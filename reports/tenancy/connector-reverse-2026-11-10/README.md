# Tenant-side Nightscout connector (MT-CONNECTOR-REVERSE, M6d), 2026-11-10

*Contributor-facing evidence record for lane R. Captured 2026-11-10. Not edited after capture.
Decisions implemented: [first-preview-no-push-provider](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#first-preview-no-push-provider),
[owner-integrations-none-first-preview](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#owner-integrations-none-first-preview),
[pool-primitive-shared](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#pool-primitive-shared),
[evaluator-static-partition](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#evaluator-static-partition),
[vcpool-egress-capacity](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#vcpool-egress-capacity) and
[activity-is-pause-suspend](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#activity-is-pause-suspend).
Synthetic data only. Credentials were held in process memory and child environments.*

## Anchors

| tree | commit |
|---|---|
| base: pool primitive, branch `codex/pool-primitive-20261110` (on #8898 head `16a1fc2d`) | `5a789903d5696ea70549ce5b57a8c23edc3967e9` |
| lane branch `codex/connector-reverse-20261110`, worktree `externals/work/crm-connector-reverse-20261110` (local, unpushed) | `1792063a28a2a018709a71af5efd65dc1c212c4c` (two commits: `fd882910` and `1792063a`) |
| alignment `main` at capture | `33691fc54d44749293dfe60c5df1324fee67d731` |
| nightscout-connect that ran | npm `0.1.0` from the crm `package-lock.json`. Its `lib/sources/nightscout.js` and `lib/outputs/nightscout.js` are byte-identical to tag `v0.1.0` (`52e1c14f`). |

The diff against the base is 20 files, 1159 insertions and 37 deletions. Queue state at start: `MT-CONNECTOR-REVERSE` was `not-started`.
This record does not change the queue, `decisions.md`, `contents.md` or the register. The queue names the branch
`codex/connector-reverse`; the lane branch carries the date suffix.

## Design

### Write path: HTTP to the api role

The connector writes through the tenant's own API over HTTP to the api role. It does not use an internal service
contract. The decisions point to this path:

- [first-preview-no-push-provider](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#first-preview-no-push-provider)
  says the connector is "writing through the tenant's own API as a tenant-bound subject".
- D23 (`lib/server/serve/roles.js` header) says "On the data path api is the only writer".
- [internal-service-contracts](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#internal-service-contracts)
  covers realtime authority and writes, alarm delivery and lifecycle coordination. It has no data-ingest contract.
- [internal-listener-ory-pattern](../../../releases/cgm-remote-monitor-16.0.0/decisions.md#internal-listener-ory-pattern)
  says serve.internal trusts its network and has no authentication of its own. A write sent there would not carry
  the subject's authority.

The decisions do not conflict on this point, so this lane did not stop to ask.

The connector authenticates with no change to nightscout-connect. Its Nightscout output sends `API-SECRET: sha1(<credential>)`.
The tenant verifier treats the sha1 of a subject's access token as that subject, as a single site does
(`lib/secrets/component.js:110,114`). The credential is the connector subject's token, never the tenant root.

### Elements

| element | where | what |
|---|---|---|
| role | `lib/server/serve/roles.js:83-94` | `vcpool` now has `start` and `multitenant: true`. Its `storage` changed from `'write'` to `'read'`: it reads activity, tenant secrets and the pool table, and commits no data row itself. Tests `serve-roles`, `serve-listeners` and `nightscout-cli` follow the change. |
| boot | `lib/server/serve/vcpool-preview.js:33-39,75` | Pool member of kind `vcpool` first. A slice refused at boot fails the start (`vcpool pool membership refused: <reason>`, exit 78), as the evaluator's does. Then the activity reader (migration check, `capability: 'reader'`), the secrets reader, and the cycle. |
| secrets | `vcpool-preview.js:57-63`, `lib/tenant-connector/config.js:134` | Principal `vcpool`, consumer `tenant-connector`. `authorize` admits only `decrypt`, and only of this tenant's three references: `sourceEndpoint`, `sourceCredential`, `writeCredential`. In the lab the Vault token's policy is decrypt on the tenant data key only. |
| configuration | `lib/tenant-connector/config.js` | `MULTITENANT_VCPOOL_CONFIG` names a JSON file holding only references. It requires `activity` and a `sources.allowHosts` list: the operator allow-list of the 2026-10-27 outbound-endpoint floor, checked on the decrypted endpoint (`config.js:154`). Partition values come from `MULTITENANT_POOL_VCPOOL_*` (`config.js:174`). |
| egress | `config.js:39`, `lib/tenant-connector/frame.js:80,82` | `MULTITENANT_VCPOOL_EGRESS_PROXY` is the member's egress setting. Only source requests use it; tenant API requests never do. With the variable unset, `proxy: false`, so `HTTP_PROXY` is never consulted. Source requests follow no redirects. |
| frame | `frame.js:87-113` | One frame runs the driver's `gap_for` (the tenant's newest rows), then `authFromCredentials` and `sessionFromAuth` (cached until the source TTL, at most 8 h), then `dataFromSesssion`, `transformGlucose`, and finally the output. |
| cycle | `lib/tenant-connector/runtime.js:82-111` | Every `cycleMs`: `member.slice()`. A refusal works no tenant and decrypts nothing. Next, `activity.connectorWorkList(slice tenants)` (`:99`). A skipped tenant has its connector discarded (`:103`), so it gets no source request and keeps no decrypted value. Eligible tenants run one after another, each when due: the driver's glucose alignment capped at `pollIntervalMs`, or `retryMs` after a refusal. |
| refusals | `frame.js:26`, `runtime.js:32-41` | HTTP 401, 403, 423, 429 and 5xx, or no response, count as refusals. They are counted per tenant and per member under `phase:status`, where the phase is `source`, `write` or `setup`. They are logged once per change of key per tenant, with the tenant id and the member ordinal and nothing else. |
| inspection | `lib/server/internal-api/contracts/connector-inspection.json`, `lib/server/serve/internal-listener.js:24,42-46` | Contract `connector-inspection`, operation `inspectConnectors`, path `POST /vcpool/inspect`, on the process's serve.internal (`listener-config.js` ROLES gains `vcpool`). It returns pool mode and eligibility, refusal counts, the proxy flag and, for each tenant, status, code, cycles, rows pulled, refusal counts and the last refusal. The schema refuses any endpoint, URL or credential field. Documented in `docs/internal-service-api.md`. |

### Two deliberate departures

1. **The vcpool owns the schedule.** The connector runs the driver's frame functions, not its xstate machine, so
   the per-cycle slice and activity checks can stop a tenant before any request. As a result the driver's own
   backoff (2.5 min × 2^n) is replaced by a fixed `retryMs` (default 150 000 ms), and session refresh is the
   frame's TTL rule.
2. **`partition=on` is admitted for `vcpool`.** The evaluator refuses it in this build. The vcpool already has the
   per-cycle slice check that the evaluator lacks. The preview default stays off.

### Connector subject grants

Create-only grants do not work on the v1 API. Two reasons:

- The tenant API requires read on the collection for every v1 request, POST included
  (`lib/server/tenant-app/data-access.js:52,57,147`).
- The driver's output reads the newest row of entries, treatments, devicestatus and profile to find its gap, and
  reads devicestatus for its checkpoint list.

The lab subject role is `api:entries:read,create`, `api:treatments:read,create`, `api:devicestatus:read` and
`api:profile:read`. This was measured: with create-only grants, A refuses with `CONNECTOR_GAP_FAILED` and
`write:401` × 6.

## Lab

Harness: `tools/tenancy/connector-reverse/run.cjs` (`CRM_ROOT=<worktree> node run.cjs`, about 40 s). Containers
`postgres:16`, `mongo:7.0` and Vault (pinned by digest), each named `ns-cr-*` with a random suffix and removed at
exit. Afterwards `docker ps -a | grep -c ns-cr` returned `0`. The local mongod on 27017 was not used. Node v22.23.4.

Setup:

- the api role with activity gating;
- two single-site Nightscout sources, one per family, on their own MongoDB databases, each with a `readable`
  reader subject;
- tenants A and B, each with a connector subject;
- operator entry of three tenant secrets per tenant through the secrets component (an operator binding with
  encrypt only);
- one vcpool process with the egress proxy pointing at a counting forward proxy.

The oracles read tenant rows directly from PostgreSQL (`preview_data.entries`, `preview_treatments.treatments`) and
source rows directly from MongoDB. They compare multisets of `(type, sgv, date)` for entries and
`(eventType, notes, created_at)` for treatments.

### Results (reproduced; last run at `1792063a`: exit 0, `SUMMARY 24 checks, 0 failing`)

| gate | output |
|---|---|
| A holds exactly source A | `{"ok":true,"missing":0,"extra":0,"duplicates":0,"expected":30,"actual":30}` |
| B holds exactly source B | `expected 13, actual 13`, ok |
| B untouched by A (no source-A row in B, no source-B row in A) | `A 30 B 13` |
| flag off: one standalone member owns every tenant | `{"mode":"standalone","eligible":true,"tenants":[["polling",1],["polling",1]],"poolRows":0}` |
| egress through the member proxy only | proxy saw 3 requests to each source and none to the tenant API |
| incremental pull (5 entries, 2 treatments) | `expected 37, actual 37` |
| paused: the pull continues | `expected 41, actual 41`. The api answered a read for paused A with HTTP 423. |
| suspended: no source request for A, no row | `source-A requests during suspension 0; A rows 41 -> 41; status skipped TENANT_SUSPENDED` |
| B keeps pulling while A is suspended | `expected 15, actual 15` |
| unsuspend: no gap, no duplicate | `{"ok":true,"missing":0,"extra":0,"duplicates":0,"expected":46,"actual":46}` |
| revoked source credential (reader subject deleted on the source) | `A rows 46 -> 46; source holds 49` |
| refusal visible in the inspection read and the log | A: `status refused`, `CONNECTOR_SOURCE_FETCH_FAILED`, `lastRefusal {phase:source, status:401}`, `refusals [source:401 ×1]`. Member: `[source:401 ×1]`. B: none. Log: `vcpool tenant 1111…: upstream refusal source:401 (member ordinal 0)`. |
| rotated credential entered (new record `connector-source-credential-2`, config reference, restart) | `expected 49, actual 49, duplicates 0` |
| partitioned member (1 of 1), plus an evaluator-kind row with count 2 | `mode partitioned, eligible true, live [0]`, both tenants polling, `expected 54, actual 54` |
| second process with the same ordinal | `exit 78`, `nightscout multitenant: vcpool pool membership refused: POOL_DUPLICATE_ORDINAL` |
| first member after the duplicate exits | `eligible true, rows 1`. No alert was raised in the first member: the duplicate registered, refused and removed its row between two of the first member's cycles. |
| final | A `56/56`, B `15/15`, duplicates 0 |

Other checks, run on the uncommitted tree that became `fd882910` (the second commit changes only `frame.js:26`, and
`tests/tenant-connector.test.js` was rerun after it: 11 passing):

| check | result |
|---|---|
| `tests/tenant-connector.test.js` (configuration, one frame against loopback source/API/proxy stand-ins, cycle gating) | 11 passing |
| `npm run test:unit` | 3201 passing, exit 0 (base record: 3189) |
| `npm run test:tiers` | `629 test files, 8 tiers: ok` |
| `npm run test:write-boundary` | all 9 adapter entry points checked |
| integration on a dedicated `postgres:16` (16.15, `ns-cr-it-pg`, removed): `pool-membership`, `tenant-activity` (`NS_EVALUATOR_CONSUMERS_TEST=1`), `multitenant-preview-process` (`NS_MULTITENANT_PREVIEW_PROCESS_DOCKER_TEST=1`) | 31 passing (8 + 7 + 16), exit 0 |
| eslint on the 17 changed JS files | 0 errors, 15 warnings, all `security/detect-non-literal-*`. Two are in `config.js` (file load); the rest are in existing test files. |

## Break-it controls

Each break was applied to the worktree, run, and then restored. `sha256sum -c` against copies taken before the
first control printed `OK` for all three `lib/tenant-connector` files.

| control | break | result |
|---|---|---|
| oracle (in-harness) | drop one tenant row from the comparison copy; alter one sgv | **red**: `missing 1, actual 29`; `missing 1, extra 1`. Restored: green `30/30`. |
| suspend check removed | `runtime.js:99`: `connectorWorkList(mine)` replaced by `{ eligible: mine, skipped: [] }` | **red**, 1 gate: `source-A requests during suspension 2; A rows 41 -> 41; status refused CONNECTOR_GAP_FAILED`. The api's ingest refusal still kept rows out, but the source was contacted. The unit suite also went red, 2 tests (`polls an active and a paused tenant and never a suspended one`; `refuses an unprovisioned … activity state`). |
| write identity given grants on B | A's connector routed to B's host, where B grants the same subject id the connector role | **refused, as intended**: A `write:401 ×12`, `CONNECTOR_GAP_FAILED`, B rows `15 -> 15`. A's credential presented to B directly: HTTP 401. The refusal comes from the per-tenant credential derivation: the token is derived from A's root, so it matches no subject on B. RLS was probed separately. The serving identity scoped to A, inserting a B entries row, was refused by the tenant-binding trigger: `42501 TENANT_ORDINAL_BINDING_REQUIRED`. The vcpool secrets identity scoped to A saw `0 of 4` of B's records, and inserting one gave `42501 new row violates row-level security policy for table "secret_records"`. Restored: A `51/51`, B unchanged. |
| pool kind key | `config.js:174`: `fromEnvironment('vcpool', …)` changed to `'evaluator'` | **red**, 3 gates: partitioned gate `mode standalone, live null`; the duplicate was not refused (`exit null`, it ran); the vcpool row count was 0. Unit: 1 failing. |
| egress proxy (extra) | `frame.js` transport forced to `proxy: false` | **red**, 2 gates: the proxy saw `{}`; the B-during-suspension gate also failed, because it counts B's requests at the proxy. Unit: 1 failing (`sends every source request … through the member egress proxy`). |

## Findings and points for the maintainer

1. **Decision needed: pause versus a connector built during the pause.** While a tenant is paused, the api refuses
   reads with HTTP 423 (`lib/tenant-activity/serving.js:14-19` classifies every GET except the token exchange as a
   read). The driver's output reads the tenant to find its gap. A connector that existed before the pause keeps
   pulling, because its gap is cached in memory, and that is the case the gate measured. A connector built during
   the pause cannot pull: after a vcpool restart, a refusal, or a slice or activity change, it gets no gap.
   Measured: after a restart while A was paused, A stayed at `55` rows with source at `56`, `CONNECTOR_GAP_FAILED`,
   `write:423 ×30`. After unpause, `56/56` with no duplicate. No data is lost, but the pull waits for unpause.
   Options:
   - (a) Accept this for the first preview. The behaviour is now visible as `write:423`.
   - (b) Let the api's paused gate admit the reads an uploader needs. This touches the activity decision, and
     Loop or AAPS reads during a pause raise the same question.
   - (c) Give the vcpool a durable per-tenant bookmark. That is a new storage path.

   Recommendation: (a) for the preview, because nothing is lost and the state is visible. Take up (b) with the
   uploader read question, which is single- and multitenant alike. Unmeasured: whether uploaders other than the
   connector read during a pause.
2. **Grants.** As described under Connector subject grants, a create-only subject cannot write through v1. This
   lane provisioned read and create. Owners cannot configure this subject in the first preview: it is
   operator-provisioned.
3. **`roles.js` change.** `vcpool.storage` changed from `'write'` to `'read'`, and `describeComposition` now lists
   it among the readers.
4. **`partition=on` admitted for vcpool, unlike the evaluator.** See departure 2.
5. **Operator procedures that do not exist yet.**
   - There is no operator command to enter a tenant secret. The lab used the secrets component's `encrypt` with an
     operator binding.
   - Rotation needs a new reference id (the store is insert-only), a configuration edit and a restart. The
     configuration is read once at boot.
   - The tenant host for the Host header is configuration (`tenants[].host`); only direct-alias resolution was
     exercised.

## UNMEASURED

- HTTPS sources, and HTTPS through the proxy (axios `proxy` with an https target). Only HTTP over loopback ran.
- The `api-secret` source credential kind: the driver may create a `nightscout-connect-reader` subject on the
  source. Only the token kind ran.
- The devicestatus and profiles collections, and the 5-minute cadence over a long run. Lab timing was
  `cycleMs 500`, `pollIntervalMs 1500`, `retryMs 1500`.
- Upstream quotas and real 429 or 5xx from a source. 429 is covered by the unit stand-in only.
- More than one partitioned member splitting tenants across processes. Only 1-of-1 and a duplicate ran.
- The Vault Agent `tokenFile` credential source, canonical-internal resolution, real DNS, TLS and ingress.
- The lock pin `b394411a` itself. It differs from `v0.1.0` in the driver files (4 files, 341+/53-); `v0.1.0`
  is what ran.
- The full suite, the browser and dom tiers, and `prcheck`. These belong to the coordinator's frozen-head
  acceptance.
- Single run of the final sequence after two earlier green runs. Run-to-run variance was not measured.
