# `bf2/auth-hardening`: withheld-style PR body

**Posting copy for the public PR (maintainer decision 2026-09-23).** Everything below the line is posted as-is. The full text is [bf2-auth-hardening.md](bf2-auth-hardening.md), for after release.

---

> **Details withheld.** Part of this PR fixes security issues present in released versions. No release contains the fixes yet, so this description is kept short on purpose. The full description, including what site owners should do after upgrading, will be added once a fixed release is out.

### Summary

This combines two branches that were already reviewed on their own, backports the client-address handling from #8605 behind a new setting, and fixes one admin-page save:

- **Subject storage** no longer writes a subject's derived fields to the database. Existing access tokens keep working: they are re-derived on every load, as before.
- **The failed-login delay** now applies only to the request that failed, not to every request from that address. The list of recent failures is cleared on a schedule and has a size limit.
- **A new setting, `TRUST_PROXY`**, says whose forwarded headers (`X-Forwarded-For`, `X-Forwarded-Proto` and similar) Nightscout believes. **Unset, behaviour is exactly as today**, so nobody needs to change anything to upgrade.
- **Editing a subject or role on the admin page keeps its `notes` and `created_at`.** Before, saving it wiped the notes and replaced the creation date.

### `TRUST_PROXY`

| value | what Nightscout believes | for |
|---|---|---|
| not set (default) | forwarded headers from anyone, as today | upgrading without changes |
| `false` | no forwarded headers; the connecting address, and whether that connection itself is https | sites reached directly, with no proxy |
| proxy IPs or CIDR ranges, comma-separated | forwarded headers only from those addresses | sites behind a proxy whose address is known |

`true`, hop counts and names such as `loopback` are rejected at startup. `CUSTOMCONNSTR_TRUST_PROXY` also works.

**Behind a proxy that terminates https, set it with care.** With `false`, or a list that leaves out the proxy, Nightscout stops believing the proxy's "the visitor used https" header and redirects to https in a loop. If the site stops loading after setting it, unset it and check the address Nightscout actually sees the proxy connect from.

While `TRUST_PROXY` is unset, Nightscout logs a `SECURITY:` line at startup saying the failed-login delay is keyed on an address taken from headers any caller can set, and how to fix that. This is one flag, not two: the failed-login delay keys on the same client address, so `TRUST_PROXY` moves both.

### Evidence

- New and changed tests: `client-ip` 48, `authdelay` 19, `authsubjects` 13, plus one `env` test. Each was checked by breaking the code it covers; every break fails on the original symptom.
- Full suite, Node 20.20.0, MongoDB 7 with a raised open-file limit: `dev` 2386 → **2467 passing**, 3 pending, 0 failing.
- None of `client-ip`, `authdelay` or `authsubjects` is in `test:unit` or `test:integration`; use `npm test`, as CI does.
- Merges cleanly into `dev`, and with #8748, #8749, #8750 and #8751; integrated with all of them and the other 15.0.9 changes, the suite passes on Node 20, 22 and 24 against MongoDB 4.4 and 7.0.
- Against #8605 it conflicts in adjacent lines only. The one deliberate difference: with `TRUST_PROXY` unset, the client address is resolved exactly as `dev` does, not as #8605's default does.
