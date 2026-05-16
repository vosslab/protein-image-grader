"""
Single entry point for protein image grading workflow.

Auto-imports stray repo-root form CSVs into the canonical
Protein_Images/semesters/<term>/forms/ directory, prints a per-image
status dashboard, and shells out to download_submission_images.py or
grade_protein_image.py for one image at a time. Never batch-grades.
"""

# Standard Library
import os
import csv
import sys
import shutil
import pathlib
import argparse
import tempfile
import subprocess

# PIP3 modules
import tabulate

# local repo modules
import protein_image_grader.email_log as email_log
import protein_image_grader.csv_compare as csv_compare
import protein_image_grader.ruid_resolver as ruid_resolver
import protein_image_grader.form_columns as form_columns
import protein_image_grader.grade_status as grade_status
import protein_image_grader.archive_paths as archive_paths
import protein_image_grader.roster_matching as roster_matching
import protein_image_grader.protein_images_path as protein_images_path


EXPECTED_IMAGE_NUMBERS = tuple(range(1, 11))
STEP_CHOICES = ("grade", "regrade", "email")
DOWNLOAD_SCRIPT = "download_submission_images.py"
GRADE_SCRIPT = "grade_protein_image.py"
EMAIL_SCRIPT = "send_feedback_email.py"
BB_ASSIGNMENT_IDS_FILENAME = "blackboard_assignment_ids.txt"


#============================================
def parse_args():
	"""
	Parse command-line arguments.
	"""
	description = "Status dashboard and orchestrator for protein image grading."
	parser = argparse.ArgumentParser(description=description)
	parser.add_argument('-t', '--term', dest='term', type=str, default=None,
		help="Active term, e.g. spring_2026 (defaults to active_term.txt).")
	parser.add_argument('-i', '--image', dest='image_number', type=int,
		default=None, help="Protein image number, 1-10.")
	parser.add_argument('-s', '--step', dest='step', type=str,
		choices=STEP_CHOICES, default=None,
		help="Action to run for the chosen image.")
	parser.add_argument('--status-only', dest='status_only',
		action='store_true', help="Print the dashboard and exit.")
	args = parser.parse_args()
	return args


#============================================
def find_repo_root_form_csvs() -> list:
	"""
	Return a sorted list of BCHM_Prot_Img_##-*.csv files at the repo root.
	"""
	repo_root = pathlib.Path(archive_paths.get_repo_root())
	matches = sorted(repo_root.glob("BCHM_Prot_Img_*.csv"))
	return matches


#============================================
def find_canonical_form_csvs(term: str) -> dict:
	"""
	Thin wrapper around protein_images_path.find_canonical_form_csvs so this
	module's existing callers keep working. The shared helper is the source
	of truth for canonical form-CSV lookup.
	"""
	return protein_images_path.find_canonical_form_csvs(term)


#============================================
def replace_file_cross_device(src: pathlib.Path, dst: pathlib.Path) -> None:
	"""
	Replace `dst` with `src`, then remove `src`.

	The final os.replace call must use a temporary file in dst.parent so
	the overwrite stays atomic even when `src` lives on another filesystem.
	"""
	fd, tmp_path = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp",
		dir=str(dst.parent))
	try:
		os.close(fd)
		shutil.copy2(src, tmp_path)
		os.replace(tmp_path, dst)
		os.unlink(src)
	except Exception:
		if os.path.exists(tmp_path):
			os.unlink(tmp_path)
		raise


