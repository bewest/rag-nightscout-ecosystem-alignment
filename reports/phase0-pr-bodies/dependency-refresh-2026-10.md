<!-- Body of #8794, branch bf/dependency-refresh-2026-10 (22d82889, merged with dev 839a1565 as 7cb8d0bc). This comment is hidden on GitHub. -->
Seven `package.json` override entries move to the patch releases that fix advisories published after the 2026-09-27 triage (BF-147), and the lockfile picks up fixed releases of `webpack-dev-middleware` and `dompurify` within their declared ranges (BF-153). One commit on `dev` `50bc1084`. `npm audit --package-lock-only` (npm 11.12.1) goes from 20 findings (4 high) to 8 (0 high). The production bundle is byte-identical.

## What changes for you

*A plain-language summary for people who run their own Nightscout site, for themselves or for a family member. Nothing here is medical advice.*

**What this is.** Nightscout is built from many smaller software libraries written by other people. Since late September, security notices ("advisories") were published against some of them. This change moves those libraries to the versions that fix the notices.

**What changes in how Nightscout works.** Nothing. Your site shows the same glucose readings, alarms, treatments and reports as before. The page your browser loads is the same file, byte for byte.

**Which libraries.** Most are tools used only to build Nightscout or to run its tests, not to run your site. Two are used by a running site, in features most sites do not turn on: loading settings from another web address (`IMPORT_CONFIG`) and the MiniMed CareLink bridge. Neither problem can be triggered by someone visiting your site on its own.

**Do you need to do anything?** No. The next release includes this change. Nothing to set or change.

## Technical detail

### Overrides moved to the fixed release

Overrides win over every declared range, so `npm audit fix` could not propose these.

| Override | Before → after | Advisory | Where it runs |
|---|---|---|---|
| `ip-address` | 10.7.0 → 10.7.1 | GHSA-j6r3-76f7-8jcv, GHSA-h3mg-xc3c-68pw | MongoDB driver's `socks` client, only when the database is reached through a SOCKS5 proxy. `socks` parses the configured proxy host and the proxy's replies and does not call `isInSubnet`. No request input reaches it. |
| `fast-uri@^3.0.0` | 3.1.7 → 3.1.8 | GHSA-hrr3-gc8f-f4qj | ajv 8 under `babel-loader`'s `schema-utils` and `eslint`: bundle build and lint. |
| `brace-expansion@^1/^2/^5` | 1.1.18 → 1.1.21, 2.1.4 → 2.1.7, 5.0.9 → 5.0.12 | GHSA-q2hr-2g5m-vwhr, GHSA-qhr7-859c-m2p7, GHSA-6j4f-fj2g-mc7p | minimatch, glob, EJS's Jake/FileList, mocha, nyc, nodemon. Patterns come from code and test globs, not request input. |
| `minimed-connect-to-nightscout` › `axios`, › `axios-cookiejar-support` › `axios` | 0.33.0 → 0.34.0 | GHSA-9fr6-4gfg-395g, GHSA-x97p-jq2g-jp4f | `IMPORT_CONFIG` (`lib/server/bootevent.js`) and the CareLink bridge. Both advisories are prototype-pollution gadgets: they need a separate bug that has already polluted `Object.prototype`. |

The `axios` devDependency range moves from `^0.33.0` to `^0.34.0` to match.

### Lockfile refresh within declared ranges

- `webpack-dev-middleware` 8.0.3 → 8.3.0 (GHSA-g84c-rxfj-3j2c). Loaded only when `NODE_ENV=development`; the `publicPath` it is given (`/devbundle/`) ends in a slash, which the advisory needs it not to. Brings `memfs` 4.57.2 → 4.80.0, eight `@jsonjoy.com/fs-*` packages 4.57.2 → 4.80.0, `glob-to-regex.js` 1.2.0 → 1.3.1, `thingies` 2.6.0 → 2.6.1, and adds a nested `range-parser` 1.3.0.
- `dompurify` 3.4.14 → 3.4.16 (GHSA-p98j-92pf-mc4p). A devDependency used only by `tests/sanitizer-differential.test.js`; `lib/server/purifier.js` does not load it and the browser bundle does not contain it.

