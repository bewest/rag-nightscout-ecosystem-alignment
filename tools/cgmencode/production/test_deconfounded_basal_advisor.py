from __future__ import annotations

import numpy as np

from cgmencode.production.advisor._basal_advisors import (
    advise_deconfounded_basal_blocks,
)
from cgmencode.production.types import PatientProfile


def _profile() -> PatientProfile:
    return PatientProfile(
        isf_schedule=[{"time": "00:00", "value": 40.0}],
        cr_schedule=[{"time": "00:00", "value": 10.0}],
        basal_schedule=[{"time": "00:00", "value": 1.0}],
    )


def test_deconfounded_basal_advisor_emits_safe_morning_block():
    n = 288 * 21
    hours = np.tile(np.arange(288) / 12.0, 21)
    glucose = np.full(n, 125.0)
    morning = (hours >= 6.0) & (hours < 12.0)
    glucose[morning] = 155.0
    actual_basal = np.full(n, 1.0)
    actual_basal[morning] = 1.35

    recs = advise_deconfounded_basal_blocks(
        glucose,
        hours,
        _profile(),
        actual_basal=actual_basal,
        cob=np.zeros(n),
        bolus=np.zeros(n),
        days_of_data=21.0,
    )

    assert len(recs) == 1
    assert recs[0].affected_hours == (6.0, 12.0)
    assert recs[0].confidence >= 0.5


def test_deconfounded_basal_advisor_blocks_high_tbr_period():
    n = 288 * 21
    hours = np.tile(np.arange(288) / 12.0, 21)
    glucose = np.full(n, 125.0)
    morning = (hours >= 6.0) & (hours < 12.0)
    glucose[morning] = 155.0
    glucose[np.where(morning)[0][::10]] = 65.0
    actual_basal = np.full(n, 1.0)
    actual_basal[morning] = 1.35

    recs = advise_deconfounded_basal_blocks(
        glucose,
        hours,
        _profile(),
        actual_basal=actual_basal,
        cob=np.zeros(n),
        bolus=np.zeros(n),
        days_of_data=21.0,
    )

    assert recs == []
