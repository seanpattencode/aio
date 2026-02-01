# Append-only: {time_ns}_{device}.txt = no conflicts. Push ours, reset to main.
import sys,time;from ._common import SYNC_ROOT,DEVICE_ID as D;from .sync import sync
def run():
    d,a=SYNC_ROOT/'common'/'tasks',sys.argv[2:];d.mkdir(exist_ok=True);sync('common');t=sorted(d.glob('*.txt'))
    if not a:[print(f"{i}. {f.read_text().strip()}")for i,f in enumerate(t,1)]+[print("\nd # to ack | https://github.com/seanpattencode/a-common/tree/main/tasks")]
    elif a[0]=='0':import subprocess;print("Analyzing...",flush=True);subprocess.run(['a','x.priority'])
    elif a[0]=='d':t[int(a[1])-1].unlink()
    else:s=' '.join(a);(d/f'{s[:20].replace(" ","-").lower()}_{time.strftime("%m%d%H%M")}.txt').write_text(s+'\n')
