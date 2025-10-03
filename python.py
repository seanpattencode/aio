import subprocess as s
from datetime import datetime
from time import sleep

run = lambda n, c: s.run(f'tmux new-session -d -s {n} "{c}"', shell=True)
status = lambda: s.run('tmux ls', shell=True, capture_output=True, text=True).stdout
send = lambda n, c: s.run(f'tmux send-keys -t {n} "{c}" Enter', shell=True)
sendkey = lambda n, k: s.run(f'tmux send-keys -t {n} {k}', shell=True)
attach = lambda n: s.run(f'tmux attach -t {n}', shell=True)
kill = lambda n: s.run(f'tmux kill-session -t {n}', shell=True, stderr=s.DEVNULL)
capture = lambda n: s.run(f'tmux capture-pane -t {n} -p', shell=True, capture_output=True, text=True).stdout
demo = lambda: (print("Starting parallel demo"), (d1 := datetime.now().strftime("%Y%m%d_%H%M%S_1"), d2 := datetime.now().strftime("%Y%m%d_%H%M%S_2")), kill("aios-demo-1"), kill("aios-demo-2"), run("aios-demo-1", "bash --norc --noprofile"), run("aios-demo-2", "bash --norc --noprofile"), send("aios-demo-1", f"mkdir -p {d1} && cd {d1}"), send("aios-demo-2", f"mkdir -p {d2} && cd {d2}"), sleep(1), send("aios-demo-1", r'codex exec -c model_reasoning_effort=\"high\" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox -- \"create a python program that factors prime numbers in 10 lines or less, save it to factor.py\"'), send("aios-demo-2", r'codex exec -c model_reasoning_effort=\"high\" --model gpt-5-codex --dangerously-bypass-approvals-and-sandbox -- \"create a python program that factors prime numbers in 10 lines or less, save it to factor.py\"'), sleep(15), send("aios-demo-1", "echo 'Input: 84' > output.txt && echo 84 | python factor.py >> output.txt"), send("aios-demo-2", "echo 'Input: 84' > output.txt && python factor.py 84 >> output.txt"), sleep(2), print(f"\naios-demo-1:\n{capture('aios-demo-1')}"), print(f"\naios-demo-2:\n{capture('aios-demo-2')}"))

__name__ == "__main__" and demo()
