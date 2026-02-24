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
        snprintf(c, B, "tmux split-window -h -t dash -c '%s' 'sh -c \"a job; exec $SHELL\"'", wd); (void)!system(c);
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

/* ── jobs: ssh cache ── */
static void jobs_ssh_refresh(void) {
    init_db();load_cfg();
    char sdir[P];snprintf(sdir,P,"%s/ssh",SROOT);
    char hpaths[32][P];int nh=listdir(sdir,hpaths,32);
    struct{char hn[64];int fd;pid_t pid;}SP[16];int nsp=0;
    for(int h=0;h<nh&&nsp<16;h++){
        kvs_t kv=kvfile(hpaths[h]);const char*hn=kvget(&kv,"Name");
        if(!hn||!strcmp(hn,DEV))continue;
        int pfd[2];if(pipe(pfd))continue;
        pid_t p=fork();if(p==0){close(pfd[0]);
            char sc[B];snprintf(sc,B,"a ssh %s 'tmux list-panes -a -F \"#{session_name}|#{pane_current_command}|#{pane_current_path}\"' 2>/dev/null",hn);
            FILE*f=popen(sc,"r");if(f){char buf[B];size_t r=fread(buf,1,B-1,f);buf[r]=0;(void)!write(pfd[1],buf,r);pclose(f);}
            close(pfd[1]);_exit(0);}
        close(pfd[1]);snprintf(SP[nsp].hn,64,"%s",hn);SP[nsp].fd=pfd[0];SP[nsp].pid=p;nsp++;}
    char cf[P],tmp[P];snprintf(cf,P,"%s/job_remote.cache",DDIR);snprintf(tmp,P,"%s.%d",cf,getpid());
    FILE*out=fopen(tmp,"w");
    for(int s=0;s<nsp;s++){
        char ro[B];int len=(int)read(SP[s].fd,ro,B-1);ro[len>0?len:0]=0;close(SP[s].fd);waitpid(SP[s].pid,NULL,0);
        for(char*rp=ro;*rp;){char*re=strchr(rp,'\n');if(re)*re=0;
            if(strchr(rp,'|')&&out)fprintf(out,"%s|%s\n",SP[s].hn,rp);
            if(re){rp=re+1;}else break;}}
    if(out){fclose(out);rename(tmp,cf);}
}

typedef struct{char sn[64],pid[32],cmd[32],p[128],dev[32];}jpane_t;
static int jobs_load_cache(jpane_t*A,int na){
    char cf[P];snprintf(cf,P,"%s/job_remote.cache",DDIR);
    char*dat=readf(cf,NULL);if(!dat)return na;
    for(char*rp=dat;*rp&&na<64;){char*re=strchr(rp,'\n');if(re)*re=0;
        char*d1=strchr(rp,'|'),*r1=d1?strchr(d1+1,'|'):0,*r2=r1?strchr(r1+1,'|'):0;
        if(d1&&r1&&r2){*d1=*r1=*r2=0;
            snprintf(A[na].sn,64,"%s",d1+1);A[na].pid[0]=0;
            snprintf(A[na].cmd,32,"%s",r1+1);snprintf(A[na].p,128,"%s",bname(r2+1));
            snprintf(A[na].dev,32,"%s",rp);na++;}
        if(re)rp=re+1;else break;}
    free(dat);return na;
}

