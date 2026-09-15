# Backfix register — defects that ship to existing operators, independent of multitenancy

**Living document.** Started 2026-09-14. Maintained alongside the
[multitenancy execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md).

This exists because the multitenancy programme keeps finding bugs in **today's** Nightscout,
and those findings must not become hostage to a large architectural change. Every entry here
is a defect that

- affects **single-tenant self-hosters running the current release**, and
- is fixable **without any tenancy decision**, and
- should therefore be landable on its own, on `dev` or on
  `chore/nightscout-modernization`, ahead of the seam.

> **D4 makes this permanent, not temporary.** MongoDB and single-tenant are first-class
> forever, so "we will fix it when the Postgres backend lands" is never an answer for anything
> in this table.

> **Renumbering, 2026-09-15.** Two ids were allocated twice by concurrent sessions. The
> **write-path trio keeps BF-21/22/23** because a research document references them as a set; the
> two later arrivals were renumbered. So in commits dated 2026-09-15 or earlier: "BF-21" in
> `c27f91a4` means **BF-30** (the auth-failure delay), and "BF-22" in `c05e6dac` means **BF-31**
> (the Google Home language leak). **Allocate a new id by reading the highest in this table at the
> moment you write it**, never the one your brief quoted.

**Status values**: `open` · `fixed <date>` (repaired on a backfix branch with tests and a
release note, not yet merged — the row names the branch and commit) · `fixed-in-seam`
(repaired inside the seam branch as a side effect, needs extraction to land independently) ·
`landed` · `wontfix` · `invalid` (investigated and does not reproduce; the row is struck
through and the detail section says why, because a wrong entry that is merely deleted gets
raised again).

---

## 1. Register

| id | defect | where | severity | tenancy-independent | status |
|---|---|---|---|---|---|
| **BF-01** | `GET /api/v1/count/entries/where` silently matches nothing | `lib/server/aggregate.js:21` | **high** — wrong answer, HTTP 200 | yes | open |
| **BF-02** | `insulin`/`carbs` query bounds truncated by `parseInt` | `lib/server/treatments.js:259-266` | **high** — wrong answer, HTTP 200 | yes | **fixed 2026-09-15** (T0.5, `bf/coercion` `88d1f8a4`) |
| **BF-03** | Numeric filters on `devicestatus`, `activity`, `food`, `profile` match nothing | `lib/server/query.js` walker, per-collection | **high** — wrong answer, HTTP 200 | yes | **fixed 2026-09-15 for `devicestatus` + `profile`** (T0.5, `bf/coercion` `88d1f8a4`); `food` and `activity` misfiled, see detail |
| **BF-11** | `treatments.duration` and `rate` have no walker entry — temp-basal filters match nothing | `lib/server/treatments.js:259-266` | **high** — wrong answer, HTTP 200 | yes | **fixed 2026-09-15** (T0.5, `bf/coercion` `88d1f8a4`) |
| **BF-12** | ~~`entries.rawbg` is coerced but is not in the model~~ — **does not reproduce**; the walker entry is `rssi`, which *is* in the model | `lib/server/entries.js:186` | none — not a defect | n/a | **closed 2026-09-15, invalid** |
| **BF-13** | API v3 `skip`/`limit` paging silently loses and duplicates documents when the whole sort chain ties | `lib/api3/generic/search/input.js` `parseSort` | **high** — silent data loss on a read | yes | open |
| **BF-14** | API v1 `?count=0` (and `-3`, `1e2`) reaches the driver unvalidated — `.limit(0)` means *unbounded* | `lib/server/entries.js:56` + 4 siblings | **high** — on PostgreSQL an empty `200` on a glucose read; unbounded read on MongoDB | yes | open |
| **BF-15** | API v3 `?fields=<dotted.path>` returns an empty document with HTTP 200 | `lib/api3/shared/fieldsProjector.js` `applyProjection` | **medium** — silently empty response to a valid request | yes | open |
| **BF-16** | Food quick-pick `hidden` filter compares to the **string** `'false'`; the field has no declared type and its stored type depends on the request's content type | `lib/server/food.js` `listquickpicks` + `lib/food/food.js:69` `restoreBoolValue` | **medium** — a JSON writer's quick picks silently vanish from the quick-pick list; no shipping client triggers it today | yes | open |
| **BF-17** | Editing a subject through the stock admin UI **persists the API access token in plaintext**, into a field the server otherwise only derives | `lib/authorization/endpoints.js:38-42` + `lib/admin_plugins/subjects.js:43` + `lib/authorization/storage.js` `save` | **high** — turns read access to the database into API access; no key required | yes | open |
| **BF-28** | `insulinage`'s URGENT branch is unreachable — it compares against `insulinInfo.urgent`, which is never assigned, where all three sibling plugins use `prefs.urgent`. "Insulin reservoir change overdue!" can never fire | `lib/plugins/insulinage.js:92` | **medium** — a site-change reminder that silently never arrives | yes | open |
| **BF-29** | An unknown name in `ENABLE` is **silently ignored** — matching is against `plugin.name` (`bwp`, `cage`, `iage`, `sage`, `bage`), not the file name. An operator who writes `ENABLE=cannulaage` gets no plugin and no warning | `lib/plugins/index.js:140` | **medium** — an operator believes an alarm plugin is on when it is off | yes | open |
| **BF-30** | The auth-failure delay is keyed on a client-controlled value under the **default** configuration, so brute-force throttling never accumulates | `lib/authorization/delaylist.js` + `TRUST_PROXY` default in `lib/server/env.js:43` | **high** — restores unthrottled guessing against `API_SECRET` and tokens | yes | open |
| **BF-31** | A Google Home request changes the display language **for the whole process**, alarm level names included, until something changes it back | `lib/api/googlehome/index.js:27` + the one `language` instance at `lib/server/server.js:34` | **medium** — gated on the Google Home plugin being enabled; reaches alarm text | yes | open |
| **BF-32** | Query coercion was applied to operands that are not field values, so `find[sgv][$exists]=true` became `{$exists: NaN}` — falsy, returning exactly the documents that lack the field | `lib/server/query.js` `walk_prop` | **medium** — inverted answer, HTTP 200; reachable on the 10 fields that had a walker entry | yes | **fixed 2026-09-15** (found during T0.5, `bf/coercion` `88d1f8a4`) |
| **BF-04** | API v1 has no operator allowlist — filter pass-through reaches the driver | `lib/server/query.js:157` | **high** — ReDoS / full-scan exposure | yes | fixed-in-seam |
| **BF-05** | Unguarded `console.log` of every count query on the request path | `lib/server/aggregate.js:30-31` | **medium** — log noise, filter contents to stdout | yes | open |
| **BF-06** | `/api/v1/entries?count=10` costs 42× a typed read | `lib/server/cache.js:73-76` | medium — CPU | yes | open |
| **BF-07** | `cache.insertData` JSON round-trips the whole retained array | `lib/server/cache.js:81` | medium — 65 % of the load cycle | yes | open |
| **BF-08** | `nightscout-connect` actors have no start or interval jitter | `nightscout-connect`, `run()` | medium — thundering herd on restart | yes | open |
| **BF-09** | Socket dedup uses truthiness, so a `0` insulin/carbs value is skipped as a match key | `lib/server/websocket.js:535-568` | **unsettled** — may be intentional | yes | open |
| **BF-10** | `mongod` fatal-asserts at Docker's default `nofile=1024` | operational, not code | medium — self-hosters in containers | yes | open |

## 1b. Pre-release findings

Entries here **fail the register's first criterion** — they do not affect anyone running the
current release. They are recorded separately rather than by widening that criterion, because the
criterion is what makes the rest of the table mean something.

