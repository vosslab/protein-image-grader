#!/usr/bin/env python3

#length, then alphabetical ordering of import statements
import os
import sys
import glob
import time
import yaml
import fnmatch
import argparse
import traceback
from types import MappingProxyType

from rich.console import Console
from rich.style import Style
from rich.table import Table

import process_images
import file_io_protein
import timestamp_tools
import student_id_protein

console = Console()
warning_color = Style(color="rgb(255, 187, 51)" )  # RGB for bright orange
question_color = Style(color="rgb(100, 149, 237)" )  # RGB for cornflower blue
data_color = Style(color="rgb(187, 51, 255)" )  # RGB for purple


#==========================================
# Get List of Accepted Answers for a Given Question
#==========================================
def get_answers_list_for_question(question_dict: dict) -> list:
	"""
	Get the list of accepted answers for a given question based on the rules in question_dict.

	Parameters:
	-----------
	question_dict : dict
		A dictionary containing question details, including either 'answer' or 'answers'.

	Returns:
	--------
	list
		A list of accepted answers, either a single-element list for one answer or multi-element for multiple answers.

	Note:
	-----
	This function will exit the program if the YAML file is not formatted correctly.
	"""

	# Initialize the variable to hold the accepted answers
	accepted_answers = None

	# Fetch the single answer from the question_dict, if it exists
	single_answer = question_dict.get('answer', None)

	# Check for the existence of a single accepted answer
	if single_answer is not None:
		# Check if the single answer is mistakenly provided as a list
		if isinstance(single_answer, list):
			console.print("use 'answers' not 'answer' in the YAML file for multiple answers")
			sys.exit(1)
		# Create a list with the single accepted answer
		accepted_answers = [question_dict.get('answer', None)]
	else:
		# Fetch the list of accepted answers from the question_dict
		accepted_answers = question_dict.get('answers', [])
		# Validate if the accepted answers are in a list format
		if not isinstance(accepted_answers, list):
			console.print("use 'answer' not 'answers' in the YAML file for single answers")
			sys.exit(1)

	# Return the list of accepted answers
	return accepted_answers

#==========================================
# Get User Input on Student Response
#==========================================
def get_user_input(student_response: str, question_dict: dict) -> tuple:
	"""
	Get the user's input to determine if a student's response to a question is correct or incorrect,
	and any deductions that should apply.

	Parameters:
	-----------
	student_response : str
		The student's answer to the question.
	question_dict : dict
		A dictionary containing the attributes of the question, such as its type, point deductions, etc.

	Returns:
	--------
	tuple
		A tuple containing (deduction, validation_status, feedback).

	Note:
	-----
	The function recurses if the user enters an invalid validation response.
	"""

	# Initialize variable for feedback
	feedback = ''

	# Get the list of accepted answers for this question
	accepted_answers = get_answers_list_for_question(question_dict)
	if accepted_answers is not None:
		feedback = f"Best answer: {accepted_answers[0]}"

	# Handling integer-type questions
	if question_dict['type'] == 'int':
		# Get the point deduction for the given student response
		deduction = timestamp_tools.get_deduction(int(student_response), question_dict.get('numeric_deductions', {}))
		if deduction == 0:
			return deduction, "Correct", feedback
		else:
			return deduction, "Incorrect", feedback

	# Handling multiple-choice questions
	elif question_dict['type'] == 'mc' or question_dict['type'] == 'ma':
		deduction = -abs(float(question_dict['point_deduction']))
		feedback = feedback + '; ' + question_dict['feedback']
		return deduction, "Incorrect", feedback

	# Handling other types of questions
	else:
		if len(student_response) == 0:
			wrong_answers = question_dict.get('glob wrong responses', {})
			if wrong_answers.get('*') is not None:
				points_deducted = wrong_answers['*']['point_deduction']
				return -abs(float(points_deducted)), "Incorrect", feedback
		# Ask the user to validate the student response
		message = f"    is the answer '{student_response}' correct?"
		validation = student_id_protein.get_input_validation(message, 'yna')
		if validation == 'y': #yes
			return 0, "Correct", feedback
		elif validation == 'a': #almost
			return 0, "Minor", feedback
		elif validation == 'n': #no
			wrong_answers = question_dict.get('glob wrong responses', {})
			if wrong_answers.get('*') is not None:
				points_deducted = wrong_answers['*']['point_deduction']
			else:
				points_deducted = input("Enter points to be deducted: ")
			return -abs(float(points_deducted)), "Incorrect", feedback
		else:
			# Recur for invalid user input
			return get_user_input(student_response, question_dict)

