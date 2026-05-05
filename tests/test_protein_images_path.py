"""
Pin the contract of protein_image_grader.protein_images_path.

All tests use tmp_path + monkeypatch against archive_paths.get_repo_root
so they never touch the real Synology-synced data root.
"""

import pathlib

import pytest

import protein_image_grader.archive_paths
import protein_image_grader.protein_images_path as pip


def _install_fake_repo_root(monkeypatch: pytest.MonkeyPatch, repo_root: pathlib.Path) -> None:
	# Force both modules to see the same fake repo root.
	monkeypatch.setattr(
		protein_image_grader.archive_paths,
		"get_repo_root",
		lambda start_path=None: repo_root,
	)


def _make_data_root(repo_root: pathlib.Path) -> pathlib.Path:
	# Create a minimal Protein_Images/ skeleton inside a fake repo root.
	data_root = repo_root / pip.PROTEIN_IMAGES_NAME
	data_root.mkdir()
	return data_root


def test_get_protein_images_dir_present(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	assert pip.get_protein_images_dir() == data_root.resolve()


def test_get_protein_images_dir_missing(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	with pytest.raises(FileNotFoundError) as excinfo:
		pip.get_protein_images_dir()
	assert "ln -s" in str(excinfo.value)


def test_get_protein_images_dir_not_a_directory(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	(tmp_path / pip.PROTEIN_IMAGES_NAME).write_text("not a dir")
	with pytest.raises(NotADirectoryError):
		pip.get_protein_images_dir()


def test_get_image_bank_dir_present(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	bank = data_root / pip.IMAGE_BANK_SUBDIR
	bank.mkdir()
	assert pip.get_image_bank_dir() == bank


def test_get_image_bank_dir_missing(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_data_root(tmp_path)
	with pytest.raises(FileNotFoundError) as excinfo:
		pip.get_image_bank_dir()
	assert "image_bank" in str(excinfo.value)


def test_get_active_term_from_file(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	(data_root / pip.ACTIVE_TERM_FILENAME).write_text("spring_2026\n")
	assert pip.get_active_term() == "spring_2026"


def test_get_active_term_override_wins(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	(data_root / pip.ACTIVE_TERM_FILENAME).write_text("spring_2026\n")
	assert pip.get_active_term("fall_2024") == "fall_2024"


def test_get_active_term_missing_file(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_data_root(tmp_path)
	with pytest.raises(FileNotFoundError) as excinfo:
		pip.get_active_term()
	assert "active_term.txt" in str(excinfo.value)


def test_get_active_term_empty_file(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	(data_root / pip.ACTIVE_TERM_FILENAME).write_text("\n")
	with pytest.raises(ValueError):
		pip.get_active_term()


def test_per_term_paths(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	term = "spring_2026"
	expected_term_dir = data_root / "semesters" / term
	assert pip.get_term_dir(term) == expected_term_dir
	assert pip.get_forms_dir(term) == expected_term_dir / "forms"
	assert pip.get_yaml_dir(term) == expected_term_dir / "yaml"
	assert pip.get_grades_dir(term) == expected_term_dir / "grades"
	assert pip.get_submissions_dir(term) == expected_term_dir / "submissions"
	assert pip.get_roster_csv(term) == expected_term_dir / "roster.csv"


def test_get_credentials_dir_is_user_local():
	# Must NOT live inside Protein_Images/.
	credentials = pip.get_credentials_dir()
	assert "Protein_Images" not in str(credentials)
	assert credentials == pathlib.Path("~/.config/bchm_355/credentials").expanduser()


def test_module_import_does_not_touch_filesystem(monkeypatch):
	# Re-importing the module must not raise even with no data root configured.
	def _boom(*args, **kwargs):
		raise AssertionError("filesystem accessed at import time")

	monkeypatch.setattr(pathlib.Path, "exists", _boom)
	import importlib
	importlib.reload(pip)
