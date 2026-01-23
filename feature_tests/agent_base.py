#!/usr/bin/env python3
"""Base module for hourly agents"""
import subprocess,smtplib,sqlite3,os,shutil
from email.message import EmailMessage

P=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(P,"email.db")
AIO=os.path.join(os.path.dirname(P),"aio.py")
GOALS=os.path.join(P,"goals.md")
FILTERS=os.path.join(P,"great_filters.md")

def get_creds():
    db=sqlite3.connect(DB);db.execute("CREATE TABLE IF NOT EXISTS c(f,t,p)")
    r=db.execute("SELECT*FROM c").fetchone()
    if not r:
        f,t,p=input("from: "),input("to: "),input("pass: ")
        db.execute("INSERT INTO c VALUES(?,?,?)",(f,t,p));db.commit();r=(f,t,p)
    return r

def send(subj,body):
    f,t,p=get_creds()
    msg=EmailMessage();msg["From"],msg["To"],msg["Subject"]=f,t,subj;msg.set_content(body)
    s=smtplib.SMTP_SSL("smtp.gmail.com",465);s.login(f,p);s.sendmail(f,t,msg.as_string());s.quit()
    print(f"Sent '{subj}' to {t}")

def ask_claude(prompt,tools="Read,Glob,Grep",timeout=120):
    try:
        claude=shutil.which('claude')or os.path.expanduser('~/.local/bin/claude')
        r=subprocess.run([claude,'-p','--allowedTools',tools],input=prompt,capture_output=True,text=True,timeout=timeout,cwd=os.path.dirname(AIO))
        return r.stdout.strip() if r.returncode==0 else f"failed: {r.stderr}"
    except Exception as e:
        return f"failed: {e}"
