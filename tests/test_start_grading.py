"""
Phase 1 tests for start_grading.py orchestrator.

All tests use tmp_path + monkeypatch against archive_paths.get_repo_root
so they never touch the real Synology-synced data root and never call
subprocess.run on real grader/downloader scripts.
"""

# Standard Library
import sys
import types
import pathlib

# PIP3 modules
import pytest
import yaml

# local repo modules
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
	# Build Protein_Images/semesters/<term> with unified image storage layout.
	# No more separate submissions/ or grades/ dirs; all per-image folders now.
	term_dir = repo_root / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR / term
	term_dir.mkdir(parents=True)
	if with_forms:
		(term_dir / pip.FORMS_SUBDIR).mkdir()
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
	# Every move record is a (src, dst, action) triple after the
	# content-aware-collision rewrite.
	for record in moves:
		assert len(record) == 3
		assert record[2] == "moved"
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


def _form_csv_text(rows: list) -> str:
	# Minimal header that resolve_meta_columns recognizes for both
	# Student ID and timestamp.
	header = "Timestamp,Email Address,First Name,Last Name,Student ID\n"
	body = "".join(rows)
	return header + body


def _row(student_id: str, timestamp: str, first: str = "Pat",
		last: str = "Roe", email: str = "pat@x") -> str:
	return f"{timestamp},{email},{first},{last},{student_id}\n"


