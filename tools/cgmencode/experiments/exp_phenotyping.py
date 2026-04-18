#!/usr/bin/env python3
"""
EXP-2541: Patient Phenotyping via Therapy Response Clustering

Research question: Do natural phenotypes emerge from per-patient therapy
metrics that could guide personalized AID recommendations?

Approach:
  a) Build ~20-feature matrix across 19 patients (glycemic, ISF, CR,
     insulin, loop, hypo metrics).
  b) Cluster with k-means (k=2..5) + hierarchical; pick optimal k via
     silhouette score; visualize with PCA.
  c) Name and characterize each phenotype.
  d) Analyse NS vs ODC controller distribution across phenotypes.
  e) Map phenotypes to personalised advisory priorities.

Usage:
    PYTHONPATH=tools python tools/cgmencode/production/exp_phenotyping.py
    PYTHONPATH=tools python tools/cgmencode/production/exp_phenotyping.py --tiny
"""

import argparse
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import linkage, fcluster
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = Path(__file__).resolve().parents[3]
RESULTS_DIR = ROOT / "externals" / "experiments"
OUTPUT_FILE = "exp-2541_phenotyping.json"

# ── Constants ────────────────────────────────────────────────────────
STEPS_PER_HOUR = 12          # 5-min grid
TIR_LOW = 70                 # mg/dL
TIR_HIGH = 180
SEVERE_LOW = 54
HIGH_THRESH = 250
HYPO_GAP_STEPS = 6           # 30 min gap to count as separate event
CORRECTION_MIN_BOLUS = 0.3   # U – threshold for correction bolus
POST_MEAL_WINDOW = STEPS_PER_HOUR * 4  # 4 h post-meal observation
MEAL_MIN_CARBS = 5           # g – minimum to count as a meal


# ── Data Loading ─────────────────────────────────────────────────────
def load_data(tiny: bool = False) -> pd.DataFrame:
    if tiny:
        path = ROOT / "externals" / "ns-parquet-tiny" / "training" / "grid.parquet"
    else:
        path = ROOT / "externals" / "ns-parquet" / "training" / "grid.parquet"
    print(f"Loading {path} …")
    df = pd.read_parquet(path)
    df["time"] = pd.to_datetime(df["time"])
    df["hour"] = df["time"].dt.hour + df["time"].dt.minute / 60.0
    df["date"] = df["time"].dt.date
    print(f"  {len(df):,} rows, {df['patient_id'].nunique()} patients\n")
    return df


# ── Helper: controller type ─────────────────────────────────────────
def controller_type(pid: str) -> str:
    return "ODC" if str(pid).startswith("odc-") else "NS"


