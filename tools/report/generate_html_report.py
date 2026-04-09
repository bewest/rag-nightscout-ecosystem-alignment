#!/usr/bin/env python3
"""Generate an interactive HTML clinical report from Nightscout data.

Loads data, runs the production inference pipeline, and produces a single
self-contained HTML file with interactive Chart.js visualizations.

Usage:
    PYTHONPATH=tools python tools/report/generate_html_report.py [DATA_DIR] [OUTPUT]

    DATA_DIR  defaults to externals/ns-data/live-recent
    OUTPUT    defaults to DATA_DIR/reports/report.html
"""
import json
import sys
import os
import time
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

from report.ns_loader import load_from_dir
from cgmencode.production.pipeline import run_pipeline

DATA_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'externals' / 'ns-data' / 'live-recent'
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else DATA_DIR / 'reports' / 'report.html'
OUTPUT.parent.mkdir(parents=True, exist_ok=True)


# ═════════════════════════════════════════════════════════════════════
# 1. Load data
# ═════════════════════════════════════════════════════════════════════
print("=" * 60)
print("CGM Clinical Report Generator")
print("=" * 60)

patient, meta = load_from_dir(DATA_DIR)
if patient is None:
    print("FATAL: Could not load data"); sys.exit(1)

# ═════════════════════════════════════════════════════════════════════
# 2. Run pipeline
# ═════════════════════════════════════════════════════════════════════
print(f"\n=== Running pipeline ({patient.n_samples} samples) ===")
t0 = time.time()
result = run_pipeline(patient)
elapsed = time.time() - t0
print(f"  Done in {elapsed:.1f}s")
print(f"  Warnings: {result.warnings}")

cr = result.clinical_report
fid = cr.fidelity
pa = result.patterns
mh = result.meal_history
metabolic = result.metabolic


# ═════════════════════════════════════════════════════════════════════
# 3. Compute display data
# ═════════════════════════════════════════════════════════════════════
glucose = patient.glucose
timestamps = patient.timestamps
N = len(glucose)

# Overall stats
valid = glucose[np.isfinite(glucose) & (glucose > 0)]
tir = float(np.mean((valid >= 70) & (valid <= 180)) * 100)
tbr_70 = float(np.mean(valid < 70) * 100)
tbr_54 = float(np.mean(valid < 54) * 100)
tar_180 = float(np.mean(valid > 180) * 100)
tar_250 = float(np.mean(valid > 250) * 100)
mean_bg = float(np.mean(valid))
std_bg = float(np.std(valid))
cv = std_bg / mean_bg * 100
gmi = 3.31 + 0.02392 * mean_bg

# Hourly percentiles for AGP
hourly = defaultdict(list)
for i in range(N):
    if np.isfinite(glucose[i]):
        dt = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc)
        hourly[dt.hour].append(glucose[i])

agp = {}
for pct in ('p5', 'p10', 'p25', 'p50', 'p75', 'p90', 'p95'):
    agp[pct] = []
for h in range(24):
    vals = np.array(hourly.get(h, [0]), dtype=np.float64)
    agp['p5'].append(round(float(np.percentile(vals, 5)), 1))
    agp['p10'].append(round(float(np.percentile(vals, 10)), 1))
    agp['p25'].append(round(float(np.percentile(vals, 25)), 1))
    agp['p50'].append(round(float(np.percentile(vals, 50)), 1))
    agp['p75'].append(round(float(np.percentile(vals, 75)), 1))
    agp['p90'].append(round(float(np.percentile(vals, 90)), 1))
    agp['p95'].append(round(float(np.percentile(vals, 95)), 1))

# Harmonic fit curve (24 points)
harm_curve = [round(mean_bg)] * 24
if pa and pa.harmonic:
    harm_curve = pa.harmonic.predict(np.arange(24, dtype=np.float64))
    harm_curve = [round(float(v), 1) for v in harm_curve]

# Daily stats
daily_buckets = defaultdict(list)
for i in range(N):
    if np.isfinite(glucose[i]):
        dt = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc)
        daily_buckets[dt.strftime('%Y-%m-%d')].append(glucose[i])

daily_stats = []
for day in sorted(daily_buckets.keys()):
    v = np.array(daily_buckets[day], dtype=np.float64)
    daily_stats.append({
        'd': day,
        'mean': round(float(np.mean(v)), 0),
        'sd': round(float(np.std(v)), 0),
        'lo': int(np.min(v)),
        'hi': int(np.max(v)),
        'tir': round(float(np.mean((v >= 70) & (v <= 180)) * 100), 1),
        'tbr': round(float(np.mean(v < 70) * 100), 1),
        'tar': round(float(np.mean(v > 180) * 100), 1),
        'n': len(v),
    })

