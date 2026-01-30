# Trio OpenAPS.swift Bridge Analysis

> **Purpose**: Document Swift↔JS bridge in Trio for algorithm execution  
> **Parent**: [aid-algorithms.md](../sdqctl-proposals/backlogs/aid-algorithms.md) #7  
> **Last Updated**: 2026-01-30

## Executive Summary

Trio uses Apple's JavaScriptCore (JSC) framework to embed the oref algorithm engine directly within the iOS app. The `OpenAPS.swift` file (908 lines) serves as the primary bridge between Swift application code and JavaScript algorithm functions.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Trio iOS App                      │
├─────────────────────────────────────────────────────┤
│  Swift Layer                                         │
│  ┌───────────────────────────────────────────────┐  │
│  │ OpenAPS.swift (908 lines)                      │  │
│  │ - Data preparation (glucose, carbs, history)   │  │
│  │ - JSON serialization                           │  │
│  │ - Result parsing (Determination)               │  │
│  │ - CoreData persistence                         │  │
│  └───────────────────────────────────────────────┘  │
│                        │                             │
│                        ▼                             │
│  ┌───────────────────────────────────────────────┐  │
│  │ JavaScriptWorker.swift                         │  │
│  │ - JSContext pool (5 contexts)                  │  │
│  │ - Script evaluation                            │  │
│  │ - Function calling                             │  │
│  │ - Error handling                               │  │
│  └───────────────────────────────────────────────┘  │
│                        │                             │
├────────────────────────┼────────────────────────────┤
│  JavaScript Layer      ▼                             │
│  ┌───────────────────────────────────────────────┐  │
│  │ bundle/*.js (oref algorithms)                  │  │
│  │ - iob.js, meal.js, autosens.js                 │  │
│  │ - determine-basal.js (main algorithm)          │  │
│  │ - profile.js                                   │  │
│  └───────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────┐  │
│  │ prepare/*.js (wrapper functions)               │  │
│  │ - Exposes generate() function                  │  │
│  │ - Handles input/output marshaling              │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## Key Components

### 1. JavaScriptWorker.swift

The JS engine wrapper provides:

| Feature | Implementation |
|---------|----------------|
| **VM** | Single `JSVirtualMachine` shared across contexts |
| **Context Pool** | 5 pre-created `JSContext` instances |
| **Thread Safety** | `NSRecursiveLock` + `DispatchQueue` |
| **Error Handling** | Exception handler logs to warning |
| **Console Bridge** | `_consoleLog` function for JS→Swift logging |

```swift
final class JavaScriptWorker {
    private let virtualMachine: JSVirtualMachine
    private var contextPool: [JSContext] = []
    
    func inCommonContext<T>(_ work: (Worker) -> T) -> T
    func call(function: String, with args: [Any]) -> RawJSON
    func evaluateBatch(scripts: [Script])
}
```

### 2. OpenAPS.swift Bridge Functions

The main algorithm entry points:

| Function | Purpose | JS Bundle |
|----------|---------|-----------|
| `iob()` | Calculate insulin on board | `bundle/iob.js` |
| `meal()` | Calculate carb absorption | `bundle/meal.js` |
| `autosense()` | Calculate sensitivity ratio | `bundle/autosens.js` |
| `determineBasal()` | Main algorithm loop | `bundle/determine-basal.js` |
| `makeProfile()` | Build profile for algorithm | `bundle/profile.js` |
| `exportDefaultPreferences()` | Get default settings | `bundle/profile.js` |

### 3. Script Loading Pattern

Each algorithm call follows this pattern:

```swift
jsWorker.inCommonContext { worker in
    // 1. Load scripts
    worker.evaluateBatch(scripts: [
        Script(name: Prepare.log),           // Console bridge
        Script(name: Bundle.determineBasal), // Algorithm bundle
        Script(name: Prepare.determineBasal) // Wrapper with generate()
    ])
    
    // 2. Optional middleware
    if let middleware = middlewareScript(name: Middleware.determineBasal) {
        worker.evaluate(script: middleware)
    }
    
    // 3. Call generate() with JSON inputs
    let result = worker.call(function: Function.generate, with: [
        glucoseJSON,
        currentTempJSON,
        iobDataJSON,
        profileJSON,
        ...
    ])
    
    return result
}
```

---

## Data Flow

### Input (Swift → JS)

| Data Type | Source | JSON Key |
|-----------|--------|----------|
| Glucose | CoreData fetch | `glucose` |
| Pump History | CoreData fetch | `pumphistory` |
| Carbs | CoreData fetch | `carbs` |
| Profile | File storage | `profile` |
| IOB | Previous JS call | `iob` |
| Autosens | Previous JS call | `autosens` |
| Preferences | File storage | `preferences` |

### Output (JS → Swift)

The `Determination` struct captures algorithm output:

```swift
struct Determination: Codable {
    var temp: TempType?       // "absolute" or "percent"
    var rate: Decimal?        // Temp basal rate
    var duration: Decimal?    // Duration in minutes
    var units: Decimal?       // SMB units
    var insulinReq: Decimal?  // Total insulin required
    var eventualBG: Int?      // Predicted BG
    var sensitivityRatio: Decimal?
    var reason: String?       // Algorithm explanation
    var predictions: Predictions?  // IOB/COB/UAM/ZT curves
    // ... additional fields
}
```

---

## JavaScript Bundles

Located in `trio-oref/` (embedded at build time):

| Bundle | Lines | Purpose |
|--------|-------|---------|
| `determine-basal.js` | ~2000 | Main loop logic |
| `iob.js` | ~400 | IOB calculation |
| `meal.js` | ~300 | Carb absorption |
| `autosens.js` | ~500 | Sensitivity detection |
| `profile.js` | ~200 | Profile generation |
| `basal-set-temp.js` | ~100 | Temp basal commands |

### Prepare Scripts

Wrapper scripts that expose `generate()`:

```javascript
// prepare/determine-basal.js
function generate(glucose, currentTemp, iob, profile, ...) {
    return freeaps.determine_basal(
        glucose, currentTemp, iob, profile, ...
    );
}
```

---

## Middleware Support

Trio supports custom middleware for algorithm modification:

```swift
private func middlewareScript(name: String) -> Script? {
    storage.retrieveRaw(name + ".js")
}
```

Middleware can intercept and modify algorithm behavior:
- `middleware/determine_basal.js` - Custom basal logic

---

## Async/Await Bridge

Swift async functions wrap JS calls with continuations:

```swift
private func iob(...) async throws -> RawJSON {
    try await withCheckedThrowingContinuation { continuation in
        jsWorker.inCommonContext { worker in
            // ... evaluate and call
            continuation.resume(returning: result)
        }
    }
}
```

---

## CoreData Integration

Algorithm results are persisted to CoreData:

```swift
func processDetermination(_ determination: Determination) async {
    await context.perform {
        let newOrefDetermination = OrefDetermination(context: self.context)
        newOrefDetermination.insulinSensitivity = ...
        newOrefDetermination.eventualBG = ...
        // ... map all fields
        
        // Store prediction curves
        if let predictions = determination.predictions {
            ["iob": predictions.iob, "zt": predictions.zt, 
             "cob": predictions.cob, "uam": predictions.uam]
                .forEach { type, values in
                    let forecast = Forecast(context: self.context)
                    // ... store forecast values
                }
        }
    }
}
```

---

## Identified Gaps

### GAP-TRIO-BRIDGE-001: No Type Safety Across Bridge

**Issue**: JSON serialization loses Swift type information; JS returns untyped objects.

**Impact**: Runtime errors possible if JS output doesn't match expected structure.

**Mitigation**: Trio uses Codable with optional fields for graceful degradation.

### GAP-TRIO-BRIDGE-002: Synchronous JS Execution

**Issue**: JS calls block the context pool; long algorithm runs could exhaust pool.

**Impact**: 5-context pool may bottleneck under heavy load.

**Mitigation**: Pool size configurable; async/await prevents UI blocking.

### GAP-TRIO-BRIDGE-003: Middleware Security

**Issue**: Custom middleware can modify algorithm behavior arbitrarily.

**Impact**: User-installed scripts could produce dangerous dosing decisions.

**Mitigation**: Trio requires explicit user action to enable middleware.

---

## Comparison with Other AID Systems

| System | JS Engine | Bridge Pattern |
|--------|-----------|----------------|
| **Trio** | JavaScriptCore | Direct embedding, context pool |
| **Loop** | None | Native Swift algorithms |
| **AAPS** | None | Native Kotlin (translated from JS) |
| **FreeAPS X** | JavaScriptCore | Similar to Trio (fork origin) |

---

## Key Insights

1. **Embedded Engine**: Trio bundles oref JS directly, avoiding network latency
2. **Async Bridge**: Swift async/await cleanly wraps synchronous JS calls
3. **Middleware Extensibility**: Users can customize algorithm behavior
4. **CoreData Persistence**: All determinations stored for history/upload
5. **Prediction Curves**: 4 curves (IOB, COB, UAM, ZT) extracted and stored

---

## References

- `externals/Trio/Trio/Sources/APS/OpenAPS/OpenAPS.swift` (908 lines)
- `externals/Trio/Trio/Sources/APS/OpenAPS/JavaScriptWorker.swift`
- `externals/Trio/Trio/Sources/APS/OpenAPS/Constants.swift`
- `externals/Trio/trio-oref/` - Bundled oref algorithms
