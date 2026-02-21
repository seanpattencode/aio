/*
 * aid.c — interactive picker daemon + client (sub-1ms startup)
 *
 * Daemon: stays resident, listens on unix socket, i_cache in memory.
 *         Receives terminal fds via SCM_RIGHTS, runs TUI, returns cmd.
 * Client: connects to socket, passes fds, waits for result, execs.
 *
 * Build: cc -O2 -o a-i lib/aid.c
 * Usage: a-i --daemon &   (auto-started by shell function)
 *        a-i              (client mode, default)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <termios.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <sys/wait.h>
#include <ctype.h>
#include <errno.h>

#define SOCK_NAME "/tmp/aid-%d.sock"
#define MAX_LINES 512
#define BUF 4096

/* ── fd passing over unix socket ── */
static int send_fds(int sock, int fd0, int fd1) {
    int fds[2] = {fd0, fd1};
    char buf[1] = {0};
    struct iovec iov = {.iov_base = buf, .iov_len = 1};
    union { struct cmsghdr h; char b[CMSG_SPACE(sizeof(fds))]; } ctrl;
    struct msghdr msg = {.msg_iov = &iov, .msg_iovlen = 1,
        .msg_control = ctrl.b, .msg_controllen = sizeof(ctrl.b)};
    struct cmsghdr *cm = CMSG_FIRSTHDR(&msg);
    cm->cmsg_level = SOL_SOCKET; cm->cmsg_type = SCM_RIGHTS;
    cm->cmsg_len = CMSG_LEN(sizeof(fds));
    memcpy(CMSG_DATA(cm), fds, sizeof(fds));
    return sendmsg(sock, &msg, 0) >= 0 ? 0 : -1;
}

static int recv_fds(int sock, int *fd0, int *fd1) {
    int fds[2] = {-1, -1};
    char buf[1];
    struct iovec iov = {.iov_base = buf, .iov_len = 1};
    union { struct cmsghdr h; char b[CMSG_SPACE(sizeof(fds))]; } ctrl;
    struct msghdr msg = {.msg_iov = &iov, .msg_iovlen = 1,
        .msg_control = ctrl.b, .msg_controllen = sizeof(ctrl.b)};
    if (recvmsg(sock, &msg, 0) < 0) return -1;
    struct cmsghdr *cm = CMSG_FIRSTHDR(&msg);
    if (cm && cm->cmsg_type == SCM_RIGHTS) memcpy(fds, CMSG_DATA(cm), sizeof(fds));
    *fd0 = fds[0]; *fd1 = fds[1];
    return (fds[0] >= 0 && fds[1] >= 0) ? 0 : -1;
}

/* ── cache loading ── */
typedef struct { char *lines[MAX_LINES]; int n; char *raw; } cache_t;

static void load_cache(cache_t *c, const char *path) {
    if (c->raw) free(c->raw);
    c->n = 0;
    int fd = open(path, O_RDONLY); if (fd < 0) return;
    struct stat st; if (fstat(fd, &st) < 0) { close(fd); return; }
    c->raw = malloc((size_t)st.st_size + 1);
    if (!c->raw) { close(fd); return; }
    ssize_t n = read(fd, c->raw, (size_t)st.st_size); close(fd);
    if (n <= 0) { free(c->raw); c->raw = NULL; return; }
    c->raw[n] = 0;
    for (char *p = c->raw, *end = c->raw + n; p < end && c->n < MAX_LINES;) {
        char *nl = memchr(p, '\n', (size_t)(end - p));
        if (!nl) nl = end;
        if (nl > p && p[0] != '<' && p[0] != '=' && p[0] != '>' && p[0] != '#')
            { *nl = 0; c->lines[c->n++] = p; }
        p = nl + 1;
    }
}

