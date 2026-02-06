/*
 * ac - fast C dispatcher for 'a' commands
 *
 * Design inspired by:
 *   Linux kernel: switch-based syscall dispatch (arch/x86/entry/syscall_64.c)
 *     - Compiler turns switch into jump table = O(1) dispatch
 *   Git: sorted cmd_struct array with function pointers (git.c)
 *     - Clean {name, fn, flags} pattern for extensibility
 *
 * Hybrid approach: switch on first char (jump table) -> strcmp tiny subset
 * Fast-path commands (help, project#, done, hi) run in C (~0ms)
 * Complex commands exec into python (~100ms) only when needed
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <dirent.h>
#include <time.h>
#include <fcntl.h>
#include <errno.h>
#include <signal.h>
#include <sys/wait.h>

/* ── paths ── */
#define DATA_DIR_SUFFIX "/.local/share/a"
#define HELP_CACHE      "/help_cache.txt"
#define PROJECTS_FILE   "/projects.txt"
#define DONE_FILE       "/.done"

static char data_dir[512];
static char script_dir[512];  /* directory containing ac binary / a.py */
static char py_path[640];     /* path to a.py for fallback */

/* ── init paths once ── */
static void init_paths(void) {
    const char *home = getenv("HOME");
    if (!home) home = "/tmp";
    snprintf(data_dir, sizeof(data_dir), "%s" DATA_DIR_SUFFIX, home);
    /* script_dir = realpath of binary's parent */
    char self[512];
    ssize_t n = readlink("/proc/self/exe", self, sizeof(self) - 1);
    if (n > 0) {
        self[n] = '\0';
        char *sl = strrchr(self, '/');
        if (sl) { *sl = '\0'; snprintf(script_dir, sizeof(script_dir), "%s", self); }
    }
    snprintf(py_path, sizeof(py_path), "%s/../a.py", script_dir);
}

/* ── helpers ── */
static int file_exists(const char *p) {
    struct stat st;
    return stat(p, &st) == 0;
}

static int dir_exists(const char *p) {
    struct stat st;
    return stat(p, &st) == 0 && S_ISDIR(st.st_mode);
}

/* Print file contents to stdout - like cat but zero-copy with sendfile */
static int cat_file(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return -1;
    char buf[8192];
    ssize_t n;
    while ((n = read(fd, buf, sizeof(buf))) > 0)
        (void)!write(STDOUT_FILENO, buf, n);
    close(fd);
    return 0;
}

/* Read file into malloc'd buffer, returns NULL on failure */
static char *read_file(const char *path, size_t *len) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return NULL;
    struct stat st;
    if (fstat(fd, &st) < 0) { close(fd); return NULL; }
    char *buf = malloc(st.st_size + 1);
    if (!buf) { close(fd); return NULL; }
    ssize_t n = read(fd, buf, st.st_size);
    close(fd);
    if (n < 0) { free(buf); return NULL; }
    buf[n] = '\0';
    if (len) *len = n;
    return buf;
}

/* Get Nth line from file (0-indexed), returns malloc'd string */
static char *get_line_n(const char *path, int lineno) {
    char *data = read_file(path, NULL);
    if (!data) return NULL;
    char *p = data;
    for (int i = 0; i < lineno && *p; i++) {
        p = strchr(p, '\n');
        if (!p) { free(data); return NULL; }
        p++;
    }
    char *end = strchr(p, '\n');
    if (!end) end = p + strlen(p);
    int slen = end - p;
    char *line = malloc(slen + 1);
    memcpy(line, p, slen);
    line[slen] = '\0';
    free(data);
    return line;
}

/* ── fallback: exec python a.py with same args ── */
__attribute__((noreturn))
static void fallback_python(int argc, char **argv) {
    /* Build args: python3 a.py <original args...> */
    char **nargv = malloc((argc + 3) * sizeof(char *));
    nargv[0] = "python3";
    nargv[1] = py_path;
    for (int i = 1; i < argc; i++)
        nargv[i + 1] = argv[i];
    nargv[argc + 1] = NULL;
    execvp("python3", nargv);
    /* If exec fails */
    perror("ac: exec python3 failed");
    _exit(127);
}