#============================================
def auto_import_repo_root_csvs(term: str) -> list:
	"""
	Move repo-root BCHM_Prot_Img_##-*.csv files into the canonical forms
	directory for `term`. Returns one record per source file as
	[(src_path, dst_path, action), ...] where action is one of
	"moved", "identical", or "replaced".

	Filesystem move only (shutil.move or destination-local replace).
	Protein_Images/ is gitignored, so `git mv` would be wrong here.

	Collision policy (when a destination already exists):
	  - byte-identical (SHA-256 match) -> delete the root copy silently
	    with a "+ identical" notice; action="identical".
	  - strict keyed superset (every shared (Student ID, timestamp)
	    key has byte-identical row content; candidate may add more) ->
	    overwrite canonical via destination-local os.replace;
	    action="replaced".
	  - any other divergence (header drift, removed key, changed cells,
	    duplicate key) -> raise FileExistsError naming the specific
	    reason.
	"""
	root_csvs = find_repo_root_form_csvs()
	if not root_csvs:
		return []
	forms_dir = protein_images_path.get_forms_dir(term)
	forms_dir.mkdir(parents=True, exist_ok=True)
	results = []
	for src in root_csvs:
		dst = forms_dir / src.name
		if not dst.exists():
			print(f"+ move {src.name} -> {dst}")
			shutil.move(str(src), str(dst))
			results.append((src, dst, "moved"))
			continue
		# Collision -- decide by content.
		if csv_compare.hash_csv(src) == csv_compare.hash_csv(dst):
			print(f"+ identical, removed root copy {src.name}")
			os.unlink(src)
			results.append((src, dst, "identical"))
			continue
		ok, reason, added = csv_compare.is_strict_form_superset(dst, src)
		if ok:
			print(f"+ superset, replaced canonical {src.name} ({reason})")
			replace_file_cross_device(src, dst)
			results.append((src, dst, "replaced"))
			continue
		message = (
			f"ERROR: cannot import {src}; destination already exists\n"
			f"  and the new file is not a strict keyed superset of:\n"
			f"  {dst}\n"
			f"  reason: {reason}\n"
			"Resolve the divergence manually before re-running."
		)
		raise FileExistsError(message)
	return results


#============================================
def detect_canonical_duplicates(term: str) -> dict:
	"""
	Return {image_number: [csv_paths]} for every image number that has 2+
	canonical CSVs. Empty dict means no duplicates.
	"""
	by_image = find_canonical_form_csvs(term)
	dups = {}
	for number, paths in by_image.items():
		if len(paths) >= 2:
			dups[number] = paths
	return dups




#============================================
def _row_value(row: list, idx: int | None) -> str:
	"""
	Return one CSV cell, or empty string when the row is short.
	"""
	if idx is None or len(row) <= idx:
		return ""
	value = row[idx].strip()
	return value


#============================================
def count_form_records(canonical_csv: pathlib.Path, term: str | None = None) -> int:
	"""
	Return the number of unique submitters in `canonical_csv`.

	Uses form_columns.resolve_meta_columns(required={"Student ID"}) to
	locate the Student-ID column; the form CSV may put it anywhere in
	the first IDENTITY_PREFIX_COLUMNS header cells. Duplicate Student
	IDs are resubmissions; the grader keeps only the newest row per
	student, so the dashboard comparison must count unique students too.
	"""
	with open(canonical_csv, "r", encoding="utf-8", newline="") as handle:
		reader = csv.reader(handle)
		all_rows = list(reader)
	if not all_rows:
		return 0
	header = all_rows[0]
	resolved = form_columns.resolve_meta_columns(header,
		required={"Student ID"})
	id_idx = resolved["Student ID"]
	student_ids: set = set()
	matcher = None
	if term is not None:
		roster_csv = protein_images_path.get_roster_csv(term)
		if roster_csv.is_file():
			roster = roster_matching.read_roster(str(roster_csv))
			matcher = roster_matching.RosterMatcher(
				roster=roster,
				interactive=False,
				auto_threshold=0.90,
				auto_gap=0.06,
				candidate_count=5,
			)
	username_idx = resolved.get("Username")
	first_idx = resolved.get("First Name")
	last_idx = resolved.get("Last Name")
	for row in all_rows[1:]:
		if len(row) <= id_idx:
			continue
		student_id = _row_value(row, id_idx)
		if student_id:
			if matcher is not None:
				form_row = {
					"form_ruid": student_id,
					"first_name": _row_value(row, first_idx),
					"last_name": _row_value(row, last_idx),
					"username": _row_value(row, username_idx),
				}
				result = ruid_resolver.resolve_form_row_to_roster_row(
					form_row, matcher, set(),
				)
				if isinstance(result, ruid_resolver.ResolvedStudent):
					student_id = str(result.roster_ruid)
			student_ids.add(student_id)
	count = len(student_ids)
	return count


