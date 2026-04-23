# EXP-2902 — cohort regime stratification report

**Date:** 2026-04-22 (overnight)
**N:** 19 patients
**Source:** `tools/cgmencode/exp_regime_strata_2902.py`
**Output:** `externals/experiments/exp-2902_regimes.parquet`

## Method

Project each patient into the 2-D space (aid_protection_severe, cf_severe)
and partition into 5 regimes via thresholds (PROT_HIGH=0.65, PROT_LOW=0.35,
CF_HIGH=0.95). Decomposition follows EXP-2897:
`observed_severe = (1 − protection) × cf_severe`.

| Regime                | Definition                          | Remediation surface         |
|-----------------------|-------------------------------------|-----------------------------|
| mechanism_gap         | protection<0.35                     | algorithm migration         |
| load_saturation       | cf≥0.95 AND protection<0.65         | settings de-aggression      |
| moderate              | mid-range both axes                 | per-patient audition        |
| defended              | protection≥0.65 AND cf<0.95         | reference template          |
| over_performer_at_load| protection≥0.65 AND cf≥0.95         | best-practice candidate     |

## Cohort breakdown

| Regime                | n  | Lineages                    |
|-----------------------|---:|-----------------------------|
| load_saturation       | **8** | 6 Loop + 2 oref1         |
| moderate              | 5  | 2 Loop + 2 oref1 + 1 oref0  |
| over_performer_at_load| 3  | 3 oref1                     |
| defended              | 2  | 1 oref1 + 1 oref0           |
| mechanism_gap         | 1  | 1 oref0                     |

## Headline findings

### 42 % of cohort is load-saturated
Eight of 19 patients have `cf_severe ≥ 0.95` — every descent would reach
severe without AID. Settings are at or beyond the safe operating envelope
for these patients. Remediation surface is **settings de-aggression**,
NOT algorithm migration or mechanism upgrade.

### Loop is concentrated in load_saturation (5 of 7 Loop patients)
This re-frames EXP-2891's lineage-protection finding. Loop's lower
median protection (0.57) vs oref1's (0.63) is **not necessarily a
mechanism deficit** — Loop users in this cohort run their settings
hotter, putting cf at the ceiling more often. With cf at 1.0, even
0.65 protection (Loop's best) yields obs=0.35 severe rate.

A controlled comparison would require matching cohorts on cf_severe
distribution. Without that, lineage-protection comparisons may
conflate algorithm and behavioural intensity.

### Over-performers are exclusively oref1 (3 of 9 oref1 patients)
Three oref1 patients hit protection ≥0.70 *while* cf is at the ceiling.
This is the strongest evidence yet that oref1 mechanism (basal-cut +
SMB) *can* defend at the load ceiling — a capability not observed in
Loop or oref0 in this cohort.

### Only 1 patient is in pure mechanism_gap regime
`odc-86025410` (conservative oref0) — the previously documented
algorithm-migration case. The mechanism-gap diagnosis is rare; the
load-saturation diagnosis is common.

## Per-regime patient lists

### load_saturation (n=8)
| Patient            | Lineage | Tercile     | prot | cf   | obs  |
|--------------------|---------|-------------|-----:|-----:|-----:|
| `c`                | Loop    | aggressive  | 0.57 | 1.00 | 0.43 |
| `d`                | Loop    | conservative| 0.52 | 1.00 | 0.48 |
| `e`                | Loop    | aggressive  | 0.65 | 0.99 | 0.34 |
| `g`                | Loop    | moderate    | 0.63 | 1.00 | 0.37 |
| `i`                | Loop    | aggressive  | 0.53 | 1.00 | 0.47 |
| `ns-a9ce2317bead`  | oref1   | moderate    | 0.60 | 0.98 | 0.38 |
| `ns-adde5f4af7ca`  | oref1   | moderate    | 0.63 | 0.99 | 0.37 |
| `ns-d444c120c23a`  | oref1   | aggressive  | 0.57 | 1.00 | 0.43 |

### over_performer_at_load (n=3)
| Patient            | Lineage | Tercile     | prot | cf   | obs  |
|--------------------|---------|-------------|-----:|-----:|-----:|
| `ns-1ccae8a375b9`  | oref1   | aggressive  | 0.76 | 1.00 | 0.24 |
| `ns-6bef17b4c1ec`  | oref1   | conservative| 0.70 | 0.98 | 0.28 |
| `ns-8b3c1b50793c`  | oref1   | aggressive  | 0.79 | 1.00 | 0.21 |

### defended (n=2)
| Patient            | Lineage | Tercile     | prot | cf   | obs  |
|--------------------|---------|-------------|-----:|-----:|-----:|
| `ns-8f3527d1ee40`  | oref1   | aggressive  | 0.75 | 0.94 | 0.19 |
| `odc-74077367`     | oref0   | aggressive  | 0.72 | 0.93 | 0.21 |

## Implications

### For per-patient audition
Triage routes by regime, not just by raw protection:
- mechanism_gap → algorithm migration (or capacity audit)
- load_saturation → settings de-aggression (CR/basal pullback)
- moderate → standard per-patient audit
- defended → reference template
- over_performer_at_load → capture settings fingerprint

### For lineage-level claims
Future cross-lineage comparisons must condition on cf distribution.
EXP-2891's lineage protection effect is real but partly mediated by
load-intensity self-selection. A more rigorous claim is:
"Within over_performer_at_load and defended regimes, oref1 has more
representatives." That is a lineage-mechanism statement; the
load_saturation Loop concentration is a behavioural one.

### For AID developers (Loop in particular)
Most Loop patients in this cohort are running with `cf_severe = 1.00`.
This suggests Loop's UI/onboarding may permit/encourage aggressive
configurations more readily than oref1 platforms — or that Loop
patients adapt their behaviour to the algorithm's capabilities. Worth
investigating whether Loop's safety guardrails (max-basal, IOB clamp)
are sized correctly for users who saturate cf.

## Audition wiring proposal

Add `regime_label: Optional[str]` to AuditionInputs. Two new flags:

```python
regime_load_saturation:  severity="medium"
  rationale: "cf_severe >= 0.95 — every descent at hypo precipice;
              settings de-aggression has higher leverage than mechanism
              upgrade. Drop CR or basal ~10% to pull cf off ceiling."

regime_mechanism_gap:    severity="high"
  rationale: "protection < 0.35 — algorithm/mechanism deficit.
              Algorithm migration or capacity audit; settings tuning
              alone unlikely to close the gap."
```

Wiring deferred to EXP-2903.

## Caveats

- Thresholds (0.35, 0.65, 0.95) chosen by inspection; sensitivity
  analysis not performed. Cf=0.95 selected because the ceiling cluster
  is sharp (visible in the patient list).
- 19 patients is small for stratification into 5 cells; 1 cell has
  n=1 (mechanism_gap).
- cf_severe depends on the ISF=50 mg/dL/U replay assumption from
  EXP-2889; sensitivity analysis (EXP-2890) shows ρ stable but
  absolute cf magnitudes shift.

## Linked artefacts

- `docs/60-research/exp-2897-hourly-cf-report-2026-04-22.md`
- `docs/60-research/vignette-load-saturation-aggressive-oref1-2026-04-22.md`
- `tools/cgmencode/exp_regime_strata_2902.py`
- `externals/experiments/exp-2902_regimes.parquet`