/* ═══════════════════════════════════════════════════════════════════
 * BUILT-IN COMMANDS (pure C, no python needed)
 * ═══════════════════════════════════════════════════════════════════ */

/* ac (no args) - show cached help */
static int cmd_help(int argc, char **argv) {
    char path[600];
    snprintf(path, sizeof(path), "%s" HELP_CACHE, data_dir);
    if (cat_file(path) < 0) {
        /* No cache, fall back to python to generate it */
        fallback_python(argc, argv);
    }
    return 0;
}

/* ac <num> - cd to project (prints path for shell function to cd) */
static int cmd_project_num(int argc, char **argv, int idx) {
    char path[600];
    snprintf(path, sizeof(path), "%s" PROJECTS_FILE, data_dir);
    char *dir = get_line_n(path, idx);
    if (dir && dir_exists(dir)) {
        printf("%s\n", dir);
        free(dir);
        return 0;
    }
    if (dir) free(dir);
    /* Fall back to python for app commands or clone logic */
    fallback_python(argc, argv);
}

/* ac done - touch done file */
static int cmd_done(void) {
    char path[600];
    snprintf(path, sizeof(path), "%s" DONE_FILE, data_dir);
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) close(fd);
    puts("\xe2\x9c\x93 done");  /* ✓ done */
    return 0;
}

/* ac hi */
static int cmd_hi(void) {
    for (int i = 1; i <= 10; i++) printf("%d\n", i);
    puts("hi");
    return 0;
}

/* ac dir - show cwd + ls */
static int cmd_dir(void) {
    char cwd[1024];
    if (getcwd(cwd, sizeof(cwd)))
        puts(cwd);
    execlp("ls", "ls", NULL);
    return 1;
}

/* ac diff <num> - show token history for last N commits (fast path)
 * Counts actual diff +/- bytes / 4 as token proxy (matches python's fallback) */
static int cmd_diff_tokens(int n) {
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "git log -%d --pretty=%%H\\ %%s", n);
    FILE *fp = popen(cmd, "r");
    if (!fp) return 1;

    char line[512];
    int total = 0, i = 0;
    while (fgets(line, sizeof(line), fp)) {
        line[strcspn(line, "\n")] = '\0';
        char *sp = strchr(line, ' ');
        if (!sp) continue;
        *sp = '\0';
        char *hash = line, *msg = sp + 1;

        /* Count bytes of added/removed lines in the actual diff */
        char dcmd[256];
        snprintf(dcmd, sizeof(dcmd), "git show %.40s --pretty=", hash);
        FILE *dp = popen(dcmd, "r");
        int add_bytes = 0, del_bytes = 0;
        if (dp) {
            char dl[4096];
            while (fgets(dl, sizeof(dl), dp)) {
                int len = strlen(dl);
                if (dl[0] == '+' && dl[1] != '+') add_bytes += len - 1;
                else if (dl[0] == '-' && dl[1] != '-') del_bytes += len - 1;
            }
            pclose(dp);
        }
        int tok = (add_bytes - del_bytes) / 4;
        total += tok;

        if (strlen(msg) > 55) { msg[52] = '.'; msg[53] = '.'; msg[54] = '.'; msg[55] = '\0'; }
        printf("  %d  %+6d  %s\n", i, tok, msg);
        i++;
    }
    pclose(fp);
    printf("\nTotal: %+d tokens\n", total);
    return 0;
}

