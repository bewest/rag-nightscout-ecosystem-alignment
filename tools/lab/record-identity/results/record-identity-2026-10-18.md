# record-identity lab results, 2026-10-18

*Contributor-facing. Synthetic data only; nothing here is from a real site.*

Produced by `tools/lab/record-identity/lab.sh up && lab.sh run` (see [README](../README.md)) with:

```sh
RID_REPO=<main checkout>/externals/cgm-remote-monitor-official
RID_BUILDS="1508=15.0.8:3983 dev=fade2299:3984"            # the default
RID_NM_1508=externals/work/crm-6a-replay-a/node_modules    # same package-lock.json as 15.0.8 (checked by cmp)
RID_NM_dev=externals/work/crm-rc-018-n20/node_modules       # same package-lock.json as fade2299 (checked by cmp)
RID_NODE=<n>/versions/node/22.23.2/bin/node
```

| build | what | head | `/api/v3/version` |
|---|---|---|---|
| 1508 | 15.0.8, the shipping release | `92d08342` | `15.0.8`, apiVersion `3.0.5` |
| dev | `official/dev` | `fade2299` | `15.0.9` (package version on dev), apiVersion `3.0.5` |

MongoDB: dedicated container `ridlab-mongo`, `mongo:7`, server version read back **7.0.43**. Node
22.23.2. `UUID_HANDLING` unset (default on). v1 calls carry the `api-secret` hash, v3 calls a JWT
for an `admin` subject the probe creates, the socket authorizes with the hash. The probes were run
three times against the same servers; every cell was the same each time except the order of two
records in one cell, which the probe now sorts.

How to read a cell: HTTP status (and the MongoDB cause when the reply body names one), then what
is stored, read **from mongo**: `n=` copies, each with `_id:oid` (an ObjectId) or `_id:string`,
`=sent` / `≠sent` against the `_id` the client sent, and `identifier=X` when it equals the value
the case sent as `identifier` (or as `_id`, for the cases that test `UUID_HANDLING`). `reply` says
whether the reply item's `_id` is the one sent, the one stored, both, or absent. Times are one
minute apart per case, 1 to 2 days back.

## Results

