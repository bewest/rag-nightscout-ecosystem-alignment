# `bf2/auth-hardening` — login security fixes, plus a setting that tells Nightscout which proxy to trust

**For the security reviewer. Not pushed, not opened.** Branch `bf2/auth-hardening` on
`origin/dev` `74fc6619`, tip `7103f657` (14 commits, 10 of them non-merge). **Ships in 15.0.9**
(decided 2026-09-23, backfix-2 plan §1a, superseding §3's "after 15.0.9 is tagged"). The combined
run with the other 15.0.9 additions is recorded in
`docs/30-design/remedial/rc-15.0.9-additions-c-2026-09-23.md`. Its posting summary is "Tested
together with the other 15.0.9 changes" below.

**Posted in the withheld style (maintainer, 2026-09-23, in answer to the question put directly;
this supersedes an earlier record in this file that said "posted in full").** BF-17 and BF-30 are
live on 15.0.8, so the public PR carries a short summary like #8744, #8745 and #8751: the four
changes, the `TRUST_PROXY` table and caution, the startup message, and the evidence. The posting
copy is [bf2-auth-hardening.withheld.md](bf2-auth-hardening.withheld.md). **This file is the full
text**, for the PR once a fixed release ships and the advisory is published; the rotation section
goes into the 15.0.9 release notes.

**`bf2/subject-edit-keeps-fields` (`7103f657`) is folded in as the final commit** (maintainer,
2026-09-23). Its parent is `29e6430e`, the previous tip of this branch, so it adds one commit and
changes nothing before it. The local `bf2/auth-hardening` ref still points at `29e6430e`;
fast-forward it to `7103f657` before pushing.

This branch combines two branches that were already reviewed on their own, adds one new setting,
and ends with one fix to the admin page's save:

| part | what it is | how it got here |
|---|---|---|
| `bf/auth` (BF-17, BF-47) | an access token was written into the database in readable form when a subject was edited | `git merge --no-ff`, ancestry kept |
| `bf/throttle` (BF-30) | the failed-login list was never cleared, had no size limit, held the secrets tried, and counted only the address; the wait stays before the credential check, as on `dev` (`f6f361b1`) | `git merge --no-ff`, ancestry kept, plus `f6f361b1` |
| `TRUST_PROXY` | a setting that tells Nightscout which proxy in front of it to trust | cherry-picked from `chore/nightscout-modernization` (#8605), `06c83f2f` and `395f3207`, plus one port commit |
| `bf2/subject-edit-keeps-fields` (BF-47) | editing a subject or role on the admin page wiped its `notes` and replaced its `created_at` | one commit, `7103f657`, on `29e6430e` |

No `CHANGELOG.md` edit. Merges clean into `dev`.

> **Read this before the diff.** If you change nothing, Nightscout behaves exactly as it does
> today. The stronger protection against password guessing applies **only once `TRUST_PROXY` is
> set**. With it unset, a caller who changes both the password they try and the address they
> claim to come from is still never delayed — the same as on the shipping release — and Nightscout
> now says so in its log at startup.
>
> The token fix is different: it is **on for everyone**, with no setting, because the old
> behaviour *was* the defect. It cannot undo what already happened. **Read "If you have ever
> edited a subject" below.**

---

## What changes for you

*Plain-language summary for people running their own Nightscout site. Nightscout is not a medical
device and none of this is medical advice.*

A few words used below:

- **Subject** — a named person or device on your Nightscout admin page (a parent's phone, an
  uploader, a follower) that gets its own **access token**, so you can give someone access without
  giving them your site's main password (`API_SECRET`).
- **Proxy** — a server that sits in front of Nightscout and passes visitors' requests on to it. Many
  hosting set-ups have one without you having set it up yourself: a hosting platform's router, a
  CDN, nginx, Apache, a Kubernetes ingress.
- **Forwarded headers** — labels a proxy attaches to each request, such as `X-Forwarded-For` ("this
  request really came from address …") and `X-Forwarded-Proto` ("the visitor used https"). The
  problem is that a visitor can attach the same labels themselves.

### 1. Editing a subject no longer writes its access token into your database

Tokens are not supposed to be stored — Nightscout recalculates each one every time it starts. But
editing a subject saved the recalculated token into the database in plain, readable text, so anyone
who could read your database (a backup, a snapshot, a copy you shared for support) could use it.
From this change on, tokens are never written. **Fixing the code does not remove copies already
written, and does not retire those tokens** — see the next section.

### 2. The failed-login delay also follows the password, and its list is bounded

After a failed login, Nightscout makes the next request from that address wait before it checks
the password, as every earlier release does, so a correct guess made during the wait is answered
no sooner than a wrong one. The wait now also follows the password or token that failed, wherever
it is tried from. The list of recent failures is cleared on a schedule and has a size limit;
before, it was cleared once and then grew for as long as Nightscout ran.

Every request from an address with recent failures waits, including ones with the correct
password. With `TRUST_PROXY` set to match the site, that address is the visitor's own, so only
people who really share an address (one home network, or a mobile carrier's shared address) share
a wait.

### 3. A new setting, `TRUST_PROXY`, and a warning in your log until you set it

Nightscout counts failed logins per visitor address. Today it takes that address from the
forwarded headers, **whoever sent them** — so a caller who changes the claimed address on every
attempt, and also changes the password they try, is never delayed. That is how every release up to
now behaves, and **with `TRUST_PROXY` unset it is still how this one behaves.**

`TRUST_PROXY` tells Nightscout whose forwarded headers to believe:

| `TRUST_PROXY` | what Nightscout believes | who should use it |
|---|---|---|
| not set (default) | forwarded headers from anyone — **exactly as today** | nobody needs to change anything to upgrade |
| `false` | no forwarded headers at all; the address actually connecting, and whether that connection itself is https | sites that visitors reach directly, with no proxy in front |
| your proxy's IP address(es) or ranges, comma-separated (for example `10.0.0.5` or `10.0.0.0/24`) | forwarded headers only when they come from those addresses | sites behind a proxy whose address you know |
| a whole number of hops, such as `1` | the entry added by the proxy that many hops from Nightscout | sites behind a known number of proxies whose addresses change, which is most hosted sites |
| `true` | every hop; the client is the left-most forwarded entry | only where every proxy in front rewrites the header |

Behind a trusted proxy that adds its entry to a forwarded header the caller may already have
filled in, the hop count back to that proxy is what makes the address trustworthy. The proxy guide
(`docs/proposals/trusted-proxy-migration.md`) has a table of the value each kind of deployment
needs. Forwarded addresses that carry a port (the form Azure App Service is reported to send) are
accepted by the explicit settings.

Once it is set, the failed-login delay counts attempts against an address the caller cannot make
up, and it starts doing its job.

**Be careful setting it behind a proxy that terminates https.** With `false`, or with a list that
does not include your proxy, Nightscout stops believing the proxy's "the visitor used https" label,
decides the visitor used plain http, and redirects them to https — over and over. If your site
stops loading after you set `TRUST_PROXY`, unset it and check your proxy's address. The address to
list is the one Nightscout **sees** the proxy connecting from, which on hosting platforms can change
or be shared; do not guess a range.

While `TRUST_PROXY` is unset, Nightscout logs this at startup:

> SECURITY: failed-authentication throttling is keyed on the client address, and TRUST_PROXY is not
> set, so that address is read from request headers (X-Forwarded-For and similar) that any caller
> can set. A caller who changes them, and the password or token tried, on every attempt is never
> delayed, so while TRUST_PROXY is unset this delay does NOT protect against guessing passwords or
> tokens. To key it on the real client address, set TRUST_PROXY to the IP address(es) or CIDR
> range(s) of the proxy in front of Nightscout, or to false if clients connect directly. Until then,
> restrict access at your proxy or hosting provider.

**Until you set it, restricting access at your proxy or hosting provider is what actually helps.**

### 4. Editing a subject keeps its notes and creation date

Opening a subject on the admin page and saving it, for example to give it another role, wiped its
notes and replaced the date it was created with the date of the edit. Both are now kept, for
subjects and for roles. You can still clear the notes on purpose by emptying the notes box and
saving. Notes and dates already lost to earlier edits cannot be recovered.

---

## If you have ever edited a subject: rotating the exposed tokens

**This is the part the code cannot do for you.**

If you have ever edited a subject (an access entry on your Nightscout admin page), a readable copy
of that subject's API access token is sitting in your database. **The stored row itself is not
rewritten by the upgrade.** The copy clears for a subject only when you next save that subject
through the admin page — and **clearing the copy does not retire the token.** Anyone who has had
read access to your database since the first edit could have used that token.

A Nightscout access token is not random. It is rebuilt every time from the subject's internal record
id, the subject's name and your site's `API_SECRET`, so the fixed code hands out **the same token**
it did before. There are exactly **two** ways to retire an exposed one:

| Option | What it retires | What breaks | Good for |
|---|---|---|---|
| **Do nothing** | nothing | nothing | Sites where only you have ever had database access and you are confident no backup or snapshot was shared |
| **Delete and re-create the subject** | that one subject's token | that one person or device must be given a new token | The normal choice — retires exactly the leaked credential |
| **Change your site's `API_SECRET`** | **every** subject token at once | everyone re-enters their token; anything using the API secret must be updated | A database copy left your control, or you cannot tell which subjects were edited |

**Renaming is not a rotation.** Renaming a subject changes only the short word at the front of its
token. The part Nightscout actually checks comes from the record id and your `API_SECRET`, and a
rename changes neither — so the old token keeps working even though it looks different. Delete and
re-create instead; that makes a new record id, which does change the token.

**How to check whether this affects you:** look in your `auth_subjects` collection for any document
with an `accessToken`, `accessTokenDigest` or `digest` field stored on it. If none has one, no edit
ever saved a token and there is nothing to rotate. If some do, those are the subjects to re-create.

**Do not paste a token, a digest or your `API_SECRET` into an issue, a forum post, a screenshot or a
chat message when asking for help** — those values are the credential itself.

If a token that could reach your data has been exposed and you are unsure what to do, treat it as
you would a shared password: retire it. If a care team is involved in your set-up, it is worth
telling them who can see your data.

---

## Settings this branch adds

The flag rule (maintainer, 2026-09-22): a fix is **on by default** when the old behaviour is itself
the defect; a **compatibility flag defaulting to today's behaviour** is used where a legitimate
deployment may rely on the old behaviour, and each flag names the release in which its default is
planned to flip.

| setting | default now | hardened value | planned flip | covers |
|---|---|---|---|---|
| `TRUST_PROXY` | unset: today's behaviour — forwarded headers believed from any peer, for client address, https detection and hostname | `false`, or an explicit list of proxy IPs/CIDRs | not yet planned | client-address trust, **and** the failed-login delay's keying (BF-30) |
| *(none)* — BF-17 token not written | on for everyone | — | — | not a flag: the old behaviour is the defect |
| *(none)* — BF-47 subject-field allow-list | on for everyone, as `bf/auth` has it | — | — | not a flag: decided 2026-09-23 that the allow-list is the intended schema; see Semver |

**There is one flag, not two.** The backfix-2 plan's flag registry lists a second row, "throttle
keying (name to be taken from `bf/throttle`)". `bf/throttle` has no such setting: it keys on
`data.ip`, and on this branch `data.ip` comes from `lib/server/client-ip.js`, so `TRUST_PROXY` is
what moves the throttle key. A separate throttle flag would let the two disagree about who the
client is.

`true`, hop counts and names like `loopback` are rejected at startup. `CUSTOMCONNSTR_TRUST_PROXY`
works too (the Azure convention).

---

## Technical detail

### Commits

| commit | what |
|---|---|
| `fd393cb1` | merge `bf/auth` (`a8f75da5` token not written, allow-list; `ce82f0cd` debug print of query options removed; `404e714c` merge-up) |
| `b4d1a0da` | merge `bf/throttle` (`435419ce`; `a0823c4f` merge-up) |
| `712c8854` | cherry-pick `06c83f2f` — `lib/server/client-ip.js`, `env.trustProxy`, all six `forwarded-for` consumers moved to it, Express `trust proxy` set from it, the `X-Forwarded-Proto` redirect bypass folded into `req.secure` |
| `708bbd4b` | cherry-pick `395f3207` — unset means compatibility, `false` means direct-only |
| `1114228d` | two cherry-picked tests adapted to `bf/throttle`'s delay-list interface |
| `8b975b41` | **port commit**: with `TRUST_PROXY` unset, the client address comes from `forwarded-for` exactly as on `dev` |
| `e701900a` | throttle tests under `TRUST_PROXY`, and the boot message |
| `29e6430e` | the proxy guide corrected to this branch's default |
| `7103f657` | `bf2/subject-edit-keeps-fields`: a subject or role save fills in `notes` and `created_at` from the stored document when the request leaves them out; `notes: ''` still clears; `roles` and `permissions` are never filled in |

### What was backported, and what it depends on

`06c83f2f` was written against Express 4.22.2, the Express `dev` has; it applied with one conflict,
a hunk to the modernization branch's own plan document, dropped. `395f3207` sits **after** the
Express 5 migration (`0ee4587e`) on #8605, but its code does not need it: `client-ip.js` needs only
`proxy-addr` (already installed, as an Express dependency; now declared) and `node:net`. Its test
file calls `lib/middleware/configure-request.js`, an Express 5 module, in one helper whose routes
never read `req.query`; that line is not carried. Its CI hunk edits a Docker smoke job `dev` does not
have, and its three planning-document hunks edit files `dev` does not have; all dropped.
`client-ip.js`'s trusted-proxy path, `env.js`, `README.md` and the `env` test are content-identical
to #8605.

### The one place this branch deliberately differs from #8605

The maintainer's rule is that the default is **today's** behaviour. `395f3207`'s default is a tidier
reimplementation of the `forwarded-for` package, and measured against `dev` `74fc6619` it is not
today's behaviour in four cases:

| case | `dev` today (and this branch) | `395f3207` |
|---|---|---|
| an IPv6 address after the first entry in a comma-and-space `X-Forwarded-For` chain | the whole chain is rejected; the connecting address is used | the first entry is used |
| an IPv4 address with a non-numeric port suffix | the suffix is stripped | the connecting address is used |
| no connecting address on the socket | headers, then `127.0.0.1` | `undefined` |
| more than one forwarding header on one request | whichever header family earlier requests used moves to the front | fixed order |

So `8b975b41` makes the default call `forwarded-for` itself, the same call `dev`'s six consumers
make, and keeps the dependency. Everything with `TRUST_PROXY` set is #8605's code, unchanged.
**If the reviewer prefers #8605's normalisation, drop `8b975b41` and change the four pinned values;
nothing else depends on it.** It is the single file that will conflict with #8605 on purpose.

HTTPS detection needed no port: with the default, `req.secure` gives the same answer `dev`'s
`X-Forwarded-Proto === 'https' || req.secure` does, for all seven values measured.

### The throttle under `TRUST_PROXY`

No throttle code changes. `bf/throttle` keys on `data.ip`; `data.ip` now comes from
`client-ip.js`; so with `TRUST_PROXY` naming a boundary the address key is one the caller cannot
choose. `bf/throttle`'s table, extended:

| what varies between attempts | `TRUST_PROXY` unset | `TRUST_PROXY` set |
|---|---|---|
| nothing | throttled | throttled |
| the claimed address only | throttled (credential key) | throttled |
| the credential only | throttled (address key) | throttled |
| **both** | **not throttled** | throttled |

BF-30 is therefore closed **only where `TRUST_PROXY` is set**. With the default it is open, as on
15.0.8, and the boot message and this body say so.

The boot message (`lib/authorization/delaylist.js`) now names `TRUST_PROXY`, says the delay does
**not** protect against guessing while it is unset, and is logged only then; a configured boundary
logs one line saying which setting the key comes from. `bf/throttle`'s version named no setting,
because none existed on that branch.

### Test changes to existing tests — called out

- `tests/client-ip.test.js` (from #8605): two tests' **calls** changed to `bf/throttle`'s
  `keysFor()` interface (expectations unchanged); one test's **expectations** changed in two places
  to `dev`'s answers (history-dependent precedence; the IPv6 chain case). Each is marked in-file.
- `tests/authdelay.test.js` (from `bf/throttle`): the gap test is **unchanged** and still passes
  under the default. Its comment says it would one day invert; it gains a paragraph saying the
  positive assertion now lives in the `TRUST_PROXY` block beside it.

---

## Test evidence

```
TEST=client-ip    npm run test-single    # 48 passing
TEST=authdelay    npm run test-single    # 19 passing
TEST=authsubjects npm run test-single    # 8 passing
TEST=env          npm run test-single    # 28 passing
npm test                                 # 2462 passing, 0 failing, 3 pending
```

`origin/dev` `74fc6619`, same machine, same Node (20.20.0), back to back: 2386 passing, 0 failing, 3 pending. The difference, 76, is exactly the four files above (48 + 19 + 8, plus one new `env` test). These counts are at `29e6430e`. `7103f657` adds 5 `authsubjects` tests (13 in all); its step on the integrated tree is recorded under "Tested together with the other 15.0.9 changes". Against mongod 7 started with `--ulimit nofile=64000:64000`, and with a database name containing `test` — `tests/mongo-storage.test.js` fails on both arms otherwise.

**None of `client-ip`, `authdelay` or `authsubjects` is in `npm run test:unit` or `npm run
test:integration`.** A green `test:unit` is not evidence for any of this; use `npm test`, which is
what CI runs. `authdelay` and `authsubjects` need MongoDB.

Every new test was broken to prove it, and each broken run failed on the original symptom:

| break | result |
|---|---|
| `client-ip.js` restored to `395f3207` | 7 fail: the four measured differences, history dependence, the authorization/API v3 pin, the changed legacy test |
| unset default flipped to trust nothing | `client-ip`: 23 fail, including the https pin; `authdelay`: 5 fail (the gap test, default keying, three boot-message tests) |
| `lib/authorization/index.js` resolves the address without `TRUST_PROXY` | 4 fail: all three `TRUST_PROXY` throttle tests and the configured-key test |
| every address shares one key | 3 fail, including "keeps a different real client on its own counter" |
| boot message says "offers little protection against guessing" | 1 fails |
| boot message names a setting that does not exist | 1 fails |
| the address key dropped from `keysFor()` | the two adapted `client-ip` delay tests fail |

## Checked against #8605

`git merge-tree --write-tree --name-only bf2/auth-hardening origin/chore/nightscout-modernization`
(`b1bdaca0`) conflicts in: `docs/proposals/trusted-proxy-migration.md`, `lib/api/index.js`, `lib/api/status.js`, `lib/api3/index.js`, `lib/authorization/storage.js`, `lib/server/bootevent.js`, `lib/server/client-ip.js`, `package-lock.json`, `package.json`, `tests/client-ip.test.js`. Of those, `lib/server/bootevent.js` conflicts from
`origin/dev` alone and `lib/authorization/storage.js` from `bf/auth` alone (both known before this
branch). `lib/server/client-ip.js`, and the proxy guide corrected to match it, are the deliberate difference above. The rest come from the
cherry-picks sitting next to lines #8605 later changed for Express 5, Helmet and dependency
upgrades — adjacent-line conflicts, not disagreements about client-address trust.

## Semver

The subject allow-list means `save()` writes only `name`, `roles`, `notes`, `created_at`
(subjects) and `name`, `permissions`, `notes`, `created_at` (roles). A field a third-party admin tool
stored on a subject or role, and sends back in its own save, is dropped.

**Decided 2026-09-23 (maintainer):** the allow-list is the declared schema for subjects and roles, so
fields outside it are not part of the contract. It stays as `bf/auth` has it, with no compatibility
flag. The branch ships in 15.0.9, and the release notes declare the allow-list as a correction.
`TRUST_PROXY` is a new setting with today's behaviour by default, and the throttle changes are fixes.

The remaining BF-47 defect, the admin page clearing `notes` and `created_at` on every edit, is fixed
by `bf2/subject-edit-keeps-fields` (`7103f657`), the final commit on this branch.

**The operator text above belongs in the release notes, not `CHANGELOG.md`.** What must survive
verbatim: the whole "If you have ever edited a subject" section, including the rotation table and
**Renaming is not a rotation**, and the instruction not to paste a token, digest or `API_SECRET`
anywhere when asking for help; and the paragraph saying that with `TRUST_PROXY` unset the delay does
not protect against guessing and restricting access at the proxy is what helps. A note listing only
the fixes would leave an operator believing guessing is handled.

## Follow-ups deliberately not in this PR

- **A planned flip for `TRUST_PROXY`.** None is set. Until one is, the default is a permanent
  setting and must be documented as one.
- **Detecting the evasion.** Counting distinct claimed addresses arriving from one connecting
  address would turn the boot warning into a signal. It belongs in `client-ip.js`.
- **BF-17's `created_at` residual** (`endpoints.js` does not return `created_at`), carried from
  `bf/auth`.

## Tested together with the other 15.0.9 changes

On a local integration branch cut from `dev` `74fc6619`, this branch at `29e6430e` was merged sixth
of eight: after #8750, #8749, #8748, #8751 and `bf2/ops`, and before `bf2/subject-edit-keeps-fields`
and the connector pin. The merge had no conflicts. The full suite went from 2427 to 2503 passing,
with 0 failing and 3 pending, on Node 20.20.0 and MongoDB 7.0.43. The difference is this branch's
76 tests, and no other test changed state. `bf2/subject-edit-keeps-fields` (`7103f657`, now this
branch's final commit) was merged seventh, as its own step: 2503 to 2508 passing, 0 failing,
3 pending, the difference being its 5 tests. After all eight merges, the full suite passes on Node 20,
22 and 24 against both MongoDB 4.4.24 and 7.0.43 (2508/0/3 each).

**`lib/api/index.js` is also edited by #8748** (the v1 `count` rule). This branch adds one line near
the top of the file, which sets the v1 app's `trust proxy` from `TRUST_PROXY`. #8748 changes the
`validateCount` middleware further down, which reads only the request method and `req.query`. The
hunks are textually and functionally disjoint. On the merged file, all of #8748's count rules were
checked against a running server, and this branch's client-address tests all pass.

That one line in `lib/api/index.js` is not covered by any test. With it removed from the integrated
tree, the full suite still passes (2508/0/3). This is because Express gives a mounted sub-app its
parent's `trust proxy`, and `lib/server/app.js` sets the same value on the parent. A direct check
with Express showed the same `req.ip` and `req.secure` with and without the line, when mounted,
for `TRUST_PROXY` unset, `false` and a list. No code under `lib/api/` reads `req.ip`, `req.secure`,
`req.protocol` or `req.hostname`. The line is inert under `lib/server/app.js` today, because
Express 4 sub-apps inherit the parent's `trust proxy` setting. It is kept because it comes from
`712c8854`, the cherry-pick of `06c83f2f` that is content-identical in every path it carries, and
trimming it would break the backport-identical rule.

Each break was repeated on the integrated tree, and each failed on its original symptom:

| break | failing |
|---|---|
| `client-ip.js` restored to `395f3207` | 7 (`client-ip`) |
| unset default flipped to trust nothing | 28: 23 `client-ip`, 5 `authdelay` |
| `lib/authorization/index.js` resolves the address without `TRUST_PROXY` | 5: 4 `authdelay`, 1 `client-ip` (the configured address through HTTP authorization) |
| every address shares one key | 5: 3 `authdelay`, 2 `client-ip` |
| the address key dropped from `keysFor()` | 9: 7 `authdelay`, 2 `client-ip` |
| `save()` writes the request body unfiltered | 5 of 13 `authsubjects`: the three token tests and the two allow-list tests; the access token is found in the stored document |

The counts across two files are larger than those in "Test evidence" above, which counted the file
named in each row.
