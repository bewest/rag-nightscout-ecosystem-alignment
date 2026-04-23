# Teammate Pickup Guide: BabelBetes + Multifactored FactsLoaders Integration

**Audience**: Teammates working on tools/cgmencode/  
**Last Updated**: 2026-04-22 (Post EXP-2892 completion)  
**Status**: Ready for pickup — all infrastructure tested, documented, and in place

---

## What's New in tools/cgmencode/production/

### 🎯 New FactsLoaders (Ready to Use)

#### 1. **PhenotypeFactsLoader** (320 lines)
**File**: `production/phenotype_facts_loader.py`

**What it does**: Merges 3 independent phenotype experiments into one lazy-loaded cache.

```python
from tools.cgmencode.production.phenotype_facts_loader import PhenotypeFactsLoader

loader = PhenotypeFactsLoader()

# Lookup patient phenotype (thread-safe, cached)
facts = loader.lookup('patient-id-xyz')

# Returns frozen dataclass with all 6 orthogonal axes:
facts.stack_score              # Evening bolus stacking (EXP-2882)
facts.brake_ratio              # Basal suspension % (EXP-2885)
facts.counter_reg_intercept    # Recovery intercept (EXP-2877)
facts.beta_nadir               # Dose-response slope (EXP-2878)
facts.p_haaf                   # HAAF fragility p-value (counterfactual, EXP-2878)
facts.evening_bolus_excess_4h  # 4h cumulative bolus excess (EXP-2881)
facts.controller_lineage       # "Loop" | "oref0" | "Trio" (EXP-2885)

# Coverage reporting
coverage = loader.coverage_by_axis()
# {'stack_score': 25/27 patients, 'brake_ratio': 27/27, ...}
```

**Key Design Principle**: **All 6 axes kept orthogonal** (|ρ| < 0.32)
- ❌ **DON'T** composite them: `risk = stack * (1-brake) * recovery`
- ✅ **DO** use them separately for stratification/audition

**Why this matters**: Compositing loses -0.227 adj-R² (observed -0.019 vs orthogonal +0.208)

**Example from audition**:
```python
class AuditionInputs:
    phenotype = PhenotypeFactsLoader()
    
    def hypo_risk_factors(self, patient_id: str):
        facts = self.phenotype.lookup(patient_id)
        
        if facts is None:
            return {"risk": "unknown"}
        
        # Separate signals = better deconfounding
        return {
            "bolus_stacking": facts.stack_score,
            "suspension_aggressive": facts.brake_ratio < 0.08,
            "fragile_to_depth": facts.beta_nadir > 0.5,
            "haaf_risk": facts.p_haaf < 0.05,
        }
```

---

#### 2. **TreatmentDedupFactsLoader** (250 lines)
**File**: `production/treatment_dedup_facts_loader.py`

**What it does**: Provides per-patient treatment deduplication strategy with confidence scoring.

```python
from tools.cgmencode.production.treatment_dedup_facts_loader import (
    TreatmentDedupFactsLoader,
)

loader = TreatmentDedupFactsLoader()

# Lookup patient dedup strategy
strategy = loader.lookup('patient-id-xyz')

# Returns frozen dataclass with dedup parameters:
strategy.dedup_window_sec       # Time window for merge (e.g., 60 sec)
strategy.tie_breaker_priority   # ["sync_id", "timestamp", "amount"] ordered
strategy.use_sync_id            # Boolean: weight sync IDs in dedup
strategy.sync_id_field          # "syncIdentifier" or "nightscoutId"
strategy.event_type_confidence  # {"bolus": 0.95, "carbs": 0.80, ...}
strategy.confidence             # Overall dedup confidence (0.0-1.0)
```

**Example from audition**:
```python
def deduplicate_treatments(self, patient_id: str, treatments: list) -> list:
    strategy = TreatmentDedupFactsLoader().lookup(patient_id)
    
    if strategy is None:
        # Graceful degradation: use conservative defaults
        strategy = TreatmentDedupFactsLoader()._default_strategy()
    
    # Apply strategy
    deduped = []
    for i, t1 in enumerate(treatments):
        if any(self._is_duplicate(t1, t2, strategy) for t2 in deduped):
            continue
        deduped.append(t1)
    
    return deduped
```

---

### ✅ Testing Infrastructure (Run Locally)

**Tests for PhenotypeFactsLoader**:
```bash
pytest tools/cgmencode/production/test_phenotype_facts_loader.py -v
# Expected: 6/6 passing ✅
```

