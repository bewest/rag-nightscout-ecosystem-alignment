# Aligning the write-path checks in cgm-remote-monitor: an addendum to the write contract

*Contributor-facing maintainer note. **Status (living, 2026-10-25): proposal; the batch policy for
`WRITE_VALIDATION` is decided (D2, 2026-10-25), everything else in §3–§5 is open (§6).** Addendum to
the [write contract](../tenancy/write-contract-spec-2026-10-07.md) (`WRITE-CONTRACT`); it adds no
new design, only how the checks that refuse a write should converge on that contract's single write
step. Code facts are read from `cgm-remote-monitor` `official/dev` `428b20b7` unless a row names
another ref. Item state: [`queue/QUEUE.md`](../../../queue/QUEUE.md) (`MOD-WRITE-VALIDATION`,
`MOD-WRITE-VALIDATION-READ`, `MOD-UNITS-CANONICAL`, `WRITE-CONTRACT`); defect facts: the
[backfix register](../remedial/nightscout-backfix-register.md).*

Builds on, and does not repeat:

| source | what it already settles |
|---|---|
| [write contract](../tenancy/write-contract-spec-2026-10-07.md) §2, §6.1 | the single step `write(intent)`, per-item outcomes including `refused` + `reason`; route rules stay above the seam (§2.5); merge on match decided 2026-10-12 (Q1) |
| [identity specification](../platform/spec/identity.md) | I1–I9, the two-id rule; I2 amended for API v3 by BF-170 (2026-10-25) |
| [write-validation design](../../60-research/modernization/write-validation-design-2026-10-25.md) | `WRITE_VALIDATION=off\|log\|reject` (D1), batch policy (D2), class a/b/c of client guards (§2), read side (§3.3), units (§3.4) |
| [upload-refusal client behaviour](../../60-research/remedial/upload-refusal-client-behaviour-2026-10-25.md) | what each uploader does with a 400, a refused slot in a 200, and other non-2xx |
| [AndroidAPS websocket delivery lab](../../60-research/remedial/aaps-websocket-delivery-lab-2026-10-25.md) | which writes reach the `/storage` socket (BF-164) |
| [versioning policy](semver-and-release-versioning-policy-2026-09-15.md) | the semver ladder that classifies each step |
| [defaults calendar](../../60-research/modernization/defaults-calendar-2026-10-25.md) row B1 | the staged ladder decided for BF-67/86 on 2026-10-13 (announce → opt-in strict → strict default in a major) |

## 1. Purpose

Nightscout refuses some writes today through several independent checks, each with its own reply
status, message and batch behaviour. This note lists those kinds of check, states the target (one
check module called by the write step), and records the constraints, measured or read on
2026-10-25, that any unification has to respect, plus a rule for adding a new check.

## 2. Kinds of check that exist today

