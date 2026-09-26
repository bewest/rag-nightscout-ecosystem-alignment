<!-- Draft body for branch bf/activity-date-coercion at 20c197bb (one commit on dev e3adc91d, tree bff28663). Not opened. BF-106. -->
Numeric `date` and `sgv` filters on API v1 `/activity`, and numeric `sgv` filters on API v1 `/devicestatus`, match the stored records again, as they did on 15.0.8.

## What changes for you

*Plain-language summary for people running their own Nightscout site for themselves or a family
member. Nightscout is not a medical device and none of this is medical advice. If your data
looks wrong, check it with your care team before relying on it.*

A few words used below:

- **Record**: one saved item, such as a glucose reading, a treatment, or an activity record
  (steps, heart rate and similar data some phone and watch apps upload).
- **Filter**: part of a request an app sends to ask Nightscout for only some records, for example
  "activity records after 9 o'clock".
- **API v1**: the older, most widely used way apps read and write Nightscout data.

### What was wrong

On the development version that will become Nightscout 15.0.9, an app that asked for activity
records by their numeric time (`date`) or by a glucose value (`sgv`) got an empty answer, even
when matching records were saved. The request still looked successful, so the app could not
tell the records were missing. The same happened when asking for device status reports by a
glucose value. Nightscout 15.0.8, the current release, is not affected.

### What this change does

Those filters find the saved records again, the same way 15.0.8 found them. Nothing else about
how filters are read changes: text stays text, so a filter on a name made only of digits still
matches that name.

No app we looked at sends these particular filters (see "Client impact"), so most sites will see
no difference. Your saved data is not changed.

## Technical detail

### The defect

Every query-string value arrives as text. On 15.0.8, `lib/server/query.js` `default_options`
gave any storage module that set no `walker` the default `{ date: parseInt, sgv: parseInt }`.
`activity` and `devicestatus` set none and inherited it.

