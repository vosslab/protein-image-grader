# Changelog

## 2026-05-05

### Additions and New Features
- Add `start_grading.py` (root entry point + `protein_image_grader/start_grading.py` implementation) as a thin orchestrator that prints a per-image status dashboard and runs one canonical step (`download`, `grade`, or `regrade`) for one image at a time. Auto-imports stray `BCHM_Prot_Img_##-*.csv` files from the repo root into `Protein_Images/semesters/<term>/forms/` via `shutil.move` (`Protein_Images/` is gitignored, so `git mv` is not appropriate). Refuses to overwrite existing destinations and refuses to act when canonical duplicates exist. CLI is intentionally minimal per `docs/PYTHON_STYLE.md`: `-t/--term`, `-i/--image`, `-s/--step {download,grade,regrade}`, `--status-only`. No `--yes`, no `--no-import-root-csvs`, no email/upload step in v1; overwrite confirmation is always interactive.
- Add `tests/test_start_grading.py` covering auto-import (move, dir creation, refuse overwrite, ignore unrelated files), duplicate detection, dashboard row construction (complete and missing), `compute_next_step` progression, command construction for `download`/`grade` (asserts no `--output-dir` is passed for download), refusal to expose batch helpers, and required-resource enforcement (`forms/` always required, `roster.csv` required only for grade/regrade, `blackboard_assignment_ids.txt` warning-only).

### Behavior or Interface Changes
- `download_submission_images.py` now writes to the canonical `Protein_Images/semesters/<term>/submissions/download_NN_raw/` when the input CSV lives under `Protein_Images/semesters/<term>/forms/`. The legacy `data/runs/DOWNLOAD_NN_year_YYYY/` default has been removed; the argparse default for `--output-dir` is `None`. An explicit `--output-dir` is honored verbatim. Non-canonical CSV inputs without an explicit `--output-dir` now raise a clear `ValueError` instead of silently falling back to `data/runs/`. New helpers: `extract_image_number_from_csv_basename`, `infer_canonical_output_dir`, `resolve_image_dir`. `profiles_image_NN.html` is written next to `download_NN_raw/` (in the canonical submissions dir) when no override is passed.
- Drop the unused `build_image_dir` function from `download_submission_images.py`.

### Fixes and Maintenance
- Add `tests/test_download_output_dir.py` to pin Phase 0 contract: canonical CSV path implies canonical submissions output, explicit `--output-dir` override wins, non-canonical CSV without override errors, image-number/path mismatch errors, and basename parsing rejects non-canonical names.

### Decisions and Failures
- Auto-import in `start_grading.py` is unconditional (no `--no-import-root-csvs` escape hatch). The user explicitly wants the scripts to maintain canonical structure rather than rely on the user remembering to move files; an opt-out would re-introduce the "where do I start?" confusion this tool is meant to fix.
- The orchestrator does not expose a `--yes` overwrite-bypass flag. Bypass flags exist mostly to enable scripted batch runs, which are explicitly out of scope: each grading run handles exactly one image assignment in the context of the full image-NN dataset.

