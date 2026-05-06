import os
import time
import yaml
import random
import argparse
#pip3 install py-applescript
import applescript

import protein_image_grader.email_log as email_log
import protein_image_grader.protein_images_path as protein_images_path

ACCEPTABLE_DOMAINS = [
	'gmail.com',
	'mail.roosevelt.edu',
]

FIX_DOMAINS = {
	'mail.roosevelet.edu': 'mail.roosevelt.edu',
	'student.roosevelt.edu': 'mail.roosevelt.edu',
	'mail.roosevel.edu': 'mail.roosevelt.edu',
}


#===============================================
#===============================================
#https://apple.stackexchange.com/questions/125822/applescript-automate-mail-tasks
def compose_script(recipient_name: str, email_addresses: list, subject: str, content: str):
	"""
	Compose an AppleScript to send an email via the Mail application.

	Args:
		recipient_name (str): Name of the email recipient.
		email_address (str): Email address of the recipient.
		subject (str): Subject of the email.
		content (str): Content/body of the email.

	Returns:
		str: AppleScript script to send the email.

	Reference:
		https://apple.stackexchange.com/questions/125822/applescript-automate-mail-tasks
	"""
	# Initialize the script_text with common parts

	script_text = f'''
	set theSubject to "{subject}"
	set theContent to "{content}"

	tell application "Mail"
		set theMessage to make new outgoing message with properties {{subject:theSubject, content:theContent, visible:true}}
		tell theMessage
	'''
	# Loop through each email address and add a new recipient
	for email_address in email_addresses:
		if '@' not in email_address:
			raise ValueError(f"invalid email address: {email_address}")
		script_text += f'''
			make new to recipient with properties {{name:"{recipient_name}", address:"{email_address}"}}
		'''
	# Complete the script by adding the send command
	script_text += '''
			send
		end tell
	end tell
	'''
	return script_text

#===============================================
def make_email_header(student_entry):
	recipient_name = student_entry['First Name'].title() + ' ' + student_entry['Last Name'].title()

	recipient_emails = []
	username = student_entry['Username'].lower()
	student_email = f"{username}@mail.roosevelt.edu"
	recipient_emails.append(student_email)

	original_email = student_entry['email'].lower()
	username, domain_name = original_email.split('@')
	domain_name = FIX_DOMAINS.get(domain_name, domain_name)
	if domain_name == "mail.roosevelt.edu":
		processed_email = f"{username}@{domain_name}"
		if processed_email != student_email:
			print(f"Student Mixed Up Their Student Email for student {recipient_name}")
			print(processed_email)
			print(student_email)
			time.sleep(1)
	elif domain_name not in ACCEPTABLE_DOMAINS:
		print(f"unknown domain for email: {domain_name} for student {recipient_name}")
	else:
		processed_email = f"{username}@{domain_name}"
		recipient_emails.append(processed_email)
	return recipient_name, recipient_emails

