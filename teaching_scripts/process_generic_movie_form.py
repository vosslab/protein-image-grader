#!/usr/bin/env python3

# Standard Library
import argparse
import csv
import datetime
import os
import re

# PIP3 modules
import yaml

# local modules
from tool_scripts import roster_matching


#============================================
def parse_args() -> argparse.Namespace:
	"""Parse command-line arguments."""
	parser = argparse.ArgumentParser(
		description=(
			"Process a Generic Movie Questions Form export and produce per-movie grades. "
			"Movie metadata (due dates, abbreviations, gradebook columns) is loaded from YAML."
		)
	)

	io_group = parser.add_argument_group("Inputs and outputs")
	io_group.add_argument(
		"-i", "--input", dest="input_csv", required=True,
		help="Input form CSV (for example Generic_Movie_Questions_Form.csv)"
	)
	io_group.add_argument(
		"-r", "--roster", dest="roster_csv", required=True,
		help="Student roster CSV (must include Student ID, Username, First Name, Last Name)"
	)
	io_group.add_argument(
		"-m", "--movies", dest="movies_yaml", required=True,
		help="Movie details YAML (due dates, abbreviations, gradebook column names)"
	)
	io_group.add_argument(
		"-p", "--processed-form", dest="processed_form_csv", default="Processed_Generic_Movie_Questions_Form.csv",
		help="Output CSV with cleaned movie title/year"
	)
	io_group.add_argument(
		"-o", "--output", dest="scores_csv", default="generic_movie_scores.csv",
		help="Output CSV with per-student scores"
	)
	io_group.add_argument(
		"-u", "--unmatched", dest="unmatched_csv", default="unmatched_students.csv",
		help="Output CSV listing submissions that could not be matched to the roster"
	)

	match_group = parser.add_argument_group("Movie matching")
	match_group.add_argument(
		"-t", "--threshold", dest="match_threshold", type=float, default=0.30,
		help="Max match score for auto-matching movie titles (title distance + small year penalty)"
	)
	match_group.add_argument(
		"-y", "--interactive", dest="interactive", action="store_true",
		help="Prompt to approve uncertain matches"
	)
	match_group.add_argument(
		"-Y", "--no-interactive", dest="interactive", action="store_false",
		help="Do not prompt"
	)
	parser.set_defaults(interactive=True)

	student_group = parser.add_argument_group("Student matching")
	student_group.add_argument(
		"--require-student-match", dest="require_student_match", action="store_true",
		help="Require every submission to match a roster student",
	)
	student_group.add_argument(
		"--allow-unmatched-students", dest="require_student_match", action="store_false",
		help="Allow submissions that do not match the roster (default)",
	)
	student_group.add_argument(
		"-T", "--student-threshold", dest="student_threshold", type=float, default=0.88,
		help="Auto-accept similarity threshold for student matching (0 to 1)"
	)
	student_group.add_argument(
		"-G", "--student-gap", dest="student_gap", type=float, default=0.06,
		help="Auto-accept requires top score exceed runner-up by this gap"
	)
	student_group.add_argument(
		"-C", "--student-candidates", dest="student_candidates", type=int, default=5,
		help="Candidates to show in interactive student matching"
	)
	parser.set_defaults(require_student_match=False)

	grade_group = parser.add_argument_group("Grading")
	grade_group.add_argument(
		"-s", "--max-score", dest="max_score", type=float, default=5.0,
		help="Max score per movie"
	)
	grade_group.add_argument(
		"-q", "--questions", dest="question_codes", default="B1,B2,B3,B4,B5,B6,B7,C1,C2,D1",
		help="Comma-separated question codes to grade (default matches the legacy script)"
	)

	args = parser.parse_args()
	return args


#============================================
def ansi_wrap(text: str, code: str) -> str:
	"""Wrap text with an ANSI color code."""
	return f"\033[{code}m{text}\033[0m"


