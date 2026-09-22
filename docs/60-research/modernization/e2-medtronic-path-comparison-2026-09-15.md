# E2 — the MiniMed / CareLink path: does the old one really not work?

> **Snapshot — research as of 2026-09-15, measured against `origin/dev a8888f0d`. Status: current — BF-41, BF-44 and BF-45 are open; nothing here is released (`origin/master` = 15.0.8, still pinning connector v0.0.13). Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md).**
> **[Correction 2026-09-22: the maintainer states (2026-09-21, operational knowledge, not measured here) that mmconnect / minimed-connect-to-nightscout has been broken for some time, and that legacy Dexcom Share is intended to map to nightscout-connect. The "cut 4 deletes two working ingestion paths" premise must carry that caveat; BF-44/BF-45 were graded assuming mmconnect is live and have not been re-graded.]**

**Status: DRAFT. Contributor-facing.** Prepared for maintainer review; nothing here is a
release decision. Every claim is labelled **reproduced** (executed on this machine) or
**read-derived** (read from source). No CareLink account, no credential, no vendor endpoint was
used — every network-shaped experiment ran against a stub adapter that rejects before any socket
is opened.

Refs pinned for this study:
`cgm-remote-monitor` `origin/dev` = `a8888f0d`; `origin/master`; `origin/chore/mime-exposure-review`
(parcel 4); `origin/chore/nightscout-modernization` (parcel 5).
`nightscout-connect` `v0.0.13` (`b394411`), `234d47c8` (dev's pin), `c962a13f` (parcel 4's pin),
`b77e5bb` (parcel 5's pin), `v0.0.14` (`649a7de`).

Harnesses: `/tmp/claude-1000/-home-bewest-src-rag-nightscout-ecosystem-alignment/c0ce5365-48f5-4392-a1ae-c72d32aabe91/scratchpad/e2/`
(`compare.js`, `chain.js`, `loop.js`, `item5.js`, `us-branch.js`, `sentinel.js`). They `require()`
the shipping modules by absolute path; nothing was modified in either product repository.

---

## 0. Three findings to read first

**C1. There is no MiniMed auto-adoption path on any released or `dev` code.**
`lib/server/mmconnect-connect-compat.js` does **not** exist on
`origin/dev` or `origin/master`. It exists only on parcel 4 (`origin/chore/mime-exposure-review`)
and therefore parcel 5. On `dev` the only compatibility shim is
`lib/server/bridge-connect-compat.js`, which is **Dexcom-only**: it refuses to act unless
`extendedSettings.bridge` carries a username and password, and it only ever writes
`connect.source = 'dexcomshare'`. **Reproduced**: called with an `mmconnect`-only environment it
returns `{"migrated":false,"legacy":false}` and leaves `extendedSettings` untouched.

So the maintainer's phrase *"includes an auto adoption/migration path"* is **true of the release
being prepared and false of everything shipped so far**. Today a MiniMed operator who wants
Connect must rewrite their configuration by hand, and nothing in the product tells them to.

**C2. On the currently released connector pin, Connect's MiniMed source is measurably *worse*
than the retired package in two specific ways.** `origin/master` pins `v0.0.13` and `origin/dev`
pins `234d47c8`. Neither has the `sg !== 0 && kind === 'SG'` filter that the retired package has
had since 2015, and neither stamps `devicestatus.created_at` from the measurement time. Both are
fixed at `c962a13f` — i.e. in the parcels — and at `v0.0.14`. The sentence *"the
nightscout-connect module works better regardless"* is therefore correct **for the code the
deprecation release would ship** and incorrect **for the code an operator would land on if they
migrated today on the advice of the existing deprecation warnings**, which `dev` already prints on
every boot.

**C3. The retirement makes the timezone hazard worse, not better, for one large class of user.**
This is item 4 and the most safety-relevant result in the study. Details in §5.

---

## 1. In what sense does the old one "not work"?

The brief offers five candidate mechanisms. Taking them one at a time, from source and from
execution.

### 1a. "It targets a CareLink API version that no longer exists" — PARTLY, with direct evidence of vendor churn

`minimed-connect-to-nightscout@1.5.8` carries a hard-coded downgrade in `carelink.js`:

```js
// HOTFIX
// https://github.com/nightscout/minimed-connect-to-nightscout/issues/39
dataRetrievalUrl = dataRetrievalUrl.replace('/carepartner/v6/display/message',
                                            '/carepartner/v5/display/message');
```

The vendor advertises a v6 endpoint through its own country-settings response and the package
rewrites it back to v5. That is documented evidence that the vendor moved and the package pinned
itself to the older shape; it is **not** evidence that v5 has since been withdrawn. **Read-derived.**

Separately, `nightscout-connect` implements an endpoint family the retired package has no
knowledge of at all — `/patient/m2m/links/patients`, `/patient/m2m/connect/data/gc/patients/…`,
`/patient/configuration/system/personal.cp.m2m.enabled`, `/patient/monitor/data`,
`/patient/dataUpload/recentUploads` — and selects between M2M and the BLE periodic endpoint on
`deviceFamily`. The retired package has only `/patient/connect/data` and the BLE carepartner POST.
That asymmetry is consistent with the vendor having introduced a newer data plane that the retired
package never followed. **Read-derived. Which endpoints a live account can still reach cannot be
settled here.**

### 1b. "Its authentication flow was changed by the vendor" — CONFIRMED as a code fact, in a way that leaves the US path dead

`carelink.js` contains two complete login implementations. The US one (`j_security_check` →
`login.do` → `_WL_AUTHCOOKIE_JSESSIONID`, then `ConnectViewerServlet` for data) is **unreachable**:

```js
async function checkLogin (relogin = false) {
    if (1 || CARELINK_EU) { ... EU SSO ... } else { ... US cookie method ... }
}
var carelinkJsonUrlNow = async function () {
    return (1 || CARELINK_EU ? CARELINKEU_JSON_BASE_URL : CARELINK_JSON_BASE_URL) + Date.now();
};
```

`1 || x` is always truthy. **Reproduced** (`us-branch.js`, stub adapter, no network): with
`MMCONNECT_SERVER` unset — i.e. a US operator following the README — the one request the package
attempts is

```
GET https://carelink.minimed.com/patient/sso/login?country=gb&lang=en
```

and the strings `j_security_check`, `login.do` and `ConnectViewerServlet` are never reached. With
`MMCONNECT_SERVER=EU` the host becomes `carelink.minimed.eu`, same path.

Two things follow. First, someone deliberately forced every operator onto the SSO flow, which is
what you do when the vendor retires the old one — so this is *evidence that the vendor changed
authentication*, though the commit rationale is not in this repository. Second, the country code
defaults to `gb` for everyone. `MMCONNECT_COUNTRYCODE` overrides it (**reproduced**:
`?country=us&lang=en`), but **the README documents only `MMCONNECT_SERVER`** — `MMCONNECT_SERVERNAME`,
`MMCONNECT_COUNTRYCODE` and `MMCONNECT_LANGCODE` are read straight from `process.env` inside the
dependency and appear nowhere an operator can find them.

The SSO flow itself is five steps of HTML scraping: `doLoginEu1`…`doLoginEu5` pull the form action,
`sessionID` and `sessionData` out of the response body with regular expressions such as
`/(<form action=")(.*)" method="POST"/gm`. Any change to the vendor's login markup breaks it. This
is the single most plausible mechanism for "it does not work", and it is **structurally fragile by
construction, which is not the same as currently broken.** Note that `nightscout-connect` scrapes
the *same* markup with the *same* regular expressions, so it inherits the fragility.

### 1c. "It depends on an abandoned package" — CONFIRMED, but this is not the breakage mechanism

`minimed-connect-to-nightscout@1.5.8` declares `request@^2.88.0` (deprecated since 2020, no
patched release for GHSA-p8p7-x288-28g6), `axios@^0.26.0` (0.x, superseded), `axios-cookiejar-support@^1.0.0`
(the pre-v2 `default(instance)` API) and `engines.node >= 12`. `request` is only reached by the
package's *standalone* Nightscout uploader (`nightscout.js`, driven by `run.js`); the Nightscout
plugin uses `carelink.Client` plus `transform`/`filter` and writes through Nightscout's own storage
adapters. Parcel 4's own review document says exactly this and adds: *"CareLink uses Axios and needs
its own TLS, authentication and redirect review; the request finding is not that review."*
**Read-derived**, and consistent with `lib/plugins/mmconnect.js`, which never touches
`connect.nightscout`.

So the dependency rot is real and is a good reason to retire the package. It is **not** a reason
the CareLink feed would stop.

### 1d. "It is broken only for some regions or some pump models" — ONE CONCRETE, TOTAL BREAK FOUND

**Care-partner (follower) accounts cannot work through Nightscout at all.** `carelink.js` handles
`CARE_PARTNER` / `CARE_PARTNER_OUS` roles by POSTing

```js
var body = { username: options.username, role: "carepartner", patientId: options.patientId };
```

`options.patientId` comes from `carelink.Client(options)`. The standalone CLI supplies it from
`CARELINK_PATIENT` (`run.js`). **The Nightscout plugin never does.** **Reproduced**:
`require('lib/plugins/mmconnect').getOptions(env)` returns exactly
`{username, password, sgvLimit, interval, maxRetryDuration, verbose, storeRawData}` — no
`patientId`, and no `server`, `countrycode`, `lang` or `patientId` key exists in `getOptions` on
`origin/dev`. A care-partner therefore sends `patientId: undefined`.

This is the strongest "does not work" mechanism established from source, it is total rather than
degraded, and it hits the commonest CareLink usage pattern — a parent following a child. Whether
the vendor rejects such a request or silently returns the caller's own (empty) data cannot be
settled without an account.

`nightscout-connect` plumbs this properly: `carelinkPatientUsername`, with a fall back to
`account.patient_list[0].username` fetched from `/patient/m2m/links/patients`. **Clear gain.**

### 1e. "It works but poorly" — CONFIRMED in error recovery

```js
let maxRetry = 1; // No retry
```

`retryDurationOnAttempt` and the `maxRetryDuration` option (`MMCONNECT_MAX_RETRY_DURATION`,
documented in the README as *"Maximum number of total seconds to spend retrying failed requests"*)
are **dead**. **Reproduced**: with the stub adapter rejecting, exactly one request is attempted and
the callback fires with the error. The only recovery is the next `setInterval` tick. The documented
setting does nothing.

### Verdict on item 1

**The maintainer's "the old medtronic does not work" is not provable from source as a single
mechanism.** What is established:

[Correction 2026-09-22: the maintainer's statement is operational knowledge (2026-09-21: broken for
some time), not a source claim; this section tests only what source and stubs can show, and does
not contradict it.]

