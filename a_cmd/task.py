# Append-only: {time_ns}_{device}.txt = no conflicts. Push ours, reset to main.
import sys,time;from ._common import SYNC_ROOT,DEVICE_ID as D
def run():
    d,a=SYNC_ROOT/'tasks',sys.argv[2:];d.mkdir(exist_ok=True);t=sorted(d.glob('*.txt'))
    if a and a[0] in ('t','--time','-h','--help','h'):import os;os.execlp('t','t',*a[1:])
    if not a:print(f"""t            review one-by-one (3ms)
a task l     list all
a task d #   delete task #
a task <txt> add task
{len(t)} tasks | https://github.com/seanpattencode/a-tasks""")
    elif a[0]in('l','ls','list'):[print(f"{i}. {f.read_text().strip()}")for i,f in enumerate(t,1)]
    elif a[0]=='0':import subprocess;print("Analyzing...",flush=True);subprocess.run(['a','x.priority'])
    elif a[0]=='d':t[int(a[1])-1].unlink()
    else:s=' '.join(a);(d/f'{s[:20].replace(" ","-").lower()}_{time.strftime("%m%d%H%M")}.txt').write_text(s+'\n')
