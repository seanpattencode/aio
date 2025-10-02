#!/usr/bin/env python3
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
from datetime import datetime

screenshot_dir = Path(__file__).parent / "screenshots"
screenshot_dir.mkdir(exist_ok=True)

async def test_page(page, name, url, actions=None):
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    await page.screenshot(path=str(screenshot_dir / f"{name}_{timestamp}.png"))
    actions and await actions(page)

async def run_tests():
    print("="*70)
    print(" ⚠️  MANUAL INSPECTION REQUIRED")
    print("="*70)
    print(" This test captures page screenshots but DOES NOT verify:")
    print("   - JavaScript functions work correctly")
    print("   - Page content is accurate")
    print("   - All features are operational")
    print(" Screenshots must be manually reviewed for correctness.")
    print("="*70)
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 720})
        page = await context.new_page()

        import sys
        sys.path.append('/home/seanpatten/projects/AIOS')
        from core import aios_db
        port = aios_db.read('ports')['web']
        base_url = f"http://localhost:{port}"

        tests = [
            ("index", f"{base_url}/"),
            ("todo", f"{base_url}/todo"),
            ("feed", f"{base_url}/feed"),
            ("jobs", f"{base_url}/jobs"),
            ("settings", f"{base_url}/settings"),
            ("autollm", f"{base_url}/autollm"),
            ("workflow", f"{base_url}/workflow"),
            ("workflow_manager", f"{base_url}/workflow-manager"),
            ("terminal_emulator", f"{base_url}/terminal-emulator"),
            ("terminal_xterm", f"{base_url}/terminal-xterm")
        ]

        [await test_page(page, name, url) for name, url in tests]

        await browser.close()
        print(f"Screenshots saved to {screenshot_dir}")

asyncio.run(run_tests())