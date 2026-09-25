# `rt/trust-one-source`: every client-address consumer reads one TRUST_PROXY policy

**OPENED 2026-09-24 as draft nightscout/cgm-remote-monitor #8763.** Head `e3354218` (pushed,
body updated). Branch `rt/trust-one-source`, two commits on `official/bf2/auth-hardening`
`e549e1a6` (the head of #8754, still open). Opened
against `bf2/auth-hardening`; retarget to `dev` when #8754 merges. Trial-merges clean into
#8754's head and into `origin/dev` `153e5658`. No `CHANGELOG.md` edit. Queue item
`RT-TRUST-ONE-SOURCE`; semver patch. The posting copy is the text below the line.

---

Stacked on #8754 (`bf2/auth-hardening`). Retarget to `dev` once #8754 merges.

### What changes for site owners

Nothing. Every part of Nightscout that works out a visitor's address now reads
the `TRUST_PROXY` setting the same way, so a later change cannot make one part
(API v3 logins) disagree with the rest.

### Why

On #8754 the compiled `TRUST_PROXY` policy reaches its consumers by two routes:

- five modules (`authorization/index.js`, `api/status.js`, `server/websocket.js`,
  `api3/alarmSocket.js`, `api3/storageSocket.js`) and the delay list's boot
  messages each compile `env.trustProxy` themselves;
- `lib/api3/security.js` alone reads Express's `'trust proxy fn'`, which the v3
  app does not set but inherits when `lib/server/app.js` mounts it.

In production both end in the same function, so today they agree. But the v3
key depends on how the app is mounted: anything that sets `'trust proxy'` on
the v3 app itself, or mounts it under a parent that sets nothing, changes the
API v3 failed-login key without touching `TRUST_PROXY`.

### How

`lib/server/client-ip.js` now exports two functions and nothing else:

- `clientIPFor(env)`: the function that turns a request into its client address;
- `trustFor(env)`: the compiled policy itself.

Both come from one entry per `env` (a `WeakMap`, recompiled only if
`env.trustProxy` changes), so every caller with the same `env` gets the same
function objects. `clientIPFor` is called where each consumer is created, so an
invalid `TRUST_PROXY` still fails at boot.

- `lib/server/app.js` gives Express `trustFor(env)`, so `req.ip`/`req.secure`
  use the same policy as everything else.
- Authorization, the status API, the websocket server and both API v3 sockets
  use `clientIPFor(env)`; the delay list's boot messages use `trustFor(env)`.
- `lib/api3/security.js` keys the failed-login delay from
  `clientIPFor(opCtx.env)` (every API v3 operation already passes `env`), not
  from the app setting.
- `compileTrust`, `createClientIP` and `getClientIP` are no longer exported, so
  there is no second way for new code to build a policy.

Two commits: the first moves every consumer onto the one policy; the second
narrows the exports and moves the tests onto them.

### Tests

- The API v3 key tests in `tests/client-ip.test.js` pass `env` instead of an
  app with `'trust proxy'` set.
- The inherits-from-parent test (e549e1a6) is replaced by one showing that a v3
  app with a different `'trust proxy'` of its own, mounted under a parent with
  yet another, does not move the key: for `TRUST_PROXY` unset, `1` and `false`,
  against app settings unset, `false`, `2` and `true`.
- New: one policy and one resolver per env, and `app.get('trust proxy fn')` is
  that policy (unset, `false`, `true`, `1`, an address); changing
  `env.trustProxy` recompiles.
- New: the module exports only `trustFor` and `clientIPFor`.
- The rest of the file builds its resolvers and policies through those two, from
  `{ trustProxy: value }` or from `lib/server/env`, instead of `createClientIP`
  and `compileTrust`.
- `tests/fixtures/api3/instance.js` sets its parent's `'trust proxy'` from
  `trustFor(env)`; it now only affects Express's `req.ip`/`req.secure`.

Break-it, each reverted after:

| Break | Result |
|---|---|
| `security.js` ignores `env` | 3 failing (both v3 key tests, the hop-count v3 test) |
| no per-env cache | 1 failing (one-policy test) |
| `app.js` builds its own policy | 1 failing (one-policy test) |
| cache ignores `env.trustProxy` changes | 1 failing (one-policy test, recompile) |
| a third export | 1 failing (export test) |

`client-ip`: 62 passing (was 60: one test replaced, two added).
Full suite at e3354218, Node 24.15.0, MongoDB 3.6.8: 2572 passing, 3 pending, 0 failing (2570 at e549e1a6). An earlier version of this text said MongoDB 7; the local server was 3.6.8.
On dev 4f705217 after the merge: 2577 passing, 3 pending, 0 failing on Node 20.20.0, 22.22.0 and 24.15.0 against MongoDB 7.0.43, and in CI on Node 20, 22 and 24 against MongoDB 4.4, 5.0 and 6.0.
