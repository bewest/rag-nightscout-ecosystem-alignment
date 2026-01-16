# Nightscout Alignment Workspace

A multi-repository workspace for working across Nightscout, AAPS, Loop, and Trio projects without merging them into a single giant repo.

## Overview

This workspace uses a "bootstrap + lockfile" approach where:
- External repositories are cloned into `externals/` (git-ignored)
- A `workspace.lock.json` manifest pins which repos and refs to check out
- A Python bootstrap script manages cloning, updating, and version pinning

This gives you submodule-like determinism without the submodule UX pain.

## Quick Start

```bash
# Clone/update all repositories
make bootstrap
# or: python3 tools/bootstrap.py

# Check status of all repos
make status

# Pin current commits for reproducibility
make freeze
```

## Included Repositories

| Name | Description |
|------|-------------|
| LoopWorkspace | Loop iOS app workspace with all dependencies |
| cgm-remote-monitor | Nightscout CGM Remote Monitor web application |
| nightscout-connect | Nightscout Connect bridge for data sources |
| AndroidAPS | Android Artificial Pancreas System |
| Trio | Trio iOS closed-loop system |
| nightscout-reporter | Nightscout Reporter for generating PDF reports |

## Managing Repositories

### Add a new repository

```bash
./tools/bootstrap.py add myrepo https://github.com/org/repo.git main
./tools/bootstrap.py add myrepo https://github.com/org/repo.git --description "My custom repo"
```

### Remove a repository

```bash
# Remove from lockfile only
./tools/bootstrap.py remove myrepo

# Remove from lockfile and delete from disk
./tools/bootstrap.py remove myrepo --delete
```

### Pin to specific commits (recommended for reproducibility)

```bash
# Freeze all repos to their current SHAs
make freeze

# Or manually edit workspace.lock.json to set specific refs
```

## Directory Structure

```
.
├── workspace.lock.json    # Manifest of external repos (committed)
├── tools/
│   └── bootstrap.py       # Bootstrap and management script
├── externals/             # Cloned repositories (git-ignored)
│   ├── .keep
│   ├── LoopWorkspace/
│   ├── cgm-remote-monitor/
│   ├── nightscout-connect/
│   ├── AndroidAPS/
│   ├── Trio/
│   └── nightscout-reporter/
├── Makefile               # Convenience commands
└── README.md
```

## For AI Coding Agents

This workspace is designed to work well with coding agents (Replit, Claude, local LLMs):

1. **Predictable layout**: All external repos live in `externals/`
2. **Version pinning**: Use `make freeze` to lock exact commits
3. **No cross-repo git pollution**: Each repo maintains its own git history
4. **Easy reset**: Delete `externals/` and re-run `make bootstrap`

### Agent Guardrails

- Agents should NOT commit directly to `main`/`master` in external repos
- Create topic branches: `git checkout -b workspace/feature-name`
- The workspace repo tracks ONLY configuration, not external code

## Troubleshooting

### Repository won't clone
- Check network connectivity
- Verify the URL in `workspace.lock.json` is correct
- Some repos may require authentication for private forks

### Dirty repository warnings
- Run `git status` in the specific external repo
- Commit, stash, or discard changes as appropriate

### Reset everything
```bash
rm -rf externals/*
touch externals/.keep
make bootstrap
```

## Contributing

To contribute changes back to upstream projects:

1. Navigate to the specific repo in `externals/`
2. Create a branch: `git checkout -b your-feature`
3. Make changes and commit
4. Push to your fork and create a PR upstream

## License

This workspace configuration is provided as-is. Individual repositories maintain their own licenses.