#==========================================
def auto_grade_student_response(student_response: str, question_dict: dict) -> tuple:
	"""
	Automatically grade a student's answer, if possible.

	Parameters
	----------
	student_response : str
		The answer provided by the student.
	question_dict : typing.Dict[str, typing.Any]
		Dictionary containing the question details.

	Returns
	-------
	typing.Tuple[typing.Union[float, None], typing.Union[str, None], typing.Union[str, None]]
		A tuple containing the points deducted, the correctness of the answer, and feedback for the student.

	"""
	# Extract the list of accepted answers for the question from the dictionary
	accepted_answers = get_answers_list_for_question(question_dict)
	if accepted_answers is not None:
		feedback = f"Best answer: {accepted_answers[0]}"

	# Initialize dictionary of wrong answers
	wrong_answers = question_dict.get('glob wrong responses', {})

	# Check if the student's response is in the list of accepted answers
	is_accepted = student_response in accepted_answers

	# Special handling for multiple-choice questions
	if question_dict['type'] == 'mc':
		for accepted_answer in accepted_answers:
			if student_response.startswith(accepted_answer):
				is_accepted = True
	elif question_dict['type'] == 'ma':
		for accepted_answer in accepted_answers:
			if is_accepted is True:
				continue
			ascii_student_response = student_response.encode('ascii', 'ignore').decode()
			#print(ascii_student_response)
			selected_answers = accepted_answer.split(';')
			student_selections = ascii_student_response.split(';')
			#print(student_selections)
			if len(student_selections) != len(selected_answers):
				#student selected too many choices
				is_accepted = False
				continue
			matches = 0
			for answer in selected_answers:
				for selection in student_selections:
					if selection.startswith(answer):
						matches += 1
			if matches == len(selected_answers):
				is_accepted = True

	# If the answer is correct, return a zero point deduction
	if is_accepted:
		return 0.0, "Correct", feedback

	# Check if the answer is a predefined wrong answer
	auto_wrong_responses = question_dict.get('auto wrong responses', [])
	if student_response in auto_wrong_responses:
		deduction = wrong_answers['*'].get('point_deduction', 0)
		feedback = feedback + '; ' + wrong_answers['*'].get('feedback', feedback)
		return deduction, "Incorrect", feedback

	# Check if the answer is wrong based on glob patterns
	for glob_pattern in list(wrong_answers.keys()):
		if glob_pattern == '*':
			continue
		if fnmatch.fnmatch(student_response, glob_pattern):
			deduction = wrong_answers[glob_pattern].get('point_deduction', 0)
			feedback = feedback + '; ' + wrong_answers[glob_pattern].get('feedback', feedback)
			return deduction, "Incorrect", feedback

	# If no conditions are met, manual validation is required
	return None, None, None

#==========================================
def process_csv_question(student_tree: dict, question_dict: dict, accepted_answers: list) -> None:
	"""
	Process a single question for all student responses in the CSV.

	Parameters
	----------
	student_tree : dict
		A nested dictionary containing student data.
	question_dict : dict
		A dictionary representing the question attributes.
	accepted_answers : list
		List of accepted answers for the question.

	Returns
	-------
	None
		The function updates the student responses in-place within the 'student_tree'.
	"""
	# Group student responses by their answer for the given question
	grouped_responses = student_id_protein.group_student_responses(student_tree, question_dict)

	correct = 0
	total = 0
	q_name = question_dict['name']

	# Loop through the grouped student responses to process each one
	for student_response, entries in grouped_responses.items():
		# Initialize a flag to track if the student response group has already been graded
		response_is_graded = True
		# Loop through individual student entries in the current response group
		for student_entry in entries:
			# Fetch the pre-existing grading status for the question from the student's response
			pre_status = student_entry.get(f"{q_name} Status")
			# Check if the grading status exists; if not, mark the group as ungraded
			if pre_status is None:
				response_is_graded = False
				break  # Exit the loop to proceed to the next section
		# Skip this response group if it has already been graded
		if response_is_graded is True:
			continue

		# Automatically grade the student response using the auto_grade_student_response function
		deduction, status, feedback = auto_grade_student_response(student_response, question_dict)

		# If the auto-grader fails to determine a grade, fallback to manual grading input
		if deduction is None:
			deduction, status, feedback = get_user_input(student_response, question_dict)

		# Update the student entries with the grading status, point deduction, and feedback
		for student_entry in entries:
			total += 1
			if status == "Correct":
				correct += 1
			student_entry[f"{q_name} Status"] = status
			student_entry[f"{q_name} Deduction"] = deduction
			student_entry[f"{q_name} Feedback"] = feedback

	if total > 0:
		console.print(f"Summary of {q_name}:")
		percent = 100*correct/float(total)
		console.print(f"  {correct} of {total} correct, {percent:.1f}%")
		if percent < 70:
			console.print(f"  {correct} of {total} correct, {percent:.1f}%")
			time.sleep(3)

