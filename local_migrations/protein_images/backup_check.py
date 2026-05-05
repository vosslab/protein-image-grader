"""
Backup verification for the migration executor.

A backup is considered valid if it contains the expected legacy top-level
folders that the migration is about to move. This is content-based, not
size-based, because filesystem metadata and sparse files make size noisy.

Two backup formats are accepted:
- A sibling directory (e.g., Protein_Images_backup_2026-05-05/).
- A tar archive (e.g., protein_image.tar).
"""

import pathlib
import re
import tarfile


# A valid backup must contain ARCHIVE_IMAGES plus at least one DOWNLOAD_*_year_*
# folder. These are the largest, hardest-to-recreate buckets in the legacy tree.
REQUIRED_NAMES = ("ARCHIVE_IMAGES",)
REQUIRED_PATTERNS = (re.compile(r"^DOWNLOAD_\d{2}_year_\d{4}$"),)


class BackupMissingError(RuntimeError):
	pass


def _names_in_dir(backup_dir: pathlib.Path) -> set[str]:
	# Direct children only.
	return {p.name for p in backup_dir.iterdir()}


def _names_in_tar(tar_path: pathlib.Path) -> set[str]:
	# Top-level segment of every member, regardless of nesting.
	# This handles tarballs created with or without a wrapping folder.
	names: set[str] = set()
	with tarfile.open(tar_path, "r") as tf:
		for member_name in tf.getnames():
			parts = pathlib.PurePosixPath(member_name).parts
			if not parts:
				continue
			# If the tar wraps a single root folder (e.g., "Protein_Images/..."),
			# also expose the second segment as a top-level candidate.
			names.add(parts[0])
			if len(parts) >= 2:
				names.add(parts[1])
	return names


def _check_required(names: set[str], source_label: str) -> None:
	missing_required = [n for n in REQUIRED_NAMES if n not in names]
	matched_patterns = [p.pattern for p in REQUIRED_PATTERNS
		if any(p.match(n) for n in names)]
	missing_patterns = [p.pattern for p in REQUIRED_PATTERNS
		if not any(p.match(n) for n in names)]
	if missing_required or missing_patterns:
		message = (
			f"Backup verification failed for {source_label}:\n"
			f"  missing required names: {missing_required or 'none'}\n"
			f"  missing required patterns: {missing_patterns or 'none'}\n"
			f"  matched patterns: {matched_patterns}\n"
			"Refusing to apply migration without a verified backup."
		)
		raise BackupMissingError(message)


def verify_backup(backup_path: pathlib.Path) -> dict:
	"""Verify that backup_path looks like a valid backup of the data root.

	Returns a dict describing how the backup was checked, suitable for
	logging into the applied report.
	"""
	if not backup_path.exists():
		raise BackupMissingError(f"Backup path does not exist: {backup_path}")

	if backup_path.is_dir():
		names = _names_in_dir(backup_path)
		_check_required(names, f"directory backup {backup_path}")
		return {
			"format": "directory",
			"path": str(backup_path),
			"top_level_count": len(names),
		}

	if backup_path.is_file() and backup_path.suffixes[-1:] == [".tar"]:
		names = _names_in_tar(backup_path)
		_check_required(names, f"tar backup {backup_path}")
		return {
			"format": "tar",
			"path": str(backup_path),
			"member_count": len(names),
		}

	raise BackupMissingError(
		f"Backup path is neither a directory nor a .tar archive: {backup_path}"
	)
