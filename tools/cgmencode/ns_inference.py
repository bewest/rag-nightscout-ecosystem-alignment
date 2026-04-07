#!/usr/bin/env python3
"""
ns_inference.py — CLI for the Nightscout CGM inference engine.

Connects to a Nightscout instance (or reads local data) and runs
production inference: triage, meal detection, pattern analysis,
risk assessment, settings recommendations, and action planning.

Usage:
    # Quick dashboard from live Nightscout
    python3 tools/cgmencode/ns_inference.py \\
        --env ../t1pal-mobile-workspace/externals/ns_url.env \\
        status

    # Full triage report from local patient data
    python3 tools/cgmencode/ns_inference.py \\
        --dir externals/ns-data/patients/a/verification \\
        triage

    # Meal analysis with timing prediction
    python3 tools/cgmencode/ns_inference.py \\
        --url https://your-ns.example.com --days 30 \\
        meals --predict-next

    # All capabilities at once
    python3 tools/cgmencode/ns_inference.py \\
        --env path/to/ns_url.env --days 14 \\
        report --json

Subcommands:
    status   — Quick dashboard: grade, TIR, risk, current BG
    triage   — ISF/CR/Basal assessment with recommendations
    meals    — Meal detection, timing patterns, next-meal prediction
    patterns — Circadian analysis, phenotype, drift detection
    quality  — Data quality assessment (spikes, gaps, sensor age)
    report   — Full clinical summary (all capabilities)
    recommend — Action recommendations ranked by priority
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# ── Resolve imports ──────────────────────────────────────────────────
# Allow running from repo root or from tools/cgmencode/
_this_dir = Path(__file__).resolve().parent
_tools_dir = _this_dir.parent.parent  # repo root / tools / cgmencode
if str(_this_dir.parent) not in sys.path:
    sys.path.insert(0, str(_this_dir.parent))
if str(_this_dir) not in sys.path:
    sys.path.insert(0, str(_this_dir))

from production.types import (
    PatientData, PatientProfile, PipelineResult,
    GlycemicGrade, MealWindow, SettingsParameter,
)
from production.pipeline import run_pipeline


# ═══════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════

def load_ns_url(env_path: str) -> str:
    """Parse NS_URL from a bash-style env file."""
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith('NS_URL='):
                url = line.split('=', 1)[1].strip().strip('"').strip("'")
                return url.rstrip('/')
    raise ValueError(f'NS_URL not found in {env_path}')


def resolve_ns_url(args) -> Optional[str]:
    """Resolve Nightscout URL from args (--url or --env)."""
    if getattr(args, 'url', None):
        return args.url.rstrip('/')
    if getattr(args, 'env', None):
        return load_ns_url(args.env)
    return None


def fetch_json(url: str, params: Optional[dict] = None) -> list:
    """Fetch JSON from Nightscout API."""
    import urllib.request
    import urllib.parse
    if params:
        qs = urllib.parse.urlencode(params)
        url = f'{url}?{qs}'
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_nightscout_data(base_url: str, days: int = 14,
                          verbose: bool = False) -> dict:
    """Fetch entries, treatments, profile from Nightscout API.

    Returns dict with keys: entries, treatments, profile.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    if verbose:
        print(f'Fetching {days} days from {base_url}...')

    # Entries (7-day windows, 10K limit per window)
    all_entries = []
    window_ms = 7 * 86400 * 1000
    cursor = end_ms
    while cursor > start_ms:
        win_start = max(start_ms, cursor - window_ms)
        if verbose:
            d1 = datetime.fromtimestamp(win_start / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            d2 = datetime.fromtimestamp(cursor / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            print(f'  entries {d1} → {d2}...', end='', flush=True)
        params = {
            'find[date][$gte]': int(win_start),
            'find[date][$lt]': int(cursor),
            'count': 10000,
        }
        chunk = fetch_json(f'{base_url}/api/v1/entries.json', params)
        if verbose:
            print(f' {len(chunk)} records')
        all_entries.extend(chunk)
        cursor -= window_ms
        time.sleep(0.3)

    # Treatments
    all_treatments = []
    window = timedelta(days=7)
    cursor_dt = now
    while cursor_dt > start:
        win_start = max(start, cursor_dt - window)
        if verbose:
            print(f'  treatments {win_start.strftime("%Y-%m-%d")} → '
                  f'{cursor_dt.strftime("%Y-%m-%d")}...', end='', flush=True)
        params = {
            'find[created_at][$gte]': win_start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'find[created_at][$lt]': cursor_dt.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'count': 10000,
        }
        chunk = fetch_json(f'{base_url}/api/v1/treatments.json', params)
        if verbose:
            print(f' {len(chunk)} records')
        all_treatments.extend(chunk)
        cursor_dt -= window
        time.sleep(0.3)

    # Profile
    if verbose:
        print('  profile...', end='', flush=True)
    profile = fetch_json(f'{base_url}/api/v1/profile.json')
    if verbose:
        print(' ok')

    # Deduplicate
    def dedup(items, key='_id'):
        seen = set()
        out = []
        for item in items:
            k = item.get(key, id(item))
            if k not in seen:
                seen.add(k)
                out.append(item)
        return out

    return {
        'entries': dedup(all_entries),
        'treatments': dedup(all_treatments),
        'profile': profile,
    }


def load_local_data(data_dir: str) -> dict:
    """Load entries, treatments, profile from a local directory."""
    data_dir = Path(data_dir)
    result = {}
    for name in ['entries', 'treatments', 'profile']:
        fpath = data_dir / f'{name}.json'
        if fpath.exists():
            with open(fpath) as f:
                result[name] = json.load(f)
        else:
            result[name] = []
    return result


def build_patient_data(raw: dict, patient_id: str = 'live',
                       days: Optional[int] = None) -> PatientData:
    """Convert raw Nightscout JSON into PatientData for the pipeline."""
    entries = raw['entries']
    treatments = raw.get('treatments', [])
    profile_raw = raw.get('profile', [])

    # Parse entries → glucose + timestamps (chronological order)
    sgvs = [e for e in entries if e.get('sgv') and e.get('date')]
    sgvs.sort(key=lambda e: e['date'])

    if days:
        cutoff = sgvs[-1]['date'] - days * 86400 * 1000 if sgvs else 0
        sgvs = [e for e in sgvs if e['date'] >= cutoff]

    if not sgvs:
        raise ValueError('No CGM readings found in data')

    glucose = np.array([e['sgv'] for e in sgvs], dtype=float)
    timestamps = np.array([e['date'] for e in sgvs], dtype=float)
    n = len(glucose)

    # Parse treatments → bolus, carbs arrays
    bolus_arr = np.zeros(n)
    carbs_arr = np.zeros(n)
    for t in treatments:
        ts = t.get('date', t.get('timestamp'))
        if ts is None:
            # Try parsing created_at
            ca = t.get('created_at', '')
            if ca:
                try:
                    dt = datetime.fromisoformat(ca.replace('Z', '+00:00'))
                    ts = int(dt.timestamp() * 1000)
                except (ValueError, TypeError):
                    continue
        if ts is None or isinstance(ts, str):
            continue
        idx = np.searchsorted(timestamps, ts)
        if 0 <= idx < n:
            ins = t.get('insulin') or 0
            carbs = t.get('carbs') or 0
            if ins > 0:
                bolus_arr[idx] += ins
            if carbs > 0:
                carbs_arr[idx] += carbs

    # Parse profile
    store = None
    if isinstance(profile_raw, list) and profile_raw:
        store = profile_raw[0].get('store', {})
    elif isinstance(profile_raw, dict):
        store = profile_raw.get('store', {})

    if store:
        dp = next(iter(store.values()), {})
        isf_sched = dp.get('sens', [{'time': '00:00', 'value': 50}])
        cr_sched = dp.get('carbratio', [{'time': '00:00', 'value': 10}])
        basal_sched = dp.get('basal', [{'time': '00:00', 'value': 1.0}])
        dia = dp.get('dia', 5.0)
    else:
        isf_sched = [{'time': '00:00', 'value': 50}]
        cr_sched = [{'time': '00:00', 'value': 10}]
        basal_sched = [{'time': '00:00', 'value': 1.0}]
        dia = 5.0

    profile = PatientProfile(
        isf_schedule=isf_sched,
        cr_schedule=cr_sched,
        basal_schedule=basal_sched,
        dia_hours=float(dia),
    )

    basal_val = basal_sched[0].get('value', basal_sched[0].get('rate', 1.0))

    return PatientData(
        patient_id=patient_id,
        glucose=glucose,
        timestamps=timestamps,
        profile=profile,
        bolus=bolus_arr,
        carbs=carbs_arr,
        iob=np.zeros(n),   # Zeroed; pipeline computes from bolus
        cob=np.zeros(n),
        basal_rate=np.full(n, float(basal_val)),
    )


# ═══════════════════════════════════════════════════════════════════════
# OUTPUT FORMATTING
# ═══════════════════════════════════════════════════════════════════════

GRADE_EMOJI = {
    GlycemicGrade.A: '🟢 A',
    GlycemicGrade.B: '🟡 B',
    GlycemicGrade.C: '🟠 C',
    GlycemicGrade.D: '🔴 D',
}

def fmt_pct(v: float) -> str:
    return f'{v * 100:.1f}%'

def fmt_tir_bar(tir: float, tbr: float, tar: float, width: int = 40) -> str:
    """Render TIR/TBR/TAR as a colored bar."""
    n_low = max(1, int(tbr * width)) if tbr > 0.01 else 0
    n_high = max(1, int(tar * width)) if tar > 0.01 else 0
    n_range = width - n_low - n_high
    return f'[{"▓" * n_low}{"█" * n_range}{"░" * n_high}]'

def section_header(title: str) -> str:
    return f'\n{"─" * 60}\n  {title}\n{"─" * 60}'


# ═══════════════════════════════════════════════════════════════════════
# SUBCOMMANDS
# ═══════════════════════════════════════════════════════════════════════

def cmd_status(result: PipelineResult, args) -> dict:
    """Quick dashboard: grade, TIR, risk, current BG."""
    cr = result.clinical_report
    bg = result.cleaned.glucose
    current_bg = float(bg[~np.isnan(bg)][-1]) if len(bg) > 0 else 0

    # Trend from last 6 readings (30 min)
    recent = bg[~np.isnan(bg)][-6:]
    if len(recent) >= 2:
        trend = float(recent[-1] - recent[0])
        trend_arrow = '↑' if trend > 10 else '↓' if trend < -10 else '→'
        trend_rate = trend / (len(recent) * 5)  # mg/dL per min
    else:
        trend_arrow, trend_rate = '?', 0.0

    out = {
        'current_bg': current_bg,
        'trend': trend_arrow,
        'trend_rate_per_min': round(trend_rate, 2),
        'grade': cr.grade.value,
        'tir': round(cr.tir * 100, 1),
        'tbr': round(cr.tbr * 100, 1),
        'tar': round(cr.tar * 100, 1),
        'estimated_a1c': round(cr.gmi, 1) if cr.gmi else None,
        'hypo_risk': round(result.hypo_alert.probability, 2) if result.hypo_alert else None,
        'pipeline_ms': round(result.pipeline_latency_ms),
    }

    if not getattr(args, 'json_output', False):
        grade_str = GRADE_EMOJI.get(cr.grade, cr.grade.value)
        bar = fmt_tir_bar(cr.tir, cr.tbr, cr.tar)
        hypo = result.hypo_alert

        print(section_header('STATUS DASHBOARD'))
        print(f'  Current BG:   {current_bg:.0f} mg/dL {trend_arrow} ({trend_rate:+.1f}/min)')
        print(f'  Grade:        {grade_str}')
        print(f'  A1c est:      {cr.gmi:.1f}%' if cr.gmi else '')
        print(f'  TIR:          {fmt_pct(cr.tir)} {bar}')
        print(f'                ▓ Low {fmt_pct(cr.tbr)}  █ In Range  ░ High {fmt_pct(cr.tar)}')
        if hypo and hypo.should_alert:
            lead = f' ({hypo.lead_time_estimate:.0f} min)' if hypo.lead_time_estimate else ''
            print(f'  ⚠ HYPO RISK:  {hypo.probability*100:.0f}% in {hypo.horizon_minutes}min{lead}')
        print(f'  Latency:      {result.pipeline_latency_ms:.0f}ms')

        if result.recommendations:
            print(f'\n  Top recommendations:')
            for rec in result.recommendations[:3]:
                pri = ['', '🚨', '📋', 'ℹ️'][rec.priority]
                print(f'    {pri} {rec.description[:75]}')

    return out


def cmd_triage(result: PipelineResult, args) -> dict:
    """ISF/CR/Basal triage with counterfactual recommendations."""
    cr = result.clinical_report
    out = {
        'grade': cr.grade.value,
        'basal_assessment': cr.basal_assessment.value if cr.basal_assessment else None,
        'cr_score': cr.cr_score,
        'isf_discrepancy': cr.isf_discrepancy,
        'effective_isf': cr.effective_isf,
        'settings_recs': [],
    }

    if not getattr(args, 'json_output', False):
        print(section_header('SETTINGS TRIAGE'))

        # Basal
        ba = cr.basal_assessment
        if ba:
            emoji = {'appropriate': '✅', 'too_low': '⬆️', 'too_high': '⬇️',
                     'slightly_high': '↘️'}.get(ba.value, '❓')
            print(f'  Basal:        {emoji} {ba.value}')
            if cr.overnight_tir is not None:
                print(f'  Overnight TIR: {fmt_pct(cr.overnight_tir)}')
        else:
            print(f'  Basal:        — (insufficient data)')

        # CR
        print(f'  CR score:     {cr.cr_score:.0f}/100'
              + (' ⚠ poor' if cr.cr_score < 40 else ' ✅ ok'))

        # ISF
        if cr.isf_discrepancy:
            ratio = cr.isf_discrepancy
            emoji = '⚠️' if ratio > 2.0 else '✅'
            print(f'  ISF ratio:    {ratio:.1f}× (effective / profile) {emoji}')
            if cr.effective_isf:
                isf_vals = [e.get('value', e.get('sensitivity', 50))
                            for e in result.clinical_report._profile_isf_schedule
                            ] if hasattr(cr, '_profile_isf_schedule') else []
                print(f'  Effective ISF: {cr.effective_isf:.0f} mg/dL/U')
        else:
            print(f'  ISF ratio:    — (not computed)')

        # Circadian ISF variation
        if result.patterns and result.patterns.isf_variation_pct:
            v = result.patterns.isf_variation_pct
            flag = ' ⚠ consider time-segmented ISF' if v > 50 else ''
            print(f'  ISF variation: {v:.0f}% across time of day{flag}')

        # Settings recommendations
        if result.settings_recs:
            print(f'\n  Recommended changes:')
            for sr in result.settings_recs:
                delta = f'{sr.predicted_tir_delta:+.1f}pp TIR' if sr.predicted_tir_delta else ''
                print(f'    • {sr.parameter.value}: {sr.direction} {sr.magnitude_pct:.0f}%'
                      f' ({sr.current_value:.1f} → {sr.suggested_value:.1f}) {delta}')
                print(f'      {sr.evidence[:80]}')
        else:
            print(f'\n  No settings changes recommended.')

        # Period-by-period
        print(f'\n  Period analysis:')
        periods = [('Fasting (00-06)', 0, 6), ('Morning (06-12)', 6, 12),
                   ('Afternoon (12-18)', 12, 18), ('Evening (18-24)', 18, 24)]
        if result.metabolic:
            from production.metabolic_engine import _extract_hours
            hours = _extract_hours(result.cleaned.glucose)
            # Use pipeline's hours array (same length as cleaned glucose)
            if hasattr(result, '_hours'):
                hours = result._hours
            bg = result.cleaned.glucose
            for label, h_start, h_end in periods:
                # Can't reliably extract hours here without timestamps,
                # but clinical report has overall stats
                pass
            # Simplified: show overall clinical recs
            for rec_text in cr.recommendations:
                print(f'    {rec_text[:78]}')

    if result.settings_recs:
        out['settings_recs'] = [
            {
                'parameter': sr.parameter.value,
                'direction': sr.direction,
                'magnitude_pct': sr.magnitude_pct,
                'current': sr.current_value,
                'suggested': sr.suggested_value,
                'predicted_tir_delta': sr.predicted_tir_delta,
                'confidence': sr.confidence,
                'rationale': sr.rationale,
            }
            for sr in result.settings_recs
        ]

    return out


def cmd_meals(result: PipelineResult, args) -> dict:
    """Meal detection, timing patterns, next-meal prediction."""
    mh = result.meal_history
    mp = result.meal_prediction
    out = {
        'total_detected': mh.total_detected if mh else 0,
        'meals_per_day': round(mh.meals_per_day, 1) if mh else 0,
        'unannounced_fraction': round(mh.unannounced_fraction, 2) if mh else None,
        'by_window': mh.by_window if mh else {},
        'prediction': None,
    }

    if not getattr(args, 'json_output', False):
        print(section_header('MEAL ANALYSIS'))

        if not mh:
            print('  No meal data available (metabolic engine required)')
            return out

        print(f'  Detected:     {mh.total_detected} meals '
              f'({mh.meals_per_day:.1f}/day)')
        print(f'  Announced:    {mh.announced_count} '
              f'({100 - mh.unannounced_fraction*100:.0f}%)')
        print(f'  Unannounced:  {mh.unannounced_count} '
              f'({mh.unannounced_fraction*100:.0f}%) '
              + ('⚠ high' if mh.unannounced_fraction > 0.40 else ''))
        print(f'  Avg size:     ~{mh.mean_carbs_g:.0f}g estimated')

        print(f'\n  By meal window:')
        for window, count in sorted(mh.by_window.items()):
            bar = '█' * min(20, count)
            print(f'    {window:>10}: {count:>3} {bar}')

        # Timing models
        if mp and mp.timing_models:
            print(f'\n  Timing patterns (learned from history):')
            for tm in mp.timing_models:
                print(f'    {tm.window.value:>10}: '
                      f'{tm.mean_hour:.1f}h ± {tm.std_hour:.1f}h, '
                      f'{tm.frequency_per_day:.1f}×/day')

        # Prediction
        if mp:
            out['prediction'] = {
                'window': mp.predicted_window.value,
                'hour': round(mp.predicted_hour, 1),
                'minutes_until': round(mp.minutes_until),
                'confidence': round(mp.confidence, 2),
                'eating_soon': mp.recommend_eating_soon,
                'estimated_carbs_g': round(mp.estimated_carbs_g),
            }
            emoji = '🍽️' if mp.recommend_eating_soon else '🕐'
            print(f'\n  {emoji} Next meal prediction:')
            print(f'    {mp.predicted_window.value.capitalize()} at '
                  f'~{mp.predicted_hour:.1f}h '
                  f'(in {mp.minutes_until:.0f} min)')
            print(f'    Estimated: ~{mp.estimated_carbs_g:.0f}g, '
                  f'confidence: {mp.confidence:.0%}')
            if mp.recommend_eating_soon:
                print(f'    ✅ RECOMMEND: Pre-bolus now for better post-meal control')
        elif mh.total_detected >= 10:
            # Have meals but no prediction — show why
            print(f'\n  ℹ️  Meal timing too variable for reliable prediction')

    return out


def cmd_patterns(result: PipelineResult, args) -> dict:
    """Circadian analysis, phenotype, drift detection."""
    pat = result.patterns
    out = {
        'phenotype': pat.phenotype.value if pat else None,
        'circadian': None,
        'changepoints': None,
    }

    if not getattr(args, 'json_output', False):
        print(section_header('PATTERN ANALYSIS'))

        if not pat:
            print('  Insufficient data for pattern analysis (need ≥7 days)')
            return out

        # Phenotype
        phenotype_desc = {
            'morning_high': '☀️  Morning highs — consider dawn phenomenon override',
            'night_hypo': '🌙 Nighttime lows — consider reducing overnight basal',
            'stable': '✅ Stable patterns — no dominant problematic period',
        }
        desc = phenotype_desc.get(pat.phenotype.value,
                                   f'  {pat.phenotype.value}')
        print(f'  Phenotype:    {desc}')

        # Circadian
        if pat.circadian:
            c = pat.circadian
            out['circadian'] = {
                'amplitude': round(c.amplitude, 1),
                'peak_hour': round(c.phase_hours, 1),
                'trough_hour': round((c.phase_hours + 12) % 24, 1),
            }
            print(f'\n  Circadian rhythm:')
            print(f'    Amplitude:  {c.amplitude:.1f} mg/dL')
            print(f'    Peak:       {c.phase_hours:.1f}h '
                  f'(~{int(c.phase_hours)}:{int((c.phase_hours%1)*60):02d})')
            print(f'    Trough:     {(c.phase_hours + 12) % 24:.1f}h')

        # ISF variation
        if pat.isf_variation_pct:
            out['isf_variation_pct'] = round(pat.isf_variation_pct, 1)
            flag = '⚠ HIGH — time-segment ISF' if pat.isf_variation_pct > 50 else ''
            print(f'    ISF var:    {pat.isf_variation_pct:.0f}% {flag}')

        # Changepoints
        if pat.n_changepoints is not None:
            out['changepoints'] = pat.n_changepoints
            stability = ('🔄 volatile' if pat.n_changepoints > 5
                         else '📌 stable' if pat.n_changepoints <= 1
                         else '  moderate')
            print(f'\n  Settings drift:')
            print(f'    Changepoints: {pat.n_changepoints} {stability}')

        # Weekly trend
        if pat.weekly_trend:
            trend_emoji = {'improving': '📈', 'declining': '📉', 'stable': '➡️'}
            print(f'    Weekly trend: {trend_emoji.get(pat.weekly_trend, "")} {pat.weekly_trend}')
            if pat.tir_first_half is not None and pat.tir_second_half is not None:
                print(f'    TIR 1st half: {fmt_pct(pat.tir_first_half)} → '
                      f'2nd half: {fmt_pct(pat.tir_second_half)}')

    return out


def cmd_quality(result: PipelineResult, args) -> dict:
    """Data quality assessment."""
    cd = result.cleaned
    out = {
        'n_readings': len(cd.glucose),
        'n_spikes': cd.n_spikes,
        'spike_rate': round(cd.spike_rate * 100, 1),
        'n_gaps': int(np.sum(np.isnan(cd.glucose))),
        'completeness': round((1 - np.mean(np.isnan(cd.glucose))) * 100, 1),
    }

    if not getattr(args, 'json_output', False):
        print(section_header('DATA QUALITY'))
        print(f'  Readings:     {out["n_readings"]:,}')
        print(f'  Spikes:       {out["n_spikes"]:,} ({out["spike_rate"]}%)'
              + (' ⚠ high' if out['spike_rate'] > 5 else ' ✅'))
        print(f'  Gaps (NaN):   {out["n_gaps"]:,}')
        print(f'  Completeness: {out["completeness"]}%')

        days = result.cleaned.glucose.shape[0] * 5 / 60 / 24
        print(f'  Duration:     {days:.1f} days')

        # Warn if data is too short for certain analyses
        if days < 3:
            print(f'  ⚠  <3 days: hypo calibration and settings unavailable')
        elif days < 7:
            print(f'  ⚠  <7 days: pattern analysis and meal prediction unavailable')
        elif days < 14:
            print(f'  ℹ️  <14 days: reduced confidence in recommendations')

        if result.warnings:
            print(f'\n  Pipeline warnings:')
            for w in result.warnings:
                print(f'    ⚠ {w}')

    return out


def cmd_recommend(result: PipelineResult, args) -> dict:
    """Action recommendations ranked by priority."""
    recs = result.recommendations or []
    out = {'recommendations': []}

    if not getattr(args, 'json_output', False):
        print(section_header('ACTION RECOMMENDATIONS'))

        if not recs:
            print('  ✅ No actionable recommendations at this time.')
            return out

        pri_labels = {1: '🚨 SAFETY', 2: '📋 TIR IMPROVEMENT', 3: 'ℹ️  INSIGHT'}
        current_pri = None

        for rec in recs:
            if rec.priority != current_pri:
                current_pri = rec.priority
                print(f'\n  {pri_labels.get(rec.priority, f"Priority {rec.priority}")}:')

            delta = f' [{rec.predicted_tir_delta:+.1f}pp TIR]' if rec.predicted_tir_delta else ''
            conf = f' (conf: {rec.confidence:.0%})' if rec.confidence else ''

            print(f'    • {rec.action_type}: {rec.description[:78]}')
            if rec.predicted_tir_delta or rec.confidence:
                print(f'      {delta}{conf}')
            if rec.time_sensitive:
                deadline = f' in {rec.deadline_minutes:.0f}min' if rec.deadline_minutes else ''
                print(f'      ⏰ Time-sensitive{deadline}')

    for rec in recs:
        out['recommendations'].append({
            'type': rec.action_type,
            'priority': rec.priority,
            'description': rec.description,
            'tir_delta': rec.predicted_tir_delta,
            'confidence': rec.confidence,
            'time_sensitive': rec.time_sensitive,
        })

    return out


def cmd_report(result: PipelineResult, args) -> dict:
    """Full clinical summary — all capabilities at once."""
    out = {}

    if not getattr(args, 'json_output', False):
        print(f'\n{"═" * 60}')
        print(f'  CLINICAL INFERENCE REPORT')
        print(f'  Patient: {result.patient_id}')
        print(f'  Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        print(f'{"═" * 60}')

    out['status'] = cmd_status(result, args)
    out['quality'] = cmd_quality(result, args)
    out['triage'] = cmd_triage(result, args)
    out['meals'] = cmd_meals(result, args)
    out['patterns'] = cmd_patterns(result, args)
    out['recommendations'] = cmd_recommend(result, args)

    if not getattr(args, 'json_output', False):
        print(f'\n{"═" * 60}')
        print(f'  Pipeline: {result.pipeline_latency_ms:.0f}ms')
        print(f'{"═" * 60}')

    return out


# ═══════════════════════════════════════════════════════════════════════
# CLI ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════

COMMANDS = {
    'status': ('Quick dashboard: grade, TIR, risk, current BG', cmd_status),
    'triage': ('ISF/CR/Basal assessment with recommendations', cmd_triage),
    'meals': ('Meal detection, timing patterns, predictions', cmd_meals),
    'patterns': ('Circadian analysis, phenotype, drift detection', cmd_patterns),
    'quality': ('Data quality assessment', cmd_quality),
    'recommend': ('Action recommendations ranked by priority', cmd_recommend),
    'report': ('Full clinical summary (all capabilities)', cmd_report),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='ns_inference',
        description='Nightscout CGM Inference Engine — production analytics from your CGM data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
        Examples:
            %(prog)s --env ns_url.env status
            %(prog)s --dir externals/ns-data/patients/a/verification triage
            %(prog)s --url https://my-ns.example.com --days 30 meals
            %(prog)s --env ns_url.env report --json
            %(prog)s --dir externals/ns-data/patients/a/verification recommend
        """),
    )

    # Data source (mutually exclusive)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--url', help='Nightscout site URL')
    src.add_argument('--env', help='Path to env file with NS_URL=...')
    src.add_argument('--dir', help='Local directory with entries.json, treatments.json, profile.json')

    # Options
    parser.add_argument('--days', type=int, default=14,
                        help='Days of data to analyze (default: 14)')
    parser.add_argument('--patient-id', default='live',
                        help='Patient identifier (default: live)')
    parser.add_argument('--json', dest='json_output', action='store_true',
                        help='Output as JSON (for piping to other tools)')
    parser.add_argument('--current-hour', type=float, default=None,
                        help='Current hour for meal prediction (default: now)')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress progress messages')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Show detailed fetch progress')

    # Subcommands
    sub = parser.add_subparsers(dest='command', help='Inference command')
    for name, (desc, _func) in COMMANDS.items():
        sub.add_parser(name, help=desc)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        args.command = 'status'  # Default to status dashboard

    # ── Load data ─────────────────────────────────────────────────
    if args.dir:
        if not args.quiet:
            print(f'Loading from {args.dir}...')
        raw = load_local_data(args.dir)
    else:
        ns_url = resolve_ns_url(args)
        if not ns_url:
            parser.error('Must specify --url, --env, or --dir')
        if not args.quiet:
            print(f'Connecting to {ns_url}...')
        raw = fetch_nightscout_data(ns_url, days=args.days,
                                     verbose=args.verbose)

    # ── Build patient ─────────────────────────────────────────────
    patient = build_patient_data(raw, patient_id=args.patient_id,
                                  days=args.days)

    if not args.quiet:
        days = patient.days_of_data
        n = patient.n_samples
        print(f'Loaded {n:,} readings ({days:.1f} days)')

    # ── Resolve current hour ──────────────────────────────────────
    current_hour = args.current_hour
    if current_hour is None:
        current_hour = datetime.now().hour + datetime.now().minute / 60.0

    # ── Run pipeline ──────────────────────────────────────────────
    result = run_pipeline(patient, current_hour=current_hour)

    # ── Execute command ───────────────────────────────────────────
    _, cmd_func = COMMANDS[args.command]
    out = cmd_func(result, args)

    if args.json_output:
        # Serialize numpy types
        def default_serializer(obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return str(obj)

        print(json.dumps(out, indent=2, default=default_serializer))


if __name__ == '__main__':
    main()
