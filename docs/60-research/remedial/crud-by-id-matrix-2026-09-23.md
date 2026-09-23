# CRUD by `_id`: a matrix over every collection, stored `_id` form, API v1, API v3 and the websocket

*Contributor-facing. Measured 2026-09-23 against `origin/dev` `1f9a9d10` (15.0.9),
`bf/object-id-consistency` `597e2899`, and `bf/object-id-crud` `6d120fa2` (eight commits on
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
| 5 | `44ac9047` | API v3 could not read, replace or delete a record whose `_id` is a non-hex string (decision D2) |
| 6 | `18b09df7` | an entries POST that matched a stored reading answered the sent `_id`, or `null`, instead of the stored `_id` (D3) |
| 7 | `ad973110` | a devicestatus re-sent with the `_id` of a string-stored copy was stored beside it (D1) |
| 8 | `6d120fa2` | comment only: the helper header states the upper-case string limit (D4) |

Commits 5 to 8 apply the maintainer's decisions of 2026-09-23 on D1 to D4 (§5).

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

The matrix observes what is stored; the `_id` an entries POST answers with (commit 6) is covered in
`tests/api.entries.repost-with-id.test.js`.

The expected outcome of every cell is written in the test (`EXPECT`) with its reason. Deliberate
differences are expected outcomes, not failures:

| rule | cells |
|---|---|
| a UUID `_id` moves to `identifier` (REQ-SYNC-072, `UUID_HANDLING` on by default) | v1 create, treatments and entries |
| a non-hex `_id` is refused with 400 | v1 create, re-send, PUT, DELETE for devicestatus, profile, food, activity |
| `/entries/:spec` takes a 24-hex id; anything else is an entry type | v1 GET and DELETE `/entries/<uuid>` (`find[_id]` finds it) |
| a re-sent profile or devicestatus `_id` is refused as a duplicate (500), whichever form it is stored in | v1 re-send, profile (BF-99) and devicestatus (commit 7) |
| the websocket keeps a non-hex `_id` as given (`tests/websocket.shape-handling.test.js`) | ws create, `uuid` |
| API v3 identifiers are immutable: a PUT naming an ObjectId record by its upper-case hex is refused (400) | v3 PUT, `oidU` |

`CRUD_MATRIX_OUT=<file>` writes every cell as JSON.

## 2. Results

The matrix file from `6d120fa2` copied into each tree, Node 20.20.0:

| tree | `mongo:7` passing / failing | MongoDB 4.4 passing / failing |
|---|---|---|
| `origin/dev` `1f9a9d10` | 176 / 160 | 176 / 160 |
| `bf/object-id-consistency` `597e2899` | 266 / 70 | 266 / 70 |
| `bf/object-id-crud` `6d120fa2` | 336 / 0 | 336 / 0 |

MongoDB 4.4 and `mongo:7` gave the same outcome in all 336 cells on each of the three trees.

Per collection and operation (of the stored forms, how many give the expected outcome):

**`origin/dev` `1f9a9d10`**

| api op | entries | treatments | devicestatus | profile | food | activity |
|---|---|---|---|---|---|---|
| v1 create | 3/3 ok | 3/3 ok | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** |
| v1 resend | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **4/5 wrong** | **4/5 wrong** |
| v1 find | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | — | **2/5 wrong** |
| v1 get | **3/5 wrong** | — | — | — | — | — |
| v1 update | — | **2/5 wrong** | — | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |
| v1 delete | **3/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |
| v3 get | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | — |
| v3 put | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | — |
| v3 delete | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | — |
| v3 resend | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | **3/5 wrong** | — |
| ws create | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** |
| ws resend | **2/5 wrong** | 5/5 ok | 5/5 ok | 5/5 ok | **2/5 wrong** | **2/5 wrong** |
| ws update | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |
| ws remove | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |

**`bf/object-id-consistency` `597e2899`**

| api op | entries | treatments | devicestatus | profile | food | activity |
|---|---|---|---|---|---|---|
| v1 create | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok |
| v1 resend | **2/5 wrong** | 5/5 ok | **2/5 wrong** | 5/5 ok | 5/5 ok | 5/5 ok |
| v1 find | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | — | 5/5 ok |
| v1 get | **2/5 wrong** | — | — | — | — | — |
| v1 update | — | 5/5 ok | — | 5/5 ok | 5/5 ok | 5/5 ok |
| v1 delete | **2/5 wrong** | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |
| v3 get | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | — |
| v3 put | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | — |
| v3 delete | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | — |
| v3 resend | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | **1/5 wrong** | — |
| ws create | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** | **2/3 wrong** |
| ws resend | **2/5 wrong** | 5/5 ok | 5/5 ok | 5/5 ok | **2/5 wrong** | **2/5 wrong** |
| ws update | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |
| ws remove | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** | **2/5 wrong** |

**`bf/object-id-crud` `6d120fa2`**

| api op | entries | treatments | devicestatus | profile | food | activity |
|---|---|---|---|---|---|---|
| v1 create | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok |
| v1 resend | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |
| v1 find | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | — | 5/5 ok |
| v1 get | 5/5 ok | — | — | — | — | — |
| v1 update | — | 5/5 ok | — | 5/5 ok | 5/5 ok | 5/5 ok |
| v1 delete | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |
| v3 get | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | — |
| v3 put | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | — |
| v3 delete | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | — |
| v3 resend | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | — |
| ws create | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok | 3/3 ok |
| ws resend | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |
| ws update | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |
| ws remove | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok | 5/5 ok |

The devicestatus re-send of a string-stored `_id` is right on dev (refused, one record), wrong on
`597e2899` (a second copy) and right again from commit 7.

### 2.1 Cells that differ on `bf/object-id-consistency` `597e2899`

| api | op | collection | stored/sent form | observed | expected |
|---|---|---|---|---|---|
| v1 | get | entries | oidU | 200 n=0 | 200 n=1 |
| v1 | delete | entries | oidU | 200 n=1 | 200 n=0 |
| v1 | resend | entries | lower | 500 [string] | 200 [string] |
| v1 | resend | entries | upper | 500 [string] | 200 [string] |
| v1 | get | entries | upper | 200 n=0 | 200 n=1 |
| v1 | delete | entries | upper | 200 n=1 | 200 n=0 |
| v1 | resend | devicestatus | lower | 200 [ObjectId,string] | 500 [string] |
| v1 | resend | devicestatus | upper | 200 [ObjectId,string] | 500 [string] |
| v3 | get | entries | uuid | 404 | 200 |
| v3 | put | entries | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | entries | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | entries | uuid | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | treatments | uuid | 404 | 200 |
| v3 | put | treatments | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | treatments | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | treatments | uuid | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | devicestatus | uuid | 404 | 200 |
| v3 | put | devicestatus | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | devicestatus | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | devicestatus | uuid | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | profile | uuid | 404 | 200 |
| v3 | put | profile | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | profile | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | profile | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | food | uuid | 404 | 200 |
| v3 | put | food | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | food | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | food | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| ws | create | entries | lower | [string] | [ObjectId] |
| ws | create | entries | upper | [string] | [ObjectId] |
| ws | resend | entries | oid | n=2 | n=1 |
| ws | resend | entries | oidU | n=2 | n=1 |
| ws | update | entries | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | entries | lower | success n=1 | success n=0 |
| ws | update | entries | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | entries | upper | success n=1 | success n=0 |
| ws | create | treatments | lower | [string] | [ObjectId] |
| ws | create | treatments | upper | [string] | [ObjectId] |
| ws | update | treatments | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | treatments | lower | success n=1 | success n=0 |
| ws | update | treatments | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | treatments | upper | success n=1 | success n=0 |
| ws | create | devicestatus | lower | [string] | [ObjectId] |
| ws | create | devicestatus | upper | [string] | [ObjectId] |
| ws | update | devicestatus | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | devicestatus | lower | success n=1 | success n=0 |
| ws | update | devicestatus | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | devicestatus | upper | success n=1 | success n=0 |
| ws | create | profile | lower | [string] | [ObjectId] |
| ws | create | profile | upper | [string] | [ObjectId] |
| ws | update | profile | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | profile | lower | success n=1 | success n=0 |
| ws | update | profile | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | profile | upper | success n=1 | success n=0 |
| ws | create | food | lower | [string] | [ObjectId] |
| ws | create | food | upper | [string] | [ObjectId] |
| ws | resend | food | oid | n=2 | n=1 |
| ws | resend | food | oidU | n=2 | n=1 |
| ws | update | food | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | food | lower | success n=1 | success n=0 |
| ws | update | food | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | food | upper | success n=1 | success n=0 |
| ws | create | activity | lower | [string] | [ObjectId] |
| ws | create | activity | upper | [string] | [ObjectId] |
| ws | resend | activity | oid | n=2 | n=1 |
| ws | resend | activity | oidU | n=2 | n=1 |
| ws | update | activity | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | activity | lower | success n=1 | success n=0 |
| ws | update | activity | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | activity | upper | success n=1 | success n=0 |

### 2.2 Cells that differ on `origin/dev` `1f9a9d10`

160 cells; 92 of them are fixed by `597e2899` and the other 68 are §2.1 less the two devicestatus
re-send cells, which dev gets right.

<details><summary>All 160 rows</summary>

| api | op | collection | stored/sent form | observed | expected |
|---|---|---|---|---|---|
| v1 | get | entries | oidU | 200 n=0 | 200 n=1 |
| v1 | delete | entries | oidU | 200 n=1 | 200 n=0 |
| v1 | resend | entries | lower | 500 [string] | 200 [string] |
| v1 | find | entries | lower | 200 n=0 | 200 n=1 |
| v1 | get | entries | lower | 500 n=0 | 200 n=1 |
| v1 | delete | entries | lower | 200 n=1 | 200 n=0 |
| v1 | resend | entries | upper | 500 [string] | 200 [string] |
| v1 | find | entries | upper | 200 n=0 | 200 n=1 |
| v1 | get | entries | upper | 200 n=0 | 200 n=1 |
| v1 | delete | entries | upper | 200 n=1 | 200 n=0 |
| v1 | resend | treatments | lower | 200 [ObjectId,string] | 200 [ObjectId] |
| v1 | find | treatments | lower | 200 n=0 | 200 n=1 |
| v1 | update | treatments | lower | 200 n=2 edited=false | 200 n=1 edited=true |
| v1 | delete | treatments | lower | 200 n=1 | 200 n=0 |
| v1 | resend | treatments | upper | 200 [ObjectId,string] | 200 [ObjectId] |
| v1 | find | treatments | upper | 200 n=0 | 200 n=1 |
| v1 | update | treatments | upper | 200 n=2 edited=false | 200 n=1 edited=true |
| v1 | delete | treatments | upper | 200 n=1 | 200 n=0 |
| v1 | create | devicestatus | lower | 200 [string] | 200 [ObjectId] |
| v1 | create | devicestatus | upper | 200 [string] | 200 [ObjectId] |
| v1 | resend | devicestatus | oid | 200 [ObjectId,string] | 500 [ObjectId] |
| v1 | resend | devicestatus | oidU | 200 [ObjectId,string] | 500 [ObjectId] |
| v1 | find | devicestatus | lower | 200 n=0 | 200 n=1 |
| v1 | delete | devicestatus | lower | 200 n=1 | 200 n=0 |
| v1 | find | devicestatus | upper | 200 n=0 | 200 n=1 |
| v1 | delete | devicestatus | upper | 200 n=1 | 200 n=0 |
| v1 | create | profile | lower | 200 [string] | 200 [ObjectId] |
| v1 | create | profile | upper | 200 [string] | 200 [ObjectId] |
| v1 | resend | profile | oid | 200 [ObjectId,string] | 500 [ObjectId] |
| v1 | resend | profile | oidU | 200 [ObjectId,string] | 500 [ObjectId] |
| v1 | find | profile | lower | 200 n=0 | 200 n=1 |
| v1 | update | profile | lower | 200 n=2 edited=false | 200 n=1 edited=true |
| v1 | delete | profile | lower | 200 n=1 | 200 n=0 |
| v1 | find | profile | upper | 200 n=0 | 200 n=1 |
| v1 | update | profile | upper | 200 n=2 edited=false | 200 n=1 edited=true |
| v1 | delete | profile | upper | 200 n=1 | 200 n=0 |
| v1 | create | food | lower | 200 [string] | 200 [ObjectId] |
| v1 | create | food | upper | 200 [string] | 200 [ObjectId] |
| v1 | resend | food | oid | 200 [ObjectId,string] | 200 [ObjectId] |
| v1 | resend | food | oidU | 200 [ObjectId,string] | 200 [ObjectId] |
| v1 | resend | food | lower | 200 [string] | 200 [ObjectId] |
| v1 | update | food | lower | 200 n=2 edited=false | 200 n=1 edited=true |
| v1 | delete | food | lower | 200 n=1 | 200 n=0 |
| v1 | resend | food | upper | 200 [string] | 200 [ObjectId] |
| v1 | update | food | upper | 200 n=2 edited=false | 200 n=1 edited=true |
| v1 | delete | food | upper | 200 n=1 | 200 n=0 |
| v1 | create | activity | lower | 200 [string] | 200 [ObjectId] |
| v1 | create | activity | upper | 200 [string] | 200 [ObjectId] |
| v1 | resend | activity | oid | 200 [ObjectId,string] | 200 [ObjectId] |
| v1 | resend | activity | oidU | 200 [ObjectId,string] | 200 [ObjectId] |
| v1 | resend | activity | lower | 200 [string] | 200 [ObjectId] |
| v1 | find | activity | lower | 200 n=0 | 200 n=1 |
| v1 | update | activity | lower | 200 n=2 edited=false | 200 n=1 edited=true |
| v1 | delete | activity | lower | 200 n=1 | 200 n=0 |
| v1 | resend | activity | upper | 200 [string] | 200 [ObjectId] |
| v1 | find | activity | upper | 200 n=0 | 200 n=1 |
| v1 | update | activity | upper | 200 n=2 edited=false | 200 n=1 edited=true |
| v1 | delete | activity | upper | 200 n=1 | 200 n=0 |
| v3 | get | entries | lower | 404 | 200 |
| v3 | put | entries | lower | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | entries | lower | 404 n=1 | 200 n=0 |
| v3 | resend | entries | lower | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | entries | upper | 404 | 200 |
| v3 | put | entries | upper | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | entries | upper | 404 n=1 | 200 n=0 |
| v3 | resend | entries | upper | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | entries | uuid | 404 | 200 |
| v3 | put | entries | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | entries | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | entries | uuid | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | treatments | lower | 404 | 200 |
| v3 | put | treatments | lower | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | treatments | lower | 404 n=1 | 200 n=0 |
| v3 | resend | treatments | lower | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | treatments | upper | 404 | 200 |
| v3 | put | treatments | upper | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | treatments | upper | 404 n=1 | 200 n=0 |
| v3 | resend | treatments | upper | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | treatments | uuid | 404 | 200 |
| v3 | put | treatments | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | treatments | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | treatments | uuid | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | devicestatus | lower | 404 | 200 |
| v3 | put | devicestatus | lower | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | devicestatus | lower | 404 n=1 | 200 n=0 |
| v3 | resend | devicestatus | lower | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | devicestatus | upper | 404 | 200 |
| v3 | put | devicestatus | upper | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | devicestatus | upper | 404 n=1 | 200 n=0 |
| v3 | resend | devicestatus | upper | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | devicestatus | uuid | 404 | 200 |
| v3 | put | devicestatus | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | devicestatus | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | devicestatus | uuid | 500 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | profile | lower | 404 | 200 |
| v3 | put | profile | lower | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | profile | lower | 404 n=1 | 200 n=0 |
| v3 | resend | profile | lower | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | profile | upper | 404 | 200 |
| v3 | put | profile | upper | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | profile | upper | 404 n=1 | 200 n=0 |
| v3 | resend | profile | upper | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | profile | uuid | 404 | 200 |
| v3 | put | profile | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | profile | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | profile | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | food | lower | 404 | 200 |
| v3 | put | food | lower | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | food | lower | 404 n=1 | 200 n=0 |
| v3 | resend | food | lower | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | food | upper | 404 | 200 |
| v3 | put | food | upper | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | food | upper | 404 n=1 | 200 n=0 |
| v3 | resend | food | upper | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | get | food | uuid | 404 | 200 |
| v3 | put | food | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| v3 | delete | food | uuid | 404 n=1 | 200 n=0 |
| v3 | resend | food | uuid | 201 n=2 edited=false | 200 n=1 edited=true |
| ws | create | entries | lower | [string] | [ObjectId] |
| ws | create | entries | upper | [string] | [ObjectId] |
| ws | resend | entries | oid | n=2 | n=1 |
| ws | resend | entries | oidU | n=2 | n=1 |
| ws | update | entries | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | entries | lower | success n=1 | success n=0 |
| ws | update | entries | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | entries | upper | success n=1 | success n=0 |
| ws | create | treatments | lower | [string] | [ObjectId] |
| ws | create | treatments | upper | [string] | [ObjectId] |
| ws | update | treatments | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | treatments | lower | success n=1 | success n=0 |
| ws | update | treatments | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | treatments | upper | success n=1 | success n=0 |
| ws | create | devicestatus | lower | [string] | [ObjectId] |
| ws | create | devicestatus | upper | [string] | [ObjectId] |
| ws | update | devicestatus | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | devicestatus | lower | success n=1 | success n=0 |
| ws | update | devicestatus | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | devicestatus | upper | success n=1 | success n=0 |
| ws | create | profile | lower | [string] | [ObjectId] |
| ws | create | profile | upper | [string] | [ObjectId] |
| ws | update | profile | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | profile | lower | success n=1 | success n=0 |
| ws | update | profile | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | profile | upper | success n=1 | success n=0 |
| ws | create | food | lower | [string] | [ObjectId] |
| ws | create | food | upper | [string] | [ObjectId] |
| ws | resend | food | oid | n=2 | n=1 |
| ws | resend | food | oidU | n=2 | n=1 |
| ws | update | food | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | food | lower | success n=1 | success n=0 |
| ws | update | food | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | food | upper | success n=1 | success n=0 |
| ws | create | activity | lower | [string] | [ObjectId] |
| ws | create | activity | upper | [string] | [ObjectId] |
| ws | resend | activity | oid | n=2 | n=1 |
| ws | resend | activity | oidU | n=2 | n=1 |
| ws | update | activity | lower | success n=1 edited=false | success n=1 edited=true |
| ws | remove | activity | lower | success n=1 | success n=0 |
| ws | update | activity | upper | success n=1 edited=false | success n=1 edited=true |
| ws | remove | activity | upper | success n=1 | success n=0 |

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
applied to a hex `_id`.

### 3.2 Upper-case ids on `/entries/:spec` (commit 2, `a612a26f`)

`lib/api/entries/index.js` had `ID_PATTERN = /^[a-f\d]{24}$/`. `GET /entries/<UPPER>` answered
`[]` and `DELETE /entries/<UPPER>` removed nothing (reproduced), because the id was taken for an
entry `type`. It now uses `isHexId` from `lib/server/object-id-forms.js`.

Upper case is accepted because every other path already did: `lib/server/query.js` (`find[_id]`),
`lib/api/shared/objectid-validation.js` (devicestatus, food, activity, profile routes),
`lib/server/websocket.js`, API v3, and `new ObjectId()` itself. The cost is that an entry `type`
spelled as 24 upper-case hex characters can no longer be named in the path, as a lower-case one
already could not. The shared validation module now imports the helper's rule instead of its own
pattern; what it accepts is unchanged.

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
  and `deleteOne` and its ids are custom strings.
- the similar-treatment update uses `similar._id` as stored.

A custom non-hex `_id` is kept exactly as given, as `tests/websocket.shape-handling.test.js`
requires. This commit was rebuilt once: `f433dc16` placed the helper's `require` next to the
`forwarded-for` lines that #8754 replaces and conflicted with #8754 and `rc/15.0.9-additions-e`;
`12c01268` moves that one line.

### 3.4 API v3 and a non-hex `_id` (commit 5, `44ac9047`, D2)

Records can hold a non-hex string `_id`: a UUID in treatments or entries stored by 15.0.6 or
earlier, or a custom id the websocket keeps as given. v3 lists such a record with `identifier` =
that `_id` (`normalizeDoc`), and `lib/api3/swagger.yaml` line 1112 says that identifier is used
"when reading or addressing these documents", but `filterForOne` and `identifyingFilter` looked a
non-hex identifier up in `identifier` only. Measured on `597e2899` and `c721e202`:

| v3 operation | treatments, entries, devicestatus | profile, food |
|---|---|---|
| GET `/<id>` | 404 | 404 |
| PUT `/<id>` | 201, second record | 201, second record |
| DELETE `/<id>?permanent=true` | 404, record kept | 404, record kept |
| POST with that `identifier` | 500 and a second record (traced for treatments: the dedup fallback fields find the record, the replace by identifier misses it, the upsert inserts a copy, and `lib/api3/generic/update/replace.js:41` throws "empty matchedCount") | 201, second record |

In both filters a non-hex **string** identifier now also matches `{_id: {$eq: identifier}}` (for
`identifyingFilter`, with `identifier: {$exists: false}`), the same literal `$eq` as every other
branch. An identifier that is not a string (operator-shaped, such as `{$ne: null}`) gets no `_id`
branch, and its `identifier` branch is still a literal `$eq`
(`tests/api3.storage.utils.test.js` "treats an object-shaped identifier as a literal value",
unchanged, and two new assertions in `tests/api3.non-hex-id.test.js`); an operator-looking string such as `{"$ne":null}` is compared
literally in both branches, and `GET /api/v3/treatments/{"$ne":null}` answers 404 with records
present. `tests/api3.storage.modify.test.js` asserted the exact filter for the non-hex identifiers
`record-1` and `record-2` (three assertions, lines 33, 49, 55) and is updated to the new shape.

`explain('executionStats')` on `mongo:7`, each collection holding 5,000 documents with
`identifier` plus one with the UUID `_id`, with the indexes Nightscout creates at boot and API v3's
`identifier_1`. Dedup fields are v3's own (`lib/api3/generic/setup.js`):

| collection | filter | winning plan (flattened) | returned | docs examined | COLLSCAN |
|---|---|---|---:|---:|---|
| treatments | `filterForOne` | `SUBPLAN > FETCH > OR > [IXSCAN(_id_), IXSCAN(identifier_1)]` | 1 | 1 | no |
| treatments | `identifyingFilter` | `SUBPLAN > FETCH > OR > [FETCH > IXSCAN(_id_), IXSCAN(identifier_1)]` | 1 | 2 | no |
| treatments | `identifyingFilter` + dedup fields | `… OR > [FETCH > IXSCAN(_id_), FETCH > IXSCAN(eventType_1_created_at_-1_identifier_-1_date_-1), IXSCAN(identifier_1)]` | 1 | 3 | no |
| entries | `filterForOne` / `identifyingFilter` | as treatments | 1 | 1 / 2 | no |
| entries | + dedup fields | `… FETCH > IXSCAN(date_-1_identifier_-1_created_at_-1) …` | 1 | 3 | no |
| devicestatus | `filterForOne` / `identifyingFilter` | as treatments | 1 | 1 / 2 | no |
| devicestatus | + dedup fields | `… FETCH > IXSCAN(created_at_-1_identifier_-1_date_-1) …` | 1 | 3 | no |
| profile | `filterForOne` / `identifyingFilter` | as treatments | 1 | 1 / 2 | no |
| profile | + dedup fields | `… FETCH > IXSCAN(created_at_1) …` | 1 | 3 | no |
| food | `filterForOne` / `identifyingFilter` | as treatments | 1 | 1 / 2 | no |
| food | + dedup fields | `… FETCH > IXSCAN(identifier_1) …` | 1 | 3 | no |

### 3.5 Entries POST answers the stored `_id` (commit 6, `18b09df7`, D3)

After commit 1, a POST that matched a stored reading by `sysTime` + `type` was answered with the
`_id` the client sent (measured: sent `…a03`, stored `…b03`), and a matched POST without `_id` with
`_id: null`. `docs/proposals/TEST-IMPLEMENTATION-SUMMARY.md` §6.1.2 requires every item in a v1
POST response to carry an `_id`; no existing test asserts the `null`, and every existing test that
reads a POST response `_id` expects one to be present (`tests/api.v1-batch-operations.test.js`,
`api.deduplication.test.js`, `api.partial-failures.test.js`, `api.aaps-client.test.js`;
all pass). So both cases were changed; nothing required stopping.

After the `bulkWrite`, `assignStoredIds` collects the entries the upsert did not insert and whose
filter is `sysTime` + `type`, and reads their stored `_id`s in **one** `find` for the whole batch
(an `$or` of those same filters, projection `_id, sysTime, type`), only when at least one entry
matched. Each matched response item gets its stored `_id`; a new entry keeps the `_id` it was
stored with. A second entry at the same time and type in one batch gets the first one's `_id`. If
the read-back fails, the POST still answers 200 with the entries stored and the response `_id`s as
before. Tests spy on the collection: one `find` for a batch of three matched entries, none for a
batch of new entries, and the `$or` holds only the matched entries.

### 3.6 devicestatus re-send guard (commit 7, `ad973110`, D1)

`597e2899` commit c stored a 24-hex devicestatus `_id` as an ObjectId with no check for the string
form, so a report re-sent with the `_id` of a string-stored copy was stored beside it (dev: refused,
500). `lib/server/devicestatus.js` `storeIdsAsObjectIds` now, for a batch that carries 24-hex
`_id`s, makes one `find({_id: {$in: <string forms>}}, {_id: 1})` (the lower-case and as-sent
spelling of each id, the same forms the websocket commit uses) and keeps the stored value for ids
found, so the insert collides and is refused as on dev and as a profile re-send is (BF-99). Other
ids become ObjectIds. A batch without 24-hex `_id`s makes no read (test: spy counts zero finds). The
in-process path (`ctx.devicestatus.create`, used by the connector) goes through the same code.

As on dev, an ordered `insertMany` stores the rows of a batch that come before a collision and not
the ones after it.

Cost, measured with `ctx.devicestatus.create` in-process on Node 20.20.0 and `mongo:7`, 100-row
batches, a devicestatus collection of 20,000 rows (10 % with string `_id`s), 40 timed runs per kind
after 3 warm-up pairs, hex and no-`_id` batches alternated, two repeats per tree:

| tree | batch | median ms | p90 ms |
|---|---|---:|---:|
| `18b09df7` (no guard) | 100 rows with hex `_id` | 4.18 / 4.17 | 5.39 / 7.68 |
| `18b09df7` (no guard) | 100 rows without `_id` | 4.06 / 4.09 | 6.45 / 6.62 |
| `ad973110` (guard) | 100 rows with hex `_id` | 5.29 / 5.09 | 7.48 / 8.81 |
| `ad973110` (guard) | 100 rows without `_id` | 4.14 / 3.93 | 5.93 / 7.34 |

So the guard adds about 1.0 to 1.1 ms (median) to a 100-row batch carrying hex `_id`s, and nothing
to one without. The guard's `find` alone, 100 ids: median 0.67 ms, p90 0.75 to 0.78 ms (a separate
loop in the same script), plan `PROJECTION_COVERED > IXSCAN(_id_)`, no documents examined. An
earlier 10-run attempt was taken while a full suite ran on the same MongoDB and is not used.

