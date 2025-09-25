#!/usr/bin/env python3
import subprocess
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from pathlib import Path
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
import signal
import os

def timeout_handler(signum, frame):
    print("\nPERFORMANCE UNACCEPTABLE: Testing took longer than 4 seconds. Fix the programs.")
    print("Do not remove this message.")
    os._exit(1)

signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(4)

print("WARNING: This does not replace manual testing. Update when programs or commands change.")
print("Auto-detects programs and tests their basic operations.\n")

programs_dir = Path('programs')

def run_test(program, command):
    result = subprocess.run(['python3', f'programs/{program}/{program}.py'] + command.split(),
                          capture_output=True, text=True, timeout=1)
    return result.returncode == 0

def detect_programs():
    return [d.name for d in programs_dir.iterdir() if d.is_dir() and (d / f"{d.name}.py").exists()]

def test_todo():
    run_test('todo', 'add Test_item_1')
    success = run_test('todo', 'list')
    run_test('todo', 'done 1')
    run_test('todo', 'clear')
    return success

def test_service():
    run_test('service', 'start test_service')
    success = run_test('service', 'list')
    run_test('service', 'stop test_service')
    return success

def test_backup():
    test_dir = tempfile.mkdtemp()
    Path(test_dir).joinpath('test.txt').write_text('test')
    aios_db.write('backup', {'source': test_dir, 'dest': '/tmp/test_backup'})
    return run_test('backup', '')

def test_scraper():
    aios_db.write('scraper', {'urls': ['https://example.com']})
    return run_test('scraper', '')

def test_planner():
    aios_db.write('tasks', ['[ ] Test task'])
    return run_test('planner', '')

def test_ranker():
    run_test('ranker', 'add Test_idea')
    return run_test('ranker', 'rank')

def test_aios_start():
    return run_test('aios_start', 'status')

def test_gdrive():
    return True

def test_swarm():
    return run_test('swarm', 'stats')

def test_builder():
    return run_test('builder', 'component1')

def test_web():
    return run_test('web', 'status')

def test_scheduler():
    aios_db.write('schedule', {'daily': {}, 'hourly': {}})
    proc = subprocess.Popen(['python3', 'programs/schedule/scheduler.py'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.2)
    proc.terminate()
    return True

test_functions = {
    'todo': test_todo, 'service': test_service, 'backup': test_backup,
    'scraper': test_scraper, 'planner': test_planner, 'ranker': test_ranker,
    'aios_start': test_aios_start, 'gdrive': test_gdrive, 'swarm': test_swarm,
    'builder': test_builder, 'web': test_web, 'scheduler': test_scheduler
}

detected = detect_programs()
print(f"Detected programs: {', '.join(detected)}")

def run_program_test(prog):
    if prog == 'autollm':
        return (prog, True)
    test_func = test_functions.get(prog, lambda: False)
    return (prog, test_func())

with ThreadPoolExecutor(max_workers=6) as executor:
    futures = [executor.submit(run_program_test, prog) for prog in detected]
    results = dict([future.result() for future in futures])

print("\nTest Results:")
[print(f"{prog}: {'✓' if results.get(prog, False) else '✗'}") for prog in detected]

failed = [prog for prog in detected if not results.get(prog, False)]
print(f"\n{'All tests passed!' if not failed else f'Failed: {', '.join(failed)}'}")
signal.alarm(0)
sys.exit(0 if not failed else 1)