"""
Canonical resolver for the external `Protein_Images/` data root.

Owns every path under `Protein_Images/` so the rest of the codebase never
joins data-root paths by hand. Resolution happens inside functions only;
importing this module performs no filesystem access.
"""

import re
import pathlib

import protein_image_grader.archive_paths


CANONICAL_FORM_CSV_RE = re.compile(r'^BCHM_Prot_Img_(\d{2})-.+\.csv$')


PROTEIN_IMAGES_NAME = "Protein_Images"
IMAGE_BANK_SUBDIR = "image_bank"
SEMESTERS_SUBDIR = "semesters"
ACTIVE_TERM_FILENAME = "active_term.txt"
ROSTER_FILENAME = "roster.csv"
EMAIL_LOG_FILENAME = "email_log.yml"
FORMS_SUBDIR = "forms"
CREDENTIALS_USER_PATH = "~/.config/bchm_355/credentials"
IMAGE_HASHES_FILENAME = "image_hashes.yml"
IMAGE_DIR_PREFIX = "BCHM_Prot_Img_"


SETUP_MESSAGE = (
	"Protein_Images/ is missing at the repo root.\n"
	"This folder holds years of student submissions and is not in git.\n"
	"Create a symlink to your local copy, for example:\n"
	"  ln -s /path/to/your/Protein_Images Protein_Images\n"
)


ACTIVE_TERM_HINT = (
	"Protein_Images/active_term.txt is missing.\n"
	"Write the active term to it, for example:\n"
	"  echo 'spring_2026' > Protein_Images/active_term.txt\n"
	"Or pass the term explicitly with --term spring_2026.\n"
)


def get_protein_images_dir() -> pathlib.Path:
	# Resolve <repo_root>/Protein_Images and verify it is a real directory.
	repo_root = protein_image_grader.archive_paths.get_repo_root()
	path = repo_root / PROTEIN_IMAGES_NAME
	if not path.exists():
		raise FileNotFoundError(SETUP_MESSAGE)
	if not path.is_dir():
		raise NotADirectoryError(SETUP_MESSAGE)
	return path.resolve()


def get_image_bank_dir() -> pathlib.Path:
	# Canonical image_bank/ subfolder; required to exist when callers ask.
	root = get_protein_images_dir()
	path = root / IMAGE_BANK_SUBDIR
	if not path.is_dir():
		message = (
			f"Required subfolder missing: {path}\n"
			"Run the migration tool or create image_bank/ under Protein_Images/.\n"
		)
		raise FileNotFoundError(message)
	return path


def get_active_term(term_override: str | None = None) -> str:
	# Explicit override wins; otherwise read active_term.txt.
	if term_override:
		return term_override.strip()
	root = get_protein_images_dir()
	active_term_file = root / ACTIVE_TERM_FILENAME
	if not active_term_file.is_file():
		raise FileNotFoundError(ACTIVE_TERM_HINT)
	term = active_term_file.read_text(encoding="ascii").strip()
	if not term:
		raise ValueError(
			f"{active_term_file} is empty; expected a term like 'spring_2026'."
		)
	return term


def get_term_dir(term: str) -> pathlib.Path:
	# Per-term root: Protein_Images/semesters/<term>/
	root = get_protein_images_dir()
	return root / SEMESTERS_SUBDIR / term


def get_forms_dir(term: str) -> pathlib.Path:
	return get_term_dir(term) / FORMS_SUBDIR


def get_roster_csv(term: str) -> pathlib.Path:
	return get_term_dir(term) / ROSTER_FILENAME


def get_email_log_yaml(term: str) -> pathlib.Path:
	# Per-term email status log; sits alongside roster.csv at the term root.
	return get_term_dir(term) / EMAIL_LOG_FILENAME


def find_canonical_form_csvs(term: str) -> dict:
	"""
	Return {image_number: [csv_paths]} from the canonical forms dir.

	Missing forms dir yields an empty dict; multiple matches per image
	number are preserved so callers can detect duplicates.
	"""
	forms_dir = get_forms_dir(term)
	by_image = {}
	if not forms_dir.is_dir():
		return by_image
	for csv_path in sorted(forms_dir.glob("BCHM_Prot_Img_*.csv")):
		match = CANONICAL_FORM_CSV_RE.match(csv_path.name)
		if match is None:
			continue
		image_number = int(match.group(1))
		by_image.setdefault(image_number, []).append(csv_path)
	return by_image


def get_credentials_dir() -> pathlib.Path:
	# Credentials are not course data; live outside Protein_Images/.
	return pathlib.Path(CREDENTIALS_USER_PATH).expanduser()


#============================================
def season_year_term(year: int, month: int) -> str:
	"""
	Canonical term string used everywhere: e.g. 'spring_2026'.

	Args:
		year: Four-digit year.
		month: Month 1-12.

	Returns:
		str: Term in the form '<season>_<year>'.
	"""
	if 1 <= month <= 5:
		season = "spring"
	elif 6 <= month <= 8:
		season = "summer"
	else:
		season = "fall"
	return f"{season}_{int(year):04d}"


