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
| repository | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@671bc88d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=T30-AUTH` is the measurement |
| semver | `n/a` |

## What this changes

No code. DECIDED 2026-09-16 - D16 adopted whole, D17 adopted in three rows of
four. Recorded in the execution plan section 1 and section 2.9. The
repo/branch fields were corrected at the same time: this item never touched
cgm-remote-monitor, its deliverable is a document here, and claiming a seam
worktree it does not write to made the item unpushable by description.

## Why that semver

research and decision, no shipped surface

## Who should review this, and why

maintainer DONE 2026-09-16; SECURITY still owes D17 row 2 a look, and that row
is the one deliberately left provisional. Under the one-deployment shape the
authentication plane is cohort-wide by construction, so tenant isolation rests
entirely on the authorization layer and RLS - which is now written down as the
D13 amendment rather than left to be discovered.

## What was measured

**`test -f docs/60-research/tenancy/auth-plane-ory-vs-inhouse-2026-09-16.md`** &nbsp;·&nbsp; kind: `static`

the deliverable exists. A presence check and nothing more - it cannot say
whether the recommendation is right, only that it was written.

**`grep -q '\*\*D16\*\*' docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md && grep -q '`** &nbsp;·&nbsp; kind: `static`

the decision reached the DECISIONS TABLE, not just a research document.
T30-RESEARCH's gate failed for three weeks because it named a file that never
existed, so a written deliverable read as not-started; this gate is
deliberately pointed at the place a later reader will look first. It cannot
tell whether the rows say the right thing.

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

DECIDED 2026-09-16 (maintainer). D16 ADOPTED WHOLE, including the prerequisite
- tenant resolution and credential verification extract to one module BEFORE
the third listener exists, which lands on T30-WIRING. D17 ADOPTED IN THREE
ROWS OF FOUR: devices and the data path keep a native per-tenant credential
permanently (forced by D1, an uploader cannot run an OAuth flow); Hydra
deferred; D7 unchanged. ROW 2 - Ory Kratos as one cohort-wide pool for human
identity - is recorded as DIRECTION OF TRAVEL, NOT ADOPTED, because every Ory
claim behind it is read and not run and because a shared identity pool is
irreversible once identities exist. It is gated on T30-ORY-PROOF. Commissioned
the same day by the maintainer, who settled the deployment shape mid-research
- ONE Kratos and ONE Hydra for the whole cohort, unified auth FOR Nightscout
tenants, not a Kratos tenant PER Nightscout tenant - which settles the largest
open question against Ory OSS, because OSS multi-tenancy is exactly what we
are not asking for. The three findings a reader should not have to dig for -
Nocturne uses no Ory at all and built identity in-house; Ory OSS is single-
tenant and its multi-tenancy is the paid boundary, which does not bind us; and
we already shipped this integration once and stopped one component short of
finishing it. A fourth was MEASURED after the decision and is in the research
document at section 3.5: Nocturne's identity plane is deployment-scoped too,
arrived at independently and with no Ory in the tree, which is the nearest
thing to corroboration this decision has.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=T30-AUTH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-15, against cgm-remote-monitor-official `a8888f0d`.*
