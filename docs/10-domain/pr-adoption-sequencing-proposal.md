# PR Adoption Sequencing Proposal

> **Created**: 2026-01-30  
> **Purpose**: Prioritized roadmap for adopting 68 open cgm-remote-monitor PRs  
> **Status**: Proposal  
> **Dependencies**: [PR Deep-Dives](priority-pr-deep-dives.md), [Node.js LTS Analysis](node-lts-upgrade-analysis.md)

---

## Executive Summary

This proposal provides a sequenced adoption plan for the 68 open PRs in cgm-remote-monitor, aligned with the Node.js LTS upgrade timeline and ecosystem priorities.

### Key Constraints

| Constraint | Impact |
|------------|--------|
| **Node 20 EOL**: 2026-04-30 | All major work must complete by April |
| **MongoDB 5x**: Foundational | Many PRs depend on modern infrastructure |
| **Security**: Remote Commands | Requires audit before merge |
| **Review Capacity**: Limited | 1-2 maintainers actively reviewing |

### Proposed Timeline

| Phase | Timeline | PRs | Focus |
|-------|----------|-----|-------|
| Phase 1 | Feb 2026 | 6 | Quick wins + testing |
| Phase 2 | Mar 2026 | 3 | Infrastructure modernization |
| Phase 3 | Apr 2026 | 4 | API features + deprecations |
| Phase 4 | Q2 2026 | 5+ | Long-tail cleanup |

---

## Phase 1: Quick Wins (February 2026)

Low-risk PRs that improve quality without breaking changes.

### 1.1 Testing & Quality

| Order | PR | Title | Size | Risk | Rationale |
|-------|-----|-------|------|------|-----------|
| 1 | #8419 | iOS Loop Push Tests | +532/-5 | Low | +1.6% coverage, no API changes |
| 2 | #8378 | mmol test fixes | +small | Low | Test reliability |
| 3 | #8377 | GitHub Actions badge | +small | Low | CI visibility |

**Outcome**: Establishes testing baseline before infrastructure changes.

### 1.2 Simple Features

| Order | PR | Title | Size | Risk | Rationale |
|-------|-----|-------|------|------|-----------|
| 4 | #8083 | Heart Rate Storage | +158/-5 | Low | Additive API, AAPS ready |
| 5 | #8261 | Multi-Insulin API | +169/-0 | Low | Additive API, already in use |
| 6 | #8281 | AAPS TBR Rendering | +4/-4 | Low | Trivial change, AAPS benefit |

**Outcome**: Closes GAP-API-HR, GAP-INSULIN-001, GAP-INS-001.

### Phase 1 Dependencies

```
#8419 (tests) → #8378 (mmol) → #8377 (badge)
       ↓
#8083 (heartrate) ┬→ No dependencies
#8261 (insulin)   ┘
#8281 (TBR)       → No dependencies
```

---

## Phase 2: Infrastructure Modernization (March 2026)

Critical infrastructure updates before Node 20 EOL (2026-04-30).

### 2.1 Database Layer

| Order | PR | Title | Size | Risk | Rationale |
|-------|-----|-------|------|------|-----------|
| 7 | #8421 | MongoDB 5x Support | +39,980/-7,689 | High | Foundation for Node 22 |

**Critical Path**: This is the blocking PR for Node.js upgrade.

**Breaking Changes**:
- Collection methods: `.find()` returns cursor
- Callback removal: Promises-only API
- Connection strings: New format

**Testing Requirements**:
- [ ] Full API3 test suite pass
- [ ] Socket.IO real-time verification
- [ ] Heroku/Docker deployment smoke tests

### 2.2 Modernization Wave

| Order | PR | Title | Size | Risk | Rationale |
|-------|-----|-------|------|------|-----------|
| 8 | #8360 | Remove Lodash | medium | Medium | Bundle size, security |
| 9 | #8348 | Remove Moment | medium | Medium | Bundle size, maintenance |

**Bundle After Phase 2**: Merge together with MongoDB 5x for single major release.

### Phase 2 Dependencies

```
#8421 (MongoDB 5x)
    ├→ #8360 (Lodash)
    └→ #8348 (Moment)
    
All three = v15.1.0 release candidate
```

---

## Phase 3: API Features & Deprecations (April 2026)

Major API additions and bridge consolidation.

### 3.1 API Enhancements

| Order | PR | Title | Size | Risk | Rationale |
|-------|-----|-------|------|------|-----------|
| 10 | #8405 | Timezone Display Fix | +194/-5 | Medium | UX improvement |
| 11 | #8422 | API3 limit error fix | small | Low | Bug fix |

### 3.2 Security-Sensitive

| Order | PR | Title | Size | Risk | Rationale |
|-------|-----|-------|------|------|-----------|
| 12 | #7791 | Remote Commands | +729/-2 | **HIGH** | Requires security audit |

**Security Requirements for #7791**:
1. ⚠️ **OTP enforcement** for bolus/carb commands
2. Command expiration (max 5 min)
3. Rate limiting (max 10/hour per user)
4. Audit logging of all commands

**Recommendation**: Do NOT merge without Loop team security review.

### 3.3 Bridge Deprecations

| Order | Action | Target | Effort | Rationale |
|-------|--------|--------|--------|-----------|
| 13 | Deprecate | share2nightscout-bridge | Low | EOL Node, `request` pkg |
| 14 | Deprecate | minimed-connect-to-nightscout | Low | nightscout-connect replacement |

**Deprecation Actions**:
1. Add README banner: "⚠️ DEPRECATED - Use nightscout-connect"
2. Archive repository
3. Remove from documentation recommendations

### Phase 3 Dependencies

