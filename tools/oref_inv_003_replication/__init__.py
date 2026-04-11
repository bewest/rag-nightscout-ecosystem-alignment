"""
oref_inv_003_replication — Replication, Contrast & Augmentation of OREF-INV-003

This package systematically replicates, strengthens, contrasts, and augments
the OREF-INV-003 analysis ("What Drives Outcomes in oref Closed-Loop Insulin
Delivery") using independent data and complementary methods.

OREF-INV-003 analyzed ~2.9M decision records from 28 oref users with LightGBM.
Our lab analyzed 11 Loop/oref0 patients with transformer AE, physics-residual ML,
supply-demand analysis, and pharmacokinetic profiling (~250 experiments).

This package bridges the two, producing a synthesis stronger than either alone.

Experiment numbering: EXP-2401 through EXP-2498
"""

__version__ = "0.1.0"

COLLEAGUE_DIR = "/home/bewest/Downloads/OREF-INV-003-v5-Analysis/OREF-INV-003-v5-Analysis"
PARQUET_DIR = "externals/ns-parquet/training"
FIGURES_DIR = "tools/oref_inv_003_replication/figures"
REPORTS_DIR = "tools/oref_inv_003_replication/reports"
RESULTS_DIR = "externals/experiments"
