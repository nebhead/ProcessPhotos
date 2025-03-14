#!/usr/bin/python3

import requests
import os
import argparse
import yaml
import time
from datetime import datetime
from pathlib import Path

def load_config(config_path='secrets.yaml'):
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        required_keys = ['api_key', 'base_url']
        missing_keys = [key for key in required_keys if key not in config]
        
        if missing_keys:
            raise ValueError(f"Missing required configuration keys: {', '.join(missing_keys)}")
            
        return config
    except FileNotFoundError:
        print(f"Error: Configuration file '{config_path}' not found.")
        print("Please create a secrets.yaml file with 'api_key' and 'base_url' fields.")
        exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML configuration: {str(e)}")
        exit(1)
    except Exception as e:
        print(f"Error loading configuration: {str(e)}")
        exit(1)

def get_file_list(path, recursive=False):
    """Get list of all files to be processed."""
    path = Path(path)
    files = []
    
    if path.is_file():
        files.append(path)
    elif path.is_dir():
        if recursive:
            files.extend([f for f in path.rglob('*') if f.is_file()])
        else:
            files.extend([f for f in path.iterdir() if f.is_file()])
            
    return files

def upload_file(file_path, config, current, total):
    """Upload a single file to the API."""
    try:
        stats = os.stat(file_path)
        
        headers = {
            'Accept': 'application/json',
            'x-api-key': config['api_key']
        }

        data = {
            'deviceAssetId': f'{file_path}-{stats.st_mtime}',
            'deviceId': 'python',
            'fileCreatedAt': datetime.fromtimestamp(stats.st_mtime),
            'fileModifiedAt': datetime.fromtimestamp(stats.st_mtime),
            'isFavorite': 'false',
        }

        progress = (current / total) * 100
        print(f"[{progress:3.1f}%] Uploading {file_path}...", end='', flush=True)

        with open(file_path, 'rb') as f:
            files = {
                'assetData': f
            }
            response = requests.post(
                f"{config['base_url']}/assets", headers=headers, data=data, files=files)
            
        result = response.json()
        print(f" Done - {result}")
        return True
        
    except Exception as e:
        print(f" Error: {str(e)}")
        return False

def process_path(path, config, recursive=False):
    """Process a path, which can be a file or directory."""
    start_time = time.time()
    
    # Get list of all files to process
    files = get_file_list(path, recursive)
    total_files = len(files)
    
    if total_files == 0:
        print("No files found to process.")
        return
    
    print(f"Found {total_files} files to process")
    
    # Process each file
    successful_uploads = 0
    for i, file_path in enumerate(files, 1):
        if upload_file(str(file_path), config, i, total_files):
            successful_uploads += 1
    
    # Calculate and display summary
    end_time = time.time()
    total_time = end_time - start_time
    
    print("\nUpload Summary:")
    print(f"Total files processed: {total_files}")
    print(f"Successful uploads: {successful_uploads}")
    print(f"Failed uploads: {total_files - successful_uploads}")
    print(f"Total runtime: {total_time:.2f} seconds")
    if total_files > 0:
        print(f"Average time per file: {total_time/total_files:.2f} seconds")

def main():
    parser = argparse.ArgumentParser(description='Upload files to API')
    parser.add_argument('path', help='Path to file or directory to upload')
    parser.add_argument('-r', '--recursive', action='store_true',
                        help='Recursively process directories')
    parser.add_argument('-c', '--config', default='secrets.yaml',
                        help='Path to configuration file (default: secrets.yaml)')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    process_path(args.path, config, args.recursive)

if __name__ == '__main__':
    main()
