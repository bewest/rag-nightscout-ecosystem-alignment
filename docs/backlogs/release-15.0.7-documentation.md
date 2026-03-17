# Release 15.0.7 Documentation Needs

**Status**: 📋 In Progress  
**Target**: Document behavioral changes before release  
**Branch**: `official/dev` (171 commits ahead of `official/master`)  
**Related PR**: [PR #8444](https://github.com/nightscout/cgm-remote-monitor/pull/8444)

---

## Summary

The dev branch contains significant changes to test infrastructure, database safety, and API behavior that need documentation before release. This backlog tracks required documentation updates.

---

## 1. Environment Variables (NEW/CHANGED)

### 1.1 Test Environment Variables

| Variable | Purpose | Default | Where Documented? | Action |
|----------|---------|---------|-------------------|--------|
| `NODE_ENV=test` | **REQUIRED** for tests - prevents production DB destruction | - | `CONTRIBUTING.md` (partial) | ⚠️ Add to test docs |
| `AUTH_FAIL_DELAY` | Delay (ms) after auth failure (brute-force protection) | 5000 | `docs/example-template.env` ✅ | ✅ OK |
| `MONGO_POOL_SIZE` | MongoDB connection pool size | 10 | `ci.test.env` only | ⚠️ Document for test tuning |
| `MONGO_MIN_POOL_SIZE` | Minimum pool connections | 1 | `ci.test.env` only | ⚠️ Document for test tuning |
| `MONGO_MAX_IDLE_TIME_MS` | Max idle time before closing | 10000 | `ci.test.env` only | ⚠️ Document for test tuning |

### 1.2 API Feature Flags

| Variable | Purpose | Default | Where Documented? | Action |
|----------|---------|---------|-------------------|--------|
| `UUID_HANDLING` | Enable UUID _id handling for treatments/entries | `false` | ❌ | ⚠️ Add to docs/example-template.env |

**Details**: See [uuid-identifier-lookup.md](./uuid-identifier-lookup.md) for full specification.

When `UUID_HANDLING=true`:
- POST/PUT: UUID in `_id` → extracted to `identifier`, server generates ObjectId
- GET/DELETE by UUID: searches by `identifier` field

When `UUID_HANDLING=false` (default):
- POST/PUT with UUID `_id`: Returns 400 error with instructions
- GET/DELETE by UUID: Returns empty results (no crash)
- **ObjectID users unaffected** — only triggers on UUID format

### 1.3 New npm Scripts

| Script | Purpose | Documented? | Action |
|--------|---------|-------------|--------|
| `test:unit` | Run unit tests (parallel, fast) | ❌ | Add to CONTRIBUTING.md |
| `test:integration` | Run integration tests (sequential, needs DB) | ❌ | Add to CONTRIBUTING.md |
| `test:stress` | Concurrent write stress tests | ❌ | Add to CONTRIBUTING.md |
| `test:flaky` | Flaky test detection runner | ❌ | Add to CONTRIBUTING.md |
| `test:timing` | Tests with setTimeout warnings | ❌ | Add to CONTRIBUTING.md |

---

## 2. Test Infrastructure Changes

### 2.1 NODE_ENV=test Safety (GAP-SYNC-046)

**Commits**: `61501cac`, `e12cf3d2`

**Behavior Change**:
- Tests now **exit with error** if `NODE_ENV !== 'test'`
- Previously: Tests would run against any database (including production!)
- Now: Hard failure with clear error message

**Documentation Needed**:
- Update CONTRIBUTING.md to emphasize `NODE_ENV=test`
- Update any test running instructions
- Document `tests/fixtures/test-guard.js` guarded operations

### 2.2 Test Organization

**Commits**: `a12f7296`, `71c89f40`, `cface548`

**Changes**:
- Tests split into `test:unit` (parallel) and `test:integration` (sequential)
- `beforeEach` → `before` conversion for performance
- Parallel jobs configured (2 workers default)

**Documentation Needed**:
- Test categories and when to use each
- How to run specific test subsets

---

## 3. API Behavior Changes

### 3.1 Treatments API - Identifier Field (REQ-SYNC-072)

**Commit**: `e78a5bc6` (PR #8447)

**Behavior Change**:
- Server now extracts `identifier` from various client sync fields:
  - Loop: UUID in `_id` → `identifier`
  - Loop: `syncIdentifier` → `identifier`
  - AAPS: `identifier` (unchanged)
  - xDrip+: `uuid` → `identifier`
- Server generates proper ObjectId for `_id`
- Deduplication by `identifier` (not `_id`)

**Documentation Needed**:
- API changelog entry
- Update API documentation for treatments endpoint
- Document `identifier` field behavior
- Document backwards compatibility (gradual adoption)

### 3.2 Entries API - UUID _id Handling (GAP-SYNC-045)

**Commit**: `b8815505`

**Behavior Change**:
- CGM entries with UUID `_id` now handled correctly
- Similar normalization as treatments

**Documentation Needed**:
- API changelog entry for entries endpoint

---

## 4. CI/CD Changes

### 4.1 Node.js Version Matrix

**Commits**: `0fb628e1`, `ee3e6af7`, `96ab5ea6`

**Changes**:
- Dropped Node 16, 18 support (EoL)
- Added Node 22, 24 testing
- Default now Node 22

**Documentation Needed**:
- Update README.md Node requirements
- Update any deployment docs

### 4.2 Stress Tests in CI

**Commit**: `6e4ff939`

**Changes**:
- Optional `stress-tests` job added to CI workflow
- Runs concurrent write tests

**Documentation Needed**:
- How to trigger stress tests
- When stress tests are run

---

## 5. Code Work Items (Pre-Release)

| ID | Task | Priority | Status |
|----|------|----------|--------|
| uuid-feature-flag | Add `TREATMENTS_ALLOW_UUID_LOOKUP` env var | 🟠 P1 | 📋 Ready |
| uuid-get-delete | Support GET/DELETE by identifier/UUID | 🟠 P1 | 📋 Blocked by flag |
| uuid-get-delete-test | Add tests for GET/DELETE by UUID | 🟠 P1 | 📋 Blocked by impl |

### Why GET/DELETE by UUID Matters

Loop's ObjectIdCache workflow:
1. POST treatment with `syncIdentifier` → server returns `_id`
2. Cache `_id` ↔ `syncIdentifier` mapping
3. Later: DELETE/PUT using cached `_id`

**Problem**: If cache is lost (app restart, 24hr expiry), Loop cannot update/delete its own treatments.

**Fix**: Allow `DELETE /api/v1/treatments/{uuid}` to search by `identifier` field when `_id` looks like a UUID.

---

## 6. Documentation Work Items

| ID | Task | Priority | Status | Assignee |
|----|------|----------|--------|----------|
| DOC-ENV-001 | Document NODE_ENV=test requirement in CONTRIBUTING.md | 🔴 P0 | ✅ Complete | - |
| DOC-ENV-002 | Document test environment variables (pool size, etc.) | 🟠 P1 | 📋 Ready | - |
| DOC-SCRIPT-001 | Document new npm test scripts | 🟠 P1 | ✅ Complete | - |
| DOC-API-001 | Document `identifier` field behavior for treatments | 🔴 P0 | ✅ Complete | - |
| DOC-API-002 | Document UUID _id handling for entries | 🟠 P1 | 📋 Ready | - |
| DOC-NODE-001 | Update Node.js version requirements | 🔴 P0 | ✅ Complete | - |
| DOC-CHANGELOG | Create CHANGELOG entry for 15.0.7 | 🔴 P0 | ✅ Complete | - |

---

## 6. Files to Update

### In cgm-remote-monitor:

| File | Updates Needed |
|------|----------------|
| `README.md` | ✅ Node.js version requirements updated |
| `CONTRIBUTING.md` | ✅ Test running instructions, NODE_ENV requirement, new scripts added |
| `docs/example-template.env` | Any new env vars (mostly OK) |
| `CHANGELOG.md` or release notes | ✅ Created with 15.0.7 changes |
| `docs/data-schemas/treatments-schema.md` | ✅ Identifier normalization documented |

### In this workspace:

| File | Updates Needed |
|------|----------------|
| `traceability/cgm-remote-monitor-docs-inventory.md` | New test infrastructure docs |
| `docs/backlogs/README.md` | Link to this backlog |

---

## 7. Verification

After documentation updates:

```bash
# Verify test docs are accurate
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447

# Test safety check works
unset NODE_ENV && npm test 2>&1 | grep -E "SAFETY|NODE_ENV"  # Should fail

# Test new scripts work
NODE_ENV=test npm run test:unit
NODE_ENV=test npm run test:integration
```

---

## 8. Related

- [PR #8444](https://github.com/nightscout/cgm-remote-monitor/pull/8444) - Dev branch PR
- [PR #8447](https://github.com/nightscout/cgm-remote-monitor/pull/8447) - UUID fix (merged to dev)
- [PR #8421](https://github.com/nightscout/cgm-remote-monitor/pull/8421) - MongoDB 5.x + test improvements
- [GAP-SYNC-046](../../traceability/sync-identity-gaps.md) - Test DB safety gap

---

## Last Updated

2026-03-17
