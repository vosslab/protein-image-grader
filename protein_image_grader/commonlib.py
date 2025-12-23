#!/usr/bin/env python3

import os
import re
import sys
import glob
import time
import random
#import unicode
import unicodedata

#import apDisplay

"""
File for common functions to musiclib, movielib, and photolib
"""

class CommonLib(object):
	#=======================
	def humantime(self, secs: float) -> str:
		"""
		Converts time in seconds into a human-readable format: days, hours, minutes, and seconds.

		Args:
			secs (float): The time duration in seconds.

		Returns:
			str: The time in a human-readable format (e.g., '02d:03h', '01h:45m', '10m:30s', or '0.5s').
		"""
		mins, secs = divmod(secs, 60)
		hours, mins = divmod(mins, 60)
		days, hours = divmod(hours, 24)

		if days > 0:
			return f'{int(days):02d}d:{int(hours):02d}h'
		elif hours > 0:
			return f'{int(hours):02d}h:{int(mins):02d}m'
		elif mins > 0:
			return f'{int(mins):02d}m:{int(secs):02d}s'
		elif secs > 0.2:
			return f'{secs:.1f}s'
		else:
			return f'{secs:.1e}s'

	#==============
	def isint(self, n: str) -> bool:
		"""
		Checks if the given string represents an integer.

		Args:
			n (str): The input string to check.

		Returns:
			bool: True if the string is a valid integer, otherwise False.
		"""
		return bool(re.fullmatch(r"\d+", n))

	#==============
	def extraCleanName(self, f: str) -> str:
		"""
		Cleans a name string further by making it lowercase and removing underscores and hyphens.

		Args:
			f (str): The input string to clean.

		Returns:
			str: A fully cleaned name string, or 'None' if the name couldn't be cleaned.
		"""
		g = self.cleanName(f)
		if g is None:
			return 'None'

		g = self.cleanName(g.lower())
		if g is None:
			return 'None'

		g = g.replace("_", "").replace("-", "")
		return g.lower()

	#=======================
	def compareStrings(self, s1, s2):
		size = max(len(s1), len(s2))
		return self.levenshtein(s1, s2)/float(size)

	#=======================
	def levenshtein(self, s1, s2):
		if len(s1) < len(s2):
			return self.levenshtein(s2, s1)
		if not s1:
			return len(s2)

		previous_row = list(range(len(s2) + 1))
		for i, c1 in enumerate(s1):
			current_row = [i + 1]
			for j, c2 in enumerate(s2):
				insertions = previous_row[j + 1] + 1 # j+1 instead of j since previous_row and current_row are one character longer
				deletions = current_row[j] + 1       # than s2
				substitutions = previous_row[j] + (c1 != c2)
				current_row.append(min(insertions, deletions, substitutions))
			previous_row = current_row

		return previous_row[-1]

	#==============
	def cleanName(self, f: str, cut: bool = True) -> str:
		"""
		Cleans up a given file or string name by removing or replacing special characters, adjusting case,
		and shortening the length if necessary.

		Args:
			f (str): The name or string to clean.
			cut (bool): Whether to shorten the result if it's longer than 40 characters.

		Returns:
			str: The cleaned-up version of the input string.
		"""
		# Special cases replacements for certain symbols or phrases
		specials = {
			"!!!": "ChkChkChk",
			"!": "Exclaim",
			"*": "Asterix",
			"( )": "Parens",
			"+/-": "PlusMinus",
		}

		# Common words to be retained during cleaning
		words = ['of', 'the', 'a', 'in', 'for', 'am', 'is', 'on', 'to', 'than', 'with', 'by', 'from', 'or', 'and']

		# Handle None input
		if f is None:
			return None

		# Initial stripping of whitespace
		g = f.strip()

		# Check if the string is in the specials dictionary
		if g in specials:
			return specials[g]

		# If the string is empty after stripping
		if len(g) < 1:
			return None

		# Convert Unicode characters to ASCII (assuming self.unicodeToString exists)
		g = self.unicodeToString(g)

		# Replace various symbols with underscores or remove unwanted characters
		g = re.sub(r"['\" \[\]]", "_", g)  # Replace space, single/double quotes, and square brackets with '_'

		# Remove articles like 'the_', 'an_', and 'a_' at the start of the string
		g = re.sub(r"^(the_|an_|a_)", "", g, flags=re.IGNORECASE)

		# Replace '&' with 'and'
		g = g.replace("&", "and")

		# Remove all non-alphanumeric characters, underscores, and hyphens
		g = re.sub(r"[^a-zA-Z0-9_-]", "_", g)

		# Preserve case for common words found in the middle of underscores
		for word in words:
			g = re.sub(rf"_{word}_", f"_{word}_", g, flags=re.IGNORECASE)

		# Replace 'feat', 'featuring', or 'ft' with 'and' at the end of the string
		g = re.sub(r"[_ ]feat(?:uring)?[_ ][a-zA-Z0-9 _-]*$", "and", g, flags=re.IGNORECASE)

		# Debug print for 'feat' matches found elsewhere in the string
		if re.search(r"[^a-z]feat[^a-z]", g):
			print(g)

		# Handle special cases for other symbols
		g = re.sub(r"[,\^]", "_", g)  # Replace commas and '^' with underscores
		g = re.sub(r"^-", "", g)      # Remove hyphen at the start
		g = re.sub(r"_+-+_?", "-", g) # Handle mixed underscores and hyphens
		g = re.sub(r"__+", "_", g)    # Collapse multiple underscores into one

		# Trim trailing and leading underscores
		g = g.strip("_")

		# Handle specific cases where the cleaned name might be problematic
		if g == "unknown":
			return None

		# Debug print for weird characters
		if re.search(r"[^a-zA-Z0-9_-]", g):
			print(f"\033[1;32mWeird character: {g}\033[0m")
			time.sleep(2)

		# Final validation before returning the name
		if len(g) == 0:
			print(f"\033[31mERROR: {f}\033[0m")
			sys.exit(1)

		# Optionally shorten the string to 40 characters if 'cut' is True
		if cut and len(g) > 40:
			g = re.sub(r"_[0-9]*$", "", g)  # Remove trailing numbers
			g = g[:40]

		# Final trimming of trailing underscores
		g = g.rstrip("_")

		# Capitalize the first letter if the name is long enough
		if len(g) > 1:
			g = g[0].upper() + g[1:]

		return g

	#===============
	def getMountPoint(self, filename):
		"""
		returns file or directory mount point
		"""
		path = os.path.abspath(filename)
		while not os.path.ismount(path):
			path = os.path.dirname(path)
		return path

	#===============
	def fileSize(self, filename):
		"""
		return file size in bytes
		"""
		if not os.path.isfile(filename):
			return 0
		stats = os.stat(filename)
		size = stats[6]
		return size

	#=======================
	def unicodeToString(self, data):
		if data is None:
			return ''
		if not isinstance(data, str):
			try:
				data = data.decode("utf-8")
			except AttributeError:
				data = str(data)
		try:
			string = unicodedata.normalize('NFKD', data)
		except TypeError:
			string = str(data)
		only_ascii = string.encode('ASCII', 'ignore').decode('ASCII')
		return only_ascii

	#===============
	def md5sumfile(self, filename):
		"""
		Returns an md5 hash for file filename
		"""
		if not os.path.isfile(filename):
			raise ValueError(f"MD5SUM, file not found: {filename}")
		print(("MD5SUM "+filename))
		f = open(filename, 'rb')
		import hashlib
		m = hashlib.md5()
		while True:
			d = f.read(8096)
			if not d:
				break
			m.update(d)
		f.close()
		return m.hexdigest()

	#===============
	def quickmd5(self, filename):
		"""
		Returns a quick md5 hash for file filename
		"""
		if not os.path.isfile(filename):
			print((self.colorString("MD5SUM, file not found: "+filename, "red")))
			sys.exit(1)
		print(("QUICK MD5 "+filename))
		f = open(filename, 'rb')
		import hashlib
		m = hashlib.md5()
		for i in range(9):
			d = f.read(8096)
			if not d:
				break
			m.update(d)
			f.seek(8096)
		f.close()
		return m.hexdigest()

	#=======================
	def getNumFilesInDir(self, dirname):
		absdirname = os.path.abspath(dirname)
		if not os.path.isdir(absdirname):
			return 0
		files = glob.glob(os.path.join(absdirname, "*.*"))
		return len(files)


	#=======================
	def getFiles(self, depth=6, extlist=[], folder=None, shuffle=False):
		files = []
		for ext in extlist:
			sstr = "*."+ext
			for i in range(depth+1):
				if folder is not None:
					sstr2 = os.path.join(folder, sstr)
				else:
					sstr2 = sstr
				files.extend(glob.glob(sstr2))
				sstr = "*/"+sstr
		files.sort()
		if shuffle is True:
			random.shuffle(files)
		print(("Found %d files"%(len(files))))
		return files

	#=======================
	def rightPadString(self, s,n=10,fill=" "):
		n = int(n)
		s = str(s)
		if(len(s) > n):
			return s[:n]
		while(len(s) < n):
			s += fill
		return s

	#=======================
	def leftPadString(self, s,n=10,fill=" "):
		n = int(n)
		s = str(s)
		if(len(s) > n):
			return s[:n]
		while(len(s) < n):
			s = fill+s
		return s

	#=======================
	def colorString(self, text, fg=None, bg=None):
		"""Return colored text.
		Uses terminal color codes; set avk_util.enable_color to 0 to
		return plain un-colored text. If fg is a tuple, it's assumed to
		be (fg, bg). Both colors may be 'None'.
		"""
		colors = {
			"black" :"30",
			"red"   :"31",
			"green" :"32",
			"brown" :"33",
			"orange":"33",
			"blue"  :"34",
			"violet":"35",
			"purple":"35",
			"magenta":"35",
			"maroon":"35",
			"cyan"  :"36",
			"lgray" :"37",
			"gray"  :"1;30",
			"lred"  :"1;31",
			"lgreen":"1;32",
			"yellow":"1;33",
			"lblue" :"1;34",
			"pink"  :"1;35",
			"lcyan" :"1;36",
			"white" :"1;37"
		}
		if fg is None:
			return text
		if type(fg) in (tuple, list):
			fg, bg = fg
		if not fg:
			return text
		opencol = "\033["
		closecol = "m"
		clear = opencol + "0" + closecol
		xterm = 0
		if os.environ.get("TERM") is not None and os.environ.get("TERM") == "xterm":
			xterm = True
		else:
			xterm = False
		b = ''
		# In xterm, brown comes out as yellow..
		if xterm and fg == "yellow":
			fg = "brown"
		f = opencol + colors[fg] + closecol
		if bg:
			if bg == "yellow" and xterm:
				bg = "brown"
			try:
				b = colors[bg].replace('3', '4', 1)
				b = opencol + b + closecol
			except KeyError:
				pass
		return "%s%s%s%s" % (b, f, text, clear)


if __name__ == '__main__':
	CL = CommonLib()
