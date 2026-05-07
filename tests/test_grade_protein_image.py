"""
Unit tests for protein_image_grader.grade_protein_image merge helpers.

Covers the YAML+CSV merge logic that drives the checkpoint-aware
resume system: identity by Student ID only, no-overwrite backfill of
form-row keys into matched YAML rows, duplicate-key rejection on both
sides, and YAML-only row preservation with a warning.
"""

# Standard Library
import argparse

# PIP3 modules
import pytest
import yaml

# local repo modules
import protein_image_grader.grade_protein_image as gpi


def _form_row(sid, first="Pat", last="Roe", **extra):
	row = {
		"Student ID": sid,
		"timestamp": "2026/04/16 1:00:00 PM EST",
		"First Name": first,
		"Last Name": last,
		"Username": f"{first.lower()}{last.lower()}",
		"Protein Image Number": 1,
		"Warnings": [],
	}
	row.update(extra)
	return row


def _cached_yaml_row(sid, **extra):
	# A cached YAML row carries grading fields the form row will not.
	row = {
		"Student ID": sid,
		"timestamp": "2026/04/16 1:00:00 PM EST",
		"First Name": "Pat",
		"Last Name": "Roe",
		"Username": "patroe",
		"Protein Image Number": 1,
		"Image Assessment Complete": True,
		"128-bit MD5 Hash": "deadbeef",
		"Image Format": "PNG",
		"Final Score": "5.00",
	}
	row.update(extra)
	return row


# ---- _validate_unique_form_student_ids -----------------------------------

def test_validate_form_rejects_duplicate_student_id():
	form_tree = [_form_row("900000001"), _form_row("900000001")]
	with pytest.raises(ValueError) as excinfo:
		gpi._validate_unique_form_student_ids(form_tree)
	assert "900000001" in str(excinfo.value)


def test_validate_form_accepts_distinct_student_ids():
	form_tree = [_form_row("900000001"), _form_row("900000002")]
	# Should not raise; the two rows have distinct Student IDs.
	gpi._validate_unique_form_student_ids(form_tree)


# ---- _merge_yaml_into_form -----------------------------------------------

def test_merge_matched_rows_use_yaml_grading_fields():
	# Three form submissions; YAML cached two of them. Merged tree
	# preserves form-row order and the matched entries carry the
	# YAML's hashes / statuses while the unmatched entry carries only
	# the form fields.
	form_tree = [
		_form_row("900000001", first="Alice"),
		_form_row("900000002", first="Bob"),
		_form_row("900000003", first="Carol"),
	]
	yaml_tree = [
		_cached_yaml_row("900000001", **{"First Name": "Alice"}),
		_cached_yaml_row("900000002", **{"First Name": "Bob"}),
	]
	merged = gpi._merge_yaml_into_form(form_tree, yaml_tree)
	assert len(merged) == 3
	# Order matches the form CSV order.
	assert [row["Student ID"] for row in merged] == [
		"900000001", "900000002", "900000003",
	]
	# Matched rows carry the YAML's grading fields.
	assert merged[0]["Image Assessment Complete"] is True
	assert merged[0]["128-bit MD5 Hash"] == "deadbeef"
	assert merged[0]["Final Score"] == "5.00"
	assert merged[1]["Image Assessment Complete"] is True
	# Unmatched row has none of the YAML grading fields.
	assert "Image Assessment Complete" not in merged[2]
	assert "128-bit MD5 Hash" not in merged[2]


def test_merge_backfills_new_form_columns_into_cached_row():
	# Form CSV added a new question column after the cached student
	# was graded. The merged row inherits the YAML's cached fields AND
	# the new form-side column -- the no-overwrite rule fires only for
	# keys that already exist in the YAML row.
	form_tree = [_form_row("900000001",
		**{"How many helices?": "5"})]
	yaml_tree = [_cached_yaml_row("900000001")]
	merged = gpi._merge_yaml_into_form(form_tree, yaml_tree)
	assert len(merged) == 1
	# Cached YAML field stays.
	assert merged[0]["Final Score"] == "5.00"
	# New form-side column was backfilled in.
	assert merged[0]["How many helices?"] == "5"


