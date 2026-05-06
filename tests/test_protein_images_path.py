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
	assert pip.get_roster_csv(term) == expected_term_dir / "roster.csv"
	assert pip.get_email_log_yaml(term) == expected_term_dir / "email_log.yml"


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


#============================================
# Tests for new helpers (plan: unified image storage layout)

def test_get_image_hashes_yaml(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	hashes_yaml = pip.get_image_hashes_yaml()
	assert hashes_yaml == tmp_path / "image_hashes.yml"


def test_get_image_hashes_yaml_with_explicit_root(tmp_path):
	hashes_yaml = pip.get_image_hashes_yaml(tmp_path)
	assert hashes_yaml == tmp_path / "image_hashes.yml"


def test_season_year_term_spring():
	assert pip.season_year_term(2026, 1) == "spring_2026"
	assert pip.season_year_term(2026, 3) == "spring_2026"
	assert pip.season_year_term(2026, 5) == "spring_2026"


def test_season_year_term_summer():
	assert pip.season_year_term(2026, 6) == "summer_2026"
	assert pip.season_year_term(2026, 7) == "summer_2026"
	assert pip.season_year_term(2026, 8) == "summer_2026"


def test_season_year_term_fall():
	assert pip.season_year_term(2026, 9) == "fall_2026"
	assert pip.season_year_term(2026, 11) == "fall_2026"
	assert pip.season_year_term(2026, 12) == "fall_2026"


def test_form_csv_to_image_dir_name():
	# Simple case: replace first hyphen
	assert pip._form_csv_to_image_dir_name("BCHM_Prot_Img_03-Hydrophobic_Interior.csv") == \
		"BCHM_Prot_Img_03_Hydrophobic_Interior"
	# Retain internal hyphens
	assert pip._form_csv_to_image_dir_name("BCHM_Prot_Img_07-Alpha-Helix.csv") == \
		"BCHM_Prot_Img_07_Alpha-Helix"
	# Replace unsafe characters
	assert pip._form_csv_to_image_dir_name("BCHM_Prot_Img_09-White Background.csv") == \
		"BCHM_Prot_Img_09_White_Background"


def test_form_csv_to_image_dir_name_not_csv():
	with pytest.raises(ValueError) as excinfo:
		pip._form_csv_to_image_dir_name("BCHM_Prot_Img_03-Foo.txt")
	assert ".csv" in str(excinfo.value)


def test_get_term_image_dir_existing_folder(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	term = "spring_2026"
	term_dir = data_root / "semesters" / term
	term_dir.mkdir(parents=True)
	image_dir = term_dir / "BCHM_Prot_Img_03_Foo"
	image_dir.mkdir()
	assert pip.get_term_image_dir(term, 3) == image_dir


def test_get_term_image_dir_from_form_csv(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	term = "spring_2026"
	forms_dir = data_root / "semesters" / term / "forms"
	forms_dir.mkdir(parents=True)
	(forms_dir / "BCHM_Prot_Img_03-Hydrophobic_Interior.csv").write_text("dummy")
	# Should return the path even though the directory doesn't exist yet
	result = pip.get_term_image_dir(term, 3)
	assert result.name == "BCHM_Prot_Img_03_Hydrophobic_Interior"


def test_get_term_image_dir_missing_raises(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	term = "spring_2026"
	(data_root / "semesters" / term).mkdir(parents=True)
	with pytest.raises(FileNotFoundError) as excinfo:
		pip.get_term_image_dir(term, 3)
	assert "Image 03 not found" in str(excinfo.value)


def test_get_term_image_dir_ambiguous_folder_raises(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	term = "spring_2026"
	term_dir = data_root / "semesters" / term
	term_dir.mkdir(parents=True)
	(term_dir / "BCHM_Prot_Img_03_Foo").mkdir()
	(term_dir / "BCHM_Prot_Img_03_Bar").mkdir()
	with pytest.raises(RuntimeError) as excinfo:
		pip.get_term_image_dir(term, 3)
	assert "Multiple folders" in str(excinfo.value)
	assert "BCHM_Prot_Img_03_Foo" in str(excinfo.value)
	assert "BCHM_Prot_Img_03_Bar" in str(excinfo.value)


def test_get_term_image_dir_ambiguous_csv_raises(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	term = "spring_2026"
	forms_dir = data_root / "semesters" / term / "forms"
	forms_dir.mkdir(parents=True)
	(forms_dir / "BCHM_Prot_Img_03-Foo.csv").write_text("dummy")
	(forms_dir / "BCHM_Prot_Img_03-Bar.csv").write_text("dummy")
	with pytest.raises(RuntimeError) as excinfo:
		pip.get_term_image_dir(term, 3)
	assert "Multiple form CSVs" in str(excinfo.value)


def test_get_image_spec_yaml(tmp_path, monkeypatch):
	_install_fake_repo_root(monkeypatch, tmp_path)
	data_root = _make_data_root(tmp_path)
	term = "spring_2026"
	forms_dir = data_root / "semesters" / term / "forms"
	forms_dir.mkdir(parents=True)
	(forms_dir / "BCHM_Prot_Img_03-Foo.csv").write_text("dummy")
	result = pip.get_image_spec_yaml(term, 3)
	assert result.name == "protein_image_03.yml"
	assert "BCHM_Prot_Img_03_Foo" in str(result)
