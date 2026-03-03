#!/usr/bin/env python3
"""Test interactive command picker with simulated tty"""
import pty, os, sys, time, select

def run_interactive_test(keystrokes, check_output):
    """Run aio i with keystrokes and check output"""
    master, slave = pty.openpty()
    pid = os.fork()

    if pid == 0:  # Child
        os.close(master)
        os.setsid()
        os.dup2(slave, 0); os.dup2(slave, 1); os.dup2(slave, 2)
        os.close(slave)
        os.execvp(sys.executable, [sys.executable, 'aio.py', 'i'])

    os.close(slave)
    time.sleep(0.2)

    def read_all():
        out = b''
        while select.select([master], [], [], 0.2)[0]:
            out += os.read(master, 4096)
        return out.decode('utf-8', errors='replace')

    read_all()  # Clear initial output
    for ch in keystrokes:
        os.write(master, ch.encode() if isinstance(ch, str) else ch)
        time.sleep(0.05)
    time.sleep(0.3)
    output = read_all()
    os.close(master)
    os.waitpid(pid, 0)
    return check_output(output)

def test_interactive():
    print("Testing interactive picker...\n")

    # Test 1: Typing filters suggestions
    tests = [
        ('c', ['cleanup', 'config', 'copy']),
        ('l', ['cleanup']),
        ('\x7f', ['cleanup', 'config', 'copy']),
        ('o', ['config', 'copy']),
        ('n', ['config']),
    ]

    master, slave = pty.openpty()
    pid = os.fork()
    if pid == 0:
        os.close(master); os.setsid()
        os.dup2(slave, 0); os.dup2(slave, 1); os.dup2(slave, 2)
        os.close(slave)
        os.execvp(sys.executable, [sys.executable, 'aio.py', 'i'])

    os.close(slave)
    time.sleep(0.2)

    def read_output():
        out = b''
        while select.select([master], [], [], 0.1)[0]:
            out += os.read(master, 1024)
        return out.decode('utf-8', errors='replace')

    read_output()  # Clear initial

    for chars, expected in tests:
        for c in chars: os.write(master, c.encode()); time.sleep(0.05)
        time.sleep(0.1)
        output = read_output()
        found = [e for e in expected if e in output]
        status = "PASS" if found else "FAIL"
        print(f"Sent {repr(chars):>6} -> found {found} [{status}]")

    os.write(master, b'\x1b'); time.sleep(0.1)
    os.close(master); os.waitpid(pid, 0)

    # Test 2: Enter with partial input selects first suggestion
    print("\nTest: Enter with partial 'cl' runs 'cleanup'...")
    result = run_interactive_test('cl\r', lambda o: 'Running: aio cleanup' in o)
    print(f"  Enter selects first suggestion: {'PASS' if result else 'FAIL'}")

    # Test 3: Enter with 'pu' runs 'push' (first of push/pull)
    print("\nTest: Enter with partial 'pu' runs 'push'...")
    result = run_interactive_test('pu\r', lambda o: 'Running: aio push' in o)
    print(f"  Enter selects first suggestion: {'PASS' if result else 'FAIL'}")

    print("\nAll tests completed!")

if __name__ == '__main__':
    test_interactive()