def test_auto_import_refuses_overwrite_on_real_conflict(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	# Same key on both sides, but the row content differs (changed
	# cell). This is a real conflict; the comparator must raise.
	src = tmp_path / "BCHM_Prot_Img_04-Active_Site.csv"
	dst = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_04-Active_Site.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	dst.write_text(
		_form_csv_text([_row("900000001", "2026/04/16 1:00:00 PM EST")]),
		encoding="ascii",
	)
	src.write_text(
		_form_csv_text([_row("900000001", "2026/04/16 1:00:00 PM EST",
			first="Patty")]),
		encoding="ascii",
	)
	with pytest.raises(FileExistsError) as excinfo:
		sg.auto_import_repo_root_csvs("spring_2026")
	assert "changed row: 900000001" in str(excinfo.value)


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
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	_drop_canonical_csv(tmp_path, "spring_2026", 1)
	# Roster.csv is now the source of expected Student IDs for the email
	# step, so it must list the student that the email log marks as sent.
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n"
		"Alice,Aaa,alice,900000001,\n",
		encoding="ascii",
	)
	# New layout: per-image folder with raw/ and output files
	image_dir = pip.get_term_image_dir("spring_2026", 1)
	image_dir.mkdir(parents=True, exist_ok=True)
	# Create raw/ subdirectory with a fake image
	image_raw_dir = image_dir / "raw"
	image_raw_dir.mkdir(exist_ok=True)
	(image_raw_dir / "fake.jpg").write_text("", encoding="ascii")
	# Create output files in the per-image folder
	(image_dir / "output-protein_image_01.csv").write_text("", encoding="ascii")
	(image_dir / "blackboard_upload-protein_image_01.csv").write_text(
		"", encoding="ascii")
	# Graded YAML still required by the grade step's "OK" gate; the email
	# step now reads the roster instead of this file for expected IDs.
	import yaml as _yaml
	import protein_image_grader.email_log as _email_log
	graded_yaml = image_dir / "output-protein_image_01.yml"
	graded_yaml.write_text(_yaml.safe_dump([{
		"Student ID": "900000001",
		"Username": "alice",
		"Image Assessment Complete": True,
		"Protein Image Number": 1,
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


# ---- emailed-status closure against roster --------------------------------

def test_compute_emailed_status_closes_against_roster(tmp_path, monkeypatch):
	# The Emailed column closes "OK" only when every roster Student ID has a
	# closing status (sent or no_submission_sent). A submitter-only "sent"
	# pass therefore stays PARTIAL until non-submitters are also closed.
	import protein_image_grader.email_log as _email_log
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n"
		"Alice,Aaa,alice,900000001,\n"
		"Bob,Bbb,bob,900000002,\n",
		encoding="ascii",
	)
	# No log at all -> MISSING.
	assert sg.compute_emailed_status("spring_2026", 1, "OK") == "MISSING"
	# Only one roster student has a closing cell -> PARTIAL.
	data = {}
	_email_log.set_status(data, "900000001", 1, "sent", "t",
		"alice", "alice@mail.roosevelt.edu")
	_email_log.save("spring_2026", data)
	assert sg.compute_emailed_status("spring_2026", 1, "OK") == "PARTIAL"
	# Closing the second student via no_submission_sent flips the cell to OK.
	_email_log.set_status(data, "900000002", 1, "no_submission_sent", "t",
		"bob", "bob@mail.roosevelt.edu")
	_email_log.save("spring_2026", data)
	assert sg.compute_emailed_status("spring_2026", 1, "OK") == "OK"


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


# ---- content-aware import collisions --------------------------------------

def test_auto_import_accepts_identical_collision(tmp_path, monkeypatch, capsys):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	src = tmp_path / "BCHM_Prot_Img_04-Active_Site.csv"
	dst = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_04-Active_Site.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	body = _form_csv_text([_row("900000001", "2026/04/16 1:00:00 PM EST")])
	src.write_text(body, encoding="ascii")
	dst.write_text(body, encoding="ascii")
	moves = sg.auto_import_repo_root_csvs("spring_2026")
	assert len(moves) == 1
	assert moves[0][2] == "identical"
	# Root copy was removed; canonical untouched.
	assert not src.exists()
	assert dst.is_file()
	out = capsys.readouterr().out
	assert "identical" in out


def test_auto_import_accepts_superset_collision(tmp_path, monkeypatch, capsys):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	src = tmp_path / "BCHM_Prot_Img_04-Active_Site.csv"
	dst = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_04-Active_Site.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	# Canonical already has 3 rows; root CSV has 5 (same 3 keys plus
	# 2 new keys, in interleaved order to prove the comparator is
	# keyed and not order-sensitive).
	r1 = _row("900000001", "2026/04/16 1:00:00 PM EST")
	r2 = _row("900000002", "2026/04/16 1:05:00 PM EST")
	r3 = _row("900000003", "2026/04/16 1:10:00 PM EST")
	new1 = _row("900000004", "2026/04/16 1:15:00 PM EST")
	new2 = _row("900000005", "2026/04/16 1:20:00 PM EST")
	dst.write_text(_form_csv_text([r1, r2, r3]), encoding="ascii")
	# Interleave new rows among the originals.
	src.write_text(
		_form_csv_text([r1, new1, r2, new2, r3]),
		encoding="ascii",
	)
	moves = sg.auto_import_repo_root_csvs("spring_2026")
	assert len(moves) == 1
	assert moves[0][2] == "replaced"
	assert not src.exists()
	# Canonical now matches the root CSV's contents: 5 data rows under
	# one header. Parse with csv.reader so a future trailing-newline or
	# line-ending change does not flap the assertion.
	import csv as _csv
	with open(dst, "r", encoding="ascii", newline="") as handle:
		all_rows = list(_csv.reader(handle))
	assert len(all_rows) == 6
	out = capsys.readouterr().out
	assert "superset" in out
	assert "+2 rows" in out


# ---- ungraded-row detection (PARTIAL) -------------------------------------

def _form_csv_with_records(student_ids: list, base_ts: str) -> str:
	rows = []
	for i, sid in enumerate(student_ids):
		ts = f"2026/04/16 1:{i:02d}:00 PM EST"
		rows.append(_row(sid, ts))
	return _form_csv_text(rows)


def _output_yaml_complete_for(student_ids: list, image_number: int) -> str:
	# Minimal checkpoint YAML carrying just the fields the dashboard
	# count helper needs: a non-empty Student ID, the image-number
	# cross-check, and Image Assessment Complete: true.
	rows = [
		{
			"Student ID": sid,
			"Image Assessment Complete": True,
			"Protein Image Number": image_number,
		}
		for sid in student_ids
	]
	return yaml.safe_dump(rows)


def test_status_row_partial_when_form_has_more_records(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	# Form CSV with 5 submitter rows; checkpoint YAML has only 3 complete.
	form_csv = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_08-Membrane.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	form_csv.write_text(
		_form_csv_with_records(
			["900000001", "900000002", "900000003",
				"900000004", "900000005"],
			"PM",
		),
		encoding="ascii",
	)
	image_dir = pip.get_term_image_dir("spring_2026", 8)
	image_dir.mkdir(parents=True, exist_ok=True)
	(image_dir / "raw").mkdir()
	(image_dir / "raw" / "x.jpg").write_text("", encoding="ascii")
	# Dashboard reads YAML, not CSV, for the graded count. Write the
	# canonical output checkpoint with three complete students.
	(image_dir / "output-protein_image_08.yml").write_text(
		_output_yaml_complete_for(
			["900000001", "900000002", "900000003"], 8
		),
		encoding="ascii",
	)
	(image_dir / "blackboard_upload-protein_image_08.csv").write_text(
		"", encoding="ascii")
	# Roster present so compute_emailed_status doesn't short to MISSING.
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)
	canonical_csvs = sg.find_canonical_form_csvs("spring_2026")
	row = sg.build_status_row(8, "spring_2026", canonical_csvs)
	assert row["form"] == "OK"
	assert row["graded"] == "PARTIAL"
	assert row["form_count"] == 5
	assert row["graded_count"] == 3
	assert row["next_step"] == "regrade"


def test_compute_next_step_partial_routes_to_regrade():
	# Use keyword args to avoid positional ambiguity between
	# bb_status and emailed_status.
	step = sg.compute_next_step(
		form_status="OK",
		downloaded_status="OK",
		graded_status="PARTIAL",
		bb_status="OK",
		emailed_status="OK",
	)
	assert step == "regrade"


def test_render_footer_warnings_lists_partial_image(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	# Hand-built dashboard rows; render_footer_warnings should emit the
	# count line for the PARTIAL image only.
	rows = []
	for n in sg.EXPECTED_IMAGE_NUMBERS:
		rows.append({
			"image": f"{n:02d}",
			"form": "OK",
			"downloaded": "OK",
			"graded": "OK",
			"emailed": "OK",
			"bb_upload": "OK",
			"next_step": "done",
			"form_count": None,
			"graded_count": None,
		})
	# Look up the row by image label so the test does not depend on
	# the position of image 08 inside EXPECTED_IMAGE_NUMBERS.
	target = next(r for r in rows if r["image"] == "08")
	target["graded"] = "PARTIAL"
	target["form_count"] = 41
	target["graded_count"] = 9
	output = sg.render_footer_warnings("spring_2026", rows=rows)
	assert "image 08: 41 form records, 9 graded records" in output


def test_render_footer_warnings_flags_stale_output(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_term_skeleton(tmp_path, "spring_2026")
	rows = []
	for n in sg.EXPECTED_IMAGE_NUMBERS:
		rows.append({
			"image": f"{n:02d}",
			"form": "OK",
			"downloaded": "OK",
			"graded": "OK",
			"emailed": "OK",
			"bb_upload": "OK",
			"next_step": "done",
			"form_count": None,
			"graded_count": None,
		})
	target = next(r for r in rows if r["image"] == "03")
	target["form_count"] = 5
	target["graded_count"] = 7
	output = sg.render_footer_warnings("spring_2026", rows=rows)
	assert "image 03: 7 graded records exceed 5 form records" in output


def test_auto_select_step_routes_partial_to_regrade(tmp_path, monkeypatch):
	# Plan WP-4 wiring: when build_status_row reports next_step="regrade"
	# (the new PARTIAL routing path), auto_select_step must return the
	# "regrade" step verb. Earlier coverage only tested compute_next_step.
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	form_csv = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_08-Membrane.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	form_csv.write_text(
		_form_csv_with_records(
			["900000001", "900000002", "900000003"],
			"PM",
		),
		encoding="ascii",
	)
	image_dir = pip.get_term_image_dir("spring_2026", 8)
	image_dir.mkdir(parents=True, exist_ok=True)
	(image_dir / "raw").mkdir()
	(image_dir / "raw" / "x.jpg").write_text("", encoding="ascii")
	(image_dir / "output-protein_image_08.yml").write_text(
		_output_yaml_complete_for(["900000001"], 8),
		encoding="ascii",
	)
	(image_dir / "blackboard_upload-protein_image_08.csv").write_text(
		"", encoding="ascii")
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)
	step = sg.auto_select_step("spring_2026", 8)
	assert step == "regrade"


# ---- build_grade_command checkpoint resume --------------------------------

def test_build_grade_command_no_yaml_path_matches_today(tmp_path):
	# Initial grade path: no checkpoint passed -> command must NOT
	# carry --yaml-backup-file. This is the default initial-grade flow.
	cmd = sg.build_grade_command(8, "spring_2026")
	assert "--yaml-backup-file" not in cmd


def test_build_grade_command_includes_yaml_backup_file_when_provided(tmp_path):
	# Regrade routing path: when start_grading.run_step picks a
	# checkpoint, build_grade_command appends the existing
	# --yaml-backup-file flag with that path.
	yaml_path = tmp_path / "output-protein_image_08.yml"
	yaml_path.write_text("[]", encoding="ascii")
	cmd = sg.build_grade_command(8, "spring_2026", yaml_backup_file=yaml_path)
	assert "--yaml-backup-file" in cmd
	idx = cmd.index("--yaml-backup-file")
	assert cmd[idx + 1] == str(yaml_path)


# ---- dashboard YAML truth: CONFLICT + multi-checkpoint footer -------------

def test_status_row_conflict_when_deepest_yaml_unparseable(tmp_path,
		monkeypatch):
	# A corrupt deepest checkpoint must surface as graded == CONFLICT
	# with no exception escaping build_status_row, and the footer
	# warning must carry the conflict reason. The dashboard never
	# prompts; the operator fixes the file and re-runs.
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	form_csv = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_08-Membrane.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	form_csv.write_text(
		_form_csv_with_records(["900000001"], "PM"),
		encoding="ascii",
	)
	image_dir = pip.get_term_image_dir("spring_2026", 8)
	image_dir.mkdir(parents=True, exist_ok=True)
	(image_dir / "raw").mkdir()
	(image_dir / "raw" / "x.jpg").write_text("", encoding="ascii")
	# Corrupt YAML: not parseable.
	(image_dir / "output-protein_image_08.yml").write_text(
		"this: is: not: valid: ::", encoding="ascii"
	)
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)
	canonical_csvs = sg.find_canonical_form_csvs("spring_2026")
	row = sg.build_status_row(8, "spring_2026", canonical_csvs)
	assert row["graded"] == "CONFLICT"
	assert row["next_step"] == "fix checkpoint"
	assert row["graded_count"] is None
	assert row["checkpoint_conflict_reason"] is not None
	# Footer surfaces the conflict.
	footer = sg.render_footer_warnings("spring_2026", rows=[row])
	assert "CHECKPOINT CONFLICT" in footer
	assert "image 08" in footer


def test_status_row_multi_checkpoint_footer_lists_others(tmp_path,
		monkeypatch):
	# Two checkpoints on disk (output + post-questions). Dashboard
	# picks the deepest (output) and a footer warning lists the
	# shallower one so the operator knows the partial-run file is
	# still around. No conflict; status is OK.
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	form_csv = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_08-Membrane.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	form_csv.write_text(
		_form_csv_with_records(["900000001"], "PM"),
		encoding="ascii",
	)
	image_dir = pip.get_term_image_dir("spring_2026", 8)
	image_dir.mkdir(parents=True, exist_ok=True)
	(image_dir / "raw").mkdir()
	(image_dir / "raw" / "x.jpg").write_text("", encoding="ascii")
	output_yaml_text = _output_yaml_complete_for(["900000001"], 8)
	(image_dir / "output-protein_image_08.yml").write_text(
		output_yaml_text, encoding="ascii"
	)
	(image_dir / "post-questions_save.yml").write_text(
		output_yaml_text, encoding="ascii"
	)
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)
	canonical_csvs = sg.find_canonical_form_csvs("spring_2026")
	row = sg.build_status_row(8, "spring_2026", canonical_csvs)
	# Status is OK because no conflict and graded_count == form_count.
	assert row["graded"] == "OK"
	assert row["checkpoint_label"] == "output"
	assert len(row["checkpoint_candidates"]) == 2
	footer = sg.render_footer_warnings("spring_2026", rows=[row])
	assert "post-questions_save.yml" in footer
	assert "using output checkpoint" in footer


def test_status_row_dashboard_does_not_call_input(tmp_path, monkeypatch):
	# Hard guard against the dashboard ever becoming interactive: any
	# call to input() during build_status_row would raise from this
	# stub. Cover the OK, PARTIAL, CONFLICT, and MISSING paths in one
	# spin so a regression in any branch is loud.
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	# Prepare image 1: graded OK.
	_drop_canonical_csv(tmp_path, "spring_2026", 1)
	image_dir_1 = pip.get_term_image_dir("spring_2026", 1)
	image_dir_1.mkdir(parents=True, exist_ok=True)
	(image_dir_1 / "raw").mkdir()
	(image_dir_1 / "output-protein_image_01.yml").write_text(
		_output_yaml_complete_for(["900000001"], 1),
		encoding="ascii",
	)
	# Prepare image 2: CONFLICT (corrupt YAML).
	_drop_canonical_csv(tmp_path, "spring_2026", 2)
	image_dir_2 = pip.get_term_image_dir("spring_2026", 2)
	image_dir_2.mkdir(parents=True, exist_ok=True)
	(image_dir_2 / "raw").mkdir()
	(image_dir_2 / "output-protein_image_02.yml").write_text(
		"::not: valid: ::", encoding="ascii"
	)
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)
	# Trip on any call to input() from the dashboard path. A named
	# function reads more clearly than the generator-throw lambda
	# workaround for raising from a lambda body.
	def _raise_on_input(*_a, **_k):
		raise AssertionError("dashboard must not prompt")
	monkeypatch.setattr("builtins.input", _raise_on_input)
	canonical_csvs = sg.find_canonical_form_csvs("spring_2026")
	# Both rows succeed without prompting.
	sg.build_status_row(1, "spring_2026", canonical_csvs)
	sg.build_status_row(2, "spring_2026", canonical_csvs)


def test_compute_next_step_conflict_routes_to_fix_checkpoint():
	step = sg.compute_next_step(
		form_status="OK",
		downloaded_status="OK",
		graded_status="CONFLICT",
		bb_status="MISSING",
		emailed_status="MISSING",
	)
	assert step == "fix checkpoint"


# ---- WP6c case 6: zero complete entries -> MISSING -----------------------

def test_status_row_yaml_with_zero_complete_entries_is_missing(tmp_path,
		monkeypatch):
	# A YAML on disk that carries entries but none of them are
	# Image Assessment Complete must surface as MISSING (regression
	# guard: the dashboard does not "graduate" a checkpoint just
	# because it exists).
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	form_csv = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_08-Membrane.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	form_csv.write_text(
		_form_csv_with_records(["900000001"], "PM"),
		encoding="ascii",
	)
	image_dir = pip.get_term_image_dir("spring_2026", 8)
	image_dir.mkdir(parents=True, exist_ok=True)
	(image_dir / "raw").mkdir()
	# YAML row exists but Image Assessment Complete is False.
	yaml_text = yaml.safe_dump([{
		"Student ID": "900000001",
		"Image Assessment Complete": False,
		"Protein Image Number": 8,
	}])
	(image_dir / "output-protein_image_08.yml").write_text(
		yaml_text, encoding="ascii"
	)
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)
	canonical_csvs = sg.find_canonical_form_csvs("spring_2026")
	row = sg.build_status_row(8, "spring_2026", canonical_csvs)
	assert row["graded"] == "MISSING"


