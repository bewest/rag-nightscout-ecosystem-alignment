# CGM Sources Domain Traceability Matrix

> **Generated**: 2026-02-01  
> **Updated**: 2026-02-01 (cycle 91 - BLE assertions added)  
> **Domain**: CGM Sources  
> **Purpose**: REQ↔GAP↔Assertion cross-reference matrix

---

## Summary

| Metric | Count |
|--------|-------|
| Requirements | 18 |
| Gaps | 52 |
| REQs with assertion coverage | 6 (33%) |
| Uncovered REQs | 12 (67%) |
| Uncovered GAPs | 49 (94%) |

**Status**: BLE protocol assertions added (cycle 91). Libre protocol assertions pending.

---

## Requirements Inventory

### BLE Protocol Requirements (6)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-BLE-001 | Message CRC Validation | GAP-G7-001 | ✅ ble-protocol.yaml (2) |
| REQ-BLE-002 | Authentication Before Data Access | GAP-G7-002 | ✅ ble-protocol.yaml (2) |
| REQ-BLE-003 | Glucose Value Extraction | - | ✅ ble-protocol.yaml (2) |
| REQ-BLE-004 | Trend Rate Conversion | GAP-CGM-034 | ✅ ble-protocol.yaml (2) |
| REQ-BLE-005 | Timestamp Calculation | - | ✅ ble-protocol.yaml (2) |
| REQ-BLE-006 | Algorithm State Interpretation | - | ✅ ble-protocol.yaml (3) |

### Bridge/Connector Requirements (6)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-BRIDGE-001 | v3 API Support for Bridge Applications | GAP-XDRIP-001, GAP-DIABLE-003 | ❌ None |
| REQ-BRIDGE-002 | Client-Side Sync Identity Generation | - | ❌ None |
| REQ-BRIDGE-003 | Complete Collection Coverage | - | ❌ None |
| REQ-CONNECT-001 | XState Machine Testability | - | ❌ None |
| REQ-CONNECT-002 | Source Transform Standardization | GAP-XDRIPJS-004 | ❌ None |
| REQ-CONNECT-003 | Exponential Backoff on Failure | - | ❌ None |

### Libre Protocol Requirements (6)

| Requirement | Description | Gap Links | Assertions |
|-------------|-------------|-----------|------------|
| REQ-LIBRE-001 | Sensor Type Detection from PatchInfo | - | ❌ None |
| REQ-LIBRE-002 | FRAM CRC Validation | - | ❌ None |
| REQ-LIBRE-003 | Libre 2 FRAM Decryption | GAP-LIBRE-002 | ❌ None |
| REQ-LIBRE-004 | BLE Streaming Authentication | GAP-LIBRE-002 | ❌ None |
| REQ-LIBRE-005 | Libre 3 Security Protocol | GAP-LIBRE-001, GAP-CGM-030 | ❌ None |
| REQ-LIBRE-006 | Glucose Data Quality Flags | - | ❌ None |

---

## Gaps Inventory

### Dexcom G7 Protocol (5)

| Gap | Description | Related REQs | Priority |
|-----|-------------|--------------|----------|
| GAP-G7-001 | J-PAKE Full Specification Incomplete | REQ-BLE-001 | High |
| GAP-G7-002 | Certificate Chain Undocumented | REQ-BLE-002 | High |
| GAP-G7-003 | Service B Purpose Unknown | - | Medium |
| GAP-G7-004 | Anubis Transmitter Extended Commands | - | Low |
| GAP-G7-005 | Encryption Info Format Unknown | - | Medium |

### CGM General (9)

| Gap | Description | Related REQs | Priority |
|-----|-------------|--------------|----------|
| GAP-CGM-NODE-001 | Node.js 16+ EOL blocks upgrades | - | High |
| GAP-CGM-NODE-002 | Deprecated `request` npm package | - | Medium |
| GAP-CGM-NODE-003 | No CI/CD pipeline | - | Medium |
| GAP-CGM-001 | DiaBLE lacks treatment support | - | Low |
| GAP-CGM-002 | xdrip-js limited to Dexcom G5/G6 | GAP-XDRIPJS-001 | Medium |
| GAP-CGM-003 | Libre 3 encryption not fully documented | REQ-LIBRE-005 | High |
| GAP-CGM-004 | No standardized Dexcom BLE protocol spec | REQ-BLE-* | High |
| GAP-CGM-005 | Raw Values Not Uploaded by iOS | - | Low |
| GAP-CGM-006 | Follower Source Not Distinguished | - | Medium |

### Libre Protocol (10)

| Gap | Description | Related REQs | Priority |
|-----|-------------|--------------|----------|
| GAP-LIBRE-001 | Libre 3 Cloud Decryption Dependency | REQ-LIBRE-005 | High |
| GAP-LIBRE-002 | Libre 2 Gen2 Session-Based Auth | REQ-LIBRE-003, REQ-LIBRE-004 | High |
| GAP-LIBRE-003 | Transmitter Bridge Firmware Variance | - | Medium |
| GAP-LIBRE-004 | Calibration Algorithm Not Synced | - | Low |
| GAP-LIBRE-005 | Sensor Serial Not in Nightscout Entries | - | Low |
| GAP-LIBRE-006 | NFC vs BLE Data Latency Difference | - | Low |
| GAP-CGM-030 | Libre 3 Direct BLE Access Blocked | REQ-LIBRE-005 | High |
| GAP-CGM-031 | Libre 3 NFC Limited to Activation | - | Medium |
| GAP-CGM-032 | LibreLinkUp API Dependency | - | Medium |
| GAP-CGM-034 | Libre Trend Arrow Granularity | REQ-BLE-004 | Low |

