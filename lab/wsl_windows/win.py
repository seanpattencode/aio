import subprocess, sys
# stderr=DEVNULL suppresses UNC path warning from cmd.exe
subprocess.run(['cmd.exe', '/c'] + sys.argv[1:], stderr=subprocess.DEVNULL)
