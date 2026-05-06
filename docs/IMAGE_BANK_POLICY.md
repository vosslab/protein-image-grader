# Image bank policy

The "image bank" is `Protein_Images/image_bank/`: the durable, cross-year
reference of every student image that has ever been downloaded. It powers
plagiarism detection across semesters, and it is the only place a graded
image is guaranteed to live long-term.

This document is the policy + reference for the bank: when files enter,
when (if ever) they leave, and how cheat detection reads them.

## Lifecycle policy

**Dual-write on download, never auto-delete.** When `download_submission_images.py`
saves an image, it writes the same bytes to two places:

1. The semester working directory:
   `Protein_Images/semesters/<term>/<image_dir>/raw/` (and `trim/` with `--trim`).
   This is the grader's working copy; the HTML review page renders from here.
2. The image bank:
   `Protein_Images/image_bank/<term>/<image_dir>/raw/` (and `trim/`).
   This is the canonical long-term record.

No code path moves files between these two locations or deletes either
copy. Specifically:

- The semester copy is **never auto-removed** by any script. The operator
  may `rm` `<image_dir>/raw/` and `<image_dir>/trim/` by hand at end of
  term once grading and emails are finalized, if disk space is a concern.
- The bank copy is **never auto-removed** by any script and **never
  modified after first write**. Once an image lands in the bank, it stays
  there for cross-year duplicate detection.
- `image_hashes.yml` (at the repo root, tracked in git) records hashes
  pointing at bank paths only. Semester paths never appear in the hash
  database.

Dual-write does not produce duplicate hash entries: `image_hashes.yml` is
keyed on the hash, so identical bytes from the semester and bank copies
collapse to a single entry pointing at the bank path. Local-duplicate
scanning (`fill_local_image_hashes` at `protein_image_grader/duplicate_processing.py:124`)
iterates the in-memory student tree parsed from the working directory
and never walks the bank, so a student's working image cannot be
flagged against its own bank copy.
Cross-student global duplicates additionally ignore matches that share
the same 9-digit RUID prefix (same student resubmitting).

If the bank ever needs to be rebuilt from scratch, run
`tools/log_image_hashes.py --rebuild`; if a flat legacy `image_bank/`
needs to be reorganized into per-term subfolders, run
`local_migrations/migrate_image_bank_to_terms.py --apply`.

## Layout
- Bank root: `Protein_Images/image_bank/`
- Hash database: `image_hashes.yml` at repo root (tracked)
- Raw/trim images (ignored by git):
	- `Protein_Images/image_bank/<term>/<image_dir>/raw/`
	- `Protein_Images/image_bank/<term>/<image_dir>/trim/`

`<term>` is canonical form `<season>_<year>`:
- `spring_2026` (Jan-May)
- `summer_2026` (Jun-Aug)
- `fall_2026` (Sep-Dec)

`<image_dir>` is derived from the form CSV basename, e.g., `BCHM_Prot_Img_04_Active_Site`.

Canonical hash paths are POSIX-style and relative to `Protein_Images/` (the
`Protein_Images/` prefix is stripped by `normalize_hash_path` before writing):
- `image_bank/spring_2026/BCHM_Prot_Img_04_Active_Site/raw/file.png`
- `image_bank/spring_2026/BCHM_Prot_Img_04_Active_Site/trim/file-trim.jpg`

## Archive path utility
- `protein_image_grader/archive_paths.py` and `protein_image_grader/protein_images_path.py` centralize archive path rules.
- `protein_images_path.get_image_bank_dir()` resolves `Protein_Images/image_bank/`.
- `archive_paths.normalize_hash_path()` normalizes paths to canonical form before writing to `image_hashes.yml`.
- Paths are strictly validated: only `image_bank/<term>/<image_dir>/{raw,trim}/<file>` are accepted.
- Legacy archive paths are not supported in new code paths.

## How the archive is updated

### Download flow
- Each form row is first resolved through `protein_image_grader/ruid_resolver.py` so the saved filename uses the authoritative Roster RUID (per [docs/RUID_POLICY.md](RUID_POLICY.md)). Rows the matcher cannot resolve are quarantined: no image is downloaded, no archive write, no hash entry; the row is appended to `Protein_Images/semesters/<term>/forms/quarantine.log` for operator triage.
- `download_submission_images.py` downloads each image to the working directory (`Protein_Images/semesters/<term>/<image_dir>/raw/`).
- Each raw image is copied into the canonical archive folder (`Protein_Images/image_bank/<term>/<image_dir>/raw/`).
- If `--trim` is used, each trimmed image is copied to `Protein_Images/image_bank/<term>/<image_dir>/trim/`.
- The hash database is updated with new hashes pointing to the archive copies.
- Archive sync is disabled when `--output-dir` is provided. Pass `--archive-anyway` alongside `--output-dir` to keep archive sync on; the archive folder name still resolves from the canonical semester layout, not the override path.

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
	- `source source_me.sh && python local_migrations/migrate_image_bank_to_terms.py`
- Dry-run mode (default) shows what would be moved.
- To perform the actual migration:
	- `source source_me.sh && python local_migrations/migrate_image_bank_to_terms.py --apply`
- Files are moved to `Protein_Images/image_bank/<term>/<assignment>/{raw,trim}/`.
- Existing identical files (by MD5) are skipped.
- Different files at the same destination path trigger an error and stop the migration.
