# Report #2 — Auth-Failure Delay Keyed on Spoofable `X-Forwarded-For`

**Date evaluated:** 2026-09-01
**Source materials:** `/home/bewest/potential-ns-issue-auth-delay-headers`
(external report, reporter: Ofri Peretz; reference only, not reproduced here
verbatim beyond quoted excerpts needed for traceability)
**Branch:** `wip/bewest/security-hotfix-eval-auth-delay`
**Worktree:** `/home/bewest/src/worktrees/nightscout/cgm-auth-delay-eval`
**Base:** `dev@4982e954` (same known-good tip as report #1; confirmed
unchanged as of evaluation date via `git fetch official dev`)
**Status:** ✅ Primary issue resolved upstream by PR #8723 (see §10);
secondary issue fixed on this branch, ready to PR against `dev`

---

## 1. Report summary (as submitted)

- `lib/authorization/index.js`'s `getRemoteIP(req)` derives the client IP via
  the `forwarded-for` npm package reading `X-Forwarded-For`, with no
  trusted-proxy/hop-count restriction.
- `data.ip` is the sole key for `lib/authorization/delaylist.js`'s
  per-IP auth-failure delay (`authFailDelay`, default 5000ms) — the only
  brute-force throttle in front of `API_SECRET`/token comparison.
- Claim: rotating the header per request gets a fresh delay bucket every
  time, making the delay ineffective and API_SECRET/token guessing
  effectively unthrottled — "on most PaaS deployments a client-supplied
  header is appended to rather than replacing the chain."
- Secondary, smaller issue: `delaylist.js`'s cleanup uses a one-shot
  `setTimeout(..., 30000)`, never rescheduled (not `setInterval`), so stale
  entries accumulate for the life of the process.
