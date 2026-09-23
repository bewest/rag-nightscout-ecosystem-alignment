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

**nightscout-connect 0.1.0 - the full release, from connector dev**

| | |
|---|---|
| repository | `nightscout-connect` |
| branch | `dev` |
| base | `official/dev@1946beb` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=P0-TAG` is the measurement |
| semver | `minor` |
| register entries | `BF-08`, `BF-34`, `BF-42`, `BF-85` |

## What this changes

The release is connector dev; there is no release branch. Measured 2026-09-22
at official/dev 1946beb, which declares 0.1.0: it carries 9fa2c3c, 5349d47,
77e2396 (credential-safe logging, BF-42), 8406edf (the BF-85 CareLink zero
filter), 51b6e6e (listener release on stop), 234d47c (the opt-in logger, the
commit cgm-remote-monitor dev pins), c1cce2a (the backoff and jitter fix,
BF-08 and BF-34), LibreLinkUp v4 (#73), Glooko (#71), connector CI (#72) and
the publish workflow (#74, #75). Prerelease 0.1.0-dev.1 (tag v0.1.0-dev.1 ->
1946beb) is on npm under `next`; npm's `latest` is 0.0.12. Upstream PR #70
(dev -> main) is open.

## Why that semver

0.1.0, set on connector dev by PR #76: the first release carrying the backoff
change (P0-F), which is caller-visible under 0.x semantics.

## What an operator would notice

> A new version of the CGM connector, the part of Nightscout that fetches
> readings from a CGM vendor's online service. It stops the connector
> writing vendor credentials, session tokens and readings to the log, stops
> a CareLink "no reading" marker being stored as a glucose value of 0, and
> carries the retry fixes in P0-F. A test version (0.1.0-dev.1) is published
> for people who ask for it; the full version is not released yet, and
> nothing reaches Nightscout users until a Nightscout release is updated to
> use it (P0-PIN).

## Who should review this, and why

maintainer - when to cut the full release is the decision. Pushing tag v0.1.0
on dev runs publish.yml, which waits for a reviewer from team c-r-m-dev on the
npm-publish environment and then publishes to npm as `latest`. After it, merge
#70 and open the next version bump on dev.

## What was measured

**`for c in 9fa2c3c 5349d47 77e2396 8406edf 51b6e6e 234d47c c1cce2a; do git -C externals/nightscout-connect merge`** &nbsp;·&nbsp; kind: `static`

all seven programme connector commits are in connector dev

**`test "$(git -C externals/nightscout-connect show official/dev:package.json | python3 -c 'import json,sys; prin`** &nbsp;·&nbsp; kind: `static`

connector dev declares 0.1.0, the version the full release must match

**`! git -C externals/nightscout-connect rev-parse -q --verify refs/tags/v0.0.14`** &nbsp;·&nbsp; kind: `static`

no local v0.0.14 tag exists. RED while the retired local tag (649a7de,
release/v0.0.14) is still present: it names a tree that is not the release.
Delete it with `git tag -d v0.0.14`.

**`git -C externals/nightscout-connect merge-base --is-ancestor c1cce2a "$(npm view nightscout-connect@next gitHe`** &nbsp;·&nbsp; kind: `network`

npm's `next` prerelease was built from a commit carrying the whole fix set.
Read-only.

**`git -C externals/nightscout-connect ls-remote --tags origin v0.1.0 | grep -q . && exit 1 || exit 0`** &nbsp;·&nbsp; kind: `network`

RULE 0. PASSES only while no v0.1.0 tag is on the remote - the machine-
checkable form of "the full release has not been cut". Read-only.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Whether 0.1.0-dev.1 has been exercised enough to cut 0.1.0 is the
  maintainer's judgement.

## Evidence

- [`docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md`](../../docs/30-design/modernization/release-readiness-15.0.9-2026-09-22.md)
- [`docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md)

## Notes carried on the item

DECIDED 2026-09-22 (maintainer) - tag 0.1.0 and pin it inside 15.0.9. Tagging
remains the maintainer's action. The programme's local release/v0.0.14 branch
and v0.0.14 tag are retired: every commit on them is in connector dev. No
0.0.14 will be published; the line is 0.1.0.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-TAG` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
