/*
 * a.c - monolithic C rewrite of 'a' AI agent session manager
 *
 * Build (parallel split — zero overhead from strict checks):
 *   make          two clang passes run simultaneously:
 *                   1) -Werror -Weverything + hardening -fsyntax-only (validate)
 *                   2) -O2 -w bare                                    (emit binary)
 *                 validation finishes inside the compile, so all checks
 *                 are free. Binary is pure -O2 with no extra codegen.
 *   make debug    all flags combined + ASan/UBSan/IntSan -O1 -g
 *
 * Sections (grep for ═══ or ──):
 *   GLOBALS, INIT PATHS, UTILITIES, RFC 5322 KEY:VALUE PARSER,
 *   SQLITE, DATA LOADERS, HELP TEXT, LIST_ALL + CACHE,
 *   TMUX HELPERS, GIT HELPERS, SYNC, FALLBACK, SESSION CREATE
 *
 * Commands (grep for ── name ──):
 *   help, install, uninstall, set, dir, hi, done, web, repo,
 *   backup, rebuild, project_num, push, pull, diff, revert,
 *   ls, kill, config, prompt, add, remove, move, scan, attach,
 *   watch, send, copy, dash, jobs, cleanup, tree, note, task,
 *   ssh, hub, log, login, sync, update, review, docs, run,
 *   agent, multi/all, session, worktree, dir_file, interactive picker
 *
 * Dispatch: MAIN DISPATCH (switch on first arg)
 */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <dirent.h>
#include <time.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <termios.h>
#include <sys/ioctl.h>
#include <ctype.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#endif

#define P 1024
#define B 4096
#define MP 256
#define MA 64
#define MS 48

static void alog(const char *cmd, const char *cwd, const char *extra);

/* ═══ GLOBALS ═══ */
static char HOME[P], DDIR[P], AROOT[P], SROOT[P], SDIR[P], PYPATH[P], DEV[128], LOGDIR[P];
static int G_argc; static char **G_argv;

typedef struct { char path[512], repo[512], name[128]; } proj_t;
static proj_t PJ[MP]; static int NPJ;

typedef struct { char name[128], cmd[512]; } app_t;
static app_t AP[MA]; static int NAP;

typedef struct { char key[16], name[64], cmd[1024]; } sess_t;
static sess_t SE[MS]; static int NSE;

typedef struct { char k[64], v[1024]; } cfg_t;
static cfg_t CF[64]; static int NCF;

/* ═══ INIT PATHS ═══ */
static void init_paths(void) {
    const char *h = getenv("HOME"); if (!h) h = "/tmp";
    snprintf(HOME, P, "%s", h);
    snprintf(DDIR, P, "%s/.local/share/a", h);
    char self[P]; ssize_t n = -1;
#ifdef __APPLE__
    uint32_t sz = P - 1;
    if (_NSGetExecutablePath(self, &sz) == 0) { n = strlen(self); char rp[P]; if (realpath(self, rp)) { snprintf(self, P, "%s", rp); n = strlen(self); } }
#else
    n = readlink("/proc/self/exe", self, P - 1);
#endif
    if (n > 0) {
        self[n] = 0;
        char *s = strrchr(self, '/');
        if (s) { *s = 0; snprintf(SDIR, P, "%s", self);
            /* binary is at projects/a/a → strip to projects/ */
            s = strrchr(self, '/');
            if (s) { *s = 0; snprintf(AROOT, P, "%s/adata", self); snprintf(SROOT, P, "%s/git", AROOT); }
        }
    }
    if (!SROOT[0]) { snprintf(AROOT, P, "%s/projects/adata", h); snprintf(SROOT, P, "%s/git", AROOT); }
    snprintf(PYPATH, P, "%s/lib/a.py", SDIR);
    /* device id */
    char df[P]; snprintf(df, P, "%s/.device", DDIR);
    FILE *f = fopen(df, "r");
    if (f) { if (fgets(DEV, 128, f)) DEV[strcspn(DEV, "\n")] = 0; fclose(f); }
    if (!DEV[0]) {
        gethostname(DEV, 128);
        char c[P]; snprintf(c, P, "mkdir -p '%s'", DDIR); (void)!system(c);
        f = fopen(df, "w"); if (f) { fputs(DEV, f); fclose(f); }
    }
    snprintf(LOGDIR, P, "%s/backup/%s", AROOT, DEV);
    /* ensure adata README exists */
    char rm[P]; snprintf(rm, P, "%s/README", AROOT);
    struct stat st;
    if (stat(rm, &st) != 0) {
        f = fopen(rm, "w");
        if (f) {
            fputs("adata/ - 4-tier data sync\n\n"
                  "  git/      git push/pull       all devices     text <15M\n"
                  "  sync/     rclone copy <->      all devices     large files <5G\n"
                  "  vault/    rclone copy on-demand big devices     models/datasets\n"
                  "  backup/   rclone move ->        all devices     logs+state, upload+purge\n", f);
            fclose(f);
        }
    }
}

/* ═══ UTILITIES ═══ */
static int fexists(const char *p) { struct stat s; return stat(p, &s) == 0; }
static int dexists(const char *p) { struct stat s; return stat(p, &s) == 0 && S_ISDIR(s.st_mode); }
static void mkdirp(const char *p) { char c[P*2]; snprintf(c, sizeof(c), "mkdir -p '%s'", p); (void)!system(c); }

static char *readf(const char *p, size_t *len) {
    int fd = open(p, O_RDONLY); if (fd < 0) return NULL;
    struct stat s; if (fstat(fd, &s) < 0) { close(fd); return NULL; }
    size_t sz = (size_t)s.st_size;
    char *b = malloc(sz + 1); if (!b) { close(fd); return NULL; }
    ssize_t n = read(fd, b, sz); close(fd);
    if (n < 0) { free(b); return NULL; }
    b[n] = 0; if (len) *len = (size_t)n; return b;
}

static int catf(const char *p) {
    int fd = open(p, O_RDONLY); if (fd < 0) return -1;
    char b[8192]; ssize_t n;
    while ((n = read(fd, b, sizeof(b))) > 0) (void)!write(STDOUT_FILENO, b, (size_t)n);
    close(fd); return 0;
}

static void writef(const char *p, const char *data) {
    FILE *f = fopen(p, "w"); if (f) { fputs(data, f); fclose(f); }
}

static int pcmd(const char *cmd, char *out, int sz) {
    if (out) out[0] = 0;
    FILE *f = popen(cmd, "r"); if (!f) return -1;
    if (out) { int n = 0; char b[B];
        while (fgets(b, B, f) && n + (int)strlen(b) < sz - 1) n += sprintf(out + n, "%s", b);
    } else { char b[B]; while (fgets(b, B, f)) ; }
    return pclose(f);
}


static const char *bname(const char *p) { const char *s = strrchr(p, '/'); return s ? s + 1 : p; }

/* ═══ RFC 5322 KEY:VALUE PARSER ═══ */
typedef struct { char k[32], v[512]; } kv_t;
typedef struct { kv_t i[16]; int n; } kvs_t;

static kvs_t kvparse(const char *data) {
    kvs_t r = {.n = 0}; const char *p = data;
    while (*p && r.n < 16) {
        const char *nl = strchr(p, '\n'); if (!nl) nl = p + strlen(p);
        const char *c = memchr(p, ':', (size_t)(nl - p));
        if (c && c > p) {
            size_t kl = (size_t)(c - p); if (kl > 31) kl = 31;
            memcpy(r.i[r.n].k, p, kl); r.i[r.n].k[kl] = 0;
            const char *v = c + 1; while (*v == ' ' && v < nl) v++;
            size_t vl = (size_t)(nl - v); if (vl > 511) vl = 511;
            memcpy(r.i[r.n].v, v, vl); r.i[r.n].v[vl] = 0;
            r.n++;
        }
        p = *nl ? nl + 1 : nl;
    }
    return r;
}

static const char *kvget(kvs_t *kv, const char *key) {
    for (int i = 0; i < kv->n; i++) if (!strcmp(kv->i[i].k, key)) return kv->i[i].v;
    return NULL;
}

static kvs_t kvfile(const char *path) {
    char *d = readf(path, NULL);
    if (!d) return (kvs_t){.n = 0};
    kvs_t r = kvparse(d); free(d); return r;
}

static int listdir(const char *dir, char paths[][P], int max) {
    DIR *d = opendir(dir); if (!d) return 0;
    struct dirent *e; int n = 0;
    while ((e = readdir(d)) && n < max) {
        if (e->d_name[0] == '.') continue;
        char *dot = strrchr(e->d_name, '.'); if (!dot || strcmp(dot, ".txt")) continue;
        snprintf(paths[n++], P, "%s/%s", dir, e->d_name);
    }
    closedir(d); return n;
}

/* ═══ DATA FILES ═══ */
static void esc_nl(const char *s, char *o, int sz) {
    int j = 0;
    for (int i = 0; s[i] && j < sz - 2; i++) {
        if (s[i] == '\n') { o[j++] = '\\'; o[j++] = 'n'; } else o[j++] = s[i];
    }
    o[j] = 0;
}
static void unesc_nl(char *s) {
    char *r = s, *w = s;
    while (*r) { if (r[0] == '\\' && r[1] == 'n') { *w++ = '\n'; r += 2; } else *w++ = *r++; }
    *w = 0;
}

static void cfset(const char *key, const char *val) {
    int found = 0;
    for (int i = 0; i < NCF; i++) if (!strcmp(CF[i].k, key)) { snprintf(CF[i].v, 1024, "%s", val); found = 1; break; }
    if (!found && NCF < 64) { snprintf(CF[NCF].k, 64, "%s", key); snprintf(CF[NCF].v, 1024, "%s", val); NCF++; }
    char p[P]; snprintf(p, P, "%s/config.txt", DDIR);
    FILE *f = fopen(p, "w"); if (!f) return;
    for (int i = 0; i < NCF; i++) { char ev[2048]; esc_nl(CF[i].v, ev, 2048); fprintf(f, "%s: %s\n", CF[i].k, ev); }
    fclose(f);
}

static void init_db(void) {
    mkdirp(DDIR);
    char p[P]; snprintf(p, P, "%s/config.txt", DDIR);
    if (!fexists(p)) {
        char pp[P], dp[B] = ""; snprintf(pp, P, "%s/common/prompts/default.txt", SROOT);
        char *pd = readf(pp, NULL); if (pd) { snprintf(dp, B, "%s", pd); free(pd); }
        char edp[B]; esc_nl(dp, edp, B);
        char wt[P]; snprintf(wt, P, "%s/projects/aWorktrees", HOME);
        char buf[B*2]; snprintf(buf, sizeof(buf),
            "claude_prompt: %s\ncodex_prompt: %s\ngemini_prompt: %s\n"
            "worktrees_dir: %s\nmulti_default: l:3\nclaude_prefix: Ultrathink. \n", edp, edp, edp, wt);
        writef(p, buf);
    }
    snprintf(p, P, "%s/sessions.txt", DDIR);
    if (!fexists(p)) {
        const char *C = "claude --dangerously-skip-permissions";
        const char *X = "codex -c model_reasoning_effort=\"high\" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox";
        char buf[B*4]; snprintf(buf, sizeof(buf),
            "h|htop|htop\nt|top|top\ng|gemini|gemini --yolo\ngemini|gemini|gemini --yolo\n"
            "c|claude|%s\nclaude|claude|%s\nl|claude|%s\no|claude|%s\n"
            "co|codex|%s\ncodex|codex|%s\n"
            "a|aider|OLLAMA_API_BASE=http://127.0.0.1:11434 aider --model ollama_chat/mistral\n"
            "cp|claude-p|%s \"{CLAUDE_PROMPT}\"\nlp|claude-p|%s \"{CLAUDE_PROMPT}\"\n"
            "gp|gemini-p|gemini --yolo \"{GEMINI_PROMPT}\"\n"
            "cop|codex-p|%s \"{CODEX_PROMPT}\"\n", C, C, C, C, X, X, C, C, X);
        writef(p, buf);
    }
}

/* ═══ DATA LOADERS ═══ */
static void load_cfg(void) {
    NCF = 0; char p[P]; snprintf(p, P, "%s/config.txt", DDIR);
    kvs_t kv = kvfile(p);
    for (int i = 0; i < kv.n; i++) { snprintf(CF[NCF].k, 64, "%s", kv.i[i].k); snprintf(CF[NCF].v, 1024, "%s", kv.i[i].v); unesc_nl(CF[NCF].v); NCF++; }
}

static const char *cfget(const char *key) {
    for (int i = 0; i < NCF; i++) if (!strcmp(CF[i].k, key)) return CF[i].v;
    return "";
}

static int pj_cmp(const void *a, const void *b) { return strcmp(((const proj_t*)a)->name, ((const proj_t*)b)->name); }

static void load_proj(void) {
    NPJ = 0;
    char dir[P]; snprintf(dir, P, "%s/workspace/projects", SROOT);
    mkdirp(dir);
    char paths[MP][P]; int n = listdir(dir, paths, MP);
    for (int i = 0; i < n && NPJ < MP; i++) {
        kvs_t kv = kvfile(paths[i]);
        const char *nm = kvget(&kv, "Name"); if (!nm) continue;
        const char *pa = kvget(&kv, "Path");
        const char *re = kvget(&kv, "Repo");
        snprintf(PJ[NPJ].name, 128, "%s", nm);
        if (pa) { /* expand ~ */
            if (pa[0] == '~') snprintf(PJ[NPJ].path, 512, "%s%s", HOME, pa + 1);
            else snprintf(PJ[NPJ].path, 512, "%s", pa);
        } else snprintf(PJ[NPJ].path, 512, "%s/projects/%s", HOME, nm);
        snprintf(PJ[NPJ].repo, 512, "%s", re ? re : "");
        NPJ++;
    }
    qsort(PJ, (size_t)NPJ, sizeof(proj_t), pj_cmp);
}

static int ap_cmp(const void *a, const void *b) { return strcmp(((const app_t*)a)->name, ((const app_t*)b)->name); }

static void load_apps(void) {
    NAP = 0;
    char dir[P]; snprintf(dir, P, "%s/workspace/cmds", SROOT);
    mkdirp(dir);
    char paths[MA][P]; int n = listdir(dir, paths, MA);
    for (int i = 0; i < n && NAP < MA; i++) {
        kvs_t kv = kvfile(paths[i]);
        const char *nm = kvget(&kv, "Name");
        const char *cm = kvget(&kv, "Command");
        if (!nm || !cm) continue;
        snprintf(AP[NAP].name, 128, "%s", nm);
        snprintf(AP[NAP].cmd, 512, "%s", cm);
        NAP++;
    }
    qsort(AP, (size_t)NAP, sizeof(app_t), ap_cmp);
}

static void load_sess(void) {
    NSE = 0; char p[P]; snprintf(p, P, "%s/sessions.txt", DDIR);
    char *data = readf(p, NULL); if (!data) return;
    char *line = data;
    while (*line && NSE < MS) {
        char *nl = strchr(line, '\n'); if (nl) *nl = 0;
        char *d1 = strchr(line, '|'), *d2 = d1 ? strchr(d1 + 1, '|') : NULL;
        if (d1 && d2) {
            *d1 = 0; *d2 = 0;
            snprintf(SE[NSE].key, 16, "%s", line);
            snprintf(SE[NSE].name, 64, "%s", d1 + 1);
            char expanded[1024]; snprintf(expanded, 1024, "%s", d2 + 1);
            const char *keys[] = {"claude_prompt","codex_prompt","gemini_prompt"};
            const char *tags[] = {"{CLAUDE_PROMPT}","{CODEX_PROMPT}","{GEMINI_PROMPT}"};
            for (int j = 0; j < 3; j++) {
                char *pos = strstr(expanded, tags[j]);
                if (pos) {
                    const char *val = cfget(keys[j]);
                    char tmp[1024]; int pre = (int)(pos - expanded);
                    snprintf(tmp, 1024, "%.*s%s%s", pre, expanded, val, pos + strlen(tags[j]));
                    snprintf(expanded, 1024, "%s", tmp);
                }
            }
            const char *k = SE[NSE].key;
            if (!strcmp(k,"cp") || !strcmp(k,"lp") || !strcmp(k,"gp")) {
                char *dq = strstr(expanded, " \"");
                if (dq) *dq = 0;
            }
            snprintf(SE[NSE].cmd, 1024, "%s", expanded);
            NSE++;
        }
        if (!nl) break; line = nl + 1;
    }
    free(data);
}

static sess_t *find_sess(const char *key) {
    for (int i = 0; i < NSE; i++) if (!strcmp(SE[i].key, key)) return &SE[i];
    return NULL;
}

/* ═══ HELP TEXT ═══ */
static const char *HELP_SHORT =
    "a c|co|g|ai     Start claude/codex/gemini/aider\n"
    "a <#>           Open project by number\n"
    "a prompt        Manage default prompt\n"
    "a help          All commands";

