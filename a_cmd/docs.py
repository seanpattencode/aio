import sys,subprocess as sp;from ._common import SYNC_ROOT
D=SYNC_ROOT/'docs'
def run():
    D.mkdir(exist_ok=True);a=sys.argv[2:]
    if a:f=D/(a[0] if'.'in a[0]else a[0]+'.txt');f.touch();sp.run(['e',str(f)]);return
    fs=sorted(D.glob('*.txt'),key=lambda x:x.stat().st_mtime,reverse=True)
    for i,f in enumerate(fs):print(f"{i+1}. {f.name}")
    print(f"\n[#] open | [name] new | [o]pen vscode | [Enter] e folder")
    c=input("> ").strip()
    if not c:sp.run(['e',str(D)])
    elif c in('o','open'):sp.run(['code',str(D)])
    elif c.isdigit()and 0<int(c)<=len(fs):sp.run(['e',str(fs[int(c)-1])])
    else:(f:=D/(c if'.'in c else c+'.txt')).touch();sp.run(['e',str(f)])
