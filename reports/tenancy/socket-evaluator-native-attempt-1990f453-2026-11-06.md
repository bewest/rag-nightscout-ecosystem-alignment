# Joined socket/evaluator native attempt — 2026-11-06

**Reproduced failed batch prediction:** committed application `1990f453e09303d9dcf3394f0f50a42c3ce4052b` produced **9 passing / 0 pending / 2 failing** in one combined targeted invocation. Mocha exited 2 and the owning runner exited 1. No repair, retry or product mutation occurred in the capture. [Machine result and immutable raw-artifact hashes](socket-evaluator-native-attempt-1990f453-2026-11-06.json).

```bash
node scripts/test-multitenant.js --only tenant-socket-data-forwarding \
  --only tenant-projection-evaluator --record <fresh-private-output>/run.json
```

The evaluator family passed all seven actual PostgreSQL cases: fresh physical-view equivalence, typed identity/current clinical reading, advanced empty-cache bootstrap, A/B retained-state isolation, downstream failure/retry, explicit later-time recomputation and committed producer-death recovery. This capture is positive evidence only; authored native semantic controls are separate. No provider, scheduler, notification or full M5 claim follows.

The socket DATA family reported two passing and two failing. Its PostgreSQL add path reached the existing bounded-read refusal, `unsupported limit or skip without a sort`, through canonical socket dedup `storage-reads.findOne`. That made the pattern acknowledgement invalid. The held-COMMIT test timed out before its entered barrier for the same pre-write reason; timeout is not a valid semantic control. The current-authority foreign-role refusal case passed. The rollback case's green result is **vacuous for its intended post-write boundary**: the earlier read refusal prevented reaching the injected abort. It is not accepted rollback evidence.

Read-derived follow-up refutes a flag-only remedy. The existing explicit natural-order capability uses `insertion_ordinal`, present in entries/food but absent from the treatments/device-status catalogues used here. Enabling its flag alone would produce a missing-column error. No arbitrary identifier/date sort, source relabelling or fixture-only schema mutation was applied. An optional versioned capability prototype and old/new/populated migration matrix continue separately; their outcome is unmeasured by this record.

Exact two owned containers and three captured mounted volumes were independently verified absent. Host volumes returned to the 462 baseline; unknown older services were preserved. Runtime released 22:38:45Z. The coordinator independently verified all six indexed original artifact hashes. Full/browser/whole-corpus/final-prcheck acceptance was not attempted. Published `83582e87`, R64 remote success and all prior milestone claims remain separate.
