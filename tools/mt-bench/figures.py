#!/usr/bin/env python3
"""Figures for docs/60-research/tenancy/multitenancy-k-and-residency-2026-09-14.md.

All values come from tools/mt-bench/results/*.json (see the report for method).
Palette: dataviz reference categorical slots 1-4, light mode, validated
(worst adjacent CVD dE 9.1, normal-vision 22.9). Slots 3 and 4 fall below 3:1
contrast on the surface, so every segment carries a visible direct label or an
outside label - the relief rule.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch
import numpy as np

SURFACE   = "#fcfcfb"
INK       = "#0b0b0b"
INK_2     = "#52514e"
INK_MUTE  = "#86857f"
GRID      = "#e6e5e1"
S = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # validated slots 1-4

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "text.color": INK,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2,
    "xtick.color": INK_2, "ytick.color": INK_2,
    "svg.fonttype": "path",   # self-contained: no font dependency on the viewer
})


def rounded_right(ax, x, y, w, h, r, color, rounded):
    """Bar segment: square at the baseline, 4px-equivalent rounded data-end."""
    r = min(r, w, h / 2) if rounded else 0
    if r <= 0:
        verts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
        codes = [Path.MOVETO] + [Path.LINETO] * 3 + [Path.CLOSEPOLY]
    else:
        verts = [(x, y), (x + w - r, y), (x + w, y), (x + w, y + r),
                 (x + w, y + h - r), (x + w, y + h), (x + w - r, y + h),
                 (x, y + h), (x, y)]
        codes = [Path.MOVETO, Path.LINETO, Path.CURVE3, Path.CURVE3,
                 Path.LINETO, Path.CURVE3, Path.CURVE3, Path.LINETO, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), facecolor=color, edgecolor="none", zorder=3))


# ---------------------------------------------------------------- figure 1
# One load cycle, 600-treatment tenant. Stage means from cycle-fix.js --stages
# plus the plugin tier from plugin-cycle.js.
STAGES = ["processDurations", "calcDelta treatments", "rest of the data path", "plugin tier"]
ROWS = [
    ("current code",      [5.856, 3.077, 0.023 + 0.048 + 0.188, 0.666]),
    ("both quadratics fixed", [0.104, 1.381, 0.015 + 0.030 + 0.163, 0.666]),
]

fig, (ax1, ax2) = plt.subplots(
    1, 2, figsize=(11.2, 3.5), gridspec_kw={"width_ratios": [1.28, 1]})

GAP = 0.035   # surface gap between stacked segments, in data units
BH = 0.34
for i, (label, vals) in enumerate(ROWS):
    y = len(ROWS) - 1 - i
    x = 0.0
    for j, v in enumerate(vals):
        w = max(v - GAP, 0.001)
        rounded_right(ax1, x, y - BH / 2, w, BH, 0.085, S[j], rounded=(j == len(vals) - 1))
        if w > 0.85:      # only label where the text comfortably fits inside
            ax1.text(x + w / 2, y, f"{v:.2f}", ha="center", va="center",
                     fontsize=8.5, color=SURFACE, fontweight="bold", zorder=4)
        x += v
    ax1.text(x + 0.16, y, f"{sum(vals):.2f} ms", ha="left", va="center",
             fontsize=9.5, color=INK, fontweight="bold", zorder=4)

ax1.set_yticks([1, 0]); ax1.set_yticklabels([ROWS[0][0], ROWS[1][0]], fontsize=9.5, color=INK)
ax1.set_xlim(0, 11.6); ax1.set_ylim(-0.62, 1.62)
ax1.set_xlabel("event-loop milliseconds per load cycle", color=INK_2)
ax1.xaxis.grid(True, color=GRID, lw=0.8, zorder=0); ax1.set_axisbelow(True)
ax1.yaxis.grid(False)
for s in ("top", "right", "left"): ax1.spines[s].set_visible(False)
ax1.spines["bottom"].set_color(GRID)
ax1.set_title("One load cycle, 600-treatment tenant",
              fontsize=10.5, color=INK, fontweight="bold", loc="left", pad=10)
handles = [plt.Line2D([], [], marker="s", ls="", markersize=8, color=S[j]) for j in range(4)]
ax1.legend(handles, STAGES, loc="upper center", bbox_to_anchor=(0.5, -0.25),
           ncol=4, frameon=False, fontsize=8.5, handletextpad=0.4, columnspacing=1.4,
           labelcolor=INK_2)

# ---------------------------------------------------------------- figure 1b
# Scaling: the same two arms across treatment volume (p50, cycle-fix.js).
TREAT = [300, 600, 1200, 2400]
CUR   = [2.734, 9.541, 31.934, 121.178]
FIX   = [1.033, 1.523, 2.518, 4.477]

ax2.plot(TREAT, CUR, lw=2, color=S[1], marker="o", markersize=8,
         markeredgecolor=SURFACE, markeredgewidth=2, solid_joinstyle="round", zorder=3)
ax2.plot(TREAT, FIX, lw=2, color=S[0], marker="o", markersize=8,
         markeredgecolor=SURFACE, markeredgewidth=2, solid_joinstyle="round", zorder=3)
ax2.set_yscale("log"); ax2.set_xscale("log")
ax2.set_xticks(TREAT); ax2.set_xticklabels([str(t) for t in TREAT])
ax2.set_yticks([1, 10, 100]); ax2.set_yticklabels(["1 ms", "10 ms", "100 ms"])
ax2.minorticks_off()
ax2.set_xlabel("treatments in the retention window", color=INK_2)
ax2.grid(True, color=GRID, lw=0.8, zorder=0); ax2.set_axisbelow(True)
for s in ("top", "right", "left"): ax2.spines[s].set_visible(False)
ax2.spines["bottom"].set_color(GRID)
ax2.set_title("…and how each scales", fontsize=10.5, color=INK,
              fontweight="bold", loc="left", pad=10)
ax2.text(TREAT[-1] * 0.94, CUR[-1] * 1.22, "current  121 ms", ha="right", va="bottom",
         fontsize=9, color=INK, fontweight="bold")
ax2.text(TREAT[-1] * 0.94, FIX[-1] * 0.78, "fixed  4.5 ms", ha="right", va="top",
         fontsize=9, color=INK, fontweight="bold")
ax2.text(TREAT[0] * 1.03, 200, "60 h of temp basals at a\n5-minute cadence ≈ 720",
         ha="left", va="top", fontsize=8, color=INK_MUTE, style="italic")
ax2.set_ylim(0.55, 260)

fig.tight_layout(rect=[0, 0.06, 1, 1])
fig.savefig("docs/visualizations/mt-load-cycle-composition.svg", format="svg",
            bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------- figure 2
# K per component, tenants per process. See report §6 for each derivation.
COMPONENTS = [
    ("APP shard\ncurrent code",        147,   "event-loop CPU\n10.2 ms/cycle", S[1]),
    ("APP shard\nquadratics fixed",    685,   "event-loop CPU\n2.2 ms/cycle",  S[0]),
    ("VCPOOL\nmachinery limit",        9700,  "actor memory\n422 KB/account",  S[2]),
    ("REALTIME\nfan-out",              27500, "emit cost + sockets\n55 µs/tenant", S[3]),
]

fig2, ax = plt.subplots(figsize=(9.6, 3.9))
ys = np.arange(len(COMPONENTS))[::-1]
for (name, k, binds, color), y in zip(COMPONENTS, ys):
    ax.barh(y, k, height=0.42, color=color, zorder=3)
    ax.text(k * 1.14, y + 0.10, f"{k:,}", ha="left", va="center",
            fontsize=10.5, color=INK, fontweight="bold")
    ax.text(k * 1.14, y - 0.17, binds.replace("\n", " · "), ha="left", va="center",
            fontsize=8, color=INK_MUTE)

ax.set_yticks(ys)
ax.set_yticklabels([c[0] for c in COMPONENTS], fontsize=9.5, color=INK)
ax.set_xscale("log"); ax.set_xlim(60, 400000)
ax.set_xticks([100, 1000, 10000, 100000])
ax.set_xticklabels(["100", "1,000", "10,000", "100,000"])
ax.minorticks_off()
ax.set_xlabel("tenants one process can hold  (30 % event-loop utilisation target)", color=INK_2)
ax.xaxis.grid(True, color=GRID, lw=0.8, zorder=0); ax.set_axisbelow(True)
ax.yaxis.grid(False)
for s in ("top", "right", "left"): ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(GRID)
ax.set_title("K is not one number — and the components differ by two orders of magnitude",
             fontsize=11, color=INK, fontweight="bold", loc="left", pad=12)
ax.set_ylim(-0.55, len(COMPONENTS) - 0.4)

fig2.tight_layout(rect=[0, 0.13, 1, 1])
fig2.text(0.012, 0.055,
          "Split components where K differs by an order of magnitude. The vendor pool's real limit is a "
          "vendor rate limit, not the\n9,700 machinery bound shown — it is the one number here that cannot "
          "be measured without vendor credentials.",
          ha="left", va="top", fontsize=8, color=INK_MUTE, style="italic")
fig2.savefig("docs/visualizations/mt-k-by-component.svg", format="svg", bbox_inches="tight")
plt.close(fig2)
print("wrote docs/visualizations/mt-load-cycle-composition.svg")
print("wrote docs/visualizations/mt-k-by-component.svg")
