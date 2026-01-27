# Workflow Usage Guide

This guide explains how to use the process-oriented sdqctl workflows in the Nightscout ecosystem alignment workspace.

## Quick Start

```bash
# Activate sdqctl
source activate-sdqctl.sh

# Check workspace status
sdqctl workspace status

# Run a comparison workflow
sdqctl iterate workflows/analysis/compare-feature.conv \
  --prologue "Focus: treatment sync. Repos: Loop, AAPS, Trio."
```

## Core Concepts

### Process-Oriented Workflows

Workflows are **generic processes** that take direction via `--prologue` or adjacent prompts. They are NOT domain-specific — instead of `compare-treatments.conv` vs `compare-bolus.conv`, there is one `compare-feature.conv` that you direct at different topics.

### I/O Contracts

Every workflow documents its I/O contract in comments at the top:

```dockerfile
# I/O Contract:
#   INPUT:  Direction via --prologue
#           traceability/*.md, externals/*
#   OUTPUT: docs/10-domain/{topic}-*.md
#           traceability/gaps.md (new GAP-XXX entries)
#           progress.md (dated entry)
#   ESCALATE: docs/OPEN-QUESTIONS.md
```

### Direction Injection

Three ways to give direction (ordered by preference):

**1. `--prologue` CLI flag (Recommended)**
```bash
sdqctl iterate workflows/analysis/compare-feature.conv \
  --prologue "Focus: treatment sync. Repos: Loop, AAPS, Trio."
```

**2. Adjacent inline prompt**
```bash
sdqctl iterate "Compare bolus commands in Loop vs AAPS" \
  workflows/analysis/compare-feature.conv
```

**3. Shell variable expansion**
```bash
feature="remote bolus commands"
repos="Loop, AAPS, Trio"
sdqctl iterate workflows/analysis/compare-feature.conv \
  --prologue "Focus: $feature. Repos: $repos"
```

## Workflow Categories

### Analysis Workflows (`workflows/analysis/`)

| Workflow | Purpose | Direction Example |
|----------|---------|-------------------|
| `compare-feature.conv` | Cross-project feature comparison | `--prologue "Focus: timestamp handling"` |
| `extract-spec.conv` | Extract specs from source code | `--prologue "Extract: RemoteTreatment from AAPS"` |
| `deep-dive.conv` | Comprehensive topic analysis | `--prologue "Topic: Dexcom G7 protocol"` |
| `gap-discovery.conv` | Systematic gap identification | `--prologue "Area: batch API behaviors"` |

### Maintenance Workflows (`workflows/maintenance/`)

| Workflow | Purpose | Direction Example |
|----------|---------|-------------------|
| `5-facet-update.conv` | Update all 5 documentation facets | `--prologue "Recent work: G7 analysis"` |
| `terminology-alignment.conv` | Map terms across projects | `--prologue "Domain: insulin dosing"` |

### Generation Workflows (`workflows/generation/`)

| Workflow | Purpose | Direction Example |
|----------|---------|-------------------|
| `gap-to-proposal.conv` | Generate RFC/ADR from GAP-ID | `--prologue "GAP-ID: GAP-API-003. Type: RFC"` |
| `gen-conformance.conv` | Generate conformance test scenarios | `--prologue "REQ-ID: REQ-BATCH-001"` |

### Traceability Workflows (`workflows/traceability/`)

| Workflow | Purpose | Direction Example |
|----------|---------|-------------------|
| `trace-requirement.conv` | Full traceability chain for REQ-ID | `--prologue "REQ-ID: REQ-BATCH-001"` |
| `trace-gap.conv` | Gap impact analysis | `--prologue "GAP-ID: GAP-SYNC-001"` |

## Common Patterns

### Pick Work from Backlog

```bash
# 1. Check the ready queue
cat docs/sdqctl-proposals/ECOSYSTEM-BACKLOG.md | head -40

# 2. Run appropriate workflow for the task type
# For comparison tasks:
sdqctl iterate workflows/analysis/compare-feature.conv \
  --prologue "Focus: [topic from backlog]"

# For gap analysis:
sdqctl iterate workflows/traceability/trace-gap.conv \
  --prologue "GAP-ID: [gap-id from backlog]"
```

