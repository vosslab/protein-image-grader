#!/usr/bin/env python3

# Standard Library
import argparse
import csv
import difflib
import os
import re
import unicodedata

# PIP3 modules
import unidecode


#============================================
def parse_args() -> argparse.Namespace:
	"""Parse command-line arguments."""
	parser = argparse.ArgumentParser(
		description=(
			"Match submission names and usernames to a roster CSV. "
			"Supports fuzzy matching with optional interactive review."
		)
	)

	io_group = parser.add_argument_group("Inputs and outputs")
	io_group.add_argument(
		"-r", "--roster", dest="roster_csv", required=True,
		help="Roster CSV with First Name, Last Name, Username, Student ID",
	)
	io_group.add_argument(
		"-i", "--input", dest="input_csv", required=True,
		help="Submission CSV or TSV to match",
	)
	io_group.add_argument(
		"-o", "--output", dest="output_csv", default="matched_submissions.csv",
		help="Output CSV with match columns appended",
	)

	col_group = parser.add_argument_group("Submission columns")
	col_group.add_argument(
		"--col-username", dest="col_username", default="Username",
		help="Column name for username or email in the submission file",
	)
	col_group.add_argument(
		"--col-first", dest="col_first", default="Enter your first name",
		help="Column name for first name in the submission file",
	)
	col_group.add_argument(
		"--col-last", dest="col_last", default="Enter your last name",
		help="Column name for last name in the submission file",
	)
	col_group.add_argument(
		"--col-id", dest="col_student_id", default="Enter your RUID",
		help="Column name for student id in the submission file",
	)

	match_group = parser.add_argument_group("Matching")
	match_group.add_argument(
		"-n", "--dry-run", dest="dry_run", action="store_true",
		help="Do not write output files, only print a summary",
	)
	match_group.add_argument(
		"-y", "--interactive", dest="interactive", action="store_true",
		help="Prompt to approve non-obvious matches",
	)
	match_group.add_argument(
		"-Y", "--no-interactive", dest="interactive", action="store_false",
		help="Do not prompt (default)",
	)
	parser.set_defaults(interactive=False)

	match_group.add_argument(
		"-t", "--threshold", dest="auto_threshold", type=float, default=0.88,
		help="Auto-accept similarity threshold (0 to 1)",
	)
	match_group.add_argument(
		"-g", "--gap", dest="auto_gap", type=float, default=0.06,
		help="Auto-accept requires top score exceed runner-up by this gap",
	)
	match_group.add_argument(
		"-c", "--candidates", dest="candidate_count", type=int, default=5,
		help="Number of candidates to show during interactive review",
	)

	return parser.parse_args()


#============================================
def detect_delimiter(path: str) -> str:
	"""Detect a delimiter (comma or tab) by inspecting the first non-empty line."""
	with open(path, "r", encoding="utf-8-sig", newline="") as f:
		for line in f:
			line = line.strip("\r\n")
			if not line.strip():
				continue
			if line.count("\t") > line.count(","):
				return "\t"
			return ","
	return ","


#============================================
def find_column_ci(header: list[str], target: str) -> int | None:
	"""Find a column name case-insensitively."""
	needle = target.strip().lower()
	for i, name in enumerate(header):
		if name.strip().lower() == needle:
			return i
	return None


#============================================
def normalize_name_text(name_text: str) -> str:
	"""Normalize a human name for matching."""
	text = (name_text or "").strip().lower()
	text = unicodedata.normalize("NFKC", text)
	text = unidecode.unidecode(text)
	text = re.sub(r"\(.*\)", "", text).strip()
	text = re.sub(r"\'s($|\s)", r"\1", text).strip()
	text = re.sub(r"\s*(iphone|ipad)\s*", " ", text)
	text = re.sub(r"[^a-z0-9\- ]", "", text)
	text = re.sub(r"\s+", " ", text).strip()
	return text


#============================================
def normalize_username(username_text: str) -> str:
	"""Normalize a username or email for matching."""
	text = (username_text or "").strip().lower()
	text = unicodedata.normalize("NFKC", text)
	text = unidecode.unidecode(text)
	text = re.sub(r"\s+", "", text)
	return text


#============================================
def safe_int(text: str) -> int | None:
	"""Parse an int-like string, returning None when empty or invalid."""
	clean = re.sub(r"[^0-9]", "", (text or "").strip())
	if not clean:
		return None
	try:
		value = int(clean)
	except ValueError:
		return None
	return value


