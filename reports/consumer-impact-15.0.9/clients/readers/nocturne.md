# nocturne — parity against cgm-remote-monitor 15.0.9 candidate

- Repo: externals/nocturne (`nightscout/nocturne`), an alternative server (C#/ASP.NET + PostgreSQL,
  with a Node socket.io bridge) that implements the Nightscout v1/v2/v3 API.
- Ref analysed: `origin/main` **42275c812 (2026-09-24)**. Local HEAD d9e143097 (2026-09-11) is
  **226 commits behind**; nothing below was read from the working tree.
- The question here is **parity**, not breakage: for each S-id, does nocturne behave like 15.0.8
  or like the candidate (dev ddd9b600 + #8754 ef3404fd + #8758 6d120fa2)?
- All claims **read-derived**. Nothing was run; nocturne's parity suite was not executed.

## Positive controls

- v1 find parser: `src/Core/Nocturne.Core.Models/Queries/FindQuery.cs:112-145` (`Parse`), used by
  entries/treatments/devicestatus/activity/count read paths (`git grep -n "FindQuery.Parse" origin/main -- src`).
- v1 count handling: `src/API/Nocturne.API/Controllers/V1/EntriesController.cs:285-356`.
- socket.io compatibility: `src/Web/packages/bridge/src/lib/socketio-server.ts:286-400` (`authorize`), `:744-829` (`/alarm`).
- v2 subjects: `src/API/Nocturne.API/Controllers/V2/AuthorizationController.cs:131-250`,
  `src/API/Nocturne.API/Services/Identity/AuthorizationService.cs:435-548`.

## A test fixture pins Nightscout **15.0.3**, not 15.0.8

`tests/Integration/Nocturne.API.Tests/Infrastructure/NightscoutContainer.cs:12,17` runs
`nightscout/cgm-remote-monitor:15.0.3` as the reference for the whole parity suite
(`ParityTestFixture.cs:15`; `Parity/V1/EntriesParityTests.cs:10` "match Nightscout 15.0.3 exactly").
`ResponseComparer.cs:36-41,246-252` compares status codes and array lengths, so these tests encode
15.0.3 answers. Last touched d006a2002 (2026-08-18, a dependency bump); the pin itself dates from
15c50e952 (2026-01-27). Parity tests whose reference answer **changes** if the image were bumped to the candidate:

| test | request | 15.0.3/15.0.8 | candidate | nocturne |
|---|---|---|---|---|
| `Parity/V1/EntriesParityTests.cs:196` | `GET /api/v1/entries?count=-1` | 200 | **400 Bad count** | 200 `[]` (`EntriesController.cs:350-353`) |
| `Parity/V1/TreatmentsParityTests.cs:181` | `GET /api/v1/treatments?count=-1` | 200 | **400 Bad count** | 200 `[]` (`TreatmentsController.cs:105`) |
| `Parity/V1/CountParityTests.cs:22-178` | `/api/v1/count/{entries,treatments,devicestatus,...}/where[?find…]` | per bf/reads, 15.0.8 counted zero/missing for requests without an explicit date range | real counts over the default window | see S4 row — bracket `find` is not bound |
| `Parity/V1/CountParityTests.cs:61` | `count/entries/where?find[date][$gte]=<ms>` | as above | as above | as above |

Everything else in the V1 parity files uses integer bounds and plain equality
(`find[sgv][$gte]=100`, `find[insulin][$gte]=3`, `find[eventType]=…`, `find[device]=…`,
ISO `find[created_at][$gte]`), whose answers the candidate does not change. No parity test uses
`$exists`, `$type`, a decimal bound, `count=0`, or an unsupported operator
(`git grep -n -E '\$exists|\$type|count=0|[0-9]\.5' origin/main -- tests/Integration/Nocturne.API.Tests/Parity`
returns only seeded values such as `insulin: 1.5` and `AddDays(-1.5)` in `CountParityTests.cs:81`,
`DeviceStatusParityTests.cs:87-119`, `IobParityTests.cs:56` — data, not filter bounds; the filter
list above is the output of `grep -E 'Assert[A-Za-z]*ParityAsync\(|"/api'` over each V1 file).
A seeded 1.5-unit treatment would matter if a test filtered `insulin>=1.5`; none does
(`TreatmentsParityTests.cs:72` uses `$gte=3`).

## Parity table

"15.0.8" / "candidate" columns are the upstream behaviour from the brief's change list and the code
at the refs named above; the verdict says which one nocturne matches.

| S-id | nocturne behaviour | anchor (nocturne@42275c812) | verdict | patterns searched |
|---|---|---|---|---|
| S1 `count=0` (GET) | entries, treatments, devicestatus: 200 `[]` (`EntriesController.cs:350-353`, `TreatmentsController.cs:105`, `DeviceStatusController.cs:93`); activity: `[]` via `ClampMergedPage` (`ActivityController.cs:85`). **profile: clamped to 1** (`ProfileController.cs:70,149` `Math.Max(1, Math.Min(count, 1000))`), so `count=0` returns one profile. | as listed | **candidate** on 4 of 5 routes; profile does not match the candidate (`[]`, `cgm-remote-monitor@ddd9b600 lib/server/profile.js` `isZeroCount`); 15.0.8's profile answer to `count=0` was not traced | `count <= 0`, `ClampCount`, `Math.Max(1` |
| S1 negative | `-3` → 200 `[]` on entries/treatments/devicestatus/activity; profile → 1 record | as above | **neither**: candidate answers 400; 15.0.8 passed `parseInt` to `limit()` | same |
| S1 non-integer (`abc`, `2.5`, `1e2`, `0x10`) | `count` is `int`/`int?` bound by MVC on an `[ApiController]` (`EntriesController.cs:29,287`; `TreatmentsController.cs:64` etc.); a value that does not parse fails model binding → automatic **400 ValidationProblemDetails** (no `SuppressModelStateInvalidFilter` in `src`). | as listed | **candidate** in status (400), **not** in body shape (RFC 7807 `errors.count`, not `{status:400, message:"Bad count"}`) | `SuppressModelStateInvalidFilter`, `InvalidModelStateResponseFactory` |
| S1 large | `> int.MaxValue` (e.g. 2^31..2^53) → binding 400; within int: clamped silently to 100 000 (entries, treatments) or 10 000 (devicestatus, activity) or 1 000 (profile) (`Helpers/LegacyReadLimits.cs:51,73,103,110`). | as listed | **neither** — candidate accepts any safe integer and does not clamp | `MaxCount`, `ClampCount` |
| S1 `+5`, ` 5 ` | .NET `int` parsing accepts a leading sign and surrounding whitespace; candidate's `^\s*\d+\s*$` accepts whitespace but refuses `+5` with 400 | (framework behaviour; not in repo) | minor divergence | — |
| S1 DELETE with count | v1 bulk DELETE takes no `count` (`EntriesController.cs:1086-1100`); `?count=0` alone becomes the find string `count=0`, which parses to an empty query, and the bulk delete then **refuses** (returns 200 "Deleted 0") because a non-empty find with no time bound would wipe everything (`Services/V4/EntryDecomposer.cs:203-236`). | as listed | safe, but status differs: candidate 400, nocturne 200 with 0 deleted | `HttpDelete`, `BulkDeleteAsync` |
| S2 operator set | Parser accepts `$eq $ne $gt $gte $lt $lte $in $nin $regex(+$options) $exists $and $or` (`FindQuery.cs:12,345-346`). **`$type` is not implemented.** Any other `$op` in querystring form parses (`TryParseFindKey` `:270-308`) and then evaluates to **no match** (`:569-579` `_ => false`); JSON form treats an unknown `$op` as a nested path and also matches nothing. | as listed | **neither**. Candidate: unknown op → **400** naming the op; `$type` allowed. 15.0.8: forwarded to MongoDB (500 or result). Nocturne: **200 `[]`**, silently. | `\$type`, `UnsupportedOp`, `_ => false` |
| S2 malformed find | A find that throws while parsing → `FindQuery.Empty` (**no filter, matches everything**) (`FindQuery.cs:140-144`, "legacy Nightscout silently ignores them"). | as listed | **neither**; candidate refuses malformed operator trees with 400 | `catch (Exception)` |
| S2 `pipeline` on `/count` | `/count/*` binds only a query key literally named `find` (`CountController.cs:87,137,180,230,285`); other keys, `pipeline` included, are ignored. | as listed | **neither**: candidate 400 | `pipeline` |
| S2/S3 `$exists` values | `true`/`TRUE`/`1` → must exist; **everything else, including `false`, `0`, `null`, `yes` and empty, → must NOT exist** (`FindQuery.cs:551-554`). | as listed | **candidate for true/1/false/0**; **opposite of the candidate for `null`, empty and other spellings** — candidate reads those as "has the value" (`ddd9b600 lib/server/query.js` `readBooleanOperand`, release notes "Other spellings, such as `null` or leaving the value empty, still mean 'has the value'"). Tests pin true/false only (`tests/Unit/Nocturne.Core.Models.Tests/Queries/FindQueryTests.cs:304-330`). | `\$exists` |
| S3 numeric comparison | Compares by the **stored JSON type**: a numeric field against a parsed double (`FindQuery.cs:671-680`), so decimals (`insulin>=1.5`), `duration`, `rate`, `absolute`, `percent`, devicestatus battery etc. all compare as numbers, with no schema list. Numeric strings in the document also compare numerically (`:690-693`). Time fields `date, mills, created_at, dateString, timestamp` compare on the epoch-ms axis in either representation (`:25-28,588-607`). | as listed | **candidate** (and broader: no field table, so also `activity.date`, which the candidate stopped coercing — see summary) | `CompareOperand`, `TimeFields` |
| S3 `created_at` vs `date` | Both are time fields and interchangeable for bounds (`FindQuery.cs:403-436`); a numeric `created_at` bound works, which on Nightscout is an ISO-string comparison. | as listed | superset of both | — |
| S4 `/count/*/where` | `find` bound only as a single `find=` value (JSON form); **bracket `find[...]` filters are not seen** (`CountController.cs:87,101`), no `ValueProvider`/middleware rewrites them (`git grep -n -E 'StartsWith\("find\[' origin/main -- src` lists only Entries/Treatments/DeviceStatus/Food controllers and FindQuery). Response shape `CountResponse {count}` (`:386`). | as listed | **neither**; counts ignore the filter. Unverified by running; the parity tests at `CountParityTests.cs:42-61` exercise exactly this and would need 15.0.3 to agree. | `CountAsync`, `find\[` |
| S4 status/verifyauth/properties/ddata | Controllers exist (`V1/StatusController.cs`, `V2/PropertiesController.cs`, `V2/DDataController.cs`). The candidate's change to two shared read addresses (per-collection read permission) and to `status.js` (client address) was not compared line by line. | — | **not analysed** in depth | — |
| S5 subjects/roles fields | Typed models (`Core/Nocturne.Core.Models/Authorization.cs:218-318`): subject `_id/id, name, roles, accessToken, notes, created, modified, isPlatformAdmin`; role `_id/id, name, permissions, notes, autoGenerated, created, modified`. Extra fields are dropped by deserialization. **Notes are not stored**: create echoes them back but persists only label and scopes (`AuthorizationService.cs:435-485`); update ignores `notes` (`:495-548`). Update needs `id` (a GUID), not `_id` (`AuthorizationController.cs:222-224`, `AuthorizationService.cs:501-505`). **An absent or empty `roles` list leaves the grant unchanged** (`:523-538`). | as listed | extra-field drop: **candidate**. notes kept on edit: **neither** (not stored at all). Removing a subject's last role: **opposite** — candidate stores the empty list (deliberately, `ef3404fd lib/authorization/storage.js` `keepStoredFields` comment); nocturne keeps the old authority. Timestamps are named `created`/`modified`, not `created_at`. | `CreateSubject`, `UpdateSubject`, `Notes`, `Roles is { Count: > 0 }` |
| S5 client address / throttle | Client address from `X-Forwarded-For` only via ASP.NET `ForwardedHeaders` with configured `KnownProxies`/`KnownNetworks` (`Extensions/NocturneForwardedHeadersExtensions.cs:29-90`); proto/host handled separately (`:80-84`). No Nightscout-style failed-auth delay list found. | as listed | closer to **candidate with `TRUST_PROXY` set** than to the unset default | `ForwardedHeaders`, `KnownProxies`, `DelayList`, `brute` |
| S6 `authorize` (main namespace) | Handshake ticket, or legacy `authorize` with `secret`/`token` replayed as `GET /api/v1/entries?count=1` against the API; success joins the tenant room (`socketio-server.ts:346-399`). **An `authorize` with no credential is denied and the socket disconnected** (`:370`), on any tenant. Broadcasts go only to the tenant room, never to unauthorized sockets (`:403-424`). | as listed | on `denied`: **candidate** (no data without read). On a public/readable site: **stricter than both** — Nightscout (either release) serves an anonymous socket on the `readable` default; nocturne disconnects a credential-less legacy client that has no ticket. | `authorize`, `no credentials supplied` |
| S6 `loadRetro`, `dbAdd/dbUpdate/dbRemove` | none found in the bridge. | — | not implemented (neither) | `loadRetro`, `retroUpdate`, `dbAdd`, `dbUpdate`, `dbRemove` |
| S6 `/alarm` subscribe | Requires `accessToken`, probed against the v3 entries read (`socketio-server.ts:786-829`). No anonymous admission. | as listed | **candidate** on `denied`; stricter than both on `readable` (candidate admits anonymous sockets there) | `handleAlarmSubscribe` |
| S6 `/alarm` ack | Withheld: a security finding for the nocturne project, to be raised with it privately first. | — | — | — |
| S7 `_id` forms | v1 accepts 24-hex and 32-hex (UUID v7 without dashes), case-insensitive by regex (`EntriesController.cs:171-175,963-966,1036-1039`; `ProfileController.cs:333-336`). Lookup: GUID parse, then exact `LegacyId == id` (`Services/Entries/EntryReadService.cs:163-175`, `Repositories/V4/V4RepositoryBase.cs:219-222`), then a GUID-prefix range. No lower-casing of the id was found on the lookup path. | as listed | Upper-case 24-hex legacy id: **probably 15.0.8 behaviour** (not found), where #8758 makes `GET/DELETE /api/v1/entries/<ID>` case-insensitive. Unverified: whether LegacyId is lower-cased on write. | `ToLowerInvariant`, `LegacyId ==` |
| S13 v3 `limit` | `limit<0` → 400 (`BaseV3Controller.cs:50-56`); **`limit=0` → clamped to 1**; `>1000` → clamped to 1000 (`:77-82`). | as listed | **neither** for 0 and over-max (both Nightscout releases refuse `limit=0` and a limit above the site maximum) | `limit`, `MaxEntriesLimit` |
| S13 v3 paging | `Link` headers by offset (`BaseV3Controller.cs:281-297`). Candidate's v3 paging fix (records skipped/repeated) not compared. | — | **not analysed** | — |

## What the join step should ask

1. nocturne's parity suite is anchored to 15.0.3. When it moves to 15.0.9, the two `count=-1`
   tests flip to 400 and the count-endpoint tests change reference values. Is the nocturne team
   aware of the 15.0.9 contract changes (count, operator allowlist, `$exists`)?
2. `$exists=null` / empty: nocturne and the candidate give **opposite** answers. A client written
   against one silently gets the complement on the other.
3. Unsupported operator: candidate 400, nocturne 200 `[]`. A client that relies on the 400 to
   detect an unsupported filter cannot on nocturne.
4. `/alarm` ack permission: a security question for the nocturne project, raised privately.
