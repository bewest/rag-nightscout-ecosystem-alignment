# Documentation Accuracy Backlog

> **Domain**: Bottom-up accuracy verification of documentation claims  
> **Parent**: [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md)  
> **Created**: 2026-01-29  
> **Purpose**: Systematic verification from evidence → mappings → analyses → proposals → gaps → traceability

---

## Verification Philosophy

Bottom-up approach ensures claims are grounded in evidence:

```
Level 1: Evidence Sources     (externals/*, source code)
    ↓
Level 2: Mappings             (mapping/*/README.md, nightscout-fields.md)
    ↓
Level 3: Deep Dive Analysis   (docs/10-domain/*-deep-dive.md)
    ↓  
Level 4: Gap Identification   (traceability/*-gaps.md)
    ↓
Level 5: Requirements         (traceability/*-requirements.md)
    ↓
Level 6: Proposals/Designs    (docs/sdqctl-proposals/*.md)
```

---

## Active Review Queue

### Level 1: Evidence Source Verification ✅ COMPLETE

| # | Item | Priority | Status | Result |
|---|------|----------|--------|--------|
| 1 | Verify CGM protocol code refs | P2 | ✅ Done | 91% valid (356/391) |
| 2 | Verify algorithm source refs | P2 | ✅ Done | Via #1 |
| 3 | Verify Nightscout API source refs | P2 | ✅ Done | Via #1 |
| 4 | Verify connector bridge refs | P2 | ✅ Done | Via #1 |

**Finding**: Active docs have 100% valid refs; 35 broken are in archives or intentional examples.

### Level 2: Mapping Accuracy Verification

| # | Item | Priority | Domain | Verification Method |
|---|------|----------|--------|---------------------|
| 5 | Audit mapping/xdrip/nightscout-fields.md | P2 | cgm-sources | Grep source for field names, confirm exists |
| 6 | Audit mapping/aaps/nsclient-upload.md | P2 | nightscout-api | Verify eventType strings in source |
| 7 | Audit mapping/loop/sync-identity-fields.md | P2 | sync-identity | Verify syncIdentifier usage in LoopKit |
| 8 | Audit mapping/trio/devicestatus-upload.md | P2 | nightscout-api | Verify openaps.* fields in Trio source |
| 9 | Audit terminology-matrix.md row by row | P3 | cross-project | Sample 10% of terms, verify in source |

### Level 3: Deep Dive Claim Verification

| # | Item | Priority | Domain | Status |
|---|------|----------|--------|--------|
| 10 | Verify cgm-data-sources-deep-dive.md claims | P2 | cgm-sources | Pending |
| 11 | Verify algorithm-comparison-deep-dive.md claims | P2 | aid-algorithms | Pending |
| 12 | Verify devicestatus-deep-dive.md claims | P2 | nightscout-api | Pending |
| 13 | Verify entries-deep-dive.md claims | P2 | nightscout-api | Pending |
| 14 | Verify treatments-deep-dive.md claims | P2 | nightscout-api | Pending |
| 15 | Verify pump-communication-deep-dive.md claims | P3 | pumps | Pending |
| 16 | Verify libre-protocol-deep-dive.md claims | P2 | cgm-sources | Pending |
| 17 | Verify g7-protocol-specification.md claims | P1 | cgm-sources | ✅ **100% accurate** |

### Level 4: Gap Verification

| # | Item | Priority | Domain | Status |
|---|------|----------|--------|--------|
| 18 | Verify GAP-CGM-* accuracy | P2 | cgm-sources | ✅ GAP-BLE-001/002 confirmed open |
| 19 | Verify GAP-ALG-* accuracy | P2 | aid-algorithms | Pending |
| 20 | Verify GAP-API-* accuracy | P2 | nightscout-api | Pending |
| 21 | Verify GAP-SYNC-* accuracy | P2 | sync-identity | Pending |
| 22 | Verify GAP-TREAT-* accuracy | P2 | treatments | Pending |
| 23 | Verify GAP-CONNECT-* accuracy | P2 | connectors | Pending |

### Level 5: Requirements Traceability

| # | Item | Priority | Domain | Verification Method |
|---|------|----------|--------|---------------------|
| 24 | Audit REQ-SYNC-* → scenario coverage | P2 | sync-identity | Run `python tools/verify_assertions.py` |
| 25 | Audit REQ-TREAT-* → scenario coverage | P2 | treatments | Verify each REQ has test scenario |
| 26 | Audit REQ-CONNECT-* completeness | P2 | connectors | Ensure all 28 GAPs have REQs |
| 27 | Audit REQ-API-* → OpenAPI alignment | P2 | nightscout-api | Check specs match requirements |

### Level 6: Proposal Coherence