#===============================================
#===============================================
def make_content(student_entry, config):
	score = float(student_entry['Final Score'])
	total_points = float(config.get('total points', -1))
	percent = 100.0 * score / total_points

	content = '\n'
	content += config['assignment name'] + ' Feedback Email\n\n'
	original_email = student_entry['email'].lower()
	recipient_name, email_addresses = make_email_header(student_entry)
	content += f'Student: {recipient_name}\n'
	if original_email not in email_addresses:
		content += 'WARNING invalid email address submitted\n'
		content += f'Original email address: {original_email}\n'
		for email_address in email_addresses:
			content += f'Sent address: {email_address}\n'
	content += 'Final Score:\n'
	content += f'{score:.1f} out of {total_points:.1f} points ({percent:.0f}%)\n\n'
	content += '----\n'


	info_fields = [
		'Student ID',
		'Original Filename',
		'Image Format',
		'128-bit MD5 Hash',
		'Consensus Background Color',
	]

	info_content = ''
	for info_key in info_fields:
		info_value = student_entry[info_key]
		info_content += f'   {info_key}: {info_value}\n'

	if len(info_content) > 0:
		content += 'Submission Information:\n'
		content += info_content
		content += '\n\n'
		content += '----\n'

	status_list = []
	for key in student_entry.keys():
		if key.endswith(' Status'):
			question_name = key[:-7].strip()
			status_list.append(question_name)

	good_feedback = ('Bonus', 'Correct', 'On-Time',)

	feedback_content = ''
	for name_key in status_list:
		response = student_entry.get(name_key, None)
		status = student_entry[f"{name_key} Status"]
		deduction = student_entry[f"{name_key} Deduction"]
		feedback = student_entry[f"{name_key} Feedback"]
		if status in good_feedback:
			if status != "Correct":
				feedback_content += f'\n{name_key}: {status}\n'
		else:
			feedback_content += f'\n{name_key}: {status}\n'
			if response is not None:
				feedback_content += f'Submission: {response}\n'
			feedback_content += f'Feedback: {feedback}\n'
			if deduction == 0:
				feedback_content += 'No deduction of points\n'
			else:
				feedback_content += f'Deduction: {deduction} points\n'
	if len(feedback_content) > 0:
		content += 'Instructor Feedback:\n\n'
		content += feedback_content
		content += '\n\n'
		content += '----\n'
	content = content.strip()
	content += '----\n'
	return content

#===============================================
#===============================================
def run_script(script_text):
	print(script_text)
	time.sleep(0.1)
	scpt = applescript.AppleScript(script_text)
	scpt.run()
	return

#===============================================
def default_send_func(student_entry: dict, subject: str, body: str) -> None:
	"""
	Default send_func injected into send_feedback_for_image.

	Composes the AppleScript and runs it. Tests inject a fake instead so
	they never touch Mail.app.
	"""
	recipient_name, email_addresses = make_email_header(student_entry)
	script = compose_script(recipient_name, email_addresses, subject, body)
	run_script(script)


#===============================================
def send_feedback_for_image(student_tree: list, image_number: int,
		term: str, dry_run: bool, send_func, config: dict) -> dict:
	"""
	Iterate student_tree and send feedback emails for one image, recording
	every attempt in email_log.yml.

	Returns a dict of counters {'sent': N, 'failed': N, 'dry_run': N,
	'skipped': N} for the caller to print a summary.

	Dry-run never calls send_func; every not-already-sent student lands
	with status 'dry_run' in the log. Real sends call send_func and record
	'sent' or 'failed' (with message) per attempt. After every student the
	log is saved so a crash mid-batch does not lose state.
	"""
	data = email_log.load(term)
	subject = "Feedback for " + config['assignment name']
	counters = {'sent': 0, 'failed': 0, 'dry_run': 0, 'skipped': 0}
	for student_entry in student_tree:
		# Student ID is the canonical join key across roster/grades/log.
		student_id = str(student_entry['Student ID'])
		username = student_entry['Username'].lower()
		email = f"{username}@mail.roosevelt.edu"

		latest = email_log.get_status(data, student_id, image_number)
		if latest == "sent":
			print(f"skip {student_id} ({username}): already sent")
			counters['skipped'] += 1
			continue

		body = make_content(student_entry, config)
		attempted_at = time.strftime("%Y-%m-%dT%H:%M:%S")

		if dry_run:
			email_log.set_status(data, student_id, image_number,
				"dry_run", attempted_at, username, email)
			email_log.save(term, data)
			print(f"dry-run {student_id} ({username})")
			counters['dry_run'] += 1
			continue

		# Real send: capture the AppleScript outcome so a single bad
		# student does not abort the rest of the batch.
		try:
			send_func(student_entry, subject, body)
		except Exception as exc:
			email_log.set_status(data, student_id, image_number,
				"failed", attempted_at, username, email,
				message=str(exc))
			email_log.save(term, data)
			print(f"failed {student_id} ({username}): {exc}")
			counters['failed'] += 1
			continue

		email_log.set_status(data, student_id, image_number,
			"sent", attempted_at, username, email)
		email_log.save(term, data)
		print(f"sent {student_id} ({username})")
		counters['sent'] += 1
	return counters


