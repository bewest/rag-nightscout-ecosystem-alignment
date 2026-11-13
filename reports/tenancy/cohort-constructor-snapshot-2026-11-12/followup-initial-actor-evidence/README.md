# Retain admitted evidence across one observation — 2026-11-12

This is a new measurement leaf following the [original constructor repair](../README.md).
The earlier record and its captures remain unchanged.

Coordinator review identified a liveness hypothesis in source
`43b6b99d196e48eed2a228cdda9999b535eac7e9`: replacing the initially observed
backend map during the optional fresh observation can lose an actor that was
already admitted at the original SQL cut but has since closed.

The [focused reproduction](before.txt) fails with
`RESTORE_COHORT_UNKNOWN_BACKEND`: a later actor triggers the one permitted fresh
observation, while an initially admitted actor present in the SQL cut drains.
This is reproduced source-protocol behavior using a recording transport, not a
new native deployment result.

The narrow original-history follow-up
`5487e4b9cde3adffcd8b8150d4db3056703899d9` retains the original admitted tuples
and augments that evidence only when an original SQL actor's exact PID, role and
birth are proven in the fresh observation. Unrelated later actors are not added
as evidence for the original SQL cut. No role exemption, observation loop,
clinical mutation or protocol change is introduced.

The [affected checks](after.txt) pass 49 cases, including persistent unknown
actors, wrong births, changed pinned datastores, shared deadlines and closed or
released cohort pins. The new positive regression distinguishes the reported
liveness defect; the earlier refused-actor and ablation controls remain active.
The source storage implementation is unchanged by this follow-up, so no new
native constructor result is asserted here. Actual fresh paired shipping restore
and evaluator membership/effect acceptance remain pending.

Captured bytes are pinned by [SHA256SUMS](SHA256SUMS). The coordinator owns the
source join and final paired acceptance.