### 3.7 Upper-case string `_id`s (commit 8, `6d120fa2`, D4)

No behaviour change. `lib/server/object-id-forms.js`'s header now states the limit: the string
forms matched are the lower-case hex and the caller's own spelling, so a string `_id` stored in
upper (or mixed) case is found when asked for in that spelling, not when asked for in lower case;
the ObjectId form is found either way. The header's list of non-hex rules also now says that the
websocket keeps a non-hex `_id` as given and that API v3 matches any string identifier against
`_id` (commit 5).

## 4. Tests, break-its, suites

New or changed test files and red counts (Node 20.20.0, `mongo:7`):

| file | tests | red on `1f9a9d10` | red on `597e2899` | red on the commit's parent | the passing ones (on the parent) |
|---|---:|---:|---:|---:|---|
| `tests/api.entries.repost-with-id.test.js` (commits 1 and 6) | 18 | 11 | 11 | 4 of 8 (commit 1), 7 of 18 (commit 6) | re-POST with the stored `_id`; new entry; entry without `type`; POST without `_id`; sent `_id` for a new entry; no read for new entries; a failed read-back |
| `tests/api.entries.upper-case-id.test.js` | 5 | 3 | 3 | 3 | `GET /entries/<lower>`; `/entries/sgv` |
| `tests/websocket.object-id.test.js` | 13 | 10 | 10 | 10 | re-send of a string-stored record, lower and upper case; `dbUpdate` of an ObjectId record |
| `tests/api.crud-by-id.matrix.test.js` | 336 | 160 | 70 | — | §2 |
| `tests/api3.non-hex-id.test.js` | 16 | 11 | 11 | 11 | an operator-shaped identifier; GET by an operator-looking string; a UUID identifier; a hex id; a new identifier |
| `tests/api.devicestatus.resend-guard.test.js` | 8 | 4 | 5 | 5 | on `597e2899`: ObjectId-stored re-send refused; new hex batch stored as ObjectIds; no read without `_id`s (dev, which stores hex `_id`s as strings, passes and fails a different mix) |
| `tests/api3.storage.modify.test.js` (changed) | — | — | — | — | three filter-shape assertions updated to the D2 shape |

