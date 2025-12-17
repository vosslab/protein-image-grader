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
		"-x", "--exclude-regex", dest="exclude_regex", default="instructor only",
		help="Regex for columns to exclude from emails, even if matched (case-insensitive)."
	)
	parser.add_argument(
		"-s", "--subject-prefix", dest="subject_prefix", default="BioTech 480 Group Presentation Peer Feedback",
		help="Prefix for the email Subject line."
	)

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
def find_group_col(headers: list[str]) -> str:
	"""
	Find the evaluator "Which group were you in?" column.

	Args:
		headers (list[str]): CSV headers.

	Returns:
		str: Column header.
	"""
	for h in headers:
		if str(h or "").strip() == "Which group were you in?":
			return h
	raise ValueError("Could not find 'Which group were you in?' column.")


#============================================
def find_own_cols(headers: list[str]) -> list[str]:
	"""
	Find all repeated "Was this YOUR GROUP?" block headers, in order.

	Args:
		headers (list[str]): CSV headers.

	Returns:
		list[str]: List of own-block headers in their CSV order.
	"""
	out: list[str] = []
	for h in headers:
		if str(h or "").startswith("Was this YOUR GROUP?"):
			out.append(h)
	if not out:
		raise ValueError("Could not find any 'Was this YOUR GROUP?' columns.")
	return out


#============================================
def unique_preserve_order(items: list[str]) -> list[str]:
	"""
	De-duplicate strings while preserving order.

	Args:
		items (list[str]): Input list.

	Returns:
		list[str]: Unique values preserving first-seen order.
	"""
	seen: set[str] = set()
	out: list[str] = []
	for x in items:
		if x in seen:
			continue
		seen.add(x)
		out.append(x)
	return out


#============================================
def select_key_columns_for_block(
	headers: list[str],
	exclude_regex: str,
) -> dict[str, str]:
	"""
	Select the four key columns for a block: PRODUCT, SUMMARY, BEST, NEEDS IMPROVEMENT.

	Args:
		headers (list[str]): Headers within this block only.
		exclude_regex (str): Exclusion regex.

	Returns:
		dict[str, str]: category -> header.
	"""
	patterns: list[tuple[str, re.Pattern]] = [
		("PRODUCT", re.compile(r"\bmain\s+PRODUCT\b", flags=re.IGNORECASE)),
		("SUMMARY", re.compile(r"\bshort\s+SUMMARY\b", flags=re.IGNORECASE)),
		("BEST", re.compile(r"\bBEST\s+part\b", flags=re.IGNORECASE)),
		("NEEDS IMPROVEMENT", re.compile(r"\bNEEDS\s+IMPROVEMENT\b", flags=re.IGNORECASE)),
	]

	found: dict[str, str] = {}
	for h in headers:
		base = strip_suffix(h)
		if is_excluded_column(base, exclude_regex):
			continue

		for key, pat in patterns:
			if key in found:
				continue
			if pat.search(base):
				found[key] = h

	out: dict[str, str] = {}
	for key, _pat in patterns:
		h = found.get(key)
		if h is None:
			continue
		out[key] = h
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
	lines.append("Peer feedback (anonymized):")
	lines.append("")

	if not question_to_responses:
		lines.append("(No presenter-visible feedback text found.)")
	else:
		preferred = ["PRODUCT", "SUMMARY", "BEST", "NEEDS IMPROVEMENT"]
		for q in preferred:
			if q not in question_to_responses:
				continue
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
	group_col = find_group_col(headers)
	own_cols = find_own_cols(headers)
	group_to_question_responses: dict[str, dict[str, list[str]]] = {}

	# Compute header ranges for each block based on the position of the repeated
	# "Was this YOUR GROUP?" column, instead of relying on ".1/.2" header suffixes.
	# Some repeated questions have slightly different wording, so Google Forms
	# won't add the suffix and suffix-based grouping mis-assigns feedback.
	ordered_blocks: list[tuple[int, str]] = []
	for own_col in own_cols:
		ordered_blocks.append((headers.index(own_col), own_col))
	ordered_blocks.sort(key=lambda x: x[0])

	for i, (own_idx, own_col) in enumerate(ordered_blocks):
		next_idx = ordered_blocks[i + 1][0] if i + 1 < len(ordered_blocks) else len(headers)
		block_headers = headers[own_idx + 1:next_idx]

		candidates: list[str] = []
		for row in rows:
			if biotech_480_group_peer_eval.norm_text(row.get(own_col)) == "yes":
				candidates.append(row.get(group_col, ""))
		presenting_group = biotech_480_group_peer_eval.mode_string(candidates)
		if presenting_group is None:
			presenting_group = f"Unknown block {i + 1}"

		key_cols = select_key_columns_for_block(block_headers, args.exclude_regex)
		if presenting_group not in group_to_question_responses:
			group_to_question_responses[presenting_group] = {}

		for row in rows:
			is_self = biotech_480_group_peer_eval.norm_text(row.get(own_col)) == "yes"
			if args.exclude_self and is_self:
				continue

			for key, col in key_cols.items():
				val = row.get(col, "")
				val_str = str(val or "").strip()
				if val_str == "":
					continue

				if key not in group_to_question_responses[presenting_group]:
					group_to_question_responses[presenting_group][key] = []

				# Normalize whitespace so text emails read cleanly.
				val_str = re.sub(r"\s+", " ", val_str).strip()
				group_to_question_responses[presenting_group][key].append(val_str)

		# De-duplicate within each question to reduce noise.
		for q_label, resp_list in group_to_question_responses[presenting_group].items():
			group_to_question_responses[presenting_group][q_label] = unique_preserve_order(resp_list)

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