### Explore Before Analyzing

```bash
# Search for relevant code first
sdqctl workspace search "Treatment" -t swift -l

# Then run deep-dive with findings
sdqctl iterate workflows/analysis/deep-dive.conv \
  --prologue "Topic: Swift Treatment types. Found in: Loop, Trio, nightguard"
```

### Chain Workflows

```bash
# 1. First discover gaps
sdqctl iterate workflows/analysis/gap-discovery.conv \
  --prologue "Area: batch upload behaviors"

# 2. Then trace the most important gap
sdqctl iterate workflows/traceability/trace-gap.conv \
  --prologue "GAP-ID: GAP-BATCH-001"

# 3. Generate proposal from findings
sdqctl iterate workflows/generation/gap-to-proposal.conv \
  --prologue "GAP-ID: GAP-BATCH-001. Type: RFC"
```

### Preview Before Running

```bash
# Use --render-only to see expanded workflow without executing
sdqctl iterate workflows/analysis/compare-feature.conv \
  --prologue "Focus: treatment sync" \
  --render-only
```

## Workspace Commands

### `sdqctl workspace status`
Show status of all external repositories:
```bash
$ sdqctl workspace status
Workspace: /path/to/rag-nightscout-ecosystem-alignment
External repositories: 16

Repository                          Branch               Changes    Last Commit
-------------------------------------------------------------------------------------
AndroidAPS                          master               ✓ clean    4 weeks ago
Trio                                dev                  ✓ clean    10 days ago
...
```

### `sdqctl workspace search <pattern>`
Search across all external repositories:
```bash
# Find Swift files mentioning Treatment
sdqctl workspace search "Treatment" -t swift

# Case-insensitive search with context
sdqctl workspace search "bolus" -i -C 2

# Files only
sdqctl workspace search "glucose" -l
```

### `sdqctl workspace diff <pattern>`
Compare implementations across repos:
```bash
sdqctl workspace diff "Treatment" -t swift
```

## Output Locations

| Artifact Type | Location | Format |
|---------------|----------|--------|
| Deep dives | `docs/10-domain/{topic}-deep-dive.md` | Markdown |
| Gap entries | `traceability/gaps.md` | GAP-XXX-NNN |
| Requirements | `traceability/requirements.md` | REQ-NNN |
| Terminology | `mapping/cross-project/terminology-matrix.md` | Table |
| Progress log | `progress.md` | Dated entries |
| Open questions | `docs/OPEN-QUESTIONS.md` | Categorized |
| Proposals | `proposals/*.md` | RFC/ADR |
| Trace reports | `traceability/{id}-trace.md` | Report |

## Gap ID Taxonomy

Gaps use format `GAP-{CATEGORY}-{NNN}`:

| Category | Description |
|----------|-------------|
| CGM | CGM protocol/data issues |
| TREAT | Treatment/bolus handling |
| DS | DataSource/sync issues |
| SYNC | Synchronization gaps |
| ALG | Algorithm differences |
| API | API specification gaps |
| REMOTE | Remote command issues |
| PUMP | Pump integration |
| SPEC | Specification gaps |
| IMPL | Implementation differences |
| BATCH | Batch processing |
| TZ | Timezone handling |
| ERR | Error handling |

## 5-Facet Pattern

All analysis workflows update the 5 documentation facets:

1. **Terminology** → `mapping/cross-project/terminology-matrix.md`
2. **Gaps** → `traceability/gaps.md`
3. **Requirements** → `traceability/requirements.md`
4. **Deep Dive** → `docs/10-domain/{topic}-deep-dive.md`
5. **Progress** → `progress.md`

## Tips

- Always use `--prologue` for reproducibility (can be scripted)
- Run `sdqctl workspace status` before analysis to check repo states
- Use `--render-only` to preview workflow expansion
- Check `progress.md` to see what's already been analyzed
- Escalate unclear decisions to `OPEN-QUESTIONS.md` rather than guessing
