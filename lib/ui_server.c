/* lib/ui_server.c — C WebSocket terminal server (xterm.js, zero Python deps)
 *
 * Serves xterm.js HTML on GET /, upgrades GET /ws to WebSocket,
 * relays between WebSocket and a PTY running bash -l.
 * Single-threaded, one terminal at a time. ~0 idle overhead.
 *
 * Usage: a ui-serve [port]   (default 1111, foreground for launchd/systemd)
 */

#include <sys/socket.h>
#include <netinet/in.h>
#include <poll.h>

static const char UI_C_HTML[] =
"<!doctype html>"
"<meta name=viewport content='width=device-width,initial-scale=1,user-scalable=no'>"
"<link rel=stylesheet href='https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.min.css'>"
"<script src='https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.min.js'></script>"
"<script src='https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.min.js'></script>"
"<body style='margin:0;height:100vh;background:#000'><div id=t style='height:100vh'></div>"
"<script>try{var T=new Terminal(),F=new(FitAddon.FitAddon||FitAddon)(),W;"
"T.loadAddon(F);T.open(document.getElementById('t'));"
"function S(d){if(W&&W.readyState===1)W.send(d);}"
"function connect(){W=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws');"
"W.onopen=function(){F.fit();S(JSON.stringify({cols:T.cols,rows:T.rows}));};"
"W.onmessage=function(e){T.write(e.data);};"
"W.onclose=function(){setTimeout(connect,1000);};"
"W.onerror=function(){};}"
"connect();T.onData(function(d){S(d);});"
"new ResizeObserver(function(){F.fit();S(JSON.stringify({cols:T.cols,rows:T.rows}));}).observe(document.getElementById('t'));"
"}catch(e){document.body.innerHTML='<pre style=color:red>'+e+'</pre>';}</script>";

/* ═══ SHA-1 (RFC 3174, for WebSocket handshake) ═══ */
static void ui_sha1(const unsigned char *data, size_t len, unsigned char out[20]) {
    uint32_t h[5] = {0x67452301,0xEFCDAB89,0x98BADCFE,0x10325476,0xC3D2E1F0};
    size_t bits = len * 8, pl = ((len + 8) / 64 + 1) * 64;
    unsigned char *m = calloc(1, pl);
    memcpy(m, data, len); m[len] = 0x80;
    for (size_t i = 0; i < 8; i++) m[pl - 1 - i] = (unsigned char)(bits >> (i * 8));
    for (size_t o = 0; o < pl; o += 64) {
        uint32_t w[80];
        for (size_t i = 0; i < 16; i++)
            w[i] = (uint32_t)m[o+i*4]<<24 | (uint32_t)m[o+i*4+1]<<16 | (uint32_t)m[o+i*4+2]<<8 | m[o+i*4+3];
        for (int i = 16; i < 80; i++) { uint32_t t = w[i-3]^w[i-8]^w[i-14]^w[i-16]; w[i] = (t<<1)|(t>>31); }
        uint32_t a=h[0], b=h[1], c=h[2], dd=h[3], e=h[4];
        for (int i = 0; i < 80; i++) {
            uint32_t f, k;
            if      (i < 20) { f=(b&c)|(~b&dd);          k=0x5A827999; }
            else if (i < 40) { f=b^c^dd;                  k=0x6ED9EBA1; }
            else if (i < 60) { f=(b&c)|(b&dd)|(c&dd);     k=0x8F1BBCDC; }
            else              { f=b^c^dd;                  k=0xCA62C1D6; }
            uint32_t t = ((a<<5)|(a>>27)) + f + e + k + w[i];
            e=dd; dd=c; c=(b<<30)|(b>>2); b=a; a=t;
        }
        h[0]+=a; h[1]+=b; h[2]+=c; h[3]+=dd; h[4]+=e;
    }
    free(m);
    for (int i = 0; i < 5; i++) {
        out[i*4]=(unsigned char)(h[i]>>24); out[i*4+1]=(unsigned char)(h[i]>>16);
        out[i*4+2]=(unsigned char)(h[i]>>8); out[i*4+3]=(unsigned char)h[i];
    }
}

