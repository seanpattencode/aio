from fastapi import FastAPI; import subprocess, time; from fastapi.responses import HTMLResponse
app = FastAPI()
@app.get("/", response_class=HTMLResponse)
async def run(c: str = "ls"):
    t = time.perf_counter(); out = subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {c}")
    return f"<b>{time.perf_counter()-t:.4f}s</b><pre>{out}</pre><button onclick=\"location.href='/?c=ls'\">ls</button>"
if __name__ == "__main__": import uvicorn; uvicorn.run(app)
