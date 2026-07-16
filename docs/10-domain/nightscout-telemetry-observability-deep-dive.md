# Nightscout Telemetry and Observability Deep Dive

Date: 2026-07-16

## Executive summary

Nightscout needs a telemetry and observability plan that helps maintainers make stability, compatibility, release, and infrastructure decisions without turning sensitive diabetes software into a broad analytics product. The practical answer is not one vendor SDK. It is a separated architecture with clear governance:

1. **Community usage telemetry**: a small, public, versioned, locally aggregated feature census for estimated active installations, release adoption, enabled capabilities, and coarse feature use.
2. **Diagnostic observability**: optional or tightly sampled metrics, traces, uptime, exceptions, and performance signals for maintainers and operators.
3. **Operational logging**: local or operator-directed structured logs for incident response on one deployment.
4. **Research and data operations**: a distinct consent-governed data commons path for clinical, product, or machine learning analysis.

This separation is the main unifying design choice. It lets different stakeholders support the same infrastructure while keeping their motivations distinct: maintainers get release stability evidence, the Foundation gets public installation and adoption reports, operators get diagnostics, researchers get a separate consent pathway, and privacy advocates get a narrow default schema with opt-out and payload preview.

## Inputs surveyed

| Source | Relevant findings |
|--------|-------------------|
| `/home/bewest/Downloads/nightscout_telemetry_observability_options.md` | Recommends separate planes for usage telemetry, diagnostic observability, and operational logs; proposes daily aggregate reporting, rotating installation identifiers, strict exclusion of therapy and identity data, OpenTelemetry for optional operational instrumentation, Sentry for scrubbed exceptions, and Grafana/Plausible/Umami style dashboards. |
| `externals/trio-telemetry` | The closest ecosystem precedent: an App-Attest-protected telemetry sink, S3 object storage, daily SQLite/report generation, Prometheus metrics, Loki logs, and Grafana/Scaleway Cockpit alerting. |
| `externals/cgm-remote-monitor-official` | Current Nightscout Heroku manifest includes Papertrail as a deployment log add-on, not product telemetry; the package manifest scan did not find Sentry, OpenTelemetry, Prometheus, Grafana, Datadog, PostHog, Plausible, Umami, or Matomo dependencies. |
| `../ns-ml-data-ops-proposal` | Defines a Foundation data commons, identity, consent, DataOps, MLOps, release support, and shared-service model that telemetry can feed without becoming a research dataset by default. |
| Comparable open-source practice | Home Assistant uses voluntary analytics with public aggregate dashboards and separate Sentry diagnostics. Homebrew uses disclosed analytics for maintainer prioritization with opt-out, public aggregate outputs, and no raw build logs in analytics events. |

Public documentation consulted for comparable patterns:

- Home Assistant analytics integration: `https://www.home-assistant.io/integrations/analytics/`
- Home Assistant public analytics dashboard: `https://analytics.home-assistant.io/`
- Homebrew analytics documentation: `https://docs.brew.sh/Analytics`
- Sentry open-source sponsorship: `https://sentry.io/for/open-source/`
- Grafana open-source stack: `https://grafana.com/oss/`
- Datadog open-source page: `https://opensource.datadoghq.com/`

## What the externals show

### Trio telemetry: strong precedent, different threat model

The workspace pins `trio-telemetry` as an "Anonymous opt-out telemetry sink for Trio, authenticated via Apple App Attest" in `workspace.lock.json:273-277`.

The Trio backend is a Flask telemetry sink that accepts JSON pings from attested Trio iOS installs and writes them to Scaleway Object Storage, with App Attest as the end-to-end authentication mechanism rather than a bearer token (`externals/trio-telemetry/trio-telemetry-backend/README.md:3-9`). Its client protocol has three endpoints: challenge, register, and checkin (`externals/trio-telemetry/trio-telemetry-backend/README.md:14-50`). The checkin payload is capped at 4 KB in code (`externals/trio-telemetry/trio-telemetry-backend/app/main.py:35,84`).

The payload validation requires `idfv` and `installId` (`externals/trio-telemetry/trio-telemetry-backend/README.md:61-62`, `externals/trio-telemetry/trio-telemetry-backend/app/validation.py:6-19`). Storage writes one object per `idfv` per day under `pings/<idfv>/<YYYY-MM-DD>.json` (`externals/trio-telemetry/trio-telemetry-backend/README.md:65-79`, `externals/trio-telemetry/trio-telemetry-backend/app/storage.py:24-26`). The README explicitly notes a 180-day lifecycle because `idfv` is a device identifier (`externals/trio-telemetry/trio-telemetry-backend/README.md:159-160`).

