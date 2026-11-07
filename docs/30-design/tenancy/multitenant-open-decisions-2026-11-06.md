# Multitenant: the five decisions on the critical path (2026-11-06)

*What this is: a decision note for the maintainer (contributor-facing), written 2026-11-06
against alignment `main` `2efaa3a89` and the published candidate `83582e87` on draft PR #8898
(the owner/evaluator candidate `4cd95d06` is in its comprehensive campaign). Each item names
the mechanism, the trade-off, what operators or clients would notice, what is measured and
what is only read, and whether it is single- or multitenant. A decision taken here is
recorded as one row in `releases/cgm-remote-monitor-16.0.0/decisions.md`; this note then
points at it. One topic per section; recommendations are given because they were asked for.*

**Decided 2026-11-06 after this note was written:** items 2, 3 and 4 are decided as recommended and recorded as rows in decisions.md (section "Multitenant promotion bars"). Item 1 is decided differently from the recommendation: the clamping mode is **dropped** as a backward-compatibility break (decisions.md row of 2026-11-06); a tenant's api-secret must get 200 on its own tenant resource, and only backward-compatible solutions are wanted. The section below is kept as the record of the question as asked. Item 5's lifecycle packet is published: [owner session and issuer lifecycle decision packet](owner-lifecycle-decision-packet-2026-11-06.md).

**Closed today, for the record:** the per-write event's `stamp` is the transaction's final
clock floor (decisions.md, B7 section, row of 2026-11-06; lane head `e7baff74`). It is not
re-asked below.

---

## 1. Selected owner mode: what a root credential gets

**Mechanism (read-derived).** In the optional selected-reader mode the data listener resolves
every operation through the current-authority reader
(`lib/tenant-authorization/access-postgres.js:18`, `:51-59`): the caller must map to a
subject session, credential and grants in one SQL snapshot. A legacy root carrier (an
`api-secret` header, which is all pinned cgmsim can send) has no subject row; the reader's
sanitized failure path reports `ACCESS_AUTHORITY_UNAVAILABLE`, which the HTTP layer renders as
**503** (`access-postgres.js:36`, `:59`).

**Measured (reproduced, R63 on `87133959`).** oref0's three subject-token upload workflows
match the unselected reference in response summary, exit and stored values; an emptied
ceiling gives 401 with no effect on the next upload; cgmsim's root-secret upload gets 503
with no effect, where the unselected reference gives 200 and a write. Only summaries and
normalized stored values were compared; raw reply-body parity is unmeasured.

**Trade-off.** 503 says "the service is unavailable, retry", which is false and makes
retrying clients hammer a healthy site; 401 says "not authorised", which is true and
stable, but a client that treats 401 as a configuration error may stop uploading. Admitting
the root carrier under selected mode would reintroduce an all-domain credential inside the
mode whose purpose is a bounded catalogue.

**Who notices.** Multitenant only; nothing changes for single-tenant or for the unselected
default. An operator who selects the mode on a tenant whose uploader is cgmsim (or any
root-carrier client) sees that uploader fail until it can present a subject token.

**Options.** (a) Map "no subject for this carrier" to **401 with no effect**, keep activation
off; (b) keep 503 as observed; (c) admit root carriers in selected mode with the tenant's
full ceiling; (d) decide nothing until clients can carry subject tokens.

**Recommendation: (a).** Correct status, no retry storm, no widening of the catalogue; it
costs one mapping in the reader plus a re-run of the selected-client lab with the predicted
401. Activation stays off until (d)'s client work lands, which is a client-side change, not
a Nightscout one.

## 2. What M2 is held to: the roadmap cell or the dashboard's additions

**Mechanism (read-derived, promotion review of 2026-11-06).** The roadmap's M2 cell lists
five properties: tenant-local effective config and versioned writes; unknown tenant
refuses; a token for A fails on B by signature; no environment, root or key leakage;
separate owner, data and operator routes. The dashboard's T30-WIRING and T30-TENANT-ADMIN
rows add four more: human issuer and refresh, existing-grant clamping, tenant lifecycle
(provision, suspend, export, delete) and production trust for resolution. The roadmap
itself places issuer/refresh and delegation ceilings under M6.

**Measured.** Of the roadmap's five: four are measured (R33/R34 unknown-tenant refusal,
R48 signature refusal, R51 tenant-local config, R62 current grants); versioned writes are
on the integrated head but the slice `011802ba` is still marked "testing pending"; route
separation now has an actual two-listener run on `4cd95d06` (owner native 9/0/0: DATA
management 405, OWNER 200). Of the dashboard's four: all unmeasured, three recorded as
unimplemented (R53, R54); the lifecycle packet is being drafted by session `-8c`.

**Trade-off.** Holding M2 to the roadmap cell lets M2 promote once `011802ba` is re-measured
on the final head and the two-listener run is in a comprehensive campaign; M3 and M4 then
proceed on operator-provisioned credentials (as R48 already does). Holding M2 to the
dashboard list parks M2, M3, M4 and therefore M6 behind human-identity work that the
roadmap already assigned to M6.

**Who notices.** Multitenant only. Operators of the preview provision owner credentials by
hand either way until M6; the difference is only when the records may say "M2 promoted".

**Options.** (a) Roadmap cell is the M2 bar; the four additions are re-homed to M6 in the
dashboard and the status overlay; (b) the dashboard list is the bar; (c) split: clamping
and production trust stay in M2, issuer and lifecycle go to M6.

**Recommendation: (a).** It is what the roadmap says, it keeps the dependency chain
honest (M2 was never the identity milestone), and the lifecycle packet gives M6 its
criteria. Clamping of existing grants is already partly measured by R62's current-ceiling
enforcement and can be listed under M6 with the rest.

