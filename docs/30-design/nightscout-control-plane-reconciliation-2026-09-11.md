# Reconciling the agentic control plane RFC with what the corpus measured

Date: 2026-09-11. Status: draft for discussion. Tenth in the series, and the
first one addressed **to cgm-remote-monitor's own `docs/proposals/` set**
rather than to a controller.

> **The RFC is not being rewritten here.** It was drafted 2026-01-01. The
> census that could check it ran on snapshots dated 2026-04-01 and
> 2026-04-26. Nothing in the RFC was wrong to assume at the time it was
> written; several things can now be *checked*, and a few of them come back
> different. This document is the checking, plus the edits that follow from
> it.

---

## TL;DR

| | |
|---|---|
| **Seven claims the corpus confirms** | Including two the RFC treats as open questions that already have answers on the wire: an idempotency key (`syncIdentifier`, 306,741 treatments) and a human/automation flag (`automatic`, 300,228 treatments) |
| **Five things the corpus corrects** | The Trio discriminator never fires; instance identity is taken from the least reliable field; `OverrideInstance.effectiveEffects` would be empty for 19% of observed active overrides; Loop has no `suggested` at all |
| **Two simplifications with arithmetic behind them** | The ten new collections would *add* 2,880 requests/day per client under the same model that measured the existing fan-out — and the RFC already contains the endpoint that removes the need for them |
| **One thing to do before any of it** | `integration-questionnaire.md` is twenty questions and fourteen empty tables. Roughly half can be pre-filled from measurement and source. An implementer corrects a wrong table far faster than they fill an empty one |

**The single most useful finding for the RFC's own case:** `CapabilitySnapshot.effectiveLimits.maxIOB`
and `PolicyComposition.effectiveParameters.maxBasalAllowed` are the objects that
would close the most-cited replay gap in this entire series — `max_iob` is
**recorded by no oref0 derivative anywhere in Nightscout**, and a real replay
tool has to assume it. The RFC proposes the right object and never says that
is what it is for.

---

## 1. Why this document exists

The roadmap listed "how much of `docs/proposals/` is live" as an open
question and said reconciling against it was "arguably ahead of Phase 1,
since duplicating an existing RFC is the specific failure this work is
supposed to prevent." This is that reconciliation.

Three things make it worth doing as edits rather than as a competing
proposal:

1. **The overlap is near-total in scope and near-zero in evidence.** The RFC
   and this series propose the same objects for the same reasons. The RFC
   argues from design; this series argues from 1.97 million documents. They
   are complements, not rivals.
2. **Two efforts independently reached the same structural discriminator.**
   `bridge-rules.md` detects controllers with `if (devicestatus.loop)`,
   `if (devicestatus.openaps)`. So does `specs/sync/registrations/`. That is
   the strongest evidence in either tree that the approach is right.
3. **The RFC's weakest sections are exactly the ones a corpus can fix**, and
   its strongest sections are ones this series never attempted — delegation,
   agent authority, remote commands.

---

## 2. What the measurements confirm

Each row is reproducible from `reports/schema-census/`.

| RFC claim | Measured | Verdict |
|---|---|---|
| "Overrides buried in devicestatus" | `override.active` on **597,335** devicestatus documents (85%, 10 sites); `override.name`, `.duration`, `.multiplier`, `.currentCorrectionRange` present only when one is running | **Confirmed.** The override *is* a devicestatus field, exactly as described |
| Structural detection in `bridge-rules.md` | `loop`, `openaps`, `pump`, `uploader`, `override` are the observed top-level `devicestatus` objects. Nothing else discriminates | **Confirmed, and independently arrived at** |
| "Controller version" in `ControllerKindDefinition` | `loop.version` on **597,335** documents (85%, 10 sites); `openaps.version` on **73,898** (1 site) | **Already published.** No controller change needed for this field |
| `EventEnvelope.idempotencyKey` | `treatments.syncIdentifier` on **306,741** documents (83%, 10 sites) | **Already on the wire under another name.** See §4.3 |
| `issuerType: human \| controller` | `treatments.automatic`, boolean, on **300,228** documents (81%, 10 sites) | **Already on the wire.** The base case of the authority hierarchy is observable today |
| `DeliveryObservation.pumpResponse.acked` | `loop.enacted.received`, boolean, **405,228** documents (58%, 10 sites); `openaps.enacted.received`, **73,834** (1 site) | **Already published as a boolean.** The ACK exists; the error *code* does not — `loop.failureReason` is a string on only **16,550** documents (2.4%) |
| "No 'effective policy' view" | `max_iob` is recorded by **no oref0 derivative anywhere**; `oref-digital-twin` lists it in `REQUIRED_SETTINGS` and must assume it | **Confirmed, and it is the strongest argument the RFC has.** See §3.1 |

