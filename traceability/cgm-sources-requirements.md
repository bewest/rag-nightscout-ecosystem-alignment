# Cgm Sources Requirements

Domain-specific requirements extracted from requirements.md.
See [requirements.md](requirements.md) for the index.

> **Traceability Matrix**: [`domain-matrices/cgm-sources-matrix.md`](domain-matrices/cgm-sources-matrix.md) - REQ↔GAP↔Assertion coverage (0% assertion coverage)

---

### REQ-BLE-001: Message CRC Validation

**Statement**: All BLE messages with CRC-16 suffix MUST be validated before processing. Messages with invalid CRC MUST be rejected.

**Rationale**: Ensures data integrity over wireless transmission. CRC-16 CCITT (XModem) is the standard used by Dexcom transmitters.

**Scenarios**:
- CGM Data Reception
- Backfill Data Parsing

**Verification**:
- Compute CRC-16 of payload (excluding last 2 bytes)
- Compare with CRC in message (little-endian)
- Verify invalid CRC causes message rejection

**Cross-System Status**:
- CGMBLEKit: ✅ `Data.isCRCValid`
- xdrip-js: ✅ CRC validation in message parsing
- DiaBLE: ✅ CRC validation implemented

---

---

### REQ-BLE-002: Authentication Before Data Access

**Statement**: BLE clients MUST complete authentication handshake before requesting glucose data. Unauthenticated requests MUST be rejected by the transmitter.

**Rationale**: Ensures only authorized devices can read sensitive health data.

**Scenarios**:
- Initial Pairing
- Reconnection

**Verification**:
- Attempt glucose request before auth: verify failure
- Complete auth handshake: verify glucose request succeeds

---

---

### REQ-BLE-003: Glucose Value Extraction

**Statement**: Glucose values MUST be extracted from the lower 12 bits of the glucose field. The upper 4 bits (G6) or specific flag byte (G7) contain display-only flag.

**Rationale**: Ensures consistent glucose interpretation across implementations.

**Scenarios**:
- Real-time Glucose Reading
- Backfill Data Parsing

**Verification**:
- Parse glucose message
- Extract `glucose = glucoseBytes & 0x0FFF`
- Verify display-only flag extraction

---

---

### REQ-BLE-004: Trend Rate Conversion

**Statement**: Trend rate values MUST be interpreted as signed Int8 divided by 10, yielding mg/dL per minute. Value 0x7F (127) indicates unavailable.

**Rationale**: Standardizes trend rate interpretation for consistent trend arrow display.

**Scenarios**:
- Trend Arrow Display
- Rate of Change Alerting

**Verification**:
- Parse trend byte as signed Int8
- Divide by 10 for mg/dL/min
- Handle 0x7F as nil/unavailable

---

---

### REQ-BLE-005: Timestamp Calculation

**Statement**: Glucose timestamps MUST be calculated as activation date plus transmitter time (seconds). Activation date is derived from `Date.now() - currentTime * 1000`.

**Rationale**: Enables accurate historical data reconstruction and correlation with other events.

**Scenarios**:
- Glucose History Display
- Data Export

**Verification**:
- Request TransmitterTime message
- Calculate activation date
- Verify glucose timestamps are consistent

---

---

### REQ-BLE-006: Algorithm State Interpretation

**Statement**: Algorithm/calibration state values MUST be interpreted according to the G6 or G7 state machine. Only specific states indicate reliable glucose readings.

**Rationale**: Prevents display of unreliable readings during warmup, calibration errors, or sensor failures.

**Scenarios**:
- Glucose Display Logic
- Alerting Decisions

**Verification**:
- Parse algorithm state byte
- Map to known state enum
- Verify `hasReliableGlucose` logic matches state

---

## Carb Absorption Requirements

---

### REQ-BRIDGE-001: v3 API Support for Bridge Applications

**Statement**: Bridge applications uploading to Nightscout SHOULD support API v3 for UPSERT semantics.

**Rationale**: v3 API provides identifier-based deduplication, preventing duplicate records on re-runs.

**Scenarios**:
- Recovery from network failures
- Scheduled re-sync operations
- Multi-instance deployments

**Verification**:
- Bridge supports v3 endpoints
- Records include `identifier` field
- Re-runs don't create duplicates

**Gap Reference**: GAP-CONNECT-001

---

---

### REQ-BRIDGE-002: Client-Side Sync Identity Generation

**Statement**: Bridge applications SHOULD generate deterministic UUIDs for uploaded records.

**Rationale**: Enables idempotent uploads and cross-system deduplication matching Nightscout's sync identity spec.

**Scenarios**:
- Re-uploading historical data
- Multiple bridges for same source
- Disaster recovery

**Verification**:
- UUID v5 generated from source|date|type
- Consistent across re-runs
- Matches Nightscout identifier format

**Gap Reference**: GAP-CONNECT-003

---

---

### REQ-BRIDGE-003: Complete Collection Coverage

**Statement**: Bridge applications SHOULD upload all available data types (entries, treatments, devicestatus) from their source.

**Rationale**: Incomplete data limits Nightscout's value as a unified diabetes data platform.

**Scenarios**:
- Algorithm analysis requiring IOB/COB
- Report generation
- Caregiver monitoring

**Verification**:
- Transform outputs all 3 collection arrays
- Empty arrays for unavailable data (not omitted)
- Device field populated for attribution