- Fix `source_me.sh` to prepend the repo root (via `git rev-parse --show-toplevel`) to `PYTHONPATH` so `tools/copy_archive_images.py` and other helper scripts can `import protein_image_grader.*` after `source source_me.sh`.
- Add `protein_image_grader/archive_paths.py` for canonical archive hash paths and legacy path resolution (imported by runtime code).
- Add `tools/copy_archive_images.py` for copy-only legacy archive migration with a CSV manifest.
- Update grading, download, duplicate checking, and hash rebuild paths to use archive utilities.
- Load Google Drive credentials lazily so non-download tests do not require `service_key.json`.
- Add pytest configuration to avoid collecting symlinked archive content.
- Document canonical archive paths, Synology-compatible legacy resolution, and copy migration commands.
- Keep `tools/` for executable maintenance scripts only; runtime infrastructure lives in `protein_image_grader/`.
- `tools/` has no `__init__.py` and is not importable; tests load `tools/copy_archive_images.py` by file path.
- Style: make every module under `protein_image_grader/` library-only by removing `if __name__ == '__main__'` blocks; the root wrapper scripts (`grade_protein_image.py`, `download_submission_images.py`, `send_feedback_email.py`) remain the only CLI entry points for those flows.
- Style: drop the executable bit on every `protein_image_grader/*.py` file.
- Style: `git mv protein_image_grader/log_image_hashes.py tools/log_image_hashes.py`, add a proper shebang, and update `docs/USAGE.md` and `docs/ARCHIVE_PROCESS.md` to invoke it as `python3 tools/log_image_hashes.py ...`.
- Style: replace `sys.exit(1)` calls in library code with raised errors (`ValueError`, `RuntimeError`, `FileNotFoundError`, `NotImplementedError`) across `commonlib.py`, `download_submission_images.py`, `google_drive_image_utils.py`, `grade_protein_image.py`, `read_save_images.py`, `send_feedback_email.py`, `student_id_protein.py`, and `timestamp_tools.py`; the Tk save-and-exit handler in `interactive_image_criteria_class.py` is unchanged.
- Style: narrow the broad `except Exception` in `grade_protein_image.py` so the crash backup is written and the original exception is re-raised instead of swallowed by `sys.exit(1)`.
- Style: in dry-run mode, `send_feedback_email.py` now `break`s out of the loop after the test email instead of calling `sys.exit(1)` from the dry-run branch.
- Style: convert remaining `%` and `.format()` strings in `commonlib.py` and `send_feedback_email.py` to f-strings.
- Style: drop the `__all__` list from `roster_matching.py`; per the package convention, `__init__.py` stays minimal and callers import from submodules directly.
- Style: replace `typing.Dict` / `typing.Tuple` / `typing.Union` references in `grade_protein_image.py` docstrings with builtin generic descriptions.
- Style: move all module-level asserts out of library code (`student_id_protein.py`, `timestamp_tools.py`, `google_drive_image_utils.py`, `grade_protein_image.py`) into a new pytest module `tests/test_module_level_assertions.py` so importing the package no longer runs sanity checks at import time.
- Style: replace the `'int or float'` string return annotation in `timestamp_tools.get_deduction` with the builtin generic `int | float`.
- Add `protein_image_grader/rmspaces.py` (`git mv tools/rmspaces.py`) as a library-only filename normalizer; the CLI helpers (`moveName`, `cleanNames`, `rmSpaces`, `__main__` block) are stripped, leaving `unicode_to_string` and `cleanName`.
- Replace the in-function `import rmspaces` plus `try/except ImportError` inside `google_drive_image_utils.download_file_data_from_google_drive` with a top-level `import protein_image_grader.rmspaces`; the downloader now calls `protein_image_grader.rmspaces.cleanName` directly.
- Narrow `transliterate` failure handling in `rmspaces.unicode_to_string` from a bare `except Exception` to `except transliterate.exceptions.LanguageDetectionError`, and drop the broad `try/except UnicodeDecodeError` around the bytes->str decode (callers pass strings).
- Replace the `sys.exit(1)` in `rmspaces.cleanName` empty-result path with a `ValueError` so the helper never terminates the host process.
- Add `transliterate` to `pip_requirements.txt` so `protein_image_grader/rmspaces.py` has a declared dependency.
- Consolidate filename normalization on `protein_image_grader.rmspaces.cleanName`. Replace the four `commonlib.CommonLib().cleanName(...)` call sites in `archive_paths.py`, `download_submission_images.py`, and `read_save_images.py` (`generate_output_filename` and `get_image_data`). The previous `commonlib` cleaner capitalized the first letter, capped names at 40 chars, and lower-cased extensions; rmspaces preserves case, has no length cap, and preserves extension case. New archive folders and image basenames will therefore be named slightly differently than legacy ones already on disk.
- Delete `protein_image_grader/commonlib.py` (`git rm`). Only `CommonLib.cleanName` was ever called and the other 15 helpers were dead code; consolidating on rmspaces removes the redundant module entirely.
- Style: convert nearly all `from X import Y` imports across `protein_image_grader/*.py` to fully-qualified `import X` form so call sites are self-describing. Updated modules: `download_submission_images.py` (`pillow_heif`), `duplicate_processing.py` (`rich.console`, `rich.style`, `collections`), `google_drive_image_utils.py` (`PIL.Image`, `PIL.ImageChops`, `google.oauth2.service_account`), `grade_protein_image.py` (`rich.console`, `rich.style`, `rich.table`), `interactive_image_criteria_class.py` (rich), `read_save_images.py` (rich, `PIL.Image`), `student_id_protein.py` (rich, `collections`), `timestamp_tools.py` (`datetime`), and `tests/test_shebangs.py` (drop `from typing import Optional` in favor of builtin `int | None`).
- Style: keep `from types import MappingProxyType` in `grade_protein_image.py` rather than `import types`; the user prefers not to import `types`.
- Style: convert `roster_matching.py:522` and `roster_matching.py:554` user-quit signals from `raise SystemExit(...)` to `raise RuntimeError(...)` so library callers can catch them as ordinary exceptions.
- Style: drop the `--threshold`, `--gap`, and `--candidates` argparse flags from `roster_matching.py`; the matcher already exposes module-level defaults (0.88, 0.06, 5) and these are tuning constants, not inputs that change between runs.
- Style: drop non-builtin type annotations from `student_id_protein.get_input_validation` (the `style: Style = ...` arg) and from the four PIL helpers in `google_drive_image_utils.py` (`get_background_color`, `rotate_if_tall`, `trim`, `multi_trim`); per PYTHON_STYLE.md, type hints stay on builtin types only.
- Style: regroup imports in `duplicate_processing.py`, `grade_protein_image.py`, `interactive_image_criteria_class.py`, `read_save_images.py`, and `student_id_protein.py` under `# Standard Library`, `# PIP3 modules`, and `# local repo modules` headings.

