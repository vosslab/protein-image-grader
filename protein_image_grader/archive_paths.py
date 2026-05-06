"""Archive path helpers for protein image storage and hash records."""

# Standard Library
import pathlib
import subprocess

IMAGE_BANK_NAME = "image_bank"

# Legacy flat-roots inside image_bank/ that are not term-organized:
# - MIXED/: student images that predate the RUID-xxx naming convention
# - PDB_IMAGES/: curated PDB reference images
# Both are hashed for plagiarism detection but never written to by new code.
LEGACY_FLAT_ROOTS = ("MIXED", "PDB_IMAGES")


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
# Archive path builders for NAS-resident image_bank/ and term-organized structure.

def make_image_bank_dir(term: str) -> pathlib.Path:
	"""
	Build the image_bank directory for a term on the NAS.

	Args:
		term: Term in canonical form, e.g. 'spring_2026'.

	Returns:
		pathlib.Path: <protein_images>/image_bank/<term>
	"""
	import protein_image_grader.protein_images_path as protein_images_path
	return protein_images_path.get_image_bank_dir() / term


#============================================
def make_archive_assignment_dir(term: str, image_dir_name: str) -> pathlib.Path:
	"""
	Build the archive assignment directory on the NAS.

	The working folder and archive folder share the exact same string so
	they stay in sync. The folder name comes from get_term_image_dir(term, NN).name,
	not from parameters.

	Args:
		term: Term in canonical form, e.g. 'spring_2026'.
		image_dir_name: The directory name (e.g. 'BCHM_Prot_Img_01_White_Background').

	Returns:
		pathlib.Path: <protein_images>/image_bank/<term>/<image_dir_name>
	"""
	return make_image_bank_dir(term) / image_dir_name


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
def normalize_hash_path(
	path_text: str,
	repo_root: pathlib.Path | None = None,
) -> str:
	"""
	Normalize a hash YAML file path to a canonical relative POSIX string.

	Accepts only:
	- Absolute paths under Protein_Images/image_bank/ -> converts to
	  image_bank/<term>/<image_dir>/{raw,trim}/<file>
	- Already-relative paths in the canonical shape above

	Rejects everything else with ValueError.
	"""
	if repo_root is None:
		repo_root = get_repo_root()
	clean_text = path_to_posix(path_text).strip()
	if not clean_text:
		raise ValueError("Archive path is empty.")

	# Strip absolute NAS paths under Protein_Images/image_bank/ to a relative
	# tail and re-prefix with image_bank/ so the canonical check below applies
	# uniformly to absolute and relative inputs.
	path_obj = pathlib.Path(path_text)
	if path_obj.is_absolute():
		try:
			import protein_image_grader.protein_images_path
			image_bank_path = protein_image_grader.protein_images_path.get_image_bank_dir()
		except (FileNotFoundError, NotADirectoryError) as exc:
			raise ValueError(
				f"Cannot resolve image_bank/ for absolute path: {path_text}"
			) from exc
		try:
			relative_obj = path_obj.relative_to(image_bank_path)
		except ValueError as exc:
			raise ValueError(
				f"Absolute path not under image_bank: {path_text}"
			) from exc
		clean_text = f"{IMAGE_BANK_NAME}/{path_to_posix(relative_obj)}"

	# Convert to POSIX
	clean_text = path_to_posix(clean_text).strip()
	clean_text = clean_text.lstrip("./")

	# Accept canonical image_bank/ prefix (term-organized or legacy flat roots).
	if not clean_text.startswith(f"{IMAGE_BANK_NAME}/"):
		raise ValueError(
			f"Archive path must be in image_bank/<term>/<image_dir>/{{raw,trim}}/<file> "
			f"form (or under {'/, '.join(LEGACY_FLAT_ROOTS)}/): {path_text}"
		)
	return clean_text


#============================================
def resolve_archive_path(path_text: str, repo_root: pathlib.Path) -> pathlib.Path:
	"""
	Resolve an archive path to a candidate local file path.

	Bare image_bank/<rel> resolves through the Synology helper to
	Protein_Images/image_bank/<rel>.

	Resolution may return a path that does not exist; callers decide.
	"""
	# Local import to avoid a circular import at module load time.
	import protein_image_grader.protein_images_path
	clean_text = path_to_posix(path_text).strip()
	if not clean_text:
		raise ValueError("Archive path is empty.")
	path = pathlib.Path(clean_text)
	if path.is_absolute():
		return path
	clean_text = clean_text.lstrip("./")
	external_prefix = f"{IMAGE_BANK_NAME}/"
	if clean_text.startswith(external_prefix):
		remainder = clean_text[len(external_prefix):]
		return protein_image_grader.protein_images_path.get_image_bank_dir() / remainder
	raise ValueError(f"Archive path must start with image_bank/: {path_text}")
