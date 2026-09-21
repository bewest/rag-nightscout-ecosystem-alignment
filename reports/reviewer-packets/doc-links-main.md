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

# Review packet — DOC-LINKS

**Every path the programme's documents and tooling cite must resolve**

| | |
|---|---|
| repository | `rag-nightscout-ecosystem-alignment` |
| branch | `main` |
| base | `main@6574b28d` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=DOC-LINKS` is the measurement |
| semver | `n/a` |

## What this changes

tools/queue/gates/doc-links.js (new), and the 55 September documents moved
into programme subdirectories on 2026-09-16 with 280 links and 212 repo-root
paths rewritten.

## Why that semver

documentation and repository tooling

## Who should review this, and why

maintainer. The gate carries four exemption classes - FROZEN, NOT_REAL,
PLANNED and QUOTED - and every one of them is a place where a future defect
could be parked with a plausible reason. The register's own suppression audit
found 5 real defects hiding behind 45 suppressions, so READ THE EXEMPTION
LIST, not just the exit code.

## What was measured

**`node tools/queue/gates/doc-links.js`** &nbsp;·&nbsp; kind: `static`

FAILS when any path cited by the groomed programme material or the live queue
tooling does not resolve. 852 references across 116 files. Three detection
passes, one per class that survived the 2026-09-16 rewrite: markdown links (in
every scoped text file, not only .md, because one was embedded in a Python
edit script), repo-root-absolute paths (which catches a backticked citation
the link regex could not see), and piecewise path.join(REPO_ROOT, 'docs', ...)
in gate sources - the class that broke FOUR gates, three of which were already
expected to fail, so the ENOENT was invisible inside an intended red.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The legacy tree is out of scope on purpose. The Jan-Apr research campaign,
  docs/backlogs/archive/ and specs/ carry 109 dead links that predate this
  work, and the maintainer's instruction on 2026-09-16 was to groom the
  recent material and leave the older material alone. Gating them would make
  this gate permanently red for reasons nobody intends to fix, which is how
  a gate stops being read. Bringing them into scope is work, not a sweep.
- 25 root-path references name a subtree this repository does not have. They
  are cgm-remote-monitor's own docs/ - docs/meta/, docs/INDEX.md,
  docs/proposals/ measured present on origin/dev and origin/master;
  docs/runtime-upgrade.md present only on cut 1's branch. The first version
  of this gate called all four dead and was wrong about all four. Telling
  the two repositories' docs/ trees apart properly needs a per-reference
  repository marker, which the documents do not carry.

## Evidence

- [`docs/60-research/remedial/e3-gate-vacuity-audit-2026-09-15.md`](../../docs/60-research/remedial/e3-gate-vacuity-audit-2026-09-15.md)

## Notes carried on the item

Non-vacuity, run 2026-09-16: three ablations, one per detection pass, each
confirmed to LAND before its result was read. A markdown link repointed to a
NOPE name - caught. A repo-root path in this manifest reverted to its pre-move
spelling - caught. doc-branch-count.js's path.join reverted to the pre-move
segments - caught, and that is the exact break that hid on 2026-09-16. Empty-
root negative control via QUEUE_GATE_ROOT exits 1 rather than passing on a
tree with nothing in it. Two earlier ablation attempts DID NOT LAND (0 and 31
occurrences against a required 1) and were re-authored rather than read as
green - rule from memory/milestone-agents-and-non-vacuity.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=DOC-LINKS` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `74fc6619`.*