static void ui_b64(const unsigned char *in, size_t len, char *out) {
    static const char B64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t i, j = 0;
    for (i = 0; i + 2 < len; i += 3) {
        out[j++]=B64[in[i]>>2]; out[j++]=B64[((in[i]&3)<<4)|(in[i+1]>>4)];
        out[j++]=B64[((in[i+1]&15)<<2)|(in[i+2]>>6)]; out[j++]=B64[in[i+2]&63];
    }
    if (i < len) {
        out[j++]=B64[in[i]>>2];
        if (i+1<len) { out[j++]=B64[((in[i]&3)<<4)|(in[i+1]>>4)]; out[j++]=B64[(in[i+1]&15)<<2]; }
        else { out[j++]=B64[(in[i]&3)<<4]; out[j++]='='; }
        out[j++]='=';
    }
    out[j] = 0;
}

/* ═══ WEBSOCKET FRAMING ═══ */
static ssize_t ui_readn(int fd, void *buf, size_t n) {
    size_t got = 0;
    while (got < n) { ssize_t r = read(fd, (char *)buf + got, n - got); if (r <= 0) return -1; got += (size_t)r; }
    return (ssize_t)got;
}

static ssize_t ui_ws_recv(int fd, unsigned char *buf, size_t bufsz, int *op) {
    unsigned char hdr[2];
    if (ui_readn(fd, hdr, 2) < 0) return -1;
    *op = hdr[0] & 0x0F;
    int masked = hdr[1] & 0x80;
    uint64_t len = hdr[1] & 0x7F;
    if (len == 126) { unsigned char x[2]; if (ui_readn(fd,x,2)<0) return -1; len=(uint64_t)x[0]<<8|x[1]; }
    else if (len == 127) { unsigned char x[8]; if (ui_readn(fd,x,8)<0) return -1; len=0; for(int i=0;i<8;i++) len=(len<<8)|x[i]; }
    if (len > bufsz) return -1;
    unsigned char mask[4] = {0};
    if (masked && ui_readn(fd, mask, 4) < 0) return -1;
    if (len > 0 && ui_readn(fd, buf, (size_t)len) < 0) return -1;
    if (masked) for (size_t i = 0; i < len; i++) buf[i] ^= mask[i & 3];
    return (ssize_t)len;
}

static int ui_ws_send(int fd, const unsigned char *data, size_t len, int op) {
    unsigned char hdr[10]; int hl = 2;
    hdr[0] = (unsigned char)(0x80 | op);
    if (len < 126) hdr[1] = (unsigned char)len;
    else if (len < 65536) { hdr[1]=126; hdr[2]=(unsigned char)(len>>8); hdr[3]=(unsigned char)len; hl=4; }
    else { hdr[1]=127; for(int i=0;i<8;i++) hdr[2+i]=(unsigned char)(len>>((unsigned)(7-i)*8)); hl=10; }
    if (write(fd, hdr, (size_t)hl) != hl) return -1;
    if (len > 0 && write(fd, data, len) != (ssize_t)len) return -1;
    return 0;
}

