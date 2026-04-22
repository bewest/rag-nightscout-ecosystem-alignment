"""
Metabolic System Visualization Toolkit

Generates per-patient diagnostic charts that make the diabetes/AID system
legible to patients and clinicians. Each chart pairs PHYSIOLOGY (what the
body is demanding) with CONTROLLER RESPONSE (what the AID is doing) at
appropriate timescales.

Charts produced (per patient):
1. WEEK ENVELOPE — 7-day strip showing state regime, BG, scheduled vs
   actual basal, daily TIR; highlights envelope demand vs profile
2. DAY DETAIL — 24h strip showing BG, IOB, COB, basal/bolus events,
   with state shading
3. MEAL EVENT — 6-hour window around a representative meal, showing
   carb absorption curve vs insulin delivery curve vs BG response
4. PROFILE AUDIT — state-conditional basal delivery histogram vs
   scheduled profile (shows where profile is materially wrong)
5. SITE-AGE TRAJECTORY — observed ISF as function of cannula age
   (when wear data available)
6. RECOVERY DIAGNOSTIC — for patients with S0->S1 transitions, shows
   recovery trajectory vs cohort baseline
"""
import json
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

OUT_VIZ = Path('docs/60-research/figures')
OUT_VIZ.mkdir(parents=True, exist_ok=True)
EXP_OUT = Path('externals/experiments')

# Color palette: physiology vs controller
COLOR_BG = '#444444'
COLOR_TARGET_BAND = '#9bc8e3'
COLOR_HIGH_BAND = '#fbb778'
COLOR_LOW_BAND = '#e07b91'
COLOR_BASAL_SCHEDULED = '#888888'
COLOR_BASAL_ACTUAL = '#1f77b4'
COLOR_BOLUS = '#d62728'
COLOR_SMB = '#ff7f0e'
COLOR_CARBS = '#2ca02c'
COLOR_STATE_S1 = '#fde2c8'
COLOR_STATE_S0 = '#e0f0e0'
COLOR_IOB = '#9467bd'
COLOR_COB = '#8c564b'

print("Loading data...")
g = pd.read_parquet('externals/ns-parquet/training/grid.parquet')
g['time'] = pd.to_datetime(g['time'], utc=True)
sa = pd.read_parquet(EXP_OUT / 'exp-2810_state_assignments.parquet')
sa['time'] = pd.to_datetime(sa['time'], utc=True)
print(f"Grid: {len(g):,} cells; states: {len(sa)} windows")


def shade_states(ax, state_windows, t_start, t_end):
    """Shade background by state windows."""
    for _, row in state_windows.iterrows():
        s = row['time']
        e = s + pd.Timedelta(hours=48)
        if e < t_start or s > t_end:
            continue
        s = max(s, t_start)
        e = min(e, t_end)
        color = COLOR_STATE_S1 if row['state'] == 1 else COLOR_STATE_S0
        ax.axvspan(s, e, color=color, alpha=0.5, zorder=0)


