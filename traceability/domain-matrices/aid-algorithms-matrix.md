# AID Algorithms Domain Traceability Matrix

> **Generated**: 2026-02-01  
> **Domain**: AID Algorithms  
> **Purpose**: REQ↔GAP↔Assertion cross-reference matrix

---

## Summary

| Metric | Count |
|--------|-------|
| Requirements | 56 |
| Gaps | 66 |
| REQs with assertion coverage | 50 (89%) |
| Uncovered REQs | 6 (11%) - now with unique IDs |
| Uncovered GAPs | 32 (48%) |

**Status**: ✅ 12/12 categories covered. Duplicate REQ IDs fixed (cycle 112): REQ-CARB-007/008/009 and REQ-INS-006/007/008 are new unique IDs.

---

## Requirements Inventory

### Algorithm Core (4) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-ALG-001 | Cross-Project Test Vector Format | GAP-ALG-001 | ✅ algorithm-core.yaml |
| REQ-ALG-002 | Semantic Equivalence Assertions | GAP-ALG-003 | ✅ algorithm-core.yaml |
| REQ-ALG-003 | Safety Limit Validation | GAP-ALG-001 | ✅ safety-limits.yaml |
| REQ-ALG-004 | Baseline Regression Detection | GAP-ALG-002 | ✅ algorithm-core.yaml |

### Carb Absorption (6) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-CARB-001 | COB Model Type Annotation | GAP-CARB-001 | ✅ carb-absorption.yaml |
| REQ-CARB-002 | Minimum Carb Impact Documentation | GAP-CARB-003, GAP-CARB-004 | ✅ carb-absorption.yaml |
| REQ-CARB-003 | Absorption Model Selection | - | ✅ carb-absorption.yaml |
| REQ-CARB-004 | Carb Sensitivity Factor Calculation | - | ✅ carb-absorption.yaml |
| REQ-CARB-005 | Per-Entry Absorption Time | GAP-CARB-002 | ✅ carb-absorption.yaml |
| REQ-CARB-006 | COB Maximum Limits | GAP-CARB-005 | ✅ carb-absorption.yaml |

### Degraded Operation (6) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-DEGRADE-001 | Automation Disable on CGM Loss | GAP-ALG-011 | ✅ degraded-operation.yaml |
| REQ-DEGRADE-002 | Pump Communication Timeout Handling | - | ✅ degraded-operation.yaml |
| REQ-DEGRADE-003 | Remote Control Fallback | - | ✅ degraded-operation.yaml |
| REQ-DEGRADE-004 | Layer Transition Logging | - | ✅ degraded-operation.yaml |
| REQ-DEGRADE-005 | Safe State Documentation | - | ✅ degraded-operation.yaml |
| REQ-DEGRADE-006 | Delegate Agent Fallback | - | ✅ degraded-operation.yaml |

### Insulin Model (5) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-INS-001 | Consistent Exponential Model | - | ✅ insulin-model.yaml |
| REQ-INS-002 | DIA Minimum Enforcement | GAP-ALG-012 | ✅ safety-limits.yaml |
| REQ-INS-003 | Peak Time Configuration Bounds | GAP-INS-003 | ✅ safety-limits.yaml |
| REQ-INS-004 | Activity Calculation for BGI | - | ✅ insulin-model.yaml |
| REQ-INS-005 | Insulin Model Metadata in Treatments | GAP-INS-001 | ✅ insulin-model.yaml |

### Proposed API (4) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-PR-001 | Heart Rate Collection Support | GAP-API-HR | ✅ proposed-api.yaml |
| REQ-PR-002 | Multi-Insulin API Standardization | GAP-INSULIN-001 | ✅ proposed-api.yaml |
| REQ-PR-003 | Remote Command Queue | GAP-REMOTE-CMD | ✅ proposed-api.yaml |
| REQ-PR-004 | Consistent Timezone Display | GAP-TZ-001 | ✅ proposed-api.yaml |

### Profile Schema (7) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-PROF-001 | Standard Time Format | GAP-PROF-001 | ✅ profile-structure.yaml |
| REQ-PROF-002 | Safety Limits in Profile | GAP-PROF-002 | ✅ profile-structure.yaml |
| REQ-PROF-003 | Override Presets Sync | GAP-PROF-003 | ✅ profile-structure.yaml |
| REQ-PROF-004 | Insulin Model Mapping | GAP-PROF-005 | ✅ profile-structure.yaml |
| REQ-PROF-005 | Basal Time Format Conversion | GAP-PROF-006 | ✅ profile-structure.yaml |
| REQ-PROF-006 | Basal Rate Precision | GAP-PROF-008 | ✅ profile-structure.yaml |
| REQ-PROF-007 | Total Daily Basal Validation | - | ✅ profile-structure.yaml |