### Loop Follow / Caregiver (9)

| Gap | Description | Related REQs | Priority |
|-----|-------------|--------------|----------|
| GAP-LF-001 | Alarm Configuration Not Synced | - | Medium |
| GAP-LF-002 | No Alarm History or Audit Log | - | Low |
| GAP-LF-003 | Prediction Data Unavailable for Trio | - | Medium |
| GAP-LF-004 | No Multi-Caregiver Alarm Acknowledgment | - | Low |
| GAP-LF-005 | No Command Status Tracking | - | Medium |
| GAP-LF-006 | No Command History or Audit Log | - | Low |
| GAP-LF-007 | TRC Return Notification Not Fully Implemented | - | Medium |
| GAP-LF-008 | Nightscout Remote Lacks OTP Security | - | High |
| GAP-LF-009 | No Unified Command Abstraction | - | Medium |

### Session Management (7)

| Gap | Description | Related REQs | Priority |
|-----|-------------|--------------|----------|
| GAP-SESSION-001 | Session Events Not Standardized | - | Medium |
| GAP-SESSION-002 | Calibration State Not Exposed | - | Low |
| GAP-SESSION-003 | Pluggable Calibration Algorithms (xDrip+ only) | - | Low |
| GAP-SESSION-004 | No Standard Sensor Session Event Schema | - | Medium |
| GAP-SESSION-005 | Warm-up Period Not Uploaded to Nightscout | - | Low |
| GAP-SESSION-006 | DiaBLE Has No Session Upload Capability | - | Low |
| GAP-SESSION-007 | Calibration State Not Synchronized | - | Low |

### xDrip+ / xdrip-js (7)

| Gap | Description | Related REQs | Priority |
|-----|-------------|--------------|----------|
| GAP-XDRIP-001 | No Nightscout v3 API Support | REQ-BRIDGE-001 | Medium |
| GAP-XDRIP-002 | Activity Data Schema Not Standardized | - | Low |
| GAP-XDRIP-003 | Device String Format Not Machine-Parseable | - | Low |
| GAP-XDRIPJS-001 | No G7 Support | - | High |
| GAP-XDRIPJS-002 | Deprecated BLE Library (noble) | - | Medium |
| GAP-XDRIPJS-003 | No Direct Nightscout Integration | - | Low |
| GAP-XDRIPJS-004 | Trend-to-Direction Mapping Not Standardized | REQ-CONNECT-002 | Medium |

### Connector / DiaBLE (5)

| Gap | Description | Related REQs | Priority |
|-----|-------------|--------------|----------|
| GAP-CONNECTOR-001 | No xDrip+ Connector in Nocturne | - | Medium |
| GAP-CONNECTOR-002 | No Eversense Connector in Nocturne | - | Low |
| GAP-DIABLE-002 | No Trend Direction Upload to Nightscout | - | Low |
| GAP-DIABLE-003 | No Nightscout v3 API Support | REQ-BRIDGE-001 | Medium |
| GAP-CGM-033 | AAPS Triple Arrow Support | - | Low |

---

## Priority Action Items

### High Priority (Assertion Coverage Needed)

1. **Create BLE protocol assertions**
   - Cover REQ-BLE-001 through REQ-BLE-006
   - Test CRC validation, auth handshake, glucose extraction
   - Deliverable: `conformance/assertions/ble-protocol.yaml`

2. **Create Libre protocol assertions**
   - Cover REQ-LIBRE-001 through REQ-LIBRE-006
   - Test FRAM decryption, sensor detection, quality flags
   - Deliverable: `conformance/assertions/libre-protocol.yaml`

3. **Address Libre 3 cloud dependency**
   - GAP-LIBRE-001, GAP-CGM-030 block direct access
   - Document LibreLinkUp API as interim solution

### Medium Priority (Gap Resolution)

4. **v3 API adoption for bridges**
   - GAP-XDRIP-001, GAP-DIABLE-003 need v3 support
   - Related to REQ-BRIDGE-001

5. **Trend arrow standardization**
   - GAP-XDRIPJS-004, GAP-CGM-034 inconsistencies
   - Need unified mapping table

---

## Cross-Reference: Related Documents

- [cgm-sources-gaps.md](../cgm-sources-gaps.md) - Full gap descriptions
- [cgm-sources-requirements.md](../cgm-sources-requirements.md) - Full requirement specs
- [g7-protocol-specification.md](../../docs/10-domain/g7-protocol-specification.md) - Dexcom G7 deep dive
- [libre3-protocol-gap-analysis.md](../../docs/10-domain/libre3-protocol-gap-analysis.md) - Libre 3 analysis

---

## Coverage Statistics

| Category | REQs | Covered | % |
|----------|------|---------|---|
| BLE Protocol | 6 | 0 | 0% |
| Bridge/Connector | 6 | 0 | 0% |
| Libre Protocol | 6 | 0 | 0% |
| **Total** | **18** | **0** | **0%** |

| Gap Category | Count | With REQ Links |
|--------------|-------|----------------|
| G7 Protocol | 5 | 2 |
| CGM General | 9 | 2 |
| Libre | 10 | 4 |
| Loop Follow | 9 | 0 |
| Session | 7 | 0 |
| xDrip | 7 | 2 |
| Connector | 5 | 1 |
| **Total** | **52** | **11** |