```
Phase 2 complete (Node 22)
    │
    ├→ #8405 (timezone) → #8422 (API fix)
    │
    └→ #7791 (commands) [SECURITY GATE]
    
Parallel: Bridge deprecations (no code changes)
```

---

## Phase 4: Long-Tail Cleanup (Q2 2026)

Lower-priority items for sustained maintenance.

### 4.1 UI/Reports

| PR | Title | Priority | Notes |
|----|-------|----------|-------|
| #8366 | 2025 Reports | P2 | WIP, clinical use case |
| #8402 | CSV Exports | P3 | Feature request |
| #8330 | GMI/Revised GMI | P3 | Statistics enhancement |

### 4.2 Deployment Options

| PR | Title | Priority | Notes |
|----|-------|----------|-------|
| #8417 | Multi-build Docker | P2 | Reduces image size |
| #8416 | Docker Mongo 8.2 | P2 | Enables latest MongoDB |
| #8413 | Fly.io Launch | P3 | New hosting option |
| #8382 | Render.yaml | P3 | New hosting option |

### 4.3 Stale PR Triage

| PR | Title | Age | Recommendation |
|----|-------|-----|----------------|
| #6875 | Carportal voice | 5 years | Close |
| #6928 | Custom test framework | 5 years | Close |
| #6974 | Alexa translations | 5 years | Close |
| #7150 | README update | 4 years | Close |
| #7221 | Pushover priority | 4 years | Close |

**Recommendation**: Close all 5 stale PRs with explanation and invitation to reopen.

---

## Release Strategy

### v15.1.0 (March 2026)

**Bundle**:
- #8421 MongoDB 5x
- #8360 Remove Lodash
- #8348 Remove Moment
- Node 22 engine requirement

**Breaking Changes**: Yes (MongoDB driver API)

**Migration Guide Required**: Yes

### v15.2.0 (April 2026)

**Features**:
- #8083 Heart Rate
- #8261 Multi-Insulin
- #8405 Timezone fix

**Breaking Changes**: No (additive only)

### v16.0.0 (Q2 2026, if #7791 merges)

**Features**:
- #7791 Remote Commands

**Breaking Changes**: Yes (new security requirements)

---

## Ecosystem Impact Matrix

| PR | Loop | AAPS | Trio | xDrip+ | Reporters |
|----|------|------|------|--------|-----------|
| #8083 HR | - | ✅ Primary | - | ⚪ Future | ⚪ Future |
| #8261 Insulin | ⚪ Future | ⚪ Future | ⚪ Future | ✅ Using | ✅ Using |
| #8281 TBR | - | ✅ Primary | - | - | - |
| #7791 Commands | ✅ Critical | - | ⚪ Future | - | - |
| #8421 MongoDB | ⚪ Infra | ⚪ Infra | ⚪ Infra | ⚪ Infra | ⚪ Infra |

Legend: ✅ Primary beneficiary | ⚪ Benefits | - No impact

---

## Gap Closure Schedule

| Gap ID | Title | Closed By | Phase |
|--------|-------|-----------|-------|
| GAP-API-HR | Heart rate collection | #8083 | Phase 1 |
| GAP-INSULIN-001 | Multi-insulin API | #8261 | Phase 1 |
| GAP-INS-001 | Insulin model interop | #8261 | Phase 1 |
| GAP-DB-001 | MongoDB 5x support | #8421 | Phase 2 |
| GAP-NODE-001 | EOL Node.js | Node 22 upgrade | Phase 2 |
| GAP-NODE-002 | Deprecated `request` | Bridge deprecation | Phase 3 |
| GAP-REMOTE-CMD | Remote commands | #7791 | Phase 3 |
| GAP-TZ-001 | Timezone handling | #8405 | Phase 3 |

---

## Resource Requirements

### Maintainer Time

| Phase | PRs | Review Hours | Testing Hours |
|-------|-----|--------------|---------------|
| Phase 1 | 6 | 8 | 4 |
| Phase 2 | 3 | 24 | 16 |
| Phase 3 | 4 | 16 | 12 |
| Phase 4 | 5+ | 12 | 8 |

**Total**: ~60 review hours, ~40 testing hours

### External Dependencies

| Dependency | Owner | Required For |
|------------|-------|--------------|
| Security audit | Loop team | #7791 |
| AAPS testing | AAPS maintainers | #8083, #8281 |
| Docker builds | Docker maintainers | #8417, #8416 |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| MongoDB 5x regressions | Medium | High | Staged rollout, canary testing |
| #7791 security issues | High | Critical | Don't merge without audit |
| Node 22 compatibility | Low | High | Heroku/Docker testing |
| Review capacity | High | Medium | Prioritize quick wins first |
| Community pushback on deprecations | Medium | Low | Clear migration path |

---

## Success Metrics

| Metric | Current | Phase 2 Target | Phase 4 Target |
|--------|---------|----------------|----------------|
| Open PRs | 68 | 55 | 45 |
| Node.js version | 16 (EOL) | 22 LTS | 22 LTS |
| Test coverage | 63.8% | 66% | 68% |
| Gaps closed | 0 | 3 | 7 |
| Stale PRs | 5 | 0 | 0 |

---

## Next Steps

1. **Immediate**: Merge #8419 (Push Tests) - unblocks Phase 1
2. **This week**: Review #8083 and #8261 for merge
3. **February**: Complete Phase 1 (6 PRs)
4. **March**: Bundle #8421 + modernization for v15.1.0
5. **April**: Security review for #7791

---

## Cross-References

- [Priority PR Deep-Dives](priority-pr-deep-dives.md)
- [Node.js LTS Upgrade Analysis](node-lts-upgrade-analysis.md)
- [cgm-remote-monitor PR Analysis](cgm-remote-monitor-pr-analysis.md)
- [Connector Gaps](../../traceability/connectors-gaps.md)
