import sys, os
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for d in ('lib', 'agents'):
    p = os.path.join(_root, d)
    if p not in sys.path: sys.path.insert(0, p)
from hub import run; run()
