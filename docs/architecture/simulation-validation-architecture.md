# Simulation Validation Architecture

> How to ensure simulated CGM and treatment data reflects actual human experience,
> and how to use validated simulations for autonomous dosing algorithm improvement.

**Trace**: REQ-060, ALG-VERIFY-007, ALG-VERIFY-008, ALG-SCORE-001

---

## 1. Problem Statement

Simulated glucose and treatment data is essential for:

1. **Exhaustive algorithm testing** — real datasets are small and sparse
2. **Edge-case coverage** — rare but dangerous scenarios (DKA, site failures, compression lows)
3. **Autonomous algorithm improvement** — the autoresearch loop (`program.md`) needs
   unlimited scenario generation to explore the parameter space

But simulation is only useful if it's **calibrated against reality**. We've already observed
the core failure mode: **algorithm rankings reverse on synthetic vs real data**. Persistence
wins on cgmsim-lib's simplified engine (narrow 89–140 mg/dL range, MAE 2.3) while oref0
wins on real TV-* vectors (real variability, MAE 14.6). Any autonomous loop that optimizes
against uncalibrated simulation will converge on algorithms that are good at predicting
*simulations*, not *humans*.

---

## 2. Current Simulation Infrastructure

### 2.1 Engines

| Engine | Location | Model Type | Fidelity | Speed |
|--------|----------|------------|----------|-------|
| **cgmsim-lib CGMSIM** | `externals/cgmsim-lib/src/CGMSIMsimulator.ts` | Pharmacokinetic (ISF-based exponential decay) | Medium | Fast |
| **cgmsim-lib UVA/Padova** | `externals/cgmsim-lib/src/UVAsimulator.ts` | ODE physiological (8-equation T1DMS) | High | Moderate |
| **cgmsim-lib sensor models** | `externals/cgmsim-lib/src/lt1/core/sensors/` | CGM noise (Breton2008, Facchinetti2014, Vettoretti2018) | Configurable | — |
| **GluPredKit UVA/Padova** | `externals/GluPredKit/glupredkit/models/uva_padova.py` | ReplayBG identification + ODE replay | High | Slow |
| **GluPredKit Loop** | `externals/GluPredKit/glupredkit/models/loop.py` | PyLoopKit prediction engine | Algorithm-level | Moderate |

### 2.2 Integration Tools

| Tool | Location | Purpose |
|------|----------|---------|
| `in-silico-bridge.js` | `tools/aid-autoresearch/` | Generates SIM-* vectors via cgmsim-lib (7 scenarios × 3 patients) |
| `score-in-silico.js` | `tools/aid-autoresearch/` | Scores algorithms against SIM-* ground truth |
| `glupredkit_oref0_model.py` | `tools/aid-autoresearch/` | Wraps oref0 as GluPredKit BaseModel |
| `glupredkit_loop_model.py` | `tools/aid-autoresearch/` | Wraps Loop as GluPredKit BaseModel |
| `algorithm_score.py` | `tools/aid-autoresearch/` | Composite 6-metric scoring (in-silico = 10% weight) |

### 2.3 Generated Artifacts

- **35 SIM-* vectors** in `conformance/in-silico/vectors/`
- **~20 TV-*-synthetic vectors** in `conformance/t1pal/vectors/oref0-endtoend/`
- **GluPredKit example data**: `externals/GluPredKit/example_data/synthetic_data.csv` (6000 rows)

### 2.4 Known Limitation: Ranking Reversal

The simplified CGMSIM engine produces BG in 89–140 mg/dL — far narrower than real T1D
variability (SD 50–65 mg/dL, range frequently 40–350+). This causes:

- Persistence (just predict current BG) to score best on synthetic data
- Algorithms that handle variability well (oref0) to score best on real data
- Any composite score mixing uncalibrated synthetic + real data to produce misleading rankings

---

## 3. Validation Methodology: Detailed R&D Plan

### 3.1 Overview: What Data Ingestion Produces

Ingesting real-world T1D datasets produces **three distinct deliverables**, each serving
a different purpose in the validation and testing pipeline:

```
Real-World T1D Data (OhioT1DM, IOBP2, Tidepool, Nightscout, etc.)
       │
       ├─── (A) STATISTICAL FINGERPRINTS
       │         Per-population distribution parameters that calibrate
       │         the simulator to produce realistic output.
       │         "Make the simulator behave like these real humans."
       │
       ├─── (B) COMMON SCENARIO LIBRARY
       │         Classified, labeled segments extracted from real data
       │         representing the wide variety of actual human experiences.
       │         Weighted by frequency of occurrence.
       │         "These things happen to real people — the simulator must
       │          reproduce them, and algorithms must handle them."
       │
       └─── (C) RARE/IMPOSSIBLE EDGE CASE CATALOG
                 Scenarios that are never or rarely observed in real data
                 but represent safety-critical situations that algorithms
                 MUST handle correctly. Some are extracted from tail events
                 in real data; others are synthetically constructed.
                 "These things almost never happen — but when they do,
                  the algorithm must not kill the patient."
```

### 3.2 Deliverable A: Statistical Fingerprinting

#### 3.2.1 What Is a Statistical Fingerprint?

A fingerprint is a vector of ~30 distributional parameters extracted from a real T1D
data stream. It characterizes *what glucose data from this population looks like* without
containing any individual patient data. The fingerprint is the calibration target for the
simulator.

