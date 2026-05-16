# Standard Library
import os
import glob
import time
import shutil
import fnmatch
import argparse
import datetime
from types import MappingProxyType

# PIP3 modules
import yaml
import rich.table
import rich.style
import rich.console

# local repo modules
import protein_image_grader.grade_status as grade_status
import protein_image_grader.ruid_resolver as ruid_resolver
import protein_image_grader.roster_matching as roster_matching
import protein_image_grader.duplicate_processing as duplicate_processing
import protein_image_grader.file_io_protein as file_io_protein
import protein_image_grader.interactive_image_criteria_class as interactive_image_criteria_class
import protein_image_grader.read_save_images as read_save_images
import protein_image_grader.student_id_protein as student_id_protein
import protein_image_grader.timestamp_tools as timestamp_tools
import protein_image_grader.download_submission_images as download_submission_images
import protein_image_grader.protein_images_path as protein_images_path

console = rich.console.Console()
warning_color = rich.style.Style(color="rgb(255, 187, 51)" )  # RGB for bright orange
question_color = rich.style.Style(color="rgb(100, 149, 237)" )  # RGB for cornflower blue
data_color = rich.style.Style(color="rgb(187, 51, 255)" )  # RGB for purple

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
			raise ValueError("use 'answers' not 'answer' in the YAML file for multiple answers")
		# Create a list with the single accepted answer
		accepted_answers = [question_dict.get('answer', None)]
	else:
		# Fetch the list of accepted answers from the question_dict
		accepted_answers = question_dict.get('answers', [])
		# Validate if the accepted answers are in a list format
		if not isinstance(accepted_answers, list):
			raise ValueError("use 'answer' not 'answers' in the YAML file for single answers")

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
	question_dict : dict
		Dictionary containing the question details.

	Returns
	-------
	tuple of (float or None, str or None, str or None)
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


#==========================================
#==========================================
#==========================================
def parse_args() -> argparse.Namespace:
	# Argument Parsing: Initialize the parser and add arguments
	parser = argparse.ArgumentParser(
		description="Process student answers from a CSV based on a given YAML config.")
	parser.add_argument("-i", dest="image_number", type=int,
		help="Protein Image Number", required=True)
	parser.add_argument('--make-html', dest='make_html',
		help='Generate HTML for visual grading', action='store_true')
	parser.add_argument('--no-make-html', dest='make_html',
		help='Skip HTML generation', action='store_false')
	parser.set_defaults(make_html=True)
	parser.add_argument("-s", "--spec-dir", dest="spec_dir", type=str,
		help="Assignment spec YAML directory", default="spec_yaml_files")
	parser.add_argument("-t", "--term", dest="term", type=str, default=None,
		help=(
			"Active term override (e.g., spring_2026). "
			"Defaults to Protein_Images/active_term.txt."
		))
	parser.add_argument("-y", "--yaml-backup-file", dest="yaml_backup_file", type=str,
		help="Resume from a checkpoint YAML written by an earlier grade run.",
		default=None)
	# Parse the arguments into a Namespace object
	args = parser.parse_args()
	return args

#============================================
def seed_or_reseed_spec_yaml(template_yaml: str, config_yaml: str) -> str:
	"""
	Ensure the per-image spec YAML exists and is up to date.

	Args:
		template_yaml: Path to the canonical template under spec_yaml_files/.
		config_yaml: Destination path inside the per-image folder.

	Returns:
		One of "seeded" (first-time copy), "reseeded" (template newer
		than dst, dst overwritten), or "kept" (no action). The string
		is also printed via the module console.

	Raises:
		ValueError: when neither the destination nor the template exist.
	"""
	if not os.path.isfile(config_yaml):
		# First-time seed: no per-image copy exists yet for this term.
		if not os.path.isfile(template_yaml):
			raise ValueError(
				f"Spec YAML not found in per-image folder ({config_yaml}) "
				f"or spec_dir template ({template_yaml})."
			)
		shutil.copy2(template_yaml, config_yaml)
		console.print(
			f"[green]seeded[/green] {os.path.relpath(config_yaml)} "
			f"from {os.path.relpath(template_yaml)}"
		)
		return "seeded"
	if os.path.isfile(template_yaml) and (
		os.path.getmtime(template_yaml) > os.path.getmtime(config_yaml)
	):
		# Template is newer: reseed so schema fixes propagate without manual rm.
		# Operator-edited per-image copies are overwritten only when the template
		# has been touched after that copy was last written.
		shutil.copy2(template_yaml, config_yaml)
		console.print(
			f"[yellow]reseeded[/yellow] {os.path.relpath(config_yaml)} "
			f"from {os.path.relpath(template_yaml)}"
		)
		return "reseeded"
	return "kept"