# Subsample SGV for main chart (target ~8000 points)
step = max(1, N // 8000)
sgv_chart = []
for i in range(0, N, step):
    if np.isfinite(glucose[i]):
        sgv_chart.append([int(timestamps[i]), int(glucose[i])])

# IOB/COB subsampled (target ~4000 points)
iob_chart = []
cob_chart = []
iob_step = max(1, N // 4000)
if patient.iob is not None:
    for i in range(0, N, iob_step):
        if np.isfinite(patient.iob[i]):
            iob_chart.append([int(timestamps[i]), round(float(patient.iob[i]), 2)])
if patient.cob is not None:
    for i in range(0, N, iob_step):
        if np.isfinite(patient.cob[i]):
            cob_chart.append([int(timestamps[i]), round(float(patient.cob[i]), 1)])

# Metabolic residual for sparkline
residual_hourly = [0.0] * 24
if metabolic is not None:
    res_buckets = defaultdict(list)
    for i in range(N):
        if np.isfinite(metabolic.residual[i]):
            dt = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc)
            res_buckets[dt.hour].append(abs(metabolic.residual[i]))
    for h in range(24):
        if res_buckets[h]:
            residual_hourly[h] = round(float(np.mean(res_buckets[h])), 2)

# Net flux subsampled
flux_chart = []
if metabolic is not None:
    for i in range(0, N, step):
        if np.isfinite(metabolic.net_flux[i]):
            flux_chart.append([int(timestamps[i]), round(float(metabolic.net_flux[i]), 2)])

# Treatment events (non-temp-basal)
treat_chart = []
for i in range(N):
    if patient.bolus[i] > 0:
        treat_chart.append({'t': int(timestamps[i]), 'type': 'bolus', 'v': round(float(patient.bolus[i]), 1)})
    if patient.carbs[i] > 0:
        treat_chart.append({'t': int(timestamps[i]), 'type': 'carbs', 'v': round(float(patient.carbs[i]), 0)})

# Meal archetypes summary
archetype_summary = {}
if mh and mh.meals:
    for m in mh.meals:
        a = m.archetype or 'unknown'
        if a not in archetype_summary:
            archetype_summary[a] = {'count': 0, 'mean_carbs': []}
        archetype_summary[a]['count'] += 1
        if m.estimated_carbs_g:
            archetype_summary[a]['mean_carbs'].append(m.estimated_carbs_g)
    for k in archetype_summary:
        mc = archetype_summary[k]['mean_carbs']
        archetype_summary[k]['mean_carbs'] = round(np.mean(mc), 1) if mc else 0

# Settings recommendations
recs_data = []
for r in result.settings_recs:
    recs_data.append({
        'param': r.parameter.value if hasattr(r.parameter, 'value') else str(r.parameter),
        'dir': r.direction,
        'current': r.current_value,
        'suggested': r.suggested_value,
        'evidence': r.evidence,
        'rationale': r.rationale,
    })

# ═════════════════════════════════════════════════════════════════════
# 4. Build the HTML
# ═════════════════════════════════════════════════════════════════════
print("\n=== Generating HTML ===")

date_start = datetime.fromtimestamp(meta['date_min']/1000, tz=timezone.utc).strftime('%Y-%m-%d')
date_end = datetime.fromtimestamp(meta['date_max']/1000, tz=timezone.utc).strftime('%Y-%m-%d')
ada = cr.grade.value
fid_grade = fid.fidelity_grade.value if fid else 'N/A'
fid_rmse = f'{fid.rmse:.1f}' if fid else '—'
fid_ce = f'{fid.correction_energy:.0f}' if fid else '—'
eff_isf = f'{cr.effective_isf:.1f}' if cr.effective_isf else '—'
isf_disc = f'{cr.isf_discrepancy:.2f}' if cr.isf_discrepancy else '—'
harm_r2 = f'{pa.harmonic.r2:.3f}' if pa and pa.harmonic else '—'
sin_r2 = f'{pa.circadian.r2_improvement:.3f}' if pa else '—'
n_meals = len(mh.meals) if mh else 0
uam_pct = f'{mh.unannounced_fraction*100:.0f}' if mh else '—'

# Color helpers
def tir_color(v):
    if v >= 70: return '#22c55e'
    if v >= 50: return '#eab308'
    return '#ef4444'

def grade_cls(g):
    return {'A': 'grade-a', 'B': 'grade-b', 'C': 'grade-c', 'D': 'grade-c'}.get(g, 'grade-b')

profile_isf = meta.get('profile_isf', ['?'])
profile_cr = meta.get('profile_cr', ['?'])
dia = meta.get('dia', '?')

html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Clinical Inference Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;
  --muted:#8b949e;--green:#3fb950;--yellow:#d29922;--red:#f85149;
  --orange:#db6d28;--blue:#58a6ff;--purple:#bc8cff;--cyan:#39d353;
}}
body{{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;line-height:1.6;padding:16px}}
.container{{max-width:1440px;margin:0 auto}}

