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

# Review packet — RT-PR-8815 (PR #8815)

**#8815 - a bearer token whose subject was deleted is refused instead of
stopping the server (awss1i; BF-171, fixes #8225), for 15.0.9**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `awss1i:wip/stale-token-crash` |
| base | `official/dev@fade2299` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=RT-PR-8815` is the measurement |
| semver | `patch` |
| register entries | `BF-171` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

lib/authorization/index.js resolve (+5/-2): a verified JWT counts as a login
only when resolveAccessToken finds its subject; otherwise the existing failed-
credential path. Plus three tests in tests/api.security.test.js and a
CHANGELOG entry. Server-side only.

## Why that semver

A request that stopped the server now gets 401 (API v1, verifyauth, both
sockets); no input that answers 2xx today changes, and the token already had
no access. API v3 answers such a token 401 instead of 403, a status change on
an already-refused request: the same kind of question as #8772's (policy
section 9 table), for the maintainer.

## What an operator would notice

> If an app kept a sign-in token after that token's subject was deleted (for
> example you removed it on the admin page, or your database was reset),
> Nightscout could stop as soon as the app connected, and stop again after
> every restart, for up to 8 hours. That token is now refused like a wrong
> one, you see a "Failed authentication" notice, and Nightscout keeps
> running.

## Who should review this, and why

maintainer

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor 93a74ce5 official/dev`** &nbsp;·&nbsp; kind: `static`

#8815's head 93a74ce5 is contained in official/dev. Red until the PR merges; a
later head changes the hash here.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- Measured 2026-10-20 (Node 24.15.0, MongoDB 7.0.43,
  AUTH_DEFAULT_ROLES=denied; probe held outside version control): on v15.0.8
  92d08342 and dev fade2299 the first API v1 request with the token stops
  the server, and again after each of 3 restarts; on dev the websocket
  authorize path stops it too. On 93a74ce5 the same requests get 401 and the
  server stays up; API v3 401 (403 before). The PR's three tests copied onto
  fade2299 fail there and pass on 93a74ce5 (19 passing). The author's full
  suite 3569 against 3566 on dev, not re-run here.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

Opened 2026-10-17 by awss1i (one commit on dev fade2299), not merged.
2026-10-20 (maintainer): goes into 15.0.9. Introduced in 14.1.0 by #6596
(7fe8e321), read not run; a process exit since the supported runtimes reached
Node 15+. Review notes, none blocking: the "Failed authentication" wording
could name a token whose subject is gone, and the callers could guard against
a result without shiros. Merging it moves dev past fade2299, so the last full
run (023) and the #8598 approval are on an older head.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=RT-PR-8815` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
