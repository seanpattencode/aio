/* ── cal ── */
static int cmd_cal(int c,char**v){
    char d[P],tf[P];snprintf(d,P,"%s/cal",SROOT);mkdirp(d);
    {struct timespec ts;clock_gettime(CLOCK_REALTIME,&ts);struct tm*tm=localtime(&ts.tv_sec);
     char tb[32];strftime(tb,32,"%Y%m%dT%H%M%S",tm);snprintf(tf,P,"%s/%s.%09ld_%s.txt",d,tb,ts.tv_nsec,DEV);}
    char*s=c>2?v[2]:"";
    if(!strcmp(s,"add")){if(c<4){puts("missing event text");return 1;}
        FILE*fp=fopen(tf,"w");if(!fp)return 1;for(int i=3;i<c;i++)fprintf(fp,"%s%s",i>3?" ":"",v[i]);
        fputc('\n',fp);fclose(fp);puts("added");return 0;}
    if(!strcmp(s,"ai")){
        char ex[B]="",pr[B],pm[B*2];int pl=0;{char cm[P];snprintf(cm,P,"cat %s/*.txt 2>/dev/null",d);pcmd(cm,ex,B);}
        if(c<4)snprintf(pr,B,"Ask the user what they want to add or change in their calendar.");
        else for(int i=3;i<c;i++)pl+=snprintf(pr+pl,(size_t)(B-pl),"%s%s",i>3?" ":"",v[i]);
        time_t now=time(NULL);struct tm*t=localtime(&now);char td[11];strftime(td,11,"%Y-%m-%d",t);
        snprintf(pm,sizeof(pm),"Today is %s. Calendar dir: %s\nWrite to: %s\nAll events:\n%s\n\nUser request: %s\n\nAdd events as lines: YYYY-MM-DD HH:MM description. Append to the write file.",td,d,tf,ex[0]?ex:"(empty)",pr);
        perf_disarm();execlp("a","a","c",pm,(char*)NULL);return 0;}
    if(*s){char f[P];snprintf(f,P,"%s/%s%s",d,s,strchr(s,'.')?""  :".txt");
        int fd=open(f,O_CREAT|O_WRONLY|O_APPEND,0644);if(fd>=0)close(fd);execlp("e","e",f,(char*)NULL);return 0;}
    {char cm[B];snprintf(cm,B,"o=$(grep -h '^2...-..-..' '%s'/*.txt 2>/dev/null|sort);[ -n \"$o\" ]&&echo \"$o\"||echo 'no events';echo;echo '%s/';ls '%s'/*.txt 2>/dev/null|xargs -n1 basename|sed 's/^/  /'",d,d,d);system(cm);}
    puts("\nusage:\n  a cal add \"2026-03-06 09:00 standup\"\n  a cal ai <prompt> ai-assisted add\n  a cal <name>      edit file");
    return 0;
}
