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
		default="ARCHIVE_IMAGES",
		help="PATH_TO_OLD_ARCHIVE_IMAGES",
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
	target_path = target_root / term / archive_paths.ARCHIVE_IMAGES_NAME / relative_path
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
def summarize_records(records: list[dict]) -> None:
	"""
	Print a status summary.
	"""
	counts = {}
	for record in records:
		status = record["status"]
		counts[status] = counts.get(status, 0) + 1
	for status in sorted(counts):
		print(f"{status}: {counts[status]}")
	return


#============================================
def main():
	"""
	Run the copy migration tool.
	"""
	args = parse_args()
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
	summarize_records(records)
	if args.copy_files is False:
		print("Dry-run complete. Use --copy to copy files.")
	return


#============================================
if __name__ == "__main__":
	main()
