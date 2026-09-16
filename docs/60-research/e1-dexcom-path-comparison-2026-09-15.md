# E1 — The Dexcom path: legacy Share bridge vs. nightscout-connect

**DRAFT. Contributor-facing.** Prepared for maintainer review. Nothing in this document has been
run against a real Dexcom account, real credentials, or any vendor endpoint. Every measurement
below comes from the shipping source files driven against synthetic fixtures on this machine.
A qualified reviewer must confirm the vendor-behaviour assumptions marked **UNSETTLEABLE HERE**
before any of this is used to size a deprecation notice.

- Date: 2026-09-15
- Shipping checkout: `externals/cgm-remote-monitor-official`, `origin/dev` = `a8888f0d`
- Connector checkout: `externals/nightscout-connect`, tags `v0.0.12` … `v0.0.14`
- Harnesses: `/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/r1..r9`

Every claim is labelled **[R]** reproduced (a harness was run and produced the number quoted) or
**[S]** read-derived (established by reading source only).

---

## 0. Three corrections to the brief, before anything else

### 0.1 The auto-adoption path is already on `dev`. It is not a parcel-4 change.

The brief places `migrateBridgeToConnect()` and `lib/server/bridge-connect-compat.js` "on the
parcel-4 branch (`chore/mime-exposure-review`) or its constituents". They are on `origin/dev`,
introduced by `a91e8ee4 feat(connect): use nightscout-connect 0.0.13 for bridge compat`. **[R]**
`git ls-tree -r origin/dev` lists both the module and `tests/bridge-connect-compat.test.js`, and
`lib/server/bootevent.js` on `dev` calls it at line 79 and gates the legacy bridge on it at
line 368.

**This changes what the parcel-4 decision is about.** The Dexcom migration is not a thing parcels 4
and 5 would introduce. It is already the default behaviour of current `dev`: any site with
`BRIDGE_USER_NAME`/`BRIDGE_PASSWORD` set is *already* served by nightscout-connect unless it sets
`DEXCOM_BRIDGE_USE_LEGACY=true`. Parcels 4/5 remove the *fallback*, not the default. The
deprecation window that matters therefore began at `a91e8ee4`, not at the parcel-4 merge.

### 0.2 `dev` does not pin nightscout-connect v0.0.13. It pins a commit that is not on the v0.0.13 line.

`package.json` on `dev` pins the tarball for `234d47c85510a77f07b3be0d2c026dd0272715d6`. **[R]**

| relation | result |
| --- | --- |
| `merge-base --is-ancestor 234d47c8 v0.0.13` | **no** |
| `merge-base --is-ancestor v0.0.13 234d47c8` | **no** |
| `merge-base --is-ancestor v0.0.12 234d47c8` | yes |
| `git describe 234d47c8` | `v0.0.12-28-g234d47c` |

The two have diverged: `v0.0.13` is a merge commit (`b394411`) whose parents are all contained in
`234d47c8`'s history, and `234d47c8` carries one commit `v0.0.13` does not. The installed package
reports `"version": "0.0.13"` in its own `package.json`, which is where the belief comes from.

For the Dexcom path specifically this matters in a useful direction: **`lib/sources/dexcomshare.js`
at the pin is byte-identical to `v0.0.14`** (`git diff 234d47c8 v0.0.14 -- lib/sources/dexcomshare.js`
is empty) **[R]**, and differs from the `v0.0.13` tag by 20 lines. So the G7-era `accountId`
normalisation, the `Array.isArray` guard on the glucose response, and the safe logger **are already
shipping on `dev` today**. The tag `v0.0.13` does not contain them.

### 0.3 "Legacy bridge vs. v0.0.13 vs. v0.0.14-with-the-fix" is the wrong three-way split.

`v0.0.14` (`649a7de`) sits directly on top of `c1cce2a`, the BF-34 backoff/jitter fix. So
`bf/connect-pin` — a one-line move of the pin to the `v0.0.14` tarball — *is* the BF-34 fix ship
vehicle. The three things actually worth comparing are:

1. the legacy `share2nightscout-bridge@0.2.12` engine driven by `lib/plugins/bridge.js`;
2. **connect as pinned on `dev` today** (`234d47c8`) — correct Dexcom driver, **broken backoff**;
3. **connect at `v0.0.14`** — same Dexcom driver, fixed backoff.

