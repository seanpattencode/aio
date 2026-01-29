"""aio dir - Show directory"""
import os, subprocess as sp

def run():
    print(f"{os.getcwd()}")
    sp.run(['ls'])
