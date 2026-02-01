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
| REQs with assertion coverage | 0 (0%) |
| Uncovered REQs | 56 (100%) |
| Uncovered GAPs | 66 (100%) |

**Status**: ❌ **NEEDS WORK** - No conformance assertions exist for algorithm domain

---

## Requirements Inventory

### Algorithm Core (4)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-ALG-001 | Cross-Project Test Vector Format | GAP-ALG-001 | ❌ None |
| REQ-ALG-002 | Semantic Equivalence Assertions | GAP-ALG-003 | ❌ None |
| REQ-ALG-003 | Safety Limit Validation | GAP-ALG-001 | ❌ None |
| REQ-ALG-004 | Baseline Regression Detection | GAP-ALG-002 | ❌ None |

### Carb Absorption (6)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-CARB-001 | COB Model Type Annotation | GAP-CARB-001 | ❌ None |
| REQ-CARB-002 | Minimum Carb Impact Documentation | GAP-CARB-003, GAP-CARB-004 | ❌ None |
| REQ-CARB-003 | Absorption Model Selection | - | ❌ None |
| REQ-CARB-004 | Carb Sensitivity Factor Calculation | - | ❌ None |
| REQ-CARB-005 | Per-Entry Absorption Time | - | ❌ None |
| REQ-CARB-006 | COB Maximum Limits | GAP-CARB-005 | ❌ None |

### Degraded Operation (6)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-DEGRADE-001 | Automation Disable on CGM Loss | - | ❌ None |
| REQ-DEGRADE-002 | Pump Communication Timeout Handling | - | ❌ None |
| REQ-DEGRADE-003 | Remote Control Fallback | - | ❌ None |
| REQ-DEGRADE-004 | Layer Transition Logging | - | ❌ None |
| REQ-DEGRADE-005 | Safe State Documentation | - | ❌ None |
| REQ-DEGRADE-006 | Delegate Agent Fallback | - | ❌ None |

### Insulin Model (5)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-INS-001 | Consistent Exponential Model | - | ❌ None |
| REQ-INS-002 | DIA Minimum Enforcement | GAP-ALG-012 | ❌ None |
| REQ-INS-003 | Peak Time Configuration Bounds | GAP-INS-003 | ❌ None |
| REQ-INS-004 | Activity Calculation for BGI | - | ❌ None |
| REQ-INS-005 | Insulin Model Metadata in Treatments | GAP-INS-001 | ❌ None |

### Proposed API (4)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-PR-001 | Heart Rate Collection Support | GAP-API-HR | ❌ None |
| REQ-PR-002 | Multi-Insulin API Standardization | GAP-INSULIN-001 | ❌ None |
| REQ-PR-003 | Remote Command Queue | GAP-REMOTE-CMD | ❌ None |
| REQ-PR-004 | Consistent Timezone Display | GAP-TZ-001 | ❌ None |

### Profile Schema (7)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-PROF-001 | Standard Time Format | GAP-PROF-001 | ❌ None |
| REQ-PROF-002 | Safety Limits in Profile | GAP-PROF-002 | ❌ None |
| REQ-PROF-003 | Override Presets Sync | GAP-PROF-003 | ❌ None |
| REQ-PROF-004 | Insulin Model Mapping | GAP-PROF-005 | ❌ None |
| REQ-PROF-005 | Basal Time Format Conversion | GAP-PROF-006 | ❌ None |
| REQ-PROF-006 | Basal Rate Precision | GAP-PROF-008 | ❌ None |
| REQ-PROF-007 | Total Daily Basal Validation | - | ❌ None |

### Bolus Wizard (3)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-BOLUS-001 | Document Calculation Approach | GAP-BOLUS-001 | ❌ None |
| REQ-BOLUS-002 | IOB Subtraction Transparency | GAP-BOLUS-002 | ❌ None |
| REQ-BOLUS-003 | Nightscout Wizard Sync | - | ❌ None |

### Sensitivity (3)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-SENS-001 | Document Sensitivity Method | GAP-SENS-001 | ❌ None |
| REQ-SENS-002 | Sensitivity Visibility in Nightscout | GAP-SENS-001 | ❌ None |
| REQ-SENS-003 | Document Detection Windows | GAP-SENS-002 | ❌ None |

### Carb Display (3) - Overlaps with Carb Absorption

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-CARB-001* | COB Display Source Attribution | GAP-CARB-001 | ❌ None |
| REQ-CARB-002* | min_5m_carbimpact Configuration | GAP-CARB-004 | ❌ None |
| REQ-CARB-003* | Absorption Model Documentation | GAP-CARB-003 | ❌ None |

*Note: Duplicate REQ-CARB IDs exist in source file - need deduplication*

### Prediction (3)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-PRED-001 | Prediction Structure Documentation | GAP-PRED-001 | ❌ None |
| REQ-PRED-002 | Prediction Curve Labeling | GAP-PRED-002 | ❌ None |
| REQ-PRED-003 | Multi-Curve Display Option | GAP-PRED-002 | ❌ None |