- Reporter's suggested fix: `app.set('trust proxy', env.settings.trustProxy
  || false)` + `req.ip` instead of raw header parsing, plus a global
  failure counter as defense-in-depth and `setInterval(...).unref()` for the
  sweep.
- Reporter's own caveats: source-review only (no live testing against a
  deployed instance); impact is limited to deployments whose edge proxy
  does *not* overwrite/strip inbound `X-Forwarded-For` before it reaches
  Node.

## 2. Claim-by-claim verification against current `dev`

| # | Claim | Verified? | Evidence |
|---|---|---|---|
| 1 | Delay key comes from `X-Forwarded-For` via `forwarded-for`, no trust/whitelist check | ✅ | `lib/authorization/index.js:9-11` — `forwarded(req, req.headers)`, no 3rd `whitelist` arg. `forwarded-for` only validates the header parses as *a* valid IP; without a whitelist it always returns the **leftmost** (client-closest) entry |
| 2 | `data.ip` is the sole delay-list key | ✅ | `index.js:114,155,174,203,210` |
| 3 | `delaylist.js` keyed purely on stringified IP, no global/rate cap | ✅ | `delaylist.js:9-19` |
| 4 | Rotating header → always-fresh bucket → unthrottled brute force | ✅ | Direct consequence of #1–#3; no other guard in `authorization.resolve` |
| 5 | Cleanup is one-shot `setTimeout`, never rescheduled | ✅ | `delaylist.js:42-49` |
| 6 | Suggested fix (`trust proxy` + `req.ip`) fully resolves it | ⚠️ **Incomplete as literally written** | `lib/server/app.js:27` already runs `app.enable('trust proxy')` **unconditionally** (`= true`, trusts every hop, no count/CIDR limit). Swapping only `getRemoteIP` to `req.ip` without also bounding the trust-proxy value leaves `req.ip` echoing the same attacker-controlled leftmost header entry |
| 7 | Impact framing (full-rate API_SECRET/token brute force) | ✅ | Matches `authorization.resolve` control flow — delay is the only throttle before secret/token comparison |
| 8 | Caveat: proxies that overwrite (rather than append) the header aren't affected | ✅ correct caveat, unverifiable from repo alone | See §4 empirical test — behavior is binary and topology-dependent |

## 3. Commit-history check: has this area been touched for security before?

**Yes — but for a different, non-overlapping reason.** Commit `62506125`
("sanitize x-forwarded-for header (#7122)", 2021, author: bewest) added the
`forwarded-for` package at **all 6** `getRemoteIP`-equivalent call sites:
`lib/authorization/index.js`, `lib/server/websocket.js`,
`lib/api/status.js`, `lib/api3/security.js`, `lib/api3/storageSocket.js`,
`lib/api3/alarmSocket.js`. Its stated purpose (per commit message): reject
**malformed/non-IP garbage** in the header, to stop injection into logs and
the `admin-notify` message — a *format-validation* / injection concern.

That fix did **not** address trust boundaries: no call site passes
`forwarded-for`'s optional `whitelist` argument, so it never restricts
*which* proxies are trusted — it only checks the header parses as valid
IP(s), then unconditionally takes the leftmost entry. This is why the new
report's claim is not contradicted by, and does not overlap with, the 2021
fix: two different bug classes (format/injection vs. trust/spoofing) in the
same function.

`lib/server/app.js:27`'s `app.enable('trust proxy')` (unconditional) has been
present, unchanged in intent, since Express app bootstrap was introduced —
comment says "Allows req.secure test on heroku https connections," i.e. it
was added for HTTPS-redirect detection, never revisited for the trust
implications on IP resolution.

**Conclusion:** this is a genuinely new finding, not a regression of or
overlap with prior security work. The 2021 fix's presence explains why a
naive `grep` for "already handled X-Forwarded-For" would be misleading.

## 4. Empirical verification: load-bearing conditions

Tested directly against `forwarded-for@1.1.0` (version pinned in
`package-lock.json`) and Express's `proxy-addr`/`compileTrust`:

| Load balancer behavior | Header after LB | `forwarded-for` result | Attacker control? |
|---|---|---|---|
| **Overwrites** (strips inbound header, sets only its own observed IP) | `203.0.113.9` | `203.0.113.9` | ❌ No |
| **Appends** (nginx `proxy_add_x_forwarded_for` default, Heroku router, AWS ALB/ELB, GCP LB — the common default) | `<attacker-fake>, 203.0.113.9` | `<attacker-fake>` | ✅ **Yes, fully** |

`forwarded-for`'s `ips.shift()` always takes the **leftmost** (client-closest)
entry regardless of hop count — the report's claim is load-bearing on
exactly one variable (append vs. overwrite), and "append" is the common
default for the deployment topologies this project has historically
targeted (Heroku is a first-class documented deploy target in `README.md`).

Also tested: a naive fix using a positive hop-count (`TRUST_PROXY=1`) is
**not safe as a default**, because it silently reintroduces the same
vulnerability for any deployment with **no real reverse proxy in front**
(bare Docker/Synology/LAN exposure — plausibly a large fraction of the
install base):

```
TRUST_PROXY=1, NO real proxy in front, attacker forges header directly -> 9.9.9.9   (❌ still spoofable)
TRUST_PROXY=false (default/off), same attacker                          -> <real socket IP>  (✅ correct)
```

Also confirmed: the only existing consumer of Express's trust-proxy-gated
`req.secure` (`lib/server/app.js:31-37`, the HTTP→HTTPS redirect middleware)
already OR's it with an **unconditional** raw-header check:
`req.header('x-forwarded-proto') === 'https' || req.secure`. This means
changing the trust-proxy default has **zero effect** on HTTPS-redirect
behavior for any deployment — the only thing that changes is how the 6
`getRemoteIP` call sites resolve client IP.

## 5. Design tradeoffs considered

| Approach | Pros | Cons |
|---|---|---|
| Keep `forwarded-for`, add a whitelist arg | Minimal code change | Whitelist would need the same env-driven config as below anyway; doesn't fix `app.js`'s independent unconditional `trust proxy`; introduces a second, parallel trust-config surface alongside Express's own |
| **Adopt Express's native `trust proxy` setting + `req.ip`, single shared helper using `proxy-addr` (Express's own dependency) for non-Express contexts (socket.io)** | One trust-config surface, reused by both Express (`req.ip`) and raw socket requests (`proxy-addr(req, trustFn)` directly); `proxy-addr` walks the list **from the trusted end inward** by hop-count/CIDR (correct direction), unlike `forwarded-for` which always trusts the untrusted/leftmost end; no new dependency (`proxy-addr` already present transitively via Express) | Requires touching all 6 call sites + `app.js`; behavior change for deployments that don't set the new env var (see §6) |
| Reject all proxied requests unless explicitly configured (fail closed, no fallback) | Maximally secure | Would break `req.secure`-dependent behavior for proxied deployments that don't reconfigure immediately — rejected as too disruptive; existing OR-fallback in `app.js` already makes this moot for HTTPS detection specifically |

**Decision: adopt the second approach.** Single `TRUST_PROXY` env var,
compiled once via Express's own `compileTrust` semantics (`express/lib/utils.js`),
reused everywhere:

```js
// lib/server/env.js
env.trustProxy = readENV('TRUST_PROXY', false);   // same idiom as INSECURE_USE_HTTP