# ---- WP6c case 9: CSV-only on disk, no YAML -> MISSING -------------------

def test_status_row_csv_only_no_yaml_is_missing(tmp_path, monkeypatch):
	# Regression gate against re-introducing CSV-as-truth: a graded
	# CSV on disk with NO YAML must report MISSING. The CSV is
	# downstream of the YAML and is not consulted by the dashboard.
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	form_csv = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_08-Membrane.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	form_csv.write_text(
		_form_csv_with_records(["900000001"], "PM"),
		encoding="ascii",
	)
	image_dir = pip.get_term_image_dir("spring_2026", 8)
	image_dir.mkdir(parents=True, exist_ok=True)
	(image_dir / "raw").mkdir()
	# Only the CSV export exists; no checkpoint YAML.
	(image_dir / "output-protein_image_08.csv").write_text(
		"Student ID\n900000001\n", encoding="ascii"
	)
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)
	canonical_csvs = sg.find_canonical_form_csvs("spring_2026")
	row = sg.build_status_row(8, "spring_2026", canonical_csvs)
	assert row["graded"] == "MISSING"


# ---- WP6c precedence: post-questions chosen when output absent ----------

def test_status_row_picks_post_questions_when_output_absent(tmp_path,
		monkeypatch):
	# pick_checkpoint precedence: with no output-NN.yml on disk but a
	# post-questions_save.yml present, the dashboard must pick the
	# shallower checkpoint. graded_status is OK (form_count == 1,
	# graded_count == 1) and the row's checkpoint_label confirms
	# which file was chosen.
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	form_csv = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_08-Membrane.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	form_csv.write_text(
		_form_csv_with_records(["900000001"], "PM"),
		encoding="ascii",
	)
	image_dir = pip.get_term_image_dir("spring_2026", 8)
	image_dir.mkdir(parents=True, exist_ok=True)
	(image_dir / "raw").mkdir()
	(image_dir / "post-questions_save.yml").write_text(
		_output_yaml_complete_for(["900000001"], 8),
		encoding="ascii",
	)
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)
	canonical_csvs = sg.find_canonical_form_csvs("spring_2026")
	row = sg.build_status_row(8, "spring_2026", canonical_csvs)
	assert row["graded"] == "OK"
	assert row["checkpoint_label"] == "post-questions"


