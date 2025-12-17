#!/usr/bin/env python3

# Standard Library
import os
import re
import argparse
import unicodedata

# Local modules
import biotech_480_group_peer_eval


#============================================
def unicode_to_string(data: str) -> str:
	"""
	Convert Unicode text to ASCII-only text.

	This is inspired by unicode_to_string() in ../rmspaces.py and asciiText() in
	../kateCleanText.js.

	Args:
		data (str): Input text.

	Returns:
		str: ASCII-only text.
	"""
	text = str(data or "")

	# Normalize line endings.
	text = text.replace("\r\n", "\n")
	text = text.replace("\r", "\n")

	# Common punctuation normalization.
	text = re.sub(r"[\u201C\u201D\u00AB\u00BB]", "\"", text)
	text = re.sub(r"[\u2018\u2019]", "'", text)
	text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015\u2212\u2043\uFE58\uFE63\uFF0D]", "-", text)
	text = text.replace("\u2026", "...")
	text = re.sub(r"[\u2022\u00B7]", "*", text)
	text = text.replace("\u00D7", "x")
	text = text.replace("\u00F7", "/")
	text = text.replace("\u2260", "!=")
	text = text.replace("\u00B1", "+/-")
	text = text.replace("\u2248", "~")
	text = text.replace("\uFFFC", "")

	# Strip accents/diacritics and remove anything still non-ASCII.
	nfkd_form = unicodedata.normalize("NFKD", text)
	ascii_bytes = nfkd_form.encode("ASCII", "ignore")
	ascii_only = ascii_bytes.decode("ASCII")

	# Trim trailing whitespace on each line.
	ascii_only = re.sub(r"[ \t]+$", "", ascii_only, flags=re.MULTILINE)
	return ascii_only


# Simple sanity check
_ascii_test = unicode_to_string("Diana\u2019s group \u2013 Week 2 \u2026")
assert _ascii_test == "Diana's group - Week 2 ..."


