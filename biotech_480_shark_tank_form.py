#!/usr/bin/env python3

import re
import os
import csv
import sys
import time
import numpy
import random
import argparse
from collections import defaultdict

#==============
def extract_brackets_content(text: str) -> str:
	"""
	Extracts the content inside parentheses at the end of a string.

	Args:
		text (str): Input string containing content in brackets.

	Returns:
		str: The content found inside the parentheses. Returns an empty string if no match.
	"""
	text = text.strip()
	match = re.search(r'\[([^\]]+)\]$', text)
	if match:
		return match.group(1).strip()  # Strip any extra spaces
	print(match)
	print(text)
	sys.exit(1)

#==============
def extract_company_info(text: str) -> dict:
	"""
	Extracts the number, company name, and student name from a string formatted like "#8 UVDermal (Karolina)".

	Args:
		text (str): Input string containing the number, company name, and student name.

	Returns:
		dict: A dictionary with keys 'number', 'company', and 'student', or None if no match is found.
	"""
	# Update the regex to handle spaces, hyphens, and underscores in the company name
	match = re.search(r'#(\d+)\s+([A-Za-z0-9\s\-_]+)\s+\(([^)]+)\)', text)
	if match:
		return {
			'number': int(match.group(1)),      # Extract number (e.g., 8)
			'company': match.group(2).strip(),  # Extract company name (e.g., UVDermal or Bio-Health Solutions)
			'student': match.group(3).strip()   # Extract student name (e.g., Karolina)
		}
	return None

def remove_non_ascii(text: str) -> str:
	"""
	Removes all non-ASCII characters from the input string.

	Args:
		text (str): Input string that may contain non-ASCII characters.

	Returns:
		str: A string containing only ASCII characters.
	"""
	# Encode to ASCII, ignoring non-ASCII characters, then decode back to string
	return text.encode('ascii', 'ignore').decode('ascii')


# Constants for biotechnology scoring
BIOTECH_SCORE_MAP = {
	"strongly agree": 4,
	"somewhat agree": 3,
	"somewhat disagree": 2,
	"strongly disagree": 1
}

#==============
def parse_csv(input_file: str) -> list:
	"""Reads the CSV file and returns its content as a list of dictionaries."""
	try:
		with open(input_file, mode='r') as file:
			csv_reader = csv.DictReader(file)
			data = list(csv_reader)
			print(f"\nINFO: Successfully read {len(data)} rows from {input_file}")
			return data
	except Exception as e:
		print(f"Error reading CSV file: {e}")
		sys.exit(1)

#==============
def detect_columns(headers: list) -> dict:
	"""Automatically detects relevant columns for biotech, investment, and awards based on the header names."""
	biotech_columns = [col for col in headers if col.startswith("Does the student")]
	investment_columns = [col for col in headers if col.startswith("Investment Group ")]
	awards_columns = [col for col in headers if col.startswith("Now is ")]

	print("\nINFO: Detected Columns:")
	print(f"  - Biotech Columns: {len(biotech_columns)}")
	print(f"  - Investment Columns: {len(investment_columns)}")
	print(f"  - Award Columns: {len(awards_columns)}")

	return {
		"biotech": biotech_columns,
		"investment": investment_columns,
		"awards": awards_columns
	}

#==============
def calculate_biotech_scores(data: list, biotech_columns: list) -> None:
	"""
	Calculates the median, average, and standard deviation for each company in the biotechnology scores.

	Args:
		data (list): List of rows (dictionaries) from the CSV file.
		biotech_columns (list): List of biotechnology-related column headers.

	Returns:
		None
	"""
	company_scores = {}  # Dictionary to store scores per company/student
	cells_processed = 0  # Update terminology to reflect that we're processing cells

	for row in data:
		for col in biotech_columns:
			# Extract the score from the row
			value = row.get(col, "").lower().strip()
			value = remove_non_ascii(value).strip()
			if value in BIOTECH_SCORE_MAP:
				score = BIOTECH_SCORE_MAP[value]
				cells_processed += 1  # Increment cells processed

				# Extract the company/student information from the column header
				company_info = extract_brackets_content(col)

				# Add the score to the company's list of scores
				if company_info not in company_scores:
					company_scores[company_info] = []
				company_scores[company_info].append(score)

	# If no scores were found, return early
	if not company_scores:
		print("No valid scores found.")
		return

	# Calculate statistics for each company
	company_stats = {}
	for company, scores in company_scores.items():
		scores_array = numpy.array(scores)
		median = numpy.median(scores_array)
		mean = numpy.mean(scores_array)
		stdev = numpy.std(scores_array, ddof=1)  # ddof=1 for sample std deviation
		company_stats[company] = {
			"median": median,
			"average": mean,
			"stdev": stdev
		}

	# Sort companies by mean (average) score in descending order
	sorted_companies = sorted(company_stats.items(), key=lambda x: x[1]['average'], reverse=True)

	# Find the maximum length of company names for dynamic column width
	max_company_length = max(len(company) for company in company_stats)

	# Print the statistics per company, aligned vertically
	print(f"\nINFO: Biotechnology Scores by Company (Sorted by Average):")
	print(f"{'Company':<{max_company_length}}{'Median':>10}{'Average':>10}{'Stdev':>10}")
	print("=" * (max_company_length + 30))  # Adjust the separator line based on company name length
	for company, stats in sorted_companies:
		print(f"{company:<{max_company_length}}{stats['median']:>10.2f}{stats['average']:>10.2f}{stats['stdev']:>10.2f}")

	sorted_companies = sorted(company_stats.items(), key=lambda x: x[0], reverse=False)
	for company, stats in sorted_companies:
		print(f"{company}\t{stats['median']:.2f}\t{stats['average']:.2f}\t{stats['stdev']:.2f}")

	# Report total cells processed
	print(f"\nINFO: Total cells processed: {cells_processed}")

