# LoopFollow Remote Commands Protocol

This document details the three remote command mechanisms supported by LoopFollow for sending commands to Loop and Trio AID systems.

---

## Executive Summary

LoopFollow implements three distinct remote command mechanisms, each targeting different AID systems with different security models and capabilities.

| Remote Type | Target AID | Transport | Security | Commands |
|-------------|------------|-----------|----------|----------|
| **Loop APNS** | Loop | Direct APNS | TOTP + JWT | Bolus, Carbs, Overrides |
| **TRC (Trio Remote Control)** | Trio | Direct APNS | AES-256-GCM + JWT | 6 command types |
| **Nightscout** | Trio | Nightscout API | Token (careportal role) | Temp Target only |

---

## Source Files

| File | Purpose |
|------|---------|
| `LoopFollow/Remote/RemoteType.swift` | Remote type enumeration |
| `LoopFollow/Remote/RemoteViewController.swift` | Remote view controller routing |
| **Loop APNS** | |
| `LoopFollow/Remote/LoopAPNS/LoopAPNSService.swift` | APNS communication service |
| `LoopFollow/Remote/LoopAPNS/LoopAPNSRemoteView.swift` | UI for Loop APNS |
| `LoopFollow/Remote/LoopAPNS/LoopAPNSBolusView.swift` | Bolus command UI |
| `LoopFollow/Remote/LoopAPNS/LoopAPNSCarbsView.swift` | Carbs command UI |
| `LoopFollow/Remote/LoopAPNS/TOTPService.swift` | TOTP code management |
| **TRC (Trio Remote Control)** | |
| `LoopFollow/Remote/TRC/PushNotificationManager.swift` | TRC APNS implementation |
| `LoopFollow/Remote/TRC/SecureMessenger.swift` | AES-256-GCM encryption |
| `LoopFollow/Remote/TRC/TRCCommandType.swift` | Command type enumeration |
| `LoopFollow/Remote/TRC/PushMessage.swift` | Payload structures |
| `LoopFollow/Remote/TRC/TrioRemoteControlView.swift` | TRC main UI |
| **Nightscout** | |
| `LoopFollow/Remote/TRC/TrioNightscoutRemoteController.swift` | NS API commands |
| `LoopFollow/Remote/Nightscout/TrioNightscoutRemoteView.swift` | NS remote UI |

---

## Remote Type Selection

```swift
// loopfollow:LoopFollow/Remote/RemoteType.swift#L6-L11
enum RemoteType: String, Codable {
    case none = "None"
    case nightscout = "Nightscout"
    case trc = "Trio Remote Control"
    case loopAPNS = "Loop APNS"
}
```

### UI Routing Logic

```swift
// loopfollow:LoopFollow/Remote/RemoteViewController.swift#L33-L60
if remoteType == .nightscout {
    switch Storage.shared.device.value {
    case "Trio":
        remoteView = AnyView(TrioNightscoutRemoteView())
    default:
        remoteView = AnyView(NoRemoteView())  // Loop not supported for NS remote
    }
} else if remoteType == .trc {
    if Storage.shared.device.value != "Trio" {
        // TRC only for Trio
    } else {
        let trioRemoteControlView = TrioRemoteControlView(...)
    }
} else if remoteType == .loopAPNS {
    hostingController = UIHostingController(rootView: AnyView(LoopAPNSRemoteView()))
}
```

---

## 1. Loop APNS Remote Commands

Direct Apple Push Notification to Loop with TOTP authentication.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Loop APNS Remote Flow                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  LoopFollow                    APNS                         Loop            │
│  ─────────                     ────                         ────            │
│      │                          │                             │             │
│      │ 1. Generate JWT token    │                             │             │
│      │    (Team ID + Key ID)    │                             │             │
│      │                          │                             │             │
│      │ 2. Build payload with:   │                             │             │
│      │    - TOTP code           │                             │             │
│      │    - Command data        │                             │             │
│      │    - Expiration          │                             │             │
│      │                          │                             │             │
│      │ 3. POST to APNS ─────────┼────────────────────────────>│             │
│      │    /3/device/{token}     │                             │             │
│      │                          │                             │             │
│      │                          │ 4. Push notification ──────>│             │
│      │                          │                             │             │
│      │                          │                             │ 5. Validate │
│      │                          │                             │    TOTP     │
│      │                          │                             │             │
│      │                          │                             │ 6. Execute  │
│      │                          │                             │    command  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Command Types

