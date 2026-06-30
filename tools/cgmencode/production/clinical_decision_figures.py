"""clinical_decision_figures.py — Data visualizations for the decision report.

Generates a small set of decision-relevant, confidence-building figures so
readers can follow the analysis and see the data behind each claim:

  * Time-in-range distribution (supports the insulin-sufficiency overview).
  * Ambulatory Glucose Profile / AGP (median + IQR + 10-90 band by hour).
  * Overnight glucose profile (00:00-06:00) for basal-adequacy context.

Each figure is returned as a :class:`ReportFigure` carrying a self-contained
base64 PNG so the HTML deliverable is portable. Generation is defensive: it
degrades gracefully (skips a figure rather than raising) when data is
missing or too sparse, and requires matplotlib only at call time.

Palette matches the HTML renderer's clinical look (teal/slate ink with the
standard AGP range colors: red lows, green target, amber/orange highs).
"""
from __future__ import annotations

import base64
import io
from typing import List, Optional

import numpy as np

from .clinical_decision_report import ReportFigure

# ── Clinical palette ──────────────────────────────────────────────────
_C_VERY_LOW = "#7e1d1d"
_C_LOW = "#c0392b"
_C_TARGET = "#2f855a"
_C_HIGH = "#e0a106"
_C_VERY_HIGH = "#b7791f"
_C_INK = "#14505a"
_C_BRAND = "#1f6f78"
_C_BAND = "#9fc7cc"
_C_GRID = "#d9e2ec"

_TARGET_LO = 70.0
_TARGET_HI = 180.0


def _fig_to_b64(fig) -> str:
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _clean(glucose: np.ndarray) -> np.ndarray:
    g = np.asarray(glucose, dtype=float)
    return g[np.isfinite(g)]


def _tir_distribution_figure(glucose: np.ndarray) -> Optional[ReportFigure]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    valid = _clean(glucose)
    if valid.size < 12:
        return None

    n = valid.size
    bands = [
        ("Very low (<54)", float(np.mean(valid < 54)), _C_VERY_LOW),
        ("Low (54-69)", float(np.mean((valid >= 54) & (valid < 70))), _C_LOW),
        ("In range (70-180)",
         float(np.mean((valid >= 70) & (valid <= 180))), _C_TARGET),
        ("High (181-250)",
         float(np.mean((valid > 180) & (valid <= 250))), _C_HIGH),
        ("Very high (>250)", float(np.mean(valid > 250)), _C_VERY_HIGH),
    ]

    fig, ax = plt.subplots(figsize=(7.2, 1.7))
    left = 0.0
    for label, frac, color in bands:
        pct = frac * 100.0
        ax.barh(0, pct, left=left, color=color, edgecolor="white",
                height=0.6)
        if pct >= 6:
            ax.text(left + pct / 2.0, 0, f"{pct:.0f}%", ha="center",
                    va="center", color="white", fontsize=9,
                    fontweight="bold")
        left += pct

    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    ax.set_xlabel("Percent of time", fontsize=9, color="#52606d")
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(colors="#52606d", labelsize=8)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in bands]
    ax.legend(handles, [b[0] for b in bands], ncol=5, fontsize=7.5,
              loc="upper center", bbox_to_anchor=(0.5, -0.5),
              frameon=False, handlelength=1.0, columnspacing=1.0)
    fig.tight_layout()

    return ReportFigure(
        section="insulin_sufficiency",
        title="Time-in-range distribution",
        caption=(f"Share of time in each glycemic band over {n:,} readings. "
                 "Green is the 70-180 mg/dL target; reds are lows, "
                 "ambers are highs."),
        filename="fig_time_in_range.png",
        png_base64=_fig_to_b64(fig),
        alt="Stacked bar of time spent in each glucose range.")


def _hourly_percentiles(glucose: np.ndarray, hours: np.ndarray,
                        hour_values):
    g = np.asarray(glucose, dtype=float)
    h = np.asarray(hours, dtype=float)
    out = {}
    for hv in hour_values:
        mask = (np.floor(h) == hv) & np.isfinite(g)
        if mask.sum() >= 6:
            seg = g[mask]
            out[hv] = (
                np.percentile(seg, 10), np.percentile(seg, 25),
                np.percentile(seg, 50), np.percentile(seg, 75),
                np.percentile(seg, 90))
    return out


