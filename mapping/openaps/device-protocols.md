# OpenAPS: Device Communication Protocols

**Source**: `externals/openaps`  
**Verified**: 2026-01-20

## Medtronic Pump Communication

Per `openaps/vendors/medtronic.py`:

### Interface

- USB stick communication via `decocare` library
- Session-based protocol with token caching

### Session Management

Per `medtronic.py:76-87`:

```python
# Token cached in JSON file
session_token = load_from_cache()
if not session_token:
    session_token = establish_session()
    save_to_cache(session_token)
```

### Supported Record Types

| Record Type | Description |
|-------------|-------------|
| `EGV_DATA` | CGM glucose values |
| `SENSOR_DATA` | Raw sensor readings |
| `CAL_SET` | Calibration data |
| `INSERTION_TIME` | Sensor insertion time |
| `METER_DATA` | Blood glucose meter values |
| `USER_EVENT_DATA` | User-entered events |

## Dexcom Receiver Communication

Per `openaps/vendors/dexcom.py`:

### Interface

- USB serial port communication
- Port scanning at connection (`dexcom.py:36`)

### Supported Models

Per `dexcom.py:41-42`:
- Dexcom G4
- Dexcom G5

### Capabilities

| Feature | Support |
|---------|---------|
| Read glucose history | ✅ |
| Read calibrations | ✅ |
| Read sensor data | ✅ |
| Read battery state | ✅ |
| Write commands | ❌ |

## Data Merging

Per `dexcom.py:455-562` (`oref0_glucose` class):

CGM and raw sensor data are merged with configurable threshold:

```python
# Default: 100 seconds
threshold = 100

# Merge glucose and raw data
for glucose in glucose_records:
    raw = find_matching_raw(glucose.timestamp, threshold)
    if raw:
        glucose.update(filtered=raw.filtered, unfiltered=raw.unfiltered, rssi=raw.rssi)
```

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-OA-DEV-001 | Must cache pump session tokens | `medtronic.py:76-87` |
| REQ-OA-DEV-002 | Must scan USB ports for Dexcom | `dexcom.py:36` |
| REQ-OA-DEV-003 | Must merge CGM with raw data within threshold | `dexcom.py:455-562` |