### Additions and New Features
- Patch 1 (complete) of the Protein_Images integration milestone: add `protein_image_grader/protein_images_path.py`, the canonical helper module that resolves the external data root, the active term, and per-term subpaths (`get_protein_images_dir`, `get_archive_images_dir`, `get_active_term`, `get_term_dir`, `get_forms_dir`, `get_yaml_dir`, `get_grades_dir`, `get_submissions_dir`, `get_roster_csv`, `get_credentials_dir`, `SETUP_MESSAGE`). Path resolution is lazy (no import-time IO). Tests in `tests/test_protein_images_path.py` pin the contract using `tmp_path` and a monkeypatched repo root.
- Patch 2 (complete) of the Protein_Images integration milestone: add the `local_migrations/protein_images/` package containing `migrate_protein_images.py` plus the classifier, planner, reporting, backup_check, and executor modules. Dry-run is the default; `--apply` requires a previously saved report and a sibling backup directory. 35 tests run against synthetic fixture trees under `tmp_path`; no real `Protein_Images/` data is touched.

### Behavior or Interface Changes
- Protein_Images integration milestone: no production behavior changes applied yet. Patch 5 will add `--term` and remove `--roster` from `grade_protein_image.py`; Patch 4 will switch `archive_paths.py`, `tools/copy_archive_images.py`, `tools/log_image_hashes.py`, and the `duplicate_processing.py` string check to lowercase `archive_images/`. These are planned, not done.

### Fixes and Maintenance
- Update `.gitignore` to anchor (with leading `/`) the external data root and stray repo-root data files: `/Protein_Images`, `/ARCHIVE_IMAGES`, `/protein_image.tar`, `/BCHM_Prot_Img_*.csv`, `/current_students.csv`. Existing nested rules (`data/inputs/current_students.csv`, etc.) are left untouched.
- Update `README.md` with an "External data" section: `ln -s` instructions, the planned canonical layout, the role of `active_term.txt` and the planned `--term` override, a pointer to `local_migrations/protein_images/migrate_protein_images.py --help`, and the credentials location at `~/.config/bchm_355/credentials/`.

### Removals and Deprecations
- Planned for the Protein_Images integration milestone (Patch 6, not yet done): remove the redundant top-level `ARCHIVE_IMAGES` symlink and the repo-root `BCHM_Prot_Img_*.csv` and `current_students.csv` copies after the grader is verified against canonical paths.
- Planned for the Protein_Images integration milestone (Patch 5, not yet done): remove the `--roster` flag from `grade_protein_image.py` after the term-aware roster resolver is verified by one real grading run.

