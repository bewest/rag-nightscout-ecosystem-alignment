# Trio Remote Commands (TrioRemoteControl)

This document details Trio's secure remote command system using Apple Push Notifications (APNS) with AES-256-GCM encryption.

## Source Files

| File | Purpose |
|------|---------|
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl.swift` | Main remote command handler |
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+Bolus.swift` | Bolus command processing |
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+Meal.swift` | Meal command processing |
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+TempTarget.swift` | Temp target commands |
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+Override.swift` | Override start/cancel |
| `trio:Trio/Sources/Services/RemoteControl/SecureMessenger.swift` | AES-GCM encryption/decryption |
| `trio:Trio/Sources/Services/RemoteControl/RemoteNotificationResponseManager.swift` | Response notifications |
| `trio:Trio/Sources/Services/RemoteControl/APNSJWTClaims.swift` | APNS JWT authentication |

---

## Overview

Trio uses a secure remote command system via Apple Push Notifications with end-to-end encryption. Commands are encrypted with a shared secret using AES-256-GCM, providing authentication and confidentiality.

**Security Model**:
- **Encryption**: AES-256-GCM with SHA256-derived key from shared secret
- **Authentication**: Shared secret must match between sender and receiver
- **Replay Protection**: Commands expire after 10 minutes (600 seconds)
- **Safety Limits**: Max bolus and max IOB checks enforced

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Trio Remote Control Flow                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Caregiver App                                                           │
│  ├── Create CommandPayload (type, amount, timestamp)                    │
│  ├── Encrypt with shared secret → AES-256-GCM                           │
│  └── Send via APNS push notification                                    │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    Apple Push Notification Service                  │ │
│  │                    (encrypted payload delivery)                     │ │
│  └──────────────────────────────┬─────────────────────────────────────┘ │
│                                 │                                        │
│  ┌──────────────────────────────▼─────────────────────────────────────┐ │
│  │              TrioRemoteControl.handleRemoteNotification()          │ │
│  │                                                                     │ │
│  │  1. Check isTrioRemoteControlEnabled setting                       │ │
│  │  2. Verify shared secret is configured                             │ │
│  │  3. Decrypt payload with SecureMessenger                           │ │
│  │  4. Validate timestamp (within ±10 minutes)                        │ │
│  │  5. Route to command handler                                       │ │
│  └──────────────────────────────┬─────────────────────────────────────┘ │
│                                 │                                        │
│  ┌──────────────────────────────▼─────────────────────────────────────┐ │
│  │              Command Handlers                                       │ │
│  │                                                                     │ │
│  │  ├── handleBolusCommand()     → Deliver insulin                    │ │
│  │  ├── handleMealCommand()      → Add carbs + optional bolus         │ │
│  │  ├── handleTempTargetCommand() → Set temp target                   │ │
│  │  ├── cancelTempTarget()       → Cancel temp target                 │ │
│  │  ├── handleStartOverrideCommand() → Start override preset          │ │
│  │  └── handleCancelOverrideCommand() → Cancel active overrides       │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Encryption

### SecureMessenger

```swift
// trio:Trio/Sources/Services/RemoteControl/SecureMessenger.swift
struct SecureMessenger {
    private let sharedKey: [UInt8]

    init?(sharedSecret: String) {
        guard let secretData = sharedSecret.data(using: .utf8) else {
            return nil
        }
        sharedKey = Array(secretData.sha256())  // SHA256 key derivation
    }