static const char *HELP_FULL =
    "a - AI agent session manager\n\n"
    "AGENTS          c=claude  co=codex  g=gemini  ai=aider\n"
    "  a <key>             Start agent in current dir\n"
    "  a <key> <#>         Start agent in project #\n"
    "  a <key>++           Start agent in new worktree\n\n"
    "PROJECTS\n"
    "  a <#>               cd to project #\n"
    "  a add               Add current dir as project\n"
    "  a remove <#>        Remove project\n"
    "  a move <#> <#>      Reorder project\n"
    "  a scan              Add your repos fast\n\n"
    "GIT\n"
    "  a push [msg]        Commit and push\n"
    "  a pull              Sync with remote\n"
    "  a diff              Show changes\n"
    "  a revert            Select commit to revert to\n\n"
    "REMOTE\n"
    "  a ssh               List hosts\n"
    "  a ssh <#>           Connect to host\n"
    "  a run <#> \"task\"    Run task on remote\n\n"
    "OTHER\n"
    "  a jobs              Active sessions\n"
    "  a ls                List tmux sessions\n"
    "  a attach            Reconnect to session\n"
    "  a kill              Kill all sessions\n"
    "  a task              Tasks (priority, review, subfolders)\n"
    "  a n \"text\"          Quick note\n"
    "  a log               View agent logs\n"
    "  a config            View/set settings\n"
    "  a update            Update a\n"
    "  a mono              Generate monolith for reading\n\n"
    "EXPERIMENTAL\n"
    "  a agent \"task\"      Spawn autonomous subagent\n"
    "  a hub               Scheduled jobs (systemd)\n"
    "  a all               Multi-agent parallel runs\n"
    "  a tree              Create git worktree\n"
    "  a gdrive            Cloud sync (Google Drive)";

/* ═══ LIST_ALL + CACHE ═══ */
static void list_all(int cache, int quiet) {
    load_proj(); load_apps();
    char pfile[P]; snprintf(pfile, P, "%s/projects.txt", DDIR);
    /* Write projects.txt for shell function */
    FILE *pf = fopen(pfile, "w");
    if (pf) { for (int i = 0; i < NPJ; i++) fprintf(pf, "%s\n", PJ[i].path); fclose(pf); }
    if (quiet && !cache) return;
    char out[B*4] = ""; int o = 0;
    if (NPJ) {
        o += sprintf(out + o, "PROJECTS:\n");
        for (int i = 0; i < NPJ; i++) {
            char mk = dexists(PJ[i].path) ? '+' : (PJ[i].repo[0] ? '~' : 'x');
            o += sprintf(out + o, "  %d. %c %s\n", i, mk, PJ[i].path);
        }
    }
    if (NAP) {
        o += sprintf(out + o, "COMMANDS:\n");
        for (int i = 0; i < NAP; i++) {
            char dc[64]; snprintf(dc, 64, "%s", AP[i].cmd);
            o += sprintf(out + o, "  %d. %s -> %s\n", NPJ + i, AP[i].name, dc);
        }
    }
    if (!quiet && out[0]) printf("%s", out);
    if (cache) {
        char cf[P]; snprintf(cf, P, "%s/help_cache.txt", DDIR);
        FILE *f = fopen(cf, "w");
        if (f) { fprintf(f, "%s\n%s", HELP_SHORT, out); fclose(f); }
    }
}

/* ═══ TMUX HELPERS ═══ */
static int tm_has(const char *s) {
    char c[B]; snprintf(c, B, "tmux has-session -t '%s' 2>/dev/null", s);
    return system(c) == 0;
}

static void tm_go(const char *s) {
    if (getenv("TMUX")) execlp("tmux", "tmux", "switch-client", "-t", s, (char*)NULL);
    else execlp("tmux", "tmux", "attach", "-t", s, (char*)NULL);
}

static int tm_new(const char *s, const char *wd, const char *cmd) {
    char c[B*2];
    if (cmd && cmd[0]) snprintf(c, sizeof(c), "tmux new-session -d -s '%s' -c '%s' '%s'", s, wd, cmd);
    else snprintf(c, sizeof(c), "tmux new-session -d -s '%s' -c '%s'", s, wd);
    return system(c);
}

static void tm_send(const char *s, const char *text) {
    /* Use tmux send-keys -l for literal text */
    pid_t p = fork();
    if (p == 0) { execlp("tmux", "tmux", "send-keys", "-l", "-t", s, text, (char*)NULL); _exit(1); }
    if (p > 0) waitpid(p, NULL, 0);
}

/* ═══ GIT HELPERS ═══ */
static int git_in_repo(const char *p) {
    char c[P]; snprintf(c, P, "%s/.git", p); return dexists(c);
}

/* ═══ SYNC ═══ */
static void sync_repo(void) {
    char c[B*2];
    snprintf(c, sizeof(c),
        "git -C '%s' add -A 2>/dev/null && git -C '%s' commit -qm sync 2>/dev/null;"
        "git -C '%s' pull --no-rebase --no-edit -q origin main 2>/dev/null;"
        "git -C '%s' push -q origin main 2>/dev/null", SROOT, SROOT, SROOT, SROOT);
    (void)!system(c);
}
static void sync_bg(void) {
    pid_t p=fork();if(p<0)return;if(p>0){waitpid(p,NULL,WNOHANG);return;}
    if(fork()>0)_exit(0);setsid();sync_repo();_exit(0);
}

/* ═══ FALLBACK ═══ */
__attribute__((noreturn))
static void fallback_py(int argc, char **argv) {
    char **na = malloc(((unsigned)argc + 3) * sizeof(char *));
    na[0] = "python3"; na[1] = PYPATH;
    for (int i = 1; i < argc; i++) na[i + 1] = argv[i];
    na[argc + 1] = NULL;
    execvp("python3", na);
    perror("a: python3"); _exit(127);
}

/* ═══ SESSION CREATE ═══ */
static void create_sess(const char *sn, const char *wd, const char *cmd) {
    int ai = cmd && (strstr(cmd,"claude") || strstr(cmd,"codex") || strstr(cmd,"gemini") || strstr(cmd,"aider"));
    char wcmd[B*2];
    if (ai) snprintf(wcmd, sizeof(wcmd),
        "while :; do %s; e=$?; [ $e -eq 0 ] && break; echo -e \"\\n! Crashed (exit $e). [R]estart / [Q]uit: \"; read -n1 k; [[ $k =~ [Rr] ]] || break; done", cmd);
    else snprintf(wcmd, sizeof(wcmd), "%s", cmd ? cmd : "");
    tm_new(sn, wd, wcmd);
    if (ai) {
        char c[B]; snprintf(c, B, "tmux split-window -v -t '%s' -c '%s' 'sh -c \"ls;exec $SHELL\"'", sn, wd);
        (void)!system(c);
        snprintf(c, B, "tmux select-pane -t '%s' -U", sn); (void)!system(c);
    }
    /* logging */
    char c[B]; snprintf(c, B, "mkdir -p '%s'", LOGDIR); (void)!system(c);
    char lf[P]; snprintf(lf, P, "%s/%s__%s.log", LOGDIR, DEV, sn);
    snprintf(c, B, "tmux pipe-pane -t '%s' 'cat >> %s'", sn, lf); (void)!system(c);
    char al[B]; snprintf(al, B, "session:%s log:%s", sn, lf);
    alog(al, wd, NULL);
    /* agent_logs */
    char alf[P]; snprintf(alf, P, "%s/agent_logs.txt", DDIR);
    time_t now = time(NULL);
    FILE *af = fopen(alf, "a"); if (af) { fprintf(af, "%s %ld %s\n", sn, (long)now, DEV); fclose(af); }
}

static void send_prefix_bg(const char *sn, const char *agent, const char *wd) {
    const char *dp = cfget("default_prompt");
    const char *cp = strstr(agent, "claude") ? cfget("claude_prefix") : "";
    char pre[B]; snprintf(pre, B, "%s%s%s", dp[0] ? dp : "", dp[0] ? " " : "", cp);
    /* Check for AGENTS.md */
    char af[P]; snprintf(af, P, "%s/AGENTS.md", wd);
    char *amd = readf(af, NULL);
    if (amd) { size_t n = strlen(pre); snprintf(pre + n, (size_t)(B - (int)n), "%s ", amd); free(amd); }
    if (!pre[0]) return;
    if (fork() == 0) {
        setsid();
        for (int i = 0; i < 300; i++) {
            usleep(50000);
            char c[B], buf[B] = "";
            snprintf(c, B, "tmux capture-pane -t '%s' -p -S -50 2>/dev/null", sn);
            pcmd(c, buf, B);
            char *lo = buf;
            for (char *p = lo; *p; p++) *p = (*p >= 'A' && *p <= 'Z') ? *p + 32 : *p;
            if (strstr(lo,"context") || strstr(lo,"claude") || strstr(lo,"opus") || strstr(lo,"gemini") || strstr(lo,"codex")) break;
        }
        tm_send(sn, pre);
        _exit(0);
    }
}

/* ═══ COMMANDS ═══ */

static int cmd_help(int argc, char **argv) { (void)argc; (void)argv;
    char p[P]; snprintf(p, P, "%s/help_cache.txt", DDIR);
    if (catf(p) < 0) { init_db(); load_cfg(); printf("%s\n", HELP_SHORT); list_all(1, 0); }
    return 0;
}

static int cmd_help_full(int argc, char **argv) { (void)argc; (void)argv;
    init_db(); load_cfg(); printf("%s\n", HELP_FULL); list_all(1, 0); return 0;
}

static int cmd_hi(void) { for (int i = 1; i <= 10; i++) printf("%d\n", i); puts("hi"); return 0; }

static int cmd_done(void) {
    char p[P]; snprintf(p, P, "%s/.done", DDIR);
    int fd = open(p, O_WRONLY|O_CREAT|O_TRUNC, 0644); if (fd >= 0) close(fd);
    puts("\xe2\x9c\x93 done"); return 0;
}

static int cmd_dir(void) {
    char cwd[P]; if (getcwd(cwd, P)) puts(cwd);
    execlp("ls", "ls", (char*)NULL); return 1;
}

static int cmd_backup(void) { puts("backup: sync system removed, rewrite pending"); return 0; }
static int cmd_rebuild(void) { puts("rebuild: sync system removed, rewrite pending"); return 0; }

static int cmd_x(void) {
    (void)!system("tmux kill-server 2>/dev/null");
    puts("\xe2\x9c\x93 All sessions killed"); return 0;
}

static int cmd_web(int argc, char **argv) {
    char url[B] = "https://google.com";
    if (argc > 2) {
        snprintf(url, B, "https://google.com/search?q=");
        for (int i = 2; i < argc; i++) {
            if (i > 2) strcat(url, "+");
            strncat(url, argv[i], B - strlen(url) - 2);
        }
    }
    char c[B]; snprintf(c, B, "xdg-open '%s' 2>/dev/null &", url); (void)!system(c);
    return 0;
}

static int cmd_repo(int argc, char **argv) {
    if (argc < 3) { puts("Usage: a repo <name>"); return 1; }
    char c[B]; snprintf(c, B, "mkdir -p '%s' && cd '%s' && git init -q && gh repo create '%s' --public --source=.", argv[2], argv[2], argv[2]);
    (void)!system(c); return 0;
}

static int cmd_set(int argc, char **argv) {
    if (argc < 3) {
        char p[P]; snprintf(p, P, "%s/n", DDIR);
        printf("1. n [%s] commands without aio prefix\n   aio set n %s\n", fexists(p)?"on":"off", fexists(p)?"off":"on");
        return 0;
    }
    char p[P]; snprintf(p, P, "%s/%s", DDIR, argv[2]);
    if (argc > 3 && !strcmp(argv[3], "on")) { int fd = open(p, O_CREAT|O_WRONLY, 0644); if (fd>=0) close(fd); puts("\xe2\x9c\x93 on"); }
    else if (argc > 3 && !strcmp(argv[3], "off")) { unlink(p); puts("\xe2\x9c\x93 off"); }
    else printf("%s\n", fexists(p) ? "on" : "off");
    return 0;
}

static int cmd_install(void) {
    char s[P]; snprintf(s, P, "%s/install.sh", SDIR);
    if (fexists(s)) execlp("bash", "bash", s, (char*)NULL);
    return 1;
}

static int cmd_uninstall(void) {
    printf("Uninstall aio? (y/n): "); char buf[16];
    if (!fgets(buf, 16, stdin) || (buf[0] != 'y' && buf[0] != 'Y')) return 0;
    char p[P];
    snprintf(p, P, "%s/.local/bin/aio", HOME); unlink(p);
    snprintf(p, P, "%s/.local/bin/aioUI.py", HOME); unlink(p);
    puts("\xe2\x9c\x93 aio uninstalled"); _exit(0);
}

static int cmd_deps(void) {
    (void)!system("which tmux >/dev/null 2>&1 || sudo apt-get install -y tmux 2>/dev/null");
    printf("%s tmux\n", system("which tmux >/dev/null 2>&1") == 0 ? "\xe2\x9c\x93" : "x");
    (void)!system("which node >/dev/null 2>&1 || sudo apt-get install -y nodejs npm 2>/dev/null");
    printf("%s node\n", system("which node >/dev/null 2>&1") == 0 ? "\xe2\x9c\x93" : "x");
    const char *tools[][2] = {{"codex","@openai/codex"},{"claude","@anthropic-ai/claude-code"},{"gemini","@google/gemini-cli"}};
    for (int i = 0; i < 3; i++) {
        char c[256]; snprintf(c, 256, "which %s >/dev/null 2>&1 || sudo npm i -g %s 2>/dev/null", tools[i][0], tools[i][1]); (void)!system(c);
        snprintf(c, 256, "which %s >/dev/null 2>&1", tools[i][0]);
        printf("%s %s\n", system(c) == 0 ? "\xe2\x9c\x93" : "x", tools[i][0]);
    }
    return 0;
}

static int cmd_e(int argc, char **argv) {
    if (argc > 2 && !strcmp(argv[2], "install")) {
        (void)!system("curl -sL https://raw.githubusercontent.com/seanpattencode/editor/main/e.c|clang -xc -Wno-everything -o ~/.local/bin/e -");
        return 0;
    }
    if (getenv("TMUX")) execlp("e", "e", ".", (char*)NULL);
    else {
        init_db(); load_cfg();
        char wd[P]; if (!getcwd(wd, P)) strcpy(wd, HOME);
        create_sess("edit", wd, "e .");
        execlp("tmux", "tmux", "attach", "-t", "edit", (char*)NULL);
    }
    return 0;
}

/* ── project_num ── */
static int cmd_project_num(int argc, char **argv, int idx) { (void)argc; (void)argv;
    init_db(); load_cfg(); load_proj(); load_apps();
    if (idx >= 0 && idx < NPJ) {
        proj_t *p=&PJ[idx]; char c[B];
        if (!dexists(p->path) && p->repo[0]) {
            strcpy(c,p->path); char *sl=strrchr(c,'/'); if(sl)*sl=0;
            if(!dexists(c))snprintf(p->path,512,"%s/projects/%s",HOME,p->name);
            printf("Cloning %s...\n", p->repo);
            snprintf(c, B, "git clone '%s' '%s'", p->repo, p->path); (void)!system(c);
        }
        if (!dexists(p->path)) { printf("x %s\n", p->path); return 1; }
        snprintf(c,B,"%s/cd_target",DDIR); writef(c,p->path); printf("%s\n",p->path);
        if(!fork()){snprintf(c,B,"git -C '%s' ls-remote --exit-code origin HEAD>/dev/null 2>&1&&touch '%s/logs/push.ok'",p->path,DDIR);(void)!system(c);_exit(0);}
        return 0;
    }
    int ai = idx - NPJ;
    if (ai>=0 && ai<NAP) { char ex[B],*p,*e; snprintf(ex,B,"%s",AP[ai].cmd); while((p=strchr(ex,'{'))&&(e=strchr(p,'}'))){ *e=0;for(int j=0;j<NPJ;j++)if(!strcmp(PJ[j].name,p+1)){*p=0;char t[B];snprintf(t,B,"%s%s%s",ex,PJ[j].path,e+1);snprintf(ex,B,"%s",t);break;}} printf("> %s\n",AP[ai].name); return system(ex)>>8; }
    printf("x Invalid index: %d\n", idx); return 1;
}

/* ── setup ── */
static int cmd_setup(int argc, char **argv) { (void)argc; (void)argv;
    char cwd[P]; if (!getcwd(cwd, P)) strcpy(cwd, ".");
    if (git_in_repo(cwd)) { puts("x Already a git repo"); return 1; }
    char c[B]; snprintf(c, B, "cd '%s' && git init && git add -A && git commit -m 'init' && gh repo create '%s' --private --source . --push", cwd, bname(cwd));
    return system(c) >> 8;
}

