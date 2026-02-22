/* ── ls ── */
static int cmd_ls(int argc, char **argv) {
    if (argc > 2 && argv[2][0] >= '0' && argv[2][0] <= '9') {
        /* Attach by number */
        char out[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null", out, B);
        char *lines[64]; int n = 0; char *p = out;
        while (*p && n < 64) { lines[n++] = p; char *e = strchr(p,'\n'); if (e) { *e=0; p=e+1; } else break; }
        int idx = atoi(argv[2]);
        if (idx >= 0 && idx < n) tm_go(lines[idx]);
        return 0;
    }
    char out[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null", out, B);
    if (!out[0]) { puts("No sessions"); return 0; }
    char *p = out; int i = 0;
    while (*p) {
        char *e = strchr(p, '\n'); if (e) *e = 0;
        if (*p) {
            char c[B], path[512] = "";
            snprintf(c, B, "tmux display-message -p -t '%s' '#{pane_current_path}' 2>/dev/null", p);
            pcmd(c, path, 512); path[strcspn(path,"\n")] = 0;
            printf("  %d  %s: %s\n", i++, p, path);
        }
        if (e) p = e + 1; else break;
    }
    puts("\nSelect:\n  a ls 0"); return 0;
}

/* ── kill ── */
static int cmd_kill(int argc, char **argv) {
    const char *sel = argc > 2 ? argv[2] : NULL;
    if ((sel && !strcmp(sel, "all")) || (argc > 1 && !strcmp(argv[1], "killall"))) {
        (void)!system("pkill -9 -f tmux 2>/dev/null"); (void)!system("clear");
        puts("\xe2\x9c\x93"); return 0;
    }
    char out[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null", out, B);
    char *lines[64]; int n = 0; char *p = out;
    while (*p && n < 64) { lines[n++] = p; char *e = strchr(p,'\n'); if (e) { *e=0; p=e+1; } else break; }
    if (!n) { puts("No sessions"); return 0; }
    if (sel && sel[0] >= '0' && sel[0] <= '9') {
        int idx = atoi(sel);
        if (idx >= 0 && idx < n) {
            char c[B]; snprintf(c, B, "tmux kill-session -t '%s'", lines[idx]); (void)!system(c);
            printf("\xe2\x9c\x93 %s\n", lines[idx]); return 0;
        }
    }
    for (int i = 0; i < n; i++) printf("  %d  %s\n", i, lines[i]);
    puts("\nSelect:\n  a kill 0\n  a kill all"); return 0;
}

/* ── copy ── */
static int cmd_copy(int argc, char **argv) { (void)argc;(void)argv;
    if (!getenv("TMUX")) { puts("x Not in tmux"); return 1; }
    (void)!system("tmux capture-pane -pJ -S -99 > /tmp/ac_copy.tmp");
    char *d = readf("/tmp/ac_copy.tmp", NULL);
    if (!d) return 1;
    char *lines[1024]; int nl = 0; char *p = d;
    while (*p && nl < 1024) { lines[nl++] = p; char *e = strchr(p,'\n'); if (e) { *e=0; p=e+1; } else break; }
    int last_prompt = -1;
    for (int i = nl - 1; i >= 0; i--) {
        if (!(strstr(lines[i],"\xe2\x9d\xaf") || (strstr(lines[i],"$") && strstr(lines[i],"@")))) continue;
        if (strstr(lines[i], "copy")) { last_prompt = i; continue; }
        if (last_prompt < 0) continue;
        char out[B]=""; int ol=0;
        for(int j=i+1;j<last_prompt&&j<nl;j++) ol+=snprintf(out+ol,(size_t)(B-ol),"%s%s",ol?"\n":"",lines[j]);
        FILE *fp = popen("wl-copy 2>/dev/null || xclip -selection clipboard -i 2>/dev/null", "w");
        if (fp) { fputs(out, fp); pclose(fp); }
        char s[54]; snprintf(s, 54, "%s", out); for (char *c=s;*c;c++) if(*c=='\n')*c=' ';
        printf("\xe2\x9c\x93 %s\n", s);
        free(d); return 0;
    }
    free(d); puts("x No output found"); return 0;
}

/* ── dash ── */
static int cmd_dash(int argc, char **argv) { (void)argc;(void)argv;
    char wd[P]; if(!getcwd(wd,P)) snprintf(wd,P,"%s",HOME);
    if (!tm_has("dash")) {
        char c[B];
        snprintf(c, B, "tmux new-session -d -s dash -c '%s'", wd); (void)!system(c);
        snprintf(c, B, "tmux split-window -h -t dash -c '%s' 'sh -c \"a jobs; exec $SHELL\"'", wd); (void)!system(c);
    }
    tm_go("dash"); return 0;
}

/* ── attach ── */
static int cmd_attach(int argc, char **argv) { fallback_py("attach", argc, argv); }

/* ── watch ── */
static int cmd_watch(int argc, char **argv) {
    if (argc < 3) { puts("Usage: a watch <session> [duration]"); return 1; }
    const char *sn = argv[2]; int dur = argc > 3 ? atoi(argv[3]) : 0;
    printf("Watching '%s'%s\n", sn, dur ? "" : " (once)");
    time_t start = time(NULL);
    char last[B] = "";
    while (1) {
        if (dur && time(NULL) - start > dur) break;
        char out[B];
        if (tm_read(sn, out, B) != 0) { printf("x Session %s not found\n", sn); return 1; }
        if (strcmp(out, last)) {
            if (strstr(out, "Are you sure?") || strstr(out, "Continue?") || strstr(out, "[y/N]") || strstr(out, "[Y/n]")) {
                tm_key(sn, "y"); tm_key(sn, "Enter");
                puts("\xe2\x9c\x93 Auto-responded");
            }
            snprintf(last, B, "%s", out);
        }
        usleep(100000);
        if (!dur) break;
    }
    return 0;
}

/* ── send ── */
static int cmd_send(int argc, char **argv) {
    if (argc < 4) { puts("Usage: a send <session> <prompt> [--wait] [--no-enter]"); return 1; }
    const char *sn = argv[2];
    if (!tm_has(sn)) { printf("x Session %s not found\n", sn); return 1; }
    char prompt[B]=""; int pl=0,wait=0,enter=1;
    for (int i = 3; i < argc; i++) {
        if (!strcmp(argv[i],"--wait")) wait = 1;
        else if (!strcmp(argv[i],"--no-enter")) enter = 0;
        else { pl+=snprintf(prompt+pl,(size_t)(B-pl),"%s%s",pl?" ":"",argv[i]); }
    }
    tm_send(sn, prompt);
    if (enter) { usleep(100000); tm_key(sn, "Enter"); }
    printf("\xe2\x9c\x93 %s '%s'\n", enter?"Sent to":"Inserted into", sn);
    if (wait) {
        printf("Waiting..."); fflush(stdout);
        time_t last_active = time(NULL);
        while (1) {
            char c[B]; snprintf(c, B, "tmux display-message -p -t '%s' '#{window_activity}' 2>/dev/null", sn);
            char out[64]; pcmd(c, out, 64);
            int act = atoi(out);
            if (time(NULL) - act < 2) { last_active = time(NULL); printf("."); fflush(stdout); }
            else if (time(NULL) - last_active > 3) { puts("\n+ Done"); break; }
            usleep(500000);
        }
    }
    return 0;
}

/* ── jobs ── list/attach/remove agent worktrees */
static int cmd_jobs(int argc, char **argv) {
    init_db(); load_cfg();
    char wd[P]; {const char*w=cfget("worktrees_dir");snprintf(wd,P,"%s",w[0]?w:"");if(!w[0])snprintf(wd,P,"%s/worktrees",AROOT);}
    const char *sel=NULL,*rm=NULL; int rf=0;
    for(int i=2;i<argc;i++){if(!strcmp(argv[i],"-r")||!strcmp(argv[i],"--running"))rf=1;
        else if(!strcmp(argv[i],"rm")&&i+1<argc)rm=argv[++i];else sel=argv[i];}
    if(sel&&!strcmp(sel,"watch")){perf_disarm();execlp("watch","watch","-n2","-c","a","jobs","-r",(char*)0);return 0;}
    struct{char p[P],s[8][128],n[64],r[128];int ns,act;time_t ct;int wt;}J[64];int nj=0;
    /* Tmux sessions -> paths */
    char to[B]; pcmd("tmux list-sessions -F '#{session_name}' 2>/dev/null",to,B);
    for(char*tp=to;*tp;){char*e=strchr(tp,'\n');if(e)*e=0;if(*tp){
        char c[B],pp[P];snprintf(c,B,"tmux display-message -p -t '%s' '#{pane_current_path}' 2>/dev/null",tp);
        pcmd(c,pp,P);pp[strcspn(pp,"\n")]=0;
        int f=-1;for(int i=0;i<nj;i++)if(!strcmp(J[i].p,pp)){f=i;break;}
        if(f<0&&nj<64){f=nj;snprintf(J[f].p,P,"%s",pp);J[f].ns=0;nj++;}
        if(f>=0&&J[f].ns<8)snprintf(J[f].s[J[f].ns++],128,"%s",tp);
    }if(e)tp=e+1;else break;}
    if(dexists(wd)){DIR*d=opendir(wd);struct dirent*e;if(d){while((e=readdir(d))){if(e->d_name[0]=='.')continue;
        char fp[P];snprintf(fp,P,"%s/%s",wd,e->d_name);struct stat st;if(stat(fp,&st)||!S_ISDIR(st.st_mode))continue;
        int found=0;for(int i=0;i<nj;i++)if(!strcmp(J[i].p,fp)){found=1;break;}
        if(!found&&nj<64){snprintf(J[nj].p,P,"%s",fp);J[nj].ns=0;nj++;}}closedir(d);}}
    if(!nj){puts("No jobs");return 0;}
    /* Enrich + filter */
    int cnt=0;
    for(int i=0;i<nj;i++){
        if(!dexists(J[i].p)){for(int s=0;s<J[i].ns;s++){char c[B];snprintf(c,B,"tmux kill-session -t '%s' 2>/dev/null",J[i].s[s]);(void)!system(c);}continue;}
        J[i].act=0;for(int s=0;s<J[i].ns&&!J[i].act;s++){char c[B],o[64];
            snprintf(c,B,"tmux display-message -p -t '%s' '#{window_activity}' 2>/dev/null",J[i].s[s]);
            pcmd(c,o,64);if(atoi(o)&&(int)time(NULL)-atoi(o)<10)J[i].act=1;}
        if(rf&&!J[i].act)continue;
        const char*bn=bname(J[i].p);snprintf(J[i].n,64,"%s",bn);
        {struct stat st;J[i].ct=(!stat(J[i].p,&st))?st.st_ctime:0;}
        char c[B],go[512];snprintf(c,B,"git -C '%s' config --get remote.origin.url 2>/dev/null",J[i].p);
        pcmd(c,go,512);go[strcspn(go,"\n")]=0;
        if(go[0]){char*sl=strrchr(go,'/');snprintf(J[i].r,128,"%s",sl?sl+1:go);char*dt=strstr(J[i].r,".git");if(dt&&!dt[4])*dt=0;}
        else{snprintf(J[i].r,128,"%s",bn);for(char*q=J[i].r;*q;q++)if(*q=='-'&&q[1]>='2'&&q[1]<='2'){*q=0;break;}}
        J[i].wt=!strncmp(J[i].p,wd,strlen(wd));if(i!=cnt)J[cnt]=J[i];cnt++;
    } nj=cnt;
    for(int i=0;i<nj-1;i++)for(int j=i+1;j<nj;j++)if(J[i].ct>J[j].ct){__typeof__(J[0])t=J[i];J[i]=J[j];J[j]=t;}
    int s0=nj>10?nj-10:0;cnt=nj-s0;
    if(rm&&*rm>='0'&&*rm<='9'){int x=atoi(rm);if(x>=0&&x<cnt){int j=s0+x;
        for(int s=0;s<J[j].ns;s++){char c[B];snprintf(c,B,"tmux kill-session -t '%s' 2>/dev/null",J[j].s[s]);(void)!system(c);}
        if(J[j].wt){char c[B];snprintf(c,B,"rm -rf '%s'",J[j].p);(void)!system(c);}
        printf("\xe2\x9c\x93 %s\n",J[j].n);}else printf("x Invalid (0-%d)\n",cnt-1);return 0;}
    if(sel&&*sel>='0'&&*sel<='9'){int x=atoi(sel);if(x>=0&&x<cnt){int j=s0+x;
        if(J[j].ns)tm_go(J[j].s[0]);if(chdir(J[j].p)==0){const char*sh=getenv("SHELL");execlp(sh?sh:"/bin/bash",sh?sh:"bash",(char*)NULL);}}return 0;}
    if(!cnt){puts("No jobs");return 0;}
    puts("  #  Active  Repo         Worktree");
    for(int i=0;i<cnt;i++){int j=s0+i;char td[16]="";if(J[j].ct){int d=(int)(time(NULL)-J[j].ct);
        if(d<3600)snprintf(td,16," (%dm)",d/60);else if(d<86400)snprintf(td,16," (%dh)",d/3600);else snprintf(td,16," (%dd)",d/86400);}
        printf("  %d  %s       %-12s %.40s%s\n",i,J[j].act?"\xe2\x97\x8f":"\xe2\x97\x8b",J[j].r,J[j].n,td);
        if(J[j].act&&J[j].ns){char o[B];tm_read(J[j].s[0],o,B);
            char*p=o+strlen(o);while(p>o&&(p[-1]=='\n'||p[-1]==' '))p--;*p=0;
            char*q=p;while(q>o&&q[-1]!='\n')q--;if(*q)printf("         \033[90m%.70s\033[0m\n",q);}}
    puts("\nSelect:\n  a jobs 0\n  a jobs watch\n  a jobs rm 0");return 0;
}

/* ── cleanup ── */
static int cmd_cleanup(int argc, char **argv) { fallback_py("cleanup", argc, argv); }

/* ── tree ── */
static int cmd_tree(int argc, char **argv) {
    init_db(); load_cfg(); load_proj();
    const char *wt = cfget("worktrees_dir"); if (!wt[0]) { char d[P]; snprintf(d,P,"%s/worktrees",AROOT); wt=d; }
    char cwd[P]; if(!getcwd(cwd,P)) snprintf(cwd,P,"%s",HOME);
    const char *proj = cwd;
    if (argc > 2 && argv[2][0]>='0' && argv[2][0]<='9') { int idx=atoi(argv[2]); if(idx<NPJ) proj=PJ[idx].path; }
    if (!git_in_repo(proj)) { puts("x Not a git repo"); return 1; }
    time_t now = time(NULL); struct tm *t = localtime(&now);
    char ts[32]; strftime(ts, 32, "%b%d", t);
    for(char*p=ts;*p;p++) *p=(*p>='A'&&*p<='Z')?*p+32:*p;
    int h=t->tm_hour%12; if(!h)h=12;
    char nm[64],wp[P],c[B];
    snprintf(nm,64,"%s-%s-%d%02d%s",bname(proj),ts,h,t->tm_min,t->tm_hour>=12?"pm":"am");
    for(int i=0;i<2;i++){if(i){size_t l=strlen(nm);char a[3]={nm[l-2],nm[l-1],0};sprintf(nm+l-2,"-%02d%s",t->tm_sec,a);}
        snprintf(wp,P,"%s/%s",wt,nm);snprintf(c,B,"mkdir -p '%s' && git -C '%s' worktree add -b 'wt-%s' '%s' HEAD 2>/dev/null",wt,proj,nm,wp);
        if(!system(c))break;if(i){puts("x Failed");return 1;}}
    printf("\xe2\x9c\x93 %s\n", wp);
    const char *sh = getenv("SHELL"); if (!sh) sh = "/bin/bash";
    if (chdir(wp) == 0) execlp(sh, sh, (char*)NULL);
    return 0;
}
