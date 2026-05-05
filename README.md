# protein-image-grader
Grading system for biochemistry protein images.

## External data
The grader requires a `Protein_Images/` directory at the repo root. This is a user-supplied symlink to a Synology-synced folder containing years of student submissions, rosters, form exports, and the archive image bank. It is never tracked in git and is not regenerable.

Create the symlink once on a new machine:

```
ln -s /path/to/your/Protein_Images Protein_Images
```

The active term will be set explicitly in `Protein_Images/active_term.txt` (one line, e.g. `spring_2026`). The grader and tools will accept a `--term` override flag for regrading older semesters; there is no date-based auto-detection.

Planned canonical layout under `Protein_Images/` (target end state; migration not yet applied):

```
Protein_Images/
+-- active_term.txt
+-- archive_images/
+-- semesters/
|   +-- <term>/
|       +-- roster.csv
|       +-- forms/
|       +-- yaml/
|       +-- grades/
|       +-- submissions/
+-- legacy/
    +-- needs_review/
```

For first-time setup on a Synology folder that still uses the legacy mixed-case layout, see the migration tool:

```
python local_migrations/protein_images/migrate_protein_images.py --help
```

The migration tool is dry-run by default and only moves or renames files inside `Protein_Images/`; it never deletes data. Low-confidence items are routed to `Protein_Images/legacy/needs_review/` for human review. The migration has not yet been applied to the real `Protein_Images/`.

Credentials (`api_file.json`, `service_key.json`) will live at `~/.config/bchm_355/credentials/`, not inside `Protein_Images/`.

## Quick start
- Install dependencies from `pip_requirements.txt`.
- Put assignment specs in `spec_yaml_files/`.
- Put roster data in `current_students.csv` at the repo root.
- Drop the assignment CSV in the repo root or `data/runs/`.
- Run `python3 grade_protein_image.py -i <image_number>`.
- After grading, run `python3 send_feedback_email.py -i <image_number>`.

## Project layout
- `spec_yaml_files/` holds assignment spec YAML files.
- `spec_yaml_files/common_image_questions.yml` holds shared image questions.
- `data/inputs/` holds templates and optional inputs.
- `data/runs/` holds generated grading outputs.
- `archive/` holds the cheat detection hash database and archive images (images ignored by git).

## Docs
- Usage details: [docs/USAGE.md](docs/USAGE.md)
- File layout: [docs/FILE_STRUCTURE.md](docs/FILE_STRUCTURE.md)
- Change history: [docs/CHANGELOG.md](docs/CHANGELOG.md)
