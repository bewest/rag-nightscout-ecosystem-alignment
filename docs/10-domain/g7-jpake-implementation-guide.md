# G7 J-PAKE Implementation Guide

This document provides a detailed guide for implementing the J-PAKE (Password Authenticated Key Exchange by Juggling) protocol required for standalone Dexcom G7 authentication, with a focus on porting from the xDrip Android `libkeks` implementation to Swift/iOS.

## Table of Contents

- [Overview](#overview)
- [J-PAKE Protocol Theory](#j-pake-protocol-theory)
- [xDrip libkeks Architecture](#xdrip-libkeks-architecture)
- [Algorithm Implementation](#algorithm-implementation)
- [Swift/iOS Porting Guide](#swiftios-porting-guide)
- [Certificate Exchange](#certificate-exchange)
- [Proof of Possession](#proof-of-possession)
- [Testing Strategy](#testing-strategy)
- [Known Issues and Blockers](#known-issues-and-blockers)

---

## Overview

### What is J-PAKE?

J-PAKE (Password Authenticated Key Exchange by Juggling) is a cryptographic protocol that:
- Allows two parties to establish a shared secret using a low-entropy password
- Protects against offline dictionary attacks
- Provides mutual authentication
- Does not require PKI or trusted third parties

### Why G7 Uses J-PAKE

The Dexcom G7 uses J-PAKE to ensure that only devices with knowledge of the sensor code (printed on the sensor) can establish a trusted BLE connection. This prevents:
- Unauthorized devices from pairing
- Replay attacks from captured BLE traffic
- Offline brute-force attacks on the sensor code

### Reference Implementation

The only known working open-source J-PAKE implementation for G7 is xDrip Android's `libkeks` library:
- **Repository**: `NightscoutFoundation/xDrip`
- **Path**: `libkeks/src/main/java/jamorham/keks/`
- **Author**: jamorham
- **License**: GPL-3.0

---

## J-PAKE Protocol Theory

### Protocol Rounds

J-PAKE consists of three rounds of message exchange:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    J-PAKE Protocol Flow                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Setup:                                                              │
│  - Agreed curve: secp256r1 (P-256)                                  │
│  - Generator: G (curve base point)                                   │
│  - Order: q (curve order)                                            │
│  - Password: s (sensor code, converted to BigInteger)               │
│  - Party IDs: alice (us), bob (sensor)                               │
│                                                                      │
│  Round 1 (both parties):                                             │
│  - Generate random x1 ∈ [1, q-1]                                    │
│  - Compute X1 = G × x1                                               │
│  - Generate ZKP for x1: prove knowledge of x1 without revealing it  │
│  - Send: X1, ZKP(x1)                                                 │
│                                                                      │
│  Round 2 (both parties):                                             │
│  - Generate random x2 ∈ [1, q-1]                                    │
│  - Compute X2 = G × x2                                               │
│  - Generate ZKP for x2: prove knowledge of x2 without revealing it  │
│  - Send: X2, ZKP(x2)                                                 │
│                                                                      │
│  Round 3 (both parties):                                             │
│  - Compute GA = X1 + X3 + X4                                         │
│  - Compute A = GA × (x2 × s mod q)                                   │
│  - Generate ZKP for (x2 × s): prove knowledge of exponent           │
│  - Send: A, ZKP(x2 × s)                                              │
│                                                                      │
│  Key Derivation:                                                     │
│  - K = (B - X4 × (x2 × s mod q)) × x2                               │
│  - SharedKey = SHA256(K.x)                                           │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Zero-Knowledge Proof (ZKP)

Each round includes a Schnorr-style ZKP that proves knowledge of the private exponent:

```
ZKP Generation:
1. Choose random v ∈ [1, q-1]
2. Compute V = G × v
3. Compute h = SHA256(G || V || X || partyID) mod q
4. Compute r = v - h × x mod q
5. Send: (V, r)

ZKP Verification:
1. Compute h = SHA256(G || V || X || partyID) mod q
2. Verify: G × r + X × h = V
```

---

## xDrip libkeks Architecture

### File Structure

```
libkeks/src/main/java/jamorham/keks/
├── Calc.java              # Core J-PAKE calculations
├── Config.java            # Configuration constants
├── Context.java           # Authentication state machine
├── Curve.java             # Elliptic curve parameters
├── DSAChallenger.java     # ECDSA signature for PoP
├── JECPoint.java          # EC point serialization
├── KeyPair.java           # EC key pair wrapper
├── Packet.java            # J-PAKE packet serialization
├── Plugin.java            # xDrip plugin interface
├── Umbilical.java         # BLE communication bridge
├── util/
│   ├── AESwrapper.java    # AES encryption helper
│   ├── ByteArrayHashMap.java  # Byte array utilities
│   ├── Log.java           # Logging wrapper
│   └── Util.java          # General utilities
└── message/
    ├── AuthChallengeTxMessage.java   # Challenge request
    ├── AuthRequestTxMessage2.java    # Auth request
    ├── AuthStatusRxMessage.java      # Auth status response
    ├── BaseMessage.java              # Message base class
    ├── CertInfoRxMessage.java        # Cert info response
    ├── CertInfoTxMessage.java        # Cert info request
    └── SignChallengeTxMessage.java   # Sign challenge
```

### Key Classes

#### Curve.java - Elliptic Curve Parameters

```java
public class Curve {
    public static final String name = "secp256r1";
    public static final ECNamedCurveParameterSpec curveSpec = 
        ECNamedCurveTable.getParameterSpec(name);
    public static final ECPoint G = curveSpec.getG();
    public static final ECCurve curve = curveSpec.getCurve();
    public static final BigInteger Q = curve.getOrder();
    public static final int CURVE_BITS = curve.getFieldSize();  // 256
    public static final int FIELD_SIZE = (CURVE_BITS + 7) / 8;  // 32 bytes
    public static final int PACKET_SIZE = FIELD_SIZE * 5;       // 160 bytes
    
    public static BigInteger getExponent() {
        return BigIntegers.createRandomInRange(ONE, Q.subtract(ONE), random);
    }
}
```

#### Context.java - Authentication State

```java
public class Context {
    public KeyPair keyA;              // Our round 1 key pair
    public KeyPair KeyB;              // Our round 2 key pair
    public String password;           // Sensor code
    public byte[] passwordBytes;      // Converted password
    public byte[] alice;              // Our party ID
    public byte[] bob;                // Sensor party ID
    public byte[] challenge;          // Challenge data
    public volatile byte[] savedKey;  // Derived shared key
    public volatile Packet[] packet = new Packet[4];  // Received packets
    public volatile int sequence;     // Current round
    
    // Certificate parts for later exchange
    private volatile byte[] partA;
    private volatile byte[] partB;
    private volatile byte[] partC;
    
    public BigInteger getPasswordBigInteger() {
        return BigIntegers.fromUnsignedByteArray(getPasswordBytes());
    }
}
```

#### Calc.java - Core Calculations

```java
public class Calc {
    // Round 1/2 packet generation
    public static Packet getRound12Packet(Context context, boolean part2) {
        KeyPair key = part2 ? context.KeyB : context.keyA;
        ZKP zkp = new ZKP(Curve.G, key, context.alice);
        return new Packet(zkp.getProof(), key.getPublicKey(), zkp.getGv());
    }
    
    // Round 3 packet generation (sending our A value)
    public static Packet getRound3Packet(Context context) {
        ECPoint x1 = context.keyA.getPublicKey();      // Our round 1 public key
        BigInteger x2 = context.KeyB.getPrivateKey();  // Our round 2 private key
        ECPoint x3 = context.getRound1Packet().getPublicKeyPoint1();  // Their round 1 public
        ECPoint x4 = context.getRound2Packet().getPublicKeyPoint1();  // Their round 2 public
        BigInteger s = context.getPasswordBigInteger();
        
        BigInteger x2s = x2.multiply(s).mod(Curve.Q);
        ECPoint GA = x1.add(x3).add(x4).normalize();   // Generator for round 3: X1 + X3 + X4
        ECPoint A = GA.multiply(x2s).normalize();       // Our A value
        
        ZKP zkp = new ZKP(GA, new KeyPair(x2s, A), context.alice);
        return new Packet(zkp.getProof(), A, zkp.getGv());
    }
    
    // Round 3 validation (verifying their B value)
    // Note: Uses DIFFERENT generator than sending: g = x1 + x2 + x3
    public static boolean validateRound3Packet(Context context) {
        Packet packet = context.getRound3Packet();
        if (packet == null) return false;
        ECPoint x1 = context.keyA.getPublicKey();      // Our round 1 public
        ECPoint x2 = context.KeyB.getPublicKey();      // Our round 2 public
        ECPoint x3 = context.getRound1Packet().getPublicKeyPoint1();  // Their round 1 public
        
        // Verification generator: X1 + X2 + X3 (asymmetric with sending!)
        ECPoint g = x1.add(x2).add(x3).normalize();
        ECPoint B = packet.getPublicKeyPoint1();
        
        return validateZeroKnowledgeProof(g, B, packet.getPublicKeyPoint2(), 
            packet.getHash(), context.bob);
    }
    
    // Shared key derivation
    public static byte[] getSharedKey(Context context) {
        ECPoint B = context.getRound3Packet().getPublicKeyPoint1();
        BigInteger x2 = context.KeyB.getPrivateKey();
        ECPoint x4 = context.getRound2Packet().getPublicKeyPoint1();
        BigInteger s = context.getPasswordBigInteger();
        
        ECPoint K = B.subtract(
            x4.multiply(x2.multiply(s).mod(Curve.Q))
        ).multiply(x2).normalize();
        
        return SHA256.hash(K.getXCoord().getEncoded());
    }
    
    // Challenge-response calculation
    public static byte[] calculateHash(Context context) {
        byte[] key = context.savedKey != null ? 
            context.savedKey : getShortSharedKey(context);
        byte[] doubleChallenge = concat(context.challenge, context.challenge);
        byte[] encrypted = AES.encrypt(key, doubleChallenge);
        return Arrays.copyOf(encrypted, 8);
    }
}
```

#### Packet.java - Serialization

```java
public class Packet {
    BigInteger hash;           // ZKP proof value (32 bytes)
    ECPoint publicKeyPoint1;   // Public key or A value
    ECPoint publicKeyPoint2;   // V from ZKP
    
    // JECPoint serializes EC points as X || Y (64 bytes, no 0x04 prefix)
    // Total layout: [Point1.x:32][Point1.y:32][Point2.x:32][Point2.y:32][hash:32] = 160 bytes
    
    public static Packet parse(byte[] packet) {
        // Parse 160-byte packet into 5 × 32-byte components
        // Layout: [Point1.x:32][Point1.y:32][Point2.x:32][Point2.y:32][hash:32]
        // Points are reconstructed from x,y coordinates (no 0x04 prefix)
    }
    
    public byte[] output() {
        // Serialize to 160-byte packet
        ByteBuffer packet = ByteBuffer.allocate(PACKET_SIZE);  // 160 bytes
        packet.put(new JECPoint(publicKeyPoint1).toBytes());   // 64 bytes (x:32 + y:32)
        packet.put(new JECPoint(publicKeyPoint2).toBytes());   // 64 bytes (x:32 + y:32)
        packet.put(asUnsignedByteArray(FIELD_SIZE, hash));     // 32 bytes
        return packet.array();
    }
}
```

---

## Algorithm Implementation

### Password Handling

The sensor code is a 6-character alphanumeric code printed on the sensor. It's converted to bytes with a prefix:

```java
// Config.java
public enum Get {
    PREFIX(new byte[]{0x00, 0x00, 0x00, 0x00}),  // 4-byte prefix
    REFERENCE(new byte[]{...}),  // Reference exponent for ZKP
}

// Context.java
public byte[] getPasswordBytes() {
    if (password.length() == 6) {
        // Prepend 4-byte prefix to 6-character code
        passwordBytes = arrayAppend(PREFIX.bytes, password.getBytes("UTF-8"));
    }
    return passwordBytes;  // Total: 10 bytes
}
```

### ZKP Implementation

```java
public static class ZKP {
    private final BigInteger exponent;
    private final ECPoint g;
    private final KeyPair keyPair;
    private final byte[] party;
    private ECPoint gv = null;
    
    private ECPoint getGv() {
        if (gv == null) {
            gv = g.multiply(exponent).normalize();
        }
        return gv;
    }
    
    public BigInteger getProof() {
        BigInteger h = getZeroKnowledgeHash(g, getGv(), keyPair.getPublicKey(), party);
        return exponent.subtract(h.multiply(keyPair.getPrivateKey())).mod(Curve.Q);
    }
}

public static BigInteger getZeroKnowledgeHash(ECPoint g, ECPoint gv, ECPoint gx, byte[] party) {
    Digest digest = new SHA256();
    updateDigestIncludingSize(digest, g);     // G point
    updateDigestIncludingSize(digest, gv);    // V = G × v
    updateDigestIncludingSize(digest, gx);    // X = G × x
    updateDigestIncludingSize(digest, party); // Party ID
    return fromUnsignedByteArray(digest.finish()).mod(Curve.Q);
}

private static void updateDigestIncludingSize(Digest digest, byte[] data) {
    digest.update(intToByteArray(data.length));  // 4-byte length prefix
    digest.update(data);
}
```

### Packet Validation

```java
public static boolean validateRound1Packet(Packet p, byte[] party) {
    if (p == null) return false;
    return validateZeroKnowledgeProof(Curve.G, p.publicKeyPoint1, 
        p.publicKeyPoint2, p.hash, party);
}

public static boolean validateZeroKnowledgeProof(ECPoint g, ECPoint X, 
        ECPoint V, BigInteger r, byte[] party) {
    BigInteger h = getZeroKnowledgeHash(g, V, X, party);
    // Verify: G × r + X × h = V
    return g.multiply(r).add(X.multiply(h)).normalize().equals(V);
}
```

---

## Swift/iOS Porting Guide

### Dependencies

| Java (BouncyCastle) | Swift Equivalent |
|---------------------|------------------|
| `ECNamedCurveParameterSpec` | `SecKey` / CryptoKit `P256` |
| `ECPoint` | `P256.Signing.PublicKey` data representation |
| `BigInteger` | `Data` / custom BigInt |
| `SHA256` | `CryptoKit.SHA256` |
| `Cipher (AES)` | `CryptoKit.AES` |
| `SecureRandom` | `SecureRandom` / `randomBytes` |
| `Signature (ECDSA)` | `P256.Signing` |

### Core Swift Implementation

```swift
import Foundation
import CryptoKit

struct JPAKECurve {
    static let name = "secp256r1"
    static let fieldSize = 32  // 256 bits
    static let packetSize = 160 // 5 × 32 bytes
    
    // P-256 curve order
    static let order: Data = Data([
        0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x00,
        0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
        0xBC, 0xE6, 0xFA, 0xAD, 0xA7, 0x17, 0x9E, 0x84,
        0xF3, 0xB9, 0xCA, 0xC2, 0xFC, 0x63, 0x25, 0x51
    ])
}

struct JPAKEContext {
    var keyA: P256.KeyAgreement.PrivateKey
    var keyB: P256.KeyAgreement.PrivateKey
    var password: String
    var alice: Data  // Our party ID
    var bob: Data    // Sensor party ID
    var challenge: Data?
    var savedKey: Data?
    var receivedPackets: [Int: JPAKEPacket] = [:]
    
    init(password: String) {
        self.password = password
        self.keyA = P256.KeyAgreement.PrivateKey()
        self.keyB = P256.KeyAgreement.PrivateKey()
        self.alice = "client".data(using: .utf8)!
        self.bob = "server".data(using: .utf8)!
    }
    
    func getPasswordBytes() -> Data {
        let prefix = Data([0x00, 0x00, 0x00, 0x00])
        let codeBytes = password.data(using: .utf8)!
        return prefix + codeBytes
    }
}

struct JPAKEPacket {
    let hash: Data           // 32 bytes - ZKP proof
    let publicKey1X: Data    // 32 bytes - Point1 X coordinate
    let publicKey1Y: Data    // 32 bytes - Point1 Y coordinate
    let publicKey2X: Data    // 32 bytes - Point2 X coordinate (V from ZKP)
    let publicKey2Y: Data    // 32 bytes - Point2 Y coordinate
    
    // Wire format: [Point1.x:32][Point1.y:32][Point2.x:32][Point2.y:32][hash:32] = 160 bytes
    // Note: Points are serialized as raw X||Y (64 bytes), NOT uncompressed (no 0x04 prefix)
    
    init?(data: Data) {
        guard data.count >= JPAKECurve.packetSize else { return nil }
        
        // Parse 160-byte packet into 5 × 32-byte components
        self.publicKey1X = data[0..<32]
        self.publicKey1Y = data[32..<64]
        self.publicKey2X = data[64..<96]
        self.publicKey2Y = data[96..<128]
        self.hash = data[128..<160]
    }
    
    func toBytes() -> Data {
        var output = Data(capacity: 160)
        output.append(publicKey1X)  // 32 bytes
        output.append(publicKey1Y)  // 32 bytes
        output.append(publicKey2X)  // 32 bytes
        output.append(publicKey2Y)  // 32 bytes
        output.append(hash)         // 32 bytes
        return output
    }
    
    // Helper to reconstruct uncompressed point for CryptoKit (if needed)
    func uncompressedPoint1() -> Data {
        return Data([0x04]) + publicKey1X + publicKey1Y
    }
}

class JPAKECalculator {
    
    static func generateRound1Packet(context: JPAKEContext) -> Data {
        let privateKey = context.keyA
        let publicKey = privateKey.publicKey
        
        // Generate ZKP
        let zkpExponent = P256.KeyAgreement.PrivateKey()
        let v = zkpExponent.publicKey.rawRepresentation
        
        // Calculate hash for ZKP
        let h = calculateZKPHash(
            g: getBasePoint(),
            v: v,
            x: publicKey.rawRepresentation,
            party: context.alice
        )
        
        // Calculate proof: r = v_exp - h × x_exp (mod q)
        let proof = calculateProof(
            vExponent: zkpExponent,
            h: h,
            xExponent: privateKey
        )
        
        return JPAKEPacket(
            hash: proof,
            publicKey1: Data([0x04]) + publicKey.rawRepresentation,
            publicKey2: Data([0x04]) + v
        ).toBytes()
    }
    
    static func calculateZKPHash(g: Data, v: Data, x: Data, party: Data) -> Data {
        var hasher = SHA256()
        
        // Include size prefix for each element
        hasher.update(data: UInt32(g.count).bigEndianData)
        hasher.update(data: g)
        hasher.update(data: UInt32(v.count).bigEndianData)
        hasher.update(data: v)
        hasher.update(data: UInt32(x.count).bigEndianData)
        hasher.update(data: x)
        hasher.update(data: UInt32(party.count).bigEndianData)
        hasher.update(data: party)
        
        return Data(hasher.finalize())
    }
    
    static func deriveSharedKey(context: JPAKEContext) -> Data? {
        // Implementation requires EC point arithmetic
        // which is not directly exposed in CryptoKit
        // May need to use Security framework or custom implementation
        return nil
    }
    
    static func calculateChallengeResponse(key: Data, challenge: Data) -> Data {
        let doubleChallenge = challenge + challenge
        let symmetricKey = SymmetricKey(data: key[0..<16])
        
        do {
            let sealed = try AES.GCM.seal(doubleChallenge, using: symmetricKey)
            return Data(sealed.ciphertext[0..<8])
        } catch {
            return Data()
        }
    }
    
    private static func getBasePoint() -> Data {
        // P-256 base point G (uncompressed)
        // This is a well-known constant
        return Data([0x04]) + Data([
            // X coordinate
            0x6B, 0x17, 0xD1, 0xF2, 0xE1, 0x2C, 0x42, 0x47,
            0xF8, 0xBC, 0xE6, 0xE5, 0x63, 0xA4, 0x40, 0xF2,
            0x77, 0x03, 0x7D, 0x81, 0x2D, 0xEB, 0x33, 0xA0,
            0xF4, 0xA1, 0x39, 0x45, 0xD8, 0x98, 0xC2, 0x96,
            // Y coordinate
            0x4F, 0xE3, 0x42, 0xE2, 0xFE, 0x1A, 0x7F, 0x9B,
            0x8E, 0xE7, 0xEB, 0x4A, 0x7C, 0x0F, 0x9E, 0x16,
            0x2B, 0xCE, 0x33, 0x57, 0x6B, 0x31, 0x5E, 0xCE,
            0xCB, 0xB6, 0x40, 0x68, 0x37, 0xBF, 0x51, 0xF5
        ])
    }
}

extension UInt32 {
    var bigEndianData: Data {
        var value = self.bigEndian
        return Data(bytes: &value, count: 4)
    }
}
```

### CryptoKit Limitations

**Problem:** CryptoKit does not expose raw elliptic curve point arithmetic (addition, scalar multiplication) required for J-PAKE.

**Solutions:**

1. **Use Security Framework directly:**
   ```swift
   import Security
   
   // Create EC key from raw bytes
   var error: Unmanaged<CFError>?
   let keyDict: [CFString: Any] = [
       kSecAttrKeyType: kSecAttrKeyTypeECSECPrimeRandom,
       kSecAttrKeyClass: kSecAttrKeyClassPublic,
       kSecAttrKeySizeInBits: 256
   ]
   let publicKey = SecKeyCreateWithData(
       keyData as CFData, 
       keyDict as CFDictionary, 
       &error
   )
   ```

2. **Use a third-party library:**
   - [swift-crypto](https://github.com/apple/swift-crypto) (Apple)
   - [CryptoSwift](https://github.com/krzyzanowskim/CryptoSwift)
   - [BigInt](https://github.com/attaswift/BigInt) for modular arithmetic

3. **Wrap mbedtls via C bridge:**
   - Similar to how particle-iot's ECJPake.swift works
   - Requires Objective-C bridging header

---

## Certificate Exchange

After J-PAKE completes, a certificate exchange phase validates device identity:

### Certificate Request (Opcode 0x0B)

```swift
struct CertInfoTxMessage {
    static let opcode: UInt8 = 0x0B
    
    static func requestCert(which: Int, expectedSize: Int) -> Data {
        var data = Data()
        data.append(opcode)
        data.append(UInt8(which))  // 0, 1, or 2
        data.append(contentsOf: UInt32(expectedSize).littleEndianBytes)
        return data
    }
}
```

### Certificate Response (Opcode 0x0B)

```swift
struct CertInfoRxMessage {
    let state: UInt8
    let which: UInt8
    let size: UInt16
    
    var isValid: Bool { size > 0 && state == 0 && which >= 0 }
    
    init?(data: Data) {
        guard data.count == 7, data[0] == 0x0B else { return nil }
        state = data[1]
        which = data[2]
        size = UInt16(data[3]) | (UInt16(data[4]) << 8)
    }
}
```

---

## Proof of Possession

The final authentication phase uses ECDSA to prove private key ownership:

### Sign Challenge (Opcode 0x0C)

```swift
struct SignChallengeTxMessage {
    static let opcode: UInt8 = 0x0C
    
    static func create(challenge: Data? = nil) -> Data {
        let challengeBytes = challenge ?? Data.random(count: 16)
        return Data([opcode]) + challengeBytes
    }
}

class DSAChallenger {
    private let privateKey: P256.Signing.PrivateKey
    
    init(keyData: Data) throws {
        self.privateKey = try P256.Signing.PrivateKey(rawRepresentation: keyData)
    }
    
    func sign(challenge: Data) throws -> Data {
        let signature = try privateKey.signature(for: challenge)
        // Convert from DER to raw R||S format (64 bytes)
        return convertDERToRaw(signature.derRepresentation)
    }
    
    private func convertDERToRaw(_ der: Data) -> Data {
        // DER format: 30 LEN 02 RLEN R 02 SLEN S
        // Raw format: R (32 bytes) || S (32 bytes)
        // Parse and pad R and S to 32 bytes each
        var raw = Data(count: 64)
        // ... parsing logic ...
        return raw
    }
}
```

---

## Testing Strategy

### Unit Tests

1. **Packet serialization/deserialization**
2. **ZKP hash calculation** (compare with known vectors)
3. **Password byte conversion**
4. **AES challenge-response**

### Integration Tests

1. **Mock sensor BLE traffic** using captured traces
2. **Round-trip validation** - generate and validate our own packets
3. **Shared key derivation** - verify both sides derive same key

### Test Vectors

From xDrip libkeks, known test cases can be extracted for validation:

```swift
// Example test vector (placeholder - extract from actual implementation)
let testPassword = "ABC123"
let expectedPasswordBytes = Data([0x00, 0x00, 0x00, 0x00, 
                                   0x41, 0x42, 0x43, 0x31, 0x32, 0x33])
```

---

## Known Issues and Blockers

### 1. CryptoKit EC Point Arithmetic

**Issue:** CryptoKit doesn't expose raw EC point operations (add, multiply).

**Workaround:** Use Security framework or third-party libraries.

### 2. Party ID Values

**Issue:** Exact values for `alice` and `bob` party IDs are not documented.

**Workaround:** Reverse engineer from xDrip BLE traces or decompile Dexcom SDK.

### 3. Certificate Format

**Issue:** Certificate structure and validation logic not fully documented.

**Workaround:** Capture and analyze certificate exchange in BLE traces.

### 4. Timing Requirements

**Issue:** Unknown timeout constraints for each authentication phase.

**Workaround:** Start with generous timeouts (30+ seconds per phase).

---

## References

### Academic Papers

1. **J-PAKE Protocol**: Hao, F., & Ryan, P. (2008). "Password Authenticated Key Exchange by Juggling"
   - https://ia.cr/2010/190
   
2. **RFC 8236**: "J-PAKE: Password-Authenticated Key Exchange by Juggling"
   - https://datatracker.ietf.org/doc/rfc8236/

### Code References

1. **xDrip libkeks**: `NightscoutFoundation/xDrip/libkeks/`
2. **Juggluco**: `j-kaltes/Juggluco/Common/src/dex/java/tk/glucodata/DexGattCallback.java`
3. **mbedtls ecjpake**: `Mbed-TLS/mbedtls/include/mbedtls/ecjpake.h`
4. **particle-iot ECJPake.swift**: `particle-iot/iOSBLEExample/ParticleBLECode/ECJPake.swift`

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial guide from xDrip libkeks analysis |