/* Header */
header{{text-align:center;padding:20px 0 16px;border-bottom:1px solid var(--border);margin-bottom:20px}}
header h1{{font-size:22px;font-weight:600}}
.subtitle{{color:var(--muted);font-size:13px;margin-top:6px}}
.subtitle span{{margin:0 8px}}

/* Metric strip */
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:20px}}
.m-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;text-align:center}}
.m-card .lbl{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}}
.m-card .val{{font-size:28px;font-weight:700;margin:2px 0}}
.m-card .sub{{font-size:11px;color:var(--muted)}}

/* Section panels */
.panel{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:12px}}
.panel h2{{font-size:14px;font-weight:600;margin-bottom:12px;display:flex;align-items:center;gap:8px}}
.panel h2 .ico{{font-size:16px}}

/* Grid layouts */
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.g3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}}
@media(max-width:960px){{.g2,.g3{{grid-template-columns:1fr}}}}

/* Charts */
.chart-wrap{{position:relative;width:100%}}
.chart-wrap.h400{{height:380px}}
.chart-wrap.h300{{height:280px}}
.chart-wrap.h250{{height:240px}}

/* Range buttons */
.range-bar{{display:flex;gap:4px;margin-bottom:10px;flex-wrap:wrap}}
.rbtn{{padding:4px 12px;border:1px solid var(--border);border-radius:6px;background:transparent;color:var(--muted);cursor:pointer;font-size:12px;transition:all .15s}}
.rbtn:hover{{border-color:var(--blue);color:var(--blue)}}
.rbtn.on{{background:var(--blue);color:#fff;border-color:var(--blue)}}

/* TIR donut */
.tir-layout{{display:grid;grid-template-columns:180px 1fr;gap:20px;align-items:center}}
.tir-ring{{position:relative;width:180px;height:180px}}
.tir-ring canvas{{width:180px!important;height:180px!important}}
.tir-ctr{{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center}}
.tir-ctr .big{{font-size:32px;font-weight:700;color:var(--green)}}
.tir-ctr .tiny{{font-size:10px;color:var(--muted)}}
.tir-rows{{display:flex;flex-direction:column;gap:6px}}
.tir-row{{display:grid;grid-template-columns:90px 1fr 44px;gap:6px;align-items:center;font-size:13px}}
.tir-bar{{height:16px;border-radius:3px}}
.tir-row .pv{{text-align:right;font-weight:600;font-size:12px}}
@media(max-width:600px){{.tir-layout{{grid-template-columns:1fr;justify-items:center}}}}

/* Tables */
table.dt{{width:100%;border-collapse:collapse;font-size:12px}}
table.dt th{{text-align:left;padding:4px 8px;color:var(--muted);border-bottom:1px solid var(--border);font-weight:500;position:sticky;top:0;background:var(--card);z-index:1}}
table.dt td{{padding:4px 8px;border-bottom:1px solid var(--border)}}
table.dt tr:hover td{{background:rgba(255,255,255,.02)}}
.scroll-y{{max-height:380px;overflow-y:auto}}

/* Info cards */
.info-grid{{display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px}}
.info-row{{display:flex;justify-content:space-between;padding:6px 10px;border-bottom:1px solid var(--border)}}
.info-row .k{{color:var(--muted)}}
.info-row .v{{font-weight:600}}

/* Recommendation items */
.rec{{padding:10px 14px;border-left:3px solid var(--yellow);background:rgba(210,153,34,.06);border-radius:0 8px 8px 0;margin-bottom:8px;font-size:13px;line-height:1.5}}
.rec.ok{{border-left-color:var(--green);background:rgba(63,185,80,.06)}}
.rec.info{{border-left-color:var(--blue);background:rgba(88,166,255,.06)}}
.rec b{{font-weight:600}}
.rec .detail{{color:var(--muted);font-size:12px;margin-top:4px}}

/* Grades */
.grade{{display:inline-block;padding:2px 10px;border-radius:6px;font-weight:700;font-size:13px}}
.grade-a{{background:rgba(63,185,80,.15);color:var(--green)}}
.grade-b{{background:rgba(210,153,34,.15);color:var(--yellow)}}
.grade-c{{background:rgba(248,81,73,.15);color:var(--red)}}

/* Footer */
footer{{text-align:center;padding:20px 0;color:var(--muted);font-size:11px;border-top:1px solid var(--border);margin-top:20px}}

/* Tab system */
.tabs{{display:flex;gap:0;border-bottom:1px solid var(--border);margin-bottom:12px}}
.tab{{padding:8px 16px;color:var(--muted);cursor:pointer;font-size:13px;border-bottom:2px solid transparent;transition:all .15s}}
.tab:hover{{color:var(--text)}}
.tab.on{{color:var(--blue);border-bottom-color:var(--blue)}}
.tab-content{{display:none}}
.tab-content.on{{display:block}}
</style>
</head>
<body>
<div class="container">

<header>
  <h1>📊 Clinical Inference Report</h1>
  <div class="subtitle">
    <span>📅 {date_start} → {date_end}</span>
    <span>•</span>
    <span>{meta["days"]:.0f} days · {meta["n_valid_glucose"]:,} readings</span>
    <span>•</span>
    <span>Pipeline v2026.04 · {elapsed:.1f}s</span>
  </div>
</header>

<!-- ── Metric Strip ── -->
<div class="metrics">
  <div class="m-card"><div class="lbl">Time in Range</div><div class="val" style="color:{tir_color(tir)}">{tir:.1f}%</div><div class="sub">70–180 mg/dL</div></div>
  <div class="m-card"><div class="lbl">Below Range</div><div class="val" style="color:{"var(--green)" if tbr_70<4 else "var(--red)"}">{tbr_70:.1f}%</div><div class="sub">&lt;70 mg/dL</div></div>
  <div class="m-card"><div class="lbl">Above Range</div><div class="val" style="color:{"var(--green)" if tar_180<25 else "var(--yellow)" if tar_180<40 else "var(--red)"}">{tar_180:.1f}%</div><div class="sub">&gt;180 mg/dL</div></div>
  <div class="m-card"><div class="lbl">Mean Glucose</div><div class="val" style="color:var(--blue)">{mean_bg:.0f}</div><div class="sub">mg/dL</div></div>
  <div class="m-card"><div class="lbl">GMI</div><div class="val" style="color:var(--purple)">{gmi:.1f}%</div><div class="sub">est. A1c</div></div>
  <div class="m-card"><div class="lbl">CV</div><div class="val" style="color:var(--cyan)">{cv:.1f}%</div><div class="sub">{"Stable" if cv<36 else "Unstable"}</div></div>
  <div class="m-card"><div class="lbl">ADA Grade</div><div class="val"><span class="grade {grade_cls(ada)}">{ada}</span></div><div class="sub"></div></div>
  <div class="m-card"><div class="lbl">Fidelity</div><div class="val" style="font-size:18px;color:{"var(--green)" if fid_grade in ("excellent","good") else "var(--yellow)" if fid_grade=="acceptable" else "var(--red)"}">{fid_grade}</div><div class="sub">RMSE {fid_rmse}</div></div>
</div>

<!-- ── Glucose Trace ── -->
<div class="panel">
  <h2><span class="ico">📈</span>Glucose Trace</h2>
  <div class="range-bar">
    <button class="rbtn on" onclick="setRange('all',this)">All</button>
    <button class="rbtn" onclick="setRange(30,this)">30d</button>
    <button class="rbtn" onclick="setRange(14,this)">14d</button>
    <button class="rbtn" onclick="setRange(7,this)">7d</button>
    <button class="rbtn" onclick="setRange(3,this)">3d</button>
    <button class="rbtn" onclick="setRange(1,this)">24h</button>
  </div>
  <div class="chart-wrap h400"><canvas id="cGlucose"></canvas></div>
</div>

<!-- ── TIR + AGP row ── -->
<div class="g2">
  <div class="panel">
    <h2><span class="ico">🎯</span>Time in Range</h2>
    <div class="tir-layout">
      <div class="tir-ring"><canvas id="cTIR"></canvas><div class="tir-ctr"><div class="big">{tir:.0f}%</div><div class="tiny">IN RANGE</div></div></div>
      <div class="tir-rows">
        <div class="tir-row"><span style="color:var(--red)">Very Low &lt;54</span><div><div class="tir-bar" style="width:{max(tbr_54*1.5,1):.1f}%;background:var(--red)"></div></div><span class="pv">{tbr_54:.1f}%</span></div>
        <div class="tir-row"><span style="color:var(--orange)">Low &lt;70</span><div><div class="tir-bar" style="width:{max(tbr_70*1.5,1):.1f}%;background:var(--orange)"></div></div><span class="pv">{tbr_70:.1f}%</span></div>
        <div class="tir-row"><span style="color:var(--green)">In Range</span><div><div class="tir-bar" style="width:{max(tir,1):.1f}%;background:var(--green)"></div></div><span class="pv">{tir:.1f}%</span></div>
        <div class="tir-row"><span style="color:var(--yellow)">High &gt;180</span><div><div class="tir-bar" style="width:{max(tar_180*1.5,1):.1f}%;background:var(--yellow)"></div></div><span class="pv">{tar_180:.1f}%</span></div>
        <div class="tir-row"><span style="color:var(--red)">Very High &gt;250</span><div><div class="tir-bar" style="width:{max(tar_250*1.5,1):.1f}%;background:var(--red)"></div></div><span class="pv">{tar_250:.1f}%</span></div>
      </div>
    </div>
  </div>

  <div class="panel">
    <h2><span class="ico">🕐</span>Ambulatory Glucose Profile</h2>
    <div class="chart-wrap h300"><canvas id="cAGP"></canvas></div>
  </div>
</div>

<!-- ── IOB/COB + Metabolic Flux ── -->
<div class="g2">
  <div class="panel">
    <h2><span class="ico">💉</span>IOB & COB</h2>
    <div class="chart-wrap h250"><canvas id="cIOB"></canvas></div>
  </div>
  <div class="panel">
    <h2><span class="ico">⚡</span>Net Metabolic Flux</h2>
    <div class="chart-wrap h250"><canvas id="cFlux"></canvas></div>
  </div>
</div>

<!-- ── Analysis Tabs ── -->
<div class="panel">
  <div class="tabs">
    <div class="tab on" onclick="showTab('settings',this)">⚙️ Settings</div>
    <div class="tab" onclick="showTab('circadian',this)">🌙 Circadian</div>
    <div class="tab" onclick="showTab('meals',this)">🍽️ Meals</div>
    <div class="tab" onclick="showTab('fidelity',this)">🔬 Fidelity</div>
  </div>

  <div id="tab-settings" class="tab-content on">
    <div class="g2">
      <div>
        <h3 style="font-size:13px;color:var(--muted);margin-bottom:8px">Profile vs Effective</h3>
        <div class="info-grid">
          <div class="info-row"><span class="k">Profile ISF</span><span class="v">{profile_isf} mg/dL</span></div>
          <div class="info-row"><span class="k">Effective ISF</span><span class="v">{eff_isf} mg/dL</span></div>
          <div class="info-row"><span class="k">ISF Discrepancy</span><span class="v">{isf_disc}×</span></div>
          <div class="info-row"><span class="k">Profile CR</span><span class="v">{profile_cr}</span></div>
          <div class="info-row"><span class="k">DIA</span><span class="v">{dia}h</span></div>
          <div class="info-row"><span class="k">Units</span><span class="v">{meta.get("units","mg/dL")}</span></div>
        </div>
      </div>
      <div id="recsBox"></div>
    </div>
  </div>

  <div id="tab-circadian" class="tab-content">
    <div class="g2">
      <div class="chart-wrap h250"><canvas id="cCircadian"></canvas></div>
      <div>
        <h3 style="font-size:13px;color:var(--muted);margin-bottom:8px">Circadian Fit</h3>
        <div class="info-grid">
          <div class="info-row"><span class="k">4-Harmonic R²</span><span class="v">{harm_r2}</span></div>
          <div class="info-row"><span class="k">Sinusoidal R²</span><span class="v">{sin_r2}</span></div>
          <div class="info-row"><span class="k">Dominant Period</span><span class="v">{pa.harmonic.dominant_period:.0f}h</span></div>
          <div class="info-row"><span class="k">Dominant Amplitude</span><span class="v">{pa.harmonic.dominant_amplitude:.1f} mg/dL</span></div>
        </div>
        <div style="margin-top:12px">
          <h3 style="font-size:13px;color:var(--muted);margin-bottom:8px">Residual by Hour</h3>
          <div class="chart-wrap" style="height:120px"><canvas id="cResidual"></canvas></div>
        </div>
      </div>
    </div>
  </div>

  <div id="tab-meals" class="tab-content">
    <div class="g2">
      <div>
        <div class="info-grid">
          <div class="info-row"><span class="k">Total Meals</span><span class="v">{n_meals}</span></div>
          <div class="info-row"><span class="k">Meals/Day</span><span class="v">{n_meals/max(meta["days"],1):.1f}</span></div>
          <div class="info-row"><span class="k">Announced</span><span class="v">{mh.announced_count if mh else 0}</span></div>
          <div class="info-row"><span class="k">UAM %</span><span class="v">{uam_pct}%</span></div>
        </div>
        <div style="margin-top:12px" id="archetypeBox"></div>
      </div>
      <div class="chart-wrap h250"><canvas id="cMealHist"></canvas></div>
    </div>
  </div>

  <div id="tab-fidelity" class="tab-content">
    <div class="g2">
      <div>
        <div class="info-grid">
          <div class="info-row"><span class="k">Fidelity Grade</span><span class="v">{fid_grade}</span></div>
          <div class="info-row"><span class="k">RMSE</span><span class="v">{fid_rmse}</span></div>
          <div class="info-row"><span class="k">Correction Energy</span><span class="v">{fid_ce}</span></div>
          <div class="info-row"><span class="k">R²</span><span class="v">{f"{fid.r2:.3f}" if fid and fid.r2 is not None else "—"}</span></div>
          <div class="info-row"><span class="k">ADA/Fidelity Match</span><span class="v">{"✅ Yes" if fid and fid.concordance else "⚠️ No"}</span></div>
        </div>
        <p style="color:var(--muted);font-size:12px;margin-top:12px;line-height:1.6">
          Fidelity measures how well the physics model (supply–demand) predicts observed glucose changes.
          High fidelity indicates well-tuned settings. Low concordance with ADA grade means the patient
          achieves outcomes through AID loop compensation rather than accurate basal settings.
        </p>
      </div>
      <div>
        <div class="chart-wrap h250"><canvas id="cFidelity"></canvas></div>
      </div>
    </div>
  </div>
</div>

<!-- ── Daily Breakdown ── -->
<div class="panel">
  <h2><span class="ico">📅</span>Daily Breakdown</h2>
  <div class="scroll-y"><table class="dt">
    <thead><tr><th>Date</th><th>Mean</th><th>SD</th><th>Min</th><th>Max</th><th>TIR</th><th>Below</th><th>Above</th><th>N</th></tr></thead>
    <tbody id="dailyTbody"></tbody>
  </table></div>
</div>

<footer>
  <p>Generated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} · Production Inference Pipeline</p>
  <p style="margin-top:6px">This report is for informational purposes only and is not medical advice.<br>Always consult with your healthcare provider before making changes to diabetes management.</p>
</footer>
</div>

<script>
// ══════════════════════════════════════════════════════════
// Data
// ══════════════════════════════════════════════════════════
const S = {json.dumps(sgv_chart)};
const IOB = {json.dumps(iob_chart)};
const COB = {json.dumps(cob_chart)};
const FLX = {json.dumps(flux_chart)};
const D = {json.dumps(daily_stats)};
const AGP = {json.dumps(agp)};
const HARM = {json.dumps(harm_curve)};
const RESID = {json.dumps(residual_hourly)};
const TREATS = {json.dumps(treat_chart)};
const RECS = {json.dumps(recs_data)};
const ARCH = {json.dumps(archetype_summary)};

// ══════════════════════════════════════════════════════════
// Chart defaults
// ══════════════════════════════════════════════════════════
Chart.defaults.color = '#8b949e';
Chart.defaults.borderColor = '#30363d';
Chart.defaults.font.family = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif";
Chart.defaults.font.size = 11;
const gridOpt = {{color:'rgba(255,255,255,.04)'}};

// ══════════════════════════════════════════════════════════
// Glucose chart
// ══════════════════════════════════════════════════════════
const gCtx = document.getElementById('cGlucose');
const gColors = S.map(d => d[1]<54?'#f85149':d[1]<70?'#db6d28':d[1]<=180?'#3fb950':d[1]<=250?'#d29922':'#f85149');

const gChart = new Chart(gCtx, {{
  type:'scatter',
  data:{{
    datasets:[
      {{data:S.map(d=>({{x:d[0],y:d[1]}})),pointRadius:1.3,pointBackgroundColor:gColors,pointBorderColor:gColors,showLine:false,label:'Glucose'}},
      {{data:[{{x:S[0][0],y:180}},{{x:S[S.length-1][0],y:180}}],borderColor:'rgba(210,153,34,.25)',borderDash:[5,5],borderWidth:1,pointRadius:0,showLine:true,fill:false,label:'180'}},
      {{data:[{{x:S[0][0],y:70}},{{x:S[S.length-1][0],y:70}}],borderColor:'rgba(248,81,73,.25)',borderDash:[5,5],borderWidth:1,pointRadius:0,showLine:true,fill:false,label:'70'}},
    ]
  }},
  options:{{
    responsive:true,maintainAspectRatio:false,animation:{{duration:0}},
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{title:i=>new Date(i[0].parsed.x).toLocaleString(),label:i=>i.parsed.y+' mg/dL'}}}}}},
    scales:{{
      x:{{type:'time',time:{{unit:'day',displayFormats:{{day:'MMM d'}}}},grid:gridOpt}},
      y:{{min:40,max:400,grid:gridOpt,title:{{display:true,text:'mg/dL'}}}}
    }}
  }}
}});

