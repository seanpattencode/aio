# Append-only: {time_ns}_{device}.txt = no conflicts. Push ours, reset to main.
import sys,time;from ._common import SYNC_ROOT,DEVICE_ID as D
def run():
    d,a=SYNC_ROOT/'tasks',sys.argv[2:];d.mkdir(exist_ok=True);t=sorted(d.glob('*.txt'),key=lambda f:f.stat().st_mtime)
    if not a:print("a task t     review one-by-one\na task l     list\na task 0     AI pick #1\na task d #   delete\na task <txt> add");return
    if a[0] in ('t','--time','-h','--help','h'):import os;os.execlp('t','t',*(a[1:]if a[0]=='t'else a))
    if a[0]in('l','ls','list'):[print(f"{i}. {f.read_text().strip()}")for i,f in enumerate(t,1)]
    elif a[0]=='0':import subprocess;subprocess.run(['a','x.priority'])
    elif a[0]=='d':t[int(a[1])-1].unlink()
    else:s=' '.join(a);(d/f'{s[:20].replace(" ","-").lower()}_{time.strftime("%m%d%H%M")}.txt').write_text(s+'\n')
