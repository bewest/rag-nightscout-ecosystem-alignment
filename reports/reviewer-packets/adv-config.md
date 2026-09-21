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

# Review packet — ADV-CONFIG

**The readable-by-world warning and the careportal role (BF-77, BF-78)**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `` |
| base | `origin/master@92d08342` |
| claimed state | `needs-decision` — a claim; `make queue-status ID=ADV-CONFIG` is the measurement |
| semver | `patch` |
| register entries | `BF-77`, `BF-78` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

No branch yet. BF-77 is a one-line change at lib/server/bootevent.js:149 -
test for the `readable` role's presence in the resolved list rather than
string equality with it. BF-78 has three possible shapes and none is obviously
right, which is why this is needs-decision rather than not-started: give the
careportal role the read permission its routes require; move the router-wide
read gate at lib/api/treatments/index.js:26 below the create route at :146; or
document that careportal only functions alongside `readable` and say so at
boot when it does not.

## Why that semver

BF-77 restores a notice that was intended; no interface changes. BF-78's
semver depends on which of the three shapes is chosen - giving careportal a
read permission would widen a documented role and is at least minor, so that
half is deliberately left unscored until the decision is taken.

## What an operator would notice

> Two things about the settings that control who can see your Nightscout.
> First, if you set TREATMENTS_AUTH=off, the warning that normally tells you
> "your Nightscout is readable by anyone who knows the address" stops
> appearing - even though that setting also lets anyone add treatments. The
> site is not more exposed than you asked for, but you stop being told.
> Second, setting AUTH_DEFAULT_ROLES=careportal on its own does nothing at
> all: the documentation says any valid role name works, and this one is
> silently ignored, with no error anywhere. If you wanted "nobody can read
> my site, but my family can enter carbs without a token", that combination
> does not currently exist. Nightscout is not a medical device and this is
> not medical advice.

## Who should review this, and why

MAINTAINER - both are contract questions about the configuration surface, not
bugs with an obvious patch. They are two halves of one trap and should be
decided together. TREATMENTS_AUTH=off appends ' careportal' to
authDefaultRoles; the boot warning compares that string for equality with
'readable'; so the notice is suppressed in exactly the configuration that is
both world-readable AND anonymously writable. Meanwhile careportal alone
grants only api:treatments:create and is refused by the router's
api:treatments:read gate before reaching the create route - so the ONLY
configuration in which careportal does anything is the one whose warning BF-77
suppresses. An operator who wants anonymous careportal entry is steered, by
the only route that works, into the configuration that stops warning them.
Note BF-78 fails CLOSED - nothing is exposed - which is why it is low; the
defect is silence, not access.

## What was measured

**`git -C externals/work/crm-adv-shipping grep -q "authDefaultRoles == 'readable'" v15.0.8 -- lib/server/booteven`** &nbsp;·&nbsp; kind: `static`

The exact-string compare is still present on the shipping release. Goes
green->red when BF-77 is fixed, which is the point.

**`git -C externals/work/crm-adv-shipping grep -q "isPermitted('api:treatments:read')" v15.0.8 -- lib/api/treatme`** &nbsp;·&nbsp; kind: `static`

The router-wide read gate BF-78 is about is still present on the shipping
release.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- THE BEHAVIOURAL HALF IS NOT GATED. Both findings were measured by booting
  the tree in three and four configurations respectively and reading GET
  /api/v2/adminnotifies and the result of an anonymous treatment POST.
  Automating that needs a fixture that boots the app per configuration,
  which does not exist in this repo. The measurements and their controls are
  in the evidence document; the two source gates above are the cheap proxy
  and they measure presence, not behaviour.

## Evidence

- [`docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md`](../../docs/60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md)
- [`docs/30-design/remedial/security-advisory-disposition-2026-09-21.md`](../../docs/30-design/remedial/security-advisory-disposition-2026-09-21.md)
- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)

## Notes carried on the item

FOUND WHILE BUILDING THE CONTROL, not while looking for them - the
configuration matrix exists to answer "were the right flags set when the five
advisories were evaluated", and these two fell out of enumerating what
AUTH_DEFAULT_ROLES actually gates. REPRODUCED on v15.0.8 AND dev 59430336,
mongod 7.0, with both controls in the same run. BF-77: default -> notifyCount
1, title "Nightscout readable by world" (POSITIVE CONTROL, the notice does
fire when it should); TREATMENTS_AUTH=off -> notifyCount 0 while anonymous
read is 200 and anonymous POST /api/v1/treatments is 200 with the record
stored; AUTH_DEFAULT_ROLES=denied -> notifyCount 0, correctly (NEGATIVE
CONTROL, so absence in the middle row is attributable to the string compare
and not to the notice being broken generally). BF-78, anonymous POST
/api/v1/treatments: `readable careportal` 200 stored, `careportal` 401,
`denied careportal` 401, `denied` 401.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=ADV-CONFIG` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-21, against cgm-remote-monitor-official `59430336`.*
