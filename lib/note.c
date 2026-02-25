/* ── note/task shared ── */
static void do_archive(const char *p) {
    const char *s=strrchr(p,'/'); char a[P],d[P]; snprintf(a,P,"%.*s/.archive",(int)(s-p),p); mkdirp(a);
    snprintf(d,P,"%s%s",a,s); rename(p,d);
}
/* ── note ── */
static void note_save(const char *d, const char *t) {
    struct timespec tp; clock_gettime(CLOCK_REALTIME,&tp); time_t now=tp.tv_sec;
    char ts[32],fn[P],buf[B]; strftime(ts,32,"%Y%m%dT%H%M%S",localtime(&now));
    snprintf(fn,P,"%s/%08x_%s.%09ld.txt",d,(unsigned)(tp.tv_nsec^(unsigned)now),ts,tp.tv_nsec);
    snprintf(buf,B,"Text: %s\nStatus: pending\nDevice: %s\nCreated: %s\n",t,DEV,ts); writef(fn,buf);
}
static char gnp[1024][P],gnt[1024][512];
static int gn_archived;
static int load_notes(const char *dir, const char *f) {
    DIR *d=opendir(dir); if(!d) return 0; struct dirent *e; int n=0; gn_archived=0;
    while((e=readdir(d))) { if(e->d_name[0]=='.'||!strstr(e->d_name,".txt")) continue;
        char fp[P]; snprintf(fp,P,"%s/%s",dir,e->d_name); kvs_t kv=kvfile(fp);
        const char *t=kvget(&kv,"Text"),*s=kvget(&kv,"Status");
        if(t&&(!s||!strcmp(s,"pending"))&&(!f||strcasestr(t,f))){
            int dup=0;for(int i=0;i<n;i++)if(!strcmp(gnt[i],t)){dup=1;break;}
            if(dup){do_archive(fp);gn_archived++;}
            else if(n<1024){snprintf(gnp[n],P,"%s",fp);snprintf(gnt[n],512,"%s",t);n++;}}
    } closedir(d); return n;
}
static int cmd_note(int argc, char **argv) {
    if (getenv("A_BENCH")) return 0;
    char dir[P]; snprintf(dir,P,"%s/notes",SROOT); mkdirp(dir);
    if(argc>2&&!strcmp(argv[2],"l")){do load_notes(dir,NULL);while(gn_archived);/* archive dupes */
        DIR *d=opendir(dir);if(!d){puts("(none)");return 0;}struct dirent *e;int n=0;
        while((e=readdir(d))){if(e->d_name[0]=='.'||!strstr(e->d_name,".txt"))continue;
            char fp[P];snprintf(fp,P,"%s/%s",dir,e->d_name);kvs_t kv=kvfile(fp);
            const char *t=kvget(&kv,"Text"),*s=kvget(&kv,"Status"),*dv=kvget(&kv,"Device"),*cr=kvget(&kv,"Created");
            if(!t||(s&&strcmp(s,"pending")))continue;
            printf("%3d. %s",++n,t);
            if(dv||cr){printf("  \033[90m");if(dv)printf(" %s",dv);if(cr)printf(" %s",cr);printf("\033[0m");}
            putchar('\n');}
        closedir(d);if(!n)puts("(none)");return 0;}
    if(argc>2&&argv[2][0]!='?'){char t[B]="";for(int i=2,l=0;i<argc;i++) l+=snprintf(t+l,(size_t)(B-l),"%s%s",i>2?" ":"",argv[i]);
        note_save(dir,t);sync_bg();puts("\xe2\x9c\x93");return 0;}
    const char *f=(argc>2&&argv[2][0]=='?')?argv[2]+1:NULL; int n=load_notes(dir,f);
    if(!n){puts("a n <text> | a n l");return 0;} if(!isatty(STDIN_FILENO)){for(int i=0;i<n&&i<10;i++)puts(gnt[i]);return 0;} perf_disarm();
    printf("Notes: %d pending  (a n l = list all)\n  %s\n\n[a]ck [d]el [s]earch [q]uit | type=add\n",n,dir);
    for(int i=0,s=n<1024?n:1024;i<s;){
        printf("\n[%d/%d] %s\n> ",i+1,n,gnt[i]); char line[B]; if(!fgets(line,B,stdin)) break; line[strcspn(line,"\n")]=0;
        if(line[0]=='q'&&!line[1]) break;
        if(!line[1]&&(line[0]=='a'||line[0]=='d')){do_archive(gnp[i]);sync_bg();puts("\xe2\x9c\x93");memmove(gnp+i,gnp+i+1,(size_t)(s-i-1)*P);memmove(gnt+i,gnt+i+1,(size_t)(s-i-1)*512);n--;s=n<1024?n:1024;continue;}
        if(line[0]=='s'&&!line[1]){printf("search: ");char q[128];if(fgets(q,128,stdin)){q[strcspn(q,"\n")]=0;n=load_notes(dir,q);s=n<1024?n:1024;i=0;printf("%d results\n",n);}continue;}
        if(line[0]){note_save(dir,line);sync_bg();n=load_notes(dir,NULL);s=n<1024?n:1024;printf("\xe2\x9c\x93 [%d]\n",n);continue;}
        i++;
    } return 0;
}
/* ── task ── */
typedef struct{char d[P],t[256],p[8];}Tk;
static Tk T[256];
static int tcmp(const void*a,const void*b){int c=strcmp(((const Tk*)a)->p,((const Tk*)b)->p);return c?c:strcmp(((const Tk*)a)->d,((const Tk*)b)->d);}
static int load_tasks(const char*dir){
    DIR*d=opendir(dir);if(!d)return 0;struct dirent*e;int n=0;
    while((e=readdir(d))&&n<256){
        if(e->d_name[0]=='.'||!strcmp(e->d_name,"README.md"))continue;
        const char*nm=e->d_name;snprintf(T[n].d,P,"%s/%s",dir,nm);
        int hp=strlen(nm)>5&&nm[5]=='-'&&isdigit(nm[0])&&isdigit(nm[1])&&isdigit(nm[2])&&isdigit(nm[3])&&isdigit(nm[4]);
        if(hp){memcpy(T[n].p,nm,5);T[n].p[5]=0;}else strcpy(T[n].p,"50000");
        const char*s=hp?nm+6:nm;int tl;
        const char*u=strchr(s,'_');const char*x=strstr(s,".txt");
        tl=u?(int)(u-s):x?(int)(x-s):(int)strlen(s);
        if(tl>255)tl=255;for(int i=0;i<tl;i++)T[n].t[i]=s[i]=='-'||s[i]=='_'?' ':s[i];T[n].t[tl]=0;n++;
    }closedir(d);qsort(T,(size_t)n,sizeof(Tk),tcmp);return n;
}
static void task_add(const char*dir,const char*t,int pri){
    char sl[64];snprintf(sl,64,"%.32s",t);for(char*p=sl;*p;p++)*p=*p==' '||*p=='/'?'-':*p>='A'&&*p<='Z'?*p+32:*p;
    struct timespec tp;clock_gettime(CLOCK_REALTIME,&tp);
    char ts[32],td[P],fn[P],buf[B];strftime(ts,32,"%Y%m%dT%H%M%S",localtime(&tp.tv_sec));
    snprintf(td,P,"%s/%05d-%s_%s",dir,pri,sl,ts);mkdir(td,0755);
    char sd[P];snprintf(sd,P,"%s/task",td);mkdir(sd,0755);
    snprintf(fn,P,"%s/task/%s.%09ld_%s.txt",td,ts,tp.tv_nsec,DEV);
    snprintf(buf,B,"Text: %s\nDevice: %s\nCreated: %s\n",t,DEV,ts);writef(fn,buf);
}
static void task_printbody(const char*path){
    size_t l;char*r=readf(path,&l);if(!r)return;if(!strncmp(r,"Text: ",6))r+=6;
    for(char*p=r;;){char*nl=strchr(p,'\n');if(nl)*nl=0;
        if(*p&&strncmp(p,"Device: ",8)&&strncmp(p,"Created: ",9))printf("    %s\n",p);
        if(!nl)break;p=nl+1;}
}
static int task_counts(const char*dir,char*out,int sz){
    DIR*d=opendir(dir);if(!d){*out=0;return 0;}struct dirent*e;
    struct{char n[64];int c;}s[32];int nd=0;
    while((e=readdir(d))&&nd<32){if(e->d_name[0]=='.'||e->d_type!=DT_DIR)continue;
        char sd[P];snprintf(sd,P,"%s/%s",dir,e->d_name);DIR*ds=opendir(sd);if(!ds)continue;
        struct dirent*f;int c=0;while((f=readdir(ds)))if(f->d_type==DT_REG&&strstr(f->d_name,".txt"))c++;
        closedir(ds);if(c){snprintf(s[nd].n,64,"%s",e->d_name);s[nd].c=c;nd++;}
    }closedir(d);if(!nd){*out=0;return 0;}
    for(int i=0;i<nd-1;i++)for(int j=i+1;j<nd;j++)if(strcmp(s[i].n,s[j].n)>0){
        char tn[64];int tc;memcpy(tn,s[i].n,64);tc=s[i].c;memcpy(s[i].n,s[j].n,64);s[i].c=s[j].c;memcpy(s[j].n,tn,64);s[j].c=tc;}
    int p=snprintf(out,(size_t)sz," [");for(int i=0;i<nd;i++)p+=snprintf(out+p,(size_t)(sz-p),"%s%d %s",i?", ":"",s[i].c,s[i].n);
    snprintf(out+p,(size_t)(sz-p),"]");return nd;
}
static void dl_norm(const char*in,char*out,size_t sz){
    int y,m,d,h=23,mi=59;time_t now=time(NULL);struct tm*t=localtime(&now);
    if(sscanf(in,"%d-%d-%d %d:%d",&y,&m,&d,&h,&mi)>=3){snprintf(out,sz,"%04d-%02d-%02d %02d:%02d",y,m,d,h,mi);}
    else if(sscanf(in,"%d-%d %d:%d",&m,&d,&h,&mi)>=2){snprintf(out,sz,"%04d-%02d-%02d %02d:%02d",t->tm_year+1900,m,d,h,mi);}
    else snprintf(out,sz,"%s",in);}
