# Nightscout Telemetry Buy-vs-Build Strategy

Date: 2026-07-16

## Recommendation

Use a **build-first telemetry contract** with selective vendor use underneath.

Nightscout should own:

- the payload schema,
- prohibited-field policy,
- installation terminology,
- opt-out/preview behavior,
- raw retention policy,
- aggregate/dashboard semantics.

Vendors can provide infrastructure layers, but no vendor product should define the Nightscout community telemetry contract.

## Separation of concerns

| Need | Recommended approach |
|------|----------------------|
| Community feature census | Build Nightscout-owned schema and receiver |
| Receiver/runtime hosting | Buy/use managed container or serverless platform |
| Raw accepted payload storage | Buy/use object storage with lifecycle rules |
| Monthly aggregate analytics | Build first; consider ClickHouse/Postgres if volume grows |
| Static dashboard | Build first; use Grafana later if useful |
| Service metrics/logs | Use Prometheus/Grafana/Loki-style stack or managed equivalent |
| Crash/error diagnostics | Sentry/GlitchTip separately, opt-in/operator-directed |
| Product funnels/cohorts | Avoid initially; reconsider PostHog only with strong governance |
| Research/data ops | Separate consented data commons, not default telemetry |

## Build components

### Nightscout aggregate schema

Build and own. This is the governance contract.

Current source of truth:

```text
specs/jsonschema/nightscout-telemetry-aggregate.schema.json
```

### cgm-remote-monitor emitter

Build inside cgm-remote-monitor because it needs:

- env/config integration,
- plugin/source allowlists,
- admin preview,
- opt-out behavior,
- local counters,
- local scheduling,
- strict no-therapy-data boundaries.

### crm-telemetry receiver

Build as a small service because the public boundary needs:

- strict schema validation,
- rejected-field handling,
- receipt IDs,
- no retained network metadata,
- Nightscout-specific aggregate semantics.

The current prototype is `/home/bewest/src/crm-telemetry`.

## Buy or managed-service candidates

### Object storage: buy

Use S3-compatible object storage for raw accepted payloads and exports.

Candidates:

- Scaleway Object Storage, consistent with Trio telemetry precedent.
- AWS S3.
- Azure Blob Storage.
- Google Cloud Storage.
- Cloudflare R2.

Selection criteria:

- lifecycle expiration for `raw/accepted/nightscout/` after 60 days,
- private raw bucket/prefix,
- public or publishable aggregate/report prefix,
- low operational burden,
- auditability and access controls.

### Container/serverless hosting: buy

Candidates:

- Scaleway Serverless Containers, consistent with Trio telemetry.
- Azure Container Apps.
- AWS App Runner, Lambda, or ECS Fargate.
- Google Cloud Run.
- Fly.io or Render for prototypes.

Selection criteria:

- simple deployment,
- private environment variables/secrets,
- logs/metrics controls,
- low idle cost,
- regional/data-processing fit.

### ClickHouse: defer

ClickHouse is a strong candidate if aggregate analytics outgrow JSON/SQLite/Postgres.

Best fit:

- high-volume event analytics,
- fast dashboards over many payloads,
- multi-dimensional feature adoption queries.

Why defer:

- first payload volume should be small,
- monthly aggregate JSON is enough for initial board/maintainer questions,
- running ClickHouse adds operational surface.

Decision: **do not start with ClickHouse**, but keep it as a scale-up path after usage volume is known.

### PostgreSQL/Timescale: possible middle path

Best fit:

- relational monthly aggregates,
- operational dashboards,
- easier administration than ClickHouse for small teams.

Decision: useful if JSON exports become insufficient, but not required for the first prototype.

### Grafana stack: buy/use selectively

Grafana, Prometheus/Mimir, Loki, and Tempo are good for service observability and dashboards.

Use for:

- receiver health,
- request rates,
- schema rejection counts,
- storage errors,
- dashboard visualization if static HTML is insufficient.

Do not use as the primary schema contract.

### Sentry or GlitchTip: buy/use separately

Best fit:

- exceptions,
- release regressions,
- scrubbed stack traces,
- sampled performance diagnostics.

Use separately from default aggregate telemetry. Do not mix Sentry payloads with feature census data.

### OpenTelemetry: use as optional diagnostics

Best fit:

- operator-selected metrics/traces,
- portable diagnostics,
- route latency and storage operation spans.

Not best fit:

- default community feature census.

Decision: keep `OTEL_EXPORTER_OTLP_ENDPOINT` separate from `NIGHTSCOUT_TELEMETRY_ENDPOINT`.

### Plausible, Umami, Matomo: buy/use only as dashboard layer if needed

Best fit:

- privacy-oriented web/product analytics dashboards.

Concern:

- website/session concepts do not map cleanly to Nightscout installations.

Decision: possible for dashboards only if wrapped by Nightscout-owned server-side schema. Do not embed browser analytics.

### PostHog: avoid initially

Best fit:

- funnels, cohorts, product paths, feature flags.

Concern:

- encourages richer person/event modeling than Nightscout should collect by default,
- autocapture/session replay/profile concepts are poor defaults for health-adjacent software.

Decision: avoid for first milestone.

### Datadog/New Relic/Honeycomb: optional observability vendors

Best fit:

- managed APM, logs, metrics, traces.

Concern:

- broad automatic collection can accidentally mix diagnostics and telemetry,
- proprietary backend dependence,
- cost if sponsorship changes.

Decision: suitable for service/operator observability only, not as the telemetry contract.

## Build versus buy decision matrix

| Layer | Build | Buy/use | First milestone decision |
|-------|-------|---------|--------------------------|
| Schema | Yes | No | Build |
| cgm emitter | Yes | No | Build |
| Receiver validation | Yes | No | Build |
| Raw storage | No | Yes | Use object storage |
| Lifecycle expiration | No | Yes | Use storage lifecycle |
| Aggregation | Yes | Later optional DB | Build JSON exporter |
| Dashboard | Yes initially | Grafana optional | Build static dashboard |
| Service metrics | Minimal code | Prometheus/Grafana optional | Build metrics later |
| Error diagnostics | No | Sentry/GlitchTip optional | Separate future plane |
| Product analytics | No | Plausible/Umami/PostHog optional | Avoid initially |
| Research data | Separate build | Data commons infra | Out of scope |

## Board-facing strategy

Fund the telemetry work as shared infrastructure:

1. Build the governance-sensitive contract in the open.
2. Use managed commodity infrastructure for hosting/storage/lifecycle where it reduces maintainer burden.
3. Keep diagnostics and research separate.
4. Publish aggregate outputs so telemetry protects data rights rather than creating a private surveillance asset.

