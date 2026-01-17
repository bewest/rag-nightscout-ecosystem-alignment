# G7 Implementation Comparison

This document provides a comprehensive comparison of Dexcom G7 support across open-source diabetes projects, analyzing implementation completeness, authentication capabilities, and feature coverage.

## Table of Contents

- [Executive Summary](#executive-summary)
- [Project Overview](#project-overview)
- [Feature Matrix](#feature-matrix)
- [Authentication Comparison](#authentication-comparison)
- [Data Capabilities](#data-capabilities)
- [Source File Reference](#source-file-reference)
- [Blockers and Gaps](#blockers-and-gaps)
- [Recommendations](#recommendations)

---

## Executive Summary

### Key Finding

**xDrip Android and Juggluco are the only open-source projects with complete standalone G7 support.** Both implement J-PAKE authentication independently (xDrip via Java libkeks, Juggluco via native C++). All iOS projects require the official Dexcom app running in background to complete authentication.

### Quick Comparison

| Project | Platform | Standalone G7 | Auth Method | Maturity |
|---------|----------|---------------|-------------|----------|
| **xDrip** | Android | ✅ Yes | J-PAKE (libkeks) | Production |
| **Juggluco** | Android | ✅ Yes | J-PAKE (native C++) | Production |
| **DiaBLE** | iOS/watchOS | ❌ No | Eavesdrop only | Experimental |
| **G7SensorKit** | iOS | ❌ No | None (uses Dexcom) | Production |
| **xDrip4iOS** | iOS | ❌ No | Eavesdrop only | Production |
| **AAPS** | Android | 🔄 Indirect | Via xDrip broadcast | Production |

---

## Project Overview

### xDrip (Android)

**Repository:** `NightscoutFoundation/xDrip`

The most feature-complete G7 implementation with full standalone capability.

| Aspect | Details |
|--------|---------|
| **Language** | Java/Kotlin |
| **Auth Library** | `libkeks` (pure Java J-PAKE) |
| **BLE Stack** | RxAndroidBle |
| **G7 Support Since** | ~2023 |
| **Maintainer** | jamorham, Nightscout Foundation |

**Key Files:**
- `libkeks/src/main/java/jamorham/keks/` - J-PAKE implementation
- `app/src/main/java/com/eveningoutpost/dexdrip/cgm/dex/g7/` - G7 message parsers
- `app/src/main/java/com/eveningoutpost/dexdrip/g5model/Ob1G5StateMachine.java` - State machine

### Juggluco (Android)

**Repository:** `j-kaltes/Juggluco`

Independent G7 implementation with native C++ J-PAKE.

| Aspect | Details |
|--------|---------|
| **Language** | Kotlin/C++ |
| **Auth Library** | Native C++ (JNI) |
| **G7 Support Since** | ~2023 |
| **Maintainer** | j-kaltes |

**Key Files:**
- `Common/src/dex/java/tk/glucodata/DexGattCallback.java` - BLE handling
- `Common/src/main/cpp/dexcom/` - Native authentication code

### DiaBLE (iOS/watchOS)

**Repository:** `gui-dos/DiaBLE`

Research-focused iOS app with extensive protocol documentation.

| Aspect | Details |
|--------|---------|
| **Language** | Swift |
| **Auth Library** | None (traces only) |
| **G7 Support Since** | 2024 (partial) |
| **Maintainer** | gui-dos |

**Key Files:**
- `DiaBLE/DexcomG7.swift` - Opcode definitions, BLE traces
- `DiaBLE/Dexcom.swift` - Base transmitter class

**Status:** Has the best protocol documentation from BLE traces, but no J-PAKE implementation. Uses "Test mode" to eavesdrop when Dexcom app is running.

### G7SensorKit (Loop/Trio)

**Repository:** `LoopKit/G7SensorKit`

CGM manager plugin for Loop ecosystem.

| Aspect | Details |
|--------|---------|
| **Language** | Swift |
| **Auth Library** | None |
| **G7 Support Since** | 2022 |
| **Maintainer** | LoopKit |

**Key Files:**
- `G7SensorKit/Messages/G7GlucoseMessage.swift` - Glucose parsing
- `G7SensorKit/Messages/G7Opcode.swift` - Limited opcode enum
- `G7SensorKit/G7CGMManager/G7BackfillMessage.swift` - Backfill parsing

**Status:** Only implements glucose/backfill parsing. Requires Dexcom app for all authentication. Described by DiaBLE maintainer as "really limited and poorly documented."

### xDrip4iOS

**Repository:** `JohanDegraeve/xdripswift`

iOS port of xDrip concepts.

| Aspect | Details |
|--------|---------|
| **Language** | Swift |
| **Auth Library** | None |
| **G7 Support Since** | 2023 |
| **Maintainer** | Johan Degraeve |

**Key Files:**
- `xdrip/BluetoothPeripheral/CGM/Dexcom/G7/DexcomG7+BluetoothPeripheral.swift`
- `xdrip/BluetoothTransmitter/CGM/Dexcom/Generic/DexcomG7*.swift`

**Status:** Uses Dexcom app for authentication. Supports glucose reading and backfill once authenticated.

### AAPS (AndroidAPS)

**Repository:** `nightscout/AndroidAPS`

Closed-loop insulin delivery system.

| Aspect | Details |
|--------|---------|
| **Language** | Kotlin |
| **G7 Support** | Indirect (via xDrip) |
| **Auth Library** | N/A |
| **Maintainer** | milos, OpenAPS contributors |

**Key Files:**
- `plugins/source/src/main/kotlin/app/aaps/plugins/source/DexcomPlugin.kt`

**Status:** Receives G7 data via xDrip broadcast or Dexcom companion app broadcast. No direct G7 BLE support.

---

## Feature Matrix

### Authentication Phases

| Phase | xDrip | Juggluco | DiaBLE | G7SensorKit | xDrip4iOS |
|-------|-------|----------|--------|-------------|-----------|
| J-PAKE Round 0 | ✅ | ✅ | 📝 | ❌ | ❌ |
| J-PAKE Round 1 | ✅ | ✅ | 📝 | ❌ | ❌ |
| J-PAKE Round 2 | ✅ | ✅ | 📝 | ❌ | ❌ |
| Traditional Auth (0x02-0x05) | ✅ | ✅ | 📝 | ❌ | ❌ |
| Certificate Exchange (0x0B) | ✅ | ✅ | 📝 | ❌ | ❌ |
| Proof of Possession (0x0C) | ✅ | ✅ | 📝 | ❌ | ❌ |
| Bonding (0x07-0x08) | ✅ | ✅ | 📝 | ❌ | ❌ |

**Legend:**
- ✅ Implemented
- 📝 Documented/traced but not implemented
- ❌ Not implemented

### Data Operations

| Operation | xDrip | Juggluco | DiaBLE | G7SensorKit | xDrip4iOS |
|-----------|-------|----------|--------|-------------|-----------|
| Read Glucose (0x4E) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Request Backfill (0x59) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Parse Backfill Stream | ✅ | ✅ | ✅ | ✅ | ✅ |
| Battery Status (0x22) | ✅ | ✅ | ✅ | ❌ | ✅ |
| Transmitter Version (0x4A) | ✅ | ✅ | ✅ | ❌ | ✅ |
| Extended Version (0x52) | ✅ | ✅ | ✅ | ❌ | ✅ |
| Calibration (0x32/0x34) | ✅ | 🔄 | 🔄 | ❌ | ❌ |
| Stop Session (0x28) | ✅ | ✅ | 📝 | ❌ | ❌ |
| Encryption Info (0x38) | ✅ | 🔄 | 🔄 | ❌ | ❌ |
| BLE Control (0xEA) | ✅ | ✅ | ✅ | ❌ | ❌ |

**Legend:**
- ✅ Full support
- 🔄 Partial/read-only
- 📝 Documented only
- ❌ Not implemented

### Operational Modes

| Mode | xDrip | Juggluco | DiaBLE | G7SensorKit | xDrip4iOS |
|------|-------|----------|--------|-------------|-----------|
| Standalone (no Dexcom app) | ✅ | ✅ | ❌ | ❌ | ❌ |
| Parallel with Dexcom app | ✅ | ✅ | ✅ | ✅ | ✅ |
| Eavesdrop/Test mode | ✅ | ❌ | ✅ | ❌ | ✅ |
| Direct-to-Watch | ✅ | ❌ | 📝 | ❌ | ❌ |

---

## Authentication Comparison

### xDrip libkeks

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                      xDrip G7 Authentication                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   Plugin    │───▶│   Context   │◀───│   Umbilical │         │
│  │  Interface  │    │   (State)   │    │    (BLE)    │         │
│  └─────────────┘    └──────┬──────┘    └─────────────┘         │
│                            │                                    │
│         ┌──────────────────┼──────────────────┐                │
│         ▼                  ▼                  ▼                │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │    Calc     │    │   Packet    │    │    Curve    │         │
│  │  (J-PAKE)   │    │ (Serialize) │    │  (secp256r1)│         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                                                                  │
│  Dependencies: BouncyCastle (EC), SHA256, AES                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Strengths:**
- Pure Java implementation (no native code)
- Well-structured modular design
- Extensive logging for debugging
- Production-proven

**Weaknesses:**
- BouncyCastle dependency adds ~2MB
- Not directly portable to iOS

### Juggluco Native

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                    Juggluco G7 Authentication                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Kotlin Layer                          │    │
│  │  DexGattCallback.java - BLE event handling               │    │
│  └────────────────────────────┬────────────────────────────┘    │
│                               │ JNI                             │
│  ┌────────────────────────────▼────────────────────────────┐    │
│  │                    C++ Layer                             │    │
│  │  Common/src/main/cpp/dexcom/                            │    │
│  │  - J-PAKE implementation                                 │    │
│  │  - Elliptic curve operations                            │    │
│  │  - Certificate handling                                  │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Dependencies: Native crypto, minimal footprint                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Strengths:**
- Smaller binary size (native crypto)
- Potentially faster EC operations
- Independent implementation (validates xDrip)

**Weaknesses:**
- JNI complexity
- Less portable
- Harder to debug

### iOS Projects (None Implemented)

All iOS projects lack J-PAKE authentication:

```
┌─────────────────────────────────────────────────────────────────┐
│                    iOS G7 Authentication Gap                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Current Approach:                                               │
│                                                                  │
│  ┌─────────────┐         ┌─────────────┐         ┌───────────┐ │
│  │ Dexcom App  │────────▶│   Sensor    │◀────────│  DIY App  │ │
│  │ (Handles    │ Auth    │             │ Glucose │ (Listens) │ │
│  │  J-PAKE)    │         │             │ Only    │           │ │
│  └─────────────┘         └─────────────┘         └───────────┘ │
│                                                                  │
│  Required for Standalone:                                        │
│                                                                  │
│  - Port libkeks Calc.java → Swift                               │
│  - Implement EC point arithmetic (CryptoKit limitation)         │
│  - Handle certificate exchange                                   │
│  - Implement proof of possession (ECDSA)                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Source File Reference

### xDrip Android

| File | Lines | Purpose |
|------|-------|---------|
| `libkeks/Calc.java` | ~180 | J-PAKE core calculations |
| `libkeks/Context.java` | ~90 | Authentication state |
| `libkeks/Curve.java` | ~40 | EC curve parameters |
| `libkeks/Packet.java` | ~75 | Packet serialization |
| `libkeks/DSAChallenger.java` | ~60 | ECDSA signing |
| `libkeks/message/*.java` | ~150 | Message types |
| `cgm/dex/g7/EGlucoseRxMessage.java` | ~110 | Glucose parsing |
| `cgm/dex/g7/BackfillControlRx.java` | ~80 | Backfill handling |
| `g5model/Ob1G5StateMachine.java` | ~2200 | Full state machine |

### DiaBLE

| File | Lines | Purpose |
|------|-------|---------|
| `DexcomG7.swift` | ~800 | Opcodes, BLE traces, parsing |
| `Dexcom.swift` | ~600 | Base transmitter, algorithm states |

### G7SensorKit

| File | Lines | Purpose |
|------|-------|---------|
| `G7GlucoseMessage.swift` | ~130 | Glucose message parsing |
| `G7BackfillMessage.swift` | ~100 | Backfill parsing |
| `G7Opcode.swift` | ~20 | Limited opcode enum (6 opcodes) |
| `G7BluetoothManager.swift` | ~400 | BLE management |

### xDrip4iOS

| File | Lines | Purpose |
|------|-------|---------|
| `DexcomG7+BluetoothPeripheral.swift` | ~150 | G7 peripheral handling |
| `DexcomG7GlucoseDataRxMessage.swift` | ~80 | Glucose message |
| `DexcomG7BackfillMessage.swift` | ~60 | Backfill message |

---

## Blockers and Gaps

### GAP-G7-001: No iOS J-PAKE Implementation

**Severity:** Critical  
**Affected Projects:** DiaBLE, G7SensorKit, xDrip4iOS  
**Description:** No pure Swift J-PAKE implementation exists. CryptoKit doesn't expose required EC point arithmetic.

**Potential Solutions:**
1. Port xDrip libkeks to Swift using BigInt library
2. Wrap mbedtls via Objective-C bridging
3. Use Security framework for raw EC operations

### GAP-G7-002: Certificate Exchange Undocumented

**Severity:** High  
**Affected Projects:** All iOS  
**Description:** Certificate structure and validation logic not fully reverse-engineered.

**Potential Solutions:**
1. Capture more BLE traces with known sensor codes
2. Decompile Dexcom iOS SDK

### GAP-G7-003: G7SensorKit Minimal Opcode Coverage

**Severity:** Medium  
**Affected Projects:** G7SensorKit (Loop/Trio)  
**Description:** Only 6 opcodes defined vs 15+ known opcodes.

**Impact:** No battery status, calibration, version info available.

### GAP-G7-004: Party ID Values Unknown

**Severity:** Medium  
**Affected Projects:** Any new implementation  
**Description:** Exact byte values for "alice" and "bob" party IDs in ZKP not documented.

---

## Recommendations

### For iOS Developers

1. **Start with xDrip libkeks port**
   - Clear, well-documented Java code
   - Modular structure aids porting
   - Use BigInt Swift library for modular arithmetic

2. **Use DiaBLE as protocol reference**
   - Best opcode documentation
   - BLE trace examples
   - Algorithm state definitions

3. **Validate against xDrip behavior**
   - Capture xDrip ↔ sensor traffic
   - Compare packet structures
   - Verify shared key derivation

### For Android Developers

1. **Use xDrip libkeks directly**
   - Production-proven
   - Well-maintained
   - Or reference Juggluco for alternative implementation

### For Researchers

1. **Document certificate exchange**
   - Capture full pairing sequences
   - Identify certificate structure
   - Map to X.509 or custom format

2. **Publish test vectors**
   - Known password → expected packets
   - Shared key derivation examples
   - Challenge-response pairs

---

## Cross-References

- [G7 Protocol Specification](../../docs/10-domain/g7-protocol-specification.md)
- [G7 J-PAKE Implementation Guide](../../docs/10-domain/g7-jpake-implementation-guide.md)
- [DiaBLE CGM Transmitters](../diable/cgm-transmitters.md)
- [xDrip Android Data Sources](../xdrip-android/data-sources.md)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial comparison from cross-project analysis |
