"""
odc_loader.py — OpenAPS Data Commons format adapter.

Translates OpenAPS Data Commons (ODC) AAPS-native JSON into
Nightscout-shaped dicts so the existing build_grid() pipeline works.

ODC Structure:
  patient_id/
    direct-sharing-NNN/
      upload-numN-ver1-dateYYYYMMDDTHHMMSS-appidUUID/
        BgReadings.json      → entries
        Treatments.json      → treatments (bolus/carb)
        TemporaryBasals.json → treatments (temp basal)
        TempTargets.json     → treatments (temp target)
        APSData.json         → devicestatus
        ProfileSwitches.json → profile
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MMOLL_TO_MGDL = 18.01559


# ── Discovery ────────────────────────────────────────────────────────────

def discover_odc_patients(odc_root: str) -> List[Tuple[str, str]]:
    """Discover patient directories in an ODC dataset.

    Returns list of (patient_id, patient_path) tuples.
    """
    root = Path(odc_root)
    patients = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and d.name.isdigit():
            patients.append((d.name, str(d)))
    return patients


def _discover_uploads(patient_dir: str) -> List[Path]:
    """Find all upload directories within a patient dir, sorted by date."""
    uploads = []
    for root, dirs, files in os.walk(patient_dir):
        # Upload dirs contain data JSON files
        if any(f in files for f in ('BgReadings.json', 'Treatments.json', 'APSData.json')):
            uploads.append(Path(root))
    return sorted(uploads)


# ── File loaders with deduplication ──────────────────────────────────────

def _load_and_merge_json(uploads: List[Path], filename: str) -> List[dict]:
    """Load a JSON file from all uploads and deduplicate by 'date' field."""
    seen = set()
    merged = []
    for upload_dir in uploads:
        fp = upload_dir / filename
        if not fp.exists():
            continue
        try:
            with open(fp) as f:
                records = json.load(f)
        except (json.JSONDecodeError, IOError):
            logger.warning('Failed to read %s', fp)
            continue
        for r in records:
            if not isinstance(r, dict):
                continue
            # Skip deletions and invalid records
            if r.get('isDeletion'):
                continue
            if r.get('isValid') is False:
                continue
            # Deduplicate by date (epoch ms)
            date_key = r.get('date')
            if date_key is not None and date_key in seen:
                continue
            if date_key is not None:
                seen.add(date_key)
            merged.append(r)
    return merged


# ── Format adapters ──────────────────────────────────────────────────────

def _convert_bg_readings(records: List[dict]) -> List[dict]:
    """Convert ODC BgReadings → Nightscout entries format."""
    entries = []
    for r in records:
        date_ms = r.get('date')
        value = r.get('value')
        if date_ms is None or value is None:
            continue
        entries.append({
            '_id': r.get('nsId', f'odc-{date_ms}'),
            'type': 'sgv',
            'date': int(date_ms),
            'sgv': float(value),
            'direction': r.get('direction', ''),
            'device': 'openaps://AndroidAPS',
            'noise': 0,
        })
    return entries


def _convert_treatments(records: List[dict]) -> List[dict]:
    """Convert ODC Treatments → Nightscout treatments format."""
    treatments = []
    for r in records:
        date_ms = r.get('date')
        if date_ms is None:
            continue

        insulin = float(r.get('insulin') or 0)
        carbs = float(r.get('carbs') or 0)
        is_smb = bool(r.get('isSMB'))
        is_meal = bool(r.get('mealBolus'))

        # Synthesize eventType from AAPS flags
        if is_smb and insulin > 0:
            event_type = 'SMB'
        elif is_meal and carbs > 0:
            event_type = 'Meal Bolus'
        elif insulin > 0 and carbs > 0:
            event_type = 'Meal Bolus'
        elif insulin > 0:
            event_type = 'Correction Bolus'
        elif carbs > 0:
            event_type = 'Carb Correction'
        else:
            continue  # Skip empty records

        tx = {
            'eventType': event_type,
            'created_at': _epoch_to_iso(date_ms),
            'insulin': insulin if insulin > 0 else None,
            'carbs': carbs if carbs > 0 else None,
            'enteredBy': 'openaps://AndroidAPS',
            'device': 'openaps://AndroidAPS',
        }
        if is_smb:
            tx['automatic'] = True
            tx['type'] = 'SMB'

        treatments.append(tx)
    return treatments


def _convert_temp_basals(records: List[dict]) -> List[dict]:
    """Convert ODC TemporaryBasals → Nightscout Temp Basal treatments."""
    treatments = []
    for r in records:
        date_ms = r.get('date')
        if date_ms is None:
            continue
        rate = r.get('absoluteRate') if r.get('isAbsolute') else r.get('percentRate')
        if rate is None:
            continue
        treatments.append({
            'eventType': 'Temp Basal',
            'created_at': _epoch_to_iso(date_ms),
            'rate': float(rate),
            'duration': float(r.get('durationInMinutes', 0)),
            'device': 'openaps://AndroidAPS',
        })
    return treatments


def _convert_temp_targets(records: List[dict]) -> List[dict]:
    """Convert ODC TempTargets → Nightscout Temporary Target treatments."""
    treatments = []
    for r in records:
        date_ms = r.get('date')
        if date_ms is None:
            continue
        treatments.append({
            'eventType': 'Temporary Target',
            'created_at': _epoch_to_iso(date_ms),
            'targetBottom': float(r.get('low', 0)),
            'targetTop': float(r.get('high', 0)),
            'duration': float(r.get('durationInMinutes', 0)),
            'reason': r.get('reason', ''),
            'device': 'openaps://AndroidAPS',
        })
    return treatments


def _convert_careportal(records: List[dict]) -> List[dict]:
    """Convert ODC CareportalEvents → Nightscout careportal treatments."""
    treatments = []
    for r in records:
        date_ms = r.get('date')
        et = r.get('eventType', '')
        if not date_ms or not et:
            continue
        tx = {
            'eventType': et,
            'created_at': _epoch_to_iso(date_ms),
            'device': 'openaps://AndroidAPS',
        }
        # Extract glucose from nested data object (BG Check)
        data = r.get('data', {})
        if isinstance(data, dict):
            if 'glucose' in data:
                tx['glucose'] = float(data['glucose'])
                tx['glucoseType'] = data.get('glucoseType', '')
        treatments.append(tx)
    return treatments


def _convert_aps_data(records: List[dict]) -> List[dict]:
    """Convert ODC APSData → Nightscout devicestatus format."""
    devicestatus = []
    for r in records:
        queued = r.get('queuedOn')
        if not queued:
            continue

        result = r.get('result', {}) or {}
        gs = r.get('glucoseStatus', {}) or {}
        iob_list = r.get('iobData', []) or []
        iob_data = iob_list[0] if iob_list else {}
        profile = r.get('profile', {}) or {}
        autosens = r.get('autosensData', {}) or {}
        current_temp = r.get('currentTemp', {}) or {}

        # Build openaps.suggested from result
        suggested = {}
        for src_key, dst_key in [
            ('bg', 'bg'), ('eventualBG', 'eventualBG'),
            ('targetBG', 'targetBG'), ('insulinReq', 'insulinReq'),
            ('rate', 'rate'), ('duration', 'duration'),
            ('COB', 'COB'), ('IOB', 'IOB'),
            ('reason', 'reason'), ('units', 'units'),
            ('tick', 'tick'), ('carbsReq', 'carbsReq'),
        ]:
            if src_key in result:
                suggested[dst_key] = result[src_key]

        # sensitivityRatio from result or autosensData
        if 'sensitivityRatio' in result:
            suggested['sensitivityRatio'] = result['sensitivityRatio']
        elif 'ratio' in autosens:
            suggested['sensitivityRatio'] = autosens['ratio']

        # Prediction curves
        if 'predBGs' in result:
            suggested['predBGs'] = result['predBGs']

        # Build openaps.iob from first iobData entry
        iob_obj = {}
        if iob_data:
            for k in ['iob', 'basaliob', 'bolussnooze', 'activity', 'lastBolusTime']:
                if k in iob_data:
                    iob_obj[k] = iob_data[k]

        # Enacted = result (APSData records represent enacted decisions)
        enacted = {}
        if 'rate' in result:
            enacted['rate'] = result['rate']
        if 'duration' in result:
            enacted['duration'] = result['duration']
        if 'units' in result and isinstance(result.get('units'), (int, float)):
            enacted['units'] = result['units']
        enacted['received'] = True  # APSData = what was executed

        ds = {
            'created_at': _epoch_to_iso(queued),
            'device': 'openaps://AndroidAPS',
            'openaps': {
                'suggested': suggested,
                'iob': iob_obj,
                'enacted': enacted,
            },
        }
        devicestatus.append(ds)

    return devicestatus


def _synthesize_profile(aps_records: List[dict],
                        profile_switch_records: List[dict]) -> List[dict]:
    """Synthesize Nightscout profile from APSData profile snapshots.

    APSData embeds per-decision profile as single values (not time-varying).
    ProfileSwitches may contain richer time-of-day schedules.
    """
    # Try ProfileSwitches first (richer data)
    if profile_switch_records:
        for r in profile_switch_records:
            prof = r.get('profile', {})
            if isinstance(prof, dict) and prof:
                # ProfileSwitch may have full schedules
                return [_build_profile_from_switch(prof, r)]

    # Fall back to APSData profile snapshot (single-point schedules)
    if not aps_records:
        return []

    # Use first valid profile snapshot
    for r in aps_records:
        profile = r.get('profile', {})
        if not profile:
            continue

        sens = profile.get('sens', 100)
        cr = profile.get('carb_ratio', 10)
        target = profile.get('target_bg', 100)
        min_bg = profile.get('min_bg', target)
        max_bg = profile.get('max_bg', target)
        basal = profile.get('current_basal', 1.0)
        dia = profile.get('dia', 5.0)

        return [{
            'defaultProfile': 'Default',
            'store': {
                'Default': {
                    'dia': float(dia),
                    'timezone': 'UTC',
                    'units': 'mg/dL',
                    'basal': [{'time': '00:00', 'value': float(basal),
                               'timeAsSeconds': 0}],
                    'sens': [{'time': '00:00', 'value': float(sens),
                              'timeAsSeconds': 0}],
                    'carbratio': [{'time': '00:00', 'value': float(cr),
                                   'timeAsSeconds': 0}],
                    'target_low': [{'time': '00:00', 'value': float(min_bg),
                                    'timeAsSeconds': 0}],
                    'target_high': [{'time': '00:00', 'value': float(max_bg),
                                     'timeAsSeconds': 0}],
                }
            }
        }]
    return []


def _build_profile_from_switch(prof: dict, record: dict) -> dict:
    """Build Nightscout profile from a ProfileSwitch record.

    ProfileSwitch profiles may use mmol/L or mg/dL; we detect via 'units'
    field and always output mg/dL (pipeline standard).
    """
    dia = prof.get('dia', 5.0)
    tz = prof.get('timezone', 'UTC')
    units = str(prof.get('units', 'mg/dL')).lower()
    need_convert = units in ('mmol', 'mmol/l')

    def _extract_schedule(key, default_val, convert=False):
        val = prof.get(key)
        if isinstance(val, list):
            if convert:
                return [{'time': e.get('time', '00:00'),
                         'value': float(e.get('value', default_val)) * MMOLL_TO_MGDL,
                         'timeAsSeconds': e.get('timeAsSeconds', 0)}
                        for e in val]
            return val
        if isinstance(val, (int, float)):
            v = float(val) * MMOLL_TO_MGDL if convert else float(val)
            return [{'time': '00:00', 'value': v, 'timeAsSeconds': 0}]
        return [{'time': '00:00', 'value': float(default_val), 'timeAsSeconds': 0}]

    return {
        'defaultProfile': 'Default',
        'store': {
            'Default': {
                'dia': float(dia),
                'timezone': tz,
                'units': 'mg/dL',
                'basal': _extract_schedule('basal', 1.0, convert=False),
                'sens': _extract_schedule('sens', 100.0, convert=need_convert),
                'carbratio': _extract_schedule('carbratio', 10.0, convert=False),
                'target_low': _extract_schedule('target_low', 100.0, convert=need_convert),
                'target_high': _extract_schedule('target_high', 120.0, convert=need_convert),
            }
        }
    }


# ── Helpers ──────────────────────────────────────────────────────────────

def _epoch_to_iso(epoch_ms) -> str:
    """Convert epoch milliseconds to ISO 8601 UTC string."""
    from datetime import datetime, timezone
    dt = datetime.fromtimestamp(int(epoch_ms) / 1000.0, tz=timezone.utc)
    return dt.isoformat()


# ── Main entry point ─────────────────────────────────────────────────────

def load_odc_patient(patient_dir: str, verbose: bool = False
                     ) -> Optional[Dict[str, list]]:
    """Load an ODC patient directory and return Nightscout-shaped data.

    Args:
        patient_dir: Path to ODC patient directory (e.g., '39819048/')
        verbose: Print progress messages

    Returns:
        Dict with keys: 'entries', 'treatments', 'devicestatus', 'profile'
        Each value is a list of Nightscout-shaped dicts.
        Returns None if insufficient data.
    """
    uploads = _discover_uploads(patient_dir)
    if not uploads:
        if verbose:
            print(f'  SKIP: no uploads found in {patient_dir}')
        return None

    if verbose:
        print(f'  Found {len(uploads)} upload(s) in {patient_dir}')

    # Load and deduplicate across overlapping uploads
    bg_raw = _load_and_merge_json(uploads, 'BgReadings.json')
    tx_raw = _load_and_merge_json(uploads, 'Treatments.json')
    tb_raw = _load_and_merge_json(uploads, 'TemporaryBasals.json')
    tt_raw = _load_and_merge_json(uploads, 'TempTargets.json')
    aps_raw = _load_and_merge_json(uploads, 'APSData.json')
    cp_raw = _load_and_merge_json(uploads, 'CareportalEvents.json')
    ps_raw = _load_and_merge_json(uploads, 'ProfileSwitches.json')

    if verbose:
        print(f'  Loaded: BG={len(bg_raw)} Tx={len(tx_raw)} TB={len(tb_raw)} '
              f'TT={len(tt_raw)} APS={len(aps_raw)} CP={len(cp_raw)} PS={len(ps_raw)}')

    if not bg_raw:
        if verbose:
            print(f'  SKIP: no BgReadings in {patient_dir}')
        return None

    # Convert to Nightscout format
    entries = _convert_bg_readings(bg_raw)
    treatments = (
        _convert_treatments(tx_raw)
        + _convert_temp_basals(tb_raw)
        + _convert_temp_targets(tt_raw)
        + _convert_careportal(cp_raw)
    )
    treatments.sort(key=lambda t: t.get('created_at', ''))

    devicestatus = _convert_aps_data(aps_raw)
    profile = _synthesize_profile(aps_raw, ps_raw)

    if verbose:
        print(f'  Converted: entries={len(entries)} treatments={len(treatments)} '
              f'devicestatus={len(devicestatus)} profiles={len(profile)}')

    return {
        'entries': entries,
        'treatments': treatments,
        'devicestatus': devicestatus,
        'profile': profile,
    }


def write_odc_as_nightscout(patient_dir: str, output_dir: str,
                            verbose: bool = False) -> bool:
    """Convert ODC patient data and write as Nightscout JSON files.

    Writes entries.json, treatments.json, devicestatus.json, profile.json
    into output_dir, compatible with build_grid().
    """
    data = load_odc_patient(patient_dir, verbose=verbose)
    if data is None:
        return False

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for name, records in data.items():
        with open(out / f'{name}.json', 'w') as f:
            json.dump(records, f)

    if verbose:
        print(f'  Wrote Nightscout JSON to {output_dir}')
    return True
