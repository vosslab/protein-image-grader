# Changelog

## 2026-05-05
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

### Decisions and Failures
- Decision: leave `os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")` in `google_drive_image_utils.find_service_key_file`. PYTHON_STYLE.md only forbids invented env vars, and this is the standard Google ecosystem variable used by every official Google Cloud SDK.
- Decision: keep the `SKIP_REPO_HYGIENE` env-var escape hatch in `tests/conftest.py`, `tests/git_file_utils.py`, `tests/test_ascii_compliance.py`, and `tests/test_import_requirements.py`. The style rule targets program code; threading a pytest CLI flag through shared test helpers and external CI invocations is more disruptive than the rule warrants.
- Decision: do not rewrite `student_entry.get(...)` / `params.get(...)` / `image_hashes['md5'].get(...)` calls in `read_save_images.py`, `duplicate_processing.py`, `roster_matching.py`, `file_io_protein.py`, and `send_feedback_email.py`. The audit flagged these as "default hides bug" but each one is a legitimate `is None` / falsy check on a genuinely optional field, not a fallback that masks a missing required key.

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
