# record-identity lab

What each cgm-remote-monitor path does with a client-sent `_id` and `identifier`: v1 POST, PUT,
GET and DELETE, API v3 POST, GET, PUT and DELETE, and the socket's `dbAdd`, `dbUpdate` and
`dbRemove`, for entries, treatments, devicestatus, profile and food, against several refs side by
side. It records the HTTP status, the reply's `_id`, and what is stored, read **from mongo**
(how many copies, and whether `_id` is an ObjectId or a string). Built for the
[record identity reference](../../../docs/10-domain/record-identity-reference.md) (queue item
`DOCS-RECORD-IDENTITY`). Same harness as [v3-identifier-immutable](../v3-identifier-immutable/README.md).

> Contributor-facing. Synthetic data only: the lab writes its own records and must never be pointed
> at a real site.

Latest results: [results/record-identity-2026-10-18.md](results/record-identity-2026-10-18.md).

## Run it

```sh
tools/lab/record-identity/lab.sh up     # mongo:7 in docker on 127.0.0.1:27184; archive and start each ref
tools/lab/record-identity/lab.sh run    # probes.js against each build, then one table
tools/lab/record-identity/lab.sh down   # stop the builds, remove the container
```

| variable | default | meaning |
|---|---|---|
| `RID_BUILDS` | `1508=15.0.8:3983 dev=fade2299:3984` | `NAME=REF:PORT`, space separated |
| `RID_REPO` | `externals/cgm-remote-monitor-official` | the clone each ref is `git archive`d from (read only) |
| `RID_NM_<NAME>` | unset | a `node_modules` installed from the same `package-lock.json`, symlinked instead of `npm ci` |
| `RID_STATE` | `$TMPDIR/record-identity` | archived builds, server logs, per-build JSON, the generated API secret |
| `RID_MONGO_PORT` | `27184` | host port for the lab's mongod |
| `RID_MONGO_IMAGE` | `mongo:7` | |
| `RID_NODE` | `node` | the Node binary that runs the servers and probes |

The API secret is generated per lab into `$RID_STATE/secret`; nothing secret lives in this
directory. Each build gets its own database, `ridlab_<NAME>`, dropped by `up`. Every case uses fresh
ids and its own minute, so `run` can be repeated without `up`. The probes need `mongodb`, `uuid` and
`socket.io-client` from the build's own `node_modules`.

## Cases

One row per case in the results; the case name says the request. Groups:

| group | what it sends |
|---|---|
| entries v1 | a new 24-hex `_id`; the same `_id` again at the same and at another time; another `_id` at a stored time; no `_id` twice; a UUID and a non-UUID string in `_id`; one `identifier` at two times; a new `identifier` at a stored time; a batch whose middle item collides; reads by `/entries/<hex>`, `find[_id]`, `find[identifier]`; DELETE by id, then the same `_id` again |
| treatments v1 | the same set for treatments, plus `identifier` and `_id` together, a stored record's `_id` under a new `identifier`, PUT by `_id` and by `identifier`, reads and DELETE by UUID and non-UUID identifiers |
| devicestatus v1 | a new 24-hex `_id`, the same again alone and inside a batch, identical bodies with no id, one `identifier` twice, a UUID `_id`, read and DELETE by id |
| profile, food v1 | POST with a 24-hex `_id`, then PUT with it; the same POST again; a UUID `_id` |
| API v3 | POST with no `identifier` (checked against `uuid.v5(device_date_eventType, "NightscoutRocks!")`); a body `_id`; GET by a v1 record's hex `_id`; soft and permanent DELETE, then GET, PUT and POST with the same `identifier`, for treatments, entries and devicestatus |
| socket | `dbAdd` with a 24-hex and a UUID `_id`, then `dbUpdate` and `dbRemove` by it; one `identifier` at two times; identical entries; the same entries `_id` twice; devicestatus at one `created_at` twice |
