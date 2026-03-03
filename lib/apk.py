"""a apk"""
import os,subprocess as S,shutil,glob,sys
P="com.aios.a"
KT=r'''@file:Suppress("DEPRECATION","OVERRIDE_DEPRECATION")
package com.aios.a
import android.app.Activity;import android.content.*;import android.os.*;import android.webkit.*
private const val U="http://localhost:1111";private const val T="com.termux"
class M:Activity(){
private lateinit var w:WebView;private val h=Handler(Looper.getMainLooper());private var n=0
private fun tx(){try{startForegroundService(Intent().apply{setClassName(T,"$T.app.RunCommandService");action="$T.RUN_COMMAND";putExtra("$T.RUN_COMMAND_PATH","/data/data/$T/files/usr/bin/bash");putExtra("$T.RUN_COMMAND_ARGUMENTS",arrayOf("-l","-c","a ui on"));putExtra("$T.RUN_COMMAND_BACKGROUND",true)})}catch(_:Exception){}}
private fun pg(s:String)=w.loadDataWithBaseURL(null,"<body style='font:18px monospace;padding:20px;background:#000;color:#0f0'>$s","text/html","utf-8",null)
@JavascriptInterface fun copy(){(getSystemService(CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("","a ui on"))}
@JavascriptInterface fun termux(){try{startActivity(Intent().apply{setClassName(T,"$T.app.TermuxActivity");addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)})}catch(_:Exception){}}
@JavascriptInterface fun retry(){h.post{boot()}}
override fun onResume(){super.onResume();boot()}
private fun boot(){if(checkSelfPermission("$T.permission.RUN_COMMAND")!=0){pg("<h2>Permission needed</h2>Settings→Apps→a→enable Run commands in Termux<br><br>In Termux:<br><code style='color:#ff0'>echo 'allow-external-apps=true'>>~/.termux/termux.properties</code><br>Reopen app");return};tx();n=0;w.loadUrl(U)}
override fun onCreate(b:Bundle?){super.onCreate(b)
w=WebView(this).apply{settings.javaScriptEnabled=true;addJavascriptInterface(this@M,"A")
webViewClient=object:WebViewClient(){override fun onReceivedError(v:WebView,r:WebResourceRequest,e:WebResourceError){if(r.isForMainFrame){if(n++<10){pg("<h2>Starting...</h2>attempt $n/10");if(n%3==0)tx();h.postDelayed({v.loadUrl(U)},2000)}else pg("<h2>Not responding</h2><button onclick='A.copy()'>Copy: a ui on</button> <button onclick='A.termux()'>Open Termux</button><br><br><button onclick='A.retry()'>Retry</button>")}}}};setContentView(w)}}
'''
MF='<manifest xmlns:android="http://schemas.android.com/apk/res/android"><uses-permission android:name="android.permission.INTERNET"/><uses-permission android:name="com.termux.permission.RUN_COMMAND"/><application android:usesCleartextTraffic="true" android:label="a"><activity android:name=".M" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>'
GS='pluginManagement{repositories{google();mavenCentral()};plugins{id("com.android.application") version "8.2.0";id("org.jetbrains.kotlin.android") version "1.9.22"}}\ndependencyResolutionManagement{repositories{google();mavenCentral()}}\ninclude(":app")\n'
GB=f'plugins{{id("com.android.application");id("org.jetbrains.kotlin.android")}}\nandroid{{namespace="{P}";compileSdk=34;defaultConfig{{applicationId="{P}";minSdk=24;targetSdk=34}}\ncompileOptions{{sourceCompatibility=JavaVersion.VERSION_11;targetCompatibility=JavaVersion.VERSION_11}}\nkotlinOptions{{jvmTarget="11"}}}}\n'
H=os.path.expanduser("~");IT=os.path.exists("/data/data/com.termux")
SDK="/data/data/com.termux/files/home/android-sdk" if IT else os.environ.get("ANDROID_HOME",H+"/Android/Sdk")
R=os.path.dirname(os.path.dirname(os.path.abspath(__file__)));D=R+"/adata/_apk_build"
if not IT:
    for v in ["21","17"]:
        p=f"/usr/lib/jvm/java-{v}-openjdk-amd64"
        if os.path.exists(p):os.environ["JAVA_HOME"]=p;break
def w(p,s):os.makedirs(os.path.dirname(p),exist_ok=True);open(p,"w").write(s)
def adb(*a,serial=None):return S.run(["adb"]+(["-s",serial] if serial else [])+list(a),capture_output=True,text=True)
def run():
    w(D+"/settings.gradle.kts",GS);w(D+"/app/build.gradle.kts",GB);w(D+"/local.properties",f"sdk.dir={SDK}\n")
    gp="android.useAndroidX=true\norg.gradle.jvmargs=-Xmx4g\n"
    if IT:gp+="android.aapt2FromMavenOverride=/data/data/com.termux/files/usr/bin/aapt2\n"
    w(D+"/gradle.properties",gp);w(D+"/app/src/main/AndroidManifest.xml",MF);w(D+"/app/src/main/java/com/aios/a/M.kt",KT)
    if not os.path.exists(D+"/gradlew"):
        for s in [R+"/lab/android/A",*glob.glob(H+"/projects/androidDev/apks/*")]:
            if os.path.exists(s+"/gradlew"):
                shutil.copy(s+"/gradlew",D+"/gradlew");os.chmod(D+"/gradlew",0o755)
                wd=s+"/gradle/wrapper";os.makedirs(D+"/gradle/wrapper",exist_ok=True)
                for f in os.listdir(wd):shutil.copy(wd+"/"+f,D+"/gradle/wrapper/")
                break
        else:sys.exit("x No gradlew")
    os.chdir(D);S.run(["./gradlew","--no-configuration-cache","assembleDebug"],check=True)
    apk="app/build/outputs/apk/debug/app-debug.apk"
    if IT:
        S.run(["cp",apk,"/storage/emulated/0/Download/a.apk"],check=True);S.run(["am","start","-n","com.example.installer/.MainActivity","--es","apk_path","/storage/emulated/0/Download/a.apk"])
    else:
        serial=sys.argv[2] if len(sys.argv)>2 and sys.argv[2]!="apk" else None
        if not serial:
            devs=[l.split('\t')[0] for l in adb("devices").stdout.strip().split('\n')[1:] if '\tdevice' in l]
            if not devs:sys.exit("No devices")
            if len(devs)==1:serial=devs[0]
            else:
                for i,d in enumerate(devs):print(f"  {i}: {adb('-s',d,'shell','getprop','ro.product.model').stdout.strip() or d} ({d})")
                serial=devs[int(input("#: "))]
        r=adb("install","-r",apk,serial=serial)
        if "INSTALL_FAILED" in r.stdout+r.stderr:print("Reinstalling...");adb("uninstall",P,serial=serial);r=adb("install",apk,serial=serial)
        if r.returncode:print(r.stderr);sys.exit(1)
        adb("shell","am","start","-n",P+"/.M",serial=serial)
    print("✓ "+P)
run()
