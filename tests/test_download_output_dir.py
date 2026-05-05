"""
Phase 0 tests for download_submission_images.py canonical output dir.

These tests pin three rules:
- A canonical CSV path
  (Protein_Images/semesters/<term>/forms/BCHM_Prot_Img_NN-*.csv) implies
  the canonical submissions/download_NN_raw output dir.
- An explicit --output-dir override wins verbatim, with no inference.
- A non-canonical CSV path with no override is a hard error, not a
  silent fallback to data/runs.

All tests use tmp_path + monkeypatch against archive_paths.get_repo_root
so they never touch the real Synology-synced data root.
"""

import pathlib

import pytest

import protein_image_grader.archive_paths
import protein_image_grader.protein_images_path as pip
import protein_image_grader.download_submission_images as dsi


def _install_fake_repo_root(monkeypatch: pytest.MonkeyPatch,
		repo_root: pathlib.Path) -> None:
	# Both archive_paths and protein_images_path read the repo root from
	# archive_paths.get_repo_root, so a single patch is enough.
	monkeypatch.setattr(
		protein_image_grader.archive_paths,
		"get_repo_root",
		lambda start_path=None: repo_root,
	)


def _make_canonical_csv(repo_root: pathlib.Path, term: str,
		image_number: int, label: str = "Example") -> pathlib.Path:
	# Build the canonical Protein_Images/semesters/<term>/forms/<file> tree
	# and return the CSV path.
	forms_dir = repo_root / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR \
		/ term / pip.FORMS_SUBDIR
	forms_dir.mkdir(parents=True)
	csv_path = forms_dir / f"BCHM_Prot_Img_{image_number:02d}-{label}.csv"
	csv_path.write_text("", encoding="ascii")
	return csv_path


def test_extract_image_number_from_canonical_basename():
	assert dsi.extract_image_number_from_csv_basename(
		"BCHM_Prot_Img_07-Whatever.csv") == 7
	assert dsi.extract_image_number_from_csv_basename(
		"BCHM_Prot_Img_01-White_Background.csv") == 1


def test_extract_image_number_rejects_non_canonical():
	with pytest.raises(ValueError):
		dsi.extract_image_number_from_csv_basename("random.csv")


def test_infer_canonical_output_dir_canonical(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	csv_path = _make_canonical_csv(tmp_path, "spring_2026", 4)
	out = dsi.infer_canonical_output_dir(str(csv_path))
	expected = (
		tmp_path / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR
		/ "spring_2026" / pip.SUBMISSIONS_SUBDIR / "download_04_raw"
	)
	assert out == expected


def test_infer_canonical_output_dir_non_canonical_returns_none(tmp_path):
	# A CSV outside the canonical tree returns None (the caller decides
	# whether that is an error).
	stray = tmp_path / "BCHM_Prot_Img_05-Stray.csv"
	stray.write_text("", encoding="ascii")
	assert dsi.infer_canonical_output_dir(str(stray)) is None


def test_resolve_image_dir_canonical_default(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	csv_path = _make_canonical_csv(tmp_path, "spring_2026", 4)
	resolved = dsi.resolve_image_dir(str(csv_path), None, 4)
	assert resolved.endswith("submissions/download_04_raw")


def test_resolve_image_dir_explicit_override_wins(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	csv_path = _make_canonical_csv(tmp_path, "spring_2026", 4)
	override = str(tmp_path / "anywhere_else")
	# Override is honored verbatim even when the CSV is canonical.
	assert dsi.resolve_image_dir(str(csv_path), override, 4) == override


def test_resolve_image_dir_non_canonical_without_override_errors(tmp_path):
	stray = tmp_path / "BCHM_Prot_Img_05-Stray.csv"
	stray.write_text("", encoding="ascii")
	with pytest.raises(ValueError) as excinfo:
		dsi.resolve_image_dir(str(stray), None, 5)
	# Error message must point the user at the canonical location, not
	# silently fall back to data/runs.
	message = str(excinfo.value)
	assert "non-canonical" in message
	assert "Protein_Images/semesters" in message


def test_resolve_image_dir_image_number_mismatch_errors(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	# CSV is image 04, but caller insists on image 07. This should fail
	# rather than silently use the wrong dir.
	csv_path = _make_canonical_csv(tmp_path, "spring_2026", 4)
	with pytest.raises(ValueError):
		dsi.resolve_image_dir(str(csv_path), None, 7)
