/* tmux window list helper */
static int tm_list(char out[B], char *lines[], int max) {
    char c[B];snprintf(c,B,"tmux list-windows -t '%s' -F '#{window_name}' 2>/dev/null",TMS);
    pcmd(c, out, B);
    int n=0; char *p=out;
    while (*p && n < max) { lines[n++]=p; char *e=strchr(p,'\n'); if(e){*e=0;p=e+1;}else break; }
    return n;
}
static int cmd_ls(int argc, char **argv) {
    if (argc > 2 && argv[2][0] >= '0' && argv[2][0] <= '9') {
        char out[B]; char *lines[64]; int n=tm_list(out,lines,64);
        int idx = atoi(argv[2]);
        if (idx >= 0 && idx < n) {
            if(getenv("TMUX"))tm_go(lines[idx]);
            else{char c[B];snprintf(c,B,"tmux select-window -t '"TMS":%s'",lines[idx]);(void)!system(c);printf("→ %s\n",lines[idx]);}
        } return 0;
    }
    char out[B];snprintf(out,B,"tmux list-windows -t '%s' -F '#{window_name}\t#{pane_current_path}' 2>/dev/null",TMS);
    char buf[B];pcmd(out,buf,B);
    if(!*buf){puts("No windows");return 0;}
    int i=0;for(char*p=buf;*p;i++){char*e=strchr(p,'\n');if(e)*e=0;
        char*t=strchr(p,'\t');if(t)*t=0;
        printf("  %d  %s: %s\n",i,p,t?t+1:"");
        if(e)p=e+1;else break;}
    puts("\nSelect:\n  a ls 0"); return 0;
}

static int cmd_kill(int argc, char **argv) {
    const char *sel = argc > 2 ? argv[2] : NULL;
    if ((sel && !strcmp(sel, "all")) || (argc > 1 && !strcmp(argv[1], "killall"))) {
        int now = (argc > 2 && !strcmp(argv[argc-1], "now"));
        if (!tmux_kill_gate("kill all", isatty(0) || now)) return 1;
        (void)!system("pkill -9 tmux 2>/dev/null; sleep 1");
        (void)!system("clear"); puts("✓"); return 0;
    }
    /* combine intelligently: numeric selector = tmux window; bare or a name = app process killer (lib/kil.py) */
    if (!sel || sel[0] < '0' || sel[0] > '9') {
        char c[B]; int o = snprintf(c, B, "python3 '%s/lib/kil.py'", SDIR);
        for (int i = 2; i < argc && o < B; i++) o += snprintf(c+o, (size_t)(B-o), " '%s'", argv[i]);
        return system(c) ? 1 : 0;
    }
    char out[B]; char *lines[64]; int n=tm_list(out,lines,64);
    if (!n) { puts("No windows"); return 0; }
    if (sel && sel[0] >= '0' && sel[0] <= '9') {
        int idx = atoi(sel);
        if (idx >= 0 && idx < n) {
            char c[B]; snprintf(c, B, "tmux kill-window -t '%s:%s'", TMS, lines[idx]); (void)!system(c);
            printf("✓ %s\n", lines[idx]); return 0;
        }
    }
    for (int i = 0; i < n; i++) printf("  %d  %s\n", i, lines[i]);
    puts("\nSelect:\n  a kill 0\n  a kill all"); return 0;
}

static int cmd_copy(int c,char**v){char o[B];int ol=0;const char*k=clip_cmd();if(!k){puts("x No clipboard");return 1;}   /* a copy FILE | cmd|a copy | a copy (in tmux: last output) */
    if(c>2||!isatty(0)){int fd=c>2?open(v[2],O_RDONLY):0;if(fd<0){printf("x no file %s\n",v[2]);return 1;}   /* file|pipe: fd -> clip tool, detached: wl-copy needs ~60ms, the perf gate 1.9 */
        if(!fork()){setsid();dup2(fd,0);execl("/bin/sh","sh","-c",k,(char*)0);_exit(127);}printf("✓ %s → %s\n",c>2?v[2]:"stdin",k);return 0;}
    if(getenv("TMUX")){pcmd("tmux capture-pane -pJ -S-99|awk '/[$@].*[$@]|❯/{b=s;s=\"\";next}{s=s?s\"\\n\"$0:$0}END{printf\"%s\",b}'",o,B);ol=(int)strlen(o);}
    else{puts("x Pipe or tmux");return 1;}
    if(ol<1){puts("x No output");return 0;}o[ol]=0;if(to_clip(o)){puts("x Needs tmux");return 1;}printf("✓ %.50s\n",o);return 0;}

