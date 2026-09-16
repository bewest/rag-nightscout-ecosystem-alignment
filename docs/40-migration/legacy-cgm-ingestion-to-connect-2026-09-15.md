# Retiring the legacy Dexcom bridge and MiniMed mmconnect: migration plan

**DRAFT REQUIRING REVIEW.** Nothing in this document may be relied upon, published, acted on, or
used to gate a release until a qualified reviewer has verified it. §10 lists what the reviewer must
check. §3 and §4 are written for people running Nightscout for themselves or a family member and
are **not medical advice**.

**Rewritten 2026-09-16** against the evidence in
`docs/60-research/e1-dexcom-path-comparison-2026-09-15.md` (Dexcom) and
`docs/60-research/e2-medtronic-path-comparison-2026-09-15.md` (MiniMed). Those two studies tested
the premises of the previous revision of this file from source. **Several of them did not survive.**
§0 says what changed and §9 says what this document now retracts.

Refs this revision was written against, re-verified on 2026-09-16 rather than carried over:

| ref | value |
| --- | --- |
| `cgm-remote-monitor` `origin/dev` | `a8888f0d` |
| `cgm-remote-monitor` `origin/master` | current release train |
| parcel 4 | `origin/chore/mime-exposure-review` |
| parcel 5 | `origin/chore/nightscout-modernization` (contains parcel 4) |
| connector pin on `origin/master` | `v0.0.13` tarball |
| connector pin on `origin/dev` | `234d47c8` tarball |
| connector pin on parcel 4 | `c962a13f` |
| connector pin on parcel 5 | `b77e5bb` |
| prepared connector release | `v0.0.14` = `649a7de`, sitting directly on `c1cce2a` (the BF-34 fix) |

Every claim below is labelled **[R]** reproduced (a command or harness was run and produced the
result quoted) or **[S]** read-derived (established by reading source only). Claims attributed to E1
or E2 carry that study's own label. **Measured across this programme, every register claim that had
to be retracted was read-derived; none that began as a reproduction has been.** Treat **[S]** rows
accordingly.

**No network request was made, no vendor was contacted, no real account, credential or patient data
was used, no branch or worktree was modified, and nothing was pushed, merged, tagged or published in
preparing this document.**

**Adversarially reviewed 2026-09-16 by a second agent, which re-ran every load-bearing command
against the repositories rather than reading the reports.** Nine changes were made in place, each
marked where it sits. The three that change what a reviewer or an operator would do:
- **R4 and the §5.1 notice were mis-scoped.** `BRIDGE_SERVER=US`/`us` breaks on `origin/dev` and
  `origin/master` but is **fixed on parcel 4**, the release the notice accompanies. The notice as
  drafted would have warned operators about a configuration the retiring release handles correctly.
- **Two whole-site outage paths were understated** in §2.1 item 9 and §4.3: having `BRIDGE_*` and
  `MMCONNECT_*` set together, or `BRIDGE_*` alongside a non-`dexcomshare` `CONNECT_SOURCE`, does not
  leave one feed unsupported on the retiring release — it stops the site from booting. Reproduced.
- **Two residues that E1 and E2 left open had been dropped** from §2.3 and are restored as U15 and
  U16. Neither has a §6 owner yet.
Also retracted: §9.3's first bullet, which "corrected" an error that is not present in E1 or E2.
Everything else checked — every SHA, pin, path, line number, log string, boot-error mechanism,
alarm gate, backfill bound, backoff arithmetic and §8 command — reproduced as written.

---

## 0. What changed in this revision

The previous revision treated this retirement as the highest-stakes change in the programme, on the
premise that the compatibility shims were unvalidated and that the headline failure mode was "a
user's glucose data silently stops arriving". **The instinct was right and most of the specific
mechanisms were wrong.** E1 and E2 moved five things:

| # | Previous revision | Evidence says | Consequence for this plan |
| --- | --- | --- | --- |
| 0.1 | The Dexcom migration is something parcels 4/5 introduce, and therefore something to validate before they ship. | **The Dexcom migration is already the default on `origin/dev` and `origin/master`.** `lib/server/bridge-connect-compat.js` and `migrateBridgeToConnect()` ship today (introduced by `a91e8ee4`); `setupBridge` stands down for Connect. Parcels 4/5 remove the **fallback**, not the migration. **[R]** (E1 §0.1; independently re-verified here — the shim is present in `git ls-tree origin/dev lib/server/` and absent only for MiniMed) | The Dexcom half has had a whole release cycle of production exposure. The alarmed framing is retired. What remains at risk is the set of operators for whom the *fallback* is load-bearing. |
| 0.2 | The MiniMed migration shim is comparably placed. | **There is no MiniMed shim on anything shipped.** `lib/server/mmconnect-connect-compat.js` exists only on parcels 4 and 5. **[R]** re-verified here across all four refs. | The two vendors are not at the same maturity and this plan stops treating them as one change. |
| 0.3 | Connect is the safer path, so the risk is confined to the cutover mechanics. | **On the pins operators can reach today Connect's MiniMed source is measurably worse than the package being retired** — no `sg !== 0` sentinel filter, `devicestatus.created_at` stamped `now`. Fixed only at `c962a13f` and `v0.0.14`. **[R]** (E2 §C2; re-verified here: the filter is present at `c962a13f` and `v0.0.14`, absent at `v0.0.13` and `234d47c8`) | `bf/connect-pin` is now a **precondition of the deprecation release**, not a parallel tidy-up. |
| 0.4 | The MiniMed timestamp divergence is a defect in Connect that the retirement should fix. | **The divergence exists in both implementations, in opposite directions, selected by whether the vendor payload carries a zone designator.** For zone-less payloads — the shape the retired package's own recorded fixtures use — it is **Connect** that files the reading in the future, which silences the stale-data alarm. **[R]** (E2 §5) | The retirement improves this for some users and worsens it for others. This is the single residue whose failure mode is a person's data stopping without the software saying so, and it now drives §6 and §8. |
| 0.5 | "Nothing is lost" was treated as the maintainer's claim to be disproved wholesale. | **It is true of stored glucose history and false of settings.** Entry records are field-for-field identical except `device`; the `{sysTime, type}` upsert key means the cutover cannot duplicate history. Eight named settings are dropped across the two vendors. **[R]** (E1 §1 rows 9–14, E2 §4) | The deprecation notice gets a short, exact, defensible residue list instead of a general warning. |

**A document that keeps warning about a risk the evidence has retired trains people to ignore it.**
The Dexcom alarm language of the previous revision is deleted rather than softened. The MiniMed
timestamp caveat is kept and sharpened, because that is the one the evidence made *worse*.

---

## 1. The decision this plan serves

**Decided by the maintainer, 2026-09-15:** parcels 4 and 5 travel together behind a deprecation
release, with little or no waiting period. Parcel 4 is contained in parcel 5 (verified linear), so
"ship 5, hold 4 back" is not achievable as a merge. This plan does not argue against that decision.
It states what must be true for it to be safe, and what the deprecation release has to say.

The maintainer's stated reasoning, and what the evidence did to each clause:

| Maintainer's words | Verdict |
| --- | --- |
| "The old medtronic does not work" | **Partly confirmed, with one total break proved and the general claim unproven.** Care-partner (follower) accounts cannot work through Nightscout at all — `lib/plugins/mmconnect.js` `getOptions` never plumbs `patientId`, so a follower posts `patientId: undefined`. The US login branch is dead code (`if (1 \|\| CARELINK_EU)`). `MMCONNECT_MAX_RETRY_DURATION` is vestigial (`let maxRetry = 1; // No retry`). **[R]** (E2 §1). But **no mechanism was found that proves the patient-role EU path is dead**, and E2 declined to manufacture one. |
| "the nightscout-connect module works better regardless" | **Confirmed for the code the deprecation release would ship; refuted for the code an operator reaches today.** `origin/master` pins `v0.0.13` and `origin/dev` pins `234d47c8`; neither has the sentinel filter or the `created_at` fix. **[R]** (E2 §C2) |
| "with modern dependencies" | **Confirmed.** The retired package declares `request@^2.88.0` (deprecated since 2020), `axios@^0.26.0`, `axios-cookiejar-support@^1.0.0`, `engines.node >= 12`. **[S]** (E2 §1c) — and E2 is explicit that dependency rot is a good reason to retire and **not** a reason the feed would stop. |
| "includes an auto adoption/migration path" | **Confirmed for Dexcom on everything shipped; refuted for MiniMed on everything shipped.** The MiniMed shim arrives only with parcel 4 — and when it does arrive it is well built: idempotent, and on half-failure it builds into a local copy and discards it, so `env.extendedSettings` is byte-identical and no half-written credentials survive. **[R]** (E2 §6b) |
| "so nothing is lost" | **True of stored glucose history. False of settings and of several legacy-tolerated configurations.** See §5. |
| "even for Dexcom, nightscout-connect has some adjustments that allow more consistent access, **from what I understand**" | **Confirmed, the hedge was warranted, and it is right for a reason the maintainer did not give.** The adjustments are real and larger than "some". But it is **refuted as a blanket claim**: on a server-invalidated session Connect is categorically worse than the thing it replaces. **[R]** (E1 §3) |

**The parts that are provable are a good enough case for retirement on their own.** Dead US branch,
no retry, no follower support, an unmaintained dependency stack, a crash-on-malformed-response that
kills the whole Nightscout process on the Dexcom side — none of that requires the unproven claim.
This plan therefore supports the decision and spends its effort on the residues.

---

## 2. What the evidence settled

### 2.1 Confirmed — risk language retired

These were argued in the previous revision as reasons for caution. They are no longer reasons for
caution, and the text that treated them as such has been deleted.