### Decisions and Failures
- Decision: leave `os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")` in `google_drive_image_utils.find_service_key_file`. PYTHON_STYLE.md only forbids invented env vars, and this is the standard Google ecosystem variable used by every official Google Cloud SDK.
- Decision: keep the `SKIP_REPO_HYGIENE` env-var escape hatch in `tests/conftest.py`, `tests/git_file_utils.py`, `tests/test_ascii_compliance.py`, and `tests/test_import_requirements.py`. The style rule targets program code; threading a pytest CLI flag through shared test helpers and external CI invocations is more disruptive than the rule warrants.
- Decision: do not rewrite `student_entry.get(...)` / `params.get(...)` / `image_hashes['md5'].get(...)` calls in `read_save_images.py`, `duplicate_processing.py`, `roster_matching.py`, `file_io_protein.py`, and `send_feedback_email.py`. The audit flagged these as "default hides bug" but each one is a legitimate `is None` / falsy check on a genuinely optional field, not a fallback that masks a missing required key.
- Decision (Protein_Images integration milestone): canonical layout under `Protein_Images/` is lowercase snake_case throughout (`archive_images/`, `semesters/<season>_<year>/{roster.csv,forms,yaml,grades,submissions}`, `legacy/needs_review/`).
- Decision (Protein_Images integration milestone): the active term is explicit (`Protein_Images/active_term.txt` plus optional `--term` override). No date-based auto-detection, because regrades happen out of season.
- Decision (Protein_Images integration milestone): credentials (`api_file.json`, `service_key.json`) are not course data and will live at `~/.config/bchm_355/credentials/`, not inside `Protein_Images/`.
- Decision (Protein_Images integration milestone): migration is dry-run-first, requires a sibling `Protein_Images_backup_<date>/` to exist before `--apply`, and only moves or renames within `Protein_Images/`. It never deletes data; low-confidence items go to `legacy/needs_review/`.
- Decision (Protein_Images integration milestone): handle macOS case-only renames (e.g. `ARCHIVE_IMAGES` -> `archive_images`) explicitly via a two-step move, since HFS+/APFS default mounts are case-insensitive.
- Decision (Protein_Images integration milestone): `local_migrations/` is tracked in git temporarily during this milestone and will be removed in a cleanup patch after the migration is applied (WS-C).

### Developer Tests and Notes
- Protein_Images integration milestone: Patches 3 (apply migration to real data), 4 (refactor `archive-paths` and tools-cli), 5 (refactor grader-cli, add `--term`, remove `--roster`), 6 (gitignore + repo-root cleanup), and 7 (final docs sweep) are upcoming, not yet done.
- Protein_Images integration milestone manual correction (2026-05-05, post-WS-C): the migration classifier sent `IMAGE_02/` to `semesters/spring_2024/submissions/image_02/` based on the legacy folder's birthtime (2024-02-17). The folder had been reused across terms; its 11 contents all have mtime 2025-02-25 and belong to spring 2025. Manually moved the folder to `Protein_Images/semesters/spring_2025/submissions/image_02/` after validation. The empty `Protein_Images/semesters/spring_2024/submissions/` directory was left in place. Recommendation: future migration runs should weight content mtime over folder birthtime when inferring per-image term.
- Rename canonical `archive_images` -> `image_bank` (Synology `Protein_Images/image_bank/` and per-term repo `archive/<term>/image_bank/`) to avoid Synology Drive case-conflict markers from the prior `ARCHIVE_IMAGES` -> `archive_images` rename. All 2615 hash records in `archive/image_hashes.yml` rewritten; helper renamed to `get_image_bank_dir()`; constant renamed to `IMAGE_BANK_NAME` / `IMAGE_BANK_SUBDIR`. Repo-internal `archive/` folder name kept as-is (unambiguous in context).

## 2025-12-29
- Rename `protein_image_grader/test_google_image.py` to `protein_image_grader/google_drive_image_utils.py`.
- Add service key discovery helper in `protein_image_grader/google_drive_image_utils.py`.
- Remove the root-level `test_google_image.py` script.

## 2025-12-23
- Add `pip_requirements.txt` with third-party dependencies used in this repo.
- Add this changelog file.
- Create `protein_image_grader/` as the canonical code location and add root entry scripts.
- Add `download_submission_images.py` for downloading protein images and generating HTML review output.
- Remove legacy `teaching_scripts/` and `protein_images/` directories after migration.
- Implement `download_image_and_inspect()` in `protein_image_grader/google_drive_image_utils.py`.
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
- Auto-copy input CSV into `data/runs/IMAGE_XX/` and default roster to `current_students.csv`.
- Improve missing roster error messaging.
- Ignore duplicate matches when filenames share the same 9-digit RUID prefix.
- Skip missing archive files when opening duplicate-review groups and guard against missing student entries.
- Document RUID duplicate-handling in archive and usage docs.
