# v3-identifier-immutable lab

Re-sends a record with the **same `identifier`** and a different `date`, `device` or `eventType`
through API v3, and through v1 for contrast, against several cgm-remote-monitor refs side by side.
It records the HTTP status, the reply's message, and what is stored, read **from mongo**. Built for
the [Loop identifier reply](../../../docs/30-design/platform/upstream-asks-loop-identifier/README.md)
(queue item `LOOP-ID-V3-IMMUTABLE`).

> Contributor-facing. Synthetic data only: the lab writes its own records and must never be pointed
> at a real site.

Latest results: [results/v3-identifier-immutable-2026-10-17.md](results/v3-identifier-immutable-2026-10-17.md).

## Run it

```sh
tools/lab/v3-identifier-immutable/lab.sh up     # mongo:7 in docker on 127.0.0.1:27183; archive and start each ref
tools/lab/v3-identifier-immutable/lab.sh run    # probes.js against each build, then one table
tools/lab/v3-identifier-immutable/lab.sh down   # stop the builds, remove the container
```

| variable | default | meaning |
|---|---|---|
| `V3I_BUILDS` | `1508=15.0.8:3981 dev=official/dev:3982` | `NAME=REF:PORT`, space separated |
| `V3I_REPO` | `externals/cgm-remote-monitor-official` | the clone each ref is `git archive`d from (read only) |
| `V3I_NM_<NAME>` | unset | a `node_modules` installed from the same `package-lock.json`, symlinked instead of `npm ci` |
| `V3I_STATE` | `$TMPDIR/v3-identifier-immutable` | archived builds, server logs, per-build JSON, the generated API secret |
| `V3I_MONGO_PORT` | `27183` | host port for the lab's mongod |
| `V3I_MONGO_IMAGE` | `mongo:7` | |
| `V3I_NODE` | `node` | the Node binary that runs the servers and probes |

The API secret is generated per lab into `$V3I_STATE/secret`; nothing secret lives in this
directory. Each build gets its own database, `v3imm_<NAME>`, dropped by `up`. Every case uses a
fresh random identifier, so `run` can be repeated without `up`.

## Cases

Each v3 case is two writes with one identifier; the cell is `first -> second | stored n=<copies
with that identifier> [fields]`. Times are relative to the run's start in seconds (`t-1800`).

| case | collections | second write |
|---|---|---|
| e. identical re-send (control) | treatments, entries, devicestatus | the same body again |
| a. same id, date +60 s | all three | `date` 60 s later, same `device` |
| b. same id, other device, date +1.5 s | all three | Loop's phone-and-watch example: `device` and `date` both differ |
| b2. same id, other device, same date | all three | only `device` differs |
| c. same id, other eventType | treatments | only `eventType` differs |
| d. PUT by id, date +60 s | all three | `PUT /api/v3/<col>/<identifier>` with `date` 60 s later |
| f / f2. v1 record, then v3 | treatments | record first written through v1 (no `date`, `device`, `app` stored), then v3 POST with the same identifier at the same time (f) or 60 s later (f2) |
| v1 treatments / v1 entries | v1 | the same identifier POSTed twice through v1, time 60 s later |
