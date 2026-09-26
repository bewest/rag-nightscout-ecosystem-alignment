# Journey lab: walk the user journeys by hand

*Contributor-facing. Synthetic data only: never point this at a real site, and never connect a
phone that doses a real person to it. Nothing here is medical advice. Every therapy value in the
lab is a made-up test value.*

This lab stands up Nightscout sites configured the way a Loop, Trio or AndroidAPS user configures
them. You play the person in a browser. The lab plays the phone: each `fire` step sends exactly
what the real app sends, copied from the app's source code, with the source lines cited in
[`clients.js`](clients.js). The journeys, and what "working" means at each step, are in the
[journey map](../../../docs/60-research/remedial/journey-map-15.0.9.md). This file is the script
for walking them.

| file | what it does |
|---|---|
| `lab.sh` | starts, seeds and stops the sites; `fire` runs a step |
| `journey.js` | the steps: what each app does, sent as the app sends it; prints one line per request |
| `clients.js` | the request builders for Loop, Trio, AAPS (3.4 v3, 3.4 v1, 4.0-dev), the followers and the web page itself, each citing its source |
| `household.js` | a deterministic synthetic household (meals, doses, overrides, site changes) used to backfill days of data |
| `apns-log.js`, `preload.js` | a fake Apple push server that logs every Loop remote command the site sends, and the redirect that points the site at it |
| `fake-share.js` | a fake Dexcom Share server over HTTPS. The `cgm-*` sites run the **real** nightscout-connect Dexcom driver against it, so login, polling, backfill and the Dexcom-to-Nightscout mapping are the connector's own |
| [`REAL-APPS.md`](REAL-APPS.md) | the track for people who can run the real apps with simulated pumps |

## Setup

From the root of the alignment repository:

```sh
git -C externals/cgm-remote-monitor-official worktree add --detach "$PWD/externals/work/crm-journey-rc" official/dev   # the candidate
git -C externals/cgm-remote-monitor-official worktree add --detach "$PWD/externals/work/crm-journey-1508" 92d08342    # 15.0.8, optional
export LAB_RC=$PWD/externals/work/crm-journey-rc
export LAB_REF=$PWD/externals/work/crm-journey-1508     # optional: `up --ref <site>` runs the same site on 15.0.8
export LAB_STATE=$HOME/journey-lab-state                # outside any git tree: holds the API secret and tokens
tools/review/journey-lab/lab.sh prep                    # npm ci, once per worktree
tools/review/journey-lab/lab.sh up                      # every site; or name some: up loop cp-trio rep-aaps
tools/review/journey-lab/lab.sh urls                    # addresses and the sharing tokens
```

- **Needs:** docker (`mongo:7`), `n` with node 22.22.0, `curl` and `openssl`.
- **Ports:** sites on 153xx and 15.0.8 copies on 153xx+50, MongoDB on 27095, fake APNs on 17601,
  fake Dexcom Share on 17602.
  All bind to 127.0.0.1.
- **Logging in:** every site is `AUTH_DEFAULT_ROLES=denied`, so the page asks you to log in. Use
  the API secret in `$LAB_STATE/secret`; the lab never prints it.
- **Time zone:** profiles and meal times use this machine's time zone, or `LAB_TZ`.
- **Starting over:** `up <site>` gives that site a fresh, empty database.
- **Keeping a site fresh:** seeded data ages, and after about 15 minutes the pages show stale
  warnings and sound alarms. `lab.sh live <site>` keeps that site's phone uploading every 5 minutes
  (a reading, device status, doses); `lab.sh live stop <site>` ends it. `down` stops all of them.

## The sites

