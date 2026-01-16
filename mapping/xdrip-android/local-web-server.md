# xDrip+ Local Web Server

This document describes xDrip+'s unique local web server feature that emulates Nightscout API endpoints, enabling inter-app communication without cloud connectivity.

## Overview

xDrip+ can operate as a **local Nightscout server** on ports 17580 (HTTP) and 17581 (HTTPS), providing API-compatible endpoints for watchfaces, automation apps, and other diabetes management tools.

This is **unique to xDrip+ Android** and not available in xDrip4iOS.

## Source Files

| File | Purpose | Lines |
|------|---------|-------|
| `webservices/XdripWebService.java` | Main web server | ~200 |
| `webservices/RouteFinder.java` | URL routing | ~50 |
| `webservices/WebServiceSgv.java` | SGV endpoint | ~150 |
| `webservices/WebServiceTreatments.java` | Treatments endpoint | ~110 |
| `webservices/WebServicePebble.java` | Pebble endpoint | ~100 |
| `webservices/WebServiceStatus.java` | Status endpoint | ~50 |
| `webservices/WebServiceTasker.java` | Tasker commands | ~80 |
| `webservices/WebServiceSteps.java` | Step counter input | ~40 |
| `webservices/WebServiceHeart.java` | Heart rate input | ~40 |
| `webservices/WebServiceSync.java` | Sync operations | ~60 |

## Server Configuration

### Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 17580 | HTTP | Primary local API |
| 17581 | HTTPS | SSL with self-signed certificate |

### Settings

- **Enable Web Service**: Settings > Inter-App Settings > Web Service
- **Open Web Service**: Allow external network access (not just localhost)
- **xDrip Web Service Secret**: Password for network authentication

## Endpoint Reference

### `/sgv.json`

Emulates Nightscout's `/api/v1/entries/sgv.json` endpoint.

**URL**: `http://127.0.0.1:17580/sgv.json`

**Method**: GET

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `count` | int | Number of entries (default: 24, max: 100) |
| `steps` | int | Set current step count (returns `steps_result`) |
| `heart` | int | Set current heart rate BPM (returns `heart_result`) |
| `tasker` | string | Execute tasker command (returns `tasker_result`) |
| `brief_mode` | Y/N | Reduce response size |
| `no_empty` | Y/N | Return "" instead of "[]" if empty |
| `all_data` | Y/N | Include previous sensor session |
| `sensor` | Y/N | Include sensor age info |
| `collector` | Y/N | Include collector alert messages |

**Response Format**:

```json
[
    {
        "date": 1705421234567,
        "dateString": "2026-01-16T12:00:34.567Z",
        "sgv": 120,
        "delta": 2.5,
        "direction": "Flat",
        "noise": 1,
        "units_hint": "mgdl"
    },
    {
        "date": 1705420934567,
        "sgv": 118,
        "delta": 1.0,
        "direction": "Flat"
    }
]
```

**First record extensions**:

```json
{
    "units_hint": "mgdl",      // or "mmol"
    "steps_result": 200,       // HTTP status if steps set
    "heart_result": 200,       // HTTP status if heart set
    "tasker_result": "OK",     // Tasker command result
    "sensor": {
        "age": 345600000,      // Sensor age in ms
        "start": 1705075634567 // Sensor start time
    },
    "collector": "Low battery" // Alert message if any
}
```

### `/treatments.json`

Emulates Nightscout's `/api/v1/treatments.json` endpoint.

**URL**: `http://127.0.0.1:17580/treatments.json`

**Method**: GET

**Query Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `count` | int | Number of treatments (default: 24, max: 100) |
| `no_empty` | Y/N | Return "" instead of "[]" if empty |

**Response Format**:

```json
[
    {
        "_id": "uuid-string",
        "created_at": 1705421234567,
        "eventType": "Meal Bolus",
        "enteredBy": "xdrip",
        "notes": "Lunch",
        "carbs": 45,
        "insulin": 5.0
    }
]
```

### `/pebble`

Provides Pebble watchface-compatible endpoint.

**URL**: `http://127.0.0.1:17580/pebble`

**Response Format**:

```json
{
    "bgs": [
        {
            "sgv": "120",
            "trend": 4,
            "direction": "Flat",
            "datetime": 1705421234567,
            "bgdelta": "+2"
        }
    ],
    "cals": [
        {
            "slope": 850.5,
            "intercept": 32000,
            "scale": 1
        }
    ]
}
```

### `/status.json`

Provides basic status information.

**URL**: `http://127.0.0.1:17580/status.json`

**Response Format**:

```json
{
    "thresholds": {
        "bgHigh": 180,
        "bgLow": 70
    }
}
```

Values are in user's preferred units (mg/dL or mmol/L).

### `/tasker/*`

Tasker automation endpoint.

**URL**: `http://127.0.0.1:17580/tasker/{command}`

**Commands**:

| Command | Description |
|---------|-------------|
| `SNOOZE` | Snooze active alert (sends to followers) |
| `OSNOOZE` | Opportunistic snooze (silent if no alert) |

**Response**: Text status of command execution

### `/steps/set/{value}`

Set step counter data.

**URL**: `http://127.0.0.1:17580/steps/set/1234`

**Note**: Value should be cumulative step count, not incremental.

### `/heart/set/{bpm}/{accuracy}`

Set heart rate data.

**URL**: `http://127.0.0.1:17580/heart/set/72/1`

**Parameters**:
- First: BPM value
- Second: Accuracy (1 = normal)

## Route Configuration

