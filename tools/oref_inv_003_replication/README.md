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

### Phase 5+: Correction, PK features, DIA, algorithm-neutral set
| ID | Script | Question |
|----|--------|----------|
| EXP-2501 | `exp_repl_2501.py` | How does AUC change with forecast horizon? |
| EXP-2511 | `exp_repl_2511.py` | Do PK replacements help; how does an 18-feature algorithm-neutral set compare? |
| EXP-2519 | `exp_repl_2519.py` | Does the 18-feature comparison hold under patient-grouped CV? |
| EXP-2521 | `exp_repl_2521.py` | Baseline replication on the corrected data |
| EXP-2531 | `exp_repl_2531.py` | Corrected data with PK features |
| EXP-2541 | `exp_repl_2541.py` | Per-patient DIA fitting |
| EXP-2581 | `exp_repl_2581.py` | Algorithm prediction quality |

**Cross-validation.** EXP-2431/2432 and EXP-2519 hold out whole patients. Every other AUC in
`reports/` comes from row-shuffled folds, which put one patient's decisions in both train and
test and overstate AUC by about 0.10 to 0.15. Feature-set comparisons should be read from
EXP-2519. Summary for the study's author and other researchers:
[`docs/60-research/collaboration/oref-inv-003-replication-brief.md`](../../docs/60-research/collaboration/oref-inv-003-replication-brief.md).

## Data Requirements

- `externals/ns-parquet/training/grid.parquet` — our patient data
- The study's own models at `COLLEAGUE_DIR` (see `__init__.py`), for EXP-2401 and the other
  experiments that compare against them; EXP-2519 does not need them
- Another data holder's grid: `exp_repl_2519.py --parquet-dir <dir>`, built with
  `ns2parquet convert-all`
