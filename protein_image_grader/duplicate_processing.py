import os
import re
import yaml
from rich.console import Console
from rich.style import Style
from collections import defaultdict

import protein_image_grader.student_id_protein as student_id_protein

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
def get_ruid_prefix(filename: str) -> str:
	"""
	Extract a 9-digit RUID prefix from a filename.

	Args:
		filename: File path or basename.

	Returns:
		The 9-digit RUID string if found, otherwise an empty string.
	"""
	base_name = os.path.basename(filename)
	match = re.match(r'^([0-9]{9})', base_name)
	if match is None:
		return ""
	return match.group(1)

#============================================
def has_same_ruid(filename_a: str, filename_b: str) -> bool:
	"""
	Check if two filenames share the same 9-digit RUID prefix.

	Args:
		filename_a: File path or basename.
		filename_b: File path or basename.

	Returns:
		True when both filenames start with the same 9-digit RUID.
	"""
	ruid_a = get_ruid_prefix(filename_a)
	ruid_b = get_ruid_prefix(filename_b)
	if not ruid_a or not ruid_b:
		return False
	return ruid_a == ruid_b

#============================================
def filter_duplicate_group_by_ruid(dup_image_filenames: set) -> set:
	"""
	Remove duplicate files that share the same RUID prefix.

	Args:
		dup_image_filenames: Set of filenames in a duplicate group.

	Returns:
		Set containing at most one file per RUID, plus any files without a RUID.
	"""
	filtered_group = set()
	seen_ruids = set()
	for filename in sorted(dup_image_filenames):
		ruid = get_ruid_prefix(filename)
		if ruid:
			if ruid in seen_ruids:
				continue
			seen_ruids.add(ruid)
		filtered_group.add(filename)
	return filtered_group

#============================================
def load_image_hashes(file_path: str = 'image_hashes.yml') -> dict:
	"""Load image hashes from a YAML file."""
	"""
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

	if not os.path.isfile(file_path):
		console.print(f"WARNING: image hashes file not found: {file_path}", style=warning_color)
		return {'md5': {}, 'phash': {}}

	with open(file_path, 'r') as f:
		image_hashes = yaml.safe_load(f)
	total_hashes = len(image_hashes['md5']) + len(image_hashes['phash'])
	print(f"Loaded {total_hashes} image hashes from file {file_path}")
	return image_hashes

#============================================
def fill_local_image_hashes(student_tree: list) -> dict:
	"""
	fill the local image hash dictionary
	"""
	"""
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
	total_hashes = 0
	for student_entry in student_tree:
		md5hash = student_entry['128-bit MD5 Hash']
		phash = student_entry['Perceptual Hash']
		output_filename = student_entry['Output Filename']
		local_image_hashes['md5'][md5hash].append(output_filename)
		local_image_hashes['phash'][phash].append(output_filename)
		total_hashes += 1
	print(f"Sorted {total_hashes} image hashes from {len(student_tree)} students")
	return local_image_hashes

#============================================

def dfs(node, graph, visited, component):
	"""Recursive DFS to collect all connected nodes."""
	visited.add(node)
	component.add(node)
	for neighbor in graph[node]:
		if neighbor not in visited:
			dfs(neighbor, graph, visited, component)

def get_non_overlapping_group_sets(list_of_sets):
	"""Builds a graph and finds connected components to get non-overlapping groups."""
	# Step 1: Build the adjacency list (graph)
	graph = defaultdict(set)
	for group_set in list_of_sets:
		for file1 in group_set:
			for file2 in group_set:
				if file1 != file2:
					graph[file1].add(file2)
					graph[file2].add(file1)

	# Step 2: Find connected components using DFS
	visited = set()
	non_overlapping_group_sets = []

	for node in graph:
		if node not in visited:
			component = set()
			dfs(node, graph, visited, component)
			non_overlapping_group_sets.append(component)

	return non_overlapping_group_sets


