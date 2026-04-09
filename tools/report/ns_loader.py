#!/usr/bin/env python3
"""Load Nightscout JSON exports into pipeline-ready PatientData.

Handles entries, treatments, devicestatus (IOB/COB), and profile.
Supports both live-recent directories and patient training directories.

Usage:
    from report.ns_loader import load_from_dir
    patient, meta = load_from_dir('externals/ns-data/live-recent')
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cgmencode.production.types import PatientData, PatientProfile


def _try_files(directory, *names):
    """Return first existing file path from candidates."""
    d = Path(directory)
    for n in names:
        p = d / n
        if p.exists():
            return p
    return None


def _parse_ts(ts):
    """Parse a timestamp string or number to epoch ms."""
    if isinstance(ts, (int, float)):
        return float(ts) if ts > 1e12 else float(ts) * 1000
    if isinstance(ts, str):
        try:
            return pd.Timestamp(ts).timestamp() * 1000
        except Exception:
            return None
    return None


def load_from_dir(directory, patient_id=None, verbose=True):
    """Load Nightscout data from a directory of JSON files.

    Looks for entries*.json, treatments*.json, devicestatus*.json, profile*.json.
    Prefers *-fresh.json variants if present.

    Returns:
        (PatientData, metadata_dict) or (None, metadata_dict) on failure.
    """
    d = Path(directory)
    pid = patient_id or d.name
    meta = {'source_dir': str(d), 'patient_id': pid}

    # ── Find files (prefer fresh) ────────────────────────────────────
    entries_path = _try_files(d, 'entries-fresh.json', 'entries.json')
    treat_path = _try_files(d, 'treatments-fresh.json', 'treatments.json')
    ds_path = _try_files(d, 'devicestatus-fresh.json', 'devicestatus.json')
    profile_path = _try_files(d, 'profile-fresh.json', 'profile.json')

    if not entries_path:
        if verbose:
            print(f"  ERROR: No entries file in {d}")
        return None, meta

    if verbose:
        print(f"  Loading from {d}")
        print(f"    entries:      {entries_path.name}")
        print(f"    treatments:   {treat_path.name if treat_path else 'MISSING'}")
        print(f"    devicestatus: {ds_path.name if ds_path else 'MISSING'}")
        print(f"    profile:      {profile_path.name if profile_path else 'MISSING'}")

    # ── Load entries → SGV records ───────────────────────────────────
    with open(entries_path) as f:
        entries = json.load(f)

    sgv_records = []
    for e in entries:
        if e.get('type') != 'sgv':
            continue
        ts = e.get('date')
        if ts is None:
            ts = _parse_ts(e.get('dateString'))
        else:
            ts = float(ts)
        sgv = e.get('sgv')
        if ts is None or sgv is None:
            continue
        sgv_records.append((ts, float(sgv), e.get('direction', '')))

    if not sgv_records:
        if verbose:
            print("  ERROR: No SGV records found")
        return None, meta

    sgv_records.sort(key=lambda x: x[0])
    meta['n_entries'] = len(sgv_records)
    meta['date_min'] = sgv_records[0][0]
    meta['date_max'] = sgv_records[-1][0]
    meta['days'] = (meta['date_max'] - meta['date_min']) / 86400000

    if verbose:
        print(f"    SGV: {len(sgv_records)} records, "
              f"{datetime.fromtimestamp(meta['date_min']/1000, tz=timezone.utc).strftime('%Y-%m-%d')} → "
              f"{datetime.fromtimestamp(meta['date_max']/1000, tz=timezone.utc).strftime('%Y-%m-%d')} "
              f"({meta['days']:.0f} days)")

    # ── Build 5-min grid ─────────────────────────────────────────────
    ts_min = sgv_records[0][0]
    ts_max = sgv_records[-1][0]
    grid_ts = np.arange(ts_min, ts_max + 300_000, 300_000, dtype=np.float64)
    N = len(grid_ts)

    glucose = np.full(N, np.nan)
    for ts, sgv, _ in sgv_records:
        idx = int((ts - ts_min) / 300_000)
        if 0 <= idx < N:
            glucose[idx] = sgv

    # Interpolate short gaps (≤30 min = 6 steps)
    valid_count = np.sum(~np.isnan(glucose))
    if valid_count > 10:
        glucose = pd.Series(glucose).interpolate(
            method='linear', limit=6
        ).to_numpy()

    meta['n_grid'] = N
    meta['n_valid_glucose'] = int(np.sum(~np.isnan(glucose)))

    # ── Load treatments → bolus, carbs ───────────────────────────────
    bolus = np.zeros(N)
    carbs = np.zeros(N)

    if treat_path:
        with open(treat_path) as f:
            treatments = json.load(f)
        meta['n_treatments'] = len(treatments)

        for t in treatments:
            ts = _parse_ts(t.get('created_at') or t.get('timestamp'))
            if ts is None:
                continue
            idx = int((ts - ts_min) / 300_000)
            if not (0 <= idx < N):
                continue

            evt = t.get('eventType', '')
            if 'Bolus' in evt or t.get('insulin'):
                ins = t.get('insulin')
                if ins and float(ins) > 0:
                    bolus[idx] += float(ins)
            if t.get('carbs'):
                carbs[idx] += float(t['carbs'])

    # ── Load devicestatus → IOB, COB ────────────────────────────────
    iob = np.full(N, np.nan)
    cob = np.full(N, np.nan)
    ds_count = 0

    if ds_path:
        with open(ds_path) as f:
            devicestatus = json.load(f)
        meta['n_devicestatus'] = len(devicestatus)

        for d in devicestatus:
            loop = d.get('loop')
            if not isinstance(loop, dict):
                continue

            # Get timestamp
            ts = _parse_ts(loop.get('timestamp') or d.get('created_at'))
            if ts is None:
                continue
            idx = int((ts - ts_min) / 300_000)
            if not (0 <= idx < N):
                continue

            # IOB
            iob_obj = loop.get('iob')
            if isinstance(iob_obj, dict) and 'iob' in iob_obj:
                val = iob_obj['iob']
                if val is not None:
                    iob[idx] = float(val)
                    ds_count += 1

            # COB
            cob_obj = loop.get('cob')
            if isinstance(cob_obj, dict) and 'cob' in cob_obj:
                val = cob_obj['cob']
                if val is not None:
                    cob[idx] = float(val)

    # Forward-fill IOB/COB (Loop reports every 5 min but may skip)
    if np.any(~np.isnan(iob)):
        iob = pd.Series(iob).ffill(limit=3).to_numpy()
    else:
        iob = None

    if np.any(~np.isnan(cob)):
        cob = pd.Series(cob).ffill(limit=3).to_numpy()
    else:
        cob = None

    meta['n_iob_mapped'] = ds_count
    has_insulin = iob is not None and not np.all(np.isnan(iob))

    if verbose:
        print(f"    Grid: {N} steps, {meta['n_valid_glucose']} valid glucose")
        print(f"    IOB: {'✓ ' + str(ds_count) + ' mapped' if has_insulin else '✗ none'}")
        print(f"    Bolus events: {int(np.sum(bolus > 0))}, Carb events: {int(np.sum(carbs > 0))}")

    # ── Load profile ─────────────────────────────────────────────────
    isf_schedule = [{'time': '00:00', 'value': 50}]
    cr_schedule = [{'time': '00:00', 'value': 10}]
    basal_schedule = [{'time': '00:00', 'value': 0.8}]
    units = 'mg/dL'
    dia = 5.0

    if profile_path:
        with open(profile_path) as f:
            profiles = json.load(f)
        if profiles:
            prof = profiles[0] if isinstance(profiles, list) else profiles
            store = prof.get('store', {})
            active_name = prof.get('defaultProfile', '')
            if not active_name and store:
                active_name = list(store.keys())[0]
            active = store.get(active_name, {})

            sens = active.get('sens', active.get('sensitivity', []))
            if isinstance(sens, list) and sens:
                isf_schedule = [
                    {'time': s.get('time', '00:00'),
                     'value': s.get('value', s.get('sensitivity', 50))}
                    for s in sens
                ]

            cr_list = active.get('carbratio', [])
            if isinstance(cr_list, list) and cr_list:
                cr_schedule = [
                    {'time': c.get('time', '00:00'),
                     'value': c.get('value', c.get('carbratio', 10))}
                    for c in cr_list
                ]

            basal_list = active.get('basal', [])
            if isinstance(basal_list, list) and basal_list:
                basal_schedule = [
                    {'time': b.get('time', '00:00'),
                     'value': b.get('value', b.get('rate', 0.8))}
                    for b in basal_list
                ]

            units = active.get('units', prof.get('units', 'mg/dL'))
            dia = float(active.get('dia', prof.get('dia', 5.0)))

    profile = PatientProfile(
        isf_schedule=isf_schedule,
        cr_schedule=cr_schedule,
        basal_schedule=basal_schedule,
        dia_hours=dia,
        units=units,
    )
    meta['units'] = units
    meta['profile_isf'] = [s['value'] for s in isf_schedule]
    meta['profile_cr'] = [c['value'] for c in cr_schedule]
    meta['dia'] = dia

    if verbose:
        print(f"    Profile: ISF={meta['profile_isf']} {units}, "
              f"CR={meta['profile_cr']}, DIA={dia}h")

    # ── Build PatientData ────────────────────────────────────────────
    kwargs = dict(
        glucose=glucose,
        timestamps=grid_ts,
        profile=profile,
        patient_id=pid,
        bolus=bolus,
        carbs=carbs,
    )
    if iob is not None:
        kwargs['iob'] = iob
    if cob is not None:
        kwargs['cob'] = cob

    patient = PatientData(**kwargs)
    meta['has_insulin'] = patient.has_insulin_data

    if verbose:
        print(f"    Pipeline ready: has_insulin={patient.has_insulin_data}, "
              f"days={patient.days_of_data:.1f}")

    return patient, meta
