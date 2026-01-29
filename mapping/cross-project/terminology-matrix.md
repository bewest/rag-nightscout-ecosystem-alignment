# Cross-Project Terminology Matrix

This matrix maps equivalent concepts across AID systems. Use this as a rosetta stone when translating between projects.

---

## OpenAPI Specification Cross-References

The following OpenAPI 3.0 specifications provide formal schema definitions aligned with this terminology matrix:

| Spec File | Collection | Description |
|-----------|------------|-------------|
| [`aid-entries-2025.yaml`](../../specs/openapi/aid-entries-2025.yaml) | `entries` | SGV, MBG, calibration records with direction mapping |
| [`aid-treatments-2025.yaml`](../../specs/openapi/aid-treatments-2025.yaml) | `treatments` | Bolus, carbs, temp basal, overrides with eventType catalog |
| [`aid-devicestatus-2025.yaml`](../../specs/openapi/aid-devicestatus-2025.yaml) | `devicestatus` | Loop vs oref0 structure variants, predictions |
| [`aid-profile-2025.yaml`](../../specs/openapi/aid-profile-2025.yaml) | `profile` | Therapy settings with time-varying schedules |
| [`aid-alignment-extensions.yaml`](../../specs/openapi/aid-alignment-extensions.yaml) | All | 2026 extensions addressing documented gaps |

**Origin Schema Extractions**:
- [`mapping/nightscout/v3-treatments-schema.md`](../nightscout/v3-treatments-schema.md) - 21+ eventTypes, deduplication rules
- [`mapping/aaps/nsclient-schema.md`](../aaps/nsclient-schema.md) - 70+ fields, 25 eventTypes

**JSON Schema**: [`aid-events.schema.json`](../../specs/jsonschema/aid-events.schema.json) provides unified validation schema with gap annotations.

**Key Annotations**: OpenAPI specs use `x-aid-*` extensions:
- `x-aid-source`: Source file reference
- `x-aid-controllers`: Controller support matrix
- `x-aid-gap`: Related gap ID
- `x-aid-2026`: Marks 2026 alignment extensions

---

## Data Concepts

### Heart Rate Collection (API v3)

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `beatsPerMinute` | double | Heart rate in BPM (20-300) | AAPS HeartRate.kt |
| `timestamp` | int64 | End of sample (epoch ms) | AAPS HeartRate.kt |
| `duration` | int64 | Sample window (default 60s) | AAPS HeartRate.kt |
| `device` | string | Source device name | AAPS HeartRate.kt |
| `utcOffset` | int64 | Timezone offset (ms) | AAPS HeartRate.kt |
| `isValid` | boolean | Data validity flag | AAPS HeartRate.kt |
| `identifier` | uuid | Sync identity | Nightscout pattern |

**Controller Support**:
| System | Support | Notes |
|--------|---------|-------|
| AAPS | Full | Primary source, Wear OS collection |

---

### Insulin Profiles Collection (API v1)

Cross-project field mapping for insulin type definitions. See [`aid-insulin-2025.yaml`](../../specs/openapi/aid-insulin-2025.yaml).

| Field | Nightscout | AAPS | oref0 | xDrip+ |
|-------|------------|------|-------|--------|
| **Name** | `name` | `insulinLabel` | `profile.insulinType` | `Insulin.name` |
| **DIA** | `dia` (hours) | `insulinEndTime` (ms) | `profile.dia` (hours) | `Insulin.maxEffect` (hours) |
| **Peak** | `peak` (min) | `peak` (ms) | `profile.insulinPeakTime` (min) | `Insulin.peak` (min) |
| **Curve** | `curve` | model class | `profile.curve` | (derived from maxEffect) |
| **Active** | `active` (bolus/basal) | N/A | N/A | N/A |
| **Concentration** | `concentration` | N/A | N/A | `Insulin.concentration` |

**Curve Models**:
| Model | Peak | DIA Min | Systems |
|-------|------|---------|---------|
| `rapid-acting` | ~75 min | 5h | oref0, AAPS, Trio |
| `ultra-rapid` | ~55 min | 5h | oref0, AAPS, Trio |
| `bilinear` | 75 min fixed | 3h | oref0 (legacy) |
| `ultra-long` | 360-540 min | 24h | Basal insulins |
| `free-peak` | User-defined | 5h | AAPS, Trio |

**Controller Support**:
| System | Support | Sync | Notes |
|--------|---------|------|-------|
| xDrip+ | Yes | Yes | InsulinInjection.insulin name |
| AAPS | Yes | No | insulinConfiguration in Bolus entity |
| Loop | No | N/A | Fixed models, not configurable |
| Trio | Yes | No | oref0 models via profile.json |
| nightscout-reporter | Yes | Read | Reads for IOB curve display |

**Specification**: [`specs/openapi/aid-insulin-2025.yaml`](../../specs/openapi/aid-insulin-2025.yaml)

---

### Remote Commands Collection (API v1)

Cross-project mapping for caregiver remote actions. See [`aid-commands-2025.yaml`](../../specs/openapi/aid-commands-2025.yaml).

| Action Type | Nightscout | Loop Action | AAPS SMS |
|-------------|------------|-------------|----------|
| **Bolus** | `bolus` | `bolusEntry(BolusAction)` | `BOLUS` |
| **Carbs** | `carbs` | `carbsEntry(CarbAction)` | `CARBS` |
| **Override** | `override` | `temporaryScheduleOverride` | `TARGET` |
| **Cancel** | `cancelOverride` | `cancelTemporaryOverride` | `CANCEL` |

**Command State Machine**:
```
Pending → In-Progress → Complete
                     └→ Error
```

**Action Parameters**:

| Action | Required Fields | Optional Fields |
|--------|-----------------|-----------------|
| bolus | `units` (double) | - |
| carbs | `grams` (double) | `absorption`, `foodType`, `startDate` |
| override | `name` (string) | `durationTime`, `remoteAddress` |
| cancelOverride | - | `reason` |

**Security Model**:
- OTP (One-Time Password) validation
- Expiration time checking
- State machine prevents duplicate execution

**Controller Support**:
| System | Support | Transport | Notes |
|--------|---------|-----------|-------|
| Loop | Full | Push Notification (APNs) | Primary consumer |
| Trio | Full | Push Notification | Same as Loop |
| AAPS | None | SMS only | Uses SmsCommunicatorPlugin |
| xDrip+ | None | Display only | No command execution |

**Specification**: [`specs/openapi/aid-commands-2025.yaml`](../../specs/openapi/aid-commands-2025.yaml)

---

### Authentication Concepts

Cross-project comparison of authentication mechanisms. See [`authentication-flows-deep-dive.md`](../../docs/10-domain/authentication-flows-deep-dive.md).

| Concept | Nightscout | AAPS | Loop | xDrip+ |
|---------|------------|------|------|--------|
| **Primary Auth** | API Secret + JWT | Access Token | API Secret | SHA1 Secret |
| **Transport** | REST + WebSocket | WebSocket | REST | REST |
| **Token Storage** | MongoDB | Preferences | Keychain | Preferences |
| **Hashing** | SHA1/SHA512 | N/A | N/A | SHA1 |
| **Rate Limiting** | Delay list | N/A | N/A | N/A |

**Permission Model (Shiro-Trie)**:

| Role | Permissions | Use Case |
|------|-------------|----------|
| `admin` | `['*']` | Full access |
| `readable` | `['*:*:read']` | Read-only |
| `careportal` | `['api:treatments:create']` | Careportal entry |
| `devicestatus-upload` | `['api:devicestatus:create']` | Device status only |
| `status-only` | `['api:status:read']` | Status endpoint only |

**Permission Format**: `{domain}:{collection}:{action}`
- Example: `api:entries:read`, `api:treatments:create`, `*`

**Enterprise RBAC (roles-gateway)**:

| Feature | Description |
|---------|-------------|
| Multi-site | Single gateway manages multiple Nightscout instances |
| Group-based | Users assigned to groups with policies |
| Scheduled | Time-based access windows (school hours) |
| HIPAA audit | Consent logging for compliance |

See: [`mapping/nightscout-roles-gateway/`](../nightscout-roles-gateway/)

**Deep Dive**: [`docs/10-domain/authentication-flows-deep-dive.md`](../../docs/10-domain/authentication-flows-deep-dive.md)

---

### Statistics API Concepts

| Concept | Definition | Formula/Source |
|---------|------------|----------------|
| TIR (Time in Range) | % of readings between 70-180 mg/dL | count_in_range / total × 100 |
| A1C (DCCT) | Estimated HbA1c percentage | (mean_glucose + 46.7) / 28.7 |
| A1C (IFCC) | Estimated HbA1c mmol/mol | (A1C_DCCT - 2.15) × 10.929 |
| GMI | Glucose Management Indicator | 3.31 + (0.02392 × mean_glucose) |
| GVI | Glycemic Variability Index | Σ√(ΔTime² + ΔGlucose²) / Σ ΔTime |
| PGS | Patient Glycemic Status | GVI × Mean × (1 - TIR_multiplier) |
| CV | Coefficient of Variation | (StdDev / Mean) × 100 |
| TDD | Total Daily Dose | basal + bolus insulin |

**Thresholds (ADA Consensus)**:
| Range | mg/dL | Target |
|-------|-------|--------|
| Very Low | < 54 | < 1% |
| Low | 54-70 | < 4% |
| In Range | 70-180 | > 70% |
| High | 180-250 | < 25% |
| Very High | > 250 | < 5% |

**Source**: `docs/sdqctl-proposals/statistics-api-proposal.md`, Nathan et al. 2008

---

### Server Implementations

| Aspect | cgm-remote-monitor | Nocturne |
|--------|-------------------|----------|
| Language | JavaScript (Node.js) | C# (.NET 10) |
| Database | MongoDB | PostgreSQL |
| Cache | In-memory | Redis |
| Real-time | Socket.IO | SignalR (+ Socket.IO bridge) |
| Algorithm | JS oref | Rust oref (FFI/WASM) |
| API Versions | v1, v2, v3 | v1, v2, v3, v4 (extensions) |
| Connectors | Via share2nightscout-bridge | 8 native (Dexcom, Libre, Glooko, MiniMed, MFP, NS, TConnect, Tidepool) |

**Source**: `externals/nocturne/AGENTS.md`, `docs/10-domain/nocturne-deep-dive.md`

### Dexcom Share API (share2nightscout-bridge)

| Endpoint | Purpose | Server |
|----------|---------|--------|
| `/ShareWebServices/Services/General/AuthenticatePublisherAccount` | Get accountId | US: share2.dexcom.com, EU: shareous1.dexcom.com |
| `/ShareWebServices/Services/General/LoginPublisherAccountById` | Get sessionID | Same |
| `/ShareWebServices/Services/Publisher/ReadPublisherLatestGlucoseValues` | Fetch glucose | Same |

**Trend Mapping**: Dexcom `Trend` (0-9) → Nightscout `direction` (DoubleUp, SingleUp, FortyFiveUp, Flat, FortyFiveDown, SingleDown, DoubleDown, etc.)

**Source**: `externals/share2nightscout-bridge/index.js:56-66`, `docs/10-domain/share2nightscout-bridge-deep-dive.md`

### Tandem t:connect API (tconnectsync)

| Endpoint | Purpose | Auth |
|----------|---------|------|
| `/tconnect/controliq/api/therapytimeline/users/{guid}` | Therapy events | OIDC |
| `/tconnect/therapyevents/api/TherapyEvents/{start}/{end}` | Therapy events | OIDC |
| `/cloud/usersettings/api/UserProfile` | Pump profile | Android OAuth |
| `/therapytimeline2csv/{guid}/{start}/{end}` | Historical CSV | Web session |

**Treatment Mapping**:

| tconnectsync | Nightscout eventType |
|--------------|---------------------|
| Bolus | `Combo Bolus` |
| Temp Basal | `Temp Basal` |
| Basal Suspension | `Basal Suspension` |
| Site Change | `Site Change` |
| Exercise/Sleep | `Exercise`, `Sleep` |

**Source**: `externals/tconnectsync/tconnectsync/sync/`, `docs/10-domain/tconnectsync-deep-dive.md`

**Gap Reference**: GAP-TCONNECT-001 (no v3 API), GAP-TCONNECT-002 (limited Control-IQ data), GAP-TCONNECT-003 (batch only), GAP-TCONNECT-004 (no trend direction)

**Mapping Docs**: `mapping/tconnectsync/` (607 lines, 4 docs)

### LibreLink Up API (nightscout-librelink-up)

| Endpoint | Purpose | Auth |
|----------|---------|------|
| `POST /llu/auth/login` | Authentication | Email/password |
| `GET /llu/connections` | Patient list | Bearer token |
| `GET /llu/connections/{id}/graph` | Historical glucose | Bearer token |

**API Regions**: EU, EU2, US, AU, DE, FR, JP, AP (`api-{region}.libreview.io`)

**Trend Mapping** (LibreLink → Nightscout):

| LibreLink TrendArrow | Nightscout direction |
|---------------------|---------------------|
| 1 | `SingleDown` |
| 2 | `FortyFiveDown` |
| 3 | `Flat` |
| 4 | `FortyFiveUp` |
| 5 | `SingleUp` |

**Field Mapping**:

| LibreLink | Nightscout |
|-----------|------------|
| `ValueInMgPerDl` | `sgv` |
| `FactoryTimestamp` | `date` (epoch ms) |
| `TrendArrow` | `direction` |

**Timestamp Pattern**: LibreLink provides two timestamps:
- `FactoryTimestamp` - Sensor time (factory calibrated) → **Used for Nightscout**
- `Timestamp` - Phone local time → Not used (avoids timezone issues)

**Source**: `externals/nightscout-librelink-up/src/`, `mapping/nightscout-librelink-up/entries.md`

**Gap Reference**: GAP-LIBRELINK-001 (no v3 API), GAP-LIBRELINK-002 (no backfill), GAP-LIBRELINK-003 (5 trend values only)

### Persistent State (Configuration)

| Alignment Term | Nightscout | Loop | AAPS | Trio | xDrip+ |
|----------------|------------|------|------|------|--------|
| Profile (config) | `profile` collection, `store` object | `TherapySettings` | `ProfileSwitch` entity (with `duration=0`) | Local settings + `FetchedNightscoutProfile` | N/A (CGM-focused) |
| Basal Schedule | `basal` array in profile | `BasalRateSchedule` | `ProfileSwitch.basalBlocks` | `basal` array (from NS) | N/A |
| ISF Schedule | `sens` array in profile | `InsulinSensitivitySchedule` | `ProfileSwitch.isfBlocks` | `sens` array (from NS) | N/A |
| CR Schedule | `carbratio` array in profile | `CarbRatioSchedule` | `ProfileSwitch.icBlocks` | `carbratio` array (from NS) | N/A |
| Target Range | `target_low`/`target_high` arrays | `GlucoseRangeSchedule` | `ProfileSwitch.targetBlocks` | `target_low`/`target_high` (from NS) | `Pref.highValue`/`lowValue` (display only) |

**Note**: AAPS stores profile data in `ProfileSwitch` entities; a switch with `duration=0` is permanent. Trio fetches profiles from Nightscout (`FetchedNightscoutProfile`) and stores local algorithm settings separately.

