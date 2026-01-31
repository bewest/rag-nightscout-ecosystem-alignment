# iOS Mobile Platform Backlog

> **Purpose**: Research and design items for iOS mobile app development across the Nightscout ecosystem  
> **Created**: 2026-01-31  
> **Status**: Active

---

## Overview

This backlog tracks research and design work for iOS mobile development strategy, focusing on:
- App Store deployment pathways
- Code sharing across ecosystem
- Monolithic vs multi-app architecture decisions
- Cross-platform testing infrastructure

---

## Ecosystem Context

### Current iOS Apps

| App | Purpose | Maintainer | App Store Status |
|-----|---------|------------|------------------|
| **Loop** | AID Controller | LoopKit | TestFlight only (self-build) |
| **Trio** | AID Controller (oref1) | Nightscout | TestFlight only (self-build) |
| **xDrip4iOS** | CGM Display | JohanDegraeve | TestFlight (self-build) |
| **DiaBLE** | CGM Display (Libre/G7) | gui-dos | App Store ✅ |
| **LoopFollow** | Follower/Monitor | loopandlearn | TestFlight (self-build) |
| **LoopCaregiver** | Remote Caregiver | loopandlearn | TestFlight (self-build) |
| **Nightguard** | Nightscout Display | nightscout | App Store ✅ |
| **Nightscout** (widget) | Widget | nightscout | App Store ✅ |

### Code Sharing Reality

**Shared via Git Submodules (Not SPM/CocoaPods):**

| Library | Used By | Purpose |
|---------|---------|---------|
| LoopKit | Loop, Trio, LoopCaregiver | Core AID framework |
| CGMBLEKit | Loop, Trio | Dexcom G5/G6 BLE |
| G7SensorKit | Loop, Trio | Dexcom G7 |
| OmniBLE/OmniKit | Loop, Trio | Omnipod pump |
| MinimedKit | Loop, Trio | Medtronic pump |
| LibreTransmitter | Loop, Trio | Libre CGM |
| dexcom-share-client-swift | Loop, Trio, LoopFollow | Dexcom Share API |

**Duplicated (Forked, not shared):**
- Trio maintains `loopandlearn` forks with `trio` branches
- Each fork is 90%+ identical with minor customizations
- Creates merge conflict burden and divergence risk

**Isolated (No code sharing):**
- DiaBLE - completely independent
- Nightguard - independent Nightscout reader
- xDrip4iOS - minimal dependencies

---

## Apple App Store Constraints

### Review Guideline 4.2: Minimum Functionality

Apps must have sufficient built-in functionality, not just act as wrappers for websites.

**Implications:**
- Pure Nightscout web-view wrapper likely rejected
- Must provide native functionality (widgets, complications, notifications)
- Nightguard succeeds by offering watch app + native display

### Guideline 4.3: Spam / Multiple Apps

Apps that are essentially the same app with different skins may be rejected.

**Implications:**
- Can't submit "Nightscout Follower", "Nightscout CGM", "Nightscout AID" as separate apps if they share 90% code
- Multiple apps acceptable if they serve genuinely different use cases

### Guideline 5.1: Safety

Medical/health apps face higher scrutiny for safety claims.

**Implications:**
- AID controllers (Loop, Trio) cannot make FDA-unapproved dosing claims
- Must disclaim "for educational/research purposes only"
- This is why Loop/Trio are self-build TestFlight only

### Guideline 2.5.1: Software Requirements

Apps must use documented APIs and work with current iOS versions.

