# Swift Package Ecosystem Assessment

> **Backlog Item**: ios-mobile-platform.md (Swift Package Ecosystem Assessment)  
> **Date**: 2026-01-31  
> **Purpose**: Inventory submodules, assess SPM conversion feasibility

## Executive Summary

The iOS ecosystem primarily uses **git submodules** for code sharing, not Swift Package Manager (SPM). While LoopKit has an experimental Package.swift, it is explicitly marked as incomplete. Only LoopCaregiverKit fully uses SPM.

| Finding | Status |
|---------|--------|
| Primary sharing mechanism | Git submodules |
| SPM adoption | Minimal (1 of 8 apps) |
| Shared libraries | 10 between Loop/Trio |
| Fork burden | High (Trio maintains 11 forks) |
| SPM conversion feasibility | Medium-High effort |

---

## iOS App Inventory

### Build System Summary

| App | Build System | Submodules | Package.swift | Notes |
|-----|--------------|------------|---------------|-------|
| **Loop** | Xcode Workspace | 20 | Experimental | LoopKit SPM incomplete |
| **Trio** | Xcode Workspace | 11 | Experimental | loopandlearn forks |
| **xDrip4iOS** | Xcode Project | 0 | No | Standalone |
| **DiaBLE** | Xcode Project | 0 | Playground only | SwiftUI standalone |
| **LoopFollow** | Xcode Project | 0 | BuildTools only | Standalone |
| **LoopCaregiver** | Xcode Workspace | 0 | **Yes (SPM)** | Uses SPM properly |
| **Nightguard** | Xcode Project | 0 | No | Standalone |
| **Spike** | (iOS, not in externals) | - | - | Separate ecosystem |

---

## Submodule Analysis

### LoopWorkspace (20 submodules)

All from `github.com/LoopKit/`:

| Submodule | Purpose |
|-----------|---------|
| Loop | Main app |
| LoopKit | Core framework |
| LoopKitUI | UI components |
| CGMBLEKit | CGM Bluetooth |
| G7SensorKit | Dexcom G7 |
| OmniBLE | Omnipod DASH BLE |
| OmniKit | Omnipod protocol |
| MinimedKit | Medtronic pumps |
| RileyLinkKit | RileyLink radio |
| LibreTransmitter | Libre CGM |
| dexcom-share-client-swift | Dexcom Share API |
| NightscoutService | Nightscout upload |
| NightscoutRemoteCGM | Remote CGM |
| TidepoolService | Tidepool upload |
| LoopOnboarding | Onboarding flows |
| LoopSupport | Support utilities |
| AmplitudeService | Analytics |
| LogglyService | Logging |
| MixpanelService | Analytics |
| TrueTime.swift | NTP time sync |
| Minizip | Compression |

### Trio (11 submodules)

All from `github.com/loopandlearn/` with `trio` branch:

| Submodule | Fork Of |
|-----------|---------|
| LoopKit | LoopKit/LoopKit |
| CGMBLEKit | LoopKit/CGMBLEKit |
| G7SensorKit | LoopKit/G7SensorKit |
| OmniBLE | LoopKit/OmniBLE |
| OmniKit | LoopKit/OmniKit |
| MinimedKit | LoopKit/MinimedKit |
| RileyLinkKit | LoopKit/RileyLinkKit |
| LibreTransmitter | LoopKit/LibreTransmitter |
| dexcom-share-client-swift | LoopKit/dexcom-share-client-swift |
| TidepoolService | LoopKit/TidepoolService |
| DanaKit | (Trio-specific) |

### Shared Libraries (10 common)

These are shared between Loop and Trio via forked submodules:

1. **LoopKit** - Core diabetes types, algorithms
2. **CGMBLEKit** - CGM Bluetooth communication
3. **G7SensorKit** - Dexcom G7 protocol
4. **OmniBLE** - Omnipod DASH Bluetooth
5. **OmniKit** - Omnipod protocol
6. **MinimedKit** - Medtronic pump protocol
7. **RileyLinkKit** - RileyLink radio bridge
8. **LibreTransmitter** - FreeStyle Libre
9. **dexcom-share-client-swift** - Dexcom Share API
10. **TidepoolService** - Tidepool integration

---

## SPM Status

### LoopKit Package.swift

**Status**: ⚠️ **Incomplete - Do Not Use**

