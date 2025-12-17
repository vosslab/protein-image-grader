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


__all__ = [
	"RosterMatcher",
	"append_match_columns",
	"build_roster_indexes",
	"detect_delimiter",
	"find_column_ci",
	"load_roster",
	"match_rows_to_roster",
	"match_submission",
	"normalize_name_text",
	"normalize_username",
	"prompt_choice",
	"read_roster",
	"safe_int",
]


#============================================
def ansi_wrap(text: str, code: str) -> str:
	"""Wrap text with an ANSI color code."""
	return f"\033[{code}m{text}\033[0m"


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
		"--require-match", dest="require_match", action="store_true",
		help="Require every row to match a roster student (will prompt when interactive)",
	)
	match_group.add_argument(
		"--allow-unmatched", dest="require_match", action="store_false",
		help="Allow unmatched rows (default)",
	)
	match_group.add_argument(
		"-y", "--interactive", dest="interactive", action="store_true",
		help="Prompt to approve non-obvious matches",
	)
	match_group.add_argument(
		"-Y", "--no-interactive", dest="interactive", action="store_false",
		help="Do not prompt",
	)
	parser.set_defaults(interactive=True)
	parser.set_defaults(require_match=False)

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
def load_roster(roster_csv: str) -> dict[int, dict]:
	"""Load a roster CSV.

	This is an import-friendly alias for read_roster.
	"""
	roster = read_roster(roster_csv)
	return roster


#============================================
def build_roster_indexes(roster: dict[int, dict]) -> dict:
	"""Build lookup tables for fast matching."""
	by_username: dict[str, int] = {}
	by_name: dict[str, list[int]] = {}
	by_first_unique: dict[str, int] = {}
	first_counts: dict[str, int] = {}

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

		first_name = normalize_name_text(info.get("first_name", ""))
		last_name = normalize_name_text(info.get("last_name", ""))
		if first_name and last_name:
			last_initial = last_name[0]
			first_last_initial = normalize_name_text(first_name + " " + last_initial)
			if first_last_initial:
				by_name.setdefault(first_last_initial, []).append(int(student_id))

		if first_name:
			first_counts[first_name] = first_counts.get(first_name, 0) + 1

	for student_id, info in roster.items():
		first_name = normalize_name_text(info.get("first_name", ""))
		if not first_name:
			continue
		if first_counts.get(first_name, 0) == 1:
			by_first_unique[first_name] = int(student_id)

	return {
		"by_username": by_username,
		"by_name": by_name,
		"by_first_unique": by_first_unique,
	}


#============================================
class RosterMatcher:
	"""Match submission identity fields to a roster.

	This is the main import-friendly API.
	"""

	def __init__(
		self,
		roster: dict[int, dict],
		interactive: bool = False,
		require_match: bool = False,
		auto_threshold: float = 0.88,
		auto_gap: float = 0.06,
		candidate_count: int = 5,
	) -> None:
		self.roster = roster
		self.indexes = build_roster_indexes(roster)
		self.interactive = interactive
		self.require_match = require_match
		self.auto_threshold = auto_threshold
		self.auto_gap = auto_gap
		self.candidate_count = candidate_count
		self.cache: dict[str, tuple[int | None, str, float]] = {}

	#============================================
	def match(
		self,
		username: str,
		first_name: str,
		last_name: str,
		student_id: str,
	) -> tuple[int | None, str, float]:
		"""Match one submission record.

		Returns (student_id or None, reason, score).
		"""
		cache_key = (
			f"{safe_int(student_id) or ''}|" +
			f"{normalize_username(username)}|" +
			f"{normalize_name_text(first_name)} {normalize_name_text(last_name)}"
		).strip()
		cached = self.cache.get(cache_key)
		if cached is not None:
			return cached

		sub = {
			"username": username,
			"first_name": first_name,
			"last_name": last_name,
			"student_id": student_id,
		}
		result = match_submission(
			sub=sub,
			roster=self.roster,
			indexes=self.indexes,
			interactive=self.interactive,
			require_match=self.require_match,
			auto_threshold=self.auto_threshold,
			auto_gap=self.auto_gap,
			candidate_count=self.candidate_count,
		)
		self.cache[cache_key] = result
		return result


#============================================
def append_match_columns(header: list[str]) -> list[str]:
	"""Return an output header with match columns appended."""
	out_header = list(header)
	out_header += [
		"Matched Student ID",
		"Matched Username",
		"Matched Full Name",
		"Match Reason",
		"Match Score",
	]
	return out_header


