#!/usr/bin/env python3

"""
 *****************************************
	Flask Script
 *****************************************

 Description: WebUI for the project.  

 *****************************************
"""

"""
Imports
"""
import os
import threading
import uuid
import re
import subprocess
import json
import shutil

from flask import Flask, request, render_template, make_response, redirect, jsonify, abort, send_from_directory, Response, send_file
from common import *
from exif.exif import *
from typing import Dict
from datetime import datetime, timezone
import time

class ProcessRunningError(Exception):
	"""Raised when attempting to start a script while another is running"""
	pass

"""
Globals
"""
app = Flask(__name__)
settings = read_settings(init=True)
folder_status = read_folder_status(originals_path=settings['folders']['originals'])
import_data = []

IMPORT_FOLDER = settings['folders']['import']
EXPORT_FOLDER = settings['folders']['export']

# Track background processes
class ProcessTracker:
	def __init__(self):
		self._processes = {}  # Dictionary of process_id -> process object
		self._lock = threading.Lock()
		self._active_scripts = {}  # Dictionary to track scripts by type: "preprocess" or "postprocess"
		self._log_dir = 'logs/process_logs'
		# Create log directory if it doesn't exist
		try:
			os.makedirs(self._log_dir, exist_ok=True)
			if 'logger' in globals():
				logger.info(f"Process log directory: {self._log_dir}")
		except Exception as e:
			if 'logger' in globals():
				logger.error(f"Failed to create log directory {self._log_dir}: {e}")
			# Try to create it anyway if it doesn't exist
			if not os.path.exists(self._log_dir):
				raise
		
	def add_process(self, process, script_type=None, log_file=None):
		with self._lock:
			process_id = str(uuid.uuid4())
			self._processes[process_id] = {
				"process": process,
				"pid": process.pid if hasattr(process, "pid") else None,
				"start_time": datetime.now(),
				"type": script_type,
				"log_file": log_file,
				"status": "running",
				"return_code": None
			}
			
			# If this is a pre or post processing script, track it specifically
			if script_type in ["preprocess", "postprocess"]:
				self._active_scripts[script_type] = process_id
				
			logger.info(f"Added new process {process.pid} with ID {process_id} - Total processes: {len(self._processes)}")
			return process_id
			
	def remove_process(self, process_id):
		with self._lock:
			if process_id in self._processes:
				process_info = self._processes[process_id]
				# Remove from active scripts if it was one
				for script_type, active_id in list(self._active_scripts.items()):
					if active_id == process_id:
						del self._active_scripts[script_type]
						
				pid = process_info["pid"] if process_info["pid"] else "unknown"
				del self._processes[process_id]
				logger.info(f"Removed process {pid} with ID {process_id} - Total processes: {len(self._processes)}")
				return True
			return False

	def get_process_id_by_pid(self, pid):
		"""Get internal process ID from OS process ID"""
		with self._lock:
			for process_id, process_info in self._processes.items():
				if process_info["pid"] == pid:
					return process_id
			return None
	
	def get_process_info(self, process_id):
		"""Get detailed information about a process"""
		with self._lock:
			if process_id in self._processes:
				process_info = self._processes[process_id].copy()
				# Don't return the actual process object
				if "process" in process_info:
					del process_info["process"]
				return process_info
			return None

	def _cleanup_finished_processes(self):
		"""Helper method to mark finished processes and remove them from active tracking
		NOTE: This should only be called while holding self._lock"""
		finished_ids = []
		for process_id, process_info in self._processes.items():
			process = process_info["process"]
			try:
				if hasattr(process, "poll") and process.poll() is not None:  # Process has finished
					# Update status but keep in tracker for frontend to see completion
					self._processes[process_id]["status"] = "completed"
					self._processes[process_id]["return_code"] = process.poll()
					finished_ids.append(process_id)
					logger.info(f"Found finished process {process_info['pid']} with ID {process_id} - Return code: {process.poll()}")
			except Exception as e:
				logger.error(f"Error checking process {process_info['pid']} with ID {process_id}: {e}")
				self._processes[process_id]["status"] = "error"
				finished_ids.append(process_id)  # Mark problematic processes as error
		
		# Remove from active scripts tracking, keep process info for frontend
		for process_id in finished_ids:
			process_info = self._processes[process_id]
			# Remove from active scripts if it was one
			for script_type, active_id in list(self._active_scripts.items()):
				if active_id == process_id:
					del self._active_scripts[script_type]
					pid = process_info["pid"] if process_info["pid"] else "unknown"
					logger.info(f"Removed {script_type} script from active tracking - PID: {pid}, ID: {process_id}")
				
	def has_running_processes(self, script_type=None):
		with self._lock:
			# Clean up any finished processes first
			self._cleanup_finished_processes()
			
			# If script_type specified, only check that type
			if script_type:
				return script_type in self._active_scripts
				
			# Check if any processes are still running (status == "running")
			return any(p["status"] == "running" for p in self._processes.values())

	def get_active_process_id(self, script_type):
		"""Return the active process_id for a given script type, or None"""
		with self._lock:
			# Clean up any finished processes first
			self._cleanup_finished_processes()
			return self._active_scripts.get(script_type)
			
	def get_status(self):
		with self._lock:
			# Clean up any finished processes first
			self._cleanup_finished_processes()
			
			# Count only processes that are still running (not completed or error)
			running_count = sum(1 for p in self._processes.values() if p["status"] == "running")
			
			# Get counts for different script types
			status = {
				"running_processes": running_count,
				"preprocess_running": "preprocess" in self._active_scripts,
				"postprocess_running": "postprocess" in self._active_scripts,
				"active_pids": [],
				"timestamp": datetime.now().isoformat()
			}
			
			# Add active PIDs for detailed info (only running processes)
			for process_id, process_info in self._processes.items():
				if process_info["status"] == "running" and process_info["pid"]:
					status["active_pids"].append({
						"pid": process_info["pid"],
						"type": process_info["type"],
						"running_time": (datetime.now() - process_info["start_time"]).total_seconds()
					})
			
			# Log status if there are running processes
			if running_count > 0:
				logger.info(f"Process status check:")
				logger.info(f"- Running processes: {running_count}")
				logger.info(f"- Active scripts: {list(self._active_scripts.keys())}")
				logger.info(f"- Active PIDs: {[p['pid'] for p in status['active_pids']]}")
			
			return status

process_tracker = ProcessTracker()

