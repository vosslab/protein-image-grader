"""
Executor for the migration apply step.

Reads a previously saved dry-run report and performs the moves listed in
its high_confidence_moves and legacy_review_moves groups. Refuses to run
without a verified backup. Records per-item outcomes for the applied
report.
"""

import dataclasses
import datetime
import pathlib
import shutil

import yaml

import local_migrations.protein_images.backup_check as backup_check


@dataclasses.dataclass(frozen=True)
class AppliedMove:
	src: str
	dst: str
	confidence: str
	bucket: str
	status: str  # "applied" | "skipped" | "error"
	detail: str  # human-readable info (error message, skip reason, "ok")


def _resolve_relative(data_root: pathlib.Path, value: str) -> pathlib.Path:
	# Reports store relative paths; absolute paths fall through unchanged.
	candidate = pathlib.Path(value)
	if candidate.is_absolute():
		return candidate
	return data_root / candidate


def _is_case_only_rename(src: pathlib.Path, dst: pathlib.Path) -> bool:
	# True if src and dst resolve to the same inode (case-insensitive FS) but
	# their names differ only by case. We must use a two-step rename in that
	# case because a naive dst.exists() check returns True for the same path.
	if src.parent != dst.parent:
		return False
	if src.name == dst.name:
		return False
	if src.name.lower() != dst.name.lower():
		return False
	return src.exists() and dst.exists() and src.samefile(dst)


def _apply_one(data_root: pathlib.Path, item: dict) -> AppliedMove:
	src_text = item["src"]
	dst_text = item["dst"]
	bucket = item["bucket"]
	confidence = item["confidence"]
	if dst_text is None:
		return AppliedMove(
			src=src_text, dst="", confidence=confidence, bucket=bucket,
			status="skipped", detail="report entry has no dst",
		)
	src = _resolve_relative(data_root, src_text)
	dst = _resolve_relative(data_root, dst_text)
	if not src.exists() and not src.is_symlink():
		return AppliedMove(
			src=src_text, dst=dst_text, confidence=confidence, bucket=bucket,
			status="skipped", detail=f"src missing at apply time: {src}",
		)
	# Case-only rename on a case-insensitive FS: rename via a temp name.
	if _is_case_only_rename(src, dst):
		temp = src.with_name(src.name + ".caseswap.tmp")
		shutil.move(str(src), str(temp))
		shutil.move(str(temp), str(dst))
		return AppliedMove(
			src=src_text, dst=dst_text, confidence=confidence, bucket=bucket,
			status="applied", detail="ok (case-only rename)",
		)
	if dst.exists() or dst.is_symlink():
		return AppliedMove(
			src=src_text, dst=dst_text, confidence=confidence, bucket=bucket,
			status="error", detail=f"dst already exists: {dst}",
		)
	dst.parent.mkdir(parents=True, exist_ok=True)
	# shutil.move handles cross-device by falling back to copy+remove and
	# preserves mtime when staying on the same FS.
	shutil.move(str(src), str(dst))
	return AppliedMove(
		src=src_text, dst=dst_text, confidence=confidence, bucket=bucket,
		status="applied", detail="ok",
	)


def apply(
	data_root: pathlib.Path,
	report_path: pathlib.Path,
	backup_path: pathlib.Path,
	output_report_path: pathlib.Path,
) -> dict:
	"""Apply the moves listed in report_path. Returns the applied-report dict."""
	if not report_path.is_file():
		raise FileNotFoundError(f"Report not found: {report_path}")
	report_payload = yaml.safe_load(report_path.read_text())
	if report_payload is None:
		raise ValueError(f"Report is empty: {report_path}")
	# Verify backup before any mutation.
	backup_info = backup_check.verify_backup(backup_path)
	# Apply both move buckets; preserve order.
	to_apply: list[dict] = []
	to_apply.extend(report_payload.get("high_confidence_moves") or [])
	to_apply.extend(report_payload.get("legacy_review_moves") or [])
	results: list[AppliedMove] = []
	for item in to_apply:
		results.append(_apply_one(data_root, item))
	now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
	applied_payload = {
		"data_root": str(data_root),
		"report_in": str(report_path),
		"backup": backup_info,
		"applied_at_utc": now_utc,
		"summary": {
			"total": len(results),
			"applied": sum(1 for r in results if r.status == "applied"),
			"skipped": sum(1 for r in results if r.status == "skipped"),
			"errors": sum(1 for r in results if r.status == "error"),
		},
		"items": [dataclasses.asdict(r) for r in results],
	}
	output_report_path.parent.mkdir(parents=True, exist_ok=True)
	output_report_path.write_text(yaml.safe_dump(applied_payload, sort_keys=False))
	return applied_payload
