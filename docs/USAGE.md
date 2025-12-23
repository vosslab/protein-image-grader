# Usage

## Typical flow
- Place assignment specs in `spec_yaml_files/`.
- Place roster data in `data/inputs/current_students.csv`.
- Download and review images with HTML:
	- `python3 download_submission_images.py -i <csv_file>`
- Grade:
	- `python3 grade_protein_image.py -i <image_number>`
- Send feedback:
	- `python3 send_feedback_email.py -i <image_number>`

## Inputs
- Assignment specs:
	- `spec_yaml_files/protein_image_XX.yml`
- Roster:
	- `data/inputs/current_students.csv`
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