| id | defect | where | severity | status |
|---|---|---|---|---|
| **BF-21** | `bulkUpsert` on PostgreSQL takes no options argument, so the `{mode:'replace'}` every shipping caller sends is silently ignored and the write merges | `lib/api3/storage/pgCollection/index.js` `bulkUpsert` | **high** — a deleted field survives for good; the two backends drift apart with every write | open |
| **BF-22** | `updateOne` with a dotted field stores a nested object on MongoDB and a literal dotted key on PostgreSQL | `lib/api3/storage/pgCollection/index.js` + `lib/api3/generic/patch/operation.js:85` | **medium** — client-reachable via v3 `PATCH`; the PostgreSQL key is unreachable by any path lookup | open |
| **BF-23** | A duplicate-key error reaches the caller as the backend's own error class | both adapters | low — no shipping caller branches on it | open |
| **BF-25** | A credential carried in the request **body** is invisible to the tenant claim check, so tenant A's token authorises A's roles against tenant B's bound data | `lib/server/tenant-middleware.js` `presentedCredential` + `lib/authorization/index.js:40-50` | **high** — cross-tenant read *and write* with any client on default config | open |
| **BF-24** | `TRUST_PROXY=false` bypasses the guard that refuses a non-`host` `TENANT_HOST_HEADER`, letting a client choose its tenant with a header | `lib/server/env.js` `fromEnv` trust-marker check | **high** — gated on one operator config pairing, which is the pairing the guard exists to catch | open |
| **BF-26** | The HTTPS redirect rebuilds the URL from the already-rewritten `req.url`, dropping the tenant path prefix | `lib/server/app.js:132` | low–medium — availability; on by default in path mode | open |
| **BF-27** | `config()` returns one module-scope `env` object, and `setAPISecret()` deletes `API_SECRET` from `process.env` once read — so a second `config()` hands back an enclave that was never armed, and (before the rebind) disarmed the first caller's | `lib/server/env.js` module scope + `setAPISecret` | low — **not reachable in production**: one call site, `lib/server/server.js:33`. 62 test files call it | open |
| **BF-18** | Driver 7 doubles the getMore batch size when `.limit(0)` is set, abandoning `READ_OPTIONS` | `lib/storage/mongo-read-options.js` + driver 7.6.0 | medium — pre-release; compounds BF-14 | open |
| **BF-19** | `ORDER BY` reads the generated column, which orders differently from the document — breaking the DDL's own stated invariant | `lib/api3/storage/pgCollection/sql.js` `orderBy` | **high** — silently wrong order, and client-reachable via v3 `?sort=` | open |
| **BF-20** | `scalarize()` converts a `Date` bound to an ISO string, so a `Date`-valued filter matches nothing on MongoDB and everything on PostgreSQL | `lib/api3/storage/pgCollection/utils.js` | low — no shipping caller passes a `Date` | open |

### BF-18 · the read bound is abandoned on `.limit(0)`

`mongo-read-options.js` = `Object.freeze({batchSize: 1000})` exists because **driver 7 stopped
sending a default `batchSize`** — measured and confirmed: drivers 5 and 6 send `batchSize=1000`
unprompted, driver 7 sends none and lets the server fill to the 16 MB wire limit. The constant is
load-bearing, not cargo.

It stops holding when `.limit(0)` is also set. Requested `getMore` batch sizes, same constant:

```
v5.9.2    1000 x40                          holds
v6.21.0   1000 x40                          holds
v7.6.0    1000 2000 4000 8000 16000 32000   ABANDONED
```

**The `.limit(0)` path is BF-14's path and only BF-14's path.** `findFiltered` calls `.limit()`
only when a caller supplied one, and v1 supplies `opts.count ? parseInt(opts.count) : undefined`
— so `.limit(0)` is reached by `?count=0` and by any unparseable `?count=` (`NaN` →
`toSafeInt(NaN, 0)`). An absent `?count=` never calls `.limit()` and the bound holds. So the two
defects compound on the same request: `?count=0` removes the document limit *and* dismantles the
memory bound that would have made the resulting read survivable.

*Not shipped*: `origin/dev` has `mongodb ^5.9.2` and no `mongo-read-options.js`. Both arrive on
`chore/nightscout-modernization` (`b8fd24c6`). Caught before release.

*Fix*: none needed here. Fixing **BF-14** makes `.limit(0)` unreachable through the API and closes
this as a side effect. Recorded anyway because `findFiltered` is a published interface — a future
caller passing `limit: 0` re-opens it, and `toSafeInt(o.limit, 0)` makes `0` the fallback for
unparseable input. A defensive `if (limit > 0)` in `findFiltered` would also do it.

*Evidence*: [readOptions across the seam](../60-research/seam-readoptions-2026-09-15.md) §2,
`tools/qc/readoptions-arm.js`, three driver versions against a real mongod.

*Unexplained*: the doubling is measured on the wire, not traced to a line in the driver. That
establishes when it changed, not why.

### BF-19 · the index accelerator changes an answer in `ORDER BY`

The emitted DDL states its own invariant in capitals:

> **THE COLUMNS BELOW ARE AN INDEX ACCELERATOR. THE DOCUMENT IS THE RECORD.**
> Dropping every generated column must not change an answer.

`lib/storage/filter.js` holds that invariant on the `WHERE` side deliberately and demonstrably —
`$exists` always reads `doc #> '{path}'` because a column built from `->>` cannot tell an absent
key from an explicit null, and the randomised differential agrees 3000/3000.

`orderBy()` chooses between **the same two branches** and they do not order the same values the
same way. Identical values in two fields of the same documents, one with a generated column
(`sgv`) and one without (`noise`):

```
postgres sort sgv   (COLUMN)  005 004 003 002 006 001
postgres sort noise (jsonb)   005 004 002 006 001 003
mongod   both fields          004 005 006 001 002 003
```

Three orders where there should be one. The cause is that the typed column is SQL `NULL` for an
absent key, for an explicit null **and for every value of the wrong type**, collapsing three
distinct things into one bucket that then sorts together.

**Client-reachable**: v3's `parseSort` puts the client's unvalidated `?sort=<field>` first in the
chain, so `sql.js`'s own justification — *"every sort this code path issues is on a field that is
one type in practice"* — describes today's callers, not today's reachable requests.

*Corroborated independently.* [`tools/qc/typeguard-arm.js`](../../tools/qc/typeguard-arm.js)
reached the same defect from the other direction, comparing one field across both branches and
mongod: on single-typed data the shipped translation matches mongod **exactly**, the only one of
five strategies that does; on mixed-typed data a string `sgv` sorts *first* where MongoDB sorts it
last. Two harnesses, two fixtures, one defect.

*Sizing holds the grade down, and it is a deadline rather than a reprieve*: the emitted manifest
flags no ambiguous field on `entries`, the only collection T2.5 implements. `NSCLIENT_ID` is
flagged on `devicestatus`, `profile` and `treatments` — so the exposure arrives **with T2.6**.

*Fix*: see [the ordering design](nightscout-seam-ordering-translation.md) §3. Restricting sortable
fields to declared single-typed ones makes the adapter's existing assumption checkable; the
alternative is a type-bucketed sort key, which is real work and still does not handle arrays.

*Evidence*: [T2.5 backend verification](../60-research/t25-postgres-backend-verification-2026-09-15.md) §6,
`tools/qc/pg-backend-arm.js`; and [ordering design](nightscout-seam-ordering-translation.md) §3.1b.

### BF-20 · a `Date`-valued filter bound silently inverts

`scalarize()` converts a JavaScript `Date` to an ISO string before it reaches the adapter. A
`gte <Date>` bound against an ISO-string `created_at` therefore matches **nothing on MongoDB**
(BSON compares only within a type, and Date is not String) and **everything in range on
PostgreSQL** (where both sides are now text). This is divergence class B moved into the value
adapter, where `typedRef()`'s type-bracketing `CASE` cannot see it.

*Not reachable today*: every shipping caller of `findFiltered`, `count` and `deleteMany` was
checked — `lib/server/query.js` emits epoch numbers or ISO strings, never a `Date`. Recorded
because the adapter is a published interface and the next caller may not.

### BF-21 · `bulkUpsert` ignores the mode every caller asks for

