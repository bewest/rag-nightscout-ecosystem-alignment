#!/usr/bin/env python3
"""
report_engine.py — Auto-report generation for OREF-INV-003 replication work.

Supports the autoresearch → autodraft → autoedit → autoreview → autocorrect
→ autopublish cycle. Each experiment produces:
  1. JSON results (externals/experiments/)
  2. Figures (tools/oref_inv_003_replication/figures/)
  3. Markdown report (tools/oref_inv_003_replication/reports/)
  4. Published report (docs/60-research/)

The comparison template structures every report around:
  - What the colleague found (their claim + their evidence)
  - What we found (our replication/contrast + our evidence)
  - Agreement/disagreement assessment
  - Combined strength of evidence
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

REPORTS_DIR = Path('tools/oref_inv_003_replication/reports')
FIGURES_DIR = Path('tools/oref_inv_003_replication/figures')
PUBLISH_DIR = Path('docs/60-research')
RESULTS_DIR = Path('externals/experiments')


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj) if np.isfinite(obj) else None
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class ComparisonReport:
    """Structured comparison report for replication/contrast/augmentation.

    Usage:
        report = ComparisonReport(
            exp_id='EXP-2401',
            title='Feature Importance Ranking Replication',
            phase='replication',
        )
        report.add_their_finding('F1', 'Target is strongest lever',
                                 evidence='SHAP 17% hypo, 15% hyper',
                                 source='OREF-INV-003 Findings Overview')
        report.add_our_finding('F1', 'Target confirmed as top lever',
                               evidence='SHAP 19% hypo in our data',
                               agreement='agrees')
        report.add_figure('fig01_shap_comparison.png', 'SHAP importance comparison')
        report.set_synthesis('Both analyses converge on target as...')
        report.save()
    """

    AGREEMENT_LEVELS = ['strongly_agrees', 'agrees', 'partially_agrees',
                        'inconclusive', 'partially_disagrees', 'disagrees',
                        'not_comparable']

    def __init__(self, exp_id: str, title: str, phase: str,
                 script: Optional[str] = None):
        self.exp_id = exp_id
        self.title = title
        self.phase = phase  # replication, contrast, augmentation, synthesis
        self.script = script
        self.date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        self.their_findings: list[dict] = []
        self.our_findings: list[dict] = []
        self.figures: list[dict] = []
        self.synthesis = ''
        self.methodology_notes = ''
        self.limitations = ''
        self.raw_results: dict = {}

    def add_their_finding(self, finding_id: str, claim: str,
                          evidence: str, source: str = 'OREF-INV-003'):
        """Record one of the colleague's findings for comparison."""
        self.their_findings.append({
            'id': finding_id, 'claim': claim,
            'evidence': evidence, 'source': source,
        })

    def add_our_finding(self, finding_id: str, claim: str,
                        evidence: str, agreement: str = 'inconclusive',
                        our_source: str = ''):
        """Record our corresponding finding and agreement assessment."""
        if agreement not in self.AGREEMENT_LEVELS:
            raise ValueError(f"agreement must be one of {self.AGREEMENT_LEVELS}")
        self.our_findings.append({
            'id': finding_id, 'claim': claim,
            'evidence': evidence, 'agreement': agreement,
            'our_source': our_source,
        })

    def add_figure(self, filename: str, caption: str):
        """Register a figure for the report."""
        self.figures.append({'filename': filename, 'caption': caption})

    def set_synthesis(self, text: str):
        """Set the overall synthesis narrative."""
        self.synthesis = text

    def set_methodology(self, text: str):
        """Set methodology notes."""
        self.methodology_notes = text

    def set_limitations(self, text: str):
        """Set limitations section."""
        self.limitations = text

    def set_raw_results(self, results: dict):
        """Attach raw experiment results for JSON export."""
        self.raw_results = results

    def _agreement_emoji(self, level: str) -> str:
        return {
            'strongly_agrees': '✅✅',
            'agrees': '✅',
            'partially_agrees': '🟡',
            'inconclusive': '❓',
            'partially_disagrees': '🟠',
            'disagrees': '❌',
            'not_comparable': '↔️',
        }.get(level, '❓')

    def render_markdown(self) -> str:
        """Render the report as Markdown."""
        lines = []
        phase_label = self.phase.title()

        lines.append(f'# {self.title}')
        lines.append(f'')
        lines.append(f'**Experiment**: {self.exp_id}  ')
        lines.append(f'**Phase**: {phase_label} (OREF-INV-003 cross-analysis)  ')
        lines.append(f'**Date**: {self.date}  ')
        if self.script:
            lines.append(f'**Script**: `{self.script}`  ')
        lines.append('')

        # Comparison table
        if self.their_findings and self.our_findings:
            lines.append('## Comparison Summary')
            lines.append('')
            lines.append('| Finding | Their Claim | Our Result | Agreement |')
            lines.append('|---------|------------|------------|-----------|')
            their_by_id = {f['id']: f for f in self.their_findings}
            for ours in self.our_findings:
                theirs = their_by_id.get(ours['id'], {})
                emoji = self._agreement_emoji(ours['agreement'])
                their_claim = theirs.get('claim', '—')
                lines.append(f"| {ours['id']} | {their_claim} | {ours['claim']} | {emoji} {ours['agreement']} |")
            lines.append('')

        # Their findings detail
        if self.their_findings:
            lines.append('## Colleague\'s Findings (OREF-INV-003)')
            lines.append('')
            for f in self.their_findings:
                lines.append(f"### {f['id']}: {f['claim']}")
                lines.append(f"")
                lines.append(f"**Evidence**: {f['evidence']}")
                lines.append(f"**Source**: {f['source']}")
                lines.append('')

        # Our findings detail
        if self.our_findings:
            lines.append('## Our Findings')
            lines.append('')
            for f in self.our_findings:
                emoji = self._agreement_emoji(f['agreement'])
                lines.append(f"### {f['id']}: {f['claim']} {emoji}")
                lines.append(f"")
                lines.append(f"**Evidence**: {f['evidence']}")
                lines.append(f"**Agreement**: {f['agreement']}")
                if f.get('our_source'):
                    lines.append(f"**Prior work**: {f['our_source']}")
                lines.append('')

        # Figures
        if self.figures:
            lines.append('## Figures')
            lines.append('')
            for fig in self.figures:
                lines.append(f"![{fig['caption']}](../figures/{fig['filename']})")
                lines.append(f"*{fig['caption']}*")
                lines.append('')

        # Methodology
        if self.methodology_notes:
            lines.append('## Methodology Notes')
            lines.append('')
            lines.append(self.methodology_notes)
            lines.append('')

        # Synthesis
        if self.synthesis:
            lines.append('## Synthesis')
            lines.append('')
            lines.append(self.synthesis)
            lines.append('')

        # Limitations
        if self.limitations:
            lines.append('## Limitations')
            lines.append('')
            lines.append(self.limitations)
            lines.append('')

        return '\n'.join(lines)

    def save(self, also_publish: bool = False):
        """Save report to reports/ dir and optionally publish to docs/60-research/."""
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        # Save markdown report
        slug = self.exp_id.lower().replace('-', '_')
        report_path = REPORTS_DIR / f'{slug}_report.md'
        report_path.write_text(self.render_markdown())
        print(f'  Report saved: {report_path}')

        # Save raw results as JSON
        if self.raw_results:
            results_path = RESULTS_DIR / f'{slug}_replication.json'
            with open(results_path, 'w') as f:
                json.dump(self.raw_results, f, indent=2, cls=NumpyEncoder)
            print(f'  Results saved: {results_path}')

        # Publish to docs/60-research/
        if also_publish:
            PUBLISH_DIR.mkdir(parents=True, exist_ok=True)
            pub_name = f"oref-inv-003-{self.phase}-{slug}-{self.date}.md"
            pub_path = PUBLISH_DIR / pub_name
            pub_path.write_text(self.render_markdown())
            print(f'  Published: {pub_path}')

        return report_path