#============================================
def find_similar_duplicates(student_tree: list, image_hashes: dict, local_image_hashes: dict):
	comparisons = 0

	list_of_sets = []

	for student_entry in student_tree:
		if student_entry.get('Exact Match') is True:
			# no need to do it more than once
			continue
		if student_entry.get('Similar Match') is True:
			# no need to do it more than once
			continue
		student_entry['Similar Match'] = False
		phash = student_entry['Perceptual Hash']
		output_filename = student_entry['Output Filename']
		student_ruid = get_ruid_prefix(output_filename)
		dup_image_filenames = set()
		dup_image_filenames.add(output_filename)
		cutoff = 38
		for old_phash, oldfilename in image_hashes['phash'].items():
			ham_dist = hamming_distance(phash, old_phash)
			comparisons += 1
			if ham_dist < cutoff:
				if student_ruid and has_same_ruid(output_filename, oldfilename):
					continue
				student_entry['Similar Match'] = True
				console.print(f"PHASH CLASH: {phash[:8]} and {old_phash[:8]} distance: {ham_dist}, file: {oldfilename}", style=warning_color)
				dup_image_filenames.add(oldfilename)

		for local_phash, output_filename_list in local_image_hashes['phash'].items():
			if local_phash == phash:
				continue
			ham_dist = hamming_distance(phash, local_phash)
			comparisons += 1
			if ham_dist < cutoff:
				student_entry['Similar Match'] = True
				for local_output_filename in output_filename_list:
					if student_ruid and has_same_ruid(output_filename, local_output_filename):
						continue
					console.print(f"PHASH CLASH: {phash[:8]} and {local_phash[:8]} distance: {ham_dist}", style=warning_color)
					dup_image_filenames.add(local_output_filename)

		dup_image_filenames = filter_duplicate_group_by_ruid(dup_image_filenames)
		if len(dup_image_filenames) == 1:
			student_entry['Similar Match'] = False
			continue
		list_of_sets.append(dup_image_filenames)

		if student_entry['Similar Match'] is True:
			student_entry['Warnings'].append("You have submitted a very similar images to other students, please make your image more unique in the future or could lost points.")

	non_overlapping_group_sets = get_non_overlapping_group_sets(list_of_sets)

	for group_num, group_set in enumerate(non_overlapping_group_sets, start=1):
		print(f"GROUP NUMBER {group_num}")
		open_files = [path for path in sorted(group_set) if os.path.isfile(path)]
		if open_files:
			system_cmd = "open " + ' '.join(open_files)
			print(system_cmd)
			os.system(system_cmd)
		else:
			print("No matching files exist to open for this group")
		validation = student_id_protein.get_input_validation("Are these images exactly the same?", 'yn', question_color)
		if validation == 'y':
			mark_images_as_duplicates(group_set, student_tree)
			continue
		validation = student_id_protein.get_input_validation("Are these images like the basic?", 'yn', question_color)
		if validation == 'y':
			warning_msg = 'Your image was generated by just doing the default. Next time move the protein structure around or change the color, so your image is more unique.'
			mark_images_with_warning(group_set, warning_msg, student_tree)
			continue
		validation = student_id_protein.get_input_validation("Are these images similar enough to warrent a warning?", 'yn', question_color)
		if validation == 'y':
			warning_msg = 'Your image was very similar to another student. Next time move the protein structure around or change the color, so your image is more unique.'
			mark_images_with_warning(group_set, warning_msg, student_tree)
			continue

	print(f"Made {comparisons:,d} comparisons looking for similar images")
	return

#============================================
def find_student_entry_by_filename(output_filename: str, student_tree: list):
		for student_entry in student_tree:
			if student_entry['Output Filename'] != output_filename:
				continue
			return student_entry

#============================================
def find_exact_local_duplicates(student_tree: list, local_image_hashes: dict):
	for student_entry in student_tree:
		if student_entry.get('Exact Match') is True:
			# no need to do it more than once
			continue
		md5hash = student_entry['128-bit MD5 Hash']
		phash = student_entry['Perceptual Hash']
		if (len(local_image_hashes['md5'][md5hash]) == 1
			and len(local_image_hashes['phash'][phash]) == 1):
			student_entry['Exact Match'] = False
			continue
		#duplicate this semester !!
		dup_image_filenames = set()
		for output_filename in local_image_hashes['md5'][md5hash]:
			dup_image_filenames.add(output_filename)
		# just case there are other matches
		for output_filename in local_image_hashes['phash'][phash]:
			dup_image_filenames.add(output_filename)

		dup_image_filenames = filter_duplicate_group_by_ruid(dup_image_filenames)
		if len(dup_image_filenames) == 1:
			student_entry['Exact Match'] = False
			continue
		student_id_protein.print_student_info(student_entry)
		student_entry['Exact Match'] = True
		mark_images_as_duplicates(dup_image_filenames, student_tree)
		system_cmd = "open " + " ".join(sorted(dup_image_filenames))
		#os.system(system_cmd)
		print(system_cmd)