#============================================
def is_non_empty_dir(path: pathlib.Path) -> bool:
	if not path.is_dir():
		return False
	for _ in path.iterdir():
		return True
	return False


#============================================
def build_status_row(image_number: int, term: str,
		canonical_csvs: dict) -> dict:
	"""
	Build one dashboard row for the given image number. Inspects path
	existence/non-emptiness and -- when the form CSV and graded output
	both exist -- compares record counts so the `graded` column can
	flip to PARTIAL on a fresh re-import that added new submissions.

	New layout: uses per-image folders under semesters/<term>/<image_dir>/.
	"""
	csv_matches = canonical_csvs.get(image_number, [])
	if len(csv_matches) == 0:
		form_status = "MISSING"
	elif len(csv_matches) >= 2:
		form_status = "DUPLICATE"
	else:
		form_status = "OK"

	# Resolve per-image folder once; if missing or ambiguous, every dependent
	# status defaults to MISSING.
	try:
		image_dir = protein_images_path.get_term_image_dir(term, image_number)
	except (FileNotFoundError, RuntimeError):
		image_dir = None

	form_count = None
	graded_count = None
	# Checkpoint metadata for footer warnings: which file was picked,
	# how many candidates exist, and -- on conflict -- the reason. The
	# dashboard never prompts; ambiguity surfaces as footer text.
	checkpoint_label = None
	checkpoint_candidates: list = []
	checkpoint_conflict_reason = None
	if image_dir is None:
		downloaded_status = "MISSING"
		graded_status = "MISSING"
		bb_status = "MISSING"
	else:
		downloaded_status = "OK" if is_non_empty_dir(image_dir / "raw") else "MISSING"
		bb_csv = image_dir / f"blackboard_upload-protein_image_{image_number:02d}.csv"
		bb_status = "OK" if bb_csv.is_file() else "MISSING"
		# YAML is the source of truth for graded records (CSV is just
		# the export). Use the deepest valid checkpoint from the
		# canonical catalog; on parse / validation failure the row goes
		# CONFLICT so the operator can repair the file.
		pick_result = grade_status.pick_checkpoint(image_dir, image_number)
		checkpoint_candidates = [hit.path for hit in pick_result.candidates]
		if pick_result.conflict:
			graded_status = "CONFLICT"
			checkpoint_conflict_reason = pick_result.conflict_reason
		elif pick_result.chosen is None:
			graded_status = "MISSING"
		else:
			checkpoint_label = pick_result.label
			graded_count = grade_status.count_graded_students_from_yaml(
				pick_result.chosen
			)
			if graded_count == 0:
				graded_status = "MISSING"
			elif form_status == "OK":
				form_count = count_form_records(csv_matches[0], term)
				# Strict less-than -> PARTIAL. Equal stays OK.
				# More-graded-than-form is handled in
				# render_footer_warnings as a stale-output warning.
				if graded_count < form_count:
					graded_status = "PARTIAL"
				else:
					graded_status = "OK"
			else:
				# Form CSV missing or duplicate -- we cannot decide
				# OK / PARTIAL without it, so default OK on the count.
				graded_status = "OK"

	emailed_status = compute_emailed_status(term, image_number, graded_status)

	next_step = compute_next_step(form_status, downloaded_status,
		graded_status, bb_status, emailed_status=emailed_status)

	row = {
		"image": f"{image_number:02d}",
		"form": form_status,
		"downloaded": downloaded_status,
		"graded": graded_status,
		"emailed": emailed_status,
		"bb_upload": bb_status,
		"next_step": next_step,
		"form_count": form_count,
		"graded_count": graded_count,
		"checkpoint_label": checkpoint_label,
		"checkpoint_candidates": checkpoint_candidates,
		"checkpoint_conflict_reason": checkpoint_conflict_reason,
	}
	return row