| site | port | app | units | starts | for |
|---|---|---|---|---|---|
| `loop` | 15301 | Loop | mg/dL | empty | J1.A app-first, then J2–J5 |
| `trio` | 15302 | Trio | mg/dL | empty | the same |
| `aaps` | 15303 | AAPS 3.4, NSClient v3 | mmol/L | empty | the same |
| `aaps-v1` | 15304 | AAPS 3.4, NSClient v1 (socket) | mg/dL | empty | J1.A, J3, J4 on the older sync path |
| `aaps40` | 15305 | AAPS 4.0-dev | mg/dL | empty | J1, J3 with 4.0's defaults |
| `cp-loop` | 15311 | Loop | mg/dL | empty | J1.B site-first: Profile Editor, then connect Loop |
| `cp-trio` | 15312 | Trio | mg/dL | empty | the same for Trio |
| `cp-aaps` | 15313 | AAPS 3.4 v3 | mmol/L | empty | the same for AAPS |
| `rep-loop` | 15321 | Loop | mg/dL | 14 days | J6 reports |
| `rep-trio` | 15322 | Trio | mg/dL | 14 days | J6 |
| `rep-aaps` | 15323 | AAPS 3.4 v3 | mmol/L | 14 days | J6 |
| `rep-90` | 15324 | Trio | mg/dL | 90 days | J6.6 |
| `cgm-loop` | 15331 | Loop + nightscout-connect | mg/dL | 2 days of CGM readings from the connector | J1.E CGM first |
| `cgm-trio` | 15332 | Trio + nightscout-connect | mg/dL | the same | J1.E |
| `cgm-aaps` | 15333 | AAPS 3.4 v3 + nightscout-connect | mmol/L | the same | J1.E |

Each site's flags are what that app's setup asks for. Loop sites add `loop override` and
`LOOP_APNS_*`; the others add `openaps`. See map §B1, or the table at the top of `lab.sh`.

## Reading a step's output

```
$ lab.sh fire loop override-start Running
[loop] override-start Running
  ✓ 200    POST /api/v1/treatments [1]  — Loop override start
```

Each line is one request the app would send, with the site's answer. ✓ means the site accepted it.
✗ is shown with the reply. `LAB_VERBOSE=1` also prints the body and the client source lines. Steps
marked "(emulated …)" predict what the app would decide (import a profile, accept a temp target).
Only a real app proves those; see [REAL-APPS.md](REAL-APPS.md).

At any time:
- `lab.sh status <site>` shows what the site holds: profiles, treatments by type and sender, the
  newest device status and reading, and the pushes sent to the phone.
- `lab.sh fire <site> help` lists the steps for that site.

## The walkthrough

Record each check as **pass**, **fail** (what you saw), or **not run**. Step numbers match the
journey map.

### J1.A App first (sites `loop`, `trio`, `aaps`, then `aaps-v1`, `aaps40`)

| # | do | expect |
|---|---|---|
| 1 | open the site, log in with the secret | one "Redirecting you to the Profile Editor" alert, then the Profile Editor with "Default values used" (J1.0) |
| 2 | `fire <site> connect` | the connection works; "the site has no profile yet: nothing to import" (J1.A1–A2). AAPS v3 makes an admin subject: check it on the admin page |
| 3 | `fire <site> onboard` | a new profile record from the app. Reload the Profile Editor: the app's values, in the site's units, with the right times (J1.A3). Loop: store `Default`. Trio: `default`. AAPS: `LabDay` and `LabWeekend` |
| 4 | reload the main page | no redirect; basal line drawn; profile pill |
| 5 | `fire <site> connect` again | the app would now import its own profile: YES (Loop, Trio) |
| 6 | `fire <site> backfill 6`, then watch the page | readings, boluses, carbs and temp basals for 6 h; loop pill (Loop or OpenAPS) recent; IOB, COB, pump reservoir and battery pills show values (J1.A4) |

### J1.B Site first (sites `cp-loop`, `cp-trio`, `cp-aaps`)

