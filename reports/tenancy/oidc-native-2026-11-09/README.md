# Owner/OIDC native acceptance matrix, disposable harness run (2026-11-09)

*Contributor-facing measurement record. Queue item `MT-OIDC-NATIVE` (milestone M6a). Decision of record: `releases/cgm-remote-monitor-16.0.0/decisions.md#disposable-native-harness`. Written from the run output in this directory; nothing here is quoted from memory.*

## What ran, on what

| Fact | Value (from `summary.json`) |
|---|---|
| Source commit executed | `3b09131e9c33bd765a58e6a25ce48c1fb8edd372` on branch `codex/oidc-native-harness-20261109` (candidate `c0a67b69e01ff430ab053286364251221c9afb4b` plus two test-only commits: the Vault 1.17+ status fix in `tests/human-access-vault-native.js` and the harness itself) |
| Tree state at start | `git status --porcelain --untracked-files=all` empty (0 entries) |
| Harness | `tests/native/oidc-matrix/` (`run.sh`, `run.cjs`, `stage.cjs`, helpers carried over from the 2026-11-07 preparation) |
| PostgreSQL | `postgres@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea`, `postgres (PostgreSQL) 16.15`, server_version `16.15` |
| MongoDB | `mongo@sha256:1f995ad6fdb93244a1addab1b58f934a0bc2f5643c38e02f5e9d7f0c7d227a7b`, `db version v7.0.43`, buildInfo `7.0.43` |
| Vault | `hashicorp/vault@sha256:962a92876e168d68eaaa24b0b8b49bbce1cb63024060a67bba95cd158a366fc2`, `Vault v2.2.1 (0e7c41b936218bd2401ab0f891c93bec10e2e8e4), built 2026-10-22T16:27:49Z`, sys/health `2.2.1`; TLS listener, private per-run CA trusted through `NODE_EXTRA_CA_CERTS`, in-memory storage |
| Node / browser | `v22.23.4` / `Google Chrome 154.0.8037.57` (`/usr/bin/google-chrome` via playwright-core) |
| oref0 pinned client | `d219baf9559d62a8bb0bd42014192a2d7c0839ef` (`externals/oref0`) |
| Compose project / loopback ports | `oidcmatrix-20261109t200708z-1204685`; postgres 36658, mongo 36657, vault 36659 (ephemeral, 127.0.0.1 only) |
| PostgreSQL identities | admin `postgres` (container superuser) plus seven `NOSUPERUSER NOBYPASSRLS` roles: `om_app`, `om_clinical`, `om_legacy`, `om_owner`, `om_reader`, `om_secrets`, `om_settings` |
| Synthetic tenants | `11111111-1111-4111-8111-111111111111`, `22222222-2222-4222-8222-222222222222` |
| Wall clock | matrix 15980 ms (2026-11-09T20:07:11.197Z to 2026-11-09T20:07:27.177Z); controls run 14727 ms |

Containers were started by `run.sh` for this run only and removed with `docker compose down -v --remove-orphans` on exit (`compose-down.log`; `commands.log` records "containers remaining ...: 0"). Every stage ran in a fresh database (`owner_oidc_<nonce>`) in its own child process under the contract deadline (90 s or 120 s active plus 15 s teardown plus 20 s harness grace). After each stage the harness measured leftovers: owned PostgreSQL schemas, Mongo collections and Vault mounts beyond the provisioning baseline. All nine stages left none (`leftovers` in `summary.json`).

## Commands

