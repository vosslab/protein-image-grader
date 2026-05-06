"""
Single entry point for protein image grading workflow.

Auto-imports stray repo-root form CSVs into the canonical
Protein_Images/semesters/<term>/forms/ directory, prints a per-image
status dashboard, and shells out to download_submission_images.py or
grade_protein_image.py for one image at a time. Never batch-grades.
"""

# Standard Library
import os
import sys
import csv
import shutil
import pathlib
import argparse
import subprocess

# PIP3 modules
import tabulate

# local repo modules
import protein_image_grader.email_log as email_log
import protein_image_grader.csv_compare as csv_compare
import protein_image_grader.form_columns as form_columns
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
def auto_import_repo_root_csvs(term: str) -> list:
	"""
	Move repo-root BCHM_Prot_Img_##-*.csv files into the canonical forms
	directory for `term`. Returns one record per source file as
	[(src_path, dst_path, action), ...] where action is one of
	"moved", "identical", or "replaced".

	Filesystem move only (shutil.move). Protein_Images/ is gitignored,
	so `git mv` would be wrong here.

	Collision policy (when a destination already exists):
	  - byte-identical (SHA-256 match) -> delete the root copy silently
	    with a "+ identical" notice; action="identical".
	  - strict keyed superset (every shared (Student ID, timestamp)
	    key has byte-identical row content; candidate may add more) ->
	    overwrite canonical via os.replace; action="replaced".
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
			os.replace(str(src), str(dst))
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
def count_form_records(canonical_csv: pathlib.Path) -> int:
	"""
	Return the number of data rows in `canonical_csv` whose Student-ID
	cell is non-empty.

	Uses form_columns.resolve_meta_columns(required={"Student ID"}) to
	locate the Student-ID column; the form CSV may put it anywhere in
	the first IDENTITY_PREFIX_COLUMNS header cells. Counts records,
	not unique students -- the grader emits one output row per form
	submission, so the dashboard comparison is record-vs-record.
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
	count = 0
	for row in all_rows[1:]:
		if len(row) <= id_idx:
			continue
		if row[id_idx].strip():
			count += 1
	return count


#============================================
def count_graded_records(output_csv: pathlib.Path) -> int:
	"""
	Return the number of data rows in `output_csv` whose Student-ID
	cell is non-empty. The grader's output CSV has a literal
	"Student ID" header column.
	"""
	with open(output_csv, "r", encoding="utf-8", newline="") as handle:
		reader = csv.DictReader(handle)
		count = 0
		for row in reader:
			value = row["Student ID"]
			if value and value.strip():
				count += 1
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
	if image_dir is None:
		downloaded_status = "MISSING"
		graded_status = "MISSING"
		bb_status = "MISSING"
	else:
		downloaded_status = "OK" if is_non_empty_dir(image_dir / "raw") else "MISSING"
		graded_csv = image_dir / f"output-protein_image_{image_number:02d}.csv"
		graded_status = "OK" if graded_csv.is_file() else "MISSING"
		bb_csv = image_dir / f"blackboard_upload-protein_image_{image_number:02d}.csv"
		bb_status = "OK" if bb_csv.is_file() else "MISSING"
		# Compare counts only when both sides are usable. Form-side
		# count needs exactly one canonical CSV (form_status == "OK");
		# graded-side count needs the output CSV on disk.
		if form_status == "OK" and graded_status == "OK":
			form_count = count_form_records(csv_matches[0])
			graded_count = count_graded_records(graded_csv)
			# Strict less-than -> PARTIAL (operator must regrade the
			# new row(s)). Equal counts stay OK. More-graded-than-form
			# is handled in render_footer_warnings as a stale-output
			# warning; status stays OK because no regrade would help.
			if graded_count < form_count:
				graded_status = "PARTIAL"

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
	return [sys.executable, DOWNLOAD_SCRIPT, "-i", str(canonical_csv)]


#============================================
def build_grade_command(image_number: int, term: str) -> list:
	"""
	Construct the argv list to invoke grade_protein_image.py for one image.
	"""
	return [
		sys.executable, GRADE_SCRIPT,
		"-i", str(image_number),
		"--term", term,
	]


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
def confirm_overwrite(prompt: str) -> bool:
	"""
	Ask for y/N. Default is N. Always interactive; no --yes bypass flag.
	"""
	answer = input(f"{prompt} [y/N] ").strip().lower()
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
		print(f"WARNING: {bb_ids.name} not found at {bb_ids} (upload not"
			" implemented yet; ignoring).")


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
		command = build_grade_command(image_number, term)
		image_dir = protein_images_path.get_term_image_dir(term, image_number)
		graded_csv = image_dir / f"output-protein_image_{image_number:02d}.csv"
		if graded_csv.is_file():
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

	command_string = " ".join(command)
	print(f"+ {command_string}")
	result = subprocess.run(command)
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
