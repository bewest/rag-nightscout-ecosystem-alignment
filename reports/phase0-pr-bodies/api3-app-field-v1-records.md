<!-- Body for bf/api3-app-field-v1-records at df6c04bc (tree 335fab7d), from origin/dev e3adc91d, 2026-09-26. This comment is hidden on GitHub. -->
API v3 can write to a treatment that was created through API v1, such as a careportal entry. Before this change, a v3 write that deduplicated onto such a record, replaced it, or patched it the way AndroidAPS does was refused with 400 "Field ... cannot be modified by the client". Fixes BF-136. One commit on `dev` `e3adc91d`.

## What changes for you

*Plain-language summary for people running their own Nightscout site for themselves or a family
member. Nightscout is not a medical device and none of this is medical advice. If the carbs,
boluses or temporary targets in Nightscout do not match what your app shows, go by your app and
your meter, and talk to your care team before relying on the Nightscout numbers.*

A few words used below:

- **Treatment**: a record of something you did or entered, such as carbs, a bolus, a temporary
  target or a note.
- **Careportal**: the form on the Nightscout website for entering treatments. It saves them
  through Nightscout's older interface, API v1. Loop, Trio, xDrip+ and several other apps also save
  through API v1.
- **API v3**: Nightscout's newer interface. AndroidAPS (AAPS) uses it when its "NSClient v3"
  plugin is selected.
- **Upload**: AAPS sending one of its records to your Nightscout site.

**Who is affected:** mostly AndroidAPS users on NSClient v3 whose Nightscout also holds treatments
that were entered another way (the careportal or another app). Anyone else writing through API v3
to those records is affected in the same way.

**What was wrong:** Nightscout's API v3 refused to change a treatment that had been saved through
API v1, because that treatment is missing some bookkeeping fields API v3 expects (which app wrote
it, and a few others). There are two cases:

- **AAPS changes a treatment it got from Nightscout.** For example, a temporary target entered on
  the Nightscout website that AAPS then changes. Nightscout refused the change. AAPS does not retry
  after that answer, so Nightscout kept the old version and did not tell you. Your followers,
  reports and the Nightscout website went on showing the old record. Deleting a record in AAPS goes
  a different way and was not affected.
- **AAPS uploads an entry at exactly the same time, to the millisecond, as an existing entry of the
  same type** (for example two "Meal Bolus" entries). Nightscout treats that as the same entry sent
  again. It tried to save the AAPS version over the existing one, and that save was refused. AAPS
  skipped the entry, so it never reached Nightscout. The usual case is an entry that already came
  from AAPS once, for example through an older AAPS version.

**What this change does:** those writes are now accepted. AAPS changes to careportal records reach
Nightscout, and the AAPS version of a same-time entry is saved.

**Important:** in the same-time case, the AAPS version **replaces** the existing entry. It does
not add a second one. If the two were really different meals, for example a careportal entry of 20
g and an AAPS entry of 30 g at the identical millisecond, Nightscout keeps only the AAPS entry (30
g), and the careportal entry's note and "entered by" are gone. Before this change, Nightscout kept
the careportal entry and lost the AAPS one. Entries of different types (AAPS calls anything under
12 g "Carb Correction" and 12 g or more "Meal Bolus") are never merged, so both stay. An exact
millisecond match between two separate meals is unlikely, because careportal times are whole
minutes and AAPS times are not. How Nightscout should handle two different entries with the same
time is a separate open question (BF-121), and this change does not answer it.

**Do you need to do anything?** No. Entries that AAPS skipped in the past are not sent again
automatically.

## Technical detail

### The defect

`lib/api3/generic/update/validate.js` (used by PUT, PATCH and the deduplicating branch of POST)
refuses any write that sends one of `identifier, date, utcOffset, eventType, device, app,
srvCreated, subject, srvModified, modifiedBy, isValid` with a value other than the stored one. It
compared `doc[field] !== storageDoc[field]`, so a field that the stored record **does not have**
counted as a change. A treatment stored through v1 has no `app`, `device` or `isValid`, and a
careportal treatment has no `date` either (stored fields: `_id, carbs, created_at, enteredBy,
eventType, notes, utcOffset`). The results, identical on `v15.0.8` `92d08342` and `dev` `e3adc91d`:

