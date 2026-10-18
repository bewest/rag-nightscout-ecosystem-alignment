# Technical control loops: controller, hub and spoke, delegation

*Contributor-facing.* **Snapshot — describes the source revisions in §0, read 2026-10-17.**
Every behavioural claim cites source or an existing repository document. Claims are
**read-derived** (from reading code, not from running it) unless marked otherwise; anything
inferred beyond what the code says is marked *inferred*. Nothing here was run on a device or
simulator.

This page supplies content for three STPA-style control-structure drawings. Each family has a
drawing input (YAML, same schema as `tools/structure-diagrams/inputs/`), a short narrative of what
the loop controls and how the controller learns the result, and unsafe-control-action (UCA)
prompts. The prompts are **questions for analysis, not findings**.

| Family | Drawing input | Zoom levels proposed (not drawn) |
|---|---|---|
| 1. Controller loop on the phone | [`3-controller.yaml`](../../../tools/structure-diagrams/inputs/3-controller.yaml) | **L1a** inside the controller app |
| 2. Hub-and-spoke sync loop | [`3-hub-sync.yaml`](../../../tools/structure-diagrams/inputs/3-hub-sync.yaml) | **L2a** per-collection view of the hub |
| 3. Delegation loop | [`3-delegation.yaml`](../../../tools/structure-diagrams/inputs/3-delegation.yaml) | **L3a** per-controller validation pipeline |

The three drawings nest: L1's `hub` node opens into L2, L2's `app` node opens into L1, and L3
reuses the hub and controller boxes with the command path added.

*Relabelled 2026-10-17:* L1, L2 and L3 are now the drawings **3·controller**, **3·hub-sync** and
**3·delegation**, published in [Control structures, drawn](../../00-overview/perspective/STRUCTURES.md);
their inputs moved to `tools/structure-diagrams/inputs/`. The zoom levels L1a–L3a below remain
proposals; the drawings no longer carry markers for them.

---

## 0. Sources

| Project | Revision read | Path under `externals/` |
|---|---|---|
| Loop (LoopWorkspace) | `f841285` (2026-09-19) | `LoopWorkspace/` (Loop, LoopKit, NightscoutService) |
| Trio | `e41c9db37` (2026-09-22) | `Trio/` |
| AndroidAPS | `7e1d537d49` (dev, 2026-09-23) | `AndroidAPS/` — release 3.4.2.6 is not an ancestor; **dev-only** marks items absent from release 3.4.2.6; they ship in the 4.0.0-beta1 and 4.0.0-rc1 prereleases, per the [intent and workflow landscape](../../30-design/platform/nightscout-intent-workflow-landscape-2026-10-09.md) §1 |
| cgm-remote-monitor | `a8888f0d` (2026-09-09) | `cgm-remote-monitor-official/` (the `cgm-remote-monitor/` checkout is a 2014 revision and was not used) |
| LoopCaregiver | `2305718` | `LoopCaregiver/` |
| LoopFollow | `4a74b781` | `LoopFollow/` |
| nightguard | `75404bd` | `nightguard/` |
| xDrip+ | `1ed760048` | `xDrip/` |

Repository documents used: [remote bolus comparison](../../10-domain/remote-bolus-comparison.md),
[authority model](../../10-domain/authority-model.md),
[LoopFollow deep dive](../../10-domain/loopfollow-deep-dive.md),
[LoopCaregiver deep dive](../../10-domain/loopcaregiver-deep-dive.md),
[hub-and-spoke sync architecture](../../30-design/platform/nightscout-hub-sync-architecture-2026-09-11.md),
[intent and workflow landscape](../../30-design/platform/nightscout-intent-workflow-landscape-2026-10-09.md)
(cited below as *landscape*).

---

## 1. The controller loop on the phone

### 1.1 Drawing

[`3-controller.yaml`](../../../tools/structure-diagrams/inputs/3-controller.yaml): six nodes. Person (supervisor) at the top;
the controller app; pump (actuator) and CGM (sensor); the body (controlled process). A pointer
node for the Nightscout hub carries the app's outbound record of applied state and opens into L2.

**Zoom L1a (proposed, not drawn).** The controller box opens into: algorithm; CGM manager; pump
manager with its command queue; dose, glucose and carb stores; uploader. That is where the
differences in the table below live, and drawing them on L1 would take it past ten nodes.

