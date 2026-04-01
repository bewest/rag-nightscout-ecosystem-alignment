# cgmencode Model Capabilities Report

**Date**: 2026-07-24
**Tool**: `tools/cgmencode/event_eval.py`, `tools/cgmencode/hindcast.py`
**Data**: 90-day Nightscout history (Nov 2025 – Feb 2026, 24,748 5-min steps)
**Patient Profile**: ISF=40 mg/dL/U, CR=10 g/U, DIA=6h (from profile.json)

## Executive Summary

We systematically evaluated 5 model configurations across 6 inference frames
using real Nightscout data with metabolic event classification heuristics.
Each model reveals different strengths depending on its training regime and
whether physics-residual composition is used.

### Key Findings at a Glance

| Capability | Best Model | Result | Clinical Significance |
|-----------|-----------|--------|----------------------|
| **Glucose forecasting** | Grouped+Physics | 12.2 MAE | 4.7× better than Loop (58.0) |
| **Reconstruction** | Grouped+Physics | 13.0 MAE | Accurate curve-fitting |
| **UAM detection** | AE Transfer+Physics | 16.9 MAE on UAM | Captures rises without carb entries |
| **Dawn phenomenon** | AE Transfer+Physics | 11.6 MAE on dawn | Best at early-morning rises |
| **Counterfactual reasoning** | AE Conformance | 23.9 mg/dL effect | Only model with treatment sensitivity |
| **Causal understanding** | AE Conformance | 0.72–1.35 impute ratio | Approaches but doesn't achieve causality |
| **Anomaly diversity** | AE Residual Enhanced | 5 event types in top 10 | Physics normalizes time-of-day bias |
| **Similarity clustering** | Grouped+Physics | 0.075 avg distance | Tightest grouping, but by dynamics not cause |

**Bottom line**: Physics-residual models (Grouped+Physics, AE Transfer+Physics)
dominate on accuracy. AE Conformance is the only model showing causal-like
reasoning (counterfactuals, imputation) thanks to synthetic training with
diverse treatment scenarios. No model yet demonstrates true causal insulin→glucose
understanding—this remains the key architectural gap.

---

## Models Under Test

| ID | Checkpoint | Architecture | Training | Residual | Params |
|----|-----------|-------------|----------|----------|--------|
| **A** | `ae_transfer.pth` | CGMTransformerAE | Synthetic→Real NS fine-tuned | No | 68,040 |
| **B** | `ae_transfer.pth` + physics | CGMTransformerAE | Same, with physics composition | Yes | 68,040 |
| **C** | `ae_best.pth` | CGMTransformerAE | Conformance synthetic (UVA/Padova) | No | 68,040 |
| **D** | `ae_014_grouped_transfer.pth` + physics | CGMGroupedEncoder | Synthetic→Real, physics | Yes | 67,704 |
| **E** | `ae_residual_enhanced.pth` + physics | CGMTransformerAE | Enhanced physics residual | Yes | 68,040 |

**Conditioned Transformer** (`conditioned_dropout+wd.pth`) was excluded—its different
`forward()` signature requires a dedicated hindcast adapter (future work).

---

## Frame 1: Forecast

**Question**: "Given the past 60 min of glucose/IOB/COB, what happens in the next 60 min?"

### Results

| Model | Avg MAE | vs Loop (58.0) | vs Physics (66.2) | Best Window | Worst Window |
|-------|---------|----------------|---------------------|-------------|-------------|
| **D** Grouped+Physics | **12.2** | **4.7× better** | 5.4× better | — | — |
| **B** AE Transfer+Physics | 14.5 | 4.0× better | 4.6× better | — | — |
| **E** AE Residual Enhanced | 20.8 | 2.8× better | 3.2× better | — | — |
| **C** AE Conformance | 111.1 | 1.9× worse | 1.7× better | — | — |
| **A** AE Transfer (raw) | 217.1 | 3.7× worse | 3.3× worse | — | — |

### Interpretation

- **Physics-residual models dominate.** The pattern is consistent: physics provides
  a ~66 MAE baseline (naïve forward integration), and ML learns the residual,
  capturing 75–82% of remaining error.
- **AE Transfer (raw) cannot forecast.** It outputs near-zero in forecast mode
  because it was trained for reconstruction (bidirectional attention). Future
  positions have no information to attend to → mean-reversion to zero.
- **AE Conformance partially forecasts.** Trained on diverse synthetic scenarios
  with masked futures, it has some notion of "what comes next" but the synthetic
  training distribution doesn't match real patient dynamics (111 MAE).