#===============================================
def parse_args():
	parser = argparse.ArgumentParser(
		description="Send feedback emails for one protein image.")
	parser.add_argument("-i", dest="image_number", type=int,
		help="Protein Image Number", required=True)
	parser.add_argument("-s", "--spec-dir", dest="spec_dir", type=str,
		help="Assignment spec YAML directory", default="spec_yaml_files")
	parser.add_argument("-o", "--run-dir", dest="run_dir", type=str,
		help="Legacy output run directory (used when --term is omitted)",
		default="data/runs")
	parser.add_argument("--term", dest="term", type=str, default=None,
		help="Active term, e.g. spring_2026. When given, paths resolve "
			"under Protein_Images/semesters/<term>/ and the email log "
			"is updated.")
	# Paired boolean flags per project style: default is dry-run; the
	# operator explicitly opts in to real sends with -e/--send-email.
	parser.add_argument('-e', '--send-email', dest='dry_run',
		action='store_false',
		help="Actually send emails (default is dry-run).")
	parser.add_argument('-n', '--dry-run', dest='dry_run',
		action='store_true',
		help="Process data but do not send emails (default).")
	parser.set_defaults(dry_run=True)
	return parser.parse_args()


#===============================================
def main():
	args = parse_args()
	image_number = args.image_number
	spec_dir = args.spec_dir

	if not os.path.isdir(spec_dir):
		raise ValueError(f"Spec directory not found: {spec_dir}")
	config_yaml = os.path.join(spec_dir,
		f"protein_image_{image_number:02d}.yml")
	with open(config_yaml, 'r') as f:
		config = yaml.safe_load(f)

	if args.term is not None:
		# Canonical mode: resolve graded YAML under
		# Protein_Images/semesters/<term>/grades/ and update the per-term
		# email log. send_feedback_for_image owns idempotency.
		grades_dir = protein_images_path.get_grades_dir(args.term)
		input_yml = grades_dir / f"output-protein_image_{image_number:02d}.yml"
		if not input_yml.is_file():
			raise FileNotFoundError(
				f"Graded YAML not found for image {image_number:02d}"
				f" in term {args.term}: {input_yml}"
			)
		with open(input_yml, 'r') as f:
			student_tree = yaml.safe_load(f)
		random.shuffle(student_tree)
		counters = send_feedback_for_image(
			student_tree, image_number, args.term, args.dry_run,
			default_send_func, config,
		)
		print(
			f"Summary: sent={counters['sent']}"
			f" failed={counters['failed']}"
			f" dry_run={counters['dry_run']}"
			f" skipped={counters['skipped']}"
		)
		return

	# Legacy mode: --run-dir layout, no email_log tracking.
	run_dir = args.run_dir
	if not os.path.isdir(run_dir):
		raise ValueError(f"Run directory not found: {run_dir}")
	folder = os.path.join(run_dir, f"IMAGE_{image_number:02d}")
	input_yml = os.path.join(folder,
		f"output-protein_image_{image_number:02d}.yml")
	with open(input_yml, 'r') as f:
		student_tree = yaml.safe_load(f)
	random.shuffle(student_tree)
	for student_entry in student_tree:
		email_subject = "Feedback for " + config['assignment name']
		recipient_name, email_addresses = make_email_header(student_entry)
		email_content = make_content(student_entry, config)
		email_script = compose_script(recipient_name, email_addresses,
			email_subject, email_content)
		print(email_script)
		if not args.dry_run:
			print("WARNING RUNNING SCRIPT NOW")
			time.sleep(0.2)
			run_script(email_script)
		else:
			print(
				f"Would send email to {recipient_name} {email_addresses}"
				f" with subject '{email_subject}'.")
			email_addresses = ["nvoss@roosevelt.edu", ]
			email_script = compose_script(recipient_name, email_addresses,
				email_subject, email_content)
			run_script(email_script)
			# Legacy dry-run mode: single test email to instructor, stop.
			break

