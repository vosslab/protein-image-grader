"""
Tests for local_migrations.protein_images (Patches 2a, 2b, 2c).

All tests build a synthetic legacy tree under tmp_path. The real
Protein_Images/ data root is never touched. No filesystem mutations
occur outside tmp_path.
"""

import pathlib
import tarfile

import pytest

import yaml

import local_migrations.protein_images.backup_check as backup_check
import local_migrations.protein_images.classifier as classifier
import local_migrations.protein_images.executor as executor
import local_migrations.protein_images.migrate_protein_images as cli
import local_migrations.protein_images.planner as planner
import local_migrations.protein_images.reporting as reporting


ACTIVE_TERM = "spring_2026"


def _make_legacy_tree(root: pathlib.Path) -> None:
	"""Build one example of every legacy bucket the classifier handles."""
	# Already-canonical items. image_bank/ vs ARCHIVE_IMAGES/ collide on
	# case-insensitive macOS FS; legacy wins here. Canonical path tested
	# separately.
	(root / "active_term.txt").write_text("spring_2026\n")
	(root / "semesters").mkdir()
	(root / "legacy").mkdir()
	# Legacy folders.
	(root / "ARCHIVE_IMAGES").mkdir()
	(root / "2024_Spring").mkdir()
	(root / "2025_1Spring").mkdir()
	(root / "DOWNLOAD_03_year_2025").mkdir()
	(root / "IMAGE_07").mkdir()
	(root / "PROFILE_IMAGES").mkdir()
	(root / "YAML_files").mkdir()
	(root / "Protein_Images_CVS").mkdir()
	# Top-level files.
	(root / "BCHM_Prot_Img_04-Active_Site.csv").write_text("col1,col2\n")
	(root / "current_students.csv").write_text("id,name\n")
	(root / "roster_2025.csv").write_text("id,name\n")
	(root / "Spring_2026_IDs.txt").write_text("900000001\n")
	(root / "backup.yml").write_text("k: v\n")
	(root / "crash_data.yml").write_text("k: v\n")
	(root / "force_exit_save.yml").write_text("k: v\n")
	(root / "temp_save.yml").write_text("k: v\n")
	(root / "wrong.yml").write_text("k: v\n")
	(root / "output-protein_image_06.yml").write_text("k: v\n")
	(root / "image_hashes.yml").write_text("k: v\n")
	(root / "packs-311.txt").write_text("x\n")
	(root / "test_graph.py").write_text("x\n")
	(root / "image_02.html").write_text("<html></html>\n")
	(root / "profiles.html").write_text("<html></html>\n")
	(root / "api_file.json").write_text("{}\n")
	(root / "service_key.json").write_text("{}\n")
	(root / "requirements.txt").write_text("requests\n")
	(root / "grade_protein_image.py").symlink_to("/nonexistent/grade_protein_image.py")
	(root / "completely_unknown_thing.dat").write_text("x")


def _make_backup_dir(parent: pathlib.Path) -> pathlib.Path:
	# Minimal directory backup that satisfies backup_check requirements.
	backup = parent / "Protein_Images_backup_2026-05-05"
	backup.mkdir()
	(backup / "ARCHIVE_IMAGES").mkdir()
	(backup / "DOWNLOAD_03_year_2025").mkdir()
	return backup


def _make_backup_tar(parent: pathlib.Path) -> pathlib.Path:
	# Minimal tar backup that satisfies backup_check requirements.
	staging = parent / "_tar_staging"
	staging.mkdir()
	(staging / "Protein_Images").mkdir()
	(staging / "Protein_Images" / "ARCHIVE_IMAGES").mkdir()
	(staging / "Protein_Images" / "DOWNLOAD_03_year_2025").mkdir()
	tar_path = parent / "protein_image.tar"
	with tarfile.open(tar_path, "w") as tf:
		tf.add(staging / "Protein_Images", arcname="Protein_Images")
	return tar_path


@pytest.fixture
def synth_root(tmp_path):
	root = tmp_path / "Protein_Images"
	root.mkdir()
	_make_legacy_tree(root)
	return root


def _classify(synth_root: pathlib.Path, name: str) -> classifier.Move:
	return classifier.classify(synth_root / name, synth_root, ACTIVE_TERM)


