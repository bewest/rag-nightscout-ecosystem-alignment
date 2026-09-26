<!-- Body for branch bf/entries-unknown-id at f79dc732 (one commit on dev e3adc91d, 2026-09-25). Register: BF-129. Not pushed. -->
Asking for one glucose reading by an ID that names no reading answers "nothing found" (HTTP 200 with an empty list) instead of a server error (HTTP 500).

## What changes for you

*Plain-language summary for people running their own Nightscout site for themselves or a family
member. Nightscout is not a medical device and none of this is medical advice.*

A few words used below:

- **Entry**: one saved glucose reading (or a meter check or calibration).
- **ID**: the label Nightscout gives each saved record so it can find it again. It is 24 letters
  and digits, such as `5f32abcdef0000000000d001`.
- **HTTP status**: the three-digit number a web server sends with every answer. `200` means "here
  is your answer" (which can be an empty list), `500` means "the server itself failed".

**What was wrong:** an app or script that asked Nightscout for one reading by its ID, and that
reading did not exist (it was never saved, or it was deleted), got a `500` "server error" answer.
A `500` normally means something is broken on the server, so an app could retry again and again
or report that your site was down when it was working normally.

**What this change does:** that request now answers `200` with an empty list, the same answer
Nightscout gives for every other search that finds nothing. If the server really cannot reach its
database, the answer is still `500`, so real faults are still reported as faults.

**What you should do:** nothing. None of the apps we checked (listed below) asks for a reading
this way; your readings, alarms and reports do not change.

---

## Technical detail

`GET /api/v1/entries/:spec` treats a 24-hex `spec` as an id and calls `entries.getEntry`. When
nothing is stored under that id, the route set `res.entries_err = "No such id: '<spec>'"`, and
`format_entries` answers any set `entries_err` with `500 "Mongo Error"`. #8758 (`a612a26f`) makes
`isId` accept either case, so an upper-case unknown id, which 15.0.8 took for a model name
(`type`) and answered `200 []`, also reached the 500.

The route now sets `res.entries = entry ? [entry] : []` and no error when `getEntry` finds
nothing, so the answer is `200` with `[]` (or an empty body for `.csv`/`.tsv`), the same as
`GET /api/v1/entries.json?find[_id]=<id>` for the same id. A storage error still takes the
existing `next(err)` path and answers 500. The swagger description of the `spec` parameter
(`lib/server/swagger.yaml`, `lib/server/swagger.json`) states the empty-array answer.

Why 200 `[]` and not 404: every v1 read answers `200 []` when nothing matches, `/entries/:spec`
already answers a list (a found id is `[entry]`, not an object), 15.0.8 answered `200 []` for the
upper-case form of this request, no client in the corpus fetches an entry by id through v1 (see
Client impact), and Nocturne, a Nightscout-compatible server, answers `200 []` for the same
request (`externals/nocturne/src/API/Nocturne.API/Controllers/V1/EntriesController.cs:177-187`,
`42275c812`, read).

### Measured (2026-09-25, MongoDB 7.0.43 in a dedicated container, Node 22.23.2, `NODE_ENV=production`, `AUTH_DEFAULT_ROLES=readable`)

Synthetic entries stored as `ObjectId('5f32abcdef0000000000a001')`, string `'5f32abcdef0000000000a002'`
and string `'5F32ABCDEF0000000000A003'`; unknown id `5f32abcdef0000000000ffff`.

| `GET /api/v1/…` | 15.0.8 `92d08342` | dev `e3adc91d` | this branch `f79dc732` |
|---|---|---|---|
| `entries/<ObjectId-stored, lower>.json` | 200, 1 entry | 200, 1 entry | 200, 1 entry |
| `entries/<ObjectId-stored, UPPER>.json` | 200 `[]` | 200, 1 entry | 200, 1 entry |
| `entries/<string-stored lower, lower>.json` | **500 "No such id"** | 200, 1 entry | 200, 1 entry |
| `entries/<string-stored UPPER, UPPER>.json` | 200 `[]` | 200, 1 entry | 200, 1 entry |
| `entries/<unknown, lower>.json` | **500 "No such id"** | **500 "No such id"** | 200 `[]` |
| `entries/<unknown, UPPER>.json` | 200 `[]` | **500 "No such id"** | 200 `[]` |
| `entries/<unknown>` (no extension) | **500** | **500** | 200 `[]` |
| `entries/<unknown>.csv` | **500** | **500** | 200, empty body |
| `entries.json?find[_id]=<unknown>` | 200 `[]` | 200 `[]` | 200 `[]` |
| `entries/<unknown>.json`, MongoDB stopped | 500 | not run | **500** (after the 30 s server-selection timeout) |