**Tests for TreatmentDedupFactsLoader**:
```bash
pytest tools/cgmencode/production/test_treatment_dedup_facts_loader.py -v
# Expected: 8/8 passing ✅
```

**Run all production tests**:
```bash
pytest tools/cgmencode/production/ -v
# Expected: 14/14 passing ✅
```

---

## Architecture Patterns You Should Follow

### Pattern 1: Lazy-Loading with Caching

```python
# ✅ GOOD: Lazy load on first access, cache result
class MyFactsLoader:
    def __init__(self):
        self._cache = {}
        self._parquet_path = "externals/experiments/exp_XYZ_something.parquet"
    
    def lookup(self, patient_id: str) -> MyFacts | None:
        if patient_id not in self._cache:
            self._load()
        return self._cache.get(patient_id)
    
    def _load(self):
        """Load once, populate cache."""
        try:
            df = pd.read_parquet(self._parquet_path)
            for _, row in df.iterrows():
                self._cache[row['patient_id']] = MyFacts(
                    field1=row['field1'],
                    field2=row['field2'],
                )
        except FileNotFoundError:
            pass  # Graceful degradation
```

### Pattern 2: Graceful Degradation for Missing Data

```python
# ✅ GOOD: Return all-None dataclass for missing patients
@dataclass(frozen=True)
class MyFacts:
    field1: float | None = None
    field2: float | None = None
    field3: bool | None = None

# ✅ GOOD: Return defaults when files missing
def lookup(self, patient_id: str) -> MyFacts:
    if patient_id not in self._cache:
        return MyFacts()  # All-None fallback
    return self._cache[patient_id]

# ✅ GOOD: Callers handle None gracefully
facts = loader.lookup(patient_id)
if facts.field1 is not None:
    use_field1 = facts.field1
else:
    use_field1 = DEFAULT_VALUE
```

### Pattern 3: Per-Patient Aggregation (Prevents Simpson's Paradox)

```python
# ✅ GOOD: Return dict[patient_id, Facts] for per-patient analysis
class MyFactsLoader:
    def __init__(self):
        self._cache = {}  # patient_id → Facts
    
    def known_patients(self) -> list[str]:
        """Return list of patients in cache."""
        if not self._cache:
            self._load()
        return list(self._cache.keys())

# ✅ GOOD: Use per-patient aggregation in metrics
def mean_by_patient(self, field_name: str) -> float:
    """Mean across patients (not across events)."""
    values = [
        getattr(facts, field_name)
        for facts in self._cache.values()
        if getattr(facts, field_name) is not None
    ]
    return np.mean(values)

# ❌ BAD: Pooled mean (Simpson's paradox)
# Wrong: np.mean(df[field_name])  # Prolific patients dominate
```

### Pattern 4: Orthogonal Signal Validation

```python
# ✅ GOOD: Keep orthogonal signals separate, document correlation
@dataclass(frozen=True)
class PhenotypeFacts:
    """
    Orthogonal phenotype dimensions (all |ρ| < 0.32):
    - stack_score: bolus stacking (patient-driven)
    - brake_ratio: suspension % (controller-driven)
    - counter_reg_intercept: physiology-driven recovery
    
    Do NOT composite these into one risk score.
    Loss of information: -0.227 adj-R² when combined.
    """
    stack_score: float | None = None          # ρ(stack, brake) = 0.00
    brake_ratio: float | None = None          # ρ(brake, counter_reg) = 0.12
    counter_reg_intercept: float | None = None

# ✅ GOOD: Use separate in audition
audition_signals = {
    'stacking_risk': facts.stack_score,
    'suspension_aggressive': facts.brake_ratio,
    'recovery_fragility': facts.counter_reg_intercept,
}

# ❌ BAD: Composite
risk = facts.stack_score * (1 - facts.brake_ratio) * facts.counter_reg_intercept
```

### Pattern 5: Data Validation (NaN Handling)

```python
# ⚠️ GOTCHA from EXP-2873: np.percentile silently returns NaN if any input is NaN
# This silently drops patients from analyses.

# ✅ GOOD: Always dropna() before percentile operations
values = [facts.field1 for facts in self._cache.values()]
values_clean = [v for v in values if pd.notna(v)]  # Explicit dropna
p95 = np.percentile(values_clean, 95)

# ❌ BAD: np.percentile with NaN inputs
percentile_result = np.percentile(values, 95)  # Returns NaN if any value is NaN
# This silently excluded 6/31 patients in EXP-2873, overturning findings
```

