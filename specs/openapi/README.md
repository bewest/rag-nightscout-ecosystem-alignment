# OpenAPI Specifications - Coverage and Methodology

**Status:** In Progress  
**Date:** 2026-01-17  
**Version:** 0.1.0

---

## Overview

This directory contains OpenAPI 3.0 specifications documenting the de facto data exchange standards for Automated Insulin Delivery (AID) systems circa 2025, along with alignment extensions proposed for 2026.

### Design Principles

1. **Two-Layer Approach**
   - **De Facto 2025**: Accurate representation of what currently exists in production
   - **2026 Alignment**: Extensions addressing documented gaps (marked with `x-aid-*` annotations)

2. **Source-Verified**
   - Every field traces to source code evidence in `externals/`
   - Cross-referenced with deep-dive documents in `docs/10-domain/`
   - Gap references link to `traceability/gaps.md`

3. **Controller-Aware**
   - Documents controller-specific variations (Loop vs AAPS vs Trio vs xDrip+)
   - Notes where semantic translation is required
   - Highlights deduplication and sync identity differences

---

## Coverage Matrix

| Spec File | Collection | 2025 Status | 2026 Extensions | Related Gaps |
|-----------|------------|-------------|-----------------|--------------|
| [`aid-entries-2025.yaml`](./aid-entries-2025.yaml) | entries | ✅ Complete | ✅ Covered | GAP-ENTRY-001 through GAP-ENTRY-005, GAP-CGM-001 through GAP-CGM-006 |
| [`aid-treatments-2025.yaml`](./aid-treatments-2025.yaml) | treatments | ✅ Complete | ✅ Covered | GAP-TREAT-001 through GAP-TREAT-007, GAP-003 |
| [`aid-devicestatus-2025.yaml`](./aid-devicestatus-2025.yaml) | devicestatus | ✅ Complete | ✅ Covered | GAP-DS-001 through GAP-DS-004, GAP-SYNC-002, GAP-SYNC-005 |
| [`aid-profile-2025.yaml`](./aid-profile-2025.yaml) | profile | ✅ Complete | ✅ Covered | GAP-002, GAP-INS-001 through GAP-INS-004 |
| [`aid-statespan-2025.yaml`](./aid-statespan-2025.yaml) | state-spans | ✅ Complete | Reference only | GAP-V4-001, GAP-V4-002, GAP-SYNC-037 |
| [`aid-alignment-extensions.yaml`](./aid-alignment-extensions.yaml) | All | N/A | ✅ Complete | All gaps mapped to extensions |
| [`nocturne-v4-extension.yaml`](./nocturne-v4-extension.yaml) | V4 | ✅ Complete | N/A (Nocturne-specific) | GAP-V4-001, GAP-NOCTURNE-001 |

### Gap Coverage Summary

The alignment extensions address the following gap categories:

| Gap Category | Gap IDs | Extension Schema |
|--------------|---------|------------------|
| **Identity/Authority** | GAP-003, GAP-AUTH-001, GAP-AUTH-002 | `ControllerIdentity`, `DocumentAuthority`, `SyncMetadata` |
| **Override Lifecycle** | GAP-001, GAP-SYNC-004 | `OverrideLifecycle` |
| **Profile Semantics** | GAP-002 | `ProfileModification` |
| **Entry Direction** | GAP-ENTRY-001 | `ExtendedDirection` |
| **Noise/Reliability** | GAP-ENTRY-002 | `NoiseMetadata` |
| **Source Taxonomy** | GAP-ENTRY-003, GAP-CGM-004 | `SourceTaxonomy` |
| **Entry Deduplication** | GAP-ENTRY-004 | `EntryDeduplication` |
| **Raw Sensor Data** | GAP-ENTRY-005, GAP-CGM-005 | `RawSensorData` |
| **CGM Provenance** | GAP-CGM-001, GAP-CGM-002, GAP-CGM-003, GAP-CGM-006 | `CGMProvenance` |
| **Insulin Metadata** | GAP-INS-001 through GAP-INS-004 | `InsulinMetadata` |
| **Treatment Precision** | GAP-PUMP-005, GAP-TREAT-003 | `TreatmentPrecision` |

---

## Methodology

### Source Authority Hierarchy

1. **Primary**: Nightscout API v3 swagger.yaml (`externals/cgm-remote-monitor/lib/api3/swagger.yaml`)
2. **Secondary**: Controller source code (Loop, AAPS, Trio, xDrip+)
3. **Tertiary**: Observed behavior documented in deep-dives

