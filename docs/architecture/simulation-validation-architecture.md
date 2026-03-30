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

**Always Present (background conditions, not discrete events):**

These are not scenarios in the traditional sense — they are **persistent background
states** that modulate how every scenario plays out. See §4.3 for the full two-layer
patient model.

| Background Condition | Prevalence | Typical Mismatch | Data Source |
|---------------------|-----------|-----------------|-------------|
| Suboptimal basal rates | ~70% of patients | ±15–30% from true need | Autotune/autosens logs in OpenAPS Data Commons |
| ISF wrong for time of day | ~80% (single ISF configured, physiology varies) | ±20–40% at night vs day | Retrospective correction analysis |
| CR wrong for meal type | ~60% (single CR, varied meals) | ±30% (pizza vs fruit) | Post-meal BG residuals in any dataset |
| Pump site >3 days old | ~30% of any given day | −10–25% absorption | Nightscout site-change events |
| Menstrual cycle (luteal phase) | ~15% of days (50% of T1D population) | ISF −20–40% | T1DEXI (gender + BG patterns), REPLACE-BG |
| Dawn phenomenon (active) | ~60% of patients, ~20% of hours | Basal need +30–60% at 3–8 AM | All overnight datasets |
| Stale settings (>30 days unchanged) | ~50% of patients | Drift of ±10–20% from optimal | Nightscout profile history |
| Untracked insulin (pen + pump) | ~5–15% of patients | 0–6 U phantom IOB | OpenAPS Data Commons self-reports |

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

### 4.3 The Therapy Settings Mismatch Problem (Critical)

**This is the single most important gap in the current simulation framework.**

The simulator defines a patient with `ISF: 40, CR: 10, basalRate: 1.0` and the
algorithm is configured with the *same* values. This means the simulation only tests
the algorithm in the **ideal case where therapy settings are correct**.

In reality, **most patients most of the time are running with suboptimal settings**:

#### 4.3.1 Profile-vs-Reality Mismatch

In real T1D management, the algorithm's configured therapy settings (the "profile")
almost never perfectly match the patient's true physiological parameters at any given
moment. This mismatch is the **dominant source of glycemic variability** — far more
significant than CGM noise or meal timing jitter.

| Mismatch Type | Real-World Prevalence | Impact |
|---------------|----------------------|--------|
| **Basal rate too high/low** | Extremely common — most patients | Persistent drift up or down, especially overnight |
| **ISF wrong by ±30–50%** | Nearly universal — ISF varies by time of day, activity level, hormonal state | Corrections overshoot or undershoot consistently |
| **CR wrong by ±20–40%** | Very common — CR varies by meal type and time of day | Systematic post-meal highs or lows |
| **DIA shorter than actual** | Common — many users set 3–4h when reality is 5–6h | IOB underestimated → insulin stacking |
| **Settings stale for months** | Extremely common — weight change, season, life change | Gradual performance degradation |

#### 4.3.2 Physiological Confounders That Shift True Parameters

Even if settings were perfect yesterday, the patient's *true* ISF/CR/basal needs
shift constantly due to factors the algorithm cannot directly observe:

**Hormonal / Metabolic:**

| Factor | Effect on Physiology | Duration | Frequency |
|--------|---------------------|----------|-----------|
| Menstrual cycle (luteal phase) | ISF drops 15–40%, basal needs rise 20–30% | 5–7 days/month | Monthly in ~50% of patients |
| Pregnancy (progressive) | ISF drops dramatically over trimesters | Months | — |
| Dawn phenomenon (cortisol) | ISF drops 20–50% between 3–8 AM | Daily, 3–6 hours | Daily in ~60% of patients |
| Illness / infection | ISF drops 30–70%, hepatic glucose rises | Days to weeks | Several times/year |
| Stress / adrenaline | Hepatic glucose dump, ISF drops acutely | Minutes to hours | Frequent |
| Growth hormone (children) | Basal needs increase, ISF shifts | Ongoing, episodic | Puberty / growth spurts |
| Thyroid changes | Global metabolic rate shift | Weeks to months | As condition evolves |

**Behavioral / Situational:**

| Factor | Effect on Physiology | Duration | Frequency |
|--------|---------------------|----------|-----------|
| Fasting / extended fast | ISF increases 20–40%, liver output changes | Hours to days | Variable |
| Weight change (±5 kg) | TDI shifts ~5–10%, ISF/CR shift | Weeks to months | Common over time |
| Travel / jet lag | Circadian basal pattern misaligned to local time | 2–5 days | Several times/year |
| Dehydration | Insulin absorption impaired, BG reads high | Hours | Common in heat/illness |
| Alcohol | Liver glucose production suppressed → delayed hypo risk 6–24h | Hours to next day | Variable |
| High-fat/protein meals | Extended carb absorption 4–8 hours; initial BG stable then rises | 4–8 hours | Frequent |
| Exhaustion / sleep deprivation | ISF changes unpredictably, cortisol elevated | Hours to days | Common |
| Altitude change | Insulin sensitivity shifts | Days | Travel/recreation |

**Insulin Delivery Complications:**

| Factor | Effect on Physiology | Duration | Frequency |
|--------|---------------------|----------|-----------|
| Pump site age (>3 days) | Absorption degrades 10–30% | Gradual over 24–72h | Every site change |
| Lipohypertrophy (scar tissue) | Absorption erratic, ±50% variability | Permanent at site | Builds over years |
| Mixing pump + MDI | IOB tracking breaks (MDI not in pump history) | Per injection | Some patients routinely |
| Site location (abdomen vs arm vs leg) | Absorption rate varies 20–40% | Per site | Every rotation |
| Temperature (hot day, sauna) | Absorption accelerates 20–50% | Hours | Seasonal / activity |
| Injection into muscle vs subQ | Absorption 2–3× faster | 1–2 hours | Accidental |

#### 4.3.3 What Current Simulation Misses

