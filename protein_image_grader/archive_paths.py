"""Archive path helpers for protein image storage and hash records."""

# Standard Library
import pathlib
import subprocess

# local repo modules
import protein_image_grader.rmspaces

ARCHIVE_ROOT_NAME = "archive"
ARCHIVE_IMAGES_NAME = "ARCHIVE_IMAGES"
LEGACY_IMPORT_TERM = "legacy_import"
IMAGE_HASHES_NAME = "image_hashes.yml"


#============================================
def get_repo_root(start_path: pathlib.Path | None = None) -> pathlib.Path:
	"""
	Find the repository root using git.

	Args:
		start_path: Optional path inside the repository.

	Returns:
		pathlib.Path: Absolute repository root.
	"""
	if start_path is None:
		start_path = pathlib.Path.cwd()
	result = subprocess.run(
		["git", "rev-parse", "--show-toplevel"],
		capture_output=True,
		text=True,
		cwd=str(start_path),
	)
	if result.returncode != 0:
		message = result.stderr.strip() or "Unable to determine repository root."
		raise ValueError(message)
	repo_root = pathlib.Path(result.stdout.strip()).resolve()
	return repo_root


#============================================
def path_to_posix(path: pathlib.Path | str) -> str:
	"""
	Convert a path to POSIX text.
	"""
	path_text = str(path).replace("\\", "/")
	while "//" in path_text:
		path_text = path_text.replace("//", "/")
	return path_text


#============================================
def make_term_label(year: int, semester: str) -> str:
	"""
	Build an archive term label.

	Args:
		year: Four-digit year.
		semester: Term name or numbered term label.

	Returns:
		str: Term label such as 2026_1Spring.
	"""
	term_text = str(semester).strip()
	term_map = {
		"spring": "1Spring",
		"1spring": "1Spring",
		"summer": "2Summer",
		"2summer": "2Summer",
		"fall": "3Fall",
		"autumn": "3Fall",
		"3fall": "3Fall",
	}
	term_key = term_text.lower()
	if term_key in term_map:
		term_text = term_map[term_key]
	if term_text == LEGACY_IMPORT_TERM:
		label = LEGACY_IMPORT_TERM
	else:
		label = f"{int(year):04d}_{term_text}"
	return label


#============================================
def make_term_label_from_month(year: int, month: int) -> str:
	"""
	Build an archive term label from a month number.
	"""
	if 1 <= month <= 5:
		semester = "1Spring"
	elif 6 <= month <= 8:
		semester = "2Summer"
	else:
		semester = "3Fall"
	label = make_term_label(year, semester)
	return label


#============================================
def make_assignment_archive_folder(image_number: int, assignment_name: str | None) -> str:
	"""
	Build the assignment archive folder name.
	"""
	folder = f"BCHM_Prot_Img_{image_number:02d}"
	if assignment_name:
		clean_name = protein_image_grader.rmspaces.cleanName(assignment_name)
		if clean_name:
			folder = f"{folder}_{clean_name}"
	return folder


#============================================
def get_image_hashes_path(repo_root: pathlib.Path | None = None) -> pathlib.Path:
	"""
	Build the archive hash YAML path.
	"""
	if repo_root is None:
		repo_root = get_repo_root()
	path = repo_root / ARCHIVE_ROOT_NAME / IMAGE_HASHES_NAME
	return path


#============================================
def make_archive_images_dir(term_label: str, repo_root: pathlib.Path | None = None) -> pathlib.Path:
	"""
	Build the archive images directory for a term.
	"""
	if repo_root is None:
		repo_root = get_repo_root()
	path = repo_root / ARCHIVE_ROOT_NAME / term_label / ARCHIVE_IMAGES_NAME
	return path


#============================================
def make_archive_assignment_dir(
	image_number: int,
	assignment_name: str | None,
	term_label: str,
	repo_root: pathlib.Path | None = None,
) -> pathlib.Path:
	"""
	Build the archive assignment directory.
	"""
	assignment_folder = make_assignment_archive_folder(image_number, assignment_name)
	path = make_archive_images_dir(term_label, repo_root) / assignment_folder
	return path


#============================================
def _strip_repo_prefix(path_text: str, repo_root: pathlib.Path) -> str:
	"""
	Convert an absolute path under repo_root to relative text.
	"""
	path = pathlib.Path(path_text)
	if not path.is_absolute():
		return path_text
	try:
		relative_path = path.resolve().relative_to(repo_root.resolve())
	except ValueError as exc:
		raise ValueError(f"Archive path is outside the repo: {path_text}") from exc
	relative_text = path_to_posix(relative_path)
	return relative_text


#============================================
def _normalize_legacy_archive_images(path_text: str) -> str:
	"""
	Normalize legacy ARCHIVE_IMAGES paths to the legacy import bucket.
	"""
	prefix = f"{ARCHIVE_IMAGES_NAME}/"
	if path_text == ARCHIVE_IMAGES_NAME:
		raise ValueError("Archive path points to ARCHIVE_IMAGES without a file path.")
	if path_text.startswith(prefix):
		remainder = path_text[len(prefix):]
		path_text = (
			f"{ARCHIVE_ROOT_NAME}/{LEGACY_IMPORT_TERM}/"
			f"{ARCHIVE_IMAGES_NAME}/{remainder}"
		)
	return path_text


#============================================
def normalize_hash_path(
	path_text: str,
	repo_root: pathlib.Path | None = None,
) -> str:
	"""
	Normalize a hash YAML file path.

	Args:
		path_text: File path from a hash record or archive operation.
		repo_root: Optional repository root for absolute path conversion.

	Returns:
		str: Canonical repo-relative POSIX path.
	"""
	if repo_root is None:
		repo_root = get_repo_root()
	clean_text = path_to_posix(path_text).strip()
	if not clean_text:
		raise ValueError("Archive path is empty.")
	clean_text = _strip_repo_prefix(clean_text, repo_root)
	clean_text = clean_text.lstrip("./")
	clean_text = _normalize_legacy_archive_images(clean_text)
	canonical_prefix = f"{ARCHIVE_ROOT_NAME}/"
	if not clean_text.startswith(canonical_prefix):
		raise ValueError(f"Archive path cannot be normalized: {path_text}")
	return clean_text


#============================================
def resolve_archive_path(path_text: str, repo_root: pathlib.Path) -> pathlib.Path:
	"""
	Resolve an archive path to a candidate local file path.

	Resolution may return a candidate path that does not exist. Caller code decides
	whether to warn or fail.
	"""
	clean_text = path_to_posix(path_text).strip()
	if not clean_text:
		raise ValueError("Archive path is empty.")
	path = pathlib.Path(clean_text)
	if path.is_absolute():
		return path
	clean_text = clean_text.lstrip("./")
	legacy_prefix = f"{ARCHIVE_IMAGES_NAME}/"
	if clean_text.startswith(legacy_prefix):
		root_legacy_path = repo_root / clean_text
		if root_legacy_path.exists():
			return root_legacy_path
		remainder = clean_text[len(legacy_prefix):]
		fallback_path = (
			repo_root / ARCHIVE_ROOT_NAME / LEGACY_IMPORT_TERM
			/ ARCHIVE_IMAGES_NAME / remainder
		)
		return fallback_path
	resolved_path = repo_root / clean_text
	return resolved_path
