# Cross-Project Testing Plan

> **Purpose**: Define Ubuntu-compatible testing strategies for Swift AID projects  
> **Scope**: Trio, Loop, LoopKit, and related Swift packages  
> **Last Updated**: 2026-01-29

## Executive Summary

This document analyzes the testing infrastructure of Loop and Trio iOS applications and proposes strategies for running tests in cross-project CI environments, particularly on Linux/Ubuntu where Swift has limited iOS support.

### Key Constraints

| Constraint | Impact |
|------------|--------|
| **iOS Simulator** | Requires macOS (Xcode) |
| **Swift on Linux** | No UIKit, CoreData, HealthKit |
| **Package.swift** | Partially supported in LoopKit (see warning) |
| **GitHub Actions** | macOS runners are 10x more expensive |

---

## Current Test Infrastructure

### Trio

| Component | Test Files | CI Status |
|-----------|-----------|-----------|
| TrioTests | 211 Swift files | GitHub Actions (macOS-15) |
| LoopKit | Package.swift exists | ⚠️ "Not complete yet" warning |
| RileyLinkKit | Tests exist | Travis CI (legacy) |

**CI Configuration**: `.github/workflows/unit_tests.yml`
- Runner: `macos-15`
- Xcode: 16.3
- Destination: iPhone 16 Simulator (iOS 18.4)
- Cache: DerivedData + .build

```yaml
# Trio unit_tests.yml (lines 26, 61-64)
runs-on: macos-15
xcodebuild build-for-testing \
  -workspace Trio.xcworkspace \
  -scheme "Trio Tests" \
  -destination 'platform=iOS Simulator,name=iPhone 16,OS=18.4'
```

### Loop

| Component | Test Files | CI Status |
|-----------|-----------|-----------|
| LoopTests | 233 Swift files | Travis CI (xcode12.4) |
| DoseMathTests | Separate scheme | Travis CI |
| LoopKit | Package.swift | ⚠️ "Not complete yet" warning |

**CI Configuration**: `.travis.yml`
- Runner: macOS (xcode12.4)
- Schemes: Loop, Learn, LoopTests, DoseMathTests

```yaml
# Loop .travis.yml (lines 17-19)
xcodebuild -project Loop.xcodeproj -scheme LoopTests \
  -destination 'platform=iOS Simulator,name=iPhone 8' test
```

### LoopKit Package.swift Status

Both Trio and Loop have LoopKit with Package.swift, but with explicit warnings:

```swift
// LoopKit/Package.swift:4-8
// *************** Not complete yet, do not expect this to work! ***********************
// There are issues with how test fixtures are copied into the bundle, and then referenced,
// and other issues, largely around accessing bundle resources, and probably others not yet
// discovered, as this is not being used as a swift package from any actual project yet.
```

**Platforms**: iOS 15.0+ only (no macOS/Linux)

---

## Swift on Linux Limitations

### What Works

| Feature | Linux Support |
|---------|---------------|
| Swift core language | ✅ Full support |
| Foundation | ✅ Most features |
| Swift Package Manager | ✅ Full support |
| XCTest | ✅ Works with SPM |
| Codable/JSON | ✅ Full support |
| Combine | ⚠️ OpenCombine alternative |

### What Doesn't Work

| Feature | Linux Support | Used By |
|---------|---------------|---------|
| UIKit | ❌ macOS/iOS only | UI tests, views |
| CoreData | ❌ Apple platforms only | All AID apps |
| HealthKit | ❌ iOS only | Glucose, insulin data |
| CoreBluetooth | ❌ Apple platforms only | CGM/pump communication |
| SwiftUI | ❌ Apple platforms only | Modern UI |

### Impact on AID Testing

| Test Category | Linux Compatible | Notes |
|---------------|------------------|-------|
| **Algorithm logic** | ✅ Yes | Pure Swift, no platform deps |
| **Data models** | ⚠️ Partial | If no CoreData |
| **Nightscout sync** | ⚠️ Partial | Network code works |
| **UI components** | ❌ No | Requires UIKit/SwiftUI |
| **CGM/pump drivers** | ❌ No | Requires CoreBluetooth |
| **HealthKit integration** | ❌ No | Requires HealthKit |

