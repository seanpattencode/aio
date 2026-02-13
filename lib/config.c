/* ── set ── */
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

/* ── install ── */
static int cmd_install(void) {
    char s[P]; snprintf(s, P, "%s/a.c", SDIR);
    execlp("bash", "bash", s, "install", (char*)NULL);
    return 1;
}

/* ── uninstall ── */
static int cmd_uninstall(void) {
    printf("Uninstall aio? (y/n): "); char buf[16];
    if (!fgets(buf, 16, stdin) || (buf[0] != 'y' && buf[0] != 'Y')) return 0;
    char p[P];
    snprintf(p, P, "%s/.local/bin/aio", HOME); unlink(p);
    snprintf(p, P, "%s/.local/bin/aioUI.py", HOME); unlink(p);
    puts("\xe2\x9c\x93 aio uninstalled"); _exit(0);
}

/* ── deps ── */
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

/* ── e ── */
static int cmd_e(int argc, char **argv) {
    if (argc > 2 && !strcmp(argv[2], "install")) {
        (void)!system("curl -sL https://raw.githubusercontent.com/seanpattencode/editor/main/e.c|clang -xc -Wno-everything -o ~/.local/bin/e -");
        return 0;
    }
    if (getenv("TMUX")) execlp("e", "e", ".", (char*)NULL);
    else {
        init_db(); load_cfg();
        char wd[P]; if(!getcwd(wd,P)) snprintf(wd,P,"%s",HOME);
        create_sess("edit", wd, "e .");
        execlp("tmux", "tmux", "attach", "-t", "edit", (char*)NULL);
    }
    return 0;
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
        char val[B]=""; for(int i=3,l=0;i<argc;i++) l+=snprintf(val+l,(size_t)(B-l),"%s%s",i>3?" ":"",argv[i]);
        if (!strcmp(val,"off")||!strcmp(val,"none")||!strcmp(val,"\"\"")||!strcmp(val,"''")) val[0]=0;
        cfset(key, val);
        load_cfg(); list_all(1, 1);
        printf("\xe2\x9c\x93 %s=%s\n", key, val[0] ? val : "(cleared)");
    } else printf("%s: %s\n", key, cfget(key));
    return 0;
}

/* ── prompt ── */
static int cmd_prompt(int argc, char **argv) {
    init_db(); load_cfg();
    char val[B] = "";
    if(argc>2)for(int i=2,l=0;i<argc;i++) l+=snprintf(val+l,(size_t)(B-l),"%s%s",i>2?" ":"",argv[i]);
    else {
        printf("Current: %s\n", cfget("default_prompt")[0] ? cfget("default_prompt") : "(none)");
        printf("New (empty to clear): "); if (!fgets(val, B, stdin)) return 0;
        val[strcspn(val,"\n")] = 0;
    }
    if (!strcmp(val,"off")||!strcmp(val,"none")) val[0]=0;
    cfset("default_prompt", val);
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
        for(int i=1,l=0;i<na;i++) l+=snprintf(cmd+l,(size_t)(B-l),"%s%s",i>1?" ":"",args[i]);
        char d[P]; snprintf(d, P, "%s/workspace/cmds", SROOT); mkdirp(d);
        char f[P]; snprintf(f, P, "%s/%s.txt", d, name);
        if (fexists(f)) { printf("x Exists: %s\n", name); return 1; }
        char cwd[P]; if(!getcwd(cwd,P)) snprintf(cwd,P,".");
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
    fallback_py("move", argc, argv);
}

/* ── scan ── */
static int cmd_scan(int argc, char **argv) { fallback_py("scan", argc, argv); }