# Thread-safe progress tracking
class ProgressTracker:
	def __init__(self):
		self._tasks: Dict[str, dict] = {}
		self._lock = threading.Lock()

	def flush_tasks(self) -> None:
		with self._lock:
			self._tasks = {}

	def create_task(self, task_id: str) -> None:
		with self._lock:
			self._tasks[task_id] = {
				'progress': 0,
				'status': 'running',
				'total_files': 0,
				'processed_files': 0,
				'data': {}
			}

	def update_progress(self, task_id: str, progress: float, 
						processed_files: int, total_files: int) -> bool:
		with self._lock:
			if task_id in self._tasks:
				self._tasks[task_id].update({
					'progress': progress,
					'processed_files': processed_files,
					'total_files': total_files
				})
				return True
			else:
				return False
   
	def complete_task(self, task_id: str, data={}) -> None:
		with self._lock:
			if task_id in self._tasks:
				self._tasks[task_id]['status'] = 'completed'
				self._tasks[task_id]['progress'] = 100
				self._tasks[task_id]['data'] = data
   
	def get_progress(self, task_id: str) -> dict:
		with self._lock:
			return self._tasks.get(task_id, {
				'status': 'not_found',
				'progress': 0,
				'processed_files': 0,
				'total_files': 0,
				'data': {}
			})

progress_tracker = ProgressTracker()

"""
App Route Functions Begin
"""
@app.route('/', methods=['POST','GET'])
def index():
	global settings
	global folder_status

	# Create Alert Structure for Alert Notification
	alert = { 
		'type' : '', 
		'text' : ''
		}

	# Flush the progress tracker
	progress_tracker.flush_tasks()

	return render_template('index.html', settings=settings, alert=alert)

@app.route('/settings', methods=['POST','GET'])
def settings_base(action=None):
	global settings
	global secrets

	# Create Alert Structure for Alert Notification
	alert = { 
		'type' : '', 
		'text' : ''
		}
	
	if(request.method == 'POST') and ('form' in request.content_type):
		# Update the system theme
		if('theme' in request.form):
			for theme in settings['globals']['themelist']:
				if theme['name'] == request.form['theme']:
					settings['globals']['theme'] = theme['filename']
					write_settings(settings)
					alert['type'] = 'success'
					alert['text'] = 'Theme updated to ' + theme['name'] + "."

		if('show_all_thumbnails' in request.form):
			settings['ui']['show_all_thumbnails'] = True
		else:
			settings['ui']['show_all_thumbnails'] = False

		if('auto_flag_processed' in request.form):
			settings['ui']['auto_flag_processed'] = True
		else:
			settings['ui']['auto_flag_processed'] = False

		if('immich_api_key' in request.form):
			secrets['api_key'] = request.form['immich_api_key']
			write_generic_yaml(secrets, 'config/secrets.yaml')

		if('immich_base_url' in request.form):
			secrets['base_url'] = request.form['immich_base_url']
			write_generic_yaml(secrets, 'config/secrets.yaml')

		write_settings(settings)
		alert['type'] = 'success'
		alert['text'] = f'UI Settings Updated.'

	return render_template('settings.html', settings=settings, alert=alert, secrets=secrets)

@app.route('/admin/<action>', methods=['POST','GET'])
@app.route('/admin', methods=['POST','GET'])
def admin(action=None):
	global settings
	global folder_status

	# Create Alert Structure for Alert Notification
	alert = { 
		'type' : '', 
		'text' : ''
		}

	if action == 'reset_folders':
		folder_status = read_folder_status(reset=True)	
		logger.info('Resetting folders.json')
		alert['type'] = 'success'
		alert['text'] = 'Folders reset.'

	uptime = os.popen('uptime').readline()

	cpuinfo = os.popen('cat /proc/cpuinfo').readlines()

	return render_template('admin.html', alert=alert, uptime=uptime, cpuinfo=cpuinfo, settings=settings)

@app.route('/admin/backup_folders', methods=['GET'])
def backup_folders():
	"""Download the current folders.json file as a backup"""
	try:
		folders_path = 'config/folders.json'
		
		if not os.path.exists(folders_path):
			logger.error(f"Backup failed: {folders_path} not found")
			abort(404)
		
		logger.info('Backing up folders.json')
		
		# Create a timestamped filename
		timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
		filename = f'folders_backup_{timestamp}.json'
		
		return send_file(
			folders_path,
			as_attachment=True,
			download_name=filename,
			mimetype='application/json'
		)
	except Exception as e:
		logger.error(f"Error during backup: {str(e)}")
		abort(500)

@app.route('/admin/restore_folders', methods=['POST'])
def restore_folders():
	"""Upload and restore a folders.json file"""
	try:
		# Check if file was uploaded
		if 'file' not in request.files:
			return jsonify({'success': False, 'message': 'No file provided'}), 400
		
		file = request.files['file']
		
		if file.filename == '' or file.filename is None:
			return jsonify({'success': False, 'message': 'No file selected'}), 400
		
		# Validate file type
		if not file.filename.endswith('.json'):
			return jsonify({'success': False, 'message': 'File must be a JSON file'}), 400
		
		# Read and validate JSON
		try:
			file_content = file.read().decode('utf-8')
			json.loads(file_content)  # Validate JSON format
		except json.JSONDecodeError:
			return jsonify({'success': False, 'message': 'Invalid JSON file format'}), 400
		except Exception as e:
			return jsonify({'success': False, 'message': f'Error reading file: {str(e)}'}), 400
		
		# Backup current folders.json before restoring
		folders_path = 'config/folders.json'
		if os.path.exists(folders_path):
			timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
			backup_path = f'{folders_path}.{timestamp}.restore_backup'
			try:
				shutil.copy2(folders_path, backup_path)
				logger.info(f'Current folders.json backed up to {backup_path}')
			except Exception as e:
				logger.warning(f'Could not backup current folders.json: {str(e)}')
		
		# Write the restored file
		try:
			with open(folders_path, 'w') as f:
				f.write(file_content)
			
			logger.info('Folders.json successfully restored from backup')
			
			# Reload the folder status
			global folder_status
			folder_status = read_folder_status(originals_path=settings['folders']['originals'])
			
			return jsonify({'success': True, 'message': 'Restore successful'}), 200
		except Exception as e:
			logger.error(f'Error writing folders.json: {str(e)}')
			return jsonify({'success': False, 'message': f'Error saving file: {str(e)}'}), 500
	
	except Exception as e:
		logger.error(f'Error during restore: {str(e)}')
		return jsonify({'success': False, 'message': f'Restore failed: {str(e)}'}), 500

@app.route('/manifest')
def manifest():
	res = make_response(render_template('manifest.json'), 200)
	res.headers["Content-Type"] = "text/cache-manifest"
	return res