#============================================
def read_roster(roster_csv: str) -> dict[int, dict]:
	"""Read a roster CSV into a dict keyed by Student ID."""
	delimiter = detect_delimiter(roster_csv)
	with open(roster_csv, "r", encoding="utf-8-sig", newline="") as f:
		reader = csv.DictReader(f, delimiter=delimiter)
		roster: dict[int, dict] = {}
		for row in reader:
			student_id = safe_int(row.get("Student ID", "") or row.get("StudentID", ""))
			if student_id is None:
				continue

			first_name = normalize_name_text(row.get("First Name", "") or row.get("First", ""))
			last_name = normalize_name_text(row.get("Last Name", "") or row.get("Last", ""))
			username = normalize_username(row.get("Username", ""))
			alias = normalize_name_text(
				row.get("Alias", "") or row.get("Phonetic", "") or row.get("Preferred", "")
			)

			roster[int(student_id)] = {
				"student_id": int(student_id),
				"first_name": first_name,
				"last_name": last_name,
				"username": username,
				"alias": alias,
				"full_name": (first_name + " " + last_name).strip(),
			}
	return roster


#============================================
def build_roster_indexes(roster: dict[int, dict]) -> dict:
	"""Build lookup tables for fast matching."""
	by_username: dict[str, int] = {}
	by_name: dict[str, list[int]] = {}

	for student_id, info in roster.items():
		username = normalize_username(info.get("username", ""))
		if username:
			by_username[username] = int(student_id)
			if "@" in username:
				by_username[username.split("@", 1)[0]] = int(student_id)
			local = username.split("@", 1)[0]
			local_nodigits = re.sub(r"[0-9]+$", "", local)
			if local_nodigits:
				by_username[local_nodigits] = int(student_id)

		full_name = normalize_name_text(info.get("full_name", ""))
		if full_name:
			by_name.setdefault(full_name, []).append(int(student_id))

		flipped = normalize_name_text(info.get("last_name", "") + " " + info.get("first_name", ""))
		if flipped:
			by_name.setdefault(flipped, []).append(int(student_id))

		alias = normalize_name_text(info.get("alias", ""))
		if alias:
			by_name.setdefault(alias, []).append(int(student_id))

	return {
		"by_username": by_username,
		"by_name": by_name,
	}


#============================================
def similarity(a: str, b: str) -> float:
	"""Return a similarity score in [0, 1] using difflib ratio."""
	if not a and not b:
		return 0.0
	return difflib.SequenceMatcher(a=a, b=b).ratio()


#============================================
def score_candidate(sub: dict, roster_row: dict) -> float:
	"""Compute a combined score for a submission against a roster row."""
	sub_user = normalize_username(sub.get("username", ""))
	if "@" in sub_user:
		sub_user = sub_user.split("@", 1)[0]
	sub_user_nodigits = re.sub(r"[0-9]+$", "", sub_user)

	sub_first = normalize_name_text(sub.get("first_name", ""))
	sub_last = normalize_name_text(sub.get("last_name", ""))
	sub_full = (sub_first + " " + sub_last).strip()

	ro_user = normalize_username(roster_row.get("username", ""))
	ro_full = normalize_name_text(roster_row.get("full_name", ""))
	ro_last = normalize_name_text(roster_row.get("last_name", ""))

	name_score = similarity(sub_full, ro_full) if sub_full and ro_full else 0.0
	last_score = similarity(sub_last, ro_last) if sub_last and ro_last else 0.0
	user_score = 0.0
	if sub_user and ro_user:
		user_score = max(similarity(sub_user, ro_user), similarity(sub_user_nodigits, ro_user))

	if not sub_full:
		return user_score

	return (0.70 * name_score) + (0.20 * last_score) + (0.10 * user_score)


#============================================
def rank_candidates(sub: dict, roster: dict[int, dict], limit: int) -> list[tuple[int, float]]:
	"""Rank roster candidates for a submission."""
	items: list[tuple[int, float]] = []
	for student_id, row in roster.items():
		score = score_candidate(sub, row)
		if score <= 0.0:
			continue
		items.append((int(student_id), score))
	items.sort(key=lambda x: x[1], reverse=True)
	return items[:limit]


#============================================
def prompt_choice(sub: dict, candidates: list[tuple[int, float]], roster: dict[int, dict]) -> int | None:
	"""Prompt the user to choose a match."""
	print("")
	print("Student match needs review:")
	print(
		"Submitted: " +
		f"{sub.get('first_name','')} {sub.get('last_name','')} | " +
		f"ID={sub.get('student_id','')} | Username={sub.get('username','')}"
	)
	print("Candidates:")
	for i, (student_id, score) in enumerate(candidates, start=1):
		row = roster.get(student_id, {})
		full = row.get("full_name", "")
		user = row.get("username", "")
		print(f"  {i}) {student_id} | {full} | {user} | score={score:.3f}")
	print("  0) No match")

	value = input("Select match number (0 for no match): ").strip()
	choice = safe_int(value)
	if choice is None:
		return None
	if choice == 0:
		return None
	if 1 <= choice <= len(candidates):
		return candidates[choice - 1][0]
	return None