```java
public class RouteFinder {

    private static final ArrayList<RouteInfo> routes = new ArrayList<>();

    static {
        // Standard routes
        routes.add(new RouteInfo("sgv.json", "WebServiceSgv"));
        routes.add(new RouteInfo("pebble", "WebServicePebble"));
        routes.add(new RouteInfo("status.json", "WebServiceStatus"));
        routes.add(new RouteInfo("tasker", "WebServiceTasker"));

        // API v1 compatible routes
        routes.add(new RouteInfo("api/v1/entries/sgv.json", "WebServiceSgv"));
        routes.add(new RouteInfo("api/v1/treatments.json", "WebServiceTreatments"));

        // Treatment routes
        routes.add(new RouteInfo("treatments.json", "WebServiceTreatments"));

        // Input routes
        routes.add(new RouteInfo("steps", "WebServiceSteps"));
        routes.add(new RouteInfo("heart", "WebServiceHeart"));

        // Sync routes
        routes.add(new RouteInfo("sync", "WebServiceSync"));

        // Libre connection code
        routes.add(new RouteInfo("libre2cc", "WebLibre2ConnectCode"));
    }
}
```

## Authentication

### Loopback Access

Requests from `127.0.0.1` require **no authentication**.

### Network Access

When "Open Web Service" is enabled:

1. Set `xDrip Web Service Secret` to a password
2. Client must include `api-secret` header with SHA1 hash

```
api-secret: 915858afa2278f25527f192038108346164b47f2
```

(SHA1 of password "Abc")

### Mutual Authentication

If client provides `api-secret` header but xDrip secret is not set, the request is **rejected**. This ensures clients connect to the correct xDrip instance.

## Implementation

### Web Server Startup

```java
public class XdripWebService extends NanoHTTPD {

    private static final int HTTP_PORT = 17580;
    private static final int HTTPS_PORT = 17581;

    public XdripWebService() {
        super(HTTP_PORT);
    }

    @Override
    public Response serve(IHTTPSession session) {
        String uri = session.getUri();
        String query = session.getQueryParameterString();

        // Check authentication for non-local requests
        if (!isLocalRequest(session) && requiresAuth()) {
            String clientSecret = session.getHeaders().get("api-secret");
            if (!validateSecret(clientSecret)) {
                return newFixedLengthResponse(
                    Response.Status.FORBIDDEN,
                    "text/plain",
                    "Authentication required"
                );
            }
        }

        // Route to appropriate handler
        BaseWebService handler = RouteFinder.getHandler(uri);
        if (handler != null) {
            WebResponse response = handler.request(query);
            return newFixedLengthResponse(
                Response.Status.OK,
                "application/json",
                response.getContent()
            );
        }

        return newFixedLengthResponse(
            Response.Status.NOT_FOUND,
            "text/plain",
            "Endpoint not found"
        );
    }
}
```

### SGV Handler

```java
public class WebServiceSgv extends BaseWebService {

    private static final String TAG = "WebServiceSgv";

    public WebResponse request(String query) {
        final Map<String, String> params = getQueryParameters(query);
        int count = 24;

        if (params.containsKey("count")) {
            count = Math.min(Integer.parseInt(params.get("count")), 100);
        }

        // Get BG readings
        List<BgReading> readings = BgReading.latest(count);

        JSONArray reply = new JSONArray();
        boolean first = true;

        for (BgReading bg : readings) {
            JSONObject item = new JSONObject();

            item.put("date", bg.timestamp);
            item.put("dateString", formatDate(bg.timestamp));
            item.put("sgv", (int) bg.calculated_value);
            item.put("direction", bg.slopeName());

            if (first) {
                // Add hints to first record
                item.put("units_hint", Pref.getBooleanDefaultFalse("units_mmol")
                    ? "mmol" : "mgdl");

                // Handle step/heart/tasker inputs
                processInputs(params, item);
                first = false;
            }

            reply.put(item);
        }

        if (params.containsKey("no_empty") && reply.length() == 0) {
            return new WebResponse("");
        }

        return new WebResponse(reply.toString());
    }
}
```

## Use Cases

### Pebble Watchface

Configure watchface to use:
```
http://127.0.0.1:17580/pebble
```

### Garmin Watch

Some Garmin apps can connect to local endpoints.

### Tasker Automation

```
URL: http://127.0.0.1:17580/tasker/SNOOZE
Method: GET
```

### Custom Integrations

Third-party apps can:
1. Poll `/sgv.json` for current glucose
2. Send step/heart data via query parameters
3. Trigger actions via `/tasker/` endpoints

### AAPS Integration

While AAPS typically uses broadcasts, the web server provides an alternative data path.

## Security Considerations

1. **Loopback only by default**: External access must be explicitly enabled
2. **Secret required for network**: SHA1-hashed password authentication
3. **Mutual validation**: Both sides can validate connection
4. **Event logging**: Rejected connections are logged

## Comparison with Nightscout

| Aspect | xDrip+ Local | Nightscout |
|--------|--------------|------------|
| **Latency** | Instant (local) | Network dependent |
| **Availability** | No internet required | Requires internet |
| **Auth** | SHA1 header | SHA1 header or token |
| **Write** | Limited (steps, heart) | Full CRUD |
| **Treatments** | Read-only | Read/Write |
| **Profiles** | Not available | Full support |

---

## Code Citation

```
xdrip-android:com/eveningoutpost/dexdrip/webservices/RouteFinder.java#L36-L40
xdrip-android:com/eveningoutpost/dexdrip/webservices/WebServiceSgv.java
xdrip-android:com/eveningoutpost/dexdrip/webservices/WebServiceTreatments.java
```