/* ── jobs ── active panes (local+remote) + review worktrees */
static int cmd_jobs(int argc, char **argv) {
    const char *sel=NULL,*rm=NULL;
    for(int i=2;i<argc;i++){if(!strcmp(argv[i],"rm")&&i+1<argc)rm=argv[++i];
        else if(!strcmp(argv[i],"watch")){perf_disarm();execlp("watch","watch","-n2","-c","a","job",(char*)0);return 0;}
        else if(strcmp(argv[i],"-r")&&strcmp(argv[i],"--running"))sel=argv[i];}
    jpane_t A[64];int na=0;
    /* Local panes */
    char out[B*2];pcmd("tmux list-panes -a -F '#{session_name}\t#{pane_id}\t#{pane_current_command}\t#{pane_current_path}' 2>/dev/null",out,B*2);
    for(char*p=out;*p&&na<64;){char*e=strchr(p,'\n');if(e)*e=0;
        char*t1=strchr(p,'\t'),*t2=t1?strchr(t1+1,'\t'):0,*t3=t2?strchr(t2+1,'\t'):0;
        if(t1&&t2&&t3){*t1=*t2=*t3=0;
            if(strcmp(t2+1,"bash")&&strcmp(t2+1,"zsh")&&strcmp(t2+1,"sh")){
                snprintf(A[na].sn,64,"%s",p);snprintf(A[na].pid,32,"%s",t1+1);
                snprintf(A[na].cmd,32,"%s",t2+1);snprintf(A[na].p,128,"%s",bname(t3+1));A[na].dev[0]=0;na++;}}
        if(e)p=e+1;else break;}
    /* Remote panes: cache + bg refresh */
    init_db();load_cfg();
    na=jobs_load_cache(A,na);
    {pid_t bg=fork();if(bg==0){jobs_ssh_refresh();_exit(0);}}
    /* Review worktrees */
    char wd[P];{const char*w=cfget("worktrees_dir");if(w[0])snprintf(wd,P,"%s",w);else snprintf(wd,P,"%s/worktrees",AROOT);}
    struct{char n[64],p[256];}R[32];int nr=0;
    if(dexists(wd)){DIR*d=opendir(wd);struct dirent*de;if(d){while((de=readdir(d))&&nr<32){
        if(de->d_name[0]=='.')continue;char fp[P];snprintf(fp,P,"%s/%s",wd,de->d_name);
        if(!dexists(fp))continue;
        int act=0;for(int i=0;i<na;i++)if(!A[i].dev[0]&&!strcmp(bname(fp),A[i].p)){act=1;break;}if(act)continue;
        snprintf(R[nr].n,64,"%s",de->d_name);snprintf(R[nr].p,256,"%s",fp);nr++;}closedir(d);}}
    if(rm&&!strcmp(rm,"all")){for(int i=0;i<nr;i++){char c[B];snprintf(c,B,"rm -rf '%s'",R[i].p);(void)!system(c);}
        printf("\xe2\x9c\x93 %d worktrees\n",nr);return 0;}
    if(rm&&*rm>='0'&&*rm<='9'){int x=atoi(rm);
        if(x<na&&!A[x].dev[0]){char c[B];snprintf(c,B,"tmux kill-pane -t '%s'",A[x].pid);(void)!system(c);printf("\xe2\x9c\x93 %s\n",A[x].sn);}
        else if(x-na>=0&&x-na<nr){char c[B];snprintf(c,B,"rm -rf '%s'",R[x-na].p);(void)!system(c);printf("\xe2\x9c\x93 %s\n",R[x-na].n);}
        return 0;}
    if(sel&&*sel>='0'&&*sel<='9'){int x=atoi(sel);
        if(x<na&&!A[x].dev[0]){char c[B];snprintf(c,B,"tmux select-pane -t '%s'",A[x].pid);(void)!system(c);tm_go(A[x].sn);}
        else if(x<na){perf_disarm();execlp("a","a","ssh",A[x].dev,"tmux","attach","-t",A[x].sn,(char*)NULL);/*foot terminal can fail here; ptyxis works*/}
        else if(x-na<nr){perf_disarm();if(chdir(R[x-na].p)==0){const char*sh=getenv("SHELL");execlp(sh?sh:"/bin/bash",sh?sh:"bash",(char*)NULL);}}
        return 0;}
    if(!na&&!nr){puts("No jobs");return 0;}
    if(na){puts("ACTIVE");for(int i=0;i<na;i++)printf("  %d  %-16s %-10s %-12s %s\n",i,A[i].sn,A[i].cmd,A[i].p,A[i].dev[0]?A[i].dev:"");}
    if(nr){if(na)puts("");puts("REVIEW");for(int i=0;i<nr;i++)printf("  %d  %s\n",na+i,R[i].n);}
    puts("\n  a job #              attach/cd\n  a job rm #           remove\n  a job rm all          clear review\n  a job <p> <prompt>    launch\n  a job <p> @name       saved prompt\n  a job <p> --device h  remote");
    return 0;
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
