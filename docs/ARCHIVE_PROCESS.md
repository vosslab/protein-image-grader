# Archive process

This document describes how the archive is maintained and how image comparisons are made
for cheat detection.

## Archive layout
- Archive root: `Protein_Images/image_bank/`
- Hash database: `image_hashes.yml` at repo root (tracked)
- Raw/trim images (ignored by git):
	- `Protein_Images/image_bank/<term>/<image_dir>/raw/`
	- `Protein_Images/image_bank/<term>/<image_dir>/trim/`

`<term>` is canonical form `<season>_<year>`:
- `spring_2026` (Jan-May)
- `summer_2026` (Jun-Aug)
- `fall_2026` (Sep-Dec)

`<image_dir>` is derived from the form CSV basename, e.g., `BCHM_Prot_Img_04_Active_Site`.

Canonical hash paths are repo-relative POSIX-style paths:
- `Protein_Images/image_bank/spring_2026/BCHM_Prot_Img_04_Active_Site/raw/file.png`
- `Protein_Images/image_bank/spring_2026/BCHM_Prot_Img_04_Active_Site/trim/file-trim.jpg`

## Archive path utility
- `protein_image_grader/archive_paths.py` and `protein_image_grader/protein_images_path.py` centralize archive path rules.
- `protein_images_path.get_image_bank_dir()` resolves `Protein_Images/image_bank/`.
- `archive_paths.normalize_hash_path()` normalizes paths to canonical form before writing to `image_hashes.yml`.
- Paths are strictly validated: only `image_bank/<term>/<image_dir>/{raw,trim}/<file>` are accepted.
- Legacy archive paths are not supported in new code paths.

## How the archive is updated

### Download flow
- `download_submission_images.py` downloads each image to the working directory (`Protein_Images/semesters/<term>/<image_dir>/raw/`).
- Each raw image is copied into the canonical archive folder (`Protein_Images/image_bank/<term>/<image_dir>/raw/`).
- If `--trim` is used, each trimmed image is copied to `Protein_Images/image_bank/<term>/<image_dir>/trim/`.
- The hash database is updated with new hashes pointing to the archive copies.

## Hash database format
`image_hashes.yml` at the repo root contains two dictionaries:
- `md5`: exact-match hash of pixel data
- `phash`: perceptual hash for similarity detection

Values are archive file paths. Keys are the hash strings.
Newly written values should use canonical repo-relative paths.

## How comparisons are made

### Local duplicates (current assignment)
Computed in `duplicate_processing.py`:
- `fill_local_image_hashes()` builds `local_image_hashes`
	- `md5` and `phash` keys map to lists of filenames
- `find_exact_local_duplicates()` flags exact matches within the current submission set
- Files that share the same 9-digit RUID prefix are treated as the same student and are not flagged

### Global duplicates (across semesters)
Computed in `duplicate_processing.py`:
- `load_image_hashes()` loads `image_hashes.yml` from the repo root
- `find_exact_global_duplicates()` checks current images against `md5` and `phash`
- Matches with the same 9-digit RUID prefix are ignored (same student resubmission)
- Archive files without a 9-digit prefix are still eligible for duplicate checks

### Similar images
Computed in `duplicate_processing.py`:
- `find_similar_duplicates()` compares each current `phash` to the archive `phash`
- It also compares current images to each other
- The Hamming distance cutoff is currently `38`
- Similarity warnings also skip matches that share the same 9-digit RUID prefix

## Hash generation details
Hashes are computed in `google_drive_image_utils.py`:
- `calculate_md5()` hashes the trimmed pixel data
- `calculate_phash()` uses perceptual hash on trimmed images

## Maintenance
- To dry-run hash rebuilding:
	- `source source_me.sh && python tools/log_image_hashes.py`
- To rebuild hashes from the archive:
	- `source source_me.sh && python tools/log_image_hashes.py --rebuild`
- It scans `Protein_Images/image_bank/` and writes canonical paths to `image_hashes.yml`.

## Archive migration
- To migrate a flat `image_bank/` structure to term-organized layout:
	- `source source_me.sh && python tools/migrate_image_bank_to_terms.py`
- Dry-run mode (default) shows what would be moved.
- To perform the actual migration:
	- `source source_me.sh && python tools/migrate_image_bank_to_terms.py --apply`
- Files are moved to `Protein_Images/image_bank/<term>/<assignment>/{raw,trim}/`.
- Existing identical files (by MD5) are skipped.
- Different files at the same destination path trigger an error and stop the migration.
