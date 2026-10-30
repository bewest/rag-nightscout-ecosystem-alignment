# ID-BATCH reply lab

What each uploader does with each candidate API v1 batch reply: whether it retries, and for how long;
whether it marks each item uploaded; whether an item is lost or stored twice; whether it reads the reply
`_id`. The evidence for the open questions (ii)-(vii) of the
[ID-BATCH design note](../../../docs/30-design/platform/id-batch-design-note-2026-10-30.md).

> Contributor-facing. Synthetic data only: the lab writes its own records into its own databases and
> must never be pointed at a real site.

Results: [RESULTS.md](RESULTS.md).

## What it runs

- **Server:** the cgm-remote-monitor prototype branch `proto/id-batch-replies` (the reply variants sit
  behind an opt-in; see `lib/api/shared/batch-reply.js` there), booted three times: `WRITE_VALIDATION`
  off, `WRITE_VALIDATION=reject`, and `WRITE_IDENTIFIER=strict`.
- **Clients:** [clients.js](clients.js) reproduces each client's handling of the reply, rule by rule,
  with the client's `file:line` at the pins it lists: Loop (NightscoutKit, NightscoutService, Loop's
  RemoteDataServicesManager), Trio, xDrip+, xDrip4iOS. AndroidAPS sends no v1 batch (API v3, one document
  per request) and is listed as not applicable. nightscout-connect is **run**, not modelled:
  [connect-run.js](connect-run.js) loads its real Nightscout output module and calls it cycle by cycle.
- **Per scenario x reply variant x client:** the client's batch goes to the real server with the variant's
  opt-in header (the harness plays a server whose default reply is that variant; the client logic never
  sees the header). The harness hands the reply to the client's rules and re-sends what the client would
  re-send, for up to three cycles. Then it reads MongoDB for how many records each item left.

## Run it

```sh
# a MongoDB for the lab (any free port; never a real site)
docker run -d --name idb-lab-mongo --ulimit nofile=64000:64000 -p 127.0.0.1:27803:27017 mongo:8
CRM_DIR=<worktree of proto/id-batch-replies, with npm ci done> IDB_MONGO=mongodb://127.0.0.1:27803 \
  node tools/lab/id-batch-replies/lab.js --out tools/lab/id-batch-replies/results/run.json
node tools/lab/id-batch-replies/report.js tools/lab/id-batch-replies/results/run.json   # the tables
docker rm -f idb-lab-mongo
```

| variable | default | meaning |
|---|---|---|
| `CRM_DIR` | required | the prototype build; its `node_modules` also supplies `mongodb`, `axios` and `qs` |
| `IDB_MONGO` | `mongodb://127.0.0.1:27803` | the lab's mongod; each server gets a database `idb_<mode>_<run>`, dropped at the end |
| `CONNECT_DIR` | `externals/nightscout-connect` | the nightscout-connect checkout that is run |
| `IDB_LOGS` | `$TMPDIR/idb-lab` | server logs and the transient connect spec; kept out of the repository |

The servers listen on 127.0.0.1:3921-3923. The API secret is generated per run and never written to the
results.
