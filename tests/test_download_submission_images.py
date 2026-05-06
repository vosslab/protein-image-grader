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
		output_dir=None, maxstudents=-1, trim=False, rotate=False,
		archive_anyway=False, profiles_html=None,
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


def test_get_image_html_tag_trim_dual_write(monkeypatch, tmp_path):
	"""
	With args.trim=True, get_image_html_tag must:
	  - save raw to <raw_dir>/<filename>
	  - save trim to <image_dir>/trim/<basename>-trim.jpg
	  - archive both to <archive_root>/raw/ and <archive_root>/trim/
	  - call update_image_hashes once per file (raw + trim)
	"""
	import protein_image_grader.google_drive_image_utils as gdiu

	_install_fake_repo_root(monkeypatch, tmp_path)
	image_bank_dir = tmp_path / pip.PROTEIN_IMAGES_NAME / "image_bank"
	image_bank_dir.mkdir(parents=True)
	monkeypatch.setattr(pip, "get_image_bank_dir", lambda: image_bank_dir)

	image_dir = tmp_path / "BCHM_Prot_Img_01_Topic"
	raw_dir = image_dir / "raw"
	raw_dir.mkdir(parents=True)
	archive_root = image_bank_dir / "spring_2026" / "BCHM_Prot_Img_01_Topic"

	# Mock download: return a non-None marker so the path proceeds.
	def fake_try_download(_file_id):
		import io
		return io.BytesIO(b"fake"), "myimage.png"
	monkeypatch.setattr(dsi, "try_download_image", fake_try_download)

	# download_and_save_image normally opens via PIL; bypass and just write bytes.
	def fake_save(_image_data, filepath):
		import os as _os
		if _os.path.isfile(filepath):
			return False
		with open(filepath, "wb") as fh:
			fh.write(b"fake-png-bytes")
		return True
	monkeypatch.setattr(dsi, "download_and_save_image", fake_save)

	# Bypass google_drive_image_utils.get_file_id_from_google_drive_url by
	# returning a fake id; the URL contents don't matter once try_download is mocked.
	monkeypatch.setattr(
		gdiu, "get_file_id_from_google_drive_url",
		lambda _url: "fake-id"
	)

	# trim_and_save_image normally needs PIL; stub it to write a fake jpg next to
	# the trim_dir caller passes in.
	def fake_trim(raw_path, trim_dir, _rotate):
		import os as _os
		basename = _os.path.splitext(_os.path.basename(raw_path))[0]
		trim_path = _os.path.join(trim_dir, f"{basename}-trim.jpg")
		with open(trim_path, "wb") as fh:
			fh.write(b"fake-trim-bytes")
		return trim_path
	monkeypatch.setattr(dsi, "trim_and_save_image", fake_trim)

	# Hash data is content-derived but we just need stable distinct values for
	# raw vs trim so update_image_hashes records two entries.
	def fake_hash(stream):
		data = stream.read()
		return f"md5-{len(data)}", f"phash-{len(data)}"
	monkeypatch.setattr(gdiu, "get_hash_data", fake_hash)

	args = _args(image_number=1, trim=True)
	image_hashes = {"md5": {}, "phash": {}}
	hashes_changed = [False]

	tag = dsi.get_image_html_tag(
		"https://drive.google.com/file/d/fake/view",
		900111222, args, str(image_dir), str(raw_dir),
		str(archive_root), image_hashes, hashes_changed,
	)

	# Raw landed under raw/
	raw_files = list(raw_dir.iterdir())
	assert len(raw_files) == 1
	assert raw_files[0].suffix == ".png"

	# Trim landed under <image_dir>/trim/, NOT next to raw
	trim_dir = image_dir / "trim"
	assert trim_dir.is_dir()
	trim_files = list(trim_dir.iterdir())
	assert len(trim_files) == 1
	assert trim_files[0].name.endswith("-trim.jpg")

	# Both files archived
	assert (archive_root / "raw").is_dir()
	assert (archive_root / "trim").is_dir()
	assert len(list((archive_root / "raw").iterdir())) == 1
	assert len(list((archive_root / "trim").iterdir())) == 1

	# Two distinct hash entries recorded (raw + trim)
	assert len(image_hashes["md5"]) == 2
	assert len(image_hashes["phash"]) == 2
	assert hashes_changed[0] is True

	# HTML tag references both files
	assert "raw/" in tag or "raw" in tag
	assert "-trim.jpg" in tag


def test_process_one_csv_creates_raw_and_archive_dirs(monkeypatch, tmp_path):
	"""
	Test that process_one_csv creates raw/ dir and archive root structure.
	"""
	_install_fake_repo_root(monkeypatch, tmp_path)
	_make_forms(tmp_path, "spring_2026", [1])

	# Create a minimal CSV with mock image URL (won't actually download).
	csv_path = (
		tmp_path / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR
		/ "spring_2026" / pip.FORMS_SUBDIR / "BCHM_Prot_Img_01-Topic.csv"
	)

	# Write CSV header and empty row to avoid actual downloads.
	csv_path.write_text(
		"First Name,Last Name,Image\nJohn,Doe,\n",
		encoding="utf-8"
	)

	# Verify raw_dir is created
	image_dir = tmp_path / pip.PROTEIN_IMAGES_NAME / pip.SEMESTERS_SUBDIR / \
		"spring_2026" / "BCHM_Prot_Img_01_Topic"
	raw_dir = image_dir / "raw"

	# Mock get_image_bank_dir to return a test path
	image_bank_dir = tmp_path / pip.PROTEIN_IMAGES_NAME / "image_bank"
	monkeypatch.setattr(
		pip, "get_image_bank_dir",
		lambda: image_bank_dir
	)

	# Mock generate_html to just verify it gets called with correct params
	called_with = []
	def mock_generate_html(csvfile, header, data_tree, args, img_dir, raw, archive_root, html, hashes, changed):
		called_with.append({
			"image_dir": img_dir,
			"raw_dir": raw,
			"archive_root": archive_root,
		})

	monkeypatch.setattr(dsi, "generate_html", mock_generate_html)

	# Run process_one_csv
	args = _args()
	image_hashes = {"md5": {}, "phash": {}}
	hashes_changed = [False]

	dsi.process_one_csv(str(csv_path), args, image_hashes, hashes_changed, False)

	# Verify raw_dir was created
	assert raw_dir.is_dir(), f"raw_dir not created: {raw_dir}"

	# Verify archive_root structure is correct
	assert len(called_with) == 1
	call = called_with[0]
	assert call["raw_dir"] == str(raw_dir)
	# Archive root should be under image_bank/spring_2026/BCHM_Prot_Img_01_Topic
	assert call["archive_root"] is not None, "archive_root should not be None"
	assert "image_bank" in call["archive_root"]
	assert "spring_2026" in call["archive_root"]
	assert "BCHM_Prot_Img_01_Topic" in call["archive_root"]