#============================================
def match_submission(
	sub: dict,
	roster: dict[int, dict],
	indexes: dict,
	interactive: bool,
	auto_threshold: float,
	auto_gap: float,
	candidate_count: int,
) -> tuple[int | None, str, float]:
	"""Match one submission to a roster student id."""

	sub_id = safe_int(sub.get("student_id", ""))
	if sub_id is not None and sub_id in roster:
		return int(sub_id), "student_id", 1.0

	sub_user = normalize_username(sub.get("username", ""))
	if sub_user:
		by_username = indexes.get("by_username", {})
		if sub_user in by_username:
			return int(by_username[sub_user]), "username", 1.0
		if "@" in sub_user:
			local = sub_user.split("@", 1)[0]
			if local in by_username:
				return int(by_username[local]), "email_local", 1.0
			local_nodigits = re.sub(r"[0-9]+$", "", local)
			if local_nodigits in by_username:
				return int(by_username[local_nodigits]), "email_local_nodigits", 1.0

	sub_full = normalize_name_text((sub.get("first_name", "") or "") + " " + (sub.get("last_name", "") or ""))
	if sub_full:
		by_name = indexes.get("by_name", {})
		ids = by_name.get(sub_full, [])
		if len(ids) == 1:
			return int(ids[0]), "name_exact", 1.0

	candidates = rank_candidates(sub, roster, max(candidate_count, 2))
	if not candidates:
		return None, "no_candidates", 0.0

	best_id, best_score = candidates[0]
	runner_up = candidates[1][1] if len(candidates) > 1 else 0.0
	gap = best_score - runner_up

	if best_score >= auto_threshold and gap >= auto_gap:
		return int(best_id), "auto", float(best_score)

	if not interactive:
		return None, "needs_review", float(best_score)

	chosen = prompt_choice(sub, candidates[:candidate_count], roster)
	if chosen is None:
		return None, "rejected", float(best_score)
	return int(chosen), "chosen", float(best_score)


#============================================
def read_submission_rows(path: str) -> tuple[list[list[str]], list[str], str]:
	"""Read submission CSV or TSV rows."""
	delimiter = detect_delimiter(path)
	with open(path, "r", encoding="utf-8-sig", newline="") as f:
		reader = csv.reader(f, delimiter=delimiter)
		header = next(reader)
		rows = [row for row in reader]
	return rows, header, delimiter


#============================================
def write_submission_rows(path: str, header: list[str], rows: list[list[str]], delimiter: str) -> None:
	"""Write submission rows to CSV."""
	with open(path, "w", encoding="utf-8", newline="") as f:
		writer = csv.writer(f, delimiter=delimiter)
		writer.writerow(header)
		writer.writerows(rows)


#============================================
def main() -> None:
	args = parse_args()

	if not os.path.isfile(args.roster_csv):
		raise FileNotFoundError(args.roster_csv)
	if not os.path.isfile(args.input_csv):
		raise FileNotFoundError(args.input_csv)

	roster = read_roster(args.roster_csv)
	indexes = build_roster_indexes(roster)
	rows, header, delimiter = read_submission_rows(args.input_csv)

	idx_user = find_column_ci(header, args.col_username)
	idx_first = find_column_ci(header, args.col_first)
	idx_last = find_column_ci(header, args.col_last)
	idx_id = find_column_ci(header, args.col_student_id)

	if idx_user is None and idx_first is None and idx_last is None and idx_id is None:
		raise ValueError("Could not find any requested submission columns in the input file")

	out_header = list(header)
	out_header += ["Matched Student ID", "Matched Username", "Matched Full Name", "Match Reason", "Match Score"]

	matched = 0
	unmatched = 0
	out_rows: list[list[str]] = []
	for row in rows:
		sub = {
			"username": row[idx_user] if idx_user is not None and idx_user < len(row) else "",
			"first_name": row[idx_first] if idx_first is not None and idx_first < len(row) else "",
			"last_name": row[idx_last] if idx_last is not None and idx_last < len(row) else "",
			"student_id": row[idx_id] if idx_id is not None and idx_id < len(row) else "",
		}

		student_id, reason, score = match_submission(
			sub=sub,
			roster=roster,
			indexes=indexes,
			interactive=args.interactive,
			auto_threshold=args.auto_threshold,
			auto_gap=args.auto_gap,
			candidate_count=args.candidate_count,
		)

		out_row = list(row)
		if student_id is None:
			unmatched += 1
			out_row += ["", "", "", reason, f"{score:.3f}"]
		else:
			matched += 1
			ro = roster.get(student_id, {})
			out_row += [
				str(student_id),
				ro.get("username", ""),
				ro.get("full_name", ""),
				reason,
				f"{score:.3f}",
			]
		out_rows.append(out_row)

	print(f"Matched: {matched}")
	print(f"Unmatched: {unmatched}")

	if args.dry_run:
		return
	write_submission_rows(args.output_csv, out_header, out_rows, delimiter)


#============================================
if __name__ == "__main__":
	main()
