# Loop Behavior Documentation

This directory contains detailed documentation of Loop's actual behavior as extracted from the LoopWorkspace source code (Swift/iOS). This serves as the authoritative reference for aligning Loop with Nightscout and other AID systems.

## Source Repository

- **Repository**: [LoopKit/LoopWorkspace](https://github.com/LoopKit/LoopWorkspace)
- **Language**: Swift (iOS)
- **Analysis Date**: 2026-01-16

## Documentation Index

| Document | Description |
|----------|-------------|
| [algorithm.md](algorithm.md) | Prediction algorithm, effect composition, momentum blending |
| [insulin-math.md](insulin-math.md) | IOB calculation, dose reconciliation, insulin models |
| [carb-math.md](carb-math.md) | COB calculation, absorption models, dynamic adaptation |
| [dose-math.md](dose-math.md) | Correction logic, temp basal/bolus recommendations |
| [overrides.md](overrides.md) | Override lifecycle, supersession, presets |
| [nightscout-sync.md](nightscout-sync.md) | Upload mappings, remote commands, field translations |
| [safety.md](safety.md) | Guardrails, limits, suspend thresholds |
| [quirks.md](quirks.md) | Edge cases, timing behaviors, gotchas |
| [data-models.md](data-models.md) | Core data structures and their fields |

## Key Source Files

| File | Location | Purpose |
|------|----------|---------|
| `LoopAlgorithm.swift` | `LoopKit/LoopKit/LoopAlgorithm/` | Main prediction algorithm |
| `LoopMath.swift` | `LoopKit/LoopKit/` | Effect composition, momentum blending |
| `InsulinMath.swift` | `LoopKit/LoopKit/InsulinKit/` | IOB calculation, dose glucose effects |
| `CarbMath.swift` | `LoopKit/LoopKit/CarbKit/` | COB calculation, absorption models |
| `DoseMath.swift` | `LoopKit/LoopKit/LoopAlgorithm/` | Correction and dosing logic |
| `DoseEntry.swift` | `LoopKit/LoopKit/InsulinKit/` | Dose data model |
| `TemporaryScheduleOverride.swift` | `LoopKit/LoopKit/` | Override data model |
| `TemporaryScheduleOverrideHistory.swift` | `LoopKit/LoopKit/` | Override lifecycle management |
| `IntegralRetrospectiveCorrection.swift` | `LoopKit/LoopKit/RetrospectiveCorrection/` | IRC algorithm |
| `GlucoseMath.swift` | `LoopKit/LoopKit/GlucoseKit/` | Momentum, counteraction effects |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Loop Algorithm Flow                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Input Data                                                         │
│  ├── Glucose History (CGM readings)                                │
│  ├── Dose History (boluses, temp basals, suspends)                 │
│  ├── Carb Entries (with absorption times)                          │
│  └── Settings (basal, ISF, CR, targets)                            │
│                                                                     │
│  ┌─────────────────┐                                                │
│  │ Insulin Effects │  doses.glucoseEffects(sensitivity, model)     │
│  └────────┬────────┘                                                │
│           │                                                         │
│  ┌────────▼────────┐                                                │
│  │ Counteraction   │  glucose.counteractionEffects(insulinEffects) │
│  │ Effects (ICE)   │                                                │
│  └────────┬────────┘                                                │
│           │                                                         │
│  ┌────────▼────────┐                                                │
│  │ Carb Effects    │  carbs.dynamicGlucoseEffects(ice, settings)   │
│  │ (Dynamic)       │                                                │
│  └────────┬────────┘                                                │
│           │                                                         │
│  ┌────────▼────────┐                                                │
│  │ Retrospective   │  ice.subtracting(carbEffects)                 │
│  │ Correction      │  → RC effect                                  │
│  └────────┬────────┘                                                │
│           │                                                         │
│  ┌────────▼────────┐                                                │
│  │ Momentum        │  linearRegression on recent glucose           │
│  └────────┬────────┘                                                │
│           │                                                         │
│  ┌────────▼────────┐                                                │
│  │ Predict Glucose │  LoopMath.predictGlucose(                     │
│  │                 │    starting, momentum, [insulin, carbs, rc])  │
│  └────────┬────────┘                                                │
│           │                                                         │
│  ┌────────▼────────┐                                                │
│  │ Dose            │  prediction.recommendedTempBasal() or         │
│  │ Recommendation  │  prediction.recommendedAutomaticDose()        │
│  └─────────────────┘                                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Differences from Other Systems

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| Algorithm | Custom prediction-based | oref0/oref1 |
| Automatic Boluses | Yes (microboluses via `AutomaticDoseRecommendation.bolusUnits`) | SMB (Super Micro Bolus) |
| UAM Detection | No explicit UAM | Yes (Unannounced Meal detection) |
| Sensitivity Adaptation | Retrospective Correction (integral or standard) | Autosens |
| Carb Absorption | PiecewiseLinear (dynamic, adaptive) | Linear decay (static) |
| Retrospective Correction | Integral (PID-like) or Standard | N/A (uses autosens) |
| Momentum | Linear regression blended into effects | Separate in prediction |

**Note**: Loop supports automatic boluses (microboluses) similar in concept to SMB, delivered via `AutomaticDoseRecommendation`. See [dose-math.md](dose-math.md) for details.

## Code Citation Format

Throughout this documentation, code references use the format:
```
loop:Path/To/File.swift#L123-L456
```

This maps to files in the `externals/LoopWorkspace/` directory.
