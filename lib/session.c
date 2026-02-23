/* ═══ FALLBACK ═══ */
__attribute__((noreturn))
static void fallback_py(const char *mod, int argc, char **argv) {
    if (getenv("A_BENCH")) _exit(0);
    perf_disarm(); /* python takes over — no timeout */
    char path[P]; snprintf(path, P, "%s/lib/%s.py", SDIR, mod);
    /* try uv run --script (auto-installs deps from PEP 723 metadata) */
    char uv[P]; snprintf(uv, P, "%s/.local/bin/uv", HOME);
    char **ua = malloc(((unsigned)argc + 5) * sizeof(char *));
    ua[0] = "uv"; ua[1] = "run"; ua[2] = "--script"; ua[3] = path;
    for (int i = 1; i < argc; i++) ua[i + 3] = argv[i];
    ua[argc + 3] = NULL;
    if (access(uv, X_OK) == 0) { ua[0] = uv; execv(uv, ua); }
    execvp("uv", ua);
    /* fallback: venv python, then system python3 */
    char vpy[P]; snprintf(vpy, P, "%s/venv/bin/python", AROOT);
    char **na = ua; na[0] = "python"; na[1] = path;
    for (int i = 1; i < argc; i++) na[i + 1] = argv[i];
    na[argc + 1] = NULL;
    if (access(vpy, X_OK) == 0) execv(vpy, na);
    na[0] = "python3"; execvp("python3", na);
    perror("a: python3"); _exit(127);
}

/* ═══ SESSION CREATE ═══ */
static void create_sess(const char *sn, const char *wd, const char *cmd) {
    int ai = cmd && (strstr(cmd,"claude") || strstr(cmd,"codex") || strstr(cmd,"gemini") || strstr(cmd,"aider"));
    char wcmd[B*2];
    if (ai) snprintf(wcmd, sizeof(wcmd),
        "unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT; while :; do %s; e=$?; [ $e -eq 0 ] && break; echo -e \"\\n! Crashed (exit $e). [R]estart / [Q]uit: \"; read -n1 k; [[ $k =~ [Rr] ]] || break; done", cmd);
    else snprintf(wcmd, sizeof(wcmd), "%s", cmd ? cmd : "");
    tm_ensure_conf();
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

static void send_prefix_bg(const char *sn, const char *agent, const char *wd, const char *extra) {
    const char *cp = strstr(agent, "claude") ? cfget("claude_prefix") : "";
    char pre[B*4]; int n = snprintf(pre, sizeof(pre), "%s%s", dprompt(), cp);
    char af[P]; snprintf(af, P, "%s/AGENTS.md", wd);
    char *amd = readf(af, NULL);
    if (amd) { n += snprintf(pre+n, sizeof(pre)-(unsigned)n, "%s ", amd); free(amd); }
    if (extra) snprintf(pre+n, sizeof(pre)-(unsigned)n, "%s", extra);
    if (!pre[0]) return;
    if (fork() == 0) {
        setsid();
        for (int i = 0; i < 300; i++) {
            usleep(50000);
            char buf[B] = "";
            tm_read(sn, buf, B);
            char *lo = buf;
            for (char *p = lo; *p; p++) *p = (*p >= 'A' && *p <= 'Z') ? *p + 32 : *p;
            if (strstr(lo,"context") || strstr(lo,"claude") || strstr(lo,"opus") || strstr(lo,"shortcut") || strstr(lo,"codex")) break;
        }
        tm_send(sn, pre);
        if (extra) { sleep(1); tm_key(sn, "Enter"); }
        _exit(0);
    }
}