/* ── push ── */
static int cmd_push(int argc, char **argv) {
    char cwd[P]; if (!getcwd(cwd, P)) strcpy(cwd, ".");
    char msg[B] = "";
    if (argc > 2) { for (int i = 2; i < argc; i++) { if (i>2) strcat(msg," "); strncat(msg, argv[i], B-strlen(msg)-2); } }
    else snprintf(msg, B, "Update %s", bname(cwd));

    if (!git_in_repo(cwd)) {
        /* Check for sub-repos */
        DIR *d = opendir(cwd); struct dirent *e; int nsub = 0;
        char subs[32][256];
        if (d) { while ((e = readdir(d)) && nsub < 32) { char gp[P]; snprintf(gp,P,"%s/%s/.git",cwd,e->d_name); if (dexists(gp)) snprintf(subs[nsub++],256,"%s",e->d_name); } closedir(d); }
        if (nsub) {
            printf("Push %d repos? ", nsub);
            for (int i = 0; i < nsub; i++) printf("%s%s", subs[i], i<nsub-1?", ":"");
            printf(" [y/n]: "); char buf[8]; if (!fgets(buf,8,stdin) || buf[0]!='y') return 0;
            for (int i = 0; i < nsub; i++) {
                char c[B]; snprintf(c, B, "cd '%s/%s' && git add -A && git commit -m '%s' --allow-empty 2>/dev/null && git push 2>/dev/null", cwd, subs[i], msg);
                int r = system(c); printf("%s %s\n", r==0?"\xe2\x9c\x93":"x", subs[i]);
            }
            return 0;
        }
        printf("Not a git repo. Set up as private GitHub repo? [y/n]: ");
        char buf2[8]; if (fgets(buf2,8,stdin) && buf2[0]=='y') return cmd_setup(argc, argv);
        return 0;
    }
    /* Check dirty */
    char dirty[64] = ""; pcmd("git status --porcelain 2>/dev/null", dirty, 64);
    const char *tag = dirty[0] ? "\xe2\x9c\x93" : "\xe2\x97\x8b";

    /* Check instant mode */
    char ok[P]; snprintf(ok, P, "%s/logs/push.ok", DDIR);
    struct stat st;
    if (stat(ok, &st) == 0 && time(NULL) - st.st_mtime < 600) {
        char c[B*2]; snprintf(c, sizeof(c),
            "cd '%s' && git add -A && git commit -m \"%s\" --allow-empty 2>/dev/null; git push 2>/dev/null; touch '%s'",
            cwd, msg, ok);
        if (fork() == 0) { setsid();
            int null = open("/dev/null", O_RDWR); dup2(null,0); dup2(null,1); dup2(null,2); if(null>2)close(null);
            execl("/bin/sh","sh","-c",c,(char*)NULL); _exit(1);
        }
        printf("%s %s\n", tag, msg); return 0;
    }
    /* Real push */
    char c[B];
    snprintf(c, B, "git -C '%s' config remote.origin.url 2>/dev/null", cwd);
    if (system(c) != 0) {
        snprintf(c, B, "cd '%s' && gh repo create --private --source . --push", cwd); (void)!system(c);
    }
    snprintf(c, B, "cd '%s' && git add -A && git commit -m '%s' --allow-empty 2>/dev/null", cwd, msg); (void)!system(c);
    snprintf(c, B, "cd '%s' && git push -u origin HEAD 2>&1", cwd);
    char out[B]; pcmd(c, out, B);
    if (strstr(out, "->") || strstr(out, "up-to-date") || strstr(out, "Everything")) {
        mkdirp(DDIR); snprintf(c, B, "%s/logs", DDIR); mkdirp(c);
        int fd = open(ok, O_CREAT|O_WRONLY|O_TRUNC, 0644); if(fd>=0)close(fd);
        printf("%s %s\n", tag, msg);
    } else printf("\xe2\x9c\x97 %s\n", out);
    return 0;
}

/* ── pull ── */
static int cmd_pull(int argc, char **argv) {
    char cwd[P]; if (!getcwd(cwd, P)) strcpy(cwd, ".");
    if (!git_in_repo(cwd)) { puts("x Not a git repo"); return 1; }
    char c[B], out[B];
    snprintf(c, B, "git -C '%s' fetch origin 2>/dev/null", cwd); (void)!system(c);
    snprintf(c, B, "git -C '%s' rev-parse --verify origin/main 2>/dev/null", cwd);
    const char *ref = (system(c) == 0) ? "origin/main" : "origin/master";
    snprintf(c, B, "git -C '%s' log -1 --format='%%h %%s' %s", cwd, ref); pcmd(c, out, B);
    out[strcspn(out,"\n")] = 0;
    printf("! DELETE local changes -> %s\n", out);
    if (argc < 3 || (strcmp(argv[2],"--yes") && strcmp(argv[2],"-y"))) {
        printf("Continue? (y/n): "); char buf[8]; if (!fgets(buf,8,stdin) || buf[0]!='y') { puts("x Cancelled"); return 1; }
    }
    snprintf(c, B, "git -C '%s' reset --hard %s && git -C '%s' clean -f -d", cwd, ref, cwd); (void)!system(c);
    printf("\xe2\x9c\x93 Synced: %s\n", out); return 0;
}

/* ── diff ── */
static int cmd_diff(int argc, char **argv) {
    const char *sel = argc > 2 ? argv[2] : NULL;
    /* Token history mode */
    if (sel && sel[0] >= '0' && sel[0] <= '9') {
        int n = atoi(sel); char c[256]; snprintf(c, 256, "git log -%d --pretty=%%H\\ %%cd\\ %%s --date=format:%%I:%%M%%p", n);
        FILE *fp = popen(c, "r"); if (!fp) return 1;
        char line[512]; int total = 0, i = 0;
        while (fgets(line, 512, fp)) {
            line[strcspn(line,"\n")] = 0;
            char *sp = strchr(line, ' '); if (!sp) continue;
            *sp = 0; char *hash = line, *ts = sp + 1;
            sp = strchr(ts, ' '); if (!sp) continue;
            *sp = 0; char *msg = sp + 1;
            char dc[256]; snprintf(dc, 256, "git show %.40s --pretty=", hash);
            FILE *dp = popen(dc, "r"); int ab = 0, db_ = 0;
            if (dp) { char dl[4096]; while (fgets(dl, 4096, dp)) { int l = (int)strlen(dl);
                if (dl[0]=='+' && dl[1]!='+') ab += l-1;
                else if (dl[0]=='-' && dl[1]!='-') db_ += l-1;
            } pclose(dp); }
            int tok = (ab - db_) / 4; total += tok;
            if (strlen(msg) > 55) { msg[52]='.'; msg[53]='.'; msg[54]='.'; msg[55]=0; }
            printf("  %d  %s  %+6d  %s\n", i++, ts, tok, msg);
        }
        pclose(fp); printf("\nTotal: %+d tokens\n", total); return 0;
    }
    /* Full diff mode - delegate to python for color output */
    fallback_py(argc, argv);
}

/* ── revert ── */
static int cmd_revert(int argc, char **argv) { (void)argc; (void)argv;
    char cwd[P]; if (!getcwd(cwd, P)) strcpy(cwd, ".");
    if (!git_in_repo(cwd)) { puts("x Not a git repo"); return 1; }
    char c[B], out[B*4]; snprintf(c, B, "git -C '%s' log --format='%%h %%ad %%s' --date=format:'%%m/%%d %%H:%%M' -15", cwd);
    pcmd(c, out, sizeof(out));
    char *lines[15]; int nl = 0; char *p = out;
    while (*p && nl < 15) { lines[nl++] = p; char *e = strchr(p, '\n'); if (e) { *e = 0; p = e+1; } else break; }
    for (int i = 0; i < nl; i++) printf("  %d. %s\n", i, lines[i]);
    printf("\nRevert to #/q: "); char buf[8]; if (!fgets(buf,8,stdin) || buf[0]=='q') return 0;
    int idx = atoi(buf); if (idx < 0 || idx >= nl) { puts("x Invalid"); return 1; }
    char hash[16]; sscanf(lines[idx], "%s", hash);
    snprintf(c, B, "git -C '%s' revert --no-commit '%s..HEAD'", cwd, hash); (void)!system(c);
    snprintf(c, B, "git -C '%s' commit -m 'revert to %s'", cwd, hash); (void)!system(c);
    printf("\xe2\x9c\x93 Reverted to %s\n", hash);
    printf("Push to main? (y/n): "); if (fgets(buf,8,stdin) && buf[0]=='y') {
        snprintf(c, B, "git -C '%s' push", cwd); (void)!system(c); puts("\xe2\x9c\x93 Pushed");
    }
    return 0;
}

/* ── ls ── */
static int cmd_ls(int argc, char **argv) {
    if (argc > 2 && argv[2][0] >= '0' && argv[2][0] <= '9') {
        /* Attach by number */
        char out[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null", out, B);
        char *lines[64]; int n = 0; char *p = out;
        while (*p && n < 64) { lines[n++] = p; char *e = strchr(p,'\n'); if (e) { *e=0; p=e+1; } else break; }
        int idx = atoi(argv[2]);
        if (idx >= 0 && idx < n) tm_go(lines[idx]);
        return 0;
    }
    char out[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null", out, B);
    if (!out[0]) { puts("No sessions"); return 0; }
    char *p = out; int i = 0;
    while (*p) {
        char *e = strchr(p, '\n'); if (e) *e = 0;
        if (*p) {
            char c[B], path[512] = "";
            snprintf(c, B, "tmux display-message -p -t '%s' '#{pane_current_path}' 2>/dev/null", p);
            pcmd(c, path, 512); path[strcspn(path,"\n")] = 0;
            printf("  %d  %s: %s\n", i++, p, path);
        }
        if (e) p = e + 1; else break;
    }
    puts("\nSelect:\n  a ls 0"); return 0;
}

/* ── kill ── */
static int cmd_kill(int argc, char **argv) {
    const char *sel = argc > 2 ? argv[2] : NULL;
    if ((sel && !strcmp(sel, "all")) || (argc > 1 && !strcmp(argv[1], "killall"))) {
        (void)!system("pkill -9 -f tmux 2>/dev/null"); (void)!system("clear");
        puts("\xe2\x9c\x93"); return 0;
    }
    char out[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null", out, B);
    char *lines[64]; int n = 0; char *p = out;
    while (*p && n < 64) { lines[n++] = p; char *e = strchr(p,'\n'); if (e) { *e=0; p=e+1; } else break; }
    if (!n) { puts("No sessions"); return 0; }
    if (sel && sel[0] >= '0' && sel[0] <= '9') {
        int idx = atoi(sel);
        if (idx >= 0 && idx < n) {
            char c[B]; snprintf(c, B, "tmux kill-session -t '%s'", lines[idx]); (void)!system(c);
            printf("\xe2\x9c\x93 %s\n", lines[idx]); return 0;
        }
    }
    for (int i = 0; i < n; i++) printf("  %d  %s\n", i, lines[i]);
    puts("\nSelect:\n  a kill 0\n  a kill all"); return 0;
}

/* ── config ── */
static int cmd_config(int argc, char **argv) {
    init_db(); load_cfg();
    if (argc < 3) {
        for (int i = 0; i < NCF; i++) {
            char v[54]; snprintf(v, 54, "%s", CF[i].v);
            printf("  %s: %s%s\n", CF[i].k, v, strlen(CF[i].v)>50?"...":"");
        }
        return 0;
    }
    const char *key = argv[2];
    if (argc > 3) {
        char val[B] = ""; for (int i=3;i<argc;i++) { if(i>3) strcat(val," "); strncat(val,argv[i],B-strlen(val)-2); }
        if (!strcmp(val,"off")||!strcmp(val,"none")||!strcmp(val,"\"\"")||!strcmp(val,"''")) val[0]=0;
        cfset(key, val);
        load_cfg(); list_all(1, 1);
        printf("\xe2\x9c\x93 %s=%s\n", key, val[0] ? val : "(cleared)");
    } else printf("%s: %s\n", key, cfget(key));
    return 0;
}

/* ── prompt ── */
static int cmd_prompt(int argc, char **argv) {
    init_db(); load_cfg();
    char val[B] = "";
    if (argc > 2) { for (int i=2;i<argc;i++) { if(i>2) strcat(val," "); strncat(val,argv[i],B-strlen(val)-2); } }
    else {
        printf("Current: %s\n", cfget("default_prompt")[0] ? cfget("default_prompt") : "(none)");
        printf("New (empty to clear): "); if (!fgets(val, B, stdin)) return 0;
        val[strcspn(val,"\n")] = 0;
    }
    if (!strcmp(val,"off")||!strcmp(val,"none")) val[0]=0;
    cfset("default_prompt", val);
    load_cfg(); list_all(1, 1);
    printf("\xe2\x9c\x93 %s\n", val[0] ? val : "(cleared)"); return 0;
}

/* ── add ── */
static int cmd_add(int argc, char **argv) {
    init_db(); load_cfg();
    char *args[16]; int na = 0;
    for (int i = 2; i < argc && na < 16; i++) if (strcmp(argv[i],"--global")) args[na++] = argv[i];
    /* App add: a add <name> <command...> or a add <interp> <script> */
    if (na >= 2 && !dexists(args[0])) {
        char name[128], cmd[B] = "";
        snprintf(name, 128, "%s", args[0]);
        for (int i = 1; i < na; i++) { if(i>1) strcat(cmd," "); strncat(cmd,args[i],B-strlen(cmd)-2); }
        char d[P]; snprintf(d, P, "%s/workspace/cmds", SROOT); mkdirp(d);
        char f[P]; snprintf(f, P, "%s/%s.txt", d, name);
        if (fexists(f)) { printf("x Exists: %s\n", name); return 1; }
        char cwd[P]; if (!getcwd(cwd,P)) strcpy(cwd,".");
        char data[B]; snprintf(data, B, "Name: %s\nCommand: %s\n", name, cmd);
        writef(f, data); sync_repo();
        printf("\xe2\x9c\x93 Added: %s\n", name); list_all(1, 0); return 0;
    }
    /* Project add */
    char path[P];
    if (na > 0) { char *a = args[0]; if (a[0]=='~') snprintf(path,P,"%s%s",HOME,a+1); else snprintf(path,P,"%s",a); }
    else if (!getcwd(path, P)) strcpy(path, ".");
    if (!dexists(path)) { printf("x Not a directory: %s\n", path); return 1; }
    const char *name = bname(path);
    char d[P]; snprintf(d, P, "%s/workspace/projects", SROOT); mkdirp(d);
    char f[P]; snprintf(f, P, "%s/%s.txt", d, name);
    if (fexists(f)) { printf("x Exists: %s\n", name); return 1; }
    char repo[512] = ""; char c[B]; snprintf(c, B, "git -C '%s' remote get-url origin 2>/dev/null", path);
    pcmd(c, repo, 512); repo[strcspn(repo,"\n")] = 0;
    char data[B]; snprintf(data, B, "Name: %s\nPath: %s\n%s%s%s", name, path, repo[0]?"Repo: ":"", repo, repo[0]?"\n":"");
    writef(f, data); sync_repo();
    printf("\xe2\x9c\x93 Added: %s\n", name); list_all(1, 0); return 0;
}

/* ── remove ── */
static int cmd_remove(int argc, char **argv) {
    init_db(); load_cfg(); load_proj(); load_apps();
    if (argc < 3) { puts("Usage: a remove <#|name>"); list_all(0, 0); return 0; }
    const char *sel = argv[2];
    if (sel[0] >= '0' && sel[0] <= '9') {
        int idx = atoi(sel);
        if (idx < NPJ) {
            char f[P]; snprintf(f, P, "%s/workspace/projects/%s.txt", SROOT, PJ[idx].name);
            unlink(f); sync_repo();
            printf("\xe2\x9c\x93 Removed: %s\n", PJ[idx].name); list_all(1, 0); return 0;
        }
        int ai = idx - NPJ;
        if (ai >= 0 && ai < NAP) {
            char f[P]; snprintf(f, P, "%s/workspace/cmds/%s.txt", SROOT, AP[ai].name);
            unlink(f); sync_repo();
            printf("\xe2\x9c\x93 Removed: %s\n", AP[ai].name); list_all(1, 0); return 0;
        }
    }
    printf("x Not found: %s\n", sel); list_all(0, 0); return 1;
}

/* ── move ── */
static int cmd_move(int argc, char **argv) {
    if (argc < 4) { puts("Usage: a move <from> <to>"); return 1; }
    /* Move is complex with display_order in sync files - delegate */
    fallback_py(argc, argv);
}

/* ── scan ── */
static int cmd_scan(int argc, char **argv) { fallback_py(argc, argv); }

/* ── attach ── */
static int cmd_attach(int argc, char **argv) { fallback_py(argc, argv); }

/* ── watch ── */
static int cmd_watch(int argc, char **argv) {
    if (argc < 3) { puts("Usage: a watch <session> [duration]"); return 1; }
    const char *sn = argv[2]; int dur = argc > 3 ? atoi(argv[3]) : 0;
    printf("Watching '%s'%s\n", sn, dur ? "" : " (once)");
    time_t start = time(NULL);
    char last[B] = "";
    while (1) {
        if (dur && time(NULL) - start > dur) break;
        char c[B], out[B]; snprintf(c, B, "tmux capture-pane -t '%s' -p 2>/dev/null", sn);
        if (pcmd(c, out, B) != 0) { printf("x Session %s not found\n", sn); return 1; }
        if (strcmp(out, last)) {
            if (strstr(out, "Are you sure?") || strstr(out, "Continue?") || strstr(out, "[y/N]") || strstr(out, "[Y/n]")) {
                snprintf(c, B, "tmux send-keys -t '%s' y Enter", sn); (void)!system(c);
                puts("\xe2\x9c\x93 Auto-responded");
            }
            snprintf(last, B, "%s", out);
        }
        usleep(100000);
        if (!dur) break;
    }
    return 0;
}

/* ── send ── */
static int cmd_send(int argc, char **argv) {
    if (argc < 4) { puts("Usage: a send <session> <prompt> [--wait] [--no-enter]"); return 1; }
    const char *sn = argv[2];
    if (!tm_has(sn)) { printf("x Session %s not found\n", sn); return 1; }
    char prompt[B] = ""; int wait = 0, enter = 1;
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i],"--wait")) wait = 1;
        else if (!strcmp(argv[i],"--no-enter")) enter = 0;
        else { if(prompt[0]) strcat(prompt," "); strncat(prompt,argv[i],B-strlen(prompt)-2); }
    }
    tm_send(sn, prompt);
    if (enter) { usleep(100000); char c[B]; snprintf(c, B, "tmux send-keys -t '%s' Enter", sn); (void)!system(c); }
    printf("\xe2\x9c\x93 %s '%s'\n", enter?"Sent to":"Inserted into", sn);
    if (wait) {
        printf("Waiting..."); fflush(stdout);
        time_t last_active = time(NULL);
        while (1) {
            char c[B]; snprintf(c, B, "tmux display-message -p -t '%s' '#{window_activity}' 2>/dev/null", sn);
            char out[64]; pcmd(c, out, 64);
            int act = atoi(out);
            if (time(NULL) - act < 2) { last_active = time(NULL); printf("."); fflush(stdout); }
            else if (time(NULL) - last_active > 3) { puts("\n+ Done"); break; }
            usleep(500000);
        }
    }
    return 0;
}

