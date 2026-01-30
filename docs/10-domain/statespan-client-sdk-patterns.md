# StateSpan Client SDK Patterns

> **Date**: 2026-01-30  
> **Status**: Research Complete  
> **Related Items**: sync-identity #21, StateSpan standardization proposal  
> **Prerequisites**: StateSpan gap remediation mapping ✅

---

## Executive Summary

This document defines SDK patterns for client applications consuming StateSpan API. It covers query patterns, caching strategies, migration from treatments, and platform-specific examples for Loop, AAPS, Trio, and xDrip+.

### Key Design Principles

1. **Time-range first**: All queries specify explicit time bounds
2. **Category filtering**: Single category per request for efficiency
3. **Active state shortcut**: Dedicated query for "current state"
4. **Backward compatible**: Coexist with treatment-based queries during migration

---

## Query Patterns

### Pattern 1: Active State at Time T

**Use case**: "What override is active right now?" or "What profile was active at 3pm?"

```
GET /api/v3/state-spans?category=Override&active=true
GET /api/v3/state-spans?category=Profile&at=1706634000000
```

**Response**: Single StateSpan or empty array

```json
{
  "result": [{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "category": "Override",
    "state": "Custom",
    "startMills": 1706630400000,
    "endMills": null,
    "source": "Loop",
    "metadata": {
      "insulinNeedsScaleFactor": 0.8,
      "targetTop": 120,
      "targetBottom": 100,
      "reason": "Exercise"
    }
  }]
}
```

### Pattern 2: All States in Time Range

**Use case**: Chart rendering, history view, data export

```
GET /api/v3/state-spans?category=Profile&from=1706544000000&to=1706630400000
GET /api/v3/state-spans?category=Override&from=1706544000000&to=1706630400000
```

**Response**: Array of StateSpans overlapping the range

```json
{
  "result": [
    {
      "id": "...",
      "category": "Profile",
      "state": "Active",
      "startMills": 1706544000000,
      "endMills": 1706572800000,
      "metadata": { "profileName": "Weekday" }
    },
    {
      "id": "...",
      "category": "Profile",
      "state": "Active",
      "startMills": 1706572800000,
      "endMills": null,
      "metadata": { "profileName": "Weekend" }
    }
  ]
}
```

### Pattern 3: Multi-Category Timeline

**Use case**: Unified timeline view showing all state changes

```
# Option A: Multiple requests (recommended for caching)
GET /api/v3/state-spans?category=Profile&from=...&to=...
GET /api/v3/state-spans?category=Override&from=...&to=...
GET /api/v3/state-spans?category=PumpMode&from=...&to=...

# Option B: Single request (if supported)
GET /api/v3/state-spans?category=Profile,Override,PumpMode&from=...&to=...
```

### Pattern 4: State at Specific Glucose Reading

**Use case**: Correlate glucose value with active states for analysis

```swift
// Given a glucose reading at timestamp T
let glucoseTime = reading.timestamp

// Query active states at that moment
let profile = await api.getStateSpan(category: .profile, at: glucoseTime)
let override = await api.getStateSpan(category: .override, at: glucoseTime)
let pumpMode = await api.getStateSpan(category: .pumpMode, at: glucoseTime)
```

---

## Caching Strategies

### Strategy 1: Sliding Window Cache

**Best for**: Real-time displays, chart rendering

```
┌─────────────────────────────────────────────────┐
│ Cache Window: now - 24h  to  now + 1h           │
│                                                 │
│ ├──────────────────────────────┼───────────────>│
│ │      Cached StateSpans       │   Future       │
│ └──────────────────────────────┴───────────────>│
│        stale after 5 min         refresh on use │
└─────────────────────────────────────────────────┘
```

**Implementation**:

