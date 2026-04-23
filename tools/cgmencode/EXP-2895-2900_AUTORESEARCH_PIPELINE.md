# BabelBetes-Aware Autoresearch Experiment Pipeline

**Purpose**: Lay out experiment templates for concurrent autoresearch agents to pick up and augment. These experiments leverage multifactored FactsLoaders + BabelBetes for cross-study phenotype synthesis and deconfounding.

---

## Active Experiment Series

### Current (EXP-2880–2894): Evening Hypo Protection Mechanisms

**Status**: Completed EXP-2891 + EXP-2892 (mechanism signature by lineage)  
**Latest**: EXP-2893 (hyper-correction channels), EXP-2894 (SMB functional equivalence)

**Outputs cached in**: `externals/experiments/exp-28{80-94}_*.parquet`

**Autoresearch agents currently picking these up?**
- No active autoresearch agents listed in current process list
- Last overnight run: 2026-04-12 (EXP-2401/2421 training/validation)

---

## Ready-to-Pickup Experiments: BabelBetes Cross-Study Series

### EXP-2895: FLAIR vs Loop Cohort Basal Rate Envelope Comparison

**Scope**: Compare basal rate envelope patterns across two different study cohorts

**Trigger**: Any autoresearch agent monitoring `externals/experiments/`

**Experiment Template**:
```python
# File: tools/cgmencode/exp_cross_study_basal_2895.py
"""EXP-2895: Cross-cohort basal envelope via BabelBetes + FactsLoader.

Load FLAIR (Tandem + Control-IQ) and Loop study datasets via BabelBetes.
Compute per-patient basal envelope (BabelBetes 4-factor reconciliation).
Compare to audition cohort (EXP-2870) basal extraction patterns.

Expected: FLAIR closed-loop should show different suspension signature
than Loop open-loop users.
"""

from externals.babelbetes.babelbetes.studies.flair import Flair
from externals.babelbetes.babelbetes.studies.loop import Loop
from tools.cgmencode.production.phenotype_facts_loader import PhenotypeFactsLoader

# Load FLAIR (Tandem t:slim X2 + Control-IQ)
flair = Flair(study_path="/data/FLAIR/raw")  # Placeholder path
flair_basal = flair.basal  # Canonical basal: standard+temp+suspend+closed-loop merged
flair_cgm = flair.cgm

# Compute envelope per FLAIR patient
for patient_id in flair_basal['patient_id'].unique():
    # Compute hourly basal envelope (same as EXP-2870)
    # Compare to Loop cohort envelope in audition inputs

# Stratify by:
#   - FLAIR (Tandem) vs Loop (iOS)
#   - Closed-loop mode (FLAIR: Control-IQ on/off; Loop: always on)
#   - Aggressiveness tercile (brake_ratio from EXP-2886)

# Output: exp_cross_study_basal_2895.parquet
#   Columns: patient_id, cohort (FLAIR|Loop), brake_ratio, 
#            envelope_1h_percentile, suspension_mean_duration, ...
```

**Deconfounding strategy**:
- BabelBetes 4-factor basal (indication-blind)
- Stratify on closed-loop mode (confounder source)
- Simpson decomposition: within-FLAIR vs across-cohort effects

**Expected output**: `externals/experiments/exp-2895_cross_cohort_basal.parquet`

**Pickup criteria**: 
- [ ] FLAIR data available at `/data/FLAIR/raw` (or path in config)
- [ ] BabelBetes bootstrapped (`make bootstrap`)
- [ ] PhenotypeFactsLoader working (14 tests pass)

---

### EXP-2896: FLAIR Evening Stacking Phenotype Generalization

**Scope**: Validate EXP-2882 (evening stacking) against FLAIR cohort

**Trigger**: After EXP-2895 completes