#============================================
def print_section(title: str, code: str = "96") -> None:
	"""Print a colored section header."""
	bar = "=" * 70
	print("")
	print(ansi_wrap(bar, code))
	print(ansi_wrap(title.strip(), code))
	print(ansi_wrap(bar, code))


#============================================
def write_unmatched_csv(path: str, records: list[dict]) -> None:
	"""Write unmatched submission info to CSV."""
	if not path:
		return
	if not records:
		return

	fields = [
		"Timestamp",
		"Movie Key",
		"Submitted Username",
		"Submitted First Name",
		"Submitted Last Name",
		"Submitted RUID",
		"Reason",
		"Score",
	]
	with open(path, "w", encoding="utf-8", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
		writer.writeheader()
		for rec in records:
			writer.writerow(rec)


#============================================
def read_form_csv(input_csv: str) -> tuple[list, list]:
	"""Read the form export CSV."""
	with open(input_csv, "r", encoding="utf-8-sig", newline="") as f:
		reader = csv.reader(f)
		rows: list = []
		header: list | None = None
		for row in reader:
			if header is None:
				header = row
				continue
			rows.append(row)
	if header is None:
		raise ValueError("Input CSV appears to be empty")
	return rows, header


#============================================
def write_csv_rows(out_csv: str, header: list, rows: list) -> None:
	"""Write a CSV with a list-of-lists body."""
	with open(out_csv, "w", encoding="utf-8", newline="") as f:
		writer = csv.writer(f)
		writer.writerow(header)
		writer.writerows(rows)


#============================================
def make_short_header(header: list) -> list:
	"""Create the legacy short header (A1, B1, etc.) from Google Form column names."""
	short_header: list = []
	for header_text in header:
		if header_text.startswith("Enter your"):
			short_text = header_text.replace("Enter your", "").strip()
			short_header.append(short_text)
			continue
		if re.match(r"^[A-Z][0-9]\. ", header_text):
			short_header.append(header_text[:2])
			continue
		if " " not in header_text:
			short_header.append(header_text)
			continue
		if " are you" in header_text:
			short_text = re.sub(r" are you", "", header_text)
			short_header.append(short_text)
			continue
		short_header.append(header_text)
	return short_header


#============================================
def clean_movie_name(movie_name_text: str) -> str:
	"""Normalize movie title from free-text user input."""
	text = movie_name_text.strip()
	text = re.sub(r'^"', "", text)
	text = re.sub(r'"$', "", text)
	text = re.sub(r"\s*\([0-9]+\)\s*", "", text)
	text = re.sub(r"[^A-Za-z0-9 ]", "", text)
	text = text.title()
	text = re.sub(r"^The ", "", text)
	return text


#============================================
def normalize_movie_title_for_matching(movie_name_text: str) -> str:
	"""Normalize movie titles for fuzzy matching (more tolerant than clean_movie_name)."""
	text = clean_movie_name(movie_name_text)

	# Common leading phrasing
	text = re.sub(r"^I Watched ", "", text, flags=re.IGNORECASE)
	text = re.sub(r"^Watched ", "", text, flags=re.IGNORECASE)

	# Remove standalone years embedded in the title text
	text = re.sub(r"\b(19|20)[0-9]{2}\b", " ", text)
	text = re.sub(r"\s+", " ", text).strip()
	return text


#============================================
def parse_year(movie_year_text: str) -> int:
	"""Parse a year that may include extra characters."""
	text = movie_year_text.strip()
	text = re.sub(r"[^0-9]", "", text)
	if len(text) > 4:
		text = text[:4]
	if len(text) != 4:
		raise ValueError(f"Could not parse year from '{movie_year_text}'")
	return int(text)


#============================================
def levenshtein(s1: str, s2: str) -> int:
	"""Compute Levenshtein edit distance."""
	if len(s1) < len(s2):
		return levenshtein(s2, s1)
	if not s1:
		return len(s2)
	previous_row = list(range(len(s2) + 1))
	for i, c1 in enumerate(s1):
		current_row = [i + 1]
		for j, c2 in enumerate(s2):
			insertions = previous_row[j + 1] + 1
			deletions = current_row[j] + 1
			substitutions = previous_row[j] + (c1 != c2)
			current_row.append(min(insertions, deletions, substitutions))
		previous_row = current_row
	return previous_row[-1]


#============================================
def normalized_distance(s1: str, s2: str) -> float:
	"""Return Levenshtein distance normalized to [0, 1]."""
	size = max(len(s1), len(s2))
	if size == 0:
		return 0.0
	distance = levenshtein(s1, s2)
	return distance / float(size)


#============================================
def load_movies_yaml(movies_yaml: str) -> dict:
	"""Load movies YAML and return a dict keyed by canonical 'YEAR - TITLE'."""
	with open(movies_yaml, "r", encoding="utf-8") as f:
		data = yaml.safe_load(f)

	if not isinstance(data, dict) or "movies" not in data:
		raise ValueError("Movies YAML must be a mapping with a top-level 'movies' key")

	movies_list = data.get("movies")
	if not isinstance(movies_list, list):
		raise ValueError("Movies YAML 'movies' must be a list")

	movies: dict = {}
	for entry in movies_list:
		if not isinstance(entry, dict):
			continue
		year = int(entry["year"])
		title = str(entry["title"]).strip()
		abbrev = str(entry["abbrev"]).strip()
		due = str(entry["due"]).strip()
		bb_grade_field = str(entry.get("gradebook_field", "") or entry.get("bb_grade_field", "")).strip()
		aliases = entry.get("aliases", [])
		if aliases is None:
			aliases = []
		if not isinstance(aliases, list):
			raise ValueError("Movie aliases must be a list")
		canonical_key = f"{year:04d} - {clean_movie_name(title)}"
		movies[canonical_key] = {
			"year": year,
			"title": clean_movie_name(title),
			"abbrev": abbrev,
			"due": due,
			"bb_grade_field": bb_grade_field,
			"aliases": [clean_movie_name(a) for a in aliases],
		}
	return movies


#============================================
def parse_time(time_string: str) -> datetime.datetime:
	"""Parse timestamp strings like '2024/06/04 11:59:59 PM CST'."""
	text = time_string.strip()
	if re.search(r" [CE][DS]T$", text):
		text = text[:-4].strip()
	return datetime.datetime.strptime(text, "%Y/%m/%d %I:%M:%S %p")


#============================================
def coleman_liau_index(text: str) -> float:
	"""Compute the Coleman-Liau index for a body of text.

	This uses a simple heuristic for sentences (., !, ?) and counts letters as A-Z.
	"""
	words = re.findall(r"\b\w+\b", text)
	word_count = len(words)
	if word_count == 0:
		return 0.0

	letters = re.findall(r"[A-Za-z]", text)
	sentences = re.findall(r"[.!?]", text)

	L = (len(letters) / float(word_count)) * 100.0
	S = (len(sentences) / float(word_count)) * 100.0
	index = (0.0588 * L) - (0.296 * S) - 15.8
	if index < 0:
		index = 0.0
	return float(index)


#============================================
def hour_penalty(timediff: datetime.timedelta) -> float:
	"""Return a penalty based on how late the submission is."""
	hours = timediff.total_seconds() / 3600.0
	days = timediff.days
	if hours <= 0:
		return 0.0
	if hours <= 27:
		return 0.1
	if days <= 7:
		return 0.2
	if days <= 28:
		return 0.5
	return 0.9


#============================================
def min_avg_or_median(values: list[float]) -> float:
	"""Return min(avg, median) for a list of floats."""
	if not values:
		return 0.0
	sorted_values = list(values)
	sorted_values.sort()
	avg = sum(sorted_values) / float(len(sorted_values))
	median = sorted_values[len(sorted_values) // 2]
	return min(avg, median)


#============================================
def pick_latest_submission(rows: list, student_id_index: int, submit_time_index: int) -> list:
	"""Collapse multiple submissions to the latest per student id."""
	latest: dict[int, tuple[datetime.datetime, list]] = {}
	for row in rows:
		student_id_text = row[student_id_index].strip()
		if not student_id_text:
			continue
		student_id = int(student_id_text)
		submit_time = parse_time(row[submit_time_index])
		current = latest.get(student_id)
		if current is None or submit_time > current[0]:
			latest[student_id] = (submit_time, row)

	collapsed = [entry[1] for entry in latest.values()]
	return collapsed


#============================================
def match_movie_key(
	movie_name: str,
	movie_year: int,
	movies: dict,
	match_threshold: float,
	interactive: bool,
) -> str | None:
	"""Match a free-text movie title and year to a canonical movie key."""
	clean_name = normalize_movie_title_for_matching(movie_name)
	key_guess = f"{movie_year:04d} - {clean_name}"

	best_key: str | None = None
	best_score = 999.0
	best_title_dist = 999.0
	best_year_delta = 999

	for canonical_key, info in movies.items():
		candidate_year = int(info["year"])
		year_delta = abs(int(movie_year) - candidate_year)
		year_penalty = min(year_delta / 5.0, 1.0)

		candidate_titles = [info.get("title", "")]
		candidate_titles += list(info.get("aliases", []))
		for cand in candidate_titles:
			cand_clean = normalize_movie_title_for_matching(str(cand))

			if not cand_clean:
				continue

			if clean_name == cand_clean or clean_name in cand_clean or cand_clean in clean_name:
				title_dist = 0.0
			else:
				title_dist = normalized_distance(clean_name, cand_clean)

			score = float(title_dist) + (0.10 * float(year_penalty))
			if score < best_score:
				best_score = score
				best_key = canonical_key
				best_title_dist = float(title_dist)
				best_year_delta = int(year_delta)

	if best_key is None:
		return None

	if best_score <= match_threshold:
		return best_key

	if not interactive:
		return None

	print("")
	print(ansi_wrap(f"Uncertain match: '{key_guess}'", "93"))
	print(ansi_wrap(f"Best guess: '{best_key}' (score {best_score:.5f})", "96"))
	if best_year_delta > 0:
		best_year = int(movies[best_key]["year"])
		print(ansi_wrap(f"NOTE: year mismatch (input {movie_year} vs movie {best_year})", "91"))
	value = input("Approve? 1 = yes; 0 = no: ").strip()
	if value == "1":
		return best_key
	return None


#============================================
def group_rows_by_movie(
	rows: list,
	short_header: list,
	movies: dict,
	match_threshold: float,
	interactive: bool,
) -> tuple[dict, list]:
	"""Group form rows by matched movie key and return (groups, updated_rows)."""
	movie_name_index = short_header.index("A1")
	movie_year_index = short_header.index("A2")

	groups: dict[str, list] = {}
	updated_rows = []
	for row in rows:
		raw_name = row[movie_name_index]
		raw_year = row[movie_year_index]
		try:
			year = parse_year(raw_year)
		except ValueError:
			updated_rows.append(row)
			continue

		matched_key = match_movie_key(
			movie_name=raw_name,
			movie_year=year,
			movies=movies,
			match_threshold=match_threshold,
			interactive=interactive,
		)
		if matched_key is None:
			row[movie_name_index] = raw_name + " ??????"
			updated_rows.append(row)
			continue

		canonical_title = movies[matched_key]["title"]
		row[movie_name_index] = canonical_title
		row[movie_year_index] = f"{year:04d}"
		groups[matched_key] = groups.get(matched_key, []) + [row]
		updated_rows.append(row)

	return groups, updated_rows


#============================================
def add_student_match_columns(header: list, short_header: list) -> tuple[list, list]:
	"""Append roster-match columns to both headers."""
	out_header = roster_matching.append_match_columns(header)
	out_short = roster_matching.append_match_columns(short_header)
	return out_header, out_short


#============================================
def match_students_for_rows(
	rows: list,
	short_header: list,
	matcher: roster_matching.RosterMatcher,
) -> list:
	"""Match students for all rows and append match columns to each row."""
	username_index = roster_matching.find_column_ci(short_header, "Username")

	first_name_index = None
	for name in ["first name", "First Name"]:
		idx = roster_matching.find_column_ci(short_header, name)
		if idx is not None:
			first_name_index = idx
			break

	last_name_index = None
	for name in ["last name", "Last Name"]:
		idx = roster_matching.find_column_ci(short_header, name)
		if idx is not None:
			last_name_index = idx
			break

	ruid_index = None
	for name in ["RUID", "RU ID", "RU Id", "Student ID", "StudentID"]:
		idx = roster_matching.find_column_ci(short_header, name)
		if idx is not None:
			ruid_index = idx
			break
	if ruid_index is None and len(short_header) > 4:
		ruid_index = 4

	updated_rows = []
	for row in rows:
		sub_username = row[username_index] if username_index is not None else ""
		sub_first = row[first_name_index] if first_name_index is not None else ""
		sub_last = row[last_name_index] if last_name_index is not None else ""
		sub_ruid = row[ruid_index] if ruid_index is not None and ruid_index < len(row) else ""

		student_id, reason, score = matcher.match(
			username=sub_username,
			first_name=sub_first,
			last_name=sub_last,
			student_id=sub_ruid,
		)

		out_row = list(row)
		if student_id is None:
			out_row += ["", "", "", reason, f"{score:.3f}"]
		else:
			ro = matcher.roster.get(int(student_id), {})
			out_row += [
				str(student_id),
				ro.get("username", ""),
				ro.get("full_name", ""),
				reason,
				f"{score:.3f}",
			]
		updated_rows.append(out_row)
	return updated_rows


#============================================
def compute_movie_grades(
	movie_key: str,
	rows: list,
	short_header: list,
	movie_info: dict,
	question_codes: list[str],
	max_score: float,
	unmatched_records: list[dict],
) -> dict[int, dict]:
	"""Compute grades for one movie and return per-student score dicts."""

	submit_time_index = 0
	match_id_index = roster_matching.find_column_ci(short_header, "Matched Student ID")
	match_reason_index = roster_matching.find_column_ci(short_header, "Match Reason")
	match_score_index = roster_matching.find_column_ci(short_header, "Match Score")

	username_index = None
	first_name_index = None
	last_name_index = None
	ruid_index = None
	for name in ["Username"]:
		idx = roster_matching.find_column_ci(short_header, name)
		if idx is not None:
			username_index = idx
			break
	for name in ["first name", "First Name"]:
		idx = roster_matching.find_column_ci(short_header, name)
		if idx is not None:
			first_name_index = idx
			break
	for name in ["last name", "Last Name"]:
		idx = roster_matching.find_column_ci(short_header, name)
		if idx is not None:
			last_name_index = idx
			break
	for name in ["RUID", "RU ID", "RU Id", "Student ID", "StudentID"]:
		idx = roster_matching.find_column_ci(short_header, name)
		if idx is not None:
			ruid_index = idx
			break
	if ruid_index is None and len(short_header) > 4:
		ruid_index = 4

	matched_rows: list[tuple[int, datetime.datetime, list]] = []
	for row in rows:
		try:
			submit_dt = parse_time(row[submit_time_index])
		except ValueError:
			continue

		sub_username = row[username_index] if username_index is not None else ""
		sub_first = row[first_name_index] if first_name_index is not None else ""
		sub_last = row[last_name_index] if last_name_index is not None else ""
		sub_ruid = row[ruid_index] if ruid_index is not None and ruid_index < len(row) else ""

		student_id_text = row[match_id_index] if match_id_index is not None and match_id_index < len(row) else ""
		student_id = roster_matching.safe_int(student_id_text)
		if student_id is None:
			reason = row[match_reason_index] if match_reason_index is not None and match_reason_index < len(row) else ""
			score = row[match_score_index] if match_score_index is not None and match_score_index < len(row) else ""
			unmatched_records.append(
				{
					"Timestamp": row[submit_time_index],
					"Movie Key": movie_key,
					"Submitted Username": sub_username,
					"Submitted First Name": sub_first,
					"Submitted Last Name": sub_last,
					"Submitted RUID": sub_ruid,
					"Reason": reason,
					"Score": score,
				}
			)
			continue
		matched_rows.append((int(student_id), submit_dt, row))

	latest: dict[int, tuple[datetime.datetime, list]] = {}
	for student_id, submit_dt, row in matched_rows:
		current = latest.get(student_id)
		if current is None or submit_dt > current[0]:
			latest[student_id] = (submit_dt, row)
	unique_pairs: list[tuple[int, list]] = []
	for student_id, pair in latest.items():
		unique_pairs.append((student_id, pair[1]))

	due_time = parse_time(movie_info["due"])
	abbrev = movie_info["abbrev"]
	bb_grade_field = movie_info.get("bb_grade_field", "")

	word_counts: list[float] = []
	read_scores: list[float] = []
	metrics_by_student: dict[int, dict] = {}

	for student_id, row in unique_pairs:
		submit_time = parse_time(row[submit_time_index])
		all_text = ""
		total_words = 0
		for qcode in question_codes:
			if qcode not in short_header:
				continue
			idx = short_header.index(qcode)
			content = row[idx]
			all_text += " " + content
			words = len(re.findall(r"\b\w+\b", content))
			total_words += words

		read_score = coleman_liau_index(all_text)
		days_late = max((submit_time - due_time).total_seconds(), 0.0) / (24.0 * 3600.0)

		metrics_by_student[int(student_id)] = {
			abbrev + "Word Count": total_words,
			abbrev + "Coleman-Liau": round(read_score, 1),
			abbrev + "Days Late": round(days_late, 2),
			abbrev + "Submit Time": row[submit_time_index],
			"_submit_dt": submit_time,
		}

		word_counts.append(float(total_words))
		read_scores.append(float(read_score))

	cut_read_score = min_avg_or_median(read_scores) * 0.9
	cut_word_count = min_avg_or_median(word_counts) * 0.9
	if cut_read_score <= 0:
		cut_read_score = 1.0
	if cut_word_count <= 0:
		cut_word_count = 1.0

	results: dict[int, dict] = {}
	for student_id, metrics in metrics_by_student.items():
		grade_adjust = 1.0
		if metrics[abbrev + "Word Count"] < cut_word_count:
			ratio = metrics[abbrev + "Word Count"] / cut_word_count
			grade_adjust *= (ratio ** 0.25)
		if metrics[abbrev + "Coleman-Liau"] < cut_read_score:
			ratio = metrics[abbrev + "Coleman-Liau"] / cut_read_score
			grade_adjust *= (ratio ** 0.25)

		timediff = metrics["_submit_dt"] - due_time
		penalty = hour_penalty(timediff)
		final_grade = round((max_score - penalty) * grade_adjust, 2)

		movie_grade_dict: dict = {}
		movie_grade_dict.update(metrics)
		movie_grade_dict.pop("_submit_dt", None)
		movie_grade_dict[abbrev + "GRADE"] = final_grade
		if bb_grade_field:
			movie_grade_dict[bb_grade_field] = round(final_grade, 1)
		results[int(student_id)] = movie_grade_dict

	return results


#============================================
def merge_student_records(
	roster: dict,
	per_movie_results: list[dict[int, dict]],
) -> list[dict]:
	"""Merge roster identity with all per-movie results."""
	merged: dict[int, dict] = {}

	for student_id, roster_row in roster.items():
		first_name = roster_row.get("first_name", "").strip().title()
		last_name = roster_row.get("last_name", "").strip().title()
		username = roster_row.get("username", "").strip()
		merged[int(student_id)] = {
			"First Name": first_name,
			"Last Name": last_name,
			"Username": username,
			"Student ID": int(student_id),
		}

	for movie_result in per_movie_results:
		for student_id, movie_dict in movie_result.items():
			base = merged.get(student_id)
			if base is None:
				base = {
					"First Name": "",
					"Last Name": "",
					"Username": "",
					"Student ID": student_id,
				}
				merged[student_id] = base
			merged[student_id] = {**merged[student_id], **movie_dict}

	student_ids = list(merged.keys())
	student_ids.sort()
	return [merged[sid] for sid in student_ids]


#============================================
def write_scores_csv(scores_csv: str, records: list[dict]) -> None:
	"""Write merged score dicts as a CSV."""
	base_fields = ["First Name", "Last Name", "Username", "Student ID"]
	all_fields: set = set(base_fields)
	for rec in records:
		all_fields = all_fields.union(set(rec.keys()))

	fields = list(all_fields)
	fields = [f for f in fields if f not in base_fields]
	fields.sort()
	fields = base_fields + fields

	with open(scores_csv, "w", encoding="utf-8", newline="") as f:
		writer = csv.DictWriter(f, fieldnames=fields, extrasaction="raise")
		writer.writeheader()
		for rec in records:
			out = dict(rec)
			for field in fields:
				if field not in out:
					out[field] = ""
			writer.writerow(out)


#============================================
def main() -> None:
	args = parse_args()

	if not os.path.isfile(args.input_csv):
		raise FileNotFoundError(args.input_csv)
	if not os.path.isfile(args.roster_csv):
		raise FileNotFoundError(args.roster_csv)
	if not os.path.isfile(args.movies_yaml):
		raise FileNotFoundError(args.movies_yaml)

	roster = roster_matching.load_roster(args.roster_csv)
	matcher = roster_matching.RosterMatcher(
		roster=roster,
		interactive=args.interactive,
		require_match=args.require_student_match,
		auto_threshold=args.student_threshold,
		auto_gap=args.student_gap,
		candidate_count=args.student_candidates,
	)
	unmatched_records: list[dict] = []
	rows, header = read_form_csv(args.input_csv)
	short_header = make_short_header(header)
	movies = load_movies_yaml(args.movies_yaml)
	question_codes = [q.strip() for q in args.question_codes.split(",") if q.strip()]

	print_section("ROSTER MATCHING", "96")
	header, short_header = add_student_match_columns(header, short_header)
	rows = match_students_for_rows(rows, short_header, matcher)

	print_section("MOVIE MATCHING", "95")
	groups, updated_rows = group_rows_by_movie(
		rows=rows,
		short_header=short_header,
		movies=movies,
		match_threshold=args.match_threshold,
		interactive=args.interactive,
	)
	write_csv_rows(args.processed_form_csv, header, updated_rows)

	per_movie_results: list[dict[int, dict]] = []
	for movie_key in sorted(groups.keys()):
		movie_info = movies[movie_key]
		print(ansi_wrap(f"Grading movie: {movie_key}", "92"))
		result = compute_movie_grades(
			movie_key=movie_key,
			rows=groups[movie_key],
			short_header=short_header,
			movie_info=movie_info,
			question_codes=question_codes,
			max_score=args.max_score,
			unmatched_records=unmatched_records,
		)
		per_movie_results.append(result)

	records = merge_student_records(roster, per_movie_results)
	write_scores_csv(args.scores_csv, records)
	write_unmatched_csv(args.unmatched_csv, unmatched_records)


#============================================
if __name__ == "__main__":
	main()