#============================================
def match_rows_to_roster(
		rows: list[list[str]],
		header: list[str],
		matcher: RosterMatcher,
		col_username: str = "Username",
		col_first: str = "Enter your first name",
		col_last: str = "Enter your last name",
		col_student_id: str = "Enter your RUID",
	) -> tuple[list[str], list[list[str]], dict]:
	"""Match many rows and return (out_header, out_rows, summary)."""
	idx_user = find_column_ci(header, col_username)
	idx_first = find_column_ci(header, col_first)
	idx_last = find_column_ci(header, col_last)
	idx_id = find_column_ci(header, col_student_id)

	if idx_user is None and idx_first is None and idx_last is None and idx_id is None:
		raise ValueError("Could not find any requested submission columns in the input header")

	out_header = append_match_columns(header)

	matched = 0
	unmatched = 0
	out_rows: list[list[str]] = []
	for row in rows:
		username = row[idx_user] if idx_user is not None and idx_user < len(row) else ""
		first_name = row[idx_first] if idx_first is not None and idx_first < len(row) else ""
		last_name = row[idx_last] if idx_last is not None and idx_last < len(row) else ""
		student_id = row[idx_id] if idx_id is not None and idx_id < len(row) else ""

		student_id_value, reason, score = matcher.match(
			username=username,
			first_name=first_name,
			last_name=last_name,
			student_id=student_id,
		)

		out_row = list(row)
		if student_id_value is None:
			unmatched += 1
			out_row += ["", "", "", reason, f"{score:.3f}"]
		else:
			matched += 1
			ro = matcher.roster.get(student_id_value, {})
			out_row += [
				str(student_id_value),
				ro.get("username", ""),
				ro.get("full_name", ""),
				reason,
				f"{score:.3f}",
			]
		out_rows.append(out_row)

	summary = {
		"matched": matched,
		"unmatched": unmatched,
		"total": matched + unmatched,
	}
	return out_header, out_rows, summary


#============================================
def similarity(a: str, b: str) -> float:
	"""Return a similarity score in [0, 1] using difflib ratio."""
	if not a and not b:
		return 0.0
	return difflib.SequenceMatcher(a=a, b=b).ratio()

#============================================
def looks_like_username_or_email(text: str) -> bool:
	"""Heuristic: return True when text looks like a username/email, not a display name."""
	value = (text or "").strip()
	if not value:
		return False
	if "@" in value:
		return True
	if " " in value:
		return False
	if re.search(r"[^a-z0-9._-]", value.lower()):
		return False
	return True


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
	sub_name_for_alias = sub_full if sub_full else sub_first
	sub_first_token = sub_name_for_alias.split(" ", 1)[0] if sub_name_for_alias else ""

	ro_user = normalize_username(roster_row.get("username", ""))
	ro_full = normalize_name_text(roster_row.get("full_name", ""))
	ro_last = normalize_name_text(roster_row.get("last_name", ""))
	ro_alias = normalize_name_text(roster_row.get("alias", ""))
	ro_alias_token = ro_alias.split(" ", 1)[0] if ro_alias else ""

	name_score = similarity(sub_full, ro_full) if sub_full and ro_full else 0.0
	last_score = similarity(sub_last, ro_last) if sub_last and ro_last else 0.0
	alias_score = 0.0
	if ro_alias:
		alias_full = similarity(sub_name_for_alias, ro_alias) if sub_name_for_alias else 0.0
		alias_token = similarity(sub_first_token, ro_alias_token) if sub_first_token and ro_alias_token else 0.0
		if len(sub_first_token) < 4 or len(ro_alias_token) < 4:
			alias_token = 0.0
		if alias_token < 0.80:
			alias_token = 0.0
		alias_score = max(alias_full, alias_token)
		if alias_score > name_score:
			name_score = alias_score
	user_score = 0.0
	if sub_user and ro_user:
		user_score = max(similarity(sub_user, ro_user), similarity(sub_user_nodigits, ro_user))

	if not sub_full:
		return user_score

	use_user = looks_like_username_or_email(sub.get("username", "")) and bool(sub_user) and bool(ro_user)
	use_last = bool(sub_last) and bool(ro_last)

	weights: dict[str, float] = {"name": 0.70}
	if use_last:
		weights["last"] = 0.20
	if use_user:
		weights["user"] = 0.10

	total_weight = sum(weights.values())
	if total_weight <= 0:
		return 0.0

	score = (weights["name"] * name_score)
	if use_last:
		score += (weights["last"] * last_score)
	if use_user:
		score += (weights["user"] * user_score)
	return score / total_weight


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
	sub_id = safe_int(sub.get("student_id", ""))
	sub_id_text = str(sub.get("student_id", "") or "").strip()
	print(ansi_wrap(
		"Submitted: " +
		f"{sub.get('first_name','')} {sub.get('last_name','')} | " +
		f"ID={sub_id_text} | Username={sub.get('username','')}",
		"93",
	))
	if sub_id is not None and sub_id not in roster:
		print(f"NOTE: Submitted ID {sub_id} is not present in the roster.")
	print("Candidates:")
	for i, (student_id, score) in enumerate(candidates, start=1):
		row = roster.get(student_id, {})
		full = row.get("full_name", "")
		user = row.get("username", "")
		print(f"  {i}) {student_id} | {full} | {user} | score={score:.3f}")
	print("  0) No match")
	print("  Or enter a Student ID directly")
	print("  q) Quit (fix roster / rerun with allow-unmatched)")

	value = input("Select match number (0 for no match): ").strip()
	if value.strip().lower() in ("q", "quit", "exit"):
		raise SystemExit("Aborted by user. Fix roster or rerun allowing unmatched.")
	choice = safe_int(value)
	if choice is None:
		return None
	if choice == 0:
		return None
	if 1 <= choice <= len(candidates):
		return candidates[choice - 1][0]
	if choice in roster:
		return int(choice)
	return None