def chart_week_envelope(pid, days=7):
    """7-day envelope chart: state, BG, basal, demand-vs-profile."""
    pat = g[g['patient_id'] == pid].sort_values('time').reset_index(drop=True)
    if len(pat) == 0:
        return False
    sa_pat = sa[sa['patient_id'] == pid].sort_values('time').reset_index(drop=True)
    
    end = pat['time'].max()
    start = end - pd.Timedelta(days=days)
    pat = pat[(pat['time'] >= start) & (pat['time'] <= end)].copy()
    if len(pat) < 100:
        return False
    
    fig, axes = plt.subplots(3, 1, figsize=(13, 8), sharex=True,
                              gridspec_kw={'height_ratios': [3, 2, 1.5]})
    fig.suptitle(f'Patient {pid} — 7-Day Metabolic Envelope', fontsize=14,
                 fontweight='bold')
    
    # Panel 1: BG with state shading
    ax = axes[0]
    shade_states(ax, sa_pat, start, end)
    ax.axhspan(70, 180, color=COLOR_TARGET_BAND, alpha=0.25, label='Target 70-180')
    ax.axhspan(180, 250, color=COLOR_HIGH_BAND, alpha=0.15)
    ax.axhspan(0, 70, color=COLOR_LOW_BAND, alpha=0.2)
    ax.plot(pat['time'], pat['glucose'], color=COLOR_BG, lw=0.8)
    ax.set_ylabel('BG (mg/dL)')
    ax.set_ylim(40, 300)
    ax.set_title('Glucose with metabolic state regime '
                 '(orange = elevated S1, green = baseline S0)', fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)
    
    # Panel 2: Basal scheduled vs actual (the "envelope demand" reveal)
    ax = axes[1]
    shade_states(ax, sa_pat, start, end)
    ax.plot(pat['time'], pat['scheduled_basal_rate'], color=COLOR_BASAL_SCHEDULED,
            lw=1.2, alpha=0.7, label='Scheduled (profile)')
    ax.plot(pat['time'], pat['actual_basal_rate'], color=COLOR_BASAL_ACTUAL,
            lw=0.9, alpha=0.85, label='Actual (controller)')
    # Bolus markers
    bolus = pat[pat['bolus'].fillna(0) > 0.05]
    if len(bolus) > 0:
        ax.scatter(bolus['time'], bolus['actual_basal_rate'].fillna(0) + 0.1,
                   marker='v', color=COLOR_BOLUS, s=20, label='User bolus', zorder=5)
    ax.set_ylabel('Basal rate (U/hr)')
    ax.set_title('Profile (gray) vs Controller delivery (blue) — '
                 'gap = envelope demand the profile misses',
                 fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)
    
    # Panel 3: IOB / COB time series
    ax = axes[2]
    shade_states(ax, sa_pat, start, end)
    ax.plot(pat['time'], pat['iob'], color=COLOR_IOB, lw=0.8, label='IOB (U)')
    ax.plot(pat['time'], pat['cob'].fillna(0)/10, color=COLOR_COB, lw=0.8,
            label='COB÷10 (g)', alpha=0.8)
    ax.set_ylabel('IOB / COB÷10')
    ax.set_xlabel('Time')
    ax.grid(alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%a %m-%d'))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right')
    
    plt.tight_layout()
    out = OUT_VIZ / f'{pid}_week_envelope.png'
    plt.savefig(out, dpi=110, bbox_inches='tight')
    plt.close()
    print(f"  ✓ {out}")
    return True


