#!/usr/bin/env python3
import sys
import os
import json
import threading
import time
from pathlib import Path

# Add the googleDriveSyncDemo folder to path
sys.path.insert(0, str(Path(__file__).parent / 'googleDriveSyncDemo'))

TOKEN_FILE = Path(__file__).parent / 'googleDriveSyncDemo' / 'token.json'
WEB_SERVER_THREAD = None
WEB_SERVER_STARTED = False

def check_auth():
    """Check if we have valid authentication"""
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, 'r') as f:
                token = json.load(f)
                if 'token' in token or 'refresh_token' in token:
                    return True
        except:
            pass
    return False

def start_web_server():
    """Start the Flask web server in a thread"""
    global WEB_SERVER_STARTED
    try:
        # Change to the googleDriveSyncDemo directory
        import os
        original_dir = os.getcwd()
        os.chdir(Path(__file__).parent / 'googleDriveSyncDemo')

        from app import app
        print("\nStarting authentication web server at http://localhost:5000")
        app.run(host='0.0.0.0', port=5000, debug=False)
        WEB_SERVER_STARTED = True
    except Exception as e:
        print(f"Failed to start web server: {e}")

def backup_to_drive(*args, **kwargs):
    """Main backup function called by orchestrator"""
    if check_auth():
        try:
            # Import necessary modules
            from datetime import datetime
            from pathlib import Path

            # Change to googleDriveSyncDemo directory to use the app functions
            import os
            original_dir = os.getcwd()
            os.chdir(Path(__file__).parent / 'googleDriveSyncDemo')

            # Import the app functions
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaFileUpload

            # Load credentials from token.json
            with open('token.json', 'r') as f:
                token_data = json.load(f)

            creds = Credentials.from_authorized_user_info(token_data)
            service = build('drive', 'v3', credentials=creds)

            # Ensure AIOS_Backups folder exists
            folder_name = 'AIOS_Backups'
            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            files = service.files().list(q=query, fields="files(id)", pageSize=1).execute().get('files', [])

            if files:
                folder_id = files[0]['id']
            else:
                folder_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
                folder = service.files().create(body=folder_metadata, fields='id').execute()
                folder_id = folder['id']
                print(f"Created {folder_name} folder in Google Drive")

            # Upload orchestrator.db with timestamp
            db_path = '../../orchestrator.db'
            if os.path.exists(db_path):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                file_metadata = {'name': f'orchestrator_{timestamp}.db', 'parents': [folder_id]}
                media = MediaFileUpload(db_path, mimetype='application/x-sqlite3')
                file = service.files().create(body=file_metadata, media_body=media, fields='id,name').execute()

                os.chdir(original_dir)
                print(f"Database backed up successfully: {file.get('name')}")
                return f"Backup completed: {file.get('name')}"
            else:
                os.chdir(original_dir)
                print("Database file not found")
                return "Database file not found"

        except Exception as e:
            print(f"Backup error: {e}")
            return f"Backup failed: {e}"
    else:
        print("Google Drive backup: Not authenticated")
        return "Authentication required"

def init_check():
    """Called at orchestrator startup to check auth and start web server if needed"""
    global WEB_SERVER_THREAD

    if not check_auth():
        print("\n" + "="*60)
        print("GOOGLE DRIVE BACKUP - AUTHENTICATION REQUIRED AT http://localhost:5000")
        print("="*60)
        print("Starting web server for authentication...")
        print("1. Open http://localhost:5000 in your browser")
        print("2. Click 'Sign in with Google'")
        print("3. Authorize the application")
        print("="*60 + "\n")

        # Start web server in background thread
        WEB_SERVER_THREAD = threading.Thread(target=start_web_server, daemon=True)
        WEB_SERVER_THREAD.start()

        # Give server time to start
        time.sleep(2)
        return False
    else:
        print("Google Drive backup: Already authenticated")
        return True

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        init_check()
        # Keep script running if web server is started
        if WEB_SERVER_THREAD and WEB_SERVER_THREAD.is_alive():
            WEB_SERVER_THREAD.join()
    else:
        backup_to_drive()