#### 3.2.2 Fingerprint Components

**Tier 1 — Glucose Distribution (minimum viable fingerprint)**

| Parameter | How Computed | Why It Matters |
|-----------|-------------|----------------|
| BG mean | `mean(CGM)` | Central tendency — primary A1C correlate |
| BG SD | `std(CGM)` | Overall variability — *this is what cgmsim-lib gets wrong* |
| BG CV | `100 × std/mean` | Normalized variability — ADA/ATTD consensus metric |
| BG P5, P25, P50, P75, P95 | Percentiles | Full shape of glucose distribution |
| TIR 70–180 | `%` of readings in range | Primary clinical outcome metric |
| TBR < 70 | `%` of readings below 70 | Hypoglycemia frequency |
| TBR < 54 | `%` of readings below 54 | Severe hypoglycemia frequency |
| TAR > 180 | `%` of readings above 180 | Hyperglycemia frequency |
| TAR > 250 | `%` of readings above 250 | Severe hyperglycemia frequency |
| MAGE | Mean Amplitude of Glycemic Excursions | Swing magnitude — captures post-meal dynamics |

**Tier 2 — Temporal Dynamics**

| Parameter | How Computed | Why It Matters |
|-----------|-------------|----------------|
| Mean |delta| per 5 min | `mean(\|CGM[t] - CGM[t-1]\|)` | Rate of change distribution |
| Delta SD | `std(CGM[t] - CGM[t-1])` | How "noisy" are transitions |
| Autocorrelation at lag 1–12 | Standard ACF | Smoothness / momentum |
| Spectral power 0–6 hr cycles | FFT | Circadian and meal periodicity |
| Overnight (00–06) mean | Nighttime CGM mean | Dawn phenomenon / basal adequacy |
| Daytime (06–22) mean | Daytime CGM mean | Meal/insulin interaction |
| Overnight vs daytime SD ratio | SD ratio | Nocturnal stability |

**Tier 3 — Treatment Patterns**

| Parameter | How Computed | Why It Matters |
|-----------|-------------|----------------|
| Total Daily Insulin (TDI) | `sum(insulin) per 24h` | Overall insulin need |
| Basal:Bolus ratio | `sum(basal) / sum(bolus)` per day | Treatment strategy |
| Boluses per day | Count of nonzero bolus events | Meal/correction frequency |
| Carbs per day | `sum(carbs)` per day | Dietary pattern |
| Mean carbs per meal event | Carbs when carbs > 0 | Meal size distribution |
| Bolus-to-meal timing (if available) | Lag between carbs and bolus events | Pre-bolus behavior |

**Tier 4 — Event Dynamics (Scenario Shapes)**

| Parameter | How Computed | Why It Matters |
|-----------|-------------|----------------|
| Post-meal peak amplitude | Max BG rise within 2h of carbs | Meal response magnitude |
| Post-meal peak timing | Minutes from carbs to BG peak | Absorption + bolus timing |
| Post-meal return-to-baseline time | Minutes to ±10% of pre-meal BG | Full meal cycle |
| Hypo nadir depth | Min BG during hypo episodes | Severity of lows |
| Hypo recovery time | Minutes from nadir to >70 mg/dL | How fast do lows resolve |
| Hypo frequency | Episodes per day below 70 | |

#### 3.2.3 How Many Samples Are Needed?

**For a single-patient fingerprint (e.g., Nightscout personal data):**

| Fingerprint Tier | Minimum Data | Recommended | Rationale |
|------------------|-------------|-------------|-----------|
| Tier 1 (distribution) | 3 days (864 readings) | 14 days (4,032 readings) | BG distribution stabilizes after ~2 weeks of continuous wear |
| Tier 2 (temporal) | 7 days | 28 days | Need full week for circadian patterns; 4 weeks for variability of variability |
| Tier 3 (treatment) | 14 days | 30 days | Need enough meal/bolus events to characterize patterns (~3 meals/day × 14 = 42 events minimum) |
| Tier 4 (event dynamics) | 14 days | 60+ days | Need ≥10 instances of each event type (post-meal, hypo, exercise) for shape extraction |

**For a population fingerprint (calibrating simulator for general use):**

| Tier | Subjects Needed | Days per Subject | Total Readings | Rationale |
|------|----------------|------------------|----------------|-----------|
| Tier 1 | ≥ 30 | 14 each | ~120K | Standard statistical sampling for distribution estimation; CLT confidence |
| Tier 2 | ≥ 30 | 28 each | ~240K | Need inter-subject variability in temporal patterns |
| Tier 3 | ≥ 50 | 14 each | ~200K | Treatment patterns vary enormously by AID vs MDI vs SAP |
| Tier 4 | ≥ 50 | 60 each | ~860K | Meal response shapes vary by individual insulin sensitivity |

**Key insight**: We don't need all tiers from a single dataset. Different datasets can
contribute to different tiers based on their strengths.

#### 3.2.4 The Matching Algorithm

Statistical matching uses **distributional distance metrics** to quantify how close
simulated data is to the fingerprint target:

