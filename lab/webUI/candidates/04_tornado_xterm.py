import tornado.ioloop, tornado.web, tornado.websocket, os, pty
H="""<html><head><script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.js"></script><link href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css" rel="stylesheet"></head>
<body><button onclick="x.send('ls -la\\r')">LS</button> <button onclick="x.send('date\\r')">Time</button><div id="t"></div>
<script>t=new Terminal();t.open(document.getElementById('t'));x=new WebSocket('ws://'+location.host+'/s');
x.onmessage=e=>t.write(e.data);t.onData(d=>x.send(d))</script></body></html>"""
class S(tornado.websocket.WebSocketHandler):
    def open(s): p,f=pty.fork(); (os.execvp("bash",["bash"]) if p==0 else (setattr(s,'f',f), tornado.ioloop.IOLoop.current().add_handler(f,lambda f,e:s.write_message(os.read(f,900).decode(errors='ignore')),1)))
    def on_message(s,m): os.write(s.f,m.encode())
if __name__=="__main__": tornado.web.Application([(r"/",tornado.web.RequestHandler,{'get':lambda s:s.write(H)}),(r"/s",S)]).listen(8888); tornado.ioloop.IOLoop.current().start()