The current `in-silico-bridge.js` patient profiles are:

```javascript
standard:  { ISF: 40, CR: 10, basalRate: 1.0 }  // "correct" settings
sensitive: { ISF: 60, CR: 15, basalRate: 0.7 }  // "correct" for sensitive patient
resistant: { ISF: 20, CR: 6,  basalRate: 1.5 }  // "correct" for resistant patient
```

In all three cases, the **algorithm's profile matches the patient's true physiology**.
This means we never test:

1. Algorithm configured with ISF=40 running on a patient whose true ISF is 25 today
   (illness, luteal phase, new pump site in scar tissue)
2. Algorithm configured with CR=10 while patient eats a high-fat pizza where effective
   CR is 6 for the first 2 hours and 15 for the next 4 hours
3. Algorithm configured with basal=1.0 while patient's dawn phenomenon needs 1.6
   between 4–7 AM
4. Patient who took 4U via pen injection that the pump doesn't know about
5. Algorithm running with week-old settings after the patient gained 3 kg on vacation

**This is why autosens, dynamic ISF, and autotune exist in oref0** — they attempt to
detect and compensate for these mismatches in real time. But our simulation never
exercises these mechanisms because the patient always matches the profile.

#### 4.3.4 Required Simulation Architecture: Two-Layer Patient Model

To capture this reality, simulation needs to separate:

```
┌─────────────────────────────────────┐
│  ALGORITHM PROFILE                  │
│  (what the algorithm believes)      │
│                                     │
│  ISF: 40  CR: 10  basal: 1.0       │
│  DIA: 6   targets: 100-110         │
│                                     │
│  → This is the input to             │
│    determine-basal / Loop           │
└─────────────────┬───────────────────┘
                  │
       ╔══════════╧══════════╗
       ║  MISMATCH LAYER     ║
       ║  (the gap between   ║
       ║   belief and reality)║
       ╚══════════╤══════════╝
                  │
┌─────────────────▼───────────────────┐
│  TRUE PATIENT PHYSIOLOGY            │
│  (what cgmsim-lib simulates)        │
│                                     │
│  ISF: 28 (today — luteal phase)     │
│  CR: 7 (this meal — high fat)       │
│  basal need: 1.4 (dawn phenomenon)  │
│  DIA: 5.5 (warm day, fast absorb)   │
│  + untracked 3U MDI pen injection   │
│  + site is 4 days old (−15% absorb) │
│                                     │
│  → This drives the BG simulation    │
└─────────────────────────────────────┘
```

The **mismatch layer** is parameterized per scenario:

| Mismatch Parameter | Range | Distribution |
|-------------------|-------|-------------|
| ISF ratio (true / profile) | 0.4–2.5 | Log-normal, mean ~1.0, SD ~0.3 |
| CR ratio (true / profile) | 0.5–2.0 | Log-normal, mean ~1.0, SD ~0.25 |
| Basal ratio (true need / set rate) | 0.5–2.0 | Normal, time-of-day dependent |
| DIA offset (true − configured) | −1.5 to +1.5 hours | Normal, mean ~0 |
| Phantom IOB (untracked insulin) | 0–8 U | Poisson-like (most days zero) |
| Absorption degradation | 0.7–1.0 | Uniform, decreasing with site age |

These can be **calibrated from real data** by observing the gap between what the
algorithm predicted and what actually happened:

- Post-meal BG consistently 40 mg/dL higher than predicted → CR mismatch
- Overnight BG drifts up 2 mg/dL/hr → basal mismatch
- Corrections take 50% longer than expected → ISF or DIA mismatch

### 4.4 Scenario Coverage Gaps

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

Missing scenarios — organized by the dimension they exercise:

**Settings Mismatch Scenarios (§4.3):**

```
❌ basal-too-low      (basal set 30% below actual need — persistent rise)
❌ basal-too-high     (basal set 30% above need — persistent drift to hypo)
❌ isf-overestimate   (ISF configured 50% too high — corrections undershoot)
❌ cr-stale           (CR wrong by 30% — systematic post-meal highs)
❌ dia-too-short      (DIA=3h configured, true=5.5h — insulin stacking)
❌ pump-plus-mdi      (patient took pen injection not tracked by pump)
❌ site-degradation   (day 4 of infusion set — 20% absorption loss)
```

**Physiological Confounder Scenarios:**

```
❌ illness            (ISF drops 50%, elevated BG for hours/days)
❌ hormone-cycle      (ISF drops 30% for 5 days, then normalizes)
❌ fasting-extended   (16+ hour fast, ISF rises, liver compensates)
❌ high-fat-meal      (extended carb absorption, 4-6 hr BG tail)
❌ alcohol-evening    (liver suppressed → delayed hypo risk next morning)
❌ dehydration        (absorption impaired, BG reads artificially high)
❌ adrenaline-spike   (stress → hepatic glucose dump, transient 50+ mg/dL rise)
❌ growth-spurt       (pediatric — basal needs jump 30% over weeks)
```

**Behavioral / Device Scenarios:**

```
❌ missed-bolus       (meal with no bolus — extremely common)
❌ double-bolus       (accidental re-dose)
❌ site-change-day    (old site removed, new site warming up — gap in absorption)
❌ sensor-warmup      (2-hour CGM gap after new sensor)
❌ compression-low    (false low during sleep — CGM artifact)
❌ stacking           (multiple corrections → hypo)
❌ rebound-high       (overtreatment of low → spike)
❌ exercise-delayed   (hypo 6-12 hrs after exercise)
❌ travel-timezone    (basal schedule misaligned to local time)
❌ exhaustion         (sleep-deprived, ISF unpredictable)
```

---

## 5. Calibration Pipeline Architecture: How Distribution Distance Drives Generation

### 5.1 The Fundamental Question

How does measuring "my synthetic BG distribution is X distance from real" actually
lead to generating **new**, realistic CGM streams? And when we replay a real scenario
with different treatments, how do we know the counterfactual response is accurate?