**Experiment Template**:
```python
# File: tools/cgmencode/exp_evening_stacking_flair_2896.py
"""EXP-2896: Evening bolus stacking phenotype (EXP-2882) in FLAIR cohort.

Load FLAIR treatments via BabelBetes. Compute evening_bolus_excess_4h
per FLAIR patient. Compare distribution to audition cohort (EXP-2881).

Expected: Evening stacking orthogonal to brake_ratio in both cohorts
(tests C6 Simpson decomposition generalization).
"""

from externals.babelbetes.babelbetes.studies.flair import Flair
from tools.cgmencode.production.phenotype_facts_loader import PhenotypeFactsLoader

flair = Flair(study_path="/data/FLAIR/raw")
flair_bolus = flair.bolus  # Canonical bolus: validated, deduped

# Replicate EXP-2881 methodology on FLAIR
# Compute stack_score per FLAIR patient (cumulative 4h bolus evening vs daily mean)

# Correlations:
# - stack_score vs brake_ratio in FLAIR (expect ρ≈0.00, like audition)
# - stack_score vs counter_reg_intercept (expect ρ≈-0.18)

# Output: exp_evening_stacking_flair_2896.parquet
#   Columns: patient_id, cohort (FLAIR|audition),
#            stack_score, evening_excess_4h, correlation_brake, ...

# Validation: Wilcoxon test for distribution equivalence
```

**Deconfounding strategy**:
- Staged dedup (BabelBetes study-specific dedup rules)
- Stratify on controller lineage (FLAIR: Tandem; audition: Loop/AAPS/Trio)
- Per-patient aggregation (avoids C5 sample dominance)

**Expected output**: `externals/experiments/exp-2896_evening_stacking_flair.parquet`

---

### EXP-2897: Multi-Study HAAF Fragility Validation

**Scope**: Validate EXP-2878 (HAAF β_nadir) against FLAIR counter-reg

**Trigger**: After EXP-2896 completes

**Experiment Template**:
```python
# File: tools/cgmencode/exp_haaf_flair_2897.py
"""EXP-2897: HAAF fragility marker validation across FLAIR + audition cohorts.

Load FLAIR + audition hypo events. Fit counter-regulation dose-response
(β_nadir) in both cohorts. Correlate with HAAF indicators.

Expected: β_nadir (sensitivity to hypo depth) is a conserved fragility
marker across studies (validates EXP-2878 in new cohort).
"""

from externals.babelbetes.babelbetes.studies.flair import Flair
from tools.cgmencode.production.phenotype_facts_loader import PhenotypeFactsLoader

flair = Flair(study_path="/data/FLAIR/raw")
flair_cgm = flair.cgm
flair_basal = flair.basal

# Replicate EXP-2877/2878 hypo detection + recovery estimation in FLAIR
# Extract rescue-free hypo events, fit BG recovery rate vs depth

# Comparison:
#   - FLAIR β_nadir distribution vs audition cohort
#   - Correlation with AID suspension frequency (indicator of HAAF pressure)
#   - Cross-controller β_nadir differences (Tandem vs Loop)

# Output: exp_haaf_flair_2897.parquet
#   Columns: patient_id, cohort, beta_nadir, recovery_intercept,
#            hypo_count, suspension_freq, haaf_p_value, ...
```

**Deconfounding strategy**:
- Counterfactual validation: use recovery-rate slope (not observed hypo count)
- Stratify on AID suspension mode (confounder source)
- Mediation audit: dose → fragility → hypo (validates causal chain)

**Expected output**: `externals/experiments/exp-2897_haaf_flair.parquet`

---

### EXP-2898: Treatment Sync Dedup Strategy Generalization

**Scope**: Validate TreatmentDedupFactsLoader strategy on FLAIR data

**Trigger**: When treatment dedup FactsLoader has real data

**Experiment Template**:
```python
# File: tools/cgmencode/exp_treatment_dedup_flair_2898.py
"""EXP-2898: Treatment dedup strategy (EXP-2892) on FLAIR cohort.

FLAIR data comes from single pump (Tandem). Validate dedup strategy
by simulating Nightscout sync (timestamp matching + sync ID merging).

Expected: FLAIR cohort should have lower dedup ambiguity (no cross-system
sync conflicts like xDrip+ ↔ AAPS ↔ Nightscout).
"""

from externals.babelbetes.babelbetes.studies.flair import Flair
from tools.cgmencode.production.treatment_dedup_facts_loader import TreatmentDedupFactsLoader

flair = Flair(study_path="/data/FLAIR/raw")
flair_bolus = flair.bolus

# Test dedup strategy on FLAIR bolus events
# Simulate: what if we applied audition dedup rules to single-source FLAIR data?

# Validation:
#   - Dedup confidence should be high (no cross-source conflicts)
#   - False-positive merge rate (same event deduplicated twice)
#   - False-negative miss rate (distinct events not merged)

# Output: exp_treatment_dedup_flair_2898.parquet
#   Columns: patient_id, dedup_window_sec, confidence,
#            false_pos_rate, false_neg_rate, ...
```

