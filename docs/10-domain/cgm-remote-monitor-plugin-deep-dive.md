# cgm-remote-monitor Plugin System Deep Dive

> **Purpose**: Comprehensive analysis of Nightscout's plugin architecture  
> **Scope**: 38 plugins, data processing pipeline, AID controller integration  
> **Last Updated**: 2026-01-29

## Executive Summary

This document analyzes the plugin system of cgm-remote-monitor, focusing on data processing plugins (IOB, COB) and AID controller integration (Loop, OpenAPS). The plugin architecture provides extensibility but reveals compatibility gaps between different AID systems.

### Key Findings

| Finding | Impact |
|---------|--------|
| 38 plugins with standardized lifecycle | Extensible architecture |
| IOB/COB use device-first, treatment-fallback | Accurate with fresh devicestatus |
| Loop vs OpenAPS prediction formats differ | Visualization complexity |
| No AAPS-specific plugin exists | AAPS uses OpenAPS plugin |

---

## Plugin Architecture

### Directory Structure

```
lib/plugins/
├── index.js           # Plugin registry and lifecycle
├── pluginbase.js      # Base utilities for UI plugins
├── iob.js             # Insulin on Board calculation
├── cob.js             # Carbs on Board calculation
├── loop.js            # Loop iOS controller
├── openaps.js         # OpenAPS/AAPS controller
├── profile.js         # Therapy profile
├── pump.js            # Pump status
└── ... (30 more plugins)
```

### Plugin Lifecycle

**File**: `lib/plugins/index.js`

```javascript
// Registration
plugins.registerServerDefaults()  // 21 server plugins
plugins.registerClientDefaults()  // 24 client plugins

// Lifecycle methods (called in order)
plugins.setProperties(sbx)        // Compute derived properties
plugins.checkNotifications(sbx)   // Check alert conditions
plugins.updateVisualisations(sbx) // Update UI elements
```

### Plugin Interface

All plugins must implement:

```javascript
{
  name: 'pluginname',           // Unique identifier
  label: 'Display Name',        // UI label
  pluginType: 'pill-major'      // Category
}
```

Optional lifecycle methods:
- `setProperties(sbx)` - Offer computed properties
- `checkNotifications(sbx)` - Request alerts
- `updateVisualisation(sbx)` - Update UI
- `getEventTypes(sbx)` - Define treatment types

### Plugin Categories

| Type | Purpose | Plugins |
|------|---------|---------|
| `pill-primary` | Main display | bgnow |
| `pill-major` | Key metrics | iob |
| `pill-minor` | Secondary metrics | cob, insulinage, cannulaage, sensorage |
| `pill-status` | System status | pump, loop, openaps, override |
| `notification` | Alerts | simplealarms, errorcodes, treatmentnotify |
| `drawer` | UI panels | careportal, boluscalc |
| `forecast` | Predictions | ar2 |

---

## Core Data Processing Plugins

### IOB (Insulin on Board)

**File**: `lib/plugins/iob.js`

#### Data Sources (Priority Order)

1. **Device Status** (preferred)
   - `devicestatus.loop.iob` - Loop iOS
   - `devicestatus.openaps.iob` - OpenAPS/AAPS
   - `devicestatus.pump.iob` - Pump-reported

2. **Treatment Fallback**
   - Calculates from `treatments` with insulin field
   - Uses exponential decay model

#### Calculation Model

```javascript
// Exponential decay with DIA (Duration of Insulin Action)
scaleFactor = 3.0 / DIA  // Default DIA=3

// Phase 1: Rising (0-75 min)
if (minAgo < 75) {
  iobContrib = insulin × (1 - 0.001852×x² + 0.001852×x)
}

// Phase 2: Falling (75-180 min)
if (minAgo >= 75) {
  iobContrib = insulin × (0.001323×x² - 0.054233×x + 0.55556)
}
```

#### Properties Exposed

| Property | Type | Description |
|----------|------|-------------|
| `iob` | number | Total insulin on board (units) |
| `basaliob` | number | Basal component (from OpenAPS) |
| `activity` | number | Insulin activity (BG impact) |
| `lastBolus` | object | Most recent bolus |
| `source` | string | Data origin (Loop/OpenAPS/Care Portal) |

---

### COB (Carbs on Board)

**File**: `lib/plugins/cob.js`

#### Data Sources (Priority Order)

1. **Device Status** (10-min freshness)
   - `devicestatus.openaps.suggested.COB`
   - `devicestatus.openaps.enacted.COB`
   - `devicestatus.loop.cob.cob`

