# nightscout-connect Design Review

> **Date**: 2026-01-29  
> **Source**: `externals/nightscout-connect/`  
> **Version**: 0.0.12  
> **License**: AGPL-3.0-or-later

## Executive Summary

nightscout-connect is a well-architected data synchronization bridge using XState state machines to manage complex async flows. The architecture cleanly separates vendor protocols from sync logic, making it extensible. Key strengths include robust session management, exponential backoff, and schedule alignment. Areas for improvement include testing infrastructure, TypeScript migration, and documentation of the adapter pattern.

---

## Architecture Overview

### Machine Hierarchy

```
Poller (Bus)
├── Session Machine (authentication lifecycle)
└── Cycle Machine(s) (per vendor loop)
    └── Fetch Machine (single data fetch frame)
```

### Data Flow

```
Input (Vendor) → Transform → Output (Nightscout)
     ↓              ↓             ↓
  raw data    entries/treatments  API v1/v3
```

---

## XState Usage Analysis

### Strengths

| Pattern | Implementation | Quality |
|---------|----------------|---------|
| **Hierarchical Machines** | Poller → Session/Cycle → Fetch | ✅ Excellent |
| **Parallel States** | Session + multiple Cycles run concurrently | ✅ Excellent |
| **Service Injection** | Promises mapped via adapter pattern | ✅ Good |
| **Delayed Transitions** | Session expiry, refresh timers | ✅ Good |
| **Parent-Child Communication** | `sendParent()` for events | ✅ Good |
| **Guards** | `shouldRetry` for retry logic | ✅ Good |
| **Context Management** | Session, last_known, diagnostics | ✅ Good |

### Areas for Improvement

| Pattern | Current State | Suggestion |
|---------|---------------|------------|
| **Machine Version** | XState 4.37.1 | Consider XState 5.x migration |
| **TypeScript** | Pure JavaScript | Add type definitions for context/events |
| **Machine Testing** | No tests | Use `@xstate/test` for model-based testing |
| **Visualization** | machines.md manual docs | Generate from machine definitions |
| **Actor Model** | Uses `spawn` but underutilized | Consider actor spawning for parallel fetches |

---

## Vendor Extensibility Model

### Builder Pattern

The `lib/builder.js` provides a fluent API for registering vendors:

```javascript
builder.support_session({
  authenticate: impl.authFromCredentials,
  authorize: impl.sessionFromAuth,
  delays: { REFRESH_AFTER_SESSSION_DELAY, EXPIRE_SESSION_DELAY }
});

builder.register_loop('VendorName', {
  tracker: tracker_for,
  frame: {
    impl: dataFromSession,
    align_schedule: align_to_glucose,
    transform: transformGlucose,
    backoff: { interval_ms },
    maxRetries: 3
  },
  expected_data_interval_ms: 5 * 60 * 1000,
  backoff: { interval_ms }
});
```

### Current Vendors

| Vendor | Source File | Status |
|--------|-------------|--------|
| Nightscout | `lib/sources/nightscout.js` | ✅ Working |
| Dexcom Share | `lib/sources/dexcomshare.js` | ✅ Working |
| Glooko | `lib/sources/glooko/` | ⚠️ Experimental |
| Libre LinkUp | `lib/sources/librelinkup.js` | ⚠️ Needs testing |
| Minimed Carelink | `lib/sources/minimedcarelink/` | ✅ Working |

### Adding a New Vendor

Required exports:
1. `validate(argv)` - Configuration validation
2. `generate_driver(builder)` - Machine registration
3. `impl` object with:
   - `authFromCredentials()` → auth info
   - `sessionFromAuth(authInfo)` → session
   - `dataFromSession(session, last_known)` → raw data
   - `transformGlucose(data, last_known)` → Nightscout format
   - `align_to_glucose(data)` → next fetch time (optional)

---

## Modern Patterns Used

### ✅ Async/Await + Promises

All vendor I/O uses promises, cleanly separated from state machine logic.

### ✅ Exponential Backoff

`lib/backoff.js` implements configurable exponential delay:

```javascript
function backoff(config) {
  return (attempt) => config.interval_ms * Math.pow(2, attempt);
}
```

### ✅ Schedule Alignment

Vendors can align next fetch to expected data arrival time, reducing latency vs fixed intervals.

### ✅ Dependency Injection

Builder pattern injects promises as XState services without vendor code knowing XState.

### ✅ Cookie Jar Support

Uses `axios-cookiejar-support` + `tough-cookie` for session persistence.

---

## Refactoring Suggestions

### 1. Add TypeScript Definitions (Priority: High)

**Problem**: No type safety for machine contexts, events, or vendor interfaces.

**Solution**: Add `.d.ts` files or migrate to TypeScript.

```typescript
interface FetchContext {
  retries: number;
  session: Session | null;
  last_known: LastKnown | null;
  data?: RawData;
  transformed?: NightscoutBatch;
}

type FetchEvent = 
  | { type: 'SESSION_RESOLVED'; session: Session }
  | { type: 'DATA_RECEIVED'; data: RawData }
  | { type: 'FRAME_ERROR' };
```

**Effort**: Medium | **Impact**: High

---

### 2. Add Model-Based Testing (Priority: High)

**Problem**: `"test": "echo \"Error: no test specified\" && exit 1"`

**Solution**: Use `@xstate/test` for machine coverage:

```javascript
import { createModel } from '@xstate/test';

const fetchModel = createModel(fetchMachine).withEvents({
  SESSION_RESOLVED: { exec: async () => { /* mock session */ } },
  DATA_RECEIVED: { exec: async () => { /* mock data */ } },
});

describe('fetch machine', () => {
  const testPlans = fetchModel.getShortestPathPlans();
  testPlans.forEach(plan => {
    plan.paths.forEach(path => {
      it(path.description, async () => {
        await path.test(interpret(fetchMachine).start());
      });
    });
  });
});
```