1. **Connect survives vendor responses the legacy Dexcom bridge dies on.** A non-array body with
   status < 400 gives the legacy path an uncaught `TypeError: glucose.map is not a function`;
   `cgm-remote-monitor` registers no `uncaughtException` handler anywhere, so this **terminates the
   Nightscout process** — a whole-site outage, not a dark CGM feed. Connect's `Array.isArray` guard
   returns `{entries: []}` and the loop continues. **[R]** (E1 §1 row 5). *This is the single
   strongest point in the maintainer's favour and it is a safety argument, not a tidiness one.*
2. **The Dexcom auto-migration is already the default**, has been since `a91e8ee4`, and
   `setupBridge` already stands down for Connect. The deprecation clock started then. **[R]**
3. **Entry fidelity is exact.** Identical keys, identical values, identical trend/direction tables
   (character-for-character the same functions). The only differing field is `device`. **[R]**
4. **The cutover cannot duplicate Dexcom history.** `lib/server/entries.js` upserts on
   `{sysTime, type}`, and `device` is not part of the key. Re-verified here: `upsertQueryFor`
   returns `{ sysTime: {$eq}, type: {$eq} }` whenever both fields are present, which is unconditionally the
   first branch. *Correction made 2026-09-16: an earlier draft said “the connector emits no `identifier`
   field that would take the other branch”. On `origin/dev` there is no `identifier` branch — only the
   stale comment at `lib/server/entries.js:130` (“prefer identifier, fall back to sysTime+type”) says
   otherwise, and `upsertQueryFor` never reads `identifier`. The conclusion is unchanged and in fact
   stronger.* **[R]**
5. **Vendor load falls by more than an order of magnitude.** Legacy makes 24 auth + 24 login + 24
   glucose requests per hour (~550 authentications/day/site) because `bridge.js` builds a fresh
   `engine()` closure every poll and never reuses a session. Connect: 1 + 1 + 14. **[R]**
6. **TLS verification comes back on.** Legacy sets `rejectUnauthorized: false` on Authenticate,
   Login, LatestGlucose **and** the Nightscout upload. **[R]**
7. **CGM readings stop being printed to the server log.** Legacy runs `console.log('Entries',
   entries)` every poll. The connector's logger prints a message plus an HTTP status and never the
   payload. **[R]**
8. **Backfill becomes bounded and database-derived** (2 days, ~576 readings) instead of unbounded
   and process-local (a 30-day gap makes legacy ask for `maxCount=8641`; after any restart legacy
   re-fetches `BRIDGE_MINUTES` regardless of what is stored). **[R]**
9. **The MiniMed shim, when it arrives, is well behaved.** Idempotent; explicit Connect values win;
   no half-written credentials on failure (it builds into a local copy of `connect` and only assigns
   it on success). **[R]** **Qualified 2026-09-16:** it "refuses with an explanatory error" when a
   different `CONNECT_SOURCE` is already set — but that refusal is not clean in its *effect*. The
   error goes to `ctx.bootErrors`, which `lib/server/app.js:202-206` turns into `app.get('*',
   bootErrorView)` before every router, so **the whole site goes down**, exactly as for a missing
   `CONNECT_COUNTRY_CODE` (R8). Reproduced by executing parcel 4's two shims in `bootevent.js`'s
   order. **[R]** The message is good; the blast radius is the site. This row should not be read as
   retiring any caution about the source-conflict case — see the end of §4.3.
10. **Follower accounts are gained, not lost.** Connect plumbs `carelinkPatientUsername` with a
    fallback to the account's patient list. **[R]**

### 2.2 Refuted — carried, with the caveat

Each of these is a way the retirement can make someone's data worse. They are stated plainly here
and each one has an owner in §6 or §8.