/* ac push [msg] - fast git add/commit/push */
static int cmd_push(int argc, char **argv) {
    /* Check if .git exists */
    if (!dir_exists(".git")) {
        fallback_python(argc, argv);
    }

    /* Build commit message */
    char msg[1024] = {0};
    if (argc > 2) {
        for (int i = 2; i < argc; i++) {
            if (i > 2) strcat(msg, " ");
            strncat(msg, argv[i], sizeof(msg) - strlen(msg) - 2);
        }
    } else {
        char cwd[512];
        if (!getcwd(cwd, sizeof(cwd))) strcpy(cwd, ".");
        char *base = strrchr(cwd, '/');
        snprintf(msg, sizeof(msg), "Update %s", base ? base + 1 : cwd);
    }

    /* Check recent push success for instant mode */
    char ok_path[600];
    snprintf(ok_path, sizeof(ok_path), "%s/logs/push.ok", data_dir);
    struct stat st;
    if (stat(ok_path, &st) == 0 && time(NULL) - st.st_mtime < 600) {
        /* Instant mode - fire and forget */
        pid_t pid = fork();
        if (pid == 0) {
            setsid();
            int null = open("/dev/null", O_RDWR);
            dup2(null, 0); dup2(null, 1); dup2(null, 2);
            if (null > 2) close(null);
            char cmd[2048];
            snprintf(cmd, sizeof(cmd),
                "git add -A && git commit -m \"%s\" --allow-empty 2>/dev/null; "
                "git push 2>/dev/null; touch \"%s\"", msg, ok_path);
            execl("/bin/sh", "sh", "-c", cmd, NULL);
            _exit(1);
        }
        /* Check for changes */
        FILE *fp = popen("git status --porcelain 2>/dev/null", "r");
        char buf[64] = {0};
        if (fp) { if (!fgets(buf, sizeof(buf), fp)) buf[0] = '\0'; pclose(fp); }
        printf("%s %s\n", buf[0] ? "\xe2\x9c\x93" : "\xe2\x97\x8b", msg);
        return 0;
    }

    /* Real push - fall back to python for repo create logic */
    fallback_python(argc, argv);
}

/* ac ls - list tmux sessions */
static int cmd_ls(int argc, char **argv) {
    if (argc > 2) fallback_python(argc, argv);
    FILE *fp = popen("tmux list-sessions -F '#{session_name}' 2>/dev/null", "r");
    if (!fp) { puts("No sessions"); return 0; }
    char line[256];
    int i = 0, any = 0;
    while (fgets(line, sizeof(line), fp)) {
        line[strcspn(line, "\n")] = '\0';
        if (!line[0]) continue;
        any = 1;
        /* Get pane path */
        char cmd[512];
        snprintf(cmd, sizeof(cmd), "tmux display-message -p -t '%s' '#{pane_current_path}' 2>/dev/null", line);
        FILE *pp = popen(cmd, "r");
        char path[512] = {0};
        if (pp) { if (!fgets(path, sizeof(path), pp)) path[0] = '\0'; pclose(pp); path[strcspn(path, "\n")] = '\0'; }
        printf("  %d  %s: %s\n", i++, line, path);
    }
    pclose(fp);
    if (!any) puts("No sessions");
    else puts("\nSelect:\n  ac ls 0");
    return 0;
}

/* ac kill [#|all] */
static int cmd_kill(int argc, char **argv) {
    const char *sel = argc > 2 ? argv[2] : NULL;
    if (sel && (!strcmp(sel, "all") || !strcmp(argv[1], "killall"))) {
        (void)!system("pkill -9 -f tmux 2>/dev/null");
        (void)!system("clear");
        puts("\xe2\x9c\x93");
        return 0;
    }
    /* List and select - fall to python for interactive */
    fallback_python(argc, argv);
}


/* ═══════════════════════════════════════════════════════════════════
 * COMMAND DISPATCH
 *
 * Hybrid of Linux kernel (switch jump table) + git (cmd_struct array)
 *
 * 1. Numeric args handled directly (project number)
 * 2. Switch on first char -> jump table (compiler optimizes to O(1))
 * 3. Within each case, strcmp against 1-3 candidates
 * 4. Unknown commands fall back to python
 * ═══════════════════════════════════════════════════════════════════ */

/* Flags for cmd_struct */
#define C_NATIVE   0x01   /* Fully implemented in C */
#define C_FALLBACK 0x02   /* Always falls back to python */

