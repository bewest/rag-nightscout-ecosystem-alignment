# What uploaders do when Nightscout refuses a write

> **Snapshot, 2026-10-25, client sources at the pins in §1; Nightscout side `official/dev` `b29f1bf7` and the draft `feat/api3-domain-validation` `a2e5fe49`. Current: the evidence behind the write-validation design's decision that `reject` stays opt-in until a refusal is visible to the person. Contributor-facing. Current decisions: [write-validation design](../modernization/write-validation-design-2026-10-25.md) and queue items `MOD-WRITE-VALIDATION`, `MOD-WRITE-VALIDATION-READ`; register BF-180.**

Session f4's upload-400 lane asked one question per uploader: if Nightscout answers a write with a
400 (or a 200 that marks one item refused, the D2 reply shape of the write-validation draft), what
happens to that record and to the uploader's queue? Three clients were run; the rest were read.
Marks: **[M]** measured, **[R]** read from source at the pinned commit, not run. Where a figure
appears only in the lane's report and not in its raw files, the row says "reported by the lane".

## 1. Sources

| client | pin | how |
|---|---|---|
| AndroidAPS | 3.4.2.6 `598e2eb39c` and `dev` `3905d352dd` (4.0.0 line); `externals/AndroidAPS` `7e1d537d49` for line numbers marked so | `core/nssdk` run on the JVM against a mock server **[M]**; sync plugin read **[R]** |
| Loop | NightscoutKit `4ec9fd1` (Loop's pin), NightscoutService `2cef489`, LoopWorkspace `v3.14.9` | **[R]** |
| Trio | `v1.0.2` `0b29cd534` | **[R]** |
| xDrip+ | `2026.09.18` `1ed760048` | **[R]** |
| xDrip4iOS (xdripswift) | `7.1.1` `c268542e` | **[R]** |
| nightscout-connect | `0.1.0` | `lib/outputs/internal.js` run in process against a fake context **[M]** |
| oref0 | `d219baf9` | `bin/ns-upload.sh` run against a stub server **[M]** |

## 2. The table

| client | a 400 on one record or a whole batch | a refused slot inside a 200 (D2 shape) | other non-2xx | mark |
|---|---|---|---|---|
| **AndroidAPS** (API v3, one record per request): treatments, entries, food | logged, the record **dropped**, the cursor moves on | n/a | any other 4xx, or an exception, **blocks** that kind's queue with no backoff and no cap; a 500 is retried 3 times within the call (measured; the 100 ms spacing is reported by the lane) | 400/422/500 handling **[M]**; queue consequences **[R]** |
| AndroidAPS: devicestatus, profile store | blocks on any non-2xx | n/a | blocks | **[R]** |
| **Loop** (NightscoutKit) | a whole-batch 400, or a reply array shorter than the batch, holds the anchor: the full batch (up to 1000) is resent on every trigger, with no cap | the slot without `_id` is recorded as `"NA"` and counted as uploaded: **lost**; its later edits and deletes are skipped | needs exactly 200 | **[R]** |
| **Trio** | any non-2xx: none of the batch is marked uploaded, the remaining chunks are not sent, and it retries each loop cycle for up to 24 h | 2xx marks every item uploaded; the body is not read: **lost** | as 400 | **[R]** |
| **xDrip+** (Android) | entries: the batch stays queued for up to 7 days. Treatments go by PUT one at a time, and a failure marks **every** queued treatment done, including ones not yet sent | n/a (treatments use PUT) | — | **[R]** |
| **xDrip4iOS** | a refused BG batch blocks the BG cursor for up to 7 days | treatments are matched by content; a refused slot without `_id` stays pending and is resent while it is among the latest 50 | — | **[R]** |
| **nightscout-connect** (in process) | all items refused: the frame is rejected, retried with backoff, and the entries in that frame are written again | the bookmark moves past the refused item: **lost** | — | **[M]** |
| **oref0** | 400, 500 and 200 all exit 0: the refused record is lost, and the newest refused record is POSTed again each cycle | — | as 400 | requests **[M]**; exit codes reported by the lane |

**No client reads a `refused` member or a `Warning` header.** (Read across all seven.)

## 3. Measurements

**AndroidAPS `core/nssdk`** (`dev` `3905d352dd`, JVM tests `UploadRefusalProbeTest` added in the lane's
scratch copy, mock server):

| server answer | what `NSAndroidClientImpl` did | requests |
|---|---|---|
| 400 `{"status":400,"message":"Temporary Target: targetBottom is above targetTop"}` | returned a response, code 400, identifier null, the error body kept | 1 |
| 422 | returned a response, code 422 | 1 |
| 500 `{"status":500,"message":"Mongo Error"}` | threw `UnsuccessfulNightscoutException` | 4 (1 + 3 retries) |

AndroidAPS string-matches two 400 bodies: "Bad or missing utcOffset field" (it resends with
`utcOffset: 0`) and "cannot be modified by the client" (it marks the record as never uploadable)
(`core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/NSAndroidClientImpl.kt:226`, `:231` on `dev`
`3905d352dd`; `:388`, `:393` for treatments on `7e1d537d49`). Any refusal message has to avoid both.

**nightscout-connect 0.1.0** `lib/outputs/internal.js`, with a fake context whose
`treatments.create` behaves like the write-validation draft under `reject` (re-run for this note):

| case | result | bookmark afterwards |
|---|---|---|
| partial: first of two treatments refused (refused slot without `_id`) | resolved | `treatments` 04:30, the refused item's own time: it is past the refused item |
| all refused (error, status 400) | rejected, "Nightscout internal write failed"; `log.error` "Internal persistence failed" | unset: the frame is retried |

In both runs `entries.create` had already written the frame's entry before the treatments call.

**oref0 `ns-upload.sh`** against a stub answering 400, 500 and 200 on three paths: the stub logged one
`POST /api/v1/treatments.json` of 2 items for each. That every run exits 0 is reported by the lane.

## 4. Read citations

The lane's citations for the read rows; those marked *(checked)* were re-read for this note at the
pinned commit.

- NightscoutKit `Sources/NightscoutKit/NightscoutClient.swift:488-490` (the array must have as many
  objects as were sent) and `:545-547` (status must be 200) *(checked)*.
- NightscoutService `NightscoutServiceKit/NightscoutService.swift:345-356`: the pump-event upload calls
  its completion with `success(false)` before the upload finishes *(checked)*.
- xDrip+ `utilitymodels/UploaderTask.java:171-187` (on success every queued item is marked complete)
  and `utilitymodels/NightscoutUploader.java:588-601` (the treatments exception path) *(checked)*.
  The "every queued treatment marked done on one failure" consequence is the lane's reading of the two
  together; it is an upstream xDrip+ defect, not a Nightscout one.
- AndroidAPS `NSAndroidClientImpl.kt` (above) *(checked)*; queue blocking in the sync plugin's
  workers, read by the lane.
- Trio `Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift`, `NightscoutManager.swift`;
  xdripswift `NightscoutSyncManager.swift`, `TreatmentNSResponse.swift`: file names from the lane;
  line numbers for the v1 POST reply handling are in the write-validation PR body
  ([design note](../modernization/write-validation-design-2026-10-25.md) §3.2).

## 5. Implications

1. **`log` is the only validation mode with no effect any client can see.** It can be recommended to
   operators now.
2. **Under `reject`, a refused record is silently lost** for AndroidAPS, Loop, Trio and
   nightscout-connect, and retried indefinitely by xDrip4iOS; xDrip+ can lose later treatments in the
   same pass.
3. **A whole-batch 400 wedges Loop and Trio.** The D2 partial-batch reply (200, one object per item,
   refused slots without `_id`) is the shape that wedges nobody, which is why it was decided.
4. **A default `reject` needs a refusal the person can see first**: clients that read `refused`
   (upstream asks), or a Nightscout-side notice when a record is refused. It is not blocked on a date.
5. **Refusal texts must avoid AndroidAPS's two matched strings**, and refusals should stay plain 400s:
   any other 4xx blocks an AndroidAPS queue.

Upstream notes from the same lane (not Nightscout defects, no register id): xDrip+'s treatment queue
drop on a partial failure; AndroidAPS's Temp Basal check reads only `durationInMilliseconds`, so
`duration: 0` in minutes passes (`TreatmentMapper.kt:172`, read); NightscoutKit builds an override's
correction range without checking lower ≤ upper; AndroidAPS subscribes to `foods` where Nightscout's
collection is `food`.
