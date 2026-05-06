# Usage

## Typical flow
- Create `Protein_Images/` structure or symlink an existing one.
- Place canonical form CSVs in `Protein_Images/semesters/<term>/forms/`.
- Place roster data in `Protein_Images/semesters/<term>/roster.csv`.
- Download and review images with HTML:
	- `source source_me.sh && python start_grading.py`
- Grade:
	- `source source_me.sh && python start_grading.py`
- Send feedback:
	- `source source_me.sh && python start_grading.py`

## Inputs
- Form CSVs:
	- `Protein_Images/semesters/<term>/forms/BCHM_Prot_Img_NN-<topic>.csv`
- Roster:
	- `Protein_Images/semesters/<term>/roster.csv`
- Cheat detection database:
	- `image_hashes.yml` at repo root

## Outputs
- Downloaded images (working):
	- `Protein_Images/semesters/<term>/<image_dir>/raw/`
	- `Protein_Images/semesters/<term>/<image_dir>/trim/` (with `--trim`)
- Downloaded images (archived):
	- `Protein_Images/image_bank/<term>/<image_dir>/raw/`
	- `Protein_Images/image_bank/<term>/<image_dir>/trim/`
- Grading outputs:
	- `Protein_Images/semesters/<term>/<image_dir>/output-protein_image_NN.yml`
- Visual grading HTML:
	- `Protein_Images/semesters/<term>/<image_dir>/profiles_image_NN.html`

## Archive behavior
- Archive images are copied into `Protein_Images/image_bank/<term>/<image_dir>/{raw,trim}/` automatically.
- `image_hashes.yml` at the repo root is updated with new image hashes from the archive.
- Hash records are written as canonical paths pointing to the image bank.
- Duplicate checks ignore matches when the 9-digit RUID prefix matches (same student).
- Archive files without a 9-digit prefix are still included in duplicate checks.

## Archive maintenance
- Dry-run hash rebuild:
	- `source source_me.sh && python tools/log_image_hashes.py`
- Rebuild hash database:
	- `source source_me.sh && python tools/log_image_hashes.py --rebuild`
- Migrate flat image_bank structure to term-organized:
	- `source source_me.sh && python tools/migrate_image_bank_to_terms.py`
- Apply the migration:
	- `source source_me.sh && python tools/migrate_image_bank_to_terms.py --apply`

## Common image questions
- If `spec_yaml_files/common_image_questions.yml` exists, it is merged into each assignment.
- By default, assignment questions override common questions with the same `name`.
- Set `use_common_image_questions: false` in an assignment YAML to disable the merge.

## Tests
- Pyflakes lint:
	- `tests/run_pyflakes.sh`
- Common question merge:
	- `python3 tests/test_common_image_questions.py`