`mongoCollection/modify.js` `bulkUpsert(col, ops, options)` takes an options bag whose `mode`
defaults to `'replace'`. `pgCollection/index.js` `bulkUpsert(ops)` **takes no options parameter at
all** and always writes in merge mode.

Measured on one stored document carrying `stale: 'was-here'`, upserted with a document that does
not carry it:

```
bulkUpsert(ops)                      mongod: stale removed   postgres: stale SURVIVES
bulkUpsert(ops, {mode:'merge'})      mongod: stale survives  postgres: stale survives   agree
bulkUpsert(ops, {mode:'replace'})    mongod: stale removed   postgres: stale SURVIVES
```

**Every shipping caller passes `{ mode: 'replace' }` explicitly** — `lib/server/activity.js:61`
and `:102`, `lib/server/treatments.js:31`. They ask for a replace in writing and the argument
reaches nothing.

The consequence is an **unremovable field**: any key a client deletes from a treatment or activity
document stays in the PostgreSQL row for good. Nothing errors, nothing logs, and the two backends
drift further apart with every write.

*Not yet live, and the deadline is known*: `entries` is the only collection with a PostgreSQL
schema and it has no `bulkUpsert` caller. `activity` and `treatments` do, so **the exposure
arrives with T2.6** — the same deadline as BF-19.

*Fix*: give the PostgreSQL `bulkUpsert` the same `(ops, options)` signature and implement
`'replace'`, or make it refuse a mode it cannot honour. Silently downgrading a replace to a merge
is the one option that should not survive review.

*Evidence*: [the write path across the seam](../60-research/seam-write-path-2026-09-15.md) §2,
`tools/qc/write-arm.js`, 23 agree / 4 differ / 0 vacuous.

### BF-22 · a dotted field in `updateOne` stores two different documents

`updateOne(identifier, setFields)` becomes `$set` on MongoDB, where a dot is a **path**. The
PostgreSQL merge treats the same string as a **literal key**:

```
setFields = { 'nested.leaf': 7 }
  mongod     …,"nested":{"leaf":7},…
  postgres   …,"nested.leaf":7,…
```

The PostgreSQL document then holds a key no path lookup will find — not `doc #> '{nested,leaf}'`,
not a generated column, not a client walking the object.

*Reachability*: `lib/api3/generic/patch/operation.js:85` passes the client's PATCH body to
`updateOne`, so this is reachable through `PATCH /api/v3/<collection>/<identifier>` **subject to a
validation layer that was not audited** — which bounds the claim and should be checked before this
is graded any higher. `lib/api3/generic/delete/operation.js:86` passes a fixed
`{isValid, srvModified}` and is safe.

MongoDB's behaviour is not obviously correct either; a client sending `{"nested.leaf": 7}` may
have meant a literal key. The defect is that the backends answer differently and neither refuses.

### BF-23 · the duplicate-key error class crosses the seam

```
mongod     MongoServerError: E11000 duplicate key error collection: …
postgres   DatabaseError: duplicate key value violates unique constraint "entries_pkey"
```

Both refuse the duplicate, which is what matters. But an error class is a driver object, and the
seam exists so that driver objects do not reach callers. `err.code === 11000` is the standard
MongoDB idiom for "already exists" and would silently stop being true.

*Low on evidence*: `grep` for `11000`, `E11000` and `MongoServerError` across `lib/` finds no
caller branching on it. Recorded because the interface is published.

### BF-25 · a body-borne credential is invisible to the tenant claim check

`presentedCredential` decides whether a request carries a credential at all. It reads the
`Authorization` header, `?token=`, `?secret=` and the `api-secret` header — and **not**
`req.body`. Its own comment explains why, and the explanation is the defect:

> `req.body` is deliberately not consulted. This middleware mounts above the body parsers, so a
> token in a body is not visible yet … an opaque credential is exactly the case the
> `requireTokenClaim` default refuses.

It is not refused. `present = false` classifies the request as **anonymous**, and an anonymous
request is passed through. Later, `lib/authorization/index.js:40-50` reads `req.body.token` and
`req.body[0].token` (and the `secret` equivalents) and resolves them against the **process-wide**
`storage.subjects`. `lib/api/entries/index.js:43` mounts a body parser on exactly that route.

Measured on one middleware instance, victim host `bar`:

```
tenant foo's JWT as ?token=          -> 403
the IDENTICAL JWT in the JSON body   -> 200, bound to tenant bar, token intact
```

Same for an opaque access token, `{secret:…}` and `[{secret:…}]`. So tenant A's credential
authorises A's roles against **tenant B's** data — read and write.

*Verified independently at both halves before publishing*: `presentedCredential` does not read the
body, and `lib/authorization/index.js` does.

*Tempering, and it is real*: `fromEnv` already warns at boot that `TENANCY_MODE=multi` is not safe
to serve two people from until T3.3–T3.5 land. This is a pre-release defect on an unfinished mode,
not something shipping to self-hosters.

*The most dangerous part is the comment*, because it tells the next reader this case is already
handled. Fix the sentence even if the code takes longer.

*Regression test to write when fixing*: start the real authorization stack with two tenants'
subjects and assert A's token cannot read B's entries. The agent established the two halves
separately — middleware pass-through measured live, process-wide subject resolution read from
source — and that end-to-end test is the gap.

*Evidence*: [tenant resolution, adversarial](../60-research/tenant-resolution-adversarial-2026-09-15.md) C1.

### BF-24 · `TRUST_PROXY=false` defeats the forwarded-host guard

> **Priority raised 2026-09-15.** BF-24 now **gates a deliverable**, not just a misconfiguration.
> Path-prefix multitenancy over websockets is only achievable by having the reverse proxy assert
> the tenant in a header derived from its own location block (T3.5 in the execution plan) — which
> is precisely the mechanism this defect makes bypassable. The maintainer's decision is to **land
> BF-24 before publishing the nginx recipe**, rather than ship a documented configuration that is
> known to be defeatable.

`fromEnv` refuses a `TENANT_HOST_HEADER` other than `host` with
`if (trust.legacyForwardedHeaders) throw`. That marker is only set on the **compatibility** trust
function — `TRUST_PROXY` unset or empty. `compileTrust('false')` returns a bare `() => false` with
no marker, so the guard never fires:

```
TRUST_PROXY=false  TENANT_HOST_HEADER=x-forwarded-host
Host: foo…   X-Forwarded-Host: bar…    ->  200, bound to bar
```

The client picks its tenant with a header, on another tenant's hostname. The pairing is
contradictory — trust nothing, then read a forwarded header — which is precisely what the guard
exists to catch.

*Evidence*: same report, H3.

### BF-26 · the HTTPS redirect drops the tenant path prefix

`lib/server/app.js:132` builds `https://${host}${req.url}` and is mounted **below** the tenant
middleware, which has already stripped the prefix from `req.url`:

```
GET /foo/api/v1/entries?count=10
  -> Location: https://apex.org/api/v1/entries?count=10   (slug `api` -> 404)
```

`INSECURE_USE_HTTP` defaults false, so in path mode this is on by default. Availability rather
than isolation. *Fix*: use `req.tenantPathPrefix` or `req.originalUrl`.

*Evidence*: same report, M2.

## 1c. Missing capabilities

Not defects — **absent features** with a bounded, measured scope that ship to every operator and
are landable independently. Kept separate so §1's criterion ("a defect in the current release")
keeps meaning something.

| id | capability | where | scope | status |
|---|---|---|---|---|
| **CAP-01** | **Base-URL / sub-path mounting.** Nightscout cannot be served from a sub-path — `apex.org/nightscout/` behind an `nginx` `proxy_pass` — because nothing in the tree resolves URLs relative to a mount point | client call sites + redirect + Socket.IO client option | 6 client sites, 1 redirect, 1 socket option | open |

### CAP-01 · sub-path mounting

**There is no base-URL support at all.** No `baseUrl`, `basePath` or `SCRIPT_NAME` anywhere in
`lib/`, `views/` or `static/` — measured 2026-09-15. `env.settings.baseURL` exists but is used
only to build *outbound* callback URLs (`lib/plugins/pushover.js:45`), never for anything the
browser loads.