| candidate | verdict | basis |
|---|---|---|
| targets a withdrawn API version | **unsettleable**; churn is evidenced (v6→v5 hotfix), withdrawal is not | read-derived |
| vendor changed authentication | **confirmed as a code fact** — the US branch is dead code and everyone is forced onto a five-step HTML-scraping SSO flow | reproduced |
| abandoned dependency | **confirmed** (`request`, axios 0.26) but **not the breakage path** — the app plugin does not use the `request` uploader | read-derived |
| broken for some accounts | **confirmed and total for care-partner accounts** — `patientId` is never plumbed through from Nightscout | reproduced |
| works but poorly | **confirmed** — no retry at all; the documented retry setting is vestigial | reproduced |

The honest sentence for a release note is: *the legacy MiniMed path has a dead US code path, a
documented setting that does nothing, no retry, an undocumented country default of `gb`, no support
at all for follower accounts, and an unmaintained dependency stack. The source is fully consistent
with the maintainer's report that it no longer works, and it identifies at least one class of user
for whom it certainly cannot — but the source does not by itself prove the feed is dead for a
patient-role EU account.*

---

## 2. What Connect does differently

| | legacy `minimed-connect-to-nightscout@1.5.8` | `nightscout-connect` `minimedcarelink` |
|---|---|---|
| **auth** | five-step EU SSO by HTML scraping; US branch unreachable | same five-step scrape, plus `/users/me`, `/users/me/profile`, `/countries/settings`, M2M-enabled check, patient list |
| **region** | `MMCONNECT_SERVER=EU` picks the host; `MMCONNECT_SERVERNAME` overrides; country defaults to `gb`, undocumented | `CONNECT_CARELINK_REGION` (`us` default) or `CONNECT_CARELINK_SERVER`; **`CONNECT_COUNTRY_CODE` is mandatory and validated** |
| **account roles** | patient only in practice (§1d) | patient and care partner, with `carelinkPatientUsername` or auto-selection |
| **endpoints** | `/patient/connect/data`, BLE carepartner v5 (hard-coded downgrade) | M2M for `GUARDIAN`, BLE periodic otherwise, chosen from `/patient/monitor/data` |
| **cadence** | fixed `setInterval`, `MMCONNECT_INTERVAL` default **60 s**, unaligned | `align_to_glucose`: next 5-minute boundary + 68 s buffer + up to 18 s random jitter; `expected_data_interval_ms` 5 min |
| **session renewal** | `refreshTokenEu` when the token expires within 6 min; on failure, drop cookies and re-login | `refresh` is **commented out** — *"have never seen refreshSession work, disabling until further notice"* — so it **re-runs the full SSO login every ~9 minutes** (`EXPIRE_SESSION_DELAY`) |
| **error recovery** | none (`maxRetry = 1`) | frame backoff 2.5 min × 2^attempt, `maxRetries: 2`, then cycle backoff |
| **deps** | axios 0.26, `request` 2.88, `axios-cookiejar-support` 1.x, Node ≥ 12 | axios 1.x, `axios-cookiejar-support` 2.x wrapper, xstate |
| **treatments** | **none** | meal bolus, correction bolus, BG check / calibration from `markers[]` |
| **logging** | `MMCONNECT_VERBOSE` | `CONNECT_DEBUG`; see BF-42 for which pins still leak credentials |

