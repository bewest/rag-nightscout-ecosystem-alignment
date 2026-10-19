# URL-form identifiers on cgm-remote-monitor, 2026-10-18

*Contributor-facing. Synthetic data only.* Produced by
[`url-identifier-probes.js`](url-identifier-probes.js) against servers started by
`tools/lab/record-identity/lab.sh up` (`RID_BUILDS="1508=15.0.8:3993 dev=fade2299:3994"`,
`RID_MONGO_PORT=27186`, node_modules symlinked from installs of the same `package-lock.json`,
Node 22.23.2). MongoDB: dedicated container `ridlab-mongo`, `mongo:7`, server version read back
7.0.43. No proxy in front of either server. Run twice; both tables were identical. The container
and the lab state were removed afterwards.

The identifier is `cgm://g7/<12 random digits>/<random seconds>` (or `loop://` for the v1
treatments rows): it contains `:` and `/`. "encoded" means `encodeURIComponent` (`:` as `%3A`,
`/` as `%2F`); "`%2F` only" leaves `:` raw; "raw" sends the identifier unescaped. `identifier=X`
means the record read back carries exactly the identifier written. The two control rows ask for the
same identifier plus `/1` and must find nothing.

| case | 15.0.8 `92d08342` | 15.0.9 `fade2299` |
|---|---|---|
| v3 entries POST identifier scheme://a/b/c | 201 \| stored n=1 identifier=X | 201 \| stored n=1 identifier=X |
| v3 entries GET /entries/<encodeURIComponent: %3A %2F> | 200 identifier=X | 200 identifier=X |
| v3 entries GET /entries/<%2F only, ":" raw> | 200 identifier=X | 200 identifier=X |
| v3 entries GET /entries/<raw> | 404 | 404 |
| v3 entries search ?identifier$eq=<encoded>, ?identifier=<encoded> | found 1, found 1 | found 1, found 1 |
| v1 entries GET find[identifier]=<encoded>, find[identifier]=<raw in query> | found 1, found 1 | found 1, found 1 |
| control: entries the same identifier plus "/1": v3 GET <encoded>, v3 search, v1 find[identifier] | 404, found 0, found 0 | 404, found 0, found 0 |
| v3 entries PATCH <encoded>, then PUT <encoded>, then PATCH <raw>, then DELETE <encoded> | PATCH 200 sgv=77 \| PUT 200 sgv=88 \| raw PATCH 404 \| DELETE 200 stored n=1 isValid:false sgv=88 | PATCH 200 sgv=77 \| PUT 200 sgv=88 \| raw PATCH 404 \| DELETE 200 stored n=1 isValid:false sgv=88 |
| v3 entries PUT <encoded> for a new identifier | 201 \| stored n=1 identifier=X | 201 \| stored n=1 identifier=X |
| v3 treatments POST identifier scheme://a/b/c | 201 \| stored n=1 identifier=X | 201 \| stored n=1 identifier=X |
| v3 treatments GET /treatments/<encodeURIComponent: %3A %2F> | 200 identifier=X | 200 identifier=X |
| v3 treatments GET /treatments/<%2F only, ":" raw> | 200 identifier=X | 200 identifier=X |
| v3 treatments GET /treatments/<raw> | 404 | 404 |
| v3 treatments search ?identifier$eq=<encoded>, ?identifier=<encoded> | found 1, found 1 | found 1, found 1 |
| v1 treatments GET find[identifier]=<encoded>, find[identifier]=<raw in query> | found 1, found 1 | found 1, found 1 |
| control: treatments the same identifier plus "/1": v3 GET <encoded>, v3 search, v1 find[identifier] | 404, found 0, found 0 | 404, found 0, found 0 |
| v3 treatments PATCH <encoded>, then PUT <encoded>, then PATCH <raw>, then DELETE <encoded> | PATCH 200 carbs=77 \| PUT 200 carbs=88 \| raw PATCH 404 \| DELETE 200 stored n=1 isValid:false carbs=88 | PATCH 200 carbs=77 \| PUT 200 carbs=88 \| raw PATCH 404 \| DELETE 200 stored n=1 isValid:false carbs=88 |
| v3 treatments PUT <encoded> for a new identifier | 201 \| stored n=1 identifier=X | 201 \| stored n=1 identifier=X |
| v1 treatments POST identifier scheme://a/b/c, then re-send with carbs changed | 200 -> 200 \| stored n=1 carbs=12 | 200 -> 200 \| stored n=1 carbs=12 |
| v1 treatments DELETE /treatments/<encoded scheme://a/b/c> | 200 {"acknowledged":true,"deletedCount":0,"n":0}, left n=1 | 200 {"acknowledged":true,"deletedCount":0,"n":0}, left n=1 |
| v1 entries POST identifier scheme://a/b/c; v3 GET <encoded> | 200 \| stored n=1 \| v3 GET 200 identifier=X | 200 \| stored n=1 \| v3 GET 200 identifier=X |
