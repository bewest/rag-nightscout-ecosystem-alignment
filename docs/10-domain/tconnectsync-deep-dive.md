# tconnectsync Deep Dive

> **Source**: `externals/tconnectsync/`  
> **Last Updated**: 2026-01-29  
> **Version**: v2.3.4

## Overview

tconnectsync is a Python tool that synchronizes data from Tandem t:connect cloud to Nightscout. It bridges the Tandem pump ecosystem (t:slim X2, Control-IQ) with the open-source diabetes data aggregation platform.

| Aspect | Details |
|--------|---------|
| **Language** | Python 3.8+ |
| **Author** | jwoglom |
| **License** | MIT |
| **Pump Support** | Tandem t:slim X2 with Control-IQ |
| **CGM Support** | Dexcom G6/G7 (via pump) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      tconnectsync                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │     API     │    │   Domain    │    │    Sync     │     │
│  │  (t:connect)│    │  (models)   │    │ (Nightscout)│     │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘     │
│         │                  │                  │             │
│         ▼                  ▼                  ▼             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ controliq   │    │   Bolus     │    │ Treatments  │     │
│  │ tandemsource│    │ TherapyEvent│    │  Entries    │     │
│  │ android     │    │   Profile   │    │  Profiles   │     │
│  │ ws2/webui   │    │   Device    │    │ DeviceStatus│     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │                                       │
         ▼                                       ▼
    t:connect Cloud                         Nightscout
```

---

## Directory Structure

```
tconnectsync/
├── api/              # t:connect API clients
│   ├── tandemsource.py   # OIDC OAuth2 authentication
│   ├── controliq.py      # Control-IQ therapy timeline
│   ├── android.py        # Android app cloud API
│   ├── ws2.py            # Historical data (CSV/JSONP)
│   ├── webui.py          # Web UI scraping
│   └── common.py         # Shared utilities
├── domain/           # Data models
│   ├── bolus.py          # Bolus events
│   ├── therapy_event.py  # Therapy event base class
│   └── device_settings.py # Device/Profile models
├── sync/             # Nightscout sync logic
│   ├── process.py        # Event processor orchestrator
│   ├── process_bolus.py  # Bolus → treatment
│   ├── process_basal.py  # Basal → temp basal
│   └── ...               # Other processors
├── parser/           # Data parsing
├── nightscout.py     # Nightscout API client
└── main.py           # CLI entry point
```

---

## API Module

### Authentication Methods

| Method | File | Flow |
|--------|------|------|
| **OIDC/OAuth2** | `tandemsource.py` | PKCE flow via Tandem services, JWT validation |
| **Android Credentials** | `android.py` | Base64 embedded credentials, password grant |
| **Web Form Auth** | `controliq.py` | Form login, extracts UserGUID cookie |

### Key API Files

| File | Lines | Purpose |
|------|-------|---------|
| `tandemsource.py` | 455 | OIDC OAuth2 with US/EU region support |
| `controliq.py` | 206 | Control-IQ therapy timeline endpoints |
| `android.py` | 175 | Android app cloud API for settings |
| `ws2.py` | 174 | Historical data CSV/JSONP export |
| `webui.py` | 296 | Web UI scraping for device settings |
| `common.py` | 138 | Shared session/error handling |

### t:connect API Endpoints

**Control-IQ APIs**:
```
/tconnect/controliq/api/therapytimeline/users/{userGuid}?startDate=X&endDate=Y
/tconnect/controliq/api/summary/users/{userGuid}?startDate=X&endDate=Y
/tconnect/controliq/api/pumpfeatures/users/{userGuid}
```

**Therapy Events**:
```
/tconnect/therapyevents/api/TherapyEvents/{startDate}/{endDate}/false?userId={userGuid}
```

**Cloud Settings (Android)**:
```
/cloud/usersettings/api/therapythresholds?userId={userId}
/cloud/usersettings/api/UserProfile?userId={userId}
/cloud/account/patient_info
/cloud/upload/getlasteventuploaded?sn={pump_serial}
```

**Historical Data (WS2)**:
```
/therapytimeline2csv/{userGuid}/{startDate}/{endDate}?format=csv
/basalsuspension/{userGuid}/{startDate}/{endDate}/{filterbasal}
/basaliqtech/{userGuid}/{startDate}/{endDate}
```

---

## Domain Models

### Bolus

**File**: `domain/bolus.py`

```python
class Bolus:
    description: str
    complete: bool
    request_time: datetime
    completion_time: datetime
    insulin: float
    requested_insulin: float
    carbs: int
    bg: int
    user_override: bool
    extended_bolus: bool
    bolex_completion_time: datetime
    bolex_start_time: datetime
