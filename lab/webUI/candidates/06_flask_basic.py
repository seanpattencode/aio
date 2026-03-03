from flask import Flask, Response; import subprocess, time
app = Flask(__name__)

@app.route('/')
def index():
    return f'''<form method="post"><button name="cmd" value="ls" formaction="/run">Run ls</button></form><pre>{result}</pre>'''

@app.route('/run', methods=['POST'])
def run_ls():
    global result; start = time.time()
    try: out = subprocess.check_output('source ~/.bashrc 2>/dev/null && ls -lart', shell=True).decode()
    except Exception as e: out = str(e)
    end = time.time(); result = f"Execution Time: {end-start:.4f}s\n\n{out}"
    return index()

result = "Click 'Run ls' to execute."
if __name__ == '__main__': app.run(host='0.0.0.0', port=5000)
