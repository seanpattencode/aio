/*
 * a.c - monolithic C rewrite of 'a' AI agent session manager
 *
 * Build:
 *   make                (uses Makefile)
 *   clang -O2 -o a a.c -lsqlite3      (manual)
 *
 * Clang preferred over GCC: 36% faster compile (0.34s vs 0.53s),
 * 5% smaller binary (67KB vs 70KB), identical runtime.
 * Benchmarked with GCC 15 vs Clang 20 on x86_64.
 */
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
#include <sqlite3.h>

#define P 1024
#define B 4096
#define MP 256
#define MA 64
#define MS 48

/* ═══ GLOBALS ═══ */
static char HOME[P], DDIR[P], DBPATH[P], SROOT[P], SDIR[P], PYPATH[P], DEV[128], LOGDIR[P];
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
    snprintf(DBPATH, P, "%s/aio.db", DDIR);
    char self[P]; ssize_t n = readlink("/proc/self/exe", self, P - 1);
    if (n > 0) {
        self[n] = 0;
        char *s = strrchr(self, '/');
        if (s) { *s = 0; snprintf(SDIR, P, "%s", self);
            /* binary is at projects/a/a → strip to projects/ */
            s = strrchr(self, '/');
            if (s) { *s = 0; snprintf(SROOT, P, "%s/a-sync", self); }
        }
    }
    if (!SROOT[0]) snprintf(SROOT, P, "%s/projects/a-sync", h);
    snprintf(PYPATH, P, "%s/archive/a.py", SDIR);
    snprintf(LOGDIR, P, "%s/logs", SROOT);
    /* device id */
    char df[P]; snprintf(df, P, "%s/.device", DDIR);
    FILE *f = fopen(df, "r");
    if (f) { if (fgets(DEV, 128, f)) DEV[strcspn(DEV, "\n")] = 0; fclose(f); }
    if (!DEV[0]) {
        gethostname(DEV, 128);
        char c[P]; snprintf(c, P, "mkdir -p '%s'", DDIR); (void)!system(c);
        f = fopen(df, "w"); if (f) { fputs(DEV, f); fclose(f); }
    }
}

/* ═══ UTILITIES ═══ */
static int fexists(const char *p) { struct stat s; return stat(p, &s) == 0; }
static int dexists(const char *p) { struct stat s; return stat(p, &s) == 0 && S_ISDIR(s.st_mode); }
static void mkdirp(const char *p) { char c[P*2]; snprintf(c, sizeof(c), "mkdir -p '%s'", p); (void)!system(c); }

static char *readf(const char *p, size_t *len) {
    int fd = open(p, O_RDONLY); if (fd < 0) return NULL;
    struct stat s; if (fstat(fd, &s) < 0) { close(fd); return NULL; }
    char *b = malloc(s.st_size + 1); if (!b) { close(fd); return NULL; }
    ssize_t n = read(fd, b, s.st_size); close(fd);
    if (n < 0) { free(b); return NULL; }
    b[n] = 0; if (len) *len = n; return b;
}

