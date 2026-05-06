# protein-image-grader

Grading system for biochemistry protein images. Downloads student-submitted Google Drive images from Google Form CSVs, applies a YAML-driven rubric, detects cross-year duplicates by perceptual hash, and writes Blackboard upload CSVs and feedback emails. Intended for the course instructor running grading locally on macOS.

## External data

The grader requires a `Protein_Images/` directory at the repo root, supplied by the instructor as a symlink to a Synology-synced folder. It is never tracked in git and is not regenerable.

```
ln -s /path/to/your/Protein_Images Protein_Images
```

Set the active term in `Protein_Images/active_term.txt` (one line, e.g. `spring_2026`). Tools accept `--term` to override for regrading older semesters; there is no date-based auto-detection. Credentials (`api_file.json`, `service_key.json`) live at `~/.config/bchm_355/credentials/`, not inside `Protein_Images/`.

For the canonical `Protein_Images/` tree, see [docs/FILE_STRUCTURE.md](docs/FILE_STRUCTURE.md).

## Quick start

- Install dependencies from `pip_requirements.txt`.
- Symlink `Protein_Images/` and write the active term to `Protein_Images/active_term.txt`.
- Drop form CSV exports under `Protein_Images/semesters/<term>/forms/`.
- Run the orchestrator:

```
source source_me.sh && python start_grading.py
```

With no flags it prints a per-image dashboard for the active term. `start_grading.py -i <NN>` runs the next pending step (download -> grade -> email -> blackboard upload) for one image.

## Documentation

- [docs/USAGE.md](docs/USAGE.md): inputs, outputs, archive behavior, and CLI flags.
- [docs/FILE_STRUCTURE.md](docs/FILE_STRUCTURE.md): canonical `Protein_Images/` and repo layout.
- [docs/ARCHIVE_PROCESS.md](docs/ARCHIVE_PROCESS.md): cross-year hash archive and duplicate detection.
- [docs/RUID_POLICY.md](docs/RUID_POLICY.md): Form RUID vs Roster RUID rules for filenames and CSVs.
- [docs/PYTHON_STYLE.md](docs/PYTHON_STYLE.md): Python conventions enforced in this repo.
- [docs/REPO_STYLE.md](docs/REPO_STYLE.md): repo-wide layout, naming, and changelog rules.
- [docs/CHANGELOG.md](docs/CHANGELOG.md): dated change history.

## Project layout

- `protein_image_grader/`: Python package (downloader, grader, email sender, orchestrator).
- `tools/`: repo-wide utilities (e.g. `log_image_hashes.py`).
- `local_migrations/`: one-shot migration scripts.
- `spec_yaml_files/common_image_questions.yml`: shared image questions.
- `image_hashes.yml`: cheat-detection hash database (tracked in git).

## Testing

```
source source_me.sh && pytest tests/
```
