# Functional Data Analysis (FDA) Experiment Proposals for CGM/AID Intelligence

**Date**: 2026-04-05  
**Basis**: Klonoff et al. "CGM Data Analysis 2.0: Functional Data Pattern Recognition
and Artificial Intelligence Applications" (2025); 327 experiments in research logs
(EXP-001–327, 33 independently verified — see `accuracy-validation-2026-04-05.md`)  
**Purpose**: Validate whether FDA representations improve feature selection, encoding
quality, and objective performance across the five CGM/AID intelligence objectives.
Define actionable experiments with clear baselines, success criteria, and auto-research
integration paths.

---

## 1. Motivation: Why FDA for CGM Data?

Klonoff et al. (2025) position Functional Data Analysis as the bridge between
traditional summary statistics ("CGM Data Analysis 1.0") and ML/AI approaches,
identifying five clinical indications:

1. **Longitudinal/repeated-measures** analysis across days/weeks
2. **Phenotyping and subgroup identification** from glucose curve shapes
3. **Meal/intervention impact** assessment via full postprandial trajectories
4. **Inter-/intra-day reproducibility** of glucose patterns
5. **Glycemic variability** as a continuous functional process

Our experiment program (EXP-001–327) is heavily neural-network-centric. FDA offers
complementary representations that could address known weaknesses:

| Known Weakness | FDA Solution |
|----------------|-------------|
| Pattern retrieval Sil=+0.326 (weak) | Functional distance metrics in L² space |
| ISF drift needs 14-day aggregation | FPCA decomposition of ISF curves |
| Feature engineering hurts CNN (EXP-316, 320) | FDA features are *derived from the curve itself*, not hand-engineered |
| Cross-scale concatenation fails (EXP-304) | Functional representations are scale-agnostic |
| R@K saturated, can't discriminate | Glucodensity profiles provide richer comparison basis |

### Key FDA Concepts for CGM

| Concept | Definition | CGM Application |
|---------|-----------|-----------------|
| **B-spline smoothing** | Represent CGM trace as weighted sum of basis functions | Noise-robust continuous representation; handles missing data natively |
| **FPCA** | Functional PCA — extract principal modes of variation | Dimensionality reduction preserving temporal structure |
| **Glucodensity** | Probability density of glucose values over time (Matabuena et al.) | Richer profile than TIR; captures distribution shape |
| **Functional derivatives** | d/dt of the smooth glucose curve | Rate-of-change features without hand-engineering |
| **Curve registration** | Time-warping to align landmark events (meals, boluses) | Meal-response comparison across days |
| **Functional clustering** | k-means in function space (L² distance) | Phenotyping without embedding networks |
| **Functional regression** | Predict scalar/functional outcome from functional input | ISF ~ glucose_curve, forecast as curve-to-curve |

### References from Klonoff et al.

- Gecili et al. (2021) — FDA prediction tools for CGM
- Matabuena et al. (2021, 2023, 2024) — Glucodensity representations
- Cui et al. (2023) — Glucodensity for pattern investigation
- Hall et al. (2018) — Glucotypes via spectral clustering of 2.5h windows

---

## 2. Feature–Problem–Encoding Matrix

The central question: **which FDA features are right for which problems at which
timescales?** This matrix defines the experimental space.

### 2.1 FDA Feature Catalog

| ID | Feature | Computation | Output Shape | Timescale |
|----|---------|------------|-------------|-----------|
| F-FDA-1 | **B-spline coefficients** | Fit B-spline (k=4, n_knots=12) to glucose | (n_coeffs,) per window | Any |
| F-FDA-2 | **FPCA scores** | Project smoothed curve onto top-K FPCs | (K,) per window | Any |
| F-FDA-3 | **Glucodensity** | KDE of glucose values within window | (n_bins,) histogram | ≥24h |
| F-FDA-4 | **Functional derivatives (1st, 2nd)** | d/dt, d²/dt² of B-spline fit | Same shape as input | Any |
| F-FDA-5 | **Phase-amplitude decomposition** | Separate time-warping from amplitude variation | (phase, amplitude) pair | ≥12h |
| F-FDA-6 | **Functional depth** (band depth) | Centrality measure — how "typical" a curve is | Scalar per window | ≥24h |
| F-FDA-7 | **L² distance to population mean** | ‖x(t) - μ(t)‖₂ | Scalar per window | Any |
| F-FDA-8 | **Cross-covariance functions** | Cov(glucose(t), insulin(s)) for all t,s | (T, T) matrix or top-K eigenvalues | ≥6h |