typedef int (*cmd_fn)(int argc, char **argv);

struct cmd_struct {
    const char *name;
    const char *alias;   /* 3-char abbreviation or NULL */
    cmd_fn fn;
    int flags;
};

/*
 * Master command table - sorted alphabetically for binary search.
 * Commands marked C_NATIVE run entirely in C.
 * Commands marked C_FALLBACK always exec python.
 */
static const struct cmd_struct commands[] = {
    { "add",       NULL,  NULL, C_FALLBACK },
    { "agent",     NULL,  NULL, C_FALLBACK },
    { "all",       NULL,  NULL, C_FALLBACK },
    { "ask",       NULL,  NULL, C_FALLBACK },
    { "attach",    "att", NULL, C_FALLBACK },
    { "backup",    "bak", NULL, C_FALLBACK },
    { "cleanup",   "cle", NULL, C_FALLBACK },
    { "config",    "con", NULL, C_FALLBACK },
    { "copy",      "cop", NULL, C_FALLBACK },
    { "dash",      "das", NULL, C_FALLBACK },
    { "deps",      "dep", NULL, C_FALLBACK },
    { "diff",      "dif", NULL, C_FALLBACK },
    { "dir",       NULL,  NULL, C_FALLBACK },
    { "docs",      "doc", NULL, C_FALLBACK },
    { "done",      NULL,  NULL, C_NATIVE   },
    { "gdrive",    "gdr", NULL, C_FALLBACK },
    { "help",      "hel", NULL, C_FALLBACK },
    { "hub",       NULL,  NULL, C_FALLBACK },
    { "install",   "ins", NULL, C_FALLBACK },
    { "jobs",      "job", NULL, C_FALLBACK },
    { "kill",      "kil", NULL, C_FALLBACK },
    { "log",       NULL,  NULL, C_FALLBACK },
    { "login",     NULL,  NULL, C_FALLBACK },
    { "ls",        NULL,  NULL, C_FALLBACK },
    { "move",      "mov", NULL, C_FALLBACK },
    { "note",      NULL,  NULL, C_FALLBACK },
    { "prompt",    "pro", NULL, C_FALLBACK },
    { "pull",      "pul", NULL, C_FALLBACK },
    { "push",      "pus", NULL, C_FALLBACK },
    { "remove",    "rem", NULL, C_FALLBACK },
    { "repo",      NULL,  NULL, C_FALLBACK },
    { "revert",    "rev", NULL, C_FALLBACK },
    { "review",    NULL,  NULL, C_FALLBACK },
    { "run",       NULL,  NULL, C_FALLBACK },
    { "scan",      "sca", NULL, C_FALLBACK },
    { "send",      "sen", NULL, C_FALLBACK },
    { "set",       NULL,  NULL, C_FALLBACK },
    { "ssh",       NULL,  NULL, C_FALLBACK },
    { "sync",      "syn", NULL, C_FALLBACK },
    { "task",      "tas", NULL, C_FALLBACK },
    { "tree",      "tre", NULL, C_FALLBACK },
    { "ui",        NULL,  NULL, C_FALLBACK },
    { "uninstall", "uni", NULL, C_FALLBACK },
    { "update",    "upd", NULL, C_FALLBACK },
    { "watch",     "wat", NULL, C_FALLBACK },
    { "web",       NULL,  NULL, C_FALLBACK },
};

#define NCMDS (sizeof(commands) / sizeof(commands[0]))

/*
 * Binary search on sorted commands[] - O(log n) vs git's O(n).
 * With 46 commands, worst case is 6 strcmp calls vs 46.
 */
static const struct cmd_struct *find_cmd(const char *name) {
    int lo = 0, hi = NCMDS - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2;
        int cmp = strcmp(name, commands[mid].name);
        if (cmp == 0) return &commands[mid];
        if (cmp < 0) hi = mid - 1;
        else lo = mid + 1;
    }
    /* Check aliases */
    for (int i = 0; i < (int)NCMDS; i++) {
        if (commands[i].alias && !strcmp(name, commands[i].alias))
            return &commands[i];
    }
    return NULL;
}

