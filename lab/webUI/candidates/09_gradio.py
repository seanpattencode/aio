import gradio as gr, subprocess, time
def run(cmd):
    s = time.time(); out = subprocess.getoutput(f"source ~/.bashrc 2>/dev/null && {cmd}")
    return out, f"{time.time()-s}s"
gr.Interface(run, "text", ["text", "text"], examples=[["ls"]]).launch()
