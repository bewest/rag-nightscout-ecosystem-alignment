# Original evaluator scheduling reproduction — 2026-11-12

**Reproduced, repair pending.** Independently scheduled evaluator work can inherit
an expired operation-window context from the job that scheduled it. The strict
closed-parent guard then refuses that later work. Ordinary late application
work must continue to be refused; its guard is not the defect.

## Exact source and actual deployment observation

The synthetic prototype used core
`d50502bb6126bda2bb0af384569e1d95de114f2f`, deployment
`962fbdbe8617ed8abe63cad7039fde70f91fcbce`, and fresh paired image
`sha256:350c76b03f98df04810dd5c72d0f209e6a2b1f05402293a16aeaec9f8f00161d`.
Its fixed roster has three evaluator processes with desired membership two;
the third is idle. The membership-three transition was not issued.

A test-only lower-port fixture bootstrapped explicit synthetic configuration
authority, then used the actual source tenant-settings component and operation
window to enable the alarm plugin. It did not SQL-seed settings values and is
not a shipping owner/operator bootstrap API. Actual tenant DATA writes were
accepted, but the [initial clinical-alarm oracle](capture/actual-alarm-oracle.txt)
timed out before observing the expected alarm fanout. Later private inspection
reported `EVALUATOR_WINDOW_REFUSED` and `EVALUATOR_CONSUMER_REFUSED` despite
healthy membership.

The [configuration/notification snapshot](capture/configuration-and-cancellation.txt)
records both tenant windows active, settings version two with the plugin enabled,
policy generation one, and notification request configuration identities equal
to their current producer identities. It observed four cancelled ordinary
requests and two accepted clear requests. This rules out a mismatched persisted
configuration identity in that snapshot. It does **not** attribute every
cancellation solely to asynchronous context propagation: stale clinical-model
withdrawal and control clears remain valid safety behavior.

The [basic native window probe](capture/native-basic-window.txt) admitted
`window.run` and `SELECT 1` for both tenants. The owned PostgreSQL log inspection
found no SQL error. The investigation did not weaken admission, change membership
or retry the clinical side-effect probe.

## Isolated cause and counterfactual

`lib/tenant-lifecycle/operation-window.js` rejects an inherited scope when its
parent is no longer active. The unchanged guard file at the diagnosed source has
SHA-256 `807cb6417530060dd8811a5f38cfb32503ac75b6aea8241003818c53a83ed8df`.

`lib/server/serve/evaluator-runtime.js` schedules its due callback inside the
clinical `window.run` body. Node propagates that body's asynchronous local
context into the timer. When the callback later enters `window.run`, the parent
has closed. The evaluator masks that typed refusal as
`EVALUATOR_WINDOW_REFUSED`.

| discriminator | reproduced result |
|---|---|
| [Actual source runtime/window over the recording PG protocol](capture/source-protocol.txt) | One successful initial body, then `EVALUATOR_WINDOW_REFUSED`; underlying `LIFECYCLE_WINDOW_SCOPE_INVALID` |
| [Actual PostgreSQL/window/runtime](capture/native-scheduler.txt) | Same one-cycle refusal and typed cause with a `SELECT 1` component; no clinical mutation |
| [Test-owned boot resource around only the due callback](capture/native-neutral-timer-control.txt) | Four cycles, no error; unchanged window guard still refuses an ordinary late application callback, whose body does not execute |

The [recording-port instrument](instrument/source-protocol-repro.cjs) selects the
exact source through `NS_CORE_WORKTREE`. The [native instrument](instrument/native-window-control.cjs)
reads a separately supplied private capability file; no capability values are
captured here. Its two native modes were executed against the same paired image
and actual owned PostgreSQL. The native window pool had a maximum of two clients.

This establishes the due-timer mechanism independently of tenant configuration
changes or notification cancellation. The neutral timer is a diagnostic
counterfactual, **not a product repair**. Revision-delivery queueing and repeat
rescheduling need their own controls before selecting the complete repair.

## Boundaries and next criterion

These controls exercise source scheduling and actual database/window admission,
with a synthetic component. They do not claim the clinical evaluator algorithm,
all notification effects, one-client deadlock freedom, successful membership
handoff, capacity, release or production acceptance. The actual clinical probe's
failure remains a failure.

The initial parent-check pool-deadlock hypothesis was refuted by source reading:
current evaluator `check()` has no outer `window.run`. A future trusted scheduling
boundary must nevertheless prove one-client revision/intent/handoff completion
and legitimate nested-await reuse, preserve fresh pause/suspend/restore admission,
and retain strict refusal of ordinary late request/provider callbacks. It must
be owned at boot before request, tenant or readiness authority exists, with no
per-tenant asynchronous resource and no generic public detach operation.

The coordinator owns the defect register fact, source integration and any new
freeze. The eventual repair will have a separate immutable measurement leaf;
this original record and captures remain unchanged. All captured files and
instruments are pinned by [SHA256SUMS](SHA256SUMS).