Break-its, one part of the fix removed at a time, the commit's own test file (for commit 5, also
the two v3 storage test files):

| commit | removed | red |
|---|---|---:|
| 1 | `$setOnInsert` of the sent `_id` (back to `$set: doc`) | 4 of 7 |
| 2 | `/entries/:spec` back to the lower-case pattern | 3 of 5 |
| 2 | shared v1 `_id` check narrowed to lower case (other-collections, profiles and upper-case files) | 4 of 49 |
| 3 | `dbAdd` conversion / "already stored as a string" guard / either-form `idMatch` | 3 / 2 / 6 of 13 |
| 3 | `dbUpdate` / `dbUpdateUnset` `updateMany`, `dbRemove` `deleteMany` | 1 / 1 / 1 of 13 |
| 3 | similar-treatment update by the stored `_id` | 1 of 13 |
| 5 | `filterForOne` non-hex branch / `identifyingFilter` non-hex branch | 12 / 4 of 25 |
| 5 | literal `$eq` in the `filterForOne` / `identifyingFilter` branch (bare value) | 4 / 1 of 25 |
| 5 | the "string only" condition (any identifier gets an `_id` branch) | 2 of 25 |
| 6 | the read-back call / "only matched entries" / the empty-batch early return | 7 / 2 / 1 of 18 |
| 6 | per-entry mapping (every item gets the first stored `_id`) / the read-back `try` | 2 / 1 of 18 |
| 7 | the guard lookup / keeping the stored value / both string spellings / no read without hex ids | 4 / 1 / 1 / 1 of 8 |
| 7 | the ObjectId conversion / the call | 2 / 4 of 8 |

