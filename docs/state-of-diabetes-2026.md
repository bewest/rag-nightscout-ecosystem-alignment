# State of Diabetes: 2026 Edition

**A framework for understanding where we are, where we're going, and what we must do to get there.**

---

## Executive Summary

Diabetes technology has reached an inflection point. Commercial closed-loop systems deliver unprecedented automation. Open-source projects have proven that patient-driven innovation works. Yet the next frontier—safe delegation to caregivers and intelligent agents—remains blocked by fragmented ecosystems, missing standards, and underdeveloped rights frameworks.

This document presents a unified view of the diabetes technology landscape in 2026: a progressive enhancement framework for thinking about capabilities, an honest assessment of where commercial and open-source systems stand today, a vision for where open source is taking us, and a tangible challenge for everyone who wants to accelerate progress.

---

## Part I: The Progressive Enhancement Framework

### A Ladder, Not a Leap

Diabetes technology is not a single thing. It's a stack of capabilities, each layer building on the one below. We call this the **Progressive Enhancement Framework**—a 10-layer model that describes what's possible, what's practical, and what's safe.

| Layer | Name | What It Adds |
|-------|------|--------------|
| **L0** | MDI Baseline | Long-acting + rapid-acting insulin, fingersticks. The floor. |
| **L1** | Structured MDI | Carb counting, schedules, logging. Better decisions. |
| **L2** | CGM Sensing | Continuous glucose, trends, alerts. Seeing the invisible. |
| **L3** | Pump Therapy | Programmable basal, precise boluses. Finer control. |
| **L4** | Manual Pump+CGM | Human as controller, informed by trends. |
| **L5** | Safety Automation | Low-glucose suspend, bounded corrections. First automation. |
| **L6** | Full AID | Closed-loop control (Loop, AAPS, Trio, Control-IQ). The algorithm drives. |
| **L7** | Networked Care | Shared history, remote visibility. Nightscout as the "narrative bus." |
| **L8** | Remote Controls | Caregivers can act at a distance—safely, with consent. |
| **L9** | Delegate Agents | Autonomous software that integrates exercise, sleep, stress, hormones. |

### Three Core Principles

**Progressive Enhancement**: Each layer should be independently valuable. You can benefit from CGM (L2) without a pump (L3). You can use a pump (L3) without automation (L5+). Higher layers are optional improvements, not requirements.

**Graceful Degradation**: When something fails—sensor dies, pump occludes, connectivity drops—the system degrades safely to the next-lower layer. The floor (L0) is always available. No one should ever be left unable to manage their diabetes.

**Explainability via Traceability**: Every decision can point to the inputs and rules that produced it. This enables debugging ("why did it do that?"), trust ("can I rely on this?"), and accountability ("who did what, and when?").

---

## Part II: Where We Are Today

### Commercial Systems: Strong at L6, Walled at L7+

Commercial automated insulin delivery systems—Tandem Control-IQ, Omnipod 5, Medtronic 780G—have brought closed-loop technology to the mainstream. They reliably achieve L6: full automation with safety guardrails.

But commercial systems hit a wall at L7 and beyond:

- **Partial L7**: Cloud reports exist, but there's no real-time insulin narrative for caregivers. You can see glucose via Dexcom Follow, but not the algorithm's decisions.
- **No L8**: No manufacturer offers audited, caregiver-grade remote commands for insulin actions. Parents can't safely deliver a correction bolus to their child at school.
- **No L9**: Closed ecosystems block third-party agents. No API exists for integrating exercise plans, menstrual cycles, or sleep data into dosing decisions.

The commercial path forward is unclear. Regulatory caution, liability concerns, and competitive moats make L8–L9 capabilities unlikely without external pressure.

### Open-Source Systems: Full L6–L7, Partial L8, Zero L9

Open-source projects—Loop, AAPS, Trio, OpenAPS—have charted a different course. Built by the #WeAreNotWaiting community, these systems deliver capabilities commercial products cannot or will not offer.

**Where open source excels:**

