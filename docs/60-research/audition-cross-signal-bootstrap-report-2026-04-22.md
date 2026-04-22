# Audition Cross-Signal Bootstrap Reliability Report (2026-04-22)

## Purpose

Synthesizes EXP-2859, 2861, 2862, 2863, and 2864 — the five
bootstrap-confidence experiments that gate the naive-threshold audition
signals in `production/audition_matrix.py`. Quantifies how often each
naive flag survives a per-patient resampling test, and tracks how
patient `b` (the prior canonical "triple-flag" archetype) is reclassified
under the new evidence.

## Naive vs bootstrap, all five signals

| EXP | Signal | Source experiment | N patients | Naive HIGH | Bootstrap `confident_high` (P≥0.9) | Demoted to `uncertain` |
|-----|--------|-------------------|-----------:|-----------:|-----------------------------------:|-----------------------:|
| 2859 | Simpson paradox | exp-2853 / 2856 | 26 | 9 | 5 | 12 (46%) |
| 2861 | ISF under-correction gap | exp-2847 | 16 | varies | varies | 5 (31%) |
| 2862 | Low recovery fraction | exp-2812 | 16 | varies | varies | 5 (31%) |
| 2863 | Wear / site degradation | grid + EXP-2831 filter | 10 | 4 | 0 | **10 (100%)** |
| 2864 | Post-high envelope | exp-2812 (post_mean_bg) | 16 | 16 | **16** | 0 |

### Headline reliability ranking (most → least trustworthy as single-event triggers)

1. **Post-high envelope** — naive flag survives 100% of the time;
   tightest CI (≈12 mg/dL); use as default triage trigger.
2. **Simpson paradox** — about half survive; route through bootstrap.
3. **ISF under-correction gap** — about two-thirds survive; route
   through bootstrap.
4. **Low recovery fraction** — about two-thirds survive; route through
   bootstrap.
5. **Wear / site degradation** — *no* patient survives bootstrap with
   the current event count (median CI width 107 pp). Do not use as a
   single-window classifier; aggregate over many wear cycles or treat
   as a pure visualization signal until N grows.

## Patient `b` reclassification chain

Patient `b` was the canonical "triple-flag" archetype before bootstrap
gating. Under the bootstrap evidence:

| Signal | Before (naive) | After (bootstrap) | Notes |
|--------|----------------|-------------------|-------|
| Simpson | HIGH | boundary | Bootstrap CI straddles threshold. |
| ISF under-correction gap | HIGH | boundary (P≈0.63) | Boundary band — provisional. |
| Low recovery fraction | HIGH | **HIGH (P=1.00)** | Strongest possible bootstrap evidence. |
| Wear / site degradation | HIGH | uncertain | Single-cycle signal, insufficient events. |
| Post-high envelope | HIGH | **HIGH (P≥0.9)** | Universal — every patient hits this. |

Net: patient `b` is **no longer a triple-flag triage candidate**. The
only signal-specific evidence is **low recovery**; the post-high envelope
is universal across the cohort and so does not differentiate `b`.
Operational read: investigate patient `b` for recovery dynamics first;
treat the prior wear and ISF-gap flags as unconfirmed.

## Production architecture (now uniform across signals)

For each of the 5 signals:

1. A research experiment writes per-patient bootstrap probabilities
   (`p_*`) to a parquet under `externals/experiments/`.
2. A `*_FactsLoader` in `tools/cgmencode/production/` exposes a
   `lookup(patient_id) → dataclass` mapping (returns all-None for
   unknown patients so callers fall through to the naive branch).
3. `AuditionInputs` carries the optional `p_*` field.
4. `classify_triage_flags` uses the bootstrap branch first; on
   `p ≥ 0.9` emits MEDIUM/HIGH severity, on `0.1 ≤ p < 0.9` emits LOW
   severity ("boundary"), on `p < 0.1` suppresses; only when `p_*` is
   `None` does the naive branch run.
5. `test_audition_matrix.py` covers all 4 transitions per signal
   (high / boundary / suppress / takes-precedence-over-naive).

## Operational implications

* **Triage reordering.** The audition triage list now requires
  per-signal bootstrap evidence, not a single naive threshold crossing.
  Most prior "triple-flag" patients are likely to drop in confidence;
  a clinician scanning the list should now prioritize `p_low_recovery`,
  `p_post_high_envelope`, and Simpson stability over wear or ISF gaps.
* **Universality vs specificity.** `p_post_high_envelope ≥ 0.9` is
  universal, so it confirms a genuine envelope problem cohort-wide but
  is *not useful for ranking* among patients. Use the *magnitude* (CI
  midpoint) when patient-comparison ranking is needed.
* **Wear signal is currently inert** as an audition trigger; we either
  need many more wear cycles per patient or to switch to within-patient
  longitudinal trend tests rather than fresh-vs-aged contrasts.

## Artifacts

* `tools/cgmencode/exp_bootstrap_simpson_2859.py` (and report)
* `tools/cgmencode/exp_bootstrap_isf_gap_2861.py` (and report)
* `tools/cgmencode/exp_bootstrap_recovery_2862.py` (and report)
* `tools/cgmencode/exp_bootstrap_wear_2863.py` (and report)
* `tools/cgmencode/exp_bootstrap_post_high_2864.py` (and report)
* `tools/cgmencode/production/audition_matrix.py` — gated branches
* `tools/cgmencode/production/{simpson,isf_gap,recovery,wear,post_high}_facts_loader.py`
