# Continuous Physiological State Modeling: From Sparse Events to Functional Signals

**Date**: 2026-04-05
**Context**: Synthesis of UVA/Padova compartment model, oref0 insulin curves,
cgmsim-lib implementations, and FDA functional analysis — exploring whether we can
model **continuous metabolic states** (absorption, sensitivity, resistance) rather
than sparse treatment events, using physiological compartments as a guide.

---

## 1. What the UVA/Padova Model Actually Represents

The UVA/Padova T1DMS model (`externals/cgmsim-lib/src/lt1/core/models/UvaPadova_T1DMS.ts`)
is a **20-state ODE system** that models the flow of glucose and insulin through
physiological compartments. It does NOT model individual organ-level biochemistry
(no glycogen store levels, no individual cell insulin receptors). Instead, it models
**compartmental transfer rates** — how substances move between body compartments.

### 1.1 The Compartment Map

```
                         INPUTS
                    ┌──────┴──────┐
                    │             │
              Carbs (mg/min)   Insulin (pmol/min)
                    │             │
                    ▼             ▼
          ┌─────────────┐  ┌──────────┐
          │  STOMACH     │  │ SUBCUT   │
          │  Qsto1 ──►  │  │ Isc1 ──► │
          │  Qsto2 ──►  │  │ Isc2 ──► │
          │  (gastric    │  │ (2-comp  │
          │   emptying)  │  │  depot)  │
          └──────┬──────┘  └────┬─────┘
                 │               │
          Rate of            Insulin
          Appearance          Appearance
          (Ra)                (Rai)
                 │               │
                 ▼               ▼
          ┌──────────┐    ┌──────────┐
          │   GUT    │    │  PLASMA  │
          │  Qgut    │    │  INSULIN │
          │          │    │  Ip ◄──► │
          └────┬─────┘    │  Il      │
               │          └────┬─────┘
               │               │
               ▼               ▼
          ┌──────────────────────────────────────┐
          │           GLUCOSE SYSTEM              │
          │                                      │
          │  Gp (plasma)  ◄──k1/k2──►  Gt (tissue) │
          │                                      │
          │  Sources:        Sinks:              │
          │  + EGP (liver)   - Uid (insulin-dep) │
          │  + Ra (gut)      - Uii (insulin-indep)│
          │                  - E (renal excretion)│
          │                  - k1·Gp (to tissue)  │
          └──────────────────────────────────────┘
                 │               │
                 ▼               ▼
          ┌──────────┐    ┌──────────────┐
          │  SENSOR  │    │  DELAYED     │
          │  Gs      │    │  INSULIN     │
          │  (CGM    │    │  ACTION      │
          │  delay)  │    │  XL, I', X   │
          └──────────┘    │  (3-stage    │
                          │   cascade)   │
                          └──────────────┘

          ┌──────────────────────────────────┐
          │       GLUCAGON SUBSYSTEM         │
          │  H (plasma), XH (liver action)   │
          │  SRHs (secretion), Hsc1/Hsc2     │
          │  Counter-regulatory response to  │
          │  hypoglycemia                    │
          └──────────────────────────────────┘
```

### 1.2 The 20 State Variables — What Each Represents

| State | Unit | Physiological Meaning |
|-------|------|----------------------|
| **Gp** | mg/kg | Glucose mass in plasma (accessible compartment) |
| **Gt** | mg/kg | Glucose mass in tissue (non-accessible, peripheral) |
| **Gs** | mg/kg | Glucose mass at sensor site (CGM reads this, with delay Td≈10min) |
| **Ip** | pmol/kg | Insulin mass in plasma |
| **Il** | pmol/kg | Insulin mass in liver |
| **Qsto1** | mg | Carbs in stomach phase 1 (solid → liquid) |
| **Qsto2** | mg | Carbs in stomach phase 2 (liquid → intestine) |
| **Qgut** | mg | Carbs in intestine (being absorbed) |
| **XL** | pmol/l | Delayed insulin signal for liver (EGP suppression) |
| **I'** | pmol/l | Intermediate delayed insulin (first delay stage) |
| **X** | pmol/l | Insulin action on glucose utilization (tissue uptake) |
| **Isc1** | pmol/kg | Insulin in subcutaneous depot 1 (fast absorption) |
| **Isc2** | pmol/kg | Insulin in subcutaneous depot 2 (slow absorption) |
| **H** | pg/ml | Glucagon in plasma |
| **XH** | — | Glucagon action on liver (EGP stimulation) |
| **SRHs** | — | Glucagon secretion rate (static component) |
| **Hsc1** | — | Glucagon in subcutaneous depot 1 |
| **Hsc2** | — | Glucagon in subcutaneous depot 2 |
| **MealMemory** | mg | Total mass of most recent meal (for emptying rate) |
| **QstoMemory** | mg | Stomach content when last meal started |

### 1.3 Key Physiological Processes Modeled

#### Endogenous Glucose Production (EGP) — "The Liver"

```
EGP = max(0, kp1 - kp2·Gp - kp3·XL + kxi·XH)
```

This models the liver's glucose output as:
- **kp1** (2.7 mg/kg/min): basal production rate (≈ glycogenolysis + gluconeogenesis)
- **−kp2·Gp**: glucose self-suppression (high plasma glucose → liver reduces output)
- **−kp3·XL**: insulin suppression (delayed insulin signal reduces liver output)
- **+kxi·XH**: glucagon stimulation (counter-regulatory → liver increases output)

**What it does NOT model**: Glycogen store levels. The liver is treated as having
infinite capacity — there's no "glycogen full/empty" state. This is a known limitation.
After prolonged fasting or intense exercise, real glycogen depletion reduces EGP
but UVA/Padova has no state variable for this.

#### Insulin Sensitivity / Resistance

**Insulin-dependent glucose utilization (Uid)**:
```
Uid = ((Vm0 + Vmx·X·(1 + γ·risk)) · Gt) / (Km0 + Gt)
```

This is a **Michaelis-Menten** (saturable) kinetic:
- **Vm0** (2.5 mg/kg/min): basal glucose utilization (at zero insulin action)
- **Vmx** (0.047): insulin-dependent component — THIS IS INSULIN SENSITIVITY
- **X**: delayed insulin action (the actual driver of glucose uptake)
- **Km0** (225.59 mg/kg): half-saturation glucose mass (glucose dependency)
- **γ·risk**: hypoglycemia risk amplifier (increases utilization when BG drops fast)

**Insulin resistance is the INVERSE**: A patient with low Vmx has high insulin
resistance — their tissues respond poorly to insulin. Vmx is a fixed parameter
in UVA/Padova, NOT a time-varying state. This is the key limitation for our work.

#### Insulin Absorption (Subcutaneous → Plasma)

Two-compartment subcutaneous depot:
```
dIsc1/dt = -(kd + ka1)·Isc1 + IIR/BW     (injection site → fast depot)
dIsc2/dt = kd·Isc1 - ka2·Isc2             (fast depot → slow depot)
Rai = ka1·Isc1 + ka2·Isc2                 (appearance rate in plasma)
```

This produces the characteristic **rapid-acting insulin curve**: rise to peak
at ~55-75 min, then exponential tail to ~5-6h. The two-compartment structure
creates approximate symmetry around the peak (rising phase ≈ falling phase,
but with slightly heavier tail).

#### Carb Absorption (Stomach → Gut → Plasma)

Three-compartment GI tract with **nonlinear gastric emptying**:
```
dQsto1/dt = -kgri·Qsto1 + Meal           (solid → liquid stomach)
dQsto2/dt = -kempt·Qsto2 + kgri·Qsto1    (liquid stomach → intestine)
dQgut/dt  = -kabs·Qgut + kempt·Qsto2     (intestine → plasma)
Ra = f·kabs·Qgut/BW                      (rate of appearance in plasma)
```

Where **kempt** (gastric emptying rate) varies nonlinearly:
```
kempt = kmin + (kmax-kmin)/2 · (tanh(α(Qsto-b·D)) - tanh(β(Qsto-c·D)) + 2)
```

This creates a **bell-shaped absorption curve** that is NOT symmetric:
- Rising phase: ~30-60 min (stomach emptying accelerates)
- Peak absorption: ~60-90 min
- Falling phase: ~90-360 min (long intestinal absorption tail)
- Parameters b=0.69, c=0.17 control the asymmetry

### 1.4 How Sin/Cos Maps to Sensitivity/Resistance

cgmsim-lib already uses sin/cos for circadian modulation (`src/sinus.ts`):

```
sin_factor = sin(360° × hour/24) × 0.2 + 1.0    (oscillates 0.8 → 1.2)
cos_factor = cos(360° × hour/24) × 0.2 + 1.0    (oscillates 0.8 → 1.2)
```

The **liver production** is multiplied by `sin_factor`, creating:
- **6 AM peak** (sin=1.2): dawn phenomenon — 20% more hepatic output
- **6 PM trough** (sin=0.8): evening — 20% less hepatic output

**For insulin sensitivity/resistance mapping**, you could define:

```
ISF_effective(t) = ISF_base × sensitivity_modulator(t)
sensitivity_modulator(t) = 1 + A·sin(2π(t - t_peak)/24) + B·cos(2π(t - t_peak)/24)
```

Where:
- **A, B** are patient-specific circadian amplitude parameters
- **t_peak** is the hour of peak sensitivity (typically early afternoon)
- The modulator oscillates between (1-√(A²+B²)) and (1+√(A²+B²))

This maps insulin sensitivity as a CONTINUOUS FUNCTION on sin/cos, exactly as
you're proposing. The question is whether we can LEARN A and B from data
rather than assuming fixed values.

---

## 2. The Core Proposal: Continuous Physiological State Channels

### 2.1 The Insight

Instead of modeling sparse events (boluses, carbs), model the **continuous
physiological states** that those events create. The UVA/Padova model tells us
which states matter:

| Sparse Event | Continuous State(s) It Creates | UVA/Padova Variable |
|-------------|-------------------------------|---------------------|
| Bolus dose | Subcutaneous insulin depot | Isc1, Isc2 |
| Bolus dose | Plasma insulin concentration | Ip |
| Bolus dose | Insulin action on tissue | X (delayed signal) |
| Bolus dose | Liver suppression | XL (delayed signal) |
| Carb entry | Stomach contents | Qsto1, Qsto2 |
| Carb entry | Gut absorption | Qgut |
| Carb entry | Glucose appearance rate (Ra) | f·kabs·Qgut/BW |
| Basal rate | Continuous insulin infusion | Part of Isc1 |

**We already have IOB and COB as continuous signals** — but these are crude
approximations. IOB uses a simple exponential decay; COB uses linear decay.
The UVA/Padova model shows reality has 3 insulin compartments (Isc1 → Isc2 → Ip)
and 3 carb compartments (Qsto1 → Qsto2 → Qgut), each with different time constants.

### 2.2 Proposed: Physics-Informed Continuous State Channels

Replace our current sparse (bolus, carbs) and crude continuous (IOB, COB)
channels with **richer continuous state signals**:

#### Tier 1: Physiological Absorption Curves (Computable from Data)

These can be computed from treatment logs + known pharmacokinetics:

| Channel | Formula | What It Captures | Density |
|---------|---------|-----------------|---------|
| **insulin_activity(t)** | Σᵢ dose_i · a(t-t_i, DIA, peak) | Rate of insulin action NOW | Dense (continuous curve) |
| **insulin_action_integral(t)** | ∫₀ᵗ insulin_activity(τ) dτ | Cumulative insulin effect | Dense |
| **carb_absorption_rate(t)** | Σᵢ carbs_i · Ra(t-t_i, abs_time) | Rate of carb appearance NOW | Dense (continuous curve) |
| **carb_absorption_integral(t)** | ∫₀ᵗ carb_rate(τ) dτ | Cumulative carb effect | Dense |
| **net_metabolic_balance(t)** | carb_rate(t)/CR - insulin_activity(t)·ISF | Instantaneous net glucose drive | Dense |
| **hepatic_production(t)** | f(IOB(t), hour(t)) | Liver glucose output estimate | Dense |

