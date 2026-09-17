# `bf/throttle` — the failed-login delay was charged to the wrong request, and its list was never swept

One commit on `origin/dev` `a8888f0d`, tip `435419ce`. 3 files, +388/−45, of which one is a new
test file. No `CHANGELOG.md` edit. Merges clean against `dev`, against every other open Phase 0
branch, **and against #8605**.

> **Read this before the diff: the default here is deliberately today's behaviour.** This branch
> makes Nightscout's brute-force delay cheaper for legitimate clients and honest about its own
> limits. **It does not make it effective.** An attacker who varies both the credential and the
> `X-Forwarded-For` header is still not throttled, exactly as on the shipping release. Closing that
> needs a proxy trust boundary, which is #8605's `TRUST_PROXY`. The gap is asserted by a test here
> rather than left implied, and the server now says so at boot.

## What changes for you

**Two fixes to the delay Nightscout applies after a failed login, and one new message in your log.
Nothing you have configured changes, and nothing you rely on stops working.**

- **A device with the correct password could be made to wait for someone else's failed attempts.**
  The delay was applied on the way *in* to every request, before Nightscout had even looked at the
  credential. If your site sits behind a proxy or a CDN — where many devices can appear to share one
  address — a single misconfigured uploader could slow everything down for everyone. **The delay now
  applies only to the request that actually failed.**
- **The list of recent failures was never being cleared properly.** It grew for as long as
  Nightscout kept running. It is now swept on a schedule and has a size limit.
- **New message in your log, and it is telling you something true.** Protection against password
  guessing is weaker than it looks, because the address it counts against is one the connecting
  client can set for itself. **Restricting access at your proxy or hosting provider is the thing
  that actually helps today.**

Nightscout is not a medical device and none of this is medical advice.

---

## The three defects

### 1. The wait was on the way in

`shouldDelayRequest` ran before authentication was attempted, so a request presenting a correct
secret waited out a delay earned by somebody else's failures. The wait now happens on the way *out*
of a failed attempt:

- a request that authenticates is never delayed;
- a request carrying no credential at all is not a guess at one, and is not throttled either;
- a failed attempt still waits, so the control itself is unchanged in strength.

This is what makes it safe to key on a shared address later: with the wait on the failure path, a
legitimate client behind a busy proxy never pays for its neighbours.

### 2. The sweep ran once

```js
setTimeout(function clearList () { /* … */ }, 30000);   // fires once, then never again
```

It fired 30 seconds after boot and never again, so every entry after that stayed for the life of the
process — in a plain object with no bound, fed by unauthenticated callers. It is now a
`setInterval`, `unref`'d so it cannot hold the process open or a test run, and the list is two
bounded buckets.

The two buckets are bounded **separately** on purpose. Credential keys are the ones an attacker can
mint at will; evicting them must never push out the address entry that is throttling that same
attacker.

### 3. The list held the secrets people had just tried

Keys were the raw values. They are now a SHA-256 under a per-process random salt, so a process that
outlives a request does not also retain the credential it was asked to throttle.

### And a second key, with an honest account of what it does not fix

Failures are counted under the credential as well as the address, so one wrong secret is slowed
however the reported address is varied. It **cannot** replace the address key — a brute force varies
the credential by definition, so a counter keyed only on the credential is fresh on every guess.

And the address key is only worth as much as the address it is given. Today that address comes from
`X-Forwarded-For` and friends with no proxy trust boundary:

| what varies between attempts | throttled today? |
|---|---|
| nothing | yes |
| the reported address only | yes — the credential key carries it |
| the credential only | yes — the address key carries it |
| **both** | **no** |

The last row is the live weakness and it is **pinned by a test** —
`does NOT yet throttle a guess that varies both the secret and the address` — so that the other
tests cannot be read as a claim that brute force is solved. When a trust boundary arrives, that test
should be inverted into the positive assertion it replaced.

## Why there is no new setting here

An earlier draft of this work added `lib/server/peer-address.js` and threaded a second, socket-derived
address through `alarmSocket.js`, `security.js`, `websocket.js` and `index.js`, keying the throttle on
something the caller cannot choose.

**It conflicted with #8605 in five files**, because that PR replaces the client-address derivation
wholesale with `lib/server/client-ip.js` driven by a new `TRUST_PROXY` setting — in exactly the call
sites the draft was editing. Two modules answering one question, and one of them would have had to go.

So the peer plumbing was dropped. This branch keys on `data.ip`, whatever the deployment resolves
that to:

- **today** — the forwarded header, caller-controlled, which is why the table above has a "no" in it;
- **with `TRUST_PROXY` configured** — the real client address, and the throttle does what it was
  always meant to do, **with no further change to these files**.

That is also why the secure default is not a flag in this PR. It is `TRUST_PROXY`'s default, and
flipping it is a deliberate later change that can be bundled with other default flips and a version
bump.

## Verifying it

```
TEST=authdelay npm run test-single     # 11 passing
```

Needs a running MongoDB. **The file is in neither `npm run test:unit` nor `npm run test:integration`**
— it is one of the files only `npm test` reaches — so a green `test:unit` is not evidence for any of
this.

Ablated: with `lib/authorization/delaylist.js` and `lib/authorization/index.js` restored to `dev`,
the same file gives **3 passing / 8 failing**.

Merge-checked 2026-09-16: clean against `origin/dev`, clean against all eight other Phase 0
branches, and clean against `chore/nightscout-modernization` (#8605).

## Semver: patch

No declared surface moves and no default changes. For any given request the delay only ever
*shrinks* — a successful authentication is no longer delayed at all — so nothing that worked stops
working. An added log line is not a surface.

The "What changes for you" text above is the release-note source; this branch adds no `CHANGELOG.md`
entry. **The paragraph that must not be dropped is the third one** — that the protection is weaker
than it looks and that restricting access at the proxy is what helps today. A note listing only the
two fixes would leave an operator believing guessing is handled.

## Follow-ups deliberately not in this PR

- **Keying on an address the caller cannot choose.** Needs `TRUST_PROXY` from #8605. `data.ip`
  becomes trustworthy the moment it exists; nothing here needs editing.
- **Naming that setting in the boot warning.** The message deliberately names no setting, because
  the one that fixes this does not exist on this branch yet. It should name it once it does.
- **Detecting the evasion rather than warning about it.** Counting distinct reported addresses
  arriving from one socket peer would turn the boot warning into a real signal, but it needs both
  the resolved address and the peer at once — which belongs in `client-ip.js`, not in a second
  module beside it.