**Implications:**
- Private/reverse-engineered APIs (like Dexcom's BLE) may be problematic
- DiaBLE succeeds by using NFC (public API) for Libre

---

## Architecture Decision: Monolithic vs Multi-App

### Option A: Multiple Specialized Apps (Current State)

**Pros:**
- Each app can focus on its core competency
- App Store approval per app (less risk of single rejection blocking all)
- Different maintainer teams can work independently
- Different privacy/permission requirements per app

**Cons:**
- Duplicated code across apps
- User must install multiple apps
- Inconsistent UX across ecosystem
- Harder to coordinate features

### Option B: Single Monolithic App

**Pros:**
- Single install for users
- Unified UX
- Code sharing is natural
- Single App Store submission

**Cons:**
- Kitchen sink - bloat for users who only need one feature
- Single point of failure for App Store approval
- AID controller functionality likely blocks App Store approval
- Larger maintenance burden on single team

### Option C: Modular App with Extensions (Recommended)

**Pros:**
- Core app provides shared services (Nightscout sync, notifications)
- Feature modules as App Extensions or separate apps
- Share code via Swift Packages
- Each extension can have own entitlements

**Architecture:**
```
NightscoutCore.framework (SPM package)
├── NightscoutKit (API client)
├── GlucoseKit (data models)
└── NotificationKit (alerts)

Apps:
├── Nightscout (main app) - App Store
│   ├── Widget Extension
│   ├── Watch App
│   └── Notification Extension
├── NightscoutFollow (follower) - App Store  
│   └── Uses NightscoutCore
├── DiaBLE (CGM reader) - App Store
│   └── Optional: NightscoutKit for upload
└── [AID Controllers remain self-build]
    └── Can use NightscoutCore for sync
```

**Cons:**
- Requires architectural investment
- Framework versioning complexity
- Must coordinate releases

---

## Ready Queue

### #1: Swift Package Ecosystem Assessment ✅ COMPLETE

**Priority**: P2  
**Effort**: Research (4-8 hours)
**Status**: ✅ Complete 2026-01-31
**Deliverable**: `docs/10-domain/swift-package-ecosystem-assessment.md`

**Tasks:**
- [x] Inventory all Swift code shared via git submodules
- [x] Assess SPM conversion feasibility for each library
- [x] Document circular dependencies blocking conversion
- [x] Propose phased migration path

**Key Findings:**
- LoopWorkspace: 20 submodules from LoopKit org
- Trio: 11 forks in loopandlearn org with `trio` branches
- 10 libraries shared between Loop/Trio
- LoopKit Package.swift explicitly marked incomplete
- Only LoopCaregiverKit uses SPM properly
- ~90% code duplication between Loop/Trio

**Gaps Added:** GAP-SPM-001, GAP-SPM-002

### #2: NightscoutKit Swift SDK Design

**Priority**: P1  
**Status**: ✅ Complete  
**Deliverable**: `docs/sdqctl-proposals/nightscoutkit-swift-sdk-design.md`

**Completed Tasks:**
- [x] Define API surface (v3 first, v1 compatibility layer)
- [x] Design authentication flow (JWT, API secret, token)
- [x] Define data models matching OpenAPI specs
- [x] Async/await pattern (actor-based client)
- [x] Incremental sync via /history endpoint

**Key Decisions:**
- Build on `gestrich/NightscoutKit` (already SPM, used by LoopCaregiver)
- Actor-based `NightscoutClient` for thread safety
- No LoopKit dependency in core (maximize reusability)

**Gap Refs:** GAP-API-003 (No v3 adoption path for iOS)

### #3: App Store Pathway Analysis ✅ COMPLETE

**Priority**: P2  
**Effort**: Research (4-8 hours)
**Status**: ✅ Complete 2026-01-31
**Deliverable**: `docs/10-domain/app-store-pathway-analysis.md`

**Tasks:**
- [x] Document DiaBLE's successful App Store submission strategy
- [x] Analyze Nightguard's App Store presence
- [x] Research "Not Medical Advice" disclaimer patterns
- [x] Identify which features require self-build vs App Store viable

**Key Findings:**
- App Store viable: NFC, HTTP APIs, display-only, disclaimers
- Self-build required: AID dosing, pump control, reverse-engineered BLE
- 3 disclaimer patterns: README, explicit rejection, first-launch acceptance

**Decision Matrix Created**: 14 features evaluated for App Store viability

### #4: Cross-Platform Testing Infrastructure Design ✅ COMPLETE

**Priority**: P2  
**Effort**: Medium (8-16 hours)
**Status**: ✅ Complete 2026-01-31
**Deliverable**: `docs/10-domain/cross-platform-testing-infrastructure-design.md`

**Tasks:**
- [x] Evaluate xtool for Linux iOS builds (per spm-cross-platform-proposal.md)
- [x] Design CI matrix for Swift testing
- [x] Create shared test vectors for algorithm validation
- [x] Propose mock infrastructure for BLE/CGM testing

**Key Findings:**
- xtool viable for algorithm-only packages, not full apps
- 3-tier CI: ubuntu syntax → ubuntu algorithms → macos full
- 90% CI cost reduction by running most tests on Linux
- Protocol-based mocks enable hardware-independent testing

**Gaps Added**: GAP-TEST-004, GAP-TEST-005
**Requirements Added**: REQ-TEST-004, REQ-TEST-005

### #5: Follower/Caregiver Feature Consolidation ✅ COMPLETE

**Priority**: P2  
**Effort**: Research (4-8 hours)
**Status**: ✅ Complete 2026-01-31
**Deliverable**: `docs/10-domain/follower-caregiver-feature-consolidation.md`

**Tasks:**
- [x] Compare LoopFollow vs LoopCaregiver feature sets
- [x] Identify overlap and unique capabilities
- [x] Propose shared component extraction
- [x] Document remote command security requirements

**Key Findings:**
- LoopFollow: 432 Swift, alarms ✅, Watch ❌, Widgets ❌
- LoopCaregiver: 138 Swift, alarms ❌, Watch ✅, Widgets ✅
- 3 protocols: Trio TRC (AES-GCM), Loop APNS (JWT), NS API (OTP)

**Proposed Packages**: NightscoutFollowerKit, RemoteCommandKit, GlucoseAlarmKit

**Gaps Added**: GAP-FOLLOW-001/002, GAP-CAREGIVER-001/002
**Requirements Added**: REQ-FOLLOW-001/002/003/004

---

## Backlog

### #6: Widget Kit Standardization

**Priority**: P3  
**Effort**: Medium

**Description:** Standardize glucose display widgets across apps.

**Tasks:**
- [ ] Audit existing widget implementations (Nightguard, DiaBLE, xDrip4iOS)
- [ ] Propose shared GlucoseWidget component
- [ ] Define widget data model matching Nightscout entries

### #7: Apple Watch Complications Survey

**Priority**: P3  
**Effort**: Low

**Description:** Document watch complication approaches across ecosystem.

**Tasks:**
- [ ] Inventory watch apps (Loop, Trio, Nightguard, xDrip4iOS)
- [ ] Compare data refresh strategies
- [ ] Identify shared complication opportunities

### #8: HealthKit Integration Audit

**Priority**: P2  
**Effort**: Medium

**Description:** Audit HealthKit usage across apps for consistency.

**Tasks:**
- [ ] Document which apps write to HealthKit (Loop, Trio)
- [ ] Document which apps read from HealthKit
- [ ] Identify duplicate/conflicting writes
- [ ] Propose coordination mechanism

### #9: BLE CGM Library Consolidation

**Priority**: P2  
**Effort**: High

**Description:** Assess feasibility of unified BLE CGM library.

**Tasks:**
- [ ] Compare CGMBLEKit vs DiaBLE BLE implementations
- [ ] Identify protocol differences (G6 vs G7 vs Libre)
- [ ] Propose abstraction layer for CGM BLE

**Gap Refs:** GAP-CGM-002, GAP-G7-*

### #10: TestFlight Distribution Infrastructure

**Priority**: P3  
**Effort**: Medium

**Description:** Document and standardize TestFlight distribution patterns.

**Tasks:**
- [ ] Survey current TestFlight groups and access patterns
- [ ] Document build/sign requirements for each app
- [ ] Propose streamlined distribution workflow

---

## Deferred

### #D1: FDA Pre-Submission Strategy

**Priority**: P4  
**Effort**: Very High

**Description:** Explore FDA pathway for AID controllers.

**Notes:** This is a major undertaking beyond current scope. Loop and Trio currently operate as "DIY" systems specifically to avoid FDA regulation.

### #D2: Multi-Platform Strategy (Android parity)

**Priority**: P4  
**Effort**: Very High

**Description:** Evaluate cross-platform frameworks (KMM, Flutter, React Native).

**Notes:** Current iOS ecosystem is native Swift. Cross-platform would require significant investment with unclear benefits given existing Android apps (AAPS, xDrip+).

---

## Completed

| Item | Date | Notes |
|------|------|-------|
| **#2: NightscoutKit SDK Design** | 2026-01-31 | `nightscoutkit-swift-sdk-design.md` - v3-first, actor-based |
| Initial ecosystem survey | 2026-01-31 | 8 iOS apps identified |
| Code sharing assessment | 2026-01-31 | Submodule-based, not SPM |
| Apple guidelines review | 2026-01-31 | 4.2, 4.3, 5.1 relevant |

---

## Cross-References

- [spm-cross-platform-proposal.md](../spm-cross-platform-proposal.md) - SPM conversion lessons
- [cross-platform-testing-research.md](../../10-domain/cross-platform-testing-research.md) - Testing infrastructure
- [stakeholder-priority-analysis.md](../../60-research/stakeholder-priority-analysis.md) - Stakeholder needs
- [ECOSYSTEM-BACKLOG.md](../ECOSYSTEM-BACKLOG.md) - Parent backlog

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-31 | Recommend Option C (Modular) | Balances code sharing with App Store constraints |
| 2026-01-31 | Prioritize NightscoutKit SDK | Unblocks GAP-API-003, enables v3 adoption |
| 2026-01-31 | AID controllers remain self-build | FDA/App Store constraints on medical devices |
