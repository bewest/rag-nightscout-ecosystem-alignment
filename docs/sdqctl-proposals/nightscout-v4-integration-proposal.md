# Nightscout V4 API Integration Proposal

> **Date**: 2026-01-31  
> **Status**: Draft  
> **Request**: "Integrate proposal to add api v4 endpoints to Nightscout coherently"  
> **Related**: [statespan-standardization-proposal.md](statespan-standardization-proposal.md)

---

## Executive Summary

This proposal consolidates findings from 14 Nocturne analysis documents to provide actionable recommendations for integrating V4-style features into the Nightscout ecosystem.

### Key Constraint

**Nocturne author preference**: StateSpan should remain V4-only (not backported to V3). This proposal respects that constraint while identifying features that:
1. Can be adopted independently in cgm-remote-monitor
2. Provide ecosystem-wide benefit
3. Have clear implementation paths

### Recommendation Summary

| Priority | Feature | Target | Effort |
|----------|---------|--------|--------|
| P0 | Document V4 as "Nocturne Extension" | Spec docs | Low |
| P1 | Soft delete consistency | cgm-remote-monitor | Low |
| P1 | srvModified semantics alignment | Nocturne | Medium |
| P2 | History endpoint in Nocturne | Nocturne | Medium |
| P3 | StateSpan adoption | Clients → V4 | High |

---

## V4 Feature Inventory

Based on analysis of `externals/nocturne/` and 14 deep-dive documents.

### V4 Endpoints (Nocturne-Native)

| Endpoint | Purpose | cgm-remote-monitor Equivalent |
|----------|---------|------------------------------|
| `/api/v4/state-spans` | Time-ranged state tracking | None |
| `/api/v4/state-spans/profiles` | Profile activation history | None |
| `/api/v4/state-spans/overrides` | Override history | None |
| `/api/v4/treatments` | Extended treatment API | V3 treatments |
| `/api/v4/chart-data` | Pre-aggregated chart data | None |
| `/api/v4/processing` | Data processing status | None |

### StateSpan Categories

| Category | States | Ecosystem Benefit |
|----------|--------|-------------------|
| `Profile` | Active | Query "what profile was active at time T?" |
| `Override` | None, Custom | Override duration visualization |
| `TempBasal` | Active, Cancelled | Temp basal history |
| `PumpMode` | Automatic, Manual, Suspended, etc. | Pump mode tracking across AID |
| `PumpConnectivity` | Connected, Disconnected | Connection status history |
| `Sleep` | User-defined | User-annotated periods |
| `Exercise` | User-defined | Activity annotations |
| `Illness` | User-defined | Sensitivity impact tracking |
| `Travel` | User-defined | Timezone change handling |

---

## Gap Analysis Summary

### Gaps Addressable by V4 Adoption

| Gap ID | Description | V4 Solution | Status |
|--------|-------------|-------------|--------|
| GAP-V4-001 | StateSpan API not standardized | V4 clients use Nocturne | Author: V4-only |
| GAP-V4-002 | Profile activation history | `/api/v4/state-spans/profiles` | Available in V4 |
| GAP-NOCTURNE-001 | V4 endpoints Nocturne-specific | Document as extension | Recommended |
| GAP-SYNC-041 | Missing history endpoint in Nocturne | StateSpan provides alternative | Partial |

### Gaps Requiring cgm-remote-monitor Work

| Gap ID | Description | Recommendation |
|--------|-------------|----------------|
| GAP-SYNC-040 | Delete semantics differ | Align on soft-delete default |
| GAP-SYNC-039 | srvModified profile support | Add to profile collection |
| GAP-PROF-004 | Profile history endpoint | Consider V4-style span query |

### Nocturne-Specific Gaps

| Gap ID | Description | Notes |
|--------|-------------|-------|
| GAP-NOCTURNE-002 | Rust oref may diverge from JS | Requires verification testing |
| GAP-NOCTURNE-003 | SignalR→Socket.IO bridge latency | 5-10ms overhead |
| GAP-NOCTURNE-004 | ProfileSwitch percentage applied internally | Different from cgm-remote-monitor |
| GAP-NOCTURNE-005 | Profile API returns raw values | Despite active ProfileSwitch |

---

## Compatibility Assessment

### Authentication: FULL COMPATIBILITY ✅

