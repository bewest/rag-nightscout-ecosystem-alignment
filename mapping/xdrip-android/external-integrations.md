# xDrip+ External Integrations

This document describes xDrip+'s integrations with external services beyond Nightscout, including Tidepool, InfluxDB, MongoDB, and AAPS.

## Overview

xDrip+ supports multiple upload destinations simultaneously via the UploaderQueue circuit system:

| Destination | Circuit Bit | Description |
|-------------|-------------|-------------|
| Nightscout REST | `1 << 1` | Nightscout REST API |
| MongoDB Direct | `1` | Direct MongoDB connection |
| InfluxDB REST | `1 << 3` | InfluxDB line protocol |
| Watch Wear API | `1 << 4` | Android Wear sync |
| Tidepool | Separate | Tidepool platform |

## Tidepool Integration

### Source Files

| File | Purpose |
|------|---------|
| `tidepool/TidepoolUploader.java` | Main uploader |
| `tidepool/TidepoolEntry.java` | Entry point |
| `tidepool/TidepoolStatus.java` | Status tracking |
| `tidepool/Session.java` | Session management |
| `tidepool/EBasal.java` | Basal record |
| `tidepool/EBolus.java` | Bolus record |
| `tidepool/EBloodGlucose.java` | Finger stick BG |
| `tidepool/ESensorGlucose.java` | CGM glucose |
| `tidepool/EWizard.java` | Bolus wizard record |

### Authentication

```java
public class TidepoolUploader {

    private static final String TIDEPOOL_URL = "https://api.tidepool.org";

    public boolean login(String username, String password) {
        MAuthRequest request = new MAuthRequest(username, password);

        Response<MAuthReply> response = service.login(
            "Basic " + Base64.encodeToString(
                (username + ":" + password).getBytes(), Base64.NO_WRAP
            )
        ).execute();

        if (response.isSuccessful()) {
            session.token = response.headers().get("x-tidepool-session-token");
            session.userId = response.body().userid;
            return true;
        }
        return false;
    }
}
```

### Data Upload

```java
// Dataset management
public interface TidepoolService {

    @POST("v1/users/{userId}/datasets")
    Call<MDatasetReply> createDataset(
        @Header("x-tidepool-session-token") String token,
        @Path("userId") String userId,
        @Body MOpenDatasetRequest request
    );

    @POST("v1/datasets/{datasetId}/data")
    Call<ResponseBody> uploadData(
        @Header("x-tidepool-session-token") String token,
        @Path("datasetId") String datasetId,
        @Body RequestBody data
    );

    @PUT("v1/datasets/{datasetId}")
    Call<ResponseBody> closeDataset(
        @Header("x-tidepool-session-token") String token,
        @Path("datasetId") String datasetId,
        @Body MCloseDatasetRequest request
    );
}
```

### Tidepool Data Models

#### Sensor Glucose (CGM)

```java
public class ESensorGlucose extends BaseElement {

    public String type = "cbg";  // Continuous blood glucose
    public long time;            // ISO 8601
    public String deviceId;
    public String uploadId;
    public double value;         // mmol/L
    public String units = "mmol/L";

    public static ESensorGlucose fromBgReading(BgReading bg) {
        ESensorGlucose e = new ESensorGlucose();
        e.time = bg.timestamp;
        e.value = bg.calculated_value / 18.0;  // Convert to mmol/L
        e.deviceId = getDeviceId();
        return e;
    }
}
```

#### Bolus

```java
public class EBolus extends BaseElement {

    public String type = "bolus";
    public String subType;       // "normal", "extended", "dual/square"
    public long time;
    public double normal;        // Units delivered
    public double extended;      // Extended portion
    public long duration;        // Extended duration (ms)
    public String deviceId;

    public static EBolus fromTreatment(Treatments t) {
        EBolus e = new EBolus();
        e.time = t.timestamp;
        e.subType = "normal";
        e.normal = t.insulin;
        return e;
    }
}
```

#### Blood Glucose (Finger Stick)

```java
public class EBloodGlucose extends BaseElement {

    public String type = "smbg";  // Self-monitored blood glucose
    public long time;
    public double value;          // mmol/L
    public String units = "mmol/L";
    public String subType = "manual";

    public static EBloodGlucose fromBloodTest(BloodTest bt) {
        EBloodGlucose e = new EBloodGlucose();
        e.time = bt.timestamp;
        e.value = bt.mgdl / 18.0;
        return e;
    }
}
```

## InfluxDB Integration

### Source File

`influxdb/InfluxDBUploader.java`

### Configuration

```java
public class InfluxDBUploader {

    private String influxUrl;       // http://localhost:8086
    private String influxDatabase;  // xdrip
    private String influxUser;
    private String influxPassword;

    public boolean upload(BgReading bg) {
        // Line protocol format
        String line = String.format(
            "glucose,device=%s value=%f %d",
            getDeviceId(),
            bg.calculated_value,
            bg.timestamp * 1000000  // Nanoseconds
        );

        RequestBody body = RequestBody.create(
            MediaType.parse("text/plain"),
            line
        );

        Response response = httpClient.newCall(
            new Request.Builder()
                .url(influxUrl + "/write?db=" + influxDatabase)
                .addHeader("Authorization", getAuth())
                .post(body)
                .build()
        ).execute();

        return response.isSuccessful();
    }
}
```

### Line Protocol Format