### 2.2 Feature × Problem Mapping

|  | Obj 1: Forecast | Obj 2: Event | Obj 3: ISF Drift | Obj 4: Retrieval | Obj 5: Override |
|--|----------------|-------------|------------------|-----------------|----------------|
| **F-FDA-1** B-spline coeff | ★★ input repr | ★ smoothed input | ☆ ISF curve fit | ★★ functional embedding | ★ smoothed input |
| **F-FDA-2** FPCA scores | ★★ dim reduction | ★ mode features | ★★★ drift in PC space | ★★★ natural embedding | ★★ mode features |
| **F-FDA-3** Glucodensity | ☆ not applicable | ☆ wrong timescale | ★★ density shift | ★★★ distribution comparison | ★★ density features |
| **F-FDA-4** Derivatives | ★★ physics check | ★★★ rate-of-change | ★ ISF velocity | ★ enrichment | ★★★ slope threshold |
| **F-FDA-5** Phase-amplitude | ☆ too slow | ☆ wrong timescale | ★★ circadian shift | ★★ time-warped alignment | ★ circadian context |
| **F-FDA-6** Functional depth | ☆ not useful | ★★ outlier detection | ★ anomaly score | ★★★ typicality measure | ★★ novelty detection |
| **F-FDA-7** L² to mean | ☆ not useful | ★★ deviation score | ★★ drift magnitude | ★★ distance metric | ★★ deviation score |
| **F-FDA-8** Cross-covariance | ★★★ glucose-insulin dynamics | ★ complex | ★★★ ISF relationship | ★★ multivariate | ★★ insulin-glucose coupling |

**Legend**: ★★★ = primary candidate, ★★ = secondary, ★ = possible enrichment, ☆ = not applicable

### 2.3 Timescale × Encoding Strategy

| Timescale | Current Encoding | Proposed FDA Encoding | Basis Config |
|-----------|-----------------|----------------------|-------------|
| **Fast (2h, 5-min)** | 8ch × 24 steps raw | B-spline(k=4, n_knots=6) → coefficients + derivatives | 6 interior knots → ~10 B-spline coeffs per channel |
| **Episode (12h, 5-min)** | 8ch × 144 steps raw | B-spline(k=4, n_knots=16) + FPCA(K=5) | Phase-amplitude decomposition viable |
| **Daily (24h, 15-min)** | 8ch × 96 steps raw | Glucodensity(n_bins=50) + FPCA(K=8) + functional depth | Full distributional representation |
| **Weekly (7d, 1-hr)** | 8ch × 168 steps raw | FPCA(K=10) + glucodensity + cross-covariance(K=5) | Multi-day functional profile |
| **Rolling (14d)** | ISF_effective rolling mean | FPCA scores over biweekly windows → Spearman on PC trajectories | Change-point detection in functional space |

---

## 3. Proposed Experiments (EXP-328 – EXP-341)

### Experiment Design Principles

1. **Each experiment has exactly one FDA hypothesis** — no confounding
2. **Baseline is always the best existing result** for that objective
3. **Success criteria are quantitative** and pre-registered
4. **Auto-research integration**: each experiment is a registered function in
   `run_pattern_experiments.py` with JSON output matching the standard schema
5. **Incremental**: early experiments validate tooling; later ones build on results

### Infrastructure Prerequisite: EXP-328

#### EXP-328: FDA Toolchain Bootstrap

**Hypothesis**: scikit-fda can produce B-spline representations and FPCA
decompositions from our existing 5-min CGM grids without data loss.

**Method**:
1. Install `scikit-fda` (add to requirements.txt)
2. Implement `fda_encode(grid_data, method, **params)` → functional representation
3. Validate round-trip: raw grid → B-spline → evaluate on grid → MAE < 0.5 mg/dL
4. Benchmark: FPCA on 11 patients' daily glucose curves → extract top-K components
5. Confirm integration with existing `load_multiscale_data()` pipeline

**Success Criteria**:
- B-spline round-trip error < 0.5 mg/dL at 5-min resolution
- FPCA captures >90% variance with K ≤ 8 components (daily scale)
- Encoding time < 1 second per patient-day
- Output shape compatible with existing CNN/Transformer input

