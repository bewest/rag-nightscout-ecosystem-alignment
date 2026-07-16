# Nightscout Telemetry Backend Service Design

Date: 2026-07-16

## Purpose

This design describes a sibling `nightscout-telemetry` service for cgm-remote-monitor aggregate telemetry. It is inspired by `externals/trio-telemetry`, but it does not widen Trio's endpoint or reuse Trio's App Attest, `idfv`, or free-form payload assumptions.

The service accepts only strict aggregate telemetry payloads that validate against `specs/jsonschema/nightscout-telemetry-aggregate.schema.json`.

## High-level architecture

```text
cgm-remote-monitor installation
  daily aggregate JSON
  monthly rotating installation ID
  no therapy data, no URL/token/logs
          |
          v
POST /v1/nightscout/checkin
  schema validation
  payload size limit
  transient abuse controls
  no retained IP/user-agent fields
          |
          v
object storage raw/accepted/nightscout/YYYY/MM/DD/<uuid>.json
  60-day lifecycle
          |
          v
daily aggregation job
  installation counts
  version/runtime/deployment counts
  feature-enabled and feature-active counts
  coarse health buckets
          |
          v
public aggregate dashboard and summary exports
```

## Service boundaries

| Plane | Service behavior |
|-------|------------------|
| Community telemetry | Accepted by `POST /v1/nightscout/checkin` only if schema-valid and under size limits |
| Diagnostics | Service exposes its own health, metrics, and logs, but does not ingest cgm-remote-monitor traces/logs |
| Operator logs | Out of scope for this endpoint |
| Research/data commons | Out of scope; must use separate consented intake |

## API

### `POST /v1/nightscout/checkin`

Accepts a single aggregate telemetry payload.

Request:

- `Content-Type: application/json`
- Body must validate against `nightscout-telemetry-aggregate.schema.json`
- Maximum body size: 8 KB

Responses:

| Status | Meaning |
|--------|---------|
| `204` | Accepted and stored |
| `400` | Malformed JSON, schema violation, unknown field, or oversized payload |
| `415` | Unsupported content type |
| `429` | Rate limited |
| `500` | Internal storage or service error |

Server behavior:

- Reject unknown fields.
- Reject unallowlisted counter names.
- Reject prohibited top-level fields such as `entries`, `treatments`, `profile`, `url`, `token`, `logs`, or `request_body`.
- Use IP/user-agent only transiently for request handling or abuse controls. Do not write them to raw payloads, object metadata, aggregate tables, dashboards, or retained application logs.
- Generate a server receipt ID for logs and object key naming. Do not use the installation ID as the object key by itself.

### `GET /healthz`

Returns service health and git SHA.

### `GET /metrics`

Prometheus-compatible service metrics. Protect in production with bearer token or provider-managed scrape controls.

Suggested metrics:

- `nightscout_telemetry_http_requests_total{path,status}`
- `nightscout_telemetry_checkin_outcome_total{outcome}`
- `nightscout_telemetry_payload_bytes_bucket`
- `nightscout_telemetry_schema_rejections_total{reason}`
- `nightscout_telemetry_storage_errors_total`

## Storage layout

Object storage should separate raw accepted payloads, aggregates, and public reports:

```text
raw/accepted/nightscout/YYYY/MM/DD/<receipt_id>.json
raw/rejected/nightscout/YYYY/MM/DD/<receipt_id>.json        # optional, metadata-free and short retention
aggregates/nightscout/daily/YYYY-MM-DD.json
aggregates/nightscout/monthly/YYYY-MM.json
reports/nightscout/YYYY-MM-DD.html
exports/nightscout/daily/YYYY-MM-DD.json
exports/nightscout/monthly/YYYY-MM.json
```

Raw accepted payload retention: 60 days.

Rejected payload retention should be avoided by default. If temporarily enabled for debugging, store only rejection reason and schema path, not the raw request body.

Object metadata must not include:

- IP address.
- Raw user-agent.
- Hostname.
- Raw URL.
- Query string.
- Authorization header.
- Provider account identifiers.

## Aggregation model

