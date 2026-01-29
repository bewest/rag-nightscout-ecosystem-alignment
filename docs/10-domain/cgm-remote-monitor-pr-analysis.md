# cgm-remote-monitor Open PR Analysis

> **Generated**: 2026-01-29  
> **Total Open PRs**: 68  
> **Date Range**: 2021-02-16 to 2026-01-25  
> **Purpose**: Ecosystem impact assessment and project trajectory analysis

## Executive Summary

The cgm-remote-monitor repository has **68 open PRs** spanning nearly 5 years. This analysis categorizes them by ecosystem impact, identifies high-priority items for the alignment project, and documents project trajectory patterns.

### Key Findings

1. **Infrastructure modernization active**: MongoDB 5x, Docker improvements, Node.js upgrade
2. **AAPS integration gap**: Heart rate storage and TBR rendering PRs pending 2+ years
3. **Multi-insulin API**: Cross-project feature used by xDrip+ and Nightscout-reporter awaits merge
4. **Remote Commands**: Critical Loop caregiver feature stalled since 2022
5. **Timezone handling**: Long-standing issue with multiple fix attempts

---

## PR Categories

### Category Overview

| Category | Count | Ecosystem Impact |
|----------|-------|------------------|
| Infrastructure/DevOps | 15 | High - affects deployment |
| API/Data Model | 8 | Critical - affects all clients |
| UI/Reports | 14 | Medium - user experience |
| Testing/Quality | 6 | Medium - reliability |
| Internationalization | 6 | Low - localization |
| Plugins | 5 | Medium - feature parity |
| Documentation | 4 | Low |
| Clock Views | 5 | Low |
| Stale/Abandoned | 5 | None |

---

## High-Priority Ecosystem PRs

### Tier 1: Critical Ecosystem Impact

#### PR#8421 - MongoDB 5x Support
| Attribute | Value |
|-----------|-------|
| Author | bewest |
| Created | 2026-01-19 |
| Size | +39,980 / -7,689 (117 files) |
| Status | Active WIP |

**Description**: Updates MongoDB driver for compatibility with MongoDB 5.x+.

**Ecosystem Impact**:
- Enables modern MongoDB deployments (Atlas, self-hosted)
- Prerequisite for Nocturne migration path
- Affects all projects uploading to Nightscout

**Gaps Addressed**: Database infrastructure modernization

---

#### PR#8083 - Heart Rate Storage
| Attribute | Value |
|-----------|-------|
| Author | buessow |
| Created | 2023-08-26 |
| Size | +158 / -5 (10 files) |
| Status | Pending 2.5 years |

**Description**: Adds HeartRate collection for long-term HR storage from AAPS.

**Ecosystem Impact**:
- **AAPS**: Primary consumer for HR data uploads
- **xDrip+**: Could leverage for CGM+HR correlation
- Extends biometric data model beyond glucose

**API Changes**: New `heartrate` collection in APIv3

