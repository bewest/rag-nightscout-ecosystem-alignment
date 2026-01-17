# xdrip-js Data Models

This document describes the data structures used by xdrip-js for glucose readings, calibration tracking, battery status, and version information.

## Glucose Data Model

The `Glucose` class (`lib/glucose.js`) combines data from multiple message types into a single event payload.

### Glucose Event Structure

```javascript
glucose = {
  inSession: <boolean>,         // True if sensor session is active
  glucoseMessage: {             // From GlucoseRxMessage (0x31/0x4F)
    status: <int>,              // Transmitter status code
    sequence: <int>,            // Reading sequence number
    timestamp: <int>,           // Seconds since transmitter activation
    glucoseIsDisplayOnly: <boolean>,
    glucose: <int>,             // Glucose value in mg/dL
    state: <int>,               // Session/calibration state
    trend: <int>                // Rate of change (mg/dL per 10 min)
  },
  timeMessage: {                // From TransmitterTimeRxMessage (0x25)
    status: <int>,              // Transmitter status code
    currentTime: <int>,         // Current time (seconds since activation)
    sessionStartTime: <int>     // Session start (seconds since activation)
  },
  status: <int>,                // Transmitter status (from glucoseMessage)
  state: <int>,                 // Session state (from glucoseMessage)
  transmitterStartDate: <Date>, // Calculated transmitter activation date
  sessionStartDate: <Date>,     // Calculated session start date (or null)
  readDate: <Date>,             // Calculated glucose reading timestamp
  isDisplayOnly: <boolean>,     // From glucoseMessage.glucoseIsDisplayOnly
  filtered: <int>,              // Filtered raw value * 1000 (from SensorRxMessage)
  unfiltered: <int>,            // Unfiltered raw value * 1000 (from SensorRxMessage)
  glucose: <int>,               // Reliable glucose or null if unreliable
  trend: <int>,                 // From glucoseMessage.trend
  canBeCalibrated: <boolean>,   // True if calibration can be sent
  rssi: <int>                   // BLE signal strength
};
```

### Glucose Class Implementation

From `lib/glucose.js`:

```javascript
function Glucose(glucoseMessage, timeMessage, activationDate, sensorMessage, rssi) {
  this.inSession = timeMessage.sessionStartTime !== 0xffffffff;
  this.glucoseMessage = glucoseMessage;
  this.timeMessage = timeMessage;
  this.status = glucoseMessage.status;
  this.state = glucoseMessage.state;
  this.transmitterStartDate = activationDate;
  this.sessionStartDate = this.inSession
    ? new Date(activationDate.getTime() + timeMessage.sessionStartTime * 1000)
    : null;
  this.readDate = new Date(activationDate.getTime() + glucoseMessage.timestamp * 1000);
  this.isDisplayOnly = glucoseMessage.glucoseIsDisplayOnly;
  this.filtered = sensorMessage ? sensorMessage.filtered : null;
  this.unfiltered = sensorMessage ? sensorMessage.unfiltered : null;
  this.glucose = CalibrationState.hasReliableGlucose(this.state)
    ? glucoseMessage.glucose
    : null;
  this.trend = glucoseMessage.trend;
  this.canBeCalibrated = CalibrationState.canBeCalibrated(this.state);
  this.rssi = rssi;
}
```

## Transmitter Status Codes

The `status` field indicates transmitter hardware status.

| Code | Hex | Description |
|------|-----|-------------|
| 0 | `0x00` | OK - Normal operation |
| 129 | `0x81` | Low Battery |
| 131 | `0x83` | Expired - Transmitter past usable life |

### Usage Example

```javascript
transmitter.on('glucose', (glucose) => {
  switch (glucose.status) {
    case 0x00:
      console.log('Transmitter OK');
      break;
    case 0x81:
      console.log('WARNING: Low battery');
      break;
    case 0x83:
      console.log('ERROR: Transmitter expired');
      break;
  }
});
```

## Session/Calibration State Codes

The `state` field (`lib/calibration-state.js`) indicates sensor session and calibration status.

### Core States (0x00 - 0x13)

