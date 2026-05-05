#!/usr/bin/env python3

"""Copy old archive image folders into the canonical archive layout."""

# Standard Library
import os
import csv
import shutil
import hashlib
import pathlib
import argparse

# local repo modules
import protein_image_grader.archive_paths as archive_paths
import protein_image_grader.protein_images_path as protein_images_path

IMAGE_EXTENSIONS = {
	".png",
	".jpg",
	".jpeg",
	".gif",
	".webp",
	".tif",
	".tiff",
	".bmp",
}


#============================================
def parse_args():
	"""
	Parse command line arguments.
	"""
	parser = argparse.ArgumentParser(
		description="Copy legacy archive images into the canonical archive layout."
	)
	parser.add_argument(
		"-s", "--source-archive",
		dest="source_archive",
		default=None,
		help=(
			"Source archive directory. Defaults to the canonical "
			"Protein_Images/image_bank/ resolved via the helper."
		),
	)
	parser.add_argument(
		"-r", "--target-root",
		dest="target_root",
		default="archive",
		help="Target archive root.",
	)
	parser.add_argument(
		"-t", "--term",
		dest="term",
		default=archive_paths.LEGACY_IMPORT_TERM,
		help="Target archive term folder.",
	)
	parser.add_argument(
		"-m", "--manifest",
		dest="manifest",
		default=None,
		help="CSV manifest path. Defaults under the target term.",
	)
	# Paired on/off flags for copy vs dry-run, default is dry-run.
	parser.add_argument(
		"-c", "--copy",
		dest="copy_files",
		action="store_true",
		help="Actually copy files.",
	)
	parser.add_argument(
		"-n", "--dry-run",
		dest="copy_files",
		action="store_false",
		help="Inspect and write a manifest without copying any files.",
	)
	parser.set_defaults(copy_files=False)
	args = parser.parse_args()
	return args


#============================================
def calculate_file_hash(file_path: pathlib.Path) -> str:
	"""
	Calculate a SHA256 hash for a file.
	"""
	sha256_hash = hashlib.sha256()
	with open(file_path, "rb") as handle:
		while True:
			chunk = handle.read(1024 * 1024)
			if not chunk:
				break
			sha256_hash.update(chunk)
	hash_text = sha256_hash.hexdigest()
	return hash_text


#============================================
def is_image_file(file_path: pathlib.Path) -> bool:
	"""
	Check whether a file extension is a recognized image extension.
	"""
	extension = file_path.suffix.lower()
	is_image = extension in IMAGE_EXTENSIONS
	return is_image


#============================================
def build_manifest_path(
	target_root: pathlib.Path,
	term: str,
	manifest_path: str | None,
) -> pathlib.Path | None:
	"""
	Build the manifest output path.
	"""
	if manifest_path is None:
		path = target_root / term / "copy_manifest.csv"
	elif manifest_path.strip().lower() in ("", "none", "off", "false"):
		path = None
	else:
		path = pathlib.Path(manifest_path)
	return path


#============================================
def iter_source_files(source_archive: pathlib.Path) -> list[pathlib.Path]:
	"""
	List files in a source archive tree.
	"""
	files = []
	for root, dirs, filenames in os.walk(source_archive):
		dirs.sort()
		for filename in sorted(filenames):
			file_path = pathlib.Path(root) / filename
			if file_path.is_file():
				files.append(file_path)
	return files


#============================================
def build_target_path(
	source_file: pathlib.Path,
	source_archive: pathlib.Path,
	target_root: pathlib.Path,
	term: str,
) -> pathlib.Path:
	"""
	Build the canonical target path for one source file.
	"""
	relative_path = source_file.relative_to(source_archive)
	target_path = target_root / term / archive_paths.IMAGE_BANK_NAME / relative_path
	return target_path


#============================================
def inspect_copy_status(source_file: pathlib.Path, target_file: pathlib.Path) -> dict:
	"""
	Inspect a source and target file pair.
	"""
	source_size = source_file.stat().st_size
	source_hash = ""
	target_hash = ""
	status = "would_copy"
	if not is_image_file(source_file):
		status = "non_image"
	elif target_file.exists():
		source_hash = calculate_file_hash(source_file)
		target_hash = calculate_file_hash(target_file)
		if source_size == target_file.stat().st_size and source_hash == target_hash:
			status = "skipped_existing"
		else:
			status = "conflict"
	result = {
		"source_path": str(source_file),
		"target_path": str(target_file),
		"status": status,
		"size_bytes": source_size,
		"source_hash": source_hash,
		"target_hash": target_hash,
	}
	return result


#============================================
def copy_file_if_needed(record: dict, copy_files: bool) -> dict:
	"""
	Copy a file when requested and safe.
	"""
	if record["status"] != "would_copy":
		return record
	if copy_files is False:
		return record
	source_path = pathlib.Path(record["source_path"])
	target_path = pathlib.Path(record["target_path"])
	target_path.parent.mkdir(parents=True, exist_ok=True)
	shutil.copy2(source_path, target_path)
	record["status"] = "copied"
	return record


