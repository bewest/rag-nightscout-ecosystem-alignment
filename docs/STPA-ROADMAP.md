# STPA Improvement Roadmap

> **Version**: 1.0  
> **Created**: 2026-01-27  
> **Work Package**: WP-005 step 5  
> **Scope**: 12-month improvement plan for STPA integration

---

## Executive Summary

This roadmap outlines a phased approach to improving STPA (Systems-Theoretic Process Analysis) integration across the Nightscout AID ecosystem. Based on the current state audit (122 GAPs, 11 UCAs, 14 SCs) and cross-project pattern analysis, we prioritize improvements by safety impact and implementation effort.

**Key Metrics**:
| Metric | Current | 3-Month Target | 12-Month Target |
|--------|---------|----------------|-----------------|
| UCAs documented | 11 | 25 | 50+ |
| Safety Constraints | 14 | 30 | 60+ |
| UCA→SC coverage | 17% | 50% | 90% |
| Tier 1 project coverage | 43% | 80% | 100% |

---

## Phase 1: Near-Term (0-3 Months)

**Theme**: Quick wins and foundation building

### 1.1 Quick Win: Fix Loop POST-Only Uploads (P0)

**Problem**: Loop uses POST (not PUT) for dose uploads, risking duplicate boluses (UCA-BOLUS-003).

**Action**: Contribute PR to Loop to use PUT/upsert for treatment uploads.

| Task | Owner | Effort | Impact |
|------|-------|--------|--------|
| Draft PR for Loop dose upload | Ecosystem team | Medium | Eliminates GAP-SYNC-001 |
| Test with Nightscout v3 API | Ecosystem team | Low | Validates fix |
| Document migration path | Ecosystem team | Low | Adoption guidance |

**Success Criteria**: Loop 3.x uses PUT for all treatment uploads.

### 1.2 Quick Win: Override Supersession Field (P2)

**Problem**: Override lifecycle not tracked in Nightscout (GAP-001).

**Action**: Add `superseded_by` field to override treatments.

| Task | Owner | Effort | Impact |
|------|-------|--------|--------|
| Add field to Nightscout schema | cgm-remote-monitor | Low | Enables tracking |
| Update Loop/Trio upload | Controller teams | Low | Populates field |
| Add conformance test | Ecosystem team | Low | Validates behavior |

**Success Criteria**: Override supersession visible in Nightscout UI.

### 1.3 Foundation: Document Sync ID Expectations

**Problem**: No unified documentation on sync identity strategies (GAP-003).

**Action**: Create sync identity specification document.

| Task | Owner | Effort | Impact |
|------|-------|--------|--------|
| Document per-controller strategy | Ecosystem team | Low | Clarity |
| Add to Nightscout API docs | cgm-remote-monitor | Low | Developer reference |
| Create conformance assertions | Ecosystem team | Low | Testability |

**Success Criteria**: Developers can look up sync ID requirements per controller.

### 1.4 Foundation: Expand UCA Catalog

**Problem**: Only 11 UCAs documented; many control actions not analyzed.

**Action**: Apply STPA to remaining Tier 1 control actions.

| Control Action | Current UCAs | Target UCAs |
|----------------|--------------|-------------|
| Bolus | 5 | 5 (complete) |
| Override | 2 | 4 |
| Basal | 0 | 4 |
| Suspend/Resume | 0 | 4 |
| SMB | 0 | 4 |
| Temp Target | 0 | 4 |

**Success Criteria**: 25+ UCAs documented with severity ratings.

---

## Phase 2: Medium-Term (3-6 Months)

**Theme**: Automation and cross-project standardization

### 2.1 Unified Sync Identity Protocol (P0)

**Problem**: Controllers use incompatible identity strategies.

**Action**: Define and implement unified sync identity standard.

| Task | Owner | Effort | Impact |
|------|-------|--------|--------|
| Draft sync identity RFC | Ecosystem team | Medium | Standard definition |
| Implement in Nightscout v3 | cgm-remote-monitor | Medium | Server support |
| Migrate AAPS (already compliant) | — | — | Baseline |
| Migrate Loop | Loop team | Medium | Adoption |
| Migrate Trio | Trio team | Medium | Adoption |

