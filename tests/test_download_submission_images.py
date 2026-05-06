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


def _build_test_matcher(mapping=None):
	"""
	Build a real RosterMatcher with one roster row per mapping value so
	a typed Form RUID in `mapping.keys()` resolves to the roster RUID
	in `mapping.values()` via the username path. Anything else falls
	through to UnresolvedStudent.

	Each mapped roster row uses a unique synthetic name and username
	derived from the typed value so the matcher's exact-username path
	resolves it cleanly without fuzzy ambiguity.
	"""
	import protein_image_grader.roster_matching as rm
	mapping = mapping or {}
	roster = {}
	for typed, roster_ruid in mapping.items():
		first_n = rm.normalize_name_text(f"User{typed}")
		last_n = rm.normalize_name_text(f"Last{typed}")
		username = rm.normalize_username(f"user{typed}")
		roster[int(roster_ruid)] = {
			"student_id": int(roster_ruid),
			"first_name": first_n, "last_name": last_n,
			"username": username, "alias": "",
			"full_name": (first_n + " " + last_n).strip(),
		}
	return rm.RosterMatcher(roster=roster, interactive=False)


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
	def mock_generate_html(csvfile, header, data_tree, args, img_dir, raw,
			archive_root, html, hashes, changed, matcher, assigned_ruids):
		called_with.append({
			"image_dir": img_dir,
			"raw_dir": raw,
			"archive_root": archive_root,
			"matcher": matcher,
			"assigned_ruids": assigned_ruids,
		})

	monkeypatch.setattr(dsi, "generate_html", mock_generate_html)

	# Run process_one_csv
	args = _args()
	image_hashes = {"md5": {}, "phash": {}}
	hashes_changed = [False]

	matcher = _build_test_matcher()
	assigned: set = set()
	dsi.process_one_csv(str(csv_path), args, image_hashes, hashes_changed,
		False, matcher, assigned)

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
	# Matcher and assigned-ruids set were threaded through unchanged.
	assert call["matcher"] is matcher
	assert call["assigned_ruids"] is assigned


def _stub_image_io(monkeypatch, tmp_path):
	# Shared download/trim/hash stubs used by the resolver-flow tests.
	import io
	import protein_image_grader.google_drive_image_utils as gdiu

	def fake_try_download(_file_id):
		return io.BytesIO(b"fake"), "myimage.png"

	def fake_save(_image_data, filepath):
		import os as _os
		if _os.path.isfile(filepath):
			return False
		with open(filepath, "wb") as fh:
			fh.write(b"fake-png-bytes")
		return True

	def fake_trim(raw_path, trim_dir, _rotate):
		import os as _os
		basename = _os.path.splitext(_os.path.basename(raw_path))[0]
		trim_path = _os.path.join(trim_dir, f"{basename}-trim.jpg")
		with open(trim_path, "wb") as fh:
			fh.write(b"fake-trim-bytes")
		return trim_path

	def fake_hash(stream):
		data = stream.read()
		return f"md5-{len(data)}", f"phash-{len(data)}"

	monkeypatch.setattr(dsi, "try_download_image", fake_try_download)
	monkeypatch.setattr(dsi, "download_and_save_image", fake_save)
	monkeypatch.setattr(dsi, "trim_and_save_image", fake_trim)
	monkeypatch.setattr(gdiu, "get_file_id_from_google_drive_url",
		lambda _url: "fake-id")
	monkeypatch.setattr(gdiu, "get_hash_data", fake_hash)