function setRange(days,btn){{
  document.querySelectorAll('.rbtn').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  if(days==='all'){{gChart.options.scales.x.min=undefined;gChart.options.scales.x.max=undefined;}}
  else{{const mx=S[S.length-1][0];gChart.options.scales.x.min=mx-days*864e5;gChart.options.scales.x.max=mx;}}
  gChart.update('none');
}}

// ══════════════════════════════════════════════════════════
// TIR donut
// ══════════════════════════════════════════════════════════
new Chart(document.getElementById('cTIR'),{{
  type:'doughnut',
  data:{{
    labels:['In Range','High','Very High','Low','Very Low'],
    datasets:[{{data:[{tir:.2f},{tar_180-tar_250:.2f},{tar_250:.2f},{tbr_70-tbr_54:.2f},{tbr_54:.2f}].map(v=>Math.max(v,.3)),
      backgroundColor:['#3fb950','#d29922','#f85149','#db6d28','#da3633'],borderWidth:0}}]
  }},
  options:{{responsive:false,cutout:'74%',plugins:{{legend:{{display:false}}}},animation:{{animateRotate:true,duration:800}}}}
}});

// ══════════════════════════════════════════════════════════
// AGP
// ══════════════════════════════════════════════════════════
const hrs=Array.from({{length:24}},(_,i)=>i+':00');
new Chart(document.getElementById('cAGP'),{{
  type:'line',
  data:{{
    labels:hrs,
    datasets:[
      {{label:'90th',data:AGP.p90,borderColor:'transparent',backgroundColor:'rgba(210,153,34,.08)',fill:'+1',pointRadius:0,tension:.4}},
      {{label:'75th',data:AGP.p75,borderColor:'transparent',backgroundColor:'rgba(210,153,34,.12)',fill:'+1',pointRadius:0,tension:.4}},
      {{label:'Median',data:AGP.p50,borderColor:'#58a6ff',borderWidth:2.5,fill:false,pointRadius:2,pointBackgroundColor:'#58a6ff',tension:.4}},
      {{label:'25th',data:AGP.p25,borderColor:'transparent',backgroundColor:'rgba(210,153,34,.12)',fill:'-1',pointRadius:0,tension:.4}},
      {{label:'10th',data:AGP.p10,borderColor:'transparent',backgroundColor:'rgba(210,153,34,.08)',fill:'-1',pointRadius:0,tension:.4}},
    ]
  }},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:i=>i.dataset.label+': '+Math.round(i.parsed.y)+' mg/dL'}}}}}},
    scales:{{x:{{grid:gridOpt}},y:{{min:40,max:350,grid:gridOpt,title:{{display:true,text:'mg/dL'}}}}}}
  }}
}});