### Dosing Mechanism (3)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-DOSE-001 | Dosing Mechanism Documentation | - | ❌ None |
| REQ-DOSE-002 | Safety Net Documentation | - | ❌ None |
| REQ-DOSE-003 | Enable Condition Transparency | - | ❌ None |

### Insulin Model (3) - Overlaps with earlier section

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-INS-001* | Exponential Formula Consistency | - | ❌ None |
| REQ-INS-002* | DIA Range Validation | GAP-ALG-012 | ❌ None |
| REQ-INS-003* | Peak Time Documentation | GAP-INS-003 | ❌ None |

*Note: Duplicate REQ-INS IDs exist in source file - need deduplication*

### Target Range (3)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-TGT-001 | Target Range Format Documentation | - | ❌ None |
| REQ-TGT-002 | Target Calculation Transparency | - | ❌ None |
| REQ-TGT-003 | Temp Target Side Effects Documentation | - | ❌ None |

### Trio oref Integration (3)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-OREF-001 | Document trio_custom_variables Interface | - | ❌ None |
| REQ-OREF-002 | Track Upstream oref0 Version | - | ❌ None |
| REQ-OREF-003 | Evaluate Breaking oref0 Changes | - | ❌ None |

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
| GAP-INS-001 | Insulin Model Metadata Not Synced | REQ-INS-005 | ❌ None |
| GAP-INS-002 | No Standardized Multi-Insulin Representation | - | ❌ None |
| GAP-INS-003 | Peak Time Customization Not Captured | REQ-INS-003 | ❌ None |
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
| Algorithm Core | 4 | 0 | 0% |
| Carb Absorption | 6 | 0 | 0% |
| Degraded Operation | 6 | 0 | 0% |
| Insulin Model | 5 | 0 | 0% |
| Proposed API | 4 | 0 | 0% |
| Profile Schema | 7 | 0 | 0% |
| Bolus Wizard | 3 | 0 | 0% |
| Sensitivity | 3 | 0 | 0% |
| Prediction | 3 | 0 | 0% |
| Dosing Mechanism | 3 | 0 | 0% |
| Target Range | 3 | 0 | 0% |
| Trio oref | 3 | 0 | 0% |
| **Total** | **56** | **0** | **0%** |

### Data Quality Issues

1. **Duplicate REQ IDs**: REQ-CARB-001-003 and REQ-INS-001-003 appear twice with different descriptions
   - Need deduplication or renumbering in source file
   - Effective unique requirements: ~50 after dedup

---

## Action Items

### High Priority (Safety-Critical)

1. **Create degradation assertions** (REQ-DEGRADE-001-006)
   - CGM loss handling
   - Pump timeout behavior
   - Layer transition logging
   - Deliverable: `conformance/assertions/degraded-operation.yaml`

2. **Create safety limit assertions** (REQ-ALG-003, REQ-INS-002)
   - Max IOB/basal enforcement
   - DIA minimum validation
   - Peak time bounds
   - Deliverable: `conformance/assertions/safety-limits.yaml`

### Medium Priority (Interoperability)

3. **Create insulin model assertions** (REQ-INS-001-005)
   - Exponential formula verification
   - Model metadata sync
   - Deliverable: `conformance/assertions/insulin-model.yaml`

4. **Create profile schema assertions** (REQ-PROF-001-007)
   - Time format conversion
   - Safety limits presence
   - Override presets structure
   - Deliverable: `conformance/assertions/profile-requirements.yaml`

5. **Create prediction assertions** (REQ-PRED-001-003)
   - Curve structure documentation
   - Multi-curve display
   - Deliverable: `conformance/assertions/prediction-requirements.yaml`

### Low Priority (Documentation)

6. **Create documentation assertions** (REQ-BOLUS, REQ-SENS, REQ-DOSE, REQ-TGT)
   - Calculation approach docs
   - Sensitivity method docs
   - Dosing mechanism docs
   - Deliverable: `conformance/assertions/algorithm-docs.yaml`

7. **Fix duplicate REQ IDs** in `aid-algorithms-requirements.md`
   - REQ-CARB-001-003 appears twice
   - REQ-INS-001-003 appears twice

---

## Assertion Files

| File | REQs Covered | Gaps Covered |
|------|--------------|--------------|
| (none yet) | 0 | 0 |
| **Total** | **0** | **0** |

---

## Cross-References

- **Requirements Source**: [`aid-algorithms-requirements.md`](../aid-algorithms-requirements.md)
- **Gaps Source**: [`aid-algorithms-gaps.md`](../aid-algorithms-gaps.md)
- **Existing Runners**: `conformance/runners/oref0-runner.js` (algorithm test vectors, not assertions)
- **Related Proposals**: `docs/sdqctl-proposals/algorithm-conformance-suite.md`
