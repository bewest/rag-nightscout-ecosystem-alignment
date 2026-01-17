# Proposal: Profile Model Evolution

**Status:** Draft  
**Author:** Agent  
**Date:** 2026-01-17  
**Related:** [GAP-002](../../traceability/gaps.md#gap-002-aaps-profileswitch-vs-override-semantic-mismatch), [Profile Comparison](profile-therapy-settings-comparison.md), [Controller Registration Proposal](controller-registration-protocol-proposal.md)

---

## Executive Summary

This proposal addresses limitations in Nightscout's current profile model through incremental schema improvements that **do not require** full controller registration. The key concepts are:

1. **Desired vs Observed Split** — Separate prescribed therapy settings from what's actually in effect
2. **Capability Tracking** — Document what a controller can do without requiring verified identity
3. **Templates/Presets** — Enable reusable therapy configurations that can be referenced by name

These improvements are **orthogonal** to controller registration—they improve data semantics regardless of whether identity verification is implemented.

---

## Problem Statement

### Current Profile Model Limitations

Nightscout's `profile` collection treats therapy settings as a monolithic document:

```json
{
  "defaultProfile": "Default",
  "store": {
    "Default": {
      "dia": 5,
      "basal": [...],
      "sens": [...],
      "carbratio": [...],
      "target_low": [...],
      "target_high": [...]
    }
  }
}
```

This model conflates several distinct concepts:

| Concept | Description | Current Status |
|---------|-------------|----------------|
| **Prescribed** | What the endocrinologist configured | Not distinguished |
| **Desired** | What the user intends (may include personal adjustments) | Assumed = profile |
| **Effective** | What's currently active (with modifiers) | Lost after event |
| **Observed** | What was actually delivered | Scattered in treatments |

### Semantic Loss Examples

**Example 1: AAPS Percentage Adjustment**

User runs at 110% insulin for exercise recovery:

```json
// What AAPS knows:
{
  "baseProfile": "Day Profile",
  "percentage": 110,
  "timeshift": 0,
  "duration": 7200000
}

// What Nightscout stores:
{
  "eventType": "Profile Switch",
  "profile": "Day Profile (+10%)",  // Semantic intent lost
  "notes": ""
}
```

**Nightscout cannot distinguish:**
- Complete profile switch to a new profile
- Temporary percentage adjustment
- Time-shifted schedule

> **GAP-002 Resolution:** This is the core issue documented in [GAP-002](../../traceability/gaps.md#gap-002-aaps-profileswitch-vs-override-semantic-mismatch). The proposed `intent` and `modifiers` fields directly implement GAP-002's "hybrid schema" option—accepting ProfileSwitch as a valid representation while adding semantic fields to distinguish the three scenarios above.

**Example 2: Override vs Profile Modification**

Loop user activates "Exercise" override (ISF -20%, CR unchanged):

```json
// What Loop knows:
{
  "overrideName": "Exercise",
  "targetRange": { "min": 140, "max": 160 },
  "insulinSensitivityScaling": 0.8,  // -20%
  "duration": 3600
}

// What Nightscout stores:
{
  "eventType": "Temporary Override",
  "reason": "Exercise",
  "duration": 60  // minutes
  // ISF modification not captured
}
```

**Nightscout loses:**
- Which settings were modified
- The modification factors
- Relationship to base profile

---

## Proposed Model: Layered Therapy State

### Concept: Separation of Concerns

```
┌─────────────────────────────────────────────────────────┐
│                    OBSERVED STATE                        │
│  (What actually happened - treatments, doses delivered)  │
└─────────────────────────────────────────────────────────┘
                           ▲
                           │ Influenced by
┌─────────────────────────────────────────────────────────┐
│                    EFFECTIVE STATE                       │
│  (What's currently active = base + modifiers)            │
│  effective_basal = base_basal * percentage / 100         │
└─────────────────────────────────────────────────────────┘
                           ▲
                           │ Composed from
┌─────────────────────────┴───────────────────────────────┐
│    MODIFIERS                    BASE PROFILE            │
│    - Percentage (110%)          - Named profile         │
│    - Timeshift (+2h)            - From store/templates  │
│    - Override (Exercise)        - Source (prescribed/   │
│    - Temp target                   user/downloaded)     │
└─────────────────────────────────────────────────────────┘
                           ▲
                           │ Selected from
┌─────────────────────────────────────────────────────────┐
│                    TEMPLATES/PRESETS                     │
│  (Reusable configurations that can be referenced)        │
│  - Override presets (Exercise, Sleep, Pre-meal)          │
│  - Profile alternatives (Day, Night, Sick Day)           │
│  - User-defined or doctor-prescribed                     │
└─────────────────────────────────────────────────────────┘
                           ▲
                           │ Constrained by
┌─────────────────────────────────────────────────────────┐
│                    CAPABILITIES                          │
│  (What the controller can do)                            │
│  - Supports percentage adjustments                       │
│  - Supports time shift                                   │
│  - Supports ISF/CR overrides                             │
│  - Max override duration                                 │
└─────────────────────────────────────────────────────────┘
```

---

## Component 1: Desired vs Effective Split

### New Fields for Profile Events

Extend `Profile Switch` and `Temporary Override` events with explicit modifier tracking:

```yaml
ProfileSwitchEvent:
  eventType: "Profile Switch"
  timestamp: "2026-01-17T10:00:00Z"
  
  # Base profile reference
  baseProfile:
    name: "Day Profile"
    source: "prescribed"  # prescribed | user | downloaded
    templateId: "uuid-of-template"  # Optional reference
  
  # Modifiers applied to base
  modifiers:
    percentage: 110        # null if not modified
    timeshift: 0           # seconds
    duration: 7200         # seconds (0 = permanent)
  
  # Computed effective values (optional, for consumers)
  effective:
    basal: [...]           # Computed: base * percentage / 100
    sens: [...]            # May be shifted by timeshift
    carbratio: [...]
  
  # Semantic intent
  intent: "temporary_adjustment"  # profile_change | temporary_adjustment | time_shift
  reason: "Exercise recovery"
```

### Benefits

1. **Preserved semantics** — `intent` field distinguishes profile changes from adjustments
2. **Traceable modifications** — `modifiers` shows exactly what changed
3. **Reference-based** — `templateId` links to reusable template
4. **Backward compatible** — Existing fields remain; new fields are additive

### Override Events Enhanced

```yaml
TemporaryOverrideEvent:
  eventType: "Temporary Override"
  timestamp: "2026-01-17T14:00:00Z"
  
  # Override identity
  overrideName: "Exercise"
  overrideId: "uuid"
  presetId: "exercise-preset-uuid"  # Reference to template
  
  # What's being modified
  modifications:
    targetRange:
      low: 140
      high: 160
      unit: "mg/dL"
    insulinSensitivityFactor: 0.8   # Multiplier (0.8 = -20%)
    carbRatioFactor: null           # null = unchanged
    basalFactor: null               # null = unchanged
  
  # Lifecycle
  duration: 3600                    # seconds
  actualEnd: null                   # Filled when override ends
  endReason: null                   # natural | superseded | cancelled | user_ended
  supersededBy: null                # UUID of replacing override
  
  # Context
  triggeredBy: "user"               # user | schedule | automation | remote
  enteredBy: "Loop"
```

---

## Component 2: Capability Tracking

### Concept

Controllers can upload a **capability document** describing what features they support. This is lighter than full registration—no verified identity required.

```yaml
ControllerCapabilities:
  controllerId: "loop-ios"          # Self-declared (not verified)
  controllerVersion: "3.4.0"
  uploadedAt: "2026-01-17T10:00:00Z"
  
  # Profile capabilities
  profile:
    supportsMultipleProfiles: true
    supportsPercentageAdjustment: false  # Loop uses overrides instead
    supportsTimeshift: false
    maxProfiles: 10
  
  # Override capabilities
  overrides:
    supported: true
    supportsISFModification: true
    supportsCRModification: false       # Loop overrides don't modify CR
    supportsBasalModification: true
    supportsTargetModification: true
    maxDuration: 86400                  # 24 hours
    presetBased: true                   # Uses predefined presets
  
  # Prediction capabilities
  predictions:
    uploadsPredictions: true
    predictionFormat: "single_array"    # vs separate_arrays
    uploadsEffectTimelines: false       # Loop doesn't upload component effects
  
  # Sync capabilities
  sync:
    apiVersion: "v1"
    identityField: "syncIdentifier"
    supportsUpdates: false              # POST only
    supportsDeletions: false
  
  # Remote command capabilities
  remoteCommands:
    supported: true
    overrides: true
    bolus: true
    carbs: true
    tempTargets: false
```

### Storage Options

**Option A: DeviceStatus Embedding**

Include capabilities in regular devicestatus uploads:

```json
{
  "device": "loop://iPhone",
  "loop": { ... },
  "capabilities": { ... }  // New field
}
```

**Pros:** No new collection, natural frequency
**Cons:** Redundant repeated uploads

**Option B: Separate Capabilities Collection**

New `/api/v1/capabilities.json` endpoint:

```http
POST /api/v1/capabilities.json
{
  "controllerId": "loop-ios",
  "capabilities": { ... }
}
```

**Pros:** Clean separation, query-friendly
**Cons:** New endpoint, adoption required

**Option C: Profile Store Extension**

Add capabilities to profile uploads:

```json
{
  "defaultProfile": "Default",
  "store": { ... },
  "controllerCapabilities": { ... }  // New field
}
```

**Pros:** Natural association with profile
**Cons:** Couples capabilities to profile timing

**Recommendation:** Option B (separate collection) for clean querying, with Option A as fallback for backward compatibility.

### Consumer Benefits

With capability tracking, consumers can:

1. **Adapt parsing** — Know whether to expect percentage modifiers or not
2. **Set expectations** — Understand why certain data is missing
3. **Compare controllers** — Build comparison matrices automatically
4. **Debug sync issues** — Know what a controller should be uploading

---

## Component 3: Templates and Presets

### Concept

Separate reusable therapy configurations from active state. Templates can be:

- **Override presets** — Exercise, Sleep, Pre-meal, Sick Day
- **Profile alternatives** — Day Profile, Night Profile, Weekend
- **Shared configurations** — Downloaded from Nightscout, prescribed by doctor

### Template Schema

```yaml
TherapyTemplate:
  templateId: "uuid"
  templateType: "override_preset"  # override_preset | profile | therapy_protocol
  
  name: "Exercise"
  description: "For moderate activity, raises target and reduces insulin sensitivity"
  
  # Source tracking
  source:
    type: "user_defined"           # user_defined | prescribed | downloaded | system
    authoredBy: "user-id"          # Optional
    prescribedBy: "Dr. Smith"      # Optional
    downloadedFrom: "nightscout"   # Optional
  
  # Template content (varies by type)
  content:
    # For override_preset:
    targetRange: { low: 140, high: 160 }
    insulinSensitivityFactor: 0.8
    carbRatioFactor: null
    basalFactor: null
    defaultDuration: 3600
    
    # For profile:
    # basal: [...], sens: [...], etc.
  
  # Usage constraints
  constraints:
    maxDuration: 14400             # 4 hours
    allowedTimeWindows: null       # null = any time
    requiresConfirmation: false
  
  # Metadata
  createdAt: "2026-01-01T00:00:00Z"
  updatedAt: "2026-01-17T10:00:00Z"
  version: 2
```

### Template References in Events

Override and profile switch events reference templates:

```yaml
TemporaryOverrideEvent:
  eventType: "Temporary Override"
  overrideName: "Exercise"
  
  # Reference to template
  templateRef:
    templateId: "exercise-uuid"
    templateVersion: 2
    
  # Actual values used (may differ from template)
  modifications:
    targetRange: { low: 150, high: 170 }  # User adjusted from template
    insulinSensitivityFactor: 0.8
```

This enables:
- **Traceability** — Know which template was used
- **Deviation tracking** — Compare actual to template values
- **Template updates** — Templates can evolve independently of events

---

## Relationship to Controller Registration

This proposal is **complementary but independent**:

| Aspect | Profile Model Evolution | Controller Registration |
|--------|-------------------------|-------------------------|
| **Focus** | Data semantics | Identity and authority |
| **Requires auth** | No | Yes |
| **Scope** | Schema improvements | Infrastructure changes |
| **Adoption barrier** | Schema updates | Registration protocol |
| **Value standalone** | Yes | Yes |

### Synergy

If both are implemented:

1. **Registered controllers** commit to uploading enhanced profile events
2. **Capability documents** become verified (linked to registration)
3. **Templates** can be protected by authority (only owner can modify)

But each can proceed independently:

- Profile model evolution can happen **now** with schema additions
- Controller registration can happen **later** when infrastructure is ready

---

## Migration Path

### Phase 1: Additive Schema (Immediate)

Add new optional fields to existing events:

```json
{
  "eventType": "Profile Switch",
  "profile": "Day Profile (+10%)",  // Existing (kept for compatibility)
  
  // New fields (optional)
  "baseProfile": { "name": "Day Profile", "source": "user" },
  "modifiers": { "percentage": 110, "duration": 7200 },
  "intent": "temporary_adjustment"
}
```

Consumers that understand new fields get richer semantics. Others continue working.

### Phase 2: Controller Adoption (3-6 months)

Encourage controllers to populate new fields:

1. Loop uploads `modifications` object in override events
2. AAPS uploads `baseProfile` + `modifiers` in ProfileSwitch
3. Trio uploads template references

### Phase 3: Capability Collection (6-12 months)

Implement capability collection endpoint:

1. Controllers upload capability documents
2. Consumers query capabilities for parsing guidance
3. Build automated compatibility matrices

### Phase 4: Template System (12+ months)

Implement full template system:

1. Template CRUD endpoints
2. Reference tracking in events
3. Source attribution (prescribed vs user)

---

## Open Questions

1. **Effective values computation** — Should Nightscout compute effective values, or trust controller uploads?

2. **Template ownership** — Who can modify a template? Only creator? Anyone with write access?

3. **Prescribed vs user settings** — How do we track when user deviates from prescribed settings?

4. **Cross-controller templates** — Should templates be shareable across controllers? Or controller-specific?

5. **Historical templates** — How do we handle template versioning when analyzing historical data?

6. **Capability staleness** — How long are capability documents valid? Should they expire?

---

## Success Metrics

1. **Semantic preservation** — % of profile events with `intent` field populated
2. **Modifier tracking** — % of adjustments with explicit `modifiers` object
3. **Template adoption** — % of overrides with `templateRef`
4. **Capability coverage** — % of active controllers with capability documents

---

## Next Steps

- [ ] Draft JSON Schema for enhanced profile events
- [ ] Propose capability document schema to Nightscout maintainers
- [ ] Create example mappings for Loop, AAPS, and Trio
- [ ] Prototype capability collection endpoint
- [ ] Gather feedback from controller maintainers
- [ ] Update GAP-002 with proposed solution path

---

## Related Documents

- [Profile/Therapy Settings Comparison](profile-therapy-settings-comparison.md)
- [AAPS ProfileSwitch Mapping](../../mapping/aaps/profile-switch.md)
- [Controller Registration Proposal](controller-registration-protocol-proposal.md)
- [Authority Model](../10-domain/authority-model.md)
- [Known Gaps](../../traceability/gaps.md)

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-17 | Agent | Initial draft |
