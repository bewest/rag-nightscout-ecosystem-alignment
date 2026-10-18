# Upstream ask: the Loop developers' `identifier` proposal

*Contributor-facing. **DRAFT, not yet sent. For maintainer review.** Queue item `LOOP-ID-REPLY`.
Facts checked 2026-10-17 at cgm-remote-monitor `15.0.8` (`92d08342`) and `dev` `fade2299`, Loop at
LoopWorkspace `548b332` (NightscoutService `2cef489`, LoopKit `d9f1437`) and NightscoutKit `4ec9fd1`,
from this repository's `5a6cef4d`. Each project's maintainers decide what, if anything, to do.*

## What this is

The Loop developers shared a proposal on 2026-10-17: *Client-supplied identifiers for Nightscout*,
based on 15.0.8. It is a private page shared with the maintainer and is not linked from here. Our
draft reply is [reply.body.md](reply.body.md), ready to paste as GitHub or Zulip markdown. It links
the published pages on the project site.

## The simple contract

What the reply proposes, and what Nightscout supports today except where the reply's table says
otherwise:

1. `_id` is a MongoDB ObjectId (24 hex) or absent. A client may create its own ObjectId and send
   it. Other values are not valid; `UUID_HANDLING` (default on) moves a UUID `_id` to
   `identifier` on treatments and entries, as a compatibility rule.
2. If `_id` is absent, the client sends `identifier`, a string (UUID recommended: v5 of a
   source-derived key when devices must agree, v4 once for a manual entry). The server assigns
   `_id`. One identifier names one record.
3. If neither is sent, the collection's time key applies (entries `sysTime` + `type`, treatments
   `created_at` + `eventType`); this fallback may be deprecated later.

Tie-break (proposed, queue `ID-CLIENT-OID-DECISION`): when a write carries both and they point at
different records, `_id` decides. That differs from D20 rule 5's identifier-first order and from
v1 treatments today (`identifier` present drops `_id`, `server/treatments.js:356-362` @15.0.8).
Every write reply returns both ids (rule 5).