# ---- WP6c case 4: run_step regrade abort on conflict ---------------------

def test_run_step_regrade_aborts_non_zero_on_conflict(tmp_path, monkeypatch):
	# Operator runs `start_grading.py` in regrade mode for an image
	# whose deepest checkpoint is corrupt. run_step must:
	#  - return a non-zero exit code (specifically 2 to distinguish
	#    "operator must repair" from "user aborted prompt"),
	#  - NOT call subprocess.run (no grader spawn),
	#  - NOT prompt via input(),
	#  - print a message naming the offending file.
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	form_csv = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_08-Membrane.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	form_csv.write_text(
		_form_csv_with_records(["900000001"], "PM"),
		encoding="ascii",
	)
	image_dir = pip.get_term_image_dir("spring_2026", 8)
	image_dir.mkdir(parents=True, exist_ok=True)
	(image_dir / "raw").mkdir()
	(image_dir / "raw" / "x.jpg").write_text("", encoding="ascii")
	# Corrupt deepest checkpoint -> pick_checkpoint reports conflict.
	corrupt_path = image_dir / "output-protein_image_08.yml"
	corrupt_path.write_text("::not: valid: ::", encoding="ascii")
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)

	def _raise_on_input(*_a, **_k):
		raise AssertionError("regrade must not prompt on conflict")
	monkeypatch.setattr("builtins.input", _raise_on_input)

	def _raise_on_subprocess(*_a, **_k):
		raise AssertionError("regrade must not spawn the grader on conflict")
	monkeypatch.setattr("subprocess.run", _raise_on_subprocess)

	exit_code = sg.run_step("spring_2026", 8, "regrade")
	assert exit_code == 2