# -----------------------------------------------------------------
# Patch 2a: classifier
# -----------------------------------------------------------------

def test_canonical_items_are_unchanged(synth_root):
	for name in ("active_term.txt", "semesters", "legacy"):
		move = _classify(synth_root, name)
		assert move.bucket == "unchanged", name
		assert move.dst is None, name


def test_canonical_image_bank_unchanged(tmp_path):
	root = tmp_path / "Protein_Images"
	root.mkdir()
	(root / "image_bank").mkdir()
	move = classifier.classify(root / "image_bank", root, ACTIVE_TERM)
	assert move.bucket == "unchanged"
	assert move.dst is None


def test_image_bank_high(synth_root):
	move = _classify(synth_root, "ARCHIVE_IMAGES")
	assert move.bucket == "high_confidence_moves"
	assert move.confidence == "high"
	assert move.dst == synth_root / "image_bank"


def test_legacy_term_folders_high(synth_root):
	move = _classify(synth_root, "2024_Spring")
	assert move.bucket == "high_confidence_moves"
	assert move.dst == synth_root / "semesters" / "spring_2024"

	move = _classify(synth_root, "2025_1Spring")
	assert move.bucket == "high_confidence_moves"
	assert move.dst == synth_root / "semesters" / "spring_2025"


def test_download_folder_high(synth_root):
	move = _classify(synth_root, "DOWNLOAD_03_year_2025")
	assert move.bucket == "high_confidence_moves"
	assert move.dst == (
		synth_root / "semesters" / "spring_2025" / "submissions" / "download_03_raw"
	)


def test_image_folder_low_with_inferred_term(synth_root):
	move = _classify(synth_root, "IMAGE_07")
	assert move.bucket == "legacy_review_moves"
	assert move.confidence == "low"
	parts = move.dst.relative_to(synth_root).parts
	assert parts[0] == "semesters"
	assert parts[2] == "submissions"
	assert parts[3] == "image_07"
	assert any("birthtime=" in e or "mtime=" in e for e in move.evidence)


def test_form_csv_to_active_term_high(synth_root):
	move = _classify(synth_root, "BCHM_Prot_Img_04-Active_Site.csv")
	assert move.bucket == "high_confidence_moves"
	assert move.dst == (
		synth_root / "semesters" / ACTIVE_TERM / "forms"
		/ "BCHM_Prot_Img_04-Active_Site.csv"
	)


def test_dated_roster_high(synth_root):
	move = _classify(synth_root, "roster_2025.csv")
	assert move.bucket == "high_confidence_moves"
	assert move.dst == synth_root / "semesters" / "spring_2025" / "roster.csv"


def test_current_students_low(synth_root):
	move = _classify(synth_root, "current_students.csv")
	assert move.bucket == "legacy_review_moves"
	assert move.dst == synth_root / "semesters" / ACTIVE_TERM / "roster.csv"


def test_term_ids_file_high(synth_root):
	move = _classify(synth_root, "Spring_2026_IDs.txt")
	assert move.bucket == "high_confidence_moves"
	assert move.dst == synth_root / "semesters" / "spring_2026" / "roster_ids.txt"


def test_needs_review_folders_low(synth_root):
	for name, sub in (("PROFILE_IMAGES", "profile_images"),
		("YAML_files", "yaml_files"),
		("Protein_Images_CVS", "protein_images_cvs")):
		move = _classify(synth_root, name)
		assert move.bucket == "legacy_review_moves", name
		assert move.dst == synth_root / "legacy" / "needs_review" / sub / name


def test_credentials_routed_low(synth_root):
	for name in ("api_file.json", "service_key.json"):
		move = _classify(synth_root, name)
		assert move.bucket == "legacy_review_moves", name
		assert move.dst == (
			synth_root / "legacy" / "needs_review" / "credentials" / name
		)


def test_state_files_routed_low(synth_root):
	for name in ("backup.yml", "crash_data.yml", "force_exit_save.yml",
		"temp_save.yml", "wrong.yml", "output-protein_image_06.yml",
		"image_hashes.yml"):
		move = _classify(synth_root, name)
		assert move.bucket == "legacy_review_moves", name
		assert move.dst == (
			synth_root / "legacy" / "needs_review" / "state_files" / name
		)


