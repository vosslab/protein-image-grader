#!/usr/bin/env python3

# external python/pip modules
import os
import yaml
import imagehash
from PIL import Image

import test_google_image

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
	return test_google_image.calculate_md5(image_data)

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

	# Iterate over each file in the images folder
	image_files = []
	#image_files = glob.glob('ARCHIVE_IMAGES/BCHM_Prot_Img_*/*.*')
	for root, dirs, files in os.walk('ARCHIVE_IMAGES/'):
		for file in files:
			full_path = os.path.join(root, file)
			if os.path.isfile(full_path):  # Ensures it's a file, not a directory
					image_files.append(full_path)
	image_files.sort()
	summarize_extensions(image_files)
	for filepath in image_files:
		filename = os.path.basename(filepath)
		print(filepath)
		# Calculate MD5 and pHash
		image_data = open(filepath, 'rb')
		md5_hash, perceptual_hash = test_google_image.get_hash_data(image_data)

		# Update the dictionaries
		md5_dict[md5_hash] = filepath
		phash_dict[perceptual_hash] = filepath

	# Save the dictionaries to a YAML file
	with open('image_hashes.yml', 'w') as f:
		yaml.dump({'md5': md5_dict, 'phash': phash_dict}, f)