/* ── copy ── */
static int cmd_copy(void) {
    if (!getenv("TMUX")) { puts("x Not in tmux"); return 1; }
    (void)!system("tmux capture-pane -pJ -S -99 > /tmp/ac_copy.tmp");
    /* Simplified: copy last output block */
    char *d = readf("/tmp/ac_copy.tmp", NULL);
    if (!d) return 1;
    /* Find last prompt line (contains $ and @) */
    char *lines[1024]; int nl = 0; char *p = d;
    while (*p && nl < 1024) { lines[nl++] = p; char *e = strchr(p,'\n'); if (e) { *e=0; p=e+1; } else break; }
    int last_prompt = -1;
    for (int i = nl - 1; i >= 0; i--)
        if (strstr(lines[i], "$") && strstr(lines[i], "@")) {
            if (strstr(lines[i], "copy")) { last_prompt = i; continue; }
            /* Find output between this prompt and the 'copy' prompt */
            char out[B] = "";
            for (int j = i + 1; j < last_prompt && j < nl; j++) {
                if (out[0]) strcat(out, "\n");
                strncat(out, lines[j], B - strlen(out) - 2);
            }
            /* Try to copy to clipboard */
            FILE *fp = popen("wl-copy 2>/dev/null || xclip -selection clipboard -i 2>/dev/null", "w");
            if (fp) { fputs(out, fp); pclose(fp); }
            char s[54]; snprintf(s, 54, "%s", out); for (char *c=s;*c;c++) if(*c=='\n')*c=' ';
            printf("\xe2\x9c\x93 %s\n", s);
            free(d); return 0;
        }
    free(d); puts("x No output found"); return 0;
}

/* ── dash ── */
static int cmd_dash(void) {
    char wd[P]; if (!getcwd(wd, P)) strcpy(wd, HOME);
    if (!tm_has("dash")) {
        char c[B];
        snprintf(c, B, "tmux new-session -d -s dash -c '%s'", wd); (void)!system(c);
        snprintf(c, B, "tmux split-window -h -t dash -c '%s' 'sh -c \"a jobs; exec $SHELL\"'", wd); (void)!system(c);
    }
    tm_go("dash"); return 0;
}

/* ── jobs ── */
static int cmd_jobs(int argc, char **argv) { fallback_py(argc, argv); }

/* ── cleanup ── */
static int cmd_cleanup(int argc, char **argv) { fallback_py(argc, argv); }

/* ── tree ── */
static int cmd_tree(int argc, char **argv) {
    init_db(); load_cfg(); load_proj();
    const char *wt = cfget("worktrees_dir"); if (!wt[0]) { char d[P]; snprintf(d,P,"%s/projects/aWorktrees",HOME); wt=d; }
    char cwd[P]; if (!getcwd(cwd, P)) strcpy(cwd, HOME);
    const char *proj = cwd;
    if (argc > 2 && argv[2][0]>='0' && argv[2][0]<='9') { int idx=atoi(argv[2]); if(idx<NPJ) proj=PJ[idx].path; }
    if (!git_in_repo(proj)) { puts("x Not a git repo"); return 1; }
    char ts[32]; time_t now = time(NULL); strftime(ts, 32, "%Y%m%d-%H%M%S", localtime(&now));
    char wp[P]; snprintf(wp, P, "%s/%s-%s", wt, bname(proj), ts);
    char c[B]; snprintf(c, B, "mkdir -p '%s' && git -C '%s' worktree add -b 'wt-%s-%s' '%s' HEAD", wt, proj, bname(proj), ts, wp);
    if (system(c) != 0) { puts("x Failed"); return 1; }
    printf("\xe2\x9c\x93 %s\n", wp);
    const char *sh = getenv("SHELL"); if (!sh) sh = "/bin/bash";
    if (chdir(wp) == 0) execlp(sh, sh, (char*)NULL);
    return 0;
}

/* ── note/task shared ── */
static void do_archive(const char *p) {
    const char *s=strrchr(p,'/'); char a[P],d[P]; snprintf(a,P,"%.*s/.archive",(int)(s-p),p); mkdirp(a);
    snprintf(d,P,"%s%s",a,s); rename(p,d);
}
/* ── note ── */
static void note_save(const char *d, const char *t) {
    struct timespec tp; clock_gettime(CLOCK_REALTIME,&tp); time_t now=tp.tv_sec;
    char ts[32],fn[P],buf[B]; strftime(ts,32,"%Y%m%dT%H%M%S",localtime(&now));
    snprintf(fn,P,"%s/%08x_%s.%09ld.txt",d,(unsigned)(tp.tv_nsec^(unsigned)now),ts,tp.tv_nsec);
    snprintf(buf,B,"Text: %s\nStatus: pending\nDevice: %s\nCreated: %s\n",t,DEV,ts); writef(fn,buf);
}
static char gnp[256][P],gnt[256][512];
static int load_notes(const char *dir, const char *f) {
    DIR *d=opendir(dir); if(!d) return 0; struct dirent *e; int n=0;
    while((e=readdir(d))) { if(e->d_name[0]=='.'||!strstr(e->d_name,".txt")) continue;
        char fp[P]; snprintf(fp,P,"%s/%s",dir,e->d_name); kvs_t kv=kvfile(fp);
        const char *t=kvget(&kv,"Text"),*s=kvget(&kv,"Status");
        if(t&&(!s||!strcmp(s,"pending"))&&(!f||strcasestr(t,f))){if(n<256){snprintf(gnp[n],P,"%s",fp);snprintf(gnt[n],512,"%s",t);} n++;}
    } closedir(d); return n;
}
static int cmd_note(int argc, char **argv) {
    char dir[P]; snprintf(dir,P,"%s/notes",SROOT); mkdirp(dir);
    if(argc>2&&argv[2][0]!='?'){char t[B]="";for(int i=2;i<argc;i++){if(i>2)strcat(t," ");strncat(t,argv[i],B-strlen(t)-2);}
        note_save(dir,t);sync_repo();puts("\xe2\x9c\x93");return 0;}
    sync_repo(); const char *f=(argc>2&&argv[2][0]=='?')?argv[2]+1:NULL; int n=load_notes(dir,f);
    if(!n){puts("a n <text>");return 0;} if(!isatty(STDIN_FILENO)){for(int i=0;i<n&&i<10;i++)puts(gnt[i]);return 0;}
    printf("Notes: %d pending\n  %s\n\n[a]ck [d]el [s]earch [q]uit | type=add\n",n,dir);
    for(int i=0,s=n<256?n:256;i<s;){
        printf("\n[%d/%d] %s\n> ",i+1,n,gnt[i]); char line[B]; if(!fgets(line,B,stdin)) break; line[strcspn(line,"\n")]=0;
        if(line[0]=='q'&&!line[1]) break;
        if(!line[1]&&(line[0]=='a'||line[0]=='d')){do_archive(gnp[i]);sync_repo();puts("\xe2\x9c\x93");memmove(gnp+i,gnp+i+1,(size_t)(s-i-1)*P);memmove(gnt+i,gnt+i+1,(size_t)(s-i-1)*512);n--;s=n<256?n:256;continue;}
        if(line[0]=='s'&&!line[1]){printf("search: ");char q[128];if(fgets(q,128,stdin)){q[strcspn(q,"\n")]=0;n=load_notes(dir,q);s=n<256?n:256;i=0;printf("%d results\n",n);}continue;}
        if(line[0]){note_save(dir,line);sync_repo();n=load_notes(dir,NULL);s=n<256?n:256;printf("\xe2\x9c\x93 [%d]\n",n);continue;}
        i++;
    } return 0;
}
/* ── task ── */
typedef struct{char d[P],t[256],p[8];}Tk;
static Tk T[256];
static int tcmp(const void*a,const void*b){int c=strcmp(((const Tk*)a)->p,((const Tk*)b)->p);return c?c:strcmp(((const Tk*)a)->d,((const Tk*)b)->d);}
static int load_tasks(const char*dir){
    DIR*d=opendir(dir);if(!d)return 0;struct dirent*e;int n=0;
    while((e=readdir(d))&&n<256){
        if(e->d_name[0]=='.'||!strcmp(e->d_name,"README.md"))continue;
        const char*nm=e->d_name;snprintf(T[n].d,P,"%s/%s",dir,nm);
        int hp=strlen(nm)>5&&nm[5]=='-'&&isdigit(nm[0])&&isdigit(nm[1])&&isdigit(nm[2])&&isdigit(nm[3])&&isdigit(nm[4]);
        if(hp){memcpy(T[n].p,nm,5);T[n].p[5]=0;}else strcpy(T[n].p,"50000");
        const char*s=hp?nm+6:nm;int tl;
        const char*u=strchr(s,'_');const char*x=strstr(s,".txt");
        tl=u?(int)(u-s):x?(int)(x-s):(int)strlen(s);
        if(tl>255)tl=255;for(int i=0;i<tl;i++)T[n].t[i]=s[i]=='-'||s[i]=='_'?' ':s[i];T[n].t[tl]=0;n++;
    }closedir(d);qsort(T,(size_t)n,sizeof(Tk),tcmp);return n;
}
static void task_add(const char*dir,const char*t,int pri){
    char sl[64];snprintf(sl,64,"%.32s",t);for(char*p=sl;*p;p++)*p=*p==' '||*p=='/'?'-':*p>='A'&&*p<='Z'?*p+32:*p;
    struct timespec tp;clock_gettime(CLOCK_REALTIME,&tp);
    char ts[32],td[P],fn[P],buf[B];strftime(ts,32,"%Y%m%dT%H%M%S",localtime(&tp.tv_sec));
    snprintf(td,P,"%s/%05d-%s_%s",dir,pri,sl,ts);mkdir(td,0755);
    char sd[P];snprintf(sd,P,"%s/task",td);mkdir(sd,0755);
    snprintf(fn,P,"%s/task/%s.%09ld_%s.txt",td,ts,tp.tv_nsec,DEV);
    snprintf(buf,B,"Text: %s\nDevice: %s\nCreated: %s\n",t,DEV,ts);writef(fn,buf);
}
static void task_printbody(const char*path){
    size_t l;char*r=readf(path,&l);if(!r)return;if(!strncmp(r,"Text: ",6))r+=6;
    for(char*p=r;;){char*nl=strchr(p,'\n');if(nl)*nl=0;
        if(*p&&strncmp(p,"Device: ",8)&&strncmp(p,"Created: ",9))printf("    %s\n",p);
        if(!nl)break;p=nl+1;}
}
static int task_counts(const char*dir,char*out,int sz){
    DIR*d=opendir(dir);if(!d){*out=0;return 0;}struct dirent*e;
    struct{char n[64];int c;}s[32];int nd=0;
    while((e=readdir(d))&&nd<32){if(e->d_name[0]=='.'||e->d_type!=DT_DIR)continue;
        char sd[P];snprintf(sd,P,"%s/%s",dir,e->d_name);DIR*ds=opendir(sd);if(!ds)continue;
        struct dirent*f;int c=0;while((f=readdir(ds)))if(f->d_type==DT_REG&&strstr(f->d_name,".txt"))c++;
        closedir(ds);if(c){snprintf(s[nd].n,64,"%s",e->d_name);s[nd].c=c;nd++;}
    }closedir(d);if(!nd){*out=0;return 0;}
    for(int i=0;i<nd-1;i++)for(int j=i+1;j<nd;j++)if(strcmp(s[i].n,s[j].n)>0){
        char tn[64];int tc;memcpy(tn,s[i].n,64);tc=s[i].c;memcpy(s[i].n,s[j].n,64);s[i].c=s[j].c;memcpy(s[j].n,tn,64);s[j].c=tc;}
    int p=snprintf(out,(size_t)sz," [");for(int i=0;i<nd;i++)p+=snprintf(out+p,(size_t)(sz-p),"%s%d %s",i?", ":"",s[i].c,s[i].n);
    snprintf(out+p,(size_t)(sz-p),"]");return nd;
}
static void dl_norm(const char*in,char*out,size_t sz){
    int y,m,d,h=23,mi=59;time_t now=time(NULL);struct tm*t=localtime(&now);
    if(sscanf(in,"%d-%d-%d %d:%d",&y,&m,&d,&h,&mi)>=3){snprintf(out,sz,"%04d-%02d-%02d %02d:%02d",y,m,d,h,mi);}
    else if(sscanf(in,"%d-%d %d:%d",&m,&d,&h,&mi)>=2){snprintf(out,sz,"%04d-%02d-%02d %02d:%02d",t->tm_year+1900,m,d,h,mi);}
    else snprintf(out,sz,"%s",in);}
static int task_dl(const char*td){char df[P];snprintf(df,P,"%s/deadline.txt",td);
    size_t l;char*c=readf(df,&l);if(!c)return-1;struct tm d={0};int h=23,mi=59;
    if(sscanf(c,"%d-%d-%d %d:%d",&d.tm_year,&d.tm_mon,&d.tm_mday,&h,&mi)<3){free(c);return-1;}
    d.tm_year-=1900;d.tm_mon--;d.tm_hour=h;d.tm_min=mi;free(c);return(int)((mktime(&d)-time(NULL))/86400);}
typedef struct{char n[256];char ts[32];}Ent;
static int entcmp(const void*a,const void*b){return strcmp(((const Ent*)a)->ts,((const Ent*)b)->ts);}
static void ts_human(const char*ts,char*out,size_t sz){
    /* "20260207T033024" → "Feb 7 3:30am" */
    if(!ts||strlen(ts)<15||ts[8]!='T'){snprintf(out,sz,"(original)");return;}
    struct tm t={0};
    t.tm_year=(ts[0]-'0')*1000+(ts[1]-'0')*100+(ts[2]-'0')*10+(ts[3]-'0')-1900;
    t.tm_mon=(ts[4]-'0')*10+(ts[5]-'0')-1;t.tm_mday=(ts[6]-'0')*10+(ts[7]-'0');
    t.tm_hour=(ts[9]-'0')*10+(ts[10]-'0');t.tm_min=(ts[11]-'0')*10+(ts[12]-'0');
    int h=t.tm_hour;const char*ap=h>=12?"pm":"am";h=h%12;if(!h)h=12;
    strftime(out,sz,"%b %-d",mktime(&t)?&t:&t);
    char tmp[32];snprintf(tmp,32," %d:%02d%s",h,t.tm_min,ap);
    strncat(out,tmp,sz-strlen(out)-1);
}
typedef struct{char sid[128];char tmx[128];char ts[32];char wd[P];int st;}Sess;
static int load_sessions(const char*td,Sess*ss,int max){
    DIR*d=opendir(td);if(!d)return 0;struct dirent*e;int ns=0;
    while((e=readdir(d))&&ns<max){
        if(strncmp(e->d_name,"session_",8)||!strstr(e->d_name,".txt"))continue;
        char fp[P];snprintf(fp,P,"%s/%s",td,e->d_name);
        size_t l;char*r=readf(fp,&l);if(!r)continue;
        ss[ns].sid[0]=ss[ns].tmx[0]=ss[ns].ts[0]=ss[ns].wd[0]=0;
        for(char*p=r;;){char*nl=strchr(p,'\n');if(nl)*nl=0;
            if(!strncmp(p,"SessionID: ",11))snprintf(ss[ns].sid,128,"%s",p+11);
            if(!strncmp(p,"TmuxSession: ",13))snprintf(ss[ns].tmx,128,"%s",p+13);
            if(!strncmp(p,"Started: ",9))snprintf(ss[ns].ts,32,"%s",p+9);
            if(!strncmp(p,"Cwd: ",5))snprintf(ss[ns].wd,P,"%s",p+5);
            if(!nl)break;p=nl+1;}
        free(r);
        ss[ns].st=2;
        ns++;}
    closedir(d);
    /* sort by timestamp ascending */
    for(int a=0;a<ns-1;a++)for(int b=a+1;b<ns;b++)if(strcmp(ss[a].ts,ss[b].ts)>0){Sess tmp=ss[a];ss[a]=ss[b];ss[b]=tmp;}
    return ns;
}
static void task_todir(char*p){char tmp[P];snprintf(tmp,P,"%s.tmp",p);rename(p,tmp);mkdir(p,0755);
    char dst[P];snprintf(dst,P,"%s/task.txt",p);rename(tmp,dst);}