**Specification**:
```
- Field: `identifier` (UUID v4)
- Required on: all treatments, entries
- Uniqueness: client-generated, globally unique
- Dedup: server upserts on identifier match
```

**Success Criteria**: All Tier 1 controllers use unified `identifier` field.

### 2.2 Remote Command Confirmation Flow (P1)

**Problem**: Remote commands can conflict with local actions (UCA-REMOTE-001).

**Action**: Implement confirmation requirement for remote bolus/carb commands.

| Task | Owner | Effort | Impact |
|------|-------|--------|--------|
| Design confirmation protocol | Ecosystem team | Medium | Safety improvement |
| Implement in LoopCaregiver | LoopCaregiver team | Medium | Caregiver safety |
| Add timeout (60s default) | All controllers | Low | Prevents stale commands |
| Add rate limiting | Nightscout | Medium | Abuse prevention |

**Safety Constraint**: SC-REMOTE-001 - Remote bolus SHALL require local confirmation within 60 seconds.

**Success Criteria**: No remote bolus executes without on-device confirmation.

### 2.3 Automated UCA Discovery

**Problem**: Manual UCA analysis is time-consuming.

**Action**: Build tooling to suggest UCAs from code patterns.

| Task | Owner | Effort | Impact |
|------|-------|--------|--------|
| Define code patterns for control actions | Ecosystem team | Medium | Detection rules |
| Extend sdqctl with `--stpa` analysis | sdqctl | Medium | Automation |
| Integrate with CI for new PRs | Ecosystem team | Low | Continuous analysis |

**Success Criteria**: sdqctl can suggest UCAs from source code with 70%+ relevance.

### 2.4 Safety Constraint Derivation

**Problem**: 83% of UCAs lack linked safety constraints.

**Action**: Systematic SC derivation for all documented UCAs.

| Priority | UCAs | Target SCs |
|----------|------|------------|
| S4 (Critical) | 2 | 4+ SCs each |
| S3 (Serious) | 5 | 2+ SCs each |
| S2 (Moderate) | 4 | 1+ SC each |

**Success Criteria**: Every S3/S4 UCA has at least 2 safety constraints.

---

## Phase 3: Long-Term (6-12 Months)

**Theme**: CI/CD integration and Tier 2 expansion

### 3.1 Authority Hierarchy Implementation (P1)

**Problem**: No authority levels for data mutations (GAP-AUTH-002).

**Action**: Implement claim-based identity with authority hierarchy.

| Authority Level | Example | Can Override |
|-----------------|---------|--------------|
| 1 - Human (primary user) | Loop app user | All |
| 2 - Human (caregiver) | LoopCaregiver user | Level 3-4 |
| 3 - Agent (AI assistant) | Copilot suggestions | Level 4 only |
| 4 - Controller (algorithm) | Automated SMB | None |

| Task | Owner | Effort | Impact |
|------|-------|--------|--------|
| Design authority schema | Ecosystem team | High | Foundation |
| OIDC integration | Nightscout | High | Identity verification |
| Controller authority claims | All controllers | Medium | Adoption |
| Conflict resolution rules | Ecosystem team | Medium | Safety |

**Success Criteria**: Authority level visible on all treatments; conflicts resolved by hierarchy.

### 3.2 CI/CD STPA Validation

**Problem**: STPA artifacts can become stale without continuous validation.

**Action**: Integrate STPA validation into CI pipelines.

| Check | Trigger | Action on Failure |
|-------|---------|-------------------|
| UCA references valid | PR | Block merge |
| SC coverage ≥80% | Weekly | Create issue |
| New control action detected | PR | Require UCA analysis |
| Severity ratings present | PR | Block merge |

| Task | Owner | Effort | Impact |
|------|-------|--------|--------|
| GitHub Action for STPA validation | Ecosystem team | Medium | Automation |
| Pre-commit hooks for local dev | Ecosystem team | Low | Developer experience |
| Dashboard for coverage metrics | Ecosystem team | Medium | Visibility |

**Success Criteria**: No PR merges without STPA validation passing.

### 3.3 Tier 2 Project Expansion

**Problem**: Safety-relevant projects (xDrip+, xDrip4iOS, DiaBLE) lack STPA coverage.

