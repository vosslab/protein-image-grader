# File structure

## Top level
- `grade_protein_image.py`: run grading workflow
- `download_submission_images.py`: download images and generate HTML
- `send_feedback_email.py`: send feedback emails
- `spec_yaml_files/`: assignment spec YAML files
- `data/inputs/`: roster data and templates
- `data/runs/`: generated outputs (ignored by git)
- `archive/`: cheat detection database and archive images
- `tools/`: executable maintenance scripts (human-run)

## Package code
- `protein_image_grader/`: core modules used by the root scripts

## Archive notes
- `archive/image_hashes.yml` is tracked in git.
- `archive/<year_term>/ARCHIVE_IMAGES/` stores raw images (ignored by git).
- `archive/legacy_import/ARCHIVE_IMAGES/` stores copied legacy archive images.
- `protein_image_grader/archive_paths.py` defines archive path normalization and legacy path resolution (imported by runtime code).
- `tools/copy_archive_images.py` copies old archive images without moving or deleting source files.
