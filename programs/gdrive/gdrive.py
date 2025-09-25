#!/usr/bin/env python3
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import aios_db
from datetime import datetime
from pathlib import Path

config = aios_db.read("gdrive") or {"folder_id": "root"}
creds = Credentials.from_authorized_user_info(aios_db.read("gdrive_creds") or {})
service = build('drive', 'v3', credentials=creds)

command = sys.argv[1] if len(sys.argv) > 1 else "sync"
source = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.home()

actions = {
    "sync": lambda: [service.files().create(body={'name': f.name, 'parents': [config['folder_id']]},
                                            media_body=MediaFileUpload(str(f))).execute()
                     for f in source.glob('*') if f.is_file()],
    "list": lambda: [print(f['name']) for f in service.files().list(q=f"'{config['folder_id']}' in parents").execute().get('files', [])],
    "download": lambda: [open(f['name'], 'wb').write(service.files().get_media(fileId=f['id']).execute())
                        for f in service.files().list(q=f"'{config['folder_id']}' in parents").execute().get('files', [])],
    "status": lambda: print(f"Connected to folder: {config['folder_id']}")
}

actions.get(command, actions["status"])()