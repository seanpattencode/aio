/* ── cal ── */
static int cmd_cal(int c,char**v){
    char dir[P],tf[P];snprintf(dir,P,"%s/cal",SROOT);mkdirp(dir);
    char ps[64][P];int n=listdir(dir,ps,64);
    {struct timespec ts;clock_gettime(CLOCK_REALTIME,&ts);struct tm*tm=localtime(&ts.tv_sec);
     char tb[32];strftime(tb,32,"%Y%m%dT%H%M%S",tm);snprintf(tf,P,"%s/%s.%09ld_%s.txt",dir,tb,ts.tv_nsec,DEV);}
    char*s=c>2?v[2]:"";
    if(!strcmp(s,"add")){if(c<4){puts("missing event text");return 1;}
        FILE*fp=fopen(tf,"w");if(!fp)return 1;for(int i=3;i<c;i++)fprintf(fp,"%s%s",i>3?" ":"",v[i]);
        fputc('\n',fp);fclose(fp);puts("added");return 0;}
    if(!strcmp(s,"ai")){
        char ex[B]="";int el=0;
        for(int i=0;i<n&&el<B-256;i++){FILE*f=fopen(ps[i],"r");if(f){el+=(int)fread(ex+el,1,(size_t)(B-256-el),f);fclose(f);}}
        char pr[B];int pl=0;
        if(c<4)snprintf(pr,B,"Ask the user what they want to add or change in their calendar.");
        else for(int i=3;i<c;i++)pl+=snprintf(pr+pl,(size_t)(B-pl),"%s%s",i>3?" ":"",v[i]);
        time_t now=time(NULL);struct tm*t=localtime(&now);char td[11];strftime(td,11,"%Y-%m-%d",t);
        char pm[B*2];snprintf(pm,sizeof(pm),"Today is %s. Calendar dir: %s\nWrite to: %s\nAll events:\n%s\n\nUser request: %s\n\nAdd events as lines: YYYY-MM-DD HH:MM description. Append to the write file.",td,dir,tf,ex[0]?ex:"(empty)",pr);
        perf_disarm();execlp("a","a","c",pm,(char*)NULL);return 0;}
    if(*s){char f[P];snprintf(f,P,"%s/%s%s",dir,s,strchr(s,'.')?""  :".txt");
        int fd=open(f,O_CREAT|O_WRONLY|O_APPEND,0644);if(fd>=0)close(fd);execlp("e","e",f,(char*)NULL);return 0;}
    typedef struct{char l[256];}E;E evs[256];int ne=0;
    for(int i=0;i<n;i++){FILE*f=fopen(ps[i],"r");if(!f)continue;char ln[256];
        while(fgets(ln,256,f)&&ne<256)if(ln[0]>='2'&&ln[4]=='-'&&ln[7]=='-'){ln[strcspn(ln,"\n")]=0;snprintf(evs[ne++].l,256,"%s",ln);}fclose(f);}
    for(int i=0;i<ne-1;i++)for(int j=i+1;j<ne;j++)if(strcmp(evs[i].l,evs[j].l)>0){E t=evs[i];evs[i]=evs[j];evs[j]=t;}
    for(int i=0;i<ne;i++)puts(evs[i].l);if(!ne)puts("no events");
    printf("\n%s/\n",dir);for(int i=0;i<n;i++)printf("  %s\n",bname(ps[i]));
    puts("\nusage:\n  a cal add \"2026-03-06 09:00 standup\"\n  a cal ai <prompt> ai-assisted add\n  a cal <name>      edit file");
    return 0;
}
