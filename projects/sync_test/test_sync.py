import subprocess as sp, time
from pathlib import Path

ROOT, DEVICES = Path(__file__).parent / 'devices', ('device_a', 'device_b', 'device_c')

def setup(): sp.run(f'rm -rf {ROOT} && mkdir -p {ROOT/"origin"} && git -C {ROOT/"origin"} init -q -b main --bare', shell=True); [sp.run(f'mkdir -p {ROOT/d} && git -C {ROOT/d} init -q -b main && git -C {ROOT/d} remote add origin {ROOT/"origin"}', shell=True) for d in DEVICES]

def create_file(device, name, content=''): ts=time.strftime('%Y%m%dT%H%M%S')+f'.{time.time_ns()%1000000000:09d}'; p=ROOT/device/f'{name}_{ts}.txt'; p.write_text(content or f'created by {device}'); sp.run(f'cd {ROOT/device} && git add -A && git commit -qm "add {p.name}" && git push -u origin main', shell=True); return p.name

def pull(device): sp.run(f'cd {ROOT/device} && git pull -q origin main', shell=True)

def run_n(n): [(pull(d), create_file(d, f'note{i}'), [pull(x) for x in DEVICES]) for i in range(n) for d in DEVICES]; return {d: len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}

def sync(device): ts=time.strftime('%Y%m%dT%H%M%S')+f'.{time.time_ns()%1000000000:09d}'; [p.rename(p.with_name(f'{p.stem}_{ts}{p.suffix}')) for p in (ROOT/device).glob('*.txt') if '_20' not in p.stem]; pull(device); sp.run(f'cd {ROOT/device} && git add -A && git commit -qm "sync" && git push origin main', shell=True)

def test_raw(n): [((ROOT/d/'samename.txt').write_text(f'v{i} {d}'), sync(d), [pull(x) for x in DEVICES]) for i in range(n) for d in DEVICES]; return {d: len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}

def sync_edit(device): ts=time.strftime('%Y%m%dT%H%M%S')+f'.{time.time_ns()%1000000000:09d}'; arc=(ROOT/device/'.archive'); arc.mkdir(exist_ok=True); [((arc/p.name).write_text(sp.run(f'git -C {ROOT/device} show HEAD:{p.name}',shell=True,capture_output=True,text=True).stdout), p.rename(p.with_name(f'{p.stem.rsplit("_",1)[0]}_{ts}{p.suffix}'))) for p in (ROOT/device).glob('*.txt') if sp.run(f'git -C {ROOT/device} diff --quiet {p.name}',shell=True).returncode]; pull(device); sp.run(f'cd {ROOT/device} && git add -A && git commit -qm "sync" && git push origin main',shell=True)

def test_edit(n): setup(); f=create_file('device_a','doc'); [pull(d) for d in DEVICES]; [((ROOT/d/f).write_text(f'edit{i} {d}'), sync_edit(d), [pull(x) for x in DEVICES]) for i in range(n) for d in DEVICES]; return {'files':{d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES},'archive':{d:len(list((ROOT/d/'.archive').glob('*.txt'))) for d in DEVICES}}

def delete(device, name): [(p.unlink()) for p in (ROOT/device).glob(f'{name}*.txt')]; pull(device); sp.run(f'cd {ROOT/device} && git add -A && git commit -qm "delete {name}" && git push origin main', shell=True)

def test_delete(): setup(); f=create_file('device_a','todelete'); [pull(d) for d in DEVICES]; before={d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}; delete('device_a','todelete'); [pull(d) for d in DEVICES]; after={d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}; return {'before':before,'after':after}

def archive(device, name): arc=(ROOT/device/'.archive'); arc.mkdir(exist_ok=True); [p.rename(arc/p.name) for p in (ROOT/device).glob(f'{name}*.txt')]; pull(device); sp.run(f'cd {ROOT/device} && git add -A && git commit -qm "archive {name}" && git push origin main', shell=True)

def test_archive(): setup(); f=create_file('device_a','toarchive'); [pull(d) for d in DEVICES]; archive('device_a','toarchive'); [pull(d) for d in DEVICES]; return {'files':{d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES},'archived':{d:len(list((ROOT/d/'.archive').glob('*.txt'))) for d in DEVICES}}

def test_offline(): setup(); f1,f2,f3,f4=[create_file('device_a',n) for n in ('toadd','todelete','toarchive','toedit')]; [pull(d) for d in DEVICES]; [(create_file('device_b',f'online{i}'), pull('device_b')) for i in range(2)]; pull('device_c'); (ROOT/'device_c'/'newfile.txt').write_text('add'); (ROOT/'device_c'/f2).unlink(); (ROOT/'device_c'/'.archive').mkdir(exist_ok=True); (ROOT/'device_c'/f3).rename(ROOT/'device_c'/'.archive'/f3); (ROOT/'device_c'/f4).write_text('edited'); sync_edit('device_c'); [pull(d) for d in DEVICES]; return {'files':{d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES},'archive':{d:len(list((ROOT/d/'.archive').glob('*.txt'))) for d in DEVICES}}

import random
def monte_carlo(n=1000):
    setup(); create_file('device_a','seed'); [pull(d) for d in DEVICES]; online={d:True for d in DEVICES}; errors=[]
    for i in range(n):
        d=random.choice(DEVICES); op=random.choice(['add','delete','archive','edit','toggle'])
        if op=='toggle': online[d]=not online[d]; continue
        if not online[d]: continue
        try:
            pull(d); files=list((ROOT/d).glob('*.txt'))
            if op=='add': (ROOT/d/f'f{i}.txt').write_text(f'{i}'); sync(d)
            elif op=='delete' and files: random.choice(files).unlink(); sp.run(f'cd {ROOT/d} && git add -A && git commit -qm "del" && git push origin main',shell=True)
            elif op=='archive' and files: (ROOT/d/'.archive').mkdir(exist_ok=True); f=random.choice(files); f.rename(ROOT/d/'.archive'/f.name); sp.run(f'cd {ROOT/d} && git add -A && git commit -qm "arc" && git push origin main',shell=True)
            elif op=='edit' and files: random.choice(files).write_text(f'edit{i}'); sync_edit(d)
        except Exception as e: errors.append((i,d,op,str(e)))
    [pull(d) for d in DEVICES]; counts={d:(len(list((ROOT/d).glob('*.txt'))),len(list((ROOT/d/'.archive').glob('*.txt')))if(ROOT/d/'.archive').exists()else 0) for d in DEVICES}
    return {'actions':n,'errors':len(errors),'counts':counts,'match':len(set(counts.values()))==1}

def test_old_no_ts(): setup(); (ROOT/'device_a'/'note.txt').write_text('old no ts'); create_file('device_b','note'); [pull(d) for d in DEVICES if d!='device_a']; sync('device_a'); [pull(d) for d in DEVICES]; return {d:[p.name for p in (ROOT/d).glob('*.txt')] for d in DEVICES}

if __name__ == '__main__': print(test_old_no_ts())
