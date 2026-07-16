# Nightscout Telemetry Execution Summary

Date: 2026-07-16

## Status

The telemetry work is **technical prototype feature-complete** for local review. It is **not yet production/default-on complete**.

Primary review links:

- cgm-remote-monitor PR: `https://github.com/nightscout/cgm-remote-monitor/pull/8564`
- crm-telemetry repo: `https://github.com/nightscout/crm-telemetry` (private)
- This document is the consolidated review entry point for the project.

Implemented and tested:

- cgm-remote-monitor telemetry branch with default-off config.
- Admin preview endpoint.
- Gated manual E2E send endpoint.
- Explicit scheduled-send gate.
- Weekly jitter scheduling helper.
- Monthly rotating pseudonymous installation IDs.
- Telemetry-specific secret, counter, and send-state persistence.
- Mongo-backed telemetry state with file fallback for local/dev.
- Route, status, report, websocket, plugin, and allowlisted connector-source counters.
- Explicitly gated scheduled-send path.
- Sibling `crm-telemetry` receiver.
- Strict schema validation.
- Accepted-payload storage.
- Monthly dedupe aggregation.
- Monthly JSON export.
- Static dashboard rendering.
- Full local E2E proof from cgm manual endpoint to crm receiver to storage to export to dashboard.

## Start here

| Reader need | Read this |
|-------------|-----------|
| One-page decision context | [Board/developer packet](nightscout-telemetry-board-developer-packet-2026-07-16.md) |
| Public data-rights posture | [Telemetry charter](nightscout-telemetry-charter-2026-07-16.md) |
| Community-facing explanation | [Community FAQ draft](nightscout-telemetry-community-faq-draft-2026-07-16.md) |
| Buy-vs-build/vendor strategy | [Buy-vs-build strategy](nightscout-telemetry-buy-vs-build-strategy-2026-07-16.md) |
| cgm branch review | [cgm branch reviewer guide](cgm-remote-monitor-telemetry-branch-reviewer-guide-2026-07-16.md) |
| Backend/service review | [Backend service design](../30-design/nightscout-telemetry-backend-service-design-2026-07-16.md) |
| Full local proof | [Local E2E report](nightscout-telemetry-local-e2e-report-2026-07-16.md) |
| Retention/deletion policy | [Lifecycle policy](../30-design/nightscout-telemetry-lifecycle-policy-2026-07-16.md) |
| Deployment lifecycle examples | [Deployment lifecycle examples](../30-design/nightscout-telemetry-deployment-lifecycle-examples-2026-07-16.md) |
| Scheduling/dedupe model | [Scheduling/dedupe model](../30-design/nightscout-telemetry-scheduling-dedupe-model-2026-07-16.md) |
| Schema source of truth | [Nightscout telemetry JSON Schema](../../specs/jsonschema/nightscout-telemetry-aggregate.schema.json) |

## One-page architecture

```text
cgm-remote-monitor
  default-off telemetry config
  admin preview
  allowlisted counters
  monthly pseudonymous installation ID
  Mongo-backed local telemetry state
  explicit manual/scheduled gates
          |
          v
NIGHTSCOUT_TELEMETRY_ENDPOINT
          |
          v
crm-telemetry or compatible receiver
  strict schema validation
  accepted-payload storage with 60-day lifecycle
  monthly dedupe aggregation
  JSON exports
  static dashboard
```

The cgm implementation is vendor-agnostic. It sends a Nightscout-owned JSON payload to a configurable HTTP endpoint. A receiver can be the current private `crm-telemetry` service, a Foundation-operated deployment, a hosted-provider endpoint, or another compatible implementation. cgm source changes should not be required unless a future receiver changes the payload, transport, authentication, or success-response contract.

## Buy-vs-build summary

The strategy is **build the telemetry contract, buy or use commodity infrastructure underneath**. See the [buy-vs-build strategy](nightscout-telemetry-buy-vs-build-strategy-2026-07-16.md) for the full analysis.

| Layer | Strategy | Rationale |
|-------|----------|-----------|
| Schema and payload contract | Build | This is the governance and privacy boundary. Vendors should not define it. |
| cgm emitter | Build | Needs Nightscout config, plugin/source allowlists, preview, opt-out, counters, and scheduling. |
| Receiver validation | Build | Needs strict schema rejection and Nightscout-specific semantics. |
| Raw accepted payload storage | Buy/use object storage | S3-compatible storage with lifecycle rules is commodity infrastructure. |
| Aggregation/export | Build first | Monthly JSON exports are sufficient for initial maintainer/board questions. |
| Dashboard | Build first, Grafana optional | Static dashboard proves the flow; Grafana can be added later if useful. |
| Service metrics/logs | Use managed/open observability | Prometheus/Grafana/Loki-style tooling is appropriate for service health. |
| Error diagnostics | Separate vendor/service | Sentry or GlitchTip can handle crashes/errors, but not default telemetry. |
| Rich product analytics | Avoid initially | PostHog/funnels/cohorts increase governance risk and are not needed for first milestone. |

