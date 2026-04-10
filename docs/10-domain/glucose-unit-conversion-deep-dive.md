# Glucose Unit Conversion Deep Dive

This document provides a comprehensive cross-project analysis of how glucose units (mg/dL vs mmol/L) are handled for ingestion, storage, algorithm processing, and display across all major apps in the Nightscout AID ecosystem.

---

## Executive Summary

**Every app in the ecosystem stores glucose internally in mg/dL.** Conversion to mmol/L is performed exclusively at the display layer based on user preferences. All Nightscout API traffic (entries, treatments, devicestatus) uses mg/dL. However, the **conversion factors differ** across projects (ranging from 18 to 18.0182), creating minor rounding inconsistencies.

### Key Findings

1. **Universal mg/dL storage** — all 10+ apps store glucose in mg/dL
2. **Display-only conversion** — mmol/L is never persisted; it is computed at render time
3. **Conversion factor divergence** — 6 distinct constants used across the ecosystem (see §4)
4. **No API-level unit negotiation** — Nightscout APIs accept and return mg/dL only; no `Accept-Units` header or unit field on entries
5. **Threshold auto-conversion** — Nightscout and oref0 use heuristics (value < 20 or < 50) to detect mmol/L in user-configured settings

---

## 1. Per-App Unit Handling

### 1.1 Nightscout (cgm-remote-monitor)

| Aspect | Value | Source |
|--------|-------|--------|
| **Storage** | mg/dL (MongoDB `sgv` field) | `lib/data/dataloader.js:219-230` |
| **API ingestion** | mg/dL only, no auto-detection | `lib/api/entries/index.js:322` |
| **Display** | Determined by `settings.units` (`'mg/dl'` or `'mmol'`) | `lib/settings.js:9` |
| **Conversion factor** | **18.01559** | `lib/constants.json:10` |
| **Conversion functions** | `units.mgdlToMMOL()`, `units.mmolToMgdl()` | `lib/units.js:5-11` |
| **Threshold heuristic** | If `settings.units` includes `'mmol'` AND thresholds < 50, auto-convert thresholds | `lib/settings.js:289-293` |

**Details**: The `sgv` field is always stored as an integer in mg/dL in MongoDB. The `settings.units` field controls display only. Profile `units` field indicates the profile's glucose unit context but does not affect storage. Client-side `utils.scaleMgdl()` (`lib/utils.js:15-21`) converts for display when `settings.units === 'mmol'`.

```javascript
// lib/units.js
function mgdlToMMOL(mgdl) {
  return (Math.round((mgdl / consts.MMOL_TO_MGDL) * 10) / 10).toFixed(1);
}
function mmolToMgdl(mgdl) {
  return Math.round(mgdl * consts.MMOL_TO_MGDL);
}
```

### 1.2 Loop (iOS)

| Aspect | Value | Source |
|--------|-------|--------|
| **Internal** | mg/dL via `HKQuantity(.milligramsPerDeciliter)` | `LoopKit/GlucoseValue.swift:47-48` |
| **Storage** | mg/dL in HealthKit and local stores | `LoopKit/GlucoseKit/StoredGlucoseSample.swift:116` |
| **Nightscout upload** | mg/dL always | `NightscoutServiceKit/Extensions/StoredGlucoseSample.swift:35` |
| **Display** | HealthKit system preference (`HKHealthStore.preferredUnits`) | `LoopKit/HealthStoreUnitCache.swift:53-113` |
| **Conversion factor** | **~18.01559** (via `HKUnitMolarMassBloodGlucose` = 180.1559 g/mol) | `LoopKit/Extensions/HKUnit.swift:18` |
| **Precision** | mg/dL: integer (chartableIncrement = 1); mmol/L: 0.04 (1/25) | `LoopKit/Extensions/HKUnit.swift:54-59` |

