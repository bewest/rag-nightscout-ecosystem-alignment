# AID Controller Conflict Detection Proposal

> **Status**: Draft  
> **Created**: 2026-02-01  
> **Domain**: Safety / Interoperability  
> **Priority**: P1 (Patient Safety)

---

## Problem Statement

DIY diabetes technology users frequently have **multiple CGM and AID apps installed simultaneously**. This creates several critical issues:

1. **BLE Peripheral Contention**: Bluetooth peripherals (CGM transmitters, insulin pumps) can only maintain ONE active connection. Multiple apps competing for the same peripheral causes:
   - Intermittent connections
   - Data gaps
   - Failed insulin delivery commands
   - User confusion ("it was working yesterday")

2. **Duplicate Insulin Delivery Risk**: If two AID controllers are both trying to command the same pump, insulin delivery becomes unpredictable and potentially dangerous.

3. **Data Integrity Issues**: Multiple apps uploading to Nightscout can create duplicate entries, conflicting treatments, or out-of-sync state.

4. **User Support Burden**: "My CGM stopped working" is often caused by a forgotten app running in background.

## Ecosystem Context

### Common Installation Patterns

Based on community observation, users frequently have:

| Pattern | Installed Apps | Risk Level |
|---------|---------------|------------|
| Migration | Loop + Trio | HIGH (both AID) |
| Backup CGM | xDrip + Dexcom | MEDIUM (CGM contention) |
| Family device | Loop + Follower apps | LOW (different roles) |
| Developer | Loop + Trio + AAPS (via Mac) | HIGH |
| Experimenting | DiaBLE + xDrip4iOS + Dexcom | MEDIUM |

### BLE Peripheral Exclusivity

```
┌─────────────┐          ┌─────────────┐
│   Dexcom    │──────────│    Loop     │  ✓ Works
│ Transmitter │          │             │
└─────────────┘          └─────────────┘

┌─────────────┐          ┌─────────────┐
│   Dexcom    │────┬─────│    Loop     │  ✗ Conflict
│ Transmitter │    │     │             │
└─────────────┘    │     └─────────────┘
                   │     ┌─────────────┐
                   └─────│   xDrip     │  ✗ Conflict
                         │             │
                         └─────────────┘
```

## Proposed Solution

### Detection Mechanisms

#### 1. URL Scheme Detection (Limited but Works)

Apps can check if specific URL schemes are registered:

```swift
// Info.plist: LSApplicationQueriesSchemes
// Must declare schemes you want to query (max 50)

let knownSchemes = [
    "loop://",           // Loop
    "freeaps://",        // Trio/iAPS
    "xdripswift://",     // xDrip4iOS
    "diabox://",         // Diabox
    "sugarmate://",      // Sugarmate
]

func detectInstalledApps() -> [String] {
    return knownSchemes.compactMap { scheme in
        if UIApplication.shared.canOpenURL(URL(string: scheme)!) {
            return scheme
        }
        return nil
    }
}
```

**Limitation**: iOS 9+ requires pre-declaring schemes in Info.plist.

#### 2. BLE Service UUID Scanning

More reliable - detects apps that are actively scanning/connected:

```swift
// Known CGM/Pump service UUIDs
let knownServiceUUIDs = [
    CBUUID(string: "FEBC"),                    // Dexcom advertisement
    CBUUID(string: "0000FDE3-0000-1000-8000-00805F9B34FB"), // Omnipod
    CBUUID(string: "00001523-1212-EFDE-1523-785FEABCD123"), // Libre
]

// If we see these being scanned by another app, there's contention
// This requires being a BLE peripheral to observe incoming scans
// (Complex - the transmitter simulator could do this)
```

#### 3. User Self-Report (Most Reliable)

During onboarding or in settings:

```
┌─────────────────────────────────────────┐
│     CGM & Pump App Check                │
├─────────────────────────────────────────┤
│                                         │
│  Do you have any of these apps          │
│  installed on this device?              │
│                                         │
│  [ ] Loop                               │
│  [ ] Trio / iAPS / FreeAPS              │
│  [ ] xDrip4iOS                          │
│  [ ] Dexcom G6 / G7                     │
│  [ ] Libre Link                         │
│  [ ] DiaBLE                             │
│  [ ] Other CGM app: _________           │
│                                         │
│  [Continue]                             │
│                                         │
└─────────────────────────────────────────┘
```

### Conflict Assessment Matrix

| Detected App | T1Pal Mode | Conflict Level | Guidance |
|--------------|------------|----------------|----------|
| Loop | CGM | HIGH | Disable Loop or use as CGM source |
| Loop | AID | CRITICAL | Cannot run simultaneously |
| Trio | CGM | HIGH | Disable Trio or use as CGM source |
| Trio | AID | CRITICAL | Cannot run simultaneously |
| xDrip4iOS | CGM | HIGH | Choose one CGM manager |
| xDrip4iOS | AID | MEDIUM | Can coexist if xDrip is receive-only |
| Dexcom | CGM | HIGH | Dexcom Share as source, not direct BLE |
| Dexcom | AID | MEDIUM | Can coexist if using Share |
| Follower apps | Any | NONE | No BLE contention |

