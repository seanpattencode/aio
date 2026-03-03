import os, pty, asyncio, aiohttp.web as w
async def i(r): return w.Response(text='<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.js"></script><link href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css" rel="stylesheet"><div id="t"></div><script>t=new Terminal();t.open(document.getElementById("t"));s=new WebSocket("ws://"+location.host+"/w");s.onmessage=e=>t.write(e.data);t.onData(d=>s.send(d))</script><button onclick="s.send(\'ls -la\\n\')">LS</button><button onclick="s.send(\'time\\n\')">Time</button>', content_type='text/html')
async def s(r):
    ws=w.WebSocketResponse(); await ws.prepare(r); m,sl=pty.openpty()
    asyncio.create_task(asyncio.create_subprocess_shell('bash', stdin=sl, stdout=sl, stderr=sl)); os.close(sl)
    asyncio.get_event_loop().add_reader(m, lambda: asyncio.create_task(ws.send_str(os.read(m,1024).decode(errors='ignore'))))
    async for msg in ws: os.write(m, msg.data.encode())
    return ws
w.run_app(w.Application().add_routes([w.get('/',i), w.get('/w',s)]))
