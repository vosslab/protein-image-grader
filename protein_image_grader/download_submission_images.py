# Standard Library
import os
import re
import csv
import time
import random
import shutil
import pathlib
import argparse

# PIP3 modules
import yaml
import PIL.Image
import pillow_heif
import rich.console
import googleapiclient.errors

# local repo modules
import protein_image_grader.ruid_resolver as ruid_resolver
import protein_image_grader.image_filename as image_filename
import protein_image_grader.google_drive_image_utils as google_drive_image_utils
import protein_image_grader.archive_paths as archive_paths
import protein_image_grader.form_columns as form_columns
import protein_image_grader.protein_images_path as protein_images_path
import protein_image_grader.roster_matching as roster_matching

pillow_heif.register_heif_opener()

# Module-level Rich console; markup=False on every call so file paths
# containing stray characters never get parsed as Rich tags.
console = rich.console.Console(highlight=False)

fail_count = 0

#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		args: Parsed arguments
	"""
	parser = argparse.ArgumentParser(description="Download submission images and build an HTML review page.")
	parser.add_argument('-i', '--input', dest='csvfile',
		type=str, default=None,
		help="Input CSV file (omit to look up by --image-number or use --all)")
	parser.add_argument('-x', '--max-students', dest='maxstudents', default=-1,
		type=int, required=False, help="Max Students, used for testing")
	parser.add_argument('-t', '--trim', dest='trim', action='store_true')
	parser.add_argument('--no-trim', dest='trim', action='store_false')
	parser.set_defaults(trim=False)
	parser.add_argument('-r', '--rotate', dest='rotate', action='store_true')
	parser.add_argument('--no-rotate', dest='rotate', action='store_false')
	parser.set_defaults(rotate=False)
	# Default is None so main() can infer the canonical per-image folder
	# (Protein_Images/semesters/<term>/BCHM_Prot_Img_NN_<topic>/) from a
	# canonical input CSV. An explicit override is honored verbatim.
	parser.add_argument('-o', '--output-dir', dest='output_dir', type=str,
		help="Output directory for downloads and HTML (disables archive sync by default)",
		default=None)
	parser.add_argument('--archive-anyway', dest='archive_anyway', action='store_true',
		help="Re-enable archive sync even when --output-dir is provided",
		default=False)
	parser.add_argument('-p', '--profiles-html', dest='profiles_html', type=str,
		help="Output HTML file name", default=None)
	parser.add_argument('--image-number', dest='image_number', default=0,
		type=int, required=False,
		help="Image number 1-20; with no -i, resolves canonical form CSV.")
	parser.add_argument('--term', dest='term', type=str, default=None,
		help="Active term, e.g. spring_2026 (defaults to active_term.txt).")
	parser.add_argument('-a', '--all', dest='all_images', action='store_true',
		help="Bulk-download every canonical form CSV in the active term.")
	args = parser.parse_args()
	return args


# Form CSV identity columns are resolved at runtime by
# form_columns.resolve_meta_columns. To add or change recognized
# header variants (e.g. accept "Net ID" as a Username column), edit
# STANDARD_META_COLUMNS in protein_image_grader/form_columns.py.

#============================================
# Canonical layout for downloaded images:
#   Protein_Images/semesters/<term>/BCHM_Prot_Img_NN_<topic>/raw/
#   Protein_Images/semesters/<term>/BCHM_Prot_Img_NN_<topic>/trim/

#============================================
# regex: BCHM_Prot_Img_NN-<anything>.csv where NN is two digits 01-20
CANONICAL_FORM_CSV_RE = re.compile(r'^BCHM_Prot_Img_(\d{2})-.+\.csv$')


#============================================
def extract_image_number_from_csv_basename(basename: str) -> int:
	"""
	Parse the image number from a canonical form CSV basename.

	Expects the form 'BCHM_Prot_Img_NN-<label>.csv'. Raises ValueError if
	the name does not match. Pure function; no filesystem access.
	"""
	match = CANONICAL_FORM_CSV_RE.match(basename)
	if match is None:
		raise ValueError(
			f"CSV basename does not match BCHM_Prot_Img_NN-*.csv: {basename}"
		)
	return int(match.group(1))


#============================================
def infer_canonical_output_dir(csv_path: str) -> pathlib.Path:
	"""
	Infer the canonical image output dir from a canonical CSV path.

	The CSV must live under
		<repo>/Protein_Images/semesters/<term>/forms/BCHM_Prot_Img_NN-*.csv
	in which case this returns
		<repo>/Protein_Images/semesters/<term>/BCHM_Prot_Img_NN_<topic>

	Returns None when the CSV path is non-canonical. Pure function except
	for resolving the path (no directories are created).
	"""
	csv_p = pathlib.Path(csv_path).resolve()
	parts = csv_p.parts
	# Look for the canonical anchor: .../Protein_Images/semesters/<term>/forms/<file>
	if len(parts) < 5:
		return None
	if parts[-2] != protein_images_path.FORMS_SUBDIR:
		return None
	if parts[-4] != protein_images_path.SEMESTERS_SUBDIR:
		return None
	if parts[-5] != protein_images_path.PROTEIN_IMAGES_NAME:
		return None
	term = parts[-3]
	image_number = extract_image_number_from_csv_basename(csv_p.name)
	# New layout: return the per-image directory (caller will add /raw or /trim)
	image_dir = protein_images_path.get_term_image_dir(term, image_number)
	return image_dir


#============================================
def resolve_image_dir(csvfile: str, output_dir_override: str | None,
		image_number: int) -> str:
	"""
	Resolve where downloaded images for this run should land.

	Rules:
	- If output_dir_override is given, honor it verbatim (no rewrites).
	- Else, infer the canonical per-image directory from the CSV path.
	  The CSV must be in Protein_Images/semesters/<term>/forms/ and match
	  the provided image_number. If the CSV is not canonical, raise a clear error.
	"""
	if output_dir_override is not None:
		return output_dir_override
	canonical = infer_canonical_output_dir(csvfile)
	if canonical is None:
		message = (
			"Cannot infer canonical output dir from non-canonical CSV path:\n"
			f"  {csvfile}\n"
			"Move the CSV to Protein_Images/semesters/<term>/forms/, or pass\n"
			"--output-dir explicitly."
		)
		raise ValueError(message)
	# Verify that the inferred image_number matches the expected one.
	# Extract the number from the CSV to compare.
	csv_basename = pathlib.Path(csvfile).name
	csv_image_number = extract_image_number_from_csv_basename(csv_basename)
	if csv_image_number != image_number:
		raise ValueError(
			f"Image number {image_number} disagrees with CSV basename {csv_basename}"
			f" (CSV indicates image {csv_image_number:02d})"
		)
	return str(canonical)

#============================================
def get_image_html_tag(image_url: str, ruid: int, args, image_dir: str,
		image_raw_dir: str, archive_root: str, image_hashes: dict, hashes_changed: list) -> str:
	"""
	Download image from Google Drive, save to raw/trim dirs, archive, hash, and return HTML tag.

	Args:
		image_url: Google Drive image URL
		ruid: Record ID for naming
		args: Parsed arguments
		image_dir: Per-image working directory
		image_raw_dir: raw/ subdirectory path
		archive_root: Archive root for the image (image_bank/<term>/<image_dir>)
		image_hashes: Hash dict to update
		hashes_changed: Mutable list to track changes

	Returns:
		str: HTML <img> tag(s) for the image
	"""
	file_id = google_drive_image_utils.get_file_id_from_google_drive_url(image_url)
	image_data, original_filename = try_download_image(file_id)
	if image_data is None:
		return ''

	filename = format_filename(original_filename, ruid, args)
	raw_path = os.path.abspath(os.path.join(image_raw_dir, filename))
	if not os.path.exists(raw_path):
		was_saved = download_and_save_image(image_data, raw_path)
		if not was_saved:
			return ''
	else:
		console.print(f"file exists: {filename}", style="dim yellow")

	# Archive the raw image if archiving is enabled
	if archive_root and image_hashes is not None:
		archive_path = archive_image_if_needed(raw_path, os.path.join(archive_root, "raw"))
		if archive_path:
			with open(archive_path, 'rb') as f:
				md5hash, phash = google_drive_image_utils.get_hash_data(f)
			hashes_changed[0] = update_image_hashes(
				image_hashes, md5hash, phash, archive_path
			) or hashes_changed[0]

	trim_path = None
	if args.trim:
		trim_dir = os.path.join(image_dir, "trim")
		if not os.path.isdir(trim_dir):
			os.makedirs(trim_dir)
		trim_path = trim_and_save_image(raw_path, trim_dir, args.rotate)
		if trim_path is None:
			trim_path = ""
		# Archive the trim image if archiving is enabled
		if archive_root and image_hashes is not None and trim_path:
			archive_path = archive_image_if_needed(trim_path, os.path.join(archive_root, "trim"))
			if archive_path:
				with open(archive_path, 'rb') as f:
					md5hash, phash = google_drive_image_utils.get_hash_data(f)
				hashes_changed[0] = update_image_hashes(
					image_hashes, md5hash, phash, archive_path
				) or hashes_changed[0]

	html_tag = f"<img border='3' src='file://{raw_path}' height='250' />"
	if args.trim and os.path.isfile(trim_path):
		html_tag += f"<img border='3' src='file://{trim_path}' height='350' />"

	print('')
	return html_tag

#============================================
def try_download_image(file_id: str) -> tuple:
	"""
	Try downloading an image using service account.

	Args:
		file_id: Google Drive file ID

	Returns:
		tuple: (image data stream, original filename)
	"""
	global fail_count
	try:
		image_data, original_filename = google_drive_image_utils.download_image(file_id)
		return image_data, original_filename
	except googleapiclient.errors.HttpError as e:
		fail_count += 1
		console.print(f"Error downloading image: {e}", style="bold red")
		time.sleep(random.random())
		console.print(
			"check permissions of the folder for vosslab-12389@protein-images.iam.gserviceaccount.com",
			style="red")
		if fail_count > 2:
			raise ValueError
		return None, ''

#============================================
def format_filename(original_filename: str, ruid: int, args) -> str:
	"""
	Clean and normalize the filename for saving.

	Thin wrapper around `image_filename.build_raw_image_filename` so the
	canonical shape lives in one module that both downloader and grader
	import. See `protein_image_grader/image_filename.py`.
	"""
	return image_filename.build_raw_image_filename(
		ruid, args.image_number, original_filename
	)

#============================================
def download_and_save_image(image_data, filepath: str) -> bool:
	"""
	Save the downloaded image if not already present.

	Args:
		image_data: BytesIO image stream
		filepath: Full path to save the image

	Returns:
		bool: True if saved, False if already existed
	"""
	if os.path.isfile(filepath):
		return False
	pil_image = PIL.Image.open(image_data)
	pil_image.save(filepath)
	console.print(f"saved {os.path.basename(filepath)}", style="bold green")
	return True

#============================================
def archive_image_if_needed(filepath: str, archive_dir: str) -> str:
	"""
	Copy a saved image into the archive folder if it is not already there.
	"""
	if archive_dir is None:
		return None
	if not os.path.isfile(filepath):
		return None
	if not os.path.isdir(archive_dir):
		os.makedirs(archive_dir)
	archive_path = os.path.join(archive_dir, os.path.basename(filepath))
	if os.path.isfile(archive_path):
		return archive_path
	shutil.copy2(filepath, archive_path)
	return archive_path

#============================================
def trim_and_save_image(filepath: str, trim_dir: str, rotate: bool=False) -> str:
	"""
	Trim borders and optionally rotate the image, then save to trim_dir.

	Args:
		filepath: Original image path
		trim_dir: Directory to save the trimmed image
		rotate: Whether to rotate tall images

	Returns:
		str: Path to trimmed image
	"""
	pil_image = PIL.Image.open(filepath)
	trimmed_image = google_drive_image_utils.multi_trim(pil_image, 1)
	if rotate:
		trimmed_image = google_drive_image_utils.rotate_if_tall(trimmed_image)
	if trimmed_image.mode != 'RGB':
		trimmed_image = trimmed_image.convert('RGB')
	basename = os.path.basename(filepath)
	basename_no_ext = os.path.splitext(basename)[0]
	trim_filename = f"{basename_no_ext}-trim.jpg"
	trim_path = os.path.join(trim_dir, trim_filename)
	trimmed_image.save(trim_path)
	console.print(f"saved {os.path.basename(trim_path)}", style="bold green")
	return trim_path

#============================================
def write_header(output, filename: str):
	"""
	Write the HTML header to the output file.
	"""
	title = os.path.splitext(filename)[0].title()
	output.write("<html><head>\n")
	output.write(f"<title>{title}</title>\n")
	output.write("</head><body>\n")

#============================================
def find_first_name_key_index_from_header(header: list) -> int:
	"""
	Find the index of the "First Name" or "Full Name" column.

	Args:
		header (list): List of CSV header values.

	Returns:
		int: Index of the first name column, or None if not found.
	"""
	for i, item in enumerate(header):
		sitem = item.strip().lower()
		if 'first' in sitem and 'name' in sitem:
			return i
	for i, item in enumerate(header):
		sitem = item.strip().lower()
		if 'full' in sitem and 'name' in sitem:
			return i
	return None

#============================================
def read_csv(csvfile: str, maxstudents: int) -> tuple:
	"""
	Read the CSV file and extract the data into a list.

	Args:
		csvfile (str): Path to the CSV file.

	Returns:
		tuple: (header row, sorted data list, first name key index)
	"""
	if not os.path.exists(csvfile):
		raise ValueError(f"Error: File '{csvfile}' does not exist.")

	data_tree = []
	first_name_key_index = None

	with open(csvfile, "r") as f:
		data = csv.reader(f)
		header = None
		for row in data:
			if header is None:
				header = row
				first_name_key_index = find_first_name_key_index_from_header(header)
				continue
			data_tree.append(row)
			if maxstudents > 0 and len(data_tree) >= maxstudents:
				break

	data_tree.sort(key=lambda x: x[first_name_key_index].lower().strip())
	return header, data_tree

#============================================
def extract_number_in_range(s: str) -> int:
	"""
	Extract the first integer between 1 and 20 (inclusive) from the string.
	"""
	matches = re.findall(r'\d{1,2}', s)
	for match in matches:
		num = int(match)
		if 1 <= num <= 20:
			return num
	raise ValueError(f"No number in range 1-20 found in string: {s}")


#============================================
def load_image_hashes(image_hashes_yaml: str) -> dict:
	"""
	Load image hashes from YAML or initialize an empty structure.
	"""
	if image_hashes_yaml is None:
		return {'md5': {}, 'phash': {}}
	if not os.path.isfile(image_hashes_yaml):
		return {'md5': {}, 'phash': {}}
	with open(image_hashes_yaml, 'r') as f:
		image_hashes = yaml.safe_load(f)
	if image_hashes is None:
		return {'md5': {}, 'phash': {}}
	if image_hashes.get('md5') is None:
		image_hashes['md5'] = {}
	if image_hashes.get('phash') is None:
		image_hashes['phash'] = {}
	return image_hashes

#============================================
def update_image_hashes(image_hashes: dict, md5hash: str, phash: str,
		archive_path: str) -> bool:
	"""
	Update image hash dictionaries with a new entry.
	"""
	archive_path = archive_paths.normalize_hash_path(archive_path)
	changed = False
	if md5hash and image_hashes['md5'].get(md5hash) is None:
		image_hashes['md5'][md5hash] = archive_path
		changed = True
	if phash and image_hashes['phash'].get(phash) is None:
		image_hashes['phash'][phash] = archive_path
		changed = True
	return changed

#============================================
def _row_value(row: list, idx: int | None) -> str:
	"""
	Read `row[idx]` defensively.

	Returns '' when the column was not found in the header (`idx is None`)
	or when the row is short (some Google Form rows omit trailing empty
	cells). Treats a None cell as empty string.
	"""
	if idx is None or idx >= len(row):
		return ""
	return row[idx] or ""


#============================================
def _extract_form_ruid_from_row(row: list, header: list,
		col_student_id_idx: int | None) -> str:
	"""
	Pull the typed Form RUID from one form-CSV row.

	Prefers the explicit Student-ID column when the form CSV has one.
	Falls back to the first cell that matches the Roosevelt RUID format
	(9 digits starting with 900 or 960; see docs/RUID_POLICY.md). Older
	form CSVs without a labeled RUID column still resolve correctly.

	Returns '' when no usable candidate was found; the resolver will
	then surface this row as UnresolvedStudent.
	"""
	if col_student_id_idx is not None:
		raw = _row_value(row, col_student_id_idx).strip()
		if raw:
			return raw
	for item in row:
		if not item:
			continue
		stripped = item.strip()
		if stripped.startswith('900') or stripped.startswith('960'):
			return stripped
	return ""


#============================================
def generate_html(csvfile: str, header: list, data_tree: list, args, image_dir: str,
		image_raw_dir: str, archive_root: str, output_html: str, image_hashes: dict,
		hashes_changed: list, matcher, assigned_ruids: set):
	"""
	Generate an HTML file based on the CSV data.

	Each row's typed Form RUID is resolved to the authoritative Roster
	RUID via `ruid_resolver.resolve_form_row_to_roster_row(matcher, ...)`
	before any image is saved or any filename is constructed (per
	`docs/RUID_POLICY.md`). Any row that cannot be resolved aborts the
	run with `RuntimeError`: an unresolved row means `roster.csv` is
	stale (or the form RUID is wrong) and the operator must fix the
	roster before re-running. `assigned_ruids` is mutated by the
	resolver to detect same-run duplicates across all CSVs in a `--all`
	run.
	"""
	if args.image_number == 0:
		args.image_number = extract_number_in_range(os.path.basename(csvfile))

	# The downloader needs name/username; Student ID is preferred but
	# missing-column rows fall back to _extract_form_ruid_from_row's
	# 900/960 prefix scan over every cell, so leave Student ID optional.
	standard_indices = form_columns.resolve_meta_columns(
		header, required={"Username", "First Name", "Last Name"},
	)
	col_student_id_idx = standard_indices.get("Student ID")
	col_first_idx = standard_indices["First Name"]
	col_last_idx = standard_indices["Last Name"]
	col_username_idx = standard_indices["Username"]

	with open(output_html, "w") as output:
		write_header(output, csvfile)
		count = 0

		for row in data_tree:
			count += 1

			if count > 1:
				output.write('<br/><p style="page-break-before: always"><br/></p>\n')

			# Resolve the Roster RUID once per row, before any image is saved.
			form_ruid = _extract_form_ruid_from_row(row, header, col_student_id_idx)
			first_name = _row_value(row, col_first_idx)
			last_name = _row_value(row, col_last_idx)
			username = _row_value(row, col_username_idx)

			form_row = {
				"form_ruid": form_ruid,
				"first_name": first_name,
				"last_name": last_name,
				"username": username,
			}
			result = ruid_resolver.resolve_form_row_to_roster_row(
				form_row, matcher, assigned_ruids,
			)

			if isinstance(result, ruid_resolver.UnresolvedStudent):
				# An unresolved row means roster.csv is stale (or the
				# typed Form RUID is wrong). Either way the operator
				# must fix the roster before any image can be saved
				# under an authoritative Roster RUID; aborting here
				# beats silently dropping the row.
				candidate_lines = ""
				for cand_ruid, cand_name, cand_score in result.candidates:
					candidate_lines += (
						f"\n  candidate: {cand_ruid} {cand_name} "
						f"score={cand_score:.3f}"
					)
				raise RuntimeError(
					f"Unresolved Form RUID in {csvfile}: "
					f"form_ruid={form_ruid!r} name={first_name!r} {last_name!r} "
					f"username={username!r} reason={result.reason} "
					f"score={result.score:.3f}. "
					"roster.csv is stale or the typed RUID is wrong; "
					"fix the roster (or the form CSV) and re-run."
					f"{candidate_lines}"
				)

			ruid = result.roster_ruid
			if result.form_ruid and str(ruid) != result.form_ruid.strip():
				# Surface mismatches so the operator can spot typos at runtime.
				console.print(
					f"  resolved form_ruid={result.form_ruid} -> roster_ruid={ruid}"
					f" ({result.full_name}, {result.reason} score={result.score:.3f})",
					style="cyan",
				)

			for i, item in enumerate(row):
				if len(item) < 1:
					continue
				elif item.startswith('900') or item.startswith('960'):
					# Already consumed by the resolver above; do not
					# emit the typed RUID into the HTML page.
					continue
				elif item.startswith('http'):
					img_html_tag = get_image_html_tag(
						item, ruid, args, image_dir, image_raw_dir, archive_root, image_hashes, hashes_changed
					)
					output.write(f"{img_html_tag}\n")
				else:
					output.write(f"<p><b>{header[i].strip()}</b>:&nbsp; {row[i].strip()}</p>\n")

#============================================
def open_html_in_browser(html_path: str):
	"""
	Open the generated HTML file in a web browser.
	"""
	os.system(f"open {html_path}")

#============================================
def write_html_from_student_tree(student_tree: list, output_html: str) -> None:
	"""
	Write an HTML file using a student_tree list that already includes output filenames.
	"""
	output_dir = os.path.dirname(output_html)
	if output_dir and not os.path.isdir(output_dir):
		os.makedirs(output_dir)

	with open(output_html, "w") as output:
		write_header(output, output_html)
		count = 0
		for student_entry in student_tree:
			count += 1
			if count > 1:
				output.write('<br/><p style="page-break-before: always"><br/></p>\n')

			student_id = student_entry.get('Student ID', '')
			first_name = student_entry.get('First Name', '')
			last_name = student_entry.get('Last Name', '')
			original_filename = student_entry.get('Original Filename', '')
			output_filename = student_entry.get('Output Filename', '')
			if output_filename:
				image_path = os.path.abspath(output_filename)
				output.write(f"<img border='3' src='file://{image_path}' height='350' />\n")

			if student_id:
				output.write(f"<p><b>Student ID</b>:&nbsp; {student_id}</p>\n")
			if first_name or last_name:
				output.write(f"<p><b>Student</b>:&nbsp; {first_name} {last_name}</p>\n")
			if original_filename:
				output.write(f"<p><b>Original Filename</b>:&nbsp; {original_filename}</p>\n")
	return

#============================================
def resolve_csv_paths(args) -> list:
	"""
	Decide which CSV(s) this run should process.

	Priority:
	1. If args.csvfile is set: [Path(args.csvfile)] (verbatim, legacy).
	2. If args.all_images: every canonical CSV for the active term, sorted
	   by image number. Duplicates are skipped with a warning.
	3. If args.image_number > 0: the single canonical CSV matching that
	   number from the active term's forms dir.
	4. Else: ValueError.
	"""
	if args.csvfile is not None:
		return [pathlib.Path(args.csvfile)]
	if args.all_images:
		term = protein_images_path.get_active_term(args.term)
		by_image = protein_images_path.find_canonical_form_csvs(term)
		if not by_image:
			forms_dir = protein_images_path.get_forms_dir(term)
			raise FileNotFoundError(
				f"No canonical form CSVs found in {forms_dir}"
			)
		paths = []
		for image_number in sorted(by_image.keys()):
			matches = by_image[image_number]
			if len(matches) >= 2:
				listing = "\n".join(f"    {p}" for p in matches)
				console.print(
					f"WARNING: skipping image {image_number:02d}; "
					f"multiple canonical CSVs:\n{listing}",
					style="bold yellow",
				)
				continue
			paths.append(matches[0])
		return paths
	if args.image_number > 0:
		term = protein_images_path.get_active_term(args.term)
		by_image = protein_images_path.find_canonical_form_csvs(term)
		matches = by_image.get(args.image_number, [])
		if len(matches) == 0:
			forms_dir = protein_images_path.get_forms_dir(term)
			raise FileNotFoundError(
				f"No canonical form CSV for image {args.image_number:02d}"
				f" in {forms_dir}"
			)
		if len(matches) >= 2:
			listing = "\n".join(f"  {p}" for p in matches)
			raise ValueError(
				f"Multiple canonical form CSVs for image"
				f" {args.image_number:02d}:\n{listing}"
			)
		return [matches[0]]
	raise ValueError(
		"No CSV selected. Pass one of: -i/--input <path>,"
		" --image-number N, or --all."
	)


#============================================
def process_one_csv(csvfile: str, args, image_hashes: dict,
		hashes_changed: list, open_browser: bool,
		matcher, assigned_ruids: set) -> None:
	"""
	Run the per-CSV pipeline: read CSV, resolve output dir, generate HTML.

	Mutates args.image_number (resolved from the basename) and
	args.profiles_html (per-CSV path) so generate_html sees the right
	values; the bulk loop resets these between iterations.

	`matcher` is a shared `roster_matching.RosterMatcher` constructed by
	main(); `assigned_ruids` is the per-CSV duplicate guard (main()
	resets it for each CSV, since each assignment is independent).
	Per-row Form-RUID -> Roster-RUID resolution happens inside
	generate_html.
	"""
	header, data_tree = read_csv(csvfile, args.maxstudents)

	# Use the basename only; the absolute CSV path may contain stray
	# digits (e.g. "/Ex2GB/..." or "/bchm_355-lecture/...") that the
	# 1-20 fallback would otherwise pick up before the real NN token.
	args.image_number = extract_number_in_range(os.path.basename(csvfile))

	# Canonical CSVs imply canonical output under
	# Protein_Images/semesters/<term>/BCHM_Prot_Img_NN_<topic>/.
	# Non-canonical CSVs require an explicit --output-dir.
	image_dir = resolve_image_dir(csvfile, args.output_dir, args.image_number)
	if not os.path.isdir(image_dir):
		os.makedirs(image_dir)
	console.print(
		f"  image {args.image_number:02d} -> {image_dir}",
		style="green")

	# Set up image_raw_dir (always under image_dir for canonical layout).
	image_raw_dir = os.path.join(image_dir, "raw")
	if not os.path.isdir(image_raw_dir):
		os.makedirs(image_raw_dir)

	# Archive is disabled by default when --output-dir is used; --archive-anyway
	# re-enables it. Without --output-dir, archive sync is always on.
	archive_root = None
	if (args.output_dir is None) or args.archive_anyway:
		term = protein_images_path.get_active_term(args.term)
		archive_root = str(archive_paths.make_archive_assignment_dir(
			term, pathlib.Path(image_dir).name))

	# profiles_html lands in the per-image folder per canonical layout.
	profiles_html = os.path.join(
		image_dir, f"profiles_image_{args.image_number:02d}.html")
	args.profiles_html = profiles_html

	generate_html(csvfile, header, data_tree, args, image_dir, image_raw_dir,
		archive_root, profiles_html, image_hashes, hashes_changed,
		matcher, assigned_ruids)
	if open_browser:
		open_html_in_browser(profiles_html)


#============================================
def main():
	"""
	Main function to parse arguments and process the CSV file(s).
	"""
	args = parse_args()
	csv_paths = resolve_csv_paths(args)

	# --output-dir cannot be combined with multi-CSV runs because every CSV
	# would land in the same dir.
	if args.output_dir is not None and len(csv_paths) > 1:
		raise ValueError("--output-dir cannot be used with --all (would collide).")

	image_hashes_yaml = str(protein_images_path.get_image_hashes_yaml())
	image_hashes = load_image_hashes(image_hashes_yaml)
	hashes_changed = [False]

	# Open browser only for single-CSV runs, so --all does not spawn 10 tabs.
	open_browser = len(csv_paths) == 1

	# Build the matcher once per run (the build is expensive due to
	# roster indexing). `assigned_ruids` is reset per CSV: each
	# assignment is independent, so the same student appearing in
	# CSV 01 and CSV 02 is normal (one submission per assignment),
	# not a duplicate. Duplicate detection only catches two form rows
	# inside the same CSV resolving to the same Roster RUID.
	# Non-interactive: the downloader quarantines on miss instead of
	# prompting.
	term = protein_images_path.get_active_term(args.term)
	roster = roster_matching.load_roster(
		str(protein_images_path.get_roster_csv(term)))
	matcher = roster_matching.RosterMatcher(roster=roster, interactive=False)

	for csv_path in csv_paths:
		console.print(f"=== {csv_path}", style="bold cyan")
		assigned_ruids: set = set()
		process_one_csv(str(csv_path), args, image_hashes, hashes_changed,
			open_browser, matcher, assigned_ruids)

	if hashes_changed[0]:
		with open(image_hashes_yaml, 'w') as f:
			yaml.dump(image_hashes, f)