---

## Proposed Testing Strategies

### Strategy 1: Extract Pure-Swift Algorithm Packages

**Approach**: Refactor algorithm code into platform-independent Swift packages.

| Package | Content | Linux Compatible |
|---------|---------|------------------|
| `LoopAlgorithm` | Dose calculations, predictions | ✅ Yes |
| `OrefAlgorithm` | oref0/oref1 determine-basal | ✅ Yes |
| `InsulinModel` | Exponential insulin curves | ✅ Yes |
| `CarbModel` | Carb absorption models | ✅ Yes |

**Implementation**:
```swift
// Package.swift for algorithm-only package
let package = Package(
    name: "LoopAlgorithm",
    platforms: [.iOS(.v15), .macOS(.v12)],  // Add macOS
    products: [
        .library(name: "LoopAlgorithm", targets: ["LoopAlgorithm"]),
    ],
    targets: [
        .target(name: "LoopAlgorithm", dependencies: []),
        .testTarget(name: "LoopAlgorithmTests", dependencies: ["LoopAlgorithm"]),
    ]
)
```

**Benefits**:
- Tests run on Linux with `swift test`
- Enables cross-language testing (Rust oref vs Swift)
- Faster CI (no simulator required)

**Effort**: Medium (requires refactoring)

### Strategy 2: Remote macOS Test Execution

**Approach**: Run tests on macOS, aggregate results to Ubuntu CI.

| Option | Cost | Setup |
|--------|------|-------|
| **GitHub Actions macOS** | $0.08/min | Native, simple |
| **Self-hosted Mac Mini** | Hardware cost | Full control |
| **MacStadium/AWS Mac** | ~$1/hr | Enterprise |
| **Codemagic/Bitrise** | Free tier available | iOS-focused |

**GitHub Actions Configuration**:
```yaml
# Cross-project test workflow
jobs:
  swift-tests:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      
      - name: Run Trio tests
        run: |
          xcodebuild test \
            -workspace Trio.xcworkspace \
            -scheme "Trio Tests" \
            -destination 'platform=iOS Simulator,name=iPhone 15'
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: test-results.xml
```

**Benefits**:
- Full iOS simulator support
- Existing CI configurations work
- No code changes required

**Effort**: Low (CI configuration only)

### Strategy 3: Test Fixture Extraction

**Approach**: Extract test fixtures (JSON, sample data) for use in other projects.

| Fixture Type | Source | Cross-Project Use |
|--------------|--------|-------------------|
| CGM readings | LoopKitTests/Fixtures | Nightscout mock data |
| Insulin doses | DoseMathTests | Algorithm validation |
| Carb entries | CarbStoreTests | Treatment sync testing |
| Predictions | PredictionTests | Visualization testing |

**Implementation**:
```
fixtures/
├── cgm/
│   ├── loop-sgv-samples.json
│   └── trio-glucose-samples.json
├── treatments/
│   ├── bolus-samples.json
│   └── carb-samples.json
└── predictions/
    ├── loop-prediction-output.json
    └── oref-prediction-output.json
```

**Benefits**:
- Test Nightscout with real app data shapes
- Validate cross-system data compatibility
- Language-independent (JSON fixtures)

**Effort**: Low (extraction script)

### Strategy 4: Docker-based Swift Testing

**Approach**: Use Swift Docker images for Linux-compatible tests.

```dockerfile
# Dockerfile.swift-tests
FROM swift:5.9
WORKDIR /app
COPY Package.swift ./
COPY Sources ./Sources
COPY Tests ./Tests
RUN swift test
```

**Limitations**:
- Only works for pure-Swift packages
- No iOS framework dependencies
- Requires Package.swift to be Linux-compatible

**Benefits**:
- Consistent test environment
- Integrates with existing CI
- Fast (no macOS overhead)

**Effort**: Low (for compatible packages)

