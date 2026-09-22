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

# Review packet — P0-PUBLISH

**ci/npm-trusted-publish - publish nightscout-connect to npm from a version tag**

| | |
|---|---|
| repository | `nightscout-connect` |
| branch | `ci/npm-trusted-publish` |
| base | `official/dev@8e26786` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=P0-PUBLISH` is the measurement |
| semver | `n/a` |

## What this changes

1 commit, e3e018e: .github/workflows/publish.yml and docs/releasing.md, +170.
No library code. Trial merge into official/dev d208c7d clean (2026-09-22).

## Why that semver

release tooling only; no published surface of the package moves

## What an operator would notice

> Nothing changes for anyone running Nightscout. It changes how the
> connector is published: a version tag publishes it to npm after a person
> approves, with a public record linking the published package to the exact
> source it was built from, and with no stored npm password or token.

## Who should review this, and why

maintainer. Two settings outside the repository must exist before the first
tag: a trusted-publisher entry on the npm package (an npm owner) and a GitHub
environment npm-publish with required reviewers (a repository admin).
docs/releasing.md on the branch lists both.

## What was measured

**`git -C externals/nightscout-connect cat-file -e ci/npm-trusted-publish:.github/workflows/publish.yml`** &nbsp;·&nbsp; kind: `static`

the workflow exists on the branch

**`git -C externals/nightscout-connect merge-tree --write-tree official/dev ci/npm-trusted-publish`** &nbsp;·&nbsp; kind: `static`

the branch merges into connector dev without conflicts

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The publish step can only run on GitHub against a configured npm package.
  Measured locally on 2026-09-22: actionlint clean (a broken control
  workflow was reported), and each refusal the workflow makes (tag/version
  mismatch, commit not on dev or main, version already on npm, npm older
  than 11.5.1) exercised with a passing and a failing case.
- The npm trusted-publisher entry and the GitHub environment are settings on
  npmjs.com and GitHub, not in any repository.

## Evidence

- [`docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md`](../../docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md)

## Notes carried on the item

Optional for the release: without it P0-TAG's tag publishes nothing and cgm-
remote-monitor pins the tag tarball. npm's latest published version is 0.0.12,
and the package has one owner account.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=P0-PUBLISH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-22, against cgm-remote-monitor-official `74fc6619`.*
