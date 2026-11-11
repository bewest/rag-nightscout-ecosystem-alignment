<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — MT-INTERNAL-LISTENER

**Internal listener: one serve.internal per role (Ory pattern, socket default)
and graceful shutdown with a deadline**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/internal-listener-20261110` |
| base | `official/workspace/multitenant-20261102@b70ad83fa4cdaeb7e6023137a05bd811d7db606a` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-INTERNAL-LISTENER` is the measurement |
| semver | `n/a` |

## What this changes

Replace per-contract socketPathEnv/endpoint config (internal-api/endpoint-
config.js and its three callers) with serve.internal host/port/socket plus
NS_SERVE_INTERNAL_* overrides; peers get NS_*_INTERNAL_URL; transport close()
waits for in-flight responses up to a deadline.

## Why that semver

unreleased preview

## Who should review this, and why

maintainer

## What was measured

**`node bin/with-env.js ./tests/ci.test.env node_modules/mocha/bin/mocha.js --fail-zero --timeout 10000 --require`** &nbsp;·&nbsp; kind: `unit` &nbsp;·&nbsp; cwd: `externals/work/crm-internal-listener-20261110`

Listener config, shutdown and role-contract planning: 18 passing on 78ecba76.
Compose run: held caller received its response (5000 ms deadline); early-drop
control red.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-ENDPOINT-TRANSPORT`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)
- [`reports/tenancy/internal-listener-2026-11-10/README.md`](../../reports/tenancy/internal-listener-2026-11-10/README.md)

## Notes carried on the item

Decisions internal-listener-ory-pattern and internal-listener-graceful-
shutdown (2026-11-10). 2026-11-10 (reproduced in lane): 78ecba76 on b70ad83f.
serve.internal {socket}|{host,port}, NS_SERVE_INTERNAL_*, socket default
<runtime>/<roles>.sock; peers NS_<ROLE>_INTERNAL_URL|SOCKET defaulting to
sockets; contracts fixed per role in internal-listener.js; endpoint-config.js
and openControl removed. Join: ownership-operations must be added to
OWNED/plan() for admin. 2026-11-10: joined into codex/batch-join-20261110
16a1fc2d (MT-BATCH-JOIN-1110), accepted, not pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-INTERNAL-LISTENER` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