def test_merge_preserves_yaml_value_when_form_has_same_key():
	# Pre-existing YAML field must NOT be overwritten by a same-name
	# form field. This protects cached grading work from being silently
	# lost when the form CSV happens to carry a key the YAML wrote.
	form_tree = [_form_row("900000001", first="Patty")]
	yaml_tree = [_cached_yaml_row("900000001", **{"First Name": "Pat"})]
	merged = gpi._merge_yaml_into_form(form_tree, yaml_tree)
	assert merged[0]["First Name"] == "Pat"  # YAML wins


def test_merge_keeps_yaml_only_row_with_warning(capsys):
	# YAML carries a Student ID no longer in the form CSV (operator
	# removed the row). The cached row is preserved at the end of the
	# merged tree and a warning is emitted.
	form_tree = [_form_row("900000001"), _form_row("900000002")]
	yaml_tree = [
		_cached_yaml_row("900000001"),
		_cached_yaml_row("900000099"),  # not in form CSV
	]
	merged = gpi._merge_yaml_into_form(form_tree, yaml_tree)
	assert [row["Student ID"] for row in merged] == [
		"900000001", "900000002", "900000099",
	]
	output = capsys.readouterr().out
	assert "yaml-only student 900000099" in output


def test_merge_resubmission_is_not_auto_regraded():
	# Operator workflow: a student submits the form again with a new
	# timestamp. Identity is Student ID only, so the cached YAML row
	# wins; the new form submission is silently absorbed. To regrade
	# this student the operator must delete the YAML row.
	cached_timestamp = "2026/04/16 1:00:00 PM EST"
	resubmit_timestamp = "2026/05/01 9:30:00 AM EST"
	form_tree = [_form_row("900000001", timestamp=resubmit_timestamp)]
	yaml_tree = [_cached_yaml_row("900000001", timestamp=cached_timestamp)]
	merged = gpi._merge_yaml_into_form(form_tree, yaml_tree)
	# Merged row carries the cached YAML timestamp, not the resubmit.
	# Behavioral assertion: the field equals the YAML fixture's value
	# (whatever it is) rather than a hardcoded literal.
	assert merged[0]["timestamp"] == yaml_tree[0]["timestamp"]
	assert merged[0]["timestamp"] != resubmit_timestamp
	assert merged[0]["Image Assessment Complete"] is True


def test_merge_idempotent_on_dump_load_round_trip(tmp_path):
	# Re-running merge on the YAML produced by a prior merge yields a
	# semantically identical tree (no duplicates, no field changes,
	# no spurious warnings). Field-order drift in the YAML dump does
	# not matter because we compare loaded dicts.
	form_tree = [_form_row("900000001"), _form_row("900000002")]
	yaml_tree = [
		_cached_yaml_row("900000001"),
		_cached_yaml_row("900000002"),
	]
	first_merge = gpi._merge_yaml_into_form(form_tree, yaml_tree)
	# Round-trip the merged tree through YAML to mirror what
	# backup_tree_to_yaml + safe_load would do at end of a real run.
	dumped = yaml.safe_dump(first_merge)
	reloaded = yaml.safe_load(dumped)
	second_merge = gpi._merge_yaml_into_form(form_tree, reloaded)
	assert len(second_merge) == 2
	for first, second in zip(first_merge, second_merge):
		assert first == second


def test_merge_raises_on_duplicate_student_id_inside_yaml():
	# WP6b case 5: a checkpoint YAML containing two entries for the
	# same Student ID is structurally bad input. _merge_yaml_into_form
	# must raise rather than silently use the last-seen entry.
	form_tree = [_form_row("900000001")]
	yaml_tree = [
		_cached_yaml_row("900000001"),
		_cached_yaml_row("900000001"),
	]
	with pytest.raises(ValueError) as excinfo:
		gpi._merge_yaml_into_form(form_tree, yaml_tree)
	assert "900000001" in str(excinfo.value)