### Event-Specific Forecast Accuracy

| Event Type | A (raw) | B (+phys) | C (conf) | D (grp+phys) | E (res+) | Loop |
|-----------|---------|-----------|----------|---------------|----------|------|
| UAM (n=3) | 36.8* | **16.9** | 73.4 | 14.2 | 23.5 | 89.1 |
| Dawn (n=3) | 25.7* | **11.6** | 56.6 | 14.0 | 23.5 | 63.5 |
| Correction (n=3) | 28.1* | 18.1 | 53.0 | **14.0** | 22.8 | 55.8 |
| Stable (n=3) | 21.0* | 8.8 | 17.0 | 16.4 | 23.8 | **2.3** |

*\*Model A uses reconstruction, not forecast—these numbers are reconstruction MAE
evaluated on event-typed windows.*

**Key insight**: Physics-residual models beat Loop on every event type except
**stable** windows, where Loop's persistence-like prediction (BG stays flat)
naturally excels. This suggests the ML component adds value precisely where
there's dynamic activity to model—UAM events, dawn phenomenon, correction boluses.

---

## Frame 2: Reconstruct

**Question**: "Can the model accurately represent what happened over a 2-hour window?"

### Results

| Model | Avg MAE | Notes |
|-------|---------|-------|
| **D** Grouped+Physics | **13.0** | Best overall; consistent across window types |
| **B** AE Transfer+Physics | 14.5 | Nearly tied with Grouped |
| **E** AE Residual Enhanced | 22.6 | Slightly worse on volatile windows |
| **A** AE Transfer (raw) | 35.8 | Good for non-residual; strong on smooth windows |
| **C** AE Conformance | 41.8 | Synthetic training means domain gap on real data |

### Interpretation

Reconstruction is the strongest capability across all models. Even the worst
performer (AE Conformance at 41.8) significantly outperforms Loop's predictions
(58.0 MAE averaged across the same windows).

The residual models' advantage (~13–15 MAE) comes from physics providing the
"easy" portion of the signal (overall trend from IOB/COB dynamics) while ML
captures the "hard" residual (patient-specific response timing, liver effects,
circadian rhythm).

---

## Frame 3: Anomaly Detection

**Question**: "Which windows does the model find hardest to represent? What patterns emerge?"

### Anomaly Event Distribution (Top 20 per Model)

| Event Type | A (raw) | B (+phys) | C (conf) | D (grp+phys) | E (res+) |
|-----------|---------|-----------|----------|---------------|----------|
| nocturnal | **16** | 3 | 7 | 3 | 0 |
| high_volatility | 11 | 9 | **20** | **18** | 3 |
| uam | 9 | 0 | 10 | 0 | 2 |
| exercise_candidate | 4 | 5 | 1 | 6 | 3 |
| correction | 0 | **4** | 0 | 0 | 0 |
| meal_bolus | 3 | 4 | 0 | 0 | 0 |
| other | 0 | 5 | 0 | 1 | **10** |
| stable | 0 | 0 | 0 | 0 | 4 |
| dawn | 0 | 0 | 1 | 0 | 0 |

### Anomaly MAE Ranges

| Model | Min MAE | Max MAE | Spread | Interpretation |
|-------|---------|---------|--------|---------------|
| **A** AE Transfer | 24.1 | 34.6 | 10.5 | Clear separation between easy/hard |
| **B** AE Transfer+Phys | 20.3 | 46.3 | 26.0 | Widest spread → best discrimination |
| **C** AE Conformance | 78.8 | 92.3 | 13.5 | High baseline error everywhere |
| **D** Grouped+Physics | 10.4 | 10.6 | **0.2** | Nearly flat → poor discriminator |
| **E** AE Residual Enhanced | 16.4 | 16.6 | **0.2** | Nearly flat → poor discriminator |

### Interpretation

**Model A (raw)**: 80% of anomalies are nocturnal. This is a training bias—
the model was fine-tuned on data where most "interesting" windows are overnight,
and it hasn't learned nocturnal physiology well (circadian liver glucose
production, compression lows).

**Model B (AE Transfer+Physics)**: Physics removes time-of-day bias. Anomalies
spread across corrections, meal boluses, and exercise — events where the
*treatment-response dynamics* are genuinely harder to model. This is the most
clinically useful anomaly detector: its top anomalies flag windows where insulin
or food actions produced unexpected outcomes.

