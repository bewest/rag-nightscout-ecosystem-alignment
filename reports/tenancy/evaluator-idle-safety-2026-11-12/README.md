# Evaluator baseline idle safety and strict work support

Reproduced 2026-11-12 on core
2d0ae0354a38b4a88f43bc2ae5ec60c085058f64 (parent 47b43b6246ce7f94f1f1f0d01830495a78b28add),
with instrument e0624657ce07b9c15fd0ef9e4db3458eaf776041. Content SHA256
52c76f7500312bc3ce8006f3783444b04489bdf53cd1f764417f77cf8333ba1d / 37 files.
This is a focused source/instrument capability, not a new deployment, native-PG,
capacity or full-acceptance measurement. No Docker, cloud or live-state query ran.
Seed/settings/plugins, phase durations, traffic, query/byte/decompression budgets,
clinical scheduling and strict work/recovery policies remain unchanged.

The coordinator's actual default-projection finding established that a 120 s
normal idle interval may have no due time work. The separate current result
therefore measures sampled idle safety; it never turns quiet into successful work.
Every owner must be already acquired, healthy and stable with no acquisition
delta, hidden failure, foreign work or sampled clinical job. All six named
clinical flags must be clear for BOTH result branches. Read-only backstop/signature
checks and notification-consumer polling are allowed and receive no work credit.

A current explicit null due + complete clear flags is NO_TIMER_DECLARED. A finite
due beyond the entire actual observation span is FUTURE_DUE. Both can produce
TIME_NOT_EXERCISED/zero completions, with timeWitness:false. Earlier observed due
values cannot be erased by later future values: they require later successful
time progression. Pending clinical work is UNMEASURED/BUSY even alongside real
time completion; raw successful counts remain intact. Unknown/legacy fields,
missing/invalid timestamps, reset/errors, foreign work or uncredited legacy-cycle
movement cannot produce quiet. Actual read boundaries use bracketed UTC and
monotonic microseconds with a common offset-interval guard. This is not a
continuous-activity or timer-deadline SLO.

The source delta is observation only: running through full owned-window cleanup,
queued boot, owned acquire/time and borrowed acquire/time fixed slots. Selected
health/DTO reads remain O(k), with the same 128-row selector and original server
caps; no inspector call schedules work or acquires ownership. Source metadata is
named booleans; the NEW idle artifact encodes the six flags as a validated 0..63
bitmask in that exact order, preserving complete owner and foreign rows.

Capability version 4/profile-selection version 3 pins a separate idle-safety-v1
artifact/policy. The standalone historical strict v1/v2 readers, strict load and
changed-runtime acquisition recovery retain their semantics. Current receipts
require the new idle proof plus an independently pinned exact-source/image/
instrument native TIME wrapper, recomputed with the strict CURRENT v2 checker.
Earlier-source attribution requires explicit coordinator approval, never inferred
equivalence. Quiet baseline support does not establish active-alarm capacity.

## Focused checks and meaningful controls

- Source inspection/job-context/partition/consumer union: 33 PASS. Actual private
  UNIX listener, recording operation-window port; no real PostgreSQL claim.
  All four queued slots, queued boot and held full-window completion are observed;
  repeated observations cause no authority or work. Actual selected128/[] census
  controls reject whole-roster iteration. Original47b getter fails the new queued
  slots control (undefined vs exact flags); restored getter passes.
- Idle assessor: 12 PASS, including quiet future, explicit null/no pending, missing
  and malformed fields, all six pending-positive-TIME flags, hidden failures,
  resets, new demand, all foreign rows, legacy-only movement and clock ambiguity.
  Scratch dropped-opportunity and dropped-pending guards produce falsePASS; the
  restored checks refuse.
- Unchanged strict-progress checks: 14 PASS with actual 2d0 component/window fixture
  enabled, including stopped-scheduler refusal and inspection noninterference.
- Existing actual source/status/fingerprint fixture: 7 PASS. Producer contract: 19 PASS.
- Full recorded-receipt suite: 51 PASS at d602; final e062 targeted native-version,
  native-support/quiet-refusal and complete full-ladder positive: 3 PASS. Those
  final checks cover the only subsequent change, global clinical busy refusal.

Independent review found two real gaps in the unreleased instrument candidate.
At 0d72 the current native gate accepted a coherently rehashed historical v1
proof through its compatibility reader. The authored control is RED (ValueError
not raised); d602 adds explicit native-only v2 kind/current-policy fencing and
passes while standalone historical readers remain valid. At d602, pending jobs
were checked only on the quiet branch; real TIME progress plus a queued clinical
job passed. The new control is RED (Refused not raised). e062 applies the global
all-six sampled-owner guard and all 12 idle controls pass. Original failures and
restored outputs remain archived; no earlier capture was relabelled.

## Reproduction and integration

On an owned exact-core tree with this lane's read-only same-lock dependencies:

```sh
node_modules/.bin/mocha tests/evaluator-inspection.test.js \
  tests/evaluator-job-context.test.js tests/evaluator-partition.test.js \
  tests/evaluator-consumers.test.js --reporter dot
```

On an owned committed alignment tree, with PYTHONDONTWRITEBYTECODE=1:

```sh
python3 -m unittest discover -s tools/mt-bench/m7-joined -p test_evaluator_idle.py
python3 -m unittest discover -s tools/mt-bench/m7-joined -p test_contract.py
python3 -m unittest discover -s tools/queue/gates -p test_m7_joined_receipt.py
```

For actual-source fixtures, select M7_PROGRESS_CORE=<owned2d0> for
test_evaluator_progress.py; select M7_PROFILE_TEST_CORE=<owned2d0> and
M7_PROFILE_TEST_COMMIT=2d0ae0354a38b4a88f43bc2ae5ec60c085058f64 for
test_profile.py. The latter needs child git read permission; initial sandbox
spawnSync git EPERM was classified as instrumentation access, then the scoped
read-only run passed. Dependencies are lane-owned npm-ci/ignore-scripts history
with byte-identical lock 6418fe21c18346435f643b8496d6b7ec23c9c6de28f1925c3bb2028eb575e93e,
not a fresh installation for 2d0. Node v22.23.4.

Root owns ordinary integration, a NEW exact paired image and required post-clinical
native TIME witness, paired qualification, frozen comprehensive acceptance and
any later capacity authorization. Those runtime results remain UNMEASURED here.
Item 8 remains a separate post-baseline lane. No patient data, credential values,
queue/release/decision edits, pushes or source changes to another lane occurred.
Logs normalize only owned absolute prefixes; captures are synthetic.