// ══════════════════════════════════════════════════════════
// IOB/COB
// ══════════════════════════════════════════════════════════
new Chart(document.getElementById('cIOB'),{{
  type:'line',
  data:{{
    datasets:[
      {{label:'IOB (U)',data:IOB.map(d=>({{x:d[0],y:d[1]}})),borderColor:'#bc8cff',backgroundColor:'rgba(188,140,255,.08)',borderWidth:1,pointRadius:0,fill:true,yAxisID:'y',tension:.2}},
      {{label:'COB (g)',data:COB.map(d=>({{x:d[0],y:d[1]}})),borderColor:'#db6d28',backgroundColor:'rgba(219,109,40,.08)',borderWidth:1,pointRadius:0,fill:true,yAxisID:'y2',tension:.2}},
    ]
  }},
  options:{{responsive:true,maintainAspectRatio:false,animation:{{duration:0}},
    plugins:{{legend:{{position:'top',labels:{{boxWidth:10,font:{{size:11}}}}}},tooltip:{{callbacks:{{title:i=>new Date(i[0].parsed.x).toLocaleString()}}}}}},
    scales:{{
      x:{{type:'time',time:{{unit:'week'}},grid:gridOpt}},
      y:{{position:'left',title:{{display:true,text:'IOB (U)'}},grid:gridOpt}},
      y2:{{position:'right',title:{{display:true,text:'COB (g)'}},grid:{{display:false}}}}
    }}
  }}
}});

