# Integration questionnaire: default answers for Loop, Trio, AndroidAPS and OpenAPS, read from their source

*Contributor-facing.* **Snapshot — describes 2026-10-18. Status: current; every answer is a default
for the project named in its column to correct.** Repository facts are read at this repository's
`57a6db95`; controller facts at the commits in §1, each checked against the project's current
branch head through the GitHub API on 2026-10-18. Every cell is marked **R** (read-derived: from
source; a hypothesis about behaviour), **M** (measured: the 11-site
corpus) or **H** (history: a release, tag or branch fact from the GitHub API). Current decisions:
[execution plan §1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions).

**The question.** `docs/proposals/integration-questionnaire.md` is part of the earlier draft in
cgm-remote-monitor's `docs/proposals` (with `agent-control-plane-rfc.md`, `bridge-rules.md` and
`conflict-resolution.md`), which this repository's [specifications](spec/) are proposed to
supersede. It asks AID controller projects 16 questions (A1–G16) in 14 tables; each response
section reads *Pending*. Read at cgm-remote-monitor `a8888f0d`; the file is unchanged on `dev`
`fade2299` since `db32bdc6` (2026-01-19). The maintainer decided on 2026-10-18 that every answer
is filled, for every controller, with a default read from that controller's source and history,
and from the corpus where it applies. This page is that fill.

---

## How to use this

* **Each cell is a default for the project to correct.** It states what the cited source does at the
  cited commit. A project corrects a cell by saying what is different; the corrected cell then cites
  the project and the date.
* **To send a correction:** open an issue or pull request on this repository naming the question
  id and column (for example "C7, Trio"), or answer on cgm-remote-monitor with the label
  `agentic-control-plane` as the questionnaire asks. A source link or a test is the fastest
  correction; a sentence is enough.
* **Where source cannot settle a question** (G15 timeline, G16 concerns), the cell gives the default
  the evidence supports and names what only the project can correct.
* **Columns.** The questionnaire's tables carry an OpenAPS column only in A1 and A3; its response
  list names OpenAPS. Every table here has an OpenAPS column, read from oref0 (the rig).
