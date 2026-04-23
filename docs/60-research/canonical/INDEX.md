# Canonical Research Narratives

Condensed, figure-anchored narratives that replace the ~349-report
`docs/60-research/` front-door as the primary reading path. Original
reports are retained for methodology and audit; this index maps each
to its canonical home.

## Narratives

| # | Narrative | Status | Figures | Script |
|---|---|---|---|---|
| 01 | [Physics of a correction](01-physics-of-a-correction.md) | canonical 2026-04-22 | 4 | `tools/cgmencode/condensed/correction_amplitude.py` |
| 02 | [Closed-loop masking & identifiability](02-masking-and-identifiability.md) | canonical 2026-04-22 | 4 | `tools/cgmencode/condensed/masking_identifiability.py` |
| 03 | [AID controller signatures](03-aid-controller-signatures.md) | canonical 2026-04-22 | 4 | `tools/cgmencode/condensed/controller_signatures.py` |
| 04 | [Metabolic memory & state structure](04-metabolic-memory-and-state.md) | canonical 2026-04-22 | 4 | `tools/cgmencode/condensed/memory_and_state.py` |
| 05 | Settings extraction in production (optional) | planned | — | — |

## Retired-EXP → canonical narrative pointer

(Partial; populated as narratives land. Use this as the first lookup
before re-reading a standalone EXP report.)

| EXP | Topic | Canonical home |
|-----|-------|----------------|
| 2624 | Three-phase correction lag | [01 §F1](01-physics-of-a-correction.md#f1--the-three-phase-correction-amplitude-resolved) |
| 2626 | Advisory asymmetry / safety guardrails | [01 §F1](01-physics-of-a-correction.md#why-this-is-controller-confounded) |
| 2634/2635 | Single-factor recovery model failures | [01 §F1](01-physics-of-a-correction.md#related-observational-constraints) |
| 2636 | Dose-dependent ISF | [01 §F2](01-physics-of-a-correction.md#f2--apparent-isf-compresses-logarithmically-with-dose) |
| 2640 | Per-patient dose-dependent ISF | [01 §F2](01-physics-of-a-correction.md#f2--apparent-isf-compresses-logarithmically-with-dose) |
| 2641/2642 | Descriptive-prescriptive paradox | [01 §F1](01-physics-of-a-correction.md#related-observational-constraints) · later in 02 |
| 2656 | SC→hepatic EGP suppression ceiling | [01 §F4](01-physics-of-a-correction.md#f4--sc-suppression-has-a-hard-ceiling) |
| 2681 | BG drop saturation model | [01 §F3](01-physics-of-a-correction.md#f3--bg-drop-saturates) |
| 2875 | Counter-regulation detection | [01 §F3](01-physics-of-a-correction.md#the-floor-plainly) |
| 2622 | Advisory convergence / days-to-stable | [02 §F4](02-masking-and-identifiability.md) · [04 retired](04-metabolic-memory-and-state.md) |
| 2627 | Carb memory window sweep | [04 §F1](04-metabolic-memory-and-state.md#f1--carb-memory-extends-to-48-h) |
| 2685 | Controller delivery strategy | [03 §F2](03-aid-controller-signatures.md#f2--three-delivery-strategies-not-one) |
| 2687/2689 | Observational-causal failures | [02](02-masking-and-identifiability.md) |
| 2695 | PSM ATT decay | [02 §F2](02-masking-and-identifiability.md) |
| 2696 | Impulse-response / Granger | [02](02-masking-and-identifiability.md) · [04](04-metabolic-memory-and-state.md) |
| 2697 | Variance decomposition | [04 §F4](04-metabolic-memory-and-state.md#f4--84--of-bolus-response-variance-is-within-day) |
| 2790 | Insulin accounting | [03 §F2](03-aid-controller-signatures.md#f2--three-delivery-strategies-not-one) |
| 2810 | Two-state clustering | [04 §F2](04-metabolic-memory-and-state.md#f2--two-metabolic-states-85--sticky) |
| 2811 | ISF / basal decoupling by state | [04 §F3](04-metabolic-memory-and-state.md#f3--single-global-isfbasal-numbers-are-lossy--parameters-are-state-dependent) |
| 2812 | State-transition audition / recovery | [03 §F3](03-aid-controller-signatures.md#f3--recovery-asymmetry-after-a-well-controlled--moderate-high-transition) |
| 2840/2841 | Two-stream charter / trajectory-steering | [02](02-masking-and-identifiability.md) |
| 2859–2864 | Bootstrap-gated fact survival | [02 §F4](02-masking-and-identifiability.md) · [03](03-aid-controller-signatures.md) |
| 2866–2869 | Carb-event data quality | [02](02-masking-and-identifiability.md) |
| 2870 | Envelope crossover phenotype | [03 §F4](03-aid-controller-signatures.md#f4--simpsons-reversal--most-of-the-phenotypetir-signal-is-controller-composition) |
| 2871 | Suspension polarity | [03 §F1](03-aid-controller-signatures.md#f1--suspension-polarity-is-inverted-across-controllers) |
| 2872 | Simpson's paradox check | [03 §F4](03-aid-controller-signatures.md#f4--simpsons-reversal--most-of-the-phenotypetir-signal-is-controller-composition) |
| 2874 | Meal-gated envelope re-run | [03 §F1](03-aid-controller-signatures.md#f1--suspension-polarity-is-inverted-across-controllers) |

## Conventions

- Each narrative owns a figure pack in `visualizations/canonical/NN/`.
- Each figure is produced by a deterministic script under
  `tools/cgmencode/condensed/`. No random seeds, no arguments.
- Claims not backed by a figure are cited to a retired EXP file in the
  same paragraph.
- Two-stream discipline (Stream A physics vs Stream B settings) applies
  uniformly — narratives explicitly state which stream a finding
  belongs to when the distinction is non-obvious.
