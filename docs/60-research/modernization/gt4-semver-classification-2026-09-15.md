# GT4: semver classification of every changeset in flight

Date: 2026-09-15. Status: **draft evidence for maintainer decision.** Contributor-facing.
Companion to [release readiness](../../30-design/modernization/cgm-remote-monitor-release-readiness-2026-09-14.md)
and [Phase 0 PR sequencing](../../30-design/remedial/phase0-pr-sequencing-2026-09-15.md).

Nothing in this document was pushed, merged, tagged or published. It proposes version
numbers; it does not set any.

## How everything here was measured

Reads only, from checkouts already on this machine. No branch, tag or worktree was
created, moved or deleted.

| What | Ref / path |
|---|---|
| `cgm-remote-monitor` refs | `externals/cgm-remote-monitor-official`, `origin/master` = `92d08342` (15.0.8), `origin/dev` = `a8888f0d` (15.0.9 candidate), the five `chore/*` cut tips |
| Phase 0 branches | `externals/work/crm-bf-*`, each measured as `git diff a8888f0d HEAD` |
| `nightscout-connect` | `externals/work/nc-jitter`; `v0.0.13` = `b394411`, `release/v0.0.14` = `649a7de`, tag `v0.0.14` = `649a7de` |
| Query oracle | `mingo` under `tools/qc/node_modules` (decision D8) |

Where a row below says **executed**, the shipping module or an exact transcription of it
was run under `node` and the transcript is quoted. Where it says **read**, the
classification rests on reading the diff. Orderings in this document are more durable
than the absolute figures (house rule 9); the figures are as of the refs above.

---

## 0. Corrections to the brief and to repository documents

Lead with these. Four of them change a conclusion.

### 0.1 `master` does **not** pin `nightscout-connect` with a semver range

[`phase0-pr-sequencing-2026-09-15.md:388`](../../30-design/remedial/phase0-pr-sequencing-2026-09-15.md)
says:

> | `master` (15.0.8, **what operators run**) | `"^0.0.12"` — a semver range from **npm** |

Measured, `origin/master:package.json` reads:

```
"nightscout-connect": "https://github.com/nightscout/nightscout-connect/archive/refs/tags/v0.0.13.tar.gz"
```

`^0.0.12` was master's pin, but two commits replaced it: `97a603fb` (`^0.0.12`) →
`a91e8ee4` (`github:nightscout/nightscout-connect#v0.0.13`) → `561974de` (the v0.0.13 tag
tarball). The `^0.2.12` that does appear on master and dev is **`share2nightscout-bridge`**,
a different package; the two look alike and were probably conflated.

Consequences:

- There is no "semver range from npm" mechanism anywhere in the tree. **All pins are
  tarball URLs.** The three mechanisms reduce to two shapes — *tag* tarball (master) and
  *commit* tarball (everything else).
- The doc's inference that "merging in the connect repository ships BF-34 to nobody"
  survives, and is in fact stronger than argued: even the `^0.0.12` it thought was there
  would have floated nothing, because npm's caret on a `0.0.z` version matches that
  version exactly.
- Master is **already on v0.0.13**, so `bf/connect-pin`'s move to v0.0.14 is a
  single-tag-step bump for operators, not a two-step one.

### 0.2 There are **four** connect pins in flight, not three

| Ref | pin | commits past `v0.0.13` |
|---|---|---:|
| `origin/master` | `refs/tags/v0.0.13.tar.gz` | 0 |
| `origin/dev` | `234d47c8` | 1 |
| `origin/chore/mime-exposure-review` (cut 4) | **`c962a13f`** | 5 |
| `origin/chore/nightscout-modernization` (cut 5) | `b77e5bb` | 7 |

Cut 4's pin is absent from every document I read. It matters because the two mitigations
for the credential-leak problem are **split across the two release trains**:

| connect commit | in `234d47c8` (dev / 15.0.9) | in `c962a13f` (cut 4) |
|---|---|---|
| `9fa2c3c` Dexcom credentials out of logs | no | **yes** |
| `5349d47` MiniMed credentials out of logs | no | **yes** |
| `77e2396` internal payloads out of logs | no | **yes** |
| `8406edf` MiniMed data contract | no | **yes** |
| `51b6e6e` listener release on stop | no | no |
| `234d47c` debug logging opt-in | **yes** | **no** |
| `c1cce2a` BF-34 + start jitter | no | no |

Measured with `git merge-base --is-ancestor` for each pair. So dev has the *narrowing*
(logging off by default) without the *redaction*; cut 4 has the redaction without the
narrowing. **Neither train carries both until cut 5**, and the adopted order ships 15.0.9
first and holds cut 4 back longest. `bf/connect-pin` moving dev to v0.0.14 is what closes
this, because v0.0.14 is the first ref that contains all seven.

### 0.3 Cut 1 does not merely "drop Node 20", and the floor it replaces is Node **16**, not 20

`package.json` on `master` and `dev` both declare `"engines": {"node": ">=20.x"}`, but
that string is **not enforced**. `lib/server/bootevent.js` on dev enforces its own,
looser rule:

```js
    // Node 16+ is supported (overlap with previous release)
    if (semver.satisfies(nodeVersion, '>=16.x')) { ... next(); return; }
```

Cut 1 replaces that with `lib/server/runtime-policy.js`, which reads `engines.node` from
`package.json` and calls `process.exit(1)` when it is not satisfied, and sets
`engines.node` to `"^22.23.2 || ^24.20.0"`.

So cut 1 changes three things at once, only one of which the brief names:

1. The **enforced** floor moves from Node 16 to Node 22.23.2 — six major versions, not one.
2. The declared range stops being a floor and becomes a **whitelist of two ranges**. Node
   21, 23 and anything ≥ 25 are excluded, and so are Node 22.0–22.23.1 and 24.0–24.19.x.
   An operator on a perfectly current Node 22 LTS below 22.23.2 boots today and exits
   immediately after cut 1.
3. The check goes from advisory-by-mismatch to a hard exit that also covers `npm install`.

Cut 1 **also** drops MongoDB 4.4 from CI (`[4.4, 5.0, 6.0]` → `[5.0, 6.0]`), which the
five-cuts summary attributes to cut 1 but which no version-number discussion picks up.
Two runtime floors move in one branch.

### 0.4 A Dexcom deprecation path **does** exist in code today; a MiniMed one does not

The brief asks whether a deprecation path exists in code today. Split answer.

**Dexcom — yes, and it has been shipping for a while.** `lib/server/bridge-connect-compat.js`
is present on **both `master` and `dev`**. It migrates `BRIDGE_*` credentials onto
`CONNECT_*` automatically, and `lib/server/bootevent.js` on dev prints five
`DEPRECATION WARNING` lines, including one that names the escape hatch:

```
DEPRECATION WARNING BRIDGE_* Dexcom settings are being served by nightscout-connect.
Set DEXCOM_BRIDGE_USE_LEGACY=true to use share2nightscout-bridge.
```

**MiniMed — no.** `lib/server/mmconnect-connect-compat.js` does not exist on `dev` or
`master`. It appears for the first time **in cut 4 itself** — the same branch that deletes
`lib/plugins/mmconnect.js`. There is no release in which an MMCONNECT operator is told
what to do before the thing they depend on is removed. The only MiniMed warning shipping
today is a generic `"DEPRECATION WARNING PLEASE CONSIDER nightscout-connect instead."`
with no instructions and no named replacement setting.

### 0.5 `bf/reads` restricts **six** previously-accepted `?count=` inputs, not two

The brief names `?count=0x10` and `?count=2.5`. Executed against
`externals/work/crm-bf-reads/lib/server/count.js` and against an exact transcription of
the old `if (opts && opts.count) return this.limit(parseInt(opts.count))`:

