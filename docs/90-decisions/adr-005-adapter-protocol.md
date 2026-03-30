# ADR-005: Cross-Validation Adapter Protocol

## Status

Accepted

## Date

2025-03-30

## Context

We need to verify that different implementations of the same dosing algorithm
(oref0 in JavaScript, Swift, and Kotlin; Loop in Swift×2) produce equivalent
outputs given identical inputs. Each implementation lives in a different
language runtime with different data types, JSON serialization, and build
systems.

Key forces:

- **Language diversity**: JS (Node.js), Swift (SPM), Kotlin (JVM/Gradle)
- **Runtime isolation**: Each adapter must run in its native environment
- **Schema evolution**: New algorithms and fields are added over time
- **Comparison granularity**: We need to compare not just final decisions
  but intermediate values (prediction curves, eventualBG, IOB arrays)
- **Test reproducibility**: Same vector must produce deterministic results

## Decision

We will use a **JSON-over-stdio adapter protocol** where each algorithm
implementation is wrapped in a thin adapter process that:

1. Reads a JSON request from stdin (`{mode, algorithm, input}`)
2. Translates the language-agnostic input to native types
3. Executes the algorithm
4. Translates native output back to the standardized output schema
5. Writes a JSON response to stdout

Each adapter is defined by a `manifest.json` declaring its capabilities,
invocation command, supported modes, and tolerances.

The protocol supports three modes:
- **execute**: Run the algorithm and return decision + predictions
- **validate-input**: Show how the adapter translates input to native format
- **describe**: Return adapter metadata and capabilities

Schemas are defined in `tools/test-harness/contracts/`:
- `adapter-input.schema.json` — input contract
- `adapter-output.schema.json` — output contract
- `adapter-manifest.schema.json` — adapter metadata

## Consequences

### Positive

- **Language-agnostic**: Any language that can read/write JSON to stdio works
- **Process isolation**: Adapter crashes don't affect the harness
- **Deterministic**: No shared state between invocations
- **Debuggable**: `validate-input` mode shows exactly what native code receives
- **Extensible**: New adapters added by creating a directory with manifest.json

### Negative

- **Process overhead**: ~50ms startup per invocation (acceptable for 100 vectors)
- **Translation layer risk**: Each adapter has its own `translateInput()` which
  could introduce bugs (mitigated by `validate-input` mode)
- **No streaming**: Entire input/output must fit in memory

### Neutral

- Adapters can be invoked directly for debugging: `echo '{}' | node adapter.js`
- The protocol is synchronous per-invocation but harness can parallelize

## Alternatives Considered

### A: Shared library / FFI binding

Compile all implementations to a shared library and call via FFI.

**Rejected because**: Swift Package Manager doesn't easily produce shared
libraries for non-Apple platforms. Kotlin requires JNI. The impedance
mismatch between type systems would be worse than JSON serialization.

### B: HTTP microservice per adapter

Each adapter runs as an HTTP server, harness sends requests.

**Rejected because**: Unnecessary complexity for batch processing. Adds
port management, lifecycle management, and HTTP overhead. stdio is simpler
and sufficient.

### C: Compile everything to WebAssembly

Use WASM as the common runtime.

**Rejected because**: Swift-to-WASM toolchain is immature. Would lose
native runtime behavior that we're specifically trying to validate.

## Related

- `tools/test-harness/contracts/` — JSON schemas
- `tools/test-harness/adapters/` — Adapter implementations
- `tools/test-harness/lib/adapter-protocol.js` — Protocol handler
- `docs/architecture/cross-validation-harness.md` — Harness architecture
- ADR-006: Continuance bypass in cross-validation