def test_scratch_files_routed_low(synth_root):
	for name in ("packs-311.txt", "test_graph.py", "image_02.html", "profiles.html"):
		move = _classify(synth_root, name)
		assert move.bucket == "legacy_review_moves", name
		assert move.dst == synth_root / "legacy" / "needs_review" / "scratch" / name


def test_requirements_routed_to_broken_symlinks(synth_root):
	move = _classify(synth_root, "requirements.txt")
	assert move.bucket == "legacy_review_moves"
	assert move.dst == (
		synth_root / "legacy" / "needs_review" / "broken_symlinks" / "requirements.txt"
	)


def test_py_symlink_routed_to_broken_symlinks_high(synth_root):
	move = _classify(synth_root, "grade_protein_image.py")
	assert move.bucket == "legacy_review_moves"
	assert move.confidence == "high"
	assert move.dst == (
		synth_root / "legacy" / "needs_review" / "broken_symlinks"
		/ "grade_protein_image.py"
	)


def test_unknown_item_falls_to_scratch(synth_root):
	move = _classify(synth_root, "completely_unknown_thing.dat")
	assert move.bucket == "legacy_review_moves"
	assert move.confidence == "low"
	assert move.dst == (
		synth_root / "legacy" / "needs_review" / "scratch"
		/ "completely_unknown_thing.dat"
	)


# -----------------------------------------------------------------
# Patch 2a: planner
# -----------------------------------------------------------------

def test_planner_groups_correctly(synth_root):
	report = planner.plan(synth_root, ACTIVE_TERM)
	assert len(report.high_confidence_moves) >= 5
	assert len(report.legacy_review_moves) >= 10
	assert len(report.unchanged) >= 3
	assert report.active_term == ACTIVE_TERM
	assert report.generated_at_utc.endswith("Z")


def test_planner_does_not_mutate_filesystem(synth_root):
	before = sorted(p.name for p in synth_root.iterdir())
	planner.plan(synth_root, ACTIVE_TERM)
	after = sorted(p.name for p in synth_root.iterdir())
	assert before == after


def test_report_serialization_round_trip(synth_root, tmp_path):
	report = planner.plan(synth_root, ACTIVE_TERM)
	payload = reporting.report_to_dict(report)
	out_path = tmp_path / "report.yml"
	out_path.write_text(yaml.safe_dump(payload, sort_keys=False))
	loaded = yaml.safe_load(out_path.read_text())
	assert loaded["active_term"] == ACTIVE_TERM
	for key in ("high_confidence_moves", "legacy_review_moves", "unchanged"):
		assert key in loaded
	some = (loaded["high_confidence_moves"] + loaded["legacy_review_moves"])[0]
	assert {"src", "dst", "confidence", "bucket", "evidence"} <= some.keys()


def test_planner_rejects_non_directory(tmp_path):
	target = tmp_path / "not_a_dir"
	target.write_text("x")
	with pytest.raises(NotADirectoryError):
		planner.plan(target, ACTIVE_TERM)


# -----------------------------------------------------------------
# Patch 2b: CLI smoke
# -----------------------------------------------------------------

def _install_fake_repo_root(monkeypatch, repo_root: pathlib.Path) -> None:
	import protein_image_grader.archive_paths
	monkeypatch.setattr(
		protein_image_grader.archive_paths, "get_repo_root",
		lambda start_path=None: repo_root,
	)


