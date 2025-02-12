import os
import sys
import yaml
from rich.console import Console
from rich.style import Style
from collections import defaultdict

from tool_scripts import test_google_image
from tool_scripts import student_id_protein

console = Console()
warning_color = Style(color="rgb(255, 187, 51)")  # RGB for bright orange
question_color = Style(color="rgb(100, 149, 237)" )  # RGB for cornflower blue
data_color = Style(color="rgb(187, 51, 255)")  # RGB for purple

#============================================
def hex_to_bin(hex_string: str) -> str:
	"""Convert a hex string to its binary representation."""
	bin_string = bin(int(hex_string, 16))[2:].zfill(len(hex_string) * 4)
	return bin_string

#============================================
def hamming_distance(s1: str, s2: str) -> int:
	"""Calculate the Hamming distance between two binary strings."""
	if len(s1) != len(s2):
		raise ValueError("Strings must be of the same length")
	distance = sum(ch1 != ch2 for ch1, ch2 in zip(s1, s2))
	return distance

#============================================
def load_image_hashes(file_path: str = 'image_hashes.yml') -> dict:
	"""Load image hashes from a YAML file."""
	with open(file_path, 'r') as f:
		image_hashes = yaml.safe_load(f)
	return image_hashes

#============================================
def fill_local_image_hashes(student_tree: list, image_hashes: dict) -> dict:
	"""
	fill the local image hash dictionary
	we will focus on matches later

	(!!!) important note:
		this is based on old images from past semesters
		image_hashes has two keys md5 and phash that point to a dict
			both the md5 and phash dict consist of
				key: the hash and
				value: a filename to compare
		local_image_hashes also has two keys md5 and phash that point to a dict
			this is based on current images submitted for this assignment
			both the md5 and phash dict consist of
				key: the hash and
				value: a LIST of filenames to compare
	so local maintains a list, whereas a image_hash
	"""
	local_image_hashes = {}
	local_image_hashes['md5'] = defaultdict(list)
	local_image_hashes['phash'] = defaultdict(list)
	for student_entry in student_tree:
		md5hash = student_entry['128-bit MD5 Hash']
		phash = student_entry['Perceptual Hash']
		local_image_hashes['md5'][md5hash].append(student_entry)
		local_image_hashes['phash'][phash].append(student_entry)
	return local_image_hashes

#============================================
def find_file_path(filename):
	pass

#============================================
def check_duplicate_images(student_tree: list, params: dict):
	"""Check for duplicate images and log warnings."""
	image_hashes = load_image_hashes()
	local_image_hashes = fill_local_image_hashes(student_tree, image_hashes)

	# doing multiple passes so the code is easier to read
	image_exact_dups = []
	#first pass exact duplicates
	for student_entry in student_tree:
		student_id_protein.print_student_info(student_entry)
		md5hash = student_entry['128-bit MD5 Hash']
		phash = student_entry['Perceptual Hash']
		if len(local_image_hashes.get(md5hash, [])) > 1:
			#duplicate this semester !!
			report_txt = "You are one of a group of students that all submitted the same image. "
			report_txt = "You are welcome to work together, but you must submit your own unique image. "
			print(f"List of students this semester with same submission: {md5hash}")
			student_names = set()
			image_filenames = set()
			for dup_student in local_image_hashes['md5'][md5hash]:
				student_id_protein.print_student_info(dup_student)
				# Format the student's name with first name and initial of the last name
				student_name = f"{dup_student['First Name']} {dup_student['Last Name'][0]}."
				student_names.add(student_name)
				image_filenames.add(dup_student['Output Filename'])
			# just case there are other matches
			for dup_student in local_image_hashes['phash'][phash]:
				student_id_protein.print_student_info(dup_student)
				# Format the student's name with first name and initial of the last name
				student_name = f"{dup_student['First Name']} {dup_student['Last Name'][0]}."
				student_names.add(student_name)
				image_filenames.add(dup_student['Output Filename'])
			report_txt = "Students: "
			report_txt = ' '.join(student_names)
			report_txt = "will all receive a point deduction."
			student_entry['Warnings'].append(f"exact same image has been submitted this semester: {report_txt}")
			student_entry['Exact Match'] = report_txt
			system_cmd = "open "
			for image_filename in image_filenames:
				image_path = os.path.join(params['image_folder'], image_filename)
				system_cmd += image_path + " "
			os.system(system_cmd)
			#wait for input
			validation = student_id_protein.get_input_validation("wait", 'yn', question_color)

	image_similar_dups = []
	#second pass similar duplicates

	"""
	student_entry['Exact Match'] = False


	if len(local_image_hashes.get(md5hash, [])) > 1:
		oldfilenames = local_image_hashes.get(md5hash)
		report_txt = f'total files matching: {len(oldfilenames)}'
		console.print(f"  \aWARNING: image has been submitted this semester: {report_txt}", style=warning_color)
		student_entry['Warnings'].append(f"exact same image has been submitted this semester: {report_txt}")
		student_entry['Exact Match'] = report_txt
	elif image_hashes['md5'].get(md5hash) != output_filename:
		oldfilename = image_hashes['md5'].get(md5hash)
		console.print(f"  \aWARNING: exact same image has been submitted in previous semester: {oldfilename}", style=warning_color)
		student_entry['Warnings'].append("exact same image has been submitted in previous semester")
		image_exact_dups.append((output_filename, oldfilename))
		student_entry['Exact Match'] = oldfilename
	"""

	console.print("=============================")
	console.print('DONE\n\n', style="bright_green")

#==========================================

def null():
	if True:
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
