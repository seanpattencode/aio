#!/usr/bin/env python3
import subprocess,smtplib,sqlite3,os,sys,shutil
from email.message import EmailMessage

P=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(P,"email.db")

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

def weather():
    try:
        gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
        r=subprocess.run([gemini,'NYC weather in 10 words or less'],capture_output=True,text=True,timeout=60)
        return r.stdout.strip() if r.returncode==0 else "weather unavailable"
    except:return "weather unavailable"

if __name__=="__main__":
    w=weather()
    print(f"NYC: {w}")
    if "--send" in sys.argv:
        subj=sys.argv[sys.argv.index("--send")+1] if len(sys.argv)>sys.argv.index("--send")+1 else "Weather Report (aio hub)"
        send(subj,f"NYC Weather: {w}")