def test_cli_dry_run_writes_report_and_does_not_mutate(tmp_path, monkeypatch, capsys):
	repo_root = tmp_path
	data_root = repo_root / "Protein_Images"
	data_root.mkdir()
	_make_legacy_tree(data_root)
	(data_root / "active_term.txt").write_text(ACTIVE_TERM + "\n")
	_install_fake_repo_root(monkeypatch, repo_root)

	report_path = tmp_path / "dryrun.yml"
	rc = cli.main(["--report-out", str(report_path)])

	assert rc == 0
	assert report_path.is_file()
	loaded = yaml.safe_load(report_path.read_text())
	for key in ("high_confidence_moves", "legacy_review_moves", "unchanged"):
		assert key in loaded
		assert isinstance(loaded[key], list)
	assert loaded["active_term"] == ACTIVE_TERM
	assert loaded["high_confidence_moves"]
	assert loaded["legacy_review_moves"]

	captured = capsys.readouterr()
	assert "Migration dry-run" in captured.out
	# Tree unchanged.
	expected = sorted([
		"active_term.txt", "semesters", "legacy", "ARCHIVE_IMAGES",
		"2024_Spring", "2025_1Spring", "DOWNLOAD_03_year_2025", "IMAGE_07",
		"PROFILE_IMAGES", "YAML_files", "Protein_Images_CVS",
		"BCHM_Prot_Img_04-Active_Site.csv", "current_students.csv",
		"roster_2025.csv", "Spring_2026_IDs.txt", "backup.yml",
		"crash_data.yml", "force_exit_save.yml", "temp_save.yml", "wrong.yml",
		"output-protein_image_06.yml", "image_hashes.yml", "packs-311.txt",
		"test_graph.py", "image_02.html", "profiles.html", "api_file.json",
		"service_key.json", "requirements.txt", "grade_protein_image.py",
		"completely_unknown_thing.dat",
	])
	assert sorted(p.name for p in data_root.iterdir()) == expected


def test_cli_apply_requires_report_in_and_backup(monkeypatch):
	# argparse exits 2 when required mutually-conditional args are missing.
	with pytest.raises(SystemExit) as e1:
		cli.parse_args(["--apply"])
	assert e1.value.code == 2
	with pytest.raises(SystemExit) as e2:
		cli.parse_args(["--apply", "--report-in", "/tmp/x"])
	assert e2.value.code == 2


# -----------------------------------------------------------------
# Patch 2c: backup_check
# -----------------------------------------------------------------

def test_backup_check_directory_ok(tmp_path):
	backup = _make_backup_dir(tmp_path)
	info = backup_check.verify_backup(backup)
	assert info["format"] == "directory"


def test_backup_check_tar_ok(tmp_path):
	tar_path = _make_backup_tar(tmp_path)
	info = backup_check.verify_backup(tar_path)
	assert info["format"] == "tar"


def test_backup_check_missing_path(tmp_path):
	with pytest.raises(backup_check.BackupMissingError):
		backup_check.verify_backup(tmp_path / "nope")


def test_backup_check_directory_missing_archive(tmp_path):
	bad = tmp_path / "bad_backup"
	bad.mkdir()
	(bad / "DOWNLOAD_01_year_2025").mkdir()
	# Missing ARCHIVE_IMAGES.
	with pytest.raises(backup_check.BackupMissingError) as exc:
		backup_check.verify_backup(bad)
	assert "ARCHIVE_IMAGES" in str(exc.value)


def test_backup_check_directory_missing_download(tmp_path):
	bad = tmp_path / "bad_backup"
	bad.mkdir()
	(bad / "ARCHIVE_IMAGES").mkdir()
	with pytest.raises(backup_check.BackupMissingError) as exc:
		backup_check.verify_backup(bad)
	assert "DOWNLOAD_" in str(exc.value)


def test_backup_check_unknown_format(tmp_path):
	bad = tmp_path / "weird.zip"
	bad.write_bytes(b"x")
	with pytest.raises(backup_check.BackupMissingError):
		backup_check.verify_backup(bad)


# -----------------------------------------------------------------
# Patch 2c: executor
# -----------------------------------------------------------------

def _write_dry_run_report(synth_root: pathlib.Path, out_path: pathlib.Path) -> None:
	report = planner.plan(synth_root, ACTIVE_TERM)
	out_path.write_text(yaml.safe_dump(reporting.report_to_dict(report), sort_keys=False))


def test_executor_applies_moves_with_directory_backup(synth_root, tmp_path):
	report_path = tmp_path / "dryrun.yml"
	_write_dry_run_report(synth_root, report_path)
	backup = _make_backup_dir(tmp_path)
	applied_path = tmp_path / "applied.yml"

	result = executor.apply(
		data_root=synth_root,
		report_path=report_path,
		backup_path=backup,
		output_report_path=applied_path,
	)
	assert result["summary"]["errors"] == 0
	assert result["summary"]["applied"] >= 5
	assert applied_path.is_file()

	# Spot-check a few moves landed.
	# On case-insensitive macOS FS, exists() returns True for both spellings;
	# verify the on-disk name via iterdir instead.
	top_names = {p.name for p in synth_root.iterdir()}
	assert "image_bank" in top_names
	assert "ARCHIVE_IMAGES" not in top_names
	assert (synth_root / "semesters" / "spring_2024").exists()
	assert (synth_root / "semesters" / "spring_2025"
		/ "submissions" / "download_03_raw").exists()
	assert (synth_root / "semesters" / "spring_2025" / "roster.csv").is_file()
	assert (synth_root / "legacy" / "needs_review"
		/ "credentials" / "api_file.json").is_file()


