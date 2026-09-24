# `bf2/auth-hardening`: withheld-style PR body

**Posting copy for the public PR (maintainer decision 2026-09-23).** Everything below the line is posted as-is. The full text is [bf2-auth-hardening.md](bf2-auth-hardening.md), for after release.

---

> **Details withheld.** Part of this PR fixes security issues present in released versions. No release contains the fixes yet, so this description is kept short on purpose. The full description, including what site owners should do after upgrading, will be added once a fixed release is out.

### Summary

This combines two branches that were already reviewed on their own, backports the client-address handling from #8605 behind a new setting, and fixes one admin-page save:

- **Subject storage** no longer writes a subject's derived fields to the database. Existing access tokens keep working: they are re-derived on every load, as before.
- **The failed-login delay** is counted per credential as well as per address, so one wrong secret is slowed however the reported address varies. As before, the wait comes before the credential is checked: a request from an address with recent failures waits, whether or not it would succeed. The list of recent failures is cleared on a schedule and has a size limit.
- **A new setting, `TRUST_PROXY`**, says whose forwarded headers (`X-Forwarded-For`, `X-Forwarded-Proto` and similar) Nightscout believes. **Unset, behaviour is exactly as today**, so nobody needs to change anything to upgrade.
- **Editing a subject or role on the admin page keeps its `notes` and `created_at`.** Before, saving it wiped the notes and replaced the creation date.

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

**Which value to use.** `docs/proposals/trusted-proxy-migration.md` has a table of the value each kind of deployment needs. Most sites behind a proxy or hosting platform need a hop count. Where a trusted proxy or load balancer adds its entry to a forwarded header the caller may already have filled in, setting the number of hops to that trusted proxy is what makes the client address trustworthy: too few gives everyone the proxy's address, too many believes the caller. On Azure App Service, leave it unset for now: the client address arrives with a port, which the explicit settings refuse, so every visitor would get the same address. That is a follow-up.

While `TRUST_PROXY` is unset, Nightscout logs a `SECURITY:` line at startup saying the failed-login delay is keyed on an address taken from headers any caller can set, and how to fix that. This is one flag, not two: the failed-login delay keys on the same client address, so `TRUST_PROXY` moves both.

### Evidence

- New and changed tests in `client-ip`, `authdelay`, `authsubjects` and `env`. Each was checked by breaking the code it covers; every break fails on the original symptom.
- `authdelay` sends the correct secret, and a request with no credential, from the same address as the failures, and expects both to wait; against a check-first order both fail, answered in 3-5 ms.
- Full suite at this tip, Node 24.15.0, MongoDB 7 with a raised open-file limit: **2567 passing**, 3 pending, 0 failing.
- A local lab put Nightscout behind real proxies (nginx appending and replacing, two nginx hops, Caddy, Traefik, HAProxy, a TLS terminator, and a PROXY-protocol load balancer in front of two nginx hops) and read back the address Nightscout recorded. With the hop count set to the trusted proxy, every topology resolved the real client and ignored forwarded headers the caller sent; one hop too few gave a proxy's address, one too many believed the caller. Unset resolved exactly as `dev`.
- None of `client-ip`, `authdelay` or `authsubjects` is in `test:unit` or `test:integration`; use `npm test`, as CI does.
- Merges cleanly into `dev`, and with #8748, #8749, #8750 and #8751. Integrated with all of them and the other 15.0.9 changes before the hop-count commit, the suite passed on Node 20, 22 and 24 against MongoDB 4.4 and 7.0; that combined run still has to be repeated with this tip.
- Against #8605 it conflicts in adjacent lines only. Three deliberate differences: with `TRUST_PROXY` unset, the client address is resolved exactly as `dev` does, not as #8605's default does; `TRUST_PROXY` here also accepts hop counts and `true`, which #8605 refuses; and the v1 and v3 API apps do not set their own `trust proxy`, because each already inherits the server's (#8605 sets it on all three).

