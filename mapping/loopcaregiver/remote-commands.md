# LoopCaregiver Remote Commands Protocol

This document details the Remote 2.0 protocol implementation in LoopCaregiver for sending commands to Loop via Nightscout.

---

## Executive Summary

LoopCaregiver implements the Nightscout Remote 2.0 API for sending commands to Loop. Commands are uploaded to Nightscout with OTP authentication, and Loop fetches and executes them via push notifications.

| Aspect | Value |
|--------|-------|
| **API Version** | Remote 2.0 |
| **Transport** | HTTPS to Nightscout + APNS to Loop |
| **Authentication** | TOTP OTP (SHA1, 6-digit, 30-second) |
| **Command Types** | 6 (bolus, carbs, override, cancelOverride, autobolus, closedLoop) |
| **Status Tracking** | Pending → InProgress → Success/Error |

---

## Source Files

| File | Purpose |
|------|---------|
| `LoopCaregiverKit/Sources/.../Nightscout/NightscoutDataSource.swift` | Main command upload logic |
| `LoopCaregiverKit/Sources/.../Nightscout/OTPManager.swift` | TOTP generation |
| `LoopCaregiverKit/Sources/.../Nightscout/NightscoutCredentialService.swift` | Credential management with OTP |
| `LoopCaregiverKit/Sources/.../Nightscout/RemoteCommands/NSRemoteCommandPayload.swift` | Payload conversion |
| `LoopCaregiverKit/Sources/.../Nightscout/RemoteCommands/RemoteCommandStatus+Extras.swift` | Status conversion |
| `LoopCaregiverKit/Sources/.../Models/RemoteCommands/Action.swift` | Command action types |
| `LoopCaregiverKit/Sources/.../Models/RemoteCommands/RemoteCommand.swift` | Command model |
| `LoopCaregiverKit/Sources/.../Models/RemoteCommands/RemoteCommandStatus.swift` | Status model |
| `LoopCaregiverKit/Sources/.../Models/RemoteDataServiceManager.swift` | Data orchestration |

---

## Command Types

### Action Enum

```swift
// loopcaregiver:LoopCaregiverKit/Sources/.../Models/RemoteCommands/Action.swift
public enum Action: Codable, Equatable {
    case temporaryScheduleOverride(OverrideAction)
    case cancelTemporaryOverride(OverrideCancelAction)
    case bolusEntry(BolusAction)
    case carbsEntry(CarbAction)
    case autobolus(AutobolusAction)
    case closedLoop(ClosedLoopAction)
}
```

### Command Details

| Command | Action Type | Parameters | OTP Required |
|---------|-------------|------------|--------------|
| **Bolus** | `bolusEntry` | `amountInUnits: Double` | Yes |
| **Carbs** | `carbsEntry` | `amountInGrams: Double`, `absorptionTime: TimeInterval?`, `startDate: Date?` | Yes |
| **Override** | `temporaryScheduleOverride` | `name: String`, `durationTime: TimeInterval?`, `remoteAddress: String` | **No** (See GAP-REMOTE-001) |
| **Cancel Override** | `cancelTemporaryOverride` | `remoteAddress: String` | **No** |
| **Autobolus Toggle** | `autobolus` | `active: Bool` | Yes |
| **Closed Loop Toggle** | `closedLoop` | `active: Bool` | Yes |

### Action Structures

```swift
// BolusAction
public struct BolusAction: Codable, Equatable {
    public let amountInUnits: Double
}

// CarbAction
public struct CarbAction: Codable, Equatable {
    public let amountInGrams: Double
    public let absorptionTime: TimeInterval?
    public let startDate: Date?
}

// OverrideAction
public struct OverrideAction: Codable, Equatable {
    public let name: String
    public let durationTime: TimeInterval?
    public let remoteAddress: String
}

// OverrideCancelAction
public struct OverrideCancelAction: Codable, Equatable {
    public let remoteAddress: String
}

// AutobolusAction
public struct AutobolusAction: Codable, Equatable {
    public let active: Bool
}

// ClosedLoopAction
public struct ClosedLoopAction: Codable, Equatable {
    public let active: Bool
}
```

---

## Remote 2.0 API Protocol

### Version Selection

LoopCaregiver supports both Remote 1.0 (legacy) and Remote 2.0 protocols, selected via settings:

