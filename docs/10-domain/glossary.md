# Glossary

This glossary defines terms as used within this alignment workspace. Projects may use different terminology internally; see the [mapping notes](../../mapping/) for project-specific translations.

---

## Core Concepts

### Profile
A collection of settings that define how the AID algorithm should behave. Includes basal rates, ISF, CR, and targets.

**See also**: [Override](#override)

### Override
A temporary modification to profile settings. Overrides have a defined duration and can affect one or more profile parameters.

**Key properties**:
- `name`: Human-readable identifier
- `duration`: How long the override is active
- `target_range`: Modified target glucose range (if any)
- `insulin_sensitivity_factor`: Modified ISF (if any)
- `overall_insulin_needs`: Percentage modifier (e.g., 110% = more aggressive)

### Supersede
When one event replaces or cancels another. An override that supersedes another means the new override takes effect and the previous one is no longer active.

**Important**: Supersession is not deletion—the original event still exists in history but is marked as superseded.

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
