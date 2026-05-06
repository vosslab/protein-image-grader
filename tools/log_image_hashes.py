#!/usr/bin/env python3

# Standard Library
import os
import argparse
import pathlib

# PIP3 modules
import yaml
import imagehash
from PIL import Image

# local repo modules
import protein_image_grader.google_drive_image_utils as google_drive_image_utils
import protein_image_grader.archive_paths as archive_paths
import protein_image_grader.protein_images_path as protein_images_path

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


#============================================
def parse_args():
	"""
	Parse command line arguments.
	"""
	parser = argparse.ArgumentParser(description="Rebuild image bank hashes from canonical archive layout.")
	parser.add_argument(
		"--rebuild",
		dest="rebuild",
		action="store_true",
		help="Write image_hashes.yml. Without this flag, run as a dry-run.",
	)
	args = parser.parse_args()
	return args


#============================================
def collect_image_bank(image_bank_path: pathlib.Path | str) -> list:
	"""
	Collect image files from the canonical image_bank/ structure.
	"""
	image_files = []
	image_bank_path = pathlib.Path(image_bank_path)
	for root, dirs, files in os.walk(str(image_bank_path)):
		dirs.sort()
		for file in sorted(files):
			full_path = os.path.join(root, file)
			if os.path.isfile(full_path):
				image_files.append(full_path)
	image_files.sort()
	return image_files


#============================================
def rebuild_hashes(image_bank_path: pathlib.Path | str) -> dict:
	"""
	Rebuild image hashes from canonical image_bank structure.
	"""
	# Initialize dictionaries to hold hash values and file names
	md5_dict = {}
	phash_dict = {}

	image_bank_path = pathlib.Path(image_bank_path)
	if not image_bank_path.is_dir():
		raise ValueError(f"Image bank directory not found: {image_bank_path}")

	# Iterate over each file in the image_bank
	image_files = collect_image_bank(image_bank_path)
	summarize_extensions(image_files)
	for filepath in image_files:
		print(filepath)
		# Calculate MD5 and pHash
		image_data = open(filepath, 'rb')
		md5_hash, perceptual_hash = google_drive_image_utils.get_hash_data(image_data)
		hash_path = archive_paths.normalize_hash_path(filepath)

		# Update the dictionaries
		md5_dict[md5_hash] = hash_path
		phash_dict[perceptual_hash] = hash_path

	image_hashes = {'md5': md5_dict, 'phash': phash_dict}
	return image_hashes


#============================================
def main():
	"""
	Run the hash rebuild script.
	"""
	args = parse_args()
	image_bank_path = protein_images_path.get_image_bank_dir()
	hashes_yaml_path = protein_images_path.get_image_hashes_yaml()
	image_hashes = rebuild_hashes(image_bank_path)

	# Save the dictionaries to a YAML file
	if args.rebuild:
		with open(hashes_yaml_path, 'w') as f:
			yaml.dump(image_hashes, f)
	else:
		print("Dry-run complete. Use --rebuild to write image_hashes.yml.")
	return


#============================================
if __name__ == '__main__':
	main()
