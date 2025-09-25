#!/usr/bin/env python3
"""AIOS Setup Script - Initialize the AI Operating System"""
import os
import sys
from pathlib import Path

def setup():
    print("\n🚀 AIOS Setup")
    print("=" * 40)

    # Create .aios directory structure
    aios_dir = Path.home() / ".aios"
    dirs = [aios_dir, aios_dir / "components", aios_dir / "scraped_data",
            aios_dir / "llm_cache"]

    for d in dirs:
        d.mkdir(exist_ok=True)
        print(f"✓ Created {d}")

    # Create initial config files
    tasks_file = aios_dir / "tasks.txt"
    if not tasks_file.exists():
        with open(tasks_file, 'w') as f:
            f.write("[ ] 2025-01-23 09:00 p:high Set up AIOS system\n")
            f.write("[ ] 2025-01-23 10:00 p:med Test all components\n")
            f.write("[ ] 2025-01-23 14:00 p:low Document workflow\n")
        print(f"✓ Created sample tasks")

    goals_file = aios_dir / "goals.txt"
    if not goals_file.exists():
        with open(goals_file, 'w') as f:
            f.write("WEEK: Complete AIOS setup and testing\n")
            f.write("MONTH: Automate daily workflows\n")
            f.write("YEAR: Build fully autonomous system\n")
        print(f"✓ Created sample goals")

    ideas_file = aios_dir / "ideas.txt"
    if not ideas_file.exists():
        with open(ideas_file, 'w') as f:
            f.write("Add voice control to AIOS\n")
            f.write("Create mobile app interface\n")
            f.write("Implement smart notifications\n")
        print(f"✓ Created sample ideas")

    print("\n✅ AIOS setup complete!")
    print(f"📁 Data directory: {aios_dir}")
    print("\n📚 Quick Start:")
    print("  python smart_todo.py list    # View tasks")
    print("  python daily_planner.py plan # Generate plan")
    print("  python web_ui.py             # Start web interface")
    print("  python backup_local.py now   # Create backup")

    # Check dependencies
    print("\n📦 Required packages:")
    packages = ['flask', 'requests', 'beautifulsoup4']
    for pkg in packages:
        print(f"  pip install {pkg}")

    print("\n🎯 Run 'python smart_todo.py list' to begin!")

if __name__ == '__main__':
    setup()