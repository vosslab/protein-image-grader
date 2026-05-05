#!/usr/bin/env python3

"""
Single entry point for the protein image grading workflow.

See protein_image_grader/start_grading.py for the implementation.
"""

import sys

import protein_image_grader.start_grading as start_grading


#============================================
def main():
	return start_grading.main()


#============================================
if __name__ == '__main__':
	sys.exit(main() or 0)
