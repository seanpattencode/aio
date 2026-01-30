"""Recommend which task should be #1"""
import subprocess,shutil,os

def run():
    gemini=shutil.which('gemini')or os.path.expanduser('~/.local/bin/gemini')
    tasks=subprocess.run(['a','task'],capture_output=True,text=True).stdout.strip()
    subprocess.run([gemini,f'Given these tasks:\n{tasks}\n\nWhich should be #1 priority? Reply: <num>NUMBER</num><why>1 sentence reason</why>'],stderr=subprocess.DEVNULL)
    subprocess.run([gemini,'-c'],stderr=subprocess.DEVNULL)