def save_figure(fig, name, dpi: int = 150):
    """Save a matplotlib figure to the figures directory."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    p = Path(name)
    # If caller already provided a rooted path, use it directly
    if str(FIGURES_DIR) in str(p):
        path = p
    else:
        path = FIGURES_DIR / p.name
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, bbox_inches='tight', facecolor='white')
    print(f'  Figure saved: {path}')
    return path


# ── Shared visualization helpers ─────────────────────────────────────────

COLORS = {
    'theirs': '#e74c3c',
    'ours': '#2563eb',
    'agree': '#059669',
    'disagree': '#dc2626',
    'neutral': '#6b7280',
    'bg_light': '#f8fafc',
    'grid': '#e2e8f0',
}

PATIENT_COLORS = {
    'a': '#e11d48', 'b': '#be123c', 'c': '#f59e0b', 'd': '#059669',
    'e': '#0284c7', 'f': '#7c3aed', 'g': '#c026d3', 'h': '#dc2626',
    'i': '#0d9488', 'j': '#ea580c', 'k': '#4f46e5',
}


def plot_shap_comparison(their_shap: dict, our_shap: dict,
                         title: str = 'SHAP Feature Importance Comparison',
                         top_n: int = 15, output_path: Optional[str] = None):
    """Side-by-side bar chart comparing SHAP importance rankings.

    Parameters
    ----------
    their_shap : dict
        {feature_name: importance_value} from colleague's model
    our_shap : dict
        {feature_name: importance_value} from our replication
    title : str
        Plot title
    top_n : int
        Number of features to show
    output_path : str, optional
        If provided, save figure. Otherwise plt.show().
    """
    import matplotlib.pyplot as plt

    # Normalize to percentages
    their_total = sum(their_shap.values())
    our_total = sum(our_shap.values())
    their_pct = {k: v / their_total * 100 for k, v in their_shap.items()}
    our_pct = {k: v / our_total * 100 for k, v in our_shap.items()}

    # Union of top features from both
    all_features = set()
    for d in [their_pct, our_pct]:
        sorted_f = sorted(d.items(), key=lambda x: -x[1])[:top_n]
        all_features.update(f[0] for f in sorted_f)

    # Sort by average importance
    features = sorted(all_features,
                      key=lambda f: (their_pct.get(f, 0) + our_pct.get(f, 0)) / 2)

    fig, ax = plt.subplots(figsize=(12, max(6, len(features) * 0.4)))
    y = np.arange(len(features))
    height = 0.35

    their_vals = [their_pct.get(f, 0) for f in features]
    our_vals = [our_pct.get(f, 0) for f in features]

    ax.barh(y - height / 2, their_vals, height, label='OREF-INV-003 (28 oref users)',
            color=COLORS['theirs'], alpha=0.8)
    ax.barh(y + height / 2, our_vals, height, label='Our replication (11+ patients)',
            color=COLORS['ours'], alpha=0.8)

    ax.set_yticks(y)
    ax.set_yticklabels(features, fontsize=9)
    ax.set_xlabel('Importance (%)')
    ax.set_title(title, fontsize=13, fontweight='bold')
    ax.legend(loc='lower right')
    ax.grid(axis='x', alpha=0.3)
    ax.set_facecolor(COLORS['bg_light'])

    plt.tight_layout()
    if output_path:
        save_figure(fig, output_path)
    plt.close(fig)
    return fig


def plot_sweep_comparison(their_x, their_hypo, their_hyper,
                          our_x, our_hypo, our_hyper,
                          xlabel: str = 'Target (mg/dL)',
                          title: str = 'Parameter Sweep Comparison',
                          output_path: Optional[str] = None):
    """Compare parameter sweep curves (theirs vs ours).

    Plots hypo and hyper rates as functions of a swept parameter,
    with separate line styles for their data and ours.
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 6))

    # Their curves (dashed)
    ax.plot(their_x, their_hypo, '--', color='#e74c3c', linewidth=2,
            label='OREF-INV-003 hypo rate', marker='o', markersize=4)
    ax.plot(their_x, their_hyper, '--', color='#f39c12', linewidth=2,
            label='OREF-INV-003 hyper rate', marker='s', markersize=4)

    # Our curves (solid)
    ax.plot(our_x, our_hypo, '-', color='#e74c3c', linewidth=2.5,
            label='Our hypo rate', marker='o', markersize=5)
    ax.plot(our_x, our_hyper, '-', color='#f39c12', linewidth=2.5,
            label='Our hyper rate', marker='s', markersize=5)

    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel('4-hour event rate (%)', fontsize=11)
    ax.set_title(title, fontsize=13, fontweight='bold')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_facecolor(COLORS['bg_light'])

    plt.tight_layout()
    if output_path:
        save_figure(fig, output_path)
    plt.close(fig)
    return fig


if __name__ == '__main__':
    # Self-test: generate a sample comparison report
    report = ComparisonReport(
        exp_id='EXP-TEST',
        title='Report Engine Self-Test',
        phase='replication',
        script='report_engine.py',
    )
    report.add_their_finding('F1', 'Target is strongest lever',
                             evidence='SHAP 17% hypo importance',
                             source='OREF-INV-003 Findings Overview')
    report.add_our_finding('F1', 'Target confirmed as top lever',
                           evidence='SHAP 19% hypo in our data',
                           agreement='agrees',
                           our_source='EXP-2201 settings recalibration')
    report.set_synthesis('Both analyses converge on glucose target as the '
                         'single most impactful user-controlled setting.')
    report.set_limitations('Our data uses Loop (not oref); '
                           'feature alignment involves approximations.')
    path = report.save()
    print(f'\nSelf-test passed. Report at: {path}')
    print(report.render_markdown()[:500])