**What this changes about the RFC's ask.** Four of the fields it proposes as
new already exist in production data. The work is not to invent them; it is
to **describe the ones that exist and name the ones that do not** — which is
what a controller description is for.

## 3. What the measurements correct

### 3.1 The RFC understates its own best argument

`agent-control-plane-rfc.md` motivates `PolicyComposition` and
`CapabilitySnapshot` as prerequisites for *agents*. They are also, and more
immediately, the fix for a measured failure that has nothing to do with
agents:

| Object and field | What it would close |
|---|---|
| `CapabilitySnapshot.effectiveLimits.maxIOB` | `profile.maxIob` — **absent from every oref0 derivative in the corpus.** A replay must assume it |
| `PolicyComposition.effectiveParameters.maxBasalAllowed` | `profile.maxBasal` — **partial.** Loop records `loopSettings.maximumBasalRatePerHour` (10 sites); AAPS and Trio record no equivalent |
| `PolicyComposition.effectiveParameters.effectiveISF`/`effectiveCR` | Reconstructing these from profile plus overrides is where replay silently diverges from what the controller used |

Replay completeness is **20% for Loop and 50% for the oref0 family**. The RFC
would move both, and it does not claim the credit.

**Recommended edit:** add a motivation item — *"Safety limits and effective
parameters are not recoverable"* — with these numbers, ahead of the agent
motivation. It makes the RFC adoptable by people who do not want agents.

### 3.2 The Trio discriminator never fires

```javascript
// bridge-rules.md:68
if (devicestatus.trio) return 'trio';
```

**No document in the corpus carries a top-level `trio` key**, and Trio's own
wire model agrees: `Trio/Sources/Models/NightscoutStatus.swift` declares
`openaps`, `suggested`, `enacted` — no `trio`. Two independent confirmations.

The honest version is worse than a typo, and it is **our limit too**: Trio is
an oref derivative and writes under `openaps`, so
`specs/sync/registrations/trio.yaml` and `androidaps.yaml` both discriminate
on `openaps` and **cannot be told apart at the top level either**.

**Recommended edit, both trees:** delete the `trio` branch; state that oref
derivatives are not distinguishable by top-level key and that separating them
needs a second-order signal (`openaps.version` string, or an explicit
declaration). Do not invent one silently.

### 3.3 Instance identity should not come from the device string

```javascript
// bridge-rules.md:470
controllerInstanceId: devicestatus.device,
// bridge-rules.md:171
issuerId: devicestatus.device || 'unknown'
```

`device` is present on all 702,254 documents, and it is the free-text field
this series spent the most effort de-identifying. It is also unreliable in a
way that matters here: **one site's device strings read like a controller
while its treatments showed no automated dosing at all.**

Using it as instance identity makes liveness inherit that unreliability, and
it makes `ControllerInstanceRegistration.instanceId` — the RFC's own answer
to liveness — a rename of a string nobody controls.

**Recommended edit:** `instanceId` is issued by the hub on registration, or
supplied by the controller. `device` may be *recorded* on the instance as an
observed alias; it must not *be* the identity. Bridge-synthesized events for
an unregistered controller get a synthetic instance id, not the device
string.

### 3.4 `OverrideInstance.effectiveEffects` will be empty 19% of the time

Bridge mode synthesizes `OverrideInstance` from devicestatus. Measured over
the **64,674** devicestatus snapshots with an active override:

| | Count | Share |
|---|---|---|
| Effect and motivation both present | 49,990 | 77.3% |
| Effect only (no label) | 2,411 | 3.7% |
| **Motivation only — a name, no effect** | **12,202** | **18.9%** |
| Neither | 71 | 0.1% |

The same shape appears on treatments: of 3,415 temporary effects, **481
carry a label and no effect at all**.

