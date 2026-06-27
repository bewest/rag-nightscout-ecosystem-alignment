from __future__ import annotations

import numpy as np

from tools.cgmencode.production.hybrid_meal_support import (
    annotate_meals_with_hybrid_support,
    hybrid_support_at,
)
from tools.cgmencode.production.types import DetectedMeal, MealWindow, MetabolicState


def _metabolic(n: int) -> MetabolicState:
    supply = np.ones(n)
    demand = np.ones(n) * 0.5
    return MetabolicState(
        supply=supply,
        demand=demand,
        hepatic=np.zeros(n),
        carb_supply=np.zeros(n),
        net_flux=supply - demand,
        residual=np.zeros(n),
    )


def test_hybrid_support_shape():
    n = 200
    glucose = np.ones(n) * 120
    glucose[80:120] += np.linspace(0, 45, 40)
    support = hybrid_support_at(
        119,
        glucose=glucose,
        metabolic=_metabolic(n),
        bolus=np.zeros(n),
        iob=np.zeros(n),
        basal_rate=np.ones(n) * 0.8,
    )
    assert 'hybrid_score' in support
    assert support['experimental'] is True
    assert support['support_level'] in {'weak', 'moderate', 'strong'}


def test_annotate_detected_meals_metadata():
    meal = DetectedMeal(
        index=119,
        timestamp_ms=1,
        window=MealWindow.LUNCH,
        estimated_carbs_g=40,
        announced=False,
        residual_integral=10,
        confidence=0.8,
        hour_of_day=12,
    )
    meals = annotate_meals_with_hybrid_support(
        [meal],
        glucose=np.ones(200) * 120,
        metabolic=_metabolic(200),
    )
    assert 'hybrid_meal_support' in meals[0].metadata
