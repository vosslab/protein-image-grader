#!/usr/bin/env python3

import os
import re
import csv
import sys
import time
import difflib
import argparse

from collections import defaultdict

from rich.console import Console
from rich.style import Style
from rich.text import Text
import unicodedata
import unidecode

console = Console()
validation_color = Style(color="rgb(153, 230, 76)")  # RGB for lime-ish green

validation_types = {
	"a": "almost",
	"b": "bonus",
	"f": "finished",
	"n": "no",
	"p": "previous",
	"s": "save",
	"y": "yes",
	}

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
def normalize_name_text(name_text: str) -> str:
	name_text = re.sub(r":", "", name_text)
	name_text = name_text.strip()
	name_text = name_text.lower()
	name_text = unicodedata.normalize('NFKC', name_text)
	name_text = unidecode.unidecode(name_text)
	name_text = re.sub(r"\(.*\)", "", name_text).strip()
	name_text = re.sub(r"\'s($|\s)", r"\1", name_text).strip()
	name_text = re.sub(r"\s*(iphone|ipad)\s*", "", name_text)
	name_text = re.sub(r"[^A-Za-z0-9\- ]", "", name_text)
	name_text = name_text.strip()
	return name_text

# =======================
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
		expanded_student_roster: dict,
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

	zoom_name = bits[1].strip().lower()
	# skip the instructor name
	if zoom_name.startswith("neil voss"):
		return
	zoom_name = re.sub(r"\s*iphone\s*", "", zoom_name)

	# Try to match by Zoom username or full name
	if zoom_name in expanded_student_roster:
		student = expanded_student_roster[zoom_name]
	else:
		# If no exact match, try to find the closest match using find_closest_match
		matched_name = find_closest_match(zoom_name, expanded_student_roster)
		if not matched_name:
			return
		student = expanded_student_roster[matched_name]

	# Extract student details
	first_name = student["first_name"]
	last_name = student["last_name"]
	student_id = student["student_id"]

	name = f"{first_name} {last_name}".lower()
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
def find_closest_match(zoom_name: str, student_roster: dict) -> str:
	"""
	Find the closest matching key in the student_roster dictionary and cache it.
	"""
	normalized_key = normalize_name_text(zoom_name)

	# First, check if the normalized key is already in the student_roster (cached match)
	if normalized_key in student_roster:
		return normalized_key  # Return the cached match

	# Try to find the best match with a high cutoff value
	best_match = difflib.get_close_matches(
		normalized_key,
		student_roster.keys(),  # Using student_roster for matching
		n=1,
		cutoff=0.9,  # High confidence cutoff
		)

	# If no match is found, lower the cutoff value and try again
	if not best_match:
		print(f"No automatic match for {normalized_key}")
		best_match = difflib.get_close_matches(
			normalized_key,
			student_roster.keys(),  # Using student_roster for matching
			n=1,
			cutoff=0.4,  # Lower confidence cutoff
			)

		# If still no match, exit the program
		if not best_match:
			print(f"{normalized_key} NOT FOUND")
			print("No matches found at all.")
			return None

	# At this point, we have a best match but might need user confirmation
	matched_name = best_match[0]
	print(f"Closest match found:\nmatch: {matched_name}\ninput: {normalized_key}")
	validation = get_input_validation("    Is this a good match? (y/n)", "yn")

	if validation == "n":
		print("Please edit the CSV file and try again.")
		raise ValueError

	# Cache the approved match in student_roster for future use
	student_roster[normalized_key] = student_roster[matched_name]

	return matched_name


# =======================
def detect_delimiter(sample_line: str) -> str:
	"""
	Detects the most likely delimiter (comma or tab) from a sample line.

	Args:
	        sample_line (str): A line from the CSV file.

	Returns:
	        str: The detected delimiter (either ',' or '\t').
	"""
	# Count occurrences of common delimiters
	if sample_line.count("\t") > sample_line.count(","):
		return "\t"
	else:
		return ","