### 1.2 What the loop controls and how the controller learns the result

The controlled variable is glucose; the manipulated variable is insulin delivery above or below
the scheduled basal. All three controllers run a cycle of roughly five minutes, triggered by new
CGM data or a pump heartbeat; read glucose, pump state and recent insulin and carbohydrate records;
predict glucose; and command a **temporary basal rate with a bounded duration**, plus (when
enabled) a small automatic bolus. The pump's acceptance or failure of each command is the
immediate feedback; the CGM reading some minutes later is the feedback on the process.

The bounded temp-basal duration is the design property that matters for lost communication: the
loop-set temp basal is 30 minutes by default in all three (Loop
`LoopKit/LoopKit/LoopAlgorithm/DoseMath.swift:404,477`; Trio
`Trio/Sources/APS/OpenAPSSwift/DetermineBasal/DosingEngine.swift:402,431,463`; AAPS
`plugins/aps/.../openAPSSMB/DetermineBasalSMB.kt:200-265`). *Inferred from temp-basal semantics,
not traced per pump driver:* if the controller stops commanding, the pump returns to its
scheduled basal when the running temp basal ends. That fallback can be higher or lower than what
the controller would have chosen.

### 1.3 Differences

| | Loop | Trio | AAPS |
|---|---|---|---|
| **Cycle trigger** | new CGM data, at most once per 4.2 min, or a pump BLE heartbeat that refreshes the CGM; pump data is refreshed before the loop runs (`Loop/Loop/Managers/DeviceDataManager.swift:562-577,1011-1021,1098-1125`) | pump heartbeat (also called from `FetchGlucoseManager.swift:317`) → `ensureCurrentPumpData` → `recommendsLoop` → `APSManager.loop()`, minimum interval 3 min (`APS/DeviceDataManager.swift:270-311`; `APSManager.swift:226-231,292-320`; `Config/Config.swift:7`) | `PostCalculationRunner` invokes the loop after the IOB/COB calculation for a new glucose value (`workflow/.../PostCalculationRunner.kt:87`); also on temp-target change and manual refresh (`LoopPlugin.kt:216`) |
| **Algorithm** | LoopKit prediction and `DoseMath` in-app | Swift port of oref (`APS/OpenAPSSwift/`; landscape §1) | oref-derived Kotlin, selectable plugin (SMB, AMA, AutoISF) (`plugins/aps/`) |
| **What it commands** | temp basal; with the automatic-bolus strategy, a partial bolus (default factor 0.4, `Loop/Models/LoopConstants.swift:53`). Temp basal first, bolus only if it succeeded (`Loop/Managers/DoseEnactor.swift`) | temp basal from the determination, then SMB if `smbToDeliver > 0` (`APSManager.swift:773-805`) | temp basal, then SMB only if the temp basal was enacted; both inside one non-cancellable block; an SMB more than one minute past `deliverAt` is refused (`LoopPlugin.kt:686-745`) |
| **Limits at the enact step** | automatic-dosing IOB ceiling = 2 × maximum bolus (`LoopDataManager.swift:1814-1816`); maximum basal; a recommendation older than 5 min is not enacted (`LoopDataManager.swift:1902`) | oref profile limits (max IOB, max basal) inside the algorithm — *not traced in this pass*; constrained modes clamp max IOB to 0 (`Models/DosingMode.swift:22-36`) | constraint checker re-applies basal, percent and bolus limits to the algorithm's result; minimum SMB interval `ApsMaxSmbFrequency` (`LoopPlugin.kt:590-608`) |
| **Stale or missing glucose** | glucose or pump data older than 15 min → `glucoseTooOld` / `pumpDataTooOld`, no dose (`LoopCore/LoopCoreConstants.swift:14`; `LoopDataManager.swift:1249-1258`); `CGMStalenessMonitor` also turns automatic dosing off (`DeviceDataManager.swift:454-462`) | `APSManager.determineBasal` fails validation if the newest reading is older than 12 min or fewer than 3 readings exist; the throw precedes `enactDetermination` (`APSManager.swift:510-558`). The algorithm itself also has a stale-glucose branch that replaces a high temp with a neutral one (`DetermineBasalGenerator.swift:620-670`); *read-derived, to verify:* that branch's result is not enacted, because the validation throw comes first | glucose status is `null` if the newest bucketed reading is older than 7 min; the APS plugin returns with no result and the loop enacts nothing (`GlucoseStatusCalculatorSMB.kt:40`; `OpenAPSSMBPlugin.kt:303-306`) |
| **Lost pump communication** | enactment error surfaces as a loop error; `pumpIsAllowingAutomation` gates automatic dosing (`DeviceDataManager.swift:454-462`); delivery-uncertain state has its own alert manager (`Loop/Managers/DeliveryUncertaintyAlertManager.swift`) | pump errors flow to `processError` (`APSManager.swift:233-238`); suspended, bolusing or empty-reservoir states block enactment (`APSManager.swift:440-460,786-788`) | `KeepAliveWorker.checkPump` raises a pump-unreachable alarm from the last connection time (`implementation/.../KeepAliveWorker.kt:242-265`); a busy command queue skips the run (`LoopPlugin.kt:565-569`) |
| **Human in or on the loop** | `dosingEnabled` (user's closed-loop switch) AND `isAutomaticDosingAllowed` (CGM fresh, sensor valid, pump allowing automation) (`LoopAppManager.swift:267-271`); open loop computes but does not enact (`LoopDataManager.swift:888-892`). Meal boluses are user-confirmed | `DosingMode` {closed, open, lowGlucoseSuspend, basalTesting}; open = determine only, never enact (`APSManager.swift:382,436`; `DosingMode.swift`) | `RunningMode` incl. OPEN_LOOP, where each change is a suggestion the user must accept (`acceptChangeRequest`, `LoopPlugin.kt:799`); constraints can force OPEN_LOOP or LGS with `autoForced` (`LoopPlugin.kt:450-500`) |
| **How it records applied state** | dosing decision store; uploads intent (`dosingEnabled`), not the gated `automaticDosingEnabled` (landscape §3) | `reportEnacted` marks the determination enacted (`APSManager.swift:436-438,845+`); uploaded as `devicestatus.openaps.enacted` | `lastRun.tbrSetByPump` / `smbSetByPump` (`LoopPlugin.kt:723-735`); RunningMode has requested and constraint-forced layers (landscape §3.3) |

### 1.4 Unsafe control action prompts (L1)

Control action: **temp basal / automatic bolus from controller to pump.**

- *Not provided.* What does each controller do when glucose is stale and a high temp basal is
  running — enact a neutral rate, or leave the high temp to run out? (Trio's two stale-glucose
  paths in §1.3 are the case to check first.) What does the person see, and when?
- *Not provided.* When the phone app is suspended by the OS and no cycle runs, which alarm tells
  the person, after how long, and is that alarm on the phone that has also stopped?
- *Provided when unsafe.* Can an automatic bolus be enacted when the pump's own history has not
  been read since the last manual bolus on the pump body? Which controllers refresh pump data
  before every cycle?
- *Provided when unsafe.* Can a CGM reading that is fresh but wrong (compression low, calibration
  artefact, a follower CGM fed from the hub) drive dosing? Which noise or "unchanged data" checks
  apply in each controller?
- *Wrong timing or order.* If the temp basal succeeds and the bolus fails, or the reverse, what
  state does the controller believe the pump is in? (All three order temp basal before bolus; is
  the reverse failure handled the same way?)
- *Wrong timing.* Can a recommendation computed before a slow pump exchange be enacted after
  newer glucose arrives? (Loop: 5-minute expiry; AAPS: 1-minute SMB `deliverAt`; Trio: 30-minute
  determination lookup window in `enactDetermination`.)
- *Stopped too soon / applied too long.* When the controller stops (crash, phone off), the last
  temp basal runs up to 30 minutes and then scheduled basal resumes. For which situations is the
  scheduled basal itself the unsafe action?
- *Supervisor.* When the person switches to open loop or a constrained mode, does every display
  (phone, watch, followers via L2) show that automation is reduced, or only the phone?

---

## 2. The hub-and-spoke sync loop

### 2.1 Drawing

[`3-hub-sync.yaml`](../../../tools/structure-diagrams/inputs/3-hub-sync.yaml): seven nodes. The hub in the middle;
uploaders and the controller below it (writers); followers and the web UI above it (readers and,
for the web UI, writers of requested state); reports to the side. **Requested state** and
**applied state** are separate edges: requests flow down to the controller as downloaded
entities; applied state flows up as devicestatus and delivered records.

**Zoom L2a (proposed, not drawn).** The hub box opens into its collections (`entries`,
`treatments`, `devicestatus`, `profile`, `settings`, `food`, `activity`) with the API generation
each spoke uses. Drawing every spoke separately would need about fifteen nodes, so followers are
one group box here.

### 2.2 What the loop controls and how each side learns the result

The hub does not control insulin. It is the shared record that lets people and software away from
the phone observe the L1 loop, and, through a few opt-in paths, lets requests reach the controller.
Under decision D18 the hub is responsible for observability and the controller for sending data
accurately and reconciling (landscape, preamble). No hub composes intents (landscape §7).

**What each spoke writes and reads.**

| Spoke | Writes | Reads | API and auth |
|---|---|---|---|
| Loop (NightscoutService) | `treatments`, `devicestatus` (`loop`, `override`, `pump`), `profile` with `loopSettings` (override presets, APNs device token and bundle id), optionally `entries` | can read `entries` as its CGM through the NightscoutRemoteCGM plugin (`LoopWorkspace/NightscoutRemoteCGM/`); otherwise does not download treatments | v1, seven endpoints, no watermark or delta (hub-sync §1–2); API secret |
| Trio | `treatments`, `devicestatus.openaps` (suggested/enacted, applied ISF/CR/target), `profile` (presets, APNs coordinates), optionally `entries` | carbs and temp targets every minute when `isDownloadEnabled` (default `false`) (`APS/FetchTreatmentsManager.swift:16-67`; `Models/TrioSettings.swift:22`); a Nightscout CGM source exists (`APS/CGM/CGMType.swift`) | v1, five endpoints (hub-sync §1–2); hashed API secret header (`NightscoutAPI.swift:141-143`) |
| AAPS | all collections via v3, with `lastModified` watermark and `history` deltas | profile switch, temp target, running mode, carbs, insulin, therapy events, CGM only if the matching `NsClientAccept*` preference is on; all default `false` (`core/keys/.../BooleanKey.kt:220-228`). **dev-only:** signed client-control documents in `settings` (§3) | v3, twenty endpoints (hub-sync §1–2) |
| CGM uploaders (xDrip+, connectors, bridges) | `entries`; xDrip+ also `treatments`, `devicestatus`, `activity` (`xDrip/.../utilitymodels/NightscoutUploader.java:130-161`) | — | v1 |
| xDrip+ follower | — | `entries`, `treatments`, latest `devicestatus` (`xDrip/.../cgm/nsfollow/NightscoutFollow.java:52-61`) | v1 |
| LoopFollow | provisions a read-only subject for itself using the API secret (`LoopFollow/Helpers/NightscoutUtils.swift:416-520`); **no treatment writes found** (`executePostRequest` has no callers at `4a74b781`) | `entries`, `treatments`, latest `devicestatus`, current `profile` (APNs token from it, `Controllers/Nightscout/ProfileManager.swift:111`), status | v1, token (LoopFollow deep dive) |
| nightguard | `Temporary Target` treatments, including zero-duration cancels (`nightguard/external/NightscoutService.swift:1827-1890`; landscape §4) | `entries`, `treatments`, `devicestatus`; requests a token via `/api/v2/authorization/request/token` | v1 |
| LoopCaregiver | remote-command relay requests (§3); experimental Remote Commands 2 documents | glucose, boluses, carbs, override presets, latest devicestatus, profile (LoopCaregiver deep dive, "Remote Data Service") | NightscoutKit fork (not available locally); API secret |
| Web UI, careportal, plugins | careportal posts `/api/v1/treatments/` (`lib/client/careportal.js:389-405`); the `loop` plugin posts `/api/v2/notifications/loop` (`lib/plugins/loop.js:115`) | receives `dataUpdate` deltas over socket.io (`lib/server/websocket.js:150`); plugins (`loop`, `openaps`, `pump`, `iob`, `cob`, `override`, alarms, `pushover`) render and alarm from the same data | session token or API secret |

**Requested versus applied.** Kept apart in the drawing because the wire mostly does not keep them
apart (landscape §2, property P3):

- **Applied** is reported by the controller: Loop and Trio in `devicestatus` (Trio's
  `openaps.enacted` carries applied ISF, CR and target; measured on one corpus site, landscape
  §3.2); AAPS as an `EffectiveProfileSwitch` written only after the pump accepts a profile
  (landscape §3.3).
- **Requested** reaches the controller only as an ordinary entity that the controller has opted to
  download (Trio carbs and temp targets; AAPS per-type opt-ins). A careportal or nightguard temp
  target that a controller applies is indistinguishable on the hub from one it did not apply
  (landscape §6).
- The two hubs disagree on what is active from the same records (measured, landscape §5), so a
  follower's picture of applied state depends on which hub it reads.

### 2.3 Unsafe control action prompts (L2)

Control actions: **a requested entity downloaded by the controller**; **a follower's display or
alarm acted on by a caregiver.**

- *Not provided.* If the controller cannot upload for an hour, what does each follower show, and
  does any follower alarm on missing devicestatus as opposed to missing glucose?
- *Not provided.* A caregiver enters a temp target in careportal for a controller that has
  downloads off. Who tells the caregiver it was not applied?
- *Provided when unsafe.* Carbs entered on the hub by one client and downloaded by Trio or AAPS
  change carbs-on-board and therefore dosing. What prevents a duplicate entry (entered on the phone
  and on the hub) from being counted twice?
- *Provided when unsafe.* When a controller uses hub `entries` as its CGM source, the uploader, the
  hub and the controller form a loop through the network. What bounds the age of that reading at
  the moment of dosing?
- *Wrong timing.* A temp target written with a past `created_at`, or arriving out of order: which
  one does each controller enable? (Trio enables the newest of a batch, `FetchTreatmentsManager.swift:47-64`.)
- *Stopped too soon / applied too long.* A cancel encoded as a zero-duration record or a shortened
  duration (landscape §4): which spokes read the cancel and which keep showing the target until
  its original end? (Measured for the two hubs, landscape §5.)
- *Display.* Two followers reading the same site show different "active override" states (units
  and supersession differences, landscape §5). Which one does a caregiver act on?

---

## 3. The delegation loop

### 3.1 Drawing

[`3-delegation.yaml`](../../../tools/structure-diagrams/inputs/3-delegation.yaml): seven nodes. The person or primary
caregiver who grants the credential; the caregiver or automated agent who sends; the remote app;
the hub; the push or SMS relay; the controller; the pump. Two edges are `status: proposed`: a
command record with an id at the hub, and a correlated acknowledgement from the controller. Those
are the parts that are missing on most paths today (§3.4).

**Zoom L3a (proposed, not drawn).** The controller box opens into each controller's validation
pipeline (enabled check → authentication → freshness → replay check → amount limits → enact →
reply). The rows of the table in §3.3 are that drawing's content.

### 3.2 What the loop controls and how the sender learns the result

The sender asks the controller to change its inputs: deliver a bolus, record carbs, set a temp
target or override, change mode. The controller, not the sender, owns the pump, so every path
ends in the controller's own validation and enactment. The sender learns the result through one
of four channels: a direct reply (APNs or SMS) on paths where the sender supplied a return
address; the resulting record appearing on the hub; a free-text failure `Note` on the hub; or,
**dev-only** in AAPS, a signed acknowledgement document with a correlation id. No path gives the
hub a request record it could show (landscape §6).

A "smart agent" acting on someone's behalf has no path of its own. It would hold one of the
credentials below and be indistinguishable from the caregiver who gave it that credential. The
delegation grants with scopes, constraints, expiry and revocation in the
[authority model](../../10-domain/authority-model.md) are recorded there as **not implemented**
("Current State (Gaps)").

### 3.3 Paths compared

| Path | Who authorises the sender | How the controller verifies | What confirms it was applied |
|---|---|---|---|
| **A. Careportal or LoopCaregiver → hub → APNs → Loop** | hub permission `notifications:loop:push` (`lib/api2/notifications-v2.js:19`); of the default roles only `admin` (`*`) holds it (`lib/authorization/storage.js:140-148`). The hub needs `profile[0].loopSettings.deviceToken` and `bundleIdentifier` and sets `expiration` = now + 5 min (`lib/server/loop.js:31-45,127`) | duplicate notification id; expiry if present; **TOTP only for bolus and carbs** — overrides and override cancel need none (`NightscoutServiceKit/RemoteCommands/V1/Notifications/*RemoteNotification.swift`, `otpValidationRequired`); TOTP period 30 s, two codes accepted, reuse refused (`OTPManager.swift:79-121`); bolus ≤ max bolus (`Loop/Managers/ServicesManager.swift:332-350`); override duration ≤ max (`:276-296`) | success: the resulting record is uploaded (`triggerUpload`) and a local notification shows on the Loop phone. Failure: a `Note` treatment whose text is the error plus the raw notification payload (`NightscoutService.swift:487-519`). The hub builds no return address, so no reply reaches the sender (landscape §6) |
| **B. LoopFollow → APNs → Loop** | LoopFollow holds the APNs key and team id and the Loop TOTP QR; it reads the device token from the hub profile (`LoopFollow/Remote/LoopAPNS/LoopAPNSService.swift:352-361`; `ProfileManager.swift:111`) | as A | as A, plus a direct APNs reply to LoopFollow when it supplies return info (`NightscoutService.swift:462-484`); the reply carries no command id (landscape §3, P6) |
| **C. LoopFollow → APNs → Trio** | shared secret configured in both apps; payload sealed with AES-GCM (`LoopFollow/Remote/TRC/SecureMessenger.swift:18-22`; Trio `RemoteControl/SecureMessenger.swift:30-31`) | remote control enabled; secret present; decrypts; timestamp within ±600 s (`TrioRemoteControl.swift:16-66`). Bolus: `BolusSafetyValidator` — max bolus, IOB available, max IOB, and reject if boluses totalling > 20 % of the request were delivered since the command's timestamp (`TrioRemoteControl+Bolus.swift`). *Read-derived:* no message-id replay store in the dispatcher; within the window the 20 % rule is the bolus repeat guard | reply "Initiating bolus…" before enactment, then "Bolus started" when `enactBolus` reports success, i.e. the pump accepted the command, not that delivery finished (*read-derived*). Failure: reply plus `Note` (`TrioRemoteControl+Helpers.swift:4-20`) |
| **D. Any hub writer → `treatments` → Trio or AAPS download** | any token with `api:treatments:create` (default role `careportal`); nightguard and careportal write temp targets | none beyond the controller's opt-in setting (Trio `isDownloadEnabled`; AAPS `NsClientAccept*`, all default off) and its normal limits (*read-derived*) | none distinct: the request is the record (landscape §6) |
| **E. SMS → AAPS (3.4.2.6 and dev)** | sender phone number on the allowed list; remote commands enabled (`plugins/sync/.../SmsCommunicatorPlugin.kt:296-360`) | reply with TOTP + PIN within 5 min (`AuthRequest.kt:43-58`; `OneTimePassword.kt:85-105`; `Constants.kt:60,91`); remote boluses at least 15 min apart, or the configured distance when several numbers are allowed (`Constants.kt:17`; plugin `:312-315,348-353`); bolus constraints applied (`processBOLUS`) | SMS reply to the sender |
| **F. AAPSClient → hub `settings` → AAPS (dev-only)** | per-client pairing with an HMAC secret (`core/nssdk/.../clientcontrol/SignedEnvelope.kt`) | HMAC first, then a per-client counter that must increase, then ±5 min clock skew, then `validUntil` (`ClientControlReceiver.kt:67-100`). A remote bolus is prepare/commit: the controller computes a QuickWizard dose and returns a preview; the commit delivers that parked dose at most once (`ClientControlReceiver.kt:532-600`) | signed ack `Executing` → `Done {Ok, Failed, Expired}` → optional late `Delivery {Failed}`, correlated by the command counter (`AckEnvelope.kt:8-30`) |
| **G. LoopCaregiver Remote Commands 2** | API secret | expects a command collection with Pending → InProgress → Success/Error (`LoopCaregiverKit/.../NightscoutDataSource.swift:136-215`); neither hub has that collection (landscape §6); needs a special hub and Loop branch (LoopCaregiver deep dive) | the status field, where the branch exists |
| **H. Automated agent** | whatever credential it is given (A–F) | as the path it uses | as the path it uses |

### 3.4 What is missing

1. **A request record and correlated acknowledgement on the hub.** Only F has one, and F is
   dev-only and AAPS-only. On A–E the hub sees success only as the resulting entity and failure
   only as free text (landscape §6). The two `status: proposed` edges in L3 are this gap.
2. **Replies on hub-relayed paths.** Path A cannot reply to the sender, because the hub does not
   add a return address. A careportal user learns of failure only by reading `Note` treatments.
3. **Accepted versus delivered.** Loop's and Trio's success messages are sent after the pump
   accepts the command (*read-derived*). Only AAPS dev has a separate late delivery-failure ack.
4. **Authorisation granularity.** The hub's relay permission sits in `admin` by default, so the
   person who can send a remote bolus can also do everything else on the site. No per-caregiver
   identity reaches the controller: `enteredBy` is free text and remote bolus and carbs lose the
   initiator (landscape §3, P5; authority model).
5. **Unequal protection across command types.** In Loop, overrides need no TOTP (path A), yet an
   override scales basal, ISF and carb ratio (landscape §3.1). Entity downloads (path D) carry
   no expiry and no authentication beyond hub write access.
6. **No agent model.** No scopes, rate limits, time windows, expiry or revocation per agent. The
   authority model's grants are a proposal. Revoking one caregiver today means rotating the shared
   credential for everyone (*inferred* from the credentials being shared secrets).

### 3.5 Unsafe control action prompts (L3)

Control actions: **remote bolus**, **remote carbs**, **remote override or temp target**.

- *Not provided.* A remote bolus fails validation on a hub-relayed path. How long until the
  caregiver knows, and through what? Could they assume success and give carbs?
- *Not provided.* A caregiver cancels an override remotely while the phone is offline. When does
  the controller learn of it, and what does the caregiver see in the meantime?
- *Provided when unsafe.* The same bolus arrives twice: APNs redelivery after a force-quit (Loop
  dedupes by id), a resend inside Trio's ±600 s window, or a caregiver retrying after no reply. Which
  guard stops the second one in each path?
- *Provided when unsafe.* A caregiver and the person both bolus for the same meal within minutes.
  Which paths see the other's bolus before validating (Trio's 20 % rule, AAPS SMS distance)? Which
  do not?