The answer has three layers:

1. **The causal model generates trajectories** — cgmsim-lib's pharmacokinetic
   equations (§5.2) are the generator, not the distance metric
2. **The distance metric is a loss function** — it tells us how wrong the causal
   model's parameters are, not what the next BG value should be
3. **Multi-tier matching validates the mechanism** — distribution matching alone
   is insufficient; you need temporal structure, event dynamics, and treatment
   response shapes to confirm the causal model is right for the right reasons

### 5.2 The Causal Model: What Actually Generates Each BG Value

cgmsim-lib is a **physics-based pharmacokinetic simulator**, not a statistical
generator. Each 5-minute BG value is computed causally:

```
BG(t+5) = BG(t)
         - insulinActivity(t) × ISF          ← insulin lowers BG
         + carbAbsorptionRate(t) × ISF/CR     ← carbs raise BG
         + liverOutput(t) × insulinSuppression(t) × circadian(t)
         ± sensorNoise(t)                     ← CGM measurement error

Where:
  insulinActivity(t) = Σ over all boluses/basals:
    units × (norm/τ²) × age × (1 - age/duration) × e^(-age/τ)
    (exponential decay with insulin-type-specific peak and duration)

  carbAbsorptionRate(t) = Σ over all meals:
    dual-phase: fast portion (~60min absorption) + slow portion (~240min)
    rate follows trapezoidal ramp-up then linear decay

  liverOutput(t) = baseRate × weight × insulinSuppression × circadianSine
    (Hill equation suppression: max 65% reduction by insulin)
```

The UVA/Padova engine uses 18 coupled ODEs for higher fidelity, including
two-compartment insulin absorption, variable gastric emptying (nonlinear tanh),
and glucagon counter-regulation.

**Key point**: Given a treatment sequence (insulin doses + carb entries + timestamps),
the simulator produces a DETERMINISTIC BG trajectory (plus optional stochastic noise).
The causal model IS the generator.

### 5.3 What the Distance Metric Actually Does

The distribution distance is **not a generator** — it's the **objective function**
for a parameter optimization loop. Here's the precise mechanism:

```
┌─────────────────────────────────────────────────────────────────┐
│            CALIBRATION AS PARAMETER OPTIMIZATION                │
│                                                                 │
│  GIVEN: Real data fingerprint F_real (from OhioT1DM, etc.)     │
│  FIND:  Simulator params θ that minimize distance(F_sim, F_real)│
│                                                                 │
│  θ = { ISF_mean, ISF_sd,          ← patient physiology knobs   │
│         CR_mean, CR_sd,                                         │
│         basal_mean, basal_sd,                                   │
│         carb_estimation_error_sd,  ← behavioral noise knobs    │
│         meal_timing_jitter_sd,                                  │
│         CGM_noise_amplitude,       ← sensor noise knobs        │
│         liver_circadian_amplitude,                              │
│         insulin_absorption_cv,     ← pharmacokinetic noise     │
│         missed_bolus_probability,  ← event frequency knobs     │
│         exercise_frequency,                                     │
│         ... }                                                   │
│                                                                 │
│  LOOP:                                                          │
│    1. Sample patient profiles from θ distributions              │
│    2. Sample scenarios (meals, exercise, etc.) at θ frequencies │
│    3. Run cgmsim-lib forward simulation for each                │
│    4. Collect ensemble of synthetic BG trajectories             │
│    5. Extract fingerprint F_sim from ensemble                   │
│    6. Compute distance = d(F_sim, F_real)                       │
│    7. Adjust θ to reduce distance                               │
│    8. Repeat until distance < threshold                         │
└─────────────────────────────────────────────────────────────────┘
```

The "knobs" θ are not individual BG values — they are **the parameters of the
distributions from which patient profiles and scenarios are sampled**. Turning
these knobs changes what kind of patients and situations the simulator generates.

### 5.4 Which Knobs Control Which Distribution Features

This is the critical mapping: each tier of the fingerprint is sensitive to
different simulator parameters. When a specific tier's distance is high, you
know which knobs to turn:

```
TIER 1 (BG Distribution: mean, SD, CV, percentiles, TIR)
│
├── BG mean too low?
│   → ISF_mean too low (insulin too effective)
│   → basal_mean too high (too much background insulin)
│   → CR_mean too high (carbs overcompensated)
│
├── BG SD too narrow? (THE KNOWN PROBLEM: 89-140 vs real 40-350)
│   → ISF_sd too low (all patients have same sensitivity)
│   → CGM_noise_amplitude too low (clean signal)
│   → carb_estimation_error_sd too low (perfect carb counting)
│   → missed_bolus_probability too low (no unbolused meals)
│   → meal_timing_jitter_sd too low (perfect timing)
│   → mismatch_layer absent (§4.3 — settings always match)
│
├── TIR too high? (more time in range than real patients)
│   → Same causes as narrow SD — simulator is "too good"
│   → No physiological confounders (illness, hormones, etc.)
│
TIER 2 (Temporal Dynamics: autocorrelation, spectral power, overnight vs day)
│
├── Autocorrelation decays too fast?
│   → insulin_absorption_cv too high (effects too variable)
│   → CGM_noise too high relative to signal (noise dominates)
│
├── No 24h spectral peak?
│   → liver_circadian_amplitude too low
│   → No dawn phenomenon scenarios
│
├── Overnight SD matches but daytime doesn't?
│   → Meal scenarios under-represented
│   → Exercise effects missing
│
TIER 3 (Treatment Patterns: TDI, basal:bolus ratio, meals/day)
│
├── TDI too low?
│   → Patient profiles have lower insulin needs than population
│   → Missing correction bolus scenarios
│
├── Basal:bolus ratio wrong?
│   → Basal rates don't match population pump settings
│   → Bolus scenarios too few/many
│
TIER 4 (Event Dynamics: meal response shape, hypo recovery arc)
│
├── Post-meal peak too sharp/too blunt?
│   → carb_absorption_time wrong (CGMSIM default: 360 min)
│   → fast/slow carb split ratio wrong
│   → CR mismatch not modeled (§4.3)
│
├── Hypo recovery too fast?
│   → Liver model over-compensating
│   → Carb correction absorption too fast
│
├── No extended meal tails (4-6 hr)?
│   → High-fat meal absorption not modeled
│   → Only dual-phase fast/slow, no extended release
```

