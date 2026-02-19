#!/usr/bin/env python3
import sys,os,subprocess as s;sys.exit("usage: evo.py <prompt|file> <message>")if len(sys.argv)<3 else 0;p=sys.argv[1];sp=open(p).read()if os.path.isfile(p)else p;e={k:v for k,v in os.environ.items()if k!="CLAUDECODE"};print(s.run(["claude","-p","--system-prompt",sp," ".join(sys.argv[2:])],capture_output=True,text=True,env=e).stdout,end="")
