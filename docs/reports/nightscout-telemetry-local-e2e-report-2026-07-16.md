# Nightscout Telemetry Local E2E Test Report

Date: 2026-07-16

## Summary

Local end-to-end telemetry testing passed across both components:

- cgm-remote-monitor branch `wip/bewest/nightscout-telemetry-emitter`
- crm-telemetry receiver repo `/home/bewest/src/crm-telemetry`

The test booted cgm-remote-monitor in-process, started a real local `crm-telemetry` HTTP receiver, exercised allowlisted cgm routes, called the admin-only manual send endpoint, stored the accepted backend payload, exported monthly aggregates, and rendered a static dashboard.

## Components tested

| Component | Commit or branch | Role |
|-----------|------------------|------|
| cgm-remote-monitor | `wip/bewest/nightscout-telemetry-emitter` through `4ae99daf` | Builds payload, counts route families, exposes preview and gated manual send |
| crm-telemetry | `d0ca8f3` plus storage/export/dashboard commits through `5a37596`/`4b6f25f`/`e42040c` | Validates, stores accepted payload, aggregates, exports, renders dashboard |

## Configuration

cgm environment:

```text
NODE_ENV=test
API_SECRET=test_api_secret_12_chars
MONGO_CONNECTION=mongodb://localhost:27017/testdb
NIGHTSCOUT_TELEMETRY=aggregate
NIGHTSCOUT_TELEMETRY_ENDPOINT=http://127.0.0.1:<ephemeral>/v1/nightscout/checkin
NIGHTSCOUT_TELEMETRY_SECRET=local-full-e2e-secret
NIGHTSCOUT_TELEMETRY_MANUAL_SEND=true
NIGHTSCOUT_TELEMETRY_STORE=<tempdir>
```

crm-telemetry ran as a `ThreadingHTTPServer` with an ephemeral local storage directory.

## Steps executed

1. Started crm-telemetry receiver on `127.0.0.1:<ephemeral>`.
2. Booted cgm-remote-monitor Express app with telemetry aggregate mode and manual send enabled.
3. Exercised:
   - `GET /api/v1/status.json`
   - `GET /api/v3/version`
   - `GET /report`
4. Requested `GET /api/v1/telemetry/preview.json` with admin auth.
5. Requested `POST /api/v1/telemetry/send.json` with admin auth.
6. Verified crm-telemetry returned `204`.
7. Verified one accepted payload was stored under `raw/accepted/nightscout/2026/07/16/<receipt>.json`.
8. Ran monthly export generation.
9. Rendered static dashboard.
10. Checked aggregate export and dashboard did not contain raw monthly installation IDs.

## Observed result

cgm manual send response:

```json
{"sent": true, "statusCode": 204}
```

Stored backend payload:

```text
raw/accepted/nightscout/2026/07/16/2898d2c12b3047df9dcf054201e815f7.json
```

Generated outputs:

```text
exports/nightscout/monthly/2026-07.json
reports/nightscout/dashboard.html
```

Aggregate summary:

```json
{
  "active_installations": 1,
  "counter_sums": {
    "api.v1.status.read": 1,
    "api.v3.version.read": 1
  },
  "feature_active_installations": {
    "api.v1.status.read": 1,
    "api.v3.version.read": 1
  }
}
```

## Assertions covered

- cgm generated a schema-valid aggregate payload.
- cgm manual send endpoint was admin-authenticated and explicitly gated by `NIGHTSCOUT_TELEMETRY_MANUAL_SEND=true`.
- crm-telemetry accepted the cgm payload with `204`.
- crm-telemetry stored exactly one accepted payload.
- monthly export generated one aggregate month.
- dashboard rendered from aggregate export.
- aggregate export and dashboard did not expose raw installation IDs.
- payload did not include URL, token, logs, request body, IP address, or user-agent fields.

## Limitations found

- `/report` did not appear in the preview counters during the full-app E2E run. The likely cause is cgm route/static ordering: static handling or redirect behavior can satisfy `/report` before the current telemetry middleware sees the app-page route. API counters did work. This should be addressed before relying on report-page counters.
- The E2E test used an in-process cgm Express app and a real local crm-telemetry HTTP server, not two long-running shell-managed daemons.
- Automatic scheduling is still not enabled.
- crm-telemetry lifecycle policy is documented separately but not implemented as cloud object-store lifecycle rules.

## Next technical follow-up

1. Fix `/report` counting by instrumenting the app-page handler directly or moving a narrow report counter before static handling.
2. Add a repeatable local E2E script if maintainers want a single command.
3. Implement production lifecycle policy in the chosen storage backend.
4. Add scheduling behind explicit telemetry configuration after review.

