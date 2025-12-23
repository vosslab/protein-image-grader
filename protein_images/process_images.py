
import sys
import time
import yaml
from PIL import Image
from rich.console import Console
from rich.style import Style

import file_io_protein
import test_google_image
import student_id_protein


console = Console()
warning_color = Style(color="rgb(255, 187, 51)")  # RGB for bright orange
question_color = Style(color="rgb(100, 149, 237)" )  # RGB for cornflower blue
brown_color = Style(color="rgb(204, 153, 102)" ) #brown
data_color = Style(color="rgb(187, 51, 255)" )  # RGB for purple

#==============
def hex_to_bin(hex_string: str):
	"""Convert a hex string to its binary representation"""
	return bin(int(hex_string, 16))[2:].zfill(len(hex_string)*4)

#==============
def hamming_distance(s1: str, s2: str):
	"""Calculate the Hamming distance between two binary strings"""
	if len(s1) != len(s2):
		raise ValueError("Strings must be of the same length")
	return sum(ch1 != ch2 for ch1, ch2 in zip(s1, s2))

#==========================================
def pre_process_student_images(student_tree: list) -> None:
	with open('image_hashes.yml', 'r') as f:
		image_hashes = yaml.safe_load(f)
	local_image_hashes = {}
	local_image_perc_hashes = {}
	console.print("\nReading Student Images", style=data_color)
	for student_entry in student_tree:
		pre_status = student_entry.get("Image Format")
		# Skip this student if it has already been graded
		if pre_status is not None:
			return

		student_id_protein.print_student_info(student_entry)
		# https://drive.google.com/u/2/open?usp=forms_web&id=1QCHoMnqKvf6gqLI272ZQ4IGBCFupnC6s
		image_url = student_entry.get('image url')
		if image_url is None:
			console.print("  \aaError: Image URL not found", style="bright_red")
			sys.exit(1)
		named_corner_pixels_dict, filename, image_data = test_google_image.download_image_and_inspect(image_url)
		phash, md5hash = test_google_image.get_hash_data(image_data)
		# Assuming image_data is a _io.BytesIO object containing image data
		image_data.seek(0)  # Make sure you're at the beginning of the BytesIO object

		# Load the image using Pillow
		pil_image = Image.open(image_data)
		# Get the file format from PIL (for image files)
		image_format = pil_image.format
		image_mode = pil_image.mode

		lower_filename = filename.lower()
		print(lower_filename)
		if image_format is None:
			console.print(image_url)
			console.print(test_google_image.normalize_google_drive_url(image_url))
			console.print("  \aError: with this student's image, format not found, likely Google Drive permissions error", style="bright_red")
			raise TypeError
		if image_format != 'PNG':
			console.print(f"  WARNING: image is not type PNG, it is: {image_format}", style=warning_color)
		if image_mode != 'RGB':
			console.print(f"  WARNING: image is not mode RGB, it is: {image_mode}", style=warning_color)

		student_entry['128-bit MD5 Hash'] = md5hash
		student_entry['Perceptual Hash'] = phash
		student_entry['Original Filename'] = filename
		student_entry['Image Format'] = image_format
		student_entry['Consensus Background Color'] = named_corner_pixels_dict['consensus']

		# Specify the output filename
		output_filename = student_entry['Student ID']
		output_filename += "-" + student_entry['First Name'].replace(' ','_')
		output_filename += "_" + student_entry['Last Name'].replace(' ','_')
		output_filename += "-" + filename.replace(' ','_')
		goodchars = list('-._' + '0123456789'
			+ 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' + 'abcdefghijklmnopqrstuvwxyz')
		new_filename = ""
		for char in output_filename:
			if not char in goodchars:
				new_filename += "_"
			else:
				new_filename += char
		if new_filename:
			output_filename = new_filename
		# Save the image to the file
		student_entry['Output Filename'] = output_filename
		print(filename)
		print(output_filename)
		pil_image.save(output_filename)
		pil_image.close()
		image_data.close()

		if image_hashes['md5'].get(md5hash) is None:
			image_hashes['md5'][md5hash] = output_filename

		if local_image_hashes.get(md5hash) is None:
			local_image_hashes[md5hash] = [output_filename, ]
			local_image_perc_hashes[phash] = output_filename
		else:
			local_image_hashes[md5hash].append(output_filename)

		if named_corner_pixels_dict is None:
			console.print(image_url)
			console.print(test_google_image.normalize_google_drive_url(image_url))
			console.print("  Error with this student's image, color info not found, likely corrupt image")
			sys.exit(1)

		if lower_filename.startswith('screenshot') or lower_filename.startswith('screen_shot'):
			console.print("  \aWARNING: image filename starts with screenshot", style=warning_color)
			student_entry['Warnings'].append("likely screenshot")
		if named_corner_pixels_dict['consensus'] != "White":
			console.print("  WARNING: image does not have White Background", style=warning_color)
			student_entry['Warnings'].append("non-white background")
			if named_corner_pixels_dict['consensus'] is False:
				console.print(named_corner_pixels_dict)
			else:
				console.print(f"  Consensus Color: {named_corner_pixels_dict['consensus']}")
	console.print("=============================")
	console.print("\nChecking Student Images for Matches", style=data_color)
	image_exact_dups = []
	image_similar_dups = []
	for student_entry in student_tree:
		student_id_protein.print_student_info(student_entry)
		student_entry['Exact Match'] = False
		md5hash = student_entry['128-bit MD5 Hash']
		phash = student_entry['Perceptual Hash']
		output_filename = student_entry['Output Filename']
		if len(local_image_hashes.get(md5hash)) > 1:
			oldfilenames = local_image_hashes.get(md5hash)
			report_txt = f'total files matching: {len(oldfilenames)}'
			student_id_protein.print_student_info(student_entry)
			console.print(f"  md5 hash: {md5hash}")
			console.print(f"  \aWARNING: image has been submitted this semester: {report_txt}", style=warning_color)
			student_entry['Warnings'].append(f"exact same image has been submitted this semester: {report_txt}")
			#image_exact_dups.append((output_filename, report_txt))
			student_entry['Exact Match'] = report_txt
		elif image_hashes['md5'].get(md5hash) != output_filename:
			oldfilename = image_hashes['md5'].get(md5hash)
			student_id_protein.print_student_info(student_entry)
			console.print(f"  md5 hash: {md5hash}")
			console.print(f"  \aWARNING: exact same image has been submitted in previous semester: {oldfilename}", style=warning_color)
			student_entry['Warnings'].append("exact same image has been submitted in previous semester")
			image_exact_dups.append((output_filename, oldfilename))
			student_entry['Exact Match'] = oldfilename
		else:
			for old_phash, oldfilename in image_hashes['phash'].items():
				if oldfilename == output_filename:
					continue
				ham_dist = hamming_distance(phash, old_phash)
				if ham_dist < 20:
					student_id_protein.print_student_info(student_entry)
					console.print(f"PHASH COMP: {phash[:8]}  and {old_phash[:8]} distance: {ham_dist}, file: {oldfilename}", style=warning_color)
					image_similar_dups.append((output_filename, oldfilename))
			for local_phash, local_file in local_image_perc_hashes.items():
				if local_file == output_filename:
					continue
				ham_dist = hamming_distance(phash, local_phash)
				if ham_dist < 20:
					student_id_protein.print_student_info(student_entry)
					console.print(f"PHASH COMP: {phash[:8]}  and {local_phash[:8]} distance: {ham_dist}, file: {local_file}", style=warning_color)
					image_similar_dups.append((output_filename, local_file))
				if ham_dist < 1:
					student_entry['Exact Match'] = local_file

	console.print("=============================")
	for md5hash in local_image_hashes.keys():
		if len(local_image_hashes[md5hash]) > 1:
			mytxt = 'open '
			for imgfile in local_image_hashes[md5hash]:
				mytxt += f'{imgfile} '
			console.print(mytxt)
	for t in image_exact_dups:
		console.print(f'exact md5 dup {t}')
	console.print("")
	for t in image_similar_dups:
		console.print(f'sim phash dup {t}')
		console.print(f'open {t[0]} $(find . -name {t[1]})')

		#sys.exit(1)
	console.print('DONE\n\n', style="bright_green")
	return

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

		if validation is None:
			# Obtain the user's input for the initial validation
			extra_desc = student_entry['extra description']
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