| # | Claim | What is true instead | Basis |
| --- | --- | --- | --- |
| R1 | The connector currently pinned is better for MiniMed. | `v0.0.13` (master) and `234d47c8` (dev) ingest CareLink gap sentinels as `sgv: 0`. While a `0` is the newest entry, `lib/plugins/simplealarms.js` skips the **entire high/low evaluation** (`lastSGVEntry.mgdl > 39`). Fixed at `c962a13f` / `v0.0.14`. **And `dev` already prints a boot-time deprecation warning steering operators at Connect** — live advice landing on the bad pin. | **[R]** E2 §3a; pin comparison re-verified here |
| R2 | The retirement improves the timezone/stale-alarm hazard. | It **worsens** it for one large class of user. With a zone-less payload (the shape the retired package's own recorded fixtures use) and a pump east of the server clock, **Connect** files the reading in the future. Reproduced end to end through both shipping transforms plus the shipping `lib/plugins/timeago.js`: pump UTC+2, server UTC, feed genuinely dead 40 minutes — legacy files at the true instant and raises the urgent stale alarm on both paths; Connect files 2 h in the future (age −80 min), `checkStatus` returns `current`, browser alarm false, zero push alarms. A zone-**bearing** payload inverts the roles. | **[R]** E2 §5; the `timeago` guard re-verified here (`if (!lastSGVEntry \|\| lastSGVEntry.mills >= sbx.time) return;`, and `sbx.time - mills > threshold` for the browser path) |
| R3 | Staging the new settings alongside the old is safe. | **Safe for Dexcom, unsafe for MiniMed.** `setupBridge` stands down for Connect; `setupMMConnect` has no such guard and starts the legacy runner unconditionally. Re-verified here by running the §8.5 command: inside `setupMMConnect` on `origin/dev` the count of `extendedSettings.connect` is **0** (`setupBridge` scores 1). *It does contain the bare word `connect` four times — `mmconnect`, and the `nightscout-connect` deprecation string — which is why §8.5 warns against grepping for it. An earlier draft of this row said “no reference to `connect` at all”, which was wrong and contradicted §8.5.* Both paths then ingest, and because of R2 they compute different `sysTime` values, so the `{sysTime, type}` upsert does **not** absorb the duplicates. | **[R]** E2 §6a (BF-45); re-verified here |
| R4 | The Dexcom auto-migration is safe for every configuration legacy tolerated. | `BRIDGE_SERVER` values that are neither empty, nor `EU` case-insensitively, nor dotted are forwarded verbatim as a hostname. `US` → `https://US`, `us` → `https://us`, `EU1` → `https://EU1`, `ous` → `https://ous` — all unresolvable — and `validate()` returns `ok: true`. Legacy fell back to the US host for all of these. **⚠ SCOPE CORRECTION MADE DURING ADVERSARIAL REVIEW, 2026-09-16 — a reviewer must confirm the consequence below.** This row was written without a ref and is true only of `origin/dev` and `origin/master`, whose shims are byte-identical (`git diff origin/master origin/dev -- lib/server/bridge-connect-compat.js` is empty). **Parcel 4 — the retiring release — adds an `=== 'US'` arm and maps `US`/`us` to `shareRegion: 'us'` correctly.** Reproduced by executing both shims over the same eight `BRIDGE_SERVER` values: `US`/`us` give `{server:'US'}` / `{server:'us'}` on `dev` and `{region:'us'}` on parcel 4; `EU`/`eu` give `{region:'ous'}` on both; `EU1`, `ous` and any dotted hostname are forwarded verbatim on both. **[R]** So the mechanism survives the upgrade but the affected population narrows to values that are neither blank, nor `EU`/`US` case-insensitively, nor a resolvable hostname. The `CONNECT_SHARE_REGION=eu` trap is unchanged on every ref (`_known_servers` has only `us` and `ous`; `url.format({protocol:'https', host: undefined})` is `'https:'`, confirmed by execution). **[R]** The same trap natively: `CONNECT_SHARE_REGION=eu` gives `baseURL = 'https:'` with `ok: true`. **The region branch of the shim is untested**: two of five ablations stayed green against the existing 4-test suite. | **[R]** E1 §2; the shim's `else { shareServer = bridgeSettings.server }` branch re-verified here |
| R5 | Connect gives more consistent Dexcom access, without qualification. | On a **server-invalidated session** — the ordinary way Dexcom Share ends a session — the fetch machine's rejection never reaches the session machine, which stays `Active` with a dead token until the hard-coded 24 h expiry. 25 simulated hours of permanent 401 on the pinned connector: `auth=1 login=1 glucose=23`. Legacy recovers on the next poll. | **[R]** E1 §3 |
| R6 | The currently shipping connector degrades gracefully under a sustained vendor problem. | The pinned `backoff()` merges `{...config, ...defaults}`, so the caller's 150 000 ms becomes 256 ms at attempt 1 (586× too fast) **and** `exponent_ceiling` caps the *exponent* rather than the delay, so attempt ≥20 yields `256 × (2²⁰−1)` = **74.6 hours**. Retry storm first, three-day dark window second. Both halves ship on `dev` today. `v0.0.14` caps the cycle at 30 min and the frame at 5 min. | **[R]** E1 §4 (BF-34; the ceiling half is not in the register entry) |
| R7 | Nothing is lost. | **Dexcom:** `BRIDGE_INTERVAL`, `BRIDGE_MINUTES`, `BRIDGE_MAX_COUNT`, `BRIDGE_FIRST_FETCH_COUNT`, `BRIDGE_MAX_FAILURES` are not translated and have no Connect equivalent; cadence becomes a fixed 5 minutes. **MiniMed:** `MMCONNECT_STORE_RAW_DATA` (`carelink_raw` entries), `MMCONNECT_SGV_LIMIT`, `MMCONNECT_INTERVAL` are dropped. **Both:** the `device` label changes, splitting chart history across two names. | **[R]** E1 §5, E2 §4 |
| R8 | `CONNECT_COUNTRY_CODE` is a detail. | It is a **brand-new mandatory variable** the shim itself says cannot be inferred from `MMCONNECT_SERVER`, and on parcel 4 omitting it pushes a boot error that installs `app.get('*', bootErrorView)` and returns before every router — **the whole site goes down, not just ingestion** (BF-61). Every MiniMed operator must act by hand. | **[R]** E2 §6b |
| R9 | Connect handles every payload the retired package handled. | `transformPayload` guards `data.medicalDeviceFamily` and then does `data.markers.filter(...)` unguarded. The retired package's own recorded CareLink payloads have **no `markers` key**. The throw is synchronous inside `transformService`, before `Promise.resolve`, so `onError` never sees it, and with no `uncaughtException` handler the Nightscout process dies. **Present on `v0.0.13`, `234d47c8` and `v0.0.14`.** Every `markers` occurrence in the connector's own tests is `markers: []` — the absence has zero coverage. | **[R]** E2 §3c |
| R10 | `BRIDGE_MAX_FAILURES` is a safety knob. | At its default it is unreachable: `bridge.js` builds a fresh closure each poll so `failures` reaches at most 2 before being discarded, and `refresh_token()` resets it to 0 on every successful login. The README documents it as "how many failures before giving up". It does nothing. | **[R]** E1 §3 |
| R11 | Connect writes what legacy wrote. | Connect **additionally** writes treatments (meal bolus, correction bolus, BG check) that legacy never produced. For a MiniMed operator also running a pump uploader, Loop, Trio or AndroidAPS against the same Nightscout, boluses may arrive twice and be counted twice in displayed IOB. | **[S]** E2 §2 — read-derived, and it belongs in the notice as a thing to check, not as a silent gain |

### 2.3 Cannot be settled without a real vendor account

**This list is the actual content of the deprecation notice and of the pre-release checklist.** It
is not a caveat section; §6 assigns each item an owner and a pass criterion.

| # | Question | Why it decides something |
| --- | --- | --- |
| U1 | **Do real CareLink payloads carry zone designators on `sgs[].datetime` / `markers[].dateTime` / `sMedicalDeviceTime`, and do they carry `lastConduitDateTime`?** | Decides whether R2 is latent or active — the difference between the retirement fixing the stale-alarm hazard and causing it. **The one residue whose failure mode is a person's glucose data stopping without the software saying so.** |
| U2 | Does a real CareLink login still succeed for the retired package, patient-role, EU and US? | The entire "short deprecation window" argument rests on it. Source reading cannot answer it. Note the SSO flow is five steps of HTML scraping — structurally fragile, which is not the same as currently broken — and **the connector scrapes the same markup with the same regular expressions**, so it inherits the fragility. |
| U3 | Does the BLE periodic endpoint ever return a payload without `markers`? | If yes, R9 kills the Nightscout process on every poll, on every pin including `v0.0.14`. |
| U4 | Does Dexcom Share throttle, rate-limit or lock accounts under legacy's ~550 authentications/day? | The most likely mechanism behind the maintainer's "more consistent access". Cannot be confirmed here, and **if it is right the case for retirement is stronger than anything that was measured.** |
| U5 | How often does Dexcom invalidate a session server-side, and is the real session lifetime shorter than Connect's hard-coded 24 h? | Sizes R5. If shorter, Connect is dark for the remainder of every session window after the vendor expires a token, which converts R5 from an edge case into the normal case. |
| U6 | Does Dexcom Share still return HTTP 200 with a JSON error object, and how often? | That is the exact shape that kills the legacy process outright — the strongest single argument for retirement. The crash is proved; its frequency is not. |
| U7 | **How many operators are on a non-`EU`, non-dotted `BRIDGE_SERVER`?** | R4 is certain in mechanism and completely unknown in population. A census of deployed values is the single highest-value thing that could be done before deciding, and it is the item that should set the length of the notice. |
| U8 | Does the vendor tolerate a full CareLink SSO re-login every ~9 minutes? | Connect disabled token refresh outright (`// TODO: have never seen refreshSession work, disabling until further notice`) and relies on `EXPIRE_SESSION_DELAY`. Legacy refreshed the EU token near expiry. A rate-limit, CAPTCHA escalation or lockout here is invisible until it is live. |
| U9 | Does a care-partner request carrying `patientId: undefined` fail loudly or return empty data? | Decides whether the notice says the legacy follower path is "broken" or "silently returns nothing" — the difference between an operator noticing and not. |
| U10 | Does CareLink return history, or only a current snapshot? | Decides whether a MiniMed outage is recoverable at all. §3.2 currently marks this as read-derived. |
| U11 | Whether `maxCount` above 288 is rejected, clamped or errors at the vendor. | Neither implementation clamps. Determines whether reconnection after an outage backfills or fails outright — the moment an operator is most anxiously watching. |
| U12 | Which pump models and regions actually work on each side. | Neither implementation branches on model beyond `GUARDIAN` vs everything else, so source reading cannot enumerate this at all. The one part of "nothing is lost" no method available here could cover. |
| U13 | Do Connect's newly-written treatments double-count against an existing uploader on the same site? | R11. Would show up as inflated IOB — the kind of thing a notice must tell people to check. |
| U14 | The current state of the **legacy Dexcom** path against live Dexcom. | "The old medtronic does not work" is a statement about MiniMed. There is no equivalent statement on the record about Dexcom. If legacy Dexcom still works fine, every "worse" item above is a live regression risk; if it is already broken, most of them are moot. |
| U15 | **Is the G7-era `{accountId: …}` Authenticate response the only Dexcom response shape that has changed, or have `LoginPublisherAccountById` and `ReadPublisherLatestGlucoseValues` changed too?** (E1 §6 "Unknowable here" item 7 — **dropped from an earlier draft of this table and restored on 2026-09-16 during adversarial review**.) | Connect normalises exactly one shape. Nobody has checked the other two against a live account. Retiring the fallback means that if a second shape has drifted, there is no longer a second implementation to fail differently and reveal it. It is the same class of defect as the `glucose.map` crash in §2.1 item 1, which is the strongest argument *for* the retirement — so it must not be answered only in the retirement's favour. |
| U16 | **Does CareLink return `sg` in mg/dL universally, or in the account's display unit?** Both implementations copy `sg` straight through and **neither consults the `bgUnits`/`bgunits` field that is present in the payload** (E2 §2 table — **dropped from an earlier draft of this table and restored on 2026-09-16**). | Not a regression: identical on both sides, so the retirement neither creates nor fixes it. But it is an unexamined shared assumption for mmol/L regions, and its failure mode is glucose values displayed at roughly 18× their true magnitude, which is a **clinical**, not cosmetic, misread. A reviewer should decide whether it belongs in this plan at all or in a separate defect; it must not disappear simply because it is not caused by the retirement. |

---

## 3. IF YOUR GLUCOSE DATA HAS STOPPED — READ THIS FIRST

*This section and the next are for anyone running Nightscout for themselves or a family member. They
are placed before the technical sections on purpose. **This is not medical advice.** If a gap in
your data affects how you or someone you care for is managing diabetes, contact your diabetes care
team. Do not use this page to decide on insulin doses. While your data is uncertain, fall back to
your CGM's own app and to fingersticks as your care team has advised.*

**Words used here**

- **Nightscout** — the website you run that shows the glucose graph.
- **Ingestion** — how glucose readings get *into* Nightscout.
- **The bridge** / **mmconnect** — the old, built-in ways Nightscout fetched readings from Dexcom
  Share or from Medtronic CareLink. Both are being removed.
- **Nightscout Connect** — the newer component that replaces both.
- **Settings**, also called *environment variables* — the `NAME=value` configuration lines you set
  when you set Nightscout up: Heroku config vars, Azure application settings, a `.env` file, or a
  `docker-compose.yml`.
- **Rolling back** — putting the previous version of Nightscout back.
- **Backfill** — fetching readings from the recent past, not just the newest one.
- **UTC offset** — how far your local clock is from UTC, for example `+2` hours or `-7` hours.

### 3.1 Roll back first. Diagnose afterwards.

**This is the reliable fix. Do it before you spend time investigating.**

Redeploy the exact Nightscout version you were running before the upgrade, with the exact settings
you had before. Do not change your database. Do not change `API_SECRET`.

- **Docker:** redeploy the image digest you wrote down before upgrading.
- **Heroku:** `heroku releases`, then `heroku rollback vNNN`.
- **Azure:** redeploy from the previous deployment slot, or from the previous commit.
- **Source install:** `git checkout <the tag or commit you recorded>`, then `npm ci` with the Node
  version that release supported, then restart.

Rolling back the *application* does not change your database and does not delete any readings you
already have.

**You cannot fix this by flipping a setting on the new version.** On the version you are on today,
`DEXCOM_BRIDGE_USE_LEGACY=true` puts you back on the old Dexcom bridge. **On the release that
retires these paths, the code that reads that setting is deleted** — verified: the parcel-4 tree
contains no reference to it anywhere under `lib/`, and its README says the fallback is removed. The
setting will be accepted and will do nothing. Redeploying the previous version is the only route
back.

**So the single most important preparation step is §4.2 item 1: write down exactly what you are
running now.** That recorded version is your only way back.

**Keep your old `BRIDGE_*` / `MMCONNECT_*` settings too (§4.5) — but understand what they are for.**
They are what the *previous* version needs in order to fetch your data again after you roll back.
They will not keep you on the old path on the *new* version: the Dexcom ones are already being
handed to Nightscout Connect at startup on today's release, and the code behind both is deleted on
the retiring release.

### 3.2 What comes back, and what is gone for good

Be clear-eyed about this before you upgrade, not after.

| | Does it come back? |
| --- | --- |
| Readings already in your database before the problem | **Yes.** Nothing in this change deletes or rewrites your history. |
| Readings that arrived during the outage from a *different* uploader — phone app, Loop, Trio, AndroidAPS, xDrip+ | **Yes.** Those paths are untouched by this change. |
| **Dexcom Share** readings missed during an outage of **up to about 2 days** | **Usually yes**, once ingestion restarts. When Nightscout Connect starts it asks Dexcom for up to about 48 hours of history and up to about 576 readings, working out what it needs from what is already in your database. This is **better** than the old bridge, which worked it out from memory and re-asked for a fixed window after every restart. |
| **Dexcom Share** readings missed during an outage **longer than about 2 days** | **No. Gone from Nightscout permanently**, unless you import them another way. Nothing reaches further back automatically. |
| **MiniMed / CareLink** readings missed during an outage | **Probably not.** CareLink appears to hand over a recent snapshot rather than deep history, so assume a long MiniMed outage leaves a permanent hole. *(This is read from the source code and the recorded sample payloads; it has not been confirmed against a live CareLink account — see U10 in §2.3. A reviewer must settle it before this line is published.)* |
| **MiniMed** readings stored at the **wrong time** (§3.3) | **Repairable, but not automatically.** They sit in your database with a shifted timestamp. Nothing removes or corrects them for you. Ask in the community channels before running any bulk edit on your own database. |
| Your alarms during the outage | **Not recoverable.** Alarms fire on data as it arrives. An alarm that did not fire because no data arrived does not fire later. |

**An outage is not a cosmetic gap.** Treat "my data stopped" as something to fix within hours.

### 3.3 The failure that does not look like a failure

There are two ways this change can go wrong where **nothing tells you anything is wrong**. Both are
MiniMed-specific. Learn to recognise them.

**(a) Readings filed in the future.** If Nightscout stores your readings with a timestamp *ahead* of
the real time, the graph looks full and current. But Nightscout's built-in *"Stale data, check
rig?"* alarm — settings `ALARM_TIMEAGO_WARN` (default on, 15 minutes) and `ALARM_TIMEAGO_URGENT`
(default on, 30 minutes) — **only fires when the newest reading is in the past**. If your newest
reading is in the future, Nightscout believes it just heard from your sensor, so the alarm stays
quiet — including later, when your data genuinely stops. Verified in `lib/plugins/timeago.js` on
`origin/dev`: both the browser and the server alarm path return early when the newest reading is not
in the past. **[R]**

This happens when your pump's clock is ahead of the clock on the computer running Nightscout (most
hosted Nightscout servers run on UTC), *and* the data CareLink sends does not say which time zone it
is in. Whether real CareLink data says which time zone it is in is **not currently known** — that is
U1 in §2.3, and it is the most important open question in this whole plan.