Commit 3's break-its ran on `f433dc16` (same hunks). Commit 8 is comment only and has no break-it.
Two tests were added during the break-its so that a hunk had a test that could fail: the
`dbUpdateUnset` twins test (commit 3) and the upper-case re-send of a lower-case string record
(commit 7). A first failing-read-back test for commit 6 made the test's own read fail and was
fixed before any count was taken.

Full suite (`npm test`, `mongo:7` in container `crud-mongo`), passing / failing / pending:

| tree | Node 20.20.0 | Node 22.23.2 | new tests |
|---|---|---|---:|
| `bf/object-id-consistency` `597e2899` | 2470 / 0 / 3 | 2470 / 0 / 3 | — |
| 1 `4b41bcf8` | 2478 / 0 / 3 | 2478 / 0 / 3 | +8 |
| 2 `a612a26f` | 2483 / 0 / 3 | 2483 / 0 / 3 | +5 |
| 3 `12c01268` | 2496 / 0 / 3 | 2496 / 0 / 3 | +13 |
| 4 `c721e202` | 2832 / 0 / 3 | 2832 / 0 / 3 | +336 |
| 5 `44ac9047` | 2848 / 0 / 3 | 2848 / 0 / 3 | +16 |
| 6 `18b09df7` | 2858 / 0 / 3 | 2858 / 0 / 3 | +10 |
| 7 `ad973110` | 2866 / 0 / 3 | 2866 / 0 / 3 | +8 |
| 8 `6d120fa2` (tip) | 2866 / 0 / 3 | 2866 / 0 / 3 | 0 |

