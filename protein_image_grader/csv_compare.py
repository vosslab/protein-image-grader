"""
Content-aware comparators for form CSV re-imports.

Used by start_grading.auto_import_repo_root_csvs to decide whether a
repo-root form CSV that collides with the canonical copy under
Protein_Images/semesters/<term>/forms/ is:

  - byte-identical (drop the root copy silently);
  - a strict keyed superset of the canonical copy -- every shared
    (Student ID, timestamp) key has byte-identical row content and
    the candidate may add extra keyed rows (replace canonical);
  - a real conflict (header drift, removed key, changed cells,
    duplicate key) -- raise and let the operator triage.

Comparator is keyed by (Student ID, timestamp) so re-exports that
re-order rows still match cleanly. Headers must be byte-identical;
header drift makes row equality ambiguous and is a real conflict.
"""

# Standard Library
import csv
import hashlib
import pathlib

# local repo modules
import protein_image_grader.form_columns as form_columns


_HASH_CHUNK_BYTES = 64 * 1024
_KEY_REQUIRED_COLUMNS = {"Student ID", "timestamp"}


#============================================
def hash_csv(path: pathlib.Path) -> str:
	"""
	Return the lowercase hex SHA-256 of the file at `path`.

	Args:
		path: Existing file path. Raises FileNotFoundError if missing.

	Returns:
		Lowercase hex SHA-256 digest of the file's bytes.
	"""
	hasher = hashlib.sha256()
	# Stream in 64 KiB chunks so a 50 MB CSV does not balloon RAM.
	with open(path, "rb") as handle:
		while True:
			chunk = handle.read(_HASH_CHUNK_BYTES)
			if not chunk:
				break
			hasher.update(chunk)
	return hasher.hexdigest()


#============================================
def _read_csv_rows(path: pathlib.Path) -> tuple:
	"""
	Read a CSV into (header_list, data_rows).

	Args:
		path: Existing CSV file path. Raises ValueError if the file
		has no rows at all (no header, no data).

	Returns:
		Tuple of (header, rows) where header is the first row as a list
		of strings and rows is a list of subsequent rows.
	"""
	# utf-8-sig strips an Excel BOM (U+FEFF) if present so the first
	# header cell is not prefixed with the BOM character (matches the
	# file_io_protein readers' policy).
	with open(path, "r", encoding="utf-8-sig", newline="") as handle:
		reader = csv.reader(handle)
		all_rows = list(reader)
	if not all_rows:
		raise ValueError(f"CSV is empty: {path}")
	header = all_rows[0]
	rows = all_rows[1:]
	return header, rows


#============================================
def _build_key_map(header: list, rows: list, label: str) -> tuple:
	"""
	Build a {(student_id, timestamp): row} map for one CSV.

	Args:
		header: Header row from the CSV.
		rows: Data rows from the CSV.
		label: "base" or "candidate"; used in the duplicate message.

	Returns:
		Tuple of (key_map, duplicate_message). When no duplicate is
		found, duplicate_message is the empty string. When a duplicate
		(student_id, timestamp) key is encountered, duplicate_message
		is f"duplicate key in {label}: <ruid>, <timestamp>" and
		key_map is whatever was built up to that point (caller stops
		using it).

		Rows whose Student-ID cell is empty are skipped -- those are
		form rows the downloader treats as no-submission, not
		conflicts.
	"""
	resolved = form_columns.resolve_meta_columns(header,
		required=_KEY_REQUIRED_COLUMNS)
	id_idx = resolved["Student ID"]
	ts_idx = resolved["timestamp"]
	key_map = {}
	for row in rows:
		if len(row) <= max(id_idx, ts_idx):
			continue
		student_id = row[id_idx].strip()
		timestamp = row[ts_idx].strip()
		if not student_id:
			continue
		key = (student_id, timestamp)
		if key in key_map:
			message = f"duplicate key in {label}: {student_id}, {timestamp}"
			return key_map, message
		key_map[key] = row
	return key_map, ""


#============================================
def is_strict_form_superset(base_path: pathlib.Path,
		candidate_path: pathlib.Path) -> tuple:
	"""
	Decide whether `candidate_path` is a strict keyed superset of `base_path`.

	A strict keyed superset means:
	  - both files have byte-identical headers;
	  - every (Student ID, timestamp) key in base also exists in
	    candidate, with byte-identical row content;
	  - candidate may contain additional keys, in any order;
	  - neither file has duplicate keys.

	Args:
		base_path: Existing canonical CSV (the destination).
		candidate_path: Candidate CSV (the repo-root file being imported).

	Returns:
		Tuple of (ok, reason, added_count):
		  - (True, "+N rows", N) on success;
		  - (False, "<reason>", 0) on any conflict.
	"""
	base_header, base_rows = _read_csv_rows(base_path)
	candidate_header, candidate_rows = _read_csv_rows(candidate_path)

	if base_header != candidate_header:
		return (False, "header mismatch", 0)

	# Build keyed maps; surface duplicates as conflicts.
	base_map, base_dup = _build_key_map(base_header, base_rows, "base")
	if base_dup:
		return (False, base_dup, 0)
	candidate_map, candidate_dup = _build_key_map(
		candidate_header, candidate_rows, "candidate")
	if candidate_dup:
		return (False, candidate_dup, 0)

	# Every base key must exist in candidate with byte-identical row.
	for key, base_row in base_map.items():
		student_id, timestamp = key
		if key not in candidate_map:
			return (
				False,
				f"missing row: {student_id}, {timestamp}",
				0,
			)
		if candidate_map[key] != base_row:
			return (
				False,
				f"changed row: {student_id}, {timestamp}",
				0,
			)

	added = len(candidate_map) - len(base_map)
	return (True, f"+{added} rows", added)
