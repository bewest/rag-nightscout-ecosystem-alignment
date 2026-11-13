# Live admission and metadata configuration feed — 2026-11-12

Reproduced in isolated resources on core `d20354797e368b03af171f4417ead60a6282d098`
(`codex/tenant-live-add-20261112`), including coordinator `5ea1e36c` original history.
All source/test instrumentation is committed at that head. No full campaign or push.

```bash
NS_TENANT_LIVE_ADD_TEST=1 NS_D6_FEED_TEST=1 MULTITENANT_STATIC_TENANTS=lab node node_modules/mocha/bin/mocha.js tests/tenant-live-add.integration.test.js tests/change-feed.integration.test.js --timeout 60000 --reporter spec
node scripts/test-tiers.js check
node scripts/test-multitenant.js --list
```

`native-final.log`: **12 passing**. Own disposable PostgreSQL and Vault, random
loopback ports, synthetic rows only, owned resources removed. Actual provisioning,
checkpoint readiness, shipping clinical evaluator and realtime projection factories
produce a new tenant's first alarm and frame while the existing tenant keeps its
runtime and alarm output. Failed warm retry, three-add burst, selected removal,
new paused/suspended deferred admission and resume without registry/data revision
are exercised. Observed first new alarm/frame including failed warm: **386 ms**.
This tiny synthetic harness is not a capacity or deployment latency guarantee.

The D6 cases exercise EXECUTE-only wrappers, RLS, committed notification before ACK,
actual backend interruption inside notification COMMIT, reader/listener outage,
activity changes without writes, transaction overshoot refusal and catalogue tamper.
The optional settings/policy publication selects exactly tenant_id+version/generation;
its owner lacks plaintext SELECT. Planted JSON column, wrong projection and plaintext
grant are refused. Settings/policy-only changes invalidate evaluator configuration
and realtime frame through authoritative rereads; clock is unchanged. Combined
observed two-change signalling: **123 ms**. The presentation/evaluator outputs here
use synthetic configuration rows, not full D15/clinical policy integration.

`focused-final.log`: **93 passing** on the same final source. Includes atomic staged
admission/activation rollback, remove-during-prepare, empty startup, bounded burst,
new tenant watchdog age, owned/unowned evaluator selection, dynamic paging after
listener loss, removed hint refusal and existing configuration/consumer/runtime
checks. Pool owned/unowned is a focused unit control; native role placement and
external alarm delivery remain coordinator acceptance. Tiers **685 files / 8 tiers**;
`inventory-final.log` **77/77** opt-in suites; changed module lint has no output.

`freeze-start-roster-red.log`: actual source mutation on `69d75085` (same runtime
and test source, before documentation/inventory-only d203): registry admission
`pump()` returned immediately. Native provisioning succeeded and the existing
240 synthetic alarm continued; new tenant output never arrived, causing
`LIVE_NATIVE_WAIT_EXPIRED` and exit 1. Thus a frozen startup roster breaks the
new-tenant output oracle rather than fixture setup. Exact original source bytes
restored in `finally`; final d203 native run above is green.

Earlier setup-only native failure used nonexistent activity `grantsFor` export
(actual module exports `grants`); corrected before final source. A sandbox loopback
EPERM in a pre-final focused run was environmental, rerun with permitted loopback.
No setup failure is counted as a semantic control. SQL row/byte limits remain
post-decode: no hard shared-server RSS or native transaction memory bound claimed.

Original history is local/unpushed. Root owns frozen joined clinical/browser/corpus,
actual restore census, deployment qualification and quiet-host capacity. Sharding
agent starts after this runtime boundary. Local lane handoff is
`externals/work/HANDOFF-d6-native-discriminators-2026-11-11.md` (untracked machine detail).
