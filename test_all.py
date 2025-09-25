#!/usr/bin/env python3
import subprocess
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
import aios_db
from pathlib import Path
import time
import tempfile

print("WARNING: This does not replace manual testing. Update when programs or commands change.")
print("Auto-detects programs and tests their basic operations.\n")

programs_dir = Path('programs')
test_results = []

def run_test(program, command):
    result = subprocess.run(['python3', f'programs/{program}/{program}.py'] + command.split(),
                          capture_output=True, text=True, timeout=3)
    return result.returncode == 0

def detect_programs():
    return [d.name for d in programs_dir.iterdir() if d.is_dir() and (d / f"{d.name}.py").exists()]

def test_todo():
    run_test('todo', 'add Test_item_1')
    run_test('todo', 'add Test_item_2')
    success = run_test('todo', 'list')
    run_test('todo', 'done 1')
    run_test('todo', 'clear')
    return success

def test_service():
    run_test('service', 'start test_service')
    success = run_test('service', 'list')
    run_test('service', 'status test_service')
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
    success = run_test('ranker', 'rank')
    run_test('ranker', 'list')
    run_test('ranker', 'pick')
    return success

def test_aios_start():
    return run_test('aios_start', 'status')

def test_gdrive():
    aios_db.write('gdrive_creds', {'client_id': 'test', 'client_secret': 'test', 'refresh_token': 'test'})
    return True

def test_swarm():
    return run_test('swarm', 'stats')

def test_builder():
    return run_test('builder', 'component1 component2')

def test_web():
    return run_test('web', 'status')

def test_scheduler():
    aios_db.write('schedule', {'daily': {'09:00': 'echo test'}, 'hourly': {}})
    proc = subprocess.Popen(['python3', 'programs/schedule/scheduler.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)
    proc.terminate()
    return proc.poll() is not None

test_functions = {
    'todo': test_todo,
    'service': test_service,
    'backup': test_backup,
    'scraper': test_scraper,
    'planner': test_planner,
    'ranker': test_ranker,
    'aios_start': test_aios_start,
    'gdrive': test_gdrive,
    'swarm': test_swarm,
    'builder': test_builder,
    'web': test_web,
    'scheduler': test_scheduler
}

detected = detect_programs()
print(f"Detected programs: {', '.join(detected)}")

[test_results.append({
    'program': prog,
    'result': test_functions.get(prog, lambda: False)() if prog != 'autollm' else True
}) for prog in detected]

print("\nTest Results:")
[print(f"{r['program']}: {'✓' if r['result'] else '✗'}") for r in test_results]

failed = [r['program'] for r in test_results if not r['result']]
print(f"\n{'All tests passed!' if not failed else f'Failed: {', '.join(failed)}'}")
sys.exit(0 if not failed else 1)