#!/usr/bin/env python3

"""
 *****************************************
 	Common Script
 *****************************************

 Description: Common functions used by multiple scripts.  

 *****************************************
"""

import datetime
import json
import yaml
import io
import logging
import os
import sys
from collections.abc import Mapping
from logging.handlers import RotatingFileHandler

"""
Globals
"""

CONFIG_FOLDER = 'config/'

"""
Common Functions
"""

def create_logger(name, filename='logs/app.log', messageformat='%(asctime)s | %(levelname)s | %(message)s', level=logging.INFO):
	'''Create or Get Existing Logger'''
	logger = logging.getLogger(name)
	''' 
		If the logger does not exist, create one. Else return the logger. 
		Note: If the a log-level change is needed, the developer should directly set the log level on the logger, instead of using 
		this function.  
	'''
	if not logger.hasHandlers():
		# Create logs directory if it doesn't exist
		os.makedirs(os.path.dirname(filename), exist_ok=True)
		
		# datefmt='%Y-%m-%d %H:%M:%S'
		formatter = logging.Formatter(fmt=messageformat, datefmt='%Y-%m-%d %H:%M:%S')

		# File Handler - Rotating log file
		try:
			file_handler = RotatingFileHandler(
				filename,
				maxBytes=10485760,  # 10MB
				backupCount=10,
				delay=True  # Don't open the file until we need to write
			)
			file_handler.setFormatter(formatter)
			file_handler.setLevel(level)
		except Exception as e:
			print(f"Error setting up file handler: {e}")
			file_handler = None
		
		# Stream Handler - Console output for Docker Support
		stream_handler = logging.StreamHandler(sys.stdout)
		stream_handler.setFormatter(formatter)
		stream_handler.setLevel(level)
		
		# Remove default handlers and add our custom ones
		logger.handlers = []
		if file_handler:
			logger.addHandler(file_handler)
		logger.addHandler(stream_handler)
		logger.setLevel(level)
		
		# Log startup message
		logger.info("Logger initialized successfully")

	return logger

def default_settings():
	settings = {}

	settings['versions'] = read_generic_json('versions.json')['versions']

	settings['globals'] = {
		'debug' : False,
		'log_level' : logging.ERROR,
		'public_url': '',
		'theme': 'bootstrap-yeti.min.css', # default to base theme, bootstrap-yeti.min.css 
		'themelist': [
			{
				'name' : 'Bootstrap',
			 	'filename' : 'bootstrap.min.css'
			},
			{
				'name' : 'Darkly',
			 	'filename' : 'bootstrap-darkly.min.css'
			},
			{
				'name' : 'Flatly',
			 	'filename' : 'bootstrap-flatly.min.css'
			},
			{
				'name' : 'Litera',
			 	'filename' : 'bootstrap-litera.min.css'
			},
			{
				'name' : 'Lumen',
			 	'filename' : 'bootstrap-lumen.min.css'
			},
			{
				'name' : 'Lux',
			 	'filename' : 'bootstrap-lux.min.css'
			},
			{
				'name' : 'Sandstone',
			 	'filename' : 'bootstrap-sandstone.min.css'
			},
			{
				'name' : 'Slate',
			 	'filename' : 'bootstrap-slate.min.css'
			},
			{
				'name' : 'Superhero',
			 	'filename' : 'bootstrap-superhero.min.css'
			},
			{
				'name' : 'Yeti (Default)',
			 	'filename' : 'bootstrap-yeti.min.css'
			},
			{
				'name' : 'Zephyr',
			 	'filename' : 'bootstrap-zephyr.min.css'
			}
		],
	}

	settings['platform'] = {
		'real_hw': False
	}

	settings['folders'] = {
		'originals' : 'originals',
		'import' : 'import',
		'export' : 'export'
	}

	settings['ui'] = {
		'show_all_thumbnails' : False,
		'auto_flag_processed' : True
	}

	settings['scripts'] = {
		'post_proc' : {
			'path' : 'config/',
			'type' : 'bash',
			'script' : 'postproc.sh'
		},
		'pre_proc' : {
			'path' : 'config/',
			'type' : 'bash',
			'script' : 'preproc.sh'
		}
	}

	settings['backup'] = {
		'retention_days': 7,
		'enabled': True
	}

	return settings

