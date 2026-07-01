"""action_label_benchmark_figures.py — shared visualization for the basal/
ISF/CR action-label benchmarks (`basal_action_label_benchmark.py`,
`isf_action_label_benchmark.py`, `cr_action_label_benchmark.py`; see
docs/60-research/state-aware-harness-parallels-2026-07-01.md §7).

Each benchmark's ``summarize_*_label_benchmark()`` returns the same
shape (coverage, persistence, and -- for basal/ISF, which have two
independent label sources -- agreement). This module renders one
consistent 3-panel comparison chart from that summary so every domain
gets the same visual treatment rather than one-off plotting code per
domain (basal's first figure was generated ad hoc; this replaces that
with a reusable, tested function).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

_C_A = "#1f6f78"
_C_B = "#c0392b"
_C_INK = "#14505a"


def _style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_action_label_benchmark(
    summary: dict,
    domain_title: str,
    method_a_label: str,
    method_b_label: str,
    output_path: Path | str,
    single_method: bool = False,
) -> Optional[Path]:
    """Render and save the coverage/persistence/agreement comparison chart.

    ``single_method=True`` (CR's case) skips the agreement panel and the
    second method's bars, since only one label source exists for that
    domain (see ``cr_action_label_benchmark`` module docstring).

    Returns the saved path, or ``None`` if ``summary`` has no windows.
    """
    if summary.get("n_windows", 0) == 0:
        return None
    import matplotlib.pyplot as plt

    n_panels = 2 if single_method else 3
    fig, axes = plt.subplots(1, n_panels, figsize=(4.5 * n_panels, 4))
    if n_panels == 1:
        axes = [axes]

    labels = [method_a_label] if single_method else [method_a_label, method_b_label]

    # ── Coverage ───────────────────────────────────────────────────
    ax = axes[0]
    if single_method:
        vals = [summary["coverage_direct_advisor"]]
        colors = [_C_A]
    else:
        vals = [summary["coverage_facts_loader"], summary["coverage_direct_advisor"]]
        colors = [_C_A, _C_B]
    bars = ax.bar(labels, vals, color=colors)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.0%}",
                ha="center", va="bottom", color=_C_INK)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Fraction of windows with a usable label")
    ax.set_title("Coverage", color=_C_INK, fontweight="bold")
    _style_axes(ax)

    # ── Persistence ────────────────────────────────────────────────
    ax = axes[1]
    if single_method:
        vals = [summary["persistence_direct_advisor"] or 0.0]
        colors = [_C_A]
    else:
        vals = [summary["persistence_facts_loader"] or 0.0,
                summary["persistence_direct_advisor"] or 0.0]
        colors = [_C_A, _C_B]
    bars = ax.bar(labels, vals, color=colors)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.0%}",
                ha="center", va="bottom", color=_C_INK)
    ax.axhline(0.5, linestyle=":", color=_C_INK, linewidth=1)
    ax.text(len(labels) - 0.6, 0.51, "chance (~50%)", fontsize=8, color=_C_INK, ha="right")
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("P(same direction on next window | non-none label)")
    ax.set_title("Persistence (temporal stability)", color=_C_INK, fontweight="bold")
    _style_axes(ax)

    # ── Agreement (basal/ISF only) ────────────────────────────────
    if not single_method:
        ax = axes[2]
        agreement = summary.get("agreement_where_both_covered")
        ax.bar(["Agreement\n(both covered)"], [agreement or 0.0], color=_C_A)
        if agreement is not None:
            ax.text(0, agreement, f"{agreement:.0%}", ha="center", va="bottom", color=_C_INK)
        ax.set_ylim(0, 1.0)
        ax.set_title(f"Agreement (n={summary.get('n_both_covered', 0)})",
                     color=_C_INK, fontweight="bold")
        _style_axes(ax)

    fig.suptitle(domain_title, color=_C_INK, fontweight="bold")
    fig.tight_layout()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return output_path
