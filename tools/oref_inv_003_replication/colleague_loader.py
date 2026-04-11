"""
colleague_loader — Load and wrap the colleague's OREF-INV-003 pre-trained LightGBM models.

Provides:
  1. Run their models on our data (after feature alignment)
  2. Compare their SHAP importance rankings with ours
  3. Use their model as a baseline for augmentation experiments
"""

import json
import logging
import pickle
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from oref_inv_003_replication import COLLEAGUE_DIR

logger = logging.getLogger(__name__)

MODEL_FILES = {
    "hypo": "hypo_lgbm.pkl",
    "hyper": "hyper_lgbm.pkl",
    "bg_change": "bg_change_lgbm.pkl",
}
META_FILE = "model_meta.json"


def normalize_shap_importance(shap_dict: dict[str, float]) -> dict[str, float]:
    """Convert raw SHAP values to percentage-of-total for fair comparison.

    Parameters
    ----------
    shap_dict : dict[str, float]
        Mapping of feature name → raw mean |SHAP| value.

    Returns
    -------
    dict[str, float]
        Mapping of feature name → percentage of total importance (0–100).
    """
    total = sum(abs(v) for v in shap_dict.values())
    if total == 0:
        return {k: 0.0 for k in shap_dict}
    return {k: abs(v) / total * 100.0 for k, v in shap_dict.items()}


def shap_rank_correlation(ranking_a: list[str], ranking_b: list[str]) -> float:
    """Compute Spearman rank correlation between two feature importance rankings.

    Both lists should contain feature names ordered by descending importance.
    Only features present in both rankings are compared.

    Parameters
    ----------
    ranking_a : list[str]
        Feature names sorted by importance (most important first).
    ranking_b : list[str]
        Feature names sorted by importance (most important first).

    Returns
    -------
    float
        Spearman rank correlation coefficient (−1 to +1).
    """
    common = [f for f in ranking_a if f in ranking_b]
    if len(common) < 3:
        warnings.warn(
            f"Only {len(common)} features in common — correlation unreliable."
        )
        return float("nan")

    rank_a = {f: i for i, f in enumerate(ranking_a)}
    rank_b = {f: i for i, f in enumerate(ranking_b)}

    a_ranks = [rank_a[f] for f in common]
    b_ranks = [rank_b[f] for f in common]

    corr, _ = spearmanr(a_ranks, b_ranks)
    return float(corr)


