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

### Phase 5: Follow-up Work Items (Post-PR)

These items are related to PR #8421 findings but should be tracked as separate work:

| ID | Task | Priority | Notes |
|----|------|----------|-------|
| SAFETY-001 | Create `guardDestructiveOperation()` in test-helpers.js | P1 | Validate DB name contains "test" |
| SAFETY-002 | Add opt-in `ALLOW_DESTRUCTIVE_TESTS=true` flag | P2 | For edge cases |
| SAFETY-003 | Update CI workflow if needed | P2 | May need env var |
| SAFETY-004 | Document test database setup | P3 | README or CONTRIBUTING.md |

**Context**: See [GAP-SYNC-046](../../traceability/sync-identity-gaps.md#gap-sync-046-test-suite-lacks-production-database-safeguards)

**Key Finding**: CI runs with `NODE_ENV=production`, so we cannot guard on `NODE_ENV=test`. Must validate database name instead.

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

## How to Work on This Backlog

### Finding Work Items

1. **Check SQL todos** for ready items (no pending dependencies):
   ```sql
   SELECT t.* FROM todos t
   WHERE t.status = 'pending'
   AND NOT EXISTS (
       SELECT 1 FROM todo_deps td
       JOIN todos dep ON td.depends_on = dep.id
       WHERE td.todo_id = t.id AND dep.status != 'done'
   );
   ```

2. **Read the backlog tables** above to understand file scope for each work item

3. **Check the reviewer's guide** to see what's already documented:
   - [docs/PR-8421-reviewers-guide.md](../PR-8421-reviewers-guide.md)

### Workflow Per Iteration

1. **Pick a work item** from the tables above (start with P0)
2. **Read relevant files** from worktree: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`
3. **Document findings** using the analysis template below
4. **Update the reviewer's guide** with key review points
5. **Mark complete** in this backlog and SQL todos
6. **Commit progress** to alignment repo

### Analysis Template

```markdown
### LIB-XXX: filename.js

**Purpose**: What this file does

**Changes Summary**:
- Bullet 1
- Bullet 2

**Key Review Points**:
1. Specific thing to verify
2. Another thing to check

**Breaking Changes**: None / Description

**Test Coverage**: `tests/relevant.test.js` (lines X-Y)

**Security Considerations**: None / Description

**Gap/Req References**: GAP-XXX-NNN, REQ-XXX
```

### Constraints

- Analyze ~1,200 LOC per iteration maximum
- Focus on substance, not style changes
- Cross-reference with gap/requirement IDs
- Note breaking changes prominently

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

## Recommended Workflow

### Best Existing Conv File: `integration-test-cycle.conv`

This workflow is closest to our needs because it:
- Uses minimal context with explore-as-needed pattern
- Has phased structure (Select → Execute → Verify → Commit)
- Already references backlog files for task selection
- Includes ALLOW-SHELL for file exploration

### Dedicated Workflow: `pr-review-analysis-v2.conv`

**Created specifically for this work:**
```bash
sdqctl iterate ./workflows/pr-review-analysis-v2.conv -n 5
```

**Phases:**
1. **Verify Environment** - Check worktree branch, run tests
2. **Select Work Item** - Pick from backlog (LIB/TEST/DOC priority)
3. **Analyze File** - Read from worktree, use template
4. **Update Guide** - Add findings to reviewer's guide
5. **Mark Complete** - Update backlog ❌ → ✅
6. **Verify** - Run `verify_refs` + `backlog_hygiene`
7. **Commit** - With trace refs

**Built-in verification:**
```bash
# Phase 5 runs automatically:
python tools/verify_refs.py | grep -E "BROKEN|ERROR"
python tools/backlog_hygiene.py --check
```

### Suggested Conv Modifications (for future version)

If creating a dedicated `pr-review-analysis.conv`, consider:

```yaml
# Changes from integration-test-cycle.conv:
CONTEXT @docs/backlogs/pr-8421-review-analysis.md    # Add backlog
CONTEXT @docs/PR-8421-reviewers-guide.md             # Add output target

# Phase 1: Task Selection - modify prompt to point here:
PROMPT Pick task from `docs/backlogs/pr-8421-review-analysis.md`:
  - Phase 1: LIB-001 to LIB-026 (library code)
  - Phase 2: TEST-001 to TEST-010 (test code)
  - Phase 3: DOC-001 to DOC-006 (documentation audit)

# Phase 2: Analysis - use worktree path:
PROMPT Analyze files in `/home/bewest/src/worktrees/nightscout/cgm-pr-8447/`

# Phase 4: Update guide - add this:
PROMPT Update `docs/PR-8421-reviewers-guide.md` with findings.
```

### Verification Tools to Run

After each analysis iteration, run these checks:

| Tool | Command | Purpose |
|------|---------|---------|
| **verify_refs** | `python tools/verify_refs.py` | Ensure code references resolve |
| **verify_coverage** | `python tools/verify_coverage.py` | Check gap/req coverage |
| **backlog_hygiene** | `python tools/backlog_hygiene.py --check` | Validate backlog structure |

**Suggested verification sequence:**
```bash
# After updating reviewer's guide
python tools/verify_refs.py --verbose | grep -E "BROKEN|ERROR" || echo "All refs valid"

# After marking items complete
python tools/backlog_hygiene.py --check

# Periodically check coverage
python tools/verify_coverage.py --json | jq '.summary'
```

### Quick Start for Teammates

```bash
# 1. Check what's pending
grep -E "^\| (LIB|TEST|DOC)-" docs/backlogs/pr-8421-review-analysis.md | grep "❌"

# 2. Run integration cycle (will find P0 work in README.md)
sdqctl iterate ./workflows/integration-test-cycle.conv -n 3

# 3. Verify changes
python tools/verify_refs.py
git status
```

---

## References

- [PR #8421](https://github.com/nightscout/cgm-remote-monitor/pull/8421)
- [Reviewer's Guide](../PR-8421-reviewers-guide.md)
- [LIVE-BACKLOG.md](../../LIVE-BACKLOG.md) - Session tracking
- [Worktree](file:///home/bewest/src/worktrees/nightscout/cgm-pr-8447)
- [GAP-SYNC-045 Test Report](../test-reports/GAP-SYNC-045-entries-uuid-fix.md)
- [Client ID Deep Dive](../10-domain/client-id-handling-deep-dive.md)