2. **Treatment Fallback**
   - Calculates from `treatments` with carbs field
   - Uses absorption decay model

#### Calculation Model

```javascript
// Carb absorption with insulin-aware delay
carbs_hr = profile.getCarbAbsorptionRate()  // g/hr
liverSensRatio = 8  // Hepatic glucose factor

// Decay timing
startDecay = carbTime + 20min  // Absorption delay
decayEnd = startDecay + (carbs / absorptionRate)

// Insulin delay adjustment
delayedCarbs = avgActivity × liverSensRatio / sensitivity
delayMinutes = delayedCarbs / absorptionRate × 60

// Remaining COB
if (currentTime < decayEnd) {
  cob += min(carbs, remainingDecayTime × absorptionRate)
}
```

#### Properties Exposed

| Property | Type | Description |
|----------|------|-------------|
| `cob` | number | Total carbs on board (grams) |
| `lastCarbs` | object | Most recent carb entry |
| `decayedBy` | timestamp | When carbs finish absorbing |
| `isDecaying` | boolean | Carbs actively absorbing |
| `rawCarbImpact` | number | Carb-driven glucose impact |

---

## AID Controller Plugins

### Loop Plugin

**File**: `lib/plugins/loop.js`

#### DeviceStatus Fields Consumed

```javascript
status.loop = {
  enacted: { timestamp, received },
  recommendedTempBasal: { rate, duration, timestamp },
  iob: { iob, basaliob },
  cob: { cob },
  predicted: { startDate, values: [] },
  recommendedBolus: number,
  failureReason: string,
  name: string
}
status.override = { timestamp }
status.radioAdapter = { pumpRSSI, RSSI }
```

#### Status States

| Symbol | State | Condition |
|--------|-------|-----------|
| ↻ | Looping | Recent successful loop |
| ⌁ | Enacted | Temp basal enacted |
| ⏀ | Recommendation | Suggestion without enact |
| ⚠ | Warning | Loop running but issues |
| x | Error | Loop failure |

#### Properties Exposed

- `lastLoop` - Most recent loop status
- `lastEnacted` - Last enacted temp basal
- `lastPredicted` - Prediction array
- `lastOverride` - Active override
- `lastOkMoment` - Last successful run

---

### OpenAPS Plugin

**File**: `lib/plugins/openaps.js`

#### DeviceStatus Fields Consumed

```javascript
status.openaps = {
  enacted: {
    timestamp, rate, duration, reason, mills,
    received: boolean,  // Note: also accepts 'recieved' typo
    predBGs: { IOB, ZT, COB, aCOB, UAM },
    eventualBG, mealAssist
  },
  suggested: {
    timestamp, mills, reason, bg,
    sensitivityRatio, predBGs, eventualBG
  },
  iob: [{ iob, basaliob, bolusiob, mills, timestamp }]
}
status.mmtune = { timestamp, scanDetails, setFreq }
status.device = string
```

#### Status States

| Symbol | State | Condition |
|--------|-------|-----------|
| ⌁ | Enacted | Command received by pump |
| ↻ | Looping | Recent activity |
| ◉ | Waiting | Suggestion pending |
| x | Not Enacted | Pump didn't receive |
| ⚠ | Warning | Stale data |

#### Properties Exposed

- `lastEnacted` - Enacted with received confirmation
- `lastSuggested` - Most recent suggestion
- `lastIOB` - IOB from OpenAPS
- `lastPredBGs` - 6 prediction curves (IOB, ZT, COB, aCOB, UAM, Values)
- `lastEventualBG` - Final predicted BG
- `seenDevices` - Multi-device tracking

---

## Prediction Data Comparison

### Format Differences

| Aspect | Loop | OpenAPS/AAPS |
|--------|------|--------------|
| Structure | Single `values` array | 6 separate arrays |
| Curves | Combined prediction | IOB, ZT, COB, aCOB, UAM, Values |
| Start time | `startDate` field | Inferred from first point |
| Interval | 5 minutes | 5 minutes |

### Loop Prediction Format

```json
{
  "predicted": {
    "startDate": "2026-01-29T12:00:00Z",
    "values": [120, 118, 115, 112, 110, ...]
  }
}
```

### OpenAPS Prediction Format

```json
{
  "predBGs": {
    "IOB": [120, 115, 110, ...],
    "ZT": [120, 118, 116, ...],
    "COB": [120, 125, 130, ...],
    "aCOB": [120, 122, 124, ...],
    "UAM": [120, 130, 140, ...]
  }
}
```

