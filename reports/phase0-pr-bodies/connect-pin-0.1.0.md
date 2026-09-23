# `bf/connect-pin-0.1.0`: install nightscout-connect from npm as an exact version

> **DRAFT, not yet opened as a PR.** Prepared 2026-09-22 against `origin/dev` `74fc6619`. The
> branch pins the prerelease `0.1.0-dev.1`. **15.0.9 must not be released on a prerelease pin:**
> a cgm-remote-monitor release pins only a full connector release. When `nightscout-connect`
> 0.1.0 is published, this PR becomes a one-token swap, `0.1.0-dev.1` → `0.1.0`, plus a
> regenerated lockfile. The exact commands are under "Swapping to 0.1.0" below.
>
> **Sequencing (maintainer, 2026-09-23):** 0.1.0 is tagged only after `0.1.0-dev.1` has had longer
> prerelease testing on this branch, and after BF-89 (the nightscout source's reader subject sent
> `role` for `roles`) is fixed in connector `dev`. The fix is prepared as `fix/nightscout-reader-roles`
> `dea2bec`. After 0.1.0 is published, re-run this branch's suite and the debug-logging control against
> it before the swap commit, because 0.1.0 will then carry at least one commit that `0.1.0-dev.1` does not.

## What changes for you

Nightscout uses a separate component, **nightscout-connect** (the connector), to fetch readings
from a CGM company's online service: Dexcom Share, MiniMed CareLink, LibreLinkUp, Glooko and
others. This PR changes which version of the connector Nightscout installs. It changes no
Nightscout code and no setting you have configured.

Compared with 15.0.8, the connector in this release:

- **no longer writes your CGM account username, password, session tokens or glucose readings
  into Nightscout's log.** The connector that 15.0.8 installs does this every time Nightscout
  starts, for every data source, and no setting turns it off.
- keeps its detailed diagnostic logging **off unless you turn it on** (`CONNECT_DEBUG`, or
  `DEBUG_LOGGING`).
- no longer stores a CareLink "no reading" marker as a glucose value of 0. While that 0 was the
  newest value, the high and low alarms were not checked.
- waits a sensible time between retries after a vendor outage, capped at 30 minutes, instead of
  retrying every quarter of a second and then, after enough failures, not retrying for days.
- shuts down cleanly when Nightscout stops.
- carries updated LibreLinkUp support (the current v4 service, its regional servers and its
  lockout recovery) and a more complete Glooko import.

Two new optional settings, `CONNECT_START_JITTER_MS` and `CONNECT_INTERVAL_JITTER_MS`, spread out
when sites contact the vendor. Both default to 0, so nothing changes unless you set them.

### If you ran 15.0.8 with the connector turned on

**Treat the password for your CGM account as exposed.** Change it at the CGM company's own site,
and change it anywhere else you have used the same password. Delete old Nightscout log files you
still have, and check anywhere you may have pasted a log: a GitHub issue, a forum or group post, a
screenshot, a message to someone helping you. Updating Nightscout stops new logs containing the
password; it cannot remove a password that is already in an old log.

Nightscout is not a medical device, and this is not medical advice. If you rely on Nightscout's
alarms, keep a second way to see your readings, and talk to your care team about any gap in your
data that worries you.

---

## Technical detail

```diff
-"nightscout-connect": "https://github.com/nightscout/nightscout-connect/archive/234d47c85510a77f07b3be0d2c026dd0272715d6.tar.gz",
+"nightscout-connect": "0.1.0-dev.1",
```

`package-lock.json` changes in two places: the root dependency spec, and the
`node_modules/nightscout-connect` entry, which now reads

```
"version": "0.1.0-dev.1",
"resolved": "https://registry.npmjs.org/nightscout-connect/-/nightscout-connect-0.1.0-dev.1.tgz",
"integrity": "sha512-r3exLBmzjKQVZOm0d0L0L6g0QcwzvFMsSBfMMPFV8gSmfjyyVVoWSRkdLhwj1Y/YgHPmK4kPJOIQEVBFe6lCpw==",
```

Diff stat: `package.json` 1 insertion / 1 deletion, `package-lock.json` 4 / 4.

- **The pin is an exact version, not a range**, so `package.json` itself names the connector that
  ships, and `npm ci` checks the tarball against the registry's integrity hash.
- `0.1.0-dev.1` was published from tag `v0.1.0-dev.1`, which points at connector commit `1946beb`
  (`gitHead` in the registry metadata agrees), with npm provenance (SLSA v1 attestation).
- `1946beb` contains `234d47c`, the commit `dev` pinned before, plus 44 non-merge commits.
- The connector's runtime `dependencies` are identical at `234d47c` and `1946beb`, so no other
  lockfile entry moves.
- The embedding contract Nightscout uses is unchanged: `require('nightscout-connect')(env, ctx)`,
  `connect.debug`.
- The `.npmrc` line `allow-remote=root` (added in `9f181789` so npm 12 would accept the GitHub
  tarball) is no longer needed by any dependency. This PR leaves it in place. `npm ci` succeeds
  with npm 12 either way.

### `overrides` and the connector's dependency tree

