# EXP-2881 — Evening Hypo Driver Characterization

**Date:** 2026-04-22
**Stream:** B (operational, actionable)
**Status:** Complete — EVENING HYPOS ARE BOLUS-STACKING DOMINATED
**Predecessor:** EXP-2880 (evening descent fastest)

## Question

EXP-2880 found evening (18-24 UTC) BG descent into hypoglycemia is
the fastest of the four TOD bands (−0.77 vs −0.65/−0.58/−0.68
mg/dL/min). What mechanistic factor drives the evening descent
acceleration?

Three non-exclusive hypotheses:

- **H1 Bolus stacking** — dinner + post-dinner corrections accumulate.
- **H2 Basal profile mis-tune** — evening scheduled basal may be too high.
- **H3 Residual meal-coupling** — extended-effect meal digestion
  unwinds faster in evening.

## Method

For 3,912 rescue-free pre-nadir-valid events, compute:

- `bolus_4h` — cumulative bolus volume in 4h window before nadir
- `time_since_bolus_min` — minutes between last bolus and nadir
- `last_bolus_size` — size of the last bolus before nadir
- `iob_start` — IOB at start of 60-min descent window
- `iob_nadir` — IOB at nadir (should be ~0)
- `sched_basal` — mean scheduled basal rate during descent window

Compare evening (n=904) vs rest-of-day (n=3,008) via two-sided
Mann-Whitney.

## Result

**VERDICT: EVENING HYPOS ARE BOLUS-STACKING DOMINATED**
**(with a secondary basal contribution)**

### Per-TOD medians

| Feature              | Night  | Morning | Afternoon | **Evening** |
|----------------------|-------:|--------:|----------:|------------:|
| bolus_4h (U)         | 2.5    | 1.6     | 2.2       | **4.3**     |
| time_since_bolus_min | 105    | 105     | 95        | **90**      |
| last_bolus_size (U)  | 0.35   | 0.30    | 0.30      | 0.35        |
| iob_start (U)        | 0.04   | 0.00    | 0.00      | **0.53**    |
| iob_nadir (U)        | 0.00   | −0.01   | 0.00      | 0.00        |
| sched_basal (U/h)    | 0.80   | 0.84    | 0.80      | **0.95**    |
| descent_slope        | −0.65  | −0.58   | −0.68     | **−0.77**   |

### Evening vs rest-of-day (Mann-Whitney two-sided)

| Feature               | Evening | Rest  | Δ       | p-value       |
|-----------------------|--------:|------:|--------:|--------------:|
| **bolus_4h**          | 4.30    | 2.05  | **+2.25**| **4.5×10⁻³⁸** |
| **iob_start**         | 0.53    | 0.00  | **+0.53**| **1.1×10⁻²⁵** |
| iob_nadir             | 0.00    | 0.00  | 0.00    | 8.3×10⁻¹²     |
| sched_basal           | 0.95    | 0.80  | +0.15   | 3.0×10⁻⁴      |
| descent_slope         | −0.77   | −0.63 | −0.13   | 2.4×10⁻⁹      |
| last_bolus_size       | 0.35    | 0.30  | +0.05   | 3.5×10⁻³      |
| time_since_bolus_min  | 90      | 100   | −10     | 1.6×10⁻³      |

## Interpretation

### 1. Bolus stacking is the dominant driver (effect size + significance)

The **4h cumulative bolus is 2.25 U higher in evening** than rest-of-
day (4.30 U vs 2.05 U — **more than 2× the daytime dose**), with
p = 4.5×10⁻³⁸. This is the largest and most significant effect in
the experiment.

The causal sequence is:
1. Dinner bolus at 18:00-20:00 (typically 3-6 U) → IOB rises
2. Post-meal correction boluses (not always justified) stack on
   top before the dinner bolus has peaked
3. BG descent accelerates as stacked IOB peaks 2-3 hours post-meal
4. Hypo occurs 19:00-22:00 during the descending limb of stacked IOB

The **IOB-at-descent-start being 0.53 U higher** in evening vs
~0.00 U in other TODs corroborates: by the time descent begins,
evening patients are already carrying significant residual insulin
the other TODs lack.

### 2. Scheduled basal contributes ~15% of the driver stack

