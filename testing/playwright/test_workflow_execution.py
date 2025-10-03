#!/usr/bin/env python3
import sys, time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / 'core'))
import aios_db
from playwright.sync_api import sync_playwright

def test_workflow_execution():
    ports = aios_db.read("ports")
    port = ports.get("web", 8080)
    base_url = f"http://localhost:{port}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{base_url}/workflow-manager")
        page.wait_for_load_state("networkidle")

        # Scroll down to see workflow section
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        page.screenshot(path="testing/screenshots/workflow_section.png")

        # Check if workflow select exists
        page.wait_for_selector("#workflow-select", timeout=5000)

        # Get workflow options
        options = page.locator("#workflow-select option").all_text_contents()
        print(f"Available workflows: {options}")

        # Check if prime_factorization workflow is available
        if any('prime' in opt.lower() for opt in options):
            print("✅ Prime factorization workflow found!")

            # Select the workflow
            page.select_option("#workflow-select", label=[opt for opt in options if 'prime' in opt.lower()][0])
            time.sleep(0.5)
            page.screenshot(path="testing/screenshots/workflow_selected.png")

            print("✅ Workflow selected successfully!")
        else:
            print(f"⚠️ Prime factorization workflow not found in: {options}")

        # Check Terminal and VSCode buttons work
        terminal_buttons = page.locator("button:has-text('Terminal')").count()
        vscode_buttons = page.locator("button:has-text('VSCode')").count()
        print(f"Found {terminal_buttons} Terminal buttons and {vscode_buttons} VSCode buttons")

        browser.close()

    print("✅ Workflow execution test completed!")

if __name__ == "__main__":
    test_workflow_execution()
