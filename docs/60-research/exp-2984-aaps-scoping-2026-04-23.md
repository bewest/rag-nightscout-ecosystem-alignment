# EXP-2984 — AAPS ingestion scoping (marker)

**Date**: 2026-04-23
**Audience**: Open-source AID code authors
**Scope**: Marker entry. The substantive output is the pipeline
document at
`docs/40-data-pipelines/aaps-ingestion-scoping-2026-04-23.md`.
**What this is NOT**: a data analysis. No new parquet output.

## Result — DIAGNOSIS: data-LABELING gap (not data-collection)

EXP-2980 surfaced "no AAPS in cohort." Closer inspection of the
ingestion pipeline shows AAPS-native uploads **are present** in
the underlying ODC corpus and reach the parquet store via
`tools/ns2parquet/odc_loader.py`, but every synthesized record
is stamped `device='openaps://AndroidAPS'` (lines 105, 145, 175,
208, 224, 252, 295). The downstream
`_detect_controller()` in `tools/ns2parquet/normalize.py:87-100`
tests `'openaps' in dl` *before* `'aaps' in dl`, so all 7 odc-*
patients get tagged `controller='openaps'` and (where eligible
for the Simpson cohort) `lineage='oref0 (legacy)'`.

**Implication**: 3 of the 9 patients currently labeled
"oref0 (legacy)" in the EXP-2891 cohort are likely AAPS-Android
uploads. Prior "oref0 vs oref1" comparisons in this workspace
may silently include misclassified AAPS data.

## Remediation outline (full detail in pipeline doc)

1. Reorder `_detect_controller` so AAPS is matched first.
2. Replace synthesized `openaps://AndroidAPS` device string with
   `androidaps://odc` (root-cause fix).
3. Add `tools/relabel_aaps.py` to re-tag the existing parquet
   without a full rebuild.
4. Re-run EXP-2891 → regenerate cohort with AAPS as a stratum.
5. Re-run EXP-2980 (Trio vs AAPS platform isolation) with the
   newly-isolated AAPS arm.

## Verdict

**POSITIVE / ACTIONABLE**: the Trio-vs-AAPS comparison is **not**
blocked by data collection. It is blocked by a 2-line fix in
`_detect_controller` plus a one-time relabel pass. The cohort
likely already contains AAPS data mis-labeled as oref0.

## Source / pipeline doc
- `docs/40-data-pipelines/aaps-ingestion-scoping-2026-04-23.md`
- `tools/ns2parquet/normalize.py:87-100`
- `tools/ns2parquet/odc_loader.py` (multiple `'openaps://AndroidAPS'` stamps)