/* ── TUI picker (runs on client's terminal fds) ── */
static int run_tui(cache_t *c, int tty_in, int tty_out, char *result, int rsz) {
    if (!c->n) return -1;
    struct winsize ws; ioctl(tty_out, TIOCGWINSZ, &ws);
    int maxshow = ws.ws_row > 6 ? ws.ws_row - 3 : 10;

    struct termios old, raw;
    tcgetattr(tty_in, &old); raw = old;
    raw.c_lflag &= ~(tcflag_t)(ICANON | ECHO);
    raw.c_cc[VMIN] = 1; raw.c_cc[VTIME] = 0;
    tcsetattr(tty_in, TCSANOW, &raw);

    char filter[256] = ""; int flen = 0, sel = 0;
    char prefix[256] = "";

#define WR(s, l) (void)!write(tty_out, s, l)
#define WRS(s) WR(s, strlen(s))

    WRS("Filter (\xe2\x86\x91\xe2\x86\x93/Tab=cycle, Enter=run, Esc=quit)\n");

    int ret = -1;
    while (1) {
        char *matches[MAX_LINES]; int nm = 0;
        int plen = (int)strlen(prefix);
        for (int i = 0; i < c->n && nm < MAX_LINES; i++) {
            if (plen && strncmp(c->lines[i], prefix, (size_t)plen)) continue;
            if (flen) {
                char *s = c->lines[i] + plen, b2[256]; char *w;
                snprintf(b2, 256, "%s", filter); int ok = 1;
                for (w = strtok(b2, " "); w && ok; w = strtok(NULL, " "))
                    if (!strcasestr(s, w)) ok = 0;
                if (!ok) continue;
            }
            matches[nm++] = c->lines[i];
        }
        if (sel >= nm) sel = nm ? nm - 1 : 0;
        int top = sel >= maxshow ? sel - maxshow + 1 : 0;
        int show = nm - top < maxshow ? nm - top : maxshow;

        /* render */
        char line[512];
        int l = snprintf(line, 512, "\r\033[K%s> %s\n", prefix, filter);
        WR(line, (size_t)l);
        for (int i = 0; i < show; i++) {
            int j=top+i,W=ws.ws_col; char *t=strchr(matches[j],'\t');
            int ml=t?(int)(t-matches[j]):(int)strlen(matches[j]); if(ml>W-5)ml=W-5;
            l=snprintf(line,512,"\033[K%s a %.*s",j==sel?" >":"  ",ml,matches[j]); WR(line,(size_t)l);
            {char*px=getenv("PREFIX");if(t&&!(px&&strstr(px,"termux"))&&ml+5+(int)strlen(t+1)<W){l=snprintf(line,512,"\033[%dG\033[90m%s\033[0m",W-(int)strlen(t+1),t+1);WR(line,(size_t)l);}}
            WRS("\n");
        }
        l = snprintf(line, 512, "\033[%dA\033[%dC\033[?25h", show + 1, plen + flen + 3);
        WR(line, (size_t)l);

        /* read key */
        char ch; if (read(tty_in, &ch, 1) != 1) break;
        if (ch == '\x1b') {
            char seq[2];
            if (read(tty_in, &seq[0], 1) != 1) break;
            if (seq[0] == '[') {
                if (read(tty_in, &seq[1], 1) != 1) break;
                if (seq[1] == 'A') { if (sel > 0) sel--; }
                else if (seq[1] == 'B') { if (sel < nm - 1) sel++; }
            } else if (prefix[0]) { prefix[0] = 0; filter[0] = 0; flen = 0; sel = 0; }
            else break;
        } else if (ch == '\t') { if (sel < nm - 1) sel++; }
        else if (ch == '\x7f' || ch == '\b') { if (flen) filter[--flen] = 0; sel = 0; }
        else if (ch == '\r' || ch == '\n') {
            if (!nm) continue;
            char *m = matches[sel], cmd[256];
            char *tab = strchr(m, '\t'), *colon = strchr(m, ':');
            if (colon && (!tab || colon < tab)) {
                int cl = (int)(colon - m); snprintf(cmd, 256, "%.*s", cl, m);
                while (cmd[0] == ' ') memmove(cmd, cmd + 1, strlen(cmd));
            } else {
                int cl = tab ? (int)(tab - m) : (int)strlen(m);
                snprintf(cmd, 256, "%.*s", cl, m);
            }
            char *e = cmd + strlen(cmd) - 1;
            while (e > cmd && *e == ' ') *e-- = 0;
            /* drill into submenu */
            int has_sub = 0, cl = (int)strlen(cmd);
            for (int i = 0; i < c->n; i++)
                if (!strncmp(c->lines[i], cmd, (size_t)cl) && c->lines[i][cl] == ' ') { has_sub = 1; break; }
            if (has_sub) {
                snprintf(prefix, 256, "%s ", cmd);
                filter[0] = 0; flen = 0; sel = 0;
                WRS("\033[J"); continue;
            }
            tcsetattr(tty_in, TCSANOW, &old);
            l = snprintf(line, 512, "\n\n\033[KRunning: a %s\n", cmd);
            WR(line, (size_t)l);
            snprintf(result, rsz, "%s", cmd);
            ret = 0; goto done;
        } else if (ch == '\x03' || ch == '\x04') break;
        else if (ch == 'q' && !flen) break;
        else if ((ch>='a'&&ch<='z')||(ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9')||ch=='-'||ch=='_'||ch==' ')
            { if (flen < 254) { filter[flen++] = ch; filter[flen] = 0; sel = 0; } }
        WRS("\033[J");
    }
    tcsetattr(tty_in, TCSANOW, &old);
    WRS("\033[2J\033[H");
done:
    return ret;
}

/* ── socket path ── */
static void sock_path(char *buf, int sz) { snprintf(buf, (size_t)sz, SOCK_NAME, getuid()); }

/* ── daemon mode ── */
static int run_daemon(const char *cache_path) {
    /* detach */
    if (fork() > 0) _exit(0);
    setsid();
    signal(SIGPIPE, SIG_IGN);

    char sp[256]; sock_path(sp, 256);
    unlink(sp);

    int srv = socket(AF_UNIX, SOCK_STREAM, 0);
    if (srv < 0) { perror("socket"); return 1; }
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", sp);
    if (bind(srv, (struct sockaddr *)&addr, sizeof(addr)) < 0) { perror("bind"); return 1; }
    chmod(sp, 0700);
    listen(srv, 4);

    /* load cache */
    cache_t cache = {.n = 0, .raw = NULL};
    load_cache(&cache, cache_path);

    /* write pid file */
    char pf[256]; snprintf(pf, 256, "%s.pid", sp);
    FILE *f = fopen(pf, "w"); if (f) { fprintf(f, "%d", getpid()); fclose(f); }

    /* serve */
    while (1) {
        int cli = accept(srv, NULL, NULL);
        if (cli < 0) { if (errno == EINTR) continue; break; }

        /* receive: 'q' = quit, 'r' = reload, 'i' = interactive */
        char op;
        if (read(cli, &op, 1) != 1) { close(cli); continue; }

        if (op == 'q') { close(cli); break; }

        if (op == 'r') {
            load_cache(&cache, cache_path);
            write(cli, "ok", 2);
            close(cli); continue;
        }

        if (op == 'i') {
            int fd_in, fd_out;
            if (recv_fds(cli, &fd_in, &fd_out) < 0) { close(cli); continue; }

            /* reload cache if stale (check mtime) */
            struct stat st;
            static time_t last_mtime;
            if (stat(cache_path, &st) == 0 && st.st_mtime != last_mtime) {
                load_cache(&cache, cache_path);
                last_mtime = st.st_mtime;
            }

            char result[256] = "";
            int ok = run_tui(&cache, fd_in, fd_out, result, 256);
            close(fd_in); close(fd_out);

            if (ok == 0 && result[0])
                write(cli, result, strlen(result));
            close(cli);
        }
    }

    unlink(sp);
    char pidf[256]; snprintf(pidf, 256, "%s.pid", sp);
    unlink(pidf);
    if (cache.raw) free(cache.raw);
    close(srv);
    return 0;
}

/* ── ensure daemon is running, return 1 if started ── */
static int ensure_daemon(const char *cache_path) {
    char sp[256]; sock_path(sp, 256);
    char pf[256]; snprintf(pf, 256, "%s.pid", sp);

    /* check existing pid */
    FILE *f = fopen(pf, "r");
    if (f) {
        int pid; if (fscanf(f, "%d", &pid) == 1) {
            fclose(f);
            if (kill(pid, 0) == 0) return 0; /* already running */
        } else fclose(f);
    }

    /* start daemon */
    pid_t p = fork();
    if (p == 0) {
        run_daemon(cache_path);
        _exit(0);
    }
    /* wait briefly for socket to appear */
    for (int i = 0; i < 50; i++) {
        usleep(1000);
        struct stat st;
        if (stat(sp, &st) == 0) return 1;
    }
    return -1;
}

/* ── client mode ── */
static int run_client(const char *cache_path) {
    ensure_daemon(cache_path);

    char sp[256]; sock_path(sp, 256);
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return 1;
    struct sockaddr_un addr = {.sun_family = AF_UNIX};
    snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", sp);
    if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(fd);
        /* daemon not ready, fall back to direct exec */
        execlp("a", "a", "i", (char *)NULL);
        return 1;
    }

    /* send 'i' + our terminal fds */
    write(fd, "i", 1);
    if (send_fds(fd, STDIN_FILENO, STDOUT_FILENO) < 0) {
        close(fd);
        execlp("a", "a", "i", (char *)NULL);
        return 1;
    }

    /* wait for result */
    char result[256] = "";
    ssize_t n = read(fd, result, 255);
    close(fd);

    if (n <= 0) return 0; /* user cancelled */
    result[n] = 0;

    /* exec the selected command */
    char *args[32]; int ac = 0;
    args[ac++] = "a";
    char *p = result;
    while (*p && ac < 31) {
        while (*p == ' ') p++;
        if (!*p) break;
        args[ac++] = p;
        while (*p && *p != ' ') p++;
        if (*p) *p++ = 0;
    }
    args[ac] = NULL;
    execvp("a", args);
    return 0;
}

/* ── main ── */
int main(int argc, char **argv) {
    /* resolve cache path from env or default */
    const char *ddir = getenv("_ADD");
    char cache_path[512];
    if (ddir) snprintf(cache_path, 512, "%s/i_cache.txt", ddir);
    else {
        const char *h = getenv("HOME");
        if (!h) h = "/tmp";
        snprintf(cache_path, 512, "%s/projects/a/adata/local/i_cache.txt", h);
    }

    if (argc > 1 && !strcmp(argv[1], "--daemon")) return run_daemon(cache_path);
    if (argc > 1 && !strcmp(argv[1], "--reload")) {
        char sp[256]; sock_path(sp, 256);
        int fd = socket(AF_UNIX, SOCK_STREAM, 0);
        struct sockaddr_un addr = {.sun_family = AF_UNIX};
        snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", sp);
        if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) == 0) { write(fd, "r", 1); close(fd); }
        return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "--stop")) {
        char sp[256]; sock_path(sp, 256);
        int fd = socket(AF_UNIX, SOCK_STREAM, 0);
        struct sockaddr_un addr = {.sun_family = AF_UNIX};
        snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", sp);
        if (connect(fd, (struct sockaddr *)&addr, sizeof(addr)) == 0) { write(fd, "q", 1); close(fd); }
        return 0;
    }
    return run_client(cache_path);
}
