# `bf2/auth-hardening`: withheld-style PR body

**Posting copy for the public PR (maintainer decision 2026-09-23).** Everything below the line is posted as-is. The full text is [bf2-auth-hardening.md](bf2-auth-hardening.md), for after release.

---

> **Details withheld.** Part of this PR fixes security issues present in released versions. No release contains the fixes yet, so this description is kept short on purpose. The full description, including what site owners should do after upgrading, will be added once a fixed release is out.

### Summary

This combines two branches that were already reviewed on their own, backports the client-address handling from #8605 behind a new setting, fixes one admin-page save, and includes #8763 and #8764:

- **Subject storage** no longer writes a subject's derived fields to the database. Existing access tokens keep working: they are re-derived on every load, as before.
- **The failed-login delay** is counted per credential as well as per address, so one wrong secret is slowed however the reported address varies. As before, the wait comes before the credential is checked: a request from an address with recent failures waits, whether or not it would succeed. The list of recent failures is cleared on a schedule and has a size limit.
- **A new setting, `TRUST_PROXY`**, says whose forwarded headers (`X-Forwarded-For`, `X-Forwarded-Proto` and similar) Nightscout believes. **Unset, behaviour is exactly as today**, so nobody needs to change anything to upgrade.
- **Forwarded addresses with a port are accepted** by the explicit `TRUST_PROXY` settings, so they work on Azure App Service.
- **Editing a subject or role on the admin page keeps its `notes` and `created_at`.** Before, saving it wiped the notes and replaced the creation date.
- **Every part of Nightscout reads `TRUST_PROXY` the same way** (#8763). One policy is compiled per server `env`; `lib/server/client-ip.js` exports only `trustFor(env)` and `clientIPFor(env)`. API v3 logins take it from `env`, not from the app they are mounted under. No behaviour change.
- **Loop remote commands carry the sender's address as `TRUST_PROXY` resolves it** (#8764), not the connecting address, which on most hosted sites is the hosting proxy's. Loop saves it on remote overrides, so **the caregiver's address is stored in treatments**, readable by anyone who can read the site's data.

### `TRUST_PROXY`

| value | what Nightscout believes | for |
|---|---|---|
| not set (default) | forwarded headers from anyone, as today | upgrading without changes |
| `false` | no forwarded headers; the connecting address, and whether that connection itself is https | sites reached directly, with no proxy |
| proxy IPs or CIDR ranges, comma-separated | forwarded headers only from those addresses | sites behind a proxy whose address is known |
| a whole number of hops, such as `1` | the closest that many proxies, as Express's numeric `trust proxy` | sites behind a known number of proxies whose addresses change |
| `true` | every hop, as Express's `true`: the client address is the left-most forwarded entry | only where every proxy in front of Nightscout rewrites the header |

Each value has Express's meaning. Subnet names such as `loopback` are refused at startup, and a hop count cannot be combined with addresses. `CUSTOMCONNSTR_TRUST_PROXY` also works. With `true`, the startup message says the client address is only as trustworthy as the outermost proxy, because a caller can put any address at the left of the header.

**Behind a proxy that terminates https, set it with care.** With `false`, or a list that leaves out the proxy, Nightscout stops believing the proxy's "the visitor used https" header and redirects to https in a loop. If the site stops loading after setting it, unset it and check the address Nightscout actually sees the proxy connect from.

**Which value to use.** `docs/proposals/trusted-proxy-migration.md` has a table of the value each kind of deployment needs. Most sites behind a proxy or hosting platform need a hop count. Where a trusted proxy or load balancer adds its entry to a forwarded header the caller may already have filled in, setting the number of hops to that trusted proxy is what makes the client address trustworthy: too few gives everyone the proxy's address, too many believes the caller. Forwarded addresses that carry a port (`203.0.113.5:51234`, the form Azure App Service is reported to send) are accepted by the explicit settings; before, they fell back to the connecting address, so on Azure every visitor got the same one.

While `TRUST_PROXY` is unset, Nightscout logs a `SECURITY:` line at startup saying the failed-login delay is keyed on an address taken from headers any caller can set, and how to fix that. This is one flag, not two: the failed-login delay keys on the same client address, so `TRUST_PROXY` moves both.

### Evidence

- New and changed tests in `client-ip`, `authdelay`, `authsubjects` and `env`. Each was checked by breaking the code it covers; every break fails on the original symptom.
- `authdelay` sends the correct secret, and a request with no credential, from the same address as the failures, and expects both to wait; against a check-first order both fail, answered in 3-5 ms.
- Full suite with #8763 and #8764 (the tree of `71987bb4`), Node 24.15.0, MongoDB 7 with a raised open-file limit: **2577 passing**, 3 pending, 0 failing. With #8763 alone (`708af170`, the tree of `e3354218`): 2572 passing.
- The API v3 failed-login key is tested to follow `TRUST_PROXY` from `env`, and a v3 app with a different `trust proxy` of its own does not move it. A test pins `client-ip.js`'s exports to `trustFor` and `clientIPFor`.
- The address Loop receives is tested for `TRUST_PROXY` unset, `1`, a proxy list and `false`, and through the real `lib/api2` app.
- An nginx front end appending `address:port`: with `1` or a list naming it, the address was the front end's before the port change and the client's after; unset resolved the client both times.
- A local lab put Nightscout behind real proxies (nginx appending and replacing, two nginx hops, Caddy, Traefik, HAProxy, a TLS terminator, and a PROXY-protocol load balancer in front of two nginx hops) and read back the address Nightscout recorded. With the hop count set to the trusted proxy, every topology resolved the real client and ignored forwarded headers the caller sent; one hop too few gave a proxy's address, one too many believed the caller. Unset resolved exactly as `dev`.
- None of `client-ip`, `authdelay` or `authsubjects` is in `test:unit` or `test:integration`; use `npm test`, as CI does.
- Merges cleanly into `dev`, and with #8748, #8749, #8750 and #8751. Integrated with all of them and the other 15.0.9 changes before the hop-count commit, the suite passed on Node 20, 22 and 24 against MongoDB 4.4 and 7.0; that combined run still has to be repeated with this tip.
- Against #8605 it conflicts in adjacent lines only. Three deliberate differences: with `TRUST_PROXY` unset, the client address is resolved exactly as `dev` does, not as #8605's default does; `TRUST_PROXY` here also accepts hop counts and `true`, which #8605 refuses; and the v1 and v3 API apps do not set their own `trust proxy`: every client-address consumer reads the one policy compiled from `env`, so a `trust proxy` on a sub-app would not change the address (#8605 sets it on all three).

