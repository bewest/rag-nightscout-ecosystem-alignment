# MT-CONNECTOR-SYNC (M6d): nightscout-connect pulls from a multitenant tenant (DRAFT evidence record)

Lane measurement, 2026-11-10. Synthetic data only; credentials live in process memory and child environments.

## Anchors (from git)
- cgm-remote-monitor `dc795bd1515f11808a8d0732f2be9925cb2ffcd1` (branch `codex/connector-sync-20261110`, worktree `externals/work/crm-connector-sync-20261110`, draft PR #8898 head), `npm ci` run in the worktree.
- nightscout-connect checkout `04102f9d260f0d21f6b6ff66d4afe27680bef37c` (`v0.1.0-1-g04102f9`, clean, used read-only). `workspace.lock.json` pins `b394411a39236b614beebffabf23ccc04f730a68`; the pin is an ancestor of the checkout (merge-base check exit 0), so the checkout is newer than the pin.
- alignment `main` `325978710` (harness untracked).
- Node v22.23.4; containers `postgres:16`, `mongo:7.0`, Vault image pinned by digest in the harness; all named `ns-cs-*`, removed at exit (`docker ps -a | grep ns-cs` empty afterwards).

## Connector mode (file:line)
`externals/nightscout-connect/lib/sources/nightscout.js`: `CONNECT_SOURCE=nightscout` (`bin/nightscout-connect forever --source nightscout`). `authFromCredentials` returns `params.token` when the source endpoint URL carries `?token=` (line ~184), and `sessionFromAuth` exchanges it at `/api/v2/authorization/request/<token>` and sends `Authorization: Bearer` on `/api/v1/entries.json` (`dataFromSesssion`). No connector change was needed; the API secret is not used in this path.

## Harness
`tools/tenancy/connector-sync/run.cjs` (untracked):
```bash
CRM_ROOT=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/work/crm-connector-sync-20261110 \
CONNECT_ROOT=/home/bewest/src/rag-nightscout-ecosystem-alignment/externals/nightscout-connect \
node tools/tenancy/connector-sync/run.cjs
```
It provisions PG16 plus Vault (two tenants, entries/legacy/context domains, same preparation as `tests/multitenant-preview-process.integration.test.js`), starts `nightscout multitenant api` (direct-alias hosts `ns-cs-a.localhost`, `ns-cs-b.localhost`), a destination single-site `nightscout single` on its own Mongo, and per pull a fresh `nightscout-connect forever` child with `CONNECT_SOURCE_ENDPOINT=http://ns-cs-a.localhost:<port>/?token=<reader legacy credential>`, `CONNECT_SOURCE_COLLECTIONS=entries`. The reader subject has only `api:entries:read`; a separate writer subject seeds synthetic sgv entries (30, then 5, then 3 more) through the tenant's v1 API.

Oracle (independent of the connector): tenant rows read directly from PostgreSQL `preview_data.entries` (operator connection), destination rows read directly from MongoDB `ns_dest.entries`; compared as a multiset of (type, sgv, date).

## Results (full output `run.log`, last run: exit 0, `SUMMARY 16 checks, 0 failing`)
| check | output |
|---|---|
| GATE pull 1 | `{"ok":true,"missing":0,"extra":0,"expected":30,"actual":30}` |
| break-it: drop one tenant entry from oracle copy | red: `{"ok":false,"missing":0,"extra":1,"expected":29,"actual":30}` |
| break-it: alter one sgv | red: `{"ok":false,"missing":1,"extra":1,"expected":30,"actual":30}` |
| oracle restored | green: `{"ok":true,"missing":0,"extra":0,"expected":30,"actual":30}` |
| GATE pull 2 (5 new entries) | `{"ok":true,"missing":0,"extra":0,"expected":35,"actual":35}` |
| CONTROL revoke (delete reader credential record): exchange | HTTP 401, no token |
| CONTROL pull after revoke | destination `before 35 after 35`; connector log `Authorization failed (HTTP 401)`, `Polling frame failed`; tenant held 38 |
| CONTROL role removed, bearer already issued | HTTP 401 on `/api/v1/entries.json` (grants are read per request); pull adds zero rows (35) |
| restore grant | pull delivers the 3 pending entries: `{"ok":true,"missing":0,"extra":0,"expected":38,"actual":38}` |
| second tenant untouched | B rows 10 before and after; destination rows carrying B's device marker: 0 |
| reader write attempt | HTTP 401 (read-only role) |

The oracle's red controls are red for the intended reason (a missing/changed row, counts shown). The refusal controls are non-vacuous: the same reader, once restored, delivers the withheld rows.

## Findings
No connector or server defect surfaced in this path. Two observations: the revoked pull is visible to the operator only as connector log lines (`Authorization failed (HTTP 401)`); the connector retries on its normal backoff rather than stopping.

## UNMEASURED
- Treatments, devicestatus, profiles (`CONNECT_SOURCE_COLLECTIONS` limited to entries) and the history/`srvModified` view of the destination.
- The checkout `04102f9d` is newer than the lock pin `b394411a` (ancestor); the pinned commit itself was not run.
- Long-running polling loop and 5-minute cadence (each pull is a fresh process ended after the destination settled); token TTL expiry/refresh.
- Reverse direction (tenant-side connector, `vcpool`): not built; not part of this lane.
- Tenant aliases resolved through `*.localhost`; real DNS/TLS/proxy ingress not exercised.
- Revocation here removes the credential record or role in PostgreSQL directly; the owner-surface revocation path was not used.
- Single run of the full sequence (plus an earlier green run before the B-marker strengthening); no repeated-run variance.
