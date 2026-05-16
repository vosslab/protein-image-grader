"""
Unit tests for protein_image_grader.grade_status.

Covers the shared helpers used by the checkpoint-aware resume system:
student_key, is_image_complete, find_checkpoints, validate_checkpoint,
pick_checkpoint, and count_graded_students_from_yaml.
"""

# Standard Library
import pathlib

# PIP3 modules
import pytest
import yaml

# local repo modules
import protein_image_grader.grade_status as grade_status


def _write_yaml(path: pathlib.Path, obj) -> pathlib.Path:
	path.write_text(yaml.safe_dump(obj), encoding="utf-8")
	return path


def _complete_entry(sid, image_number=1, **extra):
	# Minimal cached student row that should pass validation and count
	# as graded. Extra kwargs override defaults for targeted tests.
	row = {
		"Student ID": sid,
		"Image Assessment Complete": True,
		"Protein Image Number": image_number,
	}
	row.update(extra)
	return row


# ---- student_key ---------------------------------------------------------

def test_student_key_coerces_int_to_stripped_string():
	assert grade_status.student_key({"Student ID": 900000001}) == "900000001"


def test_student_key_strips_whitespace():
	assert grade_status.student_key({"Student ID": "  900000001  "}) == "900000001"


def test_student_key_raises_on_missing_field():
	# Missing key surfaces as KeyError so a caller that expected the
	# field finds out loudly rather than via a silent fallback value.
	with pytest.raises(KeyError):
		grade_status.student_key({})


def test_student_key_raises_on_blank_field():
	with pytest.raises(ValueError):
		grade_status.student_key({"Student ID": "   "})


# ---- is_image_complete ---------------------------------------------------

def test_is_image_complete_accepts_python_true():
	assert grade_status.is_image_complete(True) is True


def test_is_image_complete_accepts_string_true_case_insensitive():
	assert grade_status.is_image_complete("true") is True
	assert grade_status.is_image_complete("True") is True
	assert grade_status.is_image_complete("  TRUE  ") is True


def test_is_image_complete_rejects_false_values():
	for value in [False, "false", "False", "no", None, 0, 1, "yes"]:
		assert grade_status.is_image_complete(value) is False, value


# ---- find_checkpoints ----------------------------------------------------

def test_find_checkpoints_empty_dir_returns_empty_list(tmp_path):
	assert grade_status.find_checkpoints(tmp_path, 1) == []


def test_find_checkpoints_returns_deepest_first_when_all_present(tmp_path):
	# Drop one of every catalog file in the dir.
	for template, _label in grade_status.CHECKPOINT_PRECEDENCE:
		filename = template.format(nn=3) if "{nn" in template else template
		(tmp_path / filename).write_text("[]", encoding="utf-8")
	hits = grade_status.find_checkpoints(tmp_path, 3)
	# Behavioral check: every catalog file is found and the output
	# checkpoint (always rank 0) sorts first. Avoid asserting the full
	# ordered list of labels so the test does not break when the
	# catalog gains a future entry; the precedence-by-rank guarantee
	# is what matters.
	assert len(hits) == len(grade_status.CHECKPOINT_PRECEDENCE)
	assert hits[0].label == "output"
	# Hits are sorted by rank_index ascending.
	for earlier, later in zip(hits, hits[1:]):
		assert earlier.rank_index < later.rank_index


def test_find_checkpoints_skips_missing_files(tmp_path):
	# Only post-images and downloaded exist; output and post-questions absent.
	(tmp_path / "post-images_save.yml").write_text("[]", encoding="utf-8")
	(tmp_path / "downloaded_images.yml").write_text("[]", encoding="utf-8")
	hits = grade_status.find_checkpoints(tmp_path, 5)
	assert [hit.label for hit in hits] == ["post-images", "downloaded"]


# ---- validate_checkpoint -------------------------------------------------

def test_validate_checkpoint_accepts_well_formed_list():
	# Should not raise.
	grade_status.validate_checkpoint([_complete_entry("900000001")])


def test_validate_checkpoint_rejects_non_list():
	with pytest.raises(ValueError):
		grade_status.validate_checkpoint({"Student ID": "900000001"})


def test_validate_checkpoint_rejects_non_dict_entry():
	with pytest.raises(ValueError):
		grade_status.validate_checkpoint(["not-a-dict"])


def test_validate_checkpoint_rejects_blank_student_id():
	with pytest.raises(ValueError):
		grade_status.validate_checkpoint([{"Student ID": "  "}])


