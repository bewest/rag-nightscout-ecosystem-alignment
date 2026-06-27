# MLflow Experience Report (2026-06-27)

**Scope**: `tools/cgmencode` experiment tracking, validation, and research workflow capture

---

## Executive Summary

MLflow is already useful in this workspace because it gives the `cgmencode` research program a single local-first place to track runs, artifacts, provenance, and comparisons across several very different experiment families. The important lesson is that MLflow is not only for neural network checkpoints. In this repo it is already serving three kinds of work:

1. **Model-producing work** such as glucose forecasters, classification models, and pattern experiments
2. **Evaluation-heavy work** such as multi-patient validation runs and generated reports
3. **Structured research workflows** such as the autoresearch pilot, where traceability matters more than a single numeric score

The next step is to treat **learned physiological parameters and algorithm designs** as first-class tracked outputs too. A forecaster checkpoint is a model, but so is a learned ISF schedule, a basal schedule, a dose-response regression, or a digestion detector threshold set. Those artifacts may be equations, coefficients, schedules, and confidence intervals instead of `.pth` files, but they still represent learned behavior that should be versioned, compared, and audited.

---

## What MLflow is Doing Well Here

The current integration is practical rather than aspirational:

- tracking is **local-first** by default, using a git-ignored SQLite backend under `externals/mlflow/mlflow.db`
- artifact storage is also local and git-ignored under `externals/mlflow/artifacts/`
- MLflow remains **optional at import time**, so the rest of the workspace still runs when the package is unavailable
- runs inherit useful provenance tags such as git commit, git branch, and workspace lock hash

That combination fits this workspace well. It preserves reproducibility without forcing a cloud dependency or requiring the team to reorganize around a remote tracking service before the experiment surface is stable.

---

## What We Are Tracking Today

The current MLflow surface already covers the canonical `cgmencode` entrypoints:

| Area | Current entrypoints | What gets tracked |
|---|---|---|
| Forecast/model sweeps | `run_experiments.py` | per-config runs, per-seed runs, metrics, checkpoints, aggregate comparisons |
| Pattern and FDA experiments | `run_pattern_experiments.py` | experiment metadata, elapsed time, result JSON, artifacts |
| Forward-validated baselines | `experiments_validated.py` | held-out evaluation runs with multi-seed validation framing |
| Validation dashboards | `run_validation_report.py` | population metrics, figures, report markdown, summary JSON |
| Older research backfill | `run_research_reproduction.py` | stdout/stderr capture plus recovered result artifacts for legacy scripts |
| Agentic research pilot | `autoresearch_agent.py` | memo artifacts plus nested spans for retrieval/planning-style traces |

This is a good division of labor. It means current work does not need to choose between “only raw scripts” and “fully productized pipelines.” MLflow is already acting as a shared evidence layer across both.

---

## The Main Design Lesson

The most important lesson so far is that **“model” is broader than “deep learning artifact.”**

That matters in this repo because the most valuable outputs are often not end-to-end predictors. Many are **interpretable, structured, clinically legible parameterizations**:

- regression fits for correction-dose response
- learned per-patient settings
- basal / ISF / CR schedules
- confidence grades and bootstrap intervals
- deconfounding coefficients
- controller-specific comparison artifacts

These outputs are still learned from data. They still compete with alternative formulations. They still need provenance, reproducibility, and comparative evaluation. MLflow is a good home for them even when the final artifact is JSON, markdown, CSV, or a schedule table instead of a serialized estimator object.

---

## Where Forecasters Fit

The forecasters are the clearest conventional MLflow use case in the workspace.

They already map cleanly onto standard tracking:

- hyperparameter sweeps
- repeated seeds
- checkpoint artifacts
- validation metrics against persistence baselines
- comparisons across feature modes and architectures

For this category, MLflow should continue to be the default system of record. The main future improvement is not conceptual. It is organizational:

1. make benchmark datasets and split definitions more explicit as tracked artifacts
2. surface “best known” models by task and horizon in a stable comparison table
3. optionally promote selected checkpoints into a lightweight local model catalog once the interfaces stabilize

In other words, the forecasting lane is already the mature part of the MLflow story.

---

## Where Algorithm Design Fits

Algorithm-design work also belongs in MLflow, even when it does not look like conventional model training.

The “Simple ML to learn insulin sensitivity and basal rates” note is a good example of the pattern. It describes an adaptive physiological algorithm built from:

- segmentation rules
- digestion detection logic
- flat/decreasing-window filters
- least-squares fits
- learned basal estimates
- learned insulin sensitivity estimates
- longer-horizon schedule updates from regression

