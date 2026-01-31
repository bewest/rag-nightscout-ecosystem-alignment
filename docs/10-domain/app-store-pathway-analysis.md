# App Store Pathway Analysis

> **Date**: 2026-01-31  
> **Status**: Complete  
> **Source**: ios-mobile-platform.md #3  
> **Related**: [nightscoutkit-swift-sdk-design.md](../sdqctl-proposals/nightscoutkit-swift-sdk-design.md)

---

## Executive Summary

This analysis examines App Store submission strategies for Nightscout ecosystem iOS apps, identifying patterns that enable successful App Store presence versus factors requiring self-build distribution.

### Key Finding

**App Store viability depends on two factors:**
1. **API usage**: Public APIs (NFC, documented BLE) vs private/reverse-engineered APIs
2. **Medical claims**: Display-only vs dosing recommendations

| Category | App Store Viable | Self-Build Required |
|----------|------------------|---------------------|
| CGM Display (NFC) | ✅ DiaBLE | - |
| CGM Display (BLE) | ⚠️ Partial | xDrip4iOS (reverse-engineered) |
| Nightscout Reader | ✅ Nightguard | - |
| AID Controller | ❌ | Loop, Trio |
| Remote Caregiver | ⚠️ | LoopCaregiver (commands dosing) |

---

## App Store Success Stories

### DiaBLE - App Store ✅

**Strategy**: NFC-first, display-only, prototype disclaimer

| Aspect | Implementation |
|--------|----------------|
| **Primary API** | NFC (Core NFC - public API) |
| **Secondary API** | BLE for Dexcom G7 (experimental) |
| **Medical Claims** | None - "prototype" |
| **Distribution** | TestFlight + App Store |
| **Entitlements** | HealthKit, Critical Alerts, App Groups |

**Key Success Factors**:
1. **NFC is a public API** - Core NFC is fully documented and approved
2. **No dosing claims** - Displays values only, no treatment suggestions
3. **Prototype framing** - README explicitly states "consider my personal project still just a **prototype**"
4. **LibreLinkUp fallback** - Can use Abbott's official API as data source

**Source**: `externals/DiaBLE/README.md`

**Entitlements Used**:
```xml
<key>com.apple.developer.healthkit</key>
<key>com.apple.developer.healthkit.background-delivery</key>
<key>com.apple.developer.usernotifications.critical-alerts</key>
<key>com.apple.security.application-groups</key>
```

---

### Nightguard - App Store ✅

**Strategy**: Pure display, explicit disclaimer, watch app value

| Aspect | Implementation |
|--------|----------------|
| **Data Source** | Nightscout API only |
| **Medical Claims** | Explicit: "Don't use this App for medical decisions" |
| **Distribution** | App Store |
| **Value Add** | Apple Watch complications, overlay charts |

**Key Success Factors**:
1. **No direct CGM connection** - Uses Nightscout as intermediary
2. **Explicit disclaimer** - "Don't use this App for medical decisions. It comes without absolutely no warranty. Use it at your own risk!"
3. **Watch app** - Native Apple Watch support adds genuine value beyond web
4. **Statistics features** - Basal rate tuning visualization

**Source**: `externals/nightguard/README.md`

**Disclaimer Pattern**:
```
Disclaimer!
Don't use this App for medical decisions. 
It comes without absolutely no warranty. 
Use it at your own risk!
```

---

## Self-Build Required

### Loop & Trio - Self-Build Only ❌

**Blocker**: FDA-unapproved automated insulin dosing

| Aspect | Loop | Trio |
|--------|------|------|
| **Function** | Closed-loop AID | Closed-loop AID (oref1) |
| **Medical Claims** | "not approved for therapy" | "not CE or FDA approved for therapy" |
| **Distribution** | TestFlight (self-build) | TestFlight (self-build) |
| **Pump Control** | Yes - doses insulin | Yes - doses insulin |

**Why App Store Impossible**:
1. **Guideline 5.1 Safety**: Apps that could harm users physically face rejection
2. **FDA Regulation**: Automated insulin dosing is Class II/III medical device
3. **Liability**: Apple won't distribute unapproved medical devices