// ══════════════════════════════════════════════════════════
// Net Flux
// ══════════════════════════════════════════════════════════
const fluxColors = FLX.map(d=>d[1]>0?'rgba(63,185,80,.5)':'rgba(248,81,73,.5)');
new Chart(document.getElementById('cFlux'),{{
  type:'bar',
  data:{{datasets:[{{label:'Net Flux',data:FLX.map(d=>({{x:d[0],y:d[1]}})),backgroundColor:fluxColors,borderWidth:0,barPercentage:1,categoryPercentage:1}}]}},
  options:{{responsive:true,maintainAspectRatio:false,animation:{{duration:0}},
    plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{title:i=>new Date(i[0].parsed.x).toLocaleString(),label:i=>i.parsed.y.toFixed(1)+' mg/dL/5min'}}}}}},
    scales:{{
      x:{{type:'time',time:{{unit:'week'}},grid:gridOpt}},
      y:{{grid:gridOpt,title:{{display:true,text:'mg/dL per 5min'}}}}
    }}
  }}
}});

// ══════════════════════════════════════════════════════════
// Circadian overlay
// ══════════════════════════════════════════════════════════
new Chart(document.getElementById('cCircadian'),{{
  type:'line',
  data:{{
    labels:hrs,
    datasets:[
      {{label:'Actual (median)',data:AGP.p50,borderColor:'#58a6ff',borderWidth:2,pointRadius:2,pointBackgroundColor:'#58a6ff',tension:.4,fill:false}},
      {{label:'4-Harmonic fit',data:HARM,borderColor:'#3fb950',borderWidth:2,borderDash:[4,4],pointRadius:0,tension:.4,fill:false}},
    ]
  }},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'top',labels:{{boxWidth:10}}}}}},
    scales:{{x:{{grid:gridOpt}},y:{{grid:gridOpt,title:{{display:true,text:'mg/dL'}}}}}}
  }}
}});