```
# Glucose readings
glucose,device=xDrip-Pixel7,sensor=G6 value=120.0,raw=95000.0 1705421234567000000

# Treatments
treatment,type=bolus,device=xDrip insulin=5.0 1705421234567000000
treatment,type=carbs,device=xDrip carbs=45.0 1705421234567000000

# Calibrations
calibration,device=xDrip slope=850.5,intercept=32000.0 1705421234567000000
```

## MongoDB Direct

### Configuration

xDrip+ can connect directly to MongoDB (bypassing Nightscout REST):

```java
public class NightscoutUploader {

    private MongoClient mongoClient;
    private DB mongoDb;
    private DBCollection entriesCollection;
    private DBCollection treatmentsCollection;

    public boolean initMongo(String mongoUri) {
        try {
            MongoClientURI uri = new MongoClientURI(mongoUri);
            mongoClient = new MongoClient(uri);
            mongoDb = mongoClient.getDB(uri.getDatabase());

            entriesCollection = mongoDb.getCollection("entries");
            treatmentsCollection = mongoDb.getCollection("treatments");

            return true;
        } catch (Exception e) {
            return false;
        }
    }

    public boolean doMongoUpload(List<BgReading> readings) {
        for (BgReading bg : readings) {
            BasicDBObject doc = new BasicDBObject();
            doc.put("device", getDeviceName());
            doc.put("date", bg.timestamp);
            doc.put("dateString", formatDate(bg.timestamp));
            doc.put("sgv", (int) bg.calculated_value);
            doc.put("direction", bg.slopeName());
            doc.put("type", "sgv");

            WriteResult result = entriesCollection.insert(doc, WriteConcern.UNACKNOWLEDGED);
        }
        return true;
    }
}
```

### MongoDB URI Format

```
mongodb://username:password@hostname:27017/nightscout
```

## AAPS Integration

### Device Status Handler

```java
public class AAPSStatusHandler {

    private static final Gson gson = new GsonBuilder().create();
    private static volatile NSDeviceStatus last;

    public static void processDeviceStatus(String json) {
        synchronized (AAPSStatusHandler.class) {
            try {
                last = gson.fromJson(json, NSDeviceStatus.class);

                if (last != null) {
                    // Store for later retrieval
                    store.set(json);

                    // Update pump status display
                    val pump = last.getPump();
                    if (pump != null) {
                        val reservoir = pump.getReservoir();
                        if (reservoir != null) {
                            PumpStatus.setReservoir(reservoir);
                        }

                        val battery = pump.getBattery();
                        if (battery != null && battery.getPercent() != null) {
                            PumpStatus.setBattery(battery.getPercent());
                        }
                    }
                    PumpStatus.syncUpdate();
                }
            } catch (Exception e) {
                Log.e(TAG, "Error processing device status: " + e);
            }
        }
    }
}
```

### NSDeviceStatus Model

xDrip+ uses the AAPS NSSDK models:

```java
// From info.nightscout.sdk.localmodel.devicestatus
public class NSDeviceStatus {

    private String device;
    private Long created_at;
    private Pump pump;
    private Loop loop;
    private OpenAps openAps;
    private Uploader uploader;

    public class Pump {
        private Long clock;
        private Double reservoir;
        private PumpBattery battery;
        private PumpStatus status;
    }

    public class Loop {
        private Long timestamp;
        private String iob;
        private String cob;
        private Predicted predicted;
    }
}
```

## Upload Queue Integration

All external uploads go through the unified UploaderQueue:

```java
public static void processQueue() {
    List<UploaderQueue> pending = UploaderQueue.getPending();

    for (UploaderQueue entry : pending) {
        long circuits = entry.bitfield_wanted & ~entry.bitfield_complete;

        // Nightscout REST
        if ((circuits & NIGHTSCOUT_RESTAPI) != 0) {
            if (uploadToNightscout(entry)) {
                entry.bitfield_complete |= NIGHTSCOUT_RESTAPI;
            }
        }

        // MongoDB Direct
        if ((circuits & MONGO_DIRECT) != 0) {
            if (uploadToMongo(entry)) {
                entry.bitfield_complete |= MONGO_DIRECT;
            }
        }

        // InfluxDB
        if ((circuits & INFLUXDB_RESTAPI) != 0) {
            if (uploadToInfluxDB(entry)) {
                entry.bitfield_complete |= INFLUXDB_RESTAPI;
            }
        }

        // Check if complete
        if ((entry.bitfield_wanted & ~entry.bitfield_complete) == 0) {
            entry.delete();
        } else {
            entry.save();
        }
    }
}
```

## Comparison with Other Apps

| Integration | xDrip+ | xDrip4iOS | AAPS |
|-------------|--------|-----------|------|
| **Nightscout REST** | Yes | Yes | Yes |
| **MongoDB Direct** | Yes | No | No |
| **InfluxDB** | Yes | No | No |
| **Tidepool** | Yes (direct) | No | Yes (plugin) |
| **AAPS Status** | Yes (display) | No | N/A |
| **Multi-destination** | Yes (bitfield) | No | No |

---

## Code Citation

```
xdrip-android:com/eveningoutpost/dexdrip/tidepool/TidepoolUploader.java
xdrip-android:com/eveningoutpost/dexdrip/influxdb/InfluxDBUploader.java
xdrip-android:com/eveningoutpost/dexdrip/insulin/aaps/AAPSStatusHandler.java
xdrip-android:com/eveningoutpost/dexdrip/utilitymodels/UploaderQueue.java#L74-L92
```