@app.route('/selectfolder', methods=['POST', 'GET'])
def select_folder():
	global settings
	global folder_status 

	if(request.method == 'GET'):
		return render_template('selectfolder.html', settings=settings)

	if(request.method == 'POST') and ('form' in request.content_type):
		requestform = request.form
		#print(f'Request FORM: {requestform}')
		if('action' in requestform):
			if(requestform['action'] == 'init'):
				''' Initial Folder Selection'''
				folder_path = settings['folders']['originals']
				folder_data = get_folder_data(folder_path)
				return render_template('selectfolder.html', settings=settings, folder_data=folder_data, current_path=folder_path)
			if(requestform['action']) == 'refresh':
				''' Refresh Folder Selection from Originals Folder '''
				folder_path = settings['folders']['originals']
				try:
					# Update the folder status
					new_folder_data = {
						folder_path : scan_directory(path=folder_path)
						}
					folder_status = update_folder_status(new_folder_data, folder_status)
					write_folder_status(folder_status, path='config/folders.json')
					folder_data = get_folder_data(folder_path)
				except Exception as e:
					logger.error(f"Error updating folder status: {e}")
				return render_template('selectfolder.html', settings=settings, folder_data=folder_data, current_path=folder_path)
			if(requestform['action'] == 'open_folder'):
				''' Open Folder '''
				folder_path = requestform['current_path'] + '/' + requestform['folder_name']
				folder_data = get_folder_data(folder_path)
				return render_template('selectfolder.html', settings=settings, folder_data=folder_data, current_path=folder_path)
			if(requestform['action'] == 'back_folder'):
				''' Back to Parent Folder '''
				if requestform['current_path'] == '' or requestform['current_path'] == settings['folders']['originals']:
					folder_path = settings['folders']['originals']
				else:
					folder_path = requestform['current_path'].split('/')
					folder_path.pop()
					folder_path = '/'.join(folder_path)
				folder_data = get_folder_data(folder_path)
				return render_template('selectfolder.html', settings=settings, folder_data=folder_data, current_path=folder_path)
				
		return render_template('selectfolder.html', settings=settings)

	alert = { 
		'type' : 'error', 
		'text' : 'An error occurred. Please return to the home page and try again.'
		}
	
	return render_template('selectfolder.html', settings=settings, alert=alert)

@app.route('/importfolder', methods=['POST', 'GET'])
def import_folder():
	global settings
	global progress_tracker

	if(request.method == 'GET'):
		return render_template('importfolder.html', settings=settings)

	if(request.method == 'POST') and ('form' in request.content_type):
		requestform = request.form
		if('action' in requestform):
			action = requestform['action']

			''' Copy Task '''
			if(action == 'copy'):
				originals_path = requestform['import_folder']
				import_folder = settings['folders']['import']
				# First delete all files and folders in the import folder
				os.system(f"rm -rf {import_folder}/*")
				# Copy file and folder structure from originals to import
				task_id = get_unique_id()
				progress_tracker.create_task(task_id)
				copy_thread = threading.Thread(target=copy_folder_structure, args=(originals_path, import_folder, task_id))
				copy_thread.start()
				progress_data = progress_tracker.get_progress(task_id)
				return render_template('importfolder.html', settings=settings, action=action, percent_complete=int(progress_data['progress']), task_id=task_id, originals_path=originals_path, import_folder=import_folder)
			if(action == 'copy_progress'):
				task_id = requestform['task_id']
				progress = progress_tracker.get_progress(task_id)
				return jsonify(progress)
			
			''' Range Selection '''
			if(action == 'range'):
				originals_path = requestform['import_folder']
				import_folder = settings['folders']['import']
				#print(f'\n ** Range Page Got Originals Path: {originals_path} ** \n')
				return render_template('importfolder.html', settings=settings, action=action, originals_path=originals_path, import_folder=import_folder)

			''' Analyze Task '''
			if(action == 'analyze'):
				originals_path = requestform['import_folder']
				import_folder = settings['folders']['import']
				# Analyze the import folder
				start_date = requestform.get('start_date', None)
				end_date = requestform.get('end_date', None)
				if start_date in ['', None]:
					start_date = None 
				else:
					start_date = fixup_date_time(start_date)
				if end_date in ['', None]:
					end_date = None 
				else:
					end_date = fixup_date_time(end_date)
				#print(f'start_date = {start_date}\nend_date = {end_date}')
				task_id = get_unique_id()
				progress_tracker.create_task(task_id)
				analyze_thread = threading.Thread(target=analyze_import_folder, args=(settings['folders']['import'], task_id, originals_path, start_date, end_date))
				analyze_thread.start()
				progress_data = progress_tracker.get_progress(task_id)
				#print(f'originals_path: {originals_path}') # DEBUG
				#print(f'settings[folders][import]: {settings["folders"]["import"]}') # DEBUG
				return render_template('importfolder.html', settings=settings, action=action, percent_complete=int(progress_data['progress']), task_id=task_id, originals_path=originals_path, import_folder=import_folder)
			if(action == 'analyze_progress'):
				task_id = requestform['task_id']
				progress = progress_tracker.get_progress(task_id)
				return jsonify(progress)
			
			if(action == 'cancel'):
				return redirect('/')
		return render_template('importfolder.html', settings=settings)

	alert = { 
		'type' : 'error', 
		'text' : 'An error occurred. Please return to the home page and try again.'
		}
	
	return render_template('importfolder.html', settings=settings, alert=alert)

@app.route('/fixfiles', methods=['POST', 'GET'])
def fix_files():
	global settings
	global progress_tracker

	if(request.method == 'GET'):
		return render_template('fixfiles.html', settings=settings)

	if(request.method == 'POST') and ('form' in request.content_type):
		requestform = request.form
		if('action' in requestform):
			action = requestform['action']
			if(action == 'results'):
				task_id = requestform['task_id']
				#print(f'Task ID: {task_id}')
				progress = progress_tracker.get_progress(task_id)
				import_data = progress['data']
				#print(f'Import Data: {import_data}')
				return render_template('fixfiles.html', settings=settings, action=action, task_id=task_id, import_data=import_data)

	alert = { 
		'type' : 'error', 
		'text' : 'An error occurred. Please return to the home page and try again.'
		}

	return render_template('fixfiles.html', settings=settings, alert=alert)