static void task_show(int i,int n){
    Sess ss[32];int ns=load_sessions(T[i].d,ss,32);
    char sl[32];if(ns)snprintf(sl,32,"\033[33m%d sess\033[0m",ns);else snprintf(sl,32,"\033[90mnot run\033[0m");
    int dd=task_dl(T[i].d);char dv[32]="";if(dd>=0)snprintf(dv,32,"  %s%dd\033[0m",dd<=1?"\033[31m":dd<=7?"\033[33m":"\033[90m",dd);
    printf("\n\033[1m\xe2\x94\x81\xe2\x94\x81\xe2\x94\x81 %d/%d [P%s] %.50s\033[0m  %s%s\n",i+1,n,T[i].p,T[i].t,sl,dv);
    struct stat st;if(stat(T[i].d,&st)||!S_ISDIR(st.st_mode)){task_printbody(T[i].d);return;}
    /* collect all non-session .txt files with timestamps for chrono sort */
    Ent all[256];int na=0;
    DIR*d=opendir(T[i].d);if(!d)return;struct dirent*e;
    while((e=readdir(d))&&na<256){if(e->d_name[0]=='.'||!strncmp(e->d_name,"session_",8)||!strncmp(e->d_name,"prompt_",7))continue;
        char fp[P];snprintf(fp,P,"%s/%s",T[i].d,e->d_name);
        if(e->d_type==DT_REG&&strstr(e->d_name,".txt")){
            snprintf(all[na].n,256,"%s",fp);
            const char*u=strchr(e->d_name,'_');
            if(u&&strlen(u+1)>=15)snprintf(all[na].ts,32,"%.15s",u+1);
            else snprintf(all[na].ts,32,"0");
            na++;
        }else if(e->d_type==DT_DIR&&strncmp(e->d_name,"prompt_",7)){
            DIR*s=opendir(fp);if(!s)continue;struct dirent*f;
            while((f=readdir(s))&&na<256){if(f->d_type!=DT_REG||!strstr(f->d_name,".txt"))continue;
                snprintf(all[na].n,256,"%s/%s",fp,f->d_name);
                const char*v=f->d_name;if(strlen(v)>=15&&v[8]=='T')snprintf(all[na].ts,32,"%.15s",v);
                else snprintf(all[na].ts,32,"0");
                na++;}
            closedir(s);}}
    closedir(d);qsort(all,(size_t)na,sizeof(Ent),entcmp);
    for(int j=0;j<na;j++){char ht[48];
        if(all[j].ts[0]!='0')ts_human(all[j].ts,ht,48);else snprintf(ht,48,"(original)");
        printf("\n  \033[90m%s\033[0m  text\n",ht);task_printbody(all[j].n);}
    /* show prompt candidates (dirs or legacy .txt files) */
    int pc=2;DIR*pd=opendir(T[i].d);struct dirent*pe;
    while(pd&&(pe=readdir(pd))){
        if(strncmp(pe->d_name,"prompt_",7))continue;
        char pp[P];snprintf(pp,P,"%s/%s",T[i].d,pe->d_name);
        struct stat ps;if(stat(pp,&ps))continue;
        char ht[48];struct tm*mt=localtime(&ps.st_mtime);
        int h=mt->tm_hour%12;if(!h)h=12;
        strftime(ht,48,"%b %-d",mt);char tmp[32];snprintf(tmp,32," %d:%02d%s",h,mt->tm_min,mt->tm_hour>=12?"pm":"am");
        strncat(ht,tmp,48-strlen(ht)-1);
        if(S_ISDIR(ps.st_mode)){
            char fv[P]="",mv[64]="",cfp[P];
            snprintf(cfp,P,"%s/folder.txt",pp);{size_t l;char*c=readf(cfp,&l);if(c){snprintf(fv,P,"%s",c);fv[strcspn(fv,"\n")]=0;free(c);}}
            snprintf(cfp,P,"%s/model.txt",pp);{size_t l;char*c=readf(cfp,&l);if(c){snprintf(mv,64,"%s",c);mv[strcspn(mv,"\n")]=0;free(c);}}
            snprintf(cfp,P,"%s/prompt.txt",pp);
            printf("\n  \033[90m%s\033[0m  \033[35mprompt #%d\033[0m  \033[90m%s  %s\033[0m\n",ht,pc,mv,fv);
            task_printbody(cfp);
        }else if(S_ISREG(ps.st_mode)){
            printf("\n  \033[90m%s\033[0m  \033[35mprompt #%d\033[0m\n",ht,pc);
            task_printbody(pp);
        }else continue;
        pc++;}
    if(pd)closedir(pd);
    /* show all sessions */
    for(int j=0;j<ns;j++){char ht[48];ts_human(ss[j].ts,ht,48);
        if(ss[j].wd[0])printf("  \033[33msess\033[0m  %s  cd %s && claude -r %s\n",ht,ss[j].wd,ss[j].sid);
        else printf("  \033[33msess\033[0m  %s  claude -r %s\n",ht,ss[j].sid);}
}
static void task_repri(int x,int pv){
    if(pv<0)pv=0;if(pv>99999)pv=99999;char np[8];snprintf(np,8,"%05d",pv);
    char*bn=strrchr(T[x].d,'/');if(!bn)return;bn++;char nw[P];
    if(strlen(bn)>5&&bn[5]=='-'&&isdigit(bn[0]))snprintf(nw,P,"%s-%s",np,bn+6);else snprintf(nw,P,"%s-%s",np,bn);
    char dst[P];snprintf(dst,P,"%.*s/%s",(int)(bn-1-T[x].d),T[x].d,nw);
    rename(T[x].d,dst);printf("\xe2\x9c\x93 P%s %.40s\n",np,T[x].t);
}
static int task_getkey(void){
    struct termios old,raw;tcgetattr(0,&old);raw=old;
    raw.c_lflag&=~(tcflag_t)(ICANON|ECHO);raw.c_cc[VMIN]=1;raw.c_cc[VTIME]=0;
    tcsetattr(0,TCSAFLUSH,&raw);int c=getchar();tcsetattr(0,TCSAFLUSH,&old);return c;
}
static int cmd_task(int argc,char**argv){
    char dir[P];snprintf(dir,P,"%s/tasks",SROOT);mkdirp(dir);const char*sub=argc>2?argv[2]:NULL;
    if(!sub){
        printf("  a task l          list tasks\n");
        printf("  a task r          review tasks (send to claude, manage sessions)\n");
        printf("  a task add <t>    add task (prefix 5-digit priority, default 50000)\n");
        printf("  a task d #        archive task #\n");
        printf("  a task pri # N    set priority of task # to N\n");
        printf("  a task deadline # YYYY-MM-DD  set deadline\n");
        printf("  a task due        list by deadline\n");
        printf("  a task sync       sync tasks\n");
        printf("\n  Tasks:   %s\n",dir);
        char ctxdir[P];snprintf(ctxdir,P,"%s/context",SROOT);
        printf("  Context: %s\n",ctxdir);
        printf("  Add .txt files to context dir for agent prompts (default.txt auto-enabled)\n");
        return 0;}
    if(*sub=='l'){int n=load_tasks(dir);if(!n){puts("No tasks");return 0;}
        for(int i=0;i<n;i++){char ct[256];task_counts(T[i].d,ct,256);
            printf("  %d. P%s %.50s%s\n",i+1,T[i].p,T[i].t,ct);}return 0;}
    int grn=0;
    if(0){review:;} /* due r jumps here with T[] pre-loaded */
    if(grn||isdigit(*sub)||!strcmp(sub,"rev")||!strcmp(sub,"review")||!strcmp(sub,"r")||!strcmp(sub,"t")){
        int n=grn?grn:load_tasks(dir);if(!n){puts("No tasks");return 0;}
        {int i=isdigit(*sub)?atoi(sub)-1:argc>3?atoi(argv[3])-1:0;if(i<0||i>=n)i=0;int show=1;
        while(i<n){if(show)task_show(i,n);show=1;
            printf("\n  [e]archive [a]dd [c]prompt [r]un [g]o [d]eadline [p]ri  [j]next [k]back [q]uit  ");fflush(stdout);
            int k=task_getkey();putchar('\n');
            if(k=='e'){do_archive(T[i].d);printf("\xe2\x9c\x93 Archived: %.40s\n",T[i].t);
                sync_bg();n=load_tasks(dir);if(i>=n)i=n-1;if(i<0)break;}
            else if(k=='a'){
                {struct stat st;if(!stat(T[i].d,&st)&&!S_ISDIR(st.st_mode))task_todir(T[i].d);}
                char sd[P];snprintf(sd,P,"%s/task",T[i].d);
                printf("  Text: ");fflush(stdout);
                char buf[B];if(fgets(buf,B,stdin)){buf[strcspn(buf,"\n")]=0;if(buf[0]){
                    mkdir(sd,0755);
                    struct timespec tp;clock_gettime(CLOCK_REALTIME,&tp);
                    char ts[32],fn[P];strftime(ts,32,"%Y%m%dT%H%M%S",localtime(&tp.tv_sec));
                    snprintf(fn,P,"%s/%s.%09ld_%s.txt",sd,ts,tp.tv_nsec,DEV);
                    char fb[B];snprintf(fb,B,"Text: %s\nDevice: %s\nCreated: %s\n",buf,DEV,ts);writef(fn,fb);
                    printf("\xe2\x9c\x93 Added\n");sync_bg();}}
                /* re-show task so new addition is visible */
                task_show(i,n);show=0;}
            else if(k=='c'){docreate:
                {struct stat st;if(!stat(T[i].d,&st)&&!S_ISDIR(st.st_mode))task_todir(T[i].d);}
                printf("  Name: ");fflush(stdout);
                char nm[64];if(!fgets(nm,64,stdin)||!nm[0]||nm[0]=='\n'){show=0;continue;}
                nm[strcspn(nm,"\n")]=0;
                printf("  Prompt text: ");fflush(stdout);
                char pt[B];if(!fgets(pt,B,stdin)||!pt[0]||pt[0]=='\n'){show=0;continue;}
                pt[strcspn(pt,"\n")]=0;
                printf("  Folder [cwd]: ");fflush(stdout);
                char fd[P];if(!fgets(fd,P,stdin))fd[0]=0;fd[strcspn(fd,"\n")]=0;
                if(!fd[0])(void)!getcwd(fd,P);
                printf("  Model [opus]: ");fflush(stdout);
                char md[64];if(!fgets(md,64,stdin))md[0]=0;md[strcspn(md,"\n")]=0;
                if(!md[0])snprintf(md,64,"opus");
                char pd[P];snprintf(pd,P,"%s/prompt_%s",T[i].d,nm);mkdir(pd,0755);
                char pf[P];
                snprintf(pf,P,"%s/prompt.txt",pd);writef(pf,pt);
                snprintf(pf,P,"%s/folder.txt",pd);writef(pf,fd);
                snprintf(pf,P,"%s/model.txt",pd);writef(pf,md);
                printf("\xe2\x9c\x93 Added prompt: %s\n",nm);
                task_show(i,n);show=0;}
            else if(k=='r'){
                printf("  Prompt # or [n]ew: ");fflush(stdout);
                char pb[8];if(!fgets(pb,8,stdin)||!pb[0]||pb[0]=='\n'){show=0;continue;}
                pb[strcspn(pb,"\n")]=0;
                if(*pb=='n'||*pb=='c'){k='c';goto docreate;}
                int ci=atoi(pb);if(ci<1){show=0;continue;}
                /* collect task text */
                char body[B]="";int bl=0;
                struct stat ss;if(!stat(T[i].d,&ss)&&S_ISDIR(ss.st_mode)){
                    DIR*dd=opendir(T[i].d);struct dirent*ee;
                    while(dd&&(ee=readdir(dd))){if(ee->d_name[0]=='.')continue;
                        char fp[P];snprintf(fp,P,"%s/%s",T[i].d,ee->d_name);
                        if(ee->d_type==DT_REG&&strstr(ee->d_name,".txt")&&!strstr(ee->d_name,"session")&&!strstr(ee->d_name,"prompt_")){
                            size_t fl;char*fc=readf(fp,&fl);if(fc){bl+=snprintf(body+bl,(size_t)(B-bl),"%s\n",fc);free(fc);}}
                        else if(ee->d_type==DT_DIR&&strncmp(ee->d_name,"prompt_",7)){DIR*sd=opendir(fp);struct dirent*ff;
                            while(sd&&(ff=readdir(sd))){if(ff->d_type!=DT_REG||!strstr(ff->d_name,".txt"))continue;
                                char sfp[P];snprintf(sfp,P,"%s/%s",fp,ff->d_name);
                                size_t fl;char*fc=readf(sfp,&fl);if(fc){bl+=snprintf(body+bl,(size_t)(B-bl),"%s\n",fc);free(fc);}}
                            if(sd)closedir(sd);}}
                    if(dd)closedir(dd);
                }else{bl=snprintf(body,B,"%s",T[i].t);}
                /* build prompt from candidate */
                char prompt[B],pmodel[64]="opus",pfolder[P]="";
                (void)!getcwd(pfolder,P);
                if(ci==1){snprintf(prompt,B,"%s",body);}
                else{int cp=2;DIR*pd=opendir(T[i].d);struct dirent*pe;int found=0;
                    while(pd&&(pe=readdir(pd))){
                        if(strncmp(pe->d_name,"prompt_",7))continue;
                        char pp[P];snprintf(pp,P,"%s/%s",T[i].d,pe->d_name);
                        struct stat ps;if(stat(pp,&ps))continue;
                        if(S_ISDIR(ps.st_mode)){
                            if(cp==ci){char cfp[P];
                                snprintf(cfp,P,"%s/prompt.txt",pp);
                                size_t cl;char*cc=readf(cfp,&cl);
                                if(cc){snprintf(prompt,B,"%s",cc);free(cc);found=1;}
                                snprintf(cfp,P,"%s/model.txt",pp);cc=readf(cfp,&cl);
                                if(cc){snprintf(pmodel,64,"%s",cc);pmodel[strcspn(pmodel,"\n")]=0;free(cc);}
                                snprintf(cfp,P,"%s/folder.txt",pp);cc=readf(cfp,&cl);
                                if(cc){snprintf(pfolder,P,"%s",cc);pfolder[strcspn(pfolder,"\n")]=0;free(cc);}
                                break;}
                        }else if(S_ISREG(ps.st_mode)){
                            if(cp==ci){size_t cl;char*cc=readf(pp,&cl);
                                if(cc){snprintf(prompt,B,"%s",cc);free(cc);found=1;}
                                break;}
                        }else continue;
                        cp++;}
                    if(pd)closedir(pd);
                    if(!found){printf("  x Invalid prompt #\n");show=0;continue;}}
                /* load context files */
                char ctxdir[P];snprintf(ctxdir,P,"%s/context",SROOT);mkdirp(ctxdir);
                {char df[P];snprintf(df,P,"%s/default.txt",ctxdir);struct stat ds;if(stat(df,&ds))writef(df,"");}
                char ctxn[16][128];int ctxon[16]={0};int nctx=0;
                {DIR*cd=opendir(ctxdir);struct dirent*ce;
                while(cd&&(ce=readdir(cd))&&nctx<16){
                    if(ce->d_name[0]=='.'||!strstr(ce->d_name,".txt"))continue;
                    snprintf(ctxn[nctx],128,"%s",ce->d_name);
                    ctxon[nctx]=!strcmp(ce->d_name,"default.txt");
                    nctx++;}
                if(cd)closedir(cd);}
                /* preview loop — edit folder/model/context before confirming */
                for(;;){
                /* build final prompt with context prepended */
                char fprompt[B];int fl=0;
                for(int j=0;j<nctx;j++){if(!ctxon[j])continue;
                    char cf[P];snprintf(cf,P,"%s/%s",ctxdir,ctxn[j]);
                    size_t cl;char*cc=readf(cf,&cl);
                    if(cc){fl+=snprintf(fprompt+fl,(size_t)(B-fl),"%s\n",cc);free(cc);}}
                fl+=snprintf(fprompt+fl,(size_t)(B-fl),"%s",prompt);
                printf("\n\033[1m\xe2\x94\x80\xe2\x94\x80 Preview \xe2\x94\x80\xe2\x94\x80\033[0m\n");
                struct stat fs;int fok=!stat(pfolder,&fs)&&S_ISDIR(fs.st_mode);
                printf("  \033[1mFolder:\033[0m  %s%s\n",pfolder,fok?"":" \033[31m(not found)\033[0m");
                printf("  \033[1mModel:\033[0m   %s\n",pmodel);
                printf("  \033[1mContext:\033[0m ");
                {int any=0;for(int j=0;j<nctx;j++)if(ctxon[j]){if(any)printf(", ");printf("%s",ctxn[j]);any++;}
                if(!any)printf("none");}putchar('\n');
                printf("\033[36m%s\033[0m\n",fprompt);
                printf("\033[1m\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\033[0m\n");
                printf("  [y]send [f]older [m]odel [c]ontext [n]cancel ");fflush(stdout);
                int ck=task_getkey();putchar('\n');
                if(ck=='f'){printf("  Folder [%s]: ",pfolder);fflush(stdout);
                    char nf[P];if(fgets(nf,P,stdin)&&nf[0]&&nf[0]!='\n'){nf[strcspn(nf,"\n")]=0;snprintf(pfolder,P,"%s",nf);}
                    continue;}
                if(ck=='m'){printf("  Model [%s]: ",pmodel);fflush(stdout);
                    char nm[64];if(fgets(nm,64,stdin)&&nm[0]&&nm[0]!='\n'){nm[strcspn(nm,"\n")]=0;snprintf(pmodel,64,"%s",nm);}
                    continue;}
                if(ck=='c'){printf("  \033[90mContext dir: %s\033[0m\n  cd %s\n",ctxdir,ctxdir);
                    if(!nctx)printf("  (empty — add .txt files to enable context)\n");
                    for(int j=0;j<nctx;j++)printf("  %d. [%c] %s\n",j+1,ctxon[j]?'x':' ',ctxn[j]);
                    printf("  Toggle # (enter to skip): ");fflush(stdout);
                    char tb[8];if(fgets(tb,8,stdin)&&tb[0]&&tb[0]!='\n'){int ti=atoi(tb)-1;if(ti>=0&&ti<nctx)ctxon[ti]=!ctxon[ti];}
                    continue;}
                if(ck!='y'&&ck!='Y'){printf("  Cancelled.\n");break;}
                if(!fok){printf("  \033[31mx Folder does not exist\033[0m\n");continue;}
                /* confirmed — spawn */
                char sid[64];sid[0]=0;
                {char ub[48];if(!pcmd("uuidgen",ub,48)){ub[strcspn(ub,"\n")]=0;snprintf(sid,64,"%s",ub);}}
                struct timespec tp;clock_gettime(CLOCK_REALTIME,&tp);
                char tss[32];strftime(tss,32,"%Y%m%dT%H%M%S",localtime(&tp.tv_sec));
                char tmx[64];snprintf(tmx,64,"task-%d-%ld",i+1,tp.tv_sec);
                char sf[P];snprintf(sf,P,"%s/session_%s_%s.txt",T[i].d,tss,DEV);
                char sm[B];snprintf(sm,B,"SessionID: %s\nTmuxSession: %s\nModel: %s\nStarted: %s\nDevice: %s\nCwd: %s\n",sid,tmx,pmodel,tss,DEV,pfolder);
                writef(sf,sm);
                char pf[P];snprintf(pf,P,"/tmp/a_prompt_%s.txt",tss);
                writef(pf,fprompt);
                char rf[P];snprintf(rf,P,"/tmp/a_run_%s.sh",tss);
                char rs[B];snprintf(rs,B,"#!/bin/sh\ncd '%s'\nclaude --session-id %s --model %s --dangerously-skip-permissions \"$(cat %s)\"\n",pfolder,sid,pmodel,pf);
                writef(rf,rs);chmod(rf,0755);
                char cmd[B];snprintf(cmd,B,"tmux new-session -d -s '%s' '%s'",tmx,rf);
                (void)!system(cmd);
                printf("\xe2\x9c\x93 Running with claude (%s)\n  tmux attach -t %s\n  cd %s && claude -r %s\n",pmodel,tmx,pfolder,sid);
                break;}/* end preview loop */
                show=0;}
            else if(k=='g'){
                /* go: attach most recent live, or resume most recent dead */
                Sess ss[32];int ns=load_sessions(T[i].d,ss,32);
                if(!ns){printf("  Not run yet. Press [r] to run with claude.\n");show=0;}
                else{/* pick most recent live, else most recent review (last in sorted list) */
                    int pick=-1;
                    for(int j=ns-1;j>=0;j--)if(ss[j].st==1){pick=j;break;}
                    if(pick<0)pick=ns-1;
                    if(ss[pick].st==1){char cmd[P];snprintf(cmd,P,"tmux attach -t '%s'",ss[pick].tmx);
                        (void)!system(cmd);}
                    else{char cmd[P];snprintf(cmd,P,"claude -r %s",ss[pick].sid);
                        printf("  Resuming claude session...\n");(void)!system(cmd);}
                    show=0;}}
            else if(k=='p'){printf("  Priority (1-99999): ");fflush(stdout);
                char buf[16];if(fgets(buf,16,stdin)){task_repri(i,atoi(buf));sync_bg();n=load_tasks(dir);}}
            else if(k=='d'){
                {struct stat st;if(!stat(T[i].d,&st)&&!S_ISDIR(st.st_mode))task_todir(T[i].d);}
                printf("  Deadline (MM-DD [HH:MM]): ");fflush(stdout);
                char db[32];if(fgets(db,32,stdin)&&db[0]&&db[0]!='\n'){db[strcspn(db,"\n")]=0;
                    char dn[32];dl_norm(db,dn,32);
                    char df[P];snprintf(df,P,"%s/deadline.txt",T[i].d);writef(df,dn);printf("\xe2\x9c\x93 %s\n",dn);sync_bg();}
                task_show(i,n);show=0;}
            else if(k=='k'){if(i>0)i--;else{printf("  (first task)\n");show=0;}}
            else if(k=='q'||k==3||k==27)break;else if(k=='j')i++;else{show=0;}}
        if(i>=n)puts("Done");return 0;}}
    if(!strcmp(sub,"pri")){if(argc<5){puts("a task pri # N");return 1;}
        int n=load_tasks(dir),x=atoi(argv[3])-1;if(x<0||x>=n){puts("x Invalid");return 1;}
        task_repri(x,atoi(argv[4]));sync_bg();return 0;}
    if(!strcmp(sub,"add")||!strcmp(sub,"a")){if(argc<4){puts("a task add [PPPPP] <text>");return 1;}
        int pri=50000,si=3;
        if(strlen(argv[3])==5&&isdigit(argv[3][0])&&isdigit(argv[3][1])&&isdigit(argv[3][2])&&isdigit(argv[3][3])&&isdigit(argv[3][4])){
            pri=atoi(argv[3]);si=4;if(si>=argc){puts("a task add [PPPPP] <text>");return 1;}}
        char t[B]="";for(int i=si;i<argc;i++){if(i>si)strcat(t," ");strncat(t,argv[i],B-strlen(t)-2);}
        task_add(dir,t,pri);printf("\xe2\x9c\x93 P%05d %s\n",pri,t);sync_bg();return 0;}
    if(*sub=='d'&&!sub[1]){if(argc<4){puts("a task d #");return 1;}int n=load_tasks(dir),x=atoi(argv[3])-1;
        if(x<0||x>=n){puts("x Invalid");return 1;}do_archive(T[x].d);printf("\xe2\x9c\x93 %.40s\n",T[x].t);sync_bg();return 0;}
    if(!strcmp(sub,"deadline")){if(argc<5){puts("a task deadline # MM-DD [HH:MM]");return 1;}
        int n=load_tasks(dir),x=atoi(argv[3])-1;if(x<0||x>=n){puts("x Invalid");return 1;}
        char raw[64]="";for(int j=4;j<argc;j++){if(j>4)strcat(raw," ");strncat(raw,argv[j],63-strlen(raw));}
        char dn[32];dl_norm(raw,dn,32);
        char df[P];snprintf(df,P,"%s/deadline.txt",T[x].d);writef(df,dn);printf("\xe2\x9c\x93 %s\n",dn);sync_bg();return 0;}
    if(!strcmp(sub,"due")){int n=load_tasks(dir);if(!n){puts("No tasks");return 0;}
        int ix[256];int dl[256];int nd=0;
        for(int i=0;i<n;i++){int d=task_dl(T[i].d);if(d>=0){ix[nd]=i;dl[nd]=d;nd++;}}
        if(!nd){puts("No deadlines");return 0;}
        for(int a=0;a<nd-1;a++)for(int b=a+1;b<nd;b++)if(dl[a]>dl[b]){int t=ix[a];ix[a]=ix[b];ix[b]=t;t=dl[a];dl[a]=dl[b];dl[b]=t;}
        Tk D[256];for(int j=0;j<nd;j++)D[j]=T[ix[j]];memcpy(T,D,(size_t)nd*sizeof(Tk));
        if(argc>3&&(*argv[3]=='r'||*argv[3]=='t')){sub="r";grn=nd;goto review;}
        for(int j=0;j<nd;j++)printf("  %s%dd\033[0m P%s %.50s\n",dl[j]<=1?"\033[31m":dl[j]<=7?"\033[33m":"\033[90m",dl[j],T[j].p,T[j].t);return 0;}
    if(!strcmp(sub,"bench")){struct timespec t0,t1;
        clock_gettime(CLOCK_MONOTONIC,&t0);int n=0;for(int j=0;j<100;j++)n=load_tasks(dir);
        clock_gettime(CLOCK_MONOTONIC,&t1);
        printf("load_tasks(%d): %.0f us avg (x100)\n",n,((double)(t1.tv_sec-t0.tv_sec)*1e9+(double)(t1.tv_nsec-t0.tv_nsec))/100/1e3);
        fflush(stdout);int fd=dup(1);(void)!freopen("/dev/null","w",stdout);
        int m=n<10?n:10;
        clock_gettime(CLOCK_MONOTONIC,&t0);for(int j=0;j<m;j++)task_show(j,n);
        clock_gettime(CLOCK_MONOTONIC,&t1);fflush(stdout);dup2(fd,1);close(fd);stdout=fdopen(1,"w");
        double us=((double)(t1.tv_sec-t0.tv_sec)*1e9+(double)(t1.tv_nsec-t0.tv_nsec))/1e3;
        printf("task_show(x%d): %.0f us total, %.0f us/task\n",m,us,us/m);
        return 0;}
    if(!strcmp(sub,"sync")){sync_repo();puts("\xe2\x9c\x93");return 0;}
    if(!strcmp(sub,"0")||!strcmp(sub,"s")||!strcmp(sub,"p")||!strcmp(sub,"do")){
        const char*x=*sub=='0'?"priority":!strcmp(sub,"s")?"suggest":!strcmp(sub,"p")?"plan":"do";
        char cmd[64];snprintf(cmd,64,"x.%s",x);execvp("a",(char*[]){"a",cmd,NULL});return 1;}
    if(*sub=='1'){char pf[P];snprintf(pf,P,"%s/common/prompts/task1.txt",SROOT);
        size_t l;char*r=readf(pf,&l);if(!r){printf("x No prompt: %s\n",pf);return 1;}
        while(l>0&&(r[l-1]=='\n'||r[l-1]==' '))r[--l]=0;
        printf("Prompt: %s\n",pf);execvp("a",(char*[]){"a","c",r,NULL});return 1;}
    if(argc>4&&isdigit(argv[3][0])){
        int n=load_tasks(dir),x=atoi(argv[3])-1;
        if(x>=0&&x<n){
        {struct stat st;if(!stat(T[x].d,&st)&&!S_ISDIR(st.st_mode))task_todir(T[x].d);}
        char sd[P];snprintf(sd,P,"%s/%s",T[x].d,sub);mkdirp(sd);
        struct timespec tp;clock_gettime(CLOCK_REALTIME,&tp);
        char ts[32],fn[P];strftime(ts,32,"%Y%m%dT%H%M%S",localtime(&tp.tv_sec));
        char t[B]="";for(int i=4;i<argc;i++){if(i>4)strcat(t," ");strncat(t,argv[i],B-strlen(t)-2);}
        snprintf(fn,P,"%s/%s.%09ld_%s.txt",sd,ts,tp.tv_nsec,DEV);writef(fn,t);
        printf("\xe2\x9c\x93 %s: %.40s\n",sub,t);sync_bg();return 0;}}
    {int pri=50000,si=2;
    if(argc>2&&strlen(argv[2])==5&&isdigit(argv[2][0])&&isdigit(argv[2][1])&&isdigit(argv[2][2])&&isdigit(argv[2][3])&&isdigit(argv[2][4])){
        pri=atoi(argv[2]);si=3;if(si>=argc){puts("a task [PPPPP] <text>");return 1;}}
    char t[B]="";for(int i=si;i<argc;i++){if(i>si)strcat(t," ");strncat(t,argv[i],B-strlen(t)-2);}
    task_add(dir,t,pri);printf("\xe2\x9c\x93 P%05d %s\n",pri,t);sync_bg();return 0;}
}

