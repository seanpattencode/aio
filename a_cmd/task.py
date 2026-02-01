# Append-only: {time_ns}_{device}.txt = no conflicts. Push ours, reset to main.
import sys,time;from ._common import SYNC_ROOT,DEVICE_ID as D
def run():
    d,a=SYNC_ROOT/'tasks',sys.argv[2:];d.mkdir(exist_ok=True);t=sorted(d.glob('*.txt'))
    if a and a[0] in ('--time','-h','--help','h'):import os;os.execlp('t','t',a[0])
    if not a:
        for f in t:
            print(f"\n{f.read_text().strip()}\n");c=input("[d]el [n]ext [l]ist: ").strip().lower()
            if c=='d':f.unlink()
            elif c=='l':[print(f"{i}. {x.read_text().strip()}")for i,x in enumerate(t,1)];break
            elif c!='n':break
    elif a[0]=='0':import subprocess;print("Analyzing...",flush=True);subprocess.run(['a','x.priority'])
    elif a[0]=='d':t[int(a[1])-1].unlink()
    else:s=' '.join(a);(d/f'{s[:20].replace(" ","-").lower()}_{time.strftime("%m%d%H%M")}.txt').write_text(s+'\n')
