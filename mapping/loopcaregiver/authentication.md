# LoopCaregiver Authentication

This document details the QR code linking flow and OTP (One-Time Password) generation in LoopCaregiver.

---

## Executive Summary

LoopCaregiver authenticates caregivers via three mechanisms:
1. **Nightscout API Secret** - Validates Nightscout access
2. **OTP URL** - Contains shared secret for TOTP generation
3. **QR Code Scanning** - Encodes OTP URL for easy transfer from Loop

| Aspect | Value |
|--------|-------|
| **OTP Algorithm** | HMAC-SHA1 (TOTP RFC 6238) |
| **OTP Digits** | 6 |
| **OTP Period** | 30 seconds |
| **OTP Library** | OneTimePassword (Swift) |
| **QR Format** | Standard otpauth:// URI |

---

## Source Files

| File | Purpose |
|------|---------|
| `LoopCaregiverKit/Sources/.../Nightscout/OTPManager.swift` | TOTP generation and refresh |
| `LoopCaregiverKit/Sources/.../Nightscout/NightscoutCredentialService.swift` | Credential wrapper with auto-refresh OTP |
| `LoopCaregiverKit/Sources/.../Models/DeepLinkParser.swift` | URL scheme parsing |
| `LoopCaregiver/Views/Settings/LooperSetupView.swift` | QR scanning UI |

---

## QR Code Linking Flow

### Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         QR CODE LINKING FLOW                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────┐                    ┌─────────────────┐                 │
│  │    LOOP APP     │                    │  LOOPCAREGIVER  │                 │
│  │  (Looper Phone) │                    │ (Caregiver Phone)│                 │
│  └────────┬────────┘                    └────────┬────────┘                 │
│           │                                      │                          │
│           │  1. Settings → Services              │                          │
│           │     → Nightscout → Share QR          │                          │
│           │                                      │                          │
│           │  2. Display QR Code with:            │                          │
│           │     - OTP Secret                     │                          │
│           │     - Nightscout URL                 │                          │
│           │     - API Secret                     │                          │
│           │                                      │                          │
│           │         ┌───────────┐                │                          │
│           │         │ QR Code   │ ──────────────►│  3. Scan QR Code         │
│           │         │ [otpauth] │                │                          │
│           │         └───────────┘                │                          │
│           │                                      │                          │
│           │                                      │  4. Parse Deep Link      │
│           │                                      │     Extract credentials  │
│           │                                      │                          │
│           │                                      │  5. Validate credentials │
│           │                                      │     against Nightscout   │
│           │                                      │                          │
│           │                                      │  6. Store looper profile │
│           │                                      │     with OTP URL         │
│           │                                      │                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### QR Code Scanner

```swift
// loopcaregiver:LooperSetupView.swift#L44-L46
.sheet(isPresented: $isShowingScanner) {
    CodeScannerView(codeTypes: [.qr], simulatedData: simulatedOTP(), completion: handleScan)
}

private func handleScan(result: Result<ScanResult, ScanError>) {
    isShowingScanner = false
    switch result {
    case .success(let result):
        qrURLFieldText = result.string  // OTP URL from QR
    case .failure(let error):
        errorText = "\(error.localizedDescription)"
    }
}
```

### Manual Entry Fields

LooperSetupView requires 4 fields:

| Field | Validation | Description |
|-------|------------|-------------|
| `name` | Non-empty | Display name for the looper |
| `nightscoutURL` | Valid URL | Nightscout server URL |
| `apiSecret` | Non-empty | Nightscout API_SECRET |
| `qrURL` | Non-empty | OTP URL from QR scan |

---

## Deep Link Protocol

### URL Scheme

LoopCaregiver supports the `caregiver://` URL scheme for linking.

### CreateLooper Deep Link

**Format**:
```
caregiver://createLooper?name={name}&secretKey={api_secret}&nsURL={nightscout_url}&otpURL={otp_url}&createdDate={date}
```

**Example** (URL-encoded):
```
caregiver://createLooper?name=Joe&secretKey=ABCDEFGHIJ&nsURL=https%3A%2F%2Fexample.com&otpURL=otpauth%3A%2F%2Ftotp%2F1651507264639%3Falgorithm%3DSHA1%26digits%3D6%26issuer%3DLoop%26period%3D30%26secret%3D5WUYBVFE7XVTOFOMBQMDTBJP7JHBWOW3
```

### Deep Link Parser

