"""
Unit tests for protein_image_grader.grade_protein_image merge helpers.

Covers the YAML+CSV merge logic that drives the checkpoint-aware
resume system: identity by Student ID after keeping the newest form
submission, no-overwrite backfill of form-row keys into matched YAML
rows, duplicate-key rejection on the YAML side, and YAML-only row
skipping with a warning.
"""

# Standard Library
import argparse
import pathlib

# PIP3 modules
import pytest
import yaml

# local repo modules
import protein_image_grader.grade_protein_image as gpi
import protein_image_grader.student_id_protein as student_id_protein


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


def _roster_row(sid, first="Pat", last="Roe", username="patroe"):
	return {
		"Student ID": str(sid),
		"First Name": first,
		"Last Name": last,
		"Username": username,
		"Alias": "",
	}


# ---- _collapse_form_to_newest_submissions --------------------------------

def test_collapse_form_keeps_newest_duplicate_student_id(capsys):
	form_tree = [
		_form_row("900000001", timestamp="2026/04/16 1:00:00 PM EST"),
		_form_row("900000001", timestamp="2026/04/16 1:05:00 PM EST",
			first="New"),
		_form_row("900000002", timestamp="2026/04/16 1:03:00 PM EST"),
	]
	collapsed = gpi._collapse_form_to_newest_submissions(form_tree)
	assert [row["Student ID"] for row in collapsed] == [
		"900000001", "900000002",
	]
	assert collapsed[0]["First Name"] == "New"
	output = capsys.readouterr().out
	assert "duplicate Student ID '900000001'" in output


def test_collapse_form_accepts_distinct_student_ids():
	form_tree = [_form_row("900000001"), _form_row("900000002")]
	collapsed = gpi._collapse_form_to_newest_submissions(form_tree)
	assert collapsed == form_tree


def test_resolve_form_rows_rewrites_wrong_typed_ruid(monkeypatch):
	monkeypatch.setattr(student_id_protein.time, "sleep", lambda _seconds: None)
	form_tree = [
		_form_row("900999999", first="Alice", last="Smith",
			Username="asmith"),
	]
	student_ids_tree = [_roster_row(900000002, first="Alice",
		last="Smith", username="asmith")]
	resolved = gpi._resolve_form_rows_to_roster_student_ids(
		form_tree, student_ids_tree,
	)
	assert resolved[0]["Student ID"] == "900000002"
	assert resolved[0]["Form RUID"] == "900999999"
	assert resolved[0]["Username"] == "asmith"


def test_resolve_form_rows_allows_duplicate_submissions_before_collapse(monkeypatch):
	monkeypatch.setattr(student_id_protein.time, "sleep", lambda _seconds: None)
	form_tree = [
		_form_row("900999999", first="Alice", last="Smith",
			Username="asmith", timestamp="2026/04/16 1:00:00 PM EST"),
		_form_row("900888888", first="Alice", last="Smith",
			Username="asmith", timestamp="2026/04/16 1:05:00 PM EST"),
	]
	student_ids_tree = [_roster_row(900000002, first="Alice",
		last="Smith", username="asmith")]
	resolved = gpi._resolve_form_rows_to_roster_student_ids(
		form_tree, student_ids_tree,
	)
	collapsed = gpi._collapse_form_to_newest_submissions(resolved)
	assert [row["Student ID"] for row in resolved] == [
		"900000002", "900000002",
	]
	assert len(collapsed) == 1
	assert collapsed[0]["timestamp"] == "2026/04/16 1:05:00 PM EST"


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


def test_merge_skips_yaml_only_row_with_warning(capsys):
	# YAML carries a Student ID no longer in the form CSV (operator
	# removed the row, or roster resolution previously rewrote a typed
	# RUID). The cached row is skipped so it cannot create a duplicate
	# roster match later.
	form_tree = [_form_row("900000001"), _form_row("900000002")]
	yaml_tree = [
		_cached_yaml_row("900000001"),
		_cached_yaml_row("900000099"),  # not in form CSV
	]
	merged = gpi._merge_yaml_into_form(form_tree, yaml_tree)
	assert [row["Student ID"] for row in merged] == [
		"900000001", "900000002",
	]
	output = capsys.readouterr().out
	assert "skipped yaml-only student 900000099" in output


