# `rt/trust-one-source`: every client-address consumer reads one TRUST_PROXY policy

**DRAFT. Not pushed, not opened.** Branch `rt/trust-one-source`, tip `d0a3d628`, one commit on
`official/bf2/auth-hardening` `e549e1a6` (the head of #8754, still open). Open it against
`bf2/auth-hardening` and retarget to `dev` when #8754 merges. Trial-merges clean into #8754's
head and into `origin/dev` `153e5658`. No `CHANGELOG.md` edit. Queue item `RT-TRUST-ONE-SOURCE`;
semver patch. The posting copy is the text below the line.

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

- `lib/server/client-ip.js`: `trustFor(env)` compiles `env.trustProxy` once per
  `env` (cached in a `WeakMap`, recompiled only if `env.trustProxy` changes);
  `clientIPFor(env)` is `createClientIP` over that policy, compiled when the
  consumer is created so an invalid `TRUST_PROXY` still fails at boot.
- `lib/server/app.js` gives Express `trustFor(env)`, so `req.ip`/`req.secure`
  use the same function object as everything else.
- The five consumers use `clientIPFor(env)`; the delay list uses `trustFor(env)`.
- `lib/api3/security.js` keys the failed-login delay from `trustFor(opCtx.env)`
  (every API v3 operation already passes `env`), not from the app setting.
- `compileTrust` and `createClientIP` are unchanged and still exported.

### Tests

- The API v3 key tests in `tests/client-ip.test.js` pass `env` instead of an
  app with `'trust proxy'` set.
- The inherits-from-parent test (e549e1a6) is replaced by one showing that a v3
  app with a different `'trust proxy'` of its own, mounted under a parent with
  yet another, does not move the key: for `TRUST_PROXY` unset, `1` and `false`,
  against app settings unset, `false`, `2` and `true`.
- New: one policy per env, and `app.get('trust proxy fn')` is that policy
  (unset, `false`, `true`, `1`, an address); changing `env.trustProxy` recompiles.
- `tests/fixtures/api3/instance.js` sets its parent's `'trust proxy'` from
  `trustFor(env)`; it now only affects Express's `req.ip`/`req.secure`.

Break-it, each reverted after:

| Break | Result |
|---|---|
| `security.js` reads `app.get('trust proxy fn')` again | 3 failing (both v3 key tests, the hop-count v3 test) |
| `trustFor` never caches | 1 failing (one-policy test, at `false`) |
| `app.js` compiles its own policy | 1 failing (one-policy test, at `false`) |
| cache ignores `env.trustProxy` changes | 1 failing (one-policy test, recompile) |

`client-ip`: 61 passing (was 60: one test replaced, one added).
Full suite at d0a3d628, Node 24.15.0, MongoDB 7: 2571 passing, 3 pending, 0 failing (2570 at e549e1a6).
