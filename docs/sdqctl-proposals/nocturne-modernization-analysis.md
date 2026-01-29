# Modernization Analysis: cgm-remote-monitor vs Nocturne

> **Date**: 2026-01-28  
> **Status**: Draft Analysis  
> **Prerequisites**: Nocturne audit ✅, share2nightscout-bridge audit ✅

This document provides a comprehensive comparison between the original Nightscout server (cgm-remote-monitor) and Nocturne, analyzing feature parity, architectural differences, and migration implications.

---

## Executive Summary

| Aspect | cgm-remote-monitor | Nocturne | Assessment |
|--------|-------------------|----------|------------|
| **Maturity** | 10+ years, production | <1 year, active dev | cgm-remote-monitor proven |
| **API Parity** | v1, v2, v3 (origin) | v1, v2, v3 (compatible) | ✅ Equivalent |
| **Performance** | Adequate | Optimized (claims) | Nocturne likely faster |
| **Maintainability** | JS legacy codebase | Modern C#/.NET | Nocturne advantage |
| **Ecosystem** | 20+ integrations | Growing | cgm-remote-monitor advantage |

**Recommendation**: Nocturne is viable for new deployments; migration requires careful testing. Both should be maintained for ecosystem diversity.

---

## Architecture Comparison

### Technology Stack

| Component | cgm-remote-monitor | Nocturne |
|-----------|-------------------|----------|
| **Language** | JavaScript (Node.js) | C# (.NET 10) |
| **Runtime** | Node.js 16-20 | .NET 10 (cross-platform) |
| **Database** | MongoDB | PostgreSQL |
| **Cache** | In-memory | In-memory (no Redis) |
| **Real-time** | Socket.IO | SignalR (+ bridge) |
| **Frontend** | Backbone.js + EJS | SvelteKit 2 + Svelte 5 |
| **Build** | Webpack | .NET Aspire |
| **Algorithm** | JavaScript oref | Rust oref (FFI/WASM) |

### Codebase Scale

| Metric | cgm-remote-monitor | Nocturne |
|--------|-------------------|----------|
| **Main Language Files** | 293 JS files | 927 C# files |
| **Lines of Code** | ~35,000 (lib/) | ~282,000 |
| **Plugins/Extensions** | 38 plugins | Service-based |
| **Frontend Components** | 4 JS + 1 EJS | 438 Svelte |
| **Dependencies** | ~80 npm packages | .NET + pnpm |

**Analysis**: Nocturne is significantly larger codebase but with stronger typing and modern architecture.

---

## API Compatibility

### Endpoint Parity

| API | cgm-remote-monitor | Nocturne | Notes |
|-----|-------------------|----------|-------|
| **v1 entries** | ✅ `/api/v1/entries` | ✅ | Full compatibility |
| **v1 treatments** | ✅ `/api/v1/treatments` | ✅ | Full compatibility |
| **v1 devicestatus** | ✅ `/api/v1/devicestatus` | ✅ | Full compatibility |
| **v1 profile** | ✅ `/api/v1/profile` | ✅ | Full compatibility |
| **v1 status** | ✅ `/api/v1/status` | ✅ | Full compatibility |
| **v2 ddata** | ✅ `/api/v2/ddata` | ✅ | Loop/AAPS combined data |
| **v2 properties** | ✅ | ✅ | Runtime properties |
| **v3 generic** | ✅ Full CRUD | ✅ | All collections |
| **v4 extensions** | ❌ | ✅ | Nocturne-only |

### Deduplication

| Aspect | cgm-remote-monitor | Nocturne |
|--------|-------------------|----------|
| **Primary Key** | `identifier` | `identifier` (+ Id) |
| **Fallback** | `created_at` + `eventType` | Similar logic |
| **API v1** | `_id` based | `_id` compatible |

**Gap**: GAP-NOCTURNE-001 - V4 endpoints are Nocturne-specific.

---

## Data Connector Comparison

### cgm-remote-monitor Ecosystem

| Data Source | Method | Notes |
|-------------|--------|-------|
| Dexcom Share | `share2nightscout-bridge` | Separate daemon |
| Dexcom G7 | Via xDrip+ upload | Indirect |
| LibreLinkUp | `nightscout-librelink-up` | Separate bridge |
| Tidepool | Manual import | No real-time |
| Loop | Direct upload | Native support |
| AAPS | Direct upload | Native support |
| xDrip+ | Direct upload | Native support |
| Spike | Direct upload | iOS CGM app |

