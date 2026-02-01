# Stakeholder Priority Analysis

**Created**: 2026-01-17  
**Purpose**: Map different stakeholder priorities against documented gaps to identify high-leverage changes and sources of friction

---

## Executive Summary

This workspace documents **91+ gaps** across the Nightscout/AID ecosystem. Different stakeholders have different priorities, and these priorities sometimes conflict. Understanding these tensions is essential to making progress.

**The Core Tension**: Nightscout core maintainers prioritize *infrastructure modernization* (MongoDB, testing, release velocity), but downstream app developers are blocked on *semantic gaps* (override tracking, sync identity, authority hierarchy). Neither can fully proceed without coordinated effort.

---

## Stakeholder Categories

### 1. Nightscout Core Team (cgm-remote-monitor)

**Visible Priorities** (from branch names and documentation):

| Priority | Evidence | Impact |
|----------|----------|--------|
| MongoDB modernization | Branch: `wip/replit/with-mongodb-update` | Unblocks hosting providers, security updates |
| Testing infrastructure | `testing-modernization-proposal.md` exists | Faster, safer releases |
| API v3 adoption | Comprehensive v3 documentation | Modern auth, granular permissions |
| Technical debt reduction | `modernization-roadmap.md` referenced | Maintainability, contributor onboarding |
| UI modernization | `dashboard-ui-audit.md` mentions jQuery/D3 legacy | User experience |

**What Blocks Them**:
- Getting downstream testing of breaking changes (5+ apps depend on v1 API)
- No unified test harness across ecosystem
- Review capacity for large infrastructure PRs

**Key Constraint**: Infrastructure changes affect everyone, so changes must be backwards-compatible or carefully coordinated.

---

### 2. iOS AID Controllers (Loop, Trio)

**Visible Priorities** (from gap dependencies):

| Priority | Blocked By | Gap IDs |
|----------|------------|---------|
| Reliable sync without duplicates | POST-only creates duplicates, no upsert | GAP-TREAT-005, GAP-003 |
| Override lifecycle tracking | No supersession fields in Nightscout | GAP-001, GAP-SYNC-004 |
| Remote command security | OTP inconsistency, no authority hierarchy | GAP-REMOTE-001, GAP-AUTH-002 |
| Algorithm debugging | Effect timelines not uploaded | GAP-SYNC-002, GAP-SYNC-005 |
| API v3 adoption | No Swift SDK, migration complexity | GAP-API-003 |

**What Blocks Them**:
- v3 API requires Swift SDK development effort
- Limited maintainer bandwidth (volunteer projects)
- Breaking changes require App Store review cycles

**Key Constraint**: iOS app updates require App Store approval, making breaking changes costly.

---

### 3. Android AID Controllers (AAPS)

**Visible Priorities** (from gap patterns):

| Priority | Status | Gap IDs |
|----------|--------|---------|
| v3 API usage | **Already using v3** | N/A (ahead of ecosystem) |
| Extended bolus support | Has it, but not portable | GAP-PUMP-002, GAP-TREAT-004 |
| eCarbs support | Has it, but not recognized by iOS apps | GAP-TREAT-007 |
| Multi-insulin tracking | Would benefit MDI users | GAP-INS-002 |

**What Blocks Them**:
- iOS apps don't recognize AAPS-specific features
- No standardized extended bolus representation
- Waiting for ecosystem to catch up on v3

**Key Constraint**: Features AAPS has implemented aren't recognized by other ecosystem members.

---

### 4. CGM Data Producers (xDrip+ Android, xDrip4iOS, DiaBLE)

**Visible Priorities** (from CGM gap cluster):

| Priority | Blocked By | Gap IDs |
|----------|------------|---------|
| Calibration provenance tracking | No schema field for algorithm | GAP-CGM-001 |
| Bridge device attribution | Device field not structured | GAP-CGM-002, GAP-ENTRY-003 |
| Raw value preservation | iOS APIs don't expose raw | GAP-CGM-005 |
| Follower source distinction | No sourceType field | GAP-CGM-006 |

**What Blocks Them**:
- Nightscout schema changes require coordination
- iOS platform limitations for raw values
- No standard device field format

