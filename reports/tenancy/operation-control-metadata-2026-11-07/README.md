# Operation-control metadata — 2026-11-07

**Reproduced by the acceptance lead:** the bounded PostgreSQL diagnostic passed on application `facc5792c10bcf22d5dbd2d34de4e4498b0638f3`, tree `9d20d7163f9f4a97998b1b52e7f611469907e8fb`. This projection independently read the retained capture and verified every indexed capture file. It did not rerun the diagnostic. Portable source, instrument and capture-index hashes are in [summary.json](summary.json).

The actual migration runner applied the four-entry lifecycle control catalogue. On PostgreSQL **16.15** (`server_version_num` **160015**), all **10 named completion groups** passed. These are instrument groups, not a full application test-suite total.

| Capability | Reproduced result |
|---|---|
| Native control readiness | The lower, lifetime and private maintenance profiles each admitted the actual control schema and grants. |
| Tenant authority RLS | The maintenance profile saw its active authority for tenant A, no authority for B, and could not update its own authority. |
| Meaningful negative control | Adding column `UPDATE(active)` permission on restore authority made maintenance readiness refuse with `LIFECYCLE_WINDOW_SCHEMA_UNSAFE`. Revoking it restored fresh readiness. |
| Backend-birth visibility | The maintenance connection initially saw a NULL birth for a different-role peer. An isolated `pg_read_all_stats` grant made that peer's birth visible and exactly equal to the peer's own observation. |
| Connection and egress bounds | Peak child database concurrency was **2**, with **16** successful child connections and **0** forbidden egress attempts. An independent final verifier observed no prior child database backends. |
| Physical release | Parent proof, overall verdict and runtime release passed. Independent acceptance-lead readback confirmed owned container/volume and child/group/descendant absence, exact inventory restoration and unchanged selected baseline metadata. No parent errors, cleanup errors or unknown residues remained. |

The container's **256 MiB / 1 CPU** bounds were enforced and inspected. Node **v22.23.4** and the exact PostgreSQL server version were asserted by the pinned instrument. The single-use runtime slot is closed.

The visibility result identifies a real prerequisite for cross-role backend observation. The statistics grant was a synthetic diagnostic intervention; this result does not adopt a production operator grant recipe. NULL or unknown backend identity cannot be treated as evidence that a cohort is complete.

This evidence establishes only the source-bound control migration/readiness, authority RLS and backend-visibility behavior measured above. It does not establish an actual serving cohort or census, controller execution, drain or orphan recovery, logical restore, client convergence, separate-process or multi-node coordination, or catalogue shadowing resistance. It is not joined application acceptance or complete M6, and enables no default, production grant, real identity/data or provider delivery. Earlier source-attributed failures remain separate evidence.

The public projection contains only synthetic capability results and technical source/instrument attribution. Raw role and resource identities, process IDs, backend timestamps, machine paths, inventories, credentials and connection URLs are excluded.
