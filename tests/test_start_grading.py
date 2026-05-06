"""
Phase 1 tests for start_grading.py orchestrator.

All tests use tmp_path + monkeypatch against archive_paths.get_repo_root
so they never touch the real Synology-synced data root and never call
subprocess.run on real grader/downloader scripts.
"""

import sys
import pathlib

import pytest

import protein_image_grader.archive_paths
import protein_image_grader.protein_images_path as pip
import protein_image_grader.start_grading as sg


def _install_fake_repo_root(monkeypatch, repo_root):
	monkeypatch.setattr(
		protein_image_grader.archive_paths,
		"get_repo_root",
		lambda start_path=None: repo_root,
	)


def _make_term_skeleton(repo_root: pathlib.Path, term: str,
		with_roster: bool = True, with_bb_ids: bool = True,
		with_forms: bool = True) -> dict:
	# Build Protein_Images/semesters/<term>/{forms,submissions,grades}.
	term_dir = repo_root / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR / term
	term_dir.mkdir(parents=True)
	if with_forms:
		(term_dir / pip.FORMS_SUBDIR).mkdir()
	(term_dir / pip.SUBMISSIONS_SUBDIR).mkdir()
	(term_dir / pip.GRADES_SUBDIR).mkdir()
	if with_roster:
		(term_dir / pip.ROSTER_FILENAME).write_text("", encoding="ascii")
	if with_bb_ids:
		(term_dir / "blackboard_assignment_ids.txt").write_text("",
			encoding="ascii")
	return {"term_dir": term_dir}


def _drop_root_csv(repo_root: pathlib.Path, image_number: int,
		label: str = "Example") -> pathlib.Path:
	path = repo_root / f"BCHM_Prot_Img_{image_number:02d}-{label}.csv"
	path.write_text("", encoding="ascii")
	return path


def _drop_canonical_csv(repo_root: pathlib.Path, term: str,
		image_number: int, label: str = "Example") -> pathlib.Path:
	forms_dir = pip.get_forms_dir(term)
	forms_dir.mkdir(parents=True, exist_ok=True)
	path = forms_dir / f"BCHM_Prot_Img_{image_number:02d}-{label}.csv"
	path.write_text("", encoding="ascii")
	return path


# ---- auto-import ----------------------------------------------------------

