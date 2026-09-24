# cgm-remote-monitor 15.0.8 → 15.0.9 candidate: inventory of consumer-visible changes

**Contributor-facing working document (DRAFT).** Input to the consumer-impact join step. It is not
operator-facing and not medical advice.

- **Server repo:** `externals/cgm-remote-monitor-official` (remote `origin` = nightscout/cgm-remote-monitor).
  It was read only, through `git show` / `git grep` / `git diff` on refs; nothing was checked out, fetched or run.
- **Shipping release:** `origin/master` `92d08342` = tag 15.0.8.
- **Candidate:** `origin/dev` `ddd9b600` (2026-09-23, 59 first-parent merges past master), plus two open PRs:
  - #8754, head `ef3404fd` (2026-09-23): delta `git diff origin/dev ef3404fd`;
  - #8758, head `6d120fa2` (2026-09-23): based on dev `1f9a9d10`, 32 merges behind the dev tip; delta
    `git diff 1f9a9d10 6d120fa2`. `git merge-tree` against dev is clean (objectid part).
- **Evidence labels:** every claim is **read-derived** (from source) unless marked
  "reproduced locally against qs@x". That label means the qs library was run on its own in
  `scratch/`; no server was run and no request was sent.
- **Anchors:** `ref:path:line`. Where dev equals master for a file, parts say so explicitly.
- **Mechanism, not recipe.** The socket and auth defects are live on 15.0.8, and this document
  describes the fixed contract only.
- **Summary table:** see `summary.md`.

## How the entries were produced

The core entries (C1–C34) were written in this pass. Four parallel passes produced the rest, which
were then renumbered into the C-series; their provisional ids are kept in the mapping below so their
cross-references stay traceable.

