"""Pytest equivalents of the module-level asserts that previously ran at
import time in protein_image_grader/. Moving them out of the library modules
keeps imports side-effect-free per docs/PYTHON_STYLE.md."""

import sys

import git_file_utils

REPO_ROOT = git_file_utils.get_repo_root()
if REPO_ROOT not in sys.path:
	sys.path.insert(0, REPO_ROOT)

import protein_image_grader.grade_protein_image
import protein_image_grader.student_id_protein
import protein_image_grader.timestamp_tools
import protein_image_grader.google_drive_image_utils


def test_print_student_info_returns_none():
	# Was: assert at student_id_protein.py:103
	result = protein_image_grader.student_id_protein.print_student_info(
		{"First Name": "john", "Last Name": "doe", "Student ID": 1234}
	)
	assert result is None


def test_validate_dict_keys_in_tree_accepts_valid_tree():
	# Was: assert at student_id_protein.py:145
	required_keys = ('x', 'y')
	tree = [{'x': 1, 'y': 2}]
	assert protein_image_grader.student_id_protein.validate_dict_keys_in_tree(tree, required_keys)


def test_student_entry_to_normalized_key_lowercases_and_strips():
	# Was: assert at student_id_protein.py:251
	test_student_entry = {'ID': 12, 'Name': 'JoHN  '}
	test_keys = ('ID', 'Name')
	result = protein_image_grader.student_id_protein.student_entry_to_normalized_key(
		test_student_entry, test_keys
	)
	assert result == '12 john'


def test_merge_student_records_overwrites_in_place():
	# Was: assert at student_id_protein.py:331
	test_merge_keys = ('Student ID', 'Name')
	test_student_entry = {'Student ID': '123', 'Name': 'Jane Doe'}
	test_student_id_record = {'Student ID': '123', 'Name': 'John Doe'}
	protein_image_grader.student_id_protein.merge_student_records(
		test_student_entry, test_student_id_record, test_merge_keys
	)
	assert test_student_entry == {'Student ID': '123', 'Name': 'John Doe'}


def test_check_due_date_on_time_submission():
	# Was: assert at timestamp_tools.py:136
	result = protein_image_grader.timestamp_tools.check_due_date(
		"1970/10/25 11:59:59 PM EST",
		{'deadline': {'due date': 'Oct 25, 1970'}},
	)
	assert result == (0.0, 'On-Time', '')


def test_get_file_id_from_google_drive_url_extracts_id():
	# Was: assert at google_drive_image_utils.py:350
	url = (
		"https://drive.google.com/u/2/open?usp=forms_web"
		"&id=1QCHoMnqKvf6gqLI272ZQ4IGBCFupnC6s"
	)
	result = protein_image_grader.google_drive_image_utils.get_file_id_from_google_drive_url(url)
	assert result == "1QCHoMnqKvf6gqLI272ZQ4IGBCFupnC6s"


def test_get_final_score_with_test_entry():
	# Was: assert at grade_protein_image.py:345
	test_entry = {}
	test_config = {'total points': '100', 'assignment name': 'HW1'}
	protein_image_grader.grade_protein_image.get_final_score(test_entry, test_config)
	assert test_entry['Final Score'] == '100.00'
