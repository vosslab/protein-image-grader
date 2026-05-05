"""
Single entry point for protein image grading workflow.

Auto-imports stray repo-root form CSVs into the canonical
Protein_Images/semesters/<term>/forms/ directory, prints a per-image
status dashboard, and shells out to download_submission_images.py or
grade_protein_image.py for one image at a time. Never batch-grades.
"""

# Standard Library
import sys
import shutil
import pathlib
import argparse
import subprocess

# PIP3 modules
import tabulate

# local repo modules
import protein_image_grader.archive_paths as archive_paths
import protein_image_grader.protein_images_path as protein_images_path


EXPECTED_IMAGE_NUMBERS = tuple(range(1, 11))
STEP_CHOICES = ("download", "grade", "regrade")
DOWNLOAD_SCRIPT = "download_submission_images.py"
GRADE_SCRIPT = "grade_protein_image.py"
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
	Return a dict {image_number: [matching CSV paths]} from the canonical
	forms dir. Missing dir yields an empty dict; multiple matches per
	image number are preserved so callers can detect duplicates.
	"""
	forms_dir = protein_images_path.get_forms_dir(term)
	by_image = {}
	if not forms_dir.is_dir():
		return by_image
	for csv_path in sorted(forms_dir.glob("BCHM_Prot_Img_*.csv")):
		# basename pattern is BCHM_Prot_Img_NN-<label>.csv
		stem_parts = csv_path.name.split("_")
		# Robust extraction: take the first 2-digit run after BCHM_Prot_Img_
		number_token = csv_path.name[len("BCHM_Prot_Img_"):][:2]
		if not number_token.isdigit():
			# Skip oddly-named files; they are not canonical anyway.
			continue
		image_number = int(number_token)
		by_image.setdefault(image_number, []).append(csv_path)
		# stem_parts is currently unused but kept for future debug printing.
		del stem_parts
	return by_image


#============================================
def auto_import_repo_root_csvs(term: str) -> list:
	"""
	Move repo-root BCHM_Prot_Img_##-*.csv files into the canonical forms
	directory for `term`. Returns the list of moves performed as
	[(src_path, dst_path), ...].

	Filesystem move only (shutil.move). Protein_Images/ is gitignored, so
	`git mv` would be wrong here. Refuses to overwrite an existing
	destination and raises FileExistsError.
	"""
	root_csvs = find_repo_root_form_csvs()
	if not root_csvs:
		return []
	forms_dir = protein_images_path.get_forms_dir(term)
	forms_dir.mkdir(parents=True, exist_ok=True)
	moves = []
	for src in root_csvs:
		dst = forms_dir / src.name
		if dst.exists():
			message = (
				f"ERROR: cannot import {src}; destination already exists:\n"
				f"  {dst}\n"
				"Resolve the duplicate manually before re-running."
			)
			raise FileExistsError(message)
		print(f"+ move {src.name} -> {dst}")
		shutil.move(str(src), str(dst))
		moves.append((src, dst))
	return moves


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
def grades_dir_for(term: str) -> pathlib.Path:
	return protein_images_path.get_grades_dir(term)


#============================================
def submissions_dir_for(term: str) -> pathlib.Path:
	return protein_images_path.get_submissions_dir(term)


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
	Build one dashboard row for the given image number. Pure function:
	only inspects existence/non-emptiness of paths.
	"""
	csv_matches = canonical_csvs.get(image_number, [])
	if len(csv_matches) == 0:
		form_status = "MISSING"
	elif len(csv_matches) >= 2:
		form_status = "DUPLICATE"
	else:
		form_status = "OK"

	submissions_dir = submissions_dir_for(term) / f"download_{image_number:02d}_raw"
	if is_non_empty_dir(submissions_dir):
		downloaded_status = "OK"
	else:
		downloaded_status = "MISSING"

	grades_dir = grades_dir_for(term)
	graded_csv = grades_dir / f"output-protein_image_{image_number:02d}.csv"
	graded_status = "OK" if graded_csv.is_file() else "MISSING"

	bb_csv = grades_dir / f"blackboard_upload-protein_image_{image_number:02d}.csv"
	bb_status = "OK" if bb_csv.is_file() else "MISSING"

	next_step = compute_next_step(form_status, downloaded_status,
		graded_status, bb_status)

	row = {
		"image": f"{image_number:02d}",
		"form": form_status,
		"downloaded": downloaded_status,
		"graded": graded_status,
		"bb_upload": bb_status,
		"next_step": next_step,
	}
	return row


#============================================
def compute_next_step(form_status: str, downloaded_status: str,
		graded_status: str, bb_status: str) -> str:
	"""
	Pick the most useful next action verb for one image row.
	"""
	if form_status == "DUPLICATE":
		return "fix duplicate CSV"
	if form_status == "MISSING":
		return "add form CSV"
	if downloaded_status != "OK":
		return "download"
	if graded_status != "OK":
		return "grade"
	# Graded already; suggest regrade if late submissions might exist.
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
		"BB upload", "Next step"]
	table_rows = [
		[r["image"], r["form"], r["downloaded"], r["graded"],
			r["bb_upload"], r["next_step"]]
		for r in rows
	]
	output = ""
	output += render_header_banner(term)
	output += "\n"
	output += tabulate.tabulate(table_rows, headers=headers,
		tablefmt="simple")
	output += "\n"
	output += render_footer_warnings(term)
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
def render_footer_warnings(term: str) -> str:
	"""
	Print warnings that do not belong inside the table.
	"""
	parts = []
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
	if step in ("grade", "regrade"):
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
	"""
	require_resources(term, step)
	canonical_csv = resolve_canonical_csv(term, image_number)

	if step == "download":
		command = build_download_command(canonical_csv)
		download_dir = (
			submissions_dir_for(term) / f"download_{image_number:02d}_raw"
		)
		if is_non_empty_dir(download_dir):
			ok = confirm_overwrite(
				f"Existing download dir is non-empty:\n  {download_dir}\n"
				f"Re-run download anyway?"
			)
			if not ok:
				print("Aborted.")
				return 1
	elif step == "grade":
		command = build_grade_command(image_number, term)
		graded_csv = (
			grades_dir_for(term)
			/ f"output-protein_image_{image_number:02d}.csv"
		)
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
		graded_csv = (
			grades_dir_for(term)
			/ f"output-protein_image_{image_number:02d}.csv"
		)
		if graded_csv.is_file():
			ok = confirm_overwrite(
				f"Existing grade output:\n  {graded_csv}\n"
				f"Regrade and overwrite?"
			)
			if not ok:
				print("Aborted.")
				return 1
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
def prompt_for_step() -> str:
	choices = "/".join(STEP_CHOICES)
	answer = input(f"Step? [{choices}]: ").strip().lower()
	if answer not in STEP_CHOICES:
		raise ValueError(f"Step must be one of {STEP_CHOICES}, got {answer!r}")
	return answer


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
		step = prompt_for_step()

	return run_step(term, image_number, step)
