# xDrip+ Nightscout Synchronization

This document describes how xDrip+ (Android) synchronizes data with Nightscout, including the upload queue architecture, API interactions, and treatment sync patterns.

## Architecture Overview

xDrip+ uses a **unified UploaderQueue** that routes data to multiple destinations via bitfield circuits:

```
┌─────────────────────────────────────────────────────────────────┐
│                      UploaderQueue                               │
│                                                                  │
│  Each entry has:                                                 │
│  • timestamp       - When queued                                 │
│  • action          - "insert", "update", "delete"               │
│  • otype           - Object type (BgReading, Treatments, etc.)  │
│  • reference_uuid  - UUID of the data object                    │
│  • bitfield_wanted - Which circuits should receive this         │
│  • bitfield_complete - Which circuits have processed this       │
│                                                                  │
│  Circuits (bitfield flags):                                      │
│  ┌──────────────────────┐                                       │
│  │ MONGO_DIRECT    = 1  │ → MongoDB direct connection           │
│  │ NIGHTSCOUT_REST = 2  │ → Nightscout REST API                 │
│  │ TEST_PLUGIN    = 4   │ → Debug/testing                       │
│  │ INFLUXDB_REST  = 8   │ → InfluxDB line protocol              │
│  │ WATCH_WEARAPI  = 16  │ → Android Wear sync                   │
│  └──────────────────────┘                                       │
└─────────────────────────────────────────────────────────────────┘
```

## Source Files

| File | Purpose | Lines |
|------|---------|-------|
| `utilitymodels/UploaderQueue.java` | Unified upload queue | ~557 |
| `utilitymodels/NightscoutUploader.java` | REST API client | ~1,470 |
| `utilitymodels/NightscoutTreatments.java` | Treatment sync logic | ~400 |
| `cgm/nsfollow/NightscoutFollow.java` | Follower mode | ~135 |
| `cgm/nsfollow/NightscoutFollowService.java` | Follower service | ~237 |
| `services/SyncService.java` | Background sync | ~200 |

## UploaderQueue

### Schema

```java
@Table(name = "UploaderQueue", id = BaseColumns._ID)
public class UploaderQueue extends Model {

    // Bitfield constants for routing
    public static final long MONGO_DIRECT = 1;
    public static final long NIGHTSCOUT_RESTAPI = 1 << 1;  // 2
    public static final long TEST_OUTPUT_PLUGIN = 1 << 2;  // 4
    public static final long INFLUXDB_RESTAPI = 1 << 3;    // 8
    public static final long WATCH_WEARAPI = 1 << 4;       // 16

    @Column(name = "timestamp", index = true)
    public long timestamp;

    @Column(name = "action", index = true)
    public String action;  // "insert", "update", "delete"

    @Column(name = "otype", index = true)
    public String type;    // "BgReading", "Treatments", "Calibration", etc.

    @Column(name = "reference_id")
    public long reference_id;

    @Column(name = "reference_uuid")
    public String reference_uuid;

    @Column(name = "bitfield_wanted", index = true)
    public long bitfield_wanted;     // Which circuits should process

    @Column(name = "bitfield_complete", index = true)
    public long bitfield_complete;   // Which circuits have processed
}
```

### Queue Operations

```java
// Add new entry to queue
public static void newEntry(String action, Model obj) {
    UploaderQueue entry = new UploaderQueue();
    entry.timestamp = JoH.tsl();
    entry.action = action;
    entry.type = obj.getClass().getSimpleName();
    entry.reference_uuid = getUuid(obj);
    entry.bitfield_wanted = DEFAULT_UPLOAD_CIRCUITS;
    entry.bitfield_complete = 0;
    entry.save();

    // Trigger sync service
    startSyncService(SYNC_QUEUE, "new queue entry");
}

// Mark circuit as complete
public static void markComplete(UploaderQueue entry, long circuit) {
    entry.bitfield_complete |= circuit;
    entry.save();
}

// Check if entry is fully processed
public static boolean isComplete(UploaderQueue entry) {
    return (entry.bitfield_wanted & ~entry.bitfield_complete) == 0;
}
```

## Nightscout REST API

### Service Interface

```java
public interface NightscoutService {

    // Upload glucose entries
    @POST("entries")
    Call<ResponseBody> upload(@Header("api-secret") String secret,
                              @Body RequestBody body);

    // Upload device status
    @POST("devicestatus")
    Call<ResponseBody> uploadDeviceStatus(@Header("api-secret") String secret,
                                          @Body RequestBody body);

    // Upload treatments
    @POST("treatments")
    Call<ResponseBody> uploadTreatments(@Header("api-secret") String secret,
                                        @Body RequestBody body);

    // Upsert treatments (create or update)
    @PUT("treatments")
    Call<ResponseBody> upsertTreatments(@Header("api-secret") String secret,
                                        @Body RequestBody body);

    // Download treatments
    @GET("treatments")
    Call<ResponseBody> downloadTreatments(@Header("api-secret") String secret,
                                          @Header("BROKEN-If-Modified-Since") String ifmodified);

    // Find treatment by UUID
    @GET("treatments.json")
    Call<ResponseBody> findTreatmentByUUID(@Header("api-secret") String secret,
                                           @Query("find[uuid]") String uuid);

    // Delete treatment
    @DELETE("treatments/{id}")
    Call<ResponseBody> deleteTreatment(@Header("api-secret") String secret,
                                       @Path("id") String id);

    // Get server status
    @GET("status.json")
    Call<ResponseBody> getStatus(@Header("api-secret") String secret);

    // Upload activity data
    @POST("activity")
    Call<ResponseBody> uploadActivity(@Header("api-secret") String secret,
                                      @Body RequestBody body);
}
```

