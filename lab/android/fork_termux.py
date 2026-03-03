#!/usr/bin/env python3
"""Fork Termux, build, install to device. Self-installs SDK deps.
  python fork_termux.py          # clone + build + adb install
  python fork_termux.py build    # rebuild + adb install (skip clone)
"""
import subprocess, os, sys, re, zipfile, urllib.request, shutil

SDK = os.environ.get("ANDROID_HOME", os.path.expanduser("~/Android/Sdk"))
NDK_VER = "29.0.14206865"
SDKM = f"{SDK}/cmdline-tools/latest/bin/sdkmanager"
APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "a-app")
# different applicationId so fork installs alongside stock Termux
PKG = "com.aios.a"
# keep com.termux internally — bootstrap binaries have hardcoded /data/data/com.termux paths
TERMUX_PKG = "com.termux"

def run(*a, **kw): subprocess.run(a, check=True, **kw)

def ensure_sdk():
    if not os.path.isfile(SDKM):
        print("Installing cmdline-tools...")
        z = "/tmp/cmdline-tools.zip"
        urllib.request.urlretrieve("https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip", z)
        with zipfile.ZipFile(z) as f: f.extractall("/tmp/ct")
        dest = f"{SDK}/cmdline-tools/latest"
        if os.path.exists(dest): shutil.rmtree(dest)
        shutil.move("/tmp/ct/cmdline-tools", dest)
        os.remove(z); shutil.rmtree("/tmp/ct", ignore_errors=True)
    if not os.path.isfile(f"{SDK}/ndk/{NDK_VER}/source.properties"):
        print(f"Installing NDK {NDK_VER}...")
        shutil.rmtree(f"{SDK}/ndk/{NDK_VER}", ignore_errors=True)
        run(SDKM, f"--sdk_root={SDK}", f"ndk;{NDK_VER}", input=b"y\ny\ny\n")

def clone():
    if os.path.isdir(APP): return
    run("git", "clone", "--depth=1", "https://github.com/termux/termux-app", APP)

def rebrand():
    """Change applicationId + app name. Keep TERMUX_PACKAGE_NAME as com.termux
    because bootstrap binaries have hardcoded /data/data/com.termux paths.
    We symlink our data dir to com.termux at runtime instead."""
    bg = f"{APP}/app/build.gradle"
    c = open(bg).read()
    # add applicationId if missing (Termux defaults to namespace)
    if "applicationId" not in c:
        c = c.replace("versionCode 118", f'applicationId "{PKG}"\n        versionCode 118')
    else:
        c = re.sub(r'applicationId\s+"[^"]+"', f'applicationId "{PKG}"', c)
    # rename app in launcher (manifest placeholder)
    c = re.sub(r'(TERMUX_APP_NAME\s*=\s*)"[^"]+"', r'\1"aio"', c)
    # change manifest TERMUX_PACKAGE_NAME so permissions don't conflict with stock Termux
    c = re.sub(r'(TERMUX_PACKAGE_NAME\s*=\s*)"[^"]+"', f'\\1"{PKG}"', c)
    open(bg, 'w').write(c)
    # patch strings.xml XML entities — this is where the launcher label actually comes from
    sx = f"{APP}/app/src/main/res/values/strings.xml"
    s = open(sx).read()
    s = re.sub(r'(ENTITY TERMUX_APP_NAME )"[^"]+"', r'\1"aio"', s)
    open(sx, 'w').write(s)
    tc = f"{APP}/termux-shared/src/main/java/com/termux/shared/termux/TermuxConstants.java"
    j = open(tc).read()
    j = re.sub(r'(TERMUX_APP_NAME\s*=\s*)"Termux"', r'\1"aio"', j)
    open(tc, 'w').write(j)
    # fix context lookup: use runtime package name instead of hardcoded TERMUX_PACKAGE_NAME
    # so getTermuxPackageContext works when applicationId differs from com.termux
    tu = f"{APP}/termux-shared/src/main/java/com/termux/shared/termux/TermuxUtils.java"
    u = open(tu).read()
    u = u.replace(
        "return PackageUtils.getContextForPackage(context, TermuxConstants.TERMUX_PACKAGE_NAME);",
        "return PackageUtils.getContextForPackage(context, context.getPackageName());")
    u = u.replace(
        "return PackageUtils.getContextForPackage(context, TermuxConstants.TERMUX_PACKAGE_NAME, Context.CONTEXT_INCLUDE_CODE);",
        "return PackageUtils.getContextForPackage(context, context.getPackageName(), Context.CONTEXT_INCLUDE_CODE);")
    open(tu, 'w').write(u)

def setup_symlink():
    """Create symlink /data/data/com.termux -> /data/data/com.aios.a so bootstrap paths work."""
    # symlink from inside the app's own data dir
    run("adb", "shell", f"run-as {PKG} sh -c '"
        f'[ ! -e /data/data/{TERMUX_PKG} ] && ln -s /data/data/{PKG} /data/data/{TERMUX_PKG} || true'
        "'")

def build():
    os.environ["ANDROID_HOME"] = SDK
    os.environ["TERMUX_SPLIT_APKS_FOR_DEBUG_BUILDS"] = "0"
    open(f"{APP}/local.properties", 'w').write(f"sdk.dir={SDK}\n")
    rebrand()
    run("./gradlew", "assembleDebug", cwd=APP)
    apk = f"{APP}/app/build/outputs/apk/debug/termux-app_apt-android-7-debug_universal.apk"
    run("adb", "install", "-r", apk)
    # launch once so Android clears stopped state and shows in launcher
    run("adb", "shell", "am", "start", "-n", f"{PKG}/com.termux.app.TermuxActivity")
    print("Done.")

if __name__ == "__main__":
    ensure_sdk()
    if not (len(sys.argv) > 1 and sys.argv[1] == "build"):
        clone()
    build()
