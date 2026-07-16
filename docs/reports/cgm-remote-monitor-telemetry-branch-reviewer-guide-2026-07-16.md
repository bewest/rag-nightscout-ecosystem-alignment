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
| `8a3376f2` | Persists a telemetry-specific generated secret and daily counters, separate from API/JWT secrets |
| `10b63a99` | Adds pure scheduling helper for first-run jitter, weekly success interval, and failure retry |
| `b8149521` | Retains counters across day boundaries until a successful telemetry send, then resets them |
| `4ae99daf` | Adds admin-only, explicitly gated manual send endpoint for local E2E testing |

## What this branch does

- Parses `NIGHTSCOUT_TELEMETRY`, `NIGHTSCOUT_TELEMETRY_ENDPOINT`, `NIGHTSCOUT_TELEMETRY_PREVIEW`, and `NIGHTSCOUT_TELEMETRY_ID_ROTATION`.
- Parses optional `NIGHTSCOUT_TELEMETRY_SECRET` for stable preview IDs without using `API_SECRET` or the JWT signing random string.
- Defaults telemetry mode to `off`.
- Adds allowlisted feature and counter names.
- Adds allowlisted Nightscout Connect source/vendor feature names such as `connect.dexcomshare`, without credentials, URLs, regions, patient IDs, device IDs, or serial numbers.
- Derives monthly rotating pseudonymous installation IDs from a local secret.
- Tracks coarse local counters in memory.
- Builds a schema-shaped aggregate payload.
- Mounts an admin-only preview endpoint at `/api/telemetry/preview.json`.
- Counts allowlisted route families and coarse status classes locally.
- Provides `sendOnce()` for explicit/manual POST tests.
- Mounts `POST /api/telemetry/send.json` only as an admin endpoint and only works when `NIGHTSCOUT_TELEMETRY_MANUAL_SEND=true`.
- Persists a generated telemetry secret in a telemetry-specific cache file when `NIGHTSCOUT_TELEMETRY_SECRET` is not provided.
- Persists counter state since the last successful send.
- Resets counters only after `sendOnce()` receives a successful response.
- Provides pure scheduling helpers, but does not automatically schedule sends.
- Adds focused Mocha tests for module behavior and preview authorization.

## What this branch does not do

- Does not automatically schedule or trigger sends.
- Does not allow manual send unless `NIGHTSCOUT_TELEMETRY_MANUAL_SEND` is explicitly enabled.
- Does not use `API_SECRET` or JWT `randomString` as telemetry identity material.
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
- Whether allowlisted Nightscout Connect source names are acceptable for the first telemetry schema.
- Whether the preview endpoint is correctly admin-protected.
- Whether the payload excludes prohibited fields.
- Whether the telemetry secret stays separate from API_SECRET and JWT signing material.
- Whether manual sender semantics are acceptable before any scheduling or activation work.
- Whether the manual send endpoint should remain test/dev-only or be removed before production activation.
- Whether the telemetry cache location and backup/restore behavior are acceptable for target deployments.

## Suggested next branch slices

1. Decide whether to keep, restrict, or remove the manual send endpoint before production activation.
2. Add scheduling behind explicit `NIGHTSCOUT_TELEMETRY=aggregate`, still off by default until activation is approved.
3. Add notice/preview UX and documentation before any default-on release.
