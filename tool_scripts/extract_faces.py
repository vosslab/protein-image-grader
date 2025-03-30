#!/usr/bin/env python3

# Standard Library
import os
import sys
import argparse

# PIP3 modules
import numpy
import PIL.Image
from PIL import ImageOps
import face_recognition

#============================================

def parse_args():
	"""
	Parse command-line arguments.

	Returns:
		args: Parsed command-line arguments
	"""
	parser = argparse.ArgumentParser(description="Crop faces from images with padding.")
	parser.add_argument('-i', '--input-dir', dest='input_dir', required=True,
						help="Directory containing input images")
	parser.add_argument('-o', '--output-dir', dest='output_dir', required=True,
						help="Directory to save cropped images")
	return parser.parse_args()

#============================================

def expand_box(top: int, right: int, bottom: int, left: int,
			img_w: int, img_h: int) -> tuple:
	"""
	Expand the face bounding box with head-and-shoulder padding.

	Args:
		top: Top Y coordinate
		right: Right X coordinate
		bottom: Bottom Y coordinate
		left: Left X coordinate
		img_w: Image width
		img_h: Image height

	Returns:
		tuple: Expanded (top, right, bottom, left) bounding box
	"""
	height = bottom - top
	width = right - left

	# Padding: 150% upward, 200% downward, 150% side
	pad_y_top = int(height * 1.5)
	pad_y_bottom = int(height * 2.0)
	pad_x = int(width * 0.75)

	new_top = max(0, top - pad_y_top)
	new_bottom = min(img_h, bottom + pad_y_bottom)
	new_left = max(0, left - pad_x)
	new_right = min(img_w, right + pad_x)

	return new_top, new_right, new_bottom, new_left

#============================================

def load_and_correct_image(image_path: str) -> tuple:
	"""
	Load an image and correct orientation based on EXIF data.

	Args:
		image_path: Path to input image

	Returns:
		tuple: (PIL.Image object, numpy array version)
	"""
	pil_image = PIL.Image.open(image_path)
	pil_image = ImageOps.exif_transpose(pil_image)

	# Force RGB mode (in case it's RGBA, CMYK, etc.)
	if pil_image.mode != 'RGB':
		pil_image = pil_image.convert('RGB')

	image_array = numpy.array(pil_image)
	return pil_image, image_array
#============================================

def detect_face(image_array, model_order=('hog', 'cnn')) -> tuple:
	"""
	Detect a face using multiple models in order.

	Args:
		image_array: Numpy array of image pixels
		model_order: Tuple of models to try in order

	Returns:
		tuple: (face location or None, model used or None)
	"""
	for model in model_order:
		face_locations = face_recognition.face_locations(image_array, model=model)
		if face_locations:
			return face_locations[0], model
	return None, None

#============================================

def crop_and_save(pil_image: PIL.Image.Image, face_box: tuple, output_path: str) -> None:
	"""
	Crop the face with padding and save the output image.

	Args:
		pil_image: PIL Image object
		face_box: Tuple (top, right, bottom, left)
		output_path: Path to save cropped image
	"""
	top, right, bottom, left = face_box
	width, height = pil_image.size
	new_top, new_right, new_bottom, new_left = expand_box(
		top, right, bottom, left, width, height
	)
	cropped = pil_image.crop((new_left, new_top, new_right, new_bottom))
	cropped.save(output_path)
	print(f"[ok] Saved: {os.path.basename(output_path)}")

#============================================

def process_image(image_path: str, output_path: str) -> None:
	"""
	Process a single image: correct orientation, detect face, crop and save.

	Args:
		image_path: Path to input image
		output_path: Path to save cropped image
	"""
	pil_image, image_array = load_and_correct_image(image_path)

	face_box, model_used = detect_face(image_array)
	if face_box is None:
		print(f"[skip] No face found (HOG + CNN) in {os.path.basename(image_path)}")
		return
	if model_used == 'cnn':
		print(f"[info] Used CNN model for {os.path.basename(image_path)}")

	crop_and_save(pil_image, face_box, output_path)
	return output_path

#============================================

def main():
	args = parse_args()

	# Validate output directory
	if not os.path.isdir(args.output_dir):
		os.makedirs(args.output_dir)

	# Gather valid image files
	image_files = []
	for fname in sorted(os.listdir(args.input_dir)):
		if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
			image_files.append(fname)

	total = len(image_files)
	if total == 0:
		print("No valid images found.")
		return

	# Process each image
	for index, fname in enumerate(image_files, start=1):
		print(f"Image {index} of {total}")
		input_path = os.path.join(args.input_dir, fname)
		output_path = os.path.join(args.output_dir, fname)
		print(fname)
		if os.path.isfile(output_path):
			continue
		process_image(input_path, output_path)

#============================================

if __name__ == '__main__':
	main()
