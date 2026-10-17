# v3-identifier-immutable lab results, 2026-10-17

*Contributor-facing. Synthetic data only; nothing here is from a real site.*

Produced by `tools/lab/v3-identifier-immutable/lab.sh up && lab.sh run` (see [README](../README.md))
with:

```sh
V3I_REPO=<main checkout>/externals/cgm-remote-monitor-official
V3I_BUILDS="1508=15.0.8:3981 dev=fade2299:3982"
V3I_NM_1508=externals/work/crm-6a-replay-a/node_modules   # same package-lock.json as 15.0.8 (checked by cmp)
V3I_NM_dev=externals/work/crm-rc-018-n20/node_modules      # same package-lock.json as fade2299 (checked by cmp)
V3I_NODE=<n>/versions/node/22.23.2/bin/node
```

| build | what | head | `/api/v3/version` |
|---|---|---|---|
| 1508 | 15.0.8, the shipping release | `92d08342` | `15.0.8`, apiVersion `3.0.5` |
| dev | `official/dev` | `fade2299` | `15.0.9` (package version on dev), apiVersion `3.0.5` |

MongoDB: dedicated container `v3imm-mongo`, `mongo:7`, server version read back **7.0.43** (the
host's 127.0.0.1:27017 mongod, 3.6.8, was not used). Node 22.23.2. `AUTH_DEFAULT_ROLES=readable`;
v3 calls carry a JWT for an `admin` subject the probe creates, v1 calls the `api-secret` hash. The
same probes were run twice against the same servers (once by hand before `lab.sh` existed, once
through it); every cell was the same.

## Result

**The claim reproduces, at both refs, for all three collections.** A v3 `POST` with an identifier
that is already stored and a different `date`, `device` or `eventType` is answered **400** with
`"Field <name> cannot be modified by the client"`, and the stored record is unchanged: one copy,
first values kept. Nothing is stored twice. `PUT /api/v3/<col>/<identifier>` with a changed `date`
gives the same 400. The identical re-send (control) is `200` with the identifier, so the probe tells
the two apart.

Why POST reaches the check: `lib/api3/generic/create/operation.js:43-56` (15.0.8) looks the
identifier up and, on a match, calls `replace(..., { isDeduplication: true })`; `replace` runs
`update/validate.js`, whose loop skips only `identifier` under deduplication
(`update/validate.js:21-43` at 15.0.8, `:71-91` at `fade2299`).

| case | treatments | entries | devicestatus |
|---|---|---|---|
| e. identical re-send (control) | 201 → 200, n=1 | 201 → 200, n=1 | 201 → 200, n=1 |
| a. same id, `date` +60 s | 201 → 400 `date`, n=1 | 201 → 400 `date`, n=1 | 201 → 400 `date`, n=1 |
| b. same id, other `device`, `date` +1.5 s | 201 → 400 `date`, n=1 | 201 → 400 `date`, n=1 | 201 → 400 `date`, n=1 |
| b2. same id, other `device`, same `date` | 201 → 400 `device`, n=1 | 201 → 400 `device`, n=1 | 201 → 400 `device`, n=1 |
| c. same id, other `eventType` | 201 → 400 `eventType`, n=1 | — | — |
| d. `PUT` by id, `date` +60 s | 201 → 400 `date`, n=1 | 201 → 400 `date`, n=1 | 201 → 400 `date`, n=1 |

Every cell above is the same at 15.0.8 and `fade2299`. In b, `date` is the first immutable field the
loop meets, so the message names `date`; b2 shows `device` alone is enough.

### Where the two refs differ: a record first written through v1

| case | 15.0.8 `92d08342` | dev `fade2299` |
|---|---|---|
| f. v1 POST (identifier, `created_at`, no `device`), then v3 POST same identifier + `device`, same time | 200 → **400 `date`**; stored record has no `date`, no `device` | 200 → **200**; stored record now has `date` = `created_at` and the `device` |
| f2. as f, v3 time +60 s | 200 → 400 `date` | 200 → 400 `date` |

On dev, `isSameAsStored` (`update/validate.js:28-55` at `fade2299`) accepts a first `device` or
`app` on a record that has none and a `date` equal to the record's `created_at`; a different time is
still 400.

### v1, for contrast

| case | 15.0.8 | dev `fade2299` |
|---|---|---|
| v1 treatments: same `identifier`, `created_at` +60 s | 200 → 200, n=1, `created_at` moved to the second value | same |
| v1 entries: same `identifier`, `date` +60 s | 200 → 200, **n=2** (v1 entries match on `sysTime` + `type`, not `identifier`) | same |

So on the same server a time change under one identifier is an update on v1 treatments, a second
record on v1 entries, and a 400 on API v3.

## Is it a defect?

Not filed as one. The 400 is API v3's stated rule: swagger describes `date`, `device`, `app` and
`eventType` as "immutable by the client (it cannot be updated or patched)" (`lib/api3/swagger.yaml`
at 15.0.8, e.g. `:1426` for `eventType`), and `HTTP_400_IMMUTABLE_FIELD` is its own message. What it means for a
client-supplied identifier (Loop's phone-and-watch G7 example, an edited carb time) is the open
design question the reply raises ("whether `date` may change on an `identifier` match"). It is
recorded as an observation in the
[reply README](../../../../docs/30-design/platform/upstream-asks-loop-identifier/README.md).

Server logs: each v3 write whose identifier is not the server's computed UUID v5 printed
`APIv3: Identifier mismatch` (31 lines on the 15.0.8 build), as `resolveIdentifier` does; the
identifier was kept.

## Full table

| case | 15.0.8 `92d08342` | dev `fade2299` |
|---|---|---|
| treatments e. identical re-send (control) | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments a. same id, date +60 s, same device | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments b. same id, other device, date +1.5 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments b2. same id, other device, same date | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments c. same id, other eventType | 201 identifier -> 400 "Field eventType cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field eventType cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| treatments d. PUT by id, date +60 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone eventType=Carb Correction] |
| entries e. identical re-send (control) | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| entries a. same id, date +60 s, same device | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| entries b. same id, other device, date +1.5 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| entries b2. same id, other device, same date | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| entries d. PUT by id, date +60 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus e. identical re-send (control) | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 200 identifier \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus a. same id, date +60 s, same device | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus b. same id, other device, date +1.5 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus b2. same id, other device, same date | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field device cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| devicestatus d. PUT by id, date +60 s | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] | 201 identifier -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=t-1800 device=loop://lab-phone] |
| v1 treatments: same identifier, created_at +60 s | 200 -> 200 \| stored n=1 [created_at=t-1740] | 200 -> 200 \| stored n=1 [created_at=t-1740] |
| v1 entries: same identifier, date +60 s | 200 -> 200 \| stored n=2 [date=t-1800; date=t-1740] | 200 -> 200 \| stored n=2 [date=t-1800; date=t-1740] |
| treatments f. v1 record, then v3 same id + device, same time | 200 -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=undefined created_at=t-1800 device=undefined] | 200 -> 200 identifier \| stored n=1 [date=t-1800 created_at=t-1800 device=loop://lab-phone] |
| treatments f2. v1 record, then v3 same id + device, time +60 s | 200 -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=undefined created_at=t-1800 device=undefined] | 200 -> 400 "Field date cannot be modified by the client" \| stored n=1 [date=undefined created_at=t-1800 device=undefined] |
