# AID Alignment Workspace

## Overview

The AID Alignment Workspace is a documentation and coordination project focused on standardizing semantics, schemas, and conformance across multiple Automated Insulin Delivery (AID) systems (Nightscout, Loop, AAPS, Trio). Its core purpose is to enhance interoperability and ensure consistent data interpretation and behavior across these diverse platforms.

The project delivers normative definitions, informative documentation, decision records, and executable conformance tests. It aims to provide a centralized, version-controlled source of truth to improve understanding, integration, and reliability of AID systems for both users and developers.

## User Preferences

I want iterative development. Each iteration cycle should update:
1. Scenario backlog
2. Requirements snippet
3. Spec delta (schema changes)
4. Mapping notes (per project)
5. Conformance update
6. Gap/coverage update

## System Architecture

The workspace is designed to separate normative specifications from informative documentation and executable tests.

- **`docs/`**: Contains narrative documentation, including overviews, domain concepts, design proposals, implementation notes, and architecture decision records (ADRs). The UI/UX emphasizes clear structure and cross-referencing.
  - Key new deliverables (2026-01-19):
    - `docs/60-research/mongodb-update-readiness-report.md` - **UPDATED** Revised risk matrix based on verified NightscoutKit source; downgraded "Response format breaking change" from HIGH to MEDIUM
    - `docs/60-research/mongodb-modernization-impact-assessment.md` - **UPDATED** Corrected v1 API response requirements; only `_id` required, `ok`/`n` fields not checked by Loop
    - `docs/10-domain/nightscout-api-comparison.md` - **UPDATED** Added Section 8.3 documenting verified client response parsing behavior with source code references
    - `docs/cgm-remote-monitor-analysis-2026-01-18.md` - **UPDATED v1.2** Integrated January 19, 2026 findings from cgm-remote-monitor sources:
      - Test stability verification: 100% pass rate across 19 test files in stress testing
      - Flaky test fixes: floating-point precision, boot optimization, timeout improvements
      - MongoDB pool optimization: test environment uses `MONGO_POOL_SIZE=2`
      - Timing instrumentation: new test helper module with anti-pattern detection
      - Modernization roadmap: 5-phase plan (Security → DevEx → Performance → Architecture → UI)
      - Coverage gaps: High-priority items (WebSocket Auth, JWT expiration, API v3 Security)
  - Key deliverables (2026-01-18):
    - `docs/cgm-remote-monitor-analysis-2026-01-18.md` - Initial analysis of cgm-remote-monitor repository (superseded by v1.2 above)
  - Key deliverables (2026-01-17):
    - `docs/10-domain/data-rights-primer.md` - **NEW** Plain-language guide to the Five Fundamental Diabetes Data Rights (Access, Export, Share, Delegate, Audit), multi-stakeholder accessibility for patients, clinicians, developers, and policymakers, "ownership to agency" framing shift
    - `docs/10-domain/progressive-enhancement-framework.md` - **NEW** 10-layer capability ladder for diabetes technology (L0 MDI baseline through L9 delegate agents), design principles (progressive enhancement, graceful degradation, separation of concerns), shared vocabulary for describing any AID system
    - `docs/DIGITAL-RIGHTS.md` - **NEW** Comprehensive guide to legal frameworks protecting open-source diabetes software (GPL v3 licensing, DMCA 1201 exemptions, interoperability defenses, right-to-repair landscape, counter-notice guidance)
    - `docs/10-domain/nightscout-api-comparison.md` - **UPDATED** Major revision to Section 3 (Authentication) based on source code verification. Now accurately documents that both API v1 and v3 use a shared authorization module, with v3 REST restricting to JWT Bearer tokens at the entry point while v3 alarmSocket supports full dual-auth and storageSocket is accessToken-only.
    - `docs/10-domain/libre-protocol-deep-dive.md` - **NEW** Comprehensive Libre sensor protocol specification (800+ lines) covering all generations (Libre 1/2/2+/Gen2/3/3+), NFC access, FRAM memory layout, encryption schemes, BLE protocols, transmitter bridges, and cross-system compatibility
    - `docs/30-design/nightscout-integration-guide.md` - Practical guide for app developers
    - `docs/60-research/controller-registration-protocol-proposal.md` - **v2** Controller Registration Protocol as Nightscout Core contract with OpenAPI schema, implementation roadmap, and resolved open questions
    - `docs/60-research/profile-model-evolution-proposal.md` - Desired vs observed split, capability tracking
    - `docs/60-research/stakeholder-priority-analysis.md` - **NEW** Maps 9 stakeholder groups against 91+ documented gaps, identifies high-leverage unlock points, and analyzes friction between infrastructure modernization and semantic gap resolution
    - `docs/90-decisions/adr-002-sync-identity-strategy.md` - Decision record on sync identity
    - `docs/90-decisions/adr-003-no-custom-credentials.md` - **NEW** Decision record explaining why Nightscout avoids custom username/password authentication in favor of identity federation and zero trust principles
