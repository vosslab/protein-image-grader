"""
Per-image "no submission received" email pipeline.

This module is the non-submitter half of the email step. It is intentionally
kept separate from `send_feedback_email.py` because that module's
`send_feedback_for_image` driver assumes a graded student tree with score
and per-question feedback fields; non-submitters do not have those fields.

The submitter and non-submitter halves share `email_log.yml` (one cell per
Student ID per image) and the same AppleScript dispatcher pattern, so the
dashboard can close out a term as "OK" once every roster Student ID has
either status `sent` (real feedback) or `no_submission_sent`
(no-submission notice).
"""

# Standard Library
import time

# local repo modules
import protein_image_grader.email_log as email_log
import protein_image_grader.applescript_dispatch as applescript_dispatch


# Roster CSV usernames are stored without the email domain. All Roosevelt
# student emails route to mail.roosevelt.edu, so we build the recipient
# address here directly rather than going through `make_email_header`,
# which expects a Form-CSV `email` field that roster rows do not have.
ROSTER_EMAIL_DOMAIN = "mail.roosevelt.edu"


#============================================
def compute_non_submitters(roster: dict, submitted_ids) -> list:
	"""
	Return roster rows whose Student ID is not in submitted_ids.

	Args:
		roster: dict keyed by int Student ID, value is the roster row dict
			(see `roster_matching.read_roster`). Iteration order of the
			roster is preserved in the output.
		submitted_ids: any iterable of Student IDs (int or str). Coerced to
			str for comparison so a roster int and a graded-YAML stringified
			ID compare equal.

	Returns:
		List of roster row dicts (the original dict references) for every
		student in `roster` whose Student ID is not in `submitted_ids`.
		Pure: roster and submitted_ids are not mutated.
	"""
	# Coerce both sides to strings; YAML may load the ID as int or str
	# depending on whether quotes were used, and the email log keys are
	# always strings.
	submitted_set = set()
	for sid in submitted_ids:
		submitted_set.add(str(sid))
	missing = []
	for student_id, row in roster.items():
		if str(student_id) in submitted_set:
			continue
		missing.append(row)
	return missing


#============================================
def _recipient_name(roster_row: dict) -> str:
	"""
	Build the friendly greeting name for a roster row.

	`roster_matching.read_roster` normalizes the stored names to lowercase
	NFKC form; we re-title-case here so the email body reads naturally
	("Alice Aaa" rather than "alice aaa").

	Args:
		roster_row: row dict from `roster_matching.read_roster`.

	Returns:
		Title-cased "First Last" string.
	"""
	first = roster_row['first_name'].title()
	last = roster_row['last_name'].title()
	full = (first + ' ' + last).strip()
	return full


#============================================
def _recipient_email(roster_row: dict) -> str:
	"""
	Build the Roosevelt email address for a roster row.

	Roster usernames are stored without the email domain by
	`roster_matching.read_roster`; we attach the canonical
	mail.roosevelt.edu domain here. We do not use `make_email_header`
	(in `send_feedback_email`) because that helper expects a Form-CSV
	`email` field that roster rows do not have.

	Args:
		roster_row: row dict from `roster_matching.read_roster`.

	Returns:
		"<username>@mail.roosevelt.edu".

	Raises:
		ValueError: if the roster row has no username (cannot route mail).
	"""
	username = roster_row['username']
	if not username:
		raise ValueError(
			f"roster row for Student ID {roster_row.get('student_id')} has"
			" no username; cannot build recipient email"
		)
	return f"{username}@{ROSTER_EMAIL_DOMAIN}"


#============================================
def make_no_submission_subject(config: dict) -> str:
	"""
	Build the subject line for the no-submission email.

	The image number is intentionally omitted from the subject line --
	the assignment name (e.g. "Protein Image 01") already encodes the
	image and a redundant "image 01" prefix would clutter inboxes that
	thread on subject.

	Args:
		config: spec YAML dict for the image. Must contain key
			`assignment name` (e.g. "Protein Image 01").

	Returns:
		Subject string of the form "No submission received for <name>".
	"""
	assignment_name = config['assignment name']
	subject = f"No submission received for {assignment_name}"
	return subject


