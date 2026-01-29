# Libre 3 Protocol Gap Analysis

> **Date**: 2026-01-29  
> **Status**: Analysis Complete  
> **Focus**: "Eavesdrop only" limitations vs Libre 1/2

---

## Executive Summary

| Aspect | Libre 1 | Libre 2 | Libre 3 |
|--------|---------|---------|---------|
| **NFC Read** | ✅ Direct | ✅ Direct | ⚠️ Limited |
| **BLE Direct** | ❌ None | ✅ With unlock | ❌ Encrypted |
| **Third-party BLE** | N/A | ✅ Possible | ❌ Eavesdrop only |
| **Encryption** | None | AES-128 (cracked) | ECDH + AES (uncracked) |
| **Official app required** | No | No (with patch) | **Yes** |

**Key Finding**: Libre 3 uses uncracked ECDH cryptography. Third-party apps can only "eavesdrop" on data the official app has already decrypted and uploaded to LibreLinkUp.

---

## Protocol Comparison

### Libre 1 (Gen1)

- **NFC**: Direct read of FRAM memory (344 bytes)
- **BLE**: No native Bluetooth support
- **Third-party**: Full access via NFC scan
- **Data source**: Sensor directly

### Libre 2 (Gen2)

- **NFC**: Direct read + unlock command
- **BLE**: AES-128 encrypted stream
- **Third-party**: ✅ Fully supported
  - Encryption key derived from sensor UID + password
  - xDrip+, xdripswift, DiaBLE can read directly
- **Data source**: Sensor directly via BLE

### Libre 3

- **NFC**: Limited activation commands only
- **BLE**: ECDH + AES-256 encrypted
- **Third-party**: ❌ Cannot decrypt directly
  - Requires official app private keys
  - Keys embedded in `liblibre3extension.so`
- **Data source**: LibreLinkUp API (indirect)

---

## Libre 3 Security Architecture

### BLE Authentication Flow

```
Sensor                      Third-party App
   │                              │
   │◄──── Security Challenge ─────│
   │                              │
   │  (Requires ECDH private key  │
   │   from Abbott certificate)   │
   │                              │
   ╳  Cannot proceed without      │
      official app private key    │
```

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `liblibre3extension.so` | Trident APK | Native crypto library |
| `LIBRE3_APP_PRIVATE_KEYS` | Embedded | ECDH private keys |
| `LIBRE3_APP_CERTIFICATES_B` | Embedded | App certificates |
| `process1()` / `process2()` | Native | Encryption/decryption |

**Source**: `DiaBLE/Libre3.swift:1088`

### Security Commands

| Command | Code | Purpose |
|---------|------|---------|
| `CMD_AUTHORIZED` | 0x05 | Authorization complete |
| `CMD_AUTHORIZE_ECDSA` | 0x06 | ECDSA authorization |
| `CMD_AUTHORIZATION_CHALLENGE` | 0x07 | Challenge-response |
| `CMD_IV_AUTHENTICATED_SEND` | 0x0B | Authenticated data |

**Source**: `DiaBLE/Libre3.swift:366-372`

---

## Third-Party App Strategies

### DiaBLE (iOS)

**Approach**: Eavesdrop mode

```swift
// DiaBLE/Libre3.swift:725
if settings.userLevel < .test { // not eavesdropping on Trident
    send(securityCommand: .sendCertificate)
}
```

**Behavior**:
- In "test" mode, can observe BLE traffic
- Cannot independently authenticate
- Relies on official app running simultaneously

**Limitation**: Read-only observation of encrypted handshake

### xdripswift (iOS)

**Approach**: Heartbeat detection

```swift
// Libre3HeartBeatBluetoothTransmitter.swift
// wait for a second to allow the official app to upload to LibreView
// before triggering the heartbeat announcement to the delegate
DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
    self?.bluetoothTransmitterDelegate?.heartBeat()
}
```

**Behavior**:
- Detects BLE advertisement from Libre 3
- Triggers data fetch from LibreLinkUp API
- Does NOT read sensor directly

**Data Flow**:
```
Libre 3 → Official App → LibreView → LibreLinkUp API → xdripswift
```

### xDrip+ (Android)

**Finding**: No native Libre 3 support in current codebase.

- `DexCollectionType` includes: `LimiTTer`, `LibreAlarm`, `LibreWifi`, `LibreReceiver`
- No `Libre3` collection type found
- Relies on external bridges or Juggluco

### Juggluco (Android)

**Approach**: Extracted native library

- Uses `liblibre3extension.so` from official Trident app
- Wraps `processint()` and `processbar()` functions
- Can decrypt Libre 3 BLE data

**Legal/ethical concerns**: Uses Abbott proprietary code

**Source**: `DiaBLE/Libre3.swift:1088` references Juggluco implementation

---

## Data Access Comparison

