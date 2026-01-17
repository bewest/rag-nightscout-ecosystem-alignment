# Remote Commands Cross-System Comparison

This document analyzes how caregivers remotely control AID systems across Trio, Loop, and AAPS, focusing on security models, command types, and safety limits.

---

## Executive Summary

| Aspect | Trio | Loop | AAPS |
|--------|------|------|------|
| **Transport** | APNS Push | APNS Push | SMS |
| **Encryption** | AES-256-GCM | None (plaintext JSON) | None |
| **Authentication** | Shared secret | TOTP OTP | Phone whitelist + TOTP + PIN |
| **Command Types** | 6 | 4 | 13+ |
| **OTP Required for Bolus** | N/A (encryption) | Yes | Yes |
| **OTP Required for Override** | N/A (encryption) | **No** | N/A |
| **Replay Protection** | 10-min timestamp | Expiration + dedup | Timeout + min distance |

**Key Finding**: Trio uses symmetric encryption for all commands; Loop uses OTP only for high-risk commands (bolus/carbs) but not overrides; AAPS uses SMS with OTP+PIN for all commands.

---

## Source Files

### Trio
| File | Purpose |
|------|---------|
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl.swift` | Main remote command handler |
| `trio:Trio/Sources/Services/RemoteControl/SecureMessenger.swift` | AES-GCM encryption/decryption |
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+Bolus.swift` | Bolus command processing |
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+Meal.swift` | Meal command processing |
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+TempTarget.swift` | Temp target commands |
| `trio:Trio/Sources/Services/RemoteControl/TrioRemoteControl+Override.swift` | Override commands |

### Loop
| File | Purpose |
|------|---------|
| `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/V1/RemoteCommandSourceV1.swift` | Remote command processor |
| `loop:NightscoutService/NightscoutServiceKit/OTPManager.swift` | TOTP one-time password validation |
| `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Validators/RemoteCommandValidator.swift` | Expiration and OTP validation |
| `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/V1/Notifications/*.swift` | Notification type definitions |
| `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/Actions/Action.swift` | Action type enum |

### AAPS
| File | Purpose |
|------|---------|
| `aaps:plugins/main/src/main/kotlin/app/aaps/plugins/main/general/smsCommunicator/SmsCommunicatorPlugin.kt` | SMS command processor (1333 lines) |
| `aaps:plugins/main/src/main/kotlin/app/aaps/plugins/main/general/smsCommunicator/otp/OneTimePassword.kt` | TOTP implementation |
| `aaps:plugins/main/src/main/kotlin/app/aaps/plugins/main/general/smsCommunicator/AuthRequest.kt` | OTP verification flow |
| `aaps:core/data/src/main/kotlin/app/aaps/core/data/ue/Sources.kt` | Command source tracking |

---

## Security Models

### Trio: Symmetric Encryption (AES-256-GCM)

**Architecture**:
```
Caregiver App → Encrypt(payload, shared_secret) → APNS → Trio → Decrypt → Execute
```

**Encryption Details**:
```swift
// SecureMessenger.swift
struct SecureMessenger {
    private let sharedKey: [UInt8]  // SHA256(shared_secret)
    
    init?(sharedSecret: String) {
        guard let secretData = sharedSecret.data(using: .utf8) else { return nil }
        sharedKey = Array(secretData.sha256())  // 256-bit key from SHA256
    }
    
    func decrypt(base64EncodedString: String) throws -> CommandPayload {
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

| Parameter | Value |
|-----------|-------|
| Algorithm | AES-256 |
| Mode | GCM (Galois/Counter Mode) |
| Key Derivation | SHA256 of shared secret |
| Nonce Size | 12 bytes |
| Auth Tag | Included in ciphertext (combined mode) |

**Strengths**:
- All commands encrypted (confidentiality)
- GCM provides authentication (integrity)
- Single shared secret for all commands

**Weaknesses**:
- No key rotation mechanism visible
- Shared secret stored in UserDefaults (not Keychain)
- No forward secrecy

---

### Loop: TOTP One-Time Password

**Architecture**:
```
Caregiver App → Create notification with OTP → APNS → Loop → Validate OTP → Execute
```

**OTP Implementation**:
```swift
// OTPManager.swift
public class OTPManager {
    let algorithm: Generator.Algorithm = .sha1
    let issuerName = "Loop"
    var tokenPeriod: TimeInterval = 30  // 30-second periods
    var passwordDigitCount = 6
    let maxOTPsToAccept: Int = 2  // Accept current + 1 previous
    