#============================================
def compute_emailed_status(term: str, image_number: int,
		graded_status: str) -> str:
	"""
	Compute the dashboard 'Emailed' column for one image.

	Returns "MISSING" when grading has not happened yet (nothing to email)
	or when the roster CSV is absent. Otherwise delegates to
	email_log.summarize_image with the Student IDs taken from the per-term
	`roster.csv`. Closing the cell to "OK" therefore requires every roster
	Student ID to have status `sent` (real feedback) or
	`no_submission_sent` (no-submission notice). The graded YAML is no
	longer the source of expected IDs; submitters are a subset of the
	roster, and the email step now also covers non-submitters.
	"""
	if graded_status != "OK":
		return "MISSING"
	try:
		roster_csv = protein_images_path.get_roster_csv(term)
	except (FileNotFoundError, RuntimeError):
		return "MISSING"
	if not roster_csv.is_file():
		return "MISSING"
	roster = roster_matching.read_roster(str(roster_csv))
	if not roster:
		return "MISSING"
	expected_ids = [str(student_id) for student_id in roster.keys()]
	data = email_log.load(term)
	return email_log.summarize_image(data, image_number, expected_ids)


#============================================
def compute_next_step(form_status: str, downloaded_status: str,
		graded_status: str, bb_status: str,
		emailed_status: str = "MISSING") -> str:
	"""
	Pick the most useful next action verb for one image row.

	emailed_status is keyword-only with a default so older callers passing
	four positional values keep working. After grading is done, the next
	action is 'email' until every expected student has status 'sent' in
	the per-term email log.
	"""
	if form_status == "DUPLICATE":
		return "fix duplicate CSV"
	if form_status == "MISSING":
		return "add form CSV"
	# Checkpoint conflict (parse failure, validation failure, or
	# same-rank duplicate) needs operator triage before any action step
	# can run. Surface a manual-fix verb instead of routing to grade.
	if graded_status == "CONFLICT":
		return "fix checkpoint"
	# Download is non-interactive, so it is folded into the grade step:
	# whenever the form CSV is OK but grading has not happened, the next
	# action is "grade" (which auto-downloads first if needed).
	if graded_status == "MISSING":
		return "grade"
	# PARTIAL graded means the form CSV grew (late submission) and the
	# output CSV no longer covers every row. grade_protein_image.py is
	# idempotent on already-graded students, so route to "regrade".
	if graded_status == "PARTIAL":
		return "regrade"
	if graded_status != "OK":
		return "grade"
	# Graded already; email feedback before treating the image as done.
	if emailed_status != "OK":
		return "email"
	# Suggest regrade if late submissions might exist.
	if bb_status != "OK":
		return "regrade or upload"
	return "done"


#============================================
def render_dashboard(term: str) -> str:
	"""
	Build the dashboard string for the term. Caller prints it.
	"""
	canonical_csvs = find_canonical_form_csvs(term)
	rows = [build_status_row(n, term, canonical_csvs)
		for n in EXPECTED_IMAGE_NUMBERS]
	headers = ["Image", "Form CSV", "Downloaded", "Graded",
		"Emailed", "BB upload", "Next step"]
	table_rows = [
		[r["image"], r["form"], r["downloaded"], r["graded"],
			r["emailed"], r["bb_upload"], r["next_step"]]
		for r in rows
	]
	output = ""
	output += render_header_banner(term)
	output += "\n"
	output += tabulate.tabulate(table_rows, headers=headers,
		tablefmt="simple")
	output += "\n"
	output += render_footer_warnings(term, rows=rows)
	return output


#============================================
def render_header_banner(term: str) -> str:
	"""
	One-line-per-resource header showing which canonical files exist.
	"""
	roster = protein_images_path.get_roster_csv(term)
	bb_ids = protein_images_path.get_term_dir(term) / BB_ASSIGNMENT_IDS_FILENAME
	forms = protein_images_path.get_forms_dir(term)

	lines = []
	lines.append(f"Term: {term}")
	lines.append(f"  forms dir: {_path_status(forms, want='dir')} {forms}")
	lines.append(f"  roster:    {_path_status(roster, want='file')} {roster}")
	lines.append(f"  bb ids:    {_path_status(bb_ids, want='file')} {bb_ids}")
	return "\n".join(lines) + "\n"


