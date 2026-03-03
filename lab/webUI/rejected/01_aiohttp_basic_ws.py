from aiohttp import web
import asyncio, subprocess, webbrowser

async def index(r): return web.Response(text=HTML, content_type='text/html')
async def ws(r):
    ws = web.WebSocketResponse(); await ws.prepare(r)
    async for msg in ws:
        t = asyncio.create_subprocess_shell(msg.data, stdout=subprocess.PIPE)
        proc = await t; out, _ = await proc.communicate()
        await ws.send_str(out.decode())
    return ws

app = web.Application(); app.add_routes([web.get('/', index), web.get('/ws', ws)])
webbrowser.open('http://localhost:8080'); web.run_app(app)
