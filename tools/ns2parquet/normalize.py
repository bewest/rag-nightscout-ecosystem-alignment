"""
normalize.py — Transform Nightscout JSON records into flat DataFrames.

Each normalize_* function takes a list of raw JSON records (as dicts) and a
patient_id string, and returns a pandas DataFrame with columns matching the
corresponding PyArrow schema in schemas.py.

Key transformations:
- Timestamps → UTC datetime64
- Loop duration seconds → minutes
- AAPS duration milliseconds → minutes
- Loop absorptionTime seconds → minutes
- Multi-step SMB detection (type, automatic, eventType)
- DeviceStatus: handles both Loop (flat) and oref0 (nested) structures
- Profiles: expands time-varying schedules to one row per segment
"""

import logging
import warnings

import numpy as np
import pandas as pd
from typing import List, Dict, Optional

from .constants import DIRECTION_MAP, MMOLL_TO_MGDL  # noqa: F401 — re-export

logger = logging.getLogger(__name__)


def _parse_ts(record: dict, *fields) -> Optional[pd.Timestamp]:
    """Try multiple timestamp fields, return first valid UTC timestamp."""
    for field in fields:
        val = record.get(field)
        if val is None:
            continue
        try:
            if isinstance(val, (int, float)) and val > 1e10:
                return pd.Timestamp(val, unit='ms', tz='UTC')
            ts = pd.Timestamp(val)
            if ts.tzinfo is None:
                ts = ts.tz_localize('UTC')
            return ts.tz_convert('UTC')
        except Exception:
            continue
    return None


def _detect_controller(device: str) -> str:
    """Detect AID controller from device string."""
    if not device:
        return 'unknown'
    dl = device.lower()
    if dl.startswith('loop://') or 'loop' in dl:
        return 'loop'
    if dl.startswith('openaps://') or 'openaps' in dl:
        return 'openaps'
    if 'trio' in dl:
        return 'trio'
    if 'aaps' in dl or 'androidaps' in dl:
        return 'aaps'
    if 'xdrip' in dl:
        return 'xdrip'
    return 'unknown'


def _is_smb(record: dict) -> bool:
    """Multi-step SMB detection per GAP-TREAT-002.

    Do NOT rely solely on eventType. Check:
    1. AAPS: type == 'SMB'
    2. Loop/Trio: automatic == true AND small insulin dose
    3. eventType == 'Correction Bolus' with automatic flag
    """
    if record.get('type') == 'SMB':
        return True
    if record.get('automatic') is True:
        insulin = record.get('insulin', 0) or 0
        if insulin > 0 and insulin < 5.0:  # SMBs are typically small
            return True
    return False


def _duration_to_minutes(record: dict, device: str = '') -> Optional[float]:
    """Convert duration to minutes, handling unit differences.

    - Nightscout/oref0: minutes (no conversion)
    - Loop: may use seconds for enacted durations
    - AAPS: may use milliseconds in some contexts
    """
    dur = record.get('duration')
    if dur is None:
        return None
    dur = float(dur)
    controller = _detect_controller(device or record.get('enteredBy', ''))
    if controller == 'loop' and dur > 1000:
        return dur / 60.0  # seconds → minutes
    if dur > 86400:
        return dur / 60000.0  # milliseconds → minutes
    return dur


def _absorption_to_minutes(record: dict, device: str = '') -> Optional[float]:
    """Convert absorptionTime to minutes.

    Loop/Trio store absorption in SECONDS internally but may upload either.
    Nightscout canonical is minutes.
    """
    val = record.get('absorptionTime')
    if val is None:
        return None
    val = float(val)
    if val > 500:  # > 500 minutes is unreasonable, likely seconds
        return val / 60.0
    return val


# ── Entries ─────────────────────────────────────────────────────────────