/* ── jobs ── active panes (local+remote) + review worktrees */
typedef struct{char sn[64],pid[32],cmd[32],p[128],dev[32];}jpane_t;
static int cmd_jobs(int argc, char **argv) {
    const char *sel=NULL,*rm=NULL;
    for(int i=2;i<argc;i++){if(!strcmp(argv[i],"rm")&&i+1<argc)rm=argv[++i];
        else if(!strcmp(argv[i],"watch")){perf_disarm();execlp("watch","watch","-n2","-c","a","j",(char*)0);return 0;}
        else if(strcmp(argv[i],"-r")&&strcmp(argv[i],"--running"))sel=argv[i];}
    init_db();load_cfg();
    jpane_t A[64]={0};int na=0;
    /* Local windows */
    char out[B*2];pcmd("tmux list-windows -a -F '#{session_name}\t#{window_id}\t#{pane_current_command}\t#{pane_current_path}' 2>/dev/null",out,B*2);
    for(char*p=out;*p&&na<64;){char*e=strchr(p,'\n');if(e)*e=0;
        char*t1=strchr(p,'\t'),*t2=t1?strchr(t1+1,'\t'):0,*t3=t2?strchr(t2+1,'\t'):0;
        if(t1&&t2&&t3){*t1=*t2=*t3=0;
            snprintf(A[na].sn,64,"%s",p);snprintf(A[na].pid,32,"%s",t1+1);
            snprintf(A[na].cmd,32,"%s",t2+1);snprintf(A[na].p,128,"%s",bname(t3+1));snprintf(A[na].dev,32,"%s",DEV);na++;}
        if(e)p=e+1;else break;}
    /* Remote panes: read cache, bg refresh */
    {char cf[P];snprintf(cf,P,"%s/job_remote.cache",DDIR);
    char*dat=readf(cf,NULL);if(dat){
        for(char*rp=dat;*rp&&na<64;){char*re=strchr(rp,'\n');if(re)*re=0;
            char*d1=strchr(rp,'|'),*r1=d1?strchr(d1+1,'|'):0,*r2=r1?strchr(r1+1,'|'):0;
            if(d1&&r1&&r2){*d1=*r1=*r2=0;
                int dup=0;for(int j=0;j<na;j++)if(!strcmp(A[j].sn,d1+1)&&!strcmp(A[j].dev,rp)){dup=1;break;}
                if(!dup){snprintf(A[na].sn,64,"%s",d1+1);A[na].pid[0]=0;
                snprintf(A[na].cmd,32,"%s",r1+1);snprintf(A[na].p,128,"%s",bname(r2+1));
                snprintf(A[na].dev,32,"%s",rp);na++;}}
            if(re)rp=re+1;else break;}free(dat);}}
    {pid_t bg=fork();if(bg==0){close(0);close(1);close(2);
        char sdir[P];snprintf(sdir,P,"%s/ssh",SROOT);
        char hp[32][P];int nh=listdir(sdir,hp,32);
        struct{char hn[64];int fd;pid_t pid;}SP[16]={0};int nsp=0;
        for(int h=0;h<nh&&nsp<16;h++){
            kvs_t kv=kvfile(hp[h]);const char*hn=kvget(&kv,"Name");
            if(!hn||!strcmp(hn,DEV))continue;
            int pfd[2];if(pipe(pfd))continue;
            pid_t p=fork();if(p==0){close(pfd[0]);
                char sc[B];snprintf(sc,B,"a ssh %s 'tmux list-windows -a -F \"#{session_name}|#{pane_current_command}|#{pane_current_path}\"' 2>/dev/null",hn);
                FILE*f=popen(sc,"r");if(f){char buf[B];size_t r=fread(buf,1,B-1,f);buf[r]=0;(void)!write(pfd[1],buf,r);pclose(f);}
                close(pfd[1]);_exit(0);}
            close(pfd[1]);snprintf(SP[nsp].hn,64,"%s",hn);SP[nsp].fd=pfd[0];SP[nsp].pid=p;nsp++;}
        char cf[P],tmp[P];snprintf(cf,P,"%s/job_remote.cache",DDIR);snprintf(tmp,P,"%s.%d",cf,getpid());
        FILE*fo=fopen(tmp,"w");
        for(int s=0;s<nsp;s++){
            char ro[B];int len=(int)read(SP[s].fd,ro,B-1);ro[len>0?len:0]=0;close(SP[s].fd);waitpid(SP[s].pid,NULL,0);
            for(char*rp=ro;*rp;){char*re=strchr(rp,'\n');if(re)*re=0;
                if(strchr(rp,'|')&&fo)fprintf(fo,"%s|%s\n",SP[s].hn,rp);
                if(re){rp=re+1;}else break;}}
        if(fo){fclose(fo);rename(tmp,cf);}
        _exit(0);}}
    if(rm&&*rm>='0'&&*rm<='9'){int x=atoi(rm);
        if(x<na&&A[x].pid[0]){char c[B];snprintf(c,B,"tmux kill-window -t '%s'",A[x].pid);(void)!system(c);printf("✓ %s\n",A[x].sn);}
        return 0;}
    if(sel&&*sel>='0'&&*sel<='9'){int x=atoi(sel);
        if(x<na&&A[x].pid[0]){char c[B];snprintf(c,B,"tmux select-window -t '%s'",A[x].pid);(void)!system(c);tm_go(A[x].sn);}
        else if(x<na){perf_disarm();execlp("a","a","ssh",A[x].dev,"tmux","new-session","-t",A[x].sn,(char*)NULL);}
        return 0;}
    hub_load();
    if(!na&&!NJ){puts("No jobs");return 0;}
    if(na){puts("ACTIVE");for(int i=0;i<na;i++)printf(" %d %-12s %-5s %-5s %s\n",i,A[i].sn,A[i].cmd,A[i].p,A[i].dev);}
    if(NJ){hub_sort();hub_timers();
        if(na)puts("");printf("SCHEDULED\n  %-10s %-6s %-8s  %s\n","Name","Sched","Dev","Cmd");for(int i=0;i<NJ;i++){
        hub_t*j=&HJ[i];char cp[128];hub_trunc(cp,128,j->p,50);
        printf("  %-10s %-6s %-8.7s%s %s\n",j->n,j->s,j->d,hub_on(j)?"✓":" ",cp);}}
    printf("\n  a j \"prompt\"  new job    a j a  agent    a job #  attach    a job rm #\n  a hub add <name> <sched> <cmd>  schedule recurring    a hub  manage\n  e %s/common/prompts/job.txt\n",SROOT);
    return 0;
}

