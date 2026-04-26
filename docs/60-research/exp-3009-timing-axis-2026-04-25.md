# EXP-3009 — SMB-timing-axis cf-replay (2026-04-25)

**Branch**: `autoresearch/2026-04-24-cf-replay`
**Code**: `tools/cgmencode/autoresearch_cf/exp_3009_timing_axis.py`
**Inputs**: `externals/experiments/exp-3007_ascent_events.parquet`

## Hypothesis (motivated by EXP-3008)
EXP-3008 found Loop's overshoot rate is essentially PK-bounded for the *magnitude* axis. The remaining lever is **timing**: fire the same SMB units earlier in the ascent so the oref0 PK kernel has more time to act on the peak.

## Method
For each ascent event, evaluate the kernel as if `smb_during` were delivered T minutes earlier than its actual midpoint. `cf_peak = bg_peak − (kernel(half+T) − kernel(half)) · smb_during · isf`. Sweep T ∈ {0, 5, 10, 15, 20, 30} min (capped at `duration_min`).

Total insulin units are unchanged → ascent timing axis has **no hypo penalty over DIA** (clean lever).

## Results

| Controller | obs over | cand@5min | cand@15min | cand@30min | Δ@30min | slope |
|---|---:|---:|---:|---:|---:|---:|
| **Loop**    | 60.0% | 59.1% | 57.8% | **55.0%** | **−5.0 pp** | −0.16 pp/min |
| **Trio**    | 39.8% | 38.6% | 36.3% | **33.1%** | **−6.7 pp** | −0.22 pp/min |
| OpenAPS | 51.6% | 51.5% | 51.5% | 51.5% | −0.09 pp | −0.003 pp/min |

## Headline finding

**Timing is a stronger lever than magnitude for both Loop and Trio.**

| Lever | Loop reduction | Trio reduction |
|---|---:|---:|
| Magnitude × 3 (EXP-3008)        | −3.0 pp | −4.2 pp |
| Timing −30 min (EXP-3009)       | **−5.0 pp** | **−6.7 pp** |

Earlier-firing achieves more overshoot reduction than tripling magnitude, and does so **without increasing total insulin units** — a strict-Pareto improvement on the safety/efficacy frontier.

## Actionable interpretation

For **Loop**, this maps to lowering the BG threshold at which the application factor scales up (so SMBs start firing earlier in the ascent rather than waiting for higher BG). Concretely, the `GlucoseBasedApplicationFactorStrategy` 0.20-0.80 sliding scale could be triggered at lower BG, or the `partialApplicationFactor` floor could be raised. Either pulls SMB delivery earlier in the ascent.

For **Trio (oref1)**, the `enableSMB_always` + `SMBInterval=3min` pair is already aggressive on timing; the additional 6.7 pp suggests further benefit from lowering the SMB BG-trigger floor or increasing maxSMBBasalMinutes.

For **AAPS-oref0**, the lever is irrelevant — no SMB to retime. The fix is enabling SMB at all.

## Open question — does earlier firing trip hypo gates?

Total insulin is unchanged but redistribution within the DIA window could matter post-peak. A more rigorous EXP-3010 should integrate hypo-risk under the *redistributed* PK profile, not assume zero penalty. Logged as next-phase open question.

## Verdict
**`timing_axis_dominates_magnitude`** — Loop has a clear, PK-realisable improvement path (~5 pp overshoot reduction) by firing 30 min earlier. Magnitude alone is bounded; timing is not.

## Deliverables
```
tools/cgmencode/autoresearch_cf/exp_3009_timing_axis.py
externals/experiments/exp-3009_timing_response.parquet  (gitignored)
externals/experiments/exp-3009_summary.json             (gitignored)
docs/60-research/figures/exp-3009_timing_response.png
```
