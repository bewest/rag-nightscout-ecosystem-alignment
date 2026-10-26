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

# Review packet — BFQ-ENV (PR #8849)

**BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/16.0.0-boot-resilience` |
| base | `official/dev@b29f1bf7` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=BFQ-ENV` is the measurement |
| semver | `minor` |
| register entries | `BF-48`, `BF-49`, `BF-50`, `BF-51` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/plugins/webhook.js:36-39, lib/settings.js:48-49 against
lib/server/env.js:114, README.md:240 and :399, azuredeploy.json. Four files
plus documentation; no request path changes.

## Why that semver

Making the second HSTS spelling work, and routing WEBHOOK_* through the
settings layer, both cause a setting that previously did nothing to start
doing something on deployments that already set it. That is a behaviour change
for those deployments even though it is a repair.

## What an operator would notice

> Four settings problems, none of which changes how Nightscout treats your
> data. The webhook plugin reads four settings that appear in no
> documentation. One security setting - whether the HTTPS security header
> also covers sub-domains - has two different spellings, and only the one in
> the README works, so setting it the other way does nothing. Four more
> security-related setting names in Nightscout's own settings list are read
> by nothing at all. The README documents a MONGODB_COLLECTION setting that
> no code reads, so setting it silently does nothing. And the one-click
> Azure deployment offers a Node version field that controls nothing.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 8e4d30d3 official/dev`** &nbsp;·&nbsp; kind: `static`

official/dev contains BF-48's code-half commit 8e4d30d3 (merged 2026-10-26 as
3b2e1a68); red if dev is rewritten or the merge is reverted out of history

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 8e3717e3 official/dev`** &nbsp;·&nbsp; kind: `static`

official/dev contains BF-49's start-up warning 8e3717e3 (merged 2026-10-26 as
3b2e1a68); red if dev is rewritten or the merge is reverted out of history

**`node tools/queue/gates/config-surface-census.js --arm hsts`** &nbsp;·&nbsp; kind: `static`

BF-49. Executes lib/settings.js and records the env names its own nameFromKey
asks for, rather than grepping for a spelling - the defect is that two
spellings exist, so a gate hardcoding one could not detect a third. FAILS on
SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS. The control is inside the same family:
4 of the 5 generated security names are read by env.js, so the miss is a
divergence and not a broken compare.

**`node tools/queue/gates/config-surface-census.js --arm readme`** &nbsp;·&nbsp; kind: `static`

BF-50. FAILS while README.md documents MONGODB_COLLECTION and none of the five
configuration and storage modules reads it. Control - the same files do
contain ENTRIES_COLLECTION.

**`node tools/queue/gates/config-surface-census.js --arm azure`** &nbsp;·&nbsp; kind: `static`

BF-51. FAILS while azuredeploy.json declares a WEBSITE_NODE_DEFAULT_VERSION
parameter and references it via parameters(...) zero times. Control -
parameters('mongoConnection') occurs once, so a zero is a fact about that knob
and not about the regex.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Retired 2026-10-26: the webhook census arm (node tools/queue/gates/config-
  surface-census.js --arm webhook) first confirms that
  lib/plugins/webhook.js reads process.env.WEBHOOK_*; #8849 moved those
  reads into env.js (8e4d30d3), so on official/dev 47723cda the arm reports
  that it is measuring nothing. The BF-48 ancestry gate above measures the
  merged fix.
- BF-51 is not reproduced against a live Azure deployment - there is no
  Azure environment on this machine and rule 0 forbids creating one. Why
  deployments work today is an open question attached to the entry rather
  than a finding: the platform presumably ignores the literal 8.11.1 as
  unavailable and falls back.
- Nothing checks that a key in the settings dictionary has a consumer.
  BF-49's five dead keys were found by grep over lib/, views/ and static/;
  the general check - every settings key is read somewhere - would have
  caught all five at once. It does not exist, and D7/D13 tenant-admin work
  will generate a UI from that dictionary.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

2026-10-26: BF-48's code half (8e4d30d3) and BF-49's start-up warning
(8e3717e3) merged in #8849 (merge 3b2e1a68, 12:43:22Z; gh pr view 8849). BF-50
and BF-51 were released in 15.0.9. What is left is two maintainer decisions
from #8849's open items: whether SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS becomes
an alias of SECURE_HSTS_HEADER_INCLUDESUBDOMAINS (it would turn
includeSubDomains on for sites that set the underscored name today; proposed:
announce now, alias in a later major), and what to do with the five settings
keys nothing reads, which are served to clients. 2026-10-25: on local
bf/16.0.0-boot-resilience (head 0675e91e after merging dev 428b20b7, not
pushed): BF-48 fixed as 8e4d30d3 (WEBHOOK_* read in env.js into env.webhook,
passed as ctx.webhook); BF-49 partly fixed as 8e3717e3 (a start-up warning
when the unread SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS is set; the alias and
the five dead settings keys are open decisions). BF-50 and BF-51 were fixed by
#8799 and released in 15.0.9; their gates here are stale. 2026-10-02
(maintainer, relayed by session -d4): BF-50 and BF-51 and the documentation
half of BF-48 and BF-49 go into 15.0.9 as BFQ-CONFIG-DOCS; after 15.0.9 here:
env.js routing for WEBHOOK_*, the HSTS alias, and reconciling the Azure
template's Node ~22 with cut 1's ~24. 2026-10-02 (session -d4's agent):
bf/config-docs-truth c102d98f, five commits (one per id: BF-46, 48, 49, 50,
51) on dev ca6fcfaf, README.md +33/-4, azuredeploy.json, lib/api3/swagger.yaml
and swagger.json; no .js change; full suite 3534/0/4 (Node 24.15.0, MongoDB
7.0.43); not pushed; PR body reports/phase0-pr-bodies/config-docs-truth.md.
The config-surface-census gate: readme (BF-50) and azure (BF-51) arms red ->
green; api3 (BF-46), webhook (BF-48) and hsts (BF-49) stay red until the code
half (env.js routing or an alias) is done. Gate defect: the hsts arm reads
lib/settings.js from the main clone's working tree whatever --ref says.
2026-10-02 (maintainer, relayed by session -d4): correct the information for
BF-48 to BF-51. Prepared with BFQ-46 by -d4's agent in externals/work/crm-
bf46-env off dev ca6fcfaf, not pushed; whether it goes into 15.0.9 is decided
once it is measured. Batched because it is one piece of work with one runnable
gate in four arms - make the configuration surface tell the truth - and
because a reviewer reading any one of them alone would ask about the other
three. Split it back by arm if the documentation half lands separately from
the plumbing half. BF-46 is deliberately not batched here; see that item.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-ENV` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
