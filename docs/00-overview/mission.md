# Mission

## What Alignment Is

Alignment is a coordination effort to establish shared semantics, schemas, and conformance criteria across multiple Automated Insulin Delivery (AID) systems and their supporting infrastructure.

The goal is to enable:

- **Interoperability**: Data from any AID system (Loop, AAPS, Trio) can be understood and processed by any compliant server (Nightscout, Tidepool, etc.)
- **Traceability**: Every piece of AID data can be traced from its origin through transformations to its final representation
- **Consistency**: The same concepts (profiles, overrides, treatments, etc.) mean the same thing across all systems

## What Alignment Is Not

- **A replacement** for any existing project's internal data model
- **A mandate** that projects must change their implementations
- **A single source of truth** that overrides project-specific decisions

Instead, alignment provides:

- A reference schema that projects can map to
- Conformance tests that verify correct mapping
- Documentation that explains the rationale behind semantic choices

## Scope

This workspace covers:

| Area | In Scope | Out of Scope |
|------|----------|--------------|
| Data semantics | Event types, fields, relationships | UI/UX decisions |
| Schemas | JSON Schema, OpenAPI definitions | Internal storage formats |
| Conformance | Test scenarios, assertions | Performance benchmarks |
| Mapping | How each project interprets specs | Implementation guidance |

## Success Criteria

Alignment is successful when:

1. A new AID event type can be defined once and understood by all projects
2. Data exported from one system can be imported into another without loss of semantic meaning
3. Gaps and ambiguities are explicitly documented rather than discovered through bugs
