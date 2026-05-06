# Standard Library
import os
import pathlib

# local repo modules
import protein_image_grader.duplicate_processing as duplicate_processing


#============================================
def stub_os_system(command: str) -> int:
	"""
	Stub for os.system that records nothing and returns success.
	"""
	return 0


#============================================
def stub_input_validation(message: str, options, color=None) -> str:
	"""
	Stub for student_id_protein.get_input_validation that always declines.
	"""
	return "n"


#============================================
def test_missing_archive_file_warns_and_continues(
	tmp_path: pathlib.Path,
	monkeypatch,
	capsys,
) -> None:
	"""
	Check missing archive files warn without stopping duplicate review.
	"""
	current_file = tmp_path / "current.png"
	current_file.write_bytes(b"image")
	student_tree = [
		{
			"Perceptual Hash": "0" * 64,
			"128-bit MD5 Hash": "a",
			"Output Filename": str(current_file),
			"Exact Match": False,
			"Similar Match": False,
			"Warnings": [],
		}
	]
	image_hashes = {
		"md5": {},
		"phash": {"0" * 63 + "1": "image_bank/spring_2026/BCHM_Prot_Img_01_Foo/raw/missing.png"},
	}
	local_image_hashes = duplicate_processing.fill_local_image_hashes(student_tree)

	monkeypatch.setattr(os, "system", stub_os_system)
	monkeypatch.setattr(
		duplicate_processing.student_id_protein,
		"get_input_validation",
		stub_input_validation,
	)

	duplicate_processing.find_similar_duplicates(
		student_tree,
		image_hashes,
		local_image_hashes,
	)

	output = capsys.readouterr().out
	# The output may contain the path on a different line
	assert "image_bank/spring_2026/BCHM_Prot_Img_01_Foo/raw/missing.png" in output
	assert "WARNING" in output or "file not found" in output
