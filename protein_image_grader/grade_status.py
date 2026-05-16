"""
Shared helpers for the grader's checkpoint-aware resume system.

Holds three small concerns that are used by `grade_protein_image`,
`interactive_image_criteria_class`, and `start_grading`:

- Student identity: a stable key for matching form rows against cached
  YAML entries.
- Per-stage checkpoint catalog and picker: the canonical filenames the
  grader writes, in deepest-first precedence order, plus the picker that
  selects the best resume point for a given image_dir.
- Validation: structural checks the resume code runs before trusting a
  checkpoint YAML.

The module performs no filesystem I/O at import time.
"""

# Standard Library
import dataclasses
import pathlib

# PIP3 modules
import yaml


# Catalog of per-stage checkpoint filenames in deepest-first precedence
# order (most work preserved first). Each entry is (filename_template,
# label). The output template accepts the image number via
# str.format(nn=...). All other filenames are constants and ignore
# the image number.
#
# Order matches the actual write sequence in grade_protein_image.process_data:
#   downloaded_images.yml      (after read_and_save_student_images)
#   duplicate_check_save.yml   (after check_duplicate_images)
#   preprocess_save.yml        (after timestamp_due_date loop -- name
#                              refers to "Pre-Processing Turn In Date",
#                              NOT the earliest stage)
#   post-questions_save.yml    (after process_csv_question for all CSV questions)
#   post-images_save.yml       (after process_image_questions_class for all students)
#   output-protein_image_NN.yml (final, after final-score + exports)
#
# Resuming from a deeper checkpoint preserves strictly more graded
# state, so the picker's deepest-first scan minimizes redundant work.
CHECKPOINT_PRECEDENCE = (
	("output-protein_image_{nn:02d}.yml", "output"),
	("post-images_save.yml",               "post-images"),
	("post-questions_save.yml",            "post-questions"),
	("preprocess_save.yml",                "preprocess"),
	("duplicate_check_save.yml",           "duplicate-check"),
	("downloaded_images.yml",              "downloaded"),
)


#============================================
@dataclasses.dataclass(frozen=True)
class CheckpointHit:
	"""One existing checkpoint file located by `find_checkpoints`."""
	path: pathlib.Path
	label: str
	rank_index: int


#============================================
@dataclasses.dataclass(frozen=True)
class PickResult:
	"""Result returned by `pick_checkpoint`.

	`chosen` is the deepest valid checkpoint, or None when no checkpoints
	exist on disk. `candidates` is the full deepest-first list of every
	existing checkpoint file (always populated when at least one exists).
	`conflict` is True when the deepest existing file is unsafe to use --
	either it failed YAML parsing, or `validate_checkpoint` rejected its
	contents, or two distinct files matched the same canonical template.
	`conflict_reason` carries the human-readable explanation.
	"""
	chosen: pathlib.Path | None
	label: str | None
	candidates: list[CheckpointHit]
	conflict: bool
	conflict_reason: str | None


#============================================
def student_key(entry: dict) -> str:
	"""Return the canonical Student ID key for one YAML or form-row dict.

	Coerces the value to a stripped string so int/str differences between
	the form CSV and the cached YAML do not produce a silent merge miss.

	Args:
		entry: A dict carrying at least a `Student ID` field.

	Returns:
		The stripped string form of the Student ID.

	Raises:
		KeyError: if the `Student ID` key is missing entirely.
		ValueError: if the value is present but blank after stripping.
	"""
	# Direct key access (not .get) so a missing field fails loudly with
	# KeyError per docs/PYTHON_STYLE.md "do not hide bugs with defaults".
	sid = str(entry["Student ID"]).strip()
	if not sid:
		raise ValueError("entry has a blank Student ID")
	return sid


#============================================
def is_image_complete(value) -> bool:
	"""Return True when `value` indicates the image-question prompt is done.

	Accepts both Python `True` and a case-insensitive string `"true"` so
	historical YAMLs that wrote the field as a string still gate
	correctly. Any other value (including the operator's manual `false`,
	None, missing key) returns False.
	"""
	if value is True:
		return True
	if isinstance(value, str) and value.strip().lower() == "true":
		return True
	return False


#============================================
def _checkpoint_filename(template: str, image_number: int) -> str:
	# Render one CHECKPOINT_PRECEDENCE filename for the given image
	# number. Templates without an `{nn` slot pass through unchanged.
	if "{nn" in template:
		return template.format(nn=image_number)
	return template


#============================================
def find_checkpoints(image_dir: pathlib.Path,
		image_number: int) -> list[CheckpointHit]:
	"""Return existing checkpoint files in deepest-first order.

	Scans `image_dir` for the canonical filenames in
	CHECKPOINT_PRECEDENCE. Missing files are skipped. The returned list
	is empty when no checkpoints exist.

	Args:
		image_dir: The per-image folder under
			`Protein_Images/semesters/<term>/`.
		image_number: The image number used to render the output
			filename template.

	Returns:
		Deepest-first list of CheckpointHit entries.
	"""
	hits = []
	for rank_index, (template, label) in enumerate(CHECKPOINT_PRECEDENCE):
		filename = _checkpoint_filename(template, image_number)
		candidate = image_dir / filename
		if candidate.is_file():
			hits.append(CheckpointHit(
				path=candidate,
				label=label,
				rank_index=rank_index,
			))
	return hits