#============================================
def parse_and_prepare() -> dict:
	"""
	Parse command-line arguments and prepare file paths.

	Returns:
		dict: Dictionary containing file paths and configuration values.
	"""
	args = parse_args()
	image_number = args.image_number
	spec_dir = args.spec_dir
	if not os.path.isdir(spec_dir):
		raise ValueError(f"Spec directory not found: {spec_dir}")

	# Resolve canonical term-scoped paths via the helper.
	term = protein_images_path.get_active_term(args.term)
	forms_dir = protein_images_path.get_forms_dir(term)
	roster_csv = str(protein_images_path.get_roster_csv(term))
	image_dir = protein_images_path.get_term_image_dir(term, image_number)
	image_raw_dir = image_dir / "raw"
	if not image_raw_dir.is_dir():
		image_raw_dir.mkdir(parents=True, exist_ok=True)

	# Construct file paths
	config_yaml = str(protein_images_path.get_image_spec_yaml(term, image_number))
	# Seed the per-image folder with the canonical spec YAML on first grade.
	# spec_yaml_files/protein_image_NN.yml is the template; the per-image folder
	# gets its own copy so tweaks per semester do not edit the template in place.
	# When the template is newer than the seeded copy, reseed so schema fixes
	# (such as the meta-columns refactor) propagate without manual rm.
	template_yaml = os.path.join(spec_dir, f"protein_image_{image_number:02d}.yml")
	seed_or_reseed_spec_yaml(template_yaml, config_yaml)
	csv_pattern = f"BCHM_Prot_Img_{image_number:02d}-*.csv"
	# Look in canonical forms/ folder for this term.
	candidates = sorted(glob.glob(os.path.join(str(forms_dir), csv_pattern)))
	if len(candidates) < 1:
		raise ValueError(
			f"Input CSV not found in {forms_dir} matching {csv_pattern}"
		)
	if len(candidates) > 1:
		raise ValueError(f"Multiple input CSV files found: {candidates}")
	input_csv = candidates[0]

	output_csv = str(image_dir / f"output-protein_image_{image_number:02d}.csv")
	output_yml = str(image_dir / f"output-protein_image_{image_number:02d}.yml")
	grades_csv = str(
		image_dir / f"blackboard_upload-protein_image_{image_number:02d}.csv"
	)
	student_ids_csv = roster_csv
	image_hashes_yaml = str(protein_images_path.get_image_hashes_yaml())

	params_dict = {
		"args": args,
		"image_number": image_number,
		"term": term,
		"spec_dir": spec_dir,
		"image_dir": str(image_dir),
		"image_raw_dir": str(image_raw_dir),
		"config_yaml": config_yaml,
		"input_csv": input_csv,
		"output_csv": output_csv,
		"output_yml": output_yml,
		"grades_csv": grades_csv,
		"student_ids_csv": student_ids_csv,
		"image_hashes_yaml": image_hashes_yaml
	}

	display_info(params_dict)
	return params_dict

#============================================

def display_info(params: dict):
	"""
	Display relevant file information in a formatted table.

	Args:
		params (dict): Dictionary containing file paths and image number.
	"""
	table = rich.table.Table(show_header=True, header_style="bold magenta")

	table.add_column("Name", style="dim", width=20)
	table.add_column("Value", justify="left")

	table.add_row("Term", params["term"])
	table.add_row("Spec Dir", params["spec_dir"])
	table.add_row("Image Number", str(params["image_number"]))
	table.add_row("Config YAML", params["config_yaml"])
	table.add_row("Input CSV", params["input_csv"])
	table.add_row("Output CSV", params["output_csv"])
	table.add_row("Output YML", params["output_yml"])
	table.add_row("Grades CSV", params["grades_csv"])
	table.add_row("Roster CSV", params["student_ids_csv"])
	table.add_row("Image Hashes", params["image_hashes_yaml"])

	console.print(table)
	time.sleep(1)

#============================================

def validate_questions(read_only_config: dict):
	"""
	Check for duplicate CSV columns in YAML configuration.

	Args:
		read_only_config (dict): Dictionary containing YAML configuration.
	"""
	used_csv_columns = {}
	for question_dict in read_only_config['csv_questions']:
		csv_column = question_dict['csv_column']
		if csv_column in used_csv_columns:
			console.print(f"CSV Column {csv_column} used for more than one question!")
			console.print(used_csv_columns[csv_column])
			console.print(question_dict['name'])
			raise ValueError
	used_csv_columns[csv_column] = question_dict['name']

