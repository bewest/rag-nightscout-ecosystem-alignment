# nightscout-connect Architecture Review (2026-07-07)

## Scope

This review updates the earlier `nightscout-connect` design review after the `origin/dev` connector integration pass for 0.0.13. It focuses on additional tests that would increase confidence, architecture recommendations, and lessons from Nocturne and related connector work.

## Current Baseline

`nightscout-connect` now has a real `node --test` suite. The dev branch contains 32 tests covering:

- Dexcom Share auth response shapes, regional endpoints, non-HTTP failures, and timestamp/trend mapping.
- Nightscout source and output fake-server connectivity paths.
- LibreLinkUp region defaults, explicit hosts, multi-patient selection, current readings, missing graph/current payloads, and timestamp handling.
- Glooko regional hosts, configurable device identity, timezone offsets, and v2 CGM reading transforms.

Relevant source references:

- `/home/bewest/src/worktrees/nightscout-connect/package.json:13`
- `/home/bewest/src/worktrees/nightscout-connect/test/dexcomshare.test.js`
- `/home/bewest/src/worktrees/nightscout-connect/test/nightscout-connectivity.test.js`
- `/home/bewest/src/worktrees/nightscout-connect/test/librelinkup.test.js`
- `/home/bewest/src/worktrees/nightscout-connect/test/glooko.test.js`

## Architecture Summary

The core architecture remains sound for a small connector package:

```
source driver -> XState fetch/session/cycle machines -> output driver
```

The builder keeps vendor code mostly separate from XState:

- `builder.support_session()` wires `authenticate`, `authorize`, optional `refresh`, and session delays.
- `builder.register_loop()` wires `dataFromSesssion`, `transform`, `align_schedule`, retry/backoff, and output persistence.

Key files:

- `/home/bewest/src/worktrees/nightscout-connect/lib/builder.js:18-78`
- `/home/bewest/src/worktrees/nightscout-connect/lib/machines/session.js:5-260`
- `/home/bewest/src/worktrees/nightscout-connect/lib/machines/fetch.js:5-354`
- `/home/bewest/src/worktrees/nightscout-connect/lib/machines/cycle.js:5-227`
- `/home/bewest/src/worktrees/nightscout-connect/machines.md:163-184`

## Additional Tests Worth Adding

### P0: Machine-level state transition tests

The new tests validate drivers and HTTP contracts, but not the XState orchestration itself. Add tests for:

| Machine | Test | Why |
|---------|------|-----|
| Session | auth success -> authorize -> active -> reuse | Prevents regressions in token reuse |
| Session | auth reject -> `AUTHENTICATION_ERROR` -> frame failure | Ensures Dexcom/Glooko auth errors surface instead of looping silently |
| Fetch | gap -> fetch -> transform -> persist -> success | Verifies one full frame |
| Fetch | fetch error retries up to `maxRetries` | Guards retry/backoff behavior |
| Cycle | `ALIGN_TO` schedules next run | Guards low-latency CGM polling |

The earlier gap `GAP-CONNECT-004` should now be considered partially remediated: vendor contract tests exist, but machine transition tests do not.

### P0: Golden fixture replay tests

Create fixture directories for each connector and assert the transformed Nightscout batch shape:

```
test/fixtures/dexcomshare/
test/fixtures/librelinkup/
test/fixtures/glooko/
test/fixtures/nightscout/
```

Recommended golden cases:

- Dexcom bare UUID and `{accountId}` auth response.
- Dexcom OUS G7 response with string trend labels.
- LibreLinkUp US, EU, EU2, and explicit server config.
- LibreLinkUp multi-patient account with configured `CONNECT_LINK_UP_PATIENT_ID`.
- Glooko v2 readings with `value` encoded as mg/dL x 100.
- Glooko EU host variants including `eu.api.glooko.com` and `de-fr.api.glooko.com`.
- Nightscout readable source, token URL source, and API-secret token creation source.

### P1: Package-in-Nightscout smoke test

After publishing 0.0.13 or packing locally, test the actual `cgm-remote-monitor` plugin load path:

1. `npm pack` in `nightscout-connect`.
2. Install the tarball into the cgm-remote-monitor candidate worktree.
3. Start Nightscout with `ENABLE=connect` and a fake source/output where possible.
4. Assert boot does not regress and config errors are actionable.

This catches integration issues that package-level tests cannot see.

### P1: International compatibility matrix tests

For each connector, add table-driven validation tests for supported geographies and version knobs:

| Connector | Geography/version knobs |
|-----------|--------------------------|
| Dexcom | `us`, `ous`, explicit `CONNECT_SHARE_SERVER` |
| LibreLinkUp | AE, AP, AU, CA, DE, EU, EU2, FR, JP, US, explicit server, version, product |
| Glooko | default, US, EU, CA, explicit host, Android device identity, future web-login/v3 flags |

### P1: Error diagnostics tests

Nocturne puts user-actionable diagnostics around WAF/auth failures in its Nightscout connector. `nightscout-connect` should add tests for:

- Cloudflare/WAF HTML response from a Nightscout source.
- 401/403 response from source token creation.
- 422 Glooko response with body preserved in logs or error.
- LibreLinkUp no-connections and unmatched-patient errors.