---

## Recommended Implementation

### Phase 1: Fixture Extraction (1-2 days)

1. Create `fixtures/` directory in workspace
2. Extract JSON test data from LoopKitTests/Fixtures
3. Add Python script to validate fixture format
4. Use fixtures in `tools/test_conversions.py`

### Phase 2: Remote macOS Testing (1 day)

1. Create `.github/workflows/swift-tests.yml`
2. Configure for LoopKit tests only (most stable)
3. Cache DerivedData for faster runs
4. Upload test results as artifacts

### Phase 3: Algorithm Package Extraction (3-5 days)

1. Identify pure-Swift algorithm code in LoopKit
2. Create `LoopAlgorithm` SPM package
3. Add Linux platform support
4. Run tests with `swift test` on Ubuntu
5. Compare results with Rust oref implementation

---

## Test Matrix

| Project | Unit Tests | Integration | E2E | Linux |
|---------|------------|-------------|-----|-------|
| Trio | ✅ 211 files | ❌ | ❌ | ❌ |
| Loop | ✅ 233 files | ❌ | ❌ | ❌ |
| LoopKit | ⚠️ Partial | ❌ | ❌ | ⚠️ |
| cgm-remote-monitor | ✅ 78 files | ✅ supertest | ❌ | ✅ |
| AAPS | ✅ Kotlin | ✅ | ❌ | ✅ (JVM) |
| xDrip+ | ✅ Java | ❌ | ❌ | ✅ (JVM) |

---

## Cost Analysis

| Strategy | Monthly Cost | Setup Time | Maintenance |
|----------|--------------|------------|-------------|
| GitHub macOS | ~$50-100 | 1 day | Low |
| Self-hosted Mac | $600-1000 (hardware) | 2-3 days | Medium |
| Algorithm extraction | $0 | 3-5 days | Low |
| Fixture extraction | $0 | 1-2 days | Low |

---

## Gaps Identified

### GAP-TEST-001: No cross-project test harness for Swift

**Description**: No mechanism to run Loop/Trio algorithm tests against Nightscout data or compare with AAPS/oref results.

**Impact**: Cannot validate algorithm consistency across implementations.

**Remediation**: Extract algorithm packages with shared test fixtures.

### GAP-TEST-002: LoopKit Package.swift incomplete

**Description**: Package.swift exists but is explicitly marked as non-functional due to bundle resource issues.

**Impact**: Cannot use SPM for cross-platform testing.

**Remediation**: Fix resource copying or extract algorithm-only package.

### GAP-TEST-003: No CI for Loop unit tests

**Description**: Loop uses Travis CI with outdated Xcode 12.4. No GitHub Actions workflow for tests.

**Impact**: Test infrastructure may be broken or outdated.

**Remediation**: Migrate to GitHub Actions with modern Xcode.

---

## Recommendations

| Priority | Action | Effort | Impact |
|----------|--------|--------|--------|
| P1 | Extract test fixtures from LoopKit | Low | High |
| P1 | Create GitHub Actions workflow for Trio tests | Low | Medium |
| P2 | Extract pure-Swift algorithm package | Medium | High |
| P2 | Add Makefile targets for remote test execution | Low | Medium |
| P3 | Investigate LoopKit Package.swift fixes | Medium | Medium |

---

## Source File References

### Trio
- `.github/workflows/unit_tests.yml` - GitHub Actions test workflow
- `.github/workflows/build_trio.yml` - Build workflow
- `TrioTests/` - 211 test files
- `LoopKit/Package.swift` - SPM package (incomplete)

### Loop
- `.travis.yml` - Travis CI configuration
- `LoopTests/` - 233 test files
- `DoseMathTests/` - Dose calculation tests
- `LoopKit/Package.swift` - SPM package (incomplete)

### LoopKit
- `LoopKitTests/Fixtures/` - JSON test fixtures
- `Package.swift:4-8` - "Not complete yet" warning
- `platforms: [.iOS("15.0")]` - iOS only, no macOS/Linux