Two of these deserve flagging to the maintainer rather than being filed as wins:

- **Full re-authentication every ~9 minutes** replaces a token refresh. Read-derived from
  `lib/machines/session.js` delays plus the commented-out `refresh` in the source. Whether a vendor
  rate-limits five-step logins at that rate is exactly the kind of thing that only shows up live.
- **Connect writes treatments; the legacy path never did.** For a MiniMed operator who also runs a
  pump uploader or AndroidAPS against the same Nightscout, boluses may now arrive twice and be
  counted twice in the IOB the site displays. Read-derived; it belongs in a deprecation notice as a
  thing to check, not as a silent gain.

---

## 3. Data fidelity, same terms as E1

All **reproduced** with `compare.js`, feeding the retired package's *own* recorded CareLink payload
(`test/_fixtures.js`) to all three implementations under `TZ=UTC MMCONNECT_SERVER=EU`.

| | legacy | Connect `v0.0.14` | Connect `234d47c8` (dev's pin) |
|---|---|---|---|
| entry shape | `{type,sgv,date,dateString,device}` + `trend`/`direction` on last | same, plus raw `lastSGTrend` | same |
| **device string** | `connect-paradigm` | `nightscout-connect://minimedcarelink/PARADIGM` | same |
| units | `sgv` copied raw | `sgv` copied raw | same |
| **`bgUnits` in the payload** | **never consulted** | **never consulted** | never consulted |
| sentinel `sg: 0` | **dropped** (`kind==='SG' && sg!==0`) | **dropped** | **KEPT** → `[0, 120, 0]` |
| trend `NONE` | `trend 0 / 'NONE'` | `trend 4 / 'Flat'` | same |
| how many on first poll | last `MMCONNECT_SGV_LIMIT` (24) | all 288 newer than the DB high-water mark | same |
| duplicate suppression | in-process only; resets on restart | from the database via `data-processed`; survives restart | same |
| `devicestatus.created_at` | measurement time | measurement time | **`new Date()`** — a 2015 measurement filed as observed in 2026 |
| `devicestatus` dedup | in-process recency filter | `created_at > last_known.devicestatus` | **none — emitted every poll** |
| `pump.iob.timestamp` | ISO string | ISO string | raw epoch number |
| **`pump.clock`** | parsed to ISO UTC | **raw `"Oct 17, 2015 09:09:14"`** | raw |
| raw `carelink_raw` entries | optional, `MMCONNECT_STORE_RAW_DATA` | **not produced** | not produced |
| payload with **no `markers` field** | fine — never reads it | **throws** | **throws** |

### 3a. The sentinel regression ships to operators today

**Reproduced.** `origin/master` pins `v0.0.13`; that tree's entry pipeline is
`filter(has_dateprop) → map(reassign_zone) → map(sgs_to_sgv) → filter(is_missing) → map(assign_device)`
with no glucose filter. `v0.0.14` inserts
`.filter(reading => reading.sg !== 0 && (!reading.kind || reading.kind === 'SG'))`.

Consequence, **reproduced** against the shipping `lib/plugins/simplealarms.js` with a control
ladder: `mgdl` 55 → *Warning LOW*, 40 → *Urgent LOW*, 39 → nothing, **0 → nothing**. The guard is
`lastSGVEntry.mgdl > 39`. A sentinel zero is not itself alarmed — but while it is the newest
entry, **the whole high/low alarm evaluation is skipped**. It also renders through
`lib/plugins/errorcodes.js` as `0??`.

### 3b. Backfill

Legacy's recency filter starts at `lastTime = 0` in memory, so a restart re-posts up to
`MMCONNECT_SGV_LIMIT` entries; the `sysTime`+`type` upsert in `lib/server/entries.js` absorbs them.
Connect's high-water mark comes from the database, so restarts do not re-post — a genuine
improvement. But on `dev`'s and `master`'s pin, **a backfilled measurement is stamped
`created_at = now`**, so old pump status arrives looking new; parcel 4's own retirement evidence
document already claims the fix (*"A backfill case verifies old measurements retain their age
rather than appearing newly observed"*) and that fix is real at `c962a13f` and later.

### 3c. Connect crashes the Nightscout process on a payload with no `markers`

`transformPayload` guards `data.medicalDeviceFamily` and then does `data.markers.filter(...)`
unguarded. The retired package's own recorded CareLink payloads have **no `markers` key** —
because the retired transform never looks at one.

**Reproduced two ways.**

1. Direct: `transformPayload(legacyFixture)` throws
   `TypeError: Cannot read properties of undefined (reading 'filter')` on **both** `v0.0.14` and
   `234d47c8`.
2. Through the shipping loop (`loop.js` — real `lib/builder.js`, real `lib/machines/*`, real
   transform; only the three network calls stubbed), with a matched control:

   | arm | result |
   |---|---|
   | payload **with** `markers: []` | persists one batch, process survives |
   | payload **without** `markers` | `>>> UNCAUGHT, PROCESS WOULD DIE: TypeError: Cannot read properties of undefined (reading 'filter')` |

   The throw is synchronous inside `transformService`, *before* `Promise.resolve`, so the state
   machine's `onError` transition never sees it. `cgm-remote-monitor` registers **no**
   `uncaughtException` or `unhandledRejection` handler anywhere in `lib/`, `server.js` or `bin/`
   (**reproduced**: the grep returns nothing), so the exception terminates the Nightscout process.

   *Non-vacuity (rule 2):* the break is the removal of one field and the control is its presence;
   the control persists a batch, so the harness is not reporting a crash it would report anyway.

Every `markers` occurrence in the connector's own test suite is `markers: []` — four call sites in
`test/minimed-data.test.js` and `test/minimed-logging.test.js`, all of them injecting the field.
**The absence of the field has zero coverage.** Whether the vendor's BLE periodic endpoint ever
omits it cannot be settled here; the retired package's recorded payloads do.

---

## 4. "Nothing is lost" — enumerated

**Coverage method.** For settings: every key the legacy plugin reads was enumerated by executing
`lib/plugins/mmconnect.js` `getOptions` and diffing its keys against what
`applyMmconnectToConnectCompatibility` writes (**reproduced**, `item5.js` §6). For data: every
field each transform emits was diffed from executed output on identical payloads (**reproduced**,
`compare.js`). For endpoints and roles: both sources read in full (**read-derived**).

| capability | legacy | Connect | verdict |
|---|---|---|---|
| glucose entries | yes | yes | preserved |
| trend on the newest reading | yes | yes (`NONE` maps to `Flat/4` not `NONE/0`) | cosmetic change |
| pump devicestatus (battery, reservoir, IOB, clock) | yes | yes | preserved |
| GUARDIAN vs PARADIGM branch | yes | yes | preserved |
| uploader battery | `conduitBatteryLevel` | same, with a GUARDIAN-aware fallback | preserved |
| EU / US / custom server | yes (undocumented knobs) | yes, documented and validated | improved |
| **care-partner / follower accounts** | code exists, unreachable from Nightscout | yes | **gained** |
| **treatments (bolus, carbs, calibration)** | none | yes | **gained** — and see the double-count caution in §2 |
| retry / backoff | none | real | improved |
| **`MMCONNECT_STORE_RAW_DATA` → `carelink_raw` entries** | yes | **no equivalent** | **LOST** |
| **`MMCONNECT_SGV_LIMIT`** | yes (default 24) | **no equivalent**; writes everything newer | **LOST as a control** |
| **`MMCONNECT_INTERVAL`** | yes (default 60 s) | **no equivalent**; cadence is driver-owned (~5 min) | **LOST as a control** |
| `MMCONNECT_MAX_RETRY_DURATION` | documented but dead | superseded | no real loss |
| `MMCONNECT_VERBOSE` | yes | `CONNECT_DEBUG` | preserved |
| **device string continuity** | `connect-paradigm` | `nightscout-connect://minimedcarelink/PARADIGM` | **changes** — history splits across two device names; parcel 4's own evidence calls this deliberate |
| **20-minute stale-payload guard** | drops the whole payload | no equivalent (the high-water-mark filter covers the glucose case) | no practical loss for entries; see §5 for devicestatus on the old pin |
| **pump model / region coverage** | — | — | **cannot be enumerated from source**; neither implementation branches on model beyond `GUARDIAN` vs everything else |

**So "nothing is lost" is not quite true.** Three named residues — `carelink_raw`, `MMCONNECT_SGV_LIMIT`,
`MMCONNECT_INTERVAL` — plus a device-string discontinuity that splits a user's chart history
across two device names. None is safety-critical. All four fit in two sentences of a deprecation
notice. The deprecation notice has to name them; it does not have to be long.

---

## 5. The timezone divergence — BF-44 into BF-41, end to end

This is item 4. The result is that for zone-less payloads it is Connect, not legacy, that mis-files readings.

### 5a. The divergence, reproduced independently

`compare.js` §D, zone-less timestamps (the shape the retired package's own recorded payloads use),
`TZ=UTC MMCONNECT_SERVER=EU`:

| pump offset | legacy files at | Connect files at | Δ |
|---|---|---|---|
| UTC+0 | `09:09:59Z` | `09:09:59Z` | **0** (control) |
| UTC+2 | `09:09:59Z` | `11:09:59Z` | Connect **+2 h into the future** |
| UTC−7 | `09:09:59Z` | `02:09:59Z` | Connect −7 h |
| UTC+5:30 | `08:39:59Z` | `14:39:59Z` | −6 h (legacy rounds its guess to whole hours) |

This independently confirms BF-44. **It also settles the
direction, which matters more than the magnitude: it is *Connect* that files the reading in the
future**, for any pump in a zone east of the server clock, because `reassign_zone` falls back to
the identity function when `lastConduitDateTime` is absent and `sgs_to_sgv` then hands a zone-less
pump-local string to `Date.parse`, which reads it as *server*-local.

### 5b. The chain into the stale-data alarm, reproduced

`chain.js` runs both shipping transforms and then the shipping `lib/plugins/timeago.js` on
`origin/dev`. Scenario: pump in UTC+2, server clock UTC, **the feed has actually been dead for
40 minutes**. The browser alarm runs at its shipped defaults (`alarmTimeagoWarn`/`alarmTimeagoUrgent`
true, 15 and 30 minutes); the server push alarm is opt-in and the harness sets
`extendedSettings.enableAlerts = true` explicitly, as BF-41 requires one to say.

```
TRUTH (40 min stale)         filed=…11:20:00Z  age=  40.0min  checkStatus=urgent   browserAlarm=true   pushAlarms=[2 = URGENT]
LEGACY minimed-connect       filed=…11:20:00Z  age=  40.0min  checkStatus=urgent   browserAlarm=true   pushAlarms=[2 = URGENT]
CONNECT minimedcarelink      filed=…13:20:00Z  age= -80.0min  checkStatus=current  browserAlarm=false  pushAlarms=[]
```

**The legacy path raises the stale-data alarm. The Connect path silences both alarm paths.**

Controls and ablations, same harness:

| arm | result | reading |
|---|---|---|
| pump UTC+0 | all three identical, urgent fires | harness reports agreement when there is agreement — not vacuous |
| pump UTC+2, zone-less | Connect silent | **the break** |
| pump UTC−7, zone-less | Connect fires urgent, but on a reading filed 7 h 40 m old | wrong direction is not safe either: the trace plots 7 h out and the alarm is permanently urgent |
| zone-**bearing** ISO payload, pump UTC+2 | **roles invert** — Connect correct, legacy files 2 h in the past | the divergence exists in *both*, in opposite directions, selected by payload shape |

### 5c. What this means for the retirement

- The divergence exists in **both** implementations. Which one is wrong depends on whether the
  vendor payload carries a zone designator.
- For **zone-less** payloads — the shape the retired package's own recorded fixtures use — the
  legacy path is right and **Connect is wrong**, and wrong in the direction that silences the stale
  alarm for every pump east of the server clock. Hosted Nightscout servers conventionally run UTC,
  which — **assumption, not measured here** — would put most of Europe, Africa, Asia and Oceania on
  the future-dated side. A reviewer should confirm the server-clock convention.
- For **zone-bearing** payloads — the shape the connector's own tests use — Connect is right and
  legacy is wrong (and per BF-44, on the non-EU branch legacy throws `RangeError: Invalid time value`
  instead).
- **Therefore the retirement improves this for some users and makes it worse for others, and which
  is which is decided by a payload property nobody in this programme has observed on a real
  account.** That is the residue that matters most, because its failure mode is the one detector a
  self-hoster has for "my child's glucose data stopped" going quiet.

### 5d. A second, separate detector this silences — `pump.clock`

Connect assigns `pump.clock` the raw vendor string; legacy parsed it to ISO UTC. `lib/plugins/pump.js`
does `moment(pump.clock)` and then
`urgent.isAfter(result.clock.value)` to raise *"URGENT: Pump data stale"*.

**Reproduced** with the shipping `moment-timezone`: `moment("Oct 17, 2015 09:09:14")` is *valid* but
is parsed in the **server's** local zone (under a UTC−7 system clock it yielded `2015-10-17T16:09:14Z`),
and the call trips moment's non-ISO-string deprecation warning. And `moment(<invalid>).isAfter` — reached
whenever the vendor string is not something moment's fallback can read — returns **false**, so the
pump-stale warning never fires.

So `PUMP_WARN_CLOCK` / `PUMP_URGENT_CLOCK` are shifted by the server's UTC offset in the good case
and silently disabled in the bad one. BF-44 records the unparsed assignment; this is its measured
consequence in a detector BF-44 does not name.

---

## 6. The auto-adoption path for MiniMed

### 6a. On `dev` and `master`: it does not exist

**Reproduced** (`item5.js` §1). `applyBridgeToConnectCompatibility` with an `mmconnect`-only
environment returns `{"migrated":false,"legacy":false}` and writes nothing.

And **BF-45 reproduced directly** (`item5.js` §2): `lib/plugins/mmconnect.js` `init` returns a live
runner *whether or not* `extendedSettings.connect.source === 'minimedcarelink'`:

```
connect=<none>            mmconnect.init -> RETURNS A RUNNER (legacy will poll)
connect=minimedcarelink   mmconnect.init -> RETURNS A RUNNER (legacy will poll)
```

`setupBridge` stands down for Connect; `setupMMConnect` does not. An operator staging the new
settings before removing the old ones runs **both** ingestion paths at once — and because of §5a
the two paths compute different `sysTime` values, so the `sysTime`+`type` upsert in
`lib/server/entries.js:130` does **not** absorb the duplicates. Two traces, offset by the pump's
UTC offset.

[Correction 2026-09-22: BF-45's severity assumes the legacy mmconnect path still ingests data. The
maintainer states it has been broken for some time (operational knowledge, not measured here); if so,
the double-trace case may not arise in practice. BF-45 has not been re-graded.]

### 6b. On parcel 4/5: the shim exists, and it is well behaved

**Reproduced** (`item5.js` §§3–6) against the shipping
`origin/chore/mime-exposure-review:lib/server/mmconnect-connect-compat.js`:

| case | result |
|---|---|
| `MMCONNECT_*` only, no country code | `{"migrated":false, error:"…Set CONNECT_COUNTRY_CODE… The country cannot be inferred from MMCONNECT_SERVER."}` |
| `MMCONNECT_*` + `countryCode=gb`, `server=EU` | `{"migrated":true}` → `{source:'minimedcarelink', carelinkUsername, carelinkPassword, carelinkRegion:'eu'}` |
| `server=US` | → `carelinkRegion:'us'` |
| `server=carelink.example.invalid` | → `carelinkServer:'carelink.example.invalid'` (region left unset) |
| already `source:'dexcomshare'` | refuses with an explanatory error, leaves the existing config alone |
| already `source:'minimedcarelink'` | migrates, existing explicit values win |
| **applied twice** | `{"migrated":true}` both times, byte-identical `connect` object — **idempotent** |
| **half-failure (country missing)** | the partial mapping is built in a **local copy** and discarded; `env.extendedSettings` is byte-identical to its input — **no half-written credentials** |

*Trigger*: unconditional inside `setupConnect`, before `nightscout-connect` is constructed.
*Operator told?* Yes on success — `"MMCONNECT credentials are served by Nightscout Connect; the
legacy MiniMed bridge is retired in 15.0.9."` And on failure the message is pushed into
`ctx.bootErrors`, which is **BF-61**: a boot error installs `app.get('*', bootErrorView)` and returns
before every router and before websocket setup, so a missing `CONNECT_COUNTRY_CODE` takes the whole
site down, not just ingestion. That entry already stands; this study independently confirms the
shim's half of it.

*What the shim drops* — **reproduced** by diffing executed `getOptions` keys against the keys the
shim writes:

```
legacy getOptions -> username, password, sgvLimit, interval, maxRetryDuration, verbose, storeRawData
shim writes       -> countryCode, source, carelinkUsername, carelinkPassword, carelinkRegion
DROPPED           -> sgvLimit, interval, maxRetryDuration, verbose, storeRawData
```

which is exactly the residue list in §4, arrived at independently.

---

## 7. What cannot be settled here, and why each one matters

1. **Does a real CareLink login still succeed for the retired package?** The whole "short
   deprecation window" argument rests on it. Needs one live patient-role account, EU and US.
   [Correction 2026-09-22: the maintainer reports it has been broken for some time — operational
   knowledge, still not measured here.]
2. **Do real CareLink payloads carry zone designators, and do they carry `lastConduitDateTime`?**
   This single property decides whether §5's future-dated readings are latent or active, and it is
   the difference between the retirement fixing the stale-alarm hazard and causing it.
3. **Does the BLE periodic endpoint ever return a payload without `markers`?** If yes, §3c kills
   the Nightscout process on every poll.
4. **Does the vendor tolerate a full SSO login every ~9 minutes?** Connect disabled token refresh
   because it "never worked". A rate-limit or lockout here is invisible until it is live.
5. **Which pump models and regions actually work on each side?** Neither source branches on model
   beyond `GUARDIAN`, so source reading cannot answer it at all.
6. **Does a care-partner request with `patientId: undefined` fail loudly or return empty?** It
   decides whether §1d reads as "broken" or "silently empty" in the deprecation notice.

---

## 8. Recommendations for the maintainer (draft — requires review)

1. **Do not let the deprecation notice say "nothing is lost."** Say instead: *raw CareLink capture
   (`MMCONNECT_STORE_RAW_DATA`), the `MMCONNECT_SGV_LIMIT` and `MMCONNECT_INTERVAL` controls, and the
   `connect-paradigm` device name are retired; follower accounts, treatments, retry and a country
   setting are added.* That is four lines and it is defensible.
2. **`CONNECT_COUNTRY_CODE` is the migration's real cost**, because the shim itself states the
   country cannot be inferred. Every MMCONNECT operator must set a new variable by hand, and on
   parcel 4 forgetting it takes their whole site down (BF-61). This needs to be the headline of the
   deprecation release, not a footnote.
3. **Do not advise staging `CONNECT_*` alongside `MMCONNECT_*`** on any released version. That
   advice is safe for Dexcom and unsafe for MiniMed (BF-45, reproduced in §6a), and the resulting
   duplicates are not absorbed by the upsert.
4. **Settle residue 2 before the retirement ships**, or ship the retirement with a `pump.clock` and
   entry-timestamp fix in the connector. Of everything in this study, only §5 has a failure mode
   where a person's glucose data stops and the software does not say so.
5. **Whatever else happens, move `master` off the `v0.0.13` pin before telling anyone to migrate
   MiniMed to Connect.** On that pin Connect ingests gap sentinels as `sgv: 0`, which suppresses
   the high/low alarm evaluation while it is the newest entry, and files pump status as observed-now.
   `bf/connect-pin` already exists for this.

---

*Not medical advice. Anyone running Nightscout for their own or a family member's diabetes care
should treat a change to how glucose data reaches their site as a change worth watching closely,
and should discuss monitoring and alarm settings with their care team.*
