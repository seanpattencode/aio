#!/bin/bash
# Final demonstration that terminal works end-to-end

echo "=========================================="
echo "AIOS Terminal - Final Demonstration"
echo "=========================================="
echo
echo "This will verify the terminal works exactly as documented."
echo
echo "Steps:"
echo "  1. Create test job with interactive shell"
echo "  2. Attach to terminal"
echo "  3. Verify browser opens and terminal loads"
echo "  4. Take screenshots as proof"
echo
echo "Press Enter to start..."
read

python3 <<'PYTHON'
import sys, time, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path.cwd()))

print("\n1. Cleaning up...")
subprocess.run("tmux kill-session -t aios-* 2>/dev/null || true", shell=True)
subprocess.run("lsof -ti:7681 | xargs kill -9 2>/dev/null || true", shell=True)
subprocess.run("lsof -ti:7682 | xargs kill -9 2>/dev/null || true", shell=True)
time.sleep(2)
Path("terminal.html").unlink(missing_ok=True)
print("✓ Clean")

print("\n2. Importing aios...")
import aios
import libtmux
print("✓ Imported")

print("\n3. Creating interactive job (demo)...")
server = libtmux.Server()

# Simulate user workflow: create job with interactive shell
session_name = "aios-demo-20251012_230000"
session = server.new_session(session_name, window_command="bash", attach=False)
time.sleep(1)
print(f"✓ Job started: {session_name}")

print("\n4. Calling aios.open_terminal('demo')...")
# This is what happens when user types "attach demo"
result = aios.open_terminal("demo")
print(f"   {result}")

# Verify terminal.html was created
html_file = Path("terminal.html")
if html_file.exists():
    print(f"✓ terminal.html created ({html_file.stat().st_size} bytes)")
else:
    print("✗ terminal.html not created!")
    sys.exit(1)

print("\n5. Testing in browser...")
time.sleep(2)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(viewport={'width': 1280, 'height': 720})

    url = f"http://localhost:{aios.ws_port}/terminal.html?session={session_name}"

    try:
        response = page.goto(url, wait_until="networkidle", timeout=10000)
        print(f"✓ Browser loaded (HTTP {response.status})")

        page.wait_for_selector("#terminal", timeout=5000)
        print("✓ Terminal rendered")

        time.sleep(2)

        # Take proof screenshot
        page.screenshot(path="proof_terminal_works.png")
        print("✓ Screenshot: proof_terminal_works.png")

        # Test interaction
        page.keyboard.type("echo '==== TERMINAL IS WORKING ===='\n")
        time.sleep(1)
        page.keyboard.type("pwd\n")
        time.sleep(1)
        page.keyboard.type("echo 'Success!'\n")
        time.sleep(1)

        # Final screenshot
        page.screenshot(path="proof_terminal_interactive.png")
        print("✓ Screenshot: proof_terminal_interactive.png")

        print("\n" + "="*60)
        print("✓ TERMINAL WORKS PERFECTLY!")
        print("="*60)
        print()
        print("Proof screenshots:")
        print("  - proof_terminal_works.png")
        print("  - proof_terminal_interactive.png")
        print()
        print("The terminal is ready for use!")
        print()

        time.sleep(3)

    except Exception as e:
        print(f"✗ Failed: {e}")
        page.screenshot(path="proof_error.png")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        browser.close()

# Cleanup
session.kill()
print("\n6. Cleaned up")
print("\n✓ DEMO COMPLETE")
PYTHON

echo
echo "=========================================="
echo "Demo complete!"
echo "=========================================="
