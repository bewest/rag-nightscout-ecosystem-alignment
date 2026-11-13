# Original evaluator ownership-handoff effect-idempotency failure

Captured 2026-11-12; **reproduced** actual shipping criterion failure. This is an
unreleased multitenant candidate. The source is not a final accepted candidate.
No runtime source was patched, request replayed, member count reset or retained
project reused after the failure.

## Exact failed boundary

Core `195c932293f3abc648da8fbe4356bf7360acd002`, deployment
`f0f91f43784bb708385bcd4074cdfbd490fc096d`, fresh image
`sha256:63dfab59edb2355aa26814dfae01d88c7b4e6af7f22ad32c781cd1a8edfa22a0`.
[Verified image labels and selection](paired-identity.json): 2 API, 2 realtime,
2 logical shards, 3 fixed evaluator participants, default Vault server,
diagnostics off. Desired evaluator membership starts at 2 through the existing
private operator and changes to 3 in the committed clinical proof. The third
fixed participant is initially honestly idle.

[Stock/polling/WebSocket/API3 and actual restore](stock-restore.txt) passed with
four continuous B settings readers: 140 reads, zero errors. The existing
[test-only lower-port configuration fixture](settings-boundary-controls.txt)
then passed wrong-tenant, revoked-authority, excess-grant and restored-scope
controls. Only synthetic authority metadata and narrow role setup used fixture
SQL; settings values went through the actual owner-configuration/store fence.
This is not a shipping owner credential/bootstrap API claim.

The [clinical gate](clinical-gate-failed.txt) observed real initial alarms and
accepted durable requests, then current acquisition after the actual 2-to-3
membership change. It failed after about 8.8 seconds on its durable request-count
assertion. Its aggregate row-count expectation alone was too broad because B's
clinical reading deliberately changed; the typed classification below resolves
that ambiguity rather than treating every extra row as a duplicate.

## Typed durable classification

[Typed effects](typed-effects.json) exclude notification bodies and contain the
source's exact effect/title/message digests, request/origin, state/time,
config/clinical identity, kind, level, group and plugin.

* A has two **accepted normal** effects with identical source effect, title and
  message digests, created **4,438 ms** apart. A had no post-move clinical write.
* B's changed reading legitimately produces a changed payload. That new payload
  is then **accepted twice**, with identical effect/title/message digests,
  **543 ms** apart.
* These early rows are neither cancelled superseded requests nor control clears.
  Config and clinical identity remain the same. Ordinary subsequent repeats are
  about **60 seconds** apart and are separated from the initial clinical window.

The exact descriptor
`['producer-transition-v2', ['repeat', producer.output, null], 0]`, hashed by the
source notification contract, matches **both early duplicate origins exactly**:
[reproduced origin equality](origin-cause-match.json). The repeat condition uses
zero when the prior clock is missing; the recorded cause descriptor uses null.
This links the observed rows specifically to a repeat with no retained deadline.

Source reading suggests a transient unavailable evaluator model: reducer state
retains prior output and alarms but drops its repeat deadline while no armed
eligible cycle is available. Identical recovery can then enter the repeat path
immediately. That source transition requires the separate controlled native
warm-barrier discriminator before a repair is selected; this record does not
claim that instrument has run. A simple fresh-versus-retained actual-view content
comparison did not reproduce content-identity drift.

## Preserved state and next boundary

Desired/effective membership remains 3; A is active generation 2 and B active
generation 1. Assigned evaluators remain ready with successful time-only
completion advancing and failure count zero. The independent real-listener
collector observation is a separate scoped result and does not clear this
clinical gate. Scheduler, constructor and earlier identity qualifications remain
historical results for their exact boundaries.

The paid remote comprehensive run was cancelled before tests rather than held
while this defect is diagnosed. Root owns that cancellation/cleanup record and
any defect-register allocation. The new source lane starts from the same frozen
core; it must reproduce the unavailable-model gap with actual PostgreSQL and
preserve current-source, ownership, generation, RLS and ACK/clear/genuine-repeat
semantics. No new lock, index, failover policy or public authority is implied.

[Artifact digests](artifacts.sha256.json) cover the immutable captures. Private
credentials, notification bodies and raw role environment files are retained
only in owned local state, not in this report.
