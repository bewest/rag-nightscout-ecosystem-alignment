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

# Review packet — ADV-CONFIG (PR #8746)

**The readable-by-world warning, the careportal role, and the two settings
behind both (BF-77, BF-78, BF-81)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/master@92d08342` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ADV-CONFIG` is the measurement |
| semver | `patch` |
| register entries | `BF-77`, `BF-78`, `BF-81` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

BF-77 merged 2026-09-21 as PR #8746 - bf/readable-warning, measured at
74731433, merged as 74fc6619, with an integration merge of dev (91ed8d95)
added to the branch on the way in. Rather than string equality at
lib/server/bootevent.js:149 it adds a second notice wording for the
readable+careportal configuration. 2311 -> 2331 passing / 0 failing; the
ablation goes red on exactly the three careportal cases with thirteen still
passing. Not released. BF-78, decided 2026-09-23 as documentation plus a boot
warning with no behaviour change, has no branch. BF-81 is prose - README.md
and the swagger documents - with no branch.

## Why that semver

BF-77 restores a notice that was intended; no interface changes. BF-78's
semver depends on which of the three shapes is chosen - giving careportal a
read permission would widen a documented role and is at least minor, so that
half is deliberately left unscored until the decision is taken.

## What an operator would notice

> Two things about the settings that control who can see your Nightscout.
> First, on release 15.0.8 and earlier, if you set TREATMENTS_AUTH=off, the
> warning that normally tells you "your Nightscout is readable by anyone who
> knows the address" stops appearing - even though that setting also lets
> anyone add treatments. The site is not more exposed than you asked for,
> but you stop being told. This is corrected in the development branch and
> arrives with the next release (15.0.9). Second, setting
> AUTH_DEFAULT_ROLES=careportal on its own does nothing at all: the
> documentation says any valid role name works, and this one is silently
> ignored, with no error anywhere. If you wanted "nobody can read my site,
> but my family can enter carbs without a token", that combination does not
> currently exist. Nightscout is not a medical device and this is not
> medical advice.

## Who should review this, and why

MAINTAINER - BF-81's wording is the maintainer's to write, and BF-78's
documentation and boot warning follow the 2026-09-23 decision. The coupling:
TREATMENTS_AUTH=off appends ' careportal' to authDefaultRoles; the boot
warning compared that string for equality with 'readable'; so on 15.0.8 the
notice is suppressed in exactly the configuration that is both world-readable
and anonymously writable. Meanwhile careportal alone grants only
api:treatments:create and is refused by the router's api:treatments:read gate
before reaching the create route - so the only configuration in which
careportal does anything is the one whose warning BF-77 suppressed. BF-78
fails closed - nothing is exposed - which is why it is low; the defect is
silence, not access.

## What was measured

**`git -C externals/work/crm-adv-shipping grep -q "authDefaultRoles == 'readable'" v15.0.8 -- lib/server/booteven`** &nbsp;·&nbsp; kind: `static`

The exact-string compare is present on the shipping release tag. The tag is
immutable, so this records the shipping state rather than tracking the fix;
BF-77's fix is in dev via PR #8746.

**`git -C externals/work/crm-adv-shipping grep -q "isPermitted('api:treatments:read')" v15.0.8 -- lib/api/treatme`** &nbsp;·&nbsp; kind: `static`

The router-wide read gate BF-78 is about is present on the shipping release.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behavioural half is not gated. Both findings were measured by booting
  the tree in three and four configurations respectively and reading GET
  /api/v2/adminnotifies and the result of an anonymous treatment POST.
  Automating that needs a fixture that boots the app per configuration,
  which does not exist in this repo. The measurements and their controls are
  in the evidence document; the two source gates above are the cheap proxy
  and they measure presence, not behaviour.

## Evidence

- [`docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md`](../../docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md)
- [`docs/30-design/remedial/advisory-response-2026-09/README.md`](../../docs/30-design/remedial/advisory-response-2026-09/README.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

BF-77 is merged into dev by #8746 (74fc6619, 2026-09-21) and not released. The
item stays needs-decision for BF-81: its wording (README.md and the swagger
documents) is the maintainer's to write, and there is no branch. BF-78 is
decided (below) and not yet built: no branch documents it or adds the boot
warning. Decisions: - 2026-09-23 (maintainer): BF-78 (the careportal role) is
documented and warned about at boot; no behaviour change. - 2026-09-21
(maintainer): BF-81 filed as the shared root of the other two, and BF-77's
second notice wording for the readable+careportal configuration approved.
Reproduced on v15.0.8 and dev 59430336, mongod 7.0, with both controls in the
same run. BF-77: default -> notifyCount 1, title "Nightscout readable by
world" (positive control); TREATMENTS_AUTH=off -> notifyCount 0 while
anonymous read is 200 and anonymous POST /api/v1/treatments is 200 with the
record stored; AUTH_DEFAULT_ROLES=denied -> notifyCount 0, correctly (negative
control, so absence in the middle row is attributable to the string compare).
These are documented configurations, not a bypass. BF-78, anonymous POST
/api/v1/treatments: `readable careportal` 200 stored, `careportal` 401,
`denied careportal` 401, `denied` 401. BF-81: the configuration surface
carries two authorization-shaped settings with adjacent names -
AUTH_DEFAULT_ROLES, which is the boundary, and AUTHENTICATION_PROMPT_ON_LOAD,
which is a client prompt that grants nothing - and nothing documents the
difference; the reporter of GHSA-8849 keyed their own security patch to the
wrong one.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ADV-CONFIG` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-25, against cgm-remote-monitor-official `e3adc91d`.*