#==============
#==============
def sum_investment(data: list, investment_columns: list) -> int:
	"""
	Sums up all dollar amounts in the Investment Group columns.

	Args:
		data (list): List of rows (dictionaries) from the CSV file.
		investment_columns (list): List of investment-related column headers.

	Returns:
		int: Total investment summed across all rows and columns.
	"""
	company_investments = {}
	total_investment = 0
	cells_processed = 0

	for row in data:
		for col in investment_columns:
			# Extract the 2-digit investment value from the string, defaulting to "00" if not found
			value_str = row.get(col, " 00")[1:3]
			try:
				value = int(value_str)  # Convert the extracted value to an integer
			except ValueError:
				value = 0  # Default to 0 if the conversion fails

			# Extract company information from column header (using the updated function for brackets)
			company_info = extract_brackets_content(col)

			# Skip if no company info is extracted
			if not company_info:
				print(f"WARNING: No company info found for column: {col}")
				continue

			# Accumulate investments per company
			company_investments[company_info] = company_investments.get(company_info, 0) + value

			# Increment the total investment
			total_investment += value
			cells_processed += 1  # Count each processed column (investment entry)

	print(f"\nINFO: Investment Group Processing")
	print(f"  - Cells processed: {cells_processed}")
	print(f"  - Total Investment: ${total_investment/1000.:.2f} billion")

	# Sort the company investments by the investment amount in descending order
	sorted_investments = sorted(company_investments.items(), key=lambda x: x[1], reverse=True)

	# Output the investments per company, sorted by amount
	print("\nINFO: Per-Company Investment Breakdown (Sorted by Investment):")
	for company, investment in sorted_investments:
		print(f"  - {company}: ${investment} million")

	print("Investment Breakdown:")
	sorted_investments = sorted(company_investments.items(), key=lambda x: x[0])
	for company, investment in sorted_investments:
		print(f"{company}\t{investment}")

	return total_investment

#==============
def get_top_awards(data: list, awards_columns: list) -> None:
	"""
	For each award, returns the top 3 companies based on the number of occurrences.

	Args:
		data (list): List of rows (dictionaries) from the CSV file.
		awards_columns (list): List of awards-related column headers.

	Returns:
		None
	"""
	# Dictionary to store vote counts for each award by company
	award_tallies = defaultdict(lambda: defaultdict(int))
	company_award_count = defaultdict(int)
	cells_processed = 0

	# Process each row for each company (column)
	for row in data:
		for col in awards_columns:
			# Extract the company info (company/student name) from the column header
			company_info = extract_brackets_content(col)
			# Get the award name from the current cell (row, col)
			award_name = row.get(col, "").strip()
			#award_name = remove_non_ascii(award_name).strip()
			# If the award name is not empty, increment the count for that award
			if award_name:
				company_award_count[company_info] += 1
				award_tallies[award_name][company_info] += 1
				cells_processed += 1

	# Output the top 3 companies for each award
	print(f"\nINFO: Awards Processing")
	print(f"  - Cells processed: {cells_processed}\n")

	for award, companies in award_tallies.items():
		# Sort companies by vote count in descending order
		sorted_companies = sorted(companies.items(), key=lambda x: x[1], reverse=True)
		top_3_companies = sorted_companies[:3]  # Get the top 3 companies

		# Output the award and its top 3 companies, including vote count
		print(f"{award}:")
		for company, count in top_3_companies:
			print(f". {company} ({count} votes)")  # Print the company name and the vote count
		print()  # Add a blank line after each award

	companies = sorted(company_award_count.keys())
	print("AWARD COUNTS")
	for company_info in companies:
		award_count = company_award_count[company_info]
		print(f"{company_info}\t{award_count}")


#==============
def main():
	# Argument parsing
	parser = argparse.ArgumentParser(description='Process student grading form CSV data.')
	parser.add_argument('-i', '--input', dest='input_file', required=True, help='Input CSV file from Google Form')
	args = parser.parse_args()

	# Read CSV data
	data = parse_csv(args.input_file)

	# Automatically detect relevant columns based on headers
	if len(data) > 0:
		headers = data[0].keys()
		column_map = detect_columns(headers)
	else:
		print("No data found in CSV.")
		sys.exit(1)

	# Calculate biotech scores
	calculate_biotech_scores(data, column_map["biotech"])

	# Sum investments
	sum_investment(data, column_map["investment"])

	# Get top awards
	get_top_awards(data, column_map["awards"])

#==============
if __name__ == "__main__":
	main()
