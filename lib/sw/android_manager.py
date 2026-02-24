#!/usr/bin/env python3
"""Android Refresh Rate Manager - Force peak refresh rates via ADB.

The key to forcing 120Hz is setting min_refresh_rate - this prevents the system
from dropping below your target rate. The Developer Options toggle alone is
insufficient because LTPO displays and power management can still drop rates.
"""
import subprocess, sys, shutil, os

def find_adb():
    if p := shutil.which("adb"): return p
    for base in [os.path.expanduser("~/Android/Sdk"), "/opt/android-sdk", os.environ.get("ANDROID_HOME", "")]:
        if base and os.path.isfile(p := os.path.join(base, "platform-tools", "adb")): return p
    return "adb"

ADB = find_adb()

def adb(*args):
    try:
        r = subprocess.run([ADB] + list(args), capture_output=True, text=True, timeout=10)
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except: return False, "", "timeout/error"

def get(ns, key): return adb("shell", "settings", "get", ns, key)[1]
def put(ns, key, val): return adb("shell", "settings", "put", ns, key, str(val))[0]
def shell(cmd): return adb("shell", cmd)

def device():
    ok, out, _ = adb("devices")
    if not ok: return print("❌ ADB not responding. Try: adb kill-server && adb start-server"), None
    lines = [l for l in out.splitlines()[1:] if l.split()[-1:] == ["device"]]
    if not lines: return print("❌ No device. Enable USB debugging & authorize."), None
    mfr, model = adb("shell", "getprop", "ro.product.manufacturer")[1], adb("shell", "getprop", "ro.product.model")[1]
    print(f"📱 {mfr} {model}\n"); return mfr.lower()

def status():
    if not (mfr := device()): return
    print(f"{'─'*40}\n📊 Settings:\n{'─'*40}")
    for name, ns, key, fmt in [
        ("Battery Saver", "global", "low_power", lambda v: "🔴 ON (blocks HRR!)" if v == "1" else "🟢 OFF"),
        ("Adaptive Battery", "global", "adaptive_battery_management_enabled", lambda v: "🟡 ON" if v == "1" else "🟢 OFF"),
        ("Min Refresh Rate", "system", "min_refresh_rate", lambda v: f"{'🟢' if v and v not in ('null','') and (v == 'Infinity' or float(v) >= 90) else '🟡'} {v or 'null'}"),
        ("Peak Refresh Rate", "system", "peak_refresh_rate", lambda v: f"🔵 {v or 'null'}"),
    ]: print(f"  {name}: {fmt(get(ns, key))}")
    # Device-specific
    if "samsung" in mfr: print(f"  Motion Smoothness: {get('system', 'motion_smoothness_level') or 'null'}")
    if any(x in mfr for x in ["oneplus", "oppo", "realme"]): print(f"  OPlus Override: {get('global', 'oneplus_screen_refresh_rate')}")
    # Show all refresh-related settings
    print(f"\n{'─'*40}\n🔍 All refresh settings:\n{'─'*40}")
    ok, out, _ = shell("settings list system")
    for line in out.splitlines():
        if "refresh" in line.lower(): print(f"  {line}")

def get_supported_rates():
    ok, out, _ = shell("dumpsys display")
    rates = set()
    for line in out.splitlines():
        if "fps=" in line.lower():
            for part in line.replace(",", " ").split():
                if part.lower().startswith("fps="):
                    try: rates.add(float(part.split("=")[1]))
                    except: pass
    return sorted(rates, reverse=True)

def set_overlay(on=True):
    if not device(): return
    v = "1" if on else "0"
    # Method 1: Standard setting
    if put("system", "show_refresh_rate_enabled", v):
        if get("system", "show_refresh_rate_enabled") == v:
            return print(f"✅ Overlay {'enabled' if on else 'disabled'} via settings")
    # Method 2: SurfaceFlinger service call
    ok, out, _ = adb("shell", "service", "call", "SurfaceFlinger", "1034", "i32", v)
    if ok and "Parcel" in out: return print(f"✅ Overlay {'enabled' if on else 'disabled'} via SurfaceFlinger")
    # Method 3: setprop (needs root usually)
    if shell(f"setprop debug.sf.show_refresh_rate_enabled {v}")[0]:
        return print(f"✅ Overlay {'enabled' if on else 'disabled'} via setprop")
    print(f"❌ Overlay toggle failed. Enable manually: Settings > Developer Options > Show refresh rate")

