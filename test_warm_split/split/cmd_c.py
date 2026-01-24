import re
from pathlib import Path
def run():
    return f"cmd_c: {re.match(r'\\d+', '123').group()} {Path.cwd()}"
