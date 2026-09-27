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

# Review packet — BFQ-146

**BF-146 - API v3 treatments are held in the server's memory without mills: a
late or edited v3 record is left out of IOB and COB, and the treatments fall
out of time order**

| | |
|---|---|
| repository | `cgm-remote-monitor` |
| branch | `bf/api3-cache-derived-fields` |
| base | `official/dev@699eb5fa` |
| claimed state | `ready-to-push` — a claim; `make queue-status ID=BFQ-146` is the measurement |
| semver | `patch` |
| register entries | `BF-146`, `BF-133` |
| operator exposure | **reaches an operator on today's release** |

## What this changes

Two commits, head d235bdf6 (db99bba4 treatments, d235bdf6 device status).
lib/api3/storage/mongoCachedCollection/index.js (updateInCache passes
treatments and device status through ddata.processRawDataForRuntime, the
helper the v1 emitters in lib/server/treatments.js and
lib/server/devicestatus.js use, before the data-update event; entries are
passed on as before); tests/api3.cache-derived-fields.test.js (15 new tests).
Nothing stored changes. GET /api/v1/treatments served from memory now carries
mills (and endmills or a derived duration where the helper adds them) on v3
records too, as it already did on v1 records; order unchanged. GET
/api/v1/devicestatus served from memory now places a v3 status by time
(before, one without mills sorted last and could fall outside the count) and
shows its mills. v3 responses are unchanged.

## Why that semver

treatments and device status written through API v3 are held with the same
derived time fields as v1 writes

## What an operator would notice

> Not yet released; the same problem is in 15.0.8. When an app that uses API
> v3 (for example AndroidAPS) uploaded a bolus or carb entry late, or edited
> an older one, Nightscout could leave it out of the insulin on board (IOB)
> and carbs on board (COB) it works out from treatments, in the server and
> in the browser, until the server restarted. The same cause could put
> treatments out of time order, which could make the COB number too high and
> make the "last carbs" line name an older entry. Where your app reports its
> own IOB and COB in device status, the pills show those values instead.
> This fix makes those records count and keeps the order. A late device
> status from such an app is also now listed in its place by time when
> another app reads the latest device statuses. This is not medical advice;
> check numbers against the app that entered them and talk to your care team
> before relying on them.

## Who should review this, and why

maintainer

## What was measured

**`sh -c 'git -C externals/cgm-remote-monitor-official grep -q "processRawDataForRuntime" bf/api3-cache-derived-f`** &nbsp;·&nbsp; kind: `static`

The branch's v3 cache wrapper derives the v1 fields (official/dev 699eb5fa and
v15.0.8 92d08342 do not mention the helper there and fail this). A presence
check only; tests/api3.cache-derived-fields.test.js decides (10 of 15 red on
699eb5fa and 92d08342). Point it at official/dev once merged.

## What these gates do NOT prove

*Each of these is the author recording, at the time, a property they could not measure. This is the reviewer's worklist.*

- The behaviour is measured by booted-server tests that need MongoDB, so
  they are not queue gates. 2026-09-26, Node 22.23.2, MongoDB 7.0.43, fresh
  databases: on 92d08342 and 699eb5fa a late v3 bolus gives treatment IOB 0
  and late v3 carbs COB 0 (also in the socket page data and after v3
  PATCH/PUT), mixed v1/v3 writes load in reverse time order, "last carbs"
  names the older entry, and COB is 34.5 g where time order gives 10 g; a
  late v3 device status is missing from the default GET /api/v1/devicestatus
  served from memory (last instead of first in the whole held set, also with
  DENORMALIZE_DATES); all 15 pass on d235bdf6. Controls (v1 bolus of the
  same age, v3 bolus dated now, v1 status of the same age, v3 status dated
  now, the page's device status) pass on all three. Suite 3473/0/3 (699eb5fa
  3458/0/3, db99bba4 3467/0/3). Treatment probes unchanged on 699eb5fa,
  db99bba4 and d235bdf6.

## Evidence

- [`docs/30-design/remedial/nightscout-backfix-register.md`](../../docs/30-design/remedial/nightscout-backfix-register.md)
- [`tools/lab/rc-soak/results/proof-2026-09-27.md`](../../tools/lab/rc-soak/results/proof-2026-09-27.md)
- [`reports/phase0-pr-bodies/api3-cache-derived-fields.md`](../../reports/phase0-pr-bodies/api3-cache-derived-fields.md)

## Notes carried on the item

Found by RC run 019 (04a873ce, trace T1) as the cause of BF-133; the IOB/COB
omission was found while tracing it. Maintainer decision 2026-09-26: "fix as
appropriate". 2026-09-26 - FIXED on bf/api3-cache-derived-fields db99bba4
(local, not pushed), one commit on official/dev 699eb5fa. Break-it: deriving
and then dropping mills gives the same 7 red; deriving only on create gives
the PATCH/PUT test red. same-time-carbs, same-time-resend-shapes, retry-keeps-
srvcreated and v1-writes-v3-history give the same output on 699eb5fa and
db99bba4 (v1-writes-v3-history exit 1 on its v1 DELETE arm on both). PR body
draft: reports/phase0-pr-bodies/api3-cache-derived-fields.md. 2026-09-26
(maintainer): extend the fix to device status for consistency. Second commit
d235bdf6 on the same branch (not pushed): device status goes through the same
helper. The only change to the in-memory v1 read is placement: the same
records for the whole held set, the late v3 status first instead of last, so
for a smaller count it is now inside the window. Dataloader, pills and page
data unchanged (they already derived mills). Entries measured and left as they
are. 6 new tests (3 red on 699eb5fa, 92d08342 and db99bba4); break-its red;
suite 3473/0/3; the four probes unchanged against db99bba4.

---

## Before you approve

- [ ] Re-read **what these gates do NOT prove**. A gate can pass for the wrong reason; two in this project did, and both were green.
- [ ] If the diff changes what an existing test expects, confirm the reason is stated **in the diff**, where a reviewer sees it.
- [ ] `make queue-status ID=BFQ-146` — do the gates still agree with the claimed state?
- [ ] **Do not merge, push or tag.** Publication is a separate, deliberate human act; pushing `dev` or `master` builds and publishes a Docker image.

*Generated from `queue/work-queue.yaml`, `measured_at` 2026-09-26, against cgm-remote-monitor-official `ff93fa94`.*