#============================================
def write_manifest(manifest_path: pathlib.Path | None, records: list[dict]) -> None:
	"""
	Write a CSV copy manifest.
	"""
	if manifest_path is None:
		return
	manifest_path.parent.mkdir(parents=True, exist_ok=True)
	fieldnames = [
		"source_path",
		"target_path",
		"status",
		"size_bytes",
		"source_hash",
		"target_hash",
	]
	with open(manifest_path, "w", newline="") as handle:
		writer = csv.DictWriter(handle, fieldnames=fieldnames)
		writer.writeheader()
		for record in records:
			writer.writerow(record)
	return


#============================================
def copy_archive_images(
	source_archive: pathlib.Path,
	target_root: pathlib.Path,
	term: str,
	manifest_path: pathlib.Path | None,
	copy_files: bool,
) -> list[dict]:
	"""
	Copy legacy archive images into the target archive tree.
	"""
	if not source_archive.is_dir():
		raise ValueError(f"Source archive directory not found: {source_archive}")
	records = []
	for source_file in iter_source_files(source_archive):
		target_file = build_target_path(source_file, source_archive, target_root, term)
		record = inspect_copy_status(source_file, target_file)
		record = copy_file_if_needed(record, copy_files)
		records.append(record)
	write_manifest(manifest_path, records)
	return records


#============================================
def summarize_records(records: list[dict], target_root: pathlib.Path) -> None:
	"""
	Print a status summary plus the target output folder tree with image counts and sizes.
	"""
	# Aggregate counts by status (would_copy, copied, skipped_existing, conflict, non_image)
	status_counts = {}
	status_bytes = {}
	# Per-target-folder counts and bytes (folder = parent dir of the target file)
	target_folder_counts = {}
	target_folder_bytes = {}
	total_bytes = 0
	for record in records:
		status = record["status"]
		size = record["size_bytes"]
		status_counts[status] = status_counts.get(status, 0) + 1
		status_bytes[status] = status_bytes.get(status, 0) + size
		total_bytes += size
		if status == "non_image":
			continue
		target_path = pathlib.Path(record["target_path"])
		target_dir = target_path.parent
		target_folder_counts[target_dir] = target_folder_counts.get(target_dir, 0) + 1
		target_folder_bytes[target_dir] = target_folder_bytes.get(target_dir, 0) + size

	# Status breakdown
	print("Status breakdown:")
	for status in sorted(status_counts):
		count = status_counts[status]
		mb = status_bytes[status] / (1024 * 1024)
		print(f"  {status}: {count} files ({mb:.1f} MB)")

	# Target output tree
	print(f"\nTarget output tree under {target_root}:")
	print(f"  ({len(target_folder_counts)} folders, {sum(target_folder_counts.values())} images)\n")
	# Sort folders by their string path so the tree prints in lexicographic order
	sorted_folders = sorted(target_folder_counts, key=lambda p: str(p))
	prev_parts = ()
	for target_dir in sorted_folders:
		# Render the path as a tree by indenting each new directory component
		try:
			rel_dir = target_dir.relative_to(target_root)
		except ValueError:
			rel_dir = target_dir
		parts = rel_dir.parts
		# Print any new ancestor segments not already shown
		for depth in range(len(parts) - 1):
			if depth >= len(prev_parts) or prev_parts[depth] != parts[depth]:
				indent = "  " * depth
				print(f"{indent}{parts[depth]}/")
		# Print the leaf folder with image count and MB
		leaf_depth = max(len(parts) - 1, 0)
		indent = "  " * leaf_depth
		count = target_folder_counts[target_dir]
		mb = target_folder_bytes[target_dir] / (1024 * 1024)
		leaf_name = parts[-1] if parts else str(target_dir)
		print(f"{indent}{leaf_name}/  -- {count} images ({mb:.1f} MB)")
		prev_parts = parts

	total_mb = total_bytes / (1024 * 1024)
	print(f"\nTotal records: {len(records)} ({total_mb:.1f} MB)")
	return


#============================================
def main():
	"""
	Run the copy migration tool.
	"""
	args = parse_args()
	if args.source_archive is None:
		source_archive = protein_images_path.get_image_bank_dir()
	else:
		source_archive = pathlib.Path(args.source_archive)
	target_root = pathlib.Path(args.target_root)
	manifest_path = build_manifest_path(target_root, args.term, args.manifest)
	records = copy_archive_images(
		source_archive,
		target_root,
		args.term,
		manifest_path,
		args.copy_files,
	)
	summarize_records(records, target_root)
	if args.copy_files is False:
		print("Dry-run complete. Use --copy to copy files.")
	return


#============================================
if __name__ == "__main__":
	main()
