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

**Nothing here is a proposal to merge.**

---

## TL;DR

**The premise of the question — "Nightscout would have to build everything
first" — is less true than it looks, in one specific and useful way.**

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

| Finding | Consequence for sequencing |
|---|---|
| `settings` v3 collection exists; AAPS `dev` has the client (unreleased) | Phase 1 is a schema, not an API. Weeks, not quarters |
| Loop: 24 commits in 6 months, none touching Nightscout | Anything requiring a Loop change is the long pole. Design so Loop needs none |
| AAPS: 2,434 commits, Nightscout SDK moved to `commonMain` with an iOS target | Their sync layer is malleable *right now* — the best window to agree a convention, the worst to demand stability |
| Trio: 1,365 commits, fixes and a11y; `NightscoutExercise` unchanged | Willing and active, but override effects still unpublished |
| cgm-remote-monitor: 513 commits, no v3/v4 protocol work | The hub will not lead. Everything must degrade gracefully without it |
| xDrip+ ships a Nocturne uploader | Two hub implementations already in the field |

**On baked-in registrations: yes, and for a sharper reason than convenience.**
Loop cannot be asked to register — it has no capacity for protocol work —
so the hub must be able to recognise it from document shape alone. We
already have that discriminator, measured and structural rather than
device-string-based. A shipped registry turns "controllers must adopt this"
into "controllers may correct this", which is the only version Loop can
participate in.

---

## 1. Where each project actually is

Commits on the current dev branch in the six months to 2026-09-11.

| Project | Branch | Commits | What it is doing |
|---|---|---|---|
| Nocturne | `main` | 2,546 | Active hub development |
| AndroidAPS | `dev` | 2,434 | **Kotlin Multiplatform**: iOS and desktop targets, Dagger/Hilt removed, NS client and `nssdk` moved to `commonMain`, settings export made platform-neutral. `dev` is **2,597 commits ahead of `master`**, and the migration is nearly all on `dev`: 1,869 `commonMain` files there against 36 on `master` |
| Trio | `dev` | 1,365 | Fixes, accessibility, tests; oref runnable from CLI; fractional-date fix landed (#1476) |
| xDrip+ | `master` | 538 | Preference-manager modernisation; **Nocturne uploader and auth** |
| cgm-remote-monitor | `dev` | 513 | Bug fixes and dependency bumps; profile-switch and unnamed-profile fixes; **no protocol work** |
| xDrip4iOS | `develop` | 384 | Nightscout follower gap-fill, upload performance, settings UI |
| LoopWorkspace | `main` | 49 | Build and translations |
| Loop | `dev` | **24** | Xcode 27, Liquid Glass UI, translations, BLE heartbeat. **No Nightscout, sync or settings work** |
| LoopKit | `dev` | 12 | Translations, one BLE API |
| LoopAlgorithm | `main` | 12 | Quiet |

Three things follow directly.

**Loop is in platform-maintenance mode.** Twenty-four commits in six months,
none touching data or sync. This is not criticism — Xcode 27 and Liquid
Glass are real obligations — but it means **any plan whose first step is "Loop
changes something" does not have a first step.** Loop is also 9 of 11 sites
in the corpus, so it cannot be routed around either.

**AAPS is mid-rewrite and it is the good kind.** The Nightscout SDK is now
`commonMain` Kotlin Multiplatform with an iOS target; the NS client workers
are shared runners; settings export was deliberately moved off Android "so
every platform reads the same files". A project doing that is thinking about
portable representations, which is exactly the conversation to have — and it
is also a project whose sync internals are in motion, so asking for a *new*
obligation now competes with a migration. Ask for a *convention* they can
satisfy from where they are heading anyway.

**The hub will not lead.** cgm-remote-monitor's 513 commits are maintenance.
Nocturne's 2,546 are where hub-side capability is being built, and xDrip+ is
already uploading to it. So there are effectively two hubs, one of which is
moving fast, and a design that only works if cgm-remote-monitor ships first
will not ship.

## 2. The finding that reorders everything

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

* **cgm-remote-monitor**: nothing. The collection is enabled today.
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
evidence (`specs/sync/registrations/`), and recognises a controller by
**structural discriminator** — a devicestatus carrying `loop` versus
`openaps` — never by the device string.

A controller then has three postures, and only the first requires nothing:

1. **Recognised.** The hub applies the shipped registration. Loop lands here
   and needs no change, ever.
2. **Confirmed.** A controller posts the registration it was going to be
   given anyway, pinning a version. One request, no behaviour change.
3. **Corrected.** A controller posts its own, overriding the shipped one —
   the path for a new feature, a new controller, or a build that diverges.

**The risk this creates, named.** A wrong shipped registration is worse than
none: it would make the hub confidently misdescribe a controller. Three
mitigations, all of which this repository already supports — derive them from
measurement rather than assertion, version them so a correction is a bump
rather than a silent change, and make "not me" expressible so a controller
can always disown one.

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
* **Tenant-registered CRDs**, on current evidence.
* **Anything requiring a Loop change**, until something else has proved the
  value and Loop has capacity.

## 5. What this is actually for

The question framed these features as mainly assisting controller authors,
and that is right, with one addition worth making explicit.

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

**And for the person with diabetes and their clinician** — the part not to
lose — it is that the settings that determine dosing become visible, and that
sensitive context can be shared as its dosing effect without its motivation.
Those are the two complaints this series started from.

## 6. What is not measured

* **Commit counts are not effort or direction.** Loop's 24 commits include
  Xcode 27 support, which is more work than the number suggests, and AAPS's
  2,434 include a multiplatform migration that touches everything.
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

## 7. References

* Branch states fetched 2026-09-11: Trio `origin/dev`, AndroidAPS `origin/dev`, Loop `origin/dev`, LoopKit `origin/dev`, xdripswift `origin/develop`, xDrip `origin/master`, cgm-remote-monitor `origin/dev`, nocturne `origin/main`
* `cgm-remote-monitor/lib/api3/index.js` — `enabledCollections`
* `AndroidAPS/core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/networking/NightscoutApi.kt` — the settings client
* `Trio/Trio/Sources/Models/NightscoutExercise.swift` — still no effect on `dev`
* `specs/sync/registrations/`, `specs/sync/controller-state-model.schema.json`
* `specs/conformance/observability-profile.yaml`, `specs/quirks/`
