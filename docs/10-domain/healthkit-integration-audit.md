# HealthKit Integration Audit

> **Date**: 2026-01-31  
> **Status**: Complete  
> **Source**: ios-mobile-platform.md #8  
> **Related**: GAP-WATCH-004 (shared components)

---

## Executive Summary

This audit documents HealthKit usage across the Nightscout iOS ecosystem, identifying which apps read/write data, what HKQuantityTypes are used, and potential conflicts when multiple apps operate simultaneously.

### App Summary

| App | Writes | Reads | Primary Purpose |
|-----|--------|-------|-----------------|
| **Loop** | ✅ Glucose, Carbs, Insulin | ✅ Background delivery | AID controller |
| **Trio** | ✅ Glucose, Carbs, Insulin, Fat, Protein | ✅ Background delivery | AID controller |
| **xDrip4iOS** | ✅ Glucose only | ❌ | CGM companion |
| **DiaBLE** | ✅ Glucose, Carbs, Insulin | ✅ | CGM reader |
| **Nightguard** | ✅ Glucose only | ❌ | Follower/alarm |
| **LoopCaregiver** | ❌ | ✅ (unit conversion) | Caregiver follower |
| **LoopFollow** | ❌ | ❌ | Follower/alarm |

### Critical Conflict Risk

**⚠️ HIGH RISK**: Multiple apps writing glucose to HealthKit simultaneously will create duplicate readings.

---

## 1. HealthKit Data Types Used

### HKQuantityTypeIdentifier Summary

| Data Type | Loop | Trio | xDrip4iOS | DiaBLE | Nightguard |
|-----------|------|------|-----------|--------|------------|
| `.bloodGlucose` | ✅ Write | ✅ Write | ✅ Write | ✅ Write | ✅ Write |
| `.insulinDelivery` | ✅ Write | ✅ Write | ❌ | ✅ Write | ❌ |
| `.dietaryCarbohydrates` | ✅ Write | ✅ Write | ❌ | ✅ Write | ❌ |
| `.dietaryFatTotal` | ❌ | ✅ Write | ❌ | ❌ | ❌ |
| `.dietaryProtein` | ❌ | ✅ Write | ❌ | ❌ | ❌ |
| `.bloodPressureSystolic` | ❌ | ❌ | ❌ | ✅ Write | ❌ |
| `.bloodPressureDiastolic` | ❌ | ❌ | ❌ | ✅ Write | ❌ |

### Code References

#### Loop/LoopKit

```swift
// LoopKit/LoopKit/HealthKitSampleStore.swift:63-65
public static let carbType = HKQuantityType.quantityType(forIdentifier: .dietaryCarbohydrates)!
public static let glucoseType = HKQuantityType.quantityType(forIdentifier: .bloodGlucose)!
public static let insulinQuantityType = HKQuantityType.quantityType(forIdentifier: .insulinDelivery)!
```

#### Trio

```swift
// Trio/Sources/Services/HealthKit/HealthKitManager.swift:39-43
static let healthBGObject = HKObjectType.quantityType(forIdentifier: .bloodGlucose)
static let healthCarbObject = HKObjectType.quantityType(forIdentifier: .dietaryCarbohydrates)
static let healthFatObject = HKObjectType.quantityType(forIdentifier: .dietaryFatTotal)
static let healthProteinObject = HKObjectType.quantityType(forIdentifier: .dietaryProtein)
static let healthInsulinObject = HKObjectType.quantityType(forIdentifier: .insulinDelivery)
```

#### xDrip4iOS

```swift
// xdrip/Managers/HealthKit/HealthKitManager.swift:76
bloodGlucoseType = HKObjectType.quantityType(forIdentifier: .bloodGlucose)
```

#### DiaBLE

```swift
// DiaBLE/Health.swift:27-31
case .glucose:   HKQuantityType(.bloodGlucose)
case .insulin:   HKQuantityType(.insulinDelivery)
case .carbs:     HKQuantityType(.dietaryCarbohydrates)
case .systolic:  HKQuantityType(.bloodPressureSystolic)
case .diastolic: HKQuantityType(.bloodPressureDiastolic)
```