The long-standing reputation of this as a swamp is not borne out; the sites are enumerable:

| site | what it hardcodes |
|---|---|
| `lib/client/index.js:61` | `'/api/v1/status.json'` |
| `lib/client/careportal.js:398` | `'/api/v1/treatments/'` |
| `lib/client/boluscalc.js:544` | `'/api/v1/treatments/'` |
| `lib/client/boluscalc.js:598` | `'/api/v1/food/'` |
| `lib/client/hashauth.js:198` | `'/api/v1/verifyauth'` |
| `lib/client/adminnotifiesclient.js:17` | `'/api/v1/adminnotifies'` |
| `lib/server/app.js:132` | the HTTPS redirect rebuilds from `req.url` — **this is BF-26**, and it is the one part of CAP-01 that is a defect rather than an absence, so it can land first and on its own |
| Socket.IO client | connects to the default `/socket.io/` |

**This is a single-tenant capability and it is the wrong tool for tenant discrimination.** Getting
sub-path mounting right does not make path-prefix *tenancy* work over websockets, because a
Socket.IO handshake carries the engine path and that path is a client option — see T3.5 in the
[execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md). Path-as-tenant needs the
proxy to assert the tenant in a header regardless of how good base-URL support becomes. Keeping
the two apart is what makes each of them small.

*Requested by*: the maintainer, as a long-standing goal predating this programme.


## 2. Detail

### BF-01 · `count/entries/where` silently matches nothing

`aggregate.js:21` calls `find_options(opts)` with **one argument**, so the collection's
`queryOpts` never arrive and `lib/server/query.js` falls back to its defaults — `dateField:
'date'`, no `useEpoch`. The two paths then inject different types for the same window:

```
list  path (useEpoch:true):  {"date":{"$gte":1789099222823}}              <- number
count path (defaults)     :  {"date":{"$gte":"2026-09-11T04:00:22.824Z"}} <- ISO string
```

`entries.date` is declared `number`, and **MongoDB compares only within a BSON type**, so the
injected two-day window excludes every document rather than bounding it. The endpoint returns
`200` with a count of zero.

*Evidence*: [seam interface](nightscout-storage-seam-interface-2026-09-14.md) §4.3.1, verified by
running `query.js` directly. Independently reconfirmed as a general class by the
[three-arm validation](../60-research/seam-filter-ast-three-arm-validation-2026-09-14.md) §3 class B.
*Fix*: pass the collection's `queryOpts` as the second argument. Ship with BF-02/BF-03 (plan T0.5).

### BF-02 · `insulin` and `carbs` bounds truncated

**FIXED 2026-09-15** by plan T0.5 — cgm-remote-monitor `bf/coercion` `88d1f8a4`, emitter `tools/nsschema/emit/coercion_emit.py`, write-up in [T0.5](../60-research/t05-schema-driven-coercion-2026-09-15.md).

`treatments.js` coerces query values through a hand-maintained per-collection `walker`:

```js
walker: { insulin: parseInt, carbs: parseInt, glucose: parseInt, ... }
```

`specs/nsschema/treatments.model.json` declares `insulin` and `carbs` as `number`, not integer.
So `find[insulin][$gte]=1.5` becomes `{"insulin":{"$gte":1}}` — **a query for boluses of at
least 1.5 units returns boluses of 1.0 units.**

**This is a data-correctness defect with review implications.** Anyone using the API to review
therapy data — a report tool, a clinician export, a caregiver checking what was delivered —
gets records that do not match what they asked for, with no error. It warrants a release note
rather than a silent fix. It is not, in itself, advice about dosing, and nothing here should be
read as such; the point is narrower and worse — **the data returned does not answer the
question asked.**

**Measured**, not asserted: `treatments.insulin` was observed as **142,360 fractional values
against 2,791 integer ones** across 11 sites — 98 % of its non-null values are fractional. So
`parseInt` on the bound is not a rounding nicety.

*Evidence*: [execution plan](nightscout-multitenancy-execution-plan-2026-09-14.md) §3.4, and
[the coercion drift measurement](../60-research/query-coercion-drift-2026-09-14.md) §2 Tier 1.

### BF-03 · Numeric filters that silently match nothing

**PARTLY FIXED 2026-09-15** by plan T0.5 — `devicestatus` (99 fields) and `profile` (10) are now typed from the schema, as are the fields `entries` and `treatments` were missing. cgm-remote-monitor `bf/coercion` `88d1f8a4`; write-up in [T0.5](../60-research/t05-schema-driven-coercion-2026-09-15.md).

**Two of the four collections named above were misfiled, and neither for the reason given.**

* **`food` reaches `lib/server/query.js` at no point.** `lib/server/food.js` exposes `list(fn)`, `listquickpicks(fn)` and `listregular(fn)` — none takes query options — and `lib/api/food/index.js` passes none. v1 `/food` accepts no filters at all, so there is no under-coercion to fix. (Its numeric fields are also `['number','string']` unions in the model, because the built-in client writes form-encoded; that is BF-16.)
* **`activity` has no numeric field to fix.** Its model has exactly two leaves, `_id` and `created_at`, both strings. The collection is open-bodied, so a deployment may hold numbers there, but nothing declares them and the table will not guess. It is wired to the table with a legitimately empty entry, so it starts working the day the model gains a field.

**A smaller correction to the table below:** `devicestatus` and `activity` are recorded as having no walker "at all". They actually inherit `query.js`'s *default* walker, `{ date: parseInt, sgv: parseInt }`, because neither sets `walker` and `default_options` fills one in. The conclusion is unchanged — the fields people filter on were untyped — but that is not what the code did.

| collection | `walker` |
|---|---|
| entries | 7 fields, all `parseInt` |
| treatments | `insulin carbs glucose` → `parseInt`; `notes eventType enteredBy` → regex |
| profile | `{}` — empty |
| **devicestatus, activity, food** | **none at all** |

A field with no `walker` entry stays a **string**, and MongoDB's type ordering means a numeric
field never matches a string bound. So `devicestatus` and `activity` have no coercion at all
and **every numeric filter on them matches nothing and returns 200**:

```
devicestatus  uploader.battery $lt=50   ->  {"uploader.battery":{"$lt":"50"}}   <- still a string
entries       delta            $gte=1.5 ->  {"delta":{"$gte":"1.5"}}            <- still a string
```

**Fixing this is user-visible in the good direction**: queries that silently returned nothing
start returning rows. Release-note it, so it arrives as a fix rather than as a surprise.

*Fix*: plan T0.5 — emit a coercion table from `specs/nsschema/*.model.json` (a sixth emitter)
and drive the walker from it, instead of four hand-maintained lists that drift.
**The emitter now exists** (`tools/nsschema/emit/coercion_emit.py`, `make schema-emit`); what
remains is wiring `lib/server/query.js` to it, which is `cgm-remote-monitor` work.

**The gap is 158 disagreements** — 147 under-coercions, 8 over-coercions, 1 stale entry, and 2
collections with no model at all. Graded by corpus evidence in
[the coercion drift measurement](../60-research/query-coercion-drift-2026-09-14.md) §2, because
they are **not** 158 equivalent bugs: `entries.sgv` is declared `number` but was observed as
895,418 integers and **zero** fractional values, so truncating its bound harms nobody today.

> **Sharpened by the three-arm validation.** T0.5 was written as a v1 bug fix. It is also a
> **precondition for the seam's backend-equivalence claim**: with correctly-typed values, all
> three arms agree 3000/3000; with mistyped ones, four divergence classes open, two of which
> produce *different data* depending on which backend a deployment runs.
> See [three-arm validation](../60-research/seam-filter-ast-three-arm-validation-2026-09-14.md) §4.

### BF-14 · `?count=0` is an unbounded read

API v1 builds its limit in five places with one expression:

```js
limit: opts && opts.count ? parseInt(opts.count) : undefined
```

