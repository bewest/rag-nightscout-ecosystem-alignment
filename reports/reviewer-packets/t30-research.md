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

# Review packet — T30-RESEARCH

**T3.0 part 1 - enumerate the per-tenant configuration surface**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `seam/t1-2-storage-interface@81a1f6ce` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=T30-RESEARCH` is the measurement |
| semver | `n/a` |

## What this changes

A design report. Every SETTINGS_* variable, every plugin credential, which are
secrets and which are not, what a tenant may override versus what the hoster
pins. DELIVERED as section B of the tenant-owner config-surface document: 277
distinct names, classified T / TS / D / B / X, measured against crm-seam at
81a1f6ce.

## Why that semver

research deliverable

## Who should review this, and why

maintainer. The document is a DRAFT carrying sections marked DECISION that
need a yes before T30-SCHEMA-CONFIG can start - so this item is a decision
surface now, not an unstarted research task.

## What was measured

**`test -f docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md`** &nbsp;·&nbsp; kind: `static`

the deliverable exists. CORRECTED 2026-09-16 - this gate named
docs/60-research/tenancy/tenant-config-surface-2026-09-15.md, which has never
existed under that name or in that directory, so the item measured FAIL and
read not-started while section B was written. A file-existence gate is weak on
purpose; it is honest about being a presence check, where a "state: done"
field would have been an assertion.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Nothing checks that the enumeration is COMPLETE. The only non-vacuous form
  is a differential: enumerate from the report, enumerate from
  lib/server/env.js by parsing, and require the two sets to agree - with a
  planted extra variable as the control. The census script EXISTS, at
  section G.3 of the deliverable, and reproduces {"s1":70,"s2":51,
  "s3prefixes":37,"s4":208,"union":247} against crm-seam at 81a1f6ce. It is
  not checked in anywhere and nothing re-runs it, so the 247 is a transcript
  rather than a measurement. Lifting G.3 into tools/queue/gates/ is the
  cheapest real gate this item can have.
- The document names five gaps in its own coverage and none is closed. (1)
  the grep cannot see process.env['X'], which is how it missed the API v3
  family that includes the one that irreversibly deletes data; (2) three AWS
  names are read directly and appear in no source; (3) twelve ADMIN_* /
  FEED_* names read by the hosted entrypoints appear in no source, no gap
  and no total; (4) webhook's four reads are inside the plugin factory, not
  at module scope, as first published; (5) the per-group counts inside each
  class are hand-expansions, not script output, and the document says so.
  Completeness is therefore bounded by a method the document argues against
  itself.
- Section A's DDL has never been executed against a PostgreSQL server, and
  two findings against it - the ?| operator being top-level only, and a
  CHECK passing when its expression is NULL, which lets a PARTIAL mmol
  threshold override through - are read off PostgreSQL's documented
  semantics rather than off a server. Those two are the first thing the
  section A harness must test, and the second is about alarm thresholds.

## Evidence

- [`docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md`](../../docs/30-design/tenancy/tenant-owner-config-surface-2026-09-15.md)
- [`docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md`](../../docs/30-design/tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md)

## Notes carried on the item

T3.0 is the largest correction owed in the programme. It does NOT block T3.3 -
T3.3 landed first. It AMENDS T3.1, T3.2 and T3.3, which are all marked DONE-
EXCEPT. RE-STATED 2026-09-16 - the enumeration this item asks for was written
on 2026-09-15 and adversarially reviewed the same day, which corrected twelve
claims including the surface total (277, not 258). What remains is not
enumeration: it is the maintainer decisions the document defers, and the
harnesses that would turn its numbers into measurements. The three decisions
with the longest reach are where the tenant-owner API lives, what issues and
verifies a tenant-owner credential, and whether D7's credential-free platform
plane survives contact with Nocturne, which puts platform admin on the
consumer API behind a platform_admin role instead.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=T30-RESEARCH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `74fc6619`.*