| Code | Hex | Name | Description |
|------|-----|------|-------------|
| 0 | `0x00` | None | No session state |
| 1 | `0x01` | Stopped | Session stopped |
| 2 | `0x02` | Warmup | Sensor warming up (2 hours) |
| 3 | `0x03` | Unused | Reserved |
| 4 | `0x04` | First Calibration | Waiting for first calibration BG |
| 5 | `0x05` | Second Calibration | Waiting for second calibration BG |
| 6 | `0x06` | OK | Normal operation, glucose reliable |
| 7 | `0x07` | Need Calibration | Calibration required |
| 8 | `0x08` | Calibration Error 1 | Calibration error type 1 |
| 9 | `0x09` | Calibration Error 0 | Calibration error type 0 |
| 10 | `0x0a` | Linearity Fit Failure | Calibration linearity fit failed |
| 11 | `0x0b` | Sensor Failed (Counts) | Sensor failed due to counts aberration |
| 12 | `0x0c` | Sensor Failed (Residual) | Sensor failed due to residual aberration |
| 13 | `0x0d` | Out of Cal (Outlier) | Out of calibration due to outlier |
| 14 | `0x0e` | Outlier Cal Request | Need calibration due to outlier |
| 15 | `0x0f` | Session Expired | 10-day session expired |
| 16 | `0x10` | Unrecoverable Error | Session failed, unrecoverable |
| 17 | `0x11` | Transmitter Error | Session failed, transmitter error |
| 18 | `0x12` | Temporary Failure | Temporary session failure (???) |
| 19 | `0x13` | Reserved | Reserved |

### Extended Calibration States (0x80 - 0x8f)

| Code | Hex | Name | Description |
|------|-----|------|-------------|
| 128 | `0x80` | Calibration Start | Calibration state start |
| 129 | `0x81` | Calibration Start Up | Calibration starting up |
| 130 | `0x82` | First of Two Cals | First of two calibrations needed |
| 131 | `0x83` | High Wedge First BG | High wedge display with first BG |
| 132 | `0x84` | Low Wedge First BG | Unused - Low wedge display with first BG |
| 133 | `0x85` | Second of Two Cals | Second of two calibrations needed |
| 134 | `0x86` | In Cal Transmitter | In calibration (transmitter mode) |
| 135 | `0x87` | In Cal Display | In calibration (display mode) |
| 136 | `0x88` | High Wedge Transmitter | High wedge (transmitter mode) |
| 137 | `0x89` | Low Wedge Transmitter | Low wedge (transmitter mode) |
| 138 | `0x8a` | Linearity Fit Transmitter | Linearity fit (transmitter mode) |
| 139 | `0x8b` | Out of Cal Outlier Tx | Out of cal due to outlier (Tx mode) |
| 140 | `0x8c` | High Wedge Display | High wedge (display mode) |
| 141 | `0x8d` | Low Wedge Display | Low wedge (display mode) |
| 142 | `0x8e` | Linearity Fit Display | Linearity fit (display mode) |
| 143 | `0x8f` | Session Not in Progress | No session active |

### CalibrationState Helper Functions

From `lib/calibration-state.js`:

```javascript
const CalibrationState = {
  stopped: 0x01,
  warmup: 0x02,
  needFirstInitialCalibration: 0x04,
  needSecondInitialCalibration: 0x05,
  ok: 0x06,
  needCalibration: 0x07,
  enterNewBG: 0x0a,
  sensorFailed: 0x0b,
  somethingElseCouldBeCalibrateAgain: 0x0e,
  questionMarks: 0x12,
};

// Returns true if glucose value is reliable
CalibrationState.hasReliableGlucose = state => 
  (state === CalibrationState.ok) || 
  (state === CalibrationState.needCalibration);

// Returns true if transmitter can accept calibration
CalibrationState.canBeCalibrated = state => 
  (state === CalibrationState.needFirstInitialCalibration) ||
  (state === CalibrationState.needSecondInitialCalibration) ||
  (state === CalibrationState.ok) ||
  (state === CalibrationState.needCalibration) ||
  (state === CalibrationState.enterNewBG);
```

## Battery Status Structure

### G5 BatteryStatusRxMessage

```javascript
batteryStatus = {
  status: <int>,        // Transmitter status code
  voltagea: <int>,      // Battery A voltage (V * 200)
  voltageb: <int>,      // Battery B voltage (V * 200)
  resist: <int>,        // Measured resistance (units unknown)
  runtime: <int>,       // Days since transmitter started
  temperature: <int>    // Temperature in Celsius
};
```

### G6/G6+ BatteryStatusRxMessage

```javascript
batteryStatus = {
  status: <int>,        // Transmitter status code
  voltagea: <int>,      // Battery A voltage (V * 200)
  voltageb: <int>,      // Battery B voltage (V * 200)
  runtime: <int>,       // Days since transmitter started
  temperature: <int>    // Temperature in Celsius
};
```

Note: G6+ format does not include the `resist` field.

### Voltage Conversion

To convert raw voltage to actual voltage:
```javascript
const actualVoltage = rawVoltage / 200;
// Example: voltagea = 313 → 1.565V
```

### Example Battery Status

From captured data:
```
23 00 3901 2a01 6b03 02 1e 2dbd
│  │  │    │    │    │  │  └── CRC
│  │  │    │    │    │  └── temperature: 30°C
│  │  │    │    │    └── runtime: 2 days
│  │  │    │    └── resist: 875
│  │  │    └── voltageb: 298 (1.49V)
│  │  └── voltagea: 313 (1.565V)
│  └── status: 0x00
└── opcode: 0x23
```

