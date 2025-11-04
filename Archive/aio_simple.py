#!/usr/bin/env python3
"""
AIO Simple - Minimal implementation using only standard tools
No custom logic, just orchestrating git/tmux/ssh
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime

# Project directories - could be read from file or env var
PROJECTS = [
    "/home/seanpatten/projects/aios",
    "/home/seanpatten/projects/waylandauto",
    "/home/seanpatten/AndroidStudioProjects/Workcycle",
    "/home/seanpatten/projects/testRepoPrivate",
    "/home/seanpatten/projects/alpha",
    "/home/seanpatten/projects/aicombo",
    "/home/seanpatten/projects/aischedulerdemo",
    "/home/seanpatten/projects/monitorControl"
]

WORKTREES_DIR = Path.home() / "projects" / "aiosWorktrees"

# Agent commands - just the actual commands, no complex logic
AGENTS = {
    'c': ('codex', 'codex'),
    'l': ('claude', 'claude'),
    'g': ('gemini', 'gemini')
}

def run(cmd):
    """Run command and return result - no custom error handling"""
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def main():
    if len(sys.argv) < 2:
        print("Usage: aio_simple all <agent>:<count> [prompt]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "all":
        # Parse agent spec (e.g., "c:1")
        if len(sys.argv) < 3:
            print("Usage: aio_simple all <agent>:<count> [prompt]")
            sys.exit(1)

        agent_spec = sys.argv[2]
        agent_key, count = agent_spec.split(':')
        count = int(count)

        # Get prompt or use default
        prompt = sys.argv[3] if len(sys.argv) > 3 else "optimize"

        # Get agent info
        agent_name, agent_cmd = AGENTS.get(agent_key, ('unknown', 'echo'))

        # Create worktrees directory
        WORKTREES_DIR.mkdir(parents=True, exist_ok=True)

        print(f"Running {count} {agent_name} agents on {len(PROJECTS)} projects")

        for project_path in PROJECTS:
            project = Path(project_path)
            if not project.exists():
                print(f"Skip: {project.name} (not found)")
                continue

            print(f"\n=== {project.name} ===")

            # Check if it's a git repo
            result = run(f"git -C {project} rev-parse --git-dir")
            if result.returncode != 0:
                print(f"Skip: Not a git repo")
                continue

            # Try to fetch latest (will use system's git auth)
            print("Fetching latest...", end=" ")
            result = run(f"git -C {project} fetch origin 2>&1")
            if result.returncode == 0:
                print("✓")
            else:
                print(f"✗ (using local)")

            # Get current branch
            result = run(f"git -C {project} branch --show-current")
            branch = result.stdout.strip() or "main"

            # Create worktrees and launch agents
            for i in range(count):
                timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                worktree_name = f"{project.name}-{agent_name}-{timestamp}-{i}"
                worktree_path = WORKTREES_DIR / worktree_name

                # Create worktree (using git's native command)
                print(f"  Creating worktree {i+1}...", end=" ")
                result = run(f"git -C {project} worktree add {worktree_path} -b wt-{worktree_name} origin/{branch} 2>&1")
                if result.returncode != 0:
                    # Try with local branch if origin fails
                    result = run(f"git -C {project} worktree add {worktree_path} -b wt-{worktree_name} {branch} 2>&1")

                if result.returncode == 0:
                    print("✓")

                    # Create tmux session (using tmux's native command)
                    session_name = worktree_name
                    tmux_cmd = f"tmux new -d -s {session_name} -c {worktree_path} '{agent_cmd} \"{prompt}\"'"
                    result = run(tmux_cmd)

                    if result.returncode == 0:
                        print(f"  Launched {agent_name} in tmux session: {session_name}")
                    else:
                        print(f"  Failed to launch tmux session")
                else:
                    print(f"✗ ({result.stderr.strip()[:50]})")

        print(f"\n✓ Done! View agents with: tmux ls")

    elif command == "cleanup":
        # Clean up worktrees
        print("Cleaning up worktrees...")

        if not WORKTREES_DIR.exists():
            print("No worktrees directory found")
            return

        for worktree in WORKTREES_DIR.iterdir():
            if worktree.is_dir():
                # Find the parent repo
                for project_path in PROJECTS:
                    project = Path(project_path)
                    if not project.exists():
                        continue

                    # Check if this worktree belongs to this project
                    result = run(f"git -C {project} worktree list | grep {worktree}")
                    if result.returncode == 0:
                        # Remove worktree
                        print(f"  Removing {worktree.name}...", end=" ")
                        run(f"git -C {project} worktree remove {worktree} --force")
                        print("✓")
                        break

        # Kill tmux sessions
        print("Killing tmux sessions...")
        result = run("tmux ls -F '#{session_name}'")
        if result.returncode == 0:
            for session in result.stdout.strip().split('\n'):
                if any(p in session for p in ['codex', 'claude', 'gemini']):
                    print(f"  Killing {session}...", end=" ")
                    run(f"tmux kill-session -t {session}")
                    print("✓")

        print("✓ Cleanup complete")

    elif command == "jobs":
        # Show running tmux sessions
        result = run("tmux ls")
        if result.returncode == 0:
            print("Active sessions:")
            print(result.stdout)
        else:
            print("No active sessions")

    else:
        print(f"Unknown command: {command}")
        print("Commands: all, cleanup, jobs")

if __name__ == "__main__":
    main()