#==========================================
def get_final_score(student_entry: dict, read_only_config_dict: dict) -> None:
	"""
	Calculates and updates the final score for a student's entry based on the read_only_config_dict settings.

	Parameters
	----------
	student_entry : dict
		A dictionary containing student data, including potential keys ending with 'Status' and 'Deduction'.
	read_only_config_dict : dict
		Configuration dictionary containing 'total points' and 'assignment name'.

	Returns
	-------
	None
		Updates the student_entry dictionary in-place with the final score.
	"""

	# Retrieve the maximum score from the configuration
	maximum_score = float(read_only_config_dict['total points'])
	# Calculate the minimum score as 40% of the maximum score
	minimum_score = 0.4 * maximum_score
	# Initialize the student's score to the maximum score
	score = maximum_score

	# Iterate through the student's entries
	for key, value in student_entry.items():
		# Check if the entry is a bonus
		if key.endswith('Status') and value == "Bonus":
			score += 0.5
		# Check if the entry is a deduction
		if key.endswith('Deduction'):
			# Convert the deduction to a negative absolute value
			deduction = -abs(float(value))
			score += deduction

	# Update the score if it's less than minimum score
	if score < minimum_score and student_entry['Exact Match'] is False:
		score = minimum_score
	elif score < 0.1:
		score = 0.1

	# Format the score as a string with 2 decimal places
	score_str = f'{score:.2f}'

	# Update the student's entry with the final score
	student_entry["Final Score"] = score_str
	student_entry[read_only_config_dict['assignment name']] = score_str

# Simple assertion test for the function. Replace with actual data for real-world use.
# This assumes that the function correctly updates student_entry dictionary in-place.
test_entry = {}
test_config = {'total points': '100', 'assignment name': 'HW1'}
get_final_score(test_entry, test_config)
assert test_entry['Final Score'] == '100.00'


#==========================================
def process_data(student_tree: list, read_only_config_dict: dict) -> None:
	"""
	Processes student data and updates the student_tree based on the configuration settings.

	Parameters
	----------
	student_tree : list
		List of dictionaries, each containing data for a single student.
	read_only_config_dict : dict
		Configuration settings to guide the data processing.

	Returns
	-------
	None
		Updates the student_tree list in-place.
	"""
	console.print("\nPre-Processing Student Images", style=data_color)
	process_images.pre_process_student_images(student_tree)

	# Loop through each student entry and process timestamp due dates
	console.print("\nPre-Processing Turn In Date", style=data_color)
	for student_entry in student_tree:
		timestamp_tools.timestamp_due_date(student_entry, read_only_config_dict)

	# Temporary backup of the student_tree
	file_io_protein.backup_tree_to_yaml("temp_save.yml", student_tree)

	# Loop through questions in read_only_config_dict and process each CSV question
	console.print("\nProcess CSV Questions", style='green')
	for i, question_dict in enumerate(read_only_config_dict.get("csv_questions", [])):
		console.print(f"\n* Question {i+1}: {question_dict['name']}", style=question_color)

		# Get accepted answers for each question
		accepted_answers = get_answers_list_for_question(question_dict)
		if len(accepted_answers) > 0:
			console.print(f"best answer: {accepted_answers[0]}")

		# Process each student entry for the given CSV question
		process_csv_question(student_tree, question_dict, accepted_answers)

	# Another temporary backup
	file_io_protein.backup_tree_to_yaml("temp_save.yml", student_tree)

	# Loop through each student entry and process image questions
	console.print("\nProcess Image Questions", style='green')
	proc_img = process_images.process_image_questions_class(student_tree, read_only_config_dict)
	proc_img.process_all_student_images()

	# Another temporary backup
	file_io_protein.backup_tree_to_yaml("temp_save.yml", student_tree)

	# Calculate the final score for each student entry
	console.print("\nCalculating Final Scores")
	for student_entry in student_tree:
		get_final_score(student_entry, read_only_config_dict)
	console.print('DONE Processing Data\n\n')


