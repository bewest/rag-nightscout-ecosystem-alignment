# Write-path domain validation: lifting client ingestion guards into Nightscout

> **Draft design for maintainer review, 2026-10-25.** Base: cgm-remote-monitor `official/dev` `b29f1bf7`; draft code on local branch `feat/api3-domain-validation` `a2e5fe49` (three commits: `e8125d89`, `6e842c07`, `a2e5fe49`; not pushed). Decided by the maintainer on 2026-10-25: **D1** (the setting is `WRITE_VALIDATION=off|log|reject`, default `off`), **D2** (an API v1 batch under `reject` stores its valid items and reports the refused ones in place; all refused gives 400) and **D4** (a double-labelled record is refused with a message naming the field and the units to send). Open: D3's last step, D5, D6 (§6). Everything else here is a proposal. Contributor-facing. Current state: queue items `MOD-WRITE-VALIDATION`, `MOD-WRITE-VALIDATION-READ`, `MOD-UNITS-CANONICAL`; [backfix register](../../30-design/remedial/nightscout-backfix-register.md) BF-180, BF-95, BF-181.

Session f4's `v3-validation` lane. Evidence for §3.2 and §D3:
[upload-refusal-client-behaviour-2026-10-25](../remedial/upload-refusal-client-behaviour-2026-10-25.md).

Sources read (pinned):

- AndroidAPS `externals/AndroidAPS` `7e1d537d49` (abbreviations: **TM** = `core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/mapper/TreatmentMapper.kt`, **IDP** = `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/NsIncomingDataProcessor.kt`, **C** = `core/data/src/commonMain/kotlin/app/aaps/core/data/configuration/Constants.kt`)
- Trio `externals/Trio` `0b29cd534`
- NightscoutKit `externals/NightscoutKit` `4ec9fd1`
- cgm-remote-monitor `b29f1bf7`

Every line reference below was read, not run, unless it says "measured". AndroidAPS line numbers in §1 and §3.2 are on `7e1d537d49`; the upload-refusal note's `dev` `3905d352dd` numbers differ for the same code.

## 1. Inventory: AndroidAPS NSClientV3 ingestion guards

Each AAPS guard drops the record silently. The mapper's `return null` and the processor's `continue` leave at most a debug log line. No error reaches Nightscout or the user.

### 1.1 Treatments: mapper (`RemoteTreatment.toTreatment`, TM)

The mapper dispatches on the first `when` branch that matches, in this order. That makes the order itself a rule: a record carrying `insulin > 0` becomes a bolus whatever its `eventType` says.

| # | collection / eventType | guard | TM line | class |
|---|---|---|---|---|
| T1 | any, `insulin > 0` | becomes NSBolus whatever the eventType; `insulin <= 0` falls through | :36 | a (shape) |
| T2 | any, `carbs != 0.0` | becomes NSCarbs; missing duration → 0 | :60-61 | a |
| T3 | Temporary Target | timestamp 0 (no date, mills, timestamp or created_at) → drop | :85 | a |
| T4 | Temporary Target | neither `durationInMilliseconds` nor `duration` → drop | :87 | a |
| T5 | Temporary Target | duration 0 → cancel, targets forced to 0 | :89-111 | a (cancel semantics) |
| T6 | Temporary Target | `targetBottom` or `targetTop` missing (non-cancel) → drop | :113-114 | a |
| T7 | Temp Basal | `extendedEmulated` present → read back as an extended bolus | :141 | a (AAPS shape) |
| T8 | Temp Basal | timestamp 0 → drop | :168 | a |
| T9 | Temp Basal | neither `absolute` nor `percent` → drop | :170 | a |
| T10 | Temp Basal | no duration → drop | :171 | a |
| T11 | Temp Basal | `durationInMilliseconds == 0` → drop. The check reads only the ms field, so `duration: 0` in minutes passes (read, not run) | :172 | a |
| T12 | Note with `originalProfileName` (effective profile switch) | timestamp 0, or any of `profileJson`, `originalCustomizedName`, `originalTimeshift`, `originalPercentage`, `originalDuration`, `originalEnd` missing → drop | :199-205 | a (AAPS shape) |
| T13 | Profile Switch | timestamp 0 or no `profile` → drop | :236-237 | a |
| T14 | Bolus Wizard | timestamp 0 or no `bolusCalculatorResult` → drop | :269-270 | a (AAPS shape) |
| T15 | Site/Insulin/Sensor change, BG Check, Note, Announcement, Question, Exercise, Battery change, `<none>` | timestamp 0 → drop | :304 | a |
| T16 | OpenAPS Offline | timestamp 0 → drop | :334 | a |
| T17 | Combo Bolus | timestamp 0 or no `enteredinsulin` → drop | :365-366 | a |
| T18 | any other eventType | dropped (falls through to `return null`) | :394 | b (AAPS vocabulary) |