#============================================
def _path_status(path: pathlib.Path, want: str) -> str:
	if want == "dir" and path.is_dir():
		return "[OK]     "
	if want == "file" and path.is_file():
		return "[OK]     "
	return "[MISSING]"


#============================================
def render_footer_warnings(term: str, rows: list = None) -> str:
	"""
	Print warnings that do not belong inside the table.

	When `rows` is provided (the per-image dashboard rows produced by
	build_status_row), also emit one line per image whose graded
	status is PARTIAL with the form/graded record counts, and a
	stale-output warning when graded_count > form_count.
	"""
	parts = []
	if rows:
		count_lines = []
		for r in rows:
			form_count = r["form_count"]
			graded_count = r["graded_count"]
			if form_count is None or graded_count is None:
				continue
			if r["graded"] == "PARTIAL":
				count_lines.append(
					f"image {r['image']}: {form_count} form records, "
					f"{graded_count} graded records"
				)
			elif graded_count > form_count:
				count_lines.append(
					f"image {r['image']}: {graded_count} graded records "
					f"exceed {form_count} form records (stale output?)"
				)
		if count_lines:
			parts.append("\n".join(count_lines))

		# Multi-checkpoint advisory: only warn when the chosen file is
		# NOT the final `output-protein_image_NN.yml`. When `output`
		# is on disk, the shallower `*_save.yml` files are normal
		# scaffolding written during a successful run and are not
		# stale state -- listing them every dashboard refresh is just
		# noise. Skip CONFLICT rows too; the CONFLICT line names the
		# offending file directly.
		multi_lines = []
		for r in rows:
			if r["graded"] == "CONFLICT":
				continue
			# .get() because some test rows are hand-built without
			# this key; build_status_row always sets it for real
			# callers. Treat missing as "not output" (advisory still
			# fires for the suspicious case).
			if r.get("checkpoint_label") == "output":
				continue
			candidates = r.get("checkpoint_candidates", [])
			if len(candidates) <= 1:
				continue
			chosen_name = candidates[0].name
			others = ", ".join(p.name for p in candidates[1:])
			multi_lines.append(
				f"image {r['image']}: using {r['checkpoint_label']} "
				f"checkpoint {chosen_name}; also found: {others}"
			)
		if multi_lines:
			parts.append("\n".join(multi_lines))

		# CONFLICT lines name the offending file and the parser /
		# validation reason. Regrade will refuse to run for these
		# images until the operator deletes or repairs the file.
		conflict_lines = []
		for r in rows:
			if r["graded"] != "CONFLICT":
				continue
			reason = r.get("checkpoint_conflict_reason") or "unknown"
			conflict_lines.append(
				f"image {r['image']}: CHECKPOINT CONFLICT: {reason}"
			)
		if conflict_lines:
			parts.append("\n".join(conflict_lines))
	root_csvs = find_repo_root_form_csvs()
	if root_csvs:
		# Only happens if auto-import was skipped or failed earlier.
		parts.append(
			f"WARNING: {len(root_csvs)} repo-root form CSV(s) still present.\n"
			f"  These should have been auto-moved into:\n"
			f"    {protein_images_path.get_forms_dir(term)}"
		)
	if not protein_images_path.get_forms_dir(term).is_dir():
		parts.append(
			"ERROR: forms dir missing for this term.\n"
			f"  Expected: {protein_images_path.get_forms_dir(term)}"
		)
	dups = detect_canonical_duplicates(term)
	if dups:
		dup_lines = ["DUPLICATE form CSVs detected (resolve before grading):"]
		for image_number, paths in sorted(dups.items()):
			dup_lines.append(f"  image {image_number:02d}:")
			for p in paths:
				dup_lines.append(f"    {p}")
		parts.append("\n".join(dup_lines))
	if not parts:
		return ""
	return "\n" + "\n\n".join(parts) + "\n"


