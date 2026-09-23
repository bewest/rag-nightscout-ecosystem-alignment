# CRUD by `_id`: a matrix over every collection, stored `_id` form, API v1, API v3 and the websocket

*Contributor-facing. Measured 2026-09-23 against `origin/dev` `1f9a9d10` (15.0.9),
`bf/object-id-consistency` `597e2899`, and `bf/object-id-crud` `c721e202` (four commits on
`597e2899`). Storage: `mongo:7` and MongoDB 4.4 in Docker. Node 20.20.0 and 22.23.2 via `n exec`.
Synthetic records only. Every row marked "measured" or "reproduced" was run; rows marked "read"
were not.*

Continues [`object-id-other-collections-2026-09-23.md`](object-id-other-collections-2026-09-23.md)
(BF-99 to BF-102), whose §9 "Not changed" list is the backlog here. Plan row: backfix-2 plan §1a
"15.0.9 ID consistency". PR body draft:
[`bf-object-id-crud.md`](../../../reports/phase0-pr-bodies/bf-object-id-crud.md).

## Branch

`bf/object-id-crud`, local, not pushed, worktree `externals/work/crm-bf-object-id-crud`, on
`bf/object-id-consistency` `597e2899`:

| | commit | what it fixes or adds |
|---|---|---|
| 1 | `4b41bcf8` | an entry re-POSTed with its own hex `_id` answered 500 when the stored entry at that time and type had another `_id` (the string form, or a different id) |
| 2 | `a612a26f` | `GET` / `DELETE /api/v1/entries/<UPPER-CASE HEX>` was read as an entry type; the shared v1 `_id` check uses the helper's pattern |
| 3 | `12c01268` | websocket `dbAdd` stored a hex `_id` as the string; `dbUpdate`, `dbUpdateUnset`, `dbRemove` missed a string-stored hex `_id`; a similar-treatment match on a string-`_id` treatment did not update it |
| 4 | `c721e202` | `tests/api.crud-by-id.matrix.test.js`, 336 cells |

## 1. The matrix

`tests/api.crud-by-id.matrix.test.js` boots one server with API v1, API v3 and the websocket
(the API v3 test fixture, v1 mounted beside it). Each cell seeds one record directly into MongoDB
(or creates one), runs one operation by that record's id, and then reads MongoDB for every record
with that id in any `_id` form or as `identifier`.

Axes:

- **collection**: entries, treatments, devicestatus, profile, food, activity (every v1 route with
  an id-addressable write; `lib/api/*/index.js`, read). API v3 over the same collections except
  activity, which v3 does not serve; v3 `settings` has no v1 counterpart and is not in the matrix.
  The websocket's `supportedCollections` are the same six.
- **stored `_id` form**: `oid` (ObjectId, asked by lower-case hex), `oidU` (ObjectId, asked by
  upper-case hex), `lower` (lower-case 24-hex string), `upper` (upper-case 24-hex string), `uuid`
  (UUID string). For create, the form is what is sent: `lower`, `upper`, `uuid`.
- **operation**: v1 create with own `_id`, re-send (POST the stored record again with its `_id`),
  `find[_id]` (not food: no find route), `GET /entries/<id>`, PUT (treatments, profile, food,
  activity), DELETE by id; v3 GET, PUT, permanent DELETE, POST with the same `identifier`;
  websocket `dbAdd` create, `dbAdd` re-send, `dbUpdate`, `dbRemove`.

The expected outcome of every cell is written in the test (`EXPECT`) with its reason. Deliberate
differences are expected outcomes, not failures:

| rule | cells |
|---|---|
| a UUID `_id` moves to `identifier` (REQ-SYNC-072, `UUID_HANDLING` on by default) | v1 create, treatments and entries |
| a non-hex `_id` is refused with 400 | v1 create, re-send, PUT, DELETE for devicestatus, profile, food, activity |
| `/entries/:spec` takes a 24-hex id; anything else is an entry type | v1 GET and DELETE `/entries/<uuid>` (`find[_id]` finds it) |
| a re-sent profile or devicestatus `_id` is refused as a duplicate (500) | v1 re-send, profile (BF-99 create guard) and ObjectId-stored devicestatus |
| the websocket keeps a non-hex `_id` as given (`tests/websocket.shape-handling.test.js`) | ws create, `uuid` |
| API v3 identifiers are immutable: a PUT naming an ObjectId record by its upper-case hex is refused (400) | v3 PUT, `oidU` |

Two behaviours are **kept as they are, pending a maintainer decision** (§5). Their cells assert
today's outcome and also carry the outcome a consistent rule would give (the "consistent rule"
column below):

- a devicestatus re-sent with the `_id` of a string-stored copy is stored beside it (`597e2899`
  commit c, no create guard);