The one server change it needs, v1 entries and device status matching on `identifier`, is queue
item `ID-SIMPLE-MATCH`; it ships with BF-169 after 15.0.9 (maintainer, 2026-10-17; see
[15.0.9 decisions](../../../../releases/cgm-remote-monitor-15.0.9/decisions.md#decided-at-the-same-time-outside-1509s-contents)).

## The proposal, summarised

**The ask.** An uploader gives each record a stable `identifier` taken from the data's source. The
server puts a unique index on it and upserts on it, in every collection and both API versions.
Records without one keep today's rules.

- `identifier` is an opaque client string with a published length limit; a sparse unique index in
  entries, treatments and device status.
- If present, upsert on it and keep the stored `_id`. If absent, today's rules. Additive.
- v1 `GET`, `PUT` and `DELETE` by identifier. API v3 treats a client's value as authoritative and
  computes one only when none is sent.
- Clients derive it from the source: sensor serial + sensor time (for example
  `g7:<serial>:<seconds since activation>`, so a phone and a watch agree), the pump's event id, or
  a UUID made once for a manual entry.
- Loop would send its `syncIdentifier` as `identifier` on all three collections.
- Questions: (Q1) a new identifier at an existing `sysTime` + `type`: keep both or merge, perhaps
  merge only when the stored row has none; (Q2) per-record batch results; (Q3) is insert-only
  device status intentional, and should an identifier make re-sends idempotent.

## How the reply argues

Rewritten 2026-10-17 around the simple contract, at the maintainer's direction that the simple
model is generally workable; the previous, longer version is in git history at `dd6febcc`.

1. Agrees with the ask; most of it works; the confusion is largely the swagger sentence (BF-169).
2. The three rules and the tie-break, with D20 rule 5's "every write reply returns both" quoted.
3. A table of what works today and the one gap (v1 entries and device status store `identifier`
   but do not match on it).
4. The watch-and-phone case: four options; recommends a source-derived identifier, with an
   agreed timestamp as an interim that needs no server change. FHIR and HealthKit precedents.
5. Cautions for Loop starting today; what we will do (the one server change and BF-169, after
   15.0.9); the deferred questions as a short list.

## Evidence

[R] read at the ref; [M] measured (the cited page says how). cgm-remote-monitor paths are under
`lib/`.

| claim | our finding | where |
|---|---|---|
| proposal: treatments accept `identifier` "new in 15.0.8" | identifier-first upsert since **15.0.7**: commit `e78a5bc6` reached `dev` through #8421 (merge `cdef1e7c`, 2026-03-16); not in 15.0.6 [R] | `server/treatments.js:356-381` @15.0.8; `git merge-base --is-ancestor e78a5bc6 15.0.7` |
| identifier match returns the stored `_id` | yes, looked up after the write [R] | `server/treatments.js:104-128` @15.0.8 |
| `syncIdentifier` not matched at 15.0.8 | correct [R] | `server/treatments.js:376-380` @15.0.8 |
| BF-121 adds client identity to the treatment fallback | `CLIENT_IDS = syncIdentifier, id, uuid, NSCLIENT_ID`; a write with none matches only a record with none and no `identifier` [R]. It does **not** make a write *with* `identifier` fall back: that write still matches on `identifier` only | `server/treatment-fallback-key.js:25-63`, `server/treatments.js:411-434` @dev |
| v1 entries ignore `identifier` | match on `sysTime` + `type` only [R] | `server/entries.js:238-255` @15.0.8; `:301` @dev |
| v1 device status insert-only | `insertMany`, no key [R]; dev (#8758) answers a re-sent 24-hex `_id` with the stored record [R] | `server/devicestatus.js:70` @15.0.8; `:45-56` @dev |
| proposal: v3 "spec tells clients not to supply one" | the code keeps a client value, computes one only when absent, warns on mismatch [R, and reproduced at module level by the records agent]; swagger's "client should not create the identifier" is wrong: **BF-169** (filed 2026-10-17, `e8a1f2d0`, on main since 52a82ac8). Its "immutable by the client" part is accurate for PUT/PATCH | `api3/shared/operationTools.js:114-126`; `api3/swagger.yaml:1103` @15.0.8, `:1062` @dev; `swagger.json:1383` both |
| v3 fallback dedup | `date`+`type` (entries), `created_at`+`device` (device status), `created_at`+`eventType` (treatments), and only against a stored record **with no `identifier`** [R] | `api3/generic/setup.js:44,54,95`; `api3/storage/mongoCollection/utils.js:128-168` (`:159`) @15.0.8, `:208` @dev |
| v3 re-send with same `identifier`, different `date`/`device` | 400 immutable field, stored record unchanged, one copy; same for `eventType` on treatments and for `PUT` by identifier; identical re-send 200. Entries, treatments, device status [M, 15.0.8 and `fade2299`, MongoDB 7.0.43]. Only difference: on `dev` a record first written through v1 (no `date`/`device`) accepts a first `device` at the same time [M]. v1 contrast: treatments update the time, entries store a second record [M] | `api3/generic/update/validate.js:21-43` @15.0.8; `:71-91` @dev; [lab results 2026-10-17](../../../../tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.md) |
| indexes on `identifier` | present, none unique [R] | `server/entries.js:224,226`; `server/treatments.js:430,432`; `server/devicestatus.js:168`; `api3/storage/mongoCollection/index.js:21` @15.0.8 |
| v1 batch failure | ordered `bulkWrite` / `insertMany`; stops at first failure, earlier writes kept, one 500 [R] | `server/treatments.js:91`, `server/entries.js:147`, `api/treatments/index.js:130-133` @15.0.8 |
| v1 lookup by identifier | default window 4 days without a date or `_id`; UUID `_id` rewritten to `$or` identifier/`_id` under `UUID_HANDLING`; other non-hex values find nothing; `$in` not rewritten [R] | `server/query.js:33-36, 95-144` @15.0.8 |
| Loop id cache | 24 h; update/delete without a cached id not sent [R] | NightscoutService `NightscoutService.swift:27`, `Extensions/NightscoutUploader.swift:36-41, 53-58` |
| Loop `"NA"` | missing `_id` → `"NA"`; reply length must equal request; `"NA"` skipped on modify/delete [R] | NightscoutKit `NightscoutClient.swift:488-505, 84, 113, 141` |
| Loop sends | `syncIdentifier` on treatments; override `_id` = syncIdentifier UUID (QUIRK-TREATMENTS-006); no id on entries; no `identifier` on device status, though NightscoutKit's `DeviceStatus` has the member [R] | `NightscoutTreatment.swift:111,117`; `OverrideTreament.swift:59`; `StoredGlucoseSample.swift:34-41`; `StoredDosingDecision.swift:149-163`; NightscoutKit `DeviceStatus.swift:60-61` |
| Loop dosing decision identity | `StoredDosingDecision.syncIdentifier` [R] | LoopKit `DosingDecisionStore.swift:263` |
| cross-path re-sends | 38 of 66 pairs stored twice on `dev` `43289dde`, 36 on 15.0.8 [M] | [write contract §1.4](../../tenancy/write-contract-spec-2026-10-07.md#14-cross-path-re-send) |
| Loop device status copies | 4,001 identical groups (22,635 docs); 3,078 differing groups (14,757 docs); 12 sites [M] | [null and keys §2.1, §2.1.1](../../../60-research/tenancy/write-contract-null-and-keys-2026-10-12.md#21-devicestatus-sharing-created_at-device) |
| Trio | `_id` on carbs and temporary targets, `id` on other treatments [R] | Trio `0b29cd534`: `CarbsEntry.swift:29`, `TempTarget.swift:50`, `NightscoutTreatment.swift:62` |
| xDrip+ | sends `uuid` on treatments [R] | xDrip `1ed760048`: `NightscoutUploader.java:784` |
| AndroidAPS | keeps the server `identifier` as `nightscoutId`, plus `pumpId`/`pumpType`/`pumpSerial` [R] | AndroidAPS `7e1d537d49`: `BolusExtension.kt:26, 44-45` |

Decisions cited: [D20 rule 5 and rule 7](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16)
(`18397441`, 2026-10-16); [write contract §3 (U4, U6) and §6.1](../../tenancy/write-contract-spec-2026-10-07.md#61-decided-2026-10-12)
(2026-10-12); [hub-sync design §3.7](../nightscout-hub-sync-architecture-2026-09-11.md#37-version-scoped-quirks-and-the-two-ids)
(`write.ids`, `matchedBy`); cases in [`specs/sync/conformance/quirks/`](../../../../specs/sync/conformance/quirks/);
[GAP-SYNC-032](../../../../traceability/sync-identity-gaps.md) ("send `syncIdentifier` as
`identifier`") and REQ-BATCH-003 (per-item results) in
[sync-identity-requirements](../../../../traceability/sync-identity-requirements.md).

**Records that disagree with the code, not used in the reply.** GAP-SYNC-033 says xDrip+ does not
send its `uuid`; it does, on treatments. [Server-side dedup considerations](../../../10-domain/server-side-dedup-considerations.md)
(2026-03-18) says `uuid` is "not used for dedup"; BF-121 in `dev` uses it. Its Option B (clients
send `identifier`) is the direction the reply takes.

## Conversation record

| date | direction | channel | summary | where recorded |
|---|---|---|---|---|
| 2026-10-17 | received | private page shared with the maintainer | Loop developers' proposal: client `identifier`, unique sparse index, upsert, v1 by-identifier routes; Q1–Q3 | this README; to be weighed against D20 rule 5, write contract §6.1, and [ADR-002](../../../90-decisions/adr-002-sync-identity-strategy.md) (Proposed) |
| — | to send | not chosen | [reply.body.md](reply.body.md); adds (2026-10-17) a question back: is the watch-and-phone case a re-send to acknowledge or an edit to apply? Our decision of record (write contract Q1, merge on match) answers "update" | `ID-V3-IMMUTABLE-DECISION` (queue), beside write contract §6.1 Q1 |
| 2026-10-17 | rewritten | — | reply rewritten around the simple contract (three rules, tie-break `_id` decides, one server change after 15.0.9); previous version at `dd6febcc` in git history | `ID-SIMPLE-MATCH`, `ID-CLIENT-OID-DECISION` (queue) |

When the reply is sent, add its date, channel and link. When they answer, add a row and the
decision row it produces.

## Open for the maintainer before sending

- **Where to post.** Unknown: the proposal names no channel. Candidates are Loop Zulip, a
  cgm-remote-monitor issue or discussion, or a pull request against our decision records.
- **ADR-002.** [ADR-002](../../../90-decisions/adr-002-sync-identity-strategy.md) (Proposed,
  2026-01-17) names a new `syncId` field in UUID v4 format. D20 rule 5 and this reply use
  `identifier`, and Loop proposes opaque non-UUID values. The reply does not cite ADR-002; it may
  need a superseding note.
- **Q1–Q3 and the `date` question.** The rewritten reply takes no position on them; they are in
  its "Later, only if needed" list. The `date` behaviour on API v3 is reproduced
  ([lab results](../../../../tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.md)).
- **Tie-break.** The reply proposes that `_id` decides when the two ids disagree, which departs
  from D20 rule 5's order. Confirm before sending (`ID-CLIENT-OID-DECISION`).
- **Push first.** The reply links pages on the project site; the gh-pages build of 2026-10-17
  (`de66763c`) has every linked page and anchor, including the folder's `index.html` the rewritten
  reply links. BF-169 is cited by number only.
