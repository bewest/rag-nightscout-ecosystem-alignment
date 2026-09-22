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

# Review packet — P0-TAG (PR #70)

**nightscout-connect 0.0.14 - tag connector dev**

| | |
|---|---|
| repository | `nightscout-connect` |
| branch | `dev` |
| base | `official/dev@d208c7d` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=P0-TAG` is the measurement |
| semver | `minor` |
| register entries | `BF-08`, `BF-34`, `BF-42`, `BF-85` |

## What this changes

The release is connector dev; there is no release branch. Measured 2026-09-22
at official/dev d208c7d: dev carries 9fa2c3c, 5349d47, 77e2396 (credential-
safe logging, BF-42), 8406edf (the BF-85 CareLink zero filter), 51b6e6e
(listener release on stop) and 234d47c (the opt-in logger, the commit cgm-
remote-monitor dev pins), plus LibreLinkUp v4 (#73), Glooko (#71) and
connector CI (#72). It does not yet carry c1cce2a (#68). Upstream PR #70 (dev
-> main) is the release PR. The remote's newest tag is v0.0.13.

## Why that semver

see P0-F. GT4 argues the version should be 0.1.0; connector dev's package.json
says 0.0.14. The maintainer chooses before tagging.

## What an operator would notice

> A new version of the CGM connector, the part of Nightscout that fetches
> readings from a CGM vendor's online service. It stops the connector
> writing vendor credentials, session tokens and readings to the log, stops
> a CareLink "no reading" marker being stored as a glucose value of 0, and
> carries the retry fixes in P0-F. Nothing reaches anyone until the version
> is tagged and a Nightscout release is updated to use it (P0-PIN).

## Who should review this, and why

maintainer - choosing the version and pushing the tag are the deliberate human
acts. With P0-PUBLISH merged and npm configured, pushing the tag also
publishes to npm after an approval; without it, the tag publishes nothing by
itself.

## What was measured

**`for c in 9fa2c3c 5349d47 77e2396 8406edf 51b6e6e 234d47c; do git -C externals/nightscout-connect merge-base --`** &nbsp;·&nbsp; kind: `static`

the six fixes #64 carried are in connector dev. Passes at d208c7d.

**`! git -C externals/nightscout-connect rev-parse -q --verify refs/tags/v0.0.14`** &nbsp;·&nbsp; kind: `static`

no local v0.0.14 tag exists. RED while the retired local tag (649a7de,
release/v0.0.14) is still present: it names a different tree and would be
pushed by mistake. Delete it with `git tag -d v0.0.14` before tagging dev.

**`git -C externals/nightscout-connect ls-remote --tags origin v0.0.14 | grep -q . && exit 1 || exit 0`** &nbsp;·&nbsp; kind: `network`

RULE 0. PASSES only while no v0.0.14 tag is on the remote - the machine-
checkable form of "nothing has been pushed". Read-only.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Release content and number are the maintainer's decision. Two shapes: tag
  dev now as 0.0.14 without #68, with #68 following in the next release
  (release-readiness-15.0.9 §5.2); or merge #68 first and tag that. Under
  the versioning policy, the first release carrying the backoff change
  (c1cce2a) is 0.1.0. `git -C externals/nightscout-connect merge-base --is-
  ancestor c1cce2a official/dev` says which shape dev is in.

## Evidence

- [`docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md`](../../docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md)
- [`docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md)

## Notes carried on the item

The programme's local release/v0.0.14 branch and v0.0.14 tag are retired:
every commit on them is in connector dev or in #68. Tag dev, not that branch.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-TAG` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
