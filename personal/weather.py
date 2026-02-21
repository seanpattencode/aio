#!/usr/bin/env python3
import subprocess,shutil,os,sys
from base import send, save

def weather():
    try:
        gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
        r=subprocess.run([gemini,'-p','NYC weather in 10 words or less'],capture_output=True,text=True,timeout=60)
        return r.stdout.strip() if r.returncode==0 else f"weather unavailable (rc={r.returncode})"
    except Exception as e:return f"weather error: {e}"

if __name__=="__main__":
    w=weather()
    out=f"NYC: {w}"
    print(out)
    save("g-weather",out)
    if "--send" in sys.argv:
        subj=sys.argv[sys.argv.index("--send")+1] if len(sys.argv)>sys.argv.index("--send")+1 else "Weather Report (aio hub)"
        send(subj,f"NYC Weather: {w}")