A truthiness test **on a string**, then `parseInt`. `'0'` is a non-empty string, so it passes the
test; `parseInt` yields `0`; and **MongoDB defines `.limit(0)` as "no limit"**. `?count=0` returns
the whole collection. Measured on a ten-document collection: `count=0` -> 10 rows.

Two more from the same expression: `count=-3` silently returns 3 documents (MongoDB reads a
negative limit as legacy single-batch semantics), and `count=1e2` returns **one** document
because `parseInt('1e2')` stops at the `e`.

Not a seam regression — `origin/dev` chains `this.limit(parseInt(opts.count))` and reaches the
identical driver call.

*Fix*: API v3 already has it. `lib/api3/generic/collection.js:76` bounds-checks against
`API3_MAX_LIMIT`, returns `HTTP 400` on `0`, `abc` or a negative, and defaults sanely when absent.
Give v1 the same validation rather than inventing one.

*Also relevant to the seam*: `findFiltered` falls back to `toSafeInt(o.limit, 0)`, and `0` is the
value that means unbounded. `findMany`, in the same file, defaults to `1000`.

*Evidence*: [limit and projection](../60-research/seam-limit-and-projection-2026-09-14.md) §2,
`tools/qc/shape-arm.js`, against a real mongod.

*Compounds with [BF-18](#bf-18--the-read-bound-is-abandoned-on-limit0)*: the same `.limit(0)`
that makes the read unbounded also makes driver 7 abandon `READ_OPTIONS`, so the batch size
doubles as the read runs. Fixing this entry closes that one.

**Re-graded to high on 2026-09-15.** The medium grade rested on "it returns no wrong data".
With a second backend that is no longer true. Measured end to end through the shipping
`lib/server/entries.js` `list()`: `?count=0` returns **10 rows on MongoDB and 0 rows on
PostgreSQL** — an empty `200` on a glucose read. `?count=abc` behaves identically, because
`parseInt` yields `NaN`, which passes the `!== undefined/null` gate and reaches
`toSafeInt(NaN, 0)`. And `?count=-3` is a `2201W` — an HTTP 500 — against 3 rows on MongoDB.

*Sized, and at the time the measurement downgraded it from high to medium.*
`tools/qc/v1_count_census.py` over 10 client projects: **274 `count=` occurrences, no literal
`count=0`**. 86 % are literals (`1 … 9999999`); 9 % are computed at request time, which is where
the exposure sits — nothing bounds a computed count away from zero, and `oref0` has four such
sites. Two facts hold the grade down: nothing in the corpus reaches it today, and an unbounded
read is not a novel load for a server whose clients already send `count=100000` and
`count=9999999` deliberately. It returns no wrong data. It stays in the register because a
bounded request should not produce an unbounded read, and because the fix already exists in v3.

### BF-15 · `?fields=` with a dotted path returns `{}`

v3 projects in two stages. `storageProjection()` is handed to the driver, so MongoDB's
dotted-path rules apply and a **nested** document comes back. `applyProjection(doc)` then deletes
any **top-level** key not string-equal to something the client typed. A dotted request survives
stage one and is destroyed by stage two:

```
?fields=uploader.battery
  _id 1  from driver           {"_id":1,"uploader":{"battery":80}}
         after applyProjection {}          <- driver returned uploader; DESTROYED
```

The data is read, paid for, and discarded. The client gets `200` and an empty document.

`uploader.battery` is the canonical nested field in Nightscout and `devicestatus` is the
collection people query for it, so this is an ordinary request, not a contrived one.
Comma-separated top-level fields are unaffected, which is why it has gone unnoticed.

*Fix*: `applyProjection` must compare on paths rather than top-level keys — keep a key when any
requested field equals it or is prefixed by it plus `.`, and prune within the subtree. Either
that, or reject a dotted `fields` with `HTTP 400` rather than answering `200` with nothing.

*Evidence*: [limit and projection](../60-research/seam-limit-and-projection-2026-09-14.md) §3.3,
produced by running the shipping `fieldsProjector.js` against real mongod documents.

*Checked*: the system fields `storageProjection` adds and `applyProjection` removes are **not**
dead work — `col.resolveDates(doc)` consumes them in between
(`lib/api3/generic/search/operation.js:46-47`).

### BF-29 · a misspelt or file-named `ENABLE` entry disables a plugin silently

```
lib/plugins/index.js:140   return enable && enable.indexOf(plugin.name) > -1;

lib/plugins/insulinage.js:9          name: 'iage'
lib/plugins/boluswizardpreview.js:11 name: 'bwp'
lib/plugins/cannulaage.js:10         name: 'cage'
```

`ENABLE` is matched against the **registered plugin name**, which for five of the alarm plugins
differs from the file name. An unknown entry produces no warning, no log line and no error — the
plugin is simply absent.

**Why this is a defect and not documentation.** The failure is invisible in exactly the direction
that matters: an operator who intended to enable an age or bolus-wizard alarm sees a working site
with that alarm permanently off. Nothing on the status page distinguishes "not enabled" from
"misspelt".

**Found twice, independently**, by two agents that did not share results — both had alarm plugins
measure as INERT before noticing the naming rule, and one of them nearly published a wrong
`ddata` slice because of it. If it can silently defeat an instrument built to look at exactly
these plugins, it can silently defeat an operator.

*Fix*: warn at registration for any `ENABLE` entry matching no plugin name, and suggest the
nearest registered name.

*Evidence*: [alarm-critical slice](../60-research/alarm-critical-slice-2026-09-15.md),
[ns-evaluator spike](../60-research/ns-evaluator-spike-2026-09-15.md).

### BF-28 · `insulinage` can never raise an urgent alarm

One identifier, and the plugin's most important branch is dead:

```
lib/plugins/insulinage.js:92    if (insulinInfo.age >= insulinInfo.urgent) {
lib/plugins/insulinage.js:93      sendNotification = insulinInfo.age === prefs.urgent;

lib/plugins/cannulaage.js:87    if (cannulaInfo.age >= prefs.urgent) {
lib/plugins/cannulaage.js:88      sendNotification = cannulaInfo.age === prefs.urgent;
```

`urgent` is set on **`prefs`** (`:19`, `sbx.extendedSettings.urgent || 72`), never on
`insulinInfo`. So line 92 evaluates `age >= undefined`, which is always `false`, and the urgent
branch is unreachable — while line 93, one line below, reads `prefs.urgent` correctly. The three
sibling age plugins (`cannulaage`, `sageage`/`sensorage`, `batteryage`) all use `prefs.urgent` on
both lines.

**Consequence**: a person who has set an urgent insulin-reservoir age threshold never receives the
urgent notification. The warning branch is unaffected, so the failure is partial and quiet — the
plugin looks like it works.

*Found*: incidentally, during the `ns-evaluator` spike (T4.4), while ablating alarm producers —
not looked for. Pinned by a check in that harness: at 72 h the plugin requests nothing; at 48 h it
requests WARN.

*Fix*: `insulinInfo.urgent` → `prefs.urgent`. One identifier, and it matches three siblings.

> **Confirm intent before fixing.** This branch has never executed in any deployment, so repairing
> it **starts emitting an URGENT alarm that no operator has ever received** — on a threshold they
> may have set years ago and never seen honoured. That is the right end state, and it is also a
> behaviour change that should be release-noted rather than shipped as a typo fix. Both agents
> that found it independently flagged the same caveat.

*Evidence*: [ns-evaluator spike](../60-research/ns-evaluator-spike-2026-09-15.md),
`tools/qc/ns-evaluator-arm.js`.

*Not fixed by that task* — it is pre-existing, single-tenant, and belongs here rather than in a
tenancy commit.

### BF-04 · No operator allowlist on API v1

`lib/server/query.js:157` builds the filter with `traverse` type-coercion, injects a date
constraint, and **returns it to the driver with no operator allowlist**. Whatever
`find[x][$op]` a client sends reaches MongoDB — `$where`, `$expr`, an unbounded `$regex`.

**Status `fixed-in-seam`.** The seam branch's `fromMongo` (commit `68ffbd66`) parses `query.js`'s
output into the AST, and an AST that cannot represent an unlisted operator *is* the allowlist —
so this is repaired there as a structural consequence. **It should not have to wait for the
seam to land.** Extracting the allowlist as a standalone change is a small piece of work and a
security fix that ships to every current operator.

*Evidence*: {M} §6.5; seam interface §8.2.

### BF-05 · Debug logging on the count request path

```js
console.log('$match query', query);
console.log('AGGREGATE', groupBy);
```

Unguarded, on both `dev` (`a8888f0d`) and `chore/nightscout-modernization` (`0a4109f6`), so
every `/api/v1/count/*` request writes the constructed filter to stdout. Two problems: it is
noise the modernization branch's own quiet-logging work (`c2ac743c`) set out to remove, and a
filter can carry values a deployment would rather not have in its logs. **Route through the
existing logger at debug level, or delete.**

### BF-06 · Untyped `/api/v1/entries` read costs 42×

`?count=10` costs **0.83 ms** without `find[type]` and **0.02 ms** with it, for a byte-identical
response, because `ctx.cache.getData('entries')` deep-clones the whole 48-hour array before
anything is sliced. *Fix*: slice first, then clone the slice — the documents handed out are
still clones, so the defensive property is preserved. *Evidence*: {R} §12.2. Plan T0.2.

### BF-07 · `cache.insertData` round-trips the whole retained array

`insertData` returns `getData()` — a JSON round-trip over the **whole** retained array, per
datatype, per cycle: **4.08 ms**, 65 % of the post-#8733 load cycle.
**Resolve `dataloader.js:203` first** — `if (!element.mills) element.mills = element.date` writes
to the element, so a shallow copy changes behaviour there. The measurement sizes the prize; it
does not license the patch. *Evidence*: {R} §12.3. Plan T0.3.

### BF-08 · No jitter in `nightscout-connect`

800 actors fire their first upstream request inside one second on every restart and deploy
(`run()` sends `START` with no jitter), and stay phase-locked on the same five-minute boundary
afterwards. Different repository; independent of everything else here. *Evidence*: {R} §6.2.

### BF-09 · Socket dedup truthiness — unsettled, deliberately

`websocket.js` tests `if (data.data.insulin)` rather than presence, so a **`0`** insulin or carbs
value is skipped as a match key. No test covers it. **Recorded rather than guessed**: it may be
intentional. It needs a maintainer decision, and whichever way it goes it needs a test, because
nothing currently pins the behaviour. *Evidence*: seam interface §4.4.

### BF-10 · `mongod` fatal-asserts at the default file-descriptor limit

Docker's default `nofile=1024` is not enough for the collections and indexes Nightscout's own
test suite creates: WiredTiger hits `Too many open files` in `__wt_open` and `mongod` takes a
`fassert()` — **aborting the server**, not failing an operation.

This was reached by an ordinary test run, and matches EXP-MT-040b's finding at 50 tenant
databases. **So the fd ceiling is not a scale-only concern** — it is reachable by a self-hoster
running `mongod` in a container with default limits. Not a code defect; it belongs in the
operator documentation, and it is the kind of failure that looks like data loss to the person
it happens to.

### BF-11 · `treatments.duration` and `rate` filters match nothing

**FIXED 2026-09-15** by plan T0.5 — cgm-remote-monitor `bf/coercion` `88d1f8a4`, emitter `tools/nsschema/emit/coercion_emit.py`, write-up in [T0.5](../60-research/t05-schema-driven-coercion-2026-09-15.md).

Measured against a real `mongod`: `find[duration][$gte]=30` returned **0 rows** before and **2 of 2** after.

Neither field has a `walker` entry, so a bound stays a string and MongoDB's type ordering means
it never matches a numeric field. `find[duration][$gte]=30` returns an empty list and HTTP 200.

`duration` is present on **91 % of treatment documents across 10 sites**, and **88 % of its
values are fractional**. `rate` is on 55 % of documents. These are temp basals — not an obscure
corner of the schema. Same root cause as BF-03 and fixed by the same change; listed separately
because "devicestatus has no coercion" undersells which fields are affected.

*Evidence*: [coercion drift](../60-research/query-coercion-drift-2026-09-14.md) §2 Tier 1.

### BF-12 · `entries.rawbg` is a stale walker entry — **INVALID, closed 2026-09-15**

**This defect does not reproduce, and the entry above is struck through.** It was raised from a
mis-transcription of the walker, which this register and
`tools/nsschema/emit/coercion_emit.py` both carried.

`lib/server/entries.js` does not coerce `rawbg`. Its walker is:

```js
{ date, sgv, filtered, unfiltered, rssi, noise, mbg }
```

The entry is **`rssi`**. `git log --all -S"rawbg" -- lib/server/entries.js` returns **no commits
on any branch** — the string has never been in that file; `origin/chore/nightscout-modernization`
has `rssi` too. And `rssi` **is** in the model, as `integer`, with 32,098 observed values on one
site, so it is a *correct* walker entry, not a dead one.

The drift report now finds **zero ORPHAN rows** across every collection. The hand-maintained list
was missing entries — 148 of them — but it was not carrying stale ones, and the claim that the
drift "runs both ways" is not supported. Write-up: [T0.5](../60-research/t05-schema-driven-coercion-2026-09-15.md).

### BF-13 · v3 paging loses documents when the sort chain ties

`parseSort` appends `identifier`, `created_at` and `date` as tiebreaks. When **all** of them tie
— documents with no `identifier`, sharing one `created_at` and one `date`, as a bulk import
stamps them — the order is not total, MongoDB's blocking sort is not stable among equal keys, and
each `skip` re-runs the query. Measured: **7 of 12 documents never returned, two returned three
times**, deterministically.

**Not fixable by indexing**: only an index matching the sort exactly gives a stable `IXSCAN`, and
the sort's leading key is client-chosen (`?sort=`). Under every index set Nightscout creates the
plan is `SORT <- COLLSCAN`.

**Fires on the default path** — with no `?sort=` the chain is just the three tiebreaks, so an
ordinary paged read is exposed.

*Fix*: append `sort._id = sortDirection`. `_id` is always present and always unique, so the order
becomes total. Verified: 0/12 lost. Carry the same rule into the seam's ordering translation, or
it reappears on PostgreSQL.

*Precondition is specific and should not be overstated*: all three of no-`identifier`,
tied `created_at`, tied `date`. Any one of them differing makes it safe.

**Sized against the 11-site corpus** (~1.5 M documents) and it is **concentrated in
`devicestatus`** — expected tie-group straddles per full paginated sweep: `devicestatus` median
**23.5** (max 64), against `entries` 0.01, `treatments` 0.02, `profile` 0.09. Uploaders write
`devicestatus` in bursts sharing one `created_at`/`date`. So a client paging `entries` will
typically lose nothing, and a tool paging `devicestatus` to reconstruct controller behaviour
loses records silently — on the collection replay fidelity depends on.

*Evidence*: [ordering and pagination](../60-research/seam-ordering-and-pagination-2026-09-14.md) §3.
**Reproduced synthetically against `mongod` 7.0.43, not against a live Nightscout** — confirm
before treating as settled.

### BF-16 · `food.hidden` has no type; the server filter and the client disagree

The `food` collection stores quick picks with a `hidden` flag, and the quick-pick list filters on
it. The two ends of that round trip do not agree on what the value is:

- `lib/server/food.js` `listquickpicks` queries `cmp('eq', 'hidden', 'false')` — the **string**
  `'false'`. Pre-existing upstream: released `cgm-remote-monitor` spells the same filter
  `{ 'hidden' : 'false' }` at `lib/server/food.js:146`, so this is not a regression from the
  storage-seam work.
- `lib/food/food.js:377` writes `foodquickpick[index].hidden = this.checked` — a **boolean**.
- `lib/food/food.js:69-73` `restoreBoolValue` reads it back as `record[key] === 'true'`, i.e. the
  client expects a **string** from storage.

It works today only by an accident of transport. The editor posts with
`$.ajax({ method: 'PUT', url: '/api/v1/food/', data: foodrec })` and **no `contentType`**, so
jQuery form-encodes; `wares.urlencodedParser` is `extended: true`, so every leaf arrives as a
string. `hidden: false` becomes `'false'`, which is what the filter matches and what
`restoreBoolValue` expects.

**The field therefore has no declared type. Its stored type is a property of the request, not of
the field.** A client that sends `application/json` with a real boolean stores a boolean, and
`{hidden: 'false'}` never matches it: that quick pick disappears from `/api/v1/food/quickpicks`
while remaining in `/api/v1/food/`. Nothing reports an error. The same holds for
`hideafteruse`.

*Fix*: give the field one type and accept both on read — match `$in: [false, 'false']` (or
normalise on write) rather than picking a side, since both spellings are already on disk
wherever a non-jQuery client has ever written. Do not "fix" the client to send JSON without
fixing the filter first; that is the change that breaks it.

**Secondary consequence, same root cause.** Form encoding stringifies *every* non-string value in
a food document, not just the booleans — `carbs`, `portion`, `fat`, `protein`, `energy`, `gi` and
`position`. `listquickpicks` sorts `{ position: 1 }`, and a lexicographic sort of `'0' … '10'`
orders `'10'` between `'1'` and `'2'`. A user with eleven or more visible quick picks sees them in
the wrong order. Unlike the `hidden` mismatch this one fires on the **shipping** path, with the
built-in editor and no third-party client involved.

*Not reproduced against a live instance.* Both readings are derived from the source and from
jQuery's and `qs`'s documented behaviour; the corpus contains no `food` collection to check
against — no snapshot ever fetched one.

*Recorded here rather than fixed* because the point is the class, not the instance: this is
exactly what a typed model exists to prevent. `specs/nsschema/food.model.json` therefore declares
`hidden` and `hideafteruse` as `["boolean", "string"]` with `type_undetermined`, and says why,
instead of papering over the ambiguity by choosing one.

*Evidence*: `specs/nsschema/food.model.json` (`type_undetermined_why`);
`tools/nsschema/code_model.py` `SOURCE_ASSERTIONS` anchors the string comparison so that fixing
it fails `make schema-code-drift` and forces the model to be revisited.

### BF-17 · A subject edit writes the access token into the database in plaintext

> **Fixed 2026-09-15** on `bf/auth` (`64db1f35`), and **reproduced against a running instance**
> first — the chain below holds link for link on `dev`. One edit through the stock endpoints puts
> the token on disk, and the token read straight out of the collection authenticates (HTTP 200).
> The `notes` erasure reproduces in the same edit.
>
> `create` and `save` now build the document from the fields it owns rather than from the request
> body, and `reload()` drops the derived fields off a stored document before deriving them.
> `GET /subjects` now serves `notes`, because the durable fix does **not** fix the notes on its
> own: the client sends `notes: ''` since `GET` never gave it one, and a field whitelist writes
> that empty string faithfully. The notes fix has to be at the other end of the round-trip.
>
> **Rows already written still hold tokens, and clearing the field is not enough.** The token is
> deterministic in `_id`, `name` and the enclave key, so anyone who already read the collection —
> or a backup taken while it was in there — still holds a working credential after an `$unset`.
> Remediation is rotation, and it is the operator's decision. No migration was written. See
> [the report](../60-research/bf17-bf30-auth-defects-2026-09-15.md) §2.3.
>
> **One thing this entry missed**: `created_at` is not served by `GET /subjects` either, so an
> edit also gives the document a brand-new `created_at`. Data loss, not a security problem, and
> not fixed — one more field in the `pick` would round-trip it.


Found while deriving `specs/nsschema/auth_subjects.model.json`, by asking the narrow question
"which of these fields are actually stored?"

**`accessToken` is normally a derived value, not a stored one.** `lib/authorization/storage.js`
`reload()` recomputes it for every subject from the subject's `_id`, its `name` and the enclave
key. A stored subject document does not carry it.

Three steps put it there anyway, and each is reasonable on its own:

1. `lib/authorization/endpoints.js:38-42` — `GET /subjects` serves
   `pick(subject, ['_id', 'name', 'accessToken', 'roles'])`. Including the token is deliberate:
   the admin UI has to display it so an operator can copy it into a device.
2. `lib/admin_plugins/subjects.js:43` — the edit dialog sends the object it was given straight
   back, `data: subject`. It does not construct a payload of changed fields.
3. `lib/authorization/storage.js` `save` — `replaceOne({_id}, obj, {upsert: true})` replaces the
   document **wholesale** with the request body.

So changing a subject's name, or its roles, or its notes, writes the bearer token into the
subject's document as an ordinary string. Nothing warns, and the UI looks identical afterwards.

**Why this is worth more than the tidiness of it.** Derivation is what keeps the database from
being sufficient on its own: a reader of the stored documents alone — a backup, a replica, a
hosted MongoDB snapshot, a support export — cannot mint tokens without the enclave key. After any
subject edit, that separation is gone for that subject, and read access to the collection is read
access to a working credential. It converts a database-disclosure incident into a full API
compromise, silently and retroactively, for every subject an operator has ever edited.

Two related observations from the same reading, neither a separate entry:

- `accessTokenDigest` and `digest` are also derived and also not stored, but `GET /subjects` does
  not serve them, so they are not round-tripped. The exposure is `accessToken` alone.
- `auth_subjects.notes` has the mirror-image bug: it *is* stored, but `GET /subjects` does not
  return it, so the dialog populates its input from `undefined` and the wholesale PUT writes `''`
  back. **Any note an operator saves is erased by the next edit of that subject.**

*Fix*: the durable one is for `save` to write only the fields a subject document owns, rather
than the request body — which fixes the token and the notes together, and is the same shape of
fix as "don't replace a document with whatever a client sent". Stripping `accessToken` in the PUT
handler is the smaller change and closes the exposure; it leaves `notes` broken. Either way, a
deployment that has edited subjects already has tokens on disk, so a fix should also clear the
field on the next reload rather than only stopping new writes.

*Not reproduced against a live instance.* The chain is read from the released
`cgm-remote-monitor` source in `externals/cgm-remote-monitor-official`; every link is a literal
in that tree. **Not a regression from the storage-seam work** — the seam changed `save` from
`replaceOne` to a one-operation `bulkUpsert` with `mode: 'replace'`, which is the same wholesale
replacement.

*Evidence*: `specs/nsschema/auth_subjects.model.json` (`credential_warning`), which also records
that the field is `secret`/`credential` so no emitter or exporter can treat it as ordinary text.

### BF-30 · The auth-failure delay is keyed on something the caller chooses

> **Fixed 2026-09-15** on `bf/auth` (`a26ba416`), **reproduced against a running server**, and
> **two claims below are corrected by that reproduction**. Full working in
> [the report](../60-research/bf17-bf30-auth-defects-2026-09-15.md) §1.
>
> **1. `TRUST_PROXY` does not exist on `dev`.** It is a seam-branch construct, and so is
> `createClientIP`. `lib/server/env.js:43` is `env.debug = {`. What `dev` actually does is
> *weaker*: `getRemoteIP` calls `forwarded(req, req.headers)` — `forwarded-for`'s third argument
> is the proxy whitelist and it is not passed, in four separate copies of that function. So the
> address is client-controlled unconditionally, with no default to narrow and nothing an operator
> can configure. Fix option 3 below is therefore not available on `dev`.
>
> **2. Fix option 1 — key on the credential — was implemented and measured, and it is a net
> regression.** It fixes the rotating-address case and *removes* the throttle from the case the
> shipping code did cover: a brute force varies the credential by definition, so a counter keyed
> only on the credential is fresh on every guess. Measured at 200 ms configured delay, four
> guesses from one fixed address: 200/200/200 ms shipping, 4/3/2 ms under credential keying.
>
> **3. The penalty does not accumulate even in the working case.** Per key the shipping code is a
> flat rate limiter (~200 ms every time, not 200/400/600), because `addFailedRequest` resets to
> `now + DELAY_ON_FAIL`. The defect is that the throttle never *engages*, not that it fails to
> grow.
>
> What landed: the delay is keyed on both the socket peer address (unforgeable, carries the
> throttle) and a salted digest of the attempted credential, taking the longer wait. The wait
> moved from before resolution to the failure path, which is the load-bearing part — behind a
> platform proxy the peer address is shared, and delaying every request on a shared key is the
> self-inflicted denial of service this entry rightly warns about. Delaying only failures means a
> request that authenticates never waits on a neighbour. Option 2 (bound the list) landed too,
> with the two namespaces bounded separately so a flood of made-up credentials cannot evict the
> peer entry throttling the flooder; the sweep was also a `setTimeout`, so it had been running
> once and never again.


Found while verifying T3.1's decision to read `req.headers.host` rather than `req.hostname`.
That decision is correct, and checking *why* turned up a larger consequence of the same root
cause.

**`TRUST_PROXY` defaults to the empty string** (`lib/server/env.js:43`), and
`compileTrust('')` returns express's compatibility mode. Measured:

```
compileTrust('') trusts an arbitrary hop?  true
compileTrust('') trusts a second hop?      true
compileTrust('127.0.0.1') trusts it?       false
```

So by default the server believes any `X-Forwarded-For` it is handed. Measured again, through
the code that actually decides:

```
no header             -> 203.0.113.9      (the real peer)
client sets header A  -> 198.51.100.1
client sets header B  -> 198.51.100.2
```

**`lib/authorization/delaylist.js` keys purely on that string.** `addFailedRequest(ip)` and
`shouldDelayRequest(ip)` both index `ipDelayList[String(ip)]`, and `lib/authorization/index.js`
feeds them `data.ip` from `createClientIP(env.trustProxy)`. A caller that presents a different
forwarded address each time gets a **fresh key every time**, so the 5-second penalty
(`AUTH_FAIL_DELAY`) never accumulates and the throttle never engages. That throttle is the only
thing standing between an attacker and unlimited guesses at `API_SECRET` or a token.

**This is not simply "the default is wrong", and the fix is not "stop trusting".** Most
Nightscout deployments sit behind a platform proxy (Heroku, Railway, Azure) where the real peer
address *is* only available in `X-Forwarded-For`, and where the operator never configures
anything. A default that refused the header would report every request as coming from the
proxy — which collapses every user in a deployment onto one delay-list key and turns the
throttle into a self-inflicted denial of service. **The permissive default exists for a real
reason**; what is wrong is that a security control was keyed on a value that default makes
untrustworthy.

*Fix, in preference order:*
1. **Key the delay list on something the caller does not choose.** The credential being
   attempted is the obvious candidate — the point is to slow repeated guesses at *a secret*, and
   that key is identical whether the attacker rotates addresses or not. It also fixes the
   behind-a-proxy case, where today every user shares one key.
2. **Bound the list.** It is an unbounded object keyed by an attacker-controlled string, swept
   only once a minute; a burst of forged addresses grows it until the sweep. Secondary to (1)
   and the same root cause.
3. Narrow the `TRUST_PROXY` default with a documented migration — worth doing, but it is a
   deployment-compatibility change and it does not fix (1) for deployments that legitimately
   must trust the header.

*Not reproduced against a live server.* Both measurements above are of the shipping functions in
`externals/work/crm-seam`, called directly; the chain from `data.ip` to `shouldDelayRequest` is
read from `lib/authorization/index.js:140-206`. **Not a regression from any work in this
programme** — `delaylist.js` and the `TRUST_PROXY` default both predate it.

*Related, not the same*: T3.1 avoids this class for tenant resolution by reading
`req.headers.host` directly and refusing to honour a configured alternative header unless
`TRUST_PROXY` is set. That is the pattern the fix above generalises.

### BF-31 · One request re-languages the whole process, alarms included

Found while fixing a blind spot in `tools/qc/tenant-shared-state.js` (see
[the audit](../60-research/tenant-shared-state-audit-2026-09-15.md) §4a): the tool could not see
a singleton created by a factory and held at a call site, and `language` is the widest one in the
server.

`lib/server/server.js:34` builds **one** language instance for the process and passes it to
`bootevent`. `lib/api/googlehome/index.js:20-29` then does this inside a request handler:

```js
ctx.language.set(locale);
moment.locale(locale);
```

`language.set` assigns `language.lang` on that shared instance — it is a persistent mutation, not
a per-call option — and `moment.locale` is a global mutation of the library. So **one
authenticated request changes the language for every subsequent request and every notification
in the process**, until another request changes it back.

`lib/server/bootevent.js:212` carries it into the alarm path: `ctx.levels.translate =
ctx.language.translate`, so level names (`Urgent`, `Warning`) are translated through the same
shared instance that the Google Home handler just re-pointed.

**Severity, read honestly.** The route is mounted only `if (ctx.googleHome)`
(`lib/api/index.js:74`), so it is opt-in, and the caller needs `api:*:read` — which in a family
deployment is everyone holding the token. The consequence in ordinary use is a display bug. The
consequence in the alarm path is that a notification can arrive in a language the recipient does
not read, which for an alarm is a usability failure with a safety edge rather than a cosmetic
one.

*Fix*: the locale is a property of the **request**, not of the server. Resolve it per request and
pass it to the handler, rather than setting it on the shared instance; `moment.locale` has a
per-instance form (`moment().locale(x)`) that avoids the global. Under multitenancy this stops
being one deployment's bug and becomes a cross-tenant leak, which is why T3.3 named `language`
and `levels` as still-shared and did not attempt a fix — a correct one is a locale-keyed instance
cache, since a language file is 45–60 KB and one per tenant is the wrong shape.

*Not reproduced against a live server.* `language.set`'s persistence and the `levels.translate`
assignment were read and exercised directly; the Google Home route was not driven end to end.

### BF-32 · `$exists` was inverted by type coercion — **FIXED 2026-09-15**

Found while fixing BF-02/BF-03 (plan T0.5): `walk_prop` applied the walker's conversion to
**every leaf** of a field's query fragment, including operands that are not values drawn from the
field's domain. On `origin/dev`:

```
find[sgv][$exists]=true   ->  { sgv: { $exists: NaN } }
find[sgv][$regex]=^1      ->  { sgv: { $regex: NaN } }
```

`NaN` is falsy, so **`$exists=true` returned exactly the documents that do not have the field** —
the opposite of what was asked, with HTTP 200.

It was reachable on the 10 fields that carried a walker entry, which is why it had stayed
invisible: those are the fields most likely to be present anyway. Generalising coercion to 158
fields would have generalised this defect with it, which is how it surfaced.

*Fix*: shipped with T0.5. `lib/server/query-coercion.js` leaves `$exists`, `$type`, `$regex`,
`$options`, `$where`, `$expr`, `$text`, `$comment` and `$jsonSchema` operands alone, while still
converting every element of an `$in` list. Applied to explicit walker entries as well as
schema-driven ones, so the pre-existing case is fixed too.

*Evidence*: [T0.5](../60-research/t05-schema-driven-coercion-2026-09-15.md) §4, reproduced against
the original file before the change.
**Not a regression from this programme** — both predate it.

## 3. How to use this register

1. **Anything found while doing multitenancy work that is also broken today gets an entry
   here**, at the time it is found, with its evidence link. The register is the mechanism that
   keeps that promise.
2. **Prefer landing these independently.** Each one is small, each ships to every current
   operator, and none needs a tenancy decision.
3. **Release-note the behaviour changes.** BF-02 and BF-03 change what queries return. That is
   the point, and it should arrive as a documented fix. **Done 2026-09-15** — the note is in
   cgm-remote-monitor's `CHANGELOG.md` under `[Unreleased] / Fixed`, naming the collections and
   fields whose results change, with before/after examples.
4. **Keep severities honest.** "Wrong answer with HTTP 200" is worse than "slow", and both are
   worse than "noisy". The table is sorted by that, not by effort.