```
For each fingerprint parameter P:

  1. Extract P_real from reference dataset
  2. Generate N hours of synthetic data from simulator
  3. Extract P_sim from synthetic data
  4. Compute distance d(P_real, P_sim)
  5. If d > threshold_P → adjust simulator parameters and repeat

Distance metrics by parameter type:
  • Single scalars (mean, SD, CV, TIR):
      d = |P_real - P_sim| / P_real    (relative error)
      Threshold: 10% for Tier 1, 20% for Tier 2–4

  • Distributions (BG histogram, delta histogram):
      d = Wasserstein_1(P_real, P_sim)  (Earth Mover's Distance)
      or KL(P_real || P_sim)            (KL divergence)
      Threshold: Wasserstein < 10 mg/dL or KL < 0.1

  • Time-series shapes (meal response, hypo recovery):
      d = DTW(shape_real, shape_sim)     (Dynamic Time Warping)
      Threshold: DTW < 15 mg/dL·min (normalized)

  • Autocorrelation / spectral:
      d = RMSE(ACF_real, ACF_sim)       over lags 1–72 (6 hours)
      Threshold: RMSE < 0.05
```

**Calibration knobs** (what gets adjusted to reduce distance):

| Simulator Parameter | Affects Fingerprint |
|---------------------|---------------------|
| Patient ISF range | BG SD, CV, MAGE |
| Patient CR range | Post-meal peak amplitude |
| CGM noise model (Breton2008 σ) | BG SD, delta SD |
| Meal timing jitter (σ minutes) | Post-meal peak timing variance |
| Carb estimation error (σ %) | Post-meal amplitude variance |
| Liver glucose production rate | Overnight mean, dawn phenomenon |
| Basal rate range | TIR, overnight stability |
| Missed bolus probability | TAR > 180, meal response amplitude |
| Insulin absorption variability (σ %) | IOB prediction error, hypo frequency |

### 3.3 Deliverable B: Common Scenario Library

#### 3.3.1 What Is a Classified Scenario?

A scenario is a labeled, time-bounded segment extracted from real data representing
a recognizable human experience. Scenarios are classified by **type**, **frequency**,
and **difficulty** for the dosing algorithm.

#### 3.3.2 Scenario Detection and Extraction

Scenarios are extracted from real CGM+treatment data using event detection rules:

```
For each 5-minute-resolution data stream:

  1. MEAL EVENT: carbs > 0 within any 15-min window
     → Extract 30 min before through 4 hours after
     → Classify: adequate bolus / underbolus / overbolus / missed bolus
     → Record: pre-meal BG, carbs, bolus, peak BG, peak time, TIR during segment

  2. HYPO EVENT: CGM < 70 for ≥ 15 min (3 consecutive readings)
     → Extract 1 hour before through 2 hours after
     → Classify: fasting hypo / post-exercise / post-bolus / nocturnal
     → Record: nadir, duration < 70, recovery time, treatment (carbs if any)

  3. EXERCISE EVENT: heartrate > resting+30 OR workout_label not null
     → Extract 30 min before through 6 hours after (delayed effects)
     → Classify: aerobic / anaerobic / mixed
     → Record: duration, intensity, BG drop, delayed hypo (yes/no)

  4. OVERNIGHT SEGMENT: 22:00–07:00 daily
     → Classify: stable / dawn phenomenon / nocturnal hypo / post-dinner tail
     → Record: mean, SD, min, max, slope after 03:00

  5. HIGH VARIABILITY SEGMENT: CV > 50% over any 4-hour window
     → These represent "hard days" — the algorithm's biggest challenges
     → Classify by cause: missed bolus + correction stacking, illness, site change
```

#### 3.3.3 Frequency-Weighted Scenario Categories

Based on published literature and real-data analysis, these are approximate frequencies
of different scenarios in typical T1D daily experience:

**Common (daily occurrence, >80% of days):**

| Scenario | Frequency | Data Source for Calibration |
|----------|-----------|---------------------------|
| Meal with adequate pre-bolus | 2–3× daily | All datasets with carbs + bolus |
| Overnight stable (±30 mg/dL) | Most nights | OhioT1DM, IOBP2, Tidepool |
| Mild post-meal spike (180–250) | 1–2× daily | All datasets |
| BG within range for 4+ hours | Most days | All datasets |
| Basal-only period (fasting) | 6–10 hr/day | All datasets |

**Frequent (weekly occurrence, 30–80% of weeks):**

| Scenario | Frequency | Data Source |
|----------|-----------|-------------|
| Mild hypo (55–70, <30 min) | 2–5× /week | OhioT1DM, IOBP2 |
| Late/missed pre-bolus | 3–5× /week | Nightscout, Tidepool |
| Post-meal exercise | 2–3× /week | T1DEXI, OhioT1DM |
| Dawn phenomenon (>20 mg/dL rise 3–7am) | 3–5× /week | OhioT1DM, IOBP2 |
| Correction bolus stacking | 1–2× /week | Nightscout, Tidepool |
| Extended high (>250 for 2+ hrs) | 1–2× /week | All datasets |

**Uncommon (monthly, 10–30% of months):**

| Scenario | Frequency | Data Source |
|----------|-----------|-------------|
| Severe hypo (<54 for >15 min) | 1–4× /month | IOBP2, OhioT1DM |
| Missed bolus entirely | 2–4× /month | Nightscout (logged manually) |
| High-fat/protein extended meal | 2–4× /month | Nightscout (annotated) |
| Alcohol-related delayed hypo | 1–2× /month | OhioT1DM (self-report) |
| Intense exercise (>1 hr) | 2–4× /month | T1DEXI |
| Site/sensor change day | 1–2× /month | Tidepool, Nightscout |

