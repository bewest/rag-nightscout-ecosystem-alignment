# Nightscout user journey map (15.0.9)

*Living document. Checked against the 15.0.9 candidate, cgm-remote-monitor official/dev `e3adc91d`
(package version 15.0.9; 15.0.8 = `92d08342`), on 2026-09-25. Release PR #8598. Nothing here is
released. Current facts about defects live in the [backfix register](../../30-design/remedial/nightscout-backfix-register.md)
and [queue/work-queue.yaml](../../../queue/work-queue.yaml); lab results live in dated lab records
next to this file. The lab that walks these journeys is [tools/review/journey-lab/](../../../tools/review/journey-lab/README.md).*

**This is not medical advice.** It describes what software does, so that testers can check it.
Nothing here tells anyone what insulin to take or which settings to use. Every therapy value in the
lab is a made-up test value. For changes to your own or your family member's settings, talk to your
care team.

The map has two parts:

- **Part A, for testers** (plain language): the jobs people use Nightscout for, step by step, what
  "working" looks like at each step, and what to watch for. No programming knowledge needed.
- **Part B, for contributors** (technical): for each step, the requests each app sends, the server
  code that handles them, the lab site and step that replays them, the automated coverage, and the
  register items that touch them.

## Words used here

| word | meaning |
|---|---|
| **Nightscout site** | the web page and database a person runs for their own diabetes data |
| **AID app** | an automated insulin delivery app on a phone: **Loop**, **Trio** or **AndroidAPS (AAPS)** |
| **uploader** | anything that sends data to the site (the AID app, a CGM app, the site's own forms) |
| **follower** | anyone or anything that only watches: a parent's phone, a watch app, a report tool |
| **profile** | the therapy settings: basal rates, insulin sensitivity (ISF), carb ratio, targets, insulin duration (DIA) |
| **careportal** | the site's own form for entering treatments and events (the **+** button) |
| **Profile Editor** | the site's page for entering or changing a profile (menu → Profile Editor) |
| **override** (Loop, Trio) | a temporary change to targets and insulin needs, e.g. "Running" for 90 minutes |
| **temp target** (Trio, AAPS) | a temporary glucose target, e.g. 140 mg/dL for an hour |
| **profile switch** (AAPS) | changing to another profile, or the same one at a percentage, for a time or for good |
| **API secret** | the site's master password; whoever has it can change anything |
| **token** | a limited-access link made on the site's admin page, e.g. read-only for a follower |
| **IOB / COB** | insulin on board / carbs on board, as the app reports them |
| **device status** | the app's regular report of what it is doing (loop status, pump battery, predictions) |

## The people

| who | what they want from Nightscout |
|---|---|
| **A person starting on an AID app** | set up a new site, connect the app, see their data |
| **A parent or partner running the site for someone else** | the same, and to watch and help from another phone |
| **An experienced user changing things** | overrides, temp targets, new profiles, fixing wrong entries |
| **A follower or caregiver** | see the data, get alarms, maybe enter carbs or send a remote command |
| **A person going to a clinic visit** | reports over 2 weeks to 3 months that make sense |

---

# Part A: the journeys (for testers)

Each step says **what the person does**, **what working looks like**, and **what to watch for**.
Where something is a **known issue** that will not be fixed in 15.0.9, it says so. Please don't
report those again, but do tell us if they look worse than described.

## J1. Getting started on an empty site

The person has a new site with the settings their app's setup guide asks for. How they get
going depends on where they are coming from. These are the ways the apps themselves expect people to
start. Only path B uses the Profile Editor.

| path | who | how it starts | the profile comes from |
|---|---|---|---|
| **A** app first | new to looping, new site | set up the app, connect it to the site | the app |
| **B** site first | types settings into Nightscout before connecting the app | the Profile Editor | typed on the site, then the app |
| **C** add Nightscout later | already looping, adding a site now | connect the app that is already running | the app, sometimes only after a setting changes |
| **D** new phone or reinstall | the site already has their history | reinstall the app and import from the site | the site (the app's own earlier upload) |
| **E** CGM first | readings already reach the site from the CGM company's cloud through the built-in connector | the site's connector, then the app uses the site as its CGM | the app |
| **F** a caregiver's app | a parent or partner with AAPSClient, LoopFollow or LoopCaregiver | the caregiver's app reads the site | the site |
| **G** changing apps or versions | moving AAPS from 3.4 to 4.0, or NSClient v1 to v3; moving between Loop and Trio | reconnect | depends (see G) |

### J1.0 Open the new site

- **Do:** open the site's address.
- **Working:** the page asks for the API secret (sites set to "denied" for anonymous visitors), or
  shows an empty chart. After logging in, one message says *"Redirecting you to the Profile Editor
  to create a new profile."* and the Profile Editor opens. The message appears **once**, not in a loop.
- **Watch for:** the message repeating; a blank page; an error instead of the Profile Editor.

### Path A: the app first

#### J1.A1 Connect the app

- **Do:** in the app, enter the site address and the API secret (Loop, Trio). AndroidAPS 3.4 with
  "NSClient v3" asks for a **token**, made on the site's admin page with the *admin* role, not the
  API secret.
- **Working:** the app says it is connected. On Trio, a note "Trio connected" appears on the chart.
- **Watch for:** the app saying the secret or token is wrong when it isn't.

#### J1.A2 The app looks for settings to import

- **Do:** nothing: on an empty site there is nothing to import.
- **Working:** the app goes on to its own setup without an error.

#### J1.A3 The app sends its settings

- **Do:** finish the app's setup so it saves its therapy settings.
- **Working:**
  - the Profile Editor shows the app's profile, with the same basal rates, ISF, carb ratios and
    targets, in the right units;
  - the main page stops redirecting and draws the basal line;
  - Loop sites: the careportal list has **Temporary Override**, offering the override presets
    set up in Loop.
- **Watch for:** values in the wrong units (mg/dL shown as mmol/L or the reverse); times shifted by
  hours (time zone); the redirect still happening.
- **When the profile arrives differs by app:**
  - **Loop** sends it when the person taps "Save Settings" at the end of onboarding.
  - **Trio** does **not** send it at the end of onboarding. It arrives the next time Trio is
    fully closed and reopened, or when a setting is first edited. Until then the site keeps
    redirecting to the Profile Editor. Please note whether that tempts you to type a profile there
    (path B, with its problems).
  - **AAPS**'s setup wizard sends the profile when it is saved, and then requires a
    **profile switch** before looping. That appears on the site as a "Profile Switch" and a note.

#### J1.A4 The app starts sending data

- **Do:** let the app run for a while.
- **Working:** glucose readings every 5 minutes; boluses, carbs and temp basals on the chart;
  the loop pill (Loop or OpenAPS) shows a recent time; IOB, COB, pump reservoir and battery pills
  show values close to what the app shows.

### Path B: the site first (careportal)

#### J1.B1 Type a profile into the Profile Editor

- **Do:** on the Profile Editor, replace **every** starting value with the person's own.
- **Working:** the page says "Default values used" until real values are saved.
- **Watch for (safety):** the starting values are placeholders: insulin duration 3 h, carb ratio 30,
  ISF 100, basal 0.1 U/h, and **targets of 0**. The page lets you save them unchanged. Check that
  the warning is easy to see, and note anything that made it easy to miss a field. (15.0.8 behaves
  the same way. This is not new in 15.0.9, but it matters most on day one.)

#### J1.B2 Save it

- **Do:** press Save. This needs the API secret.
- **Working:** after a reload the values are still there. The main page draws the basal line.
- **Watch for:** "Your device is not authenticated yet" when you are logged in; values changing
  after a reload.

#### J1.B3 Connect the app

What happens next depends on the app. Each app handles a profile it didn't make differently:

| app | what the app does with a profile typed into the site | what working looks like |
|---|---|---|
| **Loop** | does **not** offer to import it (Loop only imports a profile Loop made). Loop's own setup continues. | Loop connects; the person sets up therapy in Loop; Loop then sends its own profile, which becomes the one the site uses |
| **Trio** | **cannot import it.** Trio only reads profiles shaped like the ones Trio uploads (named "default", with fields the Profile Editor doesn't write), so its import fails | Trio connects; the person enters settings in Trio; Trio sends its own profile |
| **AAPS 3.4** | with "accept profile from Nightscout" **on (the default in 3.4)**, it may **replace the profiles on the phone** with the one from the site | the phone's profile matches what was typed, or the phone keeps its own if it is newer; either way the person checks the phone before looping |
| **AAPS 4.0 (in development)** | accepting profiles from the site is **off by default** | the phone keeps its own profile |

- **Watch for (safety):** a profile on the phone changing without the person expecting it
  (AAPS 3.4). The lab only shows what AAPS *would* do; a real phone is the proof.

#### J1.B4 After the app sends its own profile

- **Working:** the site uses the **newest** profile (by its start date). The Profile Editor shows
  the app's record as newest; the older typed one is still in the list.
- **Watch for:** a careportal "Profile Switch" offering names that no longer exist; on Loop sites,
  remote commands failing (see J3.6).

### Path C: adding Nightscout to an app that is already running

The person has looped for weeks or months and now adds a site. Each app behaves differently. The
Loop and Trio rows are read from the apps' code; a real app confirms them.

| app | what reaches the site | what to check |
|---|---|---|
| **Loop** | only data from now on. Loop marks its history as already sent at the moment the service is added, before the site address is typed in. **No profile** until a therapy setting changes | readings and doses appear but the site keeps redirecting to the Profile Editor; after any settings change in Loop, the profile arrives and the redirect stops |
| **Trio** | its profile when upload is switched on, and **at most the last 24 hours** of readings, doses, carbs, overrides and temp targets | the last day is filled in, nothing older |
| **AAPS** | **everything the phone still holds**, up to about 6 months, one record at a time: readings, treatments, profile switches, device status (about 290 a day), then the profile | the site stays responsive while this runs; reports then cover the whole period; no duplicates |

- **Watch for:** the Loop case, where data flows but there is no profile, and a person is pushed
  into the Profile Editor. A profile made there breaks Loop's remote commands (J3.6).
- **Found by the lab (JL-2, also on 15.0.8):** after any new profile upload, remote commands keep
  going to the phone in the *previous* profile until the next reading or status arrives. On a new
  phone that means a few minutes of commands still going to the old phone.

### Path D: new phone or reinstall, restoring from the site

The site already holds the person's profile and history. The app is reinstalled and asked to take
its settings from the site. Nothing here is automatic: the person reviews every value.

| app | what the app imports | what it does **not** bring back | what the person sees |
|---|---|---|---|
| **Loop** | basal, ISF, carb ratio, targets, pre-meal range, override presets, max basal, max bolus, suspend threshold, from a profile **Loop** uploaded | the insulin model, whether closed loop was on, the dosing strategy, an active override. If the lowest target is below the suspend threshold, the **whole** target schedule is cleared (and the pre-meal range the same way) and has to be entered again | "Settings Found … you will still need to review the imported settings", then every settings screen. If the newest profile isn't Loop's, the import is **silently skipped** |
| **Trio** | basal, ISF, carb ratio, and the **low** end of each target, from a profile **Trio** uploaded | **insulin duration** (DIA) is not imported and is set to Trio's 10-hour default. The **top of each target range** is lost (set equal to the bottom). Schedule times not on a half hour move to midnight | the values fill the settings screens for review. A profile Trio can't read (made by Loop or the Profile Editor, or none at all) shows *Cannot find the Nightscout Profile named "default".*, even when a "Default" profile is there. A carb ratio, basal or ISF of 0 or less shows its own "Import aborted" message |
| **AAPS 3.4** | the newest profile, automatically, when NSClient first connects (the "accept profile" setting is on by default in 3.4). It also looks at the last 100 days of treatments but, at default settings, **keeps none** | treatments, so IOB history is not rebuilt, unless the person runs **Full sync** (a menu item that warns it "may take many hours") | the profile appears in Local Profile; a profile switch is still needed |
| **AAPS 4.0 (dev)** | nothing by default (accepting the profile is off) | the profile, until the person turns the setting on or runs Full sync | an empty profile screen |
| **AAPS from a settings file** | profiles, and the site address and token, from an AAPS export file, not from the site | — | reconnects by itself. On 4.0 it probably uploads the restored profile again as a new record (read, not run) |

- **Watch for (safety):** values that change on import (Trio's targets and DIA, times moved to
  midnight); an import that fails with a misleading message; AAPS 3.4 taking a profile the person
  didn't expect.

### Path E: CGM first, through the built-in connector

The person's CGM readings reach the site first, from the CGM company's cloud (for example Dexcom
Share, or LibreLinkUp), through Nightscout's built-in connector. The AID app then uses **the site
as its CGM**, and uploads its own profile, doses and status.

#### J1.E1 Turn on the connector

- **Do:** the site owner adds `connect` to `ENABLE`, and sets the source and that account's login
  (`CONNECT_SOURCE=dexcomshare` with `CONNECT_SHARE_ACCOUNT_NAME` / `CONNECT_SHARE_PASSWORD` /
  `CONNECT_SHARE_REGION`; or `CONNECT_SOURCE=linkup` with `CONNECT_LINK_UP_*`).
- **Working:**
  - Within a minute or so of starting, readings appear, including up to **2 days** of history from
    Dexcom (LibreLinkUp gives about 12 hours).
  - Then a new reading about every 5 minutes.
  - Each reading says it came from `nightscout-connect` (hover a reading, or Reports).
- **Watch for:**
  - A typo in `CONNECT_SOURCE`: the site starts without complaint and quietly runs a built-in test
    driver instead of the real one.
  - The page still redirects to the Profile Editor. That is expected: **the connector brings readings only, never a profile.**

#### J1.E2 The app uses the site as its CGM

| app | where to set it | does it send readings back to the site? |
|---|---|---|
| **Loop** | CGM → "Nightscout Remote CGM" (its own site address and secret) | **no** |
| **Trio** | CGM → "Nightscout" | **yes**, if "Upload Glucose" is on (it is on by default, although the screen says "Default: OFF"). The site merges each one with the connector's reading at the same moment, so no duplicate appears, but some fields of that reading are rewritten |
| **AAPS** | BG source → "NSClient BG" | **no** |

- **Working:** one reading per 5 minutes on the site, never two at the same moment. The app loops
  on those readings. Its profile, doses and status appear as in path A.
- **Watch for:**
  - Two readings a few seconds apart. That happens if the app *also* has its own CGM connection
    to the same sensor.
  - A gap when the sensor loses signal. The connector should fill it in when readings resume.
- **Known issue (read, not yet re-measured on 15.0.9):** if Dexcom ends the connector's session
  early, readings can stop until the connector logs in again, which happens daily.

### Path F: a caregiver's app starts from the site

- **AAPSClient** (the caregiver build of AAPS) takes the profile and every treatment from the site
  on first connect (100 days). On 4.0, a client paired with the person's phone takes its profiles
  from the phone's published settings instead.
- **LoopFollow** reads the newest profile for Loop's or Trio's remote-command details.
  **LoopCaregiver** reads Loop's override presets from it. Both need the **app's** profile to be the
  newest one: a profile made in the Profile Editor breaks them (J3.6).
- **Working:** the caregiver's app shows the same readings, treatments and presets as the site.

### Path G: changing apps or versions on the same site

- **AAPS NSClient v1 → v3 (3.4):** AAPS downloads the last 100 days again, and takes the profile if
  its accept setting is on. Nothing is uploaded twice.
- **AAPS 3.4 → 4.0:** NSClient v1 is gone in 4.0. A v1 user may end up with no sync until they
  turn on v3. Unconfirmed; the lab can't show it.
- **Loop ↔ Trio on one site:**
  - Neither app can import the other's profile.
  - The newest profile wins, so after moving from Loop to Trio, Loop-only features on the site stop:
    careportal override presets and Loop remote commands.
  - Trio doesn't download treatments that Loop, iAPS or AAPS entered.

## J2. Everyday data flowing in

- **J2.1** Readings every 5 minutes with trend arrows; "x minutes ago" counts up; a gap shows as a gap.
- **J2.2** Boluses, carbs and temp basals appear where the app put them. The IOB and COB pills are
  close to the app's numbers. Hovering over COB says where the number came from (Loop or OpenAPS).
- **J2.3** Device status: the Loop/OpenAPS pill shows the last loop time and, on hover, what the
  loop did. The pump pill shows reservoir and battery. Loop and OpenAPS draw a prediction line.
- **J2.4** Site change or sensor start entered from the careportal: the cannula age and sensor age
  pills reset.
- **J2.5** A follower's page updates by itself, without a reload.
- **Watch for:** a pill stuck on an old time while the app is running; COB or IOB very different
  from the app; duplicates of the same bolus or carbs.
- **Known issue (BF-121; a fix is planned for 15.0.9 but not yet merged):** two carb entries at exactly the same time can be stored as one.
- **Known issue (BF-133):** the COB pill's "last carbs" can name an older entry.

## J3. Changing things for a while (day 2)

### J3.1 Start an override or temp target in the app

- **Working:** a bar on the chart with the name and length. Loop sites also show the override pill.
- **Differences between apps (not defects):**
  - Loop sends an "indefinite" override as indefinite.
  - Trio sends it as 30 days (43200 minutes), labelled **Exercise**, even when the preset has
    another name. The name is in the notes.
  - Trio does not send the override's percentage or target to the site.

### J3.2 End it early in the app

- **Working:** the bar ends at the time it was ended, with no second copy left behind.

### J3.3 Start one from the site (careportal)

- **Loop:** careportal → **Temporary Override** → choose a preset. The site sends it to the phone
  as a push. It needs the API secret or an admin token, and Loop's presets appear only if Loop's
  profile is the newest one. Loop confirms on the phone. The site's own record appears when Loop
  uploads it.
- **Trio:** careportal → **Temporary Target**. Trio picks it up only if "Allow downloads" is on
  in Trio (it is off by default).
- **AAPS:** careportal → **Temporary Target** or **Profile Switch**. AAPS applies it only if its
  matching "accept … from Nightscout" setting is on (off by default in 3.4; on in the AAPSClient
  follower app).
- **Watch for:** the site saying it was sent when it wasn't; a clear message when it can't be sent
  (15.0.9 improved these messages).

### J3.4 Profile switch with a percentage (AAPS)

- **Working:** the chart and profile name pill show the switch.
- **Known issue (BF-123; a fix is planned for 15.0.9 but not yet merged):** the percentage is **not** applied to the basal, ISF and carb ratio the
  site displays. The site shows the base profile's values. AAPS itself uses the percentage.

### J3.5 Change settings in the app

- **Working:** the site gets a **new** profile record each time (apps never edit the old one). The
  Profile Editor's list grows; the newest is used. The Reports "Profiles" page shows the change.

### J3.6 Make another profile on the site

- **Do:** Profile Editor → "Add new" (or edit the newest record) → Save.
- **Working:** the new record becomes the one the site uses.
- **Watch for (Loop sites):** Loop's remote commands and the careportal's override presets read the
  **newest** profile. After a profile made on the site, they stop working ("Could not find
  loopSettings in profile") until Loop sends its settings again. Please check how clear this is to
  a person.

## J4. Fixing mistakes

- **J4.1 Edit on the site:** drag a treatment in edit mode, or edit it in Reports → Treatments.
  The change stays after a reload, and IOB/COB follow the new time.
- **J4.2 Delete on the site:** Reports → Treatments → delete, or drag past the left edge.
- **J4.3 Edit or delete in the app:** the site follows. Loop edits carbs in place and deletes
  overrides. Trio deletes carbs. AAPS marks the entry as invalid instead of removing it.
  - **Found by this lab (2026-09-25, also on 15.0.8; BF-135, to be fixed in 15.0.9 with BF-122, not yet merged):** an entry AAPS has deleted stays on the site.
    Nightscout still counts it, e.g. deleted carbs keep counting in the site's own COB. Please note
    where you see such an entry (chart, COB, reports).
- **J4.4 Which way changes travel (not defects):** changes made on the site do **not** go back to
  Loop or Trio. AAPS may pick up treatments, depending on its settings.
  - **Known issue (BF-122; a fix is planned for 15.0.9 but not yet merged):** edits made on the
    site through the older API are not seen in the history AAPS syncs from.
- **J4.5 Delete a profile record:** Profile Editor → delete (only when there is more than one).
  Deleting one named profile inside a record takes effect on Save.
- **Known issue (BF-124):** a treatment's tooltip can convert a glucose value that is already in
  display units.

## J5. Sharing and handing over control

- **J5.1 A follower who only watches:** admin page → new subject with the **readable** role → share
  its link. The link shows the data. There is no **+** button, and the follower can't change anything.
- **J5.2 A caregiver who enters carbs:** a subject with **readable** and **careportal**. The +
  button works.
  - **Known issue (BF-78):** **careportal** on its own does nothing on a "denied" site. The role
    can add treatments but cannot read, and adding needs reading.
- **J5.3 Follower apps:**

  | app | how it logs in |
  |---|---|
  | LoopFollow | makes its own read-only subject from the API secret |
  | nightguard | a token |
  | xDrip+ follower | the API secret |
  | Nightscout Reporter | a token |

  Each should show the same readings as the site.
- **J5.4 Remote commands:**
  - **Loop:** LoopCaregiver or the careportal sends overrides, carbs and boluses through the site to
    the phone. This needs the API secret or an admin token, and the site's Apple push settings.
  - **Trio:** commands go from LoopFollow straight to the phone. The site only stores the phone's
    address.
  - **AAPS:** commands travel as careportal entries through the site.
- **J5.5 Alarms:** a follower gets alarms. Silencing from a read-only token silences only that
  page. Silencing with admin rights silences every page.
- **J5.6 Taking access back:** delete the subject on the admin page. Its link stops working.
- **Known issue (BF-127):** the clock views opened from the menu are blank for a token viewer on a
  "denied" site.

## J6. Looking back: reports

- **J6.1** Reports with a token or the secret. Choose the last 14 days. Day to day, with the IOB, COB
  and basal boxes ticked, shows each day's readings, treatments and loop activity.
- **J6.2** Daily Stats, Distribution, Hourly stats, Percentile and Weekly success agree with each
  other: the same number of readings, and similar averages and time in range.
- **J6.3** Treatments: the new event-type filter narrows the list. Edit and delete work (J4).
- **J6.4** Profiles: shows each profile that was in use during the range.
- **J6.5** Loopalyzer (Loop and OpenAPS/AAPS/Trio sites): draws basal, bolus and carb patterns.
- **J6.6** 90 days: Week to week and the percentile chart handle it. Ranges over 186 days are refused.
- **Watch for:** a report showing nothing for a range that has data; numbers that differ between
  pages for the same range; mmol/L sites showing mg/dL numbers.
- **Note:** 15.0.9 counts some things differently from 15.0.8 (duplicate readings, COB taken from
  the app). A1c estimates and report totals can shift a little. The release notes describe this.

---

# Part B: contributor layer

Client facts below come from each client's source. The per-client surveys give file:line anchors:
[`reports/consumer-impact-15.0.9/clients/`](../../../reports/consumer-impact-15.0.9/clients/). The
lab replays them from [`tools/review/journey-lab/clients.js`](../../../tools/review/journey-lab/clients.js),
where every builder cites its source line. Server refs are to the candidate tree `e3adc91d`.

## B1. Flag sets (what each app's setup asks for)

| site | `ENABLE` (beyond the defaults) | other |
|---|---|---|
| Loop | `careportal basal iob cob bwp boluscalc pump profile sage cage iage bage loop override` | `LOOP_APNS_KEY`, `LOOP_APNS_KEY_ID`, `LOOP_DEVELOPER_TEAM_ID` (10 chars), `LOOP_PUSH_SERVER_ENVIRONMENT` for remote commands (`lib/server/loop.js:16-29`) |
| Trio, AAPS | the same with `openaps` instead of `loop override` | the `override` plugin reads `loop.override` only (`lib/plugins/override.js:23`), so it adds nothing for Trio |
| all | `SHOW_PLUGINS` lists the pills (its default is `dbsize` only, `lib/settings.js:34`); `AUTH_DEFAULT_ROLES=denied` (recommended by the release notes); `DEVICESTATUS_ADVANCED` defaults to true (`lib/server/env.js:304`) | `API_SECRET` ≥ 12 characters (`env.js:122-127`) |

Default-on plugins (`lib/settings.js:182`): bgnow, delta, direction, timeago, devicestatus, upbat,
errorcodes, profile, bolus, dbsize, runtimestate, basal, careportal (+ treatmentnotify).

## B2. What each app sends, by journey step

| step | Loop | Trio | AAPS 3.4 (v3; v1 socket) |
|---|---|---|---|
| auth | `api-secret` SHA-1 only; no tokens | `api-secret` SHA-1 only | v3: admin token → JWT (`/api/v2/authorization/request/<token>`); v1: `authorize` over socket.io with the secret |
| J1.A2 import | `GET /api/v1/profile/current` during onboarding; imports only a Loop-shaped record (`loopSettings`, `enteredBy`, store `Default`, `ETC/GMT±N` tz, `minimumBGGuard`), otherwise silently skips | `GET /api/v1/profile.json?count=1`, decoded as `[FetchedNightscoutProfileStore]` (`Trio/Sources/Models/RawFetchedProfile.swift:3-11`: requires `_id`, `enteredBy`, numeric `mills`, `created_at`, and every store entry with an integer `carbs_hr` and `units`), then `store["default"]` (lower case). So a Profile Editor record (no `enteredBy`/`mills`) and a Loop record (`mills` as a string) both fail; aborts on a carb ratio or basal ≤ 0 | continuous: replaces the local profile store when `NsClientAcceptProfileStore` (default **true** on 3.4, false on 4.0-dev) and `createdAt > LocalProfileLastChange` **or** `createdAt` is whole seconds |
| J1.A3 first upload | at "Save Settings" (held until push registration finishes) | **not** at the end of onboarding: next cold launch or first settings edit (`OnboardingRootView.swift:812-815`, `BuildDetails.swift:102-116`) | on profile save (`processChangedProfileStore`), then the wizard's required Profile Switch (PS + EPS `Note`) |
| J1.C add later | no backfill: service created before credentials, uploads short-circuit to success and advance anchors (`NightscoutService.swift:198-201…`, `RemoteDataServicesManager.swift:53-58, 500-513`); no profile until a settings change | profile on upload toggle; watchers catch up ≤ 24 h (`GlucoseStored+helper.swift:85-88`, `PumpEvent+helper.swift:132-139`) | every retained record from id 0, one `nsAdd` each, incl. devicestatus (`DeviceStatusDao.kt:35-37`); retention 186 d |
| J1.D restore | onboarding import only (`OnboardingUICoordinator.swift:324-343`); not imported: insulin model, closed-loop, dosing strategy | onboarding import only; `target_low` for both ends, DIA not imported (10 h default), 30-min grid; every failure → "Cannot find … "default"" | first load: BG (if NS BG), treatments −100 d, last profile store, devicestatus −7 min; keeps no treatments at default switches; Full sync overrides |
| J1.E CGM | Nightscout Remote CGM: `GET /api/v1/entries?find[dateString]…&count=24`, `shouldSyncToRemoteService=false` | `GET /api/v1/entries/sgv.json?count=1600&find[dateString][$gte]=…`; re-POSTs when upload+uploadGlucose (default true) | NSClient BG; `bgUploadEnabled` false for NS source |
| J1.A3 profile | `POST /api/v1/profile` with an **array**; `defaultProfile:"Default"`, `mills` as a string, `store.Default` (dia 6, `ETC/GMT+N`), `loopSettings{overridePresets, deviceToken, bundleIdentifier, …}`; no `_id`; a new record per change | `POST /api/v1/profile.json` (one object); `store.default`, IANA tz, top-level `deviceToken`/`bundleIdentifier`/`teamID`/`isAPNSProduction`/`overridePresets`; a new record per change | v3 `POST /api/v3/profile` (`app:"AAPS"`, every local profile in `store`); v1 `dbAdd` profile; a new record per change |
| J3.1 override / TT | `Temporary Override`, `_id` = UPPER-case UUID (moved to `identifier` by `UUID_HANDLING`), `durationType:"indefinite"` or `duration` (min), `correctionRange` mg/dL, `insulinNeedsScaleFactor` | override = `Exercise` (preset name in `notes`), **no id**, indefinite = 43200; TT = `Temporary Target`, `targetTop = targetBottom`, **no id**, no `units` | `Temporary Target` (v3: `units:"mg/dl"`; v1: the user's units); `Profile Switch` with `profileJson` (a string), `percentage`, `timeshift` (ms); effective switch as a `Note`. v3 creates send **no `identifier`**: the server assigns it |
| J3.2 end early | re-POST with the same UUID and the actual (fractional) duration; stored as **one** record (lab-verified) | `DELETE /api/v1/treatments.json?find[created_at][$eq]=…&find[eventType][$eq]=Exercise`, then re-POST; TT: a second POST with the same `created_at` and the real duration. Both leave **one** record (lab-verified) | v3 `PATCH /api/v3/treatments/{identifier}` (shortened duration); v1 `dbUpdate` by `_id` |
| J4.3 delete | `DELETE /api/v1/treatments/<UUID>` (overrides marked deleted); carbs: one `PUT` (single object) / `DELETE` by the cached hex `_id` | `DELETE …?find[id][$eq]=<UUID>` (fat/protein entries share one id, so one DELETE removes them all) | v3: HTTP `DELETE /api/v3/treatments/{identifier}` without `permanent`, and the server marks `isValid:false`; v1: `dbUpdate` re-sending the record with `isValid:false`. **See JL-1** |
| J3.3 site → app | only by APNs push (`POST /api/v2/notifications/loop`, needs `notifications:loop:push`) | polls carbs and TT only if "Allow downloads" (off by default); skips its own and other AID apps' `enteredBy` | TT, profile switch, carbs, insulin, therapy events, running mode: each behind its own accept switch (off by default in 3.4; forced on in AAPSClient) |
| J2 data | `Correction Bolus`, `Carb Correction`, `Temp Basal` (suspend = rate 0); device status under `loop`, `device:"loop://…"` | `Bolus`/`SMB`, `Carb Correction`, `Temp Basal`, suspend/resume as `Note`; device status under `openaps`, no `created_at` | `Correction Bolus`/`Meal Bolus`/SMB, `Carb Correction`, `Temp Basal`, `OpenAPS Offline`; device status under `openaps` |

Followers: LoopFollow (`?token=`; makes subject `LoopFollow` [readable] from the secret; remote via
its own APNs key), LoopCaregiver (secret; `POST /api/v2/notifications/loop` with Loop's OTP),
nightguard (token → JWT), xDrip+ follower (secret), Nightscout Reporter (`?token=`; per-day reads
with large counts, `find[eventType]=Profile Switch`).

## B3. Server behaviour each step depends on

| behaviour | code (e3adc91d) |
|---|---|
| empty-site redirect, once per load | `lib/client/renderer.js:1093-1101`, flag at `:16`; only while `basal` is enabled |
| Profile Editor defaults and the "Enter every profile value" check (numbers only) | `lib/client-core/profile-editor/default-profile.js:3-24`; `lib/profile/profileeditor.js:57-67, 628-631` |
| Profile Editor save = `PUT /api/v1/profile/` (upsert; needs `api:profile:update`); menu entry needs admin | `profileeditor.js:669-676`; `lib/api/profile/index.js:86,119`; `views/index.html:172` |
| current profile = newest `startDate`, then `_id` | `lib/server/profile.js:10`; client `lib/profilefunctions.js:435-450` |
| Profile Switch handling (`profileJson` injected as `name@@@@@mills`; percentage/timeshift only with `CircadianPercentageProfile`) | `profilefunctions.js:364-427, 124-170` |
| Temporary Override drawn from treatments (chart only); pill from device status `loop.override` | `renderer.js:215-270, 356-425`; `lib/plugins/override.js:10-60` |
| careportal event types; Loop's override/remote entries need `loopSettings.overridePresets` in the newest profile | `lib/plugins/careportal.js:15-101`; `lib/plugins/loop.js:86-184, 93-101` |
| Loop push: env checks, `loopSettings.deviceToken`/`bundleIdentifier` from `profiles[0]`, provider shut down after each push (BF-134, #8770) | `lib/server/loop.js:16-58` |
| built-in roles; token link; JWT exchange (8 h) | `lib/authorization/storage.js:231-238, 288-290`; `lib/authorization/endpoints.js:31-39` |
| alarm silence needs `notifications:*:ack`; `denied` enforced on the live socket | `lib/api3/alarmSocket.js:144`; 9765e8cd |
| reports: per-day queries, 186-day limit, devicestatus only when IOB/COB/OpenAPS ticked or Loopalyzer | `lib/report/reportclient.js:35, 420, 445, 613-800` |

## B4. Coverage by journey

| step | journey lab (site: step) | other automated / hand coverage | register items |
|---|---|---|---|
| J1.0 | any empty site: open it | manual lab 2026-09-23 #9 (`empty`) | — |
| J1.A1–A3 | `loop|trio|aaps|aaps-v1|aaps40`: `connect`, `onboard`, `status` | rc-soak profile POSTs (Loop shape); `tools/aaps/fixtures` | BF-99 (merged); OID-PROFILE-RESEND (open) |
| J1.A4, J2 | same sites: `backfill`, `tick` | rc-soak 72 h (all three shapes); manual lab #10 (COB) | BF-121, BF-133 (open) |
| J1.B1–B4 | `cp-loop|cp-trio|cp-aaps`: Profile Editor by hand, then `connect` (import/accept emulation), `onboard` | **none automated**; only a real app proves the import: real-app track | — |
| J1.C | `loop|trio|aaps`: `add-later` | — | — |
| J1.D | after `onboard` + data: `restore` (Loop/Trio import summary; AAPS first load + accept with a fresh install) | — | — |
| J1.E | `cgm-loop|cgm-trio|cgm-aaps`: the real nightscout-connect Dexcom driver against `fake-share.js`; `cgm-status`, `cgm-pause/-resume`; Loop `remote-cgm`, Trio `ns-cgm`, AAPS `ns-bg` | connector-soak (NS→NS source only) | BF-45; Dexcom session recovery (read) |
| J1.F | `client-bootstrap` (AAPSClient), `follow-loopfollow` | — | — |
| J3.1–J3.2 | Loop `override-start/-end/-delete`; Trio `override-start/-end`, `tt-start/-end`; AAPS `tt-start/-cancel`, `ps-start` | rc-soak (finite Loop override, Trio TT start, AAPS v3 PUT); object-id lab (UUID `_id` + v3 PATCH) | consumer-impact P5 (Loop override delete by UUID: works with the default `UUID_HANDLING`; never deletes with `UUID_HANDLING=false`, same on 15.0.8); OID-V3-EDIT-MERGE (open) |
| J3.3 | Loop careportal override by hand + `apns`; Trio `downloads`; AAPS `accept-check` | apns-shutdown probe; rc-soak remote commands | BF-134 (merged) |
| J3.4 | AAPS `ps-start 120` | `tools/lab/triage-2026-09/profile-switch-percentage.js` | **BF-123 (open)** |
| J3.5–J3.6 | `settings-change`; Profile Editor "Add new" by hand, then `caregiver-override` | — | — |
| J4 | by hand in the browser; app side: Loop `carb-edit/-delete`, `override-delete`; Trio `carb-delete`; AAPS `carb-delete` | rc-soak edits/deletes; object-id lab; manual lab #1–4, #11 (drag) | BF-103 (merged), BF-122, BF-124 (open); **JL-1** (new, below) |
| J5 | `share`, `follow-loopfollow`, `follow-nightguard`, `follow-xdrip`, `follow-reporter`, `caregiver-*` | rc-soak followers; manual lab #5–6 (alarms, tokens) | BF-78, BF-127 (open); BF-17/30/47, BF-126 (merged) |
| J6 | `rep-loop|rep-trio|rep-aaps` (14 d), `rep-90` (90 d) | — | #8584, #6066 (fixed in dev, confirmation pending) |

## B5. Findings from walking the journeys

**JL-1 (register id BF-135, reserved): an entry AndroidAPS deletes keeps counting on the site**
(reproduced 2026-09-25, candidate `e3adc91d` and 15.0.8 `92d08342`). Maintainer decision
2026-09-25: fixed in 15.0.9 together with BF-122 (branch `bf/v1-writes-v3-history`, not yet
merged). Records with `isValid:false` will count as deleted in v1 reads, the in-memory data and
COB/IOB; v3 search and history keep the tombstones. AAPS deletes by soft delete: v3 `DELETE`
(the server sets `isValid:false`) or v1 `dbUpdate` with `isValid:false`. Outside API v3, the
server honours `isValid` only for `OpenAPS Offline` (`lib/data/ddata.js:351`). The record is still
returned by `GET /api/v1/treatments.json`, and it still counts in the treatment-derived COB.

The lab's steps, on `cp-aaps` (no device status, so COB comes from treatments):

| step | COB (`/api/v2/properties/cob`) |
|---|---|
| AAPS carbs 40 g | 40 |
| AAPS deletes them (v3 DELETE, `isValid:false`) | still 40 |
| **control:** hard v1 DELETE of the same record | gone |

15.0.8 gives the same results. The same mechanism would apply to insulin (IOB), the chart and the
reports; those were read, not run.

**JL-2: remote commands use the previous profile until new data arrives** (reproduced
2026-09-25 on `e3adc91d` and 15.0.8; not in the register). After a new profile is uploaded, Loop
remote commands keep using the previous profile's `loopSettings` until the next reading, device
status or treatment is written. Measured with `loop`'s `switch-to-trio`: the careportal override
answered 200 and pushed to Loop's old token right after the upload and again 20 s later. It failed
correctly ("the uploaded profile has no Loop settings…") only after the next phone cycle. Profile
writes emit `data-received`; the mechanism was not determined. Details are in the lab record.

## B6. Gaps this map exposes

- **Onboarding imports are only emulated.** Loop's and Trio's import and AAPS's accept rules run
  in the lab as re-implementations cited to source. Only the real-app track proves them.
- **The site-first path has no automated test** anywhere (J1.B).
- **Report numbers need realistic data.** Phase 1 data is a deterministic toy household
  (`household.js`). Phase 2 replaces it with the UVA/Padova model from cgmsim-lib and behaviour fitted
  from the parquet stores. The fitted parameters stay local and uncommitted; the repository ships
  hand-set defaults.
- **Several client actions had no fixture before this lab:** the Trio profile, the Trio override
  end, the Trio TT end, the AAPS TT cancel, Loop's indefinite override and delete by UUID, and the
  LoopFollow subject flow.
