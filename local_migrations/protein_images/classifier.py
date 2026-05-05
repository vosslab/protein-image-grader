"""
Classifier for the Protein_Images/ legacy -> canonical migration.

Pure: takes a path on disk plus a few facts about it (active term, presence of
sibling term folders) and returns a proposed Move. Reads only os.stat for the
item it is classifying. Never mutates the filesystem and never recurses.

Confidence levels:
- high: hardcoded rule applies; destination is unambiguous.
- low : hardcoded rule says "send to legacy/needs_review/<bucket>/", or the
        rule needs evidence the classifier could not confirm.

Items already at a canonical location (active_term.txt, image_bank/,
semesters/, legacy/, credentials/) are returned with bucket="unchanged" and
no destination.
"""

import dataclasses
import os
import pathlib
import re
import time


CANONICAL_TOP_LEVEL = frozenset({
	"active_term.txt",
	"image_bank",
	"semesters",
	"legacy",
	"credentials",
})


# Filename rules for top-level files: regex -> (canonical-subdir-under-needs-review, evidence-tag).
# Order matters; first match wins.
LEGACY_FILE_RULES: tuple[tuple[re.Pattern, str, str], ...] = (
	(re.compile(r"^api_file\.json$"), "credentials", "credentials filename"),
	(re.compile(r"^service_key\.json$"), "credentials", "credentials filename"),
	(re.compile(r"^backup\.yml$"), "state_files", "scratch/state filename"),
	(re.compile(r"^crash_.*\.(yml|csv)$"), "state_files", "scratch/state filename"),
	(re.compile(r"^force_exit_.*\.yml$"), "state_files", "scratch/state filename"),
	(re.compile(r"^temp_save.*\.yml$"), "state_files", "scratch/state filename"),
	(re.compile(r"^wrong\d*\.yml$"), "state_files", "scratch/state filename"),
	(re.compile(r"^output-.*\.yml$"), "state_files", "scratch/state filename"),
	(re.compile(r"^image_hashes\.yml$"), "state_files", "scratch/state filename"),
	(re.compile(r"^packs-.*\.txt$"), "scratch", "scratch filename"),
	(re.compile(r"^test_graph\.py$"), "scratch", "scratch script"),
	(re.compile(r"^image_\d+\.html$"), "scratch", "scratch html"),
	(re.compile(r"^profiles\.html$"), "scratch", "scratch html"),
	(re.compile(r"^requirements\.txt$"), "broken_symlinks", "stray requirements.txt"),
)


# Folder rules for low-confidence (always-needs-review) buckets.
LEGACY_FOLDER_NEEDS_REVIEW: dict[str, str] = {
	"PROFILE_IMAGES": "profile_images",
	"YAML_files": "yaml_files",
	"Protein_Images_CVS": "protein_images_cvs",
}


# Regex for legacy per-term/per-image folders.
RE_LEGACY_TERM_FOLDER = re.compile(r"^(?P<year>\d{4})_(?P<num>\d*)?(?P<season>Spring|Summer|Fall)$")
RE_LEGACY_DOWNLOAD = re.compile(r"^DOWNLOAD_(?P<num>\d{2})_year_(?P<year>\d{4})$")
RE_LEGACY_IMAGE = re.compile(r"^IMAGE_(?P<num>\d{2})$")
RE_LEGACY_FORM_CSV = re.compile(r"^BCHM_Prot_Img_\d{2}-.*\.csv$")
RE_LEGACY_ROSTER_DATED = re.compile(r"^roster_(?P<year>\d{4})\.csv$")
RE_LEGACY_TERM_IDS = re.compile(r"^(?P<season>Spring|Summer|Fall)_(?P<year>\d{4})_IDs\.txt$")


@dataclasses.dataclass(frozen=True)
class Move:
	"""One proposed migration step.

	src and dst are absolute paths. confidence is "high", "low", or "none"
	(unchanged). evidence lists short human-readable strings explaining why
	the classifier reached this decision.
	"""

	src: pathlib.Path
	dst: pathlib.Path | None
	confidence: str
	bucket: str
	evidence: tuple[str, ...]


def _season_from_month(month: int) -> str:
	# Plan rule: Jan-May -> spring, Jun-Jul -> summer, Aug-Dec -> fall.
	if 1 <= month <= 5:
		return "spring"
	if 6 <= month <= 7:
		return "summer"
	return "fall"


def _term_from_stat(st: os.stat_result) -> tuple[str, str]:
	# Prefer macOS birthtime; fall back to mtime. Never use st_ctime.
	# Returns (term_string, evidence_string).
	birthtime = getattr(st, "st_birthtime", None)
	if birthtime:
		ts = birthtime
		source = "birthtime"
	else:
		ts = st.st_mtime
		source = "mtime"
	struct = time.localtime(ts)
	term = f"{_season_from_month(struct.tm_mon)}_{struct.tm_year:04d}"
	evidence = f"{source}={time.strftime('%Y-%m-%d', struct)} -> {term}"
	return term, evidence


def _legacy_review_dst(data_root: pathlib.Path, bucket: str, name: str) -> pathlib.Path:
	return data_root / "legacy" / "needs_review" / bucket / name


def _term_dst(data_root: pathlib.Path, term: str, *parts: str) -> pathlib.Path:
	return data_root.joinpath("semesters", term, *parts)


