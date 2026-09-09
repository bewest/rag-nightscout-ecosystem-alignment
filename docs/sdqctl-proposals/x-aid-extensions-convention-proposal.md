# Proposal: `x-aid-extensions` — a named convention for vendor-specific fields

**Status:** Draft, for discussion
**Created:** 2026-09-14
**Author context:** Emerged directly from cross-project research —
[`ecosystem-progression-nocturne-trio.md`](../reports/nightscout-release-planning-2026-09/ecosystem-progression-nocturne-trio.md)
and [`ecosystem-progression-loop-aaps.md`](../reports/nightscout-release-planning-2026-09/ecosystem-progression-loop-aaps.md)
found the **same two-camp split**, independently, across four unrelated
projects.

## Problem

`entries`, `treatments`, `profile`, and `devicestatus` documents in
practice all carry vendor-specific fields beyond the documented Nightscout
schema — every client that both reads and writes these collections has
independently had to decide how to handle fields it doesn't recognize.
Verified across four live codebases (research citations in the linked docs
above), there are exactly two camps, with no consistent convention across
the ecosystem:

| Camp | Example | Where |
|---|---|---|
| **Typed extension / extension-bag** — isolate non-standard fields in a dedicated sub-object | `DeviceStatus.ExtensionData` (catches unknown top-level keys, e.g. AAPS's `configuration`) | Nocturne, `src/Core/Nocturne.Core.Models/DeviceStatus.cs` |
| | `OverrideTreatment` (dedicated typed treatment subtype, not flattened fields) | Loop, `NightscoutService.swift` / `LoopCaregiverKit` |
| **Attribute-flattening** — embed vendor fields directly into the shared document shape | `overridePresets`, `bundleIdentifier`, `deviceToken`, `isAPNSProduction`, `teamID` embedded directly in the profile-store payload | Trio, `NightscoutProfileStore.swift` |
| | `targetTop`/`targetBottom`/`mode`/`autoForced`/`splitNow`/`splitExt` flattened onto the generic treatment wire model | AAPS, `core/nssdk/.../RemoteTreatment.kt` |

Our own specs already show the same split *within this repo*, unresolved:
`specs/openapi/aid-devicestatus-2025.yaml`'s `extended` field already uses
`additionalProperties: true` (an unnamed extension-bag), but
`aid-treatments-2025.yaml` and `aid-entries-2025.yaml` have **no
equivalent** — vendor fields on those collections are implicitly tolerated
(JSON is permissive) but never named, documented, or given a schema
location.

## Why this matters now

This is not a hypothetical compatibility concern:

- Trio's PR [#1476](https://github.com/nightscout/Trio/pull/1476) (merged,
  not yet tagged) had to fix a live bug where fractional-millisecond
  timestamps leaked into `entries` and broke other clients' handling of
  `lastModified.collections.entries` — an example of what happens when a
  field's exact shape isn't a named, enforced contract.
- Nocturne is independently building a `mills`-first timestamp fallback
  chain to tolerate the same ambiguity from the other direction (reading
  whatever any client wrote).
- Four independently-maintained, actively-developed projects have each
  made a real, deliberate design choice here — this is a solved-enough
  problem in practice that the ecosystem can name a convention rather than
  leaving four incompatible tacit conventions in place indefinitely.

## Proposed convention

Adopt an explicit, named, optional sub-object on each of the four core
collections' schemas, following the extension-bag camp (matches Nocturne's
`ExtensionData` and is a strict generalization of the devicestatus
`extended` field already in `aid-devicestatus-2025.yaml`):

```yaml
x-aid-extensions:
  type: object
  description: >
    Vendor- or client-specific fields not part of the core Nightscout
    schema. Clients SHOULD write non-standard fields here rather than at
    the document's top level. Readers MUST tolerate (ignore, don't reject)
    unknown keys both at the top level (for backward compatibility with
    existing attribute-flattening clients) and within this object.
  additionalProperties: true
```

- **Not a breaking change.** This does not require any existing client
  (Trio, AAPS, or anything else that currently flattens fields) to change
  anything — flattened fields remain valid and readable. It only gives
  *new* integrations, and any future refactor of existing ones, an
  explicit, documented place to put non-standard data instead of silently
  flattening it.
- **Applies uniformly** to `aid-entries-2025.yaml`, `aid-treatments-2025.yaml`,
  `aid-profile-2025.yaml`, and formalizes/renames the existing
  `devicestatus.extended` field's intent in `aid-devicestatus-2025.yaml`
  (kept as an alias or migrated, to be decided — see open questions).
- **Namespaced sub-keys recommended, not required** — e.g.
  `x-aid-extensions: { "trio": {...}, "aaps": {...} }` — to reduce
  collision risk between vendors, following the general precedent of
  reverse-DNS/vendor-prefixed keys elsewhere in the ecosystem (not
  currently enforced anywhere we found, would be a new soft convention).

## What this does *not* solve

- Does not migrate existing flattened fields (`overridePresets`, `mode`,
  `splitNow`, etc.) — those remain as documented, historical exceptions.
  This proposal is forward-looking only.
- Does not address the separate, larger timestamp-semantics question
  (`mills`/`date`/`dateString`/`created_at` fallback order) — that is
  flagged as an independent follow-up in both ecosystem-progression docs
  and deserves its own proposal.
- Does not itself resolve Nocturne's in-progress "V4" schema
  (`src/Core/Nocturne.Core.Models/V4/`) against this repo's specs — a
  field-by-field diff is still an open, unstarted next step (see the
  ecosystem-progression docs).

## Open questions for discussion

1. Should `devicestatus.extended` (`additionalProperties: true`, already
   shipped in `aid-devicestatus-2025.yaml`) be renamed to
   `x-aid-extensions` for naming consistency, or kept as-is with
   `x-aid-extensions` documented as an equivalent pattern for the other
   three collections? Renaming is a spec-only (non-breaking, since it's
   pure documentation/schema metadata) change but touches an existing,
   presumably-reviewed file.
2. Should namespacing (`x-aid-extensions.<vendor>`) be a MUST or a SHOULD?
   A MUST is stronger but unenforceable without server-side validation
   that doesn't currently exist for this field (ties into the
   `tooling-evaluation-keyv-mongoose-zod-wasm.md` zod/schema-validation
   discussion for `cgm-remote-monitor`'s API3 layer).
3. Is this worth raising upstream (as a GitHub issue/discussion on
   `nightscout/cgm-remote-monitor` or a cross-project RFC) rather than
   staying purely documentary in this repo? Given it's backed by evidence
   from four independent projects, it may carry more weight as a
   community-facing proposal than an internal-only spec note.

## Relationship to other in-repo work

- Builds directly on the cross-project research in
  `docs/reports/nightscout-release-planning-2026-09/ecosystem-progression-nocturne-trio.md`
  and `.../ecosystem-progression-loop-aaps.md` (primary evidence).
- Complements (does not duplicate) `docs/sdqctl-proposals/state-ontology-proposal.md`
  (observed/desired/control state — a different axis of schema
  organization) and `statespan-standardization-proposal.md` (time-ranged
  state modeling — orthogonal to field-extension conventions).
- The validation-mechanism question in "Open questions" #2 ties into
  `docs/reports/nightscout-release-planning-2026-09/tooling-evaluation-keyv-mongoose-zod-wasm.md`'s
  zod recommendation (fold into the broader schema-vocabulary
  implementation, not a standalone change).
