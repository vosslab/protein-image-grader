"""Single source of truth for the saved-image filename shape.

Both `download_submission_images` and `read_save_images` must agree on the
on-disk filename for a student's submission, otherwise the grader's cache
glob misses files the downloader saved and re-downloads every image. Keep
the format here so any change touches one file.
"""

# Standard Library
import os

# local repo modules
import protein_image_grader.rmspaces


#============================================
def build_raw_image_filename(ruid: int, image_number: int,
		original_filename: str) -> str:
	"""
	Build the canonical raw-image filename used by both downloader and grader.

	Shape: <RUID>-protein<NN>-<basename><extension>

	- ruid is the Roster RUID (resolved against roster.csv).
	- image_number is the assignment number 1..20 (zero-padded to two digits).
	- original_filename is the basename returned by Google Drive; it is
	  lowercased and run through `rmspaces.cleanName` for ASCII safety.
	- Extensions other than .png/.jpg are coerced to .jpg to match the
	  downloader's historical behavior.
	"""
	# normalize the original filename to lowercase before splitting
	filename = original_filename.lower()
	basename = os.path.splitext(filename)[0]
	# strip spaces and non-ASCII via the shared cleanName helper
	basename = protein_image_grader.rmspaces.cleanName(basename)
	extension = os.path.splitext(filename)[-1]
	# assemble the canonical shape; downloader and grader both call this
	result = f"{ruid}-protein{image_number:02d}-{basename}{extension}"
	# coerce unknown extensions to .jpg so downstream PIL.open never trips
	if not result.endswith('.jpg') and not result.endswith('.png'):
		result = os.path.splitext(result)[0] + '.jpg'
	return result


#============================================
def build_raw_image_prefix(ruid: int, image_number: int) -> str:
	"""
	Build the filename prefix used to glob for an existing saved image.

	Shape: <RUID>-protein<NN>-

	The grader globs `<prefix>*` to find a previously downloaded file
	regardless of the original Google Drive basename.
	"""
	prefix = f"{ruid}-protein{image_number:02d}-"
	return prefix