So a bridged `OverrideInstance` will carry a `reason` and an empty
`effectiveEffects` for roughly one in five active overrides. That is not a
bridge bug — the data is not there — but a `PolicyComposition` computed from
it would be **silently wrong rather than visibly incomplete**, which is the
worse failure for a replay or an agent.

**Recommended edit:** bridge rules must mark synthesized effects with a
confidence or completeness flag, and `PolicyComposition` must be able to say
"an override is active whose effects are unknown." The RFC already has the
vocabulary — `DeliveryObservation.confidence: confirmed | inferred |
reported` — it just is not applied to overrides.

### 3.5 Loop has no `suggested`, so question C7 has no single answer

`integration-questionnaire.md` C7 asks all three controllers to fill in one
table for suggested / requested / confirmed. The corpus says the three states
live in different places per controller:

| State | Loop | oref0 family (Trio, AAPS) |
|---|---|---|
| Suggested | `loop.automaticDoseRecommendation` — **183,049 docs (26%, 10 sites)** | `openaps.suggested` — **73,898 docs (1 site)** |
| Requested | not separately published | not separately published |
| Confirmed | `loop.enacted` + `loop.enacted.received` (bool) — **405,228 (58%)** | `openaps.enacted` + `.received` (bool) — **73,834** |

Neither publishes *requested* as distinct from *confirmed*. Both publish a
boolean ACK and neither publishes an error code except Loop's sparse
`failureReason` (2.4%).

**Recommended edit:** replace C7's empty table with this one, marked
*"pre-filled from corpus; correct what is wrong"*, and add the real question
underneath, which is narrower and answerable: **is there a point in your code
where a command has been sent and not yet acknowledged, and can you emit
it?**

---

## 4. Two simplifications, with arithmetic

### 4.1 The ten new collections work against the RFC's own goal

`agent-control-plane-rfc.md`'s API table has eleven rows: **ten new
collections**, eight of them "CRUD + history" and two "Read + history" —
and, in the eleventh row, a single `GET /api/v3/events?cursor=` stream that
carries everything those ten would carry.

Under the model in `reports/schema-census/sync-cost.json` (distinct endpoints
per 5-minute cycle × 288 cycles/day, a source-derived upper bound, not a
packet capture):

| | Endpoints/cycle | Requests/day |
|---|---|---|
| AndroidAPS today | 20 | 5,760 |
| **+ one `history/{from}` read per new collection** | **30** | **8,640** (+50%) |
| The event stream alone | 1 | 288 |
| A batched contract (this series, §3.2) | 2 | 576 |

The measured finding that motivates the whole sync section of this series is
that **the client using v3 correctly has the worst fan-out, because v3 gives
it a delta per collection.** Ten more collections is ten more deltas, and
that is before any write endpoint.

**Recommended edit:** make `/events` the **only** read path in Phase 1. Keep
the collections as *projections* — materialized views a UI or a legacy client
can read — not as a sync surface. Move "New Collections (API v3)" from the
Phase 1 deliverables to a later phase, and mark the table "projection
endpoints, not sync endpoints."

This costs the RFC nothing: the event stream is already its Phase 1
deliverable.

### 4.2 One cursor, not two

`conflict-resolution.md` proposes a global monotonic cursor
(`eventCursors` collection, `findOneAndUpdate` with `$inc`) alongside
optimistic locking on `srvModified`. v3 already ships `srvModified` per
document and `GET /lastModified` across collections. This series' §3.2
proposes an opaque server watermark deliberately so the implementation can
change without a client release.

Three cursor-ish things in two trees is one too many.

**Recommended edit:** state explicitly that the event cursor **is** the sync
watermark, exposed opaquely, and that `srvModified` is its current
implementation. Whether it stays a `srvModified` scan or becomes a counter or
a replication offset is then an internal decision rather than a protocol one.

**Unmeasured concern worth writing down rather than acting on:** a single
`{_id: 'global'}` counter document incremented on every event write is a
write-serialization point, and multi-writer is the case the RFC exists to
serve. Nobody has measured this, here or upstream. It belongs in the RFC's
own open-questions list, not in a design decision.

### 4.3 Do not add an issuer field where two already exist