```kotlin
class StateSpanCache(
    private val windowHours: Int = 24,
    private val staleDurationMinutes: Int = 5
) {
    private val spans = mutableMapOf<StateSpanCategory, List<StateSpan>>()
    private var lastFetch: Long = 0
    
    suspend fun getActiveSpan(category: StateSpanCategory): StateSpan? {
        refreshIfStale()
        return spans[category]?.find { it.isActiveAt(System.currentTimeMillis()) }
    }
    
    suspend fun getSpansInRange(category: StateSpanCategory, from: Long, to: Long): List<StateSpan> {
        refreshIfStale()
        return spans[category]?.filter { it.overlaps(from, to) } ?: emptyList()
    }
    
    private suspend fun refreshIfStale() {
        if (System.currentTimeMillis() - lastFetch > staleDurationMinutes * 60 * 1000) {
            val now = System.currentTimeMillis()
            val from = now - windowHours * 3600 * 1000
            val to = now + 3600 * 1000  // 1 hour future
            
            StateSpanCategory.values().forEach { category ->
                spans[category] = api.getStateSpans(category, from, to)
            }
            lastFetch = now
        }
    }
}
```

### Strategy 2: Incremental Sync

**Best for**: Offline-first apps, data persistence

```
┌─────────────────────────────────────────────────┐
│ Local DB: All historical StateSpans             │
│                                                 │
│ Sync Strategy:                                  │
│ 1. On app start: fetch spans since lastSync    │
│ 2. On socket event: fetch affected category    │
│ 3. Periodic: full sync every 24h               │
└─────────────────────────────────────────────────┘
```

**Implementation**:

```swift
class StateSpanSyncManager {
    private let db: LocalDatabase
    private var lastSyncTimestamp: Date
    
    func incrementalSync() async throws {
        let since = lastSyncTimestamp.timeIntervalSince1970 * 1000
        
        for category in StateSpanCategory.allCases {
            let spans = try await api.getStateSpans(
                category: category,
                modifiedSince: since
            )
            db.upsertStateSpans(spans)
        }
        
        lastSyncTimestamp = Date()
    }
    
    func handleSocketEvent(_ event: StateSpanEvent) async {
        // Real-time update for specific span
        switch event.type {
        case .created, .updated:
            db.upsertStateSpan(event.span)
        case .deleted:
            db.deleteStateSpan(event.spanId)
        }
    }
}
```

### Strategy 3: Category-Specific TTL

**Best for**: Mixed workloads with different freshness requirements

| Category | TTL | Rationale |
|----------|-----|-----------|
| Profile | 1 hour | Rarely changes during day |
| Override | 1 minute | User may cancel/modify frequently |
| PumpMode | 30 seconds | Critical for closed-loop status |
| TempBasal | 30 seconds | Changes every 5 minutes in closed-loop |

---

## Relationship to Existing APIs

### Coexistence with Treatments

During migration, clients must handle both:

```
┌─────────────────────────────────────────────────────┐
│                    Data Sources                      │
│                                                      │
│  ┌──────────────┐        ┌──────────────────────┐   │
│  │  Treatments  │        │     StateSpans       │   │
│  │  (legacy)    │───────>│     (new)            │   │
│  └──────────────┘  auto  └──────────────────────┘   │
│        │          translate         │               │
│        v                            v               │
│  ┌──────────────────────────────────────────────┐   │
│  │           Unified State Timeline              │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Migration Helper**:

```typescript
class UnifiedStateProvider {
    constructor(
        private stateSpanApi: StateSpanApi,
        private treatmentsApi: TreatmentsApi,
        private serverSupportsStateSpan: boolean
    ) {}
    
    async getActiveOverride(): Promise<Override | null> {
        if (this.serverSupportsStateSpan) {
            const span = await this.stateSpanApi.getActive('Override');
            return span ? this.mapSpanToOverride(span) : null;
        } else {
            // Fallback to treatment-based query
            const treatments = await this.treatmentsApi.query({
                eventType: ['Temporary Override', 'Temporary Target'],
                from: Date.now() - 24 * 60 * 60 * 1000
            });
            return this.findActiveOverride(treatments);
        }
    }
    
