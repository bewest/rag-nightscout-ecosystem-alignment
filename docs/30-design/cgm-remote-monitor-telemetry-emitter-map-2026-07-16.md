# cgm-remote-monitor Telemetry Emitter Integration Map

Date: 2026-07-16

## Purpose

This document maps where a disabled-by-default aggregate telemetry emitter can integrate into cgm-remote-monitor. It is a technical bridge between the schema/backend materials in this workspace and a future cgm-remote-monitor implementation branch.

The release-gate checklist remains discussable and should not block this technical work. The first code branch should be safe to review because it can run behind `NIGHTSCOUT_TELEMETRY=off` while adding fixtures, tests, payload preview, and implementation scaffolding.

## Proposed first branch scope

Branch name suggestion in the cgm-remote-monitor worktree:

```bash
git checkout -b wip/bewest/nightscout-telemetry-emitter
```

First PR slice:

1. Add a `lib/telemetry/` module with config parsing, allowlists, monthly ID derivation, counter registry, payload builder, and no-op sender.
2. Add tests for schema-shaped payloads, monthly ID rotation, opt-out/default-off behavior, and prohibited counters.
3. Add an admin/API preview endpoint that returns the exact pending payload when telemetry is configured for preview.
4. Do not send network requests by default.

## Configuration touchpoints

### `lib/server/env.js`

`lib/server/env.js` centralizes environment parsing. It already reads basic settings in `config()` and uses helpers such as `readENV` and `readENVTruthy` (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/server/env.js:33-58`, `:191-226`).

Recommended additions:

```js
env.telemetry = {
  mode: readENV('NIGHTSCOUT_TELEMETRY', 'off'), // off | aggregate
  endpoint: readENV('NIGHTSCOUT_TELEMETRY_ENDPOINT', 'https://telemetry.nightscout.foundation/v1/nightscout/checkin'),
  preview: readENVTruthy('NIGHTSCOUT_TELEMETRY_PREVIEW', true),
  idRotation: readENV('NIGHTSCOUT_TELEMETRY_ID_ROTATION', 'monthly')
};
```

Acceptance criteria:

- `off` disables payload sending and scheduling.
- `aggregate` enables payload building and scheduled send after notice/activation.
- Invalid mode records a boot notification or falls back to `off`.
- Endpoint is never included in telemetry payload.

### `lib/settings.js`

Enabled plugins are parsed through `settings.enable`, `settings.DEFAULT_FEATURES`, `enableAndDisableFeatures`, and `isEnabled` (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/settings.js:181`, `:267-280`, `:337-351`). Telemetry should read feature names from `env.settings.enable` but map them through the telemetry schema allowlist before including them.

Acceptance criteria:

- Enabled features are names only.
- Obscured/secure settings are never included.
- Unknown or sensitive plugin names are omitted unless explicitly added to the schema allowlist.

## Startup and lifecycle touchpoints

### `lib/server/server.js`

The server boots env/config, runs boot events, creates the Express app, starts HTTP(S), and initializes websocket handling (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/server/server.js:29-54`, `:71`).

Recommended behavior:

- Create telemetry in the booted callback after `ctx` exists and before or after app creation.
- Attach `ctx.telemetry` before API/app modules are mounted so middleware can increment counters.
- Schedule sending only after successful startup and only when `env.telemetry.mode === 'aggregate'`.
- Close timers on `ctx.bus.on('teardown')`.

### `lib/server/bootevent.js`

Boot events initialize `ctx.runtimeState`, bus, plugins, middleware, storage, and Nightscout Connect (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/server/bootevent.js:17-23`, `:223-251`, `:341-352`). This is the best place to attach a telemetry collector to `ctx` once env and settings are loaded.

Recommended behavior:

- `ctx.telemetry = require('../telemetry')(env, ctx)` during internal setup.
- Record `startup.success`, `startup.config-error`, `startup.database-error`, or `startup.dependency-error` based on boot errors/runtime state.
- Prefer wiring runtime event listeners around `setupListeners`, where the boot chain already attaches `tick`, `data-received`, `data-loaded`, `data-processed`, and `notification` bus listeners (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/server/bootevent.js:293-345`).
- Add teardown cleanup through existing `ctx.bus` lifecycle rather than process-level handlers.

## Request counter touchpoints

### Top-level app mount: `lib/server/app.js`

`lib/server/app.js` mounts static routes, pages, API v1/v2/v3, Pebble, docs, and development middleware (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/server/app.js:184-248`, `:229-248`, `:275-318`).

