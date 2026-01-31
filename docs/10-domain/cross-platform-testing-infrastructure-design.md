# Cross-Platform Testing Infrastructure Design

> **Date**: 2026-01-31  
> **Status**: Complete  
> **Source**: ios-mobile-platform.md #4  
> **Gap Reference**: GAP-TEST-002 (No Swift validation on Linux)

---

## Executive Summary

This document designs the testing infrastructure for validating Swift/iOS code on Linux, enabling CI/CD pipelines without expensive macOS runners.

### Key Recommendations

| Component | Tool | Status |
|-----------|------|--------|
| **Swift on Linux** | swiftly + Swift 6.2 | ✅ Available |
| **iOS SDK on Linux** | xtool + Darwin SDK | ⚠️ Experimental |
| **Algorithm Testing** | Shared test vectors | 📋 Proposed |
| **BLE/CGM Mocking** | Protocol-based abstractions | 📋 Proposed |
| **CI Matrix** | GitHub Actions | 📋 Designed |

---

## 1. Current State

### 1.1 Existing Infrastructure

| Component | Status | Purpose |
|-----------|--------|---------|
| `conformance/runners/oref0-runner.js` | ✅ Implemented | JS algorithm validation (85 vectors) |
| Tree-sitter CLI | ✅ Installed | v0.26.3, JS/TS/Swift/Java/Kotlin |
| sourcekit-lsp | ✅ Available | Swift LSP on Linux |
| swiftly | ✅ Installed | Swift 6.2.3 on Linux |

### 1.2 Platform Capabilities

| Platform | JavaScript | Swift (syntax) | Swift (full) | Kotlin |
|----------|------------|----------------|--------------|--------|
| Linux | ✅ Full | ✅ Yes | ⚠️ xtool | ✅ Gradle |
| macOS | ✅ Full | ✅ Full | ✅ Xcode | ✅ Gradle |
| CI (ubuntu) | ✅ $0.008/min | ✅ Syntax only | ⚠️ Experimental | ✅ $0.008/min |
| CI (macos) | ✅ $0.08/min | ✅ Full | ✅ Full | ✅ $0.08/min |

**Cost Impact**: macOS runners are 10x more expensive than Linux.

---

## 2. xtool Evaluation

### 2.1 What is xtool?

