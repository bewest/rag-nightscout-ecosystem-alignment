# Nightscout Telemetry Implementation Breakdown

Date: 2026-07-16

## Scope

This breakdown turns the cgm-remote-monitor telemetry plan into implementation work. It assumes:

- Default-on aggregate telemetry after notice and public schema review.
- Minimal aggregate census only for the first milestone.
- Monthly rotating pseudonymous installation ID.
- Raw accepted payload retention of 60 days.
- Sibling `nightscout-telemetry` service, separate from Trio telemetry.
- Separate diagnostics for Sentry/OpenTelemetry/log forwarding.

## Workstream A: Charter, schema, and review gate

| Task | Output | Acceptance criteria |
|------|--------|---------------------|
| A1. Public charter | One-page telemetry charter | Purpose, prohibited data, opt-out, retention, incident owner, and dashboard commitment are explicit |
| A2. JSON Schema | `specs/jsonschema/nightscout-telemetry-aggregate.schema.json` | Strict schema with `additionalProperties: false`, examples, and prohibited-field rejection |
| A3. Community copy | FAQ and announcement draft | Explains default-on aggregate telemetry, opt-out, exact payload preview, and no therapy data |
| A4. Review checklist | Release gate checklist | Defines what must be true before default-on activation; it should not block fixtures, tests, prototype branches, or disabled-by-default implementation work |

## Workstream B: cgm-remote-monitor aggregate emitter

| Task | Output | Acceptance criteria |
|------|--------|---------------------|
| B1. Configuration | `NIGHTSCOUT_TELEMETRY`, endpoint, preview, ID rotation settings | Defaults and opt-out are documented; tests cover off/aggregate behavior |
| B2. Installation secret | Local random secret storage | Secret is generated locally, never transmitted, and used only to derive monthly IDs |
| B3. Monthly ID derivation | HMAC-based identifier helper | Same ID within a month, different across months, deterministic in tests |
| B4. Feature registry | Allowlisted feature and counter names | Counters cannot include raw URL, query, body, treatment/profile values, or arbitrary names |
| B5. Counter collection | In-memory daily counters | API/report/plugin counters are route-template or feature level only |
| B6. Payload builder | Schema-shaped payload | Validates against schema and excludes prohibited fields |
| B7. Preview endpoint/CLI | Exact pending payload preview | Admin/CLI view renders the same payload the sender would transmit |
| B8. Sender | Async daily send | Startup and request handling are never blocked; failure retries naturally next day |
| B9. Tests | Unit and integration tests | Cover opt-out, monthly rotation, schema validity, no prohibited fields, and send failure behavior |

## Workstream C: nightscout-telemetry backend

| Task | Output | Acceptance criteria |
|------|--------|---------------------|
| C1. Service skeleton | Containerized validation service | Health check, structured logs, metrics, config, and deployment docs |
| C2. Checkin endpoint | `POST /v1/nightscout/checkin` | Accepts only valid schema payloads and rejects unknown fields |
| C3. Abuse controls | Payload size and rate limits | Invalid, oversized, and high-rate requests are rejected without storing payload; IP/user-agent may be used transiently for rate limiting but are not retained as telemetry fields |
| C4. Object storage | Date/product partitioned raw accepted payloads | Raw accepted payloads expire after 60 days; object keys and metadata exclude IP address, user-agent, hostname, raw URL, and provider account identifiers |
| C5. Aggregation job | Daily aggregate tables | Counts installations, versions, features, runtime/deployment families, and health buckets |
| C6. Dashboard | Static HTML or Grafana dashboard | Publishes aggregate installation and feature-use views; dashboards exclude raw installation IDs and network metadata |
| C7. Transparency export | Downloadable summary tables | Public aggregate CSV/JSON output excludes raw installation IDs, IP addresses, user agents, hostnames, and raw request metadata |
| C8. Backend tests | Validation and aggregation tests | Prove strict schema rejection and correct aggregate counts |

## Workstream D: Diagnostics separation

| Task | Output | Acceptance criteria |
|------|--------|---------------------|
| D1. OTel plan | Optional `OTEL_EXPORTER_OTLP_ENDPOINT` design | Separate from community telemetry endpoint |
| D2. Sentry/GlitchTip plan | Scrubbed exception plan | Explicit opt-in/operator-directed, no request bodies or therapy data |
| D3. Structured logs | JSON/logfmt guidance | Local stdout by default, remote forwarding operator controlled; Foundation ingress logs avoid retained IP, raw user-agent, hostname, raw URL, query string, and request body fields |
| D4. Redaction tests | Prohibited context checks | Secrets, URLs, headers, bodies, and therapy data are scrubbed before export |

## Workstream E: Maintainer workflow and budget support

| Task | Output | Acceptance criteria |
|------|--------|---------------------|
| E1. Board packet | Board/developer decision packet | Maintenance budget ask, urgency, data-rights framing, and first milestone scope are clear |
| E2. Dashboard questions | Maintainer decision map | Dashboard fields map to support windows, deprecations, docs, and release checks |
| E3. Triage workflow | Monthly review procedure | Maintainers can convert aggregate findings into issues, docs, or compatibility tests |
| E4. Shared infrastructure budget | Budget line-item narrative | Connects cgm-remote-monitor maintenance, telemetry, backend operations, and dashboards |

## Suggested first implementation order

1. Merge charter, schema, board packet, and implementation breakdown.
2. Prototype schema validation with sample accepted and rejected payloads.
3. Implement cgm-remote-monitor ID derivation and payload builder behind `NIGHTSCOUT_TELEMETRY=off`.
4. Add preview endpoint/CLI and tests.
5. Build backend checkin endpoint and object-store writer.
6. Add daily aggregation and first static dashboard.
7. Ship a notice/preview-capable release first, then switch default-on aggregate telemetry only after public review, opt-out docs, and the notice cycle are complete.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Prohibited data accidentally enters payload | Strict schema, allowlisted counters, tests, preview, server-side rejection |
| Community perceives telemetry as tracking | Installation terminology, exact payload preview, opt-out, public dashboard, no therapy data |
| Endpoint becomes runtime dependency | Non-blocking sender, delayed send, natural retry, no request-path dependency |
| Vendor/service coupling | Nightscout-owned schema and endpoint replacement |
| Budget is approved without operations owner | Board packet names shared infrastructure and maintenance responsibilities |
| Diagnostics get mixed with feature census | Separate settings, endpoints, docs, and implementation workstreams |
| Auth secrets get coupled to telemetry | Use a dedicated telemetry secret or generated telemetry-specific persisted secret, not API_SECRET or the JWT randomString cache |
