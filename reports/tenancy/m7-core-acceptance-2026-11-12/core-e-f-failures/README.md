# Original Core E/F failed acceptance chronology

**Both original campaigns remain NOT_ACCEPTED.** These immutable sanitized
projections publish existing captures only. They do not establish current-source,
paired-image, release, pilot or capacity acceptance. No tests, services, cloud or
resource queries were run to prepare this publication. G has its own record and
is not duplicated here.

## Exact original inputs

Both campaigns executed core `ff5156b984424f1ef34bcef22d5bfa0071354cfa`, deployment
metadata `cf5bda3f2d189bac5d60269df5644759c40db9e1` and alignment
`8ae6f4a3729548de0c88cc0ee5b3c0aede9aba61`, with Node24.22.1/npm11.19.1.
E used worker instrument `d358f64e464ec1b03901af1cbaf9bbed39b4caf1`;
F used the fixture-limit worker repair `7209cb29020543a82412cd69d2751ca939cf4318`.
Their captured worker, Node binary, lock and source-environment hashes are retained
in [E](core-e.json) and [F](core-f.json). They are original process facts, not
inferred from later source or a current worktree.

| Tier | E passing/pending/assertion failures | E command | F passing/pending/assertion failures | F command |
|---|---|---|---|---|
| unit |3563 /1 /0|0|3563 /1 /0|0|
| DOM |205 /0 /0|0|205 /0 /0|0|
| dependency |368 /2 /0|0|368 /2 /0|0|
| core |319 /0 /0|0|319 /0 /0|0|
| harness |99 /0 /0|0|99 /0 /0|0|
| integration |unknown /unknown /unknown|interrupted; no final code|3643 /836 /0 reported assertions|1: execution guard|
| stress, browser, enabled corpus |NOT_RUN|NOT_RUN|NOT_RUN|NOT_RUN|

The first five terminal summaries are successful commands in each original run.
Their pending cases remain pending. The 86-suite configured corpus inventory was
read from exact source, not executed in either run. Default-integration pending
bodies are not native execution; later enabled-corpus or repaired-source results
must remain separately attributed.

## E: fixture death during interrupted integration

Captured Mongo error24 `Too many open files` occurred at
2026-11-12T18:43:00.782+00:00 during WiredTiger directory synchronization while
creating an index. WT_PANIC and fatal assertion50853 followed; Docker recorded
exit14 at2026-11-12T18:43:00.856513703Z, OOMKilled:false. Docker Ulimits was empty:
this proves no explicit container override, **not an effective cap of1024**.
The actual nofile soft/hard limits remain UNMEASURED. Captured disk observation
did not report disk-full; no OOM cause was observed.

Integration has a partial log, no terminal Mocha counts and no completed command
record. It was cancelled after fixture failure. Hook announcements lack event
timestamps; their order relative to Mongo death is unresolved. Printed clinical
payload dates cannot order failure events. The fixture fatal is reproduced in the
capture, but this does not prove every hook failed because of it or exclude an
earlier independent source failure. No final integration counts are invented.

E has no captured worker final result or in-VM owned-Mongo removal/positive-absence
proof: worker cleanup and residual arrays remain UNMEASURED/unknown. Outer controller
and watchdog teardown, followed by zero remaining provider resources, were separately
verified. Provider absence does not substitute for a missing fixture-finalizer record.

## F: observed fixture-limit repair, strict execution failure

F captured12 actual mongod PID1 limit observations: ready, before/after each of the
first five tiers, and before integration. Every observed soft/hard value was65536.
Mongo remained running before intentional removal. This records the fixture-limit
repair working in F, not an unlimited future fixture capacity claim.

Integration completed its Mocha epilogue with3643 passing/836 pending and no
reported assertion failures, but stderr recorded:

```text
TEST_EXECUTION: no test body completed in tests/change-feed.integration.test.js
```

The strict command returned1. Exact-source reporter accounting treats ordinary
skipped bodies differently from recognized opt-in registration; the disabled D6
lab used ordinary describe.skip. This is a read-derived source explanation backed
by the captured guard failure, not a passing integration result. Worker completed
stages stop after harness; stress, browser and full enabled corpus did not run.

F's final worker result separately records owned-Mongo cleanup verified and empty
container/volume residuals. Outer controller/watchdog/provider cleanup was also
verified. Neither kind of cleanup changes failed acceptance to PASS.

The later [feed opt-in accounting repair](../../m7-unit-repairs-2026-11-12/feed-opt-in-accounting/README.md)
has its own source, original-red/restored controls and runtime-input comparison.
It is linked, never imported into these E/F results. New campaigns and any current
candidate acceptance belong to the coordinator's separate frozen-source records.

## Capture and sanitization

[input-anchors.json](input-anchors.json) pins the private verified assessment bytes
and76 original artifact hashes (26E/50F), all independently reread and matched at
publication. Only whitelisted source/instrument, process outcome, fixture and cleanup
fields are published. Private resource identities, addresses, environment contents,
credentials, raw log dumps, document payloads and cost estimates are omitted.
Source Git hashes and test paths identify reviewed code, not private resources.
Mongo's filesystem suffix is omitted without changing its error/code chronology.
No recorded outcome, counter or process return code is altered. E's unmeasured
effective limit remains the nonnumeric value UNMEASURED.

The previously captured E checker controls are identified separately; they cover
wrong pins, missing successful logs and partial-count/cleanup refusal. They were
not rerun for this publication. [manifest.json](manifest.json) binds the published
files. Root owns programme records, failure disposition and future acceptance;
this leaf changes no source, gate, queue or release state.
