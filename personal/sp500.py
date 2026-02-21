#!/usr/bin/env python3
import subprocess,shutil,os,re,sys
from base import send, save

gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
r=subprocess.run([gemini,'-p','S&P 500 prediction for today. Search news/sentiment. Reply ONLY: <dir>UP or DOWN</dir><pct>NUMBER</pct><conf>LOW/MED/HIGH</conf><why>10 words max</why>'],capture_output=True,text=True,timeout=120)
d,p,c,w=re.search(r'<dir>(\w+)</dir>',r.stdout),re.search(r'<pct>([\d.]+)%?</pct>',r.stdout),re.search(r'<conf>(\w+)</conf>',r.stdout),re.search(r'<why>([^<]+)</why>',r.stdout)
pred=f"{d[1]} {p[1]}% ({c[1]}) - {w[1].strip()}" if d and p and c and w else r.stdout.strip()
out=f"S&P: {pred}"
print(out)
save("g-sp500",out)
if "--send" in sys.argv: send("S&P 500 Prediction",pred)
