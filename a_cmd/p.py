"""aio p - List projects"""
from . _common import init_db, list_all

def run():
    init_db()
    list_all()