**Rare (yearly, <5% probability per month):**

| Scenario | Frequency | Data Source |
|----------|-----------|-------------|
| Pump site failure (no insulin delivery) | 1–4× /year | Nightscout (elevated BG + no IOB response) |
| Sensor failure (multi-hour gap) | 2–6× /year | All datasets (CGM NaN gaps) |
| Illness (elevated BG for days) | 2–6× /year | Longitudinal Nightscout data |
| Double/accidental bolus | 1–3× /year | Nightscout treatment logs |
| DKA event | 0–1× /year | Extremely rare in datasets |

### 3.4 Deliverable C: Rare/Impossible Edge Case Catalog

These are scenarios that may **never appear** in any real dataset but represent
conditions the algorithm must handle safely. They are generated synthetically
based on known failure modes.

#### 3.4.1 Impossible But Required

| Edge Case | Real Probability | Why Test It | How to Generate |
|-----------|-----------------|-------------|-----------------|
| BG drops from 200→40 in 15 min | Essentially 0 | Sensor malfunction; algorithm must not crash | Synthetic: inject step function |
| 200g carbs, no bolus | Very rare | Toddler gets into candy; algorithm must respond | Synthetic: massive carbs event |
| Basal rate 0 for 12 hours | Rare (site failure) | Must detect and alert | Synthetic: zero all basal |
| Two 10U boluses 5 min apart | Very rare (double tap) | Must detect overdose risk | Synthetic: duplicate bolus |
| CGM reads 400 for 6 hours | Rare (sensor error or DKA) | Must not over-correct indefinitely | Synthetic: flat high line |
| Negative CGM delta of -80 mg/dL in one reading | Compression low artifact | Must recognize as artifact | Synthetic: single-point drop |
| No CGM data for 2 hours then resumes | Sensor warmup / dropout | Must safely resume | Synthetic: NaN gap |
| Profile reports ISF=500 (data entry error) | Config error | Must sanity-check inputs | Synthetic: extreme profile |

#### 3.4.2 Relationship Between Deliverables

```
                    Calibrated Simulator
                          │
           ┌──────────────┼──────────────┐
           │              │              │
           ▼              ▼              ▼
   (A) Fingerprints   (B) Scenario    (C) Edge Cases
   calibrate the      Library tests   test safety
   simulator           prediction     invariants
   realism             quality         and robustness
           │              │              │
           │              │              │
           ▼              ▼              ▼
   "Sim output       "Algorithm      "Algorithm
    matches real       handles         doesn't
    distributions"     common life"    kill anyone"
           │              │              │
           └──────────────┼──────────────┘
                          ▼
                  algorithm_score.py
                  (composite metric)
```

### 3.5 Reference Datasets: Complete Catalog

GluPredKit has working parsers for 12 real-world T1D datasets. All normalize to the same
5-minute resolution DataFrame schema: `[date, id, CGM (mg/dL), insulin (U), carbs (g),
basal (U), bolus (U), is_test]` plus optional columns (heartrate, exercise, demographics).

#### 3.5.1 Large-Scale Datasets (Fingerprint Calibration)

| Dataset | Parser | Subjects | Data Points | Insulin Modality | Exercise | Demographics | Access |
|---------|--------|----------|-------------|-----------------|----------|-------------|--------|
| **IOBP2** | `IOBP2.py` | 332 | 9.7M | AID (iLet Bionic Pancreas) | — | Age, gender, weight, height, ethnicity | Pipe-delimited files |
| **T1DEXI** | `t1dexi.py` | 414 pump | >2M est | SAP (various pumps) | ✓ HR, steps, calories, workout labels | Age, gender, height, weight | SAS .xpt files |
| **Tidepool-JDRF** | `tidepool_dataset.py` | 300+ | Large | Mixed (HCL, SAP) | ✓ workout labels | Age, gender | CSV train/test |
| **OpenAPS Data Commons** | `open_aps.py` | 142 | Large | AID (OpenAPS/AndroidAPS) | — | — | ZIP archives |

**These four datasets together provide >10M data points across >1,000 subjects
spanning AID, SAP, and MDI modalities.** This is more than sufficient for
population-level fingerprinting (Tiers 1–3).

#### 3.5.2 Rich-Feature Datasets (Scenario Extraction)

| Dataset | Parser | Subjects | Special Features | Best For |
|---------|--------|----------|------------------|----------|
| **OhioT1DM** | `ohio_t1dm.py` | 12 | HR, skin temp, galvanic skin response, acceleration, exercise, air temp | Scenario shape extraction — richest per-subject feature set |
| **BrisT1D** | `brist1d.py` | 22 | HR, steps, calories, activity labels, multiple AID systems (780G, Omnipod 5, Control-IQ) | Multi-device comparison; UK demographics |
| **T1D-UOM** | `t1d_uom.py` | 14 | Steps, calories, walking/running labels, MDI + pump mix | Exercise scenario extraction |
| **HUPA-UCM** | `hupa_ucm.py` | 26 | HR, steps, calories, activity; includes MDI subjects | SAP vs MDI comparison |