Every step adds exactly its new tests. The only existing test changed is
`tests/api3.storage.modify.test.js` (commit 5, D2).

## 5. Decisions

Taken by the maintainer on 2026-09-23 and applied as commits 5 to 8:

| | question | decision | commit |
|---|---|---|---|
| D1 | devicestatus re-sent with the `_id` of a string-stored copy | add BF-99's guard, one indexed read per batch carrying hex `_id`s | `ad973110` |
| D2 | API v3 and a non-hex string `_id` | take the fix; update the filter-shape tests | `44ac9047` |
| D3 | entries POST response `_id` for a matched reading | answer the stored `_id`, one read per batch, for a sent `_id` and for none | `18b09df7` |
| D4 | upper-case string `_id` asked in lower case | leave; state the limit in the helper header | `6d120fa2` |

Stated, not decisions (deliberate and tested): a non-hex `_id` is moved to `identifier` by v1
treatments and entries, refused with 400 by the other v1 routes, and kept as given by the
websocket; API v3 refuses a PUT that names an ObjectId record by its upper-case hex (400, the
identifier is immutable), while GET and DELETE by that spelling work.

## 6. Merges

`git merge-tree --write-tree` of `6d120fa2` against each open 15.0.9 head:

| head | result |
|---|---|
| #8748 `d19043b2` | clean |
| #8749 `46b20b38` | clean |
| #8751 `b5038500` | clean |
| #8753 `e6a50e9a` | clean |
| #8754 `0a74ef4e` | clean |
| #8755 `92544d8f` | clean |
| #8756 `83cfff14` | clean |
| #8757 `5d342ac1` (`bf3/mmconnect-deprecation-warning`) | clean |
| `rc/15.0.9-additions-e` `1b1977e0` | clean |
| `bf/profile-object-id` `9b8cc2f9` | conflict, `lib/server/profile.js`, inherited from `597e2899` (land one) |
| `bf/object-id-other-collections` `2fac53f5` | conflict, `lib/server/object-id-forms.js` (commit 8's header) |
| `bf/api3-string-id` `7295bc8c` | conflict, `lib/server/object-id-forms.js` and `lib/api3/storage/mongoCollection/utils.js` (commits 5 and 8) |

The last three are the narrow alternatives that `bf/object-id-consistency` already carries; they
merged cleanly with `c721e202` and conflict with commits 5 and 8, so they are not landed beside this
branch. The merged tree with `rc/15.0.9-additions-e` (which contains #8754), written with
`git read-tree` into a scratch worktree, passes the websocket, matrix, entries, devicestatus and v3
storage test files (439 / 0; Node 20.20.0, with the node_modules of `origin/dev`'s lock;
`rc/15.0.9-additions-e` changes `package.json`). The full suite was not run on merged trees.

## 7. Not changed

- No boot migration: string-`_id` records stay as they are until written, edited or deleted.
- The helper's forms (D4).
- `chore/nightscout-modernization` was not examined for these defects.
