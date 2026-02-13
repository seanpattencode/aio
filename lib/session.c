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
