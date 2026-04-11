# OREF-INV-003 Replication, Contrast & Augmentation

Systematic replication and critical analysis of the OREF-INV-003 study
("What Drives Outcomes in oref Closed-Loop Insulin Delivery") using
independent data, complementary methods, and cross-algorithm comparison.

## Context

**OREF-INV-003** (colleague's work):
- 28 oref users (Trio, iAPS, AAPS), ~2.9M decision records
- LightGBM with 32 features, SHAP interpretation
- 4-hour hypo/hyper prediction, parameter sweep simulations
- Deployable Settings Advisor with per-user isotonic calibration

**Our lab** (tools/cgmencode, ~250 experiments):
- 11 patients (a–k), Loop + oref0, ~180 days each
- Transformer AE, physics-residual ML, supply-demand analysis
- Pharmacokinetic profiling, circadian therapy, meal pharmacodynamics
- AID Compensation Theorem, prediction bias analysis

## Quick Start

```bash
# From repository root
PYTHONPATH=tools python3 -m oref_inv_003_replication.exp_repl_2401 --figures

# Run all experiments
PYTHONPATH=tools python3 -m oref_inv_003_replication.run_all
```

## Experiment Index

### Phase 2: Replication
| ID | Script | Question |
|----|--------|----------|
| EXP-2401 | `exp_repl_2401.py` | Does feature importance ranking replicate? |
| EXP-2411 | `exp_repl_2411.py` | Does target sweep tradeoff replicate? |
| EXP-2421 | `exp_repl_2421.py` | Is CR×hour the top interaction? |
| EXP-2431 | `exp_repl_2431.py` | Does hypo prediction model replicate? |

### Phase 3: Contrast
| ID | Script | Question |
|----|--------|----------|
| EXP-2441 | `exp_repl_2441.py` | Loop vs oref prediction accuracy? |
| EXP-2451 | `exp_repl_2451.py` | Basal correctness: correlational vs causal? |
| EXP-2461 | `exp_repl_2461.py` | IOB protective effect reconciliation? |

### Phase 4: Augmentation
| ID | Script | Question |
|----|--------|----------|
| EXP-2471 | `exp_repl_2471.py` | Do PK features improve prediction? |
| EXP-2481 | `exp_repl_2481.py` | Do SHAP and causal importance agree? |
| EXP-2491 | `exp_repl_2491.py` | Cross-algorithm transfer learning? |

## Data Requirements

- `externals/ns-parquet/training/grid.parquet` — our patient data
- Colleague's models at `COLLEAGUE_DIR` (see `__init__.py`)
