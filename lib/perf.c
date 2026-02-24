/* ── perf: benchmark + timing display ── */
static const char *BENCH_CMDS[] = {
    "","help","config","task","ls","add","agent","copy","done","docs",
    "hi","i","move","prompt","remove","repo","send","set","setup",
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
    snprintf(buf, sz, "%.3fms", us / 1000.0);
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
            const char *label = (*c)[0] ? *c : "(bare)";
            unsigned lim = perf_limit(data, label);
            if (lim) { char fb[32]; fmt_us(lim, fb, 32); printf("%-15s %10s  %5us\n", label, fb, (lim + 999999) / 1000000); }
            else printf("%-15s %10s  %5s\n", label, "-", "1s");
        }
        puts("──────────────────────────────────────────────────");
        puts("\nDefault: 1s (local). Override with per-device file.");
        puts("Run 'a perf bench' to benchmark and auto-tighten limits.");
        free(data);
        return 0;
    }

    if (!strcmp(sub, "bench")) {
        char *data = readf(pf, NULL);
        const char *only = argc > 3 ? argv[3] : NULL;
        int ncmds = 0; for (const char **c = BENCH_CMDS; *c; c++) ncmds++;
        typedef struct { const char *cmd; pid_t pid; unsigned us, old_lim, new_lim; int done, pass, skip; } res_t;
        res_t *res = calloc((size_t)ncmds, sizeof(res_t));

        /* fork commands in parallel */
        struct timespec t0; clock_gettime(CLOCK_MONOTONIC, &t0);
        int nul = open("/dev/null", O_RDWR);
        char bin[P]; snprintf(bin, P, "%s/a", SDIR);
        for (int i = 0; i < ncmds; i++) {
            res[i].cmd = BENCH_CMDS[i];
            res[i].old_lim = perf_limit(data, BENCH_CMDS[i][0] ? BENCH_CMDS[i] : "(bare)");
            if (only && strcmp(only, BENCH_CMDS[i][0] ? BENCH_CMDS[i] : "bare")) { res[i].skip = 1; res[i].done = 1; continue; }
            pid_t p = fork();
            if (p == 0) {
                dup2(nul, STDIN_FILENO); dup2(nul, STDOUT_FILENO); dup2(nul, STDERR_FILENO);
                setpgid(0, 0);
                putenv("A_BENCH=1");
                if (BENCH_CMDS[i][0]) execl(bin, "a", BENCH_CMDS[i], (char *)NULL);
                else execl(bin, "a", (char *)NULL);
                _exit(127);
            }
            res[i].pid = p;
            setpgid(p, p);
        }
        close(nul);

        /* reap with 5s hard deadline — poll each child by PID (not -1) */
        int remaining = 0; for (int i = 0; i < ncmds; i++) if (!res[i].skip) remaining++;
        while (remaining > 0) {
            struct timespec now; clock_gettime(CLOCK_MONOTONIC, &now);
            unsigned elapsed = (unsigned)((now.tv_sec - t0.tv_sec) * 1000000
                + (now.tv_nsec - t0.tv_nsec) / 1000);
            if (elapsed > 1000000) {
                for (int i = 0; i < ncmds; i++) if (!res[i].done) {
                    kill(-res[i].pid, SIGKILL); kill(res[i].pid, SIGKILL);
                    waitpid(res[i].pid, NULL, 0);
                    res[i].done = 1; res[i].us = (unsigned)elapsed; remaining--;
                }
                fprintf(stderr, "\033[31mx\033[0m a perf bench exceeded 1s — make slow commands faster\n");
                break;
            }
            int any = 0;
            for (int i = 0; i < ncmds; i++) {
                if (res[i].done) continue;
                int status; pid_t p = waitpid(res[i].pid, &status, WNOHANG);
                if (p <= 0) continue;
                clock_gettime(CLOCK_MONOTONIC, &now);
                res[i].us = (unsigned)((now.tv_sec - t0.tv_sec) * 1000000
                    + (now.tv_nsec - t0.tv_nsec) / 1000);
                res[i].done = 1; remaining--; any = 1;
                res[i].pass = !WIFSIGNALED(status);
            }
            if (!any) usleep(500);
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
        int passed = 0, tightened = 0, shown = 0;
        for (int i = 0; i < ncmds; i++) {
            if (res[i].skip) continue;
            shown++;
            int killed = !res[i].pass;
            unsigned t = res[i].us;
            unsigned proposed = (t * 13 + 9) / 10;
            if (proposed < 500) proposed = 500;
            unsigned old = res[i].old_lim; int tight = 0;
            res[i].new_lim = old;
            if (killed) { /* keep old */ }
            else if (!old) { res[i].new_lim = proposed; tight = 1; }
            else if (proposed < old) { res[i].new_lim = proposed; tight = 1; }
            if (!killed) passed++;
            if (tight) tightened++;
            const char *label = res[i].cmd[0] ? res[i].cmd : "(bare)";
            char ft[32], fo[32], fn[32];
            fmt_us(t, ft, 32); fmt_us(old, fo, 32); fmt_us(res[i].new_lim, fn, 32);
            const char *st = killed ? "\033[31mKILLED\033[0m" : tight ? "\033[32m↓ tight\033[0m" : "\033[32m\xe2\x9c\x93\033[0m";
            printf("%-12s %10s %10s %10s  %s\n", label, ft, old ? fo : "-", fn, st);
        }
        puts("─────────────────────────────────────────────────────────────");
        printf("%d/%d passed, %d tightened\n\n", passed, shown, tightened);
        if (tightened > 0) {
            /* merge: read existing limits, update benched ones, write back */
            unsigned lims[256]; const char *keys[256]; int nlims = 0;
            for (int i = 0; i < ncmds; i++) {
                const char *k = BENCH_CMDS[i][0] ? BENCH_CMDS[i] : "(bare)";
                keys[nlims] = k;
                lims[nlims] = res[i].skip ? perf_limit(data, k) : res[i].new_lim;
                nlims++;
            }
            char pd[P]; snprintf(pd, P, "%s/perf", SROOT); mkdirp(pd);
            FILE *f = fopen(pf, "w");
            if (f) {
                for (int i = 0; i < nlims; i++)
                    fprintf(f, "%s:%u\n", keys[i], lims[i]);
                fclose(f);
                printf("\033[32m\xe2\x9c\x93\033[0m Saved: %s\n", pf);
            }
        } else puts("No limits tightened — all commands at or above current limits.");
        if(passed<shown){char c[B];snprintf(c,B,"'%s/a' email '[a perf] %d/%d FAILED on %s' 'bench failure'",SDIR,shown-passed,shown,DEV);(void)!system(c);
            char fl[B]=""; int fll=0; for(int i=0;i<ncmds;i++) if(!res[i].skip&&!res[i].pass){char ft[32];fmt_us(res[i].us,ft,32);fll+=snprintf(fl+fll,(size_t)(B-fll),"%s(%s) ",res[i].cmd[0]?res[i].cmd:"(bare)",ft);}
            snprintf(c,B,"'%s/a' job a 'a perf bench FAILED: %s— run a perf bench yourself, read the killed commands source, fix them, run a perf bench to verify all pass.' --timeout 300",SDIR,fl);(void)!system(c);}
        free(data); free(res);
        return 0;
    }

    fprintf(stderr, "a perf: unknown subcommand '%s'. Try 'a perf help'\n", sub);
    return 1;
}
