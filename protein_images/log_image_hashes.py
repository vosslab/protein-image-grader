#!/usr/bin/env python3

# external python/pip modules
import os
import glob
import yaml
import hashlib
import imagehash
from PIL import Image

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
	img = Image.open(image_path)
	pixel_data = img.tobytes()
	return hashlib.md5(pixel_data).hexdigest()

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
	image_files = glob.glob('ARCHIVE_IMAGES/BCHM_Prot_Img_*/*.*')
	image_files.sort()
	summarize_extensions(image_files)
	for filepath in image_files:
		filename = os.path.basename(filepath)
		print(filepath)
		# Calculate MD5 and pHash
		md5_hash = calculate_md5(filepath)
		perceptual_hash = calculate_phash(filepath, hash_size=16)

		# Update the dictionaries
		md5_dict[md5_hash] = filename
		phash_dict[perceptual_hash] = filename

	# Save the dictionaries to a YAML file
	with open('image_hashes.yml', 'w') as f:
		yaml.dump({'md5': md5_dict, 'phash': phash_dict}, f)