def test_merge_resubmission_is_auto_regraded_when_form_is_newer(capsys):
	# A student submits the form again with a new timestamp. The form
	# row wins over the cached YAML row so the new submission is graded.
	cached_timestamp = "2026/04/16 1:00:00 PM EST"
	resubmit_timestamp = "2026/05/01 9:30:00 AM EST"
	form_tree = [_form_row("900000001", timestamp=resubmit_timestamp)]
	yaml_tree = [_cached_yaml_row("900000001", timestamp=cached_timestamp)]
	merged = gpi._merge_yaml_into_form(form_tree, yaml_tree)
	assert merged[0]["timestamp"] == resubmit_timestamp
	assert "Image Assessment Complete" not in merged[0]
	assert merged[0]["Force Image Download"] is True
	output = capsys.readouterr().out
	assert "newer submission for Student ID 900000001" in output


def test_merge_resubmission_uses_cached_yaml_when_timestamp_matches():
	# Same timestamp means this is the same form row as the cached
	# checkpoint. Reuse grading fields and keep the no-overwrite rule.
	timestamp = "2026/04/16 1:00:00 PM EST"
	form_tree = [_form_row("900000001", timestamp=timestamp)]
	yaml_tree = [_cached_yaml_row("900000001", timestamp=timestamp)]
	merged = gpi._merge_yaml_into_form(form_tree, yaml_tree)
	assert merged[0]["timestamp"] == timestamp
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


def test_load_student_data_resume_print_uses_symlink_short_path(tmp_path,
		monkeypatch, capsys):
	real_root = tmp_path / "external"
	repo_root = tmp_path / "repo"
	protein_images_real = real_root / "Protein_Images"
	protein_images_real.mkdir(parents=True)
	repo_root.mkdir()
	(repo_root / "Protein_Images").symlink_to(protein_images_real,
		target_is_directory=True)
	monkeypatch.chdir(repo_root)

	form_tree = [_form_row("900000001")]
	student_ids_tree = [_roster_row("900000001")]
	yaml_path = (
		protein_images_real / "semesters" / "spring_2026"
		/ "BCHM_Prot_Img_01_Test" / "output-protein_image_01.yml"
	)
	yaml_path.parent.mkdir(parents=True)
	yaml_path.write_text(yaml.safe_dump([_cached_yaml_row("900000001")]),
		encoding="ascii")

	monkeypatch.setattr(gpi.file_io_protein, "read_student_csv_data",
		lambda _csv, _config: form_tree)
	monkeypatch.setattr(gpi.file_io_protein, "read_student_ids",
		lambda _csv: student_ids_tree)
	monkeypatch.setattr(gpi.timestamp_tools, "check_due_date",
		lambda _timestamp, _config: (0, "On-Time", ""))
	monkeypatch.setattr(gpi.student_id_protein.time, "sleep",
		lambda _seconds: None)

	params = {
		"args": argparse.Namespace(yaml_backup_file=str(yaml_path)),
		"input_csv": "ignored.csv",
		"image_number": 1,
		"image_dir": str(yaml_path.parent),
		"student_ids_csv": str(tmp_path / "roster.csv"),
	}
	pathlib.Path(params["student_ids_csv"]).write_text("", encoding="ascii")

	gpi.load_student_data(params, {"deadline": {"due date": "Apr 16, 2026"}})
	output = capsys.readouterr().out
	assert (
		"Resuming from Protein_Images/semesters/spring_2026/"
		"BCHM_Prot_Img_01_Test/output-protein_image_01.yml"
	) in output
	assert "../../../../" not in output
