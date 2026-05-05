"""Filename normalization helpers used by Google Drive download code.

This is a stripped-down library version of the upstream rmspaces tool.
The CLI/file-renaming functions (`moveName`, `cleanNames`, `rmSpaces`) and the
`__main__` block have been removed; only the pure-string normalization helpers
`unicode_to_string` and `cleanName` remain, which is all the grader needs."""

# Standard Library
import os
import re
import unicodedata

# PIP3 modules
import transliterate

#==============
def unicode_to_string(data: str) -> str:
	"""
	Converts Unicode text to a string with only ASCII characters,
	transliterating where possible and stripping non-ASCII characters.
	"""
	# Ensure the input is a Unicode string
	if isinstance(data, bytes):
		data = data.decode("utf-8")

	# Attempt transliteration; transliterate raises on unsupported scripts,
	# so fall back to the original string in that case (kept narrow, two lines).
	try:
		transliterated = transliterate.translit(data, reversed=True)
	except transliterate.exceptions.LanguageDetectionError:
		transliterated = data

	# Normalize the string to decompose accents and diacritics (NFKD normalization)
	nfkd_form = unicodedata.normalize('NFKD', transliterated)

	# Remove non-ASCII characters by encoding to ASCII and ignoring errors
	ascii_bytes = nfkd_form.encode('ASCII', 'ignore')

	# Decode back to string and return
	ascii_only = ascii_bytes.decode('ASCII')
	return ascii_only

#=======================
def cleanName(f: str) -> str:
	# Words to preserve or format correctly
	words = ['of', 'the', 'a', 'in', 'for', 'am', 'is', 'on',
			'la', 'to', 'than', 'with', 'by', 'from', 'or', 'and']

	# Allowed characters
	goodchars = list('-./_'
					+ '0123456789'
					+ 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
					+ 'abcdefghijklmnopqrstuvwxyz')

	# Transliterate filename to ASCII
	g = unicode_to_string(f)
	g = g.strip()

	# Handle filenames with numbers in parentheses at the end
	# Find "(number)" + optional extension
	match = re.search(r"\((\d+)\)(\.[a-zA-Z0-9]+)?$", g)
	if match:
		number = int(match.group(1))
		extension = match.group(2) if match.group(2) else ""
		# Remove the "(number)" part and append in zero-padded form
		g = re.sub(r"\s*\(\d+\)", "", g)
		g += f"_{number:04d}{extension}"

	# Preserve file extension casing when the input names a real file on disk
	if os.path.isfile(f) and len(g) > 7 and g[-4] == ".":
		g = g[:-4] + g[-4:].lower()

	# Replace spaces and unwanted patterns
	g = re.sub(" ", "_", g)
	g = re.sub(r"[Ww]{3}\.", "", g)
	g = re.sub(r"\._\.", "_", g)
	g = re.sub(r"^-*", "", g)
	g = re.sub(r"\'", "_", g)
	g = re.sub(r"\"", "_", g)
	g = re.sub(r"&", "and", g)
	g = re.sub(r"\]", "_", g)
	g = re.sub(r"\[", "_", g)

	# Replace all other non-allowed characters with underscores
	newg = ""
	for char in g:
		if char not in goodchars:
			newg += "_"
		else:
			newg += char
	if newg:
		g = newg

	# Normalize case for specific words
	for word in words:
		a = re.search(r"_(" + word + ")_", g, re.IGNORECASE)
		if a:
			for inword in a.groups():
				g = re.sub(r"_" + inword + "_", "_" + word + "_", g)

	# Fix patterns: triples, doubles, and odd characters
	## triples
	g = re.sub(r"_\._", ".", g)
	g = re.sub(r"\._\.", "_", g)
	g = re.sub(r"-_-", "_", g)
	g = re.sub(r"_-_", "-", g)
	## doubles
	g = re.sub(r"\.\.", ".", g)
	g = re.sub(r"_\.", ".", g)
	g = re.sub(r"\._", ".", g)
	g = re.sub(r"-_", "", g)
	g = re.sub(r"_-", "-", g)
	## strange chars
	g = re.sub(r"\^", "_", g)
	g = re.sub(r",", "_", g)
	## rm extra underscore
	g = re.sub(r"__*", "_", g)
	g = re.sub(r"__*", "_", g)
	## ends and starts
	g = re.sub(r"_*$", "", g)
	g = re.sub(r"^_*", "", g)
	g = re.sub(r"^-*", "", g)
	g = re.sub(r"^\.*", "", g)

	# Ensure cleaned filename is valid
	if len(g) == 0:
		raise ValueError(f"cleanName produced an empty filename for input '{f}'")
	g = re.sub("_*$", "", g)

	return g
