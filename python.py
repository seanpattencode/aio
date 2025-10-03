import subprocess as s

import time
run = lambda n, c: s.run(f'tmux new-session -d -s {n} "{c}"', shell=True)
status = lambda: s.run('tmux ls', shell=True, capture_output=True, text=True).stdout
send = lambda n, c: s.run(f'tmux send-keys -t {n} "{c}" Enter', shell=True)
sendkey = lambda n, k: s.run(f'tmux send-keys -t {n} {k}', shell=True)
attach = lambda n: s.run(f'tmux attach -t {n}', shell=True)
kill = lambda n: s.run(f'tmux kill-session -t {n}', shell=True, stderr=s.DEVNULL)
capture = lambda n: s.run(f'tmux capture-pane -t {n} -p', shell=True, capture_output=True, text=True).stdout
demo = lambda: (print("Starting parallel demo"), kill("aios-demo-1"), kill("aios-demo-2"), run("aios-demo-1", "bash --norc --noprofile"), run("aios-demo-2", "bash --norc --noprofile"), send("aios-demo-1", r'codex exec -c model_reasoning_effort=\"high\" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox -- \"count to 3\"'), send("aios-demo-2", r'codex exec -c model_reasoning_effort=\"high\" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox -- \"count to 3\"'), time.sleep(10), print(f"\naios-demo-1:\n{capture('aios-demo-1')}"), print(f"\naios-demo-2:\n{capture('aios-demo-2')}"))

__name__ == "__main__" and demo()
