/* ── session (c, l, g, co, cp, etc.) ── */
static int cmd_sess(int argc, char **argv) {
    init_db(); load_cfg(); load_proj(); load_apps(); load_sess();
    const char *key = argv[1];
    sess_t *s = find_sess(key);
    if (!s) return -1;  /* not a session key */
    char wd[P]; if(!getcwd(wd,P)) snprintf(wd,P,"%s",HOME);
    const char *wda = argc > 2 ? argv[2] : NULL;
    /* If wda is a project number */
    if (wda && wda[0] >= '0' && wda[0] <= '9') {
        int idx = atoi(wda);
        if (idx >= 0 && idx < NPJ) snprintf(wd, P, "%s", PJ[idx].path);
        else if (idx >= NPJ && idx < NPJ + NAP) {
            printf("> Running: %s\n", AP[idx-NPJ].name);
            const char *sh = getenv("SHELL"); if (!sh) sh = "/bin/bash";
            execlp(sh, sh, "-c", AP[idx-NPJ].cmd, (char*)NULL);
        }
    } else if (wda && dexists(wda)) {
        if (wda[0] == '~') snprintf(wd, P, "%s%s", HOME, wda+1);
        else snprintf(wd, P, "%s", wda);
    }
    /* Build prompt from remaining args */
    char prompt[B]=""; int is_prompt=0,pl=0;
    int start = wda ? 3 : 2;
    if (wda && !(wda[0]>='0'&&wda[0]<='9') && !dexists(wda)) { start = 2; is_prompt = 1; }
    for (int i = start; i < argc; i++) {
        if (!strcmp(argv[i],"-w")||!strcmp(argv[i],"--new-window")||!strcmp(argv[i],"-t")||!strcmp(argv[i],"--with-terminal")) continue;
        pl+=snprintf(prompt+pl,(size_t)(B-pl),"%s%s",pl?" ":"",argv[i]);
        is_prompt = 1;
    }
    /* Inside tmux + single char key = split pane mode */
    if (getenv("TMUX") && strlen(key) == 1 && key[0] != 'a') {
        char c[B]; snprintf(c, B, "tmux split-window -hfP -F '#{pane_id}' -c '%s' 'unset CLAUDECODE CLAUDE_CODE_ENTRYPOINT; %s'", wd, s->cmd);
        char pid[64]; pcmd(c, pid, 64); pid[strcspn(pid,"\n")] = 0;
        if (pid[0]) {
            snprintf(c, B, "tmux split-window -v -t '%s' -c '%s' 'sh -c \"ls;exec $SHELL\"'", pid, wd); (void)!system(c);
            snprintf(c, B, "tmux select-pane -t '%s'", pid); (void)!system(c);
            send_prefix_bg(pid, s->name, wd, is_prompt ? prompt : NULL);
        }
        return 0;
    }
    /* Find or create named session */
    char sn[256]; snprintf(sn, 256, "%s-%s", s->name, bname(wd));
    /* Check for existing session with same base name */
    if (tm_has(sn)) {
        if (is_prompt && prompt[0]) {
            /* Send prompt to existing session */
            tm_send(sn, prompt); usleep(100000);
            tm_key(sn, "Enter");
            puts("Prompt queued (existing session)");
        }
        tm_go(sn);
        return 0;
    }
    /* Create new session */
    create_sess(sn, wd, s->cmd);
    send_prefix_bg(sn, s->name, wd, is_prompt ? prompt : NULL);
    tm_go(sn);
    return 0;
}

/* ── worktree ++ ── */
static int cmd_wt_plus(int argc, char **argv) { fallback_py("wt_plus", argc, argv); }

/* ── worktree w* ── */
static int cmd_wt(int argc, char **argv) { fallback_py("wt", argc, argv); }

/* ── dir_file ── */
static int cmd_dir_file(int argc, char **argv) { (void)argc;
    const char *arg = argv[1];
    char expanded[P];
    if (arg[0] == '/' && !strncmp(arg, "/projects/", 10)) {
        snprintf(expanded, P, "%s%s", HOME, arg);
        if (dexists(expanded)) { printf("%s\n", expanded); execlp("ls", "ls", expanded, (char*)NULL); return 0; }
    }
    if (arg[0] == '~') snprintf(expanded, P, "%s%s", HOME, arg+1);
    else snprintf(expanded, P, "%s", arg);
    if (dexists(expanded)) { printf("%s\n", expanded); execlp("ls", "ls", expanded, (char*)NULL); }
    else if (fexists(expanded)) {
        const char *ext = strrchr(expanded, '.');
        if (ext && !strcmp(ext, ".py")) {
            char py[P]="python3"; const char *ve=getenv("VIRTUAL_ENV");
            if(ve) snprintf(py,P,"%s/bin/python",ve);
            else if(!access(".venv/bin/python",X_OK)) snprintf(py,P,".venv/bin/python");
            execvp(py, (char*[]){ py, expanded, NULL });
        }
        else { const char *ed = getenv("EDITOR"); if (!ed) ed = "e"; execlp(ed, ed, expanded, (char*)NULL); }
    }
    return 0;
}

