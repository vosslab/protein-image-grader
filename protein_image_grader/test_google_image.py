#!/usr/bin/env python3

# Standard Library
import io
import sys
import time
import random
import hashlib
import requests
import imagehash
import urllib.parse

# PIP modules
import PIL.Image
from PIL import Image
from PIL import ImageChops

#pip3 install google-api-python-client
import googleapiclient.http
import googleapiclient.discovery
from google.oauth2.service_account import Credentials

# Extended list of named colors and their RGB values
NAMED_COLORS = {
	'Black': (0, 0, 0),
	'White': (255, 255, 255),
	'Light Gray': (32, 32, 32),
	'Medium Gray': (128, 128, 128),
	'Dark Gray': (224, 224, 224),
	'Red': (255, 0, 0),
	'Green': (0, 128, 0),
	'Lime Green': (0, 255, 0),
	'Blue': (0, 0, 255),
	'Yellow': (255, 255, 0),
	'Orange': (255, 165, 0),
	'Brown': (139, 69, 19),
	'Pink': (255, 192, 203),
	'Indigo': (75, 0, 130),
	'Purple': (128, 0, 128),
	'Violet': (238, 130, 238),
}


# Replace with the path to your API key file
#api_key_file = "api_file.json"
api_key_file = "service_key.json"

scopes = ['https://www.googleapis.com/auth/drive.readonly']
credentials = Credentials.from_service_account_file(api_key_file, scopes=scopes)
service = googleapiclient.discovery.build('drive', 'v3', credentials=credentials)

# Initialize Google Drive API client
#credentials = Credentials.from_service_account_file(api_key_file, scopes=['https://www.googleapis.com/auth/drive.readonly'])
#service = googleapiclient.discovery.build('drive', 'v3', credentials=credentials)

#============================================

def get_background_color(image: Image.Image) -> tuple:
	"""
	Determine the background color by sampling 16 pixels near the four corners.

	Args:
		image (Image.Image): A PIL Image object.

	Returns:
		tuple: The most common background color from the sampled pixels.
	"""
	# Get image dimensions
	width, height = image.size

	# Define 16 sampled pixels (2×2 grid from each corner)
	sample_pixels = [
		image.getpixel((0, 0)), image.getpixel((1, 0)),
		image.getpixel((0, 1)), image.getpixel((1, 1)),

		image.getpixel((width - 1, 0)), image.getpixel((width - 2, 0)),
		image.getpixel((width - 1, 1)), image.getpixel((width - 2, 1)),

		image.getpixel((0, height - 1)), image.getpixel((1, height - 1)),
		image.getpixel((0, height - 2)), image.getpixel((1, height - 2)),

		image.getpixel((width - 1, height - 1)), image.getpixel((width - 2, height - 1)),
		image.getpixel((width - 1, height - 2)), image.getpixel((width - 2, height - 2))
	]

	# Find the most frequent color
	most_common_color = max(set(sample_pixels), key=sample_pixels.count)

	return most_common_color

#============================================

def rotate_if_tall(image: Image.Image) -> Image.Image:
	"""
	Rotates the image 90 degrees clockwise if its height is greater than its width.

	Args:
		image (Image.Image): A PIL Image object.

	Returns:
		Image.Image: The rotated image if needed, otherwise the original image.
	"""
	if image.height > image.width:
		# Use transpose for lossless rotation
		return image.transpose(Image.Transpose.ROTATE_90)  # 90 degrees clockwise

	return image  # No rotation needed

#============================================

def trim(image: Image.Image, tolerance: int = 0) -> Image.Image:
	"""
	Trims borders around an image based on the background color.

	Args:
		image (Image.Image): A PIL Image object to be trimmed.
		tolerance (int): How much variation in color is allowed (default 0).

	Returns:
		Image.Image: A trimmed PIL Image object.
	"""
	bg_color = get_background_color(image)  # Get the most common corner color
	bg = Image.new(image.mode, image.size, bg_color)  # Create a solid background
	diff = ImageChops.difference(image, bg)  # Find differences
	diff = ImageChops.add(diff, diff, 2.0, -tolerance)  # Enhance differences
	bbox = diff.getbbox()

	if bbox:
		return image.crop(bbox)

	return image  # No trimming possible

#============================================

def multi_trim(image: Image.Image, tolerance: int = 3) -> Image.Image:
	"""
	Iteratively trims an image until its dimensions no longer change.

	Args:
		image (Image.Image): A PIL Image object to be trimmed.
		tolerance (int): How much variation in color is allowed when trimming.

	Returns:
		Image.Image: A fully trimmed PIL Image object.
	"""
	count = 0
	while True:
		original_size = image.size
		image = trim(image, tolerance)
		image = rotate_if_tall(image)
		if image.size == original_size:
			count += 1
			if count > 1:
				# Stop when no further trimming occurs
				break

	return image

#============================================