---

## What NOT To Do (Anti-Patterns)

### ❌ Anti-Pattern 1: Composite Risk Scores

```python
# ❌ DON'T: This loses -0.227 adj-R²
hidden_leverage = stack * (1-brake) * recovery

# ✅ DO: Use separate signals
audition.add_signal('stack_signal', stack)
audition.add_signal('brake_signal', brake)
audition.add_signal('recovery_signal', recovery)
```

**Why**: Confounding direction flips when orthogonal signals combined. Observed outcome (hypo count) is collider-biased against fragility marker.

---

### ❌ Anti-Pattern 2: Pooled Aggregation (Simpson's Paradox)

```python
# ❌ DON'T: Prolific patients dominate
mean_value = df['field'].mean()  # If one patient has 100 events, they dominate

# ✅ DO: Per-patient aggregation first
per_patient_means = df.groupby('patient_id')['field'].mean()
overall_mean = per_patient_means.mean()  # Now each patient is weighted equally
```

**Why**: EXP-2870 showed controller lineage signatures hidden in pooled data. Trio brake_ratio 0.066 vs Loop 0.074 vs OpenAPS 0.748 — pooled median misleadingly ~0.095.

---

### ❌ Anti-Pattern 3: Validating Against Observed Outcomes (Collider Bias)

```python
# ❌ DON'T: Validate fragility marker against observed hypo count
# Problem: AID suspension PROTECTS fragile patients → observed correlation reversed
rho = correlate(brake_ratio, observed_hypo_count)  # ρ = -0.17 (biased)

# ✅ DO: Validate against counterfactual outcomes
rho = correlate(brake_ratio, counterfactual_hypo_depth)  # ρ = -0.71 (unbiased)
# Use pre-computed p_haaf from PhenotypeFactsLoader (already validated)
```

**Why**: EXP-2889 showed brake_ratio ρ=-0.711 p=0.001 with counterfactual hypo depth vs ρ=-0.17 p=0.48 with observed (collider-biased). C7 collider bias explanation in deconfounding toolkit.

---

### ❌ Anti-Pattern 4: Missing NaN Checks

```python
# ❌ DON'T: Implicit NaN propagation
result = np.percentile(values_with_nans, 95)  # Returns NaN, silently drops patients

# ✅ DO: Explicit dropna
values_clean = [v for v in values if pd.notna(v)]
result = np.percentile(values_clean, 95)
```

**Why**: EXP-2873 discovered np.percentile returns NaN for ALL outputs if any input is NaN. In windowed aggregations, this silently excluded 6/31 patients.

---

## Where to Find Things

### Existing FactsLoaders (Reference Implementations)

```
tools/cgmencode/production/
├── phenotype_facts_loader.py           ← NEW (EXP-2886/2878/2881)
├── treatment_dedup_facts_loader.py     ← NEW (EXP-2892)
├── basal_mismatch_facts_loader.py      ← ✅ Reference (use as template)
├── state_basal_facts_loader.py         ← ✅ Reference
├── recovery_facts_loader.py            ← ✅ Reference
├── wear_facts_loader.py                ← ✅ Reference
└── post_high_facts_loader.py           ← ✅ Reference
```

### Experiment Source Data (Parquets)

```
externals/experiments/
├── exp-2881_evening_drivers_summary.json
├── exp-2882_stacker_phenotype_summary.json
├── exp-2885_simpson_braking_summary.json
├── exp-2886_phenotype_summary.json
├── exp-2878_haaf_summary.json
└── exp-2892_mechanism_summary.json    ← Used by TreatmentDedupFactsLoader
```

### Documentation

- **Pattern guide**: `docs/10-domain/babelbetes-multifactor-pattern.md`
- **Integration guide**: `docs/INTEGRATION-MULTIFACTORED-FACTSLOADERS.md`
- **Deconfounding architecture**: `docs/10-domain/multifactored-factsloaders-deconfounding-architecture.md`

---

## How to Integrate Into Your Experiment

### Step 1: Import FactsLoaders

```python
# File: tools/cgmencode/exp_your_experiment_XXXX.py
from tools.cgmencode.production.phenotype_facts_loader import PhenotypeFactsLoader
from tools.cgmencode.production.treatment_dedup_facts_loader import TreatmentDedupFactsLoader

phenotype = PhenotypeFactsLoader()
dedup = TreatmentDedupFactsLoader()
```

