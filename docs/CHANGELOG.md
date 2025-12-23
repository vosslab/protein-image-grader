# Changelog

## 2025-12-23
- Add `pip_requirements.txt` with third-party dependencies used in this repo.
- Add this changelog file.
- Create `protein_image_grader/` as the canonical code location and add root entry scripts.
- Add `download_submission_images.py` for downloading protein images and generating HTML review output.
- Remove legacy `teaching_scripts/` and `protein_images/` directories after migration.
- Implement `download_image_and_inspect()` in `protein_image_grader/test_google_image.py`.
- Remove `protein_image_grader/sendEmail.py` (older email script superseded by `send_feedback_email.py`).
- Add `data/inputs/YAML_files/` and `data/inputs/image_hashes.yml` as tracked inputs.
- Add `data/inputs/current_students_template.csv` and ignore `data/inputs/current_students.csv`.
- Move assignment YAML specs to `spec_yaml_files/` and update CLI defaults.