### API Secret Handling

```java
// SHA1 hash of API secret
private String getApiSecret() {
    String secret = Pref.getString("api_secret", "");
    if (secret.isEmpty()) return null;
    return Hashing.sha1()
            .hashBytes(secret.getBytes(Charsets.UTF_8))
            .toString();
}
```

## BG Reading Upload

### Entry Format

```java
private JSONObject populateV1APIBGEntry(BgReading record) throws JSONException {
    JSONObject json = new JSONObject();

    // Core fields
    json.put("device", getDeviceName());
    json.put("date", record.timestamp);
    json.put("dateString", formatDate(record.timestamp));
    json.put("sgv", (int) record.calculated_value);

    // Direction/trend
    String direction = record.slopeName();
    if (direction != null) {
        json.put("direction", direction);
    }

    // Raw data (if available and not Libre)
    if (record.raw_data != 0 && !isLibre) {
        json.put("unfiltered", record.raw_data * 1000);
        json.put("filtered", record.filtered_data * 1000);
    }

    // Noise
    json.put("noise", mapNoise(record.noise));

    // Type identifier
    json.put("type", "sgv");

    return json;
}
```

### Batch Upload

```java
public boolean doRESTUploadTo(URI baseURI, List<BgReading> glucoseDataSets,
                              List<Calibration> calibrations) {

    JSONArray entriesBody = new JSONArray();

    // Add glucose readings
    for (BgReading record : glucoseDataSets) {
        entriesBody.put(populateV1APIBGEntry(record));
    }

    // Add calibrations
    for (Calibration record : calibrations) {
        entriesBody.put(populateV1APICal(record));
    }

    // Gzip if enabled
    RequestBody body = createRequestBody(entriesBody.toString());

    // POST to /api/v1/entries
    Response<ResponseBody> response = service.upload(getApiSecret(), body)
            .execute();

    return response.isSuccessful();
}
```

## Treatment Sync

### Upload

```java
public static void pushTreatmentSync(Treatments treatment, boolean is_new) {
    String action = is_new ? "insert" : "update";
    UploaderQueue.newEntry(action, treatment);
}

private boolean doRESTTreatmentUpload(Treatments treatment) {
    JSONObject json = new JSONObject();

    json.put("eventType", treatment.eventType);
    json.put("created_at", formatDate(treatment.timestamp));
    json.put("enteredBy", Treatments.XDRIP_TAG);

    if (treatment.carbs > 0) {
        json.put("carbs", treatment.carbs);
    }
    if (treatment.insulin > 0) {
        json.put("insulin", treatment.insulin);
    }
    if (treatment.notes != null && !treatment.notes.isEmpty()) {
        json.put("notes", treatment.notes);
    }

    // UUID for tracking
    json.put("uuid", treatment.uuid);

    RequestBody body = createRequestBody(json.toString());
    Response<ResponseBody> response = service.uploadTreatments(getApiSecret(), body)
            .execute();

    return response.isSuccessful();
}
```

### Download

```java
public static void processTreatmentResponse(String response) {
    JSONArray treatments = new JSONArray(response);

    for (int i = 0; i < treatments.length(); i++) {
        JSONObject t = treatments.getJSONObject(i);

        String eventType = t.optString("eventType", "");
        String enteredBy = t.optString("enteredBy", "");
        long timestamp = parseDate(t.optString("created_at"));

        // Skip our own treatments
        if (enteredBy.equals(Treatments.XDRIP_TAG)) {
            continue;
        }

        // Process based on event type
        Treatments existing = Treatments.byuuid(t.optString("_id"));
        if (existing == null) {
            Treatments newTreatment = new Treatments();
            newTreatment.uuid = t.optString("_id");
            newTreatment.eventType = eventType;
            newTreatment.enteredBy = enteredBy;
            newTreatment.timestamp = timestamp;
            newTreatment.carbs = t.optDouble("carbs", 0);
            newTreatment.insulin = t.optDouble("insulin", 0);
            newTreatment.notes = t.optString("notes", "");
            newTreatment.save();
        }
    }
}
```

### Delete Sync

```java
public boolean doRESTTreatmentDelete(String uuid) {
    // First find the NS _id
    Response<ResponseBody> findResponse = service
            .findTreatmentByUUID(getApiSecret(), uuid)
            .execute();

    if (findResponse.isSuccessful()) {
        JSONArray results = new JSONArray(findResponse.body().string());
        if (results.length() > 0) {
            String nsId = results.getJSONObject(0).getString("_id");

            // Delete by NS _id
            Response<ResponseBody> deleteResponse = service
                    .deleteTreatment(getApiSecret(), nsId)
                    .execute();

            return deleteResponse.isSuccessful();
        }
    }
    return false;
}
```