    public func validatePassword(password: String, deliveryDate: Date?) throws {
        guard password.count == passwordDigitCount else {
            throw OTPValidationError.invalidFormat(otp: password)
        }
        
        guard try isValidPassword(password) else {
            let recentOTPs = try otpsSince(date: nowDateSource().addingTimeInterval(-60*60))
            let otpIsExpired = recentOTPs.contains(where: {$0.password == password})
            if otpIsExpired {
                throw OTPValidationError.expired(deliveryDate: deliveryDate, maxOTPsToAccept: maxOTPsToAccept)
            } else {
                throw OTPValidationError.incorrectOTP(otp: password)
            }
        }
        
        let recentlyUsedOTPs = secretStore.recentAcceptedPasswords()
        guard !recentlyUsedOTPs.contains(password) else {
            throw OTPValidationError.previouslyUsed(otp: password)
        }
        
        try storeUsedPassword(password)
    }
}
```

| Parameter | Value |
|-----------|-------|
| Algorithm | HMAC-SHA1 |
| Digits | 6 |
| Period | 30 seconds |
| Window | 2 codes (current + previous) |
| Replay Protection | Track recently used passwords |
| Key Storage | Keychain |

**Critical Security Finding: OTP Not Required for Overrides**

```swift
// OverrideRemoteNotification.swift
func otpValidationRequired() -> Bool {
    return false  // ⚠️ No OTP required!
}

// OverrideCancelRemoteNotification.swift
func otpValidationRequired() -> Bool {
    return false  // ⚠️ No OTP required!
}

// vs BolusRemoteNotification.swift
func otpValidationRequired() -> Bool {
    return true  // OTP required
}
```

**Implications**:
- Anyone with Nightscout API access can activate/cancel overrides without OTP
- Override can significantly impact insulin delivery via ISF/CR adjustments
- This is documented as GAP-REMOTE-001

---

### AAPS: SMS with TOTP + PIN

**Architecture**:
```
Caregiver Phone → SMS command → Android → AAPS → Verify phone + OTP+PIN → Execute
```

**Multi-Layer Authentication**:

1. **Phone Number Whitelist**:
```kotlin
// SmsCommunicatorPlugin.kt
var allowedNumbers: MutableList<String> = ArrayList()

fun isAllowedNumber(number: String): Boolean {
    for (num in allowedNumbers) {
        if (num == number) return true
    }
    return false
}

fun processSms(receivedSms: Sms) {
    if (!isAllowedNumber(receivedSms.phoneNumber)) {
        aapsLogger.debug(LTag.SMS, "Ignoring SMS from: " + receivedSms.phoneNumber + ". Sender not allowed")
        receivedSms.ignored = true
        return
    }
    // ... process command
}
```

2. **TOTP + PIN Verification**:
```kotlin
// OneTimePassword.kt
fun checkOTP(otp: String): OneTimePasswordValidationResult {
    val normalisedOtp = otp.replace(" ", "").replace("-", "").trim()

    if (pin.length < 3) {
        return OneTimePasswordValidationResult.ERROR_WRONG_PIN
    }

    if (normalisedOtp.length != (6 + pin.length)) {
        return OneTimePasswordValidationResult.ERROR_WRONG_LENGTH
    }

    // Extract PIN from end of OTP string
    if (normalisedOtp.substring(6) != pin) {
        return OneTimePasswordValidationResult.ERROR_WRONG_PIN
    }

    val counter: Long = dateUtil.now() / 30000L
    val acceptableTokens = mutableListOf(generateOneTimePassword(counter))
    for (i in 0 until Constants.OTP_ACCEPT_OLD_TOKENS_COUNT) {
        acceptableTokens.add(generateOneTimePassword(counter - i - 1))
    }
    val candidateOtp = normalisedOtp.substring(0, 6)

    if (acceptableTokens.any { candidate -> candidateOtp == candidate }) {
        return OneTimePasswordValidationResult.OK
    }

    return OneTimePasswordValidationResult.ERROR_WRONG_OTP
}
```

| Parameter | Value |
|-----------|-------|
| Algorithm | HMAC (via HmacOneTimePasswordGenerator) |
| Digits | 6 (OTP) + 3+ (PIN) |
| Period | 30 seconds |
| Key Length | 160 bits (Constants.OTP_GENERATED_KEY_LENGTH_BITS) |
| Replay Protection | Command timeout + min bolus distance |

3. **Two-Phase Confirmation**:
```kotlin
// AuthRequest.kt
fun action(codeReceived: String) {
    if (processed) return
    if (!codeIsValid(codeReceived)) {
        processed = true
        smsCommunicator.sendSMS(Sms(requester.phoneNumber, rh.gs(R.string.sms_wrong_code)))
        return
    }
    if (dateUtil.now() - date < Constants.SMS_CONFIRM_TIMEOUT) {
        processed = true
        if (action.pumpCommand) {
            // Wait for command queue to empty (max 3 min)
            while (start + T.mins(3).msecs() > dateUtil.now()) {
                if (commandQueue.size() == 0) break
                SystemClock.sleep(100)
            }
        }
        action.run()
    }
}
```

---

## Command Type Comparison

### Trio Commands (6 types)

```swift
enum CommandType: String, Codable {
    case bolus
    case meal              // Carbs + optional bolus
    case tempTarget
    case cancelTempTarget
    case startOverride     // By preset name
    case cancelOverride
}

