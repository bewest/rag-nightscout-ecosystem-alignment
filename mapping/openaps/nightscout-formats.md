# OpenAPS: Nightscout Data Formats

**Source**: `externals/openaps`  
**Verified**: 2026-01-20

## Timestamp Conversion

Per `openaps/vendors/dexcom.py:446-451`:

```python
def adjust_nightscout_dates(records):
    for item in records:
        dt = item['display_time']
        # Millisecond epoch
        date = (time.mktime(dt.timetuple()) * 1000) + (dt.microsecond / 1000.0)
        item.update(dateString=item['display_time'], date=date)
```

**Key Fields:**
- `date` - Millisecond epoch timestamp
- `dateString` - ISO format string

## SGV (Sensor Glucose Value) Format

Per `openaps/vendors/dexcom.py:455-562` (`oref0_glucose` class):

```json
{
  "sgv": 120,
  "direction": "Flat",
  "filtered": 123456,
  "unfiltered": 123400,
  "rssi": -80,
  "dateString": "2026-01-20T12:00:00",
  "date": 1737374400000,
  "type": "sgv",
  "device": "openaps://hostname/device_name"
}
```

### Direction Mapping

Per `openaps/vendors/dexcom.py:572-604`:

| Trend | Direction |
|-------|-----------|
| DoubleUp | "DoubleUp" |
| SingleUp | "SingleUp" |
| FortyFiveUp | "FortyFiveUp" |
| Flat | "Flat" |
| FortyFiveDown | "FortyFiveDown" |
| SingleDown | "SingleDown" |
| DoubleDown | "DoubleDown" |

## Calibration Format

Per `openaps/vendors/dexcom.py:825-835`:

```json
{
  "type": "cal",
  "device": "openaps://hostname/device_name",
  "dateString": "2026-01-20T12:00:00",
  "date": 1737374400000,
  "slope": 1000,
  "intercept": 10000,
  "scale": 1
}
```

## Device Identifier

Per `openaps/vendors/dexcom.py:534`:

```python
device = "openaps://{hostname}/{device_name}"
```

Format: `openaps://<machine-hostname>/<device-reference>`

## oref0 Markers

Commands and data tagged with `[#oref0]` are specifically formatted for oref0 algorithm consumption:

**Dexcom Commands:**
- `oref0_glucose` - Merged glucose + raw data
- `nightscout_calibrations` - Formatted calibrations

**Medtronic Commands (per `vendors/medtronic.py`):**
- `read_temp_basal` [#oref0]
- `read_settings` [#oref0]
- `read_carb_ratios` [#oref0]
- `read_selected_basal_profile` [#oref0]
- `read_clock` [#oref0]
- `battery` [#oref0]
- `bg_targets`, `insulin_sensitivities` [#oref0]

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-OA-001 | Must format timestamps as both epoch ms and ISO string | `dexcom.py:446-451` |
| REQ-OA-002 | Must include device identifier in uploads | `dexcom.py:534` |
| REQ-OA-003 | Must map CGM trend to Nightscout direction | `dexcom.py:572-604` |
| REQ-OA-004 | Must merge glucose with raw sensor data | `dexcom.py:455-562` |