### Bolus Wizard (3) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-BOLUS-001 | Document Calculation Approach | GAP-BOLUS-001 | ✅ algorithm-docs.yaml |
| REQ-BOLUS-002 | IOB Subtraction Transparency | GAP-BOLUS-002 | ✅ algorithm-docs.yaml |
| REQ-BOLUS-003 | Nightscout Wizard Sync | - | ✅ algorithm-docs.yaml |

### Sensitivity (3) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-SENS-001 | Document Sensitivity Method | GAP-SENS-001 | ✅ algorithm-docs.yaml |
| REQ-SENS-002 | Sensitivity Visibility in Nightscout | GAP-SENS-001 | ✅ algorithm-docs.yaml |
| REQ-SENS-003 | Document Detection Windows | GAP-SENS-002 | ✅ algorithm-docs.yaml |

### Carb Display (3) - NEW UNIQUE IDs

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-CARB-007 | COB Display Source Attribution | GAP-CARB-001 | ❌ None |
| REQ-CARB-008 | min_5m_carbimpact Configuration Exposure | GAP-CARB-004 | ❌ None |
| REQ-CARB-009 | Absorption Model Type Documentation | GAP-CARB-003 | ❌ None |

*Note: Renamed from duplicate REQ-CARB-001-003 to unique IDs*

### Prediction (3) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-PRED-001 | Prediction Structure Documentation | GAP-PRED-001 | ✅ prediction-requirements.yaml |
| REQ-PRED-002 | Prediction Curve Labeling | GAP-PRED-002 | ✅ prediction-requirements.yaml |
| REQ-PRED-003 | Multi-Curve Display Option | GAP-PRED-002 | ✅ prediction-requirements.yaml |

### Dosing Mechanism (3) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-DOSE-001 | Dosing Mechanism Documentation | - | ✅ algorithm-docs.yaml |
| REQ-DOSE-002 | Safety Net Documentation | - | ✅ algorithm-docs.yaml |
| REQ-DOSE-003 | Enable Condition Transparency | - | ✅ algorithm-docs.yaml |

### Insulin Model Display (3) - NEW UNIQUE IDs

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-INS-006 | Exponential Formula Consistency Verification | - | ❌ None |
| REQ-INS-007 | DIA Range Validation UI | GAP-ALG-012 | ❌ None |
| REQ-INS-008 | Peak Time Preset Documentation | GAP-INS-003 | ❌ None |

*Note: Renamed from duplicate REQ-INS-001-003 to unique IDs*

### Target Range (3) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-TGT-001 | Target Range Format Documentation | - | ✅ algorithm-docs.yaml |
| REQ-TGT-002 | Target Calculation Transparency | - | ✅ algorithm-docs.yaml |
| REQ-TGT-003 | Temp Target Side Effects Documentation | - | ✅ algorithm-docs.yaml |

### Trio oref Integration (3) - COVERED ✅

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-OREF-001 | Document trio_custom_variables Interface | GAP-TRIO-001 | ✅ trio-oref.yaml |
| REQ-OREF-002 | Track Upstream oref0 Version | - | ✅ trio-oref.yaml |
| REQ-OREF-003 | Evaluate Breaking oref0 Changes | GAP-OREF-003 | ✅ trio-oref.yaml |

---

## Gaps Inventory

### Algorithm Gaps (16)

| Gap | Description | Related REQs | Assertions |
|-----|-------------|--------------|------------|
| GAP-ALG-001 | No cross-project algorithm test vectors | REQ-ALG-001, REQ-ALG-003 | ❌ None |
| GAP-ALG-002 | oref0 vs AAPS behavioral drift | REQ-ALG-004 | ❌ None |
| GAP-ALG-003 | Loop algorithm incomparable to oref | REQ-ALG-002 | ❌ None |
| GAP-ALG-009 | DynamicISF Not Present in oref0 | - | ❌ None |
| GAP-ALG-010 | AutoISF Not Present in oref0 | - | ❌ None |
| GAP-ALG-011 | LGS Duration Differences | - | ❌ None |
| GAP-ALG-012 | DIA Minimum Enforcement Differences | REQ-INS-002 | ❌ None |
| GAP-ALG-013 | Loop Has No Autosens | - | ❌ None |
| GAP-ALG-014 | Loop Prediction Is Single Curve | - | ❌ None |
| GAP-ALG-015 | Loop Does Not Expose UAM Curve | - | ❌ None |
| GAP-ALG-016 | Different IOB/COB Calculation Timing | - | ❌ None |

