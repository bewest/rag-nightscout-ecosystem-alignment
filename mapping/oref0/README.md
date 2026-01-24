# oref0 Behavior Documentation

This directory contains detailed documentation of oref0 (the OpenAPS Reference Algorithm) as extracted from the source code (JavaScript/Node.js). This serves as the authoritative reference for understanding the algorithm that powers AAPS and forms the foundation of open-source AID systems.

## Source Repository

- **Repository**: [openaps/oref0](https://github.com/openaps/oref0)
- **Language**: JavaScript (Node.js)
- **Analysis Date**: 2026-01-16

## What is oref0?

oref0 is the open reference implementation of the OpenAPS algorithm. It is the core decision engine that:
- Calculates Insulin on Board (IOB) from pump history
- Detects carb absorption and calculates Carbs on Board (COB)
- Detects sensitivity changes (autosens)
- Generates blood glucose predictions
- Recommends temporary basal rates and Super Micro Boluses (SMB)

**Key Relationship**: AAPS is a Kotlin port of oref0. Understanding oref0 is essential for understanding AAPS behavior.

## Documentation Index

| Document | Description |
|----------|-------------|
| [algorithm.md](algorithm.md) | determine-basal decision logic, predictions, temp basal/SMB recommendations |
| [insulin-math.md](insulin-math.md) | IOB calculation, bilinear vs exponential curves, activity |
| [carb-math.md](carb-math.md) | COB detection, deviation analysis, min_5m_carbimpact |
| [autosens.md](autosens.md) | Sensitivity ratio calculation, deviation analysis |
| [safety.md](safety.md) | Safety guards, CGM noise handling, max limits |
| [data-models.md](data-models.md) | Profile, glucose_status, meal_data, iob_data structures |

## Key Source Files

| File | Location | Purpose |
|------|----------|---------|
| `determine-basal.js` | `lib/determine-basal/` | Main algorithm - temp basal and SMB decisions |
| `autosens.js` | `lib/determine-basal/` | Sensitivity detection algorithm |
| `cob.js` | `lib/determine-basal/` | Carb absorption detection |
| `calculate.js` | `lib/iob/` | IOB calculation (bilinear & exponential curves) |
| `total.js` | `lib/iob/` | IOB aggregation across all treatments |
| `history.js` | `lib/iob/` | Treatment history processing |
| `index.js` | `lib/profile/` | Profile assembly and lookup |
| `index.js` | `lib/meal/` | Meal data aggregation |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       oref0 Algorithm Flow                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Input Data                                                             │
│  ├── glucose_status (CGM readings, delta, noise)                       │
│  ├── iob_data[] (IOB array with future projections)                    │
│  ├── meal_data (COB, carbs, deviations, slopes)                        │
│  ├── profile (basal, ISF, CR, targets, safety limits)                  │
│  ├── autosens_data (sensitivity ratio)                                 │
│  └── currenttemp (currently running temp basal)                        │
│                                                                         │
│  ┌────────────────────┐                                                 │
│  │ Sensitivity Adjust │  Apply autosens ratio to basal, ISF, targets   │
│  └─────────┬──────────┘                                                 │
│            │                                                            │
│  ┌─────────▼──────────┐                                                 │
│  │ Calculate BGI      │  bgi = -activity * sens * 5                    │
│  │ (Blood Glucose     │  (expected BG change in 5 min from insulin)    │
│  │  Impact)           │                                                 │
│  └─────────┬──────────┘                                                 │
│            │                                                            │
│  ┌─────────▼──────────┐                                                 │
│  │ Calculate          │  deviation = (minDelta - bgi) * 6              │
│  │ Deviation          │  (30-min projected unexplained BG change)      │
│  └─────────┬──────────┘                                                 │
│            │                                                            │
│  ┌─────────▼──────────┐                                                 │
│  │ Calculate          │  naive_eventualBG = BG - (IOB * sens)          │
│  │ EventualBG         │  eventualBG = naive_eventualBG + deviation     │
│  └─────────┬──────────┘                                                 │
│            │                                                            │
│  ┌─────────▼──────────┐                                                 │
│  │ Generate 4         │  IOBpredBG[] - insulin only                    │
│  │ Prediction Curves  │  COBpredBG[] - with carb impact                │
│  │                    │  UAMpredBG[] - unannounced meals               │
│  │                    │  ZTpredBG[]  - zero temp (what-if)             │
│  └─────────┬──────────┘                                                 │
│            │                                                            │
│  ┌─────────▼──────────┐                                                 │
│  │ Determine Action   │  Temp Basal rate/duration                      │
│  │                    │  and/or SMB (microBolus)                       │
│  └────────────────────┘                                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Concepts

### Prediction Curves (predBGs)

oref0 generates four distinct prediction curves, each representing a different scenario:

| Curve | Name | Purpose |
|-------|------|---------|
| `IOB` | Insulin-Only | BG prediction based solely on insulin activity, used as baseline |
| `COB` | Carbs on Board | Includes expected carb absorption (linear decay) |
| `UAM` | Unannounced Meal | Handles unexplained rises, uses deviation slope |
| `ZT` | Zero Temp | "What-if" scenario with no more insulin, for safety checks |

### Super Micro Bolus (SMB)

SMB delivers small boluses (microboluses) to correct high BG more aggressively than temp basals alone. Key constraints:
- `maxSMBBasalMinutes` - limits SMB to X minutes worth of basal
- `maxUAMSMBBasalMinutes` - separate limit when IOB > COB (UAM mode)
- `SMBInterval` - minimum time between SMBs (default 3 minutes)
- BG must be above `threshold` to enable SMB

### Autosens

Automatic sensitivity detection that adjusts algorithm behavior:
- Analyzes 24h of deviations (actual vs expected BG change)
- Produces `sensitivityRatio` (e.g., 0.8 = 20% more sensitive)
- Adjusts basal rate, ISF, and optionally targets

## Cross-Project Relationships

| Aspect | oref0 | AAPS | Loop | Trio |
|--------|-------|------|------|------|
| Algorithm | Reference JS | Kotlin port | Custom Swift | oref0-based |
| SMB | Yes | Yes | Auto-bolus | Yes |
| UAM | Yes | Yes | No explicit | Yes |
| Autosens | Yes | Yes (or DynISF) | Retrospective Correction | Yes |
| IOB Curves | bilinear, rapid-acting, ultra-rapid | Same (ported) | Exponential only | Same |
| Prediction Curves | IOB, COB, UAM, ZT | Same | Single combined | Same |

## IOB Curve Origins

The exponential IOB curve in oref0 was sourced from Loop:

```javascript
// lib/iob/calculate.js line 125
// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
```

This is significant for cross-project alignment - both oref0 and Loop use the same underlying insulin activity model.

## Code Citation Format

Throughout this documentation, code references use the format:
```
oref0:lib/determine-basal/determine-basal.js#L123-L456
```

This maps to files in the `externals/oref0/` directory.

## Relevance to Alignment Goals

### GAP-SYNC-002 Resolution

oref0 outputs separate prediction arrays (`predBGs.IOB[]`, `predBGs.COB[]`, etc.) which are exactly what's needed for cross-project algorithm comparison. Loop currently only uploads the combined prediction.

### AAPS Validation

Since AAPS is a port of oref0, this documentation validates and cross-references the AAPS mapping. Any discrepancies indicate either:
1. Intentional AAPS modifications
2. Documentation gaps
3. Porting bugs to investigate
