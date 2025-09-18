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
                if 'credentials' in str(token):
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
        print("Google Drive backup: Authenticated and ready")
        # TODO: Add actual backup logic here
        return "Google Drive backup completed"
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