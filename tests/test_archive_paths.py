# Standard Library
import pathlib

# PIP3 modules
import pytest

# local repo modules
import protein_image_grader.archive_paths as archive_paths




#============================================
def test_normalize_canonical_path_already_relative(tmp_path: pathlib.Path) -> None:
	"""
	Already-relative canonical path passes through.
	"""
	result = archive_paths.normalize_hash_path(
		"image_bank/spring_2026/BCHM_Prot_Img_01_Foo/raw/x.png",
		tmp_path,
	)
	assert result == "image_bank/spring_2026/BCHM_Prot_Img_01_Foo/raw/x.png"


#============================================
def test_normalize_absolute_nas_path(
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""
	An absolute path under Protein_Images/image_bank/ is stripped to the
	canonical image_bank/<term>/<image_dir>/{raw,trim}/<file> form.
	"""
	data_root = tmp_path / "Protein_Images"
	(data_root / "image_bank").mkdir(parents=True)
	monkeypatch.setattr(
		archive_paths, "get_repo_root",
		lambda start_path=None: tmp_path,
	)
	abs_path = (
		data_root / "image_bank" / "spring_2026"
		/ "BCHM_Prot_Img_01_Foo" / "raw" / "x.png"
	)
	result = archive_paths.normalize_hash_path(str(abs_path), tmp_path)
	assert result == "image_bank/spring_2026/BCHM_Prot_Img_01_Foo/raw/x.png"


#============================================
def test_normalize_absolute_path_outside_image_bank(
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""
	An absolute path NOT under image_bank/ raises ValueError.
	"""
	data_root = tmp_path / "Protein_Images"
	(data_root / "image_bank").mkdir(parents=True)
	monkeypatch.setattr(
		archive_paths, "get_repo_root",
		lambda start_path=None: tmp_path,
	)
	with pytest.raises(ValueError):
		archive_paths.normalize_hash_path("/etc/passwd", tmp_path)


#============================================
def test_normalize_legacy_flat_roots(tmp_path: pathlib.Path) -> None:
	"""
	Legacy MIXED/ and PDB_IMAGES/ flat roots are accepted as canonical paths.
	"""
	for root in archive_paths.LEGACY_FLAT_ROOTS:
		rel = f"image_bank/{root}/some_file.png"
		assert archive_paths.normalize_hash_path(rel, tmp_path) == rel


#============================================
def test_normalize_absolute_legacy_flat_root(
	tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
	"""
	Absolute paths under MIXED/ and PDB_IMAGES/ strip to the canonical
	image_bank/<root>/<file> form.
	"""
	data_root = tmp_path / "Protein_Images"
	(data_root / "image_bank").mkdir(parents=True)
	monkeypatch.setattr(
		archive_paths, "get_repo_root",
		lambda start_path=None: tmp_path,
	)
	abs_path = data_root / "image_bank" / "MIXED" / "1bl8-abdul.png"
	result = archive_paths.normalize_hash_path(str(abs_path), tmp_path)
	assert result == "image_bank/MIXED/1bl8-abdul.png"


#============================================
def test_normalize_rejects_archive_legacy(tmp_path: pathlib.Path) -> None:
	"""
	Legacy archive/<term>/image_bank/ paths are rejected.
	"""
	with pytest.raises(ValueError):
		archive_paths.normalize_hash_path(
			"archive/2026_1Spring/image_bank/A/x.png",
			tmp_path,
		)


#============================================
def test_normalize_rejects_archive_images_literal(tmp_path: pathlib.Path) -> None:
	"""
	Legacy ARCHIVE_IMAGES/ paths are rejected.
	"""
	with pytest.raises(ValueError):
		archive_paths.normalize_hash_path(
			"ARCHIVE_IMAGES/BCHM_Prot_Img_04/x.png",
			tmp_path,
		)


#============================================
def test_normalize_rejects_non_canonical_format(tmp_path: pathlib.Path) -> None:
	"""
	Non-canonical formats are rejected (anything not starting with image_bank/).
	"""
	with pytest.raises(ValueError):
		archive_paths.normalize_hash_path("some_other_path/x.png", tmp_path)


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
	_ = protein_images_path  # keep import side-effect explicit


#============================================
def test_resolve_rejects_legacy_archive_images(tmp_path: pathlib.Path) -> None:
	"""
	Legacy ARCHIVE_IMAGES/ paths are rejected in resolution.
	"""
	with pytest.raises(ValueError):
		archive_paths.resolve_archive_path("ARCHIVE_IMAGES/A/x.png", tmp_path)


#============================================
def test_resolve_rejects_archive_per_term(tmp_path: pathlib.Path) -> None:
	"""
	Legacy archive/<term>/... paths are rejected in resolution.
	"""
	with pytest.raises(ValueError):
		archive_paths.resolve_archive_path(
			"archive/2026_1Spring/image_bank/A/x.png", tmp_path,
		)
