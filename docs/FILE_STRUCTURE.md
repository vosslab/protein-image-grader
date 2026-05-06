# File structure

## Top level
- `start_grading.py`: orchestrator for download/grade/email workflows
- `image_hashes.yml`: cheat detection database (tracked in git)
- `Protein_Images/`: external data root (not in git; symlink or mount)
- `tools/`: executable maintenance scripts (human-run)

## Package code
- `protein_image_grader/`: core modules used by start_grading.py

## Protein_Images structure (external root, not tracked)
```
Protein_Images/
  active_term.txt                           # current term (e.g., spring_2026)
  semesters/
    <term>/                                 # e.g., spring_2026
      forms/
        BCHM_Prot_Img_NN-*.csv             # form submissions
      roster.csv                            # student roster for the term
      email_log.yml                         # per-image email status log
      <image_dir>/                          # e.g., BCHM_Prot_Img_04_Active_Site
        raw/                                # downloaded raw images (working copy)
          <RUID>-proteinNN-*.png           # original images from Google Drive
        trim/                               # trimmed/rotated versions (if --trim)
          <RUID>-proteinNN-*-trim.jpg      # processed for display
        output-protein_image_NN.yml         # grading results (after review)
        output-protein_image_NN.csv         # student grades and scores
        blackboard_upload-protein_image_NN.csv
        profiles_image_NN.html              # review interface (generated)
  image_bank/                               # canonical archive (cross-year plagiarism)
    <term>/
      <image_dir>/
        raw/                                # archived raw images
          <RUID>-proteinNN-*.png
        trim/                               # archived trimmed images
          <RUID>-proteinNN-*-trim.jpg

## Path resolution
- `protein_image_grader/protein_images_path.py` centralizes all Protein_Images/ path logic.
- `protein_image_grader/archive_paths.py` normalizes archive paths for hashing.
- `local_migrations/migrate_image_bank_to_terms.py` migrates flat image_bank/ to term-organized layout.
- `tools/log_image_hashes.py` rebuilds the cheat detection database from archive sources.
