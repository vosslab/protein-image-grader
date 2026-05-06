"""
Resolve standard identity columns from a Google Form CSV header row by
normalized keyword-set matching, not by YAML keys or numeric position.

WHY keyword sets, not exact-string match: Google Forms wording drifts
between semesters (Username vs Email Address, Enter your RUID vs
Student ID); a single typo or trailing-space tweak should not break a
whole semester. Token-set membership is robust to wording drift while
still rejecting ambiguous matches.

Canonical output keys are the only spellings downstream code may use:
timestamp, Username, First Name, Last Name, Student ID. Assignment-
specific fields (image url, extra description) stay in the per-image
spec YAML and are NOT resolved here.

To extend: add a new alias keyword set to STANDARD_META_COLUMNS. Each
keyword set is matched as a token-set: every keyword must appear as a
whole-word token in the normalized header. Example: to recognize
"Net ID" as a Username column, append `["net", "id"]` to the
"Username" alias list.

Scan window: the resolver only inspects the first IDENTITY_PREFIX_COLUMNS
header cells. Identity columns always occupy the start of the form CSV,
and capping the scan prevents question columns like "What is the FULL
NAME of the LAST AUTHOR..." from token-matching the ["last", "name"]
alias and triggering false ambiguity errors. If a future form ever
places an identity column past column 5, raise IDENTITY_PREFIX_COLUMNS
or pass search_limit explicitly at the call site.
"""

# Standard Library
import re
import unicodedata

# PIP3 modules
import unidecode


#============================================
# Each canonical key maps to a list of alias keyword sets. A header
# matches an alias when every keyword in the set appears as a token in
# the normalized header. Multi-token aliases (e.g. ["email", "address"])
# protect against future "Backup Email" / "Contact Email" columns being
# matched against Username.
STANDARD_META_COLUMNS = {
	"timestamp":   [["timestamp"]],
	"Username":    [["username"], ["email", "address"]],
	"First Name":  [["first", "name"]],
	"Last Name":   [["last", "name"]],
	"Student ID":  [["ruid"], ["student", "id"]],
}

# Legacy meta-column key names that older spec YAMLs may still carry.
# `email` was the buggy name for what should have been `Username`; the
# rest are the standard identity keys whose mapping is now derived
# from the CSV header. Used by file_io_protein to detect and warn on
# stale entries during the schema transition.
LEGACY_YAML_META_KEYS = frozenset(
	{"timestamp", "Username", "First Name", "Last Name", "Student ID", "email"}
)


#============================================
def _tokenize_header(text: str) -> list:
	"""
	Normalize a header cell into a list of lowercase alphanumeric tokens.

	Args:
		text: Raw header string from the CSV.

	Returns:
		List of lowercase alphanumeric tokens. Empty list for a blank
		input. Punctuation and whitespace are collapsed.
	"""
	# Unicode NFKC + ASCII transliteration matches roster_matching.
	cleaned = unicodedata.normalize("NFKC", text)
	cleaned = unidecode.unidecode(cleaned).lower()
	# Replace any non-alphanumeric run with a single space, then split.
	cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned).strip()
	if not cleaned:
		return []
	return cleaned.split()


#============================================
def header_matches_alias(tokens: list, keywords: list) -> bool:
	"""
	Test whether every alias keyword appears as a token in a header.

	Args:
		tokens: Output of _tokenize_header for one CSV header cell.
		keywords: One alias keyword set from STANDARD_META_COLUMNS.

	Returns:
		True iff every keyword in the alias set is present as a
		whole-word token in `tokens`.
	"""
	# Token-set membership: simpler and safer than substring search.
	return all(keyword in tokens for keyword in keywords)


#============================================
# Identity columns (timestamp, Username, First/Last Name, Student ID) are
# always positioned at the start of the Google Form CSV, before any
# assignment-specific question columns. Scanning the whole header row
# causes false positives such as "What is the FULL NAME of the LAST
# AUTHOR..." matching the ["last", "name"] alias for Last Name. Capping
# the search to the first IDENTITY_PREFIX_COLUMNS columns keeps matching
# robust without requiring the caller to know question-column indices.
IDENTITY_PREFIX_COLUMNS = 6


#============================================
def resolve_meta_columns(
	header_list: list,
	required: set = None,
	search_limit: int = IDENTITY_PREFIX_COLUMNS,
) -> dict:
	"""
	Resolve standard identity columns from a CSV header row.

	Args:
		header_list: list of header cells as read from row 0 of the
			form CSV.
		required: optional set of canonical keys that the caller
			treats as mandatory. None (the default) means "all five
			canonical keys are required". Pass a smaller subset
			(e.g. {"Username", "First Name"}) when the caller is
			willing to fall back for the rest. Pass an empty set to
			skip the missing-key check entirely; the caller can then
			inspect the returned dict for which keys actually
			resolved.
		search_limit: maximum number of header cells to scan from the
			start of the row. Defaults to IDENTITY_PREFIX_COLUMNS. Pass
			a larger value only if a future form places an identity
			column past the standard prefix; pass len(header_list) to
			disable the cap entirely (mainly useful in tests that need
			to confirm a question column would collide if not capped).

	Returns:
		dict mapping each canonical key that was successfully
		resolved to the zero-based column index in header_list.
		Missing canonical keys are simply absent from the dict.

	Raises:
		ValueError: on ambiguity (a canonical key matches two or more
			columns) or when a member of `required` is missing.
			Ambiguity errors list every matching column; missing-key
			errors list every missing required key in one message,
			ordered by the canonical key order in
			STANDARD_META_COLUMNS.
	"""
	if required is None:
		required = set(STANDARD_META_COLUMNS.keys())

	# Pre-tokenize once. Cap scan to identity prefix so question columns
	# like "What is the FULL NAME of the LAST AUTHOR..." cannot collide
	# with identity aliases such as ["last", "name"].
	scan_end = min(search_limit, len(header_list))
	tokenized = [_tokenize_header(cell) for cell in header_list[:scan_end]]

	resolved = {}
	for canonical_key, alias_list in STANDARD_META_COLUMNS.items():
		# Find every header cell that matches at least one alias.
		matches = []
		for index, tokens in enumerate(tokenized):
			for keywords in alias_list:
				if header_matches_alias(tokens, keywords):
					matches.append(index)
					break
		if len(matches) == 0:
			continue
		if len(matches) > 1:
			# Ambiguity: refuse to silently pick.
			matched_headers = [header_list[i] for i in matches]
			raise ValueError(
				f"Ambiguous form columns for canonical key '{canonical_key}': "
				f"matched {matched_headers}. Each canonical identity column "
				f"must match exactly one CSV header."
			)
		resolved[canonical_key] = matches[0]

	missing = [key for key in required if key not in resolved]
	if missing:
		# Stable order matching STANDARD_META_COLUMNS for readable errors.
		ordered_missing = [k for k in STANDARD_META_COLUMNS.keys() if k in missing]
		raise ValueError(
			"Required form columns not found: "
			+ ", ".join(ordered_missing)
			+ f". Header row was: {header_list}."
		)

	return resolved