**Pickup criteria**:
- [ ] Treatment dedup FactsLoader has real data from EXP-2892
- [ ] FLAIR bolus data available

**Expected output**: `externals/experiments/exp-2898_treatment_dedup_flair.parquet`

---

## Experiment Orchestration Manifest

Create a manifest file that autoresearch agents can discover and pick up:

```yaml
# File: tools/cgmencode/exp_manifest_2895_2900.yaml
experiments:
  - id: 2895
    title: "Cross-cohort basal envelope (FLAIR vs Loop)"
    status: ready
    dependencies: []
    trigger: "manual or on-bootstrap"
    input_data: "/data/FLAIR/raw"
    output: "externals/experiments/exp_2895_cross_cohort_basal.parquet"
    facets:
      - deconfounding: "4-factor basal (indication-blind), Simpson by lineage"
      - validation: "Closed-loop mode stratification"
      - references: "EXP-2870, BabelBetes Flair.py"
    
  - id: 2896
    title: "Evening stacking phenotype (FLAIR validation)"
    status: ready
    dependencies: [2895]
    trigger: "after 2895 complete"
    output: "externals/experiments/exp_2896_evening_stacking_flair.parquet"
    facets:
      - orthogonality: "stack_score ⟂ brake_ratio (expect ρ≈0.00)"
      - validation: "Wilcoxon distribution equivalence"
      - references: "EXP-2881, EXP-2886"
    
  - id: 2897
    title: "HAAF fragility validation (cross-cohort)"
    status: ready
    dependencies: [2896]
    trigger: "after 2896 complete"
    output: "externals/experiments/exp_2897_haaf_flair.parquet"
    facets:
      - deconfounding: "Counterfactual validation (recovery slope, not observed hypo)"
      - validation: "Mediation audit for causal chain"
      - references: "EXP-2877, EXP-2878"
    
  - id: 2898
    title: "Treatment dedup strategy (FLAIR single-source validation)"
    status: blocked  # Waiting for EXP-2892 FactsLoader data
    dependencies: [treatment_dedup_facts_loader]
    output: "externals/experiments/exp_2898_treatment_dedup_flair.parquet"
    facets:
      - validation: "False-positive/negative rates on single-source data"
      - references: "EXP-2892, TreatmentDedupFactsLoader"
```

---

## How Autoresearch Agents Pick This Up

### Agent Discovery Pattern

```python
# File: tools/cgmencode/exp_autoresearch_manifest_loader.py
"""Auto-discovery of experiment manifests for concurrent agents."""

import yaml
from pathlib import Path

class ExperimentManifestLoader:
    """Load experiment pipeline from YAML manifest."""
    
    def __init__(self, manifest_path: Path = Path("tools/cgmencode/exp_manifest_*.yaml")):
        self.manifests = sorted(Path(".").glob(str(manifest_path)))
        self.experiments = {}
        self._load_all()
    
    def _load_all(self):
        for manifest_file in self.manifests:
            with open(manifest_file) as f:
                data = yaml.safe_load(f)
                for exp in data.get("experiments", []):
                    self.experiments[exp["id"]] = exp
    
    def ready_experiments(self) -> list:
        """Return experiments with status='ready' and no blocking dependencies."""
        ready = []
        for exp_id, exp in self.experiments.items():
            if exp["status"] != "ready":
                continue
            
            # Check if dependencies are available
            if self._deps_satisfied(exp.get("dependencies", [])):
                ready.append(exp)
        
        return ready
    
    def _deps_satisfied(self, deps: list) -> bool:
        """Check if all dependencies are met."""
        for dep in deps:
            if isinstance(dep, int):
                # Experiment ID dependency
                dep_exp = self.experiments.get(dep, {})
                if dep_exp.get("status") != "complete":
                    return False
            elif isinstance(dep, str):
                # Data file or FactsLoader dependency
                if dep == "treatment_dedup_facts_loader":
                    # Check if TreatmentDedupFactsLoader has data
                    from tools.cgmencode.production.treatment_dedup_facts_loader import (
                        TreatmentDedupFactsLoader,
                    )
                    loader = TreatmentDedupFactsLoader()
                    if loader.n_patients_analyzed() == 0:
                        return False
        
        return True
    
    def run_experiment(self, exp_id: int) -> dict:
        """Execute experiment and record results."""
        exp = self.experiments[exp_id]
        
        # Import and run experiment
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            f"exp_{exp_id}",
            Path("tools/cgmencode") / f"exp_{exp['title'].split()[0].lower()}_{exp_id}.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Run main()
        result = module.main()
        
        # Update status
        exp["status"] = "complete"
        exp["result_path"] = str(result.get("output_path"))
        
        return result
```

