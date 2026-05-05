#!/usr/bin/env python3
"""
Migration tool for Protein_Images/.

Two modes:
  --dry-run (default): walks the top level of the data root and emits a
    YAML report grouping every entry into high_confidence_moves,
    legacy_review_moves, or unchanged. No filesystem mutations.
  --apply: reads a previously saved report (--report-in) and performs the
    moves it lists. Refuses to run without a verified backup
    (--backup-path), which may be a sibling backup directory or a tar
    archive (e.g., protein_image.tar). Writes an applied-report YAML.
"""

import argparse
import pathlib
import sys

import yaml

import rich.console
import rich.table

import local_migrations.protein_images.executor as executor
import local_migrations.protein_images.planner as planner
import local_migrations.protein_images.reporting as reporting
import protein_image_grader.protein_images_path as protein_images_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Migration tool for Protein_Images/.",
	)
	parser.add_argument(
		"-t", "--term", dest="term", type=str, default=None,
		help="Active term override (e.g., spring_2026). "
			"Defaults to Protein_Images/active_term.txt.",
	)
	mode = parser.add_mutually_exclusive_group()
	mode.add_argument(
		"-d", "--dry-run", dest="mode", action="store_const", const="dry_run",
		help="Plan moves and write a YAML report (default).",
	)
	mode.add_argument(
		"-a", "--apply", dest="mode", action="store_const", const="apply",
		help="Apply moves listed in --report-in (requires --backup-path).",
	)
	parser.set_defaults(mode="dry_run")
	parser.add_argument(
		"-r", "--report-out", dest="report_out", type=str, default=None,
		help="Path to write the YAML dry-run report. Required for --dry-run.",
	)
	parser.add_argument(
		"-i", "--report-in", dest="report_in", type=str, default=None,
		help="Path to a reviewed dry-run report. Required for --apply.",
	)
	parser.add_argument(
		"-b", "--backup-path", dest="backup_path", type=str, default=None,
		help="Sibling backup directory or .tar archive. Required for --apply.",
	)
	parser.add_argument(
		"-o", "--applied-report-out", dest="applied_report_out",
		type=str, default=None,
		help="Where to write the applied report YAML. "
			"Defaults to <report-in>.applied.yml.",
	)
	args = parser.parse_args(argv)
	if args.mode == "dry_run" and args.report_out is None:
		parser.error("--dry-run requires --report-out")
	if args.mode == "apply":
		if args.report_in is None:
			parser.error("--apply requires --report-in")
		if args.backup_path is None:
			parser.error("--apply requires --backup-path")
	return args


def _print_dry_run_table(
	report: reporting.Report, console: rich.console.Console,
) -> None:
	# Summary header
	console.print(
		f"[bold]Migration dry-run[/bold]  data_root={report.data_root}  "
		f"active_term={report.active_term}  generated_at={report.generated_at_utc}"
	)

	def _add_section(title: str, moves) -> None:
		table = rich.table.Table(title=f"{title} ({len(moves)})")
		table.add_column("src", overflow="fold")
		table.add_column("dst", overflow="fold")
		table.add_column("confidence")
		table.add_column("evidence", overflow="fold")
		for move in moves:
			src_rel = str(move.src.relative_to(report.data_root))
			dst_rel = (
				str(move.dst.relative_to(report.data_root)) if move.dst else "-"
			)
			evidence = "\n".join(move.evidence)
			table.add_row(src_rel, dst_rel, move.confidence, evidence)
		console.print(table)

	_add_section("High-confidence moves", report.high_confidence_moves)
	_add_section("Legacy review moves", report.legacy_review_moves)
	_add_section("Unchanged (already canonical)", report.unchanged)


def _run_dry_run(args: argparse.Namespace, console: rich.console.Console) -> int:
	data_root = protein_images_path.get_protein_images_dir()
	active_term = protein_images_path.get_active_term(args.term)
	report = planner.plan(data_root, active_term)
	payload = reporting.report_to_dict(report)
	report_path = pathlib.Path(args.report_out)
	report_path.parent.mkdir(parents=True, exist_ok=True)
	report_path.write_text(yaml.safe_dump(payload, sort_keys=False))
	_print_dry_run_table(report, console)
	console.print(f"[green]Wrote dry-run report:[/green] {report_path}")
	console.print(
		"[yellow]Use --apply --report-in <path> --backup-path <dir-or-tar> "
		"to perform the moves.[/yellow]"
	)
	return 0


def _run_apply(args: argparse.Namespace, console: rich.console.Console) -> int:
	data_root = protein_images_path.get_protein_images_dir()
	report_path = pathlib.Path(args.report_in)
	backup_path = pathlib.Path(args.backup_path)
	if args.applied_report_out:
		applied_path = pathlib.Path(args.applied_report_out)
	else:
		applied_path = report_path.with_suffix(report_path.suffix + ".applied.yml")
	console.print(
		f"[bold]Applying migration[/bold]  data_root={data_root}  "
		f"report_in={report_path}  backup={backup_path}"
	)
	applied = executor.apply(
		data_root=data_root,
		report_path=report_path,
		backup_path=backup_path,
		output_report_path=applied_path,
	)
	summary = applied["summary"]
	console.print(
		f"[bold]Applied:[/bold] {summary['applied']}  "
		f"[yellow]Skipped:[/yellow] {summary['skipped']}  "
		f"[red]Errors:[/red] {summary['errors']}  "
		f"[dim](total {summary['total']})[/dim]"
	)
	console.print(f"[green]Wrote applied report:[/green] {applied_path}")
	return 0 if summary["errors"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
	args = parse_args(argv)
	console = rich.console.Console()
	if args.mode == "dry_run":
		return _run_dry_run(args, console)
	return _run_apply(args, console)


if __name__ == "__main__":
	sys.exit(main())