def read_settings(filename=f'{CONFIG_FOLDER}settings.json', init=False, retry_count=0):
	"""
	Read Settings from file

	:param filename: Filename to use (default settings.json)
	"""

	try:
		json_data_file = os.fdopen(os.open(filename, os.O_RDONLY))
		json_data_string = json_data_file.read()
		settings = json.loads(json_data_string)
		json_data_file.close()

	except(IOError, OSError):
		""" Settings file not found, create a new default settings file """
		settings = default_settings()
		write_settings(settings)
		return(settings)
	except(ValueError):
		# A ValueError Exception occurs when multiple accesses collide, this code attempts a retry.
		event = 'ERROR: Value Error Exception - JSONDecodeError reading settings.json'
		write_log(event)
		json_data_file.close()
		# Retry Reading Settings
		if retry_count < 5: 
			settings = read_settings(filename=filename, retry_count=retry_count+1)
		else:
			""" Undefined settings file load error, indicates corruption """
			init = True

	if init:
		# Get latest settings format
		settings_default = default_settings()

		# Overlay the read values over the top of the default settings
		#  This ensures that any NEW fields are captured.  
		if semantic_ver_is_lower(settings['versions']['server_base'], settings_default['versions']['server_base']):
			''' Upgrade Path '''
			warning = f'Upgrading your settings from {settings["versions"]["server_base"]} to {settings_default["versions"]["server_base"]}.'
			write_log(warning)
			prev_ver = semantic_ver_to_list(settings['versions']['server_base'])
			settings = upgrade_settings(prev_ver, settings, settings_default)

		elif (settings_default['versions']['server_base'] == settings['versions']['server_base']) and (int(settings['versions']['server_build']) < settings_default['versions']['server_build']):
			''' Minor Upgrade Path '''
			warning = f'Upgrading your settings from build {settings["versions"]["server_build"]} to {settings_default["versions"]["server_build"]}.'
			write_log(warning)
			prev_ver = semantic_ver_to_list(settings['versions']['server_base'])
			settings = upgrade_settings(prev_ver, settings, settings_default)

		# Overwrite the versions block in the settings from the settings_default
		settings['versions'] = settings_default['versions']

		# Overlay the original settings on top of the default settings
		settings = deep_update(settings_default, settings)

		write_settings(settings)

	return(settings)

def write_settings(settings):
	"""
		# Write settings from JSON
	"""
	filename = CONFIG_FOLDER + "settings.json"
	json_data_string = json.dumps(settings, indent=2, sort_keys=True)
	with open(filename, 'w') as settings_file:
	    settings_file.write(json_data_string)

def upgrade_settings(prev_ver, settings, settings_default):
	''' Check if upgrading from v0.1.4 or earlier '''
	if prev_ver[0] == 0 and prev_ver[1] <= 4:
		''' Update the folders to remove ./ from each path, re-write folders.json '''
		settings['folders'] = settings_default['folders']
		folder_status = read_folder_status(reset=True)
		write_folder_status(folder_status)

	return settings 


def get_unique_id():
	"""
		# Create a unique ID based on the time
	"""
	now = str(datetime.datetime.now())
	now = now[0:19] # Truncate the microseconds

	ID = ''.join(filter(str.isalnum, str(datetime.datetime.now())))
	return(ID)

'''
is_raspberrypi() function borrowed from user https://raspberrypi.stackexchange.com/users/126953/chris
  in post: https://raspberrypi.stackexchange.com/questions/5100/detect-that-a-python-program-is-running-on-the-pi
'''
def is_raspberrypi():
	try:
		with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
			if 'raspberry pi' in m.read().lower(): return True
	except Exception: pass
	return False

