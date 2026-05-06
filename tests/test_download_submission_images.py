"""
Tests for resolve_csv_paths in download_submission_images.

Uses a fake repo root so tests never touch the real Protein_Images/ dir.
"""

import argparse
import pathlib

import pytest

import protein_image_grader.archive_paths
import protein_image_grader.protein_images_path as pip
import protein_image_grader.download_submission_images as dsi


def _install_fake_repo_root(monkeypatch, repo_root):
	monkeypatch.setattr(
		protein_image_grader.archive_paths,
		"get_repo_root",
		lambda start_path=None: repo_root,
	)


def _make_forms(repo_root: pathlib.Path, term: str,
		image_numbers: list, extra: list = None) -> pathlib.Path:
	# Build Protein_Images/semesters/<term>/forms/ with one CSV per image.
	forms_dir = (
		repo_root / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR
		/ term / pip.FORMS_SUBDIR
	)
	forms_dir.mkdir(parents=True)
	(repo_root / pip.PROTEIN_IMAGES_NAME / pip.ACTIVE_TERM_FILENAME).write_text(
		term, encoding="ascii"
	)
	for n in image_numbers:
		(forms_dir / f"BCHM_Prot_Img_{n:02d}-Topic.csv").write_text(
			"", encoding="ascii"
		)
	for name in (extra or []):
		(forms_dir / name).write_text("", encoding="ascii")
	return forms_dir


def _args(**overrides) -> argparse.Namespace:
	# Minimal Namespace mirroring parse_args defaults.
	ns = argparse.Namespace(
		csvfile=None, image_number=0, all_images=False, term=None,
		output_dir=None,
	)
	for k, v in overrides.items():
		setattr(ns, k, v)
	return ns


def test_resolve_returns_explicit_csv(monkeypatch, tmp_path):
	# -i wins regardless of canonical layout.
	_install_fake_repo_root(monkeypatch, tmp_path)
	csv_path = tmp_path / "anywhere.csv"
	csv_path.write_text("", encoding="ascii")
	paths = dsi.resolve_csv_paths(_args(csvfile=str(csv_path)))
	assert paths == [pathlib.Path(str(csv_path))]


def test_resolve_image_number_finds_canonical(monkeypatch, tmp_path):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_forms(tmp_path, "spring_2026", [1, 3, 5])
	paths = dsi.resolve_csv_paths(_args(image_number=3))
	assert len(paths) == 1
	assert paths[0].name == "BCHM_Prot_Img_03-Topic.csv"


def test_resolve_image_number_missing_raises(monkeypatch, tmp_path):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_forms(tmp_path, "spring_2026", [1, 2])
	with pytest.raises(FileNotFoundError):
		dsi.resolve_csv_paths(_args(image_number=7))


def test_resolve_all_returns_sorted_list(monkeypatch, tmp_path):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_forms(tmp_path, "spring_2026", [2, 1, 4])
	paths = dsi.resolve_csv_paths(_args(all_images=True))
	names = [p.name for p in paths]
	assert names == [
		"BCHM_Prot_Img_01-Topic.csv",
		"BCHM_Prot_Img_02-Topic.csv",
		"BCHM_Prot_Img_04-Topic.csv",
	]


def test_resolve_no_args_raises(monkeypatch, tmp_path):
	_install_fake_repo_root(monkeypatch, tmp_path)
	with pytest.raises(ValueError):
		dsi.resolve_csv_paths(_args())


def test_find_canonical_form_csvs_skips_noncanonical(monkeypatch, tmp_path):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_forms(tmp_path, "spring_2026", [1],
		extra=["random.csv", "BCHM_Prot_Img_99-Topic.csv"])
	by_image = pip.find_canonical_form_csvs("spring_2026")
	# 99 is two digits and matches the regex; "random.csv" is dropped.
	assert sorted(by_image.keys()) == [1, 99]