int main(int argc, char **argv) {
    init_paths();

    /* No args = show help cache */
    if (argc < 2) return cmd_help(argc, argv);

    const char *arg = argv[1];

    /* ── Fast path: numeric = project number ── */
    {
        const char *p = arg;
        while (*p >= '0' && *p <= '9') p++;
        if (*p == '\0' && p != arg)
            return cmd_project_num(argc, argv, atoi(arg));
    }

    /* ── Kernel-style switch on first char for ultra-fast natives ── */
    switch (arg[0]) {
    case 'd':
        if (!strcmp(arg, "done")) return cmd_done();
        if (!strcmp(arg, "dir"))  return cmd_dir();
        break;
    case 'h':
        if (!strcmp(arg, "hi"))   return cmd_hi();
        /* help/hel/--help/-h -> python for full help */
        if (!strcmp(arg, "help") || !strcmp(arg, "hel"))
            fallback_python(argc, argv);
        break;
    case '-':
        if (!strcmp(arg, "--help") || !strcmp(arg, "-h"))
            fallback_python(argc, argv);
        break;
    case 'p':
        if (!strcmp(arg, "push") || !strcmp(arg, "pus") || !strcmp(arg, "p"))
            return cmd_push(argc, argv);
        break;
    case 'l':
        if (!strcmp(arg, "ls"))
            return cmd_ls(argc, argv);
        break;
    case 'k':
        if (!strcmp(arg, "kill") || !strcmp(arg, "kil") || !strcmp(arg, "killall"))
            return cmd_kill(argc, argv);
        break;
    }

    /* ── Special aliases from Python's CMDS dict ── */
    if (!strcmp(arg, "t") || !strcmp(arg, "n") || !strcmp(arg, "i") ||
        !strcmp(arg, "e") || !strcmp(arg, "x") || !strcmp(arg, "a") ||
        !strcmp(arg, "ai") || !strcmp(arg, "aio"))
        fallback_python(argc, argv);

    /* ── Diff with number arg = token count (C fast path) ── */
    if ((!strcmp(arg, "diff") || !strcmp(arg, "dif")) && argc > 2) {
        const char *p = argv[2];
        while (*p >= '0' && *p <= '9') p++;
        if (*p == '\0') return cmd_diff_tokens(atoi(argv[2]));
    }

    /* ── Binary search the command table ── */
    const struct cmd_struct *cmd = find_cmd(arg);
    if (cmd) {
        if (cmd->fn && (cmd->flags & C_NATIVE))
            return cmd->fn(argc, argv);
        /* Fall back to python for non-native commands */
        fallback_python(argc, argv);
    }

    /* ── Directory/file arg handling ── */
    if (dir_exists(arg) || file_exists(arg))
        fallback_python(argc, argv);

    /* ── Check ~/projects/<arg> ── */
    if (arg[0] == '/') {
        char expanded[1024];
        const char *home = getenv("HOME");
        snprintf(expanded, sizeof(expanded), "%s%s", home, arg);
        if (dir_exists(expanded))
            fallback_python(argc, argv);
    }

    /* ── Session key (single/double char like 'c', 'l', 'g', 'cp', 'lp') ── */
    if (strlen(arg) <= 3 && arg[0] >= 'a' && arg[0] <= 'z')
        fallback_python(argc, argv);

    /* ── Worktree pattern: starts with 'w', ends with '++' ── */
    {
        size_t len = strlen(arg);
        if (len >= 3 && arg[len-1] == '+' && arg[len-2] == '+')
            fallback_python(argc, argv);
        if (arg[0] == 'w' && strcmp(arg, "watch") && strcmp(arg, "web"))
            fallback_python(argc, argv);
    }

    /* ── x.* experimental commands ── */
    if (arg[0] == 'x' && arg[1] == '.')
        fallback_python(argc, argv);

    /* Unknown - try as session name via python */
    fallback_python(argc, argv);
}