static int catf(const char *p) {
    int fd = open(p, O_RDONLY); if (fd < 0) return -1;
    char b[8192]; ssize_t n;
    while ((n = read(fd, b, sizeof(b))) > 0) (void)!write(STDOUT_FILENO, b, n);
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
        const char *c = memchr(p, ':', nl - p);
        if (c && c > p) {
            int kl = (int)(c - p); if (kl > 31) kl = 31;
            memcpy(r.i[r.n].k, p, kl); r.i[r.n].k[kl] = 0;
            const char *v = c + 1; while (*v == ' ' && v < nl) v++;
            int vl = (int)(nl - v); if (vl > 511) vl = 511;
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

/* ═══ SQLITE ═══ */
static sqlite3 *_db;
static sqlite3 *dbopen(void) {
    if (_db) return _db;
    sqlite3_open(DBPATH, &_db);
    sqlite3_exec(_db, "PRAGMA journal_mode=WAL", 0, 0, 0);
    return _db;
}

static void init_db(void) {
    mkdirp(DDIR); sqlite3 *d = dbopen();
    sqlite3_exec(d,
        "CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT NOT NULL);"
        "CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY AUTOINCREMENT,path TEXT NOT NULL,display_order INTEGER NOT NULL,device TEXT DEFAULT '*');"
        "CREATE TABLE IF NOT EXISTS apps(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,command TEXT NOT NULL,display_order INTEGER NOT NULL,device TEXT DEFAULT '*');"
        "CREATE TABLE IF NOT EXISTS sessions(key TEXT PRIMARY KEY,name TEXT NOT NULL,command_template TEXT NOT NULL);"
        "CREATE TABLE IF NOT EXISTS multi_runs(id TEXT PRIMARY KEY,repo TEXT NOT NULL,prompt TEXT NOT NULL,agents TEXT NOT NULL,status TEXT DEFAULT 'running',created_at TEXT DEFAULT CURRENT_TIMESTAMP,review_rank TEXT);"
        "CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,t,s DEFAULT 0,d,c DEFAULT CURRENT_TIMESTAMP,proj,dev);"
        "CREATE TABLE IF NOT EXISTS note_projects(id INTEGER PRIMARY KEY,name TEXT UNIQUE,c TEXT DEFAULT CURRENT_TIMESTAMP);"
        "CREATE TABLE IF NOT EXISTS todos(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,real_deadline INTEGER NOT NULL,virtual_deadline INTEGER,created_at INTEGER NOT NULL,completed_at INTEGER);"
        "CREATE TABLE IF NOT EXISTS jobs(name TEXT PRIMARY KEY,step TEXT NOT NULL,status TEXT NOT NULL,path TEXT,session TEXT,updated_at INTEGER NOT NULL);"
        "CREATE TABLE IF NOT EXISTS hub_jobs(id INTEGER PRIMARY KEY,name TEXT,schedule TEXT,prompt TEXT,agent TEXT DEFAULT 'l',project TEXT,device TEXT,enabled INTEGER DEFAULT 1,last_run TEXT,parallel INTEGER DEFAULT 1);"
        "CREATE TABLE IF NOT EXISTS agent_logs(session TEXT PRIMARY KEY,parent TEXT,started REAL,device TEXT);",
        0, 0, 0);
    /* defaults */
    int cnt = 0; sqlite3_stmt *st;
    sqlite3_prepare_v2(d, "SELECT COUNT(*) FROM config", -1, &st, 0);
    if (sqlite3_step(st) == SQLITE_ROW) cnt = sqlite3_column_int(st, 0);
    sqlite3_finalize(st);
    if (cnt == 0) {
        char wt[P]; snprintf(wt, P, "%s/projects/aWorktrees", HOME);
        char pp[P], dp[B] = ""; snprintf(pp, P, "%s/common/prompts/default.txt", SROOT);
        char *pd = readf(pp, NULL); if (pd) { snprintf(dp, B, "%s", pd); free(pd); }
        sqlite3_stmt *ins;
        sqlite3_prepare_v2(d, "INSERT OR IGNORE INTO config VALUES(?,?)", -1, &ins, 0);
        const char *defs[][2] = {{"claude_prompt",dp},{"codex_prompt",dp},{"gemini_prompt",dp},
            {"worktrees_dir",wt},{"multi_default","l:3"},{"claude_prefix","Ultrathink. "}};
        for (int i = 0; i < 6; i++) {
            sqlite3_bind_text(ins, 1, defs[i][0], -1, 0);
            sqlite3_bind_text(ins, 2, defs[i][1], -1, 0);
            sqlite3_step(ins); sqlite3_reset(ins);
        }
        sqlite3_finalize(ins);
    }
    sqlite3_exec(d, "INSERT OR IGNORE INTO config VALUES('multi_default','l:3')", 0, 0, 0);
    sqlite3_exec(d, "INSERT OR IGNORE INTO config VALUES('claude_prefix','Ultrathink. ')", 0, 0, 0);
    /* default sessions */
    int scnt = 0;
    sqlite3_prepare_v2(d, "SELECT COUNT(*) FROM sessions", -1, &st, 0);
    if (sqlite3_step(st) == SQLITE_ROW) scnt = sqlite3_column_int(st, 0);
    sqlite3_finalize(st);
    if (scnt == 0) {
        const char *CDX = "codex -c model_reasoning_effort=\"high\" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox";
        const char *CLD = "claude --dangerously-skip-permissions";
        sqlite3_stmt *ins;
        sqlite3_prepare_v2(d, "INSERT OR IGNORE INTO sessions VALUES(?,?,?)", -1, &ins, 0);
        struct { const char *k, *n, *t; } sd[] = {
            {"h","htop","htop"},{"t","top","top"},
            {"g","gemini","gemini --yolo"},{"gemini","gemini","gemini --yolo"},
            {"c","claude",CLD},{"claude","claude",CLD},{"l","claude",CLD},{"o","claude",CLD},
            {"co","codex",CDX},{"codex","codex",CDX},
            {"a","aider","OLLAMA_API_BASE=http://127.0.0.1:11434 aider --model ollama_chat/mistral"},
        };
        for (int i = 0; i < 11; i++) {
            sqlite3_bind_text(ins, 1, sd[i].k, -1, 0);
            sqlite3_bind_text(ins, 2, sd[i].n, -1, 0);
            sqlite3_bind_text(ins, 3, sd[i].t, -1, 0);
            sqlite3_step(ins); sqlite3_reset(ins);
        }
        /* prompt variants */
        char cpb[1200], cxpb[1200], gpb[1200];
        snprintf(cpb, 1200, "%s \"{CLAUDE_PROMPT}\"", CLD);
        snprintf(cxpb, 1200, "%s \"{CODEX_PROMPT}\"", CDX);
        snprintf(gpb, 1200, "gemini --yolo \"{GEMINI_PROMPT}\"");
        struct { const char *k, *n, *t; } sp[] = {
            {"cp","claude-p",cpb},{"lp","claude-p",cpb},{"gp","gemini-p",gpb},{"cop","codex-p",cxpb},
        };
        for (int i = 0; i < 4; i++) {
            sqlite3_bind_text(ins, 1, sp[i].k, -1, 0);
            sqlite3_bind_text(ins, 2, sp[i].n, -1, 0);
            sqlite3_bind_text(ins, 3, sp[i].t, -1, 0);
            sqlite3_step(ins); sqlite3_reset(ins);
        }
        sqlite3_finalize(ins);
    }
}

/* ═══ DATA LOADERS ═══ */
static void load_cfg(void) {
    NCF = 0; sqlite3 *d = dbopen(); sqlite3_stmt *st;
    sqlite3_prepare_v2(d, "SELECT key,value FROM config", -1, &st, 0);
    while (sqlite3_step(st) == SQLITE_ROW && NCF < 64) {
        snprintf(CF[NCF].k, 64, "%s", (const char *)sqlite3_column_text(st, 0));
        snprintf(CF[NCF].v, 1024, "%s", (const char *)sqlite3_column_text(st, 1));
        NCF++;
    }
    sqlite3_finalize(st);
}

static const char *cfget(const char *key) {
    for (int i = 0; i < NCF; i++) if (!strcmp(CF[i].k, key)) return CF[i].v;
    return "";
}

static int pj_cmp(const void *a, const void *b) { return strcmp(((proj_t*)a)->name, ((proj_t*)b)->name); }

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
    qsort(PJ, NPJ, sizeof(proj_t), pj_cmp);
}

static int ap_cmp(const void *a, const void *b) { return strcmp(((app_t*)a)->name, ((app_t*)b)->name); }

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
    qsort(AP, NAP, sizeof(app_t), ap_cmp);
}