### Field Documentation Pattern

Each field includes:
- `description`: Human-readable explanation
- `x-aid-source`: Source file reference (when applicable)
- `x-aid-controllers`: Controller support matrix
- `x-aid-gap`: Related gap ID (when applicable)
- `x-aid-2026`: Alignment extension notes (when applicable)

### Validation Strategy

Specs are validated against:
1. JSON Schema draft 2020-12 compatibility
2. Existing test fixtures in `specs/fixtures/`
3. Real-world data from controller uploads

---

## Cross-References

### Deep-Dive Documents
- [`docs/10-domain/entries-deep-dive.md`](../../docs/10-domain/entries-deep-dive.md) - SGV/MBG field mapping
- [`docs/10-domain/treatments-deep-dive.md`](../../docs/10-domain/treatments-deep-dive.md) - Bolus/carb/temp basal mapping
- [`docs/10-domain/devicestatus-deep-dive.md`](../../docs/10-domain/devicestatus-deep-dive.md) - Loop vs oref0 structure
- [`docs/10-domain/nightscout-api-comparison.md`](../../docs/10-domain/nightscout-api-comparison.md) - API v1 vs v3

### Proposals
- [`docs/60-research/controller-registration-protocol-proposal.md`](../../docs/60-research/controller-registration-protocol-proposal.md) - Identity and authority
- [`docs/60-research/profile-model-evolution-proposal.md`](../../docs/60-research/profile-model-evolution-proposal.md) - Desired vs observed split

### Traceability
- [`traceability/gaps.md`](../../traceability/gaps.md) - All identified gaps
- [`traceability/requirements.md`](../../traceability/requirements.md) - Derived requirements
- [`mapping/cross-project/terminology-matrix.md`](../../mapping/cross-project/terminology-matrix.md) - Rosetta stone
- [`docs/10-domain/req-api-openapi-alignment-audit.md`](../../docs/10-domain/req-api-openapi-alignment-audit.md) - REQ-API → OpenAPI coverage audit

---

## Progress Log

### 2026-02-01: StateSpan V3 Extension Spec

**Completed:**
- Created `aid-statespan-2025.yaml` - V3 extension for time-ranged state tracking
- 6 endpoints: status, query, active, get, update, delete
- 4 categories: Profile, Override, TempBasal, PumpMode
- Reference spec only (per Nocturne author preference for V4-only)

**Key Decisions:**
- Documented as hypothetical V3 extension for reference
- Links to GAP-V4-001, GAP-V4-002 for standardization gaps
- Includes feature detection endpoint for client compatibility

### 2026-01-17: Initial OpenAPI Spec Development

**Completed:**
- Created `aid-entries-2025.yaml` - Full entries collection schema
- Created `aid-treatments-2025.yaml` - Full treatments collection with eventType catalog
- Created `aid-devicestatus-2025.yaml` - Loop and oref0 structure variants
- Created `aid-profile-2025.yaml` - Profile store structure
- Created `aid-alignment-extensions.yaml` - Gap-resolving extensions

**Key Decisions:**
- Used OpenAPI 3.0.3 for broad tooling compatibility
- Adopted `x-aid-*` extension prefix for alignment annotations
- Documented controller quirks inline rather than separate files

---

## Next Cycle Candidates

### Priority A: Conformance Test Integration
- Generate JSON Schema from OpenAPI for `validate_fixtures.py`
- Create fixture examples from real controller uploads
- Add schema validation to CI

### Priority B: Controller-Specific Profiles
- Separate OpenAPI specs per controller for client generation
- Document required vs optional fields per controller
- Generate TypeScript/Kotlin/Swift types

### Priority C: API v1 Documentation
- Document legacy v1 endpoints still used by Loop/Trio
- Map v1 → v3 field equivalences
- Identify v1-only features not in v3

---

## Usage

### Viewing Specs
```bash
# View with Swagger UI (requires npx)
npx @redocly/cli preview-docs specs/openapi/aid-entries-2025.yaml
```

### Validating Specs
```bash
# Validate OpenAPI syntax
npx @redocly/cli lint specs/openapi/*.yaml

# Check against fixtures
python tools/validate_fixtures.py --schema specs/openapi/
```

### Generating Types
```bash
# Generate TypeScript types
npx openapi-typescript specs/openapi/aid-entries-2025.yaml -o types/entries.ts
```