| Auth Method | cgm-remote-monitor | Nocturne | Status |
|-------------|-------------------|----------|--------|
| API_SECRET header | ✅ SHA1 hash | ✅ SHA1 hash | ✅ |
| JWT Bearer token | ✅ HMAC-SHA256 | ✅ HMAC-SHA256 | ✅ |
| Access token | ✅ `{name}-{hash}` | ✅ `{name}-{hash}` | ✅ |
| Query `?token=` | ✅ | ✅ | ✅ |
| Role permissions | ✅ 7 roles | ✅ 7 roles | ✅ |

**Source**: [nocturne-auth-compatibility.md](../10-domain/nocturne-auth-compatibility.md)

### API Versions: V1/V2/V3 COMPATIBLE ✅

| Version | cgm-remote-monitor | Nocturne | Status |
|---------|-------------------|----------|--------|
| V1 | ✅ | ✅ | Full parity |
| V2 | ✅ | ✅ | Full parity |
| V3 | ✅ | ✅ | Full parity |
| V4 | ❌ | ✅ | Nocturne-only |

### Sync Behavior: PARTIAL COMPATIBILITY ⚠️

| Behavior | cgm-remote-monitor | Nocturne | Impact |
|----------|-------------------|----------|--------|
| Soft delete | ✅ Default | ❌ Hard delete | Sync detection |
| srvModified | ✅ Server time | ⚠️ Alias for Mills | Limited impact |
| History endpoint | ✅ `/history/{ts}` | ❌ Missing | Sync polling |

---

## Recommendations

### Priority 0: Documentation (Low Effort)

**Action**: Document V4 as "Nocturne Extension API" in ecosystem specs.

```yaml
# specs/openapi/aid-extensions-v4.yaml
info:
  title: Nocturne V4 Extension API
  description: |
    These endpoints are specific to Nocturne and NOT part of 
    the standard Nightscout API. Clients should feature-detect 
    availability via `/api/v4/version` endpoint.
```

**Files to Update**:
- `specs/openapi/` - Add V4 extension spec
- `mapping/nightscout/README.md` - Document V4 availability
- `docs/10-domain/nightscout-api-versions.md` - Version matrix

---

### Priority 1: Sync Semantics Alignment (Medium Effort)

#### 1a. Soft Delete Consistency

**Problem**: Nocturne uses hard delete; sync clients can't detect deletions.

**Recommendation for Nocturne**:
```csharp
// Option A: Add soft delete support
public async Task<IActionResult> Delete(string id, [FromQuery] bool permanent = false)
{
    if (permanent)
        await _storage.DeletePermanently(id);
    else
        await _storage.MarkAsDeleted(id); // Set isValid = false
}
```

**Recommendation for cgm-remote-monitor**: No changes needed (already correct).

**Gap Reference**: GAP-SYNC-040

#### 1b. srvModified Semantics

**Problem**: Nocturne returns `Mills` as `srvModified` instead of server modification time.

**Impact**: Limited - clients use `/lastModified` endpoint, not per-record field.

**Recommendation for Nocturne**:
```csharp
// Track actual server modification time
public class Treatment
{
    [JsonPropertyName("srvModified")]
    public long SrvModified { get; set; } // Server update timestamp
    
    [JsonIgnore]
    public DateTime SysUpdatedAt { get; set; } // EF Core managed
}
```

**Gap Reference**: GAP-SYNC-039

---

### Priority 2: History Endpoint in Nocturne (Medium Effort)

**Problem**: Nocturne lacks `/api/v3/{collection}/history/{ts}` endpoint that AAPS uses for incremental sync.

**Current State**:
- cgm-remote-monitor: `/api/v3/treatments/history/1706745600000`
- Nocturne: Not implemented

**Recommendation**:
```csharp
[HttpGet("history/{ts}")]
public async Task<ActionResult> GetHistory(long ts)
{
    var modified = await _storage.GetModifiedAfter(ts);
    return Ok(new { result = modified });
}
```

**Alternative**: StateSpan API provides time-range queries but requires V4.

**Gap Reference**: GAP-SYNC-041

---

### Priority 3: StateSpan Client Adoption (High Effort)

**Constraint**: Per Nocturne author, StateSpan remains V4-only.

