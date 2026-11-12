# New-pair default idle safety: first window only

Reproduced 2026-11-12: the exactly-once startup/default-normal observation passes
idle safety, with both owners TIME_NOT_EXERCISED/FUTURE_DUE, zero time completions
and timeWitness:false. This is a 21.054303402081132 s functional observation, NOT
a 120 s pilot, capacity, active-alarm, strict TIME or recovery result.

## Exact capture

- Core 2d0ae0354a38b4a88f43bc2ae5ec60c085058f64.
- Deployment dcc4a70bafd4edf31c5cab4bf3099883bd7e37f9.
- Image sha256:b16e338214d19a409333a079a3950cb97eed9cd7cc00b5eacbff28e4bd72054d,
  actual source labels and all three evaluator CIDs/StartedAt verified before/after.
- Instrument c33acdc48208586354002573b93ce4f33d6c0c6a, content
  52c76f7500312bc3ce8006f3783444b04489bdf53cd1f764417f77cf8333ba1d / 37 files.
- Actual nonce a8d9cc6f-2c1a-4749-8bf4-b350cc39a4bf, owned-pair artifact
  SHA fd0e8cf2a7ca4896fe8f8d2dcd0c014ddf35dc05d2beb8a38ed198b23e1cac4a.
- Executed capture driver 8385b1a11b8c4245b7a180b941676458e9889965e2982168af21e46937b101ce;
  unchanged SDK helper c9e0370e8a3ca4d08dfd70b1290a36a0d57f33c34f3a5639a2e6d81b77b707e8.

RT explicitly released the window after startup/owned acquisitions were ready,
with synthetic default A123/B177, BEFORE stock/settings/clinical/move writes. The
collector made 9 successful bounded private RPCs: every 2 configured synthetic IDs
on every 3 evaluator instances, three snapshots 10 s apart. All 6 rows per snapshot
are retained (18 total), including all 4 foreign rows. Actual UTC read brackets,
monotonic brackets, helper observation timestamps and six clinical job flags are
retained; common-offset clock guard passed. No write, work trigger, extra public
traffic, retry, extension or lifecycle command was performed by this lane.

| Owner | Acquisitions | Time completions | Legacy cycles | Failures | Generation | Job mask | Due reason |
|---|---|---|---|---|---|---|---|
| A/evaluator |1→1|0→0|1→1|0→0|5→5|0 throughout|sgv-recent-10|
| B/evaluator-2 |1→1|0→0|1→1|0→0|5→5|0 throughout|sgv-recent-10|

A dueAt 1794504912425 and B dueAt 1794504913043 remain unchanged across samples;
both are beyond the final actual read end 1794504542629. Foreign counters/jobs
remain unchanged/clear and foreign due fields explicitly null. Container/runtime
identity, unique admitted ownership and generation remain stable. No error or
legacy-only work is hidden.9 RPC response bytes 19999; sum of parallel round
collection times 1.0226605697534978 s. This is collector overhead, not CPU or a
performance/SLO claim.

[Actual wrapper](default-idle/observation.private.json) raw
SHA d0e1f609f19a32ed9db5e35b3cf864009d8ecff1af05015f169db78d67f5039b;
deterministic gzip SHA a96171c9b3cfa9e28e43dfc241fb86d76fd990ea4157af7c7a08858c542b9fb3.
Decoded gzip equals the raw wrapper. Numeric JSON/JSONL captures are unchanged.
The wrapper's proof is the separate evaluator-idle-safety-v1 contract. It MUST
NOT be supplied as the required native strict TIME witness.

## Controls and later boundary

Offline recomputation against an owned exact c33 archive returns PASS. Seventeen
actual-row mutations refuse clinical busy flags (all 6), earlier due hidden by
later future due, legacy-only work, hidden failure, foreign work/missing row,
runtime reset, malformed/missing jobs, missing clock brackets and clock jump.
The actual zero-work rows remain UNMEASURED under the strict TIME checker.
Restored proof passes after each control. No live stopped-worker control ran.
Recording-only driver controls additionally prove distinct branches, exact-once
output refusal and nonce mismatch refusal; they are NOT native measurements.

After this completed window was released, the stock/restore qualification FAILED
on three typed B_SETTINGS_STATUS_503_TENANT_WARMING responses. RT's read-only
classification observes a restore demo artifact state passed/B committed, while
the outer settings-continuity assertion failed. Original request timestamps and
upstream instance IDs were not retained, so which tenant was cold and whether
those responses occurred before/during restore are not established here. Global
role health is not historical per-tenant warmth. The first idle-safety PASS does
not clear that failure or establish a product defect mechanism.

The second post-clinical strict nativeTIME window, settings/clinical qualification,
controlled RT move and export are NOT_RUN. There was no second-window resource
selection, private query, retry or substitute proof. The pair is not accepted and
has no current nativeTIME witness. Stage status is recorded separately in
[stage-status.json](stage-status.json). The [canonical original failure report](../../api-readiness-continuity-2026-11-12/original/README.md)
owns the later typed chronology and causal limits; its selected safe classification
artifact SHA is d210b34fc7b0ba88454dc95e64e48569b7d79dccda211168198469ee0f95fc0b.

Root's original c33 code was archived/hash-verified before releasing its head hold.
All subsequent work used only captured files; no retained stack was queried.
Private originals remain 0700/files 0600. The capture manifest pins exact raw and
published SHA values; archived program paths alone are normalized. Root owns
causal disposition, future qualification and frozen comprehensive acceptance.