Recommended behavior:

- Add a telemetry middleware after static assets and before API mounts, or wrap only API/report mounts to avoid high-volume static noise.
- Count only route families allowed by the schema:
  - `api.v1.entries.read`
  - `api.v1.entries.write`
  - `api.v1.status.read`
  - `api.v1.profile.read`
  - `api.v1.devicestatus.read`
  - `api.v1.devicestatus.write`
  - `api.v2.properties.read`
  - `api.v3.entries.read`
  - `api.v3.entries.write`
  - `api.v3.status.read`
  - `api.v3.version.read`
  - `api.v3.last-modified.read`
  - `reports.opened`
- Count status classes using `res.on('finish')`, not request bodies.
- Do not log or store IP, raw URL, query string, user-agent, or request body.

### Middleware registry

`lib/middleware/index.js` centralizes common middleware such as JSON parsing, compression, extension handling, and device-provenance obscuring (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/middleware/index.js:1-30`). Telemetry should initially avoid broad automatic body-parser hooks. A small route-family counter middleware is safer than putting telemetry into shared parsing helpers.

### API v1: `lib/api/index.js`

API v1 enables plugins as Express app features and mounts collection routes (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/api/index.js:23-30`, `:43-65`). This is the clearest place to map v1 routes to allowed telemetry counters.

Route family mapping:

| Route | Methods | Counter |
|-------|---------|---------|
| `/entries*` | GET-like | `api.v1.entries.read` |
| `/entries*` | POST/PUT/DELETE-like | `api.v1.entries.write` |
| `/status*` | any | `api.v1.status.read` |
| `/profile*` | GET-like only | `api.v1.profile.read` |
| `/devicestatus*` | GET-like | `api.v1.devicestatus.read` |
| `/devicestatus*` | POST/PUT/DELETE-like | `api.v1.devicestatus.write` |

Do not count treatment write/read in the first schema. Treatment counters may be considered later only after a separate review because treatment activity is therapy-adjacent even when aggregated.

### API v3: `lib/api3/index.js`

API v3 sets version, enabled collections, status/version/lastModified routes, generic setup, and storage sockets (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/api3/index.js:38-76`, `:78-108`). This is the place to add v3 route-family counters or a telemetry middleware before generic routes.

Initial mapping:

| Route | Counter |
|-------|---------|
| `/version` | `api.v3.version.read` |
| `/status` | `api.v3.status.read` |
| `/lastModified` | `api.v3.last-modified.read` |
| entries generic route read/write | `api.v3.entries.read`, `api.v3.entries.write` |

### Reports and pages

`appPages` maps `/report` to the report UI (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/server/app.js:197-238`). Count `/report` page render as `reports.opened`. Daily/weekly/monthly report counters should only be added when the exact report route/action is identified and allowlisted.

## Websocket health touchpoints

`lib/server/websocket.js` tracks `watchers` and emits client counts on connection/disconnect (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/server/websocket.js:41`, `:155-166`). A telemetry collector can observe connection and disconnect events to update `websocket_connections` or peak/current counters.

Acceptance criteria:

- Count connection totals or coarse current/peak counts only.
- Do not include client IDs, remote IPs, auth state, or socket messages.

## Plugin enabled-state touchpoints

`lib/plugins/index.js` registers server defaults, marks enabled plugins based on `ctx.settings.enable`, exposes `enabledPluginNames`, and exposes `eachEnabledPlugin` (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/plugins/index.js:75-120`, `:129-173`, `:246-262`). This is preferable to hand-parsing `ENABLE` once `ctx.plugins` exists.

Recommended behavior:

- Build `features.enabled` from `ctx.plugins.eachEnabledPlugin` or `env.settings.enable`, filtered through the telemetry schema allowlist.
- Include only plugin names, not plugin settings, extended settings, display settings, or credential-backed configuration.
- Be conservative with therapy-adjacent plugin names. The first schema currently allows names such as `iob`, `cob`, `pump`, and `profile` only as enabled-feature names or allowlisted active plugin counters, not values or documents.

## Payload preview touchpoints

### API v1 status/admin area

`lib/api/status.js` already builds a filtered status response with runtime state and filtered settings (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/api/status.js:17-42`). Preview should not be added to public status by default because the payload includes an installation identifier.

Recommended endpoint:

```text
GET /api/v1/admin/telemetry/preview
```

Use existing authorization/admin patterns near `verifyauth` and `adminnotifiesapi` in `lib/api/index.js` (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/lib/api/index.js:58-60`). The endpoint should require admin permission and return the exact payload that would be sent, plus a disabled/off reason when telemetry is off.

