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

# Review packet — RT-COUNT-COMPAT

**Two real clients meet the 15.0.9 count rule: a correction or a compatibility
break?**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/dev@ddd9b600` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=RT-COUNT-COMPAT` is the measurement |
| semver | `n/a` |

## What this changes

The v1 count rule from #8738 as amended by #8748 (lib/server/count.js,
lib/api/index.js validateCount), and the number 15.0.9 ships under.

## Why that semver

this item decides whether the count rule is patch, minor or major

## What an operator would notice

> Some apps ask Nightscout for records in a way this release reads more
> strictly than 15.0.8 did. OpenAPS (oref0) asks for its latest treatment
> with a malformed count and would get an error; GluPredKit asks for "zero"
> records meaning "all of them" and would get none. What changes, and how
> the release notes describe it, is being decided before 15.0.9 ships.

## Who should review this, and why

maintainer - a semver and compatibility decision, with a safety dimension on
the oref0 side

## What was measured

**Nothing runnable.** Every gate on this item is an explicit `no-gate:` marker. Read the next section as the whole evidence picture, not as a caveat on it.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Evidence is read from client source and reproduced at the parser level; an
  end-to-end replay on 15.0.8, dev and the candidate tree 2ce67b27 is
  running (-6a), including whether the resulting oref0 re-upload stores
  duplicate treatments. The decision waits on it.

## Evidence

- [`docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md)

## Notes carried on the item

Filed 2026-09-23 from the -6a consumer-impact survey, on the maintainer
instruction to document it as a compatibility and semver item, not a backfix.
oref0 (dev d219baf9, master 88cf032a) sends count as "1?<credential>" from
latest-openaps-treatment; 15.0.8 parseInt read 1, 15.0.9 answers 400.
GluPredKit sends count=0 as "no limit"; 15.0.9 answers []. Under the semver
policy rule (section 3.2) both make the narrowing major as written. Options,
in outline - ship as a declared correction naming both clients; tolerate the
shapes real clients send and keep 15.0.9 a patch; or number the release as a
major. The release notes count section carries a hidden OPEN BEFORE THE TAG
note.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-COUNT-COMPAT` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-23, against cgm-remote-monitor-official `ddd9b600`.*
