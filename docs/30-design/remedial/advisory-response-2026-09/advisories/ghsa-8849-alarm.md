# GHSA-8849-qjp5-vrrj — unauthenticated `/alarm` namespace

Register **BF-75** (and **BF-76** found beside it; **BF-80** is the fix's cost). Fix:
`bf/alarm-socket-scope` `012f1623`, PR against `dev`.

## Metadata changes

| field | now | change to | why |
|---|---|---|---|
| `severity` | `high` | **`high`** (keep) | correct for a hardened install |
| `cvss_vector_string` | *(none)* | **`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N`** = 7.5 | state that it scores the **hardened** configuration; the default arm is 5.3 |
| `vulnerable_version_range` | `≥15.0.0` (Unicode ≥) | **`>= 15.0.0`** | the range is **correct** — `89d7eb679` is first contained in tag 15.0.0 — but the Unicode `≥` should be ASCII `>=` so it parses |
| `patched_versions` | *(blank)* | **leave blank until a release ships** | `dev` is unreleased |
| `cwe_ids` | CWE-200, CWE-862 | **keep both** | |

**`C:H` is a judgement worth stating explicitly** rather than leaving to drift. The letter of
`Low` ("no control over what is obtained") fits a passive listener. `High` was chosen because
this is identified-individual health data: the URL names the person and the stream carries their
glucose emergencies and insulin doses in real time. A re-score to 5.3 is defensible; it should
be a decision, not an accident.

## Text to add to the description

The report is accurate in every particular that was checked, including the
`authenticationPromptOnLoad` claim — verified exactly: the subscribe is refused, the socket is
**not** disconnected, and it still receives all five event classes. Three additions:

**1. Lead with the boundary.** Suggested opening line:

> `AUTH_DEFAULT_ROLES=denied` is honoured by the REST surface and ignored by the alarm stream.
> On an instance where every `/api/v1` read answers 401, an unauthenticated Socket.IO client that
> never sends `subscribe` receives every alarm, announcement and treatment notification.

**2. Say what the default install does and does not lose**, because it is most operators:

> On the shipped `AUTH_DEFAULT_ROLES=readable` default, **no field in any of the five payloads is
> absent from the anonymous REST surface** — measured field by field: the dose, device, notes and
> event type are in `treatments.json`, `debug.lastSGV` in `entries.json`, `debug.thresholds` in
> `status.json`, and `notifyhash`/`key` are sha1 over already-readable fields. What the socket
> adds on a default install is real-time delivery with no request rate and no access-log trace,
> plus a server-labelled "hypo/hyper right now" that a poller would have to re-derive. It is not
> new content. Operators on a default install should not read this as new exposure.

**3. State what `subscribe` actually gates**, which is the crisp description of the defect:

> `subscribe` resolves authorization and computes `read` from `api:*:read`, places it in the
> response, and never consults it again. It gates acknowledgement rights and nothing on the
> receive side. Under `denied` the server answers an anonymous subscriber
> `{"success":true,…,"read":false}` and then delivers everything to it.

**Add a Workarounds section:**

> **None that keeps the site working.** `AUTH_DEFAULT_ROLES=denied` does not help;
> `AUTHENTICATION_PROMPT_ON_LOAD=true` does not help; disabling careportal via `ENABLE=` removes
> `notification` and `announcement` by removing the feature while `alarm`, `urgent_alarm` and
> `clear_alarm` still arrive. The namespace is mounted unconditionally. It is multiplexed over
> the same `/socket.io/` endpoint as the dashboard, with the namespace inside the Engine.IO
> payload, so a reverse proxy cannot separate it without parsing Socket.IO frames.

## Remediation section — replace

The current text is *"I have implemented a fix in the private fork created by GitHub for this
security disclosure."* Replace with a description of the fix that ships:

> Delivery is scoped to a room (`AlarmReceivers`), mirroring the `DataReceivers` pattern the main
> namespace already uses, with membership decided by `api:*:read`. A socket is admitted at
> connection time when the deployment's anonymous default role already permits reading — so a
> `readable` install is unchanged and no undocumented third-party client breaks — and refused on
> `denied`. The web client re-subscribes after authenticating, which it previously did not.
>
> A second defect was found and fixed alongside: the access-token branch of `subscribe`
> registered the `ack` handler with no permission check, so any valid token of any role could
> silence every viewer's alarm.

## Credit — this one matters

The reporter found a real defect that nobody inside the project had, reported it responsibly
through this workflow, and wrote a patch. **Credit them on publication.** See
`../prs/PR-3-reply-to-reporter.md` for the reply to their PR; it explains why a different remedy
is being merged without diminishing the finding.
