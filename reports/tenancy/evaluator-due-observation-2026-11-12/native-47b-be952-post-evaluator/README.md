# Exactly-once due-aware post-evaluator-handoff observation

Reproduced 2026-11-12: PASS for the unchanged bounded collector/assessor on the
new exact due-aware runtime. One 21.346148286946118 s observation, three snapshots
10 s apart, 9/9 successful private RPCs. No retry, extension, write, work trigger,
cadence/plugin/threshold change or lifecycle command was performed by this lane.

The window was explicitly released after strict evaluator 2→3 qualification and
BEFORE controlled RT movement or its newer normal B input. The sole mutator
remained paused until capture finished; automatic evaluator/outbox work continued.
This is post-EVALUATOR-handoff input scope, not post-RT-move cadence, 120 s pilot,
capacity, clinical-output or changed-runtime recovery proof. The earlier once-only
cd462 UNMEASURED capture remains immutable, with its actual old B due UNKNOWN;
this differently scoped new observation does not explain or upgrade it.

## Exact identities

- Runtime core 47b43b6246ce7f94f1f1f0d01830495a78b28add.
- Deployment be95214a6cae427e1898b0ca6ce39825163ee291.
- Independently inspected image
  sha256:6138dbf5cec8dc7c4897e3c1d969868a37bb7fb3eb0af46feca7595fdbb3f361,
  with both exact source labels.
- FINALROOT instrument 4ddea55301c3d1f95faf25e15a80051bbb122e8b,
  content 157d7038c3b5a196e95c766b5777e6686bd1d59a37e3e5772ede4eea2daf6970,
  35 files. This is the final joined instrument, not the earlier 31-file lane hash.
- Executed helper c9e0370e8a3ca4d08dfd70b1290a36a0d57f33c34f3a5639a2e6d81b77b707e8.
- Actual fixture nonce 6ca2cfd8-d54d-4f11-b03a-e5f40aa1f1ab, read from RT's
  current metadata. Owned-pair artifact SHA
  c2193f4e935ec17c55ab3ceb84ccb85c1de1abc67cbf38acc81c1df428e7a194.

The driver verifies the final root head/file hashes before queries and imports
that exact tree. Each of the 3 exact evaluator container IDs/StartedAt and its
image is checked before/after; actual runtime UUID/ordinal/ownership/generation
are stable. Full identities are in native-observation.json. Only the NEW due
project was queried; retained earlier projects were not substitutes. The source
tenant file contains credentials, so only its two synthetic IDs were projected.

## Observed work and actual due fields

Every configured ID is read on EVERY evaluator. Each snapshot retains 6 rows,
including 4 foreign rows; every foreign work/failure counter stays unchanged and
every foreign dueAt/dueReason is explicitly null. Both admitted owners are ready,
code/alert null, with one unique owner per tenant.

| Owner | Acquisitions | Time completions | Legacy cycles | Failed completions | Generation |
|---|---|---|---|---|---|
| A/evaluator-2 |1→1|91→111|92→112|0→0|11→11|
| B/evaluator |1→1|91→111|92→112|0→0|15→15|

Both owners complete 20 actual time-only windows: 40 total, minimum 20 per owner,
zero failure delta. All owner samples report dueReason=slow:alarm-message.

| Snapshot | A dueAt | B dueAt | A/B milliseconds beyond their read end |
|---|---|---|---|
|0|1794498528252|1794498528252|129 /132|
|1|1794498538887|1794498538903|347 /363|
|2|1794498549672|1794498549677|625 /701|

Parent read-start, helper response-observation and parent read-end timestamps are
retained per instance/round. All owner due values are AFTER their read-end bound,
so these samples show future scheduled work, not quiet/null or already-past due.
No owner is classified as overdue in these three samples. This is a bracketed
point observation, not proof that no timer was ever late between samples or a
strict deadline SLO. The unchanged successful-work predicate, not future due by
itself, supplies the PASS.

18,076 actual encoded response bytes; 1.3136995257809758 s sum of parallel round
collection times and 3.81781214941293 s sum of per-instance exec durations. These
are different aggregations, not CPU measurements or causal latency subtraction.
All 14 compact columns retain actual due values. JSONL wire captures, compact
raw/deterministic gzip and exact read windows are retained; source/image/nonce/
instrument attribution is separate from counter assessment.

## Independent recomputation and refusal controls

FINALROOT 157d verifier independently recomputes the phase-v2 proof as PASS.
Raw SHA 11294efcb3f03e8b6d594c8466c2aea6423aacea3822842fad00eb7005657324;
deterministic gzip SHA cd6ab0ebc270d1d952e8cd871d2ff44d6c1cecab5c54dd3f3ee565018436308a.
Decoded gzip bytes equal the raw artifact.

Offline mutations of ACTUAL captured rows refuse frozen successful counters,
hidden failures, foreign work, runtime reset, missing foreign row, boolean due
and missing due column. Frozen work remains UNMEASURED despite moving future due
metadata. Restored complete proof returns PASS after each control. These are
capture-level controls, not live stopped-worker/restart experiments. No full
cell/capacity acceptance receipt was fabricated. Classification code and complete
per-row values/timing bounds are in classification.json.

The window was released immediately on completion. After this captured window,
RT reported an uncertain controlled-move failure and retained its journal/state
without retry. That separate outcome stays outside this PASS and keeps full
paired qualification under the coordinator's disposition. This leaf does not
clear it or fold the later B write/cadence into this input scope.

No core/instrument source edits, new service resources, old-state queries, cloud
or broad campaign occurred. Private originals remain 0600 under the lane's 0700
capture directory. Capture manifest pins raw/published hashes; only local path
prefixes in archived text/scripts are normalized. Numeric JSON/JSONL/gzip captures
are unchanged. Root owns integration, the later move disposition and final
comprehensive acceptance.