## Version Information Structure

The version information is assembled from three separate messages:

```javascript
firmwareData = {
  // From VersionRequestRx0Message (0x21)
  status: <int>,              // Transmitter status
  firmwareVersion: <string>,  // e.g., "2.18.2.88"
  btFirmwareVersion: <string>,// e.g., "2.18.2.88"
  hardwareRev: <int>,         // Hardware revision (e.g., 255)
  otherFirmwareVersion: <string>, // e.g., "0.49.69"
  asic: <int>,                // ASIC identifier
  
  // From VersionRequestRx1Message (0x4B)
  buildVersion: <int>,        // Build number
  inactiveDays: <int>,        // Days transmitter was inactive
  maxRuntimeDays: <int>,      // Maximum runtime in days (e.g., 112)
  maxInactiveDays: <int>,     // Shelf life in days
  
  // From VersionRequestRx2Message (0x53)
  typicalSensorDays: <int>,   // Typical sensor session length (e.g., 10)
  featureBits: <int>          // Feature flags
};
```

### Version String Format

Firmware versions are encoded as 4 bytes in dotted notation:
```
Bytes: 02 12 02 58
       │  │  │  │
       │  │  │  └── 88
       │  │  └── 2
       │  └── 18
       └── 2
       
Result: "2.18.2.88"
```

## Calibration Data Structure

### CalibrationDataRxMessage

**G5 Format (19 bytes):**
```javascript
calibrationData = {
  glucose: <int>,     // Last calibration glucose in mg/dL
  timestamp: <int>    // Calibration time (seconds since activation)
};
```

**G6 Format (20 bytes):**
```javascript
calibrationData = {
  glucose: <int>,     // Last calibration glucose in mg/dL
  timestamp: <int>    // Calibration time (seconds since activation)
};
```

### Calibration Data Event

```javascript
transmitter.on('calibrationData', (calibration) => {
  console.log(`Last cal: ${calibration.glucose} mg/dL at ${calibration.date}`);
});
```

## Backfill Data Structure

### BackfillParser Output

```javascript
backfillEntry = {
  time: <int>,        // Epoch time in milliseconds
  glucose: <int>,     // Glucose value in mg/dL
  type: <int>,        // Entry type
  trend: <int>        // Trend value (mg/dL per 10 min)
};

// Array of entries
backfillData = [backfillEntry, backfillEntry, ...];
```

### Backfill Event

```javascript
transmitter.on('backfillData', (backfillData) => {
  backfillData.forEach(entry => {
    console.log(`${new Date(entry.time)}: ${entry.glucose} mg/dL, trend: ${entry.trend}`);
  });
});
```

## Supported Commands

Commands passed to `getMessagesCallback`:

### StartSensor

```javascript
{
  type: 'StartSensor',
  date: <int>,              // Epoch time to start session
  sensorSerialCode: <string> // G6 sensor serial number (4 digits)
}
```

### StopSensor

```javascript
{
  type: 'StopSensor',
  date: <int>               // Epoch time to stop session
}
```

### CalibrateSensor

```javascript
{
  type: 'CalibrateSensor',
  date: <int>,              // Epoch time of glucose reading
  glucose: <int>            // Blood glucose value in mg/dL
}
```

### ResetTx

```javascript
{
  type: 'ResetTx'
}
```

### BatteryStatus

```javascript
{
  type: 'BatteryStatus'
}
```

### VersionRequest

```javascript
{
  type: 'VersionRequest'
}
```

### Backfill

```javascript
{
  type: 'Backfill',
  date: <int>,              // Start time for backfill (epoch ms)
  endDate: <int>            // Optional end time (defaults to now - 1 min)
}
```

## Time Calculations

All timestamps from the transmitter are in "Dexcom time" (seconds since transmitter activation).

### Converting to JavaScript Date

```javascript
// activationDate is calculated from TransmitterTimeRxMessage
const activationDate = new Date(Date.now() - timeMessage.currentTime * 1000);

// Convert any transmitter timestamp to Date
const readDate = new Date(activationDate.getTime() + timestamp * 1000);
```

### Session Start Detection

```javascript
// sessionStartTime is 0xFFFFFFFF when no session is active
const inSession = timeMessage.sessionStartTime !== 0xffffffff;

const sessionStartDate = inSession
  ? new Date(activationDate.getTime() + timeMessage.sessionStartTime * 1000)
  : null;
```

## Related Documentation

- [ble-protocol.md](ble-protocol.md) - Message formats and protocol details
- [README.md](README.md) - Library overview and architecture
