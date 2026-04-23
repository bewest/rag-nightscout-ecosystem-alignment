# EXP-2870 — Per-patient envelope crossover phenotype (2026-04-22)

## Question
EXP-2851 found that the envelope→basal coupling sign FLIPS between
12h and 24h cohort-wide. Per-patient, where does each patient's
crossover happen — and does it predict therapy quality?

## Method
For each patient, find the smallest window where envelope shift ≥ 0.
Classify:

| Phenotype | Definition |
|---|---|
| stream_A_dominant | Never crosses (always negative — reactive loop dominates all scales) |
| stream_B_early | Crosses by 6h |
| stream_B_normal | Crosses by 24h |
| stream_B_late | Crosses only at 48h |

## Results — N=25 patients

| Phenotype | N | Median TIR | Median sched basal | Loop | OpenAPS | Trio |
|---|--:|---:|---:|--:|--:|--:|
| stream_A_dominant | 7 | **0.82** | 0.85 | 0 | 2 | 5 |
| stream_B_early | 5 | 0.77 | 0.95 | 0 | 1 | 2 |
| stream_B_normal | 12 | **0.67** | **0.58** | 6 | 2 | 1 |
| stream_B_late | 1 | 0.90 | 1.40 | 0 | 0 | 1 |

## Headline (counter-hypothesis)

**Hypothesis (wrong)**: stream_A_dominant patients have controller
suspending so much it indicates over-tuned settings → lower TIR.

**Finding**: stream_A_dominant patients have the **highest TIR** in
the cohort (82% vs 67% for stream_B_normal). All 6 Loop patients are
stream_B_normal; all 7 stream_A_dominant patients run Trio/OpenAPS.

## Interpretation — phenotype is a **controller signature**

- **Trio / OpenAPS (stream_A_dominant)**: SMB / UAM / dynamic ISF
  drive tactical basal modulation at *every* timescale. Controller
  is constantly compensating; envelope shift stays negative because
  reactive intervention dominates short-window variance. Higher TIR.

- **Loop (stream_B_normal)**: simpler temp-basal modulation. At
  short scales, controller suspends during highs (negative shift).
  At long scales (24-48h), basal shift turns *positive* — meaning
  the schedule itself is being delivered higher in elevated-envelope
  windows. This is the **scheduled-basal-too-high** signal that
  shows up in the audition matrix (cf. patient C). Lower TIR.

- The crossover hour is therefore **NOT** a single-axis quality
  marker — it's encoding controller architecture. Within Loop, the
  crossover happens around 24h regardless of TIR; within Trio/OpenAPS,
  the controller suppresses the crossover entirely.

## Implications

1. **Audition window choice should be controller-aware.** For Loop
   patients, the 48h envelope signal is meaningful. For Trio/OpenAPS
   patients, even 48h envelope shifts are dominated by reactive
   intervention — the audition needs additional Stream-B isolation
   (e.g., subtract intervention-attributable basal first).

2. **Patient-comparison fairness**: comparing basal_shift across
   controllers is comparing apples to oranges. Within-controller
   normalization is required.

3. **The patient-C "scheduled basal too high" interpretation
   strengthens**: she's stream_B_normal Loop-archetype with TIR 51%.
   Of 12 stream_B_normal patients, she's at the bottom of the TIR
   distribution.

4. **Trio's tactical machinery looks effective at glycemic control
   in this cohort** (median TIR 82% vs Loop 67%) BUT the sample is
   small (7 vs 6) and unblinded to selection. Cannot generalize.

## Caveats
- N=25 (only patients with enough contiguous data for 6+ non-
  overlapping 1-48h windows).
- TIR is an outcome and may correlate with phenotype via patient
  motivation / engagement, not controller architecture.
- `stream_B_late` has N=1 — single-patient noise.
- Not deconfounded for time-of-day or meal-event clustering.

## Checks: 2/3 PASS
- ✅ Phenotype diverse (4 phenotypes observed)
- ✅ stream_A is minority (7/25)
- ❌ stream_A lower TIR (FAILED — actually HIGHER TIR; hypothesis
  was wrong, but the inversion is the finding)

## Artifacts
- `externals/experiments/exp-2870_per_patient_crossover.parquet`
- `externals/experiments/exp-2870_summary.json`
- `docs/60-research/figures/exp-2870_crossover_phenotype.png`

## Follow-ups
- EXP-2871: within-controller crossover analysis (subtract
  intervention-attributable basal before re-computing).
- EXP-2872: does crossover phenotype change after meal_filter
  gating? (Stream A signal may shrink when phantom-carb noise is
  removed.)
- Vignette enhancement: add per-patient crossover hour as
  diagnostic in the basal-mismatch section.

---

## Addendum 2026-04-22: NaN-percentile bug fix (EXP-2873)

EXP-2851 input was patched (NaN-propagation in `np.percentile`). New
crossover phenotype distribution (N=31):

| Phenotype | Loop | OpenAPS | Trio | unknown |
|---|--:|--:|--:|--:|
| stream_A_dominant | 0 | 1 | **5** | 1 |
| stream_B_early | **7** | 4 | 4 | 6 |
| stream_B_late | 0 | 0 | 0 | 1 |
| stream_B_normal | **1** | 0 | 0 | 1 |

**Old "Loop = uniform stream_B_normal" finding is INVALIDATED**.
Loop is actually 7/8 stream_B_early + 1 stream_B_normal. The
controller signature is real but takes a different form: Loop crosses
to positive shift FAST (1-6h), Trio sustains negative shift (5/9
stream_A_dominant). The mechanism is consistent with EXP-2871
(Loop hypo-prevention; Trio SMB-driven aggressive intervention)
but the phenotype-level summary needs the EXP-2872 Simpson reanalysis.

Phenotype × TIR (revised):

| Phenotype | n | median TIR |
|---|--:|--:|
| stream_A_dominant | 7 | 0.82 |
| stream_B_late | 1 | 0.90 |
| stream_B_normal | 2 | 0.72 |
| stream_B_early | 21 | 0.67 |