/* ── ssh ── */
static int cmd_ssh(int argc, char **argv) {
    char dir[P]; snprintf(dir, P, "%s/ssh", SROOT); mkdirp(dir);
    sync_repo();
    /* Load hosts */
    typedef struct { char name[128], host[256], pw[256]; } host_t;
    host_t hosts[32]; int nh = 0;
    char paths[32][P]; int np = listdir(dir, paths, 32);
    for (int i = 0; i < np && nh < 32; i++) {
        kvs_t kv = kvfile(paths[i]);
        const char *n = kvget(&kv, "Name"); if (!n) continue;
        snprintf(hosts[nh].name, 128, "%s", n);
        const char *h = kvget(&kv, "Host"); snprintf(hosts[nh].host, 256, "%s", h?h:"");
        const char *p = kvget(&kv, "Password"); snprintf(hosts[nh].pw, 256, "%s", p?p:"");
        nh++;
    }
    const char *sub = argc > 2 ? argv[2] : NULL;
    /* No args: show status + hosts */
    if (!sub) {
        char url[B]; snprintf(url, B, "git -C '%s' remote get-url origin 2>/dev/null", dir);
        char urlout[512]; pcmd(url, urlout, 512); urlout[strcspn(urlout,"\n")] = 0;
        int sshd_on=!system("pgrep -x sshd >/dev/null 2>&1");
        printf("SSH  sshd: %s\n  %s\n  %s\n\n", sshd_on?"\033[32mon\033[0m":"\033[31moff\033[0m  a ssh start", dir, urlout);
        for (int i = 0; i < nh; i++) {
            int self=!strcmp(hosts[i].name,DEV);
            printf("  %d. %s%s%s: %s%s%s\n", i, self?"\033[32m":"", hosts[i].name, self?" (self)\033[0m":"", hosts[i].host, hosts[i].pw[0]?" [pw]":"", self&&!sshd_on?" [off]":"");
        }
        if (!nh) puts("  (none)");
        puts("\nConnect: a ssh <#>          Self:  a ssh self\nRun:     a ssh <#> <cmd>    Start: a ssh start\nSetup:   a ssh setup        Stop:  a ssh stop\nAdd:     a ssh add          (interactive)");
        return 0;
    }
    /* start/stop/status */
    if (!strcmp(sub,"start")) { (void)!system("sshd 2>/dev/null || sudo /usr/sbin/sshd"); puts("\xe2\x9c\x93 sshd started"); return 0; }
    if (!strcmp(sub,"stop")) { (void)!system("pkill -x sshd 2>/dev/null || sudo pkill -x sshd"); puts("\xe2\x9c\x93 sshd stopped"); return 0; }
    if (!strcmp(sub,"status") || !strcmp(sub,"s")) { (void)!system("pgrep -x sshd >/dev/null && echo '✓ running' || echo 'x stopped'"); return 0; }
    /* add */
    if (!strcmp(sub,"add")) {
        printf("Host (user@ip): "); char h[256]; if (!fgets(h,256,stdin)) return 1; h[strcspn(h,"\n")]=0;
        printf("Name: "); char n[128]; if (!fgets(n,128,stdin)) return 1; n[strcspn(n,"\n")]=0;
        if (!n[0]) { char *at=strchr(h,'@'); snprintf(n,128,"%s",at?at+1:h); }
        printf("Password? "); char pw[256]; if (!fgets(pw,256,stdin)) return 1; pw[strcspn(pw,"\n")]=0;
        char f[P]; snprintf(f, P, "%s/%s.txt", dir, n);
        char data[B]; snprintf(data, B, "Name: %s\nHost: %s\n%s%s%s", n, h, pw[0]?"Password: ":"", pw, pw[0]?"\n":"");
        writef(f, data); sync_repo();
        printf("\xe2\x9c\x93 %s=%s\n", n, h); return 0;
    }
    /* rm */
    if (!strcmp(sub,"rm") && argc > 3) {
        int idx = atoi(argv[3]);
        if (idx >= 0 && idx < nh) {
            char f[P]; snprintf(f, P, "%s/%s.txt", dir, hosts[idx].name);
            unlink(f); sync_repo(); printf("\xe2\x9c\x93 rm %s\n", hosts[idx].name);
        }
        return 0;
    }
    /* self: register this device */
    if (!strcmp(sub,"self")) {
        char user[128]="",ip[128]="",port[8]="22",host[256];
        const char*u=getenv("USER");if(!u)u=getenv("LOGNAME");if(u)snprintf(user,128,"%s",u);
        /* detect LAN IP: try hostname -I, then ifconfig for 192.168.x, then any non-loopback */
        pcmd("hostname -I 2>/dev/null | awk '{print $1}'",ip,128);ip[strcspn(ip,"\n")]=0;
        if(!ip[0]){pcmd("ifconfig 2>/dev/null | grep 'inet ' | grep -v 127 | grep '192\\.' | awk '{print $2}' | head -1",ip,128);ip[strcspn(ip,"\n")]=0;}
        if(!ip[0]){pcmd("ifconfig 2>/dev/null | grep 'inet ' | grep -v 127 | awk '{print $2}' | head -1",ip,128);ip[strcspn(ip,"\n")]=0;}
        /* detect sshd port */
        char pp[64];if(!pcmd("grep -m1 '^Port ' /etc/ssh/sshd_config 2>/dev/null || grep -m1 '^Port ' $PREFIX/etc/ssh/sshd_config 2>/dev/null",pp,64)){
            char*sp=pp;while(*sp&&!isdigit((unsigned char)*sp))sp++;pp[strcspn(pp,"\n")]=0;if(*sp)snprintf(port,8,"%s",sp);}
        if(!strcmp(port,"22"))snprintf(host,256,"%s@%s",user,ip);
        else snprintf(host,256,"%s@%s:%s",user,ip,port);
        printf("Name: %s\nHost: %s\n",DEV,host);
        char f[P];snprintf(f,P,"%s/%s.txt",dir,DEV);
        char data[B];snprintf(data,B,"Name: %s\nHost: %s\n",DEV,host);
        writef(f,data);sync_repo();printf("\xe2\x9c\x93 registered\n");return 0;
    }
    /* setup */
    if (!strcmp(sub,"setup")) { fallback_py(argc, argv); }
    /* all "cmd" */
    if ((!strcmp(sub,"all") || !strcmp(sub,"*")) && argc > 3) {
        char cmd[B] = ""; for (int i=3;i<argc;i++) { if(i>3) strcat(cmd," "); strncat(cmd,argv[i],B-strlen(cmd)-2); }
        for (int i = 0; i < nh; i++) {
            char c[B*2]; char *hp = hosts[i].host; char port[8] = "22";
            char *colon = strrchr(hp, ':');
            if (colon) { snprintf(port, 8, "%s", colon+1); *colon = 0; }
            if (hosts[i].pw[0])
                snprintf(c, sizeof(c), "sshpass -p '%s' ssh -oConnectTimeout=5 -oStrictHostKeyChecking=no -p %s '%s' 'bash -ic %s' 2>&1", hosts[i].pw, port, hp, cmd);
            else
                snprintf(c, sizeof(c), "ssh -oConnectTimeout=5 -oStrictHostKeyChecking=no -p %s '%s' 'bash -ic %s' 2>&1", port, hp, cmd);
            if (colon) *colon = ':';
            char out[B]; int r = pcmd(c, out, B);
            printf("\n%s %s\n", r==0?"\xe2\x9c\x93":"x", hosts[i].name);
            if (out[0]) printf("%s", out);
        }
        return 0;
    }
    /* Connect by number or name */
    int idx = -1;
    if (sub[0] >= '0' && sub[0] <= '9') idx = atoi(sub);
    else { for (int i=0;i<nh;i++) if (!strcmp(hosts[i].name,sub)) { idx=i; break; } }
    if (idx < 0 || idx >= nh) { printf("x No host %s\n", sub); return 1; }
    char *hp = hosts[idx].host; char hbuf[256]; snprintf(hbuf,256,"%s",hp);
    char port[8] = "22"; char *colon = strrchr(hbuf, ':');
    if (colon) { snprintf(port, 8, "%s", colon+1); *colon = 0; }
    /* Run command on remote */
    if (argc > 3) {
        char cmd[B] = ""; for (int i=3;i<argc;i++) { if(i>3) strcat(cmd," "); strncat(cmd,argv[i],B-strlen(cmd)-2); }
        char c[B*2];
        if (hosts[idx].pw[0])
            snprintf(c, sizeof(c), "sshpass -p '%s' ssh -tt -oStrictHostKeyChecking=no -p %s '%s' 'bash -ic '\"'\"'%s'\"'\"'' 2>&1", hosts[idx].pw, port, hbuf, cmd);
        else
            snprintf(c, sizeof(c), "ssh -tt -oStrictHostKeyChecking=no -p %s '%s' 'bash -ic '\"'\"'%s'\"'\"'' 2>&1", port, hbuf, cmd);
        return system(c) >> 8;
    }
    /* Interactive SSH */
    printf("Connecting to %s...\n", hosts[idx].name);
    if (hosts[idx].pw[0])
        execlp("sshpass", "sshpass", "-p", hosts[idx].pw, "ssh", "-tt", "-o", "StrictHostKeyChecking=accept-new", "-p", port, hbuf, (char*)NULL);
    else
        execlp("ssh", "ssh", "-tt", "-o", "StrictHostKeyChecking=accept-new", "-p", port, hbuf, (char*)NULL);
    return 1;
}

