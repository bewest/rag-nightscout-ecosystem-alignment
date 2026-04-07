# Capability Report: Real-Time Operations & Deployment

**Date**: 2026-04-07 | **Overnight batch**: EXP-689–690, EXP-790 | **Patients**: 11

---

## Capability Definition

Execute the full inference pipeline — from raw CGM/treatment data to clinical recommendations — at latencies suitable for real-time deployment on devices ranging from cloud servers to wearables.

---

## Current State of the Art

| Metric | Value | Method |
|--------|-------|--------|
| End-to-end latency (11 patients) | **1.3 seconds** total | Full pipeline |
| Per-patient mean | **118.5 ms** | Flux + clean + features + train + report |
| Streaming inference latency | **19.5 μs** per step | Incremental update |
| Stream vs batch R² gap | **0.002** (negligible) | Online vs offline comparison |
| Production model size | **67K params** (medium) | d=48, L=3 transformer |
| Edge-viable model | **13K params** (tiny) | d=32, L=1, 9% accuracy loss |

---

## Pipeline Breakdown (EXP-690)

Where does time go in the end-to-end pipeline?

| Stage | Mean Time | % of Total |
|-------|-----------|-----------|
| **Metabolic flux calculation** | 109.0 ms | **92.0%** |
| Spike cleaning | 4.1 ms | 3.5% |
| Feature engineering | 1.9 ms | 1.6% |
| Model training/inference | 2.7 ms | 2.3% |
| Metrics + report | 0.6 ms | 0.5% |

**The bottleneck is physics, not ML.** Metabolic flux computation (integrating IOB/COB curves from treatment history) consumes 91% of wall time. The actual ML inference takes 2.7 ms — fast enough for real-time on any platform.

---

## Production Model Sizing (EXP-448)

| Variant | Params | h60 MAE | Inference (ms) | Use Case |
|---------|--------|---------|----------------|----------|
| **7ch** (drop time features) | 135K | **17.71** | 1.6 | Cloud/server |
| **medium** (d48, L3) | 67K | 17.85 | 1.4 | Mobile phone |
| small (d32, L2) | 26K | 18.15 | 1.1 | Wearable/edge |
| tiny (d32, L1) | 13K | 19.25 | 0.8 | Minimum viable |
| full (d64, L4) | 135K | 18.51 | 1.6 | Overparameterized ❌ |

**The full model is overparameterized.** It ranks 4th of 6 variants at h60. The medium model (67K params, 50% fewer) achieves *better* accuracy. Time features are counterproductive at h60 — confirming time-translation invariance at episode scales.

---

## Streaming Fidelity (EXP-689)

Real-time streaming (one prediction per 5-minute CGM reading) vs batch (process entire history at once):

| Patient | Stream R² | Batch R² | Δ |
|---------|-----------|----------|---|
| e (best) | 0.768 | 0.771 | −0.003 |
| g | 0.495 | 0.495 | 0.000 |
| d (worst gap) | 0.132 | 0.132 | 0.000 |
| **Mean** | **0.324** | **0.326** | **−0.002** |

The streaming/batch gap is negligible — incremental updates preserve full model quality. No accuracy is sacrificed for real-time operation.

---

## Deployment Simulation (EXP-790)

Full streaming deployment over multiple days per patient:

| Metric | Value |
|--------|-------|
| 30-min streaming R² | **0.532** |
| 60-min streaming R² | −0.548 (without circadian correction) |
| AR lookback optimal | **10 minutes** |
| Pre-bolus timing (9/11 patients) | 6.5–28.9 minutes |

The 60-minute gap confirms circadian correction is mandatory for production deployment at longer horizons. Without it, the model systematically underpredicts dawn glucose rises.

---

## Validation Vignette

**Real-time pipeline on patient g**: Raw CGM reading arrives at T+0. Physics flux computation completes at T+121.5 ms. Spike check clears at T+127.2 ms. Features extracted at T+129.5 ms. Model produces 12-step forecast (5–60 min) at T+133.7 ms. Clinical grade (A) and recommendations ("maintain current settings") generated at T+134.7 ms. Total: **134.7 ms from data arrival to actionable output** — well under the 5-minute CGM interval.

**Edge deployment sizing**: The small model (26K params, d=32, L=2) achieves h60 MAE = 18.15 — only 2.5% worse than the best model — in 1.1 ms inference time. At 26K parameters in float32, the model weights occupy **104 KB** of memory. This fits comfortably on a Bluetooth-connected CGM receiver or smartwatch.

---

## Key Insight

The ML inference is not the deployment bottleneck — **physics simulation is**. The metabolic flux calculation (integrating insulin-on-board curves from treatment history) takes 91% of pipeline time. Optimizing this computation — through incremental IOB updates rather than full-history recalculation, or pre-computed lookup tables for standard insulin curves — would reduce total latency from 118 ms to ~15 ms per patient, enabling true real-time operation even on the most constrained devices.
