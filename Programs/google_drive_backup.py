#!/usr/bin/env python3
import json
import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

# Flask and Google imports for web server
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

# Database path
DB_PATH = Path(__file__).parent.parent / 'orchestrator.db'

# Web server for authentication
app = Flask(__name__)
app.secret_key = 'aios-backup-secret-key-change-in-production'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# OAuth2 configuration
CLIENT_CONFIG = {
    "web": {
        "client_id": "***REMOVED***",
        "project_id": "todoapp9-165",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "***REMOVED***",
        "redirect_uris": ["http://localhost:5000/oauth/callback"]
    }
}

SCOPES = ['https://www.googleapis.com/auth/drive']

# HTML templates
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AIOS Google Drive Backup - Authentication Required</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background-color: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .btn { display: inline-block; padding: 12px 24px; background: #4285f4; color: white; text-decoration: none; border-radius: 6px; font-weight: 500; }
        .btn:hover { background: #357ae8; }
        h1 { color: #202124; }
        .info { background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>AIOS Google Drive Backup</h1>
        <p>Authentication is required to backup your AIOS database to Google Drive.</p>
        <div class="info">
            <h3>This service will:</h3>
            <ul>
                <li>Backup your orchestrator.db every 2 hours</li>
                <li>Store backups in an "AIOS_Backups" folder in your Drive</li>
                <li>Keep your data completely private in your own account</li>
            </ul>
        </div>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{{ url_for('login') }}" class="btn">Sign in with Google</a>
        </div>
    </div>
</body>
</html>
"""

SUCCESS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>AIOS Google Drive Backup - Success</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; background-color: #f5f5f5; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .success { color: #0d652d; background: #d4edda; padding: 15px; border-radius: 8px; margin: 20px 0; }
        h1 { color: #202124; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Authentication Successful!</h1>
        <div class="success">
            <h3>✅ Google Drive backup is now configured</h3>
            <p>Your AIOS database will be automatically backed up every 2 hours.</p>
            <p>You can close this window and return to your terminal.</p>
        </div>
        <p><strong>Signed in as:</strong> {{ email }}</p>
    </div>
</body>
</html>
"""

def get_config(key):
    """Get a config value from the database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
    result = cursor.fetchone()
    conn.close()
    return result["value"] if result else None

def set_config(key, value):
    """Set a config value in the database"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO config (key, value, updated) VALUES (?, ?, ?)",
        (key, value, time.time())
    )
    conn.commit()
    conn.close()

def check_auth():
    """Check if we have valid authentication in database"""
    token_data = get_config('google_drive_token')
    if token_data:
        try:
            token = json.loads(token_data)
            if 'refresh_token' in token:
                # Try to refresh if needed
                creds = Credentials.from_authorized_user_info(token, SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    # Save refreshed token
                    set_config('google_drive_token', creds.to_json())
                return True
        except Exception as e:
            print(f"Auth check failed: {e}")
    return False

def get_google_auth_flow():
    """Create OAuth2 flow from config"""
    return Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=url_for('oauth_callback', _external=True)
    )

# Flask routes for authentication
@app.route('/')
def index():
    """Show login page"""
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/login')
def login():
    """Redirect to Google OAuth"""
    flow = get_google_auth_flow()
    auth_url, session['state'] = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    return redirect(auth_url)

@app.route('/oauth/callback')
def oauth_callback():
    """Handle OAuth callback"""
    if session.get('state') != request.args.get('state'):
        return "Invalid state parameter", 400

    flow = get_google_auth_flow()
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    # Save token to database
    set_config('google_drive_token', creds.to_json())

    # Get user email for display
    try:
        service = build('drive', 'v3', credentials=creds)
        about = service.about().get(fields="user").execute()
        email = about['user'].get('emailAddress', 'Unknown')
    except:
        email = 'Unknown'

    print(f"\n{'='*60}")
    print("GOOGLE DRIVE AUTHENTICATION SUCCESSFUL!")
    print(f"Authenticated as: {email}")
    print(f"{'='*60}\n")

    return render_template_string(SUCCESS_TEMPLATE, email=email)

def backup_to_drive(*args, **kwargs):
    """Main backup function called by orchestrator"""
    if not check_auth():
        print("Google Drive backup: Not authenticated - please visit http://localhost:5000")
        return "Authentication required - visit http://localhost:5000"

    try:
        # Load credentials from database
        token_data = get_config('google_drive_token')
        if not token_data:
            return "No token found in database"

        creds = Credentials.from_authorized_user_info(json.loads(token_data), SCOPES)

        # Refresh token if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            set_config('google_drive_token', creds.to_json())

        service = build('drive', 'v3', credentials=creds)

        # Ensure AIOS_Backups folder exists
        folder_name = 'AIOS_Backups'
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        response = service.files().list(q=query, fields="files(id)", pageSize=1).execute()
        files = response.get('files', [])

        if files:
            folder_id = files[0]['id']
        else:
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=folder_metadata, fields='id').execute()
            folder_id = folder['id']
            print(f"Created {folder_name} folder in Google Drive")

        # Upload orchestrator.db with timestamp
        db_path = DB_PATH
        if db_path.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_metadata = {
                'name': f'orchestrator_{timestamp}.db',
                'parents': [folder_id]
            }
            media = MediaFileUpload(str(db_path), mimetype='application/x-sqlite3')
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name'
            ).execute()

            print(f"Database backed up successfully: {file.get('name')}")
            return f"Backup completed: {file.get('name')}"
        else:
            print("Database file not found")
            return "Database file not found"

    except Exception as e:
        print(f"Backup error: {e}")
        return f"Backup failed: {e}"

def init_check():
    """Called at orchestrator startup to check auth and start web server if needed"""
    if not check_auth():
        print("\n" + "="*60)
        print("GOOGLE DRIVE BACKUP - AUTHENTICATION REQUIRED")
        print("="*60)
        print("Starting web server for authentication...")
        print("1. Open http://localhost:5000 in your browser")
        print("2. Click 'Sign in with Google'")
        print("3. Authorize the application")
        print("="*60 + "\n")

        # Start web server in background thread
        web_thread = threading.Thread(
            target=lambda: app.run(host='0.0.0.0', port=5000, debug=False),
            daemon=True
        )
        web_thread.start()
        time.sleep(2)  # Give server time to start
        return False
    else:
        print("\n" + "="*60)
        print("GOOGLE DRIVE BACKUP - READY")
        print("="*60)
        print("Backup service is authenticated and will run at scheduled intervals")
        print("="*60 + "\n")
        return True

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        if not check_auth():
            print("Starting authentication server...")
            app.run(host='0.0.0.0', port=5000, debug=False)
        else:
            print("Already authenticated!")
    else:
        result = backup_to_drive()
        print(result)