| # | Item | Priority | Domain | Verification Method |
|---|------|----------|--------|---------------------|
| 28 | Audit algorithm-conformance-suite.md | P2 | aid-algorithms | Verify proposal vs actual runners |
| 29 | Audit statistics-api-proposal.md | P2 | nightscout-api | Check endpoint specs vs actual needs |
| 30 | Audit lsp-integration-proposal.md | P3 | tooling | Verify LSP claims |
| 31 | Audit nocturne-modernization-analysis.md | P2 | connectors | Cross-check with nocturne source |

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| Item #17: G7 protocol claims | 2026-01-29 | **100% accurate** - All opcodes, UUIDs, curves verified vs source |
| Item #1-4: Source refs | 2026-01-29 | **91% valid** (356/391), 2 intentional example refs |
| Broken refs fix (LSP claim verification) | 2026-01-29 | 3 refs fixed, 92% valid |
| Initial cohesiveness audit proposal | 2026-01-29 | Queued to this backlog |

### Verification Details: G7 Protocol (2026-01-29)

| Claim | Source | Status |
|-------|--------|--------|
| Service UUID `F8083532-...` | `DiaBLE/Dexcom.swift:51` | ✅ Verified |
| Characteristic 3535 (Auth) | `DiaBLE/DexcomG7.swift:54-58` | ✅ Verified |
| Characteristic 3534 (Control) | `DiaBLE/DexcomG7.swift:59-64` | ✅ Verified |
| 26 opcodes defined | `DiaBLE/DexcomG7.swift:20-47` | ✅ Verified |
| secp256r1 curve | `xDrip/libkeks/Curve.java:24` | ✅ Verified |
| J-PAKE auth flow | `xDrip/libkeks/Calc.java` | ✅ Verified |
| G7SensorKit files | `LoopWorkspace/G7SensorKit/...` | ✅ All 7 files exist |

---

## Tooling Gaps & Proposals

When verification is not possible with current tools, document here for sdqctl team:

### Currently Missing Tools

| Need | Current State | Proposal |
|------|---------------|----------|
| Cross-file claim verification | Manual grep | Extend verify_refs.py with claim patterns |
| Gap freshness check | No tool | `tools/verify_gap_freshness.py` - check if gap still exists |
| Mapping completeness | No tool | `tools/verify_mapping_coverage.py` - fields in source vs mapping |
| Terminology spot-check | No tool | `tools/sample_terminology.py` - random sample verification |

### Proposed Tool: `verify_gap_freshness.py`

**Purpose**: Check if documented gaps still exist in source code.

**Example**:
```bash
python tools/verify_gap_freshness.py --gap GAP-G7-001
# Output: GAP-G7-001: STILL OPEN - No G7 support in xDrip+
#         Evidence: grep "G7\|DexcomG7" externals/xDrip returns 0 matches
```

**Needed by**: Gap verification (items 18-23)

### Proposed Tool: `verify_mapping_coverage.py`

**Purpose**: Check that mapping docs cover fields actually used in source.

**Example**:
```bash
python tools/verify_mapping_coverage.py mapping/xdrip/nightscout-fields.md
# Output: Coverage: 87%
#         Missing from doc: transmitterBattery, sensorState
#         Extra in doc (not in source): rawNoise
```

**Needed by**: Mapping verification (items 5-9)

### Proposed Tool: `sample_terminology.py`

**Purpose**: Random sample verification of terminology matrix.

**Example**:
```bash
python tools/sample_terminology.py --sample-size 20
# Output: Sampling 20 terms from terminology-matrix.md...
#         ✓ ISF: Found in Loop (InsulinSensitivity.swift:45)
#         ✓ COB: Found in AAPS (CobInfo.kt:12)
#         ✗ UAM: Not found in nightguard (expected: n/a, claim: supports)
#         Accuracy: 95% (19/20)
```

**Needed by**: Terminology verification (item 9)

---

## Verification Commands Quick Reference

```bash
# Level 1: Source refs
python tools/verify_refs.py --json > traceability/refs-validation.json

# Level 2-3: Claim verification (manual + grep)
grep -r "syncIdentifier" externals/LoopWorkspace --include="*.swift" | head

# Level 4: Gap coverage
python tools/gen_coverage.py --json > traceability/coverage-analysis.json

# Level 5: Requirements traceability
python tools/verify_assertions.py

# Level 6: Cross-reference
make traceability
```

---

## Integration with sdqctl Workflows

```yaml
# Proposed: accuracy-audit.conv workflow
REFCAT:
  - docs/10-domain/*-deep-dive.md
  - mapping/*/README.md
  - traceability/*-gaps.md

GOAL: |
  Verify accuracy of claims in REFCAT files:
  1. Identify 3-5 specific claims with code refs
  2. Verify each claim against source
  3. Report accuracy percentage
  4. Flag any inaccuracies for correction

VERIFY: refs
```

---

## References

- [audit-verification-tooling-proposal.md](../audit-verification-tooling-proposal.md) - Tool designs
- [VERIFICATION-DIRECTIVES.md](../VERIFICATION-DIRECTIVES.md) - sdqctl verify commands
- [traceability/refs-validation.md](../../../traceability/refs-validation.md) - Latest validation report
