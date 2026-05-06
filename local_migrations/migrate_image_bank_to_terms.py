#!/usr/bin/env python3
"""
Migrate image_bank flat directory into term-organized structure.

Walks image_bank/ for BCHM_Prot_Img_NN_* folders, classifies by -trim.jpg
suffix, computes term from file mtime/birthtime, and moves to the canonical
image_bank/<term>/<assignment>/{raw,trim}/ layout.

Default is dry-run; --apply flag performs actual moves.
"""

import os
import sys
import time
import argparse
import pathlib
import hashlib

import protein_image_grader.protein_images_path as protein_images_path

#============================================
def parse_args():
	"""
	Parse command-line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Migrate image_bank flat structure to term-organized layout (dry-run by default)"
	)
	parser.add_argument(
		'--apply', dest='apply', action='store_true',
		help="Actually move files; without this flag, only dry-run",
		default=False
	)
	args = parser.parse_args()
	return args


#============================================
def compute_file_md5(filepath: str) -> str:
	"""
	Compute MD5 hash of a file.
	"""
	md5_hash = hashlib.md5()
	with open(filepath, 'rb') as f:
		for chunk in iter(lambda: f.read(4096), b""):
			md5_hash.update(chunk)
	return md5_hash.hexdigest()


#============================================
def get_file_year_month(filepath: str) -> tuple:
	"""
	Extract (year, month) from file mtime/birthtime.

	Prefers st_birthtime (creation time on macOS); falls back to st_mtime
	(modification time). Returns (year, month) as integers.
	"""
	stat_info = os.stat(filepath)
	timestamp = getattr(stat_info, 'st_birthtime', None)
	if timestamp is None:
		timestamp = stat_info.st_mtime
	time_tuple = time.localtime(timestamp)
	year = time_tuple.tm_year
	month = time_tuple.tm_mon
	return year, month


#============================================
def migrate_assignment_folder(src_path: str, image_bank_dir: str, apply: bool) -> bool:
	"""
	Migrate one BCHM_Prot_Img_NN_* folder from flat structure to term-organized.

	Returns True if migration succeeds (or would succeed in dry-run); False if blocked.
	"""
	src_path = pathlib.Path(src_path)
	assignment_name = src_path.name

	# Separate raw and trim files
	raw_files = []
	trim_files = []

	for item in src_path.iterdir():
		if not item.is_file():
			continue
		basename_lower = item.name.lower()
		if basename_lower.endswith('-trim.jpg'):
			trim_files.append(item)
		else:
			raw_files.append(item)

	# Compute term from raw files; if missing, try trim files
	source_files = raw_files if raw_files else trim_files
	if not source_files:
		print(f"  SKIP {assignment_name}: no image files found")
		return True

	year, month = get_file_year_month(str(source_files[0]))
	term = protein_images_path.season_year_term(year, month)

	# Build destination paths
	image_bank_path = pathlib.Path(image_bank_dir)
	dst_assignment_dir = image_bank_path / term / assignment_name
	dst_raw_dir = dst_assignment_dir / "raw"
	dst_trim_dir = dst_assignment_dir / "trim"

	# Plan the migrations
	migrations = []
	for raw_file in raw_files:
		dst_file = dst_raw_dir / raw_file.name
		migrations.append((str(raw_file), str(dst_file), "raw"))

	for trim_file in trim_files:
		dst_file = dst_trim_dir / trim_file.name
		migrations.append((str(trim_file), str(dst_file), "trim"))

	# Check for collisions and verify idempotency
	for src_file, dst_file, category in migrations:
		dst_path = pathlib.Path(dst_file)

		if dst_path.exists():
			# File already exists at destination; check if identical
			src_md5 = compute_file_md5(src_file)
			dst_md5 = compute_file_md5(dst_file)

			if src_md5 == dst_md5:
				# Idempotent: source is a leftover from a partial prior run.
				# Delete it so the source folder can be rmdir'd at the end.
				if apply:
					os.remove(src_file)
				print(f"  DEDUP {os.path.basename(src_file)} ({category}): same MD5 at destination, removing source")
				continue
			else:
				print(f"  ERROR {os.path.basename(src_file)} ({category}): file exists at destination with DIFFERENT MD5")
				print(f"    Source:      {src_file} ({src_md5})")
				print(f"    Destination: {dst_file} ({dst_md5})")
				return False

		# Destination is clear; plan the move
		if not apply:
			print(f"  MOVE {os.path.basename(src_file)} ({category}) -> {dst_file}")
		else:
			print(f"  MOVE {os.path.basename(src_file)} ({category}) -> {dst_file}")
			dst_path.parent.mkdir(parents=True, exist_ok=True)
			os.rename(src_file, dst_file)

	# If apply, clean up empty source directory
	if apply:
		try:
			os.rmdir(str(src_path))
			print(f"  RMDIR {assignment_name}")
		except OSError:
			# Directory not empty; that's fine (e.g., symlinks or metadata files)
			pass

	return True


#============================================
def main():
	"""
	Main function: walk image_bank and migrate assignment folders.
	"""
	args = parse_args()

	try:
		image_bank_dir = str(protein_images_path.get_image_bank_dir())
	except FileNotFoundError:
		# image_bank doesn't exist yet; nothing to migrate
		print("image_bank/ directory does not exist. Nothing to migrate.")
		return

	image_bank_path = pathlib.Path(image_bank_dir)

	# Find assignment folders (BCHM_Prot_Img_NN_*)
	assignment_folders = []
	for item in sorted(image_bank_path.iterdir()):
		if not item.is_dir():
			continue
		name = item.name
		if name.startswith(protein_images_path.IMAGE_DIR_PREFIX):
			assignment_folders.append(item)

	if not assignment_folders:
		print(f"No assignment folders found in {image_bank_dir}. Nothing to migrate.")
		return

	mode_label = "DRY-RUN" if not args.apply else "APPLY"
	print(f"Migration mode: {mode_label}\n")

	failed = False
	for folder in assignment_folders:
		print(f"Processing {folder.name}...")
		if not migrate_assignment_folder(str(folder), image_bank_dir, args.apply):
			failed = True

	if failed:
		print("\nMigration encountered errors and stopped.")
		sys.exit(1)

	if args.apply:
		print("\nMigration complete.")
	else:
		print("\nDry-run complete. Pass --apply to perform the actual moves.")


if __name__ == '__main__':
	main()
