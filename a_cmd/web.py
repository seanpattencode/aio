"""aio web - Open web search"""
import sys, subprocess as sp

def run():
    url = 'https://google.com/search?q=' + '+'.join(sys.argv[2:]) if len(sys.argv) > 2 else 'https://google.com'
    sp.Popen(['xdg-open', url], stdout=sp.DEVNULL, stderr=sp.DEVNULL)