**Details**: Loop never hardcodes a conversion constant. Instead, it relies on Apple's HealthKit framework which uses the glucose molar mass (180.1559 g/mol) to perform mathematically precise unit conversions via `HKQuantity.doubleValue(for:)`. CGM data from Dexcom Share, Libre, and Nightscout Remote all arrive as `HKQuantity` in mg/dL. Display unit is determined by the iOS system HealthKit preference, not a Loop-specific setting.

### 1.3 AndroidAPS

| Aspect | Value | Source |
|--------|-------|--------|
| **Internal** | mg/dL (`GlucoseValue.value: Double`) | `database/entities/GlucoseValue.kt:28-44` |
| **Storage** | mg/dL in Room database | `database/entities/TemporaryTarget.kt:28` (comment: `// in mgdl`) |
| **Nightscout upload** | mg/dL, hardcoded `units = NsUnits.MG_DL` | `plugins/sync/.../GlucoseValueExtension.kt:27-40` |
| **Nightscout download** | Converts with `.asMgdl()` if units are mmol/L | `core/nssdk/.../NsUnits.kt:1-12` |
| **Display** | User preference `StringKey.GeneralUnits` (default: `"mg/dl"`) | `implementation/profile/ProfileFunctionImpl.kt:144-146` |
| **Conversion factor** | **18.0** (comment: `// 18.0182;`) | `core/data/configuration/Constants.kt:8-9` |
| **GlucoseUnit enum** | `MGDL`, `MMOL` | `core/data/model/GlucoseUnit.kt:1-17` |

**Details**: AAPS uses the simplified factor 18.0, despite a comment acknowledging 18.0182. The oref algorithm receives all glucose values in mg/dL. The `out_units` profile field controls output formatting only. Download conversion: `fun Double.asMgdl() = when (units) { NsUnits.MG_DL -> this; NsUnits.MMOL_L -> this * 18; null -> this }`.

### 1.4 Trio (iOS)

| Aspect | Value | Source |
|--------|-------|--------|
| **Internal** | mg/dL (`GlucoseStored.glucose: Int16`) | `Model/Classes+Properties/GlucoseStored+CoreDataProperties.swift:11` |
| **Storage** | mg/dL in Core Data | `Model/Helper/GlucoseStored+helper.swift:30-31` |
| **Nightscout sync** | mg/dL (no conversion) | `Services/Network/Nightscout/NightscoutManager.swift:864-882` |
| **Display** | User setting `TrioSettings.units` (default: `.mgdL`) | `Models/TrioSettings.swift:19` |
| **Conversion factor** | **0.0555** (= 1/18.018018...) | `Models/BloodGlucose.swift:166` |
| **OpenAPS bridge** | mg/dL passed directly to oref1 JS engine | `APS/OpenAPS/OpenAPS.swift:100-120` |
| **HealthKit** | Always `.milligramsPerDeciliter` | `Models/BloodGlucose.swift:269` |

**Details**: Trio defines `GlucoseUnits` enum with `.mgdL` and `.mmolL` raw values. Conversion uses `Decimal` arithmetic: `Decimal(self) * GlucoseUnits.exchangeRate` for mg/dL→mmol/L. The `exchangeRate` of 0.0555 corresponds to 1/18.018018... ≈ 18.018.

### 1.5 xDrip+ (Android)

| Aspect | Value | Source |
|--------|-------|--------|
| **Internal** | mg/dL (`BgReading.calculated_value`) | `models/BgReading.java:119-120` |
| **Storage** | mg/dL in SQLite | `models/BgReading.java:103-128` |
| **Nightscout upload** | mg/dL: `json.put("sgv", (int) record.calculated_value)` | `utilitymodels/NightscoutUploader.java:703` |
| **Display** | User preference `"units"` (`"mgdl"` or `"mmol"`) | `utils/Preferences.java:1036` |
| **Conversion factor** | **18.0182** | `utilitymodels/Constants.java:7-8` |
| **CGM ingestion** | mg/dL from Dexcom, Libre2, all sources | `models/BgReading.java:1298-1319` |
| **Local web server** | mg/dL with `units_hint` field | `webservices/WebServiceSgv.java:184,224-225` |

