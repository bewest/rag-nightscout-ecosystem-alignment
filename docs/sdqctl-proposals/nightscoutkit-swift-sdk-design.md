# NightscoutKit Swift SDK Design

> **Purpose**: API design for a unified v3-first Swift SDK for Nightscout  
> **Priority**: P1 - Unblocks GAP-API-003 (iOS v3 adoption)  
> **Created**: 2026-01-31  
> **Status**: Draft

---

## Executive Summary

This document proposes a unified Swift SDK for Nightscout API v3, designed to:
1. Enable iOS apps to adopt v3 API with incremental sync
2. Share code across Loop ecosystem (Loop, Trio, LoopCaregiver, LoopFollow)
3. Provide type-safe models matching OpenAPI specs
4. Support both API_SECRET and JWT authentication

**Key Decision**: Build on existing `gestrich/NightscoutKit` foundation rather than starting from scratch.

---

## Current State Analysis

### Existing Swift Implementations

| Project | Library | API Version | Auth | SPM |
|---------|---------|-------------|------|-----|
| LoopCaregiver | `gestrich/NightscoutKit` | v1 | API_SECRET + OTP | ✅ |
| xDrip4iOS | Custom `NightscoutSyncManager` | v1 | API_SECRET/Token | ❌ |
| Nightguard | Custom `NightscoutService` | v1/v2 | Token | ❌ |
| DiaBLE | Custom `Nightscout.swift` | v1 | API_SECRET | ❌ |
| Loop/Trio | `NightscoutService` (submodule) | v1 | API_SECRET | ❌ |

### gestrich/NightscoutKit Analysis

**Location**: `https://github.com/gestrich/NightscoutKit` (feature/2023-07/bg/remote-commands branch)

**Existing Capabilities**:
- `NightscoutClient` - HTTP client with URLSession
- Glucose fetching: `fetchGlucose(dateInterval:maxCount:)`
- Treatment CRUD: `fetchTreatments()`, `uploadTreatment()`
- DeviceStatus: `fetchDeviceStatus()`
- Profile: `fetchCurrentProfile()`
- Remote commands: `uploadRemoteCommand()`, `fetchRemoteCommands()`
- Auth check: `checkAuth()`

**Gaps for v3**:
- No `/api/v3` endpoint support
- No JWT authentication
- No incremental sync via `/history`
- No soft-delete handling (`isValid: false`)
- Callback-based async (not Swift Concurrency native)

---

## Proposed Architecture

### Module Structure

```
NightscoutKit (SPM Package)
├── Sources/
│   ├── NightscoutKit/
│   │   ├── Client/
│   │   │   ├── NightscoutClient.swift        # Main entry point
│   │   │   ├── NightscoutConfiguration.swift # URL, auth config
│   │   │   ├── APIVersion.swift              # v1, v2, v3 enum
│   │   │   └── HTTPClient.swift              # URLSession wrapper
│   │   ├── Authentication/
│   │   │   ├── AuthProvider.swift            # Protocol
│   │   │   ├── APISecretAuth.swift           # SHA1 header
│   │   │   ├── JWTAuth.swift                 # Bearer token
│   │   │   └── TokenAuth.swift               # Query param token
│   │   ├── Models/
│   │   │   ├── Entry.swift                   # SGV, MBG, Cal
│   │   │   ├── Treatment.swift               # Bolus, Carbs, etc.
│   │   │   ├── DeviceStatus.swift            # Loop/AAPS status
│   │   │   ├── Profile.swift                 # Therapy settings
│   │   │   └── BaseDocument.swift            # Common v3 fields
│   │   ├── Sync/
│   │   │   ├── SyncManager.swift             # Incremental sync
│   │   │   ├── SyncState.swift               # Last-Modified tracking
│   │   │   └── ConflictResolver.swift        # Dedup handling
│   │   └── RemoteCommands/
│   │       ├── RemoteCommand.swift           # Command models
│   │       └── OTPManager.swift              # TOTP generation
│   └── NightscoutKitUI/                      # Optional UI components
│       └── GlucoseChartView.swift
└── Tests/
    └── NightscoutKitTests/
```

