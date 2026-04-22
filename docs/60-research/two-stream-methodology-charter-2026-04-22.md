# Two-Stream Methodology Charter — Physics vs Settings

**Date**: 2026-04-22
**Scope**: EXP-2840 + audit of EXP-2737 through EXP-2832
**Status**: Charter document; binding on all subsequent experiments and reports

---

## 1. The Conflation Problem

User-articulated framing (2026-04-22):

> Human and AID intervention will help restore the homeostatic balance as
> virtue of the patient staying alive — we need to compensate for this and
> subtract it from the analysis appropriately to help properly model the
> physics observed, and separate that understanding from techniques used
> to isolate and extract/calculate settings appropriately. These might be
> two separate topics which may lead to counter causal reasoning if conflated.

The physical observation: **patients in this dataset are alive**. Therefore
human + controller intervention has been continuously restoring homeostasis.
Every BG observation is a *post-intervention* signal. Natural physiology
has been actively masked by the closed-loop system that exists to mask it.

---

## 2. Two Streams (Now Formalized)

### Stream A — Physics Modeling (Causal / Biological)

**Goal**: Estimate what the body does in the absence of intervention.

**Examples of Stream A claims**:
- "EGP is X mg/dL/hr at rest"
- "Carb absorption follows pattern Y"
- "Insulin sensitivity declines after Z hours"

**Method requirements**:
- Subtract intervention contribution explicitly
- Report counterfactual error bands (irreducible due to intervention non-removability)
- Acknowledge that absolute estimates are inherently lower-bounded by the
  intervention's masking effect

**Use cases**: Digital twin construction, replay simulators, scientific
hypothesis testing about biology.

### Stream B — Settings Extraction (Operational / Control)

**Goal**: Find the ISF/CR/basal/target values that the controller should use.

**Examples of Stream B claims**:
- "Patient's effective ISF in the loop is X mg/dL/U"
- "Aged-cannula ISF drops 30%, recommend site change"
- "State-1 windows show +1 mg/dL/hr drift, suggest temporary ISF reduction"

**Method requirements**:
- Use observed responses INCLUDING intervention; settings are tuned to
  the closed-loop system, not naked physiology
- Treat extracted values as operating-point parameters, not biology
- Validate against operational outcomes (TIR, hypos), not against
  inferred biology

**Use cases**: Per-patient profile recommendations, triage flags, safety
gates.

---

## 3. Quantitative Justification (EXP-2840)

The intervention is ~5× stronger than natural physiology in this dataset:

| Metric                                       | Value          |
|----------------------------------------------|----------------|
| Median intervention effect rate              | 86.9 mg/dL/hr  |
| Canonical EGP estimate range (Stream A)      | 0–25 mg/dL/hr  |
| Median observed BG std                       | 46.9 mg/dL     |
| Intervention/BG-std ratio (median)           | 1.57           |
| Patients with intervention/BG-std > 0.5      | **100%**       |
| Patients with intervention/BG-std > 1.0      | **82%**        |
| Median intervention-active fraction of time  | 72%            |
| Median TDD                                   | 37.2 U/day     |

This means: **observed BG variability is dominated by what the controller
is doing, not by what the body is doing**. Stream A inferences from this
data have a fundamental observability limit.

---

## 4. Conflation Modes to Avoid

| Mode | Description | Example to NOT make |
|------|-------------|---------------------|
| C1 | Infer biology from closed-loop drops, then recommend profile changes | "Observed ISF in loop is 50; profile says 80; reduce profile" |
| C2 | Subtract intervention to estimate "true" sensitivity, then use it as a setting | "Biological ISF after intervention removal = 120; set ISF=120" |
| C3 | Use Stream A estimates (EGP, sensitivity) as direct controller parameters | "EGP is 5 mg/dL/hr, set basal to compensate exactly" |

---

## 5. Audit of Prior Experiments

| EXP            | Topic                       | Stream                | Risk           | Status                  |
|----------------|-----------------------------|-----------------------|----------------|-------------------------|
| EXP-2737       | Profile ISF gap             | B (settings)          | LOW            | Correctly framed        |
| EXP-2756/2758  | EGP from drift              | A (physics)           | MEDIUM         | Conservative estimate   |
| EXP-2820       | EGP audit                   | A (physics)           | MEDIUM         | Should label STREAM A   |
| EXP-2821       | EGP-aware report cards      | A→B conflation        | HIGH (CAUGHT)  | Mitigation in place     |
| EXP-2830       | Formulation constant        | A (physics)           | MEDIUM         | Refutation may be artifact|
| EXP-2831       | Multi-timescale wear        | B (settings/triage)   | LOW            | Triage = Stream B       |
| EXP-2823 H2    | Within-patient state EGP    | A (physics)           | **HIGH**       | 0-valued proxies = subtraction artifact|
| EXP-2832       | Inverse EGP                 | A→B mixed             | MEDIUM         | Honest-use guide present|

