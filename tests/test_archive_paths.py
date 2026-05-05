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
	input_path = repo_root / "archive" / "2026_1Spring" / "image_bank" / "A" / "x.png"
	result = archive_paths.normalize_hash_path(str(input_path), repo_root)
	assert result == "archive/2026_1Spring/image_bank/A/x.png"


#============================================
def test_normalize_legacy_image_bank_path_rewrites_to_canonical(
	tmp_path: pathlib.Path,
) -> None:
	"""
	Legacy bare ARCHIVE_IMAGES/ paths rewrite to canonical image_bank/.
	"""
	result = archive_paths.normalize_hash_path(
		"ARCHIVE_IMAGES\\BCHM_Prot_Img_04\\x.png",
		tmp_path,
	)
	assert result == "image_bank/BCHM_Prot_Img_04/x.png"


#============================================
def test_normalize_legacy_per_term_path_rewrites_to_canonical(
	tmp_path: pathlib.Path,
) -> None:
	"""
	Legacy per-term archive/<term>/ARCHIVE_IMAGES/ paths rewrite to canonical
	archive/<term>/image_bank/.
	"""
	result = archive_paths.normalize_hash_path(
		"archive/2026_1Spring/ARCHIVE_IMAGES/X/y.png",
		tmp_path,
	)
	assert result == "archive/2026_1Spring/image_bank/X/y.png"


#============================================
def test_normalize_outside_repo_raises(tmp_path: pathlib.Path) -> None:
	"""
	Check absolute paths outside repo are rejected.
	"""
	outside_path = tmp_path.parent / "outside" / "x.png"
	with pytest.raises(ValueError):
		archive_paths.normalize_hash_path(str(outside_path), tmp_path)


#============================================
def test_resolve_external_archive_routes_through_helper(
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""
	Bare image_bank/<rel> resolves through the Synology helper.
	"""
	import protein_image_grader.protein_images_path as protein_images_path
	# Build a fake data root with image_bank/.
	data_root = tmp_path / "Protein_Images"
	data_root.mkdir()
	(data_root / "image_bank").mkdir()
	monkeypatch.setattr(
		archive_paths, "get_repo_root",
		lambda start_path=None: tmp_path,
	)
	result = archive_paths.resolve_archive_path("image_bank/A/x.png", tmp_path)
	expected = (data_root / "image_bank" / "A" / "x.png").resolve()
	assert result.resolve() == expected
	# Also confirm legacy ARCHIVE_IMAGES/... is rewritten and resolved the same way.
	result_legacy = archive_paths.resolve_archive_path(
		"ARCHIVE_IMAGES/A/x.png", tmp_path,
	)
	assert result_legacy.resolve() == expected
	_ = protein_images_path  # keep import side-effect explicit


#============================================
def test_resolve_per_term_path(tmp_path: pathlib.Path) -> None:
	"""
	archive/<term>/... paths resolve under the repo root.
	"""
	result = archive_paths.resolve_archive_path(
		"archive/2026_1Spring/image_bank/A/x.png", tmp_path,
	)
	expected = tmp_path / "archive" / "2026_1Spring" / "image_bank" / "A" / "x.png"
	assert result == expected
