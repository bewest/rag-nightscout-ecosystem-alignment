"""therapy_trajectory_figures.py — visualizations for the therapy-trajectory
state harness (`therapy_trajectory_state.py`).

Generates a small set of reader-facing figures over the labeled-turn
cohort table so people can follow the state-aware-harness parallel
analysis without reading raw parquet output:

  1. State distribution (cohort-wide counts of the 5 rule-based labels).
  2. Mean TIR by state (sanity check that labels are behaviorally
     coherent -- resolved-like states should have higher TIR).
  3. Per-patient trajectory timeline: TIR over turns with state-colored
     markers and a TBR-safety overlay, so a reader can see a real
     patient's trajectory rather than only summary statistics.
  4. Insulin "wall"/overflow saturation by state (wall_pct distribution).
  5. Weekend-day-fraction vs TIR scatter, to show (not just claim) how
     weak or strong that association currently looks.

Each figure is returned as a self-contained base64 PNG, matching the
portable-HTML convention already used by ``clinical_decision_figures.py``.
Generation is defensive: it skips a figure rather than raising when data
is missing or too sparse.
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

_C_IMPROVING = "#2f855a"
_C_STABLE_GOOD = "#1f6f78"
_C_STABLE_POOR = "#e0a106"
_C_WORSENING = "#c0392b"
_C_UNKNOWN = "#9fa6ad"
_C_TBR = "#7e1d1d"
_C_INK = "#14505a"
_C_GRID = "#d9e2ec"

STATE_COLORS = {
    "improving": _C_IMPROVING,
    "stable_good": _C_STABLE_GOOD,
    "stable_poor": _C_STABLE_POOR,
    "worsening": _C_WORSENING,
    "unknown": _C_UNKNOWN,
}
STATE_ORDER = ["improving", "stable_good", "stable_poor", "worsening", "unknown"]


@dataclass
class TrajectoryFigure:
    title: str
    caption: str
    png_base64: str


def _fig_to_b64(fig) -> str:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color=_C_GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def state_distribution_figure(df: pd.DataFrame) -> Optional[TrajectoryFigure]:
    if df.empty:
        return None
    import matplotlib.pyplot as plt

    counts = df["state"].value_counts()
    order = [s for s in STATE_ORDER if s in counts.index]
    values = [counts[s] for s in order]
    colors = [STATE_COLORS[s] for s in order]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(order, values, color=colors, zorder=3)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v, str(v),
                ha="center", va="bottom", fontsize=9, color=_C_INK)
    ax.set_ylabel("Turns (72h windows)")
    ax.set_title("Turn outcome-label distribution", color=_C_INK, fontweight="bold")
    _style_axes(ax)
    plt.xticks(rotation=20, ha="right")

    n_patients = df["patient_id"].nunique()
    caption = (
        f"Rule-based, ADA-threshold, safety-first outcome label per 72h turn "
        f"across {n_patients} patient(s), {len(df)} turns total. This is a cheap "
        f"ex-post proxy (Candidly's first pipeline stage), not a fitted state model."
    )
    return TrajectoryFigure(
        title="Turn outcome-label distribution", caption=caption,
        png_base64=_fig_to_b64(fig),
    )


def mean_tir_by_state_figure(df: pd.DataFrame) -> Optional[TrajectoryFigure]:
    reliable = df[df["data_completeness"] >= 0.5]
    if reliable.empty:
        return None
    import matplotlib.pyplot as plt

    grouped = reliable.groupby("state")["tir"].mean()
    order = [s for s in STATE_ORDER if s in grouped.index]
    values = [grouped[s] for s in order]
    colors = [STATE_COLORS[s] for s in order]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(order, values, color=colors, zorder=3)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.0f}%",
                ha="center", va="bottom", fontsize=9, color=_C_INK)
    ax.axhline(70.0, color=_C_INK, linewidth=1, linestyle="--", zorder=2)
    ax.text(len(order) - 0.5, 71.5, "ADA TIR target (70%)", fontsize=8, color=_C_INK,
            ha="right")
    ax.set_ylabel("Mean TIR (%)")
    ax.set_title("Mean time-in-range by turn label", color=_C_INK, fontweight="bold")
    _style_axes(ax)
    plt.xticks(rotation=20, ha="right")

    caption = (
        "Sanity check that the rule-based label is behaviorally coherent: "
        "resolved-like states (improving, stable_good) should show higher "
        "TIR than unresolved-like states (stable_poor, worsening). This is "
        "descriptive, not causal — it does not by itself validate the label "
        "as predictive."
    )
    return TrajectoryFigure(
        title="Mean TIR by turn label", caption=caption, png_base64=_fig_to_b64(fig),
    )


def patient_timeline_figure(df: pd.DataFrame, patient_id: str) -> Optional[TrajectoryFigure]:
    patient_df = df[df["patient_id"] == patient_id].sort_values("turn_index")
    if patient_df.empty:
        return None
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 4))
    x = patient_df["start"]
    ax.plot(x, patient_df["tir"], color=_C_INK, linewidth=1.2, zorder=2, label="TIR (%)")
    ax.plot(x, patient_df["tbr_l1"] + patient_df["tbr_l2"], color=_C_TBR,
            linewidth=1.0, linestyle="--", zorder=2, label="TBR<70 (%)")
    colors = patient_df["state"].map(STATE_COLORS).fillna(_C_UNKNOWN)
    ax.scatter(x, patient_df["tir"], color=colors, s=28, zorder=3,
               edgecolor="white", linewidth=0.5)
    ax.axhline(70.0, color=_C_INK, linewidth=0.8, linestyle=":", zorder=1, alpha=0.6)
    ax.set_ylabel("%")
    ax.set_title(f"Patient {patient_id}: 72h-turn trajectory", color=_C_INK, fontweight="bold")
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    _style_axes(ax)
    fig.autofmt_xdate()

    caption = (
        f"Patient {patient_id}'s TIR (solid) and TBR<70 (dashed) per 72h turn, "
        f"marker color is the turn's rule-based label "
        f"({', '.join(f'{k}={v}' for k, v in STATE_COLORS.items())}). "
        f"{len(patient_df)} turns over "
        f"{(patient_df['end'].max() - patient_df['start'].min()).days} days."
    )
    return TrajectoryFigure(
        title=f"Patient {patient_id} trajectory timeline", caption=caption,
        png_base64=_fig_to_b64(fig),
    )


def saturation_by_state_figure(df: pd.DataFrame) -> Optional[TrajectoryFigure]:
    reliable = df[df["data_completeness"] >= 0.5]
    if reliable.empty or "saturation_wall_pct" not in reliable:
        return None
    import matplotlib.pyplot as plt

    grouped = reliable.groupby("state")["saturation_wall_pct"].mean()
    order = [s for s in STATE_ORDER if s in grouped.index]
    values = [grouped[s] for s in order]
    colors = [STATE_COLORS[s] for s in order]

    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(order, values, color=colors, zorder=3)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.0f}%",
                ha="center", va="bottom", fontsize=9, color=_C_INK)
    ax.set_ylabel("Mean saturation wall_pct")
    ax.set_title("Insulin \"wall\"/overflow saturation by turn label",
                 color=_C_INK, fontweight="bold")
    _style_axes(ax)
    plt.xticks(rotation=20, ha="right")

    caption = (
        "Mean insulin-saturation wall_pct (EXP-2660/2662: periods where IOB is "
        "high but glucose barely responds -- the closest validated proxy for "
        "an \"overflowing\" supply-vs-demand state) grouped by turn label. "
        "Higher wall_pct in worsening/stable_poor turns would suggest overflow "
        "saturation is a marker of a harder-to-control regime."
    )
    return TrajectoryFigure(
        title="Saturation (\"overflow\") by turn label", caption=caption,
        png_base64=_fig_to_b64(fig),
    )


def weekend_fraction_vs_tir_figure(df: pd.DataFrame) -> Optional[TrajectoryFigure]:
    reliable = df[df["data_completeness"] >= 0.5]
    if len(reliable) < 3 or reliable["weekend_day_fraction"].nunique() < 2:
        return None
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter(reliable["weekend_day_fraction"], reliable["tir"],
               color=_C_INK, alpha=0.5, s=20, zorder=3)
    corr = reliable["tir"].corr(reliable["weekend_day_fraction"])
    if len(reliable) > 1:
        coeffs = np.polyfit(reliable["weekend_day_fraction"], reliable["tir"], 1)
        xs = np.linspace(0, 1, 50)
        ax.plot(xs, np.polyval(coeffs, xs), color=_C_WORSENING, linewidth=1.2, zorder=2)
    ax.set_xlabel("Weekend-day fraction of turn")
    ax.set_ylabel("TIR (%)")
    ax.set_title(f"Weekend fraction vs TIR (r={corr:.2f})", color=_C_INK, fontweight="bold")
    _style_axes(ax)

    caption = (
        f"Each point is one turn. Correlation r={corr:.3f} across {len(reliable)} "
        f"reliable turns. Weekend-day fraction is carried as a continuous "
        f"per-turn feature (not a hard turn boundary) precisely so an "
        f"association like this can be checked rather than assumed -- a weak "
        f"correlation here is a real (if preliminary) finding, not a modeling "
        f"failure."
    )
    return TrajectoryFigure(
        title="Weekend fraction vs TIR", caption=caption, png_base64=_fig_to_b64(fig),
    )


def build_trajectory_figures(
    df: pd.DataFrame,
    example_patient_ids: list[str] | None = None,
    max_timelines: int = 3,
) -> list[TrajectoryFigure]:
    """Build the standard figure set for a cohort trajectory table."""
    figures: list[TrajectoryFigure] = []
    for fn in (state_distribution_figure, mean_tir_by_state_figure,
               saturation_by_state_figure, weekend_fraction_vs_tir_figure):
        fig = fn(df)
        if fig is not None:
            figures.append(fig)

    patient_ids = example_patient_ids or sorted(df["patient_id"].unique())[:max_timelines]
    for patient_id in patient_ids:
        fig = patient_timeline_figure(df, patient_id)
        if fig is not None:
            figures.append(fig)
    return figures