```

### TherapyEvent Hierarchy

**File**: `domain/therapy_event.py`

| Class | Purpose | NS Mapping |
|-------|---------|------------|
| `TherapyEvent` | Base class | - |
| `CGMTherapyEvent` | CGM glucose | `entries` (type: `sgv`) |
| `BGTherapyEvent` | Manual BG | `entries` or treatment |
| `BolusTherapyEvent` | Bolus | `Combo Bolus` treatment |
| `BasalTherapyEvent` | Basal change | `Temp Basal` treatment |

### Profile

**File**: `domain/device_settings.py`

```python
class Profile:
    segments: List[ProfileSegment]

class ProfileSegment:
    display_time: str
    time: str
    basal_rate: float
    correction_factor: int  # ISF
    carb_ratio: int         # CR
    target_bg_mgdl: int
```

---

## Sync Module

### Event Processing Pipeline

1. Fetch pump events from t:connect API for time range
2. Classify events by type, route to specialized processors
3. Transform events to Nightscout format
4. Upload via REST API

### Supported Treatment Types

| Treatment Type | Processor | NS eventType |
|----------------|-----------|--------------|
| **Combo Bolus** | `process_bolus.py` | `Combo Bolus` |
| **Temp Basal** | `process_basal.py` | `Temp Basal` |
| **Basal Suspension** | `process_basal_suspension.py` | `Basal Suspension` |
| **Basal Resume** | `process_basal_resume.py` | `Basal Resume` |
| **Site Change** | `process_cartridge.py` | `Site Change` |
| **Pump Alarm** | `process_alarm.py` | `Announcement` |
| **CGM Alert** | `process_cgm_alert.py` | `Announcement` |
| **Sensor Start/Stop** | `process_cgm_start_join_stop.py` | `Sensor Start` |
| **Exercise** | `process_user_mode.py` | `Exercise` |
| **Sleep** | `process_user_mode.py` | `Sleep` |

### Nightscout API Client

**File**: `nightscout.py`

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `api/v1/{entity}` | Create entries/treatments |
| PUT | `api/v1/{entity}` | Update entries |
| DELETE | `api/v1/{entity}/{id}` | Remove entries |

**Authentication**: SHA1-hashed `api-secret` header

---

## Nightscout Field Mappings

### Bolus → Treatment

| tconnectsync Field | Nightscout Field |
|--------------------|------------------|
| `insulin` | `insulin` |
| `carbs` | `carbs` |
| `bg` | `glucose` |
| `request_time` | `created_at` |
| `description` | `notes` |
| - | `eventType`: `Combo Bolus` |
| - | `enteredBy`: `tconnectsync` |

### Basal → Temp Basal

| tconnectsync Field | Nightscout Field |
|--------------------|------------------|
| `rate` | `rate` (U/hr) |
| `duration` | `duration` (minutes) |
| `reason` | `notes` |
| - | `eventType`: `Temp Basal` |

### CGM → Entry

| tconnectsync Field | Nightscout Field |
|--------------------|------------------|
| `glucose` | `sgv` |
| `timestamp` | `date` (epoch ms) |
| - | `type`: `sgv` |
| - | `device`: `tconnectsync` |

### Profile → Profile

| tconnectsync Field | Nightscout Field |
|--------------------|------------------|
| `basal_rate` | `basal[].value` |
| `time` | `basal[].time` |
| `carb_ratio` | `carbratio[].value` |
| `correction_factor` | `sens[].value` |
| `target_bg_mgdl` | `target_low`, `target_high` |

---

## Control-IQ Data

tconnectsync extracts Control-IQ algorithm data:

| Data Type | Source | Description |
|-----------|--------|-------------|
| **Therapy Timeline** | controliq API | Basal, bolus, glucose events |
| **Pump Features** | controliq API | Control-IQ mode settings |
| **Basal IQ Tech** | ws2 API | Predictive low glucose suspend |
| **Basal Suspension** | ws2 API | Suspension events |

---

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `TCONNECT_EMAIL` | t:connect account email |
| `TCONNECT_PASSWORD` | t:connect account password |
| `NS_URL` | Nightscout URL |
| `NS_SECRET` | Nightscout API secret |

### CLI Usage

```bash
# Sync last 24 hours
python -m tconnectsync

