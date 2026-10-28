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
| base | `official/dev (PR base since the retarget; first stacked on feat/storage-writes@38b910d7 + feat/nightscout-entrypoint@b63d9b7f, merge 775fd1cb)` |
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
- [`tools/lab/image-start-forms/README.md`](../../tools/lab/image-start-forms/README.md)

## Notes carried on the item

2026-10-27 night (maintainer): #8865 joins the 16.0.0 merge list. Only
`single` is supported. Then (maintainer, same night): the subcommand selects
tenancy, so TENANCY_MODE retires; `serve` is reserved for a multitenant
Nightscout and every role, api included, exits 64 until it is multitenant; the
single-tenant api code runs as scripts/headless-test-server.js for tests and
development (not in the image); API3_TEST_TARGET serve-api is renamed
headless. Head b01b77c3 (pushed by the maintainer): API v3 suites 751/0 under
single with and without the change, 643/0/108 pending under headless (MongoDB
7.0.43 with nofile 64000). PR title and body rewritten to match. #8862 is
superseded. Head 53ba192a (README and CLI help say "multitenant roles"); every
check passing; no human review yet. 2026-10-27 night (session -00): #8865 head
f01d67e6, pushed by the maintainer, a fast-forward of 9f7f84f8 (-2e's three
API v3 test commits and a dev merge, folding in the harness above). f01d67e6
fixes CodeQL alert 138 (js/disabling-certificate-validation, high) in
lib/cli/commands/healthcheck.js, present since #8862's commits: the probe set
rejectUnauthorized: false, for its loopback target and for --url alike. Now
its own target requires the certificate SSL_CERT names (the chain verifies
against SSL_CERT, SSL_CA and the system roots; the peer's fingerprint replaces
the hostname check), and --url is checked as any client checks it; an
unreadable SSL_CERT or SSL_CA is unhealthy. Tests: green for the configured
certificate on loopback; red for another certificate on the port
(tests/fixtures/ healthcheck-other.*), an unreadable SSL_CERT and a self-
signed --url, the three failing on 9f7f84f8's healthcheck.js (19/3) and
passing with the fix (22/0). start-paths + CLI 35 passing on MongoDB 8.0; unit
tier 1585/0. CodeQL then marked alert 138 fixed on the PR's merge ref (0 open
alerts; the CodeQL check passes). Image start forms measured the same night
(tools/lab/image-start-forms, 8dd7c563c; dev dcf20bfb against 9bb1f0b4): every
form that started a server on dev starts the same server (status.json
identical apart from server time, one node process, same entrypoint, user,
workdir, no HEALTHCHECK); differences are stop and signals (docker stop 10.1
s/137 to 0.13 s/0; SIGINT and SIGTERM, ignored by node as PID 1 on dev, exit
0), and `nightscout single` and `nightscout healthcheck` working as commands.
Not covered: restart: on-failure after an outside SIGTERM (the site used to
keep running; it now exits 0 and stays down), and tooling matching PID 1's
command line. #8862 is superseded: its four commits are in #8865. 2026-10-27
(maintainer, recorded by session -4f): serve api's scope is v1 + v3 + the v2
summary and authorization + tenant resolution (interface-ownership §4 item 4);
v1 joins once its storage paths run without the cache. Session -2e's
ST-V3-DECOUPLE harness (feat/v3-role-harness 88f37427, three test-only commits
on 9bb1f0b4; single 742/0, serve-api 634/0/108 pending, npm test 4757/0/3, as
reported by -2e) is to be folded into #8865, not stacked. The 15 v3 tests on
v1-created records keep running under serve-api. 2026-10-27 late (from session
-2e; not re-run by the recording session): #8865 head 9bb1f0b4 on official, a
fast-forward of 4d243590 pushed by the maintainer; open, not draft, base dev,
mergeable. Two commits. 9f4bd874: the image keeps the node base entrypoint
with CMD ["nightscout","single"]; an explicit `docker run` command replaces
CMD and is exec'd by docker-entrypoint.sh, so the image no longer routes
explicit commands through the dispatcher (one process, as on dev; env
unchanged; image 52 MB smaller). The dispatcher's passthrough itself stays:
lib/cli/index.js still runs a non-subcommand first argument as a program
(`nightscout node lib/server/server.js`, covered by start-paths). Only the
`version` shorthand without `nightscout` is lost; `nightscout version` works.
9bb1f0b4: lib/server/server.js handles SIGTERM and SIGINT through the bus
teardown and exits 0, bounded at 8 s (exit 1 past it), so every start path
(Procfile, npm start, server.js, the image) gets it. Measured on the image
with MongoDB 7.0: docker stop 10.2 s force-killed (137) on dev, 0.16-0.20 s
exit 0 on 9bb1f0b4, in every start case, with or without a connected websocket
client. npm test 4757/0/3; start-paths 13 passing; the 2 new SIGTERM tests
fail on the parent (death by signal). 2026-10-26, later: draft #8865 at
1dafe2a5, stacked on #8863 (base feat/storage-writes) with #8862 merged in.
Env per role: <PREFIX>_HOSTNAME / _PORT (API_, REALTIME_, TENANT_ADMIN_,
ADMIN_); admin defaults to 127.0.0.1:1338 and needs
ADMIN_INSECURE_BIND_ACKNOWLEDGED for a non-loopback bind. Open: per-tenant
config after TEN-RESOLVE, ADMIN_BIND vs ADMIN_HOSTNAME, the admin address rule
on any port, /api/v2/authorization under tenant-admin, migrate owning indexes,
one context per process. 2026-10-26 (D21). Open: whether a composed `serve` of
every role is part of the multi target or only a small-hoster convenience.
TEN-RESOLVE (platform admin on its own interface) depends on this item.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=PLAT-SERVE` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
