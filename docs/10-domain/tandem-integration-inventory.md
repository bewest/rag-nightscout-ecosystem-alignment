# Tandem Integration Inventory

> **Research Document** | Created: 2026-02-01
> **Source**: Ready Queue #6 (ECOSYSTEM-BACKLOG.md)
> **Focus**: Document Tandem/Control-IQ integration status across AID ecosystem

## Executive Summary

Tandem integration is **fundamentally different** from other pump integrations in the ecosystem. Unlike Omnipod/Medtronic which have direct BLE drivers in AAPS/Loop, Tandem uses a **cloud-bridge model** via tconnectsync.

| Integration Type | Apps | Status |
|------------------|------|--------|
| **Cloud Bridge** | tconnectsync, Nocturne | ✅ Full |
| **Pump Driver** | AAPS (type enum only) | ❌ No driver |
| **Data Display** | Loop, Nightscout | Read-only |
| **Direct BLE** | None | ❌ Not supported |

**Key Finding**: There is no open-source Control-IQ alternative. Tandem users cannot use AAPS/Loop/Trio as their AID controller.

---

## Integration Details

### tconnectsync (Primary Bridge)

**Location**: `externals/tconnectsync/`

**Architecture**: Python cloud-to-cloud sync

```
Tandem t:connect Cloud → tconnectsync → Nightscout API v1
```

**Codebase**: ~9,045 lines Python

**Pump Support**:
| Pump | Status |
|------|--------|
| t:slim X2 | ✅ Full support |
| t:slim G4 | ✅ Supported |
| t:flex | ⚠️ Limited |

**Data Types Synced**:
| t:connect Event | Nightscout eventType |
|-----------------|---------------------|
| Bolus | `Combo Bolus` |
| Temp Basal | `Temp Basal` |
| Basal Suspension | `Basal Suspension` |
| Site Change | `Site Change` |
| Pump Alarm | `Announcement` |
| CGM Alert | `Announcement` |
| Sensor Start | `Sensor Start` |
| Exercise Mode | `Exercise` |
| Sleep Mode | `Sleep` |
| CGM Reading | `sgv` (entries) |

**Authentication Methods**:
- OIDC/OAuth2 (recommended)
- Android app credentials
- Web form scraping (legacy)

**Key Files**:
- `tconnectsync/api/tandemsource.py` - OAuth2 authentication
- `tconnectsync/api/controliq.py` - Control-IQ therapy timeline
- `tconnectsync/sync/tandemsource/` - Data processors
- `tconnectsync/domain/` - Data models

**Features**:
- ✅ Bolus/basal synchronization
- ✅ Control-IQ activity mode sync (Exercise/Sleep)
- ✅ CGM data via pump (Dexcom G6/G7)
- ✅ Pump alarms and alerts
- ❌ No real-time sync (batch only)
- ❌ No API v3 support

**Existing Documentation**: `docs/10-domain/tconnectsync-deep-dive.md` (comprehensive)

---

### Nocturne TConnectSync Connector

**Location**: `externals/nocturne/src/Connectors/Nocturne.Connectors.TConnectSync/`

**Architecture**: Python connector wrapper for Nocturne

**Codebase**: ~150 lines Python

**Purpose**: Integrates tconnectsync into Nocturne's connector ecosystem

**Features**:
- ✅ Wraps tconnectsync API
- ✅ Normalizes to Nocturne data model
- ✅ Background polling

---

### AAPS (Android)

**Status**: ❌ **No pump driver**

**Evidence**:
- `PumpType.kt` defines `TANDEM_T_SLIM`, `TANDEM_T_SLIM_X2`, `TANDEM_T_FLEX`
- `ManufacturerType.kt` includes `Tandem`
- **No pump driver plugin** in `pump/` directory
- Type definitions exist for data import (via Nightscout), not control

**What This Means**:
- AAPS can display Tandem pump data imported from Nightscout
- AAPS cannot control Tandem pumps
- Users cannot use AAPS as AID controller with Tandem

---

### Loop (iOS)

**Status**: ❌ **No pump driver**

**Evidence**:
- Mentions of "tandem" in `BolusEntryViewModel.swift` relate to UI/UX comparisons
- No `TandemKit` or similar pump driver package
- No BLE protocol implementation

