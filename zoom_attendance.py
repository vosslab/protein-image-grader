#!/usr/bin/env python3

import re
import csv
import math
import difflib
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

from rich.console import Console
from rich.style import Style
from rich.text import Text

# TODO
# add force option, so you do not have to say yes each time
# output a score for each student, including those missing
# sort by first name in output

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

#==============================================================================
#==============================================================================
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
				'full name': full_name,
				}

			# Also map by "First Last" and "Last First" for potential Zoom names
			expanded_student_roster[full_name] = student_roster[full_name]
			expanded_student_roster[flipped_full_name] = student_roster[full_name]
			expanded_student_roster[first_name] = student_roster[full_name]
			expanded_student_roster[alias] = student_roster[full_name]
			expanded_student_roster[username] = student_roster[full_name]

	# Return the roster dictionary
	return student_roster, expanded_student_roster

#==============================================================================
#==============================================================================
def determine_meeting_start_time(participants):
	all_join_times = [session[3] for sessions in participants.values() for session in sessions]
	earliest_join_time = min(all_join_times)
	# round up to the next hour
	rounded_time = (earliest_join_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
	print(f"Official Start Time: {rounded_time}")
	return rounded_time

#==============================================================================
#==============================================================================
def categorize_participants(participants, meeting_start_time, student_roster):
	"""
	Categorizes students based on their join times relative to the meeting start and ensures all students
	are included in the output, even those who did not participate.

	Args:
		participants (dict): Attendance data for students who joined.
		meeting_start_time (datetime): The official meeting start time.
		student_roster (dict): The full student roster.

	Returns:
		list: Processed student attendance records.
		list: Bulk leave times for determining the session end time.
	"""
	processed_student_tree = []
	bulk_leave_times = []
	# Ensure every student in the roster is processed
	for student_name in student_roster.keys():
		if student_name in participants:
			# If the student has participant data, process their attendance
			sessions = participants[student_name]
			first_join_time = min(session[3] for session in sessions)
			email = max(session[2] for session in sessions)
			time_from_start = round((first_join_time - meeting_start_time).total_seconds() / 60, 1)
			if time_from_start <= 0:
				arrival_status = "On-Time"
				time_from_start = 0
			elif time_from_start <= 2:
				arrival_status = "First 2 Minutes"
			elif time_from_start <= 10:
				arrival_status = "First 10 Minutes"
			else:
				arrival_status = "Late"
			last_leave_time = max(session[4] for session in sessions)
			bulk_leave_times.append(last_leave_time)
			total_time_attended = last_leave_time - max(meeting_start_time, first_join_time)
			total_minutes_attended = int(total_time_attended.total_seconds() / 60)
			student_dict = {
				"Name": student_name,
				"Email": email,
				"Arrival Status": arrival_status,
				"Minutes From Start": time_from_start,
				"First Join Time": first_join_time.strftime("%I:%M:%S %p"),
				"Last Leave Time": last_leave_time.strftime("%I:%M:%S %p"),
				"Total Minutes Attended": total_minutes_attended,
			}
		else:
			# If the student has no participant data, fill only the name and leave other fields blank
			student_dict = {
				"Name": student_name,
				"Email": "",
				"Arrival Status": "",
				"Minutes From Start": "",
				"First Join Time": "",
				"Last Leave Time": "",
				"Total Minutes Attended": "",
			}
		processed_student_tree.append(student_dict)
	return processed_student_tree, bulk_leave_times


#==============================================================================
#==============================================================================
def mark_stayed_until_end(processed_student_tree, bulk_leave_times, meeting_start_time):
	"""
	Marks whether each student stayed until the end of the session and calculates total time attended.

	Args:
		processed_student_tree (list): List of student attendance records.
		bulk_leave_times (list): List of all leave times from the attendance data.
		meeting_start_time (datetime): The official meeting start time.

	Returns:
		None: Updates the processed_student_tree in place.
	"""
	if not bulk_leave_times:  # If no students attended, prevent index error
		return

	bulk_leave_times.sort()
	majority_leave_time = bulk_leave_times[len(bulk_leave_times) // 2]  # Median leave time
	buffered_end_time = majority_leave_time - timedelta(minutes=5)  # Subtract 5 minutes buffer
	total_class_minutes = (buffered_end_time - meeting_start_time).total_seconds() / 60
	print(f"Official End Time: {buffered_end_time}")

	for record in processed_student_tree:
		# Skip students who did not attend
		if not record["Last Leave Time"]:  # If blank, set default values and continue
			record["Stayed Until End"] = ""
			record["Percent Class Attended"] = ""
			continue  # Skip further processing

		# Convert string times back to datetime objects for calculations
		last_leave_time = datetime.strptime(record["Last Leave Time"], "%I:%M:%S %p")

		# Standardize the date to 1900-01-01 for comparison
		last_leave_time = last_leave_time.replace(year=1900, month=1, day=1)
		buffered_end_time_standardized = buffered_end_time.replace(year=1900, month=1, day=1)

		# Check if the student stayed until the adjusted buffer time
		stayed_until_end = last_leave_time >= buffered_end_time_standardized
		record["Stayed Until End"] = "Yes" if stayed_until_end else "No"

		# Compute attendance percentage
		total_minutes_attended = record["Total Minutes Attended"]
		percent_class_attended = int(100 * total_minutes_attended / total_class_minutes)
		record["Percent Class Attended"] = min(100, percent_class_attended)  # Cap at 100%

#==============================================================================
#==============================================================================
def score_attendance(processed_student_tree):
	"""
	Scores attendance based on on-time arrival, staying until the end, and total attendance.

	Args:
		processed_student_tree (list): List of student attendance records.

	Returns:
		None: Updates records in place with scores.
	"""
	for record in processed_student_tree:
		# If the student has no attendance data, mark final score as '-'
		if record["Minutes From Start"] == "":
			record["On-Time Score"] = ""
			record["Stayed Score"] = ""
			record["Percent Class Attended"] = ""
			record["Final Score"] = "-"  # Assign hyphen for missing students
			continue

		# Convert minutes_from_start to an integer if necessary
		minutes_from_start = record["Minutes From Start"]
		if isinstance(minutes_from_start, str):
			minutes_from_start = 999  # Default for safety, but this should not be needed now

		# Score for on-time arrival
		if minutes_from_start < 1:
			ontime_score = 2
		elif minutes_from_start < 10:
			ontime_score = round(2 * (9 - (minutes_from_start - 1)) / 10.0, 1)
		else:
			ontime_score = 0
		record["On-Time Score"] = ontime_score

		# Score for staying until the end
		stayed_score = 1 if record["Stayed Until End"] == "Yes" else 0
		record["Stayed Score"] = stayed_score

		# Calculate final attendance score
		fraction_attend = record["Percent Class Attended"] / 100.0
		final_score = (ontime_score + stayed_score) * math.sqrt(fraction_attend)
		record["Final Score"] = round(final_score, 1)

#==============================================================================
#==============================================================================
def write_output(processed_data, output_file):
	with open(output_file, mode='w', newline='') as outfile:
		fieldnames = ["Name", "Email",
				"First Join Time", "Minutes From Start", "Arrival Status", "On-Time Score",
				"Last Leave Time", "Stayed Until End", "Stayed Score",
				"Total Minutes Attended", "Percent Class Attended",
				'Final Score',]
		writer = csv.DictWriter(outfile, fieldnames=fieldnames)
		writer.writeheader()
		writer.writerows(processed_data)

#==============================================================================
#==============================================================================
def normalize_name_text(name_text: str) -> str:
	name_text = name_text.strip()
	name_text = name_text.lower()
	name_text = re.sub(r"\s*iphone\s*", "", name_text)
	name_text = re.sub(r"[^A-Za-z0-9\- ]", "", name_text)
	return name_text

#==============================================================================
#==============================================================================
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
	print(f"Closest match found:\nfound: {matched_name}\n zoom: {normalized_key}")
	validation = get_input_validation("    Is this a good match? (y/n)", "yn")

	if validation == "n":
		print("Please edit the CSV file and try again.")
		raise ValueError

	# Cache the approved match in student_roster for future use
	student_roster[normalized_key] = student_roster[matched_name]

	return matched_name


# =======================
def get_input_validation(message: str, valid_letters: str, style: Style = validation_color) -> str:
	"""
	Get user input for image validation and ensure it's valid.
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


#==============================================================================
#==============================================================================
def process_zoom_attendance(input_file, expanded_student_roster):
	participants = defaultdict(list)

	# Open the file with utf-8-sig to handle BOM
	with open(input_file, mode='r', encoding='utf-8-sig') as infile:
		reader = csv.DictReader(infile)

		# Debugging: Print headers to verify correct parsing
		print("Headers in file:", reader.fieldnames)

		row_count = 0
		for row in reader:
			row_count += 1
			zoom_name = row['Name (original name)']
			normalized_name = normalize_name_text(zoom_name)
			if normalized_name.startswith("neil voss"):
				continue
			# Try to match by Zoom username or full name
			if normalized_name in expanded_student_roster:
				student_dict = expanded_student_roster[normalized_name]
			else:
				# If no exact match, try to find the closest match using find_closest_match
				matched_name = find_closest_match(normalized_name, expanded_student_roster)
				if not matched_name:
					continue
				student_dict = expanded_student_roster[matched_name]
			student_name = student_dict['full name']

			email = row['Email'].strip() if row['Email'] else "No Email"
			join_time = datetime.strptime(row['Join time'].strip(), "%Y-%m-%d %I:%M:%S %p")
			leave_time = datetime.strptime(row['Leave time'].strip(), "%Y-%m-%d %I:%M:%S %p")
			duration = int(row['Duration (minutes)'].strip())

			print(student_name)
			data_tuple = tuple((student_name, normalized_name, email, join_time, leave_time, duration))

			participants[student_name].append(data_tuple)

	print(f"Processed {row_count} rows and found {len(participants)} students")
	return participants


#==============================================================================
#==============================================================================
def parse_arguments():
	parser = argparse.ArgumentParser(description="Process Zoom attendance logs.")
	parser.add_argument("-i", "--input",
		type=str,
		dest="input_file",
		help="Path to the input CSV file containing Zoom attendance logs.",
		required=True,
		)
	parser.add_argument("-o", "--output",
		type=str,
		dest="output_file",
		help="Path to the output file where processed data will be saved.",
		default="attendance-output.csv"
		)
	parser.add_argument( "-r", "--roster",
		type=str,
		dest="roster_file",
		help="Student roster CSV file",
		required=True,
		)
	return parser.parse_args()

#==============================================================================
def print_final_scores(processed_student_tree):
	"""
	Prints the final scores sorted by student name, without printing names.
	Missing students will have a hyphen ('-') instead of a numerical score.

	Args:
		processed_student_tree (list): List of student attendance records.
	"""
	# Sort records by Name (alphabetically)
	sorted_records = sorted(processed_student_tree, key=lambda x: x["Name"])

	# Print only the final scores (excluding names)
	for record in sorted_records:
		print(record["Final Score"])  # Outputs only the score (or '-')

#==============================================================================
#==============================================================================
def print_final_scores(processed_student_tree):
	"""
	Prints the final scores sorted by student name, without printing names.
	Missing students will have a hyphen ('-') instead of a numerical score.

	Args:
		processed_student_tree (list): List of student attendance records.
	"""
	# Sort records by Name (alphabetically)
	sorted_records = sorted(processed_student_tree, key=lambda x: x["Name"])

	# Print only the final scores (excluding names)
	for record in sorted_records:
		print(record["Final Score"])  # Outputs only the score (or '-')


#==============================================================================
#==============================================================================
#==============================================================================
#==============================================================================
def main():
	"""
	Main function to orchestrate the processing of Zoom attendance logs.
	Steps:
	1. Parse command-line arguments for input/output file paths and roster file.
	2. Load the student roster into a dictionary.
	3. Process the Zoom attendance file to extract participant data.
	4. Determine the meeting's start time by rounding the earliest join time to the next hour.
	5. Categorize participants based on their join times relative to the meeting start.
	6. Mark whether each participant stayed until the end of the session.
	7. Write the processed data to the output file.
	8. Display the output file location.
	"""
	args = parse_arguments()
	# Load the student roster
	student_roster, expanded_student_roster = load_student_roster(args.roster_file)

	# Process attendance data
	participants = process_zoom_attendance(args.input_file, expanded_student_roster)
	print("\n\n")

	meeting_start_time = determine_meeting_start_time(participants)
	processed_student_tree, bulk_leave_times = categorize_participants(participants, meeting_start_time, student_roster)

	# Mark end-of-session attendance and calculate total time
	mark_stayed_until_end(processed_student_tree, bulk_leave_times, meeting_start_time)

	score_attendance(processed_student_tree)

	print_final_scores(processed_student_tree)

	# Write the processed data to the output file
	write_output(processed_student_tree, args.output_file)

	# Notify the user
	print(f"Output written to: {args.output_file}")

#==============================================================================
#==============================================================================
if __name__ == "__main__":
	main()
