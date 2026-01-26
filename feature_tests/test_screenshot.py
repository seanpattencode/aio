#!/usr/bin/env python3
"""Android screenshot. Usage: python test_screenshot.py [output.png]"""
import subprocess as sp, sys, time, os
out = sys.argv[1] if len(sys.argv) > 1 else f"/tmp/shot_{int(time.time())}.png"
r = sp.run(["su", "-c", f"/system/bin/screencap -p {out}"], capture_output=True)
print(f"+ {out} ({os.path.getsize(out)}b)" if r.returncode == 0 and os.path.exists(out) else f"x {r.stderr.decode().strip() or 'Failed'}")