**What This Means**:
- Loop cannot control Tandem pumps
- Users must use Control-IQ (Tandem's built-in algorithm)

---

### Trio (iOS)

**Status**: ❌ **No pump driver**

Same as Loop - no Tandem pump driver exists.

---

### xDrip+ (Android)

**Status**: ❌ **No direct integration**

**Evidence**:
- No Tandem-specific code found
- CGM data comes directly from Dexcom, not via Tandem pump

---

### cgm-remote-monitor (Nightscout)

**Status**: ✅ **Read-only display**

**Evidence**:
- Displays data uploaded by tconnectsync
- Recognizes Tandem-specific eventTypes
- No direct t:connect API integration

---

## Why No Direct Tandem Driver?

### Technical Barriers

1. **Proprietary BLE Protocol**: Tandem pumps use encrypted, undocumented BLE
2. **Control-IQ Integration**: Algorithm is closed-source and integrated into pump firmware
3. **FDA Clearance**: Control-IQ is FDA-cleared; third-party control would void clearance
4. **No Reverse Engineering**: Unlike Medtronic/Omnipod, no community effort to reverse-engineer

### Ecosystem Difference

| Pump Family | Open-Source Control | Data Access |
|-------------|---------------------|-------------|
| Omnipod Dash/Eros | ✅ AAPS, Loop | BLE driver |
| Medtronic 5xx/7xx | ✅ AAPS, Loop | Radio driver |
| Dana-i/RS | ✅ AAPS | BLE driver |
| Tandem t:slim X2 | ❌ Control-IQ only | Cloud API only |

---

## Integration Matrix

| Feature | tconnectsync | Nocturne | AAPS | Loop | xDrip+ | Nightscout |
|---------|--------------|----------|------|------|--------|------------|
| **Read pump data** | ✅ | ✅ | Via NS | Via NS | ❌ | ✅ |
| **Read CGM** | ✅ | ✅ | Via NS | Via NS | Direct | ✅ |
| **Control pump** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Override Control-IQ** | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Activity modes** | ✅ | ✅ | Via NS | Via NS | ❌ | ✅ |
| **Real-time sync** | ❌ | ❌ | N/A | N/A | N/A | ❌ |

---

## Gaps Identified

### GAP-TANDEM-001: No Real-Time Sync

**Description**: tconnectsync uses batch polling, not real-time data streaming.

**Impact**: 
- Delay between pump events and Nightscout visibility
- Not suitable for time-critical monitoring

**Remediation**: 
t:connect API limitations; would require Tandem partnership for real-time access.

### GAP-TANDEM-002: No Open-Source AID Control

**Description**: Unlike Omnipod/Medtronic, Tandem pumps cannot be controlled by open-source AID.

**Impact**: 
- Tandem users locked into Control-IQ algorithm
- Cannot customize dosing parameters beyond Control-IQ settings

**Remediation**: 
Requires Tandem to open BLE protocol or provide control API (unlikely).

### GAP-TANDEM-003: API v3 Not Supported

**Description**: tconnectsync only uses Nightscout API v1.

**Impact**: 
- No UPSERT semantics (potential duplicates)
- No server-side validation
- No identifier-based sync

**Remediation**: 
Port tconnectsync Nightscout output to API v3.

### GAP-TANDEM-004: Limited Control-IQ Algorithm Data

**Description**: Control-IQ decision rationale not exposed in t:connect API.

**Impact**: 
- Cannot analyze why Control-IQ made specific decisions
- Harder to compare with open-source algorithms

**Remediation**: 
Tandem would need to expose algorithm internals (unlikely for proprietary IP).

---

## Comparison: Tandem vs Tidepool Integration

| Aspect | Tandem | Tidepool |
|--------|--------|----------|
| **Integration model** | Cloud bridge | Direct upload |
| **Primary tool** | tconnectsync | In-app integration |
| **Apps supported** | 1 (tconnectsync) | 5 (AAPS, Loop, Trio, xDrip+, Nocturne) |
| **Direction** | Read-only from pump | Upload to Tidepool |
| **Real-time** | No | No (batch) |
| **Open protocol** | No (Tandem proprietary) | Yes (Tidepool API) |

---

## Source Files Analyzed

| Component | Path | Lines |
|-----------|------|-------|
| tconnectsync | `externals/tconnectsync/` | ~9,045 |
| Nocturne connector | `externals/nocturne/src/Connectors/Nocturne.Connectors.TConnectSync/` | ~150 |
| AAPS pump types | `externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/pump/defs/` | Type enum only |

---

## Existing Documentation

| Document | Location |
|----------|----------|
| tconnectsync Deep Dive | `docs/10-domain/tconnectsync-deep-dive.md` |
| tconnectsync Field Mappings | `mapping/tconnectsync/README.md` |
| tconnectsync Models | `mapping/tconnectsync/models.md` |
| tconnectsync Treatments | `mapping/tconnectsync/treatments.md` |
| tconnectsync API | `mapping/tconnectsync/api.md` |
| Existing Gaps | GAP-TCONNECT-001/002/003 in connectors-gaps.md |

---

## References

- [tconnectsync GitHub](https://github.com/jwoglom/tconnectsync)
- [Tandem t:connect](https://www.tandemdiabetes.com/products/t-connect)
- [Control-IQ Technology](https://www.tandemdiabetes.com/products/control-iq)