* **Corpus coverage.** The corpus is 11 Nightscout sites (snapshots 2026-04-01 and 2026-04-26),
  9 of them Loop. One site carries `openaps.*` devicestatus, and its `openaps.recommendedBolus`,
  `pump.bolusIncrement` and `Exercise` treatments are Trio's (M: census paths below; landscape
  [§3.2](nightscout-intent-workflow-landscape-2026-10-09.md#32-trio-and-iaps)). **The AndroidAPS
  column is read from source only**: the corpus has no AndroidAPS closed-loop site (M: no
  `pump.extended` or `openaps.enacted.requested` path in the devicestatus census). **The OpenAPS
  column is read from source only**: the corpus has no oref0 rig (M: no `mmtune` or `preferences`
  path). Census counts are reads across both snapshots, which overlap, so they bound distinct
  documents from above.

## 1. Sources

| Column | Read at | Current head, 2026-10-18 | Local clone |
|---|---|---|---|
| **Loop** | `L` Loop `e959503b` (dev); `LK` LoopKit `d9f14373`; `NSS` NightscoutService `2cef4896`; `NSK` NightscoutKit `4ec9fd1` | Loop dev `e959503b`; LoopKit dev `4c8e8577` (4 commits ahead, persistence only, none of the cited files); NightscoutService dev `2cef4896`; LoopWorkspace dev `c1f55970` pins NightscoutKit `4ec9fd1` | LoopWorkspace `548b3324` = release `v3.14.9`, pinning Loop `c30b5c89` (3 commits behind dev: issue reports and alerts); **stale for Loop**, so Loop was read from a dev tarball |
| **Trio** | `T` Trio `e797b4ad` (dev) | dev `e797b4ad` | `0b29cd53` = `v1.0.2` (93 commits behind dev, including remote control and `NightscoutStatus.swift`); **stale**, read from a dev tarball |
| **AndroidAPS** | `A` AndroidAPS `b9bb9ef3` (dev) | dev `b9bb9ef3`; `4.0.0-rc1` `d5e7f5bd` is dev minus one commit | `7e1d537d` (506 commits behind); **stale**, read from a dev tarball |
| **OpenAPS** | `O` oref0 `d219baf9` (dev) | dev `d219baf9`; master `88cf032a` = `v0.7.1` | current |
| **Corpus** | `C` `reports/schema-census/<collection>.census.json`, field `docs_present` for the named path | — | — |

Heads: `gh api repos/<owner>/<repo>/commits/<branch> --jq .sha`; staleness:
`gh api repos/<owner>/<repo>/compare/<clone>...<head>`. File paths in cells are basenames; the
[path index](#appendix-b-path-index) gives the full path of each. The registrations under
[`specs/sync/registrations/`](../../../specs/sync/registrations/) were read at older commits
(Loop `c2fddb76`, Trio `e41c9db37`, AndroidAPS `7e1d537d49`); where a cell here and a registration
differ, this page is at the newer commit.

**One change since the earlier evidence.** Items the [intent
landscape](nightscout-intent-workflow-landscape-2026-10-09.md) marks AndroidAPS **dev-only**
(scenes, client control on the NS `settings` collection) are in the `4.0.0-beta1` (2026-10-08) and
`4.0.0-rc1` (2026-10-16) prereleases (H: `gh api repos/nightscout/AndroidAPS/contents/plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/SettingsIdentifiers.kt?ref=4.0.0-beta1`).
Client-control envelopes are authenticated with HMAC-SHA256 over a shared secret (R `A ClientControlCrypto.kt:10-24`).

---

## A) Profiles and overrides

### A1. Profile identification

| | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| **Current state** | One schedule set, named `Default`; the profile document is identified by name and `startDate` only — R `NSS StoredSettings.swift:92-106` | One schedule set, stored under the key `default`; no id — R `T NightscoutManager.swift:836,854` | Several named profiles held in preferences; the NS profile document has `defaultProfile` = first profile's name, `store` keyed by name, no id — R `A StringNonKey.kt:65`, `A ProfileRepositoryImpl.kt:683-709` | Profile built on the rig from pump settings; uploaded as the named profile `OpenAPS Autosync` — R `O oref0-upload-profile.js:243-271` |
| **Can emit content hash?** | Not today; a `syncIdentifier` is generated per settings snapshot (`UUID()`), not per content, and is not written — R `LK SettingsStore.swift:342`, `NSK ProfileSet.swift:143-164` | Not today; nothing in the profile path hashes — R `T NightscoutManager.swift:824-862` | Not today; profiles compare by value, block by block (`ProfileSealed.isEqual`) — R `A ProfileSealed.kt:312-325` | Not today; uploads only when the content differs by deep comparison (`_.isEqual`) — R `O oref0-upload-profile.js:255` |

*Note.* Every controller already compares or snapshots its profile; none puts a stable id or a hash
on the wire. Measured: 202 profile documents read, every one with `defaultProfile` and `startDate`
(M `C profile` paths `defaultProfile`, `startDate`).

### A2. Override templates vs activations

| | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| **Has templates?** | Yes: `TemporaryScheduleOverridePreset` {id UUID, symbol, name, settings, duration} — R `LK TemporaryScheduleOverridePreset.swift:12-17` | Yes: an `OverrideStored` row with `isPreset`; temp-target presets likewise — R `T OverrideStored+CoreDataProperties.swift:9-30`, `T TempTargetStored+CoreDataProperties.swift:9-20` | Yes, of other kinds: named profiles, TT presets, Scenes (with `id`), QuickWizard — R `A TTPreset.kt:8-25`, `A Scene.kt:8-27`. No override object | No. Temp targets are read from Nightscout treatments and local files — R `O oref0-ns-loop.sh:104-118` |
| **Templates persisted?** | Yes, in the settings store; uploaded in `profile.loopSettings.overridePresets` **without the id** — R `L SettingsManager.swift:126,172`, `NSK TemporaryScheduleOverride.swift:28-50`; M 200 profile documents carry `loopSettings.overridePresets` (`C profile`) | Yes, Core Data; uploaded in `profile.overridePresets` {name, duration, percentage, target}, **without the id** — R `T OverrideStorage.swift:379-409`, `T NightscoutStatus.swift:70-75` | Yes, preferences; uploaded in the NS `settings` document `aaps` under `runningConfig.syncedPrefs` — R `A RunningConfigurationImpl.kt:65-87,130-140`, `A SettingsIdentifiers.kt:19-20` | — (no templates) R `O targets.js:11-68` |
| **Can separate?** | Locally yes: activation copies the preset (`context: .preset`) and gives the instance its own `syncIdentifier`, uploaded as `_id`; remote enactment refers to the preset by name — R `LK TemporaryScheduleOverridePreset.swift:27-35`, `NSS OverrideTreament.swift:59`, `L Loop/Managers/LoopDataManager.swift:2502` | Partly: activation enables the preset row itself and writes a separate run record (`OverrideRunStored`); a copy is made only when a running preset is edited — R `T AdjustmentManager.swift:155-198`, `T OverrideStorage.swift:185-224` | Yes: a ProfileSwitch copies the profile blocks; scene activation writes ordinary TT/PS/RM rows and records them in `aaps-state` — R `A ProfileSwitch.kt:40-50`, `A SceneExecutor.kt:407-477`, `A RunningConfigurationImpl.kt:90-110` | Not applicable — R `O targets.js:11-68` |

*Note.* "Separate" on the wire needs the definition id published with the definition and cited by
the activation. Loop and Trio both hold the id locally and send neither; AndroidAPS sends scene ids
in `aaps-state` (4.0.0 prereleases). The state and intent specification's definition/instance rules
([spec/state-intent.md](spec/state-intent.md)) are the destination for this answer.

### A3. Override dimensions

| Dimension | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| Target range (min/max) | Yes, `targetRange` — R `LK TemporaryScheduleOverrideSettings.swift:12-14` | No (one target) — R `T OverrideStored+CoreDataProperties.swift:9-30` | Yes, on a temp target (`lowTarget`/`highTarget`) — R `A TemporaryTarget.kt:36-49` | Yes, on a temp target (`targetBottom`/`targetTop`) — R `O targets.js:56-61` |
| Single target value | As a range with equal ends — R `LK TemporaryScheduleOverrideSettings.swift:12-14` | Yes, `target`; used only when no temp target is set — R `T DetermineBasal+Helpers.swift:284-293` | As a TT with equal ends — R `A TemporaryTarget.kt:36-49` | `target_bg` preference, or a TT — R `O targets.js:27-31` |
| Sensitivity multiplier | Derived: ISF × 1/factor — R `LK TemporaryScheduleOverrideSettings.swift:24-26` | Yes when the ISF scope is on: `sens / factor` — R `T DetermineBasal+Helpers.swift:303-321` | Through profile `percentage` (ISF × 100/p); autosens/Dynamic ISF ratio is separate and algorithm-set — R `A ProfileSealed.kt:105-107`, `A OpenAPSSMBPlugin.kt:374-399` | Algorithm-set `sensitivityRatio` from autosens or a high/low TT — R `O determine-basal.js:262-286` |
| Basal multiplier/percentage | Yes: basal × factor (one factor for all three) — R `LK TemporaryScheduleOverrideSettings.swift:20-22` | Yes: `percentage` always scales basal — R `T DetermineBasalGenerator.swift:155-171` | Yes: profile `percentage` — R `A ProfileSwitch.kt:46-48` | No — R `O lib/profile/index.js:85-179` |
| Max basal ceiling | No — R `LK TemporaryScheduleOverrideSettings.swift:12-14` | No (pump setting) — R `T ProfileGenerator.swift:140` | No; preference constraint, moved only indirectly by scaled basal — R `A OpenAPSSMBPlugin.kt:535-556` | No (pump `max_basal` and safety multipliers) — R `O basal-set-temp.js:10-16` |
| Carb ratio multiplier | Derived: CR × 1/factor — R `LK TemporaryScheduleOverrideSettings.swift:28-30` | Yes when the CR scope is on — R `T ForecastGenerator.swift:25-32` | Through `percentage` (IC × 100/p) — R `A ProfileSealed.kt:333-341` | No — R `O lib/profile/index.js:85-179` |
| Automation aggressiveness | No field — R `LK TemporaryScheduleOverrideSettings.swift:12-14` | Yes: `smbIsOff`, scheduled SMB-off hours, `smbMinutes`/`uamMinutes` — R `T DosingEngine.swift:26-32,62-89,708-729` | Yes: a Scene action toggles SMB; RunningMode (open, closed, LGS) — R `A SceneAction.kt:35`, `A RunningMode.kt:49-60` | TT-dependent SMB enable/disable preferences — R `O determine-basal.js:63,103` |
| Duration (fixed/indefinite) | Both: `.finite`/`.indefinite` — R `LK TemporaryScheduleOverride.swift:26-28` | Both; indefinite sent as 43200 min — R `T OverrideStorage.swift:271` | PS: fixed or permanent (0); TT: fixed — R `A ProfileSwitch.kt:46-48` | TT: fixed; duration 0 cancels — R `O targets.js:48-52` |

*Note.* Loop's override has one factor, applied as basal × f, ISF × 1/f, CR × 1/f
(R `LK DailyQuantitySchedule+Override.swift:13-63`). Measured on the wire: 2,720 treatments carry
`insulinNeedsScaleFactor` and 1,673 `correctionRange` across 9 and 7 sites (M `C treatments`).
Trio sends neither percentage nor target on the wire (G16). AndroidAPS has no override object; the
nearest equivalents are ProfileSwitch + TempTarget + RunningMode, or a Scene that writes them.

### A4. Multiple override resolution

| Option | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| Only one override at a time | **Yes**, plus a separate pre-meal target — R `LK TemporaryScheduleOverrideHistory.swift:147-187` | **Yes**, plus a separate temp target — R `T AdjustmentManager.swift:152-198` | One PS, one TT, one RunningMode, one Scene — R `A AppRepository.kt:472-479,515-522` | One temp target — R `O targets.js:35-63` |
| Stack/compose with precedence | **Yes**, override with pre-meal (below) — R `L LoopCore/LoopSettings.swift:118-141` | **Yes**, override with temp target (below) — R `T DetermineBasal+Helpers.swift:284-293` | **Yes**, PS with TT (below) — R `A OpenAPSSMBPlugin.kt:340-349` | No — R `O targets.js:35-63` |
| Most recent wins | **Yes**: a new override ends the active one (`.early`) and deletes later-starting ones — R `LK TemporaryScheduleOverrideHistory.swift:160-187` | **Yes**: starting one ends and disables every active one in one transaction — R `T AdjustmentManager.swift:152-198` | TT: **yes**, a new one ends the running one — R `A InsertAndCancelCurrentTemporaryTargetTransaction.kt:10-21`; PS and RM: latest temporary over latest permanent — R `A AppRepository.kt:472-479` | **Yes**: newest started TT wins — R `O targets.js:35-63` |
| User must end one first | No — R as above | No — R as above | No — R as above | No — R as above |

**Precedence, by default:**

* **Loop:** target = pre-meal if active, else override, else schedule (R `L LoopCore/LoopSettings.swift:118-141`); basal × f, ISF × 1/f, CR × 1/f come from the override only, also while pre-meal is on.
* **Trio:** target = temp target if set, else override target (unless 0 or 6), else profile (R `T DetermineBasal+Helpers.swift:284-293`); override percentage and ISF/CR scope apply regardless; a high or low TT sets `sensitivityRatio` via `halfBasalTarget` (R `T DetermineBasal+Helpers.swift:121-165`).
* **AndroidAPS:** TT replaces min/max/target (R `A OpenAPSSMBPlugin.kt:340-349`); the PS percentage is already in the EffectiveProfileSwitch blocks (R `A ProfileSealed.kt:105-107`).
* **OpenAPS:** TT replaces the target range (R `O targets.js:56-61`); a high or low TT can set `sensitivityRatio` (R `O determine-basal.js:262-286`).

The hub records the controller's composition and does not compute it (D18; intent landscape
[§7](nightscout-intent-workflow-landscape-2026-10-09.md#7-composition-who-combines-overlapping-intents)).
The earlier draft's `conflict-resolution.md` composes inside the hub; the specifications replace that.

---

## B) Policy composition

### B5. Effective parameters computation

| | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| **Has explicit object?** | No single object: inputs are assembled per cycle; `StoredDosingDecision` is the kept snapshot — R `L Loop/Managers/LoopDataManager.swift:1726-1753`, `LK DosingDecisionStore.swift:239-263` | Yes: the `Profile` passed to determine-basal; overrides travel beside it, not in it — R `T Profile.swift:3-140`, `T OpenAPS.swift:378-444` | Yes: `OapsProfile`, built each run; and the EffectiveProfileSwitch for schedules — R `A OapsProfile.kt:6-51`, `A EffectiveProfileSwitch.kt:29-55` | Yes: `profile.json` — R `O lib/profile/index.js:85-179` |
| **Fields included** | Decision snapshot: effective target schedule, override, IOB, COB, prediction, recommendations, errors; **not** effective ISF/CR/basal — R `LK DosingDecisionStore.swift:239-263` | current_basal, sens, carb_ratio, max_iob, max_basal, max_daily_basal, min/max/target_bg, autosens limits, SMB flags, temptargetSet — R `T Profile.swift:3-140` | max_iob, max_basal, max_daily_basal, current_basal, sens, variable_sens, carb_ratio, min/max/target_bg, autosens_max, TDD, SMB flags — R `A OapsProfile.kt:6-51` | max_iob, max_basal, max_daily_basal, current_basal, sens, carb_ratio, min/max_bg, temptargetSet, safety multipliers — R `O lib/profile/index.js:85-179` |

### B6. Composition emission

| Field | Loop | Trio | AndroidAPS | OpenAPS | Notes |
|---|---|---|---|---|---|
| Profile hash/ID | No — R `NSK ProfileSet.swift:143-164` | No — R `T NightscoutManager.swift:824-862` | Name only (`profile`, `originalProfileName` on PS) — R `A nsclientV3/extensions/ProfileSwitchExtension.kt:52-78` | No — R `O ns-status.js:154-169` | see A1 |
| Active override IDs | Override name and multiplier in `devicestatus.override`; no id — R `NSS StoredDosingDecision.swift:118-137`; M `override.active` 597,335 reads, 10 sites | No — R `T NightscoutStatus.swift:3-32` | PS/TT/RM record ids are not in devicestatus; `aaps-state` lists a scene's record ids — R `A RunningConfigurationImpl.kt:90-110` | No — R `O ns-status.js:154-169` | |
| Effective target range | Only while an override runs: `override.currentCorrectionRange` — R `NSS StoredDosingDecision.swift:118-137` | `suggested.current_target` — R `T Determination.swift:49-76`; M 73,898 reads, 1 site | `targetBG` inside `suggested` — R `A RT.kt:19-48` | `suggested.target_bg` — R `O determine-basal.js:821` | |
| Effective ISF (current) | No — R `NSS StoredDosingDecision.swift:148-164` | `suggested.ISF` — R `T Determination.swift:49-76`; M 73,898 reads, 1 site | `suggested.variable_sens`; ISF also as text in `reason` — R `A RT.kt:19-48`, `A DetermineBasalSMB.kt:892-898` | `suggested.ISF` — R `O determine-basal.js:819` | |
| Effective CR (current) | No — R as above | `suggested.CR` — R as above; M 73,898 reads | Text in `reason` only — R `A DetermineBasalSMB.kt:892-898` | `suggested.CR` — R `O determine-basal.js:820` | |
| Effective basal (current) | No; `enacted.rate` is the dose, not the scheduled basal — R as above | No; `rate` is the dose — R `T Determination.swift:49-76` | `pump.extended.BaseBasalRate` — R `A PumpStatusProviderImpl.kt:102-127` | No; `rate` is the dose — R `O determine-basal.js:439-448` | |
| Safety limits in force | In the profile, not per cycle: `loopSettings.maximumBasalRatePerHour`, `maximumBolus`, `minimumBGGuard` — R `NSK LoopSettings.swift:38-61`; M 200 profile documents, 10 sites | Only inside `reason` text when a cap binds — R `T DosingEngine.swift:643-648,873-878` | Only inside `reason` text — R `A DetermineBasalSMB.kt:1123-1140,1240-1241` | **`preferences` (incl. `max_iob`) is in devicestatus** when the rig's loop uploads — R `O oref0-ns-loop.sh:221-227`, `O ns-status.js:40-49,175-177` | see note |
| Controller version/build | `loop.version` = short version + build — R `NSS Bundle.swift:13-15`; M 597,335 reads, 10 sites | `openaps.version` = release version — R `T NightscoutManager.swift:661`; M 73,898 reads, 1 site | `pump.extended.Version`; also `runningConfig.version` in `settings` — R `A PumpStatusProviderImpl.kt:113`, `A RunningConfigurationImpl.kt:85` | `openaps.version` = oref0 package version — R `O ns-status.js:160` | |

*Note on safety limits.* [`dosing-input-sources.yaml`](../../../specs/nsschema/dosing-input-sources.yaml)
records `profile.maxIob` as absent for every oref0 derivative, which is what the corpus shows.
oref0's own rig uploads its `preferences` file, which holds `max_iob`, with each devicestatus
(R above); the corpus has no oref0 rig to measure it on. A digital twin that read Nightscout would
find `max_iob` for an oref0 rig and for no other controller here.

---

## C) Delivery fidelity

### C7. Delivery state distinction

| State | Loop | Trio | AndroidAPS | OpenAPS | Where reported |
|---|---|---|---|---|---|
| **Suggested** | `loop.automaticDoseRecommendation`, `loop.recommendedBolus` — R `NSS StoredDosingDecision.swift:37-61`; M 183,049 and 597,143 reads, 10 sites | `openaps.suggested` (a determination not enacted) — R `T Determination+helper.swift:72-89`; M 73,898 reads | `openaps.suggested` = the whole algorithm result — R `A LoopPlugin.kt:1057-1061`, `A DetermineBasalResult.kt:152-158` | `openaps.suggested` — R `O ns-status.js:154-161` | devicestatus (R, as cited) |
| **Requested** | Held locally (`lastRequestedBolus`, pump `initiating…` states, `deliveryIsUncertain`); not uploaded — R `L Loop/Managers/LoopDataManager.swift:430,721-755`, `LK PumpManagerStatus.swift:39-71` | No requested state between send and confirmation — R `T APSManager.swift:773-874` | Local queued `PumpEnactResult` not uploaded; the request is uploaded inside `enacted.requested` once the pump enacted — R `A LoopPlugin.kt:701-705,1077-1087` | `enact/smb-suggested.json` exists locally before enactment; not uploaded — R `O oref0-pump-loop.sh:321-366` | not reported (R, as cited) |
| **Confirmed/enacted** | `loop.enacted` with `received: true`, **inferred** from "a recommendation and no errors", not from a pump acknowledgement — R `NSS StoredDosingDecision.swift:63-70`; M 405,228 reads, 10 sites | `openaps.enacted` with `received` = enacted, set after the pump call returns without error; a failed enact is uploaded as `suggested` with `received: false` — R `T APSManager.swift:436-438,841-874`, `T DeterminationStorage.swift:195` | `openaps.enacted` only if the pump reported the temp basal enacted; `enacted.smb` is taken from the temp-basal result — R `A LoopPlugin.kt:1070-1087` | `enacted.json` = suggested + `received: true`, written only after the pump command returns — R `O oref0-pump-loop.sh:365-366,459` | devicestatus (R, as cited) |

*Note.* This corrects the [control-plane reconciliation
§3.5](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md#35-all-three-publish-a-suggestion-under-three-different-names)
reading of `loop.enacted.received` as a pump acknowledgement: in Loop it is a constant. The question
§3.5 proposed as the narrower one — *is there a point in your code where a command has been sent and
not yet acknowledged, and can you emit it?* — has a default per column above: Loop and AndroidAPS
hold one locally, Trio has none, OpenAPS holds a file.

### C8. Pump response codes

| | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| **Has error codes** | Yes: `PumpManagerError` {configuration, connection, communication, deviceState, uncertainDelivery} — R `LK PumpManagerError.swift:10-24` | Yes: `APSError` {pumpError, invalidPumpState, glucoseError, apsError, manualBasalTemp} — R `T APSManager.swift:54-75` | `PumpEnactResult` {success, enacted, comment (free text), queued, cancelled}; driver alarm enums — R `A PumpEnactResult.kt:7-29`, `A medtrum/comm/enums/AlarmState.kt:3-21` | No; loop failure is a shell exit path with log text — R `O oref0-pump-loop.sh:160-180` |
| **Examples** | `pumpManagerError` with detail `communication` — R `L LoopError.swift:117-165`, `L PumpManagerError.swift:12-39` | `invalidPumpState("Pump is bolusing")` — R `T APSManager.swift:447-449` | `executing_right_now`, `stop_pressed`, Medtrum `OCCLUSION` — R `A CommandQueueImplementation.kt:390-391,723-737` | "pump suspended", BG too old — R `O oref0-pump-loop.sh:162-170` |
| **Can expose?** | Exposed as `loop.failureReason` = the first error's id and details as a string — R `NSS StoredDosingDecision.swift:72-74,168-176`; M 16,550 reads (2.4%), 10 sites | Not exposed: local alert and loop stats only — R `T APSManager.swift:1319-1406` | Not exposed; pump alarms reach Nightscout as `Announcement` text — R `A PumpSyncImplementation.kt:359-369` | `pump.status` (suspended, bolusing) only — R `O ns-status.js:162-167` |

### C9. Failure reason distinction

| Failure type | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| Capped by max basal | Silent clamp — R `LK DoseMath.swift:56` | `reason` text "adj. req. rate … to maxSafeBasal" — R `T DosingEngine.swift:873-878` | Constraint reasons in the UI; `reason` text "maxSafeBasal" on the wire — R `A LoopViewModel.kt:91-92`, `A DetermineBasalSMB.kt:1240-1241` | `reason` text — R `O determine-basal.js:1173-1177` |
| Capped by max IOB | Silent clamp (`maxBolus × 2` IOB limit) — R `L Loop/Managers/LoopDataManager.swift:1815-1816,1840`, `LK DoseMath.swift:425-428` | `reason` text "IOB … > max_iob …" — R `T DosingEngine.swift:643-648,688-693` | `reason` text — R `A DetermineBasalSMB.kt:1123-1124,1139-1140` | `reason` text — R `O determine-basal.js:1056-1073` |
| Communication failure | `failureReason` string — R `NSS StoredDosingDecision.swift:72-74` | Local alert; determination uploaded with `received: false` — R `T TrioAlertCategory.swift:163-166` | Local notification; no `enacted` in devicestatus — R `A CommandExecutor.kt:191-193`, `A LocalAlertUtilsImpl.kt:74` | Log text; retry and radio tune — R `O oref0-pump-loop.sh:171-180` |
| Pump busy/unavailable | `connectionError` for uncertain delivery; `pumpSuspended` — R `L DeviceDataManager.swift:1452-1453`, `L Loop/Managers/LoopDataManager.swift:1905-1906` | Local `invalidPumpState` — R `T APSManager.swift:447-449,790-792` | Local `executing_right_now` / `command_replaced` — R `A CommandQueueImplementation.kt:390-391,432` | `pump.status.bolusing`/`suspended` in devicestatus — R `O oref0-pump-loop.sh:428-440` |
| User canceled | Nothing specific; the delivered amount is the dose record — R `L StatusTableViewController.swift:1284` | Delivered amount re-posted on the bolus record — R `T PumpHistoryStorage.swift:244-262` | Local `stop_pressed`, `cancelled = true` — R `A CommandQueueImplementation.kt:723-737` | No cancel step in the loop script — R `O oref0-pump-loop.sh:450-460` |
| Pump error (occlusion…) | `Note` treatment with the alarm title — R `NSS PersistedPumpEvent.swift:25-26` | `Announcement` treatment "Alarm … PumpAlarm" — R `T PumpHistoryStorage.swift:541-559` | `Announcement` treatment — R `A PumpSyncImplementation.kt:359-369` | Pump-history `Note` treatments with alarm text — R `O mm-format-ns-treatments.sh:36-39` |

**Current representation format, by default:**

```
Loop:       loop.failureReason: free-text "<errorId>[detail: …, error: …]" (dictionary order not
            fixed); alarms as Note treatments; caps silent.
Trio:       openaps.suggested.reason free text for caps; received:false for a failed enact;
            alarms as Announcement treatments; other errors local only.
AndroidAPS: openaps.suggested.reason free text for caps; absence of openaps.enacted for a failed
            temp basal; alarms as Announcement treatments; queue and constraint reasons local.
OpenAPS:    openaps.suggested.reason free text; pump.status flags; Note treatments from pump history.
```

---

## D) Timing and ordering

### D10. Monotonic ordering

| | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| **Has sequence numbers** | Locally: `modificationCounter` query anchors, kept in UserDefaults, not uploaded — R `LK DosingDecisionStore.swift:144-147,197-199` | No; an `isUploadedToNS` flag per row — R `T NightscoutManager.swift:112-264` | Locally: autoincrement `id` and `version` per entity, not uploaded — R `A ProfileSwitch.kt:31-39`, `A TraceableDao.kt:68-83` | No — R `O ns-status.js:154-169` |
| **Clock guarantees** | Device clock; NTP check raises an alert at 120 s skew, does not correct — R `L TrustedTimeChecker.swift:29,43-80` | Device clock (`Date()`) — R `T NightscoutManager.swift:673` | Device clock; `utcOffset` on each treatment — R `A ProfileSwitch.kt:31-39` | Rig clock set from NTP; pump and CGM clocks set from it — R `O oref0-set-device-clocks.sh:31-41` |
| **Ordering method** | Timestamp plus `syncIdentifier` on doses and carbs (a dedup key, not a sequence) — R `NSS Extensions/DoseEntry.swift:31,47,62`; M `syncIdentifier` 306,741 reads (83%), 10 sites | Timestamp; treatments carry a UUID as `id`, which Nightscout does not read — R `T NightscoutTreatment.swift:24,62`; M `id` 55,939 reads, 1 site ([QUIRK-TREATMENTS-007](../../../specs/quirks/treatments.yaml)) | Upload in local `id` order; v3 `identifier` per record — R `A TemporaryTargetDao.kt:45-46`, `A DataSyncSelectorV3.kt:340-389` | Pump-history time; treatments newer than the latest uploaded `created_at` — R `O nightscout.sh:344-349` |

### D11. Offline batching

| Scenario | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| Queue events when offline | Yes: per-type anchors advance only on success — R `L RemoteDataServicesManager.swift:369,632-641` | Yes: rows with `isUploadedToNS == false`, **for one day** — R `T NightscoutManager.swift:112-264` | Yes: per-collection last-synced id — R `A NsclientLongKey.kt:23-37` | Yes: devicestatus files kept **24 h** — R `O oref0-ns-loop.sh:203-215` |
| Batch upload on reconnect | Yes: dosing decisions 50, settings 400, others 1000 per batch — R `NSS NightscoutService.swift:189-359` | Yes: batches of 100 — R `T NightscoutManager.swift:1373-1375` | One record at a time, in a loop — R `A DataSyncSelectorV3.kt:340-389` | Devicestatus one file at a time; treatments as one batch — R `O oref0-ns-loop.sh:207-215,230-237` |
| Preserve ordering in batch | Anchor order — R `L RemoteDataServicesManager.swift:370,381-383` | Not stated in the upload path — R `T NightscoutManager.swift:45-74` | Yes, ascending local `id` — R `A TemporaryTargetDao.kt:45-46` | Yes, file-name (time) order — R `O oref0-ns-loop.sh:206-207` |
| Mark events as "delayed" | No — R as above | No — R as above | No — R as above | No — R as above |
| Dedup on retry | `_id` = `syncIdentifier` for overrides; ObjectId cache for doses; none for devicestatus or profile — R `NSS NightscoutService.swift:209-213,252-256` | Server upsert on `created_at` + `eventType`; overrides deleted and re-posted — R `T PumpEvent+helper.swift:130-131`, `T NightscoutAPI.swift:445-475` | `identifier`/`nightscoutId`; update retried up to 5 times on 404 — R `A NSClientV3Plugin.kt:697-726` | `created_at` watermark; a separate dedupe script by `created_at` — R `O ns-dedupe-treatments.sh:7-23` |

---

## E) Minimal commitment for phase 1

### E12. Smallest native event set

| Event | Priority | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|---|
| `override.instance.activated` | High | Default: **already written** as `Temporary Override` with `_id` = instance UUID — R `NSS OverrideTreament.swift:41-59` | Default: written as `Exercise` with name only; first native step is sending the override id, percentage and target — R `T NightscoutExercise.swift:9,23-29` | Default: ProfileSwitch / TempTarget / RunningMode records already carry `identifier` — R `A nsclientV3/extensions/ProfileSwitchExtension.kt:52-78` | Default: not applicable (no overrides); TTs are read (R `O nightscout.sh:295-297`), not written |
| `override.instance.ended` | High | Default: written as an amended `duration` or a DELETE — R `NSS NightscoutService.swift:157-167` | Default: written as delete + re-post with actual duration — R `T NightscoutManager.swift:1206-1238` | Default: shortened `duration` on the same `identifier` — R `A TreatmentMapper.kt:517-541` | Not applicable — R `O targets.js:11-68` |
| `policy.composition.computed` | High | Default: partial (`override.currentCorrectionRange`, `multiplier`); effective ISF/CR/basal not written — R `NSS StoredDosingDecision.swift:118-137` | Default: `suggested` carries ISF, CR, current_target, sensitivityRatio — R `T Determination.swift:49-76` | Default: `suggested` carries variable_sens, targetBG, sensitivityRatio; the `OapsProfile` is the object to emit — R `A RT.kt:19-48`, `A OapsProfile.kt:6-51` | Default: `suggested` plus `preferences` — R `O ns-status.js:154-177` |
| `delivery.observed` (summary) | Medium | Default: `loop.enacted`, after `received` reflects the pump result — R `NSS StoredDosingDecision.swift:63-70` | Default: `openaps.enacted` — R `T APSManager.swift:841-874` | Default: `openaps.enacted` with `requested` — R `A LoopPlugin.kt:1070-1087` | Default: `openaps.enacted` — R `O oref0-pump-loop.sh:365-366` |
| `profile.selection.changed` | Medium | Default: one profile; a settings change posts a new profile document — R `NSS NightscoutService.swift:361-368` | Default: one profile, posted on change — R `T NightscoutAPI.swift:407-441` | Default: ProfileSwitch + EffectiveProfileSwitch — R `A nsclientV3/extensions/EffectiveProfileSwitchExtension.kt:45-66` | Default: `OpenAPS Autosync` profile upload — R `O oref0-upload-profile.js:243-271` |
| `capability.snapshot.updated` | Low | Default: `profile.loopSettings` snapshot — R `NSK LoopSettings.swift:38-61` | Default: `profile.remoteCommands` list (dev) — R `T NightscoutManager.swift:846` | Default: `settings` document `aaps` — R `A RunningConfigurationImpl.kt:65-87` | Default: `preferences` in devicestatus — R `O ns-status.js:40-49` |

**Default minimal commitment** (the smallest change from what each already writes):

```
Loop:       override.instance.activated/ended as today's Temporary Override records (bridge);
            native first: delivery.observed with received set from the pump result.
Trio:       override.instance.activated/ended with the override id, percentage and target added;
            policy.composition.computed from today's suggested.
AndroidAPS: profile.selection.changed (PS → EPS) and policy.composition.computed from OapsProfile;
            override events map to PS/TT/RunningMode/Scene, already identified.
OpenAPS:    policy.composition.computed and delivery.observed from today's devicestatus (bridge).
```

---

## F) Additional capabilities

### F13. Remote commands

| Command type | Loop | Trio | AndroidAPS | OpenAPS | Security model |
|---|---|---|---|---|---|
| Activate override | Yes, by preset name, no OTP — R `NSS OverrideRemoteNotification.swift:46-47`, `L Loop/Managers/LoopDataManager.swift:2502-2504` | Yes (`start_override`) — R `T CommandPayload.swift:125-143` | Scene activation via client control (4.0.0 prereleases) — R `A ClientControlMessage.kt:32-181` | No — R `O oref0-ns-loop.sh:104-137` | see note |
| End override | Yes, no OTP — R `NSS OverrideCancelRemoteNotification.swift:37-38` | Yes (`cancel_override`) — R as above | Scene stop — R as above | No — R `O oref0-ns-loop.sh:104-137` | |
| Switch profile | No — R `NSS RemoteNotification.swift:102-114` | No — R `T CommandPayload.swift:125-143` | Yes: SMS `PROFILE`; a Nightscout PS record if `NsClientAcceptProfileSwitch` (default off); client-control batch action — R `A SmsCommunicatorPlugin.kt:172-186`, `A BooleanKey.kt:222-230`, `A BatchActionMapping.kt:80-121` | No — R `O oref0-ns-loop.sh:104-137` | |
| Set temp target | No — R `NSS RemoteNotification.swift:102-114` | Yes (`temp_target`, `cancel_temp_target`); also enables the newest Nightscout TT — R `T CommandPayload.swift:125-143` | Yes: SMS `TARGET`; Nightscout TT if `NsClientAcceptTempTarget` (default off); client control — R as above | Yes: reads `Temporary Target` treatments from Nightscout each loop — R `O oref0-ns-loop.sh:104-118` | |
| Bolus (caregiving) | Yes, OTP required, ≤ max bolus — R `NSS BolusRemoteNotification.swift:36-37`, `L ServicesManager.swift:332-345` | Yes, ≤ max bolus and max IOB, with a recent-bolus check — R `T BolusSafetyValidator.swift:43-81` | Yes: SMS `BOLUS`; client-control `bolus_prepare/commit` — R as above | No — R `O oref0-ns-loop.sh:104-137` | |

*Security model, by default (mechanism only).*
**Loop:** APNs push; a TOTP one-time password for bolus and carbs, none for override or cancel; an
optional sender-set expiry, skipped when absent; failures uploaded as a `Note` treatment that
includes the received command — R `NSS RemoteCommandValidator.swift:18-43`, `NSS NightscoutService.swift:487-520`.
**Trio:** APNs push; payload encrypted with AES-GCM under a key derived from a shared secret; a
±600 s timestamp window; no one-time password; reply to the sender over APNs, and a `Note` only on
error — R `T TrioRemoteControl.swift:18,24-75`, `T SecureMessenger.swift:5-31`, `T TrioRemoteControl+Helpers.swift:4-40`.
**AndroidAPS:** SMS from an allowlisted number with TOTP + PIN, off by default; inbound Nightscout
records accepted per type behind preferences, all off by default; client control on the NS
`settings` collection with HMAC-SHA256-authenticated envelopes, a counter, clock-skew and
`validUntil` checks, and acknowledgements (Executing → Done {Ok, Failed, Expired}, Delivery Failed)
— R `A AuthRequest.kt:43-56`, `A ClientControlReceiver.kt:317-389`, `A AckEnvelope.kt:52-65`.
**OpenAPS:** whoever can write `Temporary Target` or carb treatments to the Nightscout site.
The command rules this repository proposes are in [spec/commands.md](spec/commands.md).

### F14. Controller registration

| Field | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| Unique instance ID | None on the wire; the profile's APNs `deviceToken` is the nearest — R `NSS StoredDosingDecision.swift:148-164`, `NSK LoopSettings.swift:38-61` | None; the profile's APNs `deviceToken` is the nearest — R `T NightscoutManager.swift:840-861` | An install UUID for client control only — R `A AuthorizedClientsViewModel.kt:271-278` | None; host name in `device` — R `O ns-status.js:155` |
| Device info | `device` = `loop://` + iOS device name; `uploader.name` — R `NSS StoredDosingDecision.swift:149`; M `device` on every devicestatus read | `device` = `Trio` — R `T NightscoutManager.swift:688` | `device` = `openaps://` + manufacturer + model — R `A ConfigImpl.kt:60` | `device` = `openaps://` + host name — R `O ns-status.js:155` |
| Pump binding info | `pump.manufacturer`, `model`, `pumpID` — R `NSK PumpStatus.swift:52-63`; M 588,152 / 588,152 / 597,334 reads, 10 sites | Clock, battery, reservoir, status, bolus increment; no model or id — R `T NightscoutStatus.swift:20-26` | `pump.extended` (driver extras); `runningConfig.pump` model in `settings` — R `A PumpStatusProviderImpl.kt:102-127`, `A RunningConfigurationImpl.kt:78` | Pump model in treatment `enteredBy` (`openaps://medtronic/<model>`) — R `O mm-format-ns-treatments.sh:31` |
| CGM binding info | Entry `device` = manufacturer + model, or provenance — R `NSS StoredGlucoseSample.swift:22-32` | No device string on entries — R `T BloodGlucose.swift:60-76` | Entry `device` = source sensor — R `A nsclientV3/extensions/GlucoseValueExtension.kt:38` | Entry `device` = `openaps://medtronic/pump/cgm` — R `O mm-format-ns-glucose.sh:32` |
| Version/build | `loop.version` — R, see B6 | `openaps.version` — R, see B6 | `pump.extended.Version` — R, see B6 | `openaps.version` — R, see B6 |

*Note.* `device` is free text and is not an identity (reconciliation
[§3.3](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md#33-instance-identity-should-not-come-from-the-device-string));
a registered instance gets a hub-issued or controller-supplied id ([spec/registration.md](spec/registration.md)).
Loop's `device` and `uploader.name` carry the user's device name, which `specs/sync/sensitivity.yaml` treats as identifying.

---

## G) Migration path

### G15. Adoption timeline

| Phase | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| Can test in dev builds | Default: on LoopWorkspace `dev` (head `c1f55970`, 2026-10-17), which pins Loop `691afb31` ahead of the release — H `gh api repos/LoopKit/LoopWorkspace/contents/Loop?ref=c1f5597093` | Default: on `dev` (head `e797b4ad`, 2026-10-18; versioned by `auto_version_dev.yml`) — H `gh api repos/nightscout/Trio/commits/dev` | Default: on `dev` (head `b9bb9ef3`, 2026-10-16) — H `gh api repos/nightscout/AndroidAPS/commits/dev` | Default: on `dev` (head `d219baf9`, 2026-03-10; 8 commits in 12 months) — H `git -C externals/oref0 log --since=2025-10-18` |
| Can ship in beta | Default: no prerelease channel; the 9 LoopWorkspace releases in 12 months are all marked stable — H `gh api repos/LoopKit/LoopWorkspace/releases` | Default: prereleases are used rarely (last `v0.6.0`, 2025-10-07); `dev` is the test channel — H `gh api repos/nightscout/Trio/releases` | Default: beta then rc before stable (`4.0.0-beta1` 2026-10-08, `4.0.0-rc1` 2026-10-16) — H `gh api repos/nightscout/AndroidAPS/releases` | Default: release candidates historically (`v0.7.0-rc1`, 2019) — H `gh api repos/openaps/oref0/releases` |
| Can ship in stable | Default: the next LoopWorkspace release after merge; the 9 releases from 2025-11-01 to 2026-10-05 came 5 to 101 days apart — H as above | Default: days to weeks — the dosing-mode devicestatus field was committed 2026-09-13 and shipped in `v1.0` 2026-09-15; the profile's remote-command list (committed 2026-09-21) is not in `v1.0.2`; 9 releases in 12 months — H `gh api 'repos/nightscout/Trio/commits?sha=dev&path=Trio/Sources/Models/NightscoutStatus.swift'` | Default: months — client control reached `dev` 2026-08-29 and `4.0.0-beta1` 2026-10-08; last stable `3.4.2.6` 2026-08-02 — H `gh api 'repos/nightscout/AndroidAPS/commits?sha=dev&path=plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/SettingsIdentifiers.kt'` | Default: no stable release since `v0.7.1` (2022-06-19) — H `gh api repos/openaps/oref0/releases` |
| Full native (no devicestatus) | Default: devicestatus stays alongside native events; follower apps read it — R consumer impact §5 (note) | Default: as Loop — R consumer impact §5 (note) | Default: as Loop — R consumer impact §5 (note) | Default: devicestatus stays; it is the rig's only status channel — R `O oref0-ns-loop.sh:196-215` |

*Note.* Each "Default" here is what the release history supports; only the project can give its
plan. Loop's `next-dev` branch is 631 commits ahead of and 27 behind `dev` (H
`gh api repos/LoopKit/Loop/compare/e959503b18...7d5026176c`); a change made on `dev` reaches
`next-dev` separately. Follower clients that read devicestatus (xDrip+'s follower among them) are in the
[consumer impact survey §5](../../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md#5-per-client-summary).

### G16. Bridge mode feedback

What a hub synthesizing events from today's uploads would get wrong, by default, read from each
controller's writers and from the hub lab.

| Concern | Loop | Trio | AndroidAPS | OpenAPS |
|---|---|---|---|---|
| Accuracy of override state extraction | **Yes**: pre-meal is not uploaded; devicestatus `override.duration` is seconds while the treatment's is minutes; the two hubs disagree on it — R `NSS StoredDosingDecision.swift:119,129`, `NSK OverrideTreatment.swift:67`; M hub lab, landscape [§5](nightscout-intent-workflow-landscape-2026-10-09.md#5-how-the-hubs-decide-what-is-active); M 10,892 of 55,938 active overrides carry a name and no effect ([reconciliation §3.4](../tenancy/nightscout-control-plane-reconciliation-2026-09-11.md#34-overrideinstanceeffectiveeffects-will-be-empty-20-of-the-time)) | **Yes**: every override is `Exercise` with name only; percentage and target are not sent — R `T NightscoutExercise.swift:23-29`, `T OverrideStored+helper.swift:33-36`; M 399 distinct `Exercise` documents, 1 site | **Partly**: no override object; the PS → EPS pair is clear, EPS arrives as a `Note`; `timeshift` is milliseconds — R `A nsclientV3/extensions/EffectiveProfileSwitchExtension.kt:45-66`, `A TreatmentMapper.kt:540`; M hub lab: hubs disagree on timeshift units (landscape §5) | **No** override state to extract — R `O targets.js:11-68` |
| Accuracy of delivery extraction | **Yes**: `enacted.received` is constant `true`; devicestatus is uploaded only for four decision reasons, each paired with the last loop decision — R `NSS StoredDosingDecision.swift:63-70`, `NSS NightscoutService.swift:282-297` | Low: enacted vs suggested follows the pump result — R `T Determination+helper.swift:72-89` | **Yes**: `enacted.smb` is the temp-basal result's bolus — R `A LoopPlugin.kt:1087` | Low — R `O oref0-pump-loop.sh:365-366` |
| Missing fields in current devicestatus | Effective ISF/CR/basal; failure codes (2.4% carry text) — R B6; M `loop.failureReason` | Override factors, `halfBasalTarget`, pump model — R `T NightscoutTreatment.swift:3-25` | `OapsProfile` (max_iob, ISF, CR as fields), `utcOffset` — R `A nsclientV3/extensions/DeviceStatusExtension.kt:7-23` | Pump model and CGM in devicestatus — R `O ns-status.js:154-169` |
| Timing/ordering issues | Devicestatus `created_at` is the decision time, posted later in batches — R `NSS StoredDosingDecision.swift:148-153` | Unuploaded rows older than a day are dropped — R `T Determination+helper.swift:72-89` | Inbound records by `srvModified` — R `A LoadTreatmentsRunner.kt:41-57` | Files older than 24 h deleted unsent — R `O oref0-ns-loop.sh:205` |
| Duplicate events | Devicestatus and profile have no dedup key — R `NSK DeviceStatus.swift:23,61` | Temp targets and pump notes are uploaded without `id` and marked uploaded by `id`, so they may be re-posted (needs a run) — R `T TempTargetsStorage.swift:312-329`, `T NightscoutManager.swift:1287,1330` | Low: `identifier` per record — R `A DataSyncSelectorV3.kt:340-389` | Treatments dedup by a separate script on `created_at` — R `O ns-dedupe-treatments.sh:7-23` |
| Other | `device` and `uploader.name` carry the device's name (identifying) — R `NSS StoredDosingDecision.swift:149` | Remote-command `Note` on error only — R `T TrioRemoteControl+Helpers.swift:4-21` | Accepted remote records are opt-in per type, so a hub-written TT may never apply — R `A BooleanKey.kt:222-230` | `preferences` carries setup choices (redacted host, serial and tokens) — R `O ns-status.js:40-49` |

---

## Appendix A. iAPS

The questionnaire does not list iAPS. The [intent landscape](nightscout-intent-workflow-landscape-2026-10-09.md)
(§1, iAPS `6cb69e7`, 2026-10-04) covers it; its defaults, from that page, are: separate override
presets and an append-only override log, presets not sent to Nightscout (A2); override and temp
target concurrent, temp target wins the target (A4); ends on expiry, carbs, glucose thresholds or a
chained preset, reason in the debug log only (G16); remote intent arrives as Nightscout
`Announcement` treatments, authorised by Nightscout write access, with no acknowledgement (F13).
All read-derived; not re-read here.

## Appendix B. Path index

Each basename cited above, with its full path in the tree named by its prefix.

| Prefix | Cited as | Path |
|---|---|---|
| `L` (Loop e959503b) | `DeviceDataManager.swift` | `Loop/Managers/DeviceDataManager.swift` |
| `L` (Loop e959503b) | `Loop/Managers/LoopDataManager.swift` | `Loop/Managers/LoopDataManager.swift` |
| `L` (Loop e959503b) | `LoopCore/LoopSettings.swift` | `LoopCore/LoopSettings.swift` |
| `L` (Loop e959503b) | `LoopError.swift` | `Loop/Models/LoopError.swift` |
| `L` (Loop e959503b) | `PumpManagerError.swift` | `Loop/Extensions/PumpManagerError.swift` |
| `L` (Loop e959503b) | `RemoteDataServicesManager.swift` | `Loop/Managers/RemoteDataServicesManager.swift` |
| `L` (Loop e959503b) | `ServicesManager.swift` | `Loop/Managers/ServicesManager.swift` |
| `L` (Loop e959503b) | `SettingsManager.swift` | `Loop/Managers/SettingsManager.swift` |
| `L` (Loop e959503b) | `StatusTableViewController.swift` | `Loop/View Controllers/StatusTableViewController.swift` |
| `L` (Loop e959503b) | `TrustedTimeChecker.swift` | `Loop/Managers/TrustedTimeChecker.swift` |
| `LK` (LoopKit d9f14373) | `DailyQuantitySchedule+Override.swift` | `LoopKit/DailyQuantitySchedule+Override.swift` |
| `LK` (LoopKit d9f14373) | `DoseMath.swift` | `LoopKit/LoopAlgorithm/DoseMath.swift` |
| `LK` (LoopKit d9f14373) | `DosingDecisionStore.swift` | `LoopKit/DosingDecisionStore.swift` |
| `LK` (LoopKit d9f14373) | `PumpManagerError.swift` | `LoopKit/DeviceManager/PumpManagerError.swift` |
| `LK` (LoopKit d9f14373) | `PumpManagerStatus.swift` | `LoopKit/DeviceManager/PumpManagerStatus.swift` |
| `LK` (LoopKit d9f14373) | `SettingsStore.swift` | `LoopKit/SettingsStore.swift` |
| `LK` (LoopKit d9f14373) | `TemporaryScheduleOverride.swift` | `LoopKit/TemporaryScheduleOverride.swift` |
| `LK` (LoopKit d9f14373) | `TemporaryScheduleOverrideHistory.swift` | `LoopKit/TemporaryScheduleOverrideHistory.swift` |
| `LK` (LoopKit d9f14373) | `TemporaryScheduleOverridePreset.swift` | `LoopKit/TemporaryScheduleOverridePreset.swift` |
| `LK` (LoopKit d9f14373) | `TemporaryScheduleOverrideSettings.swift` | `LoopKit/TemporaryScheduleOverrideSettings.swift` |
| `NSS` (NightscoutService 2cef4896) | `BolusRemoteNotification.swift` | `NightscoutServiceKit/RemoteCommands/V1/Notifications/BolusRemoteNotification.swift` |
| `NSS` (NightscoutService 2cef4896) | `Bundle.swift` | `Extensions/Bundle.swift` |
| `NSS` (NightscoutService 2cef4896) | `Extensions/DoseEntry.swift` | `NightscoutServiceKit/Extensions/DoseEntry.swift` |
| `NSS` (NightscoutService 2cef4896) | `NightscoutService.swift` | `NightscoutServiceKit/NightscoutService.swift` |
| `NSS` (NightscoutService 2cef4896) | `OverrideCancelRemoteNotification.swift` | `NightscoutServiceKit/RemoteCommands/V1/Notifications/OverrideCancelRemoteNotification.swift` |
| `NSS` (NightscoutService 2cef4896) | `OverrideRemoteNotification.swift` | `NightscoutServiceKit/RemoteCommands/V1/Notifications/OverrideRemoteNotification.swift` |
| `NSS` (NightscoutService 2cef4896) | `OverrideTreament.swift` | `NightscoutServiceKit/Extensions/OverrideTreament.swift` |
| `NSS` (NightscoutService 2cef4896) | `PersistedPumpEvent.swift` | `NightscoutServiceKit/Extensions/PersistedPumpEvent.swift` |
| `NSS` (NightscoutService 2cef4896) | `RemoteCommandValidator.swift` | `NightscoutServiceKit/RemoteCommands/Validators/RemoteCommandValidator.swift` |
| `NSS` (NightscoutService 2cef4896) | `RemoteNotification.swift` | `NightscoutServiceKit/RemoteCommands/V1/Notifications/RemoteNotification.swift` |
| `NSS` (NightscoutService 2cef4896) | `StoredDosingDecision.swift` | `NightscoutServiceKit/Extensions/StoredDosingDecision.swift` |
| `NSS` (NightscoutService 2cef4896) | `StoredGlucoseSample.swift` | `NightscoutServiceKit/Extensions/StoredGlucoseSample.swift` |
| `NSS` (NightscoutService 2cef4896) | `StoredSettings.swift` | `NightscoutServiceKit/Extensions/StoredSettings.swift` |
| `NSK` (NightscoutKit 4ec9fd1) | `DeviceStatus.swift` | `Sources/NightscoutKit/Models/DeviceStatus.swift` |
| `NSK` (NightscoutKit 4ec9fd1) | `LoopSettings.swift` | `Sources/NightscoutKit/Models/LoopSettings.swift` |
| `NSK` (NightscoutKit 4ec9fd1) | `OverrideTreatment.swift` | `Sources/NightscoutKit/Models/Treatments/OverrideTreatment.swift` |
| `NSK` (NightscoutKit 4ec9fd1) | `ProfileSet.swift` | `Sources/NightscoutKit/Models/ProfileSet.swift` |
| `NSK` (NightscoutKit 4ec9fd1) | `PumpStatus.swift` | `Sources/NightscoutKit/Models/PumpStatus.swift` |
| `NSK` (NightscoutKit 4ec9fd1) | `TemporaryScheduleOverride.swift` | `Sources/NightscoutKit/Models/TemporaryScheduleOverride.swift` |
| `T` (Trio e797b4ad) | `AdjustmentManager.swift` | `Trio/Sources/Services/Adjustments/AdjustmentManager.swift` |
| `T` (Trio e797b4ad) | `APSManager.swift` | `Trio/Sources/APS/APSManager.swift` |
| `T` (Trio e797b4ad) | `BloodGlucose.swift` | `Trio/Sources/Models/BloodGlucose.swift` |
| `T` (Trio e797b4ad) | `BolusSafetyValidator.swift` | `Trio/Sources/Services/BolusSafety/BolusSafetyValidator.swift` |
| `T` (Trio e797b4ad) | `CommandPayload.swift` | `Trio/Sources/Models/CommandPayload.swift` |
| `T` (Trio e797b4ad) | `Determination+helper.swift` | `Model/Helper/Determination+helper.swift` |
| `T` (Trio e797b4ad) | `Determination.swift` | `Trio/Sources/Models/Determination.swift` |
| `T` (Trio e797b4ad) | `DeterminationStorage.swift` | `Trio/Sources/APS/Storage/DeterminationStorage.swift` |
| `T` (Trio e797b4ad) | `DetermineBasal+Helpers.swift` | `Trio/Sources/APS/OpenAPSSwift/DetermineBasal/DetermineBasal+Helpers.swift` |
| `T` (Trio e797b4ad) | `DetermineBasalGenerator.swift` | `Trio/Sources/APS/OpenAPSSwift/DetermineBasal/DetermineBasalGenerator.swift` |
| `T` (Trio e797b4ad) | `DosingEngine.swift` | `Trio/Sources/APS/OpenAPSSwift/DetermineBasal/DosingEngine.swift` |
| `T` (Trio e797b4ad) | `ForecastGenerator.swift` | `Trio/Sources/APS/OpenAPSSwift/Forecasts/ForecastGenerator.swift` |
| `T` (Trio e797b4ad) | `NightscoutAPI.swift` | `Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift` |
| `T` (Trio e797b4ad) | `NightscoutExercise.swift` | `Trio/Sources/Models/NightscoutExercise.swift` |
| `T` (Trio e797b4ad) | `NightscoutManager.swift` | `Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift` |
| `T` (Trio e797b4ad) | `NightscoutStatus.swift` | `Trio/Sources/Models/NightscoutStatus.swift` |
| `T` (Trio e797b4ad) | `NightscoutTreatment.swift` | `Trio/Sources/Models/NightscoutTreatment.swift` |
| `T` (Trio e797b4ad) | `OpenAPS.swift` | `Trio/Sources/APS/OpenAPS/OpenAPS.swift` |
| `T` (Trio e797b4ad) | `OverrideStorage.swift` | `Trio/Sources/APS/Storage/OverrideStorage.swift` |
| `T` (Trio e797b4ad) | `OverrideStored+CoreDataProperties.swift` | `Model/Classes+Properties/OverrideStored+CoreDataProperties.swift` |
| `T` (Trio e797b4ad) | `OverrideStored+helper.swift` | `Model/Helper/OverrideStored+helper.swift` |
| `T` (Trio e797b4ad) | `Profile.swift` | `Trio/Sources/APS/OpenAPSSwift/Models/Profile.swift` |
| `T` (Trio e797b4ad) | `ProfileGenerator.swift` | `Trio/Sources/APS/OpenAPSSwift/Profile/ProfileGenerator.swift` |
| `T` (Trio e797b4ad) | `PumpEvent+helper.swift` | `Model/Helper/PumpEvent+helper.swift` |
| `T` (Trio e797b4ad) | `PumpHistoryStorage.swift` | `Trio/Sources/APS/Storage/PumpHistoryStorage.swift` |
| `T` (Trio e797b4ad) | `SecureMessenger.swift` | `Trio/Sources/Services/RemoteControl/SecureMessenger.swift` |
| `T` (Trio e797b4ad) | `TempTargetsStorage.swift` | `Trio/Sources/APS/Storage/TempTargetsStorage.swift` |
| `T` (Trio e797b4ad) | `TempTargetStored+CoreDataProperties.swift` | `Model/Classes+Properties/TempTargetStored+CoreDataProperties.swift` |
| `T` (Trio e797b4ad) | `TrioAlertCategory.swift` | `Trio/Sources/Services/Alerts/TrioAlertCategory.swift` |
| `T` (Trio e797b4ad) | `TrioRemoteControl+Helpers.swift` | `Trio/Sources/Services/RemoteControl/TrioRemoteControl+Helpers.swift` |
| `T` (Trio e797b4ad) | `TrioRemoteControl.swift` | `Trio/Sources/Services/RemoteControl/TrioRemoteControl.swift` |
| `A` (AndroidAPS b9bb9ef3) | `AckEnvelope.kt` | `core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/localmodel/clientcontrol/AckEnvelope.kt` |
| `A` (AndroidAPS b9bb9ef3) | `AppRepository.kt` | `database/impl/src/commonMain/kotlin/app/aaps/database/AppRepository.kt` |
| `A` (AndroidAPS b9bb9ef3) | `AuthorizedClientsViewModel.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/clientcontrol/compose/AuthorizedClientsViewModel.kt` |
| `A` (AndroidAPS b9bb9ef3) | `AuthRequest.kt` | `plugins/sync/src/androidMain/kotlin/app/aaps/plugins/sync/smsCommunicator/AuthRequest.kt` |
| `A` (AndroidAPS b9bb9ef3) | `BatchActionMapping.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/clientcontrol/BatchActionMapping.kt` |
| `A` (AndroidAPS b9bb9ef3) | `BooleanKey.kt` | `core/keys/src/commonMain/kotlin/app/aaps/core/keys/BooleanKey.kt` |
| `A` (AndroidAPS b9bb9ef3) | `ClientControlCrypto.kt` | `core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/utils/ClientControlCrypto.kt` |
| `A` (AndroidAPS b9bb9ef3) | `ClientControlMessage.kt` | `core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/localmodel/clientcontrol/ClientControlMessage.kt` |
| `A` (AndroidAPS b9bb9ef3) | `ClientControlReceiver.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/clientcontrol/ClientControlReceiver.kt` |
| `A` (AndroidAPS b9bb9ef3) | `CommandExecutor.kt` | `implementation/src/commonMain/kotlin/app/aaps/implementation/queue/CommandExecutor.kt` |
| `A` (AndroidAPS b9bb9ef3) | `CommandQueueImplementation.kt` | `implementation/src/commonMain/kotlin/app/aaps/implementation/queue/CommandQueueImplementation.kt` |
| `A` (AndroidAPS b9bb9ef3) | `ConfigImpl.kt` | `app/src/main/kotlin/app/aaps/implementations/ConfigImpl.kt` |
| `A` (AndroidAPS b9bb9ef3) | `DataSyncSelectorV3.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/DataSyncSelectorV3.kt` |
| `A` (AndroidAPS b9bb9ef3) | `DetermineBasalResult.kt` | `implementation/src/commonMain/kotlin/app/aaps/implementation/aps/DetermineBasalResult.kt` |
| `A` (AndroidAPS b9bb9ef3) | `DetermineBasalSMB.kt` | `plugins/aps/src/commonMain/kotlin/app/aaps/plugins/aps/openAPSSMB/DetermineBasalSMB.kt` |
| `A` (AndroidAPS b9bb9ef3) | `EffectiveProfileSwitch.kt` | `database/impl/src/commonMain/kotlin/app/aaps/database/entities/EffectiveProfileSwitch.kt` |
| `A` (AndroidAPS b9bb9ef3) | `InsertAndCancelCurrentTemporaryTargetTransaction.kt` | `database/impl/src/commonMain/kotlin/app/aaps/database/transactions/InsertAndCancelCurrentTemporaryTargetTransaction.kt` |
| `A` (AndroidAPS b9bb9ef3) | `LoadTreatmentsRunner.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/workers/LoadTreatmentsRunner.kt` |
| `A` (AndroidAPS b9bb9ef3) | `LocalAlertUtilsImpl.kt` | `implementation/src/commonMain/kotlin/app/aaps/implementation/alerts/LocalAlertUtilsImpl.kt` |
| `A` (AndroidAPS b9bb9ef3) | `LoopPlugin.kt` | `plugins/aps/src/commonMain/kotlin/app/aaps/plugins/aps/loop/LoopPlugin.kt` |
| `A` (AndroidAPS b9bb9ef3) | `LoopViewModel.kt` | `plugins/aps/src/commonMain/kotlin/app/aaps/plugins/aps/loop/compose/LoopViewModel.kt` |
| `A` (AndroidAPS b9bb9ef3) | `medtrum/comm/enums/AlarmState.kt` | `pump/medtrum/src/main/kotlin/app/aaps/pump/medtrum/comm/enums/AlarmState.kt` |
| `A` (AndroidAPS b9bb9ef3) | `NsclientLongKey.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/keys/NsclientLongKey.kt` |
| `A` (AndroidAPS b9bb9ef3) | `nsclientV3/extensions/DeviceStatusExtension.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/DeviceStatusExtension.kt` |
| `A` (AndroidAPS b9bb9ef3) | `nsclientV3/extensions/EffectiveProfileSwitchExtension.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/EffectiveProfileSwitchExtension.kt` |
| `A` (AndroidAPS b9bb9ef3) | `nsclientV3/extensions/GlucoseValueExtension.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/GlucoseValueExtension.kt` |
| `A` (AndroidAPS b9bb9ef3) | `nsclientV3/extensions/ProfileSwitchExtension.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/extensions/ProfileSwitchExtension.kt` |
| `A` (AndroidAPS b9bb9ef3) | `NSClientV3Plugin.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/NSClientV3Plugin.kt` |
| `A` (AndroidAPS b9bb9ef3) | `OapsProfile.kt` | `core/interfaces/src/commonMain/kotlin/app/aaps/core/interfaces/aps/OapsProfile.kt` |
| `A` (AndroidAPS b9bb9ef3) | `OpenAPSSMBPlugin.kt` | `plugins/aps/src/commonMain/kotlin/app/aaps/plugins/aps/openAPSSMB/OpenAPSSMBPlugin.kt` |
| `A` (AndroidAPS b9bb9ef3) | `ProfileRepositoryImpl.kt` | `implementation/src/commonMain/kotlin/app/aaps/implementation/profile/ProfileRepositoryImpl.kt` |
| `A` (AndroidAPS b9bb9ef3) | `ProfileSealed.kt` | `core/objects/src/commonMain/kotlin/app/aaps/core/objects/profile/ProfileSealed.kt` |
| `A` (AndroidAPS b9bb9ef3) | `ProfileSwitch.kt` | `database/impl/src/commonMain/kotlin/app/aaps/database/entities/ProfileSwitch.kt` |
| `A` (AndroidAPS b9bb9ef3) | `PumpEnactResult.kt` | `core/interfaces/src/commonMain/kotlin/app/aaps/core/interfaces/pump/PumpEnactResult.kt` |
| `A` (AndroidAPS b9bb9ef3) | `PumpStatusProviderImpl.kt` | `implementation/src/commonMain/kotlin/app/aaps/implementation/pump/PumpStatusProviderImpl.kt` |
| `A` (AndroidAPS b9bb9ef3) | `PumpSyncImplementation.kt` | `implementation/src/commonMain/kotlin/app/aaps/implementation/pump/PumpSyncImplementation.kt` |
| `A` (AndroidAPS b9bb9ef3) | `RT.kt` | `core/interfaces/src/commonMain/kotlin/app/aaps/core/interfaces/aps/RT.kt` |
| `A` (AndroidAPS b9bb9ef3) | `RunningConfigurationImpl.kt` | `plugins/configuration/src/commonMain/kotlin/app/aaps/plugins/configuration/configBuilder/RunningConfigurationImpl.kt` |
| `A` (AndroidAPS b9bb9ef3) | `RunningMode.kt` | `database/impl/src/commonMain/kotlin/app/aaps/database/entities/RunningMode.kt` |
| `A` (AndroidAPS b9bb9ef3) | `Scene.kt` | `core/data/src/commonMain/kotlin/app/aaps/core/data/model/Scene.kt` |
| `A` (AndroidAPS b9bb9ef3) | `SceneAction.kt` | `core/data/src/commonMain/kotlin/app/aaps/core/data/model/SceneAction.kt` |
| `A` (AndroidAPS b9bb9ef3) | `SceneExecutor.kt` | `implementation/src/commonMain/kotlin/app/aaps/implementation/scenes/SceneExecutor.kt` |
| `A` (AndroidAPS b9bb9ef3) | `SettingsIdentifiers.kt` | `plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/SettingsIdentifiers.kt` |
| `A` (AndroidAPS b9bb9ef3) | `SmsCommunicatorPlugin.kt` | `plugins/sync/src/androidMain/kotlin/app/aaps/plugins/sync/smsCommunicator/SmsCommunicatorPlugin.kt` |
| `A` (AndroidAPS b9bb9ef3) | `StringNonKey.kt` | `core/keys/src/commonMain/kotlin/app/aaps/core/keys/StringNonKey.kt` |
| `A` (AndroidAPS b9bb9ef3) | `TemporaryTarget.kt` | `database/impl/src/commonMain/kotlin/app/aaps/database/entities/TemporaryTarget.kt` |
| `A` (AndroidAPS b9bb9ef3) | `TemporaryTargetDao.kt` | `database/impl/src/commonMain/kotlin/app/aaps/database/daos/TemporaryTargetDao.kt` |
| `A` (AndroidAPS b9bb9ef3) | `TraceableDao.kt` | `database/impl/src/commonMain/kotlin/app/aaps/database/daos/TraceableDao.kt` |
| `A` (AndroidAPS b9bb9ef3) | `TreatmentMapper.kt` | `core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/mapper/TreatmentMapper.kt` |
| `A` (AndroidAPS b9bb9ef3) | `TTPreset.kt` | `core/data/src/commonMain/kotlin/app/aaps/core/data/model/TTPreset.kt` |
| `O` (oref0 d219baf9) | `basal-set-temp.js` | `lib/basal-set-temp.js` |
| `O` (oref0 d219baf9) | `determine-basal.js` | `lib/determine-basal/determine-basal.js` |
| `O` (oref0 d219baf9) | `lib/profile/index.js` | `lib/profile/index.js` |
| `O` (oref0 d219baf9) | `mm-format-ns-glucose.sh` | `bin/mm-format-ns-glucose.sh` |
| `O` (oref0 d219baf9) | `mm-format-ns-treatments.sh` | `bin/mm-format-ns-treatments.sh` |
| `O` (oref0 d219baf9) | `nightscout.sh` | `bin/nightscout.sh` |
| `O` (oref0 d219baf9) | `ns-dedupe-treatments.sh` | `bin/ns-dedupe-treatments.sh` |
| `O` (oref0 d219baf9) | `ns-status.js` | `bin/ns-status.js` |
| `O` (oref0 d219baf9) | `oref0-ns-loop.sh` | `bin/oref0-ns-loop.sh` |
| `O` (oref0 d219baf9) | `oref0-pump-loop.sh` | `bin/oref0-pump-loop.sh` |
| `O` (oref0 d219baf9) | `oref0-set-device-clocks.sh` | `bin/oref0-set-device-clocks.sh` |
| `O` (oref0 d219baf9) | `oref0-upload-profile.js` | `bin/oref0-upload-profile.js` |
| `O` (oref0 d219baf9) | `targets.js` | `lib/profile/targets.js` |