For observability, Trio exposes Prometheus metrics on `/metrics` with an authorization guard and relies on Scaleway Cockpit Prometheus scraping (`externals/trio-telemetry/trio-telemetry-backend/README.md:130-133`, `externals/trio-telemetry/trio-telemetry-backend/app/metrics.py:1-15,45-54`). Logs are written to stdout and optionally shipped to Loki in a non-blocking background thread (`externals/trio-telemetry/trio-telemetry-backend/README.md:135-137`, `externals/trio-telemetry/trio-telemetry-backend/app/logs.py:1-8,125-142`). The canonical request logger emits one structured line per request and increments metrics (`externals/trio-telemetry/trio-telemetry-backend/app/canonical.py:1-18,51-56`). Terraform config manages Grafana/Cockpit sources and a Loki alert rule for sustained 5xx rates (`externals/trio-telemetry/terraform/modules/cockpit/main.tf:15-29,44-58`).

The daily cron job rebuilds SQLite from S3 JSON as source of truth and publishes a self-contained HTML report (`externals/trio-telemetry/trio-telemetry-cronjob/README.md:1-21`). It treats path-derived `idfv` and `day` as authoritative and puts unknown payload keys into `extra` for forward compatibility (`externals/trio-telemetry/trio-telemetry-cronjob/README.md:37-44`, `externals/trio-telemetry/trio-telemetry-cronjob/ingest/etl.py:24-38,130-145`).

**Nightscout implication:** Trio proves that a small open-source telemetry stack can exist inside the ecosystem, but Nightscout should not copy it directly. A server-side Nightscout deployment has a different privacy surface than a mobile app, should count installations rather than "distinct users", and should prefer a stricter schema over Trio's current free-form payload pass-through.

### How Trio's self-hosted telemetry endpoint works

Trio's app-side endpoint is hardcoded to `https://telemetry.triodocs.org`, with a debug override for local testing (`externals/Trio/Trio/Sources/Services/Telemetry/TelemetryClient.swift:17-30`). "Self-hosted" here means the Trio team operates a purpose-built telemetry service rather than embedding a third-party product analytics SDK in the app. It does not mean there is no vendor infrastructure. The backend is packaged as a container and deployed to Scaleway Serverless Containers, with Scaleway Object Storage, Scaleway Cockpit, Prometheus-style metrics, Loki-style logs, and Grafana/Cockpit alerting (`externals/trio-telemetry/trio-telemetry-backend/README.md:3-6`, `externals/trio-telemetry/trio-telemetry-backend/README.md:85-96`, `externals/trio-telemetry/trio-telemetry-backend/README.md:130-137`, `externals/trio-telemetry/terraform/modules/container/main.tf:13-42`, `externals/trio-telemetry/terraform/modules/cockpit/main.tf:15-58`).

The request flow is:

1. Trio asks the backend for a short-lived challenge at `POST /api/auth/ios/challenge` (`externals/trio-telemetry/trio-telemetry-backend/app/routes_auth.py:1-9`).
2. On first use, Trio generates or reuses an Apple App Attest key and registers it with `POST /api/attest/register`; the backend verifies the attestation, challenge, key ID, and app ID before storing the public key (`externals/Trio/Trio/Sources/Services/Telemetry/TelemetryAttestor.swift:1-23`, `externals/trio-telemetry/trio-telemetry-backend/app/routes_attest.py:1-17`, `externals/trio-telemetry/trio-telemetry-backend/app/routes_attest.py:48-105`).
3. For each telemetry send, Trio builds a JSON payload, verifies it is under the 4096-byte cap, obtains a fresh App Attest assertion over `payload || challenge`, and posts to `/checkin` with App Attest headers (`externals/Trio/Trio/Sources/Services/Telemetry/TelemetryClient.swift:303-379`, `externals/trio-telemetry/trio-telemetry-backend/app/main.py:71-129`).
4. The backend validates only minimal required payload shape, currently `idfv` and `installId`, then writes the raw JSON body to `s3://<bucket>/pings/<idfv>/<YYYY-MM-DD>.json` (`externals/trio-telemetry/trio-telemetry-backend/app/validation.py:6-19`, `externals/trio-telemetry/trio-telemetry-backend/app/storage.py:24-26`).
5. A daily Scaleway Serverless Job rebuilds a SQLite snapshot from the S3 JSON source of truth and publishes a self-contained HTML report (`externals/trio-telemetry/trio-telemetry-cronjob/README.md:1-21`, `externals/trio-telemetry/trio-telemetry-cronjob/ingest/etl.py:1-6`).

