import sys, asyncio, os, pty, subprocess; from aiohttp import web
DIR = os.path.dirname(os.path.abspath(__file__))

async def page(r): return web.FileResponse(os.path.join(DIR, 'templates/index.html'))
async def run(r): d=await r.json(); return web.json_response({'out': subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {d['cmd']}")}) # Universal Command Runner

async def term(r):
    ws = web.WebSocketResponse(); await ws.prepare(r); m, s = pty.openpty()
    subprocess.Popen('bash', preexec_fn=os.setsid, stdin=s, stdout=s, stderr=s); os.close(s)
    asyncio.get_event_loop().add_reader(m, lambda: asyncio.create_task(ws.send_str(os.read(m, 1024).decode(errors='ignore'))))
    async for msg in ws: os.write(m, msg.data.encode()) # Two-way PTY Bridge
    return ws

app = web.Application(); app.add_routes([web.get('/', page), web.post('/exec', run), web.get('/ws', term)])
if __name__ == '__main__': web.run_app(app, port=int(sys.argv[2]) if len(sys.argv)>2 else 8080)