- **`specs/`**: Houses normative definitions using OpenAPI specifications and JSON Schema, along with test fixtures.
  - **OpenAPI 3.0 Specifications** (2026-01-17):
    - `specs/openapi/README.md` - Coverage matrix and methodology documentation
    - `specs/openapi/aid-entries-2025.yaml` - De facto 2025 entries collection (SGV, MBG, calibration)
    - `specs/openapi/aid-treatments-2025.yaml` - De facto 2025 treatments with complete eventType catalog
    - `specs/openapi/aid-devicestatus-2025.yaml` - De facto 2025 devicestatus (Loop/oref0/AAPS variations)
    - `specs/openapi/aid-profile-2025.yaml` - De facto 2025 profile collection
    - `specs/openapi/aid-alignment-extensions.yaml` - 2026 alignment extensions addressing 30+ documented gaps
  - **JSON Schema** (updated 2026-01-17):
    - `specs/jsonschema/aid-events.schema.json` - Unified schema aligned with OpenAPI specs, includes 2026 extension fields
- **`conformance/`**: Contains executable test scenarios and assertion definitions to validate system behavior against specifications.
- **`mapping/`**: Provides detailed interpretations and mappings for each AID project (Nightscout, Loop, AAPS, Trio), including cross-project comparison matrices.
- **`traceability/`**: Manages coordination control, including coverage matrices, identified gaps, and derived requirements.
  - Key new deliverables (2026-01-18):
    - `traceability/cgm-remote-monitor-docs-inventory.md` - **NEW** Documentation inventory for cgm-remote-monitor with new taxonomy, test file mapping, and client deduplication patterns
- **`tools/`**: A suite of utilities for workspace management, validation, and testing:
  - **Repository Management**: `bootstrap.py` (clone/update externals), `checkout_submodules.py`
  - **Validation**: `linkcheck.py` (internal links), `validate_fixtures.py` (schema validation)
  - **Conformance**: `run_conformance.py` (offline conformance tests)
  - **Inventory**: `gen_inventory.py` (artifact inventory), `gen_coverage.py` (coverage matrix), `gen_refs.py` (code reference permalinks)
  - **Static Verification** (2026-01-17):
    - `verify_refs.py` - Validates code references in mappings resolve to actual files in externals
    - `verify_coverage.py` - Analyzes requirement/gap coverage across mappings, specs, and assertions
    - `verify_terminology.py` - Checks terminology consistency using the terminology matrix as source of truth
    - `verify_assertions.py` - Traces assertions to requirements, identifies orphaned assertions and uncovered requirements
  - See `docs/tooling-roadmap.md` for proposed future tooling improvements for agent-based SDLC workflows.
