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
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-M6A-JOIN` is the measurement |
| semver | `minor` |

## What this changes

Draft PR #8898 head moves from ed2ced00 to the joined candidate. Full seven-
tier, default-browser, enabled-corpus, pinned-client and prcheck must be re-
run on the new frozen head; the ed2 campaign does not transfer. CodeQL on
74036ba6 (measured 2026-11-10 UTC): the Map dispatch closed alert 153 but
opened 155 on the same call; 150 (token type flow into subject lookup, code
identical to dev but only reported on this PR) and 154 (rate limiting on a
native test fixture) remain open. Follow-up 0fc5abf9 adds a function check on
the IPC dispatch and a string check on the subject lookup; 154 follows the
test-fixture dismissal precedent.

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
2026-11-09: maintainer accepted opt-in discovery and permitted owner DELETE,
and pushed 74036ba6 to workspace/multitenant-20261102 (PR #8898, draft). CI on
that head: tests, no-database, npm, Docker green; browser, maintained-MongoDB
and multitenant corpus jobs were still running when read; CodeQL failed on
alerts 150/154/155. Follow-up 0fc5abf9 (local, unpushed): non-string access
tokens find no subject (test red without the guard with "accessToken.split is
not a function", green with it); IPC dispatch requires a function. Focused:
authorization reload 4/0, realtime-preview 24/0,
security/api.security/api.unauthorized 40/0, lint clean, write-intent clean,
prcheck OK. 2026-11-10 (reproduced): joined the internal service API refactor
dc795bd1 (fast-forward over 0fc5abf9; decision internal-service-contracts).
Full acceptance on dc795bd1: unit 3072, dom 205, dependency 368/2, core 319,
harness 99, integration 3618/534, stress 18, browser 686, corpus 537/1, all 0
failing; OIDC matrix 9/9 with 3/3 controls; new response-schema break-it red
(listener 200 instead of 503; client "Missing expected rejection.") then
green; prcheck OK. Evidence
reports/tenancy/m6a-join-2026-11-09/dc795bd1-acceptance/. Ready for the
maintainer to push dc795bd1 to #8898.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-M6A-JOIN` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
