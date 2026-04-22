# EXP-2864: Bootstrap-Confidence Post-High Envelope (2026-04-22)

## Hypothesis

The naive `post_high_mg_dl > 25` audition flag (computed as
`median(post_mean_bg) − 110`) may be unreliable for some patients with
few post-transition windows. A per-patient event bootstrap quantifies
P(envelope > 25 mg/dL) over `N=500` resamples and gates audition output
in three tiers (high ≥0.9 / boundary 0.1–0.9 / suppress <0.1).

## Method

* Source: `externals/experiments/exp-2812_pre_post_transitions.parquet`
  (`post_mean_bg` column, post-S0→S1 windows).
* Per patient with ≥ 5 transitions, resample with replacement
  N=500 times; compute median(post_mean_bg − 110) per replicate.
* Threshold: 25 mg/dL above target (110).

## Result — opposite of EXP-2863

| Metric | Value |
|--------|-------|
| Patients (≥5 transitions) | 16 |
| Bootstrap `confident_high` (P≥0.9) | **16 / 16 (100%)** |
| Bootstrap `uncertain` | 0 / 16 |
| Bootstrap `confident_in_target` | 0 / 16 |
| Naive `>25` count | 16 / 16 (100%) |
| Median CI width (mg/dL) | 12.2 |
| Median n_transitions | 16 |

**Every patient unambiguously exceeds the 25 mg/dL post-transition
envelope** — the naive flag survives bootstrap for the entire cohort.
This signal is the most robust of the five audition signals tested.

## Productionization

* `AuditionInputs.p_post_high_envelope` field added.
* `classify_triage_flags` now branches on the bootstrap probability
  before falling back to the naive `post_high_mg_dl > 25` rule.
* Severity gating: P≥0.9 → MEDIUM; 0.1≤P<0.9 → LOW (boundary);
  P<0.1 → suppress.
* `PostHighFactsLoader` exposes per-patient `p_post_high_envelope`
  from the EXP-2864 parquet.
* Tests: 4 audition-matrix branches + 4 loader tests (37 total in
  audition + post-high suite).

## Cross-signal bootstrap reliability summary (5/5 audition signals)

| EXP | Signal | % demoted to "uncertain" | Naive flag reliability |
|-----|--------|--------------------------|-----------------------|
| 2859 | Simpson paradox | 12/26 (46%) | mixed |
| 2861 | ISF gap | 5/16 (31%) | moderate |
| 2862 | Recovery fraction | 5/16 (31%) | moderate |
| 2863 | Wear / site degradation | 10/10 (100%) | **noise** |
| 2864 | Post-high envelope | 0/16 (0%) | **rock solid** |

The audition triage system is now bootstrap-gated across all five
naive-threshold signals. The post-high envelope is the *only* signal
where the naive rule survives bootstrap intact, validating it as a
universal triage trigger; the wear signal at the other extreme should
not be used as a single-event classifier.

## Artifacts

* `externals/experiments/exp-2864_bootstrap_post_high.parquet`
* `externals/experiments/exp-2864_summary.json`
* `docs/60-research/figures/exp-2864_bootstrap_post_high.png`
* `tools/cgmencode/exp_bootstrap_post_high_2864.py`
* `tools/cgmencode/production/post_high_facts_loader.py`
* `tools/cgmencode/production/test_post_high_facts_loader.py`
* Updates to `audition_matrix.py` and `test_audition_matrix.py`
