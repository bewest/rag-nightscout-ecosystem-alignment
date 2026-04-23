# BabelBetes Multi-Factor Data Extraction Pattern

**Purpose**: Document how BabelBetes standardizes multi-source clinical diabetes data and how this pattern informs multifactored FactsLoader design in the AID audition system.

---

## Overview

BabelBetes provides a data standardization toolkit for 9 clinical trial datasets (~500,000 subject-days of paired CGM, basal, bolus). Its core insight is **factor-aware extraction**: complex real-world signals (insulin delivery, CGM artifacts, closed-loop modes) are decomposed into independent factors, reconciled at extraction time, and validated against strict schemas.

This directly parallels our multifactored phenotype synthesis (EXP-2886: stack × brake × counter-reg, all orthogonal |ρ|<0.32).

---

## Multi-Factor Extraction Pattern

### StudyDataset Base Class

```python
class StudyDataset:
    """Abstract base for clinical datasets."""
    
    @property
    def bolus(self) -> DataFrame:
        """Bolus event history (validated, cached)."""
        df = self._extract_bolus_event_history()
        BOLUS_SCHEMA.validate(df)  # Pandera strict schema
        return df
    
    @property
    def basal(self) -> DataFrame:
        """Basal rate events (validated, cached)."""
        df = self._extract_basal_event_history()
        BASAL_SCHEMA.validate(df)
        return df
    
    @property
    def cgm(self) -> DataFrame:
        """CGM measurements (validated, cached)."""
        df = self._extract_cgm_history()
        CGM_SCHEMA.validate(df)
        return df
```

**Key Pattern**: Public properties validate + cache; private `_extract_*` methods implement.

### Flair Study: 4-Factor Basal Reconciliation

The Flair study (Phase 2 trial with Tandem t:slim X2 with Control-IQ) has **complex basal measurement**:

| Factor | Source Field | Pattern |
|--------|-------------|---------|
| **F1: Standard Basal** | `BasalRt` | Scheduled rate from pump profile |
| **F2: Temp Basal** | `TempBasalAmt`, `TempBasalType`, `TempBasalDur` | Percent or absolute override |
| **F3: Suspension** | `Suspend` event + `DateTime` | Periods where basal is zeroed |
| **F4: Closed-Loop** | `AutoModeStatus` | Control-IQ on/off toggle |

**Extraction Algorithm** (cumulative application):

```python
def _extract_basal_event_history(self):
    # Start with pump data
    df = self._df_pump.copy()
    
    # Step 1: Merge temp basals into basal rates
    # - If TempBasalType='Percent': multiply BasalRt * (TempBasalAmt/100)
    # - If TempBasalType='Rate': override BasalRt with TempBasalAmt
    df['basal_merged'] = df.groupby('PtID').apply(
        merge_basal_and_temp_basal
    ).droplevel(0)
    
    # Step 2: Apply closed-loop suspension
    # - When AutoModeStatus=True, set basal to 0.0
    df['basal_cl'] = df['basal_merged'].copy()
    df.loc[df.AutoModeStatus == True, 'basal_cl'] = 0.0
    
    # Step 3: Apply pump suspension periods
    # - Find Suspend event periods
    # - Zero out basal rates during suspend
    # - Restore to previous known basal at suspend end
    df['basal_final'] = df.groupby('PtID').apply(
        lambda x: disable_basal(
            x, 
            find_periods(x, 'Suspend', 'DateTime', ...),
            'basal_cl'
        )
    ).droplevel(0)
    
    return df[['patient_id', 'datetime', 'basal_final']].rename(
        columns={'basal_final': 'basal_rate'}
    )
```

---

## Connection to FactsLoader Design

### Orthogonal Signals Pattern

**EXP-2886 phenotype result**: 3 orthogonal axes (stack, brake, counter-reg) all |ρ|<0.32.

**FactsLoader approach**: Keep orthogonal signals **separate**, not composited.

**Flair parallel**: Basal extraction keeps factors distinct until final validation:
- Temp basal adjustments applied sequentially (not blended)
- Closed-loop suspension applied *after* temp merging (order matters)
- Each factor independently documented

### Staged Validation

**BabelBetes**: `_extract_*` → `validate()` → `@cached_property`

**Our FactsLoader pattern**:
```python
class SimpsonFactsLoader:
    def _load(self) -> dict[str, SimpsonAuditionFacts]:
        # Load 3 independent parquets
        flag_by_pid = load_simpson_parquet()      # EXP-2853
        stab_by_pid = load_stability_parquet()    # EXP-2856
        psim_by_pid = load_bootstrap_parquet()    # EXP-2859
        
        # Validate: all_pids must exist in at least one source
        all_pids = set(flag_by_pid) | set(stab_by_pid) | set(psim_by_pid)
        
        # Merge orthogonal facts
        for pid in all_pids:
            idx[pid] = SimpsonAuditionFacts(
                simpson_paradox=flag_by_pid.get(pid),
                stability_frac=stab_by_pid.get(pid),
                p_simpson=psim_by_pid.get(pid),
            )
```

