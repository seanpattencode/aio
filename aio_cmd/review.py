"""aio review - Show GitHub PRs"""
import os
def run():
    os.system("gh search prs --author @me --state open")
