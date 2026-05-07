"""
Unit tests for the image-question skip gate in
protein_image_grader.interactive_image_criteria_class.

The gate at the top of process_image_questions skips a student whose
`Image Assessment Complete` is true, formalized via
grade_status.is_image_complete. The skip applies ONLY to the
interactive image-question prompt; downstream code (CSV-question
processing, final-score, exports) still runs.
"""

# PIP3 modules
import pytest

# local repo modules
import protein_image_grader.interactive_image_criteria_class as iic
import protein_image_grader.student_id_protein as sip


def _stub_input_validation(*_args, **_kwargs):
	# If the gate fires, the prompt is never reached. If it does not,
	# the test surfaces the bug as a loud error rather than blocking
	# on stdin.
	raise AssertionError(
		"image-question prompt should have been skipped by the gate"
	)


def _cached_student(**overrides):
	# Minimal cached student that print_student_info can render and
	# whose Image Assessment Complete is True by default.
	row = {
		"First Name": "Pat",
		"Last Name": "Roe",
		"Student ID": "900000001",
		"Original Filename": "image_1.png",
		"Image Assessment Complete": True,
	}
	row.update(overrides)
	return row


def _make_processor(student_tree):
	config = {"image_questions": []}
	return iic.process_image_questions_class(student_tree, config)


def test_gate_skips_when_image_assessment_complete_is_true(monkeypatch):
	monkeypatch.setattr(sip, "get_input_validation", _stub_input_validation)
	student = _cached_student()
	processor = _make_processor([student])
	# Should return without invoking the stub prompt.
	processor.process_image_questions(student)


def test_gate_accepts_string_true_for_legacy_yaml(monkeypatch):
	# Older YAMLs may have written the field as a string. The shared
	# is_image_complete helper accepts that; so should the gate.
	monkeypatch.setattr(sip, "get_input_validation", _stub_input_validation)
	student = _cached_student(**{"Image Assessment Complete": "true"})
	processor = _make_processor([student])
	processor.process_image_questions(student)


def test_gate_does_not_skip_when_image_assessment_complete_false(monkeypatch):
	# Operator's manual escape hatch: flipping the field to false must
	# re-prompt for that student. The stub raises so we know the gate
	# did NOT fire.
	monkeypatch.setattr(sip, "get_input_validation", _stub_input_validation)
	student = _cached_student(
		**{"Image Assessment Complete": False,
			"Consensus Background Color": "White",
			"Image Format": "PNG",
			"Exact Match": False,
			"extra description": "",
			"Warnings": []},
	)
	processor = _make_processor([student])
	with pytest.raises(AssertionError) as excinfo:
		processor.process_image_questions(student)
	assert "should have been skipped" in str(excinfo.value)


def test_gate_skips_cached_student_missing_original_filename(monkeypatch):
	# Regression guard for the gate-position fix: a crash-recovery
	# YAML row may carry `Image Assessment Complete: True` without an
	# `Original Filename` field. The gate must fire BEFORE
	# print_student_info / the Original Filename print so resume is
	# robust against partial rows. If the gate ever moves below those
	# field accesses, this test crashes with KeyError instead of
	# silently skipping.
	monkeypatch.setattr(sip, "get_input_validation", _stub_input_validation)
	student = {
		# Note: NO `Original Filename` and NO `First Name`/`Last Name`
		# (print_student_info reads both). Only the gate field is set.
		"Student ID": "900000001",
		"Image Assessment Complete": True,
	}
	processor = _make_processor([student])
	# Must return cleanly; KeyError here means the gate regressed
	# below the field access.
	processor.process_image_questions(student)


def test_gate_does_not_skip_when_field_absent(monkeypatch):
	# A fresh student row with no `Image Assessment Complete` key at
	# all must run the prompt. Same shape as the False-value case.
	monkeypatch.setattr(sip, "get_input_validation", _stub_input_validation)
	student = _cached_student(
		**{"Consensus Background Color": "White",
			"Image Format": "PNG",
			"Exact Match": False,
			"extra description": "",
			"Warnings": []},
	)
	del student["Image Assessment Complete"]
	processor = _make_processor([student])
	with pytest.raises(AssertionError):
		processor.process_image_questions(student)
