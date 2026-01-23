#!/usr/bin/env python3
import subprocess,smtplib,sqlite3,os,sys,shutil
from email.message import EmailMessage

P=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(P,"email.db")
AIO=os.path.join(os.path.dirname(P),"aio.py")
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

def ask_filter():
    prompt=f"""Read {FILTERS} and {AIO}.

Given where aio.py is right now as an AI agent manager, which of the 8 great filters feels MOST blocking to future success?

Pick ONE. Explain in 2-3 sentences why it's the bottleneck right now and what the smallest step to unblock it would be."""
    try:
        claude=shutil.which('claude')or os.path.expanduser('~/.local/bin/claude')
        r=subprocess.run([claude,'-p','--allowedTools','Read,Glob,Grep'],input=prompt,capture_output=True,text=True,timeout=120,cwd=os.path.dirname(AIO))
        return r.stdout.strip() if r.returncode==0 else f"analysis failed: {r.stderr}"
    except Exception as e:
        return f"analysis failed: {e}"

if __name__=="__main__":
    analysis=ask_filter()
    print(f"Filter Check:\n{analysis}")
    if "--send" in sys.argv:
        subj="Which filter is blocking? (hourly)"
        send(subj,f"Hourly check - which great filter is most blocking for aio?\n\n{analysis}")
