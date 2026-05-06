"""
Tests for the canonical-mode send_feedback_for_image helper.

We never touch Mail.app; tests inject a fake send_func and a fake repo
root so the email log lands in tmp_path.
"""

import pathlib

import protein_image_grader.archive_paths
import protein_image_grader.email_log as email_log
import protein_image_grader.protein_images_path as pip
import protein_image_grader.send_feedback_email as sfe


def _install_fake_repo_root(monkeypatch, repo_root: pathlib.Path) -> None:
	monkeypatch.setattr(
		protein_image_grader.archive_paths,
		"get_repo_root",
		lambda start_path=None: repo_root,
	)


def _make_term_skeleton(repo_root: pathlib.Path, term: str) -> pathlib.Path:
	term_dir = repo_root / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR / term
	term_dir.mkdir(parents=True)
	(term_dir / pip.GRADES_SUBDIR).mkdir()
	return term_dir


def _student(student_id: str, username: str, first: str, last: str) -> dict:
	# Minimal student_entry shape used by send_feedback_for_image; only
	# the fields the helper actually reads need to exist (others are
	# touched by make_content but tests use a fake send_func, so make_content
	# is what we have to satisfy too).
	return {
		'Student ID': student_id,
		'Username': username,
		'First Name': first,
		'Last Name': last,
		'email': f"{username}@mail.roosevelt.edu",
		'Final Score': '10.00',
		'Original Filename': 'x.png',
		'Image Format': 'png',
		'128-bit MD5 Hash': 'abc',
		'Consensus Background Color': 'White',
	}


def _config() -> dict:
	return {'assignment name': 'Protein Image 01', 'total points': 10}


# ---- skip already-sent ----------------------------------------------------

def test_skip_already_sent(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	# Pre-populate log: student A is already sent, student B has failed,
	# student C has dry_run, student D has nothing.
	data = {}
	email_log.set_status(data, "900000001", 1, "sent", "t",
		"alice", "alice@mail.roosevelt.edu")
	email_log.set_status(data, "900000002", 1, "failed", "t",
		"bob", "bob@mail.roosevelt.edu", message="boom")
	email_log.set_status(data, "900000003", 1, "dry_run", "t",
		"carol", "carol@mail.roosevelt.edu")
	email_log.save("spring_2026", data)

	student_tree = [
		_student("900000001", "alice", "Alice", "Aaa"),
		_student("900000002", "bob", "Bob", "Bbb"),
		_student("900000003", "carol", "Carol", "Ccc"),
		_student("900000004", "dave", "Dave", "Ddd"),
	]
	called_for = []
	def fake_send(student_entry, subject, body):
		called_for.append(student_entry['Student ID'])
	counters = sfe.send_feedback_for_image(
		student_tree, 1, "spring_2026", False, fake_send, _config())
	# Alice (sent) is skipped; Bob (failed), Carol (dry_run), Dave (none)
	# all get a real send.
	assert called_for == ["900000002", "900000003", "900000004"]
	assert counters['sent'] == 3
	assert counters['skipped'] == 1
	assert counters['failed'] == 0


# ---- failed send is captured, batch continues -----------------------------

def test_failed_send_continues_batch(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	student_tree = [
		_student("900000001", "alice", "Alice", "Aaa"),
		_student("900000002", "bob", "Bob", "Bbb"),
		_student("900000003", "carol", "Carol", "Ccc"),
	]
	def fake_send(student_entry, subject, body):
		if student_entry['Student ID'] == "900000002":
			raise RuntimeError("AppleScript: timeout")
	counters = sfe.send_feedback_for_image(
		student_tree, 1, "spring_2026", False, fake_send, _config())
	assert counters['sent'] == 2
	assert counters['failed'] == 1
	loaded = email_log.load("spring_2026")
	assert loaded["900000001"]["image_01"]["status"] == "sent"
	assert loaded["900000002"]["image_01"]["status"] == "failed"
	assert "AppleScript: timeout" in loaded["900000002"]["image_01"]["message"]
	assert loaded["900000003"]["image_01"]["status"] == "sent"


# ---- dry-run never calls send_func ----------------------------------------

def test_dry_run_does_not_call_send_func(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	student_tree = [
		_student("900000001", "alice", "Alice", "Aaa"),
		_student("900000002", "bob", "Bob", "Bbb"),
	]
	called = []
	def fake_send(student_entry, subject, body):
		called.append(student_entry['Student ID'])
	counters = sfe.send_feedback_for_image(
		student_tree, 1, "spring_2026", True, fake_send, _config())
	assert called == []
	assert counters['dry_run'] == 2
	loaded = email_log.load("spring_2026")
	assert loaded["900000001"]["image_01"]["status"] == "dry_run"
	assert loaded["900000002"]["image_01"]["status"] == "dry_run"


# ---- canonical path resolution --------------------------------------------

def test_canonical_path_resolves_under_term(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	expected = (tmp_path / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR
		/ "spring_2026" / pip.GRADES_SUBDIR
		/ "output-protein_image_01.yml")
	# The canonical mode in main() reads exactly this path; assert the
	# helper returns the same shape so we have one source of truth.
	assert pip.get_grades_dir("spring_2026") / "output-protein_image_01.yml" \
		== expected