def chart_meal_event(pid):
    """6-hour window around a representative meal event."""
    pat = g[g['patient_id'] == pid].sort_values('time').reset_index(drop=True)
    # Find a meal: a cell with carbs >= 30 with no carbs in prior 3h
    pat['carbs_filled'] = pat['carbs'].fillna(0)
    candidates = pat[pat['carbs_filled'] >= 30].copy()
    if len(candidates) == 0:
        candidates = pat[pat['carbs_filled'] >= 15].copy()
    if len(candidates) == 0:
        return False
    # Pick the median carb event
    meal_row = candidates.iloc[len(candidates) // 2]
    meal_t = meal_row['time']
    
    win = pat[(pat['time'] >= meal_t - pd.Timedelta(hours=1)) &
              (pat['time'] <= meal_t + pd.Timedelta(hours=5))].copy()
    if len(win) < 30:
        return False
    
    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True,
                              gridspec_kw={'height_ratios': [3, 2, 2]})
    fig.suptitle(f'Patient {pid} — Meal Event ({meal_row["carbs_filled"]:.0f}g carbs)',
                 fontsize=13, fontweight='bold')
    
    # Panel 1: BG response
    ax = axes[0]
    ax.axhspan(70, 180, color=COLOR_TARGET_BAND, alpha=0.25)
    ax.plot(win['time'], win['glucose'], color=COLOR_BG, lw=1.5)
    ax.axvline(meal_t, color=COLOR_CARBS, ls='--', lw=1.5, label=f"Meal at {meal_t.strftime('%H:%M')}")
    ax.set_ylabel('BG (mg/dL)')
    ax.set_title('BG trajectory through meal — physiology responds, '
                 'controller compensates', fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)
    
    # Panel 2: Insulin events (controller response)
    ax = axes[1]
    ax.plot(win['time'], win['actual_basal_rate'], color=COLOR_BASAL_ACTUAL,
            lw=1.2, label='Basal (U/hr)')
    ax.plot(win['time'], win['scheduled_basal_rate'], color=COLOR_BASAL_SCHEDULED,
            lw=1.0, ls='--', label='Scheduled', alpha=0.6)
    bolus = win[win['bolus'].fillna(0) > 0]
    smb = win[win['bolus_smb'].fillna(0) > 0]
    if len(bolus) > 0:
        ax.scatter(bolus['time'], bolus['bolus'] * 4, marker='v',
                   color=COLOR_BOLUS, s=80, label='Bolus (×4 U)', zorder=5)
    if len(smb) > 0:
        ax.scatter(smb['time'], smb['bolus_smb'] * 8, marker='v',
                   color=COLOR_SMB, s=40, label='SMB (×8 U)', zorder=5)
    ax.axvline(meal_t, color=COLOR_CARBS, ls='--', lw=1.5, alpha=0.5)
    ax.set_ylabel('Insulin (U/hr)')
    ax.set_title('Controller insulin response: basal modulation + boluses + SMBs',
                 fontsize=10)
    ax.grid(alpha=0.3)
    ax.legend(loc='upper right', fontsize=8)
    
    # Panel 3: COB / IOB envelope (the supply/demand balance)
    ax = axes[2]
    ax.fill_between(win['time'], 0, win['cob'].fillna(0), color=COLOR_COB, alpha=0.4,
                    label='COB (g)')
    ax2 = ax.twinx()
    ax2.fill_between(win['time'], 0, win['iob'].fillna(0), color=COLOR_IOB, alpha=0.4,
                     label='IOB (U)')
    ax.axvline(meal_t, color=COLOR_CARBS, ls='--', lw=1.5, alpha=0.5)
    ax.set_ylabel('COB (g)', color=COLOR_COB)
    ax2.set_ylabel('IOB (U)', color=COLOR_IOB)
    ax.set_title('Supply/Demand: carbs entering bloodstream vs insulin active',
                 fontsize=10)
    ax.set_xlabel('Time')
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    
    plt.tight_layout()
    out = OUT_VIZ / f'{pid}_meal_event.png'
    plt.savefig(out, dpi=110, bbox_inches='tight')
    plt.close()
    print(f"  ✓ {out}")
    return True