- **CI Integration**: A GitHub Actions workflow ensures continuous validation of code, link integrity, fixture validation, offline conformance tests, and coverage matrix generation.
- **Agent Tooling Suite** (2026-01-20):
  - `tools/phase_nav.py` - Document phase tracking and transition suggestions for the 5-phase cycle
  - `tools/detect_drift.py` - Documentation drift detection from source code
  - `tools/spec_capture.py` - Implicit requirement extraction and spec verification
  - `tools/project_seq.py` - Multi-component improvement project management
  - `tools/agent_context.py` - Single entry point for AI agents to get workspace context
  - `tools/ai_advisor.py` - AI-powered suggestions using Anthropic integration
  - Extended `workspace_cli.py` with commands: phase, drift, specs, project, context, advise

## External Dependencies

The project integrates with and documents the following external Automated Insulin Delivery (AID) systems and related projects:

- **Nightscout Ecosystem**:
    - `cgm-remote-monitor` (crm)
    - `nightscout-connect` (ns-connect)
    - `nightscout-roles-gateway` (ns-gateway)
    - `nightscout-reporter` (ns-reporter)
- **AID Systems**:
    - `LoopWorkspace` (loop)
    - `AndroidAPS` (aaps)
    - `Trio` (trio)
- **Algorithms**:
    - `oref0`
    - `openaps`
- **CGM/Monitoring Apps**:
    - `nightguard`: iOS/watchOS app for blood glucose monitoring via Nightscout, acting as a pure consumer.
    - `xdripswift` (xdrip4ios): iOS app for CGM data management, acting as a producer and consumer.
    - `xDrip`: Android xDrip+ app for CGM data collection, acting as a producer and consumer with extensive features.
    - `DiaBLE` (diable): iOS/watchOS app for reading Libre sensors directly via NFC/Bluetooth.
    - `xdrip-js`: Node.js library for interfacing with Dexcom G5/G6 transmitters via BLE.
- **Caregiver/Follower Apps**:
    - `LoopFollow` (loopfollow): iOS/watchOS app for caregivers to monitor Loop/Trio/iAPS users via Nightscout with comprehensive alarms and remote override support.
    - `LoopCaregiver` (loopcaregiver): iOS companion app enabling full remote control (bolus, carbs, overrides) for Loop users via Nightscout Remote 2.0 API.

## Static Verification Tools

The workspace includes a suite of static verification tools that analyze JSON, YAML, and Markdown artifacts without requiring external runtime dependencies. These tools provide early validation of documentation quality and conformance coverage.

### Usage

```bash
make verify              # Run all verification tools
make verify-refs         # Validate code references
make verify-coverage     # Analyze requirement/gap coverage
make verify-terminology  # Check terminology consistency
make verify-assertions   # Trace assertions to requirements
```

### Output Reports

All reports are generated in both JSON (machine-readable) and Markdown (human-readable) formats:

| Tool | JSON Output | Markdown Output |
|------|-------------|-----------------|
| verify_refs.py | `traceability/refs-validation.json` | `traceability/refs-validation.md` |
| verify_coverage.py | `traceability/coverage-analysis.json` | `traceability/coverage-analysis.md` |
| verify_terminology.py | `traceability/terminology-consistency.json` | `traceability/terminology-consistency.md` |
| verify_assertions.py | `traceability/assertion-trace.json` | `traceability/assertion-trace.md` |

### What Each Tool Validates

1. **verify_refs.py** - Ensures code references like `` `loop:Loop/Models/Override.swift` `` actually resolve to files in the `externals/` directory. Catches stale references when source code evolves.

2. **verify_coverage.py** - Cross-references requirements (REQ-XXX) and gaps (GAP-XXX-YYY) across mappings, specs, and assertions. Identifies requirements with no coverage and orphaned gaps.

3. **verify_terminology.py** - Uses the terminology matrix (`mapping/cross-project/terminology-matrix.md`) as source of truth. Checks that mapping documents use consistent terminology across projects.

4. **verify_assertions.py** - Parses conformance assertion files and maps them to requirements. Identifies orphaned assertions (no linked requirements) and uncovered requirements (no assertions).