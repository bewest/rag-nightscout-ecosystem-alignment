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

# Review packet — T30-AUTH

**The auth plane - Ory Kratos/Hydra against building it ourselves, and the
three-interface split**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=T30-AUTH` is the measurement |
| semver | `n/a` |

## What this changes

No code. Two proposed decisions - D16 three listeners, D17 the auth plane
splits by audience - plus the finding that nightscout-roles-gateway already
integrated Kratos and Hydra with Nightscout in 2022 and that the half it left
unfinished, the nsjwt token exchange, is the half no vendor writes for us.

## Why that semver

research and decision, no shipped surface

## Who should review this, and why

maintainer, and SECURITY for D17. The decision determines whether human
identity leaves the codebase, and under the one-deployment shape the
authentication plane is cohort-wide by construction - so tenant isolation
rests entirely on the authorization layer and RLS.

## What was measured

**`test -f docs/60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md`** &nbsp;·&nbsp; kind: `static`

the deliverable exists. A presence check and nothing more - it cannot say
whether the recommendation is right, only that it was written.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- EVERY ORY CLAIM IN IT IS READ, NOT RUN. No Kratos and no Hydra instance
  was started. This programme has measured five register entries whose read-
  derived claims did not survive contact with running code, and twice a
  prescribed fix measured as a regression. The discharge is specific: stand
  up Kratos 1.x and Hydra 2.x, register two tenants against one pool, and
  confirm a session for tenant A cannot be exchanged for a Nightscout token
  on tenant B.
- nightscout-roles-gateway was READ, not executed. Its dependencies are
  2022-era - @ory/kratos-client 0.9.0-alpha.3 and @ory/hydra-client 1.11.8 -
  and V0alpha2Api, which lib/privy/index.js:20 constructs, no longer exists
  under that name in Kratos 1.x. Whether its decision pipeline still works
  is unknown, and it is the first thing a port would measure.
- Nothing measures what a cohort-wide identity pool costs in isolation risk.
  Section 3.1 names the hazard - one identity, one session, one login
  spanning every tenant - and bounds nothing. A gate would need a cross-
  tenant session test, which needs the running stack the first no-gate asks
  for.
- No cost model. Ory Network pricing is not analysed and does not need to be
  under the one-deployment shape, which needs no Enterprise License - but
  the compliance question of any third-party processor adjacent to health
  data is not analysed either, and that one does not go away by self-
  hosting.

## Evidence

- [`docs/60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md`](../../docs/60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md)
- [`docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md`](../../docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md)

## Notes carried on the item

Commissioned 2026-09-16 by the maintainer, who is leaning toward Ory so that
sensitive OAuth and IAM controllers do not have to be built here, and who
settled the deployment shape mid-research - ONE Kratos and ONE Hydra for the
whole cohort, unified auth FOR Nightscout tenants, not a Kratos tenant PER
Nightscout tenant. That settles the largest open question against Ory OSS,
because OSS multi-tenancy is exactly what we are not asking for. The three
findings a reader should not have to dig for - Nocturne uses no Ory at all and
built identity in-house; Ory OSS is single-tenant and its multi-tenancy is the
paid boundary, which does not bind us; and we already shipped this integration
once and stopped one component short of finishing it.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=T30-AUTH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
