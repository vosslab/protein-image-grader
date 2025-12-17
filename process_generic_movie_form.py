#!/usr/bin/env python3

# Standard Library
import argparse
import csv
import datetime
import os
import re

# PIP3 modules
import yaml


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

	match_group = parser.add_argument_group("Movie matching")
	match_group.add_argument(
		"-t", "--threshold", dest="match_threshold", type=float, default=0.30,
		help="Max normalized Levenshtein distance for auto-matching movie titles"
	)
	match_group.add_argument(
		"-y", "--interactive", dest="interactive", action="store_true",
		help="Prompt to approve uncertain matches"
	)
	match_group.add_argument(
		"-Y", "--no-interactive", dest="interactive", action="store_false",
		help="Do not prompt (default)"
	)
	parser.set_defaults(interactive=False)

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
def read_roster(roster_csv: str) -> dict:
	"""Read roster CSV into a dict keyed by student_id (int)."""
	roster: dict = {}
	with open(roster_csv, "r", encoding="utf-8-sig", newline="") as f:
		reader = csv.DictReader(f)
		for row in reader:
			student_id_text = (row.get("Student ID") or row.get("StudentID") or "").strip()
			if not student_id_text:
				continue
			student_id = int(student_id_text)
			roster[student_id] = {
				"First Name": (row.get("First Name") or row.get("First") or "").strip().title(),
				"Last Name": (row.get("Last Name") or row.get("Last") or "").strip().title(),
				"Username": (row.get("Username") or "").strip(),
				"Student ID": student_id,
			}
	return roster


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
		bb_grade_field = str(entry.get("bb_grade_field", "")).strip()
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
	clean_name = clean_movie_name(movie_name)
	key_guess = f"{movie_year:04d} - {clean_name}"

	best_key: str | None = None
	best_dist = 999.0
	for canonical_key, info in movies.items():
		if info["year"] != movie_year:
			continue
		d = normalized_distance(key_guess, canonical_key)
		if d < best_dist:
			best_dist = d
			best_key = canonical_key
			continue

		for alias in info.get("aliases", []):
			alias_key = f"{movie_year:04d} - {alias}"
			d_alias = normalized_distance(key_guess, alias_key)
			if d_alias < best_dist:
				best_dist = d_alias
				best_key = canonical_key

	if best_key is None:
		return None

	if best_dist <= match_threshold:
		return best_key

	if not interactive:
		return None

	print("")
	print(f"Uncertain match: '{key_guess}'")
	print(f"Best guess: '{best_key}' (distance {best_dist:.5f})")
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
def compute_movie_grades(
	movie_key: str,
	rows: list,
	short_header: list,
	movie_info: dict,
	question_codes: list[str],
	max_score: float,
) -> dict[int, dict]:
	"""Compute grades for one movie and return per-student score dicts."""

	student_id_index = short_header.index("RU ID") if "RU ID" in short_header else 4
	submit_time_index = 0

	unique_rows = pick_latest_submission(rows, student_id_index=student_id_index, submit_time_index=submit_time_index)

	due_time = parse_time(movie_info["due"])
	abbrev = movie_info["abbrev"]
	bb_grade_field = movie_info.get("bb_grade_field", "")

	word_counts: list[float] = []
	read_scores: list[float] = []
	metrics_by_student: dict[int, dict] = {}

	for row in unique_rows:
		student_id = int(row[student_id_index].strip())
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

		metrics_by_student[student_id] = {
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
		results[student_id] = movie_grade_dict

	return results


#============================================
def merge_student_records(
	roster: dict,
	per_movie_results: list[dict[int, dict]],
) -> list[dict]:
	"""Merge roster identity with all per-movie results."""
	merged: dict[int, dict] = {}

	for student_id, roster_row in roster.items():
		merged[student_id] = dict(roster_row)

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

	roster = read_roster(args.roster_csv)
	rows, header = read_form_csv(args.input_csv)
	short_header = make_short_header(header)
	movies = load_movies_yaml(args.movies_yaml)
	question_codes = [q.strip() for q in args.question_codes.split(",") if q.strip()]

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
		result = compute_movie_grades(
			movie_key=movie_key,
			rows=groups[movie_key],
			short_header=short_header,
			movie_info=movie_info,
			question_codes=question_codes,
			max_score=args.max_score,
		)
		per_movie_results.append(result)

	records = merge_student_records(roster, per_movie_results)
	write_scores_csv(args.scores_csv, records)


#============================================
if __name__ == "__main__":
	main()