#============================================
def load_common_image_questions(spec_dir: str) -> list:
	"""
	Load common image questions from the spec directory.
	"""
	common_path = os.path.join(spec_dir, "common_image_questions.yml")
	if not os.path.isfile(common_path):
		return []
	with open(common_path, 'r') as f:
		common_config = yaml.safe_load(f)
	if common_config is None:
		return []
	return common_config.get('image_questions', [])

#============================================
def merge_image_questions(common_list: list, specific_list: list) -> list:
	"""
	Merge common and assignment-specific image questions.
	"""
	common_list = common_list or []
	specific_list = specific_list or []

	specific_map = {}
	for question_dict in specific_list:
		if not isinstance(question_dict, dict):
			continue
		name = question_dict.get('name')
		if name:
			specific_map[name] = question_dict

	merged = []
	used = set()
	for question_dict in common_list:
		if not isinstance(question_dict, dict):
			continue
		name = question_dict.get('name')
		if name and specific_map.get(name) is not None:
			merged.append(specific_map[name])
			used.add(name)
		else:
			merged.append(question_dict)
			if name:
				used.add(name)

	for question_dict in specific_list:
		if not isinstance(question_dict, dict):
			continue
		name = question_dict.get('name')
		if name in used:
			continue
		merged.append(question_dict)

	return merged

#============================================

def load_yaml_config(params: dict) -> dict:
	"""
	Load and validate YAML configuration.

	Args:
		params (dict): Dictionary containing file paths and image number.

	Returns:
		dict: Read-only dictionary of YAML config.
	"""
	# Read the YAML file
	with open(params["config_yaml"], 'r') as f:
		config = yaml.safe_load(f)

	# Merge common image questions if present
	if config.get('use_common_image_questions', True) is True:
		common_questions = load_common_image_questions(params["spec_dir"])
		if common_questions:
			config['image_questions'] = merge_image_questions(
				common_questions,
				config.get('image_questions', [])
			)

	# Convert config to read-only dictionary
	read_only_config = MappingProxyType(config)
	# Validate image number
	if read_only_config['image number'] != params["image_number"]:
		console.print(
			f"Image numbers do not match: {read_only_config['image number']} != {params['image_number']}"
		)
		raise ValueError("Image number mismatch in YAML file.")

	# Validate keys in config tree
	student_id_protein.validate_dict_keys_in_tree(
		read_only_config['image_questions'],
		('name', 'point_deduction', 'feedback', 'type')
	)
	student_id_protein.validate_dict_keys_in_tree(
		read_only_config['csv_questions'],
		('name', 'csv_column', 'type')
	)

	console.print(f"{read_only_config['assignment name']} worth {read_only_config['total points']} points")

	validate_questions(read_only_config)

	return read_only_config


#============================================
def _parse_submission_timestamp(row: dict) -> datetime.datetime:
	"""
	Return the comparable submission timestamp for one form or YAML row.

	Google Forms timestamps currently arrive as
	`YYYY/MM/DD H:MM:SS AM EST`. The trailing timezone abbreviation is
	not needed for ordering submissions inside one course form.

	Args:
		row: Student row carrying the canonical `timestamp` key.

	Returns:
		A naive datetime used only for newest-submission comparison.
	"""
	timestamp = row["timestamp"]
	timestamp_without_zone = timestamp[:-4].strip()
	parsed = datetime.datetime.strptime(timestamp_without_zone,
		"%Y/%m/%d %I:%M:%S %p")
	return parsed


#============================================
def _collapse_form_to_newest_submissions(form_tree: list) -> list:
	"""
	Keep only the newest form row for each Student ID.

	Duplicate Student IDs normally mean a student submitted the same
	assignment again. The newest timestamp is the row the grader should
	process; older rows are ignored with a terminal notice so the
	operator can still see what happened.

	Args:
		form_tree: List of student dicts as read from the form CSV.

	Returns:
		A form tree with at most one row per Student ID.
	"""
	entries_by_student: dict = {}
	order: list = []
	for index, row in enumerate(form_tree):
		key = grade_status.student_key(row)
		parsed_timestamp = _parse_submission_timestamp(row)
		if key not in entries_by_student:
			entries_by_student[key] = (index, parsed_timestamp, row)
			order.append(key)
			continue
		old_index, old_timestamp, old_row = entries_by_student[key]
		if parsed_timestamp > old_timestamp:
			print(
				f"WARNING: duplicate Student ID {key!r} in form CSV at "
				f"rows {old_index} and {index}; using newer row {index}."
			)
			entries_by_student[key] = (index, parsed_timestamp, row)
		else:
			print(
				f"WARNING: duplicate Student ID {key!r} in form CSV at "
				f"rows {old_index} and {index}; keeping newer row "
				f"{old_index}."
			)
			entries_by_student[key] = (old_index, old_timestamp, old_row)
	collapsed_tree = [entries_by_student[key][2] for key in order]
	return collapsed_tree