def normalize_entries(records: List[Dict], patient_id: str) -> pd.DataFrame:
    """Normalize raw Nightscout entries JSON → flat DataFrame.

    Handles SGV, MBG, and calibration records. Deduplicates by _id.
    """
    rows = []
    seen_ids = set()

    for e in records:
        eid = e.get('_id')
        if eid and eid in seen_ids:
            continue
        if eid:
            seen_ids.add(eid)

        ts = _parse_ts(e, 'date', 'dateString', 'sysTime')
        if ts is None:
            continue

        entry_type = e.get('type', 'sgv')
        rows.append({
            'patient_id': patient_id,
            '_id': eid,
            'type': entry_type,
            'date': ts,
            'sgv': float(e['sgv']) if entry_type == 'sgv' and 'sgv' in e else None,
            'mbg': float(e['mbg']) if entry_type == 'mbg' and 'mbg' in e else None,
            'direction': e.get('direction'),
            'noise': int(e['noise']) if 'noise' in e and e['noise'] is not None else None,
            'filtered': float(e['filtered']) if 'filtered' in e and e['filtered'] is not None else None,
            'unfiltered': float(e['unfiltered']) if 'unfiltered' in e and e['unfiltered'] is not None else None,
            'delta': float(e['delta']) if 'delta' in e and e['delta'] is not None else None,
            'rssi': int(e['rssi']) if 'rssi' in e and e['rssi'] is not None else None,
            'trend': int(e['trend']) if 'trend' in e and e['trend'] is not None else None,
            'trend_rate': float(e['trendRate']) if 'trendRate' in e and e['trendRate'] is not None else None,
            'device': e.get('device'),
            'utc_offset': int(e['utcOffset']) if 'utcOffset' in e and e['utcOffset'] is not None else None,
        })

    if not rows:
        return pd.DataFrame(columns=[
            'patient_id', '_id', 'type', 'date', 'sgv', 'mbg', 'direction',
            'noise', 'filtered', 'unfiltered', 'delta', 'rssi', 'trend',
            'trend_rate', 'device', 'utc_offset',
        ])

    df = pd.DataFrame(rows)
    df = df.sort_values('date').reset_index(drop=True)
    return df


# ── Treatments ──────────────────────────────────────────────────────────

