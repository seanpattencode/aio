"""a apk - Build+install minimal localhost:1111 WebView APK"""
import os,subprocess as S,shutil,glob,sys

PKG="com.a.ui"
KT='''package com.a.ui
import android.app.Activity
import android.os.Bundle
import android.webkit.*
@Suppress("DEPRECATION")
class M:Activity(){override fun onCreate(b:Bundle?){super.onCreate(b)
window.decorView.systemUiVisibility=0x706
setContentView(WebView(this).apply{settings.javaScriptEnabled=true;settings.domStorageEnabled=true;webViewClient=WebViewClient();loadUrl("http://localhost:1111")})}}
'''
MANIFEST='''<manifest xmlns:android="http://schemas.android.com/apk/res/android">
<uses-permission android:name="android.permission.INTERNET"/>
<application android:label="a apk" android:usesCleartextTraffic="true">
<activity android:name=".M" android:exported="true" android:theme="@android:style/Theme.Black.NoTitleBar.Fullscreen">
<intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter>
</activity></application></manifest>
'''
SETTINGS='pluginManagement{repositories{google();mavenCentral()};plugins{id("com.android.application") version "8.2.0";id("org.jetbrains.kotlin.android") version "1.9.21"}}\ndependencyResolutionManagement{repositories{google();mavenCentral()}}\ninclude(":app")\n'
BUILD=f'plugins{{id("com.android.application");id("org.jetbrains.kotlin.android")}}\nandroid{{namespace="{PKG}";compileSdk=34;defaultConfig{{applicationId="{PKG}";minSdk=21;targetSdk=34}}\ncompileOptions{{sourceCompatibility=JavaVersion.VERSION_17;targetCompatibility=JavaVersion.VERSION_17}}\nkotlinOptions{{jvmTarget="17"}}}}\n'

H=os.path.expanduser("~")
IS_T=os.path.exists("/data/data/com.termux")
SDK="/data/data/com.termux/files/home/android-sdk" if IS_T else os.environ.get("ANDROID_HOME",H+"/Android/Sdk")
if not IS_T and os.path.exists("/usr/lib/jvm/java-21-openjdk-amd64"):os.environ["JAVA_HOME"]="/usr/lib/jvm/java-21-openjdk-amd64"
D=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"adata","_apk_build")

def w(p,s):os.makedirs(os.path.dirname(p),exist_ok=True);open(p,"w").write(s)

def run():
    w(f"{D}/settings.gradle.kts",SETTINGS)
    w(f"{D}/app/build.gradle.kts",BUILD)
    w(f"{D}/local.properties",f"sdk.dir={SDK}\n")
    gp="android.useAndroidX=true\norg.gradle.jvmargs=-Xmx2048m\n"
    if IS_T:gp+="android.aapt2FromMavenOverride=/data/data/com.termux/files/usr/bin/aapt2\n"
    w(f"{D}/gradle.properties",gp)
    w(f"{D}/app/src/main/AndroidManifest.xml",MANIFEST)
    w(f"{D}/app/src/main/java/com/a/ui/M.kt",KT)
    # gradle wrapper from any sibling android project
    if not os.path.exists(f"{D}/gradlew"):
        for g in glob.glob(H+"/projects/androidDev/apks/*/gradlew"):
            shutil.copy(g,f"{D}/gradlew");os.chmod(f"{D}/gradlew",0o755)
            wd=os.path.join(os.path.dirname(g),"gradle/wrapper")
            os.makedirs(f"{D}/gradle/wrapper",exist_ok=True)
            for f in os.listdir(wd):shutil.copy(os.path.join(wd,f),f"{D}/gradle/wrapper/")
            break
        else:print("x No gradlew found in ~/projects/androidDev/apks/");sys.exit(1)
    os.chdir(D)
    S.run(["./gradlew","--no-configuration-cache","assembleDebug"],check=True)
    apk="app/build/outputs/apk/debug/app-debug.apk"
    if IS_T:
        dst="/storage/emulated/0/Download/a-ui.apk"
        S.run(["cp",apk,dst]);S.run(["am","start","-n","com.example.installer/.MainActivity","--es","apk_path",dst])
    else:
        dev=next((l.split()[0] for l in S.check_output(["adb","devices"]).decode().splitlines()[1:] if "device" in l.split()[-1:]),None)
        S.run(["adb"]+(["-s",dev] if dev else [])+["install","-r",apk],check=True)
    print("✓ a-ui.apk")
run()