**These datasets are smaller but contain the physiological signals (heart rate,
activity, skin temperature) needed for Tier 4 event dynamics extraction.**

#### 3.5.3 Specialized Datasets

| Dataset | Parser | Subjects | Focus |
|---------|--------|----------|-------|
| **AZT1D** | `azt1d.py` | 23 | Older adults (age 27–80), Control-IQ, sleep/exercise device modes |
| **CTR3** | `ctr3.py` | Multi | Control-to-Range trial, Roche/JAEB AID |
| **Shanghai T1DM** | `shanghai_t1dm.py` | Multi | East Asian demographics, CSII + MDI, different dietary patterns |
| **DiaTrend** | `diatrend.py` | Multi | European cohort |

#### 3.5.4 Live/Personal Data Sources

| Source | Parser | Subjects | Notes |
|--------|--------|----------|-------|
| **Nightscout API** | `nightscout.py` | 1+ per instance | Loop/AAPS/Trio device data; profile switches; temp basals; overrides |
| **Tidepool API** | `tidepool.py` | 1+ per login | Live data pull with OAuth; handles timezone |
| **Apple Health** | `apple_health.py` | 1 | iPhone export; HR, HRV, resting HR, workouts, steps |

#### 3.5.5 Data Source Quality Attributes

Not all datasets are equally useful for all purposes. Key quality attributes:

| Attribute | Why It Matters | Best Sources |
|-----------|---------------|-------------|
| **CGM continuity** | Gaps break temporal analysis | IOBP2, Tidepool (pump-connected CGM has fewer gaps) |
| **Insulin granularity** | Need basal + bolus separated, not just total | OhioT1DM, AZT1D, CTR3, Nightscout (all separate basal/bolus) |
| **Carb logging completeness** | Missed meals bias fingerprints | OhioT1DM (study protocol enforced logging), T1DEXI |
| **Activity signals** | Exercise scenario extraction | T1DEXI (gold standard), OhioT1DM, BrisT1D |
| **AID algorithm variety** | Compare Loop vs AAPS vs 780G | BrisT1D (780G, Omnipod 5), OpenAPS, Nightscout |
| **Demographic diversity** | Avoid overfitting to one population | Shanghai (East Asian), IOBP2 (multi-ethnic), AZT1D (older adults) |
| **Longitudinal duration** | Seasonal, illness, hormonal effects | Nightscout (months/years), Tidepool API |

### 3.6 Statistical Fingerprint Targets

Based on published T1D population data (ADA Standards of Care 2024, ATTD consensus 2019,
IOBP2 trial results, OhioT1DM characterization papers):

| Metric | Well-Controlled T1D | Average T1D | Poorly Controlled |
|--------|---------------------|-------------|-------------------|
| Mean BG (mg/dL) | 130–145 | 154 (A1C ~7%) | 180–220 |
| BG SD (mg/dL) | 35–45 | 50–65 | 70–90 |
| CV (%) | 25–33 | 33–40 | 40–55 |
| TIR 70–180 | > 70% | 50–70% | < 50% |
| TBR < 70 | < 4% | 4–10% | variable |
| TBR < 54 | < 1% | 1–3% | variable |
| TAR > 180 | < 25% | 25–45% | > 50% |
| MAGE (mg/dL) | 60–80 | 80–120 | 120–160 |
| Mean \|delta\| per 5 min | 2–4 mg/dL | 4–7 mg/dL | 6–10 mg/dL |
| TDI (U/day) | 25–50 | 30–60 | variable |
| Boluses per day | 4–8 | 3–6 | 2–4 |

**The simulator must produce virtual patients spanning ALL THREE COLUMNS.** An algorithm
that only works on well-controlled patients is useless for the majority of T1D experience.

The current cgmsim-lib CGMSIM engine produces data resembling the "well-controlled" column
at best — it lacks the variability to represent average or poorly-controlled T1D.

### 3.7 Clinical Evaluation Metrics

GluPredKit provides 15 clinical metrics that should be used to evaluate both simulation
realism and algorithm performance. These map directly to regulatory standards:

#### 3.7.1 FDA/Regulatory-Grade Metrics

| Metric | Module | What It Measures | Regulatory Use |
|--------|--------|-----------------|----------------|
| **Clarke Error Grid** | `metrics/clarke_error_grid.py` | Zone A–E classification of prediction accuracy | ISO 15197, FDA glucose monitor clearance |
| **Parkes Error Grid** | `metrics/parkes_error_grid.py` | Refined zone classification (stricter than Clarke) | International standard, replacing Clarke |
| **MAE** | `metrics/mae.py` | Mean absolute prediction error | FDA primary accuracy metric |
| **RMSE** | `metrics/rmse.py` | Root mean square error | FDA primary accuracy metric |
| **ME (Bias)** | `metrics/me.py` | Systematic over/under prediction | Required for regulatory assessment |

#### 3.7.2 Safety-Critical Metrics