**Note**: xDrip+ is a CGM data management app, not a closed-loop system. It does not manage therapy profiles but does track glucose thresholds for display/alerts.
- Core data models: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/`
- See `mapping/xdrip-android/README.md` for full architecture documentation.

### Events (Actions/Observations)

| Alignment Term | Nightscout | Loop | AAPS | Trio | xDrip+ |
|----------------|------------|------|------|------|--------|
| Glucose Entry | `entries` collection, `sgv` field | `StoredGlucoseSample` | `GlucoseValue` entity | `BloodGlucose` | `BgReading` entity |
| Bolus Event | eventType: `Meal Bolus`, `Correction Bolus` | `DoseEntry` (type: bolus) | `Bolus` entity | `PumpHistoryEvent` | `Treatments.insulin` |
| Carb Entry Event | eventType: `Carb Correction` | `StoredCarbEntry` | `Carbs` entity | `CarbsEntry` | `Treatments.carbs` |
| Temp Basal Event | eventType: `Temp Basal` | `DoseEntry` (type: tempBasal) | `TemporaryBasal` entity | `TempBasal` | N/A (via AAPS) |
| Profile Switch | eventType: `Profile Switch` | N/A (implicit) | `ProfileSwitch` entity | N/A (implicit) | N/A |
| Override (active) | eventType: `Temporary Override` | `TemporaryScheduleOverride` | N/A (via ProfileSwitch) | `Override` | N/A |
| Temporary Target | eventType: `Temporary Target` | via `TemporaryScheduleOverride` | `TempTarget` entity | `TempTarget` | N/A |
| Note/Annotation | eventType: `Note`, `Announcement` | `NoteEntry` | `UserEntry` | `NoteEntry` | `Treatments.notes` |
| Sensor Start | eventType: `Sensor Start` | `CGMSensorEvent` | `TherapyEvent.SENSOR_CHANGE` | `SensorChange` | `Treatments` (eventType: `Sensor Start`) |
| Sensor Stop | N/A | N/A | N/A | N/A | `Treatments` (eventType: `Sensor Stop`) |

### Treatment Data Models (Deep Dive)

> **See Also**: [Treatments Collection Deep Dive](../../docs/10-domain/treatments-deep-dive.md) for comprehensive field-by-field mappings.

#### Bolus Fields

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| Insulin Amount | `insulin` | `deliveredUnits` / `programmedUnits` | `amount` | via `DoseEntry` | `insulin` |
| Bolus Type | `eventType` | `.bolus` (single) | `Type` enum | `.bolus` | N/A |
| Automatic Flag | `automatic` | `automatic` | via `Type.SMB` | `automatic` | N/A |
| Sync Identity | `identifier` / `syncIdentifier` | `syncIdentifier` | `interfaceIDs.nightscoutId` | `syncIdentifier` | `uuid` |
| Insulin Type | `insulinType` | `insulinType?.brandName` | `insulinConfiguration` | N/A | `insulinJSON` |
| Duration (extended) | `duration` | via `endDate - startDate` | N/A | via `endDate - startDate` | N/A |

**Bolus Type Enums**:
- **Loop**: Single `.bolus` type (no SMB)
- **AAPS**: `NORMAL`, `SMB`, `PRIMING` (internal); SMB uploads as `eventType: Correction Bolus` with `type: SMB` field
- **Nightscout eventType**: `Meal Bolus`, `Correction Bolus`, `Snack Bolus` (no explicit SMB eventType - see GAP-TREAT-003)

#### Carb Entry Fields

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| Carbs Amount | `carbs` | `quantity` (HKQuantity) | `amount` | via `CarbsEntry` | `carbs` |
| Absorption Time | `absorptionTime` (min) | `absorptionTime` (sec) | N/A | `absorptionTime` (sec) | N/A |
| Duration (eCarbs) | `duration` (min) | N/A | `duration` (ms) | N/A | N/A |
| Food Type | `foodType` | `foodType` | N/A | `foodType` | N/A |
| Sync Identity | `identifier` | `syncIdentifier` | `interfaceIDs.nightscoutId` | `syncIdentifier` | `uuid` |

**Unit Differences (GAP-TREAT-001, GAP-TREAT-002)**:
- Absorption time: Loop/Trio use seconds, Nightscout uses minutes
- Duration: AAPS uses milliseconds, Nightscout uses minutes

**Validated by**: `tools/test_conversions.py` with test cases in `conformance/unit-conversions/conversions.yaml`

#### Temp Basal Fields

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| Rate | `rate` / `absolute` | `unitsPerHour` | `rate` | via `DoseEntry` | N/A |
| Is Absolute | `temp: "absolute"` | Always true | `isAbsolute` | Always true | N/A |
| Percent | `percent` | N/A | `rate - 100` (if relative) | N/A | N/A |
| Duration | `duration` (min) | `endDate - startDate` (sec) | `duration` (ms) | `endDate - startDate` (sec) | N/A |
| Type | `eventType` | `DoseType` enum | `Type` enum | `DoseType` | N/A |
| Automatic | `automatic` | `automatic ?? true` | N/A | `automatic` | N/A |

**Temp Basal Types (AAPS)**:
- `NORMAL`: Standard temp basal
- `EMULATED_PUMP_SUSPEND`: Suspend via 0% basal
- `PUMP_SUSPEND`: Actual pump suspend
- `SUPERBOLUS`: Superbolus temp basal
- `FAKE_EXTENDED`: Extended bolus emulation

#### Treatment Sync Identity

| System | Primary ID | Secondary ID | Upload Method |
|--------|-----------|--------------|---------------|
| Loop | `syncIdentifier` (UUID) | N/A | POST (v1 API) |
| AAPS | `interfaceIDs.nightscoutId` | `pumpId` + `pumpType` + `pumpSerial` | PUT (v3 API) |
| Trio | `syncIdentifier` (UUID) | N/A | POST (v1 API) |
| xDrip+ | `uuid` | N/A | PUT upsert (v1 API) |

**Gap Reference**: GAP-003 (no unified sync identity), GAP-TREAT-005 (Loop POST duplicates)

### Glucose Data Models (Deep Dive)

> **See Also**: [Entries Collection Deep Dive](../../docs/10-domain/entries-deep-dive.md) for comprehensive field-by-field mappings.

#### Core SGV Fields

| Field | Nightscout | Loop | AAPS | Trio | xDrip+ |
|-------|------------|------|------|------|--------|
| Glucose Value | `sgv` | `quantity` (HKQuantity) | `value` | `sgv` | `calculated_value` |
| Timestamp | `date` (epoch ms) | `startDate` | `timestamp` | `date` | `timestamp` |
| Trend Arrow | `direction` | `trendType` (GlucoseTrend) | `trendArrow` | `direction` | `dg_slope` → direction |
| Noise Level | `noise` (1-4) | N/A | `noise` | `noise` | `noise` |
| Device/Source | `device` | `provenanceIdentifier` | `sourceSensor` | N/A | `sensor_uuid` |
| Sync Identity | `_id` | N/A | `interfaceIDs.nightscoutId` | `_id` | `uuid` |

#### Direction (Trend Arrow) Mapping

| Nightscout | Loop (GlucoseTrend) | AAPS (TrendArrow) | Trio | xDrip+ |
|------------|---------------------|-------------------|------|--------|
| `DoubleUp` | `.upUpUp` | `DOUBLE_UP` | `DoubleUp` | `DOUBLE_UP (1)` |
| `SingleUp` | `.upUp` | `SINGLE_UP` | `SingleUp` | `SINGLE_UP (2)` |
| `FortyFiveUp` | `.up` | `FORTY_FIVE_UP` | `FortyFiveUp` | `FORTY_FIVE_UP (3)` |
| `Flat` | `.flat` | `FLAT` | `Flat` | `FLAT (4)` |
| `FortyFiveDown` | `.down` | `FORTY_FIVE_DOWN` | `FortyFiveDown` | `FORTY_FIVE_DOWN (5)` |
| `SingleDown` | `.downDown` | `SINGLE_DOWN` | `SingleDown` | `SINGLE_DOWN (6)` |
| `DoubleDown` | `.downDownDown` | `DOUBLE_DOWN` | `DoubleDown` | `DOUBLE_DOWN (7)` |
| `NOT COMPUTABLE` | N/A | `NONE` | `notComputable` | `NOT_COMPUTABLE (8)` |
| N/A | N/A | `TRIPLE_UP` | `TripleUp` | N/A |
| N/A | N/A | `TRIPLE_DOWN` | `TripleDown` | N/A |

**Gap Reference**: GAP-ENTRY-001 (triple arrows have no NS equivalent)

#### Raw/Filtered Values

| Field | Nightscout | AAPS | xDrip+ | Notes |
|-------|------------|------|--------|-------|
| Unfiltered Raw | `unfiltered` | N/A | `raw_data` | Unprocessed sensor signal |
| Filtered Raw | `filtered` | N/A | `filtered_data` | Noise-reduced signal |
| Raw Calibrated | N/A | `raw` | `raw_calculated` | Intermediate value |

**Note**: iOS systems (Loop, Trio) do not expose raw sensor values—they rely on transmitter-calibrated readings.

#### CGM vs Meter Reading Distinction

| Reading Type | Nightscout | AAPS | xDrip+ |
|--------------|------------|------|--------|
| CGM (continuous) | `entries` (type: `sgv`) | `GlucoseValue` entity | `BgReading` entity |
| Meter (fingerstick) | `treatments` (eventType: `BG Check`) | `TherapyEvent` (FINGER_STICK_BG_VALUE) | `BloodTest` entity |
| Calibration | `entries` (type: `cal`) | N/A | `Calibration` entity |

**Key Distinction**: Meter readings are **treatments**, not entries. CGM readings are entries.

#### Glucose Entry Sync Identity

| System | Primary ID | Upload Role | Dedup Strategy |
|--------|-----------|-------------|----------------|
| xDrip+ | `uuid` | Primary producer | Upsert by uuid |
| AAPS | `interfaceIDs.nightscoutId` | Consumer/rebroadcast | Check before insert |
| Loop | N/A | Typically doesn't upload CGM | N/A |
| Trio | `_id` | Passthrough | Direct from NS |

**Gap Reference**: GAP-ENTRY-003 (no standardized source taxonomy), GAP-ENTRY-004 (no universal dedup)

### State Snapshots (Point-in-Time)

| Alignment Term | Nightscout | Loop | AAPS | Trio | xDrip+ |
|----------------|------------|------|------|------|--------|
| Device Status | `devicestatus` collection | `LoopDataManager` snapshot | `DeviceStatus` entity | `DeviceStatus` | `uploaderBattery` in POST |
| Loop/Algorithm State | `loop` in devicestatus | `LoopDataManager.lastLoopCompleted` | `LoopStatus` | `LoopStatus` | N/A (no loop) |
| Pump State | `pump` in devicestatus | `PumpManagerStatus` | `PumpStatus` | `PumpStatus` | Reads from AAPS broadcast |
| Uploader State | `uploader` in devicestatus | N/A | `UploaderStatus` | `UploaderStatus` | `NightscoutUploader.last_success_time` |

**Note**: xDrip+ uploads device status but does not run a loop algorithm. It can display AAPS pump status received via broadcast.
- Device status upload: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java#L134-L138`
- AAPS status handler: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/insulin/aaps/AAPSStatusHandler.java`

### Derived Values (Computed)

| Alignment Term | Nightscout | Loop | AAPS | Trio | xDrip+ |
|----------------|------------|------|------|------|--------|
| Insulin on Board | `iob` in devicestatus | `InsulinOnBoard` | `IobTotal` | `IOB` | `Iob.getIobAtTime()` (multi-insulin) |
| Carbs on Board | `cob` in devicestatus | `CarbsOnBoard` | `COB` | `COB` | N/A (no absorption model) |
| Active Basal Rate | `basal` in loop prediction | `basalDelivery` | `currentBasal` | `basal` | N/A (no basal control) |
| Predicted Glucose | `predBgs` in loop | `predictedGlucose` | `predictedBg` | `predictedBg` | N/A (no prediction) |
| Glucose Delta | `delta` in entries | `glucoseMomentum` | `delta` | `delta` | `BgReading.currentSlope()` |

#### Prediction Array Formats

| Aspect | Loop | AAPS/Trio (oref) |
|--------|------|------------------|
| **Model** | Single combined curve | 4 separate curves (IOB/COB/UAM/ZT) |
| **NS Field** | `loop.predicted.values` | `openaps.suggested.predBGs.*` |
| **Data Type** | Decimal (HKQuantity) | Integer mg/dL |
| **Interval** | Variable | 5 minutes fixed |

**Deep Dive**: [`docs/10-domain/prediction-arrays-comparison.md`](../../docs/10-domain/prediction-arrays-comparison.md)

**Gap Reference**: GAP-PRED-002 (Loop single vs oref multi-curve), GAP-PRED-003 (interval not standardized), GAP-PRED-004 (no confidence bounds)

#### oref0 Algorithm Components

| Component | oref0 File | AAPS Equivalent | Trio Equivalent |
|-----------|------------|-----------------|-----------------|
| **Main Algorithm** | `lib/determine-basal/determine-basal.js` | `DetermineBasalAdapterSMBJS.kt` | `OpenAPS.swift` |
| **Autosens** | `lib/determine-basal/autosens.js` | `AutosensDataStore.kt` | `Autosens.swift` |
| **IOB Calculation** | `lib/iob/calculate.js` | `IobCobCalculator.kt` | `IOBCalculator.swift` |
| **COB Calculation** | `lib/determine-basal/cob.js` | `CobInfo.kt` | `COBCalculator.swift` |
| **Profile** | `lib/profile/` | `ProfileStore.kt` | `ProfileManager.swift` |
| **Autotune** | `lib/autotune/` | `AutotunePlugin.kt` | `Autotune.swift` |

**Deep Dive**: [`docs/10-domain/openaps-oref0-deep-dive.md`](../../docs/10-domain/openaps-oref0-deep-dive.md)

**Gap Reference**: GAP-OREF-001 (no npm package), GAP-OREF-002 (openaps unmaintained), GAP-OREF-003 (oref0 vs oref1 unclear)

**Note**: The distinction between persistent configuration, events, state snapshots, and derived values is critical for accurate cross-project translation.

**xDrip+ IOB**: Uses `Iob.java` with multi-insulin support via `InsulinInjection` profiles.
- Source: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/Iob.java`
- Multi-insulin: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/models/InsulinInjection.java`
- IOB calculation: `Iob.getIobAtTime()` method

---

## Profile Settings

| Setting | Nightscout | Loop | AAPS | Trio | xDrip+ |
|---------|------------|------|------|------|--------|
| Basal Rates | `basal` array | `BasalRateSchedule` | `ProfileSwitch.basalBlocks` | `basal` array | N/A |
| ISF (Correction Factor) | `sens` array | `InsulinSensitivitySchedule` | `ProfileSwitch.isfBlocks` | `sens` array | N/A |
| Carb Ratio | `carbratio` array | `CarbRatioSchedule` | `ProfileSwitch.icBlocks` | `carbratio` array | N/A |
| Target Range Low | `target_low` array | `GlucoseRangeSchedule` | `ProfileSwitch.targetBlocks.lowTarget` | `target_low` array | `Pref.lowValue` (alerts) |
| Target Range High | `target_high` array | `GlucoseRangeSchedule` | `ProfileSwitch.targetBlocks.highTarget` | `target_high` array | `Pref.highValue` (alerts) |
| Insulin Duration | `dia` | `InsulinModel.effectDuration` | `dia` | `dia` | `Insulin.maxEffect` (per profile) |
| Units | `units` (`mg/dL` or `mmol/L`) | `HKUnit` | `GlucoseUnit` | `GlucoseUnit` | `Pref.units_mmol` (boolean) |

**Note**: xDrip+ stores target ranges for alert thresholds only, not for dosing calculations.
- Insulin profiles: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/insulin/Insulin.java`
- Alert thresholds: `Pref.getStringToInt("highValue", 170)` and `Pref.getStringToInt("lowValue", 70)`

### Profile Data Structures

| Aspect | Nightscout | Loop | AAPS | Trio |
|--------|------------|------|------|------|
| Profile Entity | `profile` collection | `TherapySettings` | `ProfileSwitch` entity | `FetchedNightscoutProfile` (from NS) |
| Time-Value Format | `{time, timeAsSeconds, value}` | `RepeatingScheduleValue<T>` | `Block` (duration-based) | `NightscoutTimevalue` |
| Multiple Profiles | `store` dictionary | Single settings | Via named `ProfileSwitch` entries | `store` dictionary |
| Profile Naming | `defaultProfile` string | None (implicit) | `profileName` field | `defaultProfile` string |
| Permanent vs Temp | N/A (always stored) | N/A (single config) | `duration=0` = permanent | N/A (uses NS profiles) |

### Timezone Handling

