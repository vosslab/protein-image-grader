"""
Tests for protein_image_grader/no_submission_email.py.

Stub send_func keeps Mail.app out of the loop. A fake repo root keeps the
email log under tmp_path.
"""

# Standard Library
import pathlib

# PIP3 modules
import pytest

# local repo modules
import protein_image_grader.archive_paths
import protein_image_grader.email_log as email_log
import protein_image_grader.protein_images_path as pip
import protein_image_grader.no_submission_email as nse


def _install_fake_repo_root(monkeypatch, repo_root: pathlib.Path) -> None:
	monkeypatch.setattr(
		protein_image_grader.archive_paths,
		"get_repo_root",
		lambda start_path=None: repo_root,
	)


def _make_term_skeleton(repo_root: pathlib.Path, term: str) -> pathlib.Path:
	term_dir = repo_root / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR / term
	term_dir.mkdir(parents=True)
	return term_dir


def _roster_row(student_id: int, username: str, first: str,
		last: str) -> dict:
	# Shape mirrors roster_matching.read_roster output.
	return {
		'student_id': student_id,
		'first_name': first.lower(),
		'last_name': last.lower(),
		'username': username,
		'alias': '',
		'full_name': f"{first.lower()} {last.lower()}",
	}


def _config() -> dict:
	return {'assignment name': 'Protein Image 01', 'total points': 10}


# ---- compute_non_submitters (diff) ----------------------------------------

def test_diff_returns_only_missing_rows_in_roster_order():
	roster = {}
	for sid, user in ((900000001, "alice"), (900000002, "bob"),
			(900000003, "carol"), (900000004, "dave")):
		roster[sid] = _roster_row(sid, user, user.title(), "Aaa")
	missing = nse.compute_non_submitters(roster, ["900000001", "900000003"])
	# Bob and Dave are missing; roster iteration order preserved.
	assert [row['username'] for row in missing] == ["bob", "dave"]


def test_diff_coerces_int_and_str_student_ids():
	# Roster keys are int; submitted_ids may be a mix of int/str (YAML can
	# load Student IDs either way depending on quoting).
	roster = {
		900000001: _roster_row(900000001, "alice", "Alice", "Aaa"),
		900000002: _roster_row(900000002, "bob", "Bob", "Bbb"),
	}
	missing_with_str = nse.compute_non_submitters(roster, ["900000001"])
	missing_with_int = nse.compute_non_submitters(roster, [900000001])
	assert [r['username'] for r in missing_with_str] == ["bob"]
	assert [r['username'] for r in missing_with_int] == ["bob"]


def test_diff_does_not_mutate_inputs():
	roster = {
		900000001: _roster_row(900000001, "alice", "Alice", "Aaa"),
	}
	submitted = ["900000001"]
	roster_snapshot = dict(roster)
	submitted_snapshot = list(submitted)
	nse.compute_non_submitters(roster, submitted)
	assert roster == roster_snapshot
	assert submitted == submitted_snapshot


# ---- make_no_submission_content -------------------------------------------

def test_content_mentions_assignment_and_student_name():
	row = _roster_row(900000001, "alice", "Alice", "Aaa")
	body = nse.make_no_submission_content(row, 1, _config())
	assert "Protein Image 01" in body
	assert "Alice Aaa" in body
	# No score / feedback artifacts leak in from the submitter template.
	assert "Final Score" not in body
	assert "Deduction" not in body


def test_content_is_ascii():
	row = _roster_row(900000001, "alice", "Alice", "Aaa")
	body = nse.make_no_submission_content(row, 1, _config())
	# ASCII-only body keeps AppleScript and email log encoding-safe.
	body.encode("ascii")


def test_subject_includes_assignment_name():
	subject = nse.make_no_submission_subject(_config())
	assert "Protein Image 01" in subject


# ---- send_no_submission_for_image -----------------------------------------

def test_dry_run_writes_dry_run_cells_no_send(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	missing = [
		_roster_row(900000001, "alice", "Alice", "Aaa"),
		_roster_row(900000002, "bob", "Bob", "Bbb"),
	]
	called = []
	def fake_send(roster_row, subject, body):
		called.append(roster_row['student_id'])
	counters = nse.send_no_submission_for_image(
		missing, 1, "spring_2026", True, fake_send, _config())
	assert called == []
	assert counters['no_submission_dry_run'] == 2
	loaded = email_log.load("spring_2026")
	assert loaded["900000001"]["image_01"]["status"] == "dry_run"
	assert loaded["900000002"]["image_01"]["status"] == "dry_run"


def test_real_send_writes_no_submission_sent_status(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	missing = [_roster_row(900000001, "alice", "Alice", "Aaa")]
	called = []
	def fake_send(roster_row, subject, body):
		called.append(roster_row['student_id'])
	counters = nse.send_no_submission_for_image(
		missing, 1, "spring_2026", False, fake_send, _config())
	assert called == [900000001]
	assert counters['no_submission_sent'] == 1
	loaded = email_log.load("spring_2026")
	assert loaded["900000001"]["image_01"]["status"] == "no_submission_sent"


def test_skip_when_already_sent_or_no_submission_sent(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	# Pre-populate: alice already got real feedback (sent), bob already got
	# a no-submission notice. carol has nothing yet.
	data = {}
	email_log.set_status(data, "900000001", 1, "sent", "t",
		"alice", "alice@mail.roosevelt.edu")
	email_log.set_status(data, "900000002", 1, "no_submission_sent", "t",
		"bob", "bob@mail.roosevelt.edu")
	email_log.save("spring_2026", data)
	missing = [
		_roster_row(900000001, "alice", "Alice", "Aaa"),
		_roster_row(900000002, "bob", "Bob", "Bbb"),
		_roster_row(900000003, "carol", "Carol", "Ccc"),
	]
	called = []
	def fake_send(roster_row, subject, body):
		called.append(roster_row['student_id'])
	counters = nse.send_no_submission_for_image(
		missing, 1, "spring_2026", False, fake_send, _config())
	# Only carol is sent; alice and bob are skipped because their cells
	# are already in CLOSING_STATUSES.
	assert called == [900000003]
	assert counters['no_submission_sent'] == 1
	assert counters['no_submission_skipped'] == 2


def test_failed_send_continues_batch(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	missing = [
		_roster_row(900000001, "alice", "Alice", "Aaa"),
		_roster_row(900000002, "bob", "Bob", "Bbb"),
		_roster_row(900000003, "carol", "Carol", "Ccc"),
	]
	def fake_send(roster_row, subject, body):
		if roster_row['student_id'] == 900000002:
			raise RuntimeError("AppleScript: timeout")
	counters = nse.send_no_submission_for_image(
		missing, 1, "spring_2026", False, fake_send, _config())
	assert counters['no_submission_sent'] == 2
	assert counters['no_submission_failed'] == 1
	loaded = email_log.load("spring_2026")
	assert loaded["900000001"]["image_01"]["status"] == "no_submission_sent"
	assert loaded["900000002"]["image_01"]["status"] == "failed"
	assert "AppleScript: timeout" in loaded["900000002"]["image_01"]["message"]
	assert loaded["900000003"]["image_01"]["status"] == "no_submission_sent"


def test_recipient_email_requires_username():
	row = _roster_row(900000001, "", "Alice", "Aaa")
	with pytest.raises(ValueError):
		nse._recipient_email(row)
