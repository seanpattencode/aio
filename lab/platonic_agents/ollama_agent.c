#if 0
cc -O2 -w -o "${0%.c}" "$0" && echo "built ${0%.c}" && exit 0
exit 1
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define B 65536
static char *mem[40];static int nm;
static void madd(const char *r,const char *c){if(nm>=40){free(mem[0]);free(mem[1]);memmove(mem,mem+2,38*sizeof(char*));nm-=2;}mem[nm++]=strdup(r);mem[nm++]=strdup(c);}
static char *jesc(const char *s,char *o){char *p=o;for(;*s;s++){if(*s=='"'||*s=='\\'){*p++='\\';*p++=*s;}else if(*s=='\n'){*p++='\\';*p++='n';}else if((unsigned char)*s>=0x20)*p++=*s;}*p=0;return o;}
static char *chat(const char *mdl){
    static char body[B],resp[B],esc[B];
    int n=snprintf(body,B,"{\"model\":\"%s\",\"stream\":false,\"messages\":[{\"role\":\"system\",\"content\":\"Linux CLI. ENTIRE reply: CMD: <cmd>. After output, plain text.\"},",mdl);
    for(int i=0;i<nm;i+=2)n+=snprintf(body+n,B-n,"{\"role\":\"%s\",\"content\":\"%s\"},",mem[i],jesc(mem[i+1],esc));
    if(body[n-1]==',')n--;snprintf(body+n,B-n,"]}");
    FILE *tmp=fopen("/tmp/.ob","w");if(!tmp)return 0;fputs(body,tmp);fclose(tmp);
    FILE *f=popen("curl -s http://localhost:11434/api/chat -d @/tmp/.ob","r");if(!f)return 0;
    int len=fread(resp,1,B-1,f);resp[len]=0;pclose(f);
    char *p=strstr(resp,"\"content\":\"");if(!p)return 0;p+=11;
    char *w=resp;for(;*p&&!(*p=='"'&&*(p-1)!='\\');p++){if(*p=='\\'&&p[1]=='n'){*w++='\n';p++;}else if(*p=='\\'&&p[1]=='"'){*w++='"';p++;}else if(*p=='\\'&&p[1]=='\\'){*w++='\\';p++;}else *w++=*p;}
    *w=0;p=resp;while(*p==' '||*p=='\n')p++;return strdup(p);
}
int main(int c,char **v){
    const char *mdl=c>1?v[1]:"mistral";char in[B],out[B];
    for(;;){printf("\n> ");fflush(stdout);if(!fgets(in,B,stdin))break;in[strcspn(in,"\n")]=0;if(!*in)continue;madd("user",in);
        for(int i=0;i<5;i++){char *t=chat(mdl);if(!t){puts("(err)");break;}
            char *cp=strstr(t,"CMD:");if(!cp){puts(t);madd("assistant",t);free(t);break;}
            char *cmd=cp+4;while(*cmd==' '||*cmd=='`')cmd++;char *nl=strchr(cmd,'\n');if(nl)*nl=0;{char *e=cmd+strlen(cmd)-1;while(e>cmd&&*e=='`')*e--=0;}
            printf("$ %s\n",cmd);madd("assistant",t);
            FILE *p=popen(cmd,"r");int len=p?fread(out,1,B-1,p):0;if(p)pclose(p);out[len]=0;if(!*out)strcpy(out,"(no output)");printf("%s",out);
            char fb[B];snprintf(fb,B,"`%s`:\n%s",cmd,out);madd("user",fb);free(t);}}
}
