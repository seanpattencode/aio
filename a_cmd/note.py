"""aio note - Full note management
SYNC: Append-only event log. Never delete - archive instead. Any device can ack any note.
Events: notes.add, notes.ack, notes.update. State rebuilt via replay_events().
"""
import sys
from . _common import init_db, db, db_sync, emit_event, replay_events

def run():
    init_db(); db_sync(pull=True); replay_events(['notes'])
    raw = ' '.join(sys.argv[2:]) if len(sys.argv) > 2 else None
    with db() as c:
        if raw and raw[0]!='?': eid = emit_event("notes", "add", {"t": raw}); c.execute("INSERT OR REPLACE INTO notes(id,t,s) VALUES(?,?,0)", (eid, raw)); c.commit(); db_sync(); print("✓"); sys.exit()
        projs = [r[0] for r in c.execute("SELECT name FROM note_projects ORDER BY c")]
        devs = [r[0] for r in c.execute("SELECT DISTINCT dev FROM notes WHERE dev IS NOT NULL")]
        notes = c.execute("SELECT id,t,d,proj,dev FROM notes WHERE s=0 AND t LIKE ? ORDER BY c DESC", (f'%{raw[1:]}%',)).fetchall() if raw else c.execute("SELECT id,t,d,proj,dev FROM notes WHERE s=0 ORDER BY c DESC").fetchall()
        filt = None  # current device filter
        if not notes: print("a n <text>"); sys.exit()
        if not sys.stdin.isatty(): [print(f"{t}" + (f" @{p}" if p else "")) for _,t,_,p,_ in notes[:10]]; sys.exit()
        print(f"{len(notes)} notes | [a]ck [e]dit [s]earch [d]evice [p]rojects [m]ore [q]uit | 1/20=due")
        i = 0
        while i < len(notes):
            nid,txt,due,proj,dev = notes[i]
            print(f"\n[{i+1}/{len(notes)}] {txt}" + (f" @{proj}" if proj else "") + (f" [{due}]" if due else "") + (f" <{dev[:8]}>" if dev else "")); ch = input("> ").strip().lower()
            if ch == 'a': emit_event("notes", "ack", {"id": nid}); c.execute("UPDATE notes SET s=1 WHERE id=?", (nid,)); c.commit(); db_sync(); print("✓")
            elif ch == 'e': nv = input("new: "); nv and (emit_event("notes", "update", {"id": nid, "t": nv}), c.execute("UPDATE notes SET t=? WHERE id=?", (nv, nid)), c.commit(), db_sync(), print("✓"))
            elif '/' in ch:
                from dateutil.parser import parse
                d = str(parse(ch, dayfirst=False))[:19].replace(' 00:00:00', '')
                emit_event("notes", "update", {"id": nid, "d": d}); c.execute("UPDATE notes SET d=? WHERE id=?", (d, nid)); c.commit(); db_sync(); print(f"✓ {d}")
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
                            eid = emit_event("notes", "add", {"t": pn, "proj": pname}); c.execute("INSERT OR REPLACE INTO notes(id,t,s,proj) VALUES(?,?,0,?)", (eid, pn, pname)); c.commit(); db_sync(); print("✓")
                        break
                    c.execute("INSERT OR IGNORE INTO note_projects(name) VALUES(?)", (pc,)); c.commit(); projs.append(pc) if pc not in projs else None; db_sync(); print(f"✓ {pc}")
            elif ch == 'q': sys.exit()
            elif ch == 'd':
                print("Devices: " + ", ".join(f"{j}.{d[:10]}" for j,d in enumerate(devs)) + " | a=all")
                dc = input("d> ").strip()
                if dc == 'a' or dc == '': filt = None; notes = c.execute("SELECT id,t,d,proj,dev FROM notes WHERE s=0 ORDER BY c DESC").fetchall()
                elif dc.isdigit() and int(dc) < len(devs): filt = devs[int(dc)]; notes = c.execute("SELECT id,t,d,proj,dev FROM notes WHERE s=0 AND dev LIKE ? ORDER BY c DESC", (f'%{filt}%',)).fetchall()
                else: filt = dc; notes = c.execute("SELECT id,t,d,proj,dev FROM notes WHERE s=0 AND dev LIKE ? ORDER BY c DESC", (f'%{filt}%',)).fetchall()
                i=0; print(f"{len(notes)} notes" + (f" from {filt}" if filt else "")); continue
            elif ch == 's': q = input("search: "); notes = c.execute("SELECT id,t,d,proj,dev FROM notes WHERE s=0 AND t LIKE ? ORDER BY c DESC", (f'%{q}%',)).fetchall(); i=0; print(f"{len(notes)} results"); continue
            elif ch: eid = emit_event("notes", "add", {"t": ch}); c.execute("INSERT OR REPLACE INTO notes(id,t,s) VALUES(?,?,0)", (eid, ch)); c.commit(); db_sync(); notes.insert(0,(eid,ch,None,None,None)); print(f"✓ [{len(notes)}]"); continue
            i += 1
