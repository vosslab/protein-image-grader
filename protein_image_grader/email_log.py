"""
Per-semester email-status tracking for protein-image feedback emails.

Stores current-state-only data at:
	Protein_Images/semesters/<term>/email_log.yml

Shape (Student ID -> image_NN -> {status, attempted_at, [message]}):

	'900646199':
	  username: adarbanova
	  email: adarbanova@mail.roosevelt.edu
	  image_01:
	    status: sent
	    attempted_at: 2026-05-06T14:32:11
	  image_02:
	    status: failed
	    attempted_at: 2026-05-06T14:33:02
	    message: 'AppleScript: timeout'

Writes are atomic (tempfile + os.replace) so a crash mid-dump cannot
truncate the log. No history list; a new attempt overwrites the cell.
"""

# Standard Library
import os
import tempfile

# PIP3 modules
import yaml

# local repo modules
import protein_image_grader.protein_images_path as protein_images_path


# VALID_STATUSES are every value a cell may carry. CLOSING_STATUSES is the
# subset that closes out an expected Student ID for the email step: a roster
# row counts as "heard back from us" only when its cell is in this set.
VALID_STATUSES = ("sent", "failed", "dry_run", "no_submission_sent")
CLOSING_STATUSES = frozenset({"sent", "no_submission_sent"})


#============================================
def _image_key(image_number: int) -> str:
	# Zero-padded image_NN matches output-protein_image_NN.* convention.
	return f"image_{image_number:02d}"


#============================================
def load(term: str) -> dict:
	"""
	Read the email log for `term`. Returns {} if the file is missing.
	"""
	path = protein_images_path.get_email_log_yaml(term)
	if not path.is_file():
		return {}
	with open(path, "r", encoding="ascii") as handle:
		data = yaml.safe_load(handle)
	# Empty file -> safe_load returns None; treat as empty log.
	if data is None:
		return {}
	return data


#============================================
def _ordered_student_record(record: dict) -> dict:
	"""
	Build a new dict with username/email first, then sorted image_NN keys.
	Done explicitly so safe_dump preserves a human-readable layout.
	"""
	ordered = {}
	if "username" in record:
		ordered["username"] = record["username"]
	if "email" in record:
		ordered["email"] = record["email"]
	image_keys = sorted(k for k in record.keys()
		if k.startswith("image_"))
	for key in image_keys:
		ordered[key] = record[key]
	return ordered


#============================================
def save(term: str, data: dict) -> None:
	"""
	Atomically write the email log for `term`.

	Top-level Student IDs are sorted; inside each record, username/email
	come before image_NN keys. Atomicity via tempfile + os.replace.
	"""
	path = protein_images_path.get_email_log_yaml(term)
	term_dir = path.parent
	term_dir.mkdir(parents=True, exist_ok=True)

	# Build an ordered copy so safe_dump preserves our layout.
	ordered = {}
	for student_id in sorted(data.keys()):
		ordered[student_id] = _ordered_student_record(data[student_id])

	# Write to a sibling tempfile and atomically replace the target.
	fd, tmp_path = tempfile.mkstemp(prefix=".email_log.", suffix=".tmp",
		dir=str(term_dir))
	try:
		with os.fdopen(fd, "w", encoding="ascii") as handle:
			yaml.safe_dump(ordered, handle, sort_keys=False,
				default_flow_style=False)
		os.replace(tmp_path, path)
	except Exception:
		# Clean up the temp file if the dump failed before replace.
		if os.path.exists(tmp_path):
			os.unlink(tmp_path)
		raise


#============================================
def get_status(data: dict, student_id: str, image_number: int):
	"""
	Return the stored status for (student_id, image_number), or None.

	Returns None for unknown student IDs and for known students who have
	no entry for this image yet.
	"""
	record = data.get(student_id)
	if record is None:
		return None
	cell = record.get(_image_key(image_number))
	if cell is None:
		return None
	return cell.get("status")


#============================================
def set_status(data: dict, student_id: str, image_number: int,
		status: str, attempted_at: str, username: str, email: str,
		message: str = "") -> None:
	"""
	Overwrite the (student_id, image_number) cell with a new status.

	Raises ValueError when status is not one of VALID_STATUSES. Always
	overwrites the previous cell value (no history list).
	"""
	if status not in VALID_STATUSES:
		raise ValueError(
			f"Invalid status {status!r}; expected one of {VALID_STATUSES}"
		)
	# Ensure the top-level student record exists with username/email.
	record = data.setdefault(student_id, {})
	record["username"] = username
	record["email"] = email
	cell = {
		"status": status,
		"attempted_at": attempted_at,
	}
	if message:
		cell["message"] = message
	record[_image_key(image_number)] = cell


#============================================
def summarize_image(data: dict, image_number: int,
		expected_student_ids) -> str:
	"""
	Compute the dashboard 'Emailed' status for one image.

	Only `expected_student_ids` count; extra/old IDs in the log are
	ignored. Returns:
	  - "MISSING" when no expected student has any status for this image.
	  - "OK" when every expected student has a closing status, that is
	    "sent" (real feedback) or "no_submission_sent" (no-submission
	    notice). Mixed populations of the two still close OK.
	  - "PARTIAL" otherwise. A single dry_run or failed cell among the
	    expected IDs forces PARTIAL, so a dry-run pass cannot light OK.
	"""
	expected_ids = list(expected_student_ids)
	if not expected_ids:
		return "MISSING"
	statuses = []
	for student_id in expected_ids:
		statuses.append(get_status(data, student_id, image_number))
	any_status = any(s is not None for s in statuses)
	if not any_status:
		return "MISSING"
	all_closed = all(s in CLOSING_STATUSES for s in statuses)
	if all_closed:
		return "OK"
	return "PARTIAL"


#============================================
def summarize_image_by_submission(data: dict, image_number: int,
		roster_student_ids, submitted_student_ids) -> str:
	"""
	Compute email status when the dashboard knows who submitted.

	Submitters must have `sent`; a stale `no_submission_sent` for a
	student who later got graded is not acceptable. Roster students who did
	not submit may close with any closing status, which preserves the
	no-submission notice workflow.
	"""
	roster_ids = set(str(student_id) for student_id in roster_student_ids)
	submitted_ids = set(str(student_id) for student_id in submitted_student_ids)
	expected_ids = roster_ids | submitted_ids
	if not expected_ids:
		return "MISSING"

	statuses = []
	for student_id in expected_ids:
		statuses.append(get_status(data, student_id, image_number))
	any_status = any(status is not None for status in statuses)
	if not any_status:
		return "MISSING"

	for student_id in submitted_ids:
		status = get_status(data, student_id, image_number)
		if status != "sent":
			return "PARTIAL"
	for student_id in expected_ids - submitted_ids:
		status = get_status(data, student_id, image_number)
		if status not in CLOSING_STATUSES:
			return "PARTIAL"
	return "OK"