---

## 1. Behaviour-by-behaviour table

`interval_ms` values are what `lib/sources/dexcomshare.js` asks for (2.5 min in both the frame and
cycle blocks). "pinned" = `234d47c8` as `dev` installs it now.

| # | Behaviour | Legacy bridge (0.2.12) | Connect, pinned on `dev` | Connect v0.0.14 | Who wins |
| --- | --- | --- | --- | --- | --- |
| 1 | Session reuse | **None.** `bridge.js` calls `engine(opts)` fresh on every poll, so `my.sessionID` is always undefined and a full Authenticate+Login pair runs every time. **24 auth + 24 login + 24 glucose per hour** measured **[R]** | 1 auth + 1 login, then session reused for 24 h: **1 + 1 + 14 per hour** **[R]** | same **[R]** | connect, by ~4.5x fewer vendor requests and ~24x fewer authentications |
| 2 | Session rejected mid-poll (HTTP 401 on the glucose read) | Immediately clears `sessionID` and re-authenticates — **but `refresh_token()` resets `failures = 0` on every successful login, so a permanently-rejected session becomes an unbounded auth→login→fetch→401 loop with no delay and no exit.** 2.8 M requests in 3 s against a zero-latency fake; in production it is one triple per network round-trip, forever **[R]** | **Never re-authenticates.** Over 25 simulated hours of permanent 401: `auth=1 login=1 glucose=23`. The frame retries twice, the cycle backs off, the session machine stays `Active` **[R]** | Retries at ≤30 min indefinitely and re-authenticates at the 24 h session expiry (`t=1449 m: auth, login, glucose`) **[R]** | **legacy, on recovery latency; connect, on politeness.** Neither is correct |
| 3 | Time dark after that failure | 0 (but at the cost of item 2's storm) | **up to ~74.6 h.** Pinned `backoff()` merges `{...config, ...defaults}`, so `I = 256 ms`, and `exponent_ceiling` caps the *exponent*: attempt ≥20 → `256 × (2²⁰−1)` = 74.6 h **[R]** | ≤30 min cycle, ≤5 min frame (builder applies `max_interval_ms` of `6 × interval` and `1 × interval`) **[R]** | v0.0.14, decisively |
| 4 | Wrong credentials | 24 auth attempts/hour forever; `maxFailures` is unreachable (see §3); no operator notification beyond stdout **[R]** | 15 auth attempts/hour, then backs off; never gives up; never crashes **[R]** | 8 auth attempts/hour, then backs off **[R]** | connect |
| 5 | Vendor returns a non-array body with status < 400 | **Uncaught `TypeError: glucose.map is not a function`.** `cgm-remote-monitor` registers no `uncaughtException` handler, so this terminates the Nightscout process **[R]** | `transformGlucose` returns `{entries: []}`, the loop continues, 0 entries persisted **[R]** | same **[R]** | **connect, and this is the single strongest point in the maintainer's favour** |
| 6 | Vendor returns `{accountId: "..."}` from Authenticate (G7-era) | `opts.accountId` becomes the whole object, `login_payload` sends `accountId: {…}` — no normalisation **[S]** | Normalised in `authFromCredentials` and again defensively in `sessionFromAuth`; 7 entries persisted in 30 min **[R]** | same **[R]** | connect |
| 7 | Region: how an operator selects one | `BRIDGE_SERVER`. Read from `process.env` **at module load**, frozen into `Defaults.auth/login/LatestGlucose`. `'EU'` (exact case) → `shareous1`; any value containing a `.` → used as the host; **everything else silently falls back to `share2.dexcom.com`** **[R]** | `CONNECT_SHARE_REGION` (`us`\|`ous`) or `CONNECT_SHARE_SERVER`. `_known_servers` has only those two keys **[S]** | same **[S]** | tie on capability, **connect loses on failure mode** — see §2 |
| 8 | Region: what `validate()` rejects | n/a | **Nothing.** `CONNECT_SHARE_REGION=eu` gives `baseURL = "https:"` and `validate()` still returns `ok: true` **[R]** | same **[R]** | legacy, by accident |
| 9 | Entry shape written | `{sgv, date, dateString, trend, direction, device, type}` | identical keys, identical values | identical | — |
| 10 | `device` string | `share2` | `nightscout-connect` | `nightscout-connect` | **the only field that differs** **[R]** |
| 11 | Trend/direction mapping | `DIRECTIONS`/`matchTrend`/`trendToDirection` | character-for-character the same functions, copied | same | identical **[R]** |
| 12 | Units | Neither converts. `sgv` is whatever `d.Value` was (mg/dL from Share) | same | same | identical **[S]** |
| 13 | Timestamps | `date` = `WT` epoch ms; `dateString` = `new Date(wall).toISOString()` | identical | identical | identical **[R]** |
| 14 | Duplicate suppression | Both write through `ctx.entries.create()`, which upserts on `{sysTime, type}` — **`device` is not part of the key** **[S]** | same | same | identical **[S]** |
| 15 | Backfill window after a gap | `minutes = gap`, `maxCount = gap/5 + 1`, **unbounded**: a 30-day gap asks for `maxCount=8641` **[R]** | clamped to 2 days (`maxCount=576`) **[R]** | same **[R]** | connect |
| 16 | Backfill after a restart | Re-fetches `BRIDGE_MINUTES` (default 1440 → `maxCount=289`) regardless of what the database holds, because `mostRecentRecord` is process state **[R]** | Asks the database via the internal output's `gap_for()` **[S]** | same | connect |
| 17 | TLS verification | **`rejectUnauthorized: false` on every request** — Authenticate, Login, LatestGlucose and the Nightscout upload **[R]** | axios defaults; verification on **[S]** | same | connect |
| 18 | Logging of sensitive material | `console.log("accountId: " + …)` and `console.log('Entries', entries)` — **every CGM reading is printed to the server log on every poll** **[R]** | `lib/logging.js` prints only a message plus an HTTP status; never the error object, the request body or the payload **[R]** | same (pinned `logging.js` is byte-identical to v0.0.14's) **[R]** | connect |
| 19 | Poll cadence | `BRIDGE_INTERVAL`, default 156 000 ms in code (README says 150 000 — mismatch), plus an "on-demand" path when data is overdue **[S]** | Fixed 5 min, re-aligned to the last reading + 18 s + up to 18 s of jitter **[S]** | same, plus optional `CONNECT_START_JITTER_MS` / `CONNECT_INTERVAL_JITTER_MS` **[S]** | connect for a hosted pool; no practical difference for one site |
| 20 | Interval sanity check | Accepts 1 000 ms (**1 poll/s = 3 vendor requests/s**), and a non-numeric string defeats the range check entirely — measured 600 polls / 1 800 requests in 10 min for `BRIDGE_INTERVAL=abc` **[R]** | not operator-settable | not operator-settable | connect |

---

## 2. Regional endpoints — the part that most deserves the "my data stopped" label

`applyBridgeToConnectCompatibility` translates `BRIDGE_SERVER` into connect's settings:

```js
if (String(bridgeSettings.server).toUpperCase() === 'EU') {
  env.extendedSettings.connect.shareRegion = 'ous';
} else {
  env.extendedSettings.connect.shareServer = bridgeSettings.server;   // verbatim
}
```

Driving the real shim against the real legacy module, host by host **[R]**:

| `BRIDGE_SERVER` | Legacy reaches | After auto-migration, connect reaches | |
| --- | --- | --- | --- |
| *(unset)* | `share2.dexcom.com` | `share2.dexcom.com` | ok |
| `EU` | `shareous1.dexcom.com` | `shareous1.dexcom.com` | ok |
| `eu` / `Eu` | `share2.dexcom.com` | `shareous1.dexcom.com` | **changes** (arguably a fix) |
| `US` | `share2.dexcom.com` | **`https://US`** | **breaks** |
| `us` | `share2.dexcom.com` | **`https://us`** | **breaks** |
| `EU1` | `share2.dexcom.com` | **`https://EU1`** | **breaks** |
| `shareous1.dexcom.com` | `shareous1.dexcom.com` | `shareous1.dexcom.com` | ok |

Legacy tolerates any junk in `BRIDGE_SERVER` by falling back to the US host. The shim forwards junk
verbatim as a hostname. `BRIDGE_SERVER=US` and `BRIDGE_SERVER=us` are exactly what an operator
writes when they mean "I am in the US" — and the README's wording ("The default blank value is used
to fetch data from Dexcom servers in the US. Set to `EU` …") invites it. Those sites work today and
stop on upgrade, with no error an operator can act on: connect's `validate()` returns `ok: true`.

The same trap exists on the native path: `CONNECT_SHARE_REGION=eu` (lowercase — the obvious
spelling, and the one the shim itself produces for `BRIDGE_SERVER=eu` … as `ous`, not `eu`) yields
`baseURL = "https:"` and `ok: true` **[R]**.

Neither implementation knows about any host beyond `share2.dexcom.com` and `shareous1.dexcom.com`;
both can reach others only by being handed a literal hostname **[S]**.

### Non-vacuity of the existing test (rule 2)

`tests/bridge-connect-compat.test.js` (4 tests) passes on `dev`. Five ablations of the shim **[R]**:

| ablation | suite |
| --- | --- |
| overwrite `shareAccountName` instead of preserving an explicit one | **1 failing** — caught |
| `bridgeUseLegacy()` always returns `false` (opt-out removed) | **1 failing** — caught |
| always return `migrated:false` (legacy bridge never skipped) | **1 failing** — caught |
| drop the case-fold: `bridgeSettings.server === 'EU'` | **4 passing — NOT caught** |
| delete the `shareServer = bridgeSettings.server` pass-through entirely | **4 passing — NOT caught** |

The two green ablations are not mis-scoped: each changes which host a migrated operator's data is
fetched from, which is the failure this whole review is about. **The region branch of the migration
is untested.**

---

## 3. Authentication and session handling, in detail

### Legacy

`lib/plugins/bridge.js` runs a 1-second `setInterval`; when `should_run()` allows, it calls
`engine(opts)` from `share2nightscout-bridge`. `engine()` builds a **fresh closure each time**
(`runs = 0`, `failures = 0`, no `sessionID`), so the first thing every poll does is
`failures++; refresh_token()` → Authenticate → Login → fetch **[R]**.

Consequences, all measured **[R]**:

- ~23–24 full authentications per hour per site, ~550/day. Nothing reuses a session.
- `maxFailures` (default 3) is unreachable on the credentials path: one poll produces at most two
  increments before the closure is discarded. The documented "how many failures before giving up"
  knob does nothing at its default. A wrong password produces an indefinite 24-attempts-per-hour
  retry with no notification.
- On a rejected *session* (401 from LatestGlucose while `sessionID` is set), `my()` →
  `refresh_token()` → on success `failures = 0; my()` → 401 → … . There is no delay term anywhere
  in that cycle. The loop is bounded only by network latency.
- `throw "Too many login failures…"` is a bare string thrown from inside a `request` callback. If
  `BRIDGE_MAX_FAILURES` is set to 1 or 2 it becomes reachable, and there is no `uncaughtException`
  handler in the server **[S]**.

### Connect

`lib/machines/session.js` is an xstate machine: `Inactive → Fresh.Authenticating → Fresh.Authorizing
→ Fresh.Established → Active`. `Active` has `after` transitions at `REFRESH_AFTER_SESSSION_DELAY`
(24 h − 10 min) and `EXPIRE_SESSION_DELAY` (24 h). `dexcomshare.js` leaves `refresh:` commented
out, so the refresh tick resolves to `NO_REFRESH` and only the 24 h expiry actually moves the
machine **[S]**.

The fetch machine (`lib/machines/fetch.js`) sends `SESSION_REQUIRED` on every cycle; in `Active` the
session machine answers `SESSION_RESOLVED` with the cached session, and in `Expired` the root
handler targets `Fresh`, which re-authenticates.

**The defect:** when `dataFromSesssion` rejects — including a 401 that means "this session is
dead" — the fetch machine goes to `Error`, emits `FRAME_ERROR`, retries twice, and gives up. It
never emits anything the session machine listens to. The session stays `Active` with a dead token
until the 24 h expiry. Reproduced: 25 simulated hours of permanent 401 on the pinned connect →
`auth=1 login=1 glucose=23`; on v0.0.14 the first re-authentication lands at t=1449 min **[R]**.

**On the specific failure "Dexcom invalidated my session", the legacy bridge recovers in one poll
and connect recovers in up to 24 hours (pinned: effectively not at all, because the 74-hour cycle
ceiling arrives first).** This is the one axis on which the maintainer's understanding is
straightforwardly wrong, and it is not a small one: sessions being invalidated server-side is the
ordinary way Dexcom Share ends a session.

---

## 4. Retry and backoff — the three-way comparison

Consecutive-failure ladder for the Dexcom source (which asks for `interval_ms = 150 000`), jitter
suppressed for legibility **[R]**:

| attempt | pinned `234d47c8` (cycle & frame) | v0.0.14 cycle (cap 30 min) | v0.0.14 frame (cap 5 min) |
| --- | --- | --- | --- |
| 1 | **256 ms** | 2.5 min | 2.5 min |
| 2 | 768 ms | 7.5 min | 5.0 min |
| 4 | 3.8 s | 30.0 min | 5.0 min |
| 8 | 1.1 min | 30.0 min | 5.0 min |
| 12 | 17.5 min | 30.0 min | 5.0 min |
| ≥20 | **74.6 h** | 30.0 min | 5.0 min |

BF-34 confirmed as stated in the brief: pinned `backoff()` does `{...config, ...defaults}`, so the
caller's 150 000 ms becomes 256 ms — 586x faster at attempt 1 **[R]**. What the brief does not say,
and what the register should, is that the *same* merge order also makes the ceiling 74.6 h
(`256 × (2²⁰−1)`), so during a sustained vendor problem the pinned connector first hammers, then
goes dark for three days. Both halves ship on `dev` today.

Legacy has no backoff term at all: the retry interval is the constant poll interval, forever **[R]**.

---

## 5. The auto-adoption path, exercised

`lib/server/bootevent.js` → `migrateBridgeToConnect()` → `applyBridgeToConnectCompatibility(env)`,
in the `setupConnect` boot step, immediately before `setupBridge`.

- **Trigger:** boot, unconditionally. It acts if `env.extendedSettings.bridge.userName` *and*
  `.password` are both set. `extendedSettings.bridge` only exists when `bridge` is in `ENABLE` **[S]**.
- **Reads:** `extendedSettings.bridge.{userName,password,server,useLegacy,dexcomBridgeUseLegacy}`,
  and `process.env.{DEXCOM_BRIDGE_USE_LEGACY, CUSTOMCONNSTR_DEXCOM_BRIDGE_USE_LEGACY}`.
- **Writes:** only `env.extendedSettings.connect` **in memory**. Nothing is written to disk or to
  the database; it is re-derived on every boot **[S]**.
- **Existing settings:** every field is guarded with `||`, so an explicitly-set connect value wins.
- **Idempotent on the settings object:** running it twice leaves `connect` byte-identical **[R]**.
  It is *not* idempotent on the operator-facing side: the second run still returns `migrated: true`,
  so the deprecation line prints again.
- **Told to the operator:** one `console.log("DEPRECATION WARNING", "BRIDGE_* Dexcom settings are
  being served by nightscout-connect. Set DEXCOM_BRIDGE_USE_LEGACY=true to use
  share2nightscout-bridge.")`, plus a second line from `setupBridge` explaining the skip. Nothing in
  the web UI, nothing persisted, nothing an operator who does not read boot logs will ever see **[S]**.

### Breaking it (rule 2) — 14 synthetic states **[R]**

| state | result | verdict |
| --- | --- | --- |
| bridge only | `migrated:true`, connect gets both credentials, legacy skipped | intended |
| run twice | settings identical; still reports `migrated:true` | ok / cosmetic |
| **connect has `shareAccountName: acct-B`, no password; bridge has `acct-A`/`pw-A`** | connect ends up **`acct-B` + `pw-A`** — a credential pair assembled from two different accounts — and the legacy bridge is skipped | **defect** |
| connect fully configured for `acct-B`; bridge configured for `acct-A` | connect keeps `acct-B`; legacy bridge **skipped**, so `acct-A`'s feed silently stops | **defect** |
| connect source is `librelinkup` + bridge set | `migrated:false`, legacy bridge still runs | correct |
| bridge username set, password missing | `migrated:false`, no connect created, legacy bridge runs (and `lib/plugins/bridge.js` also declines) | correct |
| `BRIDGE_USE_LEGACY=true` / `on` (env.js coerces to boolean `true`) | opt-out honoured | correct |
| `DEXCOM_BRIDGE_USE_LEGACY=true` / `TRUE` | opt-out honoured | correct |
| **`DEXCOM_BRIDGE_USE_LEGACY=1`** | **opt-out ignored**, migration proceeds | **defect (papercut)** |
| **`useLegacy` is the string `"true"`** — the shim tests `=== true` **[R]**. `env.js` coerces `BRIDGE_USE_LEGACY=true` to a boolean, but `IMPORT_CONFIG` `deepMerge`s `body.extendedSettings` into `env.extendedSettings` with no coercion at all **[S]**, so that delivery route yields the string | **opt-out ignored** | **defect (papercut)** |
| `bridge.server` numeric (env.js coerces numeric strings) | `shareServer: 1` → `https://1` | defect, same class as §2 |
| `bridge.server` null | ignored, US default | correct |

### Adjacent observation, outside the Dexcom path

`augmentSettings` logs `console.log('extending extendedSettings with', body.extendedSettings)`
before anything redacts it **[S]**. On a site using `IMPORT_CONFIG`, that prints
`BRIDGE_PASSWORD`/`CONNECT_SHARE_PASSWORD` to the server log in clear text at every boot. Not part
of the retirement decision, but it is in the same file as the migration and should be fixed
alongside it.

### What the migration silently drops **[S]**

`BRIDGE_INTERVAL`, `BRIDGE_MINUTES`, `BRIDGE_MAX_COUNT`, `BRIDGE_FIRST_FETCH_COUNT` and
`BRIDGE_MAX_FAILURES` are not translated and connect has no equivalent. Connect's cadence is fixed
at 5 minutes, aligned to the last reading. For most sites this is better than what they configured;
for a site that deliberately set a long interval it is a change they did not ask for and are not
told about. "Nothing is lost" is true of *data* and not true of *settings*.

---

## 6. What gets better, what gets worse, what is unknowable here

### Better (measured on this machine)

1. **Process survival on a malformed vendor response.** Legacy dies with an uncaught
   `TypeError: glucose.map is not a function`; connect returns an empty batch and keeps polling. This
   is the strongest single item and it is a *whole-server* outage, not just a dark CGM feed. **[R]**
2. **Vendor load.** 72 requests/hour → 16, and 24 authentications/hour → ~1 per day. **[R]**
3. **No unbounded request storm.** Legacy's session-rejection loop has no delay term at all. **[R]**
4. **TLS verification is on.** Legacy sets `rejectUnauthorized: false` on all four of its request
   types, including the Nightscout upload. **[R]**
5. **CGM readings stop being printed to the server log** on every poll. **[R]**
6. **G7-era `{accountId: …}` Authenticate responses are handled**, on `dev` today. **[R]**
7. **Backfill is bounded** (2 days, from the database) rather than unbounded and derived from
   process-local state. **[R]**
8. **Entry records are identical except `device`,** and the `{sysTime, type}` upsert key means the
   cutover does not duplicate history. **[R]**

### Worse

1. **A server-invalidated session is not recovered for up to 24 hours** (pinned: effectively never,
   because the 74.6 h cycle ceiling arrives first). Legacy recovers on the next poll. **[R]**
2. **The pinned connector's backoff is broken in both directions** — 256 ms first retry, 74.6 h
   ceiling. Shipping on `dev` now. Fixed by `bf/connect-pin` (→ v0.0.14). **[R]**
3. **`BRIDGE_SERVER` values that legacy tolerated become unresolvable hosts** (`US`, `us`, `EU1`, any
   non-dotted non-`EU` string), with `validate()` reporting success. **[R]**
4. **`CONNECT_SHARE_REGION` accepts any string** and silently produces `baseURL = "https:"`. **[R]**
5. **A half-configured connect block gets completed from the bridge block**, producing a
   cross-account username/password pair, and the legacy bridge is skipped anyway. **[R]**
6. **An operator running both** (bridge on account A, connect on account B) loses account A at
   upgrade, silently. **[R]**
7. **`DEXCOM_BRIDGE_USE_LEGACY=1` and `useLegacy: "true"` do not opt out.** **[R]**
8. `BRIDGE_*` tuning settings are dropped without notice. **[S]**
9. **The `device` string changes from `share2` to `nightscout-connect`** at the cutover, and any
   re-fetched overlap window rewrites the label on records already stored. Anything filtering or
   grouping history by device sees a discontinuity. **[R]**

### Unknowable here — this list sizes the deprecation notice

1. **Whether Dexcom Share throttles, rate-limits or locks accounts under legacy's ~550
   authentications/day, and whether connect's one-per-day is what makes access "more consistent".**
   This is the most likely mechanism behind the maintainer's belief and it cannot be confirmed
   without a real account. If it is right, the case for retirement is stronger than anything in §6.
2. **The real 401 semantics of `ReadPublisherLatestGlucoseValues`.** §3's conclusion — that connect
   cannot recover a rejected session for 24 hours — is only as important as the frequency with which
   Dexcom invalidates sessions server-side. Unmeasurable here; decisive for the deprecation window.
3. **Whether Dexcom's actual session lifetime is longer or shorter than the hard-coded 24 hours.**
4. **Whether Share still returns 200 with a JSON error object** (the shape that kills the legacy
   process) and how often.
5. **Whether `maxCount` above 288 is rejected, clamped or errors.** Neither implementation clamps;
   legacy can ask for 8 641.
6. **Whether any operator is actually on a non-`EU`, non-dotted `BRIDGE_SERVER`.** §2's breakage is
   certain in mechanism and unknown in population. A one-line census of the deployed config values
   would settle it and is the single highest-value thing that could be done before deciding.
7. **Whether the G7 `accountId` object is the only new response shape**, or whether Login and
   LatestGlucose have also changed.
8. **The current state of the legacy path against live Dexcom.** The maintainer's "the old medtronic
   does not work" is a statement about MiniMed. No equivalent statement about Dexcom is on the
   record, and nothing here can produce one.

---

## 7. Verdict on the maintainer's sentence

> "even for Dexcom, nightscout-connect has some adjustments that allow more consistent access, from
> what I understand."

**Confirmed, and the hedge was warranted.** The adjustments are real, they are already the default
on `dev`, and they are larger than "some": a crash-on-bad-response becomes a no-op, a 550/day
authentication rate becomes 1/day, an unbounded retry loop becomes a bounded one, TLS verification
comes back on, and CGM values stop appearing in logs.

**But it is partly right for the wrong reason,** and the correction matters:

- The *code* improvement is not what the retirement decision turns on, because the code is already
  in use. What parcels 4/5 remove is the **fallback**, and the fallback is the only thing standing
  between the seven "worse" items above and an operator whose data stops.
- Connect is **not** uniformly more consistent. On a server-invalidated session it is
  categorically worse than the thing it replaces, and on the currently pinned commit it can go dark
  for three days on any sustained vendor problem.
- "Nothing is lost" is true of stored glucose history (identical records, same upsert key) and false
  of settings and of several legacy-tolerated configurations.

**Recommended sequencing, for maintainer decision:**

1. Land `bf/connect-pin` (pin → `v0.0.14`) **before** anything about parcel 4 is decided. It is one
   line, it carries BF-34, and without it the connector that is already the default has a 74-hour
   dark ceiling.
2. Fix the region pass-through and add the two missing tests before the fallback is removed; that is
   the only item here with a plausible silent-data-loss population.
3. Give the session machine a path from a rejected fetch back to re-authentication. Until that
   exists, removing the legacy fallback removes the only implementation that recovers from the
   ordinary case.
4. A deprecation notice is needed for the residues in §6, not for the code quality of the driver.
   Its length should be set by item 6 of "unknowable" — a config census — not by a waiting period.

---

*Not medical advice. This document is contributor-facing engineering analysis of data-ingestion
software; it does not describe therapy and contains no dosing guidance. Anyone whose glucose data
stops arriving should contact their care team about how to monitor in the meantime.*
