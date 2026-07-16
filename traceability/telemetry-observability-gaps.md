# Telemetry and Observability Gaps

Date: 2026-07-16

## Summary

These gaps track Nightscout telemetry and observability infrastructure needed to support maintainer stability, release planning, Foundation reporting, operator diagnostics, and consent-governed data operations without conflating those motivations.

### GAP-OBS-001: Telemetry, observability, logs, and research data are not separated

**Description**: Nightscout does not yet have a shared architecture that distinguishes community usage telemetry, diagnostic observability, operational logs, and consented research/data-ops flows.

**Affected Systems**: cgm-remote-monitor, Foundation shared services, hosted operators, research/data-ops proposals.

**Impact**: Stakeholders can talk past each other. Maintainer feature census needs, operator debugging, vendor observability, Foundation impact reports, and research data collection may be incorrectly treated as one telemetry decision.

**Remediation**: Define separate data planes, settings, schemas, endpoints, retention policies, and governance responsibilities before implementing telemetry collection.

**Evidence**: `docs/10-domain/nightscout-telemetry-observability-deep-dive.md`; `/home/bewest/Downloads/nightscout_telemetry_observability_options.md`.

### GAP-OBS-002: No Nightscout-owned aggregate feature census schema

**Description**: cgm-remote-monitor has deployment logging patterns but no public, versioned, privacy-reviewed aggregate schema for installation counts, release adoption, enabled plugins, and coarse feature-use counters.

**Affected Systems**: cgm-remote-monitor, Nightscout Foundation reporting, release planning, documentation planning.

**Impact**: Maintainers lack evidence for support windows, deprecations, migration planning, and feature prioritization. Raw anecdotes or vendor-specific dashboards may substitute for a governed public schema.

**Remediation**: Create a strict daily aggregate telemetry schema with a payload preview, prohibited-field validation, and short raw retention.

**Evidence**: `externals/cgm-remote-monitor-official/app.json:161-164`; `docs/10-domain/nightscout-telemetry-observability-deep-dive.md`.

### GAP-OBS-003: Existing ecosystem telemetry precedent is not directly reusable for Nightscout

**Description**: Trio telemetry demonstrates an App-Attest-protected telemetry sink, daily S3 pings, Prometheus metrics, Loki logs, and report generation, but its mobile-app assumptions differ from Nightscout server deployments.

**Affected Systems**: cgm-remote-monitor, Trio telemetry, Foundation shared services.

**Impact**: Copying Trio telemetry directly could import device/user semantics, free-form payload pass-through, and longer raw retention that are not appropriate for Nightscout's default community telemetry.

**Remediation**: Reuse implementation lessons from Trio while designing Nightscout-specific installation semantics, strict schema validation, rotating identifiers, and a narrower default payload.

**Evidence**: `externals/trio-telemetry/trio-telemetry-backend/README.md:3-9`; `externals/trio-telemetry/trio-telemetry-backend/README.md:61-79`; `externals/trio-telemetry/trio-telemetry-backend/README.md:159-160`.

### GAP-OBS-004: Diagnostic tools can be mistaken for public community telemetry

**Description**: Sentry, OpenTelemetry, logs, Prometheus, and Grafana can collect or expose detailed operational context. Without clear boundaries, those tools may be mistaken for the default feature census or used to answer adoption questions.

**Affected Systems**: cgm-remote-monitor, Foundation observability, hosted operators, telemetry vendors.

**Impact**: Detailed traces, stack frames, raw URLs, request context, or logs could leak sensitive deployment or health-adjacent information. Conversely, logs and traces are poor substitutes for a stable feature-adoption census.

**Remediation**: Keep diagnostics explicit, opt-in or operator-directed, with allowlisted attributes, redaction tests, endpoint replacement, and separate settings from `NIGHTSCOUT_TELEMETRY`.

**Evidence**: `externals/trio-telemetry/trio-telemetry-backend/app/metrics.py:1-15`; `externals/trio-telemetry/trio-telemetry-backend/app/logs.py:1-8`; `docs/10-domain/nightscout-telemetry-observability-deep-dive.md`.

### GAP-OBS-005: Telemetry is not yet connected to maintainer stability and shared-service plans

**Description**: Telemetry discussions can be framed as analytics or vendor selection rather than as shared infrastructure for release quality, dependency triage, documentation, data operations, and Foundation support.

**Affected Systems**: cgm-remote-monitor, Nightscout Foundation, data commons, ML/data-ops proposal, maintainer release processes.

**Impact**: Mixed motivations can create conflict. Maintainers may resist telemetry as extra burden, privacy reviewers may see it as hidden research, and Foundation stakeholders may lack evidence for infrastructure investment.

**Remediation**: Publish a phased proposal series linking the telemetry charter, feature census, structured logs, diagnostics, OpenTelemetry, and data commons integration to concrete maintainer and Foundation decisions.

**Evidence**: `../ns-ml-data-ops-proposal/docs/technical-architecture.md:1-64`; `../ns-ml-data-ops-proposal/docs/ecosystem-shared-services.md:1-43`; `docs/10-domain/nightscout-telemetry-observability-deep-dive.md`.

