# cgm-remote-monitor Telemetry Branch Reviewer Guide

Date: 2026-07-16

Branch: `wip/bewest/nightscout-telemetry-emitter`  
Worktree: `/home/bewest/src/worktrees/nightscout/cgm-pr-8447`

## Branch commits

| Commit | Purpose |
|--------|---------|
| `a8f6c31f` | Adds disabled aggregate telemetry module: config parsing, allowlists, monthly HMAC ID helper, counters, schema-shaped payload builder, no-network facade, and tests |
| `df8b218e` | Adds admin-only telemetry preview endpoint and preview tests |
| `5005aa26` | Keeps telemetry identity separate from API_SECRET/JWT signing material |
| `6555e713` | Adds local route-family and websocket counters without retaining request metadata |
| `c3d6f33d` | Adds manual sender that posts the preview-equivalent payload to `NIGHTSCOUT_TELEMETRY_ENDPOINT` only when explicitly invoked |

## What this branch does

- Parses `NIGHTSCOUT_TELEMETRY`, `NIGHTSCOUT_TELEMETRY_ENDPOINT`, `NIGHTSCOUT_TELEMETRY_PREVIEW`, and `NIGHTSCOUT_TELEMETRY_ID_ROTATION`.
- Parses optional `NIGHTSCOUT_TELEMETRY_SECRET` for stable preview IDs without using `API_SECRET` or the JWT signing random string.
- Defaults telemetry mode to `off`.
- Adds allowlisted feature and counter names.
- Derives monthly rotating pseudonymous installation IDs from a local secret.
- Tracks coarse local counters in memory.
- Builds a schema-shaped aggregate payload.
- Mounts an admin-only preview endpoint at `/api/telemetry/preview.json`.
- Counts allowlisted route families and coarse status classes locally.
- Provides `sendOnce()` for explicit/manual POST tests.
- Adds focused Mocha tests for module behavior and preview authorization.

## What this branch does not do

- Does not automatically schedule or trigger sends.
- Does not persist installation secrets.
- Does not persist daily counters.
- Does not enable default-on telemetry.
- Does not include treatment/profile values, therapy data, URLs, tokens, logs, raw request metadata, IP addresses, or user agents in the payload.

## Why it is safe to review now

The branch is a disabled-by-default implementation scaffold. It makes payload shape and preview behavior reviewable before any activation or network sender exists.

The preview endpoint is admin-only because it exposes the pending installation identifier. It is intended as a trust and verification feature, not a public status endpoint.

## Validation commands run

```bash
TEST=telemetry npm run test-single
npm run test:unit -- --grep telemetry
```

Both passed after `df8b218e`.

Additional local smoke:

```json
{"sent":true,"statusCode":204}
```

This was produced by cgm `sendOnce()` posting to a local `crm-telemetry` receiver.

## Review focus

Reviewers should focus on:

- Whether `NIGHTSCOUT_TELEMETRY=off` remains the safe default.
- Whether allowlisted counters are narrow enough.
- Whether the preview endpoint is correctly admin-protected.
- Whether the payload excludes prohibited fields.
- Whether the telemetry secret stays separate from API_SECRET and JWT signing material.
- Whether manual sender semantics are acceptable before any scheduling or activation work.

## Suggested next branch slices

1. Add local telemetry secret generation/persistence decision and implementation.
2. Add daily counter reset/persistence strategy.
3. Add explicit test/dev-only trigger for local end-to-end testing if maintainers want one.
4. Add scheduling behind explicit `NIGHTSCOUT_TELEMETRY=aggregate`, still off by default until activation is approved.
5. Add notice/preview UX and documentation before any default-on release.