@app.route('/finish', methods=['POST', 'GET'])
def finish_process():
	global settings
	global progress_tracker

	if(request.method == 'GET'):
		return render_template('finish.html', settings=settings)

	if(request.method == 'POST') and ('form' in request.content_type):
		requestform = request.form
		if('action' in requestform):
			action = requestform['action']
			if(action == 'process'):
				previous_task_id = requestform['task_id']
				import_data = progress_tracker.get_progress(previous_task_id)['data']
				#print(f'\n ** Import Data Original_Path: {import_data['original_path']} ** \n')
				# convert task_list json string to dictionary
				task_list = json.loads(requestform['radio_values'])
				task_id = get_unique_id()
				"""
				print(f'task_id: {task_id}\n')
				for key, value in task_list.items():
					print(f'key: {key} value: {value}')
				"""
				progress_tracker.create_task(task_id)
				# Process the import data
				process_thread = threading.Thread(target=process_files, args=(task_id, task_list, import_data))
				process_thread.start()
				progress_data = progress_tracker.get_progress(task_id)
				return render_template('finish.html', settings=settings, action=action, task_id=task_id)
			if(action == 'process_progress'):
				task_id = requestform['task_id']
				progress = progress_tracker.get_progress(task_id)
				return jsonify(progress)
			if(action == 'results'):
				task_id = requestform['task_id']
				#print(f'Files Processed Successfully! \nTask ID: {task_id}')
				progress = progress_tracker.get_progress(task_id)
				results = progress['data']
				return render_template('finish.html', settings=settings, action=action, task_id=task_id, results=results)

	alert = { 
		'type' : 'error', 
		'text' : 'An error occurred. Please return to the home page and try again.'
		}

	return render_template('finish.html', settings=settings, alert=alert)

@app.route('/preproc', methods=['POST', 'GET'])
def pre_process():
	global settings

	import_folder = settings['folders']['import']

	folder_path = 'originals'

	if(request.method == 'POST') and ('form' in request.content_type):
		requestform = request.form
		if('folder_path' in requestform):
			folder_path = requestform['folder_path']

	return render_template('pre_proc.html', settings=settings, folder_path=folder_path, import_folder=import_folder)

@app.route('/postproc', methods=['POST', 'GET'])
def post_process():
	global settings

	return render_template('post_proc.html', settings=settings)

def start_script(action, path='originals'):
	"""Start a script process that runs independently and writes to a log file"""
	global settings
	global process_tracker

	# Check if there are any running processes before starting a new one
	if process_tracker.has_running_processes(script_type=action):
		raise ProcessRunningError(f"A {action} script is already running. Please wait for it to complete.")
	
	logger.info(f"====== Starting new {action} script execution ======")
	
	# Create log file for this process - use a temporary UUID for the log filename
	log_id = str(uuid.uuid4())
	log_file = os.path.join('logs/process_logs', f'{action}_{log_id}.log')
	
	if action == 'preprocess':
		command = settings['scripts']['pre_proc']['type']
		script_path = os.path.join(settings['scripts']['pre_proc']['path'], settings['scripts']['pre_proc']['script'])
		arguments = path
		logger.info(f"Command: {command} {script_path} {arguments}")
		# Try to use stdbuf to disable output buffering, but make it work without it too
		if shutil.which('stdbuf'):
			cmd_list = ['stdbuf', '-oL', '-eL', command, script_path, arguments] if arguments else ['stdbuf', '-oL', '-eL', command, script_path]
		else:
			# Fallback without stdbuf (e.g., in minimal Docker containers)
			cmd_list = [command, script_path, arguments] if arguments else [command, script_path]
	else:
		command = settings['scripts']['post_proc']['type']
		script_path = os.path.join(settings['scripts']['post_proc']['path'], settings['scripts']['post_proc']['script']) 
		logger.info(f"Command: {command} {script_path}")
		# Try to use stdbuf to disable output buffering, but make it work without it too
		if shutil.which('stdbuf'):
			cmd_list = ['stdbuf', '-oL', '-eL', command, script_path]
		else:
			# Fallback without stdbuf (e.g., in minimal Docker containers)
			cmd_list = [command, script_path]

	try:
		# Open log file for writing with unbuffered mode
		log_handle = open(log_file, 'w', buffering=1)  # Line buffering
		
		# Start process with output redirected to log file
		# Set PYTHONUNBUFFERED for Python scripts and ensure bash scripts output immediately
		env = os.environ.copy()
		env['PYTHONUNBUFFERED'] = '1'
		
		process = subprocess.Popen(
			cmd_list,
			stdout=log_handle,
			stderr=subprocess.STDOUT,
			universal_newlines=True,
			bufsize=1,  # Line buffering
			env=env,
			start_new_session=True  # Runs in its own session, won't be killed if parent dies
		)
		
		# Track this process with its log file and capture the returned process_id
		process_id = process_tracker.add_process(process, script_type=action, log_file=log_file)
		logger.info(f"Started {action} process with PID: {process.pid}, ID: {process_id}, Log: {log_file}")
		
		# Start background thread to monitor process completion
		def monitor_process():
			logger.info(f"Monitor thread started for process {process.pid}")
			try:
				return_code = process.wait()  # Wait for process to complete
				logger.info(f"Process {process.pid} completed with return code {return_code}")
			except Exception as e:
				logger.error(f"Error in monitor_process: {e}")
			finally:
				# Close log file handle
				try:
					log_handle.close()
				except:
					pass
				logger.info(f"====== Script execution completed for PID {process.pid} ======")
		
		monitor_thread = threading.Thread(target=monitor_process)
		monitor_thread.daemon = True
		monitor_thread.start()
		
		return process_id
		
	except Exception as e:
		logger.error(f"Error starting script: {e}")
		# Clean up log file if it was created
		try:
			if 'log_handle' in locals():
				log_handle.close()
			if os.path.exists(log_file):
				os.remove(log_file)
		except:
			pass
		raise

@app.route('/start_process')
@app.route('/start_process/<action>')
def start_process_endpoint(action=None):
	"""Start a background process and return its ID for polling"""
	global process_tracker
	
	# Determine which action to use
	script_action = action if action else "postprocess"
	logger.info(f"=== START_PROCESS ENDPOINT CALLED ===")
	logger.info(f"Action: {script_action}")
	
	# Check if the specific script type is already running
	is_running = process_tracker.has_running_processes(script_type=script_action)
	logger.info(f"Script type '{script_action}' already running: {is_running}")
	
	if is_running:
		logger.warning(f"Attempted to start {script_action} but one is already running")
		return jsonify({
			'error': True,
			'message': f'A {script_action} script is currently running. Please wait for it to complete.'
		}), 409  # HTTP 409 Conflict
	
	path = request.args.get('script_arg', 'originals')
	logger.info(f"Script argument (path): {path}")
	
	try:
		logger.info(f"Starting {script_action} script with path: {path}")
		process_id = start_script(script_action, path=path)
		logger.info(f"Successfully started {script_action} with process ID: {process_id}")
		return jsonify({
			'success': True,
			'process_id': process_id,
			'message': f'{script_action} process started successfully'
		})
	except ProcessRunningError as e:
		logger.warning(f"ProcessRunningError: {e}")
		return jsonify({
			'error': True,
			'message': str(e)
		}), 409
	except Exception as e:
		logger.error(f"Error starting process: {e}", exc_info=True)
		return jsonify({
			'error': True,
			'message': f'Failed to start process: {str(e)}'
		}), 500

