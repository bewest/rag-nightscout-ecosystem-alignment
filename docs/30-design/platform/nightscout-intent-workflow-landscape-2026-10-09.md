# Intent, workflow and entity management across the AID controller landscape

*What this is: an analysis (contributor-facing). Read after the [platform index](README.md) and
[glossary](spec/glossary.md) (§2 and §9 first); leads to the [identity specification](spec/identity.md).* **Snapshot — describes 2026-10-09. Status: current; the evidence for D18.** Every claim is **read-derived** (from source, a hypothesis about behaviour) unless marked
**measured**. Sources and commits are in §1. Current decisions: [execution plan
§1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions).
**Corrected in place 2026-10-12:** §5 is measured on both hubs (TL;DR and §12 follow it); the §10 rows for the hub-sync design and `specs/sync/registrations/` record what the
registrations now declare and what remains; the registrations row also records the D18 addendum grammar (`SCHEMA-REG-EXT`, 2026-10-12). **Also 2026-10-18:** §2 records the maintainer's decision on agent initiators (P5); the AndroidAPS items marked **4.0.0 prerelease** ship in `4.0.0-beta1` and `4.0.0-rc1` (§1). The rules this evidence supports are maintained in the [state and intent specification](spec/state-intent.md).

**The question.** Nightscout's API v1 and v3 manage *entities*: create, read, update and delete
documents in `treatments`, `devicestatus`, `profile`. AID controllers increasingly manage
*intent*: a named preset is activated, several intents run at once and combine, the controller
applies something that may differ from what was asked, and the intent ends for a reason. This
document finds, per controller and per hub, where the two differ, so that a controller
registration can describe the difference.

**The direction this serves** (maintainer, 2026-10-09). Registration has two tiers: well-known
declarations shipped with the hub, for backwards compatibility, and controller-owned typed
registrations, for extensibility. Adoption follows the WHATWG pattern — specify what happens now,
leave room to extend. The hub (Nightscout, Nocturne) is responsible for observability; the
controller is responsible for sending data accurately and for syncing and reconciling. Recorded as
**D18** in the execution plan (§2.6.1).

---

## TL;DR

| | Finding |
|---|---|
| **Single records** | Entity CRUD works. Every controller keeps one document per instance and amends or deletes it. Each encodes identity and "ended" differently (§4) |
| **Six things CRUD cannot carry** | definition identity, concurrent intent slots with a composition rule, requested vs applied, end reason, initiator, and the command → acknowledgement → outcome link (§2) |
| **Every controller already built them** | each in its own place: AAPS on the NS `settings` collection (4.0.0 prereleases), Loop and Trio over APNs replies and failure `Note`s, iAPS over NS `Announcement` treatments. None of it is typed, and most of it is invisible to the hub (§3, §6) |
| **The hubs disagree on "what is active now"** | Measured on both hubs: cgm-remote-monitor and Nocturne differ on temp-target cancel, devicestatus override duration units, profile fallback after a timed switch, AAPS timeshift units, and out-of-order override backfill; they agree on `Temporary Override Cancel` (§5) |
| **Composition is controller-specific** | Loop: pre-meal target wins, override factor applies. Trio/iAPS: temp target wins the target, override factors apply. AAPS: temp target replaces targets, profile-switch percentage has already scaled basal/ISF/CR. No hub composes, and under the stated roles none should (§7) |
| **Cowpaths already exist** | Loop and Trio publish preset definitions in the `profile` document; Nightscout's careportal builds its remote-override picker from Loop's. AAPS dev publishes scene and automation definitions plus active-scene state. These are registrations in all but name (§8) |

---

## 1. Sources

