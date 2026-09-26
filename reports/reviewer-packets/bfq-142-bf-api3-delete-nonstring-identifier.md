<!--
  ============================================================================
  GENERATED FILE - MUST NOT BE HAND-EDITED.

  Source of truth:  queue/work-queue.yaml
  Generator:        tools/queue/emit_packets.py   (make packets)
  Staleness check:  python3 tools/queue/emit_packets.py --check

  Review NOTES belong on the pull request, not here. This file is a projection
  of the manifest; anything written into it is destroyed by the next run.
  ============================================================================
-->

# Review packet — BFQ-142

**BF-142 - API v3 DELETE answers 404 for a record whose stored identifier is 0
or an array, which v3 GET returns under its _id**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/api3-delete-nonstring-identifier` |
| base | `official/dev@ce7d754a` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-142` is the measurement |
| semver | `patch` |
| register entries | `BF-142` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

One commit at 1c3aeb8c. lib/api3/storage/mongoCollection/utils.js
filterForEveryForm (the _id fallback's identifier condition {$in: [null, ""]}
becomes {$in: [null, "", 0, false, NaN]}, still excluding arrays and now
Decimal128), used by the v3 soft and permanent DELETE (modify.js
updateEveryForm and deleteEveryForm) and by the cache invalidation in
mongoCachedCollection findEveryForm; tests/api3.delete-every-form.test.js (30
new tests). Storage, v3 reads, PUT and PATCH are unchanged; a record with its
own string or array identifier is still not deleted through its _id.

## Why that semver

a v3 delete reaches a record whose _id v3 reads show as its identifier, as on
15.0.8

## What an operator would notice

> Not in any release yet; without this fix it would be in 15.0.9. If a
> glucose reading, a device status or a treatment was stored with the number
> 0 or the value false as its identity, an app that deletes through API v3
> (for example AndroidAPS) could not delete it, and the record kept showing
> and counting on the site. The fix lets that delete work again, as in
> 15.0.8. A record whose identity is a list still cannot be deleted this
> way; the development version already worked like that before this fix. No
> app is known to store such values. This is not medical advice.

## Who should review this, and why

maintainer (API semantics)

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official grep -q "null, .., 0, false, NaN" bf/api3-delete-nonstring`** &nbsp;·&nbsp; kind: `static`

The branch's delete fallback lists the falsy identifiers normalizeDoc shows as
the _id (official/dev ce7d754a lists null and "" only and fails this). A
presence check only; tests/api3.delete-every-form.test.js decides (18 of its
30 new tests fail on ce7d754a). Point it at official/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by a booted-server probe that needs MongoDB, so
  it is not a queue gate. 2026-09-26, Node 22.23.2, MongoDB 7.0.43:
  tools/lab/triage-2026-09/api3-empty-identifier-delete.js direct-insert and
  v1 entries/devicestatus arms, identifier 0 and false: soft and permanent
  DELETE 200 on v15.0.8 92d08342 and 1c3aeb8c, 404 on ce7d754a; arrays 200
  on v15.0.8, 404 on ce7d754a and 1c3aeb8c (kept out on purpose, as #8778
  pins); bystanders untouched.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/triage-2026-09/api3-empty-identifier-delete.js`](../../tools/lab/triage-2026-09/api3-empty-identifier-delete.js)
- [`reports/phase0-pr-bodies/api3-delete-nonstring-identifier.md`](../../reports/phase0-pr-bodies/api3-delete-nonstring-identifier.md)

## Notes carried on the item

Filed 2026-09-26 from the review of #8778 (BF-140) and deferred past 15.0.9 by
the maintainer; the maintainer reversed that the same day (fix in 15.0.9).
Present on dev since #8758's cb7d4110 (BF-117). 2026-09-26 - FIXED on
bf/api3-delete-nonstring-identifier 1c3aeb8c (local, not pushed), one commit
on official/dev ce7d754a (#8781's merge). The rule: the delete's _id fallback
takes exactly the stored identifiers normalizeDoc shows as the _id. 18 of 30
new tests fail on ce7d754a (GET 200, then DELETE 404); break-its per clause
all red. Full suite 3458/0/3 on a fresh database (ce7d754a: 3428/0/3). Arrays
still answer 404, unlike 15.0.8: v3 GET shows them as stored, so they are the
record's own identifier (BF-117, #8778); for the maintainer to confirm. Not
changed: v3 PATCH and PUT by the _id of a record with a present but falsy
identifier (identifyingFilter needs it absent): PATCH 404, PUT inserts a
second record, the same on 15.0.8. PR body draft: reports/phase0-pr-
bodies/api3-delete-nonstring-identifier.md.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-142` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-26, against cgm-remote-monitor-official `ff93fa94`.*