The RFC's `IssuerIdentity` is the right model. But `treatments.enteredBy`
(100% of documents) and `treatments.automatic` (81%, boolean, 10 sites)
already carry, badly, exactly the distinction the base of the authority
hierarchy needs.

**Recommended edit:** bridge rules should derive `issuerType` from
`automatic` (true → `controller`, false/absent → `human`) and record
`enteredBy` as an observed issuer *label*, not an identity. Add both to the
questionnaire's D-section as pre-filled rows. New controllers emit
`IssuerIdentity` natively; existing ones get a correct-by-default bridge for
free.

`enteredBy` is free text and is treated as an identifying field by
`specs/sync/sensitivity.yaml`. It must not be propagated into any served
catalogue, event payload shown to a third party, or audit record that leaves
the site.

---

## 5. What is missing from both trees

| Gap | Neither document has it |
|---|---|
| **The settings resource** | The RFC has `ProfileDefinition` (schedules) and `CapabilitySnapshot` (limits) but no effective-dated *controller settings* snapshot. This series has `specs/sync/controller-settings.schema.json` and no event model for it. Neither is complete alone |
| **`DataExclusion`** | A sensor warm-up or known-bad stretch is not missing data; it is data known to be unusable. The RFC's event model has no way to say so, and a replay that cannot tell the difference scores itself against noise |
| **Replay inputs as a declared list** | The RFC asks controllers what they *can* emit (E12). It never asks what they *have and do not publish* — which is the `status: absent, path: null` line that makes completeness measurable |
| **Liveness under two controllers** | `ControllerInstanceRegistration` gives each instance an identity. Nothing in either tree says what happens when two instances write to one site, which is the normal case |

---

## 6. The concrete edit list

For `externals/cgm-remote-monitor-official/docs/proposals/`. Each is small,
each is independently useful, and none requires this series to be adopted.

| # | File | Change | Source |
|---|---|---|---|
| 1 | `agent-control-plane-rfc.md` § Motivation | Add "safety limits and effective parameters are not recoverable", with the 20%/50% replay figures and `max_iob` | §3.1 |
| 2 | `agent-control-plane-rfc.md` § API Design | Retitle "New Collections" → "Projection endpoints"; move the ten collections out of Phase 1; make `/events` the only Phase 1 read path | §4.1 |
| 3 | `agent-control-plane-rfc.md` § Capabilities | Note that `loop.version` and `openaps.version` are already published, so `ControllerKindDefinition.version` needs no controller change | §2 |
| 4 | `agent-control-plane-rfc.md` § Implementation Phases | Add the write-serialization question about the global cursor to open questions | §4.2 |
| 5 | `bridge-rules.md:68` | Delete `if (devicestatus.trio)`; document that oref derivatives share `openaps` and need a second-order signal | §3.2 |
| 6 | `bridge-rules.md:171,470` | Stop using `devicestatus.device` as `issuerId`/`controllerInstanceId`; use a hub-issued synthetic id, record `device` as an observed alias | §3.3 |
| 7 | `bridge-rules.md` § override extraction | Mark synthesized override effects with `confidence`; allow "active, effects unknown" | §3.4 |
| 8 | `bridge-rules.md` § issuer | Derive `issuerType` from `treatments.automatic`; treat `enteredBy` as a label, never an identity, and never propagate it | §4.3 |
| 9 | `conflict-resolution.md` § Event Ordering | State that the event cursor and v3's sync watermark are one object, exposed opaquely | §4.2 |
| 10 | `conflict-resolution.md` (whole) | Reconcile with `docs/10-domain/authority-model.md`, which is a near-duplicate. One should become the source and the other a pointer | §7 |
| 11 | `integration-questionnaire.md` (whole) | Pre-fill from measurement and source; mark each cell *measured*, *from source*, or *ask* | §7 |
| 12 | `api-query-normalization.md` §5.1 | Reconcile the devicestatus caps (100 docs, 7 days) with backfill and replay, which are bounded-but-large reads | §8 |

---

## 7. Pre-filling the questionnaire is the highest-value single edit

`integration-questionnaire.md` asks Loop, AAPS and Trio implementers twenty
questions across fourteen tables, and every cell is empty. Status on all four
controllers: *Pending*.

