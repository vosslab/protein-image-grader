
import sys
from datetime import datetime

#==========================================
# Helper function to determine the deduction based on a given value and ranges
#==========================================
def get_deduction(value: int, ranges: dict) -> 'int or float':
	"""
	Calculate the deduction based on the provided value and defined ranges.

	Parameters:
	-----------
	value : int
		The value for which the deduction is to be calculated.
	ranges : dict
		The ranges and corresponding deductions as key-value pairs.
		Keys are strings in 'lower_limit-upper_limit' format.

	Returns:
	--------
	int
		The calculated deduction value based on the ranges.
	"""

	# Iterate over the ranges dictionary to find the correct range for the value
	for key, deduction in ranges.items():

		# Split the key to get the lower and upper limits of the range
		lower_limit, upper_limit = key.split("-")

		# Handle the "+" symbol by replacing with positive infinity
		if len(upper_limit) == 0:
			upper_limit = float('inf')
		else:
			upper_limit = int(upper_limit)

		# Handle the "-" symbol by replacing with negative infinity
		if len(lower_limit) == 0:
			lower_limit = float('-inf')
		else:
			lower_limit = int(lower_limit)

		# Check if the value lies within the current range
		if lower_limit <= value <= upper_limit:
			return deduction  # Return the corresponding deduction value

	# Return 0 if value doesn't fall within any of the defined ranges
	return 0

#==========================================
def timestamp_due_date(student_entry: dict, config: dict) -> None:
	"""
	Calculates and updates the due date related values for a student's entry.

	Parameters
	----------
	student_entry : dict
		A dictionary containing student information including a 'timestamp' key.
	config : dict
		Configuration dictionary which is used to check due date.

	Returns
	-------
	None
		Updates the student_entry dictionary in-place with due date deduction, status, and feedback.
	"""

	# Retrieve the timestamp from the student's entry
	entry_timestamp = student_entry['timestamp']

	# Calculate the due date deduction, status, and feedback
	deduction, status, feedback = check_due_date(entry_timestamp, config)

	# Update the student's entry with the calculated due date information
	student_entry["Due Date Deduction"] = deduction
	student_entry["Due Date Status"] = status
	student_entry["Due Date Feedback"] = feedback


#==========================================
def check_due_date(entry_timestamp: str, config: dict) -> tuple:
	"""
	Check if a submission is late and calculate deductions if applicable.

	Parameters
	----------
	entry_timestamp : str
		Timestamp of when the student entry was submitted, formatted as 'YYYY/MM/DD HH:MM:SS AM/PM'.
	config : dict
		Configuration settings including deadline information.

	Returns
	-------
	tuple
		Returns a tuple containing the following:
			- deduction: Numeric penalty if the assignment is late.
			- status: A string 'On-Time' or 'Late'.
			- feedback: Additional information if the assignment is late.

	"""

	# Retrieve due date string from config and append the default time
	due_date_str = config["deadline"]["due date"] + " 11:59:59 PM"

	# Convert due_date and entry_timestamp to datetime objects
	try:
		due_date = datetime.strptime(due_date_str, "%b %d, %Y %I:%M:%S %p")
	except ValueError:
		due_date = datetime.strptime(due_date_str, "%B %d, %Y %I:%M:%S %p")
	entry_datetime = datetime.strptime(entry_timestamp[:-4].strip(), "%Y/%m/%d %I:%M:%S %p")

	# Calculate the difference in hours between due_date and entry_datetime
	hours_diff = (entry_datetime - due_date).total_seconds() / 3600

	# Exit if the assignment is more than 6 months late
	if hours_diff > 2 * 30 * 24:
		print("This assignment is more than 6 months late, fix the due date in the YAML file")
		sys.exit(1)

	# Get the numeric deduction based on how late the assignment is
	deduction = get_deduction(hours_diff, config["deadline"].get("numeric_deductions", {}))

	# Prepare the status and feedback information
	if deduction == 0.0:
		status = "On-Time"
		feedback = ''
	else:
		status = "Late"
		feedback = f"Late by {hours_diff:.0f} hours"

	return deduction, status, feedback

# Example assert command; tailor with actual data
result = check_due_date("1970/10/25 11:59:59 PM EST", {'deadline': {'due date': 'Oct 25, 1970'}})
assert result == (0.0, 'On-Time', '')