| Metric | Module | What It Measures | Clinical Significance |
|--------|--------|-----------------|----------------------|
| **MCC Hypo** | `metrics/mcc_hypo.py` | Matthews correlation for <70 mg/dL detection | Balanced hypo sensitivity/specificity |
| **MCC Hyper** | `metrics/mcc_hyper.py` | Matthews correlation for >180 mg/dL detection | Balanced hyper sensitivity/specificity |
| **Glycemia Detection** | `metrics/glycemia_detection.py` | 3×3 confusion matrix (hypo/target/hyper) | Shows misclassification patterns |
| **gRMSE** | `metrics/grmse.py` | RMSE with severity weighting (penalizes hypo errors 1.5×) | Clinically-weighted accuracy |

#### 3.7.3 Prediction Quality Metrics

| Metric | Module | What It Measures |
|--------|--------|-----------------|
| **Temporal Gain** | `metrics/temporal_gain.py` | Minutes of predictive lead time via cross-correlation |
| **G-Mean** | `metrics/g_mean.py` | Geometric mean of per-class recall (hypo/target/hyper) |
| **Parkes Exp Cost** | `metrics/parkes_error_grid_exp.py` | Exponentially-weighted zone accuracy (zone A maximized) |
| **PCC** | `metrics/pcc.py` | Pearson correlation (trend tracking quality) |
| **MARE / MRE** | `metrics/mare.py`, `mre.py` | Relative error metrics (% of true value) |

---

## 4. Gaps in Current Simulation

### 4.1 Physiological Noise Missing from CGMSIM Engine

| Factor | Real World | Current Simulation | Impact |
|--------|------------|--------------------|--------|
| CGM sensor noise | ±15–20% MARD | Clean signal (none) | Algorithms overtrained on perfect data |
| Carb estimation error | ±30–50% systematic bias | Exact carbs specified | Underestimates real meal response variance |
| Meal timing jitter | ±15–30 min from intended | Exact timestamp | Missing bolus-meal mismatch scenarios |
| Missed/late bolus | ~20% of meals in real data | All boluses given | Missing most common real-world failure |
| Compression lows | Common during sleep | Not modeled | False hypo signals not tested |
| Sensor dropout/warmup | Hours of missing data | Continuous signal | Missing data handling untested |
| Multi-day ISF drift | Illness, cycle, stress | Fixed ISF per run | Autosens/dynamic-ISF not exercised |
| Insulin absorption variability | ±20–30% per injection | Deterministic decay | IOB model precision overstated |

### 4.2 Available but Not Integrated

cgmsim-lib's `lt1/core/sensors/` directory contains CGM noise models
(Breton2008, Facchinetti2014, Vettoretti2018/2019) that are used by the UVA/Padova
simulator but **not by the CGMSIM engine** that `in-silico-bridge.js` uses. The
UVA/Padova engine with these sensor models would produce significantly more realistic
output, but integration requires:

1. State persistence between 5-minute ticks (UVA needs `lastState`)
2. ODE solver initialization with steady-state finder
3. Treatment format conversion to UVA's input schema

### 4.3 Scenario Coverage Gaps

Current 7 scenarios in `in-silico-bridge.js`:

```
✅ meal-rise          (adequate bolus)
✅ meal-underbolus    (50% bolus)
✅ fasting-flat       (stable basal)
✅ hypo-recovery      (BG 65 + carb correction)
✅ dawn-phenomenon    (cortisol rise)
✅ exercise           (post-meal exercise)
✅ multi-meal         (breakfast + lunch + snack)
```

Missing scenarios needed for realistic coverage:

```
❌ missed-bolus       (meal with no bolus — extremely common)
❌ double-bolus       (accidental re-dose)
❌ site-change        (insulin absorption disruption)
❌ sensor-warmup      (2-hour CGM gap after new sensor)
❌ compression-low    (false low during sleep)
❌ illness            (rising ISF, elevated BG for hours)
❌ alcohol-evening    (delayed hypo risk next morning)
❌ high-fat-meal      (extended carb absorption, 4-6 hr tail)
❌ stacking           (multiple corrections → hypo)
❌ rebound-high       (overtreatment of low → spike)
❌ exercise-delayed   (hypo 6-12 hrs after exercise)
❌ adrenaline-spike   (stress/competition → transient high)
```

---

## 5. Calibration Pipeline Architecture

### 5.1 Fingerprint Extraction

```
Real Dataset (OhioT1DM, Nightscout, Tidepool)
       │
       ▼
┌──────────────────────┐
│ Statistical           │
│ Fingerprint Extractor │
│                       │
│ • BG distribution     │    Output: fingerprint.json
│ • Time-in-range       │    {
│ • Meal response shape │      "bg_mean": 154,
│ • Overnight pattern   │      "bg_sd": 58,
│ • Insulin delivery    │      "cv": 37.7,
│ • Glycemic variability│      "tir_70_180": 0.62,
│ • Hypo frequency      │      "meal_peak_mg": 72,
│ • Carb:bolus patterns │      "meal_peak_min": 68,
│                       │      ...
└──────────────────────┘    }
```

### 5.2 Simulation Calibration Loop

