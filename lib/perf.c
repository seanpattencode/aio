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
        int ncmds = 0; for (const char **c = BENCH_CMDS; *c; c++) ncmds++;
        typedef struct { const char *cmd; pid_t pid; unsigned us, old_lim, new_lim; int done, pass; } res_t;
        res_t *res = calloc((size_t)ncmds, sizeof(res_t));

        /* fork all commands in parallel */
        struct timespec t0; clock_gettime(CLOCK_MONOTONIC, &t0);
        int nul = open("/dev/null", O_RDWR);
        char bin[P]; snprintf(bin, P, "%s/a", SDIR);
        for (int i = 0; i < ncmds; i++) {
            res[i].cmd = BENCH_CMDS[i];
            res[i].old_lim = perf_limit(data, BENCH_CMDS[i]);
            pid_t p = fork();
            if (p == 0) {
                dup2(nul, STDIN_FILENO); dup2(nul, STDOUT_FILENO); dup2(nul, STDERR_FILENO);
                setpgid(0, 0);
                putenv("A_BENCH=1");
                execl(bin, "a", BENCH_CMDS[i], (char *)NULL);
                _exit(127);
            }
            res[i].pid = p;
            setpgid(p, p); /* race-safe: set in both parent and child */
        }
        close(nul);

        /* reap with 5s hard deadline */
        int remaining = ncmds;
        while (remaining > 0) {
            struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
            unsigned long elapsed = (unsigned long)(now.tv_sec - t0.tv_sec) * 1000000
                + (unsigned long)(now.tv_nsec - t0.tv_nsec) / 1000;
            if (elapsed > 5000000) {
                for (int i = 0; i < ncmds; i++) if (!res[i].done) {
                    kill(-res[i].pid, SIGKILL); kill(res[i].pid, SIGKILL);
                    waitpid(res[i].pid, NULL, 0);
                    res[i].done = 1; res[i].us = UINT_MAX; remaining--;
                }
                break;
            }
            int status; pid_t p = waitpid(-1, &status, WNOHANG);
            if (p > 0) {
                clock_gettime(CLOCK_MONOTONIC, &now);
                unsigned us = (unsigned)((now.tv_sec - t0.tv_sec) * 1000000
                    + (now.tv_nsec - t0.tv_nsec) / 1000);
                for (int i = 0; i < ncmds; i++) if (res[i].pid == p && !res[i].done) {
                    res[i].done = 1; remaining--;
                    if (WIFSIGNALED(status) || (WIFEXITED(status) && WEXITSTATUS(status) == 124))
                        { res[i].us = UINT_MAX; }
                    else { res[i].us = us; res[i].pass = 1; }
                    break;
                }
            } else usleep(500);
        }

        /* compute limits + display */
        struct timespec tend; clock_gettime(CLOCK_MONOTONIC, &tend);
        unsigned total_us = (unsigned)((tend.tv_sec - t0.tv_sec) * 1000000
            + (tend.tv_nsec - t0.tv_nsec) / 1000);
        char ft_total[32]; fmt_us(total_us, ft_total, 32);
        printf("PERF BENCH — device: %s (%s)\n", DEV, ft_total);
        puts("─────────────────────────────────────────────────────────────");
        printf("%-12s %10s %10s %10s  %s\n", "COMMAND", "TIME", "LIMIT", "NEW", "STATUS");
        puts("─────────────────────────────────────────────────────────────");
        int passed = 0, tightened = 0;
        for (int i = 0; i < ncmds; i++) {
            int killed = res[i].us == UINT_MAX;
            unsigned t = killed ? 0 : res[i].us;
            unsigned proposed = (t * 13 + 9) / 10;
            if (proposed < 500) proposed = 500;
            unsigned old = res[i].old_lim; int tight = 0;
            res[i].new_lim = old;
            if (killed) { /* keep old */ }
            else if (!old) { res[i].new_lim = proposed; tight = 1; }
            else if (proposed < old) { res[i].new_lim = proposed; tight = 1; }
            if (!killed) passed++;
            if (tight) tightened++;
            char ft[32], fo[32], fn[32];
            fmt_us(t, ft, 32); fmt_us(old, fo, 32); fmt_us(res[i].new_lim, fn, 32);
            const char *st = killed ? "\033[31mKILLED\033[0m" : tight ? "\033[32m↓ tight\033[0m" : "\033[32m\xe2\x9c\x93\033[0m";
            printf("%-12s %10s %10s %10s  %s\n", res[i].cmd, ft, old ? fo : "-", fn, st);
        }
        puts("─────────────────────────────────────────────────────────────");
        printf("%d/%d passed, %d tightened\n\n", passed, ncmds, tightened);
        if (tightened > 0) {
            char pd[P]; snprintf(pd, P, "%s/perf", SROOT); mkdirp(pd);
            FILE *f = fopen(pf, "w");
            if (f) {
                for (int i = 0; i < ncmds; i++)
                    fprintf(f, "%s:%u\n", res[i].cmd, res[i].new_lim);
                fclose(f);
                printf("\033[32m\xe2\x9c\x93\033[0m Saved: %s\n", pf);
            }
        } else puts("No limits tightened — all commands at or above current limits.");
        free(data); free(res);
        return 0;
    }

    fprintf(stderr, "a perf: unknown subcommand '%s'. Try 'a perf help'\n", sub);
    return 1;
}