| Source | Commit | Notes |
|---|---|---|
| Loop (LoopWorkspace) | `f841285`; Loop `c2fddb76`, LoopKit `325bd820`, NightscoutService `fe075ef` | NightscoutKit `4ec9fd1` (the revision Loop pins) |
| Trio | `e41c9db37` | dev 1.0.1.5; the algorithm runs as a Swift port (`OpenAPS.swift:689-719`), `trio-oref/lib` is vendored and its rules match |
| iAPS | `6cb69e7` (2026-10-04) | shallow clone, read only; still runs oref JS with middleware |
| AndroidAPS | `7e1d537d49` (dev, 2026-09-23) | release `3.4.2.6` (`598e2eb39c`) is not an ancestor; items marked **4.0.0 prerelease** are absent from that release and present in `4.0.0-beta1` (2026-10-08) and `4.0.0-rc1` (2026-10-16), both descendants of `7e1d537d49` ([questionnaire defaults §1](integration-questionnaire-defaults-2026-10-18.md#1-sources)) |
| cgm-remote-monitor | `official/dev` `fade2299` | |
| Nocturne | `42275c812` | |
| LoopCaregiver | `2305718` | pins a NightscoutKit fork not available locally |
| LoopFollow | `4a74b781` | |
| nightguard | `75404bd` | |
| Upstream RFC | cgm-remote-monitor `docs/proposals/agent-control-plane-rfc.md`, v1.0, January 2026 | |

**Measured** items use the 11-site corpus (snapshots 2026-04-01 and 2026-04-26) via
`make schema-effects` and the census under `reports/schema-census/`, or a probe run against
cgm-remote-monitor `lib/data/ddata.js` and `lib/profilefunctions.js` at `fade2299`. The corpus
holds no AAPS closed-loop site and no Trio `profile` document, so every AAPS statement and every
Trio preset-join statement is read-derived.

## 2. Where intent differs from entity management

Six properties. A controller's intent model has each of them; an entity collection has none.

| # | Property | What it means | Why CRUD loses it |
|---|---|---|---|
| P1 | **Definition identity** | an activation refers to a preset by a stable id | presets are copied into the instance, or referenced by name only |
| P2 | **Concurrent slots and composition** | several intents active at once, combined by a controller rule | one collection, one "latest wins" reading per `eventType` |
| P3 | **Requested vs applied** | what was asked, what the device or algorithm accepted, what it computed | one document is both request and effect, or the effect is elsewhere and unlinked |
| P4 | **End reason** | expired, cancelled, superseded, deleted before start, ended by a trigger (carbs, glucose, loop off) | "ended" is encoded as a shortened `duration`, a delete, or a zero-duration record |
| P5 | **Initiator** | phone, watch, shortcut, automation, caregiver, remote | recorded locally or in debug logs; on the wire only free-text `enteredBy` |
| P6 | **Command lifecycle** | request → validate → apply → acknowledge, with a correlation id | no request record; success visible only as the resulting entity; failure as free text |

*P5, decided 2026-10-18 (maintainer):* no `agent` value is added to any initiator vocabulary; an
agent initiator is written in the open-vocabulary form `{value: other, controllerTerm}`, as the
registration specification ([§9](spec/registration.md#9-channels-roles-and-provenance)) does for an agent's roles. No controller records an agent as initiator today. The registrations are built for needs that are latent but measured and demonstrated — in the corpus, in controller source and in the labs — not only for what apps send now; the open form lets a controller, simulator or lab record an agent initiator today, and a shared value can be named once the corpus or a lab shows one in use. ([execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#263-d20--version-scoped-quirks-and-the-two-id-rule-maintainer-2026-10-16),
row 17; [agents in the ecosystem §4.2](agent-trust-boundaries-2026-10-18.md#42-the-upstream-rfc-under-d18)).

## 3. Per-controller matrix

| | Loop | Trio | iAPS | AAPS |
|---|---|---|---|---|
| **P1 definition** | `TemporaryScheduleOverridePreset` with UUID; activation copies the preset; presets uploaded in `profile.loopSettings.overridePresets` **without id**; remote enactment by name | one `OverrideStored` entity, `isPreset` flag; activation mutates the preset row; presets in `profile.overridePresets` {name, duration, percentage, target}; remote by name | separate `OverridePresets` and append-only `Override` log; presets not sent to Nightscout | named profiles in the store; ProfileSwitch copies blocks; TT presets in preferences; **4.0.0 prerelease** Scenes with definition id |
| **P2 slots** | `override` + `preMeal`, concurrent | override + temp target, concurrent | override + temp target, concurrent | ProfileSwitch + TT, concurrent; RunningMode (temporary over permanent); **4.0.0 prerelease** one Scene |
| **P3 requested vs applied** | `dosingEnabled` (intent) vs `automaticDosingEnabled` (gated by CGM and pump); only intent uploaded | applied ISF/CR/target in `devicestatus.openaps.suggested/enacted`, not linked to the override | as Trio | **ProfileSwitch** (request) vs **EffectiveProfileSwitch** (written only after the pump accepts); RunningMode requested vs `autoForced` |
| **P4 end** | derived from `End {natural, early, deleted}`; wire: amended `duration`, or DELETE | wire: delete + re-post with actual duration, new `_id` | ends on expiry, carbs, glucose above/below threshold, chain to next preset; reason in debug log only | shorten `duration` on the same `identifier`; invalidate = v3 soft delete |
| **P5 initiator** | `EnactTrigger {local, remote(addr)}`; phone and watch both `local`; Siri is `remote("Siri")`; remote bolus/carbs lose it | `AdjustmentSource {app, remote, shortcut, watch}` in debug log only; `enteredBy: "Trio"` always | automation is an initiator (end triggers, chain) | `Sources` enum (~80 values) in the local `UserEntry` log, **not synced**; TT `reason: Automation` is the only wire proxy |
| **P6 commands** | APNs; TOTP for bolus/carbs only; optional APNs reply without correlation id; failure as `Note` | APNs, AES-GCM, ±600 s window; reply to sender over APNs; failure `Note` | Nightscout `Announcement` treatments; authorisation is NS write access; no acknowledgement | SMS with TOTP+PIN; **4.0.0 prerelease** signed envelopes on NS `settings`: prepare/commit, `validUntil`, ack Executing → Done{Ok, Failed, Expired} → Delivery{Failed} |
| **Unique, needs typing** | retroactive application of override factors over the history window; pre-meal end triggers; GBAF and IRC (stored locally, not uploaded) | `smbIsOff`, scheduled SMB-off hours, ISF/CR scope, `smbMinutes`/`uamMinutes`, `dosingMode` | maxIOB, autoISF set, basal toggle, glucose-threshold end conditions, preset chaining | EPS scaled vs PS base `profileJson`; RunningMode `RESUME`; scenes with revert-only-if-still-owned |

### 3.1 Loop

- **Override wire shape.** `eventType: "Temporary Override"`, `reason` = preset symbol and name,
  `duration` (minutes) or `durationType: "indefinite"`, `correctionRange` (mg/dL),
  `insulinNeedsScaleFactor`, `remoteAddress`, `_id` = the instance UUID. No `syncIdentifier` field
  is sent. Whether the UUID `_id` survives depends on the server's `UUID_HANDLING` setting; without
  it the upsert falls back to `created_at` + `eventType`.
- **Pre-meal is not on the wire.** Not a treatment, not in the profile; devicestatus
  `override.active` is false when only pre-meal is on. Its target replaces the override's while it
  lasts; the override's scale factor still applies.
- **Scale factor.** basal × f, ISF × 1/f, CR × 1/f. Target replaces the scheduled target.
- **Pump suspend** uploads as `Temp Basal` rate 0, `reason: "suspend"`; resume is not uploaded.
- **Measured** (distinct documents, `make schema-effects`). 2,428 `Temporary Override`
  treatments, all with effect and motivation. Of 55,938 active devicestatus overrides: 42,799
  effect + motivation, 2,176 effect only (custom overrides have no name), 10,892 motivation only.

### 3.2 Trio and iAPS

- **Override wire shape.** `eventType: "Exercise"` for **every** override regardless of purpose;
  `notes` = the preset name (or "Custom Override"); `duration` with indefinite sentinel 43200
  (Trio) or 2880 (iAPS). Percentage, target, ISF/CR scope and SMB settings are not sent. The
  struct's `id` is excluded from its coding keys. The wire identity is `created_at` + `eventType`.
- **Measured.** One site carries all Trio `Exercise` documents: **399 distinct `_id`**, 389
  distinct `created_at`, 81 with `duration: 43200`. Applied ISF, CR, target and
  `sensitivityRatio` are present on all 73,898 of that site's `openaps` devicestatus documents.
- **Recovering the effect** needs a time join to devicestatus (post-composition, unattributed) or,
  for presets only, a name join to `profile.overridePresets`. The second is untestable in this
  corpus.
- **Temp targets.** Trio sends `notes` = name; iAPS drops it. Trio ends a TT by re-posting the
  same `created_at` with the actual duration; iAPS writes a zero-duration TT one second before the
  next start. Trio's `halfBasalTarget` is not uploaded.
- **Composition (Swift and JS agree).** The override target applies only when no temp target is
  set; the override percentage and ISF/CR scaling still apply alongside a temp target.
- **Trio also downloads** `Temporary Target` treatments entered by other clients and enables the
  newest one directly, with no acknowledgement record — an entity used as a command.
- **`dosingMode`** {closed, open, lowGlucoseSuspend, basalTesting} is in
  `devicestatus.openaps.dosingMode` (Trio); the change itself is not a treatment. Pump
  suspend/resume are `Note` treatments with `notes: PumpSuspend | PumpResume`.

### 3.3 AndroidAPS

- **ProfileSwitch → EffectiveProfileSwitch is the ecosystem's clearest request/effect pair.** A
  PS is written by a user, SMS, automation, scene or NS sync; the profile is pushed to the pump;
  **only if the pump accepts** is an EPS written. A failed or pending change is visible on the wire
  only as a PS with no following EPS. The EPS is uploaded as `eventType: "Note"`, recognised by
  `originalProfileName`; its `profileJson` is scaled, the PS's is the base profile. **4.0.0 prerelease:**
  `EPS.originalPsId` links the two locally and is not sent.
- **`percentage` scales overall insulin needs.** `ProfileSealed.convertToNonCustomizedProfile`:
  basal × p/100, ISF × 100/p, IC × 100/p; targets only time-shifted (pinned by
  `ProfileSealedTest.kt:136-141`; same maths at the 3.4.2.6 tag). With Dynamic ISF the
  percentage enters the TDD-based ISF formula instead.
- **RunningMode** has a requested layer and a constraint-forced layer (`autoForced: true`,
  `reasons`), both uploaded as `OpenAPS Offline`; open-ended `DISABLED_LOOP` is sent with a
  10-year duration and `originalDuration: 0`. **4.0.0 prerelease:** `RunningModeReconciler` drives the
  pump from the mode record and re-checks drift at startup.
- **Temp targets** have a closed reason vocabulary (`Custom, Hypo, Activity, Eating Soon,
  Automation, Wear`); a new TT ends the running one; inbound merges are shorten-only.
- **Accepting remote intent is opt-in per type.** The pump-owning phone applies NS-originated PS,
  TT and RunningMode records only if `NsClientAcceptProfileSwitch`, `…TempTarget`,
  `…RunningMode` are on; all default off.
- **Client control and scenes (4.0.0 prerelease).** Commands and acknowledgements travel as documents in
  the NS v3 `settings` collection under fixed identifiers; scene and automation definitions are
  published under `aaps`, active-scene state (with the NS identifiers of the records the scene
  created) under `aaps-state`. Scene revert shortens only records the scene still owns.

## 4. Identity and end encoding, side by side

| | Instance key on the wire | "Ended" is | Cancel before start |
|---|---|---|---|
| Loop override | `_id` = UUID (server-dependent) | amended `duration` | DELETE |
| Trio override | `created_at` + `eventType` | delete + re-post, new `_id` | delete |
| iAPS override | `created_at` ± 5 min + `enteredBy` | delete + re-post | delete |
| Trio TT | `created_at` + `eventType` (server upsert) | re-post, same `created_at` | — |
| iAPS TT | — | zero-duration TT at next start − 1 s | zero-duration TT |
| AAPS PS / TT / RunningMode | `identifier` (v3) | shortened `duration`, same `identifier` | v3 soft delete |
| Careportal / nightguard TT | — | zero-duration TT | zero-duration TT |

## 5. How the hubs decide what is active

cgm-remote-monitor recomputes active state on every load; Nocturne materialises
`StateSpan`s on write and supersedes open spans within exclusive categories.

**Status 2026-10-12: every row below is measured on both hubs** by the lab
[`tools/lab/hub-active-state`](../../../tools/lab/hub-active-state/results/RESULTS.md)
(cgm-remote-monitor `fade2299`, Nocturne `42275c812` on SQLite, one synthetic record set, a
control per case where the hubs agree). Against the 2026-10-09 text, whose Nocturne cells were
read-derived: the "Agree?" cells of the cancel rows change, the same-millisecond Nocturne cell is
corrected, the backfill row is new, and the other cells are confirmed. The careportal storage
claim in the override-cancel row is still read-derived. "Agree?" means the two hubs report the same
active state at the lab's query times; for Nocturne, "latest span" is `GetActiveAtAsync(category,
state: null, t)` and "list" is `GetStateSpansAsync` over t, which hides records deduplication
marked non-primary.

| Intent | cgm-remote-monitor | Nocturne | Agree? |
|---|---|---|---|
| Temp target + later cancel | cancel truncates the earlier target (**measured**: 60-min target + cancel at 20 → one 20-min window) | cancel becomes a separate span with state `Cancelled` and no end; the timed target keeps its 60 min (**measured**) | latest span: **yes** (it is the Cancelled one); `Active`-state and list reads: **no** until the target's own end, and the open Cancelled span stays in list reads afterwards |
| `Temporary Override Cancel` | not stored by careportal (APNs request only, read-derived); a stored one has no duration and is ignored (**measured**) | not classified; produces no record (**measured**) | **yes**: in both, the override runs its full duration |
| Loop devicestatus override | latest devicestatus `override`; `timestamp` + `duration` read as **seconds** (**measured**) | one span per devicestatus, starting at devicestatus time, `duration` read as **minutes**; spans are not superseded, and `active: false` closes nothing (**measured**) | **no** (30-min override: active at +40 and +120 in Nocturne only) |
| Timed profile switch after a permanent one | falls back to the permanent profile when the timed one expires (**measured**) | closes the permanent span at the timed start; no span after expiry, so basal resolves against profile `Default` (**measured**) | **no** |
| AAPS `timeshift` | milliseconds (AAPS 3.x wire unit); schedule read at t − shift (**measured**) | hours, modulo 24: a millisecond value becomes 0; an hours value is applied as t + shift (**measured**) | **no** for any non-zero shift |
| Same-millisecond temp targets | keeps the first, drops the second (**measured**) | both stored; deduplication marks the second arrival non-primary, so list reads show the first; `GetActiveAtAsync` sees both (**measured**) | list: **yes**; latest span: **no** once the first-arrived target ends before the second |
| Out-of-order backfill of two open overrides | no truncation of `Temporary Override` treatments in either order (**measured**) | supersession closes only spans starting at or before the new one, so the backfilled earlier span stays open: two open spans (**measured**) | list: **yes** out of order, **no** in time order (Nocturne supersedes); latest span: **no** |

Two hub writes do not reach any controller: Nocturne `POST /api/v4/state-spans` writes
Override, TemporaryTarget or Profile spans directly, and careportal or nightguard temp targets are
honoured only by controllers that download them (Trio; AAPS behind an opt-in).

## 6. The remote-command lifecycle

| Path | Request recorded at hub | Acceptance visible | Success visible | Failure visible |
|---|---|---|---|---|
| Careportal or Nocturne → Loop (hub → APNs) | no | no | as the resulting entity | `Note` with free text |
| LoopFollow → Loop (direct APNs) | no | no | reply to sender only | `Note` |
| LoopFollow → Trio (direct APNs) | no | no | reply to sender only | `Note` |
| LoopCaregiver "Remote Commands 2" (status Pending → InProgress → Success/Error) | **expects** a hub collection; neither hub has one | — | — | — |
| Any client → iAPS (`Announcement` treatment) | the request is the treatment | no | no | no |
| Careportal / nightguard TT → Trio, AAPS | the request is the treatment | no | indistinguishable from enacted | no |
| AAPSClient → AAPS (**4.0.0 prerelease**, NS `settings`) | yes, signed | `Executing` ack | `Done/Ok` ack | `Done/Failed`, `Expired`, `Delivery/Failed` |

Neither hub forwards a reply channel in the APNs payload it builds, so hub-routed commands cannot
receive a reply; that channel exists only on direct APNs. The RFC's `DeliveryRequest.requestType`
covers tempBasal, bolus, suspend and resume; the commands caregivers actually send — override,
temp target, carbs, loop mode — have no request object, and `OverrideInstance.status` has no
`requested` or `rejected` state.

## 7. Composition: who combines overlapping intents

| Controller | Rule |
|---|---|
| Loop | target = pre-meal if active, else override, else schedule; basal ×f, ISF ×1/f, CR ×1/f from the override only, applied over the history window |
| Trio, iAPS | target = temp target if set, else override target (unless 0 or 6), else profile; override percentage and ISF/CR scope apply regardless; a high or low TT separately sets `sensitivityRatio` via `halfBasalTarget` (the multiplication order with the override factor is not traced) |
| AAPS | TT replaces min/max/target; PS percentage has already scaled basal, ISF, IC in the EPS; one PS, one TT, one RunningMode, one Scene at a time |
| cgm-remote-monitor | no composition; draws bands per kind |
| Nocturne | no composition; exclusive within Override, TemporaryTarget, Profile; Exercise/Illness/Travel may overlap |

No two controllers share a rule, and the rules depend on algorithm settings (Dynamic ISF, AutoISF,
`halfBasalTarget`). Under the stated roles the hub records the controller's result rather than
computing it. The RFC's companion `conflict-resolution.md` composes overlapping overrides inside
the hub; that section is inconsistent with the roles and would need revising.

## 8. Cowpaths: what controllers already publish as definitions

| Controller | Where | What | Missing |
|---|---|---|---|
| Loop | `profile.loopSettings` | `overridePresets` (symbol, name, duration, target, scale factor), `preMealTargetRange`, `dosingEnabled`, `dosingStrategy`, APNs coordinates | preset id; workout target; GBAF, IRC |
| Trio | `profile` | `overridePresets` (name, duration, percentage, target), APNs coordinates | ISF/CR scope, SMB settings, id |
| iAPS | a non-Nightscout service | presets | everything, as far as the hub is concerned |
| AAPS (**4.0.0 prerelease**) | NS `settings`, identifiers `aaps` and `aaps-state` | scene, automation, QuickWizard and insulin definitions; active scene with component record identifiers | a schema other software can read |

Nightscout's careportal already builds its remote-override picker from
`profile.loopSettings.overridePresets`. Each row is a registration in practice: a controller
publishing its definitions to the hub, in a controller-private shape, overwritten as a snapshot.

## 9. What a registration has to be able to declare

Derived from §3–§8. Each element is something at least one controller does today.

1. **Definitions** with stable ids and typed fields, per intent kind (override preset, TT preset,
   scene, mode), including controller-unique fields (Trio SMB schedule, iAPS end conditions, AAPS
   scene actions).
2. **Intent slots**: which kinds exist, which are exclusive within themselves, which coexist.
3. **States and end reasons**: scheduled, active, ended {expired, cancelled, superseded, deleted
   before start, ended by trigger}, with the trigger vocabulary (carbs, glucose above/below, loop
   off, chain).
4. **The wire carrier**: how today's documents map onto the declared kinds — `eventType`, the
   discriminating fields, indefinite sentinels, units, and how "ended" is encoded (§4).
5. **Requested vs applied**: where the controller reports the applied effect (AAPS EPS, Loop and
   Trio devicestatus) and how it links back to the request.
6. **Composition result**, as reported by the controller (§7), not a hub-side rule.
7. **Initiator vocabulary**: the controller's own (Loop `EnactTrigger`, Trio `AdjustmentSource`,
   AAPS `Sources`).
8. **Command contract**: vocabulary, authorisation, expiry, acknowledgement states and
   correlation id; whether the hub is in the path.
9. **Acceptance policy**: which intent the controller accepts from the hub (AAPS opt-in per type,
   Trio TT download, iAPS announcements).

## 10. What this means for the existing design series

| Document | Consistent | Needs revising |
|---|---|---|
| [Controller descriptions](PROPOSAL-controller-descriptions-2026-09-11.md) | kind/instance split, `decomposesTo` (D11), `.well-known` catalogue | §4 ("static, not CRD-style, no new endpoints") is superseded in part by D18; it describes the well-known tier |
| [Hub-and-spoke sync](nightscout-hub-sync-architecture-2026-09-11.md) | registration-derived contract, cursor + batch | `stateSpans` in the schema has no slots, end reasons, initiators or command contract. *2026-10-12: the schema now has them (see the next row); the document is corrected in place* |
| [Effects and versioning](nightscout-effects-and-versioning-2026-09-11.md) | effect vs motivation; `TherapyEffect` as a span | AAPS percentage is an insulin-needs scale; Trio "481" is 399 distinct; Trio `notes` is a preset name |
| `specs/sync/registrations/{loop,trio,androidaps}.yaml` | structural discriminators. **Since 2026-10-12** (`make schema-sync-model`, schema extended additively): every intent kind declares its slot and which slots coexist, states, the wire carrier (§4), requested vs applied, initiators, definitions and acceptance policy, each with `read`/`measured` evidence; `composition` is declared as reported by the controller and `commands` per §6. Added: Loop pre-meal (declared with `wire: null`, not published), Loop `dosingEnabled`, Trio `dosingMode` (§3.2; the `dosingMode` in this row's original text is Trio's), AAPS RunningMode, the AAPS PS → EPS pair, AAPS Scene (4.0.0 prerelease). AAPS `Override` removed. **Also 2026-10-12** (`SCHEMA-REG-EXT`, D18 addendum rules 1–5): the grammar is must-ignore with typed, reverse-DNS-namespaced `extensions`, typed field declarations, `other` + `controllerTerm` for the open lists, per-kind `versions` and declared horizons; the three registrations gained `typeRef` to ControllerSettings definitions read from their own algorithm family, a `cycle` horizon on the `devicestatus` document and an `effective-dated` horizon on `settings`; a synthetic fixture (`registrations/fixtures/`) uses every rule | still undeclared, because this document does not establish them: iAPS (no registration exists); end-reason vocabularies for Trio override and temp target and for AAPS profile switch; AAPS `Sources` values; command vocabularies; where AAPS reports the composed target; a `scheduled` state for any kind except Loop's override. The declarations are read-derived except the counts §3 marks **measured**. Not typed, rather than guessed: per-cycle state, and `suspendThreshold`, whose ControllerSettings definition is labelled oref0 but was read from Loop's source; no generated field carries a sensitivity label, so each falls to `unlabelledPolicy: withhold` |
| Upstream RFC | Definition/Instance, DeliveryRequest/Observation/Reconciliation, kind vs instance | request types for override/TT/carbs/mode; `requested`/`rejected` states; hub-side composition in `conflict-resolution.md`; `bridge-rules.md` reads `devicestatus.loop.override` and AAPS `devicestatus.configuration`, neither of which is on the wire |
| Nocturne `StateSpan` | right container for observed state; supersession; overlap for activity categories | no request/applied distinction, no end reason, metadata untyped; the §5 unit and cancel differences |

## 11. Corrections applied to other documents

| Document | Claim | Source says |
|---|---|---|
| `nightscout-effects-and-versioning-2026-09-11.md` §2.2, `specs/sync/effect-remapping.yaml` `MAP-AAPS-PROFILESWITCH` | AAPS `percentage` is a basal-only scale | basal × p/100, ISF and IC × 100/p |
| same, `MAP-TRIO-EXERCISE` | 481 Trio documents; `notes` is the user's note; `classification: exercise` | 399 distinct; `notes` is the preset name; `Exercise` carries every override |
| `docs/10-domain/override-temp-target-sync-comparison.md:13,215` | Loop override eventType `Override` | `Temporary Override` (corpus agrees) |
| same `:278`; `override-profile-switch-comparison.md:342` | Loop dedup key `syncIdentifier` | `_id` = UUID, server-dependent |
| `override-profile-switch-comparison.md:24` | Loop has no separate target | pre-meal is a concurrent target slot |
| `override-profile-switch-comparison.md:344,367-374,386` | Trio identity is `id`; Trio does not track end | `created_at` + `eventType`; end is a delete + re-post |
| `override-temp-target-sync-comparison.md:16` | AAPS TT changes the target only | true for OpenAPS SMB; AutoISF can raise sensitivity on a high TT |
| `remote-bolus-comparison.md:14,309` | Loop sets a 5-min expiry; only Trio sends structured responses | the sender sets expiry; Loop also sends responses |
| `remote-commands-comparison.md:604-608` | no system signs commands | AAPS dev signs envelopes and acks (not in 3.4.2.6) |
| `nocturne-override-temptarget-analysis.md` | categories include `TempBasal`; no supersession; CRM has no supersession | source categories per §5; `SupersededById` exists; CRM truncates TTs and profile switches |
| `nocturne-profileswitch-analysis.md:238-262` | CRM does not apply percentage/timeshift | dev applies both; AAPS 3.x timeshift is milliseconds |
| docs citing Trio's oref JS as the running engine | — | Trio runs a Swift port |

The effects figures in the first two rows are also restated as distinct documents: `make
schema-effects` counted a document once per snapshot, and the corpus's two snapshots overlap. It
now counts by (site, collection, `_id`): 2,865 temporary-effect treatments (3,415 read), 55,938
active devicestatus overrides (64,674 read).

Two items are queued as labs in the `platform` parcel: `LAB-TRIO-INTENT` (Trio behaviour that
depends on app lifecycle and upload bookkeeping) and `LAB-HUB-ACTIVE-STATE` (§5, run on both hubs).

## 12. Not measured

* Anything about AAPS from data; no AAPS closed-loop site in the corpus.
* The Trio `profile.overridePresets` name join; no Trio profile document in the corpus.
* Order of multiplication between a Trio override factor and a TT `sensitivityRatio`.
* Either hub's HTTP write path (upsert, dedup on insert), Nocturne on PostgreSQL (the
  same-millisecond tie is broken by insertion order on SQLite), and the cgm-remote-monitor client
  renderer; the §5 lab ran the storage and active-state code directly.
* Whether shipping AAPS sites enable the `NsClientAccept*` preferences.
* xDrip+ remote and follower paths; the NightscoutKit fork LoopCaregiver uses.
* Behaviour that depends on app lifecycle (foreground vs background) in any controller; nothing
  here was run on a device or simulator.
