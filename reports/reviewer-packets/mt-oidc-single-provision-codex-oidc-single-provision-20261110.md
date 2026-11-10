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

# Review packet — MT-OIDC-SINGLE-PROVISION

**Single-site OIDC: declarative identity-to-role list and a role for signed-in
strangers**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `codex/oidc-single-provision-20261110` |
| base | `codex/m6a-join-20261109@dc795bd1515f11808a8d0732f2be9925cb2ffcd1` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=MT-OIDC-SINGLE-PROVISION` is the measurement |
| semver | `minor` |

## What this changes

Single-site OIDC (ENABLE includes oidc, lib/human-session/runtime.js:8) today
maps a signed-in person only through principal rows inside the
<prefix>human_authority document (lib/human-session/mongo.js); nothing
provisions those rows, and a signed-in identity with no row is refused rather
than given a role. Direction (maintainer, 2026-11-09): an operator-supplied
list (env or file, CSV/TSV/JSON) maps identities to existing roles such as
careportal + readable, and signed-in people who are not listed fall back to a
configured role (for example readable), as anonymous visitors already do with
AUTH_DEFAULT_ROLES.

## Why that semver

opt-in feature on the preview

## What an operator would notice

> A site that turns on sign-in can list the people allowed in and what each
> may do, in one file, and choose what anyone else who signs in can see.

## Who should review this, and why

maintainer; security review of the identity surface

## What was measured

**`node tools/queue/gates/oidc-native-recorded.js reports/tenancy/oidc-single-provision-2026-11-10/summary.json`** &nbsp;·&nbsp; kind: `static`

RECORDED-EVIDENCE: nine-stage OIDC native matrix at lane commit 61af8beb, 9/9
PASS, three harness controls red then green (13 checked, 0 failing).
Provisioning suite tests/human-session-provision.test.js 24 passing against
MongoDB; seven lane controls C1-C7 in reports/tenancy/oidc-single-
provision-2026-11-10/.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Blocked on

`MT-M6A-JOIN`

## Evidence

- [`releases/cgm-remote-monitor-16.0.0/decisions.md`](../../releases/cgm-remote-monitor-16.0.0/decisions.md)

## Notes carried on the item

Design points to settle in the lane: key the list on issuer + provider
subject, and accept email only when the same issuer marks it verified (emails
can be reassigned). Single-site OIDC currently also needs a Vault Transit
signer (OIDC_ACCESS_CONFIG vault block is required), a heavy dependency for
one site; a local signing-key option belongs in the same lane. 2026-11-09
(read-derived, 0fc5abf9): the single-site Mongo store keeps a permissionGroups
snapshot on each principal (lib/human-session/mongo.js:70-73), so roles edited
in the admin UI do not govern a signed-in person; the PostgreSQL path joins
current subject roles. The only signer is Vault Transit (access-config.js:73);
the access tokens are Ed25519, which node:crypto signs locally. Proposed
shape: config inline in an env value or by a *_FILE path (as LOOP_APNS_KEY
carries a key inline); single-site signs with a local Ed25519 key and derives
issuer, audiences and kid; a principal binds to an existing auth subject and
takes that subject's current roles; the env/file list seeds those bindings at
boot the way default roles are seeded, with the database as the home.
2026-11-10 (reproduced in lane): 4b81f59d on dc795bd1. OIDC_ACCESS_CONFIG
inline or _FILE (both refuse); single-site local Ed25519 signer
(OIDC_ACCESS_SIGNING_KEY[_FILE]) with HKDF-derived purpose keys, Vault
optional for single-site, refused in multitenant; principals bind to an auth
subject and read current roles per operation (stored permissionGroups
ignored); OIDC_IDENTITIES[_FILE] keyed on issuer+subject or issuer-verified
email; OIDC_FALLBACK_ROLES for unlisted people. Maintainer 2026-11-10: the
list is authoritative at each start (decision single-site-oidc-list-
authoritative). Joined into MT-M6B-JOIN. 2026-11-10: ships in #8898 at
b70ad83f (MT-M6B-JOIN); CI green.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=MT-OIDC-SINGLE-PROVISION` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-27, against cgm-remote-monitor-official `7000eb18`.*
