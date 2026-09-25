# object-id lab

Replays the ways real clients send, find, edit and delete a record **by its own `_id`** against
several Nightscout builds side by side, and records what each build does. Built for PR
[nightscout/cgm-remote-monitor#8758](https://github.com/nightscout/cgm-remote-monitor/pull/8758)
(`bf/object-id-crud`, records keep their own `_id`), and for anything that later touches the same
paths.

> Contributor-facing. Synthetic data only: the lab seeds its own records and must never be pointed
> at a real site. Not medical advice.

Latest results: [results/object-id-2026-09-24.md](results/object-id-2026-09-24.md).

## Run it

```sh
tools/lab/object-id/lab.sh up      # mongo:7 in docker on 127.0.0.1:27181, then every build
tools/lab/object-id/lab.sh run     # probes.js against each build, then a cell-by-cell table
tools/lab/object-id/lab.sh down    # stop the builds, remove the container
```

| variable | default | meaning |
|---|---|---|
| `OID_BUILDS` | `a=externals/work/crm-6a-replay-a:3971 b=…crm-6a-replay-b:3972 d=…crm-bf-object-id-crud:3973` | `NAME=worktree:port`, space separated. Each worktree needs `npm ci` done |
| `OID_STATE` | `$TMPDIR/object-id-lab` | logs, per-build JSON output, and the generated API secret |
| `OID_MONGO_PORT` | `27181` | host port for the lab's mongod |
| `OID_MONGO_IMAGE` | `mongo:7` | |
| `OID_NODE` | `22.23.2` | Node version, through `n exec` |

The API secret is generated per lab into `$OID_STATE/secret`; nothing secret lives in this
directory. Each build gets its own database, `oidlab_<NAME>`, dropped by `up`. Every probe uses
fresh random ids, so `run` can be repeated without `up`.

To test a candidate fix, add it as another build, e.g.
`OID_BUILDS="d=…/crm-bf-object-id-crud:3973 f=…/my-fix:3975"`. To ablate, make a scratch
`git worktree add` of the head, revert one file, symlink `node_modules`, and add it as a build
(the 2026-09-24 results show one, build `r`).

## What a cell records

Every cell is a short string built from the same things: the HTTP status or socket reply; which
`_id` came back (`reply = stored`, `reply = sent`, `reply no _id`); the BSON type of each stored
`_id` (`OID` or `string`) and the number of stored documents carrying that hex in either form
(`n=`), both read **from mongo**, not from the API; and a marker field (`notes`, `rate`, `sgv`)
showing which copy took a write. `P-ID-0` checks the build answers before and after.

Records that stand for data older releases left behind (a `_id` stored as a string, a twin, a
v1/v3 pair) are written straight to mongo. Everything else goes through the build's own API.

## Probes

| probe | client shape | what it asks |
|---|---|---|
| P-ID-1 | Loop re-POSTs a dose with the ObjectId it cached from an earlier reply (`NightscoutUploader.swift`); xDrip4iOS retries a LibreLinkUp Sensor Start with a fixed hex `_id` | Does the re-send update the record or add a copy? |
| P-ID-2 | AndroidAPS 4.x GET/PATCH/DELETE `/api/v3/treatments/{identifier}` on v1 records (it treats 404 as done) | Can v3 reach a record stored with a string `_id`? |
| P-ID-3 | Entries re-sent without `_id`, with a different hex, onto a string record; upper-case `GET /entries/<id>` | Status, which `_id` the reply names, what is stored |
| P-ID-4 | Websocket `dbAdd`/`dbUpdate`/`dbRemove` (the web UI editor, AndroidAPS 3.x NSClient) | Does the socket act on what it acknowledges? |
| P-ID-5 | nightscout-connect 0.1.0 copies a profile with its source `_id`, then updates it only if `find[_id]` returns it | Does the connector's update-on-change work against this sink? |
| P-ID-6 | Restore from an export: POST the same record twice to profile, devicestatus, food, activity | Stored form, re-POST status, find and DELETE by id |
| P-ID-7 | A twin (string record plus the ObjectId copy a PUT on ≤15.0.8 left) deleted by its hex through v1, the websocket and v3 | How many copies are left |
| P-ID-10 | API v3 DELETE and PUT when a v1 record and a v3 copy of it both exist | Which document the write takes |
| P-ID-11 | `find[_id][$in]` with a string-stored and an ObjectId-stored id | Reads and bulk deletes by list |
| P-ID-12 | An auth subject posted with a hex `_id`, then deleted by it | Stored form and whether DELETE removes it |

P-ID-8 (how common string `_id`s and twins are in real data) and P-ID-9 (tconnectsync's profile
replace) are not in the lab yet; the queue items `OID-PREVALENCE` and `OID-LAB` track them, with the
replays through real client code (NightscoutKit, AndroidAPS `core/nssdk`, the real connector).

## Limits

- It replays request **shapes** read from each client's source, not the clients themselves.
- One database per build, `AUTH_DEFAULT_ROLES=readable`, one mongod version per run.
- Food's v1 GET ignores `find[_id]` on every build, so food cells count in mongo.