### Package.swift

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NightscoutKit",
    platforms: [.iOS(.v15), .watchOS(.v8), .macOS(.v12)],
    products: [
        .library(name: "NightscoutKit", targets: ["NightscoutKit"]),
        .library(name: "NightscoutKitUI", targets: ["NightscoutKitUI"]),
    ],
    dependencies: [
        .package(url: "https://github.com/mattrubin/OneTimePassword.git", branch: "develop"),
    ],
    targets: [
        .target(
            name: "NightscoutKit",
            dependencies: ["OneTimePassword"]
        ),
        .target(
            name: "NightscoutKitUI",
            dependencies: ["NightscoutKit"]
        ),
        .testTarget(
            name: "NightscoutKitTests",
            dependencies: ["NightscoutKit"],
            resources: [.process("Fixtures")]
        ),
    ]
)
```

---

## API Design

### 1. Client Configuration

```swift
public struct NightscoutConfiguration {
    public let siteURL: URL
    public let apiVersion: APIVersion
    public let authProvider: AuthProvider
    
    public init(
        siteURL: URL,
        apiVersion: APIVersion = .v3,
        authProvider: AuthProvider
    )
}

public enum APIVersion: String {
    case v1 = "/api/v1"
    case v2 = "/api/v2"
    case v3 = "/api/v3"
}

// Usage
let config = NightscoutConfiguration(
    siteURL: URL(string: "https://my.nightscout.site")!,
    authProvider: .apiSecret("my-secret-key")
    // or: .jwt(token: "eyJ...")
    // or: .token("readable-token")
)
let client = NightscoutClient(configuration: config)
```

### 2. Authentication Providers

```swift
public protocol AuthProvider {
    func authenticate(request: inout URLRequest) async throws
}

public struct APISecretAuth: AuthProvider {
    private let secret: String
    
    public init(secret: String) {
        self.secret = secret
    }
    
    public func authenticate(request: inout URLRequest) {
        // SHA1 hash for api-secret header
        request.setValue(secret.sha1(), forHTTPHeaderField: "api-secret")
    }
}

public struct JWTAuth: AuthProvider {
    private let token: String
    
    public func authenticate(request: inout URLRequest) {
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
    }
}

public struct TokenAuth: AuthProvider {
    private let token: String
    
    public func authenticate(request: inout URLRequest) {
        // Append token to URL query
        guard var components = URLComponents(url: request.url!, resolvingAgainstBaseURL: false) else { return }
        var items = components.queryItems ?? []
        items.append(URLQueryItem(name: "token", value: token))
        components.queryItems = items
        request.url = components.url
    }
}
```

### 3. Core Data Models

```swift
// Base document fields (v3)
public protocol NightscoutDocument: Codable, Identifiable {
    var identifier: String { get }
    var date: Date { get }
    var utcOffset: Int? { get }
    var app: String? { get }
    var device: String? { get }
    var srvCreated: Date? { get }
    var srvModified: Date? { get }
    var isValid: Bool { get }
    var isReadOnly: Bool? { get }
}

// Entry (SGV, MBG, Cal)
public struct Entry: NightscoutDocument {
    public let identifier: String
    public let date: Date
    public let utcOffset: Int?
    public let type: EntryType
    public let sgv: Double?
    public let direction: TrendDirection?
    public let noise: Int?
    public let filtered: Double?
    public let unfiltered: Double?
    public let rssi: Int?
    public let units: GlucoseUnit?
    
    // v3 fields
    public let app: String?
    public let device: String?
    public let srvCreated: Date?
    public let srvModified: Date?
    public let isValid: Bool
    public let isReadOnly: Bool?
}

public enum EntryType: String, Codable {
    case sgv
    case mbg
    case cal
}

public enum TrendDirection: String, Codable {
    case doubleUp = "DoubleUp"
    case singleUp = "SingleUp"
    case fortyFiveUp = "FortyFiveUp"
    case flat = "Flat"
    case fortyFiveDown = "FortyFiveDown"
    case singleDown = "SingleDown"
    case doubleDown = "DoubleDown"
    case none = "NONE"
    case notComputable = "NOT COMPUTABLE"
    case rateOutOfRange = "RATE OUT OF RANGE"
}

// Treatment
public struct Treatment: NightscoutDocument {
    public let identifier: String
    public let date: Date
    public let utcOffset: Int?
    public let eventType: EventType
    public let insulin: Double?
    public let carbs: Double?
    public let duration: Double?  // minutes
    public let percent: Double?
    public let absolute: Double?
    public let glucose: Double?
    public let glucoseType: GlucoseType?
    public let notes: String?
    public let enteredBy: String?
    public let profile: String?
    public let targetTop: Double?
    public let targetBottom: Double?
    
    // v3 fields
    public let app: String?
    public let device: String?
    public let srvCreated: Date?
    public let srvModified: Date?
    public let isValid: Bool
    public let isReadOnly: Bool?
}

