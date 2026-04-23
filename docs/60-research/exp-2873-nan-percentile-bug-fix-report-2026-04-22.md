# EXP-2873 — NaN-percentile bug fix overturns Loop "zero variation" finding (2026-04-22)

## Headline

A `np.percentile` propagating NaN bug in `aggregate_windows()` silently
excluded patients with high glucose-NaN cell rates from EXP-2851 (and
therefore EXP-2870/2871/2872). Fixing the bug:

- Cohort grew from **25 → 31** patients (added: c, d, b, p, ns-...)
- **Loop is NOT zero-variation**: 7 stream_B_early + 1 stream_B_normal
  (previously reported as 0 + 6 stream_B_normal)
- Trio largely unchanged (5/5 stream_A_dominant in both runs)

This invalidates the EXP-2870 "controller signature" cross-tab and
the EXP-2872 Simpson-paradox numbers as published.

## The bug

```python
# EXP-2851 aggregate_windows: glucose mean carries NaN for sparse windows
agg = g_pat.groupby("window_id").agg(
    n=("glucose", "size"),                # counts all rows, NaN included
    glucose=("glucose", "mean"),          # NaN-resistant, but produces NaN
                                          #   for fully-NaN windows
    actual_basal=("actual_basal_rate","mean"),
)
agg = agg[agg["n"] >= cells * 0.8]        # filter on row count, not non-NaN

# Later in per_patient_signal:
q33, q67 = np.percentile(agg["glucose"], [33, 67])  # NaN propagates → both NaN
elev = agg[agg["glucose"] >= q67]   # both empty
norm = agg[agg["glucose"] <= q33]
if len(elev) < 3 or len(norm) < 3: return None  # silently skipped
```

Patient C: 51,841 cells, 42,859 non-null glucose (83% coverage),
qualifies on ALL windows after dropna — but produced no rows in
EXP-2851 because `np.percentile` returned NaN whenever any qualifying
window had a fully-NaN glucose mean.

Fix: `agg.dropna(subset=["glucose", "actual_basal"])` before percentile.

## New phenotype × controller cross-tabs

### Baseline (fill_frac=0.8, min_windows=6, min_tertile=3) — N=31

| Phenotype | Loop | OpenAPS | Trio | unknown |
|---|--:|--:|--:|--:|
| stream_A_dominant | 0 | 1 | **5** | 1 |
| stream_B_early | **7** | 4 | 4 | 6 |
| stream_B_late | 0 | 0 | 0 | 1 |
| stream_B_normal | 1 | 0 | 0 | 1 |

### Relaxed (fill_frac=0.6, min_windows=4, min_tertile=2) — N=31

Identical to baseline. Relaxation does not unlock additional patients
once the NaN bug is fixed.

## Re-interpretation

**Old (buggy) story**: "Loop produces a single envelope-coupling
signature (all stream_B_normal). This is an algorithmic uniformity."

**New story**: Loop is a **stream_B_early dominant** controller (7/8).
The envelope-coupling sign flip (negative→positive) happens **earlier**
under Loop than under Trio — consistent with a more passive/PID-style
basal that lets the envelope-demand signal emerge by 6h. Trio's
SMB-driven aggressive intervention sustains negative coupling longer
(stream_A_dominant 5/8).

This is the **opposite mechanistic interpretation** from the EXP-2871
report, but it is internally consistent with the EXP-2871 Loop
"hypo-prevention bias" mechanism — Loop suspends FAST on demand drops,
which means at long windows the basal AVERAGE tracks demand more
closely (higher elev avg vs norm avg) → positive shift earlier.

## Required follow-up actions

1. **EXP-2851** — patch `aggregate_windows` with dropna; rerun;
   addendum to `exp-2851-fast-scale-envelope-report-2026-04-22.md`.
2. **EXP-2870** — rerun with patched EXP-2851 input; update
   `exp-2870-envelope-crossover-report-2026-04-22.md`. Old "controller
   signature" framing must be revised — the signature is real but
   different from reported.
3. **EXP-2871** — rerun suspension-polarity with new patient set;
   re-test Loop-vs-Trio inverted polarity claim.
4. **EXP-2872** — rerun Simpson decomposition with new TIR cohort
   (now includes c, d, b, p with their TIR values).
5. **Vignette Patient C** — C now qualifies for envelope analysis.
   Add envelope phenotype to the section 1b state-basal facts.
6. **State-basal sparse loader** — re-check coverage after fix; may
   need to re-evaluate the MIN_BASAL_N=20 floor.

## Caveats

- The bug only affected envelope-coupling experiments
  (EXP-2849/2851/2870/2871/2872). EXP-2811/2812/state-decoupling
  used different aggregation pipelines and are unaffected.
- The settings-extraction experiments (EXP-2740s, 2750s) used
  per-event aggregation, not windowed; also unaffected.
- This is a CLASS of bug (NaN propagation through `np.percentile`/
  `np.quantile`). Search remainder of codebase for similar patterns.

## Artifacts

- `externals/experiments/exp-2873_relaxed_envelope.parquet`
- `externals/experiments/exp-2873_summary.json`
- `docs/60-research/figures/exp-2873_loop_variation.png`

## Verdict

EXP-2873 set out to test a hypothesis (Loop algorithmic uniformity)
and instead discovered that the hypothesis was based on **a coverage
artifact, not data**. This is a successful experiment: it revealed a
critical bug, produced a new (and richer) phenotype distribution, and
queues 5 follow-on reruns.