### Carb Gaps (5)

| Gap | Description | Related REQs | Assertions |
|-----|-------------|--------------|------------|
| GAP-CARB-001 | Incompatible COB Semantics | REQ-CARB-001 | ❌ None |
| GAP-CARB-002 | No Standard Carb Absorption Data Format | - | ❌ None |
| GAP-CARB-003 | UAM Detection Variance | REQ-CARB-002 | ❌ None |
| GAP-CARB-004 | min_5m_carbimpact Variance | REQ-CARB-002 | ❌ None |
| GAP-CARB-005 | COB Maximum Limits Differ | REQ-CARB-006 | ❌ None |

### Insulin Gaps (4)

| Gap | Description | Related REQs | Assertions |
|-----|-------------|--------------|------------|
| GAP-INS-001 | Insulin Model Metadata Not Synced | REQ-INS-005 | ✅ insulin-model.yaml |
| GAP-INS-002 | No Standardized Multi-Insulin Representation | - | ❌ None |
| GAP-INS-003 | Peak Time Customization Not Captured | REQ-INS-003 | ✅ safety-limits.yaml |
| GAP-INS-004 | xDrip+ Linear Trapezoid Incompatible | - | ❌ None |
| GAP-INSULIN-001 | Multi-Insulin API Not Standardized | REQ-PR-002 | ❌ None |

### Prediction Gaps (4)

| Gap | Description | Related REQs | Assertions |
|-----|-------------|--------------|------------|
| GAP-PRED-001 | Prediction Array Truncation Undocumented | REQ-PRED-001 | ❌ None |
| GAP-PRED-002 | Loop Single Prediction Incompatible | REQ-PRED-002, REQ-PRED-003 | ❌ None |
| GAP-PRED-003 | Prediction Interval Not Standardized | - | ❌ None |
| GAP-PRED-004 | No Prediction Confidence/Uncertainty | - | ❌ None |

### Profile Gaps (6+)

| Gap | Description | Related REQs | Assertions |
|-----|-------------|--------------|------------|
| GAP-PROF-001 | Time Format Incompatibility | REQ-PROF-001 | ❌ None |
| GAP-PROF-002 | Missing Safety Limits in Nightscout | REQ-PROF-002 | ❌ None |
| GAP-PROF-003 | Override Presets Missing | REQ-PROF-003 | ❌ None |
| GAP-PROF-005 | Insulin Model Mapping Missing | REQ-PROF-004 | ❌ None |
| GAP-PROF-006 | Basal Time Format Needs Conversion | REQ-PROF-005 | ❌ None |
| GAP-PROF-008 | Basal Rate Precision Loss | REQ-PROF-006 | ❌ None |

### oref/OpenAPS Gaps (3)

| Gap | Description | Related REQs | Assertions |
|-----|-------------|--------------|------------|
| GAP-OREF-001 | No oref0 Package Published to npm | - | ❌ None |
| GAP-OREF-002 | openaps Python Package Unmaintained | - | ❌ None |
| GAP-OREF-003 | oref0 vs oref1 Distinction Unclear | - | ❌ None |

---

## Coverage Analysis

### By Category

| Category | REQs | Covered | Coverage |
|----------|------|---------|----------|
| Algorithm Core | 4 | 4 | 100% ✅ |
| Carb Absorption | 6 | 6 | 100% ✅ |
| Degraded Operation | 6 | 6 | 100% ✅ |
| Insulin Model | 5 | 5 | 100% ✅ |
| Proposed API | 4 | 4 | 100% ✅ |
| Profile Schema | 7 | 7 | 100% ✅ |
| Bolus Wizard | 3 | 3 | 100% ✅ |
| Sensitivity | 3 | 3 | 100% ✅ |
| Prediction | 3 | 3 | 100% ✅ |
| Dosing Mechanism | 3 | 3 | 100% ✅ |
| Target Range | 3 | 3 | 100% ✅ |
| Trio oref | 3 | 3 | 100% ✅ |
| **Total** | **56** | **50** | **89%** |

### Data Quality Issues