public enum EventType: String, Codable {
    case bolus = "Bolus"
    case meal = "Meal Bolus"
    case correctionBolus = "Correction Bolus"
    case carbCorrection = "Carb Correction"
    case tempBasal = "Temp Basal"
    case suspendPump = "Suspend Pump"
    case resumePump = "Resume Pump"
    case temporaryOverride = "Temporary Override"
    case profileSwitch = "Profile Switch"
    case siteChange = "Site Change"
    case sensorChange = "Sensor Change"
    case note = "Note"
    case announcement = "Announcement"
    // ... additional types
}
```

### 4. Collection Operations

```swift
public actor NightscoutClient {
    private let configuration: NightscoutConfiguration
    private let httpClient: HTTPClient
    
    public init(configuration: NightscoutConfiguration)
    
    // MARK: - Entries
    
    /// Fetch entries with optional filtering
    public func fetchEntries(
        dateRange: ClosedRange<Date>? = nil,
        type: EntryType? = nil,
        limit: Int = 100,
        skip: Int = 0
    ) async throws -> [Entry]
    
    /// Create new entry (returns created entry or deduplicated existing)
    public func createEntry(_ entry: Entry) async throws -> (Entry, wasDeduplicated: Bool)
    
    /// Update entry by identifier
    public func updateEntry(_ entry: Entry) async throws -> Entry
    
    /// Soft delete entry
    public func deleteEntry(identifier: String, permanent: Bool = false) async throws
    
    // MARK: - Treatments
    
    public func fetchTreatments(
        dateRange: ClosedRange<Date>? = nil,
        eventType: EventType? = nil,
        limit: Int = 100
    ) async throws -> [Treatment]
    
    public func createTreatment(_ treatment: Treatment) async throws -> (Treatment, wasDeduplicated: Bool)
    
    public func updateTreatment(_ treatment: Treatment) async throws -> Treatment
    
    public func deleteTreatment(identifier: String, permanent: Bool = false) async throws
    
    // MARK: - DeviceStatus
    
    public func fetchDeviceStatus(
        dateRange: ClosedRange<Date>? = nil,
        limit: Int = 10
    ) async throws -> [DeviceStatus]
    
    public func createDeviceStatus(_ status: DeviceStatus) async throws -> DeviceStatus
    
    // MARK: - Profile
    
    public func fetchCurrentProfile() async throws -> ProfileSet
    
    public func updateProfile(_ profile: ProfileSet) async throws -> ProfileSet
    
    // MARK: - History (v3 only)
    
    /// Incremental sync since last modification
    public func fetchHistory<T: NightscoutDocument>(
        collection: Collection,
        since: Date
    ) async throws -> HistoryResult<T>
    
    // MARK: - Utility
    
    public func checkAuth() async throws -> AuthStatus
    
    public func lastModified() async throws -> [Collection: Date]
}

public struct HistoryResult<T: NightscoutDocument> {
    public let documents: [T]
    public let lastModified: Date
    public let deletedIdentifiers: [String]
}

public enum Collection: String {
    case entries
    case treatments
    case devicestatus
    case profile
    case food
}
```

### 5. Incremental Sync Manager

```swift
public actor SyncManager {
    private let client: NightscoutClient
    private var syncState: SyncState
    
    public init(client: NightscoutClient, persistentStorage: SyncStateStorage? = nil)
    
    /// Perform incremental sync for a collection
    public func sync<T: NightscoutDocument>(
        collection: Collection
    ) async throws -> SyncResult<T>
    
    /// Full sync (ignores last-modified, fetches all)
    public func fullSync<T: NightscoutDocument>(
        collection: Collection,
        dateRange: ClosedRange<Date>
    ) async throws -> [T]
}

public struct SyncResult<T: NightscoutDocument> {
    public let added: [T]
    public let updated: [T]
    public let deleted: [String]  // identifiers
    public let unchanged: Bool
}

public protocol SyncStateStorage {
    func lastModified(for collection: Collection) async -> Date?
    func setLastModified(_ date: Date, for collection: Collection) async
}
```

### 6. Remote Commands (Caregiver)

```swift
public struct RemoteCommand: Codable {
    public let version: String  // "2.0"
    public let createdDate: Date
    public let action: RemoteAction
    public let sendNotification: Bool
    public let status: CommandStatus
    public let otp: String
}

public enum RemoteAction: Codable {
    case bolus(amountInUnits: Double)
    case carbs(amountInGrams: Double, absorptionTime: TimeInterval, startDate: Date)
    case override(name: String, durationTime: TimeInterval)
    case cancelOverride
    case closedLoop(active: Bool)
    case autobolus(active: Bool)
}

public struct CommandStatus: Codable {
    public let state: CommandState
    public let message: String
}

public enum CommandState: String, Codable {
    case pending = "Pending"
    case inProgress = "InProgress"
    case success = "Success"
    case error = "Error"
}

