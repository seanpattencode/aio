/* ── review ── */
static int cmd_review(int argc, char **argv) { fallback_py("review", argc, argv); }

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
static int cmd_run(int argc, char **argv) { fallback_py("run", argc, argv); }

/* ── agent ── */
static int cmd_agent(int argc, char **argv) {
    if (argc < 3) { puts("Usage: a agent [run <name>|g|c|l] <task>"); return 1; }
    /* a agent run <name> [args...] — uv run --script (auto-installs PEP 723 deps) */
    if (!strcmp(argv[2],"run") && argc > 3) {
        char py[P]; snprintf(py,P,"%s/personal/%s.py",SDIR,argv[3]);
        if (!fexists(py)) { fprintf(stderr,"x %s\n",py); return 1; }
        perf_disarm();
        char **na=malloc(((unsigned)argc+2)*sizeof(char*));
        /* try uv run --script first */
        char uv[P]; snprintf(uv,P,"%s/.local/bin/uv",HOME);
        na[0]="uv"; na[1]="run"; na[2]="--script"; na[3]=py;
        for(int i=4;i<argc;i++) na[i]=argv[i];
        na[argc]=NULL;
        if(access(uv,X_OK)==0){na[0]=uv;execv(uv,na);}
        execvp("uv",na);
        /* fallback: venv python, then system python3 */
        char vpy[P]; snprintf(vpy,P,"%s/venv/bin/python",AROOT);
        na[0]="python"; na[1]=py;
        for(int i=4;i<argc;i++) na[i-2]=argv[i];
        na[argc-2]=NULL;
        if(access(vpy,X_OK)==0) execv(vpy,na);
        na[0]="python3"; execvp("python3",na);
        perror("python3"); return 1;
    }
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
        char out[B]; tm_read(sn, out, B);
        if (strstr(out, "Type your message") || strstr(out, "claude") || strstr(out, "gemini")) break;
    }
    /* Send task with instructions */
    char prompt[B*2]; snprintf(prompt, sizeof(prompt),
        "%s\n\nCommands: \"a agent g <task>\" spawns gemini subagent, \"a agent l <task>\" spawns claude subagent. When YOUR task is fully complete, run: a done",
        taskstr);
    tm_send(sn, prompt); usleep(300000);
    tm_key(sn, "Enter");
    /* Wait for done file */
    char donef[P]; snprintf(donef, P, "%s/.done", DDIR); unlink(donef);
    puts("Waiting for completion...");
    time_t start = time(NULL);
    while (!fexists(donef) && time(NULL) - start < 300) sleep(1);
    /* Capture output */
    char out[B*4]; tm_read(sn, out, sizeof(out));
    printf("--- Output ---\n%s\n--- End ---\n", out);
    return 0;
}

/* ── multi/all ── */
static int cmd_all(int argc, char **argv) { fallback_py("multi", argc, argv); }
