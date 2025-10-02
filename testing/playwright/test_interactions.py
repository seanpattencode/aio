#!/usr/bin/env python3
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
from datetime import datetime

screenshot_dir = Path(__file__).parent / "screenshots"
screenshot_dir.mkdir(exist_ok=True)

async def screenshot(page, name):
    timestamp = datetime.now().strftime("%H%M%S")
    await page.screenshot(path=str(screenshot_dir / f"{name}_{timestamp}.png"))

async def test_interactions():
    print("="*70)
    print(" ⚠️  MANUAL INSPECTION REQUIRED")
    print("="*70)
    print(" This test captures interaction screenshots but DOES NOT verify:")
    print("   - Forms submit correctly")
    print("   - Data is saved properly")
    print("   - UI responds as expected")
    print(" Screenshots must be manually reviewed for correctness.")
    print("="*70)
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1280, 'height': 720})

        import sys
        sys.path.append('/home/seanpatten/projects/AIOS')
        from core import aios_db
        port = aios_db.read('ports')['web']
        base = f"http://localhost:{port}"

        await page.goto(f"{base}/")
        await screenshot(page, "home")

        await page.goto(f"{base}/todo")
        await screenshot(page, "todo_page")
        await page.fill('input[name="task"]', "Test Task")
        await page.press('input[name="task"]', "Enter")
        await page.wait_for_timeout(500)
        await screenshot(page, "todo_added")

        await page.goto(f"{base}/settings")
        await screenshot(page, "settings_page")
        (await page.click('button:has-text("Light")', timeout=2000)) or None
        await page.wait_for_timeout(500)
        await screenshot(page, "settings_light")

        await page.goto(f"{base}/workflow")
        await screenshot(page, "workflow_page")

        await page.goto(f"{base}/workflow-manager")
        await screenshot(page, "workflow_manager")

        await browser.close()
        print(f"Done: {len(list(screenshot_dir.glob('*.png')))} screenshots")

asyncio.run(test_interactions())