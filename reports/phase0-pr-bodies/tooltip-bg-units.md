<!-- Draft body for branch bf/tooltip-bg-units at affbc8fd (one commit on dev 74942ec6), 2026-10-02. This comment is hidden on GitHub. Not pushed, not opened. -->
The chart tooltip of a treatment with carbs or insulin shows its BG in the units it was entered in (BF-124, issue #5940). One commit (`affbc8fd`) on `dev` `74942ec6`; full suite 3552 passing, 0 failing, 4 pending (Node 22.23.2, MongoDB 7.0.43), against 3538/0/4 on `74942ec6` plus the 14 new tests.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nightscout is a secondary display, and nothing here is advice about insulin doses.*

A few words used below:

- **Treatment**: a saved carb entry, insulin dose, note and similar.
- **BG**: a blood glucose value, for example one you type in from a finger-stick meter.
- **Tooltip**: the small box that appears when you point at (hover over) something on the chart.
- **Display units**: the units your site shows, mmol/L or mg/dL.
- **Profile units**: the units saved in your profile (your basal, carb ratio and sensitivity settings). On some sites these differ from the display units, for example when an app such as Loop uploads the profile in mg/dL to a site that shows mmol/L.
- **Careportal**: the form on your Nightscout site for entering treatments.

**What was wrong.** When you hovered over a carb or insulin treatment on the chart that had a BG saved with it, the tooltip could show the wrong BG number. It happened when your site's display units and your profile's units were different:

- On a site showing mmol/L with a profile in mg/dL, a BG entered as 5 showed as **0.3**.
- On a site showing mg/dL with a profile in mmol/L, a BG entered as 90 showed as **1621**.
- On a site where both are mmol/L, a BG saved in mg/dL (90) showed as **90** instead of 5.

**What was always right.** The saved record was correct: Nightscout stored the number you entered, with its units. The BG Check dots on the chart, the treatment list in Reports, and the apps that sent or read the data were not affected by this bug. Only this one tooltip showed the wrong number.

**What this change does.** The tooltip now reads the units saved with each BG and converts only when they differ from your display units. A BG saved without units is taken to be in your profile's units, as before. This changes only what the tooltip shows. No saved data is changed.

**Do you need to do anything?** No. After you update, the tooltip shows the number you entered.

**A note on BG numbers.** Treat a number in a tooltip as a reminder of what was entered, not as a reading to act on. Check BG values against your meter or CGM app before making treatment decisions, and do not work out a dose from a chart tooltip. If you see a value that does not look right, check it against the source, and talk to your care team about how to use your readings.

## Technical detail

### The defect

`lib/client/renderer.js` `appendTreatments` → `treatmentTooltip` (the `mouseover` handler of the bubble that `drawTreatment` draws for a treatment with carbs, insulin, protein or fat) started from `treatment.glucose` and converted it whenever `client.settings.units != client.ddata.profile.getUnits()`, without reading `treatment.units`. The careportal saves a BG with `units: client.settings.units` (`lib/client/careportal.js` `gatherData`), so a careportal BG is already in the display units and was converted a second time exactly when the display and profile units differ. A record whose units differ from the profile's was not converted at all. Same code on `v15.0.8` `92d08342`.

### What the commit does

- `treatmentTooltip` takes the source units from `treatment.units`, falling back to `profile.getUnits()` when the record has none, and converts only when they differ from the display units. Rounding on conversion is unchanged (one decimal for mmol/L, whole numbers for mg/dL); an unconverted value is shown as stored, as before.
- A local `normalizeUnits` maps any value containing `mmol` (case-insensitive) to `mmol` and anything else to `mg/dl`. This is the rule `profile.getUnits()` (`lib/profilefunctions.js`) and `DISPLAY_UNITS` (`lib/server/env.js`, `lib/settings.js`) already use, so `mmol`, `mmol/L`, `mg/dl` and `mg/dL` (all written by uploaders, below) compare correctly.

### Units on treatments, by uploader (read from source, not measured)

| uploader | `units` on treatments with `glucose` | spelling |
|---|---|---|
| careportal | display units | `mmol`, `mg/dl` |
| Loop (NightscoutKit) | carb and dose uploads carry no `glucose`; the model's enum, when set, is | `mmol/L`, `mg/dL` |
| Trio | treatment uploads carry no `glucose` (manual BGs go to entries) | — |
| AndroidAPS (NSClient v3) | therapy events: the record's own unit; Bolus Wizard: always mg/dL | `mmol`, `mg/dl` |
| xDrip+ | treatments carry no `glucose`; meter BGs go to entries as `mbg` in mg/dL | — |

### Other displays of a treatment BG (not changed here)

- `renderer.js` `addTreatmentCircles` tooltip (BG Check and other treatments without carbs or insulin) prints `glucose` as stored and never converts; a mg/dL record on an mmol/L site shows the mg/dL number. Different behaviour from this bug, not a double conversion.
- `lib/report_plugins/treatments.js` (Reports → Treatments) prints `glucose` as stored, without units.
- `lib/plugins/treatmentnotify.js` announcement text prints `glucose` as stored.
- `lib/report_plugins/utils.js` `scaledTreatmentBG` (Day to Day bubble position) and `lib/data/treatmenttocurve.js` (chart bubble position) compare `treatment.units` with strict equality, so `mmol/L` or `mg/dL` are taken as mg/dL and converted the wrong way. These place a bubble; they print no number.

## Tests

`tests/client.renderer.tooltip-units.test.js` (new, 14 tests), using the tree's jsdom fixtures (`tests/fixtures/secure-jsdom.js`, `dom-globals.js`, `d3.js`) as `tests/stored-output-sinks.test.js` does for this tooltip. Each test draws the treatment with the tree's `drawTreatment` (or `addTreatmentCircles`), dispatches `mouseover` and reads the "BG:" value.

- **Fail on `dev` `74942ec6` with the reported numbers** (7): mmol display, mg/dl profile, careportal 5 mmol (`expected 0.3 to be 5`); mg/dl display, mmol profile, 90 mg/dl (`expected 1621 to be 90`); all mmol, a 90 mg/dl record (`expected 90 to be 5`); and four spelling cases (`mg/dL`, `mmol/L`) that fail with 90, 5, 0.3 and 1621.
- **Pass on both** (7): same units mmol and mg/dl; a 90 mg/dl record on an mmol display with an mg/dl profile is converted to 5; the BG Check dot; and three records without `units`, which are taken to be in the profile's units.

Mutation checks on the fix: taking a record without units to be in the display units fails the two no-units conversion tests; removing the spelling normalisation fails two spelling tests (0.3, 1621); never converting fails six.

### In a browser

Playwright Chromium against the server, MongoDB 7.0.43, `DISPLAY_UNITS=mmol` and an mg/dl profile: a Meal Bolus with BG 5 (Finger) and 10 g carbs entered through the careportal form is stored as `{glucose: 5, units: 'mmol'}`. Hovering the bubble shows **BG: 0.3** on `74942ec6` and **BG: 5** on this branch (three runs each).

Fixes #5940