#============================================
def make_no_submission_content(roster_row: dict, image_number: int,
		config: dict) -> str:
	"""
	Build the brief body for a no-submission email.

	Plain ASCII; mentions the assignment name and the student's name.
	No score, no per-question feedback, no late-policy boilerplate.
	"""
	assignment_name = config['assignment name']
	recipient_name = _recipient_name(roster_row)
	body = '\n'
	body += f"{assignment_name} Submission Notice\n\n"
	body += f"Student: {recipient_name}\n\n"
	body += "Our records show that no submission was received from you "
	body += f"for {assignment_name} (image number {image_number:02d}).\n\n"
	body += "If you believe this is a mistake, please contact the "
	body += "instructor.\n"
	return body


#============================================
def default_no_submission_send_func(roster_row: dict, subject: str,
		body: str) -> None:
	"""
	Default send_func injected into send_no_submission_for_image.

	Composes the AppleScript and runs it via `applescript_dispatch`.
	Tests inject a fake send_func instead.
	"""
	recipient_name = _recipient_name(roster_row)
	recipient_email = _recipient_email(roster_row)
	script = applescript_dispatch.compose_script(
		recipient_name, [recipient_email], subject, body)
	applescript_dispatch.run_script(script)


#============================================
def send_no_submission_for_image(roster_rows_missing: list,
		image_number: int, term: str, dry_run: bool, send_func,
		config: dict) -> dict:
	"""
	Iterate non-submitter roster rows and send the "no submission" notice
	for one image, recording every attempt in email_log.yml.

	Mirrors `send_feedback_email.send_feedback_for_image`: per-student log
	save, try/except around send_func so a single failure does not abort
	the batch, and skip-if-already-closed semantics. A roster row whose
	cell already has status `sent` or `no_submission_sent` is skipped.

	Returns counters keyed under the no_submission_* namespace so the
	caller can print a single combined summary alongside the submitter
	counters.
	"""
	data = email_log.load(term)
	subject = make_no_submission_subject(config)
	counters = {
		'no_submission_sent': 0,
		'no_submission_failed': 0,
		'no_submission_dry_run': 0,
		'no_submission_skipped': 0,
	}
	for roster_row in roster_rows_missing:
		# Student ID is the canonical join key across roster/grades/log.
		student_id = str(roster_row['student_id'])
		username = roster_row['username']
		email = _recipient_email(roster_row)

		latest = email_log.get_status(data, student_id, image_number)
		# Already closed (real feedback or prior no-submission notice).
		if latest in email_log.CLOSING_STATUSES:
			print(f"skip {student_id} ({username}): already {latest}")
			counters['no_submission_skipped'] += 1
			continue

		body = make_no_submission_content(roster_row, image_number, config)
		attempted_at = time.strftime("%Y-%m-%dT%H:%M:%S")

		if dry_run:
			email_log.set_status(data, student_id, image_number,
				"dry_run", attempted_at, username, email)
			email_log.save(term, data)
			print(f"dry-run no-submission {student_id} ({username})")
			counters['no_submission_dry_run'] += 1
			continue

		# Real send: capture the AppleScript outcome so a single bad
		# student does not abort the rest of the batch.
		try:
			send_func(roster_row, subject, body)
		except Exception as exc:
			email_log.set_status(data, student_id, image_number,
				"failed", attempted_at, username, email,
				message=str(exc))
			email_log.save(term, data)
			print(f"failed no-submission {student_id} ({username}): {exc}")
			counters['no_submission_failed'] += 1
			continue

		email_log.set_status(data, student_id, image_number,
			"no_submission_sent", attempted_at, username, email)
		email_log.save(term, data)
		print(f"sent no-submission {student_id} ({username})")
		counters['no_submission_sent'] += 1
	return counters