```swift
// loopcaregiver:DeepLinkParser.swift#L14-L38
public func parseDeepLink(url: URL) throws -> DeepLinkAction {
    guard let action = url.host(percentEncoded: false) else {
        throw DeepLinkError.unsupportedURL(unsupportedURL: url)
    }

    let pathComponents = url.pathComponents.filter({ $0 != "/" })
    let queryParameters = convertQueryParametersToDictionary(from: url)

    if action == CreateLooperDeepLink.actionName {
        let deepLink = try CreateLooperDeepLink(pathParts: pathComponents, queryParameters: queryParameters)
        return .addLooper(deepLink: deepLink)
    } else if action == SelectLooperDeepLink.actionName {
        // ... other actions
    }
}
```

### CreateLooperDeepLink Structure

```swift
// loopcaregiver:DeepLinkParser.swift#L159-L216
public struct CreateLooperDeepLink: DeepLink {
    public let name: String
    public let nsURL: URL
    public let secretKey: String
    public let otpURL: URL
    public let url: URL

    public static let actionName = "createLooper"
    
    public init(pathParts: [String], queryParameters: [String: String]) throws {
        guard let name = queryParameters["name"], !name.isEmpty else {
            throw CreateLooperDeepLinkError.missingName
        }
        guard let nightscoutURLString = queryParameters["nsURL"]?.removingPercentEncoding,
              let nightscoutURL = URL(string: nightscoutURLString) else {
            throw CreateLooperDeepLinkError.missingNSURL
        }
        guard let apiSecret = queryParameters["secretKey"]?.trimmingCharacters(in: .whitespacesAndNewlines), 
              !apiSecret.isEmpty else {
            throw CreateLooperDeepLinkError.missingNSSecretKey
        }
        guard let otpURLString = queryParameters["otpURL"]?.removingPercentEncoding, 
              !otpURLString.isEmpty else {
            throw CreateLooperDeepLinkError.missingOTPURL
        }
        // ...
    }
}
```

---

## OTP URL Format

### Standard otpauth:// URI

The OTP URL follows RFC 6238 (TOTP) URI format:

```
otpauth://totp/{label}?algorithm={algo}&digits={count}&issuer={issuer}&period={seconds}&secret={base32_secret}
```

**Example**:
```
otpauth://totp/1651507264639?algorithm=SHA1&digits=6&issuer=Loop&period=30&secret=5WUYBVFE7XVTOFOMBQMDTBJP7JHBWOW3
```

### OTP Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `algorithm` | `SHA1` | HMAC algorithm |
| `digits` | `6` | OTP code length |
| `issuer` | `Loop` | Identifies the source app |
| `period` | `30` | Seconds per OTP window |
| `secret` | Base32 string | Shared secret for HMAC |
| `label` | Timestamp | Unique identifier (Loop uses creation timestamp) |

---

## OTP Generation

### OTPManager

```swift
// loopcaregiver:OTPManager.swift
public class OTPManager: ObservableObject {
    public weak var delegate: OTPManagerDelegate?
    public let otpURL: String
    @Published public var otpCode: String = ""

    private var timer: Timer?

    public init(optURL: String) {
        self.otpURL = optURL
        // Refresh every second for smooth transitions
        timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
            self.refreshCurrentOTP()
        }
        refreshCurrentOTP()
    }

    private func getOTPCode() throws -> String? {
        let token = try Token(url: URL(string: otpURL)!)
        return token.currentPassword
    }

    private func refreshCurrentOTP() {
        do {
            self.otpCode = try getOTPCode() ?? ""
        } catch {
            print(error)
        }
    }
}

public protocol OTPManagerDelegate: AnyObject {
    func otpDidUpdate(manager: OTPManager, otpCode: String)
}
```

### OTP Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            OTP GENERATION FLOW                               │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │  OTPManager                                                              ││
│  │                                                                          ││
│  │  1. Parse otpauth:// URL                                                 ││
│  │     ├── Extract secret (Base32)                                          ││
│  │     ├── Extract algorithm (SHA1)                                         ││
│  │     ├── Extract digits (6)                                               ││
│  │     └── Extract period (30 seconds)                                      ││
│  │                                                                          ││
│  │  2. Every 1 second:                                                      ││
│  │     ├── Get current Unix timestamp                                       ││
│  │     ├── Counter = floor(timestamp / period)                              ││
│  │     ├── Generate HMAC-SHA1(secret, counter)                              ││
│  │     ├── Extract dynamic 6-digit code                                     ││
│  │     └── Update @Published otpCode                                        ││
│  │                                                                          ││
│  │  3. NightscoutCredentialService receives update via delegate             ││
│  │     └── otpCode published to UI                                          ││
│  │                                                                          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  Timer (1s) ──► refreshCurrentOTP() ──► Token.currentPassword ──► @Published│
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### NightscoutCredentialService

