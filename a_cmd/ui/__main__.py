import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__)))); sys.argv = [sys.argv[0], 'ui'] + sys.argv[1:]; from aio_cmd.ui import run; run()
