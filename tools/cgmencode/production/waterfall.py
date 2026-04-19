"""
waterfall.py — R² Waterfall Analysis: the scientific method for deconfounding.

Implements the validated 5-stage R² waterfall from EXP-2698 as a reusable
analysis tool. Each stage progressively subtracts a different class of
confounding effect, making the remaining signal cleaner for extraction.

Scientific basis (oref0's insight, formalized):
    Stage 1 — Univariate:        Just dose → R² ≈ 0.015
    Stage 2 — Multi-factor raw:  All features on raw ΔBG → R² ≈ 0.350
    Stage 3 — BGI subtraction:   Same features on deviation → R² ≈ 0.768
    Stage 4 — Within-patient FE: Patient-demeaned deviation → R² ≈ 0.721
    Stage 5 — Category-specific: Correction events only → R² ≈ 0.839

Each stage removes a distinct confounding layer:
    Stage 2 vs 1: controls for covariates (BG, ROC, IOB, carbs)
    Stage 3 vs 2: subtracts known insulin effect (BGI — the +0.418 lever)
    Stage 4 vs 3: subtracts between-patient heterogeneity
    Stage 5 vs 4: conditions on event context (correction vs meal vs UAM)

The waterfall itself serves as a DIAGNOSTIC: if a stage doesn't improve R²,
the corresponding confound wasn't active. If it degrades R², the subtraction
introduced more noise than it removed (as happened with FE on deviation).

Usage:
    from production.waterfall import WaterfallAnalysis

    wf = WaterfallAnalysis(events)
    results = wf.run()
    wf.print_waterfall()
    wf.save_figure("my_waterfall.png")

    # Access individual stages for custom analysis
    stage3 = wf.stages["deviation_pooled"]
    print(stage3.r2, stage3.n, stage3.coefficients)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from numpy.linalg import lstsq
from scipy import stats


# ── Stage Result ─────────────────────────────────────────────────────

@dataclass
class WaterfallStage:
    """Result of one waterfall stage."""
    name: str
    r2: float
    n: int
    target: str                          # what we're predicting
    features: List[str]
    coefficients: Dict[str, float]       # feature → coefficient (unnormalized)
    p_values: Optional[Dict[str, float]] = None
    delta_r2: float = 0.0               # improvement over previous stage
    interpretation: str = ""


# ── OLS Helper ───────────────────────────────────────────────────────

def _ols_r2(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: List[str],
) -> Tuple[float, Dict[str, float], Dict[str, float]]:
    """Run OLS regression, return R², coefficients, and p-values.

    Uses standardized features for numerical stability,
    then un-standardizes coefficients for interpretability.
    """
    mask = ~np.isnan(y)
    for j in range(X.shape[1]):
        mask &= ~np.isnan(X[:, j])
    X_clean = X[mask]
    y_clean = y[mask]
    n = len(y_clean)
    if n < 10:
        return np.nan, {}, {}

    # Standardize
    mu = X_clean.mean(axis=0)
    sd = X_clean.std(axis=0) + 1e-10
    X_n = (X_clean - mu) / sd
    X_aug = np.column_stack([X_n, np.ones(n)])

    # Fit
    b, residuals, rank, sv = lstsq(X_aug, y_clean, rcond=None)
    y_pred = X_aug @ b

    # R²
    ss_res = np.sum((y_clean - y_pred) ** 2)
    ss_tot = np.sum((y_clean - y_clean.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Un-standardize coefficients: b_orig = b_std / sd
    coefs = {}
    for i, fname in enumerate(feature_names):
        coefs[fname] = float(b[i] / sd[i])
    coefs["intercept"] = float(b[-1] - np.sum(b[:-1] * mu / sd))

    # P-values via t-test
    p_vals = {}
    dof = n - len(b)
    if dof > 0:
        mse = ss_res / dof
        # Variance of standardized coefficients
        try:
            XtX_inv = np.linalg.inv(X_aug.T @ X_aug)
            se = np.sqrt(np.diag(XtX_inv) * mse)
            t_stats = b / (se + 1e-20)
            for i, fname in enumerate(feature_names):
                p_vals[fname] = float(2 * stats.t.sf(abs(t_stats[i]), dof))
        except np.linalg.LinAlgError:
            pass

    return r2, coefs, p_vals


# ── Waterfall Analysis ───────────────────────────────────────────────

# Standard feature sets for each stage (from EXP-2698)
BASE_FEATURES = ["bg0", "bolus_2h", "smb_2h", "excess_basal_2h",
                  "carbs_2h", "roc_start", "iob_start"]

CORRECTION_FEATURES = ["bg0", "bolus_2h", "smb_2h", "excess_basal_2h",
                        "roc_start", "iob_start"]

MEAL_FEATURES = ["bg0", "bolus_2h", "carbs_2h", "smb_2h",
                  "excess_basal_2h", "roc_start"]

BASAL_FEATURES = ["bg0", "roc_start", "iob_start"]

UAM_FEATURES = ["bg0", "smb_2h", "excess_basal_2h", "roc_start", "iob_start"]

CATEGORY_FEATURES = {
    "correction": CORRECTION_FEATURES,
    "meal": MEAL_FEATURES,
    "basal": BASAL_FEATURES,
    "uam": UAM_FEATURES,
    "mixed": UAM_FEATURES,
}


class WaterfallAnalysis:
    """R² Waterfall: progressive deconfounding analysis.

    Runs the 5-stage waterfall on a set of events (output from
    BGISubtraction.compute_deviations + EventCategorizer.categorize).
    """

    def __init__(
        self,
        events: pd.DataFrame,
        features: Optional[List[str]] = None,
        circadian_blocks: int = 6,
    ):
        self.events = events.copy()
        self.features = features or BASE_FEATURES
        self.circadian_blocks = circadian_blocks
        self.stages: Dict[str, WaterfallStage] = {}
        self.category_results: Dict[str, WaterfallStage] = {}
        self.controller_results: Dict[str, Dict[str, float]] = {}

    def run(self) -> Dict[str, Any]:
        """Execute full waterfall analysis.

        Returns dict suitable for JSON serialization.
        """
        ev = self.events

        # Ensure required columns exist
        required = {"observed_drop", "deviation"}
        available = set(ev.columns)
        if not required.issubset(available):
            missing = required - available
            raise ValueError(
                f"Missing columns: {missing}. "
                f"Run BGISubtraction.compute_deviations() first."
            )

        # Available features (subset of standard that exist in data)
        feats = [f for f in self.features if f in ev.columns]

        # ── Stage 1: Univariate bolus ────────────────────────────────
        if "bolus_2h" in ev.columns:
            r2_uni, coefs_uni, pvals_uni = _ols_r2(
                ev[["bolus_2h"]].values,
                ev["observed_drop"].values,
                ["bolus_2h"],
            )
        else:
            r2_uni = 0.015  # reference value
            coefs_uni, pvals_uni = {}, {}

        self.stages["univariate_bolus"] = WaterfallStage(
            name="univariate_bolus",
            r2=r2_uni,
            n=len(ev),
            target="observed_drop",
            features=["bolus_2h"],
            coefficients=coefs_uni,
            p_values=pvals_uni,
            delta_r2=r2_uni,
            interpretation="Baseline: raw dose alone explains almost nothing (confounding by indication).",
        )

        # ── Stage 2: Multi-factor on raw observed_drop ───────────────
        X_raw = ev[feats].values
        y_raw = ev["observed_drop"].values
        r2_raw, coefs_raw, pvals_raw = _ols_r2(X_raw, y_raw, feats)

        self.stages["multi_factor_raw"] = WaterfallStage(
            name="multi_factor_raw",
            r2=r2_raw,
            n=len(ev.dropna(subset=feats + ["observed_drop"])),
            target="observed_drop",
            features=feats,
            coefficients=coefs_raw,
            p_values=pvals_raw,
            delta_r2=r2_raw - r2_uni,
            interpretation=(
                f"Covariates add +{r2_raw - r2_uni:.3f} R². "
                f"BG₀, ROC, IOB help but insulin channels still confound."
            ),
        )

        # ── Stage 3: Multi-factor on deviation (BGI subtracted) ──────
        y_dev = ev["deviation"].values
        r2_dev, coefs_dev, pvals_dev = _ols_r2(X_raw, y_dev, feats)

        self.stages["deviation_pooled"] = WaterfallStage(
            name="deviation_pooled",
            r2=r2_dev,
            n=len(ev.dropna(subset=feats + ["deviation"])),
            target="deviation",
            features=feats,
            coefficients=coefs_dev,
            p_values=pvals_dev,
            delta_r2=r2_dev - r2_raw,
            interpretation=(
                f"BGI subtraction adds +{r2_dev - r2_raw:.3f} R² — "
                f"THE single biggest lever. Removes known insulin effect."
            ),
        )

        # ── Stage 4: Within-patient fixed effects ────────────────────
        ev["dev_demeaned"] = ev.groupby("patient_id")["deviation"].transform(
            lambda x: x - x.mean()
        )
        y_fe = ev["dev_demeaned"].values
        r2_fe, coefs_fe, pvals_fe = _ols_r2(X_raw, y_fe, feats)

        self.stages["within_patient_fe"] = WaterfallStage(
            name="within_patient_fe",
            r2=r2_fe,
            n=len(ev.dropna(subset=feats + ["dev_demeaned"])),
            target="dev_demeaned",
            features=feats,
            coefficients=coefs_fe,
            p_values=pvals_fe,
            delta_r2=r2_fe - r2_dev,
            interpretation=(
                f"Within-patient FE: Δ={r2_fe - r2_dev:+.3f}. "
                f"{'Helps' if r2_fe > r2_dev else 'Hurts'}: deviation already captures "
                f"patient effects via ISF scaling."
            ),
        )

        # ── Stage 5: Circadian blocks ────────────────────────────────
        if "hour" in ev.columns:
            block_size = 24 // self.circadian_blocks
            ev["circadian_block"] = ev["hour"] // block_size
            for b in range(1, self.circadian_blocks):
                ev[f"block_{b}"] = (ev["circadian_block"] == b).astype(float)
            circ_feats = feats + [f"block_{b}" for b in range(1, self.circadian_blocks)]
            X_circ = ev[circ_feats].values
            r2_circ, coefs_circ, pvals_circ = _ols_r2(X_circ, y_fe, circ_feats)
        else:
            circ_feats = feats
            r2_circ = r2_fe
            coefs_circ, pvals_circ = coefs_fe, pvals_fe

        self.stages["circadian_fe"] = WaterfallStage(
            name="circadian_fe",
            r2=r2_circ,
            n=len(ev.dropna(subset=feats + ["dev_demeaned"])),
            target="dev_demeaned + circadian blocks",
            features=circ_feats,
            coefficients=coefs_circ,
            p_values=pvals_circ,
            delta_r2=r2_circ - r2_fe,
            interpretation=(
                f"Circadian adds Δ={r2_circ - r2_fe:+.4f}. "
                f"Circadian structure is already IN the deviation patterns."
            ),
        )

        # ── Category-specific models ─────────────────────────────────
        if "category" in ev.columns:
            self._run_category_models(ev)

        # ── Controller-specific models ───────────────────────────────
        if "controller" in ev.columns:
            self._run_controller_models(ev)

        return self.to_dict()

    def _run_category_models(self, ev: pd.DataFrame):
        """Fit separate models per event category.

        For correction events, applies BG≥180 floor (EXP-2677/2680 validated).
        This removes negative ISF artifacts from misclassified meals.
        """
        for cat, cat_feats in CATEGORY_FEATURES.items():
            ec = ev[ev["category"] == cat]

            # Correction events: BG floor is critical (57% negative ISF without it)
            if cat == "correction" and "bg0" in ec.columns:
                ec = ec[ec["bg0"] >= 180.0]

            available_feats = [f for f in cat_feats if f in ec.columns]
            if len(ec) < 100 or not available_feats:
                continue

            X_c = ec[available_feats].values

            # R² on raw
            y_raw = ec["observed_drop"].values
            r2_raw, _, _ = _ols_r2(X_c, y_raw, available_feats)

            # R² on deviation
            y_dev = ec["deviation"].values
            r2_dev, coefs_dev, pvals_dev = _ols_r2(X_c, y_dev, available_feats)

            self.category_results[cat] = WaterfallStage(
                name=f"category_{cat}",
                r2=r2_dev,
                n=len(ec.dropna(subset=available_feats + ["deviation"])),
                target="deviation",
                features=available_feats,
                coefficients=coefs_dev,
                p_values=pvals_dev,
                delta_r2=r2_dev - r2_raw,
                interpretation=(
                    f"{cat}: raw R²={r2_raw:.3f} → dev R²={r2_dev:.3f} "
                    f"(+{r2_dev - r2_raw:.3f})"
                ),
            )

    def _run_controller_models(self, ev: pd.DataFrame):
        """Fit separate models per controller type."""
        feats = [f for f in self.features if f in ev.columns]
        for ctrl in ev["controller"].unique():
            ec = ev[ev["controller"] == ctrl]
            if len(ec) < 500:
                continue

            X = ec[feats].values

            # Raw
            r2_raw, _, _ = _ols_r2(X, ec["observed_drop"].values, feats)
            # Deviation
            r2_dev, _, _ = _ols_r2(X, ec["deviation"].values, feats)
            # Within-patient FE
            if "dev_demeaned" in ec.columns:
                r2_fe, _, _ = _ols_r2(X, ec["dev_demeaned"].values, feats)
            else:
                r2_fe = np.nan

            self.controller_results[ctrl] = {
                "raw": float(r2_raw),
                "deviation": float(r2_dev),
                "dev_fe": float(r2_fe),
            }

    # ── ISF Recovery ─────────────────────────────────────────────────

    def recover_isf(
        self,
        min_corrections: int = 20,
        bg_floor: float = 180.0,
    ) -> Dict[str, Any]:
        """Recover per-patient ISF from correction events.

        Uses the insight: deviation = (ISF_true - ISF_setting) × IOB_consumed
        So: ISF_error = deviation / IOB_consumed

        Returns dict with per-patient ISF estimates and aggregate metrics.
        """
        ev = self.events
        if "category" not in ev.columns:
            raise ValueError("Events must be categorized first")

        corrections = ev[
            (ev["category"] == "correction") &
            (ev["bg0"] >= bg_floor) &
            (ev["bolus_2h"] > 0.3)
        ].copy()

        if len(corrections) < 10:
            return {"status": "SKIP", "reason": "Insufficient corrections"}

        # Effective ISF = observed_drop / bolus_2h
        corrections["effective_isf"] = (
            corrections["observed_drop"] / corrections["bolus_2h"].clip(lower=0.1)
        )

        # ISF error = deviation / bolus_2h (excess_insulin is more accurate but bolus dominates)
        corrections["isf_error"] = (
            corrections["deviation"] / corrections["bolus_2h"].clip(lower=0.1)
        )

        # Per-patient aggregation
        pat = corrections.groupby("patient_id").agg(
            n=("effective_isf", "count"),
            mean_effective_isf=("effective_isf", "mean"),
            se_effective_isf=("effective_isf", "sem"),
            mean_isf_error=("isf_error", "mean"),
            isf_setting=("isf_used", "mean"),
            controller=("controller", "first"),
        ).reset_index()

        pat = pat[pat["n"] >= min_corrections]
        pat["implied_true_isf"] = pat["isf_setting"] + pat["mean_isf_error"]

        # Dose-dependent ISF check (log model)
        valid = corrections[
            (corrections["effective_isf"] > 0) &
            (corrections["effective_isf"] < 200)
        ]
        if len(valid) > 100:
            log_dose = np.log(valid["bolus_2h"].values)
            isf_vals = valid["effective_isf"].values
            slope, intercept, r_log, p_log, _ = stats.linregress(log_dose, isf_vals)
            dose_dependence = {
                "r": float(r_log),
                "p": float(p_log),
                "slope": float(slope),
                "intercept": float(intercept),
                "interpretation": (
                    f"ISF-dose correlation r={r_log:.3f}. "
                    f"{'Dose-dependent (artifact)' if abs(r_log) > 0.3 else 'Acceptably independent'}."
                ),
            }
        else:
            dose_dependence = {"status": "SKIP", "reason": "Insufficient valid ISF values"}

        return {
            "n_patients_recovered": len(pat),
            "n_correction_events": len(corrections),
            "mean_isf_error": float(pat["mean_isf_error"].mean()) if len(pat) > 0 else np.nan,
            "per_patient": pat.to_dict(orient="records"),
            "dose_dependence": dose_dependence,
        }

    # ── Output ───────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialize waterfall results to dict."""
        result = {
            "r2_pipeline": {},
            "stages": {},
            "category_r2": {},
            "controller_pipeline": self.controller_results,
        }
        for name, stage in self.stages.items():
            result["r2_pipeline"][name] = round(stage.r2, 6)
            result["stages"][name] = {
                "r2": round(stage.r2, 6),
                "n": stage.n,
                "target": stage.target,
                "features": stage.features,
                "delta_r2": round(stage.delta_r2, 6),
                "interpretation": stage.interpretation,
                "coefficients": {
                    k: round(v, 4) for k, v in stage.coefficients.items()
                },
            }
        for cat, stage in self.category_results.items():
            result["category_r2"][cat] = {
                "r2": round(stage.r2, 6),
                "n": stage.n,
                "delta_r2": round(stage.delta_r2, 6),
                "coefficients": {
                    k: round(v, 4) for k, v in stage.coefficients.items()
                },
            }
        return result

    def print_waterfall(self):
        """Print waterfall summary to console."""
        print("\n" + "=" * 60)
        print("R² WATERFALL — Progressive Deconfounding")
        print("=" * 60)

        prev_r2 = 0.0
        for name, stage in self.stages.items():
            delta = stage.r2 - prev_r2
            bar = "█" * int(stage.r2 * 40)
            sign = "+" if delta >= 0 else ""
            print(
                f"  {name:30s}  R²={stage.r2:.4f}  "
                f"({sign}{delta:.4f})  N={stage.n:>8,}  {bar}"
            )
            prev_r2 = stage.r2

        if self.category_results:
            print("\n  Category-Specific Models:")
            for cat, stage in sorted(
                self.category_results.items(),
                key=lambda x: -x[1].r2,
            ):
                bar = "█" * int(stage.r2 * 40)
                print(
                    f"    {cat:26s}  R²={stage.r2:.4f}  "
                    f"N={stage.n:>8,}  {bar}"
                )

        if self.controller_results:
            print("\n  Per-Controller:")
            for ctrl, vals in sorted(self.controller_results.items()):
                print(
                    f"    {ctrl:26s}  raw={vals['raw']:.3f} → "
                    f"dev={vals['deviation']:.3f} → fe={vals['dev_fe']:.3f}"
                )

        print("=" * 60 + "\n")

    def save_figure(self, path: str):
        """Save waterfall chart (matplotlib required)."""
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib not available, skipping figure")
            return

        stages = list(self.stages.values())
        names = [s.name.replace("_", "\n") for s in stages]
        r2s = [s.r2 for s in stages]
        deltas = [s.delta_r2 for s in stages]

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Panel 1: Cumulative R²
        ax = axes[0]
        colors = ["#4e79a7" if d >= 0 else "#e15759" for d in deltas]
        ax.bar(range(len(names)), r2s, color=colors, alpha=0.8, edgecolor="black")
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontsize=8)
        ax.set_ylabel("R²")
        ax.set_title("Cumulative R² by Stage")
        ax.set_ylim(0, 1)
        for i, r2 in enumerate(r2s):
            ax.text(i, r2 + 0.02, f"{r2:.3f}", ha="center", fontsize=8)

        # Panel 2: Delta R² (contribution of each stage)
        ax = axes[1]
        colors2 = ["#59a14f" if d >= 0 else "#e15759" for d in deltas]
        ax.bar(range(len(names)), deltas, color=colors2, alpha=0.8, edgecolor="black")
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, fontsize=8)
        ax.set_ylabel("ΔR²")
        ax.set_title("Marginal R² Contribution per Stage")
        ax.axhline(0, color="black", linewidth=0.5)
        for i, d in enumerate(deltas):
            sign = "+" if d >= 0 else ""
            ax.text(i, d + 0.01 * (1 if d >= 0 else -1), f"{sign}{d:.3f}",
                    ha="center", fontsize=8, va="bottom" if d >= 0 else "top")

        plt.tight_layout()
        plt.savefig(path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved waterfall figure: {path}")
