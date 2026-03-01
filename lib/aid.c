/*
 * aid.c — interactive picker (direct, no daemon)
 * Build: cc -O2 -o a-i lib/aid.c
 * Usage: a-i            (runs TUI, execs selected command)
 *        a-i --stop     (no-op, kept for compat)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <ctype.h>

#define MAX_LINES 512

/* ── cache loading ── */
typedef struct { char *lines[MAX_LINES]; int n; char *raw; } cache_t;

static void load_cache(cache_t *c, const char *path) {
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

/* ── TUI picker ── */
static int run_tui(cache_t *c, char *result, int rsz) {
    if (!c->n) return -1;
    struct winsize ws; ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws);
    int maxshow = ws.ws_row > 6 ? ws.ws_row - 3 : 10;

    struct termios old, raw;
    tcgetattr(STDIN_FILENO, &old); raw = old;
    raw.c_lflag &= ~(tcflag_t)(ICANON | ECHO | ISIG);
    raw.c_cc[VMIN] = 1; raw.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSANOW, &raw);

    char filter[256] = ""; int flen = 0, sel = 0;
    char prefix[256] = "";

#define WR(s, l) (void)!write(STDOUT_FILENO, s, l)
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
            {if(t&&ml+5+(int)strlen(t+1)<W){l=snprintf(line,512,"\033[%dG\033[90m%s\033[0m",W-(int)strlen(t+1),t+1);WR(line,(size_t)l);}}
            WRS("\n");
        }
        l = snprintf(line, 512, "\033[%dA\033[%dC\033[?25h", show + 1, plen + flen + 3);
        WR(line, (size_t)l);

        /* read key */
        char ch; if (read(STDIN_FILENO, &ch, 1) != 1) break;
        if (ch == '\x1b') {
            char seq[2];
            if (read(STDIN_FILENO, &seq[0], 1) != 1) break;
            if (seq[0] == '[') {
                if (read(STDIN_FILENO, &seq[1], 1) != 1) break;
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
            tcsetattr(STDIN_FILENO, TCSANOW, &old);
            l = snprintf(line, 512, "\n\n\033[KRunning: a %s\n", cmd);
            WR(line, (size_t)l);
            snprintf(result, rsz, "%s", cmd);
            ret = 0; goto done;
        } else if (ch == '\x03' || ch == '\x04') break;
        else if ((ch>='a'&&ch<='z')||(ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9')||ch=='-'||ch=='_'||ch==' ')
            { if (flen < 254) { filter[flen++] = ch; filter[flen] = 0; sel = 0; } }
        WRS("\033[J");
    }
    tcsetattr(STDIN_FILENO, TCSANOW, &old);
    WRS("\033[2J\033[H");
done:
    return ret;
}

/* ── main ── */
int main(int argc, char **argv) {
    if (argc > 1 && !strcmp(argv[1], "--stop")) return 0; /* compat */

    const char *ddir = getenv("_ADD");
    char cp[512];
    if (ddir) snprintf(cp, 512, "%s/i_cache.txt", ddir);
    else {
        const char *h = getenv("HOME"); if (!h) h = "/tmp";
        snprintf(cp, 512, "%s/projects/a/adata/local/i_cache.txt", h);
    }

    cache_t cache = {.n = 0, .raw = NULL};
    load_cache(&cache, cp);

    char result[256] = "";
    if (run_tui(&cache, result, 256) != 0) return 0;
    if (cache.raw) free(cache.raw);

    /* exec selected command */
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
