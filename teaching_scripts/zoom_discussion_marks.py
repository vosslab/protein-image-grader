#!/usr/bin/env python3

import os
import re
import sys
import argparse

from collections import defaultdict

from tool_scripts import roster_matching

reject_words = [
	"thank",
	" job",
	"bye",
	"http",
	"lol",
	"smh",
	"lmao",
	"fun class",
	"good afternoon",
	"good evening",
	"good morning",
	"good day",
	"good night",
	]

emoji_limit = 20

#==============================================================================
#==============================================================================
def checkContent(content: str) -> bool:
	"""
	Checks if the content meets the specified criteria.

	Args:
	        content (str): The text content to check.

	Returns:
	        bool: True if content passes all checks, False otherwise.
	"""
	length_minimum = 5
	length_cutoff = 32

	if len(content) < length_minimum:
		return False

	# Must contain a letter
	if not re.search("[a-z]", content):
		return False

	# Remove 4 repeated letters in a row
	if re.search(r"(.)\1{3}", content) and len(content) < length_cutoff:
		return False

	# Remove 10 repeated letters in a row
	if re.search(r"(.)\1{9}", content):
		return False

	# Remove most emoji, https://stackoverflow.com/questions/30470079/emoji-value-range
	if re.search(r"[\U0001F000-\U0001FFFF]", content) and len(content) < length_cutoff:
		return False

	# Remove select words
	for word in reject_words:
		if word in content and len(content) < length_cutoff * 1.5:
			return False

	return True


# =======================
def preprocess_lines(lines: list) -> list:
	"""
	Combines lines that don't start with a timestamp to the previous line.

	Args:
	        lines (list): List of lines from the input file.

	Returns:
	        list: List of pre-processed lines with multiline messages combined.
	"""
	combined_lines = []
	current_line = ""

	for line in lines:
		sline = line.strip()

		# Check if the line starts with a timestamp
		if re.match(r"^\d{2}:\d{2}:\d{2}\t", sline):
			# If there's an existing accumulated line, add it to the list
			if current_line:
				combined_lines.append(current_line)
			# Start a new line
			current_line = sline
		else:
			# If it's a continuation line, append to the current line
			current_line += " " + sline

	# Add the last accumulated line if present
	if current_line:
		combined_lines.append(current_line)

	return combined_lines


# =======================
def process_line(
		line: str,
		name_counts: dict,
		emoji_counts: dict,
		content_dict: dict,
		name_list: set,
		roster: dict,
		matcher: roster_matching.RosterMatcher,
		unmatched_zoom_names: set,
		) -> None:
	"""
	Processes a line of input, updating name counts and content dictionary.

	Args:
	        line (str): The input line to process.
	        name_counts (dict): Dictionary storing the counts of valid and rejected entries for each name.
	        content_dict (dict): Dictionary to check for duplicate content.
	        name_list (set): Set of names encountered in the input.
	"""
	sline = line.strip().replace(": ", ":\t")
	bits = sline.split("\t")

	if len(bits) < 3:
		return

	zoom_display_name = bits[1].strip()
	zoom_name = roster_matching.normalize_name_text(zoom_display_name)
	# skip the instructor name
	if zoom_name.startswith("neil voss"):
		return

	student_id, _reason, _score = matcher.match(
		username="",
		first_name=zoom_display_name,
		last_name="",
		student_id="",
	)
	if student_id is None:
		unmatched_zoom_names.add(zoom_name)
		return

	student = roster.get(student_id, {})
	if not student:
		unmatched_zoom_names.add(zoom_name)
		return

	name = student.get("full_name", "")
	if not name:
		unmatched_zoom_names.add(zoom_name)
		return
	name_list.add(name)

	# If this is the first comment by this user, award 1 free point
	if name not in name_counts:
		name_counts[name] = 1  # Free point for the first comment

	content = bits[2].lower()

	# Remove "replying to" and the quoted content
	if content.startswith("replying to"):
		content = re.sub(r'replying to ".*?"\s*', "", content)

	if content.startswith("reacted to"):
		content = re.sub(r'reacted to ".*?"\s*', "", content)

	if not checkContent(content):
		if len(content) > 6:
			print(f"REJECT: \033[91m{content}\033[0m")
		# Award 0.1 marks for rejected comments
		emoji_counts[name] += 1
		if emoji_counts[name] < emoji_limit:
			name_counts[name] += 0.1
		return

	name_counts[name] = name_counts.get(name, 0) + 1
	content_squash = re.sub("[^a-z]+", "", content)

	if not content_dict.get(content_squash, False):
		print(content)
		content_dict[content_squash] = True