**Key Constraint**: Schema changes require both Nightscout core and all uploaders to coordinate.

---

### 5. Follower Apps (LoopCaregiver, LoopFollow, Nightguard)

**Visible Priorities** (from remote command gaps):

| Priority | Blocked By | Gap IDs |
|----------|------------|---------|
| Reliable remote commands | OTP not required for all commands | GAP-REMOTE-001 |
| Command status tracking | Different status models per system | GAP-REMOTE-005 |
| Key rotation | No automatic rotation mechanism | GAP-REMOTE-003 |
| Unified auth experience | Different auth per system | GAP-REMOTE-004 |

**What Blocks Them**:
- Security changes require controller app updates
- No cross-system command standard
- Volunteer maintainer bandwidth

**Key Constraint**: Security improvements require coordinated releases across multiple apps.

---

### 6. Nightscout-Connect (Data Bridges)

**Visible Priorities** (from inventory):

| Priority | Status | Evidence |
|----------|--------|----------|
| Tidepool integration | ✅ Inventoried - GAP-TIDEPOOL-003 | `docs/10-domain/tidepool-integration-inventory.md` |
| Tandem integration | TODO - Not implemented | Inventory |
| Data ingestion reliability | Primary purpose | Inventory |

**What Blocks Them**:
- Lower integration priority (downstream of core)
- Depends on stable Nightscout core
- Data source API access/partnerships

**Key Constraint**: Bridge work is downstream of core Nightscout stability.

---

### 7. Research & Analytics Users

**Visible Priorities** (from algorithm/sync gaps):

| Priority | Blocked By | Gap IDs |
|----------|------------|---------|
| Algorithm comparison | Effect timelines not uploaded | GAP-SYNC-002 |
| IOB reconstruction | Insulin model metadata not synced | GAP-INS-001, GAP-INS-003 |
| Calibration analysis | Algorithm not tracked | GAP-CGM-001 |
| Treatment audit trails | No edit history, soft delete | GAP-TREAT-006 |

**What Blocks Them**:
- Metadata not captured at treatment time
- Historical data already incomplete
- No standardized export format

**Key Constraint**: Research needs require schema additions that benefit few operational users.

---

### 8. End Users & Caregivers

**Visible Priorities** (inferred from remote command and usability gaps):

| Priority | Blocked By | Gap IDs |
|----------|------------|---------|
| Safe remote commands | OTP inconsistency across command types | GAP-REMOTE-001 |
| Reliable data sync | Duplicates, zombie data | GAP-TREAT-005, GAP-API-001 |
| Accurate history | Override lifecycle not tracked | GAP-001, GAP-SYNC-004 |
| Easy device pairing | No key rotation, static secrets | GAP-REMOTE-003 |

**What Blocks Them**:
- Security improvements may add friction (more OTP prompts)
- UI complexity increases with more features
- Dependent on volunteer maintainer capacity

**Key Constraint**: Users bear the friction cost of both security improvements and ecosystem fragmentation.

---

### 9. Hosting Providers & Operations

**Visible Priorities** (from infrastructure work):

| Priority | Evidence | Gap IDs |
|----------|----------|---------|
| MongoDB 5.x+ support | Branch `wip/replit/with-mongodb-update` | Infrastructure |
| Node.js modernization | Dependency on security updates | Infrastructure |
| Simplified deployment | Docker, Heroku, Azure patterns | Infrastructure |
| Reduced maintenance burden | Technical debt documentation | Infrastructure |

**What Blocks Them**:
- Breaking changes require ecosystem-wide testing
- Database migrations risk data loss
- No automated regression test suite

**Key Constraint**: Infrastructure updates affect all hosted instances simultaneously.

---

## Gap Impact Matrix

Which gaps block which stakeholders? Higher blocking count = higher leverage.

