# Metabolic System Visualization Toolkit

**Date**: 2026-04-22
**Audience**: Patients, clinicians, AID developers
**Purpose**: Make the diabetes/AID dynamic legible — pair physiology
(what the body demands) with controller response (what the AID does) at
multiple timescales.

## Design Philosophy (Charter-Aligned)

Every chart in this toolkit follows the two-stream charter:
- **Stream B (operational)** elements are colored boldly and labeled as
  observable: actual basal delivery, BG, IOB, COB, state, transitions.
- **Stream A (physics inference)** elements — when shown — are explicitly
  labeled as estimates with caveats. We do NOT show "biological EGP" as
  a number; we show the demand the controller is compensating for.

This avoids the conflation modes documented in the
[Two-Stream Methodology Charter](two-stream-methodology-charter-2026-04-22.md):
patients/clinicians won't be tempted to "match the profile to biology"
because biology is never quoted as an absolute number.

## Five Diagnostic Chart Types

### 1. Week Envelope (`{patient}_week_envelope.png`)

7-day strip with 3 panels:
- **BG with state shading** — orange shading = elevated 48h state (S1),
  green = baseline (S0). Discussion question: "When does the patient enter
  S1, and how long until they recover?"
- **Profile vs Controller delivery** — gray line = scheduled (profile),
  blue line = actual (controller-delivered). The *gap* is the
  envelope demand the static profile misses.
- **IOB / COB envelope** — physiological state of insulin and carbs in
  the system, helps identify dosing patterns.

**Clinical use**: Audition opportunity. If actual basal is consistently
above scheduled in S1 windows, propose a temporary basal increase
override during S1 detection. If consistently below, propose a profile
reduction.

### 2. Meal Event (`{patient}_meal_event.png`)

6-hour window around a representative meal:
- **BG trajectory** through the event
- **Controller insulin response**: basal modulation, manual bolus, SMBs
- **Supply/Demand** envelope: carbs entering bloodstream (COB) vs
  insulin active (IOB)

**Clinical use**: Discuss meal handling — was the bolus adequate? Did
the controller add enough SMB? Is the COB curve compatible with the
declared carb count? Can identify under-bolus, over-bolus, or absorption
mismatches.

### 3. Profile Audit (`{patient}_profile_audit.png`)

Two panels:
- **Hourly basal**: scheduled (dashed black) vs actual delivery in S0
  (green) and S1 (red). Shows the time-of-day shape of the demand
  the profile is missing.
- **State envelope shift bar**: scheduled vs S0 actual vs S1 actual.
  The labeled `±X%` shift directly suggests audition magnitude.

**Clinical use**: Direct profile recommendation tool. If the S1 actual
bar is 20% above scheduled at hour 3-7am, propose a dawn-phenomenon
basal increase. If the S0 actual bar is 30% below scheduled, the
profile is over-basaling and contributing to hypos.

### 4. Recovery Diagnostic (`{patient}_recovery_diagnostic.png`)

For patients with multiple S0→S1 transitions:
- **TIR scatter** before vs after transition (deterioration if below
  diagonal)
- **Recovery histogram** — patient's own self-recovery rate vs the
  cohort distribution (red line = patient, gray = cohort)

**Clinical use**: Identify if patient is a poor self-recoverer. EXP-2812
showed Loop patients have 0% median recovery; if a patient is far below
cohort median, consider override-on-detection workflow as triage.

### 5. Site-Age Trajectory (`{patient}_site_age.png`)

When `cage_hours` (cannula age) data is available:
- **Basal demand** by cannula age bin
- **BG control** (mean ± std) by cannula age bin

**Clinical use**: Identify site degradation. Rising basal demand and
worsening BG control after day 3-4 suggests shorter site rotation
intervals. Cross-references with EXP-2831 wear-degradation flags.

---

## Example Patients (Generated in this Toolkit)

### Patient `b` (Loop, BOTH triage flags from EXP-2842)

- Week envelope shows persistent S1 with very low basal floor (~0.2 U/hr)
- Recovery diagnostic shows recovery fraction 0.00 (cohort median 0.18)
- Site age shows clear cannula degradation (basal demand rises with age)
- **Recommendation**: This patient is the highest-confidence triage case.
  Trial shorter cannula change interval AND audition override during
  S1 detection.

### Patient `c` (Loop, +69% basal shift between states)

- Profile audit shows S1 actual basal is 0.33 U/hr vs scheduled 0.20 U/hr
- Hourly profile shape suggests dawn period under-basaled
- **Recommendation**: Propose 30-50% basal increase during S1 windows
  or a temp basal scheduled at known high-burden times.

### Patient `ns-8f3527d1ee40` (Trio, −61% basal shift between states)

- Profile audit shows S1 actual basal LOWER than S0 actual
- This is the OPPOSITE phenotype from patient `c` — when patient enters
  elevated state, controller reduces basal (likely SMB-heavy correction
  strategy)
- **Recommendation**: Different audition — check if SMB dosing is
  appropriate; profile may be over-basaled at baseline.

---

## How to Generate Charts for a New Patient

```bash
# Edit the example_patients list in the script:
vim tools/cgmencode/viz_metabolic_diagnostic.py
# or import and use programmatically:
python -c "
from tools.cgmencode.viz_metabolic_diagnostic import (
    chart_week_envelope, chart_meal_event, chart_profile_audit,
    chart_recovery_diagnostic, chart_site_age
)
chart_week_envelope('your_patient_id')
chart_meal_event('your_patient_id')
# ...
"
```

Charts are saved to `docs/60-research/figures/{patient_id}_{type}.png`.

---

## Charter Compliance

| Element | Stream | Risk | Mitigation |
|---------|--------|------|------------|
| BG, basal, bolus, IOB, COB | Observed (B) | None | Direct measurement |
| State regime (S0/S1) | B | None | Operational classification |
| "Profile vs actual" gap | B | None | Two observed quantities |
| Recovery fraction | B | None | Operational metric |
| **No quantitative biology** | A | N/A | Not shown |

The charts intentionally avoid:
- Quoting biological EGP as mg/dL/hr (would be a Stream A absolute claim)
- Recommending profile values to "match" inferred biology
- Inferring sensitivity from closed-loop drops without subtraction caveats

## Limitations & Future Work

- Currently single-patient charts; cohort comparisons would require
  separate aggregate views
- No interactive version (matplotlib PNGs); a clinician dashboard would
  benefit from web-based interactivity (Plotly/Dash/Streamlit)
- Insulin activity curve overlays not yet shown but valuable
- Carb absorption modeled vs declared not yet shown
- No time-of-day correlation with state transitions (would help dawn-vs-eve
  pattern detection)

## Source Files

- `tools/cgmencode/viz_metabolic_diagnostic.py` — generator script
- `docs/60-research/figures/{patient}_*.png` — 14 example charts
- `docs/60-research/figures/manifest.json` — generated chart inventory

## Predecessors

- `docs/60-research/two-stream-methodology-charter-2026-04-22.md`
- `docs/60-research/state-transition-audition-report-2026-04-22.md`
- `docs/60-research/envelope-vs-cell-level-reconciliation-2026-04-22.md`