| # | do | expect |
|---|---|---|
| 1 | open, log in, go to the Profile Editor | the placeholders: DIA 3, carb ratio 30, ISF 100, basal 0.1, targets 0; "Default values used" |
| 2 | **safety check:** try saving with the placeholders unchanged | note whether the page lets you, and how visible the warning is (15.0.8 allows it too). Then `up <site>` to start clean |
| 3 | fill in every value (any test values), choose the time zone, Save | after a reload the values stay; the main page draws the basal line (J1.B2) |
| 4 | `fire <site> connect` | Loop: NO (not a Loop profile; Loop goes on to its own setup). Trio: NO (decode fails; Trio can only import its own profile shape). AAPS 3.4: ACCEPT (it would replace the phone's profiles) (J1.B3) |
| 5 | `fire <site> onboard`, reload the Profile Editor | the app's record is newest and in use; the typed one is still listed (J1.B4) |
| 6 | Loop only: careportal → Temporary Override | the presets from Loop's profile are offered |

`fire <site> editor-save` sends exactly what the Profile Editor saves. It is there to automate
step 3 when you only want the later steps; the hand check is the real one.

### J1.C–J1.G Other ways to get started (no Profile Editor)

Each app's own code decides these. The lab replays what that code sends, and prints what the code
decides ("read from the code" / "emulated"). The [real-app track](REAL-APPS.md) is the proof.

| # | path | site | do | expect |
|---|---|---|---|---|
| 1 | C Loop | `loop` (fresh) | `fire loop add-later`, then `tick` a few times; open the page | readings arrive, **no profile**: the page keeps redirecting to the Profile Editor. Then `fire loop settings-change`: the profile arrives, the redirect stops |
| 2 | C Trio | `trio` (fresh) | `fire trio add-later` | a profile and **only the last 24 h** of data |
| 3 | C AAPS | `aaps` (fresh) | `fire aaps connect`, then `add-later 7` | a week of readings, treatments and device status, one request each; then a profile switch and the profile. Watch the page stay responsive. A real phone sends up to about 6 months |
| 4 | A Trio timing | `trio` (fresh) | `connect`, `finish-onboarding`, open the page | **no profile yet**; the redirect continues until `onboard` (Trio's next cold launch) |
| 5 | A AAPS wizard | `aaps` (fresh) | `connect`, `wizard` | a profile record, then a Profile Switch and a note, on the chart |
| 6 | D Loop | `loop` after `onboard` | `fire loop restore` | "IMPORT OFFERED", the list of what is imported and **not** imported (insulin model, closed loop, dosing strategy), then a new profile record |
| 7 | D Trio | `trio` after `onboard` | `fire trio restore` | the imported values, and the losses: **top of each target range** set to the bottom, **DIA** replaced by the 10-hour default |
| 8 | D Trio, wrong profile | `cp-trio` after the Profile Editor save | `fire cp-trio restore` | NO IMPORT, and the app's message *Cannot find the Nightscout Profile named "default".* |
| 9 | D AAPS 3.4 | `aaps` after `wizard` + `backfill` | `fire aaps restore` | first-load reads; ACCEPT (fresh install); treatments seen, **0 kept** at default settings. `fire aaps full-sync` explains the way to get them |
| 10 | D AAPS 4.0 | `aaps40` after `wizard` | `fire aaps40 restore` | IGNORE: the profile is not taken by default |
| 11 | E connector | `cgm-loop`, `cgm-trio`, `cgm-aaps` | open the page within a minute of `up`; `lab.sh share` | about 2 days of readings, each from `nightscout-connect` (hover one); `share` shows the connector's login and polls. **The page still redirects to the Profile Editor**: the connector brings no profile |
| 12 | E Loop | `cgm-loop` | `connect`, `onboard`, `remote-cgm`, then `tick` | Loop reads the site's readings and uploads **no** readings of its own; `cgm-status` shows one sender |
| 13 | E Trio | `cgm-trio` | `connect`, `onboard`, `ns-cgm` twice | Trio re-uploads what it fetched; `cgm-status` shows **the same count**, no two readings at one moment, still from `nightscout-connect`, now with `filtered/unfiltered` |
| 14 | E AAPS | `cgm-aaps` | `connect`, `wizard`, `ns-bg`, then `tick` | AAPS reads the readings and uploads none |
| 15 | E sensor gap | any `cgm-*` | `cgm-pause`, wait 11 min, `cgm-resume`, wait 6 min, `cgm-status` | the page shows the gap and a stale warning while paused; after resuming, the connector fills the missing readings in at its next poll |
| 16 | F AAPSClient | `aaps` after data | `fire aaps client-bootstrap` | the caregiver build keeps every treatment it sees |
| 17 | G Loop → Trio | `loop` after `onboard` | `fire loop switch-to-trio` | Trio can't import Loop's profile (NO IMPORT, the "default" message); Trio's profile becomes the newest; the careportal Temporary Override then fails (no `loopSettings`), and in the browser the careportal's override presets are gone |

### J2 Everyday data (any J1.A site after `backfill`)

| # | do | expect |
|---|---|---|
| 1 | `fire <site> tick` a few times, a minute apart, with the page open | new readings and device status appear without a reload; "minutes ago" resets (J2.1, J2.5) |
| 2 | hover the COB and IOB pills | COB says where it came from (Loop or OpenAPS); values plausible (J2.2) |
| 3 | hover the loop pill; look for the prediction line | what the loop did, and when (J2.3) |
| 4 | careportal → Site Change, and Sensor Start | cannula and sensor age reset (J2.4) |
| 5 | open the follower token from `lab.sh urls` in another browser profile, then `tick` | the follower's page updates by itself |

### J3 Day 2 (sites `loop`, `trio`, `aaps`)

| # | site | do | expect |
|---|---|---|---|
| 1 | loop | `fire loop override-start Running` | a bar on the chart named "🏃 Running", 90 min (J3.1) |
| 2 | loop | `fire loop override-end` | the bar ends now; **one** record, not two (`status`) (J3.2) |
| 3 | loop | `fire loop override-start "Sick day" indef` | shown as indefinite |
| 4 | loop | careportal → Temporary Override → a preset | the site says it was sent; `lab.sh apns` shows the push to this site's phone with the preset's name and duration (J3.3) |
| 5 | loop | `fire loop caregiver-override Running`, then `caregiver-cancel` | two more pushes (J5.4) |
| 6 | loop | Profile Editor → Add new → Save, then careportal → Temporary Override | presets gone, or the send fails with "Could not find loopSettings in profile" (J3.6). Then `fire loop settings-change` and try again: works |
| 7 | trio | `fire trio override-start Exercise 60`, then `override-end` | a bar labelled Exercise; after the end, one record with the real length |
| 8 | trio | `fire trio override-start Sick indef` | shown as 43200 min (30 days); the name is in the notes (J3.1) |
| 9 | trio | `fire trio tt-start 140 60`, then `tt-end` | a temp target band; after the end, one record, the band ends now |
| 10 | trio | careportal → Temporary Target, then `fire trio downloads` | the lab predicts whether Trio would pick it up (only with "Allow downloads" on in Trio) |
| 11 | aaps | `fire aaps tt-start`, then `tt-cancel` | a band at 7.8 mmol/L; after cancel it ends now |
| 12 | aaps | `fire aaps ps-start 120 0` | a Profile Switch on the chart. **Known issue BF-123:** the displayed basal/ISF/CR do not change for the 120% |
| 13 | aaps | careportal → Temporary Target and → Profile Switch, then `fire aaps accept-check` | AAPS 3.4 would ignore both with default settings |
| 14 | any | `fire <site> settings-change`, then open the Profile Editor | a **new** record at the top; the old one is still listed (J3.5) |

### J4 Fixing mistakes

| # | site | do | expect |
|---|---|---|---|
| 1 | loop | `fire loop carbs 30`, then `carb-edit 45` | the chart shows 45 g, one entry |
| 2 | loop | `fire loop carb-delete` | gone from the chart |
| 3 | loop | `fire loop override-delete` | the override is gone |
| 4 | trio | `fire trio carbs 25`, then `carb-delete` | gone |
| 5 | aaps | `fire aaps carbs 20`, then `carb-delete` | **JL-1 / BF-135 (found by this lab; fix planned with BF-122):** the entry stays on the site and still counts in COB. Please look at the chart, the COB pill and Reports → Treatments, and note what each shows |
| 6 | any | pencil (edit mode): drag a treatment; Reports → Treatments: edit one, delete one | changes stay after a reload (J4.1, J4.2) |
| 7 | aaps | edit a treatment on the site, then think of the phone | **known BF-122:** AAPS v3 won't see site edits in its history |
| 8 | any | Profile Editor with two or more records: delete the older one | only that record goes (J4.5) |

### J5 Sharing

| # | do | expect |
|---|---|---|
| 1 | `fire loop share`, then `lab.sh urls` | four token links |
| 2 | open each link in its own browser profile (Guest, Incognito). One profile per token: tokens share browser storage | follower: data, no + button. Caregiver: data and a working + button. Careportal-only: nothing (**known BF-78**). Status-only: nothing (J5.1, J5.2) |
| 3 | `fire loop share-check` | the same, as requests: the follower reads (and a write is refused with 401); the caregiver reads and adds; careportal-only and status-only get 401 on everything |
| 4 | admin page: delete the follower subject; reload its page | the link stops working (J5.6) |
| 5 | `fire loop follow-loopfollow`, `follow-nightguard`, `follow-xdrip`, `follow-reporter 14` | every read ✓ (J5.3) |
| 6 | from a follower page, open the clock views from the menu | **known BF-127:** blank on a denied site |

### J6 Reports (sites `rep-*`; log in, menu → Reports)

| # | do | expect |
|---|---|---|
| 1 | last 14 days, Day to day, IOB + COB + basal ticked | every day drawn, with treatments, basal and loop data (J6.1) |
| 2 | Daily Stats, Distribution, Hourly stats, Percentile, Weekly success for the same range | reading counts agree; averages and time in range similar across pages (J6.2) |
| 3 | Treatments: filter by event type; edit and delete one | the filter narrows; changes stick (J6.3) |
| 4 | Profiles | the profile(s) in use during the range (J6.4) |
| 5 | Loopalyzer | basal, bolus and carb patterns drawn (J6.5) |
| 6 | `rep-90`: last 90 days, Week to week, Percentile | complete; then ask for 200 days: refused (limit 186) (J6.6) |
| 7 | `rep-aaps`: any page | mmol/L throughout |

The report data is a synthetic household (`household.js`): three meals and an afternoon snack a
day, carb-count error, day-to-day sensitivity, exercise overrides and temp targets, a site change
every 3 days and a sensor every 10. It exists to make every page non-empty. The numbers are not
physiologically meaningful. Phase 2 will replace it with a physiological model.

### Regressions: the same site on 15.0.8

When something looks wrong, `lab.sh up --ref <site>` stands up the same site on 15.0.8 at port +50,
e.g. `cp-aaps-1508` on 15363. Fire the same steps at it, e.g.
`lab.sh fire cp-aaps-1508 carbs 40`. If 15.0.8 does the same, it is not a 15.0.9 regression.

## Known issues (expected; don't re-report)

Staying in 15.0.9: BF-78 (careportal role alone), BF-124 (tooltip unit conversion), BF-127 (clock
views blank for a token on a denied site), BF-133 (COB "last carbs" names an older entry).

A fix is planned for 15.0.9 but not yet merged, so the candidate `e3adc91d` still shows these:
BF-121 (same-time carbs stored as one), BF-122 (v1 edits not in v3 history), BF-123 (profile-switch
percentage not displayed), BF-125, BF-128, and BF-135 (= JL-1, AAPS-deleted entries keep counting,
found by this lab; fixed with BF-122). When they merge, re-run the matching rows on the new dev head. Details are in the
[backfix register](../../../docs/30-design/remedial/nightscout-backfix-register.md) and map §B5.

## Reporting

Copy the tables above into a dated record next to the journey map, e.g.
`docs/60-research/remedial/journey-lab-15.0.9-<date>.md`. Fill in pass, fail or not run, with the
candidate sha (`git -C $LAB_RC rev-parse --short HEAD`), the browser, and what you saw. Leave out
the API secret, tokens and anything from real data. External testers: open an issue in
nightscout/cgm-remote-monitor that references 15.0.9 and the step number (e.g. "J3.6").

## Stop

```sh
tools/review/journey-lab/lab.sh down     # every site, the fake APNs server, and the database container
```
