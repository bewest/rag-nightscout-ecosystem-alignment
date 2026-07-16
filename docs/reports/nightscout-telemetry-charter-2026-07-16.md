# Nightscout Aggregate Telemetry Charter

Date: 2026-07-16

## Purpose

Nightscout aggregate telemetry exists to help maintainers and the Nightscout Foundation make public, evidence-based decisions about cgm-remote-monitor maintenance, release support, compatibility work, documentation, and shared infrastructure.

The first milestone answers narrow questions:

- How many installations are actively reporting during a period?
- Which release families and Node.js major versions remain in use?
- Which coarse deployment families need support?
- Which plugins, APIs, and reports are enabled or exercised?
- Which releases show startup or coarse server-error regressions?

## Non-purpose

Default aggregate telemetry is not:

- A patient registry.
- A user or caregiver count.
- A clinical outcomes dataset.
- A research cohort.
- A marketing lead source.
- A way to contact or identify installations.
- A replacement for consent-governed data commons intake.
- A diagnostic log, trace, crash report, or session replay system.

## Data rights commitment

Nightscout should use telemetry to protect and promote data rights. The project can make stronger claims about open-source maintenance needs when it can publish aggregate installation and feature-use evidence without collecting therapy data or personal identities.

The community should be able to:

- See the schema before activation.
- Preview the exact payload.
- Opt out with one setting.
- Replace the endpoint for private or hosted deployments.
- Review public aggregate dashboards.
- See what data is prohibited.
- Know how long raw accepted payloads are retained.

## Default collection boundary

The first default-on payload is limited to daily local aggregates:

- Product and schema version.
- Release family.
- UTC reporting date.
- Monthly rotating pseudonymous installation identifier.
- Node.js and npm major versions.
- Coarse deployment and database family.
- Enabled plugin/capability names.
- Coarse allowlisted API/report/plugin counters.
- Startup status and coarse health buckets.

The authoritative schema is `specs/jsonschema/nightscout-telemetry-aggregate.schema.json`.

## Prohibited data

Default telemetry must not include:

- Glucose, insulin, carbs, treatments, profiles, devicestatus documents, alarm contents, IOB, COB, basal, bolus, target values, or therapy settings.
- Names, emails, subjects, patient identifiers, caregiver identities, user accounts, clinician identities, or stable browser/device identifiers.
- API secrets, tokens, authorization headers, cookies, MongoDB connection strings, Nightscout URLs, hostnames, query strings, request bodies, response bodies, stack messages, logs, raw user-agent strings, or retained IP addresses.
- Browser DOM, screenshots, heatmaps, session replay, free-form text, or unreviewed breadcrumbs.

## Identifier policy

The default installation identifier must be monthly rotating and pseudonymous. It should be derived locally from a random installation secret and a month label. The local secret must never be transmitted.

This supports deduplication within a reporting month without creating a permanent cross-month installation identity.

## Retention policy

Raw accepted payloads may be retained for up to 60 days for validation, abuse handling, and aggregation repair. Public reporting should rely on aggregate tables. Raw payloads should not be exposed in public dashboards.

## Governance requirements

Before activation, the project should have:

1. Published schema and charter.
2. Payload preview.
3. Opt-out docs.
4. Endpoint replacement docs.
5. Server-side schema rejection for unknown fields.
6. Prohibited-field tests.
7. Named incident owner for prohibited-field receipt.
8. Public aggregate dashboard plan.
9. One notice cycle before default-on activation.

## Separation from diagnostics and research

OpenTelemetry, Sentry/GlitchTip, and remote logs are separate diagnostic planes. They require separate settings, endpoints, scrubbers, and operator or explicit user enablement.

Clinical, research, ML, or data-ops analysis requires separate consent, intake, provenance, and governance.