#============================================
def mark_images_with_warning(dup_image_filenames_list, warning_msg, student_tree):
	dup_image_filenames_list = filter_duplicate_group_by_ruid(set(dup_image_filenames_list))
	if len(dup_image_filenames_list) == 1:
		return
	for output_filename in dup_image_filenames_list:
		if not output_filename.startswith("DOWNLOAD_"):
			continue
		dup_student = find_student_entry_by_filename(output_filename, student_tree)
		if dup_student is None:
			continue
		dup_student['Similar Match'] = True
		dup_student['Warnings'].append(warning_msg)
	return

#============================================
def mark_images_as_duplicates(dup_image_filenames_list, student_tree):
	student_names = set()
	dup_image_filenames_list = filter_duplicate_group_by_ruid(set(dup_image_filenames_list))
	if len(dup_image_filenames_list) == 1:
		return
	for output_filename in dup_image_filenames_list:
		if not output_filename.startswith("DOWNLOAD_"):
			continue
		dup_student = find_student_entry_by_filename(output_filename, student_tree)
		dup_student['Exact Match'] = True
		# Format the student's name with first name and initial of the last name
		student_name = f"{dup_student['First Name']} {dup_student['Last Name'][0]}."
		student_names.add(student_name)

	report_txt = "You are one of a group of students that all submitted the same image. "
	report_txt += "Students are welcome to work together, but each student must submit your own unique image. "
	if len(student_names) > 1:
		report_txt += f"These {len(student_names)} students: "
		report_txt += ', '.join(student_names)
		report_txt += " will all receive a grade deduction."
	report_txt += "If you feel this message in error, please email me about it. "


	for output_filename in dup_image_filenames_list:
		dup_student = find_student_entry_by_filename(output_filename, student_tree)
		if dup_student is None:
			continue
		if not 'Warnings' in dup_student:
			dup_student['Warnings'] = []
		dup_student['Warnings'].append(f"exact same image has been submitted this semester: {report_txt}")


#============================================
def find_exact_global_duplicates(student_tree: list, image_hashes: dict):
	for student_entry in student_tree:
		if student_entry.get('Exact Match') is True:
			# no need to do it more than once
			continue
		md5hash = student_entry['128-bit MD5 Hash']
		phash = student_entry['Perceptual Hash']
		archive_md5_file = image_hashes['md5'].get(md5hash)
		archive_phash_file = image_hashes['phash'].get(phash)
		archive_candidates = set()
		if archive_md5_file:
			archive_candidates.add(archive_md5_file)
		if archive_phash_file:
			archive_candidates.add(archive_phash_file)
		if not archive_candidates:
			student_entry['Exact Match'] = False
			continue
		student_output = student_entry.get('Output Filename', '')
		if student_output:
			archive_candidates = {
				filename for filename in archive_candidates
				if not has_same_ruid(student_output, filename)
			}
		if not archive_candidates:
			student_entry['Exact Match'] = False
			continue
		student_entry['Exact Match'] = True
		#duplicate from previous semester !!
		report_txt = "You have submitted an image from a previous year that. "
		report_txt += "You are welcome to work together, but you must submit your own unique image. "
		report_txt += "You will receive a grade deduction for this submission. "
		print(report_txt)
		student_entry['Warnings'].append(f"exact same image has been submitted previous semester: {report_txt}")
		student_entry['Exact Match'] = report_txt
		#system_cmd = "open " + " ".join(image_filenames)
		#os.system(system_cmd)
		#wait for input
		#validation = student_id_protein.get_input_validation("wait", 'yn', question_color)

#============================================
def check_duplicate_images(student_tree: list, params: dict):
	"""Check for duplicate images and log warnings."""

	local_image_hashes = fill_local_image_hashes(student_tree)
	console.print("\nFind EXACT local duplicates", style=data_color)
	find_exact_local_duplicates(student_tree, local_image_hashes)

	image_hashes_yaml = params.get('image_hashes_yaml', 'image_hashes.yml')
	image_hashes = load_image_hashes(image_hashes_yaml)
	console.print("\nFind EXACT global duplicates", style=data_color)
	find_exact_global_duplicates(student_tree, image_hashes)

	console.print("\nFind SIMILAR duplicates", style=data_color)
	find_similar_duplicates(student_tree, image_hashes, local_image_hashes)

	console.print("=============================")
	console.print('DONE\n\n', style="bright_green")
