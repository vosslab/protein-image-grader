# RUID Policy

This repo handles two RUIDs for every student submission. Treat them differently.

## The two RUIDs

| Source | What it is | Trust |
| --- | --- | --- |
| Form RUID | The 9-digit number the student typed into the Google Form. | UNTRUSTED |
| Roster RUID | The 9-digit number in `Protein_Images/semesters/<term>/roster.csv`, joined to the student by name. | AUTHORITATIVE |

The Form RUID is whatever the student typed at submission time. Students transpose digits, copy a friend's number, paste their NetID, or guess. The Roster RUID is the registrar's record and is the only RUID that is correct for grade entry, Blackboard upload, and de-duplication.

## The rule

**When writing files to disk that include an RUID in the filename, always use the Roster RUID, never the Form RUID.** This applies to:

- `Protein_Images/semesters/<term>/submissions/download_NN_raw/<RUID>-protein NN-...`
- `archive/<term>/image_bank/<assignment>/<RUID>-protein NN-...`
- `Protein_Images/semesters/<term>/grades/output-protein_image_NN.csv` (Student ID column)
- `Protein_Images/semesters/<term>/grades/blackboard_upload-protein_image_NN.csv`
- HTML profile pages (`profiles_image_NN.html`) shown during review.

## How the resolution works

For each form row, the pipeline:

1. Reads the Form RUID from the row's "Student ID" / "RUID" cell.
2. Reads the student's name fields (First Name, Last Name, Full Name).
3. Looks up the row in `roster.csv` via `protein_image_grader.roster_matching.RosterMatcher`:
   - If the Form RUID is on the roster, use that row.
   - Else match by `name_exact` (score 1.0) on first + last name.
   - Else match by `username` (NetID/email local part).
   - Else fuzzy-match with a confidence score; below `auto_threshold` falls into interactive review.
4. The resolved Roster RUID is used to format every on-disk filename and every CSV column.

If resolution fails (no roster hit, ambiguous fuzzy match, manual reject), the row is **quarantined**: its image is not saved into `download_NN_raw/` under a typed RUID. Either the operator re-runs after fixing the roster, or the file is staged into a `download_NN_unresolved/` sibling for manual triage. The `output-protein_image_NN.csv` row for that student stays empty.

## Audit trail

The Form RUID is preserved per row, but never as a filename. Specifically:

- `output-protein_image_NN.csv` carries both `Student ID` (Roster RUID, authoritative) and `Form RUID` (typed value, audit only).
- `Protein_Images/semesters/<term>/ruid_aliases.yml` records every `typed_ruid -> resolved_ruid` mapping with the match score and the date it was resolved. Re-runs read this first and skip the matcher when an alias is already on file.
- The `WARNING OVERWRITING Student ID` log in `student_id_protein.merge_student_records` only fires when a brand-new alias is being recorded; re-runs are silent.

## Why this matters

- **Grade entry.** Blackboard rejects rows whose `Student ID` does not match the registrar's record. A wrong Form RUID silently drops the student's score.
- **De-duplication.** The same student may submit twice with two different typed RUIDs; if filenames key on the typed value, the duplicate looks like two students. Keying on the Roster RUID collapses them.
- **Roster reconciliation.** The roster is the only file we re-export for university systems. Anything keyed on a non-roster RUID has to be remapped before it leaves the lab.

## See also

- [docs/INPUT_FORMATS.md](docs/INPUT_FORMATS.md) - form CSV columns the matcher reads.
- `protein_image_grader/roster_matching.py` - the matcher implementation.
- `protein_image_grader/student_id_protein.py` - orchestrator that calls the matcher.
- `protein_image_grader/download_submission_images.py` - the saver that consumes the resolved RUID.