### 5.5 The Optimization Algorithm

The calibration controller uses these tier→knob mappings to search parameter space:

```
Algorithm: Multi-Tier Hierarchical Calibration

Input:
  F_real = population fingerprint from real datasets
  θ_0 = initial parameters (current in-silico-bridge defaults)

Phase 1 — Coarse calibration (Tier 1 distribution matching):
  Objective: minimize Wasserstein_1(BG_hist_sim, BG_hist_real)

  This is a 1D optimal transport problem:
    W_1 = ∫|CDF_sim(x) - CDF_real(x)| dx

  Intuition: Wasserstein measures the "earth moving" cost — how much
  probability mass must shift and how far to transform the simulated
  BG histogram into the real one.

  Knobs adjusted: ISF_mean, ISF_sd, CR_mean, basal_mean,
                   CGM_noise_amplitude, missed_bolus_probability
  Method: Bayesian optimization (Gaussian process surrogate) or
          Nelder-Mead simplex (derivative-free, ~6D)
  Convergence: W_1 < 5 mg/dL (distributions nearly overlap)

  Why Wasserstein, not KL divergence?
  - KL divergence is undefined when sim has zero probability at a BG
    value that real data contains (KL → ∞). This happens constantly
    because CGMSIM's 89-140 range has zero mass above 200.
  - Wasserstein is always finite and measures geometric distance between
    distributions. "Your sim never goes above 200, real goes to 350"
    gives a large but meaningful W_1 value.

Phase 2 — Temporal calibration (Tier 2 dynamics matching):
  Objective: minimize RMSE(ACF_sim[0:72], ACF_real[0:72])
             + |spectral_24h_sim - spectral_24h_real|

  ACF = autocorrelation function at lags 1-72 (5min each = 6 hours)

  Intuition: Real CGM data has strong autocorrelation (BG changes slowly)
  with a 24-hour circadian component. If the simulator's temporal dynamics
  don't match, individual trajectories will "feel wrong" even if the
  histogram matches.

  Knobs adjusted: liver_circadian_amplitude, insulin_absorption_cv,
                   CGM_noise_correlation_time, dawn_phenomenon_amplitude
  Method: Grid search over 3-4 key parameters (~5 levels = 625 combos)
  Convergence: ACF RMSE < 0.05, spectral ratio within 20%

Phase 3 — Event-shape calibration (Tier 4 dynamics matching):
  Objective: minimize DTW(meal_shape_sim, meal_shape_real)
             + DTW(hypo_shape_sim, hypo_shape_real)

  DTW = Dynamic Time Warping distance — allows time-axis stretching

  This compares the SHAPE of typical events:
  - Average post-meal BG trajectory (0-4 hours after carb entry)
  - Average hypo-recovery arc (from nadir to 100 mg/dL)
  - Average dawn phenomenon rise (3-7 AM)

  Intuition: Even with correct distribution and autocorrelation, if meal
  responses peak at wrong time or wrong height, the simulator will
  mislead algorithm validation.

  Knobs adjusted: carb_absorption_time, fast_slow_carb_ratio,
                   CR_sd, meal_timing_jitter_sd
  Method: Nelder-Mead on 4D parameter space
  Convergence: DTW < 15 mg/dL·min (shapes nearly overlap)

Phase 4 — Mismatch layer calibration (§4.3 validation):
  Objective: minimize |prediction_residual_distribution_sim - _real|

  This is unique: we compare the ERRORS the algorithm makes, not the BG.

  In real data: run oref0 on actual patient data, record how far off
  its predictions were from what actually happened.
  In sim data: same algorithm on simulated data with mismatch layer.

  If the mismatch layer is correctly calibrated, the algorithm should
  be EQUALLY WRONG on synthetic data as on real data.

  Knobs adjusted: ISF_ratio distribution, CR_ratio distribution,
                   basal_ratio distribution, phantom_IOB frequency
  Method: Moment matching (match mean and SD of residual distributions)
  Convergence: residual mean within 5 mg/dL, residual SD within 10%
```

### 5.6 From Calibrated Parameters to New Realistic Streams

Once θ is calibrated, generating new realistic CGM streams is straightforward:

```
GENERATION (unlimited new scenarios):

  1. Sample a virtual patient from calibrated distributions:
     patient = {
       ISF: lognormal(θ.ISF_mean, θ.ISF_sd),
       CR:  lognormal(θ.CR_mean, θ.CR_sd),
       basal: normal(θ.basal_mean, θ.basal_sd),
       ...
     }

  2. Sample a mismatch profile (§4.3):
     mismatch = {
       ISF_ratio:  lognormal(1.0, θ.ISF_mismatch_sd),
       CR_ratio:   lognormal(1.0, θ.CR_mismatch_sd),
       basal_ratio: normal(1.0, θ.basal_mismatch_sd),
       phantom_IOB: poisson(θ.phantom_IOB_rate),
     }

  3. Sample a scenario template:
     scenario = weighted_random_choice({
       "meal-rise": 0.35,
       "fasting": 0.20,
       "missed-bolus": 0.12,     ← frequency from real data
       "dawn-phenomenon": 0.10,
       "exercise": 0.08,
       "illness": 0.03,
       ...
     })

  4. Add noise to scenario:
     meal.carbs += normal(0, θ.carb_estimation_error_sd)
     meal.time  += normal(0, θ.meal_timing_jitter_sd)
     insulin.absorption *= uniform(θ.absorption_degradation_range)

  5. Run cgmsim-lib with:
     - TRUE physiology: patient parameters × mismatch ratios
     - ALGORITHM sees: patient parameters (without mismatch)
     - Treatments: scenario template + noise
     - CGM output: true BG + sensor noise model

  6. Output: one SIM-* vector with realistic BG trajectory,
     plus metadata about scenario, mismatch, and confounders
```

