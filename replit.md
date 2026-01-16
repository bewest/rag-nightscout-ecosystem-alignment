# Nightscout Alignment Workspace

## Overview
A multi-repository workspace bootstrap tool for working across Nightscout, AAPS, Loop, and Trio diabetes management projects. Uses a "bootstrap + lockfile" approach rather than git submodules.

## Project Architecture

```
.
├── workspace.lock.json    # Manifest defining external repos to clone
├── tools/
│   └── bootstrap.py       # Main CLI tool for managing repositories
├── externals/             # Cloned external repos (git-ignored)
├── Makefile               # Convenience wrapper
└── README.md              # User documentation
```

## Key Files

- **workspace.lock.json**: JSON manifest listing all external repositories with their URLs and pinned refs (branches, tags, or SHAs)
- **tools/bootstrap.py**: Python CLI tool with commands: bootstrap, status, freeze, add, remove
- **Makefile**: Simple make targets for common operations

## Usage

```bash
# Bootstrap all repos
python3 tools/bootstrap.py

# Check status
python3 tools/bootstrap.py status

# Pin current commits
python3 tools/bootstrap.py freeze

# Add new repo
python3 tools/bootstrap.py add <name> <url> [ref]

# Remove repo
python3 tools/bootstrap.py remove <name> [--delete]
```

## Included Repositories
1. LoopWorkspace - Loop iOS app workspace
2. cgm-remote-monitor - Nightscout web monitor
3. nightscout-connect - Nightscout Connect bridge
4. AndroidAPS - Android Artificial Pancreas System
5. Trio - Trio iOS closed-loop system
6. nightscout-reporter - PDF report generator

## Recent Changes
- 2026-01-16: Initial setup with bootstrap tool, lockfile manifest, and all core repos

## User Preferences
- Bash-compatible tooling preferred
- Simple CLI interface
- Lockfile-based version pinning for reproducibility