That is still MLflow-worthy work. The artifact is simply different. Instead of a neural checkpoint, the outputs might be:

- learned parameter schedules by time of day
- coefficients for regression-based sensitivity models
- gating thresholds for flatness, noise, or digestion completion
- training-segment inclusion criteria
- confidence summaries and failure cases
- validation plots showing where the learned parameters help or break down

This suggests a simple rule for the repo:

> If a workflow **learns from data and changes future behavior**, it belongs in MLflow, even if the learned object is a schedule, rule set, or physiological parameter table rather than a neural net.

That framing lets us track settings extraction, deconfounding, controller compensation models, and similar research on equal footing with forecasters.

---

## What MLflow Has Helped Clarify

Using MLflow in this mixed environment has clarified a few boundaries:

### 1. Standard tracking vs GenAI is a real distinction

Most current work here belongs in the **standard experiment tracking** lane, not the GenAI lane. Forecasts, classification, validation, and physiological parameter recovery are fundamentally about metrics, artifacts, and reproducibility. The GenAI surface is only the right fit when prompts, retrieval, tool traces, or human review of generated prose become central.

### 2. Legacy scripts still have research value

The backfill wrapper for older research scripts is worth keeping. It lets historically important analyses participate in the same evidence system without forcing an immediate rewrite.

### 3. Reports are artifacts, not side effects

The validation report path is especially useful. It treats markdown reports, figures, and summary JSON as tracked outputs rather than disposable byproducts. That is the right pattern for this repo because interpretation is part of the deliverable.

### 4. Provenance matters more than centralization right now

Local SQLite plus artifact logging is enough to create useful reproducibility. The immediate need is not a hosted MLOps platform. It is consistent lineage across experiments, reports, and algorithm revisions.

---

## Future Directions

### 1. First-class support for learned parameter artifacts

We should add a more explicit convention for runs whose primary output is a learned physiological object rather than a checkpoint. For example:

- `artifacts/parameters/isf_schedule.json`
- `artifacts/parameters/basal_schedule.json`
- `artifacts/models/dose_response_fit.json`
- `artifacts/evals/counterfactual_validation.json`

That would make algorithm-design runs easier to compare across cohorts, controller types, and time windows.

### 2. Stronger benchmark and cohort lineage

For both forecasters and settings algorithms, tracked runs should describe:

- patient cohort definition
- controller mix
- inclusion / exclusion criteria
- time horizon
- train / validation / test split semantics
- whether the result is descriptive, prescriptive, retrospective, or prospective

This is especially important in a domain where the same algorithm can look excellent descriptively and fail prescriptively.

### 3. Explicit “candidate for production” promotion path

Right now MLflow is strong at recording experiments but weaker at signaling which outputs are stable enough for operational use. A lightweight promotion convention would help:

- `research`
- `validated`
- `candidate`
- `production-reference`

That status could apply to forecasters, recommendation formulas, or learned setting schedules alike.

### 4. Better support for hybrid physics + ML experiments

A lot of the best work in this repo is hybrid: physics decomposition, controller-state features, and statistical or neural models layered together. MLflow should make those compositions easy to compare by logging:

- physics configuration
- feature families enabled
- learned residual model details
- evaluation regime
- exported clinical/report artifacts

This would help keep the “physics is the product, ML is the refinement” insight visible.

### 5. Broader GenAI usage where traces actually matter

The autoresearch pilot is the right place to explore MLflow’s GenAI surface. Other good candidates would be:

- retrieval-backed report generation
- literature-to-experiment hypothesis generation
- experiment planning agents
- claim-audit workflows over docs and result bundles

But this should remain a separate lane from forecasting and parameter-learning. Mixing those concepts too early would blur evaluation standards.

---

## Recommended Working Definition for This Repo

For this workspace, a useful working definition is:

> **MLflow tracks learned evidence objects.**
>
> Sometimes that object is a forecast model checkpoint. Sometimes it is a classifier. Sometimes it is a report bundle. Sometimes it is a physiological schedule, a regression, or an adaptive dosing heuristic. If it is learned from data, compared against alternatives, and intended to inform future behavior, it should usually be tracked.

That definition fits both the forecasters and the more algorithmic work on learned basal rates, insulin sensitivity, and related controller-facing parameters.

---

## Bottom Line

MLflow has already earned its place here as the common tracking surface for `cgmencode`. The key future move is to expand our notion of what counts as a model. In this repo, the next important tracked objects are not only better forecasters. They are also better **learned physiological algorithms**: parameter schedules, deconfounding fits, controller-aware adjustment rules, and the evidence bundles that justify them.
