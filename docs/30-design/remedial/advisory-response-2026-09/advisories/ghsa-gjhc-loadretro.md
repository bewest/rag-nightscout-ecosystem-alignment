# GHSA-gjhc-pc29-r3m6 — unauthenticated WebSocket `loadRetro`

Register **BF-79**. Fix: `bf/ws-loadretro-auth` `9765e8cd`, PR against `dev`.

## Metadata changes

| field | now | change to | why |
|---|---|---|---|
| `severity` | `high` | **`high`** (keep) | correct for a hardened install |
| `cvss_vector_string` | *(none)* | **`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N`** = 7.5 | currently a bare "high" with no vector; state that it scores the **hardened** configuration |
| `vulnerable_version_range` | `>0.8.1` | **`>=0.9.0`** | measured: `loadRetro` is absent from tags 0.8.1, 0.8.2, 0.8.3 and 0.8.4 |
| `patched_versions` | *(blank)* | **leave blank until a release ships**, then the release number | `dev` is unreleased; naming a SHA or PR tells 15.0.8 operators they have somewhere to go |
| `cwe_ids` | CWE-200, CWE-862 | **keep both** | disclosure via missing authorization — both apply |
| package | npm `nightscout` | keep, **and name the git/image tags in the body** | npm `nightscout` stops at 14.2.11 |

**The range correction is the substantive one.** `>0.8.1` declares 0.8.2, 0.8.3 and 0.8.4
vulnerable to a handler they do not contain. `loadRetro` first appears in **0.9.0** — which is
also the first tag carrying `DataReceivers` and `authDefaultRoles`, so the handler and the
authorization it skips shipped in the same release.

## Text to change in the description

**Remove or rewrite this sentence**, in the PoC section:

> This does not require any specific configuration on the system; all versions since 0.8.1 are affected.

It is true of *reachability* and false as an *impact* claim, and it reads as "the default makes
you exposed" — which invites the mitigation "then I will turn off anonymous reads", measured not
to work. Suggested replacement:

> **Reachability.** The handler is reachable on every configuration; no setting disables it.
> `AUTH_DEFAULT_ROLES=denied`, `status-only`, `AUTHENTICATION_PROMPT_ON_LOAD=true` and
> `TREATMENTS_AUTH=off` were each tested and all still return the data. `DEVICESTATUS_DAYS=2`,
> the only setting that touches this path, doubles the amount returned.
>
> **Impact depends on configuration, and the two cases are very different.**
> On the shipped default `AUTH_DEFAULT_ROLES=readable` — documented as "readable by anyone who
> knows the URL", and flagged by the application itself at every boot — there is **no additional
> disclosure**. Measured field by field, every record the socket returns is already in the
> anonymous `GET /api/v1/devicestatus.json` answer, no field exists only on the socket, and the
> REST route returns more. Operators on a default install have nothing to act on.
> On an install that has closed anonymous access, this is an authorization bypass: with every
> REST read answering 401, an unauthenticated socket that never sends `authorize` receives the
> retained device-status window — loop suggestions, pump battery and reservoir, bolusing and
> suspended state, pump serial, uploader name and rig hostname.

**Add**, because it sharpens the finding and is not in the report:

> The handler returns **more than an authorized reader gets**: `authorize` trims the initial load
> to ten records per device-and-type, while `loadRetro` returns the full retained window — 20
> records against 576 in the reproduction. The bound is the cache's retention (24 h by default,
> 48 h under `DEVICESTATUS_DAYS=2`), not the `loadedMills` the client sends, which is ignored.
>
> An attacker never calls `authorize`: doing so with bad credentials disconnects the socket, so
> the authorization flow is one to walk around rather than through.

**Add a Workarounds section**, which is currently absent:

> **None that keeps the site working.** `AUTH_DEFAULT_ROLES=denied` does not help. The namespace
> is multiplexed over the same `/socket.io/` endpoint as the dashboard's live updates, so a
> reverse proxy cannot separate them without parsing Socket.IO frames; blocking `/socket.io/`
> outright disables live updating and alarm delivery. The fix is the patch.

**Keep the Remediation section as written** — it describes what the fix does, and the fix follows
it.

## Credit

`collaborating_users` lists the reporter. Keep the credit.
