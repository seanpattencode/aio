#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent / 'core'))
import aios_db
from playwright.sync_api import sync_playwright, expect

def test_workflow_manager():
    # Get port from database
    ports = aios_db.read("ports")
    port = ports.get("web", 8080)
    base_url = f"http://localhost:{port}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Navigate to workflow manager
        page.goto(f"{base_url}/workflow-manager")
        page.wait_for_load_state("networkidle")

        # Take screenshot
        page.screenshot(path="testing/screenshots/workflow_manager_initial.png")

        # Check if workflow manager loaded
        page.wait_for_selector("h1", timeout=5000)
        title = page.locator("h1").text_content()
        assert "Workflow" in title, f"Expected 'Workflow' in title, got: {title}"

        # Check if workflow select is visible
        page.wait_for_selector("#workflow-select", timeout=5000)

        # Check if terminal container exists
        page.wait_for_selector("#terminal", timeout=5000)

        # Take final screenshot
        page.screenshot(path="testing/screenshots/workflow_manager_loaded.png")

        browser.close()

    print("✅ Workflow manager test passed!")

if __name__ == "__main__":
    test_workflow_manager()