def test_generate_html_uses_roster_ruid(monkeypatch, tmp_path):
	"""
	When the form CSV typed RUID differs from the Roster RUID, the saved
	filename in raw/, trim/, and both archive mirrors must use the
	Roster RUID, not the typed one.
	"""
	_install_fake_repo_root(monkeypatch, tmp_path)
	_stub_image_io(monkeypatch, tmp_path)
	# update_image_hashes calls archive_paths.normalize_hash_path which
	# resolves image_bank/. Stub it so it accepts our tmp archive root.
	image_bank_dir = tmp_path / pip.PROTEIN_IMAGES_NAME / "image_bank"
	image_bank_dir.mkdir(parents=True)
	monkeypatch.setattr(pip, "get_image_bank_dir", lambda: image_bank_dir)

	image_dir = tmp_path / "BCHM_Prot_Img_01_Topic"
	raw_dir = image_dir / "raw"
	raw_dir.mkdir(parents=True)
	# Place archive root inside image_bank/ so normalize_hash_path resolves.
	archive_root = image_bank_dir / "spring_2026" / "BCHM_Prot_Img_01_Topic"

	# Form CSV: typed RUID 900000001 is wrong; roster has Alice Smith
	# under 900000002. Real matcher resolves via exact name match.
	csv_path = tmp_path / "BCHM_Prot_Img_01-Topic.csv"
	csv_path.write_text(
		"Username,Enter your first name,Enter your last name,"
		"Enter your RUID,Image\n"
		"asmith,Alice,Smith,900000001,https://drive/x\n",
		encoding="utf-8",
	)
	header, data_tree = dsi.read_csv(str(csv_path), -1)

	import protein_image_grader.roster_matching as rm
	first_n = rm.normalize_name_text("Alice")
	last_n = rm.normalize_name_text("Smith")
	roster = {900000002: {
		"student_id": 900000002,
		"first_name": first_n, "last_name": last_n,
		"username": rm.normalize_username("asmith"), "alias": "",
		"full_name": (first_n + " " + last_n).strip(),
	}}
	matcher = rm.RosterMatcher(roster=roster, interactive=False)
	assigned: set = set()
	args = _args(image_number=1, trim=True)
	image_hashes = {"md5": {}, "phash": {}}
	hashes_changed = [False]

	dsi.generate_html(
		str(csv_path), header, data_tree, args,
		str(image_dir), str(raw_dir), str(archive_root),
		str(image_dir / "profiles.html"),
		image_hashes, hashes_changed, matcher, assigned,
	)

	# Property assertions, not collection-size: every file under any of
	# the four save locations must carry the Roster RUID prefix and
	# never the Form RUID. Robust to multi-row CSVs.
	def _names(directory):
		return [p.name for p in directory.iterdir()]

	for directory in (raw_dir, image_dir / "trim",
			archive_root / "raw", archive_root / "trim"):
		names = _names(directory)
		assert names, f"no files written to {directory}"
		for name in names:
			assert name.startswith("900000002-protein01-"), name
			assert "900000001" not in name, name

	# Trim files keep the -trim.jpg suffix specifically.
	for name in _names(image_dir / "trim"):
		assert name.endswith("-trim.jpg")


def test_generate_html_quarantines_unresolved_row(monkeypatch, tmp_path):
	"""
	Rows the resolver cannot resolve must not produce any saved image,
	must be logged to <csv_dir>/quarantine.log, and must surface a
	QUARANTINED marker in the HTML page.
	"""
	_install_fake_repo_root(monkeypatch, tmp_path)
	_stub_image_io(monkeypatch, tmp_path)

	image_dir = tmp_path / "BCHM_Prot_Img_01_Topic"
	raw_dir = image_dir / "raw"
	raw_dir.mkdir(parents=True)

	csv_path = tmp_path / "BCHM_Prot_Img_01-Topic.csv"
	csv_path.write_text(
		"Username,Enter your first name,Enter your last name,"
		"Enter your RUID,Image\n"
		"ghost,Ghost,Person,900999999,https://drive/x\n",
		encoding="utf-8",
	)
	header, data_tree = dsi.read_csv(str(csv_path), -1)

	# Empty roster -> every row goes to quarantine.
	import protein_image_grader.roster_matching as rm
	matcher = rm.RosterMatcher(roster={}, interactive=False)
	args = _args(image_number=1, trim=True)
	html_path = image_dir / "profiles.html"

	dsi.generate_html(
		str(csv_path), header, data_tree, args,
		str(image_dir), str(raw_dir), None,
		str(html_path), {"md5": {}, "phash": {}}, [False],
		matcher, set(),
	)

	# No image was saved under the Form RUID (or under any RUID) for
	# the quarantined row. Property assertion: nothing in raw/ carries
	# the typed Form RUID, and no trim/ subdir was created.
	for p in raw_dir.iterdir():
		assert "900999999" not in p.name, p.name
	assert not (image_dir / "trim").exists()

	# Quarantine log was written next to the CSV.
	q_log = csv_path.parent / "quarantine.log"
	assert q_log.is_file()
	contents = q_log.read_text(encoding="ascii")
	assert "form_ruid='900999999'" in contents
	assert "Ghost" in contents

	# HTML page surfaces the QUARANTINED marker.
	html = html_path.read_text(encoding="utf-8")
	assert "QUARANTINED" in html