# ---- WP6b case 9: CSV-question gate behavior on cached students ----------

def _question_dict():
	# Minimal question shape that group_student_responses + the auto
	# grader handle without needing a full spec YAML.
	return {
		"name": "Number of Helices",
		"type": "int",
		"correct": [{"value": "5", "deduction": 0, "feedback": "ok"}],
	}


def test_csv_question_gate_skips_when_status_already_populated(monkeypatch):
	# WP6b case 9 (skip half): a student whose `<Q> Status` is already
	# populated must not invoke the grader. Stub auto_grade to raise so
	# any reach into the grader fails the test loudly.
	question = _question_dict()
	q_name = question["name"]
	cached_student = {
		"Student ID": "900000001",
		"First Name": "Alice",
		"Last Name": "Aaa",
		q_name: "5",
		f"{q_name} Status": "Correct",
		f"{q_name} Deduction": 0,
		f"{q_name} Feedback": "ok",
	}

	def _explode(*_a, **_k):
		raise AssertionError("auto_grade_student_response should be skipped")

	monkeypatch.setattr(gpi, "auto_grade_student_response", _explode)
	monkeypatch.setattr(gpi, "get_user_input", _explode)
	# Single-student response group: gate fires, function returns
	# without ever calling the stubbed grader.
	gpi.process_csv_question([cached_student], question, ["5"])


def test_csv_question_gate_runs_when_status_deleted(monkeypatch):
	# WP6b case 9 (re-prompt half): deleting the `<Q> Status` key on a
	# cached student must re-invoke the grader for that one question.
	# This is the operator's manual escape hatch for re-prompting one
	# CSV question without touching anything else.
	question = _question_dict()
	q_name = question["name"]
	uncached_student = {
		"Student ID": "900000001",
		"First Name": "Alice",
		"Last Name": "Aaa",
		q_name: "5",
		# Note: no `Number of Helices Status` key -- operator deleted it.
	}

	calls: list = []

	def _record_auto_grade(*args, **_kwargs):
		calls.append(args)
		return (0, "Correct", "ok")

	monkeypatch.setattr(gpi, "auto_grade_student_response", _record_auto_grade)
	gpi.process_csv_question([uncached_student], question, ["5"])
	# The grader was invoked for the ungraded response group and the
	# cached fields were repopulated. Behavioral check: the call list
	# is non-empty AND the status was written; no coupling to a
	# specific call count or grouping shape.
	assert calls
	assert uncached_student[f"{q_name} Status"] == "Correct"


# ---- load_student_data integration (WP2 acceptance criteria) -------------

def test_merge_via_load_student_data_missing_yaml_path_raises(tmp_path,
		monkeypatch):
	# load_student_data should raise FileNotFoundError when the
	# operator points --yaml-backup-file at a path that does not
	# exist. Catches typos before any grading work happens.
	bad_path = tmp_path / "does_not_exist.yml"

	# Stub the form-CSV reader so we don't have to construct a real
	# spec config / form CSV; load_student_data still needs to read
	# the form before considering the YAML path.
	def _fake_read(input_csv, config):
		return [_form_row("900000001")]

	# Stub the roster path / matcher so we never hit the real ones.
	monkeypatch.setattr(
		gpi.file_io_protein, "read_student_csv_data", _fake_read
	)

	# argparse.Namespace gives us a real attribute container without
	# inventing an anonymous class inline (clearer test intent).
	params = {
		"args": argparse.Namespace(yaml_backup_file=str(bad_path)),
		"input_csv": "ignored",
		"image_number": 1,
		"image_dir": str(tmp_path),
		"student_ids_csv": "ignored",
	}
	with pytest.raises(FileNotFoundError):
		gpi.load_student_data(params, {})