#============================================
def _resolve_form_rows_to_roster_student_ids(form_tree: list,
		student_ids_tree: list) -> list:
	"""
	Resolve form rows to authoritative roster Student IDs before merging.

	The typed form RUID is untrusted. Resolve every row independently so
	two submissions from the same student can both resolve to the same
	roster row, then let `_collapse_form_to_newest_submissions` choose
	the newest timestamp.
	"""
	roster = student_id_protein.build_roster_from_student_ids_tree(
		student_ids_tree
	)
	matcher = roster_matching.RosterMatcher(
		roster=roster,
		interactive=True,
		auto_threshold=0.90,
		auto_gap=0.06,
		candidate_count=5,
	)
	resolved_tree = []
	for student_entry in form_tree:
		student_entry["Form RUID"] = str(student_entry["Student ID"])
		form_row = {
			"form_ruid": str(student_entry["Student ID"]),
			"first_name": student_entry["First Name"],
			"last_name": student_entry["Last Name"],
			"username": student_entry["Username"],
		}
		# Fresh assigned set per row: duplicate submissions are handled
		# by newest-timestamp collapse, not by the resolver's same-run
		# duplicate guard.
		result = ruid_resolver.resolve_form_row_to_roster_row(
			form_row, matcher, set(),
		)
		if isinstance(result, ruid_resolver.UnresolvedStudent):
			raise RuntimeError(
				f"Could not match a student to the roster: {student_entry}. "
				"Please edit the CSV file and try again."
			)
		raw = roster[result.roster_ruid]["_raw"]
		print(f"{result.roster_ruid} {result.full_name} <= "
			f"{result.reason} score={result.score:.3f}")
		student_id_protein.merge_student_records(student_entry, raw)
		resolved_tree.append(student_entry)
	return resolved_tree


#============================================
def _merge_yaml_into_form(form_tree: list, yaml_tree: list) -> list:
	"""
	Merge a cached checkpoint YAML into the freshly read form CSV.

	Identity is `Student ID` after the form rows are collapsed to the
	newest timestamp per student. For each form row whose Student ID is
	in the YAML with the same timestamp, the merged row starts from the
	YAML row and the form row only fills keys that are MISSING from the
	YAML; existing YAML values (cached hashes, statuses, deductions,
	scores) are never overwritten. If the form row has a newer timestamp
	than the cached YAML row, the form row wins so the resubmission is
	graded. Form rows whose Student ID is not in the YAML pass through
	unchanged. YAML rows whose Student ID is no longer in the form CSV
	are skipped with a warning; the current form CSV is the source of
	truth for which submissions exist.

	YAML duplicates raise via `_validate_unique_yaml_student_ids` so the
	helper can be called outside the normal `load_student_data` path.

	Args:
		form_tree: Latest form-CSV rows (defines column shape and order).
		yaml_tree: Cached checkpoint rows (drives the grading state).

	Returns:
		Merged tree, in form-row order.

	Raises:
		ValueError: on duplicate Student IDs in the YAML tree.
	"""
	form_tree = _collapse_form_to_newest_submissions(form_tree)
	_validate_unique_yaml_student_ids(yaml_tree)
	yaml_index = {grade_status.student_key(entry): entry for entry in yaml_tree}

	merged_tree: list = []
	consumed_yaml_keys: set = set()
	for form_row in form_tree:
		key = grade_status.student_key(form_row)
		if key in yaml_index:
			yaml_row = yaml_index[key]
			form_timestamp = _parse_submission_timestamp(form_row)
			yaml_timestamp = _parse_submission_timestamp(yaml_row)
			if form_timestamp > yaml_timestamp:
				print(
					f"WARNING: newer submission for Student ID {key}; "
					"grading latest form row instead of cached YAML row."
				)
				form_row["Force Image Download"] = True
				merged_tree.append(form_row)
				consumed_yaml_keys.add(key)
				continue
			merged_row = dict(yaml_row)
			# Backfill: only keys NOT already in the YAML row may flow
			# in from the form row. Existing YAML values (cached
			# hashes, statuses, deductions) are never overwritten.
			for form_key, form_value in form_row.items():
				if form_key not in merged_row:
					merged_row[form_key] = form_value
			merged_tree.append(merged_row)
			consumed_yaml_keys.add(key)
		else:
			merged_tree.append(form_row)

	# Skip YAML rows no form row claimed. They may be stale output, or a
	# prior roster-resolved Student ID whose current form row has a
	# different typed RUID. Appending them creates duplicate roster
	# matches later in load_student_data.
	for yaml_key, yaml_row in yaml_index.items():
		if yaml_key in consumed_yaml_keys:
			continue
		print(f"WARNING: skipped yaml-only student {yaml_key} (no matching form row)")

	return merged_tree


