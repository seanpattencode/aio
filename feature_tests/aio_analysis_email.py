#!/usr/bin/env python3
import subprocess,smtplib,sqlite3,os,sys
from email.message import EmailMessage

P=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(P,"email.db")
AIO=os.path.join(os.path.dirname(P),"aio.py")

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

def analyze():
    prompt=f"""Read {AIO} fully. What is the ONE single most important thing lacking from aio.py that would make it a true AI agent manager? Be specific and concise (under 100 words). Focus on autonomous agent capabilities, not UI/UX."""
    try:
        r=subprocess.run(['claude','-p','--allowedTools','Read,Glob,Grep'],input=prompt,capture_output=True,text=True,timeout=120,cwd=os.path.dirname(AIO))
        return r.stdout.strip() if r.returncode==0 else f"analysis failed: {r.stderr}"
    except Exception as e:
        return f"analysis failed: {e}"

if __name__=="__main__":
    analysis=analyze()
    print(f"Analysis:\n{analysis}")
    if "--send" in sys.argv:
        subj=sys.argv[sys.argv.index("--send")+1] if len(sys.argv)>sys.argv.index("--send")+1 else "aio Analysis (aio hub)"
        send(subj,f"What's missing from aio.py to be a true AI agent manager?\n\n{analysis}")