- *Provided when unsafe.* An agent holding the same credential as a caregiver sends a command the
  person would not have authorised. What, other than the shared secret, distinguishes them at the
  controller?
- *Wrong timing.* A command delayed in APNs or SMS arrives near the end of its validity window,
  after glucose has changed. Is the dose re-evaluated at arrival (AAPS dev prepare/commit), or
  only checked against static limits?
- *Wrong timing.* Remote carbs with a past start time: does each controller back-date absorption,
  and does that produce an immediate correction?
- *Stopped too soon / applied too long.* A remote override with duration 0 means indefinite in
  Loop (`ServicesManager.swift:289-291`). Who ends it, and does every follower show that it is still
  running?

---

## 4. Corrections to existing documents found while writing this

These were found against source and are recorded here only. This page does not edit the other
documents.

| Document | Says | Source at the revision in §0 says |
|---|---|---|
| [remote bolus comparison](../../10-domain/remote-bolus-comparison.md), Trio "Architecture" | `Nightscout → APNs → Trio App` | the hub relay builds only the Loop payload from `loopSettings` (`lib/server/loop.js:31-130`); Trio expects an AES-GCM `encrypted_data` payload. The sender observed in source is LoopFollow over direct APNs (landscape §6) |
| same, Summary table | Response Notification: Loop ❌ | Loop replies when the sender supplies return info (`NightscoutService.swift:462-484`); its own GAP-REMOTE-004 already says so |
| [LoopFollow deep dive](../../10-domain/loopfollow-deep-dive.md), "Remote Types" and "Trio Remote Control" | `RemoteType` has a `nightscout` case; TRC posts to `/api/v2/notifications/loop` | `RemoteType` is {none, trc, loopAPNS} (`Remote/RemoteType.swift`); TRC posts to APNs directly (`Remote/TRC/PushNotificationManager.swift:330-332`) |

## 5. Not verified

- Trio's oref profile limits (max IOB, max basal) at enact time; only the remote-bolus validator
  was read.
- Per-pump-driver behaviour when a temp basal ends with no controller present (§1.2 is *inferred*).
- Whether Trio's algorithm-level stale-glucose neutral temp is ever enacted (§1.3).
- Whether Loop's remote bolus passes through IOB checks beyond the max-bolus guard.
- AAPS dev client-control commands other than bolus prepare/commit, and the constraints they pass
  through.
- LoopCaregiver's NightscoutKit fork (not available locally); its Remote Commands 2 hub branch.
- Anything dependent on app lifecycle (background execution, APNs delivery delays); nothing was run.