#============================================
def _validate_unique_yaml_student_ids(yaml_tree: list) -> None:
	"""
	Raise if two YAML entries share a Student ID.

	Mirrors the form-CSV check so `_merge_yaml_into_form` can be
	called outside `load_student_data` (where `validate_checkpoint`
	would otherwise have already caught the duplicate).

	Args:
		yaml_tree: List of cached student dicts.

	Raises:
		ValueError: when two entries share a Student ID.
	"""
	seen: dict = {}
	for index, entry in enumerate(yaml_tree):
		key = grade_status.student_key(entry)
		if key in seen:
			raise ValueError(
				f"duplicate Student ID {key!r} in checkpoint YAML at "
				f"entries {seen[key]} and {index}"
			)
		seen[key] = index


#============================================
def load_student_data(params: dict, read_only_config: dict) -> tuple:
	"""
	Load student data from the form CSV, optionally merging a cached
	checkpoint YAML on top.

	When `--yaml-backup-file` is supplied the function:
	  - Reads the form CSV (latest column shape).
	  - Loads + validates the checkpoint YAML.
	  - Merges by Student ID with no-overwrite backfill.
	  - Prints `Resuming from <path>` on success.

	When the flag is absent the behavior is identical to the historical
	wholesale path: read the form CSV, run roster matching.

	Args:
		params (dict): Dictionary containing file paths.
		read_only_config (dict): YAML configuration.

	Returns:
		tuple: (student_tree, student_ids_tree)
	"""
	t0 = time.time()
	# Always read the form CSV first: it carries the latest column
	# shape (e.g., a CSV question added after the cached YAML was
	# written) and is the source of truth for which submissions exist.
	form_tree = file_io_protein.read_student_csv_data(
		params["input_csv"], read_only_config
	)
	yaml_path = params["args"].yaml_backup_file
	if yaml_path and not os.path.isfile(yaml_path):
		raise FileNotFoundError(
			f"Checkpoint YAML not found: {yaml_path}"
		)

	# Load roster before merging: typed form RUIDs are untrusted, so all
	# resume/collapse decisions below must use authoritative roster RUIDs.
	if not os.path.isfile(params["student_ids_csv"]):
		raise ValueError(
			f"Roster CSV not found: {params['student_ids_csv']}\n"
			"Place the roster at repo root as `current_students.csv` or pass --roster."
		)
	student_ids_tree = file_io_protein.read_student_ids(params["student_ids_csv"])
	form_tree = _resolve_form_rows_to_roster_student_ids(
		form_tree, student_ids_tree
	)
	params["all_form_submissions"] = form_tree

	if yaml_path:
		with open(yaml_path, "r", encoding="utf-8") as handle:
			yaml_tree = yaml.safe_load(handle)
		# Validate before trusting the file. Image-number cross-check
		# guards against an operator pointing the regrade at the wrong
		# image's checkpoint.
		grade_status.validate_checkpoint(
			yaml_tree, image_number=params["image_number"]
		)
		student_tree = _merge_yaml_into_form(form_tree, yaml_tree)
		print(f"Resuming from {os.path.relpath(yaml_path)}")
	else:
		# Duplicate form rows are student resubmissions; grade the
		# newest submission for each Student ID.
		student_tree = _collapse_form_to_newest_submissions(form_tree)

	# Quick timestamp check
	timestamp_tools.check_due_date(student_tree[-1]['timestamp'], read_only_config)

	#back up matched students
	match_yaml = os.path.join(params["image_dir"], "matched_students.yml")
	if time.time() - t0 > 4:
		file_io_protein.backup_tree_to_yaml(match_yaml, student_tree)

	return student_tree, student_ids_tree