// ══════════════════════════════════════════════════════════
// Residual by hour
// ══════════════════════════════════════════════════════════
new Chart(document.getElementById('cResidual'),{{
  type:'bar',
  data:{{labels:hrs,datasets:[{{data:RESID,backgroundColor:'rgba(188,140,255,.4)',borderRadius:2}}]}},
  options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}},
    scales:{{x:{{grid:{{display:false}}}},y:{{grid:gridOpt,title:{{display:true,text:'|residual|'}}}}}}
  }}
}});

// ══════════════════════════════════════════════════════════
// Meal histogram (by hour)
// ══════════════════════════════════════════════════════════
const mealByHour = Array(24).fill(0);
{f"/* meal histogram populated from pipeline */" if not mh else ""}
const mealHist = {json.dumps([sum(1 for m in mh.meals if m.hour_of_day == h) for h in range(24)] if mh and mh.meals else [0]*24)};
new Chart(document.getElementById('cMealHist'),{{
  type:'bar',
  data:{{labels:hrs,datasets:[{{label:'Meals detected',data:mealHist,backgroundColor:'rgba(219,109,40,.5)',borderRadius:3}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}}}},
    scales:{{x:{{grid:{{display:false}}}},y:{{grid:gridOpt,title:{{display:true,text:'Count'}}}}}}
  }}
}});

