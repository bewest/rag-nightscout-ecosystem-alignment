# Datastore recovery and admission: source checkpoint

**Reproduced, fixed on a branch.** Core candidate
`f1d21ef0d289d1e750cf771406a361ae67b9945d` is an ordinary join of admission
`d0036890d0623ae79f14bfa71e7226c0fa122a29` and datastore recovery
`0ec1a6384fa290b7ba2bad181ce883498869622a`. No application dev merge or release
is claimed. Paused source worktrees and original captures are unchanged.

The join preserves admitted pool construction, option descriptors, error
listeners, cold-ticket cancellation and uncertain physical credits. It resolves
three textual conflicts in pool membership, server composition and startup.

## Reproduced integration defects and repairs

| Finding | Repair and control |
|---|---|
| Recovery's no-warm invalidation left an already queued warm runnable; an older callback could queue another warm after later invalidation. | Remove queued work and fence deferred rewarm by generation. Controls fail when queue removal or the generation fence is removed. Already running I/O remains owned. |
| A timed-out recovery could invoke cache invalidation after supervisor shutdown; retry could overlap unresolved physical work. | Cancel adoption authority, retain physical-step custody, prevent overlap, and recheck cancellation before and after invalidation and before identity adoption. Expired-authority, cancelled-adoption and overlapping-step controls fail independently. |
| Waiting indefinitely for recovery before closing its owning pools could deadlock shutdown; pretending it drained could grant a false retirement acknowledgement. | Supervisor shutdown refuses unconfirmed drain while server shutdown still closes owned resources. Uncertainty prevents graceful retirement; late completion does not turn failure into an ACK. The false-graceful-retirement control fails. |

A selected admission plan belongs to an exact datastore resource epoch. Changed
postmaster recovery refuses `REBIND_REQUIRED` before dropping cached state or
adopting identity. It requires explicit controller/operator worker and resource
disposition; it does not forgive uncertain transport credits. Removing this
refusal fails the seventh control. Unselected same-store recovery remains a
separate behavior. No automatic selected-epoch rebinding is implemented.

## Executed evidence and limits

The implementation owner ran **211 affected checks**, with **10 opt-in PostgreSQL
checks pending**. Seven semantic mutations failed at the intended assertions;
the restored affected run returned zero. Parent review independently ran **97**
recovery, startup, admission and cohort checks, exit zero, and matched all four
mutated components' committed hashes to the tested/restored receipt. These
counts overlap and must not be added. Lint, tier registration and whitespace
checks passed; five existing fixture warnings remain in the lint capture.

No database, container, cloud or full native deployment was started for this
checkpoint. Actual database recovery, selected-mode restart disposition,
clinical/freshness behavior and capacity remain UNMEASURED. Full/browser/enabled
corpus acceptance and final prcheck belong to the later coherent frozen batch;
they were not run for this leaf. Independent source review remains the next gate.
Do not substitute this candidate into an existing frozen image or paid run.

Local custody and exact commands are in
`externals/work/HANDOFF-recovery-admission-join-2026-11-12.md` in the main checkout.
Primary controls remain under `/tmp/recovery-admission-controls-20261112/`;
parent replay is `/tmp/recovery-admission-parent-focused-20261112.log`.
Raw captures are intentionally outside Git. The integration coordinator owns
review/freeze; the sole cloud owner retains all remote test custody.