### P2: Idempotency and identifier tests

Before adding v3 output, add tests that define expected identifiers for each source:

- Dexcom entry: source plus Dexcom WT timestamp.
- LibreLinkUp entry: patient plus factory timestamp.
- Glooko entry/treatment: Glooko GUID when present, stable raw timestamp fallback otherwise.

These should become v3 `identifier` inputs later.

## Architecture Recommendations

### 1. Define a formal driver contract

The current source drivers expose similar but informal functions. The misspelling `dataFromSesssion` is now part of the implicit interface. Add a runtime contract validator first, before any TypeScript migration:

```js
{
  validate(input) -> { ok, errors, config }
  authFromCredentials() -> Promise<AuthInfo>
  sessionFromAuth(authInfo) -> Promise<Session>
  dataFromSesssion(session, lastKnown) -> Promise<RawBatch>
  transform(rawBatch, lastKnown) -> NightscoutBatch
  align_to_glucose(lastKnown) -> epochMs | undefined
}
```

This supports `REQ-CONNECT-006` without forcing a large rewrite.

### 2. Split mapping logic from HTTP logic

Nocturne separates connectors into configuration, auth/token provider, service/fetch, mapper, and model classes. `nightscout-connect` can adopt the same separation in JavaScript:

```
lib/sources/glooko/
  auth.js
  client.js
  map-entries.js
  map-treatments.js
  config.js
  index.js
```

This is especially important for Glooko, where v2 API reads, v3 graph reads, web-login CSRF handling, timezone correction, and treatment mapping are currently mixed.

Nocturne references:

- `externals/nocturne/src/Connectors/Nocturne.Connectors.Glooko/Services/GlookoAuthTokenProvider.cs:34-196`
- `externals/nocturne/src/Connectors/Nocturne.Connectors.Glooko/Mappers/GlookoSensorGlucoseMapper.cs:24-75`
- `externals/nocturne/src/Connectors/Nocturne.Connectors.Glooko/Configurations/GlookoConstants.cs:8-184`

### 3. Add connector status and diagnostics

Nocturne tracks successes and failures and exposes connector status APIs. `nightscout-connect` has counters inside the machines but no stable exported status object. Add a small status surface:

```js
{
  source: "glooko",
  state: "running" | "auth_error" | "data_error" | "backoff",
  lastSuccessAt,
  lastErrorAt,
  lastErrorMessage,
  frames,
  frameErrors
}
```

This would help users distinguish "no new data yet" from auth failures, regional endpoint failures, or source API latency.

### 4. Use independent cursors per data type

Nocturne's Nightscout connector explicitly avoids using glucose as the cursor for treatments and device status. `nightscout-connect` currently relies on a small `last_known` bookmark mostly centered on entries. Future multi-collection sources should track independent cursors for:

- entries
- treatments
- devicestatus
- profiles

Nocturne reference:

- `externals/nocturne/src/Connectors/Nocturne.Connectors.Nightscout/Services/NightscoutConnectorService.cs:170-220`

### 5. Treat timezone handling as connector-specific infrastructure

Glooko and LibreLinkUp both expose international timestamp risks. Nocturne has a timezone timeline service for Glooko; `nightscout-connect` currently uses fixed offsets for Glooko and timestamp parsing heuristics for LibreLinkUp.

Near-term recommendation:

- Keep fixed-offset support for compatibility.
- Add optional named timezone config where source APIs provide local wall-clock timestamps.
- Add tests around DST boundaries before changing production mapping.

### 6. Keep broad v3 output work separate

Nightscout v3 output is still the right architectural direction, but it should not be mixed with connector auth fixes. Suggested sequence:

1. Define deterministic identifiers per source.
2. Add v3 output driver behind an option.
3. Add dual v1/v3 contract tests.
4. Only then migrate default output behavior.

This preserves release stability while moving toward `REQ-CONNECT-001` and `REQ-CONNECT-002`.

## What We Would Do Differently Now

If starting over with the current ecosystem knowledge:

1. Start with a test harness and fake HTTP servers before adding vendor code.
2. Require every connector to declare supported geographies, API version knobs, and data types.
3. Separate auth, fetch, mapping, and scheduling modules.
4. Use explicit connector status and user-actionable diagnostics.
5. Store independent cursors per collection.
6. Treat timezones and vendor "fake UTC" timestamps as first-class test cases.
7. Design v3 identifiers before designing v3 output.
8. Keep experimental Glooko web-login/v3 graph work behind a feature flag until fixture coverage exists.

## Release Guidance

For the 0.0.13 cycle, the current `dev` branch is a reasonable release candidate because it improves connectivity without a broad rewrite and has 32 tests. The remaining architectural work should be staged after release:

| Phase | Recommendation |
|-------|----------------|
| 0.0.13 | Release current dev after packaging and cgm-remote-monitor dependency smoke test |
| 0.0.14 | Add XState machine tests and connector status |
| 0.0.15 | Split Glooko into auth/client/mapper modules and add v3 graph/web-login behind flags |
| Later | Add v3 output with deterministic identifiers |