### Nocturne Native Connectors

| Connector | Auth | Real-time |
|-----------|------|-----------|
| Dexcom | Share API | ✅ Polling |
| FreeStyle (LibreLinkUp) | OAuth | ✅ Polling |
| Glooko | OAuth | ✅ Polling |
| MiniMed CareLink | Username/password | ✅ Polling |
| MyFitnessPal | OAuth | ✅ Polling |
| MyLife | OAuth | ✅ Polling |
| Nightscout | API_SECRET | ✅ Sync |
| TConnectSync | OAuth | ✅ Polling |
| Tidepool | OAuth | ✅ Polling |

**Advantage**: Nocturne has 9 native connectors; cgm-remote-monitor requires separate bridges.

**Risk**: share2nightscout-bridge uses hardcoded Dexcom app ID (GAP-SHARE-003).

---

## Plugin System Comparison

### cgm-remote-monitor Plugins (38 total)

| Category | Plugins |
|----------|---------|
| **CGM Display** | bgnow, rawbg, direction, ar2, errorcodes |
| **IOB/COB** | iob, cob, boluscalc, boluswizardpreview |
| **Device Age** | cannulaage, insulinage, sensorage, batteryage |
| **Pump** | pump, basalprofile, profile |
| **AID Systems** | loop, openaps, override |
| **Alerts** | simplealarms, pushover, maker |
| **Voice** | alexa, googlehome, speech |
| **Data** | careportal, bridge, mmconnect, dbsize |
| **Core** | timeago, treatmentnotify, runtimestate |

### Nocturne Approach

- **No plugin system** - Functionality built into services
- Connectors as separate .NET projects
- V4 API provides extended endpoints instead

**Trade-off**: cgm-remote-monitor more extensible; Nocturne more integrated.

---

## Database Migration

### Schema Differences

| Collection | cgm-remote-monitor (MongoDB) | Nocturne (PostgreSQL) |
|------------|------------------------------|----------------------|
| entries | Document-based, flexible | Typed `EntryEntity` |
| treatments | Document-based, flexible | Typed `TreatmentEntity` |
| devicestatus | Nested objects | Flattened columns |
| profile | Nested schedules | Normalized tables |

### Migration Path

Nocturne includes migration tooling:
- `src/Tools/Nocturne.Tools.Migration/` - CLI migration tool
- `MigrateCommand.cs` - MongoDB → PostgreSQL
- `BackupCommand.cs` - Data backup
- `RecoveryCommand.cs` - Rollback support

### Migration Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Data loss | High | Full backup, verify counts |
| Schema mismatch | Medium | Test with production copy |
| Plugin data | Medium | Manual plugin field migration |
| `_id` format | Low | Preserved as OriginalId |

---

## Real-time Communication

### cgm-remote-monitor

```
Client ←→ Socket.IO ←→ Node.js Server ←→ MongoDB
```

- Native Socket.IO support
- All clients compatible
- 10+ years of ecosystem integration

### Nocturne

```
Client ←→ SignalR Hub ←→ .NET Server ←→ PostgreSQL
           ↓
    Socket.IO Bridge
           ↓
Legacy Socket.IO Clients
```

- Native SignalR (modern .NET)
- Socket.IO bridge for compatibility
- **Gap**: GAP-NOCTURNE-003 - Bridge adds latency

---

## Algorithm Implementation

### cgm-remote-monitor (JS oref)

- `lib/plugins/openaps.js` - OpenAPS status display
- `lib/plugins/loop.js` - Loop status display
- `lib/plugins/iob.js` - IOB calculation
- `lib/plugins/cob.js` - COB calculation

**Note**: cgm-remote-monitor displays algorithm output, doesn't run algorithms.

### Nocturne (Rust oref)

- `src/Core/oref/` - Rust implementation
- Native IOB, COB, dosing algorithms
- FFI bindings for .NET
- WASM for browser-side calculations

**Gap**: GAP-NOCTURNE-002 - Rust implementation may diverge from JS oref0/oref1.

---

## Interoperability Impact

### AID Client Compatibility