**Details**: xDrip+ is the primary glucose data producer in many setups. All CGM hardware (Dexcom, Libre, Medtronic) delivers data in mg/dL. The local web server (`/sgv.json`) always returns mg/dL values but includes a `units_hint` field so clients know the user's display preference.

### 1.6 xDrip4iOS (xdripswift)

| Aspect | Value | Source |
|--------|-------|--------|
| **Internal** | mg/dL (`calculatedValue: Double`) | `Core Data/classes/BgReading+CoreDataClass.swift:113` |
| **Storage** | mg/dL in Core Data | `Core Data/Extensions/BgReading+CoreDataProperties.swift:11-27` |
| **Nightscout upload** | mg/dL: `"sgv": Int(calculatedValue.round(toDecimalPlaces: 0))` | `Managers/Nightscout/BgReading+Nightscout.swift:14` |
| **Display** | `UserDefaults.bloodGlucoseUnitIsMgDl` boolean | `Extensions/UserDefaults.swift:659` |
| **Conversion factor** | **18.01801801801802** (= 1/0.0555 exactly) and **0.0555** | `Constants/ConstantsBloodGlucose.swift:2-3` |

**Details**: No dedicated glucose unit enum — uses a boolean flag throughout. Conversion functions in `Double` extension check the boolean and multiply/divide as needed.

### 1.7 DiaBLE (iOS)

| Aspect | Value | Source |
|--------|-------|--------|
| **Internal** | mg/dL (`Glucose.value: Int`) | `DiaBLE/Glucose.swift:123` |
| **Storage** | mg/dL | `DiaBLE/Glucose.swift:133,151` |
| **Nightscout upload** | mg/dL: `"sgv": $0.value` | `DiaBLE/Nightscout.swift:161` |
| **Display** | `UserDefaults.displayingMillimoles` boolean | `DiaBLE/Settings.swift:119` |
| **Conversion factor** | **18.0182** | `DiaBLE/Glucose.swift:20,27` |
| **Libre hardware** | Raw ADC counts → calibrated to mg/dL | `DiaBLE/LibreLink.swift:117` |

**Details**: LibreLink API provides both `ValueInMgPerDl` and `mmoll` fields; DiaBLE always uses the mg/dL variant. Abbott Libre sensors transmit raw ADC counts via BLE, which are calibrated to mg/dL using sensor FRAM calibration data.

### 1.8 oref0 (OpenAPS Reference Algorithm)

| Aspect | Value | Source |
|--------|-------|--------|
| **Algorithm input** | mg/dL only | `lib/determine-basal/determine-basal.js:152` |
| **ISF, targets** | mg/dL internally; targets auto-converted if < 20 | `lib/profile/targets.js:71-73` |
| **Conversion factor** | **18** (integer) | `lib/determine-basal/determine-basal.js:43` |
| **Output** | Display fields converted via `convert_bg()` when `out_units === "mmol/L"` | `lib/determine-basal/determine-basal.js:39-49` |
| **Profile** | `out_units` from `inputs.targets.user_preferred_units` | `lib/profile/index.js:153` |

**Details**: oref0 is the simplest — it's hardcoded to mg/dL for all calculations. The only mmol/L awareness is: (1) auto-converting input targets < 20 by multiplying by 18, and (2) dividing output display values by 18 when `out_units === "mmol/L"`. Uses integer 18, not the precise molar mass factor.

### 1.9 Bridge Apps

All bridge applications output **mg/dL to Nightscout** without glucose value conversion:

| Bridge | Source Units | To Nightscout | Conversion | Source |
|--------|-------------|---------------|------------|--------|
| **share2nightscout-bridge** | mg/dL (Dexcom Share API) | mg/dL | None | `index.js:247` (`sgv: d.Value`) |
| **nightscout-librelink-up** | mg/dL + mmol/L (both provided) | mg/dL | Uses `ValueInMgPerDl` only | `src/index.ts:302` |
| **nightscout-connect** | mg/dL (all sources) | mg/dL | None | `lib/sources/librelinkup.js:140` |
| **minimed-connect** | mg/dL | mg/dL | None | `transform.js:153` |
| **tconnectsync** | mg/dL (Tandem API) | mg/dL | Settings only (18.0182) | `util/constants.py:3` |

**Note**: tconnectsync defines `MMOLL_TO_MGDL = 18.0182` but uses it only when parsing pump settings displayed in mmol/L on the Tandem web UI, never for glucose values.

### 1.10 Nightscout Reporter (Dart)

| Aspect | Value | Source |
|--------|-------|--------|
| **Conversion factor** | **18.02** | `nr:lib/src/globals.dart` (`glucFactor`) |
| **Display** | Three modes: mg/dL, mmol/L, or both | `nr:lib/src/globals.dart` (`glucMGDLIdx`) |
| **Precision** | mg/dL: 0 decimal; mmol/L: 2 decimal | `nr:lib/src/globals.dart` (`glucPrecision`) |
| **Unit detection** | Parses `settings.units` from server status | `nr:lib/src/globals.dart:L192-L199` |

**Details**: See `mapping/nightscout-reporter/unit-conversion.md` for comprehensive analysis.

---

## 2. Conversion Factor Comparison

The glucose molecular weight is 180.156 g/mol, giving a theoretical conversion factor of **18.0156 mg/dL per mmol/L** (180.156 ÷ 10).

| App | Factor (mmol/L → mg/dL) | Inverse | Derivation |
|-----|-------------------------|---------|------------|
| **oref0** | 18 | 0.0556 | Rounded integer |
| **AAPS** | 18.0 | 0.0556 | Rounded (comment: 18.0182) |
| **Nightscout** | 18.01559 | 0.05550 | Matches molar mass 180.1559 |
| **Loop** | ~18.01559 | ~0.05550 | Via `HKUnitMolarMassBloodGlucose` (180.1559) |
| **Trio** | ~18.018 | 0.0555 | Via `1/0.0555` |
| **xDrip+** | 18.0182 | 0.05550 | Explicit constant |
| **xDrip4iOS** | 18.01801... | 0.0555 | `1/0.0555` exactly |
| **DiaBLE** | 18.0182 | 0.05550 | Explicit constant |
| **tconnectsync** | 18.0182 | 0.0555 | Settings only |
| **Reporter** | 18.02 | 0.05550 | Explicit constant |

### Practical Impact

The divergence is **clinically negligible**. Worst case at 400 mg/dL:

| Factor | Result (mmol/L) | Δ from 18.0156 |
|--------|-----------------|-----------------|
| 18 | 22.22 | +0.02 mmol/L |
| 18.0156 | 22.20 | (reference) |
| 18.0182 | 22.20 | < 0.01 mmol/L |
| 18.02 | 22.20 | < 0.01 mmol/L |

Maximum rounding difference: **0.1 mmol/L** (at regularly spaced glucose values), which is within CGM sensor error margins (±20 mg/dL / ±1.1 mmol/L). No clinical risk, but it means that the same glucose value may display as "5.6" in oref0 (factor 18) and "5.5" in xDrip+ (factor 18.0182) for 100 mg/dL, due to rounding at the 0.05 boundary. This 0.1 mmol/L divergence recurs approximately every 9 mg/dL across the clinical range.

---

## 3. Data Flow: Unit Lifecycle