- `overrides['nightscout-connect'].axios = "1.20.0"` satisfies the connector's declared
  `axios ^1.18.1`. This is the constraint that is violated on `master` (BF-43: `1.16.0` against
  `^1.18.1`); on this branch it holds.
- **The root-level `"qs": "6.15.1"` override does not.** The connector declares `qs ^6.15.3`, and
  the global override installs `qs` 6.15.1 for it (`npm ls qs` shows
  `nightscout-connect → qs@6.15.1`, and no nested copy). `npm audit --omit=dev` reports that
  version against three moderate `qs` advisories (GHSA-q8mj-m7cp-5q26 affects `<=6.15.1`;
  GHSA-x5fp-wj9c-mxmx affects `<=6.15.3`; GHSA-4mjr-xmp4-gh2g affects `<6.16.0`). The same
  override and the same connector range are on `origin/dev` today, so this PR does not introduce
  it, and it does not fix it: the override also governs `express`, `body-parser` and `request`,
  and moving it is a separate change.

## Verifying it

Node 24.20.0 / npm 11.19.0 unless noted, against a private `mongo:7`, full suite
(`mocha --timeout 5000 --require ./tests/hooks.js --exit ./tests/*.test.js` with
`tests/ci.test.env`, Mongo URI and port changed to the private container). Arms run back to back:

| arm | connector installed | passing | failing | pending |
|---|---|---|---|---|
| this branch | 0.1.0-dev.1 (registry) | 2386 | 0 | 3 |
| `origin/dev` `74fc6619`, unmodified | 0.0.13 (self-reported; GitHub archive of `234d47c`) | 2386 | 0 | 3 |

Install checks:

- `npm ci` from an empty `node_modules` succeeds on Node 24.20.0 (npm 11.19.0), Node 20.20.0
  (npm 10.8.2), and with npm 12 on Node 24.20.0.
- **The integrity check is live:** with the lockfile's `nightscout-connect` integrity replaced by
  a wrong hash, `npm ci` fails with `EINTEGRITY`, naming the registry's real hash.

**The suite can tell connectors apart.** `tests/debug-logging.test.js` boots the installed
connector under five `DEBUG_LOGGING` × `CONNECT_DEBUG` combinations and asserts how many console
lines it writes. With connector `v0.0.13` (the version 15.0.8 installs) put in place of
`0.1.0-dev.1`, exactly those five cases fail and the other 18 pass. Each failure is an assertion
on the log line count (`2 == 0` or `2 == 1`): the old connector writes two lines whatever the
debug settings say. It is not a load error. With `0.1.0-dev.1` restored, 23/23 pass.

```
TEST=debug-logging npm run test-single
npm test
```

## Swapping to 0.1.0

When `nightscout-connect` 0.1.0 is on npm, in this branch's worktree:

```sh
# 1. Confirm 0.1.0 is published, from the expected commit, with provenance.
npm view nightscout-connect@0.1.0 version gitHead dist.integrity dist.attestations.provenance.predicateType
#    expect: version 0.1.0; gitHead is the commit tag v0.1.0 points at;
#    predicateType https://slsa.dev/provenance/v1
git -C ../../nightscout-connect fetch --tags origin && git -C ../../nightscout-connect rev-parse 'v0.1.0^{commit}'

# 2. The one-token swap.
sed -i 's/"nightscout-connect": "0.1.0-dev.1"/"nightscout-connect": "0.1.0"/' package.json
grep -n '"nightscout-connect": "' package.json   # must print exactly one line: "nightscout-connect": "0.1.0",

# 3. Regenerate the lockfile from the registry (Node 24; package.json engines is >=20).
npm install --no-audit --no-fund
git diff --stat                                # expect package.json 1+/1-, package-lock.json 4+/4-

# 4. The lockfile resolves 0.1.0 from the registry with an integrity hash.
python3 -c "import json,sys; e=json.load(open('package-lock.json'))['packages']['node_modules/nightscout-connect']; print(e['version'], e['resolved'], e['integrity']); sys.exit(0 if e['version']=='0.1.0' and e['resolved'].startswith('https://registry.npmjs.org/') and e['integrity'].startswith('sha512-') else 1)"

# 5. A clean install works, and the suite still passes.
rm -rf node_modules && npm ci
npm test

# 6. Commit.
git commit -am 'Nightscout installs the connector from npm as exactly 0.1.0'
```

If the lockfile diff in step 3 touches anything beyond the root dependency spec and the
`node_modules/nightscout-connect` entry, the connector's own dependency ranges changed between
`0.1.0-dev.1` and `0.1.0`. Stop and review that before committing.

## Semver: patch

A dependency pin moves; no Nightscout route, response shape, environment variable or default
changes. The two new jitter settings belong to the connector and default to 0. The behaviour
change is the connector's, and the release notes should carry "What changes for you" above,
including "If you ran 15.0.8 with the connector turned on". That section is the only place most
operators will be told to change their password.

## Follow-ups not in this PR

- The swap to `0.1.0`, once published (above).
- The root `qs` override (6.15.1) against the connector's `^6.15.3` and the three `qs`
  advisories. It also governs `express`, `body-parser` and `request`.
- The `.npmrc` `allow-remote=root` line and its comment now describe a dependency that is gone.
- `master` (15.0.8) still installs connector `v0.0.13`; that is a separate release decision.
