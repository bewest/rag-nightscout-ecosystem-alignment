#!/usr/bin/env python3
"""
Nightscout Alignment Workspace Bootstrap Tool

This script manages external repository checkouts for a multi-repo
workspace containing Nightscout, AAPS, Loop, and Trio projects.

Usage:
    ./tools/bootstrap.py              # Clone/update all repos
    ./tools/bootstrap.py status       # Show status of all repos
    ./tools/bootstrap.py freeze       # Write resolved SHAs to lockfile
    ./tools/bootstrap.py add <name> <url> [ref]  # Add a new repo
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> int:
    """Execute a command and print it."""
    print(f"  + {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if check and result.returncode != 0:
        print(f"  ! Command failed with exit code {result.returncode}", file=sys.stderr)
    return result.returncode


def capture(cmd: list[str], cwd: Optional[Path] = None) -> str:
    """Execute a command and return its output."""
    try:
        return subprocess.check_output(cmd, cwd=cwd, text=True, stderr=subprocess.DEVNULL).strip()
    except subprocess.CalledProcessError:
        return ""


def load_lockfile(lockfile_path: Path) -> dict:
    """Load and parse the workspace lockfile."""
    if not lockfile_path.exists():
        print(f"Error: Lockfile not found: {lockfile_path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        return json.loads(lockfile_path.read_text())
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in lockfile: {e}", file=sys.stderr)
        sys.exit(1)


def save_lockfile(lockfile_path: Path, data: dict):
    """Save the lockfile with pretty formatting."""
    lockfile_path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Updated: {lockfile_path}")


def ensure_repo(dest: Path, url: str) -> bool:
    """Clone a repository if it doesn't exist. Returns True if cloned."""
    if dest.exists() and (dest / ".git").exists():
        print(f"  Repository already exists")
        return False
    
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    if dest.exists():
        shutil.rmtree(dest)
    
    return run(["git", "clone", "--progress", url, str(dest)]) == 0


def checkout_ref(dest: Path, ref: str) -> bool:
    """Fetch and checkout a specific ref (branch, tag, or SHA)."""
    run(["git", "fetch", "--all", "--tags", "--prune"], cwd=dest, check=False)
    return run(["git", "checkout", ref], cwd=dest, check=False) == 0


def get_repo_status(dest: Path) -> dict:
    """Get detailed status of a repository."""
    if not dest.exists() or not (dest / ".git").exists():
        return {"exists": False}
    
    head_sha = capture(["git", "rev-parse", "HEAD"], cwd=dest)
    head_short = capture(["git", "rev-parse", "--short", "HEAD"], cwd=dest)
    branch = capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=dest)
    dirty = capture(["git", "status", "--porcelain"], cwd=dest)
    
    remote_url = capture(["git", "remote", "get-url", "origin"], cwd=dest)
    
    ahead_behind = ""
    if branch != "HEAD":
        ab = capture(["git", "rev-list", "--left-right", "--count", f"origin/{branch}...HEAD"], cwd=dest)
        if ab:
            parts = ab.split()
            if len(parts) == 2:
                behind, ahead = int(parts[0]), int(parts[1])
                if ahead > 0 or behind > 0:
                    ahead_behind = f" [ahead {ahead}, behind {behind}]" if ahead and behind else \
                                   f" [ahead {ahead}]" if ahead else f" [behind {behind}]"
    
    return {
        "exists": True,
        "sha": head_sha,
        "sha_short": head_short,
        "branch": branch,
        "dirty": bool(dirty),
        "dirty_files": dirty.split("\n") if dirty else [],
        "remote_url": remote_url,
        "ahead_behind": ahead_behind
    }


def format_status_line(name: str, status: dict, expected_ref: str) -> str:
    """Format a single status line for display."""
    if not status["exists"]:
        return f"{name}: NOT CLONED"
    
    dirty_marker = " (dirty)" if status["dirty"] else ""
    branch_info = status["branch"] if status["branch"] != "HEAD" else "detached"
    
    return f"{name}: {branch_info} @ {status['sha_short']}{status['ahead_behind']}{dirty_marker}"


