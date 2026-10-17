# Remote Bolus Command Comparison

> **Sources**: Loop, AAPS, Trio, Nightscout  
> **Last Updated**: 2026-01-28  
> **Corrected 2026-10-09** against source; see [intent and workflow across the landscape](../30-design/platform/nightscout-intent-workflow-landscape-2026-10-09.md) §11.  
> **Corrected 2026-10-17** against source: the Trio architecture no longer routes commands through Nightscout, the Nightscout relay is shown sending to Loop only, and the summary table now shows Loop's optional response notification, matching GAP-REMOTE-004. Revisions read: cgm-remote-monitor `a8888f0d`, LoopWorkspace `548b332` (NightscoutService `2cef489`), Trio `0b29cd534`, LoopFollow `4a74b781`. See [technical control loops](../60-research/structures-2026-10-17/technical-loops.md) §4. Also 2026-10-17 (DOCS-REMOTE-FOLLOWUP): Trio's shared secret is configured in Trio and the sending app, not in Nightscout.

## Overview

Remote bolus commands allow caregivers to trigger insulin delivery from outside the AID app. This document compares how Loop, AAPS, Trio, and Nightscout handle these safety-critical commands.

## Command Flow Summary

| System | Channel | Auth | Encryption | Expiration |
|--------|---------|------|------------|------------|
| **Loop** | APNs push | OTP | TLS (APNs) | set by the sender (Nightscout: 5 minutes); Loop checks it only when present |
| **AAPS** | SMS | Passcode | None (SMS) | 15 min distance |
| **AAPS** | Wear OS | None (local) | Bluetooth | N/A |
| **Trio** | APNs push | Shared secret | AES-256 | Configurable |
| **Nightscout** | HTTP→APNs | API secret | TLS | 5 minutes |

---

## Loop (iOS)

### Architecture

```
Nightscout → APNs → Loop App → Pump
```

### Key Files

| File | Purpose |
|------|---------|
| `NightscoutServiceKit/RemoteCommands/V1/Notifications/BolusRemoteNotification.swift` | Bolus notification model |
| `NightscoutServiceKit/RemoteCommands/Validators/RemoteCommandValidator.swift` | OTP & expiration validation |
| `NightscoutServiceKit/RemoteCommands/V1/RemoteCommandSourceV1.swift` | Notification processing |

### Payload Structure

```json
{
  "bolus-entry": 2.5,
  "remote-address": "192.168.1.1",
  "otp": "123456",
  "sent-at": "2026-01-28T12:00:00Z",
  "expiration": "2026-01-28T12:05:00Z",
  "entered-by": "Caregiver"
}
```

### Validation Rules

| Rule | Implementation |
|------|----------------|
| **OTP Required** | `otpValidationRequired()` returns `true` for bolus |
| **Expiration** | 5 minutes from `sent-at` |
| **Duplicate Detection** | By notification ID |
| **Amount Validation** | Against max bolus setting |

### Security Model

- **OTP**: Time-based one-time password (shared secret)
- **Transport**: Apple Push Notification service (TLS)
- **Enrollment**: `deviceToken` + `bundleIdentifier` in profile

---

## AAPS (Android)

### Architecture

```
SMS → AAPS → Command Queue → Pump
Wear OS → DataLayer → AAPS → Command Queue → Pump
```

### Key Files

| File | Purpose |
|------|---------|
| `plugins/main/src/main/kotlin/.../SmsCommunicatorPlugin.kt` | SMS command processing |
| `wear/src/main/kotlin/.../BolusActivity.kt` | Wear OS bolus UI |
| `plugins/sync/src/main/kotlin/.../DataHandlerMobile.kt` | Wear command handler |
| `core/data/src/main/kotlin/.../Constants.kt` | Remote bolus constraints |

### SMS Command Format

```
BOLUS <amount> [MEAL]
```

Example: `BOLUS 2.5 MEAL` (triggers temp target)

### Validation Rules

| Rule | Value | Source |
|------|-------|--------|
| **Min Distance** | 15 minutes | `Constants.remoteBolusMinDistance` |
| **Configurable Distance** | 3-60 minutes | `IntKey.SmsRemoteBolusDistance` |
| **Passcode** | Required | SMS confirmation flow |
| **Constraints** | Max bolus | `applyBolusConstraints()` |

### Security Model

- **2-Step Confirmation**: Request → Passcode SMS → Execute
- **Distance Check**: Must wait `remoteBolusMinDistance` between remote boluses
- **Phone Whitelist**: Configurable allowed numbers
- **No encryption** on SMS channel

### Wear OS Flow

1. `BolusActivity` collects amount via `PlusMinusEditText`
2. Sends `ActionBolusPreCheck` via `EventWearToMobile`
3. `DataHandlerMobile.doBolus()` executes via `commandQueue.bolus()`

