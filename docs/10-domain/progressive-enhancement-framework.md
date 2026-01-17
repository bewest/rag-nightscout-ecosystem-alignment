# Progressive Enhancement Framework for Diabetes Technology

This document defines a capability ladder for diabetes technology, providing a mental model where each layer adds optional capabilities through progressive enhancement while ensuring safe degradation when components fail.

---

## Executive Summary

| Layer | Name | Capabilities | Fallback |
|-------|------|--------------|----------|
| L0 | MDI Baseline | Long-acting + rapid-acting insulin, fingersticks | None (floor) |
| L1 | Structured MDI | Carb counting, schedules, logging | L0 |
| L2 | CGM Sensing | Continuous glucose, trends, alerts | L0/L1 (SMBG) |
| L3 | Pump Therapy | Programmable basal, bolus delivery | L0/L1 (MDI) |
| L4 | Manual Pump+CGM | CGM-informed pump control (human controller) | L3 (basal schedule) |
| L5 | Safety Automation | LGS, predictive suspend, bounded corrections | L4 (manual control) |
| L6 | Full AID | Closed-loop control (Loop/AAPS/Trio) | L5 or L4 |
| L7 | Networked Care | Shared history, remote visibility (Nightscout) | L6 (local therapy continues) |
| L8 | Remote Controls | Scoped delegation to caregivers | L7 (recommendations only) |
| L9 | Delegate Agents | Autonomous agents with out-of-band context | L8 (human delegation) |

---

## Core Design Principles

### Progressive Enhancement

Add capabilities in layers; each layer consumes and produces well-defined state and events. Higher layers build on lower layers without requiring them for basic operation.

**Key insight**: Each layer should be independently valuable. A person can benefit from CGM (L2) without a pump (L3), or use a pump (L3) without automation (L5+).

### Graceful Degradation

Every layer has an explicit fallback mode and a "minimum safe operation." When a capability is lost (sensor failure, pump occlusion, connectivity loss, automation paused), care degrades safely and intelligibly to the next-lower layer.

**Key insight**: The system should never leave a person unable to manage their diabetes. The fallback floor (L0) is always available.

### Separation of Concerns

Distinguish three fundamental domains:

| Domain | Definition | Examples |
|--------|------------|----------|
| **Therapy Intent** | What we want to achieve | Target glucose, correction factor, insulin sensitivity |
| **Delivery** | What actually happened | Delivered insulin, actual basal rate, bolus completion |
| **Evidence** | What we observe | CGM readings, meals logged, activity detected |

This separation enables better debugging, audit, and reasoning about system behavior.

### Explainability via Traceability

Every decision can point to the inputs and rules that produced it (human- or machine-made). This supports:
- Retrospective analysis ("why did it do that?")
- Trust building ("can I rely on this?")
- Regulatory compliance ("prove it's safe")
- Machine learning ("what correlates with outcomes?")

### Delegation & Stewardship

Later layers may act on the person's behalf, but only with:
- Scoped authorization (what actions are permitted)
- Audit trails (who did what, when, and why)
- Revocation (ability to withdraw delegation)
- Bounded autonomy (limits on what can be enacted without confirmation)

---

## Layer Definitions

### Layer 0: Human-Only MDI Baseline (Minimum Viable Therapy)

**What it is**: Long-acting + rapid-acting insulin with fingersticks and/or symptoms.

**Inputs**:
- SMBG (fingerstick), symptoms
- Meals, planned activity
- Illness, stress, sleep

**Core control loop**:
- Human sets basal background (long insulin dose)
- Human executes bolus events (meal correction, correction dose)

**What works even if everything else fails**:
- The person can still dose safely using a plan, rules of thumb, and safety checks

**Graceful degradation target**:
- This is the floor: every higher layer must be able to fall back to "MDI + plan"

---

### Layer 1: Structured MDI

**What it adds**: Better structure, fewer surprises, more repeatability.

**Enhancements**:
- Carb counting, correction factors, insulin action time assumptions
- Schedules for patterns (wake/bed, workdays, weekends)
- Event logging (meals, doses, exercise, illness)

**Outputs**:
- A coherent therapy plan (even if implemented manually)

**Degrades to**: Layer 0 (still workable even if the logs/apps vanish)

---

### Layer 2: CGM Sensing (Observability Layer)

**What it adds**: Continuous glucose signal and trend context.

**Enhancements**:
- Trend arrows, alerts, time-in-range perspective
- Early warning for lows/highs
- Better evidence for decisions (especially overnight)

**Critical safety note**: CGM is an estimate; the layer must retain confirm-by-BG pathways for ambiguity.

