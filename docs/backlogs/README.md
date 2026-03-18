# Backlogs

Active work streams for the Nightscout ecosystem alignment project.

**Archived completed work**: [archive/](archive/)

---

## 🔴 P0: Profile API Array Handling Regression - **IN PROGRESS**

**Problem**: MongoDB driver migration broke array handling for Profile API. NightscoutKit (Loop) sends `[profile]` arrays but `insertOne()` rejects them.

**Backlog**: [profile-api-array-regression.md](profile-api-array-regression.md)  
**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`  
**NightscoutKit**: `externals/NightscoutKit/`

| ID | Task | Status |
|----|------|--------|
| `profile-array-fix` | Fix profile API array handling (add `insertMany`) | ✅ Complete (`cbb6d061`) |
| `devicestatus-purifier-fix` | Fix devicestatus API purifier for arrays | ✅ Complete (`2e81ce07`) |
| `fixture-nightscoutkit-profile` | Extract NightscoutKit profile fixtures | ✅ Complete (`9fd53e32`) |
| `fixture-nightscoutkit-devicestatus` | Extract NightscoutKit devicestatus fixtures | 📋 Ready |
| `fixture-nightscoutkit-treatments` | Extract NightscoutKit treatment fixtures | 📋 Ready |
| `test-matrix-api-array` | Create API array handling test matrix | ⏳ Blocked (needs fixtures) |
| `test-matrix-client-behaviors` | Create client behavior test matrix | ⏳ Blocked (needs analysis) |

**Root Cause**: Commit `d46c5b41` changed `insert()` → `insertOne()`, breaking array support.

**Correct Pattern** (from treatments):
```javascript
if (!Array.isArray(data)) { data = [data]; }
for (let i = 0; i < data.length; i++) { ctx.purifier.purifyObject(data[i]); }
ctx.collection.createMany(data, callback);
```

---

## ✅ P1: UUID_HANDLING Scope Correction - **COMPLETE**

**Problem**: Code incorrectly copied `syncIdentifier` and `uuid` fields to `identifier`.
Should ONLY handle UUID values sent to `_id` field.

**Backlog**: [uuid-identifier-lookup.md](uuid-identifier-lookup.md)  
**Worktree**: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

| ID | Task | Commit | Status |
|----|------|--------|--------|
| `uuid-fix-scope` | Remove syncIdentifier/uuid copying from `normalizeTreatmentId()` | `8fc155aa` | ✅ Complete |
| `uuid-fix-entries` | Apply same fix to `normalizeEntryId()` in entries.js | `8fc155aa` | ✅ Complete |
| `uuid-fix-tests` | Update tests for corrected scope | `8fc155aa` | ✅ Complete |

**Dedup preserved**: `syncIdentifier` and `uuid` still used in `upsertQueryFor()`, but NOT copied to `identifier`.

---

## ⚠️ Nightscout Server Available

**A cgm-remote-monitor server is ready for testing:**

| | |
|---|---|
| **Location** | `/home/bewest/src/worktrees/nightscout/cgm-pr-8447` |
| **URL** | `http://localhost:1337` |
| **Start** | See commands below |

**Start the server:**
```bash
cd /home/bewest/src/worktrees/nightscout/cgm-pr-8447
source my.test.env   # Sets INSECURE_USE_HTTP, API_SECRET, MONGO_CONNECTION
npm start
```

**Required environment** (`my.test.env` contents):
```
API_SECRET=test_api_secret_12_chars
MONGO_CONNECTION=mongodb://localhost:27017/nightscout_test
INSECURE_USE_HTTP=true   # Required for localhost testing without SSL
PORT=1337
```

**Verify running:**
```bash
curl http://localhost:1337/api/v1/status.json
```

---

## 🎯 Start Here: Integration Test Harness

**[integration-test-harness.md](integration-test-harness.md)** - Central document for running cgm-remote-monitor locally and testing with Swift, Kotlin, and JavaScript clients.

```
Swift (Loop) ──┐
               │
Kotlin (AAPS) ─┼──▶ cgm-pr-8447 (localhost:1337) ──▶ MongoDB
               │
JavaScript ────┘
```

**Proposals Under Test**: [REQ-SYNC-072](../../traceability/sync-identity-requirements.md#req-sync-072-transparent-uuid-promotion-option-g) (Option G - **Recommended**), [REQ-SYNC-070](../../traceability/sync-identity-requirements.md#req-sync-070) (Identifier-First), [REQ-SYNC-071](../../traceability/sync-identity-requirements.md#req-sync-071) (Server-Controlled ID)

---

## Reference

### Key Documents

- [Profile API Array Regression](profile-api-array-regression.md) - Active work: array handling fix
- [Client ID Handling Deep Dive](../10-domain/client-id-handling-deep-dive.md) - Which apps send UUID to _id
- [uuid-identifier-lookup.md](uuid-identifier-lookup.md) - UUID_HANDLING implementation spec (complete)

### External Sources

- `externals/NightscoutKit/` - Loop's Nightscout client library (fixture extraction source)
- `externals/LoopWorkspace/` - Loop iOS app
- `externals/Trio-dev/` - Trio iOS app
- `externals/AndroidAPS/` - AAPS Android app

### Worktree

| Location | Branch | Purpose |
|----------|--------|---------|
| `/home/bewest/src/worktrees/nightscout/cgm-pr-8447` | wip/test-improvements | Active development |

### Archived Work

Completed analysis and testing work: [archive/](archive/)

---

## Last Updated

2026-03-18