- **POST without `identifier`** that deduplicates onto a v1 record (`create/operation.js:52`,
  fallback key `created_at` + `eventType`, `setup.js:95`): 400 `Field date ...` for a careportal
  record, 400 `Field app ...` for a v1 record that carries `date`.
- **PUT** to a v1 record: 400 `Field date ...` (careportal record), whether or not `app` is sent.
  v3 PUT requires `app` (`validateCommon`), and sending it hit the immutable check. PUT could not
  change such a record at all.
- **PATCH**: `{carbs}` alone works. `{isValid: true, ...}`, which AndroidAPS sends on every update
  (`CarbsExtension.kt`, `TreatmentMapper.kt:407`), answers 400 `Field isValid ...`. `{app}`
  answers 400 `Field app ...`.

### The rule

A field the stored record lacks is accepted when it states nothing the record contradicts
(`isSameAsStored` in `validate.js`). The rule for each field in the list:

| field | when the stored record lacks it | why |
|---|---|---|
| `app`, `device` | the first value is accepted | provenance that v1 does not record. A value already stored still cannot be changed |
| `isValid` | `true` accepted, `false` refused | a record without `isValid` is valid. `false` is a deletion, which stays with DELETE and its permission |
| `date` | accepted only if equal to the record's `created_at` instant (`col.fallbackDateField`) | the record's time comes from `created_at`. Any other value would move the record. Collections whose fallback field is `date` itself (entries) are unchanged |
| `identifier` | not applicable | `normalizeDoc` always sets it (it falls back to `_id`). The dedup exception is unchanged |
| `utcOffset`, `eventType` | compared as before | v1 has stored `utcOffset` since 2019 (`treatments.js:491`). `eventType` is part of the dedup key. Neither is needed for this defect |
| `srvCreated`, `srvModified`, `subject`, `modifiedBy` | compared as before | server-managed. On PUT and PATCH, `resolveDates` fills `srvCreated`/`srvModified` before validation. PATCH does not overwrite `subject`, so accepting it would let a client set it |

Whether `app` is required: v3 still requires `app` on POST and PUT (`validateCommon`). A PUT without
`app` now answers `400 Bad or missing app field`, the same as any v3 PUT, instead of the immutable
field message.

### What the deduplicating POST does with different amounts

v3's fallback deduplication matches on `created_at` + `eventType`, not on amounts, and replaces the
whole document. AndroidAPS sets `eventType` from the amount (`< 12 g` is Carb Correction, otherwise
Meal Bolus). Measured with a careportal v1 record of *a* g and an AndroidAPS-shaped v3 POST of *b* g
at the same millisecond:

| a → b | v15.0.8 and `dev` | this branch | stored afterwards (this branch) |
|---|---|---|---|
| 20 → 20 | 400 `date` | 200 dedup | 1 record, 20 g, `app` AAPS, careportal notes gone |
| 20 → 30 | 400 `date` | 200 dedup | 1 record, **30 g**, careportal 20 g record replaced |
| 45 → 60 | 400 `date` | 200 dedup | 1 record, 60 g |
| 5 → 5 | 400 `date` | 200 dedup | 1 record, 5 g |
| 8 → 10 | 400 `date` | 200 dedup | 1 record, 10 g |
| 20 → 5 | 201 insert | 201 insert | 2 records (Meal Bolus 20 g and Carb Correction 5 g) |
| 5 → 20 | 201 insert | 201 insert | 2 records |

The replacement is v3's deduplication behaving as designed. It was unreachable against v1 records
because of this defect. BF-121's chosen fix leaves v3 deduplication as it is. The new test
`a deduplicating POST with other carbs replaces the whole v1 record` pins this behaviour, so a
later change to it will show up in the tests.

### Tests

`tests/api3.v1-record-immutable-fields.test.js` (new, 16 tests). v1 records are written through
`ctx.treatments.create`, which is the v1 POST path:

- the careportal-shaped record has no `date`, `app`, `device`, `isValid` or `identifier`.
- POST without identifier deduplicates onto it (200, one record, `app` AAPS), and onto a v1 record
  that carries `date`. With other carbs it replaces the record. With another `eventType` both stay.
- PUT with `app`, and with `app` + `device`: 200. PUT without `app`: 400 `Bad or missing app field`.
- PATCH in the AndroidAPS update shape (`identifier`, `eventType`, `isValid: true`, `carbs`): 200.
  PATCH `{app}`: 200. PATCH `date` equal to `created_at`: 200.
- Controls: v3 create, PUT and PATCH as usual. Changing an existing `app` or `device` through PUT,
  PATCH or a deduplicating POST: 400. On a v1 record, PATCH `isValid: false`, `srvCreated`,
  `srvModified`, `subject`, `modifiedBy`, `identifier`, another `date` or `utcOffset`, and PUT with
  another `date`: 400, and the record is unchanged. A deleted v1 record: 410.

On `dev` `e3adc91d` 9 fail with the original messages (`Field date`, `Field app`, `Field isValid
... cannot be modified by the client`). The 7 controls pass on both. No existing expectation
changed.

Full suite on `df6c04bc`: **3186 passing, 0 failing, 3 pending** (`npm test` on a freshly dropped
database, Node 22.23.2, MongoDB 7.0.43 read from the server). `dev` `e3adc91d` is 3170/0/3 on the same form. The difference is the 16 new tests.

Probe `tools/lab/triage-2026-09/api3-app-field.js` (alignment repo) boots the server: exit 1 on
`v15.0.8` and `dev` (3 of 13 arms succeed), exit 0 on `df6c04bc` (13 of 13), with its 15 controls
passing on all.

### Break-its

Each hunk of `isSameAsStored` was reverted in turn, with the new tests:

- `app`/`device` refused when absent: 6 fail (the three dedup tests, both PUT tests, PATCH app).
- `isValid: true` refused when absent: 4 fail (three dedup tests, PATCH AndroidAPS shape).
- `date` refused when absent: 6 fail (careportal dedup, the other-carbs dedup, both PUT tests, PUT
  without app, PATCH date).
- `isValid` accepted with any value: the controls test fails at `isValid: false`.
- other fields accepted when absent: the controls test fails at `subject`.
- a stored value made overwritable: 3 control tests fail (v3 app/device, v1 app, v1 device).
- `date` accepted with any value: the controls test fails at another `date`.

### With BF-122 (`bf/v1-writes-v3-history` `718efddc`)

`718efddc` touches `create/insert.js`, `update/replace.js`, `patch/operation.js` and
`delete/operation.js`, but not `validate.js`. A trial merge is clean. After it, v1 records carry
`srvCreated`/`srvModified`, which are server-managed and compared as before. Full suite on the
merge: **3212 passing, 0 failing, 3 pending**. The probe gives exit 0 on the merge.

## Client impact

Read, not run (`externals/AndroidAPS` `7e1d537d49`):

- `NSAndroidClientImpl.createTreatment` recognises "cannot be modified by the client" and returns
  the 400 without an identifier. The comment there reads "not possible to upload".
  `NSClientV3Plugin.dbOperationTreatments` logs `◄ FAIL` for 400 and returns `true`
  (`NSClientV3Plugin.kt:1019`, then `:1088`). `DataSyncSelectorV3` then advances the upload cursor
  (`confirmLastCarbsIdIfGreater`, `DataSyncSelectorV3.kt:256`). The record keeps no Nightscout id
  and is not sent again unless it changes. Updates (`nsUpdate`, a PATCH) go the same way.
- `updateTreatment` sends a PATCH with `isValid` (true) and `eventType`, and without `date` and
  `utcOffset`. So an AndroidAPS change to any record that lacks `isValid`, which is every record
  written through v1, was refused. Deletions use DELETE and were not affected.
- After this change those writes succeed. AndroidAPS stores the returned identifier for the
  deduplicated record (`result.identifier`). Nothing needs to change in AndroidAPS.

Other v3 writers (nightguard, xDrip+ in v3 mode) write through the same validator. Changing a value
that is already stored is refused exactly as before.
