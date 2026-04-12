"""
profile_generator.py — Generate AID profile JSON from optimized settings.

Research basis: EXP-2551 (simulation validates settings impact),
               EXP-1701-1717 (settings optimization pipeline),
               Profile format survey (WS-2: oref0/Loop/Trio/Nightscout).

Bridges the gap between abstract recommendations ("increase ISF by 30%")
and concrete importable profiles. Supports 4 output formats:

  1. oref0     — Minutes from midnight, "HH:MM:SS" strings
  2. Loop      — Seconds from midnight (TimeInterval)
  3. Trio      — Dual representation (minutes + "HH:MM:SS")
  4. Nightscout — "HH:MM" strings (REST API / ProfileSet)

Each format enforces system-specific constraints and validates
physiological ranges before output.

Integration: Pipeline Stage 6b, after settings_optimizer (6a).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import numpy as np

from .types import (
    OptimalSettings,
    PatientProfile,
    SettingScheduleEntry,
    SettingsOptimizationResult,
)

# ── Physiological Constraints ────────────────────────────────────────

CONSTRAINTS = {
    'basal_rate': {'min': 0.025, 'max': 10.0, 'unit': 'U/hr'},
    'isf':        {'min': 10.0,  'max': 500.0, 'unit': 'mg/dL/U'},
    'cr':         {'min': 3.0,   'max': 150.0, 'unit': 'g/U'},
    'dia':        {'min': 2.0,   'max': 12.0,  'unit': 'hours'},
    'target_low': {'min': 70.0,  'max': 180.0, 'unit': 'mg/dL'},
    'target_high':{'min': 80.0,  'max': 200.0, 'unit': 'mg/dL'},
}

# Period start hours → time strings
PERIOD_HOURS = {
    'overnight':  0,
    'morning':    6,
    'midday':    10,
    'afternoon': 14,
    'evening':   18,
}


# ── Time Format Helpers ──────────────────────────────────────────────

def _hour_to_hhmm(hour: int) -> str:
    """Convert hour (0-23) to 'HH:MM' string."""
    return f"{hour:02d}:00"


def _hour_to_hhmmss(hour: int) -> str:
    """Convert hour (0-23) to 'HH:MM:SS' string."""
    return f"{hour:02d}:00:00"


def _hour_to_minutes(hour: int) -> int:
    """Convert hour to minutes from midnight."""
    return hour * 60


def _hour_to_seconds(hour: int) -> int:
    """Convert hour to seconds from midnight."""
    return hour * 3600


def _clamp(value: float, param: str) -> float:
    """Clamp a value to its physiological constraint range."""
    c = CONSTRAINTS.get(param, {'min': 0.0, 'max': 1000.0})
    return max(c['min'], min(c['max'], value))


# ── Core Profile Data Structure ──────────────────────────────────────

@dataclass
class GeneratedProfile:
    """A complete AID therapy profile ready for export.

    Contains circadian schedules for basal, ISF, CR, and fixed DIA/targets.
    Can be exported to any supported AID format.
    """
    basal_blocks: List[Dict[str, Any]]   # [{hour, value, period, confidence}]
    isf_blocks: List[Dict[str, Any]]     # [{hour, value, period, confidence}]
    cr_blocks: List[Dict[str, Any]]      # [{hour, value, period, confidence}]
    dia_hours: float = 5.0
    target_low: float = 100.0
    target_high: float = 120.0
    units: str = 'mg/dL'
    source: str = 'digital-twin-optimizer'
    confidence_grade: str = 'B'
    warnings: List[str] = field(default_factory=list)

    def to_oref0(self) -> Dict[str, Any]:
        """Export as oref0/OpenAPS profile JSON."""
        return _to_oref0(self)

    def to_loop(self) -> Dict[str, Any]:
        """Export as Loop-compatible JSON (seconds from midnight)."""
        return _to_loop(self)

    def to_trio(self) -> Dict[str, Any]:
        """Export as Trio-compatible JSON (dual time representation)."""
        return _to_trio(self)

    def to_nightscout(self) -> Dict[str, Any]:
        """Export as Nightscout ProfileSet REST API format."""
        return _to_nightscout(self)

    def to_json(self, fmt: str = 'nightscout', indent: int = 2) -> str:
        """Serialize to JSON string in the specified format."""
        exporters = {
            'oref0': self.to_oref0,
            'loop': self.to_loop,
            'trio': self.to_trio,
            'nightscout': self.to_nightscout,
        }
        if fmt not in exporters:
            raise ValueError(f"Unknown format '{fmt}'. Use: {list(exporters)}")
        return json.dumps(exporters[fmt](), indent=indent)


# ── Profile Generation from Optimizer Output ─────────────────────────

def generate_profile(optimal: OptimalSettings,
                     base_profile: PatientProfile,
                     apply_recommendations: bool = True,
                     ) -> GeneratedProfile:
    """Generate a complete profile from optimization results.

    Args:
        optimal: OptimalSettings from settings_optimizer.
        base_profile: Current patient profile (for fallback values).
        apply_recommendations: If True, use recommended values.
            If False, use current values (for comparison export).

    Returns:
        GeneratedProfile ready for format export.
    """
    def _build_blocks(schedule: List[SettingScheduleEntry],
                      param: str) -> List[Dict[str, Any]]:
        blocks = []
        for entry in schedule:
            hour = entry.start_hour
            value = entry.recommended_value if apply_recommendations else entry.current_value
            value = _clamp(value, param)
            blocks.append({
                'hour': hour,
                'value': round(value, 3),
                'period': entry.period,
                'confidence': entry.confidence,
                'change_pct': round(entry.change_pct, 1) if apply_recommendations else 0.0,
            })
        # Ensure sorted by hour and starts at midnight
        blocks.sort(key=lambda b: b['hour'])
        if not blocks or blocks[0]['hour'] != 0:
            fallback = _get_profile_value(base_profile.basal_schedule
                                          if param == 'basal_rate'
                                          else base_profile.isf_schedule
                                          if param == 'isf'
                                          else base_profile.cr_schedule, 0)
            blocks.insert(0, {
                'hour': 0, 'value': round(_clamp(fallback, param), 3),
                'period': 'overnight', 'confidence': 'fallback', 'change_pct': 0.0,
            })
        return blocks

    basal = _build_blocks(optimal.basal_schedule, 'basal_rate')
    isf = _build_blocks(optimal.isf_schedule, 'isf')
    cr = _build_blocks(optimal.cr_schedule, 'cr')

    warnings = []
    # Flag low-confidence blocks
    for name, blocks in [('basal', basal), ('ISF', isf), ('CR', cr)]:
        low = [b for b in blocks if b['confidence'] == 'low']
        if low:
            periods = ', '.join(b['period'] for b in low)
            warnings.append(f"{name} has low confidence in: {periods}")

    # Flag large changes
    for name, blocks in [('basal', basal), ('ISF', isf), ('CR', cr)]:
        big = [b for b in blocks if abs(b.get('change_pct', 0)) > 50]
        if big:
            for b in big:
                warnings.append(
                    f"{name} {b['period']}: {b['change_pct']:+.0f}% change "
                    f"(verify with endocrinologist)")

    return GeneratedProfile(
        basal_blocks=basal,
        isf_blocks=isf,
        cr_blocks=cr,
        dia_hours=base_profile.dia_hours,
        target_low=base_profile.target_low,
        target_high=base_profile.target_high,
        units=base_profile.units,
        confidence_grade=optimal.confidence_grade.value,
        warnings=warnings,
    )


def _get_profile_value(schedule: List[Dict], hour: int) -> float:
    """Look up a profile value for a given hour."""
    if not schedule:
        return 1.0
    best = schedule[0]
    for entry in schedule:
        t = entry.get('time', '00:00')
        h = int(t.split(':')[0]) if isinstance(t, str) else 0
        if h <= hour:
            best = entry
    return float(best.get('value', best.get('rate',
                   best.get('sensitivity', best.get('ratio', 1.0)))))


# ── Format Exporters ─────────────────────────────────────────────────

def _to_oref0(profile: GeneratedProfile) -> Dict[str, Any]:
    """Convert to oref0/OpenAPS profile.json format.

    Time: minutes from midnight (int) + "HH:MM:SS" strings.
    Validated constraints: CR 3-150, DIA max 12h.

    Reference: externals/oref0/lib/profile/index.js
    """
    basalProfile = []
    for i, b in enumerate(profile.basal_blocks):
        basalProfile.append({
            'i': i,
            'start': _hour_to_hhmmss(b['hour']),
            'rate': round(b['value'], 2),
            'minutes': _hour_to_minutes(b['hour']),
        })

    isfProfile = {
        'units': profile.units,
        'user_preferred_units': profile.units,
        'sensitivities': [],
    }
    for i, b in enumerate(profile.isf_blocks):
        entry = {
            'i': i,
            'start': _hour_to_hhmmss(b['hour']),
            'sensitivity': round(b['value'], 1),
            'offset': _hour_to_minutes(b['hour']),
        }
        # Add endOffset (minutes until next block)
        if i + 1 < len(profile.isf_blocks):
            entry['endOffset'] = _hour_to_minutes(profile.isf_blocks[i + 1]['hour'])
        else:
            entry['endOffset'] = 1440  # end of day
        isfProfile['sensitivities'].append(entry)

    carbRatio = {
        'units': 'grams',
        'schedule': [],
    }
    for i, b in enumerate(profile.cr_blocks):
        carbRatio['schedule'].append({
            'i': i,
            'start': _hour_to_hhmmss(b['hour']),
            'ratio': round(b['value'], 1),
            'offset': _hour_to_minutes(b['hour']),
        })

    return {
        'min_5m_carbimpact': 8,
        'dia': min(profile.dia_hours, 12.0),
        'model': {},
        'basalprofile': basalProfile,
        'isfProfile': isfProfile,
        'carb_ratio': carbRatio['schedule'][0]['ratio'] if carbRatio['schedule'] else 10,
        'carb_ratios': carbRatio,
        'bg_targets': {
            'units': profile.units,
            'targets': [{
                'i': 0,
                'start': '00:00:00',
                'offset': 0,
                'low': profile.target_low,
                'high': profile.target_high,
                'min_bg': profile.target_low,
                'max_bg': profile.target_high,
            }],
        },
        'out_units': profile.units,
        'current_basal': basalProfile[0]['rate'] if basalProfile else 1.0,
        'max_daily_basal': max(b['value'] for b in profile.basal_blocks) * 4,
        'max_basal': max(b['value'] for b in profile.basal_blocks) * 4,
        '_meta': {
            'source': profile.source,
            'confidence': profile.confidence_grade,
            'warnings': profile.warnings,
        },
    }


def _to_loop(profile: GeneratedProfile) -> Dict[str, Any]:
    """Convert to Loop-compatible format.

    Time: seconds from midnight (Double/TimeInterval).
    Uses LoopKit schedule value representation.

    Reference: externals/LoopWorkspace/LoopKit/LoopKit/DailyValueSchedule.swift
    """
    def _schedule(blocks, key='value'):
        return [{
            'startTime': _hour_to_seconds(b['hour']),
            'value': round(b['value'], 3),
        } for b in blocks]

    return {
        'basalRateSchedule': {
            'items': _schedule(profile.basal_blocks),
            'timeZone': 0,
        },
        'insulinSensitivitySchedule': {
            'unit': profile.units,
            'items': _schedule(profile.isf_blocks),
            'timeZone': 0,
        },
        'carbRatioSchedule': {
            'unit': 'g',
            'items': _schedule(profile.cr_blocks),
            'timeZone': 0,
        },
        'insulinModelSettings': {
            'effectDuration': profile.dia_hours * 3600,
        },
        'glucoseTargetRangeSchedule': {
            'unit': profile.units,
            'items': [{
                'startTime': 0,
                'minValue': profile.target_low,
                'maxValue': profile.target_high,
            }],
            'timeZone': 0,
        },
        '_meta': {
            'source': profile.source,
            'confidence': profile.confidence_grade,
            'warnings': profile.warnings,
        },
    }


def _to_trio(profile: GeneratedProfile) -> Dict[str, Any]:
    """Convert to Trio-compatible format.

    Time: dual representation — minutes (int) + "HH:MM:SS" (string).
    Precision: values as strings for Decimal compatibility.

    Reference: externals/Trio/Trio/Sources/Models/BasalProfileEntry.swift
    """
    basal = []
    for b in profile.basal_blocks:
        basal.append({
            'start': _hour_to_hhmmss(b['hour']),
            'minutes': _hour_to_minutes(b['hour']),
            'rate': round(b['value'], 3),
        })

    isf = {
        'units': 'mg/dl' if 'mg' in profile.units.lower() else 'mmol',
        'user_preferred_units': 'mg/dl' if 'mg' in profile.units.lower() else 'mmol',
        'sensitivities': [],
    }
    for b in profile.isf_blocks:
        isf['sensitivities'].append({
            'sensitivity': round(b['value'], 1),
            'offset': _hour_to_minutes(b['hour']),
            'start': _hour_to_hhmmss(b['hour']),
        })

    cr = {
        'units': 'grams',
        'schedule': [],
    }
    for b in profile.cr_blocks:
        cr['schedule'].append({
            'start': _hour_to_hhmmss(b['hour']),
            'offset': _hour_to_minutes(b['hour']),
            'ratio': round(b['value'], 1),
        })

    return {
        'basalprofile': basal,
        'isfProfile': isf,
        'carb_ratios': cr,
        'dia': profile.dia_hours,
        'bg_targets': {
            'units': isf['units'],
            'targets': [{
                'start': '00:00:00',
                'offset': 0,
                'low': profile.target_low,
                'high': profile.target_high,
            }],
        },
        '_meta': {
            'source': profile.source,
            'confidence': profile.confidence_grade,
            'warnings': profile.warnings,
        },
    }


def _to_nightscout(profile: GeneratedProfile) -> Dict[str, Any]:
    """Convert to Nightscout ProfileSet REST API format.

    Time: "HH:MM" strings. Wraps in ProfileSet envelope.

    Reference: externals/cgm-remote-monitor/lib/api3/generic/
    """
    store = {
        'Default': {
            'dia': str(profile.dia_hours),
            'carbratio': [{
                'time': _hour_to_hhmm(b['hour']),
                'timeAsSeconds': _hour_to_seconds(b['hour']),
                'value': str(round(b['value'], 1)),
            } for b in profile.cr_blocks],
            'sens': [{
                'time': _hour_to_hhmm(b['hour']),
                'timeAsSeconds': _hour_to_seconds(b['hour']),
                'value': str(round(b['value'], 1)),
            } for b in profile.isf_blocks],
            'basal': [{
                'time': _hour_to_hhmm(b['hour']),
                'timeAsSeconds': _hour_to_seconds(b['hour']),
                'value': str(round(b['value'], 3)),
            } for b in profile.basal_blocks],
            'target_low': [{
                'time': '00:00',
                'timeAsSeconds': 0,
                'value': str(profile.target_low),
            }],
            'target_high': [{
                'time': '00:00',
                'timeAsSeconds': 0,
                'value': str(profile.target_high),
            }],
            'units': profile.units,
            'timezone': 'UTC',
        },
    }

    return {
        'defaultProfile': 'Default',
        'store': store,
        'startDate': '',
        'mills': 0,
        '_meta': {
            'source': profile.source,
            'confidence': profile.confidence_grade,
            'warnings': profile.warnings,
        },
    }


# ── Convenience: Full Pipeline ───────────────────────────────────────

def generate_all_formats(optimization_result: SettingsOptimizationResult,
                         base_profile: PatientProfile,
                         ) -> Dict[str, Any]:
    """Generate profiles in all 4 formats from an optimization result.

    Returns a dict keyed by format name, each containing the profile JSON.
    """
    profile = generate_profile(optimization_result.optimal, base_profile)
    return {
        'oref0': profile.to_oref0(),
        'loop': profile.to_loop(),
        'trio': profile.to_trio(),
        'nightscout': profile.to_nightscout(),
        'meta': {
            'confidence_grade': profile.confidence_grade,
            'warnings': profile.warnings,
            'dia_hours': profile.dia_hours,
            'units': profile.units,
        },
    }
