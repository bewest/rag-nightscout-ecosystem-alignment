# cgm-remote-monitor Analysis Depth Matrix

> **Created**: 2026-01-30  
> **Source**: nightscout-api.md #18  
> **Purpose**: Completeness grid showing analysis depth per Nightscout collection

---

## Overview

This matrix tracks the depth of analysis for each Nightscout API collection across multiple dimensions.

---

## Analysis Depth Matrix

| Collection | Schema Spec | Deep Dive | Gap Analysis | Requirements | Assertions | Ontology |
|------------|-------------|-----------|--------------|--------------|------------|----------|
| **entries** | ✅ `aid-entries-2025.yaml` | ✅ `entries-deep-dive.md` | ⚠️ 1 GAP-ENTRY | ⚠️ Partial | ⚠️ Partial | Observed |
| **treatments** | ✅ `aid-treatments-2025.yaml` | ✅ `treatments-deep-dive.md` | ✅ 9 GAP-TREAT | ✅ REQ-TREAT | ✅ 3 files | Mixed |
| **devicestatus** | ✅ `aid-devicestatus-2025.yaml` | ✅ `devicestatus-deep-dive.md` | ✅ 8 GAP-DS | ⚠️ Partial | ⚠️ Partial | Mixed |
| **profile** | ✅ `aid-profile-2025.yaml` | ✅ Multiple docs | ✅ 12 GAP-PROF | ✅ REQ-PROF | ⚠️ Partial | Desired |
| **food** | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | Desired |
| **activity** | ❌ None | ❌ None | ❌ None | ❌ None | ❌ None | Observed |

**Legend**:
- ✅ Complete or substantial coverage
- ⚠️ Partial coverage
- ❌ No coverage

---

## Detailed Breakdown

### entries (SGV, MBG, calibration)

| Dimension | Status | Details |
|-----------|--------|---------|
| **Schema Spec** | ✅ Complete | `specs/openapi/aid-entries-2025.yaml` |
| **Deep Dive** | ✅ Complete | `docs/10-domain/entries-deep-dive.md` |
| **Gap Analysis** | ⚠️ Partial | 1 GAP-ENTRY identified |
| **Requirements** | ⚠️ Partial | REQ-API-* covers API behavior |
| **Assertions** | ⚠️ Partial | Direction mapping tested |
| **Ontology** | ✅ Classified | 100% Observed |

**Coverage Score**: 4/6 (67%)

### treatments (bolus, carbs, temp basal, overrides)

| Dimension | Status | Details |
|-----------|--------|---------|
| **Schema Spec** | ✅ Complete | `specs/openapi/aid-treatments-2025.yaml` |
| **Deep Dive** | ✅ Complete | `docs/10-domain/treatments-deep-dive.md` |
| **Gap Analysis** | ✅ Complete | 9 GAP-TREAT entries |
| **Requirements** | ✅ Complete | REQ-TREAT-* series |
| **Assertions** | ✅ Complete | `conformance/assertions/treatment-sync.yaml` |
| **Ontology** | ✅ Classified | Mixed (40% Observed, 35% Desired, 25% Control) |

**Coverage Score**: 6/6 (100%)

### devicestatus (loop, openaps, pump, uploader)

| Dimension | Status | Details |
|-----------|--------|---------|
| **Schema Spec** | ✅ Complete | `specs/openapi/aid-devicestatus-2025.yaml` |
| **Deep Dive** | ✅ Complete | `docs/10-domain/devicestatus-deep-dive.md`, `nightscout-devicestatus-schema-audit.md` |
| **Gap Analysis** | ✅ Complete | 8 GAP-DS entries |
| **Requirements** | ⚠️ Partial | Some REQ-DS-* defined |
| **Assertions** | ⚠️ Partial | No dedicated assertion file |
| **Ontology** | ✅ Classified | Mixed (30% Observed, 70% Control) |

**Coverage Score**: 4.5/6 (75%)

### profile (basal, ISF, CR, targets)

| Dimension | Status | Details |
|-----------|--------|---------|
| **Schema Spec** | ✅ Complete | `specs/openapi/aid-profile-2025.yaml` |
| **Deep Dive** | ✅ Complete | Multiple: `profile-schema-alignment.md`, `profile-switch-sync-comparison.md`, nocturne analyses |
| **Gap Analysis** | ✅ Complete | 12 GAP-PROF entries |
| **Requirements** | ✅ Complete | REQ-PROF-*, REQ-SYNC-* (profile) |
| **Assertions** | ⚠️ Partial | Override-related assertions only |
| **Ontology** | ✅ Classified | 100% Desired |

**Coverage Score**: 5/6 (83%)

### food (nutritional database)

| Dimension | Status | Details |
|-----------|--------|---------|
| **Schema Spec** | ❌ None | Not in aid-* specs |
| **Deep Dive** | ❌ None | No documentation |
| **Gap Analysis** | ❌ None | No GAP-FOOD entries |
| **Requirements** | ❌ None | No requirements |
| **Assertions** | ❌ None | No assertions |
| **Ontology** | ✅ Known | Desired (user nutritional data) |

**Coverage Score**: 0.5/6 (8%)

### activity (exercise, steps)

| Dimension | Status | Details |
|-----------|--------|---------|
| **Schema Spec** | ❌ None | Not in aid-* specs |
| **Deep Dive** | ❌ None | No documentation |
| **Gap Analysis** | ❌ None | No GAP-ACTIVITY entries |
| **Requirements** | ❌ None | No requirements |
| **Assertions** | ❌ None | No assertions |
| **Ontology** | ✅ Known | Observed (activity data) |

**Coverage Score**: 0.5/6 (8%)

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Collections analyzed | 6 |
| Fully covered (>80%) | 2 (treatments, profile) |
| Partially covered (50-80%) | 2 (entries, devicestatus) |
| Not covered (<50%) | 2 (food, activity) |
| Average coverage | 57% |

---

## Recommendations

### P1: Add food/activity specs
- Low usage but needed for completeness
- Consider minimal `aid-food-2025.yaml` and `aid-activity-2025.yaml`

### P2: Complete entries gap analysis
- Only 1 GAP-ENTRY identified
- Likely more gaps exist (direction mapping, calibration sync)

### P3: Add devicestatus assertions
- Schema complete but no assertion coverage
- Add `conformance/assertions/devicestatus-sync.yaml`

---

## Related Documents

- [state-ontology.md](../architecture/state-ontology.md) - Ontology categories
- [nightscout-api-comparison.md](nightscout-api-comparison.md) - API version differences
- [terminology-matrix.md](../../mapping/cross-project/terminology-matrix.md) - Field mappings
