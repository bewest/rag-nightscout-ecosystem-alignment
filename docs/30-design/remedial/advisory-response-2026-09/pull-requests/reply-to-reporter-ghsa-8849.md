Reply to: nightscout/cgm-remote-monitor-ghsa-8849-qjp5-vrrj  PR #1  (private advisory fork)
From:     Nightscout Foundation
Purpose:  reconcile two fixes without dismissing the reporter's.

---

Thank you for this — both the report and the patch. The finding is real, it is entirely yours,
and nobody inside the project had it. We have reproduced it on v15.0.8 and on `dev`, in both
authorization configurations, for all five event classes, and we have confirmed your
`authenticationPromptOnLoad` observation exactly: the subscribe is refused, the socket is not
disconnected, and it still receives everything.

We have run your branch, and we would like to propose a different remedy. Two measurements are
the reason.

**1. The patch gates on `AUTHENTICATION_PROMPT_ON_LOAD` rather than `AUTH_DEFAULT_ROLES`.**

In the connection handler, the `else` arm calls `authorizeSocket(socket)` unconditionally. That
arm is taken whenever `authenticationPromptOnLoad` is falsy — which is its default. But
`AUTH_DEFAULT_ROLES=denied` is the setting our security documentation tells operators to use,
and it is what the whole REST surface honours. The two are independent.

Measured on your branch, `AUTH_DEFAULT_ROLES=denied`, prompt flag left at its default, a socket
that connects and never subscribes:

```
NOTIFICATION  {"title":"Bolus","message":"Insulin: 0.45U | Entered By: …"}
ANNOUNCEMENT  {"title":"Announcement", …}
```

while `/api/v1/entries.json`, `/treatments.json` and `/devicestatus.json` all returned **401**
on the same instance in the same run. With `AUTHENTICATION_PROMPT_ON_LOAD=true` your mechanism
does close it, so this is a wiring question rather than a broken idea.

**2. Where it does engage, it does not consult the read permission.**

`authorizeSocket(socket)` is called on any successful credential resolution, in both subscribe
branches. The `perms.read` value computed two lines later from `api:*:read` goes into the
response and is never consulted for delivery.

Measured on your branch with `denied` + prompt `true`, using a subject whose role grants only
`api:treatments:create`:

```
subscribe reply : {"success":true,"message":"Subscribed for alarms"}
received        : notification:Bolus, announcement:Announcement
```

and the same token, same instance, same run: **401** on entries, treatments and devicestatus. A
write-only credential — the kind an operator hands to an uploader device — hears every alarm.

**What we are proposing instead**

A room, `AlarmReceivers`, mirroring the `DataReceivers` pattern the main namespace already uses;
membership decided by `checkMultiple('api:*:read', …)`; and the socket admitted at connection
time when the deployment's anonymous default role already permits reading, re-evaluated on
subscribe. On `AUTH_DEFAULT_ROLES=readable` — the shipped default, where we measured the
marginal content disclosure at exactly zero, every field already being in `treatments.json`,
`entries.json` or `status.json` — nothing changes, so no undocumented client breaks. On `denied`
nobody is admitted without read entitlement.

We also took the ack path, which we found while working on yours: any valid token of any role
could reach `ctx.notifications.ack(...)` and silence every viewer's alarm.

One thing your shape does that ours does not, and we would value your view: you *disconnect* an
unauthenticated socket after a grace period rather than simply not delivering to it. That is a
stronger posture. We chose to decline delivery and leave the socket connected, matching the main
namespace, but the argument is not one-sided.

**On credit and on the underlying problem.** You will be credited on the published advisory for
the finding. And we would ask you not to read the two measurements above as carelessness on your
part — a reviewer competent enough to find this defect then wrote a remedy keyed to the wrong one
of Nightscout's two authorization-shaped settings, which tells us the settings are the problem.
`AUTH_DEFAULT_ROLES` and `AUTHENTICATION_PROMPT_ON_LOAD` sit next to each other in the
configuration surface, sound like they do the same job, and only one is the access-control
boundary. Documenting that distinction, and specifying the `/alarm` protocol at all — it appears
in no swagger file and nothing under `docs/` — is work this report has made unavoidable, and it
is worth more than either patch.

We would rather land this with you than around you. Happy to take your review on our branch, or
to fold the disconnect behaviour into it if you think it earns its place.