/* ═══ PTY + WEBSOCKET RELAY ═══ */
static void ui_relay(int cli) {
    int master = posix_openpt(O_RDWR | O_NOCTTY);
    if (master < 0) return;
    grantpt(master); unlockpt(master);
    char *sn = ptsname(master);
    int slave = open(sn, O_RDWR);
    struct winsize ws = {.ws_row=50, .ws_col=180};
    ioctl(slave, TIOCSWINSZ, &ws);

    pid_t pid = fork();
    if (pid == 0) {
        close(master); close(cli); setsid();
        ioctl(slave, TIOCSCTTY, 0);
        dup2(slave,0); dup2(slave,1); dup2(slave,2);
        if (slave > 2) close(slave);
        setenv("TERM", "xterm-256color", 1);
        unsetenv("TMUX"); unsetenv("TMUX_PANE");
        execlp("bash", "bash", "-l", (char *)NULL);
        _exit(1);
    }
    close(slave);

    struct pollfd fds[2] = {{.fd=master,.events=POLLIN},{.fd=cli,.events=POLLIN}};
    unsigned char buf[8192];
    while (1) {
        int ret = poll(fds, 2, -1);
        if (ret < 0) { if (errno == EINTR) continue; break; }
        if (fds[0].revents & (POLLIN|POLLHUP)) {
            ssize_t n = read(master, buf, sizeof(buf));
            if (n <= 0) break;
            if (ui_ws_send(cli, buf, (size_t)n, 1) < 0) break;
        }
        if (fds[1].revents & POLLIN) {
            int op; ssize_t n = ui_ws_recv(cli, buf, sizeof(buf)-1, &op);
            if (n < 0 || op == 8) break;
            if (op == 9) { ui_ws_send(cli, buf, (size_t)n, 0xA); continue; }
            if (op == 0xA) continue;
            buf[n] = 0;
            /* resize: {"cols":N,"rows":N} */
            if (buf[0] == '{') {
                char *cp = strstr((char*)buf, "\"cols\""), *rp = strstr((char*)buf, "\"rows\"");
                if (cp && rp) { cp=strchr(cp,':'); rp=strchr(rp,':');
                    if (cp && rp) { int c=atoi(cp+1), r=atoi(rp+1);
                        if (c>0 && r>0) { struct winsize w={.ws_row=(unsigned short)r,.ws_col=(unsigned short)c}; ioctl(master,TIOCSWINSZ,&w); continue; }
                    }
                }
            }
            write(master, buf, (size_t)n);
        }
        if (fds[1].revents & (POLLHUP|POLLERR)) break;
    }
    close(master); kill(pid, SIGHUP); waitpid(pid, NULL, WNOHANG);
}

/* ═══ HTTP + ACCEPT LOOP ═══ */
static int cmd_ui_serve(int argc, char **argv) {
    int port = (argc > 2 && argv[2][0] >= '0' && argv[2][0] <= '9') ? atoi(argv[2]) : 1111;
    int srv = socket(AF_INET, SOCK_STREAM, 0);
    if (srv < 0) { perror("socket"); return 1; }
    int opt = 1; setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    struct sockaddr_in addr; memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET; addr.sin_addr.s_addr = INADDR_ANY; addr.sin_port = htons((uint16_t)port);
    if (bind(srv, (struct sockaddr *)&addr, sizeof(addr)) < 0) { perror("bind"); close(srv); return 1; }
    if (listen(srv, 5) < 0) { perror("listen"); close(srv); return 1; }
    signal(SIGCHLD, SIG_IGN); signal(SIGPIPE, SIG_IGN);

    for (;;) {
        int cli = accept(srv, NULL, NULL);
        if (cli < 0) continue;
        char req[8192]; ssize_t n = recv(cli, req, sizeof(req)-1, 0);
        if (n <= 0) { close(cli); continue; }
        req[n] = 0;

        if (strncmp(req, "GET /ws", 7) == 0 && strstr(req, "Upgrade")) {
            /* WebSocket handshake */
            char *kp = strstr(req, "Sec-WebSocket-Key: ");
            if (!kp) { close(cli); continue; }
            kp += 19; char *ke = strstr(kp, "\r\n"); if (!ke) { close(cli); continue; }
            char cat[128]; int kl = (int)(ke - kp);
            snprintf(cat, sizeof(cat), "%.*s258EAFA5-E914-47DA-95CA-5DFB86F42D13", kl, kp);
            unsigned char hash[20]; ui_sha1((unsigned char *)cat, strlen(cat), hash);
            char acc[64]; ui_b64(hash, 20, acc);
            char resp[256]; int rl = snprintf(resp, sizeof(resp),
                "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: %s\r\n\r\n", acc);
            write(cli, resp, (size_t)rl);
            ui_relay(cli);
        } else if (strncmp(req, "GET / ", 6) == 0) {
            char hdr[256]; size_t bl = strlen(UI_C_HTML);
            int hl = snprintf(hdr, sizeof(hdr), "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %zu\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n", bl);
            write(cli, hdr, (size_t)hl); write(cli, UI_C_HTML, bl);
        } else {
            write(cli, "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n", 64);
        }
        close(cli);
    }
}
