"""
Tests for grade_protein_image.seed_or_reseed_spec_yaml.

Covers the three terminal branches: first-time seed, mtime reseed, and
no-action kept.
"""

import os
import time

import pytest

import protein_image_grader.grade_protein_image as gpi


def _write(path, text):
	path.write_text(text, encoding="utf-8")
	return path


def test_first_time_seed_copies_template(tmp_path):
	template = _write(tmp_path / "template.yml", "image number: 1\n")
	dst = tmp_path / "per_image" / "protein_image_01.yml"
	dst.parent.mkdir()

	result = gpi.seed_or_reseed_spec_yaml(str(template), str(dst))

	assert result == "seeded"
	assert dst.read_text() == "image number: 1\n"


def test_mtime_reseed_overwrites_when_template_is_newer(tmp_path):
	template = _write(tmp_path / "template.yml", "new template body\n")
	dst = _write(tmp_path / "per_image.yml", "old per-image body\n")

	# Make the per-image copy older than the template.
	old_time = time.time() - 600.0
	new_time = time.time()
	os.utime(str(dst), (old_time, old_time))
	os.utime(str(template), (new_time, new_time))

	result = gpi.seed_or_reseed_spec_yaml(str(template), str(dst))

	assert result == "reseeded"
	assert dst.read_text() == "new template body\n"


def test_no_action_when_per_image_copy_is_newer(tmp_path):
	template = _write(tmp_path / "template.yml", "template body\n")
	dst = _write(tmp_path / "per_image.yml", "operator edits\n")

	# Per-image copy is newer than the template; template should not overwrite.
	old_time = time.time() - 600.0
	new_time = time.time()
	os.utime(str(template), (old_time, old_time))
	os.utime(str(dst), (new_time, new_time))

	result = gpi.seed_or_reseed_spec_yaml(str(template), str(dst))

	assert result == "kept"
	assert dst.read_text() == "operator edits\n"


def test_missing_template_and_missing_dst_raises(tmp_path):
	# Neither path exists.
	template = tmp_path / "template.yml"
	dst = tmp_path / "per_image.yml"

	with pytest.raises(ValueError) as excinfo:
		gpi.seed_or_reseed_spec_yaml(str(template), str(dst))
	message = str(excinfo.value)
	assert "Spec YAML not found" in message
