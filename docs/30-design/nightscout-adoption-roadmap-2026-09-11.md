# Adoption roadmap: who builds what, in what order

Date: 2026-09-11. Status: draft for maintainer discussion. Sixth in a series;
sequencing companion to
[the hub-and-spoke sync design](./nightscout-hub-sync-architecture-2026-09-11.md)
and [effects and versioning](./nightscout-effects-and-versioning-2026-09-11.md).

Based on the state of each project's **development branch on 2026-09-11**.
The workspace pins have since been advanced (`workspace.lock.json`) and every
measured claim in this series re-run against them: Nocturne coverage,
treatment decomposition, vendor surfaces, dosing inputs and sync cost are
unchanged, and both reported upstream defects are still present.

One distinction runs through this document and is easy to lose: **AAPS tracks
`master` in the lockfile, and almost all the work described here is on
`dev`.** Where a claim depends on which branch, it says so.

**Nothing here is a proposal to merge.** Every phase that names a project is
a proposal *to* that project, offered to help converge work already in
progress — see [§5](#5-what-this-is-actually-for).

**Revised 2026-09-11** after maintainer review, on two counts: the claim that
cgm-remote-monitor does not do protocol work was wrong (§1, §6), and the
existing `ENABLE` / extended-settings configuration channel was missing
(§2.2), which adds a soft-adoption posture to Phase 3.

---

## TL;DR

**The premise of the question — "Nightscout would have to build everything
first" — is less true than it looks, in two specific and useful ways: the
data channel exists, and so does the configuration channel.**

`settings` is already an enabled v3 collection in cgm-remote-monitor
(`lib/api3/index.js`: `enabledCollections` = devicestatus, entries, food,
profile, **settings**, treatments). And AndroidAPS's **development**
branch carries a complete v3 settings client — create, read, patch, upsert,
delete, `history/{from}`, search — typed as a bare `JsonObject` and not yet
wired to any sync worker.

That second half needs stating carefully, because it is easy to over-read.
The settings client is **not released**: AAPS `master` (tip 2026-08-02) has
**zero** settings endpoints; `dev` has seven, and they landed on 2026-08-06
in a commit titled *":core:nssdk ktor migration"*. They arrived as part of
porting the whole v3 surface to ktor, which makes *incidental completeness*
at least as likely an explanation as an intent to publish controller
settings. What it establishes is that the **client-side cost is already
paid** — not that anyone has decided to spend it.

So the single highest-value item in this series — publishing controller
settings, the thing physicians cannot see and `oref-digital-twin` reads from
screenshots — **needs no new API on either side.** It needs a schema and a
convention for what goes in a collection that already exists.

The second mechanism is `ENABLE` and its `<PLUGIN>_<SETTING>` extended
settings (§2.2). Every Nightscout site is already configured by declaring
what it expects to run; that same declaration can select which registration
the hub applies, which makes soft adoption available to sites whose
controller has not changed and may never change.

| Finding | Consequence for sequencing |
|---|---|
| `settings` v3 collection exists; AAPS `dev` has the client (unreleased) | Phase 1 is a schema, not an API. Weeks, not quarters |
| Loop: 24 commits in 6 months, none touching Nightscout — but LoopWorkspace took on `OmnipodKit` and `MedtrumKit`, and Loop wired the pump BLE heartbeat to CGM scheduling | Loop's capacity is committed to device connectivity, not sync. Anything requiring a Loop *protocol* change is the long pole. Design so Loop needs none |
| AAPS: 2,434 commits, Nightscout SDK moved to `commonMain` with an iOS target | Their sync layer is malleable *right now* — the best window to agree a convention, the worst to demand stability |
| Trio: 1,365 commits, fixes and a11y; `NightscoutExercise` unchanged | Willing and active, but override effects still unpublished |
| cgm-remote-monitor `dev`: 513 commits, 12 on `lib/api3`, a `UUID_HANDLING` feature flag, and an in-tree `docs/proposals/` set including a control-plane RFC and an *Integration Questionnaire for Loop/AAPS/Trio Implementers* | The hub leads too. Hub-side phases are proposals to a project already asking these questions, not blockers to route around |
| `ENABLE` plus `<PLUGIN>_<SETTING>` extended settings is an existing operator-facing configuration channel | Catalogue selection needs no new mechanism. An operator can declare "expect Loop" before any controller changes anything |
| xDrip+ ships a Nocturne uploader | Two hub implementations already in the field |

**On baked-in registrations: yes, and for a sharper reason than convenience.**
Loop has no protocol work scheduled, so nothing should *require* Loop to
register. The hub needs two ways to know what it is talking to without
asking: the structural discriminator this series measured, and the
operator's own declaration. The second already exists — `ENABLE=loop`
already tells a Nightscout site which controller family to expect, and
`<PLUGIN>_<SETTING>` env vars already carry per-controller configuration
into the plugin that consumes them (§2.2). A shipped registry plus an
operator flag turns "controllers must adopt this" into "controllers may
correct this", which is the version Loop, and every site running an
unmodified build, can participate in on day one.

---

## 1. Where each project actually is

Commits on the current dev branch in the six months to 2026-09-11.

| Project | Branch | Commits | What it is doing |
|---|---|---|---|
| Nocturne | `main` | 2,546 | Active hub development |
| AndroidAPS | `dev` | 2,434 | **Kotlin Multiplatform**: iOS and desktop targets, Dagger/Hilt removed, NS client and `nssdk` moved to `commonMain`, settings export made platform-neutral. `dev` is **2,597 commits ahead of `master`**, and the migration is nearly all on `dev`: 1,869 `commonMain` files there against 36 on `master` |
| Trio | `dev` | 1,365 | Fixes, accessibility, tests; oref runnable from CLI; fractional-date fix landed (#1476) |
| xDrip+ | `master` | 538 | Preference-manager modernisation; **Nocturne uploader and auth** |
| cgm-remote-monitor | `dev` | 513 | Bug fixes and dependency bumps; profile-switch and unnamed-profile fixes; **12 commits on `lib/api3`** (v3 filter-parameter handling, write normalisation and purification, search-callback semantics) and a `UUID_HANDLING` feature flag (2026-03-17) gating a protocol behaviour change. `docs/proposals/` — control-plane RFC, multi-writer conflict resolution, bridge rules, integration questionnaire — landed 2026-01-01, ten weeks before this window opens |
| xDrip4iOS | `develop` | 384 | Nightscout follower gap-fill, upload performance, settings UI |
| LoopWorkspace | `main` | 49 | Build and translations; **`OmniBLE`/`OmniKit` replaced by `OmnipodKit`, `MedtrumKit` added** |
| Loop | `dev` | **24** | Xcode 27, Liquid Glass UI, translations; **OmnipodKit support** and the pump BLE heartbeat wired to CGM scheduling. **No Nightscout, sync or settings work** |
| LoopKit | `dev` | 12 | Translations, one BLE API |
| LoopAlgorithm | `main` | 12 | Quiet |

Three things follow directly.

**Loop's capacity is committed to device connectivity, not to sync.**
Twenty-four commits in six months, none touching data or sync — but the
count understates what is happening around it, and "maintenance mode" reads
it wrong. In the same window LoopWorkspace replaced the `OmniBLE` and
`OmniKit` submodules with `OmnipodKit` and added `MedtrumKit`, and Loop
itself landed *Support use of OmnipodKit* (#2426) and wired the pump BLE
heartbeat to the CGM reading schedule.

That is the ecosystem-wide pattern, not a Loop quirk. AAPS moved eleven pump
drivers to Metro ownership and worked Equil, Eopatch and Dana; Trio updated
DanaKit, reworked the pump and CGM screens and retired Enlite; xDrip+
migrated Dexcom Share from Retrofit 1 to Retrofit 2 and added LibreWifi
coverage; xDrip4iOS added G6 Anubis Slot 3, Bluetooth channel selection and
sensor-session recovery. **Widening pump and CGM connectivity is where the
last six months of ecosystem effort actually went.**

So the constraint to design around is not that Loop cannot move. It is that
its attention — and everyone else's — is spent on hardware coverage, and
**a plan whose first step is "a controller changes its Nightscout protocol"
is asking for the one thing nobody is currently spending on.** Loop is also
9 of 11 sites in the corpus, so it cannot be routed around either.

**AAPS is mid-rewrite and it is the good kind.** The Nightscout SDK is now
`commonMain` Kotlin Multiplatform with an iOS target; the NS client workers
are shared runners; settings export was deliberately moved off Android "so
every platform reads the same files". A project doing that is thinking about
portable representations, which is exactly the conversation to have — and it
is also a project whose sync internals are in motion, so asking for a *new*
obligation now competes with a migration. Ask for a *convention* they can
satisfy from where they are heading anyway.

**There are two hubs, and the older one is not standing still.** An earlier
draft of this document said the hub would not lead. That was wrong, and it
was wrong for a reason worth naming, because it is a failure mode of this
whole method: a six-month window opening 2026-03-11 misses
`docs/proposals/`, which landed in cgm-remote-monitor `dev` on 2026-01-01
and contains an agentic control-plane RFC, multi-writer conflict-resolution
rules, bridge rules, API query normalisation, an OIDC actor-identity
proposal — and an *Integration Questionnaire for Loop/AAPS/Trio
Implementers* whose stated purpose is to "determine how well existing AID
controllers can support the proposed event-driven control plane
architecture". That is this document's own question, asked by the hub eight
months earlier. Inside the window there are 12 `lib/api3` commits and a
`UUID_HANDLING` flag gating a protocol behaviour change, alongside the
`API3_SECURITY_ENABLE` / `API3_DEDUP_FALLBACK_ENABLED` /
`API3_CREATED_AT_FALLBACK_ENABLED` toggles already in `lib/api3/index.js`.

Meanwhile Nocturne's 2,546 commits build a second hub that xDrip+ already
uploads to. The consequence is the opposite of the earlier draft's: hub work
is not a blocker to route around, it is **where two hubs' efforts have to
converge**, and a proposal arriving there has a standing invitation rather
than an uphill argument. What still holds is narrower and worth keeping:
**no phase should require both hubs to ship before anyone gets value.**

## 2. Two mechanisms that already exist

### 2.1 The settings collection

The earlier sequencing put "publish settings" first because it was additive.
It is better than additive: **the channel already exists on both sides.**

* `cgm-remote-monitor/lib/api3/index.js` sets
  `enabledCollections = ['devicestatus','entries','food','profile','settings','treatments']`.
  The v3 generic layer gives `settings` the same CRUD, `history/{from}`
  delta, soft delete and dedup as every other collection.
* `AndroidAPS/core/nssdk/.../NightscoutApi.kt` **on `dev`** implements
  `getSetting`, `getSettingsModifiedSince`, `searchSettings`,
  `createSetting`, `patchSetting`, `updateSetting` (documented as upsert) and
  `deleteSetting` with a soft/hard distinction. Not on `master`, and five
  weeks old.

What is missing is **not transport**. The payload is `JsonObject` — no
schema, no declared shape, and no plugin wiring that writes one. That is
precisely the gap this series has been measuring from the other end, and it
means the first real step is a *document* everyone agrees on, which is the
kind of artifact this repository already generates.

### 2.2 `ENABLE` and extended settings: soft adoption without a controller change

The second mechanism is older, universally deployed, and was missing from the
earlier draft entirely. Nightscout sites are already configured by telling
the server what to expect:

* `lib/server/env.js:45` reads `ENABLE` into `env.enable`; `lib/settings.js`
  parses it into `settings.enable` and exposes `isEnabled(feature)`.
* `findExtendedSettings` (`lib/server/env.js:289`) then collects, **only for
  the plugins named in `ENABLE`**, every env var of the form
  `<PLUGIN>_<SETTING>`, camel-cases it, coerces numbers and `on`/`off`, and
  hands it to that plugin as `sbx.extendedSettings`.
* Which is how `ENABLE=loop` plus `LOOP_WARN` / `LOOP_URGENT` /
  `LOOP_ENABLE_ALERTS` configures `lib/plugins/loop.js`, `ENABLE=openaps`
  configures `lib/plugins/openaps.js`, and `PUMP_FIELDS` /
  `PUMP_WARN_ON_SUSPEND` configure `lib/plugins/pump.js`.

**An operator saying "this site runs Loop" is therefore not a new concept to
introduce — it is the concept the site is already configured with.** The
existing flags select which *renderer* runs; the same declaration can select
which *registration* from the shipped catalogue the hub applies. That makes
soft adoption available to every site immediately, including sites whose
controller will never upload a registration, and it composes with the
controller-uploaded path rather than competing with it: the operator's
declaration is a default, and a controller that uploads its own overrides it.

It is also the right escape hatch for the risk named in Phase 3. A wrong
shipped registration stops being a trap when the operator can name the
correct one, and a site running a fork or a dev build can point at the
registration that actually matches without waiting for anyone.

## 3. Single-tenant versus multitenant

They are far less entangled than the multitenancy discussion implied, and
the §6.1.2 correction widened the gap further.

| Capability | Single-tenant | Multitenant adds |
|---|---|---|
| Settings schema and publication | full value | nothing |
| Effect/motivation separation | full value | nothing |
| Sensitivity labels and projections | full value | nothing |
| Controller registration and sync contract | full value | per-tenant registration storage |
| Decomposition into primitives | full value | nothing |
| Replay completeness reporting | full value | nothing |
| Bounded query profiles | correctness | **also** the noisy-neighbour defence |
| Storage-enforced isolation | not needed | the actual multitenant problem |
| Connection multiplexing | not needed | the operational constraint |

**Everything a controller author or a clinician would notice is
single-tenant work.** Multitenancy needs isolation, query bounds and
connection multiplexing, and nothing in the schema, sync or privacy design
depends on which of those is chosen. That is worth stating plainly because
it removes multitenancy from the critical path: a self-hosted single-tenant
operator gets the whole benefit of phases 1–5 below without any tenancy
decision being made.

## 4. The roadmap

Ordered so that no phase depends on a project that cannot move, and each
phase is useful if the next never happens.

### Phase 1 — a settings document schema. Hub: none. Controllers: optional

Define what goes in the existing `settings` collection: an effective-dated,
build-versioned `ControllerSettings` document, with the fields the
[fidelity report](./nightscout-devicestatus-profile-fidelity-2026-09-10.md)
measured as absent — Loop's eight behaviour switches, `maxIob` and `maxBasal`
for the oref0 family.

* **cgm-remote-monitor**: nothing required. The collection is enabled today
  (`lib/api3/index.js`, unconditional — not behind `ENABLE`). The natural
  hub-side follow-on is a rendering of published settings, which is exactly
  the kind of work `docs/proposals/` is already scoping.
* **AndroidAPS**: wire the client they already have to a sync worker. The
  portable settings-export work is the natural place.
* **Trio, Loop**: no change required to *benefit* — a replay tool reads
  whatever is published, and a clinician view shows what exists.

This closes the physician complaint and the `oref-digital-twin` screenshot
workaround for whichever controller publishes first, without waiting for the
others. **It is the only phase that is both highest-value and
lowest-friction, which is why it is first.**

### Phase 2 — two upstream one-liners. No coordination needed

`Pump Suspend` / `Suspend Pump` in Nocturne's V4 event map, and
`bolus`/`tempBasal` versus NightscoutKit's `bolusVolume`/`tempBasalAdjustment`
in `LoopAutomaticDoseRecommendation`. Both silently discard real dosing
records today; both are single-symbol fixes in one project each.

### Phase 3 — the shipped registration catalogue. Hub only

The hub ships registrations for known controllers, generated from measured
evidence (`specs/sync/registrations/`), **serves them at a well-known path**
so any reader can fetch the same description
([proposal](./PROPOSAL-controller-descriptions-2026-09-11.md) §2.1), and
resolves which one applies from three sources in precedence order: a controller-uploaded registration, then
the operator's declared expectation (§2.2), then a **structural
discriminator** — a devicestatus carrying `loop` versus `openaps`. Never by
the device string.

That gives four postures, and the first two require nothing of the
controller:

1. **Recognised.** The hub applies the shipped registration from the
   structural discriminator. Loop lands here and needs no change, ever.
2. **Declared.** The operator names it — `ENABLE=loop`, or an explicit
   `<PLUGIN>_REGISTRATION` pin — and the hub uses the catalogue entry for
   what the site says it runs. This is the soft-adoption path: it works for
   forks, dev builds, and any controller whose maintainers have not been
   asked yet, and it reuses configuration operators already write.
3. **Confirmed.** A controller posts the registration it was going to be
   given anyway, pinning a version. One request, no behaviour change.
4. **Corrected.** A controller posts its own, overriding both of the above —
   the path for a new feature, a new controller, or a build that diverges.

**The risk this creates, named.** A wrong shipped registration is worse than
none: it would make the hub confidently misdescribe a controller. Four
mitigations, all of which this repository or the hub already supports —
derive them from measurement rather than assertion, version them so a
correction is a bump rather than a silent change, let the operator override
a wrong guess without a code change (posture 2), and make "not me"
expressible so a controller can always disown one.

### Phase 4 — the sync contract, read-only. Hub, then whoever wants it

Cursor envelope derived from the registration. Measured saving at 2.5–10×
request count. Read-only first, so an early adopter cannot corrupt anything.

**Loop and Trio are on v1 with no watermark and no delta endpoint**, so they
are the ones with most to gain — and also the ones least able to spend
effort. Which is the argument for the hub offering it and nobody being
obliged to take it.

### Phase 5 — effects, then batch write, then decomposition

`TherapyEffect` (the highest-value controller change is Trio's, whose
`NightscoutExercise` on today's `dev` still carries no effect at all), then
batched idempotent writes, then decomposition behind the contract.

### What is deliberately not on the roadmap

* **A v5.** Two of three controllers have not adopted v3. See
  [versioning](./nightscout-effects-and-versioning-2026-09-11.md) §5.
* **Tenant-registered CRDs**, on current evidence. Note the scope: this
  excludes *tenant*-scoped schema registration, not the per-controller-product
  descriptions Phase 3 ships — see
  [extensibility models](./nightscout-extensibility-models-2026-09-10.md) §3.4.
* **A liveness or channel-ownership model.** cgm-remote-monitor's
  `docs/proposals/` already drafts one (`ControllerInstanceRegistration`,
  `CapabilitySnapshot`), this series has measured nothing about it, and
  writing a competing design before reading theirs is the duplication this
  work exists to prevent. See
  [hub-and-spoke sync](./nightscout-hub-sync-architecture-2026-09-11.md) §5.2.
* **Anything requiring a Loop change**, until something else has proved the
  value and Loop has capacity.

## 5. What this is actually for

The three technical motivations — unify typed representations, provide
extensibility, offer full replay and observability — are stated with their
evidence in
[the controller-descriptions proposal](./PROPOSAL-controller-descriptions-2026-09-11.md)
§0. This section is about the *process* goal that sits above them.

**The purpose of the discovery and evidentiary work in this repository is to
produce proposals that help unify efforts already underway.** That is worth
stating at the top of this section because it changes how every phase below
should be read. None of these phases is an attempt to get projects to adopt
something new from outside. Each is an attempt to describe, in one place and
from measured evidence, a thing several projects are already building
separately — so that the next increment each of them was going to ship
anyway lands in a shape the others can consume.

The evidence for that framing is in §1: two hubs are independently building
hub-side capability, cgm-remote-monitor has an in-tree RFC and an
integration questionnaire addressed to exactly the three controllers this
series measures, AAPS is making its Nightscout SDK platform-neutral, and
five projects spent six months widening pump and CGM coverage. The work is
not absent, it is **parallel and uncoordinated**, and the gaps this series
found — undeclared settings, effects without motivation, a discarded
`Pump Suspend`, `bolusVolume` versus `bolus` — are the predictable cost of
that. A proposal's job here is to be the artifact that lets separate efforts
converge without anyone having to stop.

This is also why the measurement discipline matters more than usual: a
proposal that unifies has to describe what projects actually do, not what a
reader assumes they do. §1 records one place where this document got that
wrong and why.

The question framed these features as mainly assisting controller authors,
and that is right, with two additions worth making explicit.

**For an existing controller author** the benefit is that a new feature stops
requiring ecosystem negotiation. Today, adding a temporary-effect type means
inventing an `eventType`, hoping readers tolerate it, and discovering months
later that a typed consumer dropped it. With a registration and a declared
effect vector, a new feature is a registration bump — and the
[quirks registry](../../specs/quirks/) exists precisely because the current
answer was "everyone improvises and the divergence is found by census".

**For a new controller** the benefit is that there is something to conform
to. `specs/conformance/observability-profile.yaml` states what has to be
uploaded to be observable at all; the registrations show what three existing
controllers declare.

**For a site operator** — the constituency the earlier draft left out —
the benefit is that soft adoption does not require waiting for anyone. A
declared expectation (§2.2) plus a shipped catalogue means a site gets
correct interpretation of its own controller's data on the day the hub
ships, whether or not that controller ever changes. Most people running
Nightscout are not in a position to change either end; this is the posture
that includes them.

**And for the person with diabetes and their clinician** — the part not to
lose — it is that the settings that determine dosing become visible, and that
sensitive context can be shared as its dosing effect without its motivation.
Those are the two complaints this series started from.

## 6. What is not measured

* **Commit counts are not effort or direction, and a fixed window is not
  history.** Loop's 24 commits include Xcode 27 support, which is more work
  than the number suggests, and AAPS's 2,434 include a multiplatform
  migration that touches everything. Worse, a six-month window opening
  2026-03-11 excluded cgm-remote-monitor's `docs/proposals/` set entirely —
  the single most relevant prior art in this series — because it landed
  2026-01-01. Both errors ran the same direction: **counting recent commits
  systematically understates design work, which is bursty, and understates
  connectivity work, which is spread across submodules and sibling repos.**
* **No maintainer has been asked.** Everything here is inferred from public
  branches. Willingness, capacity and appetite are not observable from git,
  and every phase that names a project is a proposal to that project, not a
  plan for it.
* **Whether AAPS's `settings` client is intended for controller settings at
  all.** It is unwired, unreleased, and arrived inside a ktor migration
  commit, which makes incidental completeness at least as likely as intent.
  Asking is a one-line question to that project and would settle the most
  load-bearing assumption in this document.
* **Whether cgm-remote-monitor's `settings` collection has ever been used.**
  Enabled is not the same as exercised, and the corpus cannot say — it was
  collected through `/api/v1/`.
* **Nocturne's appetite for a shipped registration catalogue**, which would
  land mostly on the hub side.
* **How much of `docs/proposals/` is live.** The documents are in `dev` and
  dated January 2026, and several phases here overlap them directly —
  registration versus the control-plane RFC, the sync contract versus bridge
  rules, decomposition versus multi-writer conflict resolution. Whether they
  are active, parked, or superseded is not observable from the tree, and
  reconciling this series against them is the obvious next step — arguably
  ahead of Phase 1, since duplicating an existing RFC is the specific
  failure this work is supposed to prevent.
* **Whether the pump/CGM connectivity push has a shared bottleneck** that a
  data-layer proposal could relieve. Five projects widening device coverage
  in parallel is the ecosystem's revealed priority; nothing here tests
  whether any of it would go faster with the artifacts proposed above.

## 7. References

* Branch states fetched 2026-09-11: Trio `origin/dev`, AndroidAPS `origin/dev`, Loop `origin/dev`, LoopKit `origin/dev`, xdripswift `origin/develop`, xDrip `origin/master`, cgm-remote-monitor `origin/dev`, nocturne `origin/main`
* `cgm-remote-monitor/lib/api3/index.js` — `enabledCollections`, and the
  `API3_SECURITY_ENABLE` / `API3_DEDUP_FALLBACK_ENABLED` /
  `API3_CREATED_AT_FALLBACK_ENABLED` env toggles
* `cgm-remote-monitor/lib/server/env.js` — `ENABLE` (`:45`), `UUID_HANDLING`
  (`:101`), `findExtendedSettings` (`:289`)
* `cgm-remote-monitor/lib/settings.js` — `isEnabled` (`:345`)
* `cgm-remote-monitor/lib/plugins/{loop,openaps,pump}.js` — `extendedSettings`
  consumers
* `cgm-remote-monitor/docs/proposals/` — `agent-control-plane-rfc.md`,
  `conflict-resolution.md`, `bridge-rules.md`,
  `integration-questionnaire.md`, `api-query-normalization.md`,
  `oidc-actor-identity-proposal.md` (all added 2026-01-01, `12c90cfc`)
* `AndroidAPS/core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/networking/NightscoutApi.kt` — the settings client
* `Trio/Trio/Sources/Models/NightscoutExercise.swift` — still no effect on `dev`
* `specs/sync/registrations/`, `specs/sync/controller-state-model.schema.json`
* `specs/conformance/observability-profile.yaml`, `specs/quirks/`