**Action**: Apply STPA methodology to Tier 2 projects.

| Project | Control Actions | Target UCAs |
|---------|-----------------|-------------|
| xDrip+ | CGM data collection, calibration | 8 |
| xDrip4iOS | CGM data collection, calibration | 8 |
| DiaBLE | Libre sensor interface | 6 |
| Nightscout Connect | Data bridge | 4 |

**Success Criteria**: All Tier 2 projects have documented UCAs and SCs.

### 3.4 Regulatory Alignment Validation

**Problem**: STPA artifacts not validated against regulatory requirements.

**Action**: Map STPA artifacts to regulatory frameworks.

| Framework | Mapping Required |
|-----------|------------------|
| FDA 21 CFR 820.30 | Design Controls traceability |
| IEC 62304 | Software safety classification |
| ISO 14971 | Risk management integration |
| EU MDR 2017/745 | Technical documentation |

| Task | Owner | Effort | Impact |
|------|-------|--------|--------|
| Create mapping templates | Ecosystem team | Medium | Compliance |
| Validate Loop artifacts | Loop team | High | FDA readiness |
| Document gaps to compliance | Ecosystem team | Medium | Roadmap input |

**Success Criteria**: Regulatory mapping document with gap analysis.

---

## Dependencies

```
Phase 1 (0-3 months)
├── 1.1 Loop PUT/upsert (independent)
├── 1.2 Override supersession (independent)
├── 1.3 Sync ID documentation (independent)
└── 1.4 UCA catalog expansion (independent)

Phase 2 (3-6 months)
├── 2.1 Unified sync identity ← depends on 1.3
├── 2.2 Remote confirmation ← depends on 1.4 (UCA-REMOTE-*)
├── 2.3 Automated UCA discovery ← depends on 1.4
└── 2.4 SC derivation ← depends on 1.4

Phase 3 (6-12 months)
├── 3.1 Authority hierarchy ← depends on 2.1
├── 3.2 CI/CD validation ← depends on 2.3, 2.4
├── 3.3 Tier 2 expansion ← depends on 2.3
└── 3.4 Regulatory alignment ← depends on 3.2
```

---

## Resource Requirements

| Phase | Effort | Primary Owner | Support Needed |
|-------|--------|---------------|----------------|
| Phase 1 | 2-3 person-months | Ecosystem team | Controller maintainers |
| Phase 2 | 4-6 person-months | Ecosystem team + Nightscout | All controller teams |
| Phase 3 | 6-8 person-months | Ecosystem team | Regulatory expertise |

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Controller teams lack bandwidth | High | High | Start with ecosystem team PRs |
| Regulatory requirements unclear | Medium | Medium | Engage regulatory consultants early |
| Automation false positives | Medium | Low | Human review gate for S3/S4 |
| Scope creep | Medium | Medium | Strict phase gates |

---

## Success Metrics

### Phase 1 Exit Criteria
- [ ] Loop uses PUT for dose uploads
- [ ] `superseded_by` field in Nightscout
- [ ] Sync ID documentation published
- [ ] 25+ UCAs documented

### Phase 2 Exit Criteria
- [ ] Unified `identifier` field adopted by all Tier 1 controllers
- [ ] Remote command confirmation implemented
- [ ] sdqctl `--stpa` analysis available
- [ ] 90%+ SC coverage for S3/S4 UCAs

### Phase 3 Exit Criteria
- [ ] Authority hierarchy in production
- [ ] CI/CD STPA validation active on all Tier 1 repos
- [ ] Tier 2 projects have STPA coverage
- [ ] Regulatory mapping complete

---

## References

- [STPA Usage Guide](STPA-USAGE-GUIDE.md) - How to perform STPA analysis
- [Cross-Project Patterns](../traceability/stpa/cross-project-patterns.md) - Shared UCAs and SCs
- [Severity Scale](../../../sdqctl/docs/stpa-severity-scale.md) - S1-S4 definitions
- [STPA Audit Report](../../../sdqctl/reports/stpa-audit-2026-01-27.md) - Current state baseline
- [STPA-TRACEABILITY-FRAMEWORK](sdqctl-proposals/STPA-TRACEABILITY-FRAMEWORK.md) - Methodology

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-27
