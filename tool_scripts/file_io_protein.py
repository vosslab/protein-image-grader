
import csv
import yaml

#==============
def read_student_csv_data(input_csv: str, config: dict) -> list:
	"""
	Read student data from a CSV file and return a list of dictionaries for each student.

	Parameters
	----------
	input_csv : str
		The path to the input CSV file containing student data.
	config : dict
		Dictionary containing configuration options, such as metadata and question columns.

	Returns
	-------
	list
		Returns a list of dictionaries, where each dictionary represents a student's information.

	"""
	# Retrieve metadata column information and hidden columns from the configuration
	meta_columns_dict = config.get("meta columns", {})
	print(meta_columns_dict)
	hide_columns_indices = config.get("hide columns", [])
	print(hide_columns_indices)

	# Get the list of questions to read from the CSV
	csv_questions_list = config.get("csv_questions", {})

	# Initialize a list to hold the student entries
	student_tree = []

	# Initialize a variable to hold the CSV headers
	header_list = None

	# Open the CSV file and read its content
	with open(input_csv, 'r') as f:
		reader = csv.reader(f)
		for row_list in reader:
			# If header_list is None, this is the first row (header)
			if header_list is None:
				header_list = row_list
				continue

			# Initialize a dictionary to hold a single student's data
			student_entry = {}

			# Populate the metadata columns for the student
			for meta_key, index in meta_columns_dict.items():
				student_entry[meta_key] = row_list[index-1].strip()

			# Populate the questions for the student
			for csv_question_dict in csv_questions_list:
				index = csv_question_dict['csv_column']
				name = csv_question_dict['name'].strip()
				student_entry[name] = row_list[index-1].strip()
			student_entry['Protein Image Number'] = config['image number']

			student_entry['Warnings'] = []
			# Add the student_entry to student_tree
			student_tree.append(student_entry)

	# Sort the student_tree by the 'First Name' field
	student_tree = sorted(student_tree, key=lambda student: student['First Name'].lower().strip())

	# Output the number of read lines
	print(f"Read {len(student_tree)} lines from CSV file")

	return student_tree

#==============
def read_student_ids(student_ids_csv: str) -> list:
	"""
	Read student IDs from a CSV file and return a list of dictionaries for each student's ID data.

	Parameters
	----------
	student_ids_csv : str
		The path to the input CSV file containing student IDs.

	Returns
	-------
	list
		Returns a list of dictionaries, where each dictionary represents a student's ID information.
	"""

	# Print the filename to the console for tracking
	print(f"reading from file {student_ids_csv}")

	# Initialize variables for storing header data and student IDs
	header_list = None
	student_ids_tree = []

	# Open the CSV file for reading
	with open(student_ids_csv, 'r') as f:
		reader = csv.reader(f)
		for row_list in reader:
			# If header_list is None, it means we're reading the first row, which is the header
			if header_list is None:
				header_list = row_list
				continue

			# Initialize a dictionary to store individual student ID data
			student_id_data = {}

			# Populate the student ID data from the current row
			for i, header_key in enumerate(header_list):
				student_id_data[header_key] = row_list[i].strip()

			# Add the student ID data to the list of all student IDs
			student_ids_tree.append(student_id_data)

	# Sort the student IDs by the 'First Name' field
	student_ids_tree = sorted(student_ids_tree, key=lambda student: student['First Name'].lower().strip())

	# Print out the number of lines read from the file
	print(f"Read {len(student_ids_tree)} lines from CSV file")

	# Return the list of student IDs
	return student_ids_tree


#==============
def write_student_grades_for_upload(assignment_name: str, grades_csv: str, student_tree: list) -> None:
	"""
	Write student grades to a CSV file for upload.

	Parameters
	----------
	assignment_name : str
		The name of the assignment for which the grades are being written.

	grades_csv : str
		The file name or file path to which the grades will be written.

	student_tree : list
		List of dictionaries, each representing a student's grade and other information.

	Returns
	-------
	None
	"""

	# Displaying the file name to which grades will be written
	print(f"writing to file {grades_csv}")

	# Initialize a list to hold the headers needed for the CSV file
	headers = ['First Name', 'Last Name', 'Username', 'Student ID', assignment_name]

	# Create a new list of dictionaries filtered to only contain keys that are in the headers list
	filtered_student_tree = [{k: s[k] for k in headers} for s in student_tree]

	# Open the file in write mode
	with open(grades_csv, 'w', newline='') as output_file:
		# Initialize a CSV DictWriter object with the specified headers and delimiter
		writer = csv.DictWriter(output_file, headers, delimiter='\t')

		# Write the headers to the CSV file
		writer.writeheader()

		# Write the rows to the CSV file
		writer.writerows(filtered_student_tree)

#==============
def write_output_file(output_csv: str, student_tree: list) -> None:
	"""
	Write student data to a CSV file.

	Parameters
	----------
	output_csv : str
		The file name or file path where the CSV will be written.

	student_tree : list
		A list of dictionaries, each dictionary containing data for a single student.

	Returns
	-------
	None
	"""

	# Print the name of the output CSV file
	print(f"writing CSV to file {output_csv}")

	# Initialize a set to hold unique header fields
	all_headers = set()

	# Iterate through each student's data to update the set of headers
	for student in student_tree:
		all_headers.update(student.keys())

	# Convert the set of unique headers into a sorted list
	headers = list(all_headers)
	headers.sort()

	# Open the file in write mode
	with open(output_csv, 'w', newline='') as output_file:
		# Initialize a CSV DictWriter with the sorted headers and a tab delimiter
		writer = csv.DictWriter(output_file, headers, delimiter='\t')

		# Write the headers to the CSV file
		writer.writeheader()

		# Write the student data rows to the CSV file
		writer.writerows(student_tree)


#==============
def backup_tree_to_yaml(file_name: str, tree: list) -> None:
	"""
	Back up a list of dictionaries to a YAML file.

	Parameters
	----------
	file_name : str
		The name of the YAML file to create.

	tree : list
		The list of dictionaries to back up.

	Returns
	-------
	None
	"""

	# Print the name of the output YAML file using f-string
	print(f"writing YAML to file {file_name}")

	# Use 'with' statement to ensure the file is properly closed after writing
	with open(file_name, 'w') as yaml_file:
		# Dump the list of dictionaries (tree) into the YAML file
		# Using default_flow_style=False to make the output more human-readable
		yaml.dump(tree, yaml_file, default_flow_style=False)