- API v3 cannot address a v1 record whose `_id` is a non-hex string.

`CRUD_MATRIX_OUT=<file>` writes every cell as JSON.

## 2. Results

Run with the matrix file from `c721e202` copied into each tree, Node 20.20.0:

| tree | `mongo:7` passing / failing | MongoDB 4.4 passing / failing |
|---|---|---|
| `origin/dev` `1f9a9d10` | 194 / 142 | not run |
| `bf/object-id-consistency` `597e2899` | 288 / 48 | 288 / 48 |
| `bf/object-id-crud` `c721e202` | 336 / 0 | 336 / 0 |

MongoDB 4.4 and `mongo:7` gave the same outcome in all 336 cells on both trees measured.

Per collection and operation ("n/m ok" of the stored forms; "kept" = kept pending decision):

**`origin/dev` `1f9a9d10`**

| api op | entries | treatments | devicestatus | profile | food | activity |
|---|---|---|---|---|---|---|
| v1 create | 3/3 ok | 3/3 ok | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** |
| v1 resend | **2/5 wrong** | **2/5 wrong** | **4/5 wrong** | **2/5 wrong** | **4/5 wrong** | **4/5 wrong** |
| v1 find | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | — | **2/5 wrong** |
| v1 get | **3/5 wrong** | — | — | — | — | — |
| v1 update | — | **2/5 wrong** | — | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |
| v1 delete | **3/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |
| v3 get | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | — |
| v3 put | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | — |
| v3 delete | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | — |
| v3 resend | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | **2/5 wrong** 1 kept | — |
| ws create | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** |
| ws resend | **2/5 wrong** | 5/5 ok | 5/5 ok | 5/5 ok | **2/5 wrong** | **2/5 wrong** |
| ws update | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |
| ws remove | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |

**`bf/object-id-consistency` `597e2899`**

| api op | entries | treatments | devicestatus | profile | food | activity |
|---|---|---|---|---|---|---|
| v1 create | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok |
| v1 resend | **2/5 wrong** | 5/5 ok | 3/5 ok, 2 kept | 5/5 ok | 5/5 ok | 5/5 ok |
| v1 find | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | — | 5/5 ok |
| v1 get | **2/5 wrong** | — | — | — | — | — |
| v1 update | — | 5/5 ok | — | 5/5 ok | 5/5 ok | 5/5 ok |
| v1 delete | **2/5 wrong** | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |
| v3 get | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | — |
| v3 put | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | — |
| v3 delete | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | — |
| v3 resend | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | — |
| ws create | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** |
| ws resend | **2/5 wrong** | 5/5 ok | 5/5 ok | 5/5 ok | **2/5 wrong** | **2/5 wrong** |
| ws update | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |
| ws remove | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |

**`bf/object-id-crud` `c721e202`**

| api op | entries | treatments | devicestatus | profile | food | activity |
|---|---|---|---|---|---|---|
| v1 create | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok |
| v1 resend | 5/5 ok | 5/5 ok | 3/5 ok, 2 kept | 5/5 ok | 5/5 ok | 5/5 ok |
| v1 find | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | — | 5/5 ok |
| v1 get | 5/5 ok | — | — | — | — | — |
| v1 update | — | 5/5 ok | — | 5/5 ok | 5/5 ok | 5/5 ok |
| v1 delete | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |
| v3 get | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | — |
| v3 put | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | — |
| v3 delete | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | — |
| v3 resend | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | 4/5 ok, 1 kept | — |
| ws create | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok |
| ws resend | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |
| ws update | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |
| ws remove | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |


On dev the devicestatus re-send of a string-stored `_id` answers 500 and keeps one record, which
is the consistent outcome; `597e2899` stores a second copy (§5, D1), so those two cells count as
wrong on dev against the asserted value.

### 2.1 Cells that differ on `bf/object-id-consistency` `597e2899`

"asserted" is the value the test checks; "consistent rule" is shown where it differs.

