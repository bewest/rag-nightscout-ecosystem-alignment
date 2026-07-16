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
| One-page decision context | `docs/reports/nightscout-telemetry-board-developer-packet-2026-07-16.md` |
| Public data-rights posture | `docs/reports/nightscout-telemetry-charter-2026-07-16.md` |
| Community-facing explanation | `docs/reports/nightscout-telemetry-community-faq-draft-2026-07-16.md` |
| Buy-vs-build/vendor strategy | `docs/reports/nightscout-telemetry-buy-vs-build-strategy-2026-07-16.md` |
| cgm branch review | `docs/reports/cgm-remote-monitor-telemetry-branch-reviewer-guide-2026-07-16.md` |
| Backend/service review | `docs/30-design/nightscout-telemetry-backend-service-design-2026-07-16.md` |
| Full local proof | `docs/reports/nightscout-telemetry-local-e2e-report-2026-07-16.md` |
| Retention/deletion policy | `docs/30-design/nightscout-telemetry-lifecycle-policy-2026-07-16.md` |
| Deployment lifecycle examples | `docs/30-design/nightscout-telemetry-deployment-lifecycle-examples-2026-07-16.md` |
| Scheduling/dedupe model | `docs/30-design/nightscout-telemetry-scheduling-dedupe-model-2026-07-16.md` |
| Schema source of truth | `specs/jsonschema/nightscout-telemetry-aggregate.schema.json` |

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

- Release family.
- Node.js and npm major versions.
- Coarse deployment/database family.
- Enabled plugin names from an allowlist.
- Allowlisted Nightscout Connect source names.
- Coarse route/report/plugin/source counters.
- Startup/uptime/status-class/websocket health buckets.
- Monthly rotating pseudonymous installation ID.

## What is not collected

- Glucose, insulin, carbs, treatments, profiles, devicestatus documents, alarm content, IOB, COB, basal, bolus, target values, therapy settings.
- Names, emails, patient/caregiver/clinician identities.
- API secrets, tokens, authorization headers, cookies, MongoDB connection strings, Nightscout URLs, hostnames, query strings, request bodies, response bodies, stack messages, logs, raw user-agent strings, retained IP addresses.
- Browser DOM, screenshots, heatmaps, session replay, free-form text.
- Research or clinical outcome payloads.

## Local E2E proof

`docs/reports/nightscout-telemetry-local-e2e-report-2026-07-16.md` documents a successful local run:

```json
{"sent": true, "statusCode": 204}
```

The backend then produced:

```text
raw/accepted/nightscout/2026/07/16/<receipt>.json
exports/nightscout/monthly/2026-07.json
reports/nightscout/dashboard.html
```

## Remaining before opt-in/default-on consideration

1. Decide whether `NIGHTSCOUT_TELEMETRY_SCHEDULED_SEND=true` is acceptable for an opt-in pilot.
2. Decide whether to keep, restrict, or remove the manual send endpoint before production.
3. Add user/operator notice and opt-out docs in cgm-remote-monitor.
4. Add production deployment/runbook for `crm-telemetry`.
5. Apply storage lifecycle rules in the chosen production object store.
6. Review the initial allowlists, especially therapy-adjacent plugin names and connector source names.
7. Decide whether the Mongo collection name/default (`telemetry`) is acceptable for production deployments.
