# EXP-2965 — Per-patient validation of EXP-2961 sustained-high finding (2026-04-23)

## Scope
For open-source AID code authors. Tests whether the pooled
Loop_AB_ON +2.05 vs oref1 +0.98 sustained-high velocity-coupling
ordering reported by EXP-2961 holds per-patient (replicating the
EXP-2962 lesson), and decomposes the per-patient slope into
SMB-only and basal-only channels (per the EXP-2964 lesson).

## What this is NOT
Not per-patient therapy advice. Not a controller endorsement. Not
a within-patient dose-response claim — we measure population-level
velocity-coupling slopes only.

## Method
Sustained-high entry: BG crosses above 200 mg/dL with no carbs in
prior 120 min and no overlapping window (≥60 min spacing). For each
qualifying entry index `i`:

- `vel_30 = OLS slope of bg[i..i+6] vs minutes` (mg/dL per min)
- `ins_60_total = sum(bolus + bolus_smb + max(actual−scheduled, 0)·5/60)` over `[i, i+12)`
- Component channels: `ins_60_smb`, `ins_60_basal_excess`,
  `ins_60_bolus` (manual user bolus only)

For each patient with ≥15 events, fit individual `slope_X ~ vel_30`
per channel. Per-design summary: median, mean, sign-test, MWU
between Loop_AB_ON and oref1.

## Results

**Sustained-high events:** 3,375 across 19 qualifying patients.

### Per-patient SMB-channel slope (sustained-high)

| Design | n_pat | median | mean | (+/−) | sign-test p |
|---|---:|---:|---:|---|---:|
| Loop_AB_ON | 5 | +0.598 | +0.588 | 5+/0− | 0.0625 |
| oref1 | 9 | +0.386 | +0.410 | 9+/0− | **0.00391** |
| Loop_AB_OFF | 2 | +0.000 | +0.000 | (no SMB) | — |
| oref0 | 3 | +0.000 | +0.000 | (no SMB) | — |

### Per-patient TOTAL slope (sustained-high)

| Design | n_pat | median | mean | (+/−) | sign-test p |
|---|---:|---:|---:|---|---:|
| Loop_AB_ON | 5 | +1.753 | +1.556 | 5+/0− | 0.0625 |
| oref1 | 9 | +1.338 | +1.239 | 9+/0− | **0.00391** |
| oref0 | 3 | +0.024 | +0.195 | 2+/1− | 1.0 |

### MWU Loop_AB_ON > oref1 (one-sided)

| Channel | U | p |
|---|---:|---:|
| total | 30.0 | 0.182 |
| smb | 31.0 | **0.149** |
| basal_x | 23.0 | 0.500 |
| bolus | 28.0 | 0.259 |

## Interpretation

**MIXED.** Two simultaneous facts:

1. **Both designs show a unanimously positive sustained-high
   velocity-coupling per-patient.** oref1 sign-test p=0.0039 (9/9
   positive); Loop_AB_ON 5/5 positive (sign-test p=0.0625, max
   significance attainable at n=5). Sustained-high coupling is a
   robust property of every SMB-equipped patient in the cohort.

2. **Per-patient MWU between designs is NOT significant** (p=0.149
   for SMB channel, p=0.182 for total). The directional ordering
   (Loop_AB_ON median +0.598 > oref1 median +0.386) is consistent
   with EXP-2961's pooled +2.05 > +0.98 but is underpowered
   (n_pat = 5 vs 9, top-of-distribution oref1 patients overlap
   Loop_AB_ON's range).

3. **EXP-2962 lesson re-confirmed at sustained-high.** The pooled
   between-design ratio in EXP-2961 should not be read as a
   per-patient design effect. Replicate exactly the EXP-2962
   correction: within-design positivity is robust, between-design
   ordering is directional but not per-patient significant.

4. **oref0 has zero coupling at sustained-high** (median +0.024,
   2+/1− signs), confirming the controller is BG-reactive only
   (no velocity term in CR/IOB/ISF combination at this BG range).

5. **The Loop_AB_ON SMB-channel directional excess** (+0.60 vs +0.39
   median) is consistent with — but does not prove — a more
   aggressive SMB triggering at sustained-high than oref1's. EXP-2970
   exposes the underlying mean-dose difference (Loop ~2.06 U SMB vs
   oref1 ~1.26 U mean at sustained-high entry).

## Files
- Script: `tools/cgmencode/exp_per_patient_sustained_high_2965.py`
- JSON: `externals/experiments/exp-2965_summary.json`

## Provenance
- Cohort: `externals/experiments/exp-2891_simpson_dose_response.parquet`
- Grid: `externals/ns-parquet/training/grid.parquet`
- Repo HEAD: 15b0d75
- Date: 2026-04-23

## Next
- EXP-2966 — BG-band sweep already in this batch quantifies the
  sustained-high coupling across a finer grid.
- Future: pre-register a directional MWU test on a held-out cohort
  (n_pat ≥ 15 per design) to power the +0.60 vs +0.39 directional
  excess to p < 0.05.
