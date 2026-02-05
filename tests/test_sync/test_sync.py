import subprocess as sp, time, shlex, random
from pathlib import Path

ROOT, DEVICES = Path(__file__).parent / 'devices', ('device_a', 'device_b', 'device_c')

def q(p): return shlex.quote(str(p))

def setup(): sp.run(f'rm -rf {q(ROOT)} && mkdir -p {q(ROOT/"origin")} && git -C {q(ROOT/"origin")} init -q -b main --bare', shell=True); [sp.run(f'mkdir -p {q(ROOT/d)} && git -C {q(ROOT/d)} init -q -b main && git -C {q(ROOT/d)} remote add origin {q(ROOT/"origin")}', shell=True) for d in DEVICES]

def _sync(d, silent=False):
    """Sync with conflict detection. Returns (success, conflict_detected)"""
    r = sp.run(f'cd {q(d)} && git add -A && git commit -qm sync && git pull -q --no-rebase origin main && git push -q origin main', shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr + r.stdout).lower()
        if 'conflict' in err or 'diverged' in err or 'rejected' in err:
            if not silent:
                print(f"""
! Sync conflict (this shouldn't happen with append-only)

If you're SURE this device has the latest data:
  cd {d} && git add -A && git commit -m fix && git push --force

If unsure, ask AI:
  a c "help me resolve sync conflict in {d}"

Error: {(r.stderr + r.stdout)[:200]}
""")
            return False, True
        return False, False
    return True, False

def create_file(device, name, content=''): ts=time.strftime('%Y%m%dT%H%M%S')+f'.{time.time_ns()%1000000000:09d}'; p=ROOT/device/f'{name}_{ts}.txt'; p.write_text(content or f'created by {device}'); sp.run(f'cd {q(ROOT/device)} && git add -A && git commit -qm "add {p.name}" && git push -u origin main', shell=True); return p.name

def pull(device): sp.run(f'cd {q(ROOT/device)} && git pull -q origin main', shell=True)

def run_n(n): [(pull(d), create_file(d, f'note{i}'), [pull(x) for x in DEVICES]) for i in range(n) for d in DEVICES]; return {d: len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}

def sync(device, silent=False):
    ts=time.strftime('%Y%m%dT%H%M%S')+f'.{time.time_ns()%1000000000:09d}'
    [p.rename(p.with_name(f'{p.stem}_{ts}{p.suffix}')) for p in (ROOT/device).glob('*.txt') if '_20' not in p.stem]
    pull(device)
    return _sync(ROOT/device, silent=silent)

def test_raw(n): [((ROOT/d/'samename.txt').write_text(f'v{i} {d}'), sync(d), [pull(x) for x in DEVICES]) for i in range(n) for d in DEVICES]; return {d: len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}

def sync_edit(device, silent=False):
    ts=time.strftime('%Y%m%dT%H%M%S')+f'.{time.time_ns()%1000000000:09d}'
    arc=(ROOT/device/'.archive'); arc.mkdir(exist_ok=True)
    [((arc/p.name).write_text(sp.run(f'git -C {q(ROOT/device)} show HEAD:{p.name}',shell=True,capture_output=True,text=True).stdout), p.rename(p.with_name(f'{p.stem.rsplit("_",1)[0]}_{ts}{p.suffix}'))) for p in (ROOT/device).glob('*.txt') if sp.run(f'git -C {q(ROOT/device)} diff --quiet {p.name}',shell=True).returncode]
    pull(device)
    return _sync(ROOT/device, silent=silent)

def test_edit(n): setup(); f=create_file('device_a','doc'); [pull(d) for d in DEVICES]; [((ROOT/d/f).write_text(f'edit{i} {d}'), sync_edit(d), [pull(x) for x in DEVICES]) for i in range(n) for d in DEVICES]; return {'files':{d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES},'archive':{d:len(list((ROOT/d/'.archive').glob('*.txt'))) for d in DEVICES}}

def delete(device, name): [(p.unlink()) for p in (ROOT/device).glob(f'{name}*.txt')]; pull(device); sp.run(f'cd {q(ROOT/device)} && git add -A && git commit -qm "delete {name}" && git push origin main', shell=True)

def test_delete(): setup(); f=create_file('device_a','todelete'); [pull(d) for d in DEVICES]; before={d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}; delete('device_a','todelete'); [pull(d) for d in DEVICES]; after={d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES}; return {'before':before,'after':after}

def archive(device, name): arc=(ROOT/device/'.archive'); arc.mkdir(exist_ok=True); [p.rename(arc/p.name) for p in (ROOT/device).glob(f'{name}*.txt')]; pull(device); sp.run(f'cd {q(ROOT/device)} && git add -A && git commit -qm "archive {name}" && git push origin main', shell=True)

def test_archive(): setup(); f=create_file('device_a','toarchive'); [pull(d) for d in DEVICES]; archive('device_a','toarchive'); [pull(d) for d in DEVICES]; return {'files':{d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES},'archived':{d:len(list((ROOT/d/'.archive').glob('*.txt'))) for d in DEVICES}}

def test_offline(): setup(); f1,f2,f3,f4=[create_file('device_a',n) for n in ('toadd','todelete','toarchive','toedit')]; [pull(d) for d in DEVICES]; [(create_file('device_b',f'online{i}'), pull('device_b')) for i in range(2)]; pull('device_c'); (ROOT/'device_c'/'newfile.txt').write_text('add'); (ROOT/'device_c'/f2).unlink(); (ROOT/'device_c'/'.archive').mkdir(exist_ok=True); (ROOT/'device_c'/f3).rename(ROOT/'device_c'/'.archive'/f3); (ROOT/'device_c'/f4).write_text('edited'); sync_edit('device_c'); [pull(d) for d in DEVICES]; return {'files':{d:len(list((ROOT/d).glob('*.txt'))) for d in DEVICES},'archive':{d:len(list((ROOT/d/'.archive').glob('*.txt'))) for d in DEVICES}}

