"""
Tests for the canonical-mode send_feedback_for_image helper.

We never touch Mail.app; tests inject a fake send_func and a fake repo
root so the email log lands in tmp_path.
"""

import sys
import pathlib

import yaml

import protein_image_grader.archive_paths
import protein_image_grader.email_log as email_log
import protein_image_grader.protein_images_path as pip
import protein_image_grader.send_feedback_email as sfe
import protein_image_grader.no_submission_email as nse


def _install_fake_repo_root(monkeypatch, repo_root: pathlib.Path) -> None:
	monkeypatch.setattr(
		protein_image_grader.archive_paths,
		"get_repo_root",
		lambda start_path=None: repo_root,
	)


def _make_term_skeleton(repo_root: pathlib.Path, term: str) -> pathlib.Path:
	# Create minimal structure for testing: term root + one image directory
	term_dir = repo_root / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR / term
	term_dir.mkdir(parents=True)
	# Create a minimal per-image folder for tests
	image_dir = term_dir / "BCHM_Prot_Img_01_Test"
	image_dir.mkdir()
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


# ---- end-to-end submitter + non-submitter integration ---------------------

def _write_roster(term_dir: pathlib.Path, rows: list) -> None:
	# Tiny CSV writer; matches the shape roster_matching.read_roster expects.
	roster_csv = term_dir / "roster.csv"
	header = "First Name,Last Name,Username,Student ID,Alias\n"
	body = ""
	for first, last, user, sid in rows:
		body += f"{first},{last},{user},{sid},\n"
	roster_csv.write_text(header + body, encoding="ascii")


def test_two_pass_dry_run_then_real_send_closes_summary(tmp_path,
		monkeypatch):
	# 4-row roster, 2 submitters in graded YAML, 2 non-submitters.
	# Dry-run pass writes only dry_run cells and summary stays PARTIAL.
	# Real-send pass flips both populations to closing statuses (sent for
	# submitters, no_submission_sent for non-submitters) and the dashboard
	# summary returns OK.
	_install_fake_repo_root(monkeypatch, tmp_path)
	term_dir = _make_term_skeleton(tmp_path, "spring_2026")
	_write_roster(term_dir, [
		("Alice", "Aaa", "alice", "900000001"),
		("Bob",   "Bbb", "bob",   "900000002"),
		("Carol", "Ccc", "carol", "900000003"),
		("Dave",  "Ddd", "dave",  "900000004"),
	])

	# Submitter side: only Alice and Bob appear in the graded YAML.
	import protein_image_grader.roster_matching as roster_matching
	roster = roster_matching.read_roster(str(term_dir / "roster.csv"))
	student_tree = [
		_student("900000001", "alice", "Alice", "Aaa"),
		_student("900000002", "bob", "Bob", "Bbb"),
	]
	submitted_ids = {s["Student ID"] for s in student_tree}

	# Dry-run pass.
	dr_called = []
	def dr_send(_e, _s, _b):
		dr_called.append("called")
	sub_dr = sfe.send_feedback_for_image(
		student_tree, 1, "spring_2026", True, dr_send, _config())
	missing_dr = nse.compute_non_submitters(roster, submitted_ids)
	ns_dr = nse.send_no_submission_for_image(
		missing_dr, 1, "spring_2026", True, dr_send, _config())
	assert dr_called == []
	assert sub_dr["dry_run"] == 2
	assert ns_dr["no_submission_dry_run"] == 2
	# After dry-run only, every roster cell exists but every cell is dry_run,
	# so the summary should be PARTIAL (dry_run is not closing).
	expected_ids = [str(sid) for sid in roster.keys()]
	data = email_log.load("spring_2026")
	assert email_log.summarize_image(data, 1, expected_ids) == "PARTIAL"

	# Real-send pass.
	real_called = []
	def real_send(student_or_row, _s, _b):
		real_called.append(student_or_row)
	sub_rs = sfe.send_feedback_for_image(
		student_tree, 1, "spring_2026", False, real_send, _config())
	missing_rs = nse.compute_non_submitters(roster, submitted_ids)
	ns_rs = nse.send_no_submission_for_image(
		missing_rs, 1, "spring_2026", False, real_send, _config())
	assert sub_rs["sent"] == 2
	assert ns_rs["no_submission_sent"] == 2
	# Every roster cell now closing -> OK.
	data = email_log.load("spring_2026")
	assert email_log.summarize_image(data, 1, expected_ids) == "OK"
	# Cell-by-cell shape: submitters carry "sent", non-submitters carry
	# "no_submission_sent".
	assert data["900000001"]["image_01"]["status"] == "sent"
	assert data["900000002"]["image_01"]["status"] == "sent"
	assert data["900000003"]["image_01"]["status"] == "no_submission_sent"
	assert data["900000004"]["image_01"]["status"] == "no_submission_sent"


# ---- main() end-to-end (--term branch) ------------------------------------

