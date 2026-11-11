# MT-CONNECTOR-SYNC-OUT (M6d lane C): a single-site Nightscout pulls from a multitenant tenant, all collections, long-running (DRAFT evidence record)

Lane measurement, 2026-11-10. It follows [connector-sync-2026-11-10](../connector-sync-2026-11-10/README.md) and closes the gaps that record lists as UNMEASURED. All data is synthetic. Credentials exist only in process memory and in child environments. Every log is redacted before it is written.

## Anchors (from git)
- cgm-remote-monitor `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1`, the #8898 head (`official/workspace/multitenant-20261102`, PR open). Worktree `externals/work/crm-connector-out-20261110` on branch `codex/connector-out-20261110`, no commits; `npm ci` was run in it.
- nightscout-connect, two builds:
  - **pin**: `b394411a39236b614beebffabf23ccc04f730a68` (`workspace.lock.json`), installed from `git archive` into scratch with `npm ci`. The `externals/nightscout-connect` checkout was not touched.
  - **emb**: npm `nightscout-connect@0.1.0`, the dependency of the crm tree above. Its `lib/` and `index.js` are byte-identical to the checkout `04102f9d` (`diff -rq` is empty); tag `v0.1.0` is `52e1c14f`.
- alignment `main` `c374c090b` when the record was written. Harness: `tools/tenancy/connector-sync/out.cjs`.
- Node v22.23.4. Containers `postgres:16`, `mongo:7.0` and Vault (pinned by digest), all named `ns-co-*`. All were removed at exit (`docker ps -a | grep -c ns-co` printed 0 after the runs).

## What runs
```bash
CRM_ROOT=$PWD/externals/work/crm-connector-out-20261110 \
CONNECT_PIN_ROOT=<git archive of b394411a, npm ci> CO_OUT=<scratch> \
node tools/tenancy/connector-sync/out.cjs
```
- **Tenant setup.** One `nightscout multitenant api` process serves two tenants (A and B, as direct aliases). Its preview config adds `subjectAdmin` (the root plane of the tenant admin tools) and `activity` (the durable pause/suspend reader).
- **Reader credential.** The reader role (`api:{entries,treatments,devicestatus,profile}:read`) and the reader subject are created through the tenant's **admin tools routes**: `POST /api/v2/authorization/roles` and `POST /subjects`, authenticated with the tenant root `api-secret`. The token is read from `GET /subjects`.
- **Writer.** A separate writer subject uploads synthetic entries, treatments, devicestatus and profiles through the tenant's v1 API.
- **Two destinations**, both `nightscout single` on one dedicated Mongo:
  - `D_pin` is fed by the pin as a sidecar (`forever --source nightscout`, token in `CONNECT_SOURCE_ENDPOINT`).
  - `D_emb` runs the connector **embedded** (`ENABLE=connect`, `CONNECT_SOURCE=nightscout`, `CONNECT_SOURCE_COLLECTIONS=entries,treatments,devicestatus,profiles`). This is how a family's existing site runs it. It stays up for the whole sequence, about 110 minutes, at the connector's own cadence.
- **Oracle** (independent of the connector): tenant rows are read from PostgreSQL directly, destination rows from MongoDB directly. They are compared per collection as multisets:
  - entries `(type, sgv, date)`
  - treatments `(eventType, created_at, insulin, carbs)`
  - devicestatus `(device, created_at, uploaderBattery, pump.reservoir)`
  - profile `(defaultProfile, startDate, store.Default.dia)`
- **Pause and suspend** use the activity store's `owner` and `operator` capabilities (`lib/tenant-activity/postgres.js` `transition`), the module the owner router calls. The owner HTTP route itself was not used.

**Cadence.** The connector has no setting that shortens it. The Nightscout source fixes `expected_data_interval_ms` at 5 minutes and aligns the next poll to the last entry plus 5 minutes plus 18–36 s (`lib/sources/nightscout.js` `align_to_glucose`). After a failed frame it adds `backoff({interval_ms: 2.5 min})`. So the loop ran at its normal cadence.