def monte_carlo(n=1000, verbose=False):
    setup(); create_file('device_a','seed'); [pull(d) for d in DEVICES]
    # Create nested folder on all devices
    for d in DEVICES: (ROOT/d/'nested').mkdir(exist_ok=True); sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "mkdir" && git push origin main', shell=True, capture_output=True)
    [pull(d) for d in DEVICES]
    online={d:True for d in DEVICES}; errors=[]; conflicts=[]; reseeds=0
    ops=['add','delete','archive','edit','toggle','same_name','edit_raw','nested','non_txt','direct_push']

    for i in range(n):
        d=random.choice(DEVICES); op=random.choice(ops)
        if op=='toggle': online[d]=not online[d]; continue
        if not online[d]: continue

        try:
            pull(d); files=list((ROOT/d).glob('*.txt'))

            # Handle edge case: all files deleted, add one back
            if not files:
                if verbose: print(f"  [{i}] All files deleted on {d}, reseeding...")
                (ROOT/d/f'reseed_{i}.txt').write_text(f'reseed {i}')
                sync(d, silent=True)
                reseeds += 1
                continue

            if op=='add':
                (ROOT/d/f'f{i}.txt').write_text(f'{i}')
                ok, conflict = sync(d, silent=True)
                if conflict: conflicts.append((i, d, 'add'))
            elif op=='delete' and files:
                random.choice(files).unlink()
                r = sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "del" && git push origin main', shell=True, capture_output=True, text=True)
                if r.returncode and ('conflict' in r.stderr.lower() or 'rejected' in r.stderr.lower()):
                    conflicts.append((i, d, 'delete'))
            elif op=='archive' and files:
                (ROOT/d/'.archive').mkdir(exist_ok=True)
                f=random.choice(files); f.rename(ROOT/d/'.archive'/f.name)
                r = sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "arc" && git push origin main', shell=True, capture_output=True, text=True)
                if r.returncode and ('conflict' in r.stderr.lower() or 'rejected' in r.stderr.lower()):
                    conflicts.append((i, d, 'archive'))
            elif op=='edit' and files:
                random.choice(files).write_text(f'edit{i}')
                ok, conflict = sync_edit(d, silent=True)
                if conflict: conflicts.append((i, d, 'edit'))
            # NEW: same filename no timestamp on 2 devices
            elif op=='same_name':
                (ROOT/d/'collision.txt').write_text(f'{d}_{i}')
                ok, conflict = sync(d, silent=True)
                if conflict: conflicts.append((i, d, 'same_name'))
            # NEW: edit without sync_edit (raw edit = conflict)
            elif op=='edit_raw' and files:
                random.choice(files).write_text(f'raw{i}')
                r = sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "raw" && git push origin main', shell=True, capture_output=True, text=True)
                if r.returncode and ('conflict' in r.stderr.lower() or 'rejected' in r.stderr.lower()):
                    conflicts.append((i, d, 'edit_raw'))
            # NEW: nested folder files
            elif op=='nested':
                (ROOT/d/'nested'/f'n{i}.txt').write_text(f'{i}')
                ok, conflict = sync(d, silent=True)
                if conflict: conflicts.append((i, d, 'nested'))
            # NEW: non-txt files
            elif op=='non_txt':
                ext = random.choice(['.json','.md','.yaml'])
                (ROOT/d/f'file{i}{ext}').write_text(f'{i}')
                r = sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "non-txt" && git push origin main', shell=True, capture_output=True, text=True)
                if r.returncode and ('conflict' in r.stderr.lower() or 'rejected' in r.stderr.lower()):
                    conflicts.append((i, d, 'non_txt'))
            # NEW: direct git push bypassing sync
            elif op=='direct_push':
                (ROOT/d/f'direct{i}.txt').write_text(f'{i}')
                r = sp.run(f'cd {q(ROOT/d)} && git add -A && git commit -qm "direct" && git push origin main', shell=True, capture_output=True, text=True)
                if r.returncode and ('conflict' in r.stderr.lower() or 'rejected' in r.stderr.lower()):
                    conflicts.append((i, d, 'direct_push'))

        except Exception as e: errors.append((i,d,op,str(e)))

    [pull(d) for d in DEVICES]
    counts={d:(len(list((ROOT/d).glob('*.txt'))),len(list((ROOT/d/'.archive').glob('*.txt')))if(ROOT/d/'.archive').exists()else 0,len(list((ROOT/d/'nested').glob('*.txt')))if(ROOT/d/'nested').exists()else 0,len(list((ROOT/d).glob('*.json'))+list((ROOT/d).glob('*.md'))+list((ROOT/d).glob('*.yaml')))) for d in DEVICES}
    by_op={op:len([c for c in conflicts if c[2]==op]) for op in ops}

    return {
        'actions': n,
        'errors': len(errors),
        'conflicts': len(conflicts),
        'by_op': {k:v for k,v in by_op.items() if v},
        'conflict_details': conflicts[:10] if conflicts else [],
        'reseeds': reseeds,
        'counts': counts,
        'match': len(set(c[:2] for c in counts.values()))==1  # compare txt+archive only
    }

def test_old_no_ts(): setup(); (ROOT/'device_a'/'note.txt').write_text('old no ts'); create_file('device_b','note'); [pull(d) for d in DEVICES if d!='device_a']; sync('device_a'); [pull(d) for d in DEVICES]; return {d:[p.name for p in (ROOT/d).glob('*.txt')] for d in DEVICES}

if __name__ == '__main__': print(test_old_no_ts())
