# M7 first local join and hot-path configuration repair

*Contributor-facing measurement record, captured 2026-11-11. Synthetic fixtures only.
This records focused local acceptance; the complete M7 candidate is not frozen or accepted.
Programme state lives in the release contents and queue.*

## Source and verdict

Core `codex/m7-join-20261111` at `65ea9e37cb93e7e8e50f512cb3a6bc4709435011`,
based on capacity fixes `5c60aec669362b032a10d6dd7ac368e9c61e8003`, incorporates original histories:

- API replicas `9a450111c476afe4ee9c510738b470524f2f1cf5`.
- Realtime connection/cache changes `002c0d28e33313bca5fa41292fa8d5f9274a1b59`.
- D6 no-trigger-NOTIFY control `9179146638094fcf2b0f642a51d03a272098168e`.
- Realtime changed-parse-only roster validation `841683e2`.
- Admission configuration-cache repair and test inventory repair `65ea9e37`.

**Reproduced on the committed join:** affected campaign 132 passing, zero failing;
disposable PostgreSQL fixed-roster census 4 passing, zero failing; test-tier inventory
663 files across 8 tiers passes; no-trigger-NOTIFY check passes; changed-code lint
and whitespace checks pass. No full regression/browser/corpus/capacity campaign or final
prcheck was run: the remaining capability changes have not joined.

## Reproduced mechanism and repair

`lib/server/realtime/admission.js` reread its entire configuration file and enumerated
the tenant roster on every authority check. Realtime's configuration loader separately
re-enumerated its roster on unchanged reads. Cache the parsed file against filesystem
identity (device, inode, size, nanosecond modification/change times, mode) and the
current configured byte limit. Validate roster expansion on a changed parse.
Unchanged authority checks then perform a stat and a map lookup, without the full-file
read or roster scan. This is a call-count result, not a CPU/capacity improvement claim.

`tests/socket-admission-cache.test.js` proves no file reads/roster enumeration over
repeated unchanged checks; immediate disabling and alias-change refusal; repeated
expansion refusal; same-size edits; invalid/deleted/nonregular file refusal; and
changed byte-limit refusal. Unknown aliases retain `TENANT_HOST_UNKNOWN`.

Controls run in the coordinator-owned worktree, then restored:

| control | exact red symptom | restored result |
|---|---|---|
| Bypass identity-cache hit | `ADMISSION_UNCHANGED full-file reads`: 200 versus expected 0, exit 1 | focused campaign passes |
| Reuse cached value after file replacement | `ADMISSION_DISABLED`: true versus expected false, exit 1 | disabling immediately refuses |

Controls are retained in [control-no-cache.log](control-no-cache.txt) and
[control-stale-cache.log](control-stale-cache.txt).

The joined test inventory now registers the previously unregistered
`realtime-disconnect-causes.test.js` and `realtime-reconnect-surge.test.js`, plus the
new admission cache test. The existing API graceful-drain implementation and its
semantic control already exist; the old queue note describing immediate drops was stale.

## Commands and instruments

Run from the exact core source above using its installed lockfile dependencies:

```bash
node node_modules/mocha/bin/mocha.js --reporter dot \
  tests/socket-admission-cache.test.js tests/realtime-config-cache.test.js \
  tests/multitenant-config-bound.test.js tests/realtime-bootstrap.test.js \
  tests/realtime-api-client.test.js tests/fixed-roster-config.test.js \
  tests/realtime-disconnect-causes.test.js tests/realtime-reconnect-surge.test.js \
  tests/realtime-socket-server.test.js tests/realtime-preview.test.js \
  tests/realtime-readiness.test.js tests/internal-api-shutdown.test.js \
  tests/internal-api-composition.test.js tests/internal-api-listener-config.test.js \
  tests/no-trigger-notify.test.js
NS_API_ROSTER_DOCKER_TEST=1 node node_modules/mocha/bin/mocha.js \
  --timeout 120000 --reporter dot tests/api-fixed-roster.integration.test.js
node scripts/test-tiers.js check
node scripts/check-no-trigger-notify.js
node node_modules/eslint/bin/eslint.js lib/server/realtime/admission.js lib/server/realtime/contract.js
git diff --check
```

Retained outputs: [focused.log](focused.txt), [native-census.log](native-census.txt).
The native instrument pins its PostgreSQL image, creates its own uniquely named container
and sockets, and tears them down. It uses synthetic lifecycle participants with actual
role-identity database connections and real transports. It does not boot two serving API
applications or measure healthy-tenant traffic. Host loopback/subprocess permission was
required; initial sandbox EPERM failures are setup failures, not semantic controls.

## Remaining capability and acceptance boundaries

- Authorization CPU/allocation profile captures were recovered locally, but no credential
  cache, permission-query consolidation or measured end-to-end speedup is claimed here.
- Registry completion and its unfinished edits remain separate; live addition follows it.
- D6 reader transport, targeted scheduling, independent activity control, paged recovery,
  least-privilege grants and deployment binding remain open; the no-trigger control alone
  does not implement D6.
- Actual serving API replicas still need cross-replica authority/revocation, held-response
  maintenance with B progress, uncertainty, replacement while pinned, and pool budgets.
- Realtime edge flood controls, deploy-generated configuration, full-stack recovery and
  capacity remain open. Isolated Socket.IO fixtures are not a deployed capacity result.
- Keep original source/instrument attribution for earlier lane evidence. Join complete
  planned capabilities before one coherent full/default-browser/enabled-corpus/native
  campaign and final prcheck; quiet-host capacity follows functional acceptance.

## Authorization profile recovery

[Sanitized prior-capture summary](authorization-profile-recovery.json) preserves the
CPU/allocation/statement observations from the stopped session. Its saved source marker
names core `5c60aec6` and deploy `d1c7aca`, using image code. This session read the
capture and reduced a saved JWT CPU/allocation profile; it did not rerun that workload.
The bench scripts were untracked, so their execution-time identity is UNMEASURED;
the summary records their hashes at recovery. Pin the instrument and use owned resources
for the next comparison before claiming a current-source performance gain. Raw profiles,
credentials and the existing bench deployment remain local and untouched.

## D6 native discriminator rerun

The [D6 proof and retained controls](../d6-native-discriminators-2026-11-11/README.md)
were independently rerun with the clean joined source anchor `65ea9e37`:
[raw coordinator capture](d6-native-root.json), PASS, 36 SQL cases and 22 assertions,
container cleanup exit 0. This uses a simplified synthetic metadata schema, not shipping
reader modules. It proves a fixed-slot SECURITY DEFINER wrapper can expose reviewed
cross-tenant metadata to an EXECUTE-only login without changing ordinary FORCE RLS
reads. The privileged NOLOGIN owner holds REPLICATION; the login does not.

It also reproduces the SQL target limit: one 5,000-insert transaction produces 5,003
messages and 289,012 data bytes despite a requested target of one. An outer LIMIT
limits client output, not this wrapper's materialized decode. A production SQL reader
still needs reviewed runtime wrapper/publication admission, notify-before-advance crash
ordering, resource bounds and explicit degraded backstop recovery. These results
support the chosen transport direction without establishing its production bounds.
