# Programme status — cgm-remote-monitor

*Contributor guide, updated 2026-11-24. The release contents identify the single-tenant candidate on
`official/dev`. The tenancy execution log records the separate multitenant candidates. Tables on
this page come from the [work queue](../../queue/README.md).*

## The three horizons

| Work | Where it stands | Where to review it |
|---|---|---|
| Single-tenant release | 16.0.0 is the closing candidate on `official/dev`. The modernization train has merged. #8907 makes Modern the default theme and preserves saved choices. The releaser still needs evidence tied to the final build. | [16.0.0 contents](../../releases/cgm-remote-monitor-16.0.0/contents.md) · [testing notes](../../releases/cgm-remote-monitor-16.0.0/testing-notes.md) |
| Remedial | `v15.0.9` is the shipping tag. Check the affected version and the fix location on each defect before describing operator exposure. | [Backfix register](../30-design/remedial/nightscout-backfix-register.md) · [15.0.9 contents](../../releases/cgm-remote-monitor-15.0.9/contents.md) |
| Multitenant development | The candidate uses writer-driven clinical updates. The execution log records nominal load, connector delivery and recovery by source, deployment and workload. Multitenant roles are outside the 16.0.0 release. | [Decisions in force](../30-design/tenancy/decisions-in-force.md) · [execution log](../30-design/tenancy/execution-log.md) · [delivery dashboard](../30-design/tenancy/multitenant-delivery-dashboard.md) |

<!-- BEGIN GENERATED: horizons -->

| horizon | parcels | items | claimed `not-started` | claimed waiting on a person |
|---|---|---:|---:|---:|
| **Remedial** | `phase0`, `register-open`, `docs-truth` | 213 | 42 | 8 |
| **Modernization** | `release-train` | 55 | 8 | 2 |
| **Multitenant** | `tenancy`, `platform` | 150 | 30 | 25 |
| | **total** | **420** | **80** | **35** |

<!-- END GENERATED: horizons -->

<a id="status-words-merged-is-not-released"></a>

## Reading defect status and operator exposure

The register uses **open** for an outstanding defect, **fixed** for a repair on a branch,
**merged** for a repair integrated into application `dev`, and **released** for a repair in
a tag operators install. The table groups queue items by recorded exposure. One item can
cover several defect IDs. The affected versions and evidence are in the
[register](../30-design/remedial/nightscout-backfix-register.md).

<!-- BEGIN GENERATED: operator-exposure -->