| api | op | collection | stored/sent form | observed | asserted | consistent rule |
|---|---|---|---|---|---|---|
| v1 | get | entries | oidU | 200 n=0 | 200 n=1 | — |
| v1 | delete | entries | oidU | 200 n=1 | 200 n=0 | — |
| v1 | resend | entries | lower | 500 [string] | 200 [string] | — |
| v1 | resend | entries | upper | 500 [string] | 200 [string] | — |
| v1 | get | entries | upper | 200 n=0 | 200 n=1 | — |
| v1 | delete | entries | upper | 200 n=1 | 200 n=0 | — |
| v1 | resend | devicestatus | lower | 200 [ObjectId,string] | = observed | 500 [string] |
| v1 | resend | devicestatus | upper | 200 [ObjectId,string] | = observed | 500 [string] |
| v3 | get | entries | uuid | 404 | = observed | 200 |
| v3 | put | entries | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | entries | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | entries | uuid | 500 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | treatments | uuid | 404 | = observed | 200 |
| v3 | put | treatments | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | treatments | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | treatments | uuid | 500 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | devicestatus | uuid | 404 | = observed | 200 |
| v3 | put | devicestatus | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | devicestatus | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | devicestatus | uuid | 500 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | profile | uuid | 404 | = observed | 200 |
| v3 | put | profile | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | profile | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | profile | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | food | uuid | 404 | = observed | 200 |
| v3 | put | food | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | food | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | food | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| ws | create | entries | lower | [string] | [ObjectId] | — |
| ws | create | entries | upper | [string] | [ObjectId] | — |
| ws | resend | entries | oid | n=2 | n=1 | — |
| ws | resend | entries | oidU | n=2 | n=1 | — |
| ws | update | entries | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | entries | lower | success n=1 | success n=0 | — |
| ws | update | entries | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | entries | upper | success n=1 | success n=0 | — |
| ws | create | treatments | lower | [string] | [ObjectId] | — |
| ws | create | treatments | upper | [string] | [ObjectId] | — |
| ws | update | treatments | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | treatments | lower | success n=1 | success n=0 | — |
| ws | update | treatments | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | treatments | upper | success n=1 | success n=0 | — |
| ws | create | devicestatus | lower | [string] | [ObjectId] | — |
| ws | create | devicestatus | upper | [string] | [ObjectId] | — |
| ws | update | devicestatus | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | devicestatus | lower | success n=1 | success n=0 | — |
| ws | update | devicestatus | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | devicestatus | upper | success n=1 | success n=0 | — |
| ws | create | profile | lower | [string] | [ObjectId] | — |
| ws | create | profile | upper | [string] | [ObjectId] | — |
| ws | update | profile | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | profile | lower | success n=1 | success n=0 | — |
| ws | update | profile | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | profile | upper | success n=1 | success n=0 | — |
| ws | create | food | lower | [string] | [ObjectId] | — |
| ws | create | food | upper | [string] | [ObjectId] | — |
| ws | resend | food | oid | n=2 | n=1 | — |
| ws | resend | food | oidU | n=2 | n=1 | — |
| ws | update | food | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | food | lower | success n=1 | success n=0 | — |
| ws | update | food | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | food | upper | success n=1 | success n=0 | — |
| ws | create | activity | lower | [string] | [ObjectId] | — |
| ws | create | activity | upper | [string] | [ObjectId] | — |
| ws | resend | activity | oid | n=2 | n=1 | — |
| ws | resend | activity | oidU | n=2 | n=1 | — |
| ws | update | activity | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | activity | lower | success n=1 | success n=0 | — |
| ws | update | activity | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | activity | upper | success n=1 | success n=0 | — |


### 2.2 Cells kept pending decision on `bf/object-id-crud` `c721e202`

No cell differs from its asserted value. These 22 cells assert today's behaviour:

| api | op | collection | stored/sent form | observed | asserted | consistent rule |
|---|---|---|---|---|---|---|
| v1 | resend | devicestatus | lower | 200 [ObjectId,string] | = observed | 500 [string] |
| v1 | resend | devicestatus | upper | 200 [ObjectId,string] | = observed | 500 [string] |
| v3 | get | entries | uuid | 404 | = observed | 200 |
| v3 | put | entries | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | entries | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | entries | uuid | 500 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | treatments | uuid | 404 | = observed | 200 |
| v3 | put | treatments | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | treatments | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | treatments | uuid | 500 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | devicestatus | uuid | 404 | = observed | 200 |
| v3 | put | devicestatus | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | devicestatus | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | devicestatus | uuid | 500 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | profile | uuid | 404 | = observed | 200 |
| v3 | put | profile | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | profile | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | profile | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | food | uuid | 404 | = observed | 200 |
| v3 | put | food | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | food | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | food | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |


### 2.3 Cells that differ on `origin/dev` `1f9a9d10`

142 differ from the asserted value (94 of them are fixed by `597e2899`, the other 48 are §2.1), and
20 more are the kept cells of §2.2.

<details><summary>All 162 rows</summary>