```
┌─────────────────────────────────────────────────────────────┐
│                    CGM SENSOR HARDWARE                       │
│  (Raw ADC counts / proprietary format)                      │
└─────────────┬───────────────────────────────────────────────┘
              │ Calibration & conversion
              ▼
┌─────────────────────────────────────────────────────────────┐
│                    CGM APP (Producer)                        │
│  xDrip+, xDrip4iOS, DiaBLE, Dexcom app, Libre app          │
│  Internal: mg/dL    Storage: mg/dL                          │
└─────────────┬───────────────────────────────────────────────┘
              │ Upload (always mg/dL)
              ▼
┌─────────────────────────────────────────────────────────────┐
│              NIGHTSCOUT SERVER                               │
│  MongoDB entries.sgv: Number (mg/dL)                        │
│  No unit field on entries collection                        │
│  settings.units = display preference only                   │
└─────────────┬──────────────┬────────────────────────────────┘
              │              │
    Download  │              │  Download
    (mg/dL)   │              │  (mg/dL)
              ▼              ▼
┌──────────────────┐  ┌──────────────────┐
│   AID ALGORITHM  │  │  DISPLAY CLIENT  │
│  Loop / AAPS /   │  │  NS Web UI /     │
│  Trio / oref0    │  │  Reporter /      │
│                  │  │  Followers       │
│  All math in     │  │                  │
│  mg/dL only      │  │  Convert at      │
│                  │  │  render time     │
│  Output fields   │  │  using user      │
│  optionally      │  │  preference      │
│  converted for   │  │                  │
│  display         │  │  mg/dL → mmol/L  │
└──────────────────┘  └──────────────────┘
```

---

## 4. Unit-Sensitive Settings & Thresholds

While glucose *values* are always mg/dL, several user-configurable *settings* may be entered in either unit system. Each app handles this differently:

### 4.1 Nightscout Threshold Auto-Conversion

```javascript
// lib/settings.js:289-293
if (settings.units.toLowerCase().includes('mmol') && thresholds.bgHigh < 50) {
  thresholds.bgHigh = Math.round(thresholds.bgHigh * constants.MMOL_TO_MGDL);
  thresholds.bgTargetTop = Math.round(thresholds.bgTargetTop * constants.MMOL_TO_MGDL);
  thresholds.bgTargetBottom = Math.round(thresholds.bgTargetBottom * constants.MMOL_TO_MGDL);
  thresholds.bgLow = Math.round(thresholds.bgLow * constants.MMOL_TO_MGDL);
}
```

### 4.2 oref0 Target Auto-Conversion

```javascript
// lib/profile/targets.js:71-73
// if targets are < 20, assume for safety that they're intended to be mmol/L
if ( target.high < 20 ) { target.high = target.high * 18; }
if ( target.low < 20 ) { target.low = target.low * 18; }
```

### 4.3 AAPS Profile Handling

AAPS reads the profile's `glucoseUnit` field and converts ISF, targets, etc. to mg/dL using `.asMgdl()` before passing to the algorithm. The `ProfileSealed` class handles this transparently.

### 4.4 Trio Settings

User enters targets and ISF in their preferred unit (from `TrioSettings.units`). Values are converted to mg/dL before storage and before passing to the oref1 engine.

---

## 5. Profile Units Field

The Nightscout profile has a `units` field that specifies the glucose unit context:

| Collection | Field | Values | Purpose |
|------------|-------|--------|---------|
| `status` | `settings.units` | `"mg/dl"`, `"mmol"` | Server display default |
| `profile` | `units` | `"mg/dl"`, `"mmol/L"` | Per-profile glucose unit for ISF, targets |
| `treatments` | `units` | Optional per-record | Indicates unit of glucose field in treatment |
| `entries` | *(none)* | — | Always mg/dL, no unit field |

### Gap: No Unit Field on Entries

The `entries` collection has **no explicit unit field**. The assumption that `sgv` is always mg/dL is baked into every client. This is safe in practice (all producers send mg/dL) but is not formally documented in the API schema.

---

## 6. Display Precision