That makes 24 `return null`s: the 23 listed in T3–T17 plus :394.

### 1.2 Treatments and entries: processor (IDP)

| # | collection / kind | guard | line | class |
|---|---|---|---|---|
| P1 | entries `sgv` | dropped when dated ≥ 1 min ahead of the phone clock, or not newer than the previous reading in the batch; debug log | IDP:114-118 | c (time) + client ordering |
| P2 | treatments, any | no date → skipped (`?: continue`) | IDP:158 | a |
| P3 | Temporary Target, duration > 0 | dropped when `targetBottomAsMgdl()` or `targetTopAsMgdl()` is outside `TT_RANGE_MGDL` (72..180.16), or bottom > top; debug log only | IDP:172-180; C:41 | range = **b**; bottom > top = **a** |
| P4 | every kind | accepted only if the user's per-kind "accept from NS" preference (or AAPSCLIENT, or full sync) allows | IDP:163-232 | b (client preference) |
| P5 | Announcement | raised as a notification only within 60 min of its time | IDP:212-214 | b |
| P6 | profile store | accepted only if newer than the last local change, or `createdAt % 1000 == 0` ("edited in NS") | IDP:282 | b (sync policy) |

### 1.3 Units handling

| # | where | behaviour | line | class |
|---|---|---|---|---|
| U1 | `NsUnits.fromString` | only exactly `"mmol"` is mmol; **anything else, including `"mmol/L"`, is mg/dL** | `core/nssdk/.../localmodel/entry/NsUnits.kt:10` | a (the hazard Nightscout can remove) |
| U2 | `NSTreatment.asMgdl` | mmol × **18** (not `MMOL_TO_MGDL` 18.01559, C:8) | `core/nssdk/.../localmodel/treatment/NSTreatment.kt:31-36` | client detail |
| U3 | `GlucoseUnit.fromText` (profiles) | same exact-match-else-mg/dL rule | `core/data/.../model/GlucoseUnit.kt:18` | a |
| U4 | `pureProfileFromJson` | a profile **without** `units` is rejected, precisely because U3 would read it as mg/dL ("out by a factor of 18", per the comment) | `core/objects/.../extensions/ProfileSwitchExtension.kt:76-86` | a |
| U5 | AAPS upload of TT | always `units: "mg/dl"`, values in mg/dL | `plugins/sync/.../extensions/TemporaryTargetExtension.kt:33-35` | — |

Consequence (U1 + U2 + P3): a TT stored as `units: "mmol"` with mg/dL numbers (the careportal double label, 99.09) comes out at ~1784 mg/dL and is dropped by P3. A TT stored correctly in mmol/L but spelled `"mmol/L"` is read as 5.5 mg/dL and also dropped by P3. Neither drop leaves any trace outside AAPS's debug log.

### 1.4 Profiles, other collections

