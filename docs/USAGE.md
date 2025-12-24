# Usage

## Typical flow
- Place assignment specs in `spec_yaml_files/`.
- Place roster data in `current_students.csv` at the repo root.
- Download and review images with HTML:
	- `python3 download_submission_images.py -i <csv_file>`
- Grade:
	- `python3 grade_protein_image.py -i <image_number>`
- Send feedback:
	- `python3 send_feedback_email.py -i <image_number>`

## Inputs
- Assignment specs:
	- `spec_yaml_files/protein_image_XX.yml`
	- `spec_yaml_files/common_image_questions.yml` (shared image questions)
- Roster:
	- `current_students.csv`
- Cheat detection database:
	- `archive/image_hashes.yml`

## Outputs
- Grading outputs:
	- `data/runs/IMAGE_XX/`
- Downloaded images:
	- `data/runs/DOWNLOAD_XX_year_YYYY/`
- Visual grading HTML:
	- `data/runs/IMAGE_XX/profiles.html`

## Archive behavior
- Archive images are copied into `archive/<year_term>/ARCHIVE_IMAGES/`.
- `archive/image_hashes.yml` is updated automatically as new images are processed.
- Duplicate checks ignore matches when the 9-digit RUID prefix matches (same student).
- Archive files without a 9-digit prefix are still included in duplicate checks.

## Common image questions
- If `spec_yaml_files/common_image_questions.yml` exists, it is merged into each assignment.
- By default, assignment questions override common questions with the same `name`.
- Set `use_common_image_questions: false` in an assignment YAML to disable the merge.

## Tests
- Pyflakes lint:
	- `tests/run_pyflakes.sh`
- Common question merge:
	- `python3 tests/test_common_image_questions.py`