def cmd_bootstrap(args, lockfile_path: Path):
    """Bootstrap command: clone and checkout all repos."""
    data = load_lockfile(lockfile_path)
    externals_dir = Path(data.get("externals_dir", "externals"))
    repos = data.get("repos", [])
    
    if not repos:
        print("No repos defined in lockfile.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Bootstrapping {len(repos)} repositories into: {externals_dir}/\n")
    externals_dir.mkdir(parents=True, exist_ok=True)
    
    success_count = 0
    fail_count = 0
    
    for repo in repos:
        name = repo["name"]
        url = repo["url"]
        ref = repo.get("ref", "main")
        desc = repo.get("description", "")
        
        print(f"== {name} ==")
        if desc:
            print(f"  {desc}")
        
        dest = externals_dir / name
        
        cloned = ensure_repo(dest, url)
        if not cloned and not (dest / ".git").exists():
            print(f"  ! Failed to clone {name}")
            fail_count += 1
            continue
        
        if checkout_ref(dest, ref):
            status = get_repo_status(dest)
            print(f"  {format_status_line(name, status, ref)}")
            success_count += 1
        else:
            print(f"  ! Failed to checkout {ref}")
            fail_count += 1
        
        print()
    
    print(f"Done: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def cmd_status(args, lockfile_path: Path):
    """Status command: show current state of all repos."""
    data = load_lockfile(lockfile_path)
    externals_dir = Path(data.get("externals_dir", "externals"))
    repos = data.get("repos", [])
    
    if not repos:
        print("No repos defined in lockfile.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Workspace status ({len(repos)} repositories):\n")
    
    for repo in repos:
        name = repo["name"]
        ref = repo.get("ref", "main")
        dest = externals_dir / name
        
        status = get_repo_status(dest)
        line = format_status_line(name, status, ref)
        
        if not status["exists"]:
            print(f"  [ ] {line}")
        elif status["dirty"]:
            print(f"  [!] {line}")
        else:
            print(f"  [x] {line}")
    
    print()
    return 0


def cmd_freeze(args, lockfile_path: Path):
    """Freeze command: update lockfile with current SHAs."""
    data = load_lockfile(lockfile_path)
    externals_dir = Path(data.get("externals_dir", "externals"))
    repos = data.get("repos", [])
    
    if not repos:
        print("No repos defined in lockfile.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Freezing {len(repos)} repositories to current SHAs:\n")
    
    updated = 0
    for repo in repos:
        name = repo["name"]
        dest = externals_dir / name
        
        status = get_repo_status(dest)
        if not status["exists"]:
            print(f"  {name}: skipped (not cloned)")
            continue
        
        old_ref = repo.get("ref", "")
        new_ref = status["sha"]
        
        if old_ref != new_ref:
            repo["ref"] = new_ref
            repo["frozen_at"] = datetime.now().isoformat()
            repo["frozen_from"] = old_ref
            print(f"  {name}: {old_ref[:12] if len(old_ref) > 12 else old_ref} -> {new_ref[:12]}")
            updated += 1
        else:
            print(f"  {name}: unchanged ({new_ref[:12]})")
    
    if updated > 0:
        save_lockfile(lockfile_path, data)
        print(f"\nFroze {updated} repositories")
    else:
        print("\nNo changes to freeze")
    
    return 0


def cmd_add(args, lockfile_path: Path):
    """Add command: add a new repository to the lockfile."""
    data = load_lockfile(lockfile_path)
    repos = data.get("repos", [])
    
    for repo in repos:
        if repo["name"] == args.name:
            print(f"Error: Repository '{args.name}' already exists in lockfile", file=sys.stderr)
            sys.exit(1)
    
    new_repo = {
        "name": args.name,
        "url": args.url,
        "ref": args.ref or "main",
        "description": args.description or ""
    }
    
    repos.append(new_repo)
    data["repos"] = repos
    
    save_lockfile(lockfile_path, data)
    print(f"Added: {args.name} ({args.url})")
    print(f"Run './tools/bootstrap.py' to clone it")
    
    return 0


def cmd_remove(args, lockfile_path: Path):
    """Remove command: remove a repository from the lockfile."""
    data = load_lockfile(lockfile_path)
    repos = data.get("repos", [])
    externals_dir = Path(data.get("externals_dir", "externals"))
    
    found = False
    new_repos = []
    for repo in repos:
        if repo["name"] == args.name:
            found = True
        else:
            new_repos.append(repo)
    
    if not found:
        print(f"Error: Repository '{args.name}' not found in lockfile", file=sys.stderr)
        sys.exit(1)
    
    data["repos"] = new_repos
    save_lockfile(lockfile_path, data)
    
    dest = externals_dir / args.name
    if dest.exists() and args.delete:
        shutil.rmtree(dest)
        print(f"Removed: {args.name} (deleted from disk)")
    else:
        print(f"Removed: {args.name} from lockfile")
        if dest.exists():
            print(f"  Note: Directory still exists at {dest}")
            print(f"  Run with --delete to also remove from disk")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Nightscout Alignment Workspace Bootstrap Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./tools/bootstrap.py                    # Clone/update all repos
  ./tools/bootstrap.py status             # Show status of all repos  
  ./tools/bootstrap.py freeze             # Pin all repos to current SHAs
  ./tools/bootstrap.py add myrepo https://github.com/org/repo.git
  ./tools/bootstrap.py remove myrepo --delete
        """
    )
    
    parser.add_argument(
        "-l", "--lockfile",
        default="workspace.lock.json",
        help="Path to lockfile (default: workspace.lock.json)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    subparsers.add_parser("bootstrap", help="Clone and checkout all repositories")
    subparsers.add_parser("status", help="Show status of all repositories")
    subparsers.add_parser("freeze", help="Update lockfile with current SHAs")
    
    add_parser = subparsers.add_parser("add", help="Add a new repository")
    add_parser.add_argument("name", help="Repository name (directory name)")
    add_parser.add_argument("url", help="Git URL to clone")
    add_parser.add_argument("ref", nargs="?", help="Branch, tag, or SHA (default: main)")
    add_parser.add_argument("-d", "--description", help="Description of the repository")
    
    remove_parser = subparsers.add_parser("remove", help="Remove a repository")
    remove_parser.add_argument("name", help="Repository name to remove")
    remove_parser.add_argument("--delete", action="store_true", help="Also delete from disk")
    
    args = parser.parse_args()
    lockfile_path = Path(args.lockfile)
    
    if args.command is None or args.command == "bootstrap":
        return cmd_bootstrap(args, lockfile_path)
    elif args.command == "status":
        return cmd_status(args, lockfile_path)
    elif args.command == "freeze":
        return cmd_freeze(args, lockfile_path)
    elif args.command == "add":
        return cmd_add(args, lockfile_path)
    elif args.command == "remove":
        return cmd_remove(args, lockfile_path)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