#============================================
def prompt_manual_student_id(sub: dict, roster: dict[int, dict], allow_no_match: bool) -> int | None:
	"""Prompt the user to manually enter a Student ID."""
	print("")
	print("Manual roster match:")
	print(ansi_wrap(
		"Submitted: " +
		f"{sub.get('first_name','')} {sub.get('last_name','')} | " +
		f"ID={sub.get('student_id','')} | Username={sub.get('username','')}",
		"93",
	))

	while True:
		if allow_no_match:
			value = input("Enter Student ID (or 0 for no match; q to quit): ").strip()
		else:
			value = input("Enter Student ID (q to quit): ").strip()

		if value.strip().lower() in ("q", "quit", "exit"):
			raise SystemExit("Aborted by user. Fix roster or rerun allowing unmatched.")
		choice = safe_int(value)
		if choice is None:
			print("Invalid Student ID. Try again.")
			continue
		if allow_no_match and choice == 0:
			return None
		if choice in roster:
			return int(choice)
		print("Student ID not found in roster. Try again.")


#============================================
def match_submission(
	sub: dict,
	roster: dict[int, dict],
	indexes: dict,
	interactive: bool,
	auto_threshold: float,
	auto_gap: float,
	candidate_count: int,
	require_match: bool = False,
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

	sub_first = normalize_name_text(sub.get("first_name", ""))
	sub_last = normalize_name_text(sub.get("last_name", ""))
	if sub_first and not sub_last:
		by_first_unique = indexes.get("by_first_unique", {})
		if sub_first in by_first_unique:
			return int(by_first_unique[sub_first]), "first_unique", 1.0

	candidates = rank_candidates(sub, roster, max(candidate_count, 2))
	if not candidates:
		if not interactive:
			return None, "no_candidates", 0.0
		allow_no_match = not require_match
		chosen_id = prompt_manual_student_id(sub, roster, allow_no_match=allow_no_match)
		if chosen_id is None:
			return None, "rejected", 0.0
		return int(chosen_id), "manual_id", 0.0

	best_id, best_score = candidates[0]
	runner_up = candidates[1][1] if len(candidates) > 1 else 0.0
	gap = best_score - runner_up

	if best_score >= auto_threshold and gap >= auto_gap:
		return int(best_id), "auto", float(best_score)

	min_score = max(0.70, float(auto_threshold) - 0.18)
	min_gap = max(0.20, float(auto_gap) * 3.0)
	if best_score >= min_score and gap >= min_gap:
		return int(best_id), "auto_gap", float(best_score)

	if not interactive:
		return None, "needs_review", float(best_score)

	allow_no_match = not require_match
	chosen = prompt_choice(sub, candidates[:candidate_count], roster)
	if chosen is not None:
		return int(chosen), "chosen", float(best_score)
	if allow_no_match:
		return None, "rejected", float(best_score)

	print("A match is required. Enter a roster Student ID or 'q' to quit.")
	chosen_id = prompt_manual_student_id(sub, roster, allow_no_match=False)
	if chosen_id is None:
		return None, "rejected", float(best_score)
	return int(chosen_id), "manual_id", float(best_score)


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

	roster = load_roster(args.roster_csv)
	if getattr(args, "require_match", False) and not args.interactive:
		args.interactive = True
	matcher = RosterMatcher(
		roster=roster,
		interactive=args.interactive,
		require_match=getattr(args, "require_match", False),
		auto_threshold=args.auto_threshold,
		auto_gap=args.auto_gap,
		candidate_count=args.candidate_count,
	)
	rows, header, delimiter = read_submission_rows(args.input_csv)

	out_header, out_rows, summary = match_rows_to_roster(
		rows=rows,
		header=header,
		matcher=matcher,
		col_username=args.col_username,
		col_first=args.col_first,
		col_last=args.col_last,
		col_student_id=args.col_student_id,
	)

	print(f"Matched: {summary['matched']}")
	print(f"Unmatched: {summary['unmatched']}")

	if args.dry_run:
		return
	write_submission_rows(args.output_csv, out_header, out_rows, delimiter)


#============================================
if __name__ == "__main__":
	main()