    func decrypt(base64EncodedString: String) throws -> CommandPayload {
        guard let combinedData = Data(base64Encoded: base64EncodedString) else {
            throw NSError(domain: "SecureMessenger", code: 100)
        }

        let nonceSize = 12
        let nonce = Array(combinedData.prefix(nonceSize))
        let ciphertextAndTag = Array(combinedData.suffix(from: nonceSize))
        
        let gcm = GCM(iv: nonce, mode: .combined)
        let aes = try AES(key: sharedKey, blockMode: gcm, padding: .noPadding)
        let decryptedBytes = try aes.decrypt(ciphertextAndTag)
        
        return try JSONDecoder().decode(CommandPayload.self, from: Data(decryptedBytes))
    }
}
```

### Encryption Details

| Parameter | Value |
|-----------|-------|
| Algorithm | AES-256 |
| Mode | GCM (Galois/Counter Mode) |
| Key Derivation | SHA256 of shared secret |
| Nonce Size | 12 bytes |
| Authentication Tag | Included in ciphertext |

---

## Command Types

### 1. Bolus Command

Delivers insulin with safety validations.

```swift
// trio:TrioRemoteControl+Bolus.swift
internal func handleBolusCommand(_ payload: CommandPayload) async throws {
    guard let bolusAmount = payload.bolusAmount else { return }
    
    // Safety check 1: Max bolus
    let maxBolus = settings.pumpSettings.maxBolus
    if bolusAmount > maxBolus {
        await logError("Bolus exceeds max allowed")
        return
    }
    
    // Safety check 2: Max IOB
    let maxIOB = settings.preferences.maxIOB
    if (currentIOB + bolusAmount) > maxIOB {
        await logError("Bolus would exceed max IOB")
        return
    }
    
    // Safety check 3: Recent boluses
    let totalRecentBolus = try await fetchTotalRecentBolusAmount(since: commandTime)
    if totalRecentBolus >= bolusAmount * 0.2 {
        await logError("Recent boluses exceed 20% of requested amount")
        return
    }
    
    // Enact bolus
    await apsManager.enactBolus(amount: Double(bolusAmount), isSMB: false)
}
```

### 2. Meal Command

Adds carb entry with optional bolus.

```swift
// trio:TrioRemoteControl+Meal.swift
internal func handleMealCommand(_ payload: CommandPayload) async throws {
    guard let carbAmount = payload.carbAmount else { return }
    
    let carbEntry = CarbsEntry(
        createdAt: Date(),
        carbs: carbAmount,
        fat: payload.fatAmount ?? 0,
        protein: payload.proteinAmount ?? 0,
        note: "Remote Command",
        enteredBy: CarbsEntry.manual
    )
    
    await carbsStorage.storeCarbs([carbEntry])
    await nightscoutManager.uploadCarbs()
    
    // Optional bolus follows
    if payload.bolusAmount != nil {
        try await handleBolusCommand(payload)
    }
}
```

### 3. Temp Target Command

Sets a temporary glucose target.

```swift
// trio:TrioRemoteControl+TempTarget.swift
internal func handleTempTargetCommand(_ payload: CommandPayload) async throws {
    guard let targetBG = payload.targetBG,
          let duration = payload.duration else { return }
    
    let tempTarget = TempTargetStored(context: viewContext)
    tempTarget.id = UUID()
    tempTarget.startDate = Date()
    tempTarget.targetBottom = NSDecimalNumber(decimal: targetBG)
    tempTarget.targetTop = NSDecimalNumber(decimal: targetBG)
    tempTarget.duration = NSDecimalNumber(decimal: duration)
    tempTarget.enabled = true
    
    try viewContext.save()
}
```

### 4. Cancel Temp Target

```swift
internal func cancelTempTarget(_ payload: CommandPayload) async {
    await disableAllActiveTempTargets()
    await logSuccess("Temp target canceled")
}
```

### 5. Start Override Command

Activates a named override preset.

```swift
// trio:TrioRemoteControl+Override.swift
@MainActor internal func handleStartOverrideCommand(_ payload: CommandPayload) async {
    guard let overrideName = payload.overrideName, !overrideName.isEmpty else {
        await logError("Override name is missing")
        return
    }
    
    let presetIDs = try await overrideStorage.fetchForOverridePresets()
    let presets = try presetIDs.compactMap { 
        try viewContext.existingObject(with: $0) as? OverrideStored 
    }
    
    if let preset = presets.first(where: { $0.name == overrideName }) {
        await enactOverridePreset(preset: preset, payload: payload)
    } else {
        await logError("Override preset '\(overrideName)' not found")
    }
}
```

### 6. Cancel Override Command

```swift
@MainActor internal func handleCancelOverrideCommand(_ payload: CommandPayload) async {
    await disableAllActiveOverrides()
    await logSuccess("Override canceled")
}
```

---

## Command Payload

```swift
struct CommandPayload: Codable {
    let commandType: CommandType
    let timestamp: TimeInterval       // Unix epoch seconds
    
    // Bolus
    let bolusAmount: Decimal?
    
    // Meal
    let carbAmount: Decimal?
    let fatAmount: Decimal?
    let proteinAmount: Decimal?
    
