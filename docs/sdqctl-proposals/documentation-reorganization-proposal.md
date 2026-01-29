# Documentation Reorganization Proposal

> **Purpose**: Optimize documentation structure for AI and human comprehension  
> **Generated**: 2026-01-29  
> **Status**: Proposal

---

## Executive Summary

The workspace has **193 markdown files** totaling **74,644 lines** across 5 major directories. The structure is generally well-organized but has some areas for improvement.

| Directory | Files | Lines | Purpose |
|-----------|-------|-------|---------|
| docs/10-domain | 41 | 19,125 | Deep dives and comparisons |
| docs/60-research | 8 | 5,512 | Research and proposals |
| docs/sdqctl-proposals | 14 | 5,023 | Workflow proposals |
| mapping | 106 | 36,830 | Cross-project field mappings |
| traceability | 24 | 8,154 | Gaps and requirements |

---

## Current Structure Analysis

### Strengths

1. **Clear separation of concerns**
   - `docs/10-domain/` for technical deep dives
   - `mapping/` for cross-project terminology
   - `traceability/` for gaps and requirements

2. **Consistent naming conventions**
   - `*-deep-dive.md` for comprehensive analysis
   - `*-comparison.md` for cross-system comparisons
   - `*-proposal.md` for recommendations

3. **Well-chunked traceability**
   - Gaps split into 7 domain files
   - Requirements organized by domain
   - Index files for navigation

### Areas for Improvement

1. **Topic fragmentation**
   - Carb absorption: 2 files (comparison + deep-dive)
   - Profile: 3 files across different directories
   - Could consolidate or add cross-references

2. **Directory naming inconsistency**
   - `docs/10-domain/` (numbered prefix)
   - `docs/60-research/` (numbered prefix)
   - `docs/sdqctl-proposals/` (no prefix)

3. **Missing index files**
   - `docs/10-domain/` has no README or index
   - `mapping/` subdirectories lack indexes

---

## AI vs Human Comprehension

### AI Optimization Needs

| Need | Current State | Recommendation |
|------|---------------|----------------|
| **Context limits** | Large files exist but manageable | ✅ No action needed |
| **Cross-references** | Good use of relative links | ✅ No action needed |
| **Search patterns** | Consistent gap IDs (GAP-XXX-NNN) | ✅ No action needed |
| **File discovery** | grep/glob work well | ✅ No action needed |
| **Section navigation** | TOC missing in large files | ⚠️ Add TOCs |

### Human Optimization Needs

| Need | Current State | Recommendation |
|------|---------------|----------------|
| **Entry points** | README.md exists at root | ✅ Good |
| **Topic discovery** | No unified topic index | ⚠️ Add topic index |
| **Learning path** | No suggested reading order | ⚠️ Document in README |
| **Status visibility** | progress.md tracks completions | ✅ Good |

---

## Identified Overlaps

### Carb Absorption (2 files)

| File | Lines | Content |
|------|-------|---------|
| `carb-absorption-deep-dive.md` | 471 | Technical deep dive |
| `carb-absorption-comparison.md` | 318 | Cross-system comparison |

**Recommendation**: Keep separate. Deep dive is technical reference, comparison is cross-system analysis.

### Profile/Therapy Settings (3 files)

| File | Lines | Location |
|------|-------|----------|
| `profile-therapy-settings-comparison.md` | 557 | docs/60-research |
| `profile-model-evolution-proposal.md` | 548 | docs/60-research |
| `override-profile-switch-comparison.md` | 416 | docs/10-domain |

**Recommendation**: Add cross-references. Consider moving profile comparison to 10-domain for consistency.

### API Documentation (multiple files)

| File | Focus |
|------|-------|
| `nightscout-api-comparison.md` | v1 vs v2 vs v3 |
| `nightscout-apiv3-deep-dive.md` | v3 internals |
| `nightscout-api-requirements.md` | Requirements |
| `nightscout-api-gaps.md` | Gaps |

**Recommendation**: ✅ Appropriate separation. Each serves different purpose.

---

## Recommendations

### Priority 1: Quick Wins (Low Effort)

1. **Add index to docs/10-domain/**
   ```markdown
   # Domain Deep Dives
   
   ## By Topic
   - CGM: [cgm-data-sources-deep-dive.md](cgm-data-sources-deep-dive.md)
   - Algorithms: [algorithm-comparison-deep-dive.md](...)
   - ...
   ```

2. **Add TOC to terminology-matrix.md**
   - Already identified in large file analysis
   - Enables section navigation

3. **Add cross-references between related files**
   - Profile files should reference each other
   - Carb absorption files should link

### Priority 2: Structure Improvements (Medium Effort)

1. **Standardize directory prefixes**
   - Rename `docs/sdqctl-proposals/` to `docs/40-proposals/`
   - Maintains numerical ordering

2. **Create topic-based navigation**
   - Add `docs/00-overview/topics.md`
   - Group by: CGM, Algorithms, Sync, Treatments, Profiles

3. **Move profile comparison**
   - Move `profile-therapy-settings-comparison.md` from research to domain
   - Research is for proposals, not completed analysis

### Priority 3: Content Consolidation (Higher Effort)

1. **Merge carb absorption files** (Optional)
   - Could combine into single comprehensive document
   - Current separation is acceptable

2. **Create unified "getting started" guide**
   - For new contributors
   - Explains workspace structure and conventions

---

## Proposed Structure

```
docs/
├── 00-overview/
│   ├── README.md (entry point)
│   ├── topics.md (topic-based navigation)
│   └── getting-started.md (new)
├── 10-domain/
│   ├── README.md (new - index)
│   ├── *-deep-dive.md
│   └── *-comparison.md
├── 30-design/
│   └── (architecture decisions)
├── 40-proposals/ (renamed from sdqctl-proposals)
│   ├── README.md
│   └── *.md
├── 60-research/
│   ├── README.md
│   └── *.md (proposals and research)
├── 90-decisions/
│   └── (ADRs)
└── archive/
    └── (historical)
```

---

## Action Items

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| P1 | Add README to docs/10-domain/ | Low | Medium |
| P1 | Add TOC to terminology-matrix.md | Low | Medium |
| P2 | Add cross-references to profile files | Low | Low |
| P2 | Create docs/00-overview/topics.md | Medium | Medium |
| P3 | Rename sdqctl-proposals to 40-proposals | Low | Low |
| P3 | Move profile comparison to 10-domain | Low | Low |
| P4 | Create getting-started.md | Medium | Medium |

---

## Conclusion

The current documentation structure is **fundamentally sound**. The numbered directory prefixes (`10-domain`, `60-research`) provide logical ordering. The main opportunities are:

1. **Add index files** for better navigation
2. **Add cross-references** between related topics
3. **Standardize naming** for `sdqctl-proposals`

**No major reorganization is needed.** The workspace is well-organized for both AI and human use.

---

## Cross-References

- [Large File Analysis](large-file-analysis.md) - Related analysis
- [TOOLING-GUIDE.md](../TOOLING-GUIDE.md) - Workspace tools
- [README.md](../../README.md) - Project entry point
