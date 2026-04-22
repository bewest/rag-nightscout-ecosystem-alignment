"""EXP-2859 — Bootstrap CI on per-patient Simpson flag.

EXP-2856 showed Simpson-positive patients have only 25% rolling-window
agreement; EXP-2858 showed flips don't correlate with anything
measurable. The boolean Simpson flag is too noisy near the regime
boundary.

This experiment bootstraps β_fast and β_slow per patient to estimate
P(simpson) — a confidence value that replaces the boolean. Bootstrap
strategy:

  - β_fast: block bootstrap on 48h chunks of (glucose, basal) at 5-min
    resolution. Block size matches β_slow window so resampled chunks
    are exchangeable for both regressions.
  - β_slow: 48h window means computed FROM the resampled chunks → OLS.

For each of N_BOOT bootstrap replicates, compute β_fast, β_slow, and
the Simpson flag. Output:
  - P(simpson) per patient
  - Mean β_fast, β_slow with 95% CI
  - Categorize: high-confidence Simpson (P>=0.9), high-confidence
    non-Simpson (P<=0.1), uncertain boundary (0.1<P<0.9)

Charter B compliant.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

REPO = Path(__file__).resolve().parents[2]
EXPDIR = REPO / "externals" / "experiments"
FIGDIR = REPO / "docs" / "60-research" / "figures"
GRID = REPO / "externals" / "ns-parquet" / "training" / "grid.parquet"

WIN_SIZE = 48 * 12   # 48h at 5-min resolution
N_BOOT = 200
MIN_WINDOWS = 7
RNG_SEED = 2859


def betas_from_chunks(chunks: list[np.ndarray]) -> tuple[float, float] | None:
    """Compute β_fast (5-min OLS) and β_slow (48h means OLS) from a
    list of 48h chunks each shape (WIN_SIZE, 2) cols [glucose, basal]."""
    flat = np.concatenate(chunks, axis=0)
    if np.std(flat[:, 0]) < 1e-3 or np.std(flat[:, 1]) < 1e-6:
        return None
    fast = stats.linregress(flat[:, 0], flat[:, 1]).slope
    bg_means = np.array([c[:, 0].mean() for c in chunks])
    ba_means = np.array([c[:, 1].mean() for c in chunks])
    if np.std(bg_means) < 1e-3:
        return None
    slow = stats.linregress(bg_means, ba_means).slope
    return float(fast), float(slow)


def per_patient_bootstrap(g: pd.DataFrame, rng: np.random.Generator) -> dict | None:
    arr = g[["glucose", "actual_basal_rate"]].to_numpy()
    n_full = len(arr) // WIN_SIZE
    if n_full < MIN_WINDOWS:
        return None
    arr = arr[: n_full * WIN_SIZE]
    chunks = [arr[i * WIN_SIZE : (i + 1) * WIN_SIZE] for i in range(n_full)]

    # Point estimate
    pe = betas_from_chunks(chunks)
    if pe is None:
        return None
    point_fast, point_slow = pe

    fasts, slows, simps = [], [], []
    for _ in range(N_BOOT):
        idx = rng.integers(0, n_full, size=n_full)
        sample = [chunks[i] for i in idx]
        b = betas_from_chunks(sample)
        if b is None:
            continue
        fasts.append(b[0])
        slows.append(b[1])
        simps.append(np.sign(b[0]) != np.sign(b[1]) and abs(b[0]) > 1e-6 and abs(b[1]) > 1e-6)

    if len(fasts) < 50:
        return None
    fasts_a = np.array(fasts)
    slows_a = np.array(slows)
    return {
        "n_chunks": int(n_full),
        "n_boot_valid": int(len(fasts)),
        "point_beta_fast": point_fast,
        "point_beta_slow": point_slow,
        "point_simpson": bool(
            np.sign(point_fast) != np.sign(point_slow)
            and abs(point_fast) > 1e-6 and abs(point_slow) > 1e-6
        ),
        "p_simpson": float(np.mean(simps)),
        "beta_fast_mean": float(fasts_a.mean()),
        "beta_fast_ci_lo": float(np.quantile(fasts_a, 0.025)),
        "beta_fast_ci_hi": float(np.quantile(fasts_a, 0.975)),
        "beta_slow_mean": float(slows_a.mean()),
        "beta_slow_ci_lo": float(np.quantile(slows_a, 0.025)),
        "beta_slow_ci_hi": float(np.quantile(slows_a, 0.975)),
        "p_fast_pos": float(np.mean(fasts_a > 0)),
        "p_slow_pos": float(np.mean(slows_a > 0)),
    }


def main() -> None:
    rng = np.random.default_rng(RNG_SEED)
    cols = ["patient_id", "time", "glucose", "actual_basal_rate"]
    df = pd.read_parquet(GRID, columns=cols).dropna(
        subset=["glucose", "actual_basal_rate"]
    )
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.sort_values(["patient_id", "time"])

    rows = []
    for pid, g in df.groupby("patient_id", sort=False):
        if len(g) < WIN_SIZE * MIN_WINDOWS:
            continue
        r = per_patient_bootstrap(g, rng)
        if r is None:
            continue
        rows.append({"patient_id": pid, **r})
    out = pd.DataFrame(rows)
    out.to_parquet(EXPDIR / "exp-2859_bootstrap_simpson.parquet", index=False)

    # Categorize
    high_conf_simpson = out[out["p_simpson"] >= 0.9]
    high_conf_clean = out[out["p_simpson"] <= 0.1]
    uncertain = out[(out["p_simpson"] > 0.1) & (out["p_simpson"] < 0.9)]

    # Cross-tab vs EXP-2853 point Simpson
    ptidx = out["point_simpson"]
    summary = {
        "exp": "EXP-2859",
        "method": (
            f"Block bootstrap (N={N_BOOT}, block=48h chunks) per patient. "
            "Recompute β_fast and β_slow on each replicate; estimate "
            "P(simpson) = fraction of replicates with sign mismatch."
        ),
        "n_patients": int(len(out)),
        "n_high_conf_simpson_p_ge_0.9": int(len(high_conf_simpson)),
        "n_high_conf_clean_p_le_0.1": int(len(high_conf_clean)),
        "n_uncertain_0.1_to_0.9": int(len(uncertain)),
        "median_p_simpson": float(out["p_simpson"].median()),
        "median_p_simpson_when_point_is_True": (
            float(out.loc[ptidx, "p_simpson"].median())
            if ptidx.any() else None
        ),
        "median_p_simpson_when_point_is_False": (
            float(out.loc[~ptidx, "p_simpson"].median())
            if (~ptidx).any() else None
        ),
        "interpretation": [
            "P(simpson) >= 0.9 → confidently classify as Simpson; emit medium severity.",
            "P(simpson) <= 0.1 → confidently non-Simpson; suppress flag.",
            "0.1 < P < 0.9 → boundary case; emit low severity (acknowledged uncertainty).",
            "Compare to EXP-2856 boolean: bootstrap should give SHARPER classification "
            "for stable patients and EXPLICIT uncertainty for unstable ones.",
        ],
    }
    (EXPDIR / "exp-2859_summary.json").write_text(json.dumps(summary, indent=2))

    # Visualization
    try:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        ax = axes[0]
        ax.hist(out["p_simpson"], bins=20, color="#4472C4",
                edgecolor="black", alpha=0.85)
        ax.axvline(0.1, color="green", linestyle="--", label="P≤0.1: clean")
        ax.axvline(0.9, color="red", linestyle="--", label="P≥0.9: Simpson")
        ax.set_xlabel("P(simpson) — bootstrap")
        ax.set_ylabel("Patient count")
        ax.set_title(
            f"Per-patient P(simpson) — n={len(out)}\n"
            f"high-conf Simpson={len(high_conf_simpson)}, "
            f"clean={len(high_conf_clean)}, uncertain={len(uncertain)}"
        )
        ax.legend(fontsize=9)

        ax = axes[1]
        # β_fast vs β_slow with CI bars; color by P(simpson)
        scat = ax.scatter(
            out["beta_fast_mean"] * 50,
            out["beta_slow_mean"] * 50,
            c=out["p_simpson"], cmap="RdYlGn_r",
            s=60, edgecolor="black", vmin=0, vmax=1,
        )
        for _, r in out.iterrows():
            ax.errorbar(
                r["beta_fast_mean"] * 50,
                r["beta_slow_mean"] * 50,
                xerr=[[(r["beta_fast_mean"] - r["beta_fast_ci_lo"]) * 50],
                      [(r["beta_fast_ci_hi"] - r["beta_fast_mean"]) * 50]],
                yerr=[[(r["beta_slow_mean"] - r["beta_slow_ci_lo"]) * 50],
                      [(r["beta_slow_ci_hi"] - r["beta_slow_mean"]) * 50]],
                fmt="none", ecolor="grey", alpha=0.4, capsize=2,
            )
        ax.axhline(0, color="black", linewidth=0.5)
        ax.axvline(0, color="black", linewidth=0.5)
        ax.set_xlabel("β_fast (U/h per +50 mg/dL)")
        ax.set_ylabel("β_slow (U/h per +50 mg/dL)")
        ax.set_title("β_fast × β_slow with bootstrap 95% CI")
        plt.colorbar(scat, ax=ax, label="P(simpson)")

        fig.suptitle(
            "EXP-2859: bootstrap-confidence Simpson — replaces boolean flag",
            fontsize=12,
        )
        plt.tight_layout()
        FIGDIR.mkdir(parents=True, exist_ok=True)
        fig.savefig(FIGDIR / "exp-2859_bootstrap_simpson.png", dpi=120)
        plt.close(fig)
    except Exception as e:  # noqa: BLE001
        print("viz failed:", e)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