#============================================

def process_and_save(params: dict, student_tree: list, read_only_config: dict):
	"""
	Process student data and save output files.

	Args:
		params (dict): Dictionary containing file paths.
		student_tree (list): List of student data.
		read_only_config (dict): YAML configuration.
	"""
	try:
		process_data(student_tree, params, read_only_config)
	except (KeyboardInterrupt, Exception):
		# Backup crash data so the in-progress grading session is not lost,
		# then re-raise so the traceback reaches the user.
		file_io_protein.write_output_file("crash_data.csv", student_tree)
		file_io_protein.backup_tree_to_yaml("crash_data.yml", student_tree)
		raise

	# Write processed data to output files
	file_io_protein.write_output_file(params["output_csv"], student_tree)
	file_io_protein.backup_tree_to_yaml(params["output_yml"], student_tree)
	file_io_protein.write_student_grades_for_upload(
		read_only_config['assignment name'], params["grades_csv"], student_tree
	)


#==========================================
def process_data(student_tree: list, params: dict, read_only_config_dict: dict) -> None:
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
	t0 = time.time()
	console.print("\nPre-Processing Student Images", style=data_color)
	console.print("\nDownloading and Reading Student Images", style=data_color)
	read_save_images.read_and_save_student_images(student_tree, params)
	# Save backup of the student_tree
	download_save_yaml = os.path.join(params["image_dir"], "downloaded_images.yml")
	if time.time() - t0 > 4:
		file_io_protein.backup_tree_to_yaml(download_save_yaml, student_tree)

	console.print("\nChecking Student Images for Duplicates", style=data_color)
	duplicate_processing.check_duplicate_images(student_tree, params)
	# Save backup of the student_tree
	duplicate_check_save_yaml = os.path.join(params["image_dir"], "duplicate_check_save.yml")
	if time.time() - t0 > 4:
		file_io_protein.backup_tree_to_yaml(duplicate_check_save_yaml, student_tree)

	# Loop through each student entry and process timestamp due dates
	console.print("\nPre-Processing Turn In Date", style=data_color)
	for student_entry in student_tree:
		timestamp_tools.timestamp_due_date(student_entry, read_only_config_dict)

	# Save backup of the student_tree
	preprocess_save_yaml = os.path.join(params["image_dir"], "preprocess_save.yml")
	if time.time() - t0 > 4:
		file_io_protein.backup_tree_to_yaml(preprocess_save_yaml, student_tree)

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

	# Save backup of the student_tree
	postquestions_save_yaml = os.path.join(params["image_dir"], "post-questions_save.yml")
	if time.time() - t0 > 4:
		file_io_protein.backup_tree_to_yaml(postquestions_save_yaml, student_tree)

	# Generate HTML for visual grading if enabled
	if params["args"].make_html is True:
		image_number = params["args"].image_number
		html_output = os.path.join(
			params["image_dir"],
			f"protein_images_{image_number:02d}.html",
		)
		download_submission_images.write_html_from_student_tree(
			student_tree, html_output,
			all_submissions=params["all_form_submissions"],
		)
		download_submission_images.open_html_in_browser(html_output)

	# Loop through each student entry and process image questions
	console.print("\nProcess Image Questions", style='green')
	proc_img = interactive_image_criteria_class.process_image_questions_class(student_tree, read_only_config_dict)
	proc_img.process_all_student_images()

	# Save backup of the student_tree
	postimages_save_yaml = os.path.join(params["image_dir"], "post-images_save.yml")
	if time.time() - t0 > 4:
		file_io_protein.backup_tree_to_yaml(postimages_save_yaml, student_tree)

	# Calculate the final score for each student entry
	console.print("\nCalculating Final Scores")
	for student_entry in student_tree:
		get_final_score(student_entry, read_only_config_dict)
	console.print('DONE Processing Data\n\n')

#============================================

def main():
	"""
	Main function to parse arguments and process the CSV file.
	"""
	# Prepare file paths and other paramters
	params = parse_and_prepare()

	# Read the spec_yaml_files/protein_image_xx.yml file
	read_only_config = load_yaml_config(params)

	# read student data and match submitted names to the roster
	student_tree, student_ids_tree = load_student_data(params, read_only_config)

	#final step must be doing a lot (!)
	process_and_save(params, student_tree, read_only_config)
