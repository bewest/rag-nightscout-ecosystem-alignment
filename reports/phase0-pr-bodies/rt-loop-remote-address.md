# `rt/loop-remote-address`: Loop remote commands carry the sender's address as TRUST_PROXY resolves it

**DRAFT. Not pushed, not opened.** Branch `rt/loop-remote-address`, tip `71987bb4`, one commit on
`official/rt/trust-one-source` `e3354218` (the head of #8763, itself stacked on #8754). Open it
against `rt/trust-one-source` and retarget with the stack. Trial-merges clean into #8763's head
and into `origin/dev` `153e5658`. No `CHANGELOG.md` edit. Not for 15.0.9. Queue item
`RT-LOOP-REMOTE-ADDRESS` (decided 2026-09-24, option 2); semver patch. The posting copy is the
text below the line.

---

Stacked on #8763. Retarget with the stack.

### What changes for site owners

When a caregiver sends a remote command to Loop through Nightscout (a temporary
override, carbs or a bolus), Nightscout tells Loop where the command came from,
and Loop saves that on the override it records back in Nightscout. On most
hosted sites this was the hosting company's own proxy, not the caregiver.

After this change it is the caregiver's address, worked out the same way as
everywhere else from your `TRUST_PROXY` setting:

- `TRUST_PROXY` set to your proxy (a hop count or its addresses): the
  caregiver's address.
- `TRUST_PROXY=false`: the address connecting to Nightscout, as before.
- `TRUST_PROXY` unset: the address in the forwarded headers, as the rest of
  Nightscout reads it when the setting is unset.

**This address is saved on each remote override in your Nightscout data,
where anyone who can read your site's data can see it.** That includes
visitors without a login if your site lets them read. Whether a command is
accepted does not depend on it.

### Why

`POST /api/v2/notifications/loop` passed `req.connection.remoteAddress` as the
`remote-address` in every Loop push. It was the only client-address read in
`lib/` that did not go through `lib/server/client-ip.js`, so it ignored
`TRUST_PROXY`.

Loop (NightscoutService) decodes `remote-address` as a required string on
every remote notification, stores it on a remote override, and uploads it
back as the Temporary Override treatment's `remoteAddress` with `enteredBy`
"Loop (via remote command)". It is a label; Loop does not act on it.

### How

- `lib/api2/notifications-v2.js` resolves the address with `clientIPFor(env)`.
- `lib/api2/index.js` passes the server's `env` to it.
- The value is still a string whenever the request has a connection peer, as
  before, so Loop's decoding is unchanged.

### Tests

`tests/notifications-v2.test.js`:

- the address Loop receives for `TRUST_PROXY` unset, `1`, a proxy list and
  `false`;
- through the real `lib/api2` app, that `TRUST_PROXY=false` is read from the
  `env` it is created with.

Break-it, each reverted after:

| Break | Result |
|---|---|
| the connection's peer address again | 3 failing (unset, `1`, list) |
| `lib/api2` does not pass `env` | 1 failing (wiring test) |

`notifications-v2`: 48 passing (43 before).
Full suite at 71987bb4, Node 24.15.0, MongoDB 7: 2577 passing, 3 pending, 0 failing (2572 at e3354218).
