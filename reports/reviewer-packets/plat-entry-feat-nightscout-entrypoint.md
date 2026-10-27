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

# Review packet — PLAT-ENTRY (PR #8862)

**One executable (D21): bin/nightscout.js with `single` and the operator tools;
image ENTRYPOINT and CMD single, no image HEALTHCHECK; no start path changes**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `feat/nightscout-entrypoint` |
| base | `official/dev@8dbb60c2` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=PLAT-ENTRY` is the measurement |
| semver | `minor` |

## What this changes

New bin/nightscout.js and a package.json "bin" entry; Dockerfile
ENTRYPOINT/CMD/HEALTHCHECK. lib/server/server.js stays the implementation of
`single`, so Procfile, npm start, server.js, web.config (iisnode) and start.sh
are untouched.

## Why that semver

Adds a command and an image health check; no existing behaviour changes.

## What an operator would notice

> Nothing changes for a site started the old way. Docker images gain a
> health check, and `nightscout diagnose data` / `nightscout version` can be
> run inside the container.

## Who should review this, and why

maintainer

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured by the lab, not re-runnable from this repository alone (needs
  MongoDB and a crm tree). On feat/nightscout-entrypoint b63d9b7f (dev
  8dbb60c2): npm test 4509/0/3 (dev 4480/0/3), test:all 4837/0/3 at 4c7d678d
  (dev 4808/0/3), Node 22.23.4. tests/start-paths.test.js boots seven start
  paths as processes and deep-compares each with `nightscout single` (three
  ablations of the single mapping red); unknown subcommand exits 64;
  healthcheck red before start, green while running, red after stop; env
  redacts five planted secrets (red without redact()); the image has no
  HEALTHCHECK (asserted, red when one is added).

## Evidence

- [`docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)
- [`docs/30-design/tenancy/nightscout-deployable-components-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-deployable-components-2026-09-14.md)

## Notes carried on the item

2026-10-26, later: draft #8862 opened at 4c7d678d; b63d9b7f removed the image
HEALTHCHECK after the maintainer asked whether it would hide the boot-error
page. It would: a site that boots with errors serves that page as a 500, and
swarm or autoheal would restart it in a loop. `nightscout healthcheck` stays
as an opt-in command and names the boot-error page. Open in the PR: PATH
passthrough outside the image, `docker run <image> env`, SIGTERM handling,
307-to-https as healthy. 2026-10-26: the maintainer chose one executable with
subcommands, the Consul / node-multienv start_container.sh / Ory `serve`
pattern, and `serve <roles>` for hosted roles (D21, execution plan section
2.12). Node, not bash: self-hosters run on Windows, IIS and Azure, and the
final image has no npm. The dispatcher require()s the role in-process so
SIGTERM reaches the server.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=PLAT-ENTRY` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