// ══════════════════════════════════════════════════════════
// Fidelity chart — RMSE distribution
// ══════════════════════════════════════════════════════════
const fidHourly = RESID.map((v,i) => v);
new Chart(document.getElementById('cFidelity'),{{
  type:'line',
  data:{{
    labels:hrs,
    datasets:[
      {{label:'Mean |Residual|',data:fidHourly,borderColor:'#f85149',backgroundColor:'rgba(248,81,73,.1)',borderWidth:2,pointRadius:2,fill:true,tension:.3}},
    ]
  }},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'top',labels:{{boxWidth:10}}}}}},
    scales:{{x:{{grid:gridOpt}},y:{{grid:gridOpt,title:{{display:true,text:'mg/dL'}}}}}}
  }}
}});

// ══════════════════════════════════════════════════════════
// Tab navigation
// ══════════════════════════════════════════════════════════
function showTab(name,el){{
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('on'));
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('on'));
  el.classList.add('on');
  document.getElementById('tab-'+name).classList.add('on');
}}

// ══════════════════════════════════════════════════════════
// Daily table
// ══════════════════════════════════════════════════════════
const tb=document.getElementById('dailyTbody');
D.forEach(d=>{{
  const tc=d.tir>=70?'#3fb950':d.tir>=50?'#d29922':'#f85149';
  const tr=document.createElement('tr');
  tr.innerHTML=`<td>${{d.d}}</td><td>${{d.mean}}</td><td>${{d.sd}}</td><td>${{d.lo}}</td><td>${{d.hi}}</td><td style="color:${{tc}};font-weight:600">${{d.tir}}%</td><td style="color:${{d.tbr>4?'#f85149':'#8b949e'}}">${{d.tbr}}%</td><td style="color:${{d.tar>40?'#f85149':d.tar>25?'#d29922':'#8b949e'}}">${{d.tar}}%</td><td>${{d.n}}</td>`;
  tb.appendChild(tr);
}});

// ══════════════════════════════════════════════════════════
// Recommendations
// ══════════════════════════════════════════════════════════
const rb=document.getElementById('recsBox');
if(RECS.length===0){{
  rb.innerHTML='<div class="rec ok">✅ No actionable recommendations at this time.</div>';
}} else {{
  RECS.forEach(r=>{{
    const div=document.createElement('div');
    div.className='rec';
    div.innerHTML=`<b>${{r.param}}</b>: ${{r.dir}} (current: ${{r.current}} → suggested: ${{r.suggested}})<div class="detail">${{r.rationale}}</div>`;
    rb.appendChild(div);
  }});
}}

// Archetypes
const ab=document.getElementById('archetypeBox');
if(Object.keys(ARCH).length>0){{
  let html='<h3 style="font-size:13px;color:#8b949e;margin-bottom:8px">Meal Archetypes</h3><div class="info-grid">';
  for(const[k,v] of Object.entries(ARCH)){{
    html+=`<div class="info-row"><span class="k">${{k}}</span><span class="v">${{v.count}} meals (~${{v.mean_carbs}}g)</span></div>`;
  }}
  html+='</div>';
  ab.innerHTML=html;
}}
</script>
</body>
</html>'''

with open(OUTPUT, 'w') as f:
    f.write(html)

size_kb = os.path.getsize(OUTPUT) / 1024
print(f"  Output: {OUTPUT}")
print(f"  Size: {size_kb:.0f} KB")
print(f"\n✅ Done!")
