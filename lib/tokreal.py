# a tokreal [dir]: repo tokens as Codex (tiktoken o200k_base, free) and Claude = Fable 5 exact id (claude -p usage minus baseline; Haiku 4.5 counts 25% lower; asks first)
import json,sys,subprocess as S,tiktoken
d=sys.argv[-1]if sys.argv[2:]else'.';K=dict(capture_output=1,text=1)
F=S.run(['git','-C',d,'grep','-lI',''],**K).stdout.split();t=''.join(open(d+'/'+f,errors='replace').read()for f in F)
def n(x):
 open('/tmp/tr','w').write(x);r=S.run(['claude','-p','--model','claude-fable-5','--output-format','json','ok']+['--append-system-prompt-file','/tmp/tr']*(x>''),stdin=S.DEVNULL,**K).stdout
 return sum(v for k,v in json.loads(r)[-1]['usage'].items()if'input'in k)
b4=len(t.encode())//4;R=range(0,len(t),300000);print(f'{d}: {len(F)}f b/4 {b4} codex {len(tiktoken.get_encoding("o200k_base").encode(t))}')
if sys.stdin.isatty()and input(f'claude count = {len(R)+1} fable calls through claude -p (the model that reads it), ~{b4} tok of your usage. run? y/N ')=='y':b=n('');print('claude',sum(n(t[i:i+300000])-b for i in R))
