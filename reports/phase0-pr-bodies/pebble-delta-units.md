<!-- Body for bf/pebble-delta-units at b3db0f36 (three commits on origin/dev e3adc91d: aa224c69 BF-128, b58b937c BF-139, b3db0f36 BF-138), 2026-09-26. This comment is hidden on GitHub. Opened as #8777; merged into dev 2026-09-26 as d613c35f; the live body matches this file apart from this comment and the footer. -->
> **Reproduction detail withheld.** One of these defects (BF-139) is present in the released `v15.0.8`, so this description explains how it happens and what it could do, but leaves out how to reproduce it. Reproduction detail will be added once a fixed release is out.

Three fixes to `/pebble`, the older address that watch faces use to get the latest reading, all about units:

- **BF-128** (issue #6220): the delta (`bgdelta`) comes back in the same units as the reading (`sgv`) when a client asks an mmol/L site for mg/dL. `aa224c69`.
- **BF-139**: a `/pebble?units=mmol` request on an mg/dL site no longer changes the readings the server's own alarm checks and `/api/v2/properties` use. `b58b937c`.
- **BF-138**: the bolus wizard preview (`bwp`) is computed in the site's units whatever units are asked for, and its expected outcome (`bwpo`) comes back in the requested units. `b3db0f36`.

Three commits on `dev` `e3adc91d`, one per defect.

## What changes for you

*This is a plain-language summary for people who run their own Nightscout site for themselves or a family member. Nightscout is not a medical device, and nothing here is medical advice or dosing advice. If a number on a watch or display looks wrong, check it against your meter, and talk to your care team before relying on it.*

Some words used below:

- **`/pebble`**: an older address on your Nightscout site. Watch faces and small displays use it to get the latest glucose reading. It was first written for Pebble watches.
- **Reading**: the latest glucose value from your sensor.
- **Delta**: how much glucose changed since the reading about 5 minutes before, for example "falling 2".
- **Display units**: the units your site is set to show, mg/dL or mmol/L. This is the `DISPLAY_UNITS` setting.
- **Alarm**: the high and low alerts your Nightscout site raises itself, for example "Urgent LOW". Your site sends them to the web page, and to Pushover or other services if you set those up.
- **Bolus wizard preview (BWP)**: an estimate Nightscout shows when insulin on board (IOB) is turned on. It takes your current reading, subtracts the effect of the insulin still active, and compares the result with your profile's targets. `/pebble` returns two numbers from it:
  - `bwp`: the estimate itself, in insulin units. A negative number means the estimate is below your low target.
  - `bwpo`: the expected glucose result.

  It is a rough indicator, not a dosing recommendation.

### 1. The delta on mmol/L sites asked for mg/dL (BF-128)

**Who is affected:** sites set to mmol/L whose watch face asks `/pebble` for mg/dL.

**What was wrong:** the reading came back in mg/dL but the delta came back in mmol/L, with nothing to say so. For example, a reading of 90 mg/dL falling by 2 mg/dL came back as reading "90" and delta "-0.1". A watch face showing mg/dL would show a fall about 18 times smaller than the real one.

**What this change does:** the delta now comes back in the same units as the reading. In that example it is "90" and "-2".

### 2. Wrong alarms on mg/dL sites after an mmol/L watch face request (BF-139)

**Who is affected:** sites set to mg/dL where some watch face or display asks `/pebble` for mmol/L.

**What was wrong:** such a request could leave the reading converted to mmol/L stored on the server's own copy of the latest reading. Your site's own alarm check could then judge that reading in the wrong units, and raise a **false low alarm** when your glucose was not low. The alarm message could also show the wrong number. Values shown by `/api/v2/properties` (which some apps and watch faces read), Alexa and Google Home could be wrong until the next time the site loaded new data.

This could only happen when the watch-face request arrived in the short moment after the site loaded new data and before its alarm check ran, so it depended on timing.

It also worked the other way round. The mmol/L watch face could pick up the mg/dL value the alarm check had stored, and then show a bolus wizard preview that depended on which came first.

**What this change does:** `/pebble` now works on its own copy of the readings, so it cannot change what the alarm checks or other parts of the site see.

### 3. The bolus wizard preview in the requested units (BF-138)

**Who is affected:** sites with insulin on board turned on whose watch face asks `/pebble` for the other unit. That means an mg/dL site asked for mmol/L, or an mmol/L site asked for mg/dL.

**What was wrong:**

- **mg/dL site asked for mmol/L:** the estimate compared the mmol/L reading (5.0) with the mg/dL profile. In one example (sensitivity 70, targets 90-126, 1 U given 30 minutes before, reading 90 mg/dL), the site itself computes `bwp` -0.96 U and an expected result of 23 mg/dL. `/pebble` gave -2.17 U and -61.8. Depending on timing (see item 2), it could instead give -0.96 with an expected result of 23.2, which is an mg/dL number shown as if it were mmol/L.
- **mmol/L site asked for mg/dL:** the estimate was right, but the expected result stayed in mmol/L (1.3) next to a reading in mg/dL (90), with nothing to say so.

**What this change does:** the estimate is always computed the way the site computes it for itself, against the profile in the site's units, so `bwp` is the same whatever units the watch face asks for. The expected result `bwpo` comes back in the units the watch face asked for (23 mg/dL or 1.3 mmol/L in the example).

### Everything else

The reading, the direction arrow, insulin on board, carbs on board and the raw sensor values are unchanged for every combination of site units and requested units.

**Do you need to do anything?** No. If you had adjusted a watch face to make the delta or the expected result look right, for example by multiplying or dividing by 18, undo that adjustment after updating. If your site raised a low alarm that did not match your sensor reading, and a watch face on your site asks for mmol/L, this may have been the cause. Always check a surprising alarm against your meter.

## Technical detail

All three defects are identical on `v15.0.8` `92d08342` and `dev` `e3adc91d`. They are all in `lib/server/pebble.js`, which is mounted only at `/pebble` (`lib/server/app.js`).

### BF-128: the delta (`aa224c69`)

**The defect:** the middleware sets `req.mmol = (req.query.units || env.settings.units) === 'mmol'`, which picks the reading's units in `mapSGVs`. The delta came from the bgnow plugin's `delta.scaled`, which is in the sandbox's units. `prepareSandbox` forces the sandbox to `mmol` when `req.mmol` is true, and otherwise keeps the site's units. So on an mmol site with `?units=mgdl`, the delta stayed in mmol/L. Because `req.mmol` was false, it also came back as a bare number rather than a `toFixed(1)` string.

**The fix:** `addDelta` takes `delta.mgdl` when mg/dL is asked for, and `delta.scaled` (mmol, from the mmol sandbox) when mmol is asked for. `delta.mgdl` has the same value that `delta.scaled` has in an mg/dL sandbox, so an mg/dL site's output is unchanged. The sandbox units are deliberately left alone. Switching the sandbox to mg/dL on an mmol site would move `bwp`, which BF-138 handles separately.

### BF-139: shared scaled readings (`b58b937c`)

**The defect:**

- `sandbox.scaleEntry` stores the reading in the sandbox's units on the entry itself (`entry.scaled`), and reuses that value on later calls.
- `sandbox.serverInit` takes `ctx.ddata.clone()`, which is a shallow copy, so every server sandbox's `data.sgvs` is the server's shared `ctx.ddata.sgvs` objects.
- The `/pebble` sandbox is in mmol when `?units=mmol` is asked for, even on an mg/dL site. Its bgnow step (`lib/plugins/bgnow.js`, bucket scaling) and `bwp.calc` (`lastScaledSGV`) store `5.0` on a 90 mg/dL reading.
- `lib/data/dataloader.js` rebuilds `ddata.sgvs` as new objects on each load. `bootevent`'s `data-loaded` listener then builds a sandbox in the site's units and runs `setProperties` and `checkNotifications`, and keeps that sandbox as `ctx.sbx`.

Taken together, these give two effects:

- **Write side:** a `/pebble?units=mmol` request that lands after a data load has replaced `ddata.sgvs` and before that load's `data-loaded` evaluation leaves an mmol `scaled` value on the new readings. The evaluation then reads it against the site's mg/dL thresholds:
  - `simplealarms` can request a false low alarm.
  - `ar2`'s alarm level comes from `mgdl` and does not move, but its title and every alarm's `BG Now` message use the scaled value.
  - `ctx.sbx`, which `/api/v2/properties`, Alexa and Google Home read, keeps the mmol value until the next load.
- **Read side:** once `data-loaded` has stored the mg/dL value, `/pebble?units=mmol` reads 90 as if it were mmol/L. Its `bwp` then depends on which ran first.

Both sides were reproduced on a booted server (MongoDB 7.0.43, `DISPLAY_UNITS=mg/dl`): on `aa224c69` the server's own evaluation raised false low alarms and `/api/v2/properties` kept the mmol value; on `b3db0f36` the same runs raised none and `/api/v2/properties` kept the mg/dL value. The conditions and request pattern are left out of this description while `v15.0.8` is the current release.

**The fix:** `prepareSandbox` replaces the sandbox's `sgvs` with shallow copies of each reading and removes any `scaled` value stored by another sandbox. No other server sandbox has units that differ from the site's: `bootevent` is the only other `serverInit` caller, and Alexa, Google Home, `/api/v2/properties` and `/api/v2/summary` read its `ctx.sbx` and never scale.

### BF-138: the bolus wizard preview (`b3db0f36`)

**The defect:** `bwp.calc` computes `outcome = lastScaledSGV() - iob × sensitivity` and compares it with the profile's targets. `lib/profilefunctions.js` returns sensitivity and targets as stored, with no unit conversion, so they are in the site's units. `/pebble` ran this in its display sandbox:

- On an mg/dL site with `?units=mmol`, 5.0 was compared with the mg/dL profile.
- On an mmol site with `?units=mgdl`, the sandbox stays in mmol, so `bwp` was right but `bwpo` stayed in mmol next to an mg/dL `sgv`.

**The fix:** `pebble()` builds a second sandbox in the site's units only when mmol is asked for on an mg/dL site and `iob` or `cob` is enabled. It computes `iob`, `cob` and `bwp` there.

- `bwp` is in insulin units and is returned as computed.
- `bwpo` is converted to the requested units when they differ from the site's (`units.mgdlToMMOL` / `units.mmolToMgdl`, the same functions the reading uses). It stays a JSON number.
- The `"0"` placeholders returned when the profile lacks sensitivity or targets are kept as they are.
- `lib/sandbox` is now instantiated per sandbox rather than once per module, because `serverInit` resets the instance it is called on.
- `iob` and `cob` do not depend on the sandbox's units. They are computed in the site sandbox so that the `iob` fed to `bwp` comes from the same place.

### Every field, all combinations

Measured in-process with `tools/lab/triage-2026-09/pebble-shared-scaled.js --table` (alignment repo). Each request gets fresh data. The site profiles are:

- mg/dL: sensitivity 70, targets 90-126, basal 1.
- mmol: sensitivity 3.9, targets 5-7, basal 1.

Both have 1 U given 30 min before and a 90 mg/dL reading. Rising, falling and flat differ only in `bgdelta`: `2`/`-2`/`0` for mg/dL and `"0.1"`/`"-0.1"`/`"0.0"` for mmol. The fields that differ by combination are:

| site | query | `sgv` | `bgdelta` before → after | `bwp` before → after | `bwpo` before → after |
|---|---|---|---|---|---|
| mg/dL | none | "90" | mg/dL (unchanged) | "-0.96" | 23 |
| mg/dL | `?units=mgdl` | "90" | mg/dL (unchanged) | "-0.96" | 23 |
| mg/dL | `?units=mmol` | "5.0" | mmol (unchanged) | **"-2.17" → "-0.96"** | **-61.8 → 1.3** |
| mmol | none | "5.0" | mmol (unchanged) | "-0.96" | 1.3 |
| mmol | `?units=mmol` | "5.0" | mmol (unchanged) | "-0.96" | 1.3 |
| mmol | `?units=mgdl` | "90" | **0.1/-0.1/0 → 2/-2/0** (BF-128) | "-0.96" | **1.3 → 23** |

`iob` ("0.95"), `cob`, `trend`, `direction` and `datetime` are the same in all 18 rows before and after. `/pebble` returns no units label field.

### Tests

- `tests/pebble-units.test.js` (BF-128, extended for BF-138; no database, and each request gets a fresh ctx):
  - BF-128's 18 `sgv`/`bgdelta` combinations, the not-`-0.1` test and the no-delta legacy `0`.
  - BF-128's mmol-site `bwp` test. After BF-138 it asserts that `bwp`, `iob` and `cob` do not move with `?units=mgdl`, and `bwpo` does not move with `?units=mmol`. `bwpo` for `?units=mgdl` now changes by design and is asserted in the combinations.
  - BF-138: 18 combinations with `iob`/`cob` enabled. Each asserts that `bwp`, `iob`, `cob`, `trend` and `direction` equal the site's own answer, that `bwpo` is 23 or 1.3 in the requested units, and that `sgv`/`bgdelta` are as in BF-128. Also: not `-2.17`/`-61.8`; the `"0"` placeholders without targets, in both units; `cob` with 20 g of carbs the same in any units.
- `tests/pebble-shared-state.test.js` (BF-139, new; no database). On an mg/dL site:
  - no `scaled` value is left on the shared readings;
  - the server evaluation after `?units=mmol` reads 90 and requests no notification, and `bgnow.sgvs[].scaled` and `bwp.scaledSGV` are 90;
  - `?units=mmol` answers the same whether or not the evaluation ran first;
  - a plain request after a `?units=mmol` one answers as it does on freshly loaded readings.

Red on the parent of each fix, with the original symptoms:

- BF-139 tests on `aa224c69`: 4 of 4 fail (`expected '5.0' to not exist`, `expected 5 to be 90`, `bwp "-0.96"/bwpo 23.2` vs `"-2.17"/-61.8`).
- BF-138 tests on `b58b937c`: 7 fail. Three are `expected '-2.17' to be '-0.96'`, three are `expected 1.3 to be 23`, and the last is the `-2.17` test. The other 12 combinations pass.

Full suite on `b3db0f36`: **3216 passing, 0 failing, 3 pending** (`npm test`, Node 22.23.2, MongoDB 7.0.43 read from the server). `aa224c69` was 3191/0/3; the difference is the 25 new tests (4 BF-139, 21 BF-138).

### Break-its

| change to the fixed code | result |
|---|---|
| `bwp.calc` on the display sandbox | 4 fail: `expected '-2.17' to be '-0.96'` ×3, `-2.17` test |
| no second sandbox (`siteSbx = sbx`) | same 4 fail |
| `bwpo` not converted | 6 fail: `expected 1.3 to be 23` ×3, `expected 23 to be 1.3` ×3 |
| no `errors` guard on the conversion | 1 fails: `expected 0 to be '0'` |
| one module-level sandbox instance, as before | 2 fail: `bgdelta` `'2.0'`/`'-2.0'` instead of `'0.1'`/`'-0.1'` (the second `serverInit` resets the first) |
| copies keep `scaled` (no `delete`) | 1 fails: the read-side test |
| no copies (BF-139 reverted) | 4 of 4 BF-139 tests fail |
| `iob`/`cob` from the display sandbox | all pass. This is expected: both sandboxes hold the same treatments, devicestatus and profile, and `iob`/`cob` do not depend on units. |

## Client impact

The following was read, not run. No client in the corpora under `externals/` reads `bwp` or `bwpo` from `/pebble`, and none requests `/pebble?units=`:

- **nightguard** moved to `api/v2/properties` (commit `10a8cff`). It reads `delta.mgdl`, `delta.display`, `iob.display` and `cob.display`, which are not affected by BF-139 (they come from `mgdl` or do not depend on units), and does not read `bwp`.
- **xDrip** serves its own local `/pebble` (`WebServicePebble.java`). It ignores `?units`, has no `bwp`/`bwpo` (`// TODO output bwp and bwpo`, line 97), and does not call Nightscout's.
- **Nocturne**'s `PebbleController.cs` declares `Bwp`/`Bwpo` but never sets them, and already returns the delta in the requested units.

LoopFollow, LoopCaregiver, NightscoutKit, xdripswift, AndroidAPS, Trio, DiaBLE and nightscout-reporter do not call `/pebble`.

The callers are watch faces and displays outside the corpora, so the number of affected sites is not known. A watch face that labelled `bwpo` in its requested units was showing a wrong value in the two mismatched combinations, and now shows the right one. A watch face that had worked around either defect by multiplying or dividing by 18 would now be off by that factor; none was found.
