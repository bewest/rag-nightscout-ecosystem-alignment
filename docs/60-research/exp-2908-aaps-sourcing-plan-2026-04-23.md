# EXP-2908 — AAPS data sourcing plan

**Date:** 2026-04-23 (overnight)
**Author:** autonomous research session
**Purpose:** Concrete next-steps to expand the cohort with AAPS
(AndroidAPS) patient data so that `oref0` and `oref1` algorithm
effects can be separated from `Trio` iOS-platform effects, and so
that lineage-tier claims escape the n=3 underpowered region.

## Why this matters (gap motivation)

Current cohort lineage assignment:

| Lineage         | n  | Platform        | Algorithm   |
|-----------------|---:|-----------------|-------------|
| Loop (iOS)      |  7 | iOS             | LoopAlgorithm |
| oref1 (modern)  |  9 | iOS (Trio)      | oref1 (algo) |
| oref0 (legacy)  |  3 | iOS (Trio dev)  | oref0       |

Problems:
1. **No AAPS patients** — every "oref1" patient runs Trio on iOS, so
   oref1-algorithm and Trio-iOS-platform are **fully confounded**.
2. **n=3 oref0** — within-lineage tercile splits put 1 patient per tier;
   any tercile-level claim is anecdotal.
3. EXP-2904 oref0-vs-Loop t-collapse is driven by single patient
   (odc-86025410). With n=3 there's no graceful exclusion.
4. EXP-2908a hypothesis: AAPS+oref1 should match Trio+oref1 (algorithm
   effect dominant); AAPS+oref0 (uncommon) vs Trio+oref0 isolates the
   platform layer.

## Prerequisites already in place

- `externals/AndroidAPS/` repo cloned and visible (build files present)
- Audition matrix has `controller` field — AAPS can be added as a
  fourth value alongside Loop/Trio/OpenAPS
- EXP-2891 schema (parquet) accepts arbitrary lineage labels
- Cf-conditioning and Default Guard #6 work for any new lineage

## Sourcing options (ranked by effort / quality)

### Option A — Existing AAPS Nightscout Open Data Set (recommended)
- AAPS users frequently publish Nightscout sites publicly via
  OpenHumans / T1D Exchange / individual sharing.
- Action items:
  1. Identify at least 8 candidate AAPS Nightscout sites with ≥6 months
     of `treatments` + `entries` + `devicestatus` collections.
  2. Verify `enteredBy` / `pump` field signatures distinguish AAPS
     (`enteredBy: "openaps://AAPS"` or `device: "openaps://AndroidAPS"`).
  3. Pull via existing Nightscout ingestion code path used for
     Loop/Trio cohort.
  4. Confirm `loop` enacted records present (AAPS uses
     `pluginType: "APS"` markers in devicestatus.openaps.suggested).
- Expected yield: 5–10 patients in 1–2 batches.
- Risks: site privacy (request explicit consent); some users disable
  Nightscout uploads of devicestatus.

### Option B — OpenHumans T1D project import
- OpenHumans hosts a "Nightscout Data Commons" stream with
  IRB-cleared longitudinal data.
- Action items:
  1. File data-use agreement / project description.
  2. Request AAPS-only subset (filter by `device` field).
  3. Standardize via existing ingestion.
- Expected yield: 20+ patients but onboarding adds calendar weeks.

### Option C — Targeted recruitment via AAPS Discord / Facebook group
- Existing relationship channels.
- Action items: drop a recruitment notice with consent form referencing
  the same data-sharing template used for Loop / Trio cohort.

### Option D — Synthetic AAPS (fallback only)
- Run AAPS in simulation mode (`androidaps-simulator` / replay engine
  in `externals/AndroidAPS/benchmark/`) on existing real meal/insulin
  patterns from current cohort.
- Generates "what-would-AAPS-do" counterfactual but **not real
  patient behavior**; useful only for algorithm-layer ablation.

## Acceptance criteria (cohort growth target)

To unblock the under-powered claims:

| Claim                                              | Min n needed |
|---------------------------------------------------|-------------:|
| oref1 algorithm vs Trio platform separation       | ≥6 AAPS+oref1 |
| Within-lineage tercile (oref0) claims             | ≥9 oref0 (any platform) |
| AAPS+autosens vs AAPS+dynISF cross-config         | ≥4 each |

Combined target: **+12 AAPS patients across mixed configs**.

## Pipeline-side prep tasks (parallel, no recruitment needed)

1. **Add `platform` field to AuditionInputs** (Loop_iOS, Trio_iOS,
   AAPS_Android, OpenAPS_RPi). Wire through audition matrix tests.
2. **Update lineage classifier** (`tools/cgmencode/.../patient_classifier.py`
   if it exists, else inline) to detect AAPS device strings:
   - `device: "openaps://AndroidAPS"`
   - `enteredBy: "AAPS"`
   - `pluginType: "APS"`
3. **Add `aaps_specific` regime to EXP-2902** classifier — if cohort
   grows beyond 25 patients the 5-regime model may want a 6th cell.
4. **Regression-test cf-conditioning code paths** (EXP-2904, EXP-2907)
   with a synthetic 4th lineage to confirm they handle ≥4 lineage
   ANCOVAs without code changes.
5. **Document `lineage_assignment.md`** as part of the deconfounding
   toolkit so AAPS additions inherit Default Guard #6 automatically.

## Audition matrix forward-looking flag stubs

Once AAPS data lands, add (deferred):
- `aaps_dynisf_active` (advisory — autosens disabled, dynISF on)
- `aaps_pluginType_mismatch` (data quality — devicestatus.openaps
  missing pluginType field)
- `aaps_platform_dose_distribution` (LOW — informational comparison
  vs Trio same-algo distribution)

## Known confounder to track in plan

If AAPS patients adopt oref1 with **dynISF enabled** (default in newer
AAPS) while Trio patients use oref1 with **autosens-only**, the
algorithm comparison conflates dynISF with platform. Need explicit
config field collection before lineage assignment.

## Connection to active research arcs

- Closes Dataset Gap #1 from EXP-2894 ("no AAPS patients")
- Strengthens EXP-2891 / EXP-2904 statistical power
- Enables EXP-2902 6-regime extension
- Provides natural validation cohort for EXP-2895/2907 night
  degradation: if AAPS+oref1 shows same +9.5pp night excess → algorithm
  signature; if AAPS+oref1 differs → platform signature

## Status

This is a **plan only**. No data ingestion performed; concurrent
verification process (Phase 3 Verification by Ben West) may overlap
with cohort additions and should be coordinated with before pulling
new data.

## Linked artefacts

- `externals/AndroidAPS/` (already cloned)
- `docs/60-research/exp-2904-cf-conditioned-lineage-2026-04-22.md`
- `docs/60-research/exp-2907-cf-stratified-tod-2026-04-23.md`
- `docs/60-research/deconfounding-toolkit-2026-04-22.md`