def test_generate_html_resolver_called_per_row(monkeypatch, tmp_path):
	"""
	Resolver is invoked once per data row regardless of resolution outcome.
	A two-row CSV (one resolvable, one not) must produce exactly two
	resolver calls and exactly one saved image (under the Roster RUID).
	"""
	_install_fake_repo_root(monkeypatch, tmp_path)
	_stub_image_io(monkeypatch, tmp_path)

	image_dir = tmp_path / "BCHM_Prot_Img_01_Topic"
	raw_dir = image_dir / "raw"
	raw_dir.mkdir(parents=True)

	csv_path = tmp_path / "BCHM_Prot_Img_01-Topic.csv"
	csv_path.write_text(
		"Username,Enter your first name,Enter your last name,"
		"Enter your RUID,Image\n"
		"asmith,Alice,Smith,900000001,https://drive/x\n"
		"ghost,Ghost,Person,900999999,https://drive/y\n",
		encoding="utf-8",
	)
	header, data_tree = dsi.read_csv(str(csv_path), -1)

	import protein_image_grader.roster_matching as rm
	import protein_image_grader.ruid_resolver as rr
	first_n = rm.normalize_name_text("Alice")
	last_n = rm.normalize_name_text("Smith")
	matcher = rm.RosterMatcher(roster={900000002: {
		"student_id": 900000002,
		"first_name": first_n, "last_name": last_n,
		"username": rm.normalize_username("asmith"), "alias": "",
		"full_name": (first_n + " " + last_n).strip(),
	}}, interactive=False)

	# Wrap the resolver function to count calls.
	call_count = [0]
	original = rr.resolve_form_row_to_roster_row
	def counting(*args, **kwargs):
		call_count[0] += 1
		return original(*args, **kwargs)
	monkeypatch.setattr(rr, "resolve_form_row_to_roster_row", counting)
	monkeypatch.setattr(dsi.ruid_resolver, "resolve_form_row_to_roster_row",
		counting)

	dsi.generate_html(
		str(csv_path), header, data_tree, _args(image_number=1),
		str(image_dir), str(raw_dir), None,
		str(image_dir / "profiles.html"),
		{"md5": {}, "phash": {}}, [False], matcher, set(),
	)

	assert call_count[0] == 2
	# The resolved row produced exactly one saved file under the Roster
	# RUID; the quarantined row produced none.
	saved = [p.name for p in raw_dir.iterdir()]
	assert any(name.startswith("900000002-") for name in saved), saved
	assert not any("900999999" in name for name in saved), saved


def test_extract_form_ruid_falls_back_when_id_column_missing(monkeypatch, tmp_path):
	"""
	A form CSV that lacks an explicit Student-ID column must still
	resolve via the 9-digit prefix fallback in
	`_extract_form_ruid_from_row` (`900...`/`960...` per RUID_POLICY).
	"""
	_install_fake_repo_root(monkeypatch, tmp_path)
	_stub_image_io(monkeypatch, tmp_path)

	image_dir = tmp_path / "BCHM_Prot_Img_01_Topic"
	raw_dir = image_dir / "raw"
	raw_dir.mkdir(parents=True)

	# CSV with no "Enter your RUID" column: resolver gets typed via the
	# fallback that scans every cell for a 900/960 prefix.
	csv_path = tmp_path / "BCHM_Prot_Img_01-Topic.csv"
	csv_path.write_text(
		"Username,Enter your first name,Enter your last name,Misc,Image\n"
		"asmith,Alice,Smith,900000001,https://drive/x\n",
		encoding="utf-8",
	)
	header, data_tree = dsi.read_csv(str(csv_path), -1)

	import protein_image_grader.roster_matching as rm
	first_n = rm.normalize_name_text("Alice")
	last_n = rm.normalize_name_text("Smith")
	matcher = rm.RosterMatcher(roster={900000002: {
		"student_id": 900000002,
		"first_name": first_n, "last_name": last_n,
		"username": rm.normalize_username("asmith"), "alias": "",
		"full_name": (first_n + " " + last_n).strip(),
	}}, interactive=False)

	dsi.generate_html(
		str(csv_path), header, data_tree, _args(image_number=1),
		str(image_dir), str(raw_dir), None,
		str(image_dir / "profiles.html"),
		{"md5": {}, "phash": {}}, [False], matcher, set(),
	)

	# Saved file uses the Roster RUID; the typed 900000001 from the
	# unlabeled "Misc" column was correctly picked up by the fallback.
	saved = [p.name for p in raw_dir.iterdir()]
	assert any(name.startswith("900000002-") for name in saved), saved


