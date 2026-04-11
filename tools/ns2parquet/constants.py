"""
constants.py — Shared constants for the ns2parquet pipeline.

Single source of truth for conversion factors and mappings used across
normalize.py, grid.py, odc_loader.py, and tests.
"""

import numpy as np


# Nightscout canonical mmol/L → mg/dL conversion factor.
# Source: externals/cgm-remote-monitor/lib/constants.json
MMOLL_TO_MGDL = 18.01559

# CGM trend direction → ordinal mapping.
# Covers Dexcom, Medtronic, and Libre direction strings.
DIRECTION_MAP = {
    'DoubleUp': 2.0, 'SingleUp': 1.0, 'FortyFiveUp': 0.5,
    'Flat': 0.0,
    'FortyFiveDown': -0.5, 'SingleDown': -1.0, 'DoubleDown': -2.0,
    'NOT COMPUTABLE': np.nan, 'RATE OUT OF RANGE': np.nan,
    'NONE': np.nan, 'None': np.nan, '': np.nan,
}


def normalize_timezone(tz_str: str) -> str:
    """Normalize Nightscout timezone (ETC/GMT+7 → Etc/GMT+7).

    Handles the common Nightscout quirk where timezone strings use
    uppercase 'ETC/' prefix instead of the IANA-standard 'Etc/'.
    Falls back to 'UTC' for empty/None input.
    """
    if not tz_str:
        return 'UTC'
    if tz_str.upper().startswith('ETC/'):
        return 'Etc/' + tz_str[4:]
    return tz_str
