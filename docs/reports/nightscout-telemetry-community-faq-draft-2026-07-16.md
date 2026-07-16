# Nightscout Aggregate Telemetry Community FAQ Draft

Date: 2026-07-16

## What is changing?

Nightscout is preparing a narrow aggregate telemetry feature for cgm-remote-monitor. It would send one small daily summary from a Nightscout installation to a Nightscout/Foundation-operated endpoint.

The goal is to help maintainers understand active installations, release versions, deployment environments, enabled features, coarse API/report use, and startup/server health trends.

## Why does Nightscout need this?

Maintainers are asked to support many hosting environments, APIs, plugins, reports, connectors, and older releases. Today, many decisions rely on anecdotes. Aggregate telemetry can help the community make better maintenance and funding decisions.

There is also time pressure. Third-party cloud access patterns can change or disappear. Knowing which connector and compatibility paths are actively used helps maintainers prioritize before access is lost.

## Is this tracking users or patients?

No. The public denominator should be **estimated active installations**, not users or patients.

One Nightscout installation may represent one person with diabetes, multiple caregivers, automated clients, clinicians, or a hosted deployment. Default telemetry is not designed to count people.

## What will be sent?

The first payload is limited to daily aggregate technical information:

- Nightscout release family.
- Node.js and npm major versions.
- Coarse deployment family and database family.
- Enabled plugin/capability names.
- Coarse counters for API families, reports, and selected plugin activity.
- Startup status, uptime bucket, HTTP status-class counters, websocket count, and startup duration bucket.
- A monthly rotating pseudonymous installation identifier.

The schema is public at `specs/jsonschema/nightscout-telemetry-aggregate.schema.json`.

## What will not be sent?

Nightscout aggregate telemetry will not send glucose, insulin, carbs, treatments, profiles, devicestatus documents, therapy settings, alarms, Nightscout URLs, API secrets, tokens, hostnames, request bodies, logs, stack traces, browser replay, screenshots, or free-form text.

Research and clinical data require a separate consent pathway.

## Can I see exactly what would be sent?

Yes. The implementation plan requires a payload preview. The preview should show the exact JSON object that would be sent before or while telemetry is enabled.

## Can I opt out?

Yes. The plan requires a simple, durable opt-out. Hosted providers and private operators should also be able to replace the endpoint or disable Foundation-directed telemetry.

## Why default-on?

Default-on aggregate telemetry is being considered because the project needs timely installation and feature-use evidence for maintenance budgeting and compatibility planning. This is only acceptable after public schema review and a notice cycle, and because the payload is narrow, public, previewable, easy to opt out of, and rejected server-side if unknown fields appear.

## Where does the data go?

The recommendation is a Nightscout/Foundation-owned sibling telemetry service, separate from Trio telemetry. It may reuse the same operational pattern as Trio telemetry, such as object storage and daily aggregation, but cgm-remote-monitor should have its own schema, endpoint, retention, and dashboard labels.

## How long is raw data retained?

Raw accepted payloads should be retained for 60 days, then aggregate tables should be the source for public reporting.

## Is this the same as Sentry, logs, or OpenTelemetry?

No. Sentry, logs, and OpenTelemetry are diagnostics. They can contain more sensitive operational context and must stay separate from the default feature census.

## What will the public see?

The first public dashboard should show aggregate installation and feature-use information, such as release family distribution, Node.js version distribution, deployment family, enabled features, and coarse health trends. It should not expose raw payloads or installation IDs.

## How does this protect data rights?

Without aggregate evidence, maintenance and policy decisions can be driven by anecdotes, platform pressure, or invisible service-provider data. A narrow public census can help the community advocate for open, interoperable, self-hostable diabetes infrastructure without collecting therapy data or identifying people.