def is_real_hardware(settings=None):
	"""
	Check if running on real hardware as opposed to a prototype/test environment.

	:return: True if running on real hardware (i.e. Raspberry Pi), else False. 
	"""
	if settings == None:
		settings = read_settings()

	return True if settings['platform']['real_hw'] else False 

def restart_scripts():
	"""
	Restart the Control and WebApp Scripts
	"""
	if is_real_hardware():
		os.system("sleep 3 && sudo service supervisor restart &")

def reboot_system():
	"""
	Reboot the system
	"""
	if is_real_hardware():
		os.system("sleep 3 && sudo reboot &")

def shutdown_system():
	"""
	Shutdown the system
	"""
	if is_real_hardware():
		os.system("sleep 3 && sudo shutdown -h now &")

def read_generic_json(filename):
	try:
		json_file = os.fdopen(os.open(filename, os.O_RDONLY))
		json_data = json_file.read()
		dictionary = json.loads(json_data)
		json_file.close()
	except: 
		dictionary = {}
		event = f'An error occurred loading {filename}'
		write_log(event)

	return dictionary

def write_generic_json(dictionary, filename):
	try: 
		json_data_string = json.dumps(dictionary, indent=2, sort_keys=True)
		with open(filename, 'w') as json_file:
			json_file.write(json_data_string)
	except:
		event = f'Error writing generic json file ({filename})'
		write_log(event)

def read_generic_yaml(filename):
	try:
		yaml_file = os.fdopen(os.open(filename, os.O_RDONLY))
		yaml_data = yaml.safe_load(yaml_file)
	except:
		event = f'An error occurred loading {filename}'
		write_log(event)
		yaml_data = {}

	return yaml_data

def write_generic_yaml(dictionary, filename):
	try: 
		with open(filename, 'w') as yaml_file:
			yaml.dump(dictionary, yaml_file, default_flow_style=False)
	except:
		event = f'Error writing generic yaml file ({filename})'
		write_log(event)

def deep_update(dictionary, updates):
	for key, value in updates.items():
		if isinstance(value, Mapping):
			dictionary[key] = deep_update(dictionary.get(key, {}), value)
		else:
			dictionary[key] = value
	return dictionary

def write_log(event, log_level=logging.INFO):
	"""
	Write event to event.log

	:param event: String event
	"""
	log_level = logging.INFO
	#eventLogger = create_logger('events', filename='/tmp/events.log', messageformat='%(asctime)s [%(levelname)s] %(message)s', level=log_level)
	event_logger = create_logger('app', filename='logs/app.log', level=log_level)
	event_logger.info(event)

def scan_directory(path='originals'):
	"""
	Scans a directory and returns a dictionary containing information about its contents.

	Args:
		path (str): Path to the directory to scan
		
	Returns:
		dict: Dictionary containing:
			- path: Current directory path
			- files: List of files in the directory
			- subfolders: Dictionary of subdirectories with same structure
			- processed: Boolean flag for tracking processing status
	"""
	result = {
		'processed': False,
		'path': path,
		'num_files': 0,
		'num_subfolders': 0,
		'files': [],
		'subfolders': {}
	}

	# Check if path exists and is a directory
	if not os.path.exists(path) or not os.path.isdir(path):
		return result
		
	# Get all items in directory
	try:
		items = os.listdir(path)
		
		for item in items:
			full_path = os.path.join(path, item)
			
			# If item is a file, add to files list
			if os.path.isfile(full_path):
				result['files'].append(item)
			# If item is a directory, recursively scan it
			elif os.path.isdir(full_path):
				result['subfolders'][item] = scan_directory(full_path)
			
		result['num_files'] = len(result['files'])
		result['num_subfolders'] = len(result['subfolders'])
				
	except PermissionError:
		# Handle case where we don't have permission to access directory
		event = f"Permission denied: Cannot access {path}"
		write_log(event)
		return {} 

	except Exception as e:
		# Handle other potential errors
		event = f"Error scanning {path}: {str(e)}"
		write_log(event)
		return {}

	return result

