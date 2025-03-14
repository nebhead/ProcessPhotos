from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS
#from common import *
import piexif

# Dependencies need to be installed: Pillow, piexif

def is_valid_image(file_path):
	try:
		with Image.open(file_path) as img:
			format = img.format
			if format in ['TIFF', 'JPEG', 'PNG', 'WEBP']:
				return True
			else:
				return False
	except (IOError, SyntaxError):
		return None

""" This function will take an image path and return the exif data of the image.  Returns none if no exif data is found.  Only processes images with valid exif data such as TIFF, JPG, PNG and WEBP. """
def get_exif_data(image_path):
	# Check if the image is a valid image file
	#logger = create_logger('app', filename='logs/app.log')
	
	if not is_valid_image(image_path):
		return None
	try:
		# Open the image file
		image = Image.open(image_path)
		
		# Extract EXIF data
		exif = image.getexif()
		if not exif:
			return None
			
		# Create a dictionary to store EXIF data with readable labels
		exif_data = {}
		
		for tag_id in exif:
			# Get the tag name, instead of just the id
			tag = TAGS.get(tag_id, tag_id)
			data = exif.get(tag_id)
			
			# Decode bytes if necessary
			if isinstance(data, bytes):
				try:
					data = data.decode()
				except UnicodeDecodeError:
					data = data.hex()
					
			exif_data[tag] = data
			
		return exif_data
		
	except FileNotFoundError:
		#print(f"Error: The file {image_path} was not found.")
		#logger.error(f"Error: The file {image_path} was not found.")
		return None
	except Exception as e:
		#print(f"Error: {str(e)}")
		#logger.error(f"Error: {str(e)}")
		return None

""" This function will check an exif dictionary for a valid date.  If a valid date is found, it will return the date.  If no valid date is found, it will return None. """
def get_exif_date(exif_data):
	"""
	Extract the date the image was taken from EXIF data.

	Args:
		exif_data (dict): Dictionary containing EXIF data
		
	Returns:
		datetime or None: DateTime object of when the image was taken, or None if not found
	"""
	if not isinstance(exif_data, dict):
		return None
		
	# List of possible EXIF date tags in order of preference
	date_tags = [
		'DateTimeOriginal',  # When the original image was taken
		'DateTimeDigitized', # When the image was stored digitally
		'DateTime'           # When the file was last changed
	]

	for tag in date_tags:
		if tag in exif_data:
			try:
				# EXIF dates are typically in format: "YYYY:MM:DD HH:MM:SS"
				date_str = exif_data[tag]
				return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
			except ValueError:
				continue
				
	return None

def write_date_to_exif(image_path, date=None):
	"""
	Write a date to an image's EXIF data. If no date is provided, current date is used.

	Args:
		image_path (str): Path to the image file
		date (datetime, optional): Date to write to EXIF. Defaults to current date.
	"""
	#logger = create_logger('app', filename='logs/app.log')
	result = False
	
	# If no date provided, use current date
	if date is None:
		date = datetime.now()
	
	# Convert date to datetime object if necessary
	if not isinstance(date, datetime):
		try:
			date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
		except:
			date = datetime.now()

	# Format date according to EXIF specification
	date_string = date.strftime("%Y:%m:%d %H:%M:%S")

	try:
		# Open the image
		image = Image.open(image_path)
		
		# Get existing EXIF data or create new if none exists
		try:
			exif_dict = piexif.load(image.info["exif"])
		except:
			exif_dict = {
				"0th": {},
				"Exif": {},
				"GPS": {},
				"1st": {},
				"thumbnail": None
			}
		
		# Update date fields in EXIF
		# DateTime (0x0132) - The date and time of image creation
		exif_dict["0th"][piexif.ImageIFD.DateTime] = date_string
		# DateTimeOriginal (0x9003) - The date and time when the original image data was generated
		exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_string
		# DateTimeDigitized (0x9004) - The date and time when the image was stored as digital data
		exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = date_string
		
		# Convert EXIF dict to bytes
		exif_bytes = piexif.dump(exif_dict)
		
		# Save the image with updated EXIF data
		image.save(image_path, exif=exif_bytes)
		#print(f"Successfully updated EXIF date for {image_path}")
		#logger.info(f"Successfully updated EXIF date for {image_path}")
		result = True
		
	except Exception as e:
		#print(f"Error updating EXIF data: {str(e)}")
		#logger.error(f"Error updating EXIF data: {str(e)}")
		pass

	finally:
		if 'image' in locals():
			image.close()

	return result	