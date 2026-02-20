/* ═══ HUB — scheduled jobs (systemd timers) ═══ */
#define MJ 64
typedef struct { char n[64],s[16],p[512],d[64],lr[24]; int en; } hub_t;
static hub_t HJ[MJ]; static int NJ;

static const char *dfl(const char *a, const char *b) { return a ? a : b; }

static void hub_load(void) {
    char hd[P]; snprintf(hd,P,"%s/agents",SROOT); mkdirp(hd);
    DIR *dp=opendir(hd); if(!dp) return;
    struct dirent *e; NJ=0;
    while((e=readdir(dp))&&NJ<MJ) {
        if(e->d_name[0]=='.'||!strstr(e->d_name,".txt")||strstr(e->d_name,"_20")) continue;
        char fp[P]; snprintf(fp,P,"%s/%s",hd,e->d_name);
        kvs_t kv=kvfile(fp); const char *nm=kvget(&kv,"Name"); if(!nm) continue;
        hub_t *j=&HJ[NJ++]; const char *en=kvget(&kv,"Enabled");
        snprintf(j->n,64,"%s",nm); snprintf(j->s,16,"%s",dfl(kvget(&kv,"Schedule"),""));
        snprintf(j->p,512,"%s",dfl(kvget(&kv,"Prompt"),"")); snprintf(j->d,64,"%s",dfl(kvget(&kv,"Device"),DEV));
        j->en=!en||en[0]=='t'||en[0]=='T'; snprintf(j->lr,24,"%s",dfl(kvget(&kv,"Last-Run"),""));
    }
    closedir(dp);
}

static void hub_save(hub_t *j) {
    char hd[P],fn[P],buf[B]; snprintf(hd,P,"%s/agents",SROOT); mkdirp(hd);
    snprintf(fn,P,"%s/%s.txt",hd,j->n);
    int l=snprintf(buf,B,"Name: %s\nSchedule: %s\nPrompt: %s\nDevice: %s\nEnabled: %s\n",
        j->n,j->s,j->p,j->d,j->en?"true":"false");
    if(j->lr[0]) snprintf(buf+l,(size_t)(B-l),"Last-Run: %s\n",j->lr);
    writef(fn,buf);
}

static void hub_timer(hub_t *j, int on) {
    char sd[P],buf[B]; snprintf(sd,P,"%s/.config/systemd/user",HOME); mkdirp(sd);
    if(on) {
        snprintf(buf,B,"[Unit]\nDescription=%s\n[Service]\nType=oneshot\nExecStart=/bin/bash -c '%s/.local/bin/a hub run %s'\n",j->n,HOME,j->n);
        char svc[P]; snprintf(svc,P,"%s/aio-%s.service",sd,j->n); writef(svc,buf);
        snprintf(buf,B,"[Unit]\nDescription=%s\n[Timer]\nOnCalendar=%s\nAccuracySec=1s\nPersistent=true\n[Install]\nWantedBy=timers.target\n",j->n,j->s);
        char tmr[P]; snprintf(tmr,P,"%s/aio-%s.timer",sd,j->n); writef(tmr,buf);
        snprintf(buf,B,"systemctl --user daemon-reload && systemctl --user enable --now aio-%s.timer 2>/dev/null",j->n);
    } else {
        snprintf(buf,B,"systemctl --user disable --now aio-%s.timer 2>/dev/null;"
            "rm -f '%s/aio-%s.timer' '%s/aio-%s.service'",j->n,sd,j->n,sd,j->n);
    }
    (void)!system(buf);
}

static hub_t *hub_find(const char *s) {
    if(s[0]>='0'&&s[0]<='9') { int i=atoi(s); return i<NJ?&HJ[i]:NULL; }
    for(int i=0;i<NJ;i++) if(!strcmp(HJ[i].n,s)) return &HJ[i];
    return NULL;
}

