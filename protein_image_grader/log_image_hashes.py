# Standard Library
import os
import argparse

# PIP3 modules
import yaml
import imagehash
from PIL import Image

# local repo modules
import protein_image_grader.google_drive_image_utils as google_drive_image_utils
import protein_image_grader.archive_paths as archive_paths

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
	parser = argparse.ArgumentParser(description="Rebuild archive image hashes.")
	parser.add_argument(
		"--archive-root",
		dest="archive_root",
		default="archive",
		help="Archive root directory.",
	)
	parser.add_argument(
		"--rebuild",
		dest="rebuild",
		action="store_true",
		help="Write image_hashes.yml. Without this flag, run as a dry-run.",
	)
	args = parser.parse_args()
	return args


#============================================
def collect_archive_images(archive_root: str) -> list:
	"""
	Collect image files below ARCHIVE_IMAGES folders.
	"""
	image_files = []
	for root, dirs, files in os.walk(archive_root):
		dirs.sort()
		if 'ARCHIVE_IMAGES' not in root.split(os.sep):
			continue
		for file in sorted(files):
			full_path = os.path.join(root, file)
			if os.path.isfile(full_path):
				image_files.append(full_path)
	image_files.sort()
	return image_files


#============================================
def rebuild_hashes(archive_root: str) -> dict:
	"""
	Rebuild archive hashes from image files.
	"""
	# Initialize dictionaries to hold hash values and file names
	md5_dict = {}
	phash_dict = {}

	if not os.path.isdir(archive_root):
		raise ValueError(f"Archive directory not found: {archive_root}")

	# Iterate over each file in the archive images folders
	image_files = collect_archive_images(archive_root)
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
	archive_hashes = os.path.join(args.archive_root, 'image_hashes.yml')
	image_hashes = rebuild_hashes(args.archive_root)

	# Save the dictionaries to a YAML file
	if args.rebuild:
		with open(archive_hashes, 'w') as f:
			yaml.dump(image_hashes, f)
	else:
		print("Dry-run complete. Use --rebuild to write image_hashes.yml.")
	return


#============================================
if __name__ == '__main__':
	main()