static void load_sess(void) {
    NSE = 0; sqlite3 *d = dbopen(); sqlite3_stmt *st;
    sqlite3_prepare_v2(d, "SELECT key,name,command_template FROM sessions", -1, &st, 0);
    while (sqlite3_step(st) == SQLITE_ROW && NSE < MS) {
        snprintf(SE[NSE].key, 16, "%s", (const char *)sqlite3_column_text(st, 0));
        snprintf(SE[NSE].name, 64, "%s", (const char *)sqlite3_column_text(st, 1));
        const char *tmpl = (const char *)sqlite3_column_text(st, 2);
        /* expand template variables */
        char expanded[1024]; snprintf(expanded, 1024, "%s", tmpl);
        /* Replace {CLAUDE_PROMPT}, {CODEX_PROMPT}, {GEMINI_PROMPT} */
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
        /* For -p variants, strip the prompt arg if it's cp/lp/gp */
        const char *k = SE[NSE].key;
        if (!strcmp(k,"cp") || !strcmp(k,"lp") || !strcmp(k,"gp")) {
            /* Remove " "..." at end - the prompt was already baked in for non-p mode */
            char *dq = strstr(expanded, " \"");
            if (dq) *dq = 0;
        }
        snprintf(SE[NSE].cmd, 1024, "%s", expanded);
        NSE++;
    }
    sqlite3_finalize(st);
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
        "cd '%s' && git add -A && git commit -qm sync 2>/dev/null;"
        "git pull --no-rebase -q origin main 2>/dev/null;"
        "git push -q origin main 2>/dev/null", SROOT);
    (void)!system(c);
}