Daily aggregation reads raw accepted payloads and writes aggregate records.

Prototype implementation: `/home/bewest/src/crm-telemetry` commit `e42040c` adds `crm_telemetry.aggregate.aggregate_payloads()`, which dedupes monthly active installations and feature-active installations without exposing raw installation IDs.

Suggested aggregate tables or JSON sections:

| Aggregate | Key dimensions | Measures |
|-----------|----------------|----------|
| Active reporting installations | date, month | distinct monthly installation IDs |
| Release adoption | date/month, release | distinct installations |
| Runtime adoption | date/month, node_major, npm_major | distinct installations |
| Deployment family | date/month, deployment_family, database_family | distinct installations |
| Feature enabled | date/month, feature_name | distinct installations |
| Feature active | date/month, counter_name | sum, distinct installations with count > 0 |
| Startup status | date/month, startup | distinct installations |
| Health buckets | date/month, uptime_bucket, startup_duration_bucket_ms | distinct installations |
| HTTP status classes | date/month, release | sum of 2xx/3xx/4xx/5xx |

Monthly reports should not link an installation across months. The monthly rotating identifier supports within-month deduplication only.

## Dashboard outputs

First dashboard:

- Estimated active reporting installations by day and month.
- Release family distribution.
- Node.js major version distribution.
- Deployment family and database family.
- Top enabled plugins/capabilities.
- Top active counters.
- Startup status and uptime buckets.
- Coarse 5xx trend by release family.

Public dashboards must not expose:

- Raw payloads.
- Raw installation IDs.
- IP addresses.
- User agents.
- Hostnames.
- Raw URLs.
- Single-installation drilldown.

## Validation and tests

Backend tests should include:

- Valid minimal payload accepted.
- Valid typical payload accepted.
- Unknown top-level field rejected.
- Prohibited top-level `entries` rejected.
- Prohibited `url` rejected.
- Unallowlisted counter `api.v1.treatments.write` rejected.
- Free-form plugin counter `plugins.token.active` rejected.
- Oversized body rejected before storage.
- Invalid content type rejected.
- Accepted object stored without network metadata.
- Aggregation counts distinct monthly installation IDs.
- Aggregation does not link installation IDs across months.
- Aggregation dedupes duplicate weekly reports by `(month, installation_id)` for monthly active counts.
- Feature-active installation counts dedupe by `(month, installation_id, counter_name)` while counter sums remain separate.

The repository-level fixture validator is `tools/validate_telemetry_schema.py`.

## Operational inspiration from Trio telemetry

Reusable ideas from `externals/trio-telemetry`:

- Small containerized validation service.
- Object storage as source of truth.
- Daily rebuildable aggregate snapshot.
- Self-contained HTML reports or Grafana dashboards.
- Prometheus metrics.
- Structured canonical request logs.
- Loki/Grafana alerting for service health.

Nightscout-specific differences:

- No App Attest.
- No Apple `idfv`.
- No free-form payload pass-through.
- Strict JSON Schema rejection.
- Installation terminology, not user/device terminology.
- Endpoint replacement for hosted providers and private operators.
- Separate research/data commons pathway.

## Initial repository shape

When implemented, a sibling service could use:

```text
nightscout-telemetry/
  app/
    main.py
    config.py
    validation.py
    storage.py
    metrics.py
    canonical.py
  ingest/
    aggregate.py
    report.py
  schemas/
    nightscout-telemetry-aggregate.schema.json
  tests/
    test_validation.py
    test_storage.py
    test_aggregation.py
  Dockerfile
  README.md
```

Python/FastAPI or Flask is acceptable because Trio telemetry already uses Flask successfully. Node/Express is also acceptable if maintainers prefer to share language/runtime with cgm-remote-monitor. The schema and storage contract matter more than framework choice.

## Non-blocking next actions

1. Keep refining schema fixtures and validation tests in this repository.
2. Prototype the backend validation endpoint against these fixtures.
3. Prototype the cgm-remote-monitor payload builder behind a disabled flag.
4. Keep release-gate language under discussion without blocking fixtures, tests, or disabled-by-default implementation branches.