#============================================
def resolve_canonical_csv(term: str, image_number: int) -> pathlib.Path:
	"""
	Return the single canonical form CSV for (term, image_number).

	Raises FileNotFoundError if missing; ValueError if duplicates.
	"""
	canonical_csvs = find_canonical_form_csvs(term)
	matches = canonical_csvs.get(image_number, [])
	if len(matches) == 0:
		forms_dir = protein_images_path.get_forms_dir(term)
		raise FileNotFoundError(
			f"No canonical form CSV for image {image_number:02d} in {forms_dir}"
		)
	if len(matches) >= 2:
		listing = "\n".join(f"  {p}" for p in matches)
		raise ValueError(
			f"Multiple canonical form CSVs for image {image_number:02d}:\n{listing}"
		)
	return matches[0]


#============================================
def build_download_command(canonical_csv: pathlib.Path) -> list:
	"""
	Construct the argv list to invoke download_submission_images.py.
	After Phase 0 the downloader infers its own output dir from the
	canonical CSV path; we do not pass --output-dir here.
	"""
	# --trim and --rotate are on by default through the orchestrator so
	# the per-image HTML (`protein_images_NN.html`) shows the raw image
	# next to the trimmed/rotated copy.
	return [
		sys.executable, DOWNLOAD_SCRIPT,
		"-i", str(canonical_csv),
		"--trim",
		"--rotate",
	]


#============================================
def build_grade_command(image_number: int, term: str,
		yaml_backup_file: pathlib.Path | None = None) -> list:
	"""
	Construct the argv list to invoke grade_protein_image.py for one image.

	When `yaml_backup_file` is provided, append `--yaml-backup-file <path>`
	so the grader resumes from that checkpoint via its existing flag.
	Existing callers that omit the keyword get the wholesale grade command
	unchanged.
	"""
	command = [
		sys.executable, GRADE_SCRIPT,
		"-i", str(image_number),
		"--term", term,
	]
	if yaml_backup_file is not None:
		command.extend(["--yaml-backup-file", str(yaml_backup_file)])
	return command


#============================================
def build_email_command(image_number: int, term: str) -> list:
	"""
	Construct the argv list to invoke send_feedback_email.py for one image.

	Never passes -e/--send-email; the operator must promote a real send by
	calling send_feedback_email.py directly with -e.
	"""
	return [
		sys.executable, EMAIL_SCRIPT,
		"-i", str(image_number),
		"--term", term,
	]


#============================================
def confirm_overwrite(prompt: str, default_yes: bool = False) -> bool:
	"""
	Ask y/N. Default is N unless `default_yes` is True (then Y).
	Always interactive; no --yes bypass flag.

	Args:
		prompt: Body of the question, without the trailing "[y/N]".
		default_yes: When True, an empty answer means yes and the
			tag shows as "[Y/n]". Use this for low-risk regrades
			where the existing output is known to be a stale subset
			of the form CSV.
	"""
	suffix = "[Y/n]" if default_yes else "[y/N]"
	answer = input(f"{prompt} {suffix} ").strip().lower()
	if not answer:
		return default_yes
	return answer == "y" or answer == "yes"


#============================================
def require_resources(term: str, step: str) -> None:
	"""
	Enforce required-resource hierarchy for an action step.
	"""
	forms_dir = protein_images_path.get_forms_dir(term)
	if not forms_dir.is_dir():
		raise FileNotFoundError(
			f"forms dir missing for {term}: {forms_dir}"
		)
	if step in ("grade", "regrade", "email"):
		roster = protein_images_path.get_roster_csv(term)
		if not roster.is_file():
			raise FileNotFoundError(
				f"roster.csv missing for {term}: {roster}"
			)
	# blackboard_assignment_ids.txt is warning-only in v1.
	bb_ids = protein_images_path.get_term_dir(term) / BB_ASSIGNMENT_IDS_FILENAME
	if not bb_ids.is_file():
		print(f"WARNING: {bb_ids.name} not found at {os.path.relpath(bb_ids)} "
			"(upload not implemented yet; ignoring).")


