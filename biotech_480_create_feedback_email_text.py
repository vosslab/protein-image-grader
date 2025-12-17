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
	epilog += "- group_members_inferred.csv (group->member names/emails from respondents)\n"
	epilog += "\n"
	epilog += "Example:\n"
	epilog += "  biotech_480_create_feedback_email_text.py \\\n"
	epilog += "    -i 480_F25_W1_Group_Present_Eval.csv 480_F25_W2_Group_Present_Eval.csv \\\n"
	epilog += "    -o output_peer_feedback/\n"

	parser = argparse.ArgumentParser(
		description="Extract presenter-visible peer feedback text from BioTech 480 group peer eval CSV exports.",
		formatter_class=argparse.RawTextHelpFormatter,
		epilog=epilog,
	)
	parser.add_argument(
		"-i", "--input", dest="input_files", required=True, nargs="+",
		help="Input CSV file(s) exported from Google Forms."
	)
	parser.add_argument(
		"-o", "--output-dir", dest="output_dir", required=True,
		help="Output directory to write per-group email text files."
	)
	parser.add_argument(
		"-r", "--feedback-regex", dest="feedback_regex", default="shown to the presenters",
		help="Regex used to detect presenter-visible feedback columns (case-insensitive)."
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
		"--combine", dest="combine", action="store_true",
		help="Combine all input files into a single output file per presenting group."
	)
	parser.add_argument(
		"--no-combine", dest="combine", action="store_false",
		help="Write separate output files per input CSV."
	)
	parser.set_defaults(combine=False)

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
_slug = file_slug("Group 7 (Week 2)")
assert _slug == "group_7_week_2"


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
	member_emails: list[str],
	member_names: list[str],
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

	if member_emails or member_names:
		lines.append("")
		lines.append("Inferred group members (from survey respondents):")
		if member_names:
			lines.append("Names:")
			for n in member_names:
				lines.append(f"- {n}")
		if member_emails:
			lines.append("Emails:")
			for e in member_emails:
				lines.append(f"- {e}")

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

	all_results: list[dict] = []
	for csv_path in args.input_files:
		if not os.path.exists(csv_path):
			raise ValueError(f"Input file not found: {csv_path}")
		result = process_one_file(csv_path, args)
		all_results.append(result)

	# Build combined structures.
	combined_members: dict[str, dict[str, set[str]]] = {}
	combined_feedback: dict[str, dict[str, list[str]]] = {}
	group_name_by_key: dict[str, str] = {}
	membership_rows: list[list[str]] = []

	for result in all_results:
		csv_path = result["csv_path"]
		source_name = os.path.basename(csv_path)

		for g_key, entry in result["group_members"].items():
			if g_key not in combined_members:
				combined_members[g_key] = {"groups": set(), "names": set(), "emails": set()}
			combined_members[g_key]["groups"] |= entry["groups"]
			combined_members[g_key]["names"] |= entry["names"]
			combined_members[g_key]["emails"] |= entry["emails"]

			# If we can find a representative group name in the file, store it.
			if g_key not in group_name_by_key:
				# Try to use a presenting group name first.
				for group_name in result["group_to_question_responses"].keys():
					if biotech_480_group_peer_eval.group_key(group_name) == g_key:
						group_name_by_key[g_key] = group_name
						break

		for group_name, qmap in result["group_to_question_responses"].items():
			if group_name not in combined_feedback:
				combined_feedback[group_name] = {}
			for q, resp_list in qmap.items():
				if q not in combined_feedback[group_name]:
					combined_feedback[group_name][q] = []
				combined_feedback[group_name][q] += resp_list

		# Collect membership rows for CSV export.
		for g_key, entry in result["group_members"].items():
			g_name = group_name_by_key.get(g_key, None)
			if g_name is None:
				group_names_sorted = sorted(list(entry["groups"]))
				if group_names_sorted:
					g_name = group_names_sorted[0]
				else:
					g_name = g_key
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

	# Write inferred membership CSV.
	members_csv_path = os.path.join(args.output_dir, "group_members_inferred.csv")
	write_group_members_csv(members_csv_path, membership_rows)

	# Write outputs.
	index_lines: list[str] = []
	index_lines.append("Generated presenter-feedback email text files:")
	index_lines.append("")

	if args.combine:
		for group_name, qmap in sorted(combined_feedback.items(), key=lambda x: x[0]):
			week = biotech_480_group_peer_eval.parse_week_from_group(group_name)
			week_tag = f"W{week:02d}" if week is not None else "WXX"
			g_key = biotech_480_group_peer_eval.group_key(group_name)
			out_name = f"combined_{week_tag}_{file_slug(group_name)}.txt"
			out_path = ensure_unique_path(os.path.join(args.output_dir, out_name))

			m = combined_members.get(g_key, {"groups": set(), "names": set(), "emails": set()})
			member_names = sorted(list(m["names"]))
			member_emails = sorted(list(m["emails"]))

			subject = f"{args.subject_prefix} ({week_tag}) - {group_name}"

			write_group_email_text(
				output_path=out_path,
				subject=subject,
				group_name=group_name,
				week=week,
				source_files=[os.path.basename(r["csv_path"]) for r in all_results],
				member_emails=member_emails,
				member_names=member_names,
				question_to_responses=qmap,
			)
			index_lines.append(out_path)
	else:
		for result in all_results:
			csv_path = result["csv_path"]
			source_name = os.path.basename(csv_path)
			file_tag = os.path.splitext(source_name)[0]

			for group_name, qmap in sorted(result["group_to_question_responses"].items(), key=lambda x: x[0]):
				week = biotech_480_group_peer_eval.parse_week_from_group(group_name)
				week_tag = f"W{week:02d}" if week is not None else "WXX"
				g_key = biotech_480_group_peer_eval.group_key(group_name)
				out_name = f"{file_tag}_{week_tag}_{file_slug(group_name)}.txt"
				out_path = ensure_unique_path(os.path.join(args.output_dir, out_name))

				m = result["group_members"].get(g_key, {"groups": set(), "names": set(), "emails": set()})
				member_names = sorted(list(m["names"]))
				member_emails = sorted(list(m["emails"]))

				subject = f"{args.subject_prefix} ({week_tag}) - {group_name}"

				write_group_email_text(
					output_path=out_path,
					subject=subject,
					group_name=group_name,
					week=week,
					source_files=[source_name],
					member_emails=member_emails,
					member_names=member_names,
					question_to_responses=qmap,
				)
				index_lines.append(out_path)

	index_path = os.path.join(args.output_dir, "INDEX.txt")
	with open(index_path, "w", encoding="utf-8") as handle:
		handle.write("\n".join(index_lines).rstrip() + "\n")

	print(f"Wrote: {index_path}")
	print(f"Wrote: {members_csv_path}")


#============================================
if __name__ == "__main__":
	main()