```swift
// *************** Not complete yet, do not expect this to work! ***********************
// There are issues with how test fixtures are copied into the bundle, and then referenced,
// and other issues, largely around accessing bundle resources, and probably others not yet
// discovered, as this is not being used as a swift package from any actual project yet.
```

**Issues Documented**:
- Test fixture bundle resource access
- Bundle resource path resolution
- Not used from any actual project

### LoopCaregiverKit Package.swift

**Status**: ✅ **Working SPM**

```swift
dependencies: [
    .package(url: "https://github.com/LoopKit/LoopKit.git", branch: "dev"),
    .package(url: "https://github.com/gestrich/NightscoutKit.git", branch: "feature/2023-07/bg/remote-commands"),
    .package(url: "https://github.com/mattrubin/OneTimePassword.git", branch: "develop")
]
```

**Key Observation**: LoopCaregiver successfully uses SPM for:
- LoopKit (via SPM, not submodule)
- NightscoutKit (gestrich fork)
- OneTimePassword (OTP for remote commands)

---

## Fork Burden Analysis

### Trio Maintenance Overhead

Trio maintains **11 forks** in `loopandlearn` org with `trio` branches:

| Burden Type | Impact |
|-------------|--------|
| Merge conflicts | Must merge upstream changes manually |
| Divergence risk | Trio-specific changes may conflict |
| CI duplication | Each fork needs separate CI |
| Contributor confusion | Which repo to PR against? |

### Estimated Code Duplication

Based on submodule counts:
- Loop: 20 submodules × ~5,000 LOC avg = ~100,000 LOC
- Trio: 11 forks with ~10% divergence = ~10,000 LOC unique
- Overlap: ~90% code shared between Loop and Trio

---

## SPM Conversion Feasibility

### Blockers

| Blocker | Severity | Description |
|---------|----------|-------------|
| Bundle resources | High | LoopKit tests can't access fixtures |
| Mixed Swift/ObjC | Medium | Some libraries have ObjC bridging |
| Xcode project coupling | Medium | App targets reference submodule paths |
| Transitive dependencies | Low | SwiftCharts, etc. need version pinning |

### Conversion Path

#### Phase 1: Library SPM (Low Risk)
Convert standalone libraries with no resource dependencies:
- dexcom-share-client-swift
- TrueTime.swift
- Minizip

#### Phase 2: Core Framework (Medium Risk)
Fix LoopKit Package.swift resource issues:
- Use `.process()` instead of `.copy()` for resources
- Add `Bundle.module` accessors
- Test with LoopCaregiver as consumer

#### Phase 3: Device Libraries (High Risk)
Convert pump/CGM libraries:
- CGMBLEKit, G7SensorKit
- OmniBLE, OmniKit, MinimedKit
- Requires Bluetooth entitlement testing

#### Phase 4: App Integration (Very High Risk)
Migrate Loop/Trio to SPM workspace:
- Replace submodules with package dependencies
- Update CI/CD pipelines
- Coordinate with maintainers

---

## Recommendations

### Short Term (0-3 months)

1. **Fix LoopKit Package.swift** - Resolve resource bundle issues
2. **Document SPM patterns** - Use LoopCaregiverKit as reference
3. **Verify NightscoutKit** - gestrich fork works, document as model

### Medium Term (3-6 months)

4. **Convert 3 standalone libraries** - dexcom-share-client, TrueTime, Minizip
5. **Test with LoopCaregiver** - Validate SPM consumption works
6. **Propose SPM-first for new libraries** - DanaKit, future additions

### Long Term (6-12 months)

7. **Coordinate with LoopKit maintainers** - Propose SPM migration
8. **Prototype SPM workspace** - Loop or Trio as test bed
9. **Eliminate fork burden** - Trio uses SPM packages instead of forks

---

## Related Gaps

| Gap ID | Description |
|--------|-------------|
| GAP-IOS-001 | Submodule pattern creates fork burden |
| GAP-IOS-002 | No shared SDK for Nightscout operations |
| GAP-SPM-001 | LoopKit Package.swift incomplete (NEW) |
| GAP-SPM-002 | No SPM conversion roadmap (NEW) |

---

## References

- `externals/LoopWorkspace/.gitmodules` - Loop submodules
- `externals/Trio/.gitmodules` - Trio submodules
- `externals/LoopWorkspace/LoopKit/Package.swift` - Incomplete SPM
- `externals/LoopCaregiver/LoopCaregiverKit/Package.swift` - Working SPM
- `docs/sdqctl-proposals/nightscoutkit-swift-sdk-design.md` - SDK design