# =======================
def print_results(name_counts: dict, name_list: set, max_num: int) -> None:
	"""
	Prints the results of the processed data.

	Args:
	        name_counts (dict): Dictionary storing the counts of valid and rejected entries for each name.
	        name_list (set): Set of names encountered in the input.
	        max_num (int): Maximum number of marks allowed for each name.
	"""
	print("=======================================")
	keys = sorted(name_list)
	print_count = 0

	for name in keys:
		count = min(name_counts.get(name, 0), max_num)
		# Change color if the count reaches max_num
		if count <= 0:
			print("\u2014")
		else:
			print(f"{count:.1f}")

	print("\n\n\n")
	for name in keys:
		print_count += 1
		if print_count % 4 == 0:
			print("---\t---")

		count = min(name_counts.get(name, 0), max_num)
		# Change color if the count reaches max_num
		if count >= max_num:
			print(f"\033[92m{count:.1f}\t{name}\033[0m")
		# Change color to red if the count is zero
		elif count <= 0:
			print(f"\033[91mnil\t{name}\033[0m")
		# Regular color for other counts
		else:
			print(f"{count:.1f}\t{name}")

	print("=======================================")


# =======================
def load_student_roster(roster_file: str) -> tuple[dict, set, roster_matching.RosterMatcher]:
	"""
	Load student roster and create a shared matcher.

	Returns:
		tuple: (roster_by_id, roster_names_set, matcher)
	"""
	roster_by_id = roster_matching.load_roster(roster_file)
	roster_names = set()
	for info in roster_by_id.values():
		if info.get("full_name", ""):
			roster_names.add(info["full_name"])

	matcher = roster_matching.RosterMatcher(
		roster=roster_by_id,
		interactive=True,
		auto_threshold=0.90,
		auto_gap=0.06,
		candidate_count=5,
	)
	return roster_by_id, roster_names, matcher


# =======================
if __name__ == "__main__":
	parser = argparse.ArgumentParser()
	parser.add_argument("-f", "--file", type=str, dest="filename", help="Filename", default=None)
	parser.add_argument("-x", "--max", type=int, dest="max_marks", help="Maximum discussion marks", default=6)
	parser.add_argument(
		"-r",
		"--roster",
		type=str,
		dest="roster_file",
		help="Student roster CSV file",
		required=True,
		)
	args = parser.parse_args()

	name_list = set()
	filename = args.filename

	# File validation
	if filename is None or not os.path.isfile(filename):
		parser.print_help()
		sys.exit(1)

	emoji_counts = defaultdict(int)
	name_counts = defaultdict(float)
	content_dict = {}

	# Load the student roster
	roster_by_id, roster_names, matcher = load_student_roster(args.roster_file)
	unmatched_zoom_names = set()

	# Read and preprocess lines
	with open(filename, "r") as fpointer:
		lines = fpointer.readlines()
		combined_lines = preprocess_lines(lines)

	# Process each combined line, passing the student roster
	for line in combined_lines:
		process_line(
			line,
			name_counts,
			emoji_counts,
			content_dict,
			name_list,
			roster_by_id,
			matcher,
			unmatched_zoom_names,
		)

	# =======================
	# Compare name_list and student_roster.keys()

	# Find names that were not matched to the roster
	extra_students = unmatched_zoom_names

	# Find names that are in the roster but did not participate in the Zoom chat
	missing_students = roster_names - name_list

	# Print the names of students who are not in the roster
	if extra_students:
		print("\nExtra students (not found in the roster):")
		for student in sorted(extra_students):
			print(f" - {student}")
		sys.exit(1)
	else:
		print("\nNo extra students found in the Zoom chat.")

	# Print the count and names of students who did not participate
	if missing_students:
		print(f"\n{len(missing_students)} students from the roster did not participate in the discussion:")
		for student in sorted(missing_students):
			print(f" - {student}")
	else:
		print("\nAll students from the roster participated in the discussion.")

	# Merge the name_list (students from chat) with the student_roster keys (all students in the roster)
	name_list.update(roster_names)

	# =======================
	# Print the results
	print_results(name_counts, name_list, args.max_marks)

	print(f"\nProcessed file: {filename}")
