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

# Review packet — BFQ-CONFIG-DOCS

**bf/config-docs-truth - documentation for BF-46, BF-48, BF-49, BF-74, BF-78,
BF-81 and the fixes for BF-50, BF-51, for 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/config-docs-truth` |
| base | `official/dev@ca6fcfaf` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-CONFIG-DOCS` is the measurement |
| semver | `patch` |
| register entries | `BF-46`, `BF-48`, `BF-49`, `BF-50`, `BF-51`, `BF-74`, `BF-78`, `BF-81` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Documentation only, eight commits (one per id) on dev ca6fcfaf, head e42144ff:
README.md +33/-4 (API v3 settings, webhook settings, the HSTS spelling,
ENTRIES_COLLECTION instead of MONGODB_COLLECTION), azuredeploy.json (uses its
WEBSITE_NODE_DEFAULT_VERSION parameter), lib/api3/swagger.yaml and
swagger.json (corrected settings text); and, as draft wording for the
maintainer to edit in the PR, BF-81 (AUTH_DEFAULT_ROLES is the boundary,
AUTHENTICATION_PROMPT_ON_LOAD, the seven roles), BF-78 (careportal,
devicestatus-upload and activity do nothing without readable) and BF-74 (API
v3 settings are stored as sent). No .js change.

## Why that semver

documentation and a deploy template parameter

## What an operator would notice

> The setup documentation now names the settings Nightscout actually reads,
> including the API v3 settings and the webhook plugin's, and the Azure
> deploy template uses the Node version you choose.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official cat-file -e e42144ff`** &nbsp;·&nbsp; kind: `static`

The branch head e42144ff exists in the clone (a presence check). The config-
surface-census gate's readme (BF-50) and azure (BF-51) arms decide; its api3,
webhook and hsts arms stay red until the code half (BFQ-46, BFQ-ENV) is done.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured 2026-10-02 by session -d4's agent on c102d98f: full suite
  3534/0/4 (Node 24.15.0, MongoDB 7.0.43); readme and azure arms red ->
  green.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`reports/phase0-pr-bodies/config-docs-truth.md`](../../reports/phase0-pr-bodies/config-docs-truth.md)

## Notes carried on the item

2026-10-02 (maintainer, relayed by session -d4): draft README wording for
BF-74, BF-78 and BF-81 added (1c09b22d, b09c0af9, e42144ff), for the
maintainer to edit in the PR; full suite 3534/0/4. BF-78's boot warning is
after 15.0.9. Decided 2026-10-02 (maintainer, relayed by session -d4): goes
into 15.0.9; in RT-0's blocks_on. Split out of BFQ-46 and BFQ-ENV so that the
release waits on this branch only: their code half (env.js routing for API3_*
and WEBHOOK_*, the HSTS alias) is after 15.0.9 and stays on those items. Not
pushed.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-CONFIG-DOCS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