| api | op | collection | stored/sent form | observed | asserted | consistent rule |
|---|---|---|---|---|---|---|
| v1 | get | entries | oidU | 200 n=0 | 200 n=1 | — |
| v1 | delete | entries | oidU | 200 n=1 | 200 n=0 | — |
| v1 | resend | entries | lower | 500 [string] | 200 [string] | — |
| v1 | find | entries | lower | 200 n=0 | 200 n=1 | — |
| v1 | get | entries | lower | 500 n=0 | 200 n=1 | — |
| v1 | delete | entries | lower | 200 n=1 | 200 n=0 | — |
| v1 | resend | entries | upper | 500 [string] | 200 [string] | — |
| v1 | find | entries | upper | 200 n=0 | 200 n=1 | — |
| v1 | get | entries | upper | 200 n=0 | 200 n=1 | — |
| v1 | delete | entries | upper | 200 n=1 | 200 n=0 | — |
| v1 | resend | treatments | lower | 200 [ObjectId,string] | 200 [ObjectId] | — |
| v1 | find | treatments | lower | 200 n=0 | 200 n=1 | — |
| v1 | update | treatments | lower | 200 n=2 edited=false | 200 n=1 edited=true | — |
| v1 | delete | treatments | lower | 200 n=1 | 200 n=0 | — |
| v1 | resend | treatments | upper | 200 [ObjectId,string] | 200 [ObjectId] | — |
| v1 | find | treatments | upper | 200 n=0 | 200 n=1 | — |
| v1 | update | treatments | upper | 200 n=2 edited=false | 200 n=1 edited=true | — |
| v1 | delete | treatments | upper | 200 n=1 | 200 n=0 | — |
| v1 | create | devicestatus | lower | 200 [string] | 200 [ObjectId] | — |
| v1 | create | devicestatus | upper | 200 [string] | 200 [ObjectId] | — |
| v1 | resend | devicestatus | oid | 200 [ObjectId,string] | 500 [ObjectId] | — |
| v1 | resend | devicestatus | oidU | 200 [ObjectId,string] | 500 [ObjectId] | — |
| v1 | resend | devicestatus | lower | 500 [string] | 200 [ObjectId,string] | 500 [string] |
| v1 | find | devicestatus | lower | 200 n=0 | 200 n=1 | — |
| v1 | delete | devicestatus | lower | 200 n=1 | 200 n=0 | — |
| v1 | resend | devicestatus | upper | 500 [string] | 200 [ObjectId,string] | 500 [string] |
| v1 | find | devicestatus | upper | 200 n=0 | 200 n=1 | — |
| v1 | delete | devicestatus | upper | 200 n=1 | 200 n=0 | — |
| v1 | create | profile | lower | 200 [string] | 200 [ObjectId] | — |
| v1 | create | profile | upper | 200 [string] | 200 [ObjectId] | — |
| v1 | resend | profile | oid | 200 [ObjectId,string] | 500 [ObjectId] | — |
| v1 | resend | profile | oidU | 200 [ObjectId,string] | 500 [ObjectId] | — |
| v1 | find | profile | lower | 200 n=0 | 200 n=1 | — |
| v1 | update | profile | lower | 200 n=2 edited=false | 200 n=1 edited=true | — |
| v1 | delete | profile | lower | 200 n=1 | 200 n=0 | — |
| v1 | find | profile | upper | 200 n=0 | 200 n=1 | — |
| v1 | update | profile | upper | 200 n=2 edited=false | 200 n=1 edited=true | — |
| v1 | delete | profile | upper | 200 n=1 | 200 n=0 | — |
| v1 | create | food | lower | 200 [string] | 200 [ObjectId] | — |
| v1 | create | food | upper | 200 [string] | 200 [ObjectId] | — |
| v1 | resend | food | oid | 200 [ObjectId,string] | 200 [ObjectId] | — |
| v1 | resend | food | oidU | 200 [ObjectId,string] | 200 [ObjectId] | — |
| v1 | resend | food | lower | 200 [string] | 200 [ObjectId] | — |
| v1 | update | food | lower | 200 n=2 edited=false | 200 n=1 edited=true | — |
| v1 | delete | food | lower | 200 n=1 | 200 n=0 | — |
| v1 | resend | food | upper | 200 [string] | 200 [ObjectId] | — |
| v1 | update | food | upper | 200 n=2 edited=false | 200 n=1 edited=true | — |
| v1 | delete | food | upper | 200 n=1 | 200 n=0 | — |
| v1 | create | activity | lower | 200 [string] | 200 [ObjectId] | — |
| v1 | create | activity | upper | 200 [string] | 200 [ObjectId] | — |
| v1 | resend | activity | oid | 200 [ObjectId,string] | 200 [ObjectId] | — |
| v1 | resend | activity | oidU | 200 [ObjectId,string] | 200 [ObjectId] | — |
| v1 | resend | activity | lower | 200 [string] | 200 [ObjectId] | — |
| v1 | find | activity | lower | 200 n=0 | 200 n=1 | — |
| v1 | update | activity | lower | 200 n=2 edited=false | 200 n=1 edited=true | — |
| v1 | delete | activity | lower | 200 n=1 | 200 n=0 | — |
| v1 | resend | activity | upper | 200 [string] | 200 [ObjectId] | — |
| v1 | find | activity | upper | 200 n=0 | 200 n=1 | — |
| v1 | update | activity | upper | 200 n=2 edited=false | 200 n=1 edited=true | — |
| v1 | delete | activity | upper | 200 n=1 | 200 n=0 | — |
| v3 | get | entries | lower | 404 | 200 | — |
| v3 | put | entries | lower | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | entries | lower | 404 n=1 | 200 n=0 | — |
| v3 | resend | entries | lower | 500 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | entries | upper | 404 | 200 | — |
| v3 | put | entries | upper | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | entries | upper | 404 n=1 | 200 n=0 | — |
| v3 | resend | entries | upper | 500 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | entries | uuid | 404 | = observed | 200 |
| v3 | put | entries | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | entries | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | entries | uuid | 500 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | treatments | lower | 404 | 200 | — |
| v3 | put | treatments | lower | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | treatments | lower | 404 n=1 | 200 n=0 | — |
| v3 | resend | treatments | lower | 500 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | treatments | upper | 404 | 200 | — |
| v3 | put | treatments | upper | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | treatments | upper | 404 n=1 | 200 n=0 | — |
| v3 | resend | treatments | upper | 500 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | treatments | uuid | 404 | = observed | 200 |
| v3 | put | treatments | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | treatments | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | treatments | uuid | 500 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | devicestatus | lower | 404 | 200 | — |
| v3 | put | devicestatus | lower | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | devicestatus | lower | 404 n=1 | 200 n=0 | — |
| v3 | resend | devicestatus | lower | 500 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | devicestatus | upper | 404 | 200 | — |
| v3 | put | devicestatus | upper | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | devicestatus | upper | 404 n=1 | 200 n=0 | — |
| v3 | resend | devicestatus | upper | 500 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | devicestatus | uuid | 404 | = observed | 200 |
| v3 | put | devicestatus | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | devicestatus | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | devicestatus | uuid | 500 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | profile | lower | 404 | 200 | — |
| v3 | put | profile | lower | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | profile | lower | 404 n=1 | 200 n=0 | — |
| v3 | resend | profile | lower | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | profile | upper | 404 | 200 | — |
| v3 | put | profile | upper | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | profile | upper | 404 n=1 | 200 n=0 | — |
| v3 | resend | profile | upper | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | profile | uuid | 404 | = observed | 200 |
| v3 | put | profile | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | profile | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | profile | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | get | food | lower | 404 | 200 | — |
| v3 | put | food | lower | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | food | lower | 404 n=1 | 200 n=0 | — |
| v3 | resend | food | lower | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | food | upper | 404 | 200 | — |
| v3 | put | food | upper | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | delete | food | upper | 404 n=1 | 200 n=0 | — |
| v3 | resend | food | upper | 201 n=2 edited=false | 200 n=1 edited=true | — |
| v3 | get | food | uuid | 404 | = observed | 200 |
| v3 | put | food | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| v3 | delete | food | uuid | 404 n=1 | = observed | 200 n=0 |
| v3 | resend | food | uuid | 201 n=2 edited=false | = observed | 200 n=1 edited=true |
| ws | create | entries | lower | [string] | [ObjectId] | — |
| ws | create | entries | upper | [string] | [ObjectId] | — |
| ws | resend | entries | oid | n=2 | n=1 | — |
| ws | resend | entries | oidU | n=2 | n=1 | — |
| ws | update | entries | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | entries | lower | success n=1 | success n=0 | — |
| ws | update | entries | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | entries | upper | success n=1 | success n=0 | — |
| ws | create | treatments | lower | [string] | [ObjectId] | — |
| ws | create | treatments | upper | [string] | [ObjectId] | — |
| ws | update | treatments | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | treatments | lower | success n=1 | success n=0 | — |
| ws | update | treatments | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | treatments | upper | success n=1 | success n=0 | — |
| ws | create | devicestatus | lower | [string] | [ObjectId] | — |
| ws | create | devicestatus | upper | [string] | [ObjectId] | — |
| ws | update | devicestatus | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | devicestatus | lower | success n=1 | success n=0 | — |
| ws | update | devicestatus | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | devicestatus | upper | success n=1 | success n=0 | — |
| ws | create | profile | lower | [string] | [ObjectId] | — |
| ws | create | profile | upper | [string] | [ObjectId] | — |
| ws | update | profile | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | profile | lower | success n=1 | success n=0 | — |
| ws | update | profile | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | profile | upper | success n=1 | success n=0 | — |
| ws | create | food | lower | [string] | [ObjectId] | — |
| ws | create | food | upper | [string] | [ObjectId] | — |
| ws | resend | food | oid | n=2 | n=1 | — |
| ws | resend | food | oidU | n=2 | n=1 | — |
| ws | update | food | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | food | lower | success n=1 | success n=0 | — |
| ws | update | food | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | food | upper | success n=1 | success n=0 | — |
| ws | create | activity | lower | [string] | [ObjectId] | — |
| ws | create | activity | upper | [string] | [ObjectId] | — |
| ws | resend | activity | oid | n=2 | n=1 | — |
| ws | resend | activity | oidU | n=2 | n=1 | — |
| ws | update | activity | lower | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | activity | lower | success n=1 | success n=0 | — |
| ws | update | activity | upper | success n=1 edited=false | success n=1 edited=true | — |
| ws | remove | activity | upper | success n=1 | success n=0 | — |

