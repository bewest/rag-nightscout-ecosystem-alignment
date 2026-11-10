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

# Review packet — MT-M6A-JOIN

**M6a: join the accepted owner/OIDC candidate to #8898 and run the final
campaign**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/m6a-join-20261109` |
| base | `official/dev@4a482627bfdafb1fef8dcbe0ac6c484811cae563` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=MT-M6A-JOIN` is the measurement |
| semver | `minor` |

## What this changes

Draft PR #8898 head moves from ed2ced00 to the joined candidate. Full seven-
tier, default-browser, enabled-corpus, pinned-client and prcheck must be re-
run on the new frozen head; the ed2 campaign does not transfer. Also clears
the CodeQL alert on the private IPC dispatch (lib/server/realtime/ipc.js,
bounded own-property lookup; restructure to a Map or dismiss with
justification). The second CodeQL alert is on code identical to official/dev
and is not this PR's.

## Why that semver

opt-in feature on a dormant preview branch

## What an operator would notice

> Optional sign-in with an identity provider for people managing a
> Nightscout site, in both single-site and multitenant modes. Off unless
> enabled. Uploaders and followers keep their existing credentials.

## Who should review this, and why

maintainer; security review of the identity surface

## What was measured

**`node tools/queue/gates/oidc-native-recorded.js reports/tenancy/m6a-join-2026-11-09/oidc-matrix-final/summary.j`** &nbsp;·&nbsp; kind: `static`

RECORDED-EVIDENCE: nine-stage OIDC matrix on the joined head 74036ba6, all
PASS, three mutant controls red then green. The rest of the final verification
is in reports/tenancy/m6a-join-2026-11-09/README.md section 10: test:all 0
failing, browser 686/0, multitenant corpus 537/1 pending/0, write-intent and
write-boundary clean, prcheck exit 0 against official/dev 4a482627.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-OIDC-NATIVE`

## Evidence

- [`reports/tenancy/operation-window-acceptance-2026-11-07/README.md`](../../reports/tenancy/operation-window-acceptance-2026-11-07/README.md)

## Notes carried on the item

Owns the coherent join that closes M6a. Taking the PR out of draft, review and
merge remain the maintainer's actions. Also joins codex/vault-token-
file-20261109 and gives the three OIDC-branch getToken sites (human-
session/access-config.js, serve/owner-credential-config.js, secrets/vault-
access-signing.js) the same tokenFile shape. 2026-11-09 (reproduced): head
74036ba6, a fast-forward of the PR branch from ed2ced00 (40 commits, 143
files). Repairs: D23 socket delegation via a beforeWrite hook; human_session
family admitted to the lifecycle catalogue; two date-pinned test time bombs;
OIDC browser discovery made opt-in by a page-server hint so default-off sites
start exactly as on ed2; owner capability test expectations and grants.
Awaiting maintainer decisions on opt-in discovery and permitted owner DELETE
before the push.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-M6A-JOIN` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
