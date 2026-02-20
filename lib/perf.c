/* ── perf: benchmark + timing display ── */
static const char *BENCH_CMDS[] = {
    "help","config","task","backup","ls","add","agent","copy","done","docs",
    "hi","i","move","prompt","rebuild","remove","repo","send","set","setup",
    "uninstall","watch","web","x","e","kill","revert","deps","dash","hub",
    "jobs","mono","ssh","work","ask","login","gdrive","email","ui","attach",
    "cleanup","run","pull","diff","all","push","tree","review","log","note",
    "sync","scan","update","install",NULL
};

/* returns ms on success, UINT_MAX if killed by perf timeout */
static unsigned perf_run(const char *cmd) {
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    pid_t p = fork();
    if (p == 0) {
        int null = open("/dev/null", O_WRONLY);
        dup2(null, STDOUT_FILENO); dup2(null, STDERR_FILENO); close(null);
        /* new process group so perf kill doesn't cascade */
        setpgid(0, 0);
        char bin[P]; snprintf(bin, P, "%s/a", SDIR);
        execl(bin, "a", cmd, (char *)NULL);
        _exit(127);
    }
    int status; waitpid(p, &status, 0);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    unsigned ms = (unsigned)((t1.tv_sec - t0.tv_sec) * 1000 + (t1.tv_nsec - t0.tv_nsec) / 1000000);
    /* perf_alarm does _exit(124); signals also mean killed */
    if (WIFSIGNALED(status) || (WIFEXITED(status) && WEXITSTATUS(status) == 124))
        return UINT_MAX;
    return ms;
}

/* parse limit for cmd from perf file data; 0 = not found */
static unsigned perf_limit(const char *data, const char *cmd) {
    if (!data) return 0;
    char needle[128]; snprintf(needle, 128, "\n%s:", cmd);
    const char *m = strstr(data, needle);
    if (!m && !strncmp(data, cmd, strlen(cmd)) && data[strlen(cmd)] == ':')
        m = data - 1;
    if (m) return (unsigned)atoi(m + 1 + strlen(cmd) + 1);
    return 0;
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
        puts("────────────────────────────────────────");
        printf("%-15s %8s  %8s\n", "COMMAND", "LIMIT", "TIMEOUT");
        puts("────────────────────────────────────────");
        for (const char **c = BENCH_CMDS; *c; c++) {
            unsigned lim = perf_limit(data, *c);
            if (lim) printf("%-15s %5ums  %5us\n", *c, lim, (lim + 999) / 1000);
            else     printf("%-15s %8s  %5s\n", *c, "-", "1s");
        }
        puts("────────────────────────────────────────");
        puts("\nDefault: 1s (local), 5s (network/disk). Override with per-device file.");
        puts("Run 'a perf bench' to benchmark and auto-tighten limits.");
        free(data);
        return 0;
    }

    if (!strcmp(sub, "bench")) {
        char *data = readf(pf, NULL);
        printf("PERF BENCH — device: %s\n", DEV);
        puts("────────────────────────────────────────────────────");
        printf("%-12s %7s %7s %7s  %s\n", "COMMAND", "TIME", "LIMIT", "NEW", "STATUS");
        puts("────────────────────────────────────────────────────");
        /* collect results */
        typedef struct { const char *cmd; unsigned ms, old_lim, new_lim; int pass; } res_t;
        int ncmds = 0; for (const char **c = BENCH_CMDS; *c; c++) ncmds++;
        res_t *res = malloc((size_t)ncmds * sizeof(res_t));
        int passed = 0, tightened = 0;
        for (int i = 0; BENCH_CMDS[i]; i++) {
            const char *cmd = BENCH_CMDS[i];
            unsigned ms = perf_run(cmd);
            unsigned old = perf_limit(data, cmd);
            /* new limit: 3x measured, min 50ms, but never loosen */
            int killed = ms == UINT_MAX;
            unsigned t = killed ? 0 : ms;
            unsigned proposed = t * 3 < 50 ? 50 : t * 3;
            unsigned new_lim = old;
            int tight = 0;
            if (killed) { new_lim = old; } /* killed — keep old */
            else if (!old) { new_lim = proposed; tight = 1; } /* no previous — set */
            else if (proposed < old) { new_lim = proposed; tight = 1; } /* tighter */
            res[i] = (res_t){cmd, t, old, new_lim, !killed};
            if (!killed) passed++;
            if (tight) tightened++;
            const char *st = killed ? "\033[31mKILLED\033[0m" : tight ? "\033[32m↓ tight\033[0m" : "\033[32m✓\033[0m";
            printf("%-12s %5ums %5ums %5ums  %s\n", cmd, t, old, new_lim, st);
        }
        puts("────────────────────────────────────────────────────");
        printf("%d/%d passed, %d tightened\n\n", passed, ncmds, tightened);
        /* save */
        if (tightened > 0) {
            FILE *f = fopen(pf, "w");
            if (f) {
                for (int i = 0; BENCH_CMDS[i]; i++)
                    fprintf(f, "%s:%u\n", res[i].cmd, res[i].new_lim);
                fclose(f);
                printf("\033[32m✓\033[0m Saved: %s\n", pf);
                printf("  Limits only tighten — faster code = tighter limits next bench\n");
                printf("  Syncs to all devices via: a sync\n");
            }
        } else {
            puts("No limits tightened — all commands at or above current limits.");
        }
        free(data); free(res);
        return 0;
    }

    fprintf(stderr, "a perf: unknown subcommand '%s'. Try 'a perf help'\n", sub);
    return 1;
}
