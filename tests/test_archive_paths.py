# Standard Library
import pathlib

# PIP3 modules
import pytest

# local repo modules
import protein_image_grader.archive_paths as archive_paths


#============================================
def test_make_term_label_from_semester() -> None:
	"""
	Check term label creation.
	"""
	assert archive_paths.make_term_label(2026, "spring") == "2026_1Spring"
	assert archive_paths.make_term_label(2026, "2Summer") == "2026_2Summer"
	assert archive_paths.make_term_label(2026, "fall") == "2026_3Fall"


#============================================
def test_make_assignment_archive_folder() -> None:
	"""
	Check assignment folder naming.
	"""
	result = archive_paths.make_assignment_archive_folder(4, "Protein Image 4: 1OXG")
	assert result == "BCHM_Prot_Img_04_Protein_Image_4_1OXG"


#============================================
def test_normalize_canonical_path(tmp_path: pathlib.Path) -> None:
	"""
	Check canonical archive path normalization.
	"""
	repo_root = tmp_path
	input_path = repo_root / "archive" / "2026_1Spring" / "ARCHIVE_IMAGES" / "A" / "x.png"
	result = archive_paths.normalize_hash_path(str(input_path), repo_root)
	assert result == "archive/2026_1Spring/ARCHIVE_IMAGES/A/x.png"


#============================================
def test_normalize_legacy_archive_images_path(tmp_path: pathlib.Path) -> None:
	"""
	Check legacy ARCHIVE_IMAGES paths normalize to legacy_import.
	"""
	result = archive_paths.normalize_hash_path(
		"ARCHIVE_IMAGES\\BCHM_Prot_Img_04\\x.png",
		tmp_path,
	)
	assert result == "archive/legacy_import/ARCHIVE_IMAGES/BCHM_Prot_Img_04/x.png"


#============================================
def test_normalize_outside_repo_raises(tmp_path: pathlib.Path) -> None:
	"""
	Check absolute paths outside repo are rejected.
	"""
	outside_path = tmp_path.parent / "outside" / "x.png"
	with pytest.raises(ValueError):
		archive_paths.normalize_hash_path(str(outside_path), tmp_path)


#============================================
def test_resolve_legacy_symlink_path(tmp_path: pathlib.Path) -> None:
	"""
	Check legacy paths resolve through repo-root ARCHIVE_IMAGES when present.
	"""
	legacy_file = tmp_path / "ARCHIVE_IMAGES" / "A" / "x.png"
	legacy_file.parent.mkdir(parents=True)
	legacy_file.write_bytes(b"image")
	result = archive_paths.resolve_archive_path("ARCHIVE_IMAGES/A/x.png", tmp_path)
	assert result == legacy_file


#============================================
def test_resolve_legacy_fallback_path(tmp_path: pathlib.Path) -> None:
	"""
	Check legacy paths fall back to archive/legacy_import.
	"""
	result = archive_paths.resolve_archive_path("ARCHIVE_IMAGES/A/x.png", tmp_path)
	expected = tmp_path / "archive" / "legacy_import" / "ARCHIVE_IMAGES" / "A" / "x.png"
	assert result == expected
