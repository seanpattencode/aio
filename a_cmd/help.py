"""aio (no args) - Show short help"""
from . _common import init_db, list_all, HELP_SHORT

def run():
    init_db()
    print(HELP_SHORT)
    list_all()