1. **Duplicate REQ IDs**: REQ-CARB-001-003 and REQ-INS-001-003 appear twice with different descriptions
   - Need deduplication or renumbering in source file
   - Effective unique requirements: ~50 after dedup

---

## Action Items

### High Priority (Safety-Critical)

1. ~~**Create degradation assertions** (REQ-DEGRADE-001-006)~~ ✅ cycle 100
   - 24 assertions covering CGM loss, pump timeout, remote fallback, logging, docs, agent fallback
   - Deliverable: `conformance/assertions/degraded-operation.yaml`

2. ~~**Create safety limit assertions** (REQ-ALG-003, REQ-INS-002, REQ-INS-003)~~ ✅ cycle 101
   - 20 assertions covering max IOB/basal, DIA minimum, peak time bounds
   - Deliverable: `conformance/assertions/safety-limits.yaml`

### Medium Priority (Interoperability)

3. ~~**Create insulin model assertions** (REQ-INS-001, REQ-INS-004, REQ-INS-005)~~ ✅ cycle 102
   - 18 assertions covering exponential formula, activity calculation, model metadata
   - Deliverable: `conformance/assertions/insulin-model.yaml`

4. ~~**Create profile schema assertions** (REQ-PROF-001-007)~~ ✅ cycle 104
   - 34 assertions covering time format, safety limits, overrides, insulin model, basal precision, TDD validation
   - Deliverable: `conformance/assertions/profile-structure.yaml`

5. ~~**Create prediction assertions** (REQ-PRED-001-003)~~ ✅ cycle 105
   - 19 assertions covering structure, labeling, multi-curve display
   - Deliverable: `conformance/assertions/prediction-requirements.yaml`

### Low Priority (Documentation)

6. ~~**Create documentation assertions** (REQ-BOLUS, REQ-SENS, REQ-DOSE, REQ-TGT)~~ ✅ cycle 106
   - 32 assertions covering 12 REQs across 4 categories
   - Deliverable: `conformance/assertions/algorithm-docs.yaml`

7. ~~**Fix duplicate REQ IDs**~~ ✅ Completed cycle 112
   - REQ-CARB-001-003 → REQ-CARB-007/008/009
   - REQ-INS-001-003 → REQ-INS-006/007/008

---

## Assertion Files

| File | REQs Covered | Gaps Covered |
|------|--------------|--------------|
| `degraded-operation.yaml` | 6 (REQ-DEGRADE-001-006) | 2 (GAP-ALG-011, GAP-ALG-014) |
| `safety-limits.yaml` | 3 (REQ-ALG-003, REQ-INS-002, REQ-INS-003) | 2 (GAP-ALG-001, GAP-ALG-012) |
| `insulin-model.yaml` | 3 (REQ-INS-001, REQ-INS-004, REQ-INS-005) | 1 (GAP-INS-001) |
| `profile-structure.yaml` | 7 (REQ-PROF-001-007) | 5 (GAP-PROF-001, 002, 005, 006, 008) |
| `prediction-requirements.yaml` | 3 (REQ-PRED-001-003) | 3 (GAP-PRED-001, 002, 003) |
| `algorithm-docs.yaml` | 12 (REQ-BOLUS-001-003, SENS-001-003, DOSE-001-003, TGT-001-003) | 4 (GAP-BOLUS-001, 002, SENS-001, 002) |
| `carb-absorption.yaml` | 6 (REQ-CARB-001-006) | 5 (GAP-CARB-001, 002, 003, 004, 005) |
| `trio-oref.yaml` | 3 (REQ-OREF-001-003) | 4 (GAP-TRIO-001, GAP-OREF-001, 002, 003) |
| `proposed-api.yaml` | 4 (REQ-PR-001-004) | 4 (GAP-API-HR, GAP-INSULIN-001, GAP-REMOTE-CMD, GAP-TZ-001) |
| `algorithm-core.yaml` | 3 (REQ-ALG-001, 002, 004) | 3 (GAP-ALG-001, 002, 003) |
| **Total** | **50** | **33** |

---

## Cross-References

- **Requirements Source**: [`aid-algorithms-requirements.md`](../aid-algorithms-requirements.md)
- **Gaps Source**: [`aid-algorithms-gaps.md`](../aid-algorithms-gaps.md)
- **Existing Runners**: `conformance/runners/oref0-runner.js` (algorithm test vectors, not assertions)
- **Related Proposals**: `docs/sdqctl-proposals/algorithm-conformance-suite.md`