Vendor/technology posture:

| Option | Role | Current decision |
|--------|------|------------------|
| Scaleway Object Storage / S3-compatible storage | Raw accepted payloads and exports | Good fit, consistent with Trio telemetry precedent |
| AWS S3 / Azure Blob / GCS / Cloudflare R2 | Alternative object storage | Compatible if lifecycle/access controls are available |
| ClickHouse | Scale-up analytics engine | Defer until volume/query needs justify it |
| PostgreSQL/Timescale | Middle-path aggregate store | Optional if JSON exports become insufficient |
| Grafana/Prometheus/Loki | Service observability and dashboards | Good optional infrastructure layer |
| Sentry/GlitchTip | Error diagnostics | Separate opt-in/operator diagnostic plane |
| OpenTelemetry | Portable operational metrics/traces | Separate from community telemetry endpoint |
| Plausible/Umami/Matomo | Privacy-oriented dashboard/product analytics | Possible dashboard layer only, not schema contract |
| PostHog | Funnels/cohorts/feature flags | Avoid for first milestone |
| Datadog/New Relic/Honeycomb | Managed observability | Optional for service/operator observability, not telemetry contract |

## Current branches and repos

| Repo | Branch/commits | Purpose |
|------|----------------|---------|
| cgm-remote-monitor | PR `https://github.com/nightscout/cgm-remote-monitor/pull/8564`; local worktree `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`, branch `wip/bewest/nightscout-telemetry-emitter` | cgm emitter, preview, counters, manual send, scheduling gate |
| crm-telemetry | private repo `https://github.com/nightscout/crm-telemetry`; local repo `/home/bewest/src/crm-telemetry`, branch `main` | receiver, validation, storage, aggregation, export, dashboard |
| alignment workspace | current branch `workspace/clinical-decision-report` | docs, schema, fixtures, planning, traceability |

## cgm branch commit stack

| Commit | Purpose |
|--------|---------|
| `a8f6c31f` | Disabled aggregate telemetry module |
| `df8b218e` | Admin telemetry preview endpoint |
| `5005aa26` | Telemetry identity separated from auth secrets |
| `6555e713` | Local route-family counters |
| `c3d6f33d` | Manual aggregate sender |
| `8a3376f2` | Telemetry-specific secret and counter persistence |
| `10b63a99` | Scheduling helper |
| `b8149521` | Retain counters until successful send |
| `4ae99daf` | Gated manual send endpoint |
| `3254e8a4` | Allowlisted Nightscout Connect source names |
| `ea47d14e` | Direct `/report` counter |
| `5e7a54d4` | Explicit scheduled-send gate |
| `a6825185` | Scheduled send checks wired to the existing tick lifecycle |
| `5969531e` | Mongo-backed telemetry state with file fallback |

## crm-telemetry commit stack

| Commit | Purpose |
|--------|---------|
| `5d58a84` | Minimal receiver |
| `00b079c` | Ignore Python cache artifacts |
| `e42040c` | Monthly aggregation and dedupe |
| `4b6f25f` | Accepted-payload storage |
| `5a37596` | Monthly aggregate exports |
| `d0ca8f3` | Static dashboard |
| `1fa351d` | Nightscout Connect source allowlist |

## What is collected in the first schema

Schema source: [Nightscout telemetry JSON Schema](../../specs/jsonschema/nightscout-telemetry-aggregate.schema.json).

| Field | Example | How derived |
|-------|---------|-------------|
| `schema` | `1` | Constant schema version |
| `product` | `cgm-remote-monitor` | Constant product name |
| `release` | `16.x` | Release family from cgm version |
| `reporting_period` | `2026-07-16` | UTC date of payload build |
| `installation_id` | `monthly_...` | `HMAC(telemetry_secret, YYYY-MM)`, rotates monthly |
| `runtime.node_major` | `22` | `process.versions.node` major |
| `runtime.npm_major` | `10` | npm major when available |
| `runtime.deployment_family` | `docker`, `heroku`, `unknown` | Coarse env detection only, no hostname/app name |
| `runtime.database_family` | `mongodb-atlas`, `mongodb-compatible` | Coarse Mongo URI family, no URI |
| `features.enabled` | `careportal`, `connect.dexcomshare` | Allowlisted plugin/source names only |
| `features.used` | `api.v1.status.read`, `reports.opened` | Allowlisted route/report/plugin/source counters |
| `health.startup` | `success`, `config-error` | Boot/runtime state |
| `health.uptime_bucket` | `1-7d`, `unknown` | Coarse bucket |
| `health.http_2xx/4xx/5xx` | counters | Status class counters only |
| `health.websocket_connections` | counter | Connection count only, no socket/client/IP |

