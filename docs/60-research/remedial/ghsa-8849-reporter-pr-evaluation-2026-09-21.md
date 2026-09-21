# The reporter's proposed fix for GHSA-8849, evaluated by running it

Date: 2026-09-21. Subject: `nightscout/cgm-remote-monitor-ghsa-8849-qjp5-vrrj` **PR #1**,
`advisory-fix-1 → master`, one commit `da531f14`, 3 files, +111/−12, opened 2026-09-18 by the
advisory's reporter. Base confirmed: **`v15.0.8` is an ancestor**, so it targets the shipping
release. Fetched into `externals/work/crm-adv-reporter`, booted against `mongo:7` on a
dedicated instance, probed over the real socket with synthetic data only.

**Disclosure.** The defect is live on the shipping release and unpatched. This document
describes the *mechanism* of the proposed remedy and where it falls short; it withholds the
attack recipe, which is the same one the advisory already contains. Probes are outside version
control.

**Tone note, because this matters more than the finding.** The reporter found a real defect,
reported it responsibly through GitHub's advisory workflow, and did the unusual and generous
thing of writing a fix. Nothing below is a criticism of that. The two gaps are instances of
exactly the confusion this programme has been chasing all week — Nightscout has two
authorization-shaped settings and the intuitive one is the wrong one — and they are easy to
make. They were found by running the branch, not by reading it, and the same discipline caught
comparable mistakes in this project's own work eight times.

---

## 1. What the PR does

`lib/api3/alarmSocket.js` gains a module-level `authorizedSockets` Set. `emitNotification` stops
calling `self.namespace.emit(...)` and instead iterates that Set. Membership is granted by
`authorizeSocket(socket)`, called from two places: each successful `subscribe` branch, and — the
important one — the connection handler:

```js
if (env.settings.authenticationPromptOnLoad) {
  socket.authenticationTimeout = setTimeout(function disconnectUnauthenticatedSocket () {
    if (!authorizedSockets.has(socket)) { socket.disconnect(true); }
  }, AUTHENTICATION_GRACE_PERIOD);          // 5000 ms
} else {
  authorizeSocket(socket);                  // <- every socket, unconditionally
}
```

So the design is: *if the deployment prompts for authentication on load, give a socket five
seconds to authenticate and then hang up on it; otherwise admit it.*

## 2. Gap 1 — the gate is `AUTHENTICATION_PROMPT_ON_LOAD`, not `AUTH_DEFAULT_ROLES`

`AUTHENTICATION_PROMPT_ON_LOAD` defaults to **false**. `AUTH_DEFAULT_ROLES=denied` is the
setting Nightscout's own security documentation tells an operator to use, and the one the whole
REST surface honours. They are independent. An operator who has closed their site the documented
way, and never touched the prompt setting, gets the `else` branch — every socket admitted.

Measured on `da531f14`, never-subscribing anonymous socket, synthetic bolus and announcement
fired through the real write path:

| instance | `AUTH_DEFAULT_ROLES` | `AUTHENTICATION_PROMPT_ON_LOAD` | anon REST | never-subscribed socket |
|---|---|---|---|---|
| 3851 | **denied** | unset (default) | **401** | **`NOTIFICATION` + `ANNOUNCEMENT` received** |
| 3852 | **denied** | **true** | **401** | nothing |
| 3853 | readable | unset | 200 | received (correct — documented default) |

Row 1 is the configuration the advisory is about, and the fix does not change it. Row 2 shows
the mechanism does work when it engages, so this is a wiring problem rather than a broken idea.

## 3. Gap 2 — even when it engages, it never consults the read permission

`authorizeSocket(socket)` is called on **any** successful credential resolution. The `perms.read`
value computed two lines later from `api:*:read` is placed in the response and never consulted
for delivery — which is, precisely, the original defect, relocated from the namespace emit to
the Set insertion.

Measured on 3854 (`denied` + prompt `true`, the only configuration where the fix engages) with a
subject whose role grants **only** `api:treatments:create`:

```
subscribe reply : {"success":true,"message":"Subscribed for alarms"}
events received : ["notification:Bolus", "announcement:Announcement"]
```

and, **with that same token, on that same instance, in the same run** — the control that makes
this a finding rather than an observation:

```
GET /api/v1/entries.json?token=…       -> 401
GET /api/v1/treatments.json?token=…    -> 401
GET /api/v1/devicestatus.json?token=…  -> 401
```

A write-only credential — the kind an operator hands to an uploader device — is refused every
read over REST and hears every alarm over the socket.

## 4. Two smaller observations

- **Disconnecting versus declining to deliver.** The PR hangs up on an unauthenticated socket
  after five seconds. That is a stronger posture than not delivering to it, and it has a cost: a
  client that intends to authenticate late, or that is slow on a bad mobile connection, is
  dropped rather than simply unsubscribed. The `DataReceivers` precedent on the main namespace
  declines delivery and leaves the socket connected. Worth a deliberate choice rather than an
  incidental one.
- **The accessToken branch discards `auth`.** `function resolveFinishForToken (err, auth)`
  becomes `function resolveFinishForToken (err)`. Nothing in that branch used `auth` before, so
  it is not a regression — but it removes the value a read check would need, which is consistent
  with §3 being an oversight rather than a decision.

## 5. What this means for the response

The Foundation's own fix is on `bf/alarm-socket-scope` and takes a different shape, settled by a
maintainer decision on 2026-09-21: admit at connection time when the deployment's **anonymous
default role** already permits reading, re-evaluate on `subscribe`, and gate delivery on
`api:*:read`. That keys on the setting the rest of the product honours and closes both gaps
above. It changes nothing on the shipped `readable` default, where the marginal content
disclosure was measured at zero.

**The recommendation is not "reject the PR".** It is to reply in the private fork with §2 and §3
as measurements, offer the Foundation's branch as the merge candidate, and credit the reporter on
the published advisory for the finding — which stands entirely, and which nobody inside the
project had noticed.

**And the meta-finding is worth stating plainly, because it is the same one that started this
week's work.** A competent external reviewer, reading this codebase carefully enough to find a
real authorization defect, then wrote a remedy keyed to the wrong one of Nightscout's two
authorization settings. That is not a fact about the reviewer. `AUTH_DEFAULT_ROLES` and
`AUTHENTICATION_PROMPT_ON_LOAD` are adjacent in name, adjacent in apparent purpose, and only one
of them is the access-control boundary. Documenting that distinction — in the README next to both
settings, and in whatever specification the `/alarm` namespace eventually gets — would have
prevented this and is cheaper than either fix.

*Evidence*: probes and per-instance logs outside version control in the session scratchpad
(`review/`). See
[the GHSA-8849 report](./ghsa-8849-alarm-socket-2026-09-21.md),
[the configuration matrix](./advisory-auth-configuration-matrix-2026-09-21.md),
[the disposition](../../30-design/remedial/security-advisory-disposition-2026-09-21.md).
