
import re
import sys
import time
import difflib
from collections import defaultdict

from rich.console import Console
from rich.style import Style
from rich.text import Text

console = Console()
warning_color = Style(color="rgb(255, 187, 51)" )  # RGB for bright orange
question_color = Style(color="rgb(100, 149, 237)" )  # RGB for cornflower blue
data_color = Style(color="rgb(187, 51, 255)" )  # RGB for purple
student_style = Style(color="blue", bold=True, italic=True)
validation_color = Style(color="rgb(153, 230, 76)" )  # RGB for lime-ish green

validation_types = {
	'a': 'almost',
	'b': 'bonus',
	'f': 'finished',
	'n': 'no',
	'p': 'previous',
	's': 'save',
	'y': 'yes',
}

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

	options_text = '-- '
	for letter in valid_letters:
		word = validation_types[letter]
		word = word.replace(letter, '(' + letter + ')')
		options_text += word + '/'
	options_text = options_text[:-1] + ': '

	while True:
		# Use Rich to print the styled part of the statement
		console.print(statement)

		# Get the user's input
		validation = input(options_text)

		# Check if the entered input is in the list of valid inputs
		if validation.lower() in valid_tuple:
			return validation.lower()

		# Use Rich to print an error message if the entry is invalid
		console.print("ERROR ~ try again ~\n", style='red')

#==============
def get_input_validation2(message: str, valid_letters: str) -> str:
	"""
	Get user input for image validation and ensure it's valid.

	Parameters
	----------
	message : str
		The custom message that will be displayed to the user when asking for input.
	valid_letters : str
		The string containing all valid input letters.

	Returns
	-------
	str
		The validated user input.
	"""
	# Convert the string of valid letters to a tuple.
	valid_tuple = tuple(valid_letters)
	statement = message.strip() + '\n - '

	for letter in valid_letters:
		word = validation_types[letter]
		word = word.replace(letter, '(' + letter + ')')
		statement += word + '/'
	statement = statement[:-1] + ': '

	while True:
		# Use Rich to print the statement with style
		console.print(Text(statement, style=validation_color))

		# Get the user's input. Note: input() is used without styling as it doesn't support Rich styles directly.
		validation = input()

		# Check if the entered input is in the list of valid inputs.
		if validation.lower() in valid_tuple:
			return validation.lower()

		# Use Rich to print an error message if the entry is invalid.
		console.print("ERROR ~ try again ~\n", style='red')


#==============
def print_student_info(student_entry: dict) -> None:
	"""
	Retrieve and format student's name and ID from the student_entry.

	Parameters
	----------
	student_entry : dict
		The student information dictionary, expected to have keys 'First Name', 'Last Name', and 'Student ID'.

	Returns
	-------
	None
		This function prints the student information and returns None.
	"""
	# Get and format the first name to title case.
	first_name = student_entry['First Name'].title()
	# Get the first three characters of the last name and format to title case.
	last_name = student_entry['Last Name'].title()
	# Retrieve the student's unique ID.
	ruid = student_entry['Student ID']
	# Print the student's formatted information.
	# Create a Text object for rich formatting
	student_info_text = Text(f"Student {ruid}: {first_name} {last_name}.", style=student_style)

	# Print a line for visual separation
	#console.print("---------", style="dim")
	# Print the student's formatted information using rich console
	console.print(student_info_text)

# Validate function behavior
assert print_student_info({"First Name": "john", "Last Name": "doe", "Student ID": 1234}) is None

#==============
def validate_dict_keys_in_tree(tree: list, required_keys: tuple) -> None:
	"""
	Validates that each dictionary in a list (tree) contains all required keys.

	Parameters
	----------
	tree : list
		A list of dictionaries. Each dictionary should represent a "node" in the tree.
	required_keys : tuple
		A tuple of keys that must be present in each dictionary.

	Returns
	-------
	None
		This function raises a ValueError if any required key is missing in any dictionary.
	"""

	# Loop through each dictionary in the tree
	for i, node in enumerate(tree):
		# Check if the node is actually a dictionary
		if not isinstance(node, dict):
			raise TypeError(f"The element at index {i} is not a dictionary. It is a {type(node).__name__}.")

		# Check that each required key is in the dictionary
		for key in required_keys:
			if key not in node:
				existing_keys = ', '.join(map(str, node.keys()))
				node_name = node.get('name', '')
				node_type = node.get('type', '')
				raise ValueError(
					f"The required key '{key}' is missing in the dictionary at index {i}. "
					f"Existing keys: [{existing_keys}]. "
					f"Name: {node_name}, Type: {node_type}"
				)
	return True