extension NightscoutClient {
    public func sendRemoteCommand(_ command: RemoteCommand) async throws -> RemoteCommand
    
    public func fetchRemoteCommands(
        since: Date,
        state: CommandState? = nil
    ) async throws -> [RemoteCommand]
    
    public func deleteRemoteCommands() async throws
}
```

---

## Migration Path

### Phase 1: Fork and Extend gestrich/NightscoutKit

1. Fork to `nightscout/NightscoutKit`
2. Add v3 endpoint support alongside v1
3. Convert callback APIs to async/await
4. Add incremental sync via `/history`

### Phase 2: Adopt in LoopCaregiver

1. Update dependency to new fork
2. Migrate NightscoutDataSource to use v3
3. Test remote commands with v3 API

### Phase 3: Extract Shared Components

1. Move treatment type extensions to SDK
2. Add GlucoseEntry → LoopKit.NewGlucoseSample conversion
3. Create NightscoutKitUI with chart components

### Phase 4: Ecosystem Adoption

1. Propose to Loop maintainers for NightscoutService replacement
2. Document migration guide for xDrip4iOS, Nightguard
3. Create example app demonstrating SDK usage

---

## Testing Strategy

### Unit Tests

```swift
class NightscoutClientTests: XCTestCase {
    var mockServer: MockNightscoutServer!
    var client: NightscoutClient!
    
    func testFetchEntriesV3() async throws {
        mockServer.stub(path: "/api/v3/entries", response: entriesFixture)
        
        let entries = try await client.fetchEntries(limit: 10)
        
        XCTAssertEqual(entries.count, 10)
        XCTAssertEqual(entries[0].type, .sgv)
    }
    
    func testIncrementalSync() async throws {
        mockServer.stub(path: "/api/v3/entries/history/1234567890", response: historyFixture)
        
        let result = try await syncManager.sync(collection: .entries)
        
        XCTAssertEqual(result.added.count, 5)
        XCTAssertEqual(result.deleted.count, 1)
    }
    
    func testDeduplication() async throws {
        mockServer.stub(path: "/api/v3/entries", statusCode: 200, response: existingEntry)
        
        let (entry, wasDeduplicated) = try await client.createEntry(newEntry)
        
        XCTAssertTrue(wasDeduplicated)
    }
}
```

### Integration Tests

- Against real Nightscout test instance (CI secret)
- Conformance vectors from `conformance/vectors/nightscout/`

---

## Gap Resolution

| Gap ID | Description | How SDK Addresses |
|--------|-------------|-------------------|
| **GAP-API-003** | No v3 adoption path for iOS | Native Swift v3 client |
| **GAP-SYNC-002** | Effect timelines not uploaded | DeviceStatus model supports predictions |
| **GAP-TREAT-005** | Loop POST-only duplicates | Dedup detection via 200 response |
| **GAP-API-001** | v1 cannot detect deletions | History endpoint returns `isValid: false` |

---

## Dependencies

| Dependency | Purpose | License |
|------------|---------|---------|
| OneTimePassword | TOTP for remote commands | MIT |

**No other external dependencies** - uses Foundation URLSession.

---

## Effort Estimate

| Phase | Deliverable | Complexity |
|-------|-------------|------------|
| 1 | Fork + v3 endpoints | Medium |
| 2 | Async/await migration | Medium |
| 3 | Incremental sync | Medium |
| 4 | LoopCaregiver integration | Low |
| 5 | Documentation + examples | Low |

---

## Open Questions

1. **Namespace**: `NightscoutKit` vs `NightscoutSwift` vs `Nightscout`?
2. **LoopKit Dependency**: Should models extend LoopKit types or stay independent?
3. **Combine Support**: Include publishers for reactive patterns?
4. **Offline Support**: Cache layer in SDK or leave to consumers?

---

## References

- [Nightscout API v3 Summary](../../specs/openapi/nightscout-api3-summary.md)
- [OpenAPI Specs](../../specs/openapi/)
- [gestrich/NightscoutKit](https://github.com/gestrich/NightscoutKit)
- [LoopCaregiver Implementation](../../externals/LoopCaregiver/LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/)
- [iOS Mobile Platform Backlog](backlogs/ios-mobile-platform.md)

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-31 | Build on gestrich/NightscoutKit | Already SPM, already used by LoopCaregiver |
| 2026-01-31 | v3-first with v1 fallback | Incremental sync is killer feature |
| 2026-01-31 | Actor-based client | Thread safety for async operations |
| 2026-01-31 | No LoopKit dependency in core | Maximize reusability across ecosystem |
