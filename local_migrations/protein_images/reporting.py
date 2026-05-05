"""
Report dataclass and serialization for the migration planner.

Kept separate so the planner has no opinion on output format.
"""

import dataclasses
import pathlib

import local_migrations.protein_images.classifier as classifier


@dataclasses.dataclass(frozen=True)
class Report:
	"""Grouped classification result for one dry run."""

	data_root: pathlib.Path
	active_term: str
	generated_at_utc: str
	high_confidence_moves: tuple[classifier.Move, ...]
	legacy_review_moves: tuple[classifier.Move, ...]
	unchanged: tuple[classifier.Move, ...]


def _move_to_dict(move: classifier.Move, data_root: pathlib.Path) -> dict:
	# Render paths as strings relative to data_root when possible so reports
	# stay readable across machines.
	def _rel(path: pathlib.Path | None) -> str | None:
		if path is None:
			return None
		if path.is_absolute():
			try:
				return str(path.relative_to(data_root))
			except ValueError:
				return str(path)
		return str(path)

	entry = {
		"src": _rel(move.src),
		"dst": _rel(move.dst),
		"confidence": move.confidence,
		"bucket": move.bucket,
		"evidence": list(move.evidence),
	}
	return entry


def report_to_dict(report: Report) -> dict:
	"""Serialize a Report into a dict suitable for YAML/JSON."""
	payload = {
		"data_root": str(report.data_root),
		"active_term": report.active_term,
		"generated_at_utc": report.generated_at_utc,
		"high_confidence_moves": [
			_move_to_dict(m, report.data_root) for m in report.high_confidence_moves
		],
		"legacy_review_moves": [
			_move_to_dict(m, report.data_root) for m in report.legacy_review_moves
		],
		"unchanged": [
			_move_to_dict(m, report.data_root) for m in report.unchanged
		],
	}
	return payload
