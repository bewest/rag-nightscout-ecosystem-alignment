# Capability Layer Matrix

This document maps commercial and open-source AID systems to the [Progressive Enhancement Framework](../../docs/10-domain/progressive-enhancement-framework.md) capability layers, identifying current positions and blockers.

---

## Quick Layer Reference

| Layer | Name | Key Capability |
|-------|------|----------------|
| L4 | Pump + CGM | Manual control |
| L5 | Safety Automation | Suspend, bounded corrections |
| L6 | Full AID | Closed-loop control |
| L7 | Networked History | Remote visibility (Nightscout-style) |
| L8 | Remote Controls | Delegated actions at a distance |
| L9 | Delegate Agents | Autonomous agents with context |

---

## Commercial Systems

### Tandem t:slim X2 + Control-IQ

| Aspect | Current State |
|--------|---------------|
| **Current Layer** | L6 (Full AID) + Partial L7 (cloud upload/reports) |
| **Automation** | Control-IQ automates basal adjustments, can deliver correction boluses |
| **Phone Control** | Smartphone bolus via Tandem mobile app (compatible versions) |
| **Remote Following** | CGM sharing via Dexcom Share/Follow (glucose-only, no pump/insulin fidelity) |

**L8 Blockers**:
- No broadly-supported, audited, caregiver-grade remote command channel for insulin actions
- No unified narrative feed including insulin decisions in real time for delegates

**L9 Blockers**:
- Closed ecosystem, no API for third-party agents
- No out-of-band signal integration (exercise, hormones)

---

### Tandem Mobi

| Aspect | Current State |
|--------|---------------|
| **Current Layer** | L6 (Full AID) + Partial L7, user-centric phone control |
| **Automation** | Full Control-IQ closed-loop |
| **Phone Control** | Android smartphone support (FDA cleared Dec 2025, broader Jan 2026) |
| **Remote Following** | Same Dexcom Share pattern as t:slim X2 |

**L8/L9 Blockers**: Same as t:slim X2. Delegation for caregivers is not "full-fidelity remote operations" as a first-class feature.

---

### Insulet Omnipod 5

| Aspect | Current State |
|--------|---------------|
| **Current Layer** | L6 (Full AID) + Stronger phone control, Partial L7 |
| **Automation** | SmartAdjust algorithm (hybrid closed-loop) |
| **Phone Control** | Full control via Omnipod 5 app (iOS/Android) |
| **Remote Following** | Dexcom Share/Follow (CGM only); pod status in app |

**L7 Details**:
- Glooko integration for retrospective data
- No real-time insulin/dosing feed for caregivers

**L8 Blockers**:
- No remote bolus capability
- Caregiver app provides viewing only, not control

**L9 Blockers**:
- Closed algorithm, no API for agent integration
- No documented mechanism for contextual inputs

---

### Insulet Omnipod Dash

| Aspect | Current State |
|--------|---------------|
| **Current Layer** | L4 (Pump + CGM manual control) |
| **Automation** | None (manual bolus calculator only) |
| **Phone Control** | Full via Dash app |
| **Remote Following** | Via integrations (LibreLink/Dexcom for CGM) |

**L5+ Blockers**:
- No automation; user must manually control all delivery
- Replaced by Omnipod 5 for automation users

---

## Open-Source Systems

### Loop (LoopKit)

| Aspect | Current State |
|--------|---------------|
| **Current Layer** | L6 + L7 + Partial L8 |
| **Automation** | Full closed-loop with retrospective correction |
| **Nightscout Sync** | Full bidirectional sync (treatments, devicestatus, profiles) |
| **Remote Commands** | Via LoopCaregiver (TOTP OTP), Remote 2.0 protocol |

**L7 Details** (Nightscout as narrative bus):
- Uploads: SGV (via CGM app), treatments, devicestatus with predictions
- Uses API v1 (POST-based)
- Full sync identity via `syncIdentifier`

**L8 Details** (Remote Controls):
| Command | OTP Required | Notes |
|---------|--------------|-------|
| Bolus | Yes | TOTP validation |
| Carbs | Yes | TOTP validation |
| Override | **No** | Security gap (GAP-REMOTE-001) |
| Cancel Override | **No** | Security gap |

**L8 Blockers**:
- Override commands skip OTP validation (GAP-REMOTE-001)
- No granular permission scoping (all or nothing)
- No authority hierarchy (caregiver vs clinician vs agent)

**L9 Blockers**:
- No native agent integration
- No structured API for out-of-band signals
- Manual override selection only

**Source References**:
- [LoopCaregiver Remote Commands](../loopcaregiver/remote-commands.md)
- [Remote Commands Comparison](../../docs/10-domain/remote-commands-comparison.md)

---

### AAPS (AndroidAPS)

| Aspect | Current State |
|--------|---------------|
| **Current Layer** | L6 + L7 + Partial L8 |
| **Automation** | Full closed-loop, SMB, Dynamic ISF (TDD-based), Autosens |
| **Nightscout Sync** | Full bidirectional sync via API v3 (only v3 client) |
| **Remote Commands** | SMS-based with phone whitelist + TOTP + PIN |

**L7 Details**:
- Only system using Nightscout API v3
- Proper upsert semantics, soft delete support
- Profile sync via ProfileSwitch events
- Incremental sync via `history/{timestamp}`

