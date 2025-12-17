#!/usr/bin/env python3

# Standard Library
import os
import re
import csv
import argparse

# Local modules
import biotech_480_group_peer_eval


#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed args.
	"""
	epilog = ""
	epilog += "Outputs:\n"
	epilog += "- INDEX.txt (list of generated files)\n"
	epilog += "- Optional group_members_inferred.csv (if enabled)\n"
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

	parser.add_argument(
		"--write-members-csv", dest="write_members_csv", action="store_true",
		help="Write group_members_inferred.csv (names/emails inferred from respondents)."
	)
	parser.add_argument(
		"--no-write-members-csv", dest="write_members_csv", action="store_false",
		help="Do not write group_members_inferred.csv."
	)
	parser.set_defaults(write_members_csv=False)

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
def find_identity_columns(headers: list[str]) -> tuple[str | None, str | None]:
	"""
	Find likely name/email columns in a Google Forms export.

	Args:
		headers (list[str]): Header row.

	Returns:
		tuple[str | None, str | None]: (name_col, email_col)
	"""
	email_col = None
	name_col = None

	for h in headers:
		h_norm = str(h or "").strip().lower()
		if email_col is None:
			if h_norm == "email address" or "email" in h_norm:
				email_col = h

	for h in headers:
		h_norm = str(h or "").strip().lower()
		if name_col is None:
			if h_norm == "name" or h_norm.startswith("your name") or h_norm.endswith(" name"):
				name_col = h
				break

	return name_col, email_col


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
def infer_group_membership(
	rows: list[dict],
	group_col: str,
	name_col: str | None,
	email_col: str | None,
) -> dict[str, dict[str, set[str]]]:
	"""
	Infer group membership mapping from respondent rows.

	Args:
		rows (list[dict]): CSV rows.
		group_col (str): Column for "Which group were you in?".
		name_col (str | None): Column with respondent name.
		email_col (str | None): Column with respondent email.

	Returns:
		dict[str, dict[str, set[str]]]: group_key -> {"groups": set, "names": set, "emails": set}
	"""
	out: dict[str, dict[str, set[str]]] = {}

	for row in rows:
		group_name = row.get(group_col, "")
		key = biotech_480_group_peer_eval.group_key(group_name)
		if key == "":
			continue

		if key not in out:
			out[key] = {"groups": set(), "names": set(), "emails": set()}

		group_name_str = str(group_name or "").strip()
		if group_name_str != "":
			out[key]["groups"].add(group_name_str)

		if name_col is not None:
			name_val = str(row.get(name_col, "") or "").strip()
			if name_val != "":
				out[key]["names"].add(name_val)

		if email_col is not None:
			email_val = str(row.get(email_col, "") or "").strip()
			if email_val != "":
				out[key]["emails"].add(email_val)

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
	text = str(value or "").strip().lower()
	text = re.sub(r"[^a-z0-9]+", "_", text)
	text = text.strip("_")
	if text == "":
		text = "unknown"
	return text


# Simple sanity check
_slug = file_slug(group_base_name("Group 7 (Week 2)"))
assert _slug == "group_7"


#============================================
def ensure_unique_path(path: str) -> str:
	"""
	Ensure a file path is unique by adding _2, _3, ... if needed.

	Args:
		path (str): Desired path.

	Returns:
		str: Unique path that does not already exist.
	"""
	if not os.path.exists(path):
		return path

	base, ext = os.path.splitext(path)
	i = 2
	while True:
		candidate = f"{base}_{i}{ext}"
		if not os.path.exists(candidate):
			return candidate
		i += 1


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
	lines.append(f"Subject: {subject}")
	lines.append("")
	lines.append("BioTech 480 - Group Presentation Peer Feedback")
	lines.append(f"Group: {group_name}")
	if week is not None:
		lines.append(f"Week: {week}")
	if source_files:
		lines.append("Source files:")
		for s in source_files:
			lines.append(f"- {s}")

	lines.append("")
	lines.append("----")
	lines.append("Presenter-visible feedback (anonymized):")
	lines.append("")

	if not question_to_responses:
		lines.append("(No presenter-visible feedback text found.)")
	else:
		for q in sorted(question_to_responses.keys()):
			resp_list = question_to_responses[q]
			if not resp_list:
				continue
			lines.append(q)
			for r in resp_list:
				lines.append(f"- {r}")
			lines.append("")

	text = "\n".join(lines).rstrip() + "\n"

	with open(output_path, "w", encoding="utf-8") as handle:
		handle.write(text)


#============================================
def write_group_members_csv(output_path: str, rows: list[list[str]]):
	"""
	Write a CSV file describing inferred group membership.

	Args:
		output_path (str): Path to write.
		rows (list[list[str]]): Rows to write.
	"""
	with open(output_path, "w", encoding="utf-8", newline="") as handle:
		writer = csv.writer(handle)
		writer.writerow(["Group Key", "Group Name", "Member Name", "Member Email", "Source File"])
		for r in rows:
			writer.writerow(r)


#============================================
def process_one_file(csv_path: str, args: argparse.Namespace) -> dict:
	"""
	Process a single peer-eval CSV into per-group feedback content.
	"""
	headers, rows = biotech_480_group_peer_eval.read_csv_rows(csv_path)
	colmap = biotech_480_group_peer_eval.find_key_columns(headers)
	group_col = colmap["group_col"]
	blocks = colmap["blocks"]

	name_col, email_col = find_identity_columns(headers)
	group_members = {}
	if args.write_members_csv:
		group_members = infer_group_membership(rows, group_col, name_col, email_col)

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
		"group_members": group_members,
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

	membership_rows: list[list[str]] = []
	written_paths: list[str] = []

	# Collect membership rows for CSV export (optional).
	if args.write_members_csv:
		for g_key, entry in result["group_members"].items():
			group_names_sorted = sorted(list(entry["groups"]))
			g_name = group_names_sorted[0] if group_names_sorted else g_key
			names_sorted = sorted(list(entry["names"]))
			emails_sorted = sorted(list(entry["emails"]))

			if not names_sorted and not emails_sorted:
				membership_rows.append([g_key, g_name, "", "", source_name])
				continue

			# Emit one row per (name,email) combination for human readability.
			max_len = max(len(names_sorted), len(emails_sorted))
			if max_len == 0:
				max_len = 1
			for i in range(max_len):
				n = names_sorted[i] if i < len(names_sorted) else ""
				e = emails_sorted[i] if i < len(emails_sorted) else ""
				membership_rows.append([g_key, g_name, n, e, source_name])

	# Write inferred membership CSV (optional).
	members_csv_path = None
	if args.write_members_csv:
		members_csv_path = os.path.join(args.output_dir, "group_members_inferred.csv")
		write_group_members_csv(members_csv_path, membership_rows)
		written_paths.append(members_csv_path)

	# Write outputs.
	index_lines: list[str] = []
	index_lines.append("Generated presenter-feedback email text files:")
	index_lines.append("")

	for group_name, qmap in sorted(result["group_to_question_responses"].items(), key=lambda x: x[0]):
		week = biotech_480_group_peer_eval.parse_week_from_group(group_name)
		base_name = group_base_name(group_name)
		out_name = f"{file_slug(base_name)}.txt"
		out_path = ensure_unique_path(os.path.join(args.output_dir, out_name))
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
		index_lines.append(out_path)
		written_paths.append(out_path)

	index_path = os.path.join(args.output_dir, "INDEX.txt")
	with open(index_path, "w", encoding="utf-8") as handle:
		handle.write("\n".join(index_lines).rstrip() + "\n")
	written_paths.append(index_path)

	print("Wrote files:")
	for p in written_paths:
		print(p)


#============================================
if __name__ == "__main__":
	main()
