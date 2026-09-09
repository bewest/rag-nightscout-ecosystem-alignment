# Ecosystem Progression: Nocturne & Trio (dev vs. shipped)

**Date:** 2026-09-14 (research run 2026-09-09)
**Method:** Verified directly against live GitHub (API + `gh` CLI): repo
metadata, releases/tags, commit comparisons, source files, PRs. Every claim
below is citation-backed; see the linked URLs for primary evidence. This
supersedes the characterization of these two projects in
`workspace.lock.json`'s `description` fields, which are corrected below.

## Correction to prior assumptions

- **Nocturne is *not* a "Nightscout client app"** (as described in
  `workspace.lock.json`). It is a from-scratch **C#/.NET 10 rewrite of the
  Nightscout server/API itself**, bundled with a SvelteKit web frontend,
  desktop app, and widgets — a monorepo, not a fork of `cgm-remote-monitor`.
  Source: [`nightscout/nocturne` README](https://github.com/nightscout/nocturne#readme)
  — "Complete Nightscout API Implementation... full compatibility."
- **`Trio-dev` (the repo pinned in `workspace.lock.json`) is stale/effectively
  abandoned.** Last push 2026-05-07; zero GitHub Releases ever
  ([`repos/nightscout/Trio-dev/releases`](https://github.com/nightscout/Trio-dev/releases)
  is empty). All real Trio development now happens on the `dev` branch
  **inside `nightscout/Trio` itself**, which is 1,304 commits ahead of the
  latest tag `v0.8.4` as of 2026-09-08
  ([compare](https://github.com/nightscout/Trio/compare/v0.8.4...dev)).
  **Action: repoint `workspace.lock.json`'s Trio-dev pin to
  `nightscout/Trio@dev` and retire the `Trio-dev` entry** (tracked as a
  follow-up, not done in this pass — see "Next steps" below).

## Nocturne

| | |
|---|---|
| Latest tag | `v0.2.6` (2026-09-01), commit `36119eab8` |
| Latest `main` | `80b494084` (2026-09-09), **123 commits ahead** of `v0.2.6` |
| Our pin | `39856ca77` (2026-07-16) — **458 commits behind current `main`** |
| Cadence | ~weekly/biweekly tagged releases, terse auto-generated notes ([`v0.2.6`](https://github.com/nightscout/nocturne/releases/tag/v0.2.6)) |
| Activity | Very active — commits multiple times/day, 119 stars, 174 open issues, pushed essentially continuously |

**In-flight work not yet released:** granular perf/correctness fixes (e.g.
[#1286](https://github.com/nightscout/nocturne/pull/1286) alert evaluation
dedup, [#1274](https://github.com/nightscout/nocturne/pull/1274) reconcile
cursor paging) plus a substantial **new "V4" typed schema layer**
(`src/Core/Nocturne.Core.Models/V4/`, ~60 files: `BolusCalculation`,
`BasalInjection`, `TempBasal`/`TempBasalOrigin`, `CarbRatioSchedule`,
`DeviceCatalog`, `PatientDevice`, `InsulinCatalog`, `CanonicalGlucoseStream`)
— actively refactored as of 2026-09-05
([#1165](https://github.com/nightscout/nocturne/pull/1165)), not yet public
API. **This V4 model is the single most relevant artifact in the entire
ecosystem for our schema-vocabulary work** — it's an independent, from-scratch
attempt at exactly the typed-schema problem we're scoping.

**Data-model design worth adopting as pattern:**
- **"Mills-first" timestamp reconciliation**: `Mills` is the source of truth;
  `Date`/`DateString`/`CreatedAt` are computed fallback properties. Documented
  directly in XML doc-comments on `Entry.cs`/`DeviceStatus.cs`.
- **`ExtensionData` bag** on `DeviceStatus.cs` to tolerate unknown
  vendor-specific top-level keys (e.g. AAPS's `configuration`) without
  breaking — an explicitly forward-compatible, schema-tolerant pattern.

## Trio

| | |
|---|---|
| Latest tag | `v0.8.4` (2026-07-02) |
| Latest `dev` | `fb2b1360b` (2026-09-08), **1,304 commits ahead** of `v0.8.4` |
| Distribution | No App Store build — self-build (`TrioBuildSelectScript.sh`) or Fastlane/TestFlight sideload only |
| Cadence | ~2-6 week tagged releases (20 releases total) |
| Activity | Very active — 379 stars, 99 open issues, named `DATA_MAINTAINERS.md` governance file |

**In-flight work not yet released:**
- [#1300](https://github.com/nightscout/Trio/pull/1300) — reworks pump-event
  finalization/upload semantics: scheduled/inferred basal segments will no
  longer be uploaded to Nightscout at all ("NS is not uploaded SBR rows") —
  an **active in-progress change to Trio's NS treatment-upload contract**.
- [#1302](https://github.com/nightscout/Trio/pull/1302) — replaces
  exponential glucose smoothing with an Unscented-Kalman-Filter adaptive
  smoother (off by default).
- Recently merged, not yet tagged:
  [#1476](https://github.com/nightscout/Trio/pull/1476) — fixes a live bug
  where `getGlucoseNotYetUploadedToNightscout()` computed **fractional
  (sub-millisecond) `Decimal` timestamps**, uploading malformed values like
  `1788785143203.7996` to Nightscout's `entries` collection, which then
  broke `lastModified.collections.entries` for clients expecting integer
  milliseconds. **Directly relevant**: this is a live, real-world instance
  of the exact timestamp-typing ambiguity Nocturne's `Entry.cs` independently
  built defensive fallback logic for (see above).

**Data-model design pattern — a caution, not an example to follow:** Trio's
`NightscoutProfileStore` struct **hard-codes Trio-specific extensions
directly into the shared profile schema** (`overridePresets`,
`bundleIdentifier`, `deviceToken`, `isAPNSProduction`, `teamID`), rather than
isolating them in an extension bag the way Nocturne's `DeviceStatus`
`ExtensionData` does. This is a live source of schema drift risk: any other
client/server reading Nightscout's `profile` collection must now tolerate
Trio-specific fields it doesn't otherwise know about.

## What this means for schema-vocabulary work

1. **Standardize integer-millisecond timestamp semantics and the
   `date`/`dateString`/`mills`/`created_at` fallback order as an explicit,
   documented cross-ecosystem convention.** Both an independent server
   rewrite (Nocturne) and a major, actively-maintained client (Trio, via a
   just-fixed production bug) are each independently working around the
   same ambiguity — this is empirical proof the ambiguity is a real,
   recurring cost, not a theoretical concern.
2. **Recommend an extension-bag convention (Nocturne's `ExtensionData`
   pattern) over ad-hoc embedding (Trio's `overridePresets`/APNS-fields-in-profile
   pattern)** for any new typed schema work in this repo's
   `specs/openapi/aid-*-2025.yaml`. This should be an explicit, named
   convention (e.g., `x-aid-extensions` or similar), not left implicit.
3. **Nocturne's V4 model (`src/Core/Nocturne.Core.Models/V4/`) is prior art
   worth directly comparing field-by-field against this repo's
   `specs/openapi/aid-*-2025.yaml`** before drafting any new typed-schema
   proposal — there is a real risk of the two efforts diverging
   independently on the same problem (bolus-calculation modeling,
   device/insulin catalogs, canonical glucose streams) without either side
   aware of the other. Flagged as a concrete next step, not done in this
   pass.

## Next steps (not yet done)

- [ ] Refresh `workspace.lock.json`: advance `nocturne` pin from `39856ca77`
      to current `main`; replace the `Trio-dev` entry with a pin against
      `nightscout/Trio@dev` (retire `Trio-dev` as a tracked external).
      **Blocked as of 2026-09-14**: `externals/nocturne`'s local worktree
      has 2,591 changed files relative to its pinned commit (`git status
      --short | wc -l`) — likely leftover local experimentation from a
      prior session, not a clean fetch-only state. `tools/bootstrap.py
      refresh` correctly skipped it ("worktree is dirty") rather than
      force-discarding those changes. Needs a decision (stash/discard vs.
      inspect-and-preserve) before refreshing, not done unilaterally here.
- [ ] Field-by-field diff of Nocturne's V4 model vs.
      `specs/openapi/aid-*-2025.yaml`.
- [ ] Raise the "extension bag vs. ad-hoc embedding" convention as a
      concrete proposal in the schema-vocabulary backlog item.