#============================================
def run_step(term: str, image_number: int, step: str) -> int:
	"""
	Execute one step for one image. Returns the child's exit code.

	New layout: uses per-image folders under semesters/<term>/<image_dir>/.
	"""
	require_resources(term, step)
	canonical_csv = resolve_canonical_csv(term, image_number)

	if step == "grade":
		# Download is non-interactive, so auto-run it when the canonical
		# raw/ subdir for this image is empty/missing. Existing non-empty
		# downloads are kept as-is (no overwrite prompt) so re-runs do not
		# re-fetch hundreds of images.
		image_dir = protein_images_path.get_term_image_dir(term, image_number)
		image_raw_dir = image_dir / "raw"
		if not is_non_empty_dir(image_raw_dir):
			download_command = build_download_command(canonical_csv)
			download_command_string = " ".join(download_command)
			print(f"+ {download_command_string}")
			download_result = subprocess.run(download_command)
			if download_result.returncode != 0:
				return download_result.returncode
		command = build_grade_command(image_number, term)
		graded_csv = image_dir / f"output-protein_image_{image_number:02d}.csv"
		if graded_csv.is_file():
			ok = confirm_overwrite(
				f"Existing grade output found:\n  {graded_csv}\n"
				f"Regrade and overwrite?"
			)
			if not ok:
				print("Aborted.")
				return 1
	elif step == "regrade":
		image_dir = protein_images_path.get_term_image_dir(term, image_number)
		# Auto-resume: pick the deepest valid checkpoint by precedence and
		# pass its path through the existing --yaml-backup-file flag. If
		# pick_checkpoint reports a conflict (parse failure, validation
		# failure, or true same-rank duplicate) we abort non-zero so the
		# operator can inspect / repair the offending file.
		pick_result = grade_status.pick_checkpoint(image_dir, image_number)
		if pick_result.conflict:
			print(
				f"Cannot regrade image {image_number:02d}: checkpoint conflict.\n"
				f"  Reason: {pick_result.conflict_reason}\n"
				"  Fix the file (delete or repair) and re-run."
			)
			candidate_paths = [os.path.relpath(hit.path) for hit in pick_result.candidates]
			print("  Candidates: " + ", ".join(candidate_paths))
			# Exit 2 (operator must repair the file) is distinct from
			# exit 1 (user-visible "Aborted." after declining the
			# overwrite prompt below) so callers / scripts can route
			# the two cases differently if needed.
			return 2
		if pick_result.chosen is not None:
			print(f"Resuming from {os.path.relpath(pick_result.chosen)}")
		command = build_grade_command(
			image_number, term, yaml_backup_file=pick_result.chosen
		)
		graded_csv = image_dir / f"output-protein_image_{image_number:02d}.csv"
		if graded_csv.is_file():
			# When the dashboard auto-routed because the form CSV grew
			# (PARTIAL graded), reframe the prompt: the existing
			# already-graded rows will be re-computed (idempotent), the
			# only new work is the missing row(s). Default Y in that case
			# so the operator can press Enter to proceed.
			canonical_csvs = find_canonical_form_csvs(term)
			row = build_status_row(image_number, term, canonical_csvs)
			form_count = row["form_count"]
			graded_count = row["graded_count"]
			if (form_count is not None and graded_count is not None
					and graded_count < form_count):
				new_rows = form_count - graded_count
				prompt_text = (
					f"Re-grade to pick up {new_rows} new row(s)?"
				)
				ok = confirm_overwrite(prompt_text, default_yes=True)
			else:
				ok = confirm_overwrite(
					f"Existing grade output:\n  {graded_csv}\n"
					f"Regrade and overwrite?"
				)
			if not ok:
				print("Aborted.")
				return 1
	elif step == "email":
		# Idempotency comes from email_log.yml inside send_feedback_email.py;
		# the orchestrator never opts in to -e/--send-email, so this run
		# always defaults to dry-run.
		image_dir = protein_images_path.get_term_image_dir(term, image_number)
		graded_yaml = image_dir / f"output-protein_image_{image_number:02d}.yml"
		if not graded_yaml.is_file():
			raise FileNotFoundError(
				f"Graded YAML required for email step: {graded_yaml}"
			)
		command = build_email_command(image_number, term)
	else:
		raise ValueError(f"Unsupported step: {step}")

	# Render each argv token as a repo-relative path when it points at
	# a file on disk; otherwise pass through verbatim. Keeps the echoed
	# subprocess line readable without losing fidelity.
	display_tokens = []
	for token in command:
		if os.path.isabs(token) and os.path.exists(token):
			display_tokens.append(os.path.relpath(token))
		else:
			display_tokens.append(token)
	print(f"+ {' '.join(display_tokens)}")
	result = subprocess.run(command)

	# Email step: after a clean dry-run, offer to promote to a real
	# send. The orchestrator never invokes -e directly; the operator
	# must explicitly answer the prompt. Only fires for the email
	# step, only when the dry-run exited cleanly, and only when stdin
	# is a TTY so scripted callers are not blocked.
	if step == "email" and result.returncode == 0 and sys.stdin.isatty():
		ok = confirm_overwrite(
			"Dry-run complete. Send for real now?",
			default_yes=False,
		)
		if ok:
			real_command = command + ["-e"]
			real_display = display_tokens + ["-e"]
			print(f"+ {' '.join(real_display)}")
			real_result = subprocess.run(real_command)
			return real_result.returncode
	return result.returncode