struct CommandPayload: Codable {
    let commandType: CommandType
    let timestamp: TimeInterval       // Unix epoch for replay protection
    
    let bolusAmount: Decimal?
    let carbAmount: Decimal?
    let fatAmount: Decimal?
    let proteinAmount: Decimal?
    let targetBG: Decimal?
    let duration: Decimal?            // Minutes
    let overrideName: String?
    let returnNotification: ReturnNotificationInfo?
}
```

### Loop Commands (4 types)

```swift
public enum Action: Codable {
    case temporaryScheduleOverride(OverrideAction)
    case cancelTemporaryOverride(OverrideCancelAction)
    case bolusEntry(BolusAction)
    case carbsEntry(CarbAction)
}

// BolusAction
public struct BolusAction: Codable {
    public let amountInUnits: Double
}

// CarbAction
public struct CarbAction {
    let amountInGrams: Double
    let absorptionTime: TimeInterval?
    let foodType: String?
    let startDate: Date?
}

// OverrideAction
public struct OverrideAction {
    let name: String
    let durationTime: TimeInterval?
    let remoteAddress: String
}
```

### AAPS SMS Commands (13+ types)

```kotlin
private val commands = mapOf(
    "BG" to "BG",
    "LOOP" to "LOOP STOP/DISABLE/RESUME/STATUS/CLOSED/LGS\nLOOP SUSPEND 20",
    "AAPSCLIENT" to "AAPSCLIENT RESTART",
    "PUMP" to "PUMP\nPUMP CONNECT\nPUMP DISCONNECT 30\n",
    "BASAL" to "BASAL STOP/CANCEL\nBASAL 0.3\nBASAL 0.3 20\nBASAL 30%\nBASAL 30% 20\n",
    "BOLUS" to "BOLUS 1.2\nBOLUS 1.2 MEAL",
    "EXTENDED" to "EXTENDED STOP/CANCEL\nEXTENDED 2 120",
    "CAL" to "CAL 5.6",
    "PROFILE" to "PROFILE STATUS/LIST\nPROFILE 1\nPROFILE 2 30",
    "TARGET" to "TARGET MEAL/ACTIVITY/HYPO/STOP",
    "SMS" to "SMS DISABLE/STOP",
    "CARBS" to "CARBS 12\nCARBS 12 23:05\nCARBS 12 11:05PM",
    "HELP" to "HELP\nHELP command",
    "RESTART" to "RESTART\nRestart AAPS"
)
```

### Command Feature Matrix

| Command | Trio | Loop | AAPS |
|---------|------|------|------|
| Remote Bolus | ✅ | ✅ | ✅ |
| Remote Carbs | ✅ (via meal) | ✅ | ✅ |
| Remote Override | ✅ (by name) | ✅ (by name) | ❌ |
| Cancel Override | ✅ | ✅ | ❌ |
| Remote Temp Target | ✅ | ❌ (via override) | ✅ (preset only) |
| Cancel Temp Target | ✅ | ❌ | ✅ |
| Remote Basal | ❌ | ❌ | ✅ |
| Extended Bolus | ❌ | ❌ | ✅ |
| Loop Control | ❌ | ❌ | ✅ (suspend/resume/disable) |
| Pump Control | ❌ | ❌ | ✅ (connect/disconnect) |
| Profile Switch | ❌ | ❌ | ✅ |
| CGM Calibration | ❌ | ❌ | ✅ |
| Status Query | ❌ | ❌ | ✅ |

---

## Safety Limits

### Trio Safety Checks

```swift
// TrioRemoteControl+Bolus.swift
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
    
    // Safety check 3: Recent boluses (20% rule)
    let totalRecentBolus = try await fetchTotalRecentBolusAmount(since: commandTime)
    if totalRecentBolus >= bolusAmount * 0.2 {
        await logError("Recent boluses exceed 20% of requested amount")
        return
    }
    
    await apsManager.enactBolus(amount: Double(bolusAmount), isSMB: false)
}
```

| Check | Condition | Action |
|-------|-----------|--------|
| Max Bolus | `amount > maxBolus` | Reject |
| Max IOB | `currentIOB + amount > maxIOB` | Reject |
| Recent Boluses | `recent >= amount * 0.2` | Reject |

### Loop Safety Checks

Loop's remote command layer primarily validates authentication, not dosing limits:

```swift
// RemoteCommandValidator.swift
struct RemoteCommandValidator {
    func validate(remoteNotification: RemoteNotification) throws {
        try validateExpirationDate(remoteNotification: remoteNotification)
        if remoteNotification.otpValidationRequired() {
            try validateOTP(remoteNotification: remoteNotification)
        }
    }
    