**Relevant specifications**:
- [`aid-entries-2025.yaml`](../../specs/openapi/aid-entries-2025.yaml) - SGV, direction, noise
- [Dexcom BLE Protocol Deep Dive](dexcom-ble-protocol-deep-dive.md)
- [G7 Protocol Specification](g7-protocol-specification.md)

**Graceful degradation**: If CGM is unavailable/unreliable → revert to SMBG and/or symptom-based checks (L0/L1)

---

### Layer 3: Pump Therapy (Actuation Layer)

**What it adds**: Replace long insulin with programmable basal delivery + boluses.

**Enhancements**:
- Adjustable basal schedules
- Temp basals, extended boluses
- Finer dosing resolution

**Key interface concepts**:

The pump exposes three state dimensions:

| Dimension | Description |
|-----------|-------------|
| **Desired delivery** | What we asked for (temp basal rate, bolus amount) |
| **Observed delivery** | What actually happened (confirmed doses, reservoir delta) |
| **Constraints** | What limits apply (max basal, max bolus, reservoir level, occlusion, battery) |

**Relevant specifications**:
- [Pump Communication Deep Dive](pump-communication-deep-dive.md)
- [Pump Protocols Specification](../../specs/pump-protocols-spec.md)

**Graceful degradation**:
- Pump failure → transition to MDI plan (L0/L1)
- CGM failure while pumping → pump + SMBG (manual loop)

---

### Layer 4: CGM-Informed Manual Control

**What it is**: Pump + CGM, but the person (or caregiver) is still the controller.

**Enhancements**:
- Better "when to act" decisions using trends
- More precise corrections and prevention actions
- Safer overnight management through alerts + planned responses

**Graceful degradation**:
- Lose CGM → pump continues on basal schedule; user returns to SMBG-guided corrections
- Lose pump → MDI fallback plan

---

### Layer 5: Safety Automation Primitives

This is where automation begins without full closed loop.

**Enhancements**:
- Low-glucose suspend (LGS) / predictive suspend
- Auto-corrections with strict bounds
- Automated basal modulation within safe envelopes

**Design principles**:
- Automation must be **bounded** (hard limits)
- Automation must be **explainable** (why did it act?)
- Automation must be **interruptible** (user can override)

**Graceful degradation**:
- Automation off → return to L4 (manual pump+CGM)
- CGM off → automation must auto-disable; return to basal schedule + SMBG

---

### Layer 6: Full AID (Loop / OpenAPS / Trio / AAPS)

**What it adds**: Continuous controller that tunes basal and sometimes bolus/corrections to meet goals.

**The Three-State Model**:

| State | Contents |
|-------|----------|
| **Desired** | Targets, sensitivity, ratios, constraints, overrides, temporary intents |
| **Observed** | Delivered insulin, sensor readings, IOB, COB, device health |
| **Capabilities** | What's possible now (CGM quality, pump type, comms, max rates, automation mode) |

**The Schedule Composition Model**:

Automation composes schedules and overrides:
- Basal schedule + temp basal/SMB
- Target schedule + temporary targets/overrides
- Sensitivity schedule + contextual modifiers
- Carb ratio schedule + meal strategies
- Safety limits + guardrails

**Relevant specifications**:
- [`aid-devicestatus-2025.yaml`](../../specs/openapi/aid-devicestatus-2025.yaml) - Loop vs oref0 structure
- [`aid-profile-2025.yaml`](../../specs/openapi/aid-profile-2025.yaml) - Therapy settings
- [Algorithm Comparison Deep Dive](algorithm-comparison-deep-dive.md)

**Graceful degradation**:

If any prerequisite fails (CGM, pump comms, clock drift, data stale), the loop:
1. Reduces to a safer subset (e.g., suspend-only)
2. Or disables automation and returns to L4/L3
3. With clear operator guidance and a logged reason

---

### Layer 7: Networked Care (Nightscout as "Narrative Bus")

**What it adds**: Shared, durable history and remote visibility across humans and devices.

**Enhancements**:
- Event stream: glucose, insulin, carbs, overrides, alarms, device status
- Multi-stakeholder viewing: patient, caregiver, clinician, research
- Cross-device continuity (switch phones, swap pumps, travel)

**Progressive enhancement role**:
- Nightscout becomes a portable audit trail + integration hub, not the single point of failure

**Relevant specifications**:
- [`aid-treatments-2025.yaml`](../../specs/openapi/aid-treatments-2025.yaml)
- [Nightscout API Comparison](nightscout-api-comparison.md)
- [AID Controller Sync Patterns](../../mapping/cross-project/aid-controller-sync-patterns.md)

**Graceful degradation**:
- Connectivity loss → local therapy continues; data queues and syncs later
- Remote systems down → local loop/manual still works

---

### Layer 8: Remote Controls and Delegated Authority

**What it adds**: Authorized people can assist safely without physically holding the device.

