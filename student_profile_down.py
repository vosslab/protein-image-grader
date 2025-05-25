#!/usr/bin/env python3

# Standard Library
import os
import re
import sys
import csv
import time
import random
import argparse
import urllib.request, urllib.parse, urllib.error

# PIP3 modules
import PIL.Image
import googleapiclient.errors
from pillow_heif import register_heif_opener

#Local
import commonlib
try:
	from tool_scripts import extract_faces
except ImportError:
	pass
from tool_scripts import test_google_image

register_heif_opener()

#google_id = 2

fail_count = 0

# Define the image storage directory
current_year = time.localtime().tm_year
current_month = time.localtime().tm_mon
if 1 <= current_month <= 5:
	semester = "1Spring"
elif 6 <= current_month <= 8:
	semester = "2Summer"
else:
	semester = "3Fall"
image_dir = f"{current_year}_{semester}"
if not os.path.isdir(image_dir):
	os.makedirs(image_dir)

#============================================

def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		dict: Parsed arguments containing CSV filename.
	"""
	parser = argparse.ArgumentParser(description="Generate an HTML profile page from a CSV file.")
	parser.add_argument('-i', '--input', dest='csvfile',
		type=str, required=True, help="Input CSV file")
	parser.add_argument('-x', '--max-students', dest='maxstudents', default=-1,
		type=int, required=False, help="Max Students, used for testings")
	parser.add_argument('-t', '--trim', dest='trim', action='store_true')
	parser.add_argument('--no-trim', dest='trim', action='store_false')
	parser.set_defaults(trim=False)
	parser.add_argument('-r', '--rotate', dest='rotate', action='store_true')
	parser.add_argument('--no-rotate', dest='rotate', action='store_false')
	parser.set_defaults(rotate=False)
	parser.add_argument('-f', '--face', dest='face', action='store_true')
	parser.set_defaults(face=False)

	type_group = parser.add_mutually_exclusive_group(required=True)
	type_group.add_argument(
		'--type', dest='image_type', type=str,
		choices=('students', 'proteins'),
		help='Set the question type: num (numeric) or mc (multiple choice)'
	)
	type_group.add_argument(
		'-s', '--students', dest='image_type', action='store_const', const='students',
		help='Set image type to students'
	)
	type_group.add_argument(
		'-p', '--proteins', dest='image_type', action='store_const', const='proteins',
		help='Set image type to proteins'
	)
	parser.add_argument('--image_number', dest='image_number', default=0,
		type=int, required=False,)

	args = parser.parse_args()
	return args

#============================================

#============================================

def get_image_html_tag(image_url: str, ruid: int, args) -> str:
	"""
	Download image from Google Drive and return an HTML tag linking to the local file.

	Args:
		image_url: Google Drive image URL
		ruid: Record ID for naming
		args

	Returns:
		str: HTML <img> tag(s) for the image
	"""

	# Extract file ID and download image
	file_id = test_google_image.get_file_id_from_google_drive_url(image_url)
	image_data, original_filename = try_download_image(file_id)

	# Prepare filename and save
	filename = format_filename(original_filename, ruid, args)
	filepath = os.path.abspath(os.path.join(image_dir, filename))
	if not os.path.exists(filepath):
		was_saved = download_and_save_image(image_data, filepath)
		if not was_saved:
			return ''
	else:
		print(f"file exists: {filename}")

	# Optionally trim and rotate
	trim_path = None
	if args.trim:
		trim_path = trim_and_save_image(filepath, args.rotate)

	# Optionally extract face
	face_path = None
	if args.face:
		face_path = extract_and_save_face(filepath)

	# Build HTML
	html_tag = f"<img border='3' src='file://{filepath}' height='250' />"
	if args.trim and os.path.isfile(trim_path):
		html_tag += f"<img border='3' src='file://{trim_path}' height='350' />"
	if args.face and os.path.isfile(face_path):
		html_tag += f"<img border='3' src='file://{face_path}' height='450' />"

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
		clib: CommonLib instance for cleaning

	Returns:
		str: Normalized and extended filename
	"""
	clib = commonlib.CommonLib()
	filename = original_filename.lower()
	basename = os.path.splitext(filename)[0]
	basename = clib.cleanName(basename)
	extension = os.path.splitext(filename)[-1]
	if args.image_type == "students":
		filename = f"{ruid}-profile-{basename}{extension}"
	elif args.image_type == "proteins":
		filename = f"{ruid}-protein{args.image_number:02d}-{basename}{extension}"
	else:
		sys.exit(1)
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
def extract_and_save_face(filepath: str) -> str:
	"""
	Extract face from the given image and save cropped result.

	Args:
		filepath: Path to full input image

	Returns:
		str: Path to saved face image, or empty string if none found
	"""
	print(f"detecting face in image: {os.path.basename(filepath)}")
	face_path = os.path.splitext(filepath)[0] + '-face.jpg'
	if os.path.isfile(face_path):
		print(f"[ok] Face image exists: {os.path.basename(face_path)}")
		return face_path
	success = extract_faces.process_image(filepath, face_path)

	if success and os.path.isfile(face_path):
		print(f"[ok] Face image saved: {os.path.basename(face_path)}")
		return face_path
	else:
		print(f"[fail] Face did not work")
		# Remove file if created but face was not found
		if os.path.isfile(face_path):
			os.remove(face_path)
		return ''