| `?count=` | old effect | new effect |
|---|---|---|
| `0` | `limit(0)` → **whole collection** | HTTP 400 |
| `0x10` | `limit(16)` | HTTP 400 |
| `2.5` | `limit(2)` | HTTP 400 |
| `-3` | `limit(-3)` (≤3, cursor closed) | HTTP 400 |
| `1e2` | `limit(1)` | HTTP 400 |
| `abc` | `limit(NaN)` | HTTP 400 |
| `9007199254740993` | `limit(9007199254740992)` | HTTP 400 |
| `1`, `10`, `" 5 "`, absent, empty | unchanged | unchanged |

Also broader in scope than "the read path": the validator is `app.use(...)` mounted on the
whole v1 app *before every router*, so it applies to `/treatments`, `/profile`,
`/devicestatus`, `/notifications`, `/activity`, `/food`, `/status`, `/alexa` and
`/googlehome`, and to **writes** as well as reads. A `POST /api/v1/treatments?count=0`
now returns 400 where it previously succeeded. The branch's own CHANGELOG lists the read
routes only.

### 0.6 Three Phase 0 branches are missing from the brief's list

The brief enumerates six cgm-remote-monitor branches. There are **nine** worktrees holding
Phase 0 branches against `a8888f0d`: the six named, plus `bf/food` (`73495331`),
`bf/merge` (`b06c6faf`) and `bf/parms` (`eb0bc918`). `bf/food` changes an **HTTP API v1
response** and therefore cannot be left out of a semver classification. They are in the
table below.

### 0.7 `bf/alarms` and `bf/auth` each carry an unlisted behaviour change

- `bf/alarms` commit `5dcf783f` **removes per-request locale handling** from
  `POST /api/v1/alexa` and `POST /api/v1/googlehome`. Today a request carrying
  `request.locale` is answered in that language; after this commit it is answered in the
  server's configured language. The removal is correct — `ctx.language` and
  `moment.locale()` are process-global, so the old code re-languaged *every later request
  in the process* — but it is a **capability removal on an HTTP endpoint**, and the brief
  does not mention it.
- `bf/auth` is two commits, not one. Besides the plaintext-token fix, `a26ba416` moves the
  authentication throttle from the caller-supplied `X-Forwarded-For` address to the socket
  peer address, and `lib/authorization/storage.js` now writes only an **allow-list** of
  fields (`name`, `roles`, `notes`, `created_at`) for subjects and roles. Any extra field a
  third-party tool has been storing on a subject document is **dropped on the next edit**.
  `GET /api/v1/subjects` also gains a `notes` field in its response.

---

## 1. What "the public surface" means for this application

Semver is specified for a library's API. Nightscout is an application that operators host,
so the brief's surface list is the right adaptation, and I apply it as written:

**S1** HTTP API v1 and v3 request/response contracts · **S2** the plugin interface ·
**S3** the environment-variable configuration surface · **S4** the database schema ·
**S5** the Node (and MongoDB) runtime floor · **S6** any ingestion path an operator's data
flows through.

To these I add one the brief implies but does not name, because two changesets below turn
on it:

**S7** the set of **alarms and notifications** the deployment can emit.

An alarm is a contract with a person, not with a program. A deployment that begins
emitting a persistent URGENT alarm it has never emitted has changed in a way an operator
must be told about before they upgrade, whatever the diff size. Nightscout's own design
treats this as load-bearing: decision D1 keeps single-tenant first-class, and T3.5
deliberately withholds emissions outside tenant scope. I treat S7 as a first-class surface
throughout.

### The decision rule I apply

> **MAJOR** — an operator running a *supported, documented* configuration must change
> something (a runtime, an environment variable, a client, a stored document) for the new
> version to behave as the old one did; **or** a capability that operators use is removed;
> **or** a previously-working configuration now fails to boot or stops ingesting data.
>
> **MINOR** — behaviour an operator can observe changes, or a capability is added, **and**
> no operator action is required for the deployment to keep working: new endpoints, new
> accepted inputs, new response fields, new configuration keys, results that were empty or
> wrong becoming populated or right, an alarm that could not fire becoming able to fire.
>
> **PATCH** — for every input a supported client actually sends, the observable contract is
> unchanged. Only unambiguously broken behaviour becomes correct, with no reachable input
> whose answer changes shape, and no new emission.

Two consequences worth stating, because they decide most rows:

- **"It was a bug" does not make a fix a patch.** If a query returned `[]` and now returns
  2,000 rows, a dashboard's behaviour changed. The user-visible answer moved; the number
  moves with it. This is the single largest departure from the project's current practice.
- **A restriction on a previously-accepted input is major *only if a real client sends it*.**
  See §3.5, which argues it.

---

## 2. Master classification table

Confidence: **measured** = observed by executing code; **read** = from the diff;
**inferred** = reasoning over both. ⚖ marks a **judgement call** rather than a rule
application; each is restated in §8.