The security model is app-specific. Apple App Attest is a good fit for an iOS app because it can prove that a checkin came from a genuine app instance on supported Apple hardware. It is not directly reusable for a Node.js Nightscout server process. cgm-remote-monitor would need a different anti-spam and authenticity model, such as local random installation secrets, rate limits, signed daily reports, deployment-specific opt-out controls, and strict server-side schema rejection.

The current Trio design also accepts free-form fields beyond the required identifiers and stores unknown fields for forward compatibility (`externals/trio-telemetry/trio-telemetry-cronjob/ingest/etl.py:27-38`, `externals/trio-telemetry/trio-telemetry-cronjob/ingest/etl.py:130-145`). That is convenient for a small app telemetry program, but Nightscout should use a stricter public schema because server-side deployments have more ways to accidentally expose URLs, tokens, hostnames, therapy-adjacent metadata, or operational context.

**Reuse recommendation:** do not expand the existing `trio-telemetry` endpoint into a general Nightscout endpoint as the first move. Build a sibling Nightscout telemetry service or refactor into a shared multi-product platform only after schemas, identifiers, retention, access controls, and dashboards are product-namespaced. Reuse the proven pattern: small payloads, exact payload preview, non-blocking sends, object-store source of truth, daily aggregation, Prometheus/Grafana/Loki operational observability, and public reports. Do not reuse Trio's App Attest gate, `idfv` semantics, or free-form payload acceptance for cgm-remote-monitor.

### cgm-remote-monitor: logs exist, telemetry does not

The current Nightscout Heroku manifest includes a Papertrail add-on (`externals/cgm-remote-monitor-official/app.json:161-164`). That is operational logging for one deployment, not community usage telemetry. A package manifest scan did not find mainstream observability or product-analytics packages such as Sentry, OpenTelemetry, Prometheus, Grafana, Datadog, PostHog, Plausible, Umami, or Matomo in `externals/cgm-remote-monitor-official/package.json`.

**Nightscout implication:** the first design task is not choosing an SDK. It is defining what the project is allowed to measure, what it must never send, and how telemetry differs from logs.

### Data commons proposal: telemetry as maintainer infrastructure

The adjacent data-ops proposal frames the Nightscout Community Data Commons as a governed platform that turns approved data into quality-scored datasets, release checks, fixtures, reports, and research artifacts without collapsing consent, operations, research, and product claims into one workflow (`../ns-ml-data-ops-proposal/docs/technical-architecture.md:1-38`). It also names "Quality and observability" as a stack layer with Great Expectations or custom checks, OpenTelemetry, and Azure Monitor alternatives (`../ns-ml-data-ops-proposal/docs/technical-architecture.md:47-64`).

The shared-services proposal argues that open-source ecosystem support requires maintenance, security, identity, data governance, release support, operational reliability, and funded operations that individual maintainers cannot reliably provide alone (`../ns-ml-data-ops-proposal/docs/ecosystem-shared-services.md:1-29`). It explicitly includes dependency updates, release-candidate validation, regression reports, conformance vectors, documentation, incident response, and support windows as maintenance/release support (`../ns-ml-data-ops-proposal/docs/ecosystem-shared-services.md:33-43`).

**Nightscout implication:** telemetry should be positioned as one shared-service input to maintainer stability plans and Foundation reporting, not as a hidden research cohort or a replacement for consented data contribution.

## Comparable project patterns