[xtool](https://github.com/aspect-build/xtool) enables building iOS/macOS apps on Linux using extracted Darwin SDKs.

### 2.2 Tested Configuration

```yaml
# xtool.yml
sdk: iphoneos
configuration: debug
derived_data_path: xtool/.xtool-tmp
scheme: Trio
```

```swift
// Package.swift requirements
// swift-tools-version: 6.2
let swiftSettings: [SwiftSetting] = [
    .swiftLanguageMode(.v5),  // Critical for compatibility
]
platforms: [.iOS(.v26)]  // Must match SDK version
```

### 2.3 Conversion Effort

Based on `spm-cross-platform-proposal.md` Trio conversion:

| Issue | Files Affected | Fix |
|-------|----------------|-----|
| Missing `import Foundation` | ~200+ files | Add explicit imports |
| Internal symbols | ~100+ symbols | Change to `public` |
| Duplicate extensions | ~10 files | Delete duplicates |
| Swift 6 API changes | ~20 files | Use `Array()` initializer |
| `#Preview` macro | ~30 files | Comment out or wrap |
| Circular dependencies | Model module | Extract TrioShared |

### 2.4 xtool Viability Assessment

| Use Case | Viability | Notes |
|----------|-----------|-------|
| **Syntax validation** | ✅ Excellent | Tree-sitter + sourcekit-lsp |
| **Algorithm unit tests** | ✅ Good | Pure Swift, no iOS deps |
| **UI testing** | ❌ Not viable | Requires simulator |
| **BLE/CGM testing** | ⚠️ Partial | Needs mocks |
| **Full app build** | ⚠️ Experimental | Major refactoring needed |

**Recommendation**: Use xtool for algorithm-only packages, not full apps.

---

## 3. CI Matrix Design

### 3.1 Tiered Approach

```yaml
# .github/workflows/swift-tests.yml
name: Swift Testing Matrix

on: [push, pull_request]

jobs:
  # Tier 1: Fast, cheap - Linux syntax validation
  syntax-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: swift-actions/setup-swift@v2
        with:
          swift-version: "6.0"
      - name: Syntax Check
        run: swift build --target AlgorithmCore 2>&1 | head -100

  # Tier 2: Medium - Linux algorithm tests
  algorithm-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: swift-actions/setup-swift@v2
      - name: Run Algorithm Tests
        run: swift test --filter AlgorithmTests

  # Tier 3: Full - macOS only when needed
  full-build:
    runs-on: macos-14
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - name: Build and Test
        run: xcodebuild test -scheme Trio -destination 'platform=iOS Simulator,name=iPhone 15'
```

### 3.2 Cost Optimization

| Tier | Trigger | Runner | Est. Time | Est. Cost |
|------|---------|--------|-----------|-----------|
| 1 | Every push | ubuntu | 2 min | $0.016 |
| 2 | Every push | ubuntu | 5 min | $0.040 |
| 3 | PRs only | macos | 15 min | $1.200 |

**Monthly estimate (100 PRs, 500 pushes)**: ~$150 vs ~$1,500 if all macOS

---

## 4. Shared Test Vectors

### 4.1 Algorithm Test Vector Format

```yaml
# conformance/vectors/insulin-calculation.yaml
name: IOB Calculation
description: Test Insulin on Board calculation
algorithm: oref0/iob

vectors:
  - id: iob-001
    description: Single bolus 1 hour ago
    inputs:
      boluses:
        - timestamp: "2026-01-31T10:00:00Z"
          units: 5.0
      current_time: "2026-01-31T11:00:00Z"
      dia_hours: 5.0
    expected:
      iob: 3.2
      tolerance: 0.1
      
  - id: iob-002
    description: Multiple boluses, stacked
    inputs:
      boluses:
        - timestamp: "2026-01-31T10:00:00Z"
          units: 3.0
        - timestamp: "2026-01-31T10:30:00Z"
          units: 2.0
      current_time: "2026-01-31T11:00:00Z"
      dia_hours: 5.0
    expected:
      iob: 4.1
      tolerance: 0.1
```

### 4.2 Cross-Language Runner Architecture

```
conformance/
├── vectors/
│   ├── iob-calculation.yaml
│   ├── cob-calculation.yaml
│   ├── determine-basal.yaml
│   └── autosens.yaml
├── runners/
│   ├── oref0-runner.js          # ✅ Exists (85 vectors)
│   ├── trio-runner.swift        # 📋 Proposed
│   ├── loop-runner.swift        # 📋 Proposed
│   └── aaps-runner.kt           # 📋 Proposed
└── reports/
    └── algorithm-parity.md
```

### 4.3 Runner Interface (Swift)

```swift
// conformance/runners/trio-runner.swift
import Foundation

struct TestVector: Codable {
    let id: String
    let inputs: Inputs
    let expected: Expected
}

struct Inputs: Codable {
    let boluses: [Bolus]
    let currentTime: Date
    let diaHours: Double
}

struct Expected: Codable {
    let iob: Double
    let tolerance: Double
}

func runVectors(path: String) throws -> [TestResult] {
    let vectors = try loadVectors(from: path)
    return vectors.map { vector in
        let actual = calculateIOB(
            boluses: vector.inputs.boluses,
            at: vector.inputs.currentTime,
            dia: vector.inputs.diaHours
        )
        let passed = abs(actual - vector.expected.iob) <= vector.expected.tolerance
        return TestResult(id: vector.id, passed: passed, actual: actual)
    }
}
```

---

## 5. BLE/CGM Mock Infrastructure

### 5.1 Problem Statement

iOS apps rely on:
- CoreBluetooth for CGM/pump communication
- HealthKit for glucose storage
- Core Location for geofencing

These are unavailable on Linux.

### 5.2 Protocol-Based Abstraction

```swift
// Core abstraction layer
protocol BluetoothManagerProtocol {
    func startScanning()
    func connect(to peripheral: PeripheralProtocol)
    func write(data: Data, to characteristic: CharacteristicProtocol)
    var discoveredPeripherals: [PeripheralProtocol] { get }
}

protocol CGMManagerProtocol {
    var currentGlucose: GlucoseReading? { get }
    var glucoseHistory: [GlucoseReading] { get }
    func fetchLatest() async throws -> [GlucoseReading]
}

// Production implementation (iOS only)
#if canImport(CoreBluetooth)
class CoreBluetoothManager: BluetoothManagerProtocol {
    // Real CoreBluetooth implementation
}
#endif

// Mock implementation (Cross-platform)
class MockBluetoothManager: BluetoothManagerProtocol {
    var mockPeripherals: [MockPeripheral] = []
    var mockResponses: [Data] = []
    
    func startScanning() {
        // Return mock peripherals
    }
}
```

### 5.3 Test Fixture Pattern

```swift
// Tests/CGMTests/DexcomG7Tests.swift
import XCTest
@testable import CGMBLEKit

final class DexcomG7Tests: XCTestCase {
    var mockBLE: MockBluetoothManager!
    var manager: DexcomG7Manager!
    
    override func setUp() {
        mockBLE = MockBluetoothManager()
        manager = DexcomG7Manager(bluetooth: mockBLE)
    }
    
    func testParseGlucosePacket() {
        // Given: Mock BLE returns known glucose packet
        let glucosePacket = Data([0x01, 0x02, 0x64, 0x00]) // 100 mg/dL
        mockBLE.mockResponses = [glucosePacket]
        
        // When: Manager processes packet
        let reading = manager.parseGlucoseData(glucosePacket)
        
        // Then: Glucose value is correct
        XCTAssertEqual(reading?.glucose, 100)
    }
}
```

### 5.4 Mock Data Sources

| Data Source | Mock Pattern | Test Vectors |
|-------------|--------------|--------------|
| Dexcom G7 | BLE packet replay | `vectors/dexcom-g7-packets.yaml` |
| Libre 3 | NFC frame replay | `vectors/libre3-frames.yaml` |
| Omnipod | Command/response pairs | `vectors/omnipod-commands.yaml` |
| Dexcom Share | HTTP response mocks | `vectors/dexcom-share-responses.json` |

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Week 1)

