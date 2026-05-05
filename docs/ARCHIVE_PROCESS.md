# Archive process

This document describes how the archive is maintained and how image comparisons are made
for cheat detection.

## Archive layout
- Archive root: `archive/`
- Hash database: `archive/image_hashes.yml` (tracked)
- Raw images (ignored by git):
	- `archive/<year_term>/ARCHIVE_IMAGES/BCHM_Prot_Img_XX[_AssignmentName]/`
	- `archive/legacy_import/ARCHIVE_IMAGES/BCHM_Prot_Img_XX[_AssignmentName]/`

`<year_term>` is derived from the current date:
- `1Spring` (Jan-May)
- `2Summer` (Jun-Aug)
- `3Fall` (Sep-Dec)

Canonical hash paths are repo-relative POSIX-style paths:
- `archive/2026_1Spring/ARCHIVE_IMAGES/BCHM_Prot_Img_04_Active_Site/file.png`
- `archive/legacy_import/ARCHIVE_IMAGES/BCHM_Prot_Img_04_Active_Site/file.png`

The archive path rule is: read legacy path styles, write canonical paths.

## Archive path utility
- `protein_image_grader/archive_paths.py` centralizes archive path rules.
- It normalizes paths before they are written to `archive/image_hashes.yml`.
- It resolves old paths such as `ARCHIVE_IMAGES/...` for duplicate review.
- If a legacy repo-root `ARCHIVE_IMAGES` symlink exists, it is used.
- If that symlink is missing, legacy paths fall back to
	`archive/legacy_import/ARCHIVE_IMAGES/...`.
- Resolved paths may still point to missing files; caller code warns or fails based on context.

## How the archive is updated

### Download flow
- `download_submission_images.py` downloads each image.
- Each image is copied into the archive assignment folder.
- The hash database is updated with new hashes.

### Grading flow
- `grade_protein_image.py` downloads and saves each image.
- Each image is copied into the archive assignment folder.
- The hash database is updated with new hashes.

## Hash database format
`archive/image_hashes.yml` contains two dictionaries:
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
- `load_image_hashes()` loads `archive/image_hashes.yml`
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
	- `python3 protein_image_grader/log_image_hashes.py --archive-root archive`
- To rebuild hashes from the archive:
	- `python3 protein_image_grader/log_image_hashes.py --archive-root archive --rebuild`
- It scans `archive/*/ARCHIVE_IMAGES/` and writes canonical paths to
	`archive/image_hashes.yml`.

## Legacy archive copy migration
- Old Synology-backed archive folders are treated as read-only source data.
- To audit a copy migration from a repo-root `ARCHIVE_IMAGES` symlink:
	- `python3 tools/copy_archive_images.py --source-archive ARCHIVE_IMAGES`
- Dry-run mode writes a manifest by default:
	- `archive/legacy_import/copy_manifest.csv`
- To copy files after reviewing the manifest:
	- `python3 tools/copy_archive_images.py --source-archive ARCHIVE_IMAGES --copy`
- Files are copied into:
	- `archive/legacy_import/ARCHIVE_IMAGES/`
- Existing identical files are reported as `skipped_existing`.
- Existing different files are reported as `conflict` and are not overwritten.
- Non-image files are reported as `non_image` and are not copied.