**How you spot it:** the "minutes ago" pill next to your glucose number should count *up* from a
small number. **If it reads `future`, or sits at the same small number and never moves, stop and
roll back (§3.1).**

**(b) A gap reading stored as zero.** On the connector version currently shipping, a CareLink "no
reading here" marker can be stored as a glucose value of `0`. A `0` is not itself alarmed — and
while it is your newest reading, Nightscout's high/low alarm evaluation is **skipped entirely**, so
a genuinely high or low reading behind it would not raise an alarm either. Verified in
`lib/plugins/simplealarms.js`: the alarm check requires the newest reading to be above 39 mg/dL.
**[R]** This is fixed in the connector version the retirement release is expected to ship
(`bf/connect-pin` → `v0.0.14`), and §8 makes that pin a precondition.

**How you spot it:** a reading displayed as `0`, or as `0??`, on your graph.

*These two are different mechanisms with different symptoms. A future-dated reading switches off the
**stale-data** alarm; a zero reading switches off the **high/low** alarm. Neither switches off the
other.*

### 3.4 If you rolled back and data is still not arriving

1. **Check the vendor's own app first.** If your readings are not arriving in the Dexcom or CareLink
   app either, **Nightscout is not the problem** and rolling Nightscout back will not fix it.
2. **Look at your Nightscout startup log.** Lines containing `DEPRECATION WARNING`,
   `Executing setupBridge` or `Executing setupMMConnect` tell you which ingestion path started.
   **`Executing setupBridge` on its own proves nothing** — it is printed every time Nightscout
   starts, including when it then decides *not* to run the old Dexcom bridge. The line that says it
   actually ran is `DEPRECATION WARNING PLEASE CONSIDER nightscout-connect instead.` **printed immediately after `Executing setupBridge`** — the identical string is printed again after `Executing setupMMConnect` (`lib/server/bootevent.js` lines 376 and 392 on `origin/dev`), so the string alone does not tell you which path ran; its position in the log does. Corrected 2026-09-16. The line that
   says it stood down is `DEPRECATION WARNING Skipping legacy share2nightscout-bridge because
   nightscout-connect is handling Dexcom Share.` (Verified on `origin/dev`, `lib/server/bootevent.js`
   lines 369 and 376. **[R]**)
3. **Restore the settings you recorded.** If those startup lines are absent entirely, the old
   ingestion never started and your settings were probably changed during the upgrade.
4. **Ask for help in the Nightscout community channels**, quoting the release you are on and the
   last 30 lines of your startup log. **Remove your username, password and `API_SECRET` before
   pasting anything anywhere.**
5. **If the gap is affecting diabetes management, contact your care team.** This document cannot
   advise you on that.

---

## 4. Cutover runbook

*Plain language; the definitions in §3 apply here too. **Not medical advice.** Do this when you have
unhurried time — not at bedtime, and not on a day when you are depending on overnight alarms. If a
data gap would affect diabetes management, involve your care team first.*

### 4.1 Step 1 — Are you affected at all? Most people are not.

**Check the device name. That is the reliable test.** Open your Nightscout graph, hover over a
recent reading, and look at the device name.

| Device name | What it means |
| --- | --- |
| `share2` | The **old Dexcom bridge** is actually running — **you are affected.** On today's release there are two ways this happens: you set `DEXCOM_BRIDGE_USE_LEGACY=true`, **or** you have `BRIDGE_USER_NAME`/`BRIDGE_PASSWORD` set while `CONNECT_SOURCE` is something other than `dexcomshare` (for example `minimedcarelink`). The second case is the dangerous one: on the retiring release it stops your whole site from starting. See the end of §4.3. **[R]** |
| `connect-paradigm`, or anything starting `connect-` | The **old MiniMed plugin** — **you are affected.** |
| `nightscout-connect` | Already on Nightscout Connect for Dexcom — **the deletion does not affect you.** |
| starts with `nightscout-connect://minimedcarelink/` | Already on Nightscout Connect for MiniMed — the deletion does not affect you, but **read §3.3**, and check your pin against §8. |
| anything else | A different uploader. Not affected. |

**Then check your settings**, as a cross-check and for the MiniMed case:

- `MMCONNECT_USER_NAME` **and** `MMCONNECT_PASSWORD` set → you are on the **old MiniMed path** and
  **you are affected**. There is no automatic migration for MiniMed on any released version, so if
  these are set, the old plugin *is* running.
- `BRIDGE_USER_NAME` **and** `BRIDGE_PASSWORD` set → you supplied Dexcom Share credentials. **On
  today's release these are already handed to Nightscout Connect at startup and the old bridge
  stands down**, unless you also set `DEXCOM_BRIDGE_USE_LEGACY=true`. So `BRIDGE_*` on its own
  usually means you are *already* on the replacement. The device name settles it.

(Azure operators: the same names with a `CUSTOMCONNSTR_` prefix.)

If none of these is set, **this change does not affect you.**

### 4.2 Step 2 — Before you upgrade

1. **Write down exactly what you are running now** — version, tag, commit, or Docker image digest.
   **This is your only way back (§3.1). Do not skip it.**
2. **Write down your current settings**, including `API_SECRET`. Keep `API_SECRET` unchanged through
   the upgrade so your phone apps and uploaders keep working. Store it somewhere private.
3. **Back up your database.** This change performs no database migration. Take a backup anyway.
4. **Pick a good time.** Not overnight. Not before a long drive. Give yourself an hour where you can
   watch the graph, with your CGM's own app as a fallback.
5. **MiniMed only: find the two-letter country code for where your CareLink account was created**
   (for example `gb`, `de`, `us`). This is **not** the same as the region (`eu` / `us`), and it has
   **no default**. You will need it, and leaving it out takes your whole site down.

### 4.3 Step 3 — Staging the new settings. The answer differs by vendor.

**Dexcom — you may safely add the new settings before you upgrade.**

```text
CONNECT_SOURCE=dexcomshare
CONNECT_SHARE_ACCOUNT_NAME=<your Dexcom Share username>
CONNECT_SHARE_PASSWORD=<your Dexcom Share password>
CONNECT_SHARE_REGION=us        # use "ous" if you are outside the United States
```

This is safe because the Dexcom boot stage checks for Connect and stands down rather than running
both (`lib/server/bootevent.js` on `origin/dev`, **[R]**).

> **Use exactly `us` or `ous`.** Any other value — including `eu`, `EU`, `US`, or a region name you
> invent — is accepted without complaint and produces an address that cannot be reached, and the
> connector's own validation still reports success. Your data then stops with no error you can act
> on. Verified. **[R]** The same trap catches `BRIDGE_SERVER`: if yours is set to anything other
> than blank, `EU`, `US`, or a full hostname containing dots, **change it or remove it before you
> upgrade** — see R4 in §2.2. (`US` and `us` are handled correctly by the retiring release, but they
> are *not* handled by the release you are on today, so removing the setting is still the safe move.
> Corrected 2026-09-16 — see the scope correction in R4.)

**MiniMed — do NOT add `CONNECT_SOURCE` or `CONNECT_CARELINK_*` before you upgrade.**

