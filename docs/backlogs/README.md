# Backlogs

Active work streams for the Nightscout ecosystem alignment project.

**Archived completed work**: [archive/](archive/)

---

## ✅ P0: UUID_HANDLING Scope Correction - **COMPLETE**

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

- [Client ID Handling Deep Dive](../10-domain/client-id-handling-deep-dive.md) - Which apps send UUID to _id
- [uuid-identifier-lookup.md](uuid-identifier-lookup.md) - Full implementation spec

### Worktree

| Location | Branch | Purpose |
|----------|--------|---------|
| `/home/bewest/src/worktrees/nightscout/cgm-pr-8447` | wip/test-improvements | Active development |

### Archived Work

Completed analysis and testing work: [archive/](archive/)

---

## Last Updated

2026-03-17