#### Nightguard

```swift
// nightguard/external/AppleHealthService.swift:59-63
HKQuantitySample(
    type: getHkQuantityType(),  // .bloodGlucose
    quantity: HKQuantity(unit: unit, doubleValue: value),
    start: date, end: date
)
```

---

## 2. Write Patterns

### 2.1 Loop (via LoopKit)

**Architecture**: `HealthKitSampleStore` base class with specialized stores.

```
GlucoseStore → HealthKitSampleStore → HKHealthStore
CarbStore → HealthKitSampleStore → HKHealthStore  
DoseStore → HKHealthStore (insulin)
```

**Write Triggers**:
- New CGM reading received
- Carb entry added/modified
- Insulin delivered by pump

**Deduplication**: Uses `syncIdentifier` in sample metadata to prevent duplicates.

**Source**: `LoopKit/LoopKit/GlucoseKit/GlucoseStore.swift:427-472`

### 2.2 Trio

**Architecture**: `BaseHealthKitManager` with Combine publishers.

```
CoreData → Combine Publisher → HealthKitManager → HKHealthStore
```

**Write Functions**:
```swift
// HealthKitManager.swift
func uploadGlucose() async
func uploadCarbs() async
func uploadInsulin() async
```

**Metadata Key**: `"Trio Insulin Type"` for insulin categorization.

**Deduplication**: Uses `syncID` for delete operations.

**Source**: `Trio/Sources/Services/HealthKit/HealthKitManager.swift:20-30`

### 2.3 xDrip4iOS

**Architecture**: Simple manager with UserDefaults settings.

**Write Trigger**: New BgReading from CGM.

**Settings**:
- `storeReadingsInHealthkit` - Enable/disable
- `storeReadingsInHealthkitAuthorized` - Auth status

**Source**: `xdrip/Managers/HealthKit/HealthKitManager.swift:40-58`

### 2.4 DiaBLE

**Architecture**: Async/await based `HealthKit` class.

**Write Functions**:
```swift
func write(_ glucoseData: [Glucose]) async
```

**Source**: `DiaBLE/Health.swift:80`

### 2.5 Nightguard

**Architecture**: Singleton service with backfill capability.

**Write Pattern**: Batch save with timestamp tracking.

```swift
// AppleHealthService.swift:73
healthKitStore.save(hkQuantitySamples) { (success, error) in ... }
```

**Backfill**: Up to 10,000 readings from Nightscout.

**Source**: `nightguard/external/AppleHealthService.swift:45-78`

---

## 3. Read Patterns

### 3.1 Loop (Background Delivery)

**Uses**: `HKObserverQuery` with background delivery for glucose updates.

```swift
// LoopKit/LoopKit/HealthKitSampleStore.swift:17
func enableBackgroundDelivery(for type: HKObjectType, frequency: HKUpdateFrequency) async throws
```

**Purpose**: React to external CGM apps writing glucose.

### 3.2 Trio

**Uses**: Similar to Loop via LoopKit dependency.

**Reads**: Glucose from external CGM apps.

### 3.3 LoopCaregiver

**Uses**: `HKUnit` for unit conversion only.

```swift
// LoopCaregiverKit/Models/Extensions/HKUnit.swift
```

**No direct reads** - uses Nightscout API for data.

---

## 4. Conflict Scenarios

### 4.1 Duplicate Glucose Writes

**Scenario**: User runs xDrip4iOS + Loop simultaneously.

| Time | xDrip4iOS | Loop | HealthKit Result |
|------|-----------|------|------------------|
| 14:00 | Write 120 mg/dL | Write 120 mg/dL | 2 samples at 14:00 |
| 14:05 | Write 125 mg/dL | Write 125 mg/dL | 2 samples at 14:05 |

**Impact**: Duplicate readings in Apple Health, incorrect averages.

