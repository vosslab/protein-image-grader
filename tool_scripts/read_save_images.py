#!/usr/bin/env python3

import os
import sys
import glob
import commonlib
from rich.console import Console
from rich.style import Style
from PIL import Image
from tool_scripts import test_google_image
from tool_scripts import student_id_protein

console = Console()
warning_color = Style(color="rgb(255, 187, 51)")  # RGB for bright orange
data_color = Style(color="rgb(187, 51, 255)")  # RGB for purple

download_count = 0

#============================================
def get_image_data(student_entry: dict, params: dict):
	"""Download or load an image from cache, ensuring consistency."""
	global download_count
	clib = commonlib.CommonLib()

	image_url = student_entry.get('image url')
	if image_url is None:
		console.print("  \aError: Image URL not found", style="bright_red")
		sys.exit(1)
	output_filename_prefix = (
		f"{student_entry['Student ID']}-"
		f"{student_entry['First Name'].lower().replace(' ', '_')}_"
		f"{student_entry['Last Name'].lower().replace(' ', '_')}-"
	)
	output_filename_prefix = os.path.join(params['image_folder'], output_filename_prefix)

	file_search = glob.glob(output_filename_prefix+"*")
	image_data = None
	output_filename = None
	original_filename = None

	if len(file_search) == 0:
		file_id = test_google_image.get_file_id_from_google_drive_url(image_url)
		image_data, original_filename = test_google_image.download_image(file_id)
		download_count += 1
		print(f"original_filename = {original_filename}")
		filename = original_filename.lower()
		basename = os.path.splitext(filename)[0]
		basename = clib.cleanName(basename)
		extension = os.path.splitext(filename)[-1]
		output_filename = f"{output_filename_prefix}{basename}{extension}"
		print(f"output_filename = {output_filename}")

	elif len(file_search) > 1:
		raise ValueError(f"Too many matches for file {output_filename_prefix}")

	else:
		output_filename = file_search[0]
		original_filename = output_filename[len(output_filename_prefix):]
		print(f"Found file {output_filename}")
		image_data = open(output_filename, 'rb')

	return image_data, original_filename, output_filename

#============================================
def create_image_dict(image_data, original_filename, output_filename):
	"""Process image metadata and create a dictionary of attributes."""
	named_corner_pixels_dict = test_google_image.inspect_image_data(image_data)
	if named_corner_pixels_dict is None:
		console.print("  Error: Image metadata not found, possibly corrupt file.")
		raise ValueError

	md5hash, phash = test_google_image.get_hash_data(image_data)
	image_data.seek(0)
	pil_image = Image.open(image_data)

	image_format = pil_image.format
	image_mode = pil_image.mode

	if image_format is None:
		console.print("  \aError: Image format not found, possibly permission issue.", style="bright_red")
		raise TypeError

	if image_format != 'PNG':
		console.print(f"  WARNING: image is not type PNG, it is: {image_format}", style=warning_color)
	if image_mode != 'RGB':
		console.print(f"  WARNING: image is not mode RGB, it is: {image_mode}", style=warning_color)

	image_dict = {
		'pil_image': pil_image,
		'original_filename': original_filename,
		'output_filename': output_filename,
		'image_format': image_format,
		'image_mode': image_mode,
		'phash': phash,
		'md5hash': md5hash,
		'named_corner_pixels_dict': named_corner_pixels_dict
	}

	return image_dict

#============================================
def download_and_process_image(student_entry: dict, params: dict) -> dict:
	"""Wrapper function to download/load an image and process it."""
	image_data, original_filename, output_filename = get_image_data(student_entry, params)
	image_dict = create_image_dict(image_data, original_filename, output_filename)

	student_entry.update({
		'Original Filename': original_filename,
		'Output Filename': output_filename,
		'128-bit MD5 Hash': image_dict['md5hash'],
		'Perceptual Hash': image_dict['phash'],
		'Image Format': image_dict['image_format'],
		'Consensus Background Color': image_dict['named_corner_pixels_dict']['consensus']
	})

	return image_dict

#============================================
def generate_output_filename(student_entry: dict, filename: str, params: dict) -> str:
	"""Generate a sanitized output filename for the student's image."""
	clib = commonlib.CommonLib()

	# Convert filename to lowercase
	filename = filename.lower()

	# Raise an error if filename starts with "download_"
	if filename.startswith("download_"):
		raise ValueError

	# Clean filename and extract extension
	basename = os.path.splitext(filename)[0]
	basename = clib.cleanName(basename)
	extension = os.path.splitext(filename)[-1]

	# Construct the output filename
	output_filename = (
		f"{student_entry['Student ID']}-"
		f"{student_entry['First Name'].replace(' ', '_')}_"
		f"{student_entry['Last Name'].replace(' ', '_')}-"
		f"{basename}{extension}"
	)

	# Ensure filename contains only allowed characters
	goodchars = set('-._0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
	output_filename = ''.join(c if c in goodchars else '_' for c in output_filename)

	# Construct full file path
	output_filename = os.path.join(params['image_folder'], output_filename)

	return output_filename

#============================================
def save_image(image_dict: dict, output_filename: str):
	"""Save the processed image to a file."""
	print(f"Saved image to {output_filename}")
	image_dict['pil_image'].save(output_filename)
	image_dict['pil_image'].close()

#============================================
def read_and_save_student_images(student_tree: list, params: dict) -> None:
	"""Process student images, checking for duplicates and updating student entries."""
	global console
	global download_count

	skip_count = 0
	processed_count = 0
	for student_entry in student_tree:
		# Skip if image format already exists
		if student_entry.get("Image Format") is not None:
			skip_count += 1
			continue

		processed_count += 1
		student_id_protein.print_student_info(student_entry)
		image_dict = download_and_process_image(student_entry, params)

		console.print(f"Processing image: {image_dict['original_filename']}")

		# Ensure the image is saved if it's new
		if not os.path.exists(image_dict['output_filename']):
			save_image(image_dict, image_dict['output_filename'])

	console.print("=============================")
	console.print(f"skipped {skip_count} of {len(student_tree)}")
	console.print(f"downloaded {download_count} of {processed_count}")
	console.print('DONE\n\n', style="bright_green")
	return
