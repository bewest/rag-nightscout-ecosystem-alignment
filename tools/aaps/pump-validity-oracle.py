#!/usr/bin/env python3
"""
Pump validity oracle for AAPS profile-store sync.

Statically replicates ProfileSealed.Pure.isValid() against the user's profile
JSON, evaluated for each pump driver's pumpDescription defaults. Output tells
us which pump+profile combinations would silently bail
DataSyncSelectorV1/V3.processChangedProfileStore at the
`!allProfilesValid` guard (line 792 / 718).

Source references (externals/AndroidAPS):
  core/objects/.../ProfileSealed.kt:123-220       Pure.isValid
  core/interfaces/.../HardLimits.kt:18-23         hard-limit constants
  core/data/.../PumpDescription.kt:25,58          basalMaximumRate default + reset value
  core/interfaces/.../PumpDescriptionExtension.kt fillFor (resetSettings + pumpType overrides)
  pump/virtual/.../VirtualPumpPlugin.kt:95-116    Virtual Pump init (notably omits basalMaximumRate)

USAGE
  python3 tools/aaps/pump-validity-oracle.py
  python3 tools/aaps/pump-validity-oracle.py --profile path/to/profile.json
"""
import argparse
import json
import sys
from dataclasses import dataclass, field

# ------------------------------------------------------------- HARD LIMITS ---
# loadAge() is currently always 0 in adult mode (HardLimitsImpl.kt). We use [0]
# of every age-indexed array, matching default install.
MIN_DIA = 5.0       # HardLimits.kt:18
MAX_DIA = 9.0       # HardLimits.kt:19
MIN_IC  = 2.0       # HardLimits.kt:20
MAX_IC  = 100.0     # HardLimits.kt:21
MIN_ISF = 2.0       # HardLimits.kt:22 (mg/dL)
MAX_ISF = 1000.0    # HardLimits.kt:23 (mg/dL)
MAX_BASAL = 5.0     # typical adult value (HardLimitsImpl.kt loadAge()=0)


# --------------------------------------------------------- PUMPDESCRIPTION ---
@dataclass
class PumpDescription:
    name: str
    basalMinimumRate: float
    basalMaximumRate: float
    is30minBasalRatesCapable: bool


# Default state of `var basalMaximumRate = 0.0` (PumpDescription.kt:25)
# applies to any PumpPlugin whose init block forgets to either call
# resetSettings()/fillFor() OR explicitly assign basalMaximumRate.
PUMP_DESCRIPTIONS = [
    # Virtual Pump's pumpDescription init at VirtualPumpPlugin.kt:95-116 sets
    # basalStep/basalMinimumRate/is30minBasalRatesCapable but NOT basalMaximumRate
    # — so it is 0.0 until refreshConfiguration() runs (which happens in onStart()).
    # Both states modeled below:
    PumpDescription("Virtual (pre-onStart, basalMaximumRate=0)", 0.01, 0.0, True),
    PumpDescription("Virtual (post-onStart, fillFor → resetSettings)", 0.04, 25.0, False),

    # Pumps that go through fillFor() inherit resetSettings() defaults (25.0)
    # then have `basalMinimumRate = pumpType.baseBasalMinValue()` overridden
    # but basalMaximumRate stays at 25.0 unless explicitly assigned.
    PumpDescription("Dana RS / DanaR / Dana-i (fillFor)",        0.04, 25.0, True),
    PumpDescription("Omnipod Eros (fillFor)",                    0.05, 25.0, False),
    PumpDescription("Omnipod Dash (fillFor)",                    0.05, 25.0, False),
    PumpDescription("Medtrum Nano (fillFor)",                    0.05, 25.0, False),

    # Pumps that explicitly read max from device settings (rare for new users):
    PumpDescription("Insight (basalMaximumRate=device-supplied)", 0.02, 25.0, True),
    PumpDescription("DiaconnG8 (basalMaximumRate=device-supplied)", 0.04, 5.0, False),
]


# ------------------------------------------------------------ ISVALID LOGIC --
@dataclass
class ValidityCheck:
    is_valid: bool = True
    reasons: list = field(default_factory=list)


def in_range(value, low, high):
    """ProfileSealed.kt isInRange (HardLimitsImpl.kt:59) — inclusive on both ends."""
    return low <= value <= high


def to_mgdl(value, units):
    if units == 'mg/dl':
        return value
    return value * 18.0  # mmol/L → mg/dL