| Project or pattern | What works | Relevance to Nightscout |
|--------------------|------------|-------------------------|
| Home Assistant analytics | Voluntary analytics, public aggregate dashboard, explicit UI controls, 24-hour cadence, exact payload visible in logs, separated basic, usage, statistics, and diagnostics options. Raw per-installation payloads are not public and expire after 60 days without updates. | Strong model for opt-in analytics, public trust, installation-focused wording, and separate diagnostics. Nightscout should be more conservative because technical metadata can imply health context. |
| Homebrew analytics | Disclosed before first send, opt-out possible before collection, public aggregate outputs, fail-fast background send, maintainer-prioritization purpose, no raw build logs in analytics events. | Good precedent for maintainer capacity framing and public aggregate outputs, but Homebrew's default-on posture is less directly transferable to diabetes software. |
| Trio telemetry | App-attested mobile checkins, S3 source of truth, daily SQLite/report generation, Prometheus metrics, Loki logs, Grafana alerts. | Best local implementation reference. Useful for mechanics, but Nightscout needs stricter payload governance and installation rather than device/user semantics. |
| Sentry or GlitchTip | Exception grouping, release regressions, scrubbed stack traces, sampled performance. | Good second phase for diagnostic observability after scrubbers, release tags, and prohibited fields are defined. |
| OpenTelemetry plus Grafana stack | Vendor-neutral instrumentation and replaceable endpoints for metrics/traces/logs. | Good operator and Foundation observability substrate, but too broad for default community telemetry unless attributes are strictly allowlisted. |
| Umami or Plausible | Lightweight privacy-oriented aggregate product analytics. | Fastest path for a small feature census dashboard if wrapped server-side with Nightscout installation semantics. |
| PostHog | Rich cohorts, funnels, feature flags, experiments. | Powerful but high-governance risk. Avoid initially unless stakeholders truly need path/cohort analysis and can disable autocapture, replay, and profiles. |
| Datadog or New Relic | Managed all-in-one APM, logs, metrics, traces, infrastructure views. | Useful if sponsorship is available, but needs careful separation to avoid treating one broad vendor account as the telemetry contract. |

## Stakeholder alignment

| Stakeholder | Motivation | Risk if mixed together | Proposed boundary |
|-------------|------------|------------------------|-------------------|
| cgm-remote-monitor maintainers | Release stability, dependency prioritization, feature deprecation evidence, compatibility support. | Telemetry debates become a referendum on maintainers or a request for broad surveillance. | Use a feature census and release health counters that answer maintainer questions only. |
| Nightscout Foundation | Installation-scale estimates, impact reporting, infrastructure planning, sponsorship evidence. | Foundation reporting could be perceived as patient/user tracking. | Report estimated active installations and aggregate feature-enabled/feature-active installations, not users or patients. |
| Operators and hosted providers | Debugging, uptime, performance, incident response. | Operator logs or traces could accidentally become Foundation telemetry. | Make logs and detailed diagnostics operator-directed and endpoint-replaceable. |
| Researchers and data-ops teams | Consent-governed cohorts, quality scoring, model evaluation, reproducible reports. | Default telemetry could be repurposed into hidden research. | Keep research in a distinct consent/data commons path. Do not include therapy data in default telemetry. |
| Privacy and security reviewers | Minimal data, transparency, opt-out, deletion, incident response. | Open-ended SDKs, raw URLs, traces, stack messages, or browser replay create high-risk leakage. | Use strict schemas, prohibited field tests, payload preview, retention limits, and public transparency reports. |

## Proposed architecture

```text
Nightscout installation
  |
  |-- Community usage telemetry
  |     Daily local aggregate: release, runtime, deployment family,
  |     enabled plugins, coarse feature-use counters, startup status,
  |     status-class counters, monthly rotating installation ID.
  |     Default: candidate for default-on only after public review,
  |     exact payload preview, opt-out, strict schema rejection.
  |            |
  |            v
  |     Foundation-controlled telemetry ingress
  |     Schema validator, short raw retention, aggregate warehouse,
  |     public dashboard and transparency report.
  |
  |-- Diagnostic observability
  |     Optional OpenTelemetry metrics/traces and scrubbed Sentry errors.
  |     Endpoint selected by operator or Foundation program.
  |
  |-- Operational logs
        Structured JSON stdout with stable event codes.
        Remote forwarding only by operator configuration.

Research and ML/DataOps
  Separate consent, identity, intake, provenance, lakehouse,
  MLflow/reporting, and review workflow.
```

## Candidate solution set

### Phase 0: charter and threat model

Create a one-page telemetry charter and reviewed threat model before adding code.

The charter should define:

- Purpose: maintainer stability, release support, compatibility planning, public aggregate adoption reporting.
- Public language: "estimated active installations", "reporting installations", "feature-enabled installations", "feature-active installations".
- Prohibited claims: no "users", "patients", "clinical outcomes", "research participants", or "adherence".
- Prohibited data: glucose, insulin, carbs, treatments, profiles, devicestatus, alarm content, secrets, tokens, URLs with query strings, hostnames, IPs as retained fields, raw user agents, stack messages without review, request/response bodies, browser DOM, screenshots, heatmaps, and replay.
- Governance: public schema, opt-out, payload preview, retention, deletion, subprocessors, incident response, and transparency reporting.

### Phase 1: feature census

Implement a versioned server-side aggregate payload emitted at most once per day. Use local counters and a monthly rotating pseudonymous installation ID.

Minimum payload:

- Schema version.
- Product and release family.
- Node.js major version.
- Deployment family.
- Enabled plugin/capability names.
- Coarse feature-use counters using stable event names.
- Startup success/failure category.
- HTTP status class counters, not raw URLs.
- Monthly rotating installation ID.

This phase can use a small Foundation validation service plus a simple dashboard. Umami, Plausible, or Grafana can be evaluated as dashboard layers, but the Nightscout schema should remain the contract.

### Phase 2: structured logs and event codes

Before remote diagnostics, normalize local logs:

- JSON or logfmt output.
- Stable event codes and component names.
- Route templates instead of raw URLs.
- Duration buckets instead of exact sensitive timing when possible.
- Explicit redaction for secrets, tokens, query strings, bodies, and therapy data.
- Console volume reduction for routine paths.

Remote log forwarding should remain operator-directed, similar to the historical Papertrail role.

### Phase 3: diagnostics and release regressions

Apply for Sentry or GlitchTip style error monitoring only after scrubbers and allowlists exist.

Collect:

- Release-tagged exception fingerprints.
- Component/plugin names.
- Coarse environment labels.
- Sanitized stack frames.
- Sampled performance spans.

Do not collect browser replay, request bodies, raw URLs, environment-variable values, database documents, or user-entered text.

### Phase 4: OpenTelemetry and operator observability

Add OpenTelemetry instrumentation for optional metrics and traces:

- Templated route latency histograms.
- Mongo operation type/duration without query values or documents.
- Startup-stage timing.
- Plugin execution duration.
- WebSocket connection counts and coarse error counters.

Expose operator-selected `OTEL_EXPORTER_OTLP_ENDPOINT` separately from the Foundation telemetry endpoint. Telemetry and OTLP failures must never block startup, requests, or therapy-related data handling.

### Phase 5: Foundation shared-service integration

Connect aggregate outputs to Foundation shared services:

- Release readiness dashboards.
- Dependency and platform support decisions.
- Documentation investment.
- Plugin deprecation or migration planning.
- Community impact reports.
- Data commons recruitment only through a separate consent path.

This phase should publish aggregate dashboards and periodic transparency reports.

## Decision matrix

| Decision | Recommendation | Rationale |
|----------|----------------|-----------|
| One telemetry switch or separated controls | Separated controls: `NIGHTSCOUT_TELEMETRY`, `NIGHTSCOUT_TELEMETRY_ENDPOINT`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `LOG_FORMAT`, `LOG_LEVEL` | Prevents accidental mixing of public feature census, detailed diagnostics, and operator logs. |
| Default terminology | Estimated active installations | "Users" is ambiguous because one instance can represent a person with diabetes, caregivers, clinicians, automated clients, or hosted multi-tenant deployments. |
| Identifier model | Monthly rotating pseudonymous installation identifier | Deduplicates retries and daily reports while avoiding a permanent cross-month identifier. |
| First dashboard | Foundation-controlled schema with Umami/Plausible/Grafana evaluation | Keeps Nightscout semantics independent of vendor data models. |
| Error monitoring | Sentry sponsorship or GlitchTip after scrubbers | Useful for release regressions but unsafe as default broad context collection. |
| OTel | Optional operational plane, not community telemetry contract | Good for portability and operator endpoints, but attributes must be allowlisted. |
| Logs | Local structured logs; remote forwarding operator-controlled | Logs are too detailed and deployment-specific for Foundation default telemetry. |
| Research/data ops | Separate consented data commons | Prevents default telemetry from becoming hidden research infrastructure. |

## Open questions

1. Should Phase 1 be opt-in first, then default-on only after a public schema review and one release cycle of notice?
2. Which deployment-family categories are safe and useful without revealing hostnames or provider identities?
3. Which plugin and route counters should be in the initial allowlist?
4. Should the Foundation run a custom ingress service first, or prototype with Plausible/Umami while preserving a Nightscout-owned schema?
5. What raw retention limit is appropriate for daily aggregate payloads: 30, 60, or 90 days?
6. Which aggregate dashboards should be public from day one?
7. Who owns incident response if telemetry infrastructure receives prohibited data?
8. What governance review is needed before default-on telemetry in a health-adjacent open-source project?

## Bottom line

Nightscout should adopt a methodical telemetry program, not a single analytics tool. The most credible first step is a public telemetry charter plus a daily aggregate installation/feature census. Observability, logs, Sentry-style diagnostics, OpenTelemetry, and the data commons should be connected through shared governance and reporting, but they must remain separate data planes.
