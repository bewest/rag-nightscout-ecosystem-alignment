# Operation lifetime and cache-parameter proof — 2026-11-07

Early architectural proof on local **unpublished** application prototype
`6a245c09f652f020dc07f774aa0f2fe8e22e973f`, tree
`3da8cde2491ad21d35e25a47322f14a803af1c8d`. The source is not ready for admission:
no CLI/configuration parser selects the optional lifetime adapter, and complete
schema/privilege/census/operator control is unfinished. Same-ID identity-bearing
import retains its existing pre-effect `UNSUPPORTED` refusal.
[Observations](observations.json) retain each capture's real result and anchors.

## Reproduced scope

The focused source batch passes 95 tests. The optional prototype covers actual
lower PostgreSQL transaction entry, HTTP response finish, socket acknowledgement/
fanout/alarm, evaluator cycles and notification producer/retry/adapter handoff.
Most consumer checks use protocol doubles; they are not native role acceptance.
The session lock is acquired before BEGIN so snapshot admission cannot precede it.
A durable operation record commits before a serving callback and finishes after
its lifetime; transport loss leaves an unresolved record. Mere lock disappearance
cannot establish that a callback or provider effect completed.

The first native fixture omitted tenant_id in its raw INSERT; RLS correctly
refused 42501. No complete group/control passed. Its false acceptance is retained.
A fresh fixture-only correction kept the application source unchanged.

The second native run completed seven component groups:

| Actual component | Ordinary / meaningful break / fresh restoration |
|---|---|
| Lower connection | An open A transaction prevents A's exclusive maintenance lock while canonical B writes proceed. Omitting the optional lower window physically permits exclusion while A's body is open, triggering `WINDOW_LOWER_BYPASS`. A fresh gated transaction restores the drain property. |
| Tenant HTTP | Actual createTenantApp response lifetime holds the window and pending record through response finish. Omitting the window permits exclusion before the held response finishes, triggering `WINDOW_HTTP_COVERAGE_BYPASS`. Fresh gated composition restores the property. |
| Lease connection loss | Terminating the exact lease backend permits exclusive lock acquisition while the HTTP body remains open; its durable pending count remains 1. The pending-operation check refuses, whereas lock-absence-only admission would accept. No orphan timeout, clearance or operator override is selected. |

That run then **failed** its cache prediction; its overall instrument/driver result
remains false. The completed groups are retained constituent observations, not a
successful eight-group campaign or complete tenant suspension.

## Cache mismatch and narrow diagnostic

On actual PostgreSQL 16.15 with pg 8.23.1, a separate two-profile diagnostic recorded
backend births, values, sequence OID and relfilenode **before verdict**. Explicit
awaited queries run in order without an encompassing transaction.

- With CACHE 8 and setval alone, the retained backend returns 2 after a newer backend
  receives 101 following floor 100. The same backend/OID/relfilenode are retained.
- Adding ALTER SEQUENCE CACHE 1 retains the backend and sequence OID but changes
  relfilenode; that backend next returns109. The earlier predicted 2 was wrong for
  this parameter-change profile. R74's setval-only result remains distinct.

**Read-derived mechanism:** PostgreSQL's [REL_16_15 sequence.c](https://github.com/postgres/postgres/blob/REL_16_15/src/backend/commands/sequence.c#L1107)
discards unissued cached values on a changed relation file; parameter changes
including CACHE request a transactional rewrite. This matches the reproduced
identity observations. The [ALTER SEQUENCE notes](https://www.postgresql.org/docs/16/sql-altersequence.html#SQL-ALTERSEQUENCE-NOTES)
and the actual pinned source/measurement must be read with that distinction.
This is not a proposal to use ALTER as a restore fence: it can block concurrent
sequence operations, and no B outage/global allocator fence is adopted.

All three captures removed their exact owned container, volume and child;
immediate baseline inventories/metadata matched, and root re-read exact absence.
The diagnostic's independent final client found zero earlier database clients.
Original failed captures remain false and immutable. Raw machine inventories,
credentials and local resource identifiers remain in the local handoff.

## Open integration boundary

Current CACHE 1 and a covered counter alone are not complete connection/history
admission. Unknown old allocator authority or unproved conditions must refuse
before writes. Supported history, effective floor, above-floor refusal, exact
artifact import/rollback and current B comparisons remain unmeasured here.

Root next joins durable phase/claim/operator control, exact metadata/role/census
and **actual CLI cohort** consumption. Unknown/unconfigured lower or raw SQL
writers are not covered merely by constructing an optional adapter. No fixture
quiescence or marker alone is a production fence. Comprehensive full/browser/
enabled-corpus acceptance and final prcheck are deferred until that coherent
candidate is frozen; source tests are not a substitute.

HTTP callback completion, SQL lease loss and external provider/device effect
completion remain distinct. The prototype cannot cancel an already accepted
external effect and inherits R73's ambiguous-delivery limits. Human IdP-outage
policy, default/production enablement and M6 promotion are unchanged.