| Unit | Integer | Decimal Places | Examples |
|------|---------|----------------|----------|
| mg/dL | Yes (most apps) | 0 | 120, 95, 180 |
| mmol/L | No | 1 (most), 2 (Reporter) | 6.7, 5.3, 10.0 |

| App | mg/dL Precision | mmol/L Precision |
|-----|-----------------|------------------|
| Nightscout | integer | 1 decimal (`toFixed(1)`) |
| Loop | chartableIncrement = 1 | chartableIncrement = 0.04 (1/25) |
| AAPS | integer | 1 decimal |
| Trio | integer | 1 decimal |
| xDrip+ | integer | variable |
| Reporter | 0 decimals | 2 decimals |

---

## 7. Identified Gaps

### GAP-ENTRY-010: No Explicit Unit Field on Entries Collection

**Description**: The Nightscout `entries` collection stores `sgv` values without an explicit `units` field. The mg/dL convention is implied, not declared.

**Affected Systems**: All consumers of the entries API.

**Impact**: Low — the convention is universally followed. But a formal schema declaration would prevent future ambiguity, especially if new producers are added that natively use mmol/L.

**Remediation**: Add an optional `units` field to the entries schema, defaulting to `"mg/dl"`. Validate on ingestion that if `units` is `"mmol"` and `sgv` < 50, auto-convert to mg/dL.

### GAP-ENTRY-011: Inconsistent Conversion Factors Across Ecosystem

**Description**: Six different conversion factors are used across the ecosystem (18, 18.0, 18.01559, 18.0182, 18.01801..., 18.02).

**Affected Systems**: All apps performing mg/dL ↔ mmol/L conversion.

**Impact**: Negligible clinical impact (max 0.1 mmol/L difference). However, it can cause display inconsistencies where the same glucose value shows different mmol/L values across apps, which may confuse users.

**Remediation**: Standardize on the precise glucose molar mass factor. Recommended: **18.01559** (matching glucose molar mass 180.1559 g/mol, consistent with Nightscout server and Apple HealthKit). Document this in the OpenAPI spec as a normative constant.

### GAP-ENTRY-012: oref0 Integer Division Causes Rounding Artifacts

**Description**: oref0 uses integer `18` for conversion, while all other apps use a more precise value. This means oref0 output fields (BGI, ISF, target_bg, deviation) in mmol/L mode may differ from what other apps would display.

**Affected Systems**: oref0, AAPS (inherits oref0 factor), Trio (bridges to oref0).

**Impact**: Low — affects display only, not algorithm calculations (which remain in mg/dL).

**Remediation**: Update `convert_bg()` in oref0 to use 18.01559 instead of 18.

---

## 8. Recommendations

### For Spec Authors

1. **Declare mg/dL as the canonical storage unit** in OpenAPI specs with a normative note
2. **Standardize conversion constant** as `18.01559` in a shared constants definition
3. **Add optional `units` field** to entries schema for forward compatibility

### For App Developers

1. **Always store in mg/dL** — this is already universally followed
2. **Convert at display time only** — this is already universally followed
3. **Use the precise factor** (18.01559) for new code; avoid integer 18
4. **Round mmol/L to 1 decimal place** for display consistency

### For Data Consumers

1. **Assume entries `sgv` is mg/dL** — this is safe for all current producers
2. **Check profile `units`** before interpreting ISF, targets, and correction ranges
3. **Check treatment `units`** field when present for per-record unit context

---

## Cross-References

- [Entries Deep Dive](entries-deep-dive.md) — Field mapping for the entries collection
- [Nightscout Reporter Unit Conversion](../../mapping/nightscout-reporter/unit-conversion.md) — Detailed Reporter analysis
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md) — Cross-project term mapping
- [Profile Schema Alignment](profile-schema-alignment.md) — Profile units handling
- [OpenAPI Entries Spec](../../specs/openapi/aid-entries-2025.yaml) — Formal schema

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-04-10 | Agent | Initial comprehensive cross-project analysis. Verified conversion factors from source code across 10 apps. |
