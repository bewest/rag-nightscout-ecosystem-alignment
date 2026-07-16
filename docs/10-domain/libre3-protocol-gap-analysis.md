# Libre 3 Protocol Readiness Report

> **Updated**: 2026-07-16
> **Prior report**: 2026-01-29 "eavesdrop only" gap analysis
> **Focus**: Loop `next-dev`, Trio PR #1275, DiaBLE, LibreLoop, and LibreCRKit

---

## Executive Summary

The January report is now stale. It correctly described the then-visible ecosystem state: Libre 3/3+ direct BLE access was blocked for most open-source apps, with LibreLinkUp cloud polling or eavesdrop/Juggluco-style approaches as the practical options. The July 2026 source evidence shows a new active direct-reader lane:

- **Loop `next-dev`** has a LibreLoop/LibreCRKit integration path and has been receiving frequent Libre 3 stability updates, including backfill, reconnect, sensor-failure UI, and status handling.
- **Trio PR #1275** adds Libre 3/3+ as a CGM plugin by wiring `LibreLoop`, `LibreCRKit`, and `LoopAlgorithm` through Trio's existing `PluginManager` / `PluginSource` path.
- **DiaBLE** remains the strongest protocol-research reference. Its README now advertises Libre 3 Direct-To-Watch via Messina while still warning that direct Apple Watch BLE is prototype-stage and background operation remains unresolved.

The core protocol conclusion should shift from "no known legal/direct solution" to **"active direct-reader implementations exist, but protocol provenance, long-term compatibility, and app-readiness evidence need verification before treating this as a stable ecosystem baseline."**

| Aspect | January 2026 Status | July 2026 Evidence | Current Assessment |
|--------|---------------------|--------------------|--------------------|
| Direct BLE | Marked blocked for third-party apps | Loop `next-dev` integrates LibreLoop/LibreCRKit; Trio PR #1275 integrates the same lane | Active implementation lane, not yet broadly released |
| NFC | Activation/pairing only | No evidence of retrospective glucose reads via NFC | Still activation/pairing only |
| Cloud fallback | LibreLinkUp was the practical path | `nightscout-connect` now hardens LibreLinkUp regions, patient selection, version/product knobs, and current+graph reads | Still important fallback and bridge path |
| Backfill | Cloud/API dependent in prior report | LibreLoop commits include Libre 3 backfill fixes, ATT 0xFD, and 24h cold-start/relaunch test criteria in Trio PR #1275 | Direct-reader backfill is now a readiness claim needing validation |
| Alerts/status | Not integrated into AID UI | Loop `next-dev` and Trio PR #1275 surface sensor lifecycle/status highlights and LibreLoop alerts | Near-readiness UI integration |

---

## Current Evidence

### Trio PR #1275: Libre 3/3+ Plugin Integration

**PR**: `https://github.com/nightscout/Trio/pull/1275`
**State on 2026-07-16**: open, non-draft, 70 commits, 12 changed files, `feat/dev-libre3` into `dev`
**Head**: `3307c0775a5e838fc2e2a7dc329047a7cdb4713f`

The PR body says it:

- integrates the LibreLoop CGM plugin, with adaptations for pre-`next-dev` LoopKit;
- allows Trio to pair FreeStyle Libre 3 / 3+ directly without internet reliance or an external app;
- adds three submodules: `LibreLoop`, `LibreCRKit`, and `LoopAlgorithm`;
- wires them through Trio's existing `PluginManager` / `PluginSource` path;
- adds Libre 3 / 3+ to the CGM picker and surfaces sensor lifecycle/status on the home glucose view.

Changed files from the PR include:

| Area | File(s) | Readiness Meaning |
|------|---------|-------------------|
| Submodules | `.gitmodules`, `LibreCRKit`, `LibreLoop`, `LoopAlgorithm` | Adds the Libre 3 data plane and Loop algorithm dependency |
| Build wiring | `Trio.xcodeproj/project.pbxproj`, workspace, `Package.resolved` | Makes the plugin buildable in Trio |
| Plugin registration | `Trio/Sources/APS/PluginManager.swift` | Adds `"FreeStyle Libre 3 / 3+"` via `LibreLoopCGMManager` |
| CGM source bridge | `Trio/Sources/APS/CGM/PluginSource.swift` | Imports `LibreLoop`, forwards CGM status/alerts, maps `LibreLoopCGMManager` readings |
| UI options/status | `Trio/Sources/Helpers/CGMOptions.swift`, `HomeStateModel.swift`, localizations | Exposes the CGM picker and home status highlight |