**Mitigation**:
- Only enable HealthKit write in ONE app
- Loop reads from HealthKit, doesn't need to write if xDrip4iOS writes
- Use `syncIdentifier` metadata for cross-app dedup

### 4.2 Conflicting Insulin Writes

**Scenario**: User switches from Loop to Trio.

**Risk**: Historical insulin data from both apps may coexist.

**Mitigation**: 
- Different metadata keys (`Trio Insulin Type` vs Loop's metadata)
- Apple Health UI shows source app per sample

### 4.3 Carb Entry Conflicts

**Scenario**: User enters carbs in both Trio and DiaBLE.

**Risk**: Double carb entries affect algorithm calculations.

**Mitigation**:
- Enter carbs in ONE app only
- Use Nightscout as source of truth for carbs

---

## 5. Best Practices

### For Users

| Scenario | Recommendation |
|----------|----------------|
| Loop + xDrip4iOS | Disable HealthKit write in xDrip4iOS (Loop reads HK) |
| Trio standalone | Enable all Trio HealthKit writes |
| Nightguard only | Enable HealthKit write (only app) |
| Multiple AID apps | ⚠️ NOT SUPPORTED - use only one |

### For Developers

| Practice | Description |
|----------|-------------|
| **Use syncIdentifier** | Include unique ID in sample metadata |
| **Check before write** | Query existing samples at timestamp |
| **Prefer reading** | Read from HealthKit rather than duplicate CGM code |
| **Document source** | Add `HKSource` metadata for attribution |

---

## 6. Gap Analysis

### GAP-HK-001: No Cross-App Deduplication

**Description**: Each app writes independently without checking for existing samples from other apps.

**Affected Systems**: Loop, Trio, xDrip4iOS, DiaBLE, Nightguard

**Evidence**:
- Loop uses `syncIdentifier` but only checks its own samples
- xDrip4iOS writes without cross-app checks
- Nightguard has `lastSyncDate` but per-app only

**Impact**: Duplicate glucose readings when multiple apps enabled.

**Remediation**:
1. Before writing, query existing samples at same timestamp
2. Check sample source/metadata before writing
3. Standardize `syncIdentifier` format across apps

### GAP-HK-002: No User Guidance on Multi-App Conflicts

**Description**: None of the apps warn users about HealthKit conflicts when other apps are detected.

**Affected Systems**: All iOS apps with HealthKit write

**Impact**: Users unknowingly create duplicates.

**Remediation**:
1. Query HKSource at startup to detect other apps
2. Warn user if multiple CGM apps write to HealthKit
3. Provide recommendation in settings UI

### GAP-HK-003: Inconsistent Metadata Keys

**Description**: Each app uses different metadata schemes, preventing cross-app coordination.

**Affected Systems**: Loop, Trio, DiaBLE

**Evidence**:
- Trio: `"Trio Insulin Type"`
- Loop: syncIdentifier format differs
- DiaBLE: No standardized keys

**Impact**: Cannot identify sample source programmatically.

**Remediation**: Standardize metadata key format, e.g., `"app.nightscout.syncId"`

---

## 7. Recommendations

### Short-term

1. **Document user guidance** - Add wiki page on HealthKit configuration
2. **Single-writer principle** - Recommend one app per data type
3. **Read-first pattern** - AID apps should read glucose from HK rather than duplicate CGM writes

### Medium-term

1. **Shared HealthKitSyncKit package** - Unified sync logic with dedup
2. **Cross-app detection** - Query HKSource at startup
3. **Conflict warnings** - Alert users to multi-app scenarios

### Long-term

1. **Ecosystem coordination** - Standard syncIdentifier format
2. **Nightscout as arbiter** - Use NS identifier for HK sample correlation
3. **HealthKit reading mode** - CGM apps write, AID apps read-only

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [apple-watch-complications-survey.md](apple-watch-complications-survey.md) | Watch app patterns |
| [follower-caregiver-feature-consolidation.md](follower-caregiver-feature-consolidation.md) | Follower apps |
| [swift-package-ecosystem-assessment.md](swift-package-ecosystem-assessment.md) | SPM status |