**Path Forward**:
1. Clients that want StateSpan features must use Nocturne
2. Feature-detect V4 availability at runtime
3. Fall back to V3 treatment queries for cgm-remote-monitor

**Client Implementation Pattern**:
```swift
// NightscoutClient.swift
func getProfileHistory(from: Date, to: Date) async throws -> [ProfileSpan] {
    if await supportsV4() {
        // Use StateSpan API
        return try await getStateSpans(category: .profile, from: from, to: to)
    } else {
        // Fall back to treatment-based query
        return try await getProfileSwitches(from: from, to: to).toSpans()
    }
}
```

**Gap Reference**: GAP-V4-001, GAP-V4-002

---

## Implementation Roadmap

### Phase 1: Documentation (Week 1)

- [ ] Create `specs/openapi/nocturne-v4-extensions.yaml`
- [ ] Update `mapping/nightscout/README.md` with V4 section
- [ ] Document feature detection pattern

### Phase 2: Nocturne Alignment (Week 2-3)

- [ ] PR: Add soft delete support to Nocturne
- [ ] PR: Fix srvModified semantics
- [ ] PR: Add history endpoint

### Phase 3: Client SDK Support (Week 4+)

- [ ] NightscoutKit: Add V4 feature detection
- [ ] NightscoutKit: Add StateSpan client if V4 available
- [ ] Document fallback patterns

---

## Ecosystem Impact Matrix

| System | V4 Benefit | Migration Path |
|--------|------------|----------------|
| **Loop** | Profile history | Must use Nocturne backend |
| **Trio** | Override tracking | Must use Nocturne backend |
| **AAPS** | Already uses V3 sync | History endpoint needed in Nocturne |
| **xDrip+** | StateSpan visualization | Must use Nocturne backend |
| **LoopFollow** | Override display | StateSpan improves UX |
| **Nightguard** | N/A | Display-only, no sync |

---

## Decision Matrix: When to Use V4

| Use Case | Recommendation |
|----------|----------------|
| Profile history query | ✅ Use V4 StateSpan if Nocturne |
| Override duration display | ✅ Use V4 StateSpan if Nocturne |
| Pump mode tracking | ✅ Use V4 StateSpan if Nocturne |
| Standard treatment sync | ⏸️ Use V3 (universal) |
| Cross-controller coexistence | ⏸️ Use V3 (universal) |
| Incremental sync | ⏸️ Use V3 history endpoint |

---

## Related Documents

| Document | Purpose |
|----------|---------|
| [statespan-standardization-proposal.md](statespan-standardization-proposal.md) | StateSpan V4-only decision |
| [nocturne-deep-dive.md](../10-domain/nocturne-deep-dive.md) | Architecture overview |
| [nocturne-auth-compatibility.md](../10-domain/nocturne-auth-compatibility.md) | Auth parity |
| [nocturne-deletion-semantics.md](../10-domain/nocturne-deletion-semantics.md) | Delete behavior |
| [nocturne-srvmodified-gap-analysis.md](../10-domain/nocturne-srvmodified-gap-analysis.md) | Sync semantics |
| [nocturne-v4-profile-extensions.md](../10-domain/nocturne-v4-profile-extensions.md) | V4 profile API |

---

## Appendix: V4 Endpoint Reference

### StateSpan Model

```csharp
public class StateSpan
{
    public string? Id { get; set; }
    public StateSpanCategory Category { get; set; }  // Profile, Override, PumpMode, etc.
    public string? State { get; set; }               // Active state value
    public long StartMills { get; set; }             // Start timestamp
    public long? EndMills { get; set; }              // End timestamp (null = active)
    public string? Source { get; set; }              // Data source
    public Dictionary<string, object>? Metadata { get; set; }
    public Guid? CanonicalId { get; set; }           // Deduplication ID
    public bool IsActive => !EndMills.HasValue;
}
```

### Query Examples

```bash
# Get active profile
GET /api/v4/state-spans?category=Profile&active=true

# Get profile history for date range
GET /api/v4/state-spans?category=Profile&from=1706745600000&to=1706832000000

# Get all overrides from last 24 hours
GET /api/v4/state-spans?category=Override&from=$(date -d '24 hours ago' +%s)000

# Get pump mode changes
GET /api/v4/state-spans?category=PumpMode&count=50
```
