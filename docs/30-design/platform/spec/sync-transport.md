# Sync transport (L4)

*Contributor-facing. Living specification, current at `main` `df621fa7` (2026-10-18). Layer L4 of
the [platform index](../README.md); terms are in the [glossary](glossary.md); how a re-send is
matched is in the [identity specification](identity.md) §3. Decisions: the
[write contract's §6.1](../../tenancy/write-contract-spec-2026-10-07.md#61-decided-2026-10-12)
(2026-10-12) and [D6](../../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions)
(the change feed under multi). Queue: `SPEC-SYNC-TRANSPORT`.*

How writes are applied, ordered and delivered, over REST and the socket, and what a client pays to
stay in sync. §2 is the write path the maintainer has decided; §3 is what sync costs today,
measured; §4–§6 are proposed and specified with cases where a rule can be checked by one.

## 1. Files

| file | what it is |
|---|---|
| [write contract](../../tenancy/write-contract-spec-2026-10-07.md) | the measured write matrix, the write step and the re-send rule this page states as rules |
| `tools/nsschema/sync_cost.py` | `make schema-sync-cost`: distinct endpoints each client's sync path can call, from its own source |
| `tools/nsschema/sync_cursor.py` | reference decision function for the cursor rules (§4); it checks the cases and is not a hub |
| `specs/sync/conformance/sync-transport/` | 9 synthetic cases (§9) |

## 2. The write path

| # | rule | status |
|---|---|---|
| T1 | **One write step.** Every path that writes (API v1, API v3, the socket, in-process callers such as nightscout-connect) writes through one step, which decides per item, in order: the `_id` form, the target (identity §3), the outcome (`inserted`, `merged`, `replaced`, `unchanged`, `deleted`, `not-found`, `refused`), the server dates, the storage write, and then one change event for the call. Each item is answered with its outcome and both ids (identity I4). | specified (`WRITE-CONTRACT`, blocked) |
| T2 | **Re-send outcomes.** A re-send that matches a stored record merges into it (JSON Merge Patch: a field sent as `null` is removed); an explicit update (v1 `PUT`, v3 `PUT`) replaces. An identical re-send keeps each path's behaviour today: rewritten on API v1, v3 and in-process, answered unchanged on the socket and for devicestatus. The socket keeps its ±2 s similar-treatment match as an explicit option. `activity` gets server dates and soft delete like the other collections. The step ships first with today's behaviour pinned (a patch), then these changes (a minor). | decided 2026-10-12 |
| T3 | **Server write times.** `srvModified` and `srvCreated` are the server's, in milliseconds since the epoch, set on every write to a collection API v3 serves, by any path; a value a client sends is replaced. Within one process every `srvModified` is unique and never goes backwards, even when the clock does, and boot restores the clock from stored records. | merged on `dev` (`lib/server/srv-dates.js` at `fade2299`, read) |
| T4 | **The change event.** One event per write call: the collection, the operation, the stored documents (or the removed ids), the largest `srvModified` in the call, and the origin. Under `TENANCY_MODE=multi` the event is read from the replication slot (D6), so every field but `runtime` and `origin` is derived from the committed row. | specified (write contract §2.4) |

## 3. What sync costs today

`make schema-sync-cost`, run 2026-10-18: distinct endpoints each client's sync path can call per
five-minute cycle, priced at 288 cycles a day. It is a source-derived upper bound, not a packet
capture: a cycle with nothing to send makes fewer calls, and a catch-up after an outage makes
more.

| client (source read) | API | endpoints | watermark | delta read | upper bound a day | two requests a cycle |
|---|---|---:|---|---|---:|---:|
| AndroidAPS `7e1d537d49` (dev; `core/nssdk/.../NightscoutApi.kt`) | v3 | 26 | yes | per collection | 7,488 | 576 |
| Loop: NightscoutKit `4ec9fd12a1` | v1 | 7 | no | no | 2,016 | 576 |
| Trio `0b29cd5341` | v1 | 5 | no | no | 1,440 | 576 |

The client that uses API v3 as designed has the largest fan-out, because v3 gives it one delta read
per collection. AndroidAPS's count includes the dev-only `settings` calls of its client control.
The dated documents' figure of 20 for AndroidAPS was measured on its earlier client
(`NightscoutRemoteService.kt`). Payload size and real request counts are not measured.

## 4. The sync read and write (proposed)

| # | rule |
|---|---|
| T5 | **One read across collections.** `GET /api/v3/history/{cursor}?collections=&limit=` answers `{cursor, complete, collections: {name: [records]}}` for every collection the credential may read (each checked as `api:<collection>:read`); a collection it may not read is left out. Per-collection `history` stays. |
| T6 | **The merged cursor.** With a page limit per collection, the cursor returned is the smallest last `srvModified` among the collections that were truncated, or the hub's watermark (T9) when none was; `complete` is true only when no collection was truncated. A client reads again from the returned cursor while `complete` is false. A record can come back twice across pages; the client keeps one (T10). |
| T7 | **One write across collections.** `POST /api/v3/batch` takes `[{collection, doc}]` and answers each item as T1 does; a batch is idempotent per record. |
| T8 | **One opaque cursor.** The sync cursor is opaque to clients. Under `single` it is a `srvModified` watermark; under `multi` it is the replication slot's position (D6), which is commit-ordered. An event cursor, if one is added, is the same cursor. |
| T9 | **A low watermark.** The cursor a hub hands out never passes a write that has taken its `srvModified` but is not yet visible to readers: it is at most one less than the smallest such value, and at most the largest value taken. Under `single` the hub tracks the values it has taken and not yet stored; under `multi` the slot's position gives this. |
| T10 | **The socket is the fast path; history is the record.** A socket event carries the record and the hub's low watermark (T9) at the time the record became visible, not the record's own `srvModified`. A client that reconnects reads history from the last cursor it holds and misses nothing. A record received both ways is one record, by `identifier` (or `_id`) and `srvModified`. |

## 5. Typed records on the socket (proposed)

| # | rule |
|---|---|
| T11 | **Subscribe by what the credential may read.** A client subscribes by product and channel ([registration §9](registration.md#9-channels-roles-and-provenance)); the hub delivers events for typed records the credential may read. Each event carries the typed record, both ids (identity I4), its definition id, its instance and the role's provenance, and the T10 cursor. Where an element's `carrierView` is `served` ([registration §13](registration.md#13-projected-views-for-older-readers)), subscribers to the carrier's collection receive the projected document. |
| T12 | **Which writes reach the socket is open.** Today only API v3 writes reach the API v3 storage socket; writes through v1, the v1 socket and in-process callers do not (BF-164, reproduced on `dev` `43289dde` and 15.0.8). Whether broadcasting them would help or harm AndroidAPS, which uses the socket by default and stops polling after its first load (read), is a question to its authors before a rule is set. T10 holds either way: a client that misses an event reads it from history. |

## 6. Definitions and versions (proposed)

| # | rule |
|---|---|
| T13 | **Stored records keep their definition.** A typed record keeps the `definitionId` it was written under. The hub never converts a stored record to another version without a lossless mapping the definition declares ([registration G4](registration.md#3-the-grammar)); a reader chooses the version it shows ([registration §12](registration.md#12-read-selection)). |
| T14 | **A page carries the definitions it needs.** A sync read includes, under `definitions`, each definition referenced by a returned record, so a client can read a record written under a definition it has not seen. |
| T15 | **Moving records to a new version is the controller's.** A controller that wants stored records under a new version sends them again under the new definition with the same `identifier`; the re-send matches the stored record (identity I7) and replaces its content and `definitionId`. The hub records the change like any other write. |

## 7. Compatibility

| | older hub | newer hub |
|---|---|---|
| **older client** | today's per-collection reads and writes | unchanged: per-collection `history`, v1 and the v1 socket stay |
| **newer client** | no `history` envelope: it reads per collection, as AndroidAPS does today | one read and one write per cycle (T5, T7), with the socket for latency (T10) |

Nothing is retired. A capability member that says a hub serves T5 and T7 is not yet in the
capability document.

## 8. Open

1. **Choices for the maintainer:** the T5 and T7 paths; whether a typed re-send under a new
   definition replaces or merges (T15); whether a page carries definitions inline (T14) or only
   their ids; a capability member for the sync envelope.
2. **The in-flight window under `single`.** `srv-dates.js` takes a value just before the write, so
   a slow write can become visible after a reader has passed its value; T9 closes this only once
   the hub tracks values it has taken and not stored. How often it happens is not measured.
3. **BF-164** (T12).
4. **The write step** (`WRITE-CONTRACT`, `WC-STEP-PATCH`, `ID-BATCH-RESULTS`) is blocked behind the
   storage seam refresh.
5. **Not measured:** payload size; real request counts; `srvModified` order under several writers
   on one site; the replication-slot path (T4.1 in the execution plan).

## 9. Conformance cases

9 cases under `specs/sync/conformance/sync-transport/`, checked by
`tools/nsschema/test_sync_cursor.py`, whose expectations are written by hand. Each is a timeline of
writes, each taking its `srvModified` at one step and becoming visible at the same or a later one,
and the client's history reads and socket events. The typed socket (§5) and versions (§6) have no
case yet.

<!-- BEGIN GENERATED: sync-transport-cases (tools/nsschema/spec_cases.py) -->
| case | shows | expected | control |
|---|---|---|---|
| `sync-transport/duplicate-delivery-is-one-record` | A record received by event and by history is one record | rules T10 |  |
| `sync-transport/event-carries-low-watermark` | A socket event carries the low watermark, not its record's srvModified | rules T9, T10 | `socket-resume-after-disconnect` |
| `sync-transport/in-flight-write-not-skipped` | The cursor stays below a write that has taken its srvModified and is not yet visible | rules T9 | `no-write-in-flight` |
| `sync-transport/merged-cursor-min-over-truncated` | A page truncated in one collection holds the cursor at that collection's last value | rules T6 | `single-page-complete` |
| `sync-transport/no-write-in-flight` | With nothing in flight the cursor reaches the latest value | rules T9 |  |
| `sync-transport/nothing-new` | A read with nothing newer returns no records and keeps the cursor | rules T6 |  |
| `sync-transport/single-page-complete` | With a large enough limit one page is complete | rules T6 |  |
| `sync-transport/socket-resume-after-disconnect` | A client that reconnects reads history from the cursor its last event carried | rules T10 |  |
| `sync-transport/unreadable-collection-omitted` | A collection the credential cannot read is left out | rules T5 |  |
<!-- END GENERATED: sync-transport-cases -->