| Command | Description | Parameters |
|---------|-------------|------------|
| **Bolus** | Remote insulin bolus | `bolus-entry` (units) |
| **Carbs** | Remote carb entry | `carbs-entry` (grams), `absorption-time` (hours), `start-time` |
| **Override** | Activate override preset | (via Nightscout treatment) |

### TOTP Authentication

```swift
// loopfollow:LoopFollow/Remote/LoopAPNS/TOTPService.swift#L7-L36
class TOTPService {
    static let shared = TOTPService()
    
    // Check if current TOTP already used (prevent replay)
    func isTOTPBlocked(qrCodeURL: String) -> Bool {
        guard let currentTOTP = TOTPGenerator.extractOTPFromURL(qrCodeURL) else {
            return false
        }
        return currentTOTP == Observable.shared.lastSentTOTP.value
    }
    
    // Mark TOTP as used after successful send
    func markTOTPAsUsed(qrCodeURL: String) {
        if let currentTOTP = TOTPGenerator.extractOTPFromURL(qrCodeURL) {
            Observable.shared.lastSentTOTP.set(currentTOTP)
        }
    }
}
```

### Bolus Payload Structure

```swift
// loopfollow:LoopFollow/Remote/LoopAPNS/LoopAPNSService.swift#L180-L230
func sendBolusViaAPNS(payload: LoopAPNSPayload, completion: ...) {
    let now = Date()
    let expiration = Date(timeIntervalSinceNow: 5 * 60)  // 5 minute expiry
    
    let finalPayload = [
        "bolus-entry": bolusAmount,
        "otp": String(payload.otp),
        "remote-address": "LoopFollow",
        "notes": "Sent via LoopFollow APNS",
        "entered-by": "LoopFollow",
        "sent-at": formatDateForAPNS(now),
        "expiration": formatDateForAPNS(expiration),
        "alert": "Remote Bolus Entry: \(bolusAmount) U",
    ] as [String: Any]
}
```

### Carbs Payload Structure

```swift
// loopfollow:LoopFollow/Remote/LoopAPNS/LoopAPNSService.swift#L114-L174
func sendCarbsViaAPNS(payload: LoopAPNSPayload, completion: ...) {
    let finalPayload = [
        "carbs-entry": carbsAmount,
        "absorption-time": absorptionTime,  // hours
        "otp": String(payload.otp),
        "remote-address": "LoopFollow",
        "notes": "Sent via LoopFollow APNS",
        "entered-by": "LoopFollow",
        "sent-at": formatDateForAPNS(now),
        "expiration": formatDateForAPNS(expiration),
        "start-time": formatDateForAPNS(startTime),
        "alert": "Remote Carbs Entry: \(carbsAmount) grams",
    ] as [String: Any]
}
```

### APNS Request Structure

```swift
// loopfollow:LoopFollow/Remote/LoopAPNS/LoopAPNSService.swift#L299-L361
var request = URLRequest(url: requestURL)
request.httpMethod = "POST"
request.setValue("application/json", forHTTPHeaderField: "content-type")
request.setValue("bearer \(jwt)", forHTTPHeaderField: "authorization")
request.setValue(bundleIdentifier, forHTTPHeaderField: "apns-topic")
request.setValue("alert", forHTTPHeaderField: "apns-push-type")
request.setValue("10", forHTTPHeaderField: "apns-priority")  // High priority

let apnsPayload = [
    "aps": [
        "alert": payload["alert"] as? String ?? "",
        "content-available": 1,
        "interruption-level": "time-sensitive",
    ],
    // ... custom payload fields
]
```

### Required Configuration

