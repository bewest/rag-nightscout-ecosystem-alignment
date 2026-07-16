# Telemetry and Observability Requirements

Date: 2026-07-16

## Summary

These requirements define a privacy-conservative telemetry and observability architecture for Nightscout. They are intentionally scoped to infrastructure and governance, not clinical or research data collection.

### REQ-OBS-001: Separate telemetry data planes

**Statement**: Nightscout MUST distinguish community usage telemetry, diagnostic observability, operational logs, and consent-governed research/data-ops flows as separate data planes.

**Rationale**: Each plane answers different questions, has different privacy risks, and needs different governance.

**Scenarios**: A maintainer wants feature adoption counts; an operator wants request latency traces; a researcher wants consented datasets; a user wants telemetry disabled.

**Verification**: Configuration, documentation, and code paths expose separate settings and endpoints for usage telemetry, OpenTelemetry diagnostics, and logs.

**Related Gaps**: GAP-OBS-001, GAP-OBS-004.

### REQ-OBS-002: Default telemetry payload is strictly aggregate and allowlisted

**Statement**: Default community telemetry MUST use a public versioned schema with allowlisted aggregate fields only and MUST reject unexpected fields server-side.

**Rationale**: A health-adjacent project cannot rely on policy alone to prevent overcollection.

**Scenarios**: A plugin attempts to add a raw treatment count by type; an error path tries to include a stack message; a developer adds a raw URL. The validator rejects the payload.

**Verification**: Schema tests prove that therapy data, secrets, raw URLs, hostnames, IPs as retained fields, request bodies, and arbitrary properties are rejected.

**Related Gaps**: GAP-OBS-002, GAP-OBS-003.

### REQ-OBS-003: Telemetry reports installations, not users or patients

**Statement**: Public telemetry reporting MUST use installation-oriented terms such as estimated active installations, reporting installations, feature-enabled installations, and feature-active installations.

**Rationale**: A Nightscout instance may represent one person with diabetes, caregivers, clinicians, automated clients, or a hosted multi-tenant deployment. "Users" is an unsafe denominator.

**Scenarios**: A dashboard summarizes monthly active reporting; a Foundation report cites feature adoption; a deprecation proposal estimates remaining usage.

**Verification**: Public dashboards, docs, and generated reports avoid "users" unless a separate reviewed identity model supports the measurement.

**Related Gaps**: GAP-OBS-002, GAP-OBS-003.

### REQ-OBS-004: Installation identifiers are pseudonymous and rotate

**Statement**: If Nightscout needs deduplication, the default telemetry identifier SHOULD be a monthly rotating pseudonymous installation identifier derived locally from a random secret.

**Rationale**: Identifier-free reports are hardest to deduplicate, while permanent identifiers create unnecessary longitudinal tracking.

**Scenarios**: An installation retries a daily report; an installation sends daily reports throughout a month; a new month begins.

**Verification**: The same installation produces the same identifier within a month and a different identifier across months; the raw local secret is never transmitted.

**Related Gaps**: GAP-OBS-002.

### REQ-OBS-005: Telemetry failures are non-blocking

**Statement**: Telemetry, diagnostics, and log forwarding failures MUST NOT delay startup, block requests, or affect therapy-related data handling.

**Rationale**: Stability is a safety and trust property. Telemetry infrastructure cannot become a runtime dependency for Nightscout operation.

**Scenarios**: The telemetry endpoint is unavailable; DNS fails; a vendor quota is exhausted; an operator blocks outbound telemetry.

**Verification**: Tests or fault-injection checks show Nightscout starts and serves requests when telemetry endpoints fail.

**Related Gaps**: GAP-OBS-001, GAP-OBS-004.

### REQ-OBS-006: Operators can replace diagnostic endpoints

**Statement**: Nightscout SHOULD provide endpoint replacement for community telemetry and independent endpoint replacement for OpenTelemetry diagnostics.

**Rationale**: A service provider, clinic, researcher, or private operator may need to route diagnostics to their own backend without sending detailed data to the Foundation.

**Scenarios**: A Foundation endpoint receives only aggregate feature census payloads; a hosted provider routes OTLP traces to its own backend; an operator disables Foundation telemetry but keeps local logs.

**Verification**: `NIGHTSCOUT_TELEMETRY_ENDPOINT` and `OTEL_EXPORTER_OTLP_ENDPOINT` are independent, documented, and tested.

**Related Gaps**: GAP-OBS-001, GAP-OBS-004.

### REQ-OBS-007: Detailed diagnostics require scrubbing and explicit enablement

**Statement**: Detailed diagnostics such as stack traces, traces, browser diagnostics, and remote logs MUST be scrubbed and SHOULD be opt-in or operator-directed.

**Rationale**: Diagnostic tools can collect request context, environment details, and user-controlled text that are inappropriate for default community telemetry.

**Scenarios**: Sentry captures an exception; OpenTelemetry records a route span; structured logs are shipped to an operator backend.

**Verification**: Scrubber tests remove secrets, query strings, request bodies, raw database documents, free-form text, and therapy data before export.

**Related Gaps**: GAP-OBS-004.

### REQ-OBS-008: Governance is published before default-on collection

**Statement**: Nightscout MUST publish the telemetry purpose, schema, prohibited fields, retention, access controls, opt-out path, payload preview, incident procedure, and transparency reporting plan before any default-on telemetry release.

**Rationale**: Default-on collection can be defensible only when the community can review exactly what is collected and why.

**Scenarios**: A release candidate includes telemetry; a user wants to inspect the payload; a prohibited field is reported; the Foundation publishes an annual aggregate report.

**Verification**: Release checklist includes public schema review, documented opt-out, payload preview, retention policy, and incident response owner.

**Related Gaps**: GAP-OBS-001, GAP-OBS-005.

### REQ-OBS-009: Data commons uses a separate consent pathway

**Statement**: Clinical, research, ML, or data-ops analysis MUST use a separate consent, intake, provenance, and governance pathway from default community telemetry.

**Rationale**: Default telemetry is for maintainer and infrastructure decisions, not a hidden research cohort.

**Scenarios**: A research team wants de-identified exports; a model pipeline needs therapy data; a Foundation report cites installation counts.

**Verification**: Data commons intake records consent receipts and provenance, while default telemetry schemas exclude therapy and identity data.

**Related Gaps**: GAP-OBS-001, GAP-OBS-005.