/* ── hub ── */
static int cmd_hub(int argc, char **argv) { fallback_py(argc, argv); }

/* ── log ── */
static int cmd_log(int argc, char **argv) {
    const char *sub = argc > 2 ? argv[2] : NULL;
    if (sub && !strcmp(sub, "sync")) { fallback_py(argc, argv); }
    if (sub && !strcmp(sub, "grab")) { fallback_py(argc, argv); }

    char adir[P]; snprintf(adir, P, "%s/git/activity", AROOT);

    if (sub && !strcmp(sub, "all")) {
        char c[B]; snprintf(c, B, "cat $(ls '%s'/*.txt 2>/dev/null | sort) 2>/dev/null", adir);
        (void)!system(c); return 0;
    }

    if (sub && sub[0] >= '0' && sub[0] <= '9') {
        /* View transcript by number */
        mkdirp(LOGDIR);
        char c[B], out[B*4];
        snprintf(c, B, "ls -t '%s'/*.log 2>/dev/null | head -20", LOGDIR);
        pcmd(c, out, sizeof(out));
        char *lines[20]; int n = 0; char *p = out;
        while (*p && n < 20) { lines[n++] = p; char *e = strchr(p,'\n'); if(e){*e=0;p=e+1;}else break; }
        int idx = atoi(sub);
        if (idx >= 0 && idx < n) {
            snprintf(c, B, "tmux new-window 'cat \"%s\"; read'", lines[idx]); return (void)!system(c), 0;
        }
        return 0;
    }

    /* Default: recent activity with AM/PM display + header */
    char c[B], out[256];
    printf("%-5s %-7s %-16s %-20s %-30s %s\n", "DATE", "TIME", "DEVICE", "CMD", "CWD", "GIT");
    fflush(stdout);
    snprintf(c, B, "cat $(ls '%s'/*.txt 2>/dev/null | sort | tail -30) 2>/dev/null"
        " | awk '{split($2,t,\":\"); h=int(t[1]); m=t[2]; ap=\"AM\"; if(h>=12){ap=\"PM\"; if(h>12)h-=12} if(h==0)h=12; $2=h\":\"m ap} 1'", adir);
    (void)!system(c);

    /* Git remote for activity log */
    snprintf(c, B, "git -C '%s/git' remote get-url origin 2>/dev/null", AROOT);
    pcmd(c, out, 256); out[strcspn(out, "\n")] = 0;
    snprintf(c, B, "ls '%s'/*.txt 2>/dev/null | wc -l", adir);
    char nout[64]; pcmd(c, nout, 64);
    printf("\nActivity: %s/ (%d files)\n  git: %s\n  gdrive: adata/backup/git.tar.zst (via a gdrive sync)\n", adir, atoi(nout), out[0] ? out : "(no remote)");

    /* LLM transcript count + gdrive info */
    mkdirp(LOGDIR);
    snprintf(c, B, "ls '%s'/*.log 2>/dev/null | wc -l", LOGDIR);
    pcmd(c, out, 256); int nlogs = atoi(out);
    if (nlogs) printf("LLM transcripts: %s/ (%d files)\n  gdrive: adata/backup/%s/\n  view: a log <#> | sync: a log sync\n", LOGDIR, nlogs, DEV);

    return 0;
}

/* ── login ── */
static int cmd_login(int argc, char **argv) { fallback_py(argc, argv); }

/* ── sync ── */
static int cmd_sync(int argc, char **argv) {
    printf("%s\n", SROOT);
    sync_repo();
    char c[B], out[256];
    snprintf(c, B, "git -C '%s' remote get-url origin 2>/dev/null", SROOT);
    pcmd(c, out, 256); out[strcspn(out,"\n")] = 0;
    char t[256]; snprintf(c, B, "git -C '%s' log -1 --format='%%cd %%s' --date=format:'%%Y-%%m-%%d %%I:%%M:%%S %%p' 2>/dev/null", SROOT);
    pcmd(c, t, 256); t[strcspn(t,"\n")] = 0;
    printf("  %s\n  Last: %s\n  Status: synced\n", out, t);
    /* Count files per folder */
    const char *folders[] = {"common","ssh","login","agents","notes","workspace","docs","tasks"};
    for (int i = 0; i < 8; i++) {
        char d[P]; snprintf(d, P, "%s/%s", SROOT, folders[i]);
        if (!dexists(d)) continue;
        char cnt_cmd[P]; snprintf(cnt_cmd, P, "find '%s' -name '*.txt' -maxdepth 2 2>/dev/null | wc -l", d);
        char cnt[16]; pcmd(cnt_cmd, cnt, 16); cnt[strcspn(cnt,"\n")] = 0;
        printf("  %s: %s files\n", folders[i], cnt);
    }
    if (argc > 2 && !strcmp(argv[2], "all")) {
        puts("\n--- Broadcasting to SSH hosts ---");
        char bc[B]; snprintf(bc, B, "%s/lib/a.py", SDIR);
        char cmd[B]; snprintf(cmd, B, "python3 '%s' ssh all 'a sync'", bc); (void)!system(cmd);
    }
    return 0;
}

static void gen_icache(void) {
    load_proj(); load_apps();
    char ic[P]; snprintf(ic, P, "%s/i_cache.txt", DDIR);
    FILE *f = fopen(ic, "w"); if (!f) return;
    for (int i=0;i<NPJ;i++) fprintf(f, "%d: %s (%s)\n", i, bname(PJ[i].path), PJ[i].path);
    for (int i=0;i<NAP;i++) fprintf(f, "%d: %s\n", NPJ+i, AP[i].name);
    static const char *cmds[] = {"help","update","jobs","kill","attach","cleanup","config","ls","diff","send","watch",
        "push","pull","revert","set","install","uninstall","deps","prompt","gdrive","add","remove","move",
        "dash","all","backup","scan","copy","log","done","agent","tree","dir","web","ssh","run","hub",
        "task","ui","review","note","setup"};
    for (int i=0;i<(int)(sizeof(cmds)/sizeof(*cmds));i++) fprintf(f, "%s\n", cmds[i]);
    char sd[P]; snprintf(sd, P, "%s/ssh", SROOT);
    char sp[32][P]; int sn = listdir(sd, sp, 32);
    for (int i=0,hi=0;i<sn;i++) {
        kvs_t kv = kvfile(sp[i]);
        const char *nm = kvget(&kv,"Name"); if (!nm) continue;
        const char *host = kvget(&kv,"Host"); fprintf(f, "ssh %d: %s (%s)\n", hi++, nm, host?host:"");
    }
    fclose(f);
}

/* ── update ── */
static int cmd_update(int argc, char **argv) {
    const char *sub = argc > 2 ? argv[2] : NULL;
    if (sub && (!strcmp(sub,"help")||!strcmp(sub,"-h"))) {
        puts("a update - Update a from git + refresh caches\n  a update        Pull latest\n  a update shell  Refresh shell config\n  a update cache  Refresh caches");
        return 0;
    }
    if (sub && (!strcmp(sub,"bash")||!strcmp(sub,"zsh")||!strcmp(sub,"shell")||!strcmp(sub,"cache"))) {
        init_db(); load_cfg(); list_all(1, 1);
        gen_icache();
        puts("\xe2\x9c\x93 Cache"); return 0;
    }
    /* Full update */
    char c[B]; snprintf(c, B, "git -C '%s' rev-parse --git-dir >/dev/null 2>&1", SDIR);
    if (system(c) != 0) { puts("x Not in git repo"); return 0; }
    snprintf(c, B, "git -C '%s' fetch 2>/dev/null", SDIR); (void)!system(c);
    snprintf(c, B, "git -C '%s' status -uno 2>/dev/null", SDIR);
    char out[B]; pcmd(c, out, B);
    if (!strstr(out, "behind")) {
        printf("\xe2\x9c\x93 Up to date\n");
    } else {
        puts("Downloading...");
        snprintf(c, B, "git -C '%s' pull --ff-only 2>/dev/null", SDIR); (void)!system(c);
    }
    /* Self-build: prefer clang, fall back to gcc */
    snprintf(c, B, "cd '%s' && { command -v clang >/dev/null 2>&1 && clang -O2 -o a a.c || gcc -O2 -o a a.c; }", SDIR);
    if (system(c) == 0) puts("\xe2\x9c\x93 Built"); else puts("x Build failed");
    /* Refresh shell + caches */
    snprintf(c, B, "bash '%s/install.sh' --shell 2>/dev/null", SDIR); (void)!system(c);
    init_db(); load_cfg(); list_all(1, 1);
    /* Also sync */
    sync_repo();
    if (sub && !strcmp(sub, "all")) {
        puts("\n--- Broadcasting to SSH hosts ---");
        snprintf(c, B, "python3 '%s' ssh all 'a update'", PYPATH); (void)!system(c);
    }
    return 0;
}

/* ── review ── */
static int cmd_review(int argc, char **argv) { fallback_py(argc, argv); }

/* ── docs ── */
static int cmd_docs(int argc, char **argv) {
    char dir[P]; snprintf(dir, P, "%s/docs", SROOT); mkdirp(dir);
    if (argc > 2) {
        char f[P]; snprintf(f, P, "%s/%s%s", dir, argv[2], strchr(argv[2],'.') ? "" : ".txt");
        int fd = open(f, O_CREAT|O_WRONLY|O_APPEND, 0644); if(fd>=0) close(fd);
        execlp("e", "e", f, (char*)NULL);
        return 0;
    }
    /* List docs */
    char paths[64][P]; int n = listdir(dir, paths, 64);
    for (int i = 0; i < n; i++) printf("%d. %s\n", i+1, bname(paths[i]));
    return 0;
}

/* ── run (remote) ── */
static int cmd_run(int argc, char **argv) { fallback_py(argc, argv); }

/* ── agent ── */
static int cmd_agent(int argc, char **argv) {
    if (argc < 3) { puts("Usage: a agent [g|c|l] <task>"); return 1; }
    init_db(); load_cfg(); load_sess();
    const char *wda = argv[2];
    sess_t *s = find_sess(wda);
    const char *task;
    if (s) { task = argc > 3 ? argv[3] : NULL; }
    else { s = find_sess("g"); task = wda; /* default to gemini */ }
    if (!task || !task[0]) { puts("Usage: a agent [g|c|l] <task>"); return 1; }
    /* Build task string */
    char taskstr[B] = "";
    if (s && strcmp(wda, s->key) == 0) { for (int i=3;i<argc;i++){if(i>3)strcat(taskstr," ");strncat(taskstr,argv[i],B-strlen(taskstr)-2);} }
    else { for (int i=2;i<argc;i++){if(i>2)strcat(taskstr," ");strncat(taskstr,argv[i],B-strlen(taskstr)-2);} }
    char wd[P]; if (!getcwd(wd, P)) strcpy(wd, HOME);
    char sn[256]; snprintf(sn, 256, "agent-%s-%ld", s->key, (long)time(NULL));
    printf("Agent: %s | Task: %.50s...\n", s->key, taskstr);
    create_sess(sn, wd, s->cmd);
    /* Wait for agent to start */
    puts("Waiting for agent to start...");
    for (int i = 0; i < 60; i++) {
        sleep(1);
        char c[B], out[B]; snprintf(c, B, "tmux capture-pane -t '%s' -p 2>/dev/null", sn);
        pcmd(c, out, B);
        if (strstr(out, "Type your message") || strstr(out, "claude") || strstr(out, "gemini")) break;
    }
    /* Send task with instructions */
    char prompt[B*2]; snprintf(prompt, sizeof(prompt),
        "%s\n\nCommands: \"a agent g <task>\" spawns gemini subagent, \"a agent l <task>\" spawns claude subagent. When YOUR task is fully complete, run: a done",
        taskstr);
    tm_send(sn, prompt); usleep(300000);
    char c[B]; snprintf(c, B, "tmux send-keys -t '%s' Enter", sn); (void)!system(c);
    /* Wait for done file */
    char donef[P]; snprintf(donef, P, "%s/.done", DDIR); unlink(donef);
    puts("Waiting for completion...");
    time_t start = time(NULL);
    while (!fexists(donef) && time(NULL) - start < 300) sleep(1);
    /* Capture output */
    char out[B*4]; snprintf(c, B, "tmux capture-pane -t '%s' -p -S -100 2>/dev/null", sn);
    pcmd(c, out, sizeof(out));
    printf("--- Output ---\n%s\n--- End ---\n", out);
    return 0;
}

/* ── multi/all ── */
static int cmd_all(int argc, char **argv) { fallback_py(argc, argv); }

/* ── session (c, l, g, co, cp, etc.) ── */
static int cmd_sess(int argc, char **argv) {
    init_db(); load_cfg(); load_proj(); load_apps(); load_sess();
    const char *key = argv[1];
    sess_t *s = find_sess(key);
    if (!s) return -1;  /* not a session key */
    char wd[P]; if (!getcwd(wd, P)) strcpy(wd, HOME);
    const char *wda = argc > 2 ? argv[2] : NULL;
    /* If wda is a project number */
    if (wda && wda[0] >= '0' && wda[0] <= '9') {
        int idx = atoi(wda);
        if (idx >= 0 && idx < NPJ) snprintf(wd, P, "%s", PJ[idx].path);
        else if (idx >= NPJ && idx < NPJ + NAP) {
            printf("> Running: %s\n", AP[idx-NPJ].name);
            const char *sh = getenv("SHELL"); if (!sh) sh = "/bin/bash";
            execlp(sh, sh, "-c", AP[idx-NPJ].cmd, (char*)NULL);
        }
    } else if (wda && dexists(wda)) {
        if (wda[0] == '~') snprintf(wd, P, "%s%s", HOME, wda+1);
        else snprintf(wd, P, "%s", wda);
    }
    /* Build prompt from remaining args */
    char prompt[B] = ""; int is_prompt = 0;
    int start = wda ? 3 : 2;
    if (wda && !(wda[0]>='0'&&wda[0]<='9') && !dexists(wda)) { start = 2; is_prompt = 1; }
    for (int i = start; i < argc; i++) {
        if (!strcmp(argv[i],"-w")||!strcmp(argv[i],"--new-window")||!strcmp(argv[i],"-t")||!strcmp(argv[i],"--with-terminal")) continue;
        if (prompt[0]) strcat(prompt, " ");
        strncat(prompt, argv[i], B-strlen(prompt)-2);
        is_prompt = 1;
    }
    /* Inside tmux + single char key = split pane mode */
    if (getenv("TMUX") && strlen(key) == 1 && key[0] != 'a') {
        char cmd[B*2]; snprintf(cmd, sizeof(cmd), "%s", s->cmd);
        if (is_prompt && prompt[0]) {
            const char *dp = cfget("default_prompt");
            char full[B]; snprintf(full, B, "%s%s%s", dp[0]?dp:"", dp[0]?" ":"", prompt);
            size_t cl = strlen(cmd); snprintf(cmd + cl, sizeof(cmd) - cl, " '%s'", full);
        }
        /* Split pane */
        char c[B*2]; snprintf(c, sizeof(c), "tmux split-window -hfP -F '#{pane_id}' -c '%s' '%s'", wd, cmd);
        char pid[64]; pcmd(c, pid, 64); pid[strcspn(pid,"\n")] = 0;
        if (pid[0]) {
            snprintf(c, B, "tmux split-window -v -t '%s' -c '%s' 'sh -c \"ls;exec $SHELL\"'", pid, wd); (void)!system(c);
            snprintf(c, B, "tmux select-pane -t '%s'", pid); (void)!system(c);
            if (!is_prompt) send_prefix_bg(pid, s->name, wd);
        }
        return 0;
    }
    /* Find or create named session */
    char sn[256]; snprintf(sn, 256, "%s-%s", s->name, bname(wd));
    /* Check for existing session with same base name */
    if (tm_has(sn)) {
        if (is_prompt && prompt[0]) {
            /* Send prompt to existing session */
            tm_send(sn, prompt); usleep(100000);
            char c[B]; snprintf(c, B, "tmux send-keys -t '%s' Enter", sn); (void)!system(c);
            puts("Prompt queued (existing session)");
        }
        tm_go(sn);
        return 0;
    }
    /* Create new session */
    char cmd[B*2]; snprintf(cmd, sizeof(cmd), "%s", s->cmd);
    if (is_prompt && prompt[0]) {
        const char *dp = cfget("default_prompt");
        char full[B]; snprintf(full, B, "%s%s%s", dp[0]?dp:"", dp[0]?" ":"", prompt);
        size_t cl = strlen(cmd); snprintf(cmd + cl, sizeof(cmd) - cl, " '%s'", full);
    }
    create_sess(sn, wd, cmd);
    if (!is_prompt) send_prefix_bg(sn, s->name, wd);
    tm_go(sn);
    return 0;
}

