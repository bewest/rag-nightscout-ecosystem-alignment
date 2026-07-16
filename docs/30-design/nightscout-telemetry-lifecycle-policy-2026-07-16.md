# Nightscout Telemetry Lifecycle Policy

Date: 2026-07-16

## Scope

This policy applies to the sibling `crm-telemetry` service and cgm-remote-monitor aggregate telemetry payloads.

It does not apply to:

- cgm-remote-monitor operational logs.
- OpenTelemetry traces.
- Sentry/GlitchTip crash reports.
- consent-governed data commons or research intake.

## Data classes

| Data class | Example | Retention |
|------------|---------|-----------|
| Raw accepted payload | `raw/accepted/nightscout/YYYY/MM/DD/<receipt>.json` | 60 days |
| Rejected request body | malformed or schema-invalid payload body | Do not store by default |
| Rejection metadata | reason, schema path, timestamp | Optional, short operational retention only |
| Monthly aggregate export | `exports/nightscout/monthly/YYYY-MM.json` | Long-lived public aggregate |
| Dashboard HTML | `reports/nightscout/dashboard.html` | Long-lived public aggregate |
| Service metrics | request counts, schema rejection counts, storage errors | Operational retention per observability backend |
| Service logs | startup, storage error, aggregate job outcome | Avoid IP/user-agent/raw URL/request body; operational retention only |

## Raw accepted payload lifecycle

Raw accepted payloads are retained only to support:

- schema migration repair,
- aggregation replay,
- abuse investigation without retaining network metadata,
- incident response if prohibited data is discovered.

They should expire automatically after 60 days.

For object storage, use lifecycle rules equivalent to:

```text
prefix: raw/accepted/nightscout/
expire_after: 60 days
```

Deployment examples are in `docs/30-design/nightscout-telemetry-deployment-lifecycle-examples-2026-07-16.md`.

## Rejected payload lifecycle

Rejected request bodies should not be stored by default.

If temporary debugging requires rejected-payload retention:

- enable it explicitly,
- store only in a restricted bucket/prefix,
- retain for the shortest practical period,
- redact or avoid request body storage when possible,
- disable it after the incident.

Preferred rejected-event record:

```json
{
  "timestamp": "2026-07-16T20:00:00Z",
  "reason": "schema validation failed",
  "schema_path": "features.used",
  "status": 400
}
```

Do not include IP address, user-agent, hostname, raw URL, authorization headers, query strings, or request body.

## Aggregate exports and dashboards

Aggregate outputs may be long-lived because they do not expose raw installation IDs.

Aggregate outputs must not include:

- raw `installation_id`,
- IP address,
- user-agent,
- hostname,
- raw URL,
- query string,
- request or response body,
- therapy data.

Monthly active installation counts should dedupe by `(month, installation_id)`. Feature-active installation counts should dedupe by `(month, installation_id, counter_name)`. Counter sums are reported separately.

## Incident response

If a prohibited field is accepted:

1. Stop further ingestion if the field can recur.
2. Identify affected raw payloads and aggregate outputs.
3. Delete affected raw payloads.
4. Regenerate aggregate outputs if needed.
5. Record the schema/code fix.
6. Publish a transparency note if public outputs were affected.

## Operational ownership

The Foundation or service operator should name owners for:

- schema review,
- storage lifecycle enforcement,
- dashboard publication,
- incident response,
- access review,
- deployment credentials,
- observability alerts.

## Local prototype status

The local `crm-telemetry` prototype currently implements:

- accepted-payload storage under `raw/accepted/nightscout/YYYY/MM/DD/<receipt>.json`,
- monthly aggregate export generation,
- static dashboard generation,
- tests ensuring raw installation IDs are not included in aggregate exports or dashboard HTML.

It does not yet implement cloud lifecycle rules. Those must be added when the backend target storage provider is chosen.