From `commands.log` (the `+` lines are the commands executed; `stages/*.log` hold each stage's redacted stdout/stderr):

```
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 2 -subj /CN=oidc-matrix synthetic CA -keyout /tmp/oidc-matrix-HPpeLptK/tls/ca.key -out /tmp/oidc-matrix-HPpeLptK/tls/ca.crt
openssl req -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -subj /CN=vault -keyout /tmp/oidc-matrix-HPpeLptK/tls/vault-server.key -out /tmp/oidc-matrix-HPpeLptK/tls/vault-server.csr
openssl x509 -req -in /tmp/oidc-matrix-HPpeLptK/tls/vault-server.csr -CA /tmp/oidc-matrix-HPpeLptK/tls/ca.crt -CAkey /tmp/oidc-matrix-HPpeLptK/tls/ca.key -CAcreateserial -out /tmp/oidc-matrix-HPpeLptK/tls/vault-server.crt -days 2 -extfile /tmp/oidc-matrix-HPpeLptK/tls/san.ext
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 2 -subj /CN=oidc-matrix fixture -addext subjectAltName=IP:127.0.0.1,DNS:localhost -keyout /tmp/oidc-matrix-HPpeLptK/tls/fixture.key -out /tmp/oidc-matrix-HPpeLptK/tls/fixture.crt
docker compose -p oidcmatrix-20261109t200708z-1204685 -f /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/compose.yaml up -d --wait --wait-timeout 180
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/run.cjs --out /tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/d932d68d-9c16-442c-84b7-bd75ad82cc68/scratchpad/final-full --state /tmp/oidc-matrix-HPpeLptK --project oidcmatrix-20261109t200708z-1204685 --pg-port 36658 --mongo-port 36657 --vault-port 36659
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/stage.cjs vault-single /tmp/oidc-matrix-HPpeLptK/config-01-vault-single.json /tmp/oidc-matrix-HPpeLptK/result-01-vault-single.json
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/stage.cjs vault-multi /tmp/oidc-matrix-HPpeLptK/config-02-vault-multi.json /tmp/oidc-matrix-HPpeLptK/result-02-vault-multi.json
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/stage.cjs mongo-sessions /tmp/oidc-matrix-HPpeLptK/config-03-mongo-sessions.json /tmp/oidc-matrix-HPpeLptK/result-03-mongo-sessions.json
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/stage.cjs pg-sessions /tmp/oidc-matrix-HPpeLptK/config-04-pg-sessions.json /tmp/oidc-matrix-HPpeLptK/result-04-pg-sessions.json
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/stage.cjs mongo-http /tmp/oidc-matrix-HPpeLptK/config-05-mongo-http.json /tmp/oidc-matrix-HPpeLptK/result-05-mongo-http.json
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/stage.cjs owner-consumer /tmp/oidc-matrix-HPpeLptK/config-06-owner-consumer.json /tmp/oidc-matrix-HPpeLptK/result-06-owner-consumer.json
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/stage.cjs owner-authority /tmp/oidc-matrix-HPpeLptK/config-07-owner-authority.json /tmp/oidc-matrix-HPpeLptK/result-07-owner-authority.json
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/stage.cjs owner-browser /tmp/oidc-matrix-HPpeLptK/config-08-owner-browser.json /tmp/oidc-matrix-HPpeLptK/result-08-owner-browser.json
node /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/stage.cjs owner-compatibility /tmp/oidc-matrix-HPpeLptK/config-09-owner-compatibility.json /tmp/oidc-matrix-HPpeLptK/result-09-owner-compatibility.json
docker compose -p oidcmatrix-20261109t200708z-1204685 -f /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/compose.yaml logs --no-color --timestamps
docker compose -p oidcmatrix-20261109t200708z-1204685 -f /home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-oidc-harness-20261109/tests/native/oidc-matrix/compose.yaml down -v --remove-orphans
```

## Per-stage verdicts

| Stage | Verdict | Duration (ms) | Families | Family names |
|---|---|---|---|---|
| vault-single | PASS | 265 | 1/1 | vaultSingle |
| vault-multi | PASS | 199 | 1/1 | vaultMulti |
| mongo-sessions | PASS | 440 | 1/1 | mongoNativeSessions |
| pg-sessions | PASS | 539 | 1/1 | postgresNativeSessions |
| mongo-http | PASS | 1973 | 4/4 | defaultOffSingle, mongoSignedHttps, singleBrowserLifecycle, singleLegacyCompatibility |
| owner-consumer | PASS | 2671 | 10/10 | clinicalImmutability, dataCredentialReplay, dataRevocation, evaluatorCycle, foreignTenantRefusal, httpPresentation, ownerCreateRoleIssueRevoke, pinnedClientReplay, settingsVersionHistoryRollback, tenantBImmutability |
| owner-authority | PASS | 2321 | 11/11 | actorRevocation, actorWaiter, auditRefusal, commitRefusal, delegationContainment, heldThroughCommit, operatorContainment, policyWaiter, projectContainment, roleWaiter, shiroGrammar |
| owner-browser | PASS | 4164 | 10/10 | ownerBearerParity, ownerBrowserBearerParity, ownerBrowserLogout, ownerBrowserMutations, ownerBrowserTabsBackReload, ownerCookieMutations, ownerCsrfOrigin, ownerCurrentAuthority, ownerSensitiveFreshness, ownerSessionLogout |
| owner-compatibility | PASS | 2072 | 6/6 | anonymousReadClamp, defaultOffMulti, legacyApiSecret, legacyEightHourExchange, legacySubject, planeSeparation |

All nine stages PASS; `complete: true`. Vault stages include the bounded consumer child (`vault-consumer.cjs`: a separate process holding only the sign-only configuration, never the admin token, issues and verifies one DATA and one MANAGEMENT token through the nonexportable Transit key). Browser stages (`mongo-http`, `owner-browser`) drove an actual Chromium through cookie and bearer flows; `owner-consumer` ran the pinned oref0 `ns-get.sh` client three times as a real child process.

## Red controls (authored mutants, executed)

Each control materialises one authored mutant from the preparation's descriptor modules into a `git archive` copy of the executed commit, runs the owning stage against that copy (expected red), then re-runs the same stage against the clean tree (expected green). Both attempts use fresh databases; leftovers were empty after the red runs as well.

| Control | Stage | Mutated file | Red run | Restored run |
|---|---|---|---|---|
| `single:single-shipping-eight-hour-exchange` | mongo-http | `lib/server/enclave.js` | FAIL (499 ms): `ERR_ASSERTION` shipping single subject JWT lifetime is eight hours | PASS (1907 ms) |
| `browser:csrf` | owner-browser | `lib/human-session/http.js` | FAIL (1252 ms): `ERR_ASSERTION` owner transport status oracle | PASS (4132 ms) |
| `consumer:consumer-current-data-authority-bypass` | owner-consumer | `lib/server/tenant-app/data-access.js` | FAIL (2536 ms): `ERR_ASSERTION` next DATA operation must read current role authority | PASS (2656 ms) |

Harness-level control: `tools/queue/gates/_oidc-native-recorded/missing-stage.json` is this `summary.json` with the `owner-browser` record removed; `node tools/queue/gates/oidc-native-recorded.js` on it exits 1 with `BAD owner-browser: 0 records` and exits 0 on the real record (13 checks).

## Infrastructure findings while bringing the harness up (reproduced)

1. **Vault key creation status.** Vault v2.2.1 (the pinned image) answers `POST transit/keys/<name>` with `200` and the key metadata; the vault probe asserted `204`. Every other status the probe asserts was re-measured unchanged on this image. Fixed in `tests/human-access-vault-native.js` (test instrument only): `expect()` takes a status list and the two key-creation calls accept `[200, 204]`.
2. **Consumer callback.** `probe-checks.json` requires the vault probe's sixth check, which only runs when a `consume` callback is supplied; the retired driver never supplied one, so the oracle could not have been satisfied as written. The harness supplies the bounded consumer child described above.
3. **Reader ledger grant.** `lib/tenant-settings/effective-postgres.js` runs the migration-ledger `check` through the settings-reader identity; the fixture (`prepare.cjs`) had granted that identity only the three data tables, so `owner-consumer` failed with PostgreSQL `42501 permission denied for table schema_migrations`. Fixed in the fixture: `SELECT` on `schema_migrations` in the settings and operator-policy namespaces.
4. Vault 2.x mounts `agent-registry/` by default; the leftover check baselines the mounts after provisioning instead of listing them.

None of these changed application code. No oracle failed on the candidate's actual behaviour.

## What is NOT established by this record

- Full mocha suite, browser suite, enabled-corpus acceptance and prcheck on this branch: not run by this harness (MT-M6A-JOIN owns the final campaign).
- Interoperability with a real OpenID provider: the issuer is the synthetic in-process fixture (tests/fixtures/human-oidc-provider.js) served over HTTPS.
- PostgreSQL connection capacity under the manifest upper bound (56): not measured; the container ran with the image default max_connections and no stage hit a limit.
- The headless owner management public keys are trust anchors only; no stage signs with them.
- Vault runs single-node in-memory storage with TLS from a per-run private CA; seal/unseal, renewal and rotation behaviour under Vault Agent are DEPLOY-VAULT-AGENT scope.
- Only three of the twenty authored mutant descriptors were executed as controls (listed above); the remaining seventeen stay NOTEXECUTED.
- The record is of one machine on one day; the harness is rerunnable (tests/native/oidc-matrix/run.sh) and a re-run is the way to re-establish any of it.

## Files

- `summary.json`: machine-readable record (sourceCommit, images, ports, stages[], controls[], leftovers, notEstablished).
- `stages/NN-<stage>.stdout.log`, `.stderr.log`: per-stage output, redacted (no secret matched; the stderr lines about `_ns_cache/randomString` and "Basal plugin" are shipping-module noise from the single-compatibility and evaluator fixtures).
- `service-logs.log`: PostgreSQL, MongoDB and Vault container logs for the matrix run, redacted. The only PostgreSQL ERRORs are the authority stage's intentional refusals (`synthetic owner commit refusal`, audit check-constraint violations).
- `controls/`: the same set for the controls run, plus `controls.json`.
- `compose-up.log`, `compose-down.log`, `compose-ps.json`, `openssl.log`, `commands.log`.
