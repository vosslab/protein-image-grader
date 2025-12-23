#!/usr/bin/env python3

import os
import sys
import time
import yaml
import random
import argparse
#pip3 install py-applescript
import applescript

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
			print(email_address)
			sys.exit(1)
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
	content += '{0:.1f} out of {1:.1f} points ({2:.0f}%)\n\n'.format(score, total_points, percent)
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
def main():
	# Initialize the argument parser
	parser = argparse.ArgumentParser(description="Script to send feedback emails based on input CSV.")

	# Define the command-line arguments
	parser.add_argument("-i", dest="image_number", type=int, help="Protein Image Number", required=True)
	parser.add_argument("-s", "--spec-dir", dest="spec_dir", type=str,
		help="Assignment spec YAML directory", default="spec_yaml_files")
	parser.add_argument("-o", "--run-dir", dest="run_dir", type=str,
		help="Output run directory", default="data/runs")
	#parser.add_argument('-s', '--subject', dest='subject', help='Subject of the email, take from YAML file')
	parser.add_argument('-n', '--dry-run', dest="dry_run", action='store_true',
		help="Perform a dry run. Process the data but don't send emails.")
	parser.set_defaults(dry_run=False)
	# Parse the arguments
	args = parser.parse_args()

	image_number = args.image_number
	spec_dir = args.spec_dir
	run_dir = args.run_dir

	if not os.path.isdir(spec_dir):
		raise ValueError(f"Spec directory not found: {spec_dir}")
	if not os.path.isdir(run_dir):
		raise ValueError(f"Run directory not found: {run_dir}")

	folder = os.path.join(run_dir, f"IMAGE_{image_number:02d}")
	config_yaml = os.path.join(spec_dir, f"protein_image_{image_number:02d}.yml")
	input_yml = os.path.join(folder, f"output-protein_image_{image_number:02d}.yml")

	# Load YAML config
	with open(config_yaml, 'r') as f:
		config = yaml.safe_load(f)

	# Load YAML config
	with open(input_yml, 'r') as f:
		student_tree = yaml.safe_load(f)

	# Randomize the entries to vary the order of email sending
	random.shuffle(student_tree)

	# For each entry in the CSV, compose and send an email
	for student_entry in student_tree:
		# Use the provided subject or default to the prefix if none was provided
		email_subject = "Feedback for "+config['assignment name']

		recipient_name, email_addresses = make_email_header(student_entry)

		email_content = make_content(student_entry, config)

		# Compose the email script using AppleScript
		email_script = compose_script(recipient_name, email_addresses, email_subject, email_content)

		# If it's not a dry run, send the email. Otherwise, just print the email content for verification.
		print(email_script)
		if not args.dry_run:
			print("WARNING RUNNING SCRIPT NOW")
			time.sleep(0.2)
			run_script(email_script)
		else:
			print(f"Would send email to {recipient_name} {email_addresses} with subject '{email_subject}'.")
			email_addresses = ["nvoss@roosevelt.edu",]
			email_script = compose_script(recipient_name, email_addresses, email_subject, email_content)
			run_script(email_script)
			sys.exit(1)

# Entry point of the script
if __name__ == '__main__':
	main()




###
