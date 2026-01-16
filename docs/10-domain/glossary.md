# Glossary

This glossary defines terms as used within this alignment workspace. Projects may use different terminology internally; see the [mapping notes](../../mapping/) for project-specific translations.

---

## Core Concepts

### Profile
A collection of settings that define how the AID algorithm should behave. Includes basal rates, ISF, CR, and targets.

In Nightscout, profiles are stored in a `store` object with named profiles (e.g., "Default", "Weekend").

**See also**: [Override](#override), [Profile Switch](#profile-switch)

### Profile Switch
A treatment event that changes the active profile. In Nightscout, this is represented as a treatment with `eventType: "Profile Switch"`.

### Override
A temporary modification to profile settings. Overrides have a defined duration and can affect one or more profile parameters.

**Key properties**:
- `name`: Human-readable identifier
- `duration`: How long the override is active
- `target_range`: Modified target glucose range (if any)
- `insulin_sensitivity_factor`: Modified ISF (if any)
- `overall_insulin_needs`: Percentage modifier (e.g., 110% = more aggressive)

**Nightscout mapping**: Stored as treatments with `eventType: "Temporary Override"` or `"Temporary Target"`.

### Supersede
When one event replaces or cancels another. An override that supersedes another means the new override takes effect and the previous one is no longer active.

**Important**: Supersession is not deletion—the original event still exists in history but is marked as superseded.

**Nightscout gap**: Currently no `superseded` or `superseded_by` fields exist (GAP-001).

### Treatment
Any user intervention or system event related to diabetes management. Includes insulin doses, carb entries, profile switches, notes, and device events.

In Nightscout, treatments are stored in the `treatments` collection with an `eventType` field indicating the type.

### Entry
A glucose reading from a CGM device. In Nightscout, entries are stored in the `entries` collection with `sgv` (sensor glucose value) and `direction` (trend arrow) fields.

### DeviceStatus
Current state of a controller, pump, or uploader. Contains loop/algorithm state, pump status, and connectivity information.

---

## Data States

### Desired
What the user or algorithm intended to happen.

**Example**: "Deliver 1.2 U/hr basal"

### Observed
What sensors and devices report actually happened.

**Example**: "CGM reading of 145 mg/dL"

### Delivered
What was actually administered, as confirmed by the delivery device.

**Example**: "Pump delivered 0.3 U bolus"

---

## Authority & Provenance

### Authority
The source that has the right to define or modify a piece of data.

**Examples**:
- The pump has authority over delivered insulin
- The CGM has authority over glucose readings
- The user has authority over profile settings

### Provenance
The chain of custody for a piece of data—where it came from and how it was transformed.

---

## Project-Specific Terms

| Alignment Term | Loop | AAPS | Trio | Nightscout |
|----------------|------|------|------|------------|
| Profile | Profile | Profile | Profile | Profile |
| Override | Override | TempTarget + ProfileSwitch | Override | Override |
| Bolus | Bolus | Bolus | Bolus | Treatment (type: bolus) |

---

## Abbreviations

| Abbreviation | Expansion |
|--------------|-----------|
| AID | Automated Insulin Delivery |
| ISF | Insulin Sensitivity Factor |
| CR | Carb Ratio |
| IOB | Insulin On Board |
| COB | Carbs On Board |
| CGM | Continuous Glucose Monitor |
| BG | Blood Glucose |
