#!/usr/bin/env python3
"""
Submodule Checkout Tool

Properly initializes git submodules for repositories that are nested
inside another git repository. This solves the issue where git submodule
commands fail because they look for the parent repo's .git directory
instead of the nested repo's .git.

Usage:
    ./tools/checkout_submodules.py <repo_path>
    ./tools/checkout_submodules.py externals/LoopWorkspace
    ./tools/checkout_submodules.py --all  # Process all repos with submodules flag
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_git_with_dir(repo_path: Path, args: list[str], check: bool = True) -> int:
    """Run a git command with explicit GIT_DIR and GIT_WORK_TREE."""
    git_dir = repo_path / ".git"
    
    if not git_dir.exists():
        print(f"Error: No .git directory found at {git_dir}", file=sys.stderr)
        return 1
    
    env = os.environ.copy()
    env["GIT_DIR"] = str(git_dir.resolve())
    env["GIT_WORK_TREE"] = str(repo_path.resolve())
    
    cmd = ["git"] + args
    print(f"  + {' '.join(cmd)}")
    print(f"    (GIT_DIR={git_dir})")
    
    result = subprocess.run(cmd, env=env, cwd=repo_path)
    
    if check and result.returncode != 0:
        print(f"  ! Command failed with exit code {result.returncode}", file=sys.stderr)
    
    return result.returncode


def checkout_submodules(repo_path: Path, recursive: bool = True) -> bool:
    """Initialize and update submodules for a repository."""
    gitmodules = repo_path / ".gitmodules"
    
    if not gitmodules.exists():
        print(f"  No .gitmodules file found in {repo_path}")
        return True
    
    print(f"\n== Checking out submodules for: {repo_path} ==\n")
    
    init_args = ["submodule", "update", "--init"]
    if recursive:
        init_args.append("--recursive")
    
    result = run_git_with_dir(repo_path, init_args)
    
    if result == 0:
        print(f"\n  Submodules initialized successfully")
        return True
    else:
        print(f"\n  ! Failed to initialize submodules", file=sys.stderr)
        return False


def get_submodule_status(repo_path: Path) -> list[dict]:
    """Get the status of submodules in a repository."""
    git_dir = repo_path / ".git"
    
    if not git_dir.exists():
        return []
    
    env = os.environ.copy()
    env["GIT_DIR"] = str(git_dir.resolve())
    env["GIT_WORK_TREE"] = str(repo_path.resolve())
    
    try:
        result = subprocess.run(
            ["git", "submodule", "status"],
            env=env,
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            return []
        
        submodules = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            
            parts = line.split()
            if len(parts) >= 2:
                sha = parts[0].lstrip("-+")
                path = parts[1]
                status = "uninitialized" if line.startswith("-") else \
                         "modified" if line.startswith("+") else "ok"
                submodules.append({
                    "path": path,
                    "sha": sha[:12],
                    "status": status
                })
        
        return submodules
    except Exception:
        return []


def load_lockfile(lockfile_path: Path) -> dict:
    """Load the workspace lockfile."""
    if not lockfile_path.exists():
        return {}
    try:
        return json.loads(lockfile_path.read_text())
    except json.JSONDecodeError:
        return {}


def cmd_checkout(args) -> int:
    """Checkout submodules for a specific repo."""
    repo_path = Path(args.repo_path)
    
    if not repo_path.exists():
        print(f"Error: Repository path does not exist: {repo_path}", file=sys.stderr)
        return 1
    
    if not (repo_path / ".git").exists():
        print(f"Error: Not a git repository: {repo_path}", file=sys.stderr)
        return 1
    
    success = checkout_submodules(repo_path, recursive=not args.no_recursive)
    return 0 if success else 1


def cmd_all(args) -> int:
    """Checkout submodules for all repos with submodules flag in lockfile."""
    lockfile_path = Path(args.lockfile)
    data = load_lockfile(lockfile_path)
    
    if not data:
        print(f"Error: Could not load lockfile: {lockfile_path}", file=sys.stderr)
        return 1
    
    externals_dir = Path(data.get("externals_dir", "externals"))
    repos = data.get("repos", [])
    
    repos_with_submodules = [r for r in repos if r.get("submodules")]
    
    if not repos_with_submodules:
        print("No repositories with submodules flag found in lockfile.")
        return 0
    
    print(f"Processing {len(repos_with_submodules)} repositories with submodules:\n")
    
    success_count = 0
    fail_count = 0
    
    for repo in repos_with_submodules:
        name = repo["name"]
        repo_path = externals_dir / name
        
        if not repo_path.exists():
            print(f"  {name}: skipped (not cloned)")
            continue
        
        if checkout_submodules(repo_path, recursive=not args.no_recursive):
            success_count += 1
        else:
            fail_count += 1
    
    print(f"\nDone: {success_count} succeeded, {fail_count} failed")
    return 0 if fail_count == 0 else 1


def cmd_status(args) -> int:
    """Show submodule status for a repo or all repos."""
    if args.repo_path:
        repo_path = Path(args.repo_path)
        if not repo_path.exists():
            print(f"Error: Path does not exist: {repo_path}", file=sys.stderr)
            return 1
        
        submodules = get_submodule_status(repo_path)
        if not submodules:
            print(f"No submodules found in {repo_path}")
            return 0
        
        print(f"Submodules in {repo_path}:\n")
        for sm in submodules:
            status_icon = {"ok": "[x]", "uninitialized": "[ ]", "modified": "[!]"}
            print(f"  {status_icon.get(sm['status'], '[?]')} {sm['path']} @ {sm['sha']}")
        return 0
    
    lockfile_path = Path(args.lockfile)
    data = load_lockfile(lockfile_path)
    
    if not data:
        print(f"Error: Could not load lockfile: {lockfile_path}", file=sys.stderr)
        return 1
    
    externals_dir = Path(data.get("externals_dir", "externals"))
    repos = data.get("repos", [])
    
    repos_with_submodules = [r for r in repos if r.get("submodules")]
    
    for repo in repos_with_submodules:
        name = repo["name"]
        repo_path = externals_dir / name
        
        if not repo_path.exists():
            print(f"{name}: not cloned")
            continue
        
        submodules = get_submodule_status(repo_path)
        if not submodules:
            print(f"{name}: no submodules or .gitmodules missing")
            continue
        
        initialized = sum(1 for sm in submodules if sm["status"] == "ok")
        total = len(submodules)
        print(f"{name}: {initialized}/{total} submodules initialized")
        
        if args.verbose:
            for sm in submodules:
                status_icon = {"ok": "[x]", "uninitialized": "[ ]", "modified": "[!]"}
                print(f"    {status_icon.get(sm['status'], '[?]')} {sm['path']}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Initialize git submodules for nested repositories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./tools/checkout_submodules.py externals/LoopWorkspace
  ./tools/checkout_submodules.py all
  ./tools/checkout_submodules.py status externals/LoopWorkspace
  ./tools/checkout_submodules.py status --verbose
        """
    )
    
    parser.add_argument(
        "-l", "--lockfile",
        default="workspace.lock.json",
        help="Path to lockfile (default: workspace.lock.json)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    checkout_parser = subparsers.add_parser("checkout", help="Checkout submodules for a repo")
    checkout_parser.add_argument("repo_path", help="Path to the repository")
    checkout_parser.add_argument("--no-recursive", action="store_true", 
                                  help="Don't recursively init nested submodules")
    
    all_parser = subparsers.add_parser("all", help="Checkout submodules for all flagged repos")
    all_parser.add_argument("--no-recursive", action="store_true",
                            help="Don't recursively init nested submodules")
    
    status_parser = subparsers.add_parser("status", help="Show submodule status")
    status_parser.add_argument("repo_path", nargs="?", help="Path to repository (optional)")
    status_parser.add_argument("-v", "--verbose", action="store_true",
                               help="Show individual submodule status")
    
    if len(sys.argv) > 1 and sys.argv[1] not in ["checkout", "all", "status", "-h", "--help", "-l", "--lockfile"]:
        if os.path.exists(sys.argv[1]) or sys.argv[1].startswith("externals/"):
            class Args:
                repo_path: str = ""
                no_recursive: bool = False
            args = Args()
            args.repo_path = sys.argv[1]
            args.no_recursive = "--no-recursive" in sys.argv
            return cmd_checkout(args)
    
    args = parser.parse_args()
    
    if args.command == "checkout":
        return cmd_checkout(args)
    elif args.command == "all":
        return cmd_all(args)
    elif args.command == "status":
        return cmd_status(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
