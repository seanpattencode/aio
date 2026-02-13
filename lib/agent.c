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
    char taskstr[B]=""; int si=(s&&!strcmp(wda,s->key))?3:2;
    for(int i=si,l=0;i<argc;i++) l+=snprintf(taskstr+l,(size_t)(B-l),"%s%s",i>si?" ":"",argv[i]);
    char wd[P]; if(!getcwd(wd,P)) snprintf(wd,P,"%s",HOME);
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
