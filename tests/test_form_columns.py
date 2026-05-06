"""
Tests for protein_image_grader.form_columns.resolve_meta_columns.
"""

import textwrap

import pytest

import protein_image_grader.form_columns as form_columns
import protein_image_grader.file_io_protein as file_io_protein


# Complete baseline header that resolves all five canonical keys
# unambiguously. Mutate one column per test to exercise variants.
BASELINE_HEADER = [
	"Timestamp",
	"Username",
	"Enter your first name",
	"Enter your last name",
	"Enter your RUID",
	"Upload Protein Image with White Background",
]


def _baseline():
	return list(BASELINE_HEADER)


def test_baseline_resolves_each_canonical_key_to_its_index():
	resolved = form_columns.resolve_meta_columns(_baseline())
	# Per-key index assertions; not a full-dict equality check, so adding
	# a sixth canonical key in the future does not break this test.
	assert resolved["timestamp"] == 0
	assert resolved["Username"] == 1
	assert resolved["First Name"] == 2
	assert resolved["Last Name"] == 3
	assert resolved["Student ID"] == 4


def test_email_address_alias_resolves_username():
	header = _baseline()
	header[1] = "Email Address"
	resolved = form_columns.resolve_meta_columns(header)
	assert resolved["Username"] == 1


def test_student_id_literal_resolves_student_id():
	header = _baseline()
	header[4] = "Student ID"
	resolved = form_columns.resolve_meta_columns(header)
	assert resolved["Student ID"] == 4


def test_first_name_literal_resolves_first_name():
	header = _baseline()
	header[2] = "First Name"
	resolved = form_columns.resolve_meta_columns(header)
	assert resolved["First Name"] == 2


def test_last_name_literal_resolves_last_name():
	header = _baseline()
	header[3] = "Last Name"
	resolved = form_columns.resolve_meta_columns(header)
	assert resolved["Last Name"] == 3


def test_case_and_whitespace_insensitive():
	header = _baseline()
	header[1] = "  USERNAME  "
	resolved = form_columns.resolve_meta_columns(header)
	assert resolved["Username"] == 1


def test_ambiguous_username_columns_raise():
	header = _baseline()
	# Both Username and Email Address present in the same form.
	header.append("Email Address")
	with pytest.raises(ValueError) as excinfo:
		form_columns.resolve_meta_columns(header)
	message = str(excinfo.value)
	assert "Username" in message
	assert "Email Address" in message


def test_ambiguous_student_id_columns_raise():
	header = _baseline()
	# Both "Enter your RUID" (baseline) and "Student ID" present.
	header.append("Student ID")
	with pytest.raises(ValueError) as excinfo:
		form_columns.resolve_meta_columns(header)
	message = str(excinfo.value)
	# Both matched headers must appear in the message so the operator
	# can see what conflicted, not just the canonical key.
	assert "Student ID" in message
	assert "Enter your RUID" in message


def test_missing_only_username_lists_only_username():
	header = _baseline()
	# Replace Username with a column that matches no alias.
	header[1] = "Mascot color"
	with pytest.raises(ValueError) as excinfo:
		form_columns.resolve_meta_columns(header)
	message = str(excinfo.value)
	assert "Username" in message
	# The other four canonical keys are present, so they must NOT be listed.
	for present_key in ("First Name", "Last Name", "Student ID", "timestamp"):
		assert present_key not in message


def test_missing_multiple_lists_all_missing():
	header = ["Mascot color", "Favorite snack"]
	with pytest.raises(ValueError) as excinfo:
		form_columns.resolve_meta_columns(header)
	message = str(excinfo.value)
	for canonical_key in form_columns.STANDARD_META_COLUMNS.keys():
		assert canonical_key in message


def test_required_subset_does_not_raise_on_missing_unrequired_keys():
	# Header that is missing Student ID but has the rest. With required
	# narrowed to the keys the downloader needs, this should NOT raise.
	header = _baseline()
	header[4] = "Mascot color"
	resolved = form_columns.resolve_meta_columns(
		header, required={"Username", "First Name", "Last Name"},
	)
	assert "Student ID" not in resolved
	assert resolved["Username"] == 1
	assert resolved["First Name"] == 2
	assert resolved["Last Name"] == 3


def test_required_empty_set_skips_missing_check():
	header = ["Mascot color"]
	resolved = form_columns.resolve_meta_columns(header, required=set())
	# Nothing matched, but no error either; caller decides what to do.
	assert resolved == {}


def test_read_student_csv_data_ignores_legacy_email_key(tmp_path, capsys):
	"""
	Original-bug regression: a spec YAML carrying the legacy `email: 2`
	key must not produce student_entry["email"]. The Username column is
	now resolved from the CSV header, so student_entry["Username"] is
	the only key present.
	"""
	csv_path = tmp_path / "form.csv"
	csv_text = textwrap.dedent('''\
		"Timestamp","Username","Enter your first name","Enter your last name","Enter your RUID","Upload"
		"2026/01/01 09:00:00","alice@example.org","Alice","Smith","900000001","https://example.org/img"
	''')
	csv_path.write_text(csv_text)

	# Legacy meta keys (First Name, Last Name, Student ID, email,
	# timestamp) plus the still-supported per-image fields. The legacy
	# `email` key is wrong: it points at column 2 (first name in our
	# CSV), so if the patch ever regresses by reading email from YAML,
	# student_entry["Username"] would equal "Alice" instead of the
	# email address.
	config = {
		"meta columns": {
			"First Name": 3,
			"Last Name": 4,
			"Student ID": 5,
			"email": 2,
			"timestamp": 1,
			"image url": 6,
		},
		"csv_questions": [],
		"image number": 1,
	}

	students = file_io_protein.read_student_csv_data(str(csv_path), config)

	assert len(students) == 1
	row = students[0]
	# Canonical keys present, populated from the CSV header (not from
	# the YAML legacy indices).
	assert row["Username"] == "alice@example.org"
	assert row["First Name"] == "Alice"
	assert row["Last Name"] == "Smith"
	assert row["Student ID"] == "900000001"
	assert row["timestamp"] == "2026/01/01 09:00:00"
	# Per-image YAML field still honored.
	assert row["image url"] == "https://example.org/img"
	# Legacy YAML key must NOT have leaked through as a student_entry field.
	assert "email" not in row
	# A single warning line was emitted, anchored to the warning prefix.
	captured = capsys.readouterr()
	assert "legacy standard meta column keys" in captured.out
