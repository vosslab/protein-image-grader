# RUID Policy

This repo handles two RUIDs for every student submission. Treat them differently.

## RUID format

Roosevelt University RUIDs are always **9 digits**. By rule:

- Current students: 9 digits starting with `900...`
- Older students: 9 digits starting with `960...`

Anything else (8 digits, 10 digits, leading zeros, alpha characters, NetID-like
strings) is invalid and must be rejected or quarantined. The downloader uses
this prefix rule as a fallback when the form CSV has no explicit Student-ID
column: a cell whose stripped value starts with `900` or `960` is treated as
the typed Form RUID candidate. Resolution against `roster.csv` still applies
to the candidate before any filename is written.

The Google Form already validates the typed RUID for **shape** (9 digits,
starts with `9`). What the Form **cannot** check is whether the RUID actually
matches a student on the roster: a 9-digit number that follows the format
rule but belongs to no real student, or to a different student than the one
filling in the form, passes Google's check and lands in the form CSV
unchanged. The Roster-RUID resolution in this repo exists precisely to catch
that gap. Trust nothing about the typed RUID beyond its shape until
`roster_matching.RosterMatcher` confirms it against `roster.csv`.

## The two RUIDs

| Source | What it is | Trust |
| --- | --- | --- |
| Form RUID | The 9-digit number the student typed into the Google Form. | UNTRUSTED |
| Roster RUID | The 9-digit number in `Protein_Images/semesters/<term>/roster.csv`, joined to the student by name. | AUTHORITATIVE |

The Form RUID is whatever the student typed at submission time. Students transpose digits, copy a friend's number, paste their NetID, or guess. The Roster RUID is the registrar's record and is the only RUID that is correct for grade entry, Blackboard upload, and de-duplication.

## The rule

**When writing files to disk that include an RUID in the filename, always use the Roster RUID, never the Form RUID.** This applies to:

- `Protein_Images/semesters/<term>/<image_dir>/raw/<RUID>-protein NN-...`
- `Protein_Images/semesters/<term>/<image_dir>/trim/<RUID>-protein NN-...-trim.jpg`
- `Protein_Images/image_bank/<term>/<image_dir>/{raw,trim}/<RUID>-protein NN-...`
- `Protein_Images/semesters/<term>/<image_dir>/output-protein_image_NN.csv` (Student ID column)
- `Protein_Images/semesters/<term>/<image_dir>/blackboard_upload-protein_image_NN.csv`
- HTML profile pages (`profiles_image_NN.html`) shown during review.

## How the resolution works

The single resolver lives in `protein_image_grader/ruid_resolver.py` --
one function, `resolve_form_row_to_roster_row`, plus the
`ResolvedStudent` and `UnresolvedStudent` result dataclasses. Both the
downloader (`download_submission_images.py`, non-interactive: quarantine
on miss) and the grader (`student_id_protein.match_lists_and_add_student_ids`,
interactive: raise on miss) call the same function with the same matcher
and per-run `assigned_ruids` set. One resolver, two consumers.

For each form row, the pipeline:

1. Reads the Form RUID from the row's "Student ID" / "RUID" cell.
2. Reads the student's name fields (First Name, Last Name, Full Name).
3. Looks up the row in `roster.csv` via `protein_image_grader.roster_matching.RosterMatcher`:
   - If the Form RUID is on the roster, use that row.
   - Else match by `name_exact` (score 1.0) on first + last name.
   - Else match by `username` (NetID/email local part).
   - Else fuzzy-match with a confidence score; below `auto_threshold` falls into interactive review.
4. The resolved Roster RUID is used to format every on-disk filename and every CSV column.

If resolution fails (no roster hit, ambiguous fuzzy match, manual reject), the row is **quarantined**: its image is not saved into the working directory under a typed RUID. Either the operator re-runs after fixing the roster, or the file is staged into a manual triage folder for review. The `output-protein_image_NN.csv` row for that student stays empty.

## Audit trail

The Form RUID is preserved per row, but never as a filename. Specifically:

- `output-protein_image_NN.csv` carries both `Student ID` (Roster RUID, authoritative) and `Form RUID` (typed value, audit only).
- `Protein_Images/semesters/<term>/forms/quarantine.log` records every form row whose Form RUID could not be resolved against the roster, including the top roster candidates the matcher considered. No image is saved for quarantined rows; the operator fixes the roster (or the form CSV) and re-runs.
- The `WARNING OVERWRITING Student ID` log in `student_id_protein.merge_student_records` fires whenever the grader replaces a typed Form RUID with the resolved Roster RUID.

## Why this matters

- **Grade entry.** Blackboard rejects rows whose `Student ID` does not match the registrar's record. A wrong Form RUID silently drops the student's score.
- **De-duplication.** The same student may submit twice with two different typed RUIDs; if filenames key on the typed value, the duplicate looks like two students. Keying on the Roster RUID collapses them.
- **Roster reconciliation.** The roster is the only file we re-export for university systems. Anything keyed on a non-roster RUID has to be remapped before it leaves the lab.

## See also

- [INPUT_FORMATS.md](INPUT_FORMATS.md) - form CSV columns the matcher reads.
- `protein_image_grader/roster_matching.py` - the generic fuzzy-matching engine (`RosterMatcher` + `match_submission`).
- `protein_image_grader/ruid_resolver.py` - one function (`resolve_form_row_to_roster_row`) that wraps `RosterMatcher` with the project-specific shape: per-run duplicate guard and triage-grade `ResolvedStudent` / `UnresolvedStudent` return.
- `protein_image_grader/student_id_protein.py` - grading orchestrator; calls `resolve_form_row_to_roster_row` inside `match_lists_and_add_student_ids`.
- `protein_image_grader/download_submission_images.py` - the saver that calls the resolver before writing any RUID-bearing filename.
