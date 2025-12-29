# Archive process

This document describes how the archive is maintained and how image comparisons are made
for cheat detection.

## Archive layout
- Archive root: `archive/`
- Hash database: `archive/image_hashes.yml` (tracked)
- Raw images (ignored by git):
	- `archive/<year_term>/ARCHIVE_IMAGES/BCHM_Prot_Img_XX[_AssignmentName]/`

`<year_term>` is derived from the current date:
- `1Spring` (Jan-May)
- `2Summer` (Jun-Aug)
- `3Fall` (Sep-Dec)

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
- To rebuild hashes from the archive, run `protein_image_grader/log_image_hashes.py`.
- It scans `archive/*/ARCHIVE_IMAGES/` and regenerates `archive/image_hashes.yml`.
