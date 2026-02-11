/* a - fast CLI dispatcher. Cat cache in C, exec python3 for commands. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#ifndef SRC
#define SRC "/data/data/com.termux/files/home/projects/a"
#endif

static int cat(const char *p){
	FILE *f=fopen(p,"r"); if(!f)return 1;
	char b[8192]; size_t n;
	while((n=fread(b,1,sizeof b,f)))fwrite(b,1,n,stdout);
	fclose(f); return 0;
}

static _Noreturn void py(int c,char**v){
	setenv("PYTHONPATH",SRC"/lib",1);
	char**a=calloc(c+3,sizeof*a);
	a[0]="python3"; a[1]="-c";
	/* Build: from a_cmd.CMD import run; import sys; sys.argv=ARGV; run() */
	/* Or just run archive/a.py with correct PYTHONPATH already set */
	a[1]=SRC"/lib/a_main.py";
	memcpy(a+2,v+1,(c-1)*sizeof*a);
	execvp("python3",a);
	perror("a"); _exit(1);
}

int main(int c,char**v){
	if(c<2){
		char p[512];
		snprintf(p,sizeof p,"%s/.local/share/a/help_cache.txt",getenv("HOME")?:"/tmp");
		if(!cat(p))return 0;
	}
	py(c,v);
}
