"""Autoresearch CF-replay package.

Builds on EXP-2889 (counterfactual AID-off replay). Each experiment in this
package tests a single hypothesis on top of a shared replay engine, records its
result to ``tools/aid-autoresearch/autoresearch_cf_results.tsv``, and emits a
parquet/json/figure trio under ``externals/experiments/`` and
``docs/60-research/figures/``.

Conventions
-----------
- All input data is loaded read-only from the existing parquet inventory
  (``externals/ns-parquet/training/`` and ``externals/experiments/``).
- All numeric outputs land under ``externals/experiments/`` (gitignored).
- All figures land under ``docs/60-research/figures/`` (committed).
- All reports land under ``docs/60-research/exp-NNNN-…-2026-04-24.md``.
- The shared engine in ``replay.py`` is intentionally pure-functional so each
  experiment can dependency-inject ``isf_source``, ``insulin_kernel``, and
  ``duration_model`` without touching the pipeline.
"""