def test_main_term_branch_runs_both_passes_dry_run(tmp_path, monkeypatch):
	# Drive sfe.main() in --term dry-run mode. Verifies the wiring added
	# in Patch 3: roster load, submitter loop, non-submitter loop, and one
	# email_log cell per roster Student ID after one run. Both real
	# send_funcs are stubbed so Mail.app is never touched.
	_install_fake_repo_root(monkeypatch, tmp_path)
	term_dir = _make_term_skeleton(tmp_path, "spring_2026")
	_write_roster(term_dir, [
		("Alice", "Aaa", "alice", "900000001"),
		("Bob",   "Bbb", "bob",   "900000002"),
		("Carol", "Ccc", "carol", "900000003"),
	])
	# Graded YAML for image 01 contains only Alice and Bob.
	image_dir = pip.get_term_image_dir("spring_2026", 1)
	graded_yaml = image_dir / "output-protein_image_01.yml"
	graded_yaml.write_text(yaml.safe_dump([
		_student("900000001", "alice", "Alice", "Aaa"),
		_student("900000002", "bob", "Bob", "Bbb"),
	]), encoding="ascii")

	# Spec YAML on disk; main() loads config from spec_dir/protein_image_NN.yml.
	spec_dir = tmp_path / "spec_yaml_files"
	spec_dir.mkdir()
	(spec_dir / "protein_image_01.yml").write_text(
		yaml.safe_dump(_config()), encoding="ascii")

	# Stub both send paths so a real AppleScript dispatch never fires --
	# but in dry-run, neither default_send_func should even be invoked.
	called = []
	def boom_submitter(*_a, **_k):
		called.append("submitter")
	def boom_non_submitter(*_a, **_k):
		called.append("non_submitter")
	monkeypatch.setattr(sfe, "default_send_func", boom_submitter)
	monkeypatch.setattr(nse, "default_no_submission_send_func",
		boom_non_submitter)

	monkeypatch.setattr(sys, "argv", [
		"send_feedback_email.py",
		"-i", "1",
		"--spec-dir", str(spec_dir),
		"--term", "spring_2026",
	])
	sfe.main()

	# Dry-run: send_funcs never called.
	assert called == []
	# Every roster Student ID has a dry_run cell after one main() run.
	data = email_log.load("spring_2026")
	for sid in ("900000001", "900000002", "900000003"):
		assert data[sid]["image_01"]["status"] == "dry_run"
	# Roster-driven summary stays PARTIAL (dry_run does not close).
	expected_ids = ["900000001", "900000002", "900000003"]
	assert email_log.summarize_image(data, 1, expected_ids) == "PARTIAL"


def test_main_term_branch_real_send_closes_summary(tmp_path, monkeypatch):
	# Drive sfe.main() in --term real-send mode (-e). Verifies the same
	# wiring lights every roster cell to a closing status and the
	# dashboard summary returns OK.
	_install_fake_repo_root(monkeypatch, tmp_path)
	term_dir = _make_term_skeleton(tmp_path, "spring_2026")
	_write_roster(term_dir, [
		("Alice", "Aaa", "alice", "900000001"),
		("Bob",   "Bbb", "bob",   "900000002"),
		("Carol", "Ccc", "carol", "900000003"),
	])
	image_dir = pip.get_term_image_dir("spring_2026", 1)
	graded_yaml = image_dir / "output-protein_image_01.yml"
	graded_yaml.write_text(yaml.safe_dump([
		_student("900000001", "alice", "Alice", "Aaa"),
		_student("900000002", "bob", "Bob", "Bbb"),
	]), encoding="ascii")
	spec_dir = tmp_path / "spec_yaml_files"
	spec_dir.mkdir()
	(spec_dir / "protein_image_01.yml").write_text(
		yaml.safe_dump(_config()), encoding="ascii")

	# Stub both real-send paths to no-ops; record which got called for
	# which student so we can assert both pipelines ran.
	submitter_calls = []
	def fake_submitter(student_entry, _subject, _body):
		submitter_calls.append(student_entry["Student ID"])
	non_submitter_calls = []
	def fake_non_submitter(roster_row, _subject, _body):
		non_submitter_calls.append(roster_row["student_id"])
	monkeypatch.setattr(sfe, "default_send_func", fake_submitter)
	monkeypatch.setattr(nse, "default_no_submission_send_func",
		fake_non_submitter)

	monkeypatch.setattr(sys, "argv", [
		"send_feedback_email.py",
		"-i", "1",
		"--spec-dir", str(spec_dir),
		"--term", "spring_2026",
		"-e",
	])
	sfe.main()

	# Both pipelines fired.
	assert sorted(submitter_calls) == ["900000001", "900000002"]
	assert non_submitter_calls == [900000003]
	# Every roster cell now closing -> OK.
	data = email_log.load("spring_2026")
	expected_ids = ["900000001", "900000002", "900000003"]
	assert email_log.summarize_image(data, 1, expected_ids) == "OK"


# ---- canonical path resolution --------------------------------------------

def test_canonical_path_resolves_under_term(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	# In the new layout, output files live in the per-image folder
	expected = (tmp_path / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR
		/ "spring_2026" / "BCHM_Prot_Img_01_Test"
		/ "output-protein_image_01.yml")
	# The canonical path resolver uses get_image_spec_yaml, which returns
	# the per-image folder path. Output files are in the same folder.
	spec_yaml = pip.get_image_spec_yaml("spring_2026", 1)
	assert spec_yaml.parent / "output-protein_image_01.yml" == expected