| Setting | Description | Source |
|---------|-------------|--------|
| `keyId` | APNS Key ID (10 chars) | Apple Developer |
| `apnsKey` | APNS private key (PEM) | Apple Developer |
| `deviceToken` | Loop device token | From Loop profile |
| `bundleId` | Loop bundle identifier | From Loop profile |
| `teamId` | Apple Team ID | Apple Developer |
| `loopAPNSQrCodeURL` | TOTP secret URL | From Loop QR code |
| `productionEnvironment` | Production vs sandbox | Match Loop build |

---

## 2. TRC (Trio Remote Control)

Direct APNS to Trio with AES-256-GCM encryption.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TRC Remote Flow                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  LoopFollow                    APNS                         Trio            │
│  ─────────                     ────                         ────            │
│      │                          │                             │             │
│      │ 1. Generate JWT token    │                             │             │
│      │                          │                             │             │
│      │ 2. Build CommandPayload  │                             │             │
│      │    (user, type, params)  │                             │             │
│      │                          │                             │             │
│      │ 3. Encrypt with          │                             │             │
│      │    AES-256-GCM           │                             │             │
│      │    (shared secret)       │                             │             │
│      │                          │                             │             │
│      │ 4. POST encrypted ───────┼────────────────────────────>│             │
│      │    payload to APNS       │                             │             │
│      │                          │                             │             │
│      │                          │ 5. Push notification ──────>│             │
│      │                          │    (background)             │             │
│      │                          │                             │             │
│      │                          │                             │ 6. Decrypt  │
│      │                          │                             │    with     │
│      │                          │                             │    shared   │
│      │                          │                             │    secret   │
│      │                          │                             │             │
│      │                          │                             │ 7. Validate │
│      │                          │                             │    timestamp│
│      │                          │                             │             │
│      │                          │                             │ 8. Execute  │
│      │                          │                             │    command  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Command Types

```swift
// loopfollow:LoopFollow/Remote/TRC/TRCCommandType.swift#L6-L13
enum TRCCommandType: String, Encodable {
    case bolus
    case tempTarget = "temp_target"
    case cancelTempTarget = "cancel_temp_target"
    case meal
    case startOverride = "start_override"
    case cancelOverride = "cancel_override"
}
```

### Command Summary

| Command | Type | Parameters |
|---------|------|------------|
| **Bolus** | `bolus` | `bolusAmount` (Decimal) |
| **Temp Target** | `temp_target` | `target` (Int, mg/dL), `duration` (Int, minutes) |
| **Cancel Temp Target** | `cancel_temp_target` | - |
| **Meal** | `meal` | `carbs`, `protein`, `fat` (Int, grams), `bolusAmount`?, `scheduledTime`? |
| **Start Override** | `start_override` | `overrideName` (String) |
| **Cancel Override** | `cancel_override` | - |

### Command Payload Structure

```swift
// loopfollow:LoopFollow/Remote/TRC/PushMessage.swift#L17-L64
struct CommandPayload: Encodable {
    var user: String               // User identifier
    var commandType: TRCCommandType
    var timestamp: TimeInterval    // Unix timestamp (replay protection)
    
    var bolusAmount: Decimal?
    var target: Int?
    var duration: Int?
    var carbs: Int?
    var protein: Int?
    var fat: Int?
    var overrideName: String?
    var scheduledTime: TimeInterval?
    var returnNotification: ReturnNotificationInfo?
    
    struct ReturnNotificationInfo: Encodable {
        let productionEnvironment: Bool
        let deviceToken: String
        let bundleId: String
        let teamId: String
        let keyId: String
        let apnsKey: String
    }
}
```

### AES-256-GCM Encryption

```swift
// loopfollow:LoopFollow/Remote/TRC/SecureMessenger.swift#L8-L38
struct SecureMessenger {
    private let sharedKey: [UInt8]
    
    init?(sharedSecret: String) {
        guard let secretData = sharedSecret.data(using: .utf8) else {
            return nil
        }
        // Derive 256-bit key from shared secret using SHA-256
        sharedKey = Array(secretData.sha256())
    }
    
    func encrypt<T: Encodable>(_ object: T) throws -> String {
        let dataToEncrypt = try JSONEncoder().encode(object)
        
        // Generate 12-byte random nonce
        guard let nonce = generateSecureRandomBytes(count: 12) else {
            throw NSError(...)
        }
        
        // AES-GCM encryption (combined mode includes auth tag)
        let gcm = GCM(iv: nonce, mode: .combined)
        let aes = try AES(key: sharedKey, blockMode: gcm, padding: .noPadding)
        let encryptedBytes = try aes.encrypt(Array(dataToEncrypt))
        
        // Prepend nonce to ciphertext
        let finalData = Data(nonce + encryptedBytes)
        return finalData.base64EncodedString()
    }
}
```

