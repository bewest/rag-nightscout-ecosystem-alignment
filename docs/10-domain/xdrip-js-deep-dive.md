# xdrip-js Deep Dive

> **Repository**: [xdrip-js/xdrip-js](https://github.com/xdrip-js/xdrip-js)  
> **Language**: Node.js / JavaScript  
> **Purpose**: BLE interface for Dexcom G5/G6 transmitters on Raspberry Pi  
> **Analysis Date**: 2026-01-29  
> **Source**: `externals/xdrip-js/`

## Executive Summary

xdrip-js is a Node.js library that provides direct Bluetooth Low Energy (BLE) communication with Dexcom G5 and G6 CGM transmitters. It enables Raspberry Pi-based CGM receivers for OpenAPS closed-loop systems and Nightscout data logging. The library is foundational to the DIY diabetes technology ecosystem, offering protocol-level access that bypasses Dexcom's proprietary receiver and mobile apps.

### Key Characteristics

| Aspect | Detail |
|--------|--------|
| **Primary Use Case** | Raspberry Pi CGM receiver for OpenAPS |
| **Transmitter Support** | Dexcom G5, G6, G6+ (partial Anubis) |
| **BLE Library** | noble (custom fork) |
| **Authentication** | AES-128-ECB challenge-response |
| **Nightscout Integration** | Via client apps (Lookout, Logger) |

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        xdrip-js Data Flow                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────────┐ │
│  │ Dexcom G5/G6 │────▶│  xdrip-js    │────▶│       Client App             │ │
│  │ Transmitter  │ BLE │  (library)   │     │  (Lookout or Logger)         │ │
│  └──────────────┘     └──────────────┘     └──────────────┬───────────────┘ │
│                                                            │                 │
│                         ┌──────────────────────────────────┼─────────────┐   │
│                         ▼                                  ▼             ▼   │
│                 ┌───────────────┐              ┌─────────────┐  ┌─────────┐  │
│                 │   Nightscout  │              │   OpenAPS   │  │  Loop   │  │
│                 │   (MongoDB)   │              │  (oref0/1)  │  │  (alt)  │  │
│                 └───────────────┘              └──────┬──────┘  └─────────┘  │
│                                                       │                      │
│                                                       ▼                      │
│                                              ┌─────────────────┐             │
│                                              │  Insulin Pump   │             │
│                                              │  (via RileyLink)│             │
│                                              └─────────────────┘             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Transmitter Class (`lib/transmitter.js`)

The main entry point, extending EventEmitter for async event-driven architecture.

**Key Features**:
- Automatic G5/G6/G6+ detection based on serial number prefix
- Command queue processing (calibration, session start/stop, reset)
- Backfill data retrieval for gap-filling

**Transmitter Type Detection** (lines 394-396):
```javascript
this.g6Transmitter = (id.substr(0, 1) === '8');
const g6Type = id.substr(0, 2);
this.g6PlusTransmitter = (g6Type === '8G' || g6Type === '8H' || 
                          g6Type === '8J' || g6Type === '8L' || g6Type === '8R');
```

| Serial Prefix | Transmitter Type |
|---------------|------------------|
| `4xxxxx` | G5 |
| `8xxxxx` | G6 |
| `8G`, `8H`, `8J`, `8L`, `8R` | G6+ |

### 2. Bluetooth Manager (`lib/bluetooth-manager.js`)

Abstracts noble BLE library with promise-based API and exclusive operation handling.

**Key Features**:
- JealousPromise pattern prevents concurrent BLE operations
- Automatic reconnection on disconnect (up to 25 retries)
- Service/characteristic discovery and caching

### 3. Message Protocol (`lib/messages/`)

Complete implementation of Dexcom's proprietary BLE protocol.

| Category | Opcodes | Purpose |
|----------|---------|---------|
| Authentication | 0x01-0x08 | AES-128 challenge-response |
| Control | 0x09, 0x20-0x53 | Commands and responses |
| Glucose | 0x30/0x31 (G5), 0x4E/0x4F (G6) | SGV readings |
| Backfill | 0x50/0x51 | Historical data |

### 4. Glucose Class (`lib/glucose.js`)

Combines data from multiple messages into a single event payload.

**Key Fields**:
- `glucose`: Calibrated SGV in mg/dL (null if unreliable)
- `trend`: Rate of change in mg/dL per 10 minutes
- `filtered`/`unfiltered`: Raw sensor values × 1000
- `readDate`: JavaScript Date of reading
- `rssi`: BLE signal strength

## Nightscout Integration Points

xdrip-js does **not** directly upload to Nightscout. Client applications handle the upload:

### Lookout (Primary Client)

[xdrip-js/Lookout](https://github.com/xdrip-js/Lookout) provides:
- Nightscout upload via REST API
- OpenAPS integration (glucose file writing)
- Pump communication coordination

### Expected Nightscout Entry Format

When Lookout uploads to Nightscout, it transforms xdrip-js glucose events:

| xdrip-js Field | Nightscout Field | Notes |
|----------------|------------------|-------|
| `glucose` | `sgv` | mg/dL value |
| `trend` | `direction` | Requires conversion (see below) |
| `readDate` | `dateString`, `date` | ISO 8601 / epoch ms |
| `unfiltered` | `unfiltered` | Raw × 1000 |
| `filtered` | `filtered` | Raw × 1000 |
| `rssi` | `rssi` | Signal strength |
| - | `device` | Set to `"xdrip-js"` or similar |

### Trend to Direction Mapping

xdrip-js provides trend as mg/dL per 10 minutes. Nightscout expects string direction:

| Trend Range | Nightscout Direction |
|-------------|---------------------|
| > 3.0 | DoubleUp |
| 2.0 to 3.0 | SingleUp |
| 1.0 to 2.0 | FortyFiveUp |
| -1.0 to 1.0 | Flat |
| -2.0 to -1.0 | FortyFiveDown |
| -3.0 to -2.0 | SingleDown |
| < -3.0 | DoubleDown |

**Gap**: This mapping is not standardized and varies between client implementations.

## BLE Protocol Summary

### Authentication Flow

```
Client                              Transmitter
  │                                      │
  │  AuthRequestTx (0x01)                │
  │  [singleUseToken]                    │
  │─────────────────────────────────────▶│
  │                                      │
  │  AuthChallengeRx (0x03)              │
  │  [tokenHash, challenge]              │
  │◀─────────────────────────────────────│
  │                                      │
  │  Verify tokenHash                    │
  │  Compute challengeHash               │
  │                                      │
  │  AuthChallengeTx (0x04)              │
  │  [challengeHash]                     │
  │─────────────────────────────────────▶│
  │                                      │
  │  AuthStatusRx (0x05)                 │
  │  [authenticated, bonded]             │
  │◀─────────────────────────────────────│
```

**Source**: `lib/transmitter.js:52-122`

### Encryption

```javascript
function encrypt(buffer, id) {
  const algorithm = 'aes-128-ecb';
  const cipher = crypto.createCipheriv(algorithm, `00${id}00${id}`, '');
  const encrypted = Buffer.concat([cipher.update(buffer), cipher.final()]);
  return encrypted;
}
```

Key derivation: Transmitter ID padded to 16 bytes (`00${id}00${id}`).

## Calibration State Machine

The library tracks sensor session state via the `state` field:

| State | Code | Glucose Reliable? | Can Calibrate? |
|-------|------|-------------------|----------------|
| Warmup | 0x02 | No | No |
| First Cal Needed | 0x04 | No | Yes |
| Second Cal Needed | 0x05 | No | Yes |
| OK | 0x06 | **Yes** | Yes |
| Need Calibration | 0x07 | **Yes** | Yes |
| Session Expired | 0x0F | No | No |

**Source**: `lib/calibration-state.js`

## Test Coverage

The project has unit tests but no integration tests:

```
test/
├── test-auth-status-rx-message.js
├── test-backfill-parser.js
├── test-backfill-tx-message.js
├── test-glucose.js
├── test-glucose-rx-message.js
├── test-sensor-rx-message.js
├── test-transmitter.js
└── test-version.js
```

**Test Command**: `npm test` (runs eslint + mocha)

## Dependencies

| Dependency | Version | Purpose |
|------------|---------|---------|
| `noble` | xdrip-js fork | BLE communication |
| `crc` | ^3.4.4 | CRC-16 XMODEM validation |
| `debug` | ^4.1.0 | Debug logging |
| `uuid` | ^3.0.1 | UUID generation |

**Notable**: Uses a forked noble for Raspberry Pi compatibility.

## Limitations and Gaps

### GAP-XDRIPJS-001: No G7 Support

**Description**: xdrip-js only supports Dexcom G5 and G6 transmitters. G7 uses J-PAKE authentication which is not implemented.

**Affected Systems**: xdrip-js, Lookout, OpenAPS rigs using xdrip-js

**Impact**:
- Users with G7 cannot use xdrip-js-based solutions
- Forces migration to xDrip+ on Android or Dexcom ONE
- Limits longevity of Raspberry Pi-based CGM receivers

**Remediation**: Implement J-PAKE authentication per GAP-G7-001. Complex due to Diffie-Hellman key exchange.

**Related**: GAP-CGM-002

---

### GAP-XDRIPJS-002: Deprecated BLE Library (noble)

**Description**: The project depends on a forked version of noble, which is no longer maintained. The npm noble package was last updated in 2018.

**Affected Systems**: xdrip-js, any Node.js BLE application

**Impact**:
- Compatibility issues with newer Bluetooth stacks
- Security vulnerabilities in unmaintained code
- Installation difficulties on modern Node.js versions

**Source**: `package.json:18` - `"noble": "xdrip-js/noble"`

**Remediation**: Migrate to @abandonware/noble or noble-winrt, or rewrite using node-ble.

---

### GAP-XDRIPJS-003: No Direct Nightscout Integration

**Description**: xdrip-js is a library only; it does not upload to Nightscout directly. Users must use Lookout or Logger, adding complexity.

**Affected Systems**: xdrip-js users

**Impact**:
- Additional software layer required
- Lookout/Logger may have their own bugs
- No standardized upload format

**Remediation**: Add optional Nightscout uploader to xdrip-js, or document standard upload format.

---

### GAP-XDRIPJS-004: Trend-to-Direction Mapping Not Standardized

**Description**: xdrip-js provides numeric trend (mg/dL per 10 min), but Nightscout expects string direction. The conversion thresholds vary between implementations.

**Affected Systems**: xdrip-js → Nightscout data flow

**Impact**:
- Inconsistent trend arrows across clients
- No authoritative mapping table
- Potential for clinical confusion

**Source**: Not defined in xdrip-js; left to client apps

**Remediation**: Define standard mapping in shared constants or Nightscout spec.

---

## Cross-Project Comparison

### xdrip-js vs xDrip+ vs xDrip4iOS

| Feature | xdrip-js | xDrip+ | xDrip4iOS |
|---------|----------|--------|-----------|
| Platform | Raspberry Pi | Android | iOS |
| Language | Node.js | Java/Kotlin | Swift |
| G5/G6 Support | ✅ | ✅ | ✅ |
| G7 Support | ❌ | ✅ | ✅ |
| Libre Support | ❌ | ✅ | ✅ |
| Direct NS Upload | ❌ | ✅ | ✅ |
| Calibration | ✅ | ✅ | ✅ |
| Backfill | ✅ | ✅ | ✅ |

### Authentication Comparison

| Aspect | xdrip-js | DiaBLE | xDrip+ |
|--------|----------|--------|--------|
| G5/G6 Auth | AES-128-ECB | AES-128-ECB | AES-128-ECB |
| G7 Auth | ❌ | J-PAKE | J-PAKE |
| Key Derivation | `00${id}00${id}` | `00${id}00${id}` | Same |

## Recommendations

1. **Migrate BLE library** - Replace noble fork with maintained alternative
2. **Add G7 J-PAKE support** - Follow DiaBLE implementation pattern
3. **Standardize trend mapping** - Document in Nightscout spec
4. **Add optional NS uploader** - Reduce dependency on Lookout

## Related Documentation

- [xdrip-js BLE Protocol](../../mapping/xdrip-js/ble-protocol.md) - Complete message reference
- [xdrip-js Data Models](../../mapping/xdrip-js/data-models.md) - Data structures
- [Dexcom BLE Protocol Deep Dive](dexcom-ble-protocol-deep-dive.md) - Cross-project comparison
- [CGM Sources Gaps](../../traceability/cgm-sources-gaps.md) - GAP-CGM-002

## Source Files Referenced

| File | Purpose |
|------|---------|
| `externals/xdrip-js/lib/transmitter.js` | Main class, authentication, message handling |
| `externals/xdrip-js/lib/bluetooth-manager.js` | BLE abstraction layer |
| `externals/xdrip-js/lib/glucose.js` | Glucose data model |
| `externals/xdrip-js/lib/calibration-state.js` | Calibration state machine |
| `externals/xdrip-js/lib/messages/` | Protocol message implementations |
| `externals/xdrip-js/package.json` | Dependencies and metadata |
