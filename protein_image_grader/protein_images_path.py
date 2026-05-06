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
YAML_SUBDIR = "yaml"
GRADES_SUBDIR = "grades"
SUBMISSIONS_SUBDIR = "submissions"
CREDENTIALS_USER_PATH = "~/.config/bchm_355/credentials"


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


def get_yaml_dir(term: str) -> pathlib.Path:
	return get_term_dir(term) / YAML_SUBDIR


def get_grades_dir(term: str) -> pathlib.Path:
	return get_term_dir(term) / GRADES_SUBDIR


def get_submissions_dir(term: str) -> pathlib.Path:
	return get_term_dir(term) / SUBMISSIONS_SUBDIR


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