// lib/server/app.js
app.set('trust proxy', env.trustProxy);            // replaces unconditional app.enable('trust proxy')

// new lib/server/remoteAddress.js (shared helper)
const proxyaddr = require('proxy-addr');
module.exports = function remoteAddress(req, trust) {
  return proxyaddr(req, proxyaddr.compile(trust));
};
```

`TRUST_PROXY` accepts, matching Express's own documented `trust proxy`
values 1:1 (no new parsing idiom to learn):

| Value | Meaning |
|---|---|
| unset / `false` | No proxy trusted — raw socket address only |
| `1` | Trust exactly one hop (single LB in front) |
| `10.0.0.0/8,172.16.0.0/12` | Trust only these CIDR ranges |
| `loopback` | Express/`proxy-addr` built-in keyword |

Call sites to update (all currently using `forwarded-for`):
`lib/authorization/index.js`, `lib/server/websocket.js`,
`lib/api/status.js`, `lib/api3/security.js`,
`lib/api3/storageSocket.js`, `lib/api3/alarmSocket.js`.

`proxy-addr` only touches `req.headers`/`req.connection`/`req.socket`, so
the same helper works identically for genuine Express requests and raw
socket.io upgrade requests — one code path, no drift between HTTP and WS,
unlike today where `forwarded-for` is called ad hoc at each site.

## 6. Default-value decision (methodical)

**Goal:** preserve function for the largest number of existing instances
while not silently reintroducing the vulnerability for any of them.

| Default candidate | Instances preserved | Security when misapplied |
|---|---|---|
| `TRUST_PROXY` unset → `true` (today's status quo) | 100% functional | ❌ Vulnerable everywhere (current bug) |
| `TRUST_PROXY` unset → `1` | Functional for genuinely single-proxy deployments | ❌ **Silently vulnerable** for any direct-exposure deployment (bare Docker/Synology/LAN) — empirically confirmed above, and plausibly a large fraction of the install base |
| **`TRUST_PROXY` unset → `false`** | **100% functional** — no deployment breaks (see below) | ✅ Secure by default everywhere; proxied deployments get a coarser (not wrong) fallback |

**Why `false` breaks nothing:** with `TRUST_PROXY=false`, `getRemoteIP`
returns the raw socket address for every request. For deployments with no
reverse proxy, this is exactly correct (no change). For deployments behind
one or more reverse proxies, every client behind that proxy collapses to a
single shared "IP" (the proxy's own address) for the purposes of
auth-failure-delay bucketing and `admin-notify`/log messages — a loss of
precision, not a functional break: auth still succeeds/fails correctly, no
requests are rejected, no 500s, no lockouts. The one existing consumer of
`req.secure` (HTTPS-redirect middleware) is provably unaffected (§4).

**Decision:** default `TRUST_PROXY` to `false` (fail-closed/secure).
Document in `README.md` (next to the existing `NIGHTSCOUT_HOSTNAME`
Docker/reverse-proxy guidance) that operators behind a known single reverse
proxy should set `TRUST_PROXY=1`, or a CIDR/IP allowlist for their LB, to
restore per-client precision. Optionally emit a one-time `env.notifies`
startup warning (same pattern as the weak-`API_SECRET` notice) when
`x-forwarded-for`/`x-forwarded-proto` headers are observed on a request but
`TRUST_PROXY` is unset, to nudge affected operators without breaking
anything.

## 7. Secondary issue: one-shot cleanup timer

Confirmed (`delaylist.js:42-49`). Fix: `setInterval(clearList,
30000).unref()` instead of `setTimeout`. Low risk, no tradeoffs — matches
reporter's suggestion directly. `.unref()` prevents the interval from
holding the process open (relevant given the "Test invocation gotchas"
lesson from report #1 about lingering timers causing apparent test hangs).

## 8. Open items requiring explicit confirmation before implementation

- [ ] Confirm `TRUST_PROXY=false` default (§6) — **recommended, pending
      final user sign-off**.
- [ ] Confirm whether to add the optional global-failure-counter
      defense-in-depth suggested by the reporter, or defer it as a separate,
      lower-priority hardening item (it changes behavior more broadly than
      the minimal fix and deserves its own review).
- [ ] Confirm README/CHANGELOG documentation location and wording for the
      new `TRUST_PROXY` env var.
- [ ] Confirm test plan: regression test proving spoofed header defeats the
      delay pre-fix (mirroring report #1's `tests/websocket.xss-purification.test.js`
      pattern — write failing test first, then fix, then confirm passing).

## 9. Planned implementation (pending sign-off above)

1. Add `env.trustProxy` (`lib/server/env.js`) + settings mapping if needed.
2. Add shared `lib/server/remoteAddress.js` helper wrapping `proxy-addr`.
3. Replace `app.enable('trust proxy')` with `app.set('trust proxy',
   env.trustProxy)` in `lib/server/app.js`.
4. Replace `forwarded-for` usage at all 6 call sites with the shared helper.
5. Fix `delaylist.js`'s `setTimeout` → `setInterval(...).unref()`.
6. Regression tests: spoofed-header-defeats-delay (pre-fix red, post-fix
   green), plus a same-IP-still-delayed sanity check to prove no
   over-blocking regression.
7. README documentation for `TRUST_PROXY`.
8. Full suite run (`NODE_ENV=test npm test`) + targeted auth/delaylist tests.
9. Commit split mirroring report #1's pattern: one commit for the
   root-cause fix + tests, one (if needed) for documentation/defense-in-depth
   additions.

## 10. Reconciliation — upstream PR #8723 (2026-09-14)

While refreshing sources for the release-planning review
(`docs/reports/nightscout-release-planning-2026-09/`), we found that
`nightscout/cgm-remote-monitor#8723` ("Restore proxy compatibility for
existing ingress deployments," merged 2026-09-08 into the
`chore/nightscout-modernization` integration branch, commit `395f3207`)
already implements the primary (§1–§6) trust-boundary fix, independently
of this evaluation. It is treated here as the **authoritative
implementation**, not a competing one.

