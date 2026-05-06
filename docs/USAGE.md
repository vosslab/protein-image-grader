# Usage

## Typical flow
- Create `Protein_Images/` structure or symlink an existing one.
- Place canonical form CSVs in `Protein_Images/semesters/<term>/forms/`.
- Place roster data in `Protein_Images/semesters/<term>/roster.csv`. The
  roster is required at download time (not just grading time): every
  saved filename uses the Roster RUID resolved from this file. See
  [docs/RUID_POLICY.md](RUID_POLICY.md).
- Download and review images with HTML:
	- `source source_me.sh && python start_grading.py`
- Grade:
	- `source source_me.sh && python start_grading.py`
	- The dashboard `Graded` column reports `PARTIAL` when the form
	  CSV has more submitter records than the graded output. This
	  typically happens after a re-downloaded form CSV adds late
	  submissions; `start_grading.py` then auto-routes the next run
	  to the `regrade` step so only the new rows are processed.
- Re-import a form CSV:
	- Drop the freshly-downloaded `BCHM_Prot_Img_NN-*.csv` at the
	  repo root and run `start_grading.py`. If the canonical copy
	  under `forms/` is byte-identical, the root copy is silently
	  removed. If the new file is a strict superset (every shared
	  `(Student ID, Timestamp)` row is byte-identical and the new
	  file only adds rows), the canonical copy is replaced in place.
	  Any other divergence (changed cell, removed row, header drift,
	  duplicate key) raises `FileExistsError` with the specific
	  reason so the operator can resolve it manually.
- Send feedback:
	- `source source_me.sh && python start_grading.py`
	- The `email` step contacts every Student ID in
	  `Protein_Images/semesters/<term>/roster.csv`. Submitters get the
	  per-question feedback email; non-submitters get a brief "no
	  submission received" notice. Both populations are tracked in
	  `Protein_Images/semesters/<term>/email_log.yml`. The dashboard's
	  `Emailed` column closes to `OK` only when every roster Student ID
	  has status `sent` or `no_submission_sent` for the image.

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
- Quarantine log (appended on every unresolvable row):
	- `Protein_Images/semesters/<term>/forms/quarantine.log` lists rows
	  whose Form RUID could not be resolved against the roster. No
	  image is saved for these rows. Each entry includes the Form RUID,
	  name, username, reason, score, and the top roster candidates the
	  matcher considered. Investigate and fix the roster (or the typed
	  RUID in the form CSV) before re-running.

## Archive behavior
- Archive images are copied into `Protein_Images/image_bank/<term>/<image_dir>/{raw,trim}/` automatically.
- `image_hashes.yml` at the repo root is updated with new image hashes from the archive.
- Hash records are written as canonical paths pointing to the image bank.
- Duplicate checks ignore matches when the 9-digit RUID prefix matches (same student).
- Archive files without a 9-digit prefix are still included in duplicate checks.
- `--output-dir <path>` redirects working files to a custom path AND disables archive sync (no writes to `image_bank/`, no hash updates). Use this for ad-hoc reruns into scratch dirs.
- `--archive-anyway` re-enables archive sync when paired with `--output-dir`. The archive folder name still resolves from the canonical semester layout, not the override path.

## Archive maintenance
- Dry-run hash rebuild:
	- `source source_me.sh && python tools/log_image_hashes.py`
- Rebuild hash database:
	- `source source_me.sh && python tools/log_image_hashes.py --rebuild`
- Migrate flat image_bank structure to term-organized:
	- `source source_me.sh && python local_migrations/migrate_image_bank_to_terms.py`
- Apply the migration:
	- `source source_me.sh && python local_migrations/migrate_image_bank_to_terms.py --apply`

## Common image questions
- If `spec_yaml_files/common_image_questions.yml` exists, it is merged into each assignment.
- By default, assignment questions override common questions with the same `name`.
- Set `use_common_image_questions: false` in an assignment YAML to disable the merge.

## Tests
- Pyflakes lint:
	- `tests/run_pyflakes.sh`
- Common question merge:
	- `python3 tests/test_common_image_questions.py`