| Gap ID | Description | Stakeholders Blocked | Count |
|--------|-------------|---------------------|-------|
| **GAP-003** | No unified sync identity field | Loop, Trio, AAPS, xDrip+, Research | 5 |
| **GAP-001** | No override supersession tracking | Loop, Trio, AAPS, Followers, Research | 5 |
| **GAP-REMOTE-001** | Override commands skip OTP | Loop, Trio, Followers, Caregivers | 4 |
| **GAP-SYNC-002** | Effect timelines not uploaded | Loop, Trio, AAPS, Research | 4 |
| **GAP-TREAT-002** | Duration unit inconsistency | Loop, Trio, AAPS, Research | 4 |
| **GAP-AUTH-001** | enteredBy unverified | All controllers, Followers | 4 |
| **GAP-AUTH-002** | No authority hierarchy | Loop, Trio, AAPS, Followers | 4 |
| **GAP-INS-001** | Insulin model not synced | Loop, Trio, AAPS, Research | 4 |
| **GAP-API-003** | No v3 adoption path for iOS | Loop, Trio, Research | 3 |
| **GAP-CGM-001** | Calibration algorithm not tracked | xDrip+, DiaBLE, Research | 3 |
| **GAP-TREAT-005** | Loop POST-only duplicates | Loop, Trio, Nightscout Core | 3 |
| **GAP-API-001** | v1 cannot detect deletions | Loop, Trio, xDrip+ | 3 |

---

## Friction Points Analysis

### Friction 1: Infrastructure vs. Features

| Nightscout Core Wants | App Developers Want |
|----------------------|---------------------|
| MongoDB 5.x+ support | Override supersession fields |
| Modern test harness | Sync identity standardization |
| jQuery → React migration | Effect timeline uploads |
| Node.js version updates | Authority hierarchy |

**Resolution Path**: Bundle high-impact schema additions with infrastructure releases.

---

### Friction 2: API v3 Adoption Gap

| v3 Users | v1 Users |
|----------|----------|
| AAPS only | Loop, Trio, xDrip+, nightscout-connect |

**v3 Benefits v1 Lacks**:
- Incremental sync via `/history/{timestamp}`
- Soft delete detection (`isValid: false`)
- Granular JWT permissions
- Deduplication feedback (`isDeduplication: true`)

**Resolution Path**: Create Swift SDK for v3, document migration benefits clearly.

---

### Friction 3: Platform Fragmentation

| Android Has | iOS Lacks |
|-------------|-----------|
| Extended/combo boluses | Extended bolus support |
| eCarbs with duration | eCarbs recognition |
| v3 API usage | v3 API client |
| Multi-insulin tracking | Multi-insulin fields |

**Resolution Path**: Standardize representations in Nightscout schema, let each platform adopt at their pace.

---

### Friction 4: Security vs. Usability

| Security Improvement | Friction Cost |
|---------------------|---------------|
| OTP for all remote commands | Override convenience drops |
| Key rotation | User must re-pair devices |
| Command signing | Implementation complexity |
| OIDC integration | External dependency |

**Resolution Path**: Make security improvements opt-in or gracefully degrading.

---

## High-Leverage Unlock Points

These changes would unblock the most downstream value:

### Tier 1: Foundation Fixes (Unblocks 5+ stakeholders)

| Change | Gaps Resolved | Effort | Notes |
|--------|---------------|--------|-------|
| **Standardize sync identity field** | GAP-003 | Medium | Schema + client updates |
| **Add override supersession fields** | GAP-001, GAP-SYNC-004 | Medium | Schema + client updates |
| **OTP for all remote commands** | GAP-REMOTE-001 | Medium* | Requires coordinated releases across Loop + caregiver apps |
| **Create v3 Swift SDK** | GAP-API-003 | High | Major iOS investment |

*OTP change appears small but requires coordinated releases across multiple apps.

### Tier 2: Semantic Enrichment (Unblocks 3-4 stakeholders)

| Change | Gaps Resolved | Effort | Notes |
|--------|---------------|--------|-------|
| **Add effect timelines to devicestatus** | GAP-SYNC-002, GAP-ALG-* | Medium | Controllers, research |
| **Standardize duration units** | GAP-TREAT-002, GAP-PUMP-003 | Medium* | Convention change across clients |
| **Add insulin model metadata** | GAP-INS-001, GAP-INS-003 | Medium | Controllers, research |
| **Add authority hierarchy** | GAP-AUTH-002 | High | Depends on OIDC Actor Identity proposal |

*Duration unit standardization is convention-only but requires documentation and client updates.