| Method | Libre 2 | Libre 3 | Latency |
|--------|---------|---------|---------|
| Direct BLE | ✅ | ❌ | Real-time |
| NFC Scan | ✅ | ⚠️ Limited | Manual |
| LibreLinkUp API | ✅ | ✅ | 1-5 min delay |
| Eavesdrop (Juggluco) | N/A | ⚠️ | Real-time |

---

## Gaps Identified

### GAP-CGM-030: Libre 3 Direct BLE Access Blocked

**Description**: Libre 3 uses ECDH encryption that requires Abbott private keys. Third-party apps cannot decrypt BLE data without using proprietary libraries.

**Affected Systems**: DiaBLE, xDrip+, xdripswift, AAPS, Loop

**Impact**:
- Users must run official app
- Data delayed through LibreLinkUp
- No offline/direct sensor access

**Current Workarounds**:
1. LibreLinkUp API polling (1-5 min delay)
2. Juggluco with extracted native library (legal concerns)
3. Eavesdrop mode (requires official app running)

**Status**: Open - No known legal solution

### GAP-CGM-031: Libre 3 NFC Limited to Activation

**Description**: Unlike Libre 1/2, Libre 3 NFC cannot read glucose history. NFC is only used for initial activation and BLE PIN retrieval.

**Affected Systems**: All NFC-based readers

**Impact**:
- Cannot scan sensor for retrospective data
- Must rely on BLE (which is encrypted)

**Source**: `DiaBLE/Libre3.swift:832-848` - activation commands only

**Status**: Open - Hardware limitation

### GAP-CGM-032: LibreLinkUp API Dependency

**Description**: Third-party apps must use LibreLinkUp API as data source for Libre 3, creating dependency on Abbott cloud infrastructure.

**Affected Systems**: xdripswift, Nightscout bridges

**Impact**:
- Internet required for glucose data
- Subject to API changes/deprecation
- Privacy concerns (data through Abbott servers)
- Latency (1-5 minutes vs real-time)

**Status**: Open - Architectural limitation

---

## Implementation Status by App

| App | Libre 1 | Libre 2 | Libre 3 | Method |
|-----|---------|---------|---------|--------|
| **DiaBLE** | ✅ NFC | ✅ BLE | ⚠️ Eavesdrop | Direct + LibreLinkUp |
| **xdripswift** | ✅ NFC | ✅ BLE | ⚠️ Heartbeat | Direct + LibreLinkUp |
| **xDrip+** | ✅ NFC | ✅ BLE | ❌ None | Via external bridges |
| **Juggluco** | ✅ | ✅ | ✅ | Extracted native lib |
| **AAPS** | Via xDrip | Via xDrip | Via Juggluco | Indirect |
| **Loop** | N/A | N/A | N/A | iOS only, no Libre |

---

## Security Analysis

### Why Libre 2 Was Crackable

- AES-128 key derivation from known inputs (UID, password)
- Key exchange observable in BLE traffic
- Community reverse-engineered algorithm

### Why Libre 3 Is Not (Currently)

- ECDH requires private key (not derivable)
- Private keys embedded in signed APK
- Certificate chain validation
- No known cryptographic weakness

### Potential Future Approaches

1. **Key extraction**: From rooted device or APK analysis
2. **Protocol weakness**: Undiscovered vulnerability
3. **Abbott cooperation**: Unlikely but possible
4. **Hardware glitching**: Side-channel attacks on sensor

---

## Recommendations

### For Users

1. **Accept LibreLinkUp delay** - Most reliable method
2. **Avoid Juggluco** if concerned about legal/ethical issues
3. **Consider Libre 2** if real-time third-party access required
4. **Run official app** alongside third-party for eavesdrop mode

### For Developers

1. **Implement LibreLinkUp API** - Only legal data source
2. **Document limitations clearly** - Users need to understand delay
3. **Monitor for protocol changes** - Abbott may update security
4. **Do not distribute extracted libraries** - Legal risk

### For Ecosystem

1. **Standardize LibreLinkUp integration** across apps
2. **Document latency expectations** in user guides
3. **Track GAP-CGM-030/031/032** for future resolution
4. **Consider advocacy** for open CGM protocols

---

## Source Code References

| Component | File | Line | Key Finding |
|-----------|------|------|-------------|
| Eavesdrop logic | `DiaBLE/Libre3.swift` | 713-782 | TEST mode for observation |
| Security commands | `DiaBLE/Libre3.swift` | 366-372 | CMD_AUTHORIZE_* |
| Juggluco wrappers | `DiaBLE/Libre3.swift` | 1088 | Native lib reference |
| Heartbeat trigger | `Libre3HeartBeatBluetoothTransmitter.swift` | 75-80 | LibreLinkUp delay |
| BLE PIN retrieval | `DiaBLE/Libre3.swift` | 832-876 | NFC activation only |
| Security context | `DiaBLE/Libre3.swift` | 284-314 | BCSecurityContext |

---

## Cross-References

- [CGM Sources Gaps](../../traceability/cgm-sources-gaps.md)
- [DiaBLE Deep Dive](diable-libre-protocol-deep-dive.md)
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md)