    // Temp Target
    let targetBG: Decimal?
    let duration: Decimal?            // Minutes
    
    // Override
    let overrideName: String?
    
    // Response notification
    let returnNotification: ReturnNotificationInfo?
}

enum CommandType: String, Codable {
    case bolus
    case meal
    case tempTarget
    case cancelTempTarget
    case startOverride
    case cancelOverride
}
```

---

## Security Validations

### 1. Setting Check

```swift
let isTrioRemoteControlEnabled = UserDefaults.standard.bool(forKey: "isTrioRemoteControlEnabled")
guard isTrioRemoteControlEnabled else {
    await logError("Remote control is disabled in settings")
    return
}
```

### 2. Shared Secret Verification

```swift
let storedSecret = UserDefaults.standard.string(forKey: "trioRemoteControlSharedSecret") ?? ""
guard !storedSecret.isEmpty else {
    await logError("Shared secret is missing in settings")
    return
}
```

### 3. Timestamp Validation

Commands are rejected if older than 10 minutes or with future timestamps:

```swift
private let timeWindow: TimeInterval = 600  // 10 minutes

let currentTime = Date().timeIntervalSince1970
let timeDifference = currentTime - commandPayload.timestamp

if timeDifference > timeWindow {
    await logError("Message is too old (\(Int(timeDifference)) seconds)")
    return
}

if timeDifference < -timeWindow {
    await logError("Message has invalid future timestamp")
    return
}
```

### 4. Bolus Safety Checks

| Check | Condition | Action |
|-------|-----------|--------|
| Max Bolus | `bolusAmount > maxBolus` | Reject |
| Max IOB | `currentIOB + bolusAmount > maxIOB` | Reject |
| Recent Boluses | Recent boluses ≥ 20% of requested | Reject |

---

## Response Notifications

Trio can send response notifications back to the caregiver app:

```swift
// trio:RemoteNotificationResponseManager.swift
await RemoteNotificationResponseManager.shared.sendResponseNotification(
    to: returnInfo,
    commandType: payload.commandType,
    success: true,
    message: "Bolus started"
)
```

---

## Settings

| Setting Key | Purpose |
|-------------|---------|
| `isTrioRemoteControlEnabled` | Master toggle for remote commands |
| `trioRemoteControlSharedSecret` | Shared encryption secret |

---

## Legacy: Nightscout Announcements

**Note**: The previous Nightscout Announcement-based remote command system has been deprecated in favor of the secure APNS-based TrioRemoteControl system. The old system used `enteredBy: remote` announcements with plaintext commands like `bolus: 2.5`.

---

## Comparison with Other Systems

| Feature | Trio | Loop | AAPS |
|---------|------|------|------|
| Transport | APNS Push | APNS Push | NS Commands |
| Encryption | AES-256-GCM | Apple E2E | HMAC signing |
| Authentication | Shared secret | Apple Push Token | API secret |
| Remote Bolus | Yes | Yes | Yes |
| Remote Meal | Yes | No | Yes |
| Remote Override | Yes (by preset name) | Yes | Yes |
| Remote Temp Target | Yes | Via Override | Yes |
| Replay Protection | 10-min timestamp | Nonce | Timestamp |

---

## Creating Remote Commands

To send a remote command to Trio:

### 1. Configure Shared Secret

Both the caregiver app and Trio must use the same shared secret.

### 2. Create Command Payload

```json
{
  "commandType": "bolus",
  "timestamp": 1705420800,
  "bolusAmount": 2.5
}
```

### 3. Encrypt Payload

```python
from Crypto.Cipher import AES
import hashlib
import os
import base64
import json

shared_secret = "your_shared_secret"
key = hashlib.sha256(shared_secret.encode()).digest()
nonce = os.urandom(12)

payload = json.dumps({
    "commandType": "bolus",
    "timestamp": time.time(),
    "bolusAmount": 2.5
}).encode()

cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
ciphertext, tag = cipher.encrypt_and_digest(payload)
encrypted = base64.b64encode(nonce + ciphertext + tag).decode()
```

### 4. Send via APNS

Send the encrypted payload via Apple Push Notification Service to the Trio device.

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-16 | Agent | Complete rewrite for TrioRemoteControl APNS system (dev branch 0.6.0) |
| 2026-01-16 | Agent | Initial remote commands documentation (Announcements system) |
