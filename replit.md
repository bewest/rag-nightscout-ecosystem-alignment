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
  - Key new deliverables (2026-01-17):
    - `docs/30-design/nightscout-integration-guide.md` - Practical guide for app developers
    - `docs/60-research/controller-registration-protocol-proposal.md` - Inversion of control proposal
    - `docs/90-decisions/adr-002-sync-identity-strategy.md` - Decision record on sync identity
- **`specs/`**: Houses normative definitions using OpenAPI specifications and JSON Schema, along with test fixtures.
- **`conformance/`**: Contains executable test scenarios and assertion definitions to validate system behavior against specifications.
- **`mapping/`**: Provides detailed interpretations and mappings for each AID project (Nightscout, Loop, AAPS, Trio), including cross-project comparison matrices.
- **`traceability/`**: Manages coordination control, including coverage matrices, identified gaps, and derived requirements.
- **`tools/`**: A suite of utilities for workspace management, validation, and testing (e.g., `bootstrap.py` for external repositories, `linkcheck.py`, `validate_fixtures.py`, `run_conformance.py`, `gen_coverage.py`).
- **CI Integration**: A GitHub Actions workflow ensures continuous validation of code, link integrity, fixture validation, offline conformance tests, and coverage matrix generation.

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