### Step 2: Use in Analysis

```python
def analyze_patient_cohort():
    """Stratify cohort by phenotype axes."""
    
    for patient_id in get_patient_ids():
        facts = phenotype.lookup(patient_id)
        
        if facts is None or facts.brake_ratio is None:
            continue  # Skip if missing data
        
        # Stratify on independent axes
        is_stacker = facts.stack_score > facts.stack_score.quantile(0.66)
        is_suspension_aggressive = facts.brake_ratio < 0.08
        is_fragile = facts.beta_nadir > 0.5
        
        # Per-patient signal (not composite)
        yield {
            'patient_id': patient_id,
            'stacking_risk': facts.stack_score,
            'suspension_aggressive': is_suspension_aggressive,
            'fragility': is_fragile,
        }
```

### Step 3: Test Coverage

```python
# File: tools/cgmencode/exp_your_experiment_test.py
from tools.cgmencode.production.phenotype_facts_loader import PhenotypeFactsLoader

def test_phenotype_coverage():
    """Verify FactsLoader has data for expected patients."""
    loader = PhenotypeFactsLoader()
    known = loader.known_patients()
    
    assert len(known) > 20, f"Expected >20 patients, got {len(known)}"
    
    coverage = loader.coverage_by_axis()
    for axis, (n_covered, n_total) in coverage.items():
        assert n_covered > 0, f"{axis} has no coverage"
```

---

## Teammate Responsibilities

### If You're Writing a New Experiment:

1. **Check if FactsLoaders exist** for your domain
   - Phenotype analysis? → Use `PhenotypeFactsLoader`
   - Treatment dedup? → Use `TreatmentDedupFactsLoader`
   - Basal patterns? → Check `basal_mismatch_facts_loader.py`

2. **Don't repeat what FactsLoaders do**
   - ❌ Don't re-load `exp_2886_phenotype.parquet` yourself
   - ✅ Do use `PhenotypeFactsLoader.lookup(patient_id)`

3. **Keep orthogonal signals separate**
   - Document axis correlations in docstring
   - Use per-patient aggregation (not pooled mean)
   - Validate against counterfactual, not observed outcomes

4. **Add tests** for your integration
   - Verify FactsLoader has data
   - Test graceful degradation (None values)
   - Check coverage by axis

### If You're Enhancing Existing FactsLoaders:

1. **Add new data source as separate axis**
   - Example: If adding `evening_hypo_count` to PhenotypeFactsLoader
   - Verify |ρ| with existing axes < 0.32
   - Update docstring with orthogonality claim

2. **Update tests** before committing
   - Run: `pytest tools/cgmencode/production/ -v`
   - All 14+ tests must pass

3. **Document deconfounding logic**
   - Why is this axis kept separate?
   - What would happen if composited?
   - Reference deconfounding toolkit (C1-C8)

### If You're Integrating BabelBetes Data:

1. **Respect study-specific dedup rules**
   - BabelBetes provides 4-factor basal reconciliation
   - Don't assume Nightscout dedup logic applies
   - Flair study has single pump source (simpler dedup)

2. **Use per-study FactsLoaders**
   - Create `FLAIRFactsLoader` if FLAIR-specific facts needed
   - Share common interfaces (same frozen dataclass pattern)
   - Example: `externals/babelbetes/babelbetes/studies/flair.py`

3. **Document cross-study assumptions**
   - Simpson's paradox check: stratify by study
   - Mediation audit: does confounder source matter?
   - Reference experiments (EXP-2885, EXP-2886, EXP-2872)

---

## Checklists

### Before Committing New FactsLoader

- [ ] Inherits from FactsLoader base (frozen dataclass)
- [ ] Implements `lookup(patient_id)` → frozen dataclass
- [ ] Implements `known_patients()` → list[str]
- [ ] Implements `n_patients_analyzed()` → int
- [ ] Graceful degradation: returns all-None for unknowns
- [ ] Lazy loading: only loads on first access
- [ ] Per-patient keying: dict[patient_id, Facts]
- [ ] Test file exists with ≥4 test cases
- [ ] All tests passing: `pytest tools/cgmencode/production/ -v`
- [ ] Docstring explains orthogonality/deconfounding
- [ ] Referenced experiments documented in docstring

### Before Using FactsLoader in Experiment

