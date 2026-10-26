# AndroidAPS in websocket mode: which Nightscout writes reach it (BF-164), and the API v3 settings read (BF-152)

> **Snapshot, 2026-10-25, against `official/dev` `b29f1bf7` (Node v22.23.4), with a client simulated from AndroidAPS `dev` `3905d352dd` (4.0.0 line) and checked against 3.4.2.6. Current: the evidence for the drafted note to the AndroidAPS developers and the input to the BF-164 and BF-152 decisions; the maintainer's 2026-10-25 direction is to research the AndroidAPS side before any Nightscout code changes for BF-164. Contributor-facing. Current decisions: [backfix register](../../30-design/remedial/nightscout-backfix-register.md) BF-164, BF-152; queue `BFQ-164`, `BFQ-152`.**

Session f4's API v3 contract lane. Lab: [`tools/lab/aaps-ws-delivery/`](../../../tools/lab/aaps-ws-delivery/README.md);
the run's own output is in its `results/2026-10-25-dev-b29f1bf7/`. Marks: **[M]** measured by the
lab, **[R]** read from AndroidAPS source, not run.

## 1. What the simulated client does

From AndroidAPS `dev` `3905d352dd`, each cited in the lab script (paths under
`plugins/sync/src/commonMain/kotlin/app/aaps/plugins/sync/nsclientV3/` unless stated) **[R]**:

- `ns_use_ws` defaults to true (`core/keys/.../BooleanKey.kt:250`; 3.4.2.6 `BooleanKey.kt:101`).
- On a successful storage-socket `subscribe` it runs a catch-up round (`WS_CONNECT`): for entries and
  treatments, if `/api/v3/lastModified` is newer than the cursor, page
  `/api/v3/<collection>/history/<cursor>` and set the cursor from the reply's ETag.
- **While the socket is connected it does not poll** (`NSClientV3Plugin.kt:372-385`, `409-410`,
  `1185`; 3.4.2.6 ticks only with websocket mode off, `NSClientV3Plugin.kt:308`).
- **A pushed create or update frame sets the collection's cursor to that document's `srvModified`**,
  a plain set, not a maximum (`ws/NsFrameHandler.kt:105-111`; 3.4.2.6
  `services/NSClientV3Service.kt:226-227`).
- On disconnect it clears its initial-load flag, so the next connect runs a catch-up round.

Not modelled: the first-ever load, and profile, food, settings and devicestatus loading. The client
is a returning one whose cursor starts one hour back, using a token of a subject with the built-in
`readable` role.

## 2. Results

Two real servers from `dev` `b29f1bf7` (`AUTH_DEFAULT_ROLES=denied`): a source, and the target with
nightscout-connect 0.1.0 reading the source. **[M]**, one run:

| write path | S1: socket up, 45 s | S2: reconnect, no v3 write between | S3: reconnect after a v3 write in the same collection |
|---|---|---|---|
| API v3 create (control) | pushed, 0.05 s (treatment) and 0.01 s (entry) | — | — |
| API v1 POST (the careportal posts here) | **not received** | received by the catch-up history call | **not received** (the record is in v3 history, `srvModified` 1792973899698) |
| main socket `dbAdd` | **not received** | received by the catch-up history call | **not received** (in v3 history, `srvModified` 1792973955604) |
| nightscout-connect (in process) | **not received** | received by the catch-up history call | **not received** |

The connector copied the source reading into the target after 190 s and 84 s in the two connector
arms. In each S3 arm the follow-up API v3 write arrived over the socket and moved the cursor
(treatments to 1792973901232 and 1792973957125, entries to 1792974284339), past the earlier record's
`srvModified`; the catch-up round on reconnect then fetched nothing.

**What this means for a follower.** On a site where an AndroidAPS master uploads through API v3, a
follower in websocket mode may never see treatments entered in the careportal, sent by a v1 uploader
or over the main socket, or readings written by nightscout-connect: the master's next v3 upload moves
the follower's cursor past them. Only a full sync fetches them. This depends on the model of the
client in §1 being right; the drafted note asks the AndroidAPS developers to confirm it.

**Why.** The `/storage` socket announces only writes made through API v3 (BF-164, reproduced
2026-10-07: 0 of 190 non-v3 write cells produced an event). Since 15.0.9 every write path sets
`srvModified`, so API v3 history returns those records; the loss comes from the cursor rule in §1.

## 3. BF-152: reading a settings document by identifier

Read and measured by the same lane:

- AndroidAPS's AAPSClient reads its settings through API v3 only in the 4.0.0 line
  (`LoadSettingsRunner`, identifiers `aaps` and `aaps-state`; `ClientControlRoundTrip.pollAck` reads
  `aaps_clientcontrol_ack_<clientId>`). Released 3.4.2.6 has no such read **[R]**.
- Client tokens made by the AndroidAPS master (`ClientTokens`, role `aaps-client`) carry
  `api:settings:admin` **[R]**.
- A follower using a token with the built-in `readable` role would get 403 under a strict read, which
  makes `LoadSettingsRunner` fail and, by the lane's reading of `NsLoadChain`, stops the round before
  the device-status and data-sync steps **[R]**.
- Under shiro-trie, `*:*:read` implies `api:settings:read` and any `api:settings:read:<x>` **[M]**, so a
  narrower scope would need a new verb that `readable` does not imply.
- Step 1 of the maintainer's staged ladder is on local branch `bf/16.0.0-v3-settings-read-scope`
  `06ba6201` over `dev` `b29f1bf7`, not pushed: `API3_SETTINGS_STRICT_READ_ENABLED`, default off,
  which makes read by identifier need `api:settings:admin` as search and history do. The setting name
  was confirmed by the maintainer on 2026-10-25. Integration 1999/1/0 and unit 1218, as reported by
  the lane.

## 4. Also found

- BF-184: `/api/v3/status` reports only wildcard permissions in `apiPermissions` (filed; register).
- AndroidAPS subscribes to `foods` on the storage socket, where Nightscout's collection is `food`
  (upstream note, read).
- AndroidAPS side (upstream notes from session f4's AAPS-safety lane, mechanism only): a record
  AndroidAPS cannot decode stalls its sync round on 3.4.2.6 and loses the page on `dev`.

## 5. Next

The maintainer's direction (2026-10-25): this lab and one note to the AndroidAPS developers, then
research the AndroidAPS side's safety before any Nightscout code. The note (drafted, not sent) asks:
whether broadcasting v1, main-socket and in-process writes on `/storage` would help or harm, and if
so whether events should name their write path; whether a master-made `aaps-client` token covers every
follower setup a strict settings read would affect; and which ingestion checks AndroidAPS would want
Nightscout to enforce at write time (see the
[write-validation design](../modernization/write-validation-design-2026-10-25.md)).