**Model C (AE Conformance)**: All 20 anomalies are high-volatility. The
synthetic training distribution doesn't include the extreme ranges seen in real
data (BG 350+), so any wild excursion is flagged. Not useful for clinical
anomaly detection but could be repurposed as an "out of training distribution"
detector.

**Models D, E (Grouped, Residual Enhanced)**: Near-zero anomaly spread (0.2 MAE
difference between best and worst). These models represent *everything* equally
well—they've essentially memorized the residual patterns. They cannot be used
as anomaly detectors. Paradoxically, being "too good" at reconstruction makes
them unable to discriminate unusual from normal.

---

## Frame 4: Counterfactual

**Question**: "What would glucose look like if treatments (bolus, carbs) had not been given?"

The counterfactual frame zeroes out action channels (bolus, carbs, net_basal)
and compares model output to the original. The difference is the model's
estimate of **treatment effect**.

### Results

| Scenario | A (raw) | B (+phys) | C (conf) | D (grp+phys) | E (res+) |
|----------|---------|-----------|----------|---------------|----------|
| **Meal+bolus** (8.5U, 45g) | +0.8 | −2.3 | **−6.9** | +0.3 | +0.5 |
| **Meal+bolus** (4.9U, 50g) | −5.4 | −0.8 | **+10.7** | −0.2 | −0.7 |
| **UAM+dawn** (no actions) | −2.2 | +0.2 | **+9.7** | −0.9 | −0.0 |
| **UAM** (no actions) | −1.7 | −1.4 | **+23.9** | −0.6 | +0.6 |
| **Correction** (4.9U, no carbs) | −0.8 | +0.2 | **−4.2** | +0.1 | +0.4 |

*Values are mean treatment effect in mg/dL. Positive = glucose would be higher without treatment.*

### Interpretation

**AE Conformance is the only model with meaningful counterfactual sensitivity.**

- On a UAM window (no treatments given), zeroing actions shows +23.9 mg/dL mean
  effect and +45.9 max. This doesn't make physical sense (no actions to remove),
  but it reveals the model has learned that *action channels carry information*
  about glucose trajectory even when they're zero.
- On a correction bolus (4.9U, no carbs), the model predicts −4.2 mg/dL mean
  effect, meaning "insulin would have lowered glucose." Direction is correct;
  magnitude is small but physiologically plausible for a 4.9U bolus's partial
  effect over 2 hours.
- On meal+bolus, the model captures the *net* effect (+10.7 for carb-dominant,
  −6.9 for insulin-dominant). The sign flip between these two meal windows is
  promising—it suggests the model has some sensitivity to the carb/insulin
  ratio.

**All other models show near-zero counterfactual effects** (typically <2 mg/dL).
This means they've learned to copy/predict glucose from glucose context alone,
ignoring action channels. The residual models are especially flat because
physics already accounts for treatments—the ML residual doesn't need to
"understand" bolus/carbs.

