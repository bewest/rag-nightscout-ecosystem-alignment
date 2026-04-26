"""EXP-3021 — Generator realism smell test.

Question to answer: are EXP-3006 (patient sampler) and EXP-3016 (event
sampler) good enough to reliably generate realistic per-patient event
streams for downstream ISF/CR/basal deconfounding work, or are they
non-parametric resamplers whose smell will give them away?

Three scenarios:
  A. Patient-twin: pick a real patient, hold them out of the pool, and
     ask EXP-3006-style k-NN to regenerate them from their phenotype
     coordinate. Compare distributions of the 6 event numerics.
  B. Phenotype-divergence: 4 archetype centroids → 4 synth cohorts →
     check that aggregate distributions actually diverge across them
     (not all collapsing to cohort mean).
  C. Within-patient holdout: longest-tail patient, chronological
     70/30 split, bootstrap+jitter first 70 % → compare to held-out 30 %.

Outputs:
  externals/experiments/exp-3021_summary.json
  externals/experiments/exp-3021_moments.tsv
  docs/60-research/figures/exp-3021_scenario_A.png
  docs/60-research/figures/exp-3021_scenario_B.png
  docs/60-research/figures/exp-3021_scenario_C.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
EXT = ROOT / "externals" / "experiments"
DOCS_FIG = ROOT / "docs" / "60-research" / "figures"

EVENTS = EXT / "exp-3007_ascent_events.parquet"
PHENOTYPE = EXT / "exp-2886_phenotype.parquet"

NUMERIC_COLS = ["bg_start", "peak_delta", "smb_during",
                "iob_start", "cob_start", "carbs_during"]
JITTER_SIGMA = 0.10
N_SYNTH = 800
K_NN = 3
RNG = np.random.default_rng(seed=2026)


def knn_neighbors(target_pt: list[float], pool_phen: pd.DataFrame,
                  feats: list[str], k: int = K_NN
                  ) -> tuple[list[str], list[float], list[float]]:
    ph = pool_phen.dropna(subset=feats).copy()
    sc = StandardScaler().fit(ph[feats].values)
    nn = NearestNeighbors(n_neighbors=min(k, len(ph))).fit(sc.transform(ph[feats]))
    dists, idxs = nn.kneighbors(sc.transform([target_pt]))
    pids = ph.iloc[idxs[0]]["patient_id"].tolist()
    w = 1.0 / (dists[0] + 0.01)
    w = w / w.sum()
    return pids, w.tolist(), dists[0].tolist()


def bootstrap_mix(events: pd.DataFrame, pids: list[str],
                  weights: list[float], n: int) -> pd.DataFrame:
    parts = []
    for pid, w in zip(pids, weights):
        ev_p = events[events["patient_id"] == pid]
        m = max(1, int(round(w * n)))
        m = min(m, len(ev_p))
        if m > 0:
            parts.append(ev_p.sample(n=m, random_state=int(RNG.integers(1 << 30)),
                                     replace=False))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def jitter(df: pd.DataFrame, sigma: float = JITTER_SIGMA) -> pd.DataFrame:
    out = df.copy()
    for col in NUMERIC_COLS:
        if col in out.columns:
            j = RNG.lognormal(mean=0.0, sigma=sigma, size=len(out))
            out[col] = (out[col].fillna(0).to_numpy() * j).clip(min=0)
    if "peak_delta" in out.columns and "bg_start" in out.columns:
        out["bg_peak"] = out["bg_start"] + out["peak_delta"]
    return out


def moments(df: pd.DataFrame, label: str) -> dict:
    rec = {"label": label, "n": len(df)}
    for c in NUMERIC_COLS:
        s = df[c].dropna()
        if len(s):
            rec[f"{c}_mean"] = float(s.mean())
            rec[f"{c}_std"] = float(s.std())
            rec[f"{c}_p50"] = float(s.median())
    return rec


def ks_table(real: pd.DataFrame, synth: pd.DataFrame) -> dict[str, float]:
    out = {}
    for c in NUMERIC_COLS:
        a = real[c].dropna().to_numpy()
        b = synth[c].dropna().to_numpy()
        if len(a) > 5 and len(b) > 5:
            out[c] = float(stats.ks_2samp(a, b).statistic)
    return out


def plot_panels(real: pd.DataFrame, synth: pd.DataFrame,
                title: str, out_path: Path,
                synth_label: str = "synth") -> None:
    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    fig.suptitle(title, fontsize=12)
    for ax, col in zip(axes.flat, NUMERIC_COLS):
        a = real[col].dropna()
        b = synth[col].dropna()
        if len(a) and len(b):
            lo = float(min(a.min(), b.min()))
            hi = float(max(a.quantile(0.99), b.quantile(0.99)))
            bins = np.linspace(lo, hi, 40)
            ax.hist(a, bins=bins, alpha=0.5, label="real",
                    density=True, color="C0")
            ax.hist(b, bins=bins, alpha=0.5, label=synth_label,
                    density=True, color="C1")
        ax.set_title(col, fontsize=9)
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=7)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def plot_archetypes(synths: dict[str, pd.DataFrame], out_path: Path) -> None:
    fig, axes = plt.subplots(2, 3, figsize=(12, 7))
    fig.suptitle("EXP-3021 Scenario B: phenotype-conditioned synth cohorts",
                 fontsize=12)
    colors = ["C0", "C1", "C2", "C3"]
    for ax, col in zip(axes.flat, NUMERIC_COLS):
        all_lo = min(s[col].dropna().min() for s in synths.values())
        all_hi = max(s[col].dropna().quantile(0.99) for s in synths.values())
        bins = np.linspace(all_lo, all_hi, 40)
        for (label, syn), color in zip(synths.items(), colors):
            d = syn[col].dropna()
            if len(d):
                ax.hist(d, bins=bins, alpha=0.45, label=label,
                        density=True, color=color)
        ax.set_title(col, fontsize=9)
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=6)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    events = pd.read_parquet(EVENTS)
    phen = pd.read_parquet(PHENOTYPE)
    feats = ["braking_ratio", "stack_score", "hidden_leverage"]

    moments_rows: list[dict] = []
    summary: dict = {"scenarios": {}}

    # ---------------------------------------------------------------
    # Scenario A: patient-twin (hold-out i, regenerate from phenotype)
    # ---------------------------------------------------------------
    target_pid = "i"
    target_row = phen[phen["patient_id"] == target_pid].iloc[0]
    target_pt = [float(target_row[f]) for f in feats]
    pool_phen_A = phen[phen["patient_id"] != target_pid]
    pool_ev_A = events[events["patient_id"] != target_pid]
    nbr_A, w_A, d_A = knn_neighbors(target_pt, pool_phen_A, feats)
    synth_A = bootstrap_mix(pool_ev_A, nbr_A, w_A, N_SYNTH)
    real_A = events[events["patient_id"] == target_pid]
    plot_panels(real_A, synth_A,
                f"EXP-3021 Scenario A: patient `{target_pid}` twin "
                f"(neighbours {nbr_A}, weights {[f'{x:.2f}' for x in w_A]})",
                DOCS_FIG / "exp-3021_scenario_A.png",
                synth_label="synth twin")
    moments_rows.append(moments(real_A, "real_i"))
    moments_rows.append(moments(synth_A, "synth_twin_i"))
    summary["scenarios"]["A_patient_twin"] = {
        "target_patient": target_pid,
        "target_phenotype": dict(zip(feats, target_pt)),
        "neighbours": nbr_A,
        "weights": w_A,
        "distances": d_A,
        "n_real": len(real_A),
        "n_synth": len(synth_A),
        "ks_2samp_per_feature": ks_table(real_A, synth_A),
    }

    # ---------------------------------------------------------------
    # Scenario B: phenotype-conditioned divergence (4 archetypes)
    # ---------------------------------------------------------------
    archetypes_B = {
        "aggressive_loop":   (0.05, 0.50, 0.55),
        "well_defended":     (0.07, 0.04, 0.04),
        "exposed_stacker":   (0.31, 0.83, 0.57),
        "conservative_oref1": (0.20, 0.30, 0.30),
    }
    synths_B = {}
    arch_meta = {}
    for label, target in archetypes_B.items():
        nbr, w, d = knn_neighbors(list(target), phen, feats)
        syn = bootstrap_mix(events, nbr, w, N_SYNTH)
        synths_B[label] = syn
        arch_meta[label] = {"target": target, "neighbours": nbr,
                            "weights": w, "distances": d, "n": len(syn)}
        moments_rows.append(moments(syn, f"synth_{label}"))
    plot_archetypes(synths_B, DOCS_FIG / "exp-3021_scenario_B.png")
    summary["scenarios"]["B_phenotype_divergence"] = arch_meta

    # ---------------------------------------------------------------
    # Scenario C: within-patient temporal holdout (longest tail)
    # ---------------------------------------------------------------
    n_per_pid = events.groupby("patient_id").size()
    long_pid = n_per_pid.idxmax()
    ev_long = events[events["patient_id"] == long_pid].sort_values("time_start")
    cut = int(len(ev_long) * 0.70)
    ev_train = ev_long.iloc[:cut].reset_index(drop=True)
    ev_test = ev_long.iloc[cut:].reset_index(drop=True)
    idx = RNG.integers(0, len(ev_train), size=N_SYNTH)
    synth_C = jitter(ev_train.iloc[idx].reset_index(drop=True))
    plot_panels(ev_test, synth_C,
                f"EXP-3021 Scenario C: within-patient `{long_pid}` "
                f"(train n={len(ev_train)}, test n={len(ev_test)})",
                DOCS_FIG / "exp-3021_scenario_C.png",
                synth_label="synth (jittered train)")
    moments_rows.append(moments(ev_train, f"train_{long_pid}"))
    moments_rows.append(moments(ev_test, f"test_{long_pid}"))
    moments_rows.append(moments(synth_C, f"synth_jitter_{long_pid}"))
    summary["scenarios"]["C_within_patient"] = {
        "patient_id": long_pid,
        "n_train": len(ev_train),
        "n_test": len(ev_test),
        "n_synth": len(synth_C),
        "ks_test_vs_synth": ks_table(ev_test, synth_C),
        "ks_test_vs_train": ks_table(ev_test, ev_train),
    }

    # Persist artefacts
    pd.DataFrame(moments_rows).to_csv(EXT / "exp-3021_moments.tsv",
                                      sep="\t", index=False)
    (EXT / "exp-3021_summary.json").write_text(
        json.dumps(summary, indent=2, default=float))
    print("[EXP-3021] wrote",
          EXT / "exp-3021_summary.json",
          EXT / "exp-3021_moments.tsv",
          DOCS_FIG / "exp-3021_scenario_A.png",
          DOCS_FIG / "exp-3021_scenario_B.png",
          DOCS_FIG / "exp-3021_scenario_C.png", sep="\n  ")


if __name__ == "__main__":
    main()
