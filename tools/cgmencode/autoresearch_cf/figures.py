"""Shared figure helpers for autoresearch_cf experiments."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats


def figure_three_panel(per_patient: pd.DataFrame, title: str,
                       out_path: Path) -> None:
    """3-panel summary: leverage scatter, per-patient bars, lineage box.

    Mirrors EXP-2889's figure layout so iterations are visually comparable.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    # Panel 1: braking_ratio vs cf_severe (the EXP-2889 winning correlation)
    ax = axes[0]
    valid = per_patient.dropna(subset=['braking_ratio', 'cf_severe'])
    if not valid.empty:
        if 'archetype' in valid.columns:
            for arch, g in valid.groupby('archetype'):
                ax.scatter(g['braking_ratio'], g['cf_severe'] * 100,
                           label=str(arch), s=60, alpha=0.8)
            ax.legend(fontsize=7, loc='best')
        else:
            ax.scatter(valid['braking_ratio'], valid['cf_severe'] * 100, s=60)
        rho, p = stats.spearmanr(valid['braking_ratio'], valid['cf_severe'])
        ax.set_title(f'braking_ratio vs cf_severe\n'
                     f'rho={rho:+.3f} p={p:.3f} n={len(valid)}')
    ax.set_xlabel('braking_ratio')
    ax.set_ylabel('counterfactual severe-hypo % (AID-off)')
    ax.grid(alpha=0.3)

    # Panel 2: observed vs counterfactual per-patient bars
    ax = axes[1]
    sorted_pp = per_patient.sort_values('cf_severe', ascending=False)
    xs = np.arange(len(sorted_pp))
    ax.bar(xs - 0.2, sorted_pp['obs_severe'] * 100, width=0.4,
           label='observed', color='steelblue')
    ax.bar(xs + 0.2, sorted_pp['cf_severe'] * 100, width=0.4,
           label='counterfactual (AID-off)', color='firebrick')
    ax.set_xticks(xs)
    ax.set_xticklabels(sorted_pp['patient_id'].astype(str),
                       rotation=90, fontsize=6)
    ax.set_ylabel('severe-hypo fraction of descents (%)')
    ax.set_title('Per-patient AID protection')
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis='y')

    # Panel 3: protection by lineage
    ax = axes[2]
    if 'lineage' in per_patient.columns:
        order = (per_patient.groupby('lineage')['aid_protection_severe']
                            .median().sort_values().index.tolist())
        data = [per_patient[per_patient['lineage'] == ln][
            'aid_protection_severe'].values * 100 for ln in order]
        if any(len(d) > 0 for d in data):
            ax.boxplot(data, tick_labels=order, showmeans=True)
        ax.set_title('Protection by lineage')
    ax.set_ylabel('AID protection (cf − obs) (%)')
    ax.grid(alpha=0.3, axis='y')

    fig.suptitle(title, y=1.02, fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches='tight')
    plt.close(fig)


def figure_iteration_compare(rows: pd.DataFrame, out_path: Path) -> None:
    """Side-by-side comparison of iterations from the ledger.

    Expects rows from ``autoresearch_cf_results.tsv`` (committed).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    labels = rows['config_name'].astype(str).tolist()
    xs = np.arange(len(rows))

    ax = axes[0]
    ax.bar(xs - 0.2, rows['pop_obs_severe'] * 100, width=0.4,
           label='observed', color='steelblue')
    ax.bar(xs + 0.2, rows['pop_cf_severe'] * 100, width=0.4,
           label='counterfactual', color='firebrick')
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=8)
    ax.set_ylabel('population severe %')
    ax.set_title('Population observed vs counterfactual')
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis='y')

    ax = axes[1]
    ax.bar(xs, rows['aid_protection_severe'] * 100, color='darkgreen')
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=8)
    ax.set_ylabel('AID protection (pp)')
    ax.set_title('Population AID protection magnitude')
    ax.grid(alpha=0.3, axis='y')

    ax = axes[2]
    ax.bar(xs, rows['mean_extra_drop_mgdl'], color='slateblue')
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=8)
    ax.set_ylabel('mean extra drop (mg/dL)')
    ax.set_title('Modelled cf insulin effect')
    ax.grid(alpha=0.3, axis='y')

    fig.tight_layout()
    fig.savefig(out_path, dpi=130, bbox_inches='tight')
    plt.close(fig)