**Reference**: [AAPS HR Spec](https://docs.google.com/document/d/1RwsHYN0xWBZ6WfaFFSqMxqc4Jl4gLZJOipbpBVzyiQk/)

**Gap**: GAP-API-HR (new)

---

#### PR#8261 - Multi-Insulin API
| Attribute | Value |
|-----------|-------|
| Author | gruoner |
| Created | 2024-05-09 |
| Size | +169 / -0 (6 files) |
| Status | Pending 1.7 years |

**Description**: New `insulin` entity for multiple insulin profiles (names, curves, colors).

**Ecosystem Impact**:
- **xDrip+**: Already using this API
- **Nightscout-reporter**: Already using this API
- **Loop/Trio**: Could map insulin model types
- **AAPS**: Multi-insulin IOB calculations

**API Changes**: New `insulin` collection (modeled on food API)

**Gap**: GAP-INSULIN-001 (insulin model interoperability)

---

#### PR#7791 - Remote Commands
| Attribute | Value |
|-----------|-------|
| Author | gestrich |
| Created | 2022-12-29 |
| Size | +729 / -2 (11 files) |
| Status | Stalled 3+ years |

**Description**: Command queue for remote Loop control with status tracking.

**Ecosystem Impact**:
- **Loop**: Critical for caregiver remote bolus/carbs
- **Trio**: Would need similar integration
- Addresses push notification reliability issues

**Problems Solved**:
1. Command delivery status tracking
2. Push notification delay handling
3. Command expiration management

**Gap**: GAP-REMOTE-CMD (remote command infrastructure)

---

### Tier 2: Significant Ecosystem Impact

#### PR#8281 - AAPS TBR Rendering Granularity
| Attribute | Value |
|-----------|-------|
| Author | MilosKozak (AAPS maintainer) |
| Created | 2024-08-07 |
| Size | +4 / -4 (2 files) |
| Status | Pending 1.5 years |

**Description**: Increases basal rendering granularity for AAPS TBR visualization.

**Ecosystem Impact**: AAPS basal display accuracy on Nightscout

---

#### PR#8405 - Timezone Display Fix
| Attribute | Value |
|-----------|-------|
| Author | ryceg |
| Created | 2025-11-18 |
| Size | +194 / -5 |
| Status | Recent |

**Description**: Shows device timezone (from profile) instead of browser timezone.

**Ecosystem Impact**:
- Fixes cross-timezone caregiver confusion
- Uses profile API for timezone source
- Aligns with REQ-INTEROP-002 (timestamp handling)

---

#### PR#8366 - 2025 Reports Enhancement
| Attribute | Value |
|-----------|-------|
| Author | dburren (Nascence Biomed) |
| Created | 2025-05-28 |
| Size | +751 / -133 |
| Status | WIP |

**Description**: Enhanced reporting with dual BG ranges, new timeframes, extended statistics.

**Ecosystem Impact**:
- Professional/clinical use case improvements
- Aligns with Statistics API proposal
- Potential MCP report enhancement patterns

---

#### PR#8419 - iOS Loop Push Notification Tests
| Attribute | Value |
|-----------|-------|
| Author | je-l |
| Created | 2026-01-15 |
| Size | +532 / -5 |
| Status | Recent, Active |

**Description**: Integration tests for iOS Loop push notifications and websockets.

**Ecosystem Impact**:
- Improves Loop→Nightscout reliability
- Coverage: 63.8% → 65.4%
- Regression protection for remote features

---

### Tier 3: Infrastructure/Modernization

| PR | Title | Author | Impact |
|----|-------|--------|--------|
| #8417 | Multi-build Docker | gluk0 | Reduces image size, dev tooling |
| #8416 | Docker Mongo 8.2 | savek-cc | Enables latest MongoDB |
| #8357 | Node.js Upgrade | ninelore | Runtime modernization |
| #8360 | Remove Lodash | ryceg | Bundle size, security |
| #8355 | Remove crypto-browserify | ryceg | Security, bundle size |
| #8348 | Remove Moment | ryceg | Bundle size, maintenance |
| #8377 | GitHub Actions badge | earldouglas | CI modernization |
| #8378 | mmol test fixes | earldouglas | Test reliability |

---

## Stale PRs (3+ years)

| PR | Title | Created | Notes |
|----|-------|---------|-------|
| #6875 | Carportal via virtual assistants | 2021-02-16 | Alexa/voice features |
| #6928 | Custom test framework | 2021-02-25 | Testing infrastructure |
| #6974 | Alexa partial translations | 2021-03-22 | i18n |
| #7150 | README update | 2021-10-27 | Documentation |
| #7221 | Pushover priority disable | 2021-12-07 | Notification config |

---

## Project Trajectory Analysis

### Development Patterns

1. **Modernization Wave (2025-2026)**
   - Node.js upgrade, Lodash removal, Moment removal
   - Docker improvements, MongoDB 5x/8.2
   - Contributors: ryceg, earldouglas, ninelore, bewest

2. **AAPS Integration Backlog**
   - Heart rate, TBR rendering, multi-insulin
   - Authored by AAPS maintainers (MilosKozak, buessow)
   - Long pending = integration friction

3. **Remote Control Gap**
   - Remote Commands (Loop) stalled
   - No Trio equivalent visible
   - Critical caregiver use case unaddressed

4. **Reporting Evolution**
   - 2025 reports, A1c estimates, GMI calculations
   - Clinical/professional use case growing

### Contributor Activity

| Contributor | PRs | Focus |
|-------------|-----|-------|
| ryceg | 7 | Modernization, cleanup |
| bewest | 4 | MongoDB, infrastructure |
| earldouglas | 5 | CI, testing, quality |
| KelvinKramp | 3 | Clock views |
| gruoner | 2 | Multi-insulin |
| je-l | 2 | Testing |

---

## Gap Implications

### New Gaps Identified

| Gap ID | Title | Related PRs |
|--------|-------|-------------|
| GAP-API-HR | Heart rate collection missing | #8083 |
| GAP-INSULIN-001 | Multi-insulin API not standard | #8261, #7465 |
| GAP-REMOTE-CMD | Remote command queue | #7791 |
| GAP-TZ-001 | Timezone handling inconsistent | #8405, #8307 |

### Existing Gaps Addressed by PRs

| Gap ID | PR | Status |
|--------|-----|--------|
| GAP-DB-001 | #8421 MongoDB 5x | In progress |
| GAP-CONNECT-001 | #8281 TBR rendering | Pending |

---

## Recommendations

### For Ecosystem Alignment

1. **Prioritize PR#8083 (Heart Rate)** - Unblocks AAPS biometric sync
2. **Prioritize PR#8261 (Multi-Insulin)** - Already in use by xDrip+, needs standardization
3. **Revive PR#7791 (Remote Commands)** - Critical Loop caregiver feature
4. **Document PR#8405 timezone approach** - Potential pattern for REQ-INTEROP-002

### For Nightscout Project

1. Close/archive stale PRs (5 at 3+ years)
2. Tag PRs with ecosystem labels (AAPS, Loop, xDrip+)
3. Create milestone for "AAPS Integration" PRs
4. Merge modernization wave (Lodash, Moment, crypto removal)

### For This Workspace

1. Add PR tracker to domain backlog
2. Create conformance tests for pending API features
3. Document multi-insulin spec in OpenAPI
4. Add heart rate to entries/devicestatus spec

---

## Appendix: Full PR List by Category

### Infrastructure/DevOps (15)

| PR | Title | Author | Created |
|----|-------|--------|---------|
| 8421 | MongoDB 5x | bewest | 2026-01-19 |
| 8417 | Multi-build Docker | gluk0 | 2026-01-11 |
| 8416 | Docker Mongo 8.2 | savek-cc | 2026-01-06 |
| 8413 | Fly.io Launch | ceciliavinhas | 2025-12-30 |
| 8382 | Render.yaml | shahakz11 | 2025-07-12 |
| 8364 | GitHub Actions node.js | nspap | 2025-05-27 |
| 8357 | Node.js Upgrade | ninelore | 2025-05-12 |
| 8354 | Auto-close sync PRs | ryceg | 2025-05-09 |
| 8352 | Dev branch 15.0.4 | bewest | 2025-05-08 |
| 8326 | Node V20 apt | hershyheilpern | 2024-10-27 |
| 8300 | Docker secrets | swebster | 2024-09-10 |
| 7993 | Azure Static Web Apps | Bemowo | 2023-04-11 |
| 7656 | Deploy to Azure button | charris-msft | 2022-11-03 |
| 7639 | Oracle Cloud install | tremor | 2022-10-27 |
| 7344 | MongoDB 5 driver | hognefossland | 2022-02-16 |

### API/Data Model (8)

| PR | Title | Author | Created |
|----|-------|--------|---------|
| 8422 | Fix API3 limit error | KelvinKramp | 2026-01-25 |
| 8261 | Multi-insulin API | gruoner | 2024-05-09 |
| 8253 | API3 filter params | bniels707 | 2024-04-25 |
| 8252 | API3 multiple filters | bniels707 | 2024-04-25 |
| 8083 | Heart Rate Storage | buessow | 2023-08-26 |
| 7791 | Remote Commands | gestrich | 2022-12-29 |
| 7465 | Multi insulin (original) | gruoner | 2022-06-25 |
| 8381 | API v1 Swagger docs | arfaomar | 2025-07-03 |

### UI/Reports (14)

| PR | Title | Author | Created |
|----|-------|--------|---------|
| 8405 | Timezone display fix | ryceg | 2025-11-18 |
| 8402 | CSV exports | kelseyhuss | 2025-11-11 |
| 8398 | Omnipod overlay | cyberneticwheelbarow | 2025-11-03 |
| 8366 | 2025 reports | dburren | 2025-05-28 |
| 8330 | GMI/Revised GMI | motinis | 2024-10-28 |
| 8324 | OpenAPS pill fix | yodax | 2024-10-24 |
| 8307 | Careportal timezone | adamlounds | 2024-09-29 |
| 8281 | AAPS TBR rendering | MilosKozak | 2024-08-07 |
| 8236 | Clock color option | JaredDRobbins | 2024-04-10 |
| 8084 | Replace Google Fonts | gardenrobot | 2023-08-29 |
| 8081 | Historic COB display | bjornoleh | 2023-08-25 |
| 8064 | Careportal date fix | jpcunningh | 2023-08-18 |
| 7829 | A1c Daily Stats | Foxy7 | 2023-01-13 |
| 7342 | Glucose pentagon | mushroom-dev | 2022-02-15 |

### Testing/Quality (6)

| PR | Title | Author | Created |
|----|-------|--------|---------|
| 8419 | Loop push/websocket tests | je-l | 2026-01-15 |
| 8410 | Fix async/Promise nesting | bniels707 | 2025-11-26 |
| 8378 | mmol test fixes | earldouglas | 2025-06-28 |
| 8362 | Speed up test-ci | je-l | 2025-05-23 |
| 7875 | Playwright experiments | bewest | 2023-02-05 |
| 6928 | Custom test framework | flummoxedca | 2021-02-25 |

### Modernization (5)

| PR | Title | Author | Created |
|----|-------|--------|---------|
| 8385 | Wake lock toggle | earldouglas | 2025-07-26 |
| 8360 | Remove Lodash | ryceg | 2025-05-19 |
| 8355 | Remove crypto-browserify | ryceg | 2025-05-10 |
| 8348 | Remove Moment | ryceg | 2025-05-08 |
| 7986 | Bump xml2js | dependabot | 2023-03-21 |

---

## Source

- GitHub API: `https://api.github.com/repos/nightscout/cgm-remote-monitor/pulls`
- Query date: 2026-01-29
- Repository: `externals/cgm-remote-monitor-official/`
