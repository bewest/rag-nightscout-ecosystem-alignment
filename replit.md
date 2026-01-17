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
    - `docs/10-domain/libre-protocol-deep-dive.md` - **NEW** Comprehensive Libre sensor protocol specification (800+ lines) covering all generations (Libre 1/2/2+/Gen2/3/3+), NFC access, FRAM memory layout, encryption schemes, BLE protocols, transmitter bridges, and cross-system compatibility
    - `docs/30-design/nightscout-integration-guide.md` - Practical guide for app developers
    - `docs/60-research/controller-registration-protocol-proposal.md` - **v2** Controller Registration Protocol as Nightscout Core contract with OpenAPI schema, implementation roadmap, and resolved open questions
    - `docs/60-research/profile-model-evolution-proposal.md` - Desired vs observed split, capability tracking
    - `docs/90-decisions/adr-002-sync-identity-strategy.md` - Decision record on sync identity
    - `docs/90-decisions/adr-003-no-custom-credentials.md` - **NEW** Decision record explaining why Nightscout avoids custom username/password authentication in favor of identity federation and zero trust principles
- **`specs/`**: Houses normative definitions using OpenAPI specifications and JSON Schema, along with test fixtures.
- **`conformance/`**: Contains executable test scenarios and assertion definitions to validate system behavior against specifications.
- **`mapping/`**: Provides detailed interpretations and mappings for each AID project (Nightscout, Loop, AAPS, Trio), including cross-project comparison matrices.
- **`traceability/`**: Manages coordination control, including coverage matrices, identified gaps, and derived requirements.
- **`tools/`**: A suite of utilities for workspace management, validation, and testing (e.g., `bootstrap.py` for external repositories, `linkcheck.py`, `validate_fixtures.py`, `run_conformance.py`, `gen_coverage.py`, `gen_inventory.py` for artifact inventory).
  - See `docs/tooling-roadmap.md` for proposed future tooling improvements for agent-based SDLC workflows.
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
    - `DiaBLE` (diable): iOS/watchOS app for reading Libre sensors directly via NFC/Bluetooth.
    - `xdrip-js`: Node.js library for interfacing with Dexcom G5/G6 transmitters via BLE.
- **Caregiver/Follower Apps**:
    - `LoopFollow` (loopfollow): iOS/watchOS app for caregivers to monitor Loop/Trio/iAPS users via Nightscout with comprehensive alarms and remote override support.
    - `LoopCaregiver` (loopcaregiver): iOS companion app enabling full remote control (bolus, carbs, overrides) for Loop users via Nightscout Remote 2.0 API.