The MiniMed boot stage has **no** stand-down check: it starts the old plugin whenever
`MMCONNECT_USER_NAME` and `MMCONNECT_PASSWORD` are set, regardless of Connect. Verified on
`origin/dev`: `setupMMConnect` never tests `extendedSettings.connect`, so it cannot stand down. **[R]** If you set both,
**both paths fetch your data at the same time** — and because the two paths can compute different
timestamps for the same reading (§3.3a), Nightscout's duplicate suppression does **not** absorb
them. You get a duplicated, time-shifted trace that nothing cleans up.

The one thing you may safely pre-stage for MiniMed is:

```text
CONNECT_COUNTRY_CODE=<two-letter country where the CareLink ACCOUNT was created>
```

On today's release this setting does nothing on its own, because Nightscout Connect only starts when
`CONNECT_SOURCE` is set. Setting it now means it is already correct at the moment you upgrade, which
is the moment it becomes mandatory.

> **Correction to earlier copies of this runbook.** An earlier revision told you to confirm this by
> looking for the log line `Skipping disabled nightscout-connect, no source driver spec`. **That
> string is not what your version prints.** Verified across the three connector versions an operator
> can be on: `v0.0.13` prints `Skipping disabled nightscout-connect, no source driver spec` and
> always prints it; `234d47c8` prints `Skipping connector without a source`; `v0.0.14` prints
> `Skipping disabled connector, no source driver` — and on the last two it is a **debug** line that
> does not appear at all unless `CONNECT_DEBUG` is on. **[R]** The early return itself is the same
> on all three, so pre-staging the country code is still safe; only the check was wrong.

Add the rest **at the same time as the upgrade, not before**:

```text
CONNECT_SOURCE=minimedcarelink
CONNECT_CARELINK_USERNAME=<your CareLink username>
CONNECT_CARELINK_PASSWORD=<your CareLink password>
CONNECT_CARELINK_REGION=eu     # use "us" for the US service
CONNECT_COUNTRY_CODE=<already set above>
```

> **`CONNECT_COUNTRY_CODE` is required and has no default.** If you leave it out, **your entire
> Nightscout site refuses to start** and shows an error page instead of your graph — not just
> ingestion, the whole site. This is the most likely way this upgrade goes wrong. Verified. **[R]**

**If you use the Dexcom bridge AND MiniMed together: stop here.** Nightscout Connect handles one
source at a time. **On the retiring release, leaving both sets of credentials in place does not
merely leave one feed unsupported — your whole Nightscout site refuses to start**, with the same
error page as a missing `CONNECT_COUNTRY_CODE`. Reproduced on 2026-09-16 by executing parcel 4's two
shims in the order `lib/server/bootevent.js` runs them: the Dexcom shim migrates first and sets
`CONNECT_SOURCE=dexcomshare`, the MiniMed shim then sees a different source and returns an error,
which is pushed to `ctx.bootErrors`, and `lib/server/app.js:202-206` installs `app.get('*',
bootErrorView)` and returns before every router. **[R]** You need a separate uploader for one of the
two feeds *before* you upgrade. Ask in the community channels before proceeding.

**The same applies if you have `BRIDGE_USER_NAME`/`BRIDGE_PASSWORD` set alongside
`CONNECT_SOURCE=minimedcarelink`** (or any `CONNECT_SOURCE` that is not `dexcomshare`). Reproduced:
on today's release that combination quietly runs the **old** Dexcom bridge — the shim declines to
migrate and `setupBridge`'s stand-down test requires `connect.source === 'dexcomshare'` — and on the
retiring release it becomes a whole-site boot error. **[R]** Remove the obsolete `BRIDGE_*`
credentials before upgrading.

### 4.4 Step 4 — Upgrade, then check that data is flowing

Upgrade. Then, within the first 15 minutes, check **all five**. One is not enough.

1. **Two readings, not one.** A new reading appears within 10 minutes and the "minutes ago" counter
   resets — then **wait about five minutes and confirm a second one arrives**. A single reading can
   be leftover backfill from before the upgrade.
2. **The device name has changed.** Hover over a *new* point. It should read `nightscout-connect`
   (Dexcom) or start with `nightscout-connect://minimedcarelink/` (MiniMed). If it still says
   `share2` or `connect-…`, the old path is somehow still running — **stop and get help.** A graph
   showing *both* names means both paths are ingesting.
3. **The time on the newest reading is right — MiniMed operators, this is the one that matters
   most.** It should match your pump's clock and your phone's clock within a few minutes. The
   "minutes ago" pill must count **up**. **If it reads `future`, sits frozen at a small number, or
   the graph runs off the right-hand edge, stop and roll back (§3.1).** That is §3.3a, and it will
   keep filing every reading at the wrong time while silently disabling your stale-data alarm.
4. **No boot error**, and your startup log contains `BRIDGE credentials are served by Nightscout
   Connect` or `MMCONNECT credentials are served by Nightscout Connect`. (Verified: parcel 4's
   `lib/server/bootevent.js` prints exactly these at lines 55 and 339. **[R]**)
5. **Your stale-data alarm still works.** Confirm `ALARM_TIMEAGO_WARN` and `ALARM_TIMEAGO_URGENT`
   are on, and confirm the newest reading's time is not ahead of now. This is the check people skip
   and it is the one that protects you overnight.

**MiniMed also:** check no reading is displayed as `0` or `0??` (§3.3b), and that the pump pill
(battery, reservoir, insulin on board) shows sensible values. **If you also run a pump uploader,
Loop, Trio or AndroidAPS against this same Nightscout,** check your insulin-on-board figure over the
next day: Nightscout Connect writes boluses and carbs that the old MiniMed path never did, so the
same dose could be recorded twice. If IOB looks inflated, raise it in the community channels — and
do not act on an IOB figure you have reason to doubt.

*None of the above is medical advice. If you are unsure whether it is safe to continue while your
data is uncertain, fall back to your CGM's own app and to fingersticks as your care team has
advised, and contact your care team.*

### 4.5 Step 5 — How long to keep the old path available

- **Keep the version you recorded for at least 30 days.** That is your rollback window. Do not
  delete the old image or artifact before then.
- **Keep your old `BRIDGE_*` / `MMCONNECT_*` settings for at least 7 days** — one overnight, one
  weekend, and at least one sensor change. They are not what keeps you safe on the new version
  (§3.1); they are what the previous version needs if you roll back. Leaving them set on the new
  version is not harmful: both shims are written to be repeatable and are verified idempotent. **[R]**
- After 7 good days, remove the old settings to avoid confusion later.

### 4.6 Step 6 — If data stops, or arrives at the wrong time

Go to **§3**. Roll back first, diagnose afterwards. Do not troubleshoot for hours while your feed is
dark.

---

## 5. The deprecation notice: what it must say

The decision is a short notice. A short notice is defensible **only if it is exact.** The residues
below are short, nameable, and were arrived at by diffing executed output, not by guessing. Drafted
for review; a maintainer owns the final wording.

### 5.1 Do not write "nothing is lost"

Write this instead, or something with the same content:

> **Dexcom.** Your glucose history is unaffected: records are written with the same fields and the
> same values, and Nightscout's duplicate suppression means the changeover cannot duplicate your
> history. What changes: the device name on new readings becomes `nightscout-connect` instead of
> `share2`, so charts or tools that group by device will show a break; and the settings
> `BRIDGE_INTERVAL`, `BRIDGE_MINUTES`, `BRIDGE_MAX_COUNT`, `BRIDGE_FIRST_FETCH_COUNT` and
> `BRIDGE_MAX_FAILURES` no longer do anything — Nightscout Connect polls every five minutes and
> decides its own backfill.
>
> **Check your `BRIDGE_SERVER` setting before upgrading.** If it is blank, or `EU`, or `US`, or a
> full hostname with dots in it, you are fine. **Any other value — for example `EU1` or `ous` — will
> be turned into an address that does not exist, and your data will stop with no error message.**
> Remove it or correct it first.
>
> *(Reviewer note, added 2026-09-16 during adversarial review. An earlier draft of this paragraph
> named `US` and `us` among the values that break. That is true of the release operators are on
> today and **false of the release this notice accompanies**: parcel 4's shim adds an `=== 'US'` arm
> and maps `US`/`us` to `CONNECT_SHARE_REGION=us`. Reproduced by executing both shims. Publishing
> the earlier wording would have told operators the retiring release breaks a configuration it
> actually fixes. **If this notice is ever republished against `dev`/`master` rather than against
> the retiring release, the `US`/`us` warning must come back.**)*
>
> **MiniMed / CareLink.** `CONNECT_COUNTRY_CODE` is new, mandatory, and cannot be worked out from
> your existing settings. **If you do not set it, your whole Nightscout site will not start.** Raw
> CareLink capture (`MMCONNECT_STORE_RAW_DATA`) is retired, as are the `MMCONNECT_SGV_LIMIT` and
> `MMCONNECT_INTERVAL` controls. The device name changes from `connect-paradigm` to
> `nightscout-connect://minimedcarelink/…`. **If you have Dexcom `BRIDGE_*` credentials set as well
> as `MMCONNECT_*` — or `BRIDGE_*` set alongside any `CONNECT_SOURCE` that is not `dexcomshare` —
> remove the obsolete set before upgrading: leaving both in place stops your whole site from
> starting, not just one feed.** Follower (care-partner) accounts, treatments, retry and
> a validated country setting are gained. **If you also run a pump uploader, Loop, Trio or
> AndroidAPS against the same site, check your insulin-on-board figure afterwards** — Connect writes
> boluses that the old path did not.

### 5.2 The notice's headline is `CONNECT_COUNTRY_CODE`, not the dependency removals

