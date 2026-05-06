"""
Tests for protein_image_grader/email_log.py.

All tests use tmp_path + monkeypatch against archive_paths.get_repo_root
so they never touch the real Protein_Images/ data root.
"""

import pathlib

import pytest

import protein_image_grader.archive_paths
import protein_image_grader.email_log as email_log
import protein_image_grader.protein_images_path as pip


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


# ---- load -----------------------------------------------------------------

def test_load_returns_empty_when_missing(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	assert email_log.load("spring_2026") == {}


def test_load_after_save_round_trips(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	data = {}
	email_log.set_status(data, "900646199", 1, "sent",
		"2026-05-06T14:32:11", "adarbanova",
		"adarbanova@mail.roosevelt.edu")
	email_log.set_status(data, "900646199", 2, "failed",
		"2026-05-06T14:33:02", "adarbanova",
		"adarbanova@mail.roosevelt.edu", message="AppleScript: timeout")
	email_log.set_status(data, "900620160", 1, "dry_run",
		"2026-05-06T14:31:55", "cvirgen",
		"cvirgen@mail.roosevelt.edu")
	email_log.save("spring_2026", data)
	loaded = email_log.load("spring_2026")
	assert loaded["900646199"]["image_01"]["status"] == "sent"
	assert loaded["900646199"]["image_02"]["status"] == "failed"
	assert loaded["900646199"]["image_02"]["message"] == "AppleScript: timeout"
	assert loaded["900620160"]["image_01"]["status"] == "dry_run"


# ---- set_status -----------------------------------------------------------

def test_set_status_overwrites_same_cell():
	data = {}
	email_log.set_status(data, "900646199", 1, "failed",
		"2026-05-06T14:00:00", "adarbanova",
		"adarbanova@mail.roosevelt.edu", message="boom")
	email_log.set_status(data, "900646199", 1, "sent",
		"2026-05-06T14:32:11", "adarbanova",
		"adarbanova@mail.roosevelt.edu")
	cell = data["900646199"]["image_01"]
	assert cell["status"] == "sent"
	assert "message" not in cell
	assert cell["attempted_at"] == "2026-05-06T14:32:11"


def test_set_status_preserves_other_cells():
	data = {}
	email_log.set_status(data, "900646199", 1, "sent",
		"t1", "adarbanova", "adarbanova@mail.roosevelt.edu")
	email_log.set_status(data, "900646199", 2, "failed",
		"t2", "adarbanova", "adarbanova@mail.roosevelt.edu",
		message="boom")
	email_log.set_status(data, "900620160", 1, "sent",
		"t3", "cvirgen", "cvirgen@mail.roosevelt.edu")
	# Update student A image 2; A image 1 and B image 1 unchanged.
	email_log.set_status(data, "900646199", 2, "sent",
		"t4", "adarbanova", "adarbanova@mail.roosevelt.edu")
	assert data["900646199"]["image_01"]["status"] == "sent"
	assert data["900646199"]["image_02"]["status"] == "sent"
	assert "message" not in data["900646199"]["image_02"]
	assert data["900620160"]["image_01"]["status"] == "sent"


def test_set_status_rejects_invalid_status():
	data = {}
	for bad in ("dry-run", "fail", "SENT", "", "queued"):
		with pytest.raises(ValueError):
			email_log.set_status(data, "900646199", 1, bad, "t",
				"adarbanova", "adarbanova@mail.roosevelt.edu")


# ---- get_status -----------------------------------------------------------

def test_get_status_returns_none_for_unknown_student():
	data = {}
	email_log.set_status(data, "900646199", 1, "sent", "t",
		"adarbanova", "adarbanova@mail.roosevelt.edu")
	assert email_log.get_status(data, "900000000", 1) is None


def test_get_status_returns_none_for_unknown_image():
	data = {}
	email_log.set_status(data, "900646199", 1, "sent", "t",
		"adarbanova", "adarbanova@mail.roosevelt.edu")
	assert email_log.get_status(data, "900646199", 4) is None


def test_get_status_returns_stored_status():
	data = {}
	email_log.set_status(data, "900646199", 1, "failed", "t",
		"adarbanova", "adarbanova@mail.roosevelt.edu",
		message="boom")
	assert email_log.get_status(data, "900646199", 1) == "failed"


# ---- summarize_image ------------------------------------------------------

def test_summarize_image_missing_when_no_expected_status():
	data = {}
	# Log has data for unrelated students; expected list empty for this img.
	email_log.set_status(data, "900000000", 1, "sent", "t",
		"other", "other@mail.roosevelt.edu")
	expected = ["900646199", "900620160"]
	assert email_log.summarize_image(data, 1, expected) == "MISSING"


def test_summarize_image_ok_when_all_expected_sent():
	data = {}
	for sid, user in (("900646199", "adarbanova"),
			("900620160", "cvirgen")):
		email_log.set_status(data, sid, 1, "sent", "t", user,
			f"{user}@mail.roosevelt.edu")
	expected = ["900646199", "900620160"]
	assert email_log.summarize_image(data, 1, expected) == "OK"


def test_summarize_image_partial_when_one_missing():
	data = {}
	email_log.set_status(data, "900646199", 1, "sent", "t",
		"adarbanova", "adarbanova@mail.roosevelt.edu")
	expected = ["900646199", "900620160"]
	# Second student has no status -> PARTIAL (some have, not all sent).
	assert email_log.summarize_image(data, 1, expected) == "PARTIAL"


def test_summarize_image_partial_when_dry_run_present():
	data = {}
	email_log.set_status(data, "900646199", 1, "sent", "t",
		"adarbanova", "adarbanova@mail.roosevelt.edu")
	email_log.set_status(data, "900620160", 1, "dry_run", "t",
		"cvirgen", "cvirgen@mail.roosevelt.edu")
	expected = ["900646199", "900620160"]
	# A dry_run cell among expected IDs must force PARTIAL.
	assert email_log.summarize_image(data, 1, expected) == "PARTIAL"


def test_summarize_image_ignores_extra_ids():
	data = {}
	email_log.set_status(data, "900646199", 1, "sent", "t",
		"adarbanova", "adarbanova@mail.roosevelt.edu")
	email_log.set_status(data, "900999999", 1, "failed", "t",
		"old", "old@mail.roosevelt.edu", message="boom")
	expected = ["900646199"]
	# Old/extra ID with failed status must not affect the answer.
	assert email_log.summarize_image(data, 1, expected) == "OK"


# ---- save layout and atomicity --------------------------------------------

def test_save_orders_username_email_before_image_keys(tmp_path,
		monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	data = {}
	email_log.set_status(data, "900646199", 1, "sent", "t",
		"adarbanova", "adarbanova@mail.roosevelt.edu")
	email_log.save("spring_2026", data)
	text = pip.get_email_log_yaml("spring_2026").read_text(
		encoding="ascii")
	# Inside the student record, username appears before email, and both
	# appear before image_01.
	pos_username = text.index("username:")
	pos_email = text.index("email:")
	pos_image = text.index("image_01:")
	assert pos_username < pos_email < pos_image


def test_save_atomic_no_tmp_left_behind(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	term_dir = _make_term_skeleton(tmp_path, "spring_2026")
	data = {}
	email_log.set_status(data, "900646199", 1, "sent", "t",
		"adarbanova", "adarbanova@mail.roosevelt.edu")
	email_log.save("spring_2026", data)
	target = pip.get_email_log_yaml("spring_2026")
	assert target.is_file()
	assert target.stat().st_size > 0
	# No leftover .email_log.* tempfiles.
	leftovers = [p for p in term_dir.iterdir()
		if p.name.startswith(".email_log.")]
	assert leftovers == []