static int cmd_hub(int argc, char **argv) {
    init_db(); hub_load();
    const char *sub=argc>2?argv[2]:NULL;
    char hd[P]; snprintf(hd,P,"%s/agents",SROOT);

    if(!sub) {
        char url[512],c[B]; snprintf(c,B,"git -C '%s' remote get-url origin 2>/dev/null",SROOT);
        pcmd(c,url,512); url[strcspn(url,"\n")]=0;
        printf("Hub: %d jobs\n  %s\n  %s\n\n",NJ,hd,url);
        /* timer status */
        char tl[B*4]; pcmd("systemctl --user list-timers 2>/dev/null",tl,sizeof(tl));
        int tw=80; struct winsize ws; if(ioctl(STDOUT_FILENO,TIOCGWINSZ,&ws)==0) tw=ws.ws_col;
        int m=tw<60, cw=tw-(m?32:48);
        printf(m?"# %-8s %-9s On Cmd\n":"# %-10s %-6s %-12s %-8s On Cmd\n","Name",m?"Last":"Sched","Last","Dev");
        for(int i=0;i<NJ;i++) {
            hub_t *j=&HJ[i]; char pat[96]; snprintf(pat,96,"aio-%s.timer",j->n);
            int on=(!strcmp(j->d,DEV))?j->en&&strstr(tl,pat)!=NULL:j->en;
            char cp[512]; int pl=(int)strlen(j->p);
            if(pl>cw&&cw>5){int h=cw/2-1;snprintf(cp,512,"%.*s..%s",h,j->p,j->p+pl-(cw-h-2));}
            else snprintf(cp,512,"%s",j->p);
            const char *lr=j->lr[0]?j->lr+5:"-";
            if(m) printf("%-2d%-9.8s%-10.9s%s %s\n",i,j->n,lr,on?"\xe2\x9c\x93":" ",cp);
            else printf("%-2d%-11.10s%-7.6s%-13.12s%-8.7s%s %s\n",i,j->n,j->s,lr,j->d,on?"\xe2\x9c\x93":" ",cp);
        }
        printf("\na hub <#>       run job\na hub on/off #  toggle\na hub add|rm    create/delete\n");
        return 0;
    }

    if(!strcmp(sub,"add")) {
        if(argc<6) { fprintf(stderr,"Usage: a hub add <name> <sched> <cmd...>\n"); return 1; }
        hub_t j={.en=1}; snprintf(j.n,64,"%s",argv[3]); snprintf(j.s,16,"%s",argv[4]);
        char cmd[B]=""; for(int i=5,l=0;i<argc;i++) l+=snprintf(cmd+l,(size_t)(B-l),"%s%s",i>5?" ":"",argv[i]);
        snprintf(j.p,512,"%s",cmd); snprintf(j.d,64,"%s",DEV);
        hub_save(&j); sync_repo(); hub_timer(&j,1);
        printf("\xe2\x9c\x93 %s @ %s\n",j.n,j.s); return 0;
    }

    if(!strcmp(sub,"run")||!strcmp(sub,"on")||!strcmp(sub,"off")||!strcmp(sub,"rm")) {
        hub_t *j=argc>3?hub_find(argv[3]):NULL;
        if(!j) { fprintf(stderr,"x %s?\n",argc>3?argv[3]:"(missing)"); return 1; }
        if(!strcmp(sub,"run")) {
            char cmd[B]; if(!strncmp(j->p,"aio ",4)) snprintf(cmd,B,"%s %s",G_argv[0],j->p+4);
            else snprintf(cmd,B,"%s",j->p);
            printf("Running %s...\n",j->n); fflush(stdout);
            /* capture output for log */
            char lf[P]; snprintf(lf,P,"%s/hub.log",DDIR);
            FILE *fp=popen(cmd,"r"); char out[B*4]=""; int ol=0;
            if(fp) { char b[B]; while(fgets(b,B,fp)&&ol<(int)sizeof(out)-B) { fputs(b,stdout); ol+=sprintf(out+ol,"%s",b); } pclose(fp); }
            time_t now=time(NULL); struct tm *t=localtime(&now); char ts[32];
            strftime(ts,32,"%Y-%m-%d %I:%M:%S%p",t); strftime(j->lr,24,"%Y-%m-%d %H:%M",t);
            hub_save(j); sync_bg();
            FILE *lp=fopen(lf,"a"); if(lp) { fprintf(lp,"\n[%s] %s\n%s",ts,j->n,out); fclose(lp); }
            char sn[128]; snprintf(sn,128,"hub:%s",j->n); alog(sn,""," ");
            printf("\xe2\x9c\x93\n"); return 0;
        }
        if(!strcmp(sub,"on")||!strcmp(sub,"off")) {
            j->en=sub[1]=='n'; hub_save(j); sync_repo(); hub_timer(j,j->en);
            printf("\xe2\x9c\x93 %s %s\n",j->n,sub); return 0;
        }
        /* rm */
        hub_timer(j,0); char fn[P]; snprintf(fn,P,"%s/%s.txt",hd,j->n); unlink(fn);
        sync_repo(); printf("\xe2\x9c\x93 rm %s\n",j->n); return 0;
    }

    if(!strcmp(sub,"sync")) {
        for(int i=0;i<NJ;i++) hub_timer(&HJ[i],0);
        int m=0; for(int i=0;i<NJ;i++) if(!strcmp(HJ[i].d,DEV)&&HJ[i].en) { hub_timer(&HJ[i],1); m++; }
        printf("\xe2\x9c\x93 synced %d jobs\n",m); return 0;
    }

    if(!strcmp(sub,"log")) {
        char lf[P]; snprintf(lf,P,"%s/hub.log",DDIR);
        if(!fexists(lf)) { puts("No logs"); return 0; }
        char c[B]; snprintf(c,B,"tail -40 '%s'",lf); (void)!system(c); return 0;
    }

    fprintf(stderr,"Usage: a hub [add|run|on|off|rm|sync|log]\n"); return 1;
}