    private mapSpanToOverride(span: StateSpan): Override {
        return {
            id: span.id,
            start: new Date(span.startMills),
            end: span.endMills ? new Date(span.endMills) : null,
            insulinNeedsScaleFactor: span.metadata?.insulinNeedsScaleFactor,
            targetRange: {
                min: span.metadata?.targetBottom,
                max: span.metadata?.targetTop
            },
            reason: span.metadata?.reason
        };
    }
}
```

### Relationship to DeviceStatus

DeviceStatus contains **point-in-time snapshots** of controller state.
StateSpans provide **time-ranged states** with explicit boundaries.

| Aspect | DeviceStatus | StateSpan |
|--------|--------------|-----------|
| Granularity | Every 5 minutes | State changes only |
| Query pattern | "What was state at T?" | "When did state X start/end?" |
| Storage | High volume | Low volume |
| Use case | Real-time display | Historical analysis |

**Complementary Query**:

```swift
// Get current loop status from devicestatus
let deviceStatus = await api.getLatestDeviceStatus()

// Get context from statespans
let activeProfile = await api.getActiveStateSpan(category: .profile)
let activeOverride = await api.getActiveStateSpan(category: .override)

// Combined view
let context = LoopContext(
    iob: deviceStatus.loop.iob,
    cob: deviceStatus.loop.cob,
    profile: activeProfile?.metadata.profileName,
    override: activeOverride?.metadata.reason
)
```

---

## Platform-Specific SDK Examples

### Loop (Swift/iOS)

```swift
import NightscoutKit

// Define StateSpan types
enum StateSpanCategory: String, Codable {
    case profile = "Profile"
    case override = "Override"
    case tempBasal = "TempBasal"
    case pumpMode = "PumpMode"
}

struct StateSpan: Codable, Identifiable {
    let id: String
    let category: StateSpanCategory
    let state: String
    let startMills: Int64
    let endMills: Int64?
    let source: String
    let metadata: [String: AnyCodable]?
    
    var isActive: Bool {
        endMills == nil
    }
    
    func isActiveAt(_ timestamp: Int64) -> Bool {
        startMills <= timestamp && (endMills == nil || endMills! > timestamp)
    }
}

// NightscoutKit extension
extension NightscoutClient {
    func getStateSpans(
        category: StateSpanCategory,
        from: Date? = nil,
        to: Date? = nil,
        active: Bool? = nil
    ) async throws -> [StateSpan] {
        var params: [String: String] = ["category": category.rawValue]
        if let from = from { params["from"] = String(Int64(from.timeIntervalSince1970 * 1000)) }
        if let to = to { params["to"] = String(Int64(to.timeIntervalSince1970 * 1000)) }
        if let active = active { params["active"] = String(active) }
        
        return try await get("/api/v3/state-spans", params: params)
    }
    
    func getActiveOverride() async throws -> StateSpan? {
        let spans = try await getStateSpans(category: .override, active: true)
        return spans.first
    }
    
    func getProfileHistory(from: Date, to: Date) async throws -> [StateSpan] {
        return try await getStateSpans(category: .profile, from: from, to: to)
    }
}

// Usage in Loop
class OverrideManager {
    private let nightscout: NightscoutClient
    
    func fetchActiveOverride() async -> TemporaryScheduleOverride? {
        guard let span = try? await nightscout.getActiveOverride() else {
            return nil
        }
        
        return TemporaryScheduleOverride(
            context: .custom,
            settings: TemporaryScheduleOverrideSettings(
                targetRange: DoubleRange(
                    minValue: span.metadata?["targetBottom"]?.doubleValue,
                    maxValue: span.metadata?["targetTop"]?.doubleValue
                ),
                insulinNeedsScaleFactor: span.metadata?["insulinNeedsScaleFactor"]?.doubleValue
            ),
            startDate: Date(timeIntervalSince1970: Double(span.startMills) / 1000),
            duration: span.endMills.map { 
                TimeInterval(Double($0 - span.startMills) / 1000) 
            } ?? .infinity
        )
    }
}
```

### AAPS (Kotlin/Android)

```kotlin
package app.aaps.plugins.sync.nsclient.statespan

import kotlinx.serialization.Serializable
import java.time.Instant

