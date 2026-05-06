"""
Single-function form-row -> roster-row resolver.

Both the downloader and the grader need the same workflow:
take one form row (First Name, Last Name, Username, typed Form RUID),
resolve it against the roster via `roster_matching.RosterMatcher`, and
return the authoritative Roster RUID (or a quarantine record).

This module owns that workflow once. The generic fuzzy matching lives
in `roster_matching.py`; this is the project-specific shape on top.

Public surface:
- ResolvedStudent	dataclass returned on success.
- UnresolvedStudent	dataclass returned on failure (caller decides
			quarantine vs raise).
- resolve_form_row_to_roster_row(form_row, matcher, assigned_ruids)
			one function. Mutates `assigned_ruids` to detect
			same-run duplicates (two Form RUIDs both mapping to
			the same Roster RUID).

There is no per-term alias cache: typed Form RUIDs that miss the roster
are one-off student typos, surfaced in `quarantine.log`, and resolved
on the next clean re-run after the roster (or the form CSV) is fixed.
"""

# Standard Library
import dataclasses

# local repo modules
import protein_image_grader.roster_matching as roster_matching


#============================================
@dataclasses.dataclass
class ResolvedStudent:
	"""Successful resolution: roster_ruid is authoritative and never None."""
	roster_ruid: int
	form_ruid: str
	full_name: str
	reason: str
	score: float


#============================================
@dataclasses.dataclass
class UnresolvedStudent:
	"""Failed resolution: caller decides whether to quarantine or raise.

	`candidates` carries the top-N (roster_ruid, full_name, score) tuples
	the matcher considered, so the operator has actionable triage data
	in quarantine.log instead of a bare `reason` and `score`.
	"""
	form_ruid: str
	first_name: str
	last_name: str
	username: str
	reason: str
	score: float
	candidates: list[tuple[int, str, float]] = dataclasses.field(default_factory=list)


#============================================
def resolve_form_row_to_roster_row(form_row: dict,
		matcher: roster_matching.RosterMatcher,
		assigned_ruids: set) -> ResolvedStudent | UnresolvedStudent:
	"""
	Resolve one form row to a roster row.

	Args:
		form_row: dict with all four required keys 'form_ruid',
			'first_name', 'last_name', 'username' (all str). Direct
			key access; a missing key is a caller bug and will raise
			KeyError loudly per docs/PYTHON_STYLE.md.
		matcher: pre-built RosterMatcher (constructed once per run by
			the caller; build is expensive due to roster indexing).
		assigned_ruids: set of Roster RUIDs already claimed in this
			run; mutated to add the new claim on success. Two Form
			RUIDs that both resolve to the same Roster RUID return
			UnresolvedStudent(reason='duplicate') for the second one.

	Returns ResolvedStudent on success, UnresolvedStudent on miss or
	duplicate.
	"""
	# `form_ruid` may be None when the Google Form cell was left blank;
	# that is the only legitimately optional case, hence `or ""`.
	typed = (form_row["form_ruid"] or "").strip()
	first_name = form_row["first_name"]
	last_name = form_row["last_name"]
	username = form_row["username"]

	matched_id, reason, score = matcher.match(
		username=username, first_name=first_name,
		last_name=last_name, student_id=typed,
	)
	if matched_id is None:
		# Top-N roster candidates so quarantine.log carries triage-grade
		# data (which roster rows the matcher considered, with their
		# fuzzy scores) instead of a bare reason and a single score.
		candidates = _top_candidates(matcher, form_row)
		return UnresolvedStudent(
			form_ruid=typed, first_name=first_name,
			last_name=last_name, username=username,
			reason=reason, score=float(score), candidates=candidates,
		)

	roster_ruid = int(matched_id)
	if roster_ruid in assigned_ruids:
		# A second form row resolved to a roster row already claimed
		# this run -- two students typed each other's RUID, or one
		# student submitted twice. Quarantine the later row; the
		# operator decides which submission is authoritative.
		return UnresolvedStudent(
			form_ruid=typed, first_name=first_name,
			last_name=last_name, username=username,
			reason="duplicate", score=float(score),
		)
	assigned_ruids.add(roster_ruid)

	# Direct key access: the matcher just confirmed roster_ruid is in
	# matcher.roster, so failing loud here would be a real bug.
	full_name = matcher.roster[roster_ruid]["full_name"]
	return ResolvedStudent(
		roster_ruid=roster_ruid, form_ruid=typed,
		full_name=full_name, reason=str(reason), score=float(score),
	)


#============================================
def _top_candidates(matcher: roster_matching.RosterMatcher,
		form_row: dict) -> list[tuple[int, str, float]]:
	"""
	Return the top-N roster rows the matcher would have considered for
	this form row, as (roster_ruid, full_name, score) tuples. Used to
	populate UnresolvedStudent.candidates so quarantine.log carries
	triage data instead of just a bare reason and score.
	"""
	# Same required-key contract as resolve_form_row_to_roster_row;
	# direct access fails loud on caller bugs.
	sub = {
		"first_name": form_row["first_name"],
		"last_name": form_row["last_name"],
		"username": form_row["username"],
		"student_id": (form_row["form_ruid"] or "").strip(),
	}
	ranked = roster_matching.rank_candidates(
		sub, matcher.roster, matcher.candidate_count,
	)
	out = []
	for ruid, score in ranked:
		# rank_candidates iterates matcher.roster, so direct key access
		# is correct; fail loud if not.
		full_name = matcher.roster[ruid]["full_name"]
		out.append((int(ruid), full_name, float(score)))
	return out
