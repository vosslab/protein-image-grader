#!/usr/bin/env python3

import os
import csv
import sys
import time
import yaml
import random
import argparse
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
#===============================================
def process_csv_file(input_csv, delimiter='\t'):
	"""Read a CSV file and return its content as a list of dictionaries."""
	student_tree = []

	with open(input_csv, 'r') as f:
		reader = csv.DictReader(f, delimiter=delimiter)
		for student_entry in reader:
			# Ensure all values are stripped of leading/trailing whitespace
			student_tree.append({k.strip(): v.strip() for k, v in student_entry.items()})

	print(f"Read {len(student_tree)} lines from CSV file")
	return student_tree

#===============================================
def make_email_header(csv_dict):
	#print(csv_dict.keys())
	recipient_name = csv_dict['first name'].title() + ' ' + csv_dict['last name'].title()
	original_email = csv_dict['email'].lower()
	username, domain_name = original_email.split('@')
	domain_name = FIX_DOMAINS.get(domain_name, domain_name)
	recipient_email = f"{username}@{domain_name}"
	if domain_name not in ACCEPTABLE_DOMAINS:
		print(f"unknown domain for email: {domain_name} for student {recipient_name}")
		sys.exit(1)

	return recipient_name, recipient_email

#===============================================
#===============================================
def make_content(csv_dict, config):
	score = float(csv_dict['Final Score'])
	total_points = float(config.get('total points', -1))
	percent = 100.0 * score / total_points

	content = '\n'
	content += config['assignment name'] + ' Feedback Email\n\n'
	original_email = csv_dict['email'].lower()
	recipient_name, recipient_email = make_email_header(csv_dict)
	content += f'Student: {recipient_name}\n'
	if original_email != recipient_email:
		content += 'WARNING invalid email address submitted\n'
		content += f'Original email: {original_email}\n'
	content += f'email: {recipient_email}\n\n'
	content += 'Final Score:\n'
	content += '{0:.1f} out of {1:.1f} points ({2:.0f}%)\n\n'.format(score, total_points, percent)
	content += '----\n'


	due_date_dict = {'name': 'Due Date'}
	questions_list = [due_date_dict, ]
	questions_list += config.get("csv_questions", [])
	questions_list += config.get("image_questions", [])
	print(questions_list)

	feedback_content = ''
	for question_dict in questions_list:
		name_key = question_dict['name']
		response = csv_dict.get(name_key, None)
		status = csv_dict[f"{name_key} Status"]
		deduction = csv_dict[f"{name_key} Deduction"]
		feedback = csv_dict[f"{name_key} Feedback"]
		if status == "Correct" or status == "On-Time":
			feedback_content += f'\n{name_key}: {status}\n'
		else:
			feedback_content += f'\n{name_key}: {status}\n'
			if response is not None:
				feedback_content += f'Submission: {response}\n'
			feedback_content += f'Feedback: {feedback}\n'
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
#===============================================
def main():
	# Initialize the argument parser
	parser = argparse.ArgumentParser(description="Script to send feedback emails based on input CSV.")

	# Define the command-line arguments
	parser.add_argument("-i", "--csv", dest="input_csv", help="Path to the input CSV file containing student answers.")
	parser.add_argument("-y", "--yaml", dest="config_yaml", help="Path to the YAML config file.")
	parser.add_argument('-s', '--subject', dest='subject', help='Subject of the email, take from YAML file')
	parser.add_argument('-n', '--dry-run', dest="dry_run", action='store_true',
		help="Perform a dry run. Process the data but don't send emails.")
	parser.set_defaults(dry_run=False)
	# Parse the arguments
	args = parser.parse_args()

	# Validate the input CSV path
	if not args.input_csv or not os.path.isfile(args.input_csv):
		print("Please provide a valid path to the input CSV file.")
		print("Usage: ./sendEmail.py -i <path_to_csv> [-s <email_subject>]")
		parser.print_help()
		sys.exit(1)

	# Load YAML config
	with open(args.config_yaml, 'r') as f:
		config = yaml.safe_load(f)

	# Process the CSV data
	csv_data = process_csv_file(args.input_csv)

	# Randomize the entries to vary the order of email sending
	random.shuffle(csv_data)

	# For each entry in the CSV, compose and send an email
	for csv_dict in csv_data:
		# Use the provided subject or default to the prefix if none was provided
		email_subject = args.subject or "Feedback for "+config['assignment name']

		recipient_name, recipient_email = make_email_header(csv_dict)

		email_content = make_content(csv_dict, config)

		# Compose the email script using AppleScript
		email_addresses = [recipient_email,]
		email_script = compose_script(recipient_name, email_addresses, email_subject, email_content)

		# If it's not a dry run, send the email. Otherwise, just print the email content for verification.
		print(email_script)
		if not args.dry_run:
			print("WARNING RUNNING SCRIPT NOW")
			time.sleep(0.2)
			run_script(email_script)
		else:
			print(f"Would send email to {recipient_name} {recipient_email} with subject '{email_subject}'.")
			recipient_email = "nvoss@roosevelt.edu"
			email_script = compose_script(recipient_name, recipient_email, email_subject, email_content)
			run_script(email_script)
			sys.exit(1)

# Entry point of the script
if __name__ == '__main__':
	main()




###