@Serializable
enum class StateSpanCategory {
    Profile, Override, TempBasal, PumpMode, PumpConnectivity
}

@Serializable
data class StateSpan(
    val id: String,
    val category: StateSpanCategory,
    val state: String,
    val startMills: Long,
    val endMills: Long? = null,
    val source: String,
    val metadata: Map<String, Any>? = null,
    val originalId: String? = null,
    val canonicalId: String? = null
) {
    val isActive: Boolean get() = endMills == null
    
    fun isActiveAt(timestamp: Long): Boolean =
        startMills <= timestamp && (endMills == null || endMills > timestamp)
    
    fun overlaps(from: Long, to: Long): Boolean =
        startMills < to && (endMills == null || endMills > from)
}

// NSClient StateSpan API
interface StateSpanApi {
    @GET("api/v3/state-spans")
    suspend fun getStateSpans(
        @Query("category") category: StateSpanCategory,
        @Query("from") from: Long? = null,
        @Query("to") to: Long? = null,
        @Query("active") active: Boolean? = null
    ): Response<List<StateSpan>>
    
    @GET("api/v3/state-spans")
    suspend fun getActiveSpan(
        @Query("category") category: StateSpanCategory,
        @Query("active") active: Boolean = true
    ): Response<List<StateSpan>>
}

// Usage in AAPS
class StateSpanRepository @Inject constructor(
    private val api: StateSpanApi,
    private val db: StateSpanDao
) {
    suspend fun syncOverrides(from: Instant, to: Instant) {
        val spans = api.getStateSpans(
            category = StateSpanCategory.Override,
            from = from.toEpochMilli(),
            to = to.toEpochMilli()
        ).body() ?: return
        
        db.upsertAll(spans.map { it.toEntity() })
    }
    
    fun getActiveTemporaryTarget(): Flow<TemporaryTarget?> = 
        db.getActiveSpan(StateSpanCategory.Override)
            .map { span ->
                span?.let {
                    TemporaryTarget(
                        timestamp = it.startMills,
                        duration = it.endMills?.minus(it.startMills) ?: Long.MAX_VALUE,
                        lowTarget = (it.metadata?.get("targetBottom") as? Number)?.toDouble() ?: 0.0,
                        highTarget = (it.metadata?.get("targetTop") as? Number)?.toDouble() ?: 0.0,
                        reason = TemporaryTarget.Reason.fromString(it.metadata?.get("reason") as? String)
                    )
                }
            }
}
```

### xDrip+ (Java/Android)

```java
package com.eveningoutpost.dexdrip.nightscout;

import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

public class StateSpan {
    public String id;
    public String category;  // Profile, Override, TempBasal, PumpMode
    public String state;
    public long startMills;
    public Long endMills;  // null = active
    public String source;
    public Map<String, Object> metadata;
    
    public boolean isActive() {
        return endMills == null;
    }
    
    public boolean isActiveAt(long timestamp) {
        return startMills <= timestamp && (endMills == null || endMills > timestamp);
    }
}

public class StateSpanClient {
    private final OkHttpClient client;
    private final String baseUrl;
    private final String apiSecret;
    
    public List<StateSpan> getStateSpans(String category, Long from, Long to) throws IOException {
        HttpUrl.Builder urlBuilder = HttpUrl.parse(baseUrl + "/api/v3/state-spans").newBuilder()
            .addQueryParameter("category", category);
        
        if (from != null) urlBuilder.addQueryParameter("from", String.valueOf(from));
        if (to != null) urlBuilder.addQueryParameter("to", String.valueOf(to));
        
        Request request = new Request.Builder()
            .url(urlBuilder.build())
            .header("api-secret", apiSecret)
            .get()
            .build();
        
        try (Response response = client.newCall(request).execute()) {
            if (!response.isSuccessful()) throw new IOException("Unexpected code " + response);
            return gson.fromJson(response.body().string(), new TypeToken<List<StateSpan>>(){}.getType());
        }
    }
    