def calculate_md5(image_data) -> str:
	"""
	Calculate the MD5 hash of an image's pixel data, excluding metadata

	Parameters
	----------
	image_path : str
		Path to the image file

	Returns
	-------
	str
		MD5 hash of the image's pixel data
	"""
	pil_image = PIL.Image.open(image_data)
	# Ensure the image is in RGB mode
	if pil_image.mode != 'RGB':
		pil_image = pil_image.convert('RGB')
	pil_image = multi_trim(pil_image)
	pixel_data = pil_image.tobytes()
	return hashlib.md5(pixel_data).hexdigest()

#============================================

def calculate_phash(image_data, hash_size: int = 16) -> str:
	"""
	Calculate the perceptual hash of an image

	Parameters
	----------
	image_path : str
		Path to the image file
	hash_size : int, optional
		Size of the perceptual hash

	Returns
	-------
	str
		Perceptual hash of the image
	"""
	pil_image = PIL.Image.open(image_data)
	# Ensure the image is in RGB mode
	if pil_image.mode != 'RGB':
		pil_image = pil_image.convert('RGB')
	pil_image = multi_trim(pil_image)
	pil_image = multi_trim(pil_image)
	return str(imagehash.phash(pil_image, hash_size=hash_size))

#============================================

def closest_color(rgb: tuple) -> str:
	"""
	Find the closest named color to a given RGB value.

	Parameters:
	------------
	rgb : tuple
		The RGB value as a tuple of three integers.

	Returns:
	---------
	str
		The name of the closest named color.
	"""
	min_colors = {}
	for name, value in NAMED_COLORS.items():
		r_c, g_c, b_c = value
		rd = (r_c - rgb[0]) ** 2
		gd = (g_c - rgb[1]) ** 2
		bd = (b_c - rgb[2]) ** 2
		min_colors[name] = rd + gd + bd
	return min(min_colors, key=min_colors.get)

#============================================
# Modify the corner_pixels dictionary to include named colors
def name_corner_colors(corner_pixels: dict) -> dict:
	"""
	Convert RGB values to closest named colors for each corner.

	Parameters:
	------------
	corner_pixels : dict
		Dictionary containing corner names and their RGB values.

	Returns:
	---------
	dict
		Dictionary containing corner names and their closest named colors.
	"""
	named_colors_dict = {}
	for corner, rgb in corner_pixels.items():
		if not isinstance(rgb, tuple):
			named_colors_dict[corner] = None
			raise TypeError
		named_colors_dict[corner] = closest_color(rgb)
	consensus = None
	for pixel_key in named_colors_dict.keys():
		color_name = named_colors_dict[pixel_key]
		if consensus is None:
			consensus = color_name
		elif color_name != consensus:
			consensus = False
			break
	named_colors_dict['consensus'] = consensus
	return named_colors_dict

#============================================

def get_file_id_from_google_drive_url(image_url: str) -> str:
	# Parse the URL to get its components
	url_parts = urllib.parse.urlparse(image_url)

	# Extract the query parameters
	query = urllib.parse.parse_qs(url_parts.query)

	# Extract the file_id from the query parameters
	file_id = query['id'][0] if 'id' in query else None

	# If file_id is None, return None as we can't proceed without a file ID
	if file_id is None:
		return None

	return file_id
# Simple assertion test for the function: 'normalize_google_drive_url'
result = get_file_id_from_google_drive_url("https://drive.google.com/u/2/open?usp=forms_web&id=1QCHoMnqKvf6gqLI272ZQ4IGBCFupnC6s")
assert result == "1QCHoMnqKvf6gqLI272ZQ4IGBCFupnC6s"

#============================================

def normalize_google_drive_url(image_url: str) -> str:
	"""
	Normalize a Google Drive URL to a direct download URL.

	Parameters
	----------
	image_url : str
		The Google Form URL to the Google Drive file.

	Returns
	-------
	str
		The direct download URL for the Google Drive file.

	"""
	file_id = get_file_id_from_google_drive_url(image_url)

	# Construct and return the direct download URL
	direct_download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
	return direct_download_url

#============================================

def get_pixel_data(pil_image):
	# Get the dimensions
	width, height = pil_image.size
	print(f"IMAGE {width}, {height}")

	# Get corner pixels: Top-left, Top-right, Bottom-left, Bottom-right
	corner_pixels_dict = {
		"Top-left": pil_image.getpixel((0, 0)),
		"Top-right": pil_image.getpixel((width - 1, 0)),
		"Bottom-left": pil_image.getpixel((0, height - 1)),
		"Bottom-right": pil_image.getpixel((width - 1, height - 1))
	}
	named_corner_pixels_dict = name_corner_colors(corner_pixels_dict)
	return named_corner_pixels_dict

#============================================

def send_http_request(url: str, session_data=None):
	sys.exit(1)
	# If session data is not provided, create a new session
	if session_data is None:
		session_data = requests.Session()

	# Create headers dictionary
	headers = {
		'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Vivaldi/6.2.3105.58',
		'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
		'Accept-Encoding': 'gzip, deflate, br',
		'Accept-Language': 'en-US,en;q=0.9',
		# Add other headers as needed
	}

	# Random sleep to avoid overloading server
	time.sleep(random.random() / 10)

	# Send the request and return the response
	response = requests.get(url, headers=headers)

	if response.status_code == 403:
		print("Permission denied: 403 status code")
		print("Headers: ", response.headers)
		print("Content: ", response.content.decode())
		sys.exit(1)

	if response.status_code != 200:
		print(f"Failed to download: {response.status_code}")
		print("Headers: ", response.headers)
		print("Content: ", response.content.decode())
		sys.exit(1)

	return response, session_data


