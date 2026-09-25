# Backfix register — defects that ship to existing operators, independent of multitenancy

*Contributor-facing. Living document, maintained alongside the
[multitenancy execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md).
Entries name the refs they were measured on. Status and the counts below are as of 2026-09-24,
cgm-remote-monitor `origin/dev` `153e5658` and `origin/master` `92d08342` (= tag `15.0.8`, the
shipping release), nightscout-connect `0.1.0`. Nothing here is medical advice.*

**What belongs here.** An entry in §1 is a defect that

- affects **single-tenant self-hosters running the current release**, and
- is fixable **without any tenancy decision**, and
- can therefore land on its own, on `dev` or on `chore/nightscout-modernization`, ahead of the
  storage seam.

Decision D4 makes MongoDB and single-tenant first-class permanently, so "fixed when the PostgreSQL
backend lands" is never an answer for an entry here. Findings that fail the first criterion —
defects in unmerged seam, tenancy or release-train branches, and missing checks over behaviour
that is correct today — are in **§1b**. Absent features with a bounded scope are in **§1c**.
**§2** and **§2b** hold one detail section per id; **§3** is how to use the register; **§4** says
where it sits among the programme's documents. Audit coverage is recorded at the end of this
preamble.

This register is authoritative for **defect facts and ids**. Item state lives in
`queue/work-queue.yaml`; decisions live in the execution plan.

**Status values.** The status is the last column of every table and begins with one of these
words:

| status | meaning |
|---|---|
| `open` | not repaired anywhere |
| `fixed <date>` | repaired on a backfix branch with tests, **not merged**; the row names the branch and commit |
| `partly merged <date>` | part of the repair is in `origin/dev`; the detail section says what was deliberately left |
| `merged <date>` | in `origin/dev`, **not in any release**; the row names the PR |
| `released <tag>` | in a tagged release that operators install. **No entry has this status** — nothing from this register has been released. (`tools/queue/gates/register-exposure-legend.js` looks for this state under the name `landed`.) |
| `fixed-in-seam` | repaired only as a side effect inside the seam branch; needs extracting to land independently |
| `wontfix` | deliberately not repaired, with the reason in the detail section |
| `closed …, invalid` | investigated and does not reproduce; the row is struck through and kept, so the claim is not raised again |

**Connector defects.** For a defect in `nightscout-connect`, the status word is what a Nightscout
operator gets: `merged <date>` is the date Nightscout `dev` first pinned a connector version
carrying the fix. The cell then says where the connector release stands, in the form
"connector: released in nightscout-connect `0.1.0` (npm, 2026-09-24); Nightscout `dev` pins `0.1.0`
exactly via PR #8762". A connector release reaches Nightscout operators only through a Nightscout
release, so such an entry is still present on 15.0.8, which pins connector `v0.0.13`.

**What a status means for an operator.** Every §1 entry marked `fixed`, `partly merged` or
`merged` is **still present for every operator running today's release, 15.0.8, until it is
released.** Merging to `dev` is not releasing: a push to `dev` publishes a Docker Hub image, but
`origin/master` and its tags are what operators install. On 2026-09-25 `origin/master` is **384
commits behind `origin/dev` (`4f705217`) and 0 ahead**
(`git -C externals/cgm-remote-monitor-official rev-list --count official/master..official/dev`),
and the release PR #8598 (`dev` → `master`) is open at `4f705217`, with no review.

| question | answer, 2026-09-25 (`origin/dev` `4f705217`) | reproduce with |
|---|---|---|
| How many §1 defects are there, and how many reach an operator on 15.0.8? | **78** §1 defects (every §1 entry except BF-12, invalid, and BF-41, closed): **26 open, 46 merged, 1 partly merged (BF-07), 5 fixed on an unmerged branch** (BF-99 to BF-102 in PR #8758; BF-52 on a local branch). **76** reach an operator on 15.0.8 — BF-80 and BF-106 exist only on `dev` (below) | `node tools/queue/gates/register-exposure-legend.js` (it counts BF-07 under open) |
| How much work is outstanding? | **54 ids not repaired** | `make queue-coverage` (counts `partly merged` as not fixed) |

Two §1 entries are an overstatement to know about: BF-80 is a cost of BF-75's fix and BF-106 a
cost of BF-03's, so each is present where its fix is (`dev`) and not on 15.0.8. They are filed in
§1 because they will ship to every operator with the next release.

**Provenance.** Every status cell carries one marker, and the detail section says what was run
against which ref.

- **reproduced** — the defect was run: against a live instance, a booted app, a real `mongod`, or
  the shipping module executed directly, with a control where the claim is about access or
  severity. Reachability and severity stand as measured, on the refs named.
- **read-derived** — inferred from source, not run. Reachability and severity are hypotheses, a fix
  prescribed from reading is a proposal (marked **UNVERIFIED** in the detail), and the entry is a
  request to go and run it.

Where only part of a claim was run, the cell says which part.

**Mechanism, not recipe.** This repository is public. An entry that is live on 15.0.8 describes the
mechanism only; the working probes for BF-70, BF-72, BF-73, BF-75, BF-79 and BF-107 are held
outside version control, and no request, payload or pattern that would work against a deployed instance
belongs in this file.

**Allocating an id.** Read the highest `BF-` id in §1 and §1b at the moment you write the entry
and take the next one — never the id a brief or plan quoted, because concurrent sessions file here.
On 2026-09-25 the highest is BF-117. BF-82, BF-83 and BF-84 are reserved for three connection-pooler
defects on the unmerged seam branch
([pgbouncer-tenant-binding](../../60-research/tenancy/pgbouncer-tenant-binding-2026-09-15.md)),
which belong in §1b and are not yet filed.

**Table format, because gates parse it.** `tools/queue/gates/register-queue-coverage.js`,
`register-exposure-legend.js`, `register-rows-vs-details.js` and `tools/queue/verification-record.py`
read these tables. Keep the column order. Start the status cell with the status word (bold is
fine). Escape a literal pipe inside any cell as `\|`. Give every row a `### BF-nn` detail section
and every detail section a row. Do not use the words `open` or `merged` in a status cell whose
status is something else — the exposure gate matches words.

**Audit coverage — `lib/` eslint suppressions.** All 45 suppressions under `lib/` were audited
against the line they suppress; five defects were found (BF-35 to BF-39) and the other 40 are what
they claim. Suppressions outside `lib/` (the client bundle, `tests/`) are not audited.

| rule suppressed | sites | defects found |
|---|---:|---:|
| `security/detect-object-injection` | 34 | 2 — BF-35, BF-36 |
| `no-useless-escape` | 2 | 3 — BF-37, BF-38, BF-39 |
| `no-cond-assign` | 3 | 0 |
| `security/detect-non-literal-fs-filename` | 3 | 0 |
| `no-fallthrough`, `no-unused-vars`, `detect-possible-timing-attacks`, `detect-non-literal-regexp` | 3 | 0 |

---

## 1. Register

| id | defect | where | severity | tenancy-independent | status |
|---|---|---|---|---|---|
| **BF-01** | `GET /api/v1/count/entries/where` silently matches nothing | `lib/server/aggregate.js:21` | **high** — wrong answer, HTTP 200 | yes | **merged 2026-09-18** (PR #8738, merge `d3358e91`; `bf/reads` `4772b983`); reproduced live; `count/treatments/where` was affected too |
| **BF-02** | `insulin`/`carbs` query bounds truncated by `parseInt` | `lib/server/treatments.js:259-266` | **high** — wrong answer, HTTP 200 | yes | **merged 2026-09-18** (PR #8737, merge `025f1310`; T0.5, `bf/coercion` `f829ea11`) |
| **BF-03** | Numeric filters on `devicestatus`, `activity`, `food`, `profile` match nothing | `lib/server/query.js` walker, per-collection | **high** — wrong answer, HTTP 200 | yes | **merged 2026-09-18** for `devicestatus` and `profile` (PR #8737, merge `025f1310`; T0.5, `bf/coercion` `f829ea11`); `food` and `activity` are not affected as stated, see detail; the fix costs `activity` its numeric `date` filter (BF-106) |
| **BF-11** | `treatments.duration` and `rate` have no walker entry — temp-basal filters match nothing | `lib/server/treatments.js:259-266` | **high** — wrong answer, HTTP 200 | yes | **merged 2026-09-18** (PR #8737, merge `025f1310`; T0.5, `bf/coercion` `f829ea11`); reproduced against a real `mongod` |
| **BF-12** | ~~`entries.rawbg` is coerced but is not in the model~~ — **does not reproduce**; the walker entry is `rssi`, which *is* in the model | `lib/server/entries.js:186` | none — not a defect | n/a | **closed 2026-09-15, invalid** |
| **BF-13** | API v3 `skip`/`limit` paging silently loses and duplicates documents when the whole sort chain ties | `lib/api3/generic/search/input.js` `parseSort` | **high** — silent data loss on a read | yes | **merged 2026-09-18** (PR #8738, merge `d3358e91`; `bf/reads` `5a5269a3`); reproduced through the v3 HTTP path |
| **BF-14** | API v1 `?count=0` (and `-3`, `1e2`) reaches the driver unvalidated — `.limit(0)` means *unbounded* | `lib/server/entries.js:56` + 4 siblings | **high** — on PostgreSQL an empty `200` on a glucose read; unbounded read on MongoDB | yes | **merged 2026-09-18** (PR #8738, merge `d3358e91`; `bf/reads` `06b133a7`; rule amended by PR #8748, merge `42c5e21e`, and PR #8761, merge `f1591069`); reproduced live; **v3's own validation is defective — see BF-33** |
| **BF-15** | API v3 `?fields=<dotted.path>` returns an empty document with HTTP 200 | `lib/api3/shared/fieldsProjector.js` `applyProjection` | **medium** — silently empty response to a valid request | yes | **merged 2026-09-18** (PR #8738, merge `d3358e91`; `bf/reads` `12207df3`); reproduced live |
| **BF-16** | Food quick-pick `hidden` filter compares to the **string** `'false'`; the field has no declared type and its stored type depends on the request's content type. The built-in editor is not affected: it re-sorts numerically itself and does not use the endpoint | `lib/server/food.js` `listquickpicks` + `lib/food/food.js:69` `restoreBoolValue` | **medium** — a JSON writer's quick picks vanish from `/api/v1/food/quickpicks`, which has no in-tree consumer; `restoreBoolValue` un-hides a boolean-hidden pick in the editor | yes | **merged 2026-09-20** (PR #8735, merge `ff0d506c`; `bf/food` `73495331`); reproduced live, both spellings written over HTTP |
| **BF-35** | The bolus calculator's quick-pick chooser builds its `<option>` list from the **whole food collection** but resolves the selection against the **filtered** quick-pick array. Picking one quick pick loads a different one's foods; the last entry throws; plain foods appear in the chooser | `lib/client/boluscalc.js` `loadFoodQuickpicks` | **high** — the carbs that reach the insulin calculation come from a record the user did not choose, with no error shown. Regression from `3457de5b` (2017) | yes | **merged 2026-09-20** (PR #8735, merge `ff0d506c`; `bf/food` `73495331`, found during BF-16); reproduced in jsdom, ablated six ways |
| **BF-17** | Editing a subject through the stock admin UI **persists the API access token in plaintext**, into a field the server otherwise only derives | `lib/authorization/endpoints.js:38-42` + `lib/admin_plugins/subjects.js:43` + `lib/authorization/storage.js` `save` | **high** — turns read access to the database into API access; no key required | yes | **merged 2026-09-24** (PR #8754, merge `4f705217`, head `bae655a0`) — fixed 2026-09-15 in `bf/auth` `64db1f35`, carried by `bf2/auth-hardening`; reproduced live; **existing rows still hold tokens, see the report** |
| **BF-28** | `insulinage`'s URGENT branch is unreachable — it compares against `insulinInfo.urgent`, which is never assigned, where all three sibling plugins use `prefs.urgent`. "Insulin reservoir change overdue!" can never fire, **and the reported level stays WARN for as long as the reservoir is overdue** | `lib/plugins/insulinage.js:92` | **medium** — a site-change reminder that silently never arrives, and a severity that is wrong the whole time | yes | **merged 2026-09-20** (PR #8739, merge `7a5561f4`; `bf/alarms` `8714093b`) |
| **BF-29** | An unknown name in `ENABLE` is **silently ignored** — matching is against `plugin.name` (`bwp`, `cage`, `iage`, `sage`, `bage`, **`basal`** — six), not the file name. An operator who writes `ENABLE=cannulaage` gets no plugin and no warning | `lib/plugins/index.js:140` | **medium** — an operator believes an alarm plugin is on when it is off | yes | **merged 2026-09-20** (PR #8739, merge `7a5561f4`; `bf/alarms` `99e46a52`) |
| **BF-30** | The auth-failure delay is keyed on a client-controlled value, so brute-force throttling never engages | `lib/authorization/delaylist.js` + the un-whitelisted `forwarded-for` call in `lib/authorization/index.js:9-12` (**not** `TRUST_PROXY`, which does not exist on `dev`) | **high** — restores unthrottled guessing against `API_SECRET` and tokens | yes | **merged 2026-09-24** (PR #8754, merge `4f705217`, head `bae655a0`) — fixed 2026-09-15 in `bf/auth` `a26ba416`, carried by `bf2/auth-hardening`; reproduced live; keying on the credential alone was measured to be a regression, see detail. The address key protects only once `TRUST_PROXY` is set; unset, the behaviour is 15.0.8's, with a boot warning |
| **BF-31** | A Google Home **or Alexa** request re-points the shared `language` instance and `moment`'s global locale **for the whole process**, until something changes it back. It does *not* change alarm text (measured 2026-09-15): the catalogue is read once at boot and never reloaded | `lib/api/googlehome/index.js:27` **and `lib/api/alexa/index.js:28`** + the one `language` instance at `lib/server/server.js:34` | **low–medium** — gated on the assistant plugin being enabled; reaches the assistant's own answers, not alarm text | yes | **merged 2026-09-20** (PR #8739, merge `7a5561f4`; `bf/alarms` `5dcf783f`); reproduced |
| **BF-32** | Query coercion was applied to operands that are not field values, so `find[sgv][$exists]=true` became `{$exists: NaN}` and `find[notes][$regex]=ab` became `{$regex: NaN}`. `{$exists: NaN}` is read by MongoDB as **true**, so `$exists=true` answers correctly by accident; what the coercion does on the ten walker fields is turn a `$regex` into a **server error**. The residual `$exists=false` defect that survives the fix is **BF-40** | `lib/server/query.js` `walk_prop` | low — a 500 on `$regex`, not a wrong answer on `$exists` (measured against seven live `mongod` instances) | yes | **merged 2026-09-18** (PR #8737, merge `025f1310`; `bf/coercion` `f829ea11`, found during T0.5); reproduced against seven live `mongod` instances: `$exists=true` was not inverted, see detail and BF-40 |
| **BF-33** | API v3 `?limit=0x10` passes the `API3_MAX_LIMIT` check as 16 and reaches the driver as `.limit(0)` — *no limit*; `?limit=1e2` returns one document | `lib/api3/generic/collection.js` `parseLimit` | **high** — unbounded read, HTTP 200, and the ceiling that exists to prevent it is bypassed | yes | **merged 2026-09-18** (PR #8738, merge `d3358e91`; `bf/reads` `2ecfeb53`); found while fixing BF-14, reproduced live |
| **BF-34** | `backoff()` merges its options as `{ ...config, ...defaults }`, so **every value any caller passes is discarded**. All five vendor sources configure a 2.5-minute retry interval and every one of them gets the 256 ms default — 586× faster — and `use_random_slot` is forced `false`, so a pool that fails together retries in exact lockstep | `nightscout-connect` `lib/backoff.js` | **high** — a vendor that is refusing requests gets hammered by every account at once, which is when it can least afford it | yes | **merged 2026-09-23** into Nightscout `dev` through the connector pin (PR #8752 onward); connector: released in nightscout-connect `0.1.0` (npm, 2026-09-24); Nightscout `dev` pins `0.1.0` exactly via PR #8762 (merge `153e5658`). Fix `c1cce2a` (found during T0.4), connector PR #68 (`3f73288`). On the pre-`dev` base `b77e5bb`, 100 actors delivered the same 800 requests across 3 s before and 67 s after |
| **BF-36** | The client's delta merge captured the cached array's length once and then spliced that array, so a `remove` followed by an item matching nothing read past the end and threw. The throw escapes into `dataUpdate`, which has no `try`/`catch` — the page stops advancing until reloaded | `lib/client/receiveddata.js` `mergeTreatmentUpdate` | **medium** — availability, not a wrong reading: the time-ago watchdog is on its own timer and still marks the page stale | yes | **merged 2026-09-18** (PR #8734, merge `fdd08706`; `bf/merge` `b06c6faf`, found by auditing the suppressions after BF-35); reproduced directly, ablated against the shipped shape |
| **BF-37** | `queryParms()` reads `[1]` of each `key=value` split without checking one exists, so a valueless parameter — `?debug`, a trailing `&`, `&&`, a lone `?` — throws. It is the **first statement of `client.init`**, so the page stops loading with nothing on screen but the loading message | `lib/client/browser-utils.js` `queryParms` | **medium–high** — total, silent failure to load, on a URL shape anyone can produce | yes | **merged 2026-09-20** (PR #8736, merge `2e94de1b`; `bf/parms` `522c6ffb`, suppression audit); reproduced directly |
| **BF-38** | Translation substitution loops forwards over `%1`…`%n`; `%1` is a prefix of `%10`, so the first pass rewrites the `%1` inside `%10` and leaves a stray `0`. Same prefix-order trap as sorting a text `position` | `lib/language.js` `translate` | low — **latent**: no shipped catalogue uses more than `%3` | yes | **merged 2026-09-20** (PR #8736, merge `2e94de1b`; `bf/parms` `c9a7a21c`, suppression audit); reproduced directly |
| **BF-39** | `queryParms()` replaced `_` with a space, corrupting every access token whose subject name contains one. **Measured to have no live effect**: `findSubject` matches on the last `-`-separated segment and ignores the abbreviated name the corruption lands in | `lib/client/browser-utils.js` `queryParms` | low — a real corruption absorbed by a leniency nobody chose | yes | **merged 2026-09-20** (PR #8736, merge `2e94de1b`; `bf/parms` `eb0bc918`); **reproduced against a live instance**, both spellings authorise |
| **BF-04** | API v1 has no operator allowlist — filter pass-through reaches the driver. **`$where` executes on the driver**: measured, a caller-supplied `$where` reaches `mongod` unchanged on `origin/dev` `a8888f0d` and `mongod` runs it, on a route `AUTH_DEFAULT_ROLES=readable` opens without a token | `lib/server/query.js:157` | **high** — server-side JavaScript execution, plus ReDoS / full-scan exposure | yes | **merged 2026-09-18** (PR #8743, merge `1a36f023`; `bf/operators` `3e8ce695` + `71506cf8`); reproduced against `mongod 7.0` before and after. Does not close the NoSQL-injection advisory: see BF-71 and BF-72 |
| **BF-05** | Unguarded `console.log` of every count query on the request path | `lib/server/aggregate.js:30-31` | **medium** — log noise, filter contents to stdout | yes | **merged 2026-09-18** (PR #8738, merge `d3358e91`; `bf/reads` `3b588098`) — deleted, not gated; the module has no `env` handle |
| **BF-06** | `/api/v1/entries?count=10` costs 42× a typed read | `lib/server/cache.js:73-76` | medium — CPU | yes | **merged 2026-09-20** (PR #8740, merge `49f562d8`; T0.2, `bf/cache` `ddcdb1a8`); 0.837 → 0.025 ms, response asserted identical over HTTP |
| **BF-07** | `cache.insertData` JSON round-trips the whole retained array | `lib/server/cache.js:81` | medium — 65 % of the load cycle | yes | **partly merged 2026-09-20** (PR #8740, merge `49f562d8`; T0.3, `bf/cache` `4f86bab1`); 3.75 → 2.66 ms per cycle — **devicestatus keeps its clone on purpose, see detail** |
| **BF-08** | `nightscout-connect` actors have no start jitter — a pool reaches the vendor inside one second on every restart. The aligned poll interval is not affected: all four drivers already jitter it by 18 s | `nightscout-connect` `lib/machines/cycle.js` `Init`, and `run()` | medium — thundering herd on restart | yes | **merged 2026-09-23** into Nightscout `dev` through the connector pin (PR #8752 onward); connector: released in nightscout-connect `0.1.0` (npm, 2026-09-24); Nightscout `dev` pins `0.1.0` exactly via PR #8762 (merge `153e5658`). Fix `c1cce2a` (T0.4), connector PR #68 (`3f73288`); measured at 400 actors on the pre-`dev` base `b77e5bb`, busiest second 400 → 15 |
| **BF-09** | Socket dedup uses truthiness, so a falsy value is skipped as a match key. The value at risk is not in `insulin` or `carbs`: in 277,690 corpus treatments `insulin` is never `0` (0 of 107,732) and `carbs` never (0 of 12,394). The field that actually carries the value is **`absolute`** — zero in 67,521 of 153,315, 44 % — which is the **zero temp basal**, the canonical AID suspend | `lib/server/websocket.js:538-566` (the [storage seam interface](../tenancy/nightscout-storage-seam-interface-2026-09-14.md) §4.4 cites a stale `535-568`) | **medium** — a zero temp basal is the canonical AID suspend, not an edge case | yes | open — **measured 2026-09-23** on `74fc6619` and `15.0.8` through the real socket path ([evidence](../../60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md)): treating zero as a real key value fixes 6 dedup cases (a dropped zero temp, cancel, 100 % temp, zero bolus and zero carbs) and changes no control; `bec641ca` was a rendering change and does not touch dedup. Awaiting the maintainer's choice among the options in the evidence |
| **BF-10** | `mongod` fatal-asserts at Docker's default `nofile=1024`. **Not documentation-only**: `docker-compose.yml` ships at the repository root with a `mongo:` service and **no `ulimits:` block**, on `master` and `dev` alike (both `mongo:5.0.32`) | `docker-compose.yml` `mongo` service — a one-block code landing site in the file most self-hosters actually use; operator documentation second | medium — self-hosters in containers | yes | **merged 2026-09-23** (PR #8753, merge `3a38c6f2`: `ulimits` on the bundled compose file's `mongo` service); **reproduced 2026-09-21 on `mongod 7.0.43`** and 2026-09-22 with the shipped compose file, with the full fatal-assert trace; see detail |
| **BF-40** | `find[<field>][$exists]=false` returns the documents that **have** the field, on every field, on today's release; repaired on `bf/coercion`. MongoDB reads a non-numeric operand as **true**, so the string `"false"` and the `NaN` the old walker produced both mean *exists* | `lib/server/query.js` `walk_prop` / `lib/server/query-coercion.js` `isValueLeaf` (on `bf/coercion`) + `lib/server/query.js:288` | **medium** — inverted answer, HTTP 200, on a filter any client can send; **and it refutes BF-32's stated mechanism** | yes | **merged 2026-09-18** (PR #8737, merge `025f1310`; `bf/coercion` `b7234753`); reproduced 2026-09-15 against seven live `mongod` instances (3.6.8 and 7.0.43), identical on all seven, and end to end after the fix |
| **BF-41** | ~~A reading timestamped ahead of the server clock silently disables both stale-data alarm paths, because `isStale()` compares a negative age against a positive threshold~~ — **does not reproduce as registered**. Through the shipping sandbox, `lib/sandbox.js` `lastEntry` has skipped every entry later than `sbx.time` since `556091bf` (2015, in every tag from 0.10.0), so the timeago plugin never sees a future reading. What does happen: an uploader clock running **ahead** delays the stale-data alarm by about the size of the skew (BF-95), and when no usable reading is loaded at all there is no alarm (not filed) | `lib/plugins/timeago.js:26` (`lastSGVEntry.mills >= sbx.time` early return) and `:97-98` (`isStale`), with `lib/client/index.js:918-919` and `lib/sandbox.js` `lastEntry` | none — not a defect as registered. The residual, an uploader clock running ahead delaying the stale-data alarm, is BF-95 | yes | **closed 2026-09-23, invalid** — does not reproduce as registered (reproduced-negative on `origin/dev` `74fc6619` and `15.0.8` `92d08342`, through the real sandbox with `tools/remedial/bf3/bf41-real-sandbox.js`, with a break-it that removes the `556091bf` filter and brings the symptom back; [evidence](../../60-research/remedial/bf41-future-reading-2026-09-23.md)). **Maintainer decision 2026-09-23**: closed as not reproducing (evidence §5, option 1), and no tolerance setting is added, because a tolerance would suppress a warning that fires today. The evidence §7 text ships as a 15.0.9 known issue. The queue gate `tools/queue/gates/timeago-future-reading.js` runs through the real sandbox since `b248bb73`: 8 checked / 0 failing on `a8888f0d` and `15.0.8`, and with `lastEntry`'s filter replaced by `return true` the four future-reading arms fail with the registered symptom while the controls stay green. The gate before `b248bb73` stubbed `sbx.lastSGVEntry` and was vacuous. The clock-ahead delay is BF-95; "no usable reading means no alarm" (evidence §3, F1/F2) is not filed |
| **BF-42** | `nightscout-connect` **v0.0.13** — the version `origin/master` pins, i.e. the one every current operator runs — writes vendor credentials, session tokens and patient glucose data to the runtime log **unconditionally**, with no setting that turns it off | `nightscout-connect` v0.0.13 (`b394411`): `index.js:54` (`console.log("INPUT PARAMS", spec, validated.config)` — every source, every boot, before any network call), `lib/outputs/internal.js:88`, `lib/sources/minimedcarelink/`, `dexcomshare.js`, `librelinkup.js`, `glooko`; reached via `origin/master:package.json` | **high** — credential disclosure to anywhere the log goes | yes | **merged 2026-09-23** into Nightscout `dev` through the connector pin (PR #8752, then PR #8759); connector: released in nightscout-connect `0.1.0` (npm, 2026-09-24); Nightscout `dev` pins `0.1.0` exactly via PR #8762 (merge `153e5658`). Fix: connector PR #64. `origin/master` (15.0.8) pins the v0.0.13 tag (`tools/queue/gates/connector-pin-exposure.js`, 2026-09-23). Source census of a `git archive` extraction (112 live `console.*` sites, 101 passing a non-literal argument); **not** run against a live vendor — see detail for the per-pin table |
| **BF-43** | `origin/master` forces `nightscout-connect` onto `axios` **1.16.0**, below the connector's own declared `^1.18.1`. `overrides` suppresses the `ERESOLVE` that would normally reject it, so the violation is silent | `origin/master:package.json` `overrides['nightscout-connect']`; the branches disagree four ways (`1.16.0` on master, `1.20.0` on dev and cuts 1-4, absent on cut 5) | **medium** — a silent constraint violation on the released artefact; no specific broken API identified | yes | **merged 2026-09-05** (PR #8565, merge `eedc9439`, a dependabot bump): `origin/dev`'s override is axios `1.20.0`, which satisfies the connector's `^1.18.1` at v0.0.13 and at `0.1.0`. `origin/master` is `1.16.0`: measured (`semver.satisfies('1.16.0','^1.18.1')` is `false`; master's lockfile confirms the override takes effect). Found by `tools/qc/connector-pin-agreement-gate.js` rule R5 |
| **BF-44** | `nightscout-connect`'s MiniMed CareLink source and the retired `minimed-connect-to-nightscout` derive a reading's **absolute time by different algorithms**, so the same reading is filed at a different instant across a cutover — breaking the `sysTime`+`type` dedup key and plotting the trace at the wrong time | `nightscout-connect` `lib/sources/minimedcarelink/index.js` `reassign_zone` (identity fallback when `lastConduitDateTime` is absent) vs `minimed-connect-to-nightscout/transform.js:41-85` `guessPumpOffset`/`parsePumpTime`. Present in **every** pin including v0.0.13 | **low** — the divergence needs readings from both paths, and the maintainer confirms (2026-09-22, operational knowledge) that legacy mmconnect does not work, so no cutover produces them. The connector-alone half — its identity fallback when `lastConduitDateTime` is absent — is not graded here and is worth measuring, because a *forward* shift would compound **BF-95** | yes | open — **reproduced**: both shipping implementations loaded side by side, three arms diverging by exactly the offset and two controls agreeing. The divergence is (pump offset − server timezone offset) whenever the payload timestamps carry no zone designator, which the retired package's own recorded payloads do not |
| **BF-45** | `setupMMConnect` starts the legacy MiniMed plugin whenever `MMCONNECT_*` is set, with **no check for `nightscout-connect`** — while `setupBridge` does stand down for Connect. An operator who follows ordinary staged-migration advice runs **both** ingestion paths at once | `lib/server/bootevent.js` `setupMMConnect`, on `origin/master` and `origin/dev`; compare `setupBridge` (`origin/dev:lib/server/bootevent.js:369`) | **low** — legacy mmconnect does not work (maintainer, 2026-09-22), so starting it alongside Connect produces failed logins, not double ingestion. Cut 4 removes the path | yes | open — both function bodies read in full on both refs; not run as a live double-ingestion |
| **BF-46** | **Eleven API v3 environment variables bypass `lib/server/env.js` and the settings layer entirely** and appear in no documentation — and one six-name family of them **irreversibly deletes stored documents** older than a configured age | `lib/api3/index.js:24-38` (`setENVTruthy` reads `process.env` directly, plus three Azure/lowercase spellings), `:70`, `:73-76`; `lib/api3/generic/collection.js:32`, `:129-152` (`API3_AUTOPRUNE_<COLLECTION>` for six registered collections; `deleteBefore = now − autoPruneDays×24h`, called **without `await`**) | **high** — an undocumented variable that deletes a person's glucose history, set by a spelling nobody can look up | yes | open — measured by grep and by reading the call sites; `grep -c API3_ README.md` = 0. The deletion path was **read, not executed** |
| **BF-47** | Saving a subject or role through the stock admin UI **destroys every stored field the response did not carry**: `endpoints.js` returns a `pick()`ed object, the admin plugin `PUT`s that object straight back, and `storage.save()` does `replaceOne`. `notes`, `created_at` and anything a third-party tool stored are gone, silently. A code revert does not recover the data | `lib/authorization/endpoints.js:40` + `lib/admin_plugins/subjects.js` + `lib/authorization/storage.js` `save()`, on `origin/dev` today | **medium** — silent one-way data loss on an ordinary edit | yes | **merged 2026-09-24** (PR #8754, merge `4f705217`; the admin-page fix is `7103f657`) — derived from source on `origin/dev`; **not** reproduced against a deployment. **`bf/auth` narrows this rather than introducing it** — see detail. **Maintainer decision 2026-09-23**: the allow-list is intended. A corpus check found no open-source client that stores other subject fields; the one it found sends a misspelled field (BF-89). What remains on 15.0.8 (and on `dev` until `4f705217`) is the admin page, which fetches subjects without `notes` and `created_at` and saves the whole subject back, clearing both |
| **BF-48** | `lib/plugins/webhook.js` reads four configuration variables straight from `process.env` inside the plugin factory, bypassing `env.js`, the settings layer **and** `extendedSettings` — which `findExtendedSettings` would otherwise populate for it. They are in no documentation | `lib/plugins/webhook.js:36-39` | **medium** — undocumented and unconfigurable through any documented mechanism; under `multi` every tenant's webhook posts to the same host | yes | open — found by grepping every `process.env` read in `lib/` and subtracting `env.js`; `grep -c WEBHOOK_ README.md` = 0. Not run against a live instance. The reads are in the exported factory, not at module load, so the fix is an ordinary call-site change |
| **BF-49** | `SECURE_HSTS_HEADER_INCLUDESUBDOMAINS` has **two spellings**. `env.js` reads the un-underscored one; `lib/settings.js`'s own `nameFromKey` produces `SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS`, which is accepted, stored and read by **nothing**. Five keys in the settings dictionary are dead this way | `lib/settings.js:48` (and `:49` `secureHstsHeaderPreload`, plus `insecureUseHttp`, `secureHstsHeader`, `secureCsp`) vs `lib/server/env.js:114` and `lib/server/app.js:144`; `README.md:399` documents the working spelling | low — but a tenant-admin UI generated from the settings dictionary would offer five settings that do nothing, one of them a security header | yes | open — measured by grep over `lib/`, `views/` and `static/`: zero consumers |
| **BF-50** | `README.md` documents `MONGODB_COLLECTION` as a configuration variable. **Nothing reads it.** The code reads `ENTRIES_COLLECTION` or `MONGO_COLLECTION`. An operator who sets it gets the default and no error | `README.md:240`; `lib/server/env.js:211` | low — documentation defect with no code landing site | yes | open — measured: the only occurrence of the string in the tree is the README line |
| **BF-51** | `azuredeploy.json`'s `WEBSITE_NODE_DEFAULT_VERSION` **parameter is referenced nowhere in the template**, while the `appSettings` block hard-codes the literal `8.11.1`. No Azure operator's Node version is controlled by the field that appears to control it — and cut 1's change of that parameter's default therefore has no effect on a deployed site | `azuredeploy.json`, on `origin/master`, `origin/dev` and `origin/chore/retire-jsdom` alike | medium — a one-click deployment path whose runtime knob is inert | yes | open — measured by parsing the template and counting `parameters('WEBSITE_NODE_DEFAULT_VERSION')`: **0** on both refs. **Not** reproduced against a live Azure deployment, so *why deployments work today* is an open question, not a finding |
| **BF-52** | The four age plugins **grade the level on a threshold but request the notification only while the age is exactly at the threshold hour and within its first 20 minutes** (`age === threshold` and `minFractions <= 20`), at all three levels. The server evaluates about once a minute, so the request is made about 20 times in that window; it is lost only when the server does not evaluate at all during those minutes — a restart or deploy, a host that sleeps, a stalled data load — and nothing later asks, while the pill stays red | `lib/plugins/insulinage.js:92` and the same shape in `cannulaage`, `sensorage`, `batteryage` | **medium** — reproduced, and the maintainer decided (2026-09-23) that the reminder is to be sent once even if the window is missed, which makes the current behaviour a defect. Opt-in push only; the on-screen level is unaffected | yes | **fixed 2026-09-23** on local branch `bf3/age-push-once` `896629f8` (one commit on `origin/dev` `74fc6619`, not pushed): all four plugins, all three levels; the missed reminder is requested once. Reproduced red on dev and on 15.0.8 (`cage`, `sage`, `bage`; `iage` on 15.0.8 also has BF-28). Suite 2410/0/3 on Node 20 and 22; the break-it gives 17 red with the original symptom. One `sensorage` test expectation changed (it asserted the defect) and the README's alert entries changed. **Deferred** (maintainer, 2026-09-23): not in 15.0.9; it ships in a later release, paired with BF-92, and delivery after `requestNotify` through `pushnotify` and Pushover is to be measured first ([evidence](../../60-research/remedial/bf52-age-push-once-2026-09-23.md)) |
| **BF-67** | An out-of-order alarm threshold is **silently rewritten to a neighbour ±1** and the only trace is a `console.warn` on the server. An operator who enters an mmol/L number into a mg/dL field — `BG_HIGH=14` — gets it stored as **181 mg/dL**: the alarm then fires at a number the person never chose, and nothing they can see says so | `lib/settings.js:302-324` `verifyThresholds`, called from `:298`; present on `origin/master` and `origin/dev` alike | **medium** — the guard itself is right and the silence is the defect. It is an alarm threshold for a person managing diabetes, so quietly correcting it is the wrong behaviour even when the correction is sensible | yes | open — **reproduced** in-process against the shipping `lib/settings.js` (unchanged from `v15.0.8` to `origin/dev` `74fc6619`) by `tools/queue/gates/threshold-silent-rewrite.js`: `BG_HIGH=14` is stored as 181, `BG_LOW=90` as 79, each with only `console.warn` lines; no client-side or on-screen surface reports the rewrite (grep over `lib/client/` and `views/` finds none). A `BG_LOW` of 3.9 is *not* rewritten — see BF-86 |
| **BF-69** | The Bolus Wizard's quick-pick chooser is **built exactly once, at client construction, from an empty sandbox, and is never rebuilt**. `lib/client/index.js:239` creates `client.sbx` with no data, `:323` constructs `boluscalc`, whose own init calls `loadFoodQuickpicks()` against `client.sbx.data.food` = `[]`; `:596` then REPLACES `client.sbx` on every data update and `:637` calls `boluscalc.updateVisualisations`, which does not rebuild the chooser. `loadFoodQuickpicks` has exactly ONE call site. The chooser therefore offers only "(none)" forever, for every operator, while *Add food from database* works because it reads `sbx.data.food` at click time | `lib/client/boluscalc.js` (single call site at init) + `lib/client/index.js:239,323,596,637` | **medium** — a documented feature is inert for everyone; no wrong number is shown, and the defect it masks (BF-35) is worse than itself | yes | **merged 2026-09-23** (PR #8756, merge `c11888ed`; branch `bf3/quickpick-rebuild` `83cfff14`, on top of #8735): the chooser is rebuilt when the drawer opens and only then, and its change handler is bound once. Suite 2394/0/3 on Node 20 and 22; BF-35's probes still pass; each pick enters its own carbs in a browser. The Bolus Wizard is shown only with `boluscalc` in `SHOW_PLUGINS` and to viewers who may create treatments. First found 2026-09-17 by the maintainer in a browser, reproduced on `a8888f0d` and `rc/2026-09-dev-cycle`. **Must not ship without `bf/food`** (#8735, in `dev` since 2026-09-20) — see detail. Food edits made after a page has loaded still do not reach it (BF-93) ([evidence](../../60-research/remedial/bf69-quickpick-rebuild-2026-09-23.md)). Ships in 15.0.9 (maintainer, 2026-09-23) |
| **BF-70** | `GET /api/v1/count/:storage/where` **took its aggregation pipeline from the URL**. `lib/server/aggregate.js` concatenated `opts.pipeline` — and `opts` is `req.query` — into the pipeline it ran, so a caller could add arbitrary **aggregation stages**, not merely filter operators, to a read, including stages that read collections the endpoint is not about | `lib/server/aggregate.js:21` (`opts.pipeline`), reached from `lib/api/entries/index.js:519` `count_records` | **high** — an oracle over any collection in the database, answered under HTTP 200, on the shipped default `AUTH_DEFAULT_ROLES=readable` which needs **no token**. write-capable stages are excluded only by the order in which the module assembles the pipeline, which nothing asserts | yes | **merged 2026-09-18** (PR #8743, merge `1a36f023`; `bf/operators` `52b7b640`); **reproduced 2026-09-18** through the booted v1 app against `mongod 7.0`, unauthenticated, and the same probe returns 400 after the fix. **DISCLOSURE: see detail before writing this into anything public** |
| **BF-71** | `enforceDateFilter()` applies the default date window only when **neither** `query[dateField]` **nor** `query.dateString` is present, and the test on the second is a bare **presence check**. So any `dateString` key at all drops the 4-day default: `$ne`, `$exists`, `$gte`, `$regex` were each measured doing it. The window is a paging convenience — its own source comment is `// TODO: discuss/consensus on right value/ENV?` — and **not an access control** | `lib/server/query.js:98` (`!dateValue && !query.dateString`), default set at `:47-48` (`TWO_DAYS * 2`) | **low** — a correctness and consistency defect, **not a privilege boundary**. Measured: the allowlisted, documented `find[date][$gte]=0` returns the identical record set on the identical auth, and every form is **401 under `AUTH_DEFAULT_ROLES=denied`**. It grants a caller nothing they cannot already ask for | yes | **open, found 2026-09-21.** **Reproduced** on `dev` `59430336` through the booted v1 app against `mongod 7.0.43`, unauthenticated, *with its control in the same run*. The advisory calls this PoC its primary evidence and a full-history data dump; the outcome is real but the mechanism is not a bypass — see detail |
| **BF-72** | `$regex` on a field is in API v1's accept set **by design**, and reaches `mongod` as a caller-supplied pattern with **no anchoring, length or complexity bound**. `mongod`'s `$regex` backtracks, so a suitably constructed pattern turns a collection scan into minutes of database CPU for a single short request | `lib/server/query.js` operator allowlist (`$regex`/`$options` accepted on a field); any v1 read or `/api/v1/count/:storage/where`. A documented text-search affordance also depends on `$regex` | **high (availability)** — **unauthenticated on the shipped default `AUTH_DEFAULT_ROLES=readable`**, one request, no token, and Nightscout is a screen someone watches to decide about insulin. Not a data-exposure finding: the collections the scan reaches are already readable on that default | yes | **open, found 2026-09-21.** **Reproduced** on `dev` `59430336`, 20 000 seeded entries, `mongod 7.0.43`: control **22 ms**, three catastrophic-backtracking-class patterns **60 s / 65 s / 71 s**, stable across two runs. Unchanged by #8743 — the allowlist admits `$regex` deliberately. **DISCLOSURE: see detail before writing this into anything public** |
| **BF-73** | Express's `errorhandler` is mounted **unconditionally** — the `NODE_ENV === 'development'` guard around it is commented out — so any exception that escapes to express returns an HTML page carrying the error message and a `<ul id="stacktrace">` with **absolute server filesystem paths** and the internal call chain, on a production instance | `lib/server/app.js:388-391` on `origin/dev` and `v15.0.8`, `:343-346` on `v15.0.7` — identical on all three, long-standing, not a regression | **low-to-moderate** — paths and module layout, not data and not credentials, and it costs a write credential. It is filed because the **XSS hardening in 15.0.8 added an uncaught exception path that reaches it** (in `lib/server/purifier.js`), on v1, v3 and the socket alike | yes | **open, found 2026-09-21** while measuring the purifier's bounds for the GHSA XSS pair. **Reproduced** on `dev` `59430336` against `mongod 7.0` — stack frames naming `lib/server/purifier.js` and the deployment's full directory path returned in the HTTP body. Not reachable from the unauthenticated read surface by any of seven malformed-query probes; those return handled JSON. **DISCLOSURE: mechanism and remedy are public in the evidence doc, the trigger is not** |
| **BF-74** | `PURIFIED_COLLECTIONS` in the API v3 write purifier lists five collections and omits **`settings`**, which is the sixth enabled v3 collection. `POST /api/v3/settings` therefore stores free text **verbatim**, with no comment in the file saying why | `lib/api3/shared/writePurifier.js:3-9`; `settings` enabled at `lib/api3/index.js:67` | **low** — **no first-party render path exists**: no consumer of the v3 `settings` collection appears anywhere in `lib/client/`, `lib/report_plugins/` or `views/`. It is a storage bucket for third-party apps, which render it on their own terms | yes | **open, found 2026-09-21.** **Reproduced** end-to-end on all three of `v15.0.7`, `v15.0.8` and `dev` `59430336` with a real v3 JWT: `<img src=x onerror=…>` stored unchanged on every ref, while the same payload to `/api/v3/treatments` is sanitized on the two patched refs. **No fix proposed** — whether purification is correct for a UI-configuration collection, where entity re-encoding could corrupt stored values, is a decision and not an oversight to patch blind |
| **BF-75** | `emitNotification()` in the `/alarm` Socket.IO namespace delivers with `self.namespace.emit(...)` — the **whole namespace**. Delivery is conditional on neither having sent `subscribe` nor being allowed to read. `subscribe` *does* resolve authorization and *does* compute `read` from `api:*:read`, then returns that boolean to the client and never uses it server-side. The main namespace already gets this right twelve hundred lines away, gating `dataUpdate` behind `socket.join('DataReceivers')` on the same permission | `lib/api3/alarmSocket.js:178` (the five emits), `:67` (`subscribe`), `:36` (connection accepted); contrast `lib/server/websocket.js:150` and `:791` | **high** — **CWE-862, a real authorization bypass**: an unauthenticated socket that never subscribed receives `notification`, `announcement`, `alarm`, `urgent_alarm` and `clear_alarm` — insulin doses, entering device, treatment notes and live BG — on an instance where `AUTH_DEFAULT_ROLES=denied` makes all four v1 read endpoints **401** to the same caller. On the shipped `readable` default the marginal content disclosure is **zero**, measured field by field against `treatments.json`/`entries.json`/`status.json`; what it adds there is real-time push. Proposed `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N` = **7.5** for the hardened case, 5.3 for the default | yes | **merged 2026-09-21** (PR #8745, merge `2b22c0ce`; `bf/alarm-socket-scope` measured at `012f1623`; origin's branch tip `a198e308` carries an integration merge of `dev` and was **not** re-measured). Filed as GHSA-8849-qjp5-vrrj, external report. **Reproduced** on **`v15.0.8` (= `origin/master`, what operators run) and `dev` `59430336`**, `mongod 7.0.43`, **both `AUTH_DEFAULT_ROLES=readable` and `AUTH_DEFAULT_ROLES=denied`**, all five event classes driven through the real plugin paths with the 401 control in the same run. **No shipped setting stops it** — `denied`, `AUTHENTICATION_PROMPT_ON_LOAD=true` and `ENABLE=` were each measured. **Fix shape decided 2026-09-21 by Ben West: shape B** — admit the socket to the delivery room at *connection* time when the deployment's anonymous default role already permits reading, and re-evaluate on `subscribe`; this closes the `denied` bypass identically to the stricter subscribe-and-entitled shape and changes nothing on the shipped `readable` default. **DISCLOSURE: the fix is public in `dev`, but the shipping release is still affected — see detail before writing this into anything public** |
| **BF-76** | The access-token branch of the same `subscribe` wires `socket.on('ack', …)` up with **no permission check**, while the web-client branch beside it checks `notifications:*:ack`. `resolveAccessToken` fails only for an unknown subject, so **any valid token of any role** reaches `ctx.notifications.ack(level, group, silenceTime, true)`, which silences the alarm for every viewer — and `silenceTime` comes straight from the caller with no upper bound | `lib/api3/alarmSocket.js:83` (unguarded) vs `:137-149` (guarded); `lib/notifications.js:172` (`alarm.silenceTime = time ? time : THIRTY_MINUTES`) | **moderate** — needs a credential, so not unauthenticated, but it is loss of the safety function this software exists to provide: indefinitely silencing a hypo alarm for everyone watching. `CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:N/I:L/A:H` = **7.3** | yes | **merged 2026-09-21** (PR #8745, merge `2b22c0ce`; `bf/alarm-socket-scope`). Found while fixing BF-75; **not part of GHSA-8849 as filed**. **Reproduced** as a unit against `dev` `59430336`: a token holding only `api:*:read` reached the global ack; ablating the new guard reproduces it (`expected 1 to be 0`). Authorization fixed as a separate commit; **the unbounded `silenceTime` is deliberately unbounded for now** — what a legitimately authorized client may ask for is a decision, not an oversight |
| **BF-77** | `TREATMENTS_AUTH=off` **silently suppresses the in-product "Nightscout readable by world" warning**, and it is the one configuration that most needs it. `lib/server/env.js` implements the deprecated setting by *appending* to the roles string, producing `readable careportal`; `lib/server/bootevent.js:149` decides whether to warn with an **exact string compare** against `'readable'`, which no longer matches. That configuration is world-readable *and* accepts anonymous treatment writes | `lib/server/bootevent.js:149` (`authDefaultRoles == 'readable'`) against `lib/server/env.js:187-190` on `v15.0.8`, `:195-198` on `dev` (the append). The two defect fragments are unchanged across those refs, verified fragment by fragment; the files otherwise differ (`bootevent.js` carries the debounce logging change, `env.js` the credential-coercion change) | **medium** — no new access is granted; what is lost is the only notice the operator gets, in the one case where both reads and writes are open to anyone with the URL. The warning fails open in exactly the case it exists for | yes | **merged 2026-09-21** (PR #8746, merge `74fc6619`; `bf/readable-warning` `74731433`, off `dev` `59430336`). **Reproduced** on **v15.0.8** and on `dev` `59430336`, `mongod 7.0`, three arms in one run through `GET /api/v2/adminnotifies` with an admin credential: default → `notifyCount` **1**, title *Nightscout readable by world* (**positive control**); `TREATMENTS_AUTH=off` → `notifyCount` **0** while anonymous read **200** and anonymous `POST /api/v1/treatments` **200, record stored**; `AUTH_DEFAULT_ROLES=denied` → `notifyCount` 0, correctly (**negative control**). The fix moves the decision into `worldReadableNotify(settings)` in `lib/server/bootevent.js` and asks role membership via a new `lib/authorization/defaultroles.js`, which `lib/authorization/index.js` now shares — the split is character-identical, so the auth path does not change. `readable careportal` gets its own wording, **approved by the maintainer 2026-09-21**; plain `readable` is unchanged byte for byte. 20-case `tests/bootevent-readable-warning.test.js`; **ablation** (original compare restored inside the same seam) goes red with the original symptom — 7 failing, **13 still green**, so the red is attributable. Suite 2311→**2331** passing / 3 pending / 0 failing. **Re-measured after the fix, all four arms:** `readable` → 1, text unchanged; `readable careportal` → **1**, wider text, anonymous `POST` still 200 (nothing about access changed); `denied` → 0; `denied careportal` → 0. BF-78 is not touched by this fix; BF-81 is the root both share |
| **BF-78** | The `careportal` default role is **inert unless reads are also open**, and fails silently. `lib/api/treatments/index.js:26` applies a router-wide `api.use(ctx.authorization.isPermitted('api:treatments:read'))` *before* the per-route create check at `:146`, while the `careportal` role grants exactly one permission, `api:treatments:create`. So the role can never reach the POST handler on its own. `README.md:243` says `AUTH_DEFAULT_ROLES` takes "any valid role name"; `careportal` is one of the five the product ships | `lib/api/treatments/index.js:26` vs `:146`; role table at `lib/authorization/storage.js:143`; documented at `README.md:243` | **low** — it fails **closed**, so nothing is exposed. The defect is that a documented setting does nothing and says nothing: the operator intent it most obviously expresses — close reads, let the household enter carbs without a token — is unreachable, with no error and no log line | yes | **open, found 2026-09-21.** **Reproduced** on **v15.0.8** and `dev` `59430336`, anonymous `POST /api/v1/treatments`: `readable careportal` → **200, stored** (the only working combination, and see BF-77); `careportal` alone → **401**; `denied careportal` → **401**; `denied` → 401. **Pairs with BF-77** — the only configuration in which `careportal` works is the only configuration whose warning is suppressed, so an operator chasing the second behaviour lands on the first by construction |
| **BF-79** | `socket.on('loadRetro')` emits the retained `devicestatus` window to whoever asks. It consults **nothing** — not `socketAuthorization`, not `socketAuthorization.read`, not `DataReceivers` membership — while every sibling handler in the same closure routes through `checkConditions`, which refuses on `!socketAuthorization`. The correct decision exists 460 lines below in the `authorize` handler and is never asked for. The attacker's move is **not to call `authorize` at all**: a wrong secret ends in `socket.disconnect()`, so `authorize` is a gate to walk around, not through | `lib/server/websocket.js:315` on `v15.0.7`, `v15.0.8` and `dev` `59430336` — byte-identical on all three; contrast `:269` (`checkConditions`) and `:775-802` (`authorize`) | **high on a hardened install, zero marginal disclosure on the shipped default** — and both halves were measured. On `AUTH_DEFAULT_ROLES=denied`, where all four v1 reads are **401**, an unauthenticated socket receives **24 h** of `openaps`/`loop`, `pump` (battery, reservoir, bolusing, suspended, **manufacturer, model, pumpID**) and `uploader` (battery, isCharging, **name**) — 48 h with `DEVICESTATUS_DAYS=2`, the one setting that touches this path and which **doubles** it. On the `readable` default the payload is a **strict subset** of what anonymous `GET /api/v1/devicestatus.json?count=N` already returns on the same instance: 574 records against 1 730, **0** record ids absent from the REST answer and **0** field paths present only on the socket. Proposed `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N` = **7.5** for the hardened case (8.2 counting the unthrottled amplification), **0.0** marginal for the default | yes | **merged 2026-09-21** (PR #8744, merge `a9acd313`; `bf/ws-loadretro-auth` `9765e8cd`, the exact tip measured). Filed as GHSA-gjhc-pc29-r3m6, external report. **Reproduced** on **`v15.0.7`, `v15.0.8` (= `origin/master`, what operators run) and `dev` `59430336`**, `mongod 7.0.43`, **both `AUTH_DEFAULT_ROLES=readable` and `AUTH_DEFAULT_ROLES=denied`**, with the 401 REST control and the never-emits-`loadRetro` socket control in the same run. **No shipped setting stops it** — `denied`, `status-only`, `AUTHENTICATION_PROMPT_ON_LOAD=true` and `TREATMENTS_AUTH=off` were each measured. **The advisory's range `>0.8.1` is wrong**: `loadRetro` is absent from every `0.8.x` tag and first ships in **0.9.0**, alongside the authorization it bypasses. The reply correcting the advisory's range to `>=0.9.0` and its impact claim is drafted and **not yet sent**. **DISCLOSURE: the fix is public in `dev`, but the shipping release is still affected — see detail before writing this into anything public** |
| **BF-80** | **Scoping alarm delivery to a room couples it to the failed-login delay list, and a household shares one public IP.** `authorization.resolve()` consults `shouldDelayRequest(ip)` and `await`s the accumulated penalty before returning any permissions. Once `/alarm` delivery depends on a resolved entitlement — which it must, to close BF-75 — a socket from an address that recently failed an authentication is **outside the delivery room for the length of that penalty**, and any alarm emitted in the window does not reach it. The penalty is **cumulative, 5 s per failure** (`authFailDelay`), so a misconfigured uploader retrying with a wrong API secret keeps extending it for every other device behind the same NAT address | `lib/authorization/delaylist.js` (`DELAY_ON_FAIL`, cumulative; `FAIL_AGE` 60 s) reached from `lib/authorization/index.js:155`, via `applyReadEntitlement` on `bf/alarm-socket-scope` | **medium** — an alarm a caregiver is entitled to is not delivered, silently, for tens of seconds, and the trigger is a *neighbouring device's* misconfiguration rather than anything the viewer did. Not a new exposure and not exploitable; it is the cost of the BF-75 fix | yes (once BF-75 lands) | **open, found 2026-09-21** while reviewing the BF-75 fix. **Reproduced** on the fixed build, `readable`, mongod 7.0, alarm fired 2 s after connect, **window scales with the poison**: 0 failures → received at **2.0 s** (clean control), 1 → **4.9 s**, 3 → **10.0 s**, 6 → **15.0 s**. A *shape* assertion, not a threshold. **No shape of the BF-75 fix avoids this** — any room-scoped delivery inherits it, and the pre-fix code avoided it only by not checking anything. Deliberately NOT fixed on `bf/alarm-socket-scope`: what a failed-login control should do to an unrelated read is its own decision and must not ride along on an authorization fix |
| **BF-81** | **The configuration surface has two authorization-shaped settings with adjacent names, and only one is the access-control boundary. Nothing says which.** `AUTH_DEFAULT_ROLES` is the boundary; `AUTHENTICATION_PROMPT_ON_LOAD` decides whether the web client is *asked* to log in and grants nothing. The README documents them 30 lines apart with no statement of the difference. Three consequences measured in one week: an external security reviewer competent enough to find a real authorization defect wrote a remedy keyed to the wrong one (GHSA-8849); the `/alarm` namespace they were fixing appears in **no swagger file and nothing under `docs/`**, so its protocol is defined only by observed behaviour; and `README.md:243`'s "or any valid role name" is false for the role most operators would reach for (BF-78) | `README.md:243` (`AUTH_DEFAULT_ROLES`), `README.md` (`AUTHENTICATION_PROMPT_ON_LOAD`), `README.md:247` (`TREATMENTS_AUTH`); `swagger.yaml` / `swagger.json` (no `/alarm`); `lib/settings.js:39,74` | **medium** — no code defect and nothing exposed, but it is the shared cause of BF-77, BF-78 and of a third party's non-working security patch, and it costs a reviewer's time every time somebody audits this area | yes — operators and reviewers both | **open, found 2026-09-21.** Documentation, not code. Evidence is the three consequences above, each measured elsewhere in this register rather than asserted here |
| **BF-85** | A CareLink **no-reading marker** (`sg: 0`) is stored as a glucose entry with `sgv: 0`. While it is the newest entry, the simple high/low alarms are **not evaluated**, because `simplealarms` only checks when the newest reading is above 39 mg/dL | nightscout-connect `lib/sources/minimedcarelink/index.js` `sgs_to_sgv` (no filter on `sg === 0` at `v0.0.13` or at `234d47c`); cgm-remote-monitor `lib/plugins/simplealarms.js:21` | **high** — alarm suppression for the only working MiniMed path (the legacy mmconnect bridge is reported broken). Bounded by how often CareLink puts a zero in the newest position, which is unmeasured | yes | **merged 2026-09-23** into Nightscout `dev` through the connector pin (PR #8752 onward); connector: released in nightscout-connect `0.1.0` (npm, 2026-09-24); Nightscout `dev` pins `0.1.0` exactly via PR #8762 (merge `153e5658`). Fix: connector commit `8406edf` (connector PR #64). **Read-derived**, not reproduced — neither the defect nor the fix has been run against CareLink. Present on `15.0.8` (connector `v0.0.13`); not a regression. Operators: keep pump and CGM device alarms on |
| **BF-86** | A `BG_LOW` entered in mmol/L on a mg/dL deployment — `BG_LOW=3.9` — is stored as **3.9 mg/dL with no warning of any kind**, so the low alarm can never fire. BF-67's guard only catches a threshold that is *above* its neighbour | `lib/settings.js` `verifyThresholds` (one-sided); present on `v15.0.8` and `origin/dev` `74fc6619` | **high** — a low alarm the person believes is set does not exist, and nothing on screen or in the log says so | yes | open — **reproduced** in-process against the shipping `lib/settings.js` by `tools/queue/gates/threshold-silent-rewrite.js` (the `BG_LOW=3.9` control: stored 3.9, 0 warn lines). Operators: Nightscout's thresholds are mg/dL unless `DISPLAY_UNITS`/units say otherwise — check that your alarm settings read as the numbers you meant, and keep device alarms on. Not medical advice |
| **BF-87** | Root `overrides.qs` (and `overrides.request.qs`) force **qs 6.15.1** on the whole tree. `nightscout-connect` declares `qs ^6.15.3` (v0.0.13 and `1946beb` alike), so the connector is held below its own range, and the one copy is also what express and body-parser parse query strings with. `npm audit` reports three moderate advisories against 6.15.1 | `package.json` `overrides` on `origin/master` (`v15.0.8`) and `origin/dev` `74fc6619`, from `5ab0af7a` (2026-05-10); both lockfiles resolve a single `node_modules/qs` at 6.15.1 | **medium** — the same silent-constraint class as BF-43, on the released artefact, and it pins a server-wide parser inside published advisory ranges; exploitability through Nightscout's routes is **not measured** | yes | **merged 2026-09-23** (PR #8749, merge `9fd4600e`; `bf/qs-6.16` `46b20b38`: both `qs` overrides to 6.16.0; the documented query shapes parse identically and the suite is unchanged; only malformed bracket keys change). Measured 2026-09-22: lockfiles on both refs, `npm audit --package-lock-only --omit=dev` on master's lock (GHSA-q8mj-m7cp-5q26, GHSA-x5fp-wj9c-mxmx, GHSA-4mjr-xmp4-gh2g; the last is fixed only at 6.16.0). Found while pinning the connector to 0.1.0-dev.1 |
| **BF-89** | nightscout-connect's `nightscout` source creates its reader subject on the source site with the field **`role`** instead of **`roles`**. Nightscout grants a subject's permissions from `roles`, so the subject has **none**, and the token the connector reads back grants nothing beyond what anonymous access already allows. On a default `readable` site that is enough, which hides the defect; on a site set to `denied` the source cannot read | nightscout-connect `lib/sources/nightscout.js:81` at `v0.0.13` (the release 15.0.8 pins) and `:83` at `official/dev`; present since `3b290e5` (2023-04-05) | **low** — the Nightscout-to-Nightscout source only, and only against a source site that denies anonymous read; every CGM vendor source is unaffected. Reproduced end to end (below) | yes | **merged 2026-09-23** into Nightscout `dev` through the connector pin (PR #8759, then PR #8762); connector: released in nightscout-connect `0.1.0` (npm, 2026-09-24); Nightscout `dev` pins `0.1.0` exactly via PR #8762 (merge `153e5658`). Fix: connector PR #77 (`dea2bec`, merge `b4d8d29`). **Reproduced**: the end-to-end run against cgm-remote-monitor `74fc6619` with `AUTH_DEFAULT_ROLES=denied` is recorded in connector commit `dea2bec`'s message (before: every poll 401, no entries; after: the seeded entry arrives). A subject created by an earlier connector version keeps no roles after upgrading until it is given the readable role or deleted (BF-98) |
| **BF-90** | When an alarm reaches the web client while it holds **no glucose reading**, the "disabled locally" branch of the `alarm` and `urgent_alarm` handlers reads `client.latestSGV.mgdl` from an undefined `latestSGV` and throws, so the `chart.update` after it never runs | `lib/client/index.js:1230` and `:1242`, identical on `v15.0.8` and `origin/dev` `74fc6619` | **low** — **reachable without forcing anything**, on 15.0.8 and `dev`, by any opt-in device alert at a site with no stored CGM reading, so it is not latent. It stays low because its own cost is a skipped chart redraw (and any later listener on the same event). **It loses no alarm only because the page already drops every server alarm when it holds no reading** — that is BF-92, the safety-relevant half | yes | **merged 2026-09-23** (PR #8755, merge `728351e3`; branch `bf3/alarm-no-reading` `92544d8f`): two guards per handler, the log argument and `chart.update`, because a page that never received data has no chart and throws a second time. Suite 2390/0/3 on Node 20 and 22. Reproduced in a browser on 15.0.8, `dev` and the branch with no forcing ([evidence](../../60-research/remedial/bf90-alarm-no-reading-2026-09-23.md)); first seen in the RT-D3 probe run, with the `/alarm` gate forced to deliver. The fix does not change when alarms sound (BF-92). Ships in 15.0.9 (maintainer, 2026-09-23) |
| **BF-91** | nightscout-connect's `capture` mode crashes with `MODULE_NOT_FOUND` for the `nightscout` and `dexcomshare` sources: both `require('../../trace-axios')` from `lib/sources/`, which resolves to a repository-root file that does not exist; the module is `lib/trace-axios.js`. Sources one directory deeper (`glooko/`, `minimedcarelink/`) resolve the same string correctly | `lib/sources/nightscout.js:190`, `lib/sources/dexcomshare.js:243`, on connector `v0.0.13` and `dev` `1946beb` | **low** — only the standalone `capture` command, used to record test fixtures; the plugin path Nightscout embeds and `forever` mode never load it | yes | **merged 2026-09-23** into Nightscout `dev` through the connector pin (PR #8759, then PR #8762); connector: released in nightscout-connect `0.1.0` (npm, 2026-09-24); Nightscout `dev` pins `0.1.0` exactly via PR #8762 (merge `153e5658`). Fix: connector PR #78 (`fix/trace-axios-path` `894b132`, with a test that fails on any unresolvable relative require). Reproduced by running `capture --source nightscout` (2026-09-23), and confirmed from the trees: no `trace-axios` at either root |
| **BF-92** | **A page with no glucose reading never presents a server alarm, including device alarms.** `isAlarmForHigh()` and `isAlarmForLow()` both begin with `client.latestSGV &&`, and the `alarm` and `urgent_alarm` handlers present an alarm only if one of them is true. With no reading loaded both are false, so every `alarm` and `urgent_alarm` — including pump, loop and site-change alerts that have nothing to do with glucose — is treated as "disabled locally": no sound, no banner, no title change | `lib/client/index.js:1196-1204` (`isAlarmForHigh`, `isAlarmForLow`), gating at `:1225` and `:1237`, on `origin/dev` `74fc6619`; the same code on `15.0.8` | **high** — the maintainer's position (2026-09-23) is that it is unintended for non-glucose alarms. Measured: `URGENT: Pump Reservoir Low` is presented (red title, alarm sound) on a page with 12 in-range readings, and nothing is presented on a page with none. | yes | open — **reproduced** 2026-09-23 in a browser on `15.0.8` and `dev`, with and without the BF-90 fix, by ordinary uploads of pump status with `PUMP_ENABLE_ALERTS=true` ([evidence](../../60-research/remedial/bf90-alarm-no-reading-2026-09-23.md) §1, §4). Found while fixing BF-90. **Maintainer position 2026-09-23:** non-glucose alarms (pump, loop, age) should present on a page with no reading; to ship in a later release, not 15.0.9, paired with BF-52. 15.0.9 carries it as a known issue. No fix prescribed |
| **BF-93** | **Food changes never reach an open page.** The broadcast delta that keeps open pages current covers `sgvs`, `treatments`, `mbgs`, `cals` and `devicestatus` (and `profiles` as a whole object), and not `food`. A food or quick pick written through the API, or in the food editor in another tab, reaches a page only on a full load (connect or reconnect), so an open page keeps the old food list, including an old quick-pick carb total | `lib/data/calcdelta.js` `compressArrays` (`compressibleArrays`) and `deleteSkippables` (`skippableObjects`), on `origin/dev` `74fc6619` and `15.0.8` | **medium** — the stale data feeds the Bolus Wizard's carb entry. Measured for an added quick pick; an edited carb total follows from the same path and was not run separately | yes | open — **reproduced** 2026-09-23 in a browser on `15.0.8`, `dev` and `bf3/quickpick-rebuild` alike: a quick pick added while the page is open does not arrive by broadcast, and does after a transport drop and reconnect ([evidence](../../60-research/remedial/bf69-quickpick-rebuild-2026-09-23.md) §4, §8.1). Found while fixing BF-69. No fix prescribed |
| **BF-94** | `prevBasalTreatment` is kept at **module scope**, and `tempBasalTreatment()` returns it whenever the time falls inside it. Only `profile.clear()` resets it, which runs when an instance is created, not when `updateTreatments()` replaces the treatments. So an instance that is kept and given new treatments can return a temp basal that has since been replaced | `lib/profilefunctions.js:19` (declaration), `:455-456` (the early return), `updateTreatments` at `:292-311` (clears the cache, not this), on `origin/dev` `74fc6619`; the same on `15.0.8` | **unsettled** — the server builds a new instance on every tick and is not affected. The browser keeps one `client.profilefunctions` and calls `updateTreatments` on each data update (`lib/client/index.js:1366`), so a pill or chart lookup there could show a replaced temp; **the browser was not measured** | yes | open — **reproduced at module level** 2026-09-23 on `dev` and `15.0.8`: a 1.2 U/h temp later cut by a zero temp, the same instance returned 1.2 after `updateTreatments` (expected 0), and a new instance returned the right value ([evidence](../../60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md) §3.2). Not BF-09 |
| **BF-95** | **An uploader clock running ahead delays the stale-data alarm by the size of the error.** Once the wall clock passes a future-dated reading's timestamp, `lastEntry` returns it and the timeago plugin treats it as current. With an uploader 60 minutes ahead that stops sending, the warning a correct clock raises 15 minutes after the feed stops comes about 75 minutes after it stops, on the browser path and the server push path alike. v1 entries store no server-receipt time (`lib/server/entries.js:118-126` derives `sysTime` from the reading), so an arrival-based check needs new data | `lib/sandbox.js` `lastEntry` (`notInTheFuture`), `lib/plugins/timeago.js` `checkStatus`/`isStale`, `lib/server/entries.js:118-126`; the same on `origin/dev` `74fc6619` and `15.0.8` | **medium** — the one continuous "my data stopped" detector arrives late by the skew; it does not stay silent. BF-44 is a shipping source of forward skew | yes | open — **reproduced** 2026-09-23 through the shipping sandbox and plugin, no booted server (cases F7 and F8, `tools/remedial/bf3/bf41-real-sandbox.js`, identical on `74fc6619` and `15.0.8`; [evidence](../../60-research/remedial/bf41-future-reading-2026-09-23.md) §2, §3). Split out of BF-41 when BF-41 was closed (maintainer, 2026-09-23). **Needs a design decision**: one option is a notice when readings arrive already ahead of the clock by more than a tolerance (evidence §5, option 3); the BF-41 decision of 2026-09-23 added no new warning. 15.0.9 carries it as a known issue. No fix prescribed |
| **BF-98** | **The BF-89 fix does not repair a reader subject an earlier connector already created.** `0.1.0-dev.2` looks up `nightscout-connect-reader` on the source by name and reuses it without checking its roles. Every released version creates that subject with `role` instead of `roles` (BF-89), so a site that ever tried the API-secret path against a source with `AUTH_DEFAULT_ROLES=denied` keeps getting HTTP 401 after upgrading | connector Nightscout source reader-subject lookup: `v0.0.13` `lib/sources/nightscout.js:75-77` takes the `accessToken` of any subject named `nightscout-connect-reader` without checking its roles, and `dev` `fbd4e55` does the same; `v0.0.12`, `v0.0.13` and `234d47c` create that subject without roles (BF-89) | **low** — affects only sites that already hit BF-89, and a one-time admin step on the source clears it | yes | **merged 2026-09-23** into Nightscout `dev` through the connector pin (PR #8759, then PR #8762); connector: released in nightscout-connect `0.1.0` (npm, 2026-09-24); Nightscout `dev` pins `0.1.0` exactly via PR #8762 (merge `153e5658`). Fix: the warning `f924de2`, connector PR #79. **Reproduced** 2026-09-23 (soak control (c): started on dev.1 then moved to dev.2, never synced in 4 h 20 min; [evidence](../../60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md)). **Maintainer, 2026-09-23: warn clearly, don't repair.** The connector logs one plain message naming the subject and the two fixes (add `readable`, or delete it so the connector re-creates it) when the reused subject has no roles or its reads return 401, and writes nothing to the source; the 0.1.0 and 15.0.9 release notes carry the same steps |
| **BF-99** | **A profile POSTed with a 24-hex `_id` is stored with a string `_id`, while PUT, DELETE and `find[_id]` look profiles up by ObjectId.** An edit adds a second profile and keeps the stale one, DELETE by id cannot remove the original, and `find[_id]` returns nothing | `lib/server/profile.js` `create()` (`insertMany` with `_id` as given) against `save()` (`new ObjectID`, then upsert), `remove()` and `lib/server/query.js` `updateIdQuery`; the same on `origin/dev` `1f9a9d10` and `15.0.8` `92d08342`. `chore/nightscout-modernization` `b1bdaca0` carries it too (**reproduced** 2026-09-23: 11 of 13 red on Node 22.23.2 and 24.20.0) | **medium** — every Nightscout-to-Nightscout connector sink (every connector version) and every restored export. Reports load every profile in their date range, so a stale copy is among the profiles they read; report output not measured | yes | **fixed 2026-09-23**, in review as PR #8758 (`bf/object-id-crud` head `6d120fa2`, commit `09566345`) — **reproduced** red on dev and 15.0.8 (11 of 13 new tests); suite 2399/0/3 on Node 20 and 22 against dev 2386/0/3; break-its give the original symptoms. Existing string-`_id` profiles become editable and deletable by id with no boot migration ([evidence](../../60-research/remedial/profile-object-id-2026-09-23.md)). The connector's profile update-on-change needs it (BFQ-97) |
| **BF-100** | **devicestatus, food and activity also store a 24-hex `_id` as a string.** DELETE by id leaves the string document; a food or activity PUT adds an ObjectId duplicate; devicestatus and activity `find[_id]` return nothing | `lib/server/devicestatus.js` `create` (`insertMany`), `lib/server/food.js` and `lib/server/activity.js` `create` (upsert with the id as given); the same on `1f9a9d10` and `15.0.8` | **low to medium** — reached by clients that send their own `_id` (the connector's Nightscout source passes devicestatus `_id`s through, read-derived) | yes | **fixed 2026-09-23**, in review as PR #8758 (`bf/object-id-crud` head `6d120fa2`, commit `80993afc`) — **reproduced** red on dev (27 of 31 new tests); suite 2432/0/3 and 2445/0/3 at that commit on Node 20 and 22; every hunk broken singly goes red. devicestatus has no create guard, so a devicestatus re-sent with the `_id` of a string copy is stored beside it; the connector's in-process output does not re-send (measured: strict `created_at` watermark) ([evidence](../../60-research/remedial/object-id-other-collections-2026-09-23.md)) |
| **BF-101** | **API v3's id filters do not match a string `_id`,** so records stored with a string `_id` through v1 cannot be found or deduplicated by id through v3 | `lib/api3/storage/mongoCollection/utils.js` `filterForOne` and `identifyingFilter`, shared by every v3 collection; the same on `1f9a9d10` and `15.0.8` | **low** — a legacy string-`_id` profile is invisible to v3 id lookup until it is edited through v1 | yes | **fixed 2026-09-23**, in review as PR #8758 (`bf/object-id-crud` head `6d120fa2`, commits `597e2899` and `44ac9047`) — **reproduced** through the v3 routes on dev (9 of 10 new tests red: GET and DELETE 404, PUT and POST 201 with a second record); suite 2411/0/3 and 2470/0/3 on Node 20 and 22; `explain()` on `mongo:7` keeps IXSCAN on `_id_` and `identifier_1`, no COLLSCAN ([evidence](../../60-research/remedial/object-id-other-collections-2026-09-23.md)) |
| **BF-102** | **Treatments and entries stored by 15.0.6 or earlier with their own 24-hex `_id` hold it as a string, and today's lookups miss them.** `find[_id]` returns nothing, DELETE by id removes nothing, a treatment PUT adds an ObjectId copy, and `GET /entries/<id>` answers 500 | 15.0.6 `9cd304f7` stores the string (measured); the REQ-SYNC-072 conversion that stores new ones as ObjectId first appears in 15.0.7, but `lib/server/query.js` `updateIdQuery`, `treatments.js` save and `entries.js` `getEntry` still look up the ObjectId only, on `1f9a9d10` and `15.0.8` | **low to medium** — sites running since 15.0.6 or earlier whose uploaders sent their own hex `_id`; how many do is not known | yes | **fixed 2026-09-23**, in review as PR #8758 (`bf/object-id-crud` head `6d120fa2`, commit `5581c5e4`) — **reproduced** red on dev (13 of 15 new tests); suite 2460/0/3 at that commit on Node 20 and 22; the REQ-SYNC-072 UUID path and its tests are unchanged ([evidence](../../60-research/remedial/object-id-other-collections-2026-09-23.md)) |
| **BF-103** | **Splitting a treatment by drag (Move carbs / Move insulin) stores the new record with the old time in `mills` and `date`, so IOB and COB ignore the move.** The page shows and stores the new `created_at`; the moved half is drawn at the chart's top-left with `translate(undefined, …)` console errors | `lib/client/renderer.js` split cases copy the page's in-memory treatment (15.0.8 `:877`/`:904`, 15.0.9 rc `:879`/`:906`); `lib/data/ddata.js:39-40` derives `mills` from `created_at` only when `mills` is absent | **medium to high** — wrong IOB and COB with HTTP 200 after an ordinary UI action, feeding the Bolus Wizard and BWP; reach is limited to edit-mode users who drop a treatment carrying carbs and insulin in a split zone, and the display symptom is visible | yes | **merged 2026-09-24** (PR #8760, merge `ddd9b600`; branch `bf/split-drag-time` `8d797ba4`), on the browser side: browser probe red on dev, green on the branch; suite 2453/0/3 on Node 20 and 22; 9 of 9 break-its red. **Reproduced** 2026-09-23 by hand in a browser on 15.0.8 and the 15.0.9 rc; the IOB/COB effect measured on the rc with a control (COB 0 vs 25 g, IOB 0 vs 2.49 U for the same record with and without the stale fields). Not a D3 regression: the handlers are identical on both trees ([evidence](../../60-research/remedial/bf103-split-drag-stale-time-2026-09-23.md)). A raw v1 PUT still leaves a stale `mills` ([fix evidence](../../60-research/remedial/bf103-fix-2026-09-23.md)) |
| **BF-104** | When an `/alarm` subscription fails authorization, the API v3 alarm socket **writes the credential it was sent to the server log**: the access token, the JWT, or the whole subscribe message. Anyone who can read the log sees it | `lib/api3/alarmSocket.js` (three `console.log` calls on the failure paths) on `v15.0.8` and `origin/dev` before PR #8751 | **low–medium** — only failed credentials are logged, which are often mistyped or retired, but a near-miss secret or a token that later becomes valid is exposed to log readers | yes | **merged 2026-09-23** (PR #8751, merge `4011193e`: a content-identical cherry-pick of `31c354d8` from the modernization branch). Reproduced on `dev` and `v15.0.8` by the backport triage |
| **BF-105** | Two v1 routes under the entries router pick which collection to read from a path parameter, but the router checks only the **entries** read permission, so a credential scoped to entries can read **treatments and devicestatus** through them | `lib/api/entries/index.js` `prep_storage` on `v15.0.8` and `origin/dev` before PR #8751 | **medium** — matters only on sites that deny anonymous read and hand out collection-scoped tokens; on the default `readable` everything is readable anyway | yes | **merged 2026-09-23** (PR #8751, merge `4011193e`: a content-identical cherry-pick of `d3ac8026`). Reproduced on `dev` and `v15.0.8` by the backport triage |
| **BF-106** | A numeric `date` (or `sgv`) filter on API v1 `/activity` **matches nothing and answers 200**: the schema-driven coercion that fixed BF-03 names a `collection` on each storage and, when one is named, drops `query.js`'s default walker (`date`, `sgv` → `parseInt`). `activity`'s schema entry is empty, so the bound stays a string and never matches the stored number. `devicestatus` loses the same default for `sgv` only (its schema still types `date` and `mills`) | `lib/server/query.js` `default_options` (`opts.walker = opts.collection ? { } : …`) with `lib/server/activity.js` `queryOpts.collection = 'activity'`, on `origin/dev` `ddd9b600` and the 15.0.9 candidate; not on `v15.0.8` | **medium** — wrong answer with HTTP 200 for a read filter; no write or delete is affected, and no client in the [consumer survey](../../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md) filters activity by `date` | yes (once 15.0.9 ships) | **open, found 2026-09-23** by the consumer survey. **Reproduced**: the same `GET /api/v1/activity.json?find[date][$gte]=<ms>` returns 7 records on `v15.0.8`, 0 on `dev` `ddd9b600` and 0 on the candidate, with the `find[created_at][$gte]` control at 7 on all three (mongod 7.0.43, Node 22.23.2); gate `tools/queue/gates/bf106-activity-date-coercion.js` |
| **BF-107** | A v1 treatments read whose database query fails **ends the Nightscout process**: `serveTreatments` never checks the query error, so `results.forEach` throws on `null` and the uncaught `TypeError` exits Node. A client that retries on restart keeps the site down (issue #8675) | `lib/api/treatments/index.js` `serveTreatments` on `v15.0.8` | **high** — one request takes the whole site offline, glucose display and alarms included, on the default `readable` install; mechanism only here, because it is live on the shipping release | yes | **merged 2026-09-06** (PR #8697, merge `0ab266a3`: the handler returns HTTP 500 JSON on a query error). **Reproduced** 2026-09-23 in the consumer-replay lab: the `v15.0.8` process exited on each of 3 runs, and `dev` `ddd9b600` and the candidate answered the same request 200 |
| **BF-108** | A v1 filter that lists **two or more** timestamps under the date field (`find[date][$in][]=…`) **answers 500 and does nothing**: `enforceDateFilter` calls `.replace` on every operator value that `isNaN`, and a list is an array. xdripswift sends exactly this to delete readings in bulk (`DELETE /api/v1/entries.json?find[type]=sgv&find[date][$in][]=…`, chunks of 50), so those deletes have never removed anything; one-value lists and range deletes work | `lib/server/query.js` `enforceDateFilter` on `v15.0.8`, `origin/dev` `ddd9b600` and the 15.0.9 candidate | **medium** — readings a client asked to delete stay on the site with no error the user sees; nothing is lost or written wrongly | yes | **open, found 2026-09-23** by the consumer survey. **Reproduced**: 500 `dateString.replace is not a function` for 2, 5, 20, 21 and 50 values on all three builds, entries unchanged; the one-value and range-delete controls answer 200 and delete; gate `tools/queue/gates/bf108-date-in-list.js` |
| **BF-111** | A v1 `find[_id][$in]` list **misses a record stored with a string `_id`**, for reads and for bulk deletes: `lib/server/query.js` turns each hex in the list into an ObjectId, and #8758's `matchEitherForm` widens only a plain equality. A DELETE by a list of a string-stored and an ObjectId-stored id answers 200 and removes only the ObjectId one | `lib/server/query.js` `updateIdQuery` (the `$in`/`$nin` leaves) on `v15.0.8`, `dev` `ddd9b600` and #8758 `6d120fa2` | **low** — the same records single-id lookups now reach (BF-99 to BF-102) stay out of list operations; no client in the corpus is known to send `find[_id][$in]` | yes | **open, found 2026-09-24** in the #8758 review; **fix pushed to #8758** as `1c2d1afd` (2026-09-24) (queue BFQ-111). **Reproduced**: probe P-ID-11 on all three builds, with an ObjectId-stored record in the same list as control ([lab](../../../tools/lab/object-id/results/object-id-2026-09-24.md)) |
| **BF-112** | An auth subject created with its own 24-hex `_id` is **stored with the `_id` as a string, and DELETE by that id removes nothing** while answering 200. `createSubject` inserts `req.body` as given; `removeSubject` looks up `new ObjectID(_id)` only; `saveSubject` converts. Same class as BF-99, in `auth_subjects` | `lib/authorization/storage.js` `create` and `remove` on `v15.0.8`, `dev` `ddd9b600` and #8758 `6d120fa2` (#8758 does not touch it) | **low** — admin only (`admin:api:subjects:create`); reached by a restore of subjects or a tool that sends `_id`. The access token is derived from `_id.toString()`, so tokens are unaffected | yes | **open, found 2026-09-24** in the #8758 review; **fix pushed to #8758** as `d2fd9ff6` (2026-09-24); after `dev` was merged in, create keeps only owned fields (#8754), so follow-up `ab7b22d6` (not pushed yet) keeps only the remove half (queue BFQ-112). **Reproduced**: probe P-ID-12 on all three builds: 200 and a string `_id`, then DELETE 200 with the subject still stored ([lab](../../../tools/lab/object-id/results/object-id-2026-09-24.md)) |
| **BF-114** | After an AndroidAPS user turns the loop off **with no end time** and later turns it back on, Nightscout **keeps treating the loop as deliberately offline**, so it **raises no "not looping" alert and no pump alert** until the old record leaves the treatments it loads. AAPS records the re-enable as a new "OpenAPS Offline" record (`CLOSED_LOOP`, duration 0) and does not shorten the earlier `DISABLED_LOOP` one, whose duration is open-ended (2147483647 min, or 10 years in AAPS dev). `findOfflineMarker` reads every such record as a time span and returns the newest that covers now, which is still the disable. Loop and Trio are not affected: neither sends "OpenAPS Offline", and each ends its own indefinite overrides (PR #8568, outside contributor) | `lib/plugins/openaps.js` `findOfflineMarker` (used by `statusLevel` and `lib/plugins/pump.js:335`); `lib/data/ddata.js` `processTreatments` does not close it; `v15.0.8` and `dev` `4f705217` | **high** — silences the two server alerts that say an AAPS loop or pump needs attention, with nothing shown to say so; bounded to AAPS users who used an open-ended disable. Keep the phone's and pump's own alerts on | yes | **open, filed 2026-09-25** from the open-PR triage. PR #8568 (open, 0 behind `dev`) infers the disable's end from the next running-mode record and clears the released-AAPS shape; it misses the AAPS-dev shape (`originalDuration` 0, 10-year duration) and the day-to-day report, which does not go through `processTreatments`. **Reproduced** ([probe](../../../tools/lab/aaps-offline/probe.js)): marker still on 5 h after re-enable on `v15.0.8` and `dev` for both shapes; on #8568 `de8efff0`, cleared for the released shape only; both controls behave on all three |
| **BF-115** | An entry or treatment written with an **`_id` value that is not an id** is stored with that value, because entries and treatments are written with upserts and an upsert keeps the `_id` it is given. For one such value the request answers 500 but the record is written, and the code that loads records into memory expects every stored `_id` to be an id: **the server process stops at the next data load, and again within seconds of every restart**, until the record is removed from the database. Other such values are stored without a crash, but no id route can address the record afterwards | `lib/server/entries.js` `normalizeEntryId`, `lib/server/treatments.js` `normalizeTreatmentId` (v1 POST `/entries`, POST and PUT `/treatments`); the load in `lib/data/ddata.js` `processRawDataForRuntime` (also `dataloader.js`, `calcdelta.js`, API v3 `normalizeDoc`); `v15.0.8` `92d08342`, `dev` `4f705217` and #8758 `ab7b22d6` | **high** — one write takes a site down and keeps it down; needs a credential that can create treatments or entries. No client in the corpus sends such a value (the 2026-09-25 pass). Mechanism only here: the value is not named in this public file | yes | **open, found 2026-09-25** in the #8758 freeze pass (corpus replay, reproduced independently by the review). Fix on local branch `wip/object-id-crud-fixes-2` `17add44b` (not pushed), for #8758 (queue BFQ-115). **Reproduced** on `v15.0.8` and `ab7b22d6`: the request, the stored record, the stop at the next load and again after a restart; positive control, removing the record, and the server stays up. Fix break-its: dropping either normalizer's guard or the load guard fails a named test |
| **BF-117** | An API v3 **DELETE of a record stored twice by its `_id`** (once as the 24-hex string, as 15.0.6 and earlier stored it, and once as the ObjectId a later edit added beside it) **marks or removes only one copy**; the other stays valid in v1 and v3 reads, so a treatment deleted from AndroidAPS keeps showing. On #8758 `ab7b22d6` v1 DELETE and websocket `dbRemove` remove both copies (BF-110), so v3 is the odd one out; and #8758's v3 reads and writes take the **string copy**, the older one, where 15.0.8 takes the ObjectId copy, which holds the edit | `lib/api3/generic/delete/operation.js`; `lib/api3/storage/mongoCollection/modify.js` `writeFilter`, `find.js` `findOne`/`findOneFilter` (sort by `identifier` only); `v15.0.8` `92d08342` (one copy deleted) and #8758 `ab7b22d6` (one copy deleted, and the string copy read and written) | **medium** — a deleted treatment reappears, and on #8758 v3 GET and PATCH show and edit the stale copy; bounded to records stored twice, whose number is not known (queue OID-PREVALENCE) | yes | **open, found 2026-09-25** in the #8758 freeze pass. Fix on local branch `wip/object-id-crud-fixes-2` `63dd716c` (not pushed), for #8758 (queue BFQ-117): DELETE covers every stored form; reads and writes sort `_id` descending too. **Reproduced** on both builds (corpus Q10/Q10b; review 40/40 trials of the copy picked, both storage orders, MongoDB 4.4 and 7). Not fixed there: v3 PUT/PATCH and websocket `dbUpdate` leave both copies (queue OID-V3-EDIT-MERGE, OID-WS-EDIT-MERGE) |

## 1b. Pre-release findings

Entries here **fail the register's first criterion** — they do not affect anyone running the
current release. They are recorded separately rather than by widening that criterion, because the
criterion is what makes the rest of the table mean something.

**Three kinds now live here, and the difference matters when you pick work up.** (a) Defects in
unmerged seam and tenancy branches — the original population, BF-18 to BF-27. (b) Defects in the
**modernization release train** — in a cut branch, or in the *description* of how the cuts combine
(BF-55, BF-56, BF-58 to BF-65). (c) **Gaps in shipping code that are not yet defects**: BF-53 and
BF-54 describe checks that do not exist, over behaviour that is correct today. Those last two would
be wrong to file in §1, because nothing is currently wrong for an operator — and wrong to leave
out, because the absence of the check is how a future change becomes wrong silently.

| id | defect | where | severity | status |
|---|---|---|---|---|
| **BF-21** | `bulkUpsert` on PostgreSQL takes no options argument, so the mode the caller sends is silently ignored and the write always merges. Nine call sites: **eight** send `{mode:'replace'}` and **one** — `lib/server/entries.js:168` — sends `{mode:'merge'}` deliberately, above a comment saying the two are *not* interchangeable, so "always replace" is not a safe fix: it would make `entries` start deleting stored fields | `lib/api3/storage/pgCollection/index.js` `bulkUpsert` (:286, :292) vs `lib/api3/storage/mongoCollection/modify.js:253-255` | **high** — a deleted field survives for good; the two backends drift apart with every write | open |
| **BF-22** | `updateOne` with a dotted field stores a nested object on MongoDB and a literal dotted key on PostgreSQL | `lib/api3/storage/pgCollection/index.js` + `lib/api3/generic/patch/operation.js:85` | **medium** — client-reachable via v3 `PATCH`; the PostgreSQL key is unreachable by any path lookup | open |
| **BF-23** | A duplicate-key error reaches the caller as the backend's own error class | both adapters | low — no shipping caller branches on it | open |
| **BF-25** | A credential carried in the request **body** is invisible to the tenant claim check, so tenant A's token authorises A's roles against tenant B's bound data | `lib/server/tenant-middleware.js` `presentedCredential` + `lib/authorization/index.js:40-50` | **high** — cross-tenant read *and write* with any client on default config | open |
| **BF-24** | `TRUST_PROXY=false` bypasses the guard that refuses a non-`host` `TENANT_HOST_HEADER`, letting a client choose its tenant with a header | `lib/server/env.js` `fromEnv` trust-marker check | **high** — gated on one operator config pairing, which is the pairing the guard exists to catch | open |
| **BF-26** | The HTTPS redirect rebuilds the URL from the already-rewritten `req.url`, dropping the tenant path prefix | `lib/server/app.js:132` | low–medium — availability; on by default in path mode | open |
| **BF-27** | `config()` returns one module-scope `env` object, and `setAPISecret()` deletes `API_SECRET` from `process.env` once read — so a second `config()` hands back an enclave that was never armed, and (before the rebind) disarmed the first caller's | `lib/server/env.js` module scope + `setAPISecret` | low — **not reachable in production**: one call site, `lib/server/server.js:33`. 62 test files call it | open |
| **BF-18** | Driver 7 doubles the getMore batch size when `.limit(0)` is set, abandoning `READ_OPTIONS` | `lib/storage/mongo-read-options.js` + driver 7.6.0 | medium — pre-release; compounds BF-14 | open |
| **BF-19** | `ORDER BY` reads the generated column, which orders differently from the document — breaking the DDL's own stated invariant | `lib/api3/storage/pgCollection/sql.js` `orderBy` | **high** — silently wrong order, and client-reachable via v3 `?sort=` | open |
| **BF-20** | `scalarize()` converts a `Date` bound to an ISO string, so a `Date`-valued filter matches nothing on MongoDB and everything on PostgreSQL | `lib/api3/storage/pgCollection/sql.js:27` | low — no shipping caller passes a `Date` | open |
| **BF-53** | **The documented test commands do not run the tests under review.** `npm run test:unit` (44 files) and `npm run test:integration` (89) together reach **107 of the 159** files in `tests/`, and `npm test -- tests/x.test.js` **appends** to the script's own glob rather than replacing it, so it runs the whole tree plus the named file twice | `package.json` scripts `test:unit` / `test:integration`, on `origin/dev` `a8888f0d` | **medium** — false confidence in review: `bf/food` returned 361 passing / 0 failing while never loading `tests/boluscalc.quickpick.test.js`, the only test for **BF-35**. Same for BF-36, BF-37 and the `dataloader` change on `bf/cache` | open — measured by expanding both brace lists with `shopt -s nullglob`. **Not a CI gap**: `main.yml` runs `test-ci`, which is `./tests/*.test.js`, all 159. Use `npm test` for these branches |
| **BF-54** | The two treatment-drag coordinate clamps — which bound a user-initiated rewrite of a treatment's `created_at` — have **no coverage**: both can be deleted with the D3 interaction suite fully green | `lib/client/renderer.js:766` and `:772-773` on `origin/dev` `74fc6619`. `v15.0.8` has the same clamps at `:764` and `:770-771`, written against `d3.event` because the D3 6 migration is not in it | **medium** — no defect in shipping behaviour; what is defective is the absence of any check that would notice if the clamps stopped working. A treatment's timestamp is what IOB and COB key off | open — **reproduced by deliberate breakage**: clamps removed, `tests/dependency-d3.test.js` still 24 passing / 0 failing. Instrumentation shows 25 drag invocations, all strictly inside the bounds, so the boundary is never reached. These are the exact lines the D3 6 event migration rewrote. A browser probe does catch it: deleting the clamps turns 2 of 19 of its checks red, and it finds 15.0.8 and dev identical on every drag measured ([browser evidence](../../60-research/modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md), 2026-09-22; the probe itself is untracked, so no gate runs it) |
| **BF-55** | Merging any of cuts 1-4 into `dev` **destroys the only test coverage for a bug fix shipping in 15.0.9**: cut 1 deletes `tests/clock-client.test.js` while `dev` adds 56 lines to it, and the Playwright replacement covers none of that behaviour. The production fix auto-merges silently; only its test disappears | `tests/clock-client.test.js` (deleted on `chore/retire-jsdom`, modified on `dev` by `06372e1d`) vs `tests/browser/clock-client.test.js` | **high** — the clock view is a screen someone reads at a glance to decide whether to act, and the fix is the low-and-falling concern face | open — measured: `merge-tree` reports `CONFLICT (modify/delete)`; `grep -ciE 'concern\|falling'` is **0** against the replacement with **3** on `dev`'s file as positive control. Taking either side is wrong: the deletion is right, the 56 lines must be ported |
| **BF-56** | Merging a cut into `dev` also **silently reverts dev-only changes**, because cuts 1-4 are each 133 commits behind `dev` (2026-09-22, `74fc6619`; queue RT-REBASE re-measures): the `nightscout-connect` pin rolls back from `234d47c8` to the v0.0.13 tag — past the commit that made connector debug logging opt-in, into the tree **BF-42** describes — `DEBUG_LOGGING` and `CONNECT_DEBUG` disappear, and `dev`'s bare connector `require` replaces cut 1's stand-down guard | `package.json` and `lib/server/bootevent.js` in the `dev` × `chore/retire-jsdom` merge; same shape for cuts 2, 3 and 4 | **medium** — taking either side of either conflict hunk wholesale is wrong, and one direction re-opens a credential leak | open — measured with `merge-tree --write-tree` and by reading both conflict hunks out of the written tree. **Possible the train assumes a merge of `dev` into each cut first** — nobody has written that assumption down, which is the open question attached |
| **BF-57** | A behaviour change to **carbs-on-board reporting** is shipping in 15.0.9 with no line of its own in the release decision, because the release-readiness document files it under the D3 heading. At +49/−73 it is more than twice the size of the entire genuine D3 migration | `lib/plugins/cob.js`, commit `34e9b2da`; misattributed to `48075a18` by [release readiness](../modernization/cgm-remote-monitor-release-readiness-2026-09-14.md) §2 | **unsettled** — the COB change itself was **not audited** and no claim is made that it is wrong. The defect asserted is that the largest chart-adjacent production change on `dev` is invisible to the release decision | open — measured: `48075a18` touches three files and `cob.js` is not one of them. COB feeds what a person reads when deciding about food and correction, so it warrants its own review line |
| **BF-58** | `Dockerfile` pins the **floating** `node:22-alpine` tag while `package.json` `engines` enforces a **patch** floor of `^22.23.2`, from cut 1 onward, with `runtime-policy.js` calling `process.exit(1)` on a mismatch | `Dockerfile` vs `package.json` `engines.node` + `lib/server/runtime-policy.js`, on `chore/retire-jsdom` and every cut above it | **high — the defect is the floor, not the image.** Measured 2026-09-21 with the policy stubbed out, cut 4 is 310 passing / 0 failing on 20.20.0, 22.12.0, 22.22.0, 22.23.2, 24.15.0 and 24.20.0 alike, and cut 1's Playwright suite is 21/0 on Node 20 — so `^22.23.2 \|\| ^24.20.0` rejects a working major line and eleven working patches for no measured reason. The visible symptom: `node:22-alpine` resolved to **v22.22.0** (2026-09-21), which violates `^22.23.2`, so the container's `runtime-policy.js` refuses to start: reproduced inside the image itself, exit 1. Every cut 1-5 Docker self-hoster | **fixed 2026-09-21** on the local rebase branches `rt/cut1`…`rt/cut4` (`ed21961f` and its merges up the stack, not pushed): `engines.node` is `^22.12 \|\| >=24` on the maintainer's decision, which is the root change; the Dockerfile is untouched and `node:22-alpine` boots, verified inside the image. `tools/queue/gates/node-floor-consistency.js` is 9/9 green against each prepared cut and red against the published refs. Docker is the primary distribution path, so name the symptom in the release notes |
| **BF-59** | From **cut 3 onward CI stops exercising the exact floor Node versions** the runtime policy enforces: the matrix goes from `['22.23.2','22','24.20.0','24']` to `['22','24']`, while the floor itself is unchanged | `.github/workflows/main.yml` on cuts 3, 4 and 5 | low — lost coverage, not a changed requirement: a regression precisely at the boundary the software refuses to start below would not be caught | **fixed 2026-09-21** on `rt/cut1`…`rt/cut4` (not pushed), by removing the subject: with `engines` at minor precision (`^22.12 \|\| >=24`) there is no patch boundary left to guard, so every job tests `['22','24']` and cut 3's divergence from cut 1 is gone. Measured by reading each ref's test-job matrix; `engines` byte-identical across all five cuts |
| **BF-60** | **Fifteen refs all declare `"version": "15.0.9"`** while enforcing two different Node floors — `>=20.x` on `dev` and the nine `bf/*` branches, `^22.23.2 \|\| ^24.20.0` on all five cuts — and one of those artefacts deletes two CGM ingestion paths. A support volunteer cannot triage "my 15.0.9 will not start" from the version string | `package.json` `version` at `origin/dev`, all five `chore/*` cut tips and all nine `bf/*` branches | **medium** — supportability. Compounded by cut 4's two migration shims emitting "retired in Nightscout 15.0.9" while, on the adopted train, 15.0.9 retires nothing | open — measured by parsing `package.json` at sixteen refs. The fix is one pre-release identifier per branch and should land **before** any of them is tagged |
| **BF-61** | Cut 4 turns a **missing `CONNECT_COUNTRY_CODE` into a total site outage** for every operator running the legacy MiniMed bridge — not a loss of ingestion but of the whole deployment, because a `bootError` installs `app.get('*', bootErrorView)` and returns before every router and before websocket setup. The same happens to anyone running `BRIDGE_*` and `MMCONNECT_*` together, which **works today** | `chore/mime-exposure-review:lib/server/mmconnect-connect-compat.js` with `bootevent.js:325-340`, `app.js:202`, `server.js:61` | **high** — and the shim itself states the country **cannot be inferred**, so no MMCONNECT operator can upgrade without manual reconfiguration, while no released version warns them | **fixed 2026-09-23** on local `rh/cut1-retire-legacy` (`c043fb2d`, not pushed), where the removal now lives (lifted onto cut 1), under the maintainer's decision of 2026-09-23 that **the hard stop is intended** — these settings are usually the site's primary data source, so a misconfigured one should show a page saying what to fix. On that branch the page's named fix is enough, the messages do not name 15.0.9, and the RT-5 gate checks "the boot error names the fix, and the fix boots": each stopping shape's named fix boots 200/401/401; the rewritten gate is green there and red on `rh/cut4` ([cut 1 lift](../../60-research/modernization/cut1-legacy-bridge-lift-2026-09-23.md)). **Reproduced** on cut 4 by executing the shipping shim under node in four env shapes and reading the three call sites |
| **BF-62** | Cut 4 accepts `DEXCOM_BRIDGE_USE_LEGACY` and **silently ignores it**, after `dev`'s own `DEPRECATION WARNING` told operators to set exactly that variable | `chore/mime-exposure-review:lib/server/bridge-connect-compat.js` (`bridgeUseLegacy` deleted) with the `bootevent.js` log line deleted | low — **not** a data-availability failure: Dexcom credentials are still migrated unconditionally, so ingestion continues. What is discarded is the operator's expressed intent | **fixed 2026-09-23** on local `rh/cut1-retire-legacy` (`c043fb2d`, not pushed) — the override is logged as ignored and Dexcom still migrates; regression test with break-it ([cut 1 lift](../../60-research/modernization/cut1-legacy-bridge-lift-2026-09-23.md)). Measured on cut 4 by diffing the shim against `dev`'s |
| **BF-63** | `booterror.js` **throws `TypeError` when a boot error carries no `err` key**, because `Object.getOwnPropertyNames(obj.err)` is evaluated as an argument before `pick()`'s null guard runs. Cut 4 adds the only two `bootErrors.push` sites in the tree that omit `err` — so the migration failure messages, which are the mitigation for **BF-61**, crash the page meant to display them and leave a generic 500 | `lib/server/booterror.js` (**unchanged from `dev`** — the renderer weakness is in shipping code today, awaiting a caller) reached from `chore/mime-exposure-review:lib/server/bootevent.js:330` and `:335` | **high** — the operator is told nothing at all, on the failure this batch most needs to explain | **partly merged 2026-09-23**: the renderer half is in `dev` via PR #8753 (merge `3a38c6f2`); the other site, cut 4's `pick.js`, is on the modernization branch only. **Reproduced**: five boot-error shapes through the renderer's own map with cut 4's `pick.js`. Both cut-4 shapes throw; three controls (the Mongo shape, the ENV Error shape, a real `Error`) render |
| **BF-64** | **The adopted release train specifies a combination of releases that cannot be built.** It ships cut 5 as a "dependency release" while holding cut 4 back behind a deprecation release — but cut 4 is an **ancestor** of cut 5, so that release would ship the CGM ingestion retirement one release early and *before* the deprecation release that exists to warn operators about it | [release readiness](../modernization/cgm-remote-monitor-release-readiness-2026-09-14.md) §5 and every document repeating it. **No branch is wrong** — the description of how to combine them is | **high** — it silently ships the highest-blast-radius change in the programme ahead of its own warning | open — **reproduced**: `merge-base --is-ancestor` exits 0 (cut 5 is 154 commits past cut 4), and `lib/plugins/bridge.js`/`mmconnect.js` are present on `dev` and cut 3 and **absent** on cuts 4 and 5. Must be resolved before Release 4's contents can be written down. **Maintainer direction 2026-09-23:** mmconnect is deprecated and removed as early as possible (it does not work and carries deprecated dependencies), partly in the current cycle where appropriate; with RT-4 dropped, 15.0.9's notes are the deprecation notice, so holding cut 4 behind a separate release no longer applies. The removal is lifted onto cut 1 (local `rh/cut1-retire-legacy`, 8 cherry-picks); cut 4's remainder has no CGM-path removal, and a trial merge conflicts only in legacy files and manifests ([cut 1 lift](../../60-research/modernization/cut1-legacy-bridge-lift-2026-09-23.md)) |
| **BF-65** | The adopted train **ships the leaking connector to upgraders first**: cuts 1, 2 and 3 all pin `nightscout-connect` v0.0.13 — the tree **BF-42** describes — and are scheduled first as low-blast-radius releases, while cut 4, which carries most of the redaction, is held back longest | `package.json` on the three lower cut tips, against the adopted train | medium — an operator upgrading to cut 1 or 2 moves from a leaking connector to the same leaking connector | open — the pins are measured; the ordering is **quoted** from the adopted train and was not re-derived. Cheap to remove: all three pin the v0.0.13 **tag**, so moving them to nightscout-connect `0.1.0` is the same one-line change as `dev`'s (PR #8762) |
| **BF-66** | The deployment **mints JWTs with no tenant claim**, so under `TENANCY_MODE=multi` with the default `requireTokenClaim` the tenant check refuses every token the deployment itself issues | `lib/authorization/index.js:289` (the only minting path besides `enclave.js:58`); `lib/server/tenant-middleware.js:139-151`, `:181-192`, `:208` | **medium** — **fails safe**, refusing rather than admitting, which is why it has gone unnoticed | open — **reproduced** by executing both modules with the exact payload line 289 mints: `credentialRefusal` returns "This credential does not name a Nightscout site."; the control with a `tenant` field proceeds. Must be fixed by the task that introduces the per-tenant signing key (T3.0), because that task chooses the payload |
| **BF-68** | `bf/coercion` excludes every non-value operator from type conversion, but **`$type`'s operand has a type of its own**: it takes a BSON type code or a string alias, so `find[sgv][$type]=2` must reach the server as the number `2`. Left as the string `"2"` it is rejected outright. `origin/dev` coerced it along with everything else and it worked, so excluding it turned a working request into an **HTTP 500** — a regression introduced by the fix | `lib/server/query-coercion.js` `NON_VALUE_OPERATORS`, on `bf/coercion` only | **low** — numeric BSON type codes in a v1 filter are rare, and `$type=number` (the alias spelling) was correct throughout | **merged 2026-09-18** (PR #8737, merge `025f1310`; repaired inside `bf/coercion` by `operandReaderFor` in `f829ea11`, before the PR was opened; the reader takes a digits-only operand to a number and passes aliases through). **Reproduced** against live mongod 3.6.8 and 7.0.43, identical on both: `{$type: "2"}` → *"Unknown type name alias: 2"*, `{$type: 2}` → valid. Never in any release |
| **BF-88** | The modernization branch's `TRUST_PROXY`-unset default (`395f3207`, "Restore proxy compatibility by default") **does not reproduce today's client address** in four cases: an IPv6 entry after the first in a comma-and-space `X-Forwarded-For` chain, an IPv4 address with a non-numeric port suffix, a request with no socket remote address, and a request carrying more than one forwarding-header family (dev's precedence depends on which family earlier requests used; the branch's order is fixed) | `lib/server/client-ip.js` on `origin/chore/nightscout-modernization` `b1bdaca0` against `forwarded-for` on `origin/dev` `74fc6619` | **low** — edge-case inputs, but the address is the failed-authentication delay's key and the setting is presented as compatibility-preserving, so an upgrader has no warning | open — **decided 2026-09-23 (maintainer): the cuts keep 15.0.9's unset default** — `forwarded-for`, as on `dev`; `395f3207`'s fixed-precedence normalisation is not taken, and cut 5's four `tests/client-ip.test.js` expectations are replaced by 15.0.9's when the cuts are rebased (the rehearsal's resolution). **Reproduced** by a differential probe; `bf2/auth-hardening` `8b975b41` pins dev's behaviour for the unset default, and restoring `395f3207`'s `client-ip.js` there fails exactly 7 of 48 `tests/client-ip.test.js` cases (re-run 2026-09-22). No flag for the other normalisation: with `TRUST_PROXY` unset the forwarding headers come from any peer, so neither answer is a security boundary; an address list (`proxy-addr`) is the deterministic path. The unset path is revisited when `TRUST_PROXY`'s default is flipped |
| **BF-96** | The headless client test fixture passes the bundle loader an **un-normalised path** (`tests/fixtures/../../node_modules/...`), so `benv-shim.js`'s `delete require.cache[filename]` misses the key Node stored the bundle under. A second headless suite in the same mocha process gets the cached bundle from the first, and `$` is undefined. `careportal` was the only headless suite, so nothing showed it before BF-90's test | `tests/fixtures/headless.js` and `tests/fixtures/benv-shim.js` on `origin/dev` `74fc6619` | **low** — test-only; a new headless suite fails for a reason unrelated to its subject, or passes against a stale bundle. Nothing an operator runs is affected | open — **reproduced** 2026-09-23 while writing BF-90's `tests/client.alarm-no-reading.test.js`, which clears the resolved key itself, with a comment ([evidence](../../60-research/remedial/bf90-alarm-no-reading-2026-09-23.md) §3). Found, not fixed: the one-line shim change (`path.resolve`) is left for a separate change |
| **BF-97** | **On the connector 0.1.0 line, a Nightscout source that has a profile stalls every poll.** The Nightscout source re-fetches each profile with its source `_id` on every poll, so from the second poll the sink's insert fails with a duplicate key. Up to `v0.0.13` `lib/outputs/internal.js` logged that failure and resolved the batch; from `808ab1c` (2026-09-21) the write failure fails the whole poll, and the retry backoff grows toward its 30-minute cap. Nothing is lost, but the sink runs behind with no visible error. The failing insert also logs the whole profile document each time (that part is old, `v0.0.13` too) | connector `lib/outputs/internal.js` `safePersist` and `lib/outputs/nightscout.js` `recordingError` (`808ab1c`), on connector `dev` `fbd4e55` = `v0.1.0-dev.2`; not in `v0.0.13` or `234d47c` | **high** for the affected prereleases — a Nightscout-to-Nightscout sink ran 20–35 min behind for most of a 4 h 23 min run (55 min across an outage), with no error shown to followers. It never reached a Nightscout release: 15.0.8 pins `v0.0.13`, and `0.1.0` carries the fix | **merged 2026-09-23** in connector `dev` via connector PR #79 (merge `977da8a`: `f6359b4`, `1d2ebc8`, `de3cee1`); connector: released in nightscout-connect `0.1.0` (npm, 2026-09-24); Nightscout `dev` pins `0.1.0` exactly via PR #8762 (merge `153e5658`), and pinned `0.1.0-dev.3` via PR #8759 (merge `feafa533`) before that. Never in a Nightscout release: 15.0.8 pins `v0.0.13`. **Reproduced** 2026-09-23 by a lab soak; the one-variable control (profiles excluded with `CONNECT_SOURCE_COLLECTIONS=entries,treatments,devicestatus`) polls a steady 5 min, and `v0.0.13` and `234d47c` stay current ([evidence](../../60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md)). The fix was lab-run as `9dbef9e` (`lib/` identical to `de3cee1`) for 80 min and for 46 min against the 15.0.9 candidate sinks ([evidence](../../60-research/remedial/connector-profile-sync-bounded-update-2026-09-23.md)) |
| **BF-109** | On #8758, an API v3 **DELETE or PUT by identifier writes the v1 record when a v1/v3 pair exists**, and GET still shows the v3 copy. The pair is what a v3 PUT on a string-`_id` v1 record left on every release before #8758: `{_id: X}` plus `{_id: ObjectId, identifier: X}`. `filterForOne` gains `_id` branches; reads sort `identifier: -1` and return the v3 copy, but `replaceOne`/`updateOne`/`deleteOne` do not sort and take the v1 record. DELETE answers 200, marks the v1 record invalid, and GET keeps returning the v3 copy as valid; PUT replaces the v1 record and leaves two documents with `identifier: X` | #8758 `6d120fa2` `lib/api3/storage/mongoCollection/utils.js` `filterForOne` / `identifyingFilter`, used by `modify.js` | **medium** — pre-release; the delete looks done and the record stays; AndroidAPS 4.x addresses treatments this way. Not on 15.0.8 or `dev`, where the same requests hit the v3 copy | **open, found 2026-09-24** in the #8758 review; **fix pushed to #8758** as `a2c7eb39` (2026-09-24) (queue BFQ-109). **Reproduced**: probe P-ID-10, hex and non-hex identifiers, on `v15.0.8`, `dev` `ddd9b600` and `6d120fa2`; reverting only `utils.js` on `6d120fa2` restores `dev`'s P-ID-10 cells and loses #8758's P-ID-2 fix, so both come from the same lines ([lab](../../../tools/lab/object-id/results/object-id-2026-09-24.md)) |
| **BF-110** | On #8758, **deleting a record by its hex id also deletes its twin**: where a string record and the ObjectId copy a PUT on 15.0.8 or earlier added beside it both exist, `find[_id]` returns both and v1 `DELETE /treatments/<hex>` and websocket `dbRemove` remove both. #8758's own user advice, "If you see an old copy beside the one you edited, you can now delete it", removes the edited copy too. Editing the record merges the pair into one | #8758 `6d120fa2` `lib/server/object-id-forms.js` `matchEitherForm` via `query.js`, `treatments.js` `remove`, `websocket.js` `dbRemove` | **medium** — pre-release; the copy with the user's edit is lost with the stale one, through the careportal, the web UI's Remove and oref0's `ns-dedupe-treatments.sh`. How many twins exist in real data is not known (queue OID-PREVALENCE) | **decided 2026-09-24 (maintainer): behaviour kept** — a delete by hex removes both copies, as #8758's body already says ("Deleting such a record now removes it, including a copy left by an earlier edit"). No code change; the body's advice "you can now delete it" is to be reworded to "edit either one" (queue BFQ-110). Found 2026-09-24 in the #8758 review. **Reproduced**: probe P-ID-7 on all three builds; 15.0.8 and `dev` leave one record, `6d120fa2` leaves none; v3 DELETE is unaffected ([lab](../../../tools/lab/object-id/results/object-id-2026-09-24.md)) |
| **BF-113** | On #8758, `idForms` **accepts any 12-character string**, although its comment says anything but an ObjectId or a 24-hex string throws: driver 5.9's `new ObjectId('abcdefghijkl')` succeeds, so `idForms` returns that ObjectId, its hex and the string. `profile.save` and the food, activity and profile `remove` pass non-hex ids to it without the `isHexId` guard `staleStringForms` has, so a 12-character id would upsert and delete by forms it does not name | #8758 `6d120fa2` `lib/server/object-id-forms.js` `idForms`, `lib/server/profile.js` `save`, `food.js`/`activity.js`/`profile.js` `remove` | **low** — pre-release; the v1 routes refuse non-hex ids, so only in-process callers (the connector's internal output) reach it | **open, found 2026-09-24** in the #8758 review; **fix pushed to #8758** as `dd2cf8f1` (2026-09-24) (queue BFQ-113). **Reproduced** at the helper: `idForms('abcdefghijkl')` returns three forms on `6d120fa2` instead of throwing; the effect through `profile.save` and `remove` is read, not run |
| **BF-116** | On #8758, a **devicestatus POST that re-sends a status under the `_id` it is stored with answers 500, and every new status after it in the same POST is lost**. #8758 stores a 24-hex `_id` as an ObjectId, so a re-send now collides with the stored record; the insert is ordered, so it stops at the collision. 15.0.8 stored the re-send as a second, string copy and the rest of the batch | #8758 `ab7b22d6` `lib/server/devicestatus.js` `create` (`storeIdsAsObjectIds`, `insertMany` ordered) | **medium** — pre-release; loop status silently missing for a client that re-sends; a client that retries on 500 re-sends statuses already stored. No AID uploader in the corpus sends a devicestatus `_id` (Loop sends `identifier`; Trio and AndroidAPS send none); a restore or echo tool would | **open, found 2026-09-25** in the #8758 freeze pass. Fix on local branch `wip/object-id-crud-fixes-2` `c3a34bac` (not pushed), for #8758 (queue BFQ-116): a re-send is answered with the stored `_id` and not written, the rest is stored, and a duplicate key is accepted only for a status sent with its own `_id`. **Reproduced** (corpus Q2b; ablation of `devicestatus.js` to `dev` restores 15.0.8's cells); the same 500 and loss already happen on 15.0.8 when the stored copy is a string |

### BF-18 · the read bound is abandoned on `.limit(0)`

`mongo-read-options.js` = `Object.freeze({batchSize: 1000})` exists because **driver 7 stopped
sending a default `batchSize`** — measured and confirmed: drivers 5 and 6 send `batchSize=1000`
unprompted, driver 7 sends none and lets the server fill to the 16 MB wire limit. The constant is
load-bearing, not cargo.

It stops holding when `.limit(0)` is also set. Requested `getMore` batch sizes, same constant:

```
v5.9.2    1000 x40                          holds
v6.21.0   1000 x40                          holds
v7.6.0    1000 2000 4000 8000 16000 32000   ABANDONED
```

**The `.limit(0)` path is BF-14's path and only BF-14's path.** `findFiltered` calls `.limit()`
only when a caller supplied one, and v1 supplies `opts.count ? parseInt(opts.count) : undefined`
— so `.limit(0)` is reached by `?count=0` and by any unparseable `?count=` (`NaN` →
`toSafeInt(NaN, 0)`). An absent `?count=` never calls `.limit()` and the bound holds. So the two
defects compound on the same request: `?count=0` removes the document limit *and* dismantles the
memory bound that would have made the resulting read survivable.

*Not shipped*: `origin/dev` has `mongodb ^5.9.2` and no `mongo-read-options.js`. Both arrive on
`chore/nightscout-modernization` (`b8fd24c6`). Caught before release.

*Fix*: none needed here. Fixing **BF-14** makes `.limit(0)` unreachable through the API and closes
this as a side effect. Recorded anyway because `findFiltered` is a published interface — a future
caller passing `limit: 0` re-opens it, and `toSafeInt(o.limit, 0)` makes `0` the fallback for
unparseable input. A defensive `if (limit > 0)` in `findFiltered` would also do it.

**With BF-14's fix (merged via PR #8738), stated narrowly.** `.limit(0)` is not reachable
through the v1 API, through the six v1 storage `list()` helpers, or through v3's `?limit=`
(BF-33). The driver-7 batch behaviour itself was **not** re-measured: `origin/dev` pins
`mongodb ^5.9.2` and has no `mongo-read-options.js`, so it cannot be observed there.

**`findFiltered` does not exist on `dev`**, so the suggested defensive guard has no landing site
on that branch. The `dev` equivalent is `lib/api3/storage/mongoCollection/find.js` `findMany`,
whose `toSafeInt(args.limit, 1000)` returns `0` for a literal `0` and then calls `.limit(0)`.
**That path was left alone** — `parseLimit` can no longer produce `0`, so it is unreachable from
the v3 API, but `findMany` is a published interface and a direct caller passing `limit: 0` still
gets an unbounded read. It belongs with whoever owns the seam's limit translation.

*Evidence*: [readOptions across the seam](../../60-research/tenancy/seam-readoptions-2026-09-15.md) §2,
`tools/qc/readoptions-arm.js`, three driver versions against a real mongod.

*Unexplained*: the doubling is measured on the wire, not traced to a line in the driver. That
establishes when it changed, not why.

### BF-19 · the index accelerator changes an answer in `ORDER BY`

The emitted DDL states its own invariant in capitals:

> **THE COLUMNS BELOW ARE AN INDEX ACCELERATOR. THE DOCUMENT IS THE RECORD.**
> Dropping every generated column must not change an answer.

`lib/storage/filter.js` holds that invariant on the `WHERE` side deliberately and demonstrably —
`$exists` always reads `doc #> '{path}'` because a column built from `->>` cannot tell an absent
key from an explicit null, and the randomised differential agrees 3000/3000.

`orderBy()` chooses between **the same two branches** and they do not order the same values the
same way. Identical values in two fields of the same documents, one with a generated column
(`sgv`) and one without (`noise`):

```
postgres sort sgv   (COLUMN)  005 004 003 002 006 001
postgres sort noise (jsonb)   005 004 002 006 001 003
mongod   both fields          004 005 006 001 002 003
```

Three orders where there should be one. The cause is that the typed column is SQL `NULL` for an
absent key, for an explicit null **and for every value of the wrong type**, collapsing three
distinct things into one bucket that then sorts together.

**Client-reachable**: v3's `parseSort` puts the client's unvalidated `?sort=<field>` first in the
chain, so `sql.js`'s own justification — *"every sort this code path issues is on a field that is
one type in practice"* — describes today's callers, not today's reachable requests.

*Corroborated independently.* [`tools/qc/typeguard-arm.js`](../../../tools/qc/typeguard-arm.js)
reached the same defect from the other direction, comparing one field across both branches and
mongod: on single-typed data the shipped translation matches mongod **exactly**, the only one of
five strategies that does; on mixed-typed data a string `sgv` sorts *first* where MongoDB sorts it
last. Two harnesses, two fixtures, one defect.

*Sizing holds the grade down, and it is a deadline rather than a reprieve*: the emitted manifest
flags no ambiguous field on `entries`, the only collection T2.5 implements. `NSCLIENT_ID` is
flagged on `devicestatus`, `profile` and `treatments` — so the exposure arrives **with T2.6**,
which is defined, deliberately unscheduled, in the
[execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) Phase 2.

*Fix* — **PRESCRIBED, NEVER RUN. Read this as a proposal, not a solution.** See
[the ordering design](../tenancy/nightscout-seam-ordering-translation.md) §3. Restricting sortable fields to
declared single-typed ones makes the adapter's existing assumption checkable; the alternative is a
type-bucketed sort key, which is real work and still does not handle arrays.

- The ordering design's §3 (*"Sub-problem B — cross-type ordering · open, and harder than it
  looks"*) carries a **recommendation (option O2) conditional on a corpus measurement**, not a
  settled decision.
- O2 is **client-visible**: a v3 request sorting on an undeclared field stops being answered. That
  is a behaviour change a migrating tenant must be told about, not a silent internal fix.

*Evidence*: [T2.5 backend verification](../../60-research/tenancy/t25-postgres-backend-verification-2026-09-15.md) §6,
`tools/qc/pg-backend-arm.js`; and [ordering design](../tenancy/nightscout-seam-ordering-translation.md) §3.1b.

### BF-20 · a `Date`-valued filter bound silently inverts

`scalarize()` converts a JavaScript `Date` to an ISO string before it reaches the adapter. A
`gte <Date>` bound against an ISO-string `created_at` therefore matches **nothing on MongoDB**
(BSON compares only within a type, and Date is not String) and **everything in range on
PostgreSQL** (where both sides are now text). This is divergence class B moved into the value
adapter, where `typedRef()`'s type-bracketing `CASE` cannot see it.

*Not reachable today*: every shipping caller of `findFiltered`, `count` and `deleteMany` was
checked — `lib/server/query.js` emits epoch numbers or ISO strings, never a `Date`. Recorded
because the adapter is a published interface and the next caller may not.

### BF-21 · `bulkUpsert` ignores the mode every caller asks for

`mongoCollection/modify.js` `bulkUpsert(col, ops, options)` takes an options bag whose `mode`
defaults to `'replace'`. `pgCollection/index.js` `bulkUpsert(ops)` **takes no options parameter at
all** and always writes in merge mode.

Measured on one stored document carrying `stale: 'was-here'`, upserted with a document that does
not carry it:

```
bulkUpsert(ops)                      mongod: stale removed   postgres: stale SURVIVES
bulkUpsert(ops, {mode:'merge'})      mongod: stale survives  postgres: stale survives   agree
bulkUpsert(ops, {mode:'replace'})    mongod: stale removed   postgres: stale SURVIVES
```

**Caller census.** Measured by reading each of the nine `bulkUpsert` call sites in `lib/` on
`crm-seam` `81a1f6ce` (read, not grepped: this codebase's leading-comma style puts the options
argument on the continuation line, so a `grep -rn bulkUpsert` hit shows only the opening line):

| mode passed | sites |
|---|---|
| `{mode:'replace'}` | `treatments.js:31`, `:120`; `activity.js:61`, `:102`; `food.js:64`, `:122`; `profile.js:101`; `authorization/storage.js:143` — **eight** |
| `{mode:'merge'}` | `entries.js:168` — **one**, deliberately |
| no options | **zero** |

- **The exception is the dangerous one.** `lib/server/entries.js:168` passes
  `{ mode: 'merge', ordered: true }` deliberately, above a comment saying the two modes are *not*
  interchangeable because that path was `updateOne`+`$set` and a wholesale replace would delete
  stored fields. "Always replace" is therefore not a safe fix: it would make the
  highest-write-volume collection start deleting stored fields.
- **Why it is dormant.** `lib/storage/postgres/generated/` holds `entries.sql` alone, so `entries`
  is the only collection with a PostgreSQL schema, and its single caller happens to request the one
  mode the PostgreSQL adapter hardcodes. The backends agree by coincidence.
- **`ordered: true` is silently dropped too**, by the same missing parameter. It agrees today only
  because the PostgreSQL loop happens to be sequential.
- **The code comment says the right thing and the code beneath it does the opposite.**
  `pgCollection/index.js:275-279`: *"`mode` carries the same difference it does on the other
  backend and **must not be defaulted away**"* — followed at `:286` by `bulkUpsert (ops)` with no
  options parameter and at `:292` by `write(asAst(op.filter), op.doc, 'merge')`, a literal.
- **Scope**: the silent merge reaches `profile` (basal rates, insulin sensitivity, carb ratios) and
  `authorization/storage.js` (subjects and roles), not only `activity` and `treatments`. Not
  separately reproduced on those collections; the mechanism is the one measured above.

**Eight of the nine shipping callers pass `{ mode: 'replace' }` explicitly** and the argument
reaches nothing.

The consequence is an **unremovable field**: any key a client deletes from a treatment, activity,
food, profile or subject document stays in the PostgreSQL row for good. Nothing errors, nothing
logs, and the two backends drift further apart with every write.

*Not yet live, and the deadline is known*: **the exposure arrives with T2.6**, the same deadline as
BF-19 (a defined, deliberately unscheduled task in the execution plan's Phase 2).

*Fix* — **PRESCRIBED, NEVER RUN.** Give the PostgreSQL `bulkUpsert` the same `(ops, options)`
signature and **thread the existing mode through**, or make it refuse a mode it cannot honour.
**Replace is already implemented**: `write(ast, doc, 'replace')` emits
`$N::jsonb || jsonb_build_object('_id', doc -> '_id')` and `replaceOne` already uses it, so the
change is a parameter and a literal. **Its smallness is an argument for doing it before a
migration, not after.**
Silently downgrading a replace to a merge is the one option that should not survive review.

> **A canary is worth more than the fix here**, because the fix is easy to apply and easy to apply
> *wrongly*: an assertion that every `bulkUpsert` call site's declared mode is the mode the adapter
> actually executes, run against both backends. Without it, "always replace" passes review.

*Evidence*: [the write path across the seam](../../60-research/tenancy/seam-write-path-2026-09-15.md) §2,
`tools/qc/write-arm.js`, 23 agree / 4 differ / 0 vacuous.

### BF-22 · a dotted field in `updateOne` stores two different documents

`updateOne(identifier, setFields)` becomes `$set` on MongoDB, where a dot is a **path**. The
PostgreSQL merge treats the same string as a **literal key**:

```
setFields = { 'nested.leaf': 7 }
  mongod     …,"nested":{"leaf":7},…
  postgres   …,"nested.leaf":7,…
```

The PostgreSQL document then holds a key no path lookup will find — not `doc #> '{nested,leaf}'`,
not a generated column, not a client walking the object.

*Reachability*: `lib/api3/generic/patch/operation.js:85` passes the client's PATCH body to
`updateOne`, so this is reachable through `PATCH /api/v3/<collection>/<identifier>` **subject to a
validation layer that was not audited** — which bounds the claim and should be checked before this
is graded any higher. `lib/api3/generic/delete/operation.js:86` passes a fixed
`{isValid, srvModified}` and is safe.

MongoDB's behaviour is not obviously correct either; a client sending `{"nested.leaf": 7}` may
have meant a literal key. The defect is that the backends answer differently and neither refuses.

### BF-23 · the duplicate-key error class crosses the seam

```
mongod     MongoServerError: E11000 duplicate key error collection: …
postgres   DatabaseError: duplicate key value violates unique constraint "entries_pkey"
```

Both refuse the duplicate, which is what matters. But an error class is a driver object, and the
seam exists so that driver objects do not reach callers. `err.code === 11000` is the standard
MongoDB idiom for "already exists" and would silently stop being true.

*Low on evidence*: `grep` for `11000`, `E11000` and `MongoServerError` across `lib/` finds no
caller branching on it. Recorded because the interface is published.

### BF-25 · a body-borne credential is invisible to the tenant claim check

`presentedCredential` decides whether a request carries a credential at all. It reads the
`Authorization` header, `?token=`, `?secret=` and the `api-secret` header — and **not**
`req.body`. Its own comment explains why, and the explanation is the defect:

> `req.body` is deliberately not consulted. This middleware mounts above the body parsers, so a
> token in a body is not visible yet … an opaque credential is exactly the case the
> `requireTokenClaim` default refuses.

It is not refused. `present = false` classifies the request as **anonymous**, and an anonymous
request is passed through. Later, `lib/authorization/index.js:40-50` reads `req.body.token` and
`req.body[0].token` (and the `secret` equivalents) and resolves them against the **process-wide**
`storage.subjects`. `lib/api/entries/index.js:43` mounts a body parser on exactly that route.

Measured on one middleware instance, victim host `bar`:

```
tenant foo's JWT as ?token=          -> 403
the IDENTICAL JWT in the JSON body   -> 200, bound to tenant bar, token intact
```

Same for an opaque access token, `{secret:…}` and `[{secret:…}]`. So tenant A's credential
authorises A's roles against **tenant B's** data — read and write.

*Verified independently at both halves before publishing*: `presentedCredential` does not read the
body, and `lib/authorization/index.js` does.

*Tempering, and it is real*: `fromEnv` already warns at boot that `TENANCY_MODE=multi` is not safe
to serve two people from until T3.3–T3.5 land. This is a pre-release defect on an unfinished mode,
not something shipping to self-hosters.

*The most dangerous part is the comment*, because it tells the next reader this case is already
handled. Fix the sentence even if the code takes longer.

*Regression test to write when fixing* — **not written**: start the real authorization stack with
two tenants' subjects and assert A's token cannot read B's entries. The two halves were established
separately — middleware pass-through measured live, process-wide subject resolution read from
source — and that end-to-end test is the gap.

> **D14 does not close this.** Per-tenant JWT signing
> closes the *signed-token* vector completely and demonstrably. **BF-25's actual vector is an
> opaque access token in the request BODY**, which carries no signature for a per-tenant key to
> fail: `presentedCredential` (`tenant-middleware.js:104-129`) deliberately does not read
> `req.body`, while `apiSecretFromRequest` (`lib/authorization/index.js:72-92`) and the token
> extractor (`:41-47`) do. A body-only credential returns `{present:false}`, passes the check, and
> resolves against the process-wide `storage.subjects` array. **Killing the bug class requires D14
> *and* scoping the subject store under RLS.** The code already knows this —
> `tenant-middleware.js`'s header says `requireTokenClaim` stays a knob *"now waiting on whichever
> task scopes the subject store"*.

*Evidence*: [tenant resolution, adversarial](../../60-research/tenancy/tenant-resolution-adversarial-2026-09-15.md) C1.

### BF-24 · `TRUST_PROXY=false` defeats the forwarded-host guard

> **BF-24 gates a deliverable.** Path-prefix multitenancy over websockets is only achievable by
> having the reverse proxy assert the tenant in a header derived from its own location block (T3.5
> in the execution plan) — which is precisely the mechanism this defect makes bypassable. Decided
> 2026-09-15 (maintainer): **land BF-24 before publishing the nginx recipe**, rather than ship a
> documented configuration that is known to be defeatable.

`fromEnv` refuses a `TENANT_HOST_HEADER` other than `host` with
`if (trust.legacyForwardedHeaders) throw`. That marker is only set on the **compatibility** trust
function — `TRUST_PROXY` unset or empty. `compileTrust('false')` returns a bare `() => false` with
no marker, so the guard never fires:

```
TRUST_PROXY=false  TENANT_HOST_HEADER=x-forwarded-host
Host: foo…   X-Forwarded-Host: bar…    ->  200, bound to bar
```

The client picks its tenant with a header, on another tenant's hostname. The pairing is
contradictory — trust nothing, then read a forwarded header — which is precisely what the guard
exists to catch.

*Fix* — **none prescribed.** A starting point, not tried: refuse the pairing at boot rather than at
request time, because a contradictory configuration is contradictory before any request arrives.

*Evidence*: same report, H3.

### BF-26 · the HTTPS redirect drops the tenant path prefix

`lib/server/app.js:132` builds `https://${host}${req.url}` and is mounted **below** the tenant
middleware, which has already stripped the prefix from `req.url`:

```
GET /foo/api/v1/entries?count=10
  -> Location: https://apex.org/api/v1/entries?count=10   (slug `api` -> 404)
```

`INSECURE_USE_HTTP` defaults false, so in path mode this is on by default. Availability rather
than isolation. *Fix*: use `req.tenantPathPrefix` or `req.originalUrl`.

*Evidence*: same report, M2.

## 1c. Missing capabilities

Not defects — **absent features** with a bounded, measured scope that ship to every operator and
are landable independently. Kept separate so §1's criterion ("a defect in the current release")
keeps meaning something.

| id | capability | where | scope | status |
|---|---|---|---|---|
| **CAP-01** | **Base-URL / sub-path mounting.** Nightscout cannot be served from a sub-path — `apex.org/nightscout/` behind an `nginx` `proxy_pass` — because nothing in the tree resolves URLs relative to a mount point | client call sites + redirect + Socket.IO client option | 6 client sites, 1 redirect, 1 socket option | open |
| **CAP-02** | **No importer, and no Mongo→PostgreSQL loader.** The outbound half is built — `exportTenant` is a streaming server-side cursor in one repeatable-read transaction that declares its covered-table list before any row — and there is no counterpart anywhere | `lib/admin/platform-store.js:386` (export exists) vs `lib/admin/`, `bin/`, `tools/` (no import) | one loader, plus whatever decides the BSON→jsonb transform (see BF-19/BF-20/BF-21) | open |

### CAP-01 · sub-path mounting

**There is no base-URL support at all.** No `baseUrl`, `basePath` or `SCRIPT_NAME` anywhere in
`lib/`, `views/` or `static/` — measured 2026-09-15. `env.settings.baseURL` exists but is used
only to build *outbound* callback URLs (`lib/plugins/pushover.js:45`), never for anything the
browser loads.

The long-standing reputation of this as a swamp is not borne out; the sites are enumerable:

| site | what it hardcodes |
|---|---|
| `lib/client/index.js:61` | `'/api/v1/status.json'` |
| `lib/client/careportal.js:398` | `'/api/v1/treatments/'` |
| `lib/client/boluscalc.js:544` | `'/api/v1/treatments/'` |
| `lib/client/boluscalc.js:598` | `'/api/v1/food/'` |
| `lib/client/hashauth.js:198` | `'/api/v1/verifyauth'` |
| `lib/client/adminnotifiesclient.js:17` | `'/api/v1/adminnotifies'` |
| `lib/server/app.js:132` | the HTTPS redirect rebuilds from `req.url` — **this is BF-26**, and it is the one part of CAP-01 that is a defect rather than an absence, so it can land first and on its own |
| Socket.IO client | connects to the default `/socket.io/` |

**This is a single-tenant capability and it is the wrong tool for tenant discrimination.** Getting
sub-path mounting right does not make path-prefix *tenancy* work over websockets, because a
Socket.IO handshake carries the engine path and that path is a client option — see T3.5 in the
[execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md). Path-as-tenant needs the
proxy to assert the tenant in a header regardless of how good base-URL support becomes. Keeping
the two apart is what makes each of them small.

*Requested by*: the maintainer, as a long-standing goal predating this programme.


### CAP-02 · no importer, and no Mongo→PostgreSQL loader

**Measured 2026-09-15** on `crm-seam` `81a1f6ce`: grep across `lib/admin/`, `bin/` and `tools/`
for an importer, a loader, or a `mongoexport`/`mongodump` consumer outside vendored
`node_modules` returns nothing that loads data *in*. The one hit —
`tools/rehearse-database-upgrade.py:76`, which shells out to `mongodump` — is a Mongo→Mongo
5→6→7→8 upgrade and backup-restore rehearsal, not a seam loader. It is worth citing as prior
art for the rehearsal shape, and it is not the missing piece.

`exportTenant` was read verbatim, including the `onCollection` comment explaining why an export
must declare its own coverage before emitting rows.

**Why this is a capability and not a defect**: nothing is wrong; a thing that hosted-tenant
onboarding needs does not exist. It is filed because the execution plan currently lists per-tenant
export under "Endpoints (proposed, to be argued)" — it is **implemented** — and says nothing about
import, so the asymmetry is invisible to a reader of either document. The transform the loader
would use is itself unsettled: see the measured correction in
[the hosted migration plan](../../40-migration/mongodb-to-postgres-hosted-2026-09-15.md) §4.3, where
`scalarizeDoc` was shown to turn `Long`, `Decimal128`, `Binary`, `Int32` and `Timestamp` into jsonb
**objects**, which the generated columns then read as SQL `NULL` with no error.

*Blocks*: any hosted-tenant onboarding. *Related*: BF-19, BF-20, BF-21, T2.6.


## 2. Detail

### BF-69 · the quick-pick chooser is built once, from nothing, and never rebuilt — **merged 2026-09-23** (PR #8756)

Found 2026-09-17 by the maintainer in a browser.

The Bolus Wizard's quick-pick dropdown offers only `(none)`. The food records are present —
`client.sbx.data.food` holds them, and *Add food from database* lists them correctly, because
`fillForm` reads the sandbox at click time. The chooser does not, because it is populated once and
never again.

Measured 2026-09-17, dev-mode instances, identical 8-record seed, driven through Chrome:

| build | `sbx.data.food` | chooser after clicking the Bolus Wizard |
|---|---:|---|
| `a8888f0d` (dev) | 8 | `["(none)"]` |
| `rc/2026-09-dev-cycle` (8 units incl. `bf/food`) | 8 | `["(none)"]` |

**Mechanism.** `lib/client/index.js`:

```
:239  client.sbx = sandbox.clientInit(client.ctx, client.now);   // EMPTY
:323  client.boluscalc = require('./boluscalc')(client, $);      // -> loadFoodQuickpicks(), reads []
:596  client.sbx = sandbox.clientInit(...);                      // replaced, WITH data
:637  client.boluscalc.updateVisualisations(client.sbx);         // does NOT rebuild the chooser
```

`git grep loadFoodQuickpicks` finds the definition and **one** call site, at construction. So the
chooser is built from zero records before any data has arrived, and nothing rebuilds it.

> **SEQUENCING CONSTRAINT — this fix must not ship before `bf/food` (#8735).** Met: #8735 has been
> in `dev` since 2026-09-20.
>
> The same one-line change was applied to `a8888f0d` **without** `bf/food` and measured: the
> chooser then offered **eight** entries — every plain food plus the quick pick the user
> deliberately hid — and selecting them produced **five** `Cannot read properties of undefined
> (reading 'foods')` page errors.
>
> BF-35's dose consequence is latent today *only because this defect hides it*. Repairing the
> chooser alone converts a high-severity latent defect into a live one, in a bolus calculator.
> Ship BF-69 with BF-35, or after it — never before.

**What an operator sees.** The Bolus Wizard's quick pick list is empty, so saved quick picks cannot
be used at all; foods have to be added one at a time from the database instead. Nothing displays a
wrong number — the feature simply does not work. None of this is medical advice; if you rely on
quick picks for meal dosing, raise it with your care team as well as your settings.

**Merged 2026-09-23** via PR #8756 (merge `c11888ed`; branch `bf3/quickpick-rebuild` `83cfff14`, one
commit on `74fc6619`, which carries #8735; [evidence](../../60-research/remedial/bf69-quickpick-rebuild-2026-09-23.md)).
The chooser is rebuilt in `prepare()`, when the drawer opens, and nowhere else: an option's value is
an index into the quick-pick array, so rebuilding on a data update while a pick is selected would
move the index under the selection, which is BF-35's failure class. The `change` handler is bound
once at construction; a one-line version that only calls `loadFoodQuickpicks()` from `prepare()`
leaves the binding inside `loadFoodQuickpicks` and stacks one more handler per open (4 after 3
opens, measured). Suite 2394/0/3 on Node 20 and 22,
exactly +8. In a browser each pick enters its own carbs (45, 70, 20 g), hidden picks are not
offered, and BF-35's probes still pass. The Bolus Wizard is shown only when `SHOW_PLUGINS` lists
`boluscalc`, and only to a viewer who may create treatments. A food changed after a page has loaded
still does not reach that page until it reconnects: that is BF-93, not this entry.

### BF-01 · `count/entries/where` silently matches nothing — **merged 2026-09-18** (PR #8738)

`aggregate.js:21` calls `find_options(opts)` with **one argument**, so the collection's
`queryOpts` never arrive and `lib/server/query.js` falls back to its defaults — `dateField:
'date'`, no `useEpoch`. The two paths then inject different types for the same window:

```
list  path (useEpoch:true):  {"date":{"$gte":1789099222823}}              <- number
count path (defaults)     :  {"date":{"$gte":"2026-09-11T04:00:22.824Z"}} <- ISO string
```

`entries.date` is declared `number`, and **MongoDB compares only within a BSON type**, so the
injected two-day window excludes every document rather than bounding it. The endpoint returns
`200` with a count of zero.

*Evidence*: [seam interface](../tenancy/nightscout-storage-seam-interface-2026-09-14.md) §4.3.1, verified by
running `query.js` directly. Independently reconfirmed as a general class by the
[three-arm validation](../../60-research/tenancy/seam-filter-ast-three-arm-validation-2026-09-14.md) §3 class B.

*Fix, merged via PR #8738*: `bf/reads` `4772b983`. `aggregate()` now calls **`api.query_for(opts)`** — the same
function the matching list endpoint uses — rather than passing `queryOpts` as a second copy that
has to be kept in step. No fallback to `find_options(opts)`: a collection that registers
`aggregate` without a `query_for` should fail loudly, because a silent fallback is the defect.

*Reproduced live.* `GET /api/v1/count/entries/where` returned `200 []` with
20 entries stored. **`count/treatments/where` was affected too**, and worse: the defaults put the
window on `date` rather than on `created_at`, so the filter lands on the wrong field entirely.
And on **entries only**, a request that names its own bound (`?find[date][$gte]=`) was already
correct, because `default_options` happens to set `walker = {date: parseInt, sgv: parseInt}` — so
the defect fires on entries when the client supplies *no* date constraint, which is the default
and commonest shape. [Report](../../60-research/remedial/bf01-13-14-15-read-defects-2026-09-15.md) §1.

### BF-02 · `insulin` and `carbs` bounds truncated

**Merged 2026-09-18** via PR #8737 (merge `025f1310`); repaired by plan T0.5 on `bf/coercion` `f829ea11`, emitter `tools/nsschema/emit/coercion_emit.py`, write-up in [T0.5](../../60-research/remedial/t05-schema-driven-coercion-2026-09-15.md).

`treatments.js` coerces query values through a hand-maintained per-collection `walker`:

```js
walker: { insulin: parseInt, carbs: parseInt, glucose: parseInt, ... }
```

`specs/nsschema/treatments.model.json` declares `insulin` and `carbs` as `number`, not integer.
So `find[insulin][$gte]=1.5` becomes `{"insulin":{"$gte":1}}` — **a query for boluses of at
least 1.5 units returns boluses of 1.0 units.**

**This is a data-correctness defect with review implications.** Anyone using the API to review
therapy data — a report tool, a clinician export, a caregiver checking what was delivered —
gets records that do not match what they asked for, with no error. It warrants a release note
rather than a silent fix. It is not, in itself, advice about dosing, and nothing here should be
read as such; the point is narrower and worse — **the data returned does not answer the
question asked.**

**Measured**, not asserted: `treatments.insulin` was observed as **142,360 fractional values
against 2,791 integer ones** across 11 sites — 98 % of its non-null values are fractional. So
`parseInt` on the bound is not a rounding nicety.

*Evidence*: [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) §3.4, and
[the coercion drift measurement](../../60-research/remedial/query-coercion-drift-2026-09-14.md) §2 Tier 1.

### BF-03 · Numeric filters that silently match nothing

**Merged 2026-09-18** via PR #8737 (merge `025f1310`), repaired by plan T0.5 on `bf/coercion` `f829ea11` — `devicestatus` (99 fields) and `profile` (10) are typed from the schema, as are the fields `entries` and `treatments` were missing. The fix drops `query.js`'s default walker for a collection that names a schema, which costs `activity` its numeric `date` filter: that is BF-106. Write-up in [T0.5](../../60-research/remedial/t05-schema-driven-coercion-2026-09-15.md).

**`food` and `activity` are not affected in the way this entry's title says:**

* **`food` reaches `lib/server/query.js` at no point.** `lib/server/food.js` exposes `list(fn)`, `listquickpicks(fn)` and `listregular(fn)` — none takes query options — and `lib/api/food/index.js` passes none. v1 `/food` accepts no filters at all, so there is no under-coercion to fix. (Its numeric fields are also `['number','string']` unions in the model, because the built-in client writes form-encoded; that is BF-16.)
* **`activity` has no numeric field to fix.** Its model has exactly two leaves, `_id` and `created_at`, both strings. The collection is open-bodied, so a deployment may hold numbers there, but nothing declares them and the table will not guess. It is wired to the table with a legitimately empty entry, so it starts working the day the model gains a field.

The walkers on 15.0.8:

| collection | `walker` |
|---|---|
| entries | 7 fields, all `parseInt` |
| treatments | `insulin carbs glucose` → `parseInt`; `notes eventType enteredBy` → regex |
| profile | `{}` — empty |
| **devicestatus, activity** | none of their own; they inherit `query.js`'s *default* walker, `{ date: parseInt, sgv: parseInt }`, because neither sets `walker` and `default_options` fills one in |
| **food** | none, and no query options reach it (above) |

A field with no `walker` entry stays a **string**, and MongoDB's type ordering means a numeric
field never matches a string bound. So on `devicestatus` and `activity` **every numeric filter
other than `date` and `sgv` matches nothing and returns 200**:

```
devicestatus  uploader.battery $lt=50   ->  {"uploader.battery":{"$lt":"50"}}   <- still a string
entries       delta            $gte=1.5 ->  {"delta":{"$gte":"1.5"}}            <- still a string
```

**Fixing this is user-visible in the good direction**: queries that silently returned nothing
start returning rows. Release-note it, so it arrives as a fix rather than as a surprise.

*Fix*: plan T0.5 — emit a coercion table from `specs/nsschema/*.model.json` (a sixth emitter,
`tools/nsschema/emit/coercion_emit.py`, `make schema-emit`) and drive the walker from it, instead
of four hand-maintained lists that drift. Merged via PR #8737.

**The gap is 158 disagreements** — 147 under-coercions, 8 over-coercions, 1 stale entry, and 2
collections with no model at all. Graded by corpus evidence in
[the coercion drift measurement](../../60-research/remedial/query-coercion-drift-2026-09-14.md) §2, because
they are **not** 158 equivalent bugs: `entries.sgv` is declared `number` but was observed as
895,418 integers and **zero** fractional values, so truncating its bound harms nobody today.

> **Three-arm validation.** T0.5 is a v1 bug fix and also a
> **precondition for the seam's backend-equivalence claim**: with correctly-typed values, all
> three arms agree 3000/3000; with mistyped ones, four divergence classes open, two of which
> produce *different data* depending on which backend a deployment runs.
> See [three-arm validation](../../60-research/tenancy/seam-filter-ast-three-arm-validation-2026-09-14.md) §4.

### BF-14 · `?count=0` is an unbounded read — **merged 2026-09-18** (PR #8738)

API v1 builds its limit in five places with one expression:

```js
limit: opts && opts.count ? parseInt(opts.count) : undefined
```

A truthiness test **on a string**, then `parseInt`. `'0'` is a non-empty string, so it passes the
test; `parseInt` yields `0`; and **MongoDB defines `.limit(0)` as "no limit"**. `?count=0` returns
the whole collection. Measured on a ten-document collection: `count=0` -> 10 rows.

Two more from the same expression: `count=-3` silently returns 3 documents (MongoDB reads a
negative limit as legacy single-batch semantics), and `count=1e2` returns **one** document
because `parseInt('1e2')` stops at the `e`.

Not a seam regression — `origin/dev` chains `this.limit(parseInt(opts.count))` and reaches the
identical driver call.

*Do not copy v3's validation*: v3's `parseLimit` bounds-checks the raw string with `isNaN`/`<=`
and then converts with `parseInt(_, 10)`; the two readings disagree, so `?limit=0x10` passes the
ceiling as 16 and arrives at the driver as `.limit(0)`. That is
**[BF-33](#bf-33--v3s-limit-has-the-same-hole--merged-2026-09-18-pr-8738)**, found while fixing this one.

*Fix, merged via PR #8738* (`bf/reads` `06b133a7`), in two layers: a `validateCount` middleware in
`lib/api/index.js` in front of every v1 route, and `lib/server/count.js`, one reading of the rule,
used by the six `list()` helpers and by `profile.list()`, so that a caller reaching the storage
modules directly cannot produce `.limit(0)` either. **No upper bound was introduced**, because the
census below records `count=100000` and `count=9999999` being sent deliberately. Measured before
the fix, 24 documents stored: `count=0` -> 24 rows, `count=abc` -> 24 rows, `count=1e2` -> 1 row,
`count=-3` -> 3, `count=0x10` -> 16 (v1's `parseInt` has no radix), `count=2.5` -> 2.

*The rule on `origin/dev` `153e5658`* (read from `lib/api/index.js` and `lib/server/count.js`;
PR #8738 as amended by PR #8748, merged 2026-09-23, and PR #8761, merged 2026-09-24):

- **Reads (`GET`/`HEAD`)**: `count` must be a whole number, 0 or greater, otherwise `HTTP 400`.
  `count=0` with a `find` that bounds one date field from both sides returns the whole window;
  `count=0` without such a window is dropped, so the endpoint's default applies (setting
  `API_V1_COUNT_ZERO_WINDOW`, default `true`; with it `false`, `count=0` returns `[]`). A whole
  number followed by `?` and other text, the shape oref0 sends, reads the number (setting
  `API_V1_COUNT_LEADING_NUMBER`, default `true`; with it `false`, `400`). Both tolerated shapes
  answer with a deprecation warning.
- **Deletes**: `count` must be a whole number, 1 or greater, otherwise `HTTP 400`.
- **Saves and updates** ignore `count`.
- `lib/server/count.js` answers a zero it is handed directly with no documents and never calls
  `.limit(0)`.

*Also relevant to the seam*: `findFiltered` falls back to `toSafeInt(o.limit, 0)`, and `0` is the
value that means unbounded. `findMany`, in the same file, defaults to `1000`.

*Evidence*: [limit and projection](../../60-research/tenancy/seam-limit-and-projection-2026-09-14.md) §2,
`tools/qc/shape-arm.js`, against a real mongod.

*Compounds with [BF-18](#bf-18--the-read-bound-is-abandoned-on-limit0)*: the same `.limit(0)`
that makes the read unbounded also makes driver 7 abandon `READ_OPTIONS`, so the batch size
doubles as the read runs. Fixing this entry closes that one — **narrowly**. See BF-18 for what was
and was not established.

**Graded high** because the answer differs by backend. Measured end to end through the shipping
`lib/server/entries.js` `list()`: `?count=0` returns **10 rows on MongoDB and 0 rows on
PostgreSQL** — an empty `200` on a glucose read. `?count=abc` behaves identically, because
`parseInt` yields `NaN`, which passes the `!== undefined/null` gate and reaches
`toSafeInt(NaN, 0)`. And `?count=-3` is a `2201W` — an HTTP 500 — against 3 rows on MongoDB.

*Reachability* (census, 2026-09-14): `tools/qc/v1_count_census.py` over 10 client projects:
**274 `count=` occurrences, no literal `count=0`**. 86 % are literals (`1 … 9999999`); 9 % are
computed at request time, which is where the exposure sits — nothing bounds a computed count away
from zero, and `oref0` has four such sites. An unbounded read is not a novel load for a server whose
clients already send `count=100000` and `count=9999999` deliberately; on MongoDB alone it returns
no wrong data. The later consumer survey found two clients that do send `count=0` or a count with
trailing text (GluPredKit and oref0), which is what PR #8761 tolerates
([consumer survey](../../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md)).

### BF-15 · `?fields=` with a dotted path returns `{}` — **merged 2026-09-18** (PR #8738)

v3 projects in two stages. `storageProjection()` is handed to the driver, so MongoDB's
dotted-path rules apply and a **nested** document comes back. `applyProjection(doc)` then deletes
any **top-level** key not string-equal to something the client typed. A dotted request survives
stage one and is destroyed by stage two:

```
?fields=uploader.battery
  _id 1  from driver           {"_id":1,"uploader":{"battery":80}}
         after applyProjection {}          <- driver returned uploader; DESTROYED
```

The data is read, paid for, and discarded. The client gets `200` and an empty document.

`uploader.battery` is the canonical nested field in Nightscout and `devicestatus` is the
collection people query for it, so this is an ordinary request, not a contrived one.
Comma-separated top-level fields are unaffected, which is why it has gone unnoticed.

*Fix*: `applyProjection` must compare on paths rather than top-level keys — keep a key when any
requested field equals it or is prefixed by it plus `.`, and prune within the subtree. Either
that, or reject a dotted `fields` with `HTTP 400` rather than answering `200` with nothing.

*Fix, merged via PR #8738*: `bf/reads` `12207df3` — the first option, path comparison with subtree pruning.
The prune recurses into **array members** the way the driver's own dotted projection does, so
`?fields=foods.name` works as well as `?fields=uploader.battery`. Comma-separated top-level fields
take exactly the path they took before. Reproduced live before the fix: `200` with `{}`.
[Report](../../60-research/remedial/bf01-13-14-15-read-defects-2026-09-15.md) §4.

*Evidence*: [limit and projection](../../60-research/tenancy/seam-limit-and-projection-2026-09-14.md) §3.3,
produced by running the shipping `fieldsProjector.js` against real mongod documents.

*Checked*: the system fields `storageProjection` adds and `applyProjection` removes are **not**
dead work — `col.resolveDates(doc)` consumes them in between
(`lib/api3/generic/search/operation.js:46-47`).

### BF-29 · a misspelt or file-named `ENABLE` entry disables a plugin silently

```
lib/plugins/index.js:140   return enable && enable.indexOf(plugin.name) > -1;

lib/plugins/insulinage.js:9          name: 'iage'
lib/plugins/boluswizardpreview.js:11 name: 'bwp'
lib/plugins/cannulaage.js:10         name: 'cage'
```

`ENABLE` is matched against the **registered plugin name**, which for five of the alarm plugins
differs from the file name. An unknown entry produces no warning, no log line and no error — the
plugin is simply absent.

**Why this is a defect and not documentation.** The failure is invisible in exactly the direction
that matters: an operator who intended to enable an age or bolus-wizard alarm sees a working site
with that alarm permanently off. Nothing on the status page distinguishes "not enabled" from
"misspelt".

**Found independently twice**: two harnesses built to exercise these alarm plugins both measured
them as inert before the naming rule was noticed.

*Fix*: warn at registration for any `ENABLE` entry matching no plugin name, and suggest the
nearest registered name.

**Merged 2026-09-20** via PR #8739 (merge `7a5561f4`; `bf/alarms` `99e46a52`). Scanning every
plugin module `lib/plugins/index.js` requires and comparing the file name to the `name:` it
registers gives **six** mismatches, including `basalprofile` → `basal`. The warning is
suggestion-only on purpose: warning about *every* unmatched entry produces **six warnings on a
stock install**, because `ENABLE` also carries features that are not plugins (`delta`,
`devicestatus`, `food`, `cors`) and plugins registered on only one side of the client/server
split. A test walks `lib/plugins/*.js` and fails if a seventh mismatch is added without an entry
in the table.

*Evidence*: [alarm-critical slice](../../60-research/tenancy/alarm-critical-slice-2026-09-15.md),
[ns-evaluator spike](../../60-research/tenancy/ns-evaluator-spike-2026-09-15.md),
[BF-28/29/31 alarm delivery](../../60-research/remedial/bf28-29-31-alarm-delivery-2026-09-15.md) §2.

### BF-28 · `insulinage` can never raise an urgent alarm

One identifier, and the plugin's most important branch is dead:

```
lib/plugins/insulinage.js:92    if (insulinInfo.age >= insulinInfo.urgent) {
lib/plugins/insulinage.js:93      sendNotification = insulinInfo.age === prefs.urgent;

lib/plugins/cannulaage.js:87    if (cannulaInfo.age >= prefs.urgent) {
lib/plugins/cannulaage.js:88      sendNotification = cannulaInfo.age === prefs.urgent;
```

`urgent` is set on **`prefs`** (`:19`, `sbx.extendedSettings.urgent || 72`), never on
`insulinInfo`. So line 92 evaluates `age >= undefined`, which is always `false`, and the urgent
branch is unreachable — while line 93, one line below, reads `prefs.urgent` correctly. The three
sibling age plugins (`cannulaage`, `sageage`/`sensorage`, `batteryage`) all use `prefs.urgent` on
both lines.

**Consequence**: a person who has set an urgent insulin-reservoir age threshold never receives the
urgent notification. The warning branch is unaffected, so the failure is partial and quiet — the
plugin looks like it works.

*Found*: incidentally, during the `ns-evaluator` spike (T4.4), while ablating alarm producers —
not looked for. Pinned by a check in that harness: at 72 h the plugin requests nothing; at 48 h it
requests WARN.

*Fix*: `insulinInfo.urgent` → `prefs.urgent`. One identifier, and it matches three siblings.

This branch has never executed in any deployment, so repairing it starts emitting an URGENT level
that no operator has seen, on a threshold they may have set years ago. It is release-noted as a
behaviour change, not shipped as a typo fix.

**Merged 2026-09-20** via PR #8739 (merge `7a5561f4`; `bf/alarms` `8714093b`), with a release
note. Measured through the real sandbox at four ages: 72 h requested **nothing** before and the
URGENT overdue notification after. At **80 h**, and at every age past the threshold, the plugin
reported level **WARN** rather than URGENT before the fix, so the severity was wrong for as long as
the reservoir stayed overdue, not only during the hour the notification would have fired. **No grace period**, argued from evidence: the notification is already gated on the
operator having set `IAGE_ENABLE_ALERTS`, README documents `IAGE_URGENT` as issuing exactly this
warning, `cannulaage` has always fired on the identical default of 72, and a grace keyed on the
threshold having been set explicitly would leave the most exposed operators — the ones who
enabled alerts and trusted the default — exactly where the bug left them.

*Evidence*: [ns-evaluator spike](../../60-research/tenancy/ns-evaluator-spike-2026-09-15.md),
`tools/qc/ns-evaluator-arm.js`,
[BF-28/29/31 alarm delivery](../../60-research/remedial/bf28-29-31-alarm-delivery-2026-09-15.md) §1 and §4.

> **Two things a release note for this must state (from the semver review):**
>
> 1. **The push alarm is opt-in and OFF by default.** `iage.getPrefs` sets
>    `enableAlerts: sbx.extendedSettings.enableAlerts || false`, the notification is built only
>    under `if (prefs.enableAlerts && sendNotification && insulinInfo.minFractions <= 20)`, and
>    `IAGE_ENABLE_ALERTS` defaults to false. A note saying "operators will start receiving an alarm
>    they have never received" is **wrong for most households** — it reaches only deployments that
>    turned alerts on.
> 2. **What *does* reach everyone is the pill.** `insulinInfo.level = levels.URGENT` is assigned
>    inside the property producer, **outside** the `enableAlerts` guard, and `updateVisualisation`
>    reads it and sets `pillClass` to `urgent`. So on every deployment the on-screen Insulin Age
>    pill turns urgent-red once the reservoir passes `IAGE_URGENT`, with no opt-in. That is the
>    change to describe first, and it is a *visual* change, not a sound.
>
> **And the notification is requested only in one window, not continuously** —
> `sendNotification = insulinInfo.age === prefs.urgent` is exact equality and this fix did not
> touch it. That is **BF-52**, family-wide and older than this entry.

### BF-04 · No operator allowlist on API v1

`lib/server/query.js:157` builds the filter with `traverse` type-coercion, injects a date
constraint, and **returns it to the driver with no operator allowlist**. Whatever
`find[x][$op]` a client sends reaches MongoDB — `$where`, `$expr`, an unbounded `$regex`.

**Severity.** Measured on `origin/dev` `a8888f0d` against `mongod 7.0`: a caller-supplied
top-level `$where` operand reached the driver unchanged, and the driver **executes it**.
Server-side JavaScript is enabled by default in `mongod`, the top level of `find` is never walked
by the type coercer, and the route is gated only on `api:entries:read` — which
`AUTH_DEFAULT_ROLES=readable`, the shipped default, grants without a token. This is code execution
against the database, as well as ReDoS and full-scan exposure.

**Fix, merged 2026-09-18 via PR #8743** (merge `1a36f023`; `bf/operators`, queue item P0-K), two
commits split at the revert boundary: `3e8ce695` refuses `$where`/`$function`/`$accumulator` with
their own message and adds the shared 400 responder; `71506cf8` is the allowlist proper. The seam
branch's `fromMongo` (commit `68ffbd66`) repairs the same defect structurally — an AST that cannot
represent an unlisted operator is the allowlist — and
`lib/storage/assert-no-query-javascript.js` is carried across byte-identical at the same path, so
landing this ahead of the seam costs the seam branch nothing.

- **The accept set is the seam's, exactly** — `$eq $ne $gt $gte $lt $lte $in $nin $exists $regex`
  (`$options`) on a field, `$and`/`$or` at the top including the indexed form Trio sends. Not
  trimmed to the census's measured seven, because the census measured client *source*. Matching the
  seam makes this one narrowing instead of the first of two.
- **It refuses one operator that works on 15.0.8** — `$expr`, reachable through `/api/v1/profiles/`.
- **`$type` is allowed**, the one departure from the seam's set: `readTypeOperand()` (from #8737)
  makes `find[sgv][$type]=2` arrive as the number `2`, without which the request is an HTTP 500
  (measured against mongod 3.6.8 and 7.0.43; BF-68). `$type` executes nothing and reads nothing
  outside the document. When the seam lands its AST needs a `$type` node, or v1 narrows by one
  operator then. `$not` and `$text` stay refused. Report §2.2.
- **PR #8737 alone does not refuse `$where`.** `$where` is in that branch's `NON_VALUE_OPERATORS`
  table as an exemption from conversion, not a refusal. Top-level and `$or`-wrapped `$where` build
  byte-identically on `dev` and on `bf/coercion`; the only rows that differ are `$where` and
  `$regex` nested under a field, which `mongod` rejects, so the delta is inert.

**It does not close the reported NoSQL-injection advisory.** Of that advisory's three
proofs-of-concept only `$where` is refused. The other two are filed and reproduced with controls:
**BF-71** (the date window) is `low` and not a privilege boundary — the allowlisted, documented
`find[date][$gte]=0` returns the identical records on the identical authorisation, and every form
is 401 under `AUTH_DEFAULT_ROLES=denied`; **BF-72** (`$regex`) is an availability defect, measured
at 60–71 s of database CPU against a 22 ms control, and is open.

*Evidence*: {M} §6.5; seam interface §8.2;
[BF-04/BF-70 report](../../60-research/remedial/bf04-bf70-operator-allowlist-2026-09-18.md).

### BF-05 · Debug logging on the count request path — **merged 2026-09-18** (PR #8738)

```js
console.log('$match query', query);
console.log('AGGREGATE', groupBy);
```

Unguarded, on both `dev` (`a8888f0d`) and `chore/nightscout-modernization` (`0a4109f6`), so
every `/api/v1/count/*` request writes the constructed filter to stdout. Two problems: it is
noise the modernization branch's own quiet-logging work (`c2ac743c`) set out to remove, and a
filter can carry values a deployment would rather not have in its logs. **Route through the
existing logger at debug level, or delete.**

*Fix, merged via PR #8738*: `bf/reads` `3b588098` — **deleted**. `aggregate.js` has no `env` handle, so gating
them on `env.debug.logging` would mean threading `env` through a shared module for a debug print,
and `/api/v1/echo/*` already exists for inspecting how a query string becomes a filter.
[Report](../../60-research/remedial/bf01-13-14-15-read-defects-2026-09-15.md) §2.

*Same shape, not fixed*: `lib/authorization/storage.js:113` (present on `bf/auth` too, by grep) has an unguarded
`console.log('Loading', opts)` on the auth-storage read path. It logs query options rather than
user-supplied filter values, so it is left for an operator's judgement rather than given an id.

### BF-06 · Untyped `/api/v1/entries` read costs 42×

`?count=10` costs **0.83 ms** without `find[type]` and **0.02 ms** with it, for a byte-identical
response, because `ctx.cache.getData('entries')` deep-clones the whole 48-hour array before
anything is sliced. *Fix*: slice first, then clone the slice — the documents handed out are
still clones, so the defensive property is preserved. *Evidence*: {R} §12.2. Plan T0.2.

**Merged 2026-09-20** via PR #8740 (merge `49f562d8`; `bf/cache` `ddcdb1a8`). Re-measured baseline reproduced the figure exactly
(0.837 ms vs 0.020 ms, 42.0×). The untyped branch now reads through a new `cache.getDataRef`,
which returns a fresh array of the cache's own documents; the response is still cloned out of the
slice. **0.025 ms p50 at `count=10`, 0.7× the typed branch.** Byte-identity is asserted, not
argued: the same HTTP request is made twice, once with the old cloning read patched back in, and
the bodies compared. Write-up in
[T0.2/T0.3](../../60-research/remedial/t02-t03-cache-clone-2026-09-15.md).

### BF-07 · `cache.insertData` round-trips the whole retained array

> **Partially reverted on the modernization branch (measured 2026-09-21).** `chore/nightscout-modernization` `b1bdaca0` keeps `getDataRef`
> in `lib/server/cache.js` and both `lib/data/dataloader.js` callers, but its
> `lib/api/entries/index.js` reverted to `getData`. Measured: `origin/dev` has **7** occurrences
> of `getDataRef` under `lib/`, `b1bdaca0` has **6**, and the missing one is the
> `/api/v1/entries` read path — which is the path this entry is about. It came in through
> `e3b22034`, Andy Low's dev-into-modernization merge, where the same hunk collided with cut 3's
> independently-written `inMemoryPossible` gating. The locally prepared rebase branches
> (`rt/cut1`…`rt/cut4`, queue item RT-REBASE) keep all 7 and do not copy the revert. **Raise it
> against `e3b22034` before cut 5 ships**, because nothing downstream will notice: the function
> still exists, two of three callers still use it, and no test asserts the third.


`insertData` returns `getData()` — a JSON round-trip over the **whole** retained array, per
datatype, per cycle: **4.08 ms**, 65 % of the post-#8733 load cycle.
**Resolve `dataloader.js:204` first** — `if (!element.mills) element.mills = element.date` writes
to the element, so a shallow copy changes behaviour there. The measurement sizes the prize; it
does not license the patch. *Evidence*: {R} §12.3. Plan T0.3.

**Partly merged 2026-09-20** via PR #8740 (merge `49f562d8`; `bf/cache` `4f86bab1`) — **3.747 ms →
2.657 ms per cycle, not below 1 ms**, and the shortfall is a decision rather than an omission.

`dataloader.js:204` resolved first: **the write is dead.** All three
branches below it take `mills` from `element.date`, and the array is discarded when the loop
ends, so under the clone regime it wrote to a throwaway copy that nothing read. It is removed,
and a test runs a real load cycle and asserts the cached documents come back byte-for-byte as
they went in — it fails if the write returns.

The three call sites then split. **entries** performs no writes once the dead one is gone;
**treatments** hands its array to `idMergePreferNew`, which deep-clones what it is given and
never writes to it, so `insertData`'s clone was the first of two identical clones. Both read by
reference now (0.845 → 0.035 ms, 0.397 → 0.017 ms). **devicestatus keeps `insertData`**: its
caller rewrites `uploaderBattery` into `uploader` on every document and `mergeProcessSort` writes
`_id` and `mills` on top, on documents that then live in `ddata` for the life of the process.
That is 2.6 ms of the remaining 2.66, and taking it means proving no consumer anywhere in the
plugin tier writes to a device status document — a larger claim than this change would make.

The by-reference accessors are sound because **the cache already clones on the way in**:
`mergeCacheArrays` → `idMergePreferNew` → `JSON.parse(JSON.stringify(newData))`, so a normalising
clone on the insert path is redundant (deleting one turned no test red). Write-up, including the non-vacuity runs, in
[T0.2/T0.3](../../60-research/remedial/t02-t03-cache-clone-2026-09-15.md).

### BF-08 · No start jitter in `nightscout-connect` — **merged 2026-09-23** through the connector pin; released in nightscout-connect 0.1.0

**The start is a herd.** `run()` sends `START`, and the cycle machine walked
`Init → Ready → Operating` with no delay on any edge, so every actor in a pool issued its first
upstream request in the same instant. Measured at **400 actors** against a local mock: all 400
first contacts inside **216 ms**, busiest second **400**.

**The aligned poll interval is already jittered**, so a pool does not stay phase-locked on the
same five-minute boundary after the start. All four vendor drivers independently spell
`Math.floor(Math.random() * 18000)` into the timestamp they align to — `nightscout.js:161`,
`dexcomshare.js:233`, `librelinkup.js:182`, `minimedcarelink/index.js:662`. Over a 700-second
run at 400 actors the later cycles arrive as a **band about 15 s wide peaking at 30 requests/s**,
not as a spike. The first cycle is 13× that peak, which is the whole of the effect §6.2 saw.

So the unjittered moments are **the start**, and **the unaligned interval** — the branch taken
when a source declines to align at all, which is exactly the case where the vendor has produced
nothing new and the pool is already stepping together.

*Fix*: both are windows on the cycle machine rather than a constant copied into each driver
(`CONNECT_START_JITTER_MS`, `CONNECT_INTERVAL_JITTER_MS`). The aligned path is left alone: that
timestamp belongs to the driver, which already carries its own spread, and adding more would
push the fetch past the window the driver aimed at.

**No `cgm-remote-monitor` change is needed to set them**, and that was checked rather than
assumed: with `ENABLE=connect`, `lib/server/env.js`'s extended-settings pass turns
`CONNECT_START_JITTER_MS=60000` into `connect.startJitterMs = 60000` — already a `Number`, and
already the key `index.js` reads.

**Both default to `0`, so nothing changes for anyone who does not ask.** One connector is not a
herd; a self-hosted site would only be delaying its own first reading. This is the part of T0.4
that does *not* ship value to every existing operator — it ships a knob the hosted vendor pool
must set. What ships to every operator from that task is [BF-34](#bf-34--every-configured-retry-interval-was-discarded--merged-2026-09-23-through-the-connector-pin-released-in-nightscout-connect-010),
found while doing it.

With `CONNECT_START_JITTER_MS=60000` at 400 actors the busiest second goes **400 → 15**, and the
spread **216 ms → 59.7 s**.

**One finding a hoster has to know before relying on this.** Start jitter de-phases the *first*
cycle and nothing after it. From cycle 2 on, alignment re-anchors every actor to the data's own
shared boundary, so the pool re-locks and the 18-second driver window is what bounds the peak
again. Over the full 700-second run:

| 400 actors, 700 s | shipped | `START_JITTER_MS=60000`, `INTERVAL_JITTER_MS=60000` |
|---|---:|---:|
| first-contact spread | 211.6 ms | 59.5 s |
| busiest second, whole run | **400** | **34** |
| seconds carrying any traffic | 40 | 99 |
| upstream requests | 1600 | 1636 |

The peak falls 11.8×, and all of that comes from the start: the later bands peak at 30/s
shipped and 34/s jittered, which is the same number. **A pool that needs a permanently flatter
profile has to widen the driver's alignment window, not the start** — that is a change to the
four vendor drivers and is not in this fix.

*Evidence*: `tools/mt-bench/vcherd.js` (EXP-MT-048b) and `tools/mt-bench/results/exp-mt-048b-*.json`;
{R} §6.2 for the original reading.

### BF-34 · Every configured retry interval was discarded — **merged 2026-09-23** through the connector pin; released in nightscout-connect 0.1.0

`lib/backoff.js` built its options as `{ ...config, ...defaults }`. **The defaults go last, so
they win.** Every value a caller passed was silently thrown away.

Every shipped source configures one:

| source | frame retry asks for | cycle backoff asks for | both received |
|---|---:|---:|---:|
| `nightscout` | 10 s | 2.5 min | 256 ms |
| `dexcomshare` | 2.5 min | 2.5 min | 256 ms |
| `librelinkup` | 2.5 min | 2.5 min | 256 ms |
| `glooko` | 2.5 min | 2.5 min | 256 ms |
| `minimedcarelink` | 2.5 min | 2.5 min | 256 ms |

That is **586× faster** than written for four of them and 39× for the fifth. `use_random_slot`
went the same way: forced to `false`, so the random slot the module implements has never been
reachable by any caller, and a pool that fails together retries on the same millisecond.

**Measured**, 100 actors against a mock that refuses authentication: the same **800 requests**
in both arms, delivered across **3 seconds** by the shipped code and across **67 seconds**
after the repair. The busiest second goes 400 → 200, and the 200 that remain are the first
attempt, which is immediate by design — spreading *that* is BF-08's job, not this one.

**The precedence fix cannot ship alone**, and this is the part worth carrying:
`exponent_ceiling: 20` caps the *exponent*, not the delay. Honour the configured 2.5 minutes
and attempt 10 becomes 42 hours, attempt 12 becomes **7.1 days** and attempt 20 becomes 5 years. Fixing the merge order by
itself would trade a retry storm for a feed that never comes back — strictly worse for the
person wearing the sensor. So the same change adds `max_interval_ms`, and `lib/builder.js`
states both ceilings as a relationship to the loop's own cadence rather than as constants:

- **frame retry → one poll interval.** Waiting longer than the next scheduled cycle cannot
  help; the cycle would have re-fetched by then anyway.
- **cycle backoff → six poll intervals** (30 minutes on the five-minute cadence every source
  declares). This bounds how long a feed stays dark after a long vendor outage. **Six is a
  judgement, not a measurement**, and says so in the code.

Jitter modes are named — `none`, `full`, `equal` — and default to `equal`, which keeps half the
delay and spreads the rest. Full jitter can return ~0 on any attempt, which weakens the backoff
it is there to spread.

*Blast radius*: this changes retry timing for every operator running the connector, in the
direction the source authors wrote down. It is released in nightscout-connect 0.1.0 and reaches
Nightscout operators with 15.0.9, whose `dev` pins 0.1.0 exactly (PR #8762); **release-note it** — a vendor outage will now look
slower to recover, because it stops retrying in a burst that could not have worked.

### BF-09 · Socket dedup truthiness — the value at risk is a zero temp basal

`websocket.js` tests truthiness rather than presence, so a **falsy** value is skipped as a match
key. No test covers it — the only values in `tests/websocket.*.test.js` are `insulin: 1` and
`carbs: 9/10/15/18`. **Recorded rather than guessed**: it may be intentional.

> **Graded medium on a corpus census.** A census
> over **277,690 treatment documents across 11 sites** found:
>
> | field | zero-valued | present | share |
> |---|---:|---:|---:|
> | `insulin` | **0** | 107,732 | 0 % |
> | `carbs` | **0** | 12,394 | 0 % |
> | **`absolute`** | **67,521** | 153,315 | **44.0 %** |
> | `duration` | 2,094 | 251,051 | 0.8 % |
> | `percent` | never appears | — | — |
>
> `absolute: 0` is the **zero temp basal** — the canonical AID suspend action. `duration: 0` is
> cancelling a temp. It is not an edge case.
>
> **Read as a bug, not intent**: the author built an explicit `selected`/fallback
> mechanism, so truthiness on `absolute` means the code treats a zero temp as "no value here",
> which is false in AID terms.
>
> **Two measured caveats, both pointing the same way.** A differential sweep of the shipped
> truthiness key against a presence key found **0 outcome divergences** across all 69,604 at-risk
> documents within the ±2 s window — and that null is **non-vacuous**: a four-case injection
> harness makes the comparison report 2 divergences and 2 controls agreeing, as designed. But the
> corpus is **stored data**, so it is survivorship-biased in exactly the direction that hides this
> defect: a treatment the defect swallowed as a false duplicate cannot appear in it. The null
> bounds collision frequency **among surviving records only**; the socket-path measurement below
> is what settles the behaviour.
>
> Also measured: the dedup window is `maxtimediff = times.secs(2).msecs`, i.e. **±2 seconds**
> (`lib/server/websocket.js:452`), which is why the divergence sweep had to be windowed.

**Cross-eventType match** (read 2026-09-23, reproduced by the measurement below). Leaving a falsy field out of the lookup
does more than lose it as a key. The lookup is built from whichever of `insulin`, `carbs`,
`percent`, `absolute`, `duration` and `NSCLIENT_ID` are truthy, and `eventType` is added **only if
none of them were**. A zero temp basal therefore looks up on `duration` alone, and can match a
record of a **different** `eventType` with the same duration inside the window. A match drops the
incoming record and only refreshes the existing one's `created_at`. Only uploaders that write over
the socket without an `NSCLIENT_ID` take this path. The REST path has no window. The corpus sweep
above compared truthiness against presence, not across event types, so it did not measure this.
`tools/queue/gates/bf09-corpus-divergence.js` also undercounts, and needs fixing before it is
trusted for the measurement below.

**Maintainer decision, 2026-09-23: measure first, then decide.** The maintainer leans towards
treating zero as a real value, but recalls a temp-basal display problem when AAPS sends zero temps
seconds apart. `bec641ca`, a rendering change for AAPS temp basals, is the candidate for that fix.
Any fix here must not bring that problem back.

**Measured 2026-09-23** ([evidence](../../60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md)), on
`74fc6619` and `15.0.8` with identical output, by sending each case over an authorized socket as
`dbAdd` to the tree's real server and reading the collection back, under two arms: the shipped code,
and a copy where each numeric key test also accepts `0`. Treating zero as real fixes six cases —
a zero temp, a cancel, a 100 % temp, a zero bolus and zero carbs that the shipped dedup drops when
they follow a record of the same duration or time within ±2 s — and changes none of the four
controls. It does not fix a temp target that follows a zero temp of the same duration. The
cross-eventType match described above is reproduced by that case. `bec641ca` was a rendering change
(basal sampling) and does not touch dedup; `846bb690` has since replaced its per-second sampling
with sampling at every temp's start and end, and in every case the chart drew the stored records
exactly. So on what was measured, zero-is-real does not bring back the display problem; a dropped
zero temp is itself a shipped way to draw a temp the pump was not running. Stays open for the
maintainer's choice among the options in the evidence. A side finding while building the harness is
BF-94.

*Evidence*: seam interface §4.4 (which cites the range as `535-568`; the code is at `538-566`).

### BF-10 · `mongod` fatal-asserts at the default file-descriptor limit

Docker's default `nofile=1024` is not enough for the collections and indexes Nightscout's own
test suite creates: WiredTiger hits `Too many open files` in `__wt_open` and `mongod` takes a
`fassert()` — **aborting the server**, not failing an operation.

This was reached by an ordinary test run, and matches EXP-MT-040b's finding at 50 tenant
databases. **So the fd ceiling is not a scale-only concern** — it is reachable by a self-hoster
running `mongod` in a container with default limits. It is the kind of failure that looks like data
loss to the person it happens to.

> **It has a code landing site.** `cgm-remote-monitor` **ships `docker-compose.yml` at the
> repository root**, with a `mongo:` service, on both `origin/master` and `origin/dev` (both
> `mongo:5.0.32` since `d91a9b4c`, 2026-03-17), and on 15.0.8 it **carries no `ulimits:` block**. A recursive grep for `ulimit` or `nofile` over the whole
> released tree, excluding `node_modules`, returns **nothing**.
>
> **Reproduced with the shipped file, 2026-09-22.** Starting only the `mongo` service from `origin/dev`'s own
> compose file gives `ulimit -n` 1024 inside the container, and mongod 5.0.32 aborted about 35 s into the
> **first** full suite run (WiredTiger error 24, `Fatal assertion 23089`, exit 14; one run, not repeated).
> The same service from `bf2/ops` `03fba725` gives 64000 and ran three consecutive full suites clean.
>
> So there is a one-block code landing site, in the file most self-hosters actually use: the fix is
> that file first and documentation second. **Merged 2026-09-23** via PR #8753 (merge `3a38c6f2`):
> `ulimits` on the bundled compose file's `mongo` service. Corroborating
> detail: five harnesses under `docs/60-research/` already pass
> `--ulimit nofile=64000:64000`, because their authors hit this and worked around it silently.

**Reproduced 2026-09-21 on `mongod 7.0.43`, unplanned.**
Running one branch's full test suite (`bf/auth`, ~2 200 tests) against a plain
`docker run -d mongo:7` with no `ulimits` killed the server outright. The sequence, from the
container log: the startup warning `Soft rlimits for open file descriptors too low`
(`currentValue: 1024, recommendedMinimum: 64000`), then during index creation
`__posix_directory_sync:135:/data/db/: directory-sync: open` with `error_str: "Too many open
files", error_code: 24`, then `Fatal assertion 23089 msgid 50853` at
`wiredtiger_util.cpp:772`, then `aborting after fassert() failure`. Container exit code **14**.

Three things this establishes. It is **not version-specific to the 4.4/5.0 images the
shipped compose files pin** — 7.0.43 does it too. **One ordinary test run is enough**; no tenant
scale, no 50 databases, which is how EXP-MT-040b had reached it. And the failure is a **dead
server, not a failed request**: two other worktrees pointing at that mongod then failed their
own suites with a `before all` hook timing out, which reads as a code regression and is not one.
The positive control is cheap and was run: the same image with
`--ulimit nofile=64000:64000` logs the warning **zero** times against **two** on the default.

**Measured 2026-09-23: how close a `dev`-based suite runs to the limit.** Sampling `mongod`'s open
descriptors (`/proc/1/fd`) every half second on a default-limit `mongo:7`, the full Node 20.20.0
suite of a `dev` `74fc6619`-based branch peaked at **995 of 1024** and passed. `dev` plus only a
connector pin change crossed it about 59 s in (1007, 1023, then exit 14, 28 tests failing
downstream), and it did so **with either connector installed**, so the connector is not the
cause. Whether a given `dev`-based branch passes on the default limit is therefore close to
chance. With `--ulimit nofile=64000:64000` the same branch passes 2386/0/3 with a sampled peak
of 989. Any suite result from a default-limit container that shows mass `before all` failures
should be re-run on a raised limit before it is read as a regression.

### BF-11 · `treatments.duration` and `rate` filters match nothing

**Merged 2026-09-18** via PR #8737 (merge `025f1310`); repaired by plan T0.5 on `bf/coercion` `f829ea11`, emitter `tools/nsschema/emit/coercion_emit.py`, write-up in [T0.5](../../60-research/remedial/t05-schema-driven-coercion-2026-09-15.md).

Measured against a real `mongod`: `find[duration][$gte]=30` returned **0 rows** before and **2 of 2** after.

Neither field has a `walker` entry, so a bound stays a string and MongoDB's type ordering means
it never matches a numeric field. `find[duration][$gte]=30` returns an empty list and HTTP 200.

`duration` is present on **91 % of treatment documents across 10 sites**, and **88 % of its
values are fractional**. `rate` is on 55 % of documents. These are temp basals — not an obscure
corner of the schema. Same root cause as BF-03 and fixed by the same change; listed separately
because "devicestatus has no coercion" undersells which fields are affected.

*Evidence*: [coercion drift](../../60-research/remedial/query-coercion-drift-2026-09-14.md) §2 Tier 1.

### BF-12 · `entries.rawbg` is a stale walker entry — **INVALID, closed 2026-09-15**

**This defect does not reproduce, and the entry above is struck through.** It was raised from a
mis-transcription of the walker, which this register and
`tools/nsschema/emit/coercion_emit.py` both carried.

`lib/server/entries.js` does not coerce `rawbg`. Its walker is:

```js
{ date, sgv, filtered, unfiltered, rssi, noise, mbg }
```

The entry is **`rssi`**. `git log --all -S"rawbg" -- lib/server/entries.js` returns **no commits
on any branch** — the string has never been in that file; `origin/chore/nightscout-modernization`
has `rssi` too. And `rssi` **is** in the model, as `integer`, with 32,098 observed values on one
site, so it is a *correct* walker entry, not a dead one.

The drift report now finds **zero ORPHAN rows** across every collection. The hand-maintained list
was missing entries — 148 of them — but it was not carrying stale ones, and the claim that the
drift "runs both ways" is not supported. Write-up: [T0.5](../../60-research/remedial/t05-schema-driven-coercion-2026-09-15.md).

### BF-13 · v3 paging loses documents when the sort chain ties — **merged 2026-09-18** (PR #8738)

`parseSort` appends `identifier`, `created_at` and `date` as tiebreaks. When **all** of them tie
— documents with no `identifier`, sharing one `created_at` and one `date`, as a bulk import
stamps them — the order is not total, MongoDB's blocking sort is not stable among equal keys, and
each `skip` re-runs the query. Measured: **7 of 12 documents never returned, two returned three
times**, deterministically.

**Not fixable by indexing**: only an index matching the sort exactly gives a stable `IXSCAN`, and
the sort's leading key is client-chosen (`?sort=`). Under every index set Nightscout creates the
plan is `SORT <- COLLSCAN`.

**Fires on the default path** — with no `?sort=` the chain is just the three tiebreaks, so an
ordinary paged read is exposed.

*Fix*: append `sort._id = sortDirection`. `_id` is always present and always unique, so the order
becomes total. Verified: 0/12 lost. Carry the same rule into the seam's ordering translation, or
it reappears on PostgreSQL.

*Precondition is specific and should not be overstated*: all three of no-`identifier`,
tied `created_at`, tied `date`. Any one of them differing makes it safe.

**Sized against the 11-site corpus** (~1.5 M documents) and it is **concentrated in
`devicestatus`** — expected tie-group straddles per full paginated sweep: `devicestatus` median
**23.5** (max 64), against `entries` 0.01, `treatments` 0.02, `profile` 0.09. Uploaders write
`devicestatus` in bursts sharing one `created_at`/`date`. So a client paging `entries` will
typically lose nothing, and a tool paging `devicestatus` to reconstruct controller behaviour
loses records silently — on the collection replay fidelity depends on.

*Evidence*: [ordering and pagination](../../60-research/tenancy/seam-ordering-and-pagination-2026-09-14.md) §3,
reproduced synthetically against `mongod` 7.0.43.

*Fix, merged via PR #8738*: `bf/reads` `5a5269a3` — `sort._id = sortDirection`. **Reproduced
through the real v3 HTTP path** (`GET /api/v3/devicestatus?limit=3&skip=N`): five of twelve
documents never returned, three returned more than once. The fixture is synthetic, not a capture
from a live site. The test file carries a separate assertion whose only job is to check
that the fixture really does tie on all three keys — with the fix reverted **and** the fixture's
`date` varied, the paging assertions pass vacuously, and that guard is the only thing that fails.
[Report](../../60-research/remedial/bf01-13-14-15-read-defects-2026-09-15.md) §3.

### BF-16 · `food.hidden` has no type; the server filter and the client disagree — **merged 2026-09-20** (PR #8735)

The `food` collection stores quick picks with a `hidden` flag, and the quick-pick list filters on
it. The two ends of that round trip do not agree on what the value is:

- `lib/server/food.js` `listquickpicks` queries `cmp('eq', 'hidden', 'false')` — the **string**
  `'false'`. Pre-existing upstream: released `cgm-remote-monitor` spells the same filter
  `{ 'hidden' : 'false' }` at `lib/server/food.js:146`, so this is not a regression from the
  storage-seam work.
- `lib/food/food.js:377` writes `foodquickpick[index].hidden = this.checked` — a **boolean**.
- `lib/food/food.js:69-73` `restoreBoolValue` reads it back as `record[key] === 'true'`, i.e. the
  client expects a **string** from storage.

It works today only by an accident of transport. The editor posts with
`$.ajax({ method: 'PUT', url: '/api/v1/food/', data: foodrec })` and **no `contentType`**, so
jQuery form-encodes; `wares.urlencodedParser` is `extended: true`, so every leaf arrives as a
string. `hidden: false` becomes `'false'`, which is what the filter matches and what
`restoreBoolValue` expects.

**The field therefore has no declared type. Its stored type is a property of the request, not of
the field.** A client that sends `application/json` with a real boolean stores a boolean, and
`{hidden: 'false'}` never matches it: that quick pick disappears from `/api/v1/food/quickpicks`
while remaining in `/api/v1/food/`. Nothing reports an error. The same holds for
`hideafteruse`.

*Fix*: give the field one type and accept both on read — match `$in: [false, 'false']` (or
normalise on write) rather than picking a side, since both spellings are already on disk
wherever a non-jQuery client has ever written. Do not "fix" the client to send JSON without
fixing the filter first; that is the change that breaks it.

**Secondary consequence, same root cause, reaching nobody.** Form encoding stringifies *every*
non-string value in a food document, not just the booleans — `carbs`, `portion`, `fat`, `protein`,
`energy`, `gi` and `position` — and `listquickpicks` sorts `{ position: 1 }`, so `'10'` orders
between `'1'` and `'2'`. That sort reaches no user:

* **The built-in editor never calls `/api/v1/food/quickpicks`.** It reads `/api/v1/food.json` and
  sorts the quick picks numerically itself — `lib/food/food.js:94`, `parseInt` on both sides.
* **Nothing else in the tree calls it either.** `3457de5b` (2017) moved the bolus calculator off
  that endpoint and onto `client.sbx.data.food`, and removed its only consumer.

The order users actually see was broken by a different mechanism — the bolus calculator does not
sort at all. That is [BF-35](#bf-35--the-quick-pick-chooser-resolves-the-wrong-record--merged-2026-09-20-pr-8735).

**Reproduced 2026-09-15**, over HTTP against a live MongoDB: a form-encoded write stores
`hidden: 'false'` and `position: '1'`; the same document sent as `application/json` stores `false`
and `2`. That is a test (`tests/api.food.quickpicks.test.js`), written as an assertion about the
*premise* rather than about the fix, so that if the transport ever stops doing this the filter can
be simplified.

*Fix*: one predicate, in `lib/food/quickpick.js`, used by every reader — because "accept both on
read" only works if all the readers agree on what both are.

| site | was | now |
|---|---|---|
| `lib/server/food.js` `listquickpicks` | `{ hidden: 'false' }` — the string only, so it hid every JSON-written pick **and** every record saved before the field existed | `{ hidden: { $nin: [true, 'true'] } }` — not-hidden is anything that is not one of the two spellings of true, which a missing field also satisfies |
| `lib/server/food.js` `listquickpicks` | `.sort({position: 1})` in the query | sorted after the fetch, numerically, because the query cannot coerce |
| `lib/food/food.js` `restoreBoolValue` | `record[key] === 'true'` — **turned a real boolean `true` into `false`**, silently un-hiding a hidden pick every time the editor loaded | `quickpick.isTrue(record[key])` |
| `lib/client/boluscalc.js` | did not consider `hidden` at all | hidden picks stay out of the chooser, either spelling |

`restoreBoolValue` is the only one of the four that was losing a user's setting rather than
failing to read it.

**The model does not change.** `specs/nsschema/food.model.json` declares `hidden` and
`hideafteruse` as `["boolean", "string"]` with `type_undetermined`, and that is still exactly
right: the fix does not settle the type, it makes every reader accept both, which is what an
undetermined type calls for.

**Schema-drift anchors.** `tools/nsschema/code_model.py` `SOURCE_ASSERTIONS` pins
`lib/server/food.js`'s quoted `'false'` and `lib/food/food.js`'s `record[key] === 'true';`. Since
2026-09-16 each of the two anchors accepts **exactly two spellings, the pre-fix one and the post-fix
one**, and `lib/food/quickpick.js` `isTrue` is in `SOURCE_ASSERTIONS_IF_PRESENT`, which arms itself
when the file appears in a source root. `make schema-code-drift` exits 0 against
`externals/work/crm-seam`, `externals/cgm-remote-monitor-official` and `externals/work/crm-bf-food`.
Ablated three ways, each break confirmed before the check was run: narrowing the filter to
`{ hidden: false }` fails; rewriting `restoreBoolValue` to `Boolean(...)` fails; renaming
`quickpick.isTrue` fails.

**Owed**: once `bf/food` (in `origin/dev` since 2026-09-20, PR #8735) is in both `SOURCE_ROOTS`,
delete the pre-fix arm of each anchor and move the `quickpick.js` entry into `SOURCE_ASSERTIONS`;
keeping the pre-fix arm after that lets a revert pass silently. The comment in
`tools/nsschema/code_model.py` says so at the site.

*Evidence*: `specs/nsschema/food.model.json` (`type_undetermined_why`);
`tests/api.food.quickpicks.test.js` (live), `tests/boluscalc.quickpick.test.js` (jsdom).

### BF-35 · The quick-pick chooser resolves the wrong record — **merged 2026-09-20** (PR #8735)

Found while checking BF-16's claim about the built-in editor. It is the more serious of the two
and it is not in the place BF-16 was looking.

`lib/client/boluscalc.js` `loadFoodQuickpicks` did this:

```js
quickpicks = [];
var records = client.sbx.data.food || [];
records.forEach(function (r) { if (r.type == 'quickpick') quickpicks.push(r); });
$('#bc_quickpick').empty().append(/* (none), value -1 */);
for (var i = 0; i < records.length; i++) {          // <- the WHOLE collection
  var r = records[i];
  $('#bc_quickpick').append($('<option>').val(i).text(r.name + ' (' + r.carbs + ' g)'));
}
```

The option's `value` is an index — and `quickpickChange` and `quickpickHideFood` both look that
index up in `quickpicks`, the **filtered** array. The loop builds it from `records`, the
**unfiltered** one. The two agree only when every food record is a quick pick.

**Reproduced** in jsdom with a food collection of one plain food and two quick picks:

| | shipped | fixed |
|---|---|---|
| options offered | `Apple (12 g)`, `Breakfast (45 g)`, `Lunch (70 g)` | `Breakfast (45 g)`, `Lunch (70 g)` |
| pick the one labelled `Breakfast (45 g)` | loads **Lunch** | loads Breakfast |
| pick the last option | **throws** `Cannot read properties of undefined (reading 'foods')` | loads Lunch |

The test names the record by putting a getter on `foods` — the property `quickpickChange`
reads — rather than by inspecting the GUI, because the question is which record was resolved,
not what was computed from it.

**Why it matters more than a mislabelled dropdown.** The selected quick pick's `foods` become
the carbohydrate total the bolus calculator works from. The label the user read and the carbs
the calculator used come from different records, and nothing reports a mismatch. This software
does not decide anyone's dose, but a calculator that answers for a meal the user did not pick is
the wrong kind of wrong. **A user seeing an unexpected number here should re-check it against
their own records and their care team's guidance, not assume the calculator is right.**

**Provenance.** `3457de5b` (2017-10-16, "use websockeets instead of rest api for food") moved
both loaders off the REST endpoints and onto `client.sbx.data.food`. In `loadFoodDatabase` the
author moved the type filter *into* the loop and it stayed correct. In `loadFoodQuickpicks` the
filter became a separate pass and the loop was left iterating the original array. Before that
commit the source was `/api/v1/food/quickpicks`, where every record *was* a quick pick and
`records` and `quickpicks` were the same array — so the code was right when it was written and
was made wrong by a change that did not look like it touched it.

**It has been in every release since.** A site whose food database holds only quick picks is
unaffected, which is why it survived: the food editor's own database is the thing that breaks it,
and a user who never adds a plain food never sees it.

*Fix*: build the options from `quickpicks`, and make `quickpicks` come from the one shared
selector (`lib/food/quickpick.js` `selectable`) so that "which quick picks, in what order" is
answered the same way on the server and in the client. Two behaviours change with it, both
restoring what the 2017 endpoint did and the move dropped: **hidden quick picks stop appearing**
in the chooser, and **the chooser is ordered by `position`** instead of by whatever order the
collection came back in.

*Ablation*: six reverts, each caught — the option loop (5 failures), the hidden filter (1), the
numeric comparator (1), `isTrue`'s boolean arm (3), the server filter (1), the server sort (1).

*Evidence*: `tests/boluscalc.quickpick.test.js`.

### BF-36 · The delta merge read past the end of the array it was splicing — **merged 2026-09-18** (PR #8734)

Found by auditing the eslint suppressions after BF-35, which surfaced under a
`security/detect-object-injection` suppression annotated "verified false positive": the line had
been correctly cleared of what the linter flagged, with the indexing bug beside it. There are 34
such suppressions in `lib/`; reading all of them found this one more.

`mergeTreatmentUpdate` walks the received items against the cached array while **splicing and
pushing that same array**, and captured the cached length once, before the walk:

```js
var m = cachedDataArray.length;           // captured once
for (var i = 0; i < l; i++) {
  var no = receivedDataArray[i];
  if (!no.action) { cachedDataArray.push(no); continue; }   // grows it
  for (var j = 0; j < m; j++) {                             // stale bound
    if (no._id === cachedDataArray[j]._id) {                // <- throws
      if (no.action === 'remove') { cachedDataArray.splice(j, 1); break; }   // shrinks it
```

```
mergeTreatmentUpdate(true,
  [{_id:'a'},{_id:'b'},{_id:'c'}],
  [{_id:'a', action:'remove'}, {_id:'not-in-cache', action:'update'}])
-> TypeError: Cannot read properties of undefined (reading '_id')
```

**It needs a splice followed by a miss**, which is why it has survived. Two removes do not do
it — the second matches and `break`s before reaching the stale index. An insert does not either
— `push` grows the array *past* the bound rather than below it. What does it is deleting a
treatment and editing another that is not in the client's two-day window.

**What the user sees.** The throw escapes `receiveDData` into `lib/client/index.js`
`dataUpdate`, which has no `try`/`catch`, so the rest of that handler is abandoned: the chart
stops advancing and treatments stop arriving until the page is reloaded. **It is not silent** —
`updateClock` runs on its own `setTimeout` chain, so the time-ago indicator keeps working and
marks the page stale. That is the difference between this and BF-35, and it is why this is
*medium*: the page stops telling you things rather than telling you a wrong thing. Nothing
recovers on its own.

*Fix*: read the bound fresh on each comparison. **`mergeDataUpdate`, thirty lines up in the same
file, already does exactly that**, and its purge walks backwards for the same reason — the two
functions had drifted apart, and both are now pinned so they cannot silently do so again. Both
were exported with the comment `//expose for tests` and had none; they have twelve.

*Ablation*: the shipped shape restored in `mergeTreatmentUpdate` (length captured once, outside
the outer loop, with the splice) fails exactly the two regression tests with exactly the
production error.

*What the rest of the audit found*: nothing. The other 32 suppressions index the array their
bound came from, or guard a keyed lookup with `hasOwnProperty`. The instructive contrast is in
`boluscalc.js` itself: the **food-database** chooser filters with `continue` inside one loop
over `foodlist` and appends `.val(i)`, so its index stays valid — while the **quick-pick**
chooser filtered into a second array and did not. Same file, same author, same pattern, opposite
outcome.

*Evidence*: `tests/receiveddata.merge.test.js`.

### BF-37 · A bare flag in the URL stops the page loading — **merged 2026-09-20** (PR #8736)

The third finding from the suppression audit, and the one that reaches the most people.

```js
location.search.substr(1).split('&').forEach(function(item) {
  // eslint-disable-next-line no-useless-escape
  params[item.split('=')[0]] = item.split('=')[1].replace(/[_\+]/g, ' ');
});
```

There is no check that `[1]` exists. Every one of these throws
`TypeError: Cannot read properties of undefined (reading 'replace')`:

| URL | why |
|---|---|
| `?debug` | a bare flag has no `=` |
| `?token=abc&` | the trailing `&` leaves an empty final segment |
| `?a=1&&b=2` | a doubled `&` leaves an empty middle segment |
| `?` | one empty segment |

**Where it is called is what makes it serious.** The first statement of
`lib/client/index.js` `client.init` is
`var token = client.browserUtils.queryParms().token;` — so the throw lands before anything is
wired up. No chart, no socket, no data; the page sits on its loading message with a `TypeError`
in a console the user is not looking at. It is also called from `playAlarm`, which is the worse
place to throw, but `init` gets there first.

*Fix*: a valueless parameter reads as the empty string — which is exactly what both existing
callers already treat as absence (`queryParms().token || clientToken`,
`queryParms().mute !== 'true'`) — and an empty segment is skipped rather than becoming an
empty-named key. **The split itself is untouched**, second-`=` truncation included, so a
well-formed URL parses byte-identically; a test asserts that specifically. That truncation is a
separate latent issue for any token containing `=`, and is deliberately left alone.

*Ablation*: removing the guard fails three of the five tests with the production error.

*Evidence*: `tests/browser-utils.queryparms.test.js`.

### BF-38 · `%1` ate `%10` — **merged 2026-09-20** (PR #8736), latent

`lib/language.js` `translate` substitutes `%1 … %n` by looping forwards and replacing each
globally. `%1` is a prefix of `%10`:

```
translate('%1|%9|%10|%11', {params: [...]})
  actual    one|nine|one0|one1
  expected  one|nine|TEN|ELEVEN
```

**Same class as BF-16's `position` sort** — a prefix relationship that behaves until you reach
ten, and then quietly produces a plausible-looking wrong answer.

**Latent, not live.** No shipped catalogue uses more than `%3`, so nothing is wrong in any
translation today. It would bite the first translator to write a tenth substitution, it would
bite silently, and it would look like the *translation file* was at fault rather than the
substituter — which is the expensive part.

*Fix*: substitute backwards, so `%11` and `%10` are consumed before `%1` can reach them.

*Evidence*: `tests/language.test.js`.

### BF-39 · `queryParms` turned an underscore into a space — **merged 2026-09-20** (PR #8736), no live effect

Follow-up to BF-37, which deliberately left the *value handling* alone.

The replacement was `/[_\+]/g → ' '`. **The `+` half is correct** — `+` means space in a query
string. **The `_` half is not correct in any encoding**, and it corrupts access tokens.

A token is `<subject name, \w only>-<16 hex>`, and `\W` stripping *keeps* underscores
(`lib/authorization/storage.js:190-191`), so a subject named `mom_phone` gets:

```
issued            mom_phone-89e148acdbbb4709
after queryParms  mom phone-89e148acdbbb4709
```

**Measured, not reasoned about.** Created that subject through
`/api/v2/authorization/subjects` against a live instance, read its token back, and authorised
with both spellings: **both return 200**. `findSubject` (`storage.js:279-289`) splits on `-`,
takes the **last** segment as the prefix, and matches `subject.digest.indexOf(prefix) === 0` —
so the corruption lands entirely in the part nothing reads.

**So this is not a live defect.** It is a corruption that happens to be
absorbed — the same shape as BF-16's quick-pick filter working only by an accident of transport.
Two ends disagree and a third thing hides it. The corruption is real, the leniency is real, and
nobody chose the pairing.

*Fix*: drop `_` from the class. It can only make values more faithful; the two parameters this
function is ever asked for are an access token and `mute`.

**Deliberately not fixed, and stated rather than implied:**

* **No `decodeURIComponent`.** It throws on a malformed percent sequence, and this function is
  called from the first line of `client.init` — which is exactly the throw **BF-37** exists to
  fix. Neither caller needs percent decoding. A correct-looking decoder here would reinstate
  BF-37 in a new costume.
* **The second-`=` truncation stays.** `item.split('=')[1]` still drops anything after a second
  `=`. A token cannot contain one — the name is `\w`, the digest is hex — so there is nothing to
  fix and something to record.

*Evidence*: `tests/browser-utils.queryparms.test.js`.


### BF-17 · A subject edit writes the access token into the database in plaintext

> **Fixed 2026-09-15** on `bf/auth` (`64db1f35`), carried by `bf2/auth-hardening`, in review as
> PR #8754 (head `e32f7a1c`). **Reproduced against a running instance** first — the chain below holds link for link on `dev`. One edit through the stock endpoints puts
> the token on disk, and the token read straight out of the collection authenticates (HTTP 200).
> The `notes` erasure reproduces in the same edit.
>
> `create` and `save` now build the document from the fields it owns rather than from the request
> body, and `reload()` drops the derived fields off a stored document before deriving them.
> `GET /subjects` now serves `notes`, because the durable fix does **not** fix the notes on its
> own: the client sends `notes: ''` since `GET` never gave it one, and a field whitelist writes
> that empty string faithfully. The notes fix has to be at the other end of the round-trip.
>
> **Rows already written still hold tokens, and clearing the field is not enough.** The token is
> deterministic in `_id`, `name` and the enclave key, so anyone who already read the collection —
> or a backup taken while it was in there — still holds a working credential after an `$unset`.
> Remediation is rotation, and it is the operator's decision. No migration was written. See
> [the report](../../60-research/remedial/bf17-bf30-auth-defects-2026-09-15.md) §2.3.
>
> **A rename is not a rotation.** Only the
> `abbrev` prefix of a token comes from `name`. `checkToken` splits on `-`, keeps the **last**
> segment, and matches it against `subject.digest`, which is `getSubjectHash(subject._id)` — a
> function of `_id` and the enclave key alone. **The name is never checked**, so an exposed token
> keeps authenticating after a rename. Measured at `lib/authorization/storage.js:326` on `bf/auth`
> and `:288` on `origin/dev`: not a branch artifact. Rotation means **delete-and-recreate** (new
> `_id`) or **`API_SECRET`**, and those are the only two.
> `tools/queue/gates/bf17-remediation-note.js` guards the operator documents against listing rename
> as a third option.
>
> **The stored row is not rewritten by the upgrade.** `reload()` drops the derived fields from the
> in-memory record only. The row clears when that subject is next saved through the admin path,
> because `save` writes an allow-list through `replaceOne` — a self-healing path that is
> **operator-driven, not automatic**.
>
> **Also**: `created_at` is not served by `GET /subjects` either, so an
> edit also gives the document a brand-new `created_at`. Data loss, not a security problem, and
> not fixed — one more field in the `pick` would round-trip it.


Found while deriving `specs/nsschema/auth_subjects.model.json`, by asking the narrow question
"which of these fields are actually stored?"

**`accessToken` is normally a derived value, not a stored one.** `lib/authorization/storage.js`
`reload()` recomputes it for every subject from the subject's `_id`, its `name` and the enclave
key. A stored subject document does not carry it.

Three steps put it there anyway, and each is reasonable on its own:

1. `lib/authorization/endpoints.js:38-42` — `GET /subjects` serves
   `pick(subject, ['_id', 'name', 'accessToken', 'roles'])`. Including the token is deliberate:
   the admin UI has to display it so an operator can copy it into a device.
2. `lib/admin_plugins/subjects.js:43` — the edit dialog sends the object it was given straight
   back, `data: subject`. It does not construct a payload of changed fields.
3. `lib/authorization/storage.js` `save` — `replaceOne({_id}, obj, {upsert: true})` replaces the
   document **wholesale** with the request body.

So changing a subject's name, or its roles, or its notes, writes the bearer token into the
subject's document as an ordinary string. Nothing warns, and the UI looks identical afterwards.

**Why this is worth more than the tidiness of it.** Derivation is what keeps the database from
being sufficient on its own: a reader of the stored documents alone — a backup, a replica, a
hosted MongoDB snapshot, a support export — cannot mint tokens without the enclave key. After any
subject edit, that separation is gone for that subject, and read access to the collection is read
access to a working credential. It converts a database-disclosure incident into a full API
compromise, silently and retroactively, for every subject an operator has ever edited.

Two related observations from the same reading, neither a separate entry:

- `accessTokenDigest` and `digest` are also derived and also not stored, but `GET /subjects` does
  not serve them, so they are not round-tripped. The exposure is `accessToken` alone.
- `auth_subjects.notes` has the mirror-image bug: it *is* stored, but `GET /subjects` does not
  return it, so the dialog populates its input from `undefined` and the wholesale PUT writes `''`
  back. **Any note an operator saves is erased by the next edit of that subject.**

*Fix*: the durable one is for `save` to write only the fields a subject document owns, rather
than the request body — which fixes the token and the notes together, and is the same shape of
fix as "don't replace a document with whatever a client sent". Stripping `accessToken` in the PUT
handler is the smaller change and closes the exposure; it leaves `notes` broken. Either way, a
deployment that has edited subjects already has tokens on disk, so a fix should also clear the
field on the next reload rather than only stopping new writes.

The chain was first read from the released `cgm-remote-monitor` source in
`externals/cgm-remote-monitor-official`, where every link is a literal, and then reproduced live
(above). **Not a regression from the storage-seam work** — the seam changed `save` from
`replaceOne` to a one-operation `bulkUpsert` with `mode: 'replace'`, which is the same wholesale
replacement.

*Evidence*: `specs/nsschema/auth_subjects.model.json` (`credential_warning`), which also records
that the field is `secret`/`credential` so no emitter or exporter can treat it as ordinary text.

### BF-30 · The auth-failure delay is keyed on something the caller chooses

> **Fixed 2026-09-15** on `bf/auth` (`a26ba416`), carried by `bf2/auth-hardening`, in review as
> PR #8754 (head `e549e1a6`, 2026-09-24). **Reproduced against a
> running server.** Full working in
> [the report](../../60-research/remedial/bf17-bf30-auth-defects-2026-09-15.md) §1. Three facts from
> that reproduction qualify the reading below:
>
> **1. `TRUST_PROXY` does not exist on `dev` or 15.0.8.** `lib/server/env.js:43` on `dev` is
> `env.HOSTNAME = readHostname();`; `TRUST_PROXY` and `createClientIP` were seam-branch constructs,
> and PR #8754 adds the setting. What `dev` does is weaker: `getRemoteIP` calls
> `forwarded(req, req.headers)` — `forwarded-for`'s third argument is the proxy whitelist and it is
> not passed, in **six** separate copies of that function (2026-09-15):
> `lib/authorization/index.js:10`, `lib/api3/security.js:11`, `lib/api3/alarmSocket.js:7`,
> `lib/api3/storageSocket.js:7`, `lib/server/websocket.js:9`, `lib/api/status.js:25`. So the
> address is client-controlled unconditionally, with nothing an operator can configure.
>
> **2. Keying on the credential alone is a net regression** (fix option 1 below, implemented and
> measured). It fixes the rotating-address case and removes the throttle from the case the
> shipping code did cover: a brute force varies the credential by definition, so a counter keyed
> only on the credential is fresh on every guess. Measured at 200 ms configured delay, four
> guesses from one fixed address: 200/200/200 ms shipping, 4/3/2 ms under credential keying.
>
> **3. The penalty does not accumulate even in the working case.** Per key the shipping code is a
> flat rate limiter (~200 ms every time, not 200/400/600), because `addFailedRequest` resets to
> `now + DELAY_ON_FAIL`. The defect is that the throttle never *engages*, not that it fails to
> grow.
>
> **The fix in PR #8754** (read from head `e32f7a1c`, `lib/authorization/index.js` and
> `delaylist.js`): the wait comes **before** the credential check, as in earlier releases (commit
> `f6f361b1`), so a request from a throttled address or credential learns nothing until the delay
> has passed. Failures are counted under two keys, the client address as this deployment resolves
> it and a salted digest of the attempted credential, and the longer wait applies. The list is
> bounded, with the two namespaces bounded separately so a flood of made-up credentials cannot
> evict the address entry throttling the flooder, and it is swept on a schedule (on `dev` the sweep
> was a `setTimeout` that ran once). The address key is only as good as `TRUST_PROXY`: with it
> unset, the default, the address still comes from request headers any caller can set, the
> behaviour is unchanged from 15.0.8, and a boot warning says the throttle does not protect against
> guessing until `TRUST_PROXY` is set. Commit `9c6cde72`, on the head, makes explicit `TRUST_PROXY` settings accept forwarded addresses that carry a port
> (the form Azure App Service is reported to send); unset is unchanged.

Found while verifying T3.1's decision to read `req.headers.host` rather than `req.hostname`.
That decision is correct, and checking *why* turned up a larger consequence of the same root
cause.

**`TRUST_PROXY` defaults to the empty string** (`lib/server/env.js:43`), and
`compileTrust('')` returns express's compatibility mode. Measured:

```
compileTrust('') trusts an arbitrary hop?  true
compileTrust('') trusts a second hop?      true
compileTrust('127.0.0.1') trusts it?       false
```

So by default the server believes any `X-Forwarded-For` it is handed. Measured again, through
the code that actually decides:

```
no header             -> 203.0.113.9      (the real peer)
client sets header A  -> 198.51.100.1
client sets header B  -> 198.51.100.2
```

**`lib/authorization/delaylist.js` keys purely on that string.** `addFailedRequest(ip)` and
`shouldDelayRequest(ip)` both index `ipDelayList[String(ip)]`, and `lib/authorization/index.js`
feeds them `data.ip` from `createClientIP(env.trustProxy)`. A caller that presents a different
forwarded address each time gets a **fresh key every time**, so the 5-second penalty
(`AUTH_FAIL_DELAY`) never accumulates and the throttle never engages. That throttle is the only
thing standing between an attacker and unlimited guesses at `API_SECRET` or a token.

**This is not simply "the default is wrong", and the fix is not "stop trusting".** Most
Nightscout deployments sit behind a platform proxy (Heroku, Railway, Azure) where the real peer
address *is* only available in `X-Forwarded-For`, and where the operator never configures
anything. A default that refused the header would report every request as coming from the
proxy — which collapses every user in a deployment onto one delay-list key and turns the
throttle into a self-inflicted denial of service. **The permissive default exists for a real
reason**; what is wrong is that a security control was keyed on a value that default makes
untrustworthy.

*Fix, in preference order:*
1. **Key the delay list on something the caller does not choose.** The credential being
   attempted is the obvious candidate — the point is to slow repeated guesses at *a secret*, and
   that key is identical whether the attacker rotates addresses or not. It also fixes the
   behind-a-proxy case, where today every user shares one key.
2. **Bound the list.** It is an unbounded object keyed by an attacker-controlled string, swept
   only once a minute; a burst of forged addresses grows it until the sweep. Secondary to (1)
   and the same root cause.
3. Narrow the `TRUST_PROXY` default with a documented migration — worth doing, but it is a
   deployment-compatibility change and it does not fix (1) for deployments that legitimately
   must trust the header.

Both measurements above are of the shipping functions in `externals/work/crm-seam`, called
directly, and the defect was then reproduced live (above); the chain from `data.ip` to `shouldDelayRequest` is
read from `lib/authorization/index.js:140-206`. **Not a regression from any work in this
programme** — `delaylist.js` and the `TRUST_PROXY` default both predate it.

*Related, not the same*: T3.1 avoids this class for tenant resolution by reading
`req.headers.host` directly and refusing to honour a configured alternative header unless
`TRUST_PROXY` is set. That is the pattern the fix above generalises.

### BF-31 · One request re-languages the whole process (alarm text is not affected)

Found while fixing a blind spot in `tools/qc/tenant-shared-state.js` (see
[the audit](../../60-research/tenancy/tenant-shared-state-audit-2026-09-15.md) §4a): the tool could not see
a singleton created by a factory and held at a call site, and `language` is the widest one in the
server.

`lib/server/server.js:34` builds **one** language instance for the process and passes it to
`bootevent`. `lib/api/googlehome/index.js:20-29` then does this inside a request handler:

```js
ctx.language.set(locale);
moment.locale(locale);
```

`language.set` assigns `language.lang` on that shared instance — it is a persistent mutation, not
a per-call option — and `moment.locale` is a global mutation of the library. So **one
authenticated request changes `language.lang` and `moment`'s global locale for every subsequent
request in the process**, until another request changes it back.

`lib/server/bootevent.js:212` sets `ctx.levels.translate = ctx.language.translate`, so level
names (`Urgent`, `Warning`) go through the same shared instance — but the catalogue is loaded once
at boot and never reloaded, so they do not change (measured, below).

**Severity.** The route is mounted only `if (ctx.googleHome)`
(`lib/api/index.js:74`), so it is opt-in, and the caller needs `api:*:read` — which in a family
deployment is everyone holding the token. The consequence is a cross-request state leak in the
assistants' own answers (relative times, speech code); alarm text is not affected.

*Fix*: the locale is a property of the **request**, not of the server. Resolve it per request and
pass it to the handler, rather than setting it on the shared instance; `moment.locale` has a
per-instance form (`moment().locale(x)`) that avoids the global. Under multitenancy this stops
being one deployment's bug and becomes a cross-tenant leak, which is why T3.3 named `language`
and `levels` as still-shared and did not attempt a fix — a correct one is a locale-keyed instance
cache, since a language file is 45–60 KB and one per tenant is the wrong shape.

~~*Not reproduced against a live server.*~~ **Superseded — reproduced 2026-09-15; see the block below. Kept as the original reading trail.** `language.set`'s persistence and the `levels.translate`
assignment were read and exercised directly; the Google Home route was not driven end to end.

**Reproduced 2026-09-15; merged 2026-09-20** via PR #8739 (merge `7a5561f4`; `bf/alarms`
`5dcf783f`). Alarm text is *not* affected. `language.set` assigns `lang` and `speechCode` and nothing
else; the translation catalogue is read once at boot by `loadLocalization` and is never reloaded
on the server, so `levels.toDisplay(URGENT)` still returns `Urgent` after a German request, as
does every other translated string. Measured before and after one `de-DE` request: `lang`
`en`→`de`, `speechCode` `en-US`→`de-DE`, and every relative time `an hour ago`→`vor einer Stunde`
— all three persisting into every later request. `require('moment') === require('moment-timezone')`
is `true`, so the global locale does reach `ctx.moment` and every plugin. But enumerating every
locale-sensitive `moment` format in the server tree puts **all** of them inside virtual-assistant
handlers: no notification message built in `lib/plugins` passes a date through `moment` at all
(`timeago` does not use it; the age plugins use `diff(...,'hours')`, a number; `pump`'s
`buildMessage` concatenates displays). So the real consequence is a cross-request state leak in
the assistant integration, **not alarm text**, and the severity is lowered accordingly.

**There are two routes**: `lib/api/alexa/index.js:28` carries the identical two lines. Both are
fixed.

**What was deliberately not done.** The prescribed fix — resolve the locale per request and pass
it to the handler — is blocked structurally: every virtual-assistant handler captures
`var moment = ctx.moment;` at plugin *init* (`ar2.js:18`, `loop.js:9`, `openaps.js:9`,
`xdripjs.js:6`, `bgnow.js:9`, `basalprofile.js:6`, `virtAsstBase.js:4`), so a per-request value
cannot reach a closure captured at boot without threading a locale through six plugins, several
of them alarm producers. That is wider than this entry's framing and is reported rather than
done. The fix removes both process-wide mutations; nothing that worked is lost, since
`language.set` never changed any text and the relative times were only ever in the caller's
language if that caller happened to be the most recent one. **The same wall applies to any
per-tenant `ctx`**: a per-tenant `ctx.moment`, `ctx.language` or `ctx.levels` cannot reach a
closure that captured the boot-time value.

*Evidence*: [BF-28/29/31 alarm delivery](../../60-research/remedial/bf28-29-31-alarm-delivery-2026-09-15.md) §3.

### BF-32 · type coercion was applied to operator operands — **merged 2026-09-18** (PR #8737)

Found while fixing BF-02/BF-03 (plan T0.5): `walk_prop` applied the walker's conversion to
**every leaf** of a field's query fragment, including operands that are not values drawn from the
field's domain. On `origin/dev`:

```
find[sgv][$exists]=true   ->  { sgv: { $exists: NaN } }
find[sgv][$regex]=^1      ->  { sgv: { $regex: NaN } }
```

> **`$exists=true` was not inverted.** MongoDB does not apply JavaScript truthiness. Measured
> 2026-09-15 against seven live `mongod` instances (3.6.8 and 7.0.43, identical on all seven):
> `{$exists: NaN}` returns the documents that **have** the field — MongoDB's numeric truthiness is
> `value != 0`, and `NaN != 0`. `{$exists: "false"}` and even `{$exists: ""}` are truthy for the
> same reason. So on 15.0.8 `find[sgv][$exists]=true` answers correctly, by accident; graded **low**.
>
> **Oracle limit**: `mingo`, the differential oracle decision D8 names, is a JavaScript
> reimplementation and applies JavaScript truthiness, so it reports `[2]` for `NaN` where MongoDB
> reports `[1]`. It remains fit for comparing *operator* semantics on well-typed operands; a claim
> about a malformed operand must be taken from a server.
>
> **What is defective, in two parts:**
>
> - **`$regex` was the real breakage.** Measured on the same server, `{notes: {$regex: NaN}}`
>   returns the error *"$regex has to be a string"* — an HTTP 500 — where `{$regex: 'ab'}` matches.
>   On a coerced numeric field, `find[sgv][$regex]=^1` is a 500 today and an empty 200 after the
>   fix. That is a real improvement.
> - **`$exists=false` returns the wrong documents on 15.0.8**, on every field: **BF-40**.

It was reachable on the 10 fields that carried a walker entry, which is why it had stayed
invisible: those are the fields most likely to be present anyway. Generalising coercion to 158
fields would have generalised this defect with it, which is how it surfaced. Coercing an operand
that is not a field value is wrong regardless of which way MongoDB happens to read the result.

*Fix*: merged with T0.5 via PR #8737 (merge `025f1310`). `lib/server/query-coercion.js` leaves `$exists`, `$type`, `$regex`,
`$options`, `$where`, `$expr`, `$text`, `$comment` and `$jsonSchema` operands alone, while still
converting every element of an `$in` list. Applied to explicit walker entries as well as
schema-driven ones, so the pre-existing case is fixed too.

*Evidence*: [T0.5](../../60-research/remedial/t05-schema-driven-coercion-2026-09-15.md) §4, reproduced against
the original file before the change.
**Not a regression from this programme** — both predate it.

### BF-33 · v3's `?limit=` has the same hole — **merged 2026-09-18** (PR #8738)

Found while fixing **BF-14**, whose entry says to copy v3's validation rather than invent one.
`lib/api3/generic/collection.js` `parseLimit` bounds-checks the raw string, then converts it with
a different reading of the same string:

| `?limit=` | `isNaN` / `<= maxLimit` sees | `parseInt(_, 10)` produces |
|---|---|---|
| `0x10` | 16 — passes | **0 — no limit** |
| `1e2` | 100 — passes | 1 |
| `2.5` | 2.5 — passes | 2 |

Measured live against 30 documents with `API3_MAX_LIMIT` set to 20:

```
?limit=0x10  ->  200, 30 rows   the whole collection, over the ceiling
?limit=1e2   ->  200,  1 row    a hundred were asked for
?limit=2.5   ->  200,  2 rows
```

So **an unbounded read is reachable through v3 by any client with read access**, and it bypasses
the ceiling that exists to prevent exactly that. `?limit=0`, `-3`, `abc` and `1e400` were already
`400` and still are.

*Fix, merged via PR #8738*: `bf/reads` `2ecfeb53` — test the digits the client actually wrote, and
bounds-check the number that will be used rather than a different reading of the same string.
`0x10`, `1e2` and `2.5` are now `400`.

*Duplication, on purpose*: this and `lib/server/count.js` (BF-14) express the same rule twice, so
that each commit lands or reverts alone. Both are in `dev`; they should now be unified — two
readings of one rule is the root cause of this whole family.

*Evidence*: [report](../../60-research/remedial/bf01-13-14-15-read-defects-2026-09-15.md) §6, reproduced
against a running server before the change.

## 2b. Detail — entries added 2026-09-15 (BF-40 … BF-67), and BF-27's missing section

These were raised by the ground-truth and verification passes of 2026-09-15 and later. **Each says
which kind it is** — reproduced, or derived from source.

### BF-40 · `$exists=false` returns the documents that *have* the field

MongoDB reads a non-numeric `$exists` operand by its own truthiness, not JavaScript's (`mingo`, the
D8 differential oracle, applies JavaScript's and gets this wrong; see BF-32). Measured 2026-09-15 against **seven live `mongod` instances — 3.6.8 and 7.0.43 — with
identical results on all seven**, over `[{_id:1, sgv:100}, {_id:2}]`:

| operand | documents returned | reading |
|---|---|---|
| `true` (boolean) | `[1]` | has the field |
| `false` (boolean) | `[2]` | lacks it |
| `0` | `[2]` | lacks it |
| `NaN` | **`[1]`** | **has it** — MongoDB's numeric truthiness is `value != 0`, and `NaN != 0` |
| `"true"` | `[1]` | has it |
| `"false"` | **`[1]`** | **has it** — a non-empty string is truthy |
| `""` | `[1]` | has it — *any* string is truthy, even the empty one |

**Non-vacuity**: the probe distinguishes. `false` and `0` return `[2]`; everything else returns
`[1]`. If it could not tell the branches apart, both columns would be equal.

So:

- **On today's release**, `find[sgv][$exists]=false` becomes `{$exists: NaN}` → returns the
  documents that **have** `sgv`. The exact opposite of the request, HTTP 200.
- **On every field the walker never touched**, the string `"false"` arrives untouched → same wrong
  answer. So this is wrong on *every* field today, not just the ten walker fields.
- **After `bf/coercion`**, the operand is left as `"false"` → **still** the wrong answer.
- `$exists=true` is answered correctly before *and* after, by two different accidents.

**Fix, merged 2026-09-18 via PR #8737** (merge `025f1310`; `bf/coercion` commit `b7234753`),
reproduced 2026-09-16. It is a pass over the **finished query**, keyed on the operator, so it is
independent of whether the field has a declared type; it also handles
`{$not: {$exists: "false"}}` and an operand inside `$or`. A fix inside `isValueLeaf` would not do:
`isValueLeaf` is only reached from inside `walk_prop`, which only runs for fields that have a
typer, and `madeUpField`, `notes` and every field of `activity` never enter it (measured).

**The empty string is left alone.** Four spellings are read —
`"true"`/`"1"` and `"false"`/`"0"`, case-insensitively. **The empty string is deliberately left
alone.** `?find[x][$exists]` with no value parses to `''`, and after **BF-37** that is reachable;
it is as easily "yes, I want this flag" as "no, I do not", and reading it either way would silently
invert somebody's query — which is this defect, committed in the other direction. Anything else
unrecognised passes through for the same reason.

**End-to-end, live, over two treatments (one with `insulin`, one without):**
`find[insulin][$exists]=false` returned the document **with** `insulin` before and the one
**without** after; `$exists=true` returns the same document either way.

**Why it shipped with the schema-coercion commit.** The fix needs the schema-coercion
commit ahead of it: on `origin/dev` the walker converts the operand to `NaN` before any later pass
can read it, and `NaN` is truthy too. With only the `$exists` commit, these stay inverted —

| still inverted | fixed |
|---|---|
| `entries.sgv`, `.filtered`, `.unfiltered`, `.rssi`, `.noise`, `.mbg`; `treatments.insulin`, `.carbs`, `.glucose` | `treatments.notes`, `.eventType`, `.enteredBy`, `.duration`; all of `devicestatus` |

— which is every field a `walker` names, and they are the fields anyone actually filters on.
(`notes` and its neighbours survive because `parseRegEx` returns non-regex input unchanged rather
than producing `NaN`.) So the two are one PR of two commits. `tests/query.operands.test.js` holds twelve
tests; it is in neither local brace list, so `npm test`.

### BF-41 · a reading dated in the future silently switches off the stale-data alarm (closed: does not reproduce)

**Closed 2026-09-23, invalid.** The arithmetic below is right, but it never runs on a future
reading: `lib/sandbox.js` `lastEntry` skips every entry later than `sbx.time` (`notInTheFuture`,
`556091bf`, 2015, in every tag from 0.10.0). Measured through the real sandbox on `74fc6619` and
`15.0.8`: a stale real reading plus one dated ahead still raises warn/urgent on the browser path
and the push alarm on the server path. The original queue gate stubbed `sbx.lastSGVEntry` and so
reproduced a state the shipping code never reaches; it was rewritten in `b248bb73`. No tolerance
setting is added (maintainer, 2026-09-23). The residual is BF-95. Write-up:
[bf41-future-reading-2026-09-23.md](../../60-research/remedial/bf41-future-reading-2026-09-23.md).

**The claim as registered** (kept so it is not raised again):

`lib/plugins/timeago.js`, read on `origin/dev`:

```js
:26   if (!lastSGVEntry || lastSGVEntry.mills >= sbx.time) { return; }   // before any sendAlarm
:97   function isStale (mins) { return sbx.time - lastSGVEntry.mills > times.mins(mins).msecs; }
```

For a reading stamped ahead of the server clock, `sbx.time - mills` is **negative**, so `isStale`
is false at every threshold, `checkStatus` returns `'current'`, and `lib/client/index.js:918-919`
— `alarmTimeagoWarn && status === 'warn' || alarmTimeagoUrgent && status === 'urgent'` — is false
too. Both alarm paths go quiet.

**Which path is on by default:**

| path | default | how a future reading silences it |
|---|---|---|
| **browser alarm** (`lib/client/index.js`) | **ON** — `alarmTimeagoWarn: true` / `alarmTimeagoUrgent: true`, 15 and 30 minutes (`lib/settings.js:27-30`) | `checkStatus` never leaves `'current'` |
| **server push notification** (`timeago.checkNotifications`) | **opt-in** — returns immediately unless `sbx.extendedSettings.enableAlerts` | the `mills >= sbx.time` early return at `:26` |

The claim was graded high because a future timestamp comes from a clock or timezone error at the
uploader — the class of fault most likely to have broken the feed in the first place. **BF-44** is
a shipping way to produce one.

**Visible symptom, for an operator-facing note**: the "minutes ago" pill reads `future` when more
than five minutes ahead and sticks at `1m` between zero and five (`timeago.inTheFuture`,
`timeago.almostInTheFuture`).

**Provenance: reproduced-negative, 2026-09-23.** `tools/remedial/bf3/bf41-real-sandbox.js` loads
`ctx.ddata.sgvs`, builds the sandbox with `serverInit` (push path, alerts on) and `clientInit`
(browser path) and asks both: with a real reading 40 minutes old plus one 2 hours ahead, both paths
go `urgent`; with one 20 minutes old plus one 3 minutes ahead, both go `warn`. Identical on
`origin/dev` `74fc6619` and `15.0.8`. With the `556091bf` filter replaced by `return true`, both
cases go `current` with no push — the registered symptom — and the controls do not move, so the
harness can see the defect when it is there.
([evidence](../../60-research/remedial/bf41-future-reading-2026-09-23.md))

**What does happen, measured.** (1) An uploader whose clock runs **ahead** makes each reading look
newer than it is once the wall clock passes its timestamp, so the stale-data alarm comes late by
about the size of the skew: with a clock one hour fast, the 15-minute warning comes about 75
minutes after the feed stops. That is BF-95. (2) When every loaded reading is in the future, or
none is loaded, `checkStatus` takes the no-reading branch and assumes `current`: no usable reading
means no alarm (not filed). Neither is the registered symptom.

**Decision (maintainer, 2026-09-23)**: closed as not reproducing (evidence §5, option 1); no
tolerance setting is added. A tolerance would loosen the alarm — a real reading 20 minutes old plus
one 3 minutes ahead warns today and would stop warning — and would change nothing in the
clock-ahead case. The evidence §7 text ships as a 15.0.9 known issue.

### BF-42 · the connector every operator runs logs credentials unconditionally

`origin/master` pins `nightscout-connect` at the **v0.0.13 tag tarball**. In that tree, measured by
a comment-stripping scanner over a `git archive` extraction: **112 live `console.*` sites in
`lib/` + `index.js`, 101 of which pass a non-literal argument**, and `grep -rniE "if *\(.*(debug|verbose)"`
returns **nothing** — no guard exists.

The most universal one is not source-specific:

```
index.js:54   console.log("INPUT PARAMS", spec, validated.config)
```

`validated.config` is the source's own validated credential object — `sharePassword` for Dexcom,
`carelinkPassword` for MiniMed, `linkUpPassword` for LibreLinkUp, the Glooko password for Glooko.
It prints at **every boot, for every source, before any network call**; `index.js:57` prints the
whole object again when the config is rejected. `lib/outputs/internal.js:88` is
`console.log("INTERNAL PERSISTENCE", batch)` on the embedded Nightscout path, where `batch` holds
entries, treatments, profiles and devicestatus — i.e. patient data.

**Redaction by pin, measured — and it does not improve monotonically with release order:**

| pin | carried by | live / dynamic `console.*` | state |
|---|---|---|---|
| **v0.0.13 tag** (`b394411`) | **`origin/master`** and cuts 1, 2, 3 | 112 / 101 | leaking, no guard |
| `234d47c8` | no current ref | 22 / 20 | **the leaking call sites are deleted**, not merely gated: an 18-file rewrite introducing `lib/logging.js` |
| `c962a13f` | cut 4 | — | the three redaction commits, **but LibreLinkUp still leaks** at `lib/sources/librelinkup.js` (9 live sites, 8 dynamic; auth headers, response bodies, the session object carrying `authTicket`, and the transformed glucose batch) |
| `b77e5bb` | cut 5 | 22 / 20 | contains both lines |
| `0.1.0` on npm (`latest`, released 2026-09-24; tag `v0.1.0` on connector `main` `4dde1ec`, code identical to `977da8a` = `v0.1.0-dev.3`) | **`origin/dev`** `153e5658` (exact pin via PR #8762) | not censused | carries `234d47c` and the three redaction commits; `test/privacy-canary.test.js` runs every source against a fake vendor whose credentials, tokens, cookies, bodies and errors carry one marker, and fails if the marker reaches any console method |

Two consequences of the table:

1. `234d47c8` **deletes** the leaking call sites rather than gating them behind a debug setting.
   **`master`'s pin is the leaking one**; `dev`'s pin carries the deletion.
2. Cut 4 does not have all the redaction: LibreLinkUp is unredacted there.

**Standalone output.** `lib/outputs/nightscout.js` is **not reachable from cgm-remote-monitor** —
the embedded path selects the `internal` output — so it affects standalone `nightscout-connect` CLI
users only. At `v0.0.13` it prints its configuration, which carries the Nightscout API secret; in
connector `0.1.0` it logs fixed debug messages only.

**Provenance: source census, not a live run.** No vendor account exists on this machine and the
connector's own evidence states none has been used. The census is non-vacuous in the one way that
matters: the same scanner returns 112/101 on the leaking tree and 22/20 on the redacted ones, and
it correctly reports cut 4's commented-out MiniMed block as 47 calls with **0** dynamic arguments,
so it distinguishes deletion from commenting-out.

**Fix**: pin the full connector release `0.1.0` by exact version from npm. `origin/dev` does (PR
#8762, merge `153e5658`, 2026-09-24), so the fix reaches Nightscout operators with 15.0.9; cuts
1-3 pin v0.0.13 (BF-65). See the
[connector pin consolidation](../../40-migration/connector-pin-consolidation-2026-09-15.md).

### BF-43 · a silent `overrides` constraint violation on the released artefact

`origin/master:package.json` sets `overrides['nightscout-connect'] = {"axios": "1.16.0"}` while
`nightscout-connect` v0.0.13 and `0.1.0` declare `dependencies.axios = "^1.18.1"`.
`semver.satisfies('1.16.0', '^1.18.1')` is **false**; `'1.20.0'` is true. `master`'s
`package-lock.json` confirms the override takes effect —
`node_modules/nightscout-connect/node_modules/axios` is 1.16.0.

`overrides` exists precisely to suppress the `ERESOLVE` that would otherwise reject this, so
nothing reports it. **The branches disagree four ways**:
`1.16.0` on master, `1.20.0` on dev and cuts 1-4, **absent entirely** on cut 5.

**Not reproduced as a runtime failure, and no specific axios API was identified** that the
connector uses and 1.16.0 lacks. The defect asserted is the silent constraint violation, not a
known break. Found by `tools/qc/connector-pin-agreement-gate.js` rule R5.

### BF-44 · two MiniMed implementations disagree about what time a reading happened

`nightscout-connect`'s CareLink source rewrites a reading's zone only when the field's own value
already ends in `([+-]\d\d:\d\d|Z)`; otherwise `reassign_zone` falls back to the identity function.
The retired `minimed-connect-to-nightscout` instead **guesses and applies the pump's UTC offset**
(`transform.js:41-85`, `guessPumpOffset`/`parsePumpTime`). The two therefore assign different
absolute times to the same reading.

**Reproduced**: both shipping implementations loaded side by side against identical payloads.
Three arms diverge by exactly the offset (UTC+2 → +2 h, UTC−7 → −7 h, UTC+5:30 → +6 h) and two
controls agree (UTC+0; and UTC+2 *with* a zone-bearing `lastConduitDateTime`).

**Three qualifications, all narrowing it:**

1. **The magnitude is not a clean function of the pump offset.** It is (pump offset − *server*
   timezone offset) whenever the payload's timestamp strings carry **no** zone designator — and the
   retired package's own recorded CareLink payloads use a zone-less format (`"Oct 17, 2015 09:09:14"`).
   Under `TZ=Europe/Berlin` the Berlin arm *agrees* and the UTC control *diverges*: the arm and
   control roles invert.
2. **Presence of `lastConduitDateTime` is necessary but not sufficient.** The regex is tested
   against the *item's own* field, not against `lastConduitDateTime`. A zone-bearing conduit time
   beside a zone-less `datetime` still diverges, unmitigated.
3. **The legacy side has two branches.** `parsePumpTime` forks on `MMCONNECT_SERVER === 'EU' || medicalDeviceFamily === 'GUARDIAN'`;
   only that branch subtracts the offset. On the default branch the legacy transform **throws
   `RangeError: Invalid time value`** on a Z-suffixed payload rather than producing the comparison
   value. The arm table reproduces only with `MMCONNECT_SERVER=EU`.

Also: `pump.clock` is not parsed at all — `deviceStatusEntry` assigns `data['sMedicalDeviceTime']`
verbatim, so a client doing `new Date(pump.clock)` can get `Invalid Date`.

**Why it matters**: a forward shift files readings in the future, which delays the stale-data
alarm by about the size of the shift (**BF-95**; BF-41's "goes quiet" does not reproduce). It is
graded low because the divergence needs readings from both paths and legacy mmconnect does not work
(maintainer, 2026-09-22). Coverage is thin in the way that hides it: `lastConduitDateTime`
appears **zero** times in `tests/fixtures/minimed-cutover.json` and in
`tests/connect-minimed-cutover.test.js`, and the one connector test that sets the field passes a
`Z`-suffixed value, which makes the rewrite a no-op — that test is a control, not coverage.

**Open question that decides active vs latent**: do real CareLink payloads omit
`lastConduitDateTime`, and do `sgs[].datetime` / `markers[].dateTime` / `sMedicalDeviceTime` carry
zone designators of their own? **Not reproduced against a real CareLink account.**

### BF-45 · the MiniMed boot stage has no Connect stand-down guard

Read in full on `origin/master` and `origin/dev`: `setupBridge` logs *"Skipping legacy
share2nightscout-bridge because nightscout-connect is handling Dexcom Share"* and returns.
`setupMMConnect` references Connect **nowhere**. The boot order is
`setupListeners → setupConnect → setupBridge → setupMMConnect`, so the connector has already
started by the time the MiniMed stage runs.

**Consequence for operator guidance**: any advice to "stage the new `CONNECT_*` settings before
removing the old ones" is safe for Dexcom and **unsafe for MiniMed**, because staging produces
concurrent double ingestion rather than a clean handover. Every document that carries that advice
generically needs the MiniMed exception.

**Derived from source**, not run as a live double-ingestion. Medium alone — the `sysTime`+`type`
upsert absorbs duplicate writes — **high in combination with BF-44**, where the two paths compute
different keys and nothing absorbs them.

### BF-46 · eleven API v3 variables nobody can look up, one family of which deletes data

`lib/api3/index.js:24-38` defines `setENVTruthy`, which reads `process.env[varName]` plus three
Azure/lowercase spellings **directly** — not through `lib/server/env.js`, not through
`lib/settings.js`. Call sites: `API3_SECURITY_ENABLE`, `API3_DEDUP_FALLBACK_ENABLED`,
`API3_CREATED_AT_FALLBACK_ENABLED`, `API3_MAX_LIMIT` (`:73-76`), `CI` (`:70`), and
`API3_AUTOPRUNE_<COLLECTION>` for the six registered collections (`devicestatus`, `entries`,
`food`, `profile`, `settings`, `treatments`).

`lib/api3/generic/collection.js:129-152` computes `deleteBefore = now − autoPruneDays × 24 h` and
calls `storage.deleteManyOr` **without awaiting the result**.

`grep -c API3_ README.md` is **0**. The same grep against `lib/server/env.js` and `lib/settings.js`
returns 0 each — so these names are invisible to every configuration census this programme has
run, and to every operator reading the documentation.

**The deletion path was read, not executed.** Severity is high on the combination: an undocumented
variable, reachable by a spelling nobody can look up, that irreversibly deletes a person's stored
glucose history, with the result unawaited so a failure is not even observed.

**Fix — UNVERIFIED.** Two parts, and the second is the load-bearing one: route these through
`env.js` so they appear in the configuration surface, **and document `API3_AUTOPRUNE_*` with what
it deletes and that it cannot be undone** before any hosted deployment sets it.

### BF-47 · an ordinary subject edit destroys stored fields, on today's release

The defect is on the current release, not introduced by `bf/auth`. On `origin/dev` and 15.0.8:

- `lib/authorization/endpoints.js:40` returns `pick(subject, ['_id','name','accessToken','roles'])`.
- `lib/admin_plugins/subjects.js` `PUT`s that object straight back.
- `lib/authorization/storage.js` `save()` does `collection.replaceOne({_id: obj._id}, obj, {upsert:true})`
  — a whole-document replace of the caller's object.

So editing a subject through the stock admin UI **already** destroys `notes`, `created_at` and any
field a third-party administration tool has stored. Silently, with no error, and not recoverable by
reverting code.

**What `bf/auth` changes, precisely** — it narrows the loss rather than introducing it:

- it **adds `notes`** to both the response and the allow-list, which *reduces* one case;
- it introduces `SUBJECT_FIELDS` / `ROLE_FIELDS` / `ownedFields()`, so a third-party tool can **no
  longer preserve its own fields by sending them in its own `PUT`** — previously it could, because
  `save()` wrote the caller's object as given.

Keeping the derived `accessToken`/`accessTokenDigest`/`digest` out of the database is correct and is
the point of that commit (BF-17). The narrower change that achieves the same security goal is to
delete only `DERIVED_SUBJECT_FIELDS` and pass unknown fields through.

**Derived from source on `origin/dev` and on `bf/auth`. Not reproduced against a deployment.**
**Maintainer decision 2026-09-23**: the allow-list is intended. A corpus check found no open-source
client that stores other subject fields; the one it found sends a misspelled field (BF-89). On
`dev` and 15.0.8 what remains is the admin page, which fetches subjects without `notes` and
`created_at` and saves the whole subject back, clearing both; `bf/auth` (PR #8754) serves `notes`,
and `created_at` is still lost (BF-17).

### BF-48 · four undocumented variables read straight from `process.env`

`lib/plugins/webhook.js:36-39` reads `WEBHOOK_PROTOCOL`, `WEBHOOK_HOST`, `WEBHOOK_PORT` and
`WEBHOOK_PATH` from `process.env`, bypassing `env.js`, the settings layer and `extendedSettings` —
which `findExtendedSettings` would populate as `extendedSettings.webhook` if the plugin asked.
`grep -c WEBHOOK_ README.md` is **0**.

The reads are *inside* `module.exports = function webhookPlugin() { … }`,
so they run when the factory is invoked (`lib/plugins/index.js:71` and `:106`), **not** at module
load. The conclusion survives — the reads are of `process.env`, not of `ctx`, so per-tenant
configuration still cannot reach them — but the fix is an ordinary call-site change, not a
module-load rewrite.

**Single-tenant impact**: undocumented and unconfigurable through any documented mechanism.
**Multi-tenant impact**: every tenant's webhook posts to the same host. Not reproduced against a
running instance.

### BF-49 · a security header with two spellings, and five dead settings keys

`lib/settings.js:48` defines the camelCase key `secureHstsHeaderIncludeSubdomains`, so the settings
layer's own `nameFromKey` produces **`SECURE_HSTS_HEADER_INCLUDE_SUBDOMAINS`** — which it accepts
and stores. `lib/server/env.js:114` reads **`SECURE_HSTS_HEADER_INCLUDESUBDOMAINS`** (no underscore),
and `lib/server/app.js:144` consumes `env.secureHstsHeaderIncludeSubdomains`.

Grep over `lib/`, `views/` and `static/` finds **zero** consumers of
`settings.secureHstsHeaderIncludeSubdomains`. `README.md:399` documents the *working* spelling, so a
README-follower is fine and a settings-dictionary reader is not.

The same dead duplication **without** a spelling divergence exists for `insecureUseHttp`,
`secureHstsHeader`, `secureCsp` and `secureHstsHeaderPreload` (`settings.js:49`) — five dead keys in
all, four of them security-related.

**Why it matters past tidiness**: a tenant-admin UI generated from the settings dictionary would
offer five settings that do nothing, one of them a security header. That is D7/D13 work reading a
list that lies.

### BF-50 · a documented variable nothing reads

`README.md:240` documents `MONGODB_COLLECTION` (default `entries`) as "The Mongo collection where
CGM entries are stored". Grep over `lib/` and `bin/` returns **no reader**; the code reads
`ENTRIES_COLLECTION` or `MONGO_COLLECTION` (`lib/server/env.js:211`). The only occurrence of the
string in the tree is the README line.

An operator who sets it gets the default and no error. **Fix: correct the README.** There is no
code landing site.

### BF-51 · the Azure template's Node knob is inert

`azuredeploy.json` declares a `WEBSITE_NODE_DEFAULT_VERSION` parameter and **references it nowhere**:
`parameters('WEBSITE_NODE_DEFAULT_VERSION')` occurs **0** times in the raw template text on
`origin/dev` and on `origin/chore/retire-jsdom`. The `appSettings` entry's value is the literal
string `8.11.1` on both refs, while the parameter's `defaultValue` is `16.16.0` on dev and `~24` on
cut 1.

So no Azure operator's Node version is controlled by the field that appears to control it, and cut
1's change of that default has no effect on a deployed site.

**Not reproduced against a live Azure deployment** — there is no Azure environment on this machine.
*Why deployments work today* is therefore an open question attached to this entry, not a finding:
the platform presumably ignores `8.11.1` as unavailable and falls back.

### BF-52 · the age plugins can only *ask* for their urgent alarm in one window

`lib/plugins/insulinage.js`, after BF-28's fix:

```js
:90   if (insulinInfo.age >= prefs.urgent)   { insulinInfo.level = levels.URGENT; …   // threshold
:92   sendNotification = insulinInfo.age === prefs.urgent;                            // equality
```

The **level** is continuous — correct for as long as the reservoir is overdue, and that is what
BF-28 fixed. The **notification request** is made only while `age === threshold` **and**
`minFractions <= 20`, so the window is minutes 0–20 of the threshold hour. The server evaluates on
every heartbeat (60 s) and every upload, so inside the window it asks about 20 times; the request
is lost only when nothing evaluates during those minutes (a restart or deploy, a sleeping host, a
stalled data load), and nothing later asks.

`git show 8714093b -- lib/plugins/insulinage.js` confirms the only production change on `bf/alarms`
is `insulinInfo.urgent` → `prefs.urgent` on the `>=` line; the `===` line is untouched. The shape
is the same in all four plugins (`insulinage`, `cannulaage`, `sensorage`, `batteryage`) and at all
three levels (info, warn, urgent), and the three siblings have shipped with it for years.

**Reproduced 2026-09-23** ([evidence](../../60-research/remedial/bf52-age-push-once-2026-09-23.md)):
a sequence test that drives each plugin the way `bootevent.js` does is red on `74fc6619` (17
failing) and on `15.0.8`.

**Decided 2026-09-23 (maintainer)**: the reminder is sent once even if the window is missed, which
makes the current behaviour a defect (graded `medium`). **Fixed** on local branch
`bf3/age-push-once` `896629f8` (not pushed): `lib/plugins/agenotify.js` remembers, per plugin
instance and per change event, which levels have been requested, and requests a missed level once.
Nothing that fires today stops firing. Suite 2410/0/3 on Node 20 and 22; with the fix reverted, 17
red. One `sensorage` test expectation changed because it asserted the defect, and the README's
`*_ENABLE_ALERTS` and `IAGE_URGENT` entries changed. For the reviewer: the record is in memory, so a
restart re-sends one reminder for an item already overdue, and the first check after upgrading
sends one for each overdue item. **Deferred (maintainer, 2026-09-23)**: not in 15.0.9; it ships in
a later release, paired with BF-92, after delivery through `pushnotify` and Pushover is measured.

### BF-53 · the documented test commands do not run the test under review

Two separate defects with one consequence.

**(a) The scripts do not cover the suite.** On `origin/dev` `a8888f0d` there are **159**
`tests/*.test.js`. `npm run test:unit` is a brace list resolving to **44** files;
`test:integration` to **89**. The union is **107**, leaving **52** files run by neither. Measured by
expanding both brace lists with bash `shopt -s nullglob` in a worktree at that commit and using
`comm -23` against the full glob.

Among the 52 are the only tests for this batch's own findings —
`tests/boluscalc.quickpick.test.js` (**BF-35**, high), `tests/receiveddata.merge.test.js` (BF-36),
`tests/browser-utils.queryparms.test.js` (BF-37) and `tests/dataloader.test.js` (the `bf/cache`
change). **Demonstrated in practice**: `bf/food`'s `npm run test:unit` returned 361 passing / 0
failing while never loading BF-35's test.

**(b) A single-file run is not a single-file run.** `npm test -- tests/x.test.js` **appends** the
argument to the script's own `./tests/*.test.js` glob, so it runs the whole tree *plus* the named
file, loaded twice. Two consequences: a per-file gate cannot be read red-or-green for its own
subject, and a "must fail today" gate reports failure for any unrelated reason — and the baseline
with no `mongod` running is already 6 failing.

**This is not a CI gap.** `.github/workflows/main.yml` runs `npm run-script test-ci`, which is
`mocha … ./tests/*.test.js` over all 159. The hole is in the local scripts and therefore in every
contributor's and every agent's loop.

**Also measured**: `npm run test:unit` is **not** database-free. With
no `mongod` reachable it fails 6 tests (`verifyauth` ×4, `API_SECRET` ×2) on pristine `dev`.

**Fix — UNVERIFIED.** Either make the two scripts partition the 159 files, or add a `test:file`
script that does not carry its own glob. Whichever is chosen, the check that it worked is a file
count, not a green run.

### BF-54 · the treatment-drag clamps are unexercised, and deleting them is invisible

```js
lib/client/renderer.js:766        Math.min(Math.max(0, event.x), chart().charts.attr('width'))
lib/client/renderer.js:772-773    Math.min(Math.max(0, event.y), chart().focusHeight)
```

*Line numbers are `origin/dev` `74fc6619`; `v15.0.8` has the clamps at `:764` and `:770-771`,
where they read `d3.event`.*

**Reproduced by deliberate breakage** on an isolated copy of `origin/dev`: replacing both with the
raw `event.x`/`event.y` — substitution confirmed applied, grep count 2 → 0 — leaves
`tests/dependency-d3.test.js` at **24 passing, 0 failing**.

**It is the second vacuity mode, and instrumentation says which.** The drag handler is invoked 25
times, but with only two `x` values (20, 400) and three `y` values (20, 150, 380), every one
strictly inside 0..900 and 0..399. The clamp executes on every call and its boundary is never
reached: the code distinguishes the branches; the corpus never exercises the property.

**Why the clamps are load-bearing.** The clamped `x` feeds
`newTime = new Date(chart().xScale.invert(x))`, and the drag-end handler with operation `Move`
emits `socket.emit('dbUpdate', {collection:'treatments', _id, data:{created_at: newTime.toISOString()}})`.
The same clamped `x`/`y` select the drop-zone operation — *Remove*, *Remove insulin*, *Remove
carbs*, *Move carbs*, *Move insulin* — via `isInRect`. **A treatment's timestamp is what IOB and
COB key off.** These are also the exact lines the D3 6 event-object migration rewrote
(`d3.event.x` → `event.x`), i.e. the least covered lines that migration touched.

**No defect in shipping behaviour was reproduced.** The clamps are present and correct today.

**Fix — UNVERIFIED but cheap**: two cases dragging to `x = -50` and `x = 1200`, asserting
`newTime` stays inside the chart window. Both currently pass with the clamps deleted, which is the
whole point.

**Coverage that does exist.** `tests/dependency-d3.test.js` is 218 lines driving the real renderer and chart against the D3 7
browser bundle, 24 passing, and verified non-vacuous by deliberate breakage at the migration's core
hazard — reverting mouseover handlers to the D3-5 signature is caught, breaking `d3.pointer` in
`chart.js` is caught. The real gap is narrower and sharper: jsdom's stubbed geometry (the fixture's
own comment says "jsdom has no SVG animated width/height"; `getBoundingClientRect` is stubbed to
900×600), plus these two clamps.

### BF-55 · merging a cut deletes the only test for a fix shipping in 15.0.9

`git merge-tree --write-tree origin/dev origin/chore/retire-jsdom` reports
`CONFLICT (modify/delete): tests/clock-client.test.js` — deleted on the cut, modified on `dev`.

`dev`'s commit `06372e1d` ("show concern for low and falling clock readings") changes
`lib/client/clock-client.js` (+5/−1) and adds **+56 lines of test** covering the low-and-falling
concern face across six falling directions, five non-falling directions, both unit systems and a
stale-reading case.

Cut 1's replacement `tests/browser/clock-client.test.js` is 116 lines covering face-component
construction and markup/XSS injection. `grep -ciE 'concern|falling'` returns **0** against it, with
`dev`'s file as positive control returning **3**.

`lib/client/clock-client.js` is **not touched by cut 1**, so the production fix auto-merges
silently and only its test disappears. **Resolving the conflict by taking either side is wrong**:
the deletion is correct (jsdom retirement) and the 56 lines must be ported into the Playwright
suite. Applies identically to cuts 2, 3 and 4, which all contain cut 1.

**Related and undercosted**: "run the modernization branch's browser suite against the release tree
— one CI run plus a cherry-pick of `tests/browser/`" is not a one-CI-run task. Cut 1 also deletes
`tests/dependency-d3.test.js`, `tests/fixtures/d3.js`, `tests/fixtures/d3-chart.js` and
`tests/client.renderer.test.js`, and its `tests/browser/chart-interactions.test.js` requires
`./fixture` (playwright-core), `./modules` (`buildModules`) and `./hooks.js`. Running it against
`dev` means porting the Playwright harness and its module-building fixture onto a tree that has
neither. It is still the strongest option.

### BF-56 · merging a cut silently reverts dev-only changes

Root cause: cuts 1-4 are each **133 commits behind** `origin/dev` `74fc6619` and conflict against
it in 7, 14, 16 and 18 paths (2026-09-22; queue `RT-REBASE` re-measures). The cut tips date to
2026-09-05/06, so a rebase has been needed since `dev` moved on 2026-09-09.

Two of the conflict hunks were read out of the written tree object:

| file | `dev` side | cut 1 side | taking either side wholesale |
|---|---|---|---|
| `package.json` lines 137-142 | `mongomock` + the `234d47c8` connector tarball | the **v0.0.13 tag** tarball | keeping cut 1's rolls the connector **back past the log-narrowing commit into the tree BF-42 describes** |
| `lib/server/bootevent.js` lines 328-347 | a bare connector `require` | a guard that skips the connector when no source is configured | keeping `dev`'s drops the guard |

Separately, an env census over `readENV*` in `lib/server/env.js` gives `master` 30 names and `dev`
32 — the delta being exactly **`CONNECT_DEBUG` and `DEBUG_LOGGING`**, both of which disappear from
an operator upgrading `dev` → cut 1. Reproduced by
`tools/qc/semver-surface-gate.js --base origin/dev --head origin/chore/retire-jsdom`, which reports
`env vars REMOVED (accepted-and-ignored risk)` and `nightscout-connect pin moved`.

**Not reproduced against a running deployment.** **It is also possible the train assumes a merge of
`dev` into each cut before release**, in which case this is a fact about the branches rather than a
defect in the plan. Nobody has written that assumption down, and that is the open question attached
to this entry.

### BF-57 · the largest chart-adjacent change on `dev` has no line in the release decision

`git show --numstat 48075a18` ("Migrate charts to D3 7") touches exactly three production files:
`lib/client/renderer.js` (+25/−25), `lib/client/chart.js` (+2/−2), `lib/report_plugins/daytoday.js`
(+3/−3). Release-readiness §2 attributes five files to it. The other two are not D3 work:
`lib/plugins/loop.js` is `893e50bb` and `lib/client/clock-client.js` is `06372e1d` — and
**`lib/plugins/cob.js` (+49/−73) is `34e9b2da`, "fix(cob): use the COB reported by the uploading
system"**. §2 presented per-file `master`→`dev` aggregates as one commit's diff.

The error cuts both ways. The genuine D3 blast radius is **smaller** than stated (3 files, 30
lines). But the mistake **buries** a separate, larger, unreviewed behaviour change: at +49/−73,
`cob.js` is more than twice the size of the entire D3 migration and currently has no line of its own
in the 15.0.9 release decision.

**The COB change itself was not audited and no claim is made that it is wrong** — which is exactly
why the severity is `unsettled`. The defect asserted is that it is invisible to the decision because
it is described as part of something else. It carries the stack's governance profile: single author,
no human review.

**Carbs-on-board feeds what a person reads when deciding about food and a correction.** It warrants
its own review line before 15.0.9 is cut.

### BF-58 · a floating base image against a patch floor

`Dockerfile` is `FROM node:22-alpine` for builder and runtime on `origin/dev` **and** on every
cut, while cuts 1-5 declare `engines.node = "^22.23.2 || ^24.20.0"` and
`lib/server/runtime-policy.js` calls `semver.satisfies(process.version, supported)` followed by
`process.exit(1)`, invoked from `lib/server/server.js` before configuration load. `origin/dev` is
unaffected — its floor is `>=20.x`.

**Reproduced 2026-09-21 inside the image**: the floating tag resolved to a 22.x patch below the
floor, so a container built from cut 1's own Dockerfile exits 1 at boot:

```
$ docker run --rm node:22-alpine node --version
v22.22.0
$ docker run --rm -v "$PWD":/app:ro -w /app node:22-alpine \
    node -e "require('./lib/server/runtime-policy.js')()"
ERROR: Node v22.22.0 is not supported. Nightscout requires Node ^22.23.2 || ^24.20.0.
exit 1
```

The same holds for all five cuts (measured across all five refs). Pushing to `dev` or `master`
fires `main.yml`'s `docker-build` job and publishes to Docker Hub, so merging a cut would *publish*
the non-booting image rather than merely fail CI. The boundary is exactly what it declares,
reproduced via `n exec` on six versions: 20.20.0, 22.12.0, 22.22.0 and 24.15.0 are refused;
22.23.2 and 24.20.0 boot, confirmed through `lib/server/server.js` (the `npm start` entry).

**The defect is the floor, not the image.** With `runtime-policy.js` stubbed to a no-op, measured
2026-09-21:

| Node | cut 4 unit suite | cut 1 Playwright suite |
|---|---|---|
| 24.20.0 | **310 passing / 0 failing** | — |
| 24.15.0 | **310 / 0** | — |
| 22.23.2 *(declared floor)* | **310 / 0** | — |
| 22.22.0 *(what `node:22-alpine` was)* | **310 / 0** | — |
| 22.12.0 | **310 / 0** | **21 / 0** |
| 20.20.0 | **310 / 0** | **21 / 0** |
| 18.20.8 | 295 / **15 failing** | — |

The only break is at 18, and all 15 failures are `ERR_REQUIRE_ESM` from `sanitize-html` requiring
the ESM-only `htmlparser2`; `require(esm)` is unflagged in 22.12 and backported to 20.19. So the
dependency-derived floor is about `^20.19 || ^22.12 || >=24`, and the declared floor excludes a
working major line and eleven working 22.x patches. `docs/runtime-upgrade.md`, from the same commit
(`a95c2ce5`, 2026-09-05), says the minimum patches *"reflect the supported release baseline at the
time of this change"*, and states the image should track *"the official major tag"*: the floor and
the documented image strategy are incompatible. The maintainer's position is that Node
compatibility has historically been good and over-restricting has harmed the project; fixing the
image tag alone would hide the finding. See queue item RT-NODE-FLOOR-TESTED.

**Fixed 2026-09-21** on the local rebase branches `rt/cut1`…`rt/cut4` (`ed21961f` and its merges up
the stack, not pushed): `engines.node` is `^22.12 || >=24` on the maintainer's decision, the
Dockerfile is untouched, and `node:22-alpine` boots, verified inside the image.
`tools/queue/gates/node-floor-consistency.js`, which reads both files out of the git object
database, is 9/9 green against each prepared cut and red against the published refs.

**Docker is the primary distribution path**, so the symptom — container starts, prints the
runtime-policy message, exits — should be **named in the release notes** of any release carrying a
patch floor, so an operator recognises it rather than assuming data loss.

**Partial mitigation in CI**: from cut 1 onward the `docker-build-pr` job builds the image and runs
`docker run --rm "$IMAGE" node -e "require('./lib/server/runtime-policy')(); …"` against it, plus a
start-up smoke test. The `docker-build` job that **publishes** to Docker Hub on `master`/`dev` has
no such step and builds with `no-cache: true`, so it re-resolves `node:22-alpine` at publish time
without re-validating.

### BF-59 · CI stops testing the floor it enforces

> **Measured 2026-09-21**: there is no regression at the boundary today. Cut 4's unit suite is
> **310 passing / 0 failing on 22.23.2** — the exact floor cuts 3-5 dropped from the matrix — and
> **310 passing on 24.20.0**; cut 1, whose matrix still carries both floors, gives the same count
> on each. Measured with `n exec`, mongod 7.0.43, against the locally rebased `rt/cut1`…`rt/cut4`
> (RT-REBASE). **Fixed 2026-09-21** on those branches (not pushed) by removing the subject: with
> `engines` at minor precision (`^22.12 || >=24`) there is no patch boundary left to guard, so every
> job tests `['22','24']`.

Read from each ref's `main.yml` test-job matrix: cuts 1 and 2 use
`node-version: ['22.23.2','22','24.20.0','24']`; cuts 3, 4 and 5 use `['22','24']`. The two version
numbers the software refuses to start below are exercised by **no test job** from cut 3 on.

`engines` is byte-identical across all five cuts, so this is **lost coverage rather than a changed
requirement**.

### BF-60 · fifteen refs, one version string, two Node floors

`git show <ref>:package.json` parsed at sixteen refs:

| refs | `version` | `engines.node` |
|---|---|---|
| `origin/master` | 15.0.8 | `>=20.x` |
| `origin/dev` and all nine `bf/*` branches | **15.0.9** | `>=20.x` |
| all five `chore/*` cut tips | **15.0.9** | `^22.23.2 \|\| ^24.20.0` |

Two artefacts claim the same version string with different runtime requirements, and one of them
deletes two CGM ingestion paths. An operator reporting "my 15.0.9 will not start" cannot be triaged
from the string.

**Compounded**: both cut-4 migration shims emit error text saying "retired in Nightscout 15.0.9",
while on the adopted train 15.0.9 is the bug-fix release and retires nothing — so an operator who
reads that message and checks the release notes finds a contradiction. (Precisely: the exact string
"retired in Nightscout 15.0.9" occurs three times; two further `bootevent.js` log lines say
"retired in 15.0.9".)

**Severity medium, not high, because no released artefact is affected today** — `master` alone is
released, at 15.0.8. The fix is one pre-release identifier per branch and it closes the problem
completely. It should land **before** any of these branches is tagged, not after.

### BF-61 · cut 4 takes the whole site down for an unprepared MiniMed operator

**Reproduced** by executing `chore/mime-exposure-review:lib/server/mmconnect-connect-compat.js`
under node in four environment shapes, using the real `env.extendedSettings.{bridge,mmconnect,connect}`
shape rather than flat process-env names.

| shape | result |
|---|---|
| `MMCONNECT_*` set, no `CONNECT_COUNTRY_CODE` | `{migrated:false, error:'…Set CONNECT_COUNTRY_CODE… The country cannot be inferred from MMCONNECT_SERVER.'}` → **boot error** |
| `BRIDGE_*` and `MMCONNECT_*` both set (**works today**) | bridge shim sets `connect.source='dexcomshare'`, then the mmconnect shim refuses: "cannot run alongside a different CONNECT_SOURCE" → **boot error** |
| two control shapes | clean |

**The consequence is worse than losing ingestion.** `setupConnect` pushes the error onto
`ctx.bootErrors`; `lib/server/app.js:202` then installs `app.get('*', bootErrorView)` **and
returns**, while `lib/server/server.js:61` returns before websocket setup. The deployment serves the
boot-error page for every route: no API, no sockets, no charts, no data.

Two things follow that no summary of cut 4 carries:

1. **No MMCONNECT operator can upgrade without manual reconfiguration**, because the shim itself
   states the country cannot be inferred — and `mmconnect-connect-compat.js` does not exist on `dev`
   or `master`, so no release warns them first. The only MiniMed warning shipping today is a generic
   "PLEASE CONSIDER nightscout-connect instead." naming no setting. (Dexcom is the opposite case:
   `bridge-connect-compat.js` is on master and dev already, and `dev` prints five `DEPRECATION
   WARNING` lines, one naming `DEXCOM_BRIDGE_USE_LEGACY`.)
2. **Concurrent multi-source CGM ingestion is removed** — two independent boot stages today become
   one `CONNECT_SOURCE` with nowhere for the second source to go.

**Decided 2026-09-23 (maintainer): the hard stop is intended.** These settings are usually a
site's primary source of data, so a misconfigured one should stop the site with a page that says
what to fix, the same convention `checkSettings` uses for `MONGODB_URI` and `API_SECRET`. What the
decision requires of the removal:

1. **The fix the page names must be enough.** The 15.0.9-rc rehearsal (`cut-rehearsal-on-15.0.9-rc-2026-09-23.md`
   §4.5) measured that setting `CONNECT_COUNTRY_CODE` still leaves the error page unless `connect`
   is also in `ENABLE`. Either the migration enables `connect` or the message names both.
2. **The messages must not say "retired in Nightscout 15.0.9".**
3. **BF-63's renderer guard** stays (in `dev` via PR #8753), so the page shows the message.
4. **The RT-5 gate's pass condition changes** from "no shape produces a boot error" to "each shape
   that stops the site names its fix, and applying that fix boots".

**Fixed 2026-09-23** on local `rh/cut1-retire-legacy` (`c043fb2d`, not pushed), where the removal
now lives (lifted onto cut 1): items 1, 2 and 4 are done; in the boot matrix each stopping shape's
named fix boots 200/401/401; the rewritten gate is green there and red on `rh/cut4`
([cut 1 lift](../../60-research/modernization/cut1-legacy-bridge-lift-2026-09-23.md)). RT-4, a
deprecation release keeping the legacy plugin running, was dropped 2026-09-23; the deprecation
notice is in 15.0.9's release notes.

### BF-62 · a setting the previous release told operators to set is now ignored

Cut 4 deletes `bridgeUseLegacy` from `bridge-connect-compat.js` and deletes the `bootevent.js` line
that logged it, so `DEXCOM_BRIDGE_USE_LEGACY` becomes accepted-and-ignored — after `dev`'s own
`DEPRECATION WARNING` instructed operators to set exactly that variable.

**Checked specifically, and it is the reason this is low and not high**: Dexcom credentials are
still migrated to Connect unconditionally, so **ingestion continues**. This is not a
data-availability failure. What is discarded is the operator's expressed intent, silently.

**Fixed 2026-09-23** on local `rh/cut1-retire-legacy` (`c043fb2d`, not pushed): the override is
logged as ignored and Dexcom still migrates; regression test with break-it
([cut 1 lift](../../60-research/modernization/cut1-legacy-bridge-lift-2026-09-23.md)).

### BF-63 · the page that reports a boot error crashes on cut 4's boot errors

`lib/server/booterror.js`'s error-line map calls `pick(obj.err, Object.getOwnPropertyNames(obj.err))`.
The argument is evaluated **before** `pick()`'s null guard runs, so a boot error with no `err` key
throws `TypeError: Cannot convert undefined or null to object`.

**Reproduced** by running the renderer's map over five boot-error shapes with cut 4's own
`lib/utils/pick.js`:

| shape | result |
|---|---|
| `{desc:'CONNECT_COUNTRY_CODE is required'}` | **TypeError** |
| `{desc, err:null}` | **TypeError** |
| `{desc, err:'econnrefused'}` (the Mongo shape) | renders |
| `{desc, err:['a','b']}` (the ENV Error shape) | renders |
| `{desc, err:new Error('x')}` | renders |

Three controls render and only the two cut-4 shapes throw.

**Provenance**: `git diff origin/dev origin/chore/mime-exposure-review -- lib/server/booterror.js`
is **empty**. The renderer is unchanged and pre-existing; what cut 4 adds is the only two
`bootErrors.push` sites in the tree that omit `err` (`bootevent.js:330`, `:335`) — 7 such sites on
master and dev, all passing `err`; 9 on cut 4.

**Filed §1b because the two reachable shapes exist only on the unmerged branch** — but note that the
renderer weakness itself is in shipping code today, awaiting a caller.

**Fix, both halves**: make the renderer defensive, with a regression test asserting that a
`desc`-only boot error renders as HTML, **and** pass `err` at both call sites. This matters more
than an ordinary crash because the message it destroys is the mitigation for **BF-61**. **Partly
merged 2026-09-23**: the renderer half is in `dev` via PR #8753 (merge `3a38c6f2`); the other site,
cut 4's `pick.js`, is on the modernization branch only.

### BF-64 · the adopted release train describes a set of releases that cannot be built

The train is: 15.0.9 first, then cut 1, then cut 2, then **3+5 combined as a dependency release,
with cut 4 held back** behind a deprecation release.

**Reproduced**: `git merge-base --is-ancestor origin/chore/mime-exposure-review origin/chore/nightscout-modernization`
exits **0**; cut 5 is 154 commits past cut 4. Operator consequence confirmed directly rather than
inferred — `git cat-file -e <ref>:lib/plugins/bridge.js` and `:lib/plugins/mmconnect.js` succeed on
`origin/dev` and cut 3 and **fail** on cut 4 and cut 5, while `lib/server/mmconnect-connect-compat.js`
appears at cut 4 and persists into cut 5.

So the "dependency release" would ship **the CGM ingestion retirement one release early, and before
the deprecation release that exists to warn operators about it** — the single change this programme
has most consistently said to slow down on. Corroborating symptom: the connector pin would move
*backwards*, cut 5 pinning `b77e5bb` and cut 4 `c962a13f`, which is an ancestor of it.

**No branch is wrong.** The defect is in the description of how to combine them. It must be resolved
before Release 4's contents can be written down, and every document repeating the train needs the
caveat until it is. Options: stop the train at cut 3; ship cut 5 and accept that the retirement
lands with it; or revert cut 4's deletions out of cut 5, which is the only option that is not a
prefix cut.

**Maintainer direction 2026-09-23**: mmconnect is deprecated and removed as early as possible (it
does not work and carries deprecated dependencies), partly in the current cycle where appropriate;
with RT-4 dropped, 15.0.9's notes are the deprecation notice, so holding cut 4 behind a separate
release no longer applies. The removal is lifted onto cut 1 (local `rh/cut1-retire-legacy`, 8
cherry-picks); cut 4's remainder has no CGM-path removal, and a trial merge conflicts only in
legacy files and manifests ([cut 1 lift](../../60-research/modernization/cut1-legacy-bridge-lift-2026-09-23.md)).

### BF-65 · the train ships the leaking connector to upgraders first

`git show <ref>:package.json` on the three lower cut tips: **all three pin
`refs/tags/v0.0.13.tar.gz`** — the tree BF-42 describes, with no redaction and no guard. The adopted
train ships cut 1 and cut 2 **first** as low-blast-radius releases and holds cut 4 — which carries
most of the redaction — back longest.

So an operator upgrading to cut 1 or cut 2 as they stand moves from a leaking connector to the same
leaking connector, in a release whose stated selling point is that it is low-risk.

**The pins are measured; the ordering is quoted** from release-readiness §5 and was not re-derived
here, so this entry is an inference from combining the two. It is cheap to remove either way: all
three pin the v0.0.13 **tag**, so moving them to the connector release is the same one-line change as `dev`'s,
with no incomparability to reason about.

### BF-66 · the deployment's own tokens fail its own tenant check

`lib/authorization/index.js:289` mints a JWT with the payload `{accessToken}` and nothing else.
`grep -rn signJWT lib/ bin/` returns only `enclave.js:58` and that line, so there is no other minting
path.

**Reproduced** by executing both modules on `crm-seam` `81a1f6ce` with exactly that payload:
`tenantClaim` returns `null` and `credentialRefusal` returns *"This credential does not name a
Nightscout site."* **Control**: the identical token with a `tenant` field added returns `null` from
`credentialRefusal`, i.e. proceeds.

**It fails safe** — refusing rather than admitting — which is why it has gone unnoticed, and why the
severity is medium rather than high.

**Fix — UNVERIFIED, and it belongs to T3.0**, because the task that introduces the per-tenant signing
key (D14) is the task that chooses the payload. Fixing it separately would mean choosing the claim
twice.

### BF-67 · an alarm threshold is quietly changed and only the server log says so

`lib/settings.js` `verifyThresholds()` enforces `bgLow < bgTargetBottom < bgTargetTop < bgHigh`. It
does not reject a violation — it **rewrites** the offending value to its neighbour ±1 and calls
`console.warn` twice:

```js
if (thresholds.bgHigh <= thresholds.bgTargetTop) {
  console.warn('BG_HIGH(' + thresholds.bgHigh + ') was <= BG_TARGET_TOP(' + thresholds.bgTargetTop + ')');
  thresholds.bgHigh = thresholds.bgTargetTop + 1;
  console.warn('BG_HIGH is now ' + thresholds.bgHigh);
}
```

Defaults are `bgHigh 260 / bgTargetTop 180 / bgTargetBottom 80 / bgLow 55`, in mg/dL.

**The reachable case is a unit mix-up, which is the commonest configuration error there is.** An
operator who thinks in mmol/L and sets `BG_HIGH=14` is asking for an urgent high at 14 — in mg/dL
that is below `bgTargetTop`, so it is silently stored as **181**. They believe they have set a high
alarm and they have set a different one. The same applies at the bottom: `BG_LOW=90` against the
shipped `bgTargetBottom` of 80 is stored as `bgTargetBottom - 1 = 79`. The guard is one-sided: a
`BG_LOW` *below* its neighbour, such as an mmol/L `3.9`, is not rewritten at all (BF-86).

**The guard is right; the silence is the defect.** Refusing a contradictory threshold set at boot
would be defensible, and so would correcting it — but not with the only evidence on stdout, where a
self-hoster on a hosted platform may never see it. Grep over `lib/client/` and `views/` finds **no**
surface that reports the rewrite; the person sees the corrected number as though they had chosen it.

**Reproduced** in-process by `tools/queue/gates/threshold-silent-rewrite.js`, which loads the
shipping `lib/settings.js` with three controls (shipped defaults, a converted mmol set, a consistent
mg/dL set — none rewritten) and fails on the two rewrites above.

**Fix — NONE PRESCRIBED.** Whether to refuse, to correct-and-announce, or to unit-check the input is
a maintainer decision with a safety dimension. What is not defensible is the current combination: change the
number, tell only the log.

**Hosted-tenancy consequence**: it surfaced while reviewing the per-tenant configuration spec, whose
proposed `CHECK` constraint on stored thresholds was described as a backstop. It is not one — a
partial override leaves the absent paths SQL `NULL`, the `AND` chain evaluates to `NULL` rather than
`FALSE`, and PostgreSQL accepts the row. So under hosted tenancy the row would be stored *and then*
silently rewritten by this function. The defect is in shipping single-tenant code today; the hosted
design inherits it unless T3.0 decides otherwise.

### BF-68 · `$type`'s operand is a type code, and exempting it from conversion broke a working request

A regression introduced and repaired inside `bf/coercion` before PR #8737 was opened. The reasoning
generalises: *"operands are not values, so leave them alone"* is very nearly right, and `$type` is
the exception.

`bf/coercion`'s first draft routed field values through a schema-driven converter and exempted
every operator whose operand is not a field value — `$regex`, `$options`, `$text` and `$type` — on
the ground that converting a regular expression to a number is nonsense. It is. But **`$type`'s
operand has a type of its own**: MongoDB takes either a numeric BSON type code or a string alias.

Measured against live `mongod` **3.6.8 and 7.0.43, identical on both**:

| query reaches the server as | result |
|---|---|
| `{$type: 2}` (number) | valid — selects string-typed values |
| `{$type: "2"}` (string) | **error: *"Unknown type name alias: 2"*** |
| `{$type: "number"}` (alias) | valid |

15.0.8 converts `$type` along with everything else, so `find[sgv][$type]=2` **works on the
shipping release**. Exempting it would have turned that request into an **HTTP 500**.

**Fix.** `operandReaderFor` in `lib/server/query-coercion.js` gives each non-value operator its own
reader rather than a blanket exemption. A digits-only `$type` operand becomes a number; anything
else — `number`, `string`, `objectId` — passes through as the string MongoDB expects. `$regex`,
`$options` and `$text` keep the blanket exemption, because for them it is correct.

**Severity is low.** Numeric BSON type codes in a v1 filter are rare, and the alias spelling was
correct throughout. **It never shipped**: it existed only between two drafts of `bf/coercion` and
was repaired in `f829ea11` before PR #8737 was opened (merged 2026-09-18, merge `025f1310`). It is
recorded because the next person to add an operator exemption needs to know that the blanket form
is wrong.

**Pinned by test.** `tests/query.operands.test.js` asserts both spellings, and the branch's own
non-vacuity check confirms adding `$regex` to the reader map fails exactly the `$regex` test.

### BF-27 · one `env` object, and a secret that deletes itself once read

`lib/server/env.js` builds its result onto a **module-scope** `env` object, so `config()` returns the
same object to every caller. `setAPISecret()` reads `process.env.API_SECRET` and then **deletes it
from `process.env`**, so the secret cannot be read a second time.

The two together mean a *second* `config()` call hands back an enclave that was never armed — and,
before the rebind, disarmed the first caller's.

**Not reachable in production**: there is exactly one call site, `lib/server/server.js:33`. It is
reachable in the test suite, where **62 files call `config()`**, which is how it was found.

**Why it stays in the register at `low` rather than being closed**: under `TENANCY_MODE=multi` the
"one process, one configuration object" assumption is the thing being removed, and a module-scope
singleton that self-destructs its own credential source is exactly the shape D15 exists to stop. It
is a live trap for T3.0's wiring step, not for an operator.

**No fix is prescribed** and none should be until T3.0 decides where configuration comes from, since
the obvious local fix — return a fresh object per call — changes what 62 test files share.


### BF-70 · the count endpoint took its aggregation pipeline from the URL — **merged 2026-09-18** (PR #8743)

> **DISCLOSURE FIRST. Read this paragraph before quoting the rest anywhere public.** This is an
> **unauthenticated read oracle over arbitrary collections**, live on the shipping release 15.0.8,
> and **this repository is public**. The fix is public in `dev` (PR #8743). The working
> reproduction is deliberately **not committed** — not here, not in the branch, not in the report;
> it is held outside version control. What is withheld is a copy-paste recipe against other
> people's deployments: describe the mechanism, never a request.

**Found 2026-09-18 while tracing BF-04's blast radius.**

`lib/server/aggregate.js` built its aggregation as

```js
[{$match: <find>}].concat(conf.pipeline || []).concat(opts.pipeline || [])
```

and `opts` is the caller's parsed query string — `count_records` at `lib/api/entries/index.js:519`
passes `req.query` straight to `storage.aggregate()`. So `GET /api/v1/count/:storage/where`
accepted arbitrary **aggregation stages** from the URL, not merely filter operators.

**Why that is a different class of problem from BF-04.** A `find` filter selects within the
collection the endpoint is about. An aggregation pipeline does not: it can read *other*
collections, and the count this module appends is returned under HTTP 200, which made the endpoint
an oracle over any collection in the database, including the auth collections.

- **Unauthenticated.** The route needs `api:entries:read`, which `AUTH_DEFAULT_ROLES=readable` —
  the shipped default — grants with no token.
- **Undocumented.** `pipeline` is in neither `swagger.yaml` nor `swagger.json` nor the README, and
  appears in no client in the [14-project census](../../60-research/tenancy/v1-operator-census-2026-09-14.md).
- **Unused in-tree.** `conf.pipeline` is `{}` at all three construction sites — `entries.js:216`,
  `treatments.js:437`, `devicestatus.js:160` — so nothing in this tree supplies one either.
- **Writes are blocked by accident, not design.** Write-capable stages are excluded only by the
  order in which the module assembles the pipeline. Nothing asserts that ordering.

**Reproduced 2026-09-18**, `reproduced` not `derived`: through the booted v1 app against
`mongod 7.0`, with no `api-secret` header, a value seeded into the auth collection was recovered
character by character from the count alone. The same probe against `bf/operators` `52b7b640`
returns HTTP 400 and recovers nothing — same machine, same database, same session.

**Fix**: the parameter is **refused with 400, not dropped**. Dropping it silently would answer a
different question under HTTP 200, which is the failure mode the whole `bf/operators` branch exists
to remove. `conf.pipeline` is kept, still works, and now gets a backstop pass through the
JavaScript guard, because it is the only remaining way a stage reaches the pipeline.

**Interaction with `bf/reads`**: that branch (BF-01, BF-05) edits the same function, so the two
conflict on this file. The conflict is mechanical, both edits compose, and the resolution is
written out in the report §4.2 rather than left to be rediscovered. Merged and measured: 2172
passing, 3 pending, 0 failing.

*Evidence*:
[BF-04/BF-70 report](../../60-research/remedial/bf04-bf70-operator-allowlist-2026-09-18.md) §3.
Merged 2026-09-18 via PR **#8743** (merge `1a36f023`); re-verified on the branch's `dev` merge
`9745cae2` — the probe still returns 400 and recovers nothing.


### BF-71 · the date window is dropped by any `dateString` key — and is not a control

The advisory calls this path its primary evidence and a full-history data dump. Run with a control,
it is a correctness defect and not a privilege boundary (below).

**The mechanism.** `enforceDateFilter()` applies its default bound only when nothing else has
constrained the date:

```js
if (!dateValue && !query.dateString && true !== opts.noDateFilter) {
  var minDate = Date.now( ) - opts.deltaAgo;
  query[opts.dateField] = { $gte: ... };
}
```

`dateValue` is `query[opts.dateField]`. The second test is a bare **presence check** on a different
field, so the operator involved is irrelevant — the default is dropped by `$ne`, by `$exists`, by
`$gte`, by `$regex`, by anything that puts a `dateString` key in the query. Refusing `$ne` would
not touch it, and no operator allowlist can: the key, not the operand, is what disables the bound.

**What it is not, measured.** `opts.deltaAgo` defaults to `TWO_DAYS * 2` at `lib/server/query.js:47`
under the comment `// TODO: discuss/consensus on right value/ENV?`. It is a paging default. The
control ran in the same process, on the same seed, against the same `mongod`:

| unauthenticated request | `readable` (shipped default) | `denied` |
|---|---|---|
| plain read, no filter | 200, **3 of 10** — window applies | 401 |
| **control** `find[date][$gte]=0` — allowlisted, documented | 200, **10 of 10** | 401 |
| `find[dateString][$ne]=x` | 200, **10 of 10** | 401 |
| `find[dateString][$exists]=true` | 200, **10 of 10** | 401 |
| `find[dateString][$regex]=.` | 200, **10 of 10** | 401 |

Three entries were seeded inside the window and seven outside it, the furthest 700 days back. The
control line is the finding: **an ordinary documented filter reaches the identical record set on the
identical authorisation.** And every form, the control included, is 401 once
`AUTH_DEFAULT_ROLES=denied` — authorisation runs before the query is built, so nothing here touches
it.

So the outcome the advisory describes is real — an unauthenticated caller can read the full history
of a default install — but the cause is not this code path. **The cause is that
`AUTH_DEFAULT_ROLES=readable` is the shipped default** (`lib/settings.js:39`, documented at
`README.md:243`), which means exactly that. Calling the `dateString` path a bypass implies a
boundary it is standing on, and there is no boundary: closing it would change nothing an operator
is exposed to.

**What is still worth fixing, and why it is `low` and not `none`.** Two ways of expressing the same
intent are not equivalent — one constrains the window and the other silently removes it — and the
asymmetry is invisible at the call site. A tenancy or quota layer that assumed `deltaAgo` bounded
the work a single anonymous request could cause would be wrong, and BF-72 is the case where the
size of that scan is what matters. Fix it as correctness: test `dateString` the way `dateValue` is
tested, or bound on whichever date field the query actually names.

*Reproduced* 2026-09-21 on `dev` `59430336`, booted v1 app, `mongod 7.0.43`, no `api-secret`
header, both role settings in one run. Probe held outside version control with BF-72's; nothing
about BF-71 itself is exploit-grade.

**Independently corroborated the same day** by
[the advisory auth-configuration matrix](../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md),
which booted one instance per configuration and tabulated fourteen anonymous requests across five
`AUTH_DEFAULT_ROLES` settings: `GET /api/v1/count/entries/where` answers 200 under `readable` and
**401 under `denied`**, as does every other v1 and v2 data route including `status.json`. It grades
this against the advisory it came from, `GHSA-r3gv-x7fw-j2v5`, and finds the `$where` half is what
survives.

### BF-72 · an unauthenticated `$regex` can spend minutes of database CPU

> **DISCLOSURE FIRST. Read this paragraph before quoting the rest anywhere public.** This is a
> **one-request unauthenticated denial of service against a default install**, live on the
> shipping release and on `dev`, and **this repository is public**. The mechanism is below; the
> three patterns that produce it are **deliberately not written down here**, and the probe is held
> outside version control twice over, as BF-70's is.

**Found 2026-09-21 while re-measuring the advisory's third PoC.** It is not the defect the advisory
describes there.

`$regex` (with `$options`) is in API v1's accept set **on purpose** — the 14-project client census
found real clients sending it, and a documented text-search affordance depends on it. So this is not an
injection and #8743 did not narrow it: the operator is meant to be there. What is missing is any
bound on the *pattern*. A caller-supplied string becomes a `mongod` regular expression with no
anchoring requirement, no length cap and no complexity limit, and `mongod`'s `$regex` implementation
backtracks. Evaluated across a collection scan, a short, suitably constructed pattern costs
superlinear time per document.

**Measured**, 20 000 seeded entries, `mongod 7.0.43`, one unauthenticated `GET` each, on
`/api/v1/count/entries/where`:

| request | wall time |
|---|---|
| control — same scan, no `$regex` | **22 ms** |
| benign anchored prefix `^a` | **29 ms** |
| nested-quantifier pattern A | **71 s** |
| nested-quantifier pattern B | **60 s** |
| nested-quantifier pattern C | **65 s** |

Stable across two independent runs. That is a **2 700×** amplification from a single short request
with no token, and it needs no unusual configuration: `AUTH_DEFAULT_ROLES=readable` is the shipped
default, the route needs only `api:entries:read`, and any v1 read path accepts the operator — the
count endpoint is convenient for measuring, not required. A real site's `entries` collection is far
larger than 20 000 documents.

**Why this is filed as availability and not exposure.** The collections a scan can reach —
`entries`, `treatments`, `devicestatus`, the three `prep_storage` admits — are already fully
readable on that default, and the API returns whole documents, so `$regex` reveals nothing a plain
read does not. Treating it as a data-extraction oracle, which is how the advisory frames PoC C,
overstates one half and misses the other. What it costs is the site's availability: Nightscout is
the screen someone looks at to decide about insulin, and a site that stops answering is the
failure that matters.

**Of the advisory's three PoCs this is the one that survives.** PoC A (`$where`) is closed by
#8743; PoC B is BF-71 and is not a boundary.

**On a fix, and what makes it hard.** The operator cannot simply be refused — clients use it, and
a documented search affordance depends on it. The candidates are a pattern length cap, requiring a
literal prefix, rejecting catastrophic-backtracking constructs, or moving to a linear-time engine; each trades
capability for cost and **none of them has been measured**, so no fix is claimed here. State:
reproduced, unfixed, and the remedy is a decision about the search affordance's contract.

*Reproduced* 2026-09-21 on `dev` `59430336`; unchanged on `origin/master` by inspection — the
allowlist admits `$regex` on both refs and the route exists on both — **not** separately timed
there.

**Severity context.** The two socket-surface disclosures that no configuration stops, measured
in [the advisory auth-configuration matrix](../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md),
are **BF-79** (`loadRetro`) and **BF-75** (`/alarm` delivery). Both disclose patient data and
outrank this availability defect; both are merged to `dev` and still present on 15.0.8.

### BF-73 · the production error page hands back a stack trace and absolute paths

> **DISCLOSURE FIRST.** This is live on the shipping release and on `dev`, and this repository is
> public. The mechanism below *is* the remedy — one commented-out line — so withholding it would
> withhold the fix. What is deliberately not written down is the request that triggers it, and the
> probe is held outside version control.

**Found 2026-09-21** while measuring `lib/server/purifier.js`'s size bounds for the two stored-XSS
advisories (GHSA-5mrq-gpqw-q5v5, GHSA-mjp4-84fw-gj4v). It is not either advisory's defect.

`lib/server/app.js` mounts express's `errorhandler` with its environment guard commented out:

```js
// Handle errors with express's errorhandler, to display more readable error messages.
var errorhandler = require('errorhandler');
//if (process.env.NODE_ENV === 'development') {
app.use(errorhandler());
//}
```

Byte-identical at `v15.0.7:343`, `v15.0.8:388` and `dev:388`. `errorhandler`'s HTML response
includes the exception message in the `<title>` and an `<ul id="stacktrace">` listing frames with
**absolute filesystem paths**. With `NODE_ENV=production` explicitly set, the instance still
returns it.

**Why it matters now.** The hardening that closes the two XSS
advisories added a new uncaught exception in `lib/server/purifier.js`, and that throw propagates
out of the v1 REST path uncaught (trigger held in the evidence doc's non-public probe). Measured on `dev` `59430336`: the response
body named `lib/server/purifier.js` by absolute path along with the deployment's directory
layout. So a fix for one class of defect created a convenient trigger for another.

**Scope, measured rather than assumed.** Seven malformed-query probes against the *unauthenticated*
v1 read surface on `dev` returned either 400 or a handled `{"status":500,"message":"Mongo Error"}`
JSON body — **none** leaked a stack. So this is not an unauthenticated finding on the evidence
gathered; it costs a write credential (`api-secret`, or a v3 token with create). No exhaustive
search for an unauthenticated trigger was made.

**Remedy, and why no patch is attached.** Restore the `NODE_ENV` guard, or replace `errorhandler`
with a handler that logs server-side and returns a bare 500. Either is one line. It is not written
here because the guard is **commented out deliberately and has been for at least seven years** —
`git log -L` carries the exact four lines, comment markers and all, through `7947e300` (2019-07-29,
"feat: API improvements", #4806), which only moved them. Somebody wanted the readable error page in
production, and restoring the guard takes that away from every operator who has been debugging with
it. That is a decision about the deployment's contract, not a typo, and it belongs to whoever owns
that contract. Filed, reproduced, unfixed.

Evidence: [GHSA XSS pair verification](../../60-research/remedial/ghsa-xss-pair-verification-2026-09-21.md) §5.2 and §6.1.

### BF-74 · API v3 `settings` writes skip the purifier that every other collection gets

`lib/api3/shared/writePurifier.js` — added in `72a2257e`, the commit that closes
GHSA-mjp4-84fw-gj4v's root cause — declares:

```js
const PURIFIED_COLLECTIONS = [
  'devicestatus', 'entries', 'food', 'profile', 'treatments'
];
```

`lib/api3/index.js:67` enables six collections: those five **and `settings`**. `settings` is the
only enabled collection the purifier does not cover, and the file carries no comment explaining
the omission.

**Measured**, 2026-09-21, real v3 JWT against a booted instance of each ref, document read back
directly out of `mongod 7.0`:

| ref | `POST /api/v3/treatments` | `POST /api/v3/settings` |
|---|---|---|
| `v15.0.7` | `onerror` survives | `onerror` survives |
| `v15.0.8` | sanitized | **`onerror` survives** |
| `dev` `59430336` | sanitized | **`onerror` survives** |

The treatments column is the control that proves the purifier is wired up and working on those
refs; the settings column is the finding.

**Why this is low and not an XSS.** There is no first-party sink. `grep` over `lib/client/`,
`lib/report_plugins/` and `views/` finds **no consumer** of the v3 `settings` collection anywhere
in cgm-remote-monitor — it is storage that third-party apps write and read. Whatever they do with
it at render time is theirs. The finding here is the asymmetry, not a demonstrated execution.

**No fix is proposed, deliberately.** `settings` holds UI configuration, and `sanitize-html`'s
serializer rewrites entities; running it over configuration values could corrupt them in ways that
are worse than the gap. Whether to purify, to purify selectively, or to document the collection as
unsanitized is a decision about the collection's contract, and nobody has made it.

Evidence: [GHSA XSS pair verification](../../60-research/remedial/ghsa-xss-pair-verification-2026-09-21.md) §2.1, §4 and §6.2.

### BF-75 · the `/alarm` namespace broadcasts medical data to every socket connected to it

> **DISCLOSURE FIRST. Read this paragraph before quoting the rest anywhere public.** This is a
> **live unauthenticated disclosure of medical data on the shipping release 15.0.8**, with no
> released patched version (the fix is in `dev`, PR #8745), and **this repository is public**. The mechanism is below because an operator
> cannot act on a defect they cannot recognise and the fix is three lines they can read. The
> **probes, the seeding script and the harness are held outside version control** and are not
> reproduced here or in the evidence document.

**The mechanism.** `lib/api3/alarmSocket.js` accepts every connection to `/alarm` (`:36`), and
`emitNotification` (`:178`) delivers all five event classes with `self.namespace.emit(...)`. So
delivery depends on neither having subscribed nor being entitled to read.

`self.subscribe` (`:67`) is where the authorization lives, and it is correct — it resolves the
socket's credentials and computes
`perms.read = ctx.authorization.checkMultiple('api:*:read', auth.shiros)`. It then puts that
boolean in the response to the client and never consults it again. **What `subscribe` actually
gates is acknowledgement rights and nothing on the receive side.** That is the whole shape of the
defect: the decision exists, it is right, and the delivery path never asks for it.

**Measured, both refs, both arms**, all five classes driven through the real plugin paths —
threshold crossings via `POST /api/v1/entries` for `alarm`/`urgent_alarm`/`clear_alarm`, treatment
writes via `POST /api/v1/treatments` for `notification`/`announcement`. The socket in this table is
unauthenticated and **never sends `subscribe`**:

| ref | `AUTH_DEFAULT_ROLES` | anon v1 reads | all five classes received? |
|---|---|---|---|
| `v15.0.8` (= `origin/master`) | `readable` (shipped default) | 200 | **yes** |
| `v15.0.8` | `denied` | **401** | **yes** |
| `dev` `59430336` | `readable` | 200 | **yes** |
| `dev` `59430336` | `denied` | **401** | **yes** |

The 401 column is the control: in the hardened arm the REST surface genuinely refuses the same
anonymous caller, in the same process, at the same moment. In that arm the server even tells the
client `{"success":true,…,"read":false,"ack":false}` when it does subscribe — and then sends it
everything anyway.

**No shipped setting stops it**, measured rather than inferred: `AUTH_DEFAULT_ROLES=denied` no;
`AUTHENTICATION_PROMPT_ON_LOAD=true` no — it makes `subscribe` answer *"Missing or bad
accessToken"*, does not disconnect the socket, and does not change what `emit` reaches, exactly as
the advisory claims; `ENABLE=` (careportal off) removes only `notification` and `announcement`, by
removing the feature, and the three alarm classes still arrive. `lib/api3/index.js:113` constructs
the socket and `lib/server/app.js:294` mounts api3 unconditionally, so no flag removes the
namespace.

**What this is *not*, on the shipped default.** Every field of every payload was compared against
what the same anonymous caller gets from `treatments.json`, `entries.json` and `status.json` on a
`readable` install: dose, entering device, notes, event type, last SGV and all four thresholds are
already there, and `notifyhash`/`key` are sha1 over fields that are already there. **Nothing in the
socket payload is absent from the anonymous REST surface of a default install.** What the leak adds
on `readable` is timeliness — push instead of polling — plus one thing with no REST equivalent: a
server-labelled "this person is hypo *right now*" that a poller would have to re-derive. Hence 5.3
for the default and 7.5 for the hardened case, and the register grades the entry on the hardened
case because that is where a boundary is crossed.

**The main namespace was checked and is clean.** It has no notification path of its own;
`dataUpdate` is room-scoped behind the same `api:*:read`, and the only namespace-wide emit is an
integer viewer count. Measured on `v15.0.8` with `denied`: a socket that never sent `authorize`
saw `clients 1` and nothing else in 45 seconds while alarms and treatments were being generated.

**Affected range.** `git tag --contains 89d7eb679` gives `15.0.0` as the earliest, so the
advisory's `>=15.0.0` is correct and the first affected release is **15.0.0**.

**The fix.** Scope delivery to a room — the `DataReceivers` pattern from
`lib/server/websocket.js:791`, same permission string, not a second mechanism — and decide
membership on one question only: do this socket's resolved shiros include `api:*:read`? A helper
`applyReadEntitlement` joins or leaves `AlarmReceivers` accordingly, and the five emits target
that room.

**Decided 2026-09-21 (Ben West): shape B.** The socket is admitted at *connection* time if the deployment's anonymous default role already
permits reading — the same entitlement `AUTH_DEFAULT_ROLES` grants the REST surface to the same
anonymous caller — and re-evaluated on every `subscribe`. On `denied` the anonymous default
permits nothing, so the bypass closes exactly as under the stricter shape. On the shipped
`readable` default it permits everyone, so **a client that connects and never subscribes receives
what it has received since 15.0.0 and no client behaviour changes on the majority configuration**.

The rejected shape A required a successful `subscribe` on every configuration. It was rejected
because the marginal content disclosure on `readable` is measured at **zero**, so A removes no
disclosure there — only delivery — and because the `/alarm` protocol is in no swagger file and
nothing under `docs/`, so its third-party consumers cannot be enumerated and the failure mode if
one exists is a hypo alarm that silently stops arriving. Ben separately judged the web client to
be in practice the only consumer, which is the fact that would have argued for A, and chose B
anyway as insurance against that judgement being wrong.

Two properties of `ctx.authorization.resolve` were checked before calling it on every connection.
With neither secret nor token it takes the `!authAttempted` branch and **records no failed
request**, so an instance cannot throttle itself by accepting connections. It is `async` and
consults the failed-login delay list first, but with no delay pending no `await` executes and the
callback runs synchronously inside the connection handler — connecting is no slower. On an
address that *is* delayed the socket is simply admitted late, up to `AUTH_FAIL_DELAY`; that is
inherited by any room-scoped fix, is widened by B from subscribers to all clients, and is
recorded as a known cost rather than fixed here.

The part worth a reviewer's attention is not the server change, **and shape B does not remove
it**. `client.subscribeForAlarms` is called from exactly one place — the alarm socket's `connect`
handler — so **nothing re-subscribes after a viewer authenticates in the page**. A `denied`
instance still refuses the socket at connect, so *load → refused → prompt → enter secret* would
leave it in no room, receiving nothing, until it happened to reconnect. The fix therefore also
re-runs it from `hashauth.updateSocketAuth`. The source was already asking itself this at
`alarmSocket.js:150`: *"TODO: how will perms get updated after authorizing?"*

*Reproduced* 2026-09-21 on `v15.0.8` and `dev` `59430336` against `mongod 7.0.43`, in both
`AUTH_DEFAULT_ROLES=readable` and `AUTH_DEFAULT_ROLES=denied`, with the REST control in the same
run. Branch rebuilt on shape B at `012f1623` with **49 delivery cases and 2 ack cases**; the
delivery matrix now also pins a credential that resolves but may not read — a write-only token
and a no-permission token are refused the stream on `denied`, with the same tokens' 401 from
`/api/v1/entries.json` in the same run. **Five ablations**, each reproducing the specific wrong
outcome rather than a generic error, including one that reverts the connect-time admission and
turns exactly the five shape-B delivery cases red. Live positive control in both arms with
liveness asserted for every negative cell via the main namespace's `clients` event. Suite
2311 → **2362** passing, 3 pending, 0 failing. **Merged 2026-09-21** via PR #8745 (merge
`2b22c0ce`); origin's branch tip `a198e308` carries an integration merge of `dev` added on the way
in and was not re-measured.

Evidence: [GHSA-8849 alarm socket](../../60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md).

### BF-76 · a read-only token can silence every alarm on the instance, indefinitely

Found while fixing BF-75, in the same function, and **not part of GHSA-8849 as filed**.

`self.subscribe` has two branches. The web-client branch (`:137-149`) guards the `ack` handler with
`perms.ack = checkMultiple('notifications:*:ack', …)`. The native-client branch above it (`:83`)
registers the same handler with **no check at all**, and `resolveAccessToken` fails only when the
subject is unknown. So any token that names a real subject — including
`api:*:read`, including a role with no permissions — reaches
`ctx.notifications.ack(level, group, silenceTime, true)`.

That call is global: `lib/notifications.js:160-173` sets `alarm.lastAckTime` and
`alarm.silenceTime = time ? time : THIRTY_MINUTES` on the server's single alarm object, so every
viewer stops being alarmed, and acking URGENT recurses into WARN. `silenceTime` is taken straight
from the socket message with **no upper bound**.

*Reproduced* as a unit on `dev` `59430336`: a subscriber holding only `api:*:read` reached the
global ack; with the new guard removed, the ablation reproduces exactly that (`expected 1 to be
0`), and with it in place the read-only token is ignored while an admin token still works.

The authorization gap is fixed on `bf/alarm-socket-scope` as a separate commit, merged 2026-09-21
via PR #8745 (merge `2b22c0ce`). **The unbounded
`silenceTime` is deliberately left open** — what a legitimately authorized client should be allowed
to ask for is a product decision about a safety function, and it should not ride along on an
authorization fix.

Evidence: [GHSA-8849 alarm socket](../../60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md) §5a, §10, §11.

### BF-77 · the "readable by world" warning is switched off by the setting that widens access

Nightscout does not leave the shipped `readable` default unannounced. `lib/server/bootevent.js`
raises a **persistent** admin notice at boot:

```js
if (env.settings.authDefaultRoles == 'readable') {
  ctx.adminnotifies.addNotify({
    title: "Nightscout readable by world"
  , message: "Your Nightscout installation is readable by anyone who knows the web page URL. …"
  , persistent: true
  });
}
```

That is a good design: the default is permissive, and the product says so, every boot, to the
operator, with a link to the documentation for closing it.

**The deprecated `TREATMENTS_AUTH=off` defeats it.** `lib/server/env.js` implements that setting
by appending to the same string the warning tests:

```js
if (!readENVTruthy('TREATMENTS_AUTH', true)) {
  env.settings.authDefaultRoles = env.settings.authDefaultRoles || "";
  env.settings.authDefaultRoles += ' careportal';
}
```

`"readable careportal"` is not `"readable"`, so the compare fails and the notice is never raised.
Measured through `GET /api/v2/adminnotifies` with an admin credential, all three arms in one run,
on **v15.0.8** and again on `dev` `59430336`:

| configuration | resolved `authDefaultRoles` | anon read | anon `POST /api/v1/treatments` | notice |
|---|---|---|---|---|
| default | `readable` | 200 | 401 | **`notifyCount` 1, "Nightscout readable by world"** |
| `TREATMENTS_AUTH=off` | `readable careportal` | 200 | **200, record stored** | **`notifyCount` 0** |
| `AUTH_DEFAULT_ROLES=denied` | `denied` | 401 | 401 | `notifyCount` 0 |

Row 1 is the positive control — the notice does fire when it should. Row 3 is the negative
control — it correctly does not fire on a closed instance, so absence in row 2 is attributable to
the string compare and not to the notice being broken generally.

**Why this is worth a row of its own.** It grants no access. Everything row 2 allows is what the
operator asked for by setting `TREATMENTS_AUTH=off`. What is lost is the only signal they get,
in the configuration that is simultaneously world-readable and world-writable — and the signal is
lost *because* of the second half, which is the part that would have made a reader want the
warning more, not less.

**Merged 2026-09-21** via PR #8746 (merge `74fc6619`; `bf/readable-warning` `74731433`, off `dev`
`59430336`).

The decision moved out of `checkSettings` into a pure `worldReadableNotify(settings)` at module
scope in `lib/server/bootevent.js`, which returns the notice or `null` and is exported so a test
can reach it. It asks role membership through a new `lib/authorization/defaultroles.js`:

```js
function parse (value) { return (value || '').split(/[, :]/); }
function has (value, role) { return parse(value).indexOf(role) > -1; }
```

`lib/authorization/index.js:23` now reads through the same `parse`, so there is **one** reading
of the setting rather than two that can drift. That line is deliberately *not* a behaviour
change: the split is character-identical, empty element included, so `rolesToShiros` and
`permissionGroups` see exactly what they saw before. The empty element a leading separator
produces (`AUTH_DEFAULT_ROLES` unset plus `TREATMENTS_AUTH=off` → `' careportal'` → `['',
'careportal']`) never equals a role name, so `indexOf` needs no special case.

**The second notice** (wording approved by the maintainer 2026-09-21). Plain `readable` keeps its
existing title and message byte for byte. `readable careportal` gets:

> **Nightscout readable by world and open to treatment entry**
>
> Your Nightscout installation is readable by anyone who knows the web page URL, and it also
> accepts new treatment entries - carbs, insulin, notes and similar - from anyone who knows the
> URL, without a password. This happens when the careportal role is part of AUTH_DEFAULT_ROLES,
> either because you set it there or because the deprecated TREATMENTS_AUTH=off setting adds it.
> If this is not what you intended, please consider closing access by following the Nightscout
> documentation: https://nightscout.github.io/nightscout/security/#how-to-turn-off-unauthorized-access

One notice rather than two, because `lib/adminnotifies.js` aggregates by *message* and two
persistent entries would describe one configuration decision with one remediation link. The
claim is scoped to what `careportal` actually grants — `api:treatments:create`, so "treatment
entries", not "writable". The tone assumes the operator chose the setting on purpose: it names
both ways the role can arrive and says *if this is not what you intended*.

**`careportal` without `readable` is deliberately not warned about.** Today that combination
returns 401 to the anonymous write (BF-78), so a warning would be false. If BF-78 is resolved in
a way that changes it, `worldReadableNotify` is the single place that follows.

**Non-vacuity.** `tests/bootevent-readable-warning.test.js`, 20 cases in three groups: the
decision over every role list; the same decision against the string `lib/server/env.js` really
resolves, driving `config()` with the environment variables set, so the test fails if *either*
half of the pair moves; and the notice through the real `lib/adminnotifies`, counted once and
surviving the twelve-hour clean because it is persistent. Ablating by restoring `== 'readable'`
**inside the same seam** — so the failure cannot be a missing export — reproduces the original
symptom rather than noise:

```
1) warns on readable careportal, which is strictly wider:   expected null to exist
5) warns when TREATMENTS_AUTH=off widens the default:       expected null to exist
6) reaches the admin notify list for readable careportal:   expected 0 to be 1
```

7 failing, **13 still green** — every `denied` / stay-quiet case survives the ablation, which is
what makes the red attributable to this condition. Full suite 2311 → **2331** passing, 3 pending,
0 failing, +20 exactly.

**Re-measured live after the fix**, same four arms, `GET /api/v2/adminnotifies` with an admin
credential:

| configuration | resolved roles | anon read | anon `POST /treatments` | notice |
|---|---|---|---|---|
| default | `readable` | 200 | 401 | 1, **text unchanged** |
| `TREATMENTS_AUTH=off` | `readable careportal` | 200 | 200 | **1, wider text** |
| `AUTH_DEFAULT_ROLES=denied` | `denied` | 401 | 401 | **0, still silent** |
| `denied` + `TREATMENTS_AUTH=off` | `denied careportal` | 401 | 401 | **0, still silent** |

The last two rows carry as much weight as the second: a fix that made a hardened instance warn
about being world-readable would be worse than the defect, because it teaches operators to
ignore the notice. The anonymous `POST` still returns 200 on row 2 — this changes what is
*said*, not what is *allowed*.

*Found while building the configuration control for the five 2026-09 security advisories; see
[the configuration matrix](../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md).*

**A latent quirk found while testing this, not filed as its own row because it reaches no
operator.** `lib/server/env.js` `config()` is **not idempotent for this setting**: calling it
twice with `TREATMENTS_AUTH=off` yields `'readable careportal careportal'`, because
`eachSettingAsEnv` does not reset `authDefaultRoles` when `AUTH_DEFAULT_ROLES` is absent, so the
previous value persists and the append runs again. Production boots `config()` once, so nothing
ships broken. It is recorded here because it dictated how the new test resets state, and because
the fix on `bf/readable-warning` deliberately tolerates the repeated append — there is a test
case pinning that. Anyone refactoring `config()` toward reusability should know it first.

### BF-81 · two authorization-shaped settings, one boundary, and nothing that says which

Filed at the maintainer's request on 2026-09-21, after the week's work kept arriving back at the
same root.

**The two settings.**

| setting | default | what it actually does |
|---|---|---|
| `AUTH_DEFAULT_ROLES` | `readable` | **the access-control boundary.** Decides what an unauthenticated caller may do, on every API surface |
| `AUTHENTICATION_PROMPT_ON_LOAD` | false | decides whether the **web client is asked to log in**. Grants and denies nothing |

They sit thirty lines apart in the README, both sound like authentication, and nothing in the
documentation says that one is a boundary and the other is a prompt.

**Three consequences, each measured elsewhere in this register rather than asserted here.**

1. **An external reviewer's security patch keyed on the wrong one.** The reporter of GHSA-8849
   found a real unauthenticated-disclosure defect that nobody inside the project had, reported it
   responsibly, and wrote a fix. That fix gates on `AUTHENTICATION_PROMPT_ON_LOAD`, so on a
   hardened instance with that flag at its default it closes nothing — measured on their branch,
   a never-subscribing socket still received alarms while REST answered 401 in the same run. A
   reviewer who understood the subsystem well enough to find the defect still picked the wrong
   setting, which is the evidence that the naming is the problem.
2. **The `/alarm` protocol is not specified anywhere.** Not in `swagger.yaml`, not in
   `swagger.json`, nothing under `docs/`. Anyone who built a client against it read the wire. That
   is what made the BF-75 fix a judgement call rather than a lookup — the maintainer had to choose
   a shape without being able to enumerate who would break — and it is why the conservative shape
   was taken.
3. **`README.md:243` is false for the role an operator would most likely try.** It says
   `AUTH_DEFAULT_ROLES` accepts "`readable`, `denied`, or any valid role name". `careportal` is a
   valid role name and setting it alone does nothing at all (BF-78), silently.

**And a fourth, smaller one:** `TREATMENTS_AUTH=off` is documented (`README.md:247`) as adding the
`careportal` role, which is true, but not that it does so by *appending to `AUTH_DEFAULT_ROLES`* —
which is the mechanism behind BF-77 and is invisible to a reader of either entry alone.

**What would fix it** is documentation:

- state, next to both settings, that `AUTH_DEFAULT_ROLES` is the boundary and
  `AUTHENTICATION_PROMPT_ON_LOAD` is a client prompt that grants nothing;
- enumerate the shipped roles and their actual permissions — `denied` (none), `readable`
  (`*:*:read`), `careportal` (`api:treatments:create`), and the rest — rather than "any valid role
  name", and say which combinations are functional (see BF-78);
- say that `TREATMENTS_AUTH=off` appends to the role list rather than setting a separate flag;
- specify `/alarm` in the swagger documents, or state that it is internal and unsupported. Either
  is better than the current position, where third-party behaviour is defined by what the server
  happened to do.

**No branch.** This is prose in `README.md` and the swagger documents, and the wording is a
maintainer's to write.

*Related*: BF-75, BF-77, BF-78, and
[the reporter PR evaluation](../../60-research/remedial/ghsa-8849-reporter-pr-evaluation-2026-09-21.md),
whose closing section is the long-form version of this entry.

### BF-78 · `careportal` as a default role does nothing, and says nothing

`README.md:243` documents `AUTH_DEFAULT_ROLES` as taking "`readable`, `denied`, or any valid role
name". `careportal` is a valid role name — one of the five in `lib/authorization/storage.js` —
and it grants exactly one permission:

```js
, { name: 'careportal', permissions: [ 'api:treatments:create' ] }
```

But `lib/api/treatments/index.js` gates the **whole router** on reading, before any route is
reached:

```js
api.use(ctx.authorization.isPermitted('api:treatments:read'));   // :26
…
api.post('/treatments/', ctx.authorization.isPermitted('api:treatments:create'), post_response);  // :146
```

so a caller holding only `api:treatments:create` is refused at `:26` and never reaches `:146`.
Measured, anonymous `POST /api/v1/treatments`, on **v15.0.8** and `dev` `59430336`:

| `AUTH_DEFAULT_ROLES` | anonymous write |
|---|---|
| `readable careportal` — what `TREATMENTS_AUTH=off` produces | **200, stored** |
| `careportal` | **401** |
| `denied careportal` | **401** |
| `denied` | 401 |

**It fails closed, which is why this is `low` and not a security row.** Nothing is exposed. The
defect is that a documented setting is inert and silent: no boot error, no log line, no admin
notice. The operator intent it most naturally expresses — *close reads, but let a family member
enter carbs from the careportal without issuing a token* — is unreachable through the
configuration surface, and the operator has no way to discover that except by testing a write.

**It is the other half of BF-77.** The single combination in which `careportal` does anything is
`readable careportal`, and that is precisely the combination whose "readable by world" notice
BF-77 suppresses. An operator who wants anonymous careportal entry is therefore steered, by the
only route that works, into the configuration that stops warning them.

Three ways out, and the choice is a contract decision rather than a bug fix: give the role the
read permission its routes require; move the router-wide read gate below the create route; or
document that `careportal` only functions alongside `readable` and say so at boot when it does
not. Failing silently is the one option to rule out.

*Found while building the configuration control for the five 2026-09 security advisories; see
[the configuration matrix](../../60-research/remedial/advisory-auth-configuration-matrix-2026-09-21.md).*


### BF-79 · `loadRetro` serves the retained devicestatus window to any socket

> **DISCLOSURE FIRST. Read this paragraph before quoting the rest anywhere public.** This is a
> **live unauthenticated disclosure of medical-device telemetry on the shipping release 15.0.8**,
> with no released patched version (the fix is in `dev`, PR #8744), and **this repository is
> public**. The mechanism is below because
> an operator cannot act on a defect they cannot recognise and the fix is a handful of lines they
> can read. The **probes, the seeding script and the harness are held outside version control** and
> are not reproduced here or in the evidence document. All lab data was synthetic and canaried.

**The mechanism.** `lib/server/websocket.js:315`, identical on `v15.0.7`, `v15.0.8` and `dev`,
registers `loadRetro` at connection time and answers it immediately with
`socket.compress(true).emit('retroUpdate', { devicestatus: lastData.devicestatus })`. It reads no
authorization state of any kind. Every other handler in that closure — `dbAdd`, `dbUpdate`,
`dbUpdateUnset`, `dbRemove` — goes through `checkConditions`, which refuses on `!socketAuthorization`
at `:269`. `loadRetro` is the one *read* handler in the file and the one that skips it.

The decision it needed already exists. `socket.on('authorize')` (`:775`) calls `verifyAuthorization`
(`:119`), which resolves the socket's credentials through `ctx.authorization.resolve` and computes
`read = checkMultiple('api:*:read', shiros)`, then joins readers to `DataReceivers`. **Same shape as
BF-75**: the decision is computed correctly and the delivery path never asks for it.

**The attacker does not fight the authorization; they skip it.** Measured: `authorize` with a wrong
secret ends in `socket.disconnect()` and no data. So `authorize` is not a gate to pass — it is one
to walk around, and anyone auditing this namespace by attacking `authorize` will find it sound.
The cleanest single demonstration that this is CWE-862 is the third row below: a socket that sends
`authorize` **with no credentials** on a `denied` instance is told `{"read":false,…}` **by the
server** and is then handed the whole payload.

**Measured, three refs, both arms.** Seed: 1 730 synthetic `devicestatus` records over 72 h from two
devices (one legacy `openaps`-shaped, one modern `loop`-shaped), all canaried. The socket is
unauthenticated and **never sends `authorize`**:

| ref | `AUTH_DEFAULT_ROLES` | anon v1 reads | `retroUpdate`? | records |
|---|---|---|---|---|
| `v15.0.7` | `readable` (shipped default) | 200 | **yes** | 576 |
| `v15.0.7` | `denied` | **401** | **yes** | 576 |
| `v15.0.8` (= `origin/master`) | `readable` | 200 | **yes** | 576 |
| `v15.0.8` | `denied` | **401** | **yes** | 576 |
| `dev` `59430336` | `readable` | 200 | **yes** | 576 |
| `dev` `59430336` | `denied` | **401** | **yes** | 576 |
| `dev` + fix | `readable` | 200 | **yes** | 576 |
| `dev` + fix | `denied` | **401** | **no** | 0 |

The isolating control — the same unauthenticated socket that never emits `loadRetro` — saw only the
event `clients` in all eight rows. The disclosure is the handler's, not the connection's.

**Liveness control, because the fix's evidence is a negative.** A dead server also emits no
`retroUpdate`, and lab instances were observed being reaped by the harness. Every negative arm was
therefore re-run with the server relaunched under `setsid nohup` and four liveness assertions in
the same run: an HTTP response before and after (401 on a `denied` arm, never `000`), `connect`
succeeding, the `clients` event arriving on both the probe socket and a no-`loadRetro` control
socket, and — decisively — **the same process on the same port serving 570 canaried records to an
authorized reader seconds later**. It was alive, it held the data, and it refused the anonymous
socket. The positive rows need no such treatment, and the ablation runs in-process under mocha
with no external server to die.

**No shipped setting stops it**, measured rather than inferred, and the source agrees: every `env.*`
reference in `lib/server/websocket.js` is a collection name, `env.version`, `env.enclave` or
`env.settings.enable` for the `status` payload. Nothing reaches a handler registration.
`AUTH_DEFAULT_ROLES=denied` no; `status-only` no; `AUTHENTICATION_PROMPT_ON_LOAD=true` no — that
setting is read in `lib/api3/alarmSocket.js:113` and `lib/client/index.js:1166` and **nowhere in
this file**; `TREATMENTS_AUTH=off` no. The only knob that touches the path is `DEVICESTATUS_DAYS=2`,
which takes the leak from **576 records / 23.9 h** to **1 150 / 47.8 h**.

**The real bound, since the advisory only says `loadedMills` "does not constrain".** It does not —
every probe sent a non-zero `loadedMills` and got the whole window — but there **is** a bound and it
is worth a number. `lastData` is `ctx.ddata.clone()`; `ddata.devicestatus` comes from `ctx.cache`,
whose devicestatus **retention period is `ONE_DAY`** (`lib/server/cache.js:26-28`), `TWO_DAYS` under
`DEVICESTATUS_DAYS=2`. So: **the rolling 24-hour window, unbounded in record count** — not the full
history. Against a 72 h / 1 730 record seed it returned 576 records spanning 23.92 h.

That bound is the severity fact, because the **authenticated** initial load is *smaller*.
`authorize` → `dataWithRecentStatuses()` → `recentDeviceStatus()` (`lib/data/ddata.js:148`) trims to
the **10 most recent per device-and-type pair**. Same instance, same seed: an authorized reader's
`dataUpdate` carried **20** records; `loadRetro` to a socket that never authorized carried **576**.
**The unauthenticated path returns 28.8× more devicestatus than the authenticated one.**

**What this is *not*, on the shipped default.** Compared field by field against what the same
anonymous caller gets from `devicestatus.json?count=2000` on a `readable` instance: REST returned
**1 730** records to the socket's **574**; **0** socket record ids were absent from the REST answer;
**0** JSON field paths appeared only on the socket (one, `uploaderBattery`, appears only in REST,
because the runtime rewrites it away). The socket payload is a **strict subset** of the instance's
own documented public output. **On a default install the marginal disclosure is zero** — hence 0.0
there and 7.5 for the hardened case, and the register grades the entry on the hardened case, which
is the only place a boundary is drawn to cross.

**Beyond telemetry.** The payload carries identifiers as well as clinical data: `pump.pumpID`
(serial), `pump.manufacturer`, `pump.model`, `uploader.name` (the phone's name, frequently a
person's given name) and the `device` string (often a rig name or hostname). No credentials — the
collection has no such field — and no write primitive.

**No throttle.** One socket, 20 emits, 20 full responses, 12.4 MB in 12 s. A ~46-byte frame elicits
~618 KB, roughly 13 400×. Marginal only in the hardened arm; on `readable` the REST route already
offers the same caller a larger one.

**Affected range.** Grepping `lib/` at each tag: `loadRetro` is **absent from `0.8.1`, `0.8.2`,
`0.8.3` and `0.8.4`** and present from **`0.9.0`**, introduced by `18aa4295` (2016-10-09) and
`2cb597d3` (2016-10-10) and moved into `lib/server/` by `05157605` (2017-12-28). `0.9.0` is also the
first release carrying `DataReceivers` and `authDefaultRoles` (`a20f8e28`, `0f735d0a`), so the
handler and the authorization it fails to consult **shipped together**. The advisory's `>0.8.1`
declares three releases vulnerable to code they do not contain. **First affected: `0.9.0`.**

**The fix, and why it is not a second policy.** The requirement is asymmetric — `denied` must
refuse, `readable` must keep working, because most self-hosters run the documented public-read
default and closing this unconditionally would be a regression for them, not a fix.
`verifyAuthorization` called with an **empty message** already answers exactly "may an
unauthenticated socket read?": `ctx.authorization.resolve`'s `if (!authAttempted) → defaultShiros`
branch (`lib/authorization/index.js:161-170`) yields the `AUTH_DEFAULT_ROLES` shiros the REST
surface answers with. So the handler honours `socketAuthorization.read` when the socket authorized,
and otherwise resolves the same defaults `authorize` would have resolved for it, replying
`{result: 'Not permitted'}` — the string `checkConditions` already uses — when the answer is no.
**Nothing was reached for**; the machinery is in the same file, in the function `authorize` already calls.

`loadedMills` is deliberately **still ignored**. Honouring it is a behaviour change with client-side
consequences and does not belong in a security commit.

*Reproduced* 2026-09-21 on `v15.0.7`, `v15.0.8` and `dev` `59430336` against `mongod 7.0.43`, in
both `AUTH_DEFAULT_ROLES=readable` and `AUTH_DEFAULT_ROLES=denied`, with the REST control and the
no-`loadRetro` socket control in the same run. Fix and 4 regression cases on
`bf/ws-loadretro-auth` (`9765e8cd`), **merged 2026-09-21** via PR #8744 (merge `a9acd313`) at that
exact tip. The ablation turns the two negative cases red
printing `{retroUpdate: true, canary: true, records: 1}` — the symptom itself, canaried devicestatus
arriving at a socket the server had resolved as unable to read — while the two positive cases stay
green. Suite 2 311 → 2 315 passing, 3 pending, 0 failing.

Evidence: [GHSA-gjhc `loadRetro` report](../../60-research/remedial/ghsa-gjhc-loadretro-2026-09-21.md).

### BF-80 · the fix for BF-75 inherits the failed-login delay, and a household is one IP

This is not a defect in `bf/alarm-socket-scope`. It is a property of scoping alarm delivery to
an entitlement at all, and it is filed so that the cost of the BF-75 fix is recorded next to the
fix rather than discovered by an operator.

`authorization.resolve()` begins:

```js
const requestDelay = shouldDelayRequest(data.ip);
if (requestDelay) { await sleep(requestDelay); }
```

and `lib/authorization/delaylist.js` accumulates:

```js
if (now >= entry) { entry = now; }
ipDelayList[ipString] = entry + DELAY_ON_FAIL;     // DELAY_ON_FAIL = authFailDelay ?? 5000
```

so *n* failures close together push the deadline out by roughly 5 *n* seconds, and
`requestSucceeded` clears it. Before BF-75's fix, `/alarm` delivery consulted nothing, so no
delay could touch it. After the fix, delivery depends on a resolved entitlement, and the
resolution waits.

**Measured on the fixed build (`bf/alarm-socket-scope`, `AUTH_DEFAULT_ROLES=readable`, mongod
7.0), with the alarm always fired two seconds after the socket connected:**

| failed authentications from that IP first | first alarm event reached the socket at |
|---:|---|
| **0** (clean control) | **2.0 s** — i.e. immediately, as emitted |
| 1 | 4.9 s |
| 3 | 10.0 s |
| 6 | 15.0 s |

The clean control is what makes this a mechanism rather than a coincidence: the window is
absent at zero and grows with the count. It is deliberately reported as a *shape* — absent,
then growing — rather than as a threshold, because a fixed number measured on a loopback lab
would not survive the request path.

**Why it matters more than the seconds suggest.** The delay list is keyed on the remote address.
A household behind one NAT address is one key. The realistic trigger is not an attacker but an
uploader or follower app configured with a stale API secret, retrying quietly: it poisons the
address, and the *browser* someone is watching for a hypo alarm is admitted late on every
reconnect. Nothing tells either party this is happening.

**Three ways out, and choosing is the point of this entry:**

1. **Do not apply the delay to a permission resolution that attempted no credential.** The
   anonymous path already takes the `!authAttempted` branch and records no failure; arguably it
   should not *serve* one either. Narrowest change, and it fixes the NAT case entirely, because
   the viewer being punished is the one who supplied nothing.
2. **Keep the delay but admit optimistically and re-evaluate**, so a socket is never silently
   outside the room while a decision is pending.
3. **Accept it and document it**, on the grounds that tens of seconds is small against a CGM's
   five-minute cadence. Defensible for `notification`, weaker for `urgent_alarm`.

Option 1 looks right and is deliberately not taken here, because it changes a brute-force
control and that belongs in its own change with its own review. PR #8754 (open) keeps the wait
before the credential check and keys it on the address as well as the credential, so an anonymous
alarm socket behind a poisoned address is still admitted late (read from head `e32f7a1c`, not
run).

*Found while reviewing the BF-75 fix; see
[the alarm socket report](../../60-research/remedial/ghsa-8849-alarm-socket-2026-09-21.md) and
[the sequencing record](./security-advisory-sequencing-2026-09-21.md).*


### BF-85 · a CareLink no-reading marker holds off the high/low alarms

The CareLink source maps every element of the vendor's `sgs` array to a glucose entry, including
elements whose `sg` is `0`, which CareLink uses where there is no reading. The entry is stored with
`sgv: 0`. `lib/plugins/simplealarms.js` evaluates the high and low thresholds only when the newest
entry's `mgdl` is above 39, so while the zero is newest, no high/low alarm is evaluated.

**Read-derived.** Both halves were read on the refs named in the table; the end-to-end behaviour
has not been run, and how often CareLink emits a zero in the newest position is unknown. The
stale-data alarm's behaviour while the zero is newest is also unmeasured.

**Where the fix is.** Connector commit `8406edf` filters `sg === 0` and non-`SG` kinds before
mapping (connector PR #64, 2026-09-22). It is released in nightscout-connect `0.1.0` (npm,
2026-09-24), which Nightscout `dev` pins exactly (PR #8762, merge `153e5658`); it has been in
Nightscout `dev` through the connector prerelease pins since PR #8752 (2026-09-23). It reaches
Nightscout operators with 15.0.9. The fix is read-derived too: it has not been run against CareLink.
Nightscout is not a medical device; an operator relying on alarms should keep the device's own
alarms on.


### BF-86 · an mmol/L low threshold on a mg/dL site is kept as-is, so the low alarm never fires

`verifyThresholds` corrects a threshold only when it is out of order *upward* (BF-67). A `BG_LOW`
of `3.9` on a mg/dL deployment is in order — it is below every other threshold — so it is stored
as 3.9 mg/dL with no warning. A glucose reading below 3.9 mg/dL does not occur, so the low alarm
cannot fire. The high-side equivalent is caught and rewritten (BF-67); the low side is not caught
at all.

**Reproduced** in-process by `tools/queue/gates/threshold-silent-rewrite.js` against the shipping
`lib/settings.js`, identical on `v15.0.8` and `origin/dev` `74fc6619`.

**Fix — none prescribed.** Rejecting or flagging a threshold outside the physiological range for
the configured units is the obvious shape, but it is a maintainer decision with a safety dimension
and should be designed together with BF-67.


### BF-89 · the connector's Nightscout source asks for a subject with no roles

`lib/sources/nightscout.js` posts `{name: 'nightscout-connect-reader', role: ['readable'], notes: …}`
to the source site's `/api/v2/authorization/subjects`. The shipping server stores the body as sent
(`lib/authorization/endpoints.js`, `createSubject(req.body)`), and it grants permissions from
`roles`, so the subject has none. `bf/auth`'s allow-list (BF-47) would drop `role` outright;
the result is the same. The connector then reads the subject back by name and uses its token.
That token grants only what anonymous access already does, so on a default `readable` source site
the source works anyway, and on a `denied` one it cannot read. Present since the source was first
written (`3b290e5`, 2023-04-05).

The allow-list stays: the maintainer decided on 2026-09-23 that it is intended (BF-47), so the fix
is on the connector side, `role` → `roles`, with a test.

**Reproduced and merged, 2026-09-23.** Connector commit `dea2bec` records an end-to-end run against
cgm-remote-monitor `74fc6619` with `AUTH_DEFAULT_ROLES=denied` and the connector's `forever`
sidecar copying into a second Nightscout: before the change the token carries no permissions and
every poll ends in HTTP 401 with no entries; after it the subject is stored with `roles:
['readable']` and the seeded entry arrives. With `AUTH_DEFAULT_ROLES=readable` nothing changes. It
merged into connector `dev` as PR #77 (`b4d8d29`), is released in nightscout-connect `0.1.0`
(2026-09-24), and is in Nightscout `dev` through the connector pin (PR #8759, 2026-09-23; exactly
`0.1.0` since PR #8762). A site where an earlier connector already created the subject keeps a
subject with no roles after upgrading, until that subject is given the readable role in the admin
tools or deleted.

### BF-90 · an alarm at a page with no reading throws in the client

`alarmSocket.on('alarm')` and `on('urgent_alarm')` decide whether to sound by `isAlarmForHigh()`
and `isAlarmForLow()`, both of which guard on `client.latestSGV`. With no reading loaded both are
false, so the handler takes the "disabled locally" branch, and that branch logs
`client.latestSGV.mgdl` without a guard. It throws a `TypeError`, and `chart.update(false)` is
skipped.

**Reproduced** in a real browser on `v15.0.8` and `origin/dev`, identically, first by the RT-D3 probe
run ([browser evidence](../../60-research/modernization/rt-d3-and-alarm-browser-evidence-2026-09-22.md)),
which had the server's `/alarm` delivery gate forced open.

**Reachable without forcing** ([evidence](../../60-research/remedial/bf90-alarm-no-reading-2026-09-23.md), 2026-09-23): any opt-in device alert (for example `PUMP_ENABLE_ALERTS`) at a site with no stored CGM
reading reaches it, on 15.0.8 and on `dev`; on 15.0.8 a page that may not read data also receives
alarms (BF-75). So it is not latent; graded **low — reachable**: the throw's own cost is the skipped
`chart.update(false)` and any listener on the same event registered after the page's own. **The
throw loses no alarm only because the page has already dropped the alarm, since with no reading it
presents no server alarm at all (BF-92).** That, not the throw, is the safety-relevant behaviour, and fixing the throw
does not change it.

**Merged 2026-09-23** via PR #8755 (merge `728351e3`; branch `bf3/alarm-no-reading` `92544d8f`,
one commit on `74fc6619`).
Two guards are needed in each handler, not one: the log argument, and `chart.update`, because a page
that has never received data has no chart and throws a second time once the first is guarded. The
alarm decision is unchanged. Suite 2390/0/3 on Node 20 and 22, exactly +4.

### BF-91 · connector `capture` mode cannot load its trace module for two sources

`lib/sources/nightscout.js:190` and `lib/sources/dexcomshare.js:243` both
`require('../../trace-axios')`. From `lib/sources/` that resolves to a repository-root file that
does not exist; the module is `lib/trace-axios.js`. Sources one directory deeper (`glooko/`,
`minimedcarelink/`) resolve the same string correctly. So `capture --source nightscout` (or
`dexcomshare`) crashes with `MODULE_NOT_FOUND`, on connector `v0.0.13` and `dev` `1946beb`.

**Reproduced** 2026-09-23 by running `capture --source nightscout`, and confirmed from the trees:
no `trace-axios` at either root. **Severity: low** — only the standalone `capture` command, used to
record test fixtures, loads it; the plugin path Nightscout embeds and `forever` mode never do.

**Fixed** on `fix/trace-axios-path` `894b132`, with a test that fails on any unresolvable relative
require; merged as connector PR #78 and released in nightscout-connect `0.1.0`.

### BF-92 · a page with no glucose reading never presents a server alarm, including device alarms

`lib/client/index.js` on `74fc6619` (the same on 15.0.8): `isAlarmForHigh()` (`:1196-1198`) and
`isAlarmForLow()` (`:1202-1204`) both begin with `client.latestSGV &&`, and the `alarm` and
`urgent_alarm` handlers compute `enabled` from them (`:1225`, `:1237`). With no reading loaded both
are false, so every server alarm takes the "disabled locally" branch. That includes alarms unrelated
to glucose — pump reservoir, loop, cannula and sensor age — which a site owner has switched on.

**Reproduced 2026-09-23** in a browser on 15.0.8 and `dev`, and on the BF-90 branch, with synthetic
data and no forcing: two ordinary pump-status uploads with `PUMP_ENABLE_ALERTS=true` made the server
emit one `alarm` and one `urgent_alarm`. With 12 in-range readings on the page, the title read
`URGENT: Pump Reservoir Low`, the page showed the urgent alarm and one audio element played. With no
reading, nothing was presented. ([evidence](../../60-research/remedial/bf90-alarm-no-reading-2026-09-23.md) §1, §4.)

**Severity: high.** A person who relies on an open Nightscout page for device alarms gets none
from a page showing `---`. It did not ride along on BF-90's crash fix. *No fix is prescribed.*
Operator guidance meanwhile: keep the alarms on the devices themselves switched on.

**Maintainer position 2026-09-23.** Non-glucose alarms (pump, loop, age) should present on a page
with no reading. The change ships in a later release, not 15.0.9, paired with BF-52; 15.0.9 carries
this as a known issue.

### BF-93 · food changes never reach an open page

`lib/data/calcdelta.js` builds the delta that is broadcast to open pages. Its `compressArrays` covers
`sgvs`, `treatments`, `mbgs`, `cals` and `devicestatus`, and `deleteSkippables` sends `profiles` as a
whole object. `food` is in neither list. A food or quick pick written through the API, or in the
food editor in another tab, therefore reaches a page only on a full load: connect or reconnect.

**Reproduced 2026-09-23** in a browser on 15.0.8, `dev` and `bf3/quickpick-rebuild` alike: a quick
pick added while the page was open did not arrive by broadcast, and did after a transport drop and
automatic reconnect ([evidence](../../60-research/remedial/bf69-quickpick-rebuild-2026-09-23.md) §4, §8.1). An edited
carb total on an existing quick pick takes the same path; it was not run separately.

**Severity: medium.** The stale list feeds the Bolus Wizard's carb entry, and with BF-69 fixed the
chooser shows exactly what the page holds, stale or not. *No fix is prescribed.*

### BF-94 · a kept profile instance can return a temp basal that has been replaced

`lib/profilefunctions.js:19` declares `prevBasalTreatment` at **module scope**, and
`tempBasalTreatment()` returns it whenever the time falls inside it (`:455-456`). Only
`profile.clear()` resets it; that runs when each instance is created (`:34`), and `updateTreatments()`
(`:292-311`) clears the cache but not this variable.

**Reproduced at module level 2026-09-23** on `dev` and 15.0.8, while building the BF-09 harness: with
a 1.2 U/h temp later cut by a zero temp, the same instance returned 1.2 after `updateTreatments` had
replaced its treatments (expected 0); a new instance created afterwards returned 0
([evidence](../../60-research/remedial/bf09-dedup-zero-measurement-2026-09-23.md) §3.2).

**Severity: unsettled.** The server builds a new instance on every tick and is not affected. The
browser keeps one `client.profilefunctions` and calls `updateTreatments` on each data update
(`lib/client/index.js:1366`), so a basal pill or chart lookup there could show a replaced temp.
**The browser was not measured.** Because the variable is module-scoped, any two instances in one
process also share it. *No fix is prescribed.*

### BF-95 · an uploader clock running ahead delays the stale-data alarm

Found while measuring BF-41. `lib/sandbox.js` `lastEntry` skips readings later than `sbx.time`,
which is why BF-41 does not reproduce. Once the wall clock passes a future-dated reading's
timestamp, that reading is no longer skipped and is used as if it were current.

| case | readings | reading used | server | push | browser |
|---|---|---:|---|---|---|
| F7 | uploader 60 min ahead, stopped 15 min ago | 0 | current | none | current |
| F8 | uploader 60 min ahead, stopped 76 min ago | −16 | warn | WARN | warn |

Measured with `tools/remedial/bf3/bf41-real-sandbox.js` on `origin/dev` `74fc6619` and `15.0.8`
`92d08342`, identical output. A correct clock warns at 15 minutes; this one first warns at 76.

**Why there is no obvious fix.** v1 entries record no server-receipt time
(`lib/server/entries.js:118-126` derives `sysTime` from the reading itself; read, not executed),
so the server cannot tell "sent late" from "dated ahead". An arrival-based check needs new data.
A notice for readings that arrive already ahead of the clock by more than a tolerance is one
option (write-up §5, option 3); the BF-41 decision of 2026-09-23 added no new warning, so this
needs its own design decision.

**Not measured:** whether any uploader produces F7/F8 in practice (BF-44 names one mechanism,
measured there), and a booted server or real browser.

**Operator text** (15.0.9 release notes, Known issues, from the BF-41 write-up §7): if the device
uploading your readings has its clock set ahead, the stale-data warning comes late.
([evidence](../../60-research/remedial/bf41-future-reading-2026-09-23.md) §2, §3, §7.)

### BF-96 · the headless test fixture's bundle cache key is an un-normalised path

`tests/fixtures/headless.js` hands `tests/fixtures/benv-shim.js` a path of the form
`tests/fixtures/../../node_modules/...`. Node stores the loaded bundle in `require.cache` under the
resolved path, so the shim's `delete require.cache[filename]` deletes nothing. A second headless
suite in the same mocha process then receives the first suite's cached bundle, and `$` is
undefined in it. `careportal` was the only headless suite in the tree, so nothing had shown this.

**Reproduced 2026-09-23** while writing BF-90's `tests/client.alarm-no-reading.test.js` on
`origin/dev` `74fc6619`. That test clears the resolved key itself, with a comment
([evidence](../../60-research/remedial/bf90-alarm-no-reading-2026-09-23.md) §3). **Severity: low**,
test-only. The candidate fix is resolving the path in the shim (`path.resolve`); **UNVERIFIED**,
not run as a change of its own.

### BF-97 · on the connector 0.1.0 line, a source with a profile stalls every poll

The Nightscout source re-fetches every profile, with its source `_id`, on each poll. From the second
poll the sink's profile insert fails with a duplicate key. Through `v0.0.13`, `lib/outputs/internal.js`
caught the persist failure, logged `PERSISTED INTERNAL ERRORED`, returned `known` and resolved the
batch. `808ab1c` (2026-09-21) made `safePersist` log and rethrow `Nightscout internal write failed`,
so one duplicate profile now fails the whole poll and the backoff grows toward its 30-minute cap.

| arm | connector | poll median | newest reading behind, max / median |
|---|---|---:|---|
| K1 | `0.1.0-dev.2`, profiles synced | 25.3 min | 35 / 10 min |
| K3 | `0.1.0-dev.2`, profiles excluded | 5.0 min | 35 / 0 min (the outage only) |
| (g) | `v0.0.13` | — | never more than 5 min |

Measured 2026-09-23 over 4 h 23 min, synthetic data, with no records lost and no duplicates
([evidence](../../60-research/remedial/connector-0.1.0-dev.2-soak-2026-09-23.md)). Workaround on the
affected prereleases: `CONNECT_SOURCE_COLLECTIONS=entries,treatments,devicestatus`.

**Fixed in connector PR #79** (merge `977da8a`, 2026-09-23): `f6359b4` skips profiles the sink
already stores instead of failing the poll, `1d2ebc8` reads only the profiles a poll needs, and
`de3cee1` copies a changed source profile to the sink when the sink can replace it in place
(update-on-change works only against a sink that has PR #8758). Released in nightscout-connect
`0.1.0` (2026-09-24), pinned exactly by Nightscout `dev` (PR #8762). Lab-run: `9dbef9e`, whose
`lib/` is identical to `de3cee1`, ran 80 minutes on 2026-09-23 and 46 minutes against the 15.0.9
candidate sinks ([evidence](../../60-research/remedial/connector-profile-sync-bounded-update-2026-09-23.md)).

### BF-98 · the BF-89 fix does not repair an existing reader subject

The connector finds its `nightscout-connect-reader` subject on the source by name and reuses it
without checking its roles, on `v0.0.13` (what 15.0.8 installs, `lib/sources/nightscout.js:75-77`)
and on `0.1.0-dev.2` alike. Released connectors create it with `role` rather than `roles`, so a source with
`AUTH_DEFAULT_ROLES=denied` keeps answering 401 after the upgrade. Reproduced 2026-09-23 in the soak's
control (c). The maintainer chose a warning over a repair (2026-09-23): the connector says once, in
plain words, which subject is wrong and how to fix it (add `readable`, or delete it so it is
re-created), and never writes to the source site. The warning is connector `f924de2`, merged via
connector PR #79 and released in nightscout-connect `0.1.0`; the 0.1.0 and 15.0.9 release notes
carry the same steps.

### BF-99 · a profile posted with its own `_id` cannot be edited, deleted or found by it

`create()` stores a 24-hex `_id` as a string; `save()`, `remove()` and `find[_id]` convert to
ObjectId. So on 15.0.8 and `dev`, a PUT of that profile inserts a second document beside the stale
one, and DELETE removes only the new twin. Nightscout-to-Nightscout connector sinks hold these copies
for every profile they have synced. The fix, in review as PR #8758 (`bf/object-id-crud` head
`6d120fa2`, commit `09566345`), stores hex `_id`s as ObjectId,
as `treatments.js` already does, and makes PUT, DELETE and `find[_id]` match both forms, so existing
string copies are replaced on their next edit rather than duplicated. A POST that re-sends an id
already stored as a string keeps today's duplicate-key refusal instead of adding an ObjectId copy.
Non-hex `_id`s are already refused with 400 by the v1 routes and are unchanged.

### BF-100 · devicestatus, food and activity store a hex `_id` as a string

The same create-without-conversion pattern, reproduced on both trees: devicestatus and activity
`find[_id]` return nothing, food and activity PUT add an ObjectId duplicate, and DELETE by id keeps
the string document in all three. Fixed in PR #8758 (`bf/object-id-crud` `6d120fa2`, commit
`80993afc`) by the same rule as BF-99, through one shared helper, `lib/server/object-id-forms.js`. devicestatus gets no create guard, because it would add a read to
every connector batch.

### BF-101 · API v3 id filters miss string `_id`s

`filterForOne` and `identifyingFilter` match only ObjectId, so a v1-stored string `_id` is
unreachable by v3 id lookup and dedup. Reproduced through the v3 routes; fixed in PR #8758
(`bf/object-id-crud` `6d120fa2`, commits `597e2899` and `44ac9047`) by one `$eq` branch per form of
the id, which keeps the `_id` index in use.

### BF-102 · treatments and entries stored by 15.0.6 or earlier with a hex `_id` string

REQ-SYNC-072 (15.0.7) made new treatments and entries store a hex `_id` as ObjectId, but did not
make lookups match the ones already stored as strings. PR #8758 commit `5581c5e4` moves
both collections onto the shared helper and matches both forms; the UUID-to-`identifier` rule is
unchanged. The non-hex rule still differs by collection (UUID to `identifier` for treatments and
entries; kept or refused with 400 elsewhere) and is documented, not unified.

### BF-103 · a split treatment drag stores the old time

"Move carbs" and "Move insulin" build the new record from the page's in-memory treatment, which already
carries `mills` and `date` at the original time plus `mgdl` / `scaled`. The server stores them, and
`ddata` keeps a stored `mills` rather than deriving it from `created_at`, so IOB, COB and the chart all
use the pre-move time. Found by hand in the 15.0.9 manual-check lab; identical on 15.0.8. The plain
Move sends only `created_at`, so it neither causes nor repairs the damage. Fixed on the browser side in
PR #8760 (merged 2026-09-24, merge `ddd9b600`): a split no longer copies the page-added fields, and a move or a Reports-editor
save clears them on the stored record, which repairs records split earlier. A raw v1 PUT can still leave a
stale `mills`; the server-side options were measured and not built
([fix evidence](../../60-research/remedial/bf103-fix-2026-09-23.md)).

### BF-104 · a failed alarm subscription writes its credential to the server log

When a client subscribes to the API v3 `/alarm` socket and the credential it presents fails
authorization, `lib/api3/alarmSocket.js` logs that credential: the `accessToken`, the `jwtToken`, or
the whole subscribe message. The log is readable by whoever runs or supports the site, and by anyone
it is shared with. Reproduced on `dev` and `v15.0.8` by the backport triage
([triage](../../60-research/remedial/modernization-backport-triage-2026-09-22.md)); fixed on the
modernization branch by `31c354d8` and brought to `dev` unchanged by PR #8751 (merged 2026-09-23,
merge `4011193e`). Operators who have
shared server logs from a site whose alarm clients failed to authorize should treat those credentials
as exposed; the 15.0.9 release notes should say so.

### BF-105 · two shared v1 read routes check only the entries permission

`prep_storage` in `lib/api/entries/index.js` lets two routes under the entries router read from
`entries`, `treatments` or `devicestatus` according to a path parameter. The router is gated on the
entries read permission alone, so a credential scoped to entries reads the other two collections
through those routes. It matters only where anonymous read is denied and collection-scoped tokens are
issued. Reproduced on `dev` and `v15.0.8` by the backport triage
([triage](../../60-research/remedial/modernization-backport-triage-2026-09-22.md)); fixed on the
modernization branch by `d3ac8026` (a per-collection read check) and brought to `dev` unchanged by
PR #8751 (merged 2026-09-23, merge `4011193e`).

### BF-106 · the schema coercion drops activity's numeric `date` filter

This is a cost of BF-03's fix (PR #8737), filed next to it so that it is not discovered by an
operator. On 15.0.8 a storage module that set no `walker` inherited `query.js`'s default,
`{ date: parseInt, sgv: parseInt }`. On `dev` the default is conditional:

```js
opts.walker = opts.collection ? { } : { date: parseInt, sgv: parseInt };
```

and every v1 storage now names its `collection`, so the schema is the only source of types. The
`activity` schema has no numeric fields, so a `date` or `sgv` bound on `/api/v1/activity` reaches
MongoDB as a string and matches no stored number. `devicestatus` loses the default for `sgv`
only; its schema types `date` and `mills`. `profile` set `walker: {}` on 15.0.8 already, and
`entries` and `treatments` are typed by their schemas, so none of the three changes.

**Reproduced 2026-09-23** in the consumer-replay lab (three builds side by side, mongod 7.0.43,
Node 22.23.2, seven seeded activity records with numeric `date`): `find[date][$gte]=<ms>` returns
7 on `v15.0.8` and 0 on `dev` `ddd9b600` and on the 15.0.9 candidate; the `find[created_at][$gte]`
control returns 7 on all three. The gate builds the query with each ref's own `query.js` and
`activity.js` and checks the bound's type, with `v15.0.8` as its control.

**Fix shape, not measured:** declare `date` (and `sgv`, if activity uploads carry it) as numeric in
the activity schema, or keep the default walker's two fields when a collection's schema does not
type them. No client in the survey filters activity by `date`, which bounds the impact; the survey
reads client source and cannot see filters built at runtime.

### BF-107 · a failed treatments query ends the process

Reported upstream as issue #8675; merged to `dev` via PR #8697 (merge `0ab266a3`) on 2026-09-06.
`serveTreatments` in `lib/api/treatments/index.js` receives `(req, res, err, results)` and never
checks `err`; on a failed query `results` is `null`, `results.forEach` throws, and the uncaught
`TypeError` exits Node. On `dev` the handler answers HTTP 500 with the JSON status body.

**Reproduced 2026-09-23** in the consumer-replay lab: a treatments read whose query the database
rejects ended the `v15.0.8` process on each of three runs; `dev` `ddd9b600` and the 15.0.9
candidate answered the same request 200. The request is not given here because the defect is live
on the shipping release; it is kept with the lab's private notes.

### BF-108 · a list of timestamps under the date field answers 500

`enforceDateFilter` (`lib/server/query.js`) rewrites each value under the date field to an ISO
string when it `isNaN`:

```js
let dateString = dateValue[key];
if (isNaN(dateString)) {
  dateString = dateString.replace(/…/, '$1+$2');
```

A `$in` list of two or more timestamps is an array, which `isNaN`, and an array has no `.replace`,
so the query builder throws and the request answers 500. A one-element list is coerced to a number
by `isNaN` and passes. xdripswift's bulk delete of readings (`NightscoutSyncManager.swift:794-806`
at `c268542e`) sends `find[type]=sgv&find[date][$in][]=<ms>…` in chunks of 50, so it has never
deleted anything; its range delete (`find[date][$gte]` with `find[date][$lte]`) works.

**Reproduced 2026-09-23** in the consumer-replay lab on `v15.0.8`, `dev` `ddd9b600` and the
candidate: GET and DELETE with 2, 5, 20, 21 and 50 values all answer 500, and the entries count is
unchanged; the one-value and range controls answer 200. The gate reproduces the same exception
from each ref's own `query.js`, with a one-value control.

**Fix shape, not measured:** apply the ISO rewrite only to string values, and map it over array
values.


### BF-109 · on #8758, API v3 writes by identifier hit the v1 half of a v1/v3 pair

Before #8758, API v3 could not see a v1 record whose `_id` was stored as a string (BF-101), so a v3
PUT by that id created a second record: `{_id: X}` from v1, with no `identifier`, and
`{_id: ObjectId, identifier: X}` from v3. Sites that ran such a PUT hold those pairs.

#8758's `filterForOne` matches `identifier: X` **or** `_id` in each form of X. The read path
(`find.js`, `findOneFilter`) sorts `{identifier: -1}` and returns the v3 copy. The write path in
`modify.js` passes the same filter to `replaceOne`, `updateOne` and `deleteOne` with no sort, and
MongoDB takes the first match in natural order, the older v1 record. `identifyingFilter` (the
create/update lookup) matches both too: its `identifier: {$exists: false}` branch does not exclude
the v1 record, which has no identifier.

**Reproduced 2026-09-24**, probe P-ID-10 in `tools/lab/object-id`, with a 24-hex and a non-hex X,
on `v15.0.8`, `dev` `ddd9b600` and `6d120fa2`:

| request | 15.0.8, dev | #8758 |
|---|---|---|
| GET | the v3 copy | the v3 copy |
| DELETE, then GET | v3 copy invalid; GET 410 | **v1 record invalid**; GET 200, v3 copy |
| PUT | v3 copy replaced; one record with `identifier: X` | **v1 record replaced**; two records with `identifier: X` |

Reverting only `lib/api3/storage/mongoCollection/utils.js` to `1f9a9d10` on `6d120fa2` restores
the `dev` cells above and also restores the 404s #8758 fixes (P-ID-2), so the fix and this defect
come from the same lines.

**Fix shape, not measured:** resolve the target once with the sorted `findOneFilter` and write by
that document's exact `_id`; or, when both halves match, prefer the one with `identifier`.

### BF-110 · on #8758, deleting a record by its hex id also deletes its twin

A PUT on 15.0.8 or earlier to a treatment whose `_id` is stored as a string upserted an ObjectId
copy and left the string record (BF-102). #8758 makes every lookup by that hex match both forms,
so `find[_id]` returns both, and a delete by the hex removes both: v1
`DELETE /api/v1/treatments/<hex>` (the careportal, oref0's `ns-dedupe-treatments.sh`) and the
websocket `dbRemove` (the web UI's Remove). An edit merges the pair: #8758's upsert by the ObjectId
deletes the string form.

The PR's plain-language copy tells users with such a pair that they "can now delete" the old copy.
On #8758 that deletes the edited copy with it.

**Reproduced 2026-09-24**, probe P-ID-7: `find[_id]` returns 1 record on `v15.0.8` and `dev`
`ddd9b600`, 2 on `6d120fa2`; after the v1 DELETE or `dbRemove`, 1 record is left on 15.0.8 and
dev and 0 on `6d120fa2`. The v3 permanent DELETE leaves 1 on all three.

**Decided 2026-09-24 (maintainer): (b), the behaviour is kept.** The options were (a) when both
forms are stored, delete only the string form and keep the ObjectId copy, or (b) keep the behaviour
and change the advice. #8758's body already says a delete removes "a copy left by an earlier edit",
so only its advice line changes, to: "If you see an old copy beside the one you edited, edit either
one: the two become one record with that edit. Deleting either one deletes both." How many sites
have twins is unmeasured (queue OID-PREVALENCE).

### BF-111 · `find[_id][$in]` misses string-stored records

`updateIdQuery` in `lib/server/query.js` converts each hex under `find[_id]` to an ObjectId,
including the leaves of an `$in` or `$nin` list. #8758's `matchEitherForm` replaces a plain
ObjectId equality with an `$in` of its forms, and leaves operator objects unchanged, so a list
still asks only for ObjectIds.

**Reproduced 2026-09-24**, probe P-ID-11: with one string-stored and one ObjectId-stored treatment,
`GET ...?find[_id][$in][]=<string>&find[_id][$in][]=<oid>` returns 1 and the DELETE of the same
list removes only the ObjectId record, on `v15.0.8`, `dev` `ddd9b600` and `6d120fa2`.

**Fix shape, not measured:** expand each hex leaf of `$in` to its forms, and each leaf of `$nin`
likewise, in `matchEitherForm`.

### BF-112 · an auth subject created with a hex `_id` cannot be deleted by it

`lib/authorization/storage.js` `create` inserts the posted subject as given, so a 24-hex `_id` is
stored as a string; `remove` deletes `{_id: new ObjectID(_id)}` only. `save` converts through
`normalizeRequiredObjectId`. Only an admin can create or delete subjects. The access token is a
digest of `_id.toString()`, which is the same for either form.

**Reproduced 2026-09-24**, probe P-ID-12: POST `/api/v2/authorization/subjects` with a hex `_id`
answers 200 and stores a string; DELETE `/api/v2/authorization/subjects/<hex>` answers 200 and the
subject is still stored, on `v15.0.8`, `dev` `ddd9b600` and `6d120fa2`.

**Fix shape, not measured:** `toStoredId` on create and `idForms` on remove, as #8758 does for
profile.

### BF-113 · on #8758, `idForms` accepts a 12-character string

`idForms(id)` builds `new ObjectID(id)` for anything that is not already an ObjectId. The header
says anything but an ObjectId or a 24-hex string throws. Driver 5.9 also accepts a 12-byte string:
`idForms('abcdefghijkl')` returns `[ObjectId('6162…6c'), '6162…6c', 'abcdefghijkl']` on
`6d120fa2` (run). `staleStringForms` guards with `isHexId`; `profile.save` and the `remove` of
food, activity and profile call `idForms`/`stringIdForms` on a non-hex id without that guard, so a
12-character id would delete by the derived hex as well (read, not run). The v1 routes refuse
non-hex ids with 400, so only callers inside the server reach it.

**Fix shape, not measured:** guard with `isHexId` before `idForms` at those call sites, or make
`idForms` throw on anything else, as its comment says.

### BF-114 · an AAPS open-ended loop disable keeps alerts off after the loop is back on

AndroidAPS uploads a change of running mode as an "OpenAPS Offline" treatment with a `mode`. A
disable with no end time is uploaded with an open-ended duration: 2147483647 minutes in the shape
PR #8568's tests use, and 10 years with `originalDuration` 0 in AAPS dev
(`plugins/sync/.../nsclientV3/extensions/RunningModeExtension.kt`, commit `ac61c43960`, read).
Turning the loop back on uploads a second record, `CLOSED_LOOP` (or `OPEN_LOOP`,
`CLOSED_LOOP_LGS`) with duration 0; the first record is not shortened.

`openaps.findOfflineMarker` (`lib/plugins/openaps.js`) reads each "OpenAPS Offline" record as
`[mills, mills + duration]` and returns the newest that contains the current time. The re-enable
record has no span, so the disable is returned. While it is, `statusLevel` does not compute the
"not looping" warning or urgent level, and `pump.js` does not raise pump alert levels. Nothing on
the page says alerts are off; the loop pill shows offline.

**Reproduced 2026-09-25** with [`tools/lab/aaps-offline/probe.js`](../../../tools/lab/aaps-offline/probe.js),
which runs the shipping `processTreatments` and `findOfflineMarker` on synthetic records: 5 hours
after a re-enable, the marker is on for both shapes on `v15.0.8` `92d08342` and `dev` `4f705217`.
Controls on every tree: a finite 60-minute disable 6 hours ago is off; an open-ended disable with no
re-enable is on. On PR #8568 `de8efff0` the released shape is cleared and the AAPS-dev shape is
not. Not run: a booted server, the alarm notification itself, or AAPS.

**Fix shape (PR #8568, measured above):** end an open-ended `DISABLED_LOOP` at the next running-mode
record from the same pump or uploader. It also needs the AAPS-dev shape (for example `mode`
`DISABLED_LOOP` with `originalDuration` 0 and a duration over some bound) and a test on the alert
level. The day-to-day report (`lib/report_plugins/daytoday.js`) draws the bar from the raw records
and would still show it open-ended.

### BF-115 · an entry or treatment with an unusable `_id` is stored with it, and one such value stops the server

entries and treatments are written with `updateOne`/`replaceOne` with `upsert: true`. An upsert that
inserts keeps the `_id` in the update or replacement, unlike `insertOne`/`insertMany`, where the
driver assigns one when the field is empty. `normalizeEntryId` and `normalizeTreatmentId` convert a
24-hex string and drop a non-hex string, and leave any other value in place. The upsert filter then
falls back to `sysTime` + `type` (entries) or `created_at` + `eventType` (treatments), and the
insert writes the value as the record's `_id`. For one value the request also answers 500, but the
record is already written. `ddata.processRawDataForRuntime` (`lib/data/ddata.js`, reached from
`dataloader.js`) converts every loaded `_id` with `toString`, so the next load throws and the
process ends; a restart loads the same record and ends again. `dataloader.js`, `calcdelta.js` and
API v3 `normalizeDoc` make the same assumption.

**Measured 2026-09-25** on `v15.0.8` `92d08342` and #8758 `ab7b22d6` (MongoDB 7.0.43, Node
22.23.2): a sweep of 21 create paths × 5 unusable values. Three paths store the crashing value (v1
POST `/entries`, POST `/treatments`, PUT `/treatments`); devicestatus, profile, food and activity
POST and PUT, websocket `dbAdd` and API v3 POST assign an ObjectId for it. v1 entries and
treatments also store three other unusable values with 200; websocket `dbAdd` stores two and API
v3 POST four, without a crash. Positive control: with the record removed, the server stays up.

**Fix (`17add44b`, local):** `object-id-forms.dropEmptyId` drops an `_id` that is empty or neither
a string nor an ObjectId (an ObjectId from another copy of `bson`, by `_bsontype`, is kept);
`normalizeEntryId` and `normalizeTreatmentId` call it. The four loaders accept a stored record
without an id, so a site that already holds one keeps running. Test: `tests/api.empty-id.test.js`.
Break-its: removing the call in either normalizer, or the `ddata` or `calcdelta` guard, fails a
named test. **Not fixed:** websocket `dbAdd` and API v3 POST, which store an unusable value without
a crash (queue BFQ-115 notes).

### BF-116 · on #8758, a devicestatus re-send fails the POST and loses the rest of the batch

#8758 stores a 24-hex devicestatus `_id` as the ObjectId it names and, once per batch, reads the
string forms of those ids so that a re-send of a string-stored record keeps the string and collides
(tests/api.devicestatus.resend-guard.test.js, "refused, as before"). A re-send of a record stored
with the ObjectId, which is every record #8758 creates, now collides too. `insertMany` is ordered,
so the POST answers 500 at the collision and nothing after it is stored. The same 500 and loss
already happen on 15.0.8 for a string-stored record; on 15.0.8 the far more common ObjectId-stored
record was stored again, as a string copy.

**Measured 2026-09-25** (corpus Q2b, reproduced by the review): `[re-sent, new]` → 500 with the new
status lost; `[new, re-sent]` → 500 with the new one stored; a re-send alone, in lower or upper
case → 500; on 15.0.8 each is 200 with a string duplicate. Swapping `lib/server/devicestatus.js`
back to `dev`'s gives 15.0.8's cells exactly. No AID uploader in the corpus sends a devicestatus
`_id`: Loop sends `identifier` (NightscoutKit `DeviceStatus.swift`), Trio and AndroidAPS send
none. A Loop-shaped status posted twice plus a retry is stored three times on both builds.

**Fix (`c3a34bac`, local):** the read asks for every form of each id; a re-sent status is answered
with the `_id` it is stored under (the ObjectId copy when both exist) and not written; the same new
`_id` twice in a batch is stored once; the insert is unordered and accepts a duplicate-key error
only for a status sent with its own `_id` (a retry that raced its first POST), and fails on any
other error. #8758's resend-guard tests and CRUD matrix change from 500 to 200, marked `CHANGED
EXPECTATION`. Break-it: an ordered insert fails the race test.

### BF-117 · an API v3 DELETE of a record stored twice leaves one copy valid; on #8758 v3 takes the older copy

`utils.filterForOne(identifier)` matches the v3 document with that identifier and v1 records whose
`_id` is the identifier in any form, so it can match two copies of one record: the string `_id`
record and the ObjectId one an edit on 15.0.8 or earlier added beside it. `markAsDeleted` and
`deletePermanently` write one document (`writeFilter` → `updateOne`/`deleteOne`), so the other
copy stays valid and is returned by v1 time-window reads and v3 search. On #8758 v1 DELETE and
websocket `dbRemove` remove both copies (BF-110, decided). Which copy `findOne` and `writeFilter`
take is decided by a sort on `identifier` alone, which the two v1 copies tie on: on #8758 the string
copy in every trial, on 15.0.8 the ObjectId copy. On a real site the ObjectId copy is the one that
holds the edit, so on #8758 v3 GET shows, and PATCH and PUT write, the stale copy.

**Measured 2026-09-25:** corpus Q10/Q10b (both builds leave one copy valid; 15.0.8 the string one,
`ab7b22d6` the ObjectId one); review, 40 trials in each storage order on MongoDB 4.4 and 7: `ab7b22d6`
picks the string copy 40/40 for GET, PATCH, PUT and DELETE.

**Fix (`63dd716c`, local):** DELETE uses `updateEveryForm`/`deleteEveryForm` (`updateMany`/`deleteMany`
over `filterForOne`); `findOne`, `findOneFilter` and `writeFilter` sort `{identifier: -1, _id: -1}`,
which takes the ObjectId copy. Tests: `tests/api3.delete-every-form.test.js` (GET and PATCH in both
storage orders, soft and permanent DELETE, a control record); #8758's v1/v3 pair DELETE test and two
sort-pinning helper tests change, marked `CHANGED EXPECTATION`. Break-its: each of the four changes
reverted fails a named test; the read-sort test fails only with the ObjectId copy stored first,
which is why both orders run. **Not fixed:** v3 PUT/PATCH and websocket `dbUpdate` edit one or both
copies and leave two records, so #8758's advice "edit either one: the two become one record" holds
only for v1 PUT/POST (queue OID-V3-EDIT-MERGE, OID-WS-EDIT-MERGE).

## 3. How to use this register

1. **Anything found while doing multitenancy work that is also broken today gets an entry
   here**, at the time it is found, with its evidence link. The register is the mechanism that
   keeps that promise.
2. **Prefer landing these independently.** Each one is small, each ships to every current
   operator, and none needs a tenancy decision.
3. **Release-note the behaviour changes.** BF-02 and BF-03 change what queries return. That is
   the point, and it should arrive as a documented fix. The note is in
   cgm-remote-monitor's `CHANGELOG.md` under `[Unreleased] / Fixed`, naming the collections and
   fields whose results change, with before/after examples.
4. **Keep severities honest.** "Wrong answer with HTTP 200" is worse than "slow", and both are
   worse than "noisy". The table is sorted by that, not by effort.
5. **Allocate an id by reading the highest in §1/§1b at the moment you write it** — never the one
   your brief quoted, because concurrent sessions file here.
6. **Check it is not a restatement before you file it.** BF-12 is closed as `invalid` and is kept
   rather than deleted precisely because a deleted wrong entry gets raised again. Several of the
   entries filed on 2026-09-15 began as separate proposals and were merged into one, or folded into
   an existing entry as an amendment — the bulkUpsert scope findings amend BF-21 rather than taking
   ids, and three separate "everything says 15.0.9" proposals became one BF-60.
7. **Put it in §1 or §1b by the ships-to-operators-today test, not by how important it feels.**
   §1 means *present in what an operator runs today*, which is `master` / 15.0.8 — not `dev`, not a
   cut branch, not an unmerged `bf/*` branch. That test is the only thing making §1 mean anything,
   and widening it would cost more than the entries it would admit.
8. **Say whether a prescribed fix has been run.** An unrun prescription is marked **UNVERIFIED**
   in place rather than left to look settled.

## 4. Where this file sits

| document | relationship |
|---|---|
| [execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) | the reasoning, the decisions and the task definitions. Its §0 is the map of every other document |
| `queue/work-queue.yaml`, [`queue/QUEUE.md`](../../../queue/QUEUE.md), [`queue/README.md`](../../../queue/README.md) | **authoritative for item STATE**, because its state is measured by a gate rather than asserted by an editor. This register is authoritative for **defect facts and ids** |
| [PR sequencing](phase0-pr-sequencing-2026-09-15.md) | how the ten Phase 0 branches land |
| [maintainer release brief](maintainer-release-brief-2026-09-15.md) | the same batch, presented as one decision |
| [semver and release versioning policy](../modernization/semver-and-release-versioning-policy-2026-09-15.md) | what version number each of these fixes forces |

> **One gap in that policy is worth knowing while reading this file.** Its surface ladder has no
> question for **what the client computes and shows a person**, so **BF-35** — the bolus
> calculator's quick-pick chooser resolving the wrong record, graded **high** here — classifies as a
> *patch* under it and carries no operator-facing note obligation at all. The HTTP bytes are
> identical and the defect is entirely in the browser. BF-36 is the same case. The policy document
> records this as an open decision rather than silently adopting a fix; it is flagged here so that a
> severity in this register is not quietly downgraded by a version number somewhere else.

### BF-87 · the `qs` override holds the connector below its range and pins the server's query parser

`overrides.qs = "6.15.1"` and `overrides.request.qs = "6.15.1"` were added by `5ab0af7a` ("Remediate runtime dependency CVEs", 2026-05-10), when 6.15.1 was the remedy. Since then the connector raised its own floor to `^6.15.3` and three advisories were published whose ranges include 6.15.1. `overrides` suppresses the `ERESOLVE` that would report the connector's range, so nothing says so — the BF-43 mechanism with a different package. Because the override is at the root, the single resolved copy is also the one express's and body-parser's query-string parsing uses, so the question is wider than the connector.

**Not reproduced as a runtime failure or an exploit.** What is asserted is the silent range violation and the advisory ranges.

**Merged 2026-09-23** via PR #8749 (merge `9fd4600e`; `bf/qs-6.16` `46b20b38`): both override values are 6.16.0, the only version outside all three ranges. The documented query shapes parse identically and the suite is unchanged; only malformed bracket keys change. It changes the parser every request passes through.

### BF-88 · the modernization branch's `TRUST_PROXY`-unset default changes the client address in four cases

`395f3207` ("Restore proxy compatibility by default", `lib/server/client-ip.js` on
`origin/chore/nightscout-modernization` `b1bdaca0`) does not reproduce the address `forwarded-for`
gives on `origin/dev` `74fc6619` in four cases: an IPv6 entry after the first in a comma-and-space
`X-Forwarded-For` chain; an IPv4 address with a non-numeric port suffix; a request with no socket
remote address; and a request carrying more than one forwarding-header family (dev's precedence
depends on which family earlier requests used; the branch's order is fixed).

**Reproduced** by a differential probe. `bf2/auth-hardening` `8b975b41` pins dev's behaviour for the
unset default, and restoring `395f3207`'s `client-ip.js` there fails exactly 7 of 48
`tests/client-ip.test.js` cases (re-run 2026-09-22). **Severity: low** — edge-case inputs, but the
address is the failed-authentication delay's key and the setting is presented as
compatibility-preserving, so an upgrader has no warning.

**Decided 2026-09-23 (maintainer):** the cuts keep 15.0.9's unset default, `forwarded-for` as on
`dev`; `395f3207`'s fixed-precedence normalisation is not taken, and cut 5's four
`tests/client-ip.test.js` expectations are replaced by 15.0.9's when the cuts are rebased. No flag
for the other normalisation: with `TRUST_PROXY` unset the forwarding headers come from any peer, so
neither answer is a security boundary; an address list (`proxy-addr`) is the deterministic path.
The unset path is revisited when `TRUST_PROXY`'s default is flipped.