# Sync specific date range
python -m tconnectsync --start 2026-01-01 --end 2026-01-28

# Dry run (no upload)
python -m tconnectsync --pretend
```

---

## Gaps Identified

### GAP-TCONNECT-001: No API v3 Support

**Description**: tconnectsync uses Nightscout API v1 only. Does not leverage v3 deduplication or identifier fields.

**Impact**:
- No automatic deduplication on Nightscout side
- Re-syncs may create duplicate treatments
- Missing `identifier` field for sync tracking

**Remediation**: Add v3 API support with proper identifiers.

### GAP-TCONNECT-002: Limited Control-IQ Algorithm Data

**Description**: While pump events are synced, detailed Control-IQ algorithm decisions (predicted glucose, auto-basal adjustments) are not extracted.

**Impact**:
- Cannot visualize Control-IQ decision-making in Nightscout
- Limited debugging of algorithm behavior

**Remediation**: Extract and upload to devicestatus if available.

### GAP-TCONNECT-003: No Real-Time Sync

**Description**: tconnectsync is batch-based; requires manual or cron execution. No push/webhook from t:connect.

**Impact**:
- Delay between pump events and Nightscout visibility
- Not suitable for real-time monitoring

**Remediation**: Document as limitation; t:connect API doesn't support push.

---

## Source File Reference

### API Layer
- `externals/tconnectsync/tconnectsync/api/tandemsource.py` (455 lines) - OIDC auth
- `externals/tconnectsync/tconnectsync/api/controliq.py` (206 lines) - Control-IQ API
- `externals/tconnectsync/tconnectsync/api/android.py` (175 lines) - Android cloud API
- `externals/tconnectsync/tconnectsync/api/ws2.py` (174 lines) - Historical data

### Domain Models
- `externals/tconnectsync/tconnectsync/domain/bolus.py` - Bolus model
- `externals/tconnectsync/tconnectsync/domain/therapy_event.py` - Event hierarchy
- `externals/tconnectsync/tconnectsync/domain/device_settings.py` - Device/Profile

### Sync Layer
- `externals/tconnectsync/tconnectsync/sync/process.py` - Event orchestrator
- `externals/tconnectsync/tconnectsync/sync/process_bolus.py` - Bolus processor
- `externals/tconnectsync/tconnectsync/sync/process_basal.py` - Basal processor
- `externals/tconnectsync/tconnectsync/nightscout.py` - NS API client

---

## Summary

| Aspect | Details |
|--------|---------|
| **Purpose** | Sync Tandem t:connect → Nightscout |
| **Data Flow** | Batch pull from cloud, push to NS v1 API |
| **Treatments** | 10+ types (bolus, basal, site change, alerts) |
| **Authentication** | OIDC/OAuth2, Android credentials, web form |
| **Limitations** | No v3, no real-time, batch only |

tconnectsync is a well-structured bridge for Tandem pump users who want their data in Nightscout but lack native integration like AAPS has.