| kind | what it checks | where it lives (conceptually) | API v1 reply | API v3 reply | batch semantics |
|---|---|---|---|---|---|
| **Envelope** | `identifier` a non-blank string (create); `date` a number after 2000-01-01 (`MIN_TIMESTAMP`); `utcOffset` a number in −1440..1440; `app` a non-blank string | API v3 route layer (`create/validate.js`, `operationTools.validateCommon`); on PATCH only fields that are sent | — (v1 has no envelope) | 400 `{status, message}`, messages `Bad or missing identifier field`, `… date field`, `… utcOffset field`, `… app field` | v3 is one record per request |
| **Immutable fields on update** | `identifier`, `date`, `utcOffset`, `eventType`, `device`, `app`, `srvCreated`, `subject`, `srvModified`, `modifiedBy`, `isValid` differ from the stored record; skipped for a soft-deleted record and for `identifier` on deduplication | API v3 route layer (`update/validate.js`) | — | 400 `HTTP_400_IMMUTABLE_FIELD`, "Field {0} cannot be modified by the client"; a read-only stored document gets 422 "Trying to modify read-only document" | one record |
| **Field type** | for example a treatment's `eventType` and `identifier`, when present and not null, must be strings ("Treatment eventType must be a string"); an entry's `type` likewise ("Entry type must be a string") | v1 storage module, before any write (also on `v15.0.9`) | treatments POST: the route maps the error to 500 `{status, message: "Mongo Error"}` | — | **whole batch refused**: the check runs on every item before the first write, so nothing is stored |
| **Opt-in domain validation** (draft, `MOD-WRITE-VALIDATION`, not pushed) | Temporary Target rules: finite numbers, bottom ≤ top, units from a known set and plausible for the declared units (a double label is refused, D4) | one pure module (`lib/server/write-validation.js` on the draft), called from each path's existing validation point | `off`: unchanged; `log`: stored, one log line; `reject`: single item 400; batch per D2 | `reject`: 400 `{status, message: "Temporary Target: <rule message>"}` | v1 under `reject`: valid items stored, reply keeps one object per submitted item in order, a refused item has no `_id` and a `refused` member, `Warning: 299` header; all refused → 400 (D2) |
| **Body `_id` refusal** (BF-170, in PR #8845 to `dev`, pending push) | a client-supplied `_id` in the body of API v3 create or PUT; on PATCH, a changed `_id` | API v3 route layer | — | create and PUT: 400; PATCH: 400 "Field _id cannot be modified by the client" (reuses the immutable-field message on purpose, §4.2) | one record |

A per-path coverage table will be added here once pending security fixes are published.

## 3. The target

| element | target |
|---|---|
| module | one shared check module, pure (no I/O), called by `write(intent)` before target resolution (write contract §2.3 step 1), on the item **as it will be stored** (the design note §3.1 shows why: v1 `prepareData` changes `units`) |
| callers | every write path through the step: API v1, API v3, the socket, in-process writers (nightscout-connect, plugins) |
| result | outcome `refused` with `reason: {rule, field, message}`; the message never carries a stored value |
| route mapping | each route maps `refused` to its own reply (v3 400 `{status, message}`; v1 the D2 shape; socket a refusal ack, proposed in the design note §3.2). Route-only rules (auth, v1's 400 for a non-hex `_id`, query coercion) stay above the seam, per the write contract §2.5 |
| batch policy | one policy, the one decided for `WRITE_VALIDATION` on 2026-10-25 (D2): store the valid items, report the refused ones in place, all refused → 400 |
| conflict | today's field-type rule (§2) refuses a whole v1 batch. Moving it under D2 changes what a mixed batch stores; **aligning the two is an open decision for maintainers** (§6) |

## 4. Constraints any unification must respect (2026-10-25)

### 4.1 Client behaviour on refusal

From the [upload-refusal note](../../60-research/remedial/upload-refusal-client-behaviour-2026-10-25.md) §2 (run or read as marked there):

| client | constraint |
|---|---|
| Loop (NightscoutKit) | needs exactly 200 and a reply array as long as the batch; a shorter array or a whole-batch 400 makes it resend the batch on every trigger |
| Trio | any non-2xx stops its upload pipeline for up to 24 h |
| xDrip+ | entries stay queued (up to 7 days); treatment PUT failures drop later items in the pass |
| AndroidAPS v3: treatments, entries, food | a 400 drops the record and moves on; any other 4xx blocks that kind's queue |
| AndroidAPS v3: profile, devicestatus | any non-2xx blocks the queue |
| all | no client reads a `refused` member or a `Warning` header |

### 4.2 Message text

| text | constraint |
|---|---|
| "Bad or missing utcOffset field" | AndroidAPS string-matches it and resends with `utcOffset: 0`; a new rule must not produce it |
| "cannot be modified by the client" | AndroidAPS string-matches it and marks the record as never uploadable. Reuse it only when "permanent, don't retry" is intended, as the BF-170 PATCH `_id` decision does |
| any reply containing "Not" on the v1 socket | AndroidAPS 3.4.2.6's v1 socket client reconnects on it (session f4's lane report, 2026-10-25; not re-checked for this note) |

The draft's unit test checks every rule message against the first two (design note §3.2).

### 4.3 Relaying writers

Some writers re-send content that is already stored: oref0, tconnectsync, nightscout-connect's
Nightscout source, the Nightscout profile editor, and AndroidAPS 3.4.2.6. Refusing a value that a
working site may already hold can wedge them: the same stored content is refused on every pass.
tconnectsync exits after 45 minutes of failures. (Session f4's lane reports, 2026-10-25; not
re-checked for this note.)

### 4.4 Value types sent today

oref0 sends `timeAsSeconds` and `value` as strings (lane report, 2026-10-25). A type rule must not
cover those fields.

### 4.5 Status codes

Prefer a status clients already handle (400 for a refused item; the D2 200 for a mixed v1 batch).
Never answer a client error with a 5xx.

## 5. Adding a new check

| step | question | if yes |
|---|---|---|
| 1 | Is it a **structural invariant** (class a: true for every client, e.g. a range is ordered, a timed record has a time)? | candidate for the shared module |
| 2 | Is it **controller policy** (class b: a range or vocabulary one controller chose)? | stays client-side; Nightscout may surface a declared range (design note §3.5) but does not refuse on it |
| 3 | Is it **time sanity** (class c: a reading dated ahead of the server clock)? | flag only (log, read-side flag); do not refuse |
| 4 | For class a: **can the value already be stored on a working site?** | follow the staged ladder: log → notify → opt-in refuse → refuse by default in a major (as decided for BF-67/86 on 2026-10-13, and for `WRITE_VALIDATION` D1) |
| 5 | For class a: the value could not be stored without the site already failing | refusing directly is acceptable |

Worked example (a maintainer decision of 2026-10-25): **refuse a value the server could never have
loaded; tolerate on read a value a working site may hold.** Then check §4: the status and message
the refusal produces, and whether a relaying writer re-sends the value.

## 6. Open items for maintainers

| item | question | queue |
|---|---|---|
| batch-policy alignment | move today's whole-batch field-type refusal to the D2 policy, or keep it whole-batch | `WRITE-CONTRACT`, `MOD-WRITE-VALIDATION` |
| read-side flag | flag stored records that break a rule on API v3 reads (R1), report them (R2) | `MOD-WRITE-VALIDATION-READ` |
| units canonicalisation | N1 (spelling) or N2 (mg/dL plus original), and the conversion constant | `MOD-UNITS-CANONICAL` |
| socket coverage | opt-in validation on the socket's add and update paths (design note §3.1 lists it as the next step) | `MOD-WRITE-VALIDATION` |
| filtered `/storage` broadcast | BF-164 plan C, decided 2026-10-25: filtered broadcast after checks cover every path; filter and path-naming details open; `/storage` stays v3-only until then, and afterwards only records that pass the type checks are announced | `BFQ-164` |