#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed args.
	"""
	epilog = ""
	epilog += "Outputs:\n"
	epilog += "\n"
	epilog += "Example:\n"
	epilog += "  biotech_480_create_feedback_email_text.py \\\n"
	epilog += "    -i 480_F25_W1_Group_Present_Eval.csv \\\n"
	epilog += "    -o output_peer_feedback/\n"

	parser = argparse.ArgumentParser(
		description="Extract presenter-visible peer feedback text from BioTech 480 group peer eval CSV exports.",
		formatter_class=argparse.RawTextHelpFormatter,
		epilog=epilog,
	)
	parser.add_argument(
		"-i", "--input", dest="input_file", required=True,
		help="Input CSV file exported from Google Forms."
	)
	parser.add_argument(
		"-o", "--output-dir", dest="output_dir", default=".",
		help="Output directory to write per-group email text files."
	)
	parser.add_argument(
		"-r", "--feedback-regex", dest="feedback_regex", default="shown to the presenters",
		help="Regex used to detect presenter-visible feedback columns (case-insensitive)."
	)
	parser.add_argument(
		"-x", "--exclude-regex", dest="exclude_regex", default="instructor only",
		help="Regex for columns to exclude from emails, even if matched (case-insensitive)."
	)
	parser.add_argument(
		"-s", "--subject-prefix", dest="subject_prefix", default="BioTech 480 Group Presentation Peer Feedback",
		help="Prefix for the email Subject line."
	)

	parser.add_argument(
		"--include-ratings", dest="include_ratings", action="store_true",
		help="Include rating columns in the output text."
	)
	parser.add_argument(
		"--no-include-ratings", dest="include_ratings", action="store_false",
		help="Do not include rating columns in the output text."
	)
	parser.set_defaults(include_ratings=False)

	parser.add_argument(
		"--include-self-feedback", dest="exclude_self", action="store_false",
		help="Include self-feedback/self-ratings in the output."
	)
	parser.add_argument(
		"--exclude-self-feedback", dest="exclude_self", action="store_true",
		help="Exclude self-feedback/self-ratings from the output."
	)
	parser.set_defaults(exclude_self=True)

	args = parser.parse_args()
	return args


#============================================
def strip_suffix(header: str) -> str:
	"""
	Strip Google Forms duplicate-header suffix like ".1" / ".2".

	Args:
		header (str): Header string.

	Returns:
		str: Header without trailing suffix.
	"""
	if header is None:
		return ""
	out = re.sub(r"(\.\d+)$", "", str(header).strip())
	return out


#============================================
def clean_question_label(label: str, feedback_regex: str) -> str:
	"""
	Clean up a question label for display in the email text.

	Args:
		label (str): Raw header (without suffix).
		feedback_regex (str): Regex used to detect presenter-visible label prefix.

	Returns:
		str: Cleaned label.
	"""
	base = str(label or "").strip()

	# Remove the marker phrase if it is embedded in the question text.
	try:
		base = re.sub(feedback_regex, "", base, flags=re.IGNORECASE).strip()
	except re.error:
		# If the user provided a broken regex, keep the original label.
		base = base

	base = re.sub(r"\s+", " ", base).strip()
	return base


#============================================
def is_excluded_column(label: str, exclude_regex: str) -> bool:
	"""
	Check whether a column should be excluded from presenter emails.

	Args:
		label (str): Header label without duplicate suffix.
		exclude_regex (str): Regex of disallowed columns (case-insensitive).

	Returns:
		bool: True if excluded.
	"""
	base = str(label or "").strip()
	if base == "":
		return False
	try:
		pattern = re.compile(exclude_regex, flags=re.IGNORECASE)
	except re.error:
		return False
	return pattern.search(base) is not None


#============================================
#============================================
def detect_presenter_feedback_mode(headers: list[str], feedback_regex: str) -> bool:
	"""
	Decide whether the CSV includes explicit presenter-feedback marker columns.

	If any header matches feedback_regex, we will prefer those columns. Otherwise we
	fall back to a heuristic selection.

	Args:
		headers (list[str]): Header list.
		feedback_regex (str): Regex used to detect presenter-visible feedback.

	Returns:
		bool: True if explicit presenter feedback columns exist.
	"""
	try:
		pattern = re.compile(feedback_regex, flags=re.IGNORECASE)
	except re.error:
		return False

	for h in headers:
		base = strip_suffix(h)
		if pattern.search(base):
			return True
	return False


#============================================
def select_feedback_columns_for_block(
	headers: list[str],
	block: dict,
	include_ratings: bool,
	feedback_regex: str,
	exclude_regex: str,
	use_explicit_presenter_cols: bool,
) -> list[str]:
	"""
	Select which columns should be shown to presenters for one rating/comment block.

	Args:
		headers (list[str]): Full header list.
		block (dict): Block definition from biotech_480_group_peer_eval.find_key_columns().
		include_ratings (bool): Include rating columns.
		feedback_regex (str): Regex for selecting presenter-visible feedback columns.
		use_explicit_presenter_cols (bool): If True, select only columns whose labels match feedback_regex.

	Returns:
		list[str]: Selected column headers for this block.
	"""
	suf = block["suffix"]
	own_col = block["own_col"]
	rating_cols_set: set[str] = set(block.get("rating_cols", []))

	out: list[str] = []
	pattern = None
	if use_explicit_presenter_cols:
		try:
			pattern = re.compile(feedback_regex, flags=re.IGNORECASE)
		except re.error:
			pattern = None

	for h in headers:
		if biotech_480_group_peer_eval.col_suffix(h) != suf:
			continue
		if h == own_col:
			continue
		if (not include_ratings) and (h in rating_cols_set):
			continue

		base = strip_suffix(h)
		if is_excluded_column(base, exclude_regex):
			continue
		if use_explicit_presenter_cols and pattern is not None:
			if not pattern.search(base):
				continue

		# Heuristic fallback: include any non-rating columns in the block.
		if (not use_explicit_presenter_cols) and (h in rating_cols_set):
			continue

		out.append(h)

	# If we detected explicit presenter-feedback columns but found none for this
	# block, fall back to the heuristic selection so we still produce output.
	if use_explicit_presenter_cols and not out:
		out = select_feedback_columns_for_block(
			headers=headers,
			block=block,
			include_ratings=include_ratings,
			feedback_regex=feedback_regex,
			exclude_regex=exclude_regex,
			use_explicit_presenter_cols=False,
		)

	return out


#============================================
def group_base_name(value: str) -> str:
	"""
	Extract the base group name (drop anything in parentheses).

	Args:
		value (str): Group name.

	Returns:
		str: Base group name.
	"""
	text = str(value or "")
	text = text.split("(", 1)[0]
	text = text.strip()
	return text


#============================================
def file_slug(value: str) -> str:
	"""
	Make a filesystem-friendly ASCII slug for an output file name.

	Args:
		value (str): Input string.

	Returns:
		str: Slug containing only a-z, 0-9, and underscores.
	"""
	text = unicode_to_string(value)
	text = text.strip().lower()
	text = re.sub(r"[^a-z0-9]+", "_", text)
	text = text.strip("_")
	if text == "":
		text = "unknown"
	return text


# Simple sanity check
_slug = file_slug(group_base_name("Group 7 (Week 2)"))
assert _slug == "group_7"


#============================================
def write_group_email_text(
	output_path: str,
	subject: str,
	group_name: str,
	week: int | None,
	source_files: list[str],
	question_to_responses: dict[str, list[str]],
):
	"""
	Write a single group email text template.
	"""
	lines: list[str] = []
	lines.append(f"Subject: {unicode_to_string(subject)}")
	lines.append("")
	lines.append("BioTech 480 - Group Presentation Peer Feedback")
	lines.append(f"Group: {unicode_to_string(group_name)}")
	if week is not None:
		lines.append(f"Week: {week}")
	if source_files:
		lines.append("Source files:")
		for s in source_files:
			lines.append(f"- {unicode_to_string(s)}")

	lines.append("")
	lines.append("----")
	lines.append("Presenter-visible feedback (anonymized):")
	lines.append("")

	if not question_to_responses:
		lines.append("(No presenter-visible feedback text found.)")
	else:
		for q in sorted(question_to_responses.keys()):
			q_clean = unicode_to_string(q)
			resp_list = question_to_responses[q]
			if not resp_list:
				continue
			lines.append(q_clean)
			for r in resp_list:
				lines.append(f"- {unicode_to_string(r)}")
			lines.append("")

	text = "\n".join(lines).rstrip() + "\n"

	with open(output_path, "w", encoding="ascii", errors="replace") as handle:
		handle.write(text)


#============================================
def process_one_file(csv_path: str, args: argparse.Namespace) -> dict:
	"""
	Process a single peer-eval CSV into per-group feedback content.
	"""
	headers, rows = biotech_480_group_peer_eval.read_csv_rows(csv_path)
	colmap = biotech_480_group_peer_eval.find_key_columns(headers)
	group_col = colmap["group_col"]
	blocks = colmap["blocks"]

	suffix_to_group = biotech_480_group_peer_eval.infer_presenting_groups(rows, group_col, blocks)
	use_explicit_presenter_cols = detect_presenter_feedback_mode(headers, args.feedback_regex)

	group_to_question_responses: dict[str, dict[str, list[str]]] = {}

	for block in blocks:
		suf = block["suffix"]
		presenting_group = suffix_to_group.get(suf, f"Unknown Block {suf}")

		feedback_cols = select_feedback_columns_for_block(
			headers=headers,
			block=block,
			include_ratings=args.include_ratings,
			feedback_regex=args.feedback_regex,
			exclude_regex=args.exclude_regex,
			use_explicit_presenter_cols=use_explicit_presenter_cols,
		)
		if presenting_group not in group_to_question_responses:
			group_to_question_responses[presenting_group] = {}

		own_col = block["own_col"]
		for row in rows:
			is_self = biotech_480_group_peer_eval.norm_text(row.get(own_col)) == "yes"
			if args.exclude_self and is_self:
				continue

			for c in feedback_cols:
				val = row.get(c, "")
				val_str = str(val or "").strip()
				if val_str == "":
					continue

				q_base = strip_suffix(c)
				q_label = clean_question_label(q_base, args.feedback_regex)
				if q_label == "":
					q_label = q_base

				if q_label not in group_to_question_responses[presenting_group]:
					group_to_question_responses[presenting_group][q_label] = []

				# Normalize whitespace so text emails read cleanly.
				val_str = re.sub(r"\s+", " ", val_str).strip()
				group_to_question_responses[presenting_group][q_label].append(val_str)

	return {
		"csv_path": csv_path,
		"group_to_question_responses": group_to_question_responses,
	}


#============================================
def main():
	args = parse_args()

	os.makedirs(args.output_dir, exist_ok=True)

	csv_path = args.input_file
	if not os.path.exists(csv_path):
		raise ValueError(f"Input file not found: {csv_path}")
	result = process_one_file(csv_path, args)
	source_name = os.path.basename(csv_path)

	written_paths: list[str] = []

	# Write outputs.
	index_lines: list[str] = []
	index_lines.append("Generated presenter-feedback email text files:")
	index_lines.append("")

	for group_name, qmap in sorted(result["group_to_question_responses"].items(), key=lambda x: x[0]):
		week = biotech_480_group_peer_eval.parse_week_from_group(group_name)
		base_name = group_base_name(group_name)
		out_name = f"group_{file_slug(base_name)}.txt"
		out_path = os.path.join(args.output_dir, out_name)
		subject = f"{args.subject_prefix}"
		if week is not None:
			subject += f" (Week {week})"
		subject += f" - {base_name}"

		write_group_email_text(
			output_path=out_path,
			subject=subject,
			group_name=base_name,
			week=week,
			source_files=[source_name],
			question_to_responses=qmap,
		)
		written_paths.append(out_path)

	print("Wrote files:")
	for p in written_paths:
		print(p)


#============================================
if __name__ == "__main__":
	main()