`/api/v1/status.json` answered 200 before and after each probe set, and with MongoDB stopped.

The other v1 collections have **no** GET-by-id route: `treatments/<id>.json`,
`devicestatus/<id>.json`, `food/<id>.json`, `profile/<id>.json` and `activity/<id>.json` answer
express's 404 HTML page for a known and an unknown id alike, on 15.0.8 and on `e3adc91d`. Their
`?find[_id]=<unknown>` reads answer 200: `[]` for treatments, devicestatus and activity; `food.json`
and `profile.json` do not apply `find` and return their usual list. None has the entries 500, and
this change does not touch them.

### Tests

New `tests/api.entries.unknown-id.test.js` (11 tests):

- unknown lower-case, upper-case, extensionless and `.csv` ids answer 200 `[]` / empty body;
- the id of an entry deleted through `DELETE /entries/<id>` answers 200 `[]`;
- `find[_id]=<unknown>` answers 200 `[]` (control);
- entries stored under an ObjectId and under a lower- or upper-case hex string are still found by
  lower- and upper-case id (controls);
- `getEntry` failing with an error answers 500, not 200 `[]`, and the same request answers 200 `[]`
  once restored (control).

No existing test expectation changed.

Full suite on `f79dc732`, Node 22.23.2 × MongoDB 7.0.43, `npm test`: 3181 passing, 3 pending, 0 failing (dev `e3adc91d` measured 3170 passing; +11 new).

### Break-its

| Tamper (on `f79dc732`, test file unchanged) | Result |
|---|---|
| B1: route restored to `e3adc91d` | 6 failing: the five unknown-id tests `expected 200 "OK", got 500 "Internal Server Error"`, and the storage-fault test at its post-restore 200 `[]` step |
| B2: a `getEntry` error answered as "not found" (`entry = null` in place of `next(err)`) | 1 failing: `getEntry failing answers 500, not 200 []` — `expected 200 to be 500` |
| B3: route always answers `[]` | 5 failing: the four found-entry controls and the deleted-entry test's pre-delete step, `expected Array [] to have property length of 1 (got 0)` |
| restored | 11 passing |

### Client impact (read-derived, corpus heads 2026-09-25)

No client in the corpus sends `GET /api/v1/entries/<id>`, so no client sees a different answer.
What each reads instead:

| Client (head) | How it reads entries | Anchor |
|---|---|---|
| AndroidAPS `7e1d537d49` | API v3 only (`/api/v3/entries`, `…/history/<ms>`, `PATCH …/entries/<identifier>`); not this route | `core/nssdk/src/commonMain/kotlin/app/aaps/core/nssdk/networking/NightscoutApi.kt:107-134` |
| xDrip `1ed760048` | `GET /api/v1/entries.json` (follower), `POST /api/v1/entries` | `app/src/main/java/com/eveningoutpost/dexdrip/cgm/nsfollow/NightscoutFollow.java:52,55` |
| xdripswift `c268542e` | `/api/v1/entries/sgv.json` reads, `POST /api/v1/entries` | `xDrip/Managers/Nightscout/Endpoint+Nightscout.swift:43`, `NightscoutSyncManager.swift:54-55` |
| Trio `e41c9db37` | `/api/v1/entries/sgv.json`, `POST /api/v1/entries.json` | `Trio/Sources/Services/Network/Nightscout/NightscoutAPI.swift:14-15` |
| NightscoutKit `4ec9fd1` (Loop) | `/api/v1/entries` with `find[dateString]` queries, and POST | `Sources/NightscoutKit/NightscoutClient.swift:13,299,651` |
| LoopFollow `4a74b781` | `/api/v1/entries.json` | `LoopFollow/Helpers/NightscoutUtils.swift:55` |
| nightguard `75404bd` | API v3 with `/api/v1/entries.json` fallback | `nightguard/external/NightscoutService.swift:730-736` |
| oref0 `d219baf9` | `/api/v1/entries/sgv.json?count=…` | `bin/oref0-get-ns-entries.js:184` |
| nightscout-connect `04102f9` | `/api/v1/entries.json` by `dateString` | `lib/sources/nightscout.js:248` |
| nightscout-reporter `518d61f` | `entries.json` | `lib/src/globals.dart:865,878` |
| DiaBLE `e6a909c` | `POST api/v1/entries`, `DELETE api/v1/entries?…`, `GET api/v1/entries.json` | `DiaBLE/Nightscout.swift:165,170,204` |

`find[_id]` and `/entries/sgv.json` reads, which these clients use, answer the same on this branch
as on `e3adc91d`. No client gets worse.
