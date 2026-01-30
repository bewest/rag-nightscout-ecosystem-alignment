# Tool Coverage Audit

> **Date**: 2026-01-30  
> **Source**: tooling.md #18  
> **Purpose**: Document what each verification tool parses and identifies gaps

---

## Summary

| Metric | Value |
|--------|-------|
| Total verification tools | 7 |
| Active tools (scan files) | 6 |
| Total docs in workspace | 351 |
| Docs with tool coverage | 313 (89%) |
| Docs without coverage | 38 (11%) |

---

## Tool Coverage Matrix

| Tool | Purpose | Scan Patterns | Files | Status |
|------|---------|---------------|-------|--------|
| `verify_refs` | Validate code refs to externals/ | `mapping/**/*.md`, `docs/**/*.md`, `specs/**/*.yaml` | 300 | ✅ Active |
| `verify_mapping_coverage` | Field mappings vs source | `mapping/**/*.md` | 123 | ✅ Active |
| `verify_gap_freshness` | Check gaps still open | `traceability/*-gaps.md` | 7 | ✅ Active |
| `verify_assertions` | Trace assertions→REQ/GAP | `conformance/assertions/**/*.yaml` | 4 | ✅ Active |
| `verify_coverage` | REQ/GAP coverage analysis | `traceability/requirements.md`, `gaps.md` | 2 | ⚠️ Broken |
| `verify_terminology` | Term consistency | `mapping/cross-project/terminology-matrix.md` | 1 | ✅ Active |
| `verify_hello` | Plugin health check | (none) | 0 | ✅ Utility |

---

## Findings

### 1. ~~verify_coverage is Broken~~ ✅ FIXED (Cycle 23)

**Symptom**: Reports 0 requirements when `verify_assertions` finds 247.

**Root Cause**: `verify_coverage` looks for `requirements.md` and `gaps.md` directly, but the actual requirements are in domain-specific files like `*-requirements.md`.

**Impact**: Coverage analysis unreliable.

**Remediation**: ✅ Fixed in cycle 23 - now scans `*-requirements.md` and `*-gaps.md` patterns + updated REQ regex for `REQ-DOMAIN-NNN` format. Result: 0→242 reqs, 0→289 gaps.

### 2. Conformance .md Files Not Validated

**Files**: 9 markdown files in `conformance/` (READMEs, scenarios)

**Tools That Skip**:
- `verify_refs` only scans mapping/docs/specs
- No tool validates conformance scenario READMEs

**Remediation**: Extend `verify_refs` to include `conformance/**/*.md`.

### 3. High-Value Coverage Areas

| Directory | Files | Coverage Tool |
|-----------|-------|---------------|
| mapping/ | 123 | verify_refs, verify_mapping_coverage, verify_terminology |
| docs/ | 169 | verify_refs |
| traceability/ | 9 | verify_assertions, verify_coverage, verify_gap_freshness |
| specs/ | 8 | verify_refs |
| conformance/ | 4 YAML, 9 MD | verify_assertions (YAML only) |

### 4. Tool Overlap

- **mapping/**:  Covered by 3 tools (verify_refs, verify_mapping_coverage, verify_terminology)
- **traceability/**: Covered by 3 tools (verify_assertions, verify_coverage, verify_gap_freshness)
- **docs/**: Covered by 1 tool (verify_refs)
- **conformance/**: YAML covered, MD not covered

---

## Recommendations

### P1: Fix verify_coverage

```python
# Change from:
requirements = extract_requirements(TRACEABILITY_DIR / "requirements.md")

# To:
for req_file in TRACEABILITY_DIR.glob("*-requirements.md"):
    requirements.update(extract_requirements(req_file))
```

### ~~P1: Fix verify_coverage~~ ✅ COMPLETE (Cycle 23)

### P2: Extend verify_refs to conformance/

Add `conformance/**/*.md` to scan patterns.

### P3: Add docs/ deep-dive tool

`docs/` only validated for code refs. No semantic validation of:
- Claim accuracy
- Cross-document consistency
- Outdated recommendations

---

## Coverage Gaps by File Type

| Pattern | Files | Covered By | Gap |
|---------|-------|------------|-----|
| `mapping/**/*.md` | 123 | 3 tools | ✅ Good |
| `docs/**/*.md` | 169 | 1 tool | ⚠️ Only code refs |
| `traceability/**/*.md` | 9 | 3 tools | ✅ Good |
| `specs/**/*.yaml` | 8 | 1 tool | ⚠️ Only code refs |
| `conformance/**/*.yaml` | 4 | 1 tool | ✅ Assertions |
| `conformance/**/*.md` | 9 | 0 tools | ❌ No coverage |

---

## Next Steps

1. ~~**Fix verify_coverage** (tooling.md #21) - P1~~ ✅ COMPLETE
2. **Extend verify_refs** (tooling.md #22) - P2
3. **Documentation parse audit** (tooling.md #19) - P1
3. **Documentation parse audit** (tooling.md #19) - In progress