def chart_profile_audit(pid):
    """State-conditional actual basal vs scheduled profile."""
    pat = g[g['patient_id'] == pid].sort_values('time').reset_index(drop=True)
    sa_pat = sa[sa['patient_id'] == pid].sort_values('time').reset_index(drop=True)
    if len(sa_pat) < 4 or sa_pat['state'].nunique() < 2:
        return False
    merged = pd.merge_asof(
        pat[['time', 'actual_basal_rate', 'scheduled_basal_rate']],
        sa_pat[['time', 'state']],
        on='time', direction='backward', tolerance=pd.Timedelta('48h')
    ).dropna(subset=['state', 'actual_basal_rate'])
    
    # Hour-of-day profile audit
    merged['hour'] = merged['time'].dt.hour
    hour_state = merged.groupby(['hour', 'state']).agg(
        actual=('actual_basal_rate', 'mean'),
        scheduled=('scheduled_basal_rate', 'mean'),
    ).reset_index()
    
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle(f'Patient {pid} — Profile Audit (state-conditional)',
                 fontsize=13, fontweight='bold')
    
    # Left: hourly profile vs actual delivery, by state
    ax = axes[0]
    s0 = hour_state[hour_state['state'] == 0]
    s1 = hour_state[hour_state['state'] == 1]
    if len(s0) > 0:
        ax.plot(s0['hour'], s0['actual'], 'o-', color='#2ca02c',
                label='Actual delivery — S0 (baseline)', lw=2, ms=5)
    if len(s1) > 0:
        ax.plot(s1['hour'], s1['actual'], 'o-', color='#d62728',
                label='Actual delivery — S1 (elevated)', lw=2, ms=5)
    sched_avg = pat.groupby(pat['time'].dt.hour)['scheduled_basal_rate'].mean()
    ax.plot(sched_avg.index, sched_avg.values, 'k--', lw=1.5,
            label='Scheduled (profile)', alpha=0.7)
    ax.set_xlabel('Hour of day')
    ax.set_ylabel('Basal rate (U/hr)')
    ax.set_title('Hourly basal: profile vs actual delivery by state', fontsize=10)
    ax.set_xticks(range(0, 24, 3))
    ax.grid(alpha=0.3)
    ax.legend(loc='best', fontsize=8)
    
    # Right: bar chart of S0 vs S1 mean basal
    ax = axes[1]
    s0_mean = merged[merged['state'] == 0]['actual_basal_rate'].mean()
    s1_mean = merged[merged['state'] == 1]['actual_basal_rate'].mean()
    sched_mean = merged['scheduled_basal_rate'].mean()
    bars = ax.bar(['Profile\n(scheduled)', 'S0 actual\n(baseline)', 'S1 actual\n(elevated)'],
                   [sched_mean, s0_mean, s1_mean],
                   color=['#888888', '#2ca02c', '#d62728'])
    for bar, val in zip(bars, [sched_mean, s0_mean, s1_mean]):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                f'{val:.3f}', ha='center', fontsize=10)
    ax.set_ylabel('Mean basal rate (U/hr)')
    pct_shift = (s1_mean - s0_mean) / max(abs(s0_mean), 0.01) * 100
    ax.set_title(f'State envelope shift: {pct_shift:+.1f}%\n'
                 f'(consider audition: temp basal during S1)', fontsize=10)
    ax.grid(alpha=0.3, axis='y')
    
    plt.tight_layout()
    out = OUT_VIZ / f'{pid}_profile_audit.png'
    plt.savefig(out, dpi=110, bbox_inches='tight')
    plt.close()
    print(f"  ✓ {out}")
    return True


def chart_recovery_diagnostic(pid):
    """For patients with multiple S0->S1 transitions, show recovery pattern."""
    transitions_path = EXP_OUT / 'exp-2812_pre_post_transitions.parquet'
    if not transitions_path.exists():
        return False
    pp = pd.read_parquet(transitions_path)
    pat_pp = pp[pp['patient_id'] == pid]
    if len(pat_pp) < 3:
        return False
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    fig.suptitle(f'Patient {pid} — Recovery Diagnostic ({len(pat_pp)} S0→S1 transitions)',
                 fontsize=13, fontweight='bold')
    
    # Left: TIR before vs after
    ax = axes[0]
    ax.scatter(pat_pp['pre_pct_in_range'], pat_pp['post_pct_in_range'],
               s=80, alpha=0.7, color=COLOR_BASAL_ACTUAL)
    lim = [0, 100]
    ax.plot(lim, lim, 'k--', alpha=0.4, label='No change line')
    ax.set_xlabel('Pre-transition TIR (%)')
    ax.set_ylabel('Post-transition TIR (%)')
    ax.set_title('TIR before vs after S0→S1 transition\n'
                 '(below diagonal = deterioration)', fontsize=10)
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.grid(alpha=0.3)
    ax.legend()
    
    # Right: recovery histogram vs cohort
    ax = axes[1]
    cohort = pp['recovery_fraction_3w']
    ax.hist(cohort, bins=11, color='lightgray', alpha=0.6,
            label=f'Cohort (N={len(pp)} transitions)', edgecolor='gray')
    ax.axvline(cohort.median(), color='gray', ls='--', label=f'Cohort median: {cohort.median():.2f}')
    ax.axvline(pat_pp['recovery_fraction_3w'].median(), color='red', lw=2,
               label=f'Patient median: {pat_pp["recovery_fraction_3w"].median():.2f}')
    ax.set_xlabel('Recovery fraction (next 3 windows)')
    ax.set_ylabel('Count')
    ax.set_title('Self-recovery vs cohort\n(higher = better self-correction)',
                 fontsize=10)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    out = OUT_VIZ / f'{pid}_recovery_diagnostic.png'
    plt.savefig(out, dpi=110, bbox_inches='tight')
    plt.close()
    print(f"  ✓ {out}")
    return True