The schema-driven coercion (#8737, BF-03) names a `collection` on every v1 storage module and
types fields from `lib/server/query-coercion.json`. When a collection is named, `dev` replaced
the default with `{}`:

```js
opts.walker = opts.collection ? { } : { date: parseInt, sgv: parseInt };
```

The `activity` schema types no field (its entry is `{}`) and the `devicestatus` schema types
`date` but not `sgv`. So `find[date][$gte]=<ms>` and `find[sgv]…` on `/api/v1/activity`, and
`find[sgv]…` on `/api/v1/devicestatus`, reached MongoDB as strings, matched no stored number,
and answered 200 with no records. `DELETE /api/v1/devicestatus/?find[sgv][…]` builds its filter
the same way, so on `dev` it deleted nothing where 15.0.8 deleted the matching records.

`query-coercion.json` is generated in the alignment repo from `specs/nsschema/<collection>.model.json`
by `tools/nsschema/emit/coercion_emit.py` (`make schema-emit`). The activity model is derived
from server code, which writes only `_id` and `created_at`, and the emitter deliberately declares
no field the model does not (`test_activity_has_no_numeric_field_to_coerce`). The table is
therefore correct as a statement of the schema, and this change leaves it untouched; the fix is
in `query.js`, where the numeric default was dropped.

### What the commit does

- `lib/server/query.js:52-64, 73-89`: with a named collection and no `walker`, the default is
  `legacyNumericDefaults(collection)`: `date` and `sgv`, each only if the collection's schema does
  not type it, read with `coercion.toNumber` (the schema's own non-truncating number reading).
  A field the schema types keeps the schema's type. No schema types a top-level `date` or `sgv`
  as text (read from `specs/nsschema/*.model.json`, 2026-09-25), and every other field is left
  as it arrived.
- `lib/server/profile.js:146-152`: profile sets `walker: { }` again. It did so on 15.0.8 and never
  had the default; without this, the change above would start reading profile `date` and `sgv`
  bounds as numbers, which neither 15.0.8 nor `dev` does.
- `treatments` passes its own `walker` and gets no default, as on 15.0.8. `entries` has both
  fields typed by its schema. `lib/authorization/storage.js` names no collection and keeps the
  full 15.0.8 default. `food` has no query path.

### Bound types, per collection

Built with each ref's own `lib/` (`git archive`), by calling each storage module's own
`query_for` (profile: `list_query`) with a `$gte: '100'` bound on 28 field names and reading the
bound's type. Only fields whose type differs are listed. Harness: scratch `fix-106/table.js`
(not committed), run 2026-09-25 on Node 22.23.2.

| collection | 15.0.8 (`92d08342`) → `dev` (`e3adc91d`) | `dev` → this branch (`20c197bb`) |
|---|---|---|
| activity | `date`, `sgv`: number → **string** | `date`, `sgv`: string → number |
| devicestatus | `sgv`: number → **string**; `mills`, `utcOffset`, `srvModified`, `uploaderBattery`: string → number | `sgv`: string → number |
| profile | `utcOffset`, `srvModified`: string → number | none |
| treatments | `date`, `mills`, `duration`, `percent`, `absolute`, `rate`, `utcOffset`, `srvModified`: string → number | none |
| entries | `glucose`, `utcOffset`, `delta`, `srvModified`: string → number | none |

Every number → string change from 15.0.8 to `dev` is closed; every string → number change
(BF-03's intended fixes) is kept. Against 15.0.8, this branch has no field that 15.0.8 read as a
number and this branch reads as text.

### Tests

- `tests/api.activity-date-coercion.test.js` (new, 10 tests, booted server, records seeded
  directly into MongoDB with a marker field): activity `created_at` control; activity
  `find[date][$gte]`, a `$gt`/`$lte` window, an exact `find[date]`, `find[sgv][$gte]`; devicestatus
  `find[sgv][$gte]`, `find[date][$gte]` (schema-typed), a digits-only `device` name matched as
  text, and a bulk `DELETE` by `find[sgv][$gte]` that removes only the matching records; profile
  `find[date]` still compared as text.
- `tests/query.test.js`, new group "the numeric date and sgv default (BF-106)" (8 tests): activity
  bounds are numbers, a fractional bound is not truncated, `$in` elements, other activity fields
  stay text, devicestatus `sgv` number and `date` from the schema, devicestatus text stays text,
  `walker: {}` gives no default, an explicit walker replaces it (treatments `sgv` stays text).
- No existing expectation changed.
- Gate `tools/queue/gates/bf106-activity-date-coercion.js` (alignment repo): `--ref e3adc91d`
  exit 1 ("BF-106 PRESENT … bound is a string"), `--ref 20c197bb` exit 0; its `origin/master`
  control passes in both runs.
- Full suite on `20c197bb`: `npm test`, Node 22.23.2, MongoDB 7.0.43 (version read from the
  server), 2026-09-25: **3188 passing, 3 pending, 0 failing** (3170 on `e3adc91d` + 18 new).

### Break-its

Each fix hunk reverted on its own, both new test files run (48 tests):

| reverted | result | failing tests, with the original symptom |
|---|---|---|
| `query.js` default back to `{ }` | 38 passing, 10 failing | activity date bound / window / exact / sgv (`expected Array [] …`, "records matched by find[date][$gte]" 0), devicestatus sgv (`[]`), DELETE by sgv (all 5 left: nothing deleted), 4 unit tests (`expected '1695600000000' to be 1695600000000`). The `created_at` control, devicestatus `date`, text-field and profile tests stay green, so the failures isolate the default. |
| `profile.js` `walker: { }` removed | 47 passing, 1 failing | profile `find[date]=20210304` finds 0 (the bound became a number) |
| `toNumber` replaced by `parseInt` | 47 passing, 1 failing | "does not truncate a fractional bound": `expected 119 to be 119.5` |

## Client impact

Read from the client corpus under `externals/` on 2026-09-25; not run.

- **Activity writers**: xDrip+ (`xDrip/app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java:936-940,988-992,1036-1040`)
  uploads `type`, `timeStamp`, `created_at`, `bpm`/`steps`/`class`, with no `date` or `sgv`.
  tconnectsync (`tconnectsync/tconnectsync/parser/nightscout.py:77-82`) uploads `activityType`,
  `iob`, `created_at`, `enteredBy`.
- **Activity readers**: cgmsim-lib (`cgmsim-lib/src/load-activity.ts:29-32`) filters by
  `find[created_at][$gte]`; tconnectsync (`tconnectsync/tconnectsync/nightscout.py:114-117`) by
  `find[enteredBy]`, `find[activityType]` and a `created_at` range. Both are text filters and
  are unchanged by this branch.
- No client in the corpus sends `find[sgv]` to `/devicestatus` or `find[date]`/`find[sgv]` to
  `/activity` (grep of AndroidAPS, xDrip, xdripswift, xdrip-js, Trio, LoopWorkspace, LoopFollow,
  LoopCaregiver, NightscoutKit, nightguard, oref0, openaps, nightscout-connect,
  nightscout-reporter, DiaBLE, cgmsim-lib, nightscout-librelink-up, share2nightscout-bridge,
  minimed-connect-to-nightscout, tconnectsync, glooko2nightscout, nocturne, mobile-ios). Filters
  built at runtime, reports and custom scripts are not visible to a source read.
- No client gets worse: the only bounds that change type are the three that 15.0.8 already read
  as numbers.
