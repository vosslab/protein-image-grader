#!/usr/bin/env python3

# Standard Library
import os
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
	args = parser.parse_args()
	return args

#============================================

def get_image_html_tag(image_url: str, ruid: int, trim: bool=False, rotate: bool= False) -> str:
	"""
	Download image from Google Drive and return an HTML tag linking to the local file.
	"""
	clib = commonlib.CommonLib()
	print(image_url)
	# Extract file ID from the Google Drive URL
	file_id = test_google_image.get_file_id_from_google_drive_url(image_url)
	print(file_id)
	# Attempt to download the image
	global fail_count
	try:
		image_data, original_filename = test_google_image.download_image(file_id)
	except googleapiclient.errors.HttpError as e:
		fail_count += 1
		# Print error message and wait before retrying
		print(f"Error downloading image: {e}")
		time.sleep(random.random())  # Prevent server overload
		print("check permissions of the folder for vosslab-12389@protein-images.iam.gserviceaccount.com")
		if fail_count > 2:
			raise ValueError
		return ''
	print(original_filename)
	filename = original_filename.lower()
	basename = os.path.splitext(filename)[0]
	basename = clib.cleanName(basename)
	extension = os.path.splitext(filename)[-1]
	filename = f"{ruid}-{basename}{extension}"
	# Ensure the file has a valid image extension
	if not filename.endswith('.jpg') and not filename.endswith('.png'):
		filename = os.path.splitext(filename)[0] + '.jpg'
	global image_dir
	# Create the directory if it does not exist
	if not os.path.isdir(image_dir):
		os.makedirs(image_dir)
	#print(filename)
	if trim is True:
		trim_file = os.path.splitext(filename)[0] + '-trim.jpg'
		trim_path = os.path.abspath(os.path.join(image_dir, trim_file))
	# Create the absolute file path
	filepath = os.path.abspath(os.path.join(image_dir, filename))
	# Save the image locally if it does not already exist
	if not os.path.isfile(filename):
		pil_image = PIL.Image.open(image_data)
		pil_image.save(filepath)
		print(f"saved {filename}")
		if trim is True:
			trimmed_image = test_google_image.multi_trim(pil_image, 1)
			if rotate is True:
				trimmed_image = test_google_image.rotate_if_tall(trimmed_image)
			if trimmed_image.mode == 'RGBA' and trim_path.endswith('.jpg'):
				trimmed_image = trimmed_image.convert('RGB')
			trimmed_image.save(trim_path)
			print(f"saved {trim_file}")
		try:
			os.remove(original_filename)
		except FileNotFoundError:
			pass
	# Generate an HTML <img> tag with the local file path
	html_tag = f"<img border='3' src='file://{filepath}' height='250' />"
	if trim is True:
		html_tag += f"<img border='1' src='file://{trim_path}' height='350' />"
	print('')
	return html_tag

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
		print(f"Error: File '{csvfile}' does not exist.")
		sys.exit(1)

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

#============================================

def generate_html(csvfile: str, header: list, data_tree: list, trim: bool=False, rotate: bool=False):
	"""
	Generate an HTML file based on the CSV data.

	Args:
		csvfile (str): Path to the original CSV file.
		header (list): The header row from the CSV file.
		data_tree (list): Sorted list of CSV data rows.
	"""
	# Define the output HTML filename
	output_filename = "profiles.html"

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
					img_html_tag = get_image_html_tag(item, ruid, trim, rotate)
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
	generate_html(args.csvfile, header, data_tree, args.trim, args.rotate)

	# Open the generated HTML file in the browser
	open_html_in_browser()

#============================================

if __name__ == '__main__':
	main()