```
fingerprint.json (target)
       │
       ▼
┌──────────────────────────────────────────────────────┐
│ Calibration Controller                                │
│                                                       │
│ 1. Generate N hours of synthetic data                 │
│    (in-silico-bridge.js with current patient params)  │
│                                                       │
│ 2. Extract synthetic fingerprint                      │
│                                                       │
│ 3. Compute distance metrics:                          │
│    • Wasserstein distance on BG distribution           │
│    • Absolute error on TIR buckets                    │
│    • DTW on meal response shape template              │
│    • KL divergence on glycemic variability            │
│                                                       │
│ 4. If distance > threshold:                           │
│    • Adjust patient profiles (ISF, CR, noise params)  │
│    • Enable/tune CGM noise model                      │
│    • Add meal timing jitter, carb estimation error    │
│    • Re-run from step 1                               │
│                                                       │
│ 5. If distance < threshold:                           │
│    • Lock calibrated patient profiles                 │
│    • Generate conformance vectors                     │
│    • Proceed to algorithm scoring                     │
└──────────────────────────────────────────────────────┘
```

### 5.3 Integration with Autoresearch Loop

```
┌─────────────────────────────────────────────────────────────┐
│                  AUTONOMOUS ALGORITHM LOOP                   │
│                  (program.md experiment cycle)               │
│                                                              │
│  Data Sources (weighted by calibration confidence):          │
│                                                              │
│  ┌─────────────────────┐  ┌──────────────────────┐          │
│  │ Real TV-* Vectors   │  │ Calibrated SIM-*     │          │
│  │ (phone captures)    │  │ (validated synthetic) │          │
│  │                     │  │                       │          │
│  │ Weight: ~35%        │  │ Weight: ~25%          │          │
│  │ Vectors: ~85        │  │ Vectors: unlimited    │          │
│  │ Fidelity: ground    │  │ Fidelity: calibrated  │          │
│  │           truth     │  │           against real │          │
│  └────────┬────────────┘  └────────┬─────────────┘          │
│           │                        │                         │
│  ┌────────▼────────────┐  ┌────────▼─────────────┐          │
│  │ Safety Boundary     │  │ Adversarial Edge     │          │
│  │ Vectors             │  │ Cases                │          │
│  │                     │  │                       │          │
│  │ Weight: HARD GATE   │  │ Weight: ~15%          │          │
│  │ Vectors: 12+        │  │ Vectors: 50+          │          │
│  │ ANY fail → score 0  │  │ Intentionally extreme │          │
│  └────────┬────────────┘  └────────┬─────────────┘          │
│           │                        │                         │
│           └──────────┬─────────────┘                         │
│                      ▼                                       │
│           algorithm_score.py                                 │
│           (composite: 0.0 – 1.0)                             │
│                      │                                       │
│                      ▼                                       │
│           KEEP (improved + safe)                             │
│           DISCARD (regressed or unsafe)                      │
│                      │                                       │
│                      ▼                                       │
│           param-mutation-engine.js                           │
│           (propose next change)                              │
│                      │                                       │
│                      └────────── LOOP FOREVER                │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. R&D Phases

### Phase 1: Fingerprint Extraction (Foundation)

Build the statistical fingerprint extractor and run it against available datasets.

**Inputs**: OhioT1DM (12 subjects, immediate access), IOBP2 (332 subjects, largest),
Nightscout personal data (unlimited, live).

**Outputs**:
- `fingerprint.json` schema definition
- Per-dataset fingerprint files
- Population-level aggregate fingerprint with confidence intervals
- Visualization: real vs simulated BG distributions

**Key decision**: Which datasets to prioritize for initial calibration.
OhioT1DM is small but richly featured. IOBP2 is huge but lacks exercise data.
Recommend starting with OhioT1DM for Tier 1–4 extraction, then validating scale
with IOBP2 for Tier 1–2.

### Phase 2: Scenario Extractor and Classifier

Build the event detection pipeline that segments real data into classified scenarios.

**Inputs**: Fingerprinted datasets from Phase 1.

**Outputs**:
- Scenario library (labeled segments with metadata)
- Frequency distribution table (how often each scenario type occurs)
- Template shapes (average meal response, average hypo trajectory, etc.)
- Scenario difficulty rating (based on algorithm prediction error)

### Phase 3: Simulator Calibration Loop

Wire the fingerprint → simulator → compare → adjust cycle.

**Inputs**: Population fingerprint, cgmsim-lib UVA/Padova engine + sensor noise models.

**Outputs**:
- Calibrated patient profiles (replacing current standard/sensitive/resistant)
- Noise/jitter parameter settings
- Validated SIM-* vectors with fingerprint conformance certificates
- Before/after comparison showing BG distribution widening

### Phase 4: Scoring Integration

Update `algorithm_score.py` with calibrated synthetic data and clinical metrics.

**Inputs**: Calibrated SIM-* vectors, GluPredKit clinical metrics.

**Outputs**:
- Updated scoring weights (promoting calibrated synthetic, adding clinical metrics)
- Clarke/Parkes error grid integration
- MCC hypo/hyper as safety sub-scores
- Composite score validated against known algorithm rankings on real data

### Phase 5: Autonomous Loop with Validated Simulation

Full autoresearch cycle using calibrated simulation for unlimited scenario generation.

**Inputs**: All of the above.

**Outputs**:
- Algorithm mutations scored against realistic synthetic + real + edge case data
- Confidence that score improvements transfer to real-world performance
- Regression test suite that catches ranking-reversal problems

---

## 7. Recommended Scoring Weight Rebalance

### Current Weights (`algorithm_score.py`)

```
20%  decision agreement (rate divergence from e2e vectors)
20%  prediction trajectory MAE (captured vs reconstructed)
20%  strict conformance pass rate (e2e vectors)
15%  trajectory direction agreement
10%  robustness (xval + in-silico)        ← synthetic under-weighted
 5%  simplicity bonus
