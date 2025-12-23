#!/usr/bin/env python3

import os
import sys
import csv
import time
import urllib.request, urllib.parse, urllib.error
import subprocess
import test_google_image
import PIL.Image
import googleapiclient.errors
from pillow_heif import register_heif_opener

register_heif_opener()

#google_id = 2

image_dir = 'PROFILE_IMAGES'

def get_image_html_tag(image_url: str) -> str:
	print(image_url)
	file_id = test_google_image.get_file_id_from_google_drive_url(image_url)
	print(file_id)
	# Download the file
	try:
		image_data, filename = test_google_image.download_image(file_id, test_google_image.service)
	except googleapiclient.errors.HttpError as e:
		print(e)
		time.sleep(1)
		return ''
	print(filename)
	filename = filename.lower()
	if not filename.endswith('.jpg') and not filename.endswith('.png'):
		filename = os.path.splitext(filename)[0] + '.jpg'
	if not os.path.isdir(image_dir):
		os.makedirs(image_dir)
	print(filename)
	filename = os.path.join(image_dir, filename)
	filename = os.path.abspath(filename)
	#with open(filename, 'w') as file_handle:
	#print(dir(image_data))
	if not os.path.isfile(filename):
		pil_image = PIL.Image.open(image_data)
		pil_image.save(filename)
	html_tag =f"<a target='_blank' href='file://{filename}'>"
	html_tag += f"<img border='1' src='file://{filename}' height='350' />"
	html_tag += "</a>"
	print('')
	return html_tag

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
	# Parse the URL to get its components
	url_parts = urllib.parse.urlparse(image_url)

	# Extract the query parameters
	query = urllib.parse.parse_qs(url_parts.query)

	# Extract the file_id from the query parameters
	file_id = query['id'][0] if 'id' in query else None

	# If file_id is None, return None as we can't proceed without a file ID
	if file_id is None:
		return None

	# Construct and return the direct download URL
	#direct_download_url = f'https://drive.google.com/file/d/{file_id}/view'
	direct_download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

	return direct_download_url


def printUsage():
	print("usage: studentProfile.py <csv file>")
	sys.exit(1)

def writeHeader(output, filename):
	output.write("<html><head>\n")
	title = (os.path.splitext(filename)[0]).title()
	output.write("<title>%s</title>\n"%(title))
	output.write("</head><body>\n")

def findFirstNameKeyIndexFromHeader(header):
	for i, item in enumerate(header):
		sitem = item.strip().lower()
		if 'first' in sitem and 'name' in sitem:
			return i
	#backup idea
	for i, item in enumerate(header):
		sitem = item.strip().lower()
		if 'full' in sitem and 'name' in sitem:
			return i
	return None


if len(sys.argv) < 2:
	printUsage()
csvfile = sys.argv[1]
if not os.path.exists(csvfile):
	printUsage()


data_tree = []
first_name_key_index = None


f = open(csvfile, "r")
data = csv.reader(f)
header = None
count = 0
for row in data:
	if header is None:
		header = row
		first_name_key_index = findFirstNameKeyIndexFromHeader(header)
		continue
	data_tree.append(row)
try:
	data_tree.sort(key=lambda x:x[first_name_key_index].lower().strip())
except TypeError:
	pass

output = open("profiles.html", "w")
writeHeader(output, csvfile)
count = 0
for row in data_tree:
	count += 1
	if count > 1:
		output.write('<br/><p style="page-break-before: always"><br/></p>\n')
	for i, item in enumerate(row):
		if len(item) < 1:
			continue
		elif item.startswith('http'):
			img_html_tag = get_image_html_tag(item)
			output.write(f"{img_html_tag}\n")
		else:
			output.write("<p><b>%s</b>:\n"%(header[i].strip()))
			output.write("&nbsp; %s</p>\n"%(row[i].strip()))

f.close()
output.close()
#cmd = "open -a /Applications/Google\ Chrome.app profiles.html"
#cmd = "open -a /Applications/Vivaldi.app profiles.html"
cmd = "open -a /Applications/Firefox.app profiles.html"
print(cmd)
proc = subprocess.Popen(cmd, shell=True)
proc.communicate()