def _agp_figure(glucose: np.ndarray,
                hours: np.ndarray) -> Optional[ReportFigure]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pct = _hourly_percentiles(glucose, hours, range(24))
    if len(pct) < 12:
        return None

    xs = sorted(pct.keys())
    p10 = [pct[x][0] for x in xs]
    p25 = [pct[x][1] for x in xs]
    p50 = [pct[x][2] for x in xs]
    p75 = [pct[x][3] for x in xs]
    p90 = [pct[x][4] for x in xs]

    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.axhspan(_TARGET_LO, _TARGET_HI, color=_C_TARGET, alpha=0.10)
    ax.axhline(_TARGET_LO, color="#9aa5b1", lw=0.8, ls="--")
    ax.axhline(_TARGET_HI, color="#9aa5b1", lw=0.8, ls="--")
    ax.fill_between(xs, p10, p90, color=_C_BAND, alpha=0.45,
                    label="10–90%")
    ax.fill_between(xs, p25, p75, color=_C_BRAND, alpha=0.35,
                    label="25–75% (IQR)")
    ax.plot(xs, p50, color=_C_INK, lw=2.0, label="Median")

    ax.set_xlim(0, 23)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xlabel("Hour of day", fontsize=9, color="#52606d")
    ax.set_ylabel("Glucose (mg/dL)", fontsize=9, color="#52606d")
    ax.set_ylim(40, max(300, max(p90) + 10))
    ax.grid(True, color=_C_GRID, lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors="#52606d", labelsize=8)
    ax.legend(fontsize=7.5, loc="upper right", frameon=False, ncol=3)
    fig.tight_layout()

    return ReportFigure(
        section="overview",
        title="Ambulatory glucose profile (AGP)",
        caption=("Median glucose by time of day with interquartile (25–75%) "
                 "and 10–90% bands. The green zone is the 70–180 mg/dL "
                 "target; a flat median inside it is the goal."),
        filename="fig_agp.png",
        png_base64=_fig_to_b64(fig),
        alt="Ambulatory glucose profile percentile bands by hour of day.")


def _overnight_figure(glucose: np.ndarray,
                      hours: np.ndarray) -> Optional[ReportFigure]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pct = _hourly_percentiles(glucose, hours, range(0, 7))
    if len(pct) < 4:
        return None

    xs = sorted(pct.keys())
    p25 = [pct[x][1] for x in xs]
    p50 = [pct[x][2] for x in xs]
    p75 = [pct[x][3] for x in xs]

    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    ax.axhspan(_TARGET_LO, _TARGET_HI, color=_C_TARGET, alpha=0.10)
    ax.axhline(_TARGET_LO, color="#9aa5b1", lw=0.8, ls="--")
    ax.axhline(_TARGET_HI, color="#9aa5b1", lw=0.8, ls="--")
    ax.fill_between(xs, p25, p75, color=_C_BRAND, alpha=0.35,
                    label="25–75% (IQR)")
    ax.plot(xs, p50, color=_C_INK, lw=2.0, marker="o", markersize=4,
            label="Median")

    # Slope annotation: overnight drift informs basal adequacy.
    if len(xs) >= 2:
        slope = float(np.polyfit(xs, p50, 1)[0])  # mg/dL per hour
        ax.text(0.02, 0.95,
                f"Overnight drift: {slope:+.1f} mg/dL/h",
                transform=ax.transAxes, fontsize=8.5, va="top",
                color="#52606d")

    ax.set_xlim(0, 6)
    ax.set_xticks(range(0, 7))
    ax.set_xlabel("Hour of day (overnight)", fontsize=9, color="#52606d")
    ax.set_ylabel("Glucose (mg/dL)", fontsize=9, color="#52606d")
    ax.grid(True, color=_C_GRID, lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors="#52606d", labelsize=8)
    ax.legend(fontsize=7.5, loc="upper right", frameon=False, ncol=2)
    fig.tight_layout()

    return ReportFigure(
        section="basal",
        title="Overnight glucose profile (00:00–06:00)",
        caption=("Median overnight glucose with IQR. A rising trend suggests "
                 "basal is too low; a falling trend suggests it is too high. "
                 "Used to contextualize the basal recommendation."),
        filename="fig_overnight.png",
        png_base64=_fig_to_b64(fig),
        alt="Overnight median glucose by hour with interquartile band.")


def build_clinical_figures(
    glucose: np.ndarray,
    hours: Optional[np.ndarray] = None,
) -> List[ReportFigure]:
    """Build decision-relevant figures from a patient's glucose data.

    Args:
        glucose: (N,) glucose values in mg/dL (NaNs allowed).
        hours: (N,) fractional hour-of-day aligned to ``glucose``. When
            omitted, only the time-in-range distribution is produced
            (AGP and overnight figures require hour-of-day).

    Returns:
        List of ReportFigure (possibly empty). Generation never raises on
        sparse/degenerate data; it simply omits figures it cannot build.
    """
    figures: List[ReportFigure] = []
    try:
        import matplotlib  # noqa: F401
    except Exception:
        return figures

    builders = [lambda: _tir_distribution_figure(glucose)]
    if hours is not None:
        builders.append(lambda: _agp_figure(glucose, hours))
        builders.append(lambda: _overnight_figure(glucose, hours))

    for build in builders:
        try:
            fig = build()
        except Exception:
            fig = None
        if fig is not None:
            figures.append(fig)

    return figures
