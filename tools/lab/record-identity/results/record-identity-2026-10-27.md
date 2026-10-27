# record-identity lab results, 2026-10-27

*Contributor-facing. Synthetic data only; nothing here is from a real site.*

Produced by `tools/lab/record-identity/lab.sh up && lab.sh run` (see [README](../README.md)) with:

```sh
RID_REPO=<main checkout>/externals/cgm-remote-monitor-official
RID_BUILDS="1509=c6a0d8ed:3983 dev=7abe1cf6:3984"          # v15.0.9 and 16.0.0's dev after #8870
RID_NM_1509=externals/work/crm-1509-2610/node_modules      # a c6a0d8ed checkout
RID_NM_dev=externals/work/crm-count-onepath/node_modules   # package-lock.json identical to 7abe1cf6's (git diff)
RID_NODE=node                                              # 22.23.4
```

MongoDB `mongo:7` (the lab default). 61 cases; 7 differ between the two builds:
v1 entries and device status now match a re-send on `identifier` (#8859); a v1 treatment matched by
time is answered with its stored `_id` (BF-165, #8845); a re-sent profile `_id` is answered 200, not
500; API v3 refuses a body `_id` with 400 (BF-170, #8845); and an API v3 device status re-sent after a
soft delete stays deleted (`isValid: false`), where treatments and entries come back.

The probes now compute the UUID v5 they compare against with `node:crypto` when the build has no
`uuid` package (16.0.0 removed it); checked equal to `uuid.v5` for the lab's input.

| case | 15.0.9 `c6a0d8ed` | 16.0.0 `7abe1cf6` |
|---|---|---|
| entries v1 POST: new 24-hex _id | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored |
| entries v1 POST: same _id, same time (re-send) | 200 \| stored n=1 [_id:oid=sent sgv=112] | 200 \| stored n=1 [_id:oid=sent sgv=112] |
| entries v1 POST: same _id, different time | 500 "Mongo Error" (E11000 duplicate key) \| stored n=1 [_id:oid=sent date=t1] | 500 "Mongo Error" (E11000 duplicate key) \| stored n=1 [_id:oid=sent date=t1] |
| entries v1 POST: different _id, same time | 200 \| stored n=1 [_id:oid=sent sgv=113] \| reply _id=stored | 200 \| stored n=1 [_id:oid=sent sgv=113] \| reply _id=stored |
| entries v1 POST: no _id, same time twice | 200 -> 200 \| stored n=1 [_id:oid sgv=114] \| 1st reply _id=stored, 2nd reply _id=stored | 200 -> 200 \| stored n=1 [_id:oid sgv=114] \| 1st reply _id=stored, 2nd reply _id=stored |
| entries v1 POST: UUID _id | 200 \| stored n=1 [_id:oid≠sent identifier=X] \| reply _id=stored | 200 \| stored n=1 [_id:oid≠sent identifier=X] \| reply _id=stored |
| entries v1 POST: non-UUID, non-hex string _id | 200 \| stored n=1 [_id:oid≠sent identifier=X] | 200 \| stored n=1 [_id:oid≠sent identifier=X] |
| entries v1 POST: same identifier, different time | 200 \| stored n=2 [_id:oid identifier=X; _id:oid identifier=X] | 200 \| stored n=1 [_id:oid identifier=X] |
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
| treatments v1 POST: no ids, identical body twice | 200 \| stored n=1 [_id:oid] \| 1st reply _id=stored, 2nd reply no _id | 200 \| stored n=1 [_id:oid] \| 1st reply _id=stored, 2nd reply _id=stored |
| treatments v1 POST: no ids, same time + eventType, other carbs | 200 \| stored n=2 [_id:oid carbs=10; _id:oid carbs=25] | 200 \| stored n=2 [_id:oid carbs=10; _id:oid carbs=25] |
| treatments v1 POST (single object): same identifier twice | 200 \| stored n=1 [_id:oid identifier=X carbs=13] \| 1st reply _id=stored, 2nd reply _id=stored | 200 \| stored n=1 [_id:oid identifier=X carbs=13] \| 1st reply _id=stored, 2nd reply _id=stored |
| treatments v1 PUT: by 24-hex _id | 200 \| stored n=1 [_id:oid=sent carbs=14] \| reply _id=sent=stored | 200 \| stored n=1 [_id:oid=sent carbs=14] \| reply _id=sent=stored |
| treatments v1 PUT: by identifier, no _id | 200 \| stored n=1 [_id:oid identifier=X carbs=15] \| reply _id=stored | 200 \| stored n=1 [_id:oid identifier=X carbs=15] \| reply _id=stored |
| treatments v1 GET: find[_id]=<hex sent beside identifier>, find[identifier]=X, find[_id]=<lower-case UUID sent as _id>, <upper-case UUID sent as _id>, the first asked upper-case, the second asked lower-case | found 0, 1, 1, 1, 0, 0 | found 0, 1, 1, 1, 0, 0 |
| treatments v1 DELETE /treatments/<uuid identifier>, then re-send | delete 200 {"acknowledged":true,"deletedCount":1,"n":1}, left n=0 \| re-send 200 \| stored n=1 [_id:oid identifier=X] | delete 200 {"acknowledged":true,"deletedCount":1,"n":1}, left n=0 \| re-send 200 \| stored n=1 [_id:oid identifier=X] |
| treatments v1 DELETE /treatments/<non-UUID identifier>; GET find[identifier] | delete 200 {"acknowledged":true,"deletedCount":0,"n":0}, left n=1 \| GET found 1 | delete 200 {"acknowledged":true,"deletedCount":0,"n":0}, left n=1 \| GET found 1 |
| treatments v1 DELETE /treatments/<hex>, then re-send same _id | delete 200 {"acknowledged":true,"deletedCount":1,"n":1} \| re-send 200 \| stored n=1 [_id:oid=sent] | delete 200 {"acknowledged":true,"deletedCount":1,"n":1} \| re-send 200 \| stored n=1 [_id:oid=sent] |
| devicestatus v1 POST: new 24-hex _id | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored |
| devicestatus v1 POST: same _id re-sent | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored | 200 \| stored n=1 [_id:oid=sent] \| reply _id=sent=stored |
| devicestatus v1 POST batch [new, re-sent _id, new] | 200 \| stored per item [item1:1 item2:1 item3:1] | 200 \| stored per item [item1:1 item2:1 item3:1] |
| devicestatus v1 POST: no _id, identical body twice | 200 \| stored n=2 [_id:oid; _id:oid] | 200 \| stored n=2 [_id:oid; _id:oid] |
| devicestatus v1 POST: same identifier twice | 200 \| stored n=2 [_id:oid identifier=X; _id:oid identifier=X] | 200 \| stored n=1 [_id:oid identifier=X] |
| devicestatus v1 POST: UUID _id | 400 "Invalid _id format" \| stored n=0 | 400 "Invalid _id format" \| stored n=0 |
| devicestatus v1 GET find[_id]=<hex>, then DELETE /devicestatus/<hex> | GET found 1 \| delete 200 {"acknowledged":true,"deletedCount":1,"n":1}, left n=0 | GET found 1 \| delete 200 {"acknowledged":true,"deletedCount":1,"n":1}, left n=0 |
| profile v1 POST new 24-hex _id, then PUT same _id | POST 200 stored n=1 [_id:oid=sent] \| PUT 200 stored n=1 [_id:oid=sent defaultProfile="Edited"] | POST 200 stored n=1 [_id:oid=sent] \| PUT 200 stored n=1 [_id:oid=sent defaultProfile="Edited"] |
| profile v1 POST: same _id re-sent | 500 "Mongo Error" (E11000 duplicate key) \| stored n=1 [_id:oid=sent] | 200 \| stored n=1 [_id:oid=sent] |
| profile v1 POST: UUID _id | 400 "Invalid _id format" | 400 "Invalid _id format" |
| food v1 POST new 24-hex _id, then PUT same _id | POST 200 stored n=1 [_id:oid=sent] \| PUT 200 stored n=1 [_id:oid=sent carbs=11] | POST 200 stored n=1 [_id:oid=sent] \| PUT 200 stored n=1 [_id:oid=sent carbs=11] |
| food v1 POST: UUID _id | 400 "Invalid _id format" | 400 "Invalid _id format" |
| v3 treatments POST: no identifier | 201 identifier \| stored n=1 [_id:oid identifier] \| identifier = uuid.v5(device_date_eventType) \| reply keys status,identifier,lastModified | 201 identifier \| stored n=1 [_id:oid identifier] \| identifier = uuid.v5(device_date_eventType) \| reply keys status,identifier,lastModified |
| v3 treatments POST: identifier + 24-hex _id in body | 201 identifier \| stored n=1 [_id:string=sent identifier=X] | 400 "Field _id is assigned by Nightscout and is not accepted; send the record's own id in the identifier field" \| stored n=0 |
| v3 treatments POST: 24-hex _id in body, no identifier | 201 identifier \| stored n=1 [_id:string=sent identifier] | 400 "Field _id is assigned by Nightscout and is not accepted; send the record's own id in the identifier field" \| stored n=0 |
| v3 GET /treatments/<hex _id of a v1 record>; then v3 POST identifier=<that hex> | GET 200 identifier=hex no _id \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid=sent identifier=X] | GET 200 identifier=hex no _id \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid=sent identifier=X] |
| v3 treatments soft DELETE, then GET, PUT, POST same identifier | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] |
| v3 treatments permanent DELETE, then POST same identifier | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] |
| v3 entries soft DELETE, then GET, PUT, POST same identifier | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] |
| v3 entries permanent DELETE, then POST same identifier | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] |
| v3 devicestatus soft DELETE, then GET, PUT, POST same identifier | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] | delete 200 \| GET 410 \| PUT 410 \| POST 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X isValid:false] |
| v3 devicestatus permanent DELETE, then POST same identifier | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] | delete 200 \| POST 201 identifier \| stored n=1 [_id:oid identifier=X] |
| v3 treatments soft DELETE, then POST same identifier with date +60 s and another device | 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] date=t+60s device=ridlab-other | 200 identifier isDeduplication \| stored n=1 [_id:oid identifier=X] date=t+60s device=ridlab-other |
| v3 soft DELETE treatment, then v1 POST same identifier | 200 \| stored n=1 [_id:oid identifier=X] \| v1 GET found 1 | 200 \| stored n=1 [_id:oid identifier=X] \| v1 GET found 1 |
| socket authorize | write | write |
| socket treatments dbAdd 24-hex _id; dbUpdate and dbRemove by it | dbAdd [1 item] stored n=1 [_id:oid=sent] \| dbUpdate {"result":"success"} carbs=33 \| dbRemove {"result":"success"} left n=0 | dbAdd [1 item] stored n=1 [_id:oid=sent] \| dbUpdate {"result":"success"} carbs=33 \| dbRemove {"result":"success"} left n=0 |
| socket treatments dbAdd UUID _id | dbAdd [1 item] stored n=1 [_id:string=sent] | dbAdd [1 item] stored n=1 [_id:string=sent] |
| socket treatments dbAdd same identifier, time +60 s | dbAdd [1 item] stored n=2 [_id:oid identifier=X; _id:oid identifier=X] | dbAdd [1 item] stored n=2 [_id:oid identifier=X; _id:oid identifier=X] |
| socket entries dbAdd identical body twice | dbAdd [1 item] stored n=2 [_id:oid; _id:oid] | dbAdd [1 item] stored n=2 [_id:oid; _id:oid] |
| socket entries dbAdd same 24-hex _id twice | dbAdd [] stored n=1 [_id:oid=sent] | dbAdd [] stored n=1 [_id:oid=sent] |
| socket devicestatus dbAdd same created_at twice | dbAdd [1 item] stored n=1 [_id:oid uploaderBattery=50] | dbAdd [1 item] stored n=1 [_id:oid uploaderBattery=50] |
