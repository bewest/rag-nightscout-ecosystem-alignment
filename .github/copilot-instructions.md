# Nightscout Ecosystem Alignment Workspace

## Overview

This workspace coordinates cross-project analysis of 20 CGM/AID (Continuous Glucose Monitor / Automated Insulin Delivery) repositories to ensure interoperability and data alignment across the Nightscout ecosystem.

## Repository Structure

```
externals/           # Git-ignored external repos (reproducible via workspace.lock.json)
  ├── LoopWorkspace/      # Loop iOS app
  ├── cgm-remote-monitor/ # Nightscout web server
  ├── AndroidAPS/         # AAPS Android app
  ├── Trio/               # Trio iOS app
  ├── xDrip/              # xDrip+ Android CGM app
  ├── xdripswift/         # xDrip4iOS app
  ├── DiaBLE/             # DiaBLE iOS Libre reader
  └── ... (20 repos total)
mapping/             # Per-project and cross-project field mappings
specs/               # OpenAPI 3.0 and JSON Schema specifications
conformance/         # Test scenarios and assertions (YAML)
traceability/        # Requirements, gaps, coverage matrices
docs/                # Research and deep-dive documentation
tools/               # Python automation scripts
```

## Working with External Repos

- Run `make bootstrap` to clone all external repos to `externals/`
- Run `make freeze` to pin current commits in `workspace.lock.json`
- **Never commit directly to main/master** in external repos
- Create topic branches: `git checkout -b workspace/feature-name`

## Multi-Faceted Analysis Pattern

When analyzing any component, **update all 5 facets**:

| Facet | File | Purpose |
|-------|------|---------|
| Terminology | `mapping/cross-project/terminology-matrix.md` | Cross-project term mapping |
| Gaps | `traceability/gaps.md` | GAP-XXX-NNN identifiers |
| Requirements | `traceability/requirements.md` | REQ-NNN identifiers |
| Deep Dive | `docs/10-domain/{component}-deep-dive.md` | Technical documentation |
| Progress | `progress.md` | Dated completion entry |

## ID Conventions

### Gap IDs: `GAP-<CATEGORY>-<NNN>`

| Prefix | Domain |
|--------|--------|
| GAP-G7-NNN | Dexcom G7 protocol |
| GAP-CGM-NNN | CGM data source |
| GAP-SYNC-NNN | Synchronization |
| GAP-TREAT-NNN | Treatments |
| GAP-DS-NNN | DeviceStatus |
| GAP-ALG-NNN | Algorithm comparison |
| GAP-ENTRY-NNN | Entries collection |
| GAP-PROF-NNN | Profile/therapy settings |

### Requirement IDs: `REQ-<NNN>`

| Range | Domain |
|-------|--------|
| REQ-001-009 | Override behavior |
| REQ-010-019 | Timestamp handling |
| REQ-020-029 | Sync identity |
| REQ-030-039 | Data validation |
| REQ-050-059 | CGM data source |
| REQ-060-069 | Algorithm |

Check `traceability/requirements.md` for next available number.

## Code References

Always use explicit file:line references:

```
`externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/BgReading.java:45`
```

## Key OpenAPI Specs

| Spec | Collection |
|------|------------|
| `specs/openapi/aid-entries-2025.yaml` | SGV, MBG, calibration |
| `specs/openapi/aid-treatments-2025.yaml` | Bolus, carbs, temp basal |
| `specs/openapi/aid-devicestatus-2025.yaml` | Loop vs oref0 structure |
| `specs/openapi/aid-profile-2025.yaml` | Therapy settings |

Specs use `x-aid-*` extensions for gap annotations and controller support.

## Validation Commands

```bash
make verify              # Run all static verification
make traceability        # Generate traceability matrix
make workflow TYPE=quick # Fast validation subset
make workflow TYPE=full  # Complete CI pipeline
```

## Domain Knowledge

### Diabetes/CGM Terminology
- **SGV**: Sensor Glucose Value (mg/dL or mmol/L)
- **IOB**: Insulin on Board (active insulin)
- **COB**: Carbs on Board (unabsorbed carbs)
- **CR**: Carb Ratio (g carbs per unit insulin)
- **ISF**: Insulin Sensitivity Factor
- **DIA**: Duration of Insulin Action
- **SMB**: Super Micro Bolus (oref0/AAPS feature)
- **UAM**: Unannounced Meal detection

### AID Systems
- **Loop**: iOS closed-loop (LoopKit, LoopWorkspace)
- **AAPS**: Android APS using oref0/oref1 algorithms
- **Trio**: iOS fork using oref1 algorithm
- **oref0/oref1**: OpenAPS Reference Design algorithms

### CGM Apps
- **xDrip+**: Android CGM data manager (20+ sources)
- **xDrip4iOS**: iOS port with fewer sources
- **DiaBLE**: iOS Libre sensor reader
- **Nightscout**: Central data aggregation server