required_keys = ('x', 'y')
valid_dict = {'x': 1, 'y': 2}
tree = [valid_dict]
assert validate_dict_keys_in_tree(tree, required_keys)

#=====================
# Group Student Responses Based on Processing Rules
#=====================
def group_student_responses(student_tree: list, question_dict: dict) -> defaultdict:
	"""
	Group student answers based on processing rules specified in the 'question_dict' dictionary.

	Parameters:
	-----------
	student_tree : list of dict
		A list of dictionaries, where each dictionary contains the responses from one student.
	question_dict : dict
		A dictionary containing details of the question.
		Expected to contain 'name' (str) and may contain 'type' (str).

	Returns:
	--------
	dict
		A dictionary with processed student answers as keys and corresponding student entries as values.
	"""
	# Initialize an empty defaultdict to store grouped responses
	grouped_responses = defaultdict(list)

	# Get the key for this question's answer
	response_key = question_dict['name']

	# Iterate over each student's entry in the student_tree
	for student_entry in student_tree:
		# Extract the given answer for the question from the student's entry
		given_answer = student_entry[response_key]

		# Identify the expected data type for the answer, defaulting to an empty string
		answer_type = question_dict["type"]

		# Process the answer based on its type
		if answer_type == "str":
			# Convert to lowercase and remove non-alphanumeric characters for string answers
			processed_answer = given_answer.lower()
			processed_answer = re.sub('[^a-z0-9]', '', processed_answer)
		elif answer_type == "int":
			# Convert to integer for int type answers
			try:
				processed_answer = int(given_answer)
			except ValueError:
				processed_answer = float(given_answer)
		elif answer_type == "float":
			# Convert to float for float type answers
			processed_answer = float(given_answer)
		else:
			# Strip leading and trailing whitespace for unspecified types
			processed_answer = given_answer.strip()

		# Append the student's entry to the list of entries for this processed answer
		grouped_responses[processed_answer].append(student_entry)

	# Return the grouped responses
	return grouped_responses

#==============
def student_entry_to_normalized_key(student_entry: dict, keys: tuple) -> str:
	"""
	Create a normalized key based on a student entry and specified keys.

	Parameters
	----------
	student_entry : dict
		Dictionary containing student information.

	keys : tuple
		Tuple of keys used to generate the normalized key.

	Returns
	-------
	str
		The normalized key generated from the student entry.
	"""
	# Initialize an empty list to store processed key values
	processed_keys = []

	# Loop through each key in the tuple of keys
	for key in keys:
		# Fetch the value from the student_entry dictionary
		value = student_entry[key]

		# Check if the value is a string
		if isinstance(value, str):
			# Apply lower() and strip() if it is a string
			processed_value = value.lower().strip()
		else:
			# Otherwise, just convert it to string
			processed_value = str(value)

		# Append the processed value to the list
		processed_keys.append(processed_value)

	# Join the processed keys into a single string separated by spaces
	normalized_key = ' '.join(processed_keys)

	return normalized_key

# Simple assertion test for the function 'student_entry_to_normalized_key'
test_student_entry = {'ID': 12, 'Name': 'JoHN  '}
test_keys = ('ID', 'Name')
result = student_entry_to_normalized_key(test_student_entry, test_keys)
assert result == '12 john'


