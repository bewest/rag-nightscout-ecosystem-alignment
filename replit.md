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
        - **Comprehensive documentation**: See `mapping/nightguard/` for detailed analysis.
        - **Role**: Pure consumer/follower app (no CGM connection).
        - **Unique features**: Advanced alarm system (smart snooze, prediction, edge detection, persistent high), yesterday overlay chart, CAGE/SAGE/BAGE tracking, Loop integration (IOB/COB/temp basal), 3 widget types, Apple Watch app with complications.
        - **Primary API**: Uses `/api/v2/properties` (unlike other apps using `/api/v1/entries`).
        - **Key source files**: `external/NightscoutService.swift` (~1,377 lines), `domain/AlarmRule.swift` (~373 lines), `external/NightscoutCacheService.swift` (~330 lines).
    - `xdripswift` (xdrip4ios): iOS app for CGM data management and Nightscout sync.
        - **Comprehensive documentation**: See `mapping/xdrip4ios/` for detailed analysis.
        - **Role**: CGM producer + consumer with direct Bluetooth connection.
        - **Unique features**: Multi-source follower (Nightscout, LibreLinkUp, DexcomShare), treatment sync, HealthKit integration.
    - `xDrip`: Android xDrip+ app for CGM data collection and Nightscout sync.
        - **Comprehensive documentation**: See `mapping/xdrip-android/` for detailed analysis.
        - **Unique features**: Local web server (port 17580), multi-insulin tracking, 20+ data sources, smart pen integrations, pluggable calibration algorithms, Tidepool/InfluxDB/MongoDB direct upload.
        - **Key source files**: `models/BgReading.java` (~2,394 lines), `models/Treatments.java` (~1,436 lines), `utilitymodels/NightscoutUploader.java` (~1,470 lines), `utilitymodels/UploaderQueue.java` (~557 lines).

## Recent Analysis Documents

### DeviceStatus Structure Deep Dive (2026-01-17)

Comprehensive field mapping of the Nightscout `devicestatus` collection across AID systems:
- **Location**: `docs/10-domain/devicestatus-deep-dive.md`
- **Key findings**:
  - Loop uses flat `loop` object with single combined prediction array
  - oref0-based systems (Trio, AAPS) use nested `openaps` object with 4 prediction curves (IOB, COB, UAM, ZT)
  - Duration units differ: Loop uses seconds, oref0 uses minutes
  - `openaps.enacted` is null in open loop mode
  - `predBGs` can appear under either `suggested` or `enacted` (Trio strips from older)
- **Analytics helpers**: JavaScript normalization functions for cross-system data extraction
- **New gaps**: GAP-DS-001 through GAP-DS-004 (effect timelines, prediction incompatibility, duration units, algorithm transparency)
- **Cross-references**: Added links from Loop, Trio, AAPS nightscout-sync docs

### AID Controller Sync Patterns (2026-01-17)

Deep analysis of how Trio, Loop, and AAPS synchronize with Nightscout:
- **Location**: `mapping/cross-project/aid-controller-sync-patterns.md`
- **Key findings**:
  - Trio uses API v1 with `enteredBy` filtering for deduplication
  - Loop uses `syncIdentifier` UUID but POST-only (potential duplicates)
  - AAPS uses API v3 with `identifier` + composite pump key
  - No unified sync identity across controllers (GAP-003)
  - DeviceStatus structure differs between Loop and oref0-based systems
- **Conformance tests**: `conformance/assertions/sync-deduplication.yaml`
- **New requirements**: REQ-030 through REQ-035 (sync identity, dedup, conflict detection)
- **New gaps**: GAP-SYNC-004 (override sync), GAP-SYNC-005 (algorithm params)

### Profile/Therapy Settings Comparison (2026-01-17)

Comprehensive cross-system analysis of profile and therapy settings structures:
- **Location**: `docs/60-research/profile-therapy-settings-comparison.md`
- **Key findings**:
  - Loop uses `TherapySettings` with `RepeatingScheduleValue<T>` (startTime in seconds)
  - AAPS uses `ProfileSwitch` entity with duration-based `Block` arrays (`duration=0` = permanent)
  - Trio fetches profiles from Nightscout (`FetchedNightscoutProfile`) - download only
  - Nightscout uses `{time, timeAsSeconds, value}` format with `moment-tz` processing
  - Timezone handling differs: Loop uses `TimeZone` object (DST-aware), AAPS uses fixed `utcOffset` (GAP-TZ-001)
  - Sync directions: Loop upload-only (optional), AAPS bidirectional, Trio download-only
- **Terminology matrix updates**: New sections for Profile Data Structures, Timezone Handling, and Profile Sync Direction
- **New gaps**: GAP-TZ-001 (AAPS DST), GAP-PROFILE-001 through 004 (format transformation, semantic loss, sync identity)

### Treatments Collection Deep Dive (2026-01-17)

Comprehensive field-by-field mapping of treatment events (boluses, carbs, temp basals) across AID systems:
- **Location**: `docs/10-domain/treatments-deep-dive.md`
- **Key findings**:
  - Loop uses `DoseEntry` (bolus/temp basal) and `StoredCarbEntry` with `syncIdentifier` UUID
  - AAPS uses separate `Bolus`, `Carbs`, `TemporaryBasal` entities with composite `InterfaceIDs`
  - Trio inherits LoopKit models, uploads via `NightscoutTreatment`
  - xDrip+ has unique multi-insulin tracking via `insulinJSON` (InsulinInjection array)
  - Critical unit differences: absorption time (Loop/Trio: seconds, NS: minutes), duration (AAPS: ms, NS: minutes)
  - AAPS SMBs upload as `eventType: Correction Bolus` with `type: SMB` field (no explicit SMB eventType in NS)
  - Loop uses POST-only (potential duplicates on retry), xDrip+ uses PUT upsert
- **Conformance tests**: `conformance/assertions/treatment-sync.yaml` with 11 test scenarios
- **New requirements**: REQ-040 through REQ-046 (amount preservation, timestamp accuracy, duration normalization, sync identity)
- **New gaps**: GAP-TREAT-001 through GAP-TREAT-007 (unit mismatches, SMB representation, split boluses, duplicate uploads, retroactive edits, eCarbs support)
- **Terminology matrix updates**: New Treatment Data Models section with bolus, carb, and temp basal field mappings