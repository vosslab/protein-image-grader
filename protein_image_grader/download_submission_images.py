#!/usr/bin/env python3

# Standard Library
import os
import re
import sys
import csv
import time
import random
import argparse

# PIP3 modules
import PIL.Image
import googleapiclient.errors
from pillow_heif import register_heif_opener

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
	parser.add_argument("--year", dest="year", type=int,
		help="Year for grouping outputs", default=0)
	parser.add_argument("--term", dest="term", type=str,
		choices=("1Spring", "2Summer", "3Fall"),
		help="Term for grouping outputs", default=None)
	parser.add_argument("--session", dest="session", type=str,
		help="Session label override", default=None)
	parser.add_argument('--session-dir', dest='use_session_dir',
		help='Organize outputs by session subfolder', action='store_true')
	parser.add_argument('--no-session-dir', dest='use_session_dir',
		help='Do not organize outputs by session subfolder', action='store_false')
	parser.set_defaults(use_session_dir=True)
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
def get_image_html_tag(image_url: str, ruid: int, args, image_dir: str) -> str:
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
def generate_html(csvfile: str, header: list, data_tree: list, args, image_dir: str,
		output_html: str):
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
					img_html_tag = get_image_html_tag(item, ruid, args, image_dir)
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
def main():
	"""
	Main function to parse arguments and process the CSV file.
	"""
	args = parse_args()

	year = args.year
	term = args.term
	session = args.session

	if year == 0:
		year = time.localtime().tm_year
	if term is None:
		term = get_term_from_month(time.localtime().tm_mon)
	if session is None:
		session = f"{year}_{term}"
	if args.use_session_dir:
		args.output_dir = os.path.join(args.output_dir, session)

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

	generate_html(args.csvfile, header, data_tree, args, image_dir, args.profiles_html)
	open_html_in_browser(args.profiles_html)

#============================================
if __name__ == '__main__':
	main()