| case | 15.0.8 `92d08342` | 15.0.9 `fade2299` |
|---|---|---|
| entries v1 POST: new 24-hex _id | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored |
| entries v1 POST: same _id, same time (re-send) | 200 \| stored n=1 [_id:oid=sent sgv=112] | 200 \| stored n=1 [_id:oid=sent sgv=112] |
| entries v1 POST: same _id, different time | 500 "Mongo Error" (E11000 duplicate key) \| stored n=1 [_id:oid=sent date=t1] | 500 "Mongo Error" (E11000 duplicate key) \| stored n=1 [_id:oid=sent date=t1] |
| entries v1 POST: different _id, same time | 500 "Mongo Error" (immutable field _id) \| stored n=1 [_id:oid=sent sgv=111] \| reply no _id | 200 \| stored n=1 [_id:oid=sent sgv=113] \| reply _id=stored |
| entries v1 POST: no _id, same time twice | 200 -> 200 \| stored n=1 [_id:oid sgv=114] \| 1st reply _id=stored, 2nd reply no _id | 200 -> 200 \| stored n=1 [_id:oid sgv=114] \| 1st reply _id=stored, 2nd reply _id=stored |
| entries v1 POST: UUID _id | 200 \| stored n=1 [_id:oid≠sent identifier=X] \| reply _id=stored | 200 \| stored n=1 [_id:oid≠sent identifier=X] \| reply _id=stored |
| entries v1 POST: non-UUID, non-hex string _id | 200 \| stored n=1 [_id:oid≠sent identifier=X] | 200 \| stored n=1 [_id:oid≠sent identifier=X] |
| entries v1 POST: same identifier, different time | 200 \| stored n=2 [_id:oid identifier=X; _id:oid identifier=X] | 200 \| stored n=2 [_id:oid identifier=X; _id:oid identifier=X] |
| entries v1 POST: identifier Y at the time of a stored entry with identifier X | 200 \| stored n=1 [identifier=Y sgv=115] | 200 \| stored n=1 [identifier=Y sgv=115] |
| entries v1 POST: identifier X + new 24-hex _id | 200 \| stored n=1 [_id:oid=sent identifier=X] \| reply _id=sent=stored | 200 \| stored n=1 [_id:oid=sent identifier=X] \| reply _id=sent=stored |
| entries v1 POST batch [new, same _id at another time, new] | 500 "Mongo Error" (E11000 duplicate key) \| of the batch stored 1 [item1:yes item2:no item3:no] | 500 "Mongo Error" (E11000 duplicate key) \| of the batch stored 1 [item1:yes item2:no item3:no] |
| entries v1 GET: /entries/<hex>, find[_id]=<hex>, find[identifier]=X | found 1, 1, 1 | found 1, 1, 1 |
| entries v1 DELETE /entries/<hex>, then re-send same _id | delete 200 {"acknowledged":true,"deletedCount":1,"n":1}, left n=0 \| re-send 200 \| stored n=1 [_id:oid=sent] | delete 200 {"acknowledged":true,"deletedCount":1,"n":1}, left n=0 \| re-send 200 \| stored n=1 [_id:oid=sent] |
| treatments v1 POST: new 24-hex _id | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored |
| treatments v1 POST: same _id, carbs changed | 200 \| stored n=1 [_id:oid=sent carbs=11] | 200 \| stored n=1 [_id:oid=sent carbs=11] |
| treatments v1 POST: same _id, different time | 200 \| stored n=1 [_id:oid=sent] created_at=t2 | 200 \| stored n=1 [_id:oid=sent] created_at=t2 |
| treatments v1 POST: identifier X + new 24-hex _id | 200 \| stored n=1 [_id:oid≠sent identifier=X] \| reply _id=stored | 200 \| stored n=1 [_id:oid≠sent identifier=X] \| reply _id=stored |
| treatments v1 POST: same identifier, other _id | 200 \| stored n=1 [_id:oid≠sent identifier=X carbs=12] \| reply _id=stored | 200 \| stored n=1 [_id:oid≠sent identifier=X carbs=12] \| reply _id=stored |
| treatments v1 POST: stored record's _id with a new identifier Y | 200 \| stored n=2 [identifier=X; identifier=Y] | 200 \| stored n=2 [identifier=X; identifier=Y] |
| treatments v1 POST: UUID _id | 200 \| stored n=1 [_id:oid≠sent identifier=X] \| reply _id=stored | 200 \| stored n=1 [_id:oid≠sent identifier=X] \| reply _id=stored |
| treatments v1 POST: non-UUID, non-hex string _id | 200 \| stored n=1 [_id:oid≠sent identifier=X] | 200 \| stored n=1 [_id:oid≠sent identifier=X] |
| treatments v1 POST: no ids, identical body twice | 200 \| stored n=1 [_id:oid] \| 1st reply _id=stored, 2nd reply no _id | 200 \| stored n=1 [_id:oid] \| 1st reply _id=stored, 2nd reply no _id |
| treatments v1 POST: no ids, same time + eventType, other carbs | 200 \| stored n=1 [_id:oid carbs=25] | 200 \| stored n=2 [_id:oid carbs=10; _id:oid carbs=25] |
| treatments v1 POST (single object): same identifier twice | 200 \| stored n=1 [_id:oid identifier=X carbs=13] \| 1st reply _id=stored, 2nd reply _id=stored | 200 \| stored n=1 [_id:oid identifier=X carbs=13] \| 1st reply _id=stored, 2nd reply _id=stored |
| treatments v1 PUT: by 24-hex _id | 200 \| stored n=1 [_id:oid=sent carbs=14] \| reply _id=sent=stored | 200 \| stored n=1 [_id:oid=sent carbs=14] \| reply _id=sent=stored |
| treatments v1 PUT: by identifier, no _id | 200 \| stored n=1 [_id:oid identifier=X carbs=15] \| reply _id=stored | 200 \| stored n=1 [_id:oid identifier=X carbs=15] \| reply _id=stored |
| treatments v1 GET: find[_id]=<hex>, find[identifier]=X, find[_id]=<uuid sent as _id>, same upper-case-sent, lower-case-sent asked upper | found 0, 1, 1, 1, 1 | found 0, 1, 1, 1, 1 |
| treatments v1 DELETE /treatments/<uuid identifier>, then re-send | delete 200 {"acknowledged":true,"deletedCount":1,"n":1}, left n=0 \| re-send 200 \| stored n=1 [_id:oid identifier=X] | delete 200 {"acknowledged":true,"deletedCount":1,"n":1}, left n=0 \| re-send 200 \| stored n=1 [_id:oid identifier=X] |
| treatments v1 DELETE /treatments/<non-UUID identifier>; GET find[identifier] | delete 200 {"acknowledged":true,"deletedCount":0,"n":0}, left n=1 \| GET found 1 | delete 200 {"acknowledged":true,"deletedCount":0,"n":0}, left n=1 \| GET found 1 |
| treatments v1 DELETE /treatments/<hex>, then re-send same _id | delete 200 {"acknowledged":true,"deletedCount":1,"n":1} \| re-send 200 \| stored n=1 [_id:oid=sent] | delete 200 {"acknowledged":true,"deletedCount":1,"n":1} \| re-send 200 \| stored n=1 [_id:oid=sent] |
| devicestatus v1 POST: new 24-hex _id | 200 \| stored n=1 [_id:string=sent] \| reply _id=sent=stored | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored |
| devicestatus v1 POST: same _id re-sent | 500 "Mongo Error" (E11000 duplicate key) \| stored n=1 [_id:string=sent] \| reply no _id | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored |
| devicestatus v1 POST batch [new, re-sent _id, new] | 500 "Mongo Error" (E11000 duplicate key) \| stored per item [item1:1 item2:1 item3:0] | 200 \| stored per item [item1:1 item2:1 item3:1] |
| devicestatus v1 POST: no _id, identical body twice | 200 \| stored n=2 [_id:oid; _id:oid] | 200 \| stored n=2 [_id:oid; _id:oid] |
| devicestatus v1 POST: same identifier twice | 200 \| stored n=2 [_id:oid identifier=X; _id:oid identifier=X] | 200 \| stored n=2 [_id:oid identifier=X; _id:oid identifier=X] |
| devicestatus v1 POST: UUID _id | 400 "Invalid _id format" \| stored n=0 | 400 "Invalid _id format" \| stored n=0 |
| devicestatus v1 GET find[_id]=<hex>, then DELETE /devicestatus/<hex> | GET found 0 \| delete 200 {"acknowledged":true,"deletedCount":0,"n":0}, left n=1 | GET found 1 \| delete 200 {"acknowledged":true,"deletedCount":1,"n":1}, left n=0 |
| profile v1 POST new 24-hex _id, then PUT same _id | POST 200 stored n=1 [_id:string=sent] \| PUT 200 stored n=2 [_id:string=sent defaultProfile="Default"; _id:oid=sent defaultProfile="Edited"] | POST 200 stored n=1 [_id:oid=sent] \| PUT 200 stored n=1 [_id:oid=sent defaultProfile="Edited"] |
| profile v1 POST: same _id re-sent | 500 "Mongo Error" (E11000 duplicate key) \| stored n=1 [_id:string=sent] | 500 "Mongo Error" (E11000 duplicate key) \| stored n=1 [_id:oid=sent] |
| profile v1 POST: UUID _id | 400 "Invalid _id format" | 400 "Invalid _id format" |
| food v1 POST new 24-hex _id, then PUT same _id | POST 200 stored n=1 [_id:string=sent] \| PUT 200 stored n=2 [_id:string=sent carbs=10; _id:oid=sent carbs=11] | POST 200 stored n=1 [_id:oid=sent] \| PUT 200 stored n=1 [_id:oid=sent carbs=11] |
| food v1 POST: UUID _id | 400 "Invalid _id format" | 400 "Invalid _id format" |
| v3 treatments POST: no identifier | 201 identifier \| stored n=1 [_id:oid identifier] \| identifier = uuid.v5(device_date_eventType) \| reply keys status,identifier,lastModified | 201 identifier \| stored n=1 [_id:oid identifier] \| identifier = uuid.v5(device_date_eventType) \| reply keys status,identifier,lastModified |
| v3 treatments POST: identifier + 24-hex _id in body | 201 identifier \| stored n=1 [_id:string=sent identifier=X] | 201 identifier \| stored n=1 [_id:string=sent identifier=X] |
| v3 treatments POST: 24-hex _id in body, no identifier | 201 identifier \| stored n=1 [_id:string=sent identifier] | 201 identifier \| stored n=1 [_id:string=sent identifier] |
| v3 GET /treatments/<hex _id of a v1 record>; then v3 POST identifier=<that hex> | GET 200 identifier=hex no _id \| POST 400 "Field date cannot be modified by the client" \| stored n=1 [_id:oid=sent] | GET 200 identifier=hex no _id \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid=sent identifier=X] |
| v3 treatments soft DELETE, then GET, PUT, POST same identifier | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] |
| v3 treatments permanent DELETE, then POST same identifier | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] |
| v3 entries soft DELETE, then GET, PUT, POST same identifier | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] |
| v3 entries permanent DELETE, then POST same identifier | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] |
| v3 devicestatus soft DELETE, then GET, PUT, POST same identifier | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] |
| v3 devicestatus permanent DELETE, then POST same identifier | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] |
| v3 treatments soft DELETE, then POST same identifier with date +60 s and another device | 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] date=t+60s device=ridlab-other | 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] date=t+60s device=ridlab-other |
| v3 soft DELETE treatment, then v1 POST same identifier | 200 \| stored n=1 [_id:oid identifier=X] \| v1 GET found 1 | 200 \| stored n=1 [_id:oid identifier=X] \| v1 GET found 1 |
| socket authorize | write | write |
| socket treatments dbAdd 24-hex _id; dbUpdate and dbRemove by it | dbAdd [1 item] stored n=1 [_id:string=sent] \| dbUpdate {"result":"success"} carbs=10 \| dbRemove {"result":"success"} left n=1 | dbAdd [1 item] stored n=1 [_id:oid=sent] \| dbUpdate {"result":"success"} carbs=33 \| dbRemove {"result":"success"} left n=0 |
| socket treatments dbAdd UUID _id | dbAdd [1 item] stored n=1 [_id:string=sent] | dbAdd [1 item] stored n=1 [_id:string=sent] |
| socket treatments dbAdd same identifier, time +60 s | dbAdd [1 item] stored n=2 [_id:oid identifier=X; _id:oid identifier=X] | dbAdd [1 item] stored n=2 [_id:oid identifier=X; _id:oid identifier=X] |
| socket entries dbAdd identical body twice | dbAdd [1 item] stored n=2 [_id:oid; _id:oid] | dbAdd [1 item] stored n=2 [_id:oid; _id:oid] |
| socket entries dbAdd same 24-hex _id twice | dbAdd [] stored n=1 [_id:string=sent] | dbAdd [] stored n=1 [_id:oid=sent] |
| socket devicestatus dbAdd same created_at twice | dbAdd [1 item] stored n=1 [_id:oid uploaderBattery=50] | dbAdd [1 item] stored n=1 [_id:oid uploaderBattery=50] |
