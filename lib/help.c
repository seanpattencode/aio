/* ═══ HELP TEXT ═══ */
static const char *HELP_SHORT =
    "a c|co|g|ai     Start claude/codex/gemini/aider\n"
    "a <#>           Open project by number\n"
    "a prompt        Manage default prompt\n"
    "a help          All commands";

static const char *HELP_FULL =
    "a - AI agent session manager\n\n"
    "AGENTS          c=claude  co=codex  g=gemini  ai=aider\n"
    "  a <key>             Start agent in current dir\n"
    "  a <key> <#>         Start agent in project #\n"
    "  a <key>++           Start agent in new worktree\n\n"
    "PROJECTS\n"
    "  a <#>               cd to project #\n"
    "  a add               Add current dir as project\n"
    "  a remove <#>        Remove project\n"
    "  a move <#> <#>      Reorder project\n"
    "  a scan              Add your repos fast\n\n"
    "GIT\n"
    "  a push [msg]        Commit and push\n"
    "  a pull              Sync with remote\n"
    "  a diff              Show changes\n"
    "  a revert            Select commit to revert to\n\n"
    "REMOTE\n"
    "  a ssh               List hosts\n"
    "  a ssh <#>           Connect to host\n"
    "  a run <#> \"task\"    Run task on remote\n\n"
    "OTHER\n"
    "  a jobs              Active sessions\n"
    "  a ls                List tmux sessions\n"
    "  a attach            Reconnect to session\n"
    "  a kill              Kill all sessions\n"
    "  a task              Tasks (priority, review, subfolders)\n"
    "  a n \"text\"          Quick note\n"
    "  a log               View agent logs\n"
    "  a config            View/set settings\n"
    "  a update            Update a\n"
    "  a mono              Generate monolith for reading\n\n"
    "EXPERIMENTAL\n"
    "  a agent \"task\"      Spawn autonomous subagent\n"
    "  a hub               Scheduled jobs (systemd)\n"
    "  a all               Multi-agent parallel runs\n"
    "  a tree              Create git worktree\n"
    "  a gdrive            Cloud sync (Google Drive)\n"
    "  a perf              Show per-command timeout limits\n"
    "  a perf bench        Benchmark + auto-tighten limits";

/* ═══ LIST_ALL + CACHE ═══ */
static void list_all(int cache, int quiet) {
    load_proj(); load_apps();
    char pfile[P]; snprintf(pfile, P, "%s/projects.txt", DDIR);
    /* Write projects.txt for shell function */
    FILE *pf = fopen(pfile, "w");
    if (pf) { for (int i = 0; i < NPJ; i++) fprintf(pf, "%s\n", PJ[i].path); fclose(pf); }
    if (quiet && !cache) return;
    char out[B*4] = ""; int o = 0;
    if (NPJ) {
        o += sprintf(out + o, "PROJECTS:\n");
        for (int i = 0; i < NPJ; i++) {
            char mk = dexists(PJ[i].path) ? '+' : (PJ[i].repo[0] ? '~' : 'x');
            o += sprintf(out + o, "  %d. %c %s\n", i, mk, PJ[i].path);
        }
    }
    if (NAP) {
        o += sprintf(out + o, "COMMANDS:\n");
        for (int i = 0; i < NAP; i++) {
            char dc[64]; snprintf(dc, 64, "%s", AP[i].cmd);
            o += sprintf(out + o, "  %d. %s -> %s\n", NPJ + i, AP[i].name, dc);
        }
    }
    if (!quiet && out[0]) printf("%s", out);
    if (cache) {
        char cf[P]; snprintf(cf, P, "%s/help_cache.txt", DDIR);
        FILE *f = fopen(cf, "w");
        if (f) { fprintf(f, "%s\n%s", HELP_SHORT, out); fclose(f); }
    }
}

