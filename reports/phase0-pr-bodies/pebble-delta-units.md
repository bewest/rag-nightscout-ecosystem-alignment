<!-- Body for bf/pebble-delta-units at aa224c69 (tree 857eef35), from origin/dev e3adc91d, 2026-09-25. This comment is hidden on GitHub. -->
`/pebble` returns the delta (`bgdelta`) in the same units as the reading (`sgv`) when a client asks an mmol/L site for mg/dL. Fixes BF-128 (issue #6220). One commit on `dev` `e3adc91d`.

## What changes for you

*Plain-language summary for people running their own Nightscout site for themselves or a family
member. Nightscout is not a medical device and none of this is medical advice. If a number on a
watch or display looks wrong, check it against your meter and talk to your care team before
relying on it.*

A few words used below:

- **`/pebble`**: an older address on your Nightscout site that watch faces and small displays use
  to get the latest glucose reading. It was first written for Pebble watches.
- **Reading**: the latest glucose value from your sensor.
- **Delta**: how much glucose changed since the reading about 5 minutes before, for example
  "falling 2".
- **Display units**: the units your site is set to show, mg/dL or mmol/L (the `DISPLAY_UNITS`
  setting).

**Who is affected:** sites set to mmol/L whose watch face or display asks `/pebble` for mg/dL.
Sites set to mg/dL are not affected, and neither are mmol/L sites whose watch face asks for mmol/L
or does not ask for a unit.

**What was wrong:** on those sites the reading came back in mg/dL but the delta came back in
mmol/L, with nothing saying so. A reading of 90 mg/dL falling by 2 mg/dL came back as reading
"90", delta "-0.1". A watch face showing mg/dL would show a fall about 18 times smaller than the
real one.

**What this change does:** the delta now comes back in the same units as the reading: "90" and
"-2" in that example. Nothing else `/pebble` returns changes: the reading, the direction arrow,
insulin on board, carbs on board, the bolus wizard preview fields and the raw sensor values are the
same as before for every combination of site units and requested units.

**Do you need to do anything?** No. If you had adjusted a watch face to make the delta look right
(for example by multiplying it), undo that adjustment after updating.

## Technical detail

### The defect

`lib/server/pebble.js`: the middleware sets `req.mmol = (req.query.units || env.settings.units) === 'mmol'`,
which picks the reading's units in `mapSGVs`. The delta came from the bgnow plugin's
`delta.scaled` (`lib/plugins/bgnow.js`), which is in the sandbox's units. `prepareSandbox` sets the
sandbox to `mmol` when `req.mmol` is true and otherwise keeps the site's units, so on an mmol site
with `?units=mgdl` the delta stayed in mmol/L, and because `req.mmol` was false it was a bare number
rather than a `toFixed(1)` string. Identical on `v15.0.8` `92d08342` and `dev` `e3adc91d`.

### What the commit does

`addDelta` takes `delta.mgdl` when mg/dL is asked for and `delta.scaled` (mmol, from the mmol
sandbox, as before) when mmol is asked for. `delta.mgdl` is the same value `delta.scaled` has in a
mg/dL sandbox (`Math.round(recent.mean - mean5MinsAgo)`), so an mg/dL site's output is unchanged.

The sandbox units are deliberately left as they were. The bolus wizard preview (`bwp`, `bwpo`),
which `/pebble` adds when `iob` is enabled, compares the sandbox-scaled reading with the profile's
sensitivity and targets, which are in the profile's units. Switching the sandbox to mg/dL on an mmol
site would compare a reading of 90 with mmol/L targets: measured in-process on an mmol site with an
mmol profile (sensitivity 3.9, targets 5-7, 1 U given 30 minutes before), that variant returns
`bwp "20.32"` where the site computes `"-0.96"`. The test below fails on it.

### Every field, all combinations

Measured in-process through the pebble middleware and handler, with `iob cob rawbg` enabled, a
calibration and filtered/unfiltered values present, site mg/dL or mmol × no `units`,
`?units=mgdl`, `?units=mmol` × rising (88→90), falling (92→90), flat (90→90). Against `dev`
`e3adc91d`, the only fields that change are `bgdelta` in the mmol-site `?units=mgdl` rows: `0.1`→`2`
and `-0.1`→`-2`; flat stays `0`. `sgv`, `trend`, `direction`, `datetime`, `filtered`, `unfiltered`,
`noise`, `iob`, `bwp`, `bwpo`, `cob` and `cals` are byte-identical. `/pebble` returns no units
label field.

No other route uses `prepareSandbox`: `lib/server/pebble.js` is mounted only at `/pebble`
(`lib/server/app.js`).

### Tests

`tests/pebble-units.test.js` (new, 21 tests, no database; each request gets a fresh ctx):

- 18 tests: site mg/dL or mmol × no `units`, `?units=mgdl`, `?units=mmol` × rising, falling,
  flat, asserting `sgv` and `bgdelta` are both mg/dL (`"90"`, number) or both mmol/L (`"5.0"`,
  one-decimal string).
- a 2 mg/dL fall on an mmol site asked for mg/dL is not reported as `-0.1`.
- one reading only (no delta): the legacy `0` stays, `0` for mg/dL and `"0.0"` for mmol, both site
  units.
- mmol site with `iob` and `cob` enabled: `iob`, `bwp`, `bwpo`, `cob` are the same for no `units`,
  `?units=mgdl` and `?units=mmol`.

No existing expectation changed.

Full suite on `aa224c69`: **3191 passing, 0 failing, 3 pending** (`npm test`, Node 22.23.2,
MongoDB 7.0.43 read from the server). `dev` `e3adc91d` is 3170/0/3 on the same form; the
difference is the 21 new tests.

Probe `tools/lab/triage-2026-09/pebble-units.js` (alignment repo): exit 1 on `dev` `e3adc91d`
(`sgv "90" bgdelta -0.1`), exit 0 on `aa224c69` (`sgv "90" bgdelta -2`); its three controls pass
on both.

### Break-its

- `lib/server/pebble.js` from `dev` with the new tests: 4 fail, the mmol site `?units=mgdl`
  rising (`expected 0.1 to be 2`) and falling (`expected -0.1 to be -2`), the fall-not-0.1 test,
  and the bwp test's delta assertion. Flat passes on both, since 0 is 0 in either unit.
- `prepareSandbox` setting the sandbox units both ways (`req.mmol ? 'mmol' : 'mg/dl'`) instead of
  this commit: 20 pass, 1 fails, `bwp changed with ?units=mgdl`.

## Client impact

Read, not run. No client in the corpora under `externals/` calls Nightscout's `/pebble`:

- nightguard, whose author filed #6220, reads `api/v2/properties` and uses `delta.mgdl`
  (`externals/nightguard/nightguard/external/NightscoutService.swift:1590`, `:1629`, `:1703`) and
  computes the delta from entries elsewhere (`:1522-1530`, `:1568-1575`).
- xDrip serves its own local `/pebble`
  (`externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/webservices/WebServicePebble.java`)
  and does not call Nightscout's.
- Nocturne reimplements `/pebble` server-side and already returns the delta in the requested units
  (`externals/nocturne/src/API/Nocturne.API/Controllers/V1/PebbleController.cs:82`, `:115-120`).

The callers are watch faces and displays outside the corpora, so the number of affected sites is
not known. No corpus client compensates for the old delta. A watch face that multiplied the delta
by 18 on mmol sites to work around it would now show a value 18 times too large; none was found.