## 3. Numeric bounds and performance budgets

**Mechanism.** The only numeric limit in product code is the PostgreSQL sort-key cap,
`MAX_SORT_KEYS = 5` at `lib/storage/postgres-filter.js:34` (raised from 4 in R51; over the
cap the query is refused as unsupported, `:216`). Every other bound the roadmap names
(write latency, throughput, replay retention horizon, per-tenant evaluator cost, import
resource use) has no number in code and no approved threshold.

**Measured.** R65 (descriptive, four cohorts of 40 HTTP 201 requests, no errors): p95
18.2–23.1 ms, 303–339 successful requests/s, with the commit clock on or off. The clock
benchmark is opt-in and has been **pending in every corpus run**; R51 says sort-cost
performance is unmeasured; the durable contract's section 9 lists retention horizon and
budgets as UNMEASURED.

**Trade-off.** Approving thresholds now from four short runs would turn descriptive numbers
into pass gates with no steady-state or contention basis, and a wrong threshold either blocks
promotion on noise or waves through a regression. Deferring them leaves M1's "resource
bounds" and M6's "bounded resources" criteria open until a controlled window is run.

**Who notices.** Multitenant only; single-tenant Mongo is unaffected. The sort cap is the one
bound a client can hit today: a v3 query sorting on more than five keys is refused on PG
and accepted on Mongo.

**Options.** (a) Approve a threshold table now; (b) declare bounds deferred to batch C, let
M1 promote with "resource bounds: deferred, measured in C" stated, and commission one
controlled benchmark window (benchmark flag on, quiet machine, steady state with the
independent stored-count oracle R65 lacked); (c) refuse M1 until bounds are approved.

**Recommendation: (b).** Thresholds should come from a measurement designed to set them,
not from the first numbers available. The sort cap stays at 5 and is recorded as an
intentional PG-only difference in the compatibility page.

## 4. What "actual client execution" means for M4

**Mechanism (read-derived, M4 packet).** Pinned clients fall into feasibility classes:
A runs headless on Linux (cgmsim, oref0, nightscout-connect); B needs a vendor-cloud
stand-in that does not exist here (librelink-up); C is a JVM module inside an Android
project (AAPS NSClientV3 SDK, build cost unmeasured); D is an Android app (xDrip+, AAPS)
needing an emulator; E is iOS/watchOS (Loop, Trio, LoopFollow, LoopCaregiver, nightguard,
xDrip4iOS, DiaBLE) needing an Apple toolchain. The roadmap's M4 cell asks for v1 and v3
uploader/follower shapes "exercised on pinned versions" and distinguishes actual execution
from source-pattern replay.

**Measured.** Class A: 82/82 checks, 19 paired cells, 0 differences on `87133959` (R62) and
on `d89a44e1` (R60). Classes B–E: source-pattern replay only (R40, two 768-cell corpora),
plus the pinned AAPS 3.4.2.3 v1 socket sequence as a driven replay. No mobile binary has
been executed.

**Trade-off.** Promoting M4 on class A plus replay gives every mobile client only
read-derived compatibility evidence; iOS clients are the majority of real uploaders and
followers. An emulator lab (class D) is buildable on Linux at a cost nobody has measured;
class E needs Apple hardware or CI and a human.

**Who notices.** Multitenant preview operators whose users run iOS or Android clients: a
difference in retry, batch or refusal handling would surface in the field first. Single-tenant
is unaffected; the v1/v3 surface is unchanged there.

**Options.** (a) Promote M4 on class A execution plus replay for B–E, with the "no all-client
claim" line in the record; (b) add a class D emulator lab (xDrip+, AAPS) as a batch C item
before M6, not before M4; (c) require class D before M4; (d) require D and E before M4.

**Recommendation: (a) now, (b) in C.** M4 gates M6 through the chain, and the headless
clients already exercise every v1 and v3 shape the roadmap names. The emulator lab is
worth funding because it converts the largest read-derived block into measurement, but
it should not hold the chain.

## 5. Who owns the rest of batch C

**Mechanism.** The batching plan's section 5 now assigns two of the formerly unassigned items
to session `-8c`: the tenant export/import fidelity and deletion-with-recoverable-keys
proof (lane `codex/tenant-export-delete-20261106` off `83582e87`), and the owner
session/issuer lifecycle decision packet. Still **unassigned**: backup/restore on the
assembled tree, upgrade/rollback, resource and egress bounds, and the final-tree review.
The plan says C must prepare tools and populated fixtures in parallel with A and B, and
that no one may claim C implementation complete while an item is unassigned.

**Measured.** R62's populated PostgreSQL dump/restore lab (stopped-write synthetic
reference with explicit ACL recreation) is the only C-stage instrument that has run.
Nothing else in C has a lane, a worktree or a number.

**Trade-off.** Assigning now costs a worktree off `83582e87` and a source-only lane until a
focused run; waiting until A freezes keeps C serial behind A and B, which the plan was
written to avoid.

**Who notices.** Multitenant only. Operators of the preview have no backup, upgrade or
rollback procedure until this lands; it is the M6 gate most visible to someone running the
preview for real.

**Options.** (a) Open one new lane now for backup/restore and upgrade/rollback (they depend
only on the migration runner and R62's populated lab); bounds and final-tree review follow
item 3's benchmark window and the frozen C candidate; (b) hand the remainder to `-8c` after
export/delete lands; (c) hand it to the Codex root coordinator after the A freeze.

**Recommendation: (a).** It is the one C item that can start today without a decision
pending, and it is the one an operator would ask for first.

---

*Draft for maintainer review. Decisions taken go into decisions.md as rows; the queue and
dashboard move only after the row exists.*
