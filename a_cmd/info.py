"""Show daemon status"""
import os, socket

def run():
    sock = '/tmp/a.sock'
    if os.path.exists(sock):
        try:
            s = socket.socket(socket.AF_UNIX)
            s.settimeout(0.1)
            s.connect(sock)
            s.close()
            print("✓ prewarm daemon active")
        except:
            print("✗ socket exists but daemon not responding")
    else:
        print("✗ prewarm daemon not running")
