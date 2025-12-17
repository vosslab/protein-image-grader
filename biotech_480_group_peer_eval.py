#!/usr/bin/env python3

# Standard Library
import argparse
import csv
import os
import re
import statistics

#============================================
def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		argparse.Namespace: Parsed args.
	"""
	parser = argparse.ArgumentParser(
		description="Process peer eval CSV and compute per-group scores."
	)

	parser.add_argument(
		"-i", "--input", dest="input_files", required=True, nargs="+",
		help="Input CSV file(s) exported from Google Forms."
	)
	parser.add_argument(
		"-o", "--output", dest="output_csv", required=True,
		help="Output CSV with group summary."
	)

	parser.add_argument(
		"-b", "--week1-boost", dest="week1_boost", type=float, default=0.10,
		help="Add this to AVG score for Week 1 groups (default: 0.10)."
	)
	parser.add_argument(
		"-m", "--max-rating", dest="max_rating", type=float, default=4.0,
		help="Maximum possible rating numeric value (default: 4.0)."
	)

	parser.add_argument(
		"-w", "--award-weight", dest="award_weight", type=float, default=0.5,
		help="Weight of award score in combined score (default: 0.5)."
	)
	parser.add_argument(
		"-r", "--rating-weight", dest="rating_weight", type=float, default=0.5,
		help="Weight of rating score in combined score (default: 0.5)."
	)

	parser.add_argument(
		"-p", "--points-max", dest="points_max", type=float, default=24.0,
		help="Max points to scale to (default: 24.0)."
	)
	parser.add_argument(
		"-s", "--self-penalty", dest="penalty_per_self_vote", type=int, default=1,
		help="Penalty per self-award vote (default: 1)."
	)

	args = parser.parse_args()
	return args

#============================================
def norm_text(value: str) -> str:
	"""
	Normalize a string for comparisons.

	Args:
		value (str): Input.

	Returns:
		str: Normalized text.
	"""
	if value is None:
		return ""
	text = str(value)
	text = text.strip().lower()
	text = re.sub(r"\s+", " ", text)
	return text

#============================================
def rating_to_num(value: str) -> float | None:
	"""
	Map rubric text to numeric values.

	Supports:
		amazing -> 4
		great   -> 3
		good    -> 2
		poor    -> 1
	Also supports longer strings that start with these words.

	Args:
		value (str): Rating cell.

	Returns:
		float | None: Numeric rating, or None if missing/unrecognized.
	"""
	if value is None:
		return None

	text = norm_text(value)
	if text == "":
		return None

	if text.startswith("amazing"):
		return 4.0
	if text.startswith("great"):
		return 3.0
	if text.startswith("good"):
		return 2.0
	if text.startswith("poor"):
		return 1.0

	return None

# Simple sanity check
_result = rating_to_num("amazing - they are going to be printing money")
assert _result == 4.0

#============================================
def make_unique_headers(headers: list[str]) -> list[str]:
	"""
	Make CSV headers unique by appending .1, .2, ... to duplicates.

	Args:
		headers (list[str]): Raw header row.

	Returns:
		list[str]: Unique headers.
	"""
	seen: dict[str, int] = {}
	out: list[str] = []

	for h in headers:
		if h not in seen:
			seen[h] = 0
			out.append(h)
			continue

		seen[h] += 1
		out.append(f"{h}.{seen[h]}")

	return out

#============================================
def read_csv_rows(csv_path: str) -> tuple[list[str], list[dict]]:
	"""
	Read CSV into a header list and list of dict rows, preserving duplicate columns.

	Args:
		csv_path (str): Path to CSV.

	Returns:
		tuple[list[str], list[dict]]: (headers, rows)
	"""
	with open(csv_path, "r", encoding="utf-8", newline="") as handle:
		reader = csv.reader(handle)

		raw_headers = next(reader)
		headers = make_unique_headers(raw_headers)

		rows: list[dict] = []
		for values in reader:
			row: dict = {}
			for i, h in enumerate(headers):
				row[h] = values[i] if i < len(values) else ""
			rows.append(row)

	return headers, rows


#============================================
def col_suffix(header: str) -> str:
	"""
	Extract trailing ".<digit>" suffix used by Google Forms exports.

	Args:
		header (str): Column header.

	Returns:
		str: Suffix string like "", ".1", ".2".
	"""
	match = re.search(r"(\.\d+)$", header.strip())
	if match is None:
		return ""
	return match.group(1)

#============================================
def parse_week_from_group(group_name: str) -> int | None:
	"""
	Parse "Week N" from a group string.

	Args:
		group_name (str): Group name that may include "(Week N, ... )".

	Returns:
		int | None: Week number if found.
	"""
	match = re.search(r"\(Week\s+(\d+)\b", str(group_name))
	if match is None:
		return None
	return int(match.group(1))

#============================================
def mode_string(values: list[str]) -> str | None:
	"""
	Return the most common string, tie-broken by first seen.

	Args:
		values (list[str]): Values.

	Returns:
		str | None: Mode value.
	"""
	counts: dict[str, int] = {}
	order: list[str] = []
	for v in values:
		if v is None:
			continue
		s = str(v).strip()
		if s == "":
			continue
		if s not in counts:
			counts[s] = 0
			order.append(s)
		counts[s] += 1

	if not counts:
		return None

	best = order[0]
	for s in order:
		if counts[s] > counts[best]:
			best = s
	return best

#============================================
def find_key_columns(headers: list[str]) -> dict:
	"""
	Find the columns needed for group, blocks, ratings, and awards.

	Args:
		headers (list[str]): CSV headers.

	Returns:
		dict: Column mapping and block definitions.
	"""
	group_col = None
	for h in headers:
		if h.strip() == "Which group were you in?":
			group_col = h
			break
	if group_col is None:
		raise ValueError("Could not find 'Which group were you in?' column.")

	own_cols: dict[str, str] = {}
	for h in headers:
		if h.startswith("Was this YOUR GROUP?"):
			own_cols[col_suffix(h)] = h

	rating_starts = [
		"Innovation and CREATIVITY",
		"Product FEASIBILITY",
		"Market NICHE",
		"SCIENTIFIC Foundation",
		"Content QUALITY",
		"Team SYNERGY",
		"Presenter ENTHUSIASM",
		"Presentation STYLE and ENGAGEMENT",
		"Do you think they have what is takes to",
	]

	rating_cols: dict[str, list[str]] = {}
	for h in headers:
		suf = col_suffix(h)
		for base in rating_starts:
			if h.startswith(base):
				if suf not in rating_cols:
					rating_cols[suf] = []
				rating_cols[suf].append(h)
				break

	award_product_col = None
	award_presentation_col = None
	for h in headers:
		if h.startswith("Other than your group which group had the better PRODUCT"):
			award_product_col = h
		if h.startswith("Other than your group which group had the better PRESENTATION"):
			award_presentation_col = h

	if award_product_col is None or award_presentation_col is None:
		raise ValueError("Could not find award columns for PRODUCT and PRESENTATION.")

	blocks = []
	for suf, own_col in sorted(own_cols.items(), key=lambda x: x[0]):
		cols_for_block = rating_cols.get(suf, [])
		if not cols_for_block:
			continue
		blocks.append({
			"suffix": suf,
			"own_col": own_col,
			"rating_cols": cols_for_block,
		})

	if not blocks:
		raise ValueError("No rating blocks found. Check headers and rating question text.")

	return {
		"group_col": group_col,
		"award_product_col": award_product_col,
		"award_presentation_col": award_presentation_col,
		"blocks": blocks,
	}

#============================================
def infer_presenting_groups(rows: list[dict], group_col: str, blocks: list[dict]) -> dict[str, str]:
	"""
	Infer which group each block corresponds to, using rows where own_col == "Yes".

	Args:
		rows (list[dict]): CSV rows.
		group_col (str): Evaluator group column.
		blocks (list[dict]): Block definitions.

	Returns:
		dict[str, str]: suffix -> group_name
	"""
	suffix_to_group: dict[str, str] = {}
	for block in blocks:
		own_col = block["own_col"]
		suf = block["suffix"]

		candidates: list[str] = []
		for row in rows:
			ans = norm_text(row.get(own_col))
			if ans == "yes":
				candidates.append(row.get(group_col, ""))

		group_name = mode_string(candidates)
		if group_name is None:
			group_name = "Unknown Block " + suf
		suffix_to_group[suf] = group_name

	return suffix_to_group

#============================================
def compute_group_avg_scores(
	rows: list[dict],
	group_col: str,
	blocks: list[dict],
	suffix_to_group: dict[str, str],
) -> dict[str, float]:
	"""
	Compute average rating per presenting group, ignoring self-ratings.

	Args:
		rows (list[dict]): CSV rows.
		group_col (str): Evaluator group column.
		blocks (list[dict]): Block definitions.
		suffix_to_group (dict[str, str]): Block suffix -> group name.

	Returns:
		dict[str, float]: group -> avg numeric score
	"""
	group_avgs: dict[str, list[float]] = {}

	for block in blocks:
		suf = block["suffix"]
		own_col = block["own_col"]
		rating_cols = block["rating_cols"]
		presenting_group = suffix_to_group[suf]

		if presenting_group not in group_avgs:
			group_avgs[presenting_group] = []

		for row in rows:
			is_self = norm_text(row.get(own_col)) == "yes"
			if is_self:
				continue

			nums: list[float] = []
			for c in rating_cols:
				val = rating_to_num(row.get(c))
				if val is None:
					continue
				nums.append(val)

			if not nums:
				continue

			avg = statistics.mean(nums)
			group_avgs[presenting_group].append(avg)

	out: dict[str, float] = {}
	for g, vals in group_avgs.items():
		if not vals:
			out[g] = 0.0
			continue
		out[g] = statistics.mean(vals)

	return out

#============================================
def count_group_members(rows: list[dict], group_col: str) -> dict[str, int]:
	"""
	Count how many respondents belong to each group.

	Args:
		rows (list[dict]): CSV rows.
		group_col (str): Group column.

	Returns:
		dict[str, int]: group -> count
	"""
	counts: dict[str, int] = {}
	for row in rows:
		g = row.get(group_col, "")
		if g not in counts:
			counts[g] = 0
		counts[g] += 1
	return counts

#============================================
def group_key(value: str) -> str:
	"""
	Normalize a group string for matching.

	Rule:
		- Take text before the first "("
		- Keep only A-Z letters
		- Lowercase

	Args:
		value (str): Group name string.

	Returns:
		str: Normalized key.
	"""
	prefix = str(value or "").split("(", 1)[0]
	prefix = prefix.strip().lower()

	# Keep letters only, drop spaces, emoji, punctuation
	key = re.sub(r"[^a-z]+", "", prefix)
	return key

#============================================
def tally_awards(
	rows: list[dict],
	group_col: str,
	award_product_col: str,
	award_presentation_col: str,
) -> tuple[dict[str, int], dict[str, int]]:
	"""
	Tally award votes and self-votes using normalized group keys.
	"""
	awards_raw: dict[str, int] = {}
	self_votes: dict[str, int] = {}

	for row in rows:
		own_key = group_key(row.get(group_col, ""))

		for col in (award_product_col, award_presentation_col):
			selected = row.get(col)
			if selected is None:
				continue
			selected_str = str(selected).strip()
			if selected_str == "":
				continue

			sel_key = group_key(selected_str)

			if sel_key not in awards_raw:
				awards_raw[sel_key] = 0
			awards_raw[sel_key] += 1

			if sel_key == own_key:
				if sel_key not in self_votes:
					self_votes[sel_key] = 0
				self_votes[sel_key] += 1

	return awards_raw, self_votes

#============================================
def eligible_award_votes_for_group(
	rows: list[dict],
	group_col: str,
	target_group: str,
	award_col: str,
) -> int:
	"""
	Count eligible votes for a group in one award category using normalized keys.
	"""
	target_key = group_key(target_group)
	total = 0

	for row in rows:
		own_key = group_key(row.get(group_col, ""))
		if own_key == target_key:
			continue

		val = row.get(award_col)
		if val is None:
			continue
		if str(val).strip() == "":
			continue

		total += 1

	return total

#============================================
def build_summary_rows(
	rows: list[dict],
	colmap: dict,
	avg_scores: dict[str, float],
	suffix_to_group: dict[str, str],
	week1_boost: float,
	points_max: float,
	penalty_per_self_vote: int,
) -> list[list]:
	"""
	Build output rows for the summary CSV using LibreOffice formulas.

	Returns:
		list[list]: Rows aligned to the output header order.
	"""
	group_col = colmap["group_col"]
	award_product_col = colmap["award_product_col"]
	award_presentation_col = colmap["award_presentation_col"]

	awards_raw, self_votes = tally_awards(rows, group_col, award_product_col, award_presentation_col)

	presenting_groups: list[str] = []
	for suf in sorted(suffix_to_group.keys()):
		presenting_groups.append(suffix_to_group[suf])

	# First pass: compute columns through Award Rate and keep boosted values for MAX().
	tmp: list[dict] = []
	max_boosted = 0.0
	max_award_rate = 0.0

	for group_name in presenting_groups:
		week = parse_week_from_group(group_name)
		avg = avg_scores.get(group_name, 0.0)

		boosted = avg
		if week == 1:
			boosted = avg + week1_boost

		if boosted > max_boosted:
			max_boosted = boosted

		key = group_key(group_name)
		raw_awards = awards_raw.get(key, 0)
		self_ct = self_votes.get(key, 0)
		self_penalty = -1 * penalty_per_self_vote * self_ct
		net_awards = raw_awards + self_penalty

		eligible_prod = eligible_award_votes_for_group(rows, group_col, group_name, award_product_col)
		eligible_pres = eligible_award_votes_for_group(rows, group_col, group_name, award_presentation_col)
		total_awards = eligible_prod + eligible_pres

		award_ratio = 0.0
		if total_awards > 0 and net_awards > 0:
			award_ratio = net_awards / float(total_awards)

		# LibreOffice: =(G/H)^(1/12)
		award_rate = award_ratio ** (1.0 / 12.0)

		if award_rate > max_award_rate:
			max_award_rate = award_rate

		tmp.append({
			"group_name": group_name,
			"week": week if week is not None else "",
			"avg": avg,
			"boosted": boosted,
			"raw_awards": raw_awards,
			"self_penalty": self_penalty,
			"net_awards": net_awards,
			"total_awards": total_awards,
			"award_rate": award_rate,
		})

	# Second pass: normalize Award Score and Rating Score to MAX, then Combined, Adjusted, Points.
	out_rows: list[list] = []

	for t in tmp:
		award_score = 0.0
		if max_award_rate > 0.0:
			# LibreOffice: =I/MAX(I$13:I$19)
			award_score = t["award_rate"] / max_award_rate

		rating_ratio = 0.0
		if max_boosted > 0.0:
			rating_ratio = t["boosted"] / max_boosted

		# LibreOffice: =(D/MAX(D$13:D$19))^(0.9)
		rating_score = rating_ratio ** 0.9

		# LibreOffice: =(J+K*2)/3
		combined = (award_score + (rating_score * 2.0)) / 3.0

		# LibreOffice: =L*0.96
		adjusted = combined * 0.96

		points = adjusted * points_max

		out_rows.append([
			t["group_name"],
			t["week"],
			round(t["avg"], 2),
			round(t["boosted"], 2),
			t["raw_awards"],
			t["self_penalty"],
			t["net_awards"],
			t["total_awards"],
			round(t["award_rate"], 6),
			round(award_score, 6),
			round(rating_score, 6),
			round(combined, 6),
			round(adjusted, 6),
			round(points, 2),
			t["group_name"],
		])

	return out_rows


#============================================
def write_summary_csv(output_csv: str, header: list[str], rows: list[list]):
	"""
	Write summary rows to CSV, supporting duplicate header names.

	Args:
		output_csv (str): Output path.
		header (list[str]): Header row (may include duplicates).
		rows (list[list]): Data rows aligned to header.
	"""
	with open(output_csv, "w", encoding="utf-8", newline="") as handle:
		writer = csv.writer(handle)
		writer.writerow(header)
		for r in rows:
			writer.writerow(r)


#============================================
def process_one_file(
	csv_path: str,
	week1_boost: float,
	max_rating: float,
	award_weight: float,
	rating_weight: float,
	points_max: float,
	penalty_per_self_vote: int,
) -> list[dict]:
	"""
	Process one evaluation CSV file into summary rows.

	Args:
		csv_path (str): Input CSV.
		week1_boost (float): Week 1 additive boost.
		max_rating (float): Max rating numeric.
		award_weight (float): Weight for awards.
		rating_weight (float): Weight for ratings.
		points_max (float): Max points.
		penalty_per_self_vote (int): Penalty per self vote.

	Returns:
		list[dict]: Summary rows for this file.
	"""
	headers, rows = read_csv_rows(csv_path)
	colmap = find_key_columns(headers)

	group_col = colmap["group_col"]
	blocks = colmap["blocks"]

	suffix_to_group = infer_presenting_groups(rows, group_col, blocks)
	avg_scores = compute_group_avg_scores(rows, group_col, blocks, suffix_to_group)

	summary_rows = build_summary_rows(
		rows=rows,
		colmap=colmap,
		avg_scores=avg_scores,
		suffix_to_group=suffix_to_group,
		week1_boost=week1_boost,
		points_max=points_max,
		penalty_per_self_vote=penalty_per_self_vote,
	)


	return summary_rows




#============================================
def main():
	args = parse_args()

	all_rows: list[dict] = []
	for csv_path in args.input_files:
		if not os.path.exists(csv_path):
			raise ValueError(f"Input file not found: {csv_path}")

		rows = process_one_file(
			csv_path=csv_path,
			week1_boost=args.week1_boost,
			max_rating=args.max_rating,
			award_weight=args.award_weight,
			rating_weight=args.rating_weight,
			points_max=args.points_max,
			penalty_per_self_vote=args.penalty_per_self_vote,
		)
		all_rows += rows
	output_header = [
		"Name", "Week", "AVG Score", "Week1 boost", "Awards", "Self Penalty",
		"Net Awards", "Total Awards", "Award Rate", "Award Score", "Rating Score",
		"Combined", "Adjusted", "Points", "Name",
	]
	write_summary_csv(args.output_csv, output_header, all_rows)

#============================================
if __name__ == "__main__":
	main()