def test_auto_import_moves_repo_root_csvs(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026", with_forms=False)
	_drop_root_csv(tmp_path, 4)
	_drop_root_csv(tmp_path, 7)
	moves = sg.auto_import_repo_root_csvs("spring_2026")
	assert len(moves) == 2
	forms_dir = pip.get_forms_dir("spring_2026")
	assert (forms_dir / "BCHM_Prot_Img_04-Example.csv").is_file()
	assert (forms_dir / "BCHM_Prot_Img_07-Example.csv").is_file()
	# repo root is now clean
	leftover = list(tmp_path.glob("BCHM_Prot_Img_*.csv"))
	assert leftover == []


def test_auto_import_creates_forms_dir(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026", with_forms=False)
	assert not pip.get_forms_dir("spring_2026").exists()
	_drop_root_csv(tmp_path, 1)
	sg.auto_import_repo_root_csvs("spring_2026")
	assert pip.get_forms_dir("spring_2026").is_dir()


def test_auto_import_refuses_overwrite(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	# Same filename present at root and in canonical forms dir.
	_drop_root_csv(tmp_path, 4, label="Active_Site")
	_drop_canonical_csv(tmp_path, "spring_2026", 4, label="Active_Site")
	with pytest.raises(FileExistsError) as excinfo:
		sg.auto_import_repo_root_csvs("spring_2026")
	assert "destination already exists" in str(excinfo.value)


def test_auto_import_ignores_unrelated_root_files(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	(tmp_path / "roster.csv").write_text("", encoding="ascii")
	(tmp_path / "notes.txt").write_text("", encoding="ascii")
	moves = sg.auto_import_repo_root_csvs("spring_2026")
	assert moves == []
	# The non-form files are still at the root.
	assert (tmp_path / "roster.csv").is_file()
	assert (tmp_path / "notes.txt").is_file()


# ---- duplicate detection --------------------------------------------------

def test_detect_duplicate_canonical_csvs(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	_drop_canonical_csv(tmp_path, "spring_2026", 4, label="Active_Site")
	_drop_canonical_csv(tmp_path, "spring_2026", 4, label="Active_Site_v2")
	dups = sg.detect_canonical_duplicates("spring_2026")
	assert 4 in dups
	assert len(dups[4]) == 2


def test_no_duplicates_when_unique(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	for n in (1, 2, 3):
		_drop_canonical_csv(tmp_path, "spring_2026", n)
	assert sg.detect_canonical_duplicates("spring_2026") == {}


# ---- dashboard rows -------------------------------------------------------

def test_status_row_for_complete_image(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	_drop_canonical_csv(tmp_path, "spring_2026", 1)
	# Fake submissions and grade outputs for image 01.
	subs = pip.get_submissions_dir("spring_2026") / "download_01_raw"
	subs.mkdir(parents=True)
	(subs / "fake.jpg").write_text("", encoding="ascii")
	grades = pip.get_grades_dir("spring_2026")
	(grades / "output-protein_image_01.csv").write_text("", encoding="ascii")
	(grades / "blackboard_upload-protein_image_01.csv").write_text(
		"", encoding="ascii")
	# Graded YAML + email log marking the only expected student as sent.
	import yaml as _yaml
	import protein_image_grader.email_log as _email_log
	graded_yaml = grades / "output-protein_image_01.yml"
	graded_yaml.write_text(_yaml.safe_dump([{
		"Student ID": "900000001",
		"Username": "alice",
	}]), encoding="ascii")
	data = {}
	_email_log.set_status(data, "900000001", 1, "sent",
		"2026-05-06T14:32:11", "alice", "alice@mail.roosevelt.edu")
	_email_log.save("spring_2026", data)
	canonical_csvs = sg.find_canonical_form_csvs("spring_2026")
	row = sg.build_status_row(1, "spring_2026", canonical_csvs)
	assert row["form"] == "OK"
	assert row["downloaded"] == "OK"
	assert row["graded"] == "OK"
	assert row["emailed"] == "OK"
	assert row["bb_upload"] == "OK"
	assert row["next_step"] == "done"


def test_status_row_for_missing_image(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	canonical_csvs = sg.find_canonical_form_csvs("spring_2026")
	row = sg.build_status_row(5, "spring_2026", canonical_csvs)
	assert row["form"] == "MISSING"
	assert row["downloaded"] == "MISSING"
	assert row["graded"] == "MISSING"
	assert row["emailed"] == "MISSING"
	assert row["bb_upload"] == "MISSING"
	assert row["next_step"] == "add form CSV"


def test_status_row_next_step_progression():
	# Pure logic check on compute_next_step.
	assert sg.compute_next_step("MISSING", "MISSING", "MISSING",
		"MISSING") == "add form CSV"
	assert sg.compute_next_step("DUPLICATE", "MISSING", "MISSING",
		"MISSING") == "fix duplicate CSV"
	# Download is folded into the grade step (non-interactive); whenever
	# the form CSV is OK and grading has not happened, the next action is
	# "grade" regardless of download state.
	assert sg.compute_next_step("OK", "MISSING", "MISSING",
		"MISSING") == "grade"
	assert sg.compute_next_step("OK", "OK", "MISSING",
		"MISSING") == "grade"
	# Graded but email log missing/partial -> email step.
	assert sg.compute_next_step("OK", "OK", "OK", "MISSING",
		emailed_status="MISSING") == "email"
	assert sg.compute_next_step("OK", "OK", "OK", "MISSING",
		emailed_status="PARTIAL") == "email"
	# Email done, BB still missing -> regrade or upload.
	assert sg.compute_next_step("OK", "OK", "OK", "MISSING",
		emailed_status="OK") == "regrade or upload"
	# Everything done.
	assert sg.compute_next_step("OK", "OK", "OK", "OK",
		emailed_status="OK") == "done"


# ---- command construction -------------------------------------------------

def test_build_download_command_uses_canonical_csv():
	csv = pathlib.Path("/x/Protein_Images/semesters/spring_2026/forms/"
		"BCHM_Prot_Img_04-Active_Site.csv")
	cmd = sg.build_download_command(csv)
	assert cmd[0] == sys.executable
	assert cmd[1] == sg.DOWNLOAD_SCRIPT
	assert cmd[2] == "-i"
	assert cmd[3] == str(csv)
	# No --output-dir: downloader infers from canonical CSV path.
	assert "--output-dir" not in cmd
	assert "-o" not in cmd


def test_build_grade_command_passes_term():
	cmd = sg.build_grade_command(4, "spring_2025")
	assert cmd[0] == sys.executable
	assert cmd[1] == sg.GRADE_SCRIPT
	assert "-i" in cmd
	assert "4" in cmd
	assert "--term" in cmd
	assert "spring_2025" in cmd


# ---- no batch grading -----------------------------------------------------

def test_no_batch_grading_helper():
	# The orchestrator must not expose a helper that grades multiple
	# images at once. Keep this check broad: any public name suggesting
	# batch behavior is forbidden.
	forbidden = ("grade_all", "grade_batch", "run_all_images",
		"build_grade_commands_all")
	for name in forbidden:
		assert not hasattr(sg, name), (
			f"start_grading.py must not expose batch helper {name!r}"
		)


# ---- resolve_canonical_csv ------------------------------------------------

def test_resolve_canonical_csv_missing(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	with pytest.raises(FileNotFoundError):
		sg.resolve_canonical_csv("spring_2026", 4)


def test_resolve_canonical_csv_duplicates(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	_drop_canonical_csv(tmp_path, "spring_2026", 4, label="A")
	_drop_canonical_csv(tmp_path, "spring_2026", 4, label="B")
	with pytest.raises(ValueError):
		sg.resolve_canonical_csv("spring_2026", 4)


# ---- require_resources ----------------------------------------------------

def test_require_resources_grade_needs_roster(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026", with_roster=False)
	with pytest.raises(FileNotFoundError):
		sg.require_resources("spring_2026", "grade")


def test_require_resources_download_skips_roster(tmp_path, monkeypatch, capsys):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026", with_roster=False,
		with_bb_ids=False)
	# No exception even though roster.csv is missing.
	sg.require_resources("spring_2026", "download")
	captured = capsys.readouterr()
	# bb ids missing -> warning only.
	assert "WARNING" in captured.out


def test_require_resources_forms_missing_errors(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026", with_forms=False)
	with pytest.raises(FileNotFoundError):
		sg.require_resources("spring_2026", "download")
