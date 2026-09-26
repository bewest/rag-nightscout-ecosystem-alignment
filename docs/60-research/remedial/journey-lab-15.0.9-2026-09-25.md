# Journey lab, scripted walk on the 15.0.9 candidate

*Snapshot, 2026-09-25 (US evening; server clocks about 01:40–02:10 UTC on 09-26), against
cgm-remote-monitor official/dev `e3adc91d` (package version 15.0.9; release PR #8598), worktree
`externals/work/crm-journey-rc`. 15.0.8 `92d08342` (`externals/work/crm-journey-1508`) was used
for one comparison. Contributor-facing. Synthetic data only. Not medical advice. The journeys are
in the [journey map](journey-map-15.0.9.md); the lab is [tools/review/journey-lab/](../../../tools/review/journey-lab/README.md).*

Every `fire` step in the walkthrough was run by script against the candidate, as a check of the
lab itself and of the server side of each journey. **The browser checks in the walkthrough were
not run here.** They are the maintainer's hand checks.

Environment: node 22.22.0, `NODE_ENV=development`, `TZ=UTC` on the servers; profiles and meals in
America/Los_Angeles; `mongo:7` container `ns-journey-lab`; every site `AUTH_DEFAULT_ROLES=denied`
with the flag set in map §B1.

## Results

| journey | sites | steps run | result |
|---|---|---|---|
| J1.A app first | `loop`, `trio`, `aaps`, `aaps-v1`, `aaps40` | `connect` (empty), `onboard`, `connect` again, `backfill` | all accepted (Loop array POST, Trio object POST, AAPS v3 POST `201`, AAPS v1 socket `dbAdd` acked). Empty site: `/api/v1/profile/current` answers `null`, `profile.json` answers `[]`; each app's import is predicted to skip. After `onboard`: Loop and Trio would import their own profile |
| J1.B site first | `cp-loop`, `cp-trio`, `cp-aaps` | `editor-save` (the Profile Editor's PUT), `connect` | save `200`. Predictions: Loop **NO** (no `enteredBy`, no `loopSettings`); Trio **NO** (decode fails: no `enteredBy`, `mills`; confirmed against `Trio/Sources/Models/RawFetchedProfile.swift:3-11`); AAPS 3.4 **ACCEPT** (would replace the phone's profiles) |
| J2 sync | all J1.A sites | `backfill 6`, `tick`, `status` | readings, doses and device status stored under each app's sender; `status` shows the right keys (`loop` / `openaps`) |
| J3 Loop | `loop` | `override-start` / `-end` / `-delete`, indefinite, `site-override`, `caregiver-override`, `caregiver-cancel`, `settings-change` | all `200`. End-early re-POST leaves **one** record, with the actual duration. Delete by UPPER-UUID removes it (default `UUID_HANDLING`). Three pushes reached the fake APNs server with the preset name and duration, and a cancel |
| J3 Trio | `trio` | `override-start` / `-end`, indefinite (43200), `tt-start` / `-end`, `suspend`, `resume`, `settings-change`, `downloads` | all `200`. The override end (DELETE by `created_at` + `eventType`, then re-POST) and the TT end (second POST, same `created_at`) each leave **one** record |
| J3 AAPS | `aaps`, `aaps-v1`, `aaps40` | `tt-start` / `-cancel`, `ps-start`, `loop-off`, `settings-change`, `accept-check` | v3 `201`/`200` (PATCH cancel), v1 acked. Accept predictions: TT and profile switch ignored at default settings on all three; profile store ignored as AAPS's own echo (3.4) or by default (4.0-dev) |
| J4 app-side | `loop`, `trio`, `aaps*`, `cp-aaps` | `carbs`, `carb-edit`, `carb-delete` | Loop PUT/DELETE by `_id` and Trio DELETE by `id` remove the entry. **AAPS: see JL-1** |
| J5 sharing | `loop` | `share`, `share-check`, `follow-loopfollow`, `follow-nightguard`, `follow-xdrip`, `follow-reporter 3` | follower reads, write `401`; caregiver reads and adds; careportal-only `401` on read and write (BF-78); status-only `401`. Every follower read `200` |
| J6 reports | `rep-loop`, `rep-trio`, `rep-aaps` (14 d), `rep-90` (90 d) | seeding; headless smoke of the main page and report tabs (`rep-loop`, `rep-aaps`) | 14-day sites: about 4,000 readings, 4,032 device statuses and 270–290 treatments each. `rep-90`: 25,585 readings, 25,920 device statuses and 1,900 treatments. Pills drawn (IOB, COB, CAGE, SAGE, pump, Loop/OpenAPS). Day to day, Daily Stats, Distribution, Hourly, Percentile, Weekly, Calibrations and Profiles showed data; `rep-aaps` in mmol/L. The smoke script's timing left Week to week, Treatments and Loopalyzer unconfirmed |

## Getting started without the Profile Editor (paths C–G, added later the same day)

These sites and steps were run against `e3adc91d` with the same setup. Each app's decisions are
**read from its code** (per-app sweeps of Loop, Trio and AAPS 3.4 / 4.0-dev source) and replayed
or emulated by the lab. Nothing here was run on a real phone.

| path | site: steps | result |
|---|---|---|
| C Loop | `loop`: `add-later`, `tick`, `status`, `settings-change` | readings stored, **0 profiles** until `settings-change`; the page keeps redirecting to the Profile Editor in between |
| C AAPS | `aaps`: `connect`, `wizard`, `add-later 2` | 1,182 one-at-a-time v3 requests for 2 days, 0 failed; then a Profile Switch and the profile store |
| A Trio | `trio`: `connect`, `finish-onboarding`, `onboard` | 0 profiles after onboarding; the profile arrives with `onboard` (Trio's next cold launch) |
| A AAPS | `aaps`, `aaps40`: `wizard` | profile store `201`, Profile Switch `201`, effective-switch Note `201` |
| D Loop | `loop`: `restore` | import offered; imported basal/ISF/CR/targets/presets/max basal/max bolus/suspend threshold; not imported: insulin model, closed-loop state, dosing strategy |
| D Trio | `trio`: `restore` | import offered; losses: `target_high` replaced by `target_low`; DIA not imported (10 h default) |
| D AAPS 3.4 | `aaps`: `restore` | first-load reads `200`; ACCEPT (fresh install); 41 treatments seen, **0 kept** at default settings |
| D AAPS 4.0 | `aaps40`: `restore` | IGNORE (accept-profile default off); 2 seen, 0 kept; Full sync described |
| F AAPSClient | `aaps40`: `client-bootstrap` | 2 seen, 2 kept |
| E connector | `cgm-loop`, `cgm-trio`, `cgm-aaps` | the real nightscout-connect 0.1.0 Dexcom driver logged in to `fake-share.js` and backfilled 2 days on its first poll (`minutes=2880, maxCount=576`, 565 readings, all `device: nightscout-connect`), then polled every 5 min |
| E Loop | `cgm-loop`: `remote-cgm`, `tick` | the phone uploads no readings; one sender only |
| E Trio | `cgm-trio`: `ns-cgm` ×2 | re-upload of 566 fetched readings: count unchanged (566), no two at one moment, `device` still `nightscout-connect`, record gains Trio's `id` and `filtered`/`unfiltered` |
| E AAPS | `cgm-aaps`: `ns-bg`, `tick` | 500 readings read (first page); none uploaded |
| E sensor gap | `cgm-loop`: `cgm-pause` 11 min, `cgm-resume`, then 6 min | during the pause the connector polled and stored nothing new (newest 05:20). The first poll after resuming asked for `minutes=20, maxCount=4` and got 4. Stored series 05:20, 05:25, 05:30, 05:35 has no gap and no duplicates |
| G Loop → Trio | `loop`: `switch-to-trio` | Trio import of Loop's profile: NO (`mills` is a string); message *Cannot find the Nightscout Profile named "default".*; after Trio's profile, careportal override fails with "the uploaded profile has no Loop settings…" (**after JL-2's delay**) |

### JL-2: remote commands use the previous profile until new data arrives

After a new profile is uploaded, Loop remote commands (careportal Temporary Override,
LoopCaregiver) keep using the **previous** newest profile's `loopSettings` (device token, bundle
id). This lasts until the next reading, device status or treatment write. Measured on `loop` and on
15.0.8 (`loop-1508`):

| moment | e3adc91d | 15.0.8 |
|---|---|---|
| before the switch | 200, push to Loop's token | 200 |
| right after Trio's profile upload | **200, push still to Loop's token** | **200** |
| 20 s later, no new data | **200** | **200** |
| after the next phone cycle (devicestatus) | 500 "the uploaded profile has no Loop settings…" | 500 |

The problem exists on 15.0.8, so it is not a regression. Profile writes do emit `data-received`
(`lib/server/profile.js:46,86,125,201`), and **the mechanism was not determined**. Impact: after a
new phone or reinstall uploads a new device token, commands in that window go to the old phone.
With a looping phone that window is at most one upload cycle (about 5 minutes). Recorded as
[GAP-REMOTE-010](../../../traceability/treatments-gaps.md#gap-remote-010-loop-remote-commands-keep-the-previous-profiles-device-after-a-new-profile-upload):
an ecosystem issue, not filed in the backfix register (maintainer 2026-09-26).

## JL-1: an entry AndroidAPS deletes keeps counting

AAPS deletes by soft delete. On v3 that is `DELETE /api/v3/treatments/{identifier}`, and the server
sets `isValid:false`. On v1 it is a `dbUpdate` that re-sends the record with `isValid:false`. The
v1 API still returns such a record (`GET /api/v1/treatments.json?find[carbs]=20` on `aaps-v1` and
`aaps40` returned it with `isValid:false`). Outside API v3, the server checks `isValid` only for
`OpenAPS Offline` (`lib/data/ddata.js:351`).

The steps, on `cp-aaps`, which has no device status, so COB comes from treatments:

| step | candidate `e3adc91d` COB | 15.0.8 `92d08342` COB |
|---|---|---|
| before | none | none |
| AAPS carbs 40 g (v3 POST) | 40 | 40 |
| AAPS deletes them (v3 DELETE → `isValid:false`) | **40** | **40** |
| control: v1 DELETE of the same record by `_id` | none | not run |

The problem exists on 15.0.8, so it is not a 15.0.9 regression. The following were **read, not
run**: the same mechanism for insulin (IOB), the chart glyph, and the report totals. It is not in
the register. Filing it, and the severity call, are the maintainer's. The walkthrough's J4 row 5
asks the hand check to look at the chart, the COB pill and Reports → Treatments.

## Corrections the walk made to the map

- **Trio's import** fails on a Profile Editor record because of missing fields (`enteredBy`,
  `mills`). The store name `Default` is not the first failure. It also fails on a Loop record
  (`mills` as a string).
- **consumer-impact P5** (Loop override delete by UPPER-UUID) works with the default
  `UUID_HANDLING`. The map no longer lists it as open.
- **End-early paths** for the Loop override, the Trio override and the Trio TT each leave one
  record.

## Lab defects found and fixed during the walk

- A 90-day `backfill` sent 25,585 readings in one request and got `400 Maximum records per request:
  10000`. `up` did not stop. Arrays are now sent in chunks of 500, and a failed backfill makes `up`
  exit non-zero.
- AAPS `accept-check` compared against a phone change "a week ago", so it predicted AAPS would
  accept its own upload. It now uses the time of the lab's last AAPS profile upload.
- The nightguard token modes (`token-path`, `token-header`) and the careportal's form encoding are
  now explicit in the descriptors.

## Not covered

- Every browser check in the walkthrough (the maintainer's hand checks).
- The real-app track ([REAL-APPS.md](../../../tools/review/journey-lab/REAL-APPS.md)).
- Report numbers against a physiological model (phase 2 generator).
- 15.0.8 comparisons other than JL-1.