Allowlisted Nightscout Connect source names:

- `connect.dexcomshare`
- `connect.glooko`
- `connect.linkup`
- `connect.minimedcarelink`
- `connect.nightscout`

Representative allowlisted counters:

- `api.v1.entries.read`
- `api.v1.status.read`
- `api.v3.version.read`
- `reports.opened`
- `plugins.connect.active`
- `connect.source.dexcomshare.active`

The schema has `additionalProperties: false` and explicit counter/source allowlists. Fixtures under [`specs/fixtures/telemetry/`](../../specs/fixtures/telemetry/) prove accepted and rejected examples.

## What is not collected

- Glucose, insulin, carbs, treatments, profiles, devicestatus documents, alarm content, IOB, COB, basal, bolus, target values, therapy settings.
- Names, emails, patient/caregiver/clinician identities.
- API secrets, tokens, authorization headers, cookies, MongoDB connection strings, Nightscout URLs, hostnames, query strings, request bodies, response bodies, stack messages, logs, raw user-agent strings, retained IP addresses.
- Browser DOM, screenshots, heatmaps, session replay, free-form text.
- Research or clinical outcome payloads.

Specific connector data that is **not** collected:

- account names,
- passwords,
- API secrets,
- endpoint URLs,
- region-specific hostnames,
- patient IDs,
- device IDs,
- serial numbers,
- timezone offsets.

## How cgm derives and sends data

| Concern | Current behavior |
|---------|------------------|
| Default state | `NIGHTSCOUT_TELEMETRY=off` |
| Preview | Admin-only `/api/telemetry/preview.json` |
| Manual local E2E trigger | Admin-only `POST /api/telemetry/send.json`, requires `NIGHTSCOUT_TELEMETRY_MANUAL_SEND=true` |
| Scheduled send | Requires `NIGHTSCOUT_TELEMETRY_SCHEDULED_SEND=true`; wired to existing tick lifecycle |
| Scheduling cadence | first-run jitter 5 minutes to 7 days; success next due 7 days plus 0 to 24h jitter; failure retry 6 to 24h |
| Persistence | Mongo-backed telemetry state when `ctx.store` is available; file fallback for local/dev |
| Counters | Retained until successful send, then reset |
| Telemetry server outage | Nightscout continues running; send failure records retry state and counters are retained |

## Local E2E proof

The [local E2E report](nightscout-telemetry-local-e2e-report-2026-07-16.md) documents a successful local run:

```json
{"sent": true, "statusCode": 204}
```

The backend then produced:

```text
raw/accepted/nightscout/2026/07/16/<receipt>.json
exports/nightscout/monthly/2026-07.json
reports/nightscout/dashboard.html
```

The E2E report includes commands, assertions, generated artifacts, and limitations.

## Production readiness checklist

Before any opt-in/default-on production activation:

- Confirm `NIGHTSCOUT_TELEMETRY_SCHEDULED_SEND=true` is acceptable for opt-in pilot use.
- Decide whether the manual send endpoint remains, is restricted to test/dev, or is removed.
- Add user/operator notice and opt-out documentation in cgm-remote-monitor.
- Add production deployment/runbook for `crm-telemetry`.
- Apply object-store lifecycle rules for 60-day raw accepted payload retention.
- Confirm dashboard/export outputs do not expose raw installation IDs.
- Confirm backend logs do not retain IP, user-agent, hostnames, raw URL, query string, authorization headers, or request body.
- Review initial allowlists, especially therapy-adjacent plugin names and connector source names.
- Decide whether Mongo collection name/default (`telemetry`) is acceptable.

## Remaining before opt-in/default-on consideration

1. Decide whether `NIGHTSCOUT_TELEMETRY_SCHEDULED_SEND=true` is acceptable for an opt-in pilot.
2. Decide whether to keep, restrict, or remove the manual send endpoint before production.
3. Add user/operator notice and opt-out docs in cgm-remote-monitor.
4. Add production deployment/runbook for `crm-telemetry`.
5. Apply storage lifecycle rules in the chosen production object store.
6. Review the initial allowlists, especially therapy-adjacent plugin names and connector source names.
7. Decide whether the Mongo collection name/default (`telemetry`) is acceptable for production deployments.