Alternative for first branch:

- Add a CLI/test-only payload builder without mounting an endpoint.
- Add the endpoint in a second PR once maintainers agree on route and permission.

## Test touchpoints

Existing tests use Mocha, `supertest`, and boot helpers. Useful references:

- `tests/api.status.test.js` boots API v1 with `supertest` and checks status formats (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/tests/api.status.test.js:1-80`).
- `tests/settings.test.js` covers env-derived settings, default features, feature disablement, and `isEnabled` behavior (`/home/bewest/src/worktrees/nightscout/cgm-pr-8447/tests/settings.test.js:1-170`, `:248-259`).
- `tests/bootevent-debounce.test.js` isolates boot/listener async behavior and is the pattern for bus-listener tests.
- `tests/reports.test.js` covers report-route conventions.

Recommended first tests:

- `tests/telemetry.config.test.js`: env parsing, default-off, invalid mode.
- `tests/telemetry.id.test.js`: monthly HMAC rotation.
- `tests/telemetry.payload.test.js`: valid schema payload and prohibited counters.
- `tests/telemetry.counters.test.js`: route-family counters without raw URL/query/body.
- `tests/telemetry.preview.test.js`: preview response once route/permission is chosen.

## Proposed module shape

```text
lib/telemetry/
  index.js              # create(env, ctx)
  config.js             # normalize env.telemetry
  id.js                 # local secret + monthly HMAC ID
  counters.js           # allowlisted counters and status-class tracking
  payload.js            # build schema-shaped payload
  sender.js             # async no-op/off by default, later POST
  preview.js            # Express handler
  allowlists.js         # schema-aligned feature/counter names
```

Tests:

```text
tests/telemetry.config.test.js
tests/telemetry.id.test.js
tests/telemetry.payload.test.js
tests/telemetry.preview.test.js
tests/telemetry.sender.test.js
```

## First PR slices

| PR | Scope | Safe because |
|----|-------|--------------|
| 1 | Add telemetry module, ID helper, allowlists, payload builder, unit tests | No app wiring and no network send |
| 2 | Add env parsing and preview-only endpoint behind admin auth | No default send |
| 3 | Add route-family counters and health buckets | Local only, previewable |
| 4 | Add disabled-by-default sender with endpoint config and no-op tests | `NIGHTSCOUT_TELEMETRY=off` remains default for branch work |
| 5 | Add notice/default-on activation only after governance decision | Release gate remains separate |

## Open implementation questions

1. Where should the dedicated telemetry installation secret be persisted for self-hosted deployments without relying on auth secrets?
2. Should the preview endpoint exist in v1 admin APIs, v3 admin APIs, or CLI only at first?
3. Which exact v3 generic route hooks should map to entries read/write counters?
4. Should `api.v1.profile.read` remain in the initial schema, or be removed until maintainers are comfortable with profile-route activity counts?
5. Should `iob`, `cob`, `basal`, and `bolus` enabled-feature names stay in the schema, or should therapy-adjacent plugin names be split into a second reviewed allowlist?

## Identifier source recommendation

cgm-remote-monitor has two existing secret-like values, but neither should become the long-term telemetry identity source:

- `API_SECRET` is stable and operator-specific, but it is user-chosen authentication material. Deriving a public telemetry identifier directly from it would create unnecessary coupling between auth and telemetry, and a known-message HMAC output could become an offline guessing oracle for weak API secrets.
- `node_modules/.cache/_ns_cache/randomString` is generated by `post-generate-keys` and used as the JWT signing key. It is strong random material, but it is build/dependency-cache scoped, can rotate across rebuilds or deploys, and should remain coupled to JWT signing rather than telemetry.

Preferred approach:

1. Use a dedicated telemetry secret, for example `NIGHTSCOUT_TELEMETRY_SECRET`, when an operator or provider wants stable monthly identifiers across deploys.
2. Generate and persist a telemetry-specific secret in a separate telemetry cache file when no explicit secret is configured.
3. Use an ephemeral process secret only if telemetry-specific persistence fails, and label it as ephemeral so reviewers know it is not a stable installation identity.
4. Derive monthly IDs as `HMAC(telemetry_secret, YYYY-MM)`, never transmitting the raw secret.

## Non-blocking next action

Start with PR slice 1 in a cgm-remote-monitor branch: local module, ID derivation, allowlists, payload builder, and tests. This can proceed without resolving default-on release timing.