Every MiniMed operator must act by hand, and forgetting one variable takes down their whole site
rather than just their CGM feed. That is the migration's real cost, and it is what the release notes
must lead with. Release notes that lead with dependency modernization will be skimmed by exactly the
people who most need to act.

### 5.3 The notice must tell MiniMed operators what to watch, and why

§3.3 is the operator-facing form of the one unsettled question whose failure mode is silence. The
notice should carry its two checks — *the minutes-ago pill must count up*, and *no reading displayed
as `0`* — in the notice itself, not behind a link.

### 5.4 What the notice cannot honestly claim

- It cannot claim the legacy MiniMed path is dead. What is proved is: a dead US code branch, a
  documented retry setting that does nothing, no retry at all, an undocumented country default of
  `gb`, **no support for follower accounts**, and an unmaintained dependency stack. That is a
  sufficient case. Say it.
- It cannot claim Connect gives more consistent Dexcom access without qualification (R5).
- It cannot claim the migration is validated against live vendor accounts. Nothing in this programme
  has touched one.

---

## 6. Pre-release validation: the residue, with an owner and a pass criterion

**This is the checklist form of §2.3.** *It covers U1–U14. U15 and U16, restored on 2026-09-16, are deliberately left without a V-row so that the gap is visible rather than implied; see §10.1.* Nothing here can be done from this repository. Each item
names who must run it and what "pass" concretely looks like. Results must be reported
**de-identified** — counts and pass/fail only, no readings, no account identifiers, no logs
containing credentials (organisation policy: user-submitted CGM data is sensitive health data).

| # | Item | Who | What pass looks like | Blocking? |
| --- | --- | --- | --- | --- |
| V1 | **(U1) Capture one real CareLink response and record whether `sgs[].datetime`, `markers[].dateTime` and `sMedicalDeviceTime` carry a zone designator, and whether `lastConduitDateTime` is present with a real offset.** Redact everything else. | A maintainer with a real CareLink account, in **at least two countries, at least one not on UTC, at least one east of UTC**. | A recorded yes/no for each field. **If any timestamp field is zone-less, R2 is ACTIVE** and V2 becomes blocking. | **YES — nothing else in §8 can be interpreted until this is known.** |
| V2 | If V1 says zone-less: fix `reassign_zone()`'s fallback upstream so Connect and the legacy path agree on the instant, and pin the fix forward into every train. Add a non-UTC case to `nightscout-connect/test/minimed-data.test.js` that **fails before the fix**. | Connector maintainer. | The new test is red at the parent commit and green after. (A test that has never failed is not evidence.) | YES if V1 is zone-less |
| V3 | **(U3) Determine whether the BLE periodic endpoint ever returns a payload without `markers`.** | Maintainer with a CareLink account; or accept the cheap fix instead. | Either evidence that `markers` is always present, **or** a one-line guard in `transformPayload` plus a regression test with a `markers`-absent payload. **The guard is cheaper than the answer and should be taken regardless.** | **YES** — the failure kills the Nightscout process, on every pin including `v0.0.14`. |
| V4 | **(U2) Confirm a real CareLink login still succeeds for the retired package**, patient role, EU and US. | Maintainer, one live account per region. | A recorded result either way. **A negative result strengthens the retirement; a positive result means the "short window" argument needs a different basis.** Either outcome is publishable; no outcome is not. | No — but the notice's wording depends on it |
| V5 | **(U7) Census of deployed `BRIDGE_SERVER` values.** | Foundation / hosted-platform operators; or a community question. | A count of sites whose `BRIDGE_SERVER` is set to something other than blank, `EU`, or a dotted hostname. **This number should set the length of the notice**, and it is the single highest-value thing that can be done before deciding. | No — but it is the cheapest item with the largest effect |
| V6 | **(U9) Determine whether a care-partner request with `patientId: undefined` fails loudly or returns empty data.** | Maintainer with a follower account. | Decides whether the notice says the legacy follower path is "broken" or "silently returns nothing". | No |
| V7 | **(U10) Determine whether CareLink returns history or only a current snapshot.** | Maintainer with a CareLink account. | Settles §3.2's MiniMed row, which currently ships as read-derived and must not be published as fact until it is settled. | **YES for publication of §3.2** |
| V8 | **(U4, U5, U6, U8, U11, U13) Live soak.** ≥14 consecutive days per vendor on a non-production instance with a separate database: ≥2 pump families and ≥2 countries for CareLink; ≥1 follower topology per vendor; ≥2 sensor changes per vendor; the vendor's own app confirmed still working concurrently. | **A named maintainer who is not the branch author.** | Zero silent gaps; zero clock-skew events; **the stale-data alarm demonstrably fires when ingestion is stopped deliberately**; no vendor auth anomaly; no duplicate growth beyond the legacy baseline; IOB not inflated where a second uploader is present. | **YES** |
| V9 | **(U12) Record which pump models and regions were actually exercised**, and state plainly in the notice that coverage outside that set is unknown. | Whoever runs V8. | An explicit list. Neither implementation branches on model beyond `GUARDIAN`, so this cannot be enumerated from source at all. | No — but silence here is a claim, and a false one |
| V10 | **(U14) Form a view on the current state of the legacy *Dexcom* path against live Dexcom.** | Maintainer with a Dexcom Share account. | A recorded statement. **If legacy Dexcom still works fine, every "worse" item in §2.2 is a live regression risk; if it is already broken, most are moot.** There is no statement on the record either way. | No — but it changes how §2.2 should be read |

**V1, V3 and V8 are the three that would change the release if they came back badly.** V5 is the one
that costs almost nothing and improves the notice the most.

---

## 7. Staged rollout, and the observable that distinguishes working from quietly not working

### 7.1 Silence is the failure mode

A Nightscout site with no ingestion looks exactly like a Nightscout site whose user is asleep. The
distinguishing observable must be **positive and continuous**, and evaluated **per deployment**.

**Primary signal — arrival rate.** New `entries` rows per deployment over a rolling 30 minutes,
against that deployment's own 7-day baseline. A working feed produces roughly 12 readings/hour, so
about 6 per 30 minutes. **"Quietly not working" = zero new rows for 30 minutes on a deployment whose
own baseline is ≥6 per 30 minutes, while the process is up and answering HTTP.** Thirty minutes is
long enough to absorb a sensor warm-up and short enough that Connect's ~48 h backfill still recovers
the gap.

**Second signal, and R2 makes it mandatory — newest-reading clock skew.** `max(entries.sysTime) −
now` per deployment. Healthy sits within a few minutes of zero. **A whole number of hours away from
now is R2, and it is a stop signal, not a diagnostic**, because arrival rate alone looks perfectly
healthy while every reading is filed at the wrong time.

**Third signal — sentinel zeros.** Count of `entries` with `sgv === 0` in the last 24 hours. Should
be zero. A non-zero count on a MiniMed deployment means the connector pin predates the sentinel
filter (R1), and while such a reading is newest the high/low alarm evaluation is skipped.

| Failure mode | HTTP | Caught by an uptime monitor? |
| --- | --- | --- |
| Boot error (missing `CONNECT_COUNTRY_CODE`, conflicting sources) | **500** | **Yes** — loud and immediate |
| Connect running but not ingesting (vendor auth rejected, account locked, session not recovered per R5) | 200, site fully normal | **No** |
| Connect ingesting at the **wrong time** (R2) | 200, site fully normal, graph full of data | **No** — and the arrival-rate check also passes |
| Connect ingesting at the wrong time **and then stopping**, pump east of the server clock | 200, site fully normal | **No** — and the deployment's **own stale-data alarm is suppressed**, so the operator is not told either |
| Connector dark for 74.6 h after a sustained vendor problem (R6, pinned connector) | 200, site fully normal | **No** |

The fourth row is why clock skew is a stop signal: a forward-shifted trace removes the last local
detector an operator has.

### 7.2 What a single self-hoster actually has

The signals above presuppose visibility across deployments. **A person running Nightscout for their
own or a family member's diabetes has exactly one built-in continuous detector, and it is
`timeago`** — `ALARM_TIMEAGO_WARN` and `ALARM_TIMEAGO_URGENT`, both on by default. R2 turns it off
for the affected class of MiniMed user. Until V1/V2 are settled, **a MiniMed operator on Connect
whose pump is east of the server clock may have no local silent-failure detector at all.**

Single-tenant deployments are and remain first-class, so the migration's real observability
requirement for them is the pair already in the runbook at §4.4 item 5: **both alarm settings on,
and the newest reading not in the future.**

**Further signals:** `device` value distribution — the `nightscout-connect` fraction should rise
monotonically and the legacy fraction fall to zero; a **mixed** deployment means both paths are
running (R3) and needs immediate investigation. Also: boot-error rate, `devicestatus` growth rate
against the pre-migration baseline, and Connect's authentication-failure rate, which is what catches
a vendor blocking the client (U4, U8).

### 7.3 Stages

The decision is "little or no waiting period", so these stages are compressed relative to the
previous revision's proposal. What is **not** compressed is stage 1: maintainer validation on real
accounts is the only thing that can settle §6, and recruiting volunteers before it transfers
vendor-integration risk onto users.

| Stage | Who | Duration | Continue if | **Stop if** |
| --- | --- | --- | --- | --- |
| **0. Deprecation release** | Everyone | Set by V5, not by a calendar | — | — |
| **1. Maintainer dogfood** | ≥2 maintainers, real accounts, non-production instances, both vendors, **≥1 account not on UTC and ≥1 east of the server clock** (so R2 and the alarm suppression would be visible) | ≥14 days | V8's pass criteria met; every §8 item green | Any silent gap; any clock skew; **any failure of the stale-data alarm to fire on a deliberately stopped feed**; any vendor auth anomaly |
| **2. Invited volunteers** | 10–20 people who explicitly opt in, understand they are testing an ingestion path, keep their vendor's own app running, and have **rehearsed** a rollback | ≥21 days | ≤1 silent-gap event, root-caused and fixed; nobody loses data they could not recover | ≥2 silent-gap events; **any** clock-skew event; any unrecoverable loss; **any report from a caregiver that overnight data stopped** |
| **3. General release** | Everyone | ≥30 days soak | Community reports stable | Any cluster of ingestion reports |

