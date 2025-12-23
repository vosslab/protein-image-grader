# protein-image-grader
Grading system for biochemistry protein images.

## Quick start
- Install dependencies from `pip_requirements.txt`.
- Put assignment specs in `spec_yaml_files/`.
- Put roster data in `data/inputs/current_students.csv`.
- Run `python3 grade_protein_image.py -i <image_number>`.
- After grading, run `python3 send_feedback_email.py -i <image_number>`.

## Project layout
- `spec_yaml_files/` holds assignment spec YAML files.
- `data/inputs/` holds current roster data and templates.
- `data/runs/` holds generated grading outputs.
- `archive/` holds the cheat detection hash database and archive images (images ignored by git).

## Docs
- Usage details: [docs/USAGE.md](docs/USAGE.md)
- File layout: [docs/FILE_STRUCTURE.md](docs/FILE_STRUCTURE.md)
- Change history: [docs/CHANGELOG.md](docs/CHANGELOG.md)
