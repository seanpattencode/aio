#!/usr/bin/env python3
"""Test sync: local <-> termux <-> hsu"""
import subprocess as sp, sys, time, json, os
from concurrent.futures import ThreadPoolExecutor as Pool

DATA, EF = os.path.expanduser("~/.local/share/aios"), os.path.expanduser("~/.local/share/aios/events.jsonl")
R = "~/.local/share/aios"

def loc(c): return sp.run(c, shell=True, capture_output=True, text=True).stdout.strip()
def ssh(h,c): return sp.run(['aio','ssh',h,c], capture_output=True, text=True).stdout.strip()
def pull(h=None): (ssh(h,f'cd {R} && git fetch -q && git reset --hard origin/main') if h else loc(f'cd {DATA} && git fetch -q && git reset --hard origin/main'))
def push(h=None):
    c = f'cd {R if h else DATA} && git add -A && git -c user.name=a -c user.email=a@a commit -qm s 2>/dev/null; git fetch -q && git -c user.name=a -c user.email=a@a rebase -q origin/main 2>/dev/null; git push -q'
    return ssh(h,c) if h else loc(c)
def emit_loc(ev): open(EF,'a').write(json.dumps(ev)+'\n')
def emit_ssh(h,ev): ssh(h,f"echo '{json.dumps(ev)}' >> {R}/events.jsonl")
def replay(): loc(f'python3 -c "from aio_cmd._common import replay_events; replay_events()"')

def test():
    ts = int(time.time())

    print("1. LOCAL: add note+hub, push")
    for t,d in [('notes',{'t':f'L{ts}'}),('hub',{'name':f'Lh{ts}','schedule':'*:0','prompt':'x','device':'L','enabled':1})]:
        emit_loc({'ts':time.time(),'id':f'L{t[0]}{ts}','dev':'loc','op':f'{t}.add','d':d})
    push()

    print("2. TERMUX+HSU: pull, add, push (sequential)")
    for h in ['termux','hsu']:
        pull(h)
        for t,d in [('notes',{'t':f'{h[0].upper()}{ts}'}),('hub',{'name':f'{h[0].upper()}h{ts}','schedule':'*:0','prompt':'x','device':h,'enabled':1})]:
            emit_ssh(h, {'ts':time.time(),'id':f'{h[0].upper()}{t[0]}{ts}','dev':h,'op':f'{t}.add','d':d})
        push(h)

    print("3. LOCAL: pull, verify")
    pull()
    ef = open(EF).read()
    for h in ['T','H']: assert f'{h}n{ts}' in ef and f'{h}h{ts}' in ef, f"missing {h} data"
    print("   OK")

    print("4. TERMUX: ack note; HSU: archive hub")
    pull('termux'); emit_ssh('termux', {'ts':time.time(),'id':f'ack{ts}','dev':'tx','op':'notes.ack','d':{'id':f'Ln{ts}'}}); push('termux')
    pull('hsu'); emit_ssh('hsu', {'ts':time.time(),'id':f'rm{ts}','dev':'hsu','op':'hub.archive','d':{'name':f'Lh{ts}'}}); push('hsu')

    print("5. All pull, verify (parallel)")
    with Pool(3) as p: list(p.map(pull, [None,'termux','hsu']))
    replay()
    assert loc(f"sqlite3 {DATA}/aio.db \"SELECT s FROM notes WHERE id='Ln{ts}'\"") == "1", "note not acked"
    assert loc(f"sqlite3 {DATA}/aio.db \"SELECT COUNT(*) FROM hub_jobs WHERE name='Lh{ts}'\"") == "0", "hub not archived"
    print("   OK")

if __name__ == "__main__":
    print("=== SYNC TEST (local <-> termux <-> hsu) ===\n")
    for h in ['termux','hsu']: assert 'ok' in ssh(h,"echo ok"), f"Cannot reach {h}"
    test()
    print("\n=== PASSED ===")