**Gap Reference**: GAP-CONNECT-002

---

## PR Analysis Requirements

---

### REQ-CONNECT-001: XState Machine Testability

**Statement**: Bridge applications SHOULD use state machine patterns for testable, deterministic data flow.

**Rationale**: XState enables injecting mock services, replaying event sequences, and verifying state transitions without network I/O.

**Scenarios**:
- Unit testing fetch cycles
- Simulating session expiry
- Verifying retry behavior

**Verification**:
- Machine definitions exportable
- Services injectable at runtime
- State snapshots capturable

**Implementation Reference**: `lib/machines/*.js`

---

---

### REQ-CONNECT-002: Source Transform Standardization

**Statement**: Data transform functions MUST produce Nightscout-compatible batches with entries, treatments, devicestatus, and profile arrays.

**Rationale**: Consistent output format enables unified output drivers and simplifies testing.

**Scenarios**:
- Multi-source aggregation
- Output driver switching
- Transform validation

**Verification**:
- Transform returns `{ entries: [], treatments: [], devicestatus: [], profile: [] }`
- Each item has required fields per collection spec
- Device field populated for source attribution

**Gap Reference**: GAP-CONNECT-002

---

---

### REQ-CONNECT-003: Exponential Backoff on Failure

**Statement**: Bridge applications MUST implement exponential backoff when fetch cycles fail.

**Rationale**: Prevents overwhelming vendor APIs during outages and respects rate limits.

**Scenarios**:
- Network timeout
- Authentication failure
- Rate limiting

**Verification**:
- Delay increases with consecutive failures
- Maximum retry count enforced
- Successful fetch resets backoff

**Implementation Reference**: `lib/backoff.js`, `lib/machines/fetch.js:61-67`

---

## Carb Absorption Requirements

---

### REQ-LIBRE-001: Sensor Type Detection from PatchInfo

**Statement**: Systems reading Libre sensors MUST correctly identify sensor type from the `patchInfo` first byte using the documented mapping (0xDF/0xA2→Libre1, 0x9D/0xC5→Libre2, etc.).

**Rationale**: Correct sensor type determines encryption requirements, FRAM layout interpretation, and BLE protocol selection.

**Scenarios**:
- NFC Sensor Scan
- BLE Connection

**Verification**:
- Scan known sensor types and verify detection
- Test edge cases (Libre 2+ EU: 0xC6, Gen2 US: 0x2C)

---

---

### REQ-LIBRE-002: FRAM CRC Validation

**Statement**: Before parsing FRAM data, systems MUST validate CRC-16 checksums for header (bytes 0-1), body (bytes 24-25), and footer (bytes 320-321).

**Rationale**: Invalid CRC indicates corrupted or improperly decrypted data, which would produce incorrect glucose values.

**Scenarios**:
- NFC FRAM Read
- Transmitter Bridge Data

**Verification**:
- Read FRAM and verify CRC validation logic
- Test with intentionally corrupted data

---

---

### REQ-LIBRE-003: Libre 2 FRAM Decryption

**Statement**: Systems reading Libre 2/US14day sensors MUST decrypt FRAM using the documented XOR cipher with sensor UID and patchInfo as inputs.

**Rationale**: Libre 2 FRAM is encrypted; reading raw data produces invalid glucose values.

**Scenarios**:
- Libre 2 NFC Scan
- Transmitter Bridge Decryption

**Verification**:
- Decrypt known encrypted FRAM and verify glucose values
- Verify CRC passes after decryption

---

---

### REQ-LIBRE-004: BLE Streaming Authentication

**Statement**: For Libre 2 BLE streaming, systems MUST use the enable streaming NFC command (0xA1 0x1E) with correct unlock payload to obtain the sensor's MAC address.

**Rationale**: BLE streaming requires prior NFC pairing to establish cryptographic context.

**Scenarios**:
- Libre 2 BLE Pairing
- Streaming Reconnection

**Verification**:
- Execute enable streaming command
- Verify 6-byte MAC address response
- Verify BLE connection succeeds

---

---

### REQ-LIBRE-005: Libre 3 Security Protocol

**Statement**: Libre 3 connections MUST complete the security handshake (challenge-response with ECDH key exchange) before receiving glucose data.

**Rationale**: Libre 3 is fully encrypted; data is unreadable without completing security protocol.

**Scenarios**:
- Libre 3 BLE Connection
- Reconnection after disconnect

**Reference**: [Libre Protocol Deep Dive - Security Handshake Sequence](../docs/10-domain/libre-protocol-deep-dive.md#security-handshake-sequence)

**Verification**:
- Monitor security command sequence on characteristic 2198:
  - Write `0x11` (readChallenge) to initiate
  - Receive `0x08 0x17` (challengeLoadDone + status)
  - Exchange challenge data on 22CE
  - Write `0x08` (challengeLoadDone) to confirm
- Verify glucose data received on 177A after handshake completes

---

---

### REQ-LIBRE-006: Glucose Data Quality Flags

**Statement**: Systems SHOULD interpret the data quality flags in glucose readings and exclude readings with `hasError=true` or invalid quality codes.

**Rationale**: Sensor errors (signal disturbance, calibration issues) produce unreliable glucose values.

**Scenarios**:
- CGM Data Display
- Closed-Loop Input

**Verification**:
- Parse readings with various quality flags
- Verify error readings are filtered or flagged

---

## Template

```markdown

---
