"""EXP-2863 — Bootstrap confidence on per-patient site-degradation delta.

Generalizes the EXP-2859/2861/2862 bootstrap-confidence pattern to the
wear/site-degradation audition signal. The naive flag (EXP-2831) is
`(median_isf_aged - median_isf_fresh) / median_isf_fresh < -20%`.
Per-event bootstrap quantifies P(true degradation > 20%).

Source: per-event correction extraction from grid.parquet, mirroring
the extraction logic in EXP-2831 (re-extracted to obtain cage_hours
per event).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"

EVENT_CACHE = EXPDIR / "exp-2863_per_event_isf_wear.parquet"

EXCLUDE: set[str] = set()  # match upstream
N_BOOT = 500
RNG_SEED = 2863
THRESH_DEGRADE = -20.0   # delta_pct < -20%
MIN_FRESH = 5
MIN_AGED = 5


def _extract_events(pdata: pd.DataFrame) -> list[dict]:
    """Mirror EXP-2831 extract_with_wear, but record only what we need."""
    pdata = pdata.sort_values("time").reset_index(drop=True)
    bg = pdata["glucose"].values
    bolus = pdata["bolus"].fillna(0).values
    carbs = pdata["carbs"].fillna(0).values
    iob = pdata["iob"].fillna(0).values
    cage = pdata["cage_hours"].values
    swarmup = pdata["sensor_warmup"].fillna(0).values if "sensor_warmup" in pdata else np.zeros(len(pdata))
    n = len(pdata)
    out = []
    for i in range(72, n - 42):
        if bolus[i] < 0.5 or bg[i] < 180:
            continue
        if carbs[max(0, i - 36):min(n, i + 36)].sum() > 5:
            continue
        if iob[i] > 2.0:
            continue
        back = bg[max(0, i - 72):i]
        if np.isnan(back).any():
            continue
        time_in_high = (back > 180).sum() / 12.0
        if not (1 <= time_in_high <= 6):
            continue
        fwd = bg[i:i + 42]
        if np.isnan(fwd).any():
            continue
        if swarmup[i] > 0.5:
            continue
        drop_full = bg[i] - np.min(fwd)
        if drop_full <= 0:
            continue
        out.append({
            "isf_full": float(drop_full / bolus[i]),
            "cage_hours": float(cage[i]) if not np.isnan(cage[i]) else np.nan,
        })
    return out


def _build_event_cache() -> pd.DataFrame:
    if EVENT_CACHE.exists():
        return pd.read_parquet(EVENT_CACHE)
    grid = pd.read_parquet(GRID)
    grid = grid[~grid["patient_id"].isin(EXCLUDE)].copy()
    grid = grid.sort_values(["patient_id", "time"]).reset_index(drop=True)
    rows = []
    for pid in sorted(grid["patient_id"].unique()):
        pdata = grid[grid["patient_id"] == pid]
        if "cage_hours" not in pdata.columns:
            continue
        for ev in _extract_events(pdata):
            ev["patient_id"] = pid
            rows.append(ev)
    df = pd.DataFrame(rows)
    df.to_parquet(EVENT_CACHE, index=False)
    return df


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    ev = _build_event_cache()
    print(f"events={len(ev)} patients={ev['patient_id'].nunique()}")
    ev = ev.dropna(subset=["cage_hours", "isf_full"])

    rows = []
    for pid, g in ev.groupby("patient_id"):
        fresh = g[g["cage_hours"] < 24]["isf_full"].to_numpy()
        aged = g[g["cage_hours"] >= 48]["isf_full"].to_numpy()
        if len(fresh) < MIN_FRESH or len(aged) < MIN_AGED:
            continue
        # Bootstrap delta_pct
        nf, na = len(fresh), len(aged)
        boot_deltas = np.empty(N_BOOT)
        for k in range(N_BOOT):
            f_med = np.median(fresh[rng.integers(0, nf, size=nf)])
            a_med = np.median(aged[rng.integers(0, na, size=na)])
            boot_deltas[k] = (a_med - f_med) / f_med * 100.0 if f_med > 0 else np.nan
        boot_deltas = boot_deltas[~np.isnan(boot_deltas)]
        point_delta = (np.median(aged) - np.median(fresh)) / np.median(fresh) * 100.0
        rows.append({
            "patient_id": pid,
            "n_fresh": int(nf),
            "n_aged": int(na),
            "point_delta_pct": float(point_delta),
            "boot_delta_mean": float(boot_deltas.mean()),
            "boot_delta_ci_lo": float(np.quantile(boot_deltas, 0.025)),
            "boot_delta_ci_hi": float(np.quantile(boot_deltas, 0.975)),
            "p_site_degradation": float(np.mean(boot_deltas < THRESH_DEGRADE)),
            "p_site_improvement": float(np.mean(boot_deltas > -THRESH_DEGRADE)),
        })

    out = pd.DataFrame(rows)
    out.to_parquet(EXPDIR / "exp-2863_bootstrap_wear.parquet", index=False)

    def _band(r):
        if r["p_site_degradation"] >= 0.9:
            return "confident_degrade"
        if r["p_site_improvement"] >= 0.9:
            return "confident_improve"
        if r["p_site_degradation"] < 0.1 and r["p_site_improvement"] < 0.1:
            return "confident_neutral"
        return "uncertain"

    def _naive(r):
        if r["point_delta_pct"] < THRESH_DEGRADE:
            return "naive_degrade"
        if r["point_delta_pct"] > -THRESH_DEGRADE:
            return "naive_improve"
        return "naive_neutral"

    out["band"] = out.apply(_band, axis=1)
    out["naive_band"] = out.apply(_naive, axis=1)
    band_counts = out["band"].value_counts().to_dict()
    naive_counts = out["naive_band"].value_counts().to_dict()

    summary = {
        "exp": "EXP-2863",
        "method": (
            f"Per-patient event bootstrap (N={N_BOOT}) of fresh-vs-aged "
            "ISF medians; quantifies P(site_degradation < -20%) and "
            "P(site_improvement > +20%)."
        ),
        "n_patients": int(len(out)),
        "thresholds": {"degrade_pct": THRESH_DEGRADE, "improve_pct": -THRESH_DEGRADE},
        "min_events_required": {"fresh": MIN_FRESH, "aged": MIN_AGED},
        "bootstrap_band_counts": {str(k): int(v) for k, v in band_counts.items()},
        "naive_point_band_counts": {str(k): int(v) for k, v in naive_counts.items()},
        "median_n_fresh": int(out["n_fresh"].median()) if len(out) else 0,
        "median_n_aged": int(out["n_aged"].median()) if len(out) else 0,
        "median_ci_width_pct": float(
            (out["boot_delta_ci_hi"] - out["boot_delta_ci_lo"]).median()
        ) if len(out) else None,
    }
    (EXPDIR / "exp-2863_summary.json").write_text(json.dumps(summary, indent=2))

    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        ax = axes[0]
        out_s = out.sort_values("point_delta_pct").reset_index(drop=True)
        y = np.arange(len(out_s))
        ax.errorbar(
            out_s["boot_delta_mean"], y,
            xerr=[
                np.clip(out_s["boot_delta_mean"] - out_s["boot_delta_ci_lo"], 0, None),
                np.clip(out_s["boot_delta_ci_hi"] - out_s["boot_delta_mean"], 0, None),
            ],
            fmt="o", color="#4472C4", ecolor="grey", capsize=2, alpha=0.85,
        )
        ax.axvline(THRESH_DEGRADE, color="red", linestyle="--", label=f"degrade {THRESH_DEGRADE}%")
        ax.axvline(-THRESH_DEGRADE, color="green", linestyle="--", label=f"improve {-THRESH_DEGRADE}%")
        ax.axvline(0, color="black", linewidth=0.5)
        ax.set_xlabel("aged-vs-fresh ISF delta % (bootstrap 95% CI)")
        ax.set_ylabel("patient (sorted)")
        ax.set_title(f"Per-patient site-degradation delta with bootstrap CI (n={len(out)})")
        ax.legend(fontsize=9)

        ax = axes[1]
        bands = ["confident_degrade", "confident_improve", "confident_neutral", "uncertain"]
        bvals = [band_counts.get(b, 0) for b in bands]
        nvals = [naive_counts.get(k, 0) for k in
                 ["naive_degrade", "naive_improve", "naive_neutral"]] + [0]
        x = np.arange(len(bands))
        w = 0.35
        ax.bar(x - w/2, nvals, w, label="naive (point)", color="#A0A0A0", edgecolor="black")
        ax.bar(x + w/2, bvals, w, label="bootstrap (P>=0.9)", color="#4472C4", edgecolor="black")
        ax.set_xticks(x)
        ax.set_xticklabels(["degrade", "improve", "neutral", "uncertain"])
        ax.set_ylabel("patient count")
        ax.set_title("Bootstrap vs naive")
        ax.legend(fontsize=9)

        fig.suptitle("EXP-2863: bootstrap-confidence wear/site-degradation", fontsize=12)
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2863_bootstrap_wear.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