| # | guard | line | class |
|---|---|---|---|
| R1 | schedules (`sens`, `carbratio`, `basal`) missing, empty, unreadable, or not on whole hours → profile invalid | `core/objects/.../extensions/BlockExtension.kt:151-163` | a (hour alignment is AAPS's own model: b) |
| R2 | `target_low`/`target_high` different lengths or times, not on whole hours → invalid | BlockExtension.kt:180-198 | a / b |
| R3 | Profile Switch: profile not found locally and no `profileJson` → drop | `plugins/sync/.../extensions/ProfileSwitchExtension.kt:21-22` | a |
| R4 | Effective Profile Switch: unparseable `profileJson` → drop | `.../extensions/EffectiveProfileSwitchExtension.kt:17` | a |
| R5 | entries: `sgv` missing or `type != "sgv"` → not a reading | `core/nssdk/.../mapper/SvgMapper.kt:17-18` | a |
| R6 | entries `mbg`: only `isCalibration == true` with `date`, `mbg` and `sensorMgdlAtPairing` | `core/nssdk/.../mapper/MbgMapper.kt:19-23` | b (AAPS calibration contract) |
| R7 | food: `type` other than `"food"` → drop | `core/nssdk/.../mapper/FoodMapper.kt:43` | a |
| R8 | devicestatus: no `created_at` → skip; older than the last processed → skip; pump `clock` likewise | `plugins/sync/.../data/NSDeviceStatusHandler.kt:134-135, 143-144` | c / client ordering |

### 1.5 AAPS policy limits (controller side, not ingestion)

| limit | value | line |
|---|---|---|
| `TT_RANGE_MGDL` / `TT_RANGE_MMOL` | 72..180.16 / 4.0..10.0 | C:41-42 |
| `HardLimits.LIMIT_TEMP_MIN_BG`, `_MAX_BG`, `_TARGET_BG` | 72..180.16, 72..270, 72..200 | `core/interfaces/.../utils/HardLimits.kt:33-35`, applied in `plugins/aps/.../openAPSSMB/OpenAPSSMBPlugin.kt:347-349` |
| `ACTION_DURATION` | 0..7 days | C:25 |

### 1.6 Comparable guards in Trio and Loop/NightscoutKit (read, cheap to find)

| client | guard | line | compared with AAPS |
|---|---|---|---|
| Trio | TT fetch is API v1 `find[eventType]=Temporary+Target&find[duration][$exists]=true` | `Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:253-265` | duration required (like T4) |
| Trio | stored TT skipped if one exists at the same `createdAt`, or if it is a cancel | `Trio/Sources/APS/FetchTreatmentsManager.swift:52-53` | dedup, not validation |
| Trio | **reads no `units` on TT**; values taken as mg/dL | `Trio/Sources/Models/TempTarget.swift` (no units field) | a mmol-labelled 5.5 is read as 5.5 mg/dL |
| Trio | targets **clamped** to 80..200 mg/dL "in case pump is set too low, or units are wrong" (oref0's rule) | `Trio/Sources/APS/OpenAPSSwift/Profile/Targets.swift:67-80` | clamps where AAPS drops; no bottom ≤ top check (:46-51) |
| Trio | CGM values below 39 clamped to 39; oref ignores glucose ≤ 38 | `Trio/Sources/APS/Storage/GlucoseStorage.swift:144-166`; `.../DetermineBasal/DetermineBasal+Helpers.swift:58` | physical floor (a) |
| NightscoutKit | treatment parsed only with `_id`, a known `eventType`, `timestamp`, `enteredBy` | `Sources/NightscoutKit/Models/Treatments/NightscoutTreatment.swift:83-93` | like T3/T18 |
| NightscoutKit | units known only as exactly `"mmol/L"` / `"mg/dL"`; BG Check without one of those → dropped | `.../Treatments/NightscoutTreatment.swift:59-62`; `.../BGCheckNightscoutTreatment.swift:29-30`; `.../MealBolusNightscoutTreatment.swift:34-35` | **the opposite spelling set to AAPS's U1** |
| NightscoutKit | override `correctionRange` built with `ClosedRange(uncheckedBounds:)`: no lower ≤ upper check | `.../Treatments/OverrideTreatment.swift:50-51` | missing (a) |
| NightscoutKit | glucose entry needs `_id`, `date`, and `sgv` or `mbg` | `Sources/NightscoutKit/Models/GlucoseEntry.swift:135-165` | like R5 |
| Nightscout careportal (client) | TT targets 4..18 mmol/L (72..324 mg/dL), bottom ≤ top, both present | `lib/client-core/careportal/validate.js:31-62` | Nightscout's own policy, client-side only |
| Nightscout server (read) | TT `units == 'mmol'` → ×18.016; otherwise a target < 20 is taken as mmol | `lib/data/ddata.js:466, :478` | the plausibility rule, applied on read |

So the hazards and their spread across clients are:

- **Units spellings split.** AAPS knows `mmol`/`mg/dl`, NightscoutKit knows `mmol/L`/`mg/dL`, and Trio reads no units on a TT. Each one silently reads the other spellings as mg/dL or ignores them.
- **Out-of-range targets.** AAPS drops them, Trio clamps them, Nightscout's own chart rescales them.
- **Bottom > top.** AAPS checks it; Trio and NightscoutKit don't.

## 2. Classification and what moves

| class | meaning | goes where | items |
|---|---|---|---|
| **a** structural/physical | true for every client: numbers are finite, a range is ordered, units come from a known set, values are plausible for their declared units, durations are ≥ 0, a timed record has a time | **Nightscout write path**, staged (§4) | T3–T6, T8–T11, T13, T15–T17, P2, P3's bottom ≤ top, U1/U3 (canonical spelling), U4 (profile needs units), R5, R7, NightscoutKit's override ordering |
| **b** controller policy | a range or vocabulary one controller chose | **stays in the controller**. Nightscout may *surface* it from the controller's declaration (§3.5) but doesn't enforce it | P3's 72–180.16, HardLimits, Trio's 80–200 clamp, careportal 4–18 mmol, T18's vocabulary, R1's hour alignment, R6, P4–P6 |
| **c** time sanity | readings dated ahead of the server clock | Nightscout, as **flag/announce** first. It ties to BF-95 and the sticky-future `srvModified` candidate (§3.6) | P1, R8 |

The AAPS-specific shapes (T7, T12, T14) are a contract between AAPS and itself. They stay client-side.

## 3. Design

### 3.1 Where validation lives: one rule module, every write path

There isn't one write function today. Treatments reach MongoDB through:

1. `lib/server/treatments.js` `create`/`save`: API v1 POST/PUT, the careportal (through v1), and in-process writers (nightscout-connect, plugins). This file also calls `srvDates.carryForReplace` (BF-122).
2. `lib/server/websocket.js` `processSingleDbAdd` (`insertOne`) and `dbUpdate` (`$set`): the v1 socket (AAPS NSClient v1, xDrip+). It calls `srvDates.stampCreated`/`stampModified` at :677/:396.
3. API v3 `lib/api3/generic/{create,update,patch}`, through `lib/api3/storage/mongoCollection`. It calls `srvDates.next()` at create/insert.js:27, update/replace.js:31 and patch/operation.js:79.

BF-122's "shared write path" is a shared clock (`lib/server/srv-dates.js`) called from each of these, not a shared function. WRITE-CONTRACT ([write-contract spec](../../30-design/tenancy/write-contract-spec-2026-10-07.md) §2) already designs the single function: `lib/storage/write-step.js` `write(intent)`, with per-item outcomes including `refused` + `reason`, and route rules kept above the seam (§2.5). Domain validation belongs there as a rule that runs before target resolution (§2.3 step 1), on the item *as it will be stored*. Its result is `refused` with a reason the route maps to its own status.

**Until the write step exists** (the draft code does this), the rules live in one pure module, `lib/server/write-validation.js`, called at each path's existing validation point:

| path | hook | coverage in the draft |
|---|---|---|
| v1 REST, careportal, in-process | `treatments.js` `checkDomain` before the bulk or single write, on a `prepareData` copy | yes |
| v3 POST (insert and dedup-replace) | `create/validate.js` → `opTools.validateDomain` | yes |
| v3 PUT | `update/validate.js` | yes |
| v3 PATCH | `update/validate.js` with the merged record, only when the patch sends a rule field | yes |
| socket `dbAdd` | `processSingleDbAdd` before `stampCreated` | **no** (next step) |
| socket `dbUpdate` / `dbUpdateUnset` | needs the stored record to merge: one read | **no**. This is the case the write step closes |

**Why v1 checks the prepared copy.** v1 `prepareData` deletes `units` from any treatment without a glucose value (`lib/server/treatments.js:566-570`). The ordinary careportal mmol/L flow therefore stores mg/dL numbers unlabelled, which every reader takes correctly as mg/dL. Checking the record as sent would refuse that working flow. Checking it as stored refuses only the double label (measured, §5).

### 3.2 Rejection: v3 vs v1, on the ladder

| step | v3 | v1 REST | v1 socket |
|---|---|---|---|
| 0 status quo (`WRITE_VALIDATION=off`, default) | unchanged | unchanged | unchanged |
| 1 announce (`log`) | stored; one log line naming rule and field (never values) | same | same (once covered) |
| 2 opt-in reject (`reject`) | **400** `{status, message: "Temporary Target: <rule message>"}`; nothing stored | single item or PUT: **400** (it was a 500 "Mongo Error" path). Batch (**decided 2026-10-25, D2**): the valid items are stored; the reply keeps one object per submitted item, in order, and a refused item's object has no `_id` and a `refused` member; there is a `Warning: 299` header; a batch whose items are all refused gets 400 | reply `{result: 'refused', reason}` (proposed; today a failed dbAdd replies `[]`) |
| 3 reject by default (a major) | default `reject` | default `reject` | default `reject` |

Rules that only *normalise* (the units spelling) apply from step 2. Step 1 stores bytes unchanged, so an operator can turn `log` on without anything changing for any client.

**What a refusal does to the uploader** (corrected 2026-10-25 from the D3 study, §D3). The earlier text said here that a refusal reaches the uploader's own error path. For most clients it doesn't:

- Under `reject`, most clients lose a refused record silently. AAPS v3 drops a 400 on treatments, entries and food. Loop records a refused v1 slot as uploaded. xDrip+ PUT drops the item and every later one in that pass. nightscout-connect moves its bookmark past the item.
- A whole-batch 400 wedges Loop and Trio. Each resends the full batch on every trigger with no cap, and Trio stops its pipeline for up to 24 hours.
- No client reads the `refused` member or the `Warning` header.
- `log` is the only mode with no effect a client can see.

The D2 reply shape (200, one slot per item, refused slots without `_id`) is the shape these clients tolerate best, so it stays. The cost of `reject` is data loss with no visible error, not a wedged uploader. That decides the ladder: `reject` stays opt-in until the clients can see a refusal. Reaching that needs either clients that read `refused`, or a refusal channel they already surface (§D3, last paragraph).

The refusal messages avoid the two 400 texts AndroidAPS's nssdk string-matches (`NSAndroidClientImpl.kt:388-400`):
- "Bad or missing utcOffset field" makes AAPS resend with `utcOffset: 0`;
- "cannot be modified by the client" marks the record as never uploadable.

A unit test checks every rule's message against both.

### 3.2a What v1 uploaders read from the POST reply (why D2's shape)

All read, not run, at the pins of the upload-refusal note.

| client | what it reads from the reply | with the D2 shape |
|---|---|---|
| Loop (NightscoutKit `NightscoutClient.postToNS`, `NightscoutClient.swift:479-505`, `4ec9fd1`) | a JSON array with exactly as many objects as it sent, otherwise the upload fails; `_id` by position, and an object without `_id` is recorded as `"NA"` and treated as uploaded | count and order are kept, so stored items get their ids; a refused item is treated as uploaded and not retried |
| xdripswift (`NightscoutSyncManager.swift:1788-1830`, `TreatmentNSResponse.swift:61-62`, `c268542e`) | parses the array, skips objects without `_id`, matches the rest by content | stored items are matched; a refused item stays not-uploaded and is resent at the next sync |
| xDrip+ (`NightscoutUploader.java:858-873`, `1ed760048`) | the HTTP status only; on 2xx every item in the batch is marked done | a refused item is marked done |
| Trio (`NightscoutAPI.swift:328-335`, `0b29cd534`) | the HTTP status only | unchanged |
| AndroidAPS | does not use v1 REST POST for treatments (NSClientV3 uses API v3, one record per request) | — |

Rejected alternatives: dropping refused items from the array breaks Loop's count check, so Loop would
retry the batch indefinitely; refusing the whole batch was the previous draft, replaced by D2.

### 3.3 Already-stored invalid records, on read

**Don't hide them.** Clients already apply their own rules (AAPS drops, Trio clamps, the Nightscout chart rescales), and hiding a record would make Nightscout's view diverge from what the uploader sent. The options for a later step are:

- **(R1) flag on read.** v3 read/search/history adds `validation: [{rule, field}]` to a record that breaks a rule, computed on read and not stored. That's cheap, it needs no migration, and a client can choose to show it. v1 stays as it is.
- **(R2) report.** An admin or report page (or an `nsprobe`-style tool) lists stored records that break rules, so a user can fix them through PATCH. The draft code keeps PATCH of other fields allowed on such records.
- **(R3) migrate.** Rewrite stored records. **Not recommended**: it changes history other clients have already synced, and `srvModified` would move them all into every v3 history cursor at once.

The recommendation is R1 and R2, after step 2 has soaked.

### 3.4 Units normalisation at write

Two options:

- **(N1) canonical spelling only** (the draft, reject mode only, TT only): `mmol/L`, `mmol/l` → `mmol`; `mg/dL`, `mgdl` → `mg/dl`. That's Nightscout's own spelling (ddata.js:466, careportal) and AAPS's (U1), so AAPS starts reading correctly-labelled mmol/L TTs that it drops today. **Caution:** NightscoutKit matches only `mmol/L`/`mg/dL` (§1.6). Normalising BG Check or Meal Bolus `units` would make Loop drop records it reads today. N1 must stay TT-only, or the read path must serve per-client spellings, until NightscoutKit is changed to accept both.
- **(N2) store mg/dL plus the original.** Store `targetTop`/`targetBottom` in mg/dL with `units: 'mg/dl'` and keep `{unitsOriginal, targetTopOriginal, ...}`. Every client then reads mg/dL, which is what AAPS uploads and what Trio assumes. This changes stored values, so it's a major-release item, and a client that re-reads its own record would see different numbers. It also needs the conversion constant decided (AAPS uses 18 in U2, Nightscout uses 18.016 in ddata.js, AAPS C:8 uses 18.01559). Recommended only with the write step and a quirk-registry entry (D20).

### 3.5 Class (b): surface, don't enforce

The registration spec already has the slot. A typed declaration carries `unit` and `range` per field (`docs/30-design/platform/spec/registration.md` G2, line 75). The controller-settings snapshot (`records.md` R5) carries the controller's settings with `product`/`version`. A controller that declares "temp target range 72..180.16 mg/dL" in its registration lets Nightscout:

- tell the person entering a TT in the careportal "AndroidAPS on this site ignores targets outside 72–180 mg/dL". The page states what the controller does and advises nothing.
- flag on read (R1) `outsideDeclaredRange: {product, range}`.

Nightscout never refuses on a declared range. The controller owns it, and two controllers on one site can disagree.

### 3.6 Class (c): time

P1 drops a reading dated ≥ 1 min ahead. In Nightscout, a future-dated record is already handled on read: `sandbox.lastEntry`'s `notInTheFuture` and BF-95. The `srvModified` work (BF-95's 2026-10-25 measurement) found a related write-side hazard, filed as BF-181: a client-supplied future `srvModified` stored by 15.0.8 carries forward and stays sticky across restarts. That one is server-owned, so a write rule can apply to it outright. The *reading's* `date` is client data. The proposal is to announce (`log`) readings that arrive more than a tolerance ahead of the server clock, and flag them on read (R1). Refusing them isn't proposed, because a refused CGM reading is lost data and the uploader's clock is the defect. This feeds the BF-95 decision (its option 3).

## 4. Calendar (proposed; offsets are for maintainers and the community to decide)

| release | step |
|---|---|
| 16.0.x minor | `WRITE_VALIDATION` off/log/reject for TT on v1 REST and v3 (the draft); release notes ask operators to try `log` |
| 16.x | socket dbAdd/dbUpdate covered; the rule set extended to class (a) for Temp Basal (T9–T11), timed treatments (T3/T15), profile `units` (U4), entries `sgv` finite and > 0 |
| with the write step (WRITE-CONTRACT) | the rules move into `write(intent)` as `refused` outcomes; read flag R1 |
| 17.0.0 (major) | default `log` → `reject` for the rules that soaked clean; any N2 decision |

## 5. Measured (draft code, MongoDB 8.0.34, Node v22.23.4)

The default-off behaviour matches dev's for every shape tested. On dev `b29f1bf7`, v3 and v1 store the double label, a units value spelled `mmol/L`, and bottom > top exactly as sent. With `reject`, v3 returns 400 and v1 returns 400, nothing is stored, and the careportal mmol/L flow without a glucose value is still accepted.

Tests on the branch (re-read from the lane's logs): `tests/api.treatments-write-validation.test.js`, integration, 22 passing on its own; `tests/write-validation.test.js`, unit, 10 tests (the unit tier 1227 passing); a full integration run 1993 passing and 1 failing, an `API3 UPDATE` before-all hook timeout of the kind seen elsewhere under load (not attributed to the branch). Red controls, as reported by the lane: with the batch made all-or-nothing the mixed-batch test fails (`expected 200 "OK", got 400`); with refusal objects left out of the reply it fails on the length Loop requires (`expected 2 to be 3`); a message containing "cannot be modified by the client" fails the unit test; on `dev`'s `lib/` 12 of the first 20 integration tests fail (`expected 400, got 201/200`); with the units-plausibility rule disabled exactly the 6 double-label cases and the `log` case fail; with the default set to `reject` the 5 default-off tests fail.

## 6. Decisions needed (maintainer)

- **D1** Decided 2026-10-25 (maintainer): `WRITE_VALIDATION=off|log|reject`, default `off`.
- **D2** Decided 2026-10-25 (maintainer): store the valid items and report the refused ones in a reply shape old clients still read (the per-client table is §3.2a).
- **D3** Evidence in (§D3). It shows `reject` loses records silently for most clients. Still to decide: whether step 3 (reject by default) stays on the calendar at all. Either way it is blocked on a refusal the person can see, not on a date.
- **D4** Decided 2026-10-25 (maintainer): refuse, with a message naming the field and the units to send. The careportal source fix is separate (alarms lane).
- **D5** N1 vs N2, and the conversion constant.
- **D6** The plausibility thresholds (30 mmol/L, 20 mg/dL). The read-side fallback at ddata.js:478 already uses 20.

## D3. What uploaders do when a write is refused (evidence, 2026-10-25)

Source: the upload-400 study, written up with pins, citations and run-or-read marks in [upload-refusal-client-behaviour-2026-10-25](../remedial/upload-refusal-client-behaviour-2026-10-25.md). The AAPS nssdk part was run on the JVM, its sync plugin was read, nightscout-connect was run in process, oref0 was run against a stub, and the rest was read.

| client | 400 on one record / a whole batch | refused slot inside a 200 (D2 shape) | other non-2xx |
|---|---|---|---|
| AndroidAPS v3: treatments, entries, food | logged and **dropped**; the cursor moves on | n/a (v3 is one record per request) | any other 4xx, or an exception, **blocks** that kind's queue, with no backoff and no cap; 500 → 3 retries within the call |
| AndroidAPS v3: devicestatus, profile store | block on any non-2xx | n/a | block |
| Loop (NightscoutKit) | a whole-batch 400, or a shorter array, **wedges** that data type: the full batch is resent on every trigger, with no cap | recorded as `"NA"` and counted as uploaded: **lost**, and its later edits and deletes are skipped | needs exactly 200 |
| Trio | any non-2xx stops the pipeline for up to 24 h and resends chunks already accepted | 2xx marks everything uploaded; the body isn't read: **lost** | same as 400 |
| xDrip+ (Android) | entries: blocked for up to 7 days; treatments go by PUT one at a time, and a failure drops that item **and every later one in the pass** (an upstream xDrip+ defect) | n/a for treatments (PUT) | — |
| xDrip4iOS (xdripswift) | a refused BG batch blocks the cursor for up to 7 days | stays pending and is resent (within the latest-50 window) | — |
| nightscout-connect (in process) | an all-refused frame is retried with backoff | the bookmark moves past the item: **lost** | — |
| oref0 | never detects a 4xx or 5xx | — | — |

No client reads `refused` or the `Warning` header.

What this means for the design:
1. `log` is the only step with no effect a client can see. It is safe to recommend to operators now.
2. With `reject`, the D2 partial-batch shape is the one that wedges nobody. A refused record is still lost for AAPS, Loop, Trio and nightscout-connect, and retried indefinitely by xDrip4iOS. An all-refused batch (400) wedges Loop and Trio.
3. Making `reject` the default would turn a currently-misread record into a silently-missing one for most users. It needs a refusal the user can see first. Options:
   - clients read `refused` (upstream asks to AAPS, NightscoutKit, Trio and xDrip);
   - Nightscout raises its own notice (an announcement or admin notification) when it refuses a record, so the person sees it on the Nightscout site even though the uploader doesn't;
   - `reject` is never made the default, and `log` plus the read-side flag (§3.3 R1) carry the protection.
