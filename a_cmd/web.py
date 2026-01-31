"""aio web - Open web search"""
import sys, os

def run():
    if len(sys.argv) > 2: os.system('xdg-open "https://google.com/search?q=' + '+'.join(sys.argv[2:]) + '"')
    else: os.system(os.popen('xdg-settings get default-web-browser').read()[:-9] + ' --new-window')