| id | claimed state | defect |
|---|---|---|
| `ADV-ALARM` | `released` | GHSA-8849 - /alarm broadcasts to the whole namespace (BF-75, BF-76) |
| `ADV-CONFIG` | `needs-decision` | The readable-by-world warning, the careportal role, and the two settings behind both (BF-7 |
| `ADV-RETRO` | `released` | GHSA-gjhc - loadRetro serves devicestatus to any socket (BF-79) |
| `ADV-XSS-META` | `needs-decision` | GHSA-5mrq + GHSA-mjp4 - both closed in 15.0.8; metadata is wrong (BF-73, BF-74) |
| `BFQ-04` | `released` | BF-04 - the v1 operator allowlist - superseded by P0-K |
| `BFQ-09` | `merged-upstream` | BF-09 - socket dedup truthiness skips a falsy value |
| `BFQ-10` | `released` | BF-10 - mongod fatal-asserts at Docker's default nofile=1024 |
| `BFQ-100` | `released` | BF-100 - devicestatus, food and activity store a hex _id as a string |
| `BFQ-101` | `released` | BF-101 - API v3 id filters miss records stored with a string _id |
| `BFQ-102` | `released` | bf/object-id-consistency - one rule for a record's own hex _id across profile, devicestatu |
| `BFQ-103` | `released` | BF-103 - a split drag stores the old time, so IOB and COB ignore the move |
| `BFQ-107` | `released` | BF-107 - a failed treatments query ends the Nightscout process on 15.0.8 |
| `BFQ-111` | `released` | BF-111 - find[_id][$in] misses records stored with a string _id, for reads and bulk delete |
| `BFQ-112` | `released` | BF-112 - an auth subject created with a hex _id is stored as a string and cannot be delete |
| `BFQ-114` | `released` | BF-114 - an AAPS open-ended loop disable keeps loop and pump alerts off after the loop is  |
| `BFQ-115` | `released` | BF-115 - an entry or treatment with an unusable _id is stored with it, and one such value  |
| `BFQ-117` | `released` | BF-117 - an API v3 DELETE of a record stored twice leaves one copy valid; on #8758 v3 read |
| `BFQ-118` | `released` | BF-118 - on an mmol site, targets set without BG_HIGH are never converted, so low alarms c |
| `BFQ-119` | `released` | BF-119 - PUMP_WARN_ON_SUSPEND never raises a suspended-pump warning (issue #5622) |
| `BFQ-120` | `released` | BF-120 - the clock view shows an old reading as current when its data fetch fails (issue # |
| `BFQ-121` | `released` | BF-121 - two carb entries at the same time are stored as one, and the carbs of one are los |
| `BFQ-122` | `released` | BF-122 - records written, changed or deleted through API v1 never appear in API v3 history |
| `BFQ-123` | `released` | BF-123 - an AndroidAPS Profile Switch percentage is ignored in the basal, ISF and carb rat |
| `BFQ-125` | `released` | BF-125 - IFTTT Maker alarm events use translated level names; a failed call re-sends every |
| `BFQ-126` | `released` | BF-126 - an authorization subject without a name ends the server at every boot (issue #711 |
| `BFQ-127` | `released` | BF-127 - clock views opened from the menu are blank for a token viewer on a site that deni |
| `BFQ-128` | `released` | BF-128 - /pebble on an mmol site returns the delta in mmol when mg/dL is asked for (issue  |
| `BFQ-129` | `released` | BF-129 - GET /api/v1/entries/<id> for an id that names no entry answers 500 |
| `BFQ-133` | `released` | BF-133 - the COB pill's last-carbs detail can name an older carb entry than the newest one |
| `BFQ-134` | `released` | BF-134 - every Loop remote command leaves an APNs connection and a heartbeat timer open |
| `BFQ-136` | `released` | BF-136 - API v3 refuses an AndroidAPS write that lands on a record written through v1 (Fie |
| `BFQ-137` | `merged-upstream` | BF-137 - with more than one IFTTT Maker key, an alarm's Maker calls run out of order and a |
| `BFQ-142` | `released` | BF-142 - API v3 DELETE answers 404 for a record whose stored identifier is 0 or an array,  |
| `BFQ-145` | `merged-upstream` | BF-145 - API v3 PATCH and PUT by the shown id miss a record whose identifier is null, "" o |
| `BFQ-146` | `released` | BF-146 - API v3 treatments are held in the server's memory without mills: a late or edited |
| `BFQ-147` | `released` | BF-147 - two package.json overrides hold ajv and request's form-data inside published advi |
| `BFQ-149` | `not-started` | BF-149 - the Day to Day report draws a cancelled or replaced temp target or override for i |
| `BFQ-152` | `merged-upstream` | BF-152 - API v3 settings are admin-only through search and history, readable by identifier |
| `BFQ-154` | `blocked` | BF-154 - node-forge 1.4.0 (pinned in overrides) is inside an advisory range with no fixed  |
| `BFQ-156` | `merged-upstream` | BF-156 - API v3 auto-prune never handles its delete's result; a failed delete ends the pro |
| `BFQ-157` | `merged-upstream` | BF-157 - a treatment's glucose bubble is placed as mg/dL when its units are spelled mmol/L |
| `BFQ-159` | `merged-upstream` | BF-159 - the main page sometimes leaves for the Profile Editor while a profile exists, wit |
| `BFQ-160` | `merged-upstream` | BF-160 - the clock designer's link target is written with curly quotes |
| `BFQ-161` | `blocked` | BF-161 - braces 3.0.3 (direct dependency) is inside a stack-exhaustion advisory with no fi |
| `BFQ-163` | `merged-upstream` | BF-163 - compression 1.8.1 (every response) is inside a high memory-leak advisory fixed in |
| `BFQ-164` | `blocked` | BF-164 - writes outside API v3 never reach the v3 storage socket |
| `BFQ-165` | `merged-upstream` | BF-165 - a treatment re-send matched by its fallback key is answered without _id |
| `BFQ-166` | `merged-upstream` | BF-166 - a profile re-sent with its own _id answers 500 |
| `BFQ-168` | `released` | BF-168 - the context chart's window sometimes cannot be dragged back to now |
| `BFQ-169` | `merged-upstream` | BF-169 - API v3's swagger says clients must not supply identifier, but the server keeps a  |
| `BFQ-170` | `merged-upstream` | BF-170 - API v3 stores a client's 24-hex body _id as a string, in the case sent |
| `BFQ-172` | `merged-upstream` | BF-172 - the Bolus Wizard Preview mixes the profile's units with the display units (#8819  |
| `BFQ-173` | `merged-upstream` | BF-173 - the Careportal Bolus Wizard mixes the profile's units with the display units, a k |
| `BFQ-174` | `merged-upstream` | BF-174 - the bolus calculator's profile picker is ignored; every value comes from the acti |
| `BFQ-180` | `merged-upstream` | BF-180 - a careportal temp target on an mmol/L site is converted to mg/dL twice when the h |
| `BFQ-181` | `not-started` | BF-181 - one future srvModified pins the shared write clock ahead, across restarts |
| `BFQ-183` | `merged-upstream` | BF-183 - the API v3 storage socket logs the supplied credential on a failed authorization |
| `BFQ-184` | `not-started` | BF-184 - API v3 /status apiPermissions reports only wildcard permissions |
| `BFQ-186` | `merged-upstream` | BF-186 - API v3 logs a whole record when a client's identifier differs from the computed o |
| `BFQ-187` | `not-started` | BF-187 - an entries pattern segment over the braces parser's input limit answers 500, not  |
| `BFQ-188` | `not-started` | BF-188 - with no client bundle the server exits at boot with an unexplained module error |
| `BFQ-190` | `merged-upstream` | BF-190 - an alarm on a page without a current reading cannot be silenced from the page |
| `BFQ-191` | `in-progress` | BF-191 - a stored treatment can stop the server process, and keeps doing so after a restar |
| `BFQ-193` | `merged-upstream` | BF-193 - the realtime socket and other write paths log every record written through them |
| `BFQ-194` | `merged-upstream` | BF-194 - API v1 drops the units of a temp target with no glucose value, so mmol/L targets  |
| `BFQ-195` | `merged-upstream` | BF-195 - a stale profile is pushed over the socket after a profile re-send |
| `BFQ-196` | `not-started` | BF-196 to BF-199 - API v1 error paths and the README's read window, found by PR #8858's ro |
| `BFQ-204` | `merged-upstream` | BF-204 - API v2 data-snapshot route returns the live 48 hours, not data framed at the requ |
| `BFQ-205` | `merged-upstream` | BF-205 - same-timestamp records are ordered differently between in-memory loads |
| `BFQ-206` | `merged-upstream` | BF-206 - a device IOB without a timestamp is dated by the server clock |
| `BFQ-207` | `merged-upstream` | BF-207 - sensor age keeps the earliest of a same-hour burst of Sensor Starts; the newest i |
| `BFQ-208` | `not-started` | BF-208 - an API v1 delete by a non-hex _id can answer 200 and announce a removal while not |
| `BFQ-209` | `merged-upstream` | BF-209 - two identical treatments sent over the socket within 2 s are stored as one, even  |
| `BFQ-210` | `closed` | BF-210 - a socket treatment without an amount is matched to a stored one that has one (clo |
| `BFQ-211` | `merged-upstream` | BF-211 - a delete by query in one collection empties all three in-memory caches |
| `BFQ-212` | `in-progress` | BF-212 - a chart-drag split leaves two treatments with one client identity; a re-send can  |
| `BFQ-213` | `merged-upstream` | BF-213 - the URGENT pump reservoir alarm is refused when the level comes from reservoir_le |
| `BFQ-214` | `merged-upstream` | BF-214 - a device-status delete by query leaves its cache empty until the next heartbeat |
| `BFQ-217` | `merged-upstream` | BF-217 - an override with no reservoir value throws in the pump plugin |
| `BFQ-219` | `merged-upstream` | BF-219 - a v1 treatments batch with a preBolus answers with more items than were sent |
| `BFQ-220` | `merged-upstream` | BF-220 - a duplicate _id inside a v1 batch answers 5xx after the items before it are store |
| `BFQ-221` | `merged-upstream` | BF-221 - a v1 treatment PUT reaches open pages up to about a minute late |
| `BFQ-222` | `merged-upstream` | BF-222 - API v3 autoPrune can leave pruned records in the server's cache |
| `BFQ-223` | `merged-upstream` | BF-223 - a saved API secret the site refuses blocks a valid ?token= link |
| `BFQ-224` | `merged-upstream` | BF-224 - a v1 filter with a plain value under the date field (find[created_at]=<ISO>) answ |
| `BFQ-226` | `merged-upstream` | BF-226 - an API v3 autoPrune of more than one record empties the type's cache with no relo |
| `BFQ-227` | `merged-upstream` | BF-227 - a late or repeated Pushover receipt callback answers 500 |
| `BFQ-241` | `ready-to-push` | BF-241 - one upload limit, UPLOAD_BODY_LIMIT, for entries, treatments and device status |
| `BFQ-242` | `not-started` | BF-242 - notifications router parsers cap activity and food uploads at 100 KB |
| `BFQ-243` | `not-started` | BF-243 - with SECURE_CSP=true the CSP report parser refuses API uploads over 100 KB |
| `BFQ-244` | `not-started` | BF-244 - API v3 answers 500 for oversized or malformed request bodies |
| `BFQ-245` | `blocked` | BF-245 - profile and food uploads capped at 1 MB; bring them under UPLOAD_BODY_LIMIT |
| `BFQ-246` | `ready-to-push` | BF-246 - linear mergeProcessSort in the shared dataloader (16.0.0) |
| `BFQ-247` | `in-progress` | BF-247 - preserve treatment history across parallel read orders |
| `BFQ-248` | `gate-not-met` | BF-248 - API v3 history continuation keeps records that share the page boundary's stamp |
| `BFQ-40` | `released` | BF-40 - $exists is not read as a boolean on dev; fixed by bf/coercion |
| `BFQ-46` | `merged-upstream` | BF-46 - eleven API v3 variables bypass env.js, one family deletes data |
| `BFQ-47` | `released` | BF-47 - an ordinary subject edit destroys stored fields, on today's release |
| `BFQ-52` | `blocked` | BF-52 - an age reminder whose 20-minute window passed without a check was never sent |
| `BFQ-67` | `not-started` | BF-67, BF-86 - alarm thresholds quietly changed, or quietly kept when they cannot work |
| `BFQ-69` | `released` | BF-69 - the Bolus Wizard quick-pick chooser is built once, from nothing |
| `BFQ-71` | `closed` | BF-71 - any dateString key drops the default date window, and the window is not a control |
| `BFQ-72` | `blocked` | BF-72 - an unauthenticated $regex can spend minutes of database CPU |
| `BFQ-87` | `released` | BF-87 - the root qs override holds the connector below its range and pins the server's que |
| `BFQ-90` | `released` | BF-90 - an alarm at a page with no reading throws in the client |
| `BFQ-91` | `released` | BF-91 - connector capture mode cannot find trace-axios for two sources |
| `BFQ-92` | `merged-upstream` | BF-92 - a page with no glucose reading never presents a server alarm, including device ala |
| `BFQ-93` | `merged-upstream` | BF-93 - food changes never reach an open page |
| `BFQ-95` | `needs-decision` | BF-95 - an uploader clock running ahead delays the stale-data alarm |
| `BFQ-98` | `released` | BF-98 - the connector reuses a reader subject without roles, so the BF-89 fix does not rep |
| `BFQ-99` | `released` | bf/profile-object-id - a profile posted with its own _id is stored as an ObjectId, and str |
| `BFQ-CAP01` | `not-started` | CAP-01 - Nightscout cannot be served from a sub-path |
| `BFQ-CONNECTOR` | `gate-not-met` | BF-42, BF-43 - master pins the leaking connector, with a violated axios override |
| `BFQ-ENV` | `needs-decision` | BF-48, BF-49, BF-50, BF-51 - four ways the configuration surface lies |
| `BFQ-MINIMED` | `not-started` | BF-44, BF-45, BF-85 - MiniMed ingestion divergences and the CareLink zero reading |
| `RT-PR-8815` | `released` | #8815 - a bearer token whose subject was deleted is refused instead of stopping the server |

<!-- END GENERATED: operator-exposure -->

## Where the work stands

Each cell counts manifest claims. Run the relevant item gate before acting on a claim.
An item marked `in-flight-upstream` has been handed to upstream. An item marked
`gate-not-met` has an outstanding measurement. A skipped gate supplies no passing result.

<!-- BEGIN GENERATED: state-matrix -->

| parcel | `not-started` | `in-progress` | `gate-not-met` | `ready-to-push` | `blocked` | `in-flight-upstream` | `merged-upstream` | `released` | `needs-decision` | `done` | `unsettled` | `closed` | `answered` | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `phase0` | 3 |  |  |  |  |  |  | 18 |  | 1 |  |  |  | **22** |
| `release-train` | 8 | 2 | 1 |  |  |  | 22 | 15 | 2 | 1 |  |  | 4 | **55** |
| `register-open` | 32 | 5 | 2 | 3 | 6 |  | 56 | 58 | 5 |  |  | 5 |  | **172** |
| `tenancy` | 22 | 23 |  |  | 6 | 23 | 6 |  |  | 10 | 1 | 15 | 6 | **112** |
| `docs-truth` | 7 |  | 1 |  |  |  |  |  |  | 11 |  |  |  | **19** |
| `backfix2` |  |  |  |  |  |  |  | 2 |  |  |  |  |  | **2** |
| `platform` | 8 | 2 |  |  |  | 1 | 2 |  |  | 25 |  |  |  | **38** |

<!-- END GENERATED: state-matrix -->

<a id="the-two-constraints-neither-of-them-engineering"></a>

## Review and publication

The queue names the reviewer or reviewer group for each item. The maintainer owns
upstream publication. Pushing application `dev` or `master` can publish a development
or release image. The release record identifies the tag available to operators.

<!-- BEGIN GENERATED: reviewer-load -->

| the item is waiting for | items | share |
|---|---:|---:|
| Maintainer | 380 | 90% |
| SECURITY reviewer | 17 | 4% |
| Maintainer + a second human | 10 | 2% |
| SAFETY reviewer | 6 | 1% |
| Unassigned | 3 | 1% |
| Whoever edits it next | 3 | 1% |
| Upstream reviewers | 1 | 0% |
| **total** | **420** | |

<!-- END GENERATED: reviewer-load -->

For items awaiting a person, see [review and decision routing](NEEDS-A-HUMAN.md).
For the gate and source evidence behind an individual review, start with
[reviewer onboarding](REVIEWER-ONBOARDING.md).

## How to check any of this yourself

```bash
make queue-status                 # run static and unit gates
make queue-status ID=RT-16-RELEASE
make queue-check                  # validate records, generated views and links
```

The [roadmap](ROADMAP.md) gives the order of work. The
[definition of done](DEFINITION-OF-DONE.md) and [document control](DOCUMENT-CONTROL.md)
describe how evidence is retained.

<!-- BEGIN GENERATED: provenance -->

*Generated from `queue/work-queue.yaml` by `tools/queue/emit_views.py`. Manifest `measured_at` **2026-09-27**, against cgm-remote-monitor-official `7000eb18` and this repository at `18cdcce0`. Every state above is a **claim** about what the gates will say &mdash; `make queue-status` is the measurement.*

<!-- END GENERATED: provenance -->