# ── EXP-2541a: Feature Matrix Construction ───────────────────────────
def compute_patient_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per patient with ~20 therapy-response features."""
    rows = []
    for pid in sorted(df["patient_id"].unique()):
        pdf = df[df["patient_id"] == pid].copy().reset_index(drop=True)
        g = pdf["glucose"].dropna()
        n_days = max((pdf["time"].max() - pdf["time"].min()).days, 1)
        feat: dict = {"patient_id": pid, "controller": controller_type(pid)}

        # ── 1. Glycemic metrics ──────────────────────────────────────
        if len(g) > 0:
            feat["tir"] = float((g.between(TIR_LOW, TIR_HIGH)).mean() * 100)
            feat["tbr_70"] = float((g < TIR_LOW).mean() * 100)
            feat["tbr_54"] = float((g < SEVERE_LOW).mean() * 100)
            feat["tar_180"] = float((g > TIR_HIGH).mean() * 100)
            feat["tar_250"] = float((g > HIGH_THRESH).mean() * 100)
            feat["mean_glucose"] = float(g.mean())
            feat["glucose_cv"] = float(g.std() / g.mean() * 100) if g.mean() > 0 else 0.0
        else:
            for k in ["tir", "tbr_70", "tbr_54", "tar_180", "tar_250",
                       "mean_glucose", "glucose_cv"]:
                feat[k] = np.nan

        # ── 2. ISF metrics ───────────────────────────────────────────
        feat["profile_isf"] = float(pdf["scheduled_isf"].median())

        bolus_vals = pdf["bolus"].fillna(0).values
        glucose_vals = pdf["glucose"].values
        iob_vals = pdf["iob"].fillna(0).values
        cob_vals = pdf["cob"].fillna(0).values
        corr_idx = np.where(bolus_vals > CORRECTION_MIN_BOLUS)[0]

        isf_obs = []
        for idx in corr_idx:
            # Only pure corrections: low COB, not near meals
            if idx + STEPS_PER_HOUR * 2 >= len(glucose_vals) or idx < 2:
                continue
            if cob_vals[idx] > 5:
                continue
            start_bg = glucose_vals[idx]
            end_bg = glucose_vals[idx + STEPS_PER_HOUR * 2]
            dose = bolus_vals[idx]
            if np.isnan(start_bg) or np.isnan(end_bg) or start_bg < 100 or dose < 0.3:
                continue
            drop = start_bg - end_bg
            if drop > 0:
                isf_obs.append(drop / dose)

        if len(isf_obs) >= 3:
            feat["effective_isf"] = float(np.median(isf_obs))
            feat["isf_ratio"] = feat["effective_isf"] / feat["profile_isf"] if feat["profile_isf"] > 0 else np.nan
            feat["isf_cv"] = float(np.std(isf_obs) / np.mean(isf_obs) * 100) if np.mean(isf_obs) > 0 else 0.0
        else:
            feat["effective_isf"] = np.nan
            feat["isf_ratio"] = np.nan
            feat["isf_cv"] = np.nan

        # ── 3. CR metrics ────────────────────────────────────────────
        feat["profile_cr"] = float(pdf["scheduled_cr"].median())
        carb_vals = pdf["carbs"].fillna(0).values
        meal_idx = np.where(carb_vals >= MEAL_MIN_CARBS)[0]
        cr_obs = []
        peak_excursions = []
        for idx in meal_idx:
            if idx + POST_MEAL_WINDOW >= len(glucose_vals):
                continue
            carb_g = carb_vals[idx]
            dose = bolus_vals[max(0, idx - 2): idx + 3].sum()
            if dose < 0.1:
                continue
            cr_obs.append(carb_g / dose)
            # Post-meal excursion
            pre_bg = glucose_vals[idx] if not np.isnan(glucose_vals[idx]) else np.nan
            window = glucose_vals[idx: idx + POST_MEAL_WINDOW]
            valid_window = window[~np.isnan(window)]
            if len(valid_window) > 0 and not np.isnan(pre_bg):
                peak_excursions.append(float(np.nanmax(valid_window) - pre_bg))

        if len(cr_obs) >= 3:
            feat["effective_cr"] = float(np.median(cr_obs))
            feat["cr_ratio"] = feat["effective_cr"] / feat["profile_cr"] if feat["profile_cr"] > 0 else np.nan
        else:
            feat["effective_cr"] = np.nan
            feat["cr_ratio"] = np.nan

        feat["post_meal_peak_excursion"] = float(np.median(peak_excursions)) if peak_excursions else np.nan

        # ── 4. Insulin metrics ───────────────────────────────────────
        total_bolus_day = pdf["bolus"].fillna(0).sum() / n_days
        total_smb_day = pdf["bolus_smb"].fillna(0).sum() / n_days
        total_basal_day = (pdf["actual_basal_rate"].fillna(0).sum() / STEPS_PER_HOUR) / n_days
        total_daily = total_bolus_day + total_basal_day
        feat["mean_daily_insulin"] = float(total_daily) if total_daily > 0 else np.nan
        feat["basal_fraction"] = float(total_basal_day / total_daily * 100) if total_daily > 0 else np.nan

        n_corrections = int((bolus_vals > CORRECTION_MIN_BOLUS).sum())
        feat["correction_freq_per_day"] = float(n_corrections / n_days)

        n_smb = int((pdf["bolus_smb"].fillna(0).values > 0.01).sum())
        feat["smb_freq_per_day"] = float(n_smb / n_days)

        # ── 5. Loop metrics ──────────────────────────────────────────
        enacted = pdf["loop_enacted_rate"].dropna()
        scheduled = pdf.loc[enacted.index, "scheduled_basal_rate"] if len(enacted) > 0 else pd.Series(dtype=float)
        if len(enacted) > 10 and len(scheduled) > 0:
            ratio = enacted / scheduled.replace(0, np.nan)
            ratio = ratio.dropna()
            feat["pct_time_suspend"] = float((ratio < 0.05).mean() * 100) if len(ratio) > 0 else 0.0
            feat["pct_time_aggressive"] = float((ratio > 1.5).mean() * 100) if len(ratio) > 0 else 0.0
        else:
            feat["pct_time_suspend"] = np.nan
            feat["pct_time_aggressive"] = np.nan

        feat["mean_iob"] = float(pdf["iob"].mean()) if pdf["iob"].notna().any() else np.nan

        # ── 6. Hypo metrics ──────────────────────────────────────────
        hypo_mask = (g < TIR_LOW).values if len(g) > 0 else np.array([])
        hypo_events = 0
        hypo_depths = []
        hypo_durations = []
        if len(hypo_mask) > 0:
            in_hypo = False
            event_bg = []
            gap_count = 0
            for i, is_low in enumerate(hypo_mask):
                if is_low:
                    if not in_hypo:
                        hypo_events += 1
                        in_hypo = True
                        event_bg = []
                    event_bg.append(g.values[i])
                    gap_count = 0
                else:
                    if in_hypo:
                        gap_count += 1
                        if gap_count >= HYPO_GAP_STEPS:
                            in_hypo = False
                            if event_bg:
                                hypo_depths.append(float(TIR_LOW - np.min(event_bg)))
                                hypo_durations.append(len(event_bg) * 5)  # minutes
                            event_bg = []
            # Close final event
            if in_hypo and event_bg:
                hypo_depths.append(float(TIR_LOW - np.min(event_bg)))
                hypo_durations.append(len(event_bg) * 5)

        feat["hypo_rate_per_day"] = float(hypo_events / n_days)
        feat["mean_hypo_depth"] = float(np.mean(hypo_depths)) if hypo_depths else 0.0
        feat["mean_hypo_duration_min"] = float(np.mean(hypo_durations)) if hypo_durations else 0.0

        rows.append(feat)

    feature_df = pd.DataFrame(rows)
    return feature_df


def print_feature_matrix(feature_df: pd.DataFrame):
    """Pretty-print the full feature matrix."""
    print("=" * 100)
    print("EXP-2541a: PATIENT FEATURE MATRIX")
    print("=" * 100)
    numeric_cols = [c for c in feature_df.columns if c not in ("patient_id", "controller")]
    print(f"\n{'Patient':>15} {'Ctrl':>4}", end="")
    short_names = {
        "tir": "TIR%", "tbr_70": "TBR70", "tbr_54": "TBR54",
        "tar_180": "TAR180", "tar_250": "TAR250",
        "mean_glucose": "MnGlc", "glucose_cv": "GlcCV",
        "profile_isf": "pISF", "effective_isf": "eISF",
        "isf_ratio": "ISFr", "isf_cv": "ISFCV",
        "profile_cr": "pCR", "effective_cr": "eCR",
        "cr_ratio": "CRr", "post_meal_peak_excursion": "PkExc",
        "mean_daily_insulin": "TDI", "basal_fraction": "Bas%",
        "correction_freq_per_day": "Corr/d", "smb_freq_per_day": "SMB/d",
        "pct_time_suspend": "Susp%", "pct_time_aggressive": "Aggr%",
        "mean_iob": "IOB",
        "hypo_rate_per_day": "Hypo/d", "mean_hypo_depth": "HypDp",
        "mean_hypo_duration_min": "HypDr",
    }
    for c in numeric_cols:
        print(f" {short_names.get(c, c[:6]):>7}", end="")
    print()
    print("-" * 100)
    for _, row in feature_df.iterrows():
        print(f"{row['patient_id']:>15} {row['controller']:>4}", end="")
        for c in numeric_cols:
            v = row[c]
            if pd.isna(v):
                print(f" {'--':>7}", end="")
            elif abs(v) >= 100:
                print(f" {v:>7.1f}", end="")
            else:
                print(f" {v:>7.2f}", end="")
        print()
    print()

    # Summary stats
    print("Feature summary statistics:")
    print(f"  {'Feature':<30} {'Mean':>8} {'Std':>8} {'Min':>8} {'Max':>8}")
    print(f"  {'-'*30} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for c in numeric_cols:
        vals = feature_df[c].dropna()
        if len(vals) > 0:
            print(f"  {c:<30} {vals.mean():>8.2f} {vals.std():>8.2f} "
                  f"{vals.min():>8.2f} {vals.max():>8.2f}")
    print()


# ── EXP-2541b: Clustering ───────────────────────────────────────────
FEATURE_COLS = [
    "tir", "tbr_70", "tbr_54", "tar_180", "tar_250",
    "mean_glucose", "glucose_cv",
    "profile_isf", "isf_ratio", "isf_cv",
    "profile_cr", "cr_ratio", "post_meal_peak_excursion",
    "mean_daily_insulin", "basal_fraction",
    "correction_freq_per_day", "smb_freq_per_day",
    "pct_time_suspend", "pct_time_aggressive", "mean_iob",
    "hypo_rate_per_day", "mean_hypo_depth", "mean_hypo_duration_min",
]


def run_clustering(feature_df: pd.DataFrame) -> dict:
    """K-means (k=2..5) + hierarchical, select optimal k via silhouette."""
    # Fill NaNs with column medians for clustering
    mat = feature_df[FEATURE_COLS].copy()
    for c in mat.columns:
        mat[c] = mat[c].fillna(mat[c].median())

    scaler = StandardScaler()
    X = scaler.fit_transform(mat.values)

    results: dict = {"n_patients": len(X), "n_features": len(FEATURE_COLS)}

    # K-means sweep
    km_results = {}
    best_k, best_sil = 2, -1
    for k in range(2, 6):
        km = KMeans(n_clusters=k, n_init=50, random_state=42, max_iter=500)
        labels = km.fit_predict(X)
        sil = silhouette_score(X, labels)
        inertia = float(km.inertia_)
        sizes = [int((labels == c).sum()) for c in range(k)]
        km_results[f"k={k}"] = {
            "silhouette": round(sil, 4),
            "inertia": round(inertia, 2),
            "cluster_sizes": sizes,
        }
        if sil > best_sil:
            best_sil = sil
            best_k = k

    results["kmeans_sweep"] = km_results
    results["optimal_k"] = best_k
    results["optimal_silhouette"] = round(best_sil, 4)

    # Final k-means with optimal k
    km_final = KMeans(n_clusters=best_k, n_init=50, random_state=42, max_iter=500)
    labels_km = km_final.fit_predict(X)

    # Hierarchical clustering (Ward)
    Z = linkage(X, method="ward")
    labels_hier = fcluster(Z, t=best_k, criterion="maxclust") - 1
    sil_hier = silhouette_score(X, labels_hier)
    results["hierarchical_silhouette"] = round(sil_hier, 4)

    # Agreement between methods
    from sklearn.metrics import adjusted_rand_score
    ari = adjusted_rand_score(labels_km, labels_hier)
    results["kmeans_vs_hierarchical_ARI"] = round(ari, 4)

    # Use best method
    if sil_hier > best_sil:
        labels_final = labels_hier
        results["chosen_method"] = "hierarchical"
        results["chosen_silhouette"] = round(sil_hier, 4)
    else:
        labels_final = labels_km
        results["chosen_method"] = "kmeans"
        results["chosen_silhouette"] = round(best_sil, 4)

    # PCA for visualization
    pca = PCA(n_components=min(3, X.shape[1]))
    X_pca = pca.fit_transform(X)
    results["pca_variance_explained"] = [round(v, 4) for v in pca.explained_variance_ratio_]

    patient_assignments = []
    for i, pid in enumerate(feature_df["patient_id"]):
        patient_assignments.append({
            "patient_id": pid,
            "controller": controller_type(pid),
            "cluster": int(labels_final[i]),
            "pca_1": round(float(X_pca[i, 0]), 3),
            "pca_2": round(float(X_pca[i, 1]), 3),
        })
    results["patient_assignments"] = patient_assignments

    # PCA loadings for interpretation
    loadings = {}
    for comp_i in range(min(3, pca.n_components_)):
        top_pos = sorted(range(len(FEATURE_COLS)),
                         key=lambda j: pca.components_[comp_i, j], reverse=True)[:5]
        top_neg = sorted(range(len(FEATURE_COLS)),
                         key=lambda j: pca.components_[comp_i, j])[:5]
        loadings[f"PC{comp_i+1}"] = {
            "variance_pct": round(pca.explained_variance_ratio_[comp_i] * 100, 1),
            "top_positive": [{
                "feature": FEATURE_COLS[j],
                "loading": round(float(pca.components_[comp_i, j]), 3),
            } for j in top_pos],
            "top_negative": [{
                "feature": FEATURE_COLS[j],
                "loading": round(float(pca.components_[comp_i, j]), 3),
            } for j in top_neg],
        }
    results["pca_loadings"] = loadings

    # Print clustering results
    print("=" * 100)
    print("EXP-2541b: CLUSTERING RESULTS")
    print("=" * 100)
    print(f"\nK-means silhouette sweep:")
    for k_label, km_r in km_results.items():
        marker = " ← optimal" if k_label == f"k={best_k}" else ""
        print(f"  {k_label}: silhouette={km_r['silhouette']:.4f}  "
              f"sizes={km_r['cluster_sizes']}{marker}")
    print(f"\nHierarchical (Ward, k={best_k}): silhouette={sil_hier:.4f}")
    print(f"K-means vs Hierarchical agreement (ARI): {ari:.4f}")
    print(f"Chosen method: {results['chosen_method']} "
          f"(silhouette={results['chosen_silhouette']:.4f})")
    print(f"\nPCA variance explained: "
          f"{', '.join(f'PC{i+1}={v*100:.1f}%' for i, v in enumerate(pca.explained_variance_ratio_))}")

    print(f"\nPatient cluster assignments:")
    print(f"  {'Patient':>15} {'Ctrl':>4} {'Cluster':>8}  {'PC1':>7} {'PC2':>7}")
    for pa in patient_assignments:
        print(f"  {pa['patient_id']:>15} {pa['controller']:>4} "
              f"{pa['cluster']:>8}  {pa['pca_1']:>7.2f} {pa['pca_2']:>7.2f}")
    print()

    return results, labels_final


# ── EXP-2541c: Phenotype Characterization ────────────────────────────
def characterize_phenotypes(feature_df: pd.DataFrame, labels: np.ndarray) -> dict:
    """Name and describe each cluster phenotype."""
    feature_df = feature_df.copy()
    feature_df["cluster"] = labels
    n_clusters = len(set(labels))

    # Compute per-cluster means
    cluster_profiles = {}
    for c in range(n_clusters):
        cdf = feature_df[feature_df["cluster"] == c]
        profile = {"n_patients": int(len(cdf)), "patient_ids": list(cdf["patient_id"])}
        for feat in FEATURE_COLS:
            vals = cdf[feat].dropna()
            profile[feat] = round(float(vals.mean()), 2) if len(vals) > 0 else None
        cluster_profiles[c] = profile

    # Global means for comparison
    global_means = {}
    for feat in FEATURE_COLS:
        vals = feature_df[feat].dropna()
        global_means[feat] = float(vals.mean()) if len(vals) > 0 else 0

    # Identify distinguishing features for each cluster
    phenotypes = {}
    for c in range(n_clusters):
        profile = cluster_profiles[c]
        deviations = {}
        for feat in FEATURE_COLS:
            g_mean = global_means[feat]
            c_mean = profile[feat]
            if c_mean is not None and g_mean != 0:
                dev = (c_mean - g_mean) / abs(g_mean) * 100
                deviations[feat] = dev

        # Sort by absolute deviation
        sorted_devs = sorted(deviations.items(), key=lambda x: abs(x[1]), reverse=True)
        top_traits = sorted_devs[:5]

        # Auto-name based on dominant traits
        name = _auto_name_phenotype(profile, global_means, top_traits)

        phenotypes[f"cluster_{c}"] = {
            "name": name,
            "n_patients": profile["n_patients"],
            "patient_ids": profile["patient_ids"],
            "mean_metrics": {k: v for k, v in profile.items()
                            if k not in ("n_patients", "patient_ids")},
            "distinguishing_traits": [
                {"feature": feat, "cluster_mean": round(profile[feat], 2) if profile[feat] is not None else None,
                 "global_mean": round(global_means[feat], 2),
                 "deviation_pct": round(dev, 1)}
                for feat, dev in top_traits
            ],
        }

    # Print
    print("=" * 100)
    print("EXP-2541c: PHENOTYPE CHARACTERIZATION")
    print("=" * 100)
    for ckey, pheno in phenotypes.items():
        print(f"\n  ┌─── {ckey}: \"{pheno['name']}\" ({pheno['n_patients']} patients) ───")
        print(f"  │ Patients: {', '.join(pheno['patient_ids'])}")
        print(f"  │")
        print(f"  │ Key metrics:")
        mm = pheno["mean_metrics"]
        print(f"  │   TIR={mm.get('tir','--'):.1f}%  TBR70={mm.get('tbr_70','--'):.1f}%  "
              f"TAR180={mm.get('tar_180','--'):.1f}%  MeanGlc={mm.get('mean_glucose','--'):.0f}")
        print(f"  │   ISF ratio={mm.get('isf_ratio','--')}  CR ratio={mm.get('cr_ratio','--')}  "
              f"Correction/d={mm.get('correction_freq_per_day','--')}")
        print(f"  │   Hypo/d={mm.get('hypo_rate_per_day','--')}  "
              f"HypoDepth={mm.get('mean_hypo_depth','--')}  "
              f"HypoDur={mm.get('mean_hypo_duration_min','--')}min")
        print(f"  │   TDI={mm.get('mean_daily_insulin','--')}  Basal%={mm.get('basal_fraction','--')}  "
              f"SMB/d={mm.get('smb_freq_per_day','--')}")
        print(f"  │")
        print(f"  │ Distinguishing traits (vs population mean):")
        for trait in pheno["distinguishing_traits"]:
            direction = "↑" if trait["deviation_pct"] > 0 else "↓"
            print(f"  │   {direction} {trait['feature']}: "
                  f"{trait['cluster_mean']} vs {trait['global_mean']} "
                  f"({trait['deviation_pct']:+.1f}%)")
        print(f"  └{'─' * 70}")

    # Therapy recommendations per phenotype
    recommendations = {}
    for ckey, pheno in phenotypes.items():
        mm = pheno["mean_metrics"]
        recs = []
        # ISF adequacy
        isf_r = mm.get("isf_ratio")
        if isf_r is not None and isf_r < 0.7:
            recs.append("ISF may be set too high (over-correcting). Consider reducing profile ISF.")
        elif isf_r is not None and isf_r > 1.3:
            recs.append("ISF may be set too low (under-correcting). Consider increasing profile ISF.")

        # CR adequacy
        cr_r = mm.get("cr_ratio")
        if cr_r is not None and cr_r < 0.8:
            recs.append("CR appears too aggressive (over-bolusing for meals). Consider raising CR value.")
        elif cr_r is not None and cr_r > 1.2:
            recs.append("CR appears too conservative (under-bolusing for meals). Consider lowering CR value.")

        # Hypo risk
        hypo_rate = mm.get("hypo_rate_per_day", 0) or 0
        if hypo_rate > 1.5:
            recs.append("HIGH hypo frequency. Review overnight basals and correction targets.")
        elif hypo_rate > 0.8:
            recs.append("Moderate hypo frequency. Monitor for loop-caused lows.")

        # Meal impact
        peak_exc = mm.get("post_meal_peak_excursion")
        if peak_exc is not None and peak_exc > 80:
            recs.append("Large post-meal spikes. Consider pre-bolusing or lowering CR.")
        elif peak_exc is not None and peak_exc < 30:
            recs.append("Excellent post-meal control.")

        # Basal dominance
        basal_frac = mm.get("basal_fraction")
        if basal_frac is not None and basal_frac > 70:
            recs.append("Basal-dominant insulin delivery. Verify bolus dosing is adequate.")
        elif basal_frac is not None and basal_frac < 40:
            recs.append("Bolus-dominant delivery. Verify basal rates are sufficient.")

        # Glucose variability
        gcv = mm.get("glucose_cv", 0) or 0
        if gcv > 40:
            recs.append("High glucose variability (CV>40%). Focus on meal timing and consistency.")

        if not recs:
            recs.append("Generally well-controlled. Continue current therapy.")

        recommendations[ckey] = recs
        phenotypes[ckey]["recommendations"] = recs

    print(f"\n  Therapy Recommendations per Phenotype:")
    for ckey, recs in recommendations.items():
        print(f"\n  {ckey} (\"{phenotypes[ckey]['name']}\"):")
        for r in recs:
            print(f"    • {r}")
    print()

    return phenotypes


def _auto_name_phenotype(profile: dict, global_means: dict,
                         top_traits: list) -> str:
    """Generate a descriptive phenotype name from dominant traits."""
    tags = []
    tir = profile.get("tir")
    tbr = profile.get("tbr_70", 0) or 0
    tar = profile.get("tar_180", 0) or 0
    hypo = profile.get("hypo_rate_per_day", 0) or 0
    gcv = profile.get("glucose_cv", 0) or 0
    tdi = profile.get("mean_daily_insulin")
    isf_r = profile.get("isf_ratio")

    if tir is not None and tir > 75:
        tags.append("Well-Controlled")
    elif tir is not None and tir < 50:
        tags.append("Unstable")

    if tbr > 5:
        tags.append("Hypo-Prone")
    elif hypo > 1.5:
        tags.append("Hypo-Prone")

    if tar > 40:
        tags.append("Hyperglycemic")

    if gcv > 40:
        tags.append("High-Variability")

    if tdi is not None and tdi > global_means.get("mean_daily_insulin", 50) * 1.3:
        tags.append("High-Insulin")
    elif tdi is not None and tdi < global_means.get("mean_daily_insulin", 50) * 0.7:
        tags.append("Low-Insulin")

    if isf_r is not None and isf_r < 0.7:
        tags.append("ISF-Miscalibrated")

    if not tags:
        tags.append("Moderate")

    return " / ".join(tags[:3])


# ── EXP-2541d: Controller Distribution ──────────────────────────────
def analyse_controller_distribution(feature_df: pd.DataFrame, labels: np.ndarray) -> dict:
    """Do NS and ODC patients cluster separately?"""
    feature_df = feature_df.copy()
    feature_df["cluster"] = labels
    n_clusters = len(set(labels))

    print("=" * 100)
    print("EXP-2541d: CONTROLLER DISTRIBUTION ACROSS PHENOTYPES")
    print("=" * 100)

    # Contingency table
    ctrl_types = feature_df["controller"].values
    ct = pd.crosstab(feature_df["cluster"], feature_df["controller"])
    print(f"\nContingency table:")
    print(ct.to_string())

    # Fisher's exact or chi-square test
    contingency = ct.values
    if contingency.shape == (2, 2):
        odds_ratio, p_val = stats.fisher_exact(contingency)
        test_name = "Fisher exact"
        stat = float(odds_ratio)
    else:
        chi2, p_val, dof, expected = stats.chi2_contingency(contingency)
        test_name = "Chi-square"
        stat = float(chi2)

    print(f"\n{test_name} test: statistic={stat:.4f}, p={p_val:.4f}")
    significant = p_val < 0.05
    print(f"Controller type {'DOES' if significant else 'does NOT'} significantly "
          f"predict phenotype (p={p_val:.4f})")

    # Per-cluster controller breakdown
    per_cluster = {}
    for c in range(n_clusters):
        cdf = feature_df[feature_df["cluster"] == c]
        ns_count = int((cdf["controller"] == "NS").sum())
        odc_count = int((cdf["controller"] == "ODC").sum())
        per_cluster[f"cluster_{c}"] = {
            "NS": ns_count, "ODC": odc_count,
            "NS_pct": round(ns_count / len(cdf) * 100, 1) if len(cdf) > 0 else 0,
            "ODC_pct": round(odc_count / len(cdf) * 100, 1) if len(cdf) > 0 else 0,
        }
        print(f"\n  Cluster {c}: NS={ns_count} ({per_cluster[f'cluster_{c}']['NS_pct']:.0f}%), "
              f"ODC={odc_count} ({per_cluster[f'cluster_{c}']['ODC_pct']:.0f}%)")

    result = {
        "test": test_name,
        "test_statistic": round(stat, 4),
        "p_value": round(p_val, 6),
        "significant": significant,
        "per_cluster": per_cluster,
        "interpretation": (
            f"Controller type {'significantly predicts' if significant else 'does not predict'} "
            f"phenotype membership (p={p_val:.4f}). "
            + ("NS and ODC patients cluster separately, suggesting controller-driven behaviour differences."
               if significant else
               "NS and ODC patients are distributed across phenotypes, suggesting patient physiology "
               "matters more than controller type.")
        ),
    }
    print(f"\n  Interpretation: {result['interpretation']}")
    print()
    return result


# ── EXP-2541e: Recommendation Personalisation ───────────────────────
def personalise_recommendations(feature_df: pd.DataFrame, labels: np.ndarray,
                                phenotypes: dict) -> dict:
    """Map each phenotype to the most relevant settings advisory."""
    feature_df = feature_df.copy()
    feature_df["cluster"] = labels

    print("=" * 100)
    print("EXP-2541e: PERSONALISED ADVISORY MAPPING")
    print("=" * 100)

    advisories = {
        "isf_nonlinearity_warning": {
            "description": "ISF varies with glucose level (power-law). "
                          "Fixed ISF may over-correct at high BG or under-correct at moderate BG.",
            "key_metric": "isf_cv",
            "higher_is_more_relevant": True,
        },
        "cr_adequacy_adjustment": {
            "description": "Carb ratio is miscalibrated vs actual meal response. "
                          "Dose adjustments needed.",
            "key_metric": "cr_ratio",
            "deviation_from_1_matters": True,
        },
        "hypo_risk_warning": {
            "description": "Frequent hypoglycemia events, potentially loop-caused. "
                          "Needs safety parameter review.",
            "key_metric": "hypo_rate_per_day",
            "higher_is_more_relevant": True,
        },
        "post_meal_spike_advisory": {
            "description": "Large post-meal glucose excursions. "
                          "Pre-bolus timing or CR adjustment recommended.",
            "key_metric": "post_meal_peak_excursion",
            "higher_is_more_relevant": True,
        },
        "glucose_variability_advisory": {
            "description": "High glucose variability (CV). "
                          "Consistency and timing improvements needed.",
            "key_metric": "glucose_cv",
            "higher_is_more_relevant": True,
        },
    }

    advisory_mapping = {}
    for adv_name, adv_info in advisories.items():
        cluster_scores = {}
        metric = adv_info["key_metric"]

        for ckey, pheno in phenotypes.items():
            mm = pheno.get("mean_metrics", {})
            val = mm.get(metric)
            if val is None:
                score = 0
            elif adv_info.get("deviation_from_1_matters"):
                score = abs(val - 1.0)
            elif adv_info.get("higher_is_more_relevant"):
                score = val
            else:
                score = val
            cluster_scores[ckey] = round(score, 3)

        most_relevant = max(cluster_scores, key=cluster_scores.get)
        advisory_mapping[adv_name] = {
            "description": adv_info["description"],
            "metric": metric,
            "cluster_scores": cluster_scores,
            "most_relevant_cluster": most_relevant,
            "most_relevant_phenotype": phenotypes[most_relevant]["name"],
            "score": cluster_scores[most_relevant],
        }

    print(f"\n  Advisory → Most Relevant Phenotype:\n")
    for adv_name, adv in advisory_mapping.items():
        print(f"  {adv_name}:")
        print(f"    Metric: {adv['metric']}")
        print(f"    Most relevant: {adv['most_relevant_cluster']} "
              f"(\"{adv['most_relevant_phenotype']}\") "
              f"score={adv['score']:.3f}")
        scores_str = ", ".join(f"{k}={v:.3f}" for k, v in adv["cluster_scores"].items())
        print(f"    All clusters: {scores_str}")
        print()

    # Per-patient advisory priority
    patient_advisories = []
    for _, row in feature_df.iterrows():
        pid = row["patient_id"]
        cluster = int(row["cluster"])
        ckey = f"cluster_{cluster}"
        pheno = phenotypes.get(ckey, {})
        recs = pheno.get("recommendations", [])
        top_advisory = None
        top_score = 0
        for adv_name, adv in advisory_mapping.items():
            score = adv["cluster_scores"].get(ckey, 0)
            if score > top_score:
                top_score = score
                top_advisory = adv_name
        patient_advisories.append({
            "patient_id": pid,
            "cluster": cluster,
            "phenotype": pheno.get("name", "Unknown"),
            "top_advisory": top_advisory,
            "recommendations": recs,
        })

    print(f"  Per-Patient Advisory Priority:")
    print(f"  {'Patient':>15} {'Phenotype':<30} {'Top Advisory':<30}")
    print(f"  {'-'*15} {'-'*30} {'-'*30}")
    for pa in patient_advisories:
        print(f"  {pa['patient_id']:>15} {pa['phenotype']:<30} {pa['top_advisory'] or 'none':<30}")
    print()

    return {
        "advisory_mapping": advisory_mapping,
        "patient_advisories": patient_advisories,
    }


# ── Main ─────────────────────────────────────────────────────────────
def run_experiment(tiny: bool = False):
    df = load_data(tiny=tiny)

    # EXP-2541a: Feature Matrix
    print("Computing per-patient features …")
    feature_df = compute_patient_features(df)
    print_feature_matrix(feature_df)

    # EXP-2541b: Clustering
    print("Running clustering analysis …")
    clustering_results, labels = run_clustering(feature_df)

    # EXP-2541c: Phenotype Characterization
    phenotypes = characterize_phenotypes(feature_df, labels)

    # EXP-2541d: Controller Distribution
    controller_results = analyse_controller_distribution(feature_df, labels)

    # EXP-2541e: Recommendation Personalisation
    personalisation_results = personalise_recommendations(feature_df, labels, phenotypes)

    # ── Assemble final results ───────────────────────────────────────
    results = {
        "experiment": "EXP-2541",
        "title": "Patient Phenotyping via Therapy Response Clustering",
        "n_patients": int(feature_df["patient_id"].nunique()),
        "feature_columns": FEATURE_COLS,
        "exp_2541a": {
            "feature_matrix": feature_df.to_dict(orient="records"),
            "summary_stats": {
                col: {
                    "mean": round(float(feature_df[col].mean()), 3),
                    "std": round(float(feature_df[col].std()), 3),
                    "min": round(float(feature_df[col].min()), 3),
                    "max": round(float(feature_df[col].max()), 3),
                } for col in FEATURE_COLS if feature_df[col].notna().any()
            },
        },
        "exp_2541b": clustering_results,
        "exp_2541c": phenotypes,
        "exp_2541d": controller_results,
        "exp_2541e": personalisation_results,
    }

    # Conclusions
    conclusions = []
    conclusions.append(
        f"Optimal clustering: k={clustering_results['optimal_k']} "
        f"(silhouette={clustering_results['optimal_silhouette']:.3f}, "
        f"method={clustering_results['chosen_method']})"
    )
    for ckey, pheno in phenotypes.items():
        conclusions.append(
            f"{ckey} \"{pheno['name']}\": {pheno['n_patients']} patients "
            f"[{', '.join(pheno['patient_ids'])}]"
        )
    conclusions.append(
        f"Controller vs phenotype: {controller_results['interpretation']}"
    )
    for adv_name, adv in personalisation_results["advisory_mapping"].items():
        conclusions.append(
            f"{adv_name} → most relevant for {adv['most_relevant_cluster']} "
            f"(\"{adv['most_relevant_phenotype']}\")"
        )
    results["conclusions"] = conclusions

    # Save
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / OUTPUT_FILE
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n{'='*100}")
    print(f"Results saved to {output_path}")
    print(f"{'='*100}")

    print(f"\n{'='*100}")
    print("CONCLUSIONS")
    print(f"{'='*100}")
    for i, c in enumerate(conclusions, 1):
        print(f"  {i}. {c}")
    print()

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EXP-2541: Patient Phenotyping")
    parser.add_argument("--tiny", action="store_true", help="Use tiny dataset")
    args = parser.parse_args()
    run_experiment(tiny=args.tiny)