```swift
// loopcaregiver:NightscoutCredentialService.swift
public class NightscoutCredentialService: ObservableObject, Hashable, OTPManagerDelegate {
    @Published public var otpCode: String

    public let credentials: NightscoutCredentials
    public let otpManager: OTPManager

    public init(credentials: NightscoutCredentials) {
        self.credentials = credentials
        self.otpManager = OTPManager(optURL: credentials.otpURL)
        self.otpCode = otpManager.otpCode
        self.otpManager.delegate = self
    }

    // MARK: OTPManagerDelegate
    public func otpDidUpdate(manager: OTPManager, otpCode: String) {
        self.otpCode = otpCode
    }
}
```

---

## Credential Storage

### NightscoutCredentials

```swift
// Credentials stored per looper
public struct NightscoutCredentials: Codable, Equatable, Hashable {
    public let url: URL           // Nightscout server URL
    public let secretKey: String  // API_SECRET
    public let otpURL: String     // Full otpauth:// URL
}
```

### Looper Model

```swift
// loopcaregiver:LooperSetupView.swift#L199-L204
let looper = Looper(
    identifier: UUID(),
    name: name,
    nightscoutCredentials: NightscoutCredentials(
        url: nightscoutURL, 
        secretKey: apiSecret, 
        otpURL: otpURL
    ),
    lastSelectedDate: Date()
)
```

---

## Credential Validation

Before storing credentials, LoopCaregiver validates them:

```swift
// loopcaregiver:LooperSetupView.swift#L205-L209
let service = accountService.createLooperService(looper: looper)
try await service.remoteDataSource.checkAuth()  // Validates against Nightscout

try accountService.addLooper(looper)
try accountService.updateActiveLoopUser(looper)
```

### Auth Check

```swift
// loopcaregiver:NightscoutDataSource.swift#L124-L134
public func checkAuth() async throws {
    try await withCheckedThrowingContinuation({ (continuation: CheckedContinuation<Void, Error>) -> Void in
        nightscoutUploader.checkAuth { error in
            if let error {
                continuation.resume(throwing: error)
            } else {
                continuation.resume(returning: Void())
            }
        }
    })
}
```

---

## Security Considerations

### Strengths

1. **Standard TOTP**: Uses RFC 6238 compliant implementation
2. **Credential Validation**: Verifies Nightscout access before storing
3. **Auto-Refresh**: OTP updates every second for fresh codes
4. **Secure QR Transfer**: OTP secret transferred via visual QR, not network

### Weaknesses and Gaps

| Concern | Description | Gap Reference |
|---------|-------------|---------------|
| **Secret Storage** | OTP URL stored in app data, not Keychain | GAP-REMOTE-006 |
| **No Expiry** | Shared secret has no expiration | GAP-REMOTE-003 |
| **Override OTP Skip** | Override commands don't require OTP on Loop side | GAP-REMOTE-001 |
| **QR Security** | QR code screenshot can compromise credentials | - |

### Best Practices

1. **Secure QR Display**: Only display QR code briefly
2. **Credential Reset**: Reset OTP secret if caregiver phone is lost/stolen
3. **API Secret Rotation**: Change Nightscout API_SECRET periodically
4. **Nightscout Security**: Use authentication tokens with minimal permissions

---

## Watch Configuration

LoopCaregiver supports watchOS and uses deep links to transfer configuration:

```swift
// loopcaregiver:DeepLinkParser.swift#L242-L254
public struct RequestWatchConfigurationDeepLink: DeepLink {
    public let url: URL
    
    public init() {
        self.url = URL(string: "\(Self.host)://\(Self.actionName)?createdDate=\(Date())")!
    }

    public static let actionName = "requestWatchConfiguration"
}
```

### Deep Link Actions

| Action | URL Pattern | Purpose |
|--------|-------------|---------|
| `createLooper` | `caregiver://createLooper?...` | Add new looper with credentials |
| `selectLooper` | `caregiver://selectLooper/{uuid}` | Switch active looper |
| `selectLooperError` | `caregiver://selectLooperError/{msg}` | Handle selection error |
| `requestWatchConfiguration` | `caregiver://requestWatchConfiguration` | Request watch sync |

---

## Cross-References

- [Remote Commands Protocol](remote-commands.md) - How OTP is used in commands
- [Loop OTPManager](../loop/otp.md) - Loop-side OTP validation (if exists)
- [Remote Commands Comparison](../../docs/10-domain/remote-commands-comparison.md) - Cross-system auth comparison
- [Terminology Matrix](../cross-project/terminology-matrix.md) - Authentication field mapping

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial documentation based on source code analysis |
