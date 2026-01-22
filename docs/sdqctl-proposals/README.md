# sdqctl Proposals

This directory contains copies of sdqctl development proposals relevant to the Nightscout ecosystem workspace.

## Contents

| Proposal | Status | Description |
|----------|--------|-------------|
| [VERIFICATION-DIRECTIVES.md](./VERIFICATION-DIRECTIVES.md) | Proposal | Built-in `VERIFY refs`, `CHECK-TRACEABILITY` directives |
| [RUN-BRANCHING.md](./RUN-BRANCHING.md) | Proposal | Conditional execution and branching for RUN commands |

## Source

These files are copied from [sdqctl/proposals/](https://github.com/bewest/copilot-do-proposal/tree/main/sdqctl/proposals) for reference.

## Relevance to Nightscout Ecosystem

### VERIFICATION-DIRECTIVES

This proposal directly addresses our verification workflow needs:
- `VERIFY refs` - Validate code references in documentation
- `VERIFY traceability` - Check REQ→Spec→Test links
- `CHECK-TRACEABILITY` alias for quick checks

Currently we use `RUN python tools/verify_refs.py` - the native directives would eliminate external tool dependencies.

### RUN-BRANCHING

Enables conditional workflow execution:
- `RUN-IF` for conditional commands
- `RUN-ELSE` for fallback behavior
- Useful for handling missing conformance files

## Update Policy

These are point-in-time copies. Check the sdqctl repo for latest versions.

**Last updated:** 2026-01-22