/* ── worktree ++ ── */
static int cmd_wt_plus(int argc, char **argv) { fallback_py(argc, argv); }

/* ── worktree w* ── */
static int cmd_wt(int argc, char **argv) { fallback_py(argc, argv); }

/* ── dir_file ── */
static int cmd_dir_file(int argc, char **argv) { (void)argc;
    const char *arg = argv[1];
    char expanded[P];
    if (arg[0] == '/' && !strncmp(arg, "/projects/", 10)) {
        snprintf(expanded, P, "%s%s", HOME, arg);
        if (dexists(expanded)) { printf("%s\n", expanded); execlp("ls", "ls", expanded, (char*)NULL); return 0; }
    }
    if (arg[0] == '~') snprintf(expanded, P, "%s%s", HOME, arg+1);
    else snprintf(expanded, P, "%s", arg);
    if (dexists(expanded)) { printf("%s\n", expanded); execlp("ls", "ls", expanded, (char*)NULL); }
    else if (fexists(expanded)) {
        const char *ext = strrchr(expanded, '.');
        if (ext && !strcmp(ext, ".py")) { execvp("python3", (char*[]){ "python3", expanded, NULL }); }
        else { const char *ed = getenv("EDITOR"); if (!ed) ed = "e"; execlp(ed, ed, expanded, (char*)NULL); }
    }
    return 0;
}

/* ── interactive picker ── */
static int cmd_i(int argc, char **argv) { (void)argc; (void)argv;
    init_db(); gen_icache();
    char cache[P]; snprintf(cache, P, "%s/i_cache.txt", DDIR);
    size_t len; char *raw = readf(cache, &len);
    if (!raw) { puts("No cache"); return 1; }
    /* Parse lines */
    char *lines[512]; int n = 0;
    for (char *p = raw, *end = raw + len; p < end && n < 512;) {
        char *nl = memchr(p, '\n', (size_t)(end - p));
        if (!nl) nl = end;
        if (nl > p && p[0] != '<' && p[0] != '=' && p[0] != '>' && p[0] != '#') { *nl = 0; lines[n++] = p; }
        p = nl + 1;
    }
    if (!n) { puts("Empty cache"); free(raw); return 1; }
    if (!isatty(STDIN_FILENO)) { for (int i=0;i<n;i++) puts(lines[i]); free(raw); return 0; }
    /* Terminal size */
    struct winsize ws; ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws);
    int maxshow = ws.ws_row > 6 ? ws.ws_row - 3 : 10;
    /* Raw mode */
    struct termios old, raw_t;
    tcgetattr(STDIN_FILENO, &old); raw_t = old;
    raw_t.c_lflag &= ~(tcflag_t)(ICANON | ECHO);
    raw_t.c_cc[VMIN] = 1; raw_t.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSANOW, &raw_t);
    char buf[256] = ""; int blen = 0, sel = 0;
    printf("Filter (↑↓/Tab=cycle, Enter=run, Esc=quit)\n");
    while (1) {
        /* Search */
        char *matches[512]; int nm = 0;
        if (!blen) { for (int i=0;i<n&&nm<maxshow;i++) matches[nm++]=lines[i]; }
        else { for (int i=0;i<n&&nm<maxshow;i++) { if (strcasestr(lines[i],buf)) matches[nm++]=lines[i]; } }
        if (sel >= nm) sel = nm ? nm-1 : 0;
        /* Render */
        printf("\r\033[K> %s\n", buf);
        for (int i=0;i<nm;i++) printf("\033[K%s a %s\n", i==sel?" >":"  ", matches[i]);
        printf("\033[%dA\033[%dC\033[?25h", nm+1, blen+3);
        fflush(stdout);
        /* Read key */
        char ch; if (read(STDIN_FILENO, &ch, 1) != 1) break;
        if (ch == '\x1b') { /* Escape sequence or Esc */
            char seq[2]; if (read(STDIN_FILENO, &seq[0], 1) != 1) break;
            if (seq[0] == '[') {
                if (read(STDIN_FILENO, &seq[1], 1) != 1) break;
                if (seq[1] == 'A') { sel = sel > 0 ? sel-1 : (nm?nm-1:0); } /* Up */
                else if (seq[1] == 'B') { sel = (sel+1) % (nm?nm:1); } /* Down */
            } else break; /* bare Esc */
        } else if (ch == '\t') { sel = (sel+1) % (nm?nm:1); }
        else if (ch == '\x7f' || ch == '\b') { if (blen) buf[--blen]=0; sel=0; }
        else if (ch == '\r' || ch == '\n') {
            if (!nm) continue;
            char *m = matches[sel]; char cmd[256];
            char *colon = strchr(m, ':');
            if (colon) { int cl = (int)(colon-m); snprintf(cmd, 256, "%.*s", cl, m); while(cmd[0]==' ')memmove(cmd,cmd+1,strlen(cmd)); }
            else snprintf(cmd, 256, "%s", m);
            /* Trim */
            char *e = cmd+strlen(cmd)-1; while(e>cmd&&*e==' ')*e--=0;
            tcsetattr(STDIN_FILENO, TCSANOW, &old);
            printf("\n\n\033[KRunning: a %s\n", cmd);
            /* Build argv for exec */
            char *args[32]; int ac=0; args[ac++]="a";
            char *p=cmd; while(*p&&ac<31) { while(*p==' ')p++; if(!*p)break; args[ac++]=p; while(*p&&*p!=' ')p++; if(*p)*p++=0; }
            args[ac]=NULL;
            free(raw); execvp("a", args);
            return 0;
        } else if (ch == '\x03' || ch == '\x04') break;
        else if (ch == 'q' && !blen) break;
        else if ((ch>='a'&&ch<='z')||(ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9')||ch=='-'||ch=='_'||ch==' ') { if(blen<254){buf[blen++]=ch;buf[blen]=0;sel=0;} }
        printf("\033[J");
    }
    tcsetattr(STDIN_FILENO, TCSANOW, &old);
    printf("\033[2B\033[K"); free(raw);
    return 0;
}

/* ═══ ACTIVITY LOG ═══ */
static void alog(const char *cmd, const char *cwd, const char *extra) { (void)extra;
    pid_t p=fork();if(p<0)return;if(p>0){waitpid(p,NULL,WNOHANG);return;} /* parent returns instantly */
    if(fork()>0)_exit(0); setsid(); /* double-fork, child is orphan */
    char dir[P]; snprintf(dir, P, "%s/git/activity", AROOT);
    mkdirp(dir);
    time_t t = time(NULL); struct tm *tm = localtime(&t);
    struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts);
    char lf[P]; snprintf(lf, P, "%s/%04d%02d%02dT%02d%02d%02d.%03ld_%s.txt", dir,
        tm->tm_year+1900, tm->tm_mon+1, tm->tm_mday, tm->tm_hour, tm->tm_min, tm->tm_sec,
        ts.tv_nsec / 1000000, DEV);
    FILE *f = fopen(lf, "w"); if (!f) _exit(0);
    char repo[512] = "";
    if (git_in_repo(cwd)) {
        char c[B], out[512];
        snprintf(c, B, "git -C '%s' remote get-url origin 2>/dev/null", cwd);
        pcmd(c, out, 512); out[strcspn(out, "\n")] = 0;
        if (out[0]) snprintf(repo, 512, " git:%s", out);
    }
    fprintf(f, "%02d/%02d %02d:%02d %s %s %s%s\n",
        tm->tm_mon+1, tm->tm_mday, tm->tm_hour, tm->tm_min,
        DEV, cmd, cwd, repo);
    fclose(f); _exit(0);
}

/* ═══ MAIN DISPATCH ═══ */
int main(int argc, char **argv) {
    init_paths();
    G_argc = argc; G_argv = argv;

    if (argc < 2) return cmd_help(argc, argv);

    /* Log every command */
    char acmd[B] = "";
    for (int i = 1; i < argc && strlen(acmd) < B - 256; i++) {
        if (i > 1) strcat(acmd, " ");
        strncat(acmd, argv[i], B - strlen(acmd) - 2);
    }
    char wd[P]; if (!getcwd(wd, P)) snprintf(wd, P, "%s", HOME);
    alog(acmd, wd, NULL);

    const char *arg = argv[1];

    /* Numeric = project number */
    { const char *p = arg; while (*p >= '0' && *p <= '9') p++;
      if (*p == '\0' && p != arg) { init_db(); return cmd_project_num(argc, argv, atoi(arg)); } }

    /* Special aliases from CMDS dict */
    if (!strcmp(arg,"help")||!strcmp(arg,"hel")||!strcmp(arg,"--help")||!strcmp(arg,"-h"))
        return cmd_help_full(argc, argv);
    if (!strcmp(arg,"killall")) return cmd_kill(argc, argv);
    if (!strcmp(arg,"p")) return cmd_push(argc, argv);
    if (!strcmp(arg,"rm")) return cmd_remove(argc, argv);
    if (!strcmp(arg,"n")) return cmd_note(argc, argv);
    if (!strcmp(arg,"t")) return cmd_task(argc, argv);
    if (!strcmp(arg,"a")||!strcmp(arg,"ai")||!strcmp(arg,"aio")) return cmd_all(argc, argv);
    if (!strcmp(arg,"i")) return cmd_i(argc, argv);
    if (!strcmp(arg,"gdrive")||!strcmp(arg,"gdr")) fallback_py(argc, argv);
    if (!strcmp(arg,"ask")) fallback_py(argc, argv);
    if (!strcmp(arg,"ui")) fallback_py(argc, argv);
    if (!strcmp(arg,"mono")||!strcmp(arg,"monolith")) fallback_py(argc, argv);
    if (!strcmp(arg,"rebuild")) return cmd_rebuild();
    if (!strcmp(arg,"logs")) return cmd_log(argc, argv);

    /* Exact + alias match */
    if (!strcmp(arg,"push")||!strcmp(arg,"pus")) return cmd_push(argc, argv);
    if (!strcmp(arg,"pull")||!strcmp(arg,"pul")) return cmd_pull(argc, argv);
    if (!strcmp(arg,"diff")||!strcmp(arg,"dif")) return cmd_diff(argc, argv);
    if (!strcmp(arg,"revert")||!strcmp(arg,"rev")) return cmd_revert(argc, argv);
    if (!strcmp(arg,"ls")) return cmd_ls(argc, argv);
    if (!strcmp(arg,"kill")||!strcmp(arg,"kil")) return cmd_kill(argc, argv);
    if (!strcmp(arg,"config")||!strcmp(arg,"con")) return cmd_config(argc, argv);
    if (!strcmp(arg,"prompt")||!strcmp(arg,"pro")) return cmd_prompt(argc, argv);
    if (!strcmp(arg,"set")||!strcmp(arg,"settings")) return cmd_set(argc, argv);
    if (!strcmp(arg,"add")) return cmd_add(argc, argv);
    if (!strcmp(arg,"remove")||!strcmp(arg,"rem")) return cmd_remove(argc, argv);
    if (!strcmp(arg,"move")||!strcmp(arg,"mov")) return cmd_move(argc, argv);
    if (!strcmp(arg,"scan")||!strcmp(arg,"sca")) return cmd_scan(argc, argv);
    if (!strcmp(arg,"done")) return cmd_done();
    if (!strcmp(arg,"hi")) return cmd_hi();
    if (!strcmp(arg,"dir")) return cmd_dir();
    if (!strcmp(arg,"backup")||!strcmp(arg,"bak")) return cmd_backup();
    if (!strcmp(arg,"web")) return cmd_web(argc, argv);
    if (!strcmp(arg,"repo")) return cmd_repo(argc, argv);
    if (!strcmp(arg,"setup")||!strcmp(arg,"set up")) return cmd_setup(argc, argv);
    if (!strcmp(arg,"install")||!strcmp(arg,"ins")) return cmd_install();
    if (!strcmp(arg,"uninstall")||!strcmp(arg,"uni")) return cmd_uninstall();
    if (!strcmp(arg,"deps")||!strcmp(arg,"dep")) return cmd_deps();
    if (!strcmp(arg,"e")) return cmd_e(argc, argv);
    if (!strcmp(arg,"x")) return cmd_x();
    if (!strcmp(arg,"copy")||!strcmp(arg,"cop")) return cmd_copy();
    if (!strcmp(arg,"dash")||!strcmp(arg,"das")) return cmd_dash();
    if (!strcmp(arg,"attach")||!strcmp(arg,"att")) return cmd_attach(argc, argv);
    if (!strcmp(arg,"watch")||!strcmp(arg,"wat")) return cmd_watch(argc, argv);
    if (!strcmp(arg,"send")||!strcmp(arg,"sen")) return cmd_send(argc, argv);
    if (!strcmp(arg,"jobs")||!strcmp(arg,"job")) return cmd_jobs(argc, argv);
    if (!strcmp(arg,"cleanup")||!strcmp(arg,"cle")) return cmd_cleanup(argc, argv);
    if (!strcmp(arg,"tree")||!strcmp(arg,"tre")) return cmd_tree(argc, argv);
    if (!strcmp(arg,"note")) return cmd_note(argc, argv);
    if (!strcmp(arg,"task")||!strcmp(arg,"tas")) return cmd_task(argc, argv);
    if (!strcmp(arg,"ssh")) return cmd_ssh(argc, argv);
    if (!strcmp(arg,"hub")) return cmd_hub(argc, argv);
    if (!strcmp(arg,"log")) return cmd_log(argc, argv);
    if (!strcmp(arg,"login")) return cmd_login(argc, argv);
    if (!strcmp(arg,"sync")||!strcmp(arg,"syn")) return cmd_sync(argc, argv);
    if (!strcmp(arg,"update")||!strcmp(arg,"upd")) return cmd_update(argc, argv);
    if (!strcmp(arg,"review")) return cmd_review(argc, argv);
    if (!strcmp(arg,"docs")||!strcmp(arg,"doc")) return cmd_docs(argc, argv);
    if (!strcmp(arg,"run")) return cmd_run(argc, argv);
    if (!strcmp(arg,"agent")) return cmd_agent(argc, argv);
    if (!strcmp(arg,"work")||!strcmp(arg,"wor")) { fallback_py(argc, argv); }
    if (!strcmp(arg,"all")) return cmd_all(argc, argv);

    /* x.* experimental commands */
    if (arg[0] == 'x' && arg[1] == '.') fallback_py(argc, argv);

    /* Worktree: key++ */
    { size_t l = strlen(arg);
      if (l >= 3 && arg[l-1] == '+' && arg[l-2] == '+' && arg[0] != 'w')
          return cmd_wt_plus(argc, argv); }

    /* Worktree: w* */
    if (arg[0] == 'w' && strcmp(arg,"watch") && strcmp(arg,"web") && !fexists(arg))
        return cmd_wt(argc, argv);

    /* Directory or file */
    if (dexists(arg) || fexists(arg)) return cmd_dir_file(argc, argv);
    { char ep[P]; snprintf(ep, P, "%s%s", HOME, arg);
      if (arg[0] == '/' && dexists(ep)) return cmd_dir_file(argc, argv); }

    /* Session key check */
    { init_db(); load_cfg(); load_sess();
      if (find_sess(arg)) return cmd_sess(argc, argv); }

    /* Short session-like keys (1-3 chars) */
    if (strlen(arg) <= 3 && arg[0] >= 'a' && arg[0] <= 'z')
        return cmd_sess(argc, argv);

    /* Unknown - try python */
    fallback_py(argc, argv);
}