/* ── interactive picker ── */
static int cmd_i(int argc, char **argv) { (void)argc; (void)argv;
    perf_disarm(); init_db();
    char cache[P]; snprintf(cache, P, "%s/i_cache.txt", DDIR);
    if (!fexists(cache)) gen_icache();
    size_t len; char *raw = readf(cache, &len);
    if (!raw) { puts("No cache"); return 1; }
    /* Parse lines */
    char *lines[512]; int n = 0;
    for (char *p = raw, *end = raw + len; p < end && n < 512;) {
        char *nl = memchr(p, '\n', (size_t)(end - p));
        if (!nl) nl = end;
        if (nl > p && p[0] != '<' && p[0] != '=' && p[0] != '>' && p[0] != '#') { *nl = 0; lines[n++] = p; }
        p = nl + 1;
    }
    if (!n) { puts("Empty cache"); free(raw); return 1; }
    if (!isatty(STDIN_FILENO)) { for (int i=0;i<n;i++) puts(lines[i]); free(raw); return 0; }
    /* Terminal size */
    struct winsize ws; ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws);
    int maxshow = ws.ws_row > 6 ? ws.ws_row - 3 : 10;
    /* Raw mode */
    struct termios old, raw_t;
    tcgetattr(STDIN_FILENO, &old); raw_t = old;
    raw_t.c_lflag &= ~(tcflag_t)(ICANON | ECHO);
    raw_t.c_cc[VMIN] = 1; raw_t.c_cc[VTIME] = 0;
    tcsetattr(STDIN_FILENO, TCSANOW, &raw_t);
    char buf[256] = ""; int blen = 0, sel = 0; char prefix[256] = "";
    printf("Filter (↑↓/Tab=cycle, Enter=run, Esc=quit)\n");
    while (1) {
        /* Search */
        char *matches[512]; int nm = 0; int plen = (int)strlen(prefix);
        for (int i=0;i<n&&nm<512;i++) {
            if (plen && strncmp(lines[i], prefix, (size_t)plen)) continue;
            if(blen){char*s=lines[i]+plen,b2[256],*w;snprintf(b2,256,"%s",buf);int ok=1;
                for(w=strtok(b2," ");w&&ok;w=strtok(0," "))if(!strcasestr(s,w))ok=0;if(!ok)continue;}
            matches[nm++] = lines[i];
        }
        if (sel >= nm) sel = nm ? nm-1 : 0;
        /* Scroll window around sel */
        int top=sel>=maxshow?sel-maxshow+1:0, show=nm-top<maxshow?nm-top:maxshow;
        /* Render */
        printf("\r\033[K%s> %s\n", prefix, buf);
        for (int i=0;i<show;i++){int j=top+i,W=ws.ws_col;char*t=strchr(matches[j],'\t');int ml=t?(int)(t-matches[j]):(int)strlen(matches[j]);
            if(ml>W-5)ml=W-5;printf("\033[K%s a %.*s",j==sel?" >":"  ",ml,matches[j]);
            {char*px=getenv("PREFIX");if(t&&!(px&&strstr(px,"termux"))&&ml+5+(int)strlen(t+1)<W)printf("\033[%dG\033[90m%s\033[0m",W-(int)strlen(t+1),t+1);}putchar('\n');}
        printf("\033[%dA\033[%dC\033[?25h", show+1, plen+blen+3);
        fflush(stdout);
        /* Read key */
        char ch; if (read(STDIN_FILENO, &ch, 1) != 1) break;
        if (ch == '\x1b') { /* Escape sequence or Esc */
            char seq[2]; if (read(STDIN_FILENO, &seq[0], 1) != 1) break;
            if (seq[0] == '[') {
                if (read(STDIN_FILENO, &seq[1], 1) != 1) break;
                if (seq[1] == 'A') { if(sel>0)sel--; } /* Up */
                else if (seq[1] == 'B') { if(sel<nm-1)sel++; } /* Down */
            } else if(prefix[0]){prefix[0]=0;buf[0]=0;blen=0;sel=0;} else break;
        } else if (ch == '\t') { if(sel<nm-1)sel++; }
        else if (ch == '\x7f' || ch == '\b') { if (blen) buf[--blen]=0; sel=0; }
        else if (ch == '\r' || ch == '\n') {
            if (!nm) continue;
            char *m = matches[sel]; char cmd[256];
            char *tab=strchr(m,'\t'),*colon=strchr(m,':');
            if(colon&&(!tab||colon<tab)){int cl=(int)(colon-m);snprintf(cmd,256,"%.*s",cl,m);while(cmd[0]==' ')memmove(cmd,cmd+1,strlen(cmd));}
            else{int cl=tab?(int)(tab-m):(int)strlen(m);snprintf(cmd,256,"%.*s",cl,m);}
            /* Trim */
            char *e = cmd+strlen(cmd)-1; while(e>cmd&&*e==' ')*e--=0;
            /* Drill into submenu if sub-items exist */
            int has_sub=0,cl=(int)strlen(cmd);
            for(int i=0;i<n;i++) if(!strncmp(lines[i],cmd,(size_t)cl)&&lines[i][cl]==' '){has_sub=1;break;}
            if(has_sub){snprintf(prefix,256,"%s ",cmd);buf[0]=0;blen=0;sel=0;printf("\033[J");continue;}
            tcsetattr(STDIN_FILENO, TCSANOW, &old);
            printf("\n\n\033[KRunning: a %s\n", cmd);
            /* Build argv for exec */
            char *args[32]; int ac=0; args[ac++]="a";
            char *p=cmd; while(*p&&ac<31) { while(*p==' ')p++; if(!*p)break; args[ac++]=p; while(*p&&*p!=' ')p++; if(*p)*p++=0; }
            args[ac]=NULL;
            free(raw); execvp("a", args);
            return 0;
        } else if (ch == '\x03' || ch == '\x04') break;
        else if (ch == 'q' && !blen) break;
        else if ((ch>='a'&&ch<='z')||(ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9')||ch=='-'||ch=='_'||ch==' ') { if(blen<254){buf[blen++]=ch;buf[blen]=0;sel=0;} }
        printf("\033[J");
    }
    tcsetattr(STDIN_FILENO, TCSANOW, &old);
    printf("\033[2J\033[H"); free(raw);
    return 0;
}