#==============
def find_closest_match(normalized_key: str, name_to_record: dict) -> str:
	"""
	Find the closest matching key in a name-to-record dictionary.

	Parameters
	----------
	normalized_key : str
		The key generated from a student entry to be matched.

	name_to_record : dict
		Dictionary whose keys are normalized names, and values are student records.

	Returns
	-------
	str
		The closest matching key found in name_to_record.
	"""

	# Try to find the best match with a high cutoff value
	best_match = difflib.get_close_matches(
		normalized_key,
		name_to_record.keys(),
		n=1,
		cutoff=0.9
	)
	# If no match is found, lower the cutoff value and try again
	if not best_match:
		print(f"No automatic match for {normalized_key}")
		best_match = difflib.get_close_matches(
			normalized_key,
			name_to_record.keys(),
			n=1,
			cutoff=0.4
		)
		# If still no match, exit the program
		if not best_match:
			print(f"{normalized_key} NOT FOUND")
			print('no matches found at all.')
			sys.exit(1)

		# Ask for user validation for the found match
		matched_name = best_match[0]
		print(f"A: {matched_name}")
		print(f"B: {normalized_key}")
		validation = get_input_validation("    is this a good match?", 'yn')  # Assuming get_input_validation is defined
		if validation == 'n':
			print("Please edit the CSV file and try again.")
			sys.exit(1)
	return best_match[0]

#==============
def merge_student_records(student_entry: dict, student_id_record: dict, merge_keys=None) -> None:
	"""
	Merges student records based on given keys, defaults to 'Student ID', 'Username', 'First Name', and 'Last Name'.

	Parameters
	----------
	student_entry : dict
		The dictionary containing the initial student entry to be updated.

	student_id_record : dict
		The dictionary containing student ID records to merge with student_entry.

	merge_keys : tuple, optional
		Tuple of keys to merge, if not provided defaults to ('Student ID', 'Username', 'First Name', 'Last Name').

	Returns
	-------
	None
		Updates student_entry in-place.
	"""
	# Check if 'Student ID' in both records match
	if student_id_record['Student ID'] != student_entry['Student ID']:
		print("\n\nWARNING OVERWRITING Student ID\n")
		# Delay for 1 second to allow the user time to notice the warning
		time.sleep(1)

	# If merge_keys is not provided, set the default keys to merge
	if merge_keys is None:
		merge_keys = ('Student ID', 'Username', 'First Name', 'Last Name')

	# Loop through the keys and update the student_entry with corresponding values from student_id_record
	for key in merge_keys:
		student_entry[key] = student_id_record[key]

# Simple assertion test for the function: 'merge_student_records'
test_merge_keys = ('Student ID', 'Name')
test_student_entry = {'Student ID': '123', 'Name': 'Jane Doe'}
test_student_id_record = {'Student ID': '123', 'Name': 'John Doe'}
merge_student_records(test_student_entry, test_student_id_record, test_merge_keys)
assert test_student_entry == {'Student ID': '123', 'Name': 'John Doe'}

#==============
def match_lists_and_add_student_ids(student_ids_tree: list, student_tree: list) -> None:
	"""
	Match lists of student records and add student IDs to each record in student_tree.

	Parameters
	----------
	student_ids_tree : list
		List of dictionaries containing student ID records.

	student_tree : list
		List of dictionaries containing student records to which IDs are to be added.

	Returns
	-------
	None
	"""

	# Set to hold all the normalized_keys that have been assigned
	assigned_normalized_keys_set = set()

	# Keys used to normalize student entries
	keys_used_to_normalize = ('Student ID', 'First Name', 'Last Name')

	# Dictionary to match normalized_keys to student_entries
	name_to_record = {}
	for student_id_entry in student_ids_tree:
		normalized_key = student_entry_to_normalized_key(student_id_entry, keys_used_to_normalize)
		name_to_record[normalized_key] = student_id_entry

	for student_entry in student_tree:
		normalized_key = student_entry_to_normalized_key(student_entry, keys_used_to_normalize)
		matched_name = find_closest_match(normalized_key, name_to_record)

		# Get the student_id_record for matched_name
		student_id_record = name_to_record[matched_name]

		# Check if the new normalized_key after merging will be unique
		new_normalized_key = student_entry_to_normalized_key(student_id_record, keys_used_to_normalize)

		if new_normalized_key in assigned_normalized_keys_set:
			print(f"WARNING: The normalized_key {new_normalized_key} would be duplicated.")
			print("Please edit the CSV file and try again.")
			sys.exit(1)

		# Update the set with the new normalized_key
		assigned_normalized_keys_set.add(new_normalized_key)

		print(f"{matched_name} <=> {normalized_key}")
		merge_student_records(student_entry, student_id_record)
	print('\n\n')