---

## Trio (iOS)

### Architecture

```
Sender app (e.g. LoopFollow) → APNs → Trio App → APSManager → Pump
```

The sender pushes directly to Apple Push Notification service (APNs); Nightscout does not relay Trio commands. Trio expects an AES-GCM encrypted `encrypted_data` payload (`Trio/Sources/Models/CommandPayload.swift:3-9`, Trio `0b29cd534`), and Nightscout's relay builds only Loop's payload (see [Nightscout](#nightscout-server) below). The sender observed in source is LoopFollow's Trio Remote Control, which posts to APNs itself (`LoopFollow/Remote/TRC/PushNotificationManager.swift:329-333`, LoopFollow `4a74b781`). Nightscout's part is to hold the APNs device token that Trio uploads to its profile (`Trio/Sources/Services/Network/Nightscout/NightscoutManager.swift:838-853`), which a sender can read.

### Key Files

| File | Purpose |
|------|---------|
| `Trio/Sources/Services/RemoteControl/TrioRemoteControl.swift` | Command dispatcher |
| `Trio/Sources/Services/RemoteControl/TrioRemoteControl+Bolus.swift` | Bolus validation |
| `Trio/Sources/Models/CommandPayload.swift` | Command structure |
| `Trio/Sources/Services/RemoteControl/RemoteNotificationResponseManager.swift` | Response notifications |

### Command Payload

```swift
struct CommandPayload {
    let commandType: CommandType  // .bolus, .tempTarget, .meal, etc.
    let bolusAmount: Decimal?
    let timestamp: TimeInterval
    let returnNotification: ReturnNotificationInfo?
}
```

### Validation Rules

| Rule | Implementation |
|------|----------------|
| **Max Bolus** | `bolusAmount > maxBolus` → reject |
| **Max IOB** | `(currentIOB + bolusAmount) > maxIOB` → reject |
| **20% Rule** | Recent boluses > 20% of request → reject |
| **Encryption** | AES-256 with shared secret |

### 20% Duplicate Protection

```swift
// Reject if boluses totaling >20% of requested amount
// have been delivered since command was sent
if totalRecentBolusAmount >= bolusAmount * 0.2 {
    // Reject command
}
```

### Security Model

- **Encryption**: AES-256 via `SecureMessenger`
- **Shared Secret**: generated and stored in Trio, and entered by hand in the sending app (e.g. LoopFollow); Trio does not upload it to Nightscout, which receives only Trio's device token, bundle and team identifiers in the profile (Trio `0b29cd534`: `RemoteControlConfigStateModel.swift:7-37`, `TrioRemoteControl.swift:29`, `NightscoutManager.swift:838-853`)
- **Response Notifications**: Sends delivery status back via APNs
- **Timestamp Validation**: Command includes `timestamp` for freshness

---

## Nightscout (Server)

### Architecture

```
Careportal UI → API → loop.sendNotification() → APNs → Loop
```

`loop.sendNotification()` reads the device token and bundle identifier from the profile's `loopSettings` and builds Loop's payload keys only (`lib/server/loop.js:31-130`, cgm-remote-monitor `a8888f0d`). It does not build Trio's encrypted payload.

### Key Files

| File | Purpose |
|------|---------|
| `lib/server/loop.js` | APNs notification sender |
| `lib/plugins/careportal.js` | Event type definitions |
| `lib/api2/notifications-v2.js` | API endpoint |

### API Endpoint

```
POST /api/v2/notifications/loop
Authorization: Bearer <api-secret>
```

### Event Types

| eventType | Payload Key | Required Fields |
|-----------|-------------|-----------------|
| `Remote Bolus Entry` | `bolus-entry` | `remoteBolus`, `otp` |
| `Remote Carbs Entry` | `carbs-entry` | `remoteCarbs`, `remoteAbsorption`, `otp` |
| `Temporary Override` | `override-name` | `reason`, `duration` |
| `Temporary Override Cancel` | `cancel-temporary-override` | - |

### Notification Payload (Bolus)

```javascript
{
  'bolus-entry': parseFloat(data.remoteBolus),
  'otp': data.otp,
  'remote-address': remoteAddress,
  'notes': data.notes,
  'entered-by': data.enteredBy,
  'sent-at': now.toISOString(),
  'expiration': expiration.toISOString()  // +5 minutes
}
```

### Configuration

| Env Variable | Purpose |
|--------------|---------|
| `LOOP_APNS_KEY` | APNs authentication key (P8) |
| `LOOP_APNS_KEY_ID` | Key ID from Apple |
| `LOOP_DEVELOPER_TEAM_ID` | Apple Developer Team ID |
| `LOOP_PUSH_SERVER_ENVIRONMENT` | `production` or `development` |

### Validation

| Check | Action |
|-------|--------|
| Missing APNS config | Return error |
| Missing `loopSettings` in profile | Return error |
| Missing `deviceToken` | Return error |
| Invalid `remoteBolus` (≤0) | Return error |

---

## Cross-System Comparison

### Authentication Methods

| System | Method | Strength |
|--------|--------|----------|
| Loop | OTP (TOTP) | Strong (time-based, shared secret) |
| AAPS SMS | Passcode + confirmation | Medium (requires 2 SMS) |
| AAPS Wear | Local only | N/A (same device) |
| Trio | AES-256 encryption | Strong (encrypted payload) |
| Nightscout | API secret + TLS | Medium (bearer token) |

### Rate Limiting

| System | Mechanism |
|--------|-----------|
| Loop | Expiration (5 min) + duplicate detection |
| AAPS | `remoteBolusMinDistance` (15 min default) |
| Trio | 20% rule + IOB check |
| Nightscout | None (relies on client) |

### Max Bolus Enforcement

| System | Where Enforced |
|--------|----------------|
| Loop | `validateAmount()` in LoopKit |
| AAPS | `applyBolusConstraints()` |
| Trio | `maxBolus` check in `handleBolusCommand()` |
| Nightscout | Not enforced (server is relay only) |

### IOB Safety Check

| System | Implementation |
|--------|----------------|
| Loop | Part of standard bolus flow |
| AAPS | Constraint system |
| Trio | Explicit `(currentIOB + bolusAmount) > maxIOB` check |
| Nightscout | Not enforced |

---

## Gaps Identified

### GAP-REMOTE-001: Nightscout has no server-side bolus limits

**Description**: Nightscout acts as a relay and does not validate bolus amounts against user settings.

**Impact**: Malformed or excessive bolus commands could be relayed if client-side validation fails.

**Remediation**: Add optional `maxRemoteBolus` setting to Nightscout.

### GAP-REMOTE-002: AAPS SMS channel is unencrypted

**Description**: SMS bolus commands travel in plaintext over cellular network.

**Impact**: Commands could be intercepted or spoofed (though passcode mitigates).

**Remediation**: Accept risk (SMS inherent limitation) or use alternative channels.

### GAP-REMOTE-003: No unified remote command protocol

**Description**: Loop, AAPS, and Trio use different payload formats and auth mechanisms.

**Impact**: Caregivers need different tools for different AID systems.

**Remediation**: Define common `RemoteCommand` schema in Nightscout API v4.

### GAP-REMOTE-004: Response notification inconsistency

**Description**: Loop (NightscoutService `RemoteNotificationResponseManager`, optional, only when the sender supplies a return channel) and Trio send structured response notifications directly to the sender over APNs; neither carries a command id, and Nightscout sees only failures, as `Note` treatments. AAPS 3.4.2.6 replies by SMS; AAPS dev adds signed acknowledgements on the NS `settings` collection.

**Impact**: Caregivers may not know if remote command succeeded.

**Remediation**: Standardize response notification format.

---

## Summary Table

| Feature | Loop | AAPS | Trio | Nightscout |
|---------|------|------|------|------------|
| **Remote Bolus** | ✅ APNs | ✅ SMS/Wear | ✅ APNs | ✅ Relay |
| **Encryption** | TLS | None (SMS) | AES-256 | TLS |
| **OTP/Passcode** | OTP | Passcode | Shared secret | API secret |
| **Expiration** | 5 min | 15 min dist | Configurable | 5 min |
| **Max Bolus Check** | ✅ Client | ✅ Client | ✅ Client | ❌ |
| **IOB Safety** | ✅ | ✅ | ✅ Explicit | ❌ |
| **Response Notification** | ✅ Optional (only when the sender supplies return info) | ❌ | ✅ | ❌ |
| **Rate Limiting** | Expiration | Distance | 20% rule | None |

---

## Source Files Reference

### Loop
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/RemoteCommands/V1/Notifications/BolusRemoteNotification.swift`
- `externals/LoopWorkspace/NightscoutService/NightscoutServiceKit/RemoteCommands/Validators/RemoteCommandValidator.swift`

### AAPS
- `externals/AndroidAPS/plugins/main/src/main/kotlin/app/aaps/plugins/main/general/smsCommunicator/SmsCommunicatorPlugin.kt`
- `externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/configuration/Constants.kt`

### Trio
- `externals/Trio/Trio/Sources/Services/RemoteControl/TrioRemoteControl+Bolus.swift`
- `externals/Trio/Trio/Sources/Models/CommandPayload.swift`

### Nightscout
- `externals/cgm-remote-monitor/lib/server/loop.js`
- `externals/cgm-remote-monitor/lib/plugins/careportal.js`