### Encrypted Push Message

```swift
// loopfollow:LoopFollow/Remote/TRC/PushMessage.swift#L6-L15
struct EncryptedPushMessage: Encodable {
    let aps: [String: Int] = ["content-available": 1]  // Background push
    let encryptedData: String  // Base64-encoded encrypted payload
    
    enum CodingKeys: String, CodingKey {
        case aps
        case encryptedData = "encrypted_data"
    }
}
```

### APNS Request Structure

```swift
// loopfollow:LoopFollow/Remote/TRC/PushNotificationManager.swift#L256-L265
var request = URLRequest(url: url)
request.httpMethod = "POST"
request.setValue("bearer \(jwt)", forHTTPHeaderField: "authorization")
request.setValue("application/json", forHTTPHeaderField: "content-type")
request.setValue("10", forHTTPHeaderField: "apns-priority")
request.setValue("0", forHTTPHeaderField: "apns-expiration")
request.setValue(bundleId, forHTTPHeaderField: "apns-topic")
request.setValue("background", forHTTPHeaderField: "apns-push-type")

request.httpBody = try JSONEncoder().encode(finalMessage)
```

### Required Configuration

| Setting | Description |
|---------|-------------|
| `sharedSecret` | Shared secret for AES key derivation |
| `deviceToken` | Trio device APNS token |
| `bundleId` | Trio bundle identifier |
| `teamId` | Apple Team ID |
| `keyId` | APNS Key ID |
| `apnsKey` | APNS private key (PEM) |
| `user` | User identifier |
| `productionEnvironment` | Production vs sandbox |

---

## 3. Nightscout Remote Commands

API-based temp target control via Nightscout treatments.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Nightscout Remote Flow                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  LoopFollow                  Nightscout                      Trio           │
│  ─────────                   ──────────                      ────           │
│      │                          │                             │             │
│      │ 1. POST /api/v1/         │                             │             │
│      │    treatments            │                             │             │
│      │    (with token)  ────────┼────────>                    │             │
│      │                          │                             │             │
│      │                          │ 2. Store treatment ─────────│             │
│      │                          │    as "Temporary Target"    │             │
│      │                          │                             │             │
│      │                          │                             │             │
│      │                          │ 3. Trio polls treatments ──>│             │
│      │                          │    (or websocket push)      │             │
│      │                          │                             │             │
│      │                          │                             │ 4. Parse    │
│      │                          │                             │    and      │
│      │                          │                             │    apply    │
│      │                          │                             │    target   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Supported Commands

| Command | Description | Parameters |
|---------|-------------|------------|
| **Temp Target** | Set temporary BG target | `targetTop`, `targetBottom`, `duration` |
| **Cancel Temp Target** | Cancel active temp target | `duration: 0` |

### Treatment Payload Structure

```swift
// loopfollow:LoopFollow/Remote/TRC/TrioNightscoutRemoteController.swift#L7-L50
class TrioNightscoutRemoteController {
    func sendTempTarget(newTarget: HKQuantity, duration: HKQuantity, completion: ...) {
        let tempTargetBody: [String: Any] = [
            "enteredBy": "LoopFollow",
            "eventType": "Temporary Target",
            "reason": "Manual",
            "targetTop": newTarget.doubleValue(for: .milligramsPerDeciliter),
            "targetBottom": newTarget.doubleValue(for: .milligramsPerDeciliter),
            "duration": Int(duration.doubleValue(for: .minute())),
            "created_at": ISO8601DateFormatter().string(from: Date()),
        ]
        
        let response = try await NightscoutUtils.executePostRequest(
            eventType: .treatments,
            body: tempTargetBody
        )
    }
    
    func cancelExistingTarget(completion: ...) {
        let tempTargetBody: [String: Any] = [
            "enteredBy": "LoopFollow",
            "eventType": "Temporary Target",
            "reason": "Manual",
            "duration": 0,  // Duration 0 = cancel
            "created_at": ISO8601DateFormatter().string(from: Date()),
        ]
        
        let response = try await NightscoutUtils.executePostRequest(...)
    }
}
```