```swift
// loopcaregiver:NightscoutDataSource.swift#L136-L156
public func deliverBolus(amountInUnits: Double) async throws {
    if settings.remoteCommands2Enabled {
        // Remote 2.0: Upload command to Nightscout
        let action = NSRemoteAction.bolus(amountInUnits: amountInUnits)
        let commandPayload = createPendingCommand(action: action)
        _ = try await nightscoutUploader.uploadRemoteCommand(commandPayload)
    } else {
        // Remote 1.0: Direct OTP in request
        try await nightscoutUploader.deliverBolus(amountInUnits: amountInUnits, otp: credentialService.otpCode)
    }
}
```

### Command Payload Structure

```swift
// Remote 2.0 command payload creation
// loopcaregiver:NightscoutDataSource.swift#L200-L202
func createPendingCommand(action: NSRemoteAction) -> NSRemoteCommandPayload {
    return NSRemoteCommandPayload(
        version: "2.0",
        createdDate: Date(),
        action: action,
        sendNotification: true,
        status: .init(state: .Pending, message: ""),
        otp: credentialService.otpCode
    )
}
```

### Command Payload Fields

| Field | Type | Description |
|-------|------|-------------|
| `version` | `String` | API version, always `"2.0"` |
| `createdDate` | `Date` | Command creation timestamp |
| `action` | `NSRemoteAction` | Command type and parameters |
| `sendNotification` | `Bool` | Whether to trigger APNS push |
| `status` | `NSRemoteCommandStatus` | Initial status (Pending) |
| `otp` | `String` | Current TOTP code |

---

## Command Status Lifecycle

### Status States

```swift
// loopcaregiver:RemoteCommandStatus.swift
public struct RemoteCommandStatus: Equatable {
    public let state: RemoteComandState
    public let message: String

    public enum RemoteComandState: Equatable {
        case pending       // Command uploaded, awaiting Loop pickup
        case inProgress    // Loop received, executing
        case success       // Command completed successfully
        case error(RemoteCommandStatusError)  // Execution failed
    }
}
```

### Status Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         REMOTE COMMAND STATUS FLOW                           │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                    │
│  │   PENDING   │ ──► │ IN_PROGRESS │ ──► │   SUCCESS   │                    │
│  └─────────────┘     └─────────────┘     └─────────────┘                    │
│        │                   │                                                 │
│        │                   │             ┌─────────────┐                    │
│        │                   └──────────► │    ERROR    │                    │
│        │                                 │  (message)  │                    │
│        └─────────────────────────────► └─────────────┘                    │
│                   (timeout/failure)                                          │
│                                                                              │
│  Caregiver uploads ─► Nightscout stores ─► Loop fetches ─► Loop executes   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Status Polling

LoopCaregiver polls for command status updates:

```swift
// loopcaregiver:NightscoutDataSource.swift#L204-L210
public func fetchRecentCommands() async throws -> [RemoteCommand] {
    if settings.remoteCommands2Enabled {
        return try await nightscoutUploader.fetchRemoteCommands(
            earliestDate: fetchInterval().start, 
            commandState: nil
        ).compactMap({ try? $0.toRemoteCommand() })
    }
    return try await fetchNotes().compactMap({ $0.toRemoteCommand() })
}
```

---

## Command Delivery Flow

### Carbs Command

```swift
// loopcaregiver:NightscoutDataSource.swift#L136-L145
public func deliverCarbs(amountInGrams: Double, absorptionTime: TimeInterval, consumedDate: Date) async throws {
    if settings.remoteCommands2Enabled {
        let action = NSRemoteAction.carbs(
            amountInGrams: amountInGrams, 
            absorptionTime: absorptionTime, 
            startDate: consumedDate
        )
        let commandPayload = createPendingCommand(action: action)
        _ = try await nightscoutUploader.uploadRemoteCommand(commandPayload)
    } else {
        try await nightscoutUploader.deliverCarbs(
            amountInGrams: amountInGrams, 
            absorptionTime: absorptionTime, 
            consumedDate: consumedDate, 
            otp: credentialService.otpCode
        )
    }
}
```

### Override Command

```swift
// loopcaregiver:NightscoutDataSource.swift#L158-L167
public func startOverride(overrideName: String, durationTime: TimeInterval) async throws {
    if settings.remoteCommands2Enabled {
        let action = NSRemoteAction.override(
            name: overrideName, 
            durationTime: durationTime, 
            remoteAddress: ""  // TODO: remoteAddress should be optional
        )
        let commandPayload = createPendingCommand(action: action)
        _ = try await nightscoutUploader.uploadRemoteCommand(commandPayload)
    } else {
        try await nightscoutUploader.startOverride(
            overrideName: overrideName, 
            reasonDisplay: "Caregiver Update", 
            durationTime: durationTime
        )
    }
}
```

