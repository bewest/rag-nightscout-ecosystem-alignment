# Ecosystem Progression: Loop & AndroidAPS (dev vs. shipped)

**Date:** 2026-09-14 (research run 2026-09-09)
**Method:** Verified directly against live GitHub (API + `gh` CLI + code
search) — repo metadata, releases/tags, commit comparisons, `.gitmodules`
submodule pins, source files, open/merged PRs. Every claim is citation-backed;
see linked URLs for primary evidence. Companion to
[`ecosystem-progression-nocturne-trio.md`](./ecosystem-progression-nocturne-trio.md).

## Loop

**Repo split** (distinct roles, verified via each repo's own README/`Package.swift`):

| Repo | Role | Default branch | Latest release / HEAD |
|---|---|---|---|
| `LoopKit/LoopWorkspace` | Pure aggregator — pins 21 submodules into one buildable Xcode workspace, no algorithm/UI code of its own ([`.gitmodules`](https://github.com/LoopKit/LoopWorkspace/blob/main/.gitmodules)) | `main` | `v3.14.2` (2026-06-06) = current `main` HEAD (0 commit gap) |
| `LoopKit/LoopKit` | SwiftPM framework library, explicitly *not* providing treatment decisions ([README](https://github.com/LoopKit/LoopKit/blob/dev/README.md)) | `dev` | No release cut since `v3.0` (2019); consumed via pinned submodule instead |
| `LoopKit/LoopAlgorithm` | Newer, separately-versioned SwiftPM package extracting pure dosing-algorithm logic | `main` | No releases at all |
| `LoopKit/LoopCaregiver` | Separate SwiftPM package, README self-describes as "highly experimental" | `dev` | No releases |
| `loopandlearn/LoopFollow` | Display/monitoring-only companion, community-maintained (not in `LoopKit` org) | `main` | `v7.0.0` (2026-07-25); `dev` 11 commits ahead |

**Critical finding — the algorithm-extraction effort is real but not yet
live**: LoopKit's own `dev`-branch [`Package.resolved`](https://github.com/LoopKit/LoopKit/blob/dev/Package.resolved)
pins only `SwiftCharts` — **zero dependency on the standalone `LoopAlgorithm`
package**. LoopKit still carries its own parallel, internal implementation at
[`LoopKit/LoopKit/LoopAlgorithm/`](https://github.com/LoopKit/LoopKit/tree/dev/LoopKit/LoopAlgorithm)
(`DoseMath.swift`, `LoopAlgorithm.swift`, etc.) — distinct code from
`LoopAlgorithm`'s own `Sources/LoopAlgorithm/`. **`LoopAlgorithm` is not
referenced anywhere in LoopWorkspace's submodule tree either.** Treat
`LoopAlgorithm` as an in-progress migration target, not yet the
authoritative algorithm source.

**Submodule drift**: LoopWorkspace's pinned `LoopKit` submodule
(`e7e2ee2b`) is **~4 months and ≥5 merge commits behind** LoopKit's current
`dev` HEAD (`29bc17b`, 2026-09-05) — full chain traced via
`compare/e7e2ee2b...29bc17b`. **Schema-alignment work targeting "current
shipped Loop behavior" should read LoopWorkspace's pinned submodule SHA, not
LoopKit's `dev` HEAD.**

**Active, unshipped work**: LoopKit PR [#612](https://github.com/LoopKit/LoopKit/pull/612)
"Sport Mode, part 1/5" (largest in-flight feature); LoopAlgorithm shows
active Tidepool-linked migration commits (e.g.
[`6e4e315`](https://github.com/LoopKit/LoopAlgorithm/commit/6e4e315), merged
from `tidepool-org/main`; ticket IDs `LOOP-5502` etc. in commit metadata —
circumstantial, not a documented statement, of an eventual
LoopKit→LoopAlgorithm cutover); Loop app PR
[#2455](https://github.com/LoopKit/Loop/pull/2455) "Tag bolus origin and
surface it in Nightscout" — a direct, in-flight change to what Loop uploads.

**Nightscout touchpoints**: `LoopKit/NightscoutService`
([`NightscoutService.swift`](https://github.com/LoopKit/NightscoutService/blob/main/NightscoutServiceKit/NightscoutService.swift))
uploads `TemporaryScheduleOverride` as a Loop-specific **`OverrideTreatment`**
extension type (recurring across LoopKit, NightscoutService, and
LoopCaregiver's `overrideTreatments()` filter) — a first-class typed
extension, not attribute-flattening onto the generic treatment shape. Field-level
Codable schema of `OverrideTreatment`/device-status payloads lives in an
external NightscoutKit fork and was **not verified** in this pass.

## AndroidAPS

| | |
|---|---|
| Latest release | `3.4.2.6` (2026-08-02), ~monthly cadence |
| `dev` HEAD | `7552730` (2026-09-09) — **2,572 commits ahead / 7 behind `master`** (merge-base 2026-08-02) |
| Language | Kotlin 96% / Java 4% |

**~5.5 weeks / 2,572 commits of unreleased `dev` work** — an order of
magnitude larger gap than Loop's (where the gap lives one layer down, in
LoopKit vs. LoopWorkspace, not in AAPS's own release-vs-dev). The very high
commit granularity may reflect AI-assisted atomic commits — `dev` carries a
`CLAUDE.md` file (absent on `master`) documenting a formal AI-agent-assisted
dual-OS (Windows+Mac) build workflow specifically built around the KMP
migration below.

**Active, unshipped work — Kotlin Multiplatform (KMP) migration**: `dev`'s
`settings.gradle` adds `ios/` (full Xcode project `AAPSClient.xcodeproj`) and
`desktop/` modules absent from `master`. **`core/nssdk`** — the dedicated
Nightscout-sync SDK module — has already been restructured on `dev` into
`commonMain`/`commonTest`/`iosMain`/`jvmMain`/`jvmTest` source sets (vs. a
single `src/main` on `master`), confirming **the Nightscout-sync layer
itself is mid-migration**, further along than Loop's algorithm-extraction
effort (AAPS's nssdk is already KMP-restructured; Loop's `LoopAlgorithm` is
still fully unconsumed). `CLAUDE.md@dev` notes only `:core:data` currently
has a working iOS-simulator test target — other KMP modules are pending, not
complete.

**Nightscout/data-model touchpoints — most mature sync-identity convention
found across all four projects researched**: `InterfaceIDs.kt`
([source](https://github.com/nightscout/AndroidAPS/blob/master/database/impl/src/main/kotlin/app/aaps/database/entities/embedments/InterfaceIDs.kt))
defines `nightscoutSystemId`, `nightscoutId`, `pumpType`, `pumpSerial`,
`temporaryId`, `pumpId`, `startId`, `endId` — a canonical, typed,
Room-embedded sync-identity field set present on **every** syncable
database entity, matched by a family of `SyncNs*Transaction.kt` files.
`core/nssdk`'s `RemoteTreatment.kt` shows AAPS-specific wire-format
extensions layered onto the standard treatment schema (temp-target
`targetTop`/`targetBottom`; profile-switch `profile`/`percent`/`absolute`;
automation `mode`/`autoForced`/`reasons`; combo-bolus-split
`splitNow`/`splitExt`) **plus** standard v3 metadata (`identifier`,
`srvCreated`, `srvModified`, `subject`, `modifiedBy`, `isValid`,
`isReadOnly`, `utcOffset`) — attribute-flattening style, not a separate
typed override object the way Loop's `OverrideTreatment` is.

## Cross-project observations (Loop vs. AAPS)

1. **Sync-identity convention: AAPS is the reference model.** AAPS's
   `interfaceIDs.nightscoutId`/`nightscoutSystemId` pair is an explicit,
   typed, universally-embedded sync-identity convention. Loop's ecosystem
   has **no verified equivalent** — its Nightscout upload path issues
   creates/deletes by treatment object without a documented, app-visible
   persisted sync-ID field comparable to AAPS's. **Recommend AAPS's
   `InterfaceIDs` pattern as the reference convention** for any
   cross-project sync-identity schema work.
2. **Override/temp-target modeling differs structurally, matches the
   Nocturne/Trio finding.** Loop treats overrides as a first-class typed
   `OverrideTreatment` extension (recurring across 3 repos). AAPS instead
   flattens temp-target attributes directly onto the generic treatment
   wire model. This is the **same pattern split already observed** between
   Nocturne (extension-bag/typed-object style) and Trio (attribute-flattening
   into shared schema) — see `ecosystem-progression-nocturne-trio.md` §"Cross-project
   observations" item 3. Four independent projects, two consistent camps.
   Schema-vocabulary work should treat this as a **named, two-option design
   decision** (typed extension object vs. attribute-flattening) rather than
   an incidental implementation detail — both approaches have real,
   maintained prior art and neither is objectively "correct" yet.
3. **Algorithm/data-layer decoupling is a shared theme, different
   maturity.** Both projects are mid-migration toward separating
   algorithm/data logic from platform code — Loop via `LoopAlgorithm`
   (verified **not yet consumed** in production), AAPS via KMP (verified
   **already restructured** for the Nightscout-facing `core/nssdk` layer
   specifically). AAPS is measurably further along for the
   Nightscout-facing layer.
4. **"Current shipped behavior" means different things per project** for
   any future compatibility-testing work: pull from LoopWorkspace's pinned
   submodule SHAs (not LoopKit's `dev` HEAD) for Loop; pull from AAPS's
   tagged release (not `dev`, given the outsized unreleased delta) for AAPS.
5. **No project's public artifacts document explicit schema/versioning
   convergence plans.** AAPS↔Trio and LoopKit↔LoopAlgorithm relationships
   are both inferred from repo co-location/commit metadata, not stated
   governance — flagged as an open question for any team-level
   schema-consensus discussion, not something resolvable from source alone.

## Combined four-project schema-vocabulary takeaways

Read together with `ecosystem-progression-nocturne-trio.md`, four
independently-maintained projects show a consistent **two-camp split** on
handling non-standard/vendor-specific fields:

| Camp | Projects | Pattern |
|---|---|---|
| **Typed extension / extension-bag** | Nocturne (`ExtensionData` bag on `DeviceStatus`), Loop (`OverrideTreatment` typed object) | Isolates non-standard fields from the shared/legacy schema |
| **Attribute-flattening** | Trio (`overridePresets`/APNS fields embedded directly in profile), AAPS (`targetTop`/`targetBottom`/`mode` flattened onto generic treatment) | Embeds extensions directly into the shared collection shape |

This is the single clearest, most actionable finding for the
schema-vocabulary backlog item: **propose an explicit, named
extension-bag convention** (e.g., an `x-aid-extensions` object field) in
`specs/openapi/aid-*-2025.yaml`, using Nocturne's `ExtensionData` and Loop's
`OverrideTreatment` as prior art for the "isolate, don't flatten" side of
the decision, and cite AAPS/Trio's flattening approach as the
compatibility-preserving status quo that the extension-bag convention
should remain interoperable with (i.e., don't break existing
attribute-flattened fields, just stop encouraging new ones).

Separately, integer-millisecond timestamp semantics
(`ecosystem-progression-nocturne-trio.md`'s finding from Trio PR #1476 and
Nocturne's mills-first fallback chain) remains the other clear,
actionable, cross-project convention gap worth formalizing.

## Next steps (not yet done)

- [ ] Confirm whether AAPS's wiki (`wiki.aaps.app`) or LoopDocs
      (`loopdocs.org`) document any explicit schema/roadmap statements not
      visible via the GitHub API/code-search (both flagged as unverified
      in this pass).
- [ ] Draft the `x-aid-extensions` convention proposal referenced above as
      a concrete addition to the schema-vocabulary backlog item.
- [ ] Field-level verification of `OverrideTreatment`'s Codable schema
      (currently unverified — lives in an external NightscoutKit fork).