### Required Configuration

| Setting | Description |
|---------|-------------|
| Nightscout URL | Nightscout server address |
| API Token | Token with `careportal` and `readable` roles |

### Limitations

- **Trio only** - Loop does not read temp targets from Nightscout treatments
- **Temp Target only** - No bolus/carbs/override support via NS
- **No OTP** - Relies on API token security only

---

## Comparison Matrix

| Feature | Loop APNS | TRC | Nightscout |
|---------|-----------|-----|------------|
| **Target AID** | Loop | Trio | Trio |
| **Transport** | Direct APNS | Direct APNS | HTTPS |
| **Encryption** | None (TLS) | AES-256-GCM | None (TLS) |
| **Authentication** | TOTP + JWT | Timestamp + JWT | API Token |
| **Replay Protection** | TOTP blocking | Timestamp validation | None |
| **Bolus** | Yes | Yes | No |
| **Carbs** | Yes | Yes (with protein/fat) | No |
| **Temp Target** | No | Yes | Yes |
| **Override** | Yes (via NS) | Yes | No |
| **Meal with Macro** | No | Yes (carbs/protein/fat) | No |
| **Scheduled Commands** | No | Yes (`scheduledTime`) | No |
| **Return Notification** | Planned | Yes | No |

---

## Security Comparison

| Aspect | Loop APNS | TRC | Nightscout |
|--------|-----------|-----|------------|
| **Transport Security** | TLS | TLS | TLS |
| **Message Encryption** | None | AES-256-GCM | None |
| **Authentication** | TOTP (6-digit, 30s) | Shared secret | API token |
| **Replay Protection** | TOTP period (30s) | Timestamp + decryption | None |
| **Key Exchange** | QR code | Manual sharing | Token in URL |
| **Credential Storage** | Keychain | Keychain | UserDefaults |

### Security Notes

1. **Loop APNS**: Uses standard TOTP (RFC 6238) but override commands skip OTP validation (GAP-REMOTE-001)
2. **TRC**: Most secure - AES-256-GCM provides confidentiality and integrity; shared secret derived via SHA-256
3. **Nightscout**: Least secure - relies solely on token in headers; anyone with token can send commands

---

## Error Handling

### Common APNS Error Codes

| Code | Meaning | Resolution |
|------|---------|------------|
| 200 | Success | - |
| 400 | Bad request | Check payload format, device token |
| 403 | Auth error | Verify JWT, APNS key, permissions |
| 410 | Invalid token | Device token expired/invalid |
| 429 | Rate limited | Wait before retrying |

### Nightscout Error Handling

```swift
// loopfollow:LoopFollow/Remote/Nightscout/TrioNightscoutRemoteView.swift#L48-L52
if !nsWriteAuth.value {
    ErrorMessageView(
        message: "Please update your token to include the 'careportal' and 'readable' roles..."
    )
}
```

---

## Cross-References

- [LoopCaregiver Remote Commands](../loopcaregiver/remote-commands.md) - Compare with LC's Remote 2.0
- [LoopCaregiver Authentication](../loopcaregiver/authentication.md) - QR code linking comparison
- [Remote Commands Cross-System](../../docs/10-domain/remote-commands-comparison.md) - Trio/Loop/AAPS comparison
- [Nightscout API Comparison](../../docs/10-domain/nightscout-api-comparison.md) - API v1 vs v3

---

## Gaps Identified

| Gap ID | Description |
|--------|-------------|
| GAP-LF-005 | No command status tracking (fire-and-forget) |
| GAP-LF-006 | No command history or audit log |
| GAP-LF-007 | TRC return notification not fully implemented |
| GAP-LF-008 | Nightscout lacks OTP security for temp targets |
| GAP-LF-009 | No unified command abstraction across remote types |

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial deep dive documentation |