## Results: 3 full repetitions
Each repetition printed `SUMMARY 37 checks, 0 failing, 2 findings`. Logs: [rep1.txt](rep1.txt), [rep2.txt](rep2.txt), [rep3.txt](rep3.txt).

| check | rep1 | rep2 | rep3 |
|---|---|---|---|
| reader issued through admin tools; exchange | HTTP 200, `ttl 28800s` | same | same |
| reader cannot write | HTTP 401 | 401 | 401 |
| GATE pin first pull, all four collections | entries 30/30; treatments 6/6; devicestatus 6/6; profile 2/2 | same | same |
| GATE emb first pull, all four collections | same counts, after 0.1m | same | same |
| destination `srvModified` on every synced doc (both destinations) | 30/30, 6/6, 6/6, 2/2 | same | same |
| destination v3 `history/<4 days ago>` returns every synced doc (both) | 30/30(sgv), 6/6, 6/6, 2/2 | same | same |
| GATE emb steady: new batch delivered at cadence | after 5.4m | 5.3m | 5.4m |
| pin: rows seeded after 6 min not delivered; process | `exited {"code":0}`; D_pin entries 30/32, treatments 6/8, devicestatus 6/8 | same | same |
| CONTROL the same rows reach emb | after 4.4m | 4.5m | 4.7m |
| revoke via admin tools `PUT /subjects` roles `[]`: issued bearer | HTTP 401 | 401 | 401 |
| CONTROL revoked: emb adds zero rows over 11 min | 32/8/8/2 before and after | same | same |
| restore via `PUT /subjects` roles `[syncreader]`: same running connector delivers the withheld rows | after **25.9m** | **23.5m** | **26.0m** |
| paused: reader GET / exchange | `423 {"error":"TENANT_PAUSED"}` / 200 | same | same |
| paused: uploads stored | entries, treatments, devicestatus 200 | same | same |
| CONTROL paused: emb adds zero rows over 11 min | 33/9/9/2 before and after | same | same |
| unpause: rows uploaded while paused delivered | after **14.2m** | **17.8m** | **18.2m** |
| suspended: GET, exchange, upload | all `423 TENANT_SUSPENDED` | same | same |
| CONTROL suspended: emb adds zero rows over 11 min | 34/10/10/2 before and after | same | same |
| unsuspend (state goes back to `paused`), then unpause: rows stored before suspension delivered | after **18.8m** | **23.2m** | **19.2m** |
| delete subject via admin tools: exchange / issued bearer | 401 / 401 | same | same |
| CONTROL deleted: emb adds zero rows over 7 min | 35/11/11/2 before and after | same | same |
| tenant B untouched and absent from both destinations | B 10 entries, 1 treatment; 0 B rows in destinations | same | same |

What `D_emb` logged on stderr over the whole sequence, identical in all three runs:

```
4 nightscout-connect: Polling frame failed (HTTP 401)
8 nightscout-connect: Polling frame failed (HTTP 423)
4 nightscout-connect: Polling frame failed (HTTP 401)
```

The three groups are revoke, pause plus suspend, and delete. Nothing else was logged about the refusals.

## Controls (each went red for the intended reason)
- **Oracle**: dropping one treatment from the oracle copy goes red (`missing 0, extra 1, expected 5, actual 6`). Altering one devicestatus, one profile or one sgv each goes red (`missing 1, extra 1`). Restoring the oracle goes green.
- **`srvModified` check**: adding one unstamped document to the copy turns it red (`n=7`).
- **Revocation, pause and suspend are not vacuous**: the same running connector, with no restart, later delivers the rows it withheld (rows above).
- **Pin-stop**: the rows the pin did not deliver reach `D_emb` from the same tenant and the same token.
- **Development pass**: one extra pass with 1-minute failure windows (37/37) exercised every code path. Its windows were shorter than one connector cycle, so no polls were refused and it is not counted as evidence.

## Findings
No server defect surfaced. Every tenant-side refusal matched its design: 401 after revoke or delete; 423 `TENANT_PAUSED` with the exchange and uploads admitted; 423 `TENANT_SUSPENDED` for everything; unsuspend returns the tenant to paused.

