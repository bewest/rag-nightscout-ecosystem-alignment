# Independent scheduler review and bounded completion observer

Captured2026-11-12. Reproduced component/protocol criteria below pass on core
53a8ad725049e6bdacdd903ea8bd759c64781c8d. No additional material read-derived
scheduler blocker remains from this review. Native PostgreSQL durability,
phase controls and actual product transports remain the runtime owner's separate
proof, followed by coordinator-frozen comprehensive and paired-image acceptance.
No capacity result, cloud action, deployment qualification or release is claimed.

Source-owned observer/receipt commit: d58756664c4a29c2261c0cbd8c405836e2860179,
from alignment c8a7a9b04a165b96a9659a9306df3d03be02a081. Instrument content SHA
62e6fb240c0f857b4c801b5b40226875f8ea1b0788c3f53de596835f9e3837f1,
31 tracked/reused files in observer-instrument-manifest.json. Exact core review
history: original d50502bb6126bda2bb0af384569e1d95de114f2f;
failed first repair5ad00a523d12b5f4ef9c55c107b09f328be73309;
failed same-parent follow-up6e52fbf4580a72db371a21066f390497357a503c;
reviewed repair53a8ad725049e6bdacdd903ea8bd759c64781c8d.
Every review target used an owned detached archive; no peer product edits.

## Reproduced review criteria and controls

- Original due callback inherits an expired operation context: cycles stop at1
  with EVALUATOR_WINDOW_REFUSED / LIFECYCLE_WINDOW_SCOPE_INVALID. A timer-only
  boot context restores progress, while ordinary late application work refuses.
  Repeated health reads leave component/window counters unchanged.
- First repair5ad deadlocks awaited runtime.acquire inside an active same-tenant
  parent with one physical-client recording protocol. Original d505 completes.
  Same-parent two-acquire coalescing also regressed. Independently queued work
  joined while holding that client already deadlocked on d505; typed busy refusal
  for that distinct case was explicitly approved by the coordinator.
- Follow-up6e52 restores acquire but newly rejects same-parent no-stamp wake and
  backstop as EVALUATOR_JOB_PARENT_BUSY. Original d505 completes both. On53a8 all
  three same-parent matrix cases complete. Independent running work busy-refuses;
  an actual late callback invoking runtime.acquire itself scope-refuses.
- Actual53a8 runtime/consumer/inspection with10000 synthetic IDs: [] performs no
  tenant lookup;128 selected rows perform256 state-map gets and128 current reads,
  with zero full-roster iterations. Three unselected legacy/full-scan controls
  hit the throwing iterator. This proves bounded selected-path access, not PG cost.
- One invalidation-drain scratch discriminator never reached its adapter on ANY
  target. Its ADAPTER_NOT_REACHED results are retained as vacuous and support no
  defect claim. Read inspection confirms invalidateTenant still awaits its drain.

Read-derived ownership review: due/repeat/owned queue continuations and explicit
boot-owned feed/membership/registry callbacks obtain independent fresh admission;
origin revised/current decisions remain in their original window. Public calls
retain same-parent reuse, wrong/expired-parent refusal and fixed four-slot ticket
provenance. The operation-window execute guard is preserved. Borrowed work cannot
earn successful fresh-window completion credit. Actual errors remain observable.

## Observer/receipt checks

Exact committed commands:

```bash
M7_PROGRESS_CORE=/absolute/owned/core-53a8 \
M7_PROFILE_TEST_CORE=/absolute/owned/core-53a8 \
M7_PROFILE_TEST_COMMIT=53a8ad725049e6bdacdd903ea8bd759c64781c8d \
python -m unittest discover -s tools/mt-bench/m7-joined -p 'test_*.py'
python -m unittest discover -s tools/queue/gates -p test_m7_joined_receipt.py
```

38 joined focused tests PASS/0skip;48 receipt tests PASS. The actual component
fixture executes the committed selector helper against actual window/runtime/
inspection with a recording SQL port and synthetic component. Time-only scheduling
passes; stopping the scheduler is UNMEASURED, with repeated inspection changing
neither component-call nor SQL counts. Removing the successful-progress guard
produces a false PASS, and restoration refuses again. Hidden error, reset, wrong
coverage, foreign work, stale recovery runtime, missing successful acquisition,
missing phase, wrong source identity and gzip decode-budget controls refuse.
Generated probe syntax and helper hashes are checked. No actual Docker collector,
clinical output or capacity campaign is implied by these focused tests.

The first optional status-fixture attempt was sandbox-blocked: Node-to-git
spawnSync EPERM, surfaced as M7_SETTINGS_REFUSED. Same exact fixture with permitted
subprocess access passes. The earlier no-fixture run explicitly skipped1 of38;
it is retained and superseded only for that fixture by the38/0skip capture.
Dependencies are this lane's owned exact-lock copy from prior native/clinical
work, not a peer tree. Reviewed core locks are unchanged, and all core archives
remain clean. No new native service/container/volume was created by this review.

Integration: root ordinary-merges this branch, pins the final instrument after
joining approved repairs, and freezes the coherent runtime. Capacity/pilot
receipts require complete idle/load/recovery artifacts under profile-selection2;
functional acceptance still does not require future capacity. Component-profile
wiring remains deferred until comprehensive and paired deployment acceptance.
The observer preserves default public traffic/plugins/cadences. Insufficient
idle time-only progress remains UNMEASURED; no cold cohort or deadline SLO is
invented. Private raw evidence plus deterministic gzip retain complete foreign
rows. Gates stream-decode at most16MiB/artifact and64MiB total progress evidence.
Large optional ladder proof can honestly exceed that budget and remain unmeasured.

capture-manifest.json pins private-original and published hashes. Published
captures normalize only workspace/scratch path prefixes; original captures remain
private. Earlier native/clinical captures remain unchanged. Local worktrees,
paths and owner handoff are retained in the lane's existing untracked handoff.