# =======================
def get_input_validation(message: str, valid_letters: str, style: Style = validation_color) -> str:
	"""
	Get user input for image validation and ensure it's valid.

	Parameters
	----------
	message : str
	        The custom message that will be displayed to the user when asking for input.
	valid_letters : str
	        The string containing all valid input letters.
	style : Style
	        The Rich style to apply to the message.

	Returns
	-------
	str
	        The validated user input.
	"""
	valid_tuple = tuple(valid_letters)
	statement = Text(message.strip(), style=style)

	options_text = "-- "
	for letter in valid_letters:
		word = validation_types[letter]
		word = word.replace(letter, "(" + letter + ")")
		options_text += word + "/"
	options_text = options_text[:-1] + ": "

	while True:
		# Use Rich to print the styled part of the statement
		console.print(statement)

		# Get the user's input
		validation = input(options_text)

		# Check if the entered input is in the list of valid inputs
		if validation.lower() in valid_tuple:
			return validation.lower()

		# Use Rich to print an error message if the entry is invalid
		console.print("ERROR ~ try again ~\n", style="red")


# =======================
def load_student_roster(roster_file: str) -> dict:
	"""
	Load student roster from a CSV file and return a dictionary mapping usernames and full names to student data.

	Args:
	        roster_file (str): Path to the roster CSV file.

	Returns:
	        dict: A dictionary mapping usernames and full names to student records.
	"""
	student_roster = {}
	expanded_student_roster = {}

	# Open the file and detect the delimiter from the first line
	with open(roster_file, "r") as csvfile:
		# Read the first line to detect the delimiter
		first_line = csvfile.readline()
		detected_delimiter = detect_delimiter(first_line)

		# Use the detected delimiter for the DictReader
		csvfile.seek(0)  # Reset file pointer to the beginning
		reader = csv.DictReader(csvfile, delimiter=detected_delimiter)

		for row in reader:
			# Extract the student data
			first_name = normalize_name_text(row["First Name"])
			last_name = normalize_name_text(row["Last Name"])
			username = normalize_name_text(row["Username"])
			student_id = int(row["Student ID"].strip())
			alias = normalize_name_text(row["Alias"])
			full_name = f"{first_name} {last_name}"
			flipped_full_name = f"{last_name} {first_name}"

			# Store the student data in a dictionary using Username as the key
			student_roster[full_name] = {
				"first_name": first_name,
				"last_name": last_name,
				"username": username,
				"student_id": student_id,
				"alias": alias,
				}

			# Also map by "First Last" and "Last First" for potential Zoom names
			expanded_student_roster[full_name] = student_roster[full_name]
			expanded_student_roster[flipped_full_name] = student_roster[full_name]
			expanded_student_roster[first_name] = student_roster[full_name]
			expanded_student_roster[alias] = student_roster[full_name]
			expanded_student_roster[username] = student_roster[full_name]

	# Return the roster dictionary
	return student_roster, expanded_student_roster


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
	student_roster, expanded_student_roster = load_student_roster(args.roster_file)

	# Read and preprocess lines
	with open(filename, "r") as fpointer:
		lines = fpointer.readlines()
		combined_lines = preprocess_lines(lines)

	# Process each combined line, passing the student roster
	for line in combined_lines:
		process_line(line, name_counts, emoji_counts, content_dict, name_list, expanded_student_roster)

	# =======================
	# Compare name_list and student_roster.keys()

	# Find names that are in the Zoom chat (name_list) but not in the roster
	extra_students = name_list - set(student_roster.keys())

	# Find names that are in the roster but did not participate in the Zoom chat
	missing_students = set(student_roster.keys()) - name_list

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
	name_list.update(student_roster.keys())

	# =======================
	# Print the results
	print_results(name_counts, name_list, args.max_marks)

	print(f"\nProcessed file: {filename}")