| # | Changeset | Surface | Operator-visible effect | Class | Conf. | Reasoning |
|---|---|---|---|---|---|---|
| 1 | `bf/connect-pin` `0807eb1c` | S6 | Connector retry/log behaviour changes wholesale; `package-lock.json` deliberately left stale so `npm ci` fails loudly | **minor** | measured | One-line pin move, but it is the vehicle for every `nightscout-connect` change in §6. A version number must describe what an operator gets, not how many lines moved. ⚖ |
| 2 | `fix/connect-timer-jitter` `c1cce2a` (connect) | S6 | A vendor outage appears to recover **more slowly**: retries go from 256 ms to the 2.5 min every source configures | **minor** (in cgm-remote-monitor) / **0.1.0** (in connect) | measured | 585.94× at every attempt below the cap; see §6 |
| 3 | `bf/cache` `ddcdb1a8` + `4f86bab1` | none | Faster reads; identical bytes on the wire | **patch** | read | Pure internal clone-avoidance. `/api/v1/entries` untyped read 0.837 ms → 0.025 ms. Also removes a dead `mills` write at `dataloader.js:203`. No surface. |
| 4 | `bf/merge` `b06c6faf` | none (client) | A page that froze after a delta removed a treatment now keeps updating | **patch** | read | Client-side array-splice bounds fix (BF-36). No contract. |
| 5 | `bf/parms` (3 commits) | none (client) | A bare flag in the URL no longer stops the page loading; `%10` no longer eaten by `%1` | **patch** | read | Client URL parsing and translation substitution. Fixes an unambiguous crash and an unambiguous mis-substitution. ⚖ — `queryParms` no longer turns `_` into a space, so a bookmarked URL relying on that is affected. |
| 6 | `bf/alarms` `8714093b` | **S7** | insulinage's **URGENT alarm begins firing for operators who have never received it**; `persistent` sound; reported level stops being stuck at WARN | **minor** | measured | `insulinInfo.urgent` is never assigned; `age >= undefined` is `false` for every age. Executed: `999 >= undefined → false`, `999 >= 72 → true`. A new emission on a safety surface. See §3.1 |
| 7 | `bf/alarms` `99e46a52` | S3 | An `ENABLE` entry naming a plugin's file (`insulinage`) now prints a `console.warn` suggesting `iage`; stock settings stay silent | **patch** | measured | Adds a log line, changes no behaviour. Reconstructed the matcher and ran a stock `ENABLE` string: `food`, `bridge`, `delta`, `devicestatus`, `cors` all silent; all six aliases warn. |
| 8 | `bf/alarms` `5dcf783f` | **S1** | `POST /api/v1/alexa` and `/googlehome` stop honouring `request.locale`; answers come back in the server's language | **major** | read | A documented per-request capability is removed. Correct removal — the old code set process-global state — but removal is removal. See §3.1 |
| 9 | `bf/auth` `a26ba416` | S1, S3 | A caller rotating `X-Forwarded-For` is now throttled; behind a shared proxy, failing clients share one throttle bucket | **minor** | read | No successful request is ever delayed (the sleep moved to the failure path), so no working client is affected. Closes a bypass. ⚖ — see §3.4 |
| 10 | `bf/auth` `64db1f35` (storage allow-list) | **S4** | Editing a subject or role **discards any field not in the allow-list**; existing stored `accessToken`/`digest` values are dropped on load | **major** | read | A document loses data on an operation that is not a delete. Intended and right for the token; unbounded for anything else a tool has stored. See §3.4 |
| 11 | `bf/auth` `64db1f35` (`/subjects` gains `notes`) | S1 | `GET /api/v1/subjects` response gains a `notes` field; the admin edit dialog stops blanking notes | **minor** | read | Additive response field. |
| 12 | `bf/coercion` `88d1f8a4` | **S1** | Filters that returned `[]` now return rows; decimal bounds stop rounding down; `find[sgv][$exists]=true` stops being inverted | **minor** | measured | Executed old vs new; see §3.2. 158 coercions over 5 collections. No operator action needed; every changed answer is more correct — **except** `$exists=false`, see §9.1 |
| 13 | `bf/reads` `4a398d47` | S1 | `GET /api/v1/count/entries/where` goes from `[]` to `[{"_id":null,"count":288}]` | **minor** | read | An endpoint that returned nothing now returns numbers. |
| 14 | `bf/reads` `c8fb536b` | none | Count requests stop printing the filter and its values to stdout | **patch** | read | Log removal. Also removes a data-exposure path. |
| 15 | `bf/reads` `399dc283` | S1 | v3 paging adds `_id` as a final sort key; documents stop being skipped and repeated across page boundaries | **patch** | read | Only the order of *tied* documents changes, which was already non-deterministic. ⚖ — a client that depended on the accidental tie order is affected. |
| 16 | `bf/reads` `ba70f1fc` | S1 | `GET /api/v3/devicestatus?fields=uploader.battery` goes from `{}` to `{"uploader":{"battery":80}}` | **minor** | read | Previously-empty answer becomes populated. Comma-separated top-level `?fields=` is byte-identical. |
| 17 | `bf/reads` `1640b64b` | **S1** | `?count=0` (and five other spellings) now HTTP 400 across **all** v1 routes, reads and writes | **major** ⚖ | measured | A restriction on previously-accepted input. Argued at length in §3.5 — I land on major, narrowly, and the counter-argument is real |
| 18 | `bf/reads` `ea50cf52` | S1 | `?limit=0x10` on v3 now 400 instead of returning the whole collection past `API3_MAX_LIMIT` | **minor** | read | Same shape as #17 but v3's limit is already a *documented closed contract* with a 400 path; this restores the documented behaviour rather than narrowing it. ⚖ |
| 19 | `bf/food` `73495331` | **S1**, S4 | `/api/v1/food/quickpicks` returns quick picks written by any JSON client, and orders `position` numerically not lexicographically | **minor** | read | The filter went from `{hidden:'false'}` (the string only) to `{hidden:{$nin:[true,'true']}}`. Previously-hidden records appear. BF-16. |
| 20 | **Phase 0 as one release** | S1, S4, S7 | Union of rows 1–19 | **major** ⚖ | inferred | Driven by #8, #10 and #17. If those three are held back, the remainder is a clean **minor** — see §3.6 |
| 21 | **15.0.9 as it stands on `dev`** | S1, S3, S6 | D3 5→7 under the charts; two new env vars; logging off by default; connect pin moved to an untagged SHA | **minor** | measured | See §4. Not a patch under any reading. Not major either — nothing forces operator action |
| 22 | **Cut 1** `chore/retire-jsdom` | **S5** | Node floor 16→22.23.2 with a hard `process.exit(1)`; Node 21/23/25+ and Node 22.0–22.23.1 excluded; MongoDB 4.4 leaves CI | **major** | measured | See §5.1. Deployment stops starting. Nothing is more operator-visible than that |
| 23 | **Cut 2** `chore/build-runtime-separation` | S2 | Page bundles, narrowed D3, event bus, boot sequence, Babel 8 | **minor** ⚖ | read | 60 prod files, +923/−465. No declared surface moves, but the plugin interface and boot order are rearranged under third-party plugins. See §5.2 |
| 24 | **Cut 3** `chore/compose-mongodb6` | S4, S5 | MongoDB driver 5→7; bundled compose default `mongo:5.0.32`→`6.0.27`; jQuery UI | **minor** | measured | CI keeps 5.0 **and** adds 7.0/8.0, so no tested server version is lost in this cut. The compose default is a *default*, not a floor |
| 25 | **Cut 4** `chore/mime-exposure-review` | **S6**, S3 | `lib/plugins/bridge.js` (−139) and `lib/plugins/mmconnect.js` (−121) deleted; **every MMCONNECT operator's site fails to boot** until they set `CONNECT_COUNTRY_CODE`; `DEXCOM_BRIDGE_USE_LEGACY` becomes silently inert; running BRIDGE and MMCONNECT together becomes impossible | **major** | measured | The clearest major in the programme, and worse than the brief states. See §5.4 |
| 26 | **Cut 5** `chore/nightscout-modernization` | S2, S1 | Express 4→5, Helmet 4→8, EJS, Axios, Mocha 12, Swagger | **major** ⚖ | read | Express 5 changes routing and error semantics under every plugin that mounts a route, and Helmet 8 sets response headers an embedding client may see. See §5.5 |
| 27 | **`nightscout-connect` 0.0.13 → 0.0.14** | library API | `backoff()` option precedence fixed, jitter default changes, unknown jitter now **throws**, `max_interval_ms` added; log redaction; MiniMed data contract | **0.1.0**, not 0.0.14 ⚖ | measured | See §6 |

---

## 3. Phase 0, argued

### 3.1 `bf/alarms` — one minor, one patch, one major in three commits

**The URGENT alarm (minor).** `lib/plugins/insulinage.js:92` tested
`insulinInfo.age >= insulinInfo.urgent`. `insulinInfo` is built at line 47 as
`{found, age, treatmentDate}` and `urgent` is never assigned to it anywhere in the file
(grepped). Executed:

```
insulinInfo.urgent = undefined
age 999 >= insulinInfo.urgent (OLD) -> false
age 999 >= prefs.urgent 72 (NEW)    -> true
```

Every comparison against `undefined` is `false`, so the URGENT branch was unreachable for
every operator in every configuration since the line was written. Two things follow, and
they are different in kind:

1. `insulinInfo.level` could never reach `levels.URGENT`. It stuck at `WARN` once
   `age >= prefs.warn`. The pill colour and the reported level change for every operator
   whose reservoir is past `IAGE_URGENT` (default 72 h).
2. With `IAGE_ENABLE_ALERTS` on, a **`persistent`-sound URGENT notification** now fires at
   exactly `age === prefs.urgent`, within the 20-minute post-hour window. This is an
   emission a deployment has never produced.

Why minor and not major: nothing an operator configured stops working, and nothing they
must change. But S7 says this cannot be a patch, and the operator-facing release note must
say plainly that a new alarm will start arriving. That note is not optional.

**The `ENABLE` warning (patch).** I reconstructed the matcher from
`lib/plugins/index.js` and ran it against a stock `ENABLE` string. `food`, `bridge`,
`delta`, `devicestatus` and `cors` — the `ENABLE` entries that are features rather than
plugins — produce **no** warning, and all six file-name aliases produce the right
suggestion. Caveat on this measurement: I reconstructed the plugin-name list by hand
rather than booting the real registry, so this is evidence the tolerance is tuned
sensibly, not a run of the shipping code.

**The Alexa/Google Home locale removal (major).** Row #8. I want to be explicit that I am
*not* saying the change is wrong. The old code called `ctx.language.set(locale)` and
`moment.locale(locale)` — both process-global — so one Alexa request in French left the
whole server in French for every subsequent request until something changed it back. The
commit's own comment explains why a per-request locale cannot be threaded through today:
translations are read once at boot, and every virtual-assistant handler captures
`ctx.moment` at plugin init. Removing the broken behaviour is the right call. It is still
the removal of a capability on an HTTP endpoint that a Spanish- or German-speaking
operator's Alexa device exercises on every question, and there is no replacement in the
same changeset. Under the rule in §1 that is major, and this is exactly the kind of change
that should not be smuggled into a "bug fix" release under a patch number.