**Effort**: Medium | **Impact**: High

---

### 3. Migrate to XState 5.x (Priority: Medium)

**Problem**: XState 4.x is in maintenance mode.

**Key Changes**:
- `Machine()` → `createMachine()`
- `actions.assign()` → inline assignment
- Better TypeScript support
- Smaller bundle size

**Effort**: Medium | **Impact**: Medium

---

### 4. Generate Machine Visualization (Priority: Low)

**Problem**: `machines.md` is manually maintained.

**Solution**: Use `@xstate/inspect` or generate Mermaid diagrams:

```javascript
import { toMermaid } from '@xstate/inspect';
console.log(toMermaid(fetchMachine));
```

**Effort**: Low | **Impact**: Low

---

### 5. Standardize Vendor Interface (Priority: Medium)

**Problem**: Adapter pattern in `lib/machines/*.js` preludes is "brittle" (per machines.md).

**Solution**: Define formal interface contract:

```typescript
interface VendorDriver {
  validate(config: Config): ValidationResult;
  authenticate(): Promise<AuthInfo>;
  authorize(auth: AuthInfo): Promise<Session>;
  refresh?(auth: AuthInfo, session: Session): Promise<Session>;
  fetchData(session: Session, gap: GapInfo): Promise<RawData>;
  transform(data: RawData, gap: GapInfo): NightscoutBatch;
  alignSchedule?(data: RawData): Date | null;
}
```

**Effort**: Medium | **Impact**: Medium

---

### 6. Add API v3 Output Support (Priority: High)

**Problem**: `lib/outputs/nightscout.js` uses API v1 only.

**Solution**: Add v3 output with batch operations and history sync:

```javascript
// lib/outputs/nightscoutv3.js
async function persistBatch(batch) {
  await Promise.all([
    api.post('/api/v3/entries', batch.entries),
    api.post('/api/v3/treatments', batch.treatments),
    // ...
  ]);
}
```

**Effort**: Medium | **Impact**: High

---

### 7. Add Metrics/Observability (Priority: Medium)

**Problem**: Limited visibility into sync health beyond console logs.

**Solution**: Emit structured metrics:

```javascript
// Machine context tracks:
context.diagnostics = {
  frames_success: 0,
  frames_failed: 0,
  last_success_at: null,
  last_error: null,
  latency_ms: []
};
```

Expose via HTTP endpoint or push to monitoring.

**Effort**: Medium | **Impact**: Medium

---

## Gaps Identified

### GAP-CONNECT-001: No Test Suite

**Description**: Package has no automated tests despite complex state machine logic.

**Impact**: Regressions possible when adding vendors or upgrading XState.

**Remediation**: Add `@xstate/test` model-based tests + integration tests.

---

### GAP-CONNECT-002: API v1 Only Output

**Description**: Output drivers only support Nightscout API v1, missing v3 features.

**Impact**: Cannot use identifier-based sync, history endpoint, or batch operations.

**Remediation**: Add `lib/outputs/nightscoutv3.js` with API v3 support.

---

### GAP-CONNECT-003: No TypeScript Types

**Description**: Pure JavaScript with no type definitions for machine contexts/events.

**Impact**: Harder to maintain, refactor, or extend safely.

**Remediation**: Add TypeScript or `.d.ts` type definitions.

---

## Requirements Extracted

### REQ-CONNECT-001: Vendor Interface Contract

**Statement**: Each vendor driver MUST implement `validate`, `authenticate`, `authorize`, `fetchData`, and `transform` functions.

**Rationale**: Ensures consistent vendor implementation and enables automated testing.

**Verification**: TypeScript interface or runtime validation.

---

### REQ-CONNECT-002: Backoff on Failure

**Statement**: The system MUST implement exponential backoff on authentication or fetch failures.

**Rationale**: Prevents account lockouts and reduces load on vendor servers.

**Verification**: `frames_missing` increments delay exponentially.

---

### REQ-CONNECT-003: Session Reuse

**Statement**: The system SHOULD reuse active sessions across fetch cycles until expiry.

**Rationale**: Reduces authentication overhead and API calls.

**Verification**: `REUSED_ESTABLISHED_SESSION` event on subsequent cycles.

---

## Source Files Summary

| File | Lines | Purpose |
|------|-------|---------|
| `lib/builder.js` | 89 | Fluent builder for machine composition |
| `lib/machines/poller.js` | 197 | Bus/orchestrator machine |
| `lib/machines/session.js` | 266 | Authentication lifecycle |
| `lib/machines/cycle.js` | ~150 | Periodic fetch loop |
| `lib/machines/fetch.js` | 355 | Single fetch frame |
| `lib/sources/*.js` | varies | Vendor-specific implementations |
| `lib/outputs/*.js` | varies | Nightscout output drivers |
| `machines.md` | 298 | Architecture documentation |

---

## Conclusion

nightscout-connect demonstrates excellent use of XState for managing complex async data synchronization. The architecture is well-designed with clear separation of concerns. Priority improvements should focus on:

1. **Testing** - Add `@xstate/test` for machine coverage
2. **API v3** - Add output driver for modern Nightscout API
3. **TypeScript** - Add type safety for maintainability

The codebase is production-ready but would benefit from these hardening improvements before expanding to additional vendors.

---

## Related Documents

- [Nightscout API v3 Deep Dive](./nightscout-apiv3-deep-dive.md)
- [nightscout-connect Vendor Interop Proposal](../sdqctl-proposals/nightscout-connect-vendor-interop.md)
- [machines.md](../../externals/nightscout-connect/machines.md) - Original architecture docs
