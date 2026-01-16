# AID Alignment Workspace

## Overview

The AID Alignment Workspace is a documentation and coordination project aimed at standardizing semantics, schemas, and conformance across multiple Automated Insulin Delivery (AID) systems, including Nightscout, Loop, AAPS, and Trio. Its primary purpose is to facilitate interoperability and ensure consistent data interpretation and behavior across these diverse platforms.

The project encompasses:
- **Normative definitions**: Specifies what "must be true" for data structures and system behavior.
- **Informative documentation**: Provides explanations, rationale, and cross-project comparisons.
- **Decision records**: Documents architectural and design decisions with their underlying tradeoffs.
- **Executable conformance tests**: Verifies that systems adhere to defined specifications.

This workspace seeks to improve the understanding, integration, and reliability of AID systems for users and developers alike by providing a centralized, version-controlled source of truth for critical system aspects.

## User Preferences

I want iterative development. Each iteration cycle should update:
1. Scenario backlog
2. Requirements snippet
3. Spec delta (schema changes)
4. Mapping notes (per project)
5. Conformance update
6. Gap/coverage update

## System Architecture

The workspace is structured to separate normative specifications from informative documentation and executable tests.

- **`docs/`**: Contains narrative documentation, including overviews, domain concepts, design proposals, implementation notes, research, and architecture decision records (ADRs). It also includes auto-generated files and shared snippets.
  - **UI/UX Decisions**: The documentation emphasizes clear structure and cross-referencing to enhance usability.
- **`specs/`**: Houses normative definitions like OpenAPI specifications and JSON Schema definitions, along with test fixtures.
  - **Technical Implementations**: Utilizes OpenAPI and JSON Schema for rigorous data model definition.
- **`conformance/`**: Contains executable test scenarios and assertion definitions to validate system behavior against specifications.
- **`mapping/`**: Provides detailed interpretations and mappings for each AID project (Nightscout, Loop, AAPS, Trio), including cross-project comparison matrices. This section focuses on how each system implements or relates to the common definitions.
- **`traceability/`**: Manages coordination control, including coverage matrices, identified gaps, and derived requirements.
- **`tools/`**: A suite of utilities for workspace management, validation, and testing, such as:
    - `bootstrap.py`: Manages cloning and updating external repositories, including handling git submodules.
    - `linkcheck.py`: Verifies internal and external code references.
    - `validate_fixtures.py`: Validates JSON fixtures against defined shape specifications.
    - `run_conformance.py`: Executes conformance assertions against scenarios.
    - `gen_coverage.py`: Generates coverage reports.
- **CI Integration**: A GitHub Actions workflow ensures continuous validation of Python syntax, link integrity, fixture validation, offline conformance tests, and coverage matrix generation.

## External Dependencies

The project integrates with and documents the following external Automated Insulin Delivery (AID) systems and related projects:

- **Nightscout Ecosystem**:
    - `cgm-remote-monitor` (crm): The core Nightscout CGM Remote Monitor.
    - `nightscout-connect` (ns-connect): Data bridge for CGM sources.
    - `nightscout-roles-gateway` (ns-gateway): Access control gateway for Nightscout.
    - `nightscout-reporter` (ns-reporter): PDF reporting tool for Nightscout data.
- **AID Systems**:
    - `LoopWorkspace` (loop): The Loop iOS closed-loop system.
    - `AndroidAPS` (aaps): The Android closed-loop system.
    - `Trio` (trio): The Trio iOS closed-loop system (formerly FreeAPS).
- **Algorithms**:
    - `oref0`: The OpenAPS reference algorithm (determine-basal.js).
    - `openaps`: The OpenAPS toolkit.
- **CGM/Monitoring Apps**:
    - `nightguard`: iOS/watchOS app for blood glucose monitoring via Nightscout.
    - `xdripswift` (xdrip4ios): iOS app for CGM data management and Nightscout sync.
    - `xDrip`: Android xDrip+ app for CGM data collection and Nightscout sync.