</details>

## 3. The fixes

### 3.1 Entry re-POST with its own `_id` (commit 1, `4b41bcf8`)

Reproduced on dev and `597e2899`: an entry POSTed with the hex `_id` of an entry stored as the
string at the same `sysTime` and `type` answers 500 ("Performing an update on the path '_id' would
modify the immutable field '_id'"); so does a POST whose hex `_id` differs from the ObjectId of the
entry stored at that time and type. The same POST without `_id` answers 200 and updates the entry.

`lib/server/entries.js` `create()` now writes the sent `_id` with `$setOnInsert` and leaves it out
of `$set`: a new entry is stored with that `_id` (ObjectId, from `toStoredId`), and a matched entry
keeps its own `_id`, as with a POST without `_id`. This is the existing dedup rule for entries
(sysTime + type is the key; a different UUID at the same time deduplicates, `TEST-ENTRY-UUID-003`)
applied to a hex `_id`. A first version kept `$set` of `_id` when the upsert filter was on `_id`
(an entry without `type`); a control for that case passes with and without the condition, so the
condition was dropped.

### 3.2 Upper-case ids on `/entries/:spec` (commit 2, `a612a26f`)

`lib/api/entries/index.js` had `ID_PATTERN = /^[a-f\d]{24}$/`. `GET /entries/<UPPER>` answered
`[]` and `DELETE /entries/<UPPER>` removed nothing (reproduced), because the id was taken for an
entry `type`. It now uses `isHexId` from `lib/server/object-id-forms.js`.

Upper case is accepted because every other path already did: `lib/server/query.js` (`find[_id]`),
`lib/api/shared/objectid-validation.js` (devicestatus, food, activity, profile routes),
`lib/server/websocket.js`, API v3 (`isHexId` in its filters), and `new ObjectId()` itself. The
cost is that an entry `type` spelled as 24 upper-case hex characters can no longer be named in
the path, as a lower-case one already could not. The shared
validation module now imports the helper's rule instead of its own pattern; what it accepts is
unchanged.

### 3.3 Websocket (commit 3, `12c01268`)

Reproduced on dev and `597e2899` (§2.1): `dbAdd` stored a hex `_id` as the string in every
collection; `dbUpdate`, `dbUpdateUnset` and `dbRemove` converted a hex `_id` to ObjectId and so
missed a string-stored record while replying `success`; a re-sent record stored with an ObjectId
`_id` got a string copy in entries, food and activity (the collections with no field dedup); the
similar-treatment dedup converted the matched record's stored hex-string `_id` to an ObjectId and
updated nothing.

`lib/server/websocket.js` now:

- `dbAdd`: `storeIdAsObjectId` stores a 24-hex `_id` as the ObjectId it names, unless the same id
  is already stored as a string, in which case the stored value is used and the insert collides
  with that record as a re-send always has (reply `[]`). One indexed `findOne`, only for a record
  carrying a 24-hex `_id`. Which socket clients send their own hex `_id` was not established.
- `dbUpdate`, `dbUpdateUnset`, `dbRemove`: `idMatch` gives `{_id: {$in: idForms(id)}}` for a 24-hex
  id and writes with `updateMany` / `deleteMany`, so an ObjectId copy and a string copy of one id
  are both reached; any other id keeps `{_id: id}` with `updateOne` / `deleteOne`. The split keeps
  `tests/websocket.input-validation.test.js` unmodified: its fake collection has only `updateOne`
  and `deleteOne` and its ids are custom strings (a first version used `updateMany` for every id
  and failed one of its tests).
- the similar-treatment update uses `similar._id` as stored.

A custom non-hex `_id` is kept exactly as given, as `tests/websocket.shape-handling.test.js`
requires.

This commit was rebuilt once: `f433dc16` had the `require` of the helper next to the
`forwarded-for` lines that #8754 replaces, and conflicted with #8754 and `rc/15.0.9-additions-e`.
`12c01268` moves that one line above `var times`; nothing else differs (`git diff f433dc16
12c01268`: one line moved).

### 3.4 Not fixed: API v3 and a non-hex `_id`

A fix was written and reverted because it changes tested behaviour (decision D2, §5).

## 4. Tests, break-its, suites

New test files and red counts (Node 20.20.0, `mongo:7`):

| file | tests | red on `597e2899` | red on `1f9a9d10` | the passing ones |
|---|---:|---:|---:|---|
| `tests/api.entries.repost-with-id.test.js` | 8 | 4 | 4 | re-POST with the stored `_id`; new entry; entry without `type`; POST without `_id` |
| `tests/api.entries.upper-case-id.test.js` | 5 | 3 | 3 | `GET /entries/<lower>`; `/entries/sgv` is a model |
| `tests/websocket.object-id.test.js` | 13 | 10 | 10 | re-send of a string-stored record, lower and upper case; `dbUpdate` of an ObjectId record |
| `tests/api.crud-by-id.matrix.test.js` | 336 | 48 | 142 | §2 |

Break-its, one part of the fix removed at a time, the commit's own test file unless stated:

| commit | removed | red |
|---|---|---:|
| 1 | `$setOnInsert` of the sent `_id` (back to `$set: doc`) | 4 of 7 (run before the no-`type` control was added) |
| 2 | `/entries/:spec` back to the lower-case pattern | 3 of 5 |
| 2 | shared v1 `_id` check narrowed to lower case (other-collections, profiles object-id and upper-case files) | 4 of 49 |
| 3 | `dbAdd` conversion | 3 of 13 |
| 3 | `dbAdd` "already stored as a string" guard | 2 of 13 |
| 3 | `idMatch` either-form filter (back to the ObjectId) | 6 of 13 |
| 3 | `dbUpdate` `updateMany` (back to `updateOne`) | 1 of 13 |
| 3 | `dbUpdateUnset` `updateMany` | 1 of 13 |
| 3 | `dbRemove` `deleteMany` | 1 of 13 |
| 3 | similar-treatment update by the stored `_id` | 1 of 13 |

Commit 3's break-its were run on `f433dc16` (same hunks, one `require` line placed differently).
The `dbUpdateUnset` twin test was added so that its `updateMany` branch has a test that can fail.

Full suite (`npm test`, `mongo:7` in container `crud-mongo`), passing / failing / pending:

| tree | Node 20.20.0 | Node 22.23.2 | new tests |
|---|---|---|---:|
| `bf/object-id-consistency` `597e2899` | 2470 / 0 / 3 | 2470 / 0 / 3 | — |
| 1 `4b41bcf8` | 2478 / 0 / 3 | 2478 / 0 / 3 | +8 |
| 2 `a612a26f` | 2483 / 0 / 3 | 2483 / 0 / 3 | +5 |
| 3 `f433dc16` (before the rebuild) | 2496 / 0 / 3 | 2496 / 0 / 3 | +13 |
| 3 `12c01268` | 2496 / 0 / 3 | 2496 / 0 / 3 | +13 |
| 4 `c721e202` (tip) | 2832 / 0 / 3 | 2832 / 0 / 3 | +336 |

Every step is exactly the new test file; no existing test changed.

## 5. Decisions for the maintainer

**D1. A devicestatus re-sent with the `_id` of a string-stored copy is stored beside it.**
`597e2899` commit c converts on create with no check for the string form (comment in
`lib/server/devicestatus.js`); dev answers 500 and keeps one record. Measured: matrix cells
`v1 resend devicestatus lower/upper` → `200 [ObjectId,string]`. Options:

- keep: no read added to devicestatus creates; the connector's in-process output does not re-send
  (measured in `object-id-other-collections-2026-09-23.md` §4); `find[_id]` and DELETE reach both
  copies.
- add BF-99's guard: one `find({_id: {$in: <string forms>}}, {_id: 1})` per batch that carries hex
  `_id`s (every Nightscout-to-Nightscout connector batch), keeping the string form for ids already
  stored as strings, so the re-send is refused as on dev and as profile does. The websocket's
  `dbAdd` in this branch already does this per record.

**D2. API v3 cannot address a v1 record whose `_id` is a non-hex string.** Such records exist where
treatments or entries were stored with a UUID `_id` up to 15.0.6, and where the websocket stored a
custom `_id` (it keeps them as given). v3 lists them with `identifier` = that `_id`
(`normalizeDoc`), and `lib/api3/swagger.yaml` line 1112 says that identifier is used "when reading
or addressing these documents", but `filterForOne` and `identifyingFilter` look a non-hex
identifier up in `identifier` only. Measured on this branch (20 matrix cells, kept):

| v3 operation | treatments, entries, devicestatus | profile, food |
|---|---|---|
| GET `/<id>` | 404 | 404 |
| PUT `/<id>` | 201, second record | 201, second record |
| DELETE `/<id>?permanent=true` | 404, record kept | 404, record kept |
| POST with that `identifier` | **500** and a second record (traced for treatments: the dedup fallback fields find the record, the replace by identifier misses it, the upsert inserts a copy, and `lib/api3/generic/update/replace.js:41` throws "empty matchedCount") | 201, second record |

A fix exists (reverted, not committed): in both filters, a non-hex string identifier also matches
`{_id: {$eq: identifier}}` (for `identifyingFilter`, with `identifier: {$exists: false}`). With it,
all 20 cells give the consistent outcome (200 / one record), its 11-test file is 8 red / 3 green on
this branch, and the rest of `tests/api3*.test.js` passes except two tests in
`tests/api3.storage.modify.test.js` (lines 33, 49, 55) that assert the filter for identifier
`'record-1'` is exactly `{$or: [{identifier: {$eq: 'record-1'}}]}`. The change would update those
expectations. Cost: one more `$or` branch on the indexed `_id` for each v3 lookup by a non-hex
identifier. The diff:

```diff
--- a/lib/api3/storage/mongoCollection/utils.js
+++ b/lib/api3/storage/mongoCollection/utils.js
@@ filterForOne
   if (idForms.isHexId(identifier)) {
     idForms.idForms(identifier).forEach(function (form) {
       filterOpts.push({ _id: { $eq: form } });
     });
+  } else if (typeof identifier === 'string') {
+    filterOpts.push({ _id: { $eq: identifier } });
   }
@@ identifyingFilter
     if (idForms.isHexId(identifier)) {
       idForms.idForms(identifier).forEach(function (form) {
         filterItems.push({ identifier: { $exists: false }, _id: { $eq: form } });
       });
+    } else if (typeof identifier === 'string') {
+      filterItems.push({ identifier: { $exists: false }, _id: { $eq: identifier } });
     }
```

**D3. An entry POST that matches a stored entry reports the sent `_id`, not the stored one.** After
commit 1, a POST whose hex `_id` differs from the entry stored at that time and type updates that
entry, which keeps its `_id`; the response body echoes the sent `_id` (measured: sent `…a03`,
stored `…b03`). A matched POST without `_id` answers `_id: null`; before commit 1 the same request
answered 500. Options: leave it (the response `_id` of a matched entry was never the stored one);
read the stored `_id` back for matched entries (one read per batch with matches); or omit `_id` from
the response for matched entries.

**D4. A string `_id` stored in upper case is found only when asked for in upper case (or through
its ObjectId form).** `idForms(id)` is `[ObjectId, lower-case hex, the string as given]`, so asking
with the lower-case hex misses an upper-case string on disk, on every path that uses the helper
(v1 `find[_id]`, DELETE, the string-copy delete after PUT, API v3, and now the websocket). Adding the
upper-case spelling to `idForms` would close it and changes the exact lists
`tests/object-id-forms.test.js` asserts (lines 57, 62, 66, 74). Upper-case string `_id`s exist only
where a client sent upper-case hex before the collection converted; no such client is known.

Stated, not decisions (deliberate and tested): a non-hex `_id` is moved to `identifier` by v1
treatments and entries, refused with 400 by the other v1 routes, and kept as given by the
websocket; API v3 refuses a PUT that names an ObjectId record by its upper-case hex (400, the
identifier is immutable), while GET and DELETE by that spelling work.

## 6. Merges

`git merge-tree --write-tree` of `c721e202` against each open 15.0.9 head:

| head | result |
|---|---|
| #8748 `d19043b2` | clean |
| #8749 `46b20b38` | clean |
| #8751 `b5038500` | clean |
| #8753 `e6a50e9a` | clean |
| #8754 `0a74ef4e` | clean (`f433dc16`, before the rebuild: conflict in `lib/server/websocket.js`) |
| #8755 `92544d8f` | clean |
| #8756 `83cfff14` | clean |
| #8757 `5d342ac1` (`bf3/mmconnect-deprecation-warning`) | clean |
| `rc/15.0.9-additions-e` `1b1977e0` | clean (`f433dc16`: conflict in `lib/server/websocket.js`) |
| `bf/profile-object-id` `9b8cc2f9` | conflict, `lib/server/profile.js`, inherited from `597e2899` (land one) |
| `bf/object-id-other-collections` `2fac53f5` | clean |
| `bf/api3-string-id` `7295bc8c` | clean |

The merged tree with `rc/15.0.9-additions-e` (which contains #8754), written with `git read-tree`
into a scratch worktree, passes `tests/websocket*.test.js`, the matrix and the two entries files
(396 / 0; Node 20.20.0, with the node_modules of `origin/dev`'s lock; `rc/15.0.9-additions-e`
changes `package.json`). The full suite was not run on merged trees.

## 7. Not changed

- No boot migration: string-`_id` records stay as they are until written, edited or deleted.
- API v3 (D2), devicestatus v1 create (D1), the helper's forms (D4).
- `chore/nightscout-modernization` was not examined for these three defects.
