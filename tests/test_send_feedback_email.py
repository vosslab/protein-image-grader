"""
Basic tests for send_feedback_for_image.

Tests inject fake send_func / preview_send_func via the module-level
defaults so pytest never imports applescript_dispatch and never
reaches Mail.app.
"""

# Standard Library
import pathlib

# local repo modules
import protein_image_grader.archive_paths
import protein_image_grader.email_log as email_log
import protein_image_grader.protein_images_path as pip
import protein_image_grader.send_feedback_email as sfe


#============================================
def _install_fake_repo_root(monkeypatch, repo_root: pathlib.Path) -> None:
	monkeypatch.setattr(
		protein_image_grader.archive_paths,
		"get_repo_root",
		lambda start_path=None: repo_root,
	)


#============================================
def _make_term_skeleton(repo_root: pathlib.Path, term: str) -> pathlib.Path:
	term_dir = repo_root / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR / term
	term_dir.mkdir(parents=True)
	(term_dir / "BCHM_Prot_Img_01_Test").mkdir()
	return term_dir


#============================================
def _student(student_id: str, username: str, first: str, last: str) -> dict:
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


#============================================
def _config() -> dict:
	return {'assignment name': 'Protein Image 01', 'total points': 10}


#============================================
def test_skip_already_sent(tmp_path, monkeypatch):
	# A student whose log entry is already "sent" must be skipped.
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	data = {}
	email_log.set_status(data, "900000001", 1, "sent", "t",
		"alice", "alice@mail.roosevelt.edu")
	email_log.save("spring_2026", data)

	student_tree = [
		_student("900000001", "alice", "Alice", "Aaa"),
		_student("900000002", "bob", "Bob", "Bbb"),
	]
	called_for = []
	def fake_send(student_entry, subject, body):
		called_for.append(student_entry['Student ID'])
	sfe.send_feedback_for_image(
		student_tree, 1, "spring_2026", False, fake_send, _config())
	assert "900000001" not in called_for
	assert "900000002" in called_for


#============================================
def test_dry_run_does_not_call_send_func(tmp_path, monkeypatch):
	# Dry-run never invokes the real send_func and never invokes the
	# real preview dispatcher (we stub default_preview_send_func via
	# the module attribute, the same pattern as default_send_func).
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	monkeypatch.setattr(sfe, "default_preview_send_func",
		lambda script_text: None)

	student_tree = [
		_student("900000001", "alice", "Alice", "Aaa"),
		_student("900000002", "bob", "Bob", "Bbb"),
	]
	called = []
	def fake_send(student_entry, subject, body):
		called.append(student_entry['Student ID'])
	counters = sfe.send_feedback_for_image(
		student_tree, 1, "spring_2026", True, fake_send, _config(),
		preview_send_func=sfe.default_preview_send_func,
	)
	assert called == []
	assert counters['dry_run'] == 2
