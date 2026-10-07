# WRITE-CONTRACT: the measured write matrix, and one write step behind the storage interface

*Contributor-facing.* **Snapshot, 2026-10-07. Status: draft specification for queue `WRITE-CONTRACT`,
awaiting the maintainer decisions in §6.** Nothing here is implemented. Measured against
`cgm-remote-monitor` `official/dev` `43289dde` (the merge of #8806) and `official/master` `92d08342`
(tag `15.0.8`); the as-built storage interface is `seam/t1-2-storage-interface` `81a1f6ce`. The
decisions this builds on are in the
[execution plan §4.1](nightscout-multitenancy-execution-plan-2026-09-14.md#41-the-write-contract-belongs-behind-the-seam)
and the [storage seam interface §4.4, §5 and §10](nightscout-storage-seam-interface-2026-09-14.md).
Item state: [`queue/QUEUE.md`](../../../queue/QUEUE.md). Defect facts:
[backfix register](../remedial/nightscout-backfix-register.md).

Every claim carries one of two marks. **[M]** measured: by the commands in §1.1 and §8, on the refs
above, Node 22.23.2, MongoDB 7.0.43. **[R]** read: from source at the ref named, not run.

---

## 0. Summary

- **The matrix** [M]: six collections × four write paths × eleven write forms, plus API v3 `PUT`:
  270 cells per build, 20 of them `n/a` (the path has no such operation), and 66 cross-path
  re-sends; 336 in all. No cell was invalid (a liveness check before and after every measured
  step). A second run on `43289dde` matched the first in every field except one `cache` value
  (§1.1, a known race).
- **How often the paths disagree** [M]: of the 66 (collection, write form) groups that two or more
  paths can perform, the stored result (documents, `_id` form, `srvCreated`/`srvModified`, v3
  history, v1 read) differs between paths in **33** on `dev` (47 on 15.0.8), and the emissions
  differ in 56. A record created through one path and re-sent without `_id` through another is
  stored twice in **38 of 66** ordered path pairs (36 on 15.0.8).
- **Two findings that cut across every collection** [M]: (1) only API v3 writes reach a client subscribed to the
  API v3 storage socket; writes of the same records through API v1, the socket `dbAdd`/`dbUpdate`/
  `dbRemove` and in-process callers never do, on `dev` and on 15.0.8 (§1.5 D8, candidate C4).
  (2) An identical re-send is a no-op on some paths and a full replacement, with a new
  `srvModified`, a v3 history entry and a change event, on others (D3, D4).
- **The proposed step** (§2): `lib/storage/write-step.js`, applied in `collectionFor` above both
  adapters, so the paths call `write(intent)` and never an adapter write method. Per item: `_id`
  form → target resolution (twins included) → outcome (insert / merge / replace / unchanged /
  refused) → server dates → adapter write → one change event per call.
- **The re-send rule** (§3): identical re-send is unchanged and answered with the stored ids; a
  differing re-send merges; one natural key per collection on every path; every path's writes
  reach the storage socket. Semver: **minor** if the maintainer picks merge-on-match (§4); a
  replace-on-match on the socket path would be **major** (ladder question 5).
- **Mismatch with the plan** [M]: the plan's example "a profile re-sent in upper case is stored
  twice while the same devicestatus is refused" holds for a record an older release stored with a
  string `_id` (`legacy-upper`). For a profile created by `dev` itself, a re-send with its own `_id`
  in either case answers **500** over API v1 and a duplicate-key error in-process, and is not
  stored twice (§1.6).

---

## 1. The matrix, measured

### 1.1 How it was measured

The harness is [`tools/qc/write-contract-matrix.js`](../../../tools/qc/write-contract-matrix.js).
Per execution plan rule 4 it exercises the shipping modules, not a copy: it boots the build in
its own process from the worktree named by `WC_WORKTREE`, exactly as `lib/server/server.js` does
(`bootevent`, `app`, an HTTP listener, `websocket`), with every module `require()`d by path from
that worktree. Requests go over a real listener: API v1 and v3 over HTTP, the socket path over
socket.io (`authorize`, then `dbAdd`/`dbUpdate`/`dbRemove`), and a second socket.io client
subscribed to the API v3 `/storage` namespace with a subject's access token, as AndroidAPS
NSClientV3 subscribes in websocket mode. The in-process path calls `ctx.<collection>.create`,
`save` and `remove`, as nightscout-connect's internal output does
(`nightscout-connect/lib/outputs/internal.js:40` [R]).

Booting in-process is what lets a cell record the two bus emissions no client sees directly
(`data-update`, which the in-memory cache consumes, and `storage-socket-*`, which the v3 storage
socket forwards) and the cache itself.

- **Database:** a dedicated container, `docker run -d --name wc-mongo --ulimit nofile=64000 -p
  27151:27017 mongo:7`; `db.version()` answered `7.0.43`. Each run uses a fresh database
  `wcm_<random>` and drops it at the end. Synthetic records only.
- **Node:** `n exec 22.23.2`.
- **Builds:** detached worktrees `externals/work/crm-wc-spec` at `43289dde` and
  `externals/work/crm-wc-1508` at `92d08342`, each after `npm ci`; `git status --porcelain -- lib`
  empty on both (recorded in each result file's `dirty_lib`).
- **Results:** [`dev-43289dde.json`](../../../tools/qc/results/write-contract-matrix/dev-43289dde.json),
  [`v15.0.8-92d08342.json`](../../../tools/qc/results/write-contract-matrix/v15.0.8-92d08342.json).
  The tables below are generated from them with `--compact`, `--divergence` and the cross-path
  listing (§8).
- **Liveness:** `GET /api/v1/status.json` answered 200 before and after every measured step; a
  cell that fails it is reported `INVALID`. 0 of 336 on either build (270 matrix cells and 66
  cross-path cells).
- **Repeatability:** a second full run on `43289dde` compared with `--compare`: 1 differing cell
  of 336, `entries v3 resend-identity`, in the `cache` field only (`held no-mills` once, `held`
  once). The `cache` field races the dataloader's reload of recent records after `data-received`;
  no conclusion below rests on it, and it is left out of the divergence counts.

**Each cell records:** the reply; the stored documents carrying the cell's marker field (so twins
are found whatever their `_id`), with the BSON type of each `_id`; `srvCreated`/`srvModified`
compared with the state before the step; whether `GET /api/v3/<col>/history/<cursor>` returns the
record, the cursor being the collection's largest `srvModified` before the step (what a reader
holds); the bus emissions; what the subscribed storage-socket client received; and, for deletes,
how many records a filtered v1 read returns.

**Write forms.** `create` (no `_id`); `resend-hex` / `resend-upper` (created through the same path
with a client 24-hex `_id`, then re-sent with it, in lower or upper case); `resend-oid` (the same,
the id as an ObjectId in-process and as Extended JSON `{"$oid": …}` over the wire);
`resend-identity` (re-sent with no `_id`, same body); `resend-near` (re-sent with the times one
second later); `legacy-lower` / `legacy-upper` (a record stored straight into MongoDB with a string
`_id`, no server dates and no `identifier`, as 15.0.6 and earlier stored it, then re-sent with
that id); `update` (v1 `PUT`, v3 `PATCH`, socket `dbUpdate`, in-process `save`); `update-put` (v3
`PUT`); `softdelete` (`isValid: false`: v1 `PUT`, v3 `DELETE`, socket `dbUpdate`, in-process
`save`); `harddelete` (v1 `DELETE /<col>/<id>`, v3 `DELETE ?permanent=true`, socket `dbRemove`,
in-process `remove`). Every path sends the same body, including the `date`, `utcOffset` and `app`
API v3 requires.

### 1.2 Legend

Each cell is `reply · stored · server dates · v3 history · emissions` (`· v1:<n>` for deletes).

- **reply** — `ok+id` accepted and told the stored id; `ok, no id` accepted, reply carries no id;
  `ok` accepted, no record in the reply; `empty` an empty array; `400`/`500` HTTP status;
  `refused` a socket ack naming a problem; `dup-err` a duplicate-key error to the callback.
- **stored** — number of documents, then each `_id`: `OID` ObjectId, `str` lower-case hex string,
  `STR` upper-case hex string; `:v2` carries the update, `:inv` has `isValid: false`.
- **server dates** — per document: `C` srvCreated set on a new document, `C=` kept, `C+` added
  where it was absent, `noC` absent; `M` set, `M+` advanced, `M=` unchanged, `noM` absent. `-` no
  document.
- **v3 history** — `h` returned valid, `h:del` returned with `isValid: false`, `–` not returned,
  `n/a` no v3 endpoint (activity).
- **emissions** — `du` a `data-update` whose documents carry `mills`; `du(no mills)` without;
  `du:rm` a `data-update` remove; `ws3:<event>` what the subscribed storage-socket client
  received; `–` nothing.

### 1.3 The matrix on `dev` `43289dde`

**entries**

| form | v1 | v3 | ws | inproc |
|---|---|---|---|---|
| create | ok+id · 1 OID · CM · h · du | ok+id · 1 OID · CM · h · du(no mills)+ws3:create | ok+id · 1 OID · CM · h · du | ok+id · 1 OID · CM · h · du |
| resend-hex | ok+id · 1 OID · C=M+ · h · du | ok+id · 1 str · C=M+ · h · du(no mills)+ws3:update | empty · 1 OID · C=M= · – · – | ok+id · 1 OID · C=M+ · h · du |
| resend-upper | ok+id · 1 OID · C=M+ · h · du | ok+id · 1 STR · C=M+ · h · du(no mills)+ws3:update | empty · 1 OID · C=M= · – · – | ok+id · 1 OID · C=M+ · h · du |
| resend-oid | ok+id · 1 OID · C=M+ · h · du | 500 · 0 · - · – · – | refused · 0 · - · – · – | ok+id · 1 OID · C=M+ · h · du |
| resend-identity | ok+id · 1 OID · C=M+ · h · du | ok+id · 1 OID · C=M+ · h · du(no mills)+ws3:update | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 1 OID · C=M+ · h · du |
| resend-near | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 2 OID,OID · C=M=,CM · h · du(no mills)+ws3:create | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 2 OID,OID · C=M=,CM · h · du |
| legacy-lower | ok+id · 1 str · noCM+ · h · du | ok+id · 1 str · C+M+ · h · du(no mills)+ws3:update | empty · 1 str · noCnoM · – · – | ok+id · 1 str · noCM+ · h · du |
| legacy-upper | ok+id · 1 str · noCM+ · h · du | 500 · 1 str · noCnoM · – · – | empty · 1 str · noCnoM · – · – | ok+id · 1 str · noCM+ · h · du |
| update | n/a | ok · 1 OID:v2 · C=M+ · h · du(no mills)+ws3:update | ok · 1 OID:v2 · C=M+ · h · du | n/a |
| update-put | n/a | ok · 1 OID:v2 · C=M+ · h · du(no mills)+ws3:update | n/a | n/a |
| softdelete | n/a | ok · 1 OID:inv · C=M+ · h:del · du:rm+ws3:delete · v1:0 | ok · 1 OID:inv · C=M+ · h:del · du · v1:0 | n/a |
| harddelete | ok · 0 · - · – · du:rm · v1:0 | ok · 0 · - · – · du:rm+ws3:delete · v1:0 | ok · 0 · - · – · du:rm · v1:0 | ok, no id · 0 · - · – · du:rm · v1:0 |

**treatments**

| form | v1 | v3 | ws | inproc |
|---|---|---|---|---|
| create | ok+id · 1 OID · CM · h · du | ok+id · 1 OID · CM · h · du+ws3:create | ok+id · 1 OID · CM · h · du | ok+id · 1 OID · CM · h · du |
| resend-hex | ok+id · 1 OID · C=M+ · h · du | ok+id · 1 str · C=M+ · h · du+ws3:update | ok+id · 1 OID · C=M= · – · – | ok+id · 1 OID · C=M+ · h · du |
| resend-upper | ok+id · 1 OID · C=M+ · h · du | ok+id · 1 STR · C=M+ · h · du+ws3:update | ok+id · 1 OID · C=M= · – · – | ok+id · 1 OID · C=M+ · h · du |
| resend-oid | ok+id · 1 OID · C=M+ · h · du | 500 · 0 · - · – · – | refused · 0 · - · – · – | ok+id · 1 OID · C=M+ · h · du |
| resend-identity | ok, no id · 1 OID · C=M+ · h · du | ok+id · 1 OID · C=M+ · h · du+ws3:update | ok+id · 1 OID · C=M= · – · – | ok, no id · 1 OID · C=M+ · h · du |
| resend-near | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 2 OID,OID · C=M=,CM · h · du+ws3:create | ok+id · 1 OID · C=M+ · h · – | ok+id · 2 OID,OID · C=M=,CM · h · du |
| legacy-lower | ok+id · 1 OID · CM · h · du | ok+id · 1 str · C+M+ · h · du+ws3:update | ok+id · 1 str · noCnoM · – · – | ok+id · 1 OID · CM · h · du |
| legacy-upper | ok+id · 1 OID · CM · h · du | 500 · 1 str · noCnoM · – · – | ok+id · 1 str · noCnoM · – · – | ok+id · 1 OID · CM · h · du |
| update | ok+id · 1 OID:v2 · C=M+ · h · du | ok · 1 OID:v2 · C=M+ · h · du+ws3:update | ok · 1 OID:v2 · C=M+ · h · du | ok+id · 1 OID:v2 · C=M+ · h · du |
| update-put | n/a | ok · 1 OID:v2 · C=M+ · h · du+ws3:update | n/a | n/a |
| softdelete | ok+id · 1 OID:inv · C=M+ · h:del · du · v1:0 | ok · 1 OID:inv · C=M+ · h:del · du:rm+ws3:delete · v1:0 | ok · 1 OID:inv · C=M+ · h:del · du · v1:0 | ok+id · 1 OID:inv · C=M+ · h:del · du · v1:0 |
| harddelete | ok · 0 · - · – · du:rm · v1:0 | ok · 0 · - · – · du:rm+ws3:delete · v1:0 | ok · 0 · - · – · du:rm · v1:0 | ok, no id · 0 · - · – · du:rm · v1:0 |

**devicestatus**

| form | v1 | v3 | ws | inproc |
|---|---|---|---|---|
| create | ok+id · 1 OID · CM · h · du | ok+id · 1 OID · CM · h · du+ws3:create | ok+id · 1 OID · CM · h · du | ok+id · 1 OID · CM · h · du |
| resend-hex | ok+id · 1 OID · C=M= · – · – | ok+id · 1 str · C=M+ · h · du+ws3:update | ok+id · 1 OID · C=M= · – · – | ok+id · 1 OID · C=M= · – · – |
| resend-upper | ok+id · 1 OID · C=M= · – · – | ok+id · 1 STR · C=M+ · h · du+ws3:update | ok+id · 1 OID · C=M= · – · – | ok+id · 1 OID · C=M= · – · – |
| resend-oid | 400 · 0 · - · – · – | 500 · 0 · - · – · – | refused · 0 · - · – · – | ok+id · 1 OID · C=M= · – · – |
| resend-identity | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 1 OID · C=M+ · h · du+ws3:update | ok+id · 1 OID · C=M= · – · – | ok+id · 2 OID,OID · C=M=,CM · h · du |
| resend-near | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 2 OID,OID · C=M=,CM · h · du+ws3:create | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 2 OID,OID · C=M=,CM · h · du |
| legacy-lower | ok+id · 1 str · noCnoM · – · – | ok+id · 1 str · C+M+ · h · du+ws3:update | ok+id · 1 str · noCnoM · – · – | ok+id · 1 str · noCnoM · – · – |
| legacy-upper | ok+id · 1 str · noCnoM · – · – | 500 · 1 str · noCnoM · – · – | ok+id · 1 str · noCnoM · – · – | ok+id · 1 str · noCnoM · – · – |
| update | n/a | ok · 1 OID:v2 · C=M+ · h · du+ws3:update | ok · 1 OID:v2 · C=M+ · h · du | n/a |
| update-put | n/a | ok · 1 OID:v2 · C=M+ · h · du+ws3:update | n/a | n/a |
| softdelete | n/a | ok · 1 OID:inv · C=M+ · h:del · du:rm+ws3:delete · v1:0 | ok · 1 OID:inv · C=M+ · h:del · du · v1:0 | n/a |
| harddelete | ok · 0 · - · – · du:rm · v1:0 | ok · 0 · - · – · du:rm+ws3:delete · v1:0 | ok · 0 · - · – · du:rm · v1:0 | ok, no id · 0 · - · – · du:rm · v1:0 |

**profile**

| form | v1 | v3 | ws | inproc |
|---|---|---|---|---|
| create | ok+id · 1 OID · CM · h · – | ok+id · 1 OID · CM · h · ws3:create | ok+id · 1 OID · CM · h · du | ok+id · 1 OID · CM · h · – |
| resend-hex | 500 · 1 OID · C=M= · – · – | ok+id · 1 str · C=M+ · h · ws3:update | ok+id · 1 OID · C=M+ · h · du | dup-err · 1 OID · C=M= · – · – |
| resend-upper | 500 · 1 OID · C=M= · – · – | ok+id · 1 STR · C=M+ · h · ws3:update | ok+id · 1 OID · C=M+ · h · du | dup-err · 1 OID · C=M= · – · – |
| resend-oid | 400 · 0 · - · – · – | 500 · 0 · - · – · – | refused · 0 · - · – · – | dup-err · 1 OID · C=M= · – · – |
| resend-identity | ok+id · 2 OID,OID · C=M=,CM · h · – | ok+id · 1 OID · C=M+ · h · ws3:update | ok+id · 1 OID · C=M+ · h · du | ok+id · 2 OID,OID · C=M=,CM · h · – |
| resend-near | ok+id · 2 OID,OID · C=M=,CM · h · – | ok+id · 2 OID,OID · C=M=,CM · h · ws3:create | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 2 OID,OID · C=M=,CM · h · – |
| legacy-lower | 500 · 1 str · noCnoM · – · – | ok+id · 1 str · C+M+ · h · ws3:update | ok+id · 1 str · noCM+ · h · du | dup-err · 1 str · noCnoM · – · – |
| legacy-upper | ok+id · 2 str,OID · noCnoM,CM · h · – | 500 · 1 str · noCnoM · – · – | ok+id · 1 str · noCM+ · h · du | ok+id · 2 str,OID · noCnoM,CM · h · – |
| update | ok+id · 1 OID:v2 · C=M+ · h · – | ok · 1 OID:v2 · C=M+ · h · ws3:update | ok · 1 OID:v2 · C=M+ · h · du | ok+id · 1 OID:v2 · C=M+ · h · – |
| update-put | n/a | ok · 1 OID:v2 · C=M+ · h · ws3:update | n/a | n/a |
| softdelete | ok+id · 1 OID:inv · C=M+ · h:del · – · v1:0 | ok · 1 OID:inv · C=M+ · h:del · ws3:delete · v1:0 | ok · 1 OID:inv · C=M+ · h:del · du · v1:0 | ok+id · 1 OID:inv · C=M+ · h:del · – · v1:0 |
| harddelete | ok · 0 · - · – · – · v1:0 | ok · 0 · - · – · ws3:delete · v1:0 | ok · 0 · - · – · du:rm · v1:0 | ok, no id · 0 · - · – · – · v1:0 |

**food**

| form | v1 | v3 | ws | inproc |
|---|---|---|---|---|
| create | ok+id · 1 OID · CM · h · – | ok+id · 1 OID · CM · h · ws3:create | ok+id · 1 OID · CM · h · du | ok+id · 1 OID · CM · h · – |
| resend-hex | ok+id · 1 OID · C=M+ · h · – | ok+id · 1 str · C=M+ · h · ws3:update | empty · 1 OID · C=M= · – · – | ok+id · 1 OID · C=M+ · h · – |
| resend-upper | ok+id · 1 OID · C=M+ · h · – | ok+id · 1 STR · C=M+ · h · ws3:update | empty · 1 OID · C=M= · – · – | ok+id · 1 OID · C=M+ · h · – |
| resend-oid | 400 · 0 · - · – · – | 500 · 0 · - · – · – | refused · 0 · - · – · – | ok+id · 1 OID · C=M+ · h · – |
| resend-identity | ok+id · 2 OID,OID · C=M=,CM · h · – | ok+id · 1 OID · C=M+ · h · ws3:update | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 2 OID,OID · C=M=,CM · h · – |
| resend-near | ok+id · 2 OID,OID · C=M=,CM · h · – | ok+id · 2 OID,OID · C=M=,CM · h · ws3:create | ok+id · 2 OID,OID · C=M=,CM · h · du | ok+id · 2 OID,OID · C=M=,CM · h · – |
| legacy-lower | ok+id · 1 OID · CM · h · – | ok+id · 1 str · C+M+ · h · ws3:update | empty · 1 str · noCnoM · – · – | ok+id · 1 OID · CM · h · – |
| legacy-upper | ok+id · 1 OID · CM · h · – | 500 · 1 str · noCnoM · – · – | empty · 1 str · noCnoM · – · – | ok+id · 1 OID · CM · h · – |
| update | ok+id · 1 OID:v2 · C=M+ · h · – | ok · 1 OID:v2 · C=M+ · h · ws3:update | ok · 1 OID:v2 · C=M+ · h · du | ok+id · 1 OID:v2 · C=M+ · h · – |
| update-put | n/a | ok · 1 OID:v2 · C=M+ · h · ws3:update | n/a | n/a |
| softdelete | ok+id · 1 OID:inv · C=M+ · h:del · – · v1:0 | ok · 1 OID:inv · C=M+ · h:del · ws3:delete · v1:0 | ok · 1 OID:inv · C=M+ · h:del · du · v1:0 | ok+id · 1 OID:inv · C=M+ · h:del · – · v1:0 |
| harddelete | ok · 0 · - · – · – · v1:0 | ok · 0 · - · – · ws3:delete · v1:0 | ok · 0 · - · – · du:rm · v1:0 | ok, no id · 0 · - · – · – · v1:0 |

**activity**

| form | v1 | v3 | ws | inproc |
|---|---|---|---|---|
| create | ok+id · 1 OID · noCnoM · n/a · – | n/a | ok+id · 1 OID · noCnoM · n/a · du | ok+id · 1 OID · noCnoM · n/a · – |
| resend-hex | ok+id · 1 OID · noCnoM · n/a · – | n/a | empty · 1 OID · noCnoM · n/a · – | ok+id · 1 OID · noCnoM · n/a · – |
| resend-upper | ok+id · 1 OID · noCnoM · n/a · – | n/a | empty · 1 OID · noCnoM · n/a · – | ok+id · 1 OID · noCnoM · n/a · – |
| resend-oid | 400 · 0 · - · n/a · – | n/a | refused · 0 · - · n/a · – | ok+id · 1 OID · noCnoM · n/a · – |
| resend-identity | ok+id · 2 OID,OID · noCnoM,noCnoM · n/a · – | n/a | ok+id · 2 OID,OID · noCnoM,noCnoM · n/a · du | ok+id · 2 OID,OID · noCnoM,noCnoM · n/a · – |
| resend-near | ok+id · 2 OID,OID · noCnoM,noCnoM · n/a · – | n/a | ok+id · 2 OID,OID · noCnoM,noCnoM · n/a · du | ok+id · 2 OID,OID · noCnoM,noCnoM · n/a · – |
| legacy-lower | ok+id · 1 OID · noCnoM · n/a · – | n/a | empty · 1 str · noCnoM · n/a · – | ok+id · 1 OID · noCnoM · n/a · – |
| legacy-upper | ok+id · 1 OID · noCnoM · n/a · – | n/a | empty · 1 str · noCnoM · n/a · – | ok+id · 1 OID · noCnoM · n/a · – |
| update | ok+id · 1 OID:v2 · noCnoM · n/a · – | n/a | ok · 1 OID:v2 · noCnoM · n/a · du | ok+id · 1 OID:v2 · noCnoM · n/a · – |
| softdelete | ok+id · 1 OID:inv · noCnoM · n/a · – · v1:1 | n/a | ok · 1 OID:inv · noCnoM · n/a · du · v1:1 | ok+id · 1 OID:inv · noCnoM · n/a · – · v1:1 |
| harddelete | ok · 0 · - · n/a · – · v1:0 | n/a | ok · 0 · - · n/a · du:rm · v1:0 | ok, no id · 0 · - · n/a · – · v1:0 |

### 1.4 Cross-path re-send

Created through the first path with no `_id`, then the identical body re-sent through the second;
the number is how many documents are stored. Bold is two. Where 15.0.8 differs it is shown.

| collection | first path | then v1 | then v3 | then ws | then inproc |
|---|---|---|---|---|---|
| entries | v1 | · | 1 | **2** | 1 |
| entries | v3 | **2** | · | **2** | **2** |
| entries | ws | **2** | 1 | · | **2** |
| entries | inproc | 1 | 1 | **2** | · |
| treatments | v1 | · | 1 | 1 | 1 |
| treatments | v3 | **2** (15.0.8: 1) | · | 1 | **2** (15.0.8: 1) |
| treatments | ws | 1 | 1 | · | 1 |
| treatments | inproc | 1 | 1 | 1 | · |
| devicestatus | v1 | · | 1 | 1 | **2** |
| devicestatus | v3 | **2** | · | 1 | **2** |
| devicestatus | ws | **2** | 1 | · | **2** |
| devicestatus | inproc | **2** | 1 | 1 | · |
| profile | v1 | · | 1 | 1 | **2** |
| profile | v3 | **2** | · | 1 | **2** |
| profile | ws | **2** | 1 | · | **2** |
| profile | inproc | **2** | 1 | 1 | · |
| food | v1 | · | **2** | **2** | **2** |
| food | v3 | **2** | · | **2** | **2** |
| food | ws | **2** | 1 | · | **2** |
| food | inproc | **2** | **2** | **2** | · |
| activity | v1 | · | n/a | **2** | **2** |
| activity | ws | **2** | n/a | · | **2** |
| activity | inproc | **2** | n/a | **2** | · |

### 1.5 Where the paths disagree

Each item cites the cells above. All [M] unless marked.

- **D1 · A client 24-hex `_id` on API v3.** Stored as the string, in the case sent (`str`, `STR`),
  for every v3 collection; every other path stores the ObjectId (`resend-hex`, `resend-upper`).
  Same on 15.0.8.
- **D2 · Extended JSON `{"$oid": …}`.** Accepted by v1 entries and treatments and by every
  in-process call; v1 devicestatus, profile, food and activity answer 400
  (`lib/api/shared/objectid-validation.js` [R]); the socket refuses it ("Invalid data"); API v3
  answers 500 and stores nothing (`resend-oid`).
- **D3 · Re-send with the record's own `_id`.** v1 and in-process entries (merge), treatments,
  food and activity (replace) write the record again even when the body is identical, and for the
  first four advance `srvModified`, so v3 history returns it again (and treatments and entries
  emit a `data-update`); devicestatus is not written and is answered
  with the stored `_id` (BF-116's fix); profile answers 500 over v1 and a duplicate-key error
  in-process. The socket returns the stored treatment or devicestatus unchanged, replaces the
  profile (matched on `startDate`), and for entries, food and activity answers an empty ack and
  writes nothing. API v3 replaces (`isDeduplication`).
- **D4 · Re-send with no `_id`, same body.** entries: one record on v1, v3 and in-process, two on
  the socket. treatments: one record everywhere, but the socket leaves it unchanged while v1, v3
  and in-process replace it. devicestatus and profile: two records on v1 and in-process, one on
  v3 and the socket. food: two records on v1, the socket and in-process, one on v3; v1 food
  `create` sets `created_at` to the server's time (`lib/server/food.js:51` [R]), so the v3 key
  never matches a v1-written food. activity: two records everywhere.
- **D5 · Re-send one second later.** Two records on every path and collection except socket
  treatments, whose similar-treatment match (±2 s, `lib/server/websocket.js:618-656` [R]) keeps one
  record and rewrites its `created_at` and `srvModified`, **with no `data-update` and no storage
  event** (`resend-near`; candidate C5).
- **D6 · A record stored with a string `_id` by an older release.** entries v1 and in-process merge
  and keep the string `_id`; treatments, food and activity v1 and in-process store an ObjectId copy
  and remove the string; devicestatus is not written on v1, in-process or the socket; profile over
  v1 answers 500 in lower case and **stores a second record** in upper case (in-process: duplicate
  error, then a second record); the socket answers an empty ack for entries, food and activity,
  returns treatments and devicestatus unchanged and replaces the profile keeping the string; API v3
  replaces in lower case keeping the string, and answers **500 and writes nothing in upper case**
  (`legacy-lower`, `legacy-upper`; candidate C2).
- **D7 · Replies.** A v1 or in-process treatment re-send matched by its fallback key is answered
  with no `_id` (`ok, no id`; same on 15.0.8; candidate C3), where an entries re-send is answered
  with the stored `_id`. A hard delete answers `{acknowledged, deletedCount, n}` for v1 entries,
  treatments and devicestatus and `{}` for v1 profile, food and activity. v3 answers 201 to a
  create and 200 with `isDeduplication` to a re-send.
- **D8 · Emissions.** Only API v3 writes reach the subscribed storage-socket client: in 0 of the
  190 measured non-v3 cells on either build, against 50 of 60 v3 cells on `dev` (45 on 15.0.8), including v3 create in
  the same run as the positive control (candidate C4). v1 and in-process profile and food writes
  emit no `data-update`; the socket path emits one for every collection. API v3 entries are emitted
  without `mills` (by design: `DERIVE_FOR_CACHE` in
  `lib/api3/storage/mongoCachedCollection/index.js:159` derives for treatments and devicestatus
  only, and entries readers use `date` [R]). A v3 soft delete emits `du:rm`; a v1 or socket soft
  delete emits an update carrying `isValid: false`, which `lib/server/cache.js` treats as a removal
  [R]; the cache ends without the record either way.
- **D9 · Server dates.** activity is never stamped, on any path (not served by API v3; the
  `srv-dates` header [R]). The no-op answers in D3 and D4 leave `srvModified` as it was; every
  replace advances it.
- **D10 · Soft delete.** For the five v3 collections, every path's `isValid: false` write hides the
  record from v1 reads and v3 history reports it deleted. activity still returns it on v1 reads
  (`soft-deleted` is not called from `lib/server/activity.js` [R]).
- **D11 · Hard delete.** Stored state agrees on every path: the record is gone and v3 history does
  not report it (BF-122's decision (a), 2026-09-26).

**Cross-path (§1.4).** API v1 entries match on `sysTime` + `type` (`upsertQueryFor`, `lib/server/entries.js:301`
[R]), API v3 on `date` + `type`; the socket does not match entries. So an entry written through
v3 or the socket and re-sent through v1 is stored twice. A treatment written through API v3 and
re-sent through v1 or in-process is stored twice on `dev` and once on 15.0.8: BF-121's decided
rule that a write without identity cannot replace a record with an `identifier`.

### 1.6 The plan's counts, re-measured, and the mismatch

[M] on `43289dde`:

- `git grep -l "srv-dates')\|soft-deleted')\|object-id-forms')\|treatment-fallback-key')" -- lib`:
  **18 files**, as §4.1 states. Per module, `git grep -l "<module>')" -- lib | wc -l`:
  object-id-forms 12, srv-dates 11, soft-deleted 7, treatment-fallback-key 2, as §4.1 states.
  Module sizes 169 / 222 / 53 / 67 lines, as stated.
- `git grep -n processRawDataForRuntime -- lib/server lib/data lib/api3` lists 20 lines: the
  definition (`lib/data/ddata.js:29`), one comment (`mongoCachedCollection/index.js:148`) and
  **18 calls in six files**, seven in `lib/server/websocket.js`, as stated. Fifteen are on write paths
  (`websocket.js` 7, `treatments.js` 5, `entries.js` 1, `devicestatus.js` 1,
  `mongoCachedCollection/index.js` 1); three are the dataloader's read side
  (`lib/data/dataloader.js` 3), which the step does not take over.

**Mismatch.** §4.1, `OID-STORAGE-HELPER` and `WRITE-CONTRACT` cite "a profile re-sent in upper case
is stored twice while the same devicestatus is refused". On `43289dde` that is the `legacy-upper`
row: a profile stored with a lower-case string `_id` by an older release, re-sent through v1 in
upper case, is stored twice; the same devicestatus re-send is answered 200 with the stored `_id`
and not written. For a record created by `43289dde` itself (`resend-upper`) the profile re-send
answers 500 and stores nothing more, and the devicestatus re-send behaves as above. The queue
note's other clause, "devicestatus and profile create keep the legacy string and collide;
treatments, food and activity move it to an ObjectId", matches the `legacy-lower` row except that
devicestatus no longer collides (it answers 200, BF-116).

### 1.7 Non-vacuity

Each rule column was broken in one place and the matrix re-run on the identical setup; the clean
run is the positive control, and the restored file must reproduce it.
[`tools/qc/write-contract-ablate.sh`](../../../tools/qc/write-contract-ablate.sh) runs all six on
a detached worktree of `43289dde`
([log](../../../tools/qc/results/write-contract-matrix/ablations-43289dde.txt)); every break
changed exactly the cells listed and every revert matched the clean run.

| rule | break (one line) | cells that went red, and how |
|---|---|---|
| `_id` form | `websocket.js` `storeIdAsObjectId` returns at once | treatments and food `ws resend-hex`/`resend-upper`: stored `OID` → `str`/`STR` |
| server dates | `websocket.js` generic `dbAdd` skips `stampCreated` | food and entries `ws create`: `CM` → `noCnoM`, history `h` → `–` |
| soft delete (read half) | `treatments.js` `query_for` without `softDeleted.visible` | treatments `softdelete` on all four paths: `v1:0` → `v1:1` |
| re-send identity | `treatments.js` `upsertQueryFor` fallback can never match | treatments `v1`/`inproc` `resend-identity`: one record → two |
| derived copy | `DERIVE_FOR_CACHE = {}` | treatments and devicestatus `v3 create`/`update`: `du` → `du(no mills)` |
| storage event | `insert.js` drops `storage-socket-create` | treatments `v3 create`: `ws3:create` → nothing |

Two things the run showed about the instrument. The first attempt at the storage-event break
named the wrong line, changed nothing, and reported a green break; the script now stops with
`ABLATION-NO-OP` when a substitution changes no file. Both of its guards were seen to fail
(`ABLATION-NO-OP` on an unmatched pattern; `MISMATCH` on an expectation listing one of two cells
that changed). And the soft-delete break turned all four paths red at once: the read half of that
rule is already one place per collection (`query_for`); the write half is per path.

The existing regression net was checked the same way [M]: #8758's
`tests/api.crud-by-id.matrix.test.js` passes 336 of 336 on `43289dde` against `wc-mongo`; with the
`_id`-form break above it fails 18, twelve of them titled `ws create | <collection> |
lower|upper -> [ObjectId]`.

---

## 2. The proposed write step

### 2.1 Where it sits

```
 API v1 routes   API v3 generic ops   socket dbAdd/dbUpdate/dbRemove   in-process callers (connector, plugins)
      \                 |                         |                              /
       `---- route rules above the seam: auth, v1 400s for non-hex _id, query coercion (§3.4) ----'
                                         |
                       lib/storage/write-step.js   write(intent)   <- the five rules, once
                                         |
                 seam interface (§10.1): findFiltered, insertMany, bulkUpsert, replaceFiltered,
                                          updateMany, deleteMany
                         /                                      \
              MongoCollection (+ mongoose validation)      PgCollection (RLS)
```

`collectionFor(ctx, env, colName)` (`lib/storage/collection-for.js` on the seam [R]) wraps the
collection it returns in the step. The returned object keeps the read methods and replaces the
write methods with `write(intent)`; the adapters' write methods are reachable only from the step.
That is what makes "every write from every path" checkable (gate G2).

### 2.2 Interface

```js
// lib/storage/write-step.js
// rules: the collection's entry in COLLECTION_RULES (below); events: the change-event sink.
function writeStep (collection, rules, events) -> {
  ...readMethods,                          // findOne, findFiltered, count, getLastModified
  write (intent) -> Promise<WriteResult>
}

intent = {
  op: 'create' | 'update' | 'patch' | 'softDelete' | 'delete',
  docs:   [doc, ...],                      // create, update (whole documents)
  target: { identifier } | { _id },        // patch, softDelete, delete; update when the doc has no _id
  set, unset,                              // patch: the same two maps as updateMany (§10.3)
  near:   { ms, fields },                  // create only; the socket's similar-treatment match (§6 Q4)
  origin: { path: 'v1' | 'v3' | 'socket' | 'internal' | 'loader', subject }
}

WriteResult = {
  items: [{ index, outcome, _id, identifier, reason }],
  // outcome: 'inserted' | 'merged' | 'replaced' | 'unchanged' | 'deleted' | 'not-found' | 'refused'
  event: ChangeEvent | null                // null when no item changed stored state
}

COLLECTION_RULES = {
  // keys are tried in order; the first that resolves a target wins
  treatments:   { keys: ['identifier', '_id', 'clientIdentity', ['created_at', 'eventType']],
                  amountsWithoutIdentity: ['carbs', 'insulin'], onMatch: 'merge', v3: true, derive: true },
  entries:      { keys: ['identifier', '_id', ['date', 'type']], onMatch: 'merge', v3: true, derive: false },
  devicestatus: { keys: ['identifier', '_id', 'NSCLIENT_ID', ['created_at', 'device']], onMatch: 'merge', v3: true, derive: true },
  profile:      { keys: ['identifier', '_id', 'NSCLIENT_ID', ['created_at']], onMatch: 'merge', v3: true },
  food:         { keys: ['identifier', '_id'], onMatch: 'merge', v3: true },
  activity:     { keys: ['_id'], onMatch: 'merge', v3: false }
};
```

The natural keys and `onMatch` above are the recommendation, not decided: §6 Q1–Q3. `clientIdentity`
is `treatment-fallback-key`'s `CLIENT_IDS` with its "a write without identity matches only a record
without identity" rule (BF-121, BF-141).

The step's adapter calls are only methods both backends implement, or the dependency is named: on
the seam, PostgreSQL declines `insertMany`, `updateMany` and `replaceFiltered` (they throw, naming
themselves) and ignores `bulkUpsert`'s `mode` (BF-21, open)
([write-path research §2, §5](../../60-research/tenancy/seam-write-path-2026-09-15.md), measured
2026-09-15 on `239f8c25`; [R] here, not re-measured). BF-22 (dotted keys in `updateOne`) is reachable
through `patch`. The step on PostgreSQL waits on those.

### 2.3 Order of the rules

§4.1 lists what the seam owes, not an order. Applied per item, within one call:

1. **`_id` form** (`object-id-forms`). `{"$oid": …}` and any 24-hex string, either case, become the
   ObjectId; an empty `_id` is dropped; a non-hex string keeps today's per-collection rule (moved
   to `identifier` for treatments and entries under `UUID_HANDLING`, kept as given elsewhere).
2. **Target resolution** (re-send identity: `treatment-fallback-key` and the `keys` above; twins).
   One read per batch for all items. An `_id` matches every stored form (`idForms`); where both
   halves of a twin match, the ObjectId copy is the target (BF-117's sort) and the string form is
   listed for removal. A soft-deleted record (`isValid: false`) is not a target for `create`: a
   re-send of a deleted record is stored again (BF-135's decision).
3. **Outcome.** No target: `inserted`. Target equal to the item on every client field:
   `unchanged`, nothing written. Otherwise `onMatch` (`merged` or `replaced`), subject to the
   immutable-field rule: on API v3 its full set (`isSameAsStored`, BF-136), which can answer
   `refused`; on the other paths only the server-owned fields (`srvCreated`, `srvModified`,
   `identifier`), which they overwrite silently today. Applying v3's full set there would turn
   today's 2xx into 4xx for a real client (ladder question 4, major).
   `softDelete` sets `isValid: false` (`soft-deleted`); `delete` removes every form (BF-110's
   decided behaviour).
4. **Server dates** (`srv-dates`). `inserted`: `stampCreated`. `merged`/`replaced`: `carry`
   (`srvCreated` and `identifier` kept, new `srvModified`). `patch`/`softDelete`:
   `stampModified`. `unchanged`, `delete`: none. Stamped immediately before the adapter call, from
   the one process clock (BF-144).
5. **Adapter write**, then the string-twin removal directly after the write it belongs to (BF-130's
   ordering), with `replaceFiltered` (no upsert) where the target was resolved, so a record deleted
   between resolution and write is not recreated (§10.7).
6. **One change event** for the call, carrying every item whose stored state changed; none if
   every item was `unchanged`, `not-found` or `refused`.

Server dates come after resolution because `carry` needs the target. Soft delete sits in step 3 as
a write outcome; its read half (leave `isValid: false` out unless the caller names `isValid`) stays
on the read path, as `findFiltered`'s default, where §1.7's break showed it is already one place
per collection.

### 2.4 The change event

Under `TENANCY_MODE=single` the step emits:

```js
ChangeEvent = {
  collection: 'treatments',
  op: 'insert' | 'update' | 'delete',      // softDelete is 'update' with isValid: false
  docs:    [stored],                       // as stored, _id as lower-case hex; absent for 'delete'
  runtime: [stored + mills, endmills],     // ddata.processRawDataForRuntime on a copy, when rules.derive
  removed: { ids: ['<hex>'], count },      // 'delete'
  srvModified: <largest in the call>,
  origin: { path, subject }
}
```

One subscriber, `lib/server/write-events.js`, fans it out to today's three consumers, so none of
them changes in the first step:

| consumer today | gets | replaces |
|---|---|---|
| `lib/server/cache.js` (`data-update`) | `op: 'update'` with `runtime` (or `docs`); `op: 'remove'` with `object-id-forms.cacheRemoval(asked, count)` | 15 write-side `processRawDataForRuntime` calls and the per-path `data-update` emits (§1.6) |
| `lib/api3/storageSocket.js` (`storage-socket-create/update/delete`) | the v3-normalised doc (`identifier`, no `_id`), or the identifier on delete | the three emits in `lib/api3/generic/{create,update,patch,delete}`; adds every non-v3 path (D8) |
| dataloader trigger (`data-received`) | one per event | the per-path `data-received` emits |

Under `TENANCY_MODE=multi` the in-process event is not the transport. D6's change feed is read
from the replication slot, so the feed record is derived from the committed row. That puts three
constraints on the event's shape, so `single` and `multi` carry the same information:

- every field except `runtime` and `origin` must be a stored column or derivable from one: `op`
  from the row (`insert` when no prior row; `isValid: false` for a soft delete), `srvModified`
  stored;
- `runtime` is not in the feed: `ns-evaluator` derives on its own slice (§7b);
- a hard delete arrives from the slot with the replica identity only. The storage socket addresses
  a deleted record by `identifier`, so either the table's replica identity includes `identifier`
  or the feed reader maps the key to it. [R]: not measured; it lands on Phase 4 (T4.1).

### 2.5 What stays where it is

Route rules (authorization, v1's 400 for a non-hex `_id` on profile/devicestatus/food/activity,
query coercion §3.4) stay above the seam. Mongoose validation stays inside the MongoDB adapter
(§4 item 3). The in-memory cache stays for `single` (D4). Runtime-derived fields are not stored.
The dataloader's three read-side derivations stay.

---

## 3. The unified re-send rule

For each divergence, what the contract picks, why, and who would see it. Client facts are from the
[consumer-impact survey](../../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md), its
[client maps](../../../reports/consumer-impact-15.0.9/clients/) and the
[#8758 client survey](../../../reports/consumer-impact-15.0.9/clients-8758.md), all read-derived
except where a replay cell is cited; the server behaviour is the matrix above.

| # | today (§1.5) | contract | why | clients that would see a change |
|---|---|---|---|---|
| U1 | D1, D2: v3 keeps a client hex `_id` as a string; `{$oid}` 400/refused/500 depending on path | every path stores the ObjectId; `{$oid}` accepted everywhere the route accepts an `_id` | one form per id, which `OID-MIGRATION` assumes | none in the corpus: AndroidAPS never sends `_id` to v3 (clients-8758 Q3); no client in the survey sends `{$oid}`. `mongoexport` writes it, which is why `dropEmptyId` accepts it (`object-id-forms.js` header [R]) |
| U2 | D3, D4: an identical re-send replaces on v1/v3/in-process (new `srvModified`, history entry, event) and is a no-op on the socket and for devicestatus | identical re-send is `unchanged`: nothing written, no `srvModified`, no event, answered with the stored ids | a retry is not an edit; the no-op already exists on two paths | every uploader that retries a whole batch: Loop ("a failed batch is re-sent whole", clients-8758 Loop (e)), Trio (chunks re-posted, Trio S15), xDrip+ (entries), tconnectsync; AndroidAPS NSClientV3 stops receiving those records again through v3 history |
| U3 | D3, D4: a differing re-send replaces on v1/v3/in-process, merges for v1 entries, is ignored on the socket | `merge` on match for every collection and path; an explicit update (`PUT`, v3 `PUT`) still replaces | merge loses no stored field (ladder question 5); replace on the socket would drop fields another client added with `dbUpdate`; it also keeps the careportal `notes`/`enteredBy` that BF-136's trade-off loses | AndroidAPS 3.4.x socket client: an edit re-sent after a lost ack is applied instead of left stale (BF-121's "left by design"); a v1 re-POST no longer removes fields it omits (no client in the survey relies on that: Trio and tconnectsync edit by delete-then-POST, Loop and xDrip+ by `PUT`) |
| U4 | D4, §1.4: entries keyed `sysTime`+`type` on v1, `date`+`type` on v3, not at all on the socket; devicestatus and profile not keyed on v1; food never matches | one key per collection on every path: entries `date`+`type`; devicestatus `created_at`+`device`; profile `created_at`; food and activity by id only | the 38 cross-path twins; a key that differs by path cannot be one rule | Loop and Trio devicestatus re-sends stop being stored twice (clients-8758 Loop (e): "inserts again (a second copy, same on every build)"); AndroidAPS 3.4.x socket entries (`nsAdd("entries", …)`, `DataSyncSelectorV1.kt:434` @`598e2eb39c`) re-sent after a 60 s ack timeout (androidaps S15) stop duplicating; xDrip+ and xDrip4iOS entries are unchanged in effect (already matched on v1), provided their `date` and `sysTime` name the same instant, which is unmeasured (§6 Q3) |
| U5 | D5: ±2 s similar-treatment match on the socket only | kept as an explicit `near` option the socket path passes (§6 Q4) | removing it duplicates AAPS 3.4.x socket treatments; applying it elsewhere merges legitimate rapid boluses (seam interface §4.4) | none until decided |
| U6 | D7: v1 treatment re-send answered without `_id`; socket answers `[]` for some re-sends; profile 500 | every accepted item answered with its stored `_id` and `identifier`; a duplicate is never a 5xx, an error to the callback, or an empty ack; v3 keeps 201 create / 200 re-send | NightscoutKit maps a missing `_id` to `"NA"` and then skips the record's later `PUT`/`DELETE` (`NightscoutClient.swift:479-511` @`4ec9fd1`) | Loop: a carb whose POST was retried keeps an id it can edit and delete by; nightscout-connect and restore tools re-sending a profile get 200; librelink-up's v3 client, which throws on anything but 201 (librelink-up S13), is unchanged |
| U7 | D8: only v3 writes reach the storage socket | every path's writes reach it | AndroidAPS NSClientV3 defaults to websocket mode (`ns_use_ws`, default true, on master `598e2eb39c` and dev `7e1d537d49`) and stops polling after its first load (`NSClientV3Plugin.kt:1132` on dev) | AndroidAPS NSClientV3: careportal, Loop, Trio, xDrip+, connector and AAPS-3.4-socket records arrive while connected instead of only after a full sync. Read; whether a socket reconnect triggers a history load was not traced |
| U8 | D9, D10: activity has no server dates and ignores `isValid` | §6 Q5 | activity has no v3 endpoint and no client in the survey soft-deletes it | none known |

---

## 4. Semver class

From the [semver policy](../modernization/semver-and-release-versioning-policy-2026-09-15.md) §2;
surfaces S1 (HTTP API and the socket) and S4 (stored document shapes).

| change | ladder question that answers yes | class |
|---|---|---|
| U1 `_id` form on v3; `{$oid}` accepted | 9 (an accepted input added); 10 for the stored form | minor |
| U2 identical re-send unchanged | 10: v3 history returns a different set of records for the same cursor | minor |
| U3 merge on match | 10 (stored body differs after the same request) | minor; **major under replace-on-match**, question 5 (a non-delete write drops a field) for the socket path |
| U4 one natural key per collection | 10 (a re-send that made two records makes one) | minor, provided no client sends two distinct records with the same key; unmeasured for devicestatus `created_at`+`device` (§6 Q3) — if one does, question 5 makes it major |
| U5 `near` kept for the socket | — | none |
| U6 replies carry the stored ids; no 5xx for a duplicate | 9 (5xx/empty to 2xx with a body), 10 (body shape) | minor |
| U7 storage-socket events from every path | 9 (emissions added); not question 8, which is alarms and notifications | minor; the release note says what AndroidAPS starts receiving |
| U8 activity dates/soft delete | 9 or none | minor or none |
| the step itself, with the matrix pinned to today | — | patch: "for every input a supported client sends, the bytes on the wire and the emissions are the same" (§2 PATCH), checkable with gate G1 |

Rule R3 classifies the release by its loudest row: minor, as §4.1 says, unless the maintainer picks
replace-on-match or a key that a client collides on.

---

## 5. The gates

Each gate is proved non-vacuous by a control that removes the step from one path; the gate must
go red naming that path and that rule.

| gate | what it asserts | break-it control |
|---|---|---|
| **G1** matrix | `write-contract-matrix.js` on the branch: `--divergence` reports stored state "same" for every group, and every cell equals a committed expected file (today's matrix with each §3 change applied) | route one path's create around the step (call the adapter directly): that path's re-send rows go red; plus `write-contract-ablate.sh`'s six breaks (§1.7), retargeted at the step |
| **G2** one door | outside `lib/storage`: no call to an adapter write method (`insertOne`, `insertMany`, `replaceOne`, `updateOne`, `updateMany`, `replaceFiltered`, `deleteOne`, `deleteMany`, `deleteManyOr`, `bulkUpsert`, `bulkWrite`) on a collection, no `require` of the four rule modules (18 files today), and no write-side `processRawDataForRuntime` (15 today) | add one direct `insertOne` in `lib/server/food.js`: red, naming the file |
| **G3** CRUD-by-id | #8758's `tests/api.crud-by-id.matrix.test.js` passes; cells the contract changes are edited and marked `CHANGED EXPECTATION` | the `_id`-form break: 18 red (§1.7) |
| **G4** both backends | `tools/qc/write-arm.js` with the step: MongoDB and PostgreSQL store the same document for every intent | reintroduce BF-21 (PostgreSQL ignores `mode`): the merge/replace rows differ |
| **G5** consumer replay | the consumer-replay lab's client shapes (AndroidAPS v3 and 3.4.x socket, Loop, Trio, xDrip+, xDrip4iOS, nightscout-connect, tconnectsync, oref0) give the §3 counts and replies | per client, the same shape against `43289dde` gives today's cells |
| **G6** soak | `tools/lab/rc-soak` A/B against `dev`: no difference beyond the declared §3 changes; A/A control clean | the derived-copy break (§1.7) shows as BF-146's late-record symptom |
| **G7** events | one event per call that changed state, none for `unchanged`; the storage-socket client receives create/update/delete for every path; `runtime` docs carry `mills` | the `derive` and `wire` breaks (§1.7) |
| **G8** loader parity | for `BFQ-CAP02`: a document imported through the loader is stored identically (minus `srvCreated`/`srvModified`) to the same document written through each path | let the loader call the adapter directly: twins and `_id` forms differ |

G1 and G2 can run on every commit; G4 waits on PostgreSQL behind the seam; G8 on `BFQ-CAP02`.
Controls seen to fail for this spec, on `43289dde`: G1's six breaks, G3's and G7's two (§1.7) [M].
The others are proposed and have not been run.

---

## 6. Decisions for the maintainer

**Q1 · What a re-send does to the record it matches.** (a) merge, every collection and path;
(b) replace, every collection and path; (c) as v1 does today, merge for entries and replace for
the rest. Evidence: (a) loses no stored field and keeps BF-136's careportal `notes`; (b) and (c)
change the socket path from "ignore" to "replace", which drops fields another client set with
`dbUpdate` — a major under the policy's question 5. Recommended: (a).

**Q2 · An identical re-send writes nothing.** (a) yes: no `srvModified`, no history entry, no
event; (b) no: keep v1/v3's replace. Evidence: the socket and devicestatus already do (a); under
(b) every retried batch from Loop, Trio or xDrip+ is re-announced to AndroidAPS through v3
history. Recommended: (a).

**Q3 · The natural key per collection.** entries: (a) `date`+`type` everywhere, (b) keep
`sysTime`+`type` on v1. devicestatus: (a) `created_at`+`device` on every path, (b) none on v1.
profile: (a) `created_at`, (b) `startDate` (the socket's). Evidence: §1.4's 38 twins; whether any
client sends two distinct statuses with the same `created_at` and `device` is unmeasured (a corpus
query in `ns-data` would settle it before deciding). Recommended: (a) for each, after that query.

**Q4 · The socket's ±2 s similar-treatment match.** (a) keep it as the socket's explicit `near`
option; (b) drop it; (c) apply it on every path. Evidence: seam interface §4.4 and BF-09 (deferred
past 15.0.9 on 2026-10-02): (b) duplicates AndroidAPS 3.4.x socket treatments, (c) merges rapid
boluses. AndroidAPS dev has removed the v1 socket client (`30fe4591a7`). Recommended: (a), retired
with that client.

**Q5 · activity.** (a) server dates and soft delete like the other five; (b) leave it out (no v3
endpoint). Evidence: no client in the survey reads activity history or soft-deletes activity.
Either is defensible; (a) makes the step uniform.

**Q6 · How it ships.** (a) two releases: the step with today's matrix pinned (patch, gate G1),
then the §3 changes (minor); (b) one minor. Evidence: G1 can hold (a)'s first release to "no
cell changed". Recommended: (a). Independently, U7 (C4) is live on 15.0.8 and could be fixed on
`dev` before `WRITE-CONTRACT`, which waits on `SEAM-REFRESH`.

---

## 7. Candidate defects found

Not allocated and not in the register; each with its reproduction. "Cell" means the matrix cell
in `dev-43289dde.json` (and `v15.0.8-92d08342.json`).

| # | what | reproduction | 15.0.8 | reach |
|---|---|---|---|---|
| C1 | API v3 stores a client 24-hex `_id` as the string, in the case sent, so new upper-case string `_id`s are created on `dev` (object-id-forms' header says they arise only from older releases) | cells `<col> v3 resend-hex`, `<col> v3 resend-upper` | same | no corpus client sends `_id` to v3 |
| C2 | API v3 answers 500 and stores nothing for `_id: {"$oid": …}`, and for a re-send whose `_id` form differs from the stored record's (a string-stored record re-sent in upper case) | cells `<col> v3 resend-oid`, `<col> v3 legacy-upper` | `resend-oid` same; `legacy-upper` answered 500 **and** stored a second record | no corpus client |
| C3 | a v1 or in-process treatment re-send matched by its fallback key is answered without `_id`; its `data-update` document also lacks `_id`, which `cache.js` drops (`filterForAge` keeps only documents with `_id` [R]) | cell `treatments v1 resend-identity` (`200 [1 no _id]`), `treatments inproc resend-identity` | same | Loop: NightscoutKit stores `"NA"` for a missing `_id` and skips later `PUT`/`DELETE` of that carb or dose [R], so a retried upload cannot later be edited or deleted on the site from Loop |
| C4 | API v1, socket and in-process writes emit no API v3 storage-socket event; a subscribed client receives nothing for them | every non-v3 cell `wire: none` (0 of 190 measured on `dev`); v3 create `wire: create` in the same run | same (0 non-v3 cells) | AndroidAPS NSClientV3 in its default websocket mode (read above); stated in BF-122's mechanism paragraph, not in its fix, and without an entry of its own |
| C5 | the socket's similar-treatment match rewrites `created_at` and `srvModified` and emits no `data-update` (only `data-received`), so the cache holds the old `created_at` until it reloads | cell `treatments ws resend-near` (`1 OID · C=M+ · h · –`) | same, without `srvModified` | AndroidAPS 3.4.x socket; the web UI's drag-to-move uses `dbAdd` (BF-09's notes) |
| C6 | a socket `dbAdd` of an entry, food or activity whose `_id` is already stored answers `[]`, the same as a failure | cells `entries ws resend-hex`, `food ws resend-hex`, `activity ws resend-hex` | same | AndroidAPS 3.4.x reads `[0]._id` from the ack but sends no `_id` on `dbAdd` (androidaps S7) |
| C7 | a profile re-sent with its own `_id` answers 500 (v1) or a duplicate-key error (in-process); devicestatus, which had the same 500, was fixed by BF-116 | cells `profile v1 resend-hex`, `profile inproc resend-hex` | same | nightscout-connect guards its profile copy with a `find[_id]` first; restore tools. Recorded in the object-id lab results as "unchanged behaviour" (2026-09-25), without a register entry |

The profile `legacy-upper` twin is not listed: queue `OID-STORAGE-HELPER` tracks it.

---

## 8. Reproduction

```sh
docker run -d --name wc-mongo --ulimit nofile=64000 -p 27151:27017 mongo:7
git -C externals/cgm-remote-monitor-official worktree add --detach ../work/crm-wc-spec 43289dde
(cd externals/work/crm-wc-spec && npm ci)
WC_WORKTREE=externals/work/crm-wc-spec WC_MONGO=mongodb://127.0.0.1:27151 \
  n exec 22.23.2 node tools/qc/write-contract-matrix.js --out dev.json
node tools/qc/write-contract-matrix.js --compact dev.json       # §1.3
node tools/qc/write-contract-matrix.js --divergence dev.json    # §1.5 counts, appendix
node tools/qc/write-contract-matrix.js --table dev.json         # every field, cross-path included
node tools/qc/write-contract-matrix.js --compare a.json b.json  # cell-by-cell
git -C externals/cgm-remote-monitor-official worktree add --detach ../work/crm-wc-ablate 43289dde
ln -s ../crm-wc-spec/node_modules externals/work/crm-wc-ablate/node_modules
WC_ABLATE_WORKTREE=externals/work/crm-wc-ablate tools/qc/write-contract-ablate.sh
docker rm -f wc-mongo
```

The harness writes; it must never be pointed at a real site. It stores no credential: the API
secret is generated per run.

---

## Appendix: divergence by group, `dev` `43289dde`

"stored state" compares documents, `_id` forms, server dates, v3 history and the v1 read; "reply"
compares the kind of answer (id given, no id, refused, failed, empty); "emission" compares bus
emissions and what the storage-socket client received. The number is how many distinct outcomes
the paths produced.

| collection | form | paths | stored state | reply | emission |
|---|---|---|---|---|---|
| entries | create | v1,v3,ws,inproc | same | same | differ (2) |
| entries | resend-hex | v1,v3,ws,inproc | differ (3) | differ (2) | differ (3) |
| entries | resend-upper | v1,v3,ws,inproc | differ (3) | differ (2) | differ (3) |
| entries | resend-oid | v1,v3,ws,inproc | differ (2) | differ (3) | differ (2) |
| entries | resend-identity | v1,v3,ws,inproc | differ (2) | same | differ (2) |
| entries | resend-near | v1,v3,ws,inproc | same | same | differ (2) |
| entries | legacy-lower | v1,v3,ws,inproc | differ (3) | differ (2) | differ (3) |
| entries | legacy-upper | v1,v3,ws,inproc | differ (2) | differ (3) | differ (2) |
| entries | update | v3,ws | same | same | differ (2) |
| entries | softdelete | v3,ws | same | same | differ (2) |
| entries | harddelete | v1,v3,ws,inproc | same | same | differ (2) |
| treatments | create | v1,v3,ws,inproc | same | same | differ (2) |
| treatments | resend-hex | v1,v3,ws,inproc | differ (3) | same | differ (3) |
| treatments | resend-upper | v1,v3,ws,inproc | differ (3) | same | differ (3) |
| treatments | resend-oid | v1,v3,ws,inproc | differ (2) | differ (3) | differ (2) |
| treatments | resend-identity | v1,v3,ws,inproc | differ (2) | differ (2) | differ (3) |
| treatments | resend-near | v1,v3,ws,inproc | differ (2) | same | differ (3) |
| treatments | legacy-lower | v1,v3,ws,inproc | differ (3) | same | differ (3) |
| treatments | legacy-upper | v1,v3,ws,inproc | differ (2) | differ (2) | differ (2) |
| treatments | update | v1,v3,ws,inproc | same | differ (2) | differ (2) |
| treatments | softdelete | v1,v3,ws,inproc | same | differ (2) | differ (2) |
| treatments | harddelete | v1,v3,ws,inproc | same | same | differ (2) |
| devicestatus | create | v1,v3,ws,inproc | same | same | differ (2) |
| devicestatus | resend-hex | v1,v3,ws,inproc | differ (2) | same | differ (2) |
| devicestatus | resend-upper | v1,v3,ws,inproc | differ (2) | same | differ (2) |
| devicestatus | resend-oid | v1,v3,ws,inproc | differ (2) | differ (3) | same |
| devicestatus | resend-identity | v1,v3,ws,inproc | differ (3) | same | differ (3) |
| devicestatus | resend-near | v1,v3,ws,inproc | same | same | differ (2) |
| devicestatus | legacy-lower | v1,v3,ws,inproc | differ (2) | same | differ (2) |
| devicestatus | legacy-upper | v1,v3,ws,inproc | same | differ (2) | same |
| devicestatus | update | v3,ws | same | same | differ (2) |
| devicestatus | softdelete | v3,ws | same | same | differ (2) |
| devicestatus | harddelete | v1,v3,ws,inproc | same | same | differ (2) |
| profile | create | v1,v3,ws,inproc | same | same | differ (3) |
| profile | resend-hex | v1,v3,ws,inproc | differ (3) | differ (2) | differ (3) |
| profile | resend-upper | v1,v3,ws,inproc | differ (3) | differ (2) | differ (3) |
| profile | resend-oid | v1,v3,ws,inproc | differ (2) | differ (2) | same |
| profile | resend-identity | v1,v3,ws,inproc | differ (2) | same | differ (3) |
| profile | resend-near | v1,v3,ws,inproc | same | same | differ (3) |
| profile | legacy-lower | v1,v3,ws,inproc | differ (3) | differ (2) | differ (3) |
| profile | legacy-upper | v1,v3,ws,inproc | differ (3) | differ (2) | differ (2) |
| profile | update | v1,v3,ws,inproc | same | differ (2) | differ (3) |
| profile | softdelete | v1,v3,ws,inproc | same | differ (2) | differ (3) |
| profile | harddelete | v1,v3,ws,inproc | same | same | differ (3) |
| food | create | v1,v3,ws,inproc | same | same | differ (3) |
| food | resend-hex | v1,v3,ws,inproc | differ (3) | differ (2) | differ (2) |
| food | resend-upper | v1,v3,ws,inproc | differ (3) | differ (2) | differ (2) |
| food | resend-oid | v1,v3,ws,inproc | differ (2) | differ (3) | same |
| food | resend-identity | v1,v3,ws,inproc | differ (2) | same | differ (3) |
| food | resend-near | v1,v3,ws,inproc | same | same | differ (3) |
| food | legacy-lower | v1,v3,ws,inproc | differ (3) | differ (2) | differ (2) |
| food | legacy-upper | v1,v3,ws,inproc | differ (2) | differ (3) | same |
| food | update | v1,v3,ws,inproc | same | differ (2) | differ (3) |
| food | softdelete | v1,v3,ws,inproc | same | differ (2) | differ (3) |
| food | harddelete | v1,v3,ws,inproc | same | same | differ (3) |
| activity | create | v1,ws,inproc | same | same | differ (2) |
| activity | resend-hex | v1,ws,inproc | same | differ (2) | same |
| activity | resend-upper | v1,ws,inproc | same | differ (2) | same |
| activity | resend-oid | v1,ws,inproc | differ (2) | differ (2) | same |
| activity | resend-identity | v1,ws,inproc | same | same | differ (2) |
| activity | resend-near | v1,ws,inproc | same | same | differ (2) |
| activity | legacy-lower | v1,ws,inproc | differ (2) | differ (2) | same |
| activity | legacy-upper | v1,ws,inproc | differ (2) | differ (2) | same |
| activity | update | v1,ws,inproc | same | differ (2) | differ (2) |
| activity | softdelete | v1,ws,inproc | same | differ (2) | differ (2) |
| activity | harddelete | v1,ws,inproc | same | same | differ (2) |

groups compared: 66; stored state differs in 33, reply kind in 33, emissions in 56

