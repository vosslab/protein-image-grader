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
	- The orchestrator always runs `send_feedback_email.py` in
	  dry-run mode first. Dry-run is end-to-end: for every student
	  it builds the body, composes the AppleScript, and prints it.
	  For the FIRST non-skipped student only, it dispatches a single
	  preview copy of that AppleScript to the instructor address
	  (`nvoss@roosevelt.edu`) with subject prefix
	  `[DRY-RUN PREVIEW]`. The preview proves Mail.app and
	  AppleScript work end-to-end before any student is touched; if
	  it fails, the run halts with a stack trace and no `dry_run`
	  rows are written. After a clean dry-run, when stdin is a TTY,
	  `start_grading.py` prompts `Dry-run complete. Send for real
	  now? [y/N]`. Answer `y` to re-run with `-e` and dispatch real
	  feedback emails to every student. Direct invocations of
	  `send_feedback_email.py` do not prompt; pass `-e/--send-email`
	  explicitly to opt in to a real send.

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
	- `Protein_Images/semesters/<term>/<image_dir>/trim/` (the orchestrator always passes `--trim --rotate`; direct invocations of `download_submission_images.py` produce trim/ only when `-t` is passed)
- Downloaded images (archived):
	- `Protein_Images/image_bank/<term>/<image_dir>/raw/`
	- `Protein_Images/image_bank/<term>/<image_dir>/trim/`
- Grading outputs (final and per-stage checkpoints; see "Checkpoint files and resumption" below):
	- `Protein_Images/semesters/<term>/<image_dir>/output-protein_image_NN.yml` (final, source of truth)
	- `Protein_Images/semesters/<term>/<image_dir>/output-protein_image_NN.csv` (export, downstream of YAML)
	- `Protein_Images/semesters/<term>/<image_dir>/post-questions_save.yml` (intermediate)
	- `Protein_Images/semesters/<term>/<image_dir>/post-images_save.yml` (intermediate)
	- `Protein_Images/semesters/<term>/<image_dir>/duplicate_check_save.yml` (intermediate)
	- `Protein_Images/semesters/<term>/<image_dir>/downloaded_images.yml` (intermediate)
	- `Protein_Images/semesters/<term>/<image_dir>/preprocess_save.yml` (intermediate)
- Visual grading HTML:
	- `Protein_Images/semesters/<term>/<image_dir>/protein_images_NN.html`
- Unresolved-RUID handling:
	- The downloader and the grader both raise `RuntimeError` on the
	  first row whose Form RUID cannot be resolved against
	  `roster.csv`. No image is saved and no grading output is
	  written. The error message names the offending Form RUID, the
	  typed name and username, the resolver's reason and score, and
	  the top roster candidates the matcher considered. Fix the
	  roster (or the typed RUID in the form CSV) and re-run. See
	  [docs/RUID_POLICY.md](RUID_POLICY.md).

## Force regrade
The grader resumes from a cached YAML checkpoint when `start_grading.py` routes to the `regrade` step. Cached students with `Image Assessment Complete: true` skip the interactive image-question prompt; their cached hashes, statuses, and final score flow into the regenerated CSV unchanged. To force re-doing one specific piece of work for one student, edit that student's row in the deepest checkpoint (`output-protein_image_NN.yml` when present, otherwise the latest stage's `*_save.yml`):

| Operator edit | Effect on next grade run |
| --- | --- |
| Set `Image Assessment Complete: false` | Re-prompt the image questions for that student. All other cached state stays. |
| Delete `<Question Name> Status` (drop the key) | Re-prompt that one CSV question. All other cached state stays. |
| Delete the entire student YAML row | Treat the student as completely new. The full pipeline runs for that student on the next regrade. |

Each lever controls only the work it describes. Hash- and download-forcing behavior is intentionally not promised here -- the existing image cache keys on `Image Format`, but the supported lever is to clear the field directly. When a form CSV has multiple rows for the same `Student ID`, the grader treats them as resubmissions and keeps the newest timestamp. On a regrade, a newer form timestamp also beats the cached YAML row so the resubmission is graded automatically; same-timestamp rows still reuse cached grading.

## Checkpoint files and resumption
The grader writes per-stage checkpoint YAMLs into each `<image_dir>/` so a crashed or interrupted run leaves the deepest reached state on disk. All six files share the same shape (a flat list of student dicts) but populate progressively richer fields. The table below lists files in the order the grader writes them during a normal run; `output-protein_image_NN.yml` is the deepest:

| Filename | Written after | Stage |
| --- | --- | --- |
| `downloaded_images.yml` | `read_save_images.read_and_save_student_images` finishes | downloaded |
| `duplicate_check_save.yml` | `duplicate_processing.check_duplicate_images` finishes | duplicate-check |
| `preprocess_save.yml` | the per-student `timestamp_due_date` loop finishes (the "Pre-Processing Turn In Date" stage; the filename is historical and does NOT mean this is the earliest checkpoint) | preprocess |
| `post-questions_save.yml` | `process_csv_question` finishes for all CSV questions | post-questions |
| `post-images_save.yml` | `interactive_image_criteria_class.process_image_questions_class` finishes for all students | post-images |
| `output-protein_image_NN.yml` | `file_io_protein.backup_tree_to_yaml` (final write, after final-score and exports) | output |

`start_grading.py` picks the deepest valid checkpoint by precedence (deepest = most graded work preserved):

```
output > post-images > post-questions > preprocess > duplicate-check > downloaded
```

Both the dashboard and the regrade router use the same picker. Dashboard behavior:

- Picks the deepest valid file silently.
- When more than one checkpoint exists AND the chosen file is shallower than `output-protein_image_NN.yml` (i.e. a crashed or in-flight run), the footer prints `image NN: using <label> checkpoint <chosen.name>; also found: <comma-list>`. When the chosen checkpoint is `output`, no advisory line is printed: the shallower `*_save.yml` files are normal scaffolding from the same successful run, not stale state, and listing them every dashboard refresh would be noise. No prompt; the dashboard is non-interactive.
- When the deepest YAML fails `safe_load` or fails structural validation (must be a list of dicts, every entry has a non-empty `Student ID`, no duplicate Student IDs, `Protein Image Number` matches the requested image), the row reports `graded == "CONFLICT"` and the footer prints `image NN: CHECKPOINT CONFLICT: <reason>`.

Regrade behavior:

- Same picker; passes the chosen path to `grade_protein_image.py` via the existing `--yaml-backup-file` flag.
- On checkpoint conflict, `regrade` aborts with exit code 2 and a clear message naming the offending file. No prompt. Operator deletes or repairs the file and re-runs.
- A direct `python3 protein_image_grader/grade_protein_image.py -i NN --term <term>` call without `--yaml-backup-file` does not auto-resume; only `start_grading.py`'s regrade step picks a checkpoint automatically.

CONFLICT recovery: when the dashboard reports `graded == "CONFLICT"` for an image, the deepest checkpoint YAML in that `<image_dir>/` either failed to parse or failed structural validation. To repair:

- Inspect the file named in the footer warning. The reason follows the colon.
- A valid checkpoint YAML must be a flat list of student dicts; each entry must carry a non-empty `Student ID` (string or int); no two entries may share a `Student ID`; if the entry carries `Protein Image Number`, it must equal the image number being graded.
- The simplest fix is usually to delete the corrupt file. The next-deepest checkpoint takes over via precedence; in the worst case grading restarts from `preprocess_save.yml` or from scratch when no checkpoint remains.
- If the file is mostly intact (e.g., one entry has a blank Student ID), edit it directly. Re-run `start_grading.py` to confirm the dashboard moved past CONFLICT.

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
