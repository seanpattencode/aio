#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'googleDriveSyncDemo'))

def backup_to_drive(*args, **kwargs):
    """Minimal wrapper to satisfy orchestrator.py requirements"""
    print("Google Drive backup called - requires web authentication at http://localhost:5000")
    return "Please use web interface for Google Drive backup"

if __name__ == "__main__":
    backup_to_drive()