### User Guidance Patterns

#### Critical Conflict Alert
```
┌─────────────────────────────────────────┐
│ ⚠️ AID Conflict Detected                │
├─────────────────────────────────────────┤
│                                         │
│ Loop is installed on this device.       │
│                                         │
│ Running two AID controllers at once     │
│ can cause unpredictable insulin         │
│ delivery. This is dangerous.            │
│                                         │
│ Before using T1Pal AID:                 │
│ 1. Open Loop                            │
│ 2. Tap "Close Loop" to disable          │
│ 3. Or delete Loop                       │
│                                         │
│ [I've Disabled Loop]  [Go Back]         │
│                                         │
└─────────────────────────────────────────┘
```

#### CGM Contention Warning
```
┌─────────────────────────────────────────┐
│ ⚠️ CGM App Detected                     │
├─────────────────────────────────────────┤
│                                         │
│ xDrip4iOS is installed.                 │
│                                         │
│ Only one app can connect to your        │
│ CGM transmitter at a time.              │
│                                         │
│ Options:                                │
│ • Use xDrip as CGM source (recommended) │
│ • Disable xDrip, use T1Pal direct       │
│                                         │
│ [Use xDrip as Source]  [Use T1Pal]      │
│                                         │
└─────────────────────────────────────────┘
```

## Implementation Phases

### Phase 1: User Self-Report (Minimal)
- Onboarding checklist of common apps
- Static guidance based on selections
- No runtime detection

### Phase 2: URL Scheme Detection
- Declare known schemes in Info.plist
- Detect at launch and in settings
- Dynamic guidance based on detection

### Phase 3: Active Monitoring
- Monitor BLE scan behavior
- Detect when contention is occurring
- Alert user: "Another app is trying to connect to your CGM"

### Phase 4: Ecosystem Coordination (Future)
- Standard URL scheme for "am I running?" query
- Inter-app communication to negotiate primary role
- Graceful handoff protocols

## Requirements Trace

| Requirement | Description |
|-------------|-------------|
| REQ-CONFLICT-001 | App SHALL detect commonly installed CGM apps |
| REQ-CONFLICT-002 | App SHALL detect commonly installed AID apps |
| REQ-CONFLICT-003 | App SHALL assess conflict severity (none/medium/high/critical) |
| REQ-CONFLICT-004 | App SHALL display actionable guidance for conflicts |
| REQ-CONFLICT-005 | App SHALL NOT prevent use, only warn (user autonomy) |
| REQ-CONFLICT-006 | App SHOULD offer to use detected apps as data sources |

## Gap Analysis

### GAP-CONFLICT-001: No Standard Coexistence Protocol

**Description**: There is no ecosystem-wide standard for DIY apps to:
- Announce their presence
- Negotiate who has primary BLE access
- Hand off connections gracefully

**Impact**: Users must manually manage app conflicts.

**Remediation**: Propose a simple URL-scheme or local-network protocol for app coordination.

### GAP-CONFLICT-002: iOS URL Scheme Query Limits

**Description**: iOS limits `LSApplicationQueriesSchemes` to 50 entries and requires pre-declaration.

**Impact**: Cannot dynamically detect unknown apps.

**Remediation**: Combine with user self-report; maintain known-app database.

### GAP-CONFLICT-003: No Background Contention Detection

**Description**: When apps are backgrounded, BLE contention is invisible to the user.

**Impact**: Users don't know why their CGM "randomly stops working."

**Remediation**: Use the transmitter simulator in passive mode to observe contention (advanced).

## Cross-Project References

| Project | Relevant Code | Notes |
|---------|--------------|-------|
| Loop | `LoopKit/CGMManager/CGMManager.swift` | CGM connection management |
| Trio | `FreeAPS/Sources/Modules/CGM/` | Multiple CGM source support |
| xDrip4iOS | `xdrip/BluetoothTransmitter/` | BLE peripheral management |
| DiaBLE | `DiaBLE/Bluetooth.swift` | CBCentralManager usage |

## Appendix: Known URL Schemes

| App | URL Scheme | Source |
|-----|------------|--------|
| Loop | `loop://` | LoopKit |
| Trio | `freeaps://` | Trio Info.plist |
| xDrip4iOS | `xdripswift://` | xDrip4iOS Info.plist |
| Dexcom G6 | `dexcomg6://` | App Store analysis |
| Dexcom G7 | `dexcomg7://` | App Store analysis |
| Sugarmate | `sugarmate://` | App Store analysis |
| Nightscout | `nightscout://` | Common convention |

---

## Related Documents

- `t1pal-mobile-workspace/docs/prd/PRD-006-compatibility-testing.md`
- `t1pal-mobile-workspace/docs/reference/ios-platform-quirks.md`
- `rag-nightscout-ecosystem-alignment/mapping/cross-project/terminology-matrix.md`
