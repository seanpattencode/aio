/* ── cal ── */
static int cmd_cal(int c,char**v){
    char dir[P]; snprintf(dir,P,"%s/cal",SROOT); mkdirp(dir);
    if(c>2&&!strcmp(v[2],"add")){
        if(c<4){puts("missing event text");return 1;}
        struct timespec ts;clock_gettime(CLOCK_REALTIME,&ts);struct tm*tm=localtime(&ts.tv_sec);
        char tf[64];strftime(tf,64,"%Y%m%dT%H%M%S",tm);
        char f[P]; snprintf(f,P,"%s/%s.%09ld_%s.txt",dir,tf,ts.tv_nsec,DEV);
        FILE *fp=fopen(f,"w"); if(!fp)return 1;
        for(int i=3;i<c;i++) fprintf(fp,"%s%s",i>3?" ":"",v[i]);
        fputc('\n',fp); fclose(fp); puts("added"); return 0;
    }
    if(c>2&&!strcmp(v[2],"ai")){
        struct timespec ts2;clock_gettime(CLOCK_REALTIME,&ts2);struct tm*tm2=localtime(&ts2.tv_sec);
        char tf2[64];strftime(tf2,64,"%Y%m%dT%H%M%S",tm2);
        char ef[P]; snprintf(ef,P,"%s/%s.%09ld_%s.txt",dir,tf2,ts2.tv_nsec,DEV);
        char existing[B]="";int el=0;
        {char ps[64][P];int np=listdir(dir,ps,64);
        for(int i=0;i<np&&el<B-256;i++){FILE*f2=fopen(ps[i],"r");if(f2){el+=(int)fread(existing+el,1,(size_t)(B-256-el),f2);fclose(f2);}}}
        char pr[B]; int pl=0;
        if(c<4) snprintf(pr,B,"Ask the user what they want to add or change in their calendar.");
        else for(int i=3;i<c;i++) pl+=snprintf(pr+pl,(size_t)(B-pl),"%s%s",i>3?" ":"",v[i]);
        time_t now=time(NULL);struct tm*t=localtime(&now);char today[11];
        strftime(today,11,"%Y-%m-%d",t);
        char prompt[B*2]; snprintf(prompt,sizeof(prompt),
            "Today is %s. Calendar dir: %s\nWrite to: %s\nAll events:\n%s\n\nUser request: %s\n\n"
            "Add events as lines: YYYY-MM-DD HH:MM description. Append to the write file.",
            today,dir,ef,existing[0]?existing:"(empty)",pr);
        perf_disarm();
        execlp("a","a","c",prompt,(char*)NULL); return 0;
    }
    if(c>2){ /* edit/create */
        char f[P]; snprintf(f,P,"%s/%s%s",dir,v[2],strchr(v[2],'.')?""  :".txt");
        int fd=open(f,O_CREAT|O_WRONLY|O_APPEND,0644); if(fd>=0)close(fd);
        execlp("e","e",f,(char*)NULL); return 0;
    }
    /* scan all files for YYYY-MM-DD lines, collect and sort */
    char paths[64][P]; int n=listdir(dir,paths,64);
    typedef struct{char dt[11];char line[256];} ev_t;
    ev_t evs[256]; int ne=0;
    for(int i=0;i<n;i++){
        FILE *f=fopen(paths[i],"r"); if(!f)continue;
        char ln[256];
        while(fgets(ln,256,f)&&ne<256){
            if(ln[0]>='2'&&ln[4]=='-'&&ln[7]=='-'){
                ln[strcspn(ln,"\n")]=0;
                memcpy(evs[ne].dt,ln,10); evs[ne].dt[10]=0;
                snprintf(evs[ne].line,256,"%s",ln); ne++;
            }
        } fclose(f);
    }
    /* sort by date */
    for(int i=0;i<ne-1;i++)for(int j=i+1;j<ne;j++)if(strcmp(evs[i].dt,evs[j].dt)>0){ev_t t=evs[i];evs[i]=evs[j];evs[j]=t;}
    for(int i=0;i<ne;i++) puts(evs[i].line);
    if(!ne) puts("no events");
    printf("\n%s/\n",dir);
    for(int i=0;i<n;i++) printf("  %s\n",bname(paths[i]));
    puts("\nusage:\n  a cal add \"2026-03-06 09:00 standup\"\n  a cal ai <prompt> ai-assisted add\n  a cal <name>      edit file");
    return 0;
}