def is_valid(profile_json, pump):
    """Replicates ProfileSealed.Pure.isValid (ProfileSealed.kt:123-220)."""
    vc = ValidityCheck()
    units = profile_json.get('units', 'mg/dl')
    dia   = float(profile_json.get('dia', 0))
    basal_blocks = profile_json.get('basal', [])
    ic_blocks    = profile_json.get('carbratio', [])
    isf_blocks   = profile_json.get('sens', [])

    # ----- basal blocks (lines 127-167) -----
    # Convert time-of-day list to per-block durations.
    times_min = []
    for b in basal_blocks:
        h, m = (b.get('time') or b.get('timeAsSeconds', '00:00')).split(':')[:2]
        times_min.append(int(h) * 60 + int(m))
    times_min.sort()
    durations_ms = []
    for i, t in enumerate(times_min):
        nxt = times_min[i + 1] if i + 1 < len(times_min) else 24 * 60
        durations_ms.append((nxt - t) * 60 * 1000)

    for i, blk in enumerate(basal_blocks):
        amt = float(blk['value'])
        # hour alignment for non-30min-capable pumps (line 129-146)
        if not pump.is30minBasalRatesCapable:
            if durations_ms[i] % 3600000 != 0:
                vc.is_valid = False
                vc.reasons.append(f"basal block @{blk['time']} not aligned to whole hour")
                break
        if not in_range(amt, 0.01, MAX_BASAL):
            vc.is_valid = False
            vc.reasons.append(f"basal {amt} out of [0.01, {MAX_BASAL}]")
            break
        if amt < pump.basalMinimumRate:
            vc.is_valid = False
            vc.reasons.append(f"basal {amt} < pump.basalMinimumRate ({pump.basalMinimumRate})")
            break
        if amt > pump.basalMaximumRate:
            vc.is_valid = False
            vc.reasons.append(f"basal {amt} > pump.basalMaximumRate ({pump.basalMaximumRate})")
            break

    # ----- DIA (line 169-172) -----
    if not in_range(dia, MIN_DIA, MAX_DIA):
        vc.is_valid = False
        vc.reasons.append(f"DIA {dia} out of [{MIN_DIA}, {MAX_DIA}]")

    # ----- IC (line 173-184) -----
    for blk in ic_blocks:
        amt = float(blk['value'])
        if not in_range(amt, MIN_IC, MAX_IC):
            vc.is_valid = False
            vc.reasons.append(f"IC {amt} out of [{MIN_IC}, {MAX_IC}]")
            break

    # ----- ISF (line 185-196) — converted to mgdl -----
    for blk in isf_blocks:
        amt_mgdl = to_mgdl(float(blk['value']), units)
        if not in_range(amt_mgdl, MIN_ISF, MAX_ISF):
            vc.is_valid = False
            vc.reasons.append(f"ISF {blk['value']} ({amt_mgdl} mg/dL) out of [{MIN_ISF}, {MAX_ISF}]")
            break

    return vc


# --------------------------------------------------- DEFAULT TEST PROFILES ---
# Profile values from the Discord screenshot
# (potential-profile-ns-bug-from-discord-Screenshot_2026-04-20_145017.png).
SCREENSHOT_PROFILE = {
    'units': 'mmol/L',     # screenshot shows "Units: mmol"
    'dia': 9,
    'carbratio': [{'time': '00:00', 'value': 15}],
    'sens':      [{'time': '00:00', 'value': 4}],
    'basal':     [{'time': '00:00', 'value': 0.4}],
}

CANDIDATE_PROFILES = {
    'screenshot-defaults':  SCREENSHOT_PROFILE,
    'min-edge':             {'units': 'mg/dl', 'dia': 5,  'carbratio': [{'time': '00:00', 'value': 2}],   'sens': [{'time': '00:00', 'value': 5}],   'basal': [{'time': '00:00', 'value': 0.04}]},
    'max-edge':             {'units': 'mg/dl', 'dia': 9,  'carbratio': [{'time': '00:00', 'value': 100}], 'sens': [{'time': '00:00', 'value': 999}], 'basal': [{'time': '00:00', 'value': 4.99}]},
    'dia-just-over':        {'units': 'mg/dl', 'dia': 9.5,'carbratio': [{'time': '00:00', 'value': 10}],  'sens': [{'time': '00:00', 'value': 50}],  'basal': [{'time': '00:00', 'value': 0.5}]},
    'half-hour-block':      {'units': 'mg/dl', 'dia': 6,  'carbratio': [{'time': '00:00', 'value': 10}, {'time': '00:30', 'value': 12}],  'sens': [{'time': '00:00', 'value': 50}], 'basal': [{'time': '00:00', 'value': 0.5}, {'time': '00:30', 'value': 0.6}]},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--profile', help='Path to a profile JSON file (single store entry); '
                                       'if omitted, runs the candidate library above.')
    args = ap.parse_args()

    profiles = CANDIDATE_PROFILES
    if args.profile:
        profiles = {args.profile: json.load(open(args.profile))}

    print(f"\n{'profile':<22} {'pump':<48} valid  reason")
    print("-" * 110)
    for pname, pj in profiles.items():
        for pump in PUMP_DESCRIPTIONS:
            vc = is_valid(pj, pump)
            mark = 'OK' if vc.is_valid else 'BAIL'
            reason = '' if vc.is_valid else vc.reasons[0]
            print(f"{pname:<22} {pump.name:<48} {mark:<6} {reason}")
    print()
    print("Interpretation: any row marked BAIL would cause AAPS' processChangedProfileStore")
    print("to silently return at line 792 (V1) / 718 (V3) — no log, no NS upload, no notification.")
    print("Profile-switch sync is unaffected (no allProfilesValid gate), so treatments still flow.")


if __name__ == '__main__':
    main()