/* ═══ FALLBACK ═══ */
__attribute__((noreturn))
static void fallback_py(int argc, char **argv) {
    char **na = malloc((argc + 3) * sizeof(char *));
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
    /* agent_logs */
    sqlite3_stmt *st;
    sqlite3_prepare_v2(dbopen(), "INSERT OR REPLACE INTO agent_logs VALUES(?,?,?,?)", -1, &st, 0);
    sqlite3_bind_text(st, 1, sn, -1, 0); sqlite3_bind_null(st, 2);
    sqlite3_bind_double(st, 3, (double)time(NULL)); sqlite3_bind_text(st, 4, DEV, -1, 0);
    sqlite3_step(st); sqlite3_finalize(st);
}

static void send_prefix_bg(const char *sn, const char *agent, const char *wd) {
    const char *dp = cfget("default_prompt");
    const char *cp = strstr(agent, "claude") ? cfget("claude_prefix") : "";
    char pre[B]; snprintf(pre, B, "%s%s%s", dp[0] ? dp : "", dp[0] ? " " : "", cp);
    /* Check for AGENTS.md */
    char af[P]; snprintf(af, P, "%s/AGENTS.md", wd);
    char *amd = readf(af, NULL);
    if (amd) { int n = strlen(pre); snprintf(pre + n, B - n, "%s ", amd); free(amd); }
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

static int cmd_help(int argc, char **argv) {
    char p[P]; snprintf(p, P, "%s/help_cache.txt", DDIR);
    if (catf(p) < 0) { init_db(); load_cfg(); printf("%s\n", HELP_SHORT); list_all(1, 0); }
    return 0;
}

static int cmd_help_full(int argc, char **argv) {
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
    char s[P]; snprintf(s, P, "%s/../install.sh", SDIR);
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
static int cmd_project_num(int argc, char **argv, int idx) {
    init_db(); load_cfg(); load_proj(); load_apps();
    if (idx >= 0 && idx < NPJ) {
        if (!dexists(PJ[idx].path) && PJ[idx].repo[0]) {
            printf("Cloning %s...\n", PJ[idx].repo);
            char c[B]; snprintf(c, B, "git clone '%s' '%s'", PJ[idx].repo, PJ[idx].path); (void)!system(c);
        }
        if (!dexists(PJ[idx].path)) { printf("x %s\n", PJ[idx].path); return 1; }
        printf("%s\n", PJ[idx].path);
        /* Touch push.ok check in background */
        char ok[P]; snprintf(ok, P, "%s/logs/push.ok", DDIR);
        if (fork() == 0) {
            char c[B]; snprintf(c, B, "git -C '%s' ls-remote --exit-code origin HEAD>/dev/null 2>&1 && touch '%s'", PJ[idx].path, ok);
            (void)!system(c); _exit(0);
        }
        return 0;
    }
    int ai = idx - NPJ;
    if (ai >= 0 && ai < NAP) {
        printf("> Running: %s\n   Command: %s\n", AP[ai].name, AP[ai].cmd);
        const char *sh = getenv("SHELL"); if (!sh) sh = "/bin/bash";
        execlp(sh, sh, "-c", AP[ai].cmd, (char*)NULL);
    }
    printf("x Invalid index: %d\n", idx); return 1;
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
        fallback_py(argc, argv);
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
        int n = atoi(sel); char c[256]; snprintf(c, 256, "git log -%d --pretty=%%H\\ %%s", n);
        FILE *fp = popen(c, "r"); if (!fp) return 1;
        char line[512]; int total = 0, i = 0;
        while (fgets(line, 512, fp)) {
            line[strcspn(line,"\n")] = 0;
            char *sp = strchr(line, ' '); if (!sp) continue;
            *sp = 0; char *hash = line, *msg = sp + 1;
            char dc[256]; snprintf(dc, 256, "git show %.40s --pretty=", hash);
            FILE *dp = popen(dc, "r"); int ab = 0, db_ = 0;
            if (dp) { char dl[4096]; while (fgets(dl, 4096, dp)) { int l = strlen(dl);
                if (dl[0]=='+' && dl[1]!='+') ab += l-1;
                else if (dl[0]=='-' && dl[1]!='-') db_ += l-1;
            } pclose(dp); }
            int tok = (ab - db_) / 4; total += tok;
            if (strlen(msg) > 55) { msg[52]='.'; msg[53]='.'; msg[54]='.'; msg[55]=0; }
            printf("  %d  %+6d  %s\n", i++, tok, msg);
        }
        pclose(fp); printf("\nTotal: %+d tokens\n", total); return 0;
    }
    /* Full diff mode - delegate to python for color output */
    fallback_py(argc, argv);
}

/* ── revert ── */
static int cmd_revert(int argc, char **argv) {
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
        sqlite3_stmt *st;
        sqlite3_prepare_v2(dbopen(), "INSERT OR REPLACE INTO config VALUES(?,?)", -1, &st, 0);
        sqlite3_bind_text(st, 1, key, -1, 0); sqlite3_bind_text(st, 2, val, -1, 0);
        sqlite3_step(st); sqlite3_finalize(st);
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
    sqlite3_stmt *st;
    sqlite3_prepare_v2(dbopen(), "INSERT OR REPLACE INTO config VALUES('default_prompt',?)", -1, &st, 0);
    sqlite3_bind_text(st, 1, val, -1, 0); sqlite3_step(st); sqlite3_finalize(st);
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
static int cmd_attach(int argc, char **argv) {
    init_db();
    /* Simple: list multi_runs */
    sqlite3_stmt *st; sqlite3 *d = dbopen();
    sqlite3_prepare_v2(d, "SELECT id,repo FROM multi_runs ORDER BY created_at DESC LIMIT 10", -1, &st, 0);
    int i = 0;
    while (sqlite3_step(st) == SQLITE_ROW) {
        const char *id = (const char*)sqlite3_column_text(st, 0);
        const char *repo = (const char*)sqlite3_column_text(st, 1);
        char sn[256]; snprintf(sn, 256, "%s-%s", bname(repo), id);
        printf("  %d  %s %s\n", i++, tm_has(sn)?"\xe2\x97\x8f":"\xe2\x97\x8b", sn);
    }
    sqlite3_finalize(st);
    if (!i) { puts("No sessions"); return 0; }
    if (argc > 2 && argv[2][0] >= '0' && argv[2][0] <= '9') {
        sqlite3_prepare_v2(d, "SELECT id,repo FROM multi_runs ORDER BY created_at DESC LIMIT 10", -1, &st, 0);
        int target = atoi(argv[2]); i = 0;
        while (sqlite3_step(st) == SQLITE_ROW && i <= target) {
            if (i == target) {
                const char *id = (const char*)sqlite3_column_text(st, 0);
                const char *repo = (const char*)sqlite3_column_text(st, 1);
                char sn[256]; snprintf(sn, 256, "%s-%s", bname(repo), id);
                sqlite3_finalize(st); tm_go(sn);
            }
            i++;
        }
        sqlite3_finalize(st);
    }
    puts("\nSelect:\n  aio attach 0"); return 0;
}

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

/* ── note ── */
static int cmd_note(int argc, char **argv) {
    char dir[P]; snprintf(dir, P, "%s/notes", SROOT); mkdirp(dir);
    /* Quick add */
    if (argc > 2 && argv[2][0] != '?') {
        char text[B] = ""; for (int i=2;i<argc;i++) { if(i>2) strcat(text," "); strncat(text,argv[i],B-strlen(text)-2); }
        char ts[64]; time_t now = time(NULL); struct timespec tp; clock_gettime(CLOCK_REALTIME, &tp);
        strftime(ts, 32, "%Y%m%dT%H%M%S", localtime(&now));
        char slug[16]; snprintf(slug, 16, "%08x", (unsigned)(tp.tv_nsec ^ (unsigned)now));
        char fn[P]; snprintf(fn, P, "%s/%s_%s.%09ld.txt", dir, slug, ts, tp.tv_nsec);
        char ct[32]; strftime(ct, 32, "%Y-%m-%d %H:%M", localtime(&now));
        char data[B]; snprintf(data, B, "Text: %s\nStatus: pending\nDevice: %s\nCreated: %s\n", text, DEV, ct);
        writef(fn, data); sync_repo();
        puts("\xe2\x9c\x93"); return 0;
    }
    /* List notes */
    char paths[512][P]; int n = listdir(dir, paths, 512);
    if (!n) { puts("a n <text>"); return 0; }
    /* Sort by name descending (timestamp in name) */
    /* Print pending notes */
    sync_repo();
    n = listdir(dir, paths, 512); /* reload after sync */
    int shown = 0;
    for (int i = 0; i < n && shown < 20; i++) {
        kvs_t kv = kvfile(paths[i]);
        const char *text = kvget(&kv, "Text");
        const char *status = kvget(&kv, "Status");
        if (!text || (status && strcmp(status, "pending"))) continue;
        const char *proj = kvget(&kv, "Project");
        printf("%s%s\n", text, proj ? proj : "");
        shown++;
    }
    if (!shown) puts("a n <text>");
    return 0;
}

/* ── task ── */
static int cmd_task(int argc, char **argv) {
    char dir[P]; snprintf(dir, P, "%s/tasks", SROOT); mkdirp(dir);
    const char *sub = argc > 2 ? argv[2] : NULL;
    /* List */
    if (!sub || !strcmp(sub,"l") || !strcmp(sub,"ls") || !strcmp(sub,"list")) {
        sync_repo();
        DIR *d = opendir(dir); if (!d) { puts("No tasks"); return 0; }
        struct dirent *e; int i = 0;
        while ((e = readdir(d))) {
            if (e->d_name[0] == '.') continue;
            char fp[P]; snprintf(fp, P, "%s/%s", dir, e->d_name);
            if (e->d_type == DT_DIR) {
                /* Folder: read latest text_*.txt inside */
                char tpaths[16][P]; int tn = listdir(fp, tpaths, 16);
                const char *text = NULL;
                for (int j = tn - 1; j >= 0; j--) {
                    if (strstr(tpaths[j], "text_")) {
                        kvs_t kv = kvfile(tpaths[j]);
                        text = kvget(&kv, "Text");
                        if (!text) { /* flat text file, first line */
                            size_t len; char *raw = readf(tpaths[j], &len);
                            if (raw) { char *nl = strchr(raw, '\n'); if (nl) *nl = 0; text = raw; }
                        }
                        if (text) break;
                    }
                }
                if (text) printf("  %d. [d] %.60s\n", i++, text);
            } else if (e->d_type == DT_REG && strstr(e->d_name, ".txt")) {
                /* Flat .txt file: first line is task text */
                size_t len; char *raw = readf(fp, &len);
                if (raw) { char *nl = strchr(raw, '\n'); if (nl) *nl = 0; printf("  %d. [f] %.60s\n", i++, raw); free(raw); }
            }
        }
        closedir(d);
        if (!i) puts("No tasks");
        return 0;
    }
    /* Add */
    if (!strcmp(sub,"add") || !strcmp(sub,"a")) {
        if (argc < 4) { puts("Usage: a task add <text>"); return 1; }
        char text[B] = ""; for (int i=3;i<argc;i++) { if(i>3) strcat(text," "); strncat(text,argv[i],B-strlen(text)-2); }
        /* Create task folder */
        char slug[64]; snprintf(slug, 64, "%.32s", text);
        for (char *p=slug;*p;p++) if(*p==' '||*p=='/')*p='-'; else if(*p>='A'&&*p<='Z')*p+=32;
        char ts[64]; time_t now = time(NULL); struct timespec tp; clock_gettime(CLOCK_REALTIME, &tp);
        strftime(ts, 32, "%Y%m%dT%H%M%S", localtime(&now));
        char td[P]; snprintf(td, P, "%s/%s", dir, slug); mkdirp(td);
        char fn[P]; snprintf(fn, P, "%s/text_%s.%09ld.txt", td, ts, tp.tv_nsec);
        char ct[32]; strftime(ct, 32, "%Y-%m-%d %H:%M", localtime(&now));
        char data[B]; snprintf(data, B, "Text: %s\nDevice: %s\nCreated: %s\n", text, DEV, ct);
        writef(fn, data); sync_repo();
        puts("\xe2\x9c\x93"); return 0;
    }
    /* Delete */
    if (!strcmp(sub,"d") || !strcmp(sub,"del") || !strcmp(sub,"delete")) {
        /* Delegate to python for interactive */
        fallback_py(argc, argv);
    }
    /* Other task subcommands -> python */
    fallback_py(argc, argv);
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
        printf("SSH\n  %s\n  %s\nHosts:\n", dir, urlout);
        for (int i = 0; i < nh; i++)
            printf("  %d. %s: %s%s\n", i, hosts[i].name, hosts[i].host, hosts[i].pw[0]?" [pw]":"");
        if (!nh) puts("  (none)");
        puts("\nConnect: a ssh <#>\nRun:     a ssh <#> <cmd>");
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
    /* self */
    if (!strcmp(sub,"self")) { fallback_py(argc, argv); }
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
    mkdirp(LOGDIR);
    const char *sub = argc > 2 ? argv[2] : NULL;
    if (sub && !strcmp(sub, "sync")) { fallback_py(argc, argv); }
    if (sub && !strcmp(sub, "grab")) { fallback_py(argc, argv); }
    /* List logs */
    char c[B], out[B*4];
    snprintf(c, B, "ls -t '%s'/*.log 2>/dev/null | head -12", LOGDIR);
    pcmd(c, out, sizeof(out));
    if (!out[0]) { puts("No logs"); return 0; }
    printf("Local logs:\n%s", out);
    if (sub && sub[0] >= '0' && sub[0] <= '9') {
        /* View log by number */
        char *lines[12]; int n = 0; char *p = out;
        while (*p && n < 12) { lines[n++] = p; char *e = strchr(p,'\n'); if(e){*e=0;p=e+1;}else break; }
        int idx = atoi(sub);
        if (idx >= 0 && idx < n) {
            snprintf(c, B, "tmux new-window 'cat \"%s\"; read'", lines[idx]); (void)!system(c);
        }
    }
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
    const char *folders[] = {"common","ssh","login","hub","notes","workspace","docs","tasks"};
    for (int i = 0; i < 8; i++) {
        char d[P]; snprintf(d, P, "%s/%s", SROOT, folders[i]);
        if (!dexists(d)) continue;
        char cnt_cmd[P]; snprintf(cnt_cmd, P, "find '%s' -name '*.txt' -maxdepth 2 2>/dev/null | wc -l", d);
        char cnt[16]; pcmd(cnt_cmd, cnt, 16); cnt[strcspn(cnt,"\n")] = 0;
        printf("  %s: %s files\n", folders[i], cnt);
    }
    if (argc > 2 && !strcmp(argv[2], "all")) {
        puts("\n--- Broadcasting to SSH hosts ---");
        char bc[B]; snprintf(bc, B, "%s/archive/a.py", SDIR);
        char cmd[B]; snprintf(cmd, B, "python3 '%s' ssh all 'a sync'", bc); (void)!system(cmd);
    }
    return 0;
}

/* ── update ── */
static int cmd_update(int argc, char **argv) {
    const char *sub = argc > 2 ? argv[2] : NULL;
    if (sub && (!strcmp(sub,"help")||!strcmp(sub,"-h"))) {
        puts("a update - Update a from git + refresh caches\n  a update        Pull latest\n  a update shell  Refresh shell config\n  a update cache  Refresh caches");
        return 0;
    }
    if (sub && (!strcmp(sub,"bash")||!strcmp(sub,"zsh")||!strcmp(sub,"shell")||!strcmp(sub,"cache"))) {
        init_db(); load_cfg(); list_all(1, 0);
        /* Refresh i_cache.txt */
        load_proj(); load_apps();
        char ic[P]; snprintf(ic, P, "%s/i_cache.txt", DDIR);
        FILE *f = fopen(ic, "w"); if (f) {
            for (int i=0;i<NPJ;i++) fprintf(f, "%d: %s (%s)\n", i, bname(PJ[i].path), PJ[i].path);
            for (int i=0;i<NAP;i++) fprintf(f, "%d: %s\n", NPJ+i, AP[i].name);
            const char *cmds[] = {"help","update","jobs","kill","attach","cleanup","config","ls","diff","send","watch",
                "push","pull","revert","set","install","uninstall","deps","prompt","gdrive","add","remove","move",
                "dash","all","backup","scan","copy","log","done","agent","tree","dir","web","ssh","run","hub",
                "task","ui","review","note"};
            for (int i=0;i<40;i++) fprintf(f, "%s\n", cmds[i]);
            fclose(f);
        }
        puts("\xe2\x9c\x93 Cache"); return 0;
    }
    /* Full update */
    char c[B]; snprintf(c, B, "git -C '%s/..' rev-parse --git-dir 2>/dev/null", SDIR);
    if (system(c) != 0) { puts("x Not in git repo"); return 0; }
    snprintf(c, B, "git -C '%s/..' fetch 2>/dev/null", SDIR); (void)!system(c);
    snprintf(c, B, "git -C '%s/..' status -uno 2>/dev/null", SDIR);
    char out[B]; pcmd(c, out, B);
    if (!strstr(out, "behind")) {
        printf("\xe2\x9c\x93 Up to date\n");
    } else {
        puts("Downloading...");
        snprintf(c, B, "git -C '%s/..' pull --ff-only 2>/dev/null", SDIR); (void)!system(c);
    }
    /* Refresh shell + caches */
    snprintf(c, B, "bash '%s/../install.sh' --shell 2>/dev/null", SDIR); (void)!system(c);
    init_db(); load_cfg(); list_all(1, 0);
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
            int cl = strlen(cmd); snprintf(cmd + cl, (int)sizeof(cmd) - cl, " '%s'", full);
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
        int cl = strlen(cmd); snprintf(cmd + cl, (int)sizeof(cmd) - cl, " '%s'", full);
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
static int cmd_dir_file(int argc, char **argv) {
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

/* ═══ MAIN DISPATCH ═══ */
int main(int argc, char **argv) {
    init_paths();
    G_argc = argc; G_argv = argv;

    if (argc < 2) return cmd_help(argc, argv);

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
    if (!strcmp(arg,"i")) fallback_py(argc, argv);
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