    public StateSpan getActiveOverride() throws IOException {
        List<StateSpan> spans = getStateSpans("Override", 
            System.currentTimeMillis() - TimeUnit.HOURS.toMillis(24),
            System.currentTimeMillis() + TimeUnit.HOURS.toMillis(1));
        
        long now = System.currentTimeMillis();
        return spans.stream()
            .filter(s -> s.isActiveAt(now))
            .findFirst()
            .orElse(null);
    }
}

// Usage in xDrip+
public class NightscoutSync {
    private final StateSpanClient stateSpanClient;
    
    public void syncOverrideStatus() {
        try {
            StateSpan activeOverride = stateSpanClient.getActiveOverride();
            if (activeOverride != null) {
                Double scaleFactor = (Double) activeOverride.metadata.get("insulinNeedsScaleFactor");
                if (scaleFactor != null) {
                    Profile.setTemporaryPercentage((int) (scaleFactor * 100));
                }
            } else {
                Profile.clearTemporaryPercentage();
            }
        } catch (IOException e) {
            Log.e(TAG, "Failed to sync override: " + e.getMessage());
        }
    }
}
```

---

## Socket.IO Real-Time Events

### Event Types

```typescript
// Server emits these events
socket.emit('statespan:created', { span: StateSpan });
socket.emit('statespan:updated', { span: StateSpan, previousEndMills: number | null });
socket.emit('statespan:ended', { spanId: string, endMills: number });
socket.emit('statespan:deleted', { spanId: string });
```

### Client Subscription

```javascript
// Subscribe to StateSpan updates
socket.on('statespan:created', (event) => {
    stateSpanCache.add(event.span);
    if (event.span.category === 'Override') {
        ui.showOverrideActivated(event.span);
    }
});

socket.on('statespan:ended', (event) => {
    stateSpanCache.updateEndTime(event.spanId, event.endMills);
    ui.showStateEnded(event.spanId);
});

socket.on('statespan:updated', (event) => {
    stateSpanCache.update(event.span);
});
```

---

## Error Handling

### Common Error Responses

| Status | Meaning | Client Action |
|--------|---------|---------------|
| 400 | Invalid query params | Log error, check params |
| 401 | Auth required | Prompt re-auth |
| 404 | StateSpan API not available | Fallback to treatments |
| 503 | Server overloaded | Exponential backoff |

### Fallback Pattern

```swift
func getActiveOverride() async -> Override? {
    do {
        // Try StateSpan API first
        if let span = try await nightscout.getActiveStateSpan(category: .override) {
            return Override(from: span)
        }
        return nil
    } catch NightscoutError.notFound {
        // Server doesn't support StateSpan - fallback to treatments
        return await getActiveOverrideFromTreatments()
    } catch {
        log.error("StateSpan query failed: \(error)")
        return nil
    }
}
```

---

## Migration Checklist

### For Client Developers

- [ ] Add StateSpan model classes
- [ ] Implement StateSpan API client
- [ ] Add feature flag for StateSpan support
- [ ] Implement fallback to treatments
- [ ] Add cache layer with appropriate TTL
- [ ] Subscribe to Socket.IO events
- [ ] Update UI to show time-ranged states
- [ ] Test with both StateSpan and treatment-only servers

### Server Version Detection

```typescript
async function detectStateSpanSupport(): Promise<boolean> {
    try {
        const response = await fetch(`${baseUrl}/api/v3/state-spans?limit=1`);
        return response.ok;
    } catch {
        return false;
    }
}
```

---

## References

- [StateSpan Standardization Proposal](../../docs/sdqctl-proposals/statespan-standardization-proposal.md)
- [StateSpan Gap Remediation Mapping](./statespan-gap-remediation-mapping.md)
- [Nocturne V4 StateSpan Implementation](../../externals/nocturne/src/Core/Nocturne.Core.Models/StateSpan.cs)
- [NightscoutKit (Loop)](../../externals/LoopWorkspace/NightscoutKit/)
- [AAPS NSClient](../../externals/AndroidAPS/plugins/sync/src/main/kotlin/app/aaps/plugins/sync/nsclient/)
