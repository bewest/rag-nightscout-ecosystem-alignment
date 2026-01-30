# Nightscout Maintainer Recommendations

> **Created**: 2026-01-30  
> **Source**: nightscout-api.md #19  
> **Audience**: Nightscout maintainers  
> **Purpose**: Actionable recommendations linked to ecosystem analysis

---

## Executive Summary

This document packages key findings from the AID ecosystem alignment analysis into actionable recommendations for Nightscout maintainers.

**Priority Areas**:
1. **Quick Win PRs** (6 PRs, low risk, high value)
2. **Sync & Identity Gaps** (22 gaps affecting data sync)
3. **API Completeness** (2 collections need specs)
4. **Algorithm Interoperability** (controller output standardization)

---

## Priority 1: Quick Win PRs

These PRs are ready to merge with minimal risk:

| PR | Title | Risk | Gap Addressed | Recommendation |
|----|-------|------|---------------|----------------|
| #8419 | iOS Loop Push Tests | Low | Testing coverage | **Merge** - improves CI |
| #8083 | Heart Rate Storage | Low | GAP-API-HR | **Merge** - AAPS ready |
| #8261 | Multi-Insulin API | Low | GAP-INSULIN-001 | **Merge** - already in use |
| #8281 | AAPS TBR Rendering | Low | GAP-INS-001 | **Merge** - trivial fix |
| #8405 | Timezone offset | Low | GAP-TZ-001 | **Merge** - reviewed safe |
| #8422 | OpenAPI robustness | Low | None (quality) | **Merge** - spec compliance |

**Action**: Review and merge these 6 PRs in February 2026.

---

## Priority 2: Sync & Identity Improvements

Analysis of 22 GAP-SYNC-* entries reveals:

### By State Category

| Category | Count | Description | Priority |
|----------|-------|-------------|----------|
| **Desired** | 8 | Profile/override sync | P1 - user therapy |
| **Observed** | 6 | Treatment deduplication | P2 - data integrity |
| **Cross-category** | 6 | API/identity infra | P2 - foundation |
| **Control** | 2 | Algorithm output | P3 - advanced |

### Top Recommendations

#### 2.1 Profile Sync (8 gaps)

**Problem**: Profile sync between controllers is ambiguous.

| Gap ID | Issue | Recommendation |
|--------|-------|----------------|
| GAP-SYNC-031 | Profile source unknown | Add `sourceController` field |
| GAP-SYNC-035 | No Profile Switch events | Standardize event emission |
| GAP-SYNC-037 | Percentage/timeshift not portable | Define transformation spec |
| GAP-SYNC-039 | srvModified missing | Add server timestamp |

**Action**: Create RFC for profile sync protocol v2.

#### 2.2 Treatment Deduplication (6 gaps)

**Problem**: Duplicate treatments from network retries.

| Gap ID | Issue | Recommendation |
|--------|-------|----------------|
| GAP-SYNC-001 | POST-only, no upsert | Support PUT with identifier |
| GAP-SYNC-005 | ObjectIdCache volatile | Persist to disk |
| GAP-SYNC-029 | No cross-controller dedup | Database unique constraint |
| GAP-SYNC-032 | Missing identifier field | Require on insert |

**Action**: Add database-level unique constraint on `identifier`.

#### 2.3 API Infrastructure (6 gaps)

| Gap ID | Issue | Recommendation |
|--------|-------|----------------|
| GAP-SYNC-006 | V1 API only in Loop | Encourage V3 migration |
| GAP-SYNC-007 | syncIdentifier format | Publish format spec |
| GAP-SYNC-040 | Delete semantics differ | Document soft vs hard delete |

**Action**: Publish sync identity specification document.

---

## Priority 3: API Completeness

Analysis depth matrix shows 2 collections lacking specs:

| Collection | Current Coverage | Recommendation |
|------------|-----------------|----------------|
| **food** | 8% | Create `aid-food-2025.yaml` |
| **activity** | 8% | Create `aid-activity-2025.yaml` |

**Rationale**: These collections are used by some controllers but have no formal schema, leading to undocumented variance.

**Action**: Add minimal OpenAPI specs for food and activity collections.

---

## Priority 4: Controller Output Standardization

### Problem

Loop and oref0/AAPS upload different deviceStatus structures:

| Field | Loop | oref0/AAPS |
|-------|------|------------|
| Predictions | `loop.predicted` | `openaps.iob.iobTick` |
| Enacted temp | `loop.enacted` | `openaps.enacted` |
| IOB structure | `loop.iob.iob` | `openaps.iob.iob` |

### Recommendation

Define unified `devicestatus.controller` schema that both can use.

| Gap ID | Issue |
|--------|-------|
| GAP-DS-001 | No unified controller output schema |
| GAP-DS-002 | Prediction format differs |

**Action**: RFC for unified controller output format.

---

## Implementation Roadmap

| Phase | Timeline | Focus | Deliverable |
|-------|----------|-------|-------------|
| 1 | Feb 2026 | Quick win PRs | 6 PRs merged |
| 2 | Mar 2026 | Sync identity spec | RFC published |
| 3 | Apr 2026 | Food/activity specs | 2 OpenAPI specs |
| 4 | Q2 2026 | Controller unification | RFC published |

---

## Gap Cross-Reference

| Domain | Gaps | Top Priority |
|--------|------|--------------|
| Sync & Identity | GAP-SYNC-001 to 041 | Profile sync (8 gaps) |
| API | GAP-API-001 to 015 | Heart rate, multi-insulin |
| Treatments | GAP-TREAT-001 to 009 | eventType standardization |
| DeviceStatus | GAP-DS-001 to 008 | Controller output |
| Profile | GAP-PROF-001 to 012 | ProfileSwitch handling |

---

## Related Documents

- [pr-adoption-sequencing-proposal.md](pr-adoption-sequencing-proposal.md) - Full PR roadmap
- [cgm-remote-monitor-analysis-depth-matrix.md](cgm-remote-monitor-analysis-depth-matrix.md) - Coverage audit
- [state-ontology.md](../architecture/state-ontology.md) - Observed/Desired/Control
- [sync-identity-gaps.md](../../traceability/sync-identity-gaps.md) - Full gap list