def fix_all(rate=120.0):
    """Force refresh rate by setting BOTH min and peak rates.

    The key insight: Developer Options 'Force Peak Refresh Rate' alone doesn't work
    because LTPO displays and power management can still drop rates. Setting
    min_refresh_rate is the 'nuclear option' that actually forces constant high rates.
    """
    if not (mfr := device()): return
    rates = get_supported_rates()
    if rates: print(f"📊 Supported rates: {', '.join(map(str, rates))}Hz")
    if rate not in rates and rates: print(f"⚠️  {rate}Hz not in supported rates, using anyway")
    print(f"\n🔧 Forcing {rate}Hz...\n")
    fixes = [
        ("Disable Battery Saver", lambda: put("global", "low_power", "0")),
        ("Set min_refresh_rate", lambda: put("system", "min_refresh_rate", rate)),
        ("Set peak_refresh_rate", lambda: put("system", "peak_refresh_rate", rate)),
    ]
    if "samsung" in mfr:
        fixes.append(("Samsung: motion_smoothness=2", lambda: put("system", "motion_smoothness_level", "2")))
    if any(x in mfr for x in ["oneplus", "oppo", "realme"]):
        fixes.append(("OPlus: disable rate manager", lambda: put("global", "oneplus_screen_refresh_rate", "0")))
    for desc, fn in fixes: print(f"  {'✅' if fn() else '❌'} {desc}")
    # Verify settings were written
    print(f"\n{'─'*40}\n🔍 Verifying settings:\n{'─'*40}")
    min_r, peak_r = get("system", "min_refresh_rate"), get("system", "peak_refresh_rate")
    print(f"  min_refresh_rate:  {min_r}")
    print(f"  peak_refresh_rate: {peak_r}")
    print(f"\n{'─'*40}")
    print("⚠️  NOTE: These settings may not take effect immediately.")
    print("   Android's display subsystem reads them unpredictably.")
    print("   They may suddenly start working later - timing cannot be controlled.")
    print("   Screen off/on or app switches sometimes trigger a re-read.")
    print(f"{'─'*40}")
    print("\n💡 Enable overlay to verify: python android_manager.py overlay")

def reset():
    if not device(): return
    print("🔄 Resetting to adaptive mode...\n")
    for ns, key in [("system", "min_refresh_rate"), ("system", "peak_refresh_rate")]:
        adb("shell", "settings", "delete", ns, key)
        print(f"  ✅ Deleted {ns}/{key}")
    print("\n✅ Reset to adaptive mode.")

def restart_adb():
    print("🔄 Restarting ADB server...")
    adb("kill-server"); adb("start-server")
    print("✅ ADB restarted. Reconnect device if needed.")

def clear_cache():
    if not device(): return
    print("🧹 Clearing adaptive battery caches...")
    for pkg in ["com.google.android.apps.turbo", "com.android.providers.settings"]:
        ok, _, _ = adb("shell", "pm", "clear", pkg)
        print(f"  {'✅' if ok else '❌'} {pkg}")

def open_dev_options():
    if not device(): return
    adb("shell", "am", "start", "-a", "android.settings.APPLICATION_DEVELOPMENT_SETTINGS")
    print("📱 Opened Developer Options")

def list_apps():
    if not device(): return
    ok, out, _ = adb("shell", "pm", "list", "packages")
    for line in sorted(out.splitlines()): print(f"  {line.replace('package:', '')}")
    print(f"\n  Total: {len(out.splitlines())}")

CMDS = {
    "status": (status, "Show all refresh rate settings"),
    "fix": (lambda: fix_all(float(sys.argv[2]) if len(sys.argv) > 2 else 120.0), "Force refresh rate [default: 120]"),
    "reset": (reset, "Reset to adaptive/default"),
    "overlay": (lambda: set_overlay(len(sys.argv) < 3 or sys.argv[2] != "off"), "Toggle FPS overlay [off]"),
    "clear": (clear_cache, "Clear adaptive battery cache"),
    "dev": (open_dev_options, "Open Developer Options"),
    "apps": (list_apps, "List all installed apps"),
    "restart": (restart_adb, "Restart ADB server"),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print("Android Refresh Rate Manager\n\nCommands:")
        for c, (_, d) in CMDS.items(): print(f"  {c:12} {d}")
        print("\nExamples:\n  python android_manager.py fix        # Force 120Hz")
        print("  python android_manager.py fix 90     # Force 90Hz")
        print("  python android_manager.py overlay    # Show FPS overlay")
    else: CMDS[sys.argv[1]][0]()