---

## Data Pipeline

### Property Flow

```
┌─────────────────────────────────────────────────────────┐
│                    Data Sources                          │
├─────────────────────────────────────────────────────────┤
│  treatments    devicestatus    entries    profile        │
└──────┬────────────┬────────────┬────────────┬───────────┘
       │            │            │            │
       ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────┐
│                  Sandbox (sbx)                           │
│  sbx.data.treatments, sbx.data.devicestatus, etc.       │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Plugin.setProperties(sbx)                   │
│  Each plugin offers computed properties via              │
│  sbx.offerProperty('name', computeFn)                   │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│                 sbx.properties                           │
│  { iob, cob, loop, openaps, pump, ... }                 │
└─────────────────────────────────────────────────────────┘
```

### Plugin Initialization Order

1. `bgnow` - Current glucose
2. `direction` - Trend arrow
3. `iob` - Insulin on board
4. `cob` - Carbs on board
5. `loop` / `openaps` - Controller status
6. `pump` - Pump status
7. `profile` - Therapy settings

---

## Gaps Identified

### GAP-PLUGIN-001: No AAPS-Specific Plugin

**Description**: AAPS uploads to Nightscout but uses the OpenAPS plugin for display. AAPS-specific fields may not be utilized.

**Evidence**:
- `openaps.js` handles AAPS data via OpenAPS format
- AAPS has unique fields (interfaceIDs, pumpType) not processed
- SMB-specific visualization not differentiated

**Impact**: AAPS users may see incomplete status information.

**Remediation**: Extend OpenAPS plugin or create AAPS-specific plugin.

### GAP-PLUGIN-002: Prediction Curve Mismatch

**Description**: Loop uses single prediction array while OpenAPS/AAPS use 6 separate curves. Visualization logic must handle both.

**Evidence**:
```javascript
// Loop: status.loop.predicted.values[]
// OpenAPS: status.openaps.predBGs.{IOB,ZT,COB,aCOB,UAM}[]
```

**Impact**: Unified prediction visualization requires format normalization.

**Remediation**: Document canonical format in API spec (GAP-API-006).

### GAP-PLUGIN-003: Enacted Confirmation Inconsistency

**Description**: OpenAPS requires explicit `received: true` flag, but field has typo tolerance (`recieved`). AAPS may not consistently send this.

**Evidence**:
```javascript
// openaps.js:44
if (enacted.received || enacted.recieved) { ... }
```

**Impact**: False "not enacted" status for AAPS users.

**Remediation**: Document required fields for devicestatus uploads.

---

## Source Files Analyzed

### Core Plugin System
- `lib/plugins/index.js` - Plugin registry (320 lines)
- `lib/plugins/pluginbase.js` - UI utilities

### Data Processing
- `lib/plugins/iob.js` - IOB calculation (220 lines)
- `lib/plugins/cob.js` - COB calculation (230 lines)
- `lib/plugins/profile.js` - Therapy profile

### AID Controllers
- `lib/plugins/loop.js` - Loop iOS (280 lines)
- `lib/plugins/openaps.js` - OpenAPS/AAPS (350 lines)
- `lib/plugins/pump.js` - Pump status
- `lib/plugins/override.js` - Override handling

### Other Notable Plugins
- `lib/plugins/ar2.js` - AR2 prediction algorithm
- `lib/plugins/boluscalc.js` - Bolus calculator
- `lib/plugins/careportal.js` - Treatment entry
- `lib/plugins/simplealarms.js` - Alert system

---

## Recommendations

| Priority | Action | Impact |
|----------|--------|--------|
| P1 | Document devicestatus schema per controller | Fixes upload inconsistencies |
| P1 | Add `received` field requirement to spec | Fixes enacted confirmation |
| P2 | Normalize prediction format in API | Simplifies visualization |
| P2 | Document IOB/COB calculation models | Enables cross-project validation |
| P3 | Create AAPS-specific plugin | Better AAPS support |

---

## Related Documents

- [API Layer Deep Dive](cgm-remote-monitor-api-deep-dive.md)
- [Database Layer Deep Dive](cgm-remote-monitor-database-deep-dive.md)
- [Prediction Arrays Comparison](prediction-arrays-comparison.md)
- [DeviceStatus OpenAPI Spec](../../specs/openapi/aid-devicestatus-2025.yaml)