#============================================

def write_header(output, filename: str):
	"""
	Write the HTML header to the output file.
	"""
	# Extract the title from the filename
	title = os.path.splitext(filename)[0].title()

	# Write the HTML opening tags and title
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
	# Search for "First Name" in the header row
	for i, item in enumerate(header):
		sitem = item.strip().lower()
		if 'first' in sitem and 'name' in sitem:
			return i

	# Backup check for "Full Name"
	for i, item in enumerate(header):
		sitem = item.strip().lower()
		if 'full' in sitem and 'name' in sitem:
			return i

	# Return None if no valid column is found
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
	# Check if the file exists
	if not os.path.exists(csvfile):
		raise ValueError(f"Error: File '{csvfile}' does not exist.")

	data_tree = []
	first_name_key_index = None

	# Open and read the CSV file
	with open(csvfile, "r") as f:
		data = csv.reader(f)
		header = None

		# Process each row in the CSV file
		for row in data:
			if header is None:
				header = row
				first_name_key_index = find_first_name_key_index_from_header(header)
				continue
			data_tree.append(row)
			if maxstudents > 0 and len(data_tree) >= maxstudents:
				break

	# Attempt to sort the data by the first name column
	data_tree.sort(key=lambda x: x[first_name_key_index].lower().strip())

	return header, data_tree

def extract_number_in_range(s: str) -> int:
	"""Extract the first integer between 1 and 20 (inclusive) from the string.

	Args:
		s: The input string which may contain digits.

	Returns:
		The integer if found, otherwise raises ValueError.
	"""
	# Find all 1 or 2 digit numbers
	matches = re.findall(r'\d{1,2}', s)
	for match in matches:
		num = int(match)
		if 1 <= num <= 20:
			return num
	print(f"No number in range 1-20 found in string: {s}")
	sys.exit(1)

#============================================

def generate_html(csvfile: str, header: list, data_tree: list, args):
	"""
	Generate an HTML file based on the CSV data.
	"""
	# Define the output HTML filename
	output_filename = "profiles.html"
	if args.image_type == "proteins":
		args.image_number = extract_number_in_range(csvfile)

	# Open the output file and write the HTML content
	with open(output_filename, "w") as output:
		write_header(output, csvfile)
		count = 0

		# Process each row and generate HTML content
		for row in data_tree:
			count += 1
			ruid = None

			# Insert a page break for multiple profiles
			if count > 1:
				output.write('<br/><p style="page-break-before: always"><br/></p>\n')

			# Process each column in the row
			for i, item in enumerate(row):
				# Skip empty fields
				if len(item) < 1:
					continue
				elif item.startswith('900') or item.startswith('960'):
					ruid = int(item)
				# Process URLs as images
				elif item.startswith('http'):
					img_html_tag = get_image_html_tag(item, ruid, args)
					output.write(f"{img_html_tag}\n")
				# Regular text fields
				else:
					output.write(f"<p><b>{header[i].strip()}</b>:&nbsp; {row[i].strip()}</p>\n")

#============================================

def open_html_in_browser():
	"""
	Open the generated HTML file in a web browser.
	"""
	#cmd = "open -a /Applications/Firefox.app profiles.html"
	#cmd = "open profiles.html"
	#proc = subprocess.Popen(cmd, shell=True)
	#proc.communicate()
	os.system("open profiles.html")

#============================================

def main():
	"""
	Main function to parse arguments and process the CSV file.
	"""
	# Parse command-line arguments
	args = parse_args()

	# Read the CSV file
	header, data_tree = read_csv(args.csvfile, args.maxstudents)

	# Generate the HTML file
	generate_html(args.csvfile, header, data_tree, args)

	# Open the generated HTML file in the browser
	open_html_in_browser()

#============================================

if __name__ == '__main__':
	main()
