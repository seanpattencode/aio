#!/usr/bin/env python3
import subprocess,shutil,os,re,sys
from base import send, save

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'-p','NYC air quality index now. Reply ONLY: <aqi>NUMBER</aqi><level>Good/Moderate/Unhealthy/etc</level><main>main pollutant</main>'],capture_output=True,text=True,timeout=120)
a,l,m=re.search(r'<aqi>(\d+)</aqi>',r.stdout),re.search(r'<level>(\w+)</level>',r.stdout),re.search(r'<main>([^<]+)</main>',r.stdout)
msg=f"AQI {a[1]} ({l[1]}) - {m[1].strip()}" if a and l and m else r.stdout.strip()
out=f"NYC: {msg}"
print(out)
save("g-aqi",out)
if "--send" in sys.argv: send("NYC AQI",msg)
