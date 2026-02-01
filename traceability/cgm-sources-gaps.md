# Cgm Sources Gaps

Domain-specific gaps extracted from gaps.md.
See [gaps.md](gaps.md) for the index.

---

### GAP-G7-001: G7 J-PAKE Full Specification Incomplete

**Scenario**: G7 Initial Pairing

**Description**: The J-PAKE (Password Authenticated Key Exchange by Juggling) protocol used by Dexcom G7 for initial pairing is not fully documented. The mathematical operations for key derivation are implemented in native libraries (keks, mbedtls) but the exact message formats and state machine are not fully understood.

**Source**: [Dexcom BLE Protocol Deep Dive](../docs/10-domain/dexcom-ble-protocol-deep-dive.md#g7-j-pake-authentication)

**Impact**:
- New G7 implementations must reverse-engineer or copy existing code
- Cannot verify correctness of implementations
- Security analysis is incomplete

**Possible Solutions**:
1. Detailed packet capture and analysis of J-PAKE phases
2. Reverse engineering of official Dexcom app
3. Collaboration with existing implementations (xDrip+, DiaBLE)

**Status**: Documentation effort

---

---

### GAP-G7-002: G7 Certificate Chain Undocumented

**Scenario**: G7 Initial Pairing

**Description**: The certificate exchange (opcode 0x0B) and proof of possession (opcode 0x0C) protocols used after J-PAKE are not fully documented. These establish long-term trust between the sensor and device.

**Source**: [DiaBLE DexcomG7.swift](../externals/DiaBLE/DiaBLE Playground.swiftpm/DexcomG7.swift)

**Impact**:
- Cannot implement G7 pairing from specification alone
- Certificate validation logic is unclear
- Security implications not fully analyzed

**Possible Solutions**:
1. Packet capture of certificate exchange
2. Analysis of certificate formats (likely X.509)
3. Documentation of signature verification

**Status**: Needs investigation

---

---

### GAP-G7-003: Service B Purpose Unknown

**Scenario**: BLE Protocol Completeness

**Description**: The secondary Bluetooth service (UUID: F8084532-849E-531C-C594-30F1F86A4EA5) with characteristics E (F8084533) and F (F8084534) is present on Dexcom transmitters but its purpose is unknown.

**Source**: [CGMBLEKit BluetoothServices.swift](../externals/LoopWorkspace/CGMBLEKit/CGMBLEKit/BluetoothServices.swift)

**Impact**:
- Potentially missing functionality
- May be used for firmware updates or diagnostics

**Possible Solutions**:
1. Packet capture during firmware updates
2. Reverse engineering of Dexcom app
3. Experimentation with characteristic reads/writes

**Status**: Low priority

---

---

### GAP-G7-004: Anubis Transmitter Extended Commands

**Scenario**: G6 Extended Transmitters

**Description**: "Anubis" G6 transmitters (maxRuntimeDays > 120) use extended commands at opcodes 0x3B and 0xF0xx that are not fully documented. These appear related to transmitter reset/restart functionality.

**Source**: [xdrip-js transmitter.js](../externals/xdrip-js/lib/transmitter.js)

**Impact**:
- Cannot fully support Anubis transmitter features
- Reset/extend functionality limited

**Possible Solutions**:
1. Analysis of xDrip+ Android implementation
2. Documentation of 0xF080 message format

**Status**: Low priority

---

---

### GAP-G7-005: G7 Encryption Info Format Unknown

**Scenario**: G7 Advanced Features

**Description**: The encryption info (opcode 0x38) and encryption status (opcode 0x0F) commands for G7 are present but the data format and purpose are unclear. May relate to encrypted data streams.

**Source**: [DiaBLE DexcomG7.swift](../externals/DiaBLE/DiaBLE Playground.swiftpm/DexcomG7.swift)

**Impact**:
- May be blocking access to additional data
- Security implications unknown

**Possible Solutions**:
1. Packet analysis of encryption commands
2. Cross-reference with official app behavior

**Status**: Needs investigation

---

## Carb Absorption Gaps

---

### GAP-CGM-NODE-001: Node.js 16+ EOL blocks upgrades

**Scenario**: share2nightscout-bridge Node compatibility

**Description**: The `package.json` engines field restricts to Node 8-16, all of which are end-of-life. This blocks cgm-remote-monitor upgrade to Node 22+ (PR #8357).

**Evidence**:
```json
"engines": {
  "node": "16.x || 14.x || 12.x || 10.x || 8.x"
}
```

**Impact**:
- Cannot upgrade Nightscout to Node 22+
- Security vulnerabilities in EOL Node versions
- Deployment platform compatibility issues

**Possible Solutions**:
1. Complete `wip/bewest/axios` branch migration
2. Deprecate in favor of cgm-remote-monitor `connect` module
3. Update engines field after dependency modernization

**Status**: Open - WIP branch exists

**Related**:
- [PR Analysis](../docs/10-domain/share2nightscout-bridge-pr-analysis.md)
- [GitHub Issue #61](https://github.com/nightscout/share2nightscout-bridge/issues/61)

---

---

### GAP-CGM-NODE-002: Deprecated `request` npm package

**Scenario**: share2nightscout-bridge dependency modernization

**Description**: The sole dependency `request` is deprecated since 2020 and has known vulnerabilities. No active maintenance.

**Evidence**:
```json
"dependencies": {
  "request": "^2.88.0"
}
```

**Impact**:
- Security vulnerabilities unpatched
- Node.js compatibility issues with newer versions
- npm audit warnings

**Possible Solutions**:
1. Migrate to `axios` (WIP branch exists)
2. Migrate to native `fetch` (Node 18+)
3. Migrate to `node-fetch` or `got`

**Status**: Open - WIP branch `wip/bewest/axios` in progress

**Related**:
- [PR Analysis](../docs/10-domain/share2nightscout-bridge-pr-analysis.md)

---

---

### GAP-CGM-NODE-003: No CI/CD pipeline

**Scenario**: share2nightscout-bridge automated testing

**Description**: The project uses `wercker.yml` but Wercker service is defunct. No GitHub Actions or other CI configured.

**Evidence**:
```
wercker.yml  # Defunct service
```

**Impact**:
- PRs not automatically tested
- No confidence in merge safety
- Manual testing burden

**Possible Solutions**:
1. Add GitHub Actions workflow
2. Add simple npm test action
3. Consider deprecation if connect module preferred

**Status**: Documented

**Related**:
- [PR Analysis](../docs/10-domain/share2nightscout-bridge-pr-analysis.md)

---

## Algorithm Conformance Gaps

---

### GAP-CGM-001: DiaBLE lacks treatment support

**Scenario**: Bi-directional treatment sync

**Description**: DiaBLE only uploads CGM entries to Nightscout and downloads server status. It cannot create, edit, or sync treatments (bolus, carbs, corrections). Users cannot log insulin or carbs directly from DiaBLE.

**Source**: [DiaBLE Nightscout Sync](../mapping/diable/nightscout-sync.md)

**Impact**:
- DiaBLE users must use another app for treatment logging
- No unified CGM + treatment workflow in DiaBLE
- Cannot use DiaBLE as standalone diabetes management app

**Possible Solutions**:
1. Add treatment API integration to DiaBLE
2. Accept DiaBLE as CGM-only producer (current behavior)
3. Integrate with iOS Shortcuts for treatment logging

**Status**: Informational (DiaBLE design choice)

**Related**:
- [DiaBLE Documentation](../mapping/diable/)
- [CGM Apps Comparison](../mapping/cross-project/cgm-apps-comparison.md)

---

---

### GAP-CGM-002: xdrip-js limited to Dexcom G5/G6

**Scenario**: CGM data collection for OpenAPS rigs

**Description**: xdrip-js only supports Dexcom G5 and G6 transmitters. It cannot read from Dexcom G7, Libre sensors, or bridge devices. Users with newer sensors cannot use xdrip-js-based solutions.

**Source**: [xdrip-js Documentation](../mapping/xdrip-js/)

**Impact**:
- OpenAPS rigs using Lookout/Logger limited to G5/G6
- No path for G7 users wanting DIY closed-loop on Raspberry Pi
- Libre users must use alternative solutions

**Possible Solutions**:
1. Implement G7 J-PAKE authentication in xdrip-js (complex)
2. Use alternative libraries for G7/Libre (e.g., cgm-remote-monitor bridge)
3. Accept limitation (G5/G6 still widely used)

**Status**: Informational (library scope)

**Related**:
- [xdrip-js BLE Protocol](../mapping/xdrip-js/ble-protocol.md)
- [CGM Apps Comparison](../mapping/cross-project/cgm-apps-comparison.md)

---

---

### GAP-CGM-003: Libre 3 encryption not fully documented

**Scenario**: Direct Libre 3 sensor reading

**Description**: DiaBLE documents partial Libre 3 support but notes that AES-128-CCM encryption with ECDH key agreement and Zimperium zShield anti-tampering are not fully cracked. DiaBLE can eavesdrop on BLE traffic but cannot independently decrypt sensor data.

**Source**: [DiaBLE CGM Transmitters](../mapping/diable/cgm-transmitters.md)

**Impact**:
- Full independent Libre 3 reading requires external decryption
- Must use trident.realm extraction from rooted devices
- DIY community lacks complete Libre 3 specification

**Possible Solutions**:
1. Continue reverse engineering efforts (Juggluco project)
2. Use LibreLinkUp cloud as alternative data source
3. Document known encryption parameters for community research

**Status**: Under investigation (community effort)

**Related**:
- [DiaBLE README](../externals/DiaBLE/README.md)
- [Libre 3 Technical Blog Post](https://frdmtoplay.com/freeing-glucose-data-from-the-freestyle-libre-3/)

---

---

### GAP-CGM-004: No standardized Dexcom BLE protocol specification

**Scenario**: Cross-platform CGM integration

**Description**: Dexcom BLE protocol is undocumented by the manufacturer. xdrip-js, DiaBLE, xDrip+, and xDrip4iOS each implement their own reverse-engineered versions. There are subtle differences in authentication handling, backfill parsing, and error recovery.

**Source**: [xdrip-js BLE Protocol](../mapping/xdrip-js/ble-protocol.md), [DiaBLE CGM Transmitters](../mapping/diable/cgm-transmitters.md)

**Impact**:
- Each implementation may have different bugs or limitations
- No authoritative source for protocol behavior
- G6 "Anubis" and G7 protocols add complexity

**Possible Solutions**:
1. Create community-maintained protocol specification
2. Cross-reference implementations to identify discrepancies
3. Accept implementation diversity (current state)

**Status**: Documentation effort → Partially resolved (see `docs/10-domain/dexcom-ble-protocol-deep-dive.md`)

**Related**:
- [xdrip-js BLE Protocol](../mapping/xdrip-js/ble-protocol.md)
- [DiaBLE Dexcom Support](../mapping/diable/cgm-transmitters.md)
- [Dexcom BLE Protocol Deep Dive](../docs/10-domain/dexcom-ble-protocol-deep-dive.md)

---

---

### GAP-CGM-005: Raw Values Not Uploaded by iOS

**Scenario**: Calibration validation, algorithm comparison

**Description**: iOS systems (Loop, Trio, xDrip4iOS) typically do not upload raw sensor values (`filtered`, `unfiltered`) to Nightscout. They rely on transmitter-calibrated readings.

**Impact**:
- Cannot recalibrate iOS-sourced readings
- Cannot compare raw vs calibrated values
- Limits retrospective analysis options

**Possible Solutions**:
1. iOS apps extract and upload raw values (requires transmitter protocol changes)
2. Accept limitation and document iOS vs Android differences
3. Use companion bridges (MiaoMiao) that expose raw values

**Status**: Under discussion (likely won't fix due to iOS CGM API limitations)

**Related**:
- [xDrip4iOS CGM Transmitters](../mapping/xdrip4ios/cgm-transmitters.md)
- [GAP-ENTRY-005](../docs/10-domain/entries-deep-dive.md#gap-summary)

---

---

### GAP-CGM-006: Follower Source Not Distinguished

**Scenario**: Latency analysis, data freshness assessment

**Description**: When CGM data is sourced from follower mode (Nightscout, Dexcom Share, LibreLinkUp), the follower source is not consistently indicated in entries.

**Impact**:
- Cannot distinguish direct sensor data from cloud-sourced data
- Cannot assess data latency (follower modes have 1-5+ minute delays)
- Duplicate detection between direct and follower sources is complex

**Possible Solutions**:
1. Append "-follower" to `device` field when in follower mode
2. Add `sourceType` field: `direct` | `follower` | `cloud`
3. Include original source URL in metadata

**Status**: Under discussion

**Related**:
- [xDrip4iOS Follower Modes](../mapping/xdrip4ios/follower-modes.md)
- [xDrip+ Data Sources - Cloud Followers](../mapping/xdrip-android/data-sources.md#cloud-follower-sources)

---

---

### GAP-LF-001: Alarm Configuration Not Synced

**Scenario**: Multi-Caregiver Coordination

**Description**: LoopFollow alarm configurations are stored locally only. There is no mechanism to sync alarm settings to Nightscout or between caregiver devices. Each LoopFollow instance must be configured independently.

**Source**: `loopfollow:LoopFollow/Alarm/Alarm.swift` - Stored via `Storage.shared.alarms`

**Impact**:
- Duplicate configuration effort for multiple caregivers
- No centralized alarm management
- Alarm settings lost if device is reset

**Possible Solutions**:
1. Store alarm configuration in Nightscout profile store
2. Implement iCloud sync for alarm settings
3. Export/import configuration as JSON

**Status**: Under discussion

---

---

### GAP-LF-002: No Alarm History or Audit Log

**Scenario**: Alarm Effectiveness Review

**Description**: LoopFollow does not maintain a history of triggered alarms. Once an alarm is snoozed or cleared, there is no record of when it fired, what triggered it, or how it was resolved.

**Source**: `loopfollow:LoopFollow/Alarm/AlarmManager.swift` - No history persistence

**Impact**:
- Cannot analyze alarm patterns over time
- No audit trail for missed alarms
- Cannot tune alarm thresholds based on historical data

**Possible Solutions**:
1. Log alarm events to Nightscout treatments collection
2. Maintain local SQLite database of alarm history
3. Upload alarm events as announcements

**Status**: Under discussion

---

---

### GAP-LF-003: Prediction Data Unavailable for Trio

**Scenario**: Predictive Low Glucose Alarm

**Description**: LoopFollow's predictive low alarm relies on prediction data from deviceStatus. While Loop includes `predBgs` in deviceStatus, Trio may not include this data consistently, limiting predictive alarm effectiveness.

**Source**: `loopfollow:LoopFollow/Alarm/AlarmCondition/LowBGCondition.swift#L36-L51`

**Impact**:
- Predictive alarms only work reliably with Loop
- Trio users get delayed low alerts (reactive only)
- Feature parity gap between Loop and Trio monitoring

**Possible Solutions**:
1. Verify Trio prediction data availability
2. Document which alarms work with which AID systems
3. Implement client-side prediction from recent BG data

**Status**: Under discussion

---

---

### GAP-LF-004: No Multi-Caregiver Alarm Acknowledgment

**Scenario**: Caregiver Team Coordination

**Description**: When multiple caregivers use LoopFollow to monitor the same looper, there is no coordination for alarm acknowledgment. Each caregiver sees independent alarms, and snoozing on one device doesn't affect others.

**Source**: `loopfollow:LoopFollow/Alarm/AlarmManager.swift#L155-L169` - Local snooze only

**Impact**:
- Multiple caregivers may respond to same alarm
- No visibility into who acknowledged an alarm
- Risk of alarm fatigue from duplicate notifications

**Possible Solutions**:
1. Sync alarm acknowledgment via Nightscout
2. Implement shared snooze state
3. Use Nightscout announcements for alarm coordination

**Status**: Under discussion

---

---

### GAP-LF-005: No Command Status Tracking

**Scenario**: Remote Command Reliability

**Description**: LoopFollow remote commands (TRC, Loop APNS, Nightscout) are fire-and-forget. After sending a command, there is no mechanism to verify it was received or executed. Users must check the looper's app or Nightscout to confirm.

**Source**: 
- `loopfollow:LoopFollow/Remote/TRC/PushNotificationManager.swift` - Completion only indicates APNS delivery
- `loopfollow:LoopFollow/Remote/Nightscout/TrioNightscoutRemoteView.swift` - No status polling

**Impact**:
- Users may not know if command succeeded
- No retry mechanism for failed commands
- Commands may be sent multiple times if user is uncertain

**Possible Solutions**:
1. Implement TRC return notification fully
2. Poll Nightscout for command status (like LoopCaregiver Remote 2.0)
3. Show pending command status in UI

**Status**: Under discussion

---

---

### GAP-LF-006: No Command History or Audit Log

**Scenario**: Remote Command Audit

**Description**: LoopFollow does not maintain a history of commands sent. There is no log of when commands were sent, what parameters were used, or whether they succeeded.

**Source**: No command history persistence in codebase

**Impact**:
- Cannot audit who sent what command when
- No visibility for reviewing past remote actions
- Cannot diagnose command failures retroactively

**Possible Solutions**:
1. Maintain local command history database
2. Log commands to Nightscout
3. Display recent commands in UI

**Status**: Under discussion

---

---

### GAP-LF-007: TRC Return Notification Not Fully Implemented

**Scenario**: Command Confirmation

**Description**: TRC `CommandPayload` includes a `ReturnNotificationInfo` structure for Trio to send confirmation back to LoopFollow, but this feature does not appear to be fully implemented. The return notification fields are sent but there is no handler for incoming confirmations.

**Source**: 
- `loopfollow:LoopFollow/Remote/TRC/PushMessage.swift#L32-L48` - ReturnNotificationInfo defined
- No corresponding notification receiver implementation found

**Impact**:
- Users cannot get push confirmation of command execution
- Return notification infrastructure is unused
- Partial implementation may confuse future developers

**Possible Solutions**:
1. Implement return notification handler
2. Remove unused ReturnNotificationInfo structure
3. Document feature as planned but unimplemented

**Status**: Under discussion

---

---

### GAP-LF-008: Nightscout Remote Lacks OTP Security

**Scenario**: Temp Target Security

**Description**: LoopFollow's Nightscout-based temp target commands rely solely on API token authentication. Unlike Loop APNS (TOTP) or TRC (encryption), there is no additional security layer.

**Source**: `loopfollow:LoopFollow/Remote/Nightscout/TrioNightscoutRemoteView.swift#L48-L52`

**Impact**:
- Anyone with the API token can send temp targets
- No time-based protection against replay
- Inconsistent security model across remote types

**Possible Solutions**:
1. Add OTP support for Nightscout commands
2. Document security limitations
3. Recommend TRC for secure remote control

**Status**: Under discussion

---

---

### GAP-LF-009: No Unified Command Abstraction

**Scenario**: Multi-Protocol Remote Control

**Description**: LoopFollow implements three distinct remote protocols (Loop APNS, TRC, Nightscout) with separate codepaths, data structures, and UIs. There is no unified abstraction for sending commands.

**Source**: 
- `loopfollow:LoopFollow/Remote/RemoteViewController.swift#L33-L60` - Branched view logic
- Separate command implementations per protocol

**Impact**:
- Difficulty adding new commands requires changes in multiple places
- Inconsistent feature support across protocols
- Code duplication for similar functionality

**Possible Solutions**:
1. Create protocol-agnostic command abstraction
2. Implement command factory pattern
3. Unify UI with backend protocol selection

**Status**: Under discussion

---

## Delegation and Agent Gaps

> **See Also**: [Progressive Enhancement Framework](../docs/10-domain/progressive-enhancement-framework.md) for L7-L9 layer definitions.
> **See Also**: [Capability Layer Matrix](../mapping/cross-project/capability-layer-matrix.md) for system-by-system analysis.

---

### GAP-LIBRE-001: Libre 3 Cloud Decryption Dependency

**Scenario**: Libre 3 Direct Connection

**Description**: Libre 3 uses fully encrypted BLE communication with ECDH key exchange. Current open-source implementations (DiaBLE) can connect and receive encrypted data, but full decryption without cloud services is incomplete. Some functionality requires reverse-engineering closed-source libraries or relying on cloud-based OOP servers.

**Source**: `externals/DiaBLE/DiaBLE/Libre3.swift`

**Impact**:
- Libre 3 support is experimental/partial in open-source apps
- Users must rely on LibreLink app or patched solutions
- No offline-only Libre 3 reading capability

**Possible Solutions**:
1. Complete reverse-engineering of Libre 3 security protocol
2. Document cloud API for OOP decryption
3. Wait for community security research

**Status**: Under discussion

---

---

### GAP-LIBRE-002: Libre 2 Gen2 Session-Based Authentication

**Scenario**: Libre 2 Gen2 (US) NFC/BLE Access

**Description**: Libre 2 Gen2 sensors require session-based authentication that differs from EU Libre 2. The authentication involves challenge-response with proprietary key derivation functions that are only partially documented.

**Source**: `externals/DiaBLE/DiaBLE/Libre2Gen2.swift`

**Impact**:
- Gen2 support is limited on iOS (Loop, Trio)
- xDrip+ Android has better Gen2 support via native library
- Cross-platform parity is not achieved

**Possible Solutions**:
1. Port xDrip+ Gen2 implementation to Swift
2. Document session protocol completely
3. Use bridge transmitters (MiaoMiao, Bubble) for Gen2

**Status**: Under discussion

**Related Requirements**: REQ-LIBRE-004

---

---

### GAP-LIBRE-003: Transmitter Bridge Firmware Variance

**Scenario**: MiaoMiao/Bubble Data Reliability

**Description**: Third-party transmitter bridges (MiaoMiao, Bubble, etc.) have varying firmware versions with different capabilities. Firmware differences affect:
- Libre 2 decryption support
- PatchInfo availability (older firmware may not include it)
- Battery reporting accuracy

**Source**: `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Libre/MiaoMiao/CGMMiaoMiaoTransmitter.swift`

**Impact**:
- Same transmitter may behave differently based on firmware
- Users may need firmware updates for Libre 2 support
- Documentation becomes version-dependent

**Possible Solutions**:
1. Document minimum firmware versions per feature
2. Implement firmware detection and user notification
3. Provide firmware update instructions in apps

**Status**: Documentation needed

**Related Requirements**: REQ-LIBRE-001

---

---

### GAP-LIBRE-004: Calibration Algorithm Not Synced

**Scenario**: Cross-App Glucose Comparison

**Description**: The factory calibration parameters (i1-i6) extracted from FRAM are not synced to Nightscout. Different apps may use different OOP servers or local algorithms, producing slightly different glucose values from the same raw data.

**Source**: `externals/LoopWorkspace/LibreTransmitter/LibreSensor/SensorContents/SensorData.swift#calibrationData`

**Impact**:
- Same sensor reading may show different values in different apps
- No way to verify calibration consistency post-hoc
- Research/comparison compromised

**Possible Solutions**:
1. Add calibration info to Nightscout entries
2. Standardize on a single calibration algorithm
3. Document calibration source in devicestatus

**Status**: Under discussion

**Related Requirements**: REQ-LIBRE-002, REQ-LIBRE-006

---

---

### GAP-LIBRE-005: Sensor Serial Number Not in Nightscout Entries

**Scenario**: Multi-Sensor Tracking

**Description**: Nightscout entries have `device` field but no dedicated sensor serial number field. The 10-character Libre serial (e.g., "3MH001ABCD") is not consistently captured, making it difficult to track readings across sensor changes.

**Impact**:
- Cannot query "all readings from sensor X"
- Sensor session boundaries unclear
- Harder to correlate sensor failures with readings

**Possible Solutions**:
1. Add `sensorSerial` field to entries
2. Use `device` field with consistent format
3. Track in separate sensor metadata collection

**Status**: Under discussion

**Related Requirements**: REQ-INTEROP-003

---

---

### GAP-LIBRE-006: NFC vs BLE Data Latency Difference

**Scenario**: Real-Time Glucose Display

**Description**: Libre sensors update FRAM trend data every minute but history every 15 minutes. BLE streaming provides sparse trend (minutes 0, 2, 4, 6, 7, 12, 15) plus 3 history values, while NFC provides full 16 trend + 32 history. The data available via each method differs.

**Source**: `externals/DiaBLE/DiaBLE/Libre2.swift#parseBLEData`

**Impact**:
- NFC scans may fill gaps BLE misses
- Hybrid NFC+BLE strategies needed for complete data
- Backfill logic required

**Possible Solutions**:
1. Document exact data availability per method
2. Implement smart gap-filling in apps
3. Prefer NFC for historical data, BLE for real-time

**Status**: Documented

---

## Timezone and DST Gaps

---

### GAP-SESSION-001: Session Events Not Standardized

**Description**: Only xDrip+ consistently uploads sensor start/stop events to Nightscout. Loop and AAPS do not upload session lifecycle events.

**Affected Systems**: Loop, AAPS, Nightscout analytics

**Impact**:
- Cannot track sensor history from Nightscout alone
- Analytics cannot correlate readings with sensor age
- No cross-system session awareness

**Remediation**: Define standard `Sensor Start`/`Sensor Stop` treatment types with required fields.

**Source**: `docs/10-domain/cgm-session-handling-comparison.md`

---

### GAP-SESSION-002: Calibration State Not Exposed

**Description**: Loop has a rich 17-state calibration state machine (CalibrationState.swift), but this state is not exposed to Nightscout or other systems.

**Affected Systems**: Loop, Nightscout, analytics tools

**Impact**:
- Cannot diagnose calibration issues remotely
- No visibility into warmup progress
- Analytics cannot distinguish calibration errors from sensor failures

**Remediation**: Add `calibrationState` field to devicestatus.

**Source**: `docs/10-domain/cgm-session-handling-comparison.md`

---

### GAP-SESSION-003: Pluggable Calibration Algorithms Unique to xDrip+

**Description**: Only xDrip+ supports user-selectable calibration algorithms (XDripOriginal, Native, Datricsae, FixedSlope, LastSevenUnweighted). Loop and AAPS use native sensor calibration only.

**Affected Systems**: xDrip+, Loop, AAPS

**Impact**:
- Users switching from xDrip+ may lose preferred algorithm
- No cross-system calibration comparison possible
- Algorithm choice not preserved in Nightscout

**Remediation**: Document as intentional difference; xDrip+'s flexibility is a feature not requiring standardization.

**Source**: `docs/10-domain/cgm-session-handling-comparison.md`

---

## Nocturne Connector Gaps

---

### GAP-CONNECTOR-001: No xDrip+ Connector in Nocturne

**Description**: Nocturne's 8 native connectors do not include xDrip+. xDrip+ has a local API but it's designed for same-device communication, not cloud sync.

**Affected Systems**: Nocturne, xDrip+

**Impact**:
- xDrip+ users must use Nightscout connector as intermediary
- Data flow: xDrip+ → Nightscout → Nocturne (extra hop)

**Remediation**: Document as acceptable; xDrip+ → NS sync is mature path.

**Source**: `mapping/nocturne/connectors.md`

---

### GAP-CONNECTOR-002: No Eversense Connector in Nocturne

**Description**: Nocturne lacks an Eversense connector. Eversense has limited API availability and the implantable sensor market is smaller.

**Affected Systems**: Nocturne, Eversense users

**Impact**:
- Eversense users cannot sync directly to Nocturne
- Must use bridge or xDrip+ intermediary

**Remediation**: Low priority; limited user base. Monitor for API availability.

**Source**: `mapping/nocturne/connectors.md`

---

## DiaBLE Interoperability Gaps

---

### GAP-DIABLE-002: No Trend Direction Upload to Nightscout

**Description**: DiaBLE does not upload trend direction to Nightscout. The source code has a TODO comment for direction calculation, but it is not implemented.

**Affected Systems**: DiaBLE, Nightscout, follower apps

**Impact**:
- Nightscout graphs lack trend arrows for DiaBLE-sourced data
- Follower apps (LoopFollow, Nightguard) cannot display direction
- Missing trend data for AID systems consuming from Nightscout

**Remediation**: Implement direction calculation from rate of change data already available in sensor readings.

**Source**: `externals/DiaBLE/DiaBLE/Nightscout.swift:163`

---

### GAP-DIABLE-003: No Nightscout v3 API Support

**Description**: DiaBLE uses only Nightscout v1 API endpoints (`api/v1/entries`). No support for v3 features like identifier-based sync or atomic operations.

**Affected Systems**: DiaBLE, Nightscout

**Impact**:
- Relies on date-based deduplication rather than proper sync identity
- No atomic upsert operations
- May create duplicates if timing varies between uploads

**Remediation**: Add v3 API support with proper `identifier` field handling for robust deduplication.

**Source**: `externals/DiaBLE/DiaBLE/Nightscout.swift:40-45`

---

**Description**: Medtronic CareLink has no official API. Nocturne's MiniMed connector must use web scraping, which is fragile.

**Affected Systems**: Nocturne, Medtronic users

**Impact**:
- Connector breaks when CareLink UI changes
- No guaranteed data availability
- May violate terms of service

**Remediation**: Document fragility; consider deprecation warning.

**Source**: `mapping/nocturne/connectors.md`

---


### GAP-SESSION-004: No Standard Sensor Session Event Schema

**Description**: Each CGM system (xDrip+, DiaBLE, Loop, AAPS) tracks sensor sessions differently. There is no common Nightscout API schema for session start/stop/change events.

**Affected Systems**: xDrip+, DiaBLE, Loop, AAPS, Nightscout

**Impact**:
- Session start/stop times don't sync reliably between systems
- Different session identity patterns cause confusion
- Caregivers can't see consistent sensor change history

**Remediation**: Define standard `Sensor Session Start/Stop` treatment types with fields for session identity, warm-up duration, and expected lifetime.

**Source**: `docs/10-domain/cgm-session-handling-deep-dive.md`

---

### GAP-SESSION-005: Warm-up Period Not Uploaded to Nightscout

**Description**: CGM sensors have varying warm-up periods (30min to 2hr) but this duration is not included in Nightscout data uploads.

**Affected Systems**: xDrip+, DiaBLE, Loop, AAPS, Nightscout

**Impact**:
- Downstream consumers can't determine if readings are during warm-up
- No filtering of potentially inaccurate early readings
- Caregivers may see unreliable data without warning

**Remediation**: Add `warmupDuration` field to CGM entries or devicestatus; include `isWarmingUp` flag on readings during warm-up.

**Source**: `docs/10-domain/cgm-session-handling-deep-dive.md`

**Related Requirements**: REQ-SPEC-002, REQ-PLUGIN-001

---

### GAP-SESSION-006: DiaBLE Has No Session Upload Capability

**Description**: DiaBLE tracks sensor session states internally (`SensorState` enum with notActivated, warmingUp, active, expired, shutdown, failure) but does not upload session events to Nightscout.

**Affected Systems**: DiaBLE, Nightscout

**Impact**:
- Sensor changes in DiaBLE aren't visible in Nightscout
- No session history for DiaBLE users
- Caregivers can't see sensor lifecycle events

**Remediation**: Add session event upload to DiaBLE Nightscout integration using standard treatment types.

**Source**: `docs/10-domain/cgm-session-handling-deep-dive.md`

**Related Requirements**: REQ-SYNC-001, REQ-BRIDGE-003

---

### GAP-SESSION-007: Calibration State Not Synchronized

**Description**: xDrip+ and Loop track detailed calibration states (25+ states including WarmingUp, NeedsFirstCalibration, CalibrationConfused, etc.) but this state information isn't shared via Nightscout.

**Affected Systems**: xDrip+, Loop, AAPS, Nightscout

**Impact**:
- Other systems can't warn users about calibration issues
- No visibility into calibration problems from follower apps
- Caregivers can't see when calibration is needed

**Remediation**: Add calibration state to devicestatus or create dedicated calibration event type with state details.

**Source**: `docs/10-domain/cgm-session-handling-deep-dive.md`

**Related Requirements**: REQ-ERR-002, REQ-PLUGIN-001

---


### GAP-XDRIP-001: No Nightscout v3 API Support

**Description**: xDrip+ uses only Nightscout v1 API endpoints. No support for v3 identifier-based sync, atomic upserts, or modern API features.

**Affected Systems**: xDrip+, Nightscout

**Impact**:
- Relies on UUID lookup for updates/deletes rather than atomic upserts
- No identifier field usage for deduplication
- Less efficient sync protocol

**Remediation**: Add v3 API support with proper identifier-based sync.

**Source**: `mapping/xdrip/nightscout-fields.md`

---

### GAP-XDRIP-002: Activity Data Schema Not Standardized

**Description**: Heart rate, steps, and motion uploads use `/api/v1/activity` endpoint with xDrip+-specific schema. This is not a core Nightscout collection.

**Affected Systems**: xDrip+, Nightscout, follower apps

**Impact**:
- Activity data may not be visible in all Nightscout frontends
- No standard for other apps to upload activity data
- Heart rate especially useful for caregivers monitoring exercise

**Remediation**: Standardize activity data schema in Nightscout core.

**Source**: `mapping/xdrip/nightscout-fields.md`

---

### GAP-XDRIP-003: Device String Format Not Machine-Parseable

**Description**: xDrip+ device string format `"xDrip-{method} {source_info}"` mixes app name, collection method, and source info in free-form text.

**Affected Systems**: xDrip+, Nightscout, analytics

**Impact**:
- Difficult to programmatically identify CGM source type from device field
- Analytics/reporting can't reliably segment by data source
- Inconsistent with structured device identifiers in other apps

**Remediation**: Consider structured device identifier format like `xDrip://{method}/{source}`.

**Source**: `mapping/xdrip/nightscout-fields.md`

---

---

## xdrip-js Gaps

---

### GAP-XDRIPJS-001: No G7 Support

**Description**: xdrip-js only supports Dexcom G5 and G6 transmitters. G7 uses J-PAKE authentication which is not implemented.

**Affected Systems**: xdrip-js, Lookout, OpenAPS rigs using xdrip-js

**Impact**:
- Users with G7 cannot use xdrip-js-based solutions
- Forces migration to xDrip+ on Android or Dexcom ONE
- Limits longevity of Raspberry Pi-based CGM receivers

**Remediation**: Implement J-PAKE authentication per GAP-G7-001.

**Source**: `externals/xdrip-js/lib/transmitter.js`

**Related**: GAP-CGM-002

---

### GAP-XDRIPJS-002: Deprecated BLE Library (noble)

**Description**: The project depends on a forked version of noble, which is no longer maintained. The npm noble package was last updated in 2018.

**Affected Systems**: xdrip-js, any Node.js BLE application

**Impact**:
- Compatibility issues with newer Bluetooth stacks
- Security vulnerabilities in unmaintained code
- Installation difficulties on modern Node.js versions

**Source**: `externals/xdrip-js/package.json:18`

**Remediation**: Migrate to @abandonware/noble or node-ble.

---

### GAP-XDRIPJS-003: No Direct Nightscout Integration

**Description**: xdrip-js is a library only; it does not upload to Nightscout directly. Users must use Lookout or Logger client apps.

**Affected Systems**: xdrip-js users

**Impact**:
- Additional software layer required
- Lookout/Logger may have their own bugs
- No standardized upload format

**Remediation**: Add optional Nightscout uploader module or document standard format.

**Source**: `externals/xdrip-js/README.md`

---

### GAP-XDRIPJS-004: Trend-to-Direction Mapping Not Standardized

**Description**: xdrip-js provides numeric trend (mg/dL per 10 min), but Nightscout expects string direction. The conversion thresholds vary between implementations.

**Affected Systems**: xdrip-js → Nightscout data flow

**Impact**:
- Inconsistent trend arrows across clients
- No authoritative mapping table
- Potential for clinical confusion

**Source**: Not defined in xdrip-js; left to client apps

**Remediation**: Define standard mapping in Nightscout entries spec.

---


## Libre 3 Protocol Gaps

---

### GAP-CGM-030: Libre 3 Direct BLE Access Blocked

**Description**: Libre 3 uses ECDH encryption that requires Abbott private keys. Third-party apps cannot decrypt BLE data without using proprietary libraries.

**Affected Systems**: DiaBLE, xDrip+, xdripswift, AAPS, Loop (via bridges)

**Impact**:
- Users must run official Abbott app
- Data delayed through LibreLinkUp (1-5 min)
- No offline/direct sensor access
- Privacy concerns (data through Abbott servers)

**Current Workarounds**:
1. LibreLinkUp API polling (1-5 min delay)
2. Juggluco with extracted native library (legal concerns)
3. Eavesdrop mode (requires official app running)

**Source**: `DiaBLE/Libre3.swift:713-782` - eavesdrop logic

**Status**: Open - No known legal solution

---

### GAP-CGM-031: Libre 3 NFC Limited to Activation

**Description**: Unlike Libre 1/2, Libre 3 NFC cannot read glucose history. NFC is only used for initial activation and BLE PIN retrieval.

**Affected Systems**: All NFC-based readers (DiaBLE, xDrip+)

**Impact**:
- Cannot scan sensor for retrospective data
- Must rely on BLE (which is encrypted)
- No manual scan fallback

**Source**: `DiaBLE/Libre3.swift:832-848` - activation commands only

**Status**: Open - Hardware/firmware limitation

---

### GAP-CGM-032: LibreLinkUp API Dependency

**Description**: Third-party apps must use LibreLinkUp API as data source for Libre 3, creating dependency on Abbott cloud infrastructure.

**Affected Systems**: xdripswift, nightscout-librelink-up, AAPS

**Impact**:
- Internet required for glucose data
- Subject to API changes/deprecation (see GAP-LIBRELINK-001)
- Privacy concerns (all data through Abbott servers)
- Latency (1-5 minutes vs real-time BLE)
- No local-only operation possible

**Source**: `xdripswift/Libre3HeartBeatBluetoothTransmitter.swift:75-80`

**Status**: Open - Architectural limitation

---

### GAP-CGM-033: AAPS Triple Arrow Support

**Description:** AAPS supports TRIPLE_UP and TRIPLE_DOWN trend arrows, but Nightscout has no equivalent. These are displayed as "X" in AAPS.

**Source:** `externals/AndroidAPS/core/data/src/main/kotlin/app/aaps/core/data/model/TrendArrow.kt:5,13`

**Impact:** Extreme rate of change data may be lost when syncing to Nightscout.

**Remediation:** Consider adding optional TRIPLE_UP (0) and TRIPLE_DOWN (10) to Nightscout DIRECTIONS.

### GAP-CGM-034: Libre Trend Arrow Granularity

**Description:** Libre sensors provide only 6 trend levels vs Dexcom's 9. DiaBLE uses Libre's native enum which doesn't distinguish between SingleUp/FortyFiveUp or SingleDown/FortyFiveDown.

**Source:** `externals/DiaBLE/DiaBLE/App.swift:94-112`

**Impact:** Trend precision is reduced when using Libre sensors through DiaBLE.

**Remediation:** When syncing Libre data to Nightscout, map `rising` to `FortyFiveUp` and `falling` to `FortyFiveDown` for conservative display.
