# Changelog

## 2025-12-23
- Add `pip_requirements.txt` with third-party dependencies used in this repo.
- Add this changelog file.
- Create `protein_image_grader/` as the canonical code location and add root entry scripts.
- Add `download_submission_images.py` for downloading protein images and generating HTML review output.
- Remove legacy `teaching_scripts/` and `protein_images/` directories after migration.
- Implement `download_image_and_inspect()` in `protein_image_grader/test_google_image.py`.
- Remove `protein_image_grader/sendEmail.py` (older email script superseded by `send_feedback_email.py`).
- Add `spec_yaml_files/` as tracked assignment specs.
- Add `data/inputs/current_students_template.csv` and ignore `data/inputs/current_students.csv`.
- Move assignment YAML specs to `spec_yaml_files/` and update CLI defaults.
- Remove session/year CLI options so outputs remain flat (e.g., `IMAGE_06`, `DOWNLOAD_03_year_2025`).
- Track `archive/image_hashes.yml` and move hashes there.
- Auto-archive downloaded images and update hashes in `download_submission_images.py`.
- Auto-archive images and update hashes during grading in `read_save_images.py`.
- Update `log_image_hashes.py` to scan `archive/*/ARCHIVE_IMAGES/`.
- Generate visual grading HTML from `grade_protein_image.py` using shared HTML helpers.
- Update `README.md` and add usage and file structure docs.
- Add archive process spec documentation.
- Merge `common_image_questions.yml` into assignment specs at load time.
- Add basic test scripts for common merge and pyflakes.
- Fix pyflakes warnings and skip archive content in lint script.
- Fix test import path for `protein_image_grader` package.