**Source**: `externals/LoopWorkspace/Loop/README.md`, `externals/Trio/README.md`

---

### xDrip4iOS - Self-Build Only ❌

**Blocker**: Reverse-engineered private BLE APIs

| Aspect | Implementation |
|--------|----------------|
| **CGM Connection** | Direct BLE to Dexcom G5/G6/G7, Libre |
| **API Status** | Reverse-engineered, not documented |
| **Distribution** | TestFlight (self-build) |

**Why App Store Risky**:
1. **Guideline 2.5.1**: Must use documented APIs
2. **Private APIs**: Dexcom BLE protocol is reverse-engineered
3. **Rejection Risk**: Apple can reject for undocumented API usage

---

## App Store Guideline Analysis

### Guideline 4.2: Minimum Functionality

> "Your app should include features, content, and UI that elevate it beyond a repackaged website."

**Implications**:
- Pure Nightscout web wrapper: ❌ Rejected
- Nightscout + native widgets: ✅ Acceptable
- Nightscout + Watch complications: ✅ Acceptable (Nightguard)

### Guideline 4.3: Spam

> "Don't create multiple Bundle IDs of the same app."

**Implications**:
- Can't submit "Nightscout Follower", "Nightscout CGM", "Nightscout AID" if 90% identical
- Each app must serve genuinely different use case
- Modular architecture with distinct App Store submissions is acceptable

### Guideline 5.1: Safety

> "Apps that could cause physical harm may be rejected."

**Implications**:
- Display-only apps: ✅ Generally safe
- Dosing recommendations: ⚠️ Requires disclaimers
- Automated dosing: ❌ Rejected without FDA approval

### Guideline 2.5.1: Software Requirements

> "Apps may only use public APIs."

**Implications**:
- Core NFC (Libre): ✅ Public API
- Core Bluetooth (documented): ✅ Public API  
- Reverse-engineered Dexcom BLE: ⚠️ Undocumented, risk

---

## Feature Decision Matrix

| Feature | App Store Viable | Rationale |
|---------|------------------|-----------|
| **Nightscout data display** | ✅ Yes | API-based, display-only |
| **Nightscout widgets** | ✅ Yes | Native value-add |
| **Watch complications** | ✅ Yes | Native value-add |
| **HealthKit write** | ✅ Yes | Documented API |
| **Critical alerts** | ✅ Yes | Requires entitlement request |
| **Libre NFC scan** | ✅ Yes | Core NFC is public |
| **Dexcom G7 BLE** | ⚠️ Partial | J-PAKE auth undocumented |
| **Dexcom Share API** | ✅ Yes | HTTP-based, documented |
| **LibreLinkUp API** | ✅ Yes | HTTP-based, official |
| **Nightscout upload** | ✅ Yes | HTTP API |
| **Remote bolus commands** | ⚠️ Risky | Safety concerns (5.1) |
| **Temp basal suggestions** | ⚠️ Risky | Medical advice (5.1) |
| **Automated dosing** | ❌ No | FDA Class II/III |
| **Pump control** | ❌ No | Medical device regulation |

---

## Recommended App Store Strategy

### Tier 1: App Store Ready

| App Concept | Features | Target |
|-------------|----------|--------|
| **Nightscout Display** | Read NS data, widgets, Watch, alerts | General users |
| **Nightscout Widget** | Home screen widgets only | Lightweight option |

**Implementation**:
- Use NightscoutKit SDK for API access
- Add native widgets (iOS 14+) and Watch complications
- Include prominent disclaimer
- No dosing features

### Tier 2: App Store with Disclaimers

| App Concept | Features | Disclaimer Required |
|-------------|----------|---------------------|
| **CGM Reader** | Libre NFC + Dexcom Share | "For informational purposes only" |
| **Follower** | NS + alerts + statistics | "Not for medical decisions" |

**Implementation**:
- Use only public APIs (NFC, HTTP)
- Avoid direct Dexcom BLE unless using Share API
- Prominent first-launch disclaimer with acceptance