**Deliverable**: `tools/cgmencode/fda_features.py` module exporting:
```python
def bspline_smooth(grid: np.ndarray, n_knots: int = 12, order: int = 4) -> FDataBasis
def fpca_scores(fd: FDataBasis, n_components: int = 5) -> np.ndarray
def glucodensity(grid: np.ndarray, n_bins: int = 50) -> np.ndarray
def functional_derivatives(fd: FDataBasis, order: int = 1) -> FDataBasis
def functional_depth(fd: FDataBasis, method: str = 'band') -> np.ndarray
def l2_distance_to_mean(fd: FDataBasis) -> np.ndarray
```

**Auto-research registration**:
```python
REGISTRY['fda-bootstrap'] = 'run_fda_bootstrap'
```

---

### Phase A: Feature Validation (Which FDA features carry signal?)

#### EXP-329: FPCA Variance Structure Across Scales

**Hypothesis**: FPCA eigenvalue decay rates differ by timescale, revealing
which scales have the richest functional structure for downstream tasks.

**Baseline**: No existing FPCA analysis.

**Method**:
1. Compute FPCA on glucose channel at each scale (fast/episode/daily/weekly)
2. Record variance explained by top 1, 3, 5, 8, 10, 15, 20 components
3. Visualize principal component functions — what modes do they capture?
4. Compare eigenvalue decay across 11 patients (per-patient vs pooled)

**Success Criteria**:
- Identify which scale achieves 95% variance with fewest components
- PC1-3 interpretable (e.g., PC1 = mean level, PC2 = dawn/dusk, PC3 = variability)
- Per-patient vs pooled variance gap < 15%

**Output**: `exp329_fpca_variance.json`
```json
{
  "experiment": "EXP-329",
  "name": "fpca-variance-structure",
  "scales": {
    "fast": {"var_explained": [0.65, 0.82, ...], "n_for_95": 8},
    "episode": {"var_explained": [...], "n_for_95": 5},
    "daily": {"var_explained": [...], "n_for_95": 6},
    "weekly": {"var_explained": [...], "n_for_95": 4}
  },
  "per_patient": { "a": {...}, ... }
}
```

#### EXP-330: Glucodensity vs TIR — Information Content

**Hypothesis**: Glucodensity profiles contain strictly more information than
time-in-range (TIR) bins and can discriminate patient-states that TIR cannot.

**Baseline**: 5-bin TIR (<54, 54-70, 70-180, 180-250, >250 mg/dL) per day.

**Method**:
1. For each patient-day, compute: (a) 5-bin TIR, (b) glucodensity (50-bin KDE)
2. Compute pairwise distances between all patient-days using both representations
3. Cluster (k-means, k=9 to match episode labels) and measure ARI against labels
4. Measure mutual information: glucodensity → labels vs TIR → labels

**Success Criteria**:
- Glucodensity ARI > TIR ARI by ≥ 0.05
- Glucodensity MI > TIR MI
- At least one pair of days with same TIR but different glucodensity AND different labels

**Output**: `exp330_glucodensity_vs_tir.json`

#### EXP-331: Functional Derivatives vs Hand-Engineered Rate Features

**Hypothesis**: Derivatives from B-spline-smoothed glucose provide cleaner
rate-of-change signal than finite-difference ROC features, which hurt CNN
performance in EXP-316/320.

**Baseline**: EXP-316 showed ISF-as-feature hurts override by -3.5%.

**Method**:
1. Compute: (a) finite-difference ROC (current), (b) B-spline 1st derivative,
   (c) B-spline 2nd derivative
2. Correlation analysis: each derivative type vs actual glucose change in next 15/30/60 min
3. SNR comparison: signal (mean |derivative| during events) / noise (std during stable)
4. Feed each as additional channel to existing 8ch CNN baseline → measure Δ F1

**Success Criteria**:
- B-spline derivatives have SNR ≥ 1.5× finite-difference
- Adding B-spline derivative channel does NOT degrade CNN F1 (Δ > -1%)
- If improves: Δ F1 > +1% on override or event detection

**Output**: `exp331_functional_derivatives.json`

---

### Phase B: FDA for Specific Objectives

#### EXP-332: FPCA Scores as Pattern Retrieval Embeddings

**Hypothesis**: FPCA scores at weekly scale provide better embeddings than
GRU-learned embeddings (EXP-304 Sil=+0.326) because they capture interpretable
variance modes without training.

**Baseline**: EXP-304 weekly GRU Sil=+0.326, LOO Sil=-0.360.

**Method**:
1. Compute FPCA(K=10) on weekly (7d, 1-hr) glucose windows
2. Use FPCA scores as embeddings directly → compute Silhouette, ARI
3. Try FPCA on multivariate (glucose + IOB + COB) via MFPCA
4. Compare: (a) FPCA-only, (b) GRU-only, (c) FPCA+GRU concatenation
5. LOO evaluation: fit FPCA on N-1 patients, score held-out patient

**Success Criteria**:
- FPCA-only Sil > +0.20 (viable without training)
- FPCA LOO Sil > -0.10 (better cross-patient than GRU LOO=-0.360)
- If FPCA+GRU concat > GRU alone: confirms complementary signal

**Output**: `exp332_fpca_retrieval.json`

#### EXP-333: Glucodensity Features for Override Prediction

**Hypothesis**: Adding a glucodensity summary of the 2h context window improves
override prediction by providing distributional context that raw channels miss.

**Baseline**: EXP-327 attention override F1=0.852 (15min lead).

**Method**:
1. For each 2h window, compute 20-bin glucodensity (compressed KDE)
2. Concatenate as additional channels to 8ch input → 28ch total
3. Train attention model (same EXP-327 config) on augmented input
4. Compare: (a) 8ch baseline, (b) 8ch + glucodensity, (c) glucodensity-only

**Success Criteria**:
- 8ch + glucodensity F1 ≥ 0.852 (no degradation)
- If improves: Δ F1 > +1%
- glucodensity-only establishes lower bound of distributional signal

**Output**: `exp333_glucodensity_override.json`

#### EXP-334: FPCA-Based ISF Drift Detection

**Hypothesis**: Tracking FPCA score trajectories over biweekly windows detects
ISF drift earlier than rolling-mean Spearman (EXP-312, 14-day latency).

**Baseline**: EXP-312 biweekly rolling, 9/11 significant, ~14 day latency.

**Method**:
1. For each patient, compute daily FPCA (K=5) on 24h glucose windows
2. Track FPCA score time-series: score_k(day) for k=1..5
3. Apply Spearman test to each FPCA trajectory (vs raw ISF_effective)
4. Test: CUSUM on daily FPCA scores (vs EXP-325 raw CUSUM 85-100% FA)
5. Compare detection latency and false-alarm rate

**Success Criteria**:
- FPCA-Spearman detects ≥ 9/11 patients (match baseline)
- FPCA-CUSUM false-alarm rate < 30% (vs 85-100% raw CUSUM)
- Detection latency < 14 days for at least 6/11 patients

**Output**: `exp334_fpca_isf_drift.json`

#### EXP-335: Functional Depth for Hypoglycemia Novelty Detection

**Hypothesis**: Functional depth scores flag "atypical" glucose curves that
precede hypoglycemic events, providing an unsupervised signal complementary
to the supervised CNN detector (EXP-322 hypo F1=0.676).

**Baseline**: EXP-322 multi-task hypo F1=0.676, AUC=0.958.

**Method**:
1. Compute modified band depth (MBD) for each 2h glucose window relative to
   all training windows
2. Test: low-depth windows more likely to contain hypo events?
3. Combine: CNN hypo probability × (1 - depth) as ensemble score
4. Evaluate AUC, F1 with recalibrated threshold

**Success Criteria**:
- Depth-hypo correlation: windows with depth < 0.2 have hypo rate ≥ 2× average
- Ensemble AUC ≥ 0.960 (improvement over 0.958 baseline)
- Ensemble F1 ≥ 0.680

**Output**: `exp335_depth_hypo.json`

---

### Phase C: FDA+ML Hybrid Approaches

#### EXP-336: B-spline Encoded Input for CNN (Fast Scale)

**Hypothesis**: Replacing raw 5-min grid with B-spline coefficient representation
provides a more compact, noise-robust input that improves CNN classification
without feature engineering penalties.

**Baseline**: EXP-313 UAM F1=0.939 (8ch × 24 raw); EXP-327 Override F1=0.852.

**Method**:
1. Encode each 2h window: 8 channels × B-spline(n_knots=6) → 8 × 10 coefficients
2. Train 1D-CNN on coefficient representation (input: 8 × 10 instead of 8 × 24)
3. Compare UAM F1, Override F1 vs raw baselines
4. Test: B-spline + derivatives (coeffs + 1st-deriv coeffs) → 16 × 10 input

**Success Criteria**:
- B-spline CNN UAM F1 ≥ 0.93 (within 1% of baseline)
- B-spline CNN Override F1 ≥ 0.84 (within 1.5% of baseline)
- If within tolerance: validates FDA as a viable encoding layer
- Training time reduction (10 coeffs vs 24 steps → ~2.4× fewer parameters)

**Output**: `exp336_bspline_cnn.json`

#### EXP-337: Cross-Covariance Glucose-Insulin for Forecasting

**Hypothesis**: The cross-covariance function between glucose and insulin
curves captures the glucose-insulin dynamic relationship more naturally than
the physics residual ΔG = -ΔIOB × ISF.

**Baseline**: EXP-302 MAE=11.14 mg/dL (67K-param Transformer + physics).

**Method**:
1. Compute pairwise cross-covariance: Cov(glucose(t), IOB(s)) for episode-scale (12h)
2. Extract top-5 eigenvalues of the cross-covariance operator
3. Add as auxiliary features to Transformer encoder
4. Compare: (a) physics residual, (b) cross-cov features, (c) both

**Success Criteria**:
- Cross-cov model MAE ≤ 11.50 (competitive)
- If cross-cov + physics < physics alone → complementary information
- Cross-cov eigenvalues interpretable (e.g., λ1 = ISF effect, λ2 = delayed absorption)

**Output**: `exp337_cross_covariance.json`

#### EXP-338: Functional Clustering vs GRU Clustering for Phenotyping

**Hypothesis**: Functional clustering (k-means in L² space on FPCA-smoothed
curves) produces more clinically interpretable clusters than GRU embedding
clustering, with comparable or better quantitative metrics.

**Baseline**: EXP-304 GRU retrieval Sil=+0.326 (weekly).

**Method**:
1. Compute FPCA(K=10) on weekly glucose curves for all patients
2. k-means on FPCA scores (k=3,5,7,9 — sweep)
3. Same k-means on GRU embeddings for comparison
4. Evaluate: Silhouette, ARI (vs episode labels), clinical interpretability
5. Interpretability: plot cluster centroids as glucose curves

**Success Criteria**:
- Functional k-means Sil ≥ +0.30 at best k
- Cluster centroids visually distinct and clinically meaningful
- ARI(functional) ≥ ARI(GRU) — OR — interpretability qualitatively superior

**Output**: `exp338_functional_clustering.json`

---

### Phase D: Circadian and Advanced FDA

#### EXP-339: Fourier Basis Circadian ISF Profiling

**Hypothesis**: Modeling ISF_effective as a Fourier-basis function over
24h reveals circadian patterns (dawn phenomenon, exercise windows) that
biweekly rolling means cannot resolve.

**Baseline**: EXP-312 identifies drift direction but not circadian structure.

**Method**:
1. Pool insulin cycles by time-of-day for each patient
2. Fit Fourier basis (K=3 harmonics: 24h, 12h, 8h) to ISF_effective(hour)
3. Test: amplitude of 24h harmonic (dawn phenomenon proxy)
4. Compare: patients with known dawn phenomenon vs others
5. Cross-validate: leave-out 2 weeks, predict ISF pattern of held-out weeks

**Success Criteria**:
- 24h harmonic amplitude > 2 × noise floor in ≥ 6/11 patients
- Cross-validated ISF prediction R² > 0.30
- Dawn phenomenon detection: ISF valley at 4-8 AM in susceptible patients

**Output**: `exp339_circadian_isf.json`

#### EXP-340: Curve Registration for Meal-Response Comparison

**Hypothesis**: Aligning postprandial glucose curves via landmark registration
(meal onset → aligned t=0, peak → aligned) enables more meaningful comparison
of meal responses than raw time-aligned windows.

**Baseline**: No existing meal-response comparison framework.

**Method**:
1. Extract postprandial windows (meal announcement → +4h) from treatments.json
2. Identify landmarks: meal onset (t=0), glucose peak, return-to-baseline
3. Apply landmark registration to align all meal responses
4. Compare registered vs unregistered: (a) variance reduction, (b) cluster quality
5. Cluster registered curves → meal-response phenotypes

**Success Criteria**:
- Registration reduces cross-curve variance by ≥ 20%
- Registered clusters have higher Silhouette than unregistered
- At least 3 distinct meal-response phenotypes identified

**Output**: `exp340_meal_registration.json`

#### EXP-341: Multivariate FPCA (MFPCA) for Joint Glucose-Insulin-Carb Analysis

**Hypothesis**: MFPCA on the joint (glucose, IOB, COB) functional object captures
cross-variable dynamics that single-channel FPCA misses, providing richer
embeddings for retrieval and drift detection.

**Baseline**: EXP-332 single-channel FPCA retrieval results.

**Method**:
1. Construct multivariate functional data: (glucose(t), IOB(t), COB(t))
2. Compute MFPCA(K=10) — decomposes joint variation
3. Use MFPCA scores for: (a) retrieval (Sil), (b) ISF drift (Spearman), (c) clustering
4. Compare vs single-channel FPCA and GRU embeddings

**Success Criteria**:
- MFPCA retrieval Sil > single-FPCA Sil by ≥ 0.05
- MFPCA drift detection ≥ 9/11 patients
- Cross-variable PCs interpretable (e.g., PC1 = "insulin-responsive day")

**Output**: `exp341_mfpca.json`

---

## 4. Experiment Dependency Graph

```
EXP-328 (Bootstrap)
  ├── EXP-329 (FPCA variance)
  │     ├── EXP-332 (FPCA retrieval)         [Phase B]
  │     ├── EXP-334 (FPCA ISF drift)         [Phase B]
  │     ├── EXP-338 (Functional clustering)   [Phase C]
  │     ├── EXP-339 (Circadian ISF)           [Phase D]
  │     └── EXP-341 (MFPCA)                  [Phase D]
  ├── EXP-330 (Glucodensity vs TIR)
  │     └── EXP-333 (Glucodensity override)   [Phase B]
  ├── EXP-331 (Functional derivatives)
  │     └── EXP-336 (B-spline CNN)            [Phase C]
  └── EXP-335 (Functional depth)              [Phase B]

  Independent after EXP-329:
  EXP-337 (Cross-covariance)                  [Phase C]
  EXP-340 (Curve registration)                [Phase D]
```

**Critical path**: EXP-328 → EXP-329 → {EXP-332, EXP-334} (highest-impact experiments)

---

## 5. Auto-Research Integration Plan

### 5.1 Module Structure

```
tools/cgmencode/
  fda_features.py          # Core FDA feature extraction (EXP-328 deliverable)
  fda_experiments.py        # Experiment runners for EXP-329–341
  run_pattern_experiments.py # Add FDA experiments to REGISTRY
```

### 5.2 Registration Pattern

Each experiment follows the existing auto-research pattern:

```python
# In fda_experiments.py

def run_fpca_variance(args):
    """EXP-329: FPCA Variance Structure Across Scales.
    
    Hypothesis: FPCA eigenvalue decay rates differ by timescale.
    Baseline: No existing FPCA analysis.
    Success: Identify which scale achieves 95% variance with fewest components.
    """
    from tools.cgmencode.fda_features import bspline_smooth, fpca_scores
    
    results = {"experiment": "EXP-329", "name": "fpca-variance-structure"}
    
    for scale in ['fast', 'episode', 'daily', 'weekly']:
        train, val = load_multiscale_data(patient_paths, scale=scale)
        # ... compute FPCA, record variance explained ...
    
    save_results('exp329_fpca_variance.json', results)

# Registration
REGISTRY['fpca-variance'] = 'run_fpca_variance'
```

### 5.3 Pipeline Integration

FDA features integrate at the encoding layer:

```
Current pipeline:
  raw JSON → 5-min grid → windowing → [8ch × T] → CNN/Transformer

FDA-augmented pipeline:
  raw JSON → 5-min grid → windowing → [8ch × T] → fda_encode() →
    ├── B-spline coefficients [8 × n_coeffs]     → CNN (EXP-336)
    ├── FPCA scores [K]                            → retrieval (EXP-332)
    ├── Glucodensity [n_bins]                      → override (EXP-333)
    ├── Functional derivatives [8ch × T]           → event detect (EXP-331)
    └── Functional depth [scalar]                  → hypo ensemble (EXP-335)
```

The `fda_encode()` function acts as a drop-in preprocessing step. Existing
model architectures remain unchanged — FDA features are new input channels
or alternative representations, not architectural modifications.

### 5.4 Execution Order and Gating

```
Phase 0 (Gate): EXP-328 bootstrap
  GATE: B-spline round-trip < 0.5 mg/dL AND FPCA 90% variance with K ≤ 8
  If FAIL: Investigate scikit-fda vs custom implementation
  If PASS: Unlock Phase A

Phase A (Gate): EXP-329, 330, 331 (feature validation)
  GATE: At least 2/3 experiments show positive signal
  Positive signal defined as: meeting primary success criterion
  If FAIL: FDA features don't add value to our data — document and stop
  If PASS: Unlock Phase B with best-performing features

Phase B: EXP-332, 333, 334, 335 (objective-specific)
  Run in parallel (independent after Phase A)
  GATE: At least 2/4 improve over existing baselines
  If FAIL: FDA useful for analysis but not for model improvement
  If PASS: Unlock Phase C/D for best-performing approaches

Phase C: EXP-336, 337, 338 (hybrid FDA+ML)
  Run in parallel
  No gate — exploratory

Phase D: EXP-339, 340, 341 (advanced FDA)
  Run in parallel
  No gate — exploratory
```

### 5.5 Result Schema Extension

FDA experiments use the standard JSON schema with FDA-specific fields:

```json
{
  "experiment": "EXP-NNN",
  "name": "descriptive-slug",
  "method": "One-line description",
  "fda_config": {
    "basis_type": "bspline|fourier|fpca",
    "n_basis": 12,
    "n_components": 5,
    "smoothing_param": 1e-4,
    "scale": "daily"
  },
  "baseline": {
    "experiment": "EXP-XXX",
    "metric": "value"
  },
  "results": { ... },
  "success_criteria_met": true,
  "timestamp": "ISO-8601"
}
```

---

## 6. Dependencies and Tooling

### 6.1 Python Package Requirements

```
# Add to tools/cgmencode/requirements.txt
scikit-fda>=0.9.1        # Core FDA library (B-spline, FPCA, depth, registration)
# scikit-fda dependencies (auto-installed):
#   - scikit-learn, scipy, numpy, matplotlib (already present)
#   - rdata (for R dataset compatibility)
```

### 6.2 scikit-fda API Mapping

| Our Function | scikit-fda Implementation |
|-------------|--------------------------|
| `bspline_smooth()` | `skfda.representation.basis.BSplineBasis` + `skfda.preprocessing.smoothing.BasisSmoother` |
| `fpca_scores()` | `skfda.preprocessing.dim_reduction.FPCA` |
| `glucodensity()` | Custom: `scipy.stats.gaussian_kde` on glucose values (not in scikit-fda) |
| `functional_derivatives()` | `FDataBasis.derivative()` |
| `functional_depth()` | `skfda.exploratory.depth.ModifiedBandDepth` |
| `l2_distance_to_mean()` | `skfda.misc.metrics.l2_distance` |
| `curve_registration()` | `skfda.preprocessing.registration.LandmarkRegistration` |
| `mfpca()` | Custom: blockwise FPCA on stacked channels |

### 6.3 Computational Cost Estimates

| Operation | Per Window | Per Patient (11 patients) | Notes |
|-----------|-----------|--------------------------|-------|
| B-spline fit | ~1 ms | ~5 s (5000 windows) | Embarrassingly parallel |
| FPCA (K=10) | N/A (batch) | ~2 s | One-shot on all windows |
| Glucodensity | ~0.5 ms | ~2.5 s | KDE per window |
| Derivatives | ~0.1 ms | ~0.5 s | Analytic from B-spline |
| Depth | ~10 ms | ~50 s | O(n²) comparisons |
| Registration | ~50 ms | ~250 s | Iterative alignment |

Total FDA preprocessing: **~5 min for all 11 patients** at all scales.
This is negligible compared to model training (~30-60 min per experiment).

---

## 7. Expected Outcomes and Decision Framework

### 7.1 Best-Case Scenario

FDA representations improve 3+ objectives:
- Pattern retrieval Sil jumps from +0.33 to +0.50+ via FPCA embeddings
- ISF drift detection latency drops from 14 to <10 days via FPCA-CUSUM
- Override F1 improves modestly via glucodensity features
- **Action**: Integrate FDA encoding as standard preprocessing layer

### 7.2 Mixed-Case Scenario

FDA helps 1-2 objectives but not others:
- FPCA good for retrieval/drift but doesn't help event detection
- B-spline encoding matches but doesn't beat raw for CNN tasks
- **Action**: Use FDA selectively in rolling and weekly pipelines only

### 7.3 Worst-Case Scenario

FDA features don't improve any objective beyond baselines:
- B-spline round-trip works but representations don't discriminate
- FPCA captures variance but modes aren't task-relevant
- **Action**: Document negative results; FDA useful for *analysis and
  visualization* (glucodensity plots, functional PCA biplots) even if
  not for *model input*. This aligns with Klonoff et al.'s positioning
  of FDA as complementary to, not replacing, ML.

### 7.3 Decision Checkpoints

| After | Decision | Criteria |
|-------|----------|----------|
| EXP-328 | Proceed / Abort | Toolchain works (round-trip < 0.5 mg/dL) |
| EXP-329-331 | Focus areas | Which features show signal → prioritize Phase B |
| EXP-332-335 | Integration depth | How many objectives benefit → full/selective/none |
| EXP-336-341 | Production pathway | Best hybrid approach → deployment architecture |

---

## 8. Relationship to Klonoff et al. (2025)

This experiment program operationalizes the "CGM Data Analysis 2.0" vision:

| Klonoff et al. Concept | Our Experiment | Validation |
|------------------------|----------------|------------|
| "Treats CGM as dynamic curves rather than discrete points" | EXP-328, 336 | B-spline encoding vs raw grid |
| "Glucodensity profiles" (Matabuena) | EXP-330, 333 | Glucodensity vs TIR; as override features |
| "Functional principal components" (Gecili) | EXP-329, 332, 334 | FPCA for retrieval, drift, variance |
| "Phenotyping from glucose curve shapes" | EXP-338 | Functional vs GRU clustering |
| "Inter-/intra-day reproducibility" | EXP-339 | Circadian FPCA profiling |
| "Time-dependent observations (weekday vs weekend)" | EXP-340 | Curve registration for meal comparison |
| "ML models can leverage FDA" | EXP-336, 337 | B-spline CNN, cross-covariance Transformer |
| "Foundation model … generalizable representations" | EXP-341 | MFPCA as unsupervised multivariate encoding |

The key insight from Klonoff et al. that motivates this program:

> "Several ML architectures, including recurrent neural networks, convolutional
> neural networks, and transformers, are capable of learning temporal patterns
> in time series data, similar to Functional Data Analysis. However, AI offers
> additional capabilities as compared to Functional Data Analysis."

Our experiments test the **converse**: does FDA offer additional capabilities
compared to the ML approaches we've already validated? Specifically, do FDA
representations provide features that CNNs/Transformers fail to learn from
raw data? The feature–problem–encoding matrix (§2) is designed to answer this
question systematically.

---

## 9. Summary: Prioritized Experiment Queue

| Priority | ID | Name | Objective(s) | Key Question |
|----------|-----|------|-------------|-------------|
| **P0** | EXP-328 | FDA Bootstrap | Infrastructure | Can we compute FDA features from our data? |
| **P1** | EXP-329 | FPCA Variance | All | Where is functional structure richest? |
| **P1** | EXP-330 | Glucodensity vs TIR | Retrieval, Override | Does distributional representation add signal? |
| **P1** | EXP-331 | Functional Derivatives | Event, Override | Are B-spline derivatives cleaner than finite-diff? |
| **P2** | EXP-332 | FPCA Retrieval | Retrieval | Can FPCA beat GRU embeddings (Sil=+0.33)? |
| **P2** | EXP-334 | FPCA ISF Drift | ISF Drift | Can FPCA-CUSUM detect drift faster than 14 days? |
| **P2** | EXP-335 | Depth + Hypo | Event | Does functional depth flag pre-hypo anomalies? |
| **P2** | EXP-333 | Glucodensity Override | Override | Does distributional context help override (F1=0.85)? |
| **P3** | EXP-336 | B-spline CNN | Event, Override | Is coefficient-space input viable for CNN? |
| **P3** | EXP-337 | Cross-Covariance | Forecast | Does Cov(glucose, insulin) beat physics residual? |
| **P3** | EXP-338 | Functional Clustering | Retrieval | Is functional k-means more interpretable? |
| **P4** | EXP-339 | Circadian ISF | ISF Drift | Can Fourier basis detect dawn phenomenon? |
| **P4** | EXP-340 | Meal Registration | Analysis | Does curve alignment improve meal comparison? |
| **P4** | EXP-341 | MFPCA | Retrieval, Drift | Does multivariate FDA capture cross-variable dynamics? |

---

## Results

Phase A and Phase B experiments (EXP-328–335) completed 2026-04-05.
See **[fda-experiment-results-2026-04-05.md](fda-experiment-results-2026-04-05.md)** for full findings, data tables, and integration recommendations.
