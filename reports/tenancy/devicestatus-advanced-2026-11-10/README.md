# `devicestatus.advanced` in a multitenant tenant: client state measured against a single site

*Evidence record, lane E1, 2026-11-10 (contributor-facing). Measurement; not edited after capture.
Result: **not reproduced**. The setting differs between modes; the client state it controls does not,
for the frames a tenant sends. No code change was made.*

## Anchors

| tree | commit |
|---|---|
| cgm-remote-monitor base (#8898 batch join, `codex/batch-join-20261110`) | `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1` |
| lane worktree `externals/work/crm-devicestatus-advanced-20261110`, branch `codex/devicestatus-advanced-20261110` | `16a1fc2d45e59602eb6ec3e3bf6f506f35bcc5b1` (no commits; tree clean after the control) |
| `official/dev` (for reference) | `4a482627` |
| alignment `main` at the start of the lane | `276cc19a6` |
| node | v22.23.4; own `npm ci` in the lane worktree (871 packages), no borrowed `node_modules` |
| PostgreSQL | 16.15, dedicated container `postgres@sha256:9e2cf628…0a97`, removed afterwards; not the local 27017 mongod |

## 1. Claim under test (read-derived, from [tenant-extended-settings §6.3](../tenant-extended-settings-2026-11-10/README.md))

A single site defaults `devicestatus.advanced` to `true` (`lib/server/env.js:396`). A tenant leaves it
unset, so `lib/client/receiveddata.js:159` takes the replace branch instead of `mergeDataUpdate`, and the
browser's device status would differ from a single site's given the same frames.

No queue item covers it: `queue/work-queue.yaml` mentions it only as an open note on the tenant
extended-settings item (BF-232 lane).

## 2. Mechanism read on `16a1fc2d`

- `receiveddata.js:158-165`: with `advanced` set, `ddata.devicestatus = mergeDataUpdate(received.delta, …)`;
  without it, `ddata.devicestatus = received.devicestatus`.
- `receiveddata.js:46-49`: `mergeDataUpdate` returns the received array unchanged when `delta` is false.
  So the flag changes client state only for `delta:true` frames.
- The tenant's only `dataUpdate` source is `lib/server/realtime/projection.js:29`
  (`{ ...snapshot.ddata.dataWithRecentStatuses(), lastUpdated: at, delta: false }`), wired as the sole
  `create` in `lib/server/serve/preview-realtime.js:64`, sent by `protocol.js:110` and `:196`. The realtime
  README states main connections always receive full frames so absent rows replace browser state.
  `retroUpdate` (`protocol.js:159`) is stored in `client.retro` and does not read the flag.
- The single site sends incremental frames marked `delta: true` (`lib/data/calcdelta.js:8`, emitted at `lib/server/websocket.js:122`), which is
  where the flag matters.
- The only reader of `devicestatus.advanced` in `lib/` is `receiveddata.js:159`. A search of the client
  repositories in `externals/` (AndroidAPS, LoopCaregiver, LoopFollow, LoopWorkspace, nightguard,
  NightscoutKit, nightscout-reporter, nocturne, Trio, xDrip, xdripswift, DiaBLE, nightscout-connect,
  cgmsim-lib, mobile-ios, nightscout-roles-gateway) for `devicestatus…advanced` returned no file.

## 3. Reproduction: **not reproduced** (client state); the setting difference is reproduced

Harness: [`repro-base.js`](repro-base.js), synthetic data only (one synthetic Loop device, four statuses).
It runs the actual `realtime/protocol`, `realtime/runtime`, `realtime/projection`, tenant `snapshot`,
`ddata.dataWithRecentStatuses` and the projection-read SQL on the real PostgreSQL; only the replay
bookkeeping queries (checkpoint, clock, counts, the replay page) are answered by a double, as in
`tests/realtime-preview.test.js`. A recording socket authorizes on `/` with `status:true`; the store then
loses status 1 and gains status 4, and the recovery backstop fans out. The captured frames are fed to the
actual `lib/client/receiveddata.js` twice: with the tenant's served extended settings and with a single
site's.

```
node repro-base.js <lane worktree> <postgres admin URI>
```

Output on `16a1fc2d` (ids shortened to their last digit):

| | value |
|---|---|
| frames sent | 2 × `dataUpdate`, both `delta:false`; devicestatus `[1,2,3]` then `[2,3,4]` |
| tenant status route `extendedSettings.devicestatus` (`status.js:25` via `rest-context.js:25`) | `null` |
| tenant realtime status frame `extendedSettings.devicestatus` | `null` |
| single site (`env.js` → `plugins.extendedClientSettings` → `filteredSettings`) | `{"advanced":true,"days":1}` |
| client devicestatus, tenant settings | `[1,2,3]` → `[2,3,4]` |
| client devicestatus, single-site settings | `[1,2,3]` → `[2,3,4]` |
| verdict | `tenantFramesDiffer: false` |

The served setting differs between modes (**reproduced**). The client state it controls is identical for
the frames a tenant sends (**not reproduced**).

## 4. Controls

| control | change | result | meaning |
|---|---|---|---|
| detection (in the harness) | the same captured frames relabelled `delta:true` | tenant settings `[2,3,4]`; single-site settings `[1,2,3,4]`; `deltaControlDiffers: true` | the harness sees a merge-versus-replace difference when one exists |
| break the code under test | `projection.js:29` `delta: false` → `delta: true` in the lane worktree, harness re-run, file restored (`git status` clean, head `16a1fc2d`) | frames `delta:true`; client states diverge as in the detection row; `tenantFramesDiffer: true` | the green "no difference" depends on the full-frame shape, not on a harness that cannot see the flag |
| existing gate | `tests/realtime-preview.test.js` + `tests/receiveddata.merge.test.js` on the base | 36 passing, including "builds an actual recovered empty frame that clears the existing browser SGV consumer" (`RT_ACTUAL_FULL_RESET`, `delta === false` on the actual projection) | the frame shape is already held by a gate |

The break-it row also shows what giving a tenant `advanced:true` would mean if frames ever became
incremental: status 1, deleted from the store, would stay in the browser. Full frames are what make
deletion visible, and with full frames the merge and the replace give the same result.

## 5. Why the fix was not applied

The brief makes the fix conditional on reproducing the client-state difference. It did not reproduce, so
adding `advanced: true` to the tenant `EXTENDED` catalogue (`lib/server/tenant-app/environment.js`) would
change only the value reported in `/api/v1/status` and the realtime status frame, with no measured
consumer. The lane worktree and branch hold no commits.

## 6. For the coordinator

- **No register-worthy defect** found. Mechanism, for the record: the tenant omits a single-site default
  setting value from its status responses; the one reader of that value is a no-op for full frames, and
  the tenant sends only full frames.
- **Open, a decision rather than a defect:** under the standing rule (multitenant behaves as a single
  tenant), whether `/api/v1/status` for a tenant should report `devicestatus: {advanced: true, days: 1}`
  for parity of the reported value alone. No client in the corpus reads it. If adopted, it must be
  documented as display-only for tenants while frames stay full, and the break-it row above is the test
  that should accompany it.
- Suggested updates (not made here): the tenant extended-settings queue item's note
  "devicestatus.advanced … unset for a tenant (read-derived …)" can be closed as measured, not reproduced,
  citing this record; nothing for `decisions.md`, `contents.md` or the register unless the parity question
  above is taken.
