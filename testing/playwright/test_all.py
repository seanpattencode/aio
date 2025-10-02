#!/usr/bin/env python3
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path
from datetime import datetime
import sys
sys.path.append('/home/seanpatten/projects/AIOS')
from core import aios_db

screenshot_dir = Path(__file__).parent / "screenshots"
screenshot_dir.mkdir(exist_ok=True)

async def test_all():
    print("="*70)
    print(" ⚠️  MANUAL INSPECTION REQUIRED")
    print("="*70)
    print(" This test captures screenshots but DOES NOT verify correctness.")
    print(" A human or LLM must manually inspect each screenshot to confirm:")
    print("   - UI elements are rendered correctly")
    print("   - No visual bugs or layout issues")
    print("   - All expected components are visible")
    print("="*70)
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1280, 'height': 720})

        port = aios_db.read('ports')['web']
        base = f"http://localhost:{port}"
        timestamp = datetime.now().strftime("%H%M%S")

        pages = [
            "index", "todo", "feed", "jobs", "settings",
            "autollm", "workflow", "workflow-manager",
            "terminal-emulator", "terminal-xterm"
        ]

        results = []
        for name in pages:
            url = f"{base}/" + ("" if name == "index" else name)
            await page.goto(url)
            await page.wait_for_timeout(500)
            path = screenshot_dir / f"{name}_{timestamp}.png"
            await page.screenshot(path=str(path))
            results.append(path.exists())
            print(f"✓ {name}")

        await browser.close()
        print(f"\nSaved {sum(results)}/{len(pages)} screenshots to {screenshot_dir}")
        print("\n" + "="*70)
        print(" ⚠️  IMPORTANT: Manually inspect all screenshots to verify correctness")
        print("="*70)

asyncio.run(test_all())