### 3.2 `bf/coercion` — minor, and the single strongest case against current practice

Executed, old (`a8888f0d:lib/server/query.js`) against new, same inputs:

```
OLD entries   find[sgv][$exists]=true      -> {"sgv":{"$exists":null}}    (NaN)
NEW entries   find[sgv][$exists]=true      -> {"sgv":{"$exists":"true"}}
OLD entries   find[sgv][$gte]=100          -> {"sgv":{"$gte":100}}
NEW entries   find[sgv][$gte]=100          -> {"sgv":{"$gte":100}}
OLD treatments find[insulin][$gte]=1.5     -> {"insulin":{"$gte":1}}      (rounded down)
NEW treatments find[insulin][$gte]=1.5     -> {"insulin":{"$gte":1.5}}
OLD treatments find[duration][$gte]=30     -> {"duration":{"$gte":"30"}}  (string vs number field)
NEW treatments find[duration][$gte]=30     -> {"duration":{"$gte":30}}
```

Against the `mingo` oracle (D8) on `[{_id:1,sgv:100},{_id:2}]`:

```
$exists:true    -> [1]      $exists:"true"  -> [1]
$exists:false   -> [2]      $exists:"false" -> [1]      <-- see §9.1
$exists:NaN     -> [2]      $exists:0       -> [2]
```

Non-vacuity: the oracle distinguishes the branches — `NaN` and `"false"` give different
answers — so it is not vacuously agreeing.

Why minor and not patch: a filter that returned `[]` on a database full of temp basals now
returns rows. A dashboard that plotted nothing now plots. A decimal bound that included
1.0-unit boluses now excludes them. These are answers, and they changed. The branch's own
CHANGELOG already says so in operator language, including the safety-relevant sentence
that earlier results may have under- or over-reported delivered therapy — that sentence
must survive into the release notes verbatim.

Why not major: no operator action is required, no configuration breaks, and stored data is
untouched. A report built on a broken filter needs re-running, which is a release-note
matter, not a migration.

### 3.3 `bf/cache`, `bf/merge`, `bf/parms` — patch

`bf/cache` is the cleanest patch in the programme: identical bytes on the wire, less
copying behind them. Note that `4f86bab1` is recorded as **gate not met** (3.747 ms →
2.657 ms against a <1 ms gate), which is a *shipping* decision, not a *numbering* one. A
change can be a patch and still not be ready.

`bf/parms` carries one ⚖: `queryParms` no longer turns `_` into a space. A bookmarked
report URL that relied on that decoding renders differently. I still call it patch — the
old decoding was applied inconsistently and the server never agreed with it — but it
belongs in the release notes.

### 3.4 `bf/auth` — the brief's premise is right, and incomplete

The brief says: *a code fix does NOT invalidate tokens already written, because the token
is deterministic in `_id`, name and the enclave key.* **Confirmed by reading
`reload()`** — `digest`, `accessToken` and `accessTokenDigest` are all recomputed from
`subject._id`, `subject.name` and the enclave key on every load, and the new code deletes
any stored copy before deriving them. Existing tokens keep working. Rotation is the
operator's action, on the operator's schedule. That is correctly **not** a major.

But two other things in the same branch are surfaces:

**The storage allow-list (major).** `save()` and `create()` now build the document from
`['name','roles','notes','created_at']` only. For the derived token fields this is the
whole point. For anything else it is unbounded data loss on an edit: a third-party
administration tool that has been storing, say, an owner tag or an expiry hint on a
subject document will find it gone the next time anyone touches that subject in the admin
UI, with no error. I recommend either narrowing the deletion to
`DERIVED_SUBJECT_FIELDS` and leaving unknown fields alone, or keeping the allow-list and
calling the release major. As it stands the branch is major.

**The throttle move (minor).** The old code keyed the delay on `getRemoteIP(req)`, which
`forwarded-for` computes without a proxy whitelist — so it is whatever the caller wrote in
`X-Forwarded-For`, `X-Real-IP` or `Fastly-Client-IP`. A caller that varies the header was
never throttled. The new code keys on the socket peer, which the caller cannot vary, plus
a salted digest of the credential. The ⚖ is the shared-proxy case: behind Heroku, nginx or
Cloudflare every client shares one peer address. The branch handles this correctly — the
`sleep` moved out of the request path and onto the failure path, and requests with no
credential at all are never throttled — so **no request that authenticates is ever
delayed by somebody else's failures.** That is what keeps it minor rather than major. It
is worth a reviewer re-deriving that for themselves, because it is the whole argument.

Note also that `delaylist`'s exported functions changed signature from `(ip)` to
`(keys)`. Nothing outside `lib/authorization` calls them today, but if any deployment
patches this module, that is a break.

### 3.5 `?count=0` — restricting a previously-accepted input

This is the classic case and it deserves the argument rather than a verdict.

**The case for patch.** `?count=0` never did what it says. A client asking for zero
documents received the entire collection. No client can have *wanted* that, so no client
is relying on it; fixing it restores the documented meaning of the parameter. `0x10`,
`1e2`, `2.5` and `-3` are the same: every one returned a number of documents unrelated to
what was asked.

**The case for minor.** It is a new 400 on inputs that previously returned 200. A response
code changed for a reachable input. That is observable, so not a patch — but nobody has to
*do* anything, so not a major either.

**The case for major, which is where I land.** Three things push it over.

1. **A client that computes its count can reach zero.** "Fetch the last *N* entries I
   don't already have" is exactly how a caching uploader or a sync tool is written, and
   *N* is zero whenever it is up to date. Today that client gets the whole collection —
   wasteful, slow, but a 200 with data. Tomorrow it gets a 400. If it treats 400 as fatal
   it stops syncing. **For a Nightscout user the symptom of a sync tool stopping is that
   their glucose data stops arriving**, which is a data-availability failure for someone
   managing diabetes. That is the same class of harm the programme already agreed to slow
   down for in cut 4.
2. **The blast radius is the whole v1 app, including writes.** §0.5. The middleware runs
   before every router. A POST that carries a stray `count` in its query string now fails.
   That is not what the CHANGELOG describes.
3. **There is no deprecation window.** Nothing warns first.

The counter-argument is genuinely strong and I do not want to bury it: an unbounded
collection download is itself a denial-of-service against the operator's own database, and
leaving it in place to protect a hypothetical client has a cost too. **A reviewer could
reasonably overrule me here.** If the project wants this as a minor, the cheapest way to
earn it is to log-and-clamp rather than reject: treat `?count=0` as the endpoint's default,
emit a deprecation warning naming the offending value, and return 400 one release later.
That is a minor by any reading and it closes the unbounded-download hole immediately.

Note the asymmetry with row #18: v3's `?limit=` **already** has a documented 400 path and
a documented `API3_MAX_LIMIT` ceiling. `?limit=0x10` was escaping a ceiling that the API
contract says exists. Restoring a documented bound is not the same act as inventing one.

### 3.6 Phase 0 as a release

