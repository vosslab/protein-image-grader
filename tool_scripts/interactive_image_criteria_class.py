import sys
import time
from rich.console import Console
from rich.style import Style

from tool_scripts import file_io_protein
from tool_scripts import student_id_protein

console = Console()
warning_color = Style(color="rgb(255, 187, 51)")  # RGB for bright orange
question_color = Style(color="rgb(100, 149, 237)" )  # RGB for cornflower blue
data_color = Style(color="rgb(187, 51, 255)")  # RGB for purple
brown_color = Style(color="rgb(153, 102, 51)")  # RGB for purple

#============================
class process_image_questions_class():
	def __init__(self, student_tree, read_only_config_dict):
		self.student_tree = student_tree
		self._read_only_config_dict = read_only_config_dict

	#==========================================
	def process_all_student_images(self):
		for student_entry in self.student_tree:
			self.process_image_questions(student_entry)

	#==========================================
	def quick_process_initial_image_validation(self, student_entry: dict, validation: str) -> bool:
		"""
		Process initial image validation based on the user's input and update the student's record accordingly.

		Parameters
		----------
		student_entry : dict
			The student information dictionary, which will be updated based on the image validation status.
		validation : str
			The user's input for validation, typically a single character like 'b', 'y', or 's'.

		Returns
		-------
		bool
			Returns True if the image status was either "Bonus" or "Correct", otherwise returns False.
		"""
		# Check if the validation input is 'b' for Bonus.
		if validation == 'b':
			console.print("!! BONUS !!")
			# Update the student's record with bonus information.
			student_entry.update({
				"Protein Image Status": "Bonus",
				"Protein Image Deduction": 0.0,
				"Protein Image Feedback": "Your image was one of the best in class"
			})
			return True
		# Check if the validation input is 'y' for Yes (Correct).
		elif validation == 'y':
			# Update the student's record with correct image status.
			student_entry.update({
				"Protein Image Status": "Correct",
				"Protein Image Deduction": 0.0,
				"Protein Image Feedback": "Good Job!"
			})
			return True
		elif validation == 'a':
			# Update the student's record with correct image status.
			student_entry.update({
				"Protein Image Status": "Minor",
				"Protein Image Deduction": 0.0,
				"Protein Image Feedback": "Minor corrections needed, no point deducted, see other comments"
			})
			return False
		elif validation == 'n':
			# Update the student's record with correct image status.
			student_entry.update({
				"Protein Image Status": "Major",
				"Protein Image Deduction": 0.0,
				"Protein Image Feedback": "Major corrections needed, see other comments for points lost"
			})
			return False
		# If validation input is none of the above, return False.
		return False

	# Validate function behavior
	#student_dict = {"Protein Image Status": "", "Protein Image Deduction": "", "Protein Image Feedback": ""}
	#assert self.quick_process_initial_image_validation(student_dict, 'b') == True
	#assert student_dict["Protein Image Status"] == "Bonus"

	#==========================================
	def save_and_exit(self) -> None:
		# Temporary backup of the student_tree
		file_io_protein.backup_tree_to_yaml("force_exit_save.yml", self.student_tree)
		time.sleep(0.1)
		sys.exit(0)

	#==========================================
	def make_question_incorrect(self, student_entry: dict, q_name: str, almost: bool=False) -> None:
		# Update the student's record based on the question
		question_dict = self.image_questions_dict[q_name]
		point_deduction = question_dict.get('point_deduction', 0)
		if almost is True:
			point_deduction = round(float(point_deduction) / 2.0, 1)
		student_entry.update({
			f"{q_name} Status": "Incorrect",
			f"{q_name} Deduction": float(point_deduction),
			f"{q_name} Feedback": question_dict.get('feedback', ''),
		})
		if almost is True:
			student_entry[f"{q_name} Feedback"] = (
				"Your image was close but not quite correct, "
				+ "only half of normal points were deducted. "
				+ student_entry[f"{q_name} Feedback"])
		if isinstance(student_entry[f"{q_name} Deduction"], tuple):
			console.print("MAJOR ERROR TUPLE VALUE", style='bright_red')
			student_entry["{q_name} Deduction"] = student_entry["{q_name} Deduction"][0]
			console.print(q_name)
			console.print(question_dict.get('point_deduction'))
			self.save_and_exit()

	#==========================================
	def make_question_correct(self, student_entry: dict, q_name: str) -> None:
		# Update the student's record based on the question
		student_entry.update({
			f"{q_name} Status": "Correct",
			f"{q_name} Deduction": 0,
			f"{q_name} Feedback": "",
		})

	#==========================================
	def process_image_question_list(self, student_entry: dict, almost_mode: bool) -> None:
		"""
		Process a list of image-related questions and update the student_entry dictionary based on the answers.

		Parameters
		----------
		student_entry : dict
			The dictionary containing the student's information and results. This will be updated with the
			validation results for each question.
		image_questions : list
			A list of dictionaries. Each dictionary represents an image-related question and its associated data.
		almost_mode : bool
			A flag to indicate whether to skip questions with non-zero point_deduction.

		Returns
		-------
		None
			This function modifies the student_entry dictionary in-place but does not return anything.
		"""
		# Fetch the list of image questions from the _read_only_config_dict dictionary
		image_questions = self._read_only_config_dict["image_questions"]

		# Calculate the total number of questions

		# Initialize the loop index
		i = 0
		total_q = len(image_questions)

		# Loop through each question dictionary in image_questions
		while i < total_q:
			question_dict = image_questions[i]
			# Extract the name of the question
			q_name = question_dict['name']

			# Skip the question if almost_mode is True and the point_deduction is not zero.
			if almost_mode is True and question_dict['point_deduction'] != 0:
				i += 1
				continue

			message = f"* Assessment {i+1}/{total_q}: {q_name}"

			# Skip if already graded, but update deduction if wrong
			status = student_entry.get(f"{q_name} Status")
			if status is not None:
				console.print(f'{message}: DONE {status}', style=brown_color)
				if student_entry.get(f"{q_name} Status") == "Incorrect":
					student_entry[f"{q_name} Deduction"] = question_dict.get('point_deduction', 0)
				i += 1
				continue

			# Formulate the message to be displayed for input validation
			validation = student_id_protein.get_input_validation(message, 'ynpasf', question_color)

			if validation == 'p':
				# If 'p' is entered, move back one step (Previous) if not at the beginning
				if i > 0:
					prev_question_dict = image_questions[i-1]
					prev_q_name = prev_question_dict['name']
					student_entry[f"{prev_q_name} Status"] = None
					i -= 1
				continue
			elif validation == 'f':
				# Update variables if the validation is 'f' for Finish
				i = total_q
				continue
			elif validation == 'y':
				# Update variables if the validation is 'y' for Yes
				self.make_question_correct(student_entry, q_name)
			elif validation == 'n':
				# Update variables if the validation is 'n' for No
				self.make_question_incorrect(student_entry, q_name, almost=False)
			elif validation == 'a':
				# Update variables if the validation is 'n' for No
				self.make_question_incorrect(student_entry, q_name, almost=True)
			elif validation == 's':
				# Update variables if the validation is 's' for Save and exit
				self.save_and_exit()

			# Move to the next question
			i += 1
		return


	#==========================================
	def process_image_questions(self, student_entry: dict) -> None:
		"""
		Process answers for image-based questions and update the student's entry accordingly.

		Parameters
		----------
		student_entry : dict
			The dictionary containing the student's information and results. This will be updated with the
			validation results.

		Returns
		-------
		None
			This function modifies the student_entry dictionary in-place but does not return anything.
		"""

		# Print student information using the provided function
		student_id_protein.print_student_info(student_entry)
		#print(student_entry.keys())
		print(f".. Original Filename = {student_entry['Original Filename']}")

		# Skip this student if it has already been graded
		if student_entry.get('Image Assessment Complete') is True:
			return

		validation = None
		consensus_background_color = student_entry['Consensus Background Color']
		self.image_questions_dict = { q['name']: q for q in self._read_only_config_dict['image_questions'] }

		image_format = student_entry['Image Format']
		if image_format != 'PNG':
			console.print(f"\nWARNING: image is not type PNG, it is: {image_format}", style=warning_color)
			validation = 'n'
			self.make_question_incorrect(student_entry, "File type is PNG, not JPEG or something else")
		else:
			self.make_question_correct(student_entry, "File type is PNG, not JPEG or something else")

		exact_match = student_entry['Exact Match']
		if exact_match is False:
			self.make_question_correct(student_entry, "Unique image, not same as another student")
		else:
			console.print("\n\aWARNING: image has exact match", style=warning_color)
			validation = 'n'
			self.make_question_incorrect(student_entry, "Unique image, not same as another student")

		if consensus_background_color is None or consensus_background_color != "White":
			console.print("\nWARNING: image likely does not have White Background", style=warning_color)
			console.print(f"Consensus Background Color: {consensus_background_color}")
			if self._read_only_config_dict.get('strict background', True) is True:
				validation = 'n'
				self.make_question_incorrect(student_entry, "White background was used")

		lower_filename = student_entry['Original Filename'].lower()
		if 'screenshot' in lower_filename or 'screen_shot' in lower_filename:
			console.print("  \aWARNING: image filename starts with screenshot", style=warning_color)
			student_entry['Warnings'].append("likely screenshot")
			self.make_question_incorrect(student_entry, "PNG image export was used, not a screenshot")

		if validation is None:
			# Obtain the user's input for the initial validation
			extra_desc = student_entry.get('extra description', '')
			if len(extra_desc) > 3:
				console.print(f"{extra_desc}", style=brown_color)
			validation = student_id_protein.get_input_validation("IMAGE is correct", 'ynabs')
		else:
			time.sleep(1)

		if validation == 's':
			self.save_and_exit()

		# Quickly process the initial validation and determine whether further processing is needed
		quick_status = self.quick_process_initial_image_validation(student_entry, validation)

		# Exit the function early if quick_status is True
		if quick_status is True:
			student_entry['Image Assessment Complete'] = True
			return

		# Check whether almost_mode should be activated based on the validation input
		almost_mode = (validation == 'a')

		# Process each image question and update the student_entry dictionary
		self.process_image_question_list(student_entry, almost_mode)
		student_entry['Image Assessment Complete'] = True
		return
