#!/usr/bin/env python3
"""Test agent - verifies agent run + .done signal"""
import subprocess,os,sys
from base import save
msg=f"test ok (pid {os.getpid()})"
print(msg)
save("test",msg)
if "--done" in sys.argv:
    subprocess.run([os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'a'),'done'])