```

### Proposed Weights (after simulation calibration)

```
25%  decision agreement on real TV-* vectors
20%  prediction trajectory MAE on real TV-* vectors
15%  calibrated synthetic scenario pass rate     ← promoted from 10%
15%  clinical metrics (Clarke/Parkes zone A+B %)  ← NEW
10%  adversarial edge case survival rate          ← NEW
10%  trajectory direction agreement
 5%  simplicity bonus
───
HARD GATE: safety boundary vectors (any fail → score 0.0)
```

---

## 8. Key Architectural Decisions

### Why Two Simulation Engines?

| | CGMSIM (simplified) | UVA/Padova (ODE) |
|---|---|---|
| **Use for** | Fast scenario sweep, parameter exploration | Calibration-grade validation vectors |
| **Speed** | ~1 ms per 5-min tick | ~10–50 ms per 5-min tick |
| **Noise** | Must add externally | Built-in sensor models |
| **State** | Stateless (recalculates from history) | Stateful (13-variable ODE state) |
| **Limitation** | Narrow BG range without noise | Requires initialization, slower |

**Strategy**: Use CGMSIM for the fast inner loop of autoresearch (thousands of parameter
sweeps), use UVA/Padova for the calibration validation layer (confirm that results hold
on higher-fidelity simulation).

### Why Real Data Is Irreplaceable

Simulation cannot capture:

- **Behavioral patterns** — real people forget boluses in predictable ways
- **Device-specific artifacts** — Dexcom G7 vs Libre 3 noise profiles differ
- **Multi-day dynamics** — illness progression, hormonal cycles, travel
- **Psychosocial factors** — alarm fatigue, diabetes distress, override decisions

Real TV-* vectors from phone captures must always carry the highest scoring weight.
Simulation expands coverage; it doesn't replace ground truth.

---

## 9. Source File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `externals/cgmsim-lib/src/CGMSIMsimulator.ts` | ~100 | Simplified simulator entry point |
| `externals/cgmsim-lib/src/UVAsimulator.ts` | ~100 | UVA/Padova simulator entry point |
| `externals/cgmsim-lib/src/sgv.ts` | ~60 | Core glucose calculation |
| `externals/cgmsim-lib/src/liver.ts` | ~60 | Hepatic glucose production model |
| `externals/cgmsim-lib/src/lt1/core/models/UvaPadova_T1DMS.ts` | ~300 | FDA T1DMS ODE model |
| `externals/cgmsim-lib/src/lt1/core/sensors/Breton2008.ts` | — | CGM noise model |
| `externals/GluPredKit/glupredkit/models/uva_padova.py` | ~120 | ReplayBG-based UVA/Padova |
| `externals/GluPredKit/glupredkit/models/loop.py` | ~80 | PyLoopKit prediction wrapper |
| `externals/GluPredKit/glupredkit/parsers/ohio_t1dm.py` | ~170 | OhioT1DM real data parser |
| `externals/GluPredKit/glupredkit/parsers/nightscout.py` | ~540 | Nightscout API data parser |
| `externals/GluPredKit/glupredkit/parsers/tidepool_dataset.py` | — | Tidepool dataset parser |
| `externals/GluPredKit/glupredkit/metrics/` | 15 files | Clinical evaluation metrics |
| `tools/aid-autoresearch/in-silico-bridge.js` | ~550 | Scenario generation via cgmsim-lib |
| `tools/aid-autoresearch/score-in-silico.js` | ~250 | Algorithm scoring against SIM-* vectors |
| `tools/aid-autoresearch/algorithm_score.py` | ~330 | Composite 6-metric scoring |
| `tools/aid-autoresearch/glupredkit_oref0_model.py` | ~390 | oref0→GluPredKit wrapper |
| `tools/aid-autoresearch/glupredkit_loop_model.py` | — | Loop→GluPredKit wrapper |
| `tools/aid-autoresearch/program.md` | ~70 | Autoresearch loop specification |
| `conformance/in-silico/vectors/` | 35 files | Generated SIM-* conformance vectors |

---

## 10. Related Requirements and Gaps

| ID | Description |
|----|-------------|
| REQ-060 | Algorithm validation infrastructure |
| ALG-VERIFY-007 | In-silico bridge generates synthetic scenarios |
| ALG-VERIFY-008 | In-silico scoring against synthetic ground truth |
| ALG-SCORE-001 | Composite algorithm scoring pipeline |
| GAP-ALG-010 | *Proposed*: cgmsim-lib CGMSIM engine produces unrealistically narrow BG range |
| GAP-ALG-011 | *Proposed*: No CGM sensor noise in CGMSIM-engine-generated vectors |
| GAP-ALG-012 | *Proposed*: No meal timing/estimation error in synthetic scenarios |
| GAP-ALG-013 | *Proposed*: No statistical calibration pipeline (real → synthetic fingerprint matching) |
| GAP-ALG-014 | *Proposed*: Clinical metrics (Clarke/Parkes) not integrated into algorithm_score.py |
| GAP-ALG-015 | *Proposed*: Missing 12+ common real-world scenarios (missed bolus, site change, etc.) |
