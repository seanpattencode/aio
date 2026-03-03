from http.server import HTTPServer, BaseHTTPRequestHandler; import subprocess, time
class UI(BaseHTTPRequestHandler):
    def do_GET(self):
        t = time.time(); out = subprocess.getoutput("source ~/.bashrc 2>/dev/null && ls")
        self.send_response(200); self.end_headers()
        self.wfile.write(f"Time: {time.time()-t:.4f}s<pre>{out}</pre><button onclick='location.reload()'>ls</button>".encode())
HTTPServer(('localhost', 8000), UI).serve_forever()
