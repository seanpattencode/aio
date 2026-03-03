from fastapi import FastAPI; from fastapi.responses import HTMLResponse; import subprocess, time
app = FastAPI()
@app.get("/", response_class=HTMLResponse)
def ui():
    s = time.time(); out = subprocess.getoutput("source ~/.bashrc 2>/dev/null && ls")
    return f"Time: {time.time()-s}s<pre>{out}</pre><button onclick='location.reload()'>ls</button>"
if __name__ == "__main__": import uvicorn; uvicorn.run(app)
