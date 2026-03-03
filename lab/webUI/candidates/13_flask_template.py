from flask import Flask, request, render_template_string
import subprocess, time, os

app = Flask(__name__)
HTML = '''<form method="post"><input name="cmd" placeholder="Command"><button>Run</button></form>
<pre>{{output}}</pre><button onclick="location.href='/?cmd=ls'">LS</button>
<button onclick="location.href='/?cmd=date'">Time</button>'''

@app.route('/', methods=['GET', 'POST'])
def run():
    cmd = request.args.get('cmd') or (request.form.get('cmd') if request.method == 'POST' else None)
    output = ''
    if cmd:
        start = time.time()
        result = subprocess.run(f"source ~/.bashrc 2>/dev/null && {cmd}", shell=True, capture_output=True, text=True, cwd=os.getcwd())
        output = f'{result.stdout}\n{result.stderr}\nTime: {time.time()-start:.2f}s'
    return render_template_string(HTML, output=output)

if __name__ == '__main__':
    app.run(debug=True)
