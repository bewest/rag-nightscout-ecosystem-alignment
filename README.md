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

| Alias | Name | Description |
|-------|------|-------------|
| loop | LoopWorkspace | Loop iOS app workspace with all dependencies |
| crm | cgm-remote-monitor | Nightscout CGM Remote Monitor web application |
| ns-connect | nightscout-connect | Nightscout Connect bridge for data sources |
| aaps | AndroidAPS | Android Artificial Pancreas System |
| trio | Trio | Trio iOS closed-loop system |
| ns-reporter | nightscout-reporter | Nightscout Reporter for generating PDF reports |
| ns-gateway | nightscout-roles-gateway | Nightscout Roles Gateway for access control |
| oref0 | oref0 | OpenAPS Reference Design - core dosing algorithm (oref0/oref1) |
| openaps | openaps | OpenAPS toolkit - device interface and data management |
| nightguard | nightguard | Nightguard iOS/watchOS app for blood glucose monitoring via Nightscout |
| xdrip4ios | xdripswift | xDrip4iOS - iOS app for CGM data management and Nightscout sync |
| xdrip | xDrip | xDrip+ Android app for CGM data collection and Nightscout sync |
| diable | DiaBLE | DiaBLE - Diabetes Libre app for reading Libre sensors on iOS/watchOS |
| xdrip-js | xdrip-js | Node.js library for interfacing with Dexcom G5/G6 transmitters via BLE |
| loopfollow | LoopFollow | LoopFollow iOS/watchOS app for caregivers to monitor Loop/Trio/iAPS users |
| loopcaregiver | LoopCaregiver | LoopCaregiver iOS companion app for remote bolus, carbs, and override control |

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
├── Makefile               # Convenience commands
├── tools/                 # Bootstrap and utility scripts
│   └── bootstrap.py       # Clones/updates external repos
├── externals/             # Cloned repositories (git-ignored)
│   ├── LoopWorkspace/
│   ├── cgm-remote-monitor/
│   ├── AndroidAPS/
│   ├── Trio/
│   └── ...                # All 20 repos from workspace.lock.json
├── mapping/               # Per-project field mapping documentation
│   ├── aaps/
│   ├── loop/
│   ├── trio/
│   ├── nightscout/
│   ├── cross-project/     # Cross-project mapping analysis
│   └── ...
├── specs/                 # API and protocol specifications
│   ├── openapi/           # OpenAPI specs for Nightscout API
│   ├── jsonschema/        # JSON Schema definitions
│   └── pump-protocols-spec.md
├── conformance/           # Conformance test scenarios
│   └── scenarios/
├── traceability/          # Cross-project traceability documentation
├── docs/                  # General documentation
└── README.md
```

## For AI Coding Agents

This workspace is designed to work well with coding agents (Replit, GitHub Copilot, Claude, local LLMs):

1. **Predictable layout**: All external repos live in `externals/`
2. **Version pinning**: Use `make freeze` to lock exact commits
3. **No cross-repo git pollution**: Each repo maintains its own git history
4. **Easy reset**: Delete `externals/` and re-run `make bootstrap`
5. **Enhanced tooling**: Query, trace, and validate with JSON output

### Tooling for Agents

**Quick Start**:
```bash
# Interactive exploration
make cli

# Query documentation
python3 tools/query_workspace.py --search "authentication" --json

# Trace requirement coverage
python3 tools/query_workspace.py --tests-for REQ-001 --json

# Validate changes
python3 tools/run_workflow.py --workflow quick --json
```

**Documentation**:
- `docs/TOOLING-GUIDE.md` - Comprehensive guide
- `docs/TOOLING-QUICKREF.md` - Quick reference
- `make help` - All available commands

### Agent Guardrails

- Agents should NOT commit directly to `main`/`master` in external repos
- Create topic branches: `git checkout -b workspace/feature-name`
- The workspace repo tracks ONLY configuration, not external code
- Always validate before committing: `make workflow TYPE=quick`

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