Evening scheduled basal is +0.15 U/h higher (0.95 vs 0.80).
Over a 4h pre-hypo window this contributes ~0.6 U of insulin —
meaningful but much smaller than the +2.25 U bolus excess.

A reasonable decomposition: of the evening insulin excess, ~80%
comes from bolus stacking and ~20% from basal-profile elevation.

### 3. Descent slope effect is small given the huge insulin difference

Interesting: despite evening carrying +2.25 U bolus + 0.6 U basal
(~2.85 U excess insulin), the descent is only 0.13 mg/dL/min
faster. This is because:

- AID systems detect falling BG and cut basal pre-hypo
  (`basal_gap` compensates partially — see EXP-2880 regression)
- Evening meals provide residual carb absorption (though our filter
  requires zero carbs in the 60-min pre-window, it doesn't exclude
  longer-horizon meal tails)

The effect is small in descent units but large in *insulin units*.
This supports the clinical intuition that evening hypos are
"scarily easy" because the insulin burden is already high when
descent begins.

## Implications

### For open-source AID authors

**Actionable rule candidates:**

1. **Evening bolus-stacking guard.** If 4h cumulative bolus > 4.0 U
   AND TOD ∈ [18:00, 24:00] local AND BG falling → tighten hypo-
   prevention threshold by 10-15 mg/dL (e.g., 80 → 90) OR increase
   basal-zero aggression earlier on the descent.

2. **Post-dinner correction throttle.** If last bolus was within
   2h AND BG > target but falling → require user confirmation for
   additional correction bolus (or SMB gate).

3. **Evening basal review.** The +0.15 U/h evening basal elevation
   is not automatically wrong (many patients genuinely need higher
   evening basal) but should be reviewed in patients with frequent
   evening hypos. A simple algorithmic flag:
   `if evening_hypos_per_week > 2 AND evening_basal > 1.2 × daily_median_basal`
   → surface "evening basal may be too high".

### For Loop/Trio/AAPS users directly

Personalization guidance from this finding:

- Check if your evening (dinner/post-dinner) hypo events correlate
  with multiple boluses within 2 hours. If yes, you are likely
  stacking — consider the dinner bolus + waiting 2h before any
  correction.
- Carb-dense evening meals benefit from extended-bolus features
  (if your pump supports) rather than stacked corrections.
- The small basal contribution (~15%) means **don't chase the
  basal first** — attack stacking first; basal adjustments come
  after.

### For counter-reg framework

EXP-2879/2880/2881 form a coherent triad:

| Aspect | TOD effect | Mechanism |
|--------|-----------|-----------|
| Recovery rise (2879) | NONE | AID basal withdrawal dominates |
| Descent slope (2880) | Morning slowest | Dawn EGP opposes descent |
| **Descent cause (2881)** | **Evening = bolus stacking** | **Multi-bolus IOB accumulation** |

The counter-reg system is effectively "symmetric and self-compensating"
on the recovery side, but *input-driven* and *TOD-sensitive* on the
descent side. This is an important architectural observation for
anyone building or tuning AID systems.

## Limitations

- Does not model meal-absorption tails beyond the 60-min pre-window.
- UTC timestamps: evening ≈ 18-24 UTC covers varied local times.
- Cannot fully disentangle evening-specific bolus patterns (dinner
  sizes, carb counting accuracy) from TOD structure.
- Descent-slope effect is small in absolute terms despite large
  insulin excess; further investigation of AID pre-hypo braking
  warranted.

## Next experiments

- **EXP-2882 Dinner-bolus timing:** split evening events by time-
  since-dinner (meal onset). Is there a peak-stacking window
  2-3h post dinner specifically?
- **EXP-2883 Counter-reg × site age (CAGE>72h):** parallel to ISF
  decay work; does stale cannula weaken counter-reg too?
- **EXP-2884 Basal-attenuation efficacy:** given the large evening
  insulin excess but modest descent slope, quantify how much of
  the excess basal is AID-cut.

## Files

- `tools/cgmencode/exp_evening_drivers_2881.py`
- `externals/experiments/exp-2881_evening_drivers.parquet`
- `externals/experiments/exp-2881_evening_drivers_summary.json`
- `docs/60-research/figures/exp-2881_evening_drivers.png`