def test_header_lookup_is_case_insensitive(monkeypatch, tmp_path):
	"""
	The header lookup uses `roster_matching.find_column_ci`, so a CSV
	with all-lowercase or mixed-case header names must still resolve
	correctly. Regression guard: a case-sensitive change would silently
	fall back to the 900/960 prefix scan and could mask the bug.
	"""
	_install_fake_repo_root(monkeypatch, tmp_path)
	_stub_image_io(monkeypatch, tmp_path)

	image_dir = tmp_path / "BCHM_Prot_Img_01_Topic"
	raw_dir = image_dir / "raw"
	raw_dir.mkdir(parents=True)

	# All-lowercase headers; resolver must still extract the typed RUID
	# from the labeled column, not stumble onto the URL fragment.
	csv_path = tmp_path / "BCHM_Prot_Img_01-Topic.csv"
	csv_path.write_text(
		"username,enter your first name,enter your last name,"
		"enter your ruid,Image\n"
		"asmith,Alice,Smith,900000001,https://drive/x\n",
		encoding="utf-8",
	)
	header, data_tree = dsi.read_csv(str(csv_path), -1)

	import protein_image_grader.roster_matching as rm
	first_n = rm.normalize_name_text("Alice")
	last_n = rm.normalize_name_text("Smith")
	matcher = rm.RosterMatcher(roster={900000002: {
		"student_id": 900000002,
		"first_name": first_n, "last_name": last_n,
		"username": rm.normalize_username("asmith"), "alias": "",
		"full_name": (first_n + " " + last_n).strip(),
	}}, interactive=False)

	dsi.generate_html(
		str(csv_path), header, data_tree, _args(image_number=1),
		str(image_dir), str(raw_dir), None,
		str(image_dir / "profiles.html"),
		{"md5": {}, "phash": {}}, [False], matcher, set(),
	)

	saved = [p.name for p in raw_dir.iterdir()]
	assert any(name.startswith("900000002-") for name in saved), saved


def test_quarantine_log_appends_multiple_rows(monkeypatch, tmp_path):
	"""
	A multi-row CSV with two unresolvable rows must append two distinct
	records to quarantine.log (the file is opened in 'a' mode per row).
	"""
	_install_fake_repo_root(monkeypatch, tmp_path)
	_stub_image_io(monkeypatch, tmp_path)

	image_dir = tmp_path / "BCHM_Prot_Img_01_Topic"
	raw_dir = image_dir / "raw"
	raw_dir.mkdir(parents=True)

	csv_path = tmp_path / "BCHM_Prot_Img_01-Topic.csv"
	csv_path.write_text(
		"Username,Enter your first name,Enter your last name,"
		"Enter your RUID,Image\n"
		"ghost1,Ghost,Person,900111111,https://drive/x\n"
		"ghost2,Phantom,Spectre,900222222,https://drive/y\n",
		encoding="utf-8",
	)
	header, data_tree = dsi.read_csv(str(csv_path), -1)

	import protein_image_grader.roster_matching as rm
	matcher = rm.RosterMatcher(roster={}, interactive=False)

	dsi.generate_html(
		str(csv_path), header, data_tree, _args(image_number=1),
		str(image_dir), str(raw_dir), None,
		str(image_dir / "profiles.html"),
		{"md5": {}, "phash": {}}, [False], matcher, set(),
	)

	q_log = csv_path.parent / "quarantine.log"
	contents = q_log.read_text(encoding="ascii")
	# Both quarantined rows were appended; neither overwrote the other.
	assert "form_ruid='900111111'" in contents
	assert "form_ruid='900222222'" in contents


def test_assigned_ruids_shared_across_csvs_in_one_run(monkeypatch, tmp_path):
	"""
	When `--all` runs multiple CSVs, the same `assigned_ruids` set is
	threaded through every `process_one_csv` call, so a Form RUID
	resolved in CSV 1 cannot silently re-resolve to the same student
	in CSV 2 (the second occurrence becomes a duplicate quarantine).
	"""
	_install_fake_repo_root(monkeypatch, tmp_path)
	_stub_image_io(monkeypatch, tmp_path)

	import protein_image_grader.roster_matching as rm
	import protein_image_grader.ruid_resolver as rr
	first_n = rm.normalize_name_text("Alice")
	last_n = rm.normalize_name_text("Smith")
	matcher = rm.RosterMatcher(roster={900000002: {
		"student_id": 900000002,
		"first_name": first_n, "last_name": last_n,
		"username": rm.normalize_username("asmith"), "alias": "",
		"full_name": (first_n + " " + last_n).strip(),
	}}, interactive=False)
	assigned: set = set()

	# Resolve once -> ResolvedStudent and Roster RUID claimed.
	first = rr.resolve_form_row_to_roster_row(
		{"form_ruid": "900000001", "first_name": "Alice",
			"last_name": "Smith", "username": "asmith"},
		matcher, assigned,
	)
	assert isinstance(first, rr.ResolvedStudent)
	assert 900000002 in assigned

	# A second CSV row, different typed Form RUID, same Roster row:
	# must come back as duplicate because we share the same `assigned` set.
	second = rr.resolve_form_row_to_roster_row(
		{"form_ruid": "900999999", "first_name": "Alice",
			"last_name": "Smith", "username": "asmith"},
		matcher, assigned,
	)
	assert isinstance(second, rr.UnresolvedStudent)
	assert second.reason == "duplicate"