**Stage 2's stop condition is deliberately asymmetric.** One report from a parent whose overnight
data stopped outweighs nineteen clean reports. That is not statistics; it is who bears the harm.

**Who decides:** the Foundation's maintainer group, and each stage transition needs a named
maintainer who is **not** the branch author and who has read §6 and §8. *This is a governance
recommendation, not a decision this document can make.*

### 7.4 One thing the compressed schedule does not change

R1 and R6 are defects in the connector **that ship to operators today**, on a version `dev` already
steers people toward with a boot-time deprecation warning. They are not retirement risks; they are
current-release risks that the retirement makes more visible. `bf/connect-pin` fixes both by moving
the pin to `v0.0.14`, it is one file and one line, and **it should land before the deprecation
release, independent of the parcel schedule.**

---

## 8. What must be true before the deletion ships

Every box is unchecked: **none of this has been verified as of 2026-09-16.** Commands are given
where one exists; where none exists, that is itself the item.

### 8.1 Connector pin (do this first — it is one line)

- [ ] `bf/connect-pin` has landed, moving the pin to the `v0.0.14` tarball. This carries the BF-34
      backoff fix (256 ms first retry **and** the 74.6 h ceiling), the CareLink sentinel filter, and
      the `devicestatus.created_at` fix.
      ```sh
      git -C externals/cgm-remote-monitor-official show origin/dev:package.json | grep nightscout-connect
      # must name v0.0.14, not 234d47c8
      git -C externals/nightscout-connect grep -c "sg !== 0" v0.0.14 -- lib/sources/minimedcarelink/index.js
      # must be 1
      ```
- [ ] `package-lock.json` regenerated **after** the connector tag is published — never with a
      locally invented integrity hash.
- [ ] No connector pin anywhere in the release set predates `c1cce2a`.
      ```sh
      git -C externals/nightscout-connect merge-base --is-ancestor c1cce2a <pinned-sha> && echo OK
      ```

### 8.2 The MiniMed timestamp question (blocking — §6 V1/V2)

- [ ] V1 answered from a real account. **Nothing below can be interpreted until it is.**
- [ ] If zone-less: the upstream fix is in, pinned forward, with a test that failed first.
- [ ] A regression test asserts that a deployment whose newest reading is **future-dated** is
      flagged rather than silently accepted.
      ```sh
      git -C externals/cgm-remote-monitor-official show origin/dev:lib/plugins/timeago.js | grep -n "mills >= sbx.time"
      # today: present, with no guard — a future-dated reading returns before any alarm is requested
      ```
- [ ] Guidance published for operators **already** on `CONNECT_SOURCE=minimedcarelink` today: how to
      recognise a time-shifted trace, that their stale-data alarm may not have been firing, and what
      to do about already-stored rows.

### 8.3 The `markers` crash (blocking — §6 V3)

- [ ] `transformPayload` guards `data.markers`, with a regression test whose payload omits the field.
      ```sh
      git -C externals/nightscout-connect grep -n "data.markers" v0.0.14 -- lib/sources/minimedcarelink/index.js
      git -C externals/nightscout-connect grep -c "markers: \[\]" v0.0.14 -- test/
      # every existing occurrence injects the field; the absence has zero coverage
      ```
- [ ] Separately: `cgm-remote-monitor` registers an `uncaughtException` handler, or a decision is
      recorded that it deliberately does not.
      ```sh
      git -C externals/cgm-remote-monitor-official grep -rn "uncaughtException" origin/dev -- lib/ server.js bin/
      # today: returns nothing
      ```

### 8.4 The Dexcom region pass-through (R4)

- [ ] `applyBridgeToConnectCompatibility` no longer forwards a non-hostname `BRIDGE_SERVER` verbatim,
      **or** the release notes carry the warning in §5.1 prominently.
- [ ] Connect's `validate()` rejects a `shareRegion` that is not a known key, instead of producing
      `baseURL = 'https:'` and reporting `ok: true`.
- [ ] `tests/bridge-connect-compat.test.js` covers the region branch. **Today it does not:** two of
      five ablations of that branch left the 4-test suite green (E1 §2, **[R]**). A test suite that
      cannot fail on the branch under discussion is not evidence.
- [ ] `DEXCOM_BRIDGE_USE_LEGACY=1` and a string `"true"` either opt out, or are documented as not
      opting out.

### 8.5 Both-paths-running (R3)

- [ ] Either `setupMMConnect` stands down for Connect on the **deprecation release** (so staging is
      safe for MiniMed as it already is for Dexcom), or the notice tells MiniMed operators
      explicitly not to stage.
      ```sh
      # the stand-down guard is a test of extendedSettings.connect inside the boot stage
      for fn in setupBridge setupMMConnect; do printf '%-16s ' "$fn"; \
        git -C externals/cgm-remote-monitor-official show origin/dev:lib/server/bootevent.js \
        | sed -n "/function $fn/,/^  }/p" | grep -c "extendedSettings.connect"; done
      # today: setupBridge 1, setupMMConnect 0
      ```
      **Do not grep these functions for the bare word `connect`** — it matches `mmconnect` and the
      `nightscout-connect` deprecation string, so `setupMMConnect` scores 4 while having no guard at
      all. An earlier draft of this checklist carried exactly that mistake.

### 8.6 Boot failure is survivable and explicable

- [ ] The `CONNECT_COUNTRY_CODE` boot error **renders**. A `desc`-only boot error must produce a
      readable page, not a crash in the renderer — otherwise the message written for the operator is
      unreachable by that operator.
- [ ] A security reviewer has ruled on whether a stack trace belongs on the 500 boot-error page.
- [ ] No error path prints a credential. Note `augmentSettings` logs
      `'extending extendedSettings with', body.extendedSettings` before anything redacts it, which on
      an `IMPORT_CONFIG` site prints `BRIDGE_PASSWORD` / `CONNECT_SHARE_PASSWORD` in clear text at
      every boot (E1 §5, **[S]**). Not part of the retirement, in the same file as the migration,
      and it should be fixed alongside it.

### 8.7 Live validation (§6)

- [ ] V8 complete, by a named maintainer who is **not** the branch author, results de-identified.
- [ ] V1, V3, V7 answered.
- [ ] V5 (the `BRIDGE_SERVER` census) attempted, and its result recorded even if it is "unknown".

### 8.8 Base, CI and release hygiene

- [ ] Parcels 4 and 5 rebased onto current `dev` and merging cleanly. **Each parcel must take `dev`
      first, or merging it silently reverts the remedial fixes underneath it.**
      ```sh
      git -C externals/cgm-remote-monitor-official merge-tree --write-tree --name-only \
        origin/dev origin/chore/mime-exposure-review
      ```
      **Measured 2026-09-16, `dev` = `a8888f0d` (added during adversarial review; the box stays
      unchecked):** the two parcels are *not* in the same state and the checklist should not treat
      them as one item.
      - **Parcel 5 has already taken `dev`.** `git merge-base --is-ancestor origin/dev
        origin/chore/nightscout-modernization` succeeds; `git rev-list --left-right --count
        origin/dev...origin/chore/nightscout-modernization` is `0 495`. `merge-tree` exits 0 with no
        conflict. **[R]**
      - **Parcel 4 has not.** It is `59 400` against `dev` and `merge-tree` exits 1 with four
        conflicts: `README.md`, `lib/server/bootevent.js`, `package.json`, `package-lock.json`, plus
        a modify/delete on `tests/clock-client.test.js`. **[R]**
      - Since parcel 4 is contained in parcel 5 (re-verified: `merge-base --is-ancestor` succeeds),
        **the merge that is clean today is parcel 5**, and the `bootevent.js` conflict below is a
        parcel-4-only artefact. A reviewer should decide whether parcel 4 needs to take `dev` at all
        given that it never ships alone.
- [ ] The `lib/server/bootevent.js` conflict is resolved by someone who has read §8.5, since that
      file holds both boot stages and the stand-down guard.
- [ ] The **whole** test tree runs, not the local brace lists. CI's `test-ci` is `./tests/*.test.js`
      (159 files); `npm run test:unit` is a 44-file brace list and `test:integration` expands to 89 path
      arguments but only **66 distinct files** (the `api*` and `api3*` patterns overlap; mocha dedupes) — 52
      files match neither local script.
- [ ] Every operator-facing string naming a release version names the **actual** retiring release.
      ```sh
      git -C externals/cgm-remote-monitor-official grep -n "retired in" origin/chore/mime-exposure-review -- lib/ README.md
      ```
- [ ] `package.json` `"version"` is distinct per shipped artifact. (Measured previously: all five
      parcel tips **and** `origin/dev` said `15.0.9`.)

### 8.9 Documentation and rollback

- [ ] §3 and §4 reviewed by someone who runs Nightscout for a family member and is **not** a
      contributor.
- [ ] The rollback path is **rehearsed**, not merely documented: upgrade, break ingestion, roll back,
      confirm data resumes — on Docker, Heroku and Azure.
- [ ] The in-repo operator guide (`docs/runtime-upgrade.md` on parcel 4, which the README links from
      its retirement sections) is reconciled with §3 and §4 of this plan. **Two known gaps today:**
      its README text says a missing country code "prevents the replacement from starting" when it
      actually takes the **whole site** down; and its `BRIDGE_SERVER` sentence documents the `EU` and
      dotted-hostname cases without warning that everything else is forwarded verbatim (R4). **[R]**