Each generated stream is different because Steps 1-4 all involve stochastic
sampling from calibrated distributions. The ENSEMBLE of generated streams
matches real population statistics (because θ was calibrated to minimize
distribution distance), while each INDIVIDUAL stream follows the causal
pharmacokinetic model (because cgmsim-lib's equations compute each BG value
from insulin + carbs + liver effects).

### 5.7 Counterfactual Treatment Scenarios (Replay with Different Treatments)

Given a real or simulated scenario, what happens if we change the treatment?

```
REPLAY WITH COUNTERFACTUAL:

  Original scenario:
    Patient eats 60g carbs at 12:00
    Boluses 6U at 12:00 (CR=10, so 60/10=6U)
    BG trajectory: 120 → 165 → 185 → 170 → 145 → 125 (2.5 hours)

  Counterfactual question: What if they bolused 15 minutes early?

  Method:
    1. Keep IDENTICAL patient parameters (ISF, CR, absorption, liver)
    2. Keep identical meal (60g at 12:00)
    3. Change ONLY the bolus: 6U at 11:45 (instead of 12:00)
    4. Re-run cgmsim-lib forward simulation
    5. New trajectory: 120 → 148 → 160 → 150 → 135 → 118

  The causal model handles this because:
  - Insulin activity curve shifts 15 minutes earlier
  - Carb absorption curve stays the same
  - The OVERLAP changes: more insulin active during carb rise
  - Result: lower peak, faster return to baseline
```

**How do we know the counterfactual is ACCURATE?**

The calibration pipeline's multi-tier validation handles this:

```
COUNTERFACTUAL VALIDATION STRATEGY:

  1. Find matched pairs in REAL data:
     - Patient A bolused at meal time → recorded BG trajectory
     - Patient A bolused 15 min early another day → recorded trajectory
     (Same patient, similar meal, different bolus timing)

  2. Run simulator on both scenarios with Patient A's calibrated params

  3. Compare:
     a) Does the simulator match the ACTUAL trajectory in both cases?
     b) Does the DIRECTION of difference match?
        (Earlier bolus → lower peak in both real and simulated?)
     c) Does the MAGNITUDE of difference match?
        (Real: peak dropped 25 mg/dL; Sim: peak dropped 22 mg/dL?)

  4. The Tier 4 fingerprint (event dynamics) captures this:
     - DTW on meal response shapes: "pre-bolused" vs "at-meal-bolused"
     - If shapes match across both conditions, counterfactuals reliable

  5. Population-level validation:
     - Across 1000+ subjects in IOBP2/T1DEXI, compute the statistical
       effect of pre-bolusing on peak BG
     - Compare against simulated effect across 1000 virtual patients
     - If effect size and variance match → counterfactual mechanism
       is validated at population level
```

### 5.8 The Three Levels of Confidence

Not all generated streams are equally trustworthy:

| Confidence Level | What's Generated | Validation | Trust |
|-----------------|-----------------|------------|-------|
| **High** — Interpolation | Patient within calibrated range, common scenario (meal, fasting, dawn) | Fingerprint distance < threshold all 4 tiers; counterfactual validated against matched pairs | Full weight in algorithm scoring |
| **Medium** — Extrapolation | Mismatch layer active (settings wrong 30%+), compound confounders, uncommon scenario | Tier 1-2 validated; Tier 4 extrapolated from single-confounder calibration | Reduced weight in scoring |
| **Low** — Adversarial | Extreme parameters, impossible scenarios (BG 400→40 in 15 min) | Not fingerprint-validated; only safety invariants checked | Safety boundary testing only (hard gate) |

### 5.9 What Exists vs What's Needed

| Component | Status | Code Location |
|-----------|--------|---------------|
| Causal model (CGMSIM) | ✅ Working | `externals/cgmsim-lib/src/CGMSIMsimulator.ts` |
| Causal model (UVA/Padova) | ✅ Working | `externals/cgmsim-lib/src/lt1/core/models/UvaPadova_T1DMS.ts` |
| Trajectory metrics (MAE, RMSE) | ✅ Working | `tools/aid-autoresearch/score-in-silico.js` |
| Per-subject ISF×CR grid search | ✅ Working | `tools/aid-autoresearch/glupredkit_oref0_model.py:102-137` |
| Algorithm param mutation engine | ✅ Working | `tools/aid-autoresearch/param-mutation-engine.js` |
| ReplayBG parameter identification | ✅ Working | `externals/GluPredKit/glupredkit/models/uva_padova.py` |
| Sensor noise models | ✅ In cgmsim-lib | `externals/cgmsim-lib/src/lt1/core/sensors/` |
| **Fingerprint extractor** | ❌ Not built | Described: §5.10 |
| **Distribution distance metrics** | ❌ Not built | Described: §5.5 (Wasserstein, DTW, ACF RMSE) |
| **Calibration controller** | ❌ Not built | Described: §5.5 (4-phase hierarchical) |
| **Mismatch layer in simulator** | ❌ Not built | Described: §4.3.4 |
| **Scenario frequency sampler** | ❌ Not built | Described: §5.6 Step 3 |
| **Counterfactual validation** | ❌ Not built | Described: §5.7 (matched-pair comparison) |

### 5.10 Fingerprint Extraction

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

### 5.11 Integration with Autoresearch Loop

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

### Phase 3b: Two-Layer Mismatch Model

Implement the therapy-settings-vs-true-physiology separation (§4.3.4).

