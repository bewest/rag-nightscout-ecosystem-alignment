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

# Review packet — BF2-AUTH (PR #8754)

**bf2/auth-hardening - bf/auth + bf/throttle + the client-ip.js backport behind
TRUST_PROXY**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf2/auth-hardening` |
| base | `origin/dev@74fc6619` |
| claimed state | `in-flight-upstream` — a claim; `make queue-status ID=BF2-AUTH` is the measurement |
| semver | `major` |
| register entries | `BF-17`, `BF-30` |

## What this changes

#8754 head e549e1a6 (2026-09-24) against dev 153e5658: 27 commits, 22 files,
+2063/-100. lib/authorization/{index,delaylist,storage,endpoints}.js;
lib/server/{client-ip,env,app,websocket}.js; lib/api/status.js;
lib/api3/{security,alarmSocket,storageSocket}.js; package.json and lock
(proxy-addr declared, forwarded-for kept); README.md and
docs/proposals/trusted-proxy-migration.md; tests authdelay, authsubjects,
client-ip, env and server.security-headers. Measured with the GitHub compare
API.

## Why that semver

Inherits P0-C's major (the BF-47 allow-list), unless the maintainer's BF-47
decision puts that behind a compatibility flag, which would make this minor (a
new setting, today's behaviour by default).

## What an operator would notice

> Not released. This combines several login and access fixes planned for
> 15.0.9. Editing a subject (an access entry on the admin page) no longer
> writes that subject's access token into your database in readable form;
> tokens already written that way stay until you act (see P0-C-REMEDIATE for
> what to do). Editing a subject on the admin page no longer wipes its notes
> or its creation date. After a failed login, Nightscout still makes the
> next request from that address wait before it checks the password, as
> earlier releases do; the wait now also follows the password or token that
> failed, and the list of recent failures is bounded and cleared on a
> schedule. A new setting, TRUST_PROXY, tells Nightscout which proxy in
> front of it to trust, so that the address it counts failed logins against
> is one a visitor cannot make up; explicit TRUST_PROXY settings accept
> forwarded addresses that carry a port (the form Azure App Service is
> reported to send). If you change nothing, Nightscout works out visitor
> addresses as it does today, and it says in its log at startup that the
> protection against password guessing is weaker until TRUST_PROXY is set.
> None of this is medical advice.

## Who should review this, and why

SECURITY - the maintainer and Andy (decided 2026-09-23). No review is recorded
on #8754 as of 2026-09-24.

## What was measured

**`git -C externals/cgm-remote-monitor-official merge-base --is-ancestor bf/auth bf2/auth-hardening && git -C ext`** &nbsp;·&nbsp; kind: `static`

Contains both source branches by ancestry, not re-implementation.

**`git -C externals/cgm-remote-monitor-official merge-tree --write-tree origin/dev bf2/auth-hardening >/dev/null`** &nbsp;·&nbsp; kind: `static`

Merges into origin/dev with no conflict.

**`git -C externals/cgm-remote-monitor-official cat-file -e bf2/auth-hardening:lib/server/client-ip.js`** &nbsp;·&nbsp; kind: `static`

The client-address module is present. Its default being today's behaviour is
asserted by the branch's own tests, not here.

**`cd externals/work/crm-bf2-auth && n exec 20.20.0 npx mocha --timeout 10000 --exit tests/client-ip.test.js`** &nbsp;·&nbsp; kind: `unit`

48 cases, no database. Pins dev's client address, HTTPS detection and hostname
with TRUST_PROXY unset (0, 1 and 2 hops, history dependence). Control, re-run
2026-09-22 - restoring 395f3207's client-ip.js fails exactly 7; flipping the
unset default to trust nothing fails 23.

**`cd externals/work/crm-bf2-auth && TEST=authdelay npm run test-single`** &nbsp;·&nbsp; kind: `integration`

19 cases - default keying, the documented default gap, throttling under a
configured TRUST_PROXY, and the boot message's claims. Flipping the unset
default fails 5; bypassing TRUST_PROXY in authorization/index.js fails 4.

## What these gates do NOT prove

*No `no-gate:` markers on this item — every declared property has a runnable measurement. That is rare in this manifest and worth confirming rather than assuming.*

## Evidence

- Drafted PR body: [`reports/phase0-pr-bodies/bf2-auth-hardening.md`](../../reports/phase0-pr-bodies/bf2-auth-hardening.md)
- [`docs/30-design/remedial/backfix-2-plan-2026-09-22.md`](../../docs/30-design/remedial/backfix-2-plan-2026-09-22.md)
- [`docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md`](../../docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md)

## Notes carried on the item

Open upstream as #8754, not merged. Head e549e1a6 (2026-09-24). It carries dev
153e5658 (merged in by e32f7a1c); f6f361b1, which puts the failed-login wait
back before the credential check, as in earlier releases; 9c6cde72 (an
explicit TRUST_PROXY accepts a forwarded address that carries a port, the form
Azure App Service is reported to send; unset is unchanged); b5f61f19 (the
proxy guide recommends `1` on Azure); and e549e1a6 (an API v3 failed-login key
test through the trust its app inherits). Full suite 2570/3/0 at e549e1a6
(session -66); CI green on b5f61f19. That fix is part of #8754 and 15.0.9.
Destination 15.0.9 (backfix-2 plan section 1a, 2026-09-23). Reviewers: the
maintainer and Andy (security review); no review is recorded on the PR yet
(2026-09-24). Owed before merge: the security review and a combined run on
e549e1a6; the latest combined run (rc-15.0.9-combined-010, 3046/0/3) used
#8754 at ef3404fd. What it carries: bf/auth (BF-17, P0-C) and bf/throttle
(BF-30, P0-J) by ancestry; the client-address module and TRUST_PROXY setting
cherry-picked (-x) from chore/nightscout-modernization (06c83f2f, 395f3207),
with 8b975b41 a port so that with TRUST_PROXY unset the address comes from
forwarded-for exactly as on dev (395f3207's default differs in four cases,
BF-88); the subject-edit fix 7103f657 (BFQ-47) as its last content commit. The
failed-login delay: the wait comes before the check, as in earlier releases;
failures are also counted per credential; the list is bounded and swept on a
schedule. The throttle keys on data.ip, which comes from client-ip.js, so one
setting governs both. BF-30 is closed only when TRUST_PROXY names a boundary;
with the default it remains open, and the branch says so in its boot message
and PR body. Semver stays major for BF-47 (a compatibility flag, sketched in
the PR body, would make it minor; the maintainer decided none). Decisions: -
2026-09-23 (maintainer): ships in 15.0.9, superseding the plan's section 3
"PRs open after 15.0.9 is tagged". - 2026-09-23 (maintainer): posted in the
withheld style (reports/phase0-pr-bodies/bf2-auth-hardening.withheld.md); the
full text is kept for after a fixed release, and the rotation section goes
into the 15.0.9 release notes. bf2/subject-edit-keeps-fields folded in as the
final commit. - 2026-09-23 (maintainer): TRUST_PROXY accepts a hop count and
true, with Express's meaning for each; Express's subnet aliases (loopback,
linklocal, uniquelocal) are refused, and accepting them is deferred to a later
release. The inert trust proxy lines in lib/api/index.js and lib/api3/index.js
are trimmed (the sub-apps inherit trust proxy from lib/server/app.js). -
2026-09-23 (maintainer): the security reviewers are the maintainer and Andy.
Measured facts a reviewer needs: lib/api3/security.js:34 reads app.get('trust
proxy fn') for the v3 token throttle key, and the inherited fn equals the
parent's for unset, false, 10.0.0.0/8, 1 and true, so the api3 trim is inert
in production; tests/fixtures/api3/instance.js has no parent trust proxy, so
no test covers the v3 throttle key under the production default.
chore/nightscout-modernization b1bdaca0's lib/server/client-ip.js still
refuses hop counts and true, and needs the same change at the cut rebase
(RT-3).

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BF2-AUTH` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-24, against cgm-remote-monitor-official `153e5658`.*