def read_folder_status(path='config/folders.json', originals_path='originals', reset=False):
	"""
	Read the folder status from a JSON file

	:param path: Path to the folder status file
	:param originals_path: Path to scan for originals
	:param reset: Whether to force a rescan of the directory
	:return: JSON object with folder status
	"""
	folder_status = {}
	existing_status = {}
	
	try:
		# Try to read existing status file if it exists
		if os.path.exists(path):
			with open(path, 'r') as f:
				existing_status = json.load(f)
	except Exception as e:
		event = f"Warning: Could not read existing folder status: {e}"
		write_log(event)
		
	try:
		if reset:
			# Scan directory for new structure
			folder_status = {originals_path : scan_directory(path=originals_path)}
			# If we have existing status, overlay the processed flags
			if existing_status:
				folder_status = update_folder_status(folder_status, existing_status)
			write_folder_status(folder_status, path)
		else:
			if existing_status:
				folder_status = existing_status
			else:
				folder_status = {originals_path : scan_directory(path=originals_path)}
				write_folder_status(folder_status, path)
	except FileNotFoundError:
		event = f"Warning: Folder status file not found at {path}. Scanning directory instead."
		write_log(event)
		folder_status = {originals_path : scan_directory(path=originals_path)}
		write_folder_status(folder_status, path)
	
	return folder_status

def write_folder_status(folder_status, path='config/folders.json'):
	"""
	Write the folder status to a JSON file, creating a timestamped backup if needed

	:param folder_status: JSON object containing folder status
	:param path: Path to the folder status file
	:return: folder_status object that was written
	"""
	try:
		# Create backup if file exists and has content
		if os.path.exists(path):
			try:
				with open(path, 'r') as f:
					existing = json.load(f)
					if existing:  # Only backup if there's actual content
						timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
						backup_path = f"{path}.{timestamp}.bak"
						with open(backup_path, 'w') as f:
							json.dump(existing, f, indent=2)
						event = f"Created backup of folder status at {backup_path}"
						write_log(event)
						
						# Clean up old backups
						cleanup_old_backups(path)
			except Exception as e:
				event = f"Warning: Could not create backup: {e}"
				write_log(event)
		
		# Write new status file
		with open(path, 'w') as f:
			json.dump(folder_status, f, indent=2)
		event = f"Folder status file written to {path}"
		write_log(event)
		
	except Exception as e:
		event = f"Error writing folder status file: {e}"
		write_log(event)
		raise

	return folder_status

def update_folder_status(new, current):

	def get_processed_flags(current, processed_list):
		for key, value in current.items():
			if isinstance(value, dict):
				if value['processed']:
					processed_list.append(value['path'])
				if value['subfolders'] != {}:
					get_processed_flags(value['subfolders'], processed_list)

	def set_processed_flags(new, processed_list):
		for key, value in new.items():
			if isinstance(value, dict):
				if value['path'] in processed_list:
					#print(f'Setting {value["path"]} as processed')
					value['processed'] = True
				if value['subfolders'] != {}:
					set_processed_flags(value['subfolders'], processed_list)

	#print(f'\n ** Attempting Overlay ** \n')
	
	processed_list = []
	get_processed_flags(current, processed_list)
	#print(f'Processed List: {processed_list}')
	set_processed_flags(new, processed_list)

	return new

def semantic_ver_to_list(version_string):
	# Count number of '.' in string
	decimal_count = version_string.count('.')
	ver_list = version_string.split('.')

	if decimal_count == 0:
		ver_list = [0, 0, 0]
	elif decimal_count < 2:
		ver_list.append('0')

	ver_list = list(map(int, ver_list))

	return(ver_list)

