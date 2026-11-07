# Allocator-preserving tenant restore: bounded SQL feasibility

*Reproduced synthetic programme evidence, 2026-11-07. Application source
`f0fac99a2fccee259c9a76eba0123058bf288d96`, tree
`09dd7baf52d51f2725e7cac732fabd3f8280b482`. PostgreSQL 16.15.
[Observations](observations.json), [instrument](instrument.cjs),
[closure](closure.json) and [prior attempts](prior-attempts.json) retain this
bounded run. This report does not admit product tenant restore or promote M6.*

## Question and result

Can a same-deployment tenant A restore keep original internal insertion values
without touching the shared allocator, while tenant B continues writing?
**Yes in this controlled entries SQL fixture.** A was deliberately quiescent;
B's actual application lower-port writes ran before, inside and after A's restore
transaction. No shared write pause or sequence-maintenance statement was used.

The instrument imports the exact application's entries catalogue, restricted
NOBYPASSRLS connection/tenant binding and lower entries writer. The research
restore uses explicit SQL over an operator connection. It does not invoke or
bypass the product lifecycle importer: that importer's identity-bearing refusal
remains unchanged. Fixtures use synthetic string IDs and documents.

| Experiment | Physical observation |
|---|---|
| Original values / ordinary and fresh restored run | A restores ordinals 1,3; its next canonical insertion receives 6. B retains old rows at 2,4, commits at 5 during restore and at 7 afterward. All pre-restore B rows compare exactly by raw tenant/document/type/ordinal. |
| Allocator preservation | Live value 4 becomes 5 solely because B inserts during restore. Explicit A restoration consumes no sequence value; no `setval` or `ALTER SEQUENCE` runs. |
| Unsafe artifact / wrong binding | Artifact floor above the covered live floor and wrong sequence OID refuse before row/sequence effects; B remains unchanged. Admission is restricted to positive increment-one, noncycling CACHE 1 behavior and the same table/sequence binding. |
| Interruption | Injected failure after A's first insert rolls A back completely; independent B's committed insertion remains. |
| Meaningful floor-control red | Removing the floor refusal lets new A ordinal 5 sort before restored 1001,1003. The physical numeric-order oracle detects the intended misordering. |
| Meaningful foreign-preservation red | Deliberate B document corruption fails the independent exact pre-existing-B comparator. |
| Separate logical-restore proposal | Artifact A ordinals 1001,1003 become fresh internal values 5,7 by replaying sorted rows and omitting the identity column; documents/relative order remain equal and B continues at 6. Public record IDs remain unchanged. Original raw ordinals deliberately differ; this is not physical artifact fidelity. |

## Failed attempts and restoration

The first attempt stopped before fixture data because the instrument omitted
explicit multitenant mode. The second passed early ordinary/refusal/interruption
cells but its control oracle sorted a text output alias lexically. Qualifying the
physical numeric column repaired the oracle; the final complete run reached the
intended red and a fresh ordinary restoration. Both failed captures and their
source hashes are retained. No failed attempt is relabelled successful.

The final instrument SHA256 is
`6c4edb81148604bb38d3d06eb39805bdc10e33cffe249601f2793cc8f896855b`.
The finite parent hash is in closure; the parent and frozen instrument are
retained in the private capture. Root independently verified both hashes and
current exact owned resource absence. The parent compared complete container and
volume inventories before/after; it removed only its labelled container/volume.
Original failed and final captures retain their own teardown results.

## Limits and next boundary

This is entries SQL feasibility under controlled A fixture quiescence, not a
complete writer/serving/authority/cache fence. It does not exercise public HTTP,
mobile clients, populated history timestamps/cursors, full catalogue, secrets,
retained allocator caches, production recovery or performance. The observed tiny
fixture duration is not a recovery-time budget. B's live sequence naturally
advances; preserving B means preserving its committed rows and supported ordering,
not freezing the shared sequence value.

The separate fresh-internal-ordinal result suggests a logical tenant restore
contract worth reviewing against actual natural-order consumers. It does not
weaken the exact physical backup comparator or authorize changing whole-deployment
recovery. A still needs exclusive restore authority and derived-state/cursor
recovery before either path can serve users.

## Reproduction boundary

The instrument expects `APP_SOURCE` to be the exact archived app with matching
installed `pg` dependencies; `PROBE_ADMIN`/`PROBE_APP` are separate connections to
an owned disposable PostgreSQL fixture, `PROBE_PASSWORD` its synthetic role secret,
`SOURCE_HEAD` the asserted source and `PROBE_OUT` a new capture path. These are
private environment values and must never be committed. It creates schemas and
one synthetic role: never point it at a shared or real deployment. The original
owned finite parent supplies these capabilities and performs exact teardown;
its machine-specific captures remain in the local lane handoff.
