# Same-ID restore allocator discriminator — 2026-11-07

Reproduced isolated synthetic PostgreSQL 16 observations on unchanged application
`f0fac99a2fccee259c9a76eba0123058bf288d96`. This is an early M6 discriminator,
not a tenant restore implementation. [Observations](observations.json) retain
source/instrument/capture anchors and criterion outcomes.

| Actual composition | Ordinary → meaningful break → fresh restoration |
|---|---|
| Tenant A maintenance clock lock, decorated A/B canonical writers | A visibly waits on the maintenance backend while B commits. Removing A's actual clock decorator lets A commit before release and triggers `SID_CLOCK_COVERAGE_BOUNDARY`. Fresh decorated A waits again; B continues. |
| Default CACHE 1 shared entries allocator | B's previous maximum is5 and its next ordinal6. Operator-only rewind to A's maximum2 produces an actual canonical B write at3 and moves it inside B's natural order, triggering `SID_TENANT_MAX_REWINDS_SHARED_ALLOCATOR`. Prior B rows remain identical. Fresh no-rewind result is6 and last in natural order. |
| Separate private CACHE 8 research sequence | One backend retains2 after an operator floor100 and another backend allocates101. After both exact old backends close, a replacement on the same sequence OID allocates109 beyond the reserved108. This does not claim production uses CACHE 8. |

Seven result groups completed, including two mechanism-specific intended reds
and fresh restorations. Maximum concurrent instrument sessions was4; seven
instrument backend births were retained. An independent final client found no
prior database client remaining. The exact owned container, named volume and
child were absent; immediate parent inventory and baseline metadata matched.
Later root readback found the same inventory but changed endpoint/MAC metadata
on an existing baseline container. Docker events show its die/start after the
closure file was written. That later mismatch is retained, not normalized away.

The first native attempt stopped during setup with `Connection terminated
unexpectedly`, before instrument events. Its resources and baseline were restored;
it remains unaccepted. A fresh parent required TCP readiness, recorded both UNIX
and TCP probes, then completed the unchanged instrument. The exact original setup
cause remains read-derived; the successful rerun does not prove it.

Pure preparation checks:22 source checks,14 lifecycle controls and18 parent
identity/reference/metadata controls passed. They are separate from SQL results.
No application source changed and no comprehensive acceptance suite was repeated.

Same-ID identity-bearing tenant restore remains `OPEN/UNSUPPORTED`. A tenant-clock
fence alone misses lower-port writers; tenant-local `setval` must not reset a
shared allocator. Next: prototype allocator-preserving import under complete
writer/serving suspension and test concurrent B behavior, without adopting a
B outage or global fence by implication. Whole-deployment fresh-target restore
retains its separate accepted boundary. Human IdP-outage policy is unchanged.

Raw captures, exact synthetic resource identities and failure details remain in
the local lane handoff linked from release contents. No public global machine
inventory, credentials or user data are included here.
