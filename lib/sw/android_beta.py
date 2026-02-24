# Usage: python3 android_beta.py [--join] | ✅=tester 🔘=can join ⛔=no beta ❓=unknown | --join clicks all 🔘
import subprocess, shutil, os, sys
from playwright.sync_api import sync_playwright
JOIN = "--join" in sys.argv
pkgs = [l[8:] for l in subprocess.run(["adb", "shell", "pm", "list", "packages"], capture_output=True, text=True).stdout.split("\n") if l.startswith("package:")]
src, dst = os.path.expanduser("~/.config/google-chrome-beta"), os.path.expanduser("~/.aspect/chrome-profile")
os.makedirs(dst, exist_ok=True); shutil.copy2(f"{src}/Local State", dst); shutil.copytree(f"{src}/Default", f"{dst}/Default", dirs_exist_ok=True)
subprocess.Popen(["google-chrome-beta", f"--user-data-dir={dst}", "--remote-debugging-port=9222", "--disable-blink-features=AutomationControlled", "about:blank"]); __import__('time').sleep(3)
with sync_playwright() as p:
    page = p.chromium.connect_over_cdp("http://localhost:9222").contexts[0].pages[0]; stats = {"✅":0,"🔘":0,"⛔":0}
    for pkg in pkgs:
        page.goto(f"https://play.google.com/apps/testing/{pkg}"); h = page.content().lower()
        s = "⛔" if "not available" in h else ("✅" if "you are a tester" in h else ("🔘" if "become a tester" in h else "❓"))
        if JOIN and s=="🔘": page.get_by_text("Become a tester").click(); page.get_by_text("You are a tester").wait_for(timeout=10000); s="✅"
        stats[s] = stats.get(s,0)+1; print(f"{s} {pkg}")
    print(f"\n✅:{stats['✅']} 🔘:{stats['🔘']} ⛔:{stats['⛔']}")