**Capabilities**:
- Scoped remote actions (suggest vs enact)
- Role-based permissions (parent, partner, clinician, coach)
- Emergency pathways (temporary takeover, time-limited control)

**Safety requirements**:
- Explicit consent + revocation
- Clear boundaries (what they can/can't do)
- Tamper-evident logs ("who did what, when, and why")

**Relevant specifications**:
- [Remote Commands Cross-System Comparison](remote-commands-comparison.md)
- [LoopCaregiver Remote Commands](../../mapping/loopcaregiver/remote-commands.md)
- [LoopFollow Remote Commands](../../mapping/loopfollow/remote-commands.md)

**Graceful degradation**:
- If remote control unavailable → local control remains
- Recommendations can be communicated out-of-band (phone call, text)

---

### Layer 9: Delegate Agents with Out-of-Band Context

This is the agents layer: software delegates can use additional signals to reduce burden and improve outcomes.

**What agents do (in a safe architecture)**:

Agents should primarily operate by:
1. **Proposing intents** (temporary targets, meal timing suggestions, carb recommendations, override selection)
2. **Requesting authorization** for sensitive actions (bolus enactment, aggressive overrides)
3. **Documenting rationale** using the shared narrative (Nightscout/event log)

**Out-of-band signals (examples)**:

| Signal Type | Sources | Use Cases |
|-------------|---------|-----------|
| **Exercise** | Calendar plans, wearables (HR/steps), GPS, training load | Pre-exercise target, post-exercise sensitivity |
| **Menstrual cycle** | Cycle tracking, phase prediction, user annotations | Hormone-phase sensitivity adjustments |
| **Illness/stress** | Sleep disruption, HRV changes, self-reported symptoms | Sick-day rules, conservative targets |
| **Meals** | Photo recognition, routine detection, restaurant menus | Meal announcement, carb estimation |
| **Sleep** | Sleep tracking, circadian rhythm detection | Overnight target adjustment |

**Progressive enhancement pattern**:

1. **Advisory-only** mode: Agent suggests overrides, human decides
2. **Confirm-to-enact** mode: Human taps "approve" for each action
3. **Bounded autonomy**: Agent can enact within strict limits + rapid rollback
4. **Multi-agent collaboration**: Exercise agent + meal agent + safety agent, with conflict resolution

**Graceful degradation requirements**:
- If context signals disappear → agent falls back to CGM-only reasoning or disables itself
- If confidence drops → revert to "suggest only"
- If data is stale → do nothing, ask for confirmation, or hand off to human

---

## Shared Vocabulary

Any product/project can be described using these questions:

| Aspect | Question |
|--------|----------|
| **Sensing** | What evidence does it rely on (CGM, SMBG, wearables), and how does it detect bad data? |
| **Actuation** | What can it change (basal, bolus, targets), and what are the hard limits? |
| **Policy** | What rules/schedules/overrides define intent? |
| **State** | Desired vs observed vs capabilities—how are they represented and reconciled? |
| **Delegation** | Who/what can act, with what permissions, and how is it audited? |
| **Degradation** | What happens when components fail—what's the safe fallback? |

---

## Relationship to AID Alignment Workspace

This framework provides a conceptual foundation for the AID Alignment Workspace:

| Framework Concept | Workspace Artifact |
|-------------------|-------------------|
| L2-L3 state separation | OpenAPI specs for entries, treatments, devicestatus |
| L6 three-state model | Profile desired/observed split proposal |
| L7 narrative bus | Nightscout sync patterns, API comparison |
| L8 delegation | Remote commands documentation, authorization gaps |
| L9 agent patterns | Future: agent authorization proposals |

---

## Where This Points Next

**Today**: L6–L7 systems (Loop/OpenAPS/Trio + Nightscout) already embody progressive enhancement if we describe them as state + events + capabilities rather than monoliths.

**Near-future**: L8–L9 makes the "care team" real: humans and agents cooperating, with Nightscout-like event trails and scoped authority.

**North star**: A person-centered "therapy OS" where automation is optional, controls are shareable, and everything degrades gracefully back to safe manual care.

---

## Related Documents

- [Data Rights Primer](data-rights-primer.md) - Plain-language guide to the Five Fundamental Diabetes Data Rights
- [Digital Rights and Legal Protections](../DIGITAL-RIGHTS.md) - Legal frameworks (GPL, DMCA, interoperability)
- [Capability Layer Matrix](../../mapping/cross-project/capability-layer-matrix.md) - System-by-system mapping
- [Requirements](../../traceability/requirements.md) - REQ-DEGRADE-* requirements
- [Gaps](../../traceability/gaps.md) - GAP-DELEGATE-* gaps
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md) - Capability Layer Models section
