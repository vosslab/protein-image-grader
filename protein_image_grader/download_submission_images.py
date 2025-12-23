#!/usr/bin/env python3

# Standard Library
import os
import re
import sys
import csv
import time
import random
import shutil
import argparse

# PIP3 modules
import PIL.Image
import googleapiclient.errors
from pillow_heif import register_heif_opener
import yaml

# local repo modules
import protein_image_grader.commonlib as commonlib
import protein_image_grader.test_google_image as test_google_image

register_heif_opener()

fail_count = 0

#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		args: Parsed arguments
	"""
	parser = argparse.ArgumentParser(description="Download submission images and build an HTML review page.")
	parser.add_argument('-i', '--input', dest='csvfile',
		type=str, required=True, help="Input CSV file")
	parser.add_argument('-x', '--max-students', dest='maxstudents', default=-1,
		type=int, required=False, help="Max Students, used for testing")
	parser.add_argument('-t', '--trim', dest='trim', action='store_true')
	parser.add_argument('--no-trim', dest='trim', action='store_false')
	parser.set_defaults(trim=False)
	parser.add_argument('-r', '--rotate', dest='rotate', action='store_true')
	parser.add_argument('--no-rotate', dest='rotate', action='store_false')
	parser.set_defaults(rotate=False)
	parser.add_argument('-o', '--output-dir', dest='output_dir', type=str,
		help="Output directory for downloads and HTML", default="data/runs")
	parser.add_argument('-p', '--profiles-html', dest='profiles_html', type=str,
		help="Output HTML file name", default=None)
	parser.add_argument('--image-number', dest='image_number', default=0,
		type=int, required=False)
	args = parser.parse_args()
	return args

#============================================
def build_image_dir(image_number: int, output_dir: str) -> str:
	"""
	Build the output directory for downloaded images.

	Args:
		image_number (int): Protein image number.

	Returns:
		str: Output folder name.
	"""
	current_year = time.localtime().tm_year
	if image_number > 0:
		return os.path.join(output_dir, f"DOWNLOAD_{image_number:02d}_year_{current_year:04d}")
	return os.path.join(output_dir, f"DOWNLOAD_images_year_{current_year:04d}")

#============================================
def get_image_html_tag(image_url: str, ruid: int, args, image_dir: str,
		archive_dir: str, image_hashes: dict, hashes_changed: list) -> str:
	"""
	Download image from Google Drive and return an HTML tag linking to the local file.

	Args:
		image_url: Google Drive image URL
		ruid: Record ID for naming
		args: Parsed arguments
		image_dir: Output image directory

	Returns:
		str: HTML <img> tag(s) for the image
	"""
	file_id = test_google_image.get_file_id_from_google_drive_url(image_url)
	image_data, original_filename = try_download_image(file_id)
	if image_data is None:
		return ''

	filename = format_filename(original_filename, ruid, args)
	filepath = os.path.abspath(os.path.join(image_dir, filename))
	if not os.path.exists(filepath):
		was_saved = download_and_save_image(image_data, filepath)
		if not was_saved:
			return ''
	else:
		print(f"file exists: {filename}")

	archive_path = archive_image_if_needed(filepath, archive_dir)
	if archive_path and image_hashes is not None:
		with open(archive_path, 'rb') as f:
			md5hash, phash = test_google_image.get_hash_data(f)
		hashes_changed[0] = update_image_hashes(
			image_hashes, md5hash, phash, archive_path
		) or hashes_changed[0]

	trim_path = None
	if args.trim:
		trim_path = trim_and_save_image(filepath, args.rotate)

	html_tag = f"<img border='3' src='file://{filepath}' height='250' />"
	if args.trim and os.path.isfile(trim_path):
		html_tag += f"<img border='3' src='file://{trim_path}' height='350' />"

	print('')
	return html_tag

#============================================
def try_download_image(file_id: str) -> tuple:
	"""
	Try downloading an image using service account.

	Args:
		file_id: Google Drive file ID

	Returns:
		tuple: (image data stream, original filename)
	"""
	global fail_count
	try:
		image_data, original_filename = test_google_image.download_image(file_id)
		return image_data, original_filename
	except googleapiclient.errors.HttpError as e:
		fail_count += 1
		print(f"Error downloading image: {e}")
		time.sleep(random.random())
		print("check permissions of the folder for vosslab-12389@protein-images.iam.gserviceaccount.com")
		if fail_count > 2:
			raise ValueError
		return None, ''

#============================================
def format_filename(original_filename: str, ruid: int, args) -> str:
	"""
	Clean and normalize the filename for saving.

	Args:
		original_filename: Original filename
		ruid: Record ID
		args: Parsed arguments

	Returns:
		str: Normalized and extended filename
	"""
	clib = commonlib.CommonLib()
	filename = original_filename.lower()
	basename = os.path.splitext(filename)[0]
	basename = clib.cleanName(basename)
	extension = os.path.splitext(filename)[-1]
	filename = f"{ruid}-protein{args.image_number:02d}-{basename}{extension}"
	if not filename.endswith('.jpg') and not filename.endswith('.png'):
		filename = os.path.splitext(filename)[0] + '.jpg'
	return filename

#============================================
def download_and_save_image(image_data, filepath: str) -> bool:
	"""
	Save the downloaded image if not already present.

	Args:
		image_data: BytesIO image stream
		filepath: Full path to save the image

	Returns:
		bool: True if saved, False if already existed
	"""
	if os.path.isfile(filepath):
		return False
	pil_image = PIL.Image.open(image_data)
	pil_image.save(filepath)
	print(f"saved {os.path.basename(filepath)}")
	return True

#============================================
def archive_image_if_needed(filepath: str, archive_dir: str) -> str:
	"""
	Copy a saved image into the archive folder if it is not already there.
	"""
	if archive_dir is None:
		return None
	if not os.path.isfile(filepath):
		return None
	if not os.path.isdir(archive_dir):
		os.makedirs(archive_dir)
	archive_path = os.path.join(archive_dir, os.path.basename(filepath))
	if os.path.isfile(archive_path):
		return archive_path
	shutil.copy2(filepath, archive_path)
	return archive_path

#============================================
def trim_and_save_image(filepath: str, rotate: bool=False) -> str:
	"""
	Trim borders and optionally rotate the image, then save.

	Args:
		filepath: Original image path
		rotate: Whether to rotate tall images

	Returns:
		str: Path to trimmed image
	"""
	pil_image = PIL.Image.open(filepath)
	trimmed_image = test_google_image.multi_trim(pil_image, 1)
	if rotate:
		trimmed_image = test_google_image.rotate_if_tall(trimmed_image)
	if trimmed_image.mode != 'RGB':
		trimmed_image = trimmed_image.convert('RGB')
	trim_path = os.path.splitext(filepath)[0] + '-trim.jpg'
	trimmed_image.save(trim_path)
	print(f"saved {os.path.basename(trim_path)}")
	return trim_path

#============================================
def write_header(output, filename: str):
	"""
	Write the HTML header to the output file.
	"""
	title = os.path.splitext(filename)[0].title()
	output.write("<html><head>\n")
	output.write(f"<title>{title}</title>\n")
	output.write("</head><body>\n")

#============================================
def find_first_name_key_index_from_header(header: list) -> int:
	"""
	Find the index of the "First Name" or "Full Name" column.

	Args:
		header (list): List of CSV header values.

	Returns:
		int: Index of the first name column, or None if not found.
	"""
	for i, item in enumerate(header):
		sitem = item.strip().lower()
		if 'first' in sitem and 'name' in sitem:
			return i
	for i, item in enumerate(header):
		sitem = item.strip().lower()
		if 'full' in sitem and 'name' in sitem:
			return i
	return None

#============================================
def read_csv(csvfile: str, maxstudents: int) -> tuple:
	"""
	Read the CSV file and extract the data into a list.

	Args:
		csvfile (str): Path to the CSV file.

	Returns:
		tuple: (header row, sorted data list, first name key index)
	"""
	if not os.path.exists(csvfile):
		raise ValueError(f"Error: File '{csvfile}' does not exist.")

	data_tree = []
	first_name_key_index = None

	with open(csvfile, "r") as f:
		data = csv.reader(f)
		header = None
		for row in data:
			if header is None:
				header = row
				first_name_key_index = find_first_name_key_index_from_header(header)
				continue
			data_tree.append(row)
			if maxstudents > 0 and len(data_tree) >= maxstudents:
				break

	data_tree.sort(key=lambda x: x[first_name_key_index].lower().strip())
	return header, data_tree

#============================================
def extract_number_in_range(s: str) -> int:
	"""
	Extract the first integer between 1 and 20 (inclusive) from the string.
	"""
	matches = re.findall(r'\d{1,2}', s)
	for match in matches:
		num = int(match)
		if 1 <= num <= 20:
			return num
	print(f"No number in range 1-20 found in string: {s}")
	sys.exit(1)

#============================================
def get_term_from_month(month: int) -> str:
	"""
	Map month to term label.
	"""
	if 1 <= month <= 5:
		return "1Spring"
	if 6 <= month <= 8:
		return "2Summer"
	return "3Fall"

#============================================
def get_archive_assignment_dir(image_number: int, spec_dir: str) -> str:
	"""
	Build the archive assignment directory path.
	"""
	current_year = time.localtime().tm_year
	current_term = get_term_from_month(time.localtime().tm_mon)
	archive_session_dir = os.path.join("archive", f"{current_year}_{current_term}")
	archive_images_dir = os.path.join(archive_session_dir, "ARCHIVE_IMAGES")

	assignment_name = None
	spec_yaml = os.path.join(spec_dir, f"protein_image_{image_number:02d}.yml")
	if os.path.isfile(spec_yaml):
		with open(spec_yaml, 'r') as f:
			config = yaml.safe_load(f)
			assignment_name = config.get('assignment name', None)

	assignment_dir = f"BCHM_Prot_Img_{image_number:02d}"
	if assignment_name:
		clib = commonlib.CommonLib()
		clean_name = clib.cleanName(assignment_name)
		if clean_name:
			assignment_dir = f"{assignment_dir}_{clean_name}"

	return os.path.join(archive_images_dir, assignment_dir)

#============================================
def load_image_hashes(image_hashes_yaml: str) -> dict:
	"""
	Load image hashes from YAML or initialize an empty structure.
	"""
	if image_hashes_yaml is None:
		return {'md5': {}, 'phash': {}}
	if not os.path.isfile(image_hashes_yaml):
		return {'md5': {}, 'phash': {}}
	with open(image_hashes_yaml, 'r') as f:
		image_hashes = yaml.safe_load(f)
	if image_hashes is None:
		return {'md5': {}, 'phash': {}}
	if image_hashes.get('md5') is None:
		image_hashes['md5'] = {}
	if image_hashes.get('phash') is None:
		image_hashes['phash'] = {}
	return image_hashes

#============================================
def update_image_hashes(image_hashes: dict, md5hash: str, phash: str,
		archive_path: str) -> bool:
	"""
	Update image hash dictionaries with a new entry.
	"""
	changed = False
	if md5hash and image_hashes['md5'].get(md5hash) is None:
		image_hashes['md5'][md5hash] = archive_path
		changed = True
	if phash and image_hashes['phash'].get(phash) is None:
		image_hashes['phash'][phash] = archive_path
		changed = True
	return changed

#============================================
def generate_html(csvfile: str, header: list, data_tree: list, args, image_dir: str,
		archive_dir: str, output_html: str, image_hashes: dict, hashes_changed: list):
	"""
	Generate an HTML file based on the CSV data.
	"""
	if args.image_number == 0:
		args.image_number = extract_number_in_range(csvfile)

	with open(output_html, "w") as output:
		write_header(output, csvfile)
		count = 0

		for row in data_tree:
			count += 1
			ruid = None

			if count > 1:
				output.write('<br/><p style="page-break-before: always"><br/></p>\n')

			for i, item in enumerate(row):
				if len(item) < 1:
					continue
				elif item.startswith('900') or item.startswith('960'):
					ruid = int(item)
				elif item.startswith('http'):
					img_html_tag = get_image_html_tag(
						item, ruid, args, image_dir, archive_dir, image_hashes, hashes_changed
					)
					output.write(f"{img_html_tag}\n")
				else:
					output.write(f"<p><b>{header[i].strip()}</b>:&nbsp; {row[i].strip()}</p>\n")

#============================================
def open_html_in_browser(html_path: str):
	"""
	Open the generated HTML file in a web browser.
	"""
	os.system(f"open {html_path}")

#============================================
def write_html_from_student_tree(student_tree: list, output_html: str) -> None:
	"""
	Write an HTML file using a student_tree list that already includes output filenames.
	"""
	output_dir = os.path.dirname(output_html)
	if output_dir and not os.path.isdir(output_dir):
		os.makedirs(output_dir)

	with open(output_html, "w") as output:
		write_header(output, output_html)
		count = 0
		for student_entry in student_tree:
			count += 1
			if count > 1:
				output.write('<br/><p style="page-break-before: always"><br/></p>\n')

			student_id = student_entry.get('Student ID', '')
			first_name = student_entry.get('First Name', '')
			last_name = student_entry.get('Last Name', '')
			original_filename = student_entry.get('Original Filename', '')
			output_filename = student_entry.get('Output Filename', '')
			if output_filename:
				image_path = os.path.abspath(output_filename)
				output.write(f"<img border='3' src='file://{image_path}' height='350' />\n")

			if student_id:
				output.write(f"<p><b>Student ID</b>:&nbsp; {student_id}</p>\n")
			if first_name or last_name:
				output.write(f"<p><b>Student</b>:&nbsp; {first_name} {last_name}</p>\n")
			if original_filename:
				output.write(f"<p><b>Original Filename</b>:&nbsp; {original_filename}</p>\n")
	return

#============================================
def main():
	"""
	Main function to parse arguments and process the CSV file.
	"""
	args = parse_args()

	if not os.path.isdir(args.output_dir):
		os.makedirs(args.output_dir)

	header, data_tree = read_csv(args.csvfile, args.maxstudents)

	if args.image_number == 0:
		args.image_number = extract_number_in_range(args.csvfile)
	image_dir = build_image_dir(args.image_number, args.output_dir)
	if not os.path.isdir(image_dir):
		os.makedirs(image_dir)

	if args.profiles_html is None:
		args.profiles_html = os.path.join(
			args.output_dir, f"profiles_image_{args.image_number:02d}.html")

	archive_dir = get_archive_assignment_dir(args.image_number, "spec_yaml_files")

	image_hashes_yaml = os.path.join("archive", "image_hashes.yml")
	image_hashes = load_image_hashes(image_hashes_yaml)
	hashes_changed = [False]

	generate_html(args.csvfile, header, data_tree, args, image_dir, archive_dir,
		args.profiles_html, image_hashes, hashes_changed)
	open_html_in_browser(args.profiles_html)
	if hashes_changed[0]:
		with open(image_hashes_yaml, 'w') as f:
			yaml.dump(image_hashes, f)

#============================================
if __name__ == '__main__':
	main()
