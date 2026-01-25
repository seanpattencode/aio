"""aio note - Full note management (fast path handled in dispatcher)"""
import sys
from . _common import init_db, db, db_sync

def run():
    init_db()
    db_sync(pull=True)
    raw = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    with db() as c:
        if raw: c.execute("INSERT INTO notes(t) VALUES(?)", (raw,)); c.commit(); db_sync(); print("✓"); sys.exit()
        projs = [r[0] for r in c.execute("SELECT name FROM note_projects ORDER BY c")]
        notes = c.execute("SELECT id,t,d,proj FROM notes WHERE s=0 ORDER BY c DESC").fetchall()
        if not notes: print("aio n <text>"); sys.exit()
        if not sys.stdin.isatty(): [print(f"{t}" + (f" @{p}" if p else "")) for _,t,_,p in notes[:10]]; sys.exit()
        print(f"{len(notes)} notes | [a]ck [e]dit [p]rojects [m]ore [q]uit | 1/20=due")
        i = 0
        while i < len(notes):
            nid,txt,due,proj = notes[i]
            print(f"\n[{i+1}/{len(notes)}] {txt}" + (f" @{proj}" if proj else "") + (f" [{due}]" if due else "")); ch = input("> ").strip().lower()
            if ch == 'a': c.execute("UPDATE notes SET s=1 WHERE id=?", (nid,)); c.commit(); db_sync(); print("✓")
            elif ch == 'e': nv = input("new: "); nv and (c.execute("UPDATE notes SET t=? WHERE id=?", (nv, nid)), c.commit(), db_sync(), print("✓"))
            elif '/' in ch:
                from dateutil.parser import parse
                d = str(parse(ch, dayfirst=False))[:19].replace(' 00:00:00', '')
                c.execute("UPDATE notes SET d=? WHERE id=?", (d, nid)); c.commit(); db_sync(); print(f"✓ {d}")
            elif ch == 'm': print("\n=== Archive ==="); [print(f"  [{ct[:16]}] {t}" + (f" @{p}" if p else "")) for t,p,ct in c.execute("SELECT t,proj,c FROM notes WHERE s=1 ORDER BY c DESC LIMIT 20")]; input("[enter]")
            elif ch == 'p':
                while True:
                    print(("\n" + "\n".join(f"  {j}. {x}" for j,x in enumerate(projs))) if projs else "\n  (no projects)"); pc = input("p> ").strip()
                    if not pc: break
                    if pc[:3]=='rm ' and pc[3:].isdigit() and int(pc[3:])<len(projs): n=projs.pop(int(pc[3:])); c.execute("DELETE FROM note_projects WHERE name=?",(n,)); c.commit(); db_sync(); print(f"✓ {n}"); continue
                    if pc.isdigit() and int(pc) < len(projs):
                        pname = projs[int(pc)]
                        while True:
                            pnotes = c.execute("SELECT id,t,d FROM notes WHERE s=0 AND proj=? ORDER BY c DESC", (pname,)).fetchall(); print(f"\n=== {pname} === {len(pnotes)} notes"); [print(f"  {j}. {pt}" + (f" [{pd}]" if pd else "")) for j,(pid,pt,pd) in enumerate(pnotes)]; pn = input(f"{pname}> ").strip()
                            if not pn: break
                            c.execute("INSERT INTO notes(t,proj) VALUES(?,?)", (pn,pname)); c.commit(); db_sync(); print("✓")
                        break
                    c.execute("INSERT OR IGNORE INTO note_projects(name) VALUES(?)", (pc,)); c.commit(); projs.append(pc) if pc not in projs else None; db_sync(); print(f"✓ {pc}")
            elif ch == 'q': sys.exit()
            elif ch: c.execute("INSERT INTO notes(t) VALUES(?)", (ch,)); c.commit(); db_sync(); notes.insert(0,(0,ch,0,0)); print(f"✓ [{len(notes)}]"); continue
            i += 1