static void gen_icache(void) {
    load_proj(); load_apps();
    char ic[P]; snprintf(ic, P, "%s/i_cache.txt", DDIR);
    FILE *f = fopen(ic, "w"); if (!f) return;
    for (int i=0;i<NPJ;i++) fprintf(f, "%d: %s (%s)\n", i, bname(PJ[i].path), PJ[i].path);
    for (int i=0;i<NAP;i++) fprintf(f, "%d: %s\n", NPJ+i, AP[i].name);
    static const char *cmds[] = {"help","update","jobs","kill","attach","cleanup","config","ls","diff","send","watch",
        "push","pull","revert","set","install","uninstall","deps","prompt","gdrive","add","remove","move",
        "dash","all","backup","scan","copy","log","done","agent","tree","dir","web","ssh","run","hub",
        "task","ui","review","note","setup"};
    for (int i=0;i<(int)(sizeof(cmds)/sizeof(*cmds));i++) fprintf(f, "%s\n", cmds[i]);
    char sd[P]; snprintf(sd, P, "%s/ssh", SROOT);
    char sp[32][P]; int sn = listdir(sd, sp, 32);
    for (int i=0,hi=0;i<sn;i++) {
        kvs_t kv = kvfile(sp[i]);
        const char *nm = kvget(&kv,"Name"); if (!nm) continue;
        const char *host = kvget(&kv,"Host"); fprintf(f, "ssh %d: %s (%s)\n", hi++, nm, host?host:"");
    }
    fclose(f);
}

static int cmd_help(int argc, char **argv) { (void)argc; (void)argv;
    char p[P]; snprintf(p, P, "%s/help_cache.txt", DDIR);
    if (catf(p) < 0) { init_db(); load_cfg(); printf("%s\n", HELP_SHORT); list_all(1, 0); }
    return 0;
}

static int cmd_help_full(int argc, char **argv) { (void)argc; (void)argv;
    init_db(); load_cfg(); printf("%s\n", HELP_FULL); list_all(1, 0); return 0;
}

static int cmd_hi(int argc, char **argv) { (void)argc;(void)argv; for (int i = 1; i <= 10; i++) printf("%d\n", i); puts("hi"); return 0; }

static int cmd_done(int argc, char **argv) { (void)argc;(void)argv;
    char p[P]; snprintf(p, P, "%s/.done", DDIR);
    int fd = open(p, O_WRONLY|O_CREAT|O_TRUNC, 0644); if (fd >= 0) close(fd);
    puts("\xe2\x9c\x93 done"); return 0;
}

static int cmd_dir(int argc, char **argv) { (void)argc;(void)argv;
    char cwd[P]; if (getcwd(cwd, P)) puts(cwd);
    execlp("ls", "ls", (char*)NULL); return 1;
}

static int cmd_backup(int argc, char **argv) { (void)argc;(void)argv; puts("backup: sync system removed, rewrite pending"); return 0; }
static int cmd_rebuild(int argc, char **argv) { (void)argc;(void)argv; puts("rebuild: sync system removed, rewrite pending"); return 0; }

static int cmd_x(int argc, char **argv) { (void)argc;(void)argv;
    (void)!system("tmux kill-server 2>/dev/null");
    puts("\xe2\x9c\x93 All sessions killed"); return 0;
}

static int cmd_web(int argc, char **argv) {
    char url[B] = "https://google.com";
    if (argc > 2) {
        int l=snprintf(url,B,"https://google.com/search?q=");
        for(int i=2;i<argc&&l<B-1;i++) l+=snprintf(url+l,(size_t)(B-l),"%s%s",i>2?"+":"",argv[i]);
    }
    char c[B]; snprintf(c, B, "xdg-open '%s' 2>/dev/null &", url); (void)!system(c);
    return 0;
}

static int cmd_repo(int argc, char **argv) {
    if (argc < 3) { puts("Usage: a repo <name>"); return 1; }
    char c[B]; snprintf(c, B, "mkdir -p '%s' && cd '%s' && git init -q && gh repo create '%s' --public --source=.", argv[2], argv[2], argv[2]);
    (void)!system(c); return 0;
}
