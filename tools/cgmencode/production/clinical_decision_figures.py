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
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

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


@dataclass
class DomainContext:
    """Recommendation context used to annotate per-domain figures.

    Lets a figure show not just the existing data but the recommended
    target/direction so readers see *why* a change is (or isn't) proposed.
    """
    domain: str                       # 'basal' | 'isf' | 'cr'
    current: Optional[float] = None
    theoretical: Optional[float] = None
    direction: Optional[str] = None   # 'increase' | 'decrease' | None
    target: Optional[float] = None     # practical target if available


def figure_from_file(path: str, section: str, title: str, caption: str,
                     alt: str = "") -> Optional[ReportFigure]:
    """Wrap an already-rendered PNG file as a ReportFigure.

    Lets the decision report reuse the analyzer's existing domain plots
    (e.g. ISF reconciliation, scheduled-vs-actual basal) instead of
    duplicating that analysis. Returns None if the file is missing.
    """
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
    except OSError:
        return None
    return ReportFigure(
        section=section, title=title, caption=caption,
        filename=os.path.basename(path), png_base64=b64,
        rel_path=None, alt=alt or title)


def demand_isf_figure(
    profile_isf: Optional[float],
    demand_isf: Optional[float],
    apparent_isf: Optional[float] = None,
    ci_low: Optional[float] = None,
    ci_high: Optional[float] = None,
    n_corrections: int = 0,
    confidence_label: str = "low",
    direction: Optional[str] = None,
) -> Optional[ReportFigure]:
    """Visualize the three ISF values that drive the ISF decision.

    Profile vs apparent/correction (AID-inflated) vs demand-phase (the
    validated 0-2h target, with its confidence interval). Makes the common
    confusion legible: the high apparent value is not the target; the
    demand-phase value is. Reproducible from ``result.dual_phase_isf``.
    """
    if not profile_isf or not demand_isf:
        return None
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels, values, colors = [], [], []
    labels.append("Profile\n(programmed)")
    values.append(float(profile_isf))
    colors.append("#94a3b8")
    if apparent_isf is not None:
        labels.append("Apparent\n(AID-inflated)")
        values.append(float(apparent_isf))
        colors.append("#cbd5e1")
    labels.append("Demand-phase\n(validated target)")
    values.append(float(demand_isf))
    colors.append(_C_TARGET)

    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ypos = list(range(len(labels)))
    ax.barh(ypos, values, color=colors, edgecolor="white", height=0.6)
    for y, v in zip(ypos, values):
        ax.text(v + 1, y, f"{v:g}", va="center", fontsize=9,
                fontweight="bold", color="#334155")

    # CI whisker on the demand-phase bar.
    if ci_low is not None and ci_high is not None:
        dy = ypos[-1]
        ax.plot([ci_low, ci_high], [dy, dy], color="#14505a", lw=2)
        for b in (ci_low, ci_high):
            ax.plot([b, b], [dy - 0.12, dy + 0.12], color="#14505a", lw=2)

    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("ISF (mg/dL per Unit)", fontsize=9, color="#52606d")
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors="#52606d", labelsize=8)
    ax.set_xlim(0, max(values + [ci_high or 0]) * 1.18)

    dir_txt = ""
    if direction in ("increase", "decrease"):
        dir_txt = (f"  Recommended direction: {direction} ISF toward the "
                   f"demand-phase target.")
    ax.set_title(
        f"ISF decomposition — profile {profile_isf:g}, demand "
        f"{demand_isf:g} (N={n_corrections}, {confidence_label} confidence)",
        fontsize=10, color="#14505a")
    fig.tight_layout()

    return ReportFigure(
        section="isf",
        title="Demand-phase ISF decomposition",
        caption=(
            "Profile ISF vs the apparent/correction ISF (amplified by AID "
            "compensation) vs the demand-phase ISF — the validated 0–2h "
            "insulin effect (EXP-2651) and the true target, shown with its "
            "95% confidence interval. The apparent value is not the target; "
            "the recommendation tracks the demand-phase value, bounded by a "
            "safety margin (EXP-2738)." + dir_txt),
        filename="fig_demand_isf.png",
        png_base64=_fig_to_b64(fig),
        alt="Bar chart of profile, apparent, and demand-phase ISF with CI.")


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


