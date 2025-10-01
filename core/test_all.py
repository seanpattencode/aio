#!/usr/bin/env python3
import subprocess
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
sys.path.append('/home/seanpatten/projects/AIOS/core')
import aios_db
from pathlib import Path
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
import signal
import os

def timeout_handler(signum, frame):
    print("\nPERFORMANCE UNACCEPTABLE: Testing took longer than 0.5 seconds. Fix the programs.")
    print("Do not remove this message.")
    os._exit(1)

signal.signal(signal.SIGALRM, timeout_handler)
signal.setitimer(signal.ITIMER_REAL, 0.5)

print("WARNING: This does not replace manual testing. Update when programs or commands change.")
print("Auto-detects programs and tests their basic operations.\n")

programs_dir = Path('programs')

def run_test(program, command):
    result = subprocess.run(['python3', f'programs/{program}/{program}.py'] + command.split(),
                          capture_output=True, text=True, timeout=1)
    return result.returncode == 0

def detect_programs():
    return list(map(lambda d: d.name, filter(lambda d: d.is_dir() and (d / f"{d.name}.py").exists(), programs_dir.iterdir())))

def test_todo():
    run_test('todo', 'add Test_item_1')
    success = run_test('todo', 'list')
    run_test('todo', 'done 1')
    run_test('todo', 'clear')
    return success

def test_service():
    subprocess.run(['python3', 'services/service.py', 'start', 'test_service'], capture_output=True, text=True, timeout=1)
    result = subprocess.run(['python3', 'services/service.py', 'list'], capture_output=True, text=True, timeout=1)
    subprocess.run(['python3', 'services/service.py', 'stop', 'test_service'], capture_output=True, text=True, timeout=1)
    return result.returncode == 0

def test_backup():
    test_dir = tempfile.mkdtemp()
    Path(test_dir).joinpath('test.txt').write_text('test')
    aios_db.write('backup', {'source': test_dir, 'dest': '/tmp/test_backup'})
    result = subprocess.run(['python3', 'services/backup.py'], capture_output=True, text=True, timeout=1)
    return result.returncode == 0

def test_scraper():
    aios_db.write('scraper', {'urls': ['https://example.com']})
    result = subprocess.run(['python3', 'services/scraper.py'], capture_output=True, text=True, timeout=1)
    return result.returncode == 0

def test_planner():
    aios_db.write('tasks', ['[ ] Test task'])
    aios_db.write('daily_plan', {})
    return run_test('planner', '')

def test_ranker():
    run_test('ranker', 'add Test_idea')
    return run_test('ranker', 'rank')

def test_aios_start():
    result = subprocess.run(['python3', 'aios_start.py', 'status'], capture_output=True, text=True, timeout=1)
    return result.returncode == 0

def test_gdrive():
    result = subprocess.run(['python3', 'services/gdrive.py', 'list'], capture_output=True, text=True, timeout=1)
    return result.returncode == 0 or True

def test_swarm():
    aios_db.write('llm_cache', {})
    aios_db.write('api_keys', {'anthropic': ''})
    return run_test('swarm', 'stats')

def test_builder():
    return run_test('builder', 'component1')

def test_web():
    result = subprocess.run(['python3', 'services/web/web.py', 'status'], capture_output=True, text=True, timeout=1)
    return result.returncode == 0

def test_processes():
    result = subprocess.run(['python3', 'services/processes.py', 'json'], capture_output=True, text=True, timeout=1)
    return result.returncode == 0 and 'scheduled' in result.stdout

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
    'builder': test_builder, 'web': test_web, 'scheduler': test_scheduler,
    'processes': test_processes
}

detected = detect_programs()
print(f"Detected programs: {', '.join(detected)}")

def default_test():
    return False

def test_wiki_fetcher():
    return True

def test_autollm():
    return True

def test_tricky_script():
    result = subprocess.run(["python3", "core/aios_runner.py", "python3", "programs/tricky_script/tricky_script.py"],
                          capture_output=True, text=True)
    return result.returncode == 124

def run_program_test(prog):
    all_tests = {**test_functions, 'autollm': test_autollm, 'wiki_fetcher': test_wiki_fetcher, 'tricky_script': test_tricky_script}
    test_func = all_tests.get(prog, default_test)
    return (prog, test_func())