@app.route('/process_status/<process_id>')
def get_process_status(process_id):
	"""Get the status and recent output of a specific process"""
	global process_tracker
	
	process_info = process_tracker.get_process_info(process_id)
	
	if not process_info:
		return jsonify({
			'error': True,
			'message': 'Process not found'
		}), 404
	
	# Get recent output from log file (all lines for incremental display)
	log_content = []
	if process_info.get('log_file') and os.path.exists(process_info['log_file']):
		try:
			with open(process_info['log_file'], 'r') as f:
				log_content = f.readlines()  # Read all lines for incremental frontend display
		except Exception as e:
			logger.error(f"Error reading log file: {e}")
	
	return jsonify({
		'success': True,
		'status': process_info['status'],
		'type': process_info['type'],
		'return_code': process_info['return_code'],
		'start_time': process_info['start_time'].isoformat(),
		'log_content': log_content,
		'log_file': process_info['log_file']
	})

@app.route('/active_process/<script_type>')
def get_active_process(script_type):
	"""Get the active process info for a given script type"""
	global process_tracker
	
	process_id = process_tracker.get_active_process_id(script_type)
	if not process_id:
		return jsonify({
			'success': True,
			'process_id': None,
			'process_info': None
		})

	process_info = process_tracker.get_process_info(process_id)
	return jsonify({
		'success': True,
		'process_id': process_id,
		'process_info': process_info
	})

@app.route('/check_running_processes')
def check_running_processes():
	global process_tracker
	
	# Get detailed status from the process tracker
	status = process_tracker.get_status()
	
	# Create response data
	response_data = {
		'has_running_processes': status["running_processes"] > 0,
		'preprocess_running': status["preprocess_running"],
		'postprocess_running': status["postprocess_running"],
		'timestamp': status["timestamp"],
		'process_count': status["running_processes"],
		'active_pids': [p["pid"] for p in status["active_pids"]]
	}
	
	# Detailed logging only when processes are running
	if status["running_processes"] > 0:
		logger.info(f"Process status check at {response_data['timestamp']}")
		logger.info(f"Total tracked processes: {response_data['process_count']}")
		logger.info(f"Running processes: {response_data['has_running_processes']}")
		logger.info(f"Pre-process running: {response_data['preprocess_running']}")
		logger.info(f"Post-process running: {response_data['postprocess_running']}")
		logger.info("---") # Separator for readability
	
	return jsonify(response_data)

@app.route('/test_process_tracker')
def test_process_tracker():
	"""Test endpoint to verify process tracking"""
	global process_tracker
	
	# Specify a script type for testing
	script_type = request.args.get('type', 'test')
	
	# Start a long-running process (sleep for 30 seconds)
	process = subprocess.Popen(
		['sleep', '30'],
		stdout=subprocess.PIPE,
		stderr=subprocess.STDOUT,
		universal_newlines=True
	)
	
	process_id = process_tracker.add_process(process, script_type=script_type)
	logger.info(f"Started test process with PID: {process.pid}, ID: {process_id}")
	
	return jsonify({
		'message': f'Test {script_type} process started',
		'pid': process.pid,
		'process_id': process_id
	})

@app.route('/toggle_processed', methods=['POST'])
def toggle_processed():
	global settings
	global folder_status

	if request.method == 'POST':
		try:
			data = request.get_json()  # Get the JSON data from the request body
			path = data.get('path', '')
			flag = data.get('flag', False)
			#print(f'Path: {path}, Flag: {flag}')
			if path != '':
				# loop through folder status to find the path that matches and set/clear ['processed'] flag
				success = set_processed(path, flag)
				return jsonify({'success': success})  # Return JSON response with a dictionary.

		except Exception as e:
			logger.error(f"Error processing request: {e}")
			return jsonify({'success': False, 'error': str(e)}), 500 # return 500 error if failed

	return jsonify({'success': False, 'error': 'Invalid request method'}), 400 # return 400 error if not a POST



"""
Supporting Functions
"""

def set_processed(path, flag, recursive=False):
	"""
	Walk through the nested folder structure to find the specified path
	and update its 'processed' flag.

	Parameters:
	path (str): The path to find and update
	flag (bool): The value to set for the 'processed' flag

	Returns:
	bool: True if the path was found and updated, False otherwise
	"""
	global folder_status

	def update_processed(sub_dict, flag):
		for sub_dir, data in sub_dict.items():
			if data['subfolders'] != {}:
				update_processed(data['subfolders'], flag)
			else:
				data['processed'] = flag

	def search_and_update(current_dict):
		"""Recursive helper function to search through the nested structure"""
		for key, value in current_dict.items():
			if isinstance(value, dict):
				# Check if this is a folder entry with a matching path
				if 'path' in value and value['path'] == path:
					value['processed'] = flag
					if recursive and value['subfolders'] != {}:
						update_processed(value['subfolders'], flag)
					return True
				
				# If it has subfolders, search those
				if 'subfolders' in value:
					if search_and_update(value['subfolders']):
						return True
				
				# Check other dictionary entries
				if search_and_update(value):
					return True
		
		return False

	success = search_and_update(folder_status)
	write_folder_status(folder_status)

	return success

