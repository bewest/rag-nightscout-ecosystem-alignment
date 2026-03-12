# PR #8421 Reviewer's Guide - Analysis Backlog

> **Goal**: Systematically analyze PR #8421 and complete the reviewer's guide  
> **PR Size**: 146 files, +36,222 / -4,654 lines  
> **Constraint**: ~1,200 LOC analysis per iteration  
> **Created**: 2026-03-12

---

## Analysis Strategy

Given the PR size (~40k LOC) and our working context (~1,200 LOC), we need **~30-35 focused analysis passes** to thoroughly review and document.

### Prioritization

| Priority | Category | Files | Est. Iterations |
|----------|----------|-------|-----------------|
| P0 | Library code (core storage) | 10 | 5-6 |
| P0 | Library code (API layer) | 10 | 4-5 |
| P1 | Test code (UUID/sync) | 5 | 3-4 |
| P1 | Test code (shape/batch) | 5 | 3-4 |
| P2 | Test fixtures | 10 | 2-3 |
| P2 | Scripts/tooling | 5 | 1-2 |
| P3 | Documentation (audits) | 7 | 3-4 |
| P3 | Documentation (proposals) | 15 | 4-5 |
| P3 | Documentation (schemas) | 12 | 2-3 |
| P4 | CI/Config | 5 | 1 |

---

## Work Items

### Phase 1: Library Code Analysis (P0)

#### 1.1 Core Storage Layer

| ID | File | Lines | Status | Notes |
|----|------|-------|--------|-------|
| LIB-001 | `lib/server/treatments.js` | +216/-33 | ❌ | UUID handling, identifier promotion |
| LIB-002 | `lib/server/entries.js` | +100/-29 | ❌ | UUID handling, sysTime+type dedup |
| LIB-003 | `lib/server/devicestatus.js` | +68/-39 | ❌ | |
| LIB-004 | `lib/server/activity.js` | +29/-16 | ❌ | |
| LIB-005 | `lib/server/food.js` | +15/-11 | ❌ | |
| LIB-006 | `lib/server/profile.js` | +10/-5 | ❌ | |
| LIB-007 | `lib/server/query.js` | +26/-4 | ❌ | |
| LIB-008 | `lib/server/bootevent.js` | +6/-16 | ❌ | |
| LIB-009 | `lib/server/env.js` | +17/-0 | ❌ | |
| LIB-010 | `lib/data/ddata.js` | +23/-1 | ❌ | |

**Analysis template for each file:**
```markdown
### LIB-XXX: filename.js

**Purpose**: [What this file does]

**Changes Summary**:
- [Bullet points of key changes]

**Key Review Points**:
1. [Specific things reviewers should check]

**Breaking Changes**: None / [Description]

**Test Coverage**: [Reference to test file]

**Security Considerations**: None / [Description]
```

#### 1.2 API Layer

| ID | File | Lines | Status | Notes |
|----|------|-------|--------|-------|
| LIB-011 | `lib/api/entries/index.js` | +18/-2 | ❌ | |
| LIB-012 | `lib/api3/storage/mongoCollection/find.js` | +16/-2 | ❌ | |
| LIB-013 | `lib/api3/storage/mongoCollection/utils.js` | +3/-3 | ❌ | |
| LIB-014 | `lib/api3/storage/mongoCollection/modify.js` | +2/-2 | ❌ | |
| LIB-015 | `lib/api3/generic/patch/operation.js` | +4/-5 | ❌ | |
| LIB-016 | `lib/api3/generic/update/replace.js` | +3/-0 | ❌ | |
| LIB-017 | `lib/api3/generic/search/input.js` | +2/-2 | ❌ | |
| LIB-018 | `lib/api3/generic/collection.js` | +2/-2 | ❌ | |

#### 1.3 Other Library

| ID | File | Lines | Status | Notes |
|----|------|-------|--------|-------|
| LIB-019 | `lib/authorization/storage.js` | +15/-6 | ❌ | |
| LIB-020 | `lib/authorization/delaylist.js` | +1/-1 | ❌ | |
| LIB-021 | `lib/plugins/openaps.js` | +6/-13 | ❌ | |
| LIB-022 | `lib/sandbox.js` | +3/-2 | ❌ | |
| LIB-023 | `lib/language.js` | +6/-7 | ❌ | |
| LIB-024 | `lib/client/renderer.js` | +2/-0 | ❌ | |
| LIB-025 | `lib/client/index.js` | +1/-1 | ❌ | |
| LIB-026 | `lib/report_plugins/daytoday.js` | +2/-1 | ❌ | |

---

### Phase 2: Test Code Analysis (P1)

#### 2.1 UUID/Sync Tests

| ID | File | Lines | Status | Gap/Req |
|----|------|-------|--------|---------|
| TEST-001 | `tests/api.entries.uuid.test.js` | ~577 | ❌ | GAP-SYNC-045 |
| TEST-002 | `tests/gap-treat-012.test.js` | ~428 | ❌ | GAP-TREAT-012 |
| TEST-003 | `tests/identity-matrix.test.js` | ~476 | ❌ | REQ-SYNC-072 |
| TEST-004 | `tests/objectid-cache.test.js` | ~468 | ❌ | |
| TEST-005 | `tests/api.deduplication.test.js` | ~200 | ❌ | |

#### 2.2 Shape/Batch Tests

