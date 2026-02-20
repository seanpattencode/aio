/* ── perf: benchmark + timing display ── */
static const char *BENCH_CMDS[] = {
    "help","config","task","backup","ls","add","agent","copy","done","docs",
    "hi","i","move","prompt","rebuild","remove","repo","send","set","setup",
    "uninstall","watch","web",/* "x" kills tmux server, destroys active dev sessions */
    "e","kill","revert","deps","dash","hub",
    "jobs","mono","ssh","work","ask","login","gdrive","email","ui","attach",
    "cleanup","run","pull","diff","all","push","tree","review","log","note",
    "sync","scan","update","install",NULL
};

/* returns microseconds on success, UINT_MAX if killed/timed out */
static volatile pid_t bench_pid;
static void bench_kill(int sig) { (void)sig; if (bench_pid>0) kill(-bench_pid, SIGKILL); }
static unsigned perf_run(const char *cmd) {
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    pid_t p = fork();
    if (p == 0) {
        int null = open("/dev/null", O_WRONLY);
        dup2(null, STDOUT_FILENO); dup2(null, STDERR_FILENO); close(null);
        setpgid(0, 0);
        char bin[P]; snprintf(bin, P, "%s/a", SDIR);
        execl(bin, "a", cmd, (char *)NULL);
        _exit(127);
    }
    /* parent-side timeout: kills child even if it skips perf_arm */
    bench_pid = p;
    signal(SIGALRM, bench_kill);
    alarm(10);
    int status; waitpid(p, &status, 0);
    alarm(0); signal(SIGALRM, SIG_DFL);
    bench_pid = 0;
    clock_gettime(CLOCK_MONOTONIC, &t1);
    unsigned us = (unsigned)((t1.tv_sec - t0.tv_sec) * 1000000 + (t1.tv_nsec - t0.tv_nsec) / 1000);
    if (WIFSIGNALED(status) || (WIFEXITED(status) && WEXITSTATUS(status) == 124))
        return UINT_MAX;
    return us;
}

/* parse limit for cmd from perf file data (microseconds); 0 = not found */
static unsigned perf_limit(const char *data, const char *cmd) {
    if (!data) return 0;
    char needle[128]; snprintf(needle, 128, "\n%s:", cmd);
    const char *m = strstr(data, needle);
    if (!m && !strncmp(data, cmd, strlen(cmd)) && data[strlen(cmd)] == ':')
        m = data - 1;
    if (m) return (unsigned)atoi(m + 1 + strlen(cmd) + 1);
    return 0;
}

/* format microseconds for display: "350us" or "1.5ms" or "2.3s" */
static void fmt_us(unsigned us, char *buf, size_t sz) {
    if (us < 1000) snprintf(buf, sz, "%uus", us);
    else if (us < 1000000) snprintf(buf, sz, "%.1fms", us / 1000.0);
    else snprintf(buf, sz, "%.2fs", us / 1000000.0);
}

static int cmd_perf(int argc, char **argv) {
    perf_disarm();
    init_db();
    char pf[P]; snprintf(pf, P, "%s/perf/%s.txt", SROOT, DEV);
    const char *sub = argc > 2 ? argv[2] : NULL;

    if (sub && (!strcmp(sub,"help")||!strcmp(sub,"-h"))) {
        puts("a perf - Performance regression enforcer\n"
             "  a perf          Show current limits for this device\n"
             "  a perf bench    Benchmark all commands and save tighter limits\n\n"
             "System: every command has a timeout (default 1s local, 5s network/disk).\n"
             "If exceeded, process is killed. Limits only tighten, never loosen.\n"
             "Per-device profiles live in adata/git/perf/{device}.txt and sync across devices.");
        return 0;
    }

    if (!sub || !strcmp(sub, "show")) {
        char *data = readf(pf, NULL);
        printf("PERF — device: %s\n", DEV);
        printf("Profile: %s\n", pf);
        puts("──────────────────────────────────────────────────");
        printf("%-15s %10s  %8s\n", "COMMAND", "LIMIT", "TIMEOUT");
        puts("──────────────────────────────────────────────────");
        for (const char **c = BENCH_CMDS; *c; c++) {
            unsigned lim = perf_limit(data, *c);
            if (lim) { char fb[32]; fmt_us(lim, fb, 32); printf("%-15s %10s  %5us\n", *c, fb, (lim + 999999) / 1000000); }
            else printf("%-15s %10s  %5s\n", *c, "-", "1s");
        }
        puts("──────────────────────────────────────────────────");
        puts("\nDefault: 1s (local). Override with per-device file.");
        puts("Run 'a perf bench' to benchmark and auto-tighten limits.");
        free(data);
        return 0;
    }

    if (!strcmp(sub, "bench")) {
        char *data = readf(pf, NULL);
        printf("PERF BENCH — device: %s\n", DEV);
        puts("─────────────────────────────────────────────────────────────");
        printf("%-12s %10s %10s %10s  %s\n", "COMMAND", "TIME", "LIMIT", "NEW", "STATUS");
        puts("─────────────────────────────────────────────────────────────");
        typedef struct { const char *cmd; unsigned us, old_lim, new_lim; int pass; } res_t;
        int ncmds = 0; for (const char **c = BENCH_CMDS; *c; c++) ncmds++;
        res_t *res = malloc((size_t)ncmds * sizeof(res_t));
        int passed = 0, tightened = 0;
        for (int i = 0; BENCH_CMDS[i]; i++) {
            const char *cmd = BENCH_CMDS[i];
            unsigned us = perf_run(cmd);
            unsigned old = perf_limit(data, cmd);
            /* 1.3x measured, min 500us, never loosen */
            int killed = us == UINT_MAX;
            unsigned t = killed ? 0 : us;
            unsigned proposed = (t * 13 + 9) / 10;
            if (proposed < 500) proposed = 500;
            unsigned new_lim = old;
            int tight = 0;
            if (killed) { new_lim = old; }
            else if (!old) { new_lim = proposed; tight = 1; }
            else if (proposed < old) { new_lim = proposed; tight = 1; }
            res[i] = (res_t){cmd, t, old, new_lim, !killed};
            if (!killed) passed++;
            if (tight) tightened++;
            char ft[32], fo[32], fn[32];
            fmt_us(t, ft, 32); fmt_us(old, fo, 32); fmt_us(new_lim, fn, 32);
            const char *st = killed ? "\033[31mKILLED\033[0m" : tight ? "\033[32m↓ tight\033[0m" : "\033[32m✓\033[0m";
            printf("%-12s %10s %10s %10s  %s\n", cmd, ft, old ? fo : "-", fn, st);
        }
        puts("─────────────────────────────────────────────────────────────");
        printf("%d/%d passed, %d tightened\n\n", passed, ncmds, tightened);
        if (tightened > 0) {
            char pd[P]; snprintf(pd, P, "%s/perf", SROOT); mkdirp(pd);
            FILE *f = fopen(pf, "w");
            if (f) {
                for (int i = 0; BENCH_CMDS[i]; i++)
                    fprintf(f, "%s:%u\n", res[i].cmd, res[i].new_lim);
                fclose(f);
                printf("\033[32m✓\033[0m Saved: %s\n", pf);
                printf("  Limits only tighten — faster code = tighter limits next bench\n");
            }
        } else puts("No limits tightened — all commands at or above current limits.");
        free(data); free(res);
        return 0;
    }

    fprintf(stderr, "a perf: unknown subcommand '%s'. Try 'a perf help'\n", sub);
    return 1;
}