**Parallel**: Multiple independent sources (research experiments) → validated merge → cacheable lookup.

---

## Design Principles

### 1. **Factor Isolation**
- Extract factors independently
- Apply in documented order (state machine)
- Validate output, not intermediate steps

### 2. **Orthogonality**
- If components |ρ|<0.32, keep separate
- Document assumptions about independence
- Flag when adding new factors might break orthogonality

### 3. **Lazy Evaluation with Caching**
- Load raw data on first access
- Cache in memory (dict or `@cached_property`)
- Provide `unload_raw()` for memory cleanup

### 4. **Graceful Degradation**
- Return `None`-valued records for unknown entities
- Allow callers to fall back to alternatives
- Don't crash on missing data sources

### 5. **Testability**
- Separate extraction logic from validation
- Use pandera schemas for strict output contracts
- Mock raw data for unit tests

---

## Application to AID Treatment Sync

**Current Challenge**: Treatments (bolus, carbs, basal adjustments) sync across xDrip+→AAPS→Nightscout→Loop, with deduplication conflicts.

**Multifactor Reconciliation (Flair Pattern)**:

| Factor | Source | Logic |
|--------|--------|-------|
| **F1: Event Time** | `datetime` | Primary identity |
| **F2: Sync ID** | `identifier`/`syncIdentifier` | Secondary (cross-system link) |
| **F3: Event Type** | `eventType` | Category (bolus, temp basal, carbs) |
| **F4: Confidence** | Metadata (source, upload order) | Tie-breaker for conflicts |

**Extraction algorithm** (similar to Flair basal):
1. Collect raw treatment events from each source (xDrip+, AAPS, Nightscout, Loop)
2. Merge by sync identity if available (EXP-2887: `interfaceIDs.nightscoutId`)
3. Apply deduplication window (same time ±60s) with tie-breaker (latest upload wins)
4. Validate against treatment schema (required fields, type constraints)
5. Return deduplicated canonical treatment records

**FactsLoader for treatment dedup**:
```python
class TreatmentDeduplicationFactsLoader:
    """Load per-patient treatment sync dedup strategy from EXP-2892."""
    
    def __init__(self, dedup_path=DEFAULT_DEDUP_PARQUET):
        self._dedup_path = dedup_path
        self._index: Optional[dict[str, TreatmentDedupFacts]] = None
    
    def lookup(self, patient_id: str) -> TreatmentDedupFacts:
        """Get dedup window, tie-breaker priority, etc. for this patient."""
        if self._index is None:
            self._index = self._load()
        return self._index.get(
            patient_id,
            TreatmentDedupFacts(
                dedup_window_sec=60,
                tie_breaker='latest_upload',
                priority_sources=['AAPS', 'xDripPlus', 'Loop'],
            ),
        )
```

---

## Implementation Roadmap

### Phase 1: Documentation (Current)
- [x] Add babelbetes to workspace.lock.json
- [x] Document BabelBetes multi-factor pattern
- [x] Create FactsLoader template for multifactored signals

### Phase 2: Cross-Study Phenotype Synthesis
- [ ] Load FLAIR (500+ subject-days) via BabelBetes
- [ ] Load LOOP study data via BabelBetes
- [ ] Compute per-patient envelope + stack + brake across both cohorts
- [ ] Compare Loop vs FLAIR oref0-like controller (if present)
- [ ] Create `EnvelopePhenotypeFactsLoader` for cross-study generalization

### Phase 3: Treatment Sync Reconciliation
- [ ] Implement `TreatmentDeduplicationFactsLoader` 
- [ ] Run EXP-2892: test dedup strategies on real Nightscout traffic
- [ ] Integrate into audition pipeline (stage: before phenotype flagging)

### Phase 4: Validation & Testing
- [ ] Add pandera schemas to FactsLoader outputs
- [ ] Test graceful degradation (missing patients, incomplete data)
- [ ] Measure impact: dedup accuracy, cross-study phenotype stability

---

## References

- **BabelBetes**: `externals/babelbetes/babelbetes/studies/`
- **Flair Study**: `externals/babelbetes/babelbetes/studies/flair.py`
- **FactsLoader Examples**: `tools/cgmencode/production/*_facts_loader.py`
- **EXP-2886**: Phenotype synthesis (stack, brake, counter-reg orthogonal)
- **EXP-2887**: HAAF mediation (treatment sync identity validation)
- **EXP-2873**: NaN propagation bug fix (data hygiene lesson for FactsLoader)
