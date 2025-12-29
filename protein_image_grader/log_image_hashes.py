#!/usr/bin/env python3

# external python/pip modules
import os
import yaml
import imagehash
from PIL import Image

import protein_image_grader.google_drive_image_utils as google_drive_image_utils

def calculate_md5(image_path: str) -> str:
	"""
	Calculate the MD5 hash of an image's pixel data, excluding metadata

	Parameters
	----------
	image_path : str
		Path to the image file

	Returns
	-------
	str
		MD5 hash of the image's pixel data
	"""
	image_data = open(image_path, 'rb')
	return google_drive_image_utils.calculate_md5(image_data)

def calculate_phash(image_path: str, hash_size: int = 16) -> str:
	"""
	Calculate the perceptual hash of an image

	Parameters
	----------
	image_path : str
		Path to the image file
	hash_size : int, optional
		Size of the perceptual hash

	Returns
	-------
	str
		Perceptual hash of the image
	"""
	img = Image.open(image_path)
	return str(imagehash.phash(img, hash_size=hash_size))


def summarize_extensions(image_files: list) -> None:
	ext_set = set()
	for image_file in image_files:
		ext = os.path.splitext(image_file.lower())[-1]
		#print(ext)
		ext_set.add(ext)
	print("extensions found: ", ext_set)

if __name__ == '__main__':
	# Initialize dictionaries to hold hash values and file names
	md5_dict = {}
	phash_dict = {}

	archive_root = 'archive'
	archive_hashes = os.path.join(archive_root, 'image_hashes.yml')
	if not os.path.isdir(archive_root):
		raise ValueError(f"Archive directory not found: {archive_root}")

	# Iterate over each file in the archive images folders
	image_files = []
	for root, dirs, files in os.walk(archive_root):
		if 'ARCHIVE_IMAGES' not in root.split(os.sep):
			continue
		for file in files:
			full_path = os.path.join(root, file)
			if os.path.isfile(full_path):
				image_files.append(full_path)
	image_files.sort()
	summarize_extensions(image_files)
	for filepath in image_files:
		filename = os.path.basename(filepath)
		print(filepath)
		# Calculate MD5 and pHash
		image_data = open(filepath, 'rb')
		md5_hash, perceptual_hash = google_drive_image_utils.get_hash_data(image_data)

		# Update the dictionaries
		md5_dict[md5_hash] = filepath
		phash_dict[perceptual_hash] = filepath

	# Save the dictionaries to a YAML file
	with open(archive_hashes, 'w') as f:
		yaml.dump({'md5': md5_dict, 'phash': phash_dict}, f)