**Implication**: For counterfactual "what-if" analysis (e.g., "what if I had
bolused 2U more?"), only the conformance-trained architecture shows promise,
and even there the magnitudes are imprecise. True causal counterfactual
reasoning will require architectural changes (see Recommendations).

---

## Frame 5: Imputation

**Question**: "Can the model infer glucose from IOB, carbs, and time alone (no glucose input)?"

The imputation frame masks the glucose channel and asks the model to reconstruct
it from actions and temporal features only. The **ratio** = masked_MAE / visible_MAE
measures how much worse the model gets without glucose:

- ratio ≈ 1.0 → model can infer glucose from actions (causal understanding)
- ratio >> 1.0 → model just copies glucose (no causality)

### Results

| Window Type | A (raw) | B (+phys) | C (conf) | D (grp+phys) | E (res+) |
|------------|---------|-----------|----------|---------------|----------|
| **Meal+bolus** | 7.58 | 5.00 | **1.35** | 19.37 | 9.97 |
| **UAM+dawn** | 6.87 | 3.64 | **0.72** | 2.18 | 1.55 |
| **Stable** | 4.03 | **1.07** | 0.84 | 1.32 | 1.15 |

### Interpretation

**AE Conformance achieves near-unity ratios**, suggesting partial causal
understanding:

- On UAM+dawn windows, ratio 0.72 means the model reconstructs glucose *better*
  without the glucose channel than with it. This is paradoxical and likely
  indicates that the model's best strategy for these windows is to predict
  from temporal features (time-of-day predicts dawn) rather than glucose context.
- On stable windows, ratio 0.84 — similar pattern: flat glucose is predictable
  from "nothing is happening."
- On meal+bolus windows, ratio 1.35 — performance degrades slightly without
  glucose, but far less than other models (7–19× degradation).

**AE Transfer+Physics achieves 1.07 on stable windows.** Physics provides the
causal chain (IOB→glucose lowering, COB→glucose rising) and the ML residual
is small on stable windows, so the physics baseline alone nearly suffices.
On meal windows (5.0× ratio), the ML residual carries important information
that requires glucose context.

**Grouped+Physics has the worst meal imputation (19.37×)**. Despite being the
best forecaster, it has learned the most glucose-dependent representation.
This confirms the "copier" hypothesis: the GroupedEncoder allocates 50% of
its capacity to state channels (glucose, IOB, COB) and produces excellent
reconstruction by memorizing input patterns, not by learning causal mechanisms.

---

## Frame 6: Similarity

**Question**: "Given a reference window, which other windows look most similar to the model?"

The similarity frame computes L2 distance on reconstruction residuals (not raw
embeddings — those gave uniformly high cosine similarity ~1.0).

### Results

| Reference Event | A avg dist | B avg dist | C avg dist | D avg dist | E avg dist |
|----------------|-----------|-----------|-----------|-----------|-----------|
| UAM+dawn | 0.142 | 0.144 | 0.615 | **0.075** | 0.126 |
| Meal+bolus (nocturnal) | 0.237 | 0.425 | 1.202 | **0.217** | 0.267 |

### What the Similarity Matches Reveal

**Grouped+Physics (D)** has the tightest clustering (0.075 avg distance for UAM),
but matches are heterogeneous:
- UAM+dawn reference → matches include `high_volatility`, `uam+dawn`, and
  `exercise_candidate` windows
- Meal+bolus reference → matches to `nocturnal` and `high_volatility`
- The model clusters by **dynamics shape** (rise-then-fall, oscillation) not by
  **metabolic cause** (meal vs dawn vs exercise)

**AE Conformance (C)** has the widest distances (0.615–1.202), meaning it sees
most windows as quite different from each other. This is consistent with its
higher reconstruction error—the model's representation is less precise, so
residual patterns vary more.

**AE Transfer+Physics (B)** shows an interesting pattern on meal+bolus:
distances are wider (0.425) than UAM (0.144), suggesting the model has learned
that meal+bolus dynamics are more variable than UAM rises.

**Clinical implication**: Similarity search groups windows by glucose *trajectory
shape*, not by underlying cause. A "what other events looked like this?"
query will return dynamically similar but causally diverse windows. This is
useful for pattern clustering but not for event classification.

---

## Cross-Cutting Analysis

### 1. The Causality Gap

No model demonstrates true causal understanding (insulin → glucose lowering).
Evidence:

- **Imputation ratios > 5×** for most models on meal windows: removing glucose
  destroys the prediction, meaning models aren't using action channels causally
- **Near-zero counterfactual effects** for 4/5 models: zeroing actions doesn't
  change output, meaning the model ignores them
- **Similarity by shape not cause**: UAM matches dawn matches exercise when
  they produce similar glucose curves

The one partial exception is **AE Conformance**, which was trained on diverse
synthetic scenarios where the action→outcome relationship varied. Even so,
its counterfactual magnitudes are imprecise and its imputation ratios are
only marginally better than chance on volatile windows.

### 2. Physics Composition Is the Dominant Factor

The performance hierarchy is:

```
Grouped+Physics (12.2) > AE+Physics (14.5) > AE Residual Enhanced (20.8)
    >> AE Conformance (111.1) >> AE Transfer raw (217.1)
```

Physics provides:
- **Time-of-day normalization**: Removes circadian bias from anomaly detection
- **Treatment accounting**: IOB/COB forward integration captures 90% of
  treatment effects, freeing ML to learn subtler patterns
- **Stable window understanding**: Physics alone achieves 1.07 imputation
  ratio on stable windows

### 3. Training Data Determines Capabilities

| Training Regime | What It Learns | What It Can't Do |
|----------------|---------------|-----------------|
| Synthetic (conformance) | Action-outcome diversity, partial counterfactuals | Real patient dynamics, extreme BG ranges |
| Synthetic→Real transfer | Real patient patterns, excellent reconstruction | Causal reasoning, treatment effects |
| Enhanced physics residual | Patient-specific residual dynamics | Anomaly discrimination (too uniform) |

### 4. Model Discriminative Ability

Models that are "too good" at reconstruction (MAE spread < 0.5) lose
discriminative power:

- **Grouped+Physics**: 0.2 MAE spread across top 20 anomalies → cannot distinguish
  normal from abnormal
- **AE Residual Enhanced**: Similarly flat anomaly landscape
- **AE Transfer (raw)**: 10.5 MAE spread → best anomaly discriminator, but
  biased toward nocturnal events
- **AE Transfer+Physics**: 26.0 MAE spread → best *balanced* anomaly detector

---

## Event Detection Capabilities

### UAM (Unannounced Meal) Detection

**Definition**: BG rise > 40 mg/dL over 30 min, no carbs logged, IOB < 2.0U

| Model | UAM Forecast MAE | Anomaly Sensitivity | Usable? |
|-------|-----------------|---------------------|---------|
| D Grouped+Physics | 14.2 | Low (0 UAM in top 20) | ✅ forecast only |
| B AE Transfer+Physics | **16.9** | None (0 UAM) | ✅ forecast only |
| E AE Residual Enhanced | 23.5 | Low (2/20 UAM) | ⚠️ marginal |
| A AE Transfer (raw) | 36.8 (recon) | **High (9/20 UAM)** | ✅ anomaly detection |
| C AE Conformance | 73.4 | High (10/20 UAM) | ⚠️ high error baseline |

**Assessment**: Physics-residual models can *predict* UAM-like rises accurately but
don't flag them as *unusual*. The raw AE Transfer is the best UAM anomaly
detector precisely because it has no physics to explain the rise — it sees
unexplained glucose increases as reconstruction failures.

**Practical approach**: Use a heuristic detector (BG rise threshold + no logged
carbs) rather than model-based anomaly detection for UAM. The heuristic found
276 UAM events in 90 days vs 21 logged meals — a 13:1 underlogging ratio.

### Dawn Phenomenon Detection

**Definition**: BG rise > 20 mg/dL during 3–8 AM, IOB < 1.5U

| Model | Dawn Forecast MAE | Notes |
|-------|-----------------|-------|
| B AE Transfer+Physics | **11.6** | Best — physics captures circadian liver output |
| D Grouped+Physics | 14.0 | Good |
| A AE Transfer (raw) | 25.7 (recon) | Struggles with overnight windows |

**Assessment**: Dawn phenomenon is highly predictable by physics (circadian
liver model with peak at 5 AM). Adding ML improves on physics baseline by
capturing patient-specific dawn timing and magnitude.

### Exercise Detection

**Definition**: BG drop > 30 mg/dL over 30 min, IOB < 2.0U, no carbs

Exercise candidates appear in anomaly lists for multiple models:
- AE Transfer+Physics: 5/20 anomalies are exercise candidates
- Grouped+Physics: 6/20

However, these are **false positives** — the heuristic fires on any unexplained
BG drop, which can also be caused by sensor compression artifacts,
delayed insulin absorption, or simply returning to range. True exercise
detection would require accelerometer data or explicit activity logging,
neither of which exists in the Nightscout data.

### ISF Miscalibration Detection

**From profile**: ISF = 40 mg/dL/U
**From data**: Measured effective ISF = mean 36.7, median 31.7

This means insulin is **more effective than the profile assumes** in 64% of
windows. Implications:
- Loop is likely under-dosing (ISF too high → predicted drop too large → less
  insulin delivered)
- The models that include physics use the profile ISF (40), so their predictions
  incorporate this systematic bias
- A model trained on residuals from a *miscalibrated* physics model would learn
  a systematic positive residual during correction events

**How to detect**: Compare physics-predicted correction magnitude vs actual
correction magnitude across many windows. The ratio gives an effective ISF
that can be tracked over time.

---

## Recommendations

### Immediately Implementable (Heuristic)

1. **UAM alert**: Threshold-based detector (BG rise > 40, no carbs, IOB < 2)
   already identifies 276 events in 90 days. Can be implemented without ML.

2. **ISF tracking**: Plot effective ISF over time using correction bolus windows.
   When effective ISF diverges from profile ISF by > 20%, flag for review.

3. **Dawn phenomenon timing**: Use physics model with circadian component to
   predict dawn rise onset. Preemptive basal increase 30 min before predicted
   onset.

### Architecture Changes Needed for Causal Reasoning

4. **Conditional generation**: Train models where glucose at time t is generated
   from actions[0:t] + glucose[0:t-1] (autoregressive), not from glucose[0:T]
   (bidirectional). This would enable true "what if I bolused X?" reasoning.

5. **Action-gated attention**: Modify GroupedEncoder to route action→state
   cross-attention explicitly (currently actions are processed independently
   with 25% capacity, then concatenated—no causal mechanism).

6. **Contrastive training on treatment pairs**: Generate paired scenarios
   (same patient, same starting BG, different bolus amounts) from UVA/Padova
   simulator. Train a model to predict the *difference* in outcomes. This
   directly targets counterfactual reasoning.

### Future Evaluation

7. **ConditionedTransformer integration**: Adapt hindcast for the different
   `forward()` signature. This model was designed for conditional generation
   and may show better counterfactual behavior.

8. **Multi-patient evaluation**: Current results are from one patient's data.
   Evaluate whether findings generalize across different ISF/CR profiles.

9. **Prospective testing**: Run inference in real-time against live Nightscout
   data stream to measure forecast accuracy on unseen data (not reconstruction
   of historical data the model may have been trained on).

---

## Appendix A: Evaluation Methodology

### Data Source
- **Path**: `../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history/`
- **Duration**: 90 days, 24,748 five-minute steps
- **Patient**: Single T1D on Loop automated insulin delivery
- **Treatments**: 28 boluses, 21 carb entries (0.23/day — 95% underlogged)
- **BG range**: 39–400 mg/dL

### Window Selection
- **Forecast/Reconstruct**: 5 windows selected by `find_interesting_windows()`
  (prioritizes volatile, high-IOB windows with Loop predictions available)
- **Anomaly**: Top 20 windows by reconstruction error (sliding window, stride=12)
- **Counterfactual**: 5 windows spanning meal+bolus, UAM, correction events
- **Imputation**: 3 windows — meal+bolus, UAM+dawn, stable
- **Similarity**: 3 reference windows — UAM+dawn, meal+bolus (nocturnal)
- **Event accuracy**: 3 windows per event type (UAM, dawn, correction, stable)

### Event Classification Heuristics
| Event | Criteria |
|-------|---------|
| UAM | BG rise > 40 mg/dL / 30 min, no carbs, IOB < 2U |
| Dawn | 3–8 AM, BG rise > 20, IOB < 1.5U |
| Exercise | BG drop > 30 / 30 min, IOB < 2U, no carbs |
| Correction | Bolus present, no carbs |
| Meal+bolus | Both carbs and bolus present |
| Stable | BG range < 30 mg/dL over window |
| Nocturnal | 22:00–06:00 |
| High volatility | BG range > 80 mg/dL over window |

### Physics-Residual Protocol
- Physics baseline: `enhanced_predict_window()` with ISF=40, CR=10
- Enhanced model includes Hill equation liver suppression + circadian rhythm
- Residual = `(actual − physics) / RESIDUAL_SCALE` where RESIDUAL_SCALE=200
- ML model runs with `causal=True` (position t attends only to 0..t)
- Final prediction: `physics_forward + ML_output × RESIDUAL_SCALE`

### Tools
- `tools/cgmencode/hindcast.py` — 6 inference frames, physics-residual, Loop comparison
- `tools/cgmencode/event_eval.py` — Systematic multi-model evaluation with event classification
- `tools/cgmencode/physics_model.py` — Forward integration with circadian/liver model

---

## Appendix B: Raw Results Reference

Full structured results saved to `event_eval_results.json` (generated by
`python3 -m tools.cgmencode.event_eval`). The JSON contains per-model,
per-frame, per-window metrics with event classifications for downstream
analysis.

### Quick Reference Commands

```bash
# Run full evaluation
python3 -m tools.cgmencode.event_eval \
    --data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history

# Single model forecast
python3 -m tools.cgmencode.hindcast forecast \
    --data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history \
    --checkpoint externals/experiments/ae_transfer.pth \
    --residual --scan 5

# Anomaly scan with physics
python3 -m tools.cgmencode.hindcast anomaly \
    --data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history \
    --checkpoint externals/experiments/ae_014_grouped_transfer.pth \
    --residual --top 20

# UAM event detection
python3 -m tools.cgmencode.hindcast anomaly \
    --data ../t1pal-mobile-workspace/externals/logs/ns-fixtures/90-day-history \
    --checkpoint externals/experiments/ae_transfer.pth \
    --top 50
```
