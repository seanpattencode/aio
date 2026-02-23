#!/usr/bin/env python3
"""TermuxBridge build+install: python build.py [serial]"""
import subprocess, sys, os, re

DIR = os.path.dirname(os.path.abspath(__file__))
IS_TERMUX = os.path.exists("/data/data/com.termux")
SDK = "/data/data/com.termux/files/home/android-sdk" if IS_TERMUX else os.environ.get("ANDROID_HOME", os.path.expanduser("~/Android/Sdk"))
PKG = "com.aios.termuxbridge"

if not IS_TERMUX:
    for v in ["21", "17"]:
        p = f"/usr/lib/jvm/java-{v}-openjdk-amd64"
        if os.path.exists(p): os.environ["JAVA_HOME"] = p; break

def adb(*args, serial=None):
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    return subprocess.run(cmd, capture_output=True, text=True)

def pick_device():
    r = subprocess.run(["adb", "devices"], capture_output=True, text=True)
    devs = [l.split('\t')[0] for l in r.stdout.strip().split('\n')[1:] if '\tdevice' in l]
    if len(devs) == 1: return devs[0]
    if not devs: sys.exit("No devices connected")
    for i, d in enumerate(devs): print(f"  {i}: {d}")
    return devs[int(input("Device #: "))]

def setup():
    os.chdir(DIR)
    open("local.properties", 'w').write(f"sdk.dir={SDK}\n")
    gp = open("gradle.properties").read()
    gp = re.sub(r'.*aapt2FromMavenOverride.*\n', '', gp)
    if IS_TERMUX: gp += "android.aapt2FromMavenOverride=/data/data/com.termux/files/usr/bin/aapt2\n"
    open("gradle.properties", 'w').write(gp)

def build():
    setup()
    subprocess.run(["./gradlew", "--no-configuration-cache", "assembleDebug"], check=True)
    apk = "app/build/outputs/apk/debug/app-debug.apk"
    if IS_TERMUX:
        dst = "/storage/emulated/0/Download/termuxbridge.apk"
        subprocess.run(["cp", apk, dst], check=True)
        subprocess.run(["am", "start", "-n", "com.example.installer/.MainActivity", "--es", "apk_path", dst])
    else:
        serial = sys.argv[1] if len(sys.argv) > 1 else pick_device()
        r = adb("install", "-r", apk, serial=serial)
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in (r.stdout + r.stderr):
            print("Signature mismatch, reinstalling...")
            adb("uninstall", PKG, serial=serial)
            r = adb("install", apk, serial=serial)
        if r.returncode: print(r.stderr); sys.exit(1)
        adb("shell", "am", "start", "-n", f"{PKG}/.MainActivity", serial=serial)
    print(f"✓ {PKG}")

if __name__ == "__main__":
    build()
