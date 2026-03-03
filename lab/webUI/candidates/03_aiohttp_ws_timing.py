from aiohttp import web; import subprocess
# UI: Connects persistent socket on load. Button sends 'ls', measures round-trip time.
async def i(r): return web.Response(text="<script>w=new WebSocket('ws://'+location.host+'/w');w.onmessage=e=>document.body.innerText=e.data+' '+(performance.now()-t).toFixed(2)+'ms'</script><button onclick=\"t=performance.now();w.send('ls -la')\">Run WS</button>", content_type='text/html')

# Server: Reads from socket -> Executes -> Streams back (Persistent)
async def w(r):
    ws=web.WebSocketResponse(); await ws.prepare(r)
    async for m in ws: await ws.send_str(subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {m.data}"))
    return ws

app=web.Application(); app.add_routes([web.get('/',i), web.get('/w',w)]); web.run_app(app)
