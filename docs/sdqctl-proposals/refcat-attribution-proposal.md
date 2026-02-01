# REFCAT Attribution Proposal

> **Created**: 2026-01-30  
> **Updated**: 2026-02-01  
> **Purpose**: Use REFCAT directive for file attribution and context snippets  
> **Status**: Proposal  
> **Source**: [iterate-effectiveness-report.md](iterate-effectiveness-report.md)

---

## Executive Summary

The sdqctl `REFCAT` directive provides **file attribution with small snippets** - a more efficient alternative to `RUN head file.md` + `ELIDE` patterns. REFCAT:

1. **Injects file context** with proper source attribution
2. **Extracts specific line ranges** without loading entire files
3. **Tracks provenance** for traceability

### Current Pattern (Inefficient)

```conv
RUN head -100 traceability/gaps.md
ELIDE
PROMPT Analyze the gaps above...
```

**Problems:**
- `head` loads arbitrary content (may cut mid-entry)
- `ELIDE` still consumes tokens for truncation marker
- No source attribution in output
- Requires shell execution overhead

### Proposed Pattern (REFCAT)

```conv
REFCAT traceability/gaps.md:1-50
PROMPT Analyze the gaps above...
```

**Benefits:**
- Direct line range extraction
- Built-in source attribution
- No shell overhead
- Cleaner workflow syntax

---

## REFCAT Usage Patterns

### Pattern 1: File Header + Recent Content

```conv
# Get file header and first N lines
REFCAT progress.md:1-30

PROMPT Based on the progress header above, identify the most recent milestone.
```

### Pattern 2: Specific Section Extraction

```conv
# Extract a known section by line range
REFCAT traceability/requirements.md:45-80

PROMPT These requirements cover the CGM domain. Verify they have assertions.
```

### Pattern 3: Multiple File Attribution

```conv
# Compare implementations across repos
REFCAT externals/LoopWorkspace/LoopAlgorithm/Sources/LoopAlgorithm.swift:1-50
REFCAT externals/AndroidAPS/core/oref/src/main/kotlin/DetermineBasal.kt:1-50

PROMPT Compare the algorithm entry points between Loop and AAPS.
```

### Pattern 4: Glob-based Attribution (Proposed Enhancement)

```conv
# Future: REFCAT with glob patterns
REFCAT externals/**/*Treatment*.swift:1-20

PROMPT Identify treatment-related files across all iOS projects.
```

---

## Token Savings Analysis

### Before: RUN + ELIDE Pattern

| Step | Tokens (est.) |
|------|---------------|
| Shell execution overhead | 50-100 |
| Raw command output | 500-2000 |
| ELIDE truncation marker | 50 |
| **Total per file** | 600-2150 |

### After: REFCAT Pattern

| Step | Tokens (est.) |
|------|---------------|
| REFCAT attribution header | 30-50 |
| Extracted content | 200-500 |
| **Total per file** | 230-550 |

**Savings**: 60-75% per file reference

### Cycle-Level Impact

| Metric | Before | After | Savings |
|--------|--------|-------|---------|
| File reads/cycle | 20-40 | 20-40 | - |
| Tokens per read | ~1200 | ~400 | 800 |
| Total file read tokens | 24K-48K | 8K-16K | 16K-32K |
| As % of input tokens | 1-2% | 0.3-0.5% | ~1% |

**Note**: Modest percentage savings, but compounds across cycles and improves signal/noise ratio.

---

## Workflow Migration

### Candidates for REFCAT Conversion

| Current Pattern | File | Lines |
|-----------------|------|-------|
| `RUN head -60 progress.md` | progress.md | 1-60 |
| `RUN head -100 LIVE-BACKLOG.md` | LIVE-BACKLOG.md | 1-100 |
| `RUN head -50 traceability/gaps.md` | traceability/gaps.md | 1-50 |
| `RUN cat docs/TOOLING-GUIDE.md` | TOOLING-GUIDE.md | 1-* |

### Migration Checklist

- [ ] Audit all `.conv` files for `RUN head` patterns
- [ ] Identify line ranges that provide useful context
- [ ] Replace with `REFCAT path:start-end`
- [ ] Test workflow execution
- [ ] Remove corresponding `ELIDE` directives

---

## Implementation Status

| Component | Status |
|-----------|--------|
| REFCAT directive in sdqctl | ✅ Available |
| Glob pattern support | 📋 Proposed (REFCAT-DESIGN.md) |
| Workflow migration | 📋 Not started |
| Make targets | ❌ N/A (directive only) |

---

## Cross-References

- [iterate-effectiveness-report.md](iterate-effectiveness-report.md) - Token analysis
- [tooling.md](backlogs/tooling.md) - Backlog item #31
- [ECOSYSTEM-BACKLOG.md](ECOSYSTEM-BACKLOG.md) - Ready Queue
- [REFCAT-DESIGN.md](https://github.com/bewest/copilot-do-proposal/blob/main/sdqctl/proposals/REFCAT-DESIGN.md) - sdqctl proposal
