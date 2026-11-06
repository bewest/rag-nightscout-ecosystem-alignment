# Tenant clock HTTP: backend-abort availability diagnostic — 2026-11-06

**Reproduced availability failure in the opt-in prototype:** the explicitly faulted API worker exited with code1 after a PostgreSQL Client emitted an unhandled error. The selected transaction-clock assertion passed: the aborted write did not change its row, and the surviving worker progressed. A passing functional oracle does not establish worker availability or complete clock acceptance.

This immutable diagnostic audits preserved actual runtime output and pinned source. The report lane performed source-only review, started no services and changed no application code or current programme status. The [sanitized machine capture](tenant-clock-http-backend-abort-diagnostic-2026-11-06.json) records classifications, bounded stack frames and original-file hashes; it excludes private resource identities, host paths, credentials, connection URLs and request recipes.

## Anchors and scope

- Alignment report base: `de54fd05e1f2e57dd36e6cf3a6be11c453994dc1`.
- Exact diagnostic application source: `48b5bcd28a82c1e3fff62f7b3ed2343527e05427`.
- Earlier full functional HTTP fixture: `ad435f98441ba116443d16519dca64f3308e6501`.
- Earlier corrected-readiness HTTP attempt: `d90532ce1eb7d730e7cf7f1f2e9036ef39b6c91e`.
- Passive diagnostic preload SHA-256: `3ec4c818a565b23d5ad8f61f076624e5dc1a739b600f90929fbb2911c0519ea5`.

The selected diagnostic used the actual REST CLI process fixture and a controlled operator termination of its observed W1 database backend. The report describes a synthetic local prototype experiment, not a released-defect finding or a production failure recipe. The original log is preserved privately as `backend-abort-diagnostic-48b5.log`; its SHA-256 is `e6ed3e9d6cbb3c56fd00e65eacfbdd2c0419d576f7c23c4250e8000ee4cec0ce`.

## Actual observations

**Reproduced:** the selected case reports **1 passing (4s)**. Its success checks cover data/floor rollback and surviving-worker progress; they do not assert that the faulted API child remains available.

| Boundary | Observed result |
|---|---|
| Aborted W1 request | Transport failure; no successful write acknowledgement. |
| Original data row | Unchanged after the database fault. |
| Surviving W2 | Committed while the original data-row lock was still held, with the durable floor advancing by exactly one from the pre-abort value. |
| Faulted W1 before fixture disposal | Already exited **code1, signal null**. |
| Fixture action | **forcedKill=false**; this exit was not caused by a fixture SIGKILL during disposal. Socket closure was confirmed. |
| Passive monitor | origin **uncaughtException**, name **Error**, code **null**, connectionTerminated **true**. |
| Bounded stderr flags | unhandledError=true, connectionTerminated=true; administratorTermination=false and storageShutdownFailure=false. These flags classify captured stderr, not every possible server-side cause. |

The fixture's `portPresent` and `listeningMarker` fields record that a port number and earlier Listening output existed. They do not prove a live listener after process exit. The explicit socket-closure check is the later observation. Fault-child disposal is distinct from healthy graceful shutdown; unaffected workers retain their existing strict shutdown checks.

## Bounded emitter evidence

The captured stack is sanitized to module-relative or Node-internal frames. Its material sequence is:

```text
Error: Connection terminated unexpectedly
    at Connection.<anonymous> (node_modules/pg/lib/client.js:204:73)
Emitted 'error' event on Client instance at:
    at Client._handleErrorEvent (node_modules/pg/lib/client.js:422:10)
    at Connection.<anonymous> (node_modules/pg/lib/client.js:222:16)
```

The independent passive-monitor record also identifies `node_modules/pg/lib/client.js:204:73` and Node event frames, with origin uncaughtException. It contains no SQLSTATE; the recorded code is null. The reported stack and nonzero process exit support the availability classification without inferring a more specific server error from a generic connection-termination message.

**Read-derived source boundary:** at the pinned application source, `lib/storage/postgres-connection.js` attaches an idle pool error listener, then checks out a Client for a transaction. The shown transaction path has no corresponding checked-out Client error listener. Installed driver source explains the captured frames: unexpected connection end creates an Error and can emit it on Client after query error handling. This source inspection bounds the next engineering investigation; it is not acceptance of a proposed repair or evidence that all disconnect schedules fail alike.

The diagnostic preload installs only `uncaughtExceptionMonitor`. It records a restricted origin/name/code/location summary; it does not install an uncaughtException handler or Client error listener and does not intercept, suppress or change default fatal behavior. At source48b5, the selected test passes the preload only to W1 through its first-worker options; W2 is started without it. The monitor and fixture source were independently read and hashed for this record.

## Preserved earlier attempts

| Separate capture | Actual result and limit |
|---|---|
| `functional-d905.log` | **4 passing/1 failing**: the controlled backend-abort body passed, then strict afterEach cleanup failed with AggregateError. Later functional cases were not established by that attempt. |
| `functional-ad435.log` | **7 passing/1 pending/0 failing**: all functional cases passed after explicitly scoped fault-child disposal; the optional benchmark remained pending. It recorded the faulted child's nonzero exit and does not establish child survival. |
| `backend-abort-diagnostic-48b5.log` | **1 passing** selected diagnostic, with the bounded Client emitter stack and passive fatal-monitor record above. This is not a complete rerun of the seven-case functional cohort. |

Original outputs remain unchanged. The selected diagnostic does not turn the earlier failure into a pass, add benchmark acceptance, or relabel a selected case as a complete HTTP campaign. The [lower-port proof](tenant-commit-clock-lower-proof-2026-11-06.md) remains separately scoped PostgreSQL/SQL-readiness evidence.

## Cleanup and disposition

The diagnostic log announces fixture cleanup of **2 owned containers and3 volume references**. The coordinator reports those resources independently confirmed absent. This report independently read the announcements, but no separate post-cleanup absence artifact was available to this lane; its machine capture explicitly distinguishes that reported outcome from independently audited absence proof. No resource identities are published, no orphan ownership is inferred, and this source-only task performs no resource operation.

A separate engineering lane is investigating checked-out Client failure handling with new unit/control work. No repair or new runtime acceptance is recorded here. Clock code remains separate from the combined settings/acquisition/owner application. Worker availability, corrected full HTTP behavior, real fault controls after repair, contention/recovery bounds, performance, full nonbrowser/browser and final prcheck acceptance remain outside this diagnostic. No milestone promotion, BF allocation, release-impact claim or application publication follows.
