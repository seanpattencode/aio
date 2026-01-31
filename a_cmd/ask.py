"""a ask <prompt> - query multiple LLMs in parallel"""
import sys,threading,queue;from ._common import SYNC_ROOT
M={'claude':('claude-opus-4-5-20251101','ANTHROPIC_API_KEY',lambda p,k,m:__import__('anthropic').Anthropic(api_key=k).messages.create(model=m,max_tokens=512,messages=[{'role':'user','content':p}]).content[0].text),'gpt':('gpt-5.2','OPENAI_API_KEY',lambda p,k,m:__import__('openai').OpenAI(api_key=k).chat.completions.create(model=m,messages=[{'role':'user','content':p}],max_completion_tokens=512).choices[0].message.content),'gemini':('gemini-3-pro-preview','GOOGLE_API_KEY',lambda p,k,m:(g:=__import__('google.generativeai',fromlist=['genai']),g.configure(api_key=k),g.GenerativeModel(m).generate_content(p).text)[-1])}
def _ask(n,m,f,p,k,q):
    try:q.put((f'{n}({m})',f(p,k,m)))
    except Exception as e:q.put((f'{n}({m})',f'x {e}'))
def run():
    if len(sys.argv)<3:print("usage: a ask <prompt>");return
    p=' '.join(sys.argv[2:]);K=dict(l.split('=',1)for l in(SYNC_ROOT/'login'/'api_keys.env').read_text().splitlines()if'='in l and l[0]!='#')if(SYNC_ROOT/'login'/'api_keys.env').exists()else{};q=queue.Queue()
    T=[threading.Thread(target=_ask,args=(n,m,f,p,K[kn],q))for n,(m,kn,f)in M.items()if K.get(kn)];[t.start()for t in T];[print(f"\n{'='*40}\n{(r:=q.get())[0].upper()}\n{'='*40}\n{r[1][:500]}")for _ in T];[t.join()for t in T]
