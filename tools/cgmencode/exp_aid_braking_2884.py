"""EXP-2884 — AID basal-cut efficacy during pre-hypo descent.

Paradox from EXP-2881: evening hypos carry 2.25 U more 4h bolus +
0.6 U basal = ~2.85 U excess insulin, yet descent is only 0.13
mg/dL/min faster than other TODs. Where does the excess go?

Hypothesis: AID systems detect the falling BG and attenuate basal
aggressively pre-hypo; the descent penalty is small because a large
fraction of the scheduled basal is cut during descent.

Method:
  1. For each pre-nadir event (EXP-2880/2881 structure):
       delivery_ratio = actual_basal_mean / scheduled_basal_mean
         (fraction of scheduled basal actually delivered during descent)
       basal_attenuation_U = (sched_basal − actual_basal) × 1 hour
         (U of insulin not delivered per hour during descent window)
  2. Stratify by TOD; larger attenuation in evening implies stronger
     braking response to the stacking load.
  3. Per-patient: evening delivery_ratio vs rest delivery_ratio.
  4. Cohort-level efficacy:
       total_sched_insulin_evening vs total_actual_insulin_evening
       vs same for rest.

Output: exp-2884_aid_braking.parquet + summary + figure.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]

EV_2881 = ROOT / "externals/experiments/exp-2881_evening_drivers.parquet"
OUT = ROOT / "externals/experiments/exp-2884_aid_braking.parquet"
OUT_SUMMARY = ROOT / "externals/experiments/exp-2884_aid_braking_summary.json"
OUT_FIG = ROOT / "docs/60-research/figures/exp-2884_aid_braking.png"

TOD_BINS = [("night", 0, 6), ("morning", 6, 12), ("afternoon", 12, 18), ("evening", 18, 24)]


def main() -> None:
    df = pd.read_parquet(EV_2881).copy()
    print(f"events={len(df)} patients={df.patient_id.nunique()}")

    df["delivery_ratio"] = np.where(
        df["sched_basal"] > 0,
        df["actual_basal"] / df["sched_basal"],
        np.nan,
    )
    df["basal_attenuation_uh"] = df["sched_basal"] - df["actual_basal"]
    df.to_parquet(OUT)

    # Stratum medians
    strata = {}
    for name, _, _ in TOD_BINS:
        sub = df[df.tod == name]
        strata[name] = {
            "n": int(len(sub)),
            "delivery_ratio_median": float(sub.delivery_ratio.median()),
            "delivery_ratio_mean": float(sub.delivery_ratio.mean()),
            "basal_attenuation_uh_median": float(sub.basal_attenuation_uh.median()),
            "basal_attenuation_uh_mean": float(sub.basal_attenuation_uh.mean()),
            "sched_basal_median": float(sub.sched_basal.median()),
            "actual_basal_median": float(sub.actual_basal.median()),
        }

    print("\nPer-TOD basal braking (during 60-min descent window):")
    print(f"{'TOD':10s} {'n':>5s} {'sched':>8s} {'actual':>8s} {'ratio':>8s} {'cut U/h':>10s}")
    for name, _, _ in TOD_BINS:
        s = strata[name]
        print(
            f"{name:10s} {s['n']:5d} "
            f"{s['sched_basal_median']:8.3f} "
            f"{s['actual_basal_median']:8.3f} "
            f"{s['delivery_ratio_median']:8.3f} "
            f"{s['basal_attenuation_uh_median']:10.3f}"
        )

    # Evening vs rest Mann-Whitney
    ev = df[df.tod == "evening"]
    rest = df[df.tod != "evening"]
    mw = {}
    for col in ["delivery_ratio", "basal_attenuation_uh"]:
        ev_v = ev[col].dropna().values
        rest_v = rest[col].dropna().values
        u, p = stats.mannwhitneyu(ev_v, rest_v, alternative="two-sided")
        mw[col] = {
            "evening_median": float(np.median(ev_v)),
            "rest_median": float(np.median(rest_v)),
            "diff_median": float(np.median(ev_v) - np.median(rest_v)),
            "mannwhitney_p": float(p),
        }
    print("\nEvening vs rest Mann-Whitney:")
    for col, r in mw.items():
        print(
            f"  {col:24s}  ev={r['evening_median']:+.3f}  "
            f"rest={r['rest_median']:+.3f}  diff={r['diff_median']:+.3f}  "
            f"p={r['mannwhitney_p']:.2g}"
        )

    # Per-patient delivery_ratio evening vs rest
    pp = []
    for pid, g in df.groupby("patient_id"):
        ev_g = g[g.tod == "evening"]
        rest_g = g[g.tod != "evening"]
        if len(ev_g) < 3 or len(rest_g) < 10:
            continue
        pp.append({
            "patient_id": pid,
            "n_evening": int(len(ev_g)),
            "n_rest": int(len(rest_g)),
            "evening_delivery_ratio": float(ev_g.delivery_ratio.median()),
            "rest_delivery_ratio": float(rest_g.delivery_ratio.median()),
            "diff_delivery_ratio": float(
                ev_g.delivery_ratio.median() - rest_g.delivery_ratio.median()
            ),
            "evening_attenuation_uh": float(ev_g.basal_attenuation_uh.median()),
            "rest_attenuation_uh": float(rest_g.basal_attenuation_uh.median()),
            "diff_attenuation_uh": float(
                ev_g.basal_attenuation_uh.median() - rest_g.basal_attenuation_uh.median()
            ),
        })
    pp = pd.DataFrame(pp)
    print(f"\nPer-patient n={len(pp)}")

    if len(pp) >= 5:
        _, p_ratio = stats.wilcoxon(pp["diff_delivery_ratio"].values)
        _, p_att = stats.wilcoxon(pp["diff_attenuation_uh"].values)
    else:
        p_ratio, p_att = None, None

    median_dratio = float(pp["diff_delivery_ratio"].median())
    median_datt = float(pp["diff_attenuation_uh"].median())
    frac_ev_cut_more = float((pp["diff_attenuation_uh"] > 0).mean())
    print(
        f"  median diff_delivery_ratio = {median_dratio:+.3f} (Wilcoxon p={p_ratio})\n"
        f"  median diff_attenuation_uh  = {median_datt:+.3f} "
        f"(positive = evening cuts more; {frac_ev_cut_more:.0%} do so, p={p_att})"
    )

    # Compute approximate "saved insulin" at cohort level
    # Scheduled U/h during 60-min window → sched_basal_median U/h × 1h
    # Actual delivery = delivery_ratio × scheduled
    # Save = sched × (1 - delivery_ratio) = attenuation × 1h
    summary = {
        "exp_id": "2884",
        "n_events": int(len(df)),
        "n_patients": int(df.patient_id.nunique()),
        "per_tod": strata,
        "evening_vs_rest": mw,
        "per_patient_wilcoxon": {
            "n": int(len(pp)),
            "median_diff_delivery_ratio": median_dratio,
            "wilcoxon_p_delivery_ratio": float(p_ratio) if p_ratio else None,
            "median_diff_attenuation_uh": median_datt,
            "wilcoxon_p_attenuation_uh": float(p_att) if p_att else None,
            "frac_evening_cuts_more": frac_ev_cut_more,
        },
    }

    # Figure: 3-panel
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    tod_names = [n for n, _, _ in TOD_BINS]
    colors = ["#1f3b5f", "#d99133", "#3d8a5f", "#6d3d8f"]

    # Panel 1: delivery_ratio by TOD
    ratios = [strata[n]["delivery_ratio_median"] for n in tod_names]
    ns = [strata[n]["n"] for n in tod_names]
    bars = axes[0].bar(tod_names, ratios, color=colors)
    for bar, n in zip(bars, ns):
        axes[0].text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"n={n}",
            ha="center", fontsize=9,
        )
    axes[0].axhline(1.0, color="gray", lw=0.5, linestyle="--")
    axes[0].set_ylabel("delivery_ratio (actual / scheduled basal)")
    axes[0].set_title("Basal delivery ratio during descent by TOD")
    axes[0].set_ylim(0, 1.1)
    axes[0].grid(axis="y", alpha=0.3)

    # Panel 2: attenuation U/h
    att = [strata[n]["basal_attenuation_uh_median"] for n in tod_names]
    bars = axes[1].bar(tod_names, att, color=colors)
    axes[1].set_ylabel("basal attenuation (U/h cut below scheduled)")
    axes[1].set_title("AID basal cut during descent")
    axes[1].grid(axis="y", alpha=0.3)

    # Panel 3: per-patient evening vs rest delivery ratio
    if len(pp):
        y_pos = range(len(pp))
        vals = pp["diff_delivery_ratio"].values
        bar_colors = ["tab:red" if v < 0 else "tab:green" for v in vals]
        axes[2].barh(y_pos, vals, color=bar_colors)
        axes[2].set_yticks(y_pos)
        axes[2].set_yticklabels(pp.patient_id.values, fontsize=7)
        axes[2].axvline(0, color="k", lw=0.5)
        axes[2].set_xlabel("evening − rest delivery_ratio\n(negative = evening cuts more)")
        axes[2].set_title(
            f"Per-patient AID braking\n"
            f"median={median_dratio:+.3f}, "
            f"{1-frac_ev_cut_more:.0%} cut-more in evening, "
            f"p={p_ratio:.2g}"
        )
        axes[2].grid(axis="x", alpha=0.3)

    fig.suptitle(
        "EXP-2884 — AID Basal-Cut Efficacy During Pre-Nadir Descent",
        fontsize=13,
    )
    fig.tight_layout()
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_FIG, dpi=110)
    plt.close(fig)

    # Verdict
    # Evening delivery ratio lower than rest → AID cutting more evening (braking)
    dratio_diff = mw["delivery_ratio"]["diff_median"]
    att_diff = mw["basal_attenuation_uh"]["diff_median"]
    p_dr = mw["delivery_ratio"]["mannwhitney_p"]

    if dratio_diff < -0.05 and p_dr < 0.01:
        verdict = (
            f"AID EVENING BRAKING CONFIRMED — evening delivery_ratio is "
            f"{abs(dratio_diff)*100:.1f} percentage points LOWER than rest "
            f"(p={p_dr:.2g}). AID cuts {att_diff:+.3f} U/h MORE basal in "
            "evening descent vs rest, absorbing much of the stacking "
            "excess and explaining why evening descent slope is only "
            "0.13 mg/dL/min faster despite 2.85 U total insulin excess."
        )
    elif dratio_diff < 0 and p_dr < 0.05:
        verdict = (
            f"PARTIAL AID BRAKING — evening delivery_ratio {dratio_diff:+.3f} "
            f"below rest (p={p_dr:.2g}); braking is directionally present "
            "but modest in magnitude."
        )
    elif abs(dratio_diff) < 0.03:
        verdict = (
            f"NO DIFFERENTIAL BRAKING — evening delivery_ratio "
            f"{dratio_diff:+.3f} vs rest; AID does NOT cut evening basal "
            "more aggressively. The modest descent-slope difference must "
            "come from other factors (meal absorption tails, residual "
            "carb effects)."
        )
    else:
        verdict = (
            f"UNEXPECTED — evening delivery_ratio {dratio_diff:+.3f}, "
            f"attenuation {att_diff:+.3f} U/h, p={p_dr}. Further "
            "investigation needed."
        )

    summary["verdict"] = verdict
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"\nVerdict: {verdict}")


if __name__ == "__main__":
    main()