### Agent Invocation

```bash
# Autoresearch agent discovers and runs ready experiments
python -c "
from tools.cgmencode.exp_autoresearch_manifest_loader import ExperimentManifestLoader

loader = ExperimentManifestLoader()
ready = loader.ready_experiments()

print(f'Found {len(ready)} ready experiments')
for exp in ready:
    print(f\"  - EXP-{exp['id']}: {exp['title']}\")
    result = loader.run_experiment(exp['id'])
    print(f\"    ✓ Output: {result['output_path']}\")
"
```

---

## Integration with Audition Pipeline

### Step 1: Experiments Auto-Generate FactsLoaders

```python
# After EXP-2895/2896/2897 complete, create FactsLoader for each

# exp_2895_cross_cohort_basal.parquet
#   → new BasalEnvelopeFactsLoader(cross_cohort=True)

# exp_2896_evening_stacking_flair.parquet
#   → PhenotypeFactsLoader auto-augmented with FLAIR data

# exp_2897_haaf_flair.parquet
#   → PhenotypeFactsLoader.p_haaf field validates across cohorts
```

### Step 2: Audition Pipeline Uses Enriched FactsLoaders

```python
class AuditionInputs:
    phenotype_loader = PhenotypeFactsLoader()  # Now includes FLAIR data
    
    def compute_hypo_risk(self, patient_id: str):
        facts = self.phenotype_loader.lookup(patient_id)
        
        # Cross-study validation: FLAIR cohort shows same patterns
        # → More confident that findings generalize
        
        # Can now stratify on cohort (audition vs FLAIR)
        cohort = facts.cohort if hasattr(facts, 'cohort') else 'audition'
        
        # Apply cohort-specific thresholds
        if cohort == 'FLAIR':
            fragile = facts.brake_ratio < 0.06  # FLAIR baseline
        else:
            fragile = facts.brake_ratio < 0.07  # audition baseline
        
        return fragile
```

---

## Experiment Pickup Checklist

For autoresearch agents to successfully run these experiments:

- [ ] **EXP-2895**: FLAIR data path configured, BabelBetes bootstrapped
- [ ] **EXP-2896**: EXP-2895 output available, methodology replicated from EXP-2881
- [ ] **EXP-2897**: EXP-2896 output available, hypo detection pipeline ready
- [ ] **EXP-2898**: TreatmentDedupFactsLoader has data, dedup logic implemented

---

## Next Steps for Autoresearch Agents

1. **Discover ready experiments**: Use `ExperimentManifestLoader.ready_experiments()`
2. **Run in order**: Respect dependency chain (2895 → 2896 → 2897)
3. **Augment as needed**: Override experiment params (cohort, thresholds, paths)
4. **Validate**: Confirm orthogonality/deconfounding assumptions
5. **Report**: Update FactsLoaders with new cohort data

---

## References

- **BabelBetes Flair Study**: `externals/babelbetes/babelbetes/studies/flair.py`
- **PhenotypeFactsLoader**: `tools/cgmencode/production/phenotype_facts_loader.py`
- **TreatmentDedupFactsLoader**: `tools/cgmencode/production/treatment_dedup_facts_loader.py`
- **EXP-2881 (Evening Stacking)**: Evening drivers report
- **EXP-2878 (HAAF)**: HAAF detection report
- **EXP-2892 (Treatment Sync)**: Protection-mechanism signature
- **Deconfounding Toolkit**: `docs/60-research/deconfounding-toolkit-2026-04-22.md`
- **Multifactored Architecture**: `docs/10-domain/multifactored-factsloaders-deconfounding-architecture.md`