### Tier 3: Data Provenance (Unblocks 2-3 stakeholders)

| Change | Gaps Resolved | Effort | Stakeholders Unblocked |
|--------|---------------|--------|------------------------|
| **Structure device field format** | GAP-CGM-002, GAP-ENTRY-003 | Low | CGM producers, research |
| **Add calibration algorithm field** | GAP-CGM-001 | Low | CGM producers, research |
| **Add follower source indicator** | GAP-CGM-006 | Low | CGM producers, research |

---

## Recommended Coordination Strategy

### Phase 1: Convention Alignment (Backwards compatible, documentation-driven)

1. **Structure device field format** (GAP-CGM-002) - Convention, backwards compatible
2. **Document duration unit expectations** (GAP-TREAT-002) - Clarify minutes for Nightscout interchange
3. **Add calibration algorithm to device string** (GAP-CGM-001) - Convention, no schema change

### Phase 2: Schema Additions (Bundled with MongoDB/infrastructure releases)

1. **Add `supersededBy`, `actualEndType` to overrides** (GAP-001)
2. **Add `syncIdentifier` upsert support** (GAP-003)
3. **Add `insulinModel` object to treatments** (GAP-INS-001)

### Phase 3: Security Improvements (Coordinated cross-app releases)

1. **OTP for all remote commands** (GAP-REMOTE-001) - Requires Loop + caregiver app coordination
2. **Key rotation mechanism** (GAP-REMOTE-003) - Depends on security roadmap

### Phase 4: Ecosystem Enablement (High effort, strategic)

1. **Swift SDK for v3 API** (GAP-API-003)
2. **Authority hierarchy implementation** (GAP-AUTH-002) - Depends on [OIDC Actor Identity proposal](../../externals/cgm-remote-monitor/docs/proposals/oidc-actor-identity-proposal.md)
3. **Effect timeline schema and uploads** (GAP-SYNC-002)

**Note**: Phases 2-4 benefit from coordination with the Nightscout [Conflict Resolution](../../externals/cgm-remote-monitor/docs/proposals/conflict-resolution.md) and [Agent Control Plane](../../externals/cgm-remote-monitor/docs/proposals/agent-control-plane-rfc.md) proposals.

---

## Cross-References

- [Gaps Document](../../traceability/gaps.md) - Full gap details
- [Requirements Document](../../traceability/requirements.md) - Formal requirements
- [Nightscout API Comparison](../10-domain/nightscout-api-comparison.md) - v1 vs v3 analysis
- [Remote Commands Comparison](../10-domain/remote-commands-comparison.md) - Security analysis
- [AID Controller Sync Patterns](../../mapping/cross-project/aid-controller-sync-patterns.md) - Sync behavior

---

## Appendix: Gap Category Summary

| Category | Count | Top Blockers |
|----------|-------|--------------|
| Treatment Sync | 7 | GAP-TREAT-001 through GAP-TREAT-007 |
| CGM Data Sources | 6 | GAP-CGM-001 through GAP-CGM-006 |
| API Fragmentation | 5 | GAP-API-001 through GAP-API-005 |
| Remote Commands | 7 | GAP-REMOTE-001 through GAP-REMOTE-007 |
| Override Tracking | 4 | GAP-001, GAP-002, GAP-SYNC-004 |
| Algorithm Opacity | 8 | GAP-ALG-001 through GAP-ALG-008, GAP-SYNC-002 |
| Insulin Models | 4 | GAP-INS-001 through GAP-INS-004 |
| Pump Communication | 9 | GAP-PUMP-001 through GAP-PUMP-009 |
| Authorization | 2 | GAP-AUTH-001, GAP-AUTH-002 |
| BLE Protocol | 5 | GAP-BLE-001 through GAP-BLE-005 |
| Carb Absorption | 5 | GAP-CARB-001 through GAP-CARB-005 |
| Entry Schema | 5 | GAP-ENTRY-001 through GAP-ENTRY-005 |
| DeviceStatus | 4 | GAP-DS-001 through GAP-DS-004 |
| G7 Protocol | 4 | GAP-G7-001 through GAP-G7-004 |

**Total**: 91+ documented gaps across 14 categories