def test_executor_refuses_without_backup(synth_root, tmp_path):
	report_path = tmp_path / "dryrun.yml"
	_write_dry_run_report(synth_root, report_path)
	with pytest.raises(backup_check.BackupMissingError):
		executor.apply(
			data_root=synth_root,
			report_path=report_path,
			backup_path=tmp_path / "missing_backup",
			output_report_path=tmp_path / "applied.yml",
		)
	# Ensure no moves happened: ARCHIVE_IMAGES still in place.
	assert (synth_root / "ARCHIVE_IMAGES").exists()


def test_executor_accepts_tar_backup(synth_root, tmp_path):
	report_path = tmp_path / "dryrun.yml"
	_write_dry_run_report(synth_root, report_path)
	tar_path = _make_backup_tar(tmp_path)
	result = executor.apply(
		data_root=synth_root,
		report_path=report_path,
		backup_path=tar_path,
		output_report_path=tmp_path / "applied.yml",
	)
	assert result["summary"]["errors"] == 0
	assert result["backup"]["format"] == "tar"


def test_executor_records_skip_for_missing_src(synth_root, tmp_path):
	report_path = tmp_path / "dryrun.yml"
	_write_dry_run_report(synth_root, report_path)
	# Remove one src before apply to simulate concurrent change.
	(synth_root / "BCHM_Prot_Img_04-Active_Site.csv").unlink()
	backup = _make_backup_dir(tmp_path)
	result = executor.apply(
		data_root=synth_root,
		report_path=report_path,
		backup_path=backup,
		output_report_path=tmp_path / "applied.yml",
	)
	skipped = [i for i in result["items"] if i["status"] == "skipped"]
	assert any("src missing" in i["detail"] for i in skipped)


def test_executor_records_error_when_dst_exists(synth_root, tmp_path):
	report_path = tmp_path / "dryrun.yml"
	_write_dry_run_report(synth_root, report_path)
	# Pre-create the destination of the ARCHIVE_IMAGES move so it conflicts.
	# But we cannot create image_bank/ next to ARCHIVE_IMAGES on macOS,
	# so use a different conflict: pre-create the dated-roster destination.
	pre = synth_root / "semesters" / "spring_2025" / "roster.csv"
	pre.parent.mkdir(parents=True)
	pre.write_text("conflict")
	backup = _make_backup_dir(tmp_path)
	result = executor.apply(
		data_root=synth_root,
		report_path=report_path,
		backup_path=backup,
		output_report_path=tmp_path / "applied.yml",
	)
	errors = [i for i in result["items"] if i["status"] == "error"]
	assert any("dst already exists" in i["detail"] for i in errors)


# -----------------------------------------------------------------
# Patch 2c: CLI apply
# -----------------------------------------------------------------

def test_cli_apply_runs_end_to_end(tmp_path, monkeypatch):
	repo_root = tmp_path
	data_root = repo_root / "Protein_Images"
	data_root.mkdir()
	_make_legacy_tree(data_root)
	(data_root / "active_term.txt").write_text(ACTIVE_TERM + "\n")
	_install_fake_repo_root(monkeypatch, repo_root)

	report_path = tmp_path / "dryrun.yml"
	rc_dry = cli.main(["--report-out", str(report_path)])
	assert rc_dry == 0

	backup = _make_backup_dir(tmp_path)
	applied_out = tmp_path / "applied.yml"
	rc_apply = cli.main([
		"--apply",
		"--report-in", str(report_path),
		"--backup-path", str(backup),
		"--applied-report-out", str(applied_out),
	])
	assert rc_apply == 0
	assert applied_out.is_file()
	loaded = yaml.safe_load(applied_out.read_text())
	assert loaded["summary"]["errors"] == 0
	assert (data_root / "image_bank").exists()