| Client | cgm-remote-monitor | Nocturne |
|--------|-------------------|----------|
| **Loop** | ✅ Native | ✅ API compatible |
| **AAPS** | ✅ Native | ✅ API compatible |
| **Trio** | ✅ Native | ✅ API compatible |
| **xDrip+** | ✅ Native | ✅ API compatible |
| **xDrip4iOS** | ✅ Native | ⚠️ Needs testing |
| **Nightguard** | ✅ Native | ⚠️ Needs testing |
| **LoopFollow** | ✅ Native | ⚠️ Needs testing |
| **LoopCaregiver** | ✅ Native | ⚠️ Needs testing |

### Breaking Changes

None identified - Nocturne maintains API compatibility.

### Ecosystem Diversity Value

Having both implementations provides:
1. **Resilience** - No single point of failure
2. **Choice** - Users can select preferred stack
3. **Competition** - Drives innovation
4. **Validation** - Cross-check implementations

---

## Deployment Comparison

### cgm-remote-monitor

| Platform | Support |
|----------|---------|
| Heroku | ✅ One-click |
| Azure | ✅ ARM template |
| Railway | ✅ Community |
| Fly.io | ✅ Community |
| Docker | ✅ Official |
| Local | ✅ npm install |

### Nocturne

| Platform | Support |
|----------|---------|
| Docker | ✅ Official |
| .NET Aspire | ✅ Native (dev) |
| Kubernetes | ⚠️ Possible |
| Heroku | ❌ Not .NET |
| Azure | ⚠️ Needs config |

**Gap**: Nocturne has fewer deployment options currently.

---

## Recommendations

### For New Users

| Scenario | Recommendation |
|----------|----------------|
| Simple setup, Heroku | cgm-remote-monitor |
| Technical user, wants modern stack | Nocturne |
| Multiple CGM sources | Nocturne (native connectors) |
| Need specific plugin | cgm-remote-monitor |

### For Existing Users

| Scenario | Recommendation |
|----------|----------------|
| Happy with current setup | Stay on cgm-remote-monitor |
| Want PostgreSQL | Migrate to Nocturne |
| Performance issues | Evaluate Nocturne |
| Using Dexcom Share bridge | Consider Nocturne native |

### For Ecosystem Development

1. **Maintain both** - Ecosystem diversity is valuable
2. **API parity tests** - Cross-validate v1/v2/v3 behavior
3. **Algorithm conformance** - Test Rust vs JS oref outputs
4. **Document V4** - If adopted, standardize extensions

---

## Migration Checklist

- [ ] Backup MongoDB data completely
- [ ] Test migration on copy first
- [ ] Verify all collections migrated
- [ ] Test AID client connectivity (Loop, AAPS, Trio)
- [ ] Verify real-time updates (Socket.IO bridge)
- [ ] Check plugin functionality alternatives
- [ ] Validate historical data access
- [ ] Test reports and analytics
- [ ] Configure connectors (if switching from bridges)
- [ ] Update DNS/firewall as needed

---

## Gaps Summary

| Gap ID | Description | Impact |
|--------|-------------|--------|
| GAP-NOCTURNE-001 | V4 endpoints Nocturne-specific | Ecosystem fragmentation risk |
| GAP-NOCTURNE-002 | Rust oref may diverge | Algorithm consistency |
| GAP-NOCTURNE-003 | SignalR bridge latency | Real-time performance |
| GAP-SHARE-001 | Bridge uses API v1 only | No v3 features |
| GAP-SHARE-002 | No backfill logic | Data gaps |
| GAP-SHARE-003 | Hardcoded Dexcom app ID | Ecosystem risk |

---

## Cross-References

- [Nocturne Deep Dive](../10-domain/nocturne-deep-dive.md)
- [share2nightscout-bridge Deep Dive](../10-domain/share2nightscout-bridge-deep-dive.md)
- [Terminology Matrix](../../mapping/cross-project/terminology-matrix.md)
- [Gaps Registry](../../traceability/gaps.md)

---

## Next Steps

1. **Performance benchmarking** - Quantify speed differences
2. **Migration pilot** - Test with volunteer users
3. **V4 standardization** - Propose RFC if valuable
4. **Algorithm conformance suite** - Rust vs JS test vectors
5. **Client compatibility matrix** - Systematic testing
