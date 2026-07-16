# Nightscout Telemetry Board and Developer Packet

Date: 2026-07-16

## Decision requested

Approve a first cgm-remote-monitor telemetry milestone and maintenance/shared-infrastructure budget comparable to Trio's telemetry investment.

The first milestone is not broad analytics. It is a narrow aggregate installation and feature census with clear notice, exact payload preview, one-line opt-out, endpoint replacement, strict schema validation, and a 60-day raw accepted payload retention limit. Default-on activation should occur only after public schema review, payload preview, opt-out documentation, and a notice cycle are complete.

## Why now

Nightscout maintainers need installation and feature-use evidence before more third-party cloud access patterns change or disappear. LibreLinkUp is the current example: if third-party access changes before maintainers understand how many installations depend on related connectors and fallbacks, decisions become anecdotal and reactive.

The same evidence supports:

- Maintenance budgeting for cgm-remote-monitor and shared infrastructure.
- Prioritizing compatibility work across connectors, APIs, reports, and deployment families.
- Deprecation and migration planning based on actual installation signals.
- Public transparency about what the project can and cannot support.
- Data-rights-preserving community reporting that avoids patient/user tracking.

## What we will collect first

Only a local daily aggregate payload:

- Nightscout release family.
- Node.js and npm major versions.
- Coarse deployment family and database family.
- Enabled plugin/capability names, without configuration values.
- Coarse feature-use counters for allowlisted API families, reports, and selected plugin activity.
- Startup status, uptime bucket, HTTP status-class counters, websocket connection count, and startup duration bucket.
- Monthly rotating pseudonymous installation identifier.

The draft schema is `specs/jsonschema/nightscout-telemetry-aggregate.schema.json`.
The companion charter is `docs/reports/nightscout-telemetry-charter-2026-07-16.md`.

## What we will not collect

Default telemetry must not include:

- Glucose, insulin, carbs, treatments, profiles, devicestatus documents, alarm contents, IOB, COB, basal, bolus, or target values.
- Names, emails, subjects, patient identifiers, caregiver identities, user accounts, or clinician identities.
- API secrets, tokens, authorization headers, cookies, MongoDB connection strings, Nightscout URLs, hostnames, query strings, request bodies, response bodies, stack messages, logs, raw user-agent strings, or retained IP addresses.
- Browser DOM, screenshots, heatmaps, session replay, free-form text, or unreviewed breadcrumbs.
- Research, clinical outcome, or data commons payloads.

Clinical and research data require a separate consent-governed data commons pathway.

## Community commitment

The default-on posture is only acceptable because the first payload is narrow and community-visible. The project should commit to:

- Publish the schema before activation.
- Show the exact payload in an admin/CLI preview.
- Make opt-out simple and durable.
- Support endpoint replacement for hosted providers and private operators.
- Reject unknown fields server-side.
- Publish aggregate dashboard outputs and periodic transparency summaries.
- Treat prohibited-field receipt as an incident with a named owner.

## Maintainer value

The telemetry dashboard should answer the questions maintainers already face:

| Maintainer question | Telemetry signal |
|---------------------|------------------|
| Which versions still need support? | Release family distribution by reporting installation |
| Which runtime/deployment environments matter? | Node major, npm major, deployment family, database family |
| Which plugins and APIs are active? | Enabled capabilities and coarse use counters |
| Which migrations need more time? | Adoption of v3 APIs, reports, and connector-related features |
| Which releases are unstable? | Startup status and coarse 5xx trends by release |
| Which docs should be improved? | Commonly enabled features and deployment families |

## Developer value

Developers should receive better release support without taking on hidden surveillance obligations:

- One reviewed schema instead of ad hoc analytics fields.
- Non-blocking telemetry that never affects Nightscout startup or request handling.
- No dependency on a product analytics SDK inside cgm-remote-monitor.
- Separate diagnostics for traces, errors, and logs.
- A path to convert aggregate signals into tests, fixtures, docs, and release checks.

## Infrastructure recommendation

Create a sibling `nightscout-telemetry` service rather than widening the existing `trio-telemetry` endpoint.

Reuse the successful operational pattern:

- Containerized validation service.
- Object storage as short-retention source of truth.
- Daily aggregation job.
- Public aggregate dashboard.
- Prometheus/Grafana/Loki-style service observability.

Do not reuse Trio's product assumptions:

- No Apple App Attest for cgm-remote-monitor.
- No Apple `idfv`.
- No free-form payload acceptance.
- No "distinct users" denominator.

## First milestone deliverables

1. Telemetry charter and public schema.
2. cgm-remote-monitor local aggregate emitter design.
3. Payload preview and opt-out design.
4. Sibling ingestion endpoint architecture.
5. Daily aggregation and dashboard design.
6. Community FAQ and announcement draft.
7. Implementation task breakdown with owners and review gates.

## Recommended board resolution language

Approve a first Nightscout aggregate telemetry milestone for cgm-remote-monitor that funds maintainer and shared-infrastructure work comparable to Trio's telemetry effort. The milestone will collect only a strict, locally aggregated installation and feature census with monthly rotating pseudonymous installation identifiers, 60-day raw accepted payload retention, public schema review, exact payload preview, durable opt-out, endpoint replacement, and separate consent pathways for research or clinical data.
