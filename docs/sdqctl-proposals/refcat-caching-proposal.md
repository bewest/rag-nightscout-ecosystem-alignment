# REFCAT Caching Proposal

> **Created**: 2026-01-30  
> **Purpose**: Reduce token usage 20-40% by caching external repo parsing  
> **Status**: Proposal  
> **Source**: [iterate-effectiveness-report.md](iterate-effectiveness-report.md)

---

## Executive Summary

The `sdqctl iterate` workflow consumes **3.4M input tokens per cycle**, primarily from repeated codebase exploration. By caching frequently-accessed file summaries and structural information, we can reduce token usage by an estimated **20-40%**.

### Current Problem

| Metric | Value | Issue |
|--------|-------|-------|
| Input tokens/cycle | 3,421,770 | High |
| Input/Output ratio | 242:1 | Heavy exploration |
| Cost/cycle | $10.27 | Could be $6-8 |
| Repeated file reads | ~40% estimated | Redundant |

### Proposed Solution

Implement a **REFCAT (Reference Catalog)** cache that stores:
1. File structure summaries per repository
2. Parsed AST signatures for key files
3. Previously extracted field mappings
4. Cross-reference indices

### Expected Benefits

| Benefit | Estimate |
|---------|----------|
| Token reduction | 20-40% |
| Cost savings | $2-4/cycle |
| Cycle speed | 15-25% faster |
| Context efficiency | Higher signal/noise |

---

## Current State Analysis

### Token Usage Breakdown (Estimated)

Based on iterate-effectiveness-report.md observations:

| Category | % of Input | Tokens/Cycle | Cacheable? |
|----------|------------|--------------|------------|
| File content reads | 45% | 1.54M | ✅ Yes |
| Directory listings | 15% | 513K | ✅ Yes |
| Grep/search results | 20% | 684K | ⚠️ Partial |
| Tool call overhead | 10% | 342K | ❌ No |
| Context/instructions | 10% | 342K | ❌ No |

**Cacheable portion**: ~60% of input tokens (2.0M/cycle)

### Frequently Accessed Patterns

From repository coverage data:

| Repository | References | Key Files |
|------------|------------|-----------|
| LoopWorkspace | 60 | LoopAlgorithm/, LoopKit/Models/ |
| AndroidAPS | 45 | core/oref/, database/entities/ |
| DiaBLE | 40 | LibreLink/, Dexcom*.swift |
| cgm-remote-monitor | 28 | lib/api3/, lib/plugins/ |
| Trio | 20 | FreeAPS/Sources/APS/ |
| oref0 | 20 | lib/determine-basal/ |

These 6 repositories account for **80%** of codebase references.

---

## Caching Architecture

### REFCAT Structure

```
.refcat/
├── index.json              # Global cache index
├── repos/
│   ├── LoopWorkspace/
│   │   ├── structure.json  # Directory tree
│   │   ├── files/
│   │   │   ├── LoopAlgorithm_LoopAlgorithm.swift.json
│   │   │   └── LoopKit_Models_*.json
│   │   └── signatures.json # AST signatures
│   ├── AndroidAPS/
│   │   ├── structure.json
│   │   ├── files/
│   │   └── signatures.json
│   └── ...
├── mappings/
│   ├── field-mappings.json   # Discovered field→field maps
│   ├── terminology.json      # Term definitions
│   └── gaps.json             # Discovered gaps
└── metadata.json             # Cache timestamps, versions
```

### Cache Entry Format

```json
{
  "path": "externals/LoopWorkspace/LoopAlgorithm/Sources/LoopAlgorithm/LoopAlgorithm.swift",
  "hash": "sha256:abc123...",
  "timestamp": "2026-01-30T12:00:00Z",
  "size_bytes": 15234,
  "summary": {
    "type": "swift_source",
    "classes": ["LoopAlgorithm"],
    "protocols": ["AlgorithmProtocol"],
    "key_functions": ["recommendBolus", "recommendTempBasal"],
    "imports": ["LoopKit", "HealthKit"],
    "line_count": 450
  },
  "content_hash": "sha256:def456...",
  "last_accessed": "2026-01-30T15:00:00Z",
  "access_count": 12
}
```

### Cache Invalidation

| Trigger | Action |
|---------|--------|
| File modified (git diff) | Invalidate specific file |
| Repository updated (git pull) | Invalidate all repo files |
| Cache age > 7 days | Soft invalidate (verify on access) |
| Manual `make cache-clear` | Clear all caches |

---

## Implementation Phases

### Phase 1: Directory Structure Cache (1-2 hours)

**Scope**: Cache `view` tool responses for directory listings.

**Implementation**:
```python
# .refcat/repos/{repo}/structure.json
{
  "path": "externals/LoopWorkspace",
  "tree": {
    "LoopAlgorithm": {
      "type": "dir",
      "children": ["Sources", "Tests", "Package.swift"]
    },
    "LoopKit": {...}
  },
  "generated": "2026-01-30T12:00:00Z"
}
```