def get_folder_data(path='originals'):
	global folder_status
	global settings 

	''' 
	 Walk the folder_status dictionary to map the path, then return the following structure:
	 folder_details = [folder_dict of each subfolder in the path]
	 folder_dict = {
		'name' : folder,
		'num_folders' : number of subfolders in this folder,
		'num_files' : number of files in this folder,
		'processed' : True/False/None (None indicates partially processed)
	 }
	'''
	def check_processed_status(folder_data):
		"""Recursively check the processed status of a folder and all its subfolders"""
		if not folder_data['subfolders']:
			return folder_data['processed'], folder_data['processed']

		all_processed = folder_data['processed']
		has_processed = folder_data['processed']
		has_unprocessed = not folder_data['processed']

		for _, sub_data in folder_data['subfolders'].items():
			sub_all_processed, sub_has_processed = check_processed_status(sub_data)
			all_processed = all_processed and sub_all_processed
			has_processed = has_processed or sub_has_processed
			has_unprocessed = has_unprocessed or not sub_all_processed

		return all_processed, has_processed

	#print(f'path: {path}') # DEBUG
	folder_details = []
	try:
		original_path = path.replace('./', '')

		path_list = original_path.split('/')

		path_depth = len(path_list)

		#print(f'path_depth: {path_depth}') # DEBUG
		#print(f'path_list: {path_list}') # DEBUG

		subfolder_target = folder_status.copy()
		
		''' Traverse the folder_status dictionary to find the path, get details of the subfolders in the path, 
			and return a list of dictionaries with the details of each subfolder. '''
		# If path_depth is 1, then we are at the top level of the folder_status dictionary
		if path_depth == 1:
			subfolder_target = subfolder_target[path_list[0]]['subfolders']
		else:
			for index in range(0, path_depth):
				#print(f'Path_list[{index}]: {path_list[index]} Subfolder_target: {subfolder_target[path_list[index]]['path']}') # DEBUG
				subfolder_target = subfolder_target[path_list[index]]['subfolders']

		for subfolder, data in subfolder_target.items():
			# Check the processed status recursively through all subfolders
			all_processed, has_processed = check_processed_status(data)
			
			if all_processed:
				processed_status = True
			elif has_processed:
				processed_status = None  # Partially processed
			else:
				processed_status = False

			folder_dict = {
				'name' : subfolder,
				'num_folders' : data['num_subfolders'],
				'num_files' : data['num_files'],
				'processed' : processed_status
			}
			folder_details.append(folder_dict)

		return folder_details
			
	except KeyError as e:
		logger.error(f"KeyError: {e}")
	except Exception as e:
		logger.error(f"An unexpected error occurred: {e}")

	return []

def copy_folder_structure(originals_path, import_folder, task_id):
	""" Copy folder structure and all files from originals folder to the import folder and provide progress updates while copying. """
	try:
		#print(f'\n ** Copying folder structure and files from {originals_path} to {import_folder}. ** \n')
		total_files = sum([len(files) for _, _, files in os.walk(originals_path)])
		processed_files = 0
		for root, dirs, files in os.walk(originals_path):
			for file in files:
				file_path = os.path.join(root, file)
				relative_path = os.path.relpath(file_path, originals_path)
				import_path = os.path.join(import_folder, relative_path)
				#print(f"[DEBUG] cp '{file_path}' '{import_path}'") # DEBUG
				os.makedirs(os.path.dirname(import_path), exist_ok=True)
				os.system(f"cp -p '{file_path}' '{import_path}'")
				processed_files += 1
				progress = (processed_files / total_files) * 100
				status = progress_tracker.update_progress(task_id, progress, processed_files, total_files)
				if not status:
					return
		data = {'alert': {'type': 'success', 'text': 'Folder structure and files copied successfully.'}, 'original_path': originals_path}
		progress_tracker.complete_task(task_id, data=data)
	except Exception as e:
		data = {'alert': {'type': 'danger', 'text': f'Error copying folder structure and files: {e}'}, 'original_path': originals_path}
		progress_tracker.complete_task(task_id, data=data)
		logger.error(f"Error copying folder structure and files: {e}")

def analyze_import_folder(import_folder, task_id, originals_path, start_date, end_date):
	""" Recusively analyze files and folders in the import folder. Create and return a dictionary of three dictionaries: files_with_dates (image files with exif date), files_without_dates (image files without exif date), and ignored_files (all other files). Each entry into these dictionaries should have the path, filename, date (if exif data exists). """
	#print(f'\n ** Analyzing import folder: {import_folder} from originals folder: {originals_path} ** \n')
	files_with_dates = []
	files_without_dates = []
	ignored_files = []
	total_files = sum([len(files) for _, _, files in os.walk(import_folder)])
	processed_files = 0
	for root, dirs, files in os.walk(import_folder):
		for file in files:
			file_path = os.path.join(root, file)
			if is_valid_image(file_path):
				exif_data = get_exif_data(file_path)
				date = get_exif_date(exif_data)
				file_date = get_file_date(file_path)
				#print(f'file_root: {root}, file: {file}, date: {date}, file_date: {file_date}')
				image_link = root.replace('./static/', '').replace('./', '') + '/' + file 
				#print(f'image_link: {image_link}')
				if date:
					guessed_dates = guess_date(file, file_date, file_path, start_date, end_date)
					files_with_dates.append({'path': root, 'filename': file, 'date': date, 'file_date': file_date, 'image_link': image_link, 'guessed_dates': guessed_dates, 'start_date': start_date, 'end_date': end_date})
				else:
					guessed_dates = guess_date(file, file_date, file_path, start_date, end_date)
					files_without_dates.append({'path': root, 'filename': file, 'file_date': file_date, 'image_link': image_link, 'guessed_dates': guessed_dates, 'start_date': start_date, 'end_date': end_date})
			else:
				ignored_files.append({'path': root, 'filename': file})
			processed_files += 1
			progress = (processed_files / total_files) * 100
			status = progress_tracker.update_progress(task_id, progress, processed_files, total_files)
			if not status:
				return
	import_data = {'files_with_dates': files_with_dates, 'files_without_dates': files_without_dates, 'ignored_files': ignored_files, 'original_path': originals_path}
	progress_tracker.complete_task(task_id, data=import_data)
	#print(import_data) # DEBUG

