# HELP-INLINE Directive Proposal

> **Status**: Proposal  
> **Priority**: P2 (Medium)  
> **Source**: [sdqctl/proposals/HELP-INLINE.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/HELP-INLINE.md)

## Summary

Allow the HELP directive to work anywhere in a ConversationFile (not just prologues), enabling just-in-time help injection mid-workflow.

## Motivation for Nightscout Ecosystem

### Current Problem

When running multi-phase analysis workflows, context often needs to shift mid-workflow:
- Phase 1 analyzes treatments → needs terminology reference
- Phase 2 creates gaps → needs GAP-ID format reference
- Phase 3 generates proposals → needs RFC template reference

Currently, all HELP topics must be injected at the start (prologue), leading to either:
- Very long initial context (wastes tokens on phases that don't need it)
- Missing context in later phases (user must remember formats)

### Proposed Solution

```dockerfile
PROMPT Analyze treatment sync differences across Loop, AAPS, Trio.
COMPACT  # Clear context for phase 2

HELP-INLINE gap-ids  # Inject just before gap creation
PROMPT Create GAP entries for issues identified above.
COMPACT

HELP-INLINE conformance  # Inject before test generation
PROMPT Generate conformance test scenarios.
```

## Use Cases

### 1. Terminology Injection Before Comparison
```dockerfile
PROMPT Analyze the treatment handling in Loop.
HELP-INLINE terminology  # Ecosystem-specific term mappings
PROMPT Now compare with AAPS using consistent terminology.
```

### 2. Gap ID Format Before Creating Gaps
```dockerfile
PROMPT Identify issues with timestamp handling across systems.
HELP-INLINE gap-ids
PROMPT Create GAP-XXX entries for each issue.
```

### 3. STPA Guidance Before Hazard Analysis
```dockerfile
PROMPT Summarize the insulin bolus command flow.
HELP-INLINE stpa
PROMPT Identify unsafe control actions per STPA methodology.
```

## New Help Topics Needed

| Topic | Content |
|-------|---------|
| `gap-ids` | GAP-XXX-NNN taxonomy (CGM, TREAT, SYNC, ALG, API, etc.) |
| `5-facet` | 5-facet documentation pattern |
| `stpa` | STPA hazard analysis guidance |
| `conformance` | Conformance test scenario format |
| `nightscout` | Project overview (16 repos, key files) |

## Implementation Status

**Pending** - Tracked in [sdqctl/proposals/BACKLOG.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/BACKLOG.md)

## Workaround Until Implementation

Use PROLOGUE with shell variable expansion:
```bash
# Define help content in variable
gap_help="GAP IDs use format: GAP-{CATEGORY}-{NNN}. Categories: CGM, TREAT, SYNC..."

# Inject via --prologue
sdqctl iterate workflows/generation/gap-to-proposal.conv \
  --prologue "$gap_help. GAP-ID: GAP-SYNC-001"
```

Or use separate workflow phases:
```bash
# Phase 1: Analysis
sdqctl iterate workflows/analysis/compare-feature.conv \
  --prologue "Focus: treatment sync"

# Phase 2: Gap creation with fresh context
sdqctl iterate workflows/analysis/gap-discovery.conv \
  --prologue "HELP: gap-ids. Area: treatment sync"
```