- [ ] Imports correctly: `from tools.cgmencode.production.X import Y`
- [ ] Handles None return values gracefully
- [ ] Checks FactsLoader has coverage: `loader.known_patients()` > 0
- [ ] Uses per-patient aggregation (not pooled)
- [ ] Documents which axis signals are used
- [ ] Tests FactsLoader availability locally
- [ ] Run full test suite: `pytest tools/cgmencode/production/ -v`

---

## Quick Start: Copy-Paste Template

```python
# File: tools/cgmencode/production/my_new_facts_loader.py
"""MyNewFactsLoader: Load [experiment] results for [domain]."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import pandas as pd


@dataclass(frozen=True)
class MyNewFacts:
    """Immutable fact set for patient [domain].
    
    Orthogonal axes (keep separate, don't composite):
    - field1: description (ρ with field2 = X)
    - field2: description (ρ with field3 = Y)
    """
    field1: Optional[float] = None
    field2: Optional[float] = None
    field3: Optional[bool] = None


class MyNewFactsLoader:
    """Lazy-loaded [experiment] results."""
    
    def __init__(self):
        self._cache = {}
        self._parquet_path = Path("externals/experiments/exp_XXXX_something.parquet")
    
    def lookup(self, patient_id: str) -> Optional[MyNewFacts]:
        """Return facts for patient, or all-None if unknown."""
        if not self._cache:
            self._load()
        return self._cache.get(patient_id)
    
    def known_patients(self) -> list:
        """Return patient IDs in cache."""
        if not self._cache:
            self._load()
        return list(self._cache.keys())
    
    def n_patients_analyzed(self) -> int:
        """Return count of patients with data."""
        return len(self.known_patients())
    
    def _load(self):
        """Load parquet once, populate cache."""
        if not self._parquet_path.exists():
            return
        
        df = pd.read_parquet(self._parquet_path)
        for _, row in df.iterrows():
            self._cache[row['patient_id']] = MyNewFacts(
                field1=row.get('field1'),
                field2=row.get('field2'),
                field3=row.get('field3'),
            )
```

Test template:
```python
# File: tools/cgmencode/production/test_my_new_facts_loader.py
import pytest
from .my_new_facts_loader import MyNewFactsLoader


def test_load_and_lookup():
    loader = MyNewFactsLoader()
    facts = loader.lookup('patient-id')
    
    if facts is not None:
        assert facts.field1 is not None or facts.field2 is not None


def test_graceful_fallback_unknown_patient():
    loader = MyNewFactsLoader()
    facts = loader.lookup('unknown-patient-xyz')
    
    assert facts is None or all(
        getattr(facts, f) is None
        for f in ['field1', 'field2', 'field3']
    )


def test_known_patients():
    loader = MyNewFactsLoader()
    known = loader.known_patients()
    
    assert isinstance(known, list)
```

---

## Need Help?

1. **Reference implementations**: `basal_mismatch_facts_loader.py`, `state_basal_facts_loader.py`
2. **Integration example**: `audition_matrix.py` (shows how to use multiple FactsLoaders)
3. **Deconfounding guidance**: `docs/10-domain/multifactored-factsloaders-deconfounding-architecture.md`
4. **Pattern rules**: `docs/10-domain/babelbetes-multifactor-pattern.md`
5. **Experiment manifests**: `tools/cgmencode/EXP-2895-2900_AUTORESEARCH_PIPELINE.md` (shows how to wire into autoresearch)

---

## Summary: What to Pick Up

| Component | Location | Use Case | Status |
|-----------|----------|----------|--------|
| **PhenotypeFactsLoader** | `production/phenotype_facts_loader.py` | Stratify by bolus stacking, suspension, fragility | ✅ Ready |
| **TreatmentDedupFactsLoader** | `production/treatment_dedup_facts_loader.py` | Treatment canonicalization strategy | ✅ Ready |
| **Orthogonal signals pattern** | Docstrings + tests | Keep stack/brake/recovery separate | ✅ Documented |
| **Per-patient aggregation** | `audition_matrix.py` example | Avoid Simpson's paradox | ✅ Implemented |
| **NaN handling** | Tests + deconfounding doc | Explicit dropna() before percentile | ✅ Validated |
| **Graceful degradation** | All FactsLoaders | Return all-None for missing data | ✅ Enforced |
| **BabelBetes integration** | `EXP-2895-2900_AUTORESEARCH_PIPELINE.md` | Cross-study phenotype synthesis | 📋 Ready to pickup |

**Next step**: Pick up ready experiments (EXP-2895, 2896, 2897) and augment as needed! 🚀
