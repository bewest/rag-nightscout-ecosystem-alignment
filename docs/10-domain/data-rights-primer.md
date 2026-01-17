# Data Rights Primer for Diabetes Technology

**Status:** Living Document  
**Last Updated:** January 2026  
**Purpose:** A plain-language guide to data rights in diabetes care for patients, caregivers, clinicians, developers, and policymakers

---

## Overview

This document provides an accessible introduction to data rights in the context of diabetes technology. It complements the [Digital Rights and Legal Protections](../DIGITAL-RIGHTS.md) document (which covers legal frameworks) and the [Progressive Enhancement Framework](progressive-enhancement-framework.md) (which covers technical architecture).

Modern diabetes care is increasingly data-driven. Continuous glucose monitors generate readings every few minutes. Insulin pumps log every dose. Automated systems make decisions based on patterns, predictions, and real-time signals. This data doesn't just describe care—it *drives* care.

If data drives care, then people with diabetes must have clear rights to control, share, and act on their data.

---

## The Core Insight: From Ownership to Agency

Traditional discussions ask: *"Who owns the data?"*

A more useful question is: *"Who is allowed to do what with the data—and under what rules?"*

This shift from **ownership** to **agency** matters because diabetes care is often:

- **Shared** — involving parents, partners, clinicians, caregivers, and sometimes AI tools
- **Time-critical** — where delays in data access can have health consequences
- **Increasingly automated** — where software agents act on data in real time

The goal isn't just to possess your data. It's to have meaningful control over how it's used, who can see it, and who can act on your behalf.

---

## The Five Fundamental Diabetes Data Rights

These rights build on each other. Missing one weakens the rest.

### 1. The Right to Access

**"I can see my data."**

- Glucose readings, insulin doses, carbohydrate entries, alerts, device status
- In real time, not weeks later
- Without needing special permission from a vendor

**Why it matters:** You cannot manage or understand what you cannot see. Real-time access enables informed decisions, whether made by you, a caregiver, or an automated system.

**How open source helps:** Projects like Nightscout exist precisely because this right was not being met by commercial systems. They enable people to see their own data on their own terms.