- [ ] Create `conformance/vectors/` YAML schema
- [ ] Add 10 IOB/COB test vectors
- [ ] Port oref0-runner.js vectors to YAML format
- [ ] Document vector format in `conformance/README.md`

### Phase 2: Swift Runner (Week 2)

- [ ] Create `conformance/runners/trio-runner.swift`
- [ ] Extract algorithm-only code from Trio
- [ ] Create `AlgorithmCore` SPM package
- [ ] Run vectors on Linux CI

### Phase 3: Mock Infrastructure (Week 3)

- [ ] Define `BluetoothManagerProtocol`
- [ ] Create `MockBluetoothManager`
- [ ] Add BLE packet test fixtures
- [ ] Create example CGM tests

### Phase 4: CI Integration (Week 4)

- [ ] Add `.github/workflows/swift-tests.yml`
- [ ] Configure tiered testing
- [ ] Add algorithm parity report generation
- [ ] Document in CONTRIBUTING.md

---

## 7. Architecture Recommendation

### 7.1 Module Structure for Testability

```
NightscoutEcosystem/
├── AlgorithmCore/              # Pure Swift, no iOS deps
│   ├── Package.swift
│   ├── Sources/
│   │   ├── IOB.swift
│   │   ├── COB.swift
│   │   ├── DetermineBasal.swift
│   │   └── Autosens.swift
│   └── Tests/
│       └── AlgorithmCoreTests/
│
├── DeviceAbstractions/         # Protocols only
│   ├── Package.swift
│   └── Sources/
│       ├── BluetoothManagerProtocol.swift
│       ├── CGMManagerProtocol.swift
│       └── PumpManagerProtocol.swift
│
├── DeviceMocks/                # Test doubles
│   ├── Package.swift
│   └── Sources/
│       ├── MockBluetoothManager.swift
│       └── MockCGMManager.swift
│
└── TrioApp/                    # Full iOS app
    └── (uses all above)
```

### 7.2 Package Dependencies

```swift
// AlgorithmCore/Package.swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AlgorithmCore",
    platforms: [.iOS(.v15), .macOS(.v12)],
    products: [
        .library(name: "AlgorithmCore", targets: ["AlgorithmCore"]),
    ],
    targets: [
        .target(name: "AlgorithmCore", dependencies: []),
        .testTarget(name: "AlgorithmCoreTests", dependencies: ["AlgorithmCore"]),
    ]
)
```

**Key**: No iOS-specific imports in `AlgorithmCore` → runs on Linux.

---

## 8. Gap References

| Gap ID | Description | Addressed By |
|--------|-------------|--------------|
| GAP-TEST-002 | No Swift validation on Linux | AlgorithmCore package + CI |
| GAP-TRIO-SWIFT-001 | OpenAPS algorithm parity | Shared test vectors |
| GAP-VERIFY-002 | AAPS algorithm runner | aaps-runner.kt (planned) |

---

## 9. Related Documents

| Document | Purpose |
|----------|---------|
| [cross-platform-testing-research.md](cross-platform-testing-research.md) | Prior research |
| [spm-cross-platform-proposal.md](../sdqctl-proposals/spm-cross-platform-proposal.md) | xtool experience |
| [swift-package-ecosystem-assessment.md](swift-package-ecosystem-assessment.md) | SPM status |

---

## Summary

**Key Decisions:**

1. **Use tiered CI**: Linux for syntax/algorithms, macOS for full builds
2. **Extract AlgorithmCore**: Pure Swift package runnable on Linux
3. **Shared test vectors**: YAML format, cross-language runners
4. **Protocol-based mocks**: Abstract BLE/CGM for testability
5. **xtool for algorithms only**: Full app builds still need macOS

**Estimated Savings**: 90% reduction in CI costs by running most tests on Linux.