- **Full L6**: Mature closed-loop algorithms (oref0, Loop's retrospective correction, AAPS's SMB/Autosens) with years of real-world validation.
- **Full L7**: Nightscout as the narrative bus—a shared, portable audit trail of glucose, insulin, carbs, overrides, and device status. Multi-stakeholder visibility that works across devices, phones, and care teams.
- **Partial L8**: Remote commands exist (LoopCaregiver, AAPS SMS, Trio's encrypted push), but with gaps:
  - Loop's override commands skip OTP validation (security gap)
  - No role-based permissions (parent vs. clinician vs. agent)
  - No authority hierarchy or delegation framework
  - Key rotation mechanisms missing or incomplete

**Where open source hasn't arrived yet:**

- **Zero L9**: No system has a structured agent architecture. No API exists for out-of-band signals (exercise, hormones, stress). Manual override selection only.

### The Gap Analysis: 91+ Blockers Across 14 Categories

We've documented **91+ gaps** blocking ecosystem progress, spanning:

| Category | Example Blockers |
|----------|------------------|
| Treatment Sync | Duplicates on reconnect, no upsert semantics |
| CGM Data | Calibration algorithm not tracked, no source attribution |
| Remote Commands | Override OTP bypass, no key rotation, no role scoping |
| Authorization | No authority hierarchy, enteredBy unverified |
| Algorithm Opacity | Effect timelines not uploaded, insulin models not synced |

**The core tension**: Nightscout maintainers prioritize infrastructure (MongoDB updates, testing, security). Downstream app developers need semantic features (sync identity, override tracking, delegation). Neither can fully proceed without coordination.

### The Capability Matrix: A Comparative View

| System | L6 (AID) | L7 (Network) | L8 (Remote) | L9 (Agents) | Key Blocker |
|--------|----------|--------------|-------------|-------------|-------------|
| Tandem Control-IQ | Full | Partial | None | None | Closed ecosystem |
| Omnipod 5 | Full | Partial | None | None | Closed ecosystem |
| Loop | Full | Full | Partial | None | Override security gap |
| AAPS | Full | Full (v3) | Partial | None | SMS transport, no roles |
| Trio | Full | Full | Partial | None | Key storage, no rotation |
| OpenAPS | Full | Full | Limited | None | Rig-based, no structured remote |

The pattern is clear: open-source systems lead on L7 (networked care) and are pushing into L8 (remote controls). But L8 security is incomplete, and L9 remains unexplored territory.

---

## Part III: The Five Fundamental Data Rights

Before we can delegate care—to parents, partners, clinicians, or agents—we need a clear framework for data rights. Not "who owns the data?" but **"who can do what, under what rules, with accountability?"**

### 1. The Right to Access
**"I can see my data."** In real time. Without vendor gatekeeping. Glucose, insulin, carbs, alerts, device status—visible when I need it.

### 2. The Right to Export
**"I can get my data out."** In machine-readable formats. Portable across platforms. My history follows me, not my device subscription.

### 3. The Right to Share
**"I can let others see it."** Family, caregivers, clinicians, researchers—on my terms, revocable when circumstances change.

### 4. The Right to Delegate
**"I can let someone act on my behalf."** A parent sends a correction. A nurse adjusts settings. An agent suggests a pre-exercise target. With scoped permissions, audit trails, and the ability to revoke.

### 5. The Right to Audit
**"I can see who did what, and when."** Every action logged. Tamper-evident. Accessible to the person whose health is at stake.

**The critical gap**: The Right to Delegate is the least developed—in law, in technology, and in practice. Current frameworks protect data access but not delegated action. As remote control and agent-based features become central to safe automated insulin delivery, we need frameworks that clearly define: Who can act? On what? Under what rules? With what accountability?

---

## Part IV: Where We're Going Thanks to Open Source

### The Near Future: Completing L8

The next 12–24 months should see open-source systems close the L8 gaps:

- **OTP for all remote commands**: Overrides, temporary targets, and other safety-critical commands should require the same authentication as boluses.
- **Role-based permissions**: Distinguish between what a parent can do, what a clinician can advise, and what an agent can propose.
- **Key rotation and forward secrecy**: Secrets should rotate automatically. Compromise of today's key shouldn't unlock yesterday's commands.
- **Authority hierarchy**: Nightscout should know the difference between "patient enacted," "caregiver delegated," and "agent suggested."

These aren't theoretical—they're documented proposals awaiting implementation.

### The Horizon: Layer 9 and Delegate Agents

Layer 9 is the frontier: software agents that reduce burden by integrating signals the algorithm can't see.

**What agents could do:**
- Propose a pre-exercise temporary target based on your calendar and workout history
- Suggest a sensitivity adjustment during the luteal phase of your menstrual cycle
- Recommend conservative targets when sleep data indicates illness or stress
- Estimate carb content from a photo before you even enter the meal

**How agents should work:**
1. **Propose**: Suggest an intent (override, target, meal announcement)
2. **Request authorization**: For sensitive actions, ask before acting
3. **Document rationale**: Log the inputs and reasoning to the shared narrative

**Graceful degradation requirements:**
- If context signals disappear → agent falls back to CGM-only reasoning or disables itself
- If confidence drops → revert to "suggest only" mode
- If data is stale → do nothing, hand off to human

The architecture for L9 doesn't exist yet. No system has a structured out-of-band signal API. No agent authorization framework. No propose-authorize-enact pattern. But the path is clear, and open source will build it.

### The North Star: A Person-Centered Therapy OS

The ultimate vision is a "therapy OS" where:
- **Automation is optional**—each layer is independently valuable
- **Controls are shareable**—delegation is safe, scoped, and auditable
- **Everything degrades gracefully**—back to safe manual care when needed
- **Data rights are respected**—access, export, share, delegate, and audit

This isn't a single product. It's an ecosystem of interoperable components, connected by shared standards, built on open-source foundations.

---

## Part V: The Challenge

We've mapped the terrain. We know where we are and where we need to go. Now we need action.

### For Developers

**Pick a gap. Close it.**

The highest-leverage contributions right now:

1. **Swift SDK for Nightscout API v3** *(GAP-API-003)*: Loop and Trio are stuck on v1. A production-quality v3 client unblocks incremental sync, soft delete detection, and proper deduplication for the entire iOS ecosystem.

2. **Standardize sync identity** *(GAP-003)*: Every controller should emit a `syncIdentifier` that survives round-trips through Nightscout. This is a convention change with massive downstream impact.

3. **OTP for override commands** *(GAP-REMOTE-001)*: The security gap in Loop's remote commands is documented. The fix is scoped. Ship it.

4. **Add override supersession fields** *(GAP-001, GAP-SYNC-004)*: When one override ends because another started, track it. This single schema addition unblocks accurate retrospective analysis across all systems.

5. **Document the agent control plane** *(GAP-DELEGATE-003, GAP-DELEGATE-004)*: Even if implementation is years away, a well-specified API for out-of-band signals and propose-authorize-enact patterns will shape the conversation.

### For Clinicians

**Support patient-controlled tools.**

Nightscout isn't a competitor to your clinical systems—it's a window into patient life between visits. When patients share their data openly, you can provide better guidance. Ask about the whole picture: wearables, sleep, stress, activity. These signals inform care even if your EHR doesn't capture them.

**Advocate for the Right to Delegate.** Remote commands and agent-based care are coming. Help define what safe delegation looks like in clinical practice.

### For People with Diabetes and Caregivers

**Use tools that respect your data rights.** Choose platforms that let you access, export, share, and control your data. Ask vendors: Can I get my data out? Can I share it with my care team? Can I revoke access?

**Advocate for interoperability.** When you talk to manufacturers, insurers, and policymakers, make clear: data lock-in is a safety issue. Portability and delegation aren't nice-to-haves—they're essential.

### For Policymakers

**Recognize that data is care.** In diabetes technology, real-time data enables life-saving decisions. The Five Fundamental Data Rights—Access, Export, Share, Delegate, and Audit—aren't abstract privacy concepts. They're safety, autonomy, and quality-of-life issues.

**Protect the Right to Delegate.** Existing frameworks cover data access but not delegated action. As remote control and agent-based systems become central to safe care, we need legal clarity on: Who can act? Under what authorization? With what accountability?

**Support interoperability mandates.** Prevent vendors from trapping patient data in proprietary silos. Require standard export and sharing mechanisms. Make it illegal to lock patients out of their own health data.

---

## Conclusion: The Work Ahead

In 2026, diabetes technology is better than it's ever been. Closed-loop systems work. Open-source projects have proven that patient-driven innovation is not only possible but essential. The community has mapped the gaps, documented the requirements, and proposed the solutions.

But we're not done. Layer 8 security is incomplete. Layer 9 doesn't exist. Data rights—especially the Right to Delegate—lack legal and technical infrastructure. The ecosystem remains fragmented.

The next chapter isn't written by any single company or project. It's written by everyone who contributes: developers closing gaps, clinicians embracing patient-controlled tools, people with diabetes advocating for their rights, and policymakers creating frameworks that enable safe, interoperable, person-centered care.

The foundation is built. The path is clear.

**Now we build the rest.**

---

## Related Documents

- [Progressive Enhancement Framework](10-domain/progressive-enhancement-framework.md) — Full 10-layer specification
- [Data Rights Primer](10-domain/data-rights-primer.md) — Plain-language guide to the Five Fundamental Rights
- [Digital Rights and Legal Protections](DIGITAL-RIGHTS.md) — Legal frameworks (GPL, DMCA, interoperability)
- [Stakeholder Priority Analysis](60-research/stakeholder-priority-analysis.md) — Gap impact and coordination strategy
- [Capability Layer Matrix](../mapping/cross-project/capability-layer-matrix.md) — System-by-system comparison
- [Remote Commands Comparison](10-domain/remote-commands-comparison.md) — L8 security analysis across systems

---

*State of Diabetes: 2026 Edition*  
*Published: January 2026*  
*#WeAreNotWaiting*