### Tier 3: Self-Build Only

| App Concept | Features | Reason |
|-------------|----------|--------|
| **AID Controller** | Pump control, dosing | FDA regulation |
| **Direct CGM BLE** | Dexcom G5/G6 direct | Private APIs |
| **Remote Commander** | Remote bolus | Safety liability |

---

## Disclaimer Patterns

### Pattern 1: README Disclaimer (DiaBLE)

```markdown
Please consider my personal project still just a **prototype**
```

**Strength**: Low-key, doesn't scare users
**Weakness**: May not satisfy App Review

### Pattern 2: Explicit Rejection (Nightguard)

```markdown
Disclaimer!
Don't use this App for medical decisions. 
It comes without absolutely no warranty. 
Use it at your own risk!
```

**Strength**: Clear, satisfies legal concerns
**Weakness**: Prominent negative messaging

### Pattern 3: First-Launch Acceptance (Recommended)

```swift
struct DisclaimerView: View {
    var body: some View {
        VStack {
            Text("Important Notice")
                .font(.title)
            Text("""
                This app displays glucose data for informational purposes only.
                It is not intended for making medical decisions.
                Always consult your healthcare provider for treatment decisions.
                """)
            Button("I Understand and Accept") {
                UserDefaults.standard.set(true, forKey: "disclaimerAccepted")
            }
        }
    }
}
```

**Strength**: User must actively accept, logged for audit
**Weakness**: Friction at first launch

---

## Critical Alerts Entitlement

Both DiaBLE and Nightguard request Critical Alerts entitlement:

```xml
<key>com.apple.developer.usernotifications.critical-alerts</key>
<true/>
```

**Requirements**:
1. Must request from Apple: [Critical Alert Entitlement Request](https://developer.apple.com/contact/request/notifications-critical-alerts-entitlement/)
2. Justify medical/safety need
3. Apple manually reviews each request

**Approval Likelihood**:
- Glucose monitoring apps: ✅ Typically approved
- Must demonstrate legitimate safety use case

---

## Architecture Recommendation

### For App Store Submission

```
NightscoutKit (SDK)
├── Core: HTTP client, models, sync
├── No dosing logic
└── No pump control

App Layer
├── NightscoutDisplayApp (App Store)
│   ├── Uses NightscoutKit
│   ├── Widgets, Watch, Alerts
│   └── Disclaimer on launch
│
├── NightscoutCGMApp (App Store)
│   ├── Uses NightscoutKit + Core NFC
│   ├── Libre scanning
│   └── LibreLinkUp/Dexcom Share
│
└── [AID Apps] (Self-Build Only)
    ├── Uses NightscoutKit for sync
    ├── LoopKit for dosing
    └── Pump control
```

---

## Gap References

| Gap ID | Description | Relevance |
|--------|-------------|-----------|
| GAP-IOS-002 | No shared NightscoutKit SDK | SDK enables App Store apps |
| GAP-API-003 | No v3 adoption path for iOS | App Store apps need modern API |
| GAP-TEST-002 | No Swift validation on Linux | CI for SDK development |

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [ios-mobile-platform.md](../sdqctl-proposals/backlogs/ios-mobile-platform.md) | iOS backlog |
| [nightscoutkit-swift-sdk-design.md](../sdqctl-proposals/nightscoutkit-swift-sdk-design.md) | SDK design |
| [swift-package-ecosystem-assessment.md](swift-package-ecosystem-assessment.md) | SPM status |

---

## Summary

**App Store success requires:**
1. ✅ Use only public/documented APIs
2. ✅ Display-only (no dosing)
3. ✅ Prominent disclaimers
4. ✅ Native value-add (widgets, Watch)
5. ❌ Avoid pump control
6. ❌ Avoid reverse-engineered protocols

**Recommended next steps:**
1. Develop NightscoutKit SDK (SPM-ready)
2. Create "Nightscout Display" App Store app
3. Separate AID features to self-build apps
4. Apply for Critical Alerts entitlement
