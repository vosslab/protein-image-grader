# Standard Library
import csv
import pathlib
import importlib.util


# tools/ holds executable scripts and is intentionally not a package.
# Load the migration script by file path so the test does not import tools.*.
SCRIPT_PATH = pathlib.Path(__file__).resolve().parent.parent / "tools" / "copy_archive_images.py"
spec = importlib.util.spec_from_file_location("copy_archive_images", SCRIPT_PATH)
copy_archive_images = importlib.util.module_from_spec(spec)
spec.loader.exec_module(copy_archive_images)


#============================================
def read_manifest(path: pathlib.Path) -> list[dict]:
	"""
	Read a copy manifest CSV.
	"""
	with open(path, newline="") as handle:
		reader = csv.DictReader(handle)
		rows = list(reader)
	return rows


#============================================
def test_dry_run_writes_manifest_without_copying(tmp_path: pathlib.Path) -> None:
	"""
	Check dry-run writes an audit manifest and copies nothing.
	"""
	source = tmp_path / "ARCHIVE_IMAGES"
	source_file = source / "BCHM_Prot_Img_04" / "x.png"
	source_file.parent.mkdir(parents=True)
	source_file.write_bytes(b"image")
	target_root = tmp_path / "archive"
	manifest = target_root / "legacy_import" / "copy_manifest.csv"

	records = copy_archive_images.copy_archive_images(
		source,
		target_root,
		"legacy_import",
		manifest,
		False,
	)

	target_file = target_root / "legacy_import" / "image_bank" / "BCHM_Prot_Img_04" / "x.png"
	assert records[0]["status"] == "would_copy"
	assert not target_file.exists()
	assert read_manifest(manifest)[0]["status"] == "would_copy"


#============================================
def test_copy_mode_preserves_assignment_folder(tmp_path: pathlib.Path) -> None:
	"""
	Check copy mode preserves source assignment folders.
	"""
	source = tmp_path / "ARCHIVE_IMAGES"
	source_file = source / "BCHM_Prot_Img_04" / "x.png"
	source_file.parent.mkdir(parents=True)
	source_file.write_bytes(b"image")
	target_root = tmp_path / "archive"

	records = copy_archive_images.copy_archive_images(
		source,
		target_root,
		"legacy_import",
		None,
		True,
	)

	target_file = target_root / "legacy_import" / "image_bank" / "BCHM_Prot_Img_04" / "x.png"
	assert records[0]["status"] == "copied"
	assert target_file.read_bytes() == b"image"


#============================================
def test_existing_same_file_is_skipped(tmp_path: pathlib.Path) -> None:
	"""
	Check identical existing targets are skipped.
	"""
	source = tmp_path / "ARCHIVE_IMAGES"
	source_file = source / "BCHM_Prot_Img_04" / "x.png"
	source_file.parent.mkdir(parents=True)
	source_file.write_bytes(b"image")
	target_root = tmp_path / "archive"
	target_file = target_root / "legacy_import" / "image_bank" / "BCHM_Prot_Img_04" / "x.png"
	target_file.parent.mkdir(parents=True)
	target_file.write_bytes(b"image")

	record = copy_archive_images.inspect_copy_status(source_file, target_file)
	assert record["status"] == "skipped_existing"
	assert record["source_hash"] == record["target_hash"]


#============================================
def test_existing_different_file_is_conflict(tmp_path: pathlib.Path) -> None:
	"""
	Check different existing targets are conflicts.
	"""
	source = tmp_path / "ARCHIVE_IMAGES"
	source_file = source / "BCHM_Prot_Img_04" / "x.png"
	source_file.parent.mkdir(parents=True)
	source_file.write_bytes(b"image")
	target_root = tmp_path / "archive"
	target_file = target_root / "legacy_import" / "image_bank" / "BCHM_Prot_Img_04" / "x.png"
	target_file.parent.mkdir(parents=True)
	target_file.write_bytes(b"different")

	record = copy_archive_images.inspect_copy_status(source_file, target_file)
	assert record["status"] == "conflict"
	assert record["source_hash"] != record["target_hash"]


#============================================
def test_non_image_file_is_reported_and_not_copied(tmp_path: pathlib.Path) -> None:
	"""
	Check non-image files are reported and skipped.
	"""
	source = tmp_path / "ARCHIVE_IMAGES"
	source_file = source / "BCHM_Prot_Img_04" / "notes.txt"
	source_file.parent.mkdir(parents=True)
	source_file.write_text("notes")
	target_root = tmp_path / "archive"

	records = copy_archive_images.copy_archive_images(
		source,
		target_root,
		"legacy_import",
		None,
		True,
	)

	target_file = target_root / "legacy_import" / "image_bank" / "BCHM_Prot_Img_04" / "notes.txt"
	assert records[0]["status"] == "non_image"
	assert not target_file.exists()