    private func validateExpirationDate(remoteNotification: RemoteNotification) throws {
        guard let expirationDate = remoteNotification.expiration else {
            return  // Skip if no expiration
        }
        if nowDateSource() > expirationDate {
            throw NotificationValidationError.expiredNotification
        }
    }
}
```

Safety limits are enforced downstream in the dosing logic (LoopDataManager, etc.), not in the remote command layer.

### AAPS Safety Checks

```kotlin
// SmsCommunicatorPlugin.kt - Bolus command processing
"BOLUS" ->
    if (!remoteCommandsAllowed) 
        sendSMS(Sms(receivedSms.phoneNumber, rh.gs(R.string.smscommunicator_remote_command_not_allowed)))
    else if (commandQueue.bolusInQueue()) 
        sendSMS(Sms(receivedSms.phoneNumber, rh.gs(R.string.smscommunicator_another_bolus_in_queue)))
    else if (divided.size == 2 && dateUtil.now() - lastRemoteBolusTime < minDistance) 
        sendSMS(Sms(receivedSms.phoneNumber, rh.gs(R.string.smscommunicator_remote_bolus_not_allowed)))
    else if (divided.size == 2 && loop.runningMode.isSuspended()) 
        sendSMS(Sms(receivedSms.phoneNumber, rh.gs(app.aaps.core.ui.R.string.pumpsuspended)))
    else if (divided.size == 2 || divided.size == 3) 
        processBOLUS(divided, receivedSms)

// Minimum bolus distance
val minDistance =
    if (areMoreNumbers(preferences.get(StringKey.SmsAllowedNumbers)))
        T.mins(preferences.get(IntKey.SmsRemoteBolusDistance).toLong()).msecs()
    else Constants.remoteBolusMinDistance
```

| Check | Condition | Action |
|-------|-----------|--------|
| Remote Commands Enabled | `!remoteCommandsAllowed` | Reject with message |
| Bolus Already Queued | `commandQueue.bolusInQueue()` | Reject |
| Min Time Between Boluses | `now - lastRemoteBolusTime < minDistance` | Reject |
| Pump Suspended | `loop.runningMode.isSuspended()` | Reject |
| Constraint Checker | Applied downstream | Enforce max bolus, IOB, etc. |

---

## Replay Protection Comparison

### Trio: Timestamp Window

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

**Mechanism**: Commands must be within ±10 minutes of current time.

### Loop: Expiration + Deduplication

```swift
// RemoteCommandSourceV1.swift
func remoteNotificationWasReceived(_ notification: [String: AnyObject]) async {
    guard await !recentNotifications.isDuplicate(remoteNotification) else {
        return  // Prevent duplicate processing
    }
    try commandValidator.validate(remoteNotification: remoteNotification)
    // ...
}

