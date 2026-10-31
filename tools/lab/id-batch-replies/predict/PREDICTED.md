# ID-BATCH predicted cells (feat/id-batch on ee49832d)

Contributor-facing. Written before any route change was gated. The rules are in `predict.js`
(committed at 0c08cd258, written before the first route edit). The explicit lists come from those
rules applied to the base pins `tools/qc/results/write-contract-matrix/batch-ee49832d-*.json`
(QC-MATRIX-BATCH cells, 312 per run) and `idfmt-ee49832d-*-strict.json` (QC-MATRIX-IDFMT cells, 2,675
per run). `predict.js --check <base> <head> <mode>` holds a head run to them.

| file | MongoDB | settings | cells predicted to move |
|---|---|---|---|
| `predicted-batch-m5.0.32-default.json`, `-m8.0.29-default.json` | 5.0.32, 8.0.29 | none | 45 each |
| `predicted-batch-*-reject.json` | both | `WRITE_VALIDATION=reject` | 45 each |
| `predicted-batch-*-strict.json` | both | `WRITE_IDENTIFIER=strict` | 57 each |
| `predicted-idfmt-*-strict.json` | both | `WRITE_IDENTIFIER=strict` | 780 each |
| every earlier matrix cell (create … idf-*, TT, V2) | both | none | 0 |

## Default replies (no opt-in): what moves, and why

Byte for byte unchanged except:

1. **ID-STRICT-V1** (decided 2026-10-30). Under `WRITE_IDENTIFIER=strict`, an API v1 item with an invalid
   identifier is refused in its slot (400, the socket's `refused` member word for word). The rest are
   stored, with a `Warning: 299 - "k of n <collection> refused; see the refused member of each"`; when
   every item is refused, the reply is 400. Cells: `<coll> v1 batch-mixed-ident` and
   `<coll> v1 batch-placeholder-identifier` for all six collections (12 cells), plus the
   QC-MATRIX-IDFMT cells that write an invalid class (undefined, null, invalid, nan, unknown, empty,
   blank, jsonnull, number, len257) through v1, same-path or as either half of a cross cell (780).
   `idfmt-idundef-*` does not move: the route checks `identifier` before the step's `_id` step moves
   `_id: "undefined"` into it.
2. **(iv) preBolus record out of the reply**: no cell moves. It is already on the base (BF-219, #8883).
   `treatments v1 batch-prebolus` is 3 slots on the base.
3. **Every entry refused for a taken `_id` → 200 with 409 slots**: no cell moves. It is already on the base
   (BF-220, c3a939f7). `entries v1 batch-taken-all` is 200 with two 409 slots on the base.

Socket and in-process cells never move: R1–R6 change API v1 routes only, and in-process strict stays
"absent" (`IDENTIFIER_STRICT['v1/internal']` is not edited).

## Opt-in cells (`… +results`, `Nightscout-Write-Results: items`)

Every v1 `+results` cell moves (the body becomes `{ items, documents }`), except those answering 5xx
(R4, no items). Those are `batch-storage-fail-mid` everywhere, and `batch-repeat-identifier`,
`batch-repeat-stored`, `batch-deleted` and `batch-dupkey-mid` on profile, food and activity, which
answer 500 on the base. The fields predicted beyond "moves" are listed in the JSON:

- R2: `batch-mixed-oid` on devicestatus, profile, food and activity is 200 with
  `1:noid:i:ref400`, and items 0 and 2 are stored (base: a whole-batch 400).
- (iii): `profile v1 batch-profile-permission +results` is 200 with `1:noid:ref403`, and the new profiles
  are stored (base: 401 whole).
- (vi): acknowledged, counted in the Warning. This covers the deleted re-send (entries, treatments,
  devicestatus `batch-deleted`) and devicestatus `batch-repeat-identifier`, `batch-taken-id` and
  `batch-taken-all` (the step's `refused` "repeated in the batch" / "already stored").
- R6 counts: `"k of n items refused"`, `"a acknowledged, not applied"`, `"g identifier ignored"`.

## batch-dupkey-mid: today (ee49832d) and at -4e's item-level fix

The fixed head is predicted, not measured. The fix keeps the operations before `writeErrors[0].index`,
applies only the race item as its re-send, continues from the next operation, and composes the slots and
the one data-update once.

| cell (default and `+results`) | ee49832d (measured) | fixed head (predicted) |
|---|---|---|
| entries v1, inproc | 200, slots `0:id:i,1:id:i,2:id:i`, writes `0:2,1:1,2:1` (item 0 written twice), one du[3] | same slots; writes `0:1,1:1,2:1`; one du[3]; `+results` items `0:inserted, 1:merged, 2:inserted` |
| devicestatus v1, inproc | 200, writes `0:3,1:1,2:3` (baseline 2 per item: items 0, 2 one write extra) | writes `0:2,1:1,2:2`; `+results` `0:inserted, 1:merged, 2:inserted` |
| treatments v1, inproc | 200, writes `0:1,1:1,2:1`: no duplicate key arises (the batch upsert reaches the rival) | unchanged |
| profile, food, activity v1 | 500, item 0 kept, writes `0:2` (food/activity baseline 1: item 0 written twice) | 500 still, if the race item's re-send cannot apply on these paths (no identifier match on v1 yet). Item 0 written once (food/activity `0:1`) |
| every ws cell | unchanged (items one at a time) | unchanged |

Under the fix, the word the coordinator relayed for already-written slots is `created`. The step's word
is `inserted` (`OUTCOMES` in write-intent.js), and ID-BATCH passes the step's word through.

## Slot outcomes after the replace-on-match change (maintainer, 2026-10-31; not built)

A matched re-send will **replace** on every collection; merge stays only for v3 PATCH and socket
dbUpdate. ID-BATCH passes the step's outcome word through and treats no word specially except
`refused` and not-written (`acknowledged`, decision (vi)), so the only expected change is in the opt-in
`items` column. No test asserts `merged`. Measured on feat/id-batch 76fd7bfb (MongoDB 5.0.32, no
settings); none of these cells' slots, status, Warning or `storeb` should move from this change alone.
`storeb` may move where the re-send's fields replace the stored record's (`:v2`).

| `+results` cell | today | after replace-on-match (predicted) |
|---|---|---|
| entries v1 batch-repeat-identifier | `0:inserted,1:inserted,2:merged` | `2:replaced` |
| entries v1 batch-repeat-stored | `1:merged` | `1:replaced` |
| devicestatus v1 batch-repeat-stored | `1:merged` | `1:replaced` |
| profile, food, activity v1 batch-taken-id | `1:merged` | `1:replaced` |
| profile, food, activity v1 batch-taken-all | `0:merged,1:merged` | `0:replaced,1:replaced` |
| treatments (every re-send) | `replaced` | unchanged |
| entries v1 batch-dupkey-mid | `0:merged,1:merged,2:inserted` | `0:replaced,1:replaced` at ee49832d; at -4e's item-level fix `0:inserted,1:replaced,2:inserted` |
| devicestatus v1 batch-dupkey-mid | `0:merged,1:merged,2:merged` | at the item-level fix `0:inserted,1:replaced,2:inserted` |

PENDING-4E, seen in the opt-in today: after the whole-batch retry, the step's items come from the
second run, so entries item 0 and devicestatus items 0 and 2 (inserted by the first run) report
`merged`. The fixed-head column above (`inserted` for the slots written before the race) is what
the item-level fix should give. `merged` becomes `replaced` once replace-on-match lands too.
