"""
Unit tests for protein_image_grader.csv_compare.

Covers hash_csv (byte-level digest) and is_strict_form_superset
(keyed superset over (Student ID, timestamp)).
"""

# Standard Library
import pathlib

# local repo modules
import protein_image_grader.csv_compare as csv_compare


HEADER = "Timestamp,Email Address,First Name,Last Name,Student ID\n"


def _row(student_id: str, ts: str, first: str = "Pat") -> str:
	return f"{ts},pat@x,{first},Roe,{student_id}\n"


def _write(path: pathlib.Path, rows: list) -> pathlib.Path:
	path.write_text(HEADER + "".join(rows), encoding="ascii")
	return path


def test_hash_csv_matches_for_identical_files(tmp_path):
	a = _write(tmp_path / "a.csv", [_row("900000001", "2026/04/16 1:00:00 PM EST")])
	b = _write(tmp_path / "b.csv", [_row("900000001", "2026/04/16 1:00:00 PM EST")])
	assert csv_compare.hash_csv(a) == csv_compare.hash_csv(b)


def test_hash_csv_differs_when_bytes_differ(tmp_path):
	a = _write(tmp_path / "a.csv", [_row("900000001", "2026/04/16 1:00:00 PM EST")])
	b = _write(tmp_path / "b.csv", [_row("900000002", "2026/04/16 1:00:00 PM EST")])
	assert csv_compare.hash_csv(a) != csv_compare.hash_csv(b)


def test_strict_form_superset_identical(tmp_path):
	body = [_row("900000001", "2026/04/16 1:00:00 PM EST")]
	base = _write(tmp_path / "base.csv", body)
	cand = _write(tmp_path / "cand.csv", body)
	ok, reason, added = csv_compare.is_strict_form_superset(base, cand)
	assert ok is True
	assert added == 0
	assert reason == "+0 rows"


def test_strict_form_superset_appended_rows(tmp_path):
	r1 = _row("900000001", "2026/04/16 1:00:00 PM EST")
	r2 = _row("900000002", "2026/04/16 1:05:00 PM EST")
	r3 = _row("900000003", "2026/04/16 1:10:00 PM EST")
	base = _write(tmp_path / "base.csv", [r1])
	cand = _write(tmp_path / "cand.csv", [r1, r2, r3])
	ok, reason, added = csv_compare.is_strict_form_superset(base, cand)
	assert ok is True
	assert added == 2
	assert reason == "+2 rows"


def test_strict_form_superset_interleaved_rows(tmp_path):
	# Same shared keys, candidate adds 2 new keys, but in interleaved
	# order to prove the comparator does not depend on row order.
	r1 = _row("900000001", "2026/04/16 1:00:00 PM EST")
	r2 = _row("900000002", "2026/04/16 1:05:00 PM EST")
	new1 = _row("900000010", "2026/04/16 1:11:00 PM EST")
	new2 = _row("900000011", "2026/04/16 1:12:00 PM EST")
	base = _write(tmp_path / "base.csv", [r1, r2])
	cand = _write(tmp_path / "cand.csv", [new1, r1, new2, r2])
	ok, reason, added = csv_compare.is_strict_form_superset(base, cand)
	assert ok is True
	assert added == 2


def test_strict_form_superset_missing_row(tmp_path):
	r1 = _row("900000001", "2026/04/16 1:00:00 PM EST")
	r2 = _row("900000002", "2026/04/16 1:05:00 PM EST")
	base = _write(tmp_path / "base.csv", [r1, r2])
	cand = _write(tmp_path / "cand.csv", [r1])
	ok, reason, added = csv_compare.is_strict_form_superset(base, cand)
	assert ok is False
	assert "missing row: 900000002" in reason
	assert added == 0


def test_strict_form_superset_changed_row(tmp_path):
	r1_base = _row("900000001", "2026/04/16 1:00:00 PM EST", first="Pat")
	r1_cand = _row("900000001", "2026/04/16 1:00:00 PM EST", first="Patty")
	base = _write(tmp_path / "base.csv", [r1_base])
	cand = _write(tmp_path / "cand.csv", [r1_cand])
	ok, reason, added = csv_compare.is_strict_form_superset(base, cand)
	assert ok is False
	assert "changed row: 900000001" in reason


def test_strict_form_superset_duplicate_in_candidate(tmp_path):
	r1 = _row("900000001", "2026/04/16 1:00:00 PM EST")
	base = _write(tmp_path / "base.csv", [r1])
	cand = _write(tmp_path / "cand.csv", [r1, r1])
	ok, reason, added = csv_compare.is_strict_form_superset(base, cand)
	assert ok is False
	assert "duplicate key in candidate: 900000001" in reason


def test_strict_form_superset_duplicate_in_base(tmp_path):
	# Symmetrical to the duplicate-in-candidate case: when the
	# canonical (base) CSV has two rows with the same
	# (Student ID, timestamp) key, the comparator must surface
	# "duplicate key in base: ..." before checking candidate keys.
	r1 = _row("900000001", "2026/04/16 1:00:00 PM EST")
	base = _write(tmp_path / "base.csv", [r1, r1])
	cand = _write(tmp_path / "cand.csv", [r1])
	ok, reason, added = csv_compare.is_strict_form_superset(base, cand)
	assert ok is False
	assert "duplicate key in base: 900000001" in reason


def test_strict_form_superset_header_mismatch(tmp_path):
	body = [_row("900000001", "2026/04/16 1:00:00 PM EST")]
	base = tmp_path / "base.csv"
	cand = tmp_path / "cand.csv"
	base.write_text(HEADER + "".join(body), encoding="ascii")
	cand.write_text(
		"Timestamp,Email Address,First Name,Last Name,Student ID,Extra\n"
		+ "".join(r.rstrip("\n") + ",x\n" for r in body),
		encoding="ascii",
	)
	ok, reason, added = csv_compare.is_strict_form_superset(base, cand)
	assert ok is False
	assert reason == "header mismatch"
	assert added == 0