| ID | File | Lines | Status | Notes |
|----|------|-------|--------|-------|
| TEST-006 | `tests/sgv-devicestatus.test.js` | ~646 | ❌ | |
| TEST-007 | `tests/websocket.shape-handling.test.js` | ~643 | ❌ | |
| TEST-008 | `tests/storage.shape-handling.test.js` | ~410 | ❌ | |
| TEST-009 | `tests/api.aaps-client.test.js` | ~300 | ❌ | |
| TEST-010 | `tests/flakiness-control.test.js` | ~306 | ❌ | |

#### 2.3 Test Fixtures

| ID | File | Lines | Status |
|----|------|-------|--------|
| FIX-001 | `tests/fixtures/loop-override.js` | ~219 | ❌ |
| FIX-002 | `tests/fixtures/partial-failures.js` | ~190 | ❌ |
| FIX-003 | `tests/fixtures/trio-pipeline.js` | ~198 | ❌ |
| FIX-004 | `tests/lib/test-helpers.js` | ~277 | ❌ |

---

### Phase 3: Documentation Audit (P2-P3)

#### 3.1 Verify Doc Accuracy

| ID | Document | Status | Notes |
|----|----------|--------|-------|
| DOC-001 | `docs/meta/architecture-overview.md` | ❌ | Verify matches code |
| DOC-002 | `docs/meta/modernization-roadmap.md` | ❌ | Check completion status |
| DOC-003 | `docs/audits/*.md` (7 files) | ❌ | Spot-check accuracy |
| DOC-004 | `docs/proposals/*.md` (15 files) | ❌ | Identify implemented vs proposed |
| DOC-005 | `docs/requirements/*.md` (3 files) | ❌ | Verify test coverage |
| DOC-006 | `docs/test-specs/*.md` (4 files) | ❌ | Match to actual tests |

---

### Phase 4: CI/Config Analysis (P4)

| ID | File | Status | Notes |
|----|------|--------|-------|
| CI-001 | `.github/workflows/main.yml` | ❌ | Node version change |
| CI-002 | `package-lock.json` | ❌ | Dependency audit |
| CI-003 | `Makefile` | ❌ | New targets |

---

## Iteration Plan

### Iteration Template

```markdown
## Iteration N: [Focus Area]

**Files analyzed**:
- file1.js (+X/-Y)
- file2.js (+X/-Y)

**Findings**:
1. ...

**Guide updates**:
- Section X.Y updated
- Added review point for Z

**Next iteration**: [Focus]
```

### Suggested Iteration Sequence

| Iter | Focus | Work Items | Est. Time |
|------|-------|------------|-----------|
| 1 | treatments.js deep dive | LIB-001 | 30 min |
| 2 | entries.js deep dive | LIB-002 | 30 min |
| 3 | devicestatus.js, activity.js | LIB-003, LIB-004 | 25 min |
| 4 | food.js, profile.js, query.js | LIB-005-007 | 20 min |
| 5 | bootevent, env, ddata | LIB-008-010 | 15 min |
| 6 | API layer (entries) | LIB-011-014 | 20 min |
| 7 | API layer (v3 generic) | LIB-015-018 | 20 min |
| 8 | Other lib files | LIB-019-026 | 25 min |
| 9 | UUID test files | TEST-001-003 | 30 min |
| 10 | Sync test files | TEST-004-005 | 25 min |
| 11 | Shape test files | TEST-006-008 | 30 min |
| 12 | Other test files | TEST-009-010 | 20 min |
| 13 | Test fixtures | FIX-001-004 | 20 min |
| 14 | Doc accuracy check | DOC-001-002 | 25 min |
| 15 | Doc audit check | DOC-003 | 30 min |
| 16 | Doc proposals check | DOC-004 | 30 min |
| 17 | Doc requirements/specs | DOC-005-006 | 25 min |
| 18 | CI/Config | CI-001-003 | 15 min |
| 19 | Final guide polish | - | 20 min |
| 20 | Cross-reference check | - | 20 min |

---

## Completion Criteria

### For Each Work Item

- [ ] File analyzed and understood
- [ ] Key changes documented
- [ ] Review points identified
- [ ] Breaking changes noted
- [ ] Test coverage verified
- [ ] Guide section updated

### For Overall Guide

- [ ] All library files documented
- [ ] All test files documented
- [ ] Documentation accuracy verified
- [ ] Review sessions defined
- [ ] Checklist complete
- [ ] Questions for reviewers added

---

## Workflow Command

```bash
# Run analysis iterations
time sdqctl iterate ./workflows/pr-8421-review-analysis.conv -n 20

# Or step by step
time sdqctl iterate ./workflows/pr-8421-review-analysis.conv -n 5  # Library core
time sdqctl iterate ./workflows/pr-8421-review-analysis.conv -n 5  # Library API + tests
time sdqctl iterate ./workflows/pr-8421-review-analysis.conv -n 5  # More tests + fixtures
time sdqctl iterate ./workflows/pr-8421-review-analysis.conv -n 5  # Docs + polish
```

---

## References

- [PR #8421](https://github.com/nightscout/cgm-remote-monitor/pull/8421)
- [Reviewer's Guide (stub)](./PR-8421-reviewers-guide.md)
- [Worktree](file:///home/bewest/src/worktrees/nightscout/cgm-pr-8447)