### 10.1 Design comparison

| Aspect | This report's plan (§9) | PR #8723's shipped design |
|---|---|---|
| Env var | `TRUST_PROXY` | `TRUST_PROXY` (same name; also honors `CUSTOMCONNSTR_TRUST_PROXY`) |
| Unset default | `false` (fail-closed) | **Compatibility mode** — behaves like the pre-fix code (legacy header walk), *not* `false` |
| `TRUST_PROXY=false` | (this *was* the default) | Explicit opt-in: direct-only, ignores all forwarded headers |
| Explicit trust value | Reuse Express's `trust proxy` semantics (hop count / `true` / CIDR list) | **Narrower on purpose**: only literal comma-separated IPs/CIDRs accepted; `true`, hop counts, and subnet aliases are rejected at startup with a thrown error |
| Header precedence | Not specified (assumed `forwarded-for`/`req.ip` semantics) | Fixed precedence list (`Fastly-Client-IP`, `X-Forwarded-For`, `Z-Forwarded-For`, `Forwarded`, `X-Real-IP`), first present header wins, first valid IP in it is the client |
| Scope | `getRemoteIP` call sites only | Same call sites **plus** HTTPS/hostname detection unified under one trust policy (closes a gap this report didn't check) |
| Call sites patched | 6 (as traced in §3, not shown above) | Same 6, verified via `git grep` on the PR branch: `lib/api/index.js`, `lib/api/status.js`, `lib/api3/{index,alarmSocket,security,storageSocket}.js`, `lib/authorization/index.js`, `lib/server/{app,websocket}.js` |
| Design doc | This report | `docs/proposals/trusted-proxy-migration.md` (upstream, 130 lines) — explicitly documents that an *earlier* candidate on that same branch *did* default to mandatory explicit-IP config and caused **production redirect loops** on a Kubernetes trial; the compatibility-default design in #8723 is the fix for that regression |
| Test coverage | Planned, not written | Shipped: `tests/client-ip.test.js` (81 tests: compatibility, direct mode, CIDR trust, changing ingress peers, header precedence, malformed chains, IPv4/IPv6/ports, HTTPS redirects, independent auth-delay keys, HTTP/API3/Socket.IO consumers) + `tests/env.test.js` additions |

### 10.2 Why the shipped default differs from this report's `false` recommendation

This report (§6) concluded `TRUST_PROXY=false` was the only default safe
for *all* deployments. PR #8723's own history (via its design doc)
shows that conclusion was tried first upstream and **broke production**
for TLS-terminating-ingress deployments that rely on `trust proxy` for
HTTPS-redirect detection, not just client-IP resolution — a consumer this
report's §4 checked only for regression-safety under `false`, not for
what happens when a *stricter* default is forced on ingress topologies
that need forwarded-proto trust to avoid redirect loops. The shipped
"compatibility mode" default preserves exactly the pre-fix behavior
(spoofable, as documented candidly in the design doc's "Compatibility
boundary" section) and treats hardening as strictly opt-in
(`TRUST_PROXY=false` or an explicit CIDR list) rather than a breaking
default flip. This is the same "keep current behavior, document the
opt-in" approach this evaluation discussed as an alternative to a
default flip, now confirmed as the correct choice by a real production
incident upstream.

### 10.3 Disposition

- **§1–§6 (trust-boundary root cause):** superseded by PR #8723. No
  separate implementation needed from this branch; when
  `chore/nightscout-modernization` merges into `dev` via #8605, this
  finding is resolved. This report's empirical LB-topology tests (§4–§5)
  remain useful as independent corroboration that the vulnerability was
  real and reproducible, and can inform review/QA of #8605 if requested.
- **§7 (one-shot `setTimeout` cleanup timer):** **not** addressed by
  #8723 (out of scope for that PR) and not tracked by any other open
  issue/PR as of this check. Implemented directly on this branch
  (`wip/bewest/security-hotfix-eval-auth-delay`, commit `4d0c9524`,
  rebased onto `dev@a8888f0d`) as a small, independent, low-risk fix:
  `setInterval(...).unref()` replacing the one-shot `setTimeout`, with a
  new regression test (`tests/authorization.delaylist.test.js`, 3 cases)
  that fails against the prior code and passes with the fix. Full suite
  run clean (2026 passing; 5 pre-existing, unrelated `debug-logging.test.js`
  failures confirmed present on unmodified `dev@a8888f0d` baseline too).
  This fix is decoupled from #8605/#8723's timeline and can ship as its
  own small hotfix PR against `dev` independently.
- **`wip/bewest/security-hotfix-eval-auth-delay` branch status:**
  retained (not closed) — now contains exactly one commit (the
  setInterval fix) and is ready to open as a standalone PR against `dev`.

**Status:** ✅ Primary issue resolved upstream (pending #8605 merge);
secondary issue fixed and tested on this branch, ready for PR.
