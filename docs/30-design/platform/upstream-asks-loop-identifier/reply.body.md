**Re: client-supplied identifiers for Nightscout**

Thank you for writing this up. We agree with the ask. We decided the same rule for our own design
work on 2026-10-16, and much of what you need is partly in place. This reply says where each part
stands today, what is decided but not built, what is not decided, and what we could do next together.

Code references are to cgm-remote-monitor `15.0.8` (`92d08342`) and to `dev` at `fade2299` (the
unreleased 15.0.9 candidate). Loop references are to LoopWorkspace `548b332`, which pins
NightscoutService `2cef489`, and to NightscoutKit `4ec9fd1`.

## 1. The problems you describe, as we measured them

- **The id cache.** Loop keeps a map from `syncIdentifier` to the server `_id` for 24 hours
  ([NightscoutService.swift:27](https://github.com/LoopKit/NightscoutService/blob/2cef4896f0704fb112575ab34b596ee7de78e48d/NightscoutServiceKit/NightscoutService.swift#L27)).
  An edit or delete of a carb or dose whose id is not in the map is not sent
  ([NightscoutUploader.swift:36-41, 53-58](https://github.com/LoopKit/NightscoutService/blob/2cef4896f0704fb112575ab34b596ee7de78e48d/NightscoutServiceKit/Extensions/NightscoutUploader.swift#L36-L58)).
- **A reply without `_id`.** NightscoutKit records `"NA"` when a POST reply item has no `_id`
  ([NightscoutClient.swift:488-505](https://github.com/LoopKit/NightscoutKit/blob/4ec9fd12a16b5d6c2de4f11870511361d42e1b7f/Sources/NightscoutKit/NightscoutClient.swift#L488-L505)),
  and later skips `PUT` and `DELETE` for that record (lines 84, 113, 141). The server sends such a
  reply today: a treatment re-send that matches by `created_at` + `eventType` is answered without
  `_id`. We track this as BF-165 (open).
- **Re-sends stored twice.** We measured every write path against every other. A record created
  through one path and re-sent without `_id` through another is stored twice in **38 of 66**
  ordered path pairs on `dev` (36 on 15.0.8)
  ([write contract §1.4](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/tenancy/write-contract-spec-2026-10-07.html#14-cross-path-re-send)).
  Device status over API v1 has no key at all on 15.0.8, so every re-send is a new document.
- **Device status from Loop.** In a corpus of 12 sites, Loop device status has 4,001 groups
  (22,635 documents) of byte-identical copies sharing `created_at` + `device`, and 3,078 groups
  (14,757 documents) of copies that differ. Some of the differing ones are retries whose
  upload-time fields changed (battery, the paired `enacted`). Others are separate decisions in
  the same second
  ([null and keys §2.1](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/60-research/tenancy/write-contract-null-and-keys-2026-10-12.html#21-devicestatus-sharing-created_at-device)).

Timestamps cannot tell these apart. A client identity can.

## 2. The rule we decided: "Two ids, one rule"

On 2026-10-16 the Nightscout maintainer decided this rule for the hub design. It is rule 5 of
decision D20
([execution plan §2.6.3](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.html#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16)):

> **Two ids, one rule.** `identifier` is the sync identity the client assigns, stable across
> retries and devices; in the typed API it is the controller's record id. `_id` is the storage key
> the hub assigns. Every write reply returns both. Re-sends match on `identifier` first, as the
> write contract's keys already order it, so a client needs no cache of server ids.

This is your proposal in our words:

| your proposal | rule 5 |
|---|---|
| alternate key assigned at the edge | `identifier` is the sync identity the client assigns |
| keep the surrogate key for internal identity | `_id` is the storage key the hub assigns |
| the phone and the watch derive the same value | stable across retries and devices |
| upsert on it, keep the stored `_id` | re-sends match on `identifier` first |
| no ObjectIdCache | a client needs no cache of server ids |

Rule 5 adds one thing: every write reply returns both ids. The specification adds `matchedBy`
(`identifier`, `_id`, or none for a new record), so a client can see why a write matched
([hub-sync design §3.7](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/platform/nightscout-hub-sync-architecture-2026-09-11.html#37-version-scoped-quirks-and-the-two-ids)).

Two related rules from the same decision:

- **`_id` stays a 24-hex value the server assigns** on every legacy surface (v1 and v3).
- **Today's `UUID_HANDLING` stays as it is.** It moves a non-ObjectId `_id` (for example Loop's
  override UUID) to `identifier`. It becomes a recorded quirk tied to the app versions that send
  it, and it retires once those versions send `identifier` instead (D20 rule 7).

## 3. Why we decided it

The 38-of-66 measurement above is the main reason. A key that differs by write path cannot be one
rule. Matching on the client's identity first removes most of those cases.

The other reason is that the controllers already work this way, each with its own field:

| client | its own record identity | sent to Nightscout as |
|---|---|---|
| Loop | `syncIdentifier` (UUID) | `syncIdentifier` on treatments; a UUID `_id` on overrides; nothing on entries or device status |
| Trio | a UUID per record | `_id` on carbs and temporary targets; `id` on other treatments (Trio `0b29cd534`) |
| xDrip+ | `uuid` | `uuid` on treatments (`NightscoutUploader.java:784`, xDrip `1ed760048`) |
| AndroidAPS | pump event id (`pumpId`, `pumpType`, `pumpSerial`) and the server's `identifier`, kept as `nightscoutId` | API v3 (`BolusExtension.kt:26, 44-45`, AndroidAPS `7e1d537d49`) |

Nightscout's gap is that it reads these under four names and matches on none of them for entries
or device status. One field, `identifier`, closes that gap for every client.

## 4. Where each part stands

### Works on 15.0.8 today

- **Treatments over API v1 match `identifier` first**, then `_id`, then `created_at` + `eventType`
  ([treatments.js:356-381](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/server/treatments.js#L356-L381)).
  When a write matches by `identifier`, the reply carries the stored `_id`
  ([lines 104-128](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/server/treatments.js#L104-L128)).
  So sending `identifier` on treatments also avoids BF-165's missing `_id`.
- **API v3 keeps a client's `identifier`** on every collection. It computes one from `device` +
  `date` (+ `eventType`) only when none is sent, and logs a warning when they differ
  ([operationTools.js:114-126](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/api3/shared/operationTools.js#L114-L126)).
  The API documentation says the opposite: "The client should not create the identifier"
  ([swagger.yaml:1103](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/api3/swagger.yaml#L1103)).
  That sentence is wrong, and we filed it as BF-169 on 2026-10-17. The same description's "immutable
  by the client" is accurate for `PUT` and `PATCH`.
- **API v3 already merges on the fallback key only when the stored record has no `identifier`**
  ([utils.js:159](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/api3/storage/mongoCollection/utils.js#L159)).
  That is the option in your first question.

Two small corrections to the proposal's table, for the record. Treatments have matched on
`identifier` since **15.0.7** (commit `e78a5bc6`, merged in #8421), not 15.0.8. And API v3 keeps a
client value, as above.

### In `dev`, unreleased (15.0.9 candidate)

- **BF-121** (merged in #8780): a treatment with no `identifier` and no `_id` now also matches on the
  client's own identity: Loop `syncIdentifier`, Trio `id`, xDrip+ `uuid`, or `NSCLIENT_ID`. A write
  that carries none matches only a stored record that has none, and no `identifier` either
  ([treatment-fallback-key.js:25-63](https://github.com/nightscout/cgm-remote-monitor/blob/fade229909e6f3a0b5459230bc7273fe85de4f32/lib/server/treatment-fallback-key.js#L25-L63)).
  This is the reverse of your first question: a write without an identity cannot fold into a
  record that has one.
- **#8758**: device status over API v1 answers a re-sent 24-hex `_id` with the stored record
  instead of a second copy. Loop sends no `_id` on device status, so this does not reach Loop.

### Decided, not built

From the write contract the maintainer decided on 2026-10-12
([§6.1](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/tenancy/write-contract-spec-2026-10-07.html#61-decided-2026-10-12)),
plus rule 5:

- One write step for every path, with keys tried in order: `identifier`, then `_id`, then one
  natural key per collection (entries `date` + `type`; device status `created_at` + `device`).
- On a match, merge (an explicit `PUT` still replaces).
- **U6**: every accepted item is answered with its stored `_id` and `identifier`. A duplicate is
  never a 5xx and never an empty reply
  ([§3](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/30-design/tenancy/write-contract-spec-2026-10-07.html#3-the-unified-re-send-rule)).
  This closes BF-165.
- Two releases: first the write step with today's behaviour pinned, then the behaviour changes as
  a minor release.

### Not decided anywhere

- a **unique** index on `identifier`. Indexes on `identifier` exist today, and none is unique;
- a published **length limit** and allowed characters;
- **v1 `GET`, `PUT` and `DELETE` by an arbitrary identifier**. Today `find[identifier]=…` works
  but, like any v1 query without a date or `_id`, only over the last 4 days. A UUID-shaped `:id`
  or `find[_id]` is rewritten to match `identifier` or `_id` under `UUID_HANDLING`. A value such
  as `g7:<serial>:<seconds>` is neither hex nor a UUID, so by-id routes find nothing
  ([query.js:33-36, 95-144](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/server/query.js#L95-L144));
- **whether `date` may change on an `identifier` match.** On API v3, `date`, `device` and
  `eventType` are immutable. A re-send with the same `identifier` and a different `date`,
  `device` or `eventType` is answered 400 ("Field date cannot be modified by the client") and the
  stored record is left as it was, not stored twice; a `PUT` by identifier is answered the same.
  We ran it on 15.0.8 and on `dev` (`fade2299`) for entries, treatments and device status, with an
  identical re-send answered 200 as the control
  ([update/validate.js:21-43](https://github.com/nightscout/cgm-remote-monitor/blob/92d0834219aa771b5837dbcbf1baeb839a200cf6/lib/api3/generic/update/validate.js#L21-L43)).
  On v1 the same re-send updates the time on treatments and adds a second record on entries.
  Your watch-and-phone example (1.5 s apart, two `device` values) and an edited carb time both
  meet this rule. It needs a decision.

## 5. Your three questions

**Q1. A new `identifier` at an existing `sysTime` + `type`: keep both or merge?**
Today the answer depends on the path:

- API v3, every collection: merge only when the stored record has no `identifier`, which is your
  option.
- v1 treatments (15.0.7 and later): a write with an `identifier` matches on `identifier` alone, so
  it is kept beside any stored record. In `dev`, BF-121 adds the other direction: a write with no
  identity cannot fold into a record that has one.
- v1 entries: `sysTime` + `type` alone, so the second sensor's reading is merged into the first.

The write contract decided entries' natural key (`date` + `type`), but not whether that key may
match a stored record that has an `identifier`, or whether a write that has one may fall back to
it at all. Your option keeps two identified sensors apart and still adopts a legacy record that
has no `identifier`. Our position is to take it for every collection and path, so the paths stop
disagreeing; treatments over v1 would then also adopt legacy records. We would like to record that
as a decision row with you.

**Q2. Per-record batch results instead of failing the whole batch?**
Today a v1 batch is one ordered `bulkWrite` (`insertMany` for device status). It stops at the first
failure, keeps the writes before it, and answers one 500 with no per-item status. Decided (U6):
each accepted item is answered with its stored ids, and a duplicate is never a 5xx. The write
step's internal result already carries one outcome per item, including `refused` with a reason.
Not decided: how v1 shows a refused item. NightscoutKit requires the reply to have as many items as
the request, so a per-item status inside each item may fit Loop better than a new envelope. Your
view would help. Note that a unique index without per-item results would turn a collision into a
whole-batch 500, so per-item results come first.

**Q3. Is insert-only device status intentional? Should an identifier make re-sends idempotent?**
We found no record that it was chosen. At 15.0.8, v1 device status has no key. Decided 2026-10-12:
the same `created_at` + `device` with an **identical** body is a retry and is not stored again; a
differing body is a new record. We chose body comparison because Loop writes distinct reports
under the same `created_at` + `device` (§1 above), so merging on that key would fold them.

A client `identifier` is a cleaner retry signal. Each Loop dosing decision already has a
`syncIdentifier` ([LoopKit `DosingDecisionStore.swift:263`](https://github.com/LoopKit/LoopKit/blob/d9f1437353482690426bd981536f58c1e95ff535/LoopKit/DosingDecisionStore.swift#L263), the LoopKit `548b332` pins). If device status carried it, a retry
whose battery reading changed would match its first attempt, and two decisions in the same second
would stay two records. Body comparison cannot do either. NightscoutKit's `DeviceStatus` already
has an `identifier` member; NightscoutService does not set it today. We would revisit the
device status decision with you on that basis: `identifier` first, then the identical-body rule
for clients that send none.

**A question back to you: a re-send or an edit?**
Your watch-and-phone example could mean either of two things, and the proposal does not say
which. Say the watch uploads a reading, and later the phone uploads the same reading with the same
`identifier`, a different `device` and a `date` 1.5 s later. What should Nightscout do?

| outcome | what is stored | what the phone sees |
|---|---|---|
| reject | the watch's record | an error (API v3 today: 400) |
| update | one record, now with the phone's `device` and `date` | success |
| acknowledge | the watch's record, unchanged | success, with the stored ids |

Our decision of record is **update**. The write contract merges a matching re-send into the
stored record on every path (decision Q1, 2026-10-12), and rule 5 matches on `identifier` first.
So once built, the phone's upload would replace `device` and move `date` by 1.5 s. Today's
servers do something different on every path: API v3 rejects it, v1 entries store a second
record, and v1 treatments update it.

The contrast matters for the backfill you describe. A rejection would stall the phone's upload of
that data type, because NightscoutKit treats an error reply as a failed batch. An update rewrites
which device uploaded the reading. An acknowledgement keeps the first upload and needs no
coordination, but it cannot carry a correction.

So, two cases:

1. **The same reading, uploaded again by another device.** Should Nightscout acknowledge it and
   keep the first `device` and `date`, or overwrite them with the later upload's?
2. **An intended edit**, such as a carb's time or amount changed in Loop. Should a re-send with
   the same `identifier` update the record? If both cases are wanted, how should Nightscout tell
   them apart: by `POST` versus `PUT`, or by something in the record?

Your answer becomes a decision row next to Q1, and we would revise Q1 for `identifier` matches if
it points the other way.

## 6. What we propose to do next

In order:

1. **Loop sends `identifier` on treatments, entries and device status.** Nothing on the server
   blocks this today. A server older than 15.0.7 stores the field and ignores it. On 15.0.7 and
   later it already works for treatments over v1, including `DELETE /treatments/<uuid>`, which is
   how Loop deletes overrides now. It also works for every collection over API v3. Two cautions:
    - **Each `identifier` must name exactly one Nightscout record.** In our 12-site corpus, 13 of
      the 255,811 `syncIdentifier` values on Loop treatments are each on 2 to 4 records. For
      example, a Suspend Pump and a Temp Basal at the same instant share one value
      ([identifier duplicates §2.2](https://bewest.github.io/rag-nightscout-ecosystem-alignment/docs/60-research/tenancy/identifier-duplicates-2026-10-17.html#22-syncidentifier-on-treatments-as-a-proxy-m)).
      Sent as `identifier` to a 15.0.7+ server, the second upload would replace the first, because
      treatments match on `identifier` first and replace the whole stored record. Where one
      `syncIdentifier` becomes several treatments, each needs its own `identifier`. We have not
      read which Loop path produces these pairs.
    - **Entries are not matched on `identifier` yet.** Until the server side lands, a phone backfill
      with the same `identifier` and a different time is stored as a second record. We measured
      this on v1 at 15.0.8 and `dev`
      ([lab results](https://bewest.github.io/rag-nightscout-ecosystem-alignment/tools/lab/v3-identifier-immutable/results/v3-identifier-immutable-2026-10-17.html)).
      Keep the phone's skip-the-watch-period approach until then. Device status stores the field
      and does not match on it, so sending it changes nothing there yet.
2. **We turn your three questions, and the `date` question above, into decision rows** beside rule
   5 and the write contract's §6.1, with a link to your proposal. We would like you to review
   them before they are marked decided.
3. **Shared conformance cases.** Our rule-5 cases are in `specs/sync/conformance/quirks/` (for
   example `carrier-write-both-ids.yaml` and `carrier-resend-matches-identifier.yaml`). We would
   add one case per question, including your watch-and-phone G7 example, and run them against the
   server. If Loop's tests can replay the same cases, both sides check one contract.
4. **Server side, after 15.0.9.** BF-169 (documentation). Then the write step with today's
   behaviour pinned. Then `identifier`-first matching for entries and device status, U6 replies,
   and the Q1 rule, as a minor release. The unique index, the length limit and v1 by-identifier
   routes follow the decisions in step 2. We are not giving dates.

Thanks again. Where would you like to continue: here, or on a pull request against the decision
records?
