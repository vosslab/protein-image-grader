#!/usr/bin/env python3

# Standard Library
import time

# local repo modules
import protein_image_grader.duplicate_processing as duplicate_processing
import protein_image_grader.interactive_image_criteria_class as interactive_image_criteria_class
import protein_image_grader.read_save_images as read_save_images


#============================================
def hex_to_bin(hex_string: str) -> str:
	"""
	Convert a hex string to its binary representation.
	"""
	return duplicate_processing.hex_to_bin(hex_string)


#============================================
def hamming_distance(s1: str, s2: str) -> int:
	"""
	Calculate the Hamming distance between two binary strings.
	"""
	return duplicate_processing.hamming_distance(s1, s2)


#============================================
def pre_process_student_images(student_tree: list, params: dict) -> None:
	"""
	Download, inspect, and deduplicate student images before grading.

	Args:
		student_tree (list): List of student entries.
		params (dict): Parameter dictionary with file paths and folders.
	"""
	read_save_images.read_and_save_student_images(student_tree, params)
	time.sleep(0.1)
	duplicate_processing.check_duplicate_images(student_tree, params)
	return


#============================================
class process_image_questions_class(interactive_image_criteria_class.process_image_questions_class):
	"""
	Compatibility wrapper for the interactive image grading class.
	"""
	pass
