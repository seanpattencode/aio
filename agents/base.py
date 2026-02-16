#!/usr/bin/env python3
"""Base module for agents — shared: save(), send(), ask_claude(), ask_gemini()"""
import subprocess,smtplib,os,shutil,socket
from datetime import datetime
from pathlib import Path
from email.message import EmailMessage

P=os.path.dirname(os.path.abspath(__file__))
AIO=os.path.join(os.path.dirname(P),"lib","a.py")
EMAIL_F=str(Path(P).parent/'adata'/'git'/'email.txt')
GOALS=os.path.join(P,"goals.md")
FILTERS=os.path.join(P,"great_filters.md")

# Device ID (matches _common.py logic)
_dev_file=os.path.join(os.path.dirname(P),'adata','local','.device')
DEVICE_ID=open(_dev_file).read().strip() if os.path.exists(_dev_file) else socket.gethostname()[:8]

# Conversation save dir
AGENTS_DIR=Path(P).parent/'adata'/'git'/'agents'

def save(name, output):
    """Save agent conversation to git-synced agents dir"""
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    now=datetime.now()
    ts=now.strftime('%Y%m%dT%H%M%S')
    fn=f'{name}_{ts}_{DEVICE_ID}.txt'
    header=f'Agent: {name}\nDate: {now:%Y-%m-%d %H:%M}\nDevice: {DEVICE_ID}\n---\n'
    (AGENTS_DIR/fn).write_text(header+output+'\n')
    ad=AGENTS_DIR.parent/'activity'; ad.mkdir(parents=True,exist_ok=True)
    snippet=(output.strip().split('\n')[-1])[:60]
    (ad/f'{ts}.{int(now.timestamp()*1000)%1000:03d}_{DEVICE_ID}.txt').write_text(f'{now:%m/%d %H:%M} {DEVICE_ID} agent:{name} → {snippet} {os.getcwd()}\n')
    subprocess.Popen([os.path.join(os.path.dirname(P),'a'),'sync'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

def get_creds():
    if os.path.exists(EMAIL_F):
        kv={l.split(': ',1)[0]:l.split(': ',1)[1] for l in open(EMAIL_F).read().strip().split('\n') if ': ' in l}
        return kv.get('From',''),kv.get('To',''),kv.get('Pass','')
    f,t,p=input("from: "),input("to: "),input("pass: ")
    os.makedirs(os.path.dirname(EMAIL_F),exist_ok=True)
    open(EMAIL_F,'w').write(f'From: {f}\nTo: {t}\nPass: {p}\n')
    return f,t,p

def send(subj,body):
    f,t,p=get_creds()
    msg=EmailMessage();msg["From"],msg["To"],msg["Subject"]=f,t,subj;msg.set_content(body)
    s=smtplib.SMTP_SSL("smtp.gmail.com",465);s.login(f,p);s.sendmail(f,t,msg.as_string());s.quit()
    print(f"Sent '{subj}' to {t}")

def send_stdin(subj):
    """Send email with body from stdin (for piping)."""
    import sys; send(subj, sys.stdin.read())

def ask_gemini(prompt,timeout=120):
    gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
    r=subprocess.run([gemini,'-p',prompt],capture_output=True,text=True,timeout=timeout)
    return r.stdout.strip()

def ask_claude(prompt,tools="Read,Glob,Grep",timeout=120):
    try:
        claude=shutil.which('claude')or os.path.expanduser('~/.local/bin/claude')
        r=subprocess.run([claude,'-p','--allowedTools',tools],input=prompt,capture_output=True,text=True,timeout=timeout,cwd=os.path.dirname(AIO))
        return r.stdout.strip() if r.returncode==0 else f"failed: {r.stderr}"
    except Exception as e:
        return f"failed: {e}"

if __name__=="__main__":
    import sys
    a=sys.argv[1:]
    if not a or a[0] in ('-h','--help','help'):
        to="(not configured)"
        if os.path.exists(EMAIL_F):
            kv={l.split(': ',1)[0]:l.split(': ',1)[1] for l in open(EMAIL_F).read().strip().split('\n') if ': ' in l}
            to=kv.get('To',to)
        print("a email - send email\n\n"
              "  a email \"subject\" \"body\"     send with subject + body\n"
              "  a email \"subject\"            body from stdin\n"
              "  a email \"subject\" < file     pipe file as body\n"
              "  echo msg | a email \"subj\"    pipe as body\n\n"
              f"Config: {EMAIL_F}\n"
              f"  To: {to}"); sys.exit(0)
    subj=a[0]
    body=a[1] if len(a)>1 else sys.stdin.read()
    send(subj,body)