def semantic_ver_is_lower(version_A, version_B):
	version_A = semantic_ver_to_list(version_A)
	version_B = semantic_ver_to_list(version_B)
	
	if version_A [0] < version_B[0]:
		return True
	elif version_A [0] > version_B[0]:
		return False
	else:
		if version_A [1] < version_B[1]:
			return True
		elif version_A [1] > version_B[1]:
			return False
		else:
			if version_A [2] < version_B[2]:
				return True
			elif version_A [2] > version_B[2]:
				return False
	return False

def list_available_backups(path):
	"""
	List all available backups for a given file

	:param path: Path to the main JSON file (not the backup)
	:return: List of dictionaries containing backup information, sorted by date (newest first)
	"""
	backups = []
	try:
		directory = os.path.dirname(path)
		base_name = os.path.basename(path)
		
		if directory == "":
			directory = "."
			
		for filename in os.listdir(directory):
			if filename.startswith(base_name) and filename.endswith('.bak'):
				try:
					# Extract timestamp from filename
					timestamp_str = filename.split('.')[-2]
					file_date = datetime.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
					
					backup_path = os.path.join(directory, filename)
					file_size = os.path.getsize(backup_path)
					
					backups.append({
						'filename': filename,
						'path': backup_path,
						'date': file_date,
						'size': file_size
					})
				except (ValueError, IndexError):
					continue
					
		# Sort backups by date, newest first
		backups.sort(key=lambda x: x['date'], reverse=True)
		
	except Exception as e:
		event = f"Error listing backup files: {e}"
		write_log(event)
		
	return backups

def restore_backup(backup_path, target_path=None):
	"""
	Restore a backup file to its original location or a specified target

	:param backup_path: Path to the backup file to restore
	:param target_path: Optional path to restore to (if None, derives from backup name)
	:return: True if successful, False otherwise
	"""
	try:
		if target_path is None:
			# Remove the timestamp and .bak from the backup filename
			parts = backup_path.split('.')
			target_path = '.'.join(parts[:-2])
		
		# Create a backup of the current file before restoring
		if os.path.exists(target_path):
			write_folder_status(read_folder_status(target_path), target_path)
			
		# Restore the backup
		with open(backup_path, 'r') as source:
			data = json.load(source)
			with open(target_path, 'w') as target:
				json.dump(data, target, indent=2)
				
		event = f"Restored backup from {backup_path} to {target_path}"
		write_log(event)
		return True
		
	except Exception as e:
		event = f"Error restoring backup: {e}"
		write_log(event)
		return False

def cleanup_old_backups(path, days=None):
	"""
	Clean up backup files older than specified number of days

	:param path: Path to the main JSON file (not the backup)
	:param days: Optional number of days to keep backups (if None, uses settings value)
	"""
	# Read settings to get retention period
	settings = read_settings()
	if not settings['backup']['enabled']:
		return
		
	if days is None:
		days = settings['backup']['retention_days']
	try:
		# Get the directory and base filename
		directory = os.path.dirname(path)
		base_name = os.path.basename(path)
		
		# Get current time
		now = datetime.datetime.now()
		
		# Look for backup files
		if directory == "":
			directory = "."
		for filename in os.listdir(directory):
			if filename.startswith(base_name) and filename.endswith('.bak'):
				try:
					# Extract timestamp from filename (format: YYYYMMDD_HHMMSS)
					timestamp_str = filename.split('.')[-2]  # Get the timestamp part
					file_date = datetime.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
					
					# Calculate age in days
					age = now - file_date
					
					# Remove if older than specified days
					if age.days > days:
						file_path = os.path.join(directory, filename)
						os.remove(file_path)
						event = f"Removed old backup file: {filename}"
						write_log(event)
				except (ValueError, IndexError):
					# Skip files that don't match our timestamp format
					continue
	except Exception as e:
		event = f"Error cleaning up backup files: {e}"
		write_log(event)

