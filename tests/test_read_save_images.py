"""
Tests for the cache-glob behavior in read_save_images.get_image_data.

Locks in the contract that the grader's cache prefix matches the
downloader's saved-filename shape, so a previously-downloaded file is
recognized and the Google Drive download path is NOT taken.

See docs/PYTEST_STYLE.md: assertions check branch behavior (cache hit vs
miss), not log line counts or hardcoded download tallies.
"""

# Standard Library
import io
import os
import pathlib
import argparse

# local repo modules
import protein_image_grader.read_save_images as read_save_images
import protein_image_grader.image_filename as image_filename
import protein_image_grader.download_submission_images as dsi


def _student_entry(ruid: int = 900000002,
		first: str = "Alice", last: str = "Smith") -> dict:
	# Minimal student_entry shape that get_image_data reads.
	return {
		"Student ID": ruid,
		"First Name": first,
		"Last Name": last,
		"image url": "https://drive.google.com/file/d/FAKE_FILE_ID/view",
	}


def _params(image_raw_dir: pathlib.Path, image_number: int = 1) -> dict:
	return {
		"image_raw_dir": str(image_raw_dir),
		"image_number": image_number,
	}


def test_get_image_data_cache_hit_does_not_download(tmp_path, monkeypatch):
	# Pre-seed a file with the canonical downloader shape.
	image_raw_dir = tmp_path / "raw"
	image_raw_dir.mkdir()
	saved_name = image_filename.build_raw_image_filename(
		ruid=900000002, image_number=1, original_filename="MyImage.PNG"
	)
	saved_path = image_raw_dir / saved_name
	saved_path.write_bytes(b"\x89PNG\r\n\x1a\n")  # short stub PNG header

	# Fail loudly if the download path is taken; this stub raising
	# AssertionError is the real cache-hit contract enforcement.
	def _no_download(file_id):
		raise AssertionError("download_image must not be called on cache hit")
	monkeypatch.setattr(
		read_save_images.google_drive_image_utils, "download_image", _no_download
	)

	entry = _student_entry()
	params = _params(image_raw_dir)

	image_data, original_filename, output_filename = read_save_images.get_image_data(
		entry, params
	)

	assert output_filename == str(saved_path)
	image_data.close()


def test_get_image_data_cache_miss_uses_canonical_shape(tmp_path, monkeypatch):
	# Empty image_raw_dir: glob misses, downloader stub returns bytes.
	image_raw_dir = tmp_path / "raw"
	image_raw_dir.mkdir()

	def _fake_file_id(url):
		return "FAKE_FILE_ID"

	# Closure counter: the cache-miss branch must call download_image exactly
	# once. Tracking via a local list avoids order-sensitive module state.
	calls = []
	def _fake_download(file_id):
		calls.append(file_id)
		return io.BytesIO(b"\x89PNG\r\n\x1a\n"), "MyImage.PNG"

	monkeypatch.setattr(
		read_save_images.google_drive_image_utils,
		"get_file_id_from_google_drive_url", _fake_file_id,
	)
	monkeypatch.setattr(
		read_save_images.google_drive_image_utils, "download_image", _fake_download
	)

	entry = _student_entry()
	params = _params(image_raw_dir)

	_image_data, _original, output_filename = read_save_images.get_image_data(
		entry, params
	)

	# The grader-built name must match what the downloader would have built
	# from the same inputs.
	expected = image_filename.build_raw_image_filename(
		ruid=900000002, image_number=1, original_filename="MyImage.PNG"
	)
	assert os.path.basename(output_filename) == expected
	assert len(calls) == 1


def test_downloader_and_grader_agree_on_filename_shape():
	# Round-trip: downloader.format_filename and the grader's prefix builder
	# must agree, so a file the downloader saves is found by the grader's
	# cache glob.
	args = argparse.Namespace(image_number=3)
	saved = dsi.format_filename("photo of cell.PNG", ruid=900123456, args=args)
	prefix = image_filename.build_raw_image_prefix(
		ruid=900123456, image_number=3
	)
	assert saved.startswith(prefix)
