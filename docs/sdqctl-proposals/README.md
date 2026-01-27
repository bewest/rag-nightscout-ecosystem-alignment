# sdqctl Proposals

This directory contains copies of sdqctl development proposals relevant to the Nightscout ecosystem workspace.

## Contents

| Proposal | Status | Description |
|----------|--------|-------------|
| [HELP-INLINE.md](./HELP-INLINE.md) | Proposal | Allow HELP anywhere in workflow (not just prologues) |
| [VERIFICATION-DIRECTIVES.md](./VERIFICATION-DIRECTIVES.md) | Proposal | Built-in `VERIFY refs`, `CHECK-TRACEABILITY` directives |
| [RUN-BRANCHING.md](./RUN-BRANCHING.md) | ✅ Complete | Conditional execution (ON-FAILURE, ON-SUCCESS) |
| [STPA-TRACEABILITY-FRAMEWORK.md](./STPA-TRACEABILITY-FRAMEWORK.md) | Framework | STPA integration patterns |
| [ECOSYSTEM-BACKLOG.md](./ECOSYSTEM-BACKLOG.md) | Active | Prioritized analysis task queue |

## Agentic Automation (R&D)

| Proposal | Status | Description |
|----------|--------|-------------|
| [AGENTIC-ANALYSIS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/AGENTIC-ANALYSIS.md) | R&D | `sdqctl agent analyze` - Autonomous multi-cycle deep-dive |
| [CONTINUOUS-MONITORING.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/CONTINUOUS-MONITORING.md) | R&D | `sdqctl watch/drift` - Monitor repos for changes |
| [UPSTREAM-CONTRIBUTIONS.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/UPSTREAM-CONTRIBUTIONS.md) | R&D | `sdqctl delegate` - Draft upstream fixes |

## Source

These files are copied from [sdqctl/proposals/](https://github.com/bewest/copilot-do-proposal/tree/main/sdqctl/proposals) for reference.

## Relevance to Nightscout Ecosystem

### HELP-INLINE (NEW)

Enables just-in-time help injection mid-workflow:
- Inject terminology reference before comparison phase
- Inject GAP-ID format before gap creation phase
- Inject STPA guidance before hazard analysis

Currently, HELP only works in prologues, forcing all context at the start.

### VERIFICATION-DIRECTIVES

This proposal directly addresses our verification workflow needs:
- `VERIFY refs` - Validate code references in documentation
- `VERIFY traceability` - Check REQ→Spec→Test links
- `CHECK-TRACEABILITY` alias for quick checks

Currently we use `RUN python tools/verify_refs.py` - the native directives would eliminate external tool dependencies.

### RUN-BRANCHING

Enables conditional workflow execution:
- `ON-FAILURE` for error handling
- `ON-SUCCESS` for conditional follow-up
- Useful for handling missing conformance files

**Status**: ✅ Implemented in sdqctl

## Update Policy

These are point-in-time copies. Check the sdqctl repo for latest versions.

**Last updated:** 2026-01-27