#============================================
def validate_checkpoint(yaml_obj, image_number: int | None = None) -> None:
	"""Validate the structural shape of a loaded checkpoint YAML.

	The grader contract requires a flat list of student dicts. Each dict
	must carry a non-empty `Student ID`; no two entries may share one.
	When `image_number` is supplied, every entry that carries a
	`Protein Image Number` field must equal it (cross-check guards the
	operator from pointing a regrade at the wrong image's checkpoint).

	Args:
		yaml_obj: The Python object produced by `yaml.safe_load`.
		image_number: Optional expected image number for the cross-check.

	Raises:
		ValueError: with a specific message on any structural failure.
	"""
	if not isinstance(yaml_obj, list):
		raise ValueError(
			f"checkpoint YAML must be a list, got {type(yaml_obj).__name__}"
		)
	seen_ids: dict[str, int] = {}
	for index, entry in enumerate(yaml_obj):
		if not isinstance(entry, dict):
			raise ValueError(
				f"checkpoint entry {index} is not a dict: "
				f"{type(entry).__name__}"
			)
		sid = str(entry.get("Student ID", "")).strip()
		if not sid:
			raise ValueError(
				f"checkpoint entry {index} has missing or blank Student ID"
			)
		if sid in seen_ids:
			raise ValueError(
				f"duplicate Student ID {sid!r} in checkpoint at "
				f"entries {seen_ids[sid]} and {index}"
			)
		seen_ids[sid] = index
		# Image-number cross-check is only enforced when the entry
		# explicitly carries the field. Older preprocess checkpoints may
		# not have it yet; that is fine.
		if image_number is not None and "Protein Image Number" in entry:
			recorded = entry["Protein Image Number"]
			if recorded != image_number:
				raise ValueError(
					f"checkpoint entry {index} has Protein Image Number "
					f"{recorded!r}, expected {image_number}"
				)


#============================================
def pick_checkpoint(image_dir: pathlib.Path,
		image_number: int) -> PickResult:
	"""Pick the best resume checkpoint for an image_dir.

	Walks CHECKPOINT_PRECEDENCE deepest-first and returns the first
	existing file. If that file fails YAML parsing or
	`validate_checkpoint`, the result is marked as a conflict and the
	caller (dashboard or regrade) decides how to surface it.

	Args:
		image_dir: The per-image folder.
		image_number: The image number used to render the output
			filename template AND to cross-check entries.

	Returns:
		A PickResult describing the chosen file (or None), the full
		candidate list, and a conflict flag with reason.
	"""
	candidates = find_checkpoints(image_dir, image_number)
	if not candidates:
		return PickResult(
			chosen=None,
			label=None,
			candidates=[],
			conflict=False,
			conflict_reason=None,
		)

	# Defensive guard: each rank should map to one canonical filename, so
	# two hits at the same rank should never happen. If it does, refuse
	# to guess which one is authoritative.
	deepest = candidates[0]
	same_rank_dupes = [
		hit for hit in candidates[1:] if hit.rank_index == deepest.rank_index
	]
	if same_rank_dupes:
		dupe_paths = ", ".join(str(hit.path) for hit in same_rank_dupes)
		reason = (
			f"two checkpoint files share rank {deepest.rank_index} "
			f"({deepest.label}): {deepest.path} and {dupe_paths}"
		)
		return PickResult(
			chosen=None,
			label=None,
			candidates=candidates,
			conflict=True,
			conflict_reason=reason,
		)

	# Try to parse + validate the deepest. Any failure marks the pick
	# CONFLICT; the dashboard will display CONFLICT and the regrade will
	# abort with this same reason.
	with open(deepest.path, "r", encoding="utf-8") as handle:
		try:
			loaded = yaml.safe_load(handle)
		except yaml.YAMLError as exc:
			return PickResult(
				chosen=None,
				label=None,
				candidates=candidates,
				conflict=True,
				conflict_reason=f"YAML parse failure in {deepest.path}: {exc}",
			)
	try:
		validate_checkpoint(loaded, image_number=image_number)
	except ValueError as exc:
		return PickResult(
			chosen=None,
			label=None,
			candidates=candidates,
			conflict=True,
			conflict_reason=f"validation failed for {deepest.path}: {exc}",
		)

	return PickResult(
		chosen=deepest.path,
		label=deepest.label,
		candidates=candidates,
		conflict=False,
		conflict_reason=None,
	)


#============================================
def count_graded_students_from_yaml(yaml_path: pathlib.Path) -> int:
	"""Count YAML entries whose image-question grading is complete.

	Loads `yaml_path`, validates it, then counts entries where
	`is_image_complete(entry["Image Assessment Complete"])` is True.
	Validation is performed without the image-number cross-check so the
	helper can be used for status display when the caller does not know
	the image number; callers that DO know the number (the dashboard)
	go through `pick_checkpoint` first which already cross-checks.

	Args:
		yaml_path: Path to a checkpoint YAML file.

	Returns:
		The number of students whose image-question pass is complete.

	Raises:
		ValueError: when the file fails `validate_checkpoint`.
	"""
	with open(yaml_path, "r", encoding="utf-8") as handle:
		loaded = yaml.safe_load(handle)
	validate_checkpoint(loaded)
	count = 0
	for entry in loaded:
		if is_image_complete(entry.get("Image Assessment Complete")):
			count += 1
	return count


#============================================
def graded_student_ids_from_yaml(yaml_path: pathlib.Path) -> set:
	"""Return Student IDs whose image-question grading is complete.

	This mirrors `count_graded_students_from_yaml`, but returns the actual
	Student IDs so callers can compare downstream state against submitters
	instead of just comparing counts.

	Args:
		yaml_path: Path to a checkpoint YAML file.

	Returns:
		Set of canonical Student ID strings for completed image rows.

	Raises:
		ValueError: when the file fails `validate_checkpoint`.
	"""
	with open(yaml_path, "r", encoding="utf-8") as handle:
		loaded = yaml.safe_load(handle)
	validate_checkpoint(loaded)
	student_ids = set()
	for entry in loaded:
		if is_image_complete(entry.get("Image Assessment Complete")):
			student_ids.add(student_key(entry))
	return student_ids
