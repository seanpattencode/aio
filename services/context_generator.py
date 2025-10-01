from pathlib import Path
from datetime import datetime
def generate():
    root = Path(__file__).parent.parent
    output = Path(root / "projectContext.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    files = [f for f in root.rglob("*.py")]
    readme = root / "README.md"
    content = f"Generated: {timestamp}\n\n"
    content += "\n".join([f"{f.relative_to(root)}:\n{f.read_text()}\n" for f in files])
    content += {True: "", False: f"\nREADME.md:\n{readme.read_text()}\n"}[readme.exists()]
    output.write_text(content)
    return str(output)