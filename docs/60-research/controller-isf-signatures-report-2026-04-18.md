# EXP-2668: Per-Controller Demand ISF Signatures

**Date**: 2026-04-18  
**Predecessor**: EXP-2663, EXP-2666  
**Patients**: 17  
**Data**: CGM + pump telemetry from grid.parquet

## 1. Motivation

EXP-2666 found patient i has 1132% ISF shift between 2-12h isolation, while most patients stabilize at 6h. Different AID controllers dose differently: SMB-AID fires 50-75 micro-boluses/day (short inter-bolus gaps), Loop/TBR modulates basal rates (longer clean windows). This experiment tests whether controller type creates systematic demand ISF measurement bias.

## 2. Controller Classification

![Spacing](../../visualizations/controller-isf-signatures/fig1_bolus_spacing_by_controller.png)

| Patient | Controller | Days | SMB/day | Bol/day | Median Gap (h) | >6h gaps |
|---------|-----------|------|---------|---------|---------------|----------|
| a | Loop/TBR | 180 | 0.0 | 4.9 | 1.58 | 23.9% |
| b | SMB-AID | 180 | 50.4 | 59.7 | 0.42 | 2.9% |
| c | SMB-AID | 180 | 56.5 | 57.9 | 0.17 | 4.8% |
| d | SMB-AID | 180 | 63.1 | 65.8 | 0.33 | 3.6% |
| e | SMB-AID | 158 | 72.2 | 75.2 | 0.08 | 1.5% |
| f | Loop/TBR | 180 | 0.0 | 3.0 | 3.5 | 36.5% |
| g | SMB-AID | 180 | 54.0 | 60.3 | 0.33 | 6.7% |
| h | SMB-AID | 180 | 43.5 | 46.8 | 0.96 | 12.7% |
| i | SMB-AID | 180 | 76.2 | 78.6 | 0.17 | 2.2% |
| k | SMB-AID | 179 | 58.9 | 66.9 | 0.42 | 3.0% |
| odc-39819048 | SMB-AID | 10 | 40.2 | 42.2 | 0.25 | 3.3% |
| odc-49141524 | SMB-AID | 12 | 27.2 | 28.6 | 0.08 | 5.9% |
| odc-58680324 | Loop/TBR | 11 | 0.0 | 4.3 | 1.75 | 16.3% |
| odc-61403732 | SMB-AID | 11 | 31.1 | 32.8 | 0.17 | 2.5% |
| odc-74077367 | Loop/TBR | 212 | 0.0 | 65.4 | 0.33 | 3.3% |
| odc-86025410 | Loop/TBR | 375 | 0.0 | 9.4 | 2.92 | 25.6% |
| odc-96254963 | Loop/TBR | 183 | 0.0 | 9.0 | 2.0 | 17.9% |

## 3. Isolation Sweep by Controller

![Sweep](../../visualizations/controller-isf-signatures/fig2_isf_sweep_by_controller.png)

![Stability](../../visualizations/controller-isf-signatures/fig3_isf_stability_by_controller.png)

## 4. Demand ISF by Controller Group

![Box](../../visualizations/controller-isf-signatures/fig4_isf_boxplot_by_controller.png)

## 5. Patient i Deep Dive

![Patient i](../../visualizations/controller-isf-signatures/fig5_patient_i_deep_dive.png)

Patient i (SMB-AID, 76.2 SMB/day):
- Stability range: 3.44x
- Median inter-bolus gap: 0.17h
- Gaps >6h: 2.2%

## 6. Controller Effect Summary

![Summary](../../visualizations/controller-isf-signatures/fig6_controller_effect_summary.png)

## 7. Hypothesis Results

| H | Result | Description |
|---|--------|-------------|
| H1 | SKIP | Demand ISF differs by controller type (ANOVA/KW p<0.05) |
| H2 | SKIP | Optimal isolation window differs by controller |
| H3 | **PASS** | Patient i shift explained by SMB-AID bolus spacing |
| H4 | **PASS** | Loop/TBR has more isolated corrections/day than SMB-AID |
| H5 | **PASS** | Within-controller ISF CV < overall CV |

## 8. Clinical Implications

1. **Controller-aware calibration**: ISF measurement depends on dosing pattern
2. **Isolation window selection**: SMB-AID patients may need shorter windows (2-4h) with lax filtering
3. **Cross-device portability**: switching controllers may shift measured ISF
4. **Patient i**: specific controller signature, not physiological outlier