def chart_site_age(pid):
    """ISF by cannula age (when wear data available)."""
    pat = g[g['patient_id'] == pid].copy()
    if 'cage_hours' not in pat.columns or pat['cage_hours'].isna().all():
        return False
    # Bin cannula age and compute observed effective response per bin
    pat['cage_bin'] = pd.cut(pat['cage_hours'], 
                              bins=[0, 24, 48, 72, 96, 120, 168, 999],
                              labels=['<1d', '1-2d', '2-3d', '3-4d', '4-5d', '5-7d', '>7d'])
    # Use insulin_activity or actual_basal_rate as proxy for "insulin needed"
    pat = pat.dropna(subset=['cage_bin', 'glucose'])
    if len(pat) < 100:
        return False
    binned = pat.groupby('cage_bin').agg(
        mean_bg=('glucose', 'mean'),
        mean_basal=('actual_basal_rate', 'mean'),
        std_bg=('glucose', 'std'),
        n=('glucose', 'count'),
    )
    binned = binned[binned['n'] > 50]
    if len(binned) < 3:
        return False
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    fig.suptitle(f'Patient {pid} — Site-Age Trajectory', fontsize=13, fontweight='bold')
    
    ax = axes[0]
    ax.plot(binned.index.astype(str), binned['mean_basal'], 'o-',
            color=COLOR_BASAL_ACTUAL, lw=2, ms=8)
    ax.set_xlabel('Cannula age')
    ax.set_ylabel('Mean basal delivery (U/hr)')
    ax.set_title('Controller basal demand by cannula age\n'
                 '(rising = potential site degradation)', fontsize=10)
    ax.grid(alpha=0.3)
    
    ax = axes[1]
    ax.errorbar(range(len(binned)), binned['mean_bg'], yerr=binned['std_bg'],
                fmt='o-', color=COLOR_BG, lw=2, ms=8, capsize=5)
    ax.set_xticks(range(len(binned)))
    ax.set_xticklabels(binned.index.astype(str))
    ax.set_xlabel('Cannula age')
    ax.set_ylabel('Mean BG ± std')
    ax.set_title('BG control by cannula age', fontsize=10)
    ax.grid(alpha=0.3)
    
    plt.tight_layout()
    out = OUT_VIZ / f'{pid}_site_age.png'
    plt.savefig(out, dpi=110, bbox_inches='tight')
    plt.close()
    print(f"  ✓ {out}")
    return True


# Generate charts for example patients
# Pick: b (BOTH triage flags), c (large +69% basal shift), 
# ns-8f3527d1ee40 (large -61% basal shift)
example_patients = ['b', 'c', 'ns-8f3527d1ee40']

print("\n=== Generating diagnostic charts ===\n")
manifest = []
for pid in example_patients:
    print(f"\nPatient {pid}:")
    charts_made = []
    if chart_week_envelope(pid):
        charts_made.append('week_envelope')
    if chart_meal_event(pid):
        charts_made.append('meal_event')
    if chart_profile_audit(pid):
        charts_made.append('profile_audit')
    if chart_recovery_diagnostic(pid):
        charts_made.append('recovery_diagnostic')
    if chart_site_age(pid):
        charts_made.append('site_age')
    manifest.append({'patient_id': pid, 'charts': charts_made})

with open(OUT_VIZ / 'manifest.json', 'w') as f:
    json.dump(manifest, f, indent=2)
print(f"\nDone. Charts saved to {OUT_VIZ}/")
print(f"Manifest: {OUT_VIZ}/manifest.json")
