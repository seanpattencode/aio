import sys;from _common import SYNC_ROOT as S;K=dict(l.split('=',1)for l in(S/'login'/'api_keys.env').read_text().splitlines()if'='in l)
def run():p=' '.join(sys.argv[2:]);p and print(__import__('anthropic').Anthropic(api_key=K['ANTHROPIC_API_KEY']).messages.create(model='claude-opus-4-5-20251101',max_tokens=99,messages=[{'role':'user','content':p}]).content[0].text)
run()