#============================================

def download_image(file_id):
	global service
	# Initialize the file request for downloading the image
	#print(f"fileId={file_id}")
	#print("request = service.files().get_media(fileId=file_id)")
	request = service.files().get_media(fileId=file_id)

	# Get the file metadata to retrieve the filename
	#file_metadata = service.files().get(fileId=file_id).execute()
	file_metadata = service.files().get(fileId=file_id, supportsAllDrives=True).execute()
	#print("file_metadata = service.files().get(fileId=file_id).execute()")
	filename = file_metadata['name'].lower()
	#print(f"file_metadata['name'].lower() = {filename}")
	mime_parts = file_metadata['mimeType'].split('/')
	if mime_parts[0] != 'image':
		print(file_metadata)
		raise TypeError
	filename = filename.replace(' ', '_')
	if not filename.endswith(mime_parts[1]):
		print(file_metadata)
		filename = filename + "." + mime_parts[1]
		#raise TypeError
	try:
		import rmspaces
		filename = rmspaces.cleanName(filename)
	except ImportError:
		pass

	# Use an in-memory byte stream to hold the downloaded file
	file_data = io.BytesIO()

	print("downloader = googleapiclient.http.MediaIoBaseDownload(file_data, request)")
	# Initialize downloader
	downloader = googleapiclient.http.MediaIoBaseDownload(file_data, request)

	# Perform the download in chunks
	done = False
	while not done:
		status, done = downloader.next_chunk()
		time.sleep(random.random() / 100.)

	# Reset stream position to start
	file_data.seek(0)
	time.sleep(random.random() / 10)

	# Return the byte stream and filename to caller
	return file_data, filename

#============================================

def inspect_image_data(image_data) -> tuple:
	"""
	return its file type, corner pixel RGB values, and updated session data.
	"""
	# Create a PIL Image object from the downloaded data
	pil_image = PIL.Image.open(image_data)

	# Ensure the image is in RGB mode
	if pil_image.mode != 'RGB':
		print(f"Wrong image mode {pil_image.mode}")
		time.sleep(1)
		pil_image = pil_image.convert('RGB')

	named_corner_pixels_dict = get_pixel_data(pil_image)
	image_data.seek(0)

	return named_corner_pixels_dict

#============================================

def download_image_and_inspect(image_url: str) -> tuple:
	"""
	Download an image from Google Drive and return its file type, corner pixel RGB values, and updated session data.

	Parameters:
		image_url : str
			The Google Drive URL of the image to be downloaded.
		session_data : requests.Session, optional
			A requests.Session object for persisting parameters across requests.

	Returns:
		tuple
			A tuple containing the file type as a string, a dictionary with corner pixel named colors, and updated session data.
	"""
	file_id = get_file_id_from_google_drive_url(image_url)
	image_data, filename = download_image(file_id)

	time.sleep(random.random() / 10)
	#print(image_data)

	# Create a PIL Image object from the downloaded data
	pil_image = PIL.Image.open(image_data)
	#print(pil_image)

	# Ensure the image is in RGB mode
	if pil_image.mode != 'RGB':
		print(f"Wrong image mode {pil_image.mode}")
		time.sleep(1)
		pil_image = pil_image.convert('RGB')

	named_corner_pixels_dict = get_pixel_data(pil_image)

	return named_corner_pixels_dict, filename, image_data

#============================================

def get_hash_data(image_data):
	phash = calculate_phash(image_data)
	md5hash = calculate_md5(image_data)
	return md5hash, phash

#============================================

# Test the function
if __name__ == "__main__":
	# The file ID to download, replace with your file's ID
	file_id = '1QCHoMnqKvf6gqLI272ZQ4IGBCFupnC6s'

	# Download the file
	file_data, filename = download_image(file_id)

	# Replace the Google Drive URL with a valid one
	session_data = None
	image_url = "https://drive.google.com/u/2/open?usp=forms_web&id=1-Fvg5kCYB1-QUjjMtqjshpqgmfG1kTVq"

	image_format, named_corner_pixels_dict, filename, phash, md5hash, image_data = download_image_and_inspect(image_url)
	print(f"Image format: {image_format}")
	print(f"Corner pixel RGB values: {named_corner_pixels_dict}")

	image_url = "https://drive.google.com/u/2/open?usp=forms_web&id=1QCHoMnqKvf6gqLI272ZQ4IGBCFupnC6s"
	image_format, named_corner_pixels_dict, filename, phash, md5hash, image_data = download_image_and_inspect(image_url)
	print(f"Image format: {image_format}")
	print(f"Corner pixel RGB values: {named_corner_pixels_dict}")