| C-id | provisional | topic |
|---|---|---|
| C14-detail | W4 | count/slice per-collection read permission (#8751) |
| C31-detail | W8 | readable-by-world admin notice (#8746) |
| C37 | W1 | websocket `loadRetro` authorisation (#8744) |
| C38 | W2 | `/alarm` delivery restricted to `AlarmReceivers` (#8745) |
| C39 | W3 | `/alarm` `ack` needs `notifications:*:ack` on the native-token path (#8745) |
| C40 | W5 | alarm-socket logging (#8751) |
| C41 | W6 | #8754 socket deltas |
| C42 | W7 | #8758 websocket `_id` deltas |
| C43–C48 | A1–A6 | #8754: stored subject/role fields, notes/created_at, failed-auth delay, `TRUST_PROXY`, startup logs, status/v3 address |
| C49–C59 | O1–O11 | #8758 `_id` contract (entries, treatments, profile/BF-99, devicestatus, food, activity, websocket, v3) |
| (C35–C36) | – | unused (docker-compose ulimit and boot-error page are folded into C29) |
| C60–C67 | D1–D8 | dependencies: Express 4.22.2 array limit, body-parser, qs 6.16, socket.io stack, uuid, axios, d3/babel, proxy-addr |

---

## Prose vs code mismatches (key deliverable)

The release notes (`releases/cgm-remote-monitor-15.0.9/release-notes.md`) are going to operators. Where
they, a PR body, or a code comment disagree with the code, **the code wins**. Each item names the entry
with the detail.

### A. Release-note statements that describe code not on dev

1. **Everything from #8754 is written as shipped, with no pending marker.** This covers:
   - security items 6 and 7;
   - the whole `TRUST_PROXY` section;
   - "Corrections: Fields stored on users and roles";
   - "Editing a user on the admin page keeps its notes and creation date";
   - "Access tokens stored in plain text";
   - the Known-issues `TRUST_PROXY` line;
   - "What you must do" items 4 and 9.

   All of these depend on the **open** PR #8754 (`ef3404fd`). `origin/dev` has none of it. The #8758
   and connector sections carry `<!-- PENDING -->` markers; the #8754 sections do not. (C43–C48.)
2. **The connector section says the release installs "nightscout-connect 0.1.0".** Dev pins
   `0.1.0-dev.3` (C33). The section is behind `PENDING: connector v0.1.0 tag` markers, so this is expected
   until the tag lands. The pin PR still has to happen.

### B. Release-note statements that disagree with the code

3. **`count=0` "never returns your whole history … an empty list" is too broad in one direction and
   hides a change in the other.** (C2)
   - Routes that ignore `count` still answer normally for `count=0`: `/count/…/where`, `/food*`,
     `/profile/current`, `/entries/current`, `/status`.
   - On 15.0.8 the unbounded answer happened only for some request shapes. Entries and treatments
     already returned `[]` from the cache for a bare `count=0`.
   - `GET /api/v1/devicestatus?count=0` returned **10 records** on 15.0.8 and now returns `[]`. The notes
     do not mention devicestatus.
4. **The `count` table leaves out several refusals** (C1):
   - a **repeated** `count` parameter is refused;
   - `+5` is refused;
   - `count` is validated on **every** v1 route, including ones that do not use it, so
     `/api/v1/status.json?count=x` → 400;
   - there is **no upper cap** apart from 2^53−1, and "a number too large to handle exactly" means
     exactly that.
5. **COB: "now shows the value reported by your looping app rather than Nightscout's own estimate".**
   (C17)
   - 15.0.8 already preferred a controller-reported COB up to 10 minutes old, on sites whose profile has
     sens and carbratio.
   - What actually changed:
     - COB now appears on sites without such a profile;
     - devicestatus blocks without a timestamp are dated by the record, not by "now";
     - the tooltip was added;
     - `treatmentCOB` changed from an object to a number;
     - `cob.source` is localised in the fallback case.
6. **"Filter conditions … Anything else gets an error (HTTP 400) that names the refused condition".**
   (C5)
   - True on the JSON routes.
   - On `/api/v1/echo/…` the refusal is raised synchronously, so it goes to express's `errorhandler`:
     status 400, but not the JSON body.
   - The allowlist does not apply to API v3 or `/api/v1/food`.
7. **"Earlier results may have under-reported…" / coercion.** (C7) The notes name temp-basal duration
   and decimal insulin. The code coerces about 150 fields across four collections, including booleans
   (`isValid`, `automatic`, `pump.suspended` …). Boolean filters also flip from matching nothing to
   matching.
8. **Qs / query parsing: "no difference for any request a known app sends".**
   - True for qs 6.15.1 → 6.16.0 measured against dev.
   - False for 15.0.8 → 15.0.9: Express 4.22.1 → 4.22.2 (#8571) raised `req.query` `arrayLimit` from 20
     to 1000.
   - As a result, `$in`/`$nin` lists and `$or`/`$and` branch lists of 21–1000 items, which reached the
     server as objects and failed, now work. That includes **bulk DELETE by id list, which deleted
     nothing on 15.0.8 and now deletes every match.**
   - The #8749 PR body measured against dev, not master, so its "Express sets arrayLimit: 1000" and
     "zero differences" are false for 15.0.8. (C60, C62)
9. **Security item 1, the live-update connection.** (C37, C38)
   - `dataUpdate` was already gated on 15.0.8.
   - The fix covers `loadRetro`/`retroUpdate` (retro devicestatus) and the `/alarm` namespace.
   - "Nothing changes on `readable`" holds on dev except on an address that is being throttled after
     failed logins, which is the #8745 known cost. #8754 removes that exception.
10. **Security item 2, silencing alarms.** (C39)
    - Only the native `accessToken` subscribe path changed, and it changed on the **`readable` default
      too**.
    - `ack` now needs `notifications:*:ack`, which among built-in roles only admin has.
    - The refusal is **silent**: no callback, no event. A follower app with a `readable` token appears to
      silence an alarm that stays active on the server.
    - HTTP `/api/v1/notifications/ack` is unchanged.
11. **Security item 4, "two shared read addresses".** (C14) These are `GET /api/v1/count/:storage/where`
    and `GET /api/v1/slice/:storage/…` for `storage` ∈ {treatments, devicestatus}, and they answer 401.
    Neither the notes nor the #8751 body names them.
12. **Security item 8, the readable warning.** (C31-detail) The code raises the notice for **any**
    `AUTH_DEFAULT_ROLES` list containing `readable`, such as `readable devicestatus-upload`, not only
    `TREATMENTS_AUTH=off`. The "open to treatment entry" title appears whenever `careportal` is present.
13. **"Edited records no longer leave an old copy behind"** (#8758, behind a PENDING marker). (C49–C59)
    - **"Nothing in your database changes until a record is edited or deleted" is false.**
      - New POSTs and websocket `dbAdd` with a 24-hex `_id` are now stored as ObjectId.
      - A food/activity create removes an old string copy.
      - The PR body says "written, edited or deleted".
    - **Not mentioned:**
      - an entries re-send with a different `_id` goes from 500 to 200;
      - the entries POST reply now carries the **stored** reading's `_id`;
      - upper-case hex ids now work on `/api/v1/entries/<id>`;
      - **a new refusal**: a profile/devicestatus POST whose `_id` equals an ObjectId-stored record went
        from 200 plus a silent duplicate to **500 "Mongo Error"**, and websocket `dbAdd` now replies `[]`;
      - upper-case ids sent on POST come back in lower case.
    - "Those records are found" has limits:
      - an upper-case string `_id` is found only in that spelling;
      - `find[_id][$in]` is not widened;
      - food GET has no id filter.
    - Devicestatus is listed under "editing saved a second copy", but v1 has no devicestatus PUT.
14. **`TRUST_PROXY` details.** (C46)
    - `false` is case-sensitive (`FALSE` is refused), while `true` is not.
    - A refused value throws during boot and the **process exits**. It is not a startup message.
    - More values are refused than the notes list: `0`, `off`, hostnames, and values with a port.
    - "Fields stored on users" omits that a POST to `/api/v2/authorization/subjects` or `/roles` with its
      own `_id` now gets a server-generated `_id`, so the token differs from one a tool may have derived.
      POST/PUT replies no longer echo the body. (C43)
15. **Underscore side effect** ("an underscore `_` in a web address is no longer turned into a space").
    (C27) This is correct, but it is **browser-page-only**: two parameters read by the page, `token` and
    `mute`. Server-side query parsing never did this. Bookmarks are affected only through those two.

### C. PR-body and code-comment mismatches

16. **`reports/phase0-pr-bodies/qs-6.16.md` used the wrong baseline for a 15.0.8 statement** (see 8).
17. **`reports/phase0-pr-bodies/bf2-auth-hardening.md`, the local copy, is stale.**
    - It says `true` and hop counts are rejected, and it describes a `lib/api/index.js` trust-proxy line
      that `22953b77` removed.
    - The posted body and the `.withheld.md` copy are current. (C46)
18. **The #8745 body's "connected clients receive alarms exactly as before" leaves things out.** It
    omits the native-token `ack` change on the default install and the throttled-address race. (C38,
    C39)
19. **The #8758 body's "re-sent devicestatus/profile … refused again, as on dev" leaves a case out.** On
    dev, a re-send over an **ObjectId**-stored record was accepted (200, duplicate). #8758 refuses it
    with 500. (C55)
20. **#8529 is titled "uuid-14.0.0", but uuid is not bumped** (11.1.1 on both refs). (C64)
21. **Code comment `origin/dev:lib/api/index.js:59-62`** says a delete with an unreadable count "is
    refused as before". 15.0.8 never refused it. (C3)
22. **Code comment `ef3404fd:lib/api3/alarmSocket.js:94-102`** still says anonymous admission waits on the
    delay list. It no longer does. (C41, C45)

---

## Merge classification (all 59 first-parent merges `origin/master..origin/dev`, plus the 2 open PRs)

Key: **API** = changes what an API/websocket client can observe; **HTML** = the Nightscout web page only;
**STORE** = changes what the web page writes, which other clients later read; **OPS** = operator or log
only; **DEP** = dependency bump; **DOC/L10N/CI** = no runtime effect.

| # | merge | PR | branch / title | class | C-ids |
|---|---|---|---|---|---|
| 1 | ddd9b600 | #8760 | bf/split-drag-time | HTML+STORE | C24 |
| 2 | 4011193e | #8751 | bf2/backports | API | C14, C40 |
| 3 | 3a38c6f2 | #8753 | bf2/ops (Alexa default reply, docker ulimit, booterror, isPluginEnabled) | API (Alexa) + OPS | C19, C29 |
| 4 | c11888ed | #8756 | bf3/quickpick-rebuild | HTML+STORE | C16 |
| 5 | 728351e3 | #8755 | bf3/alarm-no-reading | HTML | C30 |
| 6 | 42c5e21e | #8748 | bf/count-zero-empty | API | C1, C2, C3 |
| 7 | 9fd4600e | #8749 | bf/qs-6.16 | DEP (API only for malformed keys) | C62 |
| 8 | d0d6b433 | #8757 | bf3/mmconnect-deprecation-warning | OPS | C29 |
| 9 | feafa533 | #8759 | bf/connect-pin-0.1.0-dev.3 | DEP (connector behaviour) | C33 |
| 10 | 1f9a9d10 | #8750 | docs/mongodb-floor | DOC | – |
| 11 | f0954a6a | #8752 | bf/connect-pin-0.1.0 (→0.1.0-dev.2) | DEP (connector) | C33 |
| 12 | 74fc6619 | #8746 | bf/readable-warning | API (adminnotifies) + OPS | C31 |
| 13 | 2b22c0ce | #8745 | bf/alarm-socket-scope | API (socket) | C38, C39 |
| 14 | a9acd313 | #8744 | bf/ws-loadretro-auth | API (socket) | C37 |
| 15 | 59430336 | #8732 | wip/mobile-ui-fixes (pill titles, sage n/a, profile editor defaults) | HTML + API (sage property) + STORE | C22, C23 |
| 16 | 7a5561f4 | #8739 | bf/alarms (IAGE urgent, voice locale, ENABLE hints) | API | C18, C19, C29 |
| 17 | 2e94de1b | #8736 | bf/parms (page URL params, %n translation) | HTML | C27, C34 |
| 18 | ff0d506c | #8735 | bf/food | API (quickpicks) + HTML/STORE | C15, C16 |
| 19 | 49f562d8 | #8740 | bf/cache | API (cache-served reads) | C25 |
| 20 | bcd171cb | #8741 | env-credential-coercion | OPS (outbound logins) | C28 |
| 21 | 1abc1aad | #8729 | fix-chart-container-height-race | HTML | C30 |
| 22 | 1a36f023 | #8743 | bf/operators | API | C4, C5, C6 |
| 23 | fdd08706 | #8734 | bf/merge | HTML | C26 |
| 24 | d3358e91 | #8738 | bf/reads (count grammar, count/where, v3 limit/sort/fields) | API | C1, C4, C11, C12, C13 |
| 25 | 025f1310 | #8737 | bf/coercion | API | C7, C8, C9 |
| 26 | 77d153d2 | #8733 | optimize-treatment-processing | none claimed (performance; order-preserving by construction, read-derived) | C26 note |
| 27 | a8888f0d | #8726 | opt-in debug logging | OPS | C29 |
| 28 | 57d1cac9 | #7338 | fix_docs (CONTRIBUTING) | DOC | – |
| 29 | ca35f2a3 | #8702 | empty profile name | API (server-computed properties) + HTML | C21, C22 |
| 30 | 5a09befd | #8701 | profile-switch preprocessing | API (server-computed properties) | C21 |
| 31 | 6fbff0ec | #8699 | clock low+falling face | HTML | C30 |
| 32 | 0ab266a3 | #8697 | treatments query errors / date `+` repair | API | C6, C10 |
| 33 | b982e1e9 | #8603 | crowdin_incoming (+`lt`, `sl_SI`, de-de Alexa template) | L10N (+ language table) | C34 |
| 34 | 9205ea30 | #8529 | uuid-14.0.0 (uuid NOT bumped; tests) | CI | C64 |
| 35 | 97d1aa1b | #8544 | jsdom/ws (dev deps) | DEP/CI | table |
| 36 | 7e71fb62 | #8550 | babel | DEP (build) | C66 |
| 37 | eedc9439 | #8565 | axios 0.33 | DEP (outbound only) | C65 |
| 38 | c5fd8054 | #8566 | engine.io / ws | DEP (no protocol change) | C63 |
| 39 | 6fb8db1c | #8571 | express 4.22.2 / body-parser 1.20.6 | **DEP → API** | C60, C61 |
| 40 | e7c0cd6f | #8573 | d3 7 (+ renderer adaptations) | DEP → HTML | C66 |
| 41 | f7c7812c | #8575 | ip-address | DEP (no client effect) | table |
| 42 | 4b62921b | #8576 | fast-uri | DEP (no client effect) | table |
| 43 | 4b665293 | #8577 | socket.io-parser 4.2.7 | DEP (no client effect) | C63 |
| 44 | 3bb07409 | #8578 | dompurify (dev) | DEP (no client effect) | table |
| 45 | a363d760 | #8579 | js-yaml | DEP (tooling) | table |
| 46 | 02c63225 | #8581 | mocha | DEP (tests) | table |
| 47 | 1156aafd | #8582 | postcss | DEP (build) | table |
| 48 | d6e90d00 | #8586 | brace-expansion | DEP (tooling) | table |
| 49 | 4f6151d7 | #8583 | opaque Loop notification error | API | C20 |
| 50 | 57f45284 | #8602 | dailystats A1c units | HTML (reports) | C30 |
| 51 | c1943ced | #8588 | report uniq cascade | HTML (reports) | C30 |
| 52 | 948aafac | #8567 | cache stale-delete race | API (cache-served reads) | C25 |
| 53 | 9f1b4d3a | #8599 | crowdin_incoming (translations only) | L10N | – |
| 54 | 56ebbf30 | #8601 | npm 12 remote (.npmrc, CI) | OPS/CI | – |
| 55 | 48441640 | #8587 | COB uploader-reported value | API (properties) | C17 |
| 56 | 2af0aed9 | #8589 | report reinit on reconnect | HTML (reports) | C30 |
| 57 | 101f51a0 | #8590 | treatments event-type filter (report) | HTML (reports) | C30 |
| 58 | 85fed44b | #8516 | remove mongo44 support (README only) | DOC | – |
| 59 | 5c26c9d2 | #8597 | 15.0.9 dev bump | API (version string) | C32 |
| – | ef3404fd | #8754 (open) | bf2/auth-hardening | API | C41, C43–C48, C67 |
| – | 6d120fa2 | #8758 (open) | bf/object-id-crud (incl. BF-99) | API | C42, C49–C59 |

**Counts** (each merge counted once, by its primary class):
- 59 merges classified.
- **24 API-affecting** (rows 2, 3, 6, 7, 9, 11, 12, 13, 14, 15, 16, 18, 19, 22, 24, 25, 29, 30, 32, 39, 49,
  52, 55, 59). Rows 7, 9 and 11 are dependency bumps whose effect reaches clients: qs on malformed keys,
  and the connector as a client of a source site. Row 39 is the Express bump.
- **12 HTML/browser-only** (rows 1, 4, 5, 17, 21, 23, 31, 40, 50, 51, 56, 57). Rows 1 and 4 also change
  stored data (STORE).
- **4 OPS-only** (rows 8, 20, 27, 54).
- **12 dependency bumps with no client effect** (rows 35–38, 41–48).
- **6 DOC/L10N/CI** (rows 10, 28, 33, 34, 53, 58).
- **1 with no observable change claimed** (row 26).
- Both open PRs are API-affecting.

---

# Core entries (C1–C34)

## C1 — v1 `count`: a strict grammar, enforced for every v1 route by one middleware; HTTP 400 "Bad count"

- **PRs / merges:** #8738 `bf/reads` (merge `d3358e91`, 2026-09-18) introduced `lib/server/count.js`
  and the middleware; #8748 `bf/count-zero-empty` (merge `42c5e21e`, 2026-09-23) made `count=0` a
  valid read and changed the DELETE rule. **Status:** merged (in dev).
- **Surfaces:** S1, S12, S15.
- **Where enforced:** `origin/dev:lib/api/index.js:71-94` — an `app.use` on the whole v1 app,
  installed after `/experiments` (`:38`) and before every router (`:96-125`). It therefore runs for
  **every** `/api/v1/*` route: `entries*`, `echo/*`, `times/*`, `slice/*`, `count/*`,
  `treatments*`, `profile*`, `devicestatus*`, `notifications*`, `activity*`, `verifyauth`,
  `adminnotifies`, `food*`, `status*`, `alexa*`, `googlehome*` — including routes that do not use
  `count` at all (e.g. `GET /api/v1/status.json?count=abc` is now 400). It does not run for
  `/api/v1/experiments/*`, API v2 or API v3. **read-derived**
- **Grammar** (`origin/dev:lib/server/count.js:22-57`):
  - absent, `null` or empty (`count=`) → "no count" → the route's own default applies (C1 does
    nothing) (`:55-57`);
  - valid **read** count: the string matches `^\s*\d+\s*$` (ASCII digits, optional surrounding
    whitespace, leading zeros allowed) and `Number(value)` is a safe integer. `0`/`00`/` 0 ` is
    "zero" (C2); anything ≥ 1 is a limit. **MAX is `Number.MAX_SAFE_INTEGER` (2^53−1); there is no
    lower server-side cap** — `count=1000000` is accepted and becomes `.limit(1000000)`.
  - refused on GET/HEAD: `abc`, `-3`, `-0`, `+5`, `2.5`, `0.0`, `1e2`, `0x10`, `10abc`, any value
    above 2^53−1, and a **repeated** `count` (qs turns `count=1&count=2` into an array, which is not
    a string → refused) or `count[]=…`.
- **Verb rules** (`origin/dev:lib/api/index.js:78-91`):
  - `GET`/`HEAD`: refused unless zero or a valid positive count → **HTTP 400**, JSON body
    `{"status":400,"message":"Bad count","description":"count must be a whole number of documents, 0 or greater"}`
    (`:63-69`, `:89-90`). The body is JSON even on `.csv`/`.txt`/`.tsv` extension routes.
  - `DELETE`: refused unless a valid positive count (so `count=0` is refused) → 400 with
    description `"count must be a whole number of documents, 1 or greater"` (`:78-83`). See C3.
  - `POST`/`PUT`/`PATCH`: `count` is ignored, never refused (`:85-87`).
- **Before (15.0.8):** no validation anywhere. Each storage module did
  `if (opts.count) this.limit(parseInt(opts.count))`
  (`origin/master:lib/server/entries.js:35-36`, `treatments.js:243-244`, `devicestatus.js:121-122`,
  `profile.js:102-103`, `activity.js:112-113`, `lib/authorization/storage.js:78-79`), so
  `2.5`→2, `1e2`→1, `10abc`→10, `+5`→5, `-3`→`limit(-3)` (MongoDB: at most 3 documents, single
  batch), `abc`/`0x10`→`limit(NaN)`/`limit(0)`. Devicestatus parsed its own count and fell back to
  10 for anything non-positive or non-numeric (`origin/master:lib/api/devicestatus/index.js:85-93`).
  The entries in-memory path compared the raw string (`origin/master:lib/api/entries/index.js:493-494`,
  `query.count <= inMemoryCollection.length` then `slice(0, query.count)`), so e.g. `1e2` served
  100 cached entries there but `parseInt` would have read 1.
- **After (candidate):** as above; every accepted count reaches storage through
  `applyCount` (`origin/dev:lib/server/count.js:74-80`) at the same six call sites
  (`origin/dev:lib/server/entries.js:36`, `treatments.js:244`, `devicestatus.js:122`,
  `profile.js:111`, `activity.js:113`, `lib/authorization/storage.js:79`).
- **Defaults when absent (unchanged):** entries 10 (`origin/dev:lib/api/entries/index.js:440,468,556`,
  `lib/constants.json:8`); treatments 100, or 1000 when `find` is present
  (`origin/dev:lib/api/treatments/index.js:85-88`); devicestatus 10
  (`origin/dev:lib/api/devicestatus/index.js:97`); `/profiles/` 10 and `/profile/` 10
  (`origin/dev:lib/api/profile/index.js:35-36,59`, `lib/constants.json:9`); activity: no limit.
- **What a client relying on the old behaviour observes:** HTTP 400 `Bad count` where it used to get
  data (for any computed count that can be fractional, negative, exponent-formatted, or sent twice).
  A client that treats 400 as "drop the batch" or "retry forever" stalls (S15).
- **Search hints:** `count=`, `"count"`, `@Query("count")`, `URLQueryItem(name: "count"`,
  `params: { count`, `count: ` in query maps, `hours * 12`, `* 12`, `/ 5`, `Math.`/`round` near
  count, `toString()` of a Double count, `String(format:` with `%f`, duplicate `count` in URL
  templates.

## C2 — v1 `count=0` on a read now always returns `[]` (it could return unbounded data, or 10 records)

- **PR / merge:** #8748 (merge `42c5e21e`); the storage half first appeared in #8738. **Status:** merged.
- **Surfaces:** S1, S15.
- **After:** `isZeroCount` (`origin/dev:lib/server/count.js:42-47`) → `applyCount` returns a stub
  cursor whose `toArray()` resolves `[]` (`:63-65`, `:75-77`); devicestatus maps a zero count to 0
  instead of the default (`origin/dev:lib/api/devicestatus/index.js:87-88`); `/profile/` returns `[]`
  (`origin/dev:lib/server/profile.js:88-100`). HTTP 200, body `[]`.
- **Before (15.0.8), route by route (read-derived):**
  | route | 15.0.8 answer to `count=0` | anchor |
  |---|---|---|
  | `GET /api/v1/entries(.json)` with no `find` or only `find[type]` | `[]` (in-memory `slice(0,'0')`) | `origin/master:lib/api/entries/index.js:493-494` |
  | same, with any other `find[...]` | **every matching entry** (`limit(0)` = no limit; the default 4-day date floor applies only when no date filter is given) | `origin/master:lib/server/entries.js:35-36` |
  | `/times/…`, `/slice/…` | every match (they always add a `find`) | as above |
  | `GET /api/v1/treatments` with `count` as the **only** query key | `[]` (cache slice) | `origin/master:lib/api/treatments/index.js:85-88` |
  | same, with any other key (a `find`, or even `token=`) | every match | `origin/master:lib/server/treatments.js:243-244` |
  | `GET /api/v1/devicestatus` | **10 records** (zero was "invalid" → default 10) | `origin/master:lib/api/devicestatus/index.js:85-93` |
  | `GET /api/v1/profile(.json)` | every profile (`Number('0')` → `limit(0)`) | `origin/master:lib/api/profile/index.js:49`, `lib/server/profile.js:87-91` |
  | `GET /api/v1/profiles` | every match | `origin/master:lib/server/profile.js:102-103` |
  | `GET /api/v1/activity` | every match | `origin/master:lib/server/activity.js:112-113` |
- **Routes that ignore `count` and are unchanged by `count=0`:** `/count/:storage/where` (still returns
  the aggregate), `/food*`, `/profile/current`, `/entries/current`, `/status`, `/verifyauth`.
- **What a client observes:** a `count=0` read that returned data (or 10 devicestatus) now returns `[]`.
  A client that computed a count which can be 0 (e.g. `hours*12` with hours 0, or "remaining = N − have")
  and relied on getting data sees an empty list; one that treats `[]` as "caught up" silently stops.
- **Search hints:** as C1, plus any arithmetic producing the count (`max(0,`, `- received`, `* 12`).

## C3 — v1 DELETE carrying an unreadable `count` is refused; a valid count still does not limit a delete

- **PR / merge:** #8738 then #8748 (`origin/dev:lib/api/index.js:78-83`). **Status:** merged.
- **Surfaces:** S1, S8, S15.
- **Before:** every v1 `remove` ignored `count` entirely — `deleteMany(query_for(opts))`
  (`origin/master:lib/server/entries.js:50-52`, `treatments.js:274-276`, `devicestatus.js:135-138`);
  profile/food/activity delete by `_id` only (`origin/master:lib/server/profile.js:144-147`,
  `food.js:156-159`, `activity.js:126-129`). So `DELETE …?count=0` or `?count=abc` deleted every match.
- **After:** `count` present and not a positive whole number (including `0`) → 400 "Bad count",
  **nothing deleted**. Valid `count` (e.g. `2`) → the delete runs and still removes **every** match
  (remove functions unchanged on dev).
- **Code-comment mismatch (not client-facing):** `origin/dev:lib/api/index.js:59-62` says such a delete
  "is refused as before"; 15.0.8 did not refuse it (the "before" is #8738's intermediate state).
- **Search hints:** `DELETE` / `.delete(` / `httpMethod = "DELETE"` with `count` in the same URL.

## C4 — `/api/v1/count/:storage/where` now counts with the collection's own filter rules; `pipeline` refused

- **PRs / merges:** #8738 (merge `d3358e91`) switched the filter builder; #8743 `bf/operators`
  (merge `1a36f023`) refuses `pipeline`. **Status:** merged. **Surfaces:** S4, S2, S3.
- **Before:** `find_options(opts)` with **no** collection options (`origin/master:lib/server/aggregate.js:19`)
  → date field `date`, default walker `{date,sgv}`, no `useEpoch`. Without `find[date]`/`find[dateString]`
  it added `date: {$gte: <ISO string 4 days ago>}` (`origin/master:lib/server/query.js:82-87`). For
  entries (`date` is a number) and for treatments/devicestatus (no `date` field / date is `created_at`)
  that matched nothing, so the route answered `[]` instead of `[{"_id":null,"count":N}]`. Caller-supplied
  `opts.pipeline` stages were appended (`origin/master:lib/server/aggregate.js:21-22`).
- **After:** `api.query_for(opts)` of the selected collection (`origin/dev:lib/server/aggregate.js:44`;
  wired at `origin/dev:lib/server/entries.js:204-206`, `treatments.js:412,433`,
  `devicestatus.js:155,158`) — same date field, epoch handling, coercion (C7) and operator allowlist
  (C5) as the list routes. Any `pipeline` parameter → 400 JSON
  `{"status":400,"message":"The pipeline parameter is not supported by the Nightscout API v1. Use find[...] to filter the records a count is taken over."}`
  (`origin/dev:lib/server/aggregate.js:17-23,40`; answered by `origin/dev:lib/api/entries/index.js:531-536`).
  Also new: `treatments`/`devicestatus` storage requires that collection's read permission (C14).
- **What a client observes:** a count that was `[]` (or 0) now returns a real number — often much larger.
  A client that passed `pipeline` gets 400.
- **Search hints:** `api/v1/count/`, `/where`, `pipeline`, `$group`.

## C5 — v1 filter operator allowlist (and server-side JavaScript refusal)

- **PR / merge:** #8743 `bf/operators` (merge `1a36f023`, 2026-09-18). **Status:** merged.
- **Surfaces:** S2, S12, S15.
- **Where enforced:** `origin/dev:lib/server/query.js:245-249`, on the caller's literal `find` object,
  before any rewriting, for **every** consumer of the v1 query builder: entries (incl. `/times`,
  `/slice`, `/count/.../where`, `/echo`), treatments, devicestatus, `/profiles` (profile `list_query`),
  activity, and the internal auth-subject storage (`origin/dev:lib/authorization/storage.js:27`).
  **Not** enforced on: `/api/v1/food*` (takes no filter), `/api/v1/profile/` (no filter), API v3
  (own query parser), API v2, websocket `dbUpdate`/`dbRemove` (by `_id`).
- **Exact list** (`origin/dev:lib/server/query-operator-allowlist.js:72-78`):
  - on a field: `$eq $ne $gt $gte $lt $lte $in $nin $regex $options $exists $type`;
  - top level (or inside an `$and`/`$or` branch): `$and $or`.
  - A plain field with a non-operator value (or a sub-document with no `$` keys) is an equality match
    and passes (`:96-102`). Values are **not** recursed into (`:121-127`).
- **Refused (400):** everything else, at any position — explicitly `$not`, `$elemMatch`, `$all`,
  `$size`, `$mod`, `$nor`, `$text`, `$expr`, `$comment`, `$jsonSchema`, geospatial operators; a
  predicate object mixing a field key with `$` keys; `$where`/`$function`/`$accumulator` (refused first
  by `origin/dev:lib/storage/assert-no-query-javascript.js:15-19` with message
  `"Server-side JavaScript is not allowed in database queries"`).
  - `$regex` **with** `$options` is allowed.
  - `$expr` on `/api/v1/profiles` — worked on 15.0.8 (profile `list_query` reached the raw collection:
    `origin/master:lib/server/profile.js:94-116`) — is now refused.
  - `pipeline` on `/count/…/where` — see C4.
- **Error body:** HTTP 400 JSON `{"status":400,"message":"Query operator <op> is not supported by the Nightscout API v1 <query|field filter>. Supported operators: $and $or (top level), $eq $ne $gt $gte $lt $lte $in $nin $regex $options $exists $type (on a field)."}`
  (`origin/dev:lib/server/query-operator-allowlist.js:80-90`, sent by
  `origin/dev:lib/api/shared/query-error.js:25-32`). Exception: `/api/v1/echo/...` builds the query
  synchronously (`origin/dev:lib/api/entries/index.js:447-449`), so the error goes to express's
  `errorhandler` (`origin/dev:lib/server/app.js:389-391`) — status 400 from `err.status`, body in
  errorhandler's format, not the JSON above (library behaviour, read-derived).
- **Structural gap to know about (not a bypass):** `$and`/`$or` branches are only walked when the value
  is an array (`:110-113`). On the candidate qs/express keep ≤1000 branches as an array (C60), so this
  only matters for a non-array `$or`, which MongoDB itself rejects.
- **Before (15.0.8):** no allowlist; any operator reached MongoDB (`origin/master:lib/server/query.js:156-176`).
- **What a client observes:** a filter using a refused operator now gets 400 with the operator named,
  where it used to get data (e.g. `$not`, `$elemMatch`, `$all`, `$size`), an HTTP 500, or an empty list.
- **Search hints:** `$not`, `$elemMatch`, `$all`, `$size`, `$nor`, `$expr`, `$where`, `$text`, `$mod`,
  `%24not` (URL-encoded `$`), `pipeline`, `find[$`, and any operator built from a variable.

## C6 — v1 read/delete errors caused by a refused filter are 400 JSON, and several error paths stopped being 200/500

- **PRs / merges:** #8743 (merge `1a36f023`) added `lib/api/shared/query-error.js` and wired it in;
  #8697 (merge `0ab266a3`, 2026-09-06) added the treatments `err` check. **Status:** merged. **Surfaces:** S15.
- **Before → after per endpoint (read-derived):**
  | endpoint | 15.0.8 on a query error | candidate |
  |---|---|---|
  | `GET /api/v1/entries`, `/times`, `/slice` | 500 `Mongo Error` (`origin/master:lib/api/entries/index.js:138`) | 400 JSON for a refused filter (`origin/dev:…:139-141`); other errors 500 as before |
  | `POST /api/v1/entries` error path | 500 `Mongo Error` | 400 for a refused query (`origin/dev:…:262`) |
  | `GET /api/v1/count/:storage/where` | error passed to `next(err)` | 400 JSON (`origin/dev:…:533-536`) |
  | `DELETE /api/v1/entries` | `next(err)` | 400 (`origin/dev:…:562`) |
  | `GET /api/v1/treatments` | `err` ignored; `results.forEach` on null throws (`origin/master:lib/api/treatments/index.js:27-35`) | 400 JSON for refused; else 500 `Query Error` with the message (`origin/dev:…:29-32`) |
  | `DELETE /api/v1/treatments` | `next(err)` | 400 (`origin/dev:…:162`) |
  | `GET /api/v1/devicestatus` | 500 with body `[]` | 400 for refused; else 500 `[]` (`origin/dev:lib/api/devicestatus/index.js:130-133`) |
  | `GET /api/v1/profiles` | `err` ignored → **200 with an empty/undefined body** (`origin/master:lib/api/profile/index.js:40-42`) | 400 for refused; else **500** `{"status":500,"message":"Unable to read profiles"}` (`origin/dev:…:41-49`) |
  | `GET /api/v1/activity` | `err` ignored → throws on `results.forEach` (`origin/master:lib/api/activity/index.js:32`) | 400 for refused (`origin/dev:…:31-34`); other errors still throw |
- **What a client observes:** a refused filter is now distinguishable from an outage (400 vs 500). A
  profile read failure that used to be a 200 with no JSON is now a 500.
- **Search hints:** handling of `statusCode == 400` vs `500` on reads; `"Mongo Error"`, `"Query Error"`,
  `"Unable to read profiles"`, `message` field parsing.

## C7 — v1 `find[...]` values are typed from a schema table: numbers as floats, booleans as booleans, many more fields

- **PR / merge:** #8737 `bf/coercion` (merge `025f1310`, 2026-09-18). **Status:** merged. **Surfaces:** S3, S2.
- **Before (15.0.8):** hand-written `parseInt` walkers only:
  - entries: `date sgv filtered unfiltered rssi noise mbg` (`origin/master:lib/server/entries.js:185-194`);
  - treatments: `insulin carbs glucose` (+ `notes eventType enteredBy` as regex) (`origin/master:lib/server/treatments.js:259-268`);
  - devicestatus and activity: the default `{date, sgv}` (`origin/master:lib/server/query.js:40-42`,
    `devicestatus.js:173-174`, `activity.js:146-147`); profile: none (`origin/master:lib/server/profile.js:96-98`).
  - Every other field stayed a **string**, so numeric comparisons were string-vs-number and matched
    nothing (e.g. `find[duration][$gte]=30` on temp basals → `[]`), and `parseInt` truncated decimals
    (`find[insulin][$gte]=1.5` → `$gte: 1`).
- **After:** `schemaWalker` (`origin/dev:lib/server/query.js:287-311`) looks up each queried field in
  `origin/dev:lib/server/query-coercion.json` and applies `parseFloat` for `integer`/`number` and
  `true`/`false` (case-insensitive) → boolean for `boolean`
  (`origin/dev:lib/server/query-coercion.js:90-111,123-128`). Explicit walkers still win (treatments'
  `notes/eventType/enteredBy` regex). Fields now coerced, by collection:
  - **entries:** `date delta filtered glucose intercept mbg noise rssi scale sgv slope srvCreated
    srvModified trend trendRate unfiltered utcOffset` (numbers); `isCalibration isReadOnly isValid` (booleans).
  - **treatments:** `absolute absorptionTime amount carbs date duration endmills fat glucose insulin
    insulinNeedsScaleFactor mills percent percentage programmed protein pumpId rate srvCreated
    srvModified targetBottom targetTop timeshift unabsorbed utcOffset` (numbers);
    `automatic isBasalInsulin isReadOnly isValid` (booleans).
  - **devicestatus:** ~95 dotted paths incl. `date mills utcOffset uploaderBattery uploader.battery
    pump.reservoir pump.battery.percent loop.cob.cob loop.iob.iob openaps.suggested.COB
    openaps.suggested.IOB openaps.enacted.* openaps.iob.* override.*` (numbers) and `isCharging
    isValid pump.suspended pump.bolusing override.active …` (booleans).
  - **profile:** `utcOffset srvCreated srvModified loopSettings.*` numbers/booleans, `isValid`.
  - **activity:** none (it lost the old default `date`/`sgv` parseInt).
  - Not coerced (still strings): `created_at`, `dateString`, `startDate`, `type`, `eventType`,
    `enteredBy`, `device`, `_id` (handled separately), and any field not in the table.
- **Operands:** under `$in`/`$nin` every element is converted; under `$exists`, `$type`, `$regex`,
  `$options` (and `$where`/`$expr`/`$text`/`$comment`/`$jsonSchema`) the operand is **not** converted
  as a field value (`origin/dev:lib/server/query-coercion.js:29-32,138-146`); `$type` digits become a
  number (`:49-61`) — but only for fields in the table (for other fields `$type=2` still reaches MongoDB
  as a string and errors, as on 15.0.8).
- **What a client observes:** filters on `duration`, `absolute`, `percent`, `rate`, `amount`,
  boolean flags, and decimal bounds now return records they did not before — "often many more". A
  client that compensated for the old behaviour (e.g. filtering numerically client-side after an
  over-broad query, or string-encoding a bound) may now double-filter or get different sets.
  `parseFloat` also reads `1.7e12` correctly where `parseInt` read `1`.
- **Search hints:** `find[duration]`, `find[absolute]`, `find[percent]`, `find[rate]`, `find[insulin]`,
  `find[carbs]`, `find[isValid]`, `find[automatic]`, `find[date]`, `find[mills]`, `find[srvModified]`,
  `find[utcOffset]`, `find[pump.`, `find[openaps.`, `find[loop.`, `find[uploader.`.

## C8 — `$exists` operands `true`/`false`/`1`/`0` are read as booleans on every field

- **PR / merge:** #8737 (merge `025f1310`). **Status:** merged. **Surfaces:** S2, S3.
- **Before:** the operand reached MongoDB as a string (MongoDB treats any string as **true**), and on
  walker-typed fields as `parseInt('false')` = NaN (also true). So `find[x][$exists]=false` returned the
  records that **have** `x` (`origin/master:lib/server/query.js:223-248`).
- **After:** `normalizeOperands` walks the whole built query and rewrites any `$exists` operand
  `true`/`1` → `true`, `false`/`0` → `false` (case-insensitive); any other spelling — empty (`find[x][$exists]`
  or `find[x][$exists]=`), `null`, `yes` — is passed through unchanged and still means "exists"
  (`origin/dev:lib/server/query.js:194-239,267`).
- **What a client observes:** `$exists=false` / `$exists=0` now returns the records **without** the
  field (the opposite set). `$exists=1` unchanged in effect.
- **Search hints:** `$exists`, `%24exists`.

## C9 — `$regex` operands are no longer passed through the field walker (treatments slash-regex edge)

- **PR / merge:** #8737. **Status:** merged. **Surfaces:** S2.
- **Before:** the walker converted **every** leaf, so on treatments `find[notes|eventType|enteredBy][$regex]=/x/i`
  became a RegExp object (`origin/master:lib/server/query.js:233-241`, walker `lib/server/treatments.js:260-266`).
- **After:** leaves under `$regex`/`$options` are left as strings (`origin/dev:lib/server/query.js:377-386`),
  so a slash-delimited value under `$regex` is a pattern containing literal slashes and matches nothing.
  The direct form `find[eventType]=/x/i` (no operator) is still converted to a RegExp (`:363-365`) —
  that is what Nightscout's own reports send (`origin/dev:lib/report/reportclient.js:331,368`).
- **What a client observes:** `find[eventType][$regex]=/Temp/` (with slashes) → `[]`; plain
  `find[eventType][$regex]=Temp` works as before.
- **Search hints:** `[$regex]=/`, `$regex` combined with `/…/` literal.

## C10 — date filters: only an unescaped `+` in a UTC offset is repaired

- **PR / merge:** #8697 `fix/treatments-query-errors-8675` (merge `0ab266a3`). **Status:** merged. **Surfaces:** S3.
- **Before:** the first space anywhere in a non-numeric date-field value was replaced with `+`
  (`origin/master:lib/server/query.js:66-67`), so `2026-09-23 10:00:00` (space separator) became
  `2026-09-23+10:00:00` and could throw "Cannot parse … as a valid ISO-8601 date" (→ error path).
- **After:** only a space before a trailing offset is turned into `+`
  (`origin/dev:lib/server/query.js:80-82`). Applies to the collection's date field (`date` for
  entries, `created_at` for treatments/devicestatus/activity, `startDate` for profiles).
- **What a client observes:** space-separated date strings in `find[created_at][$gte]` etc. now parse.
- **Search hints:** date formatters producing `yyyy-MM-dd HH:mm:ss` used in `find[created_at]`.

## C11 — API v3 `limit`: only plain digits accepted

- **PR / merge:** #8738 (merge `d3358e91`). **Status:** merged. **Surfaces:** S13, S15.
- **Before:** `!isNaN(limit) && limit > 0 && limit <= max` then `parseInt(limit, 10)`
  (`origin/master:lib/api3/generic/collection.js:80-85`): `0x10` → limit 0 = **whole collection**;
  `1e2` → 1; `2.5` → 2.
- **After:** must match `^\s*\d+\s*$` and be a safe integer in `1..API3_MAX_LIMIT`
  (`origin/dev:lib/api3/generic/collection.js:80-93`); otherwise 400 `"Parameter limit out of tolerance"`
  (`origin/dev:lib/api3/const.json:26`). `limit=0` was already 400 on both. Absent/empty → max limit, as before.
- **Search hints:** `limit=` on `/api/v3/`, `"limit"` query items.

## C12 — API v3 search sort adds `_id` as final tie-breaker (paging no longer skips/repeats)

- **PR / merge:** #8738. **Status:** merged. **Surfaces:** S13.
- **Before:** sort key chain ended at `created_at`, `date` (`origin/master:lib/api3/generic/search/input.js`, `parseSort`).
- **After:** `sort._id = sortDirection` appended (`origin/dev:lib/api3/generic/search/input.js:191`).
  Order among documents that tie on every earlier key changes; `skip` paging becomes stable.
- **What a client observes:** a pager that saw duplicates/gaps no longer does; a client that de-duplicated
  across pages still works. Tied-record order may differ from 15.0.8.
- **Search hints:** `/api/v3/.*?(sort|sort$desc)=`, `skip=`, paging loops.

## C13 — API v3 `fields` with a dotted path now returns that sub-path

- **PR / merge:** #8738. **Status:** merged. **Surfaces:** S13.
- **Before:** after the storage projection, every top-level key not literally in the list was deleted
  (`origin/master:lib/api3/shared/fieldsProjector.js:62-67`), so `fields=loop.cob` returned no `loop` at all.
- **After:** `pruneToFields` keeps named sub-paths (`origin/dev:lib/api3/shared/fieldsProjector.js:10-40,103`):
  `fields=loop.cob` returns `{loop:{cob:…}}`.
- **Search hints:** `fields=` with a `.` on `/api/v3/`.

## C14 — `/api/v1/count/{treatments|devicestatus}/where` and `/api/v1/slice/{treatments|devicestatus}/…` require that collection's read permission

- **PR / merge:** #8751 `bf2/backports` (merge `4011193e`, 2026-09-23). **Status:** merged. **Surfaces:** S4, S5.
- These are the release notes' "two shared read addresses" (security item 4). `prep_storage`
  (`origin/dev:lib/api/entries/index.js:734-744`) now adds `api:<storage>:read` on top of the router's
  `api:entries:read` (`:55`). 15.0.8 checked only `api:entries:read`
  (`origin/master:lib/api/entries/index.js` `prep_storage`). Refusal: 401. `/times/` and `/echo/` have no
  `:storage` parameter and are unaffected. Full detail: **C14-detail** below (from the socket/permissions pass).
- **Search hints:** `api/v1/count/treatments`, `api/v1/count/devicestatus`, `api/v1/slice/`.

## C15 — `GET /api/v1/food/quickpicks` returns JSON-written and legacy quick picks, in numeric position order

- **PR / merge:** #8735 `bf/food` (merge `ff0d506c`, 2026-09-20). **Status:** merged. **Surfaces:** S9.
- **Before:** `find({type:'quickpick', hidden:'false'}).sort({position:1})`
  (`origin/master:lib/server/food.js` `listquickpicks`): only records whose `hidden` is the **string**
  `'false'` (what the form-encoding web editor writes); a JSON client's boolean `false` or a record with
  no `hidden` was omitted; `position` sorted by BSON type/lexicographic for strings (`'10'` before `'2'`).
- **After:** `{type:'quickpick', hidden: {$nin:[true,'true']}}`, then sorted in JS by `parseInt(position)`,
  unusable positions last (`origin/dev:lib/server/food.js:145-164`, `lib/food/quickpick.js:36-43`).
- **What a client observes:** more quick picks (boolean-`false` and missing-`hidden` ones), different order.
  `GET /api/v1/food` and `/food/regular` unchanged.
- **Search hints:** `food/quickpicks`, `quickpick`, `hidden`, `hideafteruse`, `position`.

## C16 — web bolus calculator: quick-pick list and "hide after use" write

- **PRs / merges:** #8735 (merge `ff0d506c`), #8756 `bf3/quickpick-rebuild` (merge `c11888ed`). **Status:** merged.
- **Surfaces:** HTML page; S9 (stored `hidden` value other clients read).
- **Before:** the chooser listed every food record but indexed into the quick-pick array (wrong record
  loaded), was built before food data arrived ("(none)" only), and `if (qp.hideafteruse)` treated the
  stored string `'false'` as true, so a quick pick with `hideafteruse:'false'` was **PUT back with
  `hidden: true`** after use (`origin/master:lib/client/boluscalc.js` ~590, `loadFoodQuickpicks`).
- **After:** list = `quickpick.selectable(food)` (type quickpick, not hidden, by position), rebuilt on each
  open (`origin/dev:lib/client/boluscalc.js:162,646-679`); hide-after-use only when `hideafteruse` is
  `true`/`'true'` (`:595`).
- **What another client observes:** fewer quick picks flipped to `hidden:true` by the web page.
- **Search hints:** `hideafteruse`, `hidden` on food records.

## C17 — COB property: controller-reported COB is used without a profile; `treatmentCOB` is now a number; AAPS/Loop blocks without timestamps dated by the record

- **PR / merge:** #8587 `fix/cob-uploader-reported-value` (merge `48441640`, 2026-09-04; commit `34e9b2da`). **Status:** merged.
- **Surfaces:** S11 (via `/api/v2/properties` `cob`, `/api/v2/summary` `cob`, pills, websocket-driven page).
- **Before:** `cobTotal` returned `{}` unless the profile had data **and** sens **and** carbratio
  (`origin/master:lib/plugins/cob.js:26-35`). With a profile, a devicestatus COB ≤10 min old was
  already preferred; otherwise treatment COB with `source:'Care Portal'` and `treatmentCOB` = the full
  treatment-COB **object** (`:43-54`). Device COB dating: `moment(block.timestamp)` — a missing
  timestamp (AAPS `openaps.suggested`, a `loop.cob` without one) became **now** (`origin/master:lib/plugins/cob.js`
  `fromDeviceStatus`).
- **After:** current device COB is returned with or without a profile; if profile+treatments exist,
  `treatmentCOB` is added as a **number** only when non-zero (`origin/dev:lib/plugins/cob.js:26-67`).
  Fallback treatment COB (profile required) no longer carries `treatmentCOB`; its `source` is
  `translate('Care Portal')` — localised on non-English sites (`:64`). Block selection:
  `origin/dev:lib/client-core/devicestatus/cob.js:27-94` — a block's time falls back to the record's
  `mills`; COB given as a numeric string is accepted; OpenAPS wins over Loop; newer of enacted/suggested,
  ties to suggested. No-candidate now returns `{}` instead of `undefined` (`origin/dev:lib/plugins/cob.js:106`).
- **What a client observes:** `cob` present on sites without a full profile; `cob.treatmentCOB` type changed
  object → number (or absent); `cob.source` may be a translated string; COB may differ from 15.0.8 for AAPS/Trio.
- **Release-notes wording** ("now shows the value reported by your looping app rather than Nightscout's own
  estimate"): see mismatches — 15.0.8 already preferred a current device COB when a profile existed.
- **Search hints:** `api/v2/properties`, `properties?`, `"cob"`, `treatmentCOB`, `cob.source`, `displayLine`.

## C18 — insulin-age URGENT level and "Insulin reservoir change overdue!" notification now fire

- **PR / merge:** #8739 `bf/alarms` (merge `7a5561f4`, 2026-09-20). **Status:** merged. **Surfaces:** S6 (`/alarm` notifications), S14 (push services), `/api/v2/properties` `iage`.
- **Before:** `if (insulinInfo.age >= insulinInfo.urgent)` — `urgent` undefined, never true
  (`origin/master:lib/plugins/insulinage.js:92`).
- **After:** `>= prefs.urgent` (`origin/dev:lib/plugins/insulinage.js:92`): `iage.level` can be URGENT;
  with `IAGE_ENABLE_ALERTS`, a one-shot urgent notification (sound `persistent`) at `age === urgent`.
- **What a client observes:** a new urgent notification on the alarm socket / push channels and an
  URGENT iage property.
- **Search hints:** `iage`, `Insulin reservoir change overdue`, `persistent` sound handling.

## C19 — voice assistants: request locale ignored; unhandled Alexa request types answered

- **PRs / merges:** #8739 (merge `7a5561f4`) and #8753 `bf2/ops` (merge `3a38c6f2`). **Status:** merged. **Surfaces:** S14.
- **Before:** `POST /api/v1/alexa` and `/api/v1/googlehome` set the **process-wide** language and
  `moment.locale` from `request.locale` / `queryResult.languageCode`
  (`origin/master:lib/api/alexa/index.js:23-30`, `lib/api/googlehome/index.js:22-29`); an Alexa request
  type other than the handled ones got no response (hung).
- **After:** no locale change; relative times are localised per call to the site's configured language
  (`origin/dev:lib/plugins/virtAsstBase.js:12-15,31,58`); unknown Alexa request types get HTTP 200 JSON `""`
  (`origin/dev:lib/api/alexa/index.js:59-66`).
- **Search hints:** `request.locale`, `languageCode`, `api/v1/alexa`, `api/v1/googlehome`.

## C20 — `POST /api/v2/notifications/loop` 500 bodies are fixed text; thrown errors answered

- **PR / merge:** #8583 `fix/opaque-error-response` (merge `4f6151d7`, 2026-09-05). **Status:** merged. **Surfaces:** S14, S15.
- **Before:** 500 with the raw error string from `lib/server/loop.js` (e.g. `Loop notification failed:
  LOOP_APNS_KEY not set.`, `APNs delivery failed: <reason>`) (`origin/master:lib/api2/notifications-v2.js:18-25`);
  a synchronous throw was not caught.
- **After:** 500 with a mapped message (`origin/dev:lib/api2/loop-notification-errors.js:5-82`), exact-match
  on the server string, else `"Loop notification failed unexpectedly. Ask the Nightscout administrator to check the server logs for details."`;
  throws caught → same 500 (`origin/dev:lib/api2/notifications-v2.js:19-37`). Success still `200 OK`.
  Web careportal (`lib/plugins/loop.js:121-133`, browser) maps 401/403/timeout to its own messages.
- **What a client observes:** a caregiver app that parsed or displayed the old 500 body sees different text
  (e.g. an app matching `"APNs delivery failed: BadDeviceToken"` no longer matches).
- **Search hints:** `notifications/loop`, `LOOP_APNS`, `APNs delivery failed`, `Loop notification failed`, `remoteBolus`, `remoteCarbs`.

## C21 — server-side profile interpretation: profile-switch `profileJson` schedules, store detection, missing names

- **PRs / merges:** #8701 `fix/profile-switch-preprocessing-8584` (merge `5a09befd`), #8702
  `fix/empty-profile-name-8562` (merge `ca35f2a3`), both 2026-09-06. **Status:** merged.
- **Surfaces:** S10, S11 (server plugins → `/api/v2/properties` basal/iob/cob/bwp, pills; also the web page).
- **Before → after** (`lib/profilefunctions.js` is shared by server and page):
  - A Profile Switch treatment's `profileJson` was stored into the active store **without** computing
    `timeAsSeconds` for its schedule entries (`origin/master:lib/profilefunctions.js:399-413`); now
    `preprocessProfileOnLoad(json)` runs first (`origin/dev:lib/profilefunctions.js:405,416`), so
    time-of-day lookups (basal, ISF, CR, targets) on a `profileJson` switch (e.g. AndroidAPS) use the right entry.
  - A profile document was converted "on the fly" as a legacy single profile whenever `defaultProfile`
    was falsy (e.g. `""`) (`origin/master:lib/profilefunctions.js:61`); now only when `store` is missing
    or not an object (`origin/dev:lib/profilefunctions.js:61`).
  - A profile name / switch target not present in the store now yields `{}` / `null` instead of reading
    `store[undefined]` (`origin/dev:lib/profilefunctions.js:193-194,372-377`).
- **What a client observes:** server-computed basal/IOB/COB/BWP values can differ on sites that use
  `profileJson` switches or an empty `defaultProfile`. Stored data unchanged.
- **Search hints:** `profileJson`, `Profile Switch`, `defaultProfile: ""`, `api/v2/properties` `basal`.

## C22 — web profile editor no longer saves a fabricated default profile

- **PRs / merges:** #8732 `wip/mobile-ui-fixes` (merge `59430336`, 2026-09-21), #8702. **Status:** merged. **Surfaces:** HTML; S10 (what gets POSTed).
- **Before:** if `GET /api/v1/profile.json?count=20` returned `[]` or failed, the editor seeded a default
  profile and could POST it (`origin/master:lib/profile/profileeditor.js` load/error handlers).
- **After:** empty → nothing fabricated; failure → controls stay disabled with "Your profile could not be
  loaded. Reload before editing." (`origin/dev:lib/profile/profileeditor.js:29-34,76-104`); unnamed (`""`)
  profiles are shown as "(unnamed)" and preserved, not renamed.
- **Search hints:** n/a (browser); API consumers see fewer default-valued profile documents.

## C23 — `sage` property shows `n/a` when no sensor treatment exists

- **PR / merge:** #8732 (merge `59430336`). **Status:** merged. **Surfaces:** `/api/v2/properties` `sage`, pills.
- `origin/dev:lib/plugins/sensorage.js:135-137` sets `display = 'n/a '` when no Sensor Start/Change is found (15.0.8: default display).
- **Search hints:** `sage`, `display`.

## C24 — web chart "Move / Move carbs / Move insulin" write new time fields and drop page-derived fields

- **PR / merge:** #8760 `bf/split-drag-time` (merge `ddd9b600`, 2026-09-23). **Status:** merged. **Surfaces:** S6 (websocket messages the page sends), S8 (stored treatments other clients read).
- **Before:** Move sent `dbUpdate {created_at}` only; split sent `dbUpdateUnset {insulin|carbs:1}` and
  `dbAdd` of a copy of the **page object**, carrying page-derived `mills`, `endmills`, `mgdl`, `scaled`,
  `cuttedby`, `cutting` and `date` (a Date, so stored as an ISO **string**)
  (`origin/master:lib/client/renderer.js` drag `end` handler).
- **After** (`origin/dev:lib/client/renderer.js:808-955` (drag `end` handler), `lib/client/treatmenttime.js:31-117`):
  Move also sends `dbUpdateUnset {mills,endmills,mgdl,scaled}` and sets a stored `date` to the new epoch
  ms; split's `dbAdd` record has no derived fields, `date` only if the original had a stored one (as a
  number), and the source record gets the same unset and `date` alignment. Report editor PUT (#8760):
  `alignEditedRecord` drops the same fields and moves a stored `date` (`origin/dev:lib/report_plugins/treatments.js:230`).
- **What another client observes:** treatments edited on the web chart no longer carry stale `mills`/
  `mgdl`/`scaled`, and no longer gain a string-typed `date`; `date` (if present) is a number matching
  `created_at`.
- **Search hints:** reading `date` / `mills` from treatments, `dbUpdateUnset`, v3 `date` typing.

## C25 — deleted records no longer reappear from the server cache

- **PRs / merges:** #8567 `fix/cache-stale-delete-race` (merge `948aafac`), #8740 `bf/cache` (merge `49f562d8`). **Status:** merged. **Surfaces:** S8, S4 (cache-served reads), S6 (`dataUpdate`).
- **Before:** a delete landing while the periodic load was in flight could be merged back into the cache
  and served by cache-backed reads (`/api/v1/entries`, `/treatments`, `/devicestatus` without filters;
  websocket data) until retention expiry.
- **After:** removal generation counters; the loader retries/discards a racing load
  (`origin/dev:lib/server/cache.js:32-43,117-140`, `lib/data/dataloader.js:160-199,300-337,455-497`);
  cache retains JSON clones (`cache.js:79-117`).
- **What a client observes:** a deleted treatment/entry/devicestatus stays deleted in cache-served reads.
- **Search hints:** clients relying on re-seeing a record after DELETE (none expected).

## C26 — web page: treatment delete + update in one socket delta no longer freezes the page

- **PR / merge:** #8734 `bf/merge` (merge `fdd08706`). **Status:** merged. **Surfaces:** HTML only.
- `origin/dev:lib/client/receiveddata.js:98-114` (inner bound re-read) vs `origin/master:…:98-107`.
- No wire change; `dataUpdate` delta format unchanged (`lib/data/calcdelta.js` rewrite in #8733 is claimed
  order-preserving; **read-derived**).

## C27 — web page URL parameters: `_` no longer turned into a space; valueless parameters tolerated (browser only)

- **PR / merge:** #8736 `bf/parms` (merge `2e94de1b`). **Status:** merged. **Surfaces:** HTML; S5 (the page's own `?token=`).
- **Scope:** `lib/client/browser-utils.js` `queryParms` — **browser-only**; the server's `req.query`
  parsing of `token=` etc. is unchanged. Before: `params[k] = item.split('=')[1].replace(/[_\+]/g,' ')`
  (throws on `?mute`, trailing `&`, bare `?`) (`origin/master:lib/client/browser-utils.js:45-47`). After:
  empty segments skipped, valueless → `''`, only `+` → space (`origin/dev:lib/client/browser-utils.js:43-75`).
  The two parameters read this way are `token` and `mute`.
- **What a client observes:** a web page opened with `?token=<subject_with_underscore>-<digest>` sends the
  exact token (it already worked, because the server matches on the digest).
- **Search hints:** apps that open the web page with `?token=` (WebView followers, widgets).

## C28 — env: credential-like extended settings stay strings

- **PR / merge:** #8741 `wip/dtschida/env-credential-coercion` (merge `bcd171cb`). **Status:** merged.
- **Surfaces:** none of the API; affects outbound logins by connect/bridge/mmconnect and Loop APNs settings.
- `origin/dev:lib/server/env.js:300-334`: `connect.{shareAccountName,sharePassword,carelinkUsername,
  carelinkPassword,carelinkPatientUsername,glookoPassword,glookoSerialNumber,glookoDeviceId,linkUpPassword,
  sourceApiSecret}`, `loop.{apnsKeyId,developerTeamId}`, `bridge.{userName,password}`,
  `mmconnect.{userName,password}` are not `Number()`-converted. These are all filtered out of
  `/api/v1/status` `extendedSettings` (`origin/dev:lib/settings.js:77-85`), so no status-JSON change.
- **Search hints:** none (operator-facing).

## C29 — logging-only changes

- #8726 (merge `a8888f0d`): `DEBUG_LOGGING` gates tick/reload/"Load Complete" lines
  (`origin/dev:lib/server/env.js:47-48`, `bootevent.js:351-362`, `dataloader.js:116-124`); `CONNECT_DEBUG`
  (`env.js:61-66`). #8757 (merge `d0d6b433`): mmconnect deprecation text (`lib/plugins/mmconnect.js`,
  `bootevent.js:418-422`). #8753: boot-error page tolerates an error with no `err`
  (`origin/dev:lib/server/booterror.js:24-28`) and `isPluginEnabled` correctness
  (`origin/dev:lib/plugins/index.js:241`; no callers). #8739: `ENABLE` misspelling suggestions in the log
  (`origin/dev:lib/plugins/index.js:129-238`). No wire effect.

## C30 — reports page (browser) fixes

- #8602 A1c units (`lib/report_plugins/dailystats.js`), #8588 uniq-SGV cascade (`lib/report/uniqsgv.js`),
  #8589 re-init on socket reconnect, #8590 treatments report event-type filter / labels
  (`views/reportindex.html`), #8729 chart container height race, #8699 clock face for low+falling
  (`lib/client/clock-client.js:194-207`), #8755 alarm on a page with no reading (`lib/client/index.js:1206-1262`).
  HTML only; the report page's API queries are the same shapes (`origin/dev:lib/report/reportclient.js:228-796`).
  Note the report page itself uses `count=10000`, `count=1000`, `count=1` — all valid under C1.

## C31 — "Nightscout readable by world" admin notice

- #8746 (merge `74fc6619`). Visible only in `GET /api/v1/adminnotifies` (admin). Full detail: **C31-detail** below.

## C32 — reported version is `15.0.9`

- #8597 `wip/15.0.9-dev-bump` (merge `5c26c9d2`): `package.json` version 15.0.8 → 15.0.9, surfaced as
  `/api/v1/status` `version` and API v3 `/api/v3/version`. **Surfaces:** S4.
- Dev-channel sites already report 15.0.9 before release (release notes say so).
- **Search hints:** `version` parsing / comparisons against `15.0`.

## C33 — built-in connector: nightscout-connect 0.0.13 → 0.1.0-dev.3

- **PRs / merges:** #8752 `bf/connect-pin-0.1.0` (merge `f0954a6a`, → 0.1.0-dev.2), #8759
  `bf/connect-pin-0.1.0-dev.3` (merge `feafa533`). **Status:** merged. `origin/dev:package.json`
  `"nightscout-connect": "0.1.0-dev.3"`, lock `origin/dev:package-lock.json:7892-7895` (registry
  tarball) vs `origin/master:package-lock.json:7398-7401` (GitHub `v0.0.13` tarball).
- **Surfaces:** S5, S1, S2 on the **source** Nightscout site when `CONNECT_SOURCE=nightscout`; data the
  receiving site stores.
- **As a client of a source Nightscout** (`externals/nightscout-connect@977da8a` = tag `v0.1.0-dev.3`,
  2026-09-23, `lib/sources/nightscout.js`): reads `/api/v1/entries.json` (`find[dateString][$gt]`),
  `/api/v1/treatments.json` and `/api/v1/devicestatus.json` (`find[created_at][$gt]`) with
  `count=sourceMaxCount` (`:60`, `:248-250`); profiles via `/api/v1/profile.json?count=…` and, new,
  `/api/v1/profiles.json` with `find[created_at][$gt]`, `find[startDate][$gte|$lt]` and `count=1`
  (`:88-120`); auth via `/api/v2/authorization/subjects`, `/api/v1/verifyauth`,
  `/api/v2/authorization/request/<token>` (`:150-209`). `sourceMaxCount = opts.sourceMaxCount || 1000`
  (`:46`) — if an operator sets a non-integer `CONNECT_SOURCE_MAX_COUNT`, a 15.0.9 source answers 400
  (C1); `0` falls back to 1000. All operators used are in the allowlist (C5).
  v0.0.13 (`b394411`, 2026-07-07) read profiles only via `/api/v1/profile.json?count=…` (`:65`).
- **As the receiving site's writer:** writes through `ctx.*` in-process (`lib/outputs/internal.js`), not
  HTTP, so C1's middleware does not apply; C5/C7 do (they are in the query builder). Behaviour changes
  (profile updates copied, log redaction, retry backoff, `nightscout-connect-reader` role) are described in
  the release notes' connector section, which is behind `<!-- PENDING: connector v0.1.0 tag -->`
  markers; not re-derived here beyond the query shapes.
- **Search hints (for the join step):** the connector itself is the client; check `sourceMaxCount`,
  `count: 1` on profiles, and `find[startDate]`.

## C34 — language table: `lt` added; Slovenian file/speech code `sl_SI` / `sl-SI`

- #8603 crowdin (merge `b982e1e9`): `origin/dev:lib/language.js:29,38` (was `sl_SL`/`sl-SL` at
  `origin/master:lib/language.js:37`). #8736: `%10`+ substitution order (`lib/language.js:107-117`).
  **Surfaces:** HTML; Alexa/Google Home phrasing; `speechCode` used by the page's speech synthesis.


---

# Websocket, alarm socket, shared-read permission, readable notice (C14-detail, C31-detail, C37–C42)

## Part intro: Part: websocket, alarm socket, shared-read permission, readable warning

Every claim here is **read-derived**: it comes from the source at the refs named, and nothing was run.
Refs: `origin/master` 92d08342 (= 15.0.8), `origin/dev` ddd9b600, #8754 head ef3404fd, #8758 head 6d120fa2
(branched from dev at 1f9a9d10).
Mechanism, not recipe: the socket defects are live on 15.0.8. This part describes the contract after
the fix. It does not describe how to use the old behaviour.

---

## C37 — `loadRetro` on the main namespace now checks read permission (#8744)

- **PR / merge:** #8744, a9acd313. **Surface:** S6. **Status:** merged (in dev).
- **Messages involved:** client→server `loadRetro(opts, ack)`; server→client `retroUpdate { devicestatus: [...] }`
  and the ack callback `{ result: ... }`. `authorize`, `dataUpdate`, `dbAdd`/`dbUpdate`/`dbUpdateUnset`/`dbRemove`
  and `clients` are **unchanged** by this PR.
- **Before (15.0.8):** `origin/master:lib/server/websocket.js:315-320`. There was no permission check. Any
  connected socket, whether or not it had sent `authorize`, got the ack `{ result: 'success' }` followed by the
  `retroUpdate` event carrying `lastData.devicestatus`.
  - For comparison, `dataUpdate` was already gated. A socket joins the room `DataReceivers` only when
    `authorize` resolves `api:*:read` (`origin/master:lib/server/websocket.js:790-802`), and broadcasts go only to
    that room (`:150`).
- **After (dev):** `origin/dev:lib/server/websocket.js:326-352`.
  - `resolveReadAccess` uses the socket's stored `authorize` decision if there is one (its `.read`, which is
    `api:*:read`, `:119-140`).
  - A socket that never sent `authorize` is resolved with an empty credential. That gives the
    `AUTH_DEFAULT_ROLES` default roles, the same answer the REST API gives an anonymous caller.
  - Permitted: the ack `{ result: 'success' }`, then `retroUpdate`, as before.
  - Not permitted: the ack `{ result: 'Not permitted' }`. **No `retroUpdate` is emitted.** The socket is **not**
    disconnected, and no error event is sent.
- **What a client observes:**
  - `AUTH_DEFAULT_ROLES=readable` (the default): no change for an anonymous socket or for one that authorized.
  - `AUTH_DEFAULT_ROLES=denied`:
    - A socket that did not `authorize`, or that authorized with credentials lacking `api:*:read`, now gets the
      ack `result: 'Not permitted'` and no retro devicestatus.
    - A client that ignores the ack and waits for `retroUpdate` waits for ever. Retro devicestatus (loop and
      pump pills history on the chart) stays empty.
  - Timing: on dev the anonymous resolve also passes through the failed-login delay for the socket's address
    (`origin/dev:lib/authorization/index.js:155-159`). After recent failed logins from the same address, both
    the ack and `retroUpdate` arrive late. #8754 removes that wait for requests that carry no credential (C41).
- **Search hints:** `loadRetro`, `retroUpdate`, `'Not permitted'`, `result`, socket.io `emit('loadRetro'`,
  `on('retroUpdate'`, `DataReceivers`.

## C38 — Alarm namespace `/alarm`: alarms are delivered only to sockets with read permission (#8745)

- **PR / merge:** #8745, 2b22c0ce. **Surface:** S6 (also S14). **Status:** merged.
- **Messages involved:** namespace `/alarm`:
  - client→server: `subscribe(message, callback)`, where `message` is `{accessToken}` for a native client or
    `{secret, jwtToken}` for a web client; also `ack(level, group, silenceTime)`.
  - server→client: `alarm`, `urgent_alarm`, `clear_alarm`, `announcement`, `notification`.
- **Before (15.0.8):**
  - `origin/master:lib/api3/alarmSocket.js:178-195`. Every notification was sent with `self.namespace.emit`, to
    **every socket connected to `/alarm`**, whether or not it had subscribed and whether or not its subscribe
    succeeded. The subscribe callback's result had no effect on delivery.
- **After (dev):**
  - Notifications go only to room `AlarmReceivers`: `origin/dev:lib/api3/alarmSocket.js:29` and `:251-268`.
  - Room membership is `applyReadEntitlement` (`:45-55`). A socket is in the room when its resolved permissions
    include `api:*:read`, and is taken out when they do not.
  - **At connect** (`:109-113`), the socket is resolved with no credential, which gives the default roles. It is
    admitted when those roles include `api:*:read`. This admission is skipped if a `subscribe` has already
    arrived (`hasSubscribed`, `:73`, `:80`).
  - **On a successful `subscribe`**, whether native `accessToken` (`:146`) or web `secret`/`jwtToken` (`:204`),
    membership is re-evaluated from the resolved permissions. A valid token's permissions always include the
    default roles (`origin/dev:lib/authorization/index.js:234`, `:204`).
  - **On a failed `subscribe`**, the callback is `{ success: false, message: <SOCKET_MISSING_OR_BAD_ACCESS_TOKEN> }`,
    unchanged. Room membership is **not changed**: a socket already admitted at connect stays in the room.
- **Callback shapes (unchanged):**
  - Native success: `{ success: true, message: 'Subscribed for alarms' }`, with no permission fields
    (`:161`).
  - Web success: `{ success: true, message: 'Subscribed for alarms', read, ack }` (`:230`).
- **What a client observes:**
  - `readable` default: every socket is admitted at connect, so alarms arrive as before, including for clients
    that never send `subscribe`. A valid token also carries `readable`, so it stays in the room.
  - `denied`:
    - A socket that never subscribes, or whose subscribe fails, **no longer receives any `alarm`,
      `urgent_alarm`, `clear_alarm`, `announcement` or `notification` events**. Nothing tells it so: no error
      event and no disconnect.
    - A native client whose token lacks `api:*:read` gets `success: true` from subscribe but **receives no
      alarms**. The callback does not report `read`.
  - Timing (dev only): the connect-time admission waits on the failed-login delay for that address. The PR body
    for #8745 names this as a known cost of 5 s per recent failure, cumulative. On a throttled address, a
    `subscribe` that arrives while that wait is pending sets `hasSubscribed`. If that subscribe then fails, the
    socket is never admitted, even on `readable`. On an address that is not throttled, the admission runs
    before any message is handled, because `resolve` does not await when there is no delay
    (`origin/dev:lib/authorization/index.js:155-169`). Under #8754 the anonymous path never waits (C41).
  - Web client (in-repo browser code): `origin/dev:lib/client/hashauth.js:414-421` now calls
    `client.subscribeForAlarms()` (`origin/dev:lib/client/index.js:1149-1176`) whenever socket auth is updated.
    A viewer who logs in within the page is therefore re-admitted without reconnecting.
    - Side effect: each subscribe registers another server-side `ack` listener on the same socket
      (`origin/dev:lib/api3/alarmSocket.js:152`, `:210`). This accumulation already happened before, but the
      re-subscribe now happens on every in-page auth update. One `ack` is then processed once per listener, each
      with the permission captured at its own subscribe.
- **Search hints:** `/alarm`, `io('/alarm'` / `socket.io` namespace `alarm`, `subscribe`, `accessToken`,
  `jwtToken`, `urgent_alarm`, `clear_alarm`, `announcement`, `notification`, `Subscribed for alarms`,
  `AlarmReceivers`.

## C39 — Alarm `ack` over the socket requires `notifications:*:ack` on the native-token path (#8745)

- **PR / merge:** #8745, 2b22c0ce (second commit). **Surface:** S6, S14. **Status:** merged.
- **Before (15.0.8):**
  - Native path (`subscribe` with `accessToken`): `origin/master:lib/api3/alarmSocket.js:81-86`. Any **valid**
    access token, whatever its roles, got an `ack` handler that called `ctx.notifications.ack(...)`
    **unconditionally**.
  - Web path (`secret`/`jwtToken`): already gated on `notifications:*:ack` (`origin/master:lib/api3/alarmSocket.js:131-137`).
- **After (dev):**
  - Native path: `origin/dev:lib/api3/alarmSocket.js:148-159`. `mayAck = checkMultiple('notifications:*:ack', ...)`.
    Without it, the ack is dropped and logged server-side only. **There is no callback and no event to the
    client.**
  - Web path: unchanged (`:203-222`).
- **Permission name:** `notifications:*:ack` both before and after. The change is that the native path now
  checks it.
  - Of the built-in roles, only `admin` (`*`) carries it. `readable` is `*:*:read` and does not
    (`origin/dev:lib/authorization/storage.js:139-145`).
- **HTTP `GET /api/v1/notifications/ack`:** unchanged. It is gated by `isPermitted('notifications:*:ack')` on
  both refs (`origin/dev:lib/api/notifications-api.js:24`, with no diff master..dev and none in #8754).
- **What a client observes:**
  - Follower or caregiver apps that subscribe with an access token whose role is `readable` (or any custom role
    without `notifications:*:ack`) and silence alarms over `/alarm` `ack` now silence **only locally**.
  - The server does not snooze, so the alarm re-fires to every viewer after the next check. The app gets no
    error.
  - This applies on **every** `AUTH_DEFAULT_ROLES` setting, including the `readable` default.
- **Search hints:** `emit('ack'`, `ack`, `silenceTime`, `level`, `group`, `accessToken`, `notifications:*:ack`,
  `/api/v1/notifications/ack`.

## C14-detail — `/api/v1/count/:storage/where` and `/api/v1/slice/:storage/...` check the selected collection's read permission (#8751)

- **PR / merge:** #8751, 4011193e. **Surface:** S4, S5. **Status:** merged.
- **These are the "two shared read addresses"** in release-note security item 4 and the #8751 body.
  - `GET /api/v1/count/:storage/where`: `origin/master:lib/api/entries/index.js:760` → `origin/dev:lib/api/entries/index.js:776`.
  - `GET /api/v1/slice/:storage/:field/:type?/:prefix?/:regex?`: `origin/master:…:773` → `origin/dev:…:789`.
  - `/times/…` also runs `prep_storage`, but it has no `:storage` parameter, so it always uses entries and is
    unaffected. `/echo/:echo/…` returns only the built query, not records, and is not gated.
- **Before (15.0.8):**
  - `prep_storage` (`origin/master:lib/api/entries/index.js:721-728`) selected the `treatments` or
    `devicestatus` storage with no extra check.
  - The only check on these routes was the router-wide `api:entries:read` (`origin/master:lib/api/entries/index.js:54`).
- **After (dev):**
  - For `:storage` = `treatments` or `devicestatus`, the route also requires `api:<storage>:read`
    (`origin/dev:lib/api/entries/index.js:734-744`). This runs before the query, the cache or MongoDB.
  - `entries`, and any unknown storage name (which falls back to entries), are unchanged.
- **Failure response:** HTTP **401**, JSON `{ "status": 401, "message": "Unauthorized", "description": "Invalid/Missing" }`
  (`origin/dev:lib/authorization/index.js:267`, `lib/middleware/send-json-status.js:4-12`).
- **What a client observes:**
  - `readable` default: unchanged, because `*:*:read` covers everything.
  - A token or role with `api:entries:read` but not `api:treatments:read` (or not `api:devicestatus:read`),
    on a site with anonymous read turned off: `count/treatments/where`, `count/devicestatus/where`,
    `slice/treatments/…` and `slice/devicestatus/…` go from 200 with data to 401.
  - A token with `api:treatments:read` but without `api:entries:read` is still refused, as before, by the
    router-wide check.
- **Search hints:** `count/treatments/where`, `count/devicestatus/where`, `/api/v1/count/`, `/api/v1/slice/`,
  `slice/treatments`, `slice/devicestatus`.

## C40 — Alarm-socket logging no longer prints credentials (#8751)

- **PR / merge:** #8751, 4011193e. **Surface:** none client-visible; operator log only (S14 at most).
  **Status:** merged.
- **Before:** the three failure log lines printed the access token, the JWT and the whole subscribe message
  (`origin/master:lib/api3/alarmSocket.js:74`, plus the jwtToken and message lines in the same function).
- **After:** fixed strings. `origin/dev:lib/api3/alarmSocket.js:139` prints "Authorization failed for access
  token", `:196` prints "... for web credentials", and `:239` prints "...: missing credentials".
- **Client observation:** none. Callback shapes are unchanged.
- **Search hints:** n/a (log text).

## C41 — #8754 (open) deltas on the socket files: client address and the failed-login delay

- **PR:** #8754, ef3404fd. **Surface:** S5, S6. **Status:** open PR.
- **Socket file delta:**
  - `git diff origin/dev ef3404fd -- lib/server/websocket.js lib/api3/alarmSocket.js lib/api3/storageSocket.js`
    only replaces each file's local `forwarded-for` `getRemoteIP` with `createClientIP(env.trustProxy)`
    (`ef3404fd:lib/server/client-ip.js:79-82`).
  - With `TRUST_PROXY` unset, it makes the same `forwarded-for` call as dev (`ef3404fd:lib/server/client-ip.js:65-67`).
  - With `TRUST_PROXY` set, the address comes from `proxy-addr` and the socket peer
    (`ef3404fd:lib/server/client-ip.js:68-76`). That address is used as the throttle key.
- **What the client sees differently (through `authorization.resolve`):**
  - The wait now happens only on a **failed** credential, on the way out (`ef3404fd:lib/authorization/index.js:205-215`).
  - A request with no credential is never delayed (`:161-165`).
  - A request with a good credential is never delayed (`:169-203`).
- **On sockets, this means:**
  - `authorize` with good credentials is no longer held behind other clients' failures from the same address.
  - The anonymous `loadRetro` resolve (C37) and the connect-time `/alarm` admission (C38) no longer wait, so the
    dev-only race in C38 disappears.
  - A failed `authorize` still ends in `socket.disconnect()` (`origin/dev:lib/server/websocket.js:810-813`), now
    after the delay.
- **Search hints:** `X-Forwarded-For`, `authorize`, reconnect/backoff logic after disconnect.
- The rest of #8754 (HTTP throttling, TRUST_PROXY, token storage) is covered elsewhere in the inventory.

## C42 — #8758 (open) delta on the main-namespace websocket: `_id` forms for `dbAdd`, `dbUpdate`, `dbUpdateUnset`, `dbRemove`

- **PR:** #8758, 6d120fa2 (`git diff 1f9a9d10 6d120fa2 -- lib/server/websocket.js`). **Surface:** S6, S7.
  **Status:** open PR.
- **Before (dev, the same as master here):**
  - `safeObjectID` turns a 24-hex `_id` into an ObjectId and leaves any other value as it is
    (`origin/dev:lib/server/websocket.js:13-25`).
  - `dbUpdate`, `dbUpdateUnset` and `dbRemove` matched exactly **one** stored form, the ObjectId.
  - `dbAdd` stored the client's `_id` exactly as sent. A 24-hex string stayed a **string**.
  - The result: a record added over the socket with its own 24-hex `_id` could not then be edited or removed
    over the socket, and re-sending it added a second copy. This is the commit message of 12c01268.
- **After (#8758):**
  - `idMatch` (`6d120fa2:lib/server/websocket.js:14-25`):
    - A 24-hex `_id`, in any letter case, or an ObjectId matches the ObjectId, the lower-case hex string and
      the string exactly as given (`6d120fa2:lib/server/object-id-forms.js`, `idForms`).
    - `dbUpdate`, `dbUpdateUnset` and `dbRemove` then apply to **every** match (`updateMany` / `deleteMany`).
    - Any other `_id`, such as a UUID or a custom string, matches exactly as given, one record.
  - `dbAdd` → `storeIdAsObjectId` (`6d120fa2:lib/server/websocket.js:547-569`): a 24-hex `_id` is stored as an
    ObjectId, unless the same id is already stored as a string, in which case that stored value is reused and
    the insert collides as a re-send always has.
- **Reply shapes are unchanged:**
  - `dbAdd` replies with an array of stored documents; `_id` serialises as the 24-hex string.
  - `dbAdd` replies `[]` on an internal error. The new pre-insert lookup failing also gives `[]`.
  - `dbUpdate`, `dbUpdateUnset` and `dbRemove` reply `{ result: 'success' }` or `{ result: 'Unable to process …' }`.
  - `data-update` `count` for a remove can now be greater than 1 when both forms were stored.
- **What a client observes:** edits and removes over the socket by a 24-hex `_id` now take effect where they
  silently did nothing, and a re-sent `dbAdd` with the same 24-hex `_id` no longer creates a duplicate. A client
  that relied on a re-send creating a new record would see a duplicate-key refusal instead.
- **Search hints:** `dbAdd`, `dbUpdate`, `dbUpdateUnset`, `dbRemove`, `_id`, `collection`.

## C31-detail — "Nightscout readable by world" admin notice now also raised for role lists (#8746)

- **PR / merge:** #8746, 74fc6619. **Surface:** S14 (admin notifications). **Status:** merged.
- **Before:** the notice was raised only when the whole `AUTH_DEFAULT_ROLES` string equalled `'readable'`
  (`origin/master:lib/server/bootevent.js:149`). `TREATMENTS_AUTH=off` appends `' careportal'`, which made the
  string `'readable careportal'`, so no notice appeared.
- **After:** the setting is parsed as a list (`origin/dev:lib/authorization/defaultroles.js:12-21`, and
  `origin/dev:lib/server/bootevent.js:21-39`, `:182-185`).
  - Any list containing `readable` gets a notice.
  - A list containing both `readable` and `careportal` gets the new title "Nightscout readable by world and open
    to treatment entry".
  - `lib/authorization/index.js:23` uses the same parser. The resulting default-role behaviour is identical:
    same split regex.
- **What a client observes:**
  - `GET /api/v1/adminnotifies` (`origin/dev:lib/api/adminnotifiesapi.js:9-28`) returns one more persistent
    entry to an admin, and one more in `notifyCount` to anyone.
  - This happens on sites with `TREATMENTS_AUTH=off`, and on sites whose `AUTH_DEFAULT_ROLES` lists `readable`
    together with any other role.
  - There is no change to access.
- **Search hints:** `adminnotifies`, `notifyCount`, `readable by world`.

---

## Prose vs code mismatches (release notes security items 1, 2, 4, 5, 8; PR bodies)

1. **Item 1 overstates the scope.** It says the live-update connection "now checks a visitor's access … before
   sending live information, alarms or notifications".
   - `dataUpdate` ("live information") was **already** gated on 15.0.8 (`origin/master:lib/server/websocket.js:790-802`).
   - The fix covers two things. The first is `loadRetro` / `retroUpdate` (retro devicestatus only, C37). The
     second is the `/alarm` namespace (`alarm`/`urgent_alarm`/`clear_alarm`/`announcement`/`notification`, C38).
   - That is accurate as a result, but an operator could read it as "live glucose was leaking". It was the retro
     devicestatus and alarms that leaked.
   - The "nothing changes on `readable`" clause is true for C37 and C38 **on an address that is not throttled**.
     On dev without #8754 (C38 timing), the #8745 PR body's known cost applies: alarms delayed after failed
     logins from the same address.
2. **Item 2 ("silencing alarms … now requires the permission meant for it") is true but does not say who is
   affected.**
   - HTTP `/api/v1/notifications/ack` and the web client's socket path were already gated and are unchanged.
   - Only the **native `accessToken`** subscribe path changed (C39).
   - The refusal is **silent**: no callback, no event.
   - It applies on the `readable` default too.
   - A follower app using a `readable` token will appear to silence an alarm while the server keeps it active.
   - The notes do not say this, and the "nothing changes on the standard setting" framing of item 1 does not
     cover item 2.
3. **Item 4 matches the code** once the two addresses are named: `GET /api/v1/count/:storage/where` and
   `GET /api/v1/slice/:storage/…`, for `storage` ∈ {treatments, devicestatus}, returning 401 (C14-detail).
   - Neither the release notes nor the #8751 body names them.
   - `/times/` and `/echo/` are not affected.
4. **Item 5 matches the code** (C40).
5. **Item 8 is narrower than the code.**
   - The notes describe only `TREATMENTS_AUTH=off`.
   - The code also warns for **any** `AUTH_DEFAULT_ROLES` list that contains `readable` plus another role
     (e.g. `readable devicestatus-upload`). Those lists got no notice on 15.0.8.
   - It uses the "open to treatment entry" wording whenever `careportal` is present with `readable`, including
     when set directly rather than through `TREATMENTS_AUTH=off`. The #8746 body does say this.
6. **#8745 PR body:** it says "connected clients receive alarms exactly as before" on the default install. That
   is true for connect-time admission.
   - It omits C39's native-token ack change on the default install.
   - It omits the C38 race on a throttled address, where a failed `subscribe` handled while the connect-time
     admission is still waiting leaves the socket out of the room even on `readable`.

## Could not settle

- How native clients (follower apps) actually use `/alarm` `subscribe`/`ack`, and with which role, is for the
  client join step to answer.
- Whether duplicate `ack` listeners (C38 side effect) cause a visible effect depends on
  `ctx.notifications.ack` being idempotent. This was not traced.


---

# Open PR #8754 — auth hardening and stored subject/role fields (C43–C48)

## Part intro: Part: #8754 (bf2/auth-hardening) and the subject/role stored-field restriction

Refs analysed (cgm-remote-monitor-official, read-only): `origin/master` 92d08342 (= 15.0.8),
`origin/dev` ddd9b600 (2026-09-23), PR #8754 head `ef3404fd` (2026-09-23, OPEN, head sha confirmed
with `gh pr view 8754` read-only). Every claim below is **read-derived**: nothing was run.

**Headline for the join step: every item in this file is in the open PR #8754 only. None of it is
on `origin/dev`.** `lib/authorization/storage.js` on dev differs from master only by the `count`
change (`origin/dev:lib/authorization/storage.js:9,79`), `endpoints.js`, `delaylist.js`,
`client-ip.js` and `app.js:52` are identical on master and dev. So the release-notes items
"Security fixes 6 and 7", "The new TRUST_PROXY setting", "Corrections: Fields stored on users and
roles" and "Editing a user on the admin page keeps its notes and creation date" all describe an
unmerged PR, and — unlike #8758's section — carry **no `<!-- PENDING: #8754 merge -->` marker**
(`grep -n PENDING release-notes.md` finds only the connector and #8758 markers).

Where dev == master for a file, the anchor is given as `origin/master` and applies to dev at the
same line unless a dev line is also given.

---

## C43 — Subject and role documents: only owned fields are stored (allow-list)

- PR / commits: #8754 (open), from `bf/auth` merged at `fd393cb1` (commit `a8f75da5`, BF-17/BF-47).
- Surface: **S5** (subjects/roles via `/api/v2/authorization/{subjects,roles}`), also S7-like (`_id` on create).
- Status: **open-PR (#8754)**.

**Before (15.0.8 and dev):**
- `POST /api/v2/authorization/subjects` and `POST .../roles` call `create(collection)`, which adds
  `created_at` (ISO now) if absent and `insertOne(obj)` **the whole request body**:
  `origin/master:lib/authorization/storage.js:41-59` (dev `:42-60`). Any field the body carries is
  stored, including a client-supplied `_id` (stored as sent) and `accessToken`/`digest`.
  Response: `res.json(created)` = the request body + `created_at` + the driver-added `_id`
  (`origin/master:lib/authorization/endpoints.js:44-52`).
- `PUT .../subjects` and `PUT .../roles` call `save(collection)`: `_id` normalised by
  `normalizeRequiredObjectId`, `created_at` set to now **if the body lacks it**, then
  `replaceOne({_id}, obj, {upsert:true})` with **the whole body** (`origin/master:lib/authorization/storage.js:108-124`,
  dev `:106-122`). Response: the body as stored.
- Because `GET .../subjects` serves `accessToken` (`origin/master:lib/authorization/endpoints.js:40`,
  `pick(subject, ['_id','name','accessToken','roles'])`) and the admin UI sends the object back,
  a save stored the derived `accessToken` in plain text (BF-17).

**After (ef3404fd):**
- Stored fields: subjects `['name','roles','notes','created_at']`, roles
  `['name','permissions','notes','created_at']` (`ef3404fd:lib/authorization/storage.js:51-52`);
  `ownedFields()` copies only those (`:59-66`). `create` inserts `doc`, not the body
  (`:110`), and returns `doc` (`:120`). `save` builds `doc` from owned fields plus the normalised
  `_id` (`:171-183`).
- Consequences a client can observe:
  - Any other field (tool metadata, `accessToken`, `accessTokenDigest`, `digest`, anything custom)
    is **not stored** on create, and is **removed** from the stored document on the next PUT
    (whole-document `replaceOne`).
  - **POST create ignores a client-supplied `_id`**: `_id` is not an owned field, so `doc` has none
    and MongoDB generates one (`:100-110`). On 15.0.8 a tool could POST a subject with its own `_id`.
    Not covered by a test in `tests/authsubjects.test.js` (read-derived). PUT with a new 24-hex
    `_id` still upserts under that `_id` (unchanged, `:171,181`).
  - POST/PUT responses now echo only the stored fields + `_id` (+ `created_at`), not the whole
    request body. Neither side returns the derived `accessToken` in the POST/PUT response; a tool
    must read it from `GET .../subjects` on both.
  - On load, `reload()` deletes any stored `accessToken`/`accessTokenDigest`/`digest` before
    deriving them (`ef3404fd:lib/authorization/storage.js:57,250-252`), so a stored copy can no
    longer supply the token; with no enclave key (`API_SECRET` unset) a stored token is no longer
    surfaced at all (test "drops a stored token when there is no enclave key",
    `ef3404fd:tests/authsubjects.test.js:322`).
- Unchanged: the tokens themselves (derived from `_id` + `API_SECRET` + name,
  `ef3404fd:lib/authorization/storage.js:254-258`) — existing tokens keep working.

**What a client relying on the old behaviour sees:** extra fields it stored on a subject/role are
missing on the next `GET`; a POST that set its own `_id` gets a different `_id` back (and so a
different token than it may have pre-computed); a response body that no longer echoes its extra
fields. HTTP status codes are unchanged (200; 500 "Mongo Error" on DB failure).

**Search hints:** `authorization/subjects`, `authorization/roles`, `/api/v2/authorization`,
`createSubject`, `saveSubject`, `auth_subjects`, `auth_roles`, `accessTokenDigest`, `notes`,
`created_at` on a subject body, a POST body with `_id` to subjects, `nightscout-connect-reader`
(nightscout-connect creates a subject on the source site).

## C44 — Subject/role save keeps `notes` and `created_at` when the request omits them; GET /subjects serves `notes`

- PR / commit: #8754 (open), commit `7103f657` (`bf2/subject-edit-keeps-fields`, BF-47 residual).
- Surface: **S5**. Status: **open-PR (#8754)**.

**Before (15.0.8 and dev):** `PUT` replaced the whole document with the body; a body without
`created_at` got `created_at = now` (`origin/master:lib/authorization/storage.js:117-118`); a body
without `notes` stored no notes. `GET .../subjects` did not serve `notes`
(`origin/master:lib/authorization/endpoints.js:40`), so the admin dialog sent `notes` empty and
wiped it.

**After:** `keepStoredFields()` (`ef3404fd:lib/authorization/storage.js:81-98`), called from
`save` (`:180`): if the body has **no own `notes` property**, the stored `notes` is copied in; if
`created_at` is **falsy**, the stored `created_at` is copied in (then `now` only if nothing is
stored, `:181-183`). `notes: ''` sent explicitly clears. `roles`/`permissions` are **never**
filled in from storage (a body without `roles` stores a subject with no roles — unchanged, and
deliberate because form encoding drops empty arrays). `GET .../subjects` now returns
`['_id','name','accessToken','roles','notes']` (`ef3404fd:lib/authorization/endpoints.js:44`).
`created_at` is still not served by `GET .../subjects` (PR body lists this as a residual).
`GET .../roles` returns the whole in-memory role (unchanged, `:78-80`).

**What a client observes:** `GET .../subjects` items gain a `notes` key; a PUT without
`created_at` keeps the original creation date instead of resetting it; a PUT without `notes` no
longer clears them. A tool that relied on "PUT without notes clears notes" must now send `notes: ''`.

**Search hints:** as C43, plus `notes` in a subjects PUT body, parsing of the `/subjects` list.

## C45 — Failed-authentication delay: only failed attempts wait; keyed on address AND credential; bounded, swept

- PR / commits: #8754 (open), from `bf/throttle` merged at `b4d1a0da` (commit `435419ce`, BF-30).
- Surface: **S5** (all auth), **S6** (socket `authorize`, `/alarm` `subscribe`), **S13** (API v3 JWT), **S15** (latency).
- Status: **open-PR (#8754)**.

**Before (15.0.8 and dev):**
- `resolve()` looks up the delay for `data.ip` and **sleeps before doing anything else, for every
  request that reaches resolve**, including requests with **no credential** and requests with the
  **correct** credential (`origin/master:lib/authorization/index.js:155-159`). Then a failure calls
  `addFailedRequest(ip)` (`:210`), a success `requestSucceeded(ip)` (`:174,203`).
- Delay list: plain object keyed by the IP string; each failure pushes the deadline by
  `authFailDelay` (default 5000 ms, `origin/dev:lib/settings.js:70`) from `max(entry, now)`
  (`origin/master:lib/authorization/delaylist.js:10-20`). Sweep is a single `setTimeout` at 30 s,
  so after the first 30 s nothing is ever removed and the list is unbounded (`:43-51`).
- Callers that reach `resolve()`: every `isPermitted` REST check (`origin/master:lib/authorization/index.js:253-260`),
  `resolveWithRequest` (verifyauth, adminnotifies), websocket `authorize`
  (`origin/dev:lib/server/websocket.js:119-123` via `verifyAuthorization`), `/alarm` namespace
  `subscribe` (`origin/dev:lib/api3/alarmSocket.js:193`) and the `/alarm` connect-time anonymous
  admission (`origin/dev:lib/api3/alarmSocket.js:108`, whose comment at `:98-106` says it awaits the
  delay on a throttled address), API v3 JWT auth (`origin/master:lib/api3/security.js:40`).
  NOT through resolve: `/storage` socket `subscribe` uses `resolveAccessToken` directly — never
  throttled, both sides (`ef3404fd:lib/api3/storageSocket.js` subscribe).
- Consequence: behind a shared proxy (one apparent IP), one client with a wrong secret made
  **every** client behind that IP wait up to 5 s+ per request, including anonymous page loads and
  correctly-authenticated uploaders.

**After (ef3404fd):**
- The delay is taken **only on the failure path**, after the credential has been checked and
  found wrong, before the 401 is sent (`ef3404fd:lib/authorization/index.js:209-215`). A request
  with no credential returns default roles immediately (`:158-167`); a request with a correct
  secret/token returns immediately and clears its keys (`:170,199`).
- Keys: `keysFor()` returns `addr:<salted sha256(ip)>` and, if a secret or token was sent,
  `cred:<salted sha256(credential)>` (`ef3404fd:lib/authorization/delaylist.js:170-180`, salt
  `:28`). The wait is the **max** over the keys (`:178-190`); a failure pushes each key's deadline
  by `authFailDelay` from `max(entry, now)` (`:168-176`). So the same wrong credential is delayed
  from any address, and any wrong credential is delayed from the same address.
- Bounds: 10000 entries per namespace, oldest evicted first (`:15-16,40-47`); sweep every 30 s by
  `setInterval`, unref'd, dropping entries more than 60 s past expiry (`:10-11,198-205`).
- The address key is the address resolved through `TRUST_PROXY` (C46). With `TRUST_PROXY` unset it
  is the same header-derived address as today, so a caller varying both address header and
  credential is still never delayed (PR's own table; boot warning, C47).

**What a client observes:**
- A correctly-authenticated client (uploader, follower, websocket `authorize` with the right
  secret, API v3 with a valid JWT) **never waits** any more, even from an address that just
  failed. Anonymous requests never wait. (Before: they could wait ~5 s per queued failure.)
- A client with a **wrong** secret/token: first failure answered at once (401 / socket
  disconnect); each further failure within the window (same address or same credential) is
  answered only after the pending deadline — about `authFailDelay` (5 s default) after the
  previous failure. Status codes and bodies unchanged (REST 401 `Unauthorized`/`Invalid/Missing`,
  `ef3404fd:lib/authorization/index.js:~276`; websocket `authorize` failure → `socket.disconnect()`,
  `ef3404fd:lib/server/websocket.js:805-812`; API v3 401 `HTTP_401_BAD_TOKEN`,
  `ef3404fd:lib/api3/security.js:34-38`). New vs before: a misconfigured uploader is now delayed on
  its bad credential even after its IP changes (phone switching networks).
- `/alarm` connect-time admission on a throttled address is no longer deferred (dev comment at
  `origin/dev:lib/api3/alarmSocket.js:98-106` no longer holds on ef3404fd, where the same comment is
  retained verbatim at `ef3404fd:lib/api3/alarmSocket.js:94-102` — stale comment, code is fine).
- The "Failed authentication" admin notification and its IP text are unchanged except that the IP
  is now resolved through `TRUST_PROXY`.

**Search hints:** handling of 401 with retry/backoff; request timeouts shorter than ~5–10 s on
auth'd calls (`timeout`, `connectTimeout`, `readTimeout`); `api-secret` header; `token=`; socket
`authorize` callback / `disconnect` handling; `/api/v2/authorization/request/`; `verifyauth`.

## C46 — `TRUST_PROXY`: new setting controlling client-address and https trust

- PR / commits: #8754 (open): `712c8854`, `708bbd4b`, `8b975b41`, `81623f9b` (hops/`true`),
  `22953b77`/`0a74ef4e` (sub-app lines removed).
- Surface: **S5** (anything that sets `X-Forwarded-For`/`X-Forwarded-Proto`), whole-site availability.
- Status: **open-PR (#8754)**.

**Before (15.0.8 and dev):** `app.enable('trust proxy')` — Express trusts every hop
(`origin/master:lib/server/app.js:52`). The https redirect passes if
`X-Forwarded-Proto === 'https'` exactly, **or** `req.secure` (`:107`); otherwise 307 to
`https://<Host><url>`. Client IP everywhere (six consumers) comes from the `forwarded-for` package
reading forwarding headers from any peer (`origin/master:lib/authorization/index.js:9-12`,
`lib/api/status.js:24-27`, `lib/api3/security.js:10-13`, `lib/api3/alarmSocket.js:6-9`,
`lib/api3/storageSocket.js:6-9`, `lib/server/websocket.js:8-11`).

**After:** `env.trustProxy = readENV('TRUST_PROXY', '')` (`ef3404fd:lib/server/env.js:43`; also
`CUSTOMCONNSTR_TRUST_PROXY` and lower-case name via `readENV`, `:202-217`; value is the trimmed
string, no numeric coercion). `compileTrust()` (`ef3404fd:lib/server/client-ip.js:28-45`), grammar
in evaluation order:

| value (after trim) | result | client address | `req.secure` / https redirect |
|---|---|---|---|
| unset / empty | `compatibilityTrust` (`:10,31`) | `forwarded-for` exactly as dev (`:66-68`) | trusts `X-Forwarded-Proto` from any peer; PR states identical to dev's `=== 'https' || req.secure` for all values it measured (read-derived: Express 4 `req.protocol` takes the first comma element, which agrees) |
| `false` (**lower-case only**, `value === 'false'`, `:32`) | trust nothing | socket peer | only a direct TLS connection is secure → behind a TLS-terminating proxy **every request is 307-redirected to https, in a loop** |
| `true` (any case, `:34`) | trust every hop | left-most `X-Forwarded-For` via `proxy-addr` | trusts `X-Forwarded-Proto` |
| `^[1-9][0-9]*$` safe integer (`:35`) | trust n closest hops | the address the n-th proxy saw | trusts `X-Forwarded-Proto` if the peer is hop 0 (always, n ≥ 1) |
| comma list of IPs/CIDRs (`:36-45`) | `proxy-addr.compile(list)` | first untrusted address from the right | trusts `X-Forwarded-Proto` only if the connecting peer is in the list; otherwise redirect loop as for `false` |
| any entry `loopback`/`linklocal`/`uniquelocal` | **throws** `TRUST_PROXY must be … ; the subnet aliases … are not accepted` (`:39-41`) | — | — |
| anything else (`0`, `FALSE`, `False`, `off`, a hostname, `1,10.0.0.1`, a port) | **throws** `TRUST_PROXY must be false, true, a whole number of proxy hops (1 or more), or a comma-separated list …` (`:24-25,42-44`) | — | — |

- Where applied: parent app `app.set('trust proxy', compileTrust(...))` (`ef3404fd:lib/server/app.js:52`),
  inherited by the mounted v1/v2/v3 sub-apps (their own lines removed in `22953b77`/`0a74ef4e`);
  redirect now `if (req.secure)` only (`:107`); the six IP consumers use `createClientIP(env.trustProxy)`
  (`ef3404fd:lib/authorization/index.js:10`, `lib/api/status.js:5`, `lib/api3/alarmSocket.js:10`,
  `lib/api3/storageSocket.js:10`, `lib/server/websocket.js:23`) or Express's compiled fn
  (`ef3404fd:lib/api3/security.js:34`). With a boundary set, a forwarded value that is not a bare IP
  (e.g. with a port) falls back to the socket peer (`client-ip.js:69-73`).
- **Startup failure mode for a refused value (read-derived):** the first `compileTrust` call is in
  `delaylist` init during `setupAuthorization` (`ef3404fd:lib/server/bootevent.js:227` →
  `lib/authorization/delaylist.js:230`), and again in `app.js:52`. Neither is caught (`bootevent`
  0.0.1 has no try/catch, `node_modules/bootevent/index.js`), so the process **exits with an
  uncaught Error**; it does not render the "Nightscout is having trouble" boot-error page. Not run.
- No change to `Host`/`X-Forwarded-Host` handling in Nightscout code: nothing under `lib/` reads
  `req.hostname`/`req.protocol`/`req.ip` (grep on ef3404fd finds only `app.js:107` `req.secure`);
  the redirect target uses the raw `Host` header on both sides.

**What a client observes:** with `TRUST_PROXY` unset, nothing (by construction). Once an operator
sets it: clients that spoof or add `X-Forwarded-For` no longer choose their throttle key; a wrong
`false`/list behind a TLS proxy makes **every client** (browsers, uploaders, followers) see an
endless 307 redirect to the same https URL — most HTTP libraries report "too many redirects";
a refused value means the site does not start at all.

**Search hints:** client code that sets `X-Forwarded-For`, `X-Real-IP`, `Forwarded`,
`X-Forwarded-Proto`; redirect-follow limits (`maxRedirects`, `followRedirects`, `HttpURLConnection`
redirect handling); for operator tooling / deploy templates: `TRUST_PROXY`, `CUSTOMCONNSTR_TRUST_PROXY`,
`INSECURE_USE_HTTP`.

## C47 — New startup log lines about the throttle

- PR / commit: #8754 (open), `e701900a`. Surface: operator log only (no client surface). Status: open-PR.
- Before: none. After: `console.warn` "SECURITY: failed-authentication throttling … TRUST_PROXY is
  not set … does NOT protect against guessing passwords or tokens …" when unset
  (`ef3404fd:lib/authorization/delaylist.js:80-89`); a different `SECURITY:` warning when
  `TRUST_PROXY=true` (`:69-78`); otherwise one `console.info` naming the configured value or hop
  count (`:91-100`), logged at `:230-231`. Also removed: the `console.log('Loading', opts)` printed
  on every read of the auth collections (`origin/dev:lib/authorization/storage.js:82`, commit `ce82f0cd`).
- Search hints: log scrapers matching `SECURITY:` or `Loading`.

## C48 — `/api/v1/status` and API v3 auth: address resolution only

- PR: #8754 (open). Surface: **S4** (`/api/v1/status`), **S13**. Status: open-PR.
- `status.js` swaps its local `forwarded-for` helper for `createClientIP(env.trustProxy)`
  (`origin/dev:lib/api/status.js:24-27` → `ef3404fd:lib/api/status.js:5`). The only use is
  `authorized: ctx.authorization.authorize(authToken, getRemoteIP(req))` (`ef3404fd:lib/api/status.js:35`),
  and `authorize` takes a single argument (`ef3404fd:lib/authorization/index.js:284`), so the IP is
  ignored. **No change to the `/api/v1/status` body.** `verifyauth.js` is not changed by #8754.
- API v3 `security.js` resolves the JWT through `resolve()` with the `TRUST_PROXY`-resolved address
  (`ef3404fd:lib/api3/security.js:34`); response codes unchanged; timing changes as in C45.

---

## Prose vs code mismatches

1. **Release notes present #8754 content as in the release with no merge marker.** Security items 6
   and 7, the whole "The new `TRUST_PROXY` setting" section, "Corrections: Fields stored on users
   and roles", "Editing a user on the admin page keeps its notes and creation date", "Access tokens
   stored in plain text", the Known-issues `TRUST_PROXY` line, and "What you must do" items 4 and 9
   all depend on PR #8754, which is **open** (head `ef3404fd`); `origin/dev` ddd9b600 has none of it.
   The #8758 section carries `<!-- PENDING: #8758 merge -->`; the #8754 sections carry nothing.
2. **`TRUST_PROXY=false` is case-sensitive; `true` is not.** Code: `value === 'false'`
   (`ef3404fd:lib/server/client-ip.js:32`) vs `value.toLowerCase() === 'true'` (`:34`). `FALSE` or
   `False` is refused and the process does not start. The release-notes table writes `false`
   (correct literal) but says nothing about case; an operator typing `FALSE` gets a site that will
   not start.
3. **"Refused at startup" understates the failure.** Release notes: "Names like `loopback` are
   refused at startup, and a number of proxies cannot be combined with addresses." Code: the throw
   is uncaught during boot (C46), so the process exits instead of showing the boot-error page. Also
   refused and not mentioned: `0`, `off`, hostnames, any value with a port. (Read-derived; not run.)
4. **Corrections "Fields stored on users and roles" omits the `_id` effect.** The notes say "Any
   other field … is not kept … and is not stored when one is created." True, but `_id` is also not
   an owned field on **create**: a POST to `/api/v2/authorization/subjects` (or `/roles`) with its
   own `_id` now gets a server-generated `_id` (`ef3404fd:lib/authorization/storage.js:51-52,100-110`),
   hence a different access token from the one a tool may have derived. PUT-with-upsert still
   honours `_id`. Also unstated: POST/PUT responses no longer echo the request body.
5. **Local PR-body file `reports/phase0-pr-bodies/bf2-auth-hardening.md` is stale against code**
   (the **posted** PR body and `bf2-auth-hardening.withheld.md` are current):
   - "`true`, hop counts and names like `loopback` are rejected at startup" — code accepts `true`
     and hop counts since `81623f9b` (`client-ip.js:34-35`).
   - Its `TRUST_PROXY` table has no hop-count or `true` rows.
   - "That one line in `lib/api/index.js` … sets the v1 app's `trust proxy`" / "It is kept" —
     removed by `22953b77` (and the v3 line by `0a74ef4e`); `git grep -i 'trust.proxy' ef3404fd -- lib`
     finds only `app.js:52` and `api3/security.js:34`.
   - "No throttle code changes" under TRUST_PROXY is fine, but its test counts are at `29e6430e`,
     not the tip.
6. **Stale code comment on the PR head** (not a client effect): `ef3404fd:lib/api3/alarmSocket.js:94-102`
   still says the anonymous admission "does consult the failed-login delay list … and awaits it";
   on ef3404fd, a no-credential `resolve()` returns before any delay (`lib/authorization/index.js:158-167`).
7. Release-notes security item 7 ("Now only failed attempts wait, and the list of recent failures
   is cleared regularly and has a size limit") — **matches code** (C45). Not stated, and
   client-relevant: the delay is also keyed on the credential, so an uploader with a stale secret
   is delayed from every address it uses. Item 6 and "Access tokens stored in plain text" —
   **match code** (C43: tokens derived, stored copies ignored on load and removed on next save).
   "Editing a user … keeps its notes and creation date" — **matches code** (C44), including
   "clear the notes on purpose by emptying the notes box".

## Not settled

- Whether a refused `TRUST_PROXY` value crashes the process or is caught somewhere above
  `bootevent` (e.g. a process manager restart loop on Heroku/Docker) — read-derived only; the
  in-repo code has no catch.
- Exact Express 4.22.2 `req.protocol` source was not re-read from `node_modules`; the https
  equivalence for the unset case rests on the PR's measured claim plus Express 4's documented
  first-element behaviour.


---

# Open PR #8758 — `_id` contract incl. BF-99 (C49–C59)

## Part intro: `_id` handling — open PR #8758 (`bf/object-id-crud`), incl. BF-99 (profile `_id`)

All claims **read-derived** (source read; nothing run). Repo `externals/cgm-remote-monitor-official`.

- Before = `origin/master` `92d08342` (15.0.8). For every file #8758 touches, the `_id`-handling
  lines on `origin/master` and on the PR base `origin/dev@1f9a9d10` are identical (checked with
  `git diff origin/master 1f9a9d10 -- <file> | grep -iE '_id|objectid|hex|safeObjectID|isId'`:
  no hits). Master line numbers are quoted; `websocket.js` line numbers differ between master and
  dev because of #8744, not because of id handling.
- After = PR #8758 head `6d120fa2` (2026-09-23), based on `origin/dev@1f9a9d10` (#8750 merge).
- **Status: open-PR #8758.** Nothing in this file is on `origin/dev ddd9b600`.

## Scope check (what #8758 contains, what dev already has)

- **No profile `_id` change is on dev.** `origin/master..origin/dev` changes `lib/server/profile.js`
  only for `count` (#8738/#8748, `isZeroCount`, `parseCount`), not for `_id`.
- **BF-99 is folded into #8758.** `git log 1f9a9d10..6d120fa2` has 13 commits: the five of
  `bf/object-id-consistency` (`1f9db1fe` helper, `09566345` profile = BF-99, `80993afc`
  devicestatus/food/activity = BF-100, `5581c5e4` treatments/entries = BF-101, `597e2899` API v3
  string `_id`) and the eight of `bf/object-id-crud` (`4b41bcf8` … `6d120fa2`). The narrower
  branches `bf/profile-object-id` `9b8cc2f9`, `bf/object-id-other-collections` `2fac53f5` and
  `bf/api3-string-id` `7295bc8c` are superseded (PR body: they conflict with it; not to be landed).
  Register `docs/30-design/remedial/nightscout-backfix-register.md:174` agrees (BF-99 "fixed … on
  `bf/object-id-crud` `6d120fa2`, in review as PR #8758").
- **Interaction with later dev merges.** Of the files #8758 touches, dev after `1f9a9d10` changes
  only `lib/api/entries/index.js` (#8751: `prep_storage` adds `api:<coll>:read` for
  treatments/devicestatus on the shared read path, `origin/dev:lib/api/entries/index.js:737`) and
  `lib/server/profile.js` (#8748: `count=0` → `[]` in `list`). Neither touches `_id` code.
  `git merge-tree --write-tree origin/dev 6d120fa2` → clean (tree `d8724320`), no conflicts.

## The rule (new helper `lib/server/object-id-forms.js`, 6d120fa2)

- `isHexId(id)`: `typeof id === 'string' && /^[0-9a-fA-F]{24}$/` (`6d120fa2:lib/server/object-id-forms.js:42`).
  Same regex as master's copies in `objectid-validation.js:3`, `query.js:6`, `entries.js`,
  `treatments.js`, `api3 utils.js:3`; **different** from master's entries-route `ID_PATTERN = /^[a-f\d]{24}$/`
  (lower case only, `origin/master:lib/api/entries/index.js:12`).
- `toStoredId`: 24-hex string → `ObjectId`; anything else kept (`:47`).
- `idForms(id)`: `[ObjectId, lower-case hex, the string as given if different]` (`:55`). Throws on
  non-hex input (as `new ObjectId` does).
- `matchEitherForm(query, asked)`: only when the built query has `_id` **as a plain ObjectId
  equality** it is widened to `{_id: {$in: idForms(asked)}}` (`:73`). **Not** widened:
  `find[_id][$in][]=…`, `find[_id][$ne]` etc. (those still become ObjectIds only, via
  `lib/server/query.js` `updateIdQuery` traverse, `6d120fa2:lib/server/query.js:128`).
- `withStaleStringsRemoved(bulkOps, ids)` / `staleStringForms`: after an upsert by the ObjectId
  form, `deleteMany({_id: {$in: <string forms>}})` (`:96`).
- Stated limit (`:14-20`): a string `_id` stored in UPPER/mixed case is matched only when asked in
  the same spelling; the ObjectId form is matched in any case.

## Entries

### C49 — Entries POST re-send with an `_id` different from the stored reading's: HTTP 500 → 200
- PR #8758, commit `4b41bcf8`; surface **S7** (also S15); status **open-PR #8758**.
- Endpoint: `POST /api/v1/entries` (and `.json`), body item carries `_id` (24-hex) and the same
  `sysTime`/`dateString`/`date` + `type` as a stored reading whose `_id` differs (a 24-hex string
  stored by ≤15.0.6, or a different ObjectId).
- Before: upsert filter is `{sysTime, type}` (`origin/master:lib/server/entries.js:238-247`
  `upsertQueryFor`), update is `{ $set: doc }` including `_id`
  (`origin/master:lib/server/entries.js:136`); MongoDB refuses a change to immutable `_id`, the
  `bulkWrite` throws (`:146-150`), the batch (ordered) stops, response **HTTP 500 `Mongo Error`**
  (`origin/master:lib/api/entries/index.js:258`). Earlier items of the batch are stored.
- After: `$set` without `_id`, `$setOnInsert: {_id}` (`6d120fa2:lib/server/entries.js:134-141`);
  the stored reading is updated and keeps its own `_id`; **HTTP 200**.
- Client observes: a re-upload that used to fail (and, for a client that retries on 500, loop)
  now succeeds.
- Search hints: entries POST body builders that set `_id`; retry-on-500 logic around
  `api/v1/entries`; `"_id"` in sgv/mbg/cal JSON.

### C50 — Entries POST response `_id` for a reading that matched a stored one
- PR #8758, commit `18b09df7`; **S7**; **open-PR #8758**.
- Before: response item `_id` is set only from `bulkResult.upsertedIds`
  (`origin/master:lib/server/entries.js:154-157`), i.e. only for a newly inserted reading. A
  reading that matched a stored `sysTime`+`type` is echoed with the `_id` it was **sent** with
  (hex sent → the same id as an ObjectId, serialised lower-case) or with **no `_id` key** (none
  sent; the PR body says "answered `null`", which holds when the client sent `_id: null`, since
  `normalizeEntryId` keeps a `null`).
- After: one extra `find` over the matched `{sysTime,type}` filters; each matched item's `_id` is
  replaced by the **stored** reading's `_id` (`6d120fa2:lib/server/entries.js:156-178`, called at
  `:197-202`). If that read fails, the POST still answers 200 and items keep `_id` as sent.
- Client observes: the POST response can now name an `_id` **different from the one it sent**
  (the stored one), and names one where it previously named none.
- Search hints: code that reads `_id` from the `api/v1/entries` POST response and stores it
  (e.g. as a remote id / `nightscoutId` / `interfaceIDs`); code that asserts response `_id` ==
  sent `_id`.

### C51 — `GET` / `DELETE /api/v1/entries/<id>` accept upper-case hex
- PR #8758, commit `a612a26f`; **S7**; **open-PR #8758**.
- Before: `isId` = `/^[a-f\d]{24}$/` (`origin/master:lib/api/entries/index.js:12-16`). An
  upper/mixed-case 24-hex `<id>` is not an id, so it is treated as a **type name**:
  `GET` → `find[type]=<ID>` → `[]` (`:390-409`); `DELETE` → deletes records with that `type` →
  nothing deleted, 200 with a zero delete status (`:810-823`). Lower case worked.
- After: `isId` = `isHexId` (either case) (`6d120fa2:lib/api/entries/index.js:14`, used at `:392`,
  `:573`, `:820`); the id matches an ObjectId-stored reading in any case, and a string-stored
  reading in lower case or in the spelling asked.
- Client observes: upper-case ids now find/delete the reading.
- Search hints: `api/v1/entries/` + id path segment; `.uppercased()` / `toUpperCase()` on ids.

### C52 — Entries by id match a string-stored `_id` (≤15.0.6 records)
- PR #8758, commit `5581c5e4`; **S7**; **open-PR #8758**.
- Before: `getEntry` = `findOne({_id: new ObjectId(id)})` (`origin/master:lib/server/entries.js:179`);
  `find[_id]=<hex>` → ObjectId equality (`origin/master:lib/server/query.js:132`,
  `entries.js:183` `query_for`) → a reading stored with the 24-hex **string** `_id` (as ≤15.0.6
  stored it; confirmed `15.0.6:lib/server/treatments.js` upserts `obj` as given, and 15.0.6
  entries has no conversion) is not found; `DELETE /entries/<id>` deletes nothing.
- After: `getEntry` uses `{$in: idForms(id)}` (`6d120fa2:lib/server/entries.js:225`);
  `query_for` → `matchEitherForm` (`:240`); DELETE by id reaches both forms (`deleteMany`, `:50`).
- Client observes: `GET /entries/<id>` and `find[_id]=<id>` return a reading they returned `[]`
  / `[null]` for; `DELETE` now removes it.
- Search hints: `find[_id]`, `api/v1/entries/<id>`.

## Treatments

### C53 — Treatments POST/PUT by `_id` over a string-stored record leaves one record
- PR #8758, commit `5581c5e4`; **S7, S8**; **open-PR #8758**.
- Before: a 24-hex `_id` is converted to ObjectId (`origin/master:lib/server/treatments.js:394-408`
  `normalizeTreatmentId`) and the upsert filter is `{_id: ObjectId}` (priority identifier > `_id`
  > time+eventType); against a treatment stored by ≤15.0.6 with the **string** `_id` the filter
  misses, so `POST /api/v1/treatments` (bulk `replaceOne` upsert, `:27`, `:162`) and
  `PUT /api/v1/treatments` (`save`, `:292`, `:307`) **insert a second treatment** and keep the
  original. `DELETE /api/v1/treatments/<id>` (via `find[_id]`, `:257`, `:276`) misses the string
  original.
- After: after the upsert, `deleteMany({_id: {$in: <string forms>}})` (bulk:
  `6d120fa2:lib/server/treatments.js:75-90`; `upsert`: `:165-172`; `save`: `:315-321`; helper
  `staleFormsFor` `:368`) — only when the filter matched by `_id` (not by identifier or
  time+type). `query_for` → `matchEitherForm` (`:280`), so DELETE by id and `find[_id]` reach both
  forms.
- Response `_id`: unchanged (ObjectId, serialised lower-case hex), both sides.
- Client observes: an edit no longer duplicates the treatment; delete by id works on those
  records; an extra `data-update` is not emitted for the removed string copy (read-derived: the
  delete is a bare `deleteMany`).
- Search hints: `PUT api/v1/treatments`, POST-to-update with `_id`, `DELETE api/v1/treatments/`.

## Profile (BF-99), devicestatus, food, activity

### C54 — Profile POST with a 24-hex `_id` is stored as ObjectId; PUT/DELETE/`find[_id]` find it
- PR #8758, commit `09566345` (BF-99); **S7, S10**; **open-PR #8758**.
- Before: `create` = `insertMany(docs)` with `_id` as given → stored as the **string**
  (`origin/master:lib/server/profile.js:12-38`); `save` (`PUT /api/v1/profile/`) converts to
  ObjectId and upserts (`:60-79`) → **adds a second profile**, keeps the string one; `remove`
  (`DELETE /api/v1/profile/<id>`) = `deleteOne({_id: ObjectId})` (`:145-147`) → deletes nothing,
  still answers `{}`; `find[_id]=<hex>` on `/api/v1/profile(s)` → `[]` (`:116`).
- After: `create` converts a 24-hex `_id` to ObjectId unless that exact string is already stored
  (`6d120fa2:lib/server/profile.js:23-37`, applied at `:66-68`); `save` upserts by ObjectId then
  deletes the string forms of the submitted id (`:99-118`); `remove` = `deleteMany` over all forms
  (`:186-191`); `query_for` → `matchEitherForm` (`:156-160`).
- Route validation unchanged: non-hex string `_id` on POST/PUT/DELETE → 400 `Invalid _id format`
  (`6d120fa2:lib/api/profile/index.js:95-99`, `:123-126`, `:164-167`), same as master.
- Client observes: after one PUT, one profile remains (was two); DELETE by id removes it;
  `find[_id]` returns it. For a profile created with an upper-case hex `_id` the POST response
  `_id` is now lower-case (ObjectId serialisation) where it used to echo the sent spelling.
- Search hints: `api/v1/profile` POST/PUT with `_id`; profile `DELETE .../profile/<id>`; Nightscout
  connector Nightscout source (profile sink).

### C55 — Devicestatus POST with a 24-hex `_id` is stored as ObjectId; re-send guard
- PR #8758, commits `80993afc` (BF-100) + `ad973110` (the PR's own label D1: guard); **S7, S11**; **open-PR #8758**.
- Before: `insertMany(statuses, {ordered: true})` with `_id` as given → stored as **string**
  (`origin/master:lib/server/devicestatus.js:41-70`); `find[_id]` / `DELETE
  /api/v1/devicestatus/<id>` (both via `query_for`, `:105`, `:138`) convert to ObjectId → miss.
- After: before insert, one `find({_id: {$in: <string forms>}})` for batches carrying 24-hex ids;
  an id already stored as a string keeps the string (so the re-send collides), otherwise it is
  converted to ObjectId (`6d120fa2:lib/server/devicestatus.js:50-71`, called `:100-105`);
  `query_for` → `matchEitherForm` (`:144-148`).
- **Re-send response (both sides): HTTP 500**, body from `res.sendJSONStatus(res, 500, 'Mongo Error', err)`
  where `err` is the MongoDB duplicate-key message string (`6d120fa2:lib/api/devicestatus/index.js:168-173`;
  `create` rethrows `err.message`, `6d120fa2:lib/server/devicestatus.js:107-113`). With
  `ordered: true`, items before the duplicate are stored, items after are not (unchanged).
- **Behaviour change the PR body does not list:** a POST whose 24-hex `_id` equals a record stored
  as an **ObjectId** (for example one created without `_id`, read back, and re-posted with its
  `_id`) was stored **a second time** as a string with **HTTP 200** on master; after, it is
  converted, collides, and gets **HTTP 500 `Mongo Error`**. The PR's "refused again, as on dev"
  holds only for the string-stored case.
- Client observes: `find[_id]` and delete-by-id now work for own-`_id` devicestatus; the ObjectId
  collision case above turns a silent duplicate into a 500.
- Search hints: devicestatus upload bodies with `_id`; re-upload/retry of devicestatus; handling
  of 500 on `api/v1/devicestatus`.

### C56 — Food and activity POST/PUT with a 24-hex `_id`
- PR #8758, commit `80993afc` (BF-100); **S7, S9**; **open-PR #8758**.
- Before: `create` (POST) upserts `replaceOne({_id: <as given>})` with a string `_id` kept as the
  string (`origin/master:lib/server/food.js:16-63`, `origin/master:lib/server/activity.js:19-63`);
  `save` (PUT) converts to ObjectId (`food.js:77-124` `normalizeObjectId`; `activity.js:78-91`) →
  misses the string original → second record; `remove` = `deleteOne({_id: ObjectId})`
  (`food.js:157-159`, `activity.js:127-129`) → misses.
- After: `create` converts (`toStoredId`) and appends a `deleteMany` of the string forms
  (`6d120fa2:lib/server/food.js:37-56`, `activity.js:35-56`); `save` likewise (`food.js:104-120`;
  `activity.js:94-103` single `deleteMany` after `replaceOne`); `remove` = `deleteMany` of all forms
  (`food.js:182-187`, `activity.js:138-143`); activity `query_for` widened (`activity.js:108-112`).
  Food has no `find` on its GET routes (`/food/`, `/food/quickpicks`, `/food/regular` ignore the
  query, `6d120fa2:lib/server/food.js:149-178`).
- Also changed, not listed in the PR table: a **POST** (create) with a 24-hex `_id` equal to an
  ObjectId-stored food/activity used to insert a string duplicate; now it **replaces** that record
  (upsert by ObjectId), 200 both sides.
- Search hints: `api/v1/food` POST/PUT with `_id`, `DELETE api/v1/food/<id>`; `api/v1/activity`.

### C57 — v1 `_id` validation: unchanged
- `isValidObjectId` before: `typeof id === 'string' && /^[a-fA-F0-9]{24}$/` or `undefined/null`
  (`origin/master:lib/api/shared/objectid-validation.js:3-11`); after: `isHexId` — the same
  predicate (`6d120fa2:lib/api/shared/objectid-validation.js:4-12`). Used by profile, devicestatus,
  food, activity routes (not treatments/entries). **v1 rejects nothing it accepted before**; the
  400 body stays `Invalid _id format` / `Must be 24-character hex string …`.

## Websocket (S6, S7)

### C58 — `dbAdd` stores a 24-hex `_id` as ObjectId; `dbUpdate`/`dbUpdateUnset`/`dbRemove` match both forms
- PR #8758, commit `12c01268`; **S6, S7**; **open-PR #8758**.
- Before: `dbAdd` inserts `data.data` with `_id` as given → a 24-hex `_id` stored as the **string**
  (`origin/master:lib/server/websocket.js:511`, inserts at `:590`, `:633`, `:686`, `:707`);
  `dbUpdate` / `dbUpdateUnset` / `dbRemove` convert a 24-hex `_id` to ObjectId (`safeObjectID`,
  `:15-25`) and `updateOne`/`deleteOne({_id: ObjectId})` (`:342-366`, `:406-419`, `:745-749`) →
  **miss the record `dbAdd` itself stored, yet reply `{result: 'success'}`**.
- After: `dbAdd` converts a 24-hex `_id` to ObjectId unless a string copy exists (then keeps it so
  the insert collides) (`6d120fa2:lib/server/websocket.js:553-559`, called `:564-569`); `idMatch`
  (`:20-25`) gives `{_id: {$in: idForms}}` + `updateMany`/`deleteMany` for 24-hex ids, exact match
  + `updateOne`/`deleteOne` for any other id (`:370-398`, `:438-455`, `:802-811`). Reply shapes
  unchanged (`{result:'success'}` / `{result:'Unable to process …'}`; `dbAdd` → `[doc]` or `[]`).
- Client observes: websocket edits/deletes of own-`_id` records now take effect; the `dbAdd` reply
  `_id` is an ObjectId (lower-case hex in JSON) instead of the string as sent; a `dbAdd` whose hex
  `_id` equals an **ObjectId-stored** record now collides and replies `[]` (was: string duplicate
  inserted, reply `[doc]`) — for the generic collections; treatments/devicestatus/profile run
  their own dedup queries first (unchanged).
- Search hints: socket.io `emit('dbAdd'|'dbUpdate'|'dbUpdateUnset'|'dbRemove')`, `collection`,
  `_id` in the payload (AAPS NSClient v1, older xDrip, NSClient-derived code).

## API v3 (S13)

### C59 — v3 read/update/delete by `identifier` reach v1 records with a string `_id`
- PR #8758, commits `597e2899` (24-hex string) + `44ac9047` (non-hex string, the PR's own label D2); **S13, S7**;
  **open-PR #8758**.
- Before: `filterForOne` = `identifier == X` OR (if 24-hex) `_id == ObjectId(X)`
  (`origin/master:lib/api3/storage/mongoCollection/utils.js:106-116`); `identifyingFilter`
  likewise (`:132-139`). A record stored with a 24-hex **string** `_id`, or a non-hex string `_id`
  (UUID treatment/entry from ≤15.0.6, custom websocket id), is listed by v3 search under
  `identifier` = that `_id`, but `GET/PUT/PATCH/DELETE /api/v3/<coll>/<identifier>` → **404**, and a
  v3 create/PUT for it inserts a **second record**.
- After: 24-hex identifier matches `_id` in every form; any other string identifier matches `_id`
  literally (`6d120fa2:lib/api3/storage/mongoCollection/utils.js:112-121`, `:145-152`); a
  non-string identifier gets no `_id` branch.
- Client observes: 404 → 200 for those records; no second record on write.
- Search hints: `api/v3/` + `identifier` path; `lastModified` sync clients reading `identifier`.

## Contract matrix (before = master/dev base, after = 6d120fa2)

Stored forms: **OID** = ObjectId; **hex-s** = 24-hex string (lower); **HEX-s** = upper-case string;
**uuid-s** = non-hex string. "found" = the operation reaches the record. Cells are read-derived from
the anchors above; the PR's own 336-cell test (`tests/api.crud-by-id.matrix.test.js`) was **not run**.

| collection | op (surface) | OID | hex-s | HEX-s | uuid-s |
|---|---|---|---|---|---|
| entries | v1 GET/DELETE `/entries/<lower>` | found → found | miss → found | miss → miss (only same spelling) | n/a (non-hex path = type name) |
| entries | v1 GET/DELETE `/entries/<UPPER>` | **miss → found** | miss → found | miss → found | n/a |
| entries | v1 POST re-send, `_id` ≠ stored, same time+type | 500 → 200, keeps stored `_id` | 500 → 200 | 500 → 200 | UUID `_id` stripped → `identifier` (unchanged) |
| entries | POST response `_id`, matched reading | sent/none → stored `_id` | same | same | same |
| treatments | v1 POST/PUT by `_id` | update → update | **2nd copy → one record** | 2nd copy → one record (submitted spelling) | UUID → `identifier` (unchanged) |
| treatments | v1 DELETE `/treatments/<id>`, `find[_id]` | found → found | miss → found | miss → found if same spelling | unchanged (UUID_HANDLING `$or`) |
| profile | v1 POST new hex `_id` | stored hex-s → stored OID | — | — | 400 (unchanged) |
| profile | v1 POST, `_id` already stored | **200 + string duplicate → 500** | 500 → 500 | 500 → 500 (same spelling) | 400 |
| profile | v1 PUT | update → update | **2nd copy → one** | 2nd copy → one | 400 |
| profile | v1 DELETE `/profile/<id>`, `find[_id]` | found → found | **miss → found** | miss → found (same spelling) | 400 |
| devicestatus | v1 POST new hex `_id` | stored hex-s → stored OID | — | — | 400 |
| devicestatus | v1 POST, `_id` already stored | **200 + string duplicate → 500** | 500 → 500 | 500 → 500 | 400 |
| devicestatus | v1 DELETE `/devicestatus/<id>`, `find[_id]` | found → found | miss → found | miss → found (same spelling) | 400 |
| food / activity | v1 POST hex `_id` | new: hex-s → OID; existing OID: **dup → replace** | dup-free replace → replace + string removed | as hex-s, submitted spelling | 400 |
| food / activity | v1 PUT | update → update | **2nd copy → one** | 2nd copy → one | 400 |
| food / activity | v1 DELETE `/<coll>/<id>` | found → found | miss → found | miss → found (same spelling) | 400 |
| all ws collections | `dbAdd` hex `_id` | new: hex-s → OID; existing OID: **dup → `[]`** (generic) | collide `[]` → collide `[]` | collide → collide | kept as given (unchanged) |
| all ws collections | `dbUpdate`/`dbUpdateUnset`/`dbRemove` | found → found | **miss (reply success) → found** | miss → found if same spelling | exact match (unchanged) |
| all v3 collections | GET/PUT/PATCH/DELETE `/api/v3/<coll>/<identifier>` | found → found | **404 → found** | 404 → found if same spelling | **404 → found** |

Not changed anywhere: `find[_id][$in][]=…` / other operator forms on `_id` (ObjectId only, string
copies not matched); the non-hex `_id` rules (entries/treatments strip → `identifier` under
`UUID_HANDLING`; 400 on profile/devicestatus/food/activity; websocket keeps as given).

## Edge noted (not a regression)

- Profile's create guard looks up **only the exact submitted spelling**
  (`6d120fa2:lib/server/profile.js:29-37`), while devicestatus and `dbAdd` look up lower-case +
  submitted (`devicestatus.js:54-58`, `websocket.js:555-557`). A profile stored as lower-case
  string and re-sent with the same id in upper case is converted to ObjectId and inserted beside it
  (a second profile) — the same outcome as on master (different strings never collided).

## Prose vs code mismatches

Against `releases/cgm-remote-monitor-15.0.9/release-notes.md` §"Edited records no longer leave an
old copy behind" (lines 463-480, behind `<!-- PENDING: #8758 merge -->`) and the PR bodies.

1. **"Nothing in your database changes until a record is edited or deleted."** Code: a new POST
   (profile, devicestatus, food, activity) or websocket `dbAdd` carrying a 24-hex `_id` is now
   **stored differently** (ObjectId instead of string), and a food/activity **POST** (create) with
   an id that exists as a string removes the string copy. The PR body says "until a record is
   written, edited or deleted"; the release notes dropped "written".
2. **Not in the release notes at all** (API clients would notice):
   - entries POST re-send with a different `_id`: **HTTP 500 → 200** (C49);
   - entries POST response now carries the **stored** reading's `_id`, possibly different from the
     one sent (C50);
   - `GET`/`DELETE /api/v1/entries/<UPPER-HEX>` now find/delete (C51);
   - profile/devicestatus POST, and websocket `dbAdd` (generic collections), with a 24-hex `_id`
     that equals an **ObjectId-stored** record: **200 + silent duplicate → HTTP 500 `Mongo Error`**
     (v1) / reply `[]` (websocket) (C55, C58);
   - response `_id` for an upper-case hex `_id` sent to profile/devicestatus/food/activity/`dbAdd`
     is now lower-case.
3. **PR body "a device status report re-sent … is refused again, as on dev, instead of being stored
   twice" / "unchanged: … a re-sent profile (still refused)".** True for a record stored as a
   string. For a record stored as an ObjectId, dev **accepted** the re-send (200, string duplicate)
   and #8758 **refuses** it (500). The "unchanged" list does not cover that case.
4. **Release notes: "In this release those records are found."** Code limits: an upper-case string
   `_id` is found only in that spelling (`object-id-forms.js:14-20`, stated in the PR as its own label D4);
   `find[_id]` with `$in`/other operators is not widened; food GET has no id filter at all. Minor,
   but "found" is unconditional in the notes.
5. **Release notes: devicestatus listed among records where "editing one saved a second copy".**
   v1 has no devicestatus PUT (`6d120fa2:lib/api/devicestatus/index.js` routes: GET, POST, DELETE
   only); for devicestatus the defect was find/delete by id only (and websocket `dbUpdate`). Minor
   wording.
6. **"treatments and glucose readings saved that way by Nightscout 15.0.6 or earlier"** — consistent
   with code: `15.0.6:lib/server/treatments.js` upserts `obj` with `_id` as given; 15.0.7 added the
   hex→ObjectId conversion (`15.0.7:lib/server/treatments.js:375-376`, `entries.js:259`).

## Not settled

- The 336-cell matrix and the PR's test counts were not run here (read-only brief).
- Whether the `data-update` bus event for a string copy removed by `withStaleStringsRemoved` /
  `deleteMany` reaches websocket clients (no `remove` event is emitted for it in the code read;
  open pages may keep showing the old copy until reload). Not verified by running.


---

# Dependencies — Express/qs/socket.io stack (C60–C67)

## Part intro: Dependency changes a client can observe: qs 6.16 (#8749) and the other bumps (items 7 and 11)

Server repo: `externals/cgm-remote-monitor-official`. Refs: `origin/master` 92d08342 (= 15.0.8),
`origin/dev` ddd9b600 (2026-09-23), open PRs #8754 `ef3404fd` and #8758 `6d120fa2`.
Installed versions come from `package-lock.json` `packages["node_modules/<name>"]` on each ref,
not from `package.json` ranges.

The evidence is labelled as follows:
- **read-derived** means taken from source or lock files; nothing was run.
- **reproduced locally against qs@x** means the qs parser was run in Node on its own, in
  `scratch/` (`scratch/probe.js`), with the exact options each Express version passes. No
  server was run and no request was sent anywhere.

## Headline

The change to how query strings are read between 15.0.8 and the candidate comes from the
**Express 4.22.1 → 4.22.2** bump (#8571, merge `6fb8db1c`, 2026-09-05). It does **not** come
from qs 6.15.1 → 6.16.0 (#8749).

- Express 4.22.2 passes `arrayLimit: 1000` to qs for `req.query`. Express 4.22.1 used qs's
  default of 20.
- On 15.0.8, a query-string array of **21 or more** values (for example `find[_id][$in][]=…`
  repeated 21 times, or `find[_id][$in][0..20]`) reaches the server as an **object with numeric
  keys** (`{"0":…, "1":…}`), not an array.
- On the candidate, that array stays an array up to 1000 values.

This change is not mentioned in the release notes (see the mismatches section).

---

## C60: query-string arrays of 21–1000 values now reach the server as arrays (Express 4.22.2)

- **PR / merge:** #8571 (`dependabot/npm_and_yarn/multi-be700a2db9`), merge `6fb8db1c`. The
  lock moves express 4.22.1 → 4.22.2 and body-parser 1.20.5 → 1.20.6 in this merge and no other
  (attributed per merge from `package-lock.json`, **read-derived**).
- **Status:** merged (in dev).
- **Surfaces:** S12 (array size), S2 (`$in`/`$nin`, `$or`/`$and` branch lists), S7 (bulk
  GET/DELETE by `_id` list), S13 (API v3 uses its own express app with the same default parser),
  S15.

**Server configuration (read-derived):**
- Nightscout never sets `'query parser'`, and there is no `qs.parse` call in `lib/`. `git grep`
  for `query parser|qs.parse|require('qs')` finds only a comment at
  `origin/dev:lib/server/query.js:161`.
- Express's default is `'extended'` (express `lib/application.js:84`, both versions).
- The query string is therefore parsed by express `lib/utils.js:288` `parseExtendedQueryString`:
  - express 4.22.1 (15.0.8): `qs.parse(str, { allowPrototypes: true })`, which means qs's default
    `arrayLimit: 20`, `parameterLimit: 1000`, `depth: 5`, `allowDots: false`.
  - express 4.22.2 (candidate): `qs.parse(str, { allowPrototypes: true, arrayLimit: 1000 })`.
- There is no nested `express/node_modules/qs` on either ref, so express uses the top-level qs:
  6.15.1 on master and 6.16.0 on dev.
- Express 4.22.2's `History.md` says: "restore >20 array parsing for `req.query` repeated keys …
  Indexed notation … also allows up to 1000 items."

**Before (15.0.8)**, reproduced locally against qs@6.15.1 with `{allowPrototypes:true}`:

| query shape | 20 values | 21 values | 100 / 1000 values |
|---|---|---|---|
| `find[_id][$in][]=v` repeated | array (20) | **object, keys "0".."20"** | object |
| `find[_id][$in][0]=v…[n]=v` (indexed) | array | **object** | object |
| `find[_id][$in]=v` repeated (no brackets) | array | **object** | object |

A lone sparse index such as `a[25]=1` becomes the object `{"25":"1"}`.

The server then passes the object on as the `$in` operand:
- `origin/master:lib/server/query.js:113-121` converts each leaf to an ObjectId and leaves the
  container as an object.
- MongoDB refuses `$in` with a non-array operand. That is MongoDB behaviour from reading and
  general knowledge; it was not run.
- On `/api/v1/entries`, the error becomes HTTP 500 `Mongo Error`
  (`origin/master:lib/api/entries/index.js:138`, `:258`).
- On `/api/v1/treatments`, `serveTreatments` does not check `err` before calling
  `results.forEach` (`origin/master:lib/api/treatments/index.js:27`, `:35`). The request fails
  with a thrown TypeError. The exact HTTP outcome there is **not settled**.
- The same applies to `$nin`, and to `find[$or][…]` / `find[$and][…]` with 21 or more branches:
  MongoDB needs an array for `$or`/`$and`.

**After (candidate)**, reproduced locally against qs@6.16.0 with
`{allowPrototypes:true, arrayLimit:1000}`:
- All three shapes stay arrays up to 1000 values, so `$in`/`$nin`/`$or`/`$and` with 21–1000
  values work.
- `a[25]=1` becomes `["1"]` (compacted).
- A dev test pins 25-value `$in` arrays in bracket, indexed and repeated notation through
  Nightscout's query conversion (`origin/dev:tests/dependency-express.test.js:130`,
  **read-derived**; not run here).
- The operator allowlist accepts array operands as literals
  (`origin/dev:lib/server/query-operator-allowlist.js:96-101`, called from
  `origin/dev:lib/server/query.js:249`).

**Above 1000 values (unchanged, both refs):**
- qs `parameterLimit` 1000 applies to the **whole** query string. Parameters after the 1000th are
  **silently dropped**, including any `count` or `find[date]` placed after the ids.
- The server receives the first ~1000 values as an array on dev, or as an object on master.
- Reproduced locally: 1001 and 1500 values give 1000 keys on both refs.
- Because of this, on dev `arrayLimit` 1000 can never actually be exceeded through the query
  string.

**What a client would observe:**
- A client that sends 21 or more `$in` values, such as a bulk fetch or bulk delete by an id list:
  - on 15.0.8 it gets an error (500 on entries), or a failure on treatments;
  - on 15.0.9 the request works.
- This includes **DELETE with `find[_id][$in][]`**: on 15.0.8 it fails and deletes nothing; on
  15.0.9 it **deletes every matching record**.
- A client that learned to split lists into chunks of 20 or fewer sees no change.
- A client that relied on the failure as a guard, for example retrying or dropping, now gets data
  or deletions.
- **Baseline note:** 15.0.7 (express 4.17.1, qs 6.14.1) already turned repeated `[]` arrays of
  more than 20 values into objects (reproduced locally against qs@6.14.1). So "more than 20 fails"
  also held on 15.0.7. It is not new in 15.0.8.

**Client search hints:**
- `$in]`, `%24in`, `[$in][]`, `$nin`, `find[_id]`, `find[$or]`, `find[$and]`
- chunk/batch sizes of 20 near id lists (`chunked(20)`, `slice(0, 20)`, `batch`)
- bulk-delete helpers (`DELETE … /api/v1/treatments?find[_id]`)
- URLQueryItem loops over ids; Retrofit `@Query("find[_id][$in][]") List<…>`

## C61: form-post (urlencoded) body parsing is unchanged apart from limit validation (body-parser 1.20.6)

- **PR / merge:** #8571, merge `6fb8db1c`. Status: merged.
- **Surfaces:** S12, S15. Not observable.

**Code (read-derived):**
- Nightscout's urlencoded parser is `extended: true, limit: '1Mb', parameterLimit: 50000`
  (`origin/master:lib/middleware/index.js:21-24`; the same at `origin/dev` `:21-24`).
- body-parser's extended parser calls qs with
  `arrayLimit: max(100, paramCount), depth: 32, strictDepth: true`. That code is identical in
  1.20.5 and 1.20.6 (`lib/types/urlencoded.js:136-185`).
- The only change in 1.20.6: an **invalid** `limit` option now throws at construction instead of
  disabling the cap.
- Every limit Nightscout passes is valid: `'50Mb'`, `'1Mb'`, `1048576 * 50`, and no-option calls
  that get the 100kb default. Anchors: `origin/dev:lib/api/entries/index.js:44-45`,
  `lib/api/treatments/index.js:17-18`, `lib/api/activity/index.js:17-18`,
  `lib/api2/notifications-v2.js:14-15`, `lib/api3/index.js:40-41`,
  `lib/authorization/endpoints.js:15-19`, `lib/server/app.js:149`.
- Nothing is accepted or refused differently.

**Search hints:** none needed.

## C62: qs 6.15.1 → 6.16.0 changes only malformed bracket keys (#8749)

- **PR / merge:** #8749 (`bf/qs-6.16`), merge `9fd4600e`. `overrides.qs` and
  `overrides.request.qs` change 6.15.1 → 6.16.0 (`origin/dev:package.json`, overrides block).
- **Status:** merged.
- **Surfaces:** S12, S2.

**Before and after (read-derived from the qs `lib/` diff, plus reproduced locally against both
versions):**
- **Unchanged:**
  - the parse defaults;
  - arrays up to 1000 under Express's options (identical results for 20, 21, 22, 100, 1000,
    1001 and 1500 values);
  - `parameterLimit` 1000;
  - `depth` 5, with the remainder kept as a literal key segment:
    `find[a][b][c][d][e][f][g]=1` gives the key `"[f][g]"` at depth 6 on both;
  - `allowDots: false`: `find.sgv.$gte=1` stays one literal key on both;
  - empty values: `count=` / `find[type]` / `mute` all become `""` on both;
  - no comma splitting: `find[_id][$in]=a,b` stays the string `"a,b"` on both.
- **Changed:** `splitKeyIntoSegments` (qs 6.15.2) now balances nested brackets. Keys whose
  brackets do not pair up parse differently, for example:
  - `find[sgv][$gte=1`: on 6.15.1 this was an equality match on `sgv`; on 6.16.0 it is the
    operator-like key `[$gte`, which matches nothing;
  - `find[sgv=1`: on 6.15.1 it was dropped from the filter; on 6.16.0 it is a field named `[sgv`;
  - `$`-operators carrying brackets (`[$gte[x]]`) keep them. The v1 allowlist
    (`origin/dev:lib/server/query-operator-allowlist.js:132`) then refuses them with HTTP 400
    `Query operator … is not supported`.
- This list comes from the PR body's differential. I confirmed the grammar change in the `lib/`
  diff and did not re-run all 15 inputs.
- `merge`/`combine` overflow changes (6.15.3, 6.16.0) only show when `arrayLimit` is exceeded or
  `throwOnLimitExceeded` is set. Neither can happen under Nightscout's options (see C60).

**What a client observes:** nothing, for well-formed queries. A client that emits unbalanced
brackets (for example a string-concatenation bug that drops a `]`) now gets an empty result or a
400 where it used to get a quietly rewritten filter.

**Search hints:** hand-built query keys containing `[` without a matching `]`; strings like
`"find[" + field + "][$gte="`, or `"[$" + op` with no closing bracket.

## C63: the socket.io transport stack has small bumps and no protocol change

- **PRs / merges:**
  - #8566 (`multi-d41c8c1b4b`), merge `c5fd8054`: engine.io 6.6.7 → 6.6.10; ws 8.20.1 → 8.21.3.
    Master also had a nested `engine.io/node_modules/ws` 8.18.3, which is gone on dev, so engine.io
    moves 8.18.3 → 8.21.3.
  - #8577, merge `4b665293`: socket.io-parser 4.2.6 → 4.2.7.
  - socket.io 4.8.3 and socket.io-client 4.8.3 (the copy served to pages at `socket.io/socket.io.js`,
    `origin/dev:views/index.html:756`) are **unchanged**.
- **Status:** merged. **Surfaces:** S6.

**Server options, identical on both refs (read-derived):**
- `origin/master:lib/server/websocket.js:88-103` and `origin/dev:lib/server/websocket.js:88-103`
  set `allowEIO3: true` (line 93), `transports: ["polling","websocket"]`,
  `perMessageDeflate {threshold:512}` and `httpCompression {threshold:512}`.
- No `cookie`, `cors`, `maxHttpBufferSize`, `pingTimeout` or `pingInterval` is set, so the
  engine.io defaults apply: 1e6 bytes, 20000 ms and 25000 ms, the same in 6.6.7 and 6.6.10
  (engine.io `build/server.js:41-51` / `:48-58`).

**Library deltas (read-derived from the tarball diffs):**
- engine.io 6.6.10 refuses a transport **upgrade** whose `EIO` query value differs from the one
  the session was opened with (`PROTOCOL_MISMATCH`, `build/server.js` `computeProtocolRevision`).
  A real v2/EIO3 or v3–v4/EIO4 client sends the same `EIO` on its polling handshake and on its
  upgrade, so this is not expected to affect any genuine client library.
- Other engine.io deltas:
  - cookie `httpOnly` is forced true, but Nightscout sets no cookie;
  - WebTransport session clean-up;
  - polling body accumulation is refactored with the same `maxHttpBufferSize`.
- socket.io-parser 4.2.7:
  - a BINARY packet that declares 0 attachments is no longer emitted as decoded; an attachment
    count must now be at least 1;
  - `toJSON()` is honoured when encoding binary.
  - Nightscout's messages (`authorize`, `loadRetro`, `dataUpdate`, `/alarm` `subscribe`/`ack`,
    `dbAdd`/`dbUpdate`/`dbRemove`) are JSON events without binary, so this is not observable.
- ws 8.21.3:
  - new server defaults `maxFragments` 16384 and `maxBufferedChunks` 262144 per message, with
    close code 1008 when exceeded;
  - a permessage-deflate negotiation fix for a numeric `client_max_window_bits`, which does not
    apply because Nightscout sets no `clientMaxWindowBits`.
  - Ordinary clients do not fragment a message 16k times.

**What a client observes:** nothing. Old socket.io v2 clients (EIO3), such as libraries embedded
in older iOS and Android apps, still connect because `allowEIO3: true` is unchanged. Socket
**authorisation** does change (#8744, #8745, #8758), but that is covered elsewhere and is not a
dependency effect.

**Search hints (for completeness):** `EIO=3`, `socket.io-client` version pins in `Podfile`,
`build.gradle`, `package.json`; `Socket.IO-Client-Swift` major version.

## C64: uuid is NOT bumped (#8529 kept uuid 11)

- **PR / merge:** #8529 (titled "uuid-14.0.0"), merge `9205ea30`. The merge commit body says
  "retain patched UUID 11 and protect API identifiers". `package.json` stays `"uuid": "^11.1.1"`
  on both refs (`origin/master:package.json:156`, `origin/dev:package.json:157`), and the lock
  stays uuid 11.1.1.
- **Status:** merged, with tests only.
- **Surfaces:** S13 (API v3 `identifier` generation, `origin/dev:lib/api3/shared/operationTools.js:5`).

**What a client observes:** nothing. Generated `identifier` values are unchanged in form.

**Search hints:** none.

## C65: axios bumps affect only the server's outbound requests

- **PRs / merges:**
  - #8565, merge `eedc9439`: top-level axios 0.31.1 → 0.33.0. It is a devDependency, but
    `overrides.minimed-connect-to-nightscout.axios` is also set to 0.33.0, so the legacy mmconnect
    plugin's outbound CareLink calls use it.
  - nightscout-connect's nested axios moves 1.16.0 → 1.20.0 with the connector pin (#8752 / #8759;
    lock `node_modules/nightscout-connect/node_modules/axios`).
- Nightscout's `lib/` has no `require('axios')` outside `lib/api3/doc/tutorial.md`
  (**read-derived**).
- **Status:** merged. **Surfaces:** none of S1–S15 directly. For clients that sync from another
  Nightscout site, the connector behaviour change belongs to the connector-pin entry (item 9),
  not here.

**What a client observes:** nothing on the Nightscout API.

## C66: the browser page bundle is built with d3 7 and babel 7.29 / babel-loader 9

- **PRs / merges:**
  - #8573 (`multi-45103ee312`), merge `e7c0cd6f`: d3 5.16.0 → 7.9.0, bundled through
    `origin/dev:bundle/bundle.source.js:9`. The same merge adapts `lib/client/renderer.js`,
    `lib/client/chart.js` and `lib/report_plugins/daytoday.js`.
  - #8550, merge `7e71fb62`: @babel/core 7.29.0 → 7.29.7; babel-loader 8.4.1 → 9.2.1.
- There is no babel, browserslist or webpack config change between the refs (`git diff --stat`
  of those paths is empty).
- **Status:** merged. **Surfaces:** HTML page only; no S-id for API clients.

**What a client observes:** only people using the web page can see a difference, in chart and
report rendering. That is the parent inventory's renderer entries. There is no API effect.

## C67: #8754 adds `proxy-addr` as a direct dependency (open PR)

- `ef3404fd:package.json` adds `"proxy-addr": "^2.0.7"`. The lock already had 2.0.7 as an
  Express dependency (`origin/dev` and `ef3404fd` lock both 2.0.7), so the installed version is
  unchanged.
- The client-visible effect is `TRUST_PROXY` (`ef3404fd:lib/server/app.js:52`
  `app.set('trust proxy', …compileTrust(env.trustProxy))`, versus
  `origin/dev:lib/server/app.js:52` `app.enable('trust proxy')`). That belongs to the #8754 entry
  (item 10), not here.

---

## Every package.json / lock bump master..dev, classified

| package (lock) | before → after | merge (PR) | observable to API/socket/HTML client? | reason |
|---|---|---|---|---|
| express | 4.22.1 → 4.22.2 | `6fb8db1c` (#8571) | **YES (C60)** | `req.query` `arrayLimit` 20 → 1000 |
| body-parser | 1.20.5 → 1.20.6 | `6fb8db1c` (#8571) | no (C61) | only invalid `limit` options now throw; Nightscout's are valid |
| qs | 6.15.1 → 6.16.0 | `9fd4600e` (#8749) | only malformed bracket keys (C62) | nested-bracket segmenting; overflow changes unreachable |
| qs under `request` | 6.15.1 → 6.16.0 | `9fd4600e` (#8749) | no | outbound mmconnect `request` stringify |
| side-channel | 1.1.0 → 1.1.1 | `9fd4600e` (#8749) | no | assert message building |
| engine.io | 6.6.7 → 6.6.10 | `c5fd8054` (#8566) | no (C63) | upgrade EIO mismatch refused; defaults unchanged |
| ws (engine.io's) | 8.18.3 → 8.21.3 | `c5fd8054` (#8566) | no (C63) | fragment/chunk caps far above normal use |
| socket.io-parser | 4.2.6 → 4.2.7 | `4b665293` (#8577) | no (C63) | 0-attachment binary packets; Nightscout sends JSON events |
| socket.io / socket.io-client | 4.8.3 = 4.8.3 | – | no | unchanged; `allowEIO3: true` unchanged |
| uuid | 11.1.1 = 11.1.1 | `9205ea30` (#8529) | no (C64) | not bumped despite the PR title |
| axios (top-level; mmconnect override) | 0.31.1 → 0.33.0 | `eedc9439` (#8565) | no (C65) | outbound only |
| nightscout-connect | 0.0.13 → 0.1.0-dev.2 → 0.1.0-dev.3 | `f0954a6a` (#8752), `feafa533` (#8759) | yes, but a connector behaviour change | handled by the item-9 connector entry |
| axios under nightscout-connect | 1.16.0 → 1.20.0 | with the connector pin | no | outbound only |
| d3 | 5.16.0 → 7.9.0 | `e7c0cd6f` (#8573) | HTML page only (C66) | chart code adapted |
| @babel/core, @babel/preset-env | 7.29.0 → 7.29.7 | `7e71fb62` (#8550) | no | bundle build; no target config change |
| babel-loader | 8.4.1 → 9.2.1 | `7e71fb62` (#8550) | no | build tooling |
| jsdom (dev) | ^24 → ^26 | `97d1aa1b` (#8544) | no | tests only |
| mocha (dev) | 11.7.5 → 11.8.0 | `02c63225` (#8581) | no | tests only |
| dompurify (dev) | 3.4.3 → 3.4.14 | `3bb07409` (#8578) | no | dev only; production sanitising is `sanitize-html` 2.17.5, unchanged |
| ip-address | 10.2.0 → 10.7.0 | `f7c7812c` (#8575) | no | MongoDB driver SOCKS proxy address parsing |
| fast-uri | → 3.1.7 | `4b62921b` (#8576) | no | Ajv (build and schema tooling) |
| postcss / nanoid | 8.5.14 → 8.5.28 | `1156aafd` (#8582) | no | CSS build |
| js-yaml | → 3.15.2 / 4.3.2 | `a363d760` (#8579) | no | eslint/nyc/mocha tooling |
| brace-expansion | → 1.1.18 / 2.1.4 / 5.0.9 | `d6e90d00` (#8586) | no | glob tooling |
| proxy-addr (#8754, open) | 2.0.7 = 2.0.7 | `ef3404fd` | no by itself (C67) | now a direct dependency; `TRUST_PROXY` belongs to item 10 |
| (#8758, open) | – | `6d120fa2` | – | no package.json or lock change |

## Prose vs code mismatches (deps)

1. **The release notes leave out the one parsing change clients can observe.** The notes (Other
   fixes) say the query library "is updated to a version that clears three published security
   notices against it, with no difference for any request a known app sends", and otherwise
   mention only "many software library updates".
   - The qs part is accurate for qs 6.15.1 → 6.16.0 **measured against dev**.
   - But 15.0.8 → 15.0.9 **does** change how requests are read: Express 4.22.2 (#8571) turns
     query-string arrays of 21–1000 values from an object into an array (C60).
   - Requests that fail on 15.0.8 (`$in`/`$nin` with more than 20 values, or `$or`/`$and` with
     more than 20 branches, including bulk **DELETE** by an id list) **succeed** on 15.0.9.
   - Nothing that works on 15.0.8 stops working. But a bulk delete that used to fail harmlessly
     now removes records, which operators and client authors should hear about.
2. **The #8749 PR body (`reports/phase0-pr-bodies/qs-6.16.md`) measured the wrong baseline for a
   15.0.8 → 15.0.9 statement.**
   - Its differential compared `origin/dev` `74fc6619`, which already had Express 4.22.2, with the
     branch. So "arrays at 19–22, 99–102 and 999–1002 … zero differences" and "Express sets
     `arrayLimit: 1000`" are true on dev and **false for 15.0.8**, where Express 4.22.1 passes no
     `arrayLimit`, so it is 20.
   - Its closing line, "15.0.8 (`master`) carries the same two pins and the same audit findings",
     is true about the qs pins. Read next to "Express sets arrayLimit: 1000", it suggests 15.0.8
     reads queries the same way, and it does not.
   - Reproduced locally against qs@6.15.1: 21 values on 15.0.8's options give an object.
3. **The #8529 title says "uuid-14.0.0", but uuid is not bumped** (11.1.1 on both refs). This is
   minor and only matters so that no one reads a uuid-14 identifier change into the release.

## Not settled

- The exact HTTP response on 15.0.8 for `/api/v1/treatments` when MongoDB refuses a non-array
  `$in`: `serveTreatments` does not check `err` (`origin/master:lib/api/treatments/index.js:27-35`),
  so it is a thrown TypeError. Whether Express turns that into a 500 or it escapes the callback
  was not run.
- "MongoDB refuses a non-array `$in`/`$or` operand" is based on MongoDB's documented behaviour.
  It was not run against mongod here.
- The 15 malformed-key inputs in C62 are taken from the PR body's differential. I confirmed the
  grammar change in the qs diff but did not re-run every input.


---

# Not settled (consolidated)

1. **15.0.8 responses to `count=abc` and `count=0x10` on the storage path.** `limit(NaN)` is what the
   MongoDB 5.9 driver receives; whether it errors or reads NaN as 0 was not run. On 15.0.9 both are
   400, so this only matters for describing "before". (C1)
2. **15.0.8 response on `/api/v1/treatments` and `/api/v1/activity` when the query errors.** The
   callbacks do not check `err` and throw, and the exact HTTP outcome (express 500, or an escaped
   exception) was not run. (C6, C60)
3. **MongoDB's refusal of a non-array `$in`/`$or` operand.** This is taken from MongoDB's documented
   behaviour and was not run. (C60)
4. **The `/api/v1/echo/…` refusal body.** Status 400 comes from `err.status` through `errorhandler`.
   The exact body format was taken from library behaviour, not re-read. (C5)
5. **`TRUST_PROXY` refused at boot.** Whether a hosting platform turns the process exit into a
   restart loop was not checked. Express 4.22.2's `req.protocol` source was not re-read. (C46)
6. **#8758 leftover string copies.** Whether an open page stops showing a leftover string copy after
   it is deleted was not traced: no `remove` event is emitted for it in the code read. The PR's
   336-cell matrix was not run. (C49–C59)
7. **How follower apps use `/alarm` `subscribe`/`ack`, and with which role.** Also whether repeated
   subscribes, which stack duplicate `ack` listeners, cause anything visible. This is for the join
   step. (C38, C39)
8. **The connector 0.1.0-dev.3 → 0.1.0 behaviour changes** beyond the query shapes it sends to a
   source site. Those were taken from the release notes, which are behind PENDING markers, and not
   re-derived. (C33)
9. **#8733 treatment processing.** It is claimed to preserve results exactly, and this was not
   verified by running. (C26 note)
