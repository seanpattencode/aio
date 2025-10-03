import subprocess as s

run = lambda n, c: s.run(f'tmux new-session -d -s {n} "{c}"', shell=True)
status = lambda: s.run('tmux ls', shell=True, capture_output=True, text=True).stdout
send = lambda n, c: s.run(f'tmux send-keys -t {n} "{c}" Enter', shell=True)
attach = lambda n: s.run(f'tmux attach -t {n}', shell=True)
demo = lambda: (run("aios-demo-1", "bash"), run("aios-demo-2", "bash"), [send("aios-demo-1", c) for c in ["echo 'Session 1'", "sleep 2 && echo 'Done 1'"]], [send("aios-demo-2", c) for c in ["echo 'Session 2'", "sleep 2 && echo 'Done 2'"]], print("✓ tmux attach -t aios-demo-1\n✓ tmux attach -t aios-demo-2"))

__name__ == "__main__" and demo()
