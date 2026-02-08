# Effect Bundle Architecture Deep Dive

> **Domain**: AID Algorithms / Nightscout API
> **Last Updated**: 2026-02-08
> **Source**: T1Pal Mobile Workspace Architecture Documentation
> **Cross-Reference**: [T1Pal EFFECT-BUNDLE-NIGHTSCOUT-SPEC.md](../../../t1pal-mobile-workspace/docs/architecture/EFFECT-BUNDLE-NIGHTSCOUT-SPEC.md)

---

## Executive Summary

Effect Bundles represent a standardized mechanism for external agents to influence AID algorithm behavior through Nightscout as an interoperability hub. This architecture enables contextual adjustments (exercise, meals, menstrual cycles) without exposing sensitive personal data.

**Key Innovation**: Blackboard pattern where agents produce effects, Nightscout stores/validates, and AID controllers consume—with privacy tiers controlling what syncs.

---

## 1. Core Concepts

### 1.1 Effect Bundle Definition

An EffectBundle is a timestamped collection of algorithm adjustments produced by an agent:

```typescript
interface EffectBundle {
  identifier: string;              // UUID
  agentName: string;               // e.g., "BreakfastBoost", "ActivityMode"
  createdAt: Date;
  validFrom: Date;
  validUntil: Date;
  effects: Effect[];               // Array of typed effects
  metadata: {
    confidence: number;            // 0.0-1.0
    source: "onDevice" | "cloud";
    privacyTier: PrivacyTier;
  };
}
```

### 1.2 Effect Types

| Type | Purpose | Fields | Safety Bounds |
|------|---------|--------|---------------|
| **GlucoseEffect** | Predicted BG curve modification | `predictedDelta`, `startTime`, `duration` | ±50 mg/dL |
| **SensitivityEffect** | ISF/CR modulation | `sensitivityFactor`, `duration` | 0.2-2.0 multiplier |
| **AbsorptionEffect** | Carb absorption rate change | `absorptionMultiplier`, `duration` | 0.2-3.0 multiplier |

### 1.3 Privacy Tiers

| Tier | Description | Sync Behavior |
|------|-------------|---------------|
| `transparent` | All data syncs | Full bundle to Nightscout |
| `privacyPreserving` | Effects sync, context stays local | No reason/trigger fields |
| `configurable` | User chooses what syncs | Per-field sync settings |
| `onDeviceOnly` | Nothing syncs ever | Agent runs locally only |

---

## 2. Cross-Project Implementation Mapping

### 2.1 Loop Integration

| Effect Type | LoopKit Mapping | Implementation |
|-------------|-----------------|----------------|
| GlucoseEffect | `GlucoseEffect` struct | Prediction curve overlay |
| SensitivityEffect | `InsulinSensitivitySchedule` modulation | ISF multiplier |
| AbsorptionEffect | `CarbAbsorptionTime` modification | Per-entry adjustment |

**Key Files**:
- `Loop/Managers/LoopDataManager.swift` - Algorithm integration point
- `LoopKit/Models/GlucoseEffect.swift` - Native effect type
- `Loop/Managers/OverridePresetManager.swift` - Override inspiration

**Reconciliation Pattern**:
```swift
func mergeEffects(existing: [GlucoseEffect], external: EffectBundle) -> [GlucoseEffect] {
    let merged = existing.map { effect in
        if let external = external.glucoseEffect(at: effect.startDate) {
            let weight = min(external.confidence, 0.5) // Cap external influence
            let blended = effect.quantity.doubleValue * (1 - weight) +
                          (effect.quantity.doubleValue + external.delta) * weight
            return GlucoseEffect(startDate: effect.startDate, quantity: .init(unit: .milligramsPerDeciliter, doubleValue: blended))
        }
        return effect
    }
    return merged
}
```

### 2.2 AAPS/OpenAPS Integration

| Effect Type | oref1 Field | Injection Point |
|-------------|-------------|-----------------|
| GlucoseEffect | `bg_predictions` array | determine-basal.js |
| SensitivityEffect | `sens_ratio` | autosens-ratio merge |
| AbsorptionEffect | `carb_absorption_rate` | meal.js |

**Key Files**:
- `oref0/lib/determine-basal/determine-basal.js` - Main algorithm
- `oref0/lib/meal/total.js` - Carb absorption
- `AndroidAPS/app/src/main/kotlin/app/aaps/core/main/iob/GlucoseStatus.kt` - AAPS glucose status

**Effect Injection (JavaScript)**:
```javascript
// effects.js - new module for oref0
function applyEffects(effects, glucose_status, profile) {
    effects.forEach(effect => {
        switch (effect.type) {
            case 'sensitivity':
                profile.sens = profile.sens / effect.sensitivityFactor;
                profile.carb_ratio = profile.carb_ratio / effect.sensitivityFactor;
                break;
            case 'glucose':
                glucose_status.delta += effect.predictedDelta * effect.confidence;
                break;
            case 'absorption':
                profile.carb_absorption_rate *= effect.absorptionMultiplier;
                break;
        }
    });
    return { glucose_status, profile };
}
```

### 2.3 Trio Integration

| Effect Type | OpenAPSSwift Type | Implementation |
|-------------|-------------------|----------------|
| GlucoseEffect | Generator protocol | Prediction curve contribution |
| SensitivityEffect | SensitivityRatio | Dynamic ISF modulation |
| AbsorptionEffect | CarbAbsorptionModel | Rate adjustment |

**Key Files**:
- `Trio/OpenAPS/Predict/Glucose/GlucosePredictor.swift` - Prediction engine
- `Trio/Managers/NightscoutManager.swift` - Nightscout integration
- `Trio/OpenAPS/SensitivityResult.swift` - Sensitivity calculation