If Phase 0 ships as one thing, it is a **major**, on three rows: the Alexa locale removal
(#8), the subject-storage allow-list (#10) and the `?count=` restriction (#17).

That is an expensive number for a set of changes that is overwhelmingly "things that were
broken now work". The cheaper path is to split:

- **15.1.0** — rows 3, 4, 5, 6, 7, 9, 11, 12, 13, 14, 15, 16, 18, 19 and the connect pin.
  Everything an operator gains, nothing they must react to beyond reading the notes.
- **The next major** (§5.6 puts that at 16.0.0, the runtime release) — rows 8, 10, 17,
  each preceded by its own deprecation step:
  a `Deprecation` response header and a log line for `?count=0`; a release that *warns*
  before the subject allow-list drops fields; an Alexa/Google Home release note that says
  the locale is now the server's.

This mirrors the decision already adopted for the cuts — hold the one that breaks things,
ship the rest — and it is the same reasoning applied one level down.

---

## 4. The 15.0.9 candidate, as it stands on `dev`

234 commits, 121 files, +8,285/−1,057, most of it new tests.

**Does the D3 upgrade alone force a minor or major?** By itself: **neither, quite.** D3
5.16 → 7.9 is two majors of a **client-side charting library**. None of S1–S7 moves: no
endpoint changes, no env var, no schema, no runtime floor, no ingestion path, no new
emission. If the charts render identically it is invisible to the contract.

The problem is the "if". D3 v6 renamed the event system (`d3.event` is gone, handlers take
the event as their first argument) and v7 continued the module reshuffle, and the upgrade
reaches `lib/client/renderer.js` (+52/−), `lib/plugins/cob.js` (+122/−) and
`lib/client/chart.js`, with **no real-browser coverage on `dev`** (cut 1 is where
Playwright arrives). So the honest statement is: *the version number is not what is wrong
with shipping D3 here; the absence of browser coverage is.* A major version number would
not make an untested chart render correctly, and a patch number does not make it render
incorrectly. **Do not let the semver argument substitute for the browser test.**

**But 15.0.9 cannot be a patch anyway**, for reasons independent of D3 — and I do not
think these have been noticed:

1. **Two new environment variables.** `lib/server/env.js` gains `DEBUG_LOGGING` and
   `CONNECT_DEBUG`. S3 grew. New configuration keys are the textbook minor.
2. **Logging is off where it was on.** `debug.logging` defaults to `false`. Log lines an
   operator relies on when diagnosing a problem are no longer there unless they opt in.
   This is the mitigation described in the brief, and it is a behaviour change in an
   operator-facing surface.
3. **A new API surface file**, `lib/api2/loop-notification-errors.js` (+82), alongside
   changes to `lib/api2/notifications-v2.js`.
4. **The connect pin moves to `234d47c8`**, an untagged commit on an unmerged feature
   branch — which changes the connector under every operator who uses it.

**What I would call it: `15.1.0`.**

And I would attach two conditions that are about shipping, not numbering:

- **Answer the D3 question with a browser, not with a version number.** Either land the
  Playwright coverage from cut 1 first, or have a human open the chart and the COB pill on
  a real deployment and say so in the PR.
- **Move the connect pin to the `v0.0.14` tag** (that is what `bf/connect-pin` does),
  because `234d47c8` is the one pin in flight that has the logging narrowing *without* the
  redaction (§0.2), and because pinning a release to an untagged SHA on an unmerged branch
  is not a reproducibility story anyone can audit.

---

## 5. The five cuts

A reminder that shapes everything here: **all five cut tips carry
`"version": "15.0.9"` in `package.json`** — the same string as the release candidate. As
the tree stands, the entire modernization stack is labelled a patch release of 15.0.8, and
labelled *identically* to a different release. That is measured, not inferred:

```
origin/dev                            15.0.9  engines.node ">=20.x"
origin/chore/retire-jsdom             15.0.9  engines.node "^22.23.2 || ^24.20.0"
origin/chore/build-runtime-separation 15.0.9  engines.node "^22.23.2 || ^24.20.0"
origin/chore/compose-mongodb6         15.0.9  engines.node "^22.23.2 || ^24.20.0"
origin/chore/mime-exposure-review     15.0.9  engines.node "^22.23.2 || ^24.20.0"
origin/chore/nightscout-modernization 15.0.9  engines.node "^22.23.2 || ^24.20.0"
```

Two artefacts claiming to be `15.0.9` with different Node floors is a supportability
problem independent of semver: an operator reporting "15.0.9 won't start" cannot be
triaged from the version string.

### 5.1 Cut 1 `chore/retire-jsdom` — **major**

*Is an application's runtime floor a major?* For a library, `engines` is advisory and npm
merely warns. For an application, **it is the first thing an operator experiences**, and
here it is enforced with `process.exit(1)`.

Concretely, after cut 1 an operator on Node 20 — the version that is the *default* on
several one-click Nightscout hosts and the one `engines` has nominally required — starts
their deployment and gets:

```
ERROR: Node v20.x.x is not supported. Nightscout requires Node ^22.23.2 || ^24.20.0.
```

and no site at all. Not a degraded site, not a warning banner: no Nightscout. For someone
whose family member's glucose data flows through that deployment, that is the most
operator-visible change any of these branches makes. If that is not a major then the
category has no content.

Three aggravations from §0.3 that a reviewer should weigh separately:

- The floor moves from the **enforced** 16, not the **declared** 20, so the jump is larger
  than the `engines` diff suggests.
- `^22.23.2 || ^24.20.0` is a whitelist, so it excludes future Node majors too. Node 26
  LTS will not start Nightscout until someone edits `package.json`. That is a maintenance
  obligation created by the format, and a floor written `>=22.23.2` would not create it.
  **Recommend `>=22.23.2` unless there is a known incompatibility with an odd major**, in
  which case say which.
- MongoDB 4.4 leaves CI in the same branch. Nothing in the code refuses 4.4, but the
  project stops testing it, so the supported-database statement changes silently.

### 5.2 Cut 2 `chore/build-runtime-separation` — **minor** ⚖

159 commits, 60 production files, +923/−465. No declared surface in S1–S7 moves.

The ⚖ is **S2**. Page bundles, a narrowed D3 import surface, a new event bus and a
reordered boot sequence are exactly the things a third-party plugin reaches into. Nightscout
plugins are not a versioned API — they are files in `lib/plugins/` and, for the
adventurous, a fork — so "the plugin interface" is really "whatever the plugins happened to
touch". I cannot measure the break without a corpus of third-party plugins, and I do not
have one. **Minor, flagged**, with a recommendation that the release note name the boot
sequence and the event bus as things a forked deployment should re-test. If the project
has any inventory of community plugins, running them is worth more than this paragraph.

### 5.3 Cut 3 `chore/compose-mongodb6` — **minor**

MongoDB Node driver 5 → 7, jQuery UI, compose default `mongo:5.0.32` → `6.0.27`.

I expected this to be a major on the database surface and the measurement says otherwise.
The CI matrix on this branch runs **5.0.32, 6.0.27, 7.0.40 and 8.0.29**, so coverage is
added, not removed. The compose file's image is the bundled *development* default; an
operator pointing `MONGODB_URI` at their own cluster is unaffected by it.

What makes it minor rather than patch: driver 7 changes result shapes in places
(`insertOne` and friends), and the storage layer has to be right about them. Combined with
cut 5 as the adopted plan proposes, the dependency release is minor overall.

### 5.4 Cut 4 `chore/mime-exposure-review` — **major**, and sharper than described

The brief calls this the clearest major candidate. It is, and the measurement found three
things worse than "two ingestion paths are deleted".

**(a) Every MMCONNECT operator's entire site stops working, not just MiniMed ingestion.**
I executed the shipping shim from the branch:

```
MMCONNECT only, no CONNECT_COUNTRY_CODE ->
  {"migrated":false,"error":"The legacy MiniMed mmconnect bridge was retired in
   Nightscout 15.0.9. Set CONNECT_COUNTRY_CODE to the two-letter country where the
   CareLink account was created ... The country cannot be inferred from MMCONNECT_SERVER."}
with countryCode -> {"migrated":true}  connect={source:'minimedcarelink',...,carelinkRegion:'eu'}
```

`setupConnect` pushes that error onto `ctx.bootErrors`, and `lib/server/app.js:202` then
installs `app.get('*', bootErrorView)` and returns, while `lib/server/server.js:61` returns
before websockets are set up. So the deployment serves **the boot-error page for every
route** — no API, no sockets, no charts, no data. An operator who upgrades without reading
release notes does not lose MiniMed data; they lose Nightscout.

The requirement is unavoidable by design: the shim states that the country cannot be
inferred from `MMCONNECT_SERVER`, so **there is no configuration in which this migration
is automatic.** Every one of these operators must set a new environment variable by hand.

**(b) Running both legacy bridges at once becomes impossible.** Executed both shims in the
order `bootevent.js` calls them, for an operator with `BRIDGE_*` and `MMCONNECT_*` both
configured:

```
bridge step    -> {"migrated":true,"legacy":false}       (sets connect.source='dexcomshare')
mmconnect step -> {"migrated":false,"error":"... MMCONNECT credentials cannot run alongside
                   a different CONNECT_SOURCE ..."}
```

Same total outage. Today both plugins run side by side as independent boot stages; after
cut 4 there is one `CONNECT_SOURCE` and the second source has nowhere to go. This is a
**capability removal** — concurrent multi-source CGM ingestion — that is not in any
summary of the cut, and the error text's suggested remedy ("migrate to a separate
uploader") is an unbounded amount of work for a family.

**(c) `DEXCOM_BRIDGE_USE_LEGACY` becomes silently inert.** Cut 4 deletes `bridgeUseLegacy`
from `bridge-connect-compat.js` entirely and deletes the log line that mentioned it. So an
operator who set that variable *because dev's own deprecation warning told them to* gets
Connect instead of the legacy bridge, with no message of any kind. Dexcom data keeps
flowing — I checked, the credentials are migrated unconditionally — so this is not an
outage. It is a configuration key that is accepted and ignored, which is its own small
defect (§9.2).

**Does a deprecation path exist in code today?** §0.4: Dexcom yes, MiniMed no. The plan to
precede cut 4 with a deprecation release is therefore right and **the deprecation release
has real work in it for MiniMed**, not just a warning string:

1. Ship `mmconnect-connect-compat.js` **without** deleting `lib/plugins/mmconnect.js`.
2. When `MMCONNECT_*` is set and `CONNECT_COUNTRY_CODE` is not, print a warning naming
   the variable and **keep running the legacy plugin**. Do not push a boot error.
3. When both `BRIDGE_*` and `MMCONNECT_*` are set, warn that a future release supports one
   `CONNECT_SOURCE`, and name the date.
4. Keep `DEXCOM_BRIDGE_USE_LEGACY` working, or warn loudly that it is now ignored.
5. Only then delete, in a release numbered major.

One more thing the reviewer must fix regardless of sequencing: both shims' error strings
say *"retired in Nightscout 15.0.9"*, and on the adopted train **15.0.9 does not retire
anything** — it is the bug-fix release. An operator who reads that message and then checks
their release notes finds a contradiction. The string must name whatever version actually
deletes the plugins, and the deprecation warnings must name the same one.

### 5.5 Cut 5 `chore/nightscout-modernization` — **major** ⚖

Express 4 → 5 and Helmet 4 → 8 are the two that carry it. Express 5 changes path-matching
syntax, drops several deprecated signatures and changes how rejected promises reach error
handlers; anything that mounts a route or a middleware — which is what a Nightscout plugin
does — sits directly on that. Helmet 8 changes the default response headers, which an
embedding page or a mobile client can observe.

The ⚖ is that I am classifying from dependency majors and a 36-file production diff, not
from a measured break. If someone runs the suite plus a browser pass and nothing in S1–S7
moves, **minor** is defensible. Given the train puts 3+5 together as a dependency release,
and given that cut 1 has already forced a major, the practical answer is that cuts 1–5
land inside one **16.x** line and the cost of this particular judgement is low.

### 5.6 Suggested numbering for the adopted train

| Release | Contents | Number |
|---|---|---|
| Bug-fix release | `dev` + the safe Phase 0 rows (§3.6) | **15.1.0** |
| Deprecation release | MiniMed + Dexcom deprecation work from §5.4, no deletions | **15.2.0** |
| Runtime release | Cut 1 | **16.0.0** |
| Build release | Cut 2 | **16.1.0** |
| Dependency release | Cuts 3 + 5 | **17.0.0** (or 16.2.0 if §5.5 resolves to minor) |
| Ingestion retirement | Cut 4 | **18.0.0** |
| Deferred breaks | Rows 8, 10, 17 from §3.6 | fold into the nearest major |

Cut 4 is last because the adopted plan holds it back; its number follows from wherever it
lands, not from its position here.

---

## 6. `nightscout-connect` 0.0.13 → 0.0.14

`v0.0.13` = `b394411`, `release/v0.0.14` = `649a7de` (annotated tag `v0.0.14`, fast-forward
from v0.0.13 — verified). 29 files, +1,362/−312, of which 887 lines are new tests.

### What actually changes for a caller

Measured by executing `lib/backoff.js` from `c1cce2a` against a transcription of the old one:

| attempt | old (ms) | new, `jitter:'none'`, `interval_ms=150000` | new, with `builder.js`'s `max_interval_ms` |
|---:|---:|---:|---:|
| 1 | 256 | 150,000 | 150,000 |
| 2 | 768 | 450,000 | 450,000 |
| 3 | 1,792 | 1,050,000 | 1,050,000 |
| 5 | 7,936 | 4,650,000 | 1,800,000 |
| 10 | 261,888 | 153,450,000 | 1,800,000 |
| 20 | 268,435,200 | 157,286,250,000 | 1,800,000 |

- Ratio at attempts 1–5: **585.94× exactly** at each, i.e. `150000/256`. The brief's 586×
  is confirmed and it is a constant, not an average.
- Uncapped attempt 20 is **4.99 years**, which confirms why the precedence fix could not
  ship alone.
- `lib/builder.js` supplies `max_interval_ms: expected_data_interval_ms * 6` = 1,800,000 ms,
  so the shipped ceiling is **30 minutes**, not five years.
- With the new default `'equal'` jitter, 2,000 samples at attempt 10 fell in
  [900,351 ms, 1,799,757 ms] — i.e. [15 min, 30 min], exactly `K/2 + U(0, K/2)`.
- `backoff({jitter:'wild'})` now **throws** `backoff: unknown jitter mode "wild"`. It
  previously accepted anything.

Five caller-visible API changes, then: option precedence reversed, a new option
(`max_interval_ms`), a changed default (`use_random_slot:false` → `jitter:'equal'`), a new
throw, and a return value that is now non-deterministic where it was deterministic.

### What number is right under 0.x

The spec says of `0.y.z` only that "anything MAY change at any time; the public API SHOULD
NOT be considered stable." Read literally, `0.0.14` is permitted. That reading also makes
the version number carry no information, which is the opposite of what a version is for.

The convention the ecosystem actually applies to `0.y.z` — and which npm's own range
operators encode, since `^0.1.0` admits `0.1.z` but not `0.2.0` — is that **`y` is the
major and `z` is the minor/patch**. Under that convention this release is a `y` bump:
reversed option precedence, a changed default, and a new exception on input that was
previously accepted are each independently breaking for a caller.

**Recommendation: `0.1.0`, not `0.0.14`.** ⚖

The reasons are practical as much as doctrinal:

1. **It makes the change legible in one glance.** The consumer is
   `cgm-remote-monitor`'s `package.json`, and the human reviewing that PR is the only gate.
   `0.0.13 → 0.0.14` reads as "a fix"; it is a 586× change in how often the connector talks
   to a vendor. `0.1.0` makes the reviewer stop.
2. **It costs nothing.** `^0.0.13` matches only `0.0.13` exactly, and cgm-remote-monitor
   pins by tarball URL anyway (§0.1), so **no consumer's resolution changes** whichever
   number is chosen. There is no upgrade to break.
3. **The behaviour is the safety-relevant part.** "Retries are 586× slower" is the correct
   summary for a Nightscout release note, and it must be written in plain language:
   *after a vendor outage, glucose readings may take longer to start arriving again than
   they used to, because the connector now waits the interval its authors configured
   instead of retrying every quarter-second. The old behaviour retried far too fast to
   succeed and could get a whole pool of users rate-limited together.*

The counter-argument, which I do not find persuasive but which is real: pre-1.0 packages
routinely stay on `0.0.z` until a `1.0.0`, and moving to `0.1.0` invites the question of
what `0.2.0` will mean. If the project prefers to stay on `0.0.z`, then the release **must**
carry a `BREAKING` section in its notes, because the number will not carry it.

Either way, hold the line already taken on `package-lock.json`: leaving it on the old SHA
so `npm ci` fails loudly is correct, and a locally invented integrity hash would break
`npm ci` for everyone. Regenerate with `npm install` after the tag is pushed, in the same
PR.

---

## 7. Proposed semver policy

### 7.1 The decision procedure

Answer in order and stop at the first **yes**.

**Is it a MAJOR?**

1. Does a supported deployment that starts today fail to start, or start into an error
   page, after the upgrade without an operator changing something? *(Node/MongoDB floor,
   a new required environment variable, a boot error.)*
2. Does any path an operator's data flows in on — CGM, pump, uploader, connector, API
   write — stop working, or require reconfiguration to keep working?
3. Is a capability removed: an endpoint, a documented parameter's effect, an ingestion
   source, a configuration key's meaning, the ability to run two things at once?
4. Does an input a real client sends, and that today returns 2xx, now return 4xx or 5xx?
5. Does an operation that is not a delete lose stored data?
6. Does an existing credential, token or session stop working?

**Is it a MINOR?**

7. Does the set of alarms or notifications the deployment can emit change — anything new,
   anything louder, anything that could not fire before?
8. Is something added: an endpoint, a response field, a configuration key, an accepted
   input, a plugin?
9. Does a query, report, count or list return a **different set of records** than before
   for the same request — including empty becoming non-empty?
10. Does a default change, including logging verbosity and retry timing?
11. Does a dependency that renders, charts, styles or serves anything the operator sees
    move by a major?

**Otherwise it is a PATCH**, and the claim being made is: *for every input a supported
client actually sends, the bytes on the wire and the emissions from the deployment are the
same as before.* If a reviewer cannot say that sentence out loud about the diff, it is not
a patch.

Three standing rules that override the ladder:

- **Question 7 is never waived.** An alarm is a contract with a person.
- **"It was a bug" is not a defence at any level.** Correctness decides whether to ship;
  observability decides the number. They are different questions and a fix can be a major.
- **A release is classified by its loudest change, not its median.** One major row makes
  the release major. The remedy is to split the release, not to round the number down.

### 7.2 Reviewer checklist for a PR

Paste into the PR template. Every box is answerable from the diff in a few minutes.

```
## Semver impact

Surfaces touched (tick all):
[ ] S1 HTTP API v1 / v3 request or response contract
[ ] S2 plugin interface, boot sequence, or client event bus
[ ] S3 environment-variable configuration surface
[ ] S4 database schema, stored document shape, or index
[ ] S5 Node or MongoDB runtime floor (engines, CI matrix, runtime-policy)
[ ] S6 an ingestion path (bridge, mmconnect, connect, uploader, API write)
[ ] S7 the set of alarms or notifications that can be emitted
[ ] none of the above

Required answers:
- Does anything that boots today fail to boot after this?          yes / no
- Does any request that returns 2xx today return 4xx/5xx after?    yes / no
  If yes, name a real client that sends it, or say none exists.
- Does any request return a DIFFERENT SET of records?              yes / no
- Can an alarm or notification fire that could not fire before?    yes / no
- Does any default change (logging, retry, limit, sort, units)?    yes / no
- Does any stored document lose a field on a non-delete write?     yes / no
- New env var, or existing one whose meaning changes?              yes / no
- Any env var now accepted and ignored?                            yes / no
- Dependency major bump reaching anything an operator sees?        yes / no

Proposed: [ ] patch  [ ] minor  [ ] major
Evidence for the "no" answers (a test name, a diff line, or a transcript):

Non-vacuity: name one check in this PR, say how you broke the code under it,
and confirm the check failed.

Deprecation (required if MAJOR):
[ ] the previous release warns about this, naming the setting and the version
[ ] or: no warning is possible, and here is why:

Operator-facing release note (required if MINOR or MAJOR):
[ ] drafted, in plain language, jargon defined
[ ] every safety-relevant caveat preserved; no algorithm behaviour simplified
[ ] says what the operator must do and by when
[ ] no individualised dosing advice; suggests the care team where relevant
```

### 7.3 Where current practice departs from this policy

Measured, not asserted. Each row is a concrete thing a reviewer can check today.

| # | Departure | Evidence |
|---|---|---|
| D-a | **The version number is not moved at all.** All five cut tips and `dev` carry `15.0.9`, including the branch that changes the Node floor and the branch that deletes two ingestion paths | §5, measured from six `package.json` files |
| D-b | **Two different artefacts claim the same version.** `dev` (15.0.9, Node ≥20) and cut 1 (15.0.9, Node ^22.23.2\|\|^24.20.0) are both "15.0.9" | §5 |
| D-c | **A patch number carries a two-major client dependency upgrade with no browser coverage** | §4, D3 5.16 → 7.9 |
| D-d | **New environment variables ship under a patch number.** `DEBUG_LOGGING` and `CONNECT_DEBUG` are new on `dev` | §4, `lib/server/env.js` diff |
| D-e | **Deprecation warnings name a version that does not do the thing.** Both cut-4 shims say "retired in Nightscout 15.0.9"; on the adopted train 15.0.9 retires nothing | §5.4, executed |
| D-f | **A deletion ships in the same release as its migration shim.** `mmconnect-connect-compat.js` is born in the branch that deletes `mmconnect.js` | §0.4 |
| D-g | **A previously-documented escape hatch is removed without a word.** `DEXCOM_BRIDGE_USE_LEGACY` is silently ignored in cut 4, and dev's own warning tells operators to set it | §5.4(c) |
| D-h | **Release dependencies are pinned to untagged commit SHAs on unmerged branches**, so what an operator gets cannot be named | `dev` → `234d47c8`, cut 4 → `c962a13f`, cut 5 → `b77e5bb` |
| D-i | **There is no PR field for semver impact**, so classification is nobody's job at the moment it is cheapest | §7.2 exists to close this |
| D-j | **Nothing enforces the number.** No CI check compares the diff's surfaces against the version bump | see §7.4 |

The governance finding from the release-readiness review is what makes all of this matter
rather than being bookkeeping: 495 stack commits with one author, 100 child PRs self-merged
with zero human reviews, and release PR #8598 and integration PR #8605 each carrying zero
human reviews. **When there is no second reader, the version number is the only signal an
operator gets about how carefully to upgrade.** A patch number on a release that changes
the Node floor is not a labelling error in that situation; it is the whole of the warning,
missing.

### 7.4 One mechanical check worth building

The policy above is a discipline, and disciplines decay. The cheapest enforcement, in the
house style of "emit, then check the emission":

A CI job that, for a PR against a release branch, computes which of S1–S7 the diff touches
by path and by pattern — `engines` in `package.json`, `readENV` calls in
`lib/server/env.js`, files under `lib/api/` and `lib/api3/`, `levels.URGENT` and
`sendNotification` assignments, the CI matrix — and **fails if the version bump is smaller
than the surfaces imply.** It cannot detect everything and it will need an explicit
override label for the cases it gets wrong. It would have caught D-a, D-b and D-d on this
tree without a human looking.

**Non-vacuity requirement for whoever builds it (house rule 2):** it must be demonstrated
by taking cut 1 as it stands — `15.0.9` with `engines.node` changed — and confirming the
check fails. A check that has only ever passed is not evidence.

---

## 8. Index of judgement calls

Restated so a reviewer can overrule them individually. This project's convention is that
judgements are marked as such.

| § | Judgement | If overruled |
|---|---|---|
| 3.5 | `?count=0` → 400 is **major** | The strongest counter-argument in the document. If minor, prefer the clamp-and-warn path in §3.5; Phase 0's classification is unaffected because #8 and #10 still carry it |
| 1 | **S7 (alarms) is a first-class surface** | If alarms are not a surface, `bf/alarms`'s URGENT fix is a patch and row 6 moves down |
| 3.1 | The Alexa/Google Home locale removal is **major** | Defensible as minor: the old behaviour was globally harmful and arguably never worked as documented |
| 2 #1 | `bf/connect-pin` is **minor** although it is one line | A one-line pin bump carrying a 586× behaviour change is the case for classifying by what an operator gets, not by diff size |
| 2 #5 | `bf/parms` is **patch** although `_`-decoding changes | If bookmarked report URLs count as a surface, minor |
| 2 #15 | v3 `_id` tiebreak is **patch** | If tie order counts as a contract, minor |
| 2 #18 | v3 `?limit` restriction is **minor**, unlike #17 | Rests on v3's limit being a documented closed contract with an existing 400 path |
| 5.2 | Cut 2 is **minor** | Unmeasured against third-party plugins. A plugin corpus would settle it |
| 5.5 | Cut 5 is **major** | Classified from dependency majors, not a measured break. A browser pass could make it minor |
| 6 | connect should be **0.1.0** | Literal 0.x semver permits 0.0.14. If 0.0.14 is kept, a `BREAKING` section in the notes is mandatory |
| 5.6 | The whole numbering table | One consistent scheme among several; the orderings matter more than the numbers |

---

## 9. New defects found, proposed for the register

No ids allocated (house rule 3). A later agent assigns them by reading the register's
highest id at the moment it writes.

### 9.1 `find[field][$exists]=false` is inverted by `bf/coercion` on the five previously-walked fields

**Where:** `externals/work/crm-bf-coercion/lib/server/query-coercion.js:90` (`isValueLeaf`)
with `lib/server/query.js:288`.

`isValueLeaf` returns `false` for `$exists`, so the operand is left exactly as the query
string delivered it — the **string** `"false"`. A non-empty string is truthy, so MongoDB
reads `$exists: "false"` as `$exists: true`. Confirmed against the `mingo` oracle (D8) on
`[{_id:1,sgv:100},{_id:2}]`:

```
$exists:"true"  -> [1]     (correct)
$exists:"false" -> [1]     (WRONG: returns documents that HAVE the field)
$exists:NaN     -> [2]     (what master does today, accidentally correct for =false)
```

So for `sgv`, `date`, `insulin`, `carbs` and `glucose` — the five fields the old
hand-written walker covered — `$exists=false` works today by accident (`NaN` is falsy) and
**stops working after `bf/coercion`**. For every other field the string already arrived
untouched, so `$exists=false` is *already* wrong on master and dev today.

This does not change my minor classification of `bf/coercion`: it replaces one wrong answer
with a different wrong answer on five fields, and it fixes the far more commonly used
`=true` form. But it is a regression on those five and it is trivially fixable — map the
`$exists` operand through a boolean reader that understands `"false"`, `"0"` and `""`, in
the same place `isValueLeaf` already special-cases the operator. `tests/query.test.js:138`
covers `$exists=true` only; the `=false` case is untested.

**Severity: medium.** Client-reachable on v1, returns the opposite record set, silently.
**Ships to operators today: yes** — in the broad form (every field outside the five), it is
already on master.

### 9.2 Cut 4 accepts `DEXCOM_BRIDGE_USE_LEGACY` and silently ignores it

**Where:** `origin/chore/mime-exposure-review:lib/server/bridge-connect-compat.js`
(the `bridgeUseLegacy` function is deleted) with `lib/server/bootevent.js:51-57` (the
`result.legacy` log line is deleted).

Dev's own deprecation warning instructs operators to set `DEXCOM_BRIDGE_USE_LEGACY=true`.
After cut 4 that variable is read by nothing. Dexcom ingestion continues via Connect — I
verified the credentials are migrated unconditionally — so this is not a data-availability
failure, but the operator's expressed intent is discarded with no message. Either honour it
with a clear "no longer supported" error, or log that it is ignored.

**Severity: low. Ships to operators today: no** — cut 4 only.

### 9.3 Cut 4 turns a missing `CONNECT_COUNTRY_CODE` into a total site outage for every MMCONNECT operator

**Where:** `origin/chore/mime-exposure-review:lib/server/mmconnect-connect-compat.js`
with `lib/server/bootevent.js:325-340`, `lib/server/app.js:202`, `lib/server/server.js:61`.

Executed: an operator with `MMCONNECT_USER_NAME`/`MMCONNECT_PASSWORD` and no
`CONNECT_COUNTRY_CODE` gets `{migrated:false, error:...}`; the error is pushed to
`ctx.bootErrors`; `app.js` then serves the boot-error view for `*` and `server.js` skips
websocket setup. The whole deployment is down, not just MiniMed ingestion. The same happens
to any operator running `BRIDGE_*` and `MMCONNECT_*` together, which works today.

The shim itself states the country cannot be inferred, so **no MMCONNECT operator can
upgrade without manual reconfiguration**. There is no release in which they are warned
first (§0.4).

Whether this is a defect or an intended hard stop is a maintainer decision. Either way the
sequencing consequence is fixed: a deprecation release must ship the shim *without* the
deletion, warn and keep running.

**Severity: high. Ships to operators today: no** — cut 4 only, which is the cut the plan
already holds back. That is the right call and this is the measurement supporting it.

### 9.4 `bf/auth`'s storage allow-list silently drops any field it does not know

**Where:** `externals/work/crm-bf-auth/lib/authorization/storage.js`, `SUBJECT_FIELDS` /
`ROLE_FIELDS` with `ownedFields()` in `create()` and `save()`.

Keeping the derived token fields out of the database is correct and is the point of the
commit. But the allow-list is applied to the *whole* document, so any field a third-party
administration tool has stored on a subject or role is discarded on the next edit, with no
error and no log line. The narrower fix — delete only `DERIVED_SUBJECT_FIELDS` and pass
everything else through — achieves the security goal without the data loss.

**Not reproduced against a real deployment**; identified by reading the diff, and I have no
inventory of tools that write to these collections. Flagging it as unsettled rather than
confirmed.

**Severity: unsettled. Ships to operators today: no** — `bf/auth` is unlanded.

### 9.5 Six `package.json` files claim to be version 15.0.9

**Where:** `origin/dev` and all five `chore/*` cut tips.

Not a code defect; a supportability one. An operator reporting a problem with "15.0.9"
cannot be triaged, because the string covers artefacts with different Node floors and,
in cut 4's case, different ingestion paths. Fixing it is free and should happen before any
of these branches is tagged.

**Severity: medium. Ships to operators today: no** — but it ships the moment any of these
is released under its current number.

---

## 10. What a reviewer should verify before acting on this

This is a draft for maintainer decision, not a decision.

1. **§3.5 is the judgement most likely to be wrong.** Read the argument and the
   counter-argument and rule.
2. **§5.2 and §5.5 are unmeasured against third-party plugins.** If a plugin corpus exists
   anywhere, running it is worth more than both sections.
3. **§4's D3 conclusion is deliberately narrow**: the version number is not the risk, the
   missing browser coverage is. Do not let a number stand in for the test.
4. **§9.1 should be confirmed against a real MongoDB server**, not only against `mingo`.
   `mingo` is the project's differential oracle by D8, but `$exists` operand coercion is
   exactly the kind of thing a server and an oracle can differ on.
5. **§0.1 needs a one-line fix** to `phase0-pr-sequencing-2026-09-15.md:388`. I have not
   edited that document; it belongs to another session's work and house rule 6 means the
   fix needs a contradiction sweep across every other statement of the pin.
