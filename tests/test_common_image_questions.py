#!/usr/bin/env python3

import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
	sys.path.insert(0, REPO_ROOT)

import protein_image_grader.grade_protein_image as grade_protein_image


#============================================
def main() -> None:
	common_list = [
		{"name": "Image was received", "type": "bool", "point_deduction": -1, "feedback": "no image"},
		{"name": "White background was used", "type": "bool", "point_deduction": -1, "feedback": "white"},
	]
	specific_list = [
		{"name": "White background was used", "type": "bool", "point_deduction": 0, "feedback": "override"},
		{"name": "Unique image, not same as another student", "type": "bool", "point_deduction": -1, "feedback": "unique"},
	]

	merged = grade_protein_image.merge_image_questions(common_list, specific_list)

	assert merged[0]["name"] == "Image was received"
	assert merged[1]["name"] == "White background was used"
	assert merged[1]["feedback"] == "override"
	assert merged[2]["name"] == "Unique image, not same as another student"
	return


#============================================
if __name__ == '__main__':
	main()
