# Admitted lifecycle operator: bounded source approval

**Fixed on a branch; independent source/accounting review approved.** Companion
`f098dcc368a80fd0fdeb25c72316523a5c6dd955` implements fixed `inspect`, `resume`
and `clear-operations` entry paths. Tests use archived core
`b06106eb8748e975cbe651f6ab51a2b664bd34a1`. The selected SOURCE literal remains
`d003`; no executable source/image pair was repinned. [Selected results and
provenance](summary.json) retain exact hashes; raw captures stay outside Git.

## Behavior and accounting

Reserved controlRecovery headroom alone did not authorize an operator process.
The new fresh-v2 ledger path durably charges one control lease before ticket,
child authentication or connection effects. It gates the fixed child until exact
custody is bound. It has no arbitrary SQL, role or module selector. Old ledgers
are not silently upgraded.

The child uses the actual core admission and restore interfaces. It binds role
and database names and object identities from bootstrap, permits one connection,
and preserves deadlines, clean-close proof and uncertain authentication/COMMIT
outcomes. An uncertain lease retains its charge. A zero census or forced stop
alone cannot grant graceful closure.

Diagnostic inspect does not construct a participant cohort, so a missing peer
remains diagnosable. Both mutations require current participant authority and
complete pins/census. Managed-session accounting includes only the controller's
durably issued/bound/unknown control tags. It distinguishes control occupancy
from workers and keeps observers separately charged.

## Executed source evidence

Owner archive-backed replay passes **49 companion checks and 64 affected core
checks**, with all **13 processes** returning zero. Independent review passes
**35 focused checks** across five processes. Role-OID and database-OID mutations
each fail one of eight controls; restoration passes all eight. Source controls
also cover debit ordering, crash/closure uncertainty, control tags, deadlines,
single-connect behavior, participant failures and private principal binding.
These overlapping counts are not additive.

This is source/protocol evidence using recording transports and actual modules.
It is not native PostgreSQL RLS or tenant-B continuity evidence. No runtime,
container, cloud, source/image pin, full campaign or final prcheck changed here.

## Open native boundary

The old raw-Pool capture/restore helpers are UNPLANNED under selected admission.
The new three-command entry cannot initiate an actual restore. An unclosed lease,
including UNKNOWN, consumes current controlRecovery1 and blocks another operator.
A concrete admitted fixture/drill is still required before native effects.

The same capability owner is comparing an explicitly seeded fixture with fixed
capture/restore end-to-end support. Any proposed fresh-profile second credit must
keep uncertainty charged, permit at most one current active operator, and define
version/compatibility semantics. It is not an approved ledger upgrade or runtime
change. Controlled placement move/rollback remains a separate later criterion.
The native collector's active-control-tag interoperability has its own owner.

Actual interrupted restore, all three command effects, RLS/authority/audit and
healthy-tenant continuity remain UNMEASURED. Native/full acceptance will use the
later coherent source/binding freeze. No current artifact was substituted.

Local custody and the concrete proposed acceptance seam are in
`externals/work/HANDOFF-restore-recovery-join-2026-11-12.md`.
Evidence identifiers: `lifecycle-operator-f098dcc-b06106e-source-20261113` and
`m7-lifecycle-operator-independent-review-20261113`.