def test_validate_checkpoint_rejects_duplicate_student_id():
	rows = [_complete_entry("900000001"), _complete_entry("900000001")]
	with pytest.raises(ValueError) as excinfo:
		grade_status.validate_checkpoint(rows)
	assert "duplicate Student ID" in str(excinfo.value)


def test_validate_checkpoint_cross_checks_image_number_when_provided():
	rows = [_complete_entry("900000001", image_number=2)]
	with pytest.raises(ValueError):
		grade_status.validate_checkpoint(rows, image_number=3)


def test_validate_checkpoint_skips_image_number_when_field_absent():
	# A row without Protein Image Number should not trigger the cross-check.
	rows = [{"Student ID": "900000001"}]
	# Should not raise even though image_number=3 is provided.
	grade_status.validate_checkpoint(rows, image_number=3)


# ---- pick_checkpoint -----------------------------------------------------

def test_pick_checkpoint_unique_deepest(tmp_path):
	output_path = tmp_path / "output-protein_image_03.yml"
	_write_yaml(output_path, [_complete_entry("900000001", image_number=3)])
	(tmp_path / "preprocess_save.yml").write_text("[]", encoding="utf-8")
	pick = grade_status.pick_checkpoint(tmp_path, 3)
	assert pick.chosen == output_path
	assert pick.label == "output"
	assert pick.conflict is False
	# Both files appear in the candidate list, deepest-first.
	assert [hit.label for hit in pick.candidates] == ["output", "preprocess"]


def test_pick_checkpoint_no_files_returns_none(tmp_path):
	pick = grade_status.pick_checkpoint(tmp_path, 1)
	assert pick.chosen is None
	assert pick.candidates == []
	assert pick.conflict is False


def test_pick_checkpoint_marks_conflict_on_parse_failure(tmp_path):
	bad = tmp_path / "output-protein_image_01.yml"
	bad.write_text("not: valid: yaml: ::", encoding="utf-8")
	pick = grade_status.pick_checkpoint(tmp_path, 1)
	assert pick.chosen is None
	assert pick.conflict is True
	assert "parse failure" in pick.conflict_reason


def test_pick_checkpoint_marks_conflict_on_validation_failure(tmp_path):
	# Two entries with the same Student ID -> validate_checkpoint raises.
	bad = tmp_path / "output-protein_image_02.yml"
	_write_yaml(bad, [
		_complete_entry("900000001", image_number=2),
		_complete_entry("900000001", image_number=2),
	])
	pick = grade_status.pick_checkpoint(tmp_path, 2)
	assert pick.chosen is None
	assert pick.conflict is True
	assert "validation failed" in pick.conflict_reason


def test_pick_checkpoint_marks_conflict_on_image_number_mismatch(tmp_path):
	# YAML carries image_number=5 but caller asked for 7.
	bad = tmp_path / "output-protein_image_07.yml"
	_write_yaml(bad, [_complete_entry("900000001", image_number=5)])
	pick = grade_status.pick_checkpoint(tmp_path, 7)
	assert pick.chosen is None
	assert pick.conflict is True


# ---- count_graded_students_from_yaml -------------------------------------

def test_count_graded_students_from_yaml_counts_only_complete(tmp_path):
	path = tmp_path / "output-protein_image_01.yml"
	rows = [
		_complete_entry("900000001"),
		_complete_entry("900000002"),
		_complete_entry("900000003"),
		_complete_entry("900000004", **{"Image Assessment Complete": False}),
	]
	_write_yaml(path, rows)
	assert grade_status.count_graded_students_from_yaml(path) == 3


def test_graded_student_ids_from_yaml_returns_only_complete_ids(tmp_path):
	path = tmp_path / "output-protein_image_01.yml"
	rows = [
		_complete_entry("900000001"),
		_complete_entry("900000002",
			**{"Image Assessment Complete": False}),
		_complete_entry("900000003"),
	]
	_write_yaml(path, rows)
	student_ids = grade_status.graded_student_ids_from_yaml(path)
	assert student_ids == {"900000001", "900000003"}


def test_count_graded_students_from_yaml_accepts_string_true(tmp_path):
	# A historical YAML written with string-typed booleans should still count.
	path = tmp_path / "output-protein_image_01.yml"
	rows = [_complete_entry("900000001", **{"Image Assessment Complete": "true"})]
	_write_yaml(path, rows)
	assert grade_status.count_graded_students_from_yaml(path) == 1


def test_count_graded_students_from_yaml_raises_on_validation_failure(tmp_path):
	path = tmp_path / "bad.yml"
	_write_yaml(path, [{"Student ID": ""}])
	with pytest.raises(ValueError):
		grade_status.count_graded_students_from_yaml(path)
