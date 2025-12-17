#!/usr/bin/env python3

import re
import csv
import math
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

from tool_scripts import roster_matching

# TODO
# add force option, so you do not have to say yes each time
# output a score for each student, including those missing
# sort by first name in output

#==============================================================================
#==============================================================================
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
def categorize_participants(participants, meeting_start_time, roster_names):
	"""
	Categorizes students based on their join times relative to the meeting start and ensures all students
	are included in the output, even those who did not participate.

	Args:
		participants (dict): Attendance data for students who joined.
		meeting_start_time (datetime): The official meeting start time.
		roster_names (set): The full set of student names from the roster.

	Returns:
		list: Processed student attendance records.
		list: Bulk leave times for determining the session end time.
	"""
	processed_student_tree = []
	bulk_leave_times = []
	# Ensure every student in the roster is processed
	for student_name in sorted(roster_names):
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
#==============================================================================
#==============================================================================
def process_zoom_attendance(input_file, roster_by_id, matcher):
	participants = defaultdict(list)

	# Open the file with utf-8-sig to handle BOM
	with open(input_file, mode='r', encoding='utf-8-sig') as infile:
		reader = csv.DictReader(infile)

		# Debugging: Print headers to verify correct parsing
		print("Headers in file:", reader.fieldnames)

		row_count = 0
		for row in reader:
			row_count += 1
			zoom_name = row['Name (original name)'].strip()
			normalized_name = roster_matching.normalize_name_text(zoom_name)
			if normalized_name.startswith("neil voss"):
				continue
			email = (row.get('Email', '') or '').strip()
			student_id, _reason, _score = matcher.match(
				username=email,
				first_name=zoom_name,
				last_name="",
				student_id="",
			)
			if student_id is None:
				continue
			student_dict = roster_by_id.get(student_id, {})
			student_name = student_dict.get('full_name', '')
			if not student_name:
				continue

			email = email if email else "No Email"
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
	roster_by_id, roster_names, matcher = load_student_roster(args.roster_file)

	# Process attendance data
	participants = process_zoom_attendance(args.input_file, roster_by_id, matcher)
	print("\n\n")

	meeting_start_time = determine_meeting_start_time(participants)
	processed_student_tree, bulk_leave_times = categorize_participants(participants, meeting_start_time, roster_names)

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