**Inputs**: Calibrated patient profiles from Phase 3, autosens/autotune logs from
OpenAPS Data Commons (142 subjects), retrospective BG prediction residuals.

**Outputs**:
- Parameterized mismatch layer (ISF ratio, CR ratio, basal ratio distributions)
- Mismatch scenario library (27+ scenarios from §4.4) with realistic parameter ranges
- Physiological confounder models (hormonal cycle ISF shift curve, illness ISF decay,
  site degradation absorption curve, etc.)
- "Compound confounder" generator: randomly composites 1–3 concurrent confounders
  weighted by real-world co-occurrence frequency
- Validation: compare simulated prediction-error distributions against real prediction
  errors from OpenAPS Data Commons (the real data already contains these mismatches)

**Key insight**: We can calibrate the mismatch layer indirectly. In real data, the
gap between what the algorithm predicted and what happened IS the mismatch signal.
By measuring the distribution of prediction residuals in real OpenAPS/Nightscout data,
we can parameterize how much mismatch to inject into simulation.

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

Even with the two-layer mismatch model (§4.3), simulation cannot fully capture:

- **Behavioral patterns** — real people forget boluses in predictable ways, overtrust
  or ignore alerts, have alarm fatigue, and make emotional override decisions
- **Device-specific artifacts** — Dexcom G7 vs Libre 3 noise profiles differ;
  pump occlusion alarms, Bluetooth dropouts, and app crashes create real-world gaps
- **Multi-day dynamics** — illness progression follows patient-specific arcs,
  hormonal cycles shift ISF over 5–7 days, travel jet-lag misaligns circadian basal
- **Compound confounders** — real patients rarely have just ONE confounder active.
  A real day might be: luteal phase + bad pump site + pizza dinner + forgot to bolus
  for snack + late night alcohol. The combination space is effectively infinite
- **Psychosocial factors** — diabetes distress, "rage bolusing" after extended highs,
  carb restriction then binge, deliberate insulin omission — these show up in real
  data as patterns an algorithm must handle safely

Real TV-* vectors from phone captures must always carry the highest scoring weight.
Simulation expands coverage; it doesn't replace ground truth. The goal of the
mismatch layer is to bridge the gap so simulation results are *directionally correct*
— not to eliminate the need for real data.

### The UVA/Padova Integration Gap (Critical Known Issue)

**`in-silico-bridge.js` uses the CGMSIM engine, NOT UVA/Padova.** This is a primary
source of the narrow BG range problem (89–140 mg/dL synthetic vs 40–350+ real).

| Factor | CGMSIM (what we use) | UVA/Padova (what we should use) |
|--------|---------------------|--------------------------------|
| BG calculation | Algebraic: `lastBG + Σeffects` | 18 coupled ODEs integrated per minute |
| Insulin model | Single exponential decay per type | Two-compartment SC absorption (Isc1→Isc2→plasma) |
| Meal model | Dual-phase (fast/slow) fixed split | Variable gastric emptying (nonlinear tanh function of stomach load) |
| Liver model | Hill equation, max 65% suppression | Full EGP with glucagon counter-regulation |
| CGM noise | None (clean signal) | Vettoretti2019/Breton2008 sensor models built in |
| State | Stateless (recomputes from history) | Stateful (carries 18 ODE state variables forward) |
| Realistic range | 89–140 mg/dL typical | 40–400+ mg/dL with noise |

**Why we're not using it yet** (from §4.2):
1. UVA/Padova requires persistent state between ticks (`lastState` carry-forward)
2. Needs ODE solver initialization with steady-state finder
3. Treatment format conversion to UVA input schema
4. `in-silico-bridge.js` was built for CGMSIM's simpler API

**Impact**: Until UVA/Padova integration happens, calibration efforts (§5) are
fighting against a fundamentally limited generator. The CGMSIM engine cannot produce
realistic variability because its algebraic model lacks the nonlinear dynamics
(variable gastric emptying, glucagon counter-regulation, sensor noise) that create
real-world BG spread. This should be the **first infrastructure priority** before
attempting fingerprint calibration.

### CGM Trace Generation: Methodology Comparison

> **Detailed research exploration**: See `docs/60-research/cgm-trace-generation-methodologies.md`
> for in-depth analysis of 5 generation methodologies, UVA/Padova validation history,
> corruption-based augmentation (advisor's "corrupt historical data" approach),
> and a phased exploration roadmap.

The ecosystem currently has **two methodology families** for generating CGM traces.
A third family — trained generative models — is absent but worth evaluating.

#### Methodology 1: Physics-Based Simulation (What We Have)

```
Treatment inputs (insulin, carbs, timestamps)
        │
        ▼
  Pharmacokinetic equations
  (ODE or algebraic)
        │
        ▼
  Deterministic BG trajectory + optional sensor noise
```

**Available in ecosystem**:
- cgmsim-lib CGMSIM engine (algebraic, fast, simplified)
- cgmsim-lib UVA/Padova engine (18-ODE, realistic, not yet integrated)
- GluPredKit `uva_padova.py` model (ReplayBG-based, particle filter)
- GluPredKit `loop.py` / `loop_v2.py` (rule-based + parameter fitting)

**Strengths**:
- Causally correct: change bolus timing → physically plausible BG change
- Interpretable: every BG movement has an assignable cause
- Counterfactual-capable: can answer "what if" by changing one input
- Parameters map to physiology (ISF, CR, DIA have clinical meaning)

**Weaknesses**:
- Only as realistic as the equations — missing physiology = missing dynamics
- Hard to model behavioral/psychosocial effects (forgotten boluses, alarm fatigue)
- Parameter identification requires solving inverse problems
- Single-trajectory: doesn't naturally express uncertainty

#### Methodology 2: Supervised ML Prediction (What We Have)

```
Historical CGM + insulin + carbs (last N windows)
        │
        ▼
  Trained model (LSTM, TCN, Random Forest, etc.)
        │
        ▼
  Predicted BG at t+5, t+10, ... t+60 minutes
```

**Available in ecosystem** (GluPredKit `glupredkit/models/`):
- Neural: LSTM, Double LSTM, TCN, MTL (Conv1D+LSTM), STL, Stacked PLSR
- Ensemble: Random Forest (300 trees)
- Linear: Ridge, Weighted Ridge, SVR
- Baselines: Zero-order hold, Naive linear regressor

**Strengths**:
- Learns patterns that physics models miss (behavioral, device-specific)
- No equations needed — patterns emerge from data
- Multi-point output (predicts full trajectory, not just next value)
- Can implicitly capture confounders present in training data

**Weaknesses**:
- Cannot generate NOVEL scenarios not in training data
- Not causally valid for counterfactuals (changing input treatment doesn't
  produce physically meaningful output — the model learned correlations, not causes)
- Requires large training datasets per prediction horizon
- Extrapolation outside training distribution is unreliable
- Output is a single trajectory, not a distribution

#### Methodology 3: Generative Models (What We Don't Have)

```
Latent noise vector z + conditioning variables (patient type, scenario, treatments)
        │
        ▼
  Generative model (GAN, VAE, Diffusion, Neural ODE)
        │
        ▼
  Synthetic CGM stream (multi-hour, stochastic, distribution-aware)
```

**Not present in ecosystem.** But several architectures are relevant:

| Approach | How It Works | Strengths | Weaknesses | Relevant For Us? |
|----------|-------------|-----------|------------|-----------------|
| **TimeGAN** | GAN trained on time-series: generator learns temporal dynamics, discriminator validates realism | Generates diverse realistic traces; captures temporal correlations automatically | Mode collapse risk; no causal validity; needs large training set (>10K traces) | ✅ High — could generate unlimited training data |
| **Conditional VAE** | Encoder compresses real traces → latent space; decoder generates from latent + condition | Smooth latent space; can interpolate between patient types; uncertainty quantification via sampling | Blurrier outputs than GAN; reconstruction loss can miss sharp events | ✅ High — natural patient-type conditioning |
| **Diffusion Models** | Iterative denoising from Gaussian noise → realistic trace | Highest quality generation; stable training; no mode collapse | Slow generation; computationally expensive; newer, less tooling | ⚠️ Medium — quality is best but compute cost high |
| **Neural ODE** | Learned continuous-time dynamics: dBG/dt = f_θ(BG, insulin, carbs, t) | Combines physics structure with learned dynamics; handles irregular time steps; causally interpretable | Complex training; limited tooling; needs physics-informed loss | ✅ Very high — best of physics + ML |
| **Copula Models** | Statistical: model marginals + dependency structure separately | Fast; well-understood theory; easy to calibrate from population fingerprints | No temporal dynamics; only generates distributions, not trajectories | ⚠️ Low — useful only for Tier 1 validation |

#### Methodology 4: Hybrid Physics-ML (What We Should Consider)

The most promising approach for this ecosystem combines physics and ML:

```
Treatment inputs + patient parameters
        │
        ├──→ Physics model (UVA/Padova) produces "expected" trajectory
        │
        ├──→ ML residual model (LSTM or Neural ODE) learns the GAP
        │    between physics prediction and real observed BG
        │    (this gap captures: behavioral noise, confounders,
        │     device artifacts, model misspecification)
        │
        ▼
  Final BG = physics_prediction + learned_residual + sensor_noise
```

**Why this is compelling for our use case:**

1. **Physics provides causal backbone** — changing bolus timing produces
   physically correct directional change in the base trajectory
2. **ML residual captures what physics misses** — trained on the GAP between
   UVA/Padova predictions and real data, the residual model learns behavioral
   patterns, device artifacts, and confounder effects
3. **Residual is small and learnable** — instead of learning the full BG dynamics
   (hard), the ML model only learns the correction term (easier, less data needed)
4. **Counterfactuals remain meaningful** — the physics base changes correctly when
   treatments change; the residual provides realistic noise around it
5. **Calibration pipeline (§5) applies naturally** — the fingerprint distance metric
   optimizes the physics parameters; the ML residual absorbs remaining distribution
   mismatch automatically

**Data requirement**: This hybrid approach needs per-subject paired data:
(real_BG_trajectory, UVA_predicted_trajectory, treatments, scenario_label) to train
the residual model. The GluPredKit per-subject pipeline (§9 of therapy optimization
doc) already produces this pairing.

### Recommended Generation Strategy

Given current ecosystem capabilities and the calibration architecture:

```
PRIORITY ORDER:

1. IMMEDIATE: Integrate UVA/Padova into in-silico-bridge.js
   - Biggest single improvement to realism
   - Enables sensor noise, nonlinear meal absorption, glucagon
   - Unblocks meaningful calibration (§5)
   - Physics-only, no ML training needed

1b. IMMEDIATE: Extract sensor noise models as standalone corruption tools
   - Facchinetti2014, Vettoretti2019, Breton2008 already exist in code
   - Apply retrospectively to real CGM traces for data augmentation
   - Implements advisor's "corrupt historical data" recommendation
   - See docs/60-research/cgm-trace-generation-methodologies.md §7

2. SHORT-TERM: Calibrate UVA/Padova via fingerprint distance (§5.5)
   - Use Wasserstein/DTW/ACF matching against real dataset fingerprints
   - Produce validated SIM-* vectors that match real distributions
   - Still physics-only but with empirically-tuned parameters

3. MEDIUM-TERM: Add mismatch layer (§4.3) to calibrated UVA/Padova
   - Separate algorithm-profile from true-physiology
   - Enable compound confounder scenarios
   - Dramatic expansion of scenario diversity

3b. MEDIUM-TERM: Treatment perturbation + physics counterfactuals
   - Corrupt real treatment streams (dose ±%, timing jitter)
   - Use calibrated physics model to compute counterfactual BG
   - Grounded augmentation: real data structure + controlled variation

4. LONGER-TERM: Evaluate hybrid physics-ML residual approach
   - Train residual model on gap between UVA/Padova and real data
   - Absorbs behavioral noise, device artifacts, unmodeled confounders
   - Requires per-subject paired trajectories (GluPredKit provides)

5. RESEARCH: Evaluate pure generative models (TimeGAN, Diffusion, Neural ODE)
   - For unlimited scenario generation beyond calibrated physics
   - Would need >10K real CGM traces for training
   - Most relevant for edge case synthesis and data augmentation
   - Diffusion models are formal version of "corrupt and reconstruct"
```

Each level builds on the previous. Level 1 (UVA/Padova integration) is the
critical unblock — all subsequent calibration work is undermined by using the
simplified CGMSIM engine.

---

## 9. Feature Pipeline: From Fingerprinting to Therapy Optimization

> **Extracted to standalone document**: See
> [`therapy-optimization-feature-pipeline.md`](therapy-optimization-feature-pipeline.md)
> for the full architecture of how the fingerprinting pipeline produces therapy
> assessment reports as a fourth deliverable — enabling therapy optimization for
> any person with CGM + insulin + carb data, without requiring algorithm adoption.
>
> Key sections: reverse mismatch detection mathematics, 4-stage ingestion pipeline,
> example therapy assessment JSON output, population context, and the virtuous cycle
> back to simulation calibration.

## 10. Source File Reference

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
| `externals/oref0/lib/autotune/index.js` | ~551 | Autotune: ISF/CR/basal/DIA optimization |
| `externals/oref0/lib/autotune-prep/categorize.js` | — | Period categorization (basal/meal/correction/UAM) |
| `externals/oref0/lib/determine-basal/autosens.js` | ~100 | Real-time 24h sensitivity detection |
| `externals/AndroidAPS/plugins/aps/src/main/kotlin/.../autotune/AutotuneCore.kt` | ~670 | AAPS autotune (Kotlin port + extensions) |
| `externals/AndroidAPS/plugins/aps/src/main/kotlin/.../autotune/AutotunePrep.kt` | ~900 | AAPS data categorization |
| `externals/Trio/trio-oref/lib/autotune/` | — | Trio autotune (oref1 fork) |
| `tools/aid-autoresearch/in-silico-bridge.js` | ~550 | Scenario generation via cgmsim-lib |
| `tools/aid-autoresearch/score-in-silico.js` | ~250 | Algorithm scoring against SIM-* vectors |
| `tools/aid-autoresearch/algorithm_score.py` | ~330 | Composite 6-metric scoring |
| `tools/aid-autoresearch/glupredkit_oref0_model.py` | ~390 | oref0→GluPredKit wrapper (per-subject) |
| `tools/aid-autoresearch/glupredkit_loop_model.py` | — | Loop→GluPredKit wrapper (per-subject) |
| `tools/aid-autoresearch/program.md` | ~70 | Autoresearch loop specification |
| `conformance/in-silico/vectors/` | 35 files | Generated SIM-* conformance vectors |

---

## 11. Related Requirements and Gaps

| ID | Description |
|----|-------------|
| REQ-060 | Algorithm validation infrastructure |
| REQ-070 | *Proposed*: Therapy assessment pipeline — any Nightscout/Tidepool data stream → actionable report (§9) |
| ALG-VERIFY-007 | In-silico bridge generates synthetic scenarios |
| ALG-VERIFY-008 | In-silico scoring against synthetic ground truth |
| ALG-SCORE-001 | Composite algorithm scoring pipeline |
| GAP-ALG-010 | *Proposed*: cgmsim-lib CGMSIM engine produces unrealistically narrow BG range |
| GAP-ALG-011 | *Proposed*: No CGM sensor noise in CGMSIM-engine-generated vectors |
| GAP-ALG-012 | *Proposed*: No meal timing/estimation error in synthetic scenarios |
| GAP-ALG-013 | *Proposed*: No statistical calibration pipeline (real → synthetic fingerprint matching) |
| GAP-ALG-014 | *Proposed*: Clinical metrics (Clarke/Parkes) not integrated into algorithm_score.py |
| GAP-ALG-015 | *Proposed*: Missing 12+ common real-world scenarios (missed bolus, site change, etc.) |
| GAP-ALG-016 | *Proposed*: No therapy settings mismatch modeling — simulator assumes perfect profile match (§4.3) |
| GAP-ALG-017 | *Proposed*: No physiological confounder models (hormones, illness, site degradation) (§4.3.2) |
| GAP-ALG-018 | *Proposed*: No compound confounder composition — real patients have 2–3 concurrent confounders |
| GAP-ALG-019 | *Proposed*: Mixed pump+MDI not representable — phantom IOB invisible to algorithm |
| GAP-ALG-020 | *Proposed*: Autosens/dynamic-ISF never exercised in simulation because settings always match |
| GAP-ALG-021 | *Proposed*: No automated fingerprint extractor module (Tiers 1–4 from raw data) (§9.2) |
| GAP-ALG-022 | *Proposed*: No individual therapy assessment report generator (§9.4) |
| GAP-ALG-023 | *Proposed*: Autotune deviation categories lack population-context sanity checking (§9.6) |
| GAP-ALG-024 | *Proposed*: No replay validation wrapper — cannot feed real patient history into cgmsim-lib and compare |
| GAP-ALG-025 | *Proposed*: in-silico-bridge.js uses CGMSIM engine, not UVA/Padova — primary source of narrow BG range (§8) |
| GAP-ALG-026 | *Proposed*: No generative models (GAN, VAE, diffusion) for synthetic CGM trace generation (§8) |
| GAP-ALG-027 | *Proposed*: No hybrid physics-ML residual model to capture what equations miss (§8) |
| GAP-ALG-028 | *Proposed*: GluPredKit ML models (LSTM, TCN, etc.) cannot produce causally valid counterfactuals (§8) |
