"""aio send - Send to session"""
import sys
from . _common import send_to_sess, _die

def run():
    wda = sys.argv[2] if len(sys.argv) > 2 else None
    wda or _die("Usage: a send <session> <prompt> [--wait] [--no-enter]")
    prompt = ' '.join(a for a in sys.argv[3:] if a not in ('--wait', '--no-enter'))
    prompt or _die("No prompt provided")
    send_to_sess(wda, prompt, wait='--wait' in sys.argv, timeout=60, enter='--no-enter' not in sys.argv) or sys.exit(1)