static int task_dl(const char*td){char df[P];snprintf(df,P,"%s/deadline.txt",td);
    size_t l;char*c=readf(df,&l);if(!c)return-1;struct tm d={0};int h=23,mi=59;
    if(sscanf(c,"%d-%d-%d %d:%d",&d.tm_year,&d.tm_mon,&d.tm_mday,&h,&mi)<3){free(c);return-1;}
    d.tm_year-=1900;d.tm_mon--;d.tm_hour=h;d.tm_min=mi;free(c);return(int)((mktime(&d)-time(NULL))/86400);}
typedef struct{char n[256];char ts[32];}Ent;
static int entcmp(const void*a,const void*b){return strcmp(((const Ent*)a)->ts,((const Ent*)b)->ts);}
static void ts_human(const char*ts,char*out,size_t sz){
    /* "20260207T033024" → "Feb 7 3:30am" */
    if(!ts||strlen(ts)<15||ts[8]!='T'){snprintf(out,sz,"(original)");return;}
    struct tm t={0};
    t.tm_year=(ts[0]-'0')*1000+(ts[1]-'0')*100+(ts[2]-'0')*10+(ts[3]-'0')-1900;
    t.tm_mon=(ts[4]-'0')*10+(ts[5]-'0')-1;t.tm_mday=(ts[6]-'0')*10+(ts[7]-'0');
    t.tm_hour=(ts[9]-'0')*10+(ts[10]-'0');t.tm_min=(ts[11]-'0')*10+(ts[12]-'0');
    int h=t.tm_hour;const char*ap=h>=12?"pm":"am";h=h%12;if(!h)h=12;
    strftime(out,sz,"%b %-d",mktime(&t)?&t:&t);
    char tmp[32];snprintf(tmp,32," %d:%02d%s",h,t.tm_min,ap);
    strncat(out,tmp,sz-strlen(out)-1);
}
typedef struct{char sid[128];char tmx[128];char ts[32];char wd[P];int st;}Sess;
static int load_sessions(const char*td,Sess*ss,int max){
    DIR*d=opendir(td);if(!d)return 0;struct dirent*e;int ns=0;
    while((e=readdir(d))&&ns<max){
        if(strncmp(e->d_name,"session_",8)||!strstr(e->d_name,".txt"))continue;
        char fp[P];snprintf(fp,P,"%s/%s",td,e->d_name);
        size_t l;char*r=readf(fp,&l);if(!r)continue;
        ss[ns].sid[0]=ss[ns].tmx[0]=ss[ns].ts[0]=ss[ns].wd[0]=0;
        for(char*p=r;;){char*nl=strchr(p,'\n');if(nl)*nl=0;
            if(!strncmp(p,"SessionID: ",11))snprintf(ss[ns].sid,128,"%s",p+11);
            if(!strncmp(p,"TmuxSession: ",13))snprintf(ss[ns].tmx,128,"%s",p+13);
            if(!strncmp(p,"Started: ",9))snprintf(ss[ns].ts,32,"%s",p+9);
            if(!strncmp(p,"Cwd: ",5))snprintf(ss[ns].wd,P,"%s",p+5);
            if(!nl)break;p=nl+1;}
        free(r);
        ss[ns].st=2;
        ns++;}
    closedir(d);
    /* sort by timestamp ascending */
    for(int a=0;a<ns-1;a++)for(int b=a+1;b<ns;b++)if(strcmp(ss[a].ts,ss[b].ts)>0){Sess tmp=ss[a];ss[a]=ss[b];ss[b]=tmp;}
    return ns;
}
static void task_todir(char*p){char tmp[P];snprintf(tmp,P,"%s.tmp",p);rename(p,tmp);mkdir(p,0755);
    char dst[P];snprintf(dst,P,"%s/task.txt",p);rename(tmp,dst);}
