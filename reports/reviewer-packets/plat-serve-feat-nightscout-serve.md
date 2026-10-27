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

# Review packet — PLAT-SERVE (PR #8865)

**`nightscout serve <roles>` (D21): hosted roles carved from bootevent one at a
time, `api` first; each listener bound separately**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feat/nightscout-serve` |
| base | `feat/storage-writes@38b910d7 + feat/nightscout-entrypoint@b63d9b7f (merge 775fd1cb)` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=PLAT-SERVE` is the measurement |
| semver | `minor` |

## What this changes

bin/nightscout.js, lib/server/bootevent.js (the factory chain split by role,
per the components document's table), lib/server/server.js (listener
construction per role).

## Why that semver

new subcommands; `single` unchanged

## What an operator would notice

> Nothing for single-tenant sites. A hoster can start `serve api` without
> the in-memory data layer.

## Who should review this, and why

maintainer, plus a second human - the boot sequence moves

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by the lab, not re-runnable from this repository alone. On
  feat/nightscout-serve 1dafe2a5 against 775fd1cb (Node 22.23.4, MongoDB
  8.0.34): single npm test 4639/0/3 (base 4617), test:all 4967/0/3 (base
  4945), start-paths green. API v3 suites (46 files) under `serve api`: 485
  passing, 81 failing, 168 not run, against 734/0 under single; the failures
  are fixtures that wait for the cache's data-update event (42), call v1
  modules (33) or need socket.io (6), all pieces the api role leaves out. A
  `serve api` boot constructs no bus, ddata, cache, websocket or v1/v2
  (asserted; red when the api profile lists single's stages). Plane rule: 18
  listener tests, each check ablated red. Unknown or unimplemented role
  exits 64; SIGTERM exits 0 in under 10 ms (red: Mongo client left open,
  exit 1 at 10 s).

## Blocked on

`PLAT-ENTRY`, `ST-FILTER-READS`

## Evidence

- [`docs/30-design/tenancy/nightscout-deployable-components-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-deployable-components-2026-09-14.md)

## Notes carried on the item

2026-10-26, later: draft #8865 at 1dafe2a5, stacked on #8863 (base
feat/storage-writes) with #8862 merged in. Env per role: <PREFIX>_HOSTNAME /
_PORT (API_, REALTIME_, TENANT_ADMIN_, ADMIN_); admin defaults to
127.0.0.1:1338 and needs ADMIN_INSECURE_BIND_ACKNOWLEDGED for a non-loopback
bind. Open: per-tenant config after TEN-RESOLVE, ADMIN_BIND vs ADMIN_HOSTNAME,
the admin address rule on any port, /api/v2/authorization under tenant-admin,
migrate owning indexes, one context per process. 2026-10-26 (D21). Open:
whether a composed `serve` of every role is part of the multi target or only a
small-hoster convenience. TEN-RESOLVE (platform admin on its own interface)
depends on this item.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=PLAT-SERVE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