def process_files(task_id, task_list, import_data):
	""" Process the files based on the task list. """
	originals_path = import_data.get('original_path', 'NOT FOUND')
	#print(f'originals_path: {originals_path}')
	
	processed_tasks = 0
	report = []
	# Get total tasks to process
	total_tasks = len(list(task_list.keys()))
	# Get total files to copy
	total_files = len(import_data['files_with_dates']) + len(import_data['files_without_dates']) + len(import_data['ignored_files'])
	# Get total items to process
	total_items = total_files + total_tasks

	# Get the current date and time
	now = datetime.now()

	# Define the format for the date and time string
	date_time_format = "%Y-%m-%d %H:%M:%S"

	# Generate the date and time string
	date_time_str = now.strftime(date_time_format)

	report.append(f'Process Images Report [{date_time_str}]')
	report.append(f'Number of tasks: {total_tasks}')
	report.append(f'Number of files scanned: {total_files}')
	report.append(f'Number of items total: {total_items}')

	# Process the files in place
	results = {
		'files_ignored' : [],
		'files_deleted' : [],
		'files_edited' : [],
		'files_copied' : [],
		'errors' : []
	}
	delete_files = []
	for file, task in task_list.items():
		#print(f'task = {task}')
		filename = file.replace('choices_fileid_', '')
		# if task value is 'ignore', skip the task
		if task == 'ignore':
			results['files_ignored'].append(f'{filename.replace(IMPORT_FOLDER, '')}')
		elif task == 'delete':
			delete_files.append(filename)
		elif is_valid_date(task):
			new_date = fixup_date_time(task)
			if write_date_to_exif(filename, new_date):
				results['files_edited'].append(f'{filename.replace(IMPORT_FOLDER, '')} was processed with date {new_date}.')
			else:
				results['errors'].append(f'{filename.replace(IMPORT_FOLDER, '')} had an error when processing with {new_date}.')
		else:
			results['errors'].append(f'{filename.replace(IMPORT_FOLDER, '')} was not processed.')
		processed_tasks += 1
		progress = int((processed_tasks / total_items) * 100)
		status = progress_tracker.update_progress(task_id, progress, processed_tasks, total_tasks)
		if not status:
			return
	# Copy the files to export folder
	export_folder = f"{settings['folders']['export']}/"
	# Delete files in export folder before copying files
	try:
		os.system(f"rm -rf {export_folder}*")
	except Exception as e:
		#print(f'Oh dang it! There was an error deleting files in the export folder: {e}')
		logger.error(f'Error deleting files in the export folder: {e}')

	for group in ['files_with_dates', 'files_without_dates', 'ignored_files']:
		for file in import_data[group]:
			file_path = os.path.join(file['path'], file['filename'])
			if file_path in delete_files:
				try:
					os.remove(file_path)
					results['files_deleted'].append(f'{file_path.replace(IMPORT_FOLDER, '')} was deleted.')
				except Exception as e:
					results['errors'].append(f'Error deleting {file_path.replace(IMPORT_FOLDER, '')}: {e}')
					logger.error(f'Error deleting {file_path.replace(IMPORT_FOLDER, '')}: {e}')
			else:
				try:
					os.makedirs(export_folder + file['path'].replace(IMPORT_FOLDER, ''), exist_ok=True)
					os.system(f"cp -p '{file_path}' '{export_folder}{file['path'].replace(IMPORT_FOLDER, '')}'")
					os.system(f"rm '{file_path}'")
					results['files_copied'].append(f'{file_path.replace(IMPORT_FOLDER, '')} was copied to export folder.')
				except Exception as e:
					results['errors'].append(f'Error moving {file_path.replace(IMPORT_FOLDER, '')} to export folder: {e}')
					logger.error(f'Error moving {file_path.replace(IMPORT_FOLDER, '')} to export folder: {e}')
			processed_tasks += 1
			progress = int((processed_tasks / total_items) * 100)
			status = progress_tracker.update_progress(task_id, progress, processed_tasks, total_items)
			if not status:
				return

	progress_tracker.complete_task(task_id, data=results)

	# Generate report
	report.append('')
	report.append('======')
	report.append('Errors')
	report.append('======')
	for line in results['errors']:
		report.append(f' - {line}')

	report.append('')
	report.append('============')
	report.append('Files Edited')
	report.append('============')
	for line in results['files_edited']:
		report.append(f' - {line}')

	report.append('')
	report.append('=============')
	report.append('Files Deleted')
	report.append('=============')
	for line in results['files_deleted']:
		report.append(f' - {line}')

	report.append('')
	report.append('=============')
	report.append('Files Ignored')
	report.append('=============')
	for line in results['files_ignored']:
		report.append(f' - {line}')

	report.append('')
	report.append('============')
	report.append('Files Copied')
	report.append('============')
	for line in results['files_copied']:
		report.append(f' - {line}')

	report.append('')
	report.append('=============')
	report.append('End of Report')
	report.append('=============')

	report_filename = f'logs/report_{date_time_str}.log'

	with open(report_filename, 'w') as file:
		file.writelines(line + '\n' for line in report)

	if settings['ui']['auto_flag_processed']:
		set_processed(import_data['original_path'], True, recursive=True)

