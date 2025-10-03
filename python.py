import subprocess as s

import time
run = lambda n, c: s.run(f'tmux new-session -d -s {n} "{c}"', shell=True)
status = lambda: s.run('tmux ls', shell=True, capture_output=True, text=True).stdout
send = lambda n, c: s.run(f'tmux send-keys -t {n} "{c}" Enter', shell=True)
attach = lambda n: s.run(f'tmux attach -t {n}', shell=True)
kill = lambda n: s.run(f'tmux kill-session -t {n}', shell=True, stderr=s.DEVNULL)
capture = lambda n: s.run(f'tmux capture-pane -t {n} -p', shell=True, capture_output=True, text=True).stdout
demo = lambda: (kill("aios-demo-1"), kill("aios-demo-2"), run("aios-demo-1", "bash --norc --noprofile"), run("aios-demo-2", "bash --norc --noprofile"), send("aios-demo-1", "echo 'S1: Step 1' && sleep 1 && echo 'S1: Step 2 complete'"), send("aios-demo-2", "echo 'S2: Step 1' && sleep 1 && echo 'S2: Step 2 complete'"), time.sleep(2), print(f"\naios-demo-1:\n{capture('aios-demo-1')}"), print(f"\naios-demo-2:\n{capture('aios-demo-2')}"))

__name__ == "__main__" and demo()
