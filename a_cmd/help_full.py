"""aio help - Show full help"""
from . _common import init_db, list_all, HELP_FULL

def run():
    init_db()
    print(HELP_FULL)
    list_all()