def normalize_treatments(records: List[Dict], patient_id: str) -> pd.DataFrame:
    """Normalize raw Nightscout treatments JSON → flat DataFrame.

    Performs:
    - Unit conversion (duration, absorption time)
    - SMB detection (multi-step)
    - Deduplication by _id
    """
    rows = []
    seen_ids = set()

    for tx in records:
        tid = tx.get('_id')
        if tid and tid in seen_ids:
            continue
        if tid:
            seen_ids.add(tid)

        ts = _parse_ts(tx, 'created_at', 'timestamp', 'date')
        if ts is None:
            continue

        device = tx.get('enteredBy', '') or tx.get('device', '') or ''
        rows.append({
            'patient_id': patient_id,
            '_id': tid,
            'event_type': tx.get('eventType', ''),
            'created_at': ts,
            'insulin': float(tx['insulin']) if tx.get('insulin') else None,
            'programmed': float(tx['programmed']) if tx.get('programmed') else None,
            'is_smb': _is_smb(tx),
            'is_automatic': bool(tx.get('automatic', False)),
            'bolus_type': tx.get('bolusType'),
            'insulin_type': tx.get('insulinType') or tx.get('insulintype'),
            'carbs': float(tx['carbs']) if tx.get('carbs') else None,
            'absorption_time_min': _absorption_to_minutes(tx, device),
            'food_type': tx.get('foodType'),
            'fat': float(tx['fat']) if tx.get('fat') else None,
            'protein': float(tx['protein']) if tx.get('protein') else None,
            'rate': float(tx['rate']) if 'rate' in tx and tx['rate'] is not None else (
                float(tx['absolute']) if 'absolute' in tx and tx['absolute'] is not None else None),
            'duration_min': _duration_to_minutes(tx, device),
            'percent': float(tx['percent']) if tx.get('percent') is not None else None,
            'temp_type': tx.get('temp'),
            'target_top': float(tx['targetTop']) if tx.get('targetTop') else None,
            'target_bottom': float(tx['targetBottom']) if tx.get('targetBottom') else None,
            'reason': tx.get('reason'),
            'glucose': float(tx['glucose']) if tx.get('glucose') else None,
            'glucose_type': tx.get('glucoseType'),
            'entered_by': tx.get('enteredBy'),
            'device': tx.get('device'),
            'notes': tx.get('notes'),
            'utc_offset': int(tx['utcOffset']) if 'utcOffset' in tx and tx['utcOffset'] is not None else None,
            'identifier': tx.get('identifier'),
            'sync_identifier': tx.get('syncIdentifier'),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values('created_at').reset_index(drop=True)
    return df


# ── DeviceStatus ────────────────────────────────────────────────────────

def _extract_loop_ds(ds: dict) -> dict:
    """Extract fields from a Loop-style devicestatus (flat structure)."""
    loop = ds.get('loop', {}) or {}
    iob_data = loop.get('iob', {}) or {}
    cob_data = loop.get('cob', {}) or {}
    predicted = loop.get('predicted', {}) or {}
    pred_values = predicted.get('values', []) if isinstance(predicted, dict) else []
    enacted = loop.get('enacted', {}) or {}
    override = ds.get('override', loop.get('override', {})) or {}

    # Enacted duration: Loop uses SECONDS
    enacted_dur = enacted.get('duration')
    if enacted_dur is not None:
        enacted_dur = float(enacted_dur) / 60.0  # seconds → minutes

    return {
        'iob': float(iob_data['iob']) if 'iob' in iob_data else None,
        'basal_iob': None,
        'bolus_iob': None,
        'cob': float(cob_data.get('cob', 0)) if cob_data else None,
        'bg': None,
        'eventual_bg': None,
        'target_bg': None,
        'sensitivity_ratio': None,
        'insulin_req': None,
        'suggested_rate': None,
        'suggested_duration_min': None,
        'suggested_smb': None,
        'enacted_rate': float(enacted['rate']) if 'rate' in enacted else None,
        'enacted_duration_min': enacted_dur,
        'enacted_smb': float(enacted.get('bolusVolume', 0) or 0) if enacted else None,
        'enacted_received': enacted.get('received'),
        'predicted_30': float(pred_values[6]) if len(pred_values) > 6 else None,
        'predicted_60': float(pred_values[12]) if len(pred_values) > 12 else None,
        'predicted_min': float(min(pred_values)) if pred_values else None,
        'hypo_risk_count': sum(1 for v in pred_values if v < 70) if pred_values else None,
        'pred_iob_30': None,
        'pred_cob_30': None,
        'pred_uam_30': None,
        'pred_zt_30': None,
        'loop_failure_reason': loop.get('failureReason'),
        'loop_version': loop.get('version'),
        'recommended_bolus': float(loop.get('recommendedBolus', 0) or 0),
        'override_active': bool(override.get('active', False)),
        'override_name': override.get('name'),
        'override_multiplier': float(override['multiplier']) if 'multiplier' in override else None,
        'reason': None,
    }


def _extract_oref0_ds(ds: dict) -> dict:
    """Extract fields from an oref0-style devicestatus (nested openaps structure)."""
    openaps = ds.get('openaps', {}) or {}
    iob_data = openaps.get('iob', {}) or {}
    # oref0 may have iob as a list; take first entry
    if isinstance(iob_data, list) and iob_data:
        iob_data = iob_data[0]

    suggested = openaps.get('suggested', {}) or {}
    enacted = openaps.get('enacted', {}) or {}
    pred_bgs = suggested.get('predBGs', {}) or {}

    def _pred_at(curve_name, idx):
        vals = pred_bgs.get(curve_name, [])
        return float(vals[idx]) if len(vals) > idx else None

    # Select best available prediction curve (same priority as grid.py)
    best_curve = None
    for _cn in ['COB', 'UAM', 'IOB', 'ZT']:
        if pred_bgs.get(_cn):
            best_curve = pred_bgs[_cn]
            break

    # oref0 durations are in MINUTES (no conversion needed)
    return {
        'iob': float(iob_data.get('iob', 0)) if iob_data else None,
        'basal_iob': float(iob_data.get('basaliob', 0)) if 'basaliob' in iob_data else None,
        'bolus_iob': float(iob_data.get('bolussnooze', 0)) if 'bolussnooze' in iob_data else None,
        'cob': float(suggested.get('COB', 0)) if 'COB' in suggested else None,
        'bg': int(suggested['bg']) if 'bg' in suggested else None,
        'eventual_bg': int(suggested['eventualBG']) if 'eventualBG' in suggested else None,
        'target_bg': int(suggested['targetBG']) if 'targetBG' in suggested else None,
        'sensitivity_ratio': float(suggested['sensitivityRatio']) if 'sensitivityRatio' in suggested else None,
        'insulin_req': float(suggested['insulinReq']) if 'insulinReq' in suggested else None,
        'suggested_rate': float(suggested['rate']) if 'rate' in suggested else None,
        'suggested_duration_min': float(suggested['duration']) if 'duration' in suggested else None,
        'suggested_smb': float(suggested['units']) if 'units' in suggested else None,
        'enacted_rate': float(enacted['rate']) if 'rate' in enacted else None,
        'enacted_duration_min': float(enacted['duration']) if 'duration' in enacted else None,
        'enacted_smb': float(enacted.get('units', 0)) if enacted else None,
        'enacted_received': enacted.get('received') if enacted else None,
        'predicted_30': float(best_curve[6]) if best_curve and len(best_curve) > 6 else None,
        'predicted_60': float(best_curve[12]) if best_curve and len(best_curve) > 12 else None,
        'predicted_min': float(min(best_curve)) if best_curve else None,
        'hypo_risk_count': sum(1 for v in best_curve if v < 70) if best_curve else None,
        'pred_iob_30': _pred_at('IOB', 6),
        'pred_cob_30': _pred_at('COB', 6),
        'pred_uam_30': _pred_at('UAM', 6),
        'pred_zt_30': _pred_at('ZT', 6),
        'loop_failure_reason': None,
        'loop_version': None,
        'recommended_bolus': None,
        'override_active': None,
        'override_name': None,
        'override_multiplier': None,
        'reason': suggested.get('reason'),
    }


def normalize_devicestatus(records: List[Dict], patient_id: str) -> pd.DataFrame:
    """Normalize raw Nightscout devicestatus JSON → flat DataFrame.

    Detects Loop vs oref0 structure and flattens accordingly.
    """
    rows = []
    seen_ids = set()

    for ds in records:
        did = ds.get('_id')
        if did and did in seen_ids:
            continue
        if did:
            seen_ids.add(did)

        ts = _parse_ts(ds, 'created_at', 'timestamp')
        if ts is None:
            continue

        device = ds.get('device', '')
        controller = _detect_controller(device)

        # Choose extraction strategy based on structure
        if 'loop' in ds and isinstance(ds.get('loop'), dict):
            fields = _extract_loop_ds(ds)
            if controller == 'unknown':
                controller = 'loop'
        elif 'openaps' in ds and isinstance(ds.get('openaps'), dict):
            fields = _extract_oref0_ds(ds)
            if controller == 'unknown':
                controller = 'openaps'
        else:
            # Minimal record — just pump/uploader info
            fields = {k: None for k in _extract_loop_ds({}).keys()}

        # Pump info (common structure)
        pump = ds.get('pump', {}) or {}
        batt = pump.get('battery', {})
        if isinstance(batt, dict):
            pump_battery = float(batt['percent']) if 'percent' in batt else None
        else:
            pump_battery = None

        pump_clock = None
        if 'clock' in pump:
            try:
                pump_clock = pd.Timestamp(pump['clock'])
                if pump_clock.tzinfo is None:
                    pump_clock = pump_clock.tz_localize('UTC')
            except Exception:
                pass

        # Uploader info
        uploader = ds.get('uploader', {}) or {}
        uploader_battery = (
            float(uploader.get('battery', ds.get('uploaderBattery', np.nan)))
        )
        if np.isnan(uploader_battery):
            uploader_battery = None

        row = {
            'patient_id': patient_id,
            '_id': did,
            'created_at': ts,
            'device': device,
            'controller': controller,
            **fields,
            'pump_battery_pct': pump_battery,
            'pump_reservoir': float(pump['reservoir']) if 'reservoir' in pump else None,
            'pump_status': pump.get('status', {}).get('status') if isinstance(pump.get('status'), dict) else None,
            'pump_clock': pump_clock,
            'uploader_battery_pct': uploader_battery,
            'utc_offset': int(ds['utcOffset']) if 'utcOffset' in ds and ds['utcOffset'] is not None else None,
        }
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.sort_values('created_at').reset_index(drop=True)
    return df


# ── Profiles ────────────────────────────────────────────────────────────

def _normalize_timezone(tz_str: str) -> str:
    """Normalize Nightscout timezone (ETC/GMT+7 → Etc/GMT+7)."""
    if not tz_str:
        return 'UTC'
    if tz_str.upper().startswith('ETC/'):
        return 'Etc/' + tz_str[4:]
    return tz_str


def _resolve_timezone(settings: dict, patient_id: str) -> Optional[str]:
    """Extract IANA timezone from settings, NOT timeFormat.

    Nightscout settings.timeFormat is 12/24 (clock format), not a timezone.
    The actual timezone lives in the profile store.  If the status doc
    doesn't carry it directly, return None rather than a wrong value.
    """
    # Some deployments surface timezone at the settings level
    tz = settings.get('timezone')
    if isinstance(tz, str) and tz:
        return _normalize_timezone(tz)
    return None


def normalize_profiles(records, patient_id: str) -> pd.DataFrame:
    """Normalize Nightscout profile JSON → expanded schedule rows.

    Each schedule segment (basal, ISF, CR, target) becomes its own row.
    This makes it easy to query: "What was patient X's ISF at 3pm?"
    """
    if isinstance(records, dict):
        records = [records]

    rows = []
    for profile_doc in records:
        pid = profile_doc.get('_id')
        created = _parse_ts(profile_doc, 'created_at', 'startDate', 'mills')
        start_date = _parse_ts(profile_doc, 'startDate')

        store = profile_doc.get('store', {})
        if not store:
            continue

        for profile_name, profile in store.items():
            tz = _normalize_timezone(profile.get('timezone', ''))
            dia = float(profile.get('dia', 5.0))
            insulin_curve = profile.get('insulinCurve')

            # Detect mmol/L profiles — ISF and targets need conversion to mg/dL
            profile_units = (profile.get('units') or 'mg/dL').lower().replace('/', '')
            is_mmol = profile_units in ('mmoll', 'mmol')
            # Schedule types where values are glucose-unit-dependent
            _glucose_unit_schedules = {'isf', 'target_low', 'target_high'}

            schedule_types = {
                'basal': profile.get('basal', []),
                'isf': profile.get('sens', []),
                'cr': profile.get('carbratio', []),
                'target_low': profile.get('target_low', []),
                'target_high': profile.get('target_high', []),
            }

            for stype, schedule in schedule_types.items():
                if not schedule:
                    continue
                for entry in schedule:
                    time_secs = entry.get('timeAsSeconds', 0)
                    time_str = entry.get('time', f'{time_secs // 3600:02d}:{(time_secs % 3600) // 60:02d}')
                    raw_value = float(entry.get('value', 0))
                    # Convert mmol/L → mg/dL for ISF and target schedules
                    if is_mmol and stype in _glucose_unit_schedules:
                        raw_value = raw_value * MMOLL_TO_MGDL
                    rows.append({
                        'patient_id': patient_id,
                        '_id': pid,
                        'profile_name': profile_name,
                        'created_at': created,
                        'start_date': start_date,
                        'timezone': tz,
                        'dia_hours': dia,
                        'insulin_curve': insulin_curve,
                        'schedule_type': stype,
                        'time_seconds': int(time_secs),
                        'time_str': time_str,
                        'value': raw_value,
                        'units': 'mg/dL',  # always mg/dL after conversion
                    })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def normalize_settings(status_doc: dict, patient_id: str) -> pd.DataFrame:
    """Normalize Nightscout /api/v1/status.json → site metadata row.

    Extracts key settings that inform data interpretation:
    - units: display preference (mg/dL or mmol/L)
    - enable: active plugins (indicates pump/MDI, CGM source, AID system)
    - thresholds: BG target ranges configured on the site

    One row per patient per fetch, enabling unit verification and
    MDI-vs-pump classification without inspecting devicestatus.
    """
    settings = status_doc.get('settings', status_doc)
    if not settings:
        return pd.DataFrame()

    enabled = settings.get('enable', [])
    has_loop = 'loop' in enabled
    has_openaps = 'openaps' in enabled
    has_pump = any(p in enabled for p in ['pump', 'iob', 'loop', 'openaps'])

    # Classify data mode
    if has_loop or has_openaps:
        data_mode = 'AID'
    elif has_pump:
        data_mode = 'pump'
    else:
        data_mode = 'MDI'

    thresholds = settings.get('thresholds', {})

    row = {
        'patient_id': patient_id,
        'fetched_at': pd.Timestamp.now(tz='UTC'),
        'server_version': status_doc.get('version', None),
        'units': settings.get('units', 'mg/dL'),
        'data_mode': data_mode,
        'has_pump': has_pump,
        'has_loop': has_loop,
        'has_openaps': has_openaps,
        'enabled_plugins': ','.join(sorted(enabled)) if enabled else None,
        'bg_high': float(thresholds.get('bgHigh', 260)),
        'bg_target_top': float(thresholds.get('bgTargetTop', 180)),
        'bg_target_bottom': float(thresholds.get('bgTargetBottom', 80)),
        'bg_low': float(thresholds.get('bgLow', 55)),
        'timezone': _resolve_timezone(settings, patient_id),
        'language': settings.get('language', None),
    }

    return pd.DataFrame([row])