#============================================
def prompt_for_image_number() -> int:
	answer = input("Image number? [1-10]: ").strip()
	number = int(answer)
	if number not in EXPECTED_IMAGE_NUMBERS:
		raise ValueError(f"Image number must be in 1-10, got {number}")
	return number


#============================================
def main():
	"""
	Resolve term, auto-import stray repo-root CSVs, print the dashboard,
	then either exit (status-only) or run the requested step.
	"""
	args = parse_args()
	term = protein_images_path.get_active_term(args.term)

	# Always run auto-import first; it enforces canonical layout.
	auto_import_repo_root_csvs(term)

	# Refuse to continue if the canonical forms dir contains duplicates;
	# the dashboard will still print so the user sees what is wrong.
	dashboard = render_dashboard(term)
	print(dashboard)

	if args.status_only:
		return 0

	dups = detect_canonical_duplicates(term)
	if dups:
		print("Refusing to run any action step while duplicate form CSVs exist.")
		return 2

	image_number = args.image_number
	if image_number is None:
		image_number = prompt_for_image_number()
	if image_number not in EXPECTED_IMAGE_NUMBERS:
		raise ValueError(
			f"Image number must be in {EXPECTED_IMAGE_NUMBERS}, got {image_number}"
		)

	step = args.step
	if step is None:
		step = auto_select_step(term, image_number)
		print(f"Step: {step} (auto-selected)")

	return run_step(term, image_number, step)


#============================================
def auto_select_step(term: str, image_number: int) -> str:
	"""
	Pick the next actionable step for one image. Steps are sequential, so
	the dashboard's computed next_step is authoritative; we only collapse
	the few non-actionable cases into hard errors.
	"""
	canonical_csvs = find_canonical_form_csvs(term)
	row = build_status_row(image_number, term, canonical_csvs)
	next_step = row["next_step"]
	if next_step == "grade":
		return "grade"
	if next_step == "email":
		return "email"
	if next_step == "regrade":
		return "regrade"
	if next_step == "regrade or upload":
		return "regrade"
	if next_step == "done":
		raise ValueError(
			f"Image {image_number:02d} is already complete; pass -s regrade to redo."
		)
	raise ValueError(
		f"Image {image_number:02d} cannot be auto-stepped (next_step={next_step!r}); "
		"resolve the dashboard warning first."
	)