# ---- WP6c case 1: regrade with output-NN.yml routes through --yaml-backup-file ----

def test_run_step_regrade_passes_output_yml_to_grader(tmp_path, monkeypatch):
	# When a clean output checkpoint exists, run_step("regrade") spawns
	# the grader with --yaml-backup-file pointing at that file. We
	# capture the spawned argv via a subprocess.run stub.
	_install_fake_repo_root(monkeypatch, tmp_path)
	skel = _make_term_skeleton(tmp_path, "spring_2026")
	form_csv = pip.get_forms_dir("spring_2026") / "BCHM_Prot_Img_08-Membrane.csv"
	pip.get_forms_dir("spring_2026").mkdir(parents=True, exist_ok=True)
	form_csv.write_text(
		_form_csv_with_records(["900000001"], "PM"),
		encoding="ascii",
	)
	image_dir = pip.get_term_image_dir("spring_2026", 8)
	image_dir.mkdir(parents=True, exist_ok=True)
	(image_dir / "raw").mkdir()
	(image_dir / "raw" / "x.jpg").write_text("", encoding="ascii")
	output_yaml = image_dir / "output-protein_image_08.yml"
	output_yaml.write_text(
		_output_yaml_complete_for(["900000001"], 8),
		encoding="ascii",
	)
	# No graded CSV on disk -> no overwrite prompt -> no input call.
	roster_csv = skel["term_dir"] / pip.ROSTER_FILENAME
	roster_csv.write_text(
		"First Name,Last Name,Username,Student ID,Alias\n",
		encoding="ascii",
	)

	captured: dict = {}

	def _capture_subprocess(argv, *_a, **_k):
		captured["argv"] = argv
		# Return a duck-type stand-in for subprocess.CompletedProcess
		# carrying just the .returncode that run_step reads.
		return types.SimpleNamespace(returncode=0)

	# Guard against the overwrite-prompt condition changing in the
	# future and reaching input(): no graded CSV is on disk in this
	# fixture, so the prompt branch should not execute. If it does,
	# the stub raises and the test fails loudly rather than blocking.
	def _raise_on_input(*_a, **_k):
		raise AssertionError("regrade-resume must not prompt on this fixture")
	monkeypatch.setattr("builtins.input", _raise_on_input)
	monkeypatch.setattr("subprocess.run", _capture_subprocess)

	exit_code = sg.run_step("spring_2026", 8, "regrade")
	assert exit_code == 0
	argv = captured["argv"]
	assert "--yaml-backup-file" in argv
	idx = argv.index("--yaml-backup-file")
	assert argv[idx + 1] == str(output_yaml)
