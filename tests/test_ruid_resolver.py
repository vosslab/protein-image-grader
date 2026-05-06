"""
Tests for protein_image_grader.ruid_resolver --
resolve_form_row_to_roster_row() and the result dataclasses.

Tests construct a small in-memory roster + matcher and exercise the
function rather than touching real roster.csv files.
"""

import protein_image_grader.roster_matching as roster_matching
import protein_image_grader.ruid_resolver as ruid_resolver


def _make_matcher() -> roster_matching.RosterMatcher:
	# Two-row in-memory roster matching roster_matching.load_roster shape.
	def row(student_id, first, last, username):
		first_n = roster_matching.normalize_name_text(first)
		last_n = roster_matching.normalize_name_text(last)
		return {
			"student_id": student_id,
			"first_name": first_n,
			"last_name": last_n,
			"username": roster_matching.normalize_username(username),
			"alias": "",
			"full_name": (first_n + " " + last_n).strip(),
		}
	roster = {
		900000002: row(900000002, "Alice", "Smith", "asmith"),
		900000004: row(900000004, "Bob", "Jones", "bjones"),
	}
	return roster_matching.RosterMatcher(roster=roster, interactive=False)


def _form_row(form_ruid, first, last, username):
	return {
		"form_ruid": form_ruid, "first_name": first,
		"last_name": last, "username": username,
	}


def test_resolve_typed_ruid_on_roster():
	# When the typed RUID is itself on the roster, resolution returns it.
	matcher = _make_matcher()
	assigned: set = set()
	result = ruid_resolver.resolve_form_row_to_roster_row(
		_form_row("900000002", "Alice", "Smith", "asmith"),
		matcher, assigned,
	)
	assert isinstance(result, ruid_resolver.ResolvedStudent)
	assert result.roster_ruid == 900000002
	assert 900000002 in assigned


def test_resolve_wrong_typed_ruid_uses_name_match():
	# Typed RUID is wrong (not on roster) but the name matches a roster
	# row exactly: resolver returns the ROSTER RUID, not the typed one.
	matcher = _make_matcher()
	result = ruid_resolver.resolve_form_row_to_roster_row(
		_form_row("900999999", "Alice", "Smith", "asmith"),
		matcher, set(),
	)
	assert isinstance(result, ruid_resolver.ResolvedStudent)
	assert result.roster_ruid == 900000002
	assert result.form_ruid == "900999999"


def test_resolve_bogus_row_returns_unresolved():
	matcher = _make_matcher()
	assigned: set = set()
	result = ruid_resolver.resolve_form_row_to_roster_row(
		_form_row("900111111", "Nobody", "Whatsoever", "nobody"),
		matcher, assigned,
	)
	assert isinstance(result, ruid_resolver.UnresolvedStudent)
	# No claim on assigned set when resolution fails.
	assert assigned == set()


def test_duplicate_roster_ruid_in_one_run():
	# Two different Form RUIDs cannot both resolve to the same Roster
	# RUID in one run; the second resolve returns Unresolved(duplicate).
	matcher = _make_matcher()
	assigned: set = set()
	first = ruid_resolver.resolve_form_row_to_roster_row(
		_form_row("900000002", "Alice", "Smith", "asmith"),
		matcher, assigned,
	)
	assert isinstance(first, ruid_resolver.ResolvedStudent)

	second = ruid_resolver.resolve_form_row_to_roster_row(
		_form_row("900111111", "Alice", "Smith", "asmith"),
		matcher, assigned,
	)
	assert isinstance(second, ruid_resolver.UnresolvedStudent)
	assert second.reason == "duplicate"


def test_unresolved_carries_top_candidates():
	# UnresolvedStudent.candidates must contain the matcher's top-N
	# roster candidates so quarantine.log has triage data. Use a name
	# distinct enough from any roster row that no auto-match path
	# (exact, gap-based, or fuzzy) can resolve it, forcing the
	# unresolved branch with non-empty candidates.
	matcher = _make_matcher()
	result = ruid_resolver.resolve_form_row_to_roster_row(
		_form_row("900111111", "Zephyrina", "Quux", "zquux"),
		matcher, set(),
	)
	assert isinstance(result, ruid_resolver.UnresolvedStudent)
	# At least one candidate from the roster surfaced.
	assert result.candidates
	for cand_ruid, cand_name, cand_score in result.candidates:
		assert isinstance(cand_ruid, int)
		assert cand_name
		assert 0.0 <= cand_score <= 1.0