def classify(src: pathlib.Path, data_root: pathlib.Path, active_term: str) -> Move:
	"""Classify a single top-level entry inside data_root.

	`src` must be a direct child of `data_root`. The function does not
	recurse; the planner handles tree walking.
	"""
	name = src.name

	# Already canonical: leave alone.
	if name in CANONICAL_TOP_LEVEL:
		return Move(src=src, dst=None, confidence="none", bucket="unchanged",
			evidence=("already canonical name",))

	# Hardcoded "send to legacy/needs_review/" folders.
	if src.is_dir() and name in LEGACY_FOLDER_NEEDS_REVIEW:
		bucket_subdir = LEGACY_FOLDER_NEEDS_REVIEW[name]
		dst = _legacy_review_dst(data_root, bucket_subdir, name)
		return Move(src=src, dst=dst, confidence="low", bucket="legacy_review_moves",
			evidence=(f"name match: legacy folder {name}",))

	# ARCHIVE_IMAGES/ -> image_bank/ (high confidence).
	if src.is_dir() and name == "ARCHIVE_IMAGES":
		return Move(src=src, dst=data_root / "image_bank", confidence="high",
			bucket="high_confidence_moves",
			evidence=("name match: ARCHIVE_IMAGES",))

	# Legacy per-term roots (e.g., 2024_Spring/, 2025_1Spring/).
	if src.is_dir():
		match = RE_LEGACY_TERM_FOLDER.match(name)
		if match:
			year = match.group("year")
			season = match.group("season").lower()
			term = f"{season}_{year}"
			dst = _term_dst(data_root, term)
			return Move(src=src, dst=dst, confidence="high",
				bucket="high_confidence_moves",
				evidence=(f"name match: {season} {year} -> {term}",))

	# DOWNLOAD_NN_year_YYYY/ -> semesters/spring_YYYY/submissions/download_NN_raw/.
	# (Spring is hardcoded for this course; only one term per year.)
	if src.is_dir():
		match = RE_LEGACY_DOWNLOAD.match(name)
		if match:
			num = match.group("num")
			year = match.group("year")
			term = f"spring_{year}"
			dst = _term_dst(data_root, term, "submissions", f"download_{num}_raw")
			return Move(src=src, dst=dst, confidence="high",
				bucket="high_confidence_moves",
				evidence=(f"name match: DOWNLOAD_{num}_year_{year} -> {term}",))

	# IMAGE_NN/ -> semesters/<inferred_term>/submissions/image_NN/.
	# Term inferred from filesystem timestamp; medium confidence overall, so
	# we route to legacy_review_moves rather than high_confidence_moves.
	if src.is_dir():
		match = RE_LEGACY_IMAGE.match(name)
		if match:
			num = match.group("num")
			term, ts_evidence = _term_from_stat(src.stat())
			dst = _term_dst(data_root, term, "submissions", f"image_{num}")
			return Move(src=src, dst=dst, confidence="low",
				bucket="legacy_review_moves",
				evidence=(f"name match: IMAGE_{num}", ts_evidence,
					"term inferred from timestamp; verify before apply"))

	# BCHM_Prot_Img_NN-*.csv at data_root -> active term forms/.
	if src.is_file() and RE_LEGACY_FORM_CSV.match(name):
		dst = _term_dst(data_root, active_term, "forms", name)
		return Move(src=src, dst=dst, confidence="high",
			bucket="high_confidence_moves",
			evidence=(f"name match: form csv -> {active_term}/forms/",))

	# roster_YYYY.csv -> semesters/spring_YYYY/roster.csv.
	if src.is_file():
		match = RE_LEGACY_ROSTER_DATED.match(name)
		if match:
			year = match.group("year")
			term = f"spring_{year}"
			dst = _term_dst(data_root, term, "roster.csv")
			return Move(src=src, dst=dst, confidence="high",
				bucket="high_confidence_moves",
				evidence=(f"name match: roster_{year} -> {term}",))

	# current_students.csv -> active term roster.csv (medium).
	if src.is_file() and name == "current_students.csv":
		dst = _term_dst(data_root, active_term, "roster.csv")
		return Move(src=src, dst=dst, confidence="low",
			bucket="legacy_review_moves",
			evidence=("name match: current_students.csv",
				f"defaulting to active term {active_term}; confirm before apply"))

	# <Season>_<YYYY>_IDs.txt -> semesters/<season>_<year>/roster_ids.txt.
	if src.is_file():
		match = RE_LEGACY_TERM_IDS.match(name)
		if match:
			season = match.group("season").lower()
			year = match.group("year")
			term = f"{season}_{year}"
			dst = _term_dst(data_root, term, "roster_ids.txt")
			return Move(src=src, dst=dst, confidence="high",
				bucket="high_confidence_moves",
				evidence=(f"name match: {season}_{year}_IDs.txt -> {term}",))

	# *.py symlinks -> legacy/needs_review/broken_symlinks/.
	if src.is_symlink() and name.endswith(".py"):
		dst = _legacy_review_dst(data_root, "broken_symlinks", name)
		return Move(src=src, dst=dst, confidence="high",
			bucket="legacy_review_moves",
			evidence=("symlink with .py extension",))

	# Per-name file rules (state files, scratch, requirements.txt, credentials).
	if src.is_file() or src.is_symlink():
		for pattern, bucket_subdir, evidence_tag in LEGACY_FILE_RULES:
			if pattern.match(name):
				dst = _legacy_review_dst(data_root, bucket_subdir, name)
				return Move(src=src, dst=dst, confidence="low",
					bucket="legacy_review_moves",
					evidence=(f"{evidence_tag}: {name}",))

	# Default: unknown legacy item -> legacy/needs_review/scratch/.
	dst = _legacy_review_dst(data_root, "scratch", name)
	return Move(src=src, dst=dst, confidence="low", bucket="legacy_review_moves",
		evidence=("no rule matched; routed to scratch for human review",))