**Token Savings**: ~15% (513K tokens/cycle)

### Phase 2: File Summary Cache (2-3 hours)

**Scope**: Store file metadata and structural summaries without full content.

**Implementation**:
- Parse Swift/Kotlin/JS files for class/function signatures
- Store first 100 lines as "preview"
- Index by file path and content hash

**Token Savings**: Additional ~15% (500K tokens/cycle)

### Phase 3: Cross-Reference Index (2-3 hours)

**Scope**: Pre-build indices for common search patterns.

**Implementation**:
```python
# .refcat/mappings/field-mappings.json
{
  "sgv": {
    "definitions": [
      {"repo": "cgm-remote-monitor", "path": "lib/api3/entries.js:45"},
      {"repo": "AndroidAPS", "path": "database/entities/GlucoseValue.kt:12"}
    ],
    "aliases": ["glucose", "bg", "bloodGlucose"]
  }
}
```

**Token Savings**: Additional ~10% (340K tokens/cycle)

### Phase 4: sdqctl Integration (3-4 hours)

**Scope**: Make REFCAT accessible to sdqctl workflows.

**Commands**:
```bash
# Build/update cache
sdqctl refcat build                    # Full rebuild
sdqctl refcat update                   # Incremental update
sdqctl refcat search "sgv"             # Search cached index

# Cache management
sdqctl refcat status                   # Show cache stats
sdqctl refcat clear                    # Clear all caches
sdqctl refcat clear --repo LoopWorkspace  # Clear specific repo
```

**Make Targets**:
```makefile
refcat-build:
	python tools/refcat_builder.py

refcat-update:
	python tools/refcat_builder.py --incremental

refcat-clear:
	rm -rf .refcat/
```

---

## Token Savings Estimate

### Conservative Estimate (20%)

| Category | Before | After | Savings |
|----------|--------|-------|---------|
| Input tokens/cycle | 3.42M | 2.74M | 680K |
| Cost/cycle | $10.27 | $8.22 | $2.05 |
| 40-cycle run | $410 | $328 | $82 |

### Optimistic Estimate (40%)

| Category | Before | After | Savings |
|----------|--------|-------|---------|
| Input tokens/cycle | 3.42M | 2.05M | 1.37M |
| Cost/cycle | $10.27 | $6.16 | $4.11 |
| 40-cycle run | $410 | $246 | $164 |

---

## Technical Considerations

### Storage Requirements

| Component | Size (est.) |
|-----------|-------------|
| 20 repos × structure.json | 200KB |
| 500 file summaries | 2MB |
| Cross-reference indices | 500KB |
| **Total** | ~3MB |

### Performance Impact

| Operation | Time (est.) |
|-----------|-------------|
| Cache lookup | <10ms |
| Cache miss + populate | 100-500ms |
| Full rebuild (20 repos) | 5-10 min |
| Incremental update | 30-60 sec |

### Git Integration

```bash
# .gitignore additions
.refcat/

# Or commit cache for reproducibility
# (trade-off: larger repo vs faster bootstrap)
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Stale cache returns wrong info | Medium | High | Hash-based invalidation |
| Cache size grows unbounded | Low | Medium | LRU eviction, size limits |
| Implementation complexity | Medium | Medium | Phased rollout |
| sdqctl compatibility | Low | Medium | Separate tooling, optional integration |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Token reduction | >20% | Compare iterate runs |
| Cache hit rate | >70% | `.refcat/metadata.json` stats |
| Cycle time improvement | >10% | Timing comparison |
| Zero stale data issues | 100% | No incorrect conclusions from cache |

---

## Implementation Files

| File | Purpose |
|------|---------|
| `tools/refcat_builder.py` | Cache builder/updater |
| `tools/refcat_query.py` | Cache query interface |
| `.refcat/` | Cache storage directory |
| `Makefile` | refcat-* targets |

---

## Timeline

| Phase | Effort | Target |
|-------|--------|--------|
| Phase 1: Directory cache | 2 hours | Week 1 |
| Phase 2: File summaries | 3 hours | Week 1 |
| Phase 3: Cross-reference | 3 hours | Week 2 |
| Phase 4: sdqctl integration | 4 hours | Week 2 |
| **Total** | ~12 hours | 2 weeks |

---

## Alternatives Considered

### 1. Context Window Increase

**Pros**: No implementation needed  
**Cons**: Higher cost per token, doesn't reduce exploration

### 2. Smarter Exploration Heuristics

**Pros**: Could be combined with caching  
**Cons**: Harder to implement, less deterministic

### 3. Pre-computed Embeddings

**Pros**: Semantic search capability  
**Cons**: Much higher complexity, external dependencies

**Recommendation**: REFCAT caching is the most practical approach with best effort/reward ratio.

---

## Cross-References

- [iterate-effectiveness-report.md](iterate-effectiveness-report.md) - Source data
- [tooling.md](backlogs/tooling.md) - Backlog item #8
- [ECOSYSTEM-BACKLOG.md](ECOSYSTEM-BACKLOG.md) - Ready Queue #2