An empty table is a request for unpaid work from maintainers whose capacity
is demonstrably committed elsewhere — Loop's six-month commit history is
device connectivity, not sync. **A wrong table is a five-minute correction.**
Roughly half the questionnaire can be answered from the corpus or from each
project's own source, today, with provenance marked per cell:

| Question | Can be pre-filled | From |
|---|---|---|
| A3 Override dimensions | **Mostly** — Loop's observed dimensions are target range, multiplier, duration, name | `override.*` census |
| B6 Composition emission — controller version | **Yes** | `loop.version`, `openaps.version` |
| B6 — effective ISF/CR/basal, safety limits | **Yes, as "no"** | dosing-input map: absent/partial |
| C7 Suggested / requested / confirmed | **Yes** | §3.5 table |
| C8 Pump response codes | **Partly** — boolean ACK yes, error codes only Loop `failureReason` (2.4%) | census |
| D10 Monotonic ordering | **Partly** — `syncIdentifier` on 83% of treatments is a dedup key, not a sequence | census |
| F14 Controller registration — version, device info | **Yes** | `loop.version`, `device` (with §3.3's caveat) |
| A1 Profile identifiers, A2 templates, A4 resolution | **No — ask** | Internal to each controller |
| C9 Failure reason distinction | **No — ask** | Not published |
| D11 Offline batching, F13 remote commands, G15 timeline | **No — ask** | Not observable |

The remaining questions are then a genuinely short list of things only a
maintainer knows, which is what a questionnaire should be.

**One caveat that must travel with any pre-filled table.** The corpus is
**Loop-dominant — 9 of 11 sites — and contains no AAPS closed-loop site at
all.** Every `openaps.*` figure above comes from **one site**. A pre-filled
AAPS column would be read from source only, and must be labelled that way or
it will mislead exactly the maintainer it is meant to help.

---

## 8. One conflict to resolve before both land

`api-query-normalization.md` caps `devicestatus` at **100 documents and a
7-day range** for anonymous callers, 5× for admin. That is a sound answer to
the self-inflicted-DDoS problem it documents — and it collides with two
things:

* **Backfill and replay** are bounded-but-large reads. `oref-digital-twin`
  replays a history; a decomposition migration reads everything once.
* **The event stream** would inherit whatever limits `/events` is given, and
  a cursor-based reader catching up after an outage is indistinguishable from
  an abusive one by request shape alone.

**Recommended edit:** state that cursor-paginated reads are exempt from the
range cap and bounded by page size instead — the cursor already guarantees
forward progress and bounded work per request, which is what the cap is for.
This series' §3.4 makes the same argument from the other side: a
`queryProfile` fixed in advance is what makes a bounded query safe without
making it small.

---

## 9. What changes on our side

| Doc | Change |
|---|---|
| `nightscout-hub-sync-architecture-2026-09-11.md` §5.2 | Points here; §5.2 stays as the reconciliation table, this document carries the edits |
| `PROPOSAL-controller-descriptions-2026-09-11.md` §9 | Prior-art row points here |
| `docs/10-domain/authority-model.md` | Two cross-reference links point at a path that does not exist (`externals/cgm-remote-monitor/`, the fork, not `-official`). Fixed. The duplication with `conflict-resolution.md` is now named in the document itself |
| `nightscout-adoption-roadmap-2026-09-11.md` §6 | "How much of `docs/proposals/` is live" is now partly answered: no reference anywhere in `lib/` or `tests/`, one line in `docs/INDEX.md`, and all four questionnaire responses still *Pending* — drafted and parked, not in progress |

## 10. Caveats

* **Nobody upstream has been asked about any of this.** Every recommendation
  is a proposal to a document, not a decision about it. The RFC's status is
  "Draft (2026 Proposal)" and no maintainer has said it is active.
* **All `openaps.*` figures are single-site.** Trio and AAPS statements that
  are not from the corpus are read from each project's source and are marked
  as such.
* **"Parked, not in progress" is inferred** from the absence of references to
  these documents anywhere in `lib/` or `tests/` — the only mention in the
  tree is one line in `docs/INDEX.md` — and from the absence of filled
  questionnaire responses. It is not a statement anybody made.
* **The fan-out arithmetic in §4.1 is an upper bound on distinct endpoint
  calls**, extended from `sync-cost.json` under the same stated model. It is
  a basis for comparing designs, not a traffic measurement.