26 lockfile versions change (25 updated, 1 added), all patch or minor. Sixteen unchanged `memfs` dependencies gain the `resolved` and `integrity` fields the previous lockfile lacked. `lockfileVersion` stays 3; no resolved URL changes. `npm install --package-lock-only` also flips `@types/tough-cookie` to `dev: true` even with `dev`'s own `package.json`; that unrelated flip is left out, since `axios-cookiejar-support` (a production package) declares it as a peer.

### Deliberately left

- `moment` stays at 2.30.1 (GHSA-4p3w-j4w9-5jqw): no request input reaches `moment.locale` on `dev`, and 2.31.0 changes parsing and locale display output in the browser bundle.
- `sanitize-html` (deliberate pin), `csv-parse`, `request` and `uuid`: unchanged since the 2026-09-27 triage.

### `npm audit --package-lock-only` (npm 11.12.1)

Counts are packages with a finding; one advisory is counted once for each package that depends on it.

| | All | High | `--omit=dev` | High |
|---|---|---|---|---|
| `dev` `50bc1084` | 20 | 4 | 16 | 4 |
| this branch | 8 | 0 | 6 | 0 |

The 8 left: `csv-parse`, `istanbul-lib-processinfo` (via `uuid`), `minimed-connect-to-nightscout` (via `request`), `moment`, `request`, `sanitize-html`, `share2nightscout-bridge` (via `request`), `uuid`. That is the 7 left after BF-147 plus `moment`. With `--omit=dev`, `csv-parse` and `istanbul-lib-processinfo` drop out. npm 10.9.8 (Node 22.23.2) counts `dev` as 21 and 17 and this branch as 8 and 6.

## Tests

- `tests/dependency-overrides.test.js`: for `ip-address`, `fast-uri`, `axios` 0.x, `dompurify` and `webpack-dev-middleware`, every locked copy matches the installed tree and is at or above its floor (`nightscout-connect`'s `axios` 1.x is a separate line and is skipped). `ip-address`, as loaded through `mongodb` › `socks`, no longer places an address inside a subnet of the other family and bounds its parse diagnostic for a long invalid IPv6 string. `axios`, as loaded by the server and by `minimed-connect-to-nightscout`, keeps the GET method when `Object.prototype.method` is set.
- `tests/dependency-brace-expansion.test.js`: the floors per major rise to 1.1.21, 2.1.7 and 5.0.12, and every copy expands 5000-deep nested alternatives without exhausting the stack.

On `dev`'s installed tree all 27 new or raised cases fail (versions below the floor, `isInSubnet` true across families, a 40,034-character diagnostic, `delete` chosen as the method, `RangeError` in all nine `brace-expansion` copies); the 5 copy-presence guards pass on both.

### Validation (Node 22.23.2, MongoDB 7.0.43 in a dedicated container)

- Full suite (`ci.test.env` form): 3512 passing, 0 failing, 4 pending, against 3489/0/3 on `50bc1084`; the 23 passing and 1 pending added are this commit's.
- Production bundle built at `50bc1084` and at this commit (webpack 5.106.2): byte-identical, all 7 files under `node_modules/.cache/_ns_cache/public`. Builds from `npm ci` on Node 20.20.0 and 24.20.0 match too.
- `IMPORT_CONFIG` pointed at a local server returning a settings object: one GET with `Accept: application/json`, and the same `units`, `customTitle`, `theme`, `thresholds.bgHigh` and `extendedSettings.pump` in `/api/v1/status.json` as on `dev`.
- `npm ci` succeeds on Node 20.20.0 (npm 10.8.2), 22.23.2 (npm 10.9.8) and 24.20.0 (npm 11.19.0). The npm 12 job reproduced (Node 24.20.0, npm 12.2.0): `npm ci`, `npm run test:dependencies` (345 passing, 1 pending) and `npm run bundle-dev` succeed.
- ESLint on the two changed test files: clean. `git diff --check` is clean.