static void task_show(int i,int n){
    Sess ss[32];int ns=load_sessions(T[i].d,ss,32);
    char sl[32];if(ns)snprintf(sl,32,"\033[33m%d sess\033[0m",ns);else snprintf(sl,32,"\033[90mnot run\033[0m");
    int dd=task_dl(T[i].d);char dv[32]="";if(dd>=0)snprintf(dv,32,"  %s%dd\033[0m",dd<=1?"\033[31m":dd<=7?"\033[33m":"\033[90m",dd);
    printf("\n\033[1m\xe2\x94\x81\xe2\x94\x81\xe2\x94\x81 %d/%d [P%s] %.50s\033[0m  %s%s\n",i+1,n,T[i].p,T[i].t,sl,dv);
    struct stat st;if(stat(T[i].d,&st)||!S_ISDIR(st.st_mode)){task_printbody(T[i].d);return;}
    /* collect all non-session .txt files with timestamps for chrono sort */
    Ent all[256];int na=0;
    DIR*d=opendir(T[i].d);if(!d)return;struct dirent*e;
    while((e=readdir(d))&&na<256){if(e->d_name[0]=='.'||!strncmp(e->d_name,"session_",8)||!strncmp(e->d_name,"prompt_",7))continue;
        char fp[P];snprintf(fp,P,"%s/%s",T[i].d,e->d_name);
        if(e->d_type==DT_REG&&strstr(e->d_name,".txt")){
            snprintf(all[na].n,256,"%s",fp);
            const char*u=strchr(e->d_name,'_');
            if(u&&strlen(u+1)>=15)snprintf(all[na].ts,32,"%.15s",u+1);
            else snprintf(all[na].ts,32,"0");
            na++;
        }else if(e->d_type==DT_DIR&&strncmp(e->d_name,"prompt_",7)){
            DIR*s=opendir(fp);if(!s)continue;struct dirent*f;
            while((f=readdir(s))&&na<256){if(f->d_type!=DT_REG||!strstr(f->d_name,".txt"))continue;
                snprintf(all[na].n,256,"%s/%s",fp,f->d_name);
                const char*v=f->d_name;if(strlen(v)>=15&&v[8]=='T')snprintf(all[na].ts,32,"%.15s",v);
                else snprintf(all[na].ts,32,"0");
                na++;}
            closedir(s);}}
    closedir(d);qsort(all,(size_t)na,sizeof(Ent),entcmp);
    for(int j=0;j<na;j++){char ht[48];
        if(all[j].ts[0]!='0')ts_human(all[j].ts,ht,48);else snprintf(ht,48,"(original)");
        printf("\n  \033[90m%s\033[0m  text\n",ht);task_printbody(all[j].n);}
    /* show prompt candidates (dirs or legacy .txt files) */
    int pc=2;DIR*pd=opendir(T[i].d);struct dirent*pe;
    while(pd&&(pe=readdir(pd))){
        if(strncmp(pe->d_name,"prompt_",7))continue;
        char pp[P];snprintf(pp,P,"%s/%s",T[i].d,pe->d_name);
        struct stat ps;if(stat(pp,&ps))continue;
        char ht[48];struct tm*mt=localtime(&ps.st_mtime);
        int h=mt->tm_hour%12;if(!h)h=12;
        strftime(ht,48,"%b %-d",mt);char tmp[32];snprintf(tmp,32," %d:%02d%s",h,mt->tm_min,mt->tm_hour>=12?"pm":"am");
        strncat(ht,tmp,48-strlen(ht)-1);
        if(S_ISDIR(ps.st_mode)){
            char fv[P]="",mv[64]="",cfp[P];
            snprintf(cfp,P,"%s/folder.txt",pp);{size_t l;char*c=readf(cfp,&l);if(c){snprintf(fv,P,"%s",c);fv[strcspn(fv,"\n")]=0;free(c);}}
            snprintf(cfp,P,"%s/model.txt",pp);{size_t l;char*c=readf(cfp,&l);if(c){snprintf(mv,64,"%s",c);mv[strcspn(mv,"\n")]=0;free(c);}}
            snprintf(cfp,P,"%s/prompt.txt",pp);
            printf("\n  \033[90m%s\033[0m  \033[35mprompt #%d\033[0m  \033[90m%s  %s\033[0m\n",ht,pc,mv,fv);
            task_printbody(cfp);
        }else if(S_ISREG(ps.st_mode)){
            printf("\n  \033[90m%s\033[0m  \033[35mprompt #%d\033[0m\n",ht,pc);
            task_printbody(pp);
        }else continue;
        pc++;}
    if(pd)closedir(pd);
    /* show all sessions */
    for(int j=0;j<ns;j++){char ht[48];ts_human(ss[j].ts,ht,48);
        if(ss[j].wd[0])printf("  \033[33msess\033[0m  %s  cd %s && claude -r %s\n",ht,ss[j].wd,ss[j].sid);
        else printf("  \033[33msess\033[0m  %s  claude -r %s\n",ht,ss[j].sid);}
}
static void task_repri(int x,int pv){
    if(pv<0)pv=0;if(pv>99999)pv=99999;char np[8];snprintf(np,8,"%05d",pv);
    char*bn=strrchr(T[x].d,'/');if(!bn)return;bn++;char nw[P];
    if(strlen(bn)>5&&bn[5]=='-'&&isdigit(bn[0]))snprintf(nw,P,"%s-%s",np,bn+6);else snprintf(nw,P,"%s-%s",np,bn);
    char dst[P];snprintf(dst,P,"%.*s/%s",(int)(bn-1-T[x].d),T[x].d,nw);
    rename(T[x].d,dst);printf("\xe2\x9c\x93 P%s %.40s\n",np,T[x].t);
}
static int task_getkey(void){
    struct termios old,raw;tcgetattr(0,&old);raw=old;
    raw.c_lflag&=~(tcflag_t)(ICANON|ECHO);raw.c_cc[VMIN]=1;raw.c_cc[VTIME]=0;
    tcsetattr(0,TCSAFLUSH,&raw);int c=getchar();tcsetattr(0,TCSAFLUSH,&old);return c;
}
static int cmd_task(int argc,char**argv){
    perf_disarm();
    char dir[P];snprintf(dir,P,"%s/tasks",SROOT);mkdirp(dir);const char*sub=argc>2?argv[2]:NULL;
    if(!sub||!strcmp(sub,"v")||!strcmp(sub,"vision")){
        char vf[P];snprintf(vf,P,"%s/vision.txt",SROOT);
        size_t vl;char*vc=readf(vf,&vl);
        static const char*vk[]={"Focus","Saves","Daily"};
        kvs_t vkv=vc?kvparse(vc):(kvs_t){.n=0};if(vc)free(vc);
        printf("\033[1m\xe2\x94\x81\xe2\x94\x81\xe2\x94\x81 Vision\033[0m");
        if(vkv.n){struct stat vs;if(!stat(vf,&vs)){char vd[16];strftime(vd,16,"%b %d",localtime(&vs.st_mtime));printf(" \033[90m(%s)\033[0m",vd);}}
        putchar('\n');
        for(int j=0;j<3;j++){const char*v=kvget(&vkv,vk[j]);printf("  \033[1m%-6s\033[0m %s\n",vk[j],v?v:"\033[90m-\033[0m");}
        if(sub){/* a task v — edit vision fields */
            printf("\n");for(int j=0;j<3;j++){const char*v=kvget(&vkv,vk[j]);
                printf("  %s [%s]: ",vk[j],v?v:"");fflush(stdout);
                char lb[512];if(fgets(lb,512,stdin)&&lb[0]!='\n'){lb[strcspn(lb,"\n")]=0;
                    int found=0;for(int k=0;k<vkv.n;k++)if(!strcmp(vkv.i[k].k,vk[j])){snprintf(vkv.i[k].v,512,"%s",lb);found=1;break;}
                    if(!found&&vkv.n<16){snprintf(vkv.i[vkv.n].k,32,"%s",vk[j]);snprintf(vkv.i[vkv.n].v,512,"%s",lb);vkv.n++;}}}
            char wb[B]="";int wl=0;for(int j=0;j<vkv.n;j++)wl+=snprintf(wb+wl,(size_t)(B-wl),"%s: %s\n",vkv.i[j].k,vkv.i[j].v);
            writef(vf,wb);sync_bg();puts("\xe2\x9c\x93");return 0;}
        /* show top task + scream */
        int n=load_tasks(dir);
        if(n){printf("\n\033[1m\xe2\x94\x81\xe2\x94\x81\xe2\x94\x81 #1 [P%s] %.50s\033[0m\n",T[0].p,T[0].t);
            struct stat ts;if(!stat(T[0].d,&ts)){int age=(int)((time(NULL)-ts.st_mtime)/86400);if(age>0)printf("  \033[90m%dd stale\033[0m\n",age);}}
        if(!isatty(STDIN_FILENO))return 0;
        printf("\n  Scream or [enter]work on #1: ");fflush(stdout);
        char sb[B];if(fgets(sb,B,stdin)&&sb[0]!='\n'){sb[strcspn(sb,"\n")]=0;
            task_add(dir,sb,100);printf("\xe2\x9c\x93 P00100 %s\n",sb);sync_bg();}
        else if(n){sub="1";}
        else return 0;}
    int grn=0;
    if(!strcmp(sub,"help")||!strcmp(sub,"-h")||!strcmp(sub,"h")){
        puts("  a task          vision + scream + #1\n  a task v        edit vision\n  a task l        list\n  a task r        review (navigate)\n  a task rank     reprioritize walk-through\n  a task add <t>  add (prefix 5-digit pri)\n  a task d #      archive\n  a task pri # N  set priority\n  a task flag     AI triage\n  a task deadline # MM-DD\n  a task due      by deadline\n  a task sync     sync");
        return 0;}
    if(!strcmp(sub,"rank")){int n=load_tasks(dir);if(!n){puts("No tasks");return 0;}
        int changed=0;
        for(int i=0;i<n;i++){
            printf("  %d/%d [P%s] %.60s  pri (enter=keep): ",i+1,n,T[i].p,T[i].t);fflush(stdout);
            char buf[16];if(!fgets(buf,16,stdin)||buf[0]=='q')break;
            if(buf[0]!='\n'){int pv=atoi(buf);if(pv>0){task_repri(i,pv);changed=1;}}
        }if(changed){sync_bg();n=load_tasks(dir);puts("\nNew order:");
            for(int i=0;i<n;i++)printf("  %d. P%s %.50s\n",i+1,T[i].p,T[i].t);}
        return 0;}
    if(*sub=='l'){int n=load_tasks(dir);if(!n){puts("No tasks");return 0;}
        for(int i=0;i<n;i++){char ct[256];task_counts(T[i].d,ct,256);
            printf("  %d. P%s %.50s%s\n",i+1,T[i].p,T[i].t,ct);}return 0;}
    if(0){review:;} /* due r jumps here with T[] pre-loaded */
    if(grn||isdigit(*sub)||!strcmp(sub,"rev")||!strcmp(sub,"review")||!strcmp(sub,"r")||!strcmp(sub,"t")){
        int n=grn?grn:load_tasks(dir);if(!n){puts("No tasks");return 0;}
        {int i=isdigit(*sub)?atoi(sub)-1:argc>3?atoi(argv[3])-1:0;if(i<0||i>=n)i=0;int show=1;
        while(i<n){if(show)task_show(i,n);show=1;
            printf("\n  [e]archive [a]dd [c]prompt [r]un [g]o [d]eadline [p]ri [/]search  [j]next [k]back [q]uit  ");fflush(stdout);
            int k=task_getkey();putchar('\n');
            if(k=='e'){do_archive(T[i].d);printf("\xe2\x9c\x93 Archived: %.40s\n",T[i].t);
                sync_bg();n=load_tasks(dir);if(i>=n)i=n-1;if(i<0)break;}
            else if(k=='a'){
                {struct stat st;if(!stat(T[i].d,&st)&&!S_ISDIR(st.st_mode))task_todir(T[i].d);}
                char sd[P];snprintf(sd,P,"%s/task",T[i].d);
                printf("  Text: ");fflush(stdout);
                char buf[B];if(fgets(buf,B,stdin)){buf[strcspn(buf,"\n")]=0;if(buf[0]){
                    mkdir(sd,0755);
                    struct timespec tp;clock_gettime(CLOCK_REALTIME,&tp);
                    char ts[32],fn[P];strftime(ts,32,"%Y%m%dT%H%M%S",localtime(&tp.tv_sec));
                    snprintf(fn,P,"%s/%s.%09ld_%s.txt",sd,ts,tp.tv_nsec,DEV);
                    char fb[B];snprintf(fb,B,"Text: %s\nDevice: %s\nCreated: %s\n",buf,DEV,ts);writef(fn,fb);
                    printf("\xe2\x9c\x93 Added\n");sync_bg();}}
                /* re-show task so new addition is visible */
                task_show(i,n);show=0;}
            else if(k=='c'){docreate:
                {struct stat st;if(!stat(T[i].d,&st)&&!S_ISDIR(st.st_mode))task_todir(T[i].d);}
                printf("  Name: ");fflush(stdout);
                char nm[64];if(!fgets(nm,64,stdin)||!nm[0]||nm[0]=='\n'){show=0;continue;}
                nm[strcspn(nm,"\n")]=0;
                printf("  Prompt text: ");fflush(stdout);
                char pt[B];if(!fgets(pt,B,stdin)||!pt[0]||pt[0]=='\n'){show=0;continue;}
                pt[strcspn(pt,"\n")]=0;
                printf("  Folder [cwd]: ");fflush(stdout);
                char fd[P];if(!fgets(fd,P,stdin))fd[0]=0;fd[strcspn(fd,"\n")]=0;
                if(!fd[0])(void)!getcwd(fd,P);
                printf("  Model [opus]: ");fflush(stdout);
                char md[64];if(!fgets(md,64,stdin))md[0]=0;md[strcspn(md,"\n")]=0;
                if(!md[0])snprintf(md,64,"opus");
                char pd[P];snprintf(pd,P,"%s/prompt_%s",T[i].d,nm);mkdir(pd,0755);
                char pf[P];
                snprintf(pf,P,"%s/prompt.txt",pd);writef(pf,pt);
                snprintf(pf,P,"%s/folder.txt",pd);writef(pf,fd);
                snprintf(pf,P,"%s/model.txt",pd);writef(pf,md);
                printf("\xe2\x9c\x93 Added prompt: %s\n",nm);
                task_show(i,n);show=0;}
            else if(k=='r'){
                printf("  Prompt # or [n]ew: ");fflush(stdout);
                char pb[8];if(!fgets(pb,8,stdin)||!pb[0]||pb[0]=='\n'){show=0;continue;}
                pb[strcspn(pb,"\n")]=0;
                if(*pb=='n'||*pb=='c')goto docreate;
                int ci=atoi(pb);if(ci<1){show=0;continue;}
                /* collect task text */
                char body[B]="";int bl=0;
                struct stat ss;if(!stat(T[i].d,&ss)&&S_ISDIR(ss.st_mode)){
                    DIR*dd=opendir(T[i].d);struct dirent*ee;
                    while(dd&&(ee=readdir(dd))){if(ee->d_name[0]=='.')continue;
                        char fp[P];snprintf(fp,P,"%s/%s",T[i].d,ee->d_name);
                        if(ee->d_type==DT_REG&&strstr(ee->d_name,".txt")&&!strstr(ee->d_name,"session")&&!strstr(ee->d_name,"prompt_")){
                            size_t fl;char*fc=readf(fp,&fl);if(fc){bl+=snprintf(body+bl,(size_t)(B-bl),"%s\n",fc);free(fc);}}
                        else if(ee->d_type==DT_DIR&&strncmp(ee->d_name,"prompt_",7)){DIR*sd=opendir(fp);struct dirent*ff;
                            while(sd&&(ff=readdir(sd))){if(ff->d_type!=DT_REG||!strstr(ff->d_name,".txt"))continue;
                                char sfp[P];snprintf(sfp,P,"%s/%s",fp,ff->d_name);
                                size_t fl;char*fc=readf(sfp,&fl);if(fc){bl+=snprintf(body+bl,(size_t)(B-bl),"%s\n",fc);free(fc);}}
                            if(sd)closedir(sd);}}
                    if(dd)closedir(dd);
                }else{snprintf(body,B,"%s",T[i].t);}
                /* build prompt from candidate */
                char prompt[B],pmodel[64]="opus",pfolder[P]="";
                (void)!getcwd(pfolder,P);
                if(ci==1){snprintf(prompt,B,"%s",body);}
                else{int cp=2;DIR*pd=opendir(T[i].d);struct dirent*pe;int found=0;
                    while(pd&&(pe=readdir(pd))){
                        if(strncmp(pe->d_name,"prompt_",7))continue;
                        char pp[P];snprintf(pp,P,"%s/%s",T[i].d,pe->d_name);
                        struct stat ps;if(stat(pp,&ps))continue;
                        if(S_ISDIR(ps.st_mode)){
                            if(cp==ci){char cfp[P];
                                snprintf(cfp,P,"%s/prompt.txt",pp);
                                size_t cl;char*cc=readf(cfp,&cl);
                                if(cc){snprintf(prompt,B,"%s",cc);free(cc);found=1;}
                                snprintf(cfp,P,"%s/model.txt",pp);cc=readf(cfp,&cl);
                                if(cc){snprintf(pmodel,64,"%s",cc);pmodel[strcspn(pmodel,"\n")]=0;free(cc);}
                                snprintf(cfp,P,"%s/folder.txt",pp);cc=readf(cfp,&cl);
                                if(cc){snprintf(pfolder,P,"%s",cc);pfolder[strcspn(pfolder,"\n")]=0;free(cc);}
                                break;}
                        }else if(S_ISREG(ps.st_mode)){
                            if(cp==ci){size_t cl;char*cc=readf(pp,&cl);
                                if(cc){snprintf(prompt,B,"%s",cc);free(cc);found=1;}
                                break;}
                        }else continue;
                        cp++;}
                    if(pd)closedir(pd);
                    if(!found){printf("  x Invalid prompt #\n");show=0;continue;}}
                /* hand off to a job */
                {char pf[P];snprintf(pf,P,"%s/a_task_%d.txt",TMP,(int)getpid());writef(pf,prompt);
                char cmd[B];snprintf(cmd,B,"a job '%s' --prompt-file '%s' --no-worktree --model %s --bg",pfolder,pf,pmodel);
                (void)!system(cmd);}show=0;}
            else if(k=='g'){
                /* go: attach most recent live, or resume most recent dead */
                Sess ss[32];int ns=load_sessions(T[i].d,ss,32);
                if(!ns){printf("  Not run yet. Press [r] to run with claude.\n");show=0;}
                else{/* pick most recent live, else most recent review (last in sorted list) */
                    int pick=-1;
                    for(int j=ns-1;j>=0;j--)if(ss[j].st==1){pick=j;break;}
                    if(pick<0)pick=ns-1;
                    if(ss[pick].st==1){char cmd[P];snprintf(cmd,P,"tmux attach -t '%s'",ss[pick].tmx);
                        (void)!system(cmd);}
                    else{char cmd[P];snprintf(cmd,P,"claude -r %s",ss[pick].sid);
                        printf("  Resuming claude session...\n");(void)!system(cmd);}
                    show=0;}}
            else if(k=='p'){printf("  Priority (1-99999): ");fflush(stdout);
                char buf[16];if(fgets(buf,16,stdin)){task_repri(i,atoi(buf));sync_bg();n=load_tasks(dir);}}
            else if(k=='d'){
                {struct stat st;if(!stat(T[i].d,&st)&&!S_ISDIR(st.st_mode))task_todir(T[i].d);}
                printf("  Deadline (MM-DD [HH:MM]): ");fflush(stdout);
                char db[32];if(fgets(db,32,stdin)&&db[0]&&db[0]!='\n'){db[strcspn(db,"\n")]=0;
                    char dn[32];dl_norm(db,dn,32);
                    char df[P];snprintf(df,P,"%s/deadline.txt",T[i].d);writef(df,dn);printf("\xe2\x9c\x93 %s\n",dn);sync_bg();}
                task_show(i,n);show=0;}
            else if(k=='/'||k=='s'){printf("  Search: ");fflush(stdout);
                char q[128];if(!fgets(q,128,stdin)||q[0]=='\n'){show=0;continue;}q[strcspn(q,"\n")]=0;
                int mx[256],nm=0;for(int j=0;j<n&&nm<256;j++){
                    if(strcasestr(T[j].t,q)){mx[nm++]=j;continue;}
                    struct stat ss;if(stat(T[j].d,&ss))continue;
                    if(!S_ISDIR(ss.st_mode)){size_t l;char*fc=readf(T[j].d,&l);
                        if(fc){if(strcasestr(fc,q))mx[nm++]=j;free(fc);}continue;}
                    char sd[P];snprintf(sd,P,"%s/task",T[j].d);DIR*dd=opendir(sd);if(!dd)continue;
                    struct dirent*de;int fd=0;while((de=readdir(dd))&&!fd){if(de->d_name[0]=='.'||!strstr(de->d_name,".txt"))continue;
                        char fp[P];snprintf(fp,P,"%s/%s",sd,de->d_name);size_t l;char*fc=readf(fp,&l);
                        if(fc){if(strcasestr(fc,q)){mx[nm++]=j;fd=1;}free(fc);}}closedir(dd);
                }if(!nm){printf("  No match\n");show=0;continue;}
                for(int j=0;j<nm;j++)printf("  %d. [P%s] %.60s\n",j+1,T[mx[j]].p,T[mx[j]].t);
                printf("  Go to (1-%d): ",nm);fflush(stdout);
                char gb[8];if(fgets(gb,8,stdin)&&gb[0]!='\n'){int gi=atoi(gb)-1;if(gi>=0&&gi<nm)i=mx[gi];else show=0;}else show=0;}
            else if(k=='k'){if(i>0)i--;else{printf("  (first task)\n");show=0;}}
            else if(k=='q'||k==3||k==27)break;else if(k=='j')i++;else{show=0;}}
        if(i>=n)puts("Done");return 0;}}
    if(!strcmp(sub,"pri")){if(argc<5){puts("a task pri # N");return 1;}
        int n=load_tasks(dir),x=atoi(argv[3])-1;if(x<0||x>=n){puts("x Invalid");return 1;}
        task_repri(x,atoi(argv[4]));sync_bg();return 0;}
    if(!strcmp(sub,"add")||!strcmp(sub,"a")){if(argc<4){puts("a task add [PPPPP] <text>");return 1;}
        int pri=50000,si=3;
        if(strlen(argv[3])==5&&isdigit(argv[3][0])&&isdigit(argv[3][1])&&isdigit(argv[3][2])&&isdigit(argv[3][3])&&isdigit(argv[3][4])){
            pri=atoi(argv[3]);si=4;if(si>=argc){puts("a task add [PPPPP] <text>");return 1;}}
        char t[B]="";for(int i=si,l=0;i<argc;i++) l+=snprintf(t+l,(size_t)(B-l),"%s%s",i>si?" ":"",argv[i]);
        task_add(dir,t,pri);printf("\xe2\x9c\x93 P%05d %s\n",pri,t);sync_bg();return 0;}
    if(*sub=='d'&&!sub[1]){if(argc<4){puts("a task d <#|name>...");return 1;}int n=load_tasks(dir);
        for(int j=3;j<argc;j++){int x=-1,v=atoi(argv[j]);if(v>0&&v<=n)x=v-1;
            else{for(int i=0;i<n;i++){char*b=strrchr(T[i].d,'/');if(b&&!strcmp(b+1,argv[j])){x=i;break;}}}
            if(x<0||x>=n){printf("x %s\n",argv[j]);continue;}do_archive(T[x].d);printf("\xe2\x9c\x93 %.40s\n",T[x].t);}
        sync_bg();return 0;}
    if(!strcmp(sub,"deadline")){if(argc<5){puts("a task deadline # MM-DD [HH:MM]");return 1;}
        int n=load_tasks(dir),x=atoi(argv[3])-1;if(x<0||x>=n){puts("x Invalid");return 1;}
        char raw[64]="";for(int j=4,l=0;j<argc;j++) l+=snprintf(raw+l,(size_t)(64-l),"%s%s",j>4?" ":"",argv[j]);
        char dn[32];dl_norm(raw,dn,32);
        char df[P];snprintf(df,P,"%s/deadline.txt",T[x].d);writef(df,dn);printf("\xe2\x9c\x93 %s\n",dn);sync_bg();return 0;}
    if(!strcmp(sub,"due")){int n=load_tasks(dir);if(!n){puts("No tasks");return 0;}
        int ix[256];int dl[256];int nd=0;
        for(int i=0;i<n;i++){int d=task_dl(T[i].d);if(d>=0){ix[nd]=i;dl[nd]=d;nd++;}}
        if(!nd){puts("No deadlines");return 0;}
        for(int a=0;a<nd-1;a++)for(int b=a+1;b<nd;b++)if(dl[a]>dl[b]){int t=ix[a];ix[a]=ix[b];ix[b]=t;t=dl[a];dl[a]=dl[b];dl[b]=t;}
        Tk D[256];for(int j=0;j<nd;j++)D[j]=T[ix[j]];memcpy(T,D,(size_t)nd*sizeof(Tk));
        if(argc>3&&(*argv[3]=='r'||*argv[3]=='t')){sub="r";grn=nd;goto review;}
        for(int j=0;j<nd;j++)printf("  %s%dd\033[0m P%s %.50s\n",dl[j]<=1?"\033[31m":dl[j]<=7?"\033[33m":"\033[90m",dl[j],T[j].p,T[j].t);return 0;}
    if(!strcmp(sub,"bench")){struct timespec t0,t1;
        clock_gettime(CLOCK_MONOTONIC,&t0);int n=0;for(int j=0;j<100;j++)n=load_tasks(dir);
        clock_gettime(CLOCK_MONOTONIC,&t1);
        printf("load_tasks(%d): %.0f us avg (x100)\n",n,((double)(t1.tv_sec-t0.tv_sec)*1e9+(double)(t1.tv_nsec-t0.tv_nsec))/100/1e3);
        fflush(stdout);int fd=dup(1);(void)!freopen("/dev/null","w",stdout);
        int m=n<10?n:10;
        clock_gettime(CLOCK_MONOTONIC,&t0);for(int j=0;j<m;j++)task_show(j,n);
        clock_gettime(CLOCK_MONOTONIC,&t1);fflush(stdout);dup2(fd,1);close(fd);stdout=fdopen(1,"w");
        double us=((double)(t1.tv_sec-t0.tv_sec)*1e9+(double)(t1.tv_nsec-t0.tv_nsec))/1e3;
        printf("task_show(x%d): %.0f us total, %.0f us/task\n",m,us,us/m);
        return 0;}
    if(!strcmp(sub,"sync")){sync_repo();puts("\xe2\x9c\x93");return 0;}
    if(!strcmp(sub,"flag")||!strcmp(sub,"f")){int n=load_tasks(dir);if(!n){puts("No tasks");return 0;}
        char tf[P];snprintf(tf,P,"%s/a_flag_%d.txt",TMP,(int)getpid());
        FILE*fp=fopen(tf,"w");if(!fp)return 1;
        fprintf(fp,"Help me clean up my task list. Identify tasks to archive (duplicate, done, vague, obsolete).\n"
            "Ask me to confirm each batch. For confirmed tasks run: a task d <dirname> <dirname>...\n"
            "Use directory names (in brackets) as stable IDs. Multiple can be deleted in one command.\n"
            "Go in batches of ~10. Only archive what I approve.\n\n"
            "COMMANDS: a task d <dirname>... (archive) | a task pri # N (reprioritize) | a task sync\n\nTASK LIST:\n");
        for(int i=0;i<n;i++){char ft[B]="",td[P];snprintf(td,P,"%s/task",T[i].d);
            DIR*dd=opendir(td);if(dd){struct dirent*de;
                while((de=readdir(dd))){if(de->d_name[0]!='.'){ char fp2[P];snprintf(fp2,P,"%s/%s",td,de->d_name);
                    char*c=readf(fp2,NULL);if(c){if(!strncmp(c,"Text: ",6)){char*nl=strchr(c+6,'\n');if(nl)*nl=0;snprintf(ft,B,"%s",c+6);}free(c);break;}}}
                closedir(dd);}
            char*bn=strrchr(T[i].d,'/');fprintf(fp,"  %d. P%s %s [%s]\n",i+1,T[i].p,ft[0]?ft:T[i].t,bn?bn+1:"?");}
        fclose(fp);printf("Task list: %s (%d tasks)\n",tf,n);
        char pr[256];snprintf(pr,256,"Read %s and follow the instructions to help me triage tasks.",tf);
        execvp("a",(char*[]){"a","c",pr,NULL});return 1;}
    if(!strcmp(sub,"0")||!strcmp(sub,"s")||!strcmp(sub,"p")||!strcmp(sub,"do")){
        const char*x=*sub=='0'?"priority":!strcmp(sub,"s")?"suggest":!strcmp(sub,"p")?"plan":"do";
        char cmd[64];snprintf(cmd,64,"x.%s",x);execvp("a",(char*[]){"a",cmd,NULL});return 1;}
    if(*sub=='1'){char pf[P];snprintf(pf,P,"%s/common/prompts/task1.txt",SROOT);
        size_t l;char*r=readf(pf,&l);if(!r){printf("x No prompt: %s\n",pf);return 1;}
        while(l>0&&(r[l-1]=='\n'||r[l-1]==' '))r[--l]=0;
        printf("Prompt: %s\n",pf);execvp("a",(char*[]){"a","c",r,NULL});return 1;}
    if(argc>4&&isdigit(argv[3][0])){
        int n=load_tasks(dir),x=atoi(argv[3])-1;
        if(x>=0&&x<n){
        {struct stat st;if(!stat(T[x].d,&st)&&!S_ISDIR(st.st_mode))task_todir(T[x].d);}
        char sd[P];snprintf(sd,P,"%s/%s",T[x].d,sub);mkdirp(sd);
        struct timespec tp;clock_gettime(CLOCK_REALTIME,&tp);
        char ts[32],fn[P];strftime(ts,32,"%Y%m%dT%H%M%S",localtime(&tp.tv_sec));
        char t[B]="";for(int i=4,l=0;i<argc;i++) l+=snprintf(t+l,(size_t)(B-l),"%s%s",i>4?" ":"",argv[i]);
        snprintf(fn,P,"%s/%s.%09ld_%s.txt",sd,ts,tp.tv_nsec,DEV);writef(fn,t);
        printf("\xe2\x9c\x93 %s: %.40s\n",sub,t);sync_bg();return 0;}}
    {int pri=50000,si=2;
    if(argc>2&&strlen(argv[2])==5&&isdigit(argv[2][0])&&isdigit(argv[2][1])&&isdigit(argv[2][2])&&isdigit(argv[2][3])&&isdigit(argv[2][4])){
        pri=atoi(argv[2]);si=3;if(si>=argc){puts("a task [PPPPP] <text>");return 1;}}
    char t[B]="";for(int i=si,l=0;i<argc;i++) l+=snprintf(t+l,(size_t)(B-l),"%s%s",i>si?" ":"",argv[i]);
    task_add(dir,t,pri);printf("\xe2\x9c\x93 P%05d %s\n",pri,t);sync_bg();return 0;}
}