### Autobolus/Closed Loop Toggle

```swift
// loopcaregiver:NightscoutDataSource.swift#L180-L189
public func activateAutobolus(activate: Bool) async throws {
    let action = NSRemoteAction.autobolus(active: activate)
    let commandPayload = createPendingCommand(action: action)
    _ = try await nightscoutUploader.uploadRemoteCommand(commandPayload)
}

public func activateClosedLoop(activate: Bool) async throws {
    let action = NSRemoteAction.closedLoop(active: activate)
    let commandPayload = createPendingCommand(action: action)
    _ = try await nightscoutUploader.uploadRemoteCommand(commandPayload)
}
```

---

## Safety Considerations

### Caregiver-Side Safety

LoopCaregiver implements minimal safety checks on the caregiver side:

1. **Recommended Bolus Expiry**: 7-minute timeout for stale recommendations

```swift
// loopcaregiver:RemoteDataServiceManager.swift#L191-L217
private func calculateValidRecommendedBolus() -> Double? {
    guard let latestDeviceStatus = self.latestDeviceStatus else { return nil }
    guard let recommendedBolus = latestDeviceStatus.loopStatus?.recommendedBolus else { return nil }
    guard recommendedBolus > 0.0 else { return nil }
    
    // Expire after 7 minutes
    let expired = Date().timeIntervalSince(latestDeviceStatus.timestamp) > 60 * 7
    guard !expired else { return nil }
    
    // Reject if bolus occurred after recommendation
    if let latestBolusEntry = bolusEntries.filter({ $0.timestamp < nowDate() })
        .max(by: { $0.timestamp < $1.timestamp }) {
        if latestBolusEntry.timestamp >= latestDeviceStatus.timestamp {
            return nil
        }
    }
    
    return recommendedBolus
}
```

2. **Credential Validation**: Auth check before saving credentials

```swift
// loopcaregiver:LooperSetupView.swift#L205-L206
let service = accountService.createLooperService(looper: looper)
try await service.remoteDataSource.checkAuth()
```

### Device-Side Safety

All actual dosing safety limits are enforced on the Loop device side, not in LoopCaregiver. See [remote-commands-comparison.md](../../docs/10-domain/remote-commands-comparison.md#loop-safety-checks) for details.

**Key Gap**: Override commands do not require OTP validation on the Loop side (GAP-REMOTE-001).

---

## Data Models

### RemoteCommand

```swift
// loopcaregiver:RemoteCommand.swift
public struct RemoteCommand: Equatable {
    public let id: String
    public let action: Action
    public let status: RemoteCommandStatus
    public let createdDate: Date
}
```

### Command Conversion

```swift
// loopcaregiver:NSRemoteCommandPayload.swift#L12-L19
public extension NSRemoteCommandPayload {
    func toRemoteCommand() throws -> RemoteCommand {
        guard let id = _id else {
            throw RemoteCommandPayloadError.missingID
        }
        return RemoteCommand(
            id: id, 
            action: toRemoteAction(), 
            status: status.toStatus(), 
            createdDate: createdDate
        )
    }
}
```

---

## Cross-References

- [LoopCaregiver Authentication](authentication.md) - QR code linking and OTP details
- [Remote Commands Comparison](../../docs/10-domain/remote-commands-comparison.md) - Cross-system security comparison
- [Loop Remote Commands](../loop/remote-commands.md) - Loop-side implementation (if exists)
- [Terminology Matrix](../cross-project/terminology-matrix.md) - Field mapping

---

## Gaps and Requirements

### Related Gaps

| Gap ID | Description |
|--------|-------------|
| GAP-REMOTE-001 | Override commands not protected by OTP on Loop side |
| GAP-REMOTE-005 | `remoteAddress` field purpose unclear, hardcoded to empty string |
| GAP-REMOTE-006 | No command retry mechanism for failed deliveries |

### Related Requirements

| Requirement ID | Description |
|----------------|-------------|
| REQ-REMOTE-007 | Caregiver apps MUST display command status to users |
| REQ-REMOTE-008 | Caregiver apps MUST expire recommended bolus after device status age |
| REQ-REMOTE-009 | Remote commands MUST include creation timestamp for ordering |
| REQ-REMOTE-010 | Caregiver apps SHOULD validate credentials before storing |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial documentation based on source code analysis |