**Native Advantage**: Trio's native Nightscout integration simplifies effect sync compared to Loop's optional integration.

---

## 3. Nightscout API Extension

### 3.1 Proposed Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v3/effectbundles` | Create effect bundle |
| GET | `/api/v3/effectbundles?valid={now}` | Active bundles |
| GET | `/api/v3/effectbundles/{identifier}` | Single bundle |
| DELETE | `/api/v3/effectbundles/{identifier}` | Revoke bundle |

### 3.2 JSON Schema

```yaml
apiVersion: nightscout.dev/v1
kind: EffectBundle
metadata:
  identifier: "550e8400-e29b-41d4-a716-446655440000"
  agentName: "ActivityMode"
  createdAt: "2026-02-08T10:00:00Z"
spec:
  validFrom: "2026-02-08T10:00:00Z"
  validUntil: "2026-02-08T12:00:00Z"
  effects:
    - type: sensitivity
      sensitivityFactor: 1.3
      confidence: 0.8
    - type: glucose
      predictedDelta: -15
      confidence: 0.7
  metadata:
    source: onDevice
    privacyTier: privacyPreserving
```

### 3.3 Validation Rules

1. **Time Bounds**: `validUntil` must be ≤ 24 hours from `createdAt`
2. **Confidence**: Must be 0.0-1.0 inclusive
3. **Safety Bounds**: Effects must respect type-specific limits
4. **Agent Registration**: `agentName` should match registered agent

---

## 4. Data Three-Tier Model

### 4.1 Personal Context (Never Syncs)

Data that stays on-device regardless of settings:
- Menstrual cycle phase
- Heart rate variability
- Stress indicators
- Sleep quality metrics

### 4.2 Effect Metrics (Syncs by Default)

Algorithm-relevant data that enables interoperability:
- Glucose prediction curves
- Sensitivity multipliers
- Confidence scores
- Validity windows

### 4.3 Reason Field (User-Controlled)

Explanatory data with configurable sync:
- "Morning exercise session"
- "Large breakfast"
- "Stress from work"

---

## 5. Agent Examples

### 5.1 BreakfastBoost Agent

**Privacy Tier**: `transparent`

**Trigger**: Morning meal detection (CGM rise pattern)

**Effects**:
- SensitivityEffect: 0.8 factor (more sensitive → more insulin)
- AbsorptionEffect: 1.5 multiplier (faster absorption)

### 5.2 ActivityMode Agent

**Privacy Tier**: `privacyPreserving`

**Trigger**: Exercise detection (accelerometer, heart rate)

**Effects**:
- GlucoseEffect: -30 mg/dL predicted drop
- SensitivityEffect: 1.5 factor (less sensitive during activity)
- Post-exercise: 0.7 sensitivity for 2 hours

### 5.3 MenstrualCycle Agent

**Privacy Tier**: `onDeviceOnly`

**Trigger**: Cycle phase from Apple Health or manual entry

**Effects**:
- SensitivityEffect: 0.85-1.15 factor based on phase
- No sync—effects apply locally only

---

## 6. Reconciliation Strategy

### 6.1 Confidence-Weighted Averaging

When multiple effects overlap:

```
Final = Σ(value × confidence) / Σ(confidence)
```

### 6.2 Conservative Blending

External effects limited to 50% maximum influence:

```
blendedValue = algorithmValue × (1 - weight) + 
               (algorithmValue + externalEffect) × weight
where weight = min(confidence, 0.5)
```

### 6.3 Safety Override

Algorithm can reject effects outside safety bounds:
- Sensitivity: 0.2-2.0 (reject if outside)
- Glucose: ±50 mg/dL (cap if exceeded)
- Absorption: 0.2-3.0 (reject if outside)

---

## 7. Related Documentation

### T1Pal Architecture Docs

| Document | Focus |
|----------|-------|
| EFFECT-BUNDLE-NIGHTSCOUT-SPEC.md | Community specification |
| LOOP-EFFECT-INTEGRATION.md | Loop/LoopKit pathway |
| AAPS-EFFECT-INTEGRATION.md | AAPS/OpenAPS pathway |
| TRIO-EFFECT-INTEGRATION.md | Trio/iAPS pathway |
| EFFECT-BUNDLE-PRIVACY-MODEL.md | Privacy tiers detail |
| AGENT-PRIVACY-GUARANTEES.md | 6 core privacy guarantees |

### Proposals

| File | Status |
|------|--------|
| docs/proposals/README.md | Overview |
| docs/proposals/effect-bundle-crd.yaml | CRD definition |
| docs/proposals/effect-bundle-schema.json | JSON Schema |

---

## 8. Gap Analysis

Effects from this analysis:

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-EFFECT-001 | No standard effect format across AID systems | Each implements proprietary override/preset |
| GAP-EFFECT-002 | Privacy tier not defined in existing APIs | Personal context risks leaking |
| GAP-EFFECT-003 | No agent registration mechanism | Rogue effects possible |
| GAP-EFFECT-004 | Reconciliation undefined when multiple agents | Conflicting effects unresolved |
| GAP-EFFECT-005 | No Nightscout collection for effects | No cloud sync path |

---

## 9. Requirements Analysis

| Req ID | Requirement |
|--------|-------------|
| REQ-EFFECT-001 | Effect bundles MUST include validity window |
| REQ-EFFECT-002 | Privacy tiers MUST prevent personal context sync |
| REQ-EFFECT-003 | Effects MUST be bounded by safety limits |
| REQ-EFFECT-004 | Agents SHOULD declare privacy tier |
| REQ-EFFECT-005 | Reconciliation MUST cap external influence at 50% |

---

*Last Updated: 2026-02-08 by ecosystem-alignment automation*