**Related framework concepts:** [L2: CGM Sensing](progressive-enhancement-framework.md#layer-2-cgm-sensing-observability-layer), [L7: Networked Care](progressive-enhancement-framework.md#layer-7-networked-care-nightscout-as-narrative-bus)

---

### 2. The Right to Export

**"I can get my data out."**

- Downloadable in standard formats
- Machine-readable (not just PDFs or screenshots)
- Not locked into one app or ecosystem

**Why it matters:** Diabetes is lifelong. Tools change. Devices are replaced. Insurance changes. Your history must follow you, not disappear when you switch platforms.

**How open source helps:** Open-source tools typically use open formats and provide full export capabilities. Community-defined data standards (like those documented in this workspace) enable portability across systems.

**Related framework concepts:** [L7: Networked Care](progressive-enhancement-framework.md#layer-7-networked-care-nightscout-as-narrative-bus) — Nightscout as a portable audit trail

---

### 3. The Right to Share

**"I can let others see it."**

- Share with family, caregivers, clinicians, coaches, or researchers
- On your terms, with the scope you choose
- Revocable when circumstances change

**Why it matters:** Diabetes management is rarely solo. Parents monitor children. Partners help overnight. Clinicians review patterns. Coaches guide athletic goals. The ability to share appropriately enables collaborative care.

**How open source helps:** Open platforms like Nightscout allow flexible sharing—with specific people, with clinics, or publicly (for advocacy or research). You control the audience.

**Related framework concepts:** [L7: Networked Care](progressive-enhancement-framework.md#layer-7-networked-care-nightscout-as-narrative-bus) — multi-stakeholder viewing

---

### 4. The Right to Delegate

**"I can let someone take actions on my behalf."**

- A parent sends a correction bolus to their child at school
- A nurse adjusts settings for a patient in memory care
- An AI agent suggests a temporary target before exercise

Delegation goes beyond viewing. It means authorizing others (human or machine) to **act**, within defined boundaries and with clear accountability.

**Why it matters:** As care becomes more connected and more automated, the question isn't just "who can see?" but "who can do?" Safe delegation requires explicit consent, clear boundaries, and the ability to revoke.

**How open source helps:** Projects like LoopCaregiver and LoopFollow implement remote control features with logging and accountability. The [Controller Registration Protocol](../60-research/controller-registration-protocol-proposal.md) proposal defines how delegation can be formalized.

**Related framework concepts:** [L8: Remote Controls](progressive-enhancement-framework.md#layer-8-remote-controls-and-delegated-authority), [L9: Delegate Agents](progressive-enhancement-framework.md#layer-9-delegate-agents-with-out-of-band-context)

---

### 5. The Right to Audit

**"I can see who did what, and when."**

- Every action is logged
- Logs are accessible to the person whose health is affected
- Logs are tamper-evident and persistent

**Why it matters:** Without audit trails, there is no accountability. You can't troubleshoot a bad outcome, verify that a caregiver acted appropriately, or debug an automated decision. Audit enables trust.

**How open source helps:** Open-source systems expose their logs. Nightscout maintains a complete event history. The Progressive Enhancement Framework requires "explainability via traceability" at every layer.

**Related framework concepts:** [Core Design Principles: Explainability via Traceability](progressive-enhancement-framework.md#explainability-via-traceability)

---

## Data Beyond the Device

Agent-based insulin delivery (Layer 9 in the Progressive Enhancement Framework) requires access to data beyond traditional health signals:

| Signal Type | Examples | Why It Matters |
|-------------|----------|----------------|
| **Activity** | Steps, heart rate, workout type | Exercise affects insulin sensitivity |
| **Calendar** | Meetings, travel, meals planned | Context for timing and targets |
| **Sleep** | Sleep tracking, circadian patterns | Overnight management |
| **Environment** | Weather, altitude, time zone | Affects physiology and routines |
| **Behavior** | Meal patterns, stress indicators | Predictive adjustments |

These signals are not captured in clinical records or regulated by traditional health data frameworks. Yet without access, automated systems are blind to key variables influencing insulin need.

**Implication:** If we want agent-based care to be safe and effective, patients must have explicit rights to access, route, and delegate control over these additional data streams.

---

## What Different People Can Do

### For People with Diabetes and Caregivers

- **Use tools that respect your rights** — Choose platforms that let you access, export, share, and control your data
- **Understand what you're consenting to** — When you connect a device or service, know what data flows where
- **Advocate for yourself** — Ask vendors: "Can I export my data? Can I share it with others? Can I revoke access?"

### For Clinicians and Care Teams

- **Support patient-controlled tools** — Nightscout and similar platforms can extend your visibility into patient life between visits
- **Encourage data sharing** — When patients share openly, you can provide better guidance
- **Ask about the whole picture** — Data from wearables, calendars, and daily life can inform care

### For Developers and Designers

- **Build for portability** — Use open formats, standard APIs, and clear export features
- **Design for delegation** — Implement scoped permissions, revocation, and audit logging
- **Follow community lead** — Open-source diabetes projects have decades of experience with these patterns

### For Policymakers and Advocates

- **Promote a "Right to Delegate"** — Existing frameworks often cover data access but not delegated action
- **Ensure interoperability** — Require that health data systems support standard export and sharing
- **Protect against lock-in** — Prevent vendors from trapping patient data in proprietary silos

---

## Relationship to Legal Frameworks

The [Digital Rights and Legal Protections](../DIGITAL-RIGHTS.md) document covers the legal mechanisms that protect these rights:

| Data Right | Legal Mechanisms |
|------------|------------------|
| **Access** | GDPR data subject access, state privacy laws |
| **Export** | GDPR data portability, interoperability mandates |
| **Share** | User-controlled consent, privacy preferences |
| **Delegate** | Emerging frameworks (not fully addressed in current law) |
| **Audit** | Audit log requirements, transparency obligations |

**Note:** The Right to Delegate is the least developed in current legal frameworks. As remote control and agent-based features become central to safe automated insulin delivery, we need frameworks that clearly define and enforce: Who can see what? Who can act on what? Under what rules or revocable permissions?

---

## Relationship to Progressive Enhancement Framework

The [Progressive Enhancement Framework](progressive-enhancement-framework.md) provides the technical architecture where these rights are exercised:

| Data Right | Framework Layers |
|------------|------------------|
| **Access** | L2 (CGM Sensing), L7 (Networked Care) |
| **Export** | L7 (Nightscout as portable history) |
| **Share** | L7 (multi-stakeholder viewing) |
| **Delegate** | L8 (Remote Controls), L9 (Delegate Agents) |
| **Audit** | All layers (Explainability via Traceability) |

The Progressive Enhancement Framework ensures that every layer has an explicit fallback. Data rights complement this: even when delegation fails or is revoked, the person retains access to their own data and can fall back to direct control.

---

## Summary: Data Rights Are Care Rights

In diabetes technology, **data is not just information — data is care**.

- Real-time glucose data enables life-saving decisions
- Insulin delivery history enables troubleshooting and optimization
- Shared visibility enables collaborative care teams
- Delegated action enables caregivers and agents to help safely
- Audit trails enable trust and accountability

The five fundamental data rights — **Access, Export, Share, Delegate, and Audit** — are not abstract privacy concepts. They are safety, autonomy, and quality-of-life issues.

Open-source diabetes tools like Nightscout, Loop, OpenAPS, and the systems documented in this workspace exist because these rights were not being met. They demonstrate that patient-centered data rights are not only possible but essential.

---

## Related Documents

- [Digital Rights and Legal Protections](../DIGITAL-RIGHTS.md) — Legal frameworks (GPL, DMCA, interoperability)
- [Progressive Enhancement Framework](progressive-enhancement-framework.md) — 10-layer capability model
- [Authority Model](authority-model.md) — Delegation and authorization patterns
- [Controller Registration Protocol Proposal](../60-research/controller-registration-protocol-proposal.md) — Formalizing controller delegation
- [Remote Commands Comparison](remote-commands-comparison.md) — Cross-system remote control features