## Follower Mode

### Entry Download

```java
public interface Nightscout {
    @GET("/api/v1/entries.json")
    Call<List<Entry>> getEntries(@Header("api-secret") String secret,
                                 @Query("count") int count,
                                 @Query("rr") String rr);

    @GET("/api/v1/treatments")
    Call<ResponseBody> getTreatments(@Header("api-secret") String secret);
}

public static void work(final boolean live) {
    int count = Math.min(MissedReadingsEstimator.estimate() + 1, 288);
    count = Math.max(10, count);

    getService().getEntries(session.url.getHashedSecret(), count, JoH.tsl() + "")
            .enqueue(session.entriesCallback);

    if (treatmentDownloadEnabled()) {
        getService().getTreatments(session.url.getHashedSecret())
                .enqueue(session.treatmentsCallback);
    }
}
```

### Entry Processing

```java
public static void processEntries(List<Entry> entries, boolean live) {
    for (Entry entry : entries) {
        // Skip if already exists
        if (BgReading.getForTimestamp(entry.date) != null) {
            continue;
        }

        // Create new reading
        BgReading bg = BgReading.create();
        bg.timestamp = entry.date;
        bg.calculated_value = entry.sgv;
        bg.source_info = "NSFollow";

        // Map direction to slope
        if (entry.direction != null) {
            bg.hide_slope = false;
            // ... map direction string to slope value
        }

        bg.save();
    }
}
```

## Device Status Upload

```java
private boolean doRESTDeviceStatusUpload() {
    JSONObject json = new JSONObject();

    // Uploader info
    JSONObject uploader = new JSONObject();
    uploader.put("battery", getBatteryLevel());
    json.put("uploader", uploader);

    // Device identifier
    json.put("device", "xDrip-" + Build.MANUFACTURER + Build.MODEL);

    // Created timestamp
    json.put("created_at", formatDate(JoH.tsl()));

    RequestBody body = createRequestBody(json.toString());
    Response<ResponseBody> response = service
            .uploadDeviceStatus(getApiSecret(), body)
            .execute();

    return response.isSuccessful();
}
```

## Backfill Logic

xDrip+ implements intelligent backfill for missed readings:

```java
public class MissedReadingsEstimator {

    private static final long DEXCOM_PERIOD = 5 * 60 * 1000; // 5 minutes

    public static int estimate() {
        BgReading last = BgReading.last();
        if (last == null) {
            return 288; // Full day of readings
        }

        long gap = JoH.msSince(last.timestamp);
        int missed = (int) (gap / DEXCOM_PERIOD);

        return Math.min(missed, 288);
    }
}
```

## Rate Limiting

```java
// Rate limit treatment downloads
if (JoH.ratelimit("nsfollow-treatment-download", 60)) {
    getService().getTreatments(secret).enqueue(callback);
}

// Rate limit uploads to prevent flooding
if (JoH.ratelimit("ns-upload", 5)) {
    doRESTUploadTo(baseURI, readings, calibrations);
}
```

## Error Handling

```java
public static long last_success_time = -1;
public static long last_exception_time = -1;
public static int last_exception_count = 0;
public static String last_exception;

public static final int FAIL_NOTIFICATION_PERIOD = 24 * 60 * 60; // 24 hours
public static final int FAIL_LOG_PERIOD = 6 * 60 * 60;          // 6 hours

private void handleUploadFailure(Exception e) {
    last_exception_time = JoH.tsl();
    last_exception_count++;
    last_exception = e.getMessage();

    if (last_exception_count >= FAIl_COUNT_NOTIFICATION) {
        showFailureNotification();
    }

    if (last_exception_count >= FAIL_COUNT_LOG) {
        UserError.Log.e(TAG, "Nightscout upload failed: " + e);
    }
}
```

## Comparison with xDrip4iOS

| Aspect | xDrip+ (Android) | xDrip4iOS |
|--------|-----------------|-----------|
| **Queue System** | UploaderQueue with bitfields | Direct upload |
| **Multi-destination** | 5 circuits (NS, Mongo, InfluxDB, Wear, Test) | Nightscout only |
| **Treatment Sync** | Bi-directional with delete | Bi-directional |
| **Backfill** | MissedReadingsEstimator | Time-based |
| **Gzip** | Yes (configurable) | No |
| **Rate Limiting** | JoH.ratelimit() | Timer-based |
| **Device Status** | Detailed (battery, device) | Basic |

---

## Code Citation

```
xdrip-android:com/eveningoutpost/dexdrip/utilitymodels/UploaderQueue.java#L44-L125
xdrip-android:com/eveningoutpost/dexdrip/utilitymodels/NightscoutUploader.java#L127-L162
xdrip-android:com/eveningoutpost/dexdrip/cgm/nsfollow/NightscoutFollow.java#L43-L53
```