def _cr_excursion_figure(
    glucose: np.ndarray,
    bolus: np.ndarray,
    carbs: np.ndarray,
    ctx: Optional[DomainContext] = None,
) -> Optional[ReportFigure]:
    """Mean post-meal glucose excursion aligned at meal time.

    Shows how glucose behaves after carb-counted, bolused meals — the
    existing data behind a carb-ratio decision — and annotates the
    recommended CR direction/target so the reason for change is visible.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    g = np.asarray(glucose, dtype=float)
    b = np.asarray(bolus, dtype=float)
    c = np.asarray(carbs, dtype=float)
    n = g.size
    pre, post = 6, 48  # 30 min before, 4 h after (5-min grid)

    traces = []
    for i in range(pre, n - post):
        if not (c[i] >= 20.0):
            continue
        # Require a bolus near the meal and no large extra carbs after.
        if np.nansum(b[max(0, i - 2):i + 3]) < 0.3:
            continue
        if np.nansum(c[i + 1:i + post]) > 10.0:
            continue
        seg = g[i - pre:i + post]
        if np.isfinite(seg).sum() < (pre + post) * 0.6:
            continue
        base = np.nanmedian(g[i - pre:i + 1])
        if not np.isfinite(base):
            continue
        traces.append(seg - base)  # excursion relative to pre-meal baseline

    if len(traces) < 5:
        return None

    arr = np.vstack(traces)
    x = (np.arange(-pre, post)) * 5.0 / 60.0  # hours relative to meal
    med = np.nanmedian(arr, axis=0)
    q25 = np.nanpercentile(arr, 25, axis=0)
    q75 = np.nanpercentile(arr, 75, axis=0)
    peak = float(np.nanmax(med))
    peak_t = float(x[int(np.nanargmax(med))])
    ret_4h = float(med[-1])

    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.axhline(0, color="#9aa5b1", lw=0.8, ls="--")
    ax.fill_between(x, q25, q75, color=_C_BRAND, alpha=0.30,
                    label="25–75% (IQR)")
    ax.plot(x, med, color=_C_INK, lw=2.0, label="Median excursion")
    ax.scatter([peak_t], [peak], color=_C_HIGH, zorder=5, s=30)
    ax.annotate(f"peak +{peak:.0f} mg/dL\n@ {peak_t*60:.0f} min",
                xy=(peak_t, peak), xytext=(peak_t + 0.4, peak),
                fontsize=8, color="#52606d", va="center")

    ax.set_xlim(-0.5, 4)
    ax.set_xlabel("Hours from meal", fontsize=9, color="#52606d")
    ax.set_ylabel("Glucose rise vs pre-meal (mg/dL)", fontsize=9,
                  color="#52606d")
    ax.grid(True, color=_C_GRID, lw=0.6)
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(colors="#52606d", labelsize=8)
    ax.legend(fontsize=7.5, loc="upper right", frameon=False, ncol=2)
    fig.tight_layout()

    n_meals = len(traces)
    direction_note = ""
    if ctx is not None and ctx.direction in ("increase", "decrease") \
            and ctx.current is not None and ctx.theoretical is not None:
        direction_note = (
            f" Recommendation: {ctx.direction} carb ratio "
            f"{ctx.current:g}→{ctx.theoretical:g} g/U to "
            + ("tighten meal coverage and lower these peaks."
               if ctx.direction == "decrease"
               else "relax coverage and reduce post-meal lows."))
    else:
        direction_note = (
            " Carb ratio held this cycle; this profile is the baseline "
            "to compare against at the next review.")

    return ReportFigure(
        section="cr",
        title="Post-meal glucose excursion",
        caption=(f"Median glucose rise after {n_meals} carb-counted, bolused "
                 f"meals (peak +{peak:.0f} mg/dL at {peak_t*60:.0f} min; "
                 f"{ret_4h:+.0f} mg/dL vs baseline at 4 h)."
                 + direction_note),
        filename="fig_cr_excursion.png",
        png_base64=_fig_to_b64(fig),
        alt="Mean post-meal glucose excursion curve with interquartile band.")


def build_clinical_figures(
    glucose: np.ndarray,
    hours: Optional[np.ndarray] = None,
    bolus: Optional[np.ndarray] = None,
    carbs: Optional[np.ndarray] = None,
    domains: Optional[Dict[str, DomainContext]] = None,
) -> List[ReportFigure]:
    """Build decision-relevant figures from a patient's data.

    Args:
        glucose: (N,) glucose values in mg/dL (NaNs allowed).
        hours: (N,) fractional hour-of-day aligned to ``glucose``. When
            omitted, only the time-in-range distribution is produced
            (AGP and overnight figures require hour-of-day).
        bolus: (N,) optional bolus units, for the CR excursion figure.
        carbs: (N,) optional carb grams, for the CR excursion figure.
        domains: optional per-domain context (current/theoretical/
            direction) used to annotate the reason for change.

    Returns:
        List of ReportFigure (possibly empty). Generation never raises on
        sparse/degenerate data; it simply omits figures it cannot build.
    """
    figures: List[ReportFigure] = []
    try:
        import matplotlib  # noqa: F401
    except Exception:
        return figures

    domains = domains or {}
    builders = [lambda: _tir_distribution_figure(glucose)]
    if hours is not None:
        builders.append(lambda: _agp_figure(glucose, hours))
        builders.append(lambda: _overnight_figure(glucose, hours))
    if bolus is not None and carbs is not None:
        builders.append(
            lambda: _cr_excursion_figure(
                glucose, bolus, carbs, domains.get("cr")))

    for build in builders:
        try:
            fig = build()
        except Exception:
            fig = None
        if fig is not None:
            figures.append(fig)

    return figures
