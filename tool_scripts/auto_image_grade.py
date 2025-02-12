


def auto_grade_images(student_tree: list):
	for student_entry in student_tree:
		lower_filename = student_entry['Original Filename'].lower()
		if lower_filename.startswith('screenshot') or lower_filename.startswith('screen_shot'):
			console.print("  \aWARNING: image filename starts with screenshot", style=warning_color)
			student_entry['Warnings'].append("likely screenshot")

		if named_corner_pixels_dict['consensus'] != "White":
			console.print("  WARNING: image does not have White Background", style=warning_color)
			student_entry['Warnings'].append("non-white background")
			if named_corner_pixels_dict['consensus'] is False:
				console.print(named_corner_pixels_dict)
			else:
				console.print(f"  Consensus Color: {named_corner_pixels_dict['consensus']}")