def get_file_date(file_path):
	""" Get the date of the file. """
	try:
		file_stats = os.stat(file_path)
		file_date = file_stats.st_mtime
		# convert file_date to a human-readable format
		file_date = datetime.fromtimestamp(file_date, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
		return file_date
	except Exception as e:
		#print(f"Error getting file date: {e}")
		logger.error(f"Error getting file date: {e}")
		return None

def guess_date(filename, file_date, file_path, start_date, end_date):
	""" Using the filename, file_date (should already be a date, simply append to the list), and file_path, attempt to guess the date and time of the image and return a list of possible dates. """
	guessed_dates = {
		'filename' : None,
		'pathname' : None,
		'filedate' : None
	}
	# start_date and end_date are already in string format and fixed up
	# Get the date from the filename
	filename_date = get_date_from_filename(filename)
	if filename_date:
		#print(f'filename_date: {filename_date}')
		fixed_date = fixup_date_time(filename_date)
		#print(f'fixed_data: {fixed_date}')
		if date_in_range(start_date, end_date, fixed_date):
			guessed_dates['filename'] = fixed_date
	# Get the date from the file path
	path_date = get_date_from_path(file_path)
	if path_date:
		#print(f'path_date: {path_date}')
		fixed_date = fixup_date_time(path_date)
		if date_in_range(start_date, end_date, fixed_date):
			guessed_dates['pathname'] = fixed_date
	# Get the date from the file date
	if file_date:
		if date_in_range(start_date, end_date, file_date):
			guessed_dates['filedate'] = file_date
	return guessed_dates

def get_date_from_filename(filename):
	""" Get the date from the filename. 
	# Check for several different date patterns in the filename including YYYY-MM-DD, YYYYMMDD, YYYY_MM_DD, MM-DD-YYYY, MM_DD_YYYY, YYYY-MM, YYYY_MM where year would be 1900-2099
	"""
	search_patterns = [r'\d{4}-\d{2}-\d{2}', r'\d{4}_\d{2}_\d{2}', r'\d{2}-\d{2}-\d{4}', r'\d{2}_\d{2}_\d{4}', r'\d{4}-\d{2}', r'\d{4}_\d{2}', r'\d{8}']
	for pattern in search_patterns:
		date = re.search(pattern, filename)
		if date:
			# Check if the date is a valid date
			if is_valid_date(date.group()):
				return date.group()
	return None

def get_date_from_path(file_path):
	""" Get the date from the file_path string. 
	# Check for several different date patterns in the file_path string including YYYY-MM-DD, YYYY_MM_DD, YYYY/MM/DD, YYYY/MM, MM-DD-YYYY, MM_DD_YYYY, YYYY-MM, YYYY_MM, YYYYMMDD where year would be 1900-2099
	"""
	search_patterns = [r'\d{4}-\d{2}-\d{2}', r'\d{4}_\d{2}_\d{2}', r'\d{4}/\d{2}/\d{2}', r'\d{4}/\d{2}', r'\d{2}-\d{2}-\d{4}', r'\d{2}_\d{2}_\d{4}', r'\d{4}-\d{2}', r'\d{4}_\d{2}', r'\d{8}']
	for pattern in search_patterns:
		date = re.search(pattern, file_path)
		if date:
			# Check if the date is a valid date
			if is_valid_date(date.group()):
				return date.group()
	return None

def is_valid_date(date):
	""" The variable date is a string that could be in various formats (is not a datetime format), check to see if it looks like a valid date based knowing the year should be between 1900-2099."""
	year = re.search(r'\d{4}', date)
	if year:
		year = int(year.group())
		if year >= 1900 and year <= 2099:
			return True
	return False

def fixup_date_time(date_time):
	""" 
		Fixup date input to be in the format. 
		Input: Possible input formats are YYYY-MM-DD, YYYY_MM_DD, YYYY/MM/DD, YYYY/MM, MM-DD-YYYY, MM_DD_YYYY, YYYY-MM, YYYY_MM, YYYYMMDD and may or may not contain the time. 
		Output: string in the format YYYY-MM-DD HH:MM:SS (where HH:MM:SS is 00:00:00 if not present).
	"""
	# Check if input contains full date matching one of these patterns YYYY-MM-DD, YYYY_MM_DD, YYYY/MM/DD, MM-DD-YYYY, MM_DD_YYYY, YYYYMMDD and format to YYYY-MM-DD
	search_patterns = [r'\d{4}-\d{2}-\d{2}', r'\d{4}_\d{2}_\d{2}', r'\d{4}/\d{2}/\d{2}', r'\d{2}-\d{2}-\d{4}', r'\d{2}_\d{2}_\d{4}', r'\d{8}']
	patterns = ['YYYY-MM-DD', 'YYYY_MM_DD', 'YYYY/MM/DD', 'MM-DD-YYYY', 'MM_DD_YYYY', 'YYYYMMDD']
	for index, pattern in enumerate(search_patterns):
		date_match = re.search(pattern, date_time)
		if date_match:
			date = date_match.group()
			# Convert date to YYYY-MM-DD
			date = convert_date(date, patterns[index])
			break
	if not date_match:
		patterns = ['YYYY-MM', 'YYYY_MM']
		search_patterns	= [r'\d{4}-\d{2}', r'\d{4}_\d{2}']
		for index, pattern in enumerate(search_patterns):
			date_match = re.search(pattern, date_time)
			if date_match:
				date = date_match.group()
				# Convert date to YYYY-MM-DD
				date = convert_date(date, patterns[index])
				break
	
	if not date_match:
		return '0000-00-00 00:00:00'

	# Check if input contains time and format to HH:MM:SS
	time_match = re.search(r'\d{2}:\d{2}:\d{2}', date_time)
	if time_match:
		time = time_match.group()
	else:
		time = '00:00:00'

	return f'{date} {time}'

def convert_date(date, pattern):
	""" Convert date to YYYY-MM-DD format. """
	if pattern == 'YYYY-MM-DD':
		return date
	if pattern == 'YYYY_MM_DD':
		return date.replace('_', '-')
	if pattern == 'YYYY/MM/DD':
		return date.replace('/', '-')
	if pattern == 'MM-DD-YYYY':
		return '-'.join(date.split('-')[::-1])
	if pattern == 'MM_DD_YYYY':
		return '-'.join(date.split('_')[::-1])
	if pattern == 'YYYYMMDD':
		return f'{date[0:4]}-{date[4:6]}-{date[6:8]}'
	if pattern == 'YYYY-MM':
		return date + '-01'
	if pattern == 'YYYY_MM':
		return date.replace('_', '-') + '-01'
	
	return '1900-01-01'

def date_is_after(date_string1, date_string2):
	"""
	Compare two date strings and return True if the first date is after the second date.

	Args:
	date_string1 (str): The first date string.
	date_string2 (str): The second date string.

	Returns:
	bool: True if the first date is after the second date, False otherwise.
	"""
	date_format = "%Y-%m-%d %H:%M:%S"

	# Convert date strings to datetime objects
	date1 = datetime.strptime(date_string1, date_format)
	date2 = datetime.strptime(date_string2, date_format)

	# Compare the dates
	return date1 >= date2

def date_is_before(date_string1, date_string2):
	"""
	Compare two date strings and return True if the first date is before the second date.

	Args:
	date_string1 (str): The first date string.
	date_string2 (str): The second date string.

	Returns:
	bool: True if the first date is after the second date, False otherwise.
	"""
	date_format = "%Y-%m-%d %H:%M:%S"

	# Convert date strings to datetime objects
	date1 = datetime.strptime(date_string1, date_format)
	date2 = datetime.strptime(date_string2, date_format)

	# Compare the dates
	return date1 <= date2

def date_in_range(start_date, end_date, test_date):
	if start_date == None and end_date == None:
		return True 
	
	if start_date or end_date:
		if start_date and end_date and date_is_after(test_date, start_date) and end_date and date_is_before(test_date, end_date):
			return True
		elif start_date and date_is_after(test_date, start_date):
			return True
		elif end_date and date_is_before(test_date, end_date):
			return True 

	return False

def get_unique_id():
	""" Generate a unique ID for a task. """
	return str(uuid.uuid4())

@app.route('/logs')
@app.route('/logs/<filename>')
def logs(filename=None):
	"""View log files in the logs directory"""
	# Get list of all .log files in the logs directory
	log_files = []
	for file in os.listdir('logs'):
		if file.endswith('.log'):
			log_files.append(file)
	
	# Sort log files with app.log first, then by name
	log_files.sort(key=lambda x: (x != 'app.log', x))
	
	# If no filename specified, use app.log or the first log file found
	if not filename:
		filename = 'app.log' if 'app.log' in log_files else (log_files[0] if log_files else None)
	
	# Read the selected log file
	log_content = ''
	if filename and filename in log_files:
		try:
			with open(os.path.join('logs', filename), 'r') as f:
				log_content = f.read()
		except Exception as e:
			logger.error(f"Error reading log file {filename}: {e}")
			log_content = f"Error reading log file: {str(e)}"
	
	return render_template('logs.html', 
						 settings=settings,
						 log_files=log_files,
						 current_log=filename,
						 log_content=log_content)

"""
Run Flask App
"""
logger = create_logger('app', filename='logs/app.log', level=settings['globals']['log_level'])

logger.info('Application Started.')

secrets = read_generic_yaml('config/secrets.yaml')
if secrets == {}:
	logger.info('New config/secrets.yaml file created.')
	secrets = {
		'base_url': 'http://127.0.0.1:2283/api',
		'api_key': ''
	}
	write_generic_yaml(secrets, 'config/secrets.yaml')

if __name__ == '__main__':
	if settings['globals']['debug'] == False:
		app.run(host='0.0.0.0')
	else:
		app.run(host='0.0.0.0', debug=True)
