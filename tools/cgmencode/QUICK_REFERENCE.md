# BabelBetes Integration: Quick Reference Card

**Posted**: 2026-04-22 | **Status**: Ready for team pickup  
**For**: Concurrent teammates working in `tools/cgmencode/`

---

## 🎯 What's Ready to Use Right Now

### 1. **PhenotypeFactsLoader** — Load 3 orthogonal phenotype axes
```python
from tools.cgmencode.production.phenotype_facts_loader import PhenotypeFactsLoader

loader = PhenotypeFactsLoader()
facts = loader.lookup('patient-id')

# Available fields (all ⟂ orthogonal):
facts.stack_score              # Bolus stacking (EXP-2882)
facts.brake_ratio              # Suspension % (EXP-2885)
facts.counter_reg_intercept    # Recovery intercept (EXP-2877)
facts.beta_nadir               # HAAF fragility (EXP-2878)
facts.p_haaf                   # Counterfactual p-value
facts.evening_bolus_excess_4h  # 4h bolus excess (EXP-2881)
facts.controller_lineage       # "Loop" | "oref0" | "Trio"
```

### 2. **TreatmentDedupFactsLoader** — Load dedup strategy + confidence
```python
from tools.cgmencode.production.treatment_dedup_facts_loader import (
    TreatmentDedupFactsLoader,
)

loader = TreatmentDedupFactsLoader()
strategy = loader.lookup('patient-id')

# Available fields:
strategy.dedup_window_sec           # e.g., 60 sec
strategy.tie_breaker_priority       # ["sync_id", "timestamp", "amount"]
strategy.use_sync_id                # Boolean
strategy.event_type_confidence      # {"bolus": 0.95, "carbs": 0.80}
strategy.confidence                 # Overall 0.0-1.0
```

---

## ⚠️ 4 Things to Avoid

| Anti-Pattern | Problem | Solution |
|---|---|---|
| **Composite risk** | `stack * (1-brake) * recovery` loses -0.227 adj-R² | Use separate signals: `audition.add_signal('stack', x); add_signal('brake', y)` |
| **Pooled aggregation** | Prolific patients dominate | Use per-patient aggregation: `df.groupby('patient_id').mean().mean()` |
| **Validate vs observed** | AID suspension creates collider bias | Validate vs counterfactual: use `p_haaf` field (pre-computed) |
| **Missing NaN checks** | `np.percentile()` silently returns NaN | Explicit dropna: `[v for v in vals if pd.notna(v)]` |

---

## 🚀 How to Integrate (3 Steps)

### Step 1: Import
```python
from tools.cgmencode.production.phenotype_facts_loader import PhenotypeFactsLoader
```

### Step 2: Lookup
```python
phenotype = PhenotypeFactsLoader()
facts = phenotype.lookup(patient_id)
if facts is None or facts.brake_ratio is None:
    continue  # Graceful degradation
```

### Step 3: Use Separate Signals
```python
audition.add_signal('stacking', facts.stack_score)
audition.add_signal('suspension', facts.brake_ratio)
audition.add_signal('fragility', facts.beta_nadir)
# Don't composite ↑ these
```

---

## 📊 Test Locally

```bash
# Run all production FactsLoaders tests (14 tests)
pytest tools/cgmencode/production/ -v

# Expected output: 14/14 passing ✅
```

---

## 📖 Documentation

| Doc | Use Case |
|---|---|
| `TEAMMATE_PICKUP_GUIDE.md` | Full integration guide + patterns + templates |
| `EXP-2895-2900_AUTORESEARCH_PIPELINE.md` | Autoresearch agents: ready experiment templates |
| `babelbetes-multifactor-pattern.md` | Architecture background (why orthogonal signals) |
| `multifactored-factsloaders-deconfounding-architecture.md` | Deconfounding principles (C1-C8) |

---

## 🔍 Reference Implementations

Look at these existing FactsLoaders as templates:
- `basal_mismatch_facts_loader.py` ← Best reference
- `state_basal_facts_loader.py`
- `recovery_facts_loader.py`

---

## 🎁 Bonus: Ready-to-Pickup Experiments

For autoresearch agents (or manual runs):

| Exp | Title | Status | Depends On |
|---|---|---|---|
| **2895** | Cross-cohort basal (FLAIR vs Loop) | Ready | None |
| **2896** | Evening stacking (FLAIR validation) | Ready | 2895 |
| **2897** | HAAF fragility (cross-cohort) | Ready | 2896 |
| **2898** | Treatment dedup (FLAIR validation) | Blocked | Treatment data |

See `EXP-2895-2900_AUTORESEARCH_PIPELINE.md` for full templates.

---

## ✅ Checklist: Before You Commit

- [ ] Imported from `tools.cgmencode.production/`
- [ ] Handles `None` gracefully
- [ ] Uses per-patient aggregation (not pooled)
- [ ] Signals kept separate (no composites)
- [ ] Tests pass: `pytest tools/cgmencode/production/ -v`
- [ ] Docstring explains orthogonality/deconfounding

---

## ❓ Quick Questions?

**Q: Can I composite `stack * brake * recovery`?**  
A: No. This loses -0.227 adj-R². Use separate signals instead.

**Q: What if FactsLoader returns None?**  
A: Graceful degradation by design. Check `if facts is None` and skip or use default.

**Q: Should I load `exp_2886_phenotype.parquet` myself?**  
A: No. Use `PhenotypeFactsLoader.lookup()` instead (lazy-loaded, cached, tested).

**Q: How do I extend PhenotypeFactsLoader with new data?**  
A: Add new orthogonal axis (verify |ρ| < 0.32 with existing axes), add field to dataclass, update `_load()`, add test, update docstring.

---

## 🎯 TL;DR

✅ Use `PhenotypeFactsLoader` for phenotype stratification  
✅ Use `TreatmentDedupFactsLoader` for treatment dedup strategy  
✅ Keep signals orthogonal (don't composite)  
✅ Use per-patient aggregation  
✅ Run: `pytest tools/cgmencode/production/ -v`  

❌ Don't composite risk scores  
❌ Don't pool events (Simpson's paradox)  
❌ Don't validate vs observed outcomes (collider bias)  
❌ Don't forget NaN checks

**Ready to pick up?** See `TEAMMATE_PICKUP_GUIDE.md` for full integration template! 🚀