**L8 Details**:
| Command | Auth Required | Notes |
|---------|---------------|-------|
| Bolus | TOTP + PIN | Most secure |
| Carbs | TOTP + PIN | |
| Profile Switch | TOTP + PIN | |
| TempTarget | TOTP + PIN | |
| Loop Suspend/Resume | TOTP + PIN | |
| Pump Controls | TOTP + PIN | |
| ... 13+ total | | |

**L8 Advantages**:
- Most comprehensive command set
- All commands require authentication
- Granular safety limits via ConstraintChecker

**L8 Blockers**:
- SMS transport (not push-based)
- No role-based permissions (single phone whitelist)
- No delegation hierarchy

**L9 Blockers**:
- WEAR plugin for watch, but no agent architecture
- Automation plugin (rule-based), but not contextual agents
- No structured out-of-band signal API

**Source References**:
- [Remote Commands Comparison](../../docs/10-domain/remote-commands-comparison.md)
- [Nightscout API Comparison](../../docs/10-domain/nightscout-api-comparison.md)

---

### Trio (formerly FreeAPS X / iAPS)

| Aspect | Current State |
|--------|---------------|
| **Current Layer** | L6 + L7 + Partial L8 |
| **Automation** | oref0-based with SMB, Autosens, dynamic settings |
| **Nightscout Sync** | Full sync via API v1 |
| **Remote Commands** | AES-256-GCM encrypted via APNS |

**L7 Details**:
- Same pattern as Loop (v1 API, POST-based)
- Fetches profiles from Nightscout (`FetchedNightscoutProfile`)
- Uploads devicestatus with oref0-style predictions

**L8 Details**:
| Command | Security | Notes |
|---------|----------|-------|
| Bolus | AES-GCM encrypted | Most secure transport |
| Meal | AES-GCM encrypted | |
| TempTarget | AES-GCM encrypted | |
| Override | AES-GCM encrypted | |
| Cancel TempTarget | AES-GCM encrypted | |
| Cancel Override | AES-GCM encrypted | |

**L8 Advantages**:
- All commands encrypted (best transport security)
- 10-minute timestamp replay protection

**L8 Blockers**:
- Key stored in UserDefaults (not Keychain) - security concern
- No key rotation mechanism
- No forward secrecy
- No granular permissions

**L9 Blockers**:
- Same as Loop - no agent architecture
- No contextual signal integration

**Source References**:
- [Remote Commands Comparison](../../docs/10-domain/remote-commands-comparison.md)
- [Trio Mapping](../trio/README.md)

---

### OpenAPS (oref0)

| Aspect | Current State |
|--------|---------------|
| **Current Layer** | L6 + L7 |
| **Automation** | Original oref0/oref1 algorithms (SMB, Autosens, UAM) |
| **Nightscout Sync** | Full sync |
| **Remote Commands** | Limited (via Nightscout treatments or Pushover) |

**L7 Details**:
- Pioneer of the "narrative bus" concept
- devicestatus format that others adopted
- Full prediction arrays (IOB, COB, UAM, ZT)

**L8 Blockers**:
- Remote control less developed than mobile-first systems
- Typically rig-based (not phone-native)
- Pushover notifications but not structured commands

**L9 Blockers**:
- Shell script architecture, not agent-friendly
- No structured API for out-of-band signals

**Source References**:
- [oref0 Algorithm Mapping](../oref0/algorithm.md)
- [Algorithm Comparison](../../docs/10-domain/algorithm-comparison-deep-dive.md)

---

## Summary Matrix

| System | L6 (AID) | L7 (Network) | L8 (Remote) | L9 (Agents) | Key Blocker |
|--------|----------|--------------|-------------|-------------|-------------|
| **Tandem Control-IQ** | Full | Partial | None | None | Closed ecosystem |
| **Tandem Mobi** | Full | Partial | None | None | Closed ecosystem |
| **Omnipod 5** | Full | Partial | None | None | Closed ecosystem |
| **Omnipod Dash** | None | Partial | None | None | No automation |
| **Loop** | Full | Full | Partial | None | Override OTP gap |
| **AAPS** | Full | Full (v3) | Partial | None | SMS transport, no roles |
| **Trio** | Full | Full | Partial | None | Key storage, no roles |
| **OpenAPS** | Full | Full | Limited | None | Rig-based, no structured remote |

---

## Cross-Cutting Blockers for L8-L9

### L8 (Remote Controls) Common Gaps

| Gap ID | Description | Affected Systems |
|--------|-------------|------------------|
| GAP-DELEGATE-001 | No standardized authorization scoping | All |
| GAP-DELEGATE-002 | No role-based permission model | All |
| GAP-REMOTE-001 | Loop override skips OTP | Loop |
| GAP-AUTH-002 | No authority hierarchy in Nightscout | All |

### L9 (Delegate Agents) Common Gaps

| Gap ID | Description | Affected Systems |
|--------|-------------|------------------|
| GAP-DELEGATE-003 | No structured out-of-band signal API | All |
| GAP-DELEGATE-004 | No agent authorization framework | All |
| GAP-DELEGATE-005 | No propose-authorize-enact pattern | All |

---

## Related Documents

- [Progressive Enhancement Framework](../../docs/10-domain/progressive-enhancement-framework.md) - Layer definitions
- [Remote Commands Comparison](../../docs/10-domain/remote-commands-comparison.md) - Security analysis
- [Nightscout API Comparison](../../docs/10-domain/nightscout-api-comparison.md) - L7 implementation details
- [Requirements](../../traceability/requirements.md) - REQ-DEGRADE-* requirements
- [Gaps](../../traceability/gaps.md) - GAP-DELEGATE-* gaps