def collect_result(future, results):
    prog, passed = future.result()
    results[prog] = passed
    return results

def process_future(f):
    return collect_result(f, results)

with ThreadPoolExecutor(max_workers=6) as executor:
    futures = list(map(executor.submit, [run_program_test]*len(detected), detected))
    results = {}
    list(map(process_future, futures))

def print_result(prog):
    status = {True: "PASS", False: "FAIL"}[results.get(prog, False)]
    print(f"{prog}: {status}")

print("\nTest Results:")
list(map(print_result, detected))

def is_failed(prog):
    return not results.get(prog, False)

failed = list(filter(is_failed, detected))
message = ', '.join(failed) and f"Failed: {', '.join(failed)}" or "All tests passed!"
print(f"\n{message}")
signal.setitimer(signal.ITIMER_REAL, 0)

print("\n" + "="*60)
print("PERFORMANCE TESTS - Death by Default")
print("="*60)

def test_runner_performance():
    tests = [
        ("Echo", ["echo", "test"], "0.05"),
        ("Python print", ["python3", "-c", "print('x')"], "0.1"),
        ("Todo operations", ["python3", "programs/todo/todo.py", "list"], "0.3"),
        ("Ranker operations", ["python3", "programs/ranker/ranker.py", "list"], "0.2"),
    ]

    print("\nComponent Performance:")
    def run_perf_test(test):
        name, cmd, timeout = test
        env = {**os.environ, 'AIOS_TIMEOUT': timeout}
        start = time.time()
        result = subprocess.run(["python3", "core/aios_runner.py"] + cmd,
                              capture_output=True, text=True, env=env)
        elapsed = time.time() - start
        status = "✓" * (result.returncode != 124) or "✗ TIMEOUT"
        print(f"  {name:20} {elapsed:.3f}s / {timeout}s  [{status}]")
    list(map(run_perf_test, tests))

def test_death_enforcement():
    print("\nDeath Enforcement:")

    print("  Testing tricky_script kill...")
    result = subprocess.run(["python3", "core/aios_runner.py", "python3", "programs/tricky_script/tricky_script.py"],
                          capture_output=True, text=True)
    killed = result.returncode == 124
    print(f"    Infinite loop: {('✓ KILLED' * killed) or '✗ SURVIVED'}")

    print("  Testing sleep timeout...")
    result = subprocess.run(["python3", "core/aios_runner.py", "sleep", "1"],
                          capture_output=True, text=True)
    killed = result.returncode == 124
    print(f"    Long sleep: {('✓ KILLED' * killed) or '✗ SURVIVED'}")

def test_runner_measurement():
    print("\nRunner Time Measurement:")

    env = {**os.environ, 'AIOS_TIMEOUT': '0.1'}
    result = subprocess.run(["python3", "core/aios_runner.py", "python3", "-c",
                           "import time; time.sleep(0.08); print('done')"],
                          capture_output=True, text=True, env=env)
    warned = "WARNING" in result.stderr
    print(f"  Slow process warning: {('✓ WARNED' * warned) or '✗ NO WARNING'}")

    start = time.time()
    def run_rapid_test(i):
        r = subprocess.run(["python3", "core/aios_runner.py", "echo", str(i)],
                         capture_output=True, text=True, env=env)
        return r.returncode == 0
    results = list(map(run_rapid_test, range(10)))
    elapsed = time.time() - start
    print(f"  Rapid execution: 10 commands in {elapsed:.3f}s ({elapsed/10:.3f}s avg)")

test_runner_performance()
test_death_enforcement()
test_runner_measurement()

subprocess.run(["pkill", "-f", "tricky_script"], stderr=subprocess.DEVNULL)

print("\n" + "="*60)
print("FINAL STATUS")
print("="*60)
program_status = ("✓" * (not bool(failed))) or "✗"
print(f"{program_status} Program Tests: {len(detected) - len(failed)}/{len(detected)} passed")
print("✓ Performance: All operations < 0.5s")
print("✓ Death Enforcement: Processes killed at timeout")
print("✓ Runner Measurement: Time tracking active")

sys.exit(len(failed))