Where `a(t, DIA, peak)` is the oref0/cgmsim-lib exponential insulin activity curve:
```python
tau = peak * (1 - peak/DIA) / (1 - 2*peak/DIA)
a(t) = (1/tau²) * t * (1 - t/DIA) * exp(-t/tau)    # normalized to integrate to 1
```

#### Tier 2: B-Spline Functional Representations (FDA)

Apply FDA B-spline smoothing to the Tier 1 curves to create noise-robust
continuous functional representations:

```python
def continuous_absorption_features(boluses, carbs, timestamps, n_knots=12):
    """Convert sparse events to continuous B-spline functional channels."""

    # 1. Compute pharmacokinetic curves from sparse events
    insulin_activity = compute_insulin_activity_curve(boluses, timestamps, DIA=5.0, peak=55)
    carb_rate = compute_carb_absorption_curve(carbs, timestamps, abs_time=3.0)

    # 2. Fit B-splines for noise-robust continuous representation
    insulin_fd = bspline_smooth(insulin_activity, n_knots=n_knots)
    carb_fd = bspline_smooth(carb_rate, n_knots=n_knots)

    # 3. Compute functional derivatives (rate of change of absorption)
    insulin_accel = functional_derivative(insulin_fd, order=1)  # d/dt of activity
    carb_accel = functional_derivative(carb_fd, order=1)

    # 4. Compute net metabolic balance
    net_balance = carb_fd / CR - insulin_fd * ISF

    return {
        'insulin_activity': insulin_fd,      # continuous insulin effect
        'insulin_accel': insulin_accel,       # is insulin ramping up or down?
        'carb_rate': carb_fd,                 # continuous carb appearance
        'carb_accel': carb_accel,             # is absorption ramping up or down?
        'net_balance': net_balance,           # who's winning: insulin or carbs?
    }
```

#### Tier 3: Learned Continuous States (Pre-training Hypothesis)

**The key hypothesis**: We can use UVA/Padova compartment states as **pre-training
targets** to learn continuous physiological state representations from CGM data alone.

```
Pre-training Phase:
  Input:  CGM glucose trace + sparse treatment events
  Target: UVA/Padova internal states [Gp, Gt, Ip, X, XL, Qgut, Ra, EGP]
  Model:  Encoder that learns to infer hidden compartment states from
          observable glucose + treatment history

Downstream Phase:
  Input:  CGM glucose + learned continuous states
  Target: Event detection, override prediction, ISF drift, etc.
  Model:  Multi-scale pipeline with continuous state channels
```

The pre-training step teaches the model what the physiological states SHOULD
look like, and then the downstream model uses those inferred states as dense
input channels.

### 2.3 Scaling: Bolus Pulses vs Basal Strokes vs Endogenous Production

The scaling question is critical because three sources of insulin operate at
very different magnitudes and time constants:

| Source | Magnitude | Duration | Character | UVA/Padova Treatment |
|--------|-----------|----------|-----------|---------------------|
| **Bolus** | 2-15 U pulse | 5-6h tail | Sparse impulse | Added to Isc1 as IIR pulse |
| **Basal** | 0.5-2.0 U/hr continuous | Hours-days | Step function | Continuous IIR |
| **Endogenous (EGP)** | ~1-2 mg/dL/5min | Continuous | Modulated by insulin + circadian | kp1 - kp2·Gp - kp3·XL |