// RecentNotifications actor
private actor RecentNotifications {
    private var recentNotifications = [RemoteNotification]()
    
    func isDuplicate(_ remoteNotification: RemoteNotification) -> Bool {
        if recentNotifications.contains(where: {remoteNotification.id == $0.id}) {
            return true
        }
        recentNotifications.append(remoteNotification)
        return false
    }
}
```

**Mechanism**: 
1. Expiration date validation
2. In-memory duplicate tracking by notification ID
3. OTP can only be used once (stored in Keychain)

### AAPS: Timeout + Min Distance

```kotlin
// AuthRequest.kt
if (dateUtil.now() - date < Constants.SMS_CONFIRM_TIMEOUT) {
    processed = true
    action.run()
} else {
    aapsLogger.debug(LTag.SMS, "Timed out SMS: " + requester.text)
}

// Bolus-specific
var lastRemoteBolusTime: Long = 0
if (dateUtil.now() - lastRemoteBolusTime < minDistance)
    // Reject
```

**Mechanism**:
1. Command timeout (Constants.SMS_CONFIRM_TIMEOUT)
2. Minimum distance between boluses (configurable)
3. `processed` flag prevents re-execution

---

## Transport Security Comparison

| Aspect | Trio | Loop | AAPS |
|--------|------|------|------|
| **Transport** | APNS | APNS | SMS |
| **Transport Encryption** | TLS (Apple) | TLS (Apple) | GSM/3G/4G carrier |
| **Payload Encryption** | AES-256-GCM | None | None |
| **Man-in-Middle** | Protected | Vulnerable* | Vulnerable* |
| **Requires Internet** | Yes (both ends) | Yes (both ends) | No (SMS only) |
| **Offline Operation** | No | No | Yes |

*Loop and AAPS rely on transport-layer security only; payload is plaintext.

---

## Key Security Gaps

### GAP-REMOTE-001: Loop Override Commands Not Protected by OTP

**Severity**: High

**Description**: Loop's override and cancel-override commands do not require OTP validation, meaning anyone with Nightscout API access can manipulate overrides.

**Evidence**:
```swift
// OverrideRemoteNotification.swift
func otpValidationRequired() -> Bool {
    return false
}
```

**Impact**: Overrides can significantly affect insulin delivery via ISF/CR adjustments, potentially causing hypo/hyperglycemia.

**Recommendation**: Require OTP for all commands that affect insulin dosing.

**Reference**: See [GAP-REMOTE-001 in gaps.md](../../traceability/gaps.md#gap-remote-001-remote-command-authorization-unverified) for full gap documentation.

### GAP-REMOTE-002: No Command Signing Across Systems

**Severity**: Medium

**Description**: None of the systems use cryptographic signatures to verify command origin. Trio uses symmetric encryption (provides integrity via GCM), but Loop and AAPS send commands in plaintext.

**Impact**: 
- Loop: Anyone with Nightscout access can forge commands
- AAPS: Phone number spoofing could bypass whitelist (though OTP still required)

**Recommendation**: Implement HMAC or asymmetric signatures for commands.

### GAP-REMOTE-003: No Key Rotation Mechanism

**Severity**: Low-Medium

**Description**: 
- Trio: Shared secret stored indefinitely
- Loop: OTP secret can be reset but no scheduled rotation
- AAPS: Similar to Loop

**Impact**: Long-lived secrets increase risk of compromise.

### GAP-REMOTE-004: Inconsistent Safety Enforcement Layer

**Severity**: Medium

**Description**: Trio enforces safety limits (max bolus, max IOB) in the remote command handler. Loop delegates to downstream dosing logic. AAPS uses ConstraintChecker.

**Impact**: Inconsistent behavior and harder to audit.

---

## Interoperability Considerations

### Command Normalization

A unified remote command schema would need to address:

| Field | Trio | Loop | AAPS |
|-------|------|------|------|
| Bolus Amount | `bolusAmount: Decimal` | `amountInUnits: Double` | Text parsing |
| Carbs | `carbAmount: Decimal` | `amountInGrams: Double` | Text parsing |
| Override | `overrideName: String` | `name: String` | N/A |
| Timestamp | `timestamp: TimeInterval` | `sentAt: Date?` | N/A (SMS timestamp) |
| Auth | Encrypted payload | `otp: String?` | OTP+PIN in reply SMS |

### Authentication Bridging

A unified system would need to support:
1. Symmetric encryption (Trio model)
2. TOTP validation (Loop/AAPS model)
3. Or: New mutual authentication protocol

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial comprehensive comparison based on source code analysis |
