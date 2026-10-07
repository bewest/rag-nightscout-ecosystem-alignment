<!-- Draft, not opened: branch bf/proxy-addr-2.0.8 at 7dd4f400 (one commit on dev 1ad03e29). This comment is hidden on GitHub. -->
`proxy-addr` moves from 2.0.7 to 2.0.8, which fixes GHSA-jqcg-44mw-7w3h (critical): a `TRUST_PROXY` entry written in IPv6 notation could make every client a trusted proxy (BF-162). One commit on `dev` `1ad03e29`. `TRUST_PROXY` is new in 15.0.9, so no released version is affected.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member.*

**Who is affected.** Only sites that set `TRUST_PROXY` to a list of proxy addresses, and only if one entry in that list is written in IPv6 notation with a short prefix (for example `::ffff:10.0.0.0/8`). `TRUST_PROXY` is a new setting in 15.0.9; no released Nightscout has it. If you leave it unset, which is the default, or set it to `true`, `false` or a number of proxies, nothing changes for you.

**What was wrong.** Nightscout uses the visitor's address to slow down repeated failed logins and to decide whether a request arrived over HTTPS. `TRUST_PROXY` tells it which proxies in front of it to believe about that address. With an entry like the one above, the library that checks addresses treated every visitor as a trusted proxy, so any visitor could state their own address.

**What this change does.** The updated library only trusts the addresses the entry actually names. Entries written in plain IPv4 notation (for example `10.0.0.0/8`) worked correctly before and still do.

**Do you need to do anything?** No.

## Technical detail

`lib/server/client-ip.js` `compileTrust` hands an explicit `TRUST_PROXY` address list to `proxyaddr.compile` (line 52). Each entry passes the `isIP` check, so an IPv6-notation subnet is accepted. Per GHSA-jqcg-44mw-7w3h (`proxy-addr >= 1.1.0, < 2.0.8`), proxy-addr before 2.0.8 compiles an IPv6 subnet whose leading bits are zero, such as `::ffff:10.0.0.0/8` (the correct spelling of that block is `::ffff:10.0.0.0/104`) or `::/1`, so that it matches every IPv4 address. Every client was then trusted at hop 0, and `X-Forwarded-For` decided the client address for the failed-login delay, the sockets, API v3 authentication and Express's `req.ip` and `req.secure`.

`proxy-addr` is a direct dependency (`package.json`: `^2.0.7`) and is shared with Express 4.22.2 (`~2.0.7`) at the top of the tree. 2.0.8 satisfies both ranges, so the change is:

- `package.json`: `"proxy-addr": "^2.0.8"`;
- `package-lock.json`: the root dependency range and the one `node_modules/proxy-addr` entry. `npm ls proxy-addr` shows a single 2.0.8, deduplicated under Express.

No `overrides` entry and no code change. `npm install --package-lock-only` (npm 10.9.8) also adds an unrelated `"dev": true` to `@types/tough-cookie`; that drift is left out.

15.0.8 calls `app.enable('trust proxy')`, which trusts every hop and never compiles a subnet list, so 15.0.8 cannot reach this code path; scanners still report its locked 2.0.7.

## Tests

`tests/client-ip.test.js`, new case *trusts only the IPv4 block an IPv6-notation entry names*: with `::ffff:10.0.0.0/8` and with `::/1`, a client at an unrelated IPv4 address keeps its own address whatever `X-Forwarded-For` it sends; with `::ffff:10.0.0.0/104`, a peer inside 10.0.0.0/8 is trusted and an outside one is not.

With proxy-addr 2.0.7 in place the new case fails on its first assertion (the client's own header is returned); the other 62 cases in the file pass on both versions.

### Validation (Node 22.23.2, MongoDB 7.0.43 in a dedicated container)

- Full suite (`ci.test.env` form): 3564 passing, 0 failing, 4 pending, against 3563 on `1ad03e29`; the 1 added is this commit's.
- `npm audit --package-lock-only` (npm 10.9.8, 2026-10-07): 24 findings, 9 high, 0 critical, against 25, 9 high, 1 critical on `1ad03e29`; proxy-addr no longer listed.
- ESLint on the changed test file: no findings. `git diff --check` is clean.