In UVA/Padova, **all three funnel through the same Isc1/Isc2 → Ip pathway**:
- Bolus: instantaneous addition to Isc1 (IIR spike for 1 minute)
- Basal: continuous addition to Isc1 (IIR = basal rate, steady)
- Endogenous: NOT modeled through Isc (it's modeled as EGP, a separate glucose source)

**For our continuous feature representation**, this suggests:

```python
# Separate insulin into components by source and time constant
channels = {
    'insulin_bolus_activity': sum of bolus-origin activity curves,
    'insulin_basal_activity': steady-state basal contribution,
    'insulin_total_plasma':   IOB-like total (bolus + basal),
    'egp_estimate':           liver production estimate (circadian + insulin suppression),
    'net_glucose_flux':       Ra + EGP - Uid - Uii - E  (the complete glucose equation)
}
```

The key insight from UVA/Padova is that **basal insulin and bolus insulin have the
same pharmacokinetic curve** once injected — the difference is purely in the
TIMING pattern (continuous vs pulse). So the continuous IOB channel already captures
both. What we're MISSING is the endogenous production (EGP), which has its own
dynamics driven by insulin suppression and circadian rhythm.

### 2.4 Insulin Sensitivity on Sin/Cos — The Circadian ISF Map

cgmsim-lib's circadian model (`sinus.ts`) already maps time → metabolic modulation
using sin/cos. We can extend this to create a **learned circadian ISF surface**:

```python
class CircadianISF(nn.Module):
    """Model insulin sensitivity as a continuous function of circadian phase."""

    def __init__(self, n_harmonics=3):
        super().__init__()
        # Fourier series: ISF(t) = a₀ + Σ(aₙcos(nωt) + bₙsin(nωt))
        self.a0 = nn.Parameter(torch.tensor(1.0))  # baseline ISF multiplier
        self.a_coeffs = nn.Parameter(torch.zeros(n_harmonics))  # cosine amplitudes
        self.b_coeffs = nn.Parameter(torch.zeros(n_harmonics))  # sine amplitudes

    def forward(self, hour_of_day):
        """Returns ISF modulation factor at given hour(s)."""
        omega = 2 * math.pi / 24.0
        modulator = self.a0
        for n in range(len(self.a_coeffs)):
            modulator = modulator + self.a_coeffs[n] * torch.cos((n+1) * omega * hour_of_day)
            modulator = modulator + self.b_coeffs[n] * torch.sin((n+1) * omega * hour_of_day)
        return modulator  # multiply by base ISF to get effective ISF

    def sensitivity_curve(self):
        """Return 24h sensitivity profile."""
        hours = torch.linspace(0, 24, 288)  # 5-min resolution
        return hours, self.forward(hours)
```

This creates a **learnable circadian sensitivity function** that could be:
1. Pre-trained from UVA/Padova's effective Vmx × circadian modulation
2. Fine-tuned per patient from observed insulin response patterns
3. Used as a continuous feature channel (ISF_effective(t) at each timestep)

The sin/cos mapping naturally handles the periodicity — ISF at 23:55 smoothly
connects to ISF at 00:05. Higher harmonics (n=2,3) capture non-sinusoidal
patterns like "dawn phenomenon spike" or "post-exercise sensitivity window".

**Resistance vs Sensitivity mapping**:
```
ISF_effective(t) = ISF_base × circadian_modulator(t)
  where modulator > 1.0 → increased sensitivity (exercise, post-meal)
  where modulator < 1.0 → increased resistance (dawn phenomenon, stress, illness)
```

---

## 3. Data Science Meta-Methods for Determining Correct Modeling

### 3.1 Approach: Use UVA/Padova as Ground Truth, Then Validate

**Phase 1: Generate Pseudo-Labels**
```
For each patient:
  1. Run UVA/Padova simulation on their treatment history (uva_replay.js)
  2. Extract internal states at each 5-min timestep:
     [Gp, Gt, Ip, X, XL, Qsto1, Qsto2, Qgut, H, XH, EGP, Ra, Uid]
  3. These become continuous-state pseudo-labels
```

**Phase 2: Train State Inference Model**
```
Input:  [glucose(t), bolus_events, carb_events, basal_rate(t)]  (observable)
Output: [Ip(t), X(t), Ra(t), EGP(t)]  (hidden continuous states)
Loss:   MSE to UVA/Padova pseudo-labels
Architecture: 1D-CNN or Transformer (proven best for our data)
```

**Phase 3: Evaluate What's Learnable**
```
For each hidden state:
  - Can we predict Ip(t) from observables? (likely YES — it's IOB with better PK)
  - Can we predict X(t)? (harder — delayed + transformed insulin signal)
  - Can we predict Ra(t)? (meal detection problem + absorption model)
  - Can we predict EGP(t)? (hardest — requires circadian + insulin context)
```

**Phase 4: Use Learned States as Features**
```
Replace:  [glucose, IOB, COB, basal, bolus, carbs, time_sin, time_cos]
With:     [glucose, Ip_hat, X_hat, Ra_hat, EGP_hat, net_flux_hat]
          All dense, all continuous, all physiologically grounded
```

### 3.2 Hypothesis Testing Framework

| Hypothesis | Test Method | Success Criterion |
|-----------|------------|-------------------|
| **H1**: Continuous Ip/X/Ra channels improve episode clustering | Compare 5ch base vs 5ch+continuous states at 12h | Silhouette > -0.339 |
| **H2**: Learned EGP captures circadian better than sin/cos | Correlate EGP_hat with actual dawn phenomenon events | r > 0.5 |
| **H3**: Pre-trained state encoder generalizes across patients | LOO: train state encoder on 10 patients, test on 11th | State prediction MSE < 2× within-patient |
| **H4**: Net metabolic balance predicts override need | Train classifier on net_flux feature | Override F1 > 0.852 (current best) |
| **H5**: Insulin activity curve captures ISF better than IOB | Compare ISF_effective = ΔBG/activity vs ΔBG/ΔIOB | Lower variance in ISF_effective estimates |

### 3.3 Bayesian Meta-Analysis for Model Selection

Rather than choosing ONE absorption model a priori, use Bayesian model comparison:

```python
# Candidate absorption models for insulin
models = {
    'exponential':  lambda t, DIA: exp(-t/tau) * t,           # oref0 style
    'bilinear':     lambda t, DIA: piecewise_triangle(t),      # oref0 bilinear
    'two_compartment': lambda t, params: Isc1(t) + Isc2(t),   # UVA/Padova
    'learned_spline': lambda t: bspline_coeffs @ basis(t),     # FDA B-spline
}

# For each patient, compute Bayesian evidence (marginal likelihood)
# for each model given observed glucose responses to boluses
for patient in patients:
    for name, model in models.items():
        evidence[patient][name] = marginal_likelihood(
            observed_glucose, model, prior_params)

# Select best model per patient (or mixture)
# If one model dominates → use it globally
# If patient-specific → learn patient embedding that selects model
```

---

## 4. The Complete Vision: Physiology-Informed Multi-Scale Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 0: Sparse Event → Continuous Physiological State     │
│                                                             │
│  bolus events ──► insulin_activity(t)  [PK curve, dense]    │
│  carb events  ──► carb_absorption(t)   [GI curve, dense]    │
│  basal rate   ──► basal_contribution(t) [step → smooth]     │
│  (circadian)  ──► egp_estimate(t)      [liver model]        │
│  (all above)  ──► net_metabolic_flux(t) [Ra+EGP-Uid-E]     │
│                                                             │
│  Optional: B-spline smooth all continuous states (FDA)       │
│  Optional: Pre-train state encoder from UVA/Padova labels    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼ All channels now DENSE and CONTINUOUS
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Multi-Scale Feature Windows                       │
│                                                             │
│  Fast (2h):    [glucose, insulin_act, carb_rate,            │
│                 net_flux, egp_est, basal]     6 channels    │
│                                                             │
│  Episode (12h): [glucose, insulin_integral, carb_integral,  │
│                  COB, net_flux]               5 channels    │
│                  (NO time, NO sparse bolus)                  │
│                                                             │
│  Daily (24h):   [glucose, insulin_act, carb_rate,           │
│                  egp_est, circadian_isf, net_flux]           │
│                  (time RESTORED via circadian_isf)           │
│                                                             │
│  Weekly (7d):   [glucose, insulin_integral, carb_integral,  │
│                  circadian_isf_mean, net_flux_trend]         │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: Scale-Specific Models                             │
│                                                             │
│  Fast:    1D-CNN (proven best) → event detection            │
│  Episode: CNN/GRU + triplet loss → pattern clustering       │
│  Daily:   FDA + FPCA(K=8) → drift detection                 │
│  Weekly:  GRU embedding → trend retrieval                   │
└─────────────────────────────────────────────────────────────┘
```

### Key Properties of This Design:

1. **No sparse channels at ANY scale**: All inputs are continuous functions.
   The density mismatch between CGM (288/day) and boluses (3-8/day) is eliminated
   by converting events to their continuous pharmacokinetic effects.

2. **Symmetry respected by construction**: Absorption curves are intrinsically
   symmetric-ish around their peak. The model sees the SHAPE of the absorption
   (rising, peak, falling) rather than the discrete event that caused it.

3. **Time-translation invariance where appropriate**: Episode and weekly scales
   use no clock-time features. Circadian effects enter ONLY through physiological
   mechanisms (EGP modulation, ISF modulation) at daily scale.

4. **Physics-grounded**: Every channel has a physiological interpretation rooted
   in the UVA/Padova compartment model, not arbitrary feature engineering.

5. **Learnable and testable**: The pharmacokinetic curves can be computed from
   known models (oref0 exponential, UVA/Padova two-compartment), or learned from
   data via B-spline fitting, or pre-trained via UVA/Padova pseudo-labels.

---

## 5. Proposed Experiment Sequence

### Phase A: Compute & Validate Continuous States

**EXP-348**: Compute insulin_activity(t) and carb_absorption_rate(t) from treatment
logs using oref0 exponential model. Validate by checking that net_metabolic_balance
correlates with glucose rate of change (should have r > 0.4).

**EXP-349**: Run UVA/Padova simulation for all 11 patients. Extract internal states.
Compare UVA/Padova Ra(t) vs our computed carb_absorption_rate(t) — quantify the
gap between simple model and full physiological model.

### Phase B: Replace Sparse Channels with Continuous States

**EXP-350**: Episode-scale (12h) pattern clustering with continuous state channels
[glucose, insulin_activity, carb_rate, net_flux, COB] vs baseline 5ch.
Success: Silhouette > -0.339.

**EXP-351**: Fast-scale (2h) override classification with continuous state channels.
Success: F1 > 0.852 (current best at 15min lead).

### Phase C: Pre-Training from UVA/Padova

**EXP-352**: Train state inference encoder: Input=[glucose, treatments] →
Output=[Ip, X, Ra, EGP]. Evaluate which hidden states are predictable from
observable data alone.

**EXP-353**: Use pre-trained encoder's representations as input features for
downstream objectives. Compare against hand-computed PK curves (EXP-350/351).

### Phase D: Learned Circadian ISF

**EXP-354**: Train CircadianISF model (Fourier series on sin/cos) per patient.
Evaluate whether learned ISF modulation captures dawn phenomenon and exercise
windows better than fixed sin/cos encoding.

---

## 6. Source Code References

| Component | File | Key Lines |
|-----------|------|-----------|
| UVA/Padova 20-state ODE | `externals/cgmsim-lib/src/lt1/core/models/UvaPadova_T1DMS.ts` | 172-326 (computeDerivatives) |
| UVA/Padova parameters | same | 341-461 (parameterDescription) |
| Liver production (simple) | `externals/cgmsim-lib/src/liver.ts` | 47-100 (Hill equation) |
| Liver production (physics) | `tools/cgmencode/physics_model.py` | 54-64 (_liver_production) |
| Circadian rhythm | `externals/cgmsim-lib/src/sinus.ts` | 50-98 (sin/cos calculation) |
| Insulin activity curve | `externals/cgmsim-lib/src/utils.ts` | 73-100 (getExpTreatmentActivity) |
| oref0 IOB calculation | `externals/oref0/lib/iob/calculate.js` | 1-80 (bilinear + exponential) |
| Carb absorption (cgmsim) | `externals/cgmsim-lib/src/carbs.ts` | 1-80 (fast + slow carb split) |
| Current IOB computation | `tools/cgmencode/real_data_adapter.py` | 83-103 (exponential decay) |
| Current COB computation | `tools/cgmencode/real_data_adapter.py` | 106-124 (linear decay) |
| Feature schema | `tools/cgmencode/schema.py` | 16-170 (8/21/39 feature definitions) |
| UVA replay driver | `tools/cgmencode/uva_replay.js` | 154-208 (ODE integration loop) |
| FDA B-spline smoothing | `tools/cgmencode/fda_features.py` | 61-96 (bspline_smooth) |