#==========================================
#==========================================
#==========================================
def main() -> None:
	"""
	Main function to drive the script for processing student answers based on a YAML config.
	"""

	# Argument Parsing: Initialize the parser and add arguments
	parser = argparse.ArgumentParser(description="Process student answers from a CSV based on a given YAML config.")
	parser.add_argument("-i", dest="image_number", type=int, help="Protein Image Number", required=True)
	parser.add_argument("-y", dest="yaml_backup_file", type=str, help="Load backup data file", default=None)

	# Parse the arguments into a Namespace object
	args = parser.parse_args()



	# Extract image number and construct file names based on it
	image_number = args.image_number
	folder = f"IMAGE_{image_number:02d}"
	#print(folder)
	if not os.path.isdir(folder):
		os.mkdir(folder)

	config_yaml = f"YAML_files/protein_image_{image_number:02d}.yml"
	#print(config_yaml)
	input_csv_glob = glob.glob(f"{folder}/BCHM_Prot_Img_{image_number:02d}-*.csv")
	#print(input_csv_glob)
	input_csv = input_csv_glob.pop()
	output_csv = f"{folder}/output-protein_image_{image_number:02d}.csv"
	output_yml = f"{folder}/output-protein_image_{image_number:02d}.yml"
	grades_csv = f"{folder}/blackboard_upload-protein_image_{image_number:02d}.csv"
	student_ids_csv = "current_students.csv"

	# Directly print the variables
	console = Console()
	table = Table(show_header=True, header_style="bold magenta")

	# Add columns
	table.add_column("Name", style="dim", width=20)
	table.add_column("Value", justify="left", style=data_color)

	# Add rows
	table.add_row("Image Number", str(image_number))
	table.add_row("Config YAML", config_yaml)
	table.add_row("Input CSV", input_csv)
	table.add_row("Output CSV", output_csv)
	table.add_row("Output YML", output_yml)
	table.add_row("Grades CSV", grades_csv)
	table.add_row("Student IDs CSV", student_ids_csv)

	# Print the table
	console.print(table)
	time.sleep(1)

	# Load YAML config: Open and read YAML file
	with open(config_yaml, 'r') as f:
		config = yaml.safe_load(f)
		read_only_config_dict = MappingProxyType(config)

	# Validate if the image numbers in the YAML file and arguments match
	if read_only_config_dict['image number'] != image_number:
		console.print(f"image numbers do not match, check YAML file {read_only_config_dict['image number']} != {image_number}")
		sys.exit(1)

	# Validate keys in read_only_config_dict trees
	student_id_protein.validate_dict_keys_in_tree(read_only_config_dict['image_questions'], ('name', 'point_deduction', 'feedback', 'type'))
	student_id_protein.validate_dict_keys_in_tree(read_only_config_dict['csv_questions'], ('name', 'csv_column', 'type'))
	console.print(f"{read_only_config_dict['assignment name']} worth {read_only_config_dict['total points']} points")

	# make sure columns are not used twice
	used_csv_columns = {}
	for question_dict in read_only_config_dict['csv_questions']:
		csv_column = question_dict['csv_column']
		if used_csv_columns.get(csv_column, None) is not None:
			console.print(f"CSV Column {csv_column} used for more than one question!")
			console.print(used_csv_columns[csv_column])
			console.print(question_dict['name'])
			sys.exit(1)
		used_csv_columns[csv_column] = question_dict['name']

	# Read student data from CSV files and load into trees
	if args.yaml_backup_file is not None:
		with open(args.yaml_backup_file, 'r') as f:
			student_tree = yaml.safe_load(f)
	else:
		student_tree = file_io_protein.read_student_csv_data(input_csv, read_only_config_dict)
	# quick check
	timestamp_tools.check_due_date(student_tree[-1]['timestamp'], read_only_config_dict)

	student_ids_tree = file_io_protein.read_student_ids(student_ids_csv)
	student_id_protein.match_lists_and_add_student_ids(student_ids_tree, student_tree)

	# Process data: Perform the main data processing steps
	try:
		process_data(student_tree, read_only_config_dict)
	except Exception as e:
		# In case of an exception, backup the data to a crash file
		file_io_protein.write_output_file("crash_data.csv", student_tree)
		file_io_protein.backup_tree_to_yaml("crash_data.yml", student_tree)

		# Print the full traceback
		traceback.print_exc()

		# Print the error message
		console.print(f"Error processing: {e}")

		# Exit the script
		sys.exit(1)

	# Write processed data to output files
	file_io_protein.write_output_file(output_csv, student_tree)
	file_io_protein.backup_tree_to_yaml(output_yml, student_tree)
	file_io_protein.write_student_grades_for_upload(read_only_config_dict['assignment name'], grades_csv, student_tree)

# Run the main function if the script is executed
if __name__ == "__main__":
	main()