#============================================
def _form_csv_to_image_dir_name(csv_basename: str) -> str:
	"""
	Derive the image directory name from a form CSV basename.

	Rules:
	1. Strip the trailing .csv.
	2. Replace only the first '-' (between NN and <topic>) with '_'.
	3. Replace any character outside [A-Za-z0-9._-] with '_'.

	Examples:
	- BCHM_Prot_Img_03-Hydrophobic_Interior.csv -> BCHM_Prot_Img_03_Hydrophobic_Interior
	- BCHM_Prot_Img_07-Alpha-Helix.csv -> BCHM_Prot_Img_07_Alpha-Helix
	- BCHM_Prot_Img_09-White Background.csv -> BCHM_Prot_Img_09_White_Background
	"""
	if not csv_basename.endswith('.csv'):
		raise ValueError(f"Expected .csv basename, got: {csv_basename}")
	# Remove .csv
	name = csv_basename[:-4]
	# Replace only the first hyphen (between NN and topic)
	parts = name.split('-', 1)
	if len(parts) == 2:
		name = parts[0] + '_' + parts[1]
	# Replace unsafe characters with underscores
	safe_name = ""
	for char in name:
		if char.isalnum() or char in "._-":
			safe_name += char
		else:
			safe_name += "_"
	return safe_name


#============================================
def get_term_image_dir(term: str, image_number: int) -> pathlib.Path:
	"""
	Resolve the per-image working folder under semesters/<term>/.

	Looks up the form CSV (BCHM_Prot_Img_NN-<topic>.csv) in forms/ to derive
	the canonical folder name BCHM_Prot_Img_NN_<topic> (with '-' -> '_').

	Falls back to a prefix-only match if the dir already exists (re-runs
	against an existing folder whose form CSV has been renamed are tolerated;
	the prefix BCHM_Prot_Img_NN_ is the keyed identity).

	Raises FileNotFoundError if neither the form CSV nor an existing folder
	is found. Raises RuntimeError if multiple folders or CSVs match.

	Args:
		term: Term in the form 'spring_2026'.
		image_number: Image number (01-20).

	Returns:
		pathlib.Path: The per-image working directory.
	"""
	# Step 1: glob for existing folders matching BCHM_Prot_Img_NN_*
	term_dir = get_term_dir(term)
	prefix = f"{IMAGE_DIR_PREFIX}{image_number:02d}_"
	existing_folders = sorted(term_dir.glob(f"{prefix}*"))
	# Filter to directories only
	existing_folders = [p for p in existing_folders if p.is_dir()]

	if len(existing_folders) == 1:
		return existing_folders[0]
	elif len(existing_folders) > 1:
		folder_names = [p.name for p in existing_folders]
		raise RuntimeError(
			f"Multiple folders match BCHM_Prot_Img_{image_number:02d}_* in {term}:\n"
			+ "\n".join(f"  {name}" for name in folder_names) +
			"\nOperator must reconcile."
		)

	# Step 2: look for form CSV
	forms_dir = get_forms_dir(term)
	matching_csvs = sorted(forms_dir.glob(f"BCHM_Prot_Img_{image_number:02d}-*.csv"))

	if len(matching_csvs) == 1:
		csv_basename = matching_csvs[0].name
		image_dir_name = _form_csv_to_image_dir_name(csv_basename)
		return term_dir / image_dir_name
	elif len(matching_csvs) > 1:
		csv_names = [p.name for p in matching_csvs]
		raise RuntimeError(
			f"Multiple form CSVs match BCHM_Prot_Img_{image_number:02d}-*.csv in {term}:\n"
			+ "\n".join(f"  {name}" for name in csv_names) +
			"\nOperator must reconcile."
		)

	# Step 3: nothing found
	raise FileNotFoundError(
		f"Image {image_number:02d} not found in term '{term}'.\n"
		f"Expected either:\n"
		f"  - An existing folder: {term_dir}/BCHM_Prot_Img_{image_number:02d}_*\n"
		f"  - A form CSV: {forms_dir}/BCHM_Prot_Img_{image_number:02d}-*.csv"
	)


#============================================
def get_image_hashes_yaml(repo_root: pathlib.Path | str | None = None) -> pathlib.Path:
	"""
	Repo-root-tracked hash YAML; portable across machines.

	Args:
		repo_root: Optional repo root. Defaults to inferred root.

	Returns:
		pathlib.Path: Path to <repo_root>/image_hashes.yml.
	"""
	if repo_root is None:
		repo_root = protein_image_grader.archive_paths.get_repo_root()
	return pathlib.Path(repo_root) / IMAGE_HASHES_FILENAME


#============================================
def get_image_spec_yaml(term: str, image_number: int) -> pathlib.Path:
	"""
	Resolve the spec YAML file for one image in a term.

	The spec lives inside the per-image folder:
		<repo_root>/Protein_Images/semesters/<term>/<image_dir>/protein_image_NN.yml

	Args:
		term: Term in the form 'spring_2026'.
		image_number: Image number (01-20).

	Returns:
		pathlib.Path: Path to the spec YAML.
	"""
	image_dir = get_term_image_dir(term, image_number)
	return image_dir / f"protein_image_{image_number:02d}.yml"