class ColleagueModels:
    """Wrapper around the colleague's OREF-INV-003 pre-trained LightGBM models.

    Loads the 3 models (hypo, hyper, bg_change) and their metadata from disk,
    providing a clean API for prediction, SHAP comparison, and diagnostics.

    Parameters
    ----------
    model_dir : str or None
        Path to the colleague's analysis directory. Defaults to COLLEAGUE_DIR
        from the package ``__init__.py``.
    """

    def __init__(self, model_dir: Optional[str] = None):
        model_dir = model_dir or COLLEAGUE_DIR
        self._dir = Path(model_dir)
        self._models_dir = self._dir / "models"

        if not self._dir.exists():
            raise FileNotFoundError(
                f"Colleague directory not found: {self._dir}\n"
                "Download the OREF-INV-003-v5-Analysis archive and place it at:\n"
                f"  {COLLEAGUE_DIR}"
            )
        if not self._models_dir.exists():
            raise FileNotFoundError(
                f"Models subdirectory not found: {self._models_dir}\n"
                "Expected structure: <dir>/models/{{model_meta.json, *.pkl}}"
            )

        # Load metadata
        meta_path = self._models_dir / META_FILE
        if not meta_path.exists():
            raise FileNotFoundError(f"Metadata file not found: {meta_path}")
        with open(meta_path) as f:
            self._meta: dict = json.load(f)

        self._features: list[str] = self._meta["features"]
        self._shap_importance: dict[str, dict[str, float]] = self._meta.get(
            "shap_importance", {}
        )

        # Load pickle models
        self._models: dict = {}
        for name, filename in MODEL_FILES.items():
            pkl_path = self._models_dir / filename
            if not pkl_path.exists():
                raise FileNotFoundError(f"Model file not found: {pkl_path}")
            with open(pkl_path, "rb") as f:
                self._models[name] = pickle.load(f)  # noqa: S301

        logger.info(
            "Loaded %d colleague models with %d features from %s",
            len(self._models),
            len(self._features),
            self._models_dir,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def features(self) -> list[str]:
        """The 32 feature names in model input order."""
        return list(self._features)

    @property
    def shap_importance(self) -> dict[str, dict[str, float]]:
        """SHAP importance dicts for hypo, hyper, bg_change."""
        return self._shap_importance

    @property
    def training_stats(self) -> dict:
        """Training metadata: n_train, n_users, AUCs, etc."""
        keys = [
            "n_train",
            "n_users_train",
            "n_features",
            "units",
            "hypo_threshold",
            "hyper_threshold",
            "cv_auc_hypo",
            "cv_f1_hypo",
            "cv_auc_hyper",
            "cv_r2_delta",
            "dropped_features",
            "n_dynisf_on",
            "n_dynisf_off",
        ]
        return {k: self._meta[k] for k in keys if k in self._meta}

    # ------------------------------------------------------------------
    # Prediction helpers
    # ------------------------------------------------------------------

    def _prepare_X(self, X: pd.DataFrame) -> pd.DataFrame:
        """Reorder columns to match model feature order, warn on missing."""
        missing = [f for f in self._features if f not in X.columns]
        if missing:
            warnings.warn(
                f"Missing {len(missing)} features (filled with 0): {missing}"
            )
        # Build aligned frame: keep order, fill missing with 0
        aligned = pd.DataFrame(0.0, index=X.index, columns=self._features)
        present = [f for f in self._features if f in X.columns]
        aligned[present] = X[present].values
        return aligned

    def predict_hypo(self, X: pd.DataFrame) -> np.ndarray:
        """Predict hypo probability. X must have columns matching self.features.

        Returns
        -------
        np.ndarray
            Predicted probability of hypoglycaemia (< 70 mg/dL within 4 h).
        """
        aligned = self._prepare_X(X)
        return self._models["hypo"].predict_proba(aligned)[:, 1]

    def predict_hyper(self, X: pd.DataFrame) -> np.ndarray:
        """Predict hyper probability.

        Returns
        -------
        np.ndarray
            Predicted probability of hyperglycaemia (> 180 mg/dL within 4 h).
        """
        aligned = self._prepare_X(X)
        return self._models["hyper"].predict_proba(aligned)[:, 1]

    def predict_bg_change(self, X: pd.DataFrame) -> np.ndarray:
        """Predict 4 h BG change (mg/dL).

        Returns
        -------
        np.ndarray
            Predicted BG delta in mg/dL.
        """
        aligned = self._prepare_X(X)
        return self._models["bg_change"].predict(aligned)

    def predict_all(self, X: pd.DataFrame) -> dict[str, np.ndarray]:
        """Run all 3 models.

        Returns
        -------
        dict[str, np.ndarray]
            Keys: ``hypo_prob``, ``hyper_prob``, ``bg_change``.
        """
        aligned = self._prepare_X(X)
        return {
            "hypo_prob": self._models["hypo"].predict_proba(aligned)[:, 1],
            "hyper_prob": self._models["hyper"].predict_proba(aligned)[:, 1],
            "bg_change": self._models["bg_change"].predict(aligned),
        }

    # ------------------------------------------------------------------
    # SHAP / importance utilities
    # ------------------------------------------------------------------

    def rank_features(self, model_name: str = "hypo") -> list[tuple[str, float]]:
        """Return features sorted by SHAP importance (descending).

        Parameters
        ----------
        model_name : str
            One of ``'hypo'``, ``'hyper'``, ``'bg_change'``.

        Returns
        -------
        list[tuple[str, float]]
            ``(feature_name, importance)`` pairs, highest first.
        """
        if model_name not in self._shap_importance:
            raise KeyError(
                f"No SHAP data for '{model_name}'. "
                f"Available: {list(self._shap_importance)}"
            )
        items = self._shap_importance[model_name]
        return sorted(items.items(), key=lambda kv: abs(kv[1]), reverse=True)

    def compare_importance(
        self,
        our_shap: dict[str, float],
        model_name: str = "hypo",
    ) -> pd.DataFrame:
        """Compare our SHAP rankings with theirs.

        Parameters
        ----------
        our_shap : dict[str, float]
            Our feature → mean |SHAP| mapping.
        model_name : str
            Which colleague model to compare against.

        Returns
        -------
        pd.DataFrame
            Columns: feature, their_rank, their_importance,
            our_rank, our_importance, rank_delta.
        """
        their_ranked = self.rank_features(model_name)
        their_order = [f for f, _ in their_ranked]
        their_imp = {f: v for f, v in their_ranked}

        our_ranked = sorted(our_shap.items(), key=lambda kv: abs(kv[1]), reverse=True)
        our_order = [f for f, _ in our_ranked]
        our_imp = dict(our_ranked)

        all_features = list(dict.fromkeys(their_order + our_order))

        rows = []
        for feat in all_features:
            t_rank = their_order.index(feat) + 1 if feat in their_order else None
            o_rank = our_order.index(feat) + 1 if feat in our_order else None
            delta = (t_rank - o_rank) if (t_rank is not None and o_rank is not None) else None
            rows.append(
                {
                    "feature": feat,
                    "their_rank": t_rank,
                    "their_importance": their_imp.get(feat),
                    "our_rank": o_rank,
                    "our_importance": our_imp.get(feat),
                    "rank_delta": delta,
                }
            )
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def summary(self) -> str:
        """Return a human-readable summary of the colleague's models."""
        stats = self.training_stats
        lines = [
            "═══ OREF-INV-003 Colleague Models ═══",
            f"  Directory   : {self._dir}",
            f"  Features    : {stats.get('n_features', '?')}",
            f"  Training N  : {stats.get('n_train', '?'):,}",
            f"  Users       : {stats.get('n_users_train', '?')}",
            f"  Units       : {stats.get('units', '?')}",
            "",
            "  Performance:",
            f"    Hypo  AUC : {stats.get('cv_auc_hypo', '?')}",
            f"    Hypo  F1  : {stats.get('cv_f1_hypo', '?')}",
            f"    Hyper AUC : {stats.get('cv_auc_hyper', '?')}",
            f"    ΔBG   R²  : {stats.get('cv_r2_delta', '?')}",
            "",
            f"  DynISF on   : {stats.get('n_dynisf_on', '?'):,}",
            f"  DynISF off  : {stats.get('n_dynisf_off', '?'):,}",
            f"  Dropped     : {stats.get('dropped_features', [])}",
            "",
            "  Top-5 features (hypo SHAP):",
        ]
        if "hypo" in self._shap_importance:
            for feat, val in self.rank_features("hypo")[:5]:
                lines.append(f"    {feat:30s}  {val:.4f}")
        lines.append("")
        return "\n".join(lines)


# ======================================================================
# CLI entry point
# ======================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    cm = ColleagueModels()
    print(cm.summary())

    for model_name in ("hypo", "hyper", "bg_change"):
        ranked = cm.rank_features(model_name)
        print(f"── Top-10 features ({model_name}) ──")
        for i, (feat, val) in enumerate(ranked[:10], 1):
            print(f"  {i:2d}. {feat:30s}  {val:.4f}")
        print()