> **See Also**: [Timezone/DST Gap Summary](#timezone-and-dst-gap-summary) for interoperability issues.

#### Profile/Schedule Timezone Storage

| Aspect | Nightscout | Loop | AAPS | Trio | xDrip+ | oref0 |
|--------|------------|------|------|------|--------|-------|
| **Profile TZ Format** | IANA string (`"US/Eastern"`) | `TimeZone` object | N/A (uses device TZ) | IANA string (from NS) | N/A | N/A |
| **Schedule TZ** | Per-profile `timezone` field | Per `DailyValueSchedule.timeZone` | Per `ProfileSwitch.utcOffset` | From NS profile | N/A | N/A |
| **TZ Library** | `moment-timezone` | Foundation `TimeZone` | Java `TimeZone` | Foundation `TimeZone` | Java `TimeZone` | `moment-timezone` |

**Source Code References**:
- Nightscout: `cgm-remote-monitor:lib/profilefunctions.js:178` - `profile['timezone']`
- Loop: `LoopKit/LoopKit/DailyValueSchedule.swift:103` - `public var timeZone: TimeZone`
- AAPS: `database/entities/ProfileSwitch.kt:42` - `utcOffset: Long = TimeZone.getDefault().getOffset(timestamp)`

#### Event Timestamp/Offset Storage

| Aspect | Nightscout | Loop | AAPS | Trio | xDrip+ | oref0 |
|--------|------------|------|------|------|--------|-------|
| **Event Offset Field** | `utcOffset` (minutes) | N/A | `utcOffset` (ms) | N/A | N/A | N/A |
| **Offset Calculation** | From `dateString` TZ | N/A | `TimeZone.getOffset(timestamp)` | N/A | N/A | N/A |
| **Offset Auto-Parse** | Yes (API3) | N/A | Yes | N/A | N/A | N/A |

**Unit Difference (GAP-TZ-004)**:
- **Nightscout API**: `utcOffset` in **minutes** (e.g., `-480` for UTC-8)
- **AAPS internal**: `utcOffset` in **milliseconds** (e.g., `-28800000` for UTC-8)

**Source Code References**:
- Nightscout: `cgm-remote-monitor:lib/api3/generic/collection.js:182` - `doc.utcOffset = m.utcOffset()` (minutes)
- AAPS: `database/entities/interfaces/DBEntryWithTime.kt:6` - `var utcOffset: Long` (milliseconds)

#### DST (Daylight Saving Time) Awareness

| Aspect | Nightscout | Loop | AAPS | Trio | xDrip+ |
|--------|------------|------|------|------|--------|
| **DST Automatic** | Yes (IANA rules) | Yes (Foundation) | **No** (fixed offset at capture) | Yes (via NS) | Partial |
| **DST Detection** | `moment-tz` | System | N/A | System | `TimeZone.getDSTSavings()` |
| **Profile TZ DST** | Automatic | Automatic | N/A (no IANA) | Automatic | N/A |

**Critical Gap (GAP-TZ-005)**: AAPS captures `utcOffset` at event creation time using `TimeZone.getDefault().getOffset(timestamp)`. This captures the **current** offset including DST, but the offset is **fixed** and won't update when DST transitions occur. Historical data analysis crossing DST boundaries may misinterpret times.

#### Pump Timezone/DST Handling

| Pump Driver | Can Handle DST | Auto-Update | Source |
|-------------|----------------|-------------|--------|
| **Medtronic** | ❌ No | User intervention | `MedtronicPumpPlugin.kt:259` |
| **Omnipod DASH** | ❌ No | User intervention | `OmnipodDashPumpPlugin.kt:987` |
| **Omnipod Eros** | ❌ No | Event-driven | `OmnipodErosPumpPlugin.kt:769` |
| **Dana RS/R** | ❌ No | User intervention | `AbstractDanaRPlugin.kt:361` |
| **Medtrum** | ✅ Yes | Automatic | `MedtrumPlugin.kt:408` |
| **Combo v2** | ✅ Yes | Automatic | `ComboV2Plugin.kt:1417` |
| **Equil** | ❌ No | Event-driven | `EquilPumpPlugin.kt:314` |

**AAPS TimeChangeType Enum** (`core/data/pump/defs/TimeChangeType.kt`):
```kotlin
enum class TimeChangeType {
    TimezoneChanged, DSTStarted, DSTEnded, TimeChanged
}
```

**Source**: `Pump.timezoneOrDSTChanged(timeChangeType: TimeChangeType)` callback

#### Loop "Fixed" Timezone Pattern

Loop uses a "fixed" timezone pattern to ensure schedule consistency:

```swift
// RileyLinkKit/Common/TimeZone.swift:12-13
static var currentFixed: TimeZone {
    return TimeZone(secondsFromGMT: TimeZone.current.secondsFromGMT())!
}
```

This creates a timezone with a **fixed UTC offset** (no DST rules) from the current moment. This ensures:
- Schedules don't shift during DST transitions
- Pump-stored schedules remain consistent
- Explicit user action required to update schedules after TZ change

**Implication**: Loop schedules are stored with fixed offsets, not IANA identifiers. A schedule created at `-0800` (PST) remains at `-0800` even when DST starts (PDT would be `-0700`).

#### Nightscout Profile Timezone Quirks

**Loop Non-Standard Format (GAP-TZ-006)**:
```javascript
// lib/profilefunctions.js:179-181
// Work around Loop uploading non-ISO compliant time zone string
if (rVal) rVal.replace('ETC','Etc');
```

Loop uploads timezone strings like `ETC/GMT+8` instead of the standard `Etc/GMT+8`.

**Missing Timezone Fallback**:
```javascript
// lib/profilefunctions.js:107-110
// Use local time zone if profile doesn't contain a time zone
// This WILL break on the server; added warnings elsewhere that this is missing
```

If no timezone is specified, Nightscout uses server local time, which can cause schedule misalignment.

#### utcOffset Recalculation Behavior (GAP-TZ-003)

Nightscout API v3 recalculates `utcOffset` from the `dateString` timezone if not explicitly provided:

```javascript
// lib/api3/generic/collection.js:181-183
if (typeof doc.utcOffset === 'undefined') {
  doc.utcOffset = m.utcOffset();
}
```

**Implication**: Client-provided `utcOffset` is preserved if present, but parsed from timestamp otherwise. This can lead to unexpected behavior when:
1. Client is in different TZ than the dateString indicates
2. Historical data is uploaded with ISO timestamps without offset

#### Schedule Offset Calculation

Loop's schedule offset logic handles the relationship between absolute time and schedule position:

```swift
// DailyValueSchedule.swift:126-132
func scheduleOffset(for date: Date) -> TimeInterval {
    // The time interval since a reference date in the specified time zone
    let interval = date.timeIntervalSinceReferenceDate + TimeInterval(timeZone.secondsFromGMT(for: date))
    
    // The offset of the time interval since the last occurrence of the reference time
    return ((interval - referenceTimeInterval).truncatingRemainder(dividingBy: repeatInterval)) + referenceTimeInterval
}
```

This uses `secondsFromGMT(for: date)` which **does** account for DST at the specific date, allowing proper schedule lookup even across DST boundaries.

#### Timezone and DST Gap Summary

| Gap ID | Description | Impact | Systems |
|--------|-------------|--------|---------|
| **GAP-TZ-001** | Most pump drivers cannot handle DST | Basal schedules off by 1h during transitions | AAPS (Medtronic, Omnipod, Dana) |
| **GAP-TZ-002** | Medtrum GMT+12 bug | Incorrect pump time in Pacific timezones | AAPS Medtrum |
| **GAP-TZ-003** | Nightscout recalculates utcOffset | Client offset may be overwritten | Nightscout API v3 |
| **GAP-TZ-004** | utcOffset unit mismatch | Minutes (NS) vs milliseconds (AAPS) | NS ↔ AAPS sync |
| **GAP-TZ-005** | AAPS fixed offset storage | Historical DST analysis incorrect | AAPS data export |
| **GAP-TZ-006** | Loop non-standard TZ format | `ETC/GMT` vs `Etc/GMT` case mismatch | Loop → NS |
| **GAP-TZ-007** | Missing TZ fallback | Server local time used if missing | All clients |

**Full Gap Details**: See [Timezone and DST Gaps](../../traceability/gaps.md#timezone-and-dst-gaps)

### Profile Sync Direction

| System | Upload | Download | Identity Field |
|--------|--------|----------|----------------|
| Loop | Optional | No | N/A |
| AAPS | Yes | Yes | `interfaceIDs.nightscoutId` |
| Trio | No | Yes | `_id` from NS |
| xDrip4iOS | No | Yes (read-only) | N/A |

**See Also**: [Profile/Therapy Settings Comparison](../../docs/60-research/profile-therapy-settings-comparison.md) for comprehensive cross-system analysis.

---

## Override/Adjustment Concepts

| Concept | Nightscout | Loop | AAPS | Trio | xDrip+ |
|---------|------------|------|------|------|--------|
| Override Active | `Temporary Override` active | `overrideContext != nil` | `ProfileSwitch.percentage != 100` | `Override.enabled` | N/A (no override) |
| Duration | `duration` (minutes) | `duration` (TimeInterval) | `duration` (minutes) | `duration` (minutes) | N/A |
| Reason/Name | `reason` | `preset.symbol` + `preset.name` | N/A | `reason` | N/A |
| Target Adjustment | `targetTop`/`targetBottom` | `settings.targetRange` | `targetLow`/`targetHigh` | `target` | N/A |
| Overall Insulin % | `insulinNeedsScaleFactor` | `settings.insulinNeedsScaleFactor` | `ProfileSwitch.percentage` | `insulinNeedsScaleFactor` | N/A |
| Supersession | N/A (gap) | Built-in (new cancels old) | N/A (last switch wins) | Built-in | N/A |

**Note**: xDrip+ is a CGM app without override/adjustment concepts. It receives and displays AAPS overrides but does not create them.
- Broadcast receiver for AAPS: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/services/broadcastservice/BroadcastService.java`

---

## Sync Identity Fields

> **See Also**: [Loop Sync Identity Deep Dive](../loop/sync-identity-fields.md) for ObjectIdCache pattern and treatment deduplication analysis.

| Controller | Nightscout Field | Purpose | Source Code |
|------------|------------------|---------|-------------|
| AAPS | `identifier` | Client-side unique ID | `database/entities/*.kt` |
| Loop | `syncIdentifier` | Pump hex or UUID | `LoopKit/DoseEntry.swift`, `CarbKit/StoredCarbEntry.swift` |
| Loop (cache) | ObjectIdCache | Maps syncIdentifier → NS _id (24hr memory) | `NightscoutServiceKit/ObjectIdCache.swift` |
| Trio | `syncIdentifier` | Inherits Loop pattern | `Trio/Sources/Services/Network/Nightscout/` |
| Trio (status) | OpenAPSStatus | DeviceStatus upload (iob, suggested, enacted) | `Trio/Sources/Models/NightscoutStatus.swift:10-14` |
| xDrip+ (Android) | `uuid` | Client-generated UUID | `models/Treatments.java#L85` |
| xDrip4iOS | `uuid` | Client-generated UUID | `Managers/Nightscout/*.swift` |
| Generic | `_id` | MongoDB ObjectId (server-generated) | N/A |

**Gap**: No unified sync identity field exists across controllers (GAP-003). Loop's ObjectIdCache is memory-only (GAP-SYNC-005), Loop uses v1 API only (GAP-SYNC-006), syncIdentifier format varies (GAP-SYNC-007).

---

## Authority/Actor Identity

| Concept | Nightscout | Loop | AAPS | Trio | xDrip+ |
|---------|------------|------|------|------|--------|
| Actor Identity | `enteredBy` (unverified) | `origin` | `pumpType` | `enteredBy` | `enteredBy: "xdrip"` |
| Authority Level | N/A (gap) | N/A | N/A | N/A | N/A |
| Verified Identity | Proposed (OIDC) | N/A | N/A | N/A | N/A |

**Gap**: No system tracks verified actor identity with authority levels (GAP-AUTH-001, GAP-AUTH-002).

### xDrip+ Unique Identifiers

| Identifier | Value | Source |
|------------|-------|--------|
| `enteredBy` | `"xdrip"` | `Treatments.XDRIP_TAG` constant |
| `device` | `"xDrip-" + manufacturer + model` | `NightscoutUploader.getDeviceName()` |
| User-Agent | `"xDrip+ " + BuildConfig.VERSION_NAME` | HTTP headers |

---

## Event Types Mapping

### Insulin Events

| Event | Nightscout eventType | Loop | AAPS | Trio |
|-------|---------------------|------|------|------|
| Meal Bolus | `Meal Bolus` | `Bolus` | `Bolus` | `Bolus` |
| Correction Bolus | `Correction Bolus` | `Bolus` | `Bolus` | `Bolus` |
| Temp Basal Start | `Temp Basal Start` | `TempBasal` | `TemporaryBasal` | `TempBasal` |
| Temp Basal End | `Temp Basal End` | (implicit) | (implicit) | (implicit) |

### Device Events

| Event | Nightscout eventType | Loop | AAPS | Trio | xDrip+ |
|-------|---------------------|------|------|------|--------|
| Sensor Start | `Sensor Start` | `CGMSensorEvent` | `TherapyEvent.SENSOR_CHANGE` | `SensorChange` | `Sensor Start` |
| Sensor Stop | N/A | N/A | N/A | N/A | `Sensor Stop` (unique) |
| Site Change | `Site Change` | `PumpEvent` | `TherapyEvent.CANNULA_CHANGE` | `SiteChange` | N/A |
| Pump Battery | `Pump Battery Change` | `PumpEvent` | `TherapyEvent` | `PumpBattery` | N/A |
| BG Check | `BG Check` | `BGCheck` | `TherapyEvent.FINGER_STICK_BG_VALUE` | `BGCheck` | `BG Check` |

---

## Code References

| Project | Override/Adjustment Model Location |
|---------|-----------------------------------|
| Nightscout | `crm:lib/plugins/careportal.js` |
| Loop | `loop:LoopKit/LoopKit/TemporaryScheduleOverride.swift` |
| AAPS | `aaps:database/impl/src/main/kotlin/app/aaps/database/entities/ProfileSwitch.kt` |
| Trio | `trio:Trio/Sources/Models/Override.swift` |
| xDrip+ (Android) | N/A (CGM-focused, no override) |

### xDrip+ Key Source Files

| Component | Location | Lines | Purpose |
|-----------|----------|-------|---------|
| BgReading | `models/BgReading.java` | ~2,394 | Core glucose entity |
| Treatments | `models/Treatments.java` | ~1,436 | Treatment/bolus/carb entity |
| Calibration | `models/Calibration.java` | ~1,123 | Calibration data |
| UploaderQueue | `utilitymodels/UploaderQueue.java` | ~557 | Multi-destination upload queue |
| NightscoutUploader | `utilitymodels/NightscoutUploader.java` | ~1,470 | Nightscout REST API client |
| NightscoutFollow | `cgm/nsfollow/NightscoutFollow.java` | ~135 | Follower mode |
| DexCollectionType | `utils/DexCollectionType.java` | ~392 | CGM source enum (20+ types) |

**Full documentation**: See `mapping/xdrip-android/` for comprehensive xDrip+ analysis.

---

## Algorithm/Controller Concepts

### Algorithm Recommendations

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Basal Recommendation | `rate`, `duration` in output | `TemporaryBasalRecommendation` | `APSResult.rate` | `Suggestion.rate` |
| Bolus Recommendation | `units` (SMB) | `BolusRecommendation` | `APSResult.smb` | `Suggestion.units` |
| Reason/Explanation | `reason` string | `recommendation.notice` | `APSResult.reason` | `Suggestion.reason` |
| Enact Timestamp | `deliverAt` | `date` | `date` | `deliverAt` |

### Prediction Types

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| IOB Prediction | `predBGs.IOB[]` | `predictedGlucose` (IOB effect) | `predictions.iob[]` | `predictions.IOB[]` |
| COB Prediction | `predBGs.COB[]` | `predictedGlucose` (carb effect) | `predictions.cob[]` | `predictions.COB[]` |
| UAM Prediction | `predBGs.UAM[]` | N/A (no UAM) | `predictions.uam[]` | `predictions.UAM[]` |
| Zero Temp Prediction | `predBGs.ZT[]` | N/A | `predictions.zt[]` | `predictions.ZT[]` |
| Eventual BG | `eventualBG` | `predictedGlucose.last` | `eventualBG` | `eventualBG` |

### Insulin Calculations

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Total IOB | `iob.iob` | `insulinOnBoard` | `iobTotal.iob` | `iob.iob` |
| Basal IOB | `iob.basaliob` | `basalDeliveryState.iob` | `iobTotal.basaliob` | `iob.basaliob` |
| Bolus Snooze IOB | `iob.bolussnooze` | N/A | `iobTotal.bolussnooze` | `iob.bolussnooze` |
| Insulin Activity | `iob.activity` | `insulinActivityForecast` | `iobTotal.activity` | `iob.activity` |

### Meal/Carb Calculations

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Carbs on Board | `meal.mealCOB` | `carbsOnBoard` | `iobCobCalculator.cob` | `meal.carbs` |
| Meal Absorption | `meal.slopeFromMaxDeviation` | `carbAbsorptionRate` | `carbsFromBolus` | `meal.slopeFromMaxDeviation` |
| Last Carb Time | `meal.lastCarbTime` | `lastCarbEntry.date` | `mealData.lastCarbTime` | `meal.lastCarbTime` |
| Unannounced Meal | UAM detection in algorithm | N/A | UAM via openAPSSMB | UAM in oref algorithm |

---

## Safety Constraints

### Maximum Limits

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Max IOB | `profile.max_iob` | `settings.maximumActiveInsulin` | `preferences.maxIOB` | `preferences.maxIOB` |
| Max Basal Rate | `profile.max_basal` | `settings.maximumBasalRate` | `preferences.maxBasal` | `preferences.maxBasal` |
| Max Bolus | N/A (SMB limit) | `settings.maximumBolus` | `preferences.maxBolus` | `preferences.maxBolus` |
| Max SMB | `profile.maxSMBBasalMinutes` | N/A (no SMB) | `preferences.maxSMBBasalMinutes` | `preferences.maxSMBBasalMinutes` |
| Max Daily Basal Multiplier | `profile.max_daily_safety_multiplier` | N/A | `maxDailySafetyMultiplier` | `maxDailySafetyMultiplier` |
| Current Basal Multiplier | `profile.current_basal_safety_multiplier` | N/A | `currentBasalSafetyMultiplier` | `currentBasalSafetyMultiplier` |

### Low Glucose Safety

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Suspend Threshold | N/A (uses min_bg) | `settings.suspendThreshold` | `preferences.lgsThreshold` | `preferences.suspendThreshold` |
| Min BG Target | `profile.min_bg` | `GlucoseRangeSchedule.minValue` | `profile.targetLow` | `target_low` |

### Autosensitivity

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Sensitivity Ratio | `sensitivityRatio` | `insulinSensitivity` | `autosensData.ratio` | `sensitivityRatio` |
| Autosens Max | `profile.autosens_max` | N/A | `autosensMax` | `autosensMax` |
| Autosens Min | `profile.autosens_min` | N/A | `autosensMin` | `autosensMin` |
| Autosens Adjust Targets | `profile.autosens_adjust_targets` | N/A | `autosensAdjustTargets` | `autosensAdjustTargets` |

---

## Pump Commands

### Basal Commands

| Alignment Term | oref0/openaps | Loop | AAPS | Trio |
|----------------|---------------|------|------|------|
| Set Temp Basal | `set_temp_basal` | `enactTempBasal()` | `tempBasalAbsolute()` | `enactTempBasal()` |
| Cancel Temp Basal | `set_temp_basal(rate=0)` | `cancelTempBasal()` | `cancelTempBasal()` | `cancelTempBasal()` |
| Suspend | `suspend_pump` | `suspendDelivery()` | `suspendPump()` | `suspendDelivery()` |
| Resume | `resume_pump` | `resumeDelivery()` | `resumePump()` | `resumeDelivery()` |

### Bolus Commands

| Alignment Term | oref0/openaps | Loop | AAPS | Trio |
|----------------|---------------|------|------|------|
| Deliver Bolus | N/A (manual) | `enactBolus()` | `deliverBolus()` | `enactBolus()` |
| Deliver SMB | via rig | N/A (no SMB) | `deliverSMB()` | `enactSMB()` |
| Cancel Bolus | N/A | `cancelBolus()` | `stopBolusDelivering()` | `cancelBolus()` |

### Status Queries

| Alignment Term | oref0/openaps | Loop | AAPS | Trio |
|----------------|---------------|------|------|------|
| Get Pump Status | `read_pump_status` | `getPumpStatus()` | `readPumpStatus()` | `getPumpStatus()` |
| Get Reservoir | `reservoir` | `reservoirLevel` | `remainingInsulin` | `reservoir` |
| Get Battery | `battery` | `batteryLevel` | `batteryLevel` | `battery` |

---

## Pump Protocol Models (Deep Dive)

> **See Also**: [Pump Protocols Specification](../../specs/pump-protocols-spec.md) for comprehensive low-level protocol documentation.

### Transport Layer Comparison

| Aspect | Omnipod DASH | Dana RS | Medtronic |
|--------|--------------|---------|-----------|
| **Transport** | BLE Direct | BLE Direct | RF (916.5/868 MHz) |
| **Bridge Device** | No | No | RileyLink required |
| **MTU** | 20 bytes | 20 bytes | 64 bytes |
| **Encryption** | AES-128-CCM | Matrix + XOR | None |
| **Session Auth** | EAP-AKA (Milenage) | Time + Password | Serial check |

### Omnipod DASH Message Structure

| Component | Offset | Size | Description |
|-----------|--------|------|-------------|
| Magic | 0 | 2 | "TW" pattern |
| Flags | 2 | 2 | Version, SAS, TFS, EQOS, ack, priority |
| Sequence | 4 | 1 | Message sequence number |
| Ack Num | 5 | 1 | Acknowledgment number |
| Payload Size | 6 | 2 | 11-bit size (shifted) |
| Source ID | 8 | 4 | Controller address |
| Dest ID | 12 | 4 | Pod address |
| Payload | 16 | N | Data + 8-byte MAC for encrypted |

**Source**: `OmniBLE/Bluetooth/MessagePacket.swift`

### Omnipod DASH Command Opcodes

| Opcode | Command | Direction | Description |
|--------|---------|-----------|-------------|
| `0x01` | VersionResponse | Pod→Ctrl | Pod version info |
| `0x07` | AssignAddress | Ctrl→Pod | Assign pod address |
| `0x0e` | GetStatus | Ctrl→Pod | Request status |
| `0x17` | BolusExtra | Ctrl→Pod | Extended bolus params |
| `0x1a` | SetInsulinSchedule | Ctrl→Pod | Main delivery command |
| `0x1d` | StatusResponse | Pod→Ctrl | Current status |
| `0x1f` | CancelDelivery | Ctrl→Pod | Stop delivery |

**Source**: `OmniBLE/OmnipodCommon/MessageBlocks/MessageBlock.swift`

### Omnipod Delivery Constants

| Constant | Value | Unit |
|----------|-------|------|
| Pulse Size | 0.05 | U |
| Pulses per Unit | 20 | pulses/U |
| Bolus Delivery Rate | 0.025 | U/s |
| Max Reservoir Reading | 50 | U |
| Service Duration | 80 | hours |

**Source**: `OmniBLE/OmnipodCommon/Pod.swift`

### Dana RS Packet Structure

| Component | Offset | Size | Description |
|-----------|--------|------|-------------|
| Start Bytes | 0 | 2 | `0xA5 0xA5` |
| Length | 2 | 1 | Packet size - 7 |
| Type | 3 | 1 | Command type |
| OpCode | 4 | 1 | Command code |
| Data | 5 | N | Payload |
| CRC | -4 | 2 | CRC-16 (big-endian) |
| End Bytes | -2 | 2 | `0x5A 0x5A` |

**Source**: `pump/danars/comm/DanaRSPacket.kt`

### Dana RS Encryption Modes

| Mode | Description | CRC Variant |
|------|-------------|-------------|
| DEFAULT | Legacy (time + password + SN) | Standard polynomial |
| RSv3 | Pairing key + random key + matrix | Modified polynomial |
| BLE5 | 6-digit PIN + matrix (Dana-i) | BLE5-specific polynomial |

**Source**: `pump/danars/encryption/BleEncryption.kt`

### Medtronic History Entry Types

| Code | Entry | Head | Date | Body |
|------|-------|------|------|------|
| `0x01` | Bolus | 4 (8 on 523+) | 5 | 0 |
| `0x16` | TempBasalDuration | 2 | 5 | 0 |
| `0x33` | TempBasalRate | 2 | 5 | 1 |
| `0x1e` | SuspendPump | 2 | 5 | 0 |
| `0x6e` | DailyTotals523 | 1 | 2 | 49 |

**Source**: `pump/medtronic/comm/history/pump/PumpHistoryEntryType.kt`

### Pump Protocol Gap Summary

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-PUMP-006** | Medtronic RF lacks encryption | Replay attacks possible |
| **GAP-PUMP-007** | Omnipod uses non-standard Milenage | Requires Insulet-specific constants |
| **GAP-PUMP-008** | Dana RS encryption mode detection | Must handle 3 modes |
| **GAP-PUMP-009** | Medtronic history size varies by model | Parsing must be model-aware |

**Full details**: See [Pump Protocols Specification](../../specs/pump-protocols-spec.md)

---

## Insulin Curve Models (Deep Dive)

> **See Also**: [Insulin Curves Deep Dive](../../docs/10-domain/insulin-curves-deep-dive.md) for comprehensive cross-system analysis of insulin activity curves, mathematical formulas, and IOB calculations.

### Mathematical Model Comparison

| System | Primary Model | Formula Source | Legacy Model |
|--------|---------------|----------------|--------------|
| **Loop** | Exponential | Original | N/A |
| **oref0** | Exponential | Loop (copied) | Bilinear |
| **AAPS** | Exponential | oref0 (port) | N/A |
| **Trio** | Exponential | oref0 (via JS) | Bilinear |
| **xDrip+** | Linear Trapezoid | Independent | N/A |

**Key Finding**: All major AID systems share the **same exponential insulin model**. oref0 explicitly credits Loop as the source: `// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473`

### Insulin Type Presets

| Preset | Loop Peak | oref0 Peak | AAPS Peak | Trio Peak | Delay |
|--------|-----------|------------|-----------|-----------|-------|
| Rapid-Acting Adult | 75 min | 75 min | 75 min | 75 min | Loop: 10 min, others: 0 |
| Rapid-Acting Child | 65 min | N/A | N/A | N/A | 10 min |
| Ultra-Rapid / Fiasp | 55 min | 55 min | 55 min | 55 min | Loop: 10 min, others: 0 |
| Lyumjev | **55 min** | 55 min | **45 min** | 55 min | Loop: 10 min, others: 0 |
| Afrezza (Inhaled) | 29 min | N/A | N/A | N/A | 10 min |
| Free Peak | N/A | 50-120 min | Configurable | Configurable | 0 |

**Important**: Peak times are NOT equivalent across systems. AAPS Lyumjev uses **45 min** while Loop uses **55 min**. Loop also includes a 10-minute delay before activity starts that oref0/AAPS/Trio do not have.

### DIA (Duration of Insulin Action) Constraints

| System | Minimum DIA | Default DIA | Enforcement |
|--------|-------------|-------------|-------------|
| **Loop** | Fixed per preset | 5-6 hr | Hardcoded in model |
| **oref0 (bilinear)** | 3 hr | 3 hr | Soft clamp |
| **oref0 (exponential)** | 5 hr | 5 hr | `requireLongDia` flag |
| **AAPS** | 5 hr | 5 hr | `hardLimits.minDia()` |
| **Trio** | 5 hr | Profile-defined | Via oref0 |
| **xDrip+** | None | Per profile | User configurable |

### Insulin Model Implementation

| Aspect | oref0 | Loop | AAPS | Trio | xDrip+ |
|--------|-------|------|------|------|--------|
| **Source File** | `lib/iob/calculate.js` | `ExponentialInsulinModel.swift` | `InsulinOrefBasePlugin.kt` | `lib/iob/index.js` | `LinearTrapezoidInsulin.java` |
| **Model Class** | N/A (function) | `InsulinModel` protocol | `Insulin` interface | N/A (function) | `Insulin` abstract class |
| **Peak Config** | `profile.insulinPeakTime` | Per preset | Plugin-specific | `preferences.insulinPeakTime` | Per profile JSON |
| **DIA Config** | `profile.dia` | Per preset | `profile.dia` | `pumpSettings.insulinActionCurve` | `Insulin.maxEffect` |
| **Custom Peak** | Yes (ranges) | No | Yes (Free Peak) | Yes (via oref0) | Yes (JSON config) |

### IOB Calculation Components

| Component | oref0 | Loop | AAPS | Trio | xDrip+ |
|-----------|-------|------|------|------|--------|
| **Total IOB** | `iob.iob` | `insulinOnBoard` | `iobTotal.iob` | `iob.iob` | `Iob.getIobAtTime()` |
| **Basal IOB** | `iob.basaliob` | N/A (combined) | `iobTotal.basaliob` | `iob.basaliob` | Not applicable (no basal tracking) |
| **Bolus IOB** | `iob.bolusiob` | N/A (combined) | N/A | `iob.bolusiob` | Not applicable (no basal/bolus split) |
| **Activity** | `iob.activity` | N/A | `iobTotal.activity` | `iob.activity` | `calculateActivity()` |
| **Bolus Snooze** | `iob.bolussnooze` | N/A | `iobTotal.bolussnooze` | `iob.bolussnooze` | Not applicable |
| **Zero Temp IOB** | `iob.iobWithZeroTemp` | N/A | `iobWithZeroTemp` | `iobWithZeroTemp` | Not applicable |

**xDrip+ Note**: xDrip+ tracks total IOB from all insulin injections but does not distinguish basal vs bolus IOB (it tracks injections, not pump-controlled basals). The `Iob.getIobBreakdown()` method provides IOB per insulin type (e.g., NovoRapid vs Lantus), not basal/bolus split.

### xDrip+ Multi-Insulin Support

xDrip+ uniquely supports multiple insulin types per treatment:

| Feature | xDrip+ | AID Systems |
|---------|--------|-------------|
| **Multi-Insulin Per Treatment** | ✅ `insulinJSON` array | No |
| **Long-Acting Insulin Tracking** | ✅ (13+ types) | No |
| **Concentration Support** | U100-U500 | U100-U200 (AAPS only) |
| **IOB Per Insulin Type** | ✅ `Iob.getIobBreakdown()` | No |
| **Smart Pen Integration** | InPen, Pendiq, NovoPen | No |

**xDrip+ Insulin Profiles**: `externals/xDrip/app/src/main/res/raw/insulin_profiles.json`

### Insulin Curve Gap Summary

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-INS-001** | Insulin model metadata not synced to Nightscout | Cannot determine which curve produced IOB |
| **GAP-INS-002** | No standardized multi-insulin representation | xDrip+ `insulinJSON` is non-portable |
| **GAP-INS-003** | Peak time customization not captured in treatments | Cannot reproduce historical IOB calculations |
| **GAP-INS-004** | xDrip+ linear trapezoid model incompatible | IOB values differ from AID exponential models |

**Full gap details**: See [Insulin Curves Deep Dive - Related Gaps](../../docs/10-domain/insulin-curves-deep-dive.md#related-gaps)

---

## Loop Cycle States

| Alignment Term | oref0 | Loop | AAPS | Trio |
|----------------|-------|------|------|------|
| Loop Running | rig running | `loopManager.isLoopRunning` | `loop.isEnabled` | `isLooping` |
| Loop Suspended | rig stopped | `loopManager.isSuspended` | `loop.isSuspended` | `isSuspended` |
| Open Loop Mode | N/A (always closed) | `closedLoop = false` | `isOpenLoop` | `closedLoop = false` |
| Closed Loop Mode | default | `closedLoop = true` | `isClosedLoop` | `closedLoop = true` |
| Last Loop Time | cron timestamp | `lastLoopCompleted` | `lastRun` | `lastLoopDate` |

---

## Algorithm Variants

| Variant | oref0 | Loop | AAPS | Trio |
|---------|-------|------|------|------|
| AMA (Advanced Meal Assist) | `determine-basal.js` with AMA | N/A | `OpenAPSAMAPlugin` | N/A |
| SMB (Super Micro Bolus) | oref1 SMB mode | N/A (no SMB) | `OpenAPSSMBPlugin` | oref1 SMB |
| AutoISF | N/A | N/A | `OpenAPSAutoISFPlugin` | N/A |
| Autotune | `lib/autotune/` | N/A | `AutotunePlugin` | Autotune module |

---

## Algorithm Core Terminology

> **See Also**: [Algorithm Comparison Deep Dive](../../docs/10-domain/algorithm-comparison-deep-dive.md)

### Insulin Sensitivity Factor (ISF)

| System | Term | Type/Class | File |
|--------|------|------------|------|
| **oref0** | `sens` | Number (mg/dL/U) | `lib/profile/isf.js` |
| **Loop** | `insulinSensitivity` | `InsulinSensitivitySchedule` | `LoopKit/TherapySettings.swift` |
| **AAPS** | `isf` / `getIsfMgdl()` | `ProfileSwitch.isfBlocks` | `core/interfaces/profile/Profile.kt` |
| **Trio** | `sensitivity` | `InsulinSensitivityEntry` | `Models/InsulinSensitivities.swift` |

**Description**: Drop in glucose (mg/dL or mmol/L) expected from one unit of insulin.

### Carb Ratio (CR / ICR)

| System | Term | Type/Class | File |
|--------|------|------------|------|
| **oref0** | `carb_ratio` | Number (g/U) | `lib/profile/carbs.js` |
| **Loop** | `carbRatio` | `CarbRatioSchedule` | `LoopKit/TherapySettings.swift` |
| **AAPS** | `ic` / `getIc()` | `ProfileSwitch.icBlocks` | `core/interfaces/profile/Profile.kt` |
| **Trio** | `ratio` | `CarbRatioEntry` | `Models/CarbRatios.swift` |

**Description**: Grams of carbohydrates covered by one unit of insulin.

### Duration of Insulin Action (DIA)

| System | Term | Type/Class | Default | File |
|--------|------|------------|---------|------|
| **oref0** | `dia` | Number (hours) | 5-6h | `lib/iob/total.js` |
| **Loop** | `actionDuration` | `TimeInterval` | 360 min (6h) | `LoopKit/InsulinKit/ExponentialInsulinModel.swift` |
| **AAPS** | `dia` | Double (hours) | 5h min | `OapsProfile.kt` |
| **Trio** | `actionDuration` | `TimeInterval` | From model | `LoopKit/InsulinKit/ExponentialInsulinModel.swift` |

**Description**: Time over which insulin has glucose-lowering effect.

### Unannounced Meal Detection (UAM)

| System | Term | Supported | Configuration | File |
|--------|------|-----------|---------------|------|
| **oref0** | `enableUAM` | ✅ Yes | Boolean flag | `lib/profile/index.js` |
| **Loop** | `MissedMeal` | ⚠️ Notification only | Detection, no dosing | `Managers/MissedMealSettings.swift` |
| **AAPS** | `enableUAM` | ✅ Yes | Boolean + `maxUAMSMBBasalMinutes` | `SMBDefaults.kt` |
| **Trio** | `enableUAM` | ✅ Yes | Boolean + `maxUAMSMBBasalMinutes` | `SMBSettingsStateModel.swift` |

**Description**: Detection of carb absorption from unannounced/un-logged meals. Allows algorithm to respond to rising glucose even without carb entry.

**Gap**: Loop does not have full UAM - only missed meal notifications without automatic dosing adjustment.

### Super Micro Bolus (SMB)

| System | Term | Supported | Configuration Flags | File |
|--------|------|-----------|---------------------|------|
| **oref0** | `enableSMB_*` | ✅ Yes (oref1) | `enableSMB_with_COB`, `enableSMB_always`, `enableSMB_after_carbs` | `lib/profile/index.js` |
| **Loop** | N/A | ❌ No | N/A | N/A |
| **AAPS** | `SMB` | ✅ Yes | `SMBInterval`, `maxSMBBasalMinutes`, multiple enable flags | `SMBDefaults.kt` |
| **Trio** | `SMB` | ✅ Yes | `enableSMBAlways`, `enableSMBWithCOB`, `enableSMBWithTemptarget`, etc. | `SMBSettingsStateModel.swift` |

**Description**: Small bolus doses delivered automatically to accelerate glucose correction beyond what temp basal alone can achieve.

**Gap**: Loop does not support SMB. Uses temp basal adjustments only.

### Autosens (Sensitivity Detection)

| System | Term | Output | Range | File |
|--------|------|--------|-------|------|
| **oref0** | `sensitivityRatio` | Multiplier (0.7-1.2 default) | `autosens_min` to `autosens_max` | `lib/determine-basal/autosens.js` |
| **Loop** | N/A | ❌ No autosens | N/A | N/A (uses `RetrospectiveCorrection`) |
| **AAPS** | `AutosensResult.ratio` | Multiplier | Configurable min/max | `core/interfaces/aps/AutosensResult.kt` |
| **Trio** | `autosens.ratio` | Multiplier | Configurable | `Models/Autosens.swift` |

**Description**: Automatic detection of insulin sensitivity changes based on recent glucose deviations from predictions.

**Loop Alternative**: `RetrospectiveCorrection` detects discrepancies but does NOT adjust ISF dynamically.

### Feature Support Matrix

| Feature | oref0 | Loop | AAPS | Trio |
|---------|-------|------|------|------|
| ISF Schedule | ✅ | ✅ | ✅ | ✅ |
| Carb Ratio Schedule | ✅ | ✅ | ✅ | ✅ |
| DIA Setting | ✅ | ✅ | ✅ | ✅ |
| UAM Detection | ✅ | ⚠️ Notify only | ✅ | ✅ |
| SMB Delivery | ✅ | ❌ | ✅ | ✅ |
| Autosens | ✅ | ❌ (uses RC) | ✅ | ✅ |
| Dynamic ISF | ❌ | ❌ | ✅ (DynISF) | ✅ |
| Autotune | ✅ | ❌ | ✅ | ✅ |
| 4 Prediction Curves | ✅ | ❌ (single) | ✅ | ✅ |
| RetrospectiveCorrection | ❌ | ✅ | ❌ | ❌ |

### Key Differences Summary

1. **Loop vs oref0 family**: Loop lacks UAM (full), SMB, and Autosens. Uses different paradigm (single prediction curve vs 4 curves). Uses RetrospectiveCorrection instead of Autosens.

2. **Terminology variance**:
   - ISF: `sens` (oref0/Trio) vs `insulinSensitivity` (Loop) vs `isf` (AAPS)
   - CR: `carb_ratio` (oref0) vs `carbRatio` (Loop) vs `ic` (AAPS)

3. **Config structure**: oref0/Trio use flat JSON config; AAPS uses entity blocks; Loop uses Swift structs with schedule arrays.

4. **Input formats**: oref0 expects pre-computed IOB/COB; Loop computes from raw dose/carb history.

**Gap Reference**: GAP-ALG-005 (Loop lacks SMB/UAM), GAP-ALG-006 (DynISF TDD-based vs deviation-based), GAP-ALG-013..016 (Loop architecture differences)

**See Also**: [Loop vs oref0 Semantic Equivalence](../../docs/10-domain/loop-oref0-semantic-equivalence.md)

### AAPS-Specific Algorithm Variants

AAPS extends oref0 with additional ISF calculation algorithms not present in vanilla oref0:

| Algorithm | Class | ISF Calculation | Pass Rate vs oref0 |
|-----------|-------|-----------------|---------------------|
| **OpenAPSSMBPlugin** | Standard oref0 port | Static from profile | 94% |
| **OpenAPSAMAPlugin** | Advanced Meal Assist | Static from profile | 67% |
| **OpenAPSSMBDynamicISFPlugin** | TDD-based ISF | `1800 / (TDD × ln(BG/divisor + 1))` | 18% |
| **OpenAPSSMBAutoISFPlugin** | Sigmoid-adjusted ISF | Multi-factor: BG, bolus time, exercise | 5% |

**Dynamic ISF Formula**:
```kotlin
// externals/AndroidAPS/plugins/aps/src/main/kotlin/app/aaps/plugins/aps/openAPSSMB/DetermineBasalAdapterSMBDynamicISFJS.kt
val variableSensitivity = 1800 / (tdd * ln((glucose / insulinDivisor) + 1))
```

**TDD Weighting**:
```kotlin
val tddWeightedFromLast8H = ((1.4 * tddLast4H) + (0.6 * tddLast8to4H)) * 3
val tdd = ((tddWeightedFromLast8H * 0.33) + (tdd7D * 0.34) + (tdd1D * 0.33)) * adjustmentFactor
```

**Gap Reference**: GAP-ALG-009 (DynamicISF not in oref0), GAP-ALG-010 (AutoISF not in oref0)

**See Also**: [AAPS vs oref0 Divergence Analysis](../../docs/10-domain/aaps-oref0-divergence-analysis.md)

---

## CGM Source Models (Deep Dive)

> **See Also**: [CGM Data Sources Deep Dive](../../docs/10-domain/cgm-data-sources-deep-dive.md) for comprehensive analysis of how CGM data flows from sensors to Nightscout.

### Data Source Types

| Source Category | xDrip+ Android | xDrip4iOS | Loop | AAPS |
|-----------------|----------------|-----------|------|------|
| **Direct Bluetooth** | G5, G6, G7, Medtrum, GluPro | G5, G6, G7, Libre 2 | CGMBLEKit, G7SensorKit | Via xDrip+ |
| **Bridge Devices** | 6+ (MiaoMiao, Bubble, Wixel, etc.) | 4 (MiaoMiao, Bubble, Blucon, Atom) | No | Via xDrip+ |
| **Cloud Followers** | NS, Share, CareLink, WebFollow | NS, Share, LibreLinkUp | Share only | NS only |
| **Companion Apps** | 5+ (LibreAlarm, NSEmulator, etc.) | No | No | No |
| **Local Web Server** | Yes (port 17580) | No | No | No |
| **Total Source Types** | 20+ | ~6 | 3-4 | Via xDrip+ |

### Calibration Models

| System | Calibration Options | Description |
|--------|---------------------|-------------|
| **xDrip+ Android** | xDrip Original, Native, Datricsae, Last7Unweighted, FixedSlope | Pluggable algorithms |
| **xDrip4iOS** | Native, WebOOP | Transmitter calibration or OOP server |
| **Loop** | Native only | Transmitter-calibrated readings |
| **AAPS** | Via xDrip+ | Inherits xDrip+ calibration |
| **Trio** | Native only | Transmitter-calibrated readings |

### BgReading Entity Mapping

| Field | xDrip+ Android | xDrip4iOS | Loop | AAPS | Nightscout |
|-------|----------------|-----------|------|------|------------|
| **Glucose Value** | `calculated_value` | `calculatedValue` | `quantity` | `value` | `sgv` |
| **Timestamp** | `timestamp` | `timeStamp` | `startDate` | `timestamp` | `date` |
| **Raw Value** | `raw_data` | `rawData` | N/A | N/A | `unfiltered` |
| **Filtered Value** | `filtered_data` | `filteredData` | N/A | N/A | `filtered` |
| **Trend Slope** | `dg_slope` | `calculatedValueSlope` | `trendType` | `trendArrow` | `direction` |
| **Noise** | `noise` | N/A | N/A | `noise` | `noise` |
| **Sync Identity** | `uuid` | `uuid` | N/A | `interfaceIDs` | `_id` |
| **Source Info** | `source_info` | `deviceName` | `provenanceIdentifier` | `sourceSensor` | `device` |

### Follower Data Sources

| Follower Type | xDrip+ Android | xDrip4iOS | Loop | Trio |
|---------------|----------------|-----------|------|------|
| **Nightscout** | `NSFollow` | `NightscoutFollowManager` | N/A | Via CGMManager |
| **Dexcom Share** | `SHFollow` | `DexcomShareFollowManager` | `ShareClient` | `ShareClient` |
| **LibreLinkUp** | No | `LibreLinkUpFollowManager` | No | No |
| **CareLink** | `CLFollow` | No | No | No |
| **Generic Web** | `WebFollow` | No | No | No |

### Collection Type Enum (xDrip+ Android)

```java
// DexCollectionType categories
usesBluetooth:  BluetoothWixel, DexcomShare, DexbridgeWixel, LimiTTer, ...
usesWifi:       WifiWixel, WifiBlueToothWixel, Mock, LimiTTerWifi, ...
usesLibre:      LimiTTer, LibreAlarm, LimiTTerWifi, LibreWifi, LibreReceiver
isPassive:      NSEmulator, NSFollow, SHFollow, WebFollow, LibreReceiver, ...
usesDexcomRaw:  BluetoothWixel, DexbridgeWixel, WifiWixel, DexcomG5, ...
```

### CGM Data Provenance Gap Summary

| Gap ID | Description | Impact |
|--------|-------------|--------|
| **GAP-CGM-001** | Calibration algorithm not tracked | Cannot determine calibration quality |
| **GAP-CGM-002** | Bridge device info lost in upload | Cannot identify hardware issues |
| **GAP-CGM-003** | Sensor age not standardized | Cannot assess reading reliability |
| **GAP-CGM-004** | No universal source taxonomy | Free-form `device` field unreliable |
| **GAP-CGM-005** | Raw values not uploaded by iOS | Cannot recalibrate or validate |
| **GAP-CGM-006** | Follower source not distinguished | Cannot tell direct vs cloud data |

**Full gap details**: See [CGM Data Sources Deep Dive - Gap Summary](../../docs/10-domain/cgm-data-sources-deep-dive.md#gap-summary)

---

## Algorithm Comparison (Deep Dive)

> **See Also**: [Algorithm Comparison Deep Dive](../../docs/10-domain/algorithm-comparison-deep-dive.md) for comprehensive cross-system analysis explaining why the same CGM data produces different dosing recommendations.

### Prediction Methodology

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| **Prediction Style** | Single combined curve | 4 separate curves (IOB, COB, UAM, ZT) |
| **Effect Combination** | All effects summed + momentum blend | Each curve independent |
| **Decision Basis** | Minimize combined prediction excursions | Use minPredBG across all curves |
| **UAM Handling** | Implicitly via Retrospective Correction | Explicit UAM curve |
| **Safety Floor** | Combined prediction minimum | ZT curve provides floor |

### Carb Absorption Models

| Aspect | Loop | oref0/AAPS/Trio |
|--------|------|-----------------|
| **Model Type** | Dynamic piecewise linear | Linear decay with assumed rate |
| **Adaptation** | Real-time based on ICE (Insulin Counteraction Effects) | Limited deviation-based |
| **Absorption Time** | Per-entry (user or default) | Global `carbs_hr` rate |
| **Fast Carbs** | Handles via dynamic adaptation | Handled via UAM curve |

### Sensitivity Adjustment Mechanisms

| Mechanism | Loop | oref0 | AAPS | Trio |
|-----------|------|-------|------|------|
| **Real-time** | Retrospective Correction | Via deviation | Via deviation | Via deviation |
| **Historical Pattern** | No | Autosens (8-24h) | Autosens or DynISF | Autosens |
| **TDD-Based** | No | No | Dynamic ISF option | No |
| **Override/Preset** | Override presets | Temp target | Profile switch % | Override profiles |

### Algorithm Interoperability Gaps

| Gap ID | Description | Systems Affected |
|--------|-------------|------------------|
| **GAP-ALG-001** | Insulin model configuration differs (preset vs DIA field) | Loop vs oref0/AAPS/Trio |
| **GAP-ALG-002** | Carb absorption model differs (dynamic vs linear) | Loop vs oref0/AAPS/Trio |
| **GAP-ALG-003** | Sensitivity mechanism differs (RC vs Autosens) | Loop vs oref0/AAPS/Trio |
| **GAP-ALG-004** | Loop has no explicit UAM curve (relies on RC instead) | Loop |
| **GAP-ALG-005** | Loop has no SMB algorithm (Loop 3 auto-bolus is distinct from SMB) | Loop |
| **GAP-ALG-006** | AAPS DynISF is TDD-based while others are deviation-based | AAPS vs others |
| **GAP-ALG-007** | Trio supports SMB time-window scheduling (`smbIsScheduledOff`) | Trio |
| **GAP-ALG-008** | Prediction transparency differs (1 combined curve vs 4 separate curves) | Loop vs oref0/AAPS/Trio |

**Full gap details with source citations**: See [Algorithm Comparison Deep Dive - Section 7](../../docs/10-domain/algorithm-comparison-deep-dive.md#7-identified-gaps)

---

## Notes for Implementers

1. **AAPS has no explicit "Override" concept** - Use ProfileSwitch with percentage/target modifications
2. **Loop conflates overrides and temp targets** - Both are handled via TemporaryScheduleOverride
3. **Nightscout separates Override and Temp Target** - Different eventTypes for different use cases
4. **Trio follows OpenAPS patterns** - Similar to Nightscout with some extensions
5. **Loop does not use oref0** - Has its own prediction and dosing algorithm (LoopMath)
6. **AAPS and Trio embed oref0** - AAPS has ported oref0 to native Kotlin (not JavaScript bridge)
7. **SMB (Super Micro Bolus)** - Only available in oref1-based systems (AAPS, Trio), not Loop
8. **Autosens** - Available in oref0/AAPS/Trio, Loop uses different sensitivity approach (RC)
9. **Dynamic ISF** - AAPS supports TDD-based variable sensitivity (DynISF), Loop has IRC

---

## Pending API Extensions (from PR Analysis)

These concepts are in open PRs awaiting merge:

### Heart Rate Collection (PR#8083)

| Concept | Status | Description |
|---------|--------|-------------|
| HeartRate collection | Pending | New APIv3 collection for HR data |
| HR timestamp | Pending | ISO8601 with millisecond precision |
| HR source | Pending | Device that captured HR (watch, pump) |
| HR bpm | Pending | Beats per minute value |

**Gap**: GAP-API-HR

### Multi-Insulin API (PR#8261)

| Concept | xDrip+ | nightscout-reporter | Nightscout |
|---------|--------|---------------------|------------|
| Insulin entity | ✓ uses | ✓ uses | pending |
| Insulin curve | custom JSON | custom JSON | pending |
| Insulin color | #RRGGBB | #RRGGBB | pending |
| Insulin active | boolean | boolean | pending |

**Gap**: GAP-INSULIN-001

### Remote Commands (PR#7791)

| Concept | Loop | Nightscout |
|---------|------|------------|
| Command queue | push notification | pending |
| Command status | none | pending |
| Command expiration | implicit | pending |
| Delivery confirmation | none | pending |

**Gap**: GAP-REMOTE-CMD

---

## AAPS-Specific Concepts

### Nightscout SDK (NSSDK)

AAPS maintains a dedicated Nightscout SDK (`core/nssdk/`) with local model classes:

| AAPS NSSDK Class | Nightscout Collection | Key Fields |
|------------------|----------------------|------------|
| `NSSgvV3` | `entries` | `sgv`, `direction`, `noise` |
| `NSBolus` | `treatments` | `insulin`, `type` (NORMAL/SMB/PRIMING) |
| `NSCarbs` | `treatments` | `carbs`, `duration` (eCarbs) |
| `NSTemporaryBasal` | `treatments` | `rate`, `duration`, `type` |
| `NSProfileSwitch` | `treatments` | `profile`, `percentage`, `timeShift` |
| `NSTemporaryTarget` | `treatments` | `targetTop`, `targetBottom`, `reason` |
| `NSDeviceStatus` | `devicestatus` | `openaps`, `pump`, `configuration` |
| `NSTherapyEvent` | `treatments` | `eventType`, `notes` |

**Remote Model Classes** (verified 2026-01-29):

| Remote Model | Source | Key Fields |
|--------------|--------|------------|
| `RemoteTreatment` | `remotemodel/RemoteTreatment.kt:18-79` | `identifier`, `eventType`, `insulin`, `carbs`, `isSMB` |
| `RemoteEntry` | `remotemodel/RemoteEntry.kt:15-34` | `type`, `sgv`, `direction`, `noise`, `filtered` |
| `EventType` | `localmodel/treatment/EventType.kt` | 25 enum values mapping to NS eventTypes |

### ProfileSwitch Modifiers (GAP-002)

AAPS ProfileSwitch has semantic fields that Nightscout doesn't distinguish:

| Modifier | Field | Effect |
|----------|-------|--------|
| Complete Switch | `profileName` changes | New profile settings |
| Percentage | `percentage != 100` | All insulin delivery scaled |
| Time Shift | `timeshift != 0` | Schedule shifted |
| Duration | `duration > 0` | Temporary vs permanent |

### Bolus Types

AAPS distinguishes bolus types via enum:

| Type | Description | NS Mapping |
|------|-------------|------------|
| `NORMAL` | User-initiated bolus | `Meal Bolus` or `Correction Bolus` |
| `SMB` | Super Micro Bolus (automatic) | `SMB` eventType |
| `PRIMING` | Pump priming (not therapy) | `Prime` eventType |

### Temp Basal Types

| Type | Description |
|------|-------------|
| `NORMAL` | Standard temp basal |
| `EMULATED_PUMP_SUSPEND` | Suspend via 0% basal |
| `PUMP_SUSPEND` | Actual pump suspend |
| `SUPERBOLUS` | Superbolus temp basal |
| `FAKE_EXTENDED` | Extended bolus emulation |

### Insulin Model Peak Times

| AAPS Plugin | Peak (minutes) | Insulin Type |
|-------------|----------------|--------------|
| `InsulinOrefRapidActingPlugin` | 75 | NovoRapid, Humalog, Apidra |
| `InsulinOrefUltraRapidActingPlugin` | 55 | Fiasp |
| `InsulinLyumjevPlugin` | 45 | Lyumjev |
| `InsulinOrefFreePeakPlugin` | Configurable | Custom |

### Dynamic ISF Formula

AAPS DynISF uses TDD-based calculation:

```
TDD = (tddWeighted8h * 0.33) + (tdd7D * 0.34) + (tdd1D * 0.33)
variableSens = 1800 / (TDD * ln((glucose / insulinDivisor) + 1))
```

Where `insulinDivisor` depends on insulin type (55-75).

---

## Trio-Specific Concepts

### oref2 Variables

Trio extends oref0 with additional state tracked in CoreData and passed to the algorithm:

| Variable | Purpose | NS Equivalent |
|----------|---------|---------------|
| `average_total_data` | 10-day TDD average | N/A (local only) |
| `weightedAverage` | Weighted 2h/10d TDD for dynamic ISF | N/A |
| `past2hoursAverage` | Recent 2-hour TDD | N/A |
| `overridePercentage` | Active override insulin % | N/A (temp target only syncs) |
| `useOverride` | Override active flag | N/A |
| `smbIsOff` | Override disables SMB | N/A |
| `smbIsScheduledOff` | Time-window SMB disable | N/A |
| `hbt` | Half-basal exercise target | N/A |

### Remote Commands (Announcements)

Trio supports remote commands via Nightscout Announcements:

| Command | Format | Example |
|---------|--------|---------|
| Remote Bolus | `bolus: <units>` | `bolus: 2.5` |
| Pump Suspend | `pump: suspend` | `pump: suspend` |
| Pump Resume | `pump: resume` | `pump: resume` |
| Loop Toggle | `looping: <bool>` | `looping: false` |
| Temp Basal | `tempbasal: <rate>,<duration>` | `tempbasal: 0.5,30` |

**Security**: Only announcements with `enteredBy: "remote"` are processed.

### Override vs Temp Target

| Feature | Override | Temp Target |
|---------|----------|-------------|
| Stored In | CoreData (local) | CoreData + NS |
| Affects ISF/CR | Yes (percentage) | No |
| Affects Target | Yes | Yes |
| Disables SMB | Optional | No |
| NS Sync | No | Yes |
| Priority | Lower | Higher (if both active) |

### Insulin Curves

| Curve | JSON Value | Peak (min) | Default DIA |
|-------|------------|------------|-------------|
| Rapid Acting | `rapid-acting` | 75 | 5 hours |
| Ultra Rapid | `ultra-rapid` | 55 | 4 hours |
| Bilinear | `bilinear` | N/A | Variable |
| Custom Peak | via `insulinPeakTime` | User-set | Variable |

### Dynamic ISF (Trio)

Trio's dynamic ISF uses TDD-based adjustment:

```
weightedTDD = (weight × 2h_TDD) + ((1 - weight) × 10d_TDD)
adjustedISF = baseISF × (referenceWeight / weightedTDD)
```

Where `weight` is configurable via `weightPercentage` (default 0.65).

---

## oref0-Specific Concepts

### Core Algorithm Components

oref0 is the reference algorithm that powers AAPS (via Kotlin port) and Trio (via embedded JS). Understanding oref0 is essential for understanding these systems.

| Component | File | Purpose |
|-----------|------|---------|
| `determine-basal` | `lib/determine-basal/determine-basal.js` | Main algorithm decision engine |
| `autosens` | `lib/determine-basal/autosens.js` | 24h sensitivity detection |
| `cob` | `lib/determine-basal/cob.js` | Carb absorption detection |
| `iob/calculate` | `lib/iob/calculate.js` | IOB calculation with bilinear/exponential curves |
| `iob/total` | `lib/iob/total.js` | IOB aggregation across treatments |

### Prediction Curves (predBGs)

oref0 outputs four separate prediction curves, each representing a different scenario:

| Curve | Field | Description | Loop Equivalent |
|-------|-------|-------------|-----------------|
| IOB | `predBGs.IOB[]` | Insulin-only prediction (baseline) | Combined `predictedGlucose` |
| COB | `predBGs.COB[]` | With carb absorption (linear decay) | Carb effect component |
| UAM | `predBGs.UAM[]` | Unannounced meal (deviation-based) | N/A (no UAM) |
| ZT | `predBGs.ZT[]` | Zero temp "what-if" for safety | N/A |

**Cross-Project Significance**: Loop only uploads combined predictions, not component effects (GAP-SYNC-002). oref0's separate arrays enable algorithm comparison.

### Carb Absorption Model

| Parameter | oref0 | AAPS | Loop | Notes |
|-----------|-------|------|------|-------|
| Model Type | Linear decay | Same | PiecewiseLinear (dynamic) | oref0 is simpler |
| Min Absorption Rate | `min_5m_carbimpact` (8 mg/dL/5m) | Same | `absorptionTimeOverrun` | Prevents stalled COB |
| Max COB | `maxCOB` (120g) | Same | Per-entry limit | Global cap |
| Absorption Duration | Calculated from CI | Same | Observed dynamically | Different approaches |

### SMB (Super Micro Bolus) Parameters

| Parameter | oref0 | AAPS | Trio | Description |
|-----------|-------|------|------|-------------|
| `maxSMBBasalMinutes` | 75 | Same | Same | Max SMB as minutes of basal |
| `maxUAMSMBBasalMinutes` | 30 | Same | Same | Max SMB in UAM mode |
| `SMBInterval` | 3 | Same | Same | Minimum minutes between SMBs |
| `enableSMB_always` | false | Same | Same | SMB at all times |
| `enableSMB_with_COB` | true | Same | Same | SMB when COB > 0 |
| `enableSMB_after_carbs` | true | Same | Same | SMB for 6h after carbs |

### Shared IOB Formula Origin

The exponential insulin activity curve in oref0 was sourced directly from Loop:

```
oref0:lib/iob/calculate.js#L125
// Formula source: https://github.com/LoopKit/Loop/issues/388#issuecomment-317938473
```

This means **oref0, AAPS, Trio, and Loop all use the same exponential insulin model**, enabling direct cross-project IOB comparison for rapid-acting and ultra-rapid insulin types.

### Deviation-Based Algorithm

oref0's core innovation is deviation analysis:

| Term | Calculation | Purpose |
|------|-------------|---------|
| BGI | `-activity × sens × 5` | Expected 5-min BG change from insulin |
| Deviation | `delta - BGI` | Unexplained BG change (carbs, sensitivity) |
| eventualBG | `BG - (IOB × sens) + deviation` | Where BG is heading |

### Safety Parameters

| Parameter | oref0 Default | Description |
|-----------|---------------|-------------|
| `max_iob` | 6 U | Maximum insulin on board |
| `max_basal` | 4 U/hr | Maximum temp basal rate |
| `autosens_min` | 0.5 | Minimum sensitivity ratio |
| `autosens_max` | 2.0 | Maximum sensitivity ratio |
| `max_daily_safety_multiplier` | 4 | Multiplier on max daily basal |
| `current_basal_safety_multiplier` | 5 | Multiplier on current basal |

---

## Remote Command Security Models

> **See Also**: 
> - [Remote Commands Cross-System Comparison](../../docs/10-domain/remote-commands-comparison.md) - Architecture and source analysis
> - [Remote Bolus Comparison](../../docs/10-domain/remote-bolus-comparison.md) - Safety validation deep dive

### Transport and Authentication

| Aspect | Trio | Loop | AAPS |
|--------|------|------|------|
| Transport | APNS Push | APNS Push | SMS |
| Payload Encryption | AES-256-GCM | None | None |
| Authentication | Shared secret | TOTP OTP | Phone whitelist + TOTP + PIN |
| Key Derivation | SHA256 | Base32 secret | HMAC key |

### Security Parameters

| Parameter | Trio | Loop | AAPS |
|-----------|------|------|------|
| Encryption Algorithm | AES-256-GCM | N/A | N/A |
| Key Size | 256 bits | 160+ bits (SHA1) | 160 bits |
| OTP Algorithm | N/A | HMAC-SHA1 | HMAC |
| OTP Digits | N/A | 6 | 6 + PIN (3+) |
| OTP Period | N/A | 30 sec | 30 sec |
| Nonce Size | 12 bytes | N/A | N/A |

### Replay Protection

| Mechanism | Trio | Loop | AAPS |
|-----------|------|------|------|
| Timestamp Window | ±10 minutes | Expiration date | Command timeout |
| Duplicate Detection | Implicit (timestamp) | In-memory tracking | `processed` flag |
| OTP Reuse Prevention | N/A | Track recent OTPs | Timeout-based |
| Bolus Distance | Recent bolus check (20%) | N/A | Configurable minimum |

### Command Type Support

| Command | Trio | Loop | AAPS |
|---------|------|------|------|
| Remote Bolus | `bolus` | `bolusEntry` | `BOLUS` SMS |
| Remote Carbs | `meal` | `carbsEntry` | `CARBS` SMS |
| Override Start | `startOverride` | `temporaryScheduleOverride` | N/A |
| Override Cancel | `cancelOverride` | `cancelTemporaryOverride` | N/A |
| Temp Target | `tempTarget` | N/A (via override) | `TARGET` SMS |
| Cancel TT | `cancelTempTarget` | N/A | `TARGET STOP` SMS |
| Basal Change | N/A | N/A | `BASAL` SMS |
| Loop Control | N/A | N/A | `LOOP` SMS |
| Pump Control | N/A | N/A | `PUMP` SMS |
| Profile Switch | N/A | N/A | `PROFILE` SMS |

### OTP Requirement per Command

| Command Type | Trio | Loop | AAPS |
|--------------|------|------|------|
| Bolus | N/A (encrypted) | **Required** | Required |
| Carbs | N/A (encrypted) | **Required** | Required |
| Override | N/A (encrypted) | **Not Required** ⚠️ | N/A |
| Cancel Override | N/A (encrypted) | **Not Required** ⚠️ | N/A |

**Security Gap**: Loop does not require OTP for override commands. See [GAP-REMOTE-001](../../traceability/gaps.md#gap-remote-001-remote-command-authorization-unverified).

### Safety Enforcement

| Check | Trio | Loop | AAPS |
|-------|------|------|------|
| Max Bolus | Remote handler | Downstream | ConstraintChecker |
| Max IOB | Remote handler | Downstream | ConstraintChecker |
| Recent Bolus | 20% rule | N/A | Min distance |
| Queue Empty | N/A | N/A | 3-min wait |
| Pump Suspended | N/A | N/A | Checked |

### Source File References

| System | Primary Source |
|--------|---------------|
| Trio | `trio:Trio/Sources/Services/RemoteControl/` |
| Loop | `loop:NightscoutService/NightscoutServiceKit/RemoteCommands/` |
| AAPS | `aaps:plugins/main/src/main/kotlin/app/aaps/plugins/main/general/smsCommunicator/` |

---

## API Version Models

> **See Also**: [Nightscout API v1 vs v3 Comparison](../../docs/10-domain/nightscout-api-comparison.md)

### API Version by Client

| Client | API Version | Authentication | Sync Method |
|--------|-------------|----------------|-------------|
| **AAPS** | v3 | Bearer token (opaque) | History endpoint |
| **Loop** | v1 | SHA1 secret | Polling with date filter |
| **Trio** | v1 | SHA1 secret | Polling with date filter |
| **xDrip+** | v1 | SHA1 secret | Polling with date filter |
| **OpenAPS** | v1 | SHA1 secret | Polling with date filter |
| **Nightguard** | v1 | SHA1 secret (read-only) | Polling |
| **xDrip4iOS** | v1 | SHA1 secret | Polling with date filter |

### Document Identity Fields

| System | API Version | Primary ID | Secondary ID | Update Method |
|--------|-------------|-----------|--------------|---------------|
| **Nightscout v1** | v1 | `_id` (MongoDB ObjectId) | N/A | PUT to `/{collection}/{_id}` |
| **Nightscout v3** | v3 | `identifier` (server-assigned) | `_id` (internal) | PUT/PATCH to `/{collection}/{identifier}` |
| **AAPS** | v3 | `identifier` | `interfaceIDs.nightscoutId` | PATCH via SDK |
| **Loop** | v1 | `_id` | `syncIdentifier` | POST (no upsert) |
| **Trio** | v1 | `_id` | `syncIdentifier` | POST (no upsert) |
| **xDrip+** | v1 | `_id` | `uuid` | PUT upsert |

### API v3 Exclusive Features

| Feature | Description | Used By |
|---------|-------------|---------|
| `identifier` | Server-assigned immutable document ID | AAPS |
| `history/{timestamp}` | Incremental sync since timestamp | AAPS |
| `isValid` | Soft-delete flag (false = deleted) | AAPS |
| `isDeduplication` | Response flag indicating duplicate | AAPS |
| `srvModified` | Server modification timestamp | AAPS |
| Bearer Access Tokens | Opaque tokens with Shiro permissions | AAPS |
| Shiro Permissions | Granular `api:collection:operation` | AAPS |

### Sync Pattern Comparison

| Aspect | v1 Polling | v3 History |
|--------|------------|------------|
| Detects Insertions | Yes | Yes |
| Detects Updates | Partial | Yes |
| Detects Deletions | No | Yes (`isValid: false`) |
| Bandwidth Efficiency | Lower | Higher |
| Time Precision | Seconds | Milliseconds |

### API v3 Deduplication Keys

> **See Also**: [API Deep Dive](../../docs/10-domain/cgm-remote-monitor-api-deep-dive.md)

| Collection | Primary Key | Fallback Keys | Source |
|------------|-------------|---------------|--------|
| entries | `identifier` | `date`, `type` | `lib/api3/generic/setup.js` |
| treatments | `identifier` | `created_at`, `eventType` | `lib/api3/generic/setup.js` |
| devicestatus | `identifier` | `created_at`, `device` | `lib/api3/generic/setup.js` |
| profile | `identifier` | `created_at` | `lib/api3/generic/setup.js` |
| food | `identifier` | `created_at` | `lib/api3/generic/setup.js` |
| settings | `identifier` | (none) | `lib/api3/generic/setup.js` |

**Behavior**: When duplicate found → UPSERT (update, not reject)  
**Control**: `API3_DEDUP_FALLBACK_ENABLED` environment variable  
**Gap Reference**: GAP-API-005, GAP-API-006

### Timestamp Fields by Collection

| Collection | Primary Timestamp | Format | Usage |
|------------|------------------|--------|-------|
| entries | `date` | Epoch milliseconds | CGM reading time |
| treatments | `created_at` | ISO-8601 string | Treatment creation time |
| devicestatus | `created_at` | ISO-8601 string | Status report time |
| profile | `created_at` | ISO-8601 string | Profile creation time |

**Gap Reference**: GAP-API-008

### Nocturne Timestamp Pattern

Nocturne uses a "Mills-first" pattern where `Mills` (Unix epoch milliseconds) is the canonical timestamp:

| Field | Type | Purpose |
|-------|------|---------|
| `Mills` | long | **Source of truth** (Unix ms) |
| `Date` | DateTime? | Computed from Mills |
| `DateString` | string? | ISO-8601, computed |

This differs from cgm-remote-monitor where `date` (epoch ms) and `dateString` (ISO-8601) may be set independently.

**Source**: `mapping/nocturne/models.md`

### Dexcom Share Timestamp Pattern

Dexcom Share API uses a .NET-style serialized DateTime format:

```
/Date(1234567890123-0500)/
```

| Component | Description |
|-----------|-------------|
| `1234567890123` | Unix epoch milliseconds |
| `-0500` | Timezone offset (optional) |

Parsing requires regex: `/Date\((\d+)([+-]\d{4})?\)/`

share2nightscout-bridge converts to Nightscout format:
- `date` ← extracted epoch ms
- `dateString` ← `new Date(epoch).toISOString()`

**Source**: `mapping/share2nightscout-bridge/entries.md`

### Query Syntax Comparison

| Operation | v1 Syntax | v3 Syntax |
|-----------|-----------|-----------|
| Equality | `find[type]=sgv` | `type$eq=sgv` |
| Greater Than | `find[date][$gte]=1705000000000` | `date$gte=1705000000000` |
| Less Than | `find[date][$lte]=1705000000000` | `date$lte=1705000000000` |
| Count/Limit | `count=100` | `limit=100` |
| Sorting | N/A (server default) | `sort=field` or `sort$desc=field` |

**Gap Reference**: GAP-API-001 (v1 cannot detect deletions), GAP-API-003 (no v3 adoption path for iOS)

---

## Pump Communication Models

> **See Also**: [Pump Communication Deep Dive](../../docs/10-domain/pump-communication-deep-dive.md) for comprehensive protocol analysis.

### Pump Interface Abstraction

| Concept | Loop/Trio | AAPS |
|---------|-----------|------|
| **Pump Interface** | `PumpManager` protocol | `Pump` interface |
| **Status Object** | `PumpManagerStatus` | `PumpDescription` + state getters |
| **Command Result** | `PumpManagerResult<T>` | `PumpEnactResult` |
| **History Sync** | `PumpManagerDelegate.hasNewPumpEvents()` | `PumpSync` interface |
| **Connection State** | Implicit (delegate callbacks) | `isConnected()`, `isConnecting()`, `isHandshakeInProgress()` |

### Core Pump Commands

| Command | Loop PumpManager | AAPS Pump |
|---------|------------------|-----------|
| **Bolus** | `enactBolus(units:activationType:completion:)` | `deliverTreatment(DetailedBolusInfo)` |
| **Cancel Bolus** | `cancelBolus(completion:)` | `stopBolusDelivering()` |
| **Temp Basal** | `enactTempBasal(unitsPerHour:for:completion:)` | `setTempBasalAbsolute(rate, minutes, profile, enforceNew, tbrType)` |
| **Cancel TBR** | `enactTempBasal(0, 0, completion:)` | `cancelTempBasal(enforceNew)` |
| **Suspend** | `suspendDelivery(completion:)` | `suspendDelivery()`* or `setTempBasalPercent(0, ...)` |
| **Resume** | `resumeDelivery(completion:)` | `resumeDelivery()`* or `cancelTempBasal()` |
| **Set Profile** | `syncBasalRateSchedule(items:completion:)` | `setNewBasalProfile(Profile)` |

*Note: AAPS supports native suspend/resume on some pumps; others emulate via 0% temp basal (`PUMP_SUSPEND` or `EMULATED_PUMP_SUSPEND` types).

### Pump Transport Protocols

| Pump Type | Loop/Trio | AAPS | Protocol |
|-----------|-----------|------|----------|
| **Omnipod DASH** | OmniBLE | omnipod-dash | BLE + AES-CCM |
| **Omnipod Eros** | OmniKit | omnipod-eros | RF 433MHz + RileyLink |
| **Medtronic** | MinimedKit | medtronic | RF 916MHz + RileyLink |
| **Dana RS** | N/A | danars | BLE + Custom encryption |
| **Dana i** | N/A | danars | BLE + Custom encryption |
| **Accu-Chek Insight** | N/A | insight | BLE + SightParser |
| **Accu-Chek Combo** | N/A | combov2 | RF + ruffy |
| **Diaconn G8** | N/A | diaconn | BLE |
| **Medtrum** | N/A | medtrum | BLE |

### Precision Constraints Comparison

| Pump | Bolus Step | Basal Step | TBR Duration Step |
|------|------------|------------|-------------------|
| **Omnipod DASH/Eros** | 0.05 U | 0.05 U/hr | 30 min |
| **Dana RS** | 0.05 U | 0.01 U/hr | 15/30/60 min |
| **Medtronic 523/723** | 0.05 U | 0.025 U/hr | 30 min |
| **Accu-Chek Insight** | 0.01-0.05 U | 0.01 U/hr | 15 min |
| **Diaconn G8** | 0.01 U | 0.01 U/hr | 30 min |

### Bolus State Machine

| State | Loop `BolusState` | AAPS |
|-------|-------------------|------|
| **No Bolus** | `.noBolus` | N/A (no explicit state) |
| **Initiating** | `.initiating` | Pre-`deliverTreatment()` |
| **In Progress** | `.inProgress(dose)` | `BolusProgressData.delivering` |
| **Canceling** | `.canceling` | `stopBolusDelivering()` called |
| **Uncertain** | `deliveryIsUncertain: true` | `PumpEnactResult.success == false` |

### Basal Delivery State Machine

| State | Loop `BasalDeliveryState` | AAPS |
|-------|---------------------------|------|
| **Active (scheduled)** | `.active(at)` | `isSuspended() == false` |
| **Temp Basal** | `.tempBasal(dose)` | `PumpSync.expectedPumpState().temporaryBasal != null` |
| **Suspended** | `.suspended(at)` | `isSuspended() == true` |
| **Initiating TBR** | `.initiatingTempBasal` | N/A |
| **Canceling TBR** | `.cancelingTempBasal` | N/A |

### Temp Basal Type Enums

| AAPS TBR Type | Description | Nightscout |
|---------------|-------------|------------|
| `NORMAL` | Standard temp basal | `Temp Basal` |
| `EMULATED_PUMP_SUSPEND` | Suspend via 0% basal | `Temp Basal` |
| `PUMP_SUSPEND` | Actual pump suspend | `Temp Basal` |
| `SUPERBOLUS` | Superbolus temp basal | `Temp Basal` |
| `FAKE_EXTENDED` | Extended bolus emulation | `Temp Basal` |

**Gap Reference**: GAP-PUMP-002 (extended bolus not in Loop), GAP-PUMP-003 (TBR duration units)

---

## Dexcom BLE Protocol Models

> **See Also**: [Dexcom BLE Protocol Deep Dive](../../docs/10-domain/dexcom-ble-protocol-deep-dive.md) for comprehensive protocol specification.

### BLE Service and Characteristic UUIDs

| Purpose | UUID | Description |
|---------|------|-------------|
| **Advertisement** | `FEBC` | Dexcom advertisement service |
| **CGM Data Service** | `F8083532-849E-531C-C594-30F1F86A4EA5` | Main data service |
| **Communication** | `F8083533-849E-531C-C594-30F1F86A4EA5` | Status updates (Read/Notify) |
| **Control** | `F8083534-849E-531C-C594-30F1F86A4EA5` | Command exchange (Write/Indicate) |
| **Authentication** | `F8083535-849E-531C-C594-30F1F86A4EA5` | Auth handshake (Write/Indicate) |
| **Backfill** | `F8083536-849E-531C-C594-30F1F86A4EA5` | Historical data (Read/Write/Notify) |
| **J-PAKE (G7)** | `F8083538-849E-531C-C594-30F1F86A4EA5` | G7 J-PAKE exchange |

### G6 vs G7 Protocol Differences

| Aspect | G6 | G7 |
|--------|----|----|
| **Authentication** | AES-128-ECB challenge-response | J-PAKE (Password Authenticated Key Exchange) |
| **Connection Slots** | 2 (xDrip + Dexcom app) | 1 (exclusive) |
| **Glucose Opcode** | 0x30/0x31 or 0x4E/0x4F | 0x4E/0x4F only |
| **Calibration** | Factory + user calibration | Factory only |
| **Warmup** | 2 hours | 27 minutes |
| **Backfill Opcode** | 0x50/0x51 | 0x59 |

### Core Message Opcodes

| Category | Opcode (Tx/Rx) | Purpose |
|----------|----------------|---------|
| **Auth Request** | 0x01/0x03 | Initiate authentication |
| **Auth Challenge** | 0x04/0x05 | Complete authentication |
| **Keep Alive** | 0x06 | Maintain connection |
| **Bond Request** | 0x07/0x08 | Request Bluetooth bonding |
| **Disconnect** | 0x09 | Graceful disconnect |
| **Battery Status** | 0x22/0x23 | Battery voltage and runtime |
| **Transmitter Time** | 0x24/0x25 | Current time and session start |
| **Session Start** | 0x26/0x27 | Start sensor session |
| **Session Stop** | 0x28/0x29 | Stop sensor session |
| **Glucose (G5)** | 0x30/0x31 | Request glucose reading |
| **Calibration Data** | 0x32/0x33 | Get/set calibration |
| **Calibrate Glucose** | 0x34/0x35 | Submit calibration value |
| **Reset** | 0x42/0x43 | Reset transmitter |
| **Version (extended)** | 0x4A/0x4B | Get transmitter version |
| **Glucose (G6/G7)** | 0x4E/0x4F | Request glucose reading |
| **Backfill (G6)** | 0x50/0x51 | Request historical data |
| **Version Extended (G7)** | 0x52/0x53 | Get extended version |
| **Backfill Finished (G7)** | 0x59 | Backfill complete |

### Glucose Message Structure Comparison

| Field | G6 (0x31/0x4F) | G7 (0x4E) |
|-------|----------------|-----------|
| **Opcode** | Byte 0 | Byte 0 |
| **Status** | Byte 1 | Byte 1 |
| **Timestamp** | Bytes 6-9 (submessage) | Bytes 2-5 |
| **Sequence** | Bytes 2-5 | Bytes 6-7 |
| **Age** | N/A | Bytes 10-11 |
| **Glucose** | Bytes 10-11 (12-bit) | Bytes 12-13 (12-bit) |
| **Algorithm State** | Byte 12 | Byte 14 |
| **Trend** | Byte 13 (signed) | Byte 15 (signed, /10) |
| **Predicted** | N/A | Bytes 16-17 |

### Authentication Hash Function

| System | Implementation | Key Derivation |
|--------|----------------|----------------|
| **CGMBLEKit** | `aes128ecb_encrypt(challenge+challenge, key)` | `key = "00" + transmitterID + "00" + transmitterID` |
| **xdrip-js** | `crypto.createCipheriv('aes-128-ecb', key, '')` | Same as above |
| **DiaBLE** | `doubleChallenge.aes128Encrypt(keyData: cryptKey)` | Same as above |

### CRC-16 Implementation

All systems use **CRC-16 CCITT (XModem)**:
- Polynomial: `0x1021`
- Initial value: `0x0000`
- Position: Last 2 bytes of message (little-endian)

### Transmitter ID Formats

| Transmitter | ID Format | Example | Detection |
|-------------|-----------|---------|-----------|
| **G5** | 5 alphanumeric | `40XXX` | Length == 5 |
| **G6** | 6 alphanumeric, starts with 8 | `80XXXX` | `id[0] == '8'` |
| **G6+** | 6 alphanumeric, 8G/8H/8J/8L/8R | `8GXXXX` | Prefix check |
| **G7** | DXCM + suffix | `DXCMXX` | Advertisement name |

### Calibration/Algorithm State Mapping

| State Value | G6 Name | G7 Name | Reliable Glucose |
|-------------|---------|---------|------------------|
| 0x01 | Stopped | Stopped | No |
| 0x02 | Warmup | Warmup | No |
| 0x06 | OK | OK | Yes |
| 0x07 | NeedCalibration7 | NeedsCalibration | G6: Yes, G7: No |
| 0x0F | SessionFailure15 | SessionExpired | No |
| 0x12 | QuestionMarks | TemporarySensorIssue | No |

**Gap Reference**: GAP-BLE-001 (J-PAKE spec), GAP-BLE-002 (certificate chain)

---

## Carb Absorption Models

> **See Also**: [Carb Absorption Deep Dive](../../docs/10-domain/carb-absorption-deep-dive.md) for comprehensive mathematical formulas and source code citations.

### Absorption Curve Types

| Model Type | Loop | oref0 | AAPS | Trio |
|------------|------|-------|------|------|
| **Parabolic (Scheiner)** | `ParabolicAbsorption` | N/A | N/A | `ParabolicAbsorption` |
| **Linear** | `LinearAbsorption` | Default (implicit) | Default (implicit) | `LinearAbsorption` |
| **PiecewiseLinear (Trapezoid)** | `PiecewiseLinearAbsorption` (default) | N/A | N/A | `PiecewiseLinearAbsorption` (default) |
| **Extended Carbs (eCarbs)** | N/A | N/A | `duration` field on `Carbs` entity | N/A |

### COB Calculation Approach

| Aspect | Loop/Trio | oref0/AAPS |
|--------|-----------|------------|
| **Philosophy** | Model-first with dynamic adaptation | Observation-first with min floor |
| **Absorption Tracking** | Per-entry with `AbsorbedCarbValue` | Global deviation-based inference |
| **Dynamic Adaptation** | Yes (`observedTimeline`) | No (linear decay) |
| **Minimum Rate** | Clamping logic | `min_5m_carbimpact` (3 mg/dL/5m) |

### Key Parameters

| Parameter | Loop | oref0 | AAPS | Source (Line) |
|-----------|------|-------|------|---------------|
| **Default Absorption Time** | 3 hours | Profile-based | Profile-based | `CarbMath.swift#L14` |
| **Max Absorption Time** | 10 hours | 6 hours (carb window) | 6 hours | `CarbMath.swift#L13`, `total.js#L49` |
| **Effect Delay** | 10 minutes | None | None | `CarbMath.swift#L16` |
| **Initial Overrun Factor** | 1.5x | N/A | N/A | `CarbMath.swift#L15` |
| **Max COB Cap** | None | 120g (configurable) | 120g | `total.js#L108` |
| **Min Carb Impact** | N/A | 3 mg/dL/5m (8 for low-carb) | 3 mg/dL/5m | `cob.js#L190` |
| **Max Absorption Rate** | N/A | 30 g/h | 30 g/h | `determine-basal.js#L480` |

**Source Files**:
- Loop: `externals/LoopWorkspace/LoopKit/LoopKit/CarbKit/CarbMath.swift`
- oref0: `externals/oref0/lib/meal/total.js`, `externals/oref0/lib/determine-basal/cob.js`, `externals/oref0/lib/determine-basal/determine-basal.js`

### Carb Entry Field Comparison

| Field | Loop | oref0 | AAPS | Nightscout |
|-------|------|-------|------|------------|
| **Amount** | `quantity` (HKQuantity) | `carbs` | `amount` | `carbs` |
| **Absorption Time** | `absorptionTime` (seconds) | N/A | N/A | `absorptionTime` (minutes) |
| **Duration (eCarbs)** | N/A | N/A | `duration` (milliseconds) | `duration` (minutes) |
| **Start Date** | `startDate` | `timestamp` | `timestamp` | `created_at` |

**Unit Conversion Notes**:
- Loop/Trio absorption time: **seconds**
- Nightscout absorption time: **minutes** (GAP-CARB-001)
- AAPS duration: **milliseconds**
- Nightscout duration: **minutes** (GAP-CARB-002)

### UAM (Unannounced Meals) Handling

| Mechanism | Loop | oref0 | AAPS | Trio |
|-----------|------|-------|------|------|
| **Detection** | Retrospective Correction (implicit) | Explicit UAM curve | Explicit UAM | Both (RC + UAM) |
| **Prediction Curve** | Single combined | Separate `UAMpredBGs` | Separate | Separate |
| **Decay Model** | Via RC adjustment | Linear decay (3h max) | Linear decay | Linear decay |
| **Enable Setting** | Always via RC | `enableUAM` profile flag | `enableUAM` | `enableUAM` |

### Glucose Effect Calculation

| System | Formula | Source |
|--------|---------|--------|
| **Loop** | `glucoseEffect = ISF / CR * absorbedCarbs` | `CarbMath.swift#L279-L288` |
| **oref0** | `csf = sens / carb_ratio; effect = csf * carbs` | `determine-basal.js#L477` |
| **AAPS** | Same as oref0 (JS port) | oref0 JS execution |

### Source Files Reference

| System | Key Carb Absorption Files |
|--------|---------------------------|
| **Loop** | `LoopKit/CarbKit/CarbMath.swift`, `CarbStatus.swift`, `AbsorbedCarbValue.swift` |
| **oref0** | `lib/determine-basal/cob.js`, `lib/meal/total.js`, `lib/determine-basal/determine-basal.js` |
| **AAPS** | `database/entities/Carbs.kt`, `core/data/iob/CobInfo.kt` |
| **Trio** | Same as Loop (`LoopKit/CarbKit/*`) + oref0 JS |

**Gap Reference**: GAP-CARB-001 through GAP-CARB-005

---

## Libre CGM Protocol Models

> **See Also**: [Libre Protocol Deep Dive](../../docs/10-domain/libre-protocol-deep-dive.md) for comprehensive protocol specification.

### Sensor Type Detection (from PatchInfo)

| PatchInfo[0] | Sensor Type | Family | Security Generation |
|--------------|-------------|--------|---------------------|
| 0xDF, 0xA2 | Libre 1 | 0 | 0 |
| 0xE5, 0xE6 | Libre US 14-day | 0 | 1 |
| 0x70 | Libre Pro/H | 1 | 0 |
| 0x9D, 0xC5 | Libre 2 EU | 3 | 1 |
| 0xC6, 0x7F | Libre 2+ EU | 3 | 1 |
| 0x76, 0x2B, 0x2C | Libre 2 Gen2 (US) | 3 | 2 |
| 24-byte patchInfo | Libre 3 | 4 | 3 |

### Sensor Families

| Family | Raw Value | Sensors | IC Manufacturer |
|--------|-----------|---------|-----------------|
| libre1 | 0 | Libre 1 | TI (0x07) |
| librePro | 1 | Libre Pro/H | TI (0x07) |
| libre2 | 3 | Libre 2, 2+, Gen2 | TI (0x07) |
| libre3 | 4 | Libre 3, 3+ | Abbott (0x7a) |
| libreSense | 7 | Libre Sense (wellness) | TI (0x07) |
| lingo | 9 | Lingo (wellness) | Abbott (0x7a) |

### FRAM Memory Layout (344 bytes) - Libre 1/2/2+/Gen2 Only

> **Note**: FRAM applies only to NFC-based sensors. Libre 3 is BLE-only and does not use FRAM.

| Region | Offset | Size | Key Fields |
|--------|--------|------|------------|
| Header | 0-23 | 24 bytes | CRC (0-1), State (4), Error Code (6), Failure Age (7-8) |
| Body | 24-319 | 296 bytes | CRC (24-25), Trend Index (26), History Index (27), Trend (28-123), History (124-315), Age (316-317) |
| Footer | 320-343 | 24 bytes | CRC (320-321), Region (323), Max Life (326-327), Calibration (328+) |

### Glucose Reading Structure (6 bytes)

| Bit Offset | Bit Count | Field | Notes |
|------------|-----------|-------|-------|
| 0 | 14 | rawValue | Raw glucose value |
| 14 | 9 | quality | Data quality (error bits) |
| 23 | 2 | qualityFlags | Additional flags |
| 25 | 1 | hasError | Error indicator |
| 26 | 12 | rawTemperature | Temperature reading (<<2) |
| 38 | 9 | tempAdjustment | Temperature adjustment (<<2) |
| 47 | 1 | negativeAdj | Sign bit for adjustment |

### NFC Commands

| Code | Name | Description |
|------|------|-------------|
| 0xA1 | Universal Prefix | Execute subcommand |
| 0xB0 | Read Block | Read single memory block |
| 0xB3 | Read Blocks | Read multiple blocks |

### NFC Subcommands (via 0xA1)

| Subcode | Name | Description |
|---------|------|-------------|
| 0x1A | Unlock | Read FRAM in clear |
| 0x1B | Activate | Activate sensor |
| 0x1E | Enable Streaming | Enable BLE (Libre 2) |
| 0x1F | Get Session Info | Gen2 session info |
| 0x20 | Read Challenge | Gen2 challenge |
| 0x21 | Read Blocks | Gen2 FRAM read |
| 0x22 | Read Attribute | Gen2 sensor state |

### Libre 2 Key Derivation Constants

> **Note**: These are derivation constants, NOT direct encryption keys. Actual keys are derived per-sensor using the 8-byte sensor UID and 6-byte patchInfo as inputs. See [Libre Protocol Deep Dive](../../docs/10-domain/libre-protocol-deep-dive.md#libre-2-encryption) for full algorithm.

| Constant | Value | Purpose |
|----------|-------|---------|
| key[0] | 0xA0C5 | XOR derivation constant |
| key[1] | 0x6860 | XOR derivation constant |
| key[3] | 0x14C6 | Initial XOR derivation |
| secret | 0x1b6a | Default secret for key derivation |

### BLE UUIDs

| System | Service UUID | Key Characteristic UUIDs |
|--------|--------------|--------------------------|
| Libre 2 | FDE3 | F001 (login), F002 (data) |
| Libre 3 | Base: 0898xxxx-EF89-11E9-81B4-2A2AE2DBCCE4 | 10CC (data), 1338 (control), 1482 (status), 177A (glucose), 2198 (security), 22CE (challenge), 23FA (cert) |

> **Note**: Libre 3 uses 13+ characteristics. See [Libre Protocol Deep Dive - BLE Service and Characteristic UUIDs](../../docs/10-domain/libre-protocol-deep-dive.md#ble-service-and-characteristic-uuids) for complete list with full UUIDs.

### Libre 3 BLE Characteristics

| UUID Suffix | Name | Purpose |
|-------------|------|---------|
| 10CC | data | Data service |
| 1338 | patchControl | Send commands |
| 1482 | patchStatus | Sensor status |
| 177A | oneMinuteReading | Current glucose |
| 195A | historicalData | Backfill history |
| 1AB8 | clinicalData | Clinical backfill |
| 1BEE | eventLog | Event logging |
| 1D24 | factoryData | Factory data |
| 2198 | securityCommands | Security protocol |
| 22CE | challengeData | Auth challenge |
| 23FA | certificateData | Certificates |

### Transmitter Bridge Protocols

| Device | Service UUID | Start Command | Data Format |
|--------|--------------|---------------|-------------|
| MiaoMiao | 6E400001-... (Nordic UART) | 0xF0 | 363+ bytes (18 header + 344 FRAM + patchInfo) |
| Bubble | 6E400001-... (Nordic UART) | [0x00, 0xA0, interval] | 8 header + 344 FRAM |
| Blucon | Proprietary | Device-specific | Wrapped FRAM |
| Atom | 6E400001-... (Nordic UART) | Similar to Bubble | Wrapped FRAM |

### Cross-Implementation Comparison

| Feature | DiaBLE | LibreTransmitter | xDrip4iOS | xDrip+ Android |
|---------|--------|------------------|-----------|----------------|
| Libre 1 NFC | ✅ | ✅ | ✅ | ✅ |
| Libre 2 NFC | ✅ | ✅ | ✅ | ✅ |
| Libre 2 BLE | ✅ | ✅ | ✅ | ✅ |
| Libre 2 Gen2 | ⚠️ | ❌ | ⚠️ | ✅ |
| Libre 3 | ⚠️ | ❌ | ❌ | ⚠️ |
| Bridge Transmitters | Limited | MiaoMiao, Bubble | MiaoMiao, Bubble, etc. | All |

**Source Files**:
- DiaBLE: `externals/DiaBLE/DiaBLE/Libre.swift`, `Libre2.swift`, `Libre3.swift`
- LibreTransmitter: `externals/LoopWorkspace/LibreTransmitter/LibreSensor/`
- xDrip4iOS: `externals/xdripswift/xdrip/BluetoothTransmitter/CGM/Libre/`

**Gap Reference**: GAP-LIBRE-001 through GAP-LIBRE-006

### DiaBLE Nightscout Device Identifier Pattern

DiaBLE uses the **sensor type name** as the Nightscout `device` field:

| Sensor | DiaBLE `device` Value | Example |
|--------|----------------------|---------|
| Libre 1 | `"Libre 1"` | `{"device": "Libre 1", "sgv": 120}` |
| Libre 2 | `"Libre 2"` | `{"device": "Libre 2", "sgv": 115}` |
| Libre 3 | `"Libre 3"` | `{"device": "Libre 3", "sgv": 108}` |
| Dexcom G6 | `"Dexcom G6"` | `{"device": "Dexcom G6", "sgv": 122}` |
| Dexcom G7 | `"Dexcom G7"` | `{"device": "Dexcom G7", "sgv": 118}` |

**Source**: `externals/DiaBLE/DiaBLE/Nightscout.swift:162` - uses `$0.source` which is sensor type name.

**Note**: DiaBLE does NOT include app name in device field (unlike xDrip+ which uses `"xDrip-LibreOOP"`).

### xDrip+ Nightscout Device Identifier Pattern

xDrip+ uses `"xDrip-{collection_method}"` with optional source info appended:

| Collection Method | xDrip+ `device` Value | Description |
|-------------------|----------------------|-------------|
| BluetoothWixel | `"xDrip-BluetoothWixel"` | Classic Dexcom with Wixel bridge |
| DexcomG5 | `"xDrip-DexcomG5"` | Dexcom G5/G6/G7 direct |
| LibreOOP | `"xDrip-LibreOOP"` | Libre with out-of-process algorithm |
| Libre2 | `"xDrip-Libre2"` | Libre 2 direct BLE |
| Medtronic640g | `"xDrip-Medtronic640g"` | Medtronic pump CGM |
| Follower | `"xDrip-Follower"` | Following another xDrip+ |
| NSClient | `"xDrip-NSClient"` | Following Nightscout |

**Source**: `externals/xDrip/app/src/main/java/com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java:649-657`

**Note**: If `source_info` preference enabled, device string becomes `"xDrip-{method} {source_info}"`.

**Gap**: GAP-XDRIP-003 - Device string format not machine-parseable.

### DiaBLE Data Quality Flags

DiaBLE tracks sensor data quality with detailed error flags not exposed to Nightscout:

| Flag | Hex | Description |
|------|-----|-------------|
| `SD14_FIFO_OVERFLOW` | 0x0001 | FIFO buffer overflow |
| `FILTER_DELTA` | 0x0002 | Excessive jitter between measurements |
| `WORK_VOLTAGE` | 0x0004 | Voltage anomaly |
| `PEAK_DELTA_EXCEEDED` | 0x0008 | Peak measurement delta exceeded |
| `AVG_DELTA_EXCEEDED` | 0x0010 | Average delta exceeded |
| `RF` | 0x0020 | NFC interference during measurement |
| `REF_R` | 0x0040 | Reference resistance issue |
| `SIGNAL_SATURATED` | 0x0080 | Reading exceeds 14-bit max (0x3FFF) |
| `SENSOR_SIGNAL_LOW` | 0x0100 | Raw reading below threshold (150) |
| `THERMISTOR_OUT_OF_RANGE` | 0x0800 | Temperature sensor error |
| `TEMP_HIGH` | 0x2000 | Temperature too high |
| `TEMP_LOW` | 0x4000 | Temperature too low |
| `INVALID_DATA` | 0x8000 | General invalid data flag |

**Source**: `externals/DiaBLE/DiaBLE/Glucose.swift:63-91`

**Gap**: These quality flags are not uploaded to Nightscout, limiting remote diagnostic capability.

---

## CGM Sensor Session Terminology

> **See Also**: [CGM Session Handling Deep Dive](../../docs/10-domain/cgm-session-handling-deep-dive.md)

### Sensor Session States

| Alignment Term | xDrip+ | DiaBLE | Loop | AAPS |
|----------------|--------|--------|------|------|
| Not Started | `CalibrationState.Unknown` | `.notActivated` | `notYetStarted` | Missing `SENSOR_CHANGE` |
| Warming Up | `CalibrationState.WarmingUp (0x02)` | `.warmingUp` | `warmup` | Calculated from start |
| Active | Implied | `.active` | `ready` | Implied |
| Expired | ✅ | `.expired` | `sessionExpired` | Via age trigger |
| Failed | ✅ | `.failure` | `sessionFailedDuetoUnrecoverableError` | Via missing data |
| Stopped | `Sensor.stopped_at` | `.shutdown` | `stopped`, `sessionEnded` | `SENSOR_STOPPED` |

### Calibration State Terminology

| Alignment Term | xDrip+ Hex | DiaBLE | Loop |
|----------------|------------|--------|------|
| Needs First Cal | `0x04` | `calibrationsPermitted` | `needFirstInitialCalibration` |
| Needs Second Cal | `0x05` | N/A | `needSecondInitialCalibration` |
| Calibration OK | `0x06` | N/A | `ok` |
| Calibration Error | `0x08-0x0e` | N/A | `calibrationError*` |
| Cal Sent | `0xC3` | N/A | N/A |

### Warm-up Duration Constants

| Sensor | Duration | xDrip+ Source | DiaBLE Source |
|--------|----------|---------------|---------------|
| Dexcom G6 | 2 hours | `SensorDays.warmupMs` | From transmitter |
| Dexcom G7 | Variable | `VersionRequest2RxMessage.warmupSeconds` | `warmupLength` field |
| Libre 1/2 | 1 hour | `SensorDays.java` | Frame `[316-317]` |
| Libre 3 | 1 hour | N/A | `warmupTime × 5 min` |
| Medtrum | 30 min | `SensorDays.java` | N/A |

### Session Identity Fields

| System | Session Tracking | Calibration Tracking |
|--------|------------------|----------------------|
| xDrip+ | `sensor.uuid` | `calibration.uuid` |
| DiaBLE | `activationTime` | N/A (no upload) |
| Loop | `syncIdentifier` | `syncIdentifier` |
| AAPS | `SENSOR_CHANGE` event + `nightscoutId` | `FINGER_STICK_BG_VALUE` event |

### Nightscout Treatment Event Types

| Event | eventType | Purpose |
|-------|-----------|---------|
| Sensor Start | `Sensor Start` | New sensor insertion |
| Sensor Change | `Sensor Start` (implicit) | Session start/restart |
| Sensor Stop | N/A (no standard) | Session end |
| Calibration | `BG Check` | Finger-stick BG value |

**Deep Dive**: [`docs/10-domain/cgm-session-handling-deep-dive.md`](../../docs/10-domain/cgm-session-handling-deep-dive.md)

**Gap Reference**: GAP-SESSION-001 (no standard schema), GAP-SESSION-002 (no warm-up upload), GAP-SESSION-003 (DiaBLE no session upload), GAP-SESSION-004 (calibration state not synced)

---

## LoopCaregiver Remote 2.0 Models

> **See Also**: [LoopCaregiver Remote Commands](../loopcaregiver/remote-commands.md), [LoopCaregiver Authentication](../loopcaregiver/authentication.md)

### Remote Command Types

| Action Type | LoopCaregiver | Loop (Receiver) | Description |
|-------------|---------------|-----------------|-------------|
| `bolusEntry` | `BolusAction(amountInUnits)` | `BolusRemoteNotification` | Remote insulin delivery |
| `carbsEntry` | `CarbAction(amountInGrams, absorptionTime?, startDate?)` | `CarbEntryRemoteNotification` | Remote carb entry |
| `temporaryScheduleOverride` | `OverrideAction(name, durationTime?, remoteAddress)` | `OverrideRemoteNotification` | Activate override by name |
| `cancelTemporaryOverride` | `OverrideCancelAction(remoteAddress)` | `OverrideCancelRemoteNotification` | Cancel active override |
| `autobolus` | `AutobolusAction(active)` | Remote 2.0 only | Toggle autobolus on/off |
| `closedLoop` | `ClosedLoopAction(active)` | Remote 2.0 only | Toggle closed loop on/off |

### Remote Command Status States

| LoopCaregiver State | Nightscout State | Description |
|---------------------|------------------|-------------|
| `.pending` | `Pending` | Command uploaded, awaiting Loop pickup |
| `.inProgress` | `InProgress` | Loop received, executing |
| `.success` | `Success` | Command completed successfully |
| `.error(message)` | `Error` | Execution failed with error message |

### Authentication Components

| Component | LoopCaregiver | Loop | Description |
|-----------|---------------|------|-------------|
| OTP Secret | `NightscoutCredentials.otpURL` | `OTPSecretStore` (Keychain) | Shared TOTP secret |
| OTP Manager | `OTPManager` | `OTPManager` | Generates/validates TOTP codes |
| OTP Parameters | SHA1, 6 digits, 30s | SHA1, 6 digits, 30s | Standard TOTP (RFC 6238) |
| Credential Service | `NightscoutCredentialService` | N/A | Wraps OTP with auto-refresh |

### QR Code Deep Link Format

| Field | Query Parameter | Required | Description |
|-------|-----------------|----------|-------------|
| Looper Name | `name` | Yes | Display name for the looper |
| Nightscout URL | `nsURL` | Yes | URL-encoded Nightscout server URL |
| API Secret | `secretKey` | Yes | Nightscout API_SECRET |
| OTP URL | `otpURL` | Yes | URL-encoded otpauth:// URI |
| Creation Date | `createdDate` | No | For watch configuration uniqueness |

**Deep Link URL Format**:
```
caregiver://createLooper?name={name}&secretKey={api_secret}&nsURL={ns_url_encoded}&otpURL={otp_url_encoded}
```

**OTP URL Format** (Standard TOTP):
```
otpauth://totp/{label}?algorithm=SHA1&digits=6&issuer=Loop&period=30&secret={base32_secret}
```

### Remote 2.0 vs 1.0 Comparison (LoopCaregiver)

| Aspect | Remote 1.0 | Remote 2.0 |
|--------|------------|------------|
| **Protocol** | Direct OTP in request | Command payload with status |
| **OTP Inclusion** | Query parameter | `otp` field in payload |
| **Status Tracking** | None | Pending → InProgress → Success/Error |
| **Command Types** | 4 (bolus, carbs, override, cancel) | 6 (adds autobolus, closedLoop) |
| **Version Field** | None | `version: "2.0"` |
| **Enable Flag** | N/A | `settings.remoteCommands2Enabled` |

### Caregiver Safety Features

| Feature | Implementation | Value |
|---------|----------------|-------|
| Recommended Bolus Expiry | `calculateValidRecommendedBolus()` | 7 minutes |
| Post-Bolus Rejection | Compare bolus timestamp vs deviceStatus | Reject if bolus after recommendation |
| Credential Validation | `checkAuth()` before storing | API call to Nightscout |
| OTP Refresh | Timer-based (1 second) | Always fresh code |

### Cross-App Command Comparison

| Feature | LoopCaregiver | LoopFollow | Nightguard | Trio Caregiver* |
|---------|---------------|------------|------------|-----------------|
| Remote Bolus | ✅ | ❌ | ❌ | ✅ |
| Remote Carbs | ✅ | ❌ | ❌ | ✅ |
| Remote Override | ✅ | ✅ | ❌ | ✅ |
| Cancel Override | ✅ | ✅ | ❌ | ✅ |
| Autobolus Toggle | ✅ | ❌ | ❌ | N/A |
| Closed Loop Toggle | ✅ | ❌ | ❌ | N/A |
| OTP Handling | Automatic | Manual | N/A | N/A (encrypted) |
| Status Tracking | ✅ | ❌ | N/A | ✅ |

*Trio uses encryption rather than OTP

**Source Files**:
- `loopcaregiver:LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/OTPManager.swift` - TOTP generation
- `loopcaregiver:LoopCaregiverKit/Sources/LoopCaregiverKit/Nightscout/NightscoutDataSource.swift` - Command upload
- `loopcaregiver:LoopCaregiverKit/Sources/LoopCaregiverKit/Models/DeepLinkParser.swift` - QR code parsing
- `loopcaregiver:LoopCaregiverKit/Sources/LoopCaregiverKit/Models/RemoteCommands/Action.swift` - Action types

**Gap Reference**: GAP-REMOTE-005, GAP-REMOTE-006

---

## LoopFollow Alarm Models

### Alarm Types

| Alarm Type | Category | Trigger | Default Threshold |
|------------|----------|---------|-------------------|
| `low` | Glucose | BG ≤ threshold | 70 mg/dL |
| `high` | Glucose | BG ≥ threshold | 180 mg/dL |
| `fastDrop` | Glucose | N consecutive drops ≥ delta | 18 mg/dL / 2 readings |
| `fastRise` | Glucose | N consecutive rises ≥ delta | 10 mg/dL / 3 readings |
| `missedReading` | Glucose | No BG for N minutes | 16 minutes |
| `temporary` | Glucose | One-time BG limit trigger | User-defined |
| `iob` | Insulin | IOB ≥ threshold OR bolus pattern | 6 units |
| `cob` | Food | COB ≥ threshold | 20 grams |
| `missedBolus` | Insulin | Carbs logged without bolus | 15 min delay |
| `recBolus` | Insulin | Recommended bolus ≥ threshold | 1 unit |
| `notLooping` | System | Loop not run for N minutes | 31 minutes |
| `buildExpire` | System | App expires in N days | 7 days |
| `sensorChange` | Device | Sensor age ≥ N days | 12 days |
| `pumpChange` | Device | Pump site age ≥ N days | 12 days |
| `pump` | Device | Reservoir ≤ N units | 20 units |
| `battery` | Device | Phone battery ≤ N% | 20% |
| `batteryDrop` | Device | Battery dropped N% in window | 10% / 15 min |
| `overrideStart` | Event | Override activated | N/A |
| `overrideEnd` | Event | Override ended | N/A |
| `tempTargetStart` | Event | Temp target activated | N/A |
| `tempTargetEnd` | Event | Temp target ended | N/A |

### Alarm Condition Parameters

| Parameter | Field | Description | Used By |
|-----------|-------|-------------|---------|
| BG Above | `aboveBG` | Upper BG threshold (mg/dL) | high, missedBolus |
| BG Below | `belowBG` | Lower BG threshold (mg/dL) | low |
| Threshold | `threshold` | Generic limit (units/grams/days/%) | iob, cob, battery, etc. |
| Predictive | `predictiveMinutes` | Look-ahead for predictions | low |
| Persistent | `persistentMinutes` | Duration BG must persist | low, high |
| Delta | `delta` | Change per reading (mg/dL) | fastDrop, fastRise, batteryDrop |
| Window | `monitoringWindow` | Readings/minutes to observe | fastDrop, fastRise, missedBolus |

### Day/Night Scheduling

| Option Type | Values | Description |
|-------------|--------|-------------|
| `ActiveOption` | always, day, night | When alarm is active |
| `PlaySoundOption` | always, day, night, never | When to play sound |
| `RepeatSoundOption` | always, day, night, never | When to repeat sound |

**Configuration**: `dayStart` (default 6:00 AM), `nightStart` (default 10:00 PM)

### Comparison with Other Caregiver Apps

| Feature | LoopFollow | LoopCaregiver | Nightguard |
|---------|------------|---------------|------------|
| Alarm Types | 20 | ~5 | 3-4 |
| Predictive Alarms | ✅ (low BG) | ❌ | ❌ |
| Persistent Alarms | ✅ | ❌ | ❌ |
| Delta Alarms | ✅ | ❌ | ❌ |
| Day/Night Scheduling | ✅ | ❌ | ❌ |
| Custom Sounds | ✅ (20+) | System | System |
| Missed Bolus | ✅ | ❌ | ❌ |
| Build Expiration | ✅ | ❌ | ❌ |

**Source Files**:
- `loopfollow:LoopFollow/Alarm/AlarmType/AlarmType.swift` - Type enumeration
- `loopfollow:LoopFollow/Alarm/Alarm.swift` - Alarm model
- `loopfollow:LoopFollow/Alarm/AlarmManager.swift` - Evaluation logic
- `loopfollow:LoopFollow/Alarm/AlarmCondition/*.swift` - Condition implementations

---

## LoopFollow Remote Command Models

### Remote Types

| Remote Type | Target AID | Transport | Security |
|-------------|------------|-----------|----------|
| `loopAPNS` | Loop | Direct APNS | TOTP + JWT |
| `trc` | Trio | Direct APNS | AES-256-GCM + JWT |
| `nightscout` | Trio | HTTPS API | Token (careportal) |

### TRC (Trio Remote Control) Commands

| Command | Type String | Parameters |
|---------|-------------|------------|
| Bolus | `bolus` | `bolusAmount` (Decimal) |
| Temp Target | `temp_target` | `target` (Int, mg/dL), `duration` (Int, min) |
| Cancel Temp Target | `cancel_temp_target` | - |
| Meal | `meal` | `carbs`, `protein`, `fat` (Int), `bolusAmount`?, `scheduledTime`? |
| Start Override | `start_override` | `overrideName` (String) |
| Cancel Override | `cancel_override` | - |

### TRC Encryption (AES-256-GCM)

| Step | Detail |
|------|--------|
| 1. Key Derivation | `SHA256(sharedSecret.utf8)` → 256-bit key |
| 2. Nonce | 12 random bytes (SecRandomCopyBytes) |
| 3. Encryption | AES-GCM combined mode (ciphertext + auth tag) |
| 4. Output | `Base64(nonce + encryptedBytes)` |

### Loop APNS Payload Fields

| Field | Description |
|-------|-------------|
| `otp` | 6-digit TOTP code |
| `bolus-entry` | Bolus amount (units) |
| `carbs-entry` | Carb amount (grams) |
| `absorption-time` | Carb absorption (hours) |
| `start-time` | Carb entry time (ISO 8601) |
| `expiration` | Command expiry (5 minutes) |
| `remote-address` | "LoopFollow" |

### Nightscout Remote Payload

| Field | Description |
|-------|-------------|
| `eventType` | "Temporary Target" |
| `targetTop` | Target value (mg/dL) |
| `targetBottom` | Target value (mg/dL) |
| `duration` | Minutes (0 = cancel) |
| `enteredBy` | "LoopFollow" |
| `reason` | "Manual" |

### Remote Security Comparison

| Aspect | Loop APNS | TRC | Nightscout |
|--------|-----------|-----|------------|
| Transport | TLS | TLS | TLS |
| Message Encryption | None | AES-256-GCM | None |
| Authentication | TOTP (30s) | Shared secret + timestamp | API token |
| Replay Protection | TOTP period | Timestamp validation | None |
| Command Types | 3 | 6 | 1 |

**Source Files**:
- `loopfollow:LoopFollow/Remote/RemoteType.swift` - Type enumeration
- `loopfollow:LoopFollow/Remote/TRC/PushNotificationManager.swift` - TRC implementation
- `loopfollow:LoopFollow/Remote/TRC/SecureMessenger.swift` - AES encryption
- `loopfollow:LoopFollow/Remote/LoopAPNS/LoopAPNSService.swift` - Loop APNS service
- `loopfollow:LoopFollow/Remote/LoopAPNS/TOTPService.swift` - TOTP handling

**Gap Reference**: GAP-LF-005 through GAP-LF-009

---

## Capability Layer Models

> **See Also**: [Progressive Enhancement Framework](../../docs/10-domain/progressive-enhancement-framework.md) for complete layer definitions.
> **See Also**: [Capability Layer Matrix](capability-layer-matrix.md) for system-by-system analysis.

### Layer Vocabulary

| Layer | Name | Key Capability | Example Systems |
|-------|------|----------------|-----------------|
| L0 | MDI Baseline | Manual insulin, fingersticks | Syringes, pens, meters |
| L1 | Structured MDI | Carb counting, logging | Diabetes apps |
| L2 | CGM Sensing | Continuous glucose, trends | Dexcom, Libre, Medtronic |
| L3 | Pump Therapy | Programmable basal, bolus | Omnipod, Tandem, Dana |
| L4 | Manual Pump+CGM | CGM-informed manual control | Pre-automation pump users |
| L5 | Safety Automation | Suspend, bounded corrections | Basal-IQ, SmartGuard |
| L6 | Full AID | Closed-loop control | Loop, AAPS, Trio, Control-IQ |
| L7 | Networked Care | Remote visibility, audit | Nightscout, Dexcom Follow |
| L8 | Remote Controls | Delegated actions | LoopCaregiver, AAPS SMS |
| L9 | Delegate Agents | Autonomous agents | (Future) |

### Three-State Model (L6+)

| State | Definition | Examples |
|-------|------------|----------|
| **Desired** | What we want to achieve | Targets, ISF, CR, overrides, constraints |
| **Observed** | What actually happened | Delivered insulin, CGM readings, IOB, COB |
| **Capabilities** | What's possible now | CGM quality, pump type, comms status, max rates |

**Implementation Mapping**:

| State | Loop | AAPS | Trio |
|-------|------|------|------|
| Desired | `TherapySettings`, `TemporaryScheduleOverride` | `ProfileSwitch`, `TempTarget` | Settings + `Override` |
| Observed | `DoseEntry`, `StoredGlucoseSample`, `InsulinOnBoard` | `Bolus`, `GlucoseValue`, `IobTotal` | via oref0 state |
| Capabilities | `PumpManagerStatus.deliveryStatus` | `Pump.isSuspended()`, `LoopState` | `LoopStatus` |

### Delegation Authority Levels

| Level | Actor Type | Permissions | Audit |
|-------|------------|-------------|-------|
| Primary | Human (person with diabetes) | Full control | Optional |
| Caregiver | Human (parent, partner) | Scoped by primary | Required |
| Clinician | Human (healthcare provider) | View + recommend | Required |
| Observer | Human (friend, teacher) | View only | Optional |
| Agent | Software | Bounded autonomy | Required |
| Controller | AID system | Therapy execution | Automatic |

**Current Gap**: No system implements this hierarchy (GAP-DELEGATE-001, GAP-DELEGATE-002)

### Agent Operation Patterns

| Pattern | Description | Trust Level | Implementation |
|---------|-------------|-------------|----------------|
| Advisory | Propose only, no action | Low | Notification with suggestion |
| Confirm-to-Enact | Await human approval | Medium | Proposal + authorization workflow |
| Bounded Autonomy | Act within strict limits | High | Scoped permissions + rollback |
| Full Autonomy | Unrestricted action | Maximum | (Not recommended) |

**Current Gap**: No system implements propose-authorize-enact (GAP-DELEGATE-005)

### Out-of-Band Signal Types

| Signal | Sources | Use Cases | Integration Status |
|--------|---------|-----------|-------------------|
| Exercise | Calendar, HR, steps, GPS | Pre-exercise target, post-exercise sensitivity | Manual (override) |
| Menstrual cycle | Cycle apps, user annotation | Hormone-phase sensitivity | Manual |
| Sleep | Sleep trackers, time-of-day | Overnight targets | Schedule-based |
| Illness | Self-report, HRV | Sick-day rules | Manual |
| Meals | Photo, routine, calendar | Carb estimation | Manual |

**Current Gap**: No structured API for context integration (GAP-DELEGATE-003)

### Graceful Degradation Paths

| From Layer | Trigger | To Layer | Action |
|------------|---------|----------|--------|
| L6 (AID) | CGM stale | L4 (Manual) | Suspend automation, resume scheduled basal |
| L6 (AID) | Pump comms fail | L0/L1 (MDI) | Alert user, provide MDI guidance |
| L8 (Remote) | Network loss | L7 (View) | Maintain read-only access |
| L8 (Remote) | Push failure | L6 (Local) | Fallback to local control |
| L9 (Agent) | Context stale | L8 (Human) | Revert to human delegation |
| L9 (Agent) | Low confidence | L8 (Human) | Switch to propose-only mode |

**Requirement Reference**: REQ-DEGRADE-001 through REQ-DEGRADE-006

**Source Files**:
- Loop: `LoopDataManager.swift` - staleness checks
- AAPS: `LoopPlugin.kt` - loop state management
- Trio: `LoopStatus.swift` - loop state tracking

**Gap Reference**: GAP-DELEGATE-001 through GAP-DELEGATE-005

---

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2026-01-29 | Agent | Added oref0 runner results, conformance runner table, 69% AAPS divergence finding |
| 2026-01-29 | Agent | Added API v3 Deduplication Keys and Timestamp Fields tables from API layer audit |
| 2026-01-29 | Agent | Added Algorithm Conformance Testing section with entry points, input/output shapes, test fixture locations |
| 2026-01-17 | Agent | Added Capability Layer Models section with layer vocabulary, three-state model, delegation authority levels, agent patterns, graceful degradation paths |
| 2026-01-17 | Agent | Added LoopFollow Alarm Models and Remote Command Models sections |
| 2026-01-17 | Agent | Added LoopCaregiver Remote 2.0 Models section with command types, status states, auth components, deep links |
| 2026-01-17 | Agent | Added Libre CGM Protocol Models section with sensor types, FRAM layout, encryption, BLE, transmitter bridges |
| 2026-01-17 | Agent | Added Carb Absorption Models section with curve types, COB calculation, parameters, UAM handling |
| 2026-01-17 | Agent | Added Dexcom BLE Protocol Models section with UUIDs, opcodes, message structures, authentication |
| 2026-01-17 | Agent | Added Pump Communication Models section with interface, commands, protocols, and state machines |
| 2026-01-17 | Agent | Added API Version Models section with v1/v3 comparison |
| 2026-01-17 | Agent | Added Remote Command Security Models section with cross-system comparison |
| 2026-01-16 | Agent | Integrated xDrip+ (Android) into terminology matrix - events, sync identity, actor identity, device events, code references |
| 2026-01-16 | Agent | Added oref0-specific concepts (algorithm components, prediction curves, carb model, SMB params, shared IOB formula) |
| 2026-01-16 | Agent | Added Trio-specific concepts (oref2 variables, remote commands, overrides, insulin curves, dynamic ISF) |
| 2026-01-16 | Agent | Added algorithm/controller concepts, safety constraints, pump commands, insulin models, loop states |
| 2026-01-16 | Agent | Initial cross-project terminology matrix |

## Algorithm Conformance Testing

> **See Also**: [Algorithm Conformance Suite Proposal](../../docs/sdqctl-proposals/algorithm-conformance-suite.md)

### Algorithm Entry Points

| Alignment Term | oref0 | AAPS | Loop | Trio |
|----------------|-------|------|------|------|
| Main Function | `determine_basal()` | `DetermineBasalSMB.kt` | `LoopAlgorithm.run()` | `OpenAPS.makeProfiles()` |
| JS Adapter | N/A (native JS) | `DetermineBasalAdapterSMBJS.kt` | N/A | N/A |
| Input Type | Function params | `GlucoseStatus`, `IobTotal`, etc. | `LoopAlgorithmInput` | JS objects |
| Output Type | JSON object | `APSResult` | `LoopAlgorithmOutput` | `Suggestion` |

### Algorithm Input Shapes (Conformance Mapping)

| Conformance Field | oref0 | AAPS | Loop |
|-------------------|-------|------|------|
| `glucoseStatus.glucose` | `glucose_status.glucose` | `glucoseStatus.glucose` | `glucoseHistory.last().quantity` |
| `glucoseStatus.delta` | `glucose_status.delta` | `glucoseStatus.delta` | Computed from history |
| `iob.iob` | `iob_data.iob` | `iobTotal.iob` | `insulinOnBoard` |
| `iob.basalIob` | `iob_data.basaliob` | `iobTotal.basaliob` | N/A (combined) |
| `profile.sensitivity` | `profile.sens` | `profile.sens` | `settings.sensitivity` |
| `profile.carbRatio` | `profile.carb_ratio` | `profile.carb_ratio` | `settings.carbRatio` |
| `profile.targetLow` | `profile.min_bg` | `profile.target_bg` | `settings.target.lowerBound` |
| `mealData.cob` | `meal_data.mealCOB` | `mealData.mealCOB` | `carbsOnBoard` |

### Algorithm Output Shapes (Conformance Mapping)

| Conformance Field | oref0 | AAPS | Loop |
|-------------------|-------|------|------|
| `rate` | `suggested.rate` | `result.rate` | `tempBasal.rate` |
| `duration` | `suggested.duration` | `result.duration` | `tempBasal.duration` |
| `smb` | `suggested.units` | `result.smb` | N/A (no SMB) |
| `eventualBG` | `suggested.eventualBG` | `result.eventualBG` | `predictedGlucose.last` |
| `reason` | `suggested.reason` | `result.reason` | `recommendation.notice` |

### Test Fixture Locations

| Project | Test Framework | Fixture Path |
|---------|---------------|--------------|
| oref0 | Mocha + Should.js | `tests/determine-basal.test.js` (inline) |
| AAPS | JUnit + JSONAssert | `app/src/androidTest/assets/results/*.json` |
| Loop | XCTest | `LoopKitTests/Fixtures/{DoseMath,CarbKit,InsulinKit}/` |
| Trio | XCTest | Uses LoopKit fixtures |

**Gap Reference**: GAP-ALG-001 (no cross-project vectors), GAP-ALG-002 (drift detection), GAP-ALG-003 (semantic mapping)


## Plugin System Architecture

> **See Also**: [Plugin Deep Dive](../../docs/10-domain/cgm-remote-monitor-plugin-deep-dive.md)

### Plugin Types

| Type | Purpose | Examples |
|------|---------|----------|
| `pill-primary` | Main display element | bgnow |
| `pill-major` | Key metrics | iob |
| `pill-minor` | Secondary metrics | cob, insulinage, sensorage |
| `pill-status` | System status | loop, openaps, pump |
| `notification` | Alerts | simplealarms, treatmentnotify |
| `drawer` | UI panels | careportal, boluscalc |
| `forecast` | Predictions | ar2 |

### IOB Calculation Sources

| Source | Priority | Path | Controller |
|--------|----------|------|------------|
| Loop devicestatus | 1 | `status.loop.iob` | Loop |
| OpenAPS devicestatus | 1 | `status.openaps.iob[0]` | OpenAPS/AAPS |
| Pump devicestatus | 2 | `status.pump.iob` | Pump-reported |
| Treatment fallback | 3 | Calculated from `treatments` | All |

### COB Calculation Sources

| Source | Priority | Freshness | Path |
|--------|----------|-----------|------|
| OpenAPS suggested | 1 | 10 min | `status.openaps.suggested.COB` |
| OpenAPS enacted | 1 | 10 min | `status.openaps.enacted.COB` |
| Loop COB | 1 | 10 min | `status.loop.cob.cob` |
| Treatment fallback | 2 | N/A | Calculated from `treatments` |

### Prediction Format Comparison

| Aspect | Loop | OpenAPS/AAPS |
|--------|------|--------------|
| Structure | Single array | 6 separate arrays |
| Field | `predicted.values[]` | `predBGs.{IOB,ZT,COB,aCOB,UAM}[]` |
| Interval | 5 minutes | 5 minutes |
| Start time | `predicted.startDate` | Inferred |

**Gap Reference**: GAP-PLUGIN-002

### Controller Status Symbols

| Symbol | Loop Meaning | OpenAPS Meaning |
|--------|--------------|-----------------|
| ↻ | Looping | Looping |
| ⌁ | Enacted | Enacted (received) |
| ⏀ | Recommendation | - |
| ◉ | - | Waiting |
| x | Error | Not enacted |
| ⚠ | Warning | Warning |


## Sync/Upload Architecture

> **See Also**: [Sync Deep Dive](../../docs/10-domain/cgm-remote-monitor-sync-deep-dive.md)

### Socket.IO Namespaces

| Namespace | Purpose | Key Events |
|-----------|---------|------------|
| `/` (default) | Main data channel | `dataUpdate`, `authorize`, `loadRetro` |
| `/alarm` | Alarm notifications | `alarm`, `urgent_alarm`, `clear_alarm`, `ack` |
| `/storage` | CRUD notifications | `create`, `update`, `delete` |

### Socket.IO Events

| Event | Direction | Payload | Purpose |
|-------|-----------|---------|---------|
| `dataUpdate` | Server→Client | Delta object | Incremental data broadcast |
| `retroUpdate` | Server→Client | `{devicestatus: [...]}` | Historical data |
| `authorize` | Client→Server | Secret/token | Authentication |
| `loadRetro` | Client→Server | - | Request history |
| `connected` | Server→Client | - | Auth success |
| `clients` | Server→Client | Number | Active client count |

### Sync Identity Components

| Collection | UUID v5 Input | Dedup Fallback Fields |
|------------|---------------|----------------------|
| entries | `device \| date \| type` | `date`, `type` |
| treatments | `device \| created_at \| eventType` | `created_at`, `eventType` |
| devicestatus | `created_at \| device` | `created_at`, `device` |

### Event Bus Flow

| Event | Trigger | Listener | Result |
|-------|---------|----------|--------|
| `tick` | Timer (heartbeat) | bootevent | Refresh data |
| `data-received` | Upload handler | bootevent | Reload from DB |
| `data-loaded` | Dataloader | bootevent | Process plugins |
| `data-processed` | Plugin processing | websocket | Broadcast delta |

**Gap Reference**: GAP-SYNC-008, GAP-SYNC-009, GAP-SYNC-010


## Authentication Architecture

> **See Also**: [Auth Deep Dive](../../docs/10-domain/cgm-remote-monitor-auth-deep-dive.md)

### Permission String Format

```
[domain]:[collection]:[action]
```

| Component | Examples | Description |
|-----------|----------|-------------|
| domain | `api`, `admin` | Top-level namespace |
| collection | `entries`, `treatments`, `subjects` | Resource type |
| action | `read`, `create`, `update`, `delete` | Operation |

### Default Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| `admin` | `['*']` | Full access |
| `denied` | `[]` | No access |
| `status-only` | `['api:status:read']` | Read status only |
| `readable` | `['*:*:read']` | Read-only access |
| `careportal` | `['api:treatments:create']` | Treatment creation |
| `devicestatus-upload` | `['api:devicestatus:create']` | Device uploads |
| `activity` | `['api:activity:create']` | Activity logs |

### Authentication Methods

| Method | Header/Param | Grants | Use Case |
|--------|--------------|--------|----------|
| API Secret | `api-secret` header | `*` (admin) | Legacy, admin ops |
| JWT Token | `Authorization: Bearer` | Per-subject roles | API v3, modern clients |
| Access Token | `?token=` param | Per-subject roles | Initial auth, get JWT |

### Token Formats

| Type | Format | Lifetime | Example |
|------|--------|----------|---------|
| API Secret | User-defined string | Permanent | `my-secret-key-123` |
| Access Token | `{name}-{digest}` | Permanent | `myuploader-a1b2c3d4e5f6` |
| JWT | Base64 encoded | 8 hours | `eyJhbGciOiJIUzI1NiIs...` |

### Rate Limiting

| Trigger | Delay | Cumulative |
|---------|-------|------------|
| Failed auth | 5 seconds | Yes |
| Cleanup | 60 seconds | - |

**Gap Reference**: GAP-AUTH-001, GAP-AUTH-002, GAP-AUTH-003


## Frontend Architecture

> **See Also**: [Frontend Deep Dive](../../docs/10-domain/cgm-remote-monitor-frontend-deep-dive.md)

### Chart Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| Focus View | Main glucose display (70%) | D3.js |
| Context View | Timeline brush (30%) | D3.js |
| Basals | Basal rate area chart | D3.js stepAfter |
| Treatment Markers | Bolus/carb arcs | SVG arcs |

### D3 Scales

| Scale | Type | Domain | Purpose |
|-------|------|--------|---------|
| xScale | Time | Brush extent | Focus X-axis |
| xScale2 | Time | Full data | Context X-axis |
| yScale | Linear/Log | 30 to max SGV | Focus Y-axis |
| futureOpacity | Linear | 0.8 to 0.1 | Prediction fade |

### Plugin UI Containers

| Type | CSS Class | Examples |
|------|-----------|----------|
| `pill-major` | `.majorPills` | IOB, COB |
| `pill-minor` | `.minorPills` | Pump age, sensor age |
| `pill-status` | `.statusPills` | Loop, OpenAPS |
| `drawer` | `#drawer` | Careportal, bolus calc |

### Bundle Structure

| Bundle | Entry Point | Purpose |
|--------|-------------|---------|
| `bundle.source.js` | `lib/client/index.js` | Main app |
| `bundle.clocks.source.js` | `lib/client/clock-client.js` | Clock view |
| `bundle.reports.source.js` | `lib/client/report-client.js` | Reports |

### Translation System

| Component | Purpose |
|-----------|---------|
| `language.set()` | Set current language |
| `language.translate()` | Translate string |
| `language.DOMtranslate()` | Auto-translate DOM |
| Placeholders | `%1`, `%2` for params |

**Languages**: 33 (Arabic, Chinese, English, French, German, Japanese, Spanish, etc.)

**Gap Reference**: GAP-UI-001, GAP-UI-002, GAP-UI-003


## Interoperability Specification

> **See Also**: [Interoperability Spec](../../specs/interoperability-spec-v1.md)

### Conformance Levels

| Level | Description | Required Sections |
|-------|-------------|-------------------|
| Reader | Read-only data access | 2, 3, 4 |
| Uploader | Write glucose/treatments | 2-6 |
| Controller | Full AID integration | All |

### Requirement Keywords (RFC 2119)

| Keyword | Meaning |
|---------|---------|
| MUST | Absolute requirement |
| SHOULD | Recommended, may be ignored with reason |
| MAY | Optional |

### Core Collections Summary

| Collection | Purpose | Dedup Key |
|------------|---------|-----------|
| entries | Glucose readings | `date` + `type` |
| treatments | Boluses, carbs, events | `created_at` + `eventType` |
| devicestatus | Controller state | `created_at` + `device` |
| profile | Therapy settings | `created_at` |

### Standard eventTypes

| Category | eventTypes |
|----------|------------|
| Insulin | Correction Bolus, Meal Bolus, Temp Basal |
| Carbs | Carb Correction, Meal Bolus |
| Targets | Temporary Target, Profile Switch |
| Events | Note, Exercise, Site Change, Sensor Start |


## nightscout-connect Bridge

> **See Also**: [nightscout-connect Deep Dive](../../docs/10-domain/nightscout-connect-deep-dive.md)

### XState Machine Terms

| Term | Description |
|------|-------------|
| Poller | Top-level bus machine owning session and cycles |
| Session Machine | Manages authentication lifecycle |
| Cycle Machine | Periodic polling loop for one data type |
| Fetch Machine | Single data fetch with retry logic |
| Frame | One complete fetch attempt |

### Machine States

| Machine | States |
|---------|--------|
| Fetch | Idle, Waiting, Auth, DetermineGaps, Fetching, Transforming, Persisting, Success, Error, Done |
| Session | Inactive, Authenticating, Authorizing, Established, Active, Refreshing, Expired |
| Cycle | Init, Ready, Operating, After |

### Key Events

| Event | Direction | Purpose |
|-------|-----------|---------|
| SESSION_REQUIRED | fetch → session | Request active session |
| SESSION_RESOLVED | session → fetch | Provide session token |
| GAP_ANALYSIS | fetch → source | Determine query window |
| DATA_RECEIVED | fetch → transform | Raw vendor data |
| STORE | fetch → output | Persist data |

### Source Drivers

| Source | Vendor | Data Types |
|--------|--------|------------|
| dexcomshare | Dexcom Share | entries |
| librelinkup | LibreLinkUp | entries |
| nightscout | Nightscout | entries |
| glooko | Glooko | treatments |
| minimedcarelink | Medtronic CareLink | entries, treatments, devicestatus |

### Builder Pattern

| Method | Purpose |
|--------|---------|
| support_session() | Register auth promises |
| register_loop() | Create polling cycle |
| tracker_for() | Gap analysis setup |


## Carb Absorption Models

> **See Also**: [Carb Absorption Comparison](../../docs/10-domain/carb-absorption-comparison.md)

### Model Paradigms

| Paradigm | Description | Systems |
|----------|-------------|---------|
| Predictive | Models expected absorption curve, adjusts based on observed effects | Loop |
| Reactive | Infers absorption from glucose deviation vs insulin prediction | oref0, AAPS, Trio |

### Absorption Curve Types

| Curve | Description | System |
|-------|-------------|--------|
| Linear | Constant absorption rate over time | Loop, oref0 |
| Parabolic (Scheiner) | Slower start/end, peak in middle | Loop |
| Piecewise Linear | Rise (0-15%), plateau (15-50%), fall (50-100%) | Loop (default) |
| Bilinear/Weighted | Dynamic based on max absorption time | AAPS |

### Key Parameters

| Parameter | Loop | oref0 | AAPS | Trio |
|-----------|------|-------|------|------|
| Default Absorption Time | 3h | Profile | Profile | Profile |
| Max Absorption Time | 10h | 6h | Configurable | 6h |
| Min 5m Impact | Curve-based | 8 mg/dL | 8 mg/dL | 8 mg/dL |
| Max COB | None | None | None | 120g |

### Key Formulas

| Formula | Description |
|---------|-------------|
| CSF = ISF / CR | Carb Sensitivity Factor |
| CI = deviation × CR / ISF | Carb Impact (oref0) |
| COB = carbs × (1 - %absorbed) | COB (Loop) |
| COB = carbs - Σ(absorbed) | COB (oref0) |

### UAM Detection

| System | Method |
|--------|--------|
| Loop | Implicit via retrospective correction |
| oref0 | Explicit deviation slope analysis |
| AAPS | enableUAM constraint |
| Trio | enableUAM setting |


## Pump Communication Terminology

> **Systems**: Loop, AAPS, xDrip+

### Insulin Container Terms

| Concept | Loop | AAPS | xDrip+ | Nightscout |
|---------|------|------|--------|------------|
| Insulin container | `reservoir` | `reservoirLevel` | `reservoirAmount` | `pump.reservoir` |
| Container level | `reservoirLevel` | `reservoirLevel: Double` | `reservoirRemainingUnits` | `pump.reservoir.amount` |
| Low warning | N/A (app handles) | `PUMP_LOW_RESERVOIR` | N/A | N/A |
| Empty state | N/A | `RESERVOIR_EMPTY` | N/A | N/A |

**Source References**:
- Loop: `LoopKit/InsulinKit/PumpEventType.swift:88`
- AAPS: `core/data/src/main/kotlin/app/aaps/core/data/pump/defs/Pump.kt:124`
- xDrip+: `app/src/main/java/com/eveningoutpost/dexdrip/models/PumpStatus.java:19`

### Device Type Terms

| Concept | Loop | AAPS | xDrip+ |
|---------|------|------|--------|
| Patch pump | `pod` | `Pod` | N/A |
| Traditional pump | `pump` | `Pump` | `pump` |
| Full replacement | `ReplaceableComponent.pump` | `PodStatus.DEACTIVATED` | N/A |
| Infusion set | `infusionSet` | N/A | N/A |

**Source References**:
- Loop: `LoopKit/InsulinKit/PumpEventType.swift:89-90`
- AAPS: `pump/medtrum/src/main/kotlin/app/aaps/pump/medtrum/comm/enums/PodStatus.kt`

### Battery/Power Terms

| Concept | Loop | AAPS | xDrip+ | Nightscout |
|---------|------|------|--------|------------|
| Battery level | `pumpBatteryChargeRemaining` | `batteryLevel: Int?` | `pumpBatteryLevelPercent` | `pump.battery.percent` |
| Low battery | N/A | `PUMP_LOW_BATTERY` | N/A | N/A |
| Battery out | N/A | `BATTERY_OUT` | N/A | N/A |

**Source References**:
- Loop: `LoopKit/DeviceManager/PumpManagerStatus.swift:64`
- AAPS: `core/data/src/main/kotlin/app/aaps/core/data/pump/defs/Pump.kt:129`
- xDrip+: `app/src/main/java/com/eveningoutpost/dexdrip/utils/framework/RecentData.java`

### Pump State Terms

| State | Loop | AAPS | xDrip+ |
|-------|------|------|--------|
| Active/Delivering | `BasalDeliveryState.active` | `ACTIVE` | N/A |
| Suspended | `BasalDeliveryState.suspended` | `SUSPENDED`, `PAUSED` | `pumpSuspended` |
| Suspending | `BasalDeliveryState.suspending` | N/A | N/A |
| Resuming | `BasalDeliveryState.resuming` | N/A | N/A |
| Temp basal | `BasalDeliveryState.tempBasal` | `TemporaryBasal` | N/A |
| Occlusion | N/A | `OCCLUSION` | N/A |
| Expired | N/A | `EXPIRED` | N/A |

**Source References**:
- Loop: `LoopKit/DeviceManager/PumpManagerStatus.swift:39-45`
- AAPS: `pump/medtrum/src/main/kotlin/app/aaps/pump/medtrum/comm/enums/MedtrumPumpState.kt`
- xDrip+: `app/src/main/java/com/eveningoutpost/dexdrip/utils/framework/RecentData.java`

### Bolus State Terms

| State | Loop | AAPS | xDrip+ |
|-------|------|------|--------|
| No bolus | `BolusState.noBolus` | N/A | N/A |
| Initiating | `BolusState.initiating` | N/A | N/A |
| In progress | `BolusState.inProgress` | `NORMAL` | N/A |
| SMB | N/A | `SMB` | N/A |
| Priming | N/A | `PRIMING` | N/A |
| Extended | N/A | `extendedBolus` | N/A |

**Source References**:
- Loop: `LoopKit/DeviceManager/PumpManagerStatus.swift:56-58`
- AAPS: `core/data/src/main/kotlin/app/aaps/core/data/db/BS.kt:36-39`

### Bolus Activation Types (Loop)

| Type | Description |
|------|-------------|
| `automatic` | Closed-loop automatic bolus |
| `manualRecommendationAccepted` | User accepted recommendation |
| `manualRecommendationChanged` | User modified recommendation |
| `manualNoRecommendation` | Manual entry without recommendation |

**Source**: `LoopKit/DeviceManager/BolusActivationType.swift:9-14`

### Temp Basal Types (AAPS)

| Type | Description |
|------|-------------|
| `NORMAL` | Standard temp basal |
| `EMULATED_PUMP_SUSPEND` | Emulated via zero temp |
| `PUMP_SUSPEND` | Actual pump suspend |
| `SUPERBOLUS` | Superbolus mode |
| `FAKE_EXTENDED` | Emulated extended bolus |

**Source**: `core/interfaces/src/main/kotlin/app/aaps/core/interfaces/pump/PumpSync.kt:300-320`

### Pod Setup States (Loop/OmniKit)

| State | Description |
|-------|-------------|
| `podPaired` | Pod successfully paired |
| `cannulaInserting` | Cannula insertion in progress |
| `priming` | Pod priming |
| `running` | Pod active |

**Source**: `OmniKit/PumpManager/PodState.swift:14-20`

### Pump Event Types (Loop)

| Event | Description |
|-------|-------------|
| `prime` | Pump/pod priming |
| `rewind` | Reservoir change |
| `suspend` | Delivery suspended |
| `resume` | Delivery resumed |
| `tempBasal` | Temp basal set |

**Source**: `LoopKit/InsulinKit/PumpEventType.swift:16-24`

### xDrip+ Pump Integration

| Field | Source | Description |
|-------|--------|-------------|
| `pumpModelNumber` | RecentData | Device model |
| `pumpSuspended` | RecentData | Boolean suspension |
| `pumpCommunicationState` | RecentData | Connection status |
| `pumpBannerState` | RecentData | Banner alerts list |

**Source**: `app/src/main/java/com/eveningoutpost/dexdrip/utils/framework/RecentData.java`

### Nightscout devicestatus.pump Structure

```json
{
  "pump": {
    "reservoir": 150.5,
    "battery": {
      "percent": 75
    },
    "iob": {
      "bolusiob": 2.5
    },
    "status": {
      "suspended": false
    }
  }
}
```


---

## Algorithm Conformance Testing

### Test Vector Format

| Term | Definition | Schema Location |
|------|------------|-----------------|
| **Test Vector** | Standardized input/output pair for algorithm validation | `conformance/schemas/conformance-vector-v1.json` |
| **glucoseStatus** | Current CGM reading + deltas | `input.glucoseStatus` |
| **iob** | Insulin on board snapshot | `input.iob` |
| **profile** | Current therapy settings | `input.profile` |
| **mealData** | Carb/COB information | `input.mealData` |
| **expected** | Expected algorithm output (rates, durations) | `expected` object |
| **assertions** | Semantic behavioral checks | `assertions` array |

### Conformance Runners

| Runner | Target Algorithm | Location | Status |
|--------|-----------------|----------|--------|
| **oref0-runner** | oref0 determine-basal | `conformance/runners/oref0-runner.js` | ✅ Complete |
| **aaps-runner** | AAPS Kotlin algorithm | `conformance/runners/aaps/` | 🔄 Planned |
| **loop-runner** | Loop algorithm | `conformance/runners/loop/` | 🔄 Planned |

### oref0 Runner Results (2026-01-29)

| Category | Passed | Total | Rate | Notes |
|----------|--------|-------|------|-------|
| basal-adjustment | 24 | 77 | 31% | eventualBG differs |
| low-glucose-suspend | 2 | 8 | 25% | Safety logic matches |
| **Total** | 26 | 85 | **31%** | 69% divergence from AAPS |

### Test Vector Categories

| Category | Description | Use Case |
|----------|-------------|----------|
| `basal-adjustment` | Temp basal rate changes | Normal glucose management |
| `smb-delivery` | SuperMicroBolus scenarios | Rapid correction |
| `low-glucose-suspend` | LGS safety behavior | Hypoglycemia prevention |
| `carb-absorption` | COB impact on dosing | Meal handling |
| `safety-limits` | Max IOB/basal enforcement | Safety validation |
| `autosens` | Sensitivity adjustments | Dynamic tuning |
| `exercise-mode` | Override/activity adjustments | Activity handling |

### Assertion Types

| Assertion | Validates |
|-----------|-----------|
| `rate_increased` | Temp basal > scheduled basal |
| `rate_decreased` | Temp basal < scheduled basal |
| `rate_zero` | Temp basal suspended (0 U/hr) |
| `smb_delivered` | SMB bolus issued |
| `no_smb` | SMB withheld |
| `safety_limit` | Output within safety bounds |
| `eventual_in_range` | Predicted BG reaches target |

**Source**: `conformance/schemas/conformance-vector-v1.json`, `conformance/runners/oref0-runner.js`

---

## Traceability Terminology

### Requirement ID Formats

| Format | Domain | Example |
|--------|--------|---------|
| `REQ-NNN` | General/legacy | REQ-030 |
| `REQ-SYNC-NNN` | Sync & identity | REQ-SYNC-036 |
| `REQ-TREAT-NNN` | Treatments | REQ-TREAT-040 |
| `REQ-ALG-NNN` | Algorithms | REQ-ALG-001 |
| `REQ-BLE-NNN` | BLE/CGM protocols | REQ-BLE-001 |
| `REQ-OVERRIDE-NNN` | Override behavior | REQ-OVERRIDE-001 |
| `REQ-UNIT-NNN` | Unit handling | REQ-UNIT-001 |
| `REQ-ALARM-NNN` | Caregiver alarms | REQ-ALARM-001 |
| `REQ-REMOTE-NNN` | Remote commands | REQ-REMOTE-001 |
| `REQ-CONNECT-NNN` | nightscout-connect | REQ-CONNECT-001 |
| `REQ-NOCTURNE-NNN` | Nocturne-specific | REQ-NOCTURNE-001 |
| `REQ-TCONNECT-NNN` | tconnectsync | REQ-TCONNECT-001 |
| `REQ-TEST-NNN` | Testing infrastructure | REQ-TEST-001 |
| `REQ-SHARE-NNN` | share2nightscout-bridge | REQ-SHARE-001 |
| `REQ-LIBRELINK-NNN` | nightscout-librelink-up | REQ-LIBRELINK-001 |
| `REQ-LOOPFOLLOW-NNN` | LoopFollow | REQ-LOOPFOLLOW-001 |
| `REQ-LOOPCAREGIVER-NNN` | LoopCaregiver | REQ-LOOPCAREGIVER-001 |

### Gap ID Formats

| Format | Domain | Example |
|--------|--------|---------|
| `GAP-SYNC-NNN` | Sync & identity | GAP-SYNC-001 |
| `GAP-TREAT-NNN` | Treatments | GAP-TREAT-001 |
| `GAP-ALG-NNN` | Algorithms | GAP-ALG-001 |
| `GAP-BLE-NNN` | BLE/CGM protocols | GAP-BLE-001 |
| `GAP-BATCH-NNN` | Batch operations | GAP-BATCH-001 |
| `GAP-TZ-NNN` | Timezone handling | GAP-TZ-001 |
| `GAP-SESSION-NNN` | CGM session | GAP-SESSION-001 |
| `GAP-CONNECT-NNN` | nightscout-connect | GAP-CONNECT-001 |
| `GAP-NOCTURNE-NNN` | Nocturne-specific | GAP-NOCTURNE-001 |
| `GAP-TCONNECT-NNN` | tconnectsync | GAP-TCONNECT-001 |
| `GAP-TEST-NNN` | Testing infrastructure | GAP-TEST-001 |
| `GAP-SHARE-NNN` | share2nightscout-bridge | GAP-SHARE-001 |
| `GAP-LIBRELINK-NNN` | nightscout-librelink-up | GAP-LIBRELINK-001 |
| `GAP-LOOPFOLLOW-NNN` | LoopFollow | GAP-LOOPFOLLOW-001 |
| `GAP-LOOPCAREGIVER-NNN` | LoopCaregiver | GAP-LOOPCAREGIVER-001 |
| `GAP-XDRIPJS-NNN` | xdrip-js Node.js | GAP-XDRIPJS-001 |
| `GAP-XDRIP-NNN` | xDrip+ Android | GAP-XDRIP-001 |
| `GAP-CGM-NNN` | CGM general | GAP-CGM-001 |

### Traceability Concepts

| Term | Definition |
|------|------------|
| **Orphaned assertion** | Assertion with no linked REQ or GAP |
| **Scenario-level requirements** | REQs declared at file level, apply to all assertions |
| **Requirement coverage** | % of REQs with linked assertions |
| **Gap coverage** | % of GAPs with linked assertions |
| **Traceability matrix** | REQ → Spec → Test linkage |

**Source**: `tools/verify_assertions.py`, `traceability/assertion-trace.md`

### Verification Concepts

| Term | Definition |
|------|------------|
| **Claim verification** | Validating doc statements against source code |
| **Ref validation** | Checking `repo:path` references resolve to files |
| **Gap freshness** | Confirming documented gaps still exist |
| **Mapping coverage** | % of source fields documented in mappings |
| **Accuracy rate** | % of claims verified as correct |

**Verification Levels** (bottom-up):
| Level | Focus | Method |
|-------|-------|--------|
| 1 | Evidence sources | `verify_refs.py` |
| 2 | Mappings | Grep field names in source |
| 3 | Deep dives | Manual claim extraction + grep |
| 4 | Gaps | `verify_gap_freshness.py` (proposed) |
| 5 | Requirements | `verify_assertions.py` |
| 6 | Proposals | Cross-reference coherence |

**Source**: `docs/sdqctl-proposals/backlogs/documentation-accuracy.md`

## Trend Arrow Standardization

See `docs/10-domain/cgm-trend-arrow-standardization.md` for full cross-project mapping.

| Term | Nightscout | xDrip+ | Loop | AAPS | DiaBLE |
|------|------------|--------|------|------|--------|
| Rising very rapidly | DoubleUp (1) | DOUBLE_UP | upUpUp | DOUBLE_UP | risingQuickly |
| Rising rapidly | SingleUp (2) | SINGLE_UP | upUp | SINGLE_UP | rising |
| Rising | FortyFiveUp (3) | UP_45 | up | FORTY_FIVE_UP | rising |
| Stable | Flat (4) | FLAT | flat | FLAT | stable |
| Falling | FortyFiveDown (5) | DOWN_45 | down | FORTY_FIVE_DOWN | falling |
| Falling rapidly | SingleDown (6) | SINGLE_DOWN | downDown | SINGLE_DOWN | falling |
| Falling very rapidly | DoubleDown (7) | DOUBLE_DOWN | downDownDown | DOUBLE_DOWN | fallingQuickly |
| Not computable | NOT COMPUTABLE (8) | NOT_COMPUTABLE | - | NONE | notDetermined |
| Rate out of range | RATE OUT OF RANGE (9) | OUT_OF_RANGE | - | TRIPLE_UP/DOWN | - |
