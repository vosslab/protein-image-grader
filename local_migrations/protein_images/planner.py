"""
Dry-run planner for the Protein_Images/ migration.

Walks only the top level of the data root, calls the classifier for each
entry, and groups proposed moves into a Report dataclass. Performs no
filesystem mutations. Serialization lives in reporting.py.
"""

import datetime
import pathlib

import local_migrations.protein_images.classifier as classifier
import local_migrations.protein_images.reporting as reporting


def plan(data_root: pathlib.Path, active_term: str) -> reporting.Report:
	"""Walk top level of data_root and classify every entry."""
	if not data_root.is_dir():
		raise NotADirectoryError(f"data_root is not a directory: {data_root}")

	entries = sorted(data_root.iterdir(), key=lambda p: p.name)
	high: list[classifier.Move] = []
	low: list[classifier.Move] = []
	unchanged: list[classifier.Move] = []
	for entry in entries:
		move = classifier.classify(entry, data_root, active_term)
		if move.bucket == "high_confidence_moves":
			high.append(move)
		elif move.bucket == "legacy_review_moves":
			low.append(move)
		else:
			unchanged.append(move)

	now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
	return reporting.Report(
		data_root=data_root,
		active_term=active_term,
		generated_at_utc=now_utc,
		high_confidence_moves=tuple(high),
		legacy_review_moves=tuple(low),
		unchanged=tuple(unchanged),
	)
