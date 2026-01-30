# cgm-remote-monitor: WebSocket System

**Source**: `externals/cgm-remote-monitor` (wip/bewest/mongodb-5x)  
**Verified**: 2026-01-20

## Overview

The WebSocket system provides real-time data updates to connected clients (followers, apps).

## Broadcast Mechanism

Per `lib/server/websocket.js:128-138`:

```javascript
function emitData(delta) {
  if (lastData.cals) {
    if (lastProfileSwitch !== ctx.ddata.lastProfileFromSwitch) {
      delta.status = status(ctx.ddata.profiles);
      lastProfileSwitch = ctx.ddata.lastProfileFromSwitch;
    }
    io.to('DataReceivers').compress(true).emit('dataUpdate', delta);
  }
}
```

**Key Points**:
- Broadcasts to `'DataReceivers'` room
- Uses compression when payload > 512 bytes
- Delta-based: Only changes sent, not full data
- Triggered by `'data-processed'` event

## Client Rooms

Per `lib/server/websocket.js:601`:

Clients join `'DataReceivers'` room on connection to receive broadcasts.

## Array vs Single Document Handling

Per `lib/server/websocket.js:305-354`:

```javascript
// Comment: "Array support added for MongoDB 5.x migration"

function processNextItem() {
  if (index >= data.length) {
    return callback(null, results);
  }
  
  processSingleDbAdd(data[index], collection, function(err, result) {
    results.push(result);
    index++;
    processNextItem();  // Sequential processing
  });
}
```

**Behavior**:
- Arrays processed sequentially, item-by-item
- Each item passes through independent deduplication
- Results concatenated into response array

## Deduplication

### Time Window

Per `lib/server/websocket.js:310`:

```javascript
const maxtimediff = times.secs(2).msecs;  // 2000ms
```

### Treatments Deduplication

Per `lib/server/websocket.js:364-467`:

Two-level matching:

1. **Exact match**: `created_at` + `eventType`
2. **Similar match** (within 2 seconds):
   - Same `eventType`
   - Optional field matching: `insulin`, `carbs`, `NSCLIENT_ID`, etc.

### DeviceStatus Deduplication

Per `lib/server/websocket.js:469-515`:

- Match on `NSCLIENT_ID` or `created_at`

## Known Issue: Array Deduplication

Per `docs/proposals/websocket-array-deduplication-issue.md`:

**Issue**: When 3 items sent as array with same `eventType` within 2 seconds, only 1 document inserted.

**Root Cause**: Sequential processing + cascading deduplication (items 2 & 3 match item 1 in DB).

**Status**: NOT A BUG - Expected deduplication behavior.

**Real-World Impact**: None - actual clients use unique identifiers (`NSCLIENT_ID`, `syncIdentifier`, `id`).

## Delta Calculation

Per `lib/data/calcdelta.js`:

### Compressible Arrays

Line 100: `['sgvs', 'treatments', 'mbgs', 'cals', 'devicestatus']`

### Deduplication Methods

| Array | Method | Key |
|-------|--------|-----|
| `treatments` | `nsArrayTreatments()` | `_id` |
| Others | `nsArrayDiff()` | `mills + sgv/mgdl` |

## Events

| Event | Direction | Purpose |
|-------|-----------|---------|
| `dataUpdate` | Server → Client | Delta data broadcast |
| `data-processed` | Internal | Triggers broadcast |
| `authorize` | Client → Server | Authentication |

## Requirements Derived

| ID | Requirement | Source |
|----|-------------|--------|
| REQ-NS-WS-001 | Must broadcast delta updates, not full data | `calcdelta.js` |
| REQ-NS-WS-002 | Must use 2-second dedup window | `websocket.js:310` |
| REQ-NS-WS-003 | Must handle array input sequentially | `websocket.js:305-354` |
| REQ-NS-WS-004 | Must compress broadcasts > 512 bytes | `websocket.js:136` |

## Test Coverage

| Test File | Purpose |
|-----------|---------|
| `tests/websocket.shape-handling.test.js` | Array input behavior |

---

## Nocturne Comparison

Nocturne uses SignalR instead of Socket.IO, with a bridge for legacy client compatibility.

| Aspect | cgm-remote-monitor | Nocturne |
|--------|-------------------|----------|
| Protocol | Socket.IO | SignalR + Bridge |
| Compression | ✅ `.compress(true)` | ❌ Not enabled (GAP-BRIDGE-002) |
| `clients` event | ✅ Broadcasts count | ❌ Not bridged (GAP-BRIDGE-001) |
| Latency | Native | +5-10ms via bridge |

See [Nocturne SignalR Bridge Analysis](../../docs/10-domain/nocturne-signalr-bridge-analysis.md) for details.
