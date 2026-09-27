# Journey lab, browser hand checks on the 15.0.9 candidate

*Snapshot, 2026-09-26 (US afternoon and evening). The maintainer checked each step by hand in
Chrome while an agent played the phone with `tools/review/journey-lab/lab.sh fire`. Tree under
test: cgm-remote-monitor official/dev `ff93fa94` (package 15.0.9, with BF-80, 106, 121, 122, 123,
125, 128, 129, 135, 136, 138, 139 and 140 merged; register commit `d5428196`), worktree
`externals/work/crm-journey-dev`. 15.0.8 `92d08342` (`externals/work/crm-journey-1508`) was used
for comparison on ports +50. Contributor-facing. Synthetic data only. Not medical advice. The
journeys are in the [journey map](journey-map-15.0.9.md); the scripted walk on `e3adc91d` is
[journey-lab-15.0.9-2026-09-25.md](journey-lab-15.0.9-2026-09-25.md).*

**Since this run, `dev` moved to `699eb5fa`** (#8781 at `ce7d754a`, #8783 at `699eb5fa`). Both are
server-only (`git diff --stat ff93fa94 699eb5fa`: `lib/api3/storage/mongoCollection/utils.js`,
`lib/server/bootevent.js`, `lib/server/srv-dates.js`, `lib/server/treatment-fallback-key.js`, tests)
and touch paths scenarios 3, 4 and 7 exercised (v3 DELETE, the same-time key, `srvModified`). The
browser outcomes below are for `ff93fa94`; see [what this does not cover](#what-this-does-not-cover).

Environment: node 22.22.0, `NODE_ENV=development`, `TZ=UTC` on the servers; `mongo:7` container
`ns-journey-lab`; every site `AUTH_DEFAULT_ROLES=denied` with the flag set in map §B1.

## Scripted re-run before the hand checks

JL-1 (BF-135) on `ff93fa94`, with 15.0.8 controls, read with `/api/v2/properties/cob` and
`/api/v1/treatments.json?find[carbs]=40`:

| site | step | `ff93fa94` | 15.0.8 |
|---|---|---|---|
| `cp-aaps` (v3, no device status) | AAPS carbs 40 g | COB 40 | COB 40 |
| | AAPS v3 DELETE (soft delete) | COB none; v1 returns 0 records | COB 40; v1 returns the record with `isValid:false` |
| `aaps-v1` (socket `dbAdd`, then `dbUpdate isValid:false`) | after the delete | v1 returns 0 records | v1 returns the record with `isValid:false` |

With the AAPS-uploaded profile, v1 carbs gave COB 0 before the delete on both trees: the lab's
AAPS profile has no `carbs_hr`. With the Profile Editor profile (`carbs_hr` 20), the same v1 carbs
give COB 40. A lab profile-shape effect, not a defect.

## Results

| # | scenario | new `ff93fa94` | 15.0.8 |
|---|---|---|---|
| 1 | Empty site, Profile Editor first (`cp-loop` :15311 / :15361) | pass, with JL-3 and one feature request below | pass; first save needs a start date after 1970 |
| 2 | App first: Loop / Trio / AAPS (:15301–15303) | pass | deferred |
| 3 | AAPS deletes carbs, BF-135 (:15313, :15304 / :15363) | pass: the carbs leave the chart and COB without a reload | control: the deleted carbs stay counted (COB 40) |
| 4 | Two carb entries at the same time from Care Portal, BF-121 (:15301 / :15351) | pass: both kept, COB 35 | control: the 15 g replaced the 20 g, COB 15 |
| 5 | Loop remote commands from Care Portal (:15301 / :15351) | pass; JL-2 mechanism found, window at most about 60 s | same |
| 6 | AAPS temporary target and 150% profile switch, BF-123 (:15303 / :15353) | pass: scaled basal, ISF, CR; JL-5 cosmetic; two lab payload defects fixed | control: unscaled values |
| 7 | Edit and delete in the browser (:15303 / :15353) | pass; web edits now visible to AAPS (`srvModified` bumped); JL-6 report race (pre-existing) | edit not visible to AAPS; same race |
| 8 | Sharing tokens (:15323 / :15373) | pass: all four roles behave as designed; edit/delete icons shown without permission (usability) | same |
| 9 | Reports, every tab, 7 days (:15323 / :15373) | pass: Day to day, Daily Stats, Distribution, Hourly stats, Percentile, Success, Week to week, Treatments (with the new event-type filter), Profiles, Loopalyzer; no console errors | pass (no filter) |
| 10 | CGM first through nightscout-connect 0.1.0 (:15331–15333) | pass: no duplicates after Trio's re-upload; a 14-minute signal loss filled on the first poll after it | — |
| 11 | `/pebble` units, BF-128/138/139 (:15323 / :15373) | pass: mg/dL delta and bwpo in mg/dL | control: mmol/L values in an mg/dL answer |

## What this gives confidence in

Every scenario ran on 15.0.9 with the maintainer at the browser; ten of eleven also ran on 15.0.8
side by side (scenario 10 has no 15.0.8 counterpart; scenario 2's 15.0.8 half is deferred).
**No 15.0.9 regression was found.** Where the two trees differ, 15.0.9 is the one that behaves as
the release notes say.

- **The 15.0.9 fixes that change what a person sees work in a real browser**, with 15.0.8 showing
  the old behaviour on the same steps: BF-135 (AAPS-deleted carbs leave the chart and COB, live),
  BF-121 (two Care Portal carb entries at the same time both kept), BF-123 (a 150% AAPS Profile
  Switch shows scaled basal, ISF and carb ratio), BF-122 (a web edit of an AAPS record bumps
  `srvModified`, so AAPS's v3 history sees it), BF-128/BF-138 (`/pebble?units=mgdl` on an mmol/L
  site answers in mg/dL).
- **Backwards compatibility held** on every path both trees ran: first-run redirects and the
  Profile Editor, Loop remote commands (override, remote carbs, cancel) delivered to the right
  device, AAPS temp targets and their cancel, Reports edit and delete, all four sharing roles, all
  Reports tabs over 7 days of AAPS history, live page updates.
- **The connector-first path works with nightscout-connect 0.1.0**: 2 days of history on first
  start, no duplicate readings when Trio re-uploads what it fetched, and a 14-minute signal loss
  filled on the first poll after it.
- **Live updates**: new treatments, deletes, AAPS edits (temp target cancel), new profiles (Care
  Portal preset list) all reached open pages without a reload on both trees.

## Findings by category

| category | item | trees | where |
|---|---|---|---|
| 15.0.9 fix confirmed in the browser | BF-135, BF-121, BF-123, BF-122 (web edit visible to AAPS), BF-128, BF-138 | 15.0.9 fixed; 15.0.8 old behaviour | scenarios 3, 4, 6, 7, 11 |
| 15.0.9 difference, not traced to a PR | the Profile Editor's first save on an empty site works as filled in; 15.0.8 refuses until a start date after 1970 is chosen | 15.0.9 better | scenario 1 |
| regression | none found | — | — |
| pre-existing defect, found here | **JL-2 corrected**: after a new profile upload, remote commands go to the previous device for up to about 60 s (the heartbeat), not one upload cycle; mechanism found (profile writes signal a reload before the write completes) | both | scenario 5 |
| pre-existing defect, found here | **JL-3** Reports → Profiles drops later profiles on the report's last day | both (same code) | scenario 1 |
| pre-existing defect, found here | **JL-4** Care Portal stores and pre-fills Entered By as the text `undefined` after a blank submit | both; same code on 14.2.6 | scenario 4 |
| pre-existing defect, found here | **JL-5** (cosmetic) the basal pill shows scaled ISF and carb ratio unrounded (`1.866666666667`); BF-123 makes it common | both code paths | scenario 6 |
| pre-existing defect, found here | **JL-6** the Treatments report can repaint before its own PUT or DELETE lands, showing the old value | both (same code) | scenario 7 |
| usability gap | a Loop remote command gives no confirmation on success (the drawer just closes) | both | scenario 5 |
| usability gap | Reports → Treatments shows edit and delete to a role that cannot use them (401) | both | scenario 8 |
| feature request | the Profile Editor should default a new profile's time zone to the browser's (today `UTC`) | both | scenario 1 |
| as designed, confirmed | a web delete removes the record, so AAPS never learns of it (decision `BFQ-122`, in the release notes); `careportal` alone cannot read (BF-78, open); a caregiver can add but not edit or delete; the Profile Editor does not update itself while open | both | scenarios 7, 8, 2 |
| not evidenced either way | BF-139: the reads checked showed site units on both trees | both | scenario 11 |
| lab defect, fixed | the emulated AAPS embedded `profileJson` as tuples (breaks a percentage switch on both trees); sent temp targets in mmol/L labelled mg/dL | lab only | scenario 6 |

None of JL-2 to JL-6 is filed in the backfix register. The maintainer decided on 2026-09-26 to list
all five as known issues in the 15.0.9 release notes. JL-2 is
recorded as an ecosystem gap (GAP-REMOTE-010), a classification made while the mechanism was
unknown: with the mechanism found it is a Nightscout race with a local fix (signal the reload
after the write completes), which the maintainer may want to reclassify.

## What this does not cover

- **`dev` after `ff93fa94`**: #8781 and #8783 (server-only) change paths scenarios 3, 4 and 7 used.
  Their own tests and run 019 cover them; the browser steps were not repeated on `699eb5fa`.
- **Hand checks the release contents still list** that this run did not do: a remote bolus, and
  LoopCaregiver from its own app (scripted only); the clock views; the pump pill; the alarm level
  labels (`lib/levels.js`); during an AAPS percentage switch, the Bolus Wizard Preview pill and the
  reports (the basal pill, ISF and carb ratio were checked).
- **Scenario 2 on 15.0.8** (deferred at the maintainer's request).
- **Real apps.** Every phone was emulated from the apps' source; the real-app track is in
  `tools/review/journey-lab/REAL-APPS.md`.

## Scenario detail

### 1. Empty site, Profile Editor first

| step | `ff93fa94` :15311 | 15.0.8 :15361 |
|---|---|---|
| open, log in with the API secret | login prompt, then one "Redirecting you to the Profile Editor", then `/profile` | same |
| Profile Editor on an empty site | "Default values used" warning; placeholders | same |
| save | saves as filled in (start date = now) | **does not save** until a start date after 1970 is chosen: the empty-site record starts at `new Date(0)`; the maintainer picked 1970-01-02 |
| `/` afterwards | no redirect, after reloads too; empty chart; `Loop ⚠`, empty `Pump`, `IOB ---U`, CAGE/SAGE/BAGE `n/a` | same |
| Loop `connect` (emulated) | no import: the record has no `enteredBy` | same |
| Loop `onboard` | Loop's profile newest; Profile Editor lists both; Loop's targets and basals shown correctly | same |
| Care Portal | Temporary Override and Remote Carbs offered | same |
| Reports → Profiles, today | **only the 12:19 Profile Editor record (JL-3)** | both (this data cannot trigger JL-3) |

The maintainer saved basal 0.0 and targets 0–0: accepted, and correct to accept (correction-only
users run 0 basal).

**Feature request:** the Profile Editor should default a new profile's time zone to the browser's.
Today it defaults to `UTC` (`lib/client-core/profile-editor/default-profile.js`).

**JL-3: Reports → Profiles drops later profiles on the report's last day.** Not a 15.0.9
regression. `dataLoadedCallback` passes the day strings (`YYYY-MM-DD`) as `dFrom`/`dTo`
(`lib/report/reportclient.js:480`), and `new Date('2026-09-26')` is UTC midnight. For a one-day
report the core query (`startDate` between the two midnights, `:764`) finds nothing, the previous
query finds nothing, and the next query (`$gt dTo`, ascending, `count=1`, `:796`) returns only the
earliest record after midnight. Every later record that day is dropped. Replayed against the
server: the same three queries return 0, 0 and 1, while `/api/v1/profiles` holds 2. The code is the
same on 15.0.8. Read, not run: the other report tabs use the same `datastorage.profiles`, so their
basal and target lines on the last day may follow the wrong profile. Not filed; the maintainer's
call.

### 2. App first

| check | Loop :15301 | Trio :15302 | AAPS :15303 (mmol) |
|---|---|---|---|
| empty site redirects | pass | pass | pass |
| what the app sent | `onboard`: profile | `finish-onboarding`: a "Trio connected" Note only; `onboard` (next cold launch): profile | `wizard`: profile store (LabDay, LabWeekend), Profile Switch, effective-switch Note |
| redirect stops | pass | only after `onboard`, as predicted | pass |
| values in the Profile Editor match the upload | pass (DIA 6, CR 10/12, ISF 50, basal 0.8/0.95/0.75, target 100–110) | pass (DIA 10) | pass (ISF 2.8, target 5.5–6.1 mmol/L; both profiles) |
| time zone | Loop sent `ETC/GMT+7`; the editor shows `Etc/GMT+7` (case-insensitive match) | America/Los_Angeles | America/Los_Angeles |
| open Profile Editor updates by itself | no; it loads once (no live-update code in `lib/profile/profileeditor.js`): expected | same | same |
| chart | — | — | the LabDay Note always; the Profile Switch is drawn in the basal area, so it shows once the basal display is on: expected |

### 3. AAPS deletes carbs (BF-135)

Reset first (`up cp-aaps aaps-v1`, `up --ref cp-aaps`), then `cgm-tick 3`, `editor-save` (a profile
with `carbs_hr` 20), `connect`, `live <n> cgm`. The stale-data alarm from the break cleared.

| step | :15313 (v3, mmol) | :15304 (v1 socket) | :15363 15.0.8 (v3, mmol) |
|---|---|---|---|
| baseline | fresh readings, no alarm, COB empty, no redirect | same | same |
| AAPS carbs 40 g | marker live; COB 40 (source Care Portal) | same | same |
| AAPS delete (v3 DELETE / socket `dbUpdate isValid:false`) | marker gone **live**; COB empty; v1 lists nothing | same | marker and COB 40 stay; v1 lists the record with `isValid:false` |

### 4. Two carb entries at the same time (BF-121)

First attempt, not a valid test: both trees stored two records, but the second Care Portal submit
had `eventType: ""` (event type left at its default) and `enteredBy: "undefined"` (the string),
so the pair never shared the `created_at` + `eventType` key that 15.0.8 merges on. COB stayed 0: the
Loop profile has no `carbs_hr`. Both records deleted, a Profile Editor profile (`carbs_hr` 20) saved
on both sites, and the step repeated with the event type chosen on each submit.

| step (event time 22:40 UTC, Carb Correction both times) | :15301 | :15351 15.0.8 |
|---|---|---|
| 20 g, then 15 g, same time | 2 records (20, 15); COB 35 | 1 record (15); COB 15 |

**JL-4: Care Portal pre-fills Entered By with the text `undefined`.** Not a 15.0.9 regression: the
same code is in 14.2.6, 15.0.7 and 15.0.8. When Entered By is blank on submit, the normalizer drops
the empty field (`lib/client-core/careportal/normalize-treatment.js:113`), so `data.enteredBy` is
`undefined`, and `storage.set('enteredBy', data.enteredBy)` (`lib/client/careportal.js:408`) writes
the string `undefined` to local storage. The next time the drawer opens,
`storage.get('enteredBy')` (`:286`) pre-fills it, and the record is stored with
`enteredBy: "undefined"` unless the person clears the field. Seen on both trees in an Incognito
window after one blank submit. `client.authorized` is not set with an API-secret login, so the
stored value is used. Not filed; the maintainer's call.

### 5. Loop remote commands from Care Portal

Reset first (`up loop`, `up --ref loop`, `cgm-tick 3`, `onboard`, `live <n> cgm`).

| step | :15301 | :15351 15.0.8 |
|---|---|---|
| Care Portal Temporary Override (Running, 60 min) | push to this site's device token, topic `org.lab.Loop`, `override-name` Running, 60 min | same |
| Care Portal Remote Carbs (12 g, 3 h, OTP 123456) | push with `carbs-entry` 12, `absorption-time` 3, `otp` | same |
| on-screen response | none: the drawer closes | same |

The silent success is the code: on success the submit hook's callback only closes the drawer
(`lib/client/careportal.js:374-379`); errors show an alert (`lib/plugins/loop.js:118-133`). The
same on 15.0.8. The maintainer noticed no confirmation; a usability gap, not a defect.

| step | :15301 | :15351 15.0.8 |
|---|---|---|
| Loop uploads the override and the carbs | Running band and 12 g marker, live | same |
| Loop on a new phone (`new-phone`: new token, preset Movie night), readings feed stopped | Movie night offered in Care Portal **without a reload** | same |
| Running, then Movie night, about 3.5 min after the upload, no new data | both pushes to the **new** token | same |
| after the scripted re-upload of the first phone's profile | Movie night gone from the list without a reload; Temporary Override Cancel pushes `cancel-temporary-override` to the first phone's token | same |

**JL-2, mechanism found and window measured.** The browser commands above went to the new phone,
so the window is not "until the next reading". Scripted: `onboard` (back to the old token), then a
Care Portal override at 2, 20, 40, 60, 90, 120 and 180 s with no other writes:

| after the upload | :15301 | :15351 15.0.8 |
|---|---|---|
| 2 s | previous token | previous token |
| 20 s, 40 s | previous token | new token |
| 60 s and later | new token | new token |

Cause: profile `create`, `save` and `remove` emit `data-received` synchronously, before the
database write completes (`lib/server/profile.js:90,130,210` on `ff93fa94` and `699eb5fa`, the
`ctx.bus.emit` after `runWithCallback`; the same on 15.0.8). The
leading-edge debounce (`lib/server/bootevent.js:349`) runs the data loader at once, so
`loadProfile` reads the previous newest profile, and `ctx.ddata.profiles[0]` (read by
`lib/server/loop.js:36`) stays stale until the next reload: the next write of any kind or the
heartbeat tick (`heartbeat: 60` s, `lib/settings.js:37`). The window is therefore at most about 60 s
with no other writes, not one upload cycle. The 15.0.8/15.0.9 difference above is the tick phase.
[GAP-REMOTE-010](../../../traceability/treatments-gaps.md#gap-remote-010-loop-remote-commands-keep-the-previous-profiles-device-after-a-new-profile-upload)
says the mechanism was not determined and gives the window as one upload cycle; both need updating.

### 6. AAPS temporary target and 150% profile switch (BF-123)

Reset first (`up aaps`, `up --ref aaps`, `cgm-tick 3`, `connect`, `wizard`, `live <n> cgm`).
Baseline on both trees at 16:18 Los Angeles time: basal 0.950 U/h, ISF 2.8, CR 12.

**Lab defect found and fixed during the step.** The first `ps-start 150` made the server drop the
basal property on both trees ("For the Basal plugin to function you need a basal profile"). The
lab embedded `profileJson` as its own `[time, value]` tuples; AAPS sends Nightscout schedule items
(`toPureNsJson`). A switch named in the store (the wizard's 100% LabDay) never reads `profileJson`,
so only the percentage switch exposed it. `clients.js` now converts `profileJson` to schedule items
(`pureNsJson`); the sites were reset and the switch repeated.

| step | :15303 | :15353 15.0.8 |
|---|---|---|
| AAPS `ps-start 150 0 LabDay` (server `basal` property) | 1.425 U | 0.950 U |
| basal pill, hover (maintainer) | 1.425 / ISF 1.866666666667 / CR 8 | 0.950 / 2.8 / 12 |

**JL-5 (cosmetic): the basal pill shows the scaled ISF unrounded.** `lib/plugins/basalprofile.js:64-77`
rounds the sensitivity only when it converts units, and never rounds the carb ratio. With BF-123's
scaling a 150% switch gives `1.866666666667`; before 11:00 the carb ratio would show `6.666…`.
The same code path already applied to AAPS 2.x `CircadianPercentageProfile` switches, so the
rounding gap predates 15.0.9; BF-123 makes it common. Not filed.

**Second lab defect: the AAPS temp target in mmol/L.** `tt-start 7.8` stored `targetTop: 7.8,
units: "mg/dl"`: no band on the mmol/L chart (0.4 mmol/L, off the bottom), while Reports →
Treatments listed it ("Activity", 60 min). AAPS uploads temp targets in mg/dL whatever the display
units, so the lab now converts a mmol/L argument (7.8 → 140 mg/dL). The bad target was cancelled
(`tt-cancel`, a PATCH shortening it to 5 min) and a new one started at 23:29 UTC.

| step | :15303 | :15353 15.0.8 |
|---|---|---|
| AAPS temp target 7.8 mmol/L (140 mg/dL), 60 min | thin grey bar at 7.8 (Nightscout draws a bar, not a band); hover: Temporary Target, 7.8, Activity; Reports: 5 and 60 min | same |
| AAPS cancel (v3 PATCH, duration 60 → 8) | bar shortened **live** | same |

### 7. Edit and delete in the browser

| step | :15303 | :15353 15.0.8 |
|---|---|---|
| AAPS carbs 20 g (v3) | marker live | same |
| Reports → Treatments edit 20 → 25 | saved; main-page marker 25 **live**; **the Treatments table still showed 20** | saved; marker 25 live; table showed 25 |
| stored record after the edit | `identifier` kept; `srvModified` bumped; `created_at` and `date` moved to the minute (23:38:00, the form has minute precision); `date` and `isValid` now strings | `identifier` kept; `srvModified` **not** bumped (so AAPS's v3 history would not see the edit); `date` and `isValid` now strings |

**JL-6: the Treatments report can repaint before its own save lands.** `saveTreatmentRecord` sends
the PUT without waiting, then the dialog's Save handler at once deletes the day from
`datastorage` and calls `report_plugins.show()` (`lib/report_plugins/treatments.js:229-231`; delete
at `:181-182` is the same). Whichever finishes first, the PUT or the re-read, decides what the
table shows. The same code is on 15.0.8 (`:218-220`), where the maintainer's table happened to
show 25. Measured PUT times are the same on both trees (4–11 ms), so this is ordering, not a
slowdown. Not filed.

| step | :15303 | :15353 15.0.8 |
|---|---|---|
| Reports → Show again | the row reads 25 (JL-6 confirmed as the race) | — |
| Reports → Treatments delete | marker gone **live**; the record is **removed from the database** (v1 DELETE), no `isValid:false` tombstone | same |

A web delete of an AAPS record leaves nothing for AAPS's v3 history to report, on both trees, so
the phone keeps its copy. Pre-existing; consistent with J4.4 ("changes made on the site do not go
back"), noted for the ecosystem map.

### 8. Sharing tokens

Sites stale since 19:10 UTC: `cgm-tick 5` filled the gap, `live rep-aaps` / `live rep-aaps-1508`
(phone cycle) keeps them fresh. Each role in its own Incognito window, no API secret.

| role (link `?token=`) | :15323 | :15373 15.0.8 |
|---|---|---|
| follower (`readable`) | data, no prompt, no Care Portal button, Reports ok | same |
| caregiver (`readable` + `careportal`) | data; Care Portal Note saved; Entered By pre-filled `labcaregiver`; Reports lists it; **edit and delete → 401** | same |

The 401s are the role design: `careportal` is `api:treatments:create` only
(`lib/authorization/storage.js:236`), while PUT and DELETE need `api:treatments:update` and
`:delete` (`lib/api/treatments/index.js:174,194`). The Treatments report shows the edit and delete
icons whatever the permissions; a usability gap on both trees, not a defect.

| role | :15323 | :15373 15.0.8 |
|---|---|---|
| careportal only (BF-78, open) | login prompt; closed: empty chart, no Care Portal button | same |
| status only | login prompt; closed: clock and `---`, empty chart, no Care Portal button | same |

### 9. Reports, every tab

Sites `rep-aaps` / `rep-aaps-1508`: 14 days of simulated AAPS history each (about 4,045 readings,
300 treatments, 4,035 device statuses), seeded per site, so figures differ between the trees and
the check was that each tab draws sensibly. Range: last 7 days. Day to day, Daily Stats,
Distribution, Hourly stats, Percentile, Success, Week to week, Treatments, Profiles and Loopalyzer
drew on both trees with no console errors. The Treatments event-type filter (`9231f8cf`) is
on 15.0.9 only and works.

### 10. CGM first, through nightscout-connect 0.1.0 (:15331–15333, no 15.0.8 counterpart)

| step | cgm-loop :15331 | cgm-trio :15332 | cgm-aaps :15333 (mmol) |
|---|---|---|---|
| connector only, no app | redirect to the Profile Editor (expected: readings only); the redirect hides the chart, the title shows the current reading | same | same |
| app joins (00:14 UTC) | `remote-cgm`, `onboard` | `onboard`, `ns-cgm` (fetch 628, **re-upload 628**) | `connect`, `wizard`, `ns-bg` |
| after reload | no redirect; readings; 48 h single | same | same |
| database | 630 readings, spacing 5 min (8 gaps of 10 min), no two in the same minute, all `nightscout-connect` | 629, no duplicates after Trio's re-upload (count unchanged, device still `nightscout-connect`) | 636, no duplicates |

The 10–15 min gaps are the fake Share server's simulated sensor gaps (`household.js:99`, about
1.2%), all in the history, none since the apps joined. The maintainer could not judge doubles by
eye on the 48 h chart; the database check replaced it (a process note).

**Gap fill after lost signal (cgm-loop).** The fake Share account was paused 00:18:53–00:32:51 UTC
(`share-pause-cgm-loop`). The page showed the stale warning at 18 minutes. During the pause each
poll asked for everything since its last reading (`minutes` 10, 15, 20; the connector sizes the
window from its last reading, `nightscout-connect/lib/sources/dexcomshare.js:194-195`). The first
poll after the resume (00:35:20, `minutes` 25, `maxCount` 5) returned 5 and the database gained
00:20, 00:25, 00:30 and 00:35: **the gap was filled with no hole.** The 00:15 reading was
re-sent in the same batch and its value changed (101 → 97): the lab's fake Share server derives
values from a plan anchored at "now", so the same timestamp can get a different value between
polls. A lab artefact (real Share values are fixed), but it shows the server replaces a reading
re-sent with the same time. In the browser the warning cleared and the gap filled **live**.

### 11. `/pebble` on an mmol/L site (BF-128, BF-138, BF-139; :15323 / :15373)

One reading posted 18 mg/dL above the previous one on each site, so the delta is not zero.

| request | :15323 | :15373 15.0.8 |
|---|---|---|
| `/pebble` (site units) | sgv 7.5, bgdelta "0.5", bwpo 7.5 | sgv 7.4, bgdelta "0.5", bwpo 7.4 |
| `/pebble?units=mgdl` | sgv 135, **bgdelta 9, bwpo 135 (mg/dL)** | sgv 133, **bgdelta 0.5, bwpo 7.4 (mmol/L, unlabelled)** |

The maintainer's reads a reading later agree (A2 bgdelta 9, bwpo 117; B2 bgdelta 0.5, bwpo 6.4).
BF-139 (live on 15.0.8, outcome only): after repeated mg/dL requests, the site-unit readers
checked (`/pebble`, `/api/v2/properties/bgnow`) showed site-unit values on **both** trees, so these
reads show no difference between the trees; not evidence either way for the fix.

## Observations that are not defects

- **Chrome with a pending update froze new tabs.** Two 15.0.8 tabs froze soon after the login
  prompt appeared. Headless Chrome did not reproduce it: 0 CPU with the prompt up, the same bundle
  byte for byte as the working :15361. Letting Chrome finish its update fixed it.
- **A site with no new readings alarms.** Seeded sites go stale after about 15 minutes and sound
  the stale-data alarm. `lab.sh live <name>` (phone cycle) or `lab.sh live <name> cgm` (readings
  only, added during this session) keeps them fresh.

## Process notes (for automating this later)

What worked and what didn't in running an interactive browser lab this way:

- **Small chunks.** One junction at a time: what to open, what to check, the words to reply with.
  Long multi-step instructions got answered in part. Put the addresses and the API secret in every
  chunk: each new browser window needs the secret again.
- **Numbered expectations with a reply template** make the report back quick and complete.
- **Separate browser contexts.** A new Incognito window or Guest profile per page that needs its own
  login. Pending browser updates can cause freezes that look like app bugs.
- **Data goes stale.** The pause between steps (a lunch break) left seeded sites stale and alarming.
  Every scenario should begin with a reset-and-seed step and keep a feed running.
- **Phone status hides treatment COB.** A device status with COB takes precedence, so scenarios that
  test the site's own COB need readings without device status (`live <name> cgm`).
- **Show the values the phone sent.** When the page shouldn't change by itself, give the person the
  exact values to look for, distinct from the defaults.
- **Read the stored records after every hand entry.** A step can look right in the browser and
  still miss the condition under test (scenario 4: the event type was left at its default, so the
  pair could not collide). The expected stored shape belongs in the checklist.
- **Say when a readout isn't meant to move.** COB depends on the profile's `carbs_hr`; say up front
  which readouts the scenario's profile supports.
- **The emulated phone can be wrong too.** A lab payload shape bug looked like a server regression
  on both trees at once; a failure on the control tree as well is the hint. Compare the payload with
  the app's source before blaming the server.
- **Some checks are not visual.** Duplicates and 5-minute spacing are invisible at 48 h; pair
  such a step with a database or API check and show its result to the person.
- **Candidates for automation or generated UI:** a checklist page per scenario (addresses, secret,
  expectations, pass/fail/notes per step) whose buttons fire the `lab.sh` step, and which records
  answers for the snapshot record.