The findings are about the connector.

1. **Recovery after a refusal takes 14–26 minutes**, not one cycle (reproduced, 3/3). Each refused cycle increments `frames_missing`. The next frame then waits `2.5 min × (2^n − 1)` with equal jitter, on top of the 5-minute cadence (`lib/sources/nightscout.js` backoff `interval_ms: 2.5 min`; `lib/backoff.js`; read-derived mechanism). Users would see a site that stays stale for up to about half an hour after the owner restores access or unpauses.
2. **The operator sees only `Polling frame failed (HTTP 401|423)`** (reproduced, 3/3). The status separates a refused grant from a paused or suspended tenant. Nothing separates paused from suspended, which the tenant's error body carries. The connector retries on backoff indefinitely.
3. **A data 401 or 423 does not trigger a new credential exchange** (read-derived: `lib/machines/fetch.js` routes a `dataFetchService` error to `Error` without `SESSION_EXPIRED`). The suspend phase is consistent with this: the connector kept its bearer and logged no `Authorization failed`. The session is re-established only by `EXPIRE_SESSION_DELAY` (28 800 000 ms in the source driver).
4. **Pin `b394411a`, token-only configuration crashes at start** (reproduced, 3/3). `exited {"code":1}` with `TypeError ... at encode_api_secret (<pin>/lib/sources/nightscout.js:12:10)`. Without `CONNECT_SOURCE_API_SECRET` the pin's `forever` passes `apiSecret: undefined`, which the source hashes unconditionally (pin `lib/sources/nightscout.js:26-27`; read-derived cause). The pin arm therefore ran with a placeholder `CONNECT_SOURCE_API_SECRET`. The placeholder is never sent, because the endpoint token short-circuits `authFromCredentials`. Release 0.1.0 defaults it to `''` in `validate`.
5. **Pin `forever` stops 5 minutes after start and exits 0** (reproduced, 3/3). The cause is `setTimeout(STOP, 60000 * 5)` in pin `commands/forever.js`; 0.1.0 has 24 h. In practice the pin delivered only its first pull. It missed even the batch seeded while it was alive, because its next poll was aligned past the STOP.
6. **Pin `forever` ignores `CONNECT_SOURCE_COLLECTIONS`** (reproduced: configured `entries`, it delivered all four collections). Its `input` carries only `kind`, `url` and `apiSecret`, so the source default applies.
7. **Pin `forever` prints the source token and the destination API secret to stdout** (reproduced: 4 occurrences each before redaction, 3/3). The embedded 0.1.0 printed the source token 0 times.

## UNMEASURED
- **Token TTL expiry and refresh: stopped as briefed.** The tenant exchange lifetime is not configurable:
  - `preview-api.js:74` and `owner-credential-runtime.js:24` pass `maxTokenLifetimeSeconds: 28800`;
  - `lib/secrets/component.js:222` refuses any other value (`SECRETS_EXCHANGE_LIFETIME`).

  A minutes-scale expiry would need a code change or a shifted clock, and neither was done. The read-derived expectation is in finding 3: the bearer expires at `iat + 8 h`, and the connector re-authenticates only when its own 8-hour session delay fires. A poll between those two instants would get a 401 and fall into the backoff in finding 1.
- **Pause and suspend through the owner HTTP routes** (`/api/v1/tenant/activity/*` on the owner listener); the store capabilities were used instead.
- **Profile duplication on repeated polls by the pin.** The pin stopped before a second poll. The embedded 0.1.0 showed no duplicates over about 110 minutes (profile 2/2 throughout).
- **Restoring after a subject is deleted.** A new subject has a new token, so the connector must be reconfigured; that was not run.
- Also not exercised:
  - real DNS, TLS and proxy ingress (aliases were `*.localhost`);
  - the reverse direction (tenant-side connector, `vcpool`);
  - the pin running embedded (cgm-remote-monitor depends on npm 0.1.0, not the pin).