**EXP-2823 H2 NEW INSIGHT**: The "NOT FOUND" result for within-patient
state EGP variation is partly an observability artifact, not necessarily
a true negative. The proxy (`basal × scheduled_isf` in flat windows)
returned 0 for many patient/state combinations because controllers heavily
suspend basal — but the suspension is *because* the system needs no basal
push, which is exactly when EGP would be visible. The Stream A claim
"state doesn't capture within-patient EGP" should be relabeled
"state×EGP within-patient signal not extractable from current closed-loop
data."

---

## 6. Methodology Guardrails (Binding)

These apply to all future experiments and reports:

- **G1**: Stream A experiments must report counterfactual error bands
  derived from intervention-subtraction; absolute estimates are inherently
  lower-bounded.
- **G2**: Stream B experiments must NOT use Stream A estimates as absolute
  setting values; only as covariates in extraction methods.
- **G3**: When closed-loop data is the only source, Stream A inferences
  need explicit "controller-confounded" label.
- **G4**: Reports must declare the stream of each finding and flag any
  Stream A → Stream B translation as REQUIRES CLINICAL VALIDATION.
- **G5**: Triage signals (Stream B) can use any layer of the pipeline as
  input without conflation risk because they don't claim biology.

---

## 7. What This Means for Pipeline Layers

| Layer | Stream | Counter-causal risk |
|-------|--------|---------------------|
| L0 raw observed ISF | B | None (operational measurement) |
| L1 state regime (EXP-2810) | B | None (BG-history proxy) |
| L2a canonical EGP (EXP-2820) | A | Intervention-subtraction conservative |
| L2b inverse EGP (EXP-2832) | A | Use ranking only, not absolute |
| L2c state EGP proxy (EXP-2823 H1) | A→B | Use as feature, not claim biology |
| L3 wear (EXP-2831) | B | Operational triage, no biology claim |
| L4 patient-mean residual | B | Operating-point ISF |

Layers L2 are the only Stream A elements; they must be labeled accordingly
and gated against direct setting use.

---

## 8. Open Stream A Questions (Now Bounded)

These can only be answered with one of:
- Out-of-sample data with intervention pauses (rare; ethical issues)
- Forward simulators / digital twins constructed independently
- Sensor-gap analysis (EXP-2809 used this approach — Stream A)

For Stream A questions like "what is true biological EGP?" the current
data provides a LOWER BOUND. Higher EGP estimates would require either
intervention pauses or external biological data (e.g., UVA/Padova
literature).

---

## 9. Open Stream B Questions (Unconstrained)

Stream B work can continue without conflation concern:
- Extract ISF/CR/basal as operational parameters from observed data
- Build triage signals from per-event deviations
- Recommend overrides based on detected patterns
- Compare per-controller performance

These don't need physics interpretation and can use any data layer.

---

## 10. Action Items

1. **Existing reports**: Update terminology in pipeline architecture
   diagrams to label Layer 2 as Stream A (physics inference) and
   Layers 0/1/3/4 as Stream B (operational extraction).
2. **EXP-2823 H2**: Reclassify finding as "not extractable from current
   closed-loop data" rather than "no within-patient EGP variation exists."
3. **EXP-2820 canonical EGP**: Re-label as "lower-bound biological EGP
   estimate, intervention-confounded."
4. **Future Stream A experiments**: Must declare counterfactual error
   band methodology in Methods section.
5. **Future Stream B experiments**: Must declare which Stream A inputs
   (if any) are used and with what gating (G2 compliance).

---

## Source Files

- `tools/cgmencode/exp_intervention_subtraction_2840.py`
- `externals/experiments/exp-2840_intervention_subtraction.json`
- `externals/experiments/exp-2840_intervention_burden.parquet`
- `externals/experiments/exp-2840_counterfactual_envelope.parquet`

## Predecessors

- `docs/60-research/state-and-egp-integration-report-2026-04-22.md`
- `docs/60-research/multitimescale-supply-demand-report-2026-04-22.md`
- `docs/60-research/cross-layer-interactions-report-2026-04-22.md`