Submodule pins in the PR:

| Submodule | Pin |
|-----------|-----|
| `LibreCRKit` | `2d87f81ac4c0d17295b9cb642299c46fe4ddf9b1` |
| `LibreLoop` | `8e376c4bc8a559ff8da41f5e11101771897884d6` |
| `LoopAlgorithm` | `2f5c630084aa0d72b8d14999e1e0f7c836b0c341` |

The PR test plan explicitly claims:

- Libre 3 / 3+ appears in CGM settings on fresh install.
- A new Libre 3 / 3+ can pair and complete warmup.
- Glucose arrives on a 5-minute cadence with no gaps over 6 minutes under steady conditions.
- Backfill on cold-start/relaunch fills the last 24 hours.
- Sensor progress on the home view matches remaining lifetime and flips to grace period near expiry.
- LibreLoop alerts for sensor issue, expiring, and expired surface in Trio.
- Swapping between Libre 3 / 3+ and another CGM does not leave stuck state.
- Trio enacts against Libre readings without regressions.

### Loop `next-dev`: LibreLoop/LibreCRKit Stabilization Lane

Local worktree: `externals/readiness/LoopWorkspace-next-dev`
Current HEAD: `584bdafc915a`
Submodule pins observed:

| Submodule | Pin / Ref | Notes |
|-----------|-----------|-------|
| `LibreLoop` | `e0282d063323` | Active direct-reader plugin lane |
| `LibreCRKit` | `66920c6d5a0d` | Crypto/control reader kit |
| `LoopAlgorithm` | `0ed893c1a75` | Included for algorithm/package integration |
| `NightscoutRemoteCGM` | `origin/next-dev` | CGM integration branch |
| `NightscoutService` | `origin/next-dev` | Nightscout service branch |

Recent Libre-specific commits in Loop `next-dev` and its Libre submodules:

| Date | Commit | Finding |
|------|--------|---------|
| 2026-07-15 | `584bdaf` / LibreLoop `e0282d0` | Distinguishes sensor expired vs transient communication errors; transient code-7 no longer stops Loop |
| 2026-07-11 | `d770452` / LibreLoop `b21aa70` | Libre 3 backfill fix, ATT `0xFD`, silence watchdog, glucose diagnostics |
| 2026-06-30 | `60a3282` / LibreLoop `849653b` | Fixes Recent Readings detail crash |
| 2026-06-29 | `2e02b8a` / LibreCRKit `abb0f7e` | CCCD re-arm on `patchControl` reconnect |
| 2026-06-26 | `b3cde61`, `3d62a3c` | Sensor failure UI, reconnect backoff, re-scan prompt |
| 2026-06-25 | `ebd3441`, `b8528c0` | Stable receiverID, pairing fixes, sensor-attention alerts |
| 2026-06-24 | `58d2d6b`, LibreCRKit `ae3ebf7` | Glucose stream debug view and data-plane notification subscription |
| 2026-06-11 | `c3e6b65` | Backfill recent window plus sync ID |

This pattern looks like release-hardening rather than exploratory one-off work: the branch is repeatedly fixing reconnection, pairing, backfill, localization, display units, and user-facing error states.

### DiaBLE: Protocol Research and Prototype App

DiaBLE's README now records a 2026-07-03 build for **Libre 3 Direct-To-Watch** using the Messina one-shot server. It also states that the project is targeting Libre 3 and Dexcom G7, but warns that direct Libre 2/3 and G7 Apple Watch connection remains proof-of-concept and background execution needs additional work.

Recent DiaBLE commits show ongoing Libre 3 protocol research:

| Date | Commit | Finding |
|------|--------|---------|
| 2026-07-16 | `a7db070` | Tested `.shutdownPatch` |
| 2026-07-16 | `f11f2d4` | Gets `wearDuration` from factory data |
| 2026-07-16 | `cfa8d45` | Gets NFC UID from factory data |
| 2026-07-15 | `1f3fffd` | BLE Setup toggle between Messina and LibreCRKit |
| 2026-07-06 | `e5580d5` | Updates Libre 3++ TODOs |
| 2026-07-05 | `9b9f741` | Stores `lastPatchStatusEvent` and event log |
| 2026-07-03 | `823e455` | Drops LibreCRKit from DiaBLE after earlier experimentation |
| 2026-06-22 | `3dcb386` | Sets Libre 3 family on BLE |
| 2026-06-18 | `7c0f775` | Uses LibreCRKit AES-CCM encrypt/decrypt with Phase 5 raw key |

DiaBLE remains valuable because it exposes low-level protocol artifacts: factory data, event log, patch status, activation, NFC UID, shared key material, and watchOS feasibility.

---

## Updated Protocol Model

### What Appears Stable

- Libre 3/3+ remains a BLE-first sensor; NFC is used for activation/pairing metadata, not retrospective glucose history.
- Direct BLE operation requires a security handshake and encrypted data plane.
- The ecosystem now has active Swift implementations (`LibreLoop`, `LibreCRKit`) that claim direct pairing, 5-minute clinical cadence, 24h backfill, and sensor lifecycle events.
- LibreLinkUp remains a necessary fallback/integration path for cloud follower use cases and for systems that do not ship direct BLE support.

### What Needs Verification

The open question is no longer simply "can any app decrypt Libre 3?" The current verification questions are:

1. **Key and certificate provenance**: What exact certificate/key material is bundled or derived, and can it be documented without distributing proprietary material?
2. **Handshake completeness**: Which Libre 3/3+ firmware, region, product type, and sensor family variants complete first-pair, reconnect, and re-pair flows?
3. **Backfill semantics**: How do ATT `0xFD`, clinical data, historical data, life count, and timestamp alignment map to Nightscout `entries`?
4. **Error taxonomy**: How should transient communication errors, terminal sensor failures, sensor attention, grace period, expired state, and shutdown patch map across Loop, Trio, Nightscout, and xDrip?
5. **Closed-loop safety**: What filtering, quality flags, stale-data guards, and sensor status checks are required before AID enacts from direct Libre 3 readings?

---

## Revised Implementation Status

| App / Project | January Status | July 2026 Status | Method |
|---------------|----------------|------------------|--------|
| Loop `main` | No Libre 3 direct support documented | `v3.14.2` main remains release baseline | No direct Libre 3 release baseline observed |
| Loop `next-dev` | Not represented | Active LibreLoop/LibreCRKit integration with repeated backfill, reconnect, UI, and alert fixes | Direct BLE via LibreLoop/LibreCRKit |
| Trio `dev` | Not represented | PR #1275 open, adds Libre 3/3+ CGM picker, submodules, status highlight, and plugin wiring | Direct BLE via LibreLoop/LibreCRKit |
| DiaBLE | Eavesdrop/prototype | Direct-To-Watch prototype via Messina and LibreCRKit experiments; still prototype-stage | Protocol research/direct BLE experiments |
| xdripswift | Heartbeat/cloud follower | No new direct Libre 3 release evidence in current pinned release | LibreLinkUp/cloud follower |
| xDrip+ | No native Libre 3 in prior report | July release hardens Nightscout/Juggluco follow paths, but no direct Libre 3 branch in pinned path | External bridge/follower likely |
| nightscout-connect | Not a direct reader | Hardened LibreLinkUp region/version/patient/current+graph behavior | Cloud bridge |

---

## Gaps Reclassified

### GAP-CGM-030: Libre 3 Direct BLE Access Blocked

**Old classification**: Open, no known legal solution.
**New classification**: Partially remediated by active Loop/Trio direct-reader implementations, but not closed.

The existence of Loop `next-dev` and Trio PR #1275 changes the gap from absolute access blockage to **ecosystem validation and documentation**:

- Does the implementation work across Libre 3 and Libre 3+ regions and firmware?
- Can the security material and protocol be documented with acceptable provenance?
- Can direct-reader entries carry enough source/status metadata for Nightscout and downstream AID safety review?

### GAP-CGM-031: Libre 3 NFC Limited to Activation

Still open. No evidence found that Libre 3 NFC can read retrospective glucose history like Libre 1/2 FRAM.

### GAP-CGM-032: LibreLinkUp API Dependency

Partially mitigated for Loop/Trio direct-reader paths, but still open for cloud/follower integrations and non-direct-reader apps. LibreLinkUp remains important for Nightscout Connect, xdripswift follower mode, and cross-device sharing.

### GAP-CGM-035: Libre 3 Direct-Reader Provenance and Readiness Evidence

New gap. Direct-reader code now exists, but the ecosystem lacks a consolidated, traceable specification for handshake inputs, certificate/key provenance, supported variants, backfill mapping, and safety gates.

---

## Recommendations

### For Protocol Documentation

1. Promote this report from "blocked" language to "active direct-reader validation" language.
2. Add a source-backed Libre 3 handshake and data-plane appendix once LibreCRKit/LibreLoop source review is complete.
3. Document ATT `0xFD`, factory data, patch status, event log, clinical/historical data, and `sensorAttention` meanings with source line references.
4. Keep cloud fallback documentation because LibreLinkUp remains the broadest interoperability path.

### For Loop / Trio Readiness Review

1. Treat Loop `next-dev` as the current upstream readiness lane.
2. Treat Trio PR #1275 as a port/integration lane that adapts LibreLoop for pre-`next-dev` LoopKit.
3. Verify 5-minute cadence, no gaps over 6 minutes, 24h backfill, sensor expiry/grace-period UI, and CGM swap cleanup using real sensor traces.
4. Require explicit stale-reading and sensor-status gating before closed-loop enactment from Libre 3 direct readings.

### For Nightscout Interoperability

1. Ensure entries from direct Libre 3 readers carry stable `device` and source metadata that distinguishes direct BLE from LibreLinkUp cloud follower data.
2. Standardize mapping for sensor status events: warmup, active, grace period, expiring, expired, terminal failure, transient communication failure.
3. Keep `nightscout-connect` LibreLinkUp compatibility tests current for regions, explicit hosts, product/version knobs, patient selection, graph/current overlap, and timezone-qualified timestamps.

---

## Source References

| Evidence | Source |
|----------|--------|
| Trio PR #1275 summary, test plan, open state | `https://github.com/nightscout/Trio/pull/1275` |
| Trio PR #1275 submodules | `externals/Trio:.gitmodules` on fetched `origin/pr-1275` |
| Trio PR #1275 plugin wiring | `externals/Trio/Trio/Sources/APS/PluginManager.swift` on `origin/pr-1275` |
| Trio PR #1275 CGM source bridge | `externals/Trio/Trio/Sources/APS/CGM/PluginSource.swift` on `origin/pr-1275` |
| Loop `next-dev` Libre pins | `externals/readiness/LoopWorkspace-next-dev` submodule status |
| LibreLoop readiness commits | `externals/readiness/LoopWorkspace-next-dev/LibreLoop` git log |
| LibreCRKit readiness commits | `externals/readiness/LoopWorkspace-next-dev/LibreCRKit` git log |
| DiaBLE Direct-To-Watch and prototype caveat | `externals/DiaBLE/README.md:6-23` |
| LibreLinkUp bridge compatibility | `externals/nightscout-connect/README.md:211-233`, `externals/nightscout-connect/test/librelinkup.test.js:21-150` |

---

## Cross-References

- [Libre Sensor Protocol Deep Dive](libre-protocol-deep-dive.md)
- [CGM Sources Gaps](../../traceability/cgm-sources-gaps.md)
- [CGM Sources Requirements](../../traceability/cgm-sources-requirements.md)
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md)
- [nightscout-connect LibreLinkUp Deep Dive](nightscout-librelink-up-deep-dive.md)
