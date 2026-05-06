"""
AppleScript composition + dispatch for outgoing feedback emails.

Extracted from `send_feedback_email.py` so both the submitter pipeline
(`send_feedback_email`) and the non-submitter pipeline
(`no_submission_email`) can share one dispatcher without a circular
import. Touching this module means touching the actual Mail.app send
path; tests should never import `applescript` and must inject a fake
send_func instead.
"""

# Standard Library
import time

# PIP3 modules
# pip3 install py-applescript
import applescript


#===============================================
def compose_script(recipient_name: str, email_addresses: list,
		subject: str, content: str) -> str:
	"""
	Compose an AppleScript that sends one email via Mail.app.

	Args:
		recipient_name: Display name of the email recipient.
		email_addresses: One or more recipient addresses (each must
			contain '@'; ValueError otherwise).
		subject: Subject of the email.
		content: Body of the email.

	Returns:
		An AppleScript string ready to hand to `run_script`.

	Reference:
		https://apple.stackexchange.com/questions/125822/applescript-automate-mail-tasks
	"""
	# Initialize the script_text with common parts.
	script_text = f'''
	set theSubject to "{subject}"
	set theContent to "{content}"

	tell application "Mail"
		set theMessage to make new outgoing message with properties {{subject:theSubject, content:theContent, visible:true}}
		tell theMessage
	'''
	# Loop through each email address and add a new recipient.
	for email_address in email_addresses:
		if '@' not in email_address:
			raise ValueError(f"invalid email address: {email_address}")
		script_text += f'''
			make new to recipient with properties {{name:"{recipient_name}", address:"{email_address}"}}
		'''
	# Complete the script by adding the send command.
	script_text += '''
			send
		end tell
	end tell
	'''
	return script_text


#===============================================
def run_script(script_text: str) -> None:
	"""
	Execute an AppleScript string via Mail.app.

	Prints the script for operator visibility and pauses briefly so the
	output is not lost in a tight send loop.

	Args:
		script_text: AppleScript source as returned by `compose_script`.
			Must be a complete `tell application "Mail" ... end tell`
			block; partial fragments are not supported.

	Returns:
		None. Side effect: dispatches the message via Mail.app.
	"""
	print(script_text)
	time.sleep(0.1)
	scpt = applescript.AppleScript(script_text)
	scpt.run()