- [ ] The Dexcom-and-MiniMed-together case has a documented answer before release, not after the
      first report.
- [ ] Release notes lead with **"check whether you are affected"** and with `CONNECT_COUNTRY_CODE`,
      not with the dependency removals.

---

## 9. What this revision retracts, and two corrections it makes on its own account

### 9.1 Retracted from the previous revision of this file

1. **"Cut 4 introduces the Dexcom migration."** It does not. The migration ships on `dev` and
   `master` today; parcels 4/5 remove the fallback. The alarmed Dexcom framing throughout the
   previous revision is withdrawn.
2. **"The compatibility shims are unvalidated."** The Dexcom shim has a release cycle of production
   exposure and a 4-test suite; the MiniMed shim is reproduced idempotent and reproduced safe on
   half-failure. What is unvalidated is the **region branch** of the Dexcom shim (R4) and everything
   in §6 — a narrower and more actionable claim.
3. **"The retirement's headline risk is that glucose data silently stops."** The instinct survives;
   the mechanism was wrong. The measured silent-stop mechanisms are (a) `BRIDGE_SERVER`
   pass-through producing an unresolvable host while `validate()` reports success, (b) Connect's
   inability to recover a server-invalidated session for up to 24 h, (c) the pinned connector's
   74.6 h ceiling, and (d) a future-dated MiniMed reading disabling the stale-data alarm. **None of
   them is "Connect cannot talk to the vendor."**
4. **"Split the cut, Dexcom first."** Withdrawn as a recommendation: parcel 4 is contained in parcel
   5, so the split is not achievable as a merge, and the decision is made. What survives from the
   argument is that the two vendors are at different maturity and the notice must treat them
   separately — which §5 does.
5. **The instruction to confirm the connector is dormant by finding
   `Skipping disabled nightscout-connect, no source driver spec` in the log.** See §9.2.

### 9.2 Two corrections this revision makes from its own measurements

**C1 — the connector's "not running" log line is not stable across pins, and on two of the three it
does not print at all by default.** Measured on 2026-09-16 with `git show <ref>:index.js`:

| connector version | where it is reached | string | printed by default? |
| --- | --- | --- | --- |
| `v0.0.13` (`origin/master`'s pin) | `index.js:30` | `Skipping disabled nightscout-connect, no source driver spec` | **yes** (`console.log`) |
| `234d47c8` (`origin/dev`'s pin) | `index.js:34` — the first message is at `:30`, the no-source one has moved and been reworded | `Skipping connector without a source` | **no** (`log.debug`) |
| `v0.0.14` (the prepared release) | `index.js:51` | `Skipping disabled connector, no source driver` | **no** (`log.debug`) |

`createLogger` emits `debug` only when `CONNECT_DEBUG` (or `env.debug.logging`) is on. **[R]** The
previous revision recorded the `v0.0.13` string as a correction and generalised it to all pins. An
operator on `dev`'s pin who follows that instruction finds nothing and concludes the connector *is*
running. The early return itself is identical on all three, so the underlying advice — pre-staging
`CONNECT_COUNTRY_CODE` is inert — is unaffected. Corrected in §4.3.

**C2 — future-dating and sentinel zeros silence two *different* alarms, and the previous revision's
§1 read as though one disabled everything.** Verified on `origin/dev`:

- `lib/plugins/timeago.js` returns before requesting any alarm when `lastSGVEntry.mills >= sbx.time`,
  and the browser path computes `sbx.time - mills > threshold`. A **future-dated** reading therefore
  silences the **stale-data** alarm on both paths. **[R]**
- `lib/plugins/simplealarms.js` gates on `lastSGVEntry.mgdl > 39 && sbx.time - lastSGVEntry.mills <
  10 min`. A future-dated reading **passes** that recency test (the difference is negative), so
  high/low evaluation still runs. What stops it is a **sentinel `0`**, which fails `mgdl > 39`. **[R]**

Two mechanisms, two symptoms, two different fixes. §3.3 now states them separately. Conflating them
would have told an operator to look for the wrong thing.

### 9.3 Two corrections to the evidence documents themselves

- **~~E1 and E2 both refer to the connector's CareLink source as `lib/sources/minimedcarelink.js`.~~
  RETRACTED 2026-09-16 during adversarial review — this correction was itself wrong.** Neither
  `docs/60-research/e1-dexcom-path-comparison-2026-09-15.md` nor
  `docs/60-research/e2-medtronic-path-comparison-2026-09-15.md` contains the string
  `lib/sources/minimedcarelink.js`; grepped, both return zero, and E1 does not name a
  `lib/sources/` path for the CareLink source at all. There was no error in E1 or E2 to correct.
  **What survives, and is worth keeping as a navigation note:** the connector's CareLink source is a
  **directory**, `lib/sources/minimedcarelink/index.js`, and the sentinel filter is at
  `.../index.js:720` on `v0.0.14` and `:738` on `c962a13f`, absent at `v0.0.13` and `234d47c8` —
  all four re-verified by `git grep` on 2026-09-16. **[R]** *(If an earlier revision of E1 or E2 did
  spell the path as a file and has since been edited by another session, that is the only reading
  under which the original bullet was ever true; a reviewer who wants to settle it should check the
  history of those two files rather than trust either version of this bullet.)*
- **BF-34's register entry, as quoted in E1, records only the 586×-too-fast retry.** The same
  `{...config, ...defaults}` merge also makes the ceiling 74.6 hours, because `exponent_ceiling`
  caps the exponent rather than the delay. **The dark-window half is the one that stops a person's
  data**, and it is the half that is missing. Reported here as a proposed register amendment; this
  document does not edit the register.

---

## 10. Open questions and reviewer checklist

### 10.1 Open, and who settles them

The vendor-account questions are U1–U16 in §2.3. U1–U14 have owners in §6; **U15 and U16 were restored on 2026-09-16 and do not yet have a §6 owner — a reviewer must assign one or record why neither needs answering.** Beyond those:

1. **How many operators run each legacy path?** Nobody in this programme knows. It changes whether
   R4 affects three people or three hundred. **Foundation**, from hosted-platform or community data.
2. **Do any operators already run `CONNECT_SOURCE=minimedcarelink` today?** If so they are exposed
   to R1 and R2 **now**, and need guidance before the deprecation release rather than after it.
   **Foundation / community.**
3. **Is "little or no waiting period" right?** A judgement with no adoption telemetry behind it. V5
   is the cheapest thing that would inform it. **Foundation.**
4. **Does anything downstream read `carelink_raw`?** The feature is dropped. That needs a community
   question, not a grep.
5. **Are the connector changes the release pins actually merged upstream**, rather than pinned as
   commits from open pull requests? **Not checkable here** (no network). **Whoever prepares the
   release.**

### 10.2 Verify these before relying on anything above

- **R-A.** That `lib/server/bridge-connect-compat.js` and `migrateBridgeToConnect()` are on
  `origin/dev` **and** `origin/master`, and that `mmconnect-connect-compat.js` is on neither. Every
  reframing in §0 and §1 rests on it.
- **R-B. The most important one.** E2 §5's MiniMed timestamp divergence, **including its controls**:
  UTC+0 must show all three implementations agreeing, and a zone-**bearing** payload must invert the
  roles, before the diverging arms are trusted. If this is wrong, §6 V1/V2 fall away and the
  schedule gets easier. If it is right, it is a **current-release** defect, not a retirement one.
- **R-C.** E2 §3c's `markers` crash, through the shipping loop, with the `markers: []` control that
  survives. This is a whole-process kill and should be confirmed independently before §8.3 blocks a
  release on it.
- **R-D.** E1 §1 row 5's legacy `glucose.map` crash and the absence of any `uncaughtException`
  handler. This is the strongest single argument **for** the retirement and it should be as
  well-verified as the arguments against.
- **R-E.** E1 §3's session-rejection asymmetry (legacy recovers next poll; Connect does not for up
  to 24 h). It is the one axis where removing the fallback makes a feed **more** likely to go dark,
  and its real-world severity is entirely U5.
- **R-F.** E1 §2's `BRIDGE_SERVER` table, **including the two green ablations** that prove the
  region branch is untested.
- **R-G.** Every environment-variable name spelled in §4.3, against the shipped code. A wrong
  variable name in an operator runbook causes the exact outage this document exists to prevent.
- **R-H.** §9.2's two corrections, which are mine and were not independently reviewed.
- **R-I. Lay and clinical review of §3 and §4** by someone qualified to judge whether the guidance is
  safe for a non-technical person acting on it while managing diabetes — particularly "pick a good
  time", "keep the old settings 7 days", "roll back first, diagnose later", and the §4.4 clock check.
- **R-J.** That nothing in §3 or §4 constitutes individualised dosing advice. I believe it does not;
  a reviewer should confirm. Note §4.4's IOB paragraph in particular: it tells an operator to check a
  number and to raise a doubt, and deliberately does not tell them what to do about a dose.

---

**Status: DRAFT. Not reviewed. Not approved.** Nothing here has been acted on, pushed, merged, tagged
or published. No branch or worktree was modified, no shipping file was edited, and no network request
was made in preparing it. No BF id was allocated; proposed register entries are returned separately
for a later agent to number.

*Not medical advice. This document describes how glucose data reaches a self-hosted Nightscout site;
it does not describe therapy and contains no dosing guidance. Anyone running Nightscout for their own
or a family member's diabetes should treat a change to how data reaches their site as a change worth
watching closely, and should discuss monitoring and alarm settings with their diabetes care team.
Anyone whose glucose data has stopped arriving should fall back to their CGM's own app and to
fingersticks as their care team has advised, and contact that team if the gap affects their care.*
