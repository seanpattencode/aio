from http.server import BaseHTTPRequestHandler,HTTPServer;import urllib.parse,subprocess,datetime
H="<!doctype html><html><meta charset=utf-8><body><input id=c value=ls><button onclick=run(c.value)>run</button><button onclick=run('ls')>ls</button><button onclick=run('time')>time</button><pre id=o></pre><script>run=x=>fetch('/?c='+encodeURIComponent(x)).then(r=>r.text()).then(t=>o.textContent=t)</script></body></html>"
A={"ls":lambda:subprocess.getoutput("source ~/.bashrc 2>/dev/null && ls"),"aio":lambda:subprocess.getoutput("source ~/.bashrc 2>/dev/null && aio"),"time":lambda:datetime.datetime.now().isoformat()}
class S(BaseHTTPRequestHandler):
 def do_GET(s):c=urllib.parse.parse_qs(urllib.parse.urlsplit(s.path).query).get("c",[""])[0];out=H if not c else A.get(c,lambda:"(blocked)")();s.send_response(200);s.send_header("Content-Type","text/html; charset=utf-8" if not c else "text/plain; charset=utf-8");s.end_headers();s.wfile.write(out.encode())
HTTPServer(("127.0.0.1",8000),S).serve_forever()
