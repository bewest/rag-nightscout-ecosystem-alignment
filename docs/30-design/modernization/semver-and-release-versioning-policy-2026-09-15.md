# Semver and release versioning policy — cgm-remote-monitor and nightscout-connect

*Contributor- and maintainer-facing. Full technical depth is intended. Operator-facing text
derived from this document has its own rules — §5.6.*

**Status: living document.** Two parts with different standing:

- **The release train (§8.3) is adopted** — maintainer, 2026-09-15: 15.0.9, then cut 1
  (`chore/retire-jsdom`) alone, then cut 2, then cuts 3+5 combined, with cut 4 held behind its
  own deprecation release. One open register defect, **BF-64**, bears on how step 4 is built.
- **The policy itself (§1–§7) and the numbers it proposes are a draft awaiting maintainer
  adoption.** Nothing has been renumbered, tagged or released on its strength. The queue items
  that carry the numbering decision are `RT-0` and `RT-VERSION`.

Measured facts are anchored as of **2026-09-22**: `cgm-remote-monitor` `origin/dev` =
`74fc6619` (package.json `15.0.9`), `origin/master` = `92d08342` = tag `15.0.8`, the shipping
release; master is 308 commits behind dev
(`git -C externals/cgm-remote-monitor-official rev-list --count official/master..official/dev`).
Sections that quote gate transcripts (§3.8, §6.3) were measured 2026-09-15 against the then
`origin/dev` `a8888f0d` and the `bf/*` branch tips of that date, and are labelled so.

Related: the classification draft this policy builds on,
[`gt4-semver-classification-2026-09-15.md`](../../60-research/modernization/gt4-semver-classification-2026-09-15.md)
(where the two disagree, this document is the later position);
[release readiness for 15.0.9](release-readiness-15.0.9-2026-09-22.md);
[backfix register](../remedial/nightscout-backfix-register.md) (defect facts);
[`queue/work-queue.yaml`](../../../queue/work-queue.yaml) (item state);
[execution plan §1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions)
(decisions D1–D17, cited here by number).

---

## 0. How this was measured

Reads only. No branch, tag, worktree or shipping file was created, moved or modified by this
document. The one file it added is the gate script, which is tooling in this repository
(decision D12).

| What | Where |
|---|---|
| `cgm-remote-monitor` | `externals/cgm-remote-monitor-official` — `origin/master` `92d08342` (15.0.8), `origin/dev` `74fc6619` (15.0.9 candidate), the five published `chore/*` cut tips, the locally prepared rebases `rt/cut1`…`rt/cut4` (unpushed) |
| `nightscout-connect` | `externals/nightscout-connect`, `externals/work/nc-jitter` — tag `v0.0.13` `b394411`; `official/dev` `1946beb` (package.json `0.1.0`, 2026-09-22); tag `v0.1.0-dev.1` → `1946beb`, published on npm as `0.1.0-dev.1` (`next`) |
| semver arithmetic | `semver` **6.3.1** under Node v24.15.0, resolved from the inspected repo (`package.json` declares `"semver": "^6.3.0"` on `dev` and on every cut) |
| the gate | `tools/qc/semver-surface-gate.js`, exercised in §6.3 |

**Environment-variable census method.** Variables are read through several helpers
(`readENV`, `readENVTruthy`, `readENVRaw`), so a census must match `readENV[A-Za-z]*\('NAME'`.
Measured at both refs: master 30 names, dev 32, the delta being exactly `CONNECT_DEBUG` and
`DEBUG_LOGGING`. A census restricted to `readENV(` reports no difference between master and
dev, which is the exact case the policy exists to catch.

**House rule: orderings are more durable than absolutes.** Where a number appears, the method
is named next to it.

---

## 1. What the public surface is

Semver is specified for a library: "the public API" is what other code imports. That
definition is empty for an application nobody imports, and without a substitute every
classification argument becomes unfalsifiable.

**The substitute this policy adopts:** the public surface of Nightscout is **everything an
operator, or a program an operator runs, can depend on without reading the source.** If a
reasonable person could build a habit, a script, a device integration or a care routine on it,
it is a surface.

Each candidate is argued below; the verdict is what this policy adopts.

### S1 — HTTP API v1 and v3, and the realtime socket. **IN.**

v3 is a documented, versioned, swagger-described contract with a closed 9-operator query set
(D8). v1 is undocumented in places but is what every uploader, watch face and mobile client
actually calls; "undocumented" describes the project's writing, not the client's dependency.

**The socket belongs here too.** `lib/server/websocket.js` on `dev` registers client-callable
`authorize`, `dbAdd`, `dbUpdate`, `dbRemove`, `dbUpdateUnset` and `loadRetro` (measured by
grepping `socket.on('…'` at `origin/dev`). Those are writes from third-party clients; a change to
the shapes they accept is an API change in everything but the URL.

*Counter-argument, answered:* "v1 is an open pass-through, so it has no contract to break." D8
says v1 is to be **bounded by corpus evidence**, not that it is exempt. An open surface is a wide
contract, not the absence of one.

### S2 — The plugin interface, boot sequence and client bundle. **IN, with a named limit.**

Nightscout plugins are files in `lib/plugins/`, not a published API, and forks are the normal
extension mechanism. Page bundles, a narrowed D3 import surface, a new event bus and a reordered
boot sequence (cut 2) are invisible to S1 and directly under a fork.

**In**, because a forked deployment is a supported way to run Nightscout. **The limit:** this
policy does not promise a stable plugin API. It promises that **a release that changes the boot
order, the plugin registration contract or the client event surface says so in its notes and
does not hide under a patch number** — a disclosure obligation, not a compatibility guarantee,
which is the strongest promise that can be made without a plugin corpus to test against (§10).

**Embedding the client bundle is OUT.** The bundle is served, not published; there is no npm
artefact, no documented embed API, and no evidence of anyone embedding it. A bundle change is
covered as an S2 change.

### S3 — The environment-variable configuration surface. **IN. The most-used surface there is.**

For a self-hosted application this is the primary interface: every operator sets environment
variables, and one-click hosts encode them in templates that outlive the operator's attention.

| Event | Weight | Why |
|---|---|---|
| A new variable is read | minor | Additive; nothing an operator set stops working |
| An existing variable changes meaning or default | minor at least, major if it changes what the deployment does without the operator acting | `DEBUG_LOGGING` flipping logging off is the live example |
| A variable stops being read | **major** | The operator's expressed intent is discarded, usually silently. `DEXCOM_BRIDGE_USE_LEGACY` in cut 4 is the live example, and dev's own warning text tells operators to set it (BF-62) |

**Accepted-and-ignored is the worst of the three**: it produces no error, no log line and no
failing test. The gate in §6 detects it mechanically by censusing the names read at both refs.

### S4 — The database schema and stored document shapes. **IN, with the D4 nuance.**

Operators own their MongoDB. Their data outlives every release, and third-party tools read and
write the same collections. A change that requires a migration, or that causes a write to drop a
field it previously preserved, is an S4 change.

**The D4 nuance:** the storage seam carries two mature backends permanently — MongoDB for
single-tenant, PostgreSQL for the hosted service. A divergence between the two (BF-19, BF-21,
BF-22) is a correctness defect within one version, owned by the register, not a versioning
question. **S4 is about what a release does to an operator's stored documents.**

**The event this policy calls out:** *a non-delete write that silently discards a field it did
not write.* `bf/auth`'s subject and role allow-list does this (queue `P0-C`, not merged). Data
loss on an edit is a major even when the field removed should never have been stored.

### S5 — The Node and MongoDB runtime floor. **IN, and for an application the loudest surface of all.**

*The strongest counter-argument, stated fairly:* for a library, `engines` is advisory; a library
that raises its floor has not changed its API, and many projects call that a minor.

**Why this policy rejects that for Nightscout** — three measured facts:

1. **It is enforced with `process.exit(1)`.** Cut 1 introduces `lib/server/runtime-policy.js`,
   which reads `engines.node` and exits. There is no warn-and-continue path.
2. **The floor being replaced is not the one declared.** `package.json` on master and dev says
   `>=20.x`, but `lib/server/bootevent.js` enforces `semver.satisfies(nodeVersion, '>=16.x')`.
   The *enforced* jump is from 16, not 20.
3. **The published cut-1 range is a whitelist, not a floor.** Measured with `semver.satisfies`:
   `^22.23.2 || ^24.20.0` (the range on every published cut tip, 2026-09-22) rejects 20.0.0,
   20.19.5, 21.7.3, 22.0.0, 22.23.1, 23.11.0, 24.0.0, 24.19.1, 25.0.0 and 26.0.0; `>=20.x`
   accepts all ten (18.20.4 is rejected by both). An operator on Node 22.23.1, a current 22 LTS,
   boots today and exits after cut 1, and Node 26 will not start Nightscout until someone edits
   `package.json`. The locally prepared rebase `rt/cut1` (`ed21961f`, unpushed) declares
   `^22.12 || >=24` instead, which admits 22.12+ and 24+ but still rejects 20, 21 and 23;
   whichever range ships, it is a narrowing of the enforced floor.

For a person whose family member's glucose data flows through that deployment, "it does not
start" is the largest observable change any branch in this programme makes.

**Refinement:** *narrowing* the accepted runtime range is major; *widening* it is minor. This is
mechanically decidable and the gate decides it (§6.3 runs H, H2).

**MongoDB is in this surface too.** Cut 1 drops MongoDB 4.4 from CI without any code refusing
4.4. **Policy: removing a database version from the CI matrix is a minor and must be stated in
the notes as a change to the supported set** — nothing stops working, but the support statement
moved.

### S6 — The ingestion paths an operator's data flows through. **IN, with precedence over every other surface.**

Bridge, mmconnect, nightscout-connect, uploader writes, API writes. **The symptom of an ingestion
failure is that a person's glucose data stops arriving.**

- A change that can stop ingestion is **major**, even when it is also correct, small and overdue.
- A change to a pinned connector revision is classified by **what the operator receives**, not by
  diff size. `bf/connect-pin` is `+1/-1` and carries a 585.94× change in retry timing plus three
  log-redaction fixes.
- **An ingestion removal requires a deprecation release first** (§5) — the one place where the
  number alone is not a sufficient warning.

### S7 — The set of alarms and notifications the deployment can emit. **IN.**

An alarm is a contract with a *person*, not a program. It arrives at 3 a.m. on the phone of
someone who is asleep, and its meaning is learned by repetition. A deployment that begins
emitting a persistent URGENT notification it has never emitted has changed the thing the
household has learned to trust, and no diff size makes that a patch.

**The live case** (`bf/alarms` `8714093b`, merged to dev as #8739, not released):
`lib/plugins/insulinage.js` tested `insulinInfo.age >= insulinInfo.urgent`, and `insulinInfo` is
constructed without an `urgent` key, so the comparison was `>= undefined` — false for every age,
for every operator, since the line was written. The fix makes the URGENT branch reachable at
`IAGE_URGENT` (default 72 h). **Minor**, with two effects the note must both describe (read at
`origin/dev` and on `bf/alarms`):

- **The push/Pushover alarm is opt-in and off by default.** `iage.getPrefs` sets
  `enableAlerts: sbx.extendedSettings.enableAlerts || false`; the notification is built only
  under `if (prefs.enableAlerts && sendNotification && insulinInfo.minFractions <= 20)`;
  `IAGE_ENABLE_ALERTS` defaults to `false` (README on dev, line 465). `sendNotification` is
  `insulinInfo.age === prefs.urgent`, an exact equality, so it is one shot at exactly
  `IAGE_URGENT` hours inside the 20-minute post-hour window. The sound reaches only deployments
  that set `IAGE_ENABLE_ALERTS=true`.
- **The red pill reaches everyone.** `insulinInfo.level = levels.URGENT` is assigned in
  `findLatestTimeChange` (line 96), the property producer, outside the `enableAlerts` guard;
  `updateVisualisation` reads it and sets `pillClass = 'urgent'`. On every deployment the IAGE
  pill turns urgent-red once the reservoir passes `IAGE_URGENT` hours.

S7 needs its own name rather than living inside S2 because a plugin-file rule would fire on most
edits; S7 asks one question about behaviour rather than about paths, and §6.3 shows the question
cannot be answered by grep.

### S8 — The version string itself. **IN.**

An operator, a support volunteer and a bug reporter all depend on it. Measured 2026-09-22 with
`git show <ref>:package.json`: master is `15.0.8`; **`origin/dev` and all five published cut tips
carry `15.0.9`**, with two different `engines.node` values between them (`>=20.x` on dev,
`^22.23.2 || ^24.20.0` on the cuts), and one of them (cut 4) deletes two CGM ingestion paths
(register BF-60). The string is live, not merely a file: `lib/server/env.js:137` copies it to
`env.version` and `lib/api/status.js:32` returns it, so every deployment on the dev channel
already answers `/api/v1/status` with `15.0.9`. "My 15.0.9 will not start" cannot be triaged
from the string.

**Policy: a build that is not the release its version names says so in its version string** — a
pre-release identifier is enough (§5.1).

### Candidate S9 — What the client computes and shows to a person. **Proposed, not adopted.**

See §3.8. S1–S8 read as though the browser were a rendering detail of the server; for a
self-hosted diabetes application it is the product. Adding a surface moves §2, §6 and §8
together, so it is left for the maintainer.

### Candidates argued OUT

| Candidate | Verdict | Why |
|---|---|---|
| Internal module layout, `lib/**` requires | **out** | No supported consumer; a fork requiring an internal path is covered by S2's disclosure duty |
| Log line text and format | **out as a contract**, in as a note | Promising log stability would freeze every diagnostic. Removing a log line an operator was told to look for is an S3 event |
| Performance | **out** | `bf/cache`'s 0.837 ms → 0.025 ms is not a version event unless it changes what is returned |
| Test-suite layout and CI structure | **out**, except the supported-matrix statement in S5 | Contributor-facing |
| The client bundle as an embeddable artefact | **out** | See S2. This does **not** put client *behaviour* out — see candidate S9 |
| Documentation | **out**, but a deprecation announcement is not documentation — §5 | |

---

## 2. The decision procedure

Short enough to use in review. Answer in order; **stop at the first yes.**

### MAJOR — any one of these

1. Does a supported deployment that starts today **fail to start**, or start into an error page,
   without the operator changing something? *(runtime floor, new required variable, boot error)*
2. Does any **ingestion path** stop working, or need reconfiguration to keep working?
3. Is a **capability removed or narrowed** — an endpoint, a parameter's effect, a request header
   that was honoured, an ingestion source, the ability to run two sources at once, a
   configuration key's meaning?
4. Does an input that a **real client sends**, and that returns 2xx today, now return 4xx/5xx?
5. Does an operation that is **not a delete** lose stored data, or does stored data need
   migrating?
6. Does an existing **credential, token or session** stop working?
7. Does a configuration key become **accepted and ignored**?

### MINOR — any one of these

8. Can an **alarm or notification** fire that could not fire before, fire at a different level,
   or fire louder? *(Never waivable — R2.)*
9. Is something **added**: an endpoint, a response field, a configuration key, an accepted input,
   a plugin, a supported runtime?
10. Does any request return a **different set of records**, or a differently-shaped body, for the
    same query — **including empty becoming populated, and a wrong answer becoming right**?
11. Does a **default** change: logging verbosity, retry timing, a limit, a sort order, a unit, a
    bundled image?
12. Does the **supported set** change — a database version leaving CI, a runtime being added?
13. Does a dependency that **renders, charts, styles or serves** anything an operator sees move by
    a major?

**A gap in this ladder.** Questions 1–13 are server-, HTTP- and configuration-shaped. A change
confined to what the **browser computes and shows a person** — the bolus calculator's inputs, a
pill's value, the page continuing to advance — answers "no" to every one and falls through to
patch. That is how BF-35, graded high, classifies as a patch with no release-note obligation.
**Read §3.8 before using this ladder on anything under `lib/client/`.**

### PATCH — otherwise

The claim a patch makes, which a reviewer must be able to say out loud about the diff:

> *For every input a supported client actually sends, the bytes on the wire and the emissions
> from the deployment are the same as before.*

### Four standing rules that override the ladder

- **R1. "It was a bug" is not a defence at any level.** Correctness decides *whether to ship*;
  observability decides *the number*. A fix can be a major. This is the largest departure from
  current practice. *(Where the maintainer rules that removed behaviour was itself the defect and
  never an intended capability — as for the Alexa/Google Home locale handling, §9 — question 3
  does not apply.)*
- **R2. Question 8 is never waived.**
- **R3. A release is classified by its loudest change, not its median.** One major row makes the
  release major. The remedy is to **split the release**, not to round down.
- **R4. Classify by what the operator receives, not by the size of the diff.**

### The one rule about *not* using this procedure

**A version number is not a substitute for a test.** Where this document recommends a major, it
is because operators must be warned, never because the change is risky and the number will absorb
the risk. See §3.7.

---

## 3. The hard cases this programme has produced

### 3.1 A fix that makes a query start returning rows it previously, wrongly, omitted

*The case: `bf/coercion`, merged to dev as #8737 (2026-09-18), not released.
`find[duration][$gte]=30` produced `{"$gte":"30"}` — a string compared against a numeric field —
and matched nothing; it now produces `{"$gte":30}`. `find[insulin][$gte]=1.5` produced
`{"$gte":1}` and now produces `{"$gte":1.5}`. 158 schema-driven coercions over five collections.
The same change reads `$exists` operands as booleans (`BOOLEAN_OPERANDS`/`readBooleanOperand` in
`lib/server/query.js`), which fixes BF-40. Old and new `query.js` executed side by side (GT4);
operand semantics cross-checked against the `mingo` oracle (D8).*

**Answer: MINOR. Correcting a wrong answer is a behaviour change.**

The thing an operator interacts with is the answer, not the intent. A report that plotted an
empty chart now plots a full one; somebody's saved filter changed meaning under them. **"What if
clients adapted to the wrong answer?" makes it worse, not better**: a client that compensated
(fetching wider and filtering locally) now double-filters or double-counts. Adaptation is
evidence *for* the minor.

**Where the line is:**

> Does the **set of records**, or the **shape of the body**, change for a request a client can
> send? If yes, minor. If the change is confined to internals — caching, cloning, logging, query
> plan — patch.

`bf/cache` is on the patch side (identical bytes, less copying); `bf/coercion` on the minor side.

**The safety-relevant consequence.** `bf/coercion`'s CHANGELOG says earlier results may have
under- or over-reported delivered therapy. That sentence must survive verbatim into the
operator-facing release note: a person may have looked at a total-insulin report built on a
broken filter.

### 3.2 A fix that adds restrictions — `?count=0x10` and `?count=2.5` now return 400

*The case: `bf/reads`, merged to dev as #8738 (2026-09-18) **as written**, not released. On
`origin/dev` `74fc6619`, `lib/server/count.js` `parseCount` accepts only a positive safe integer,
and `lib/api/index.js:54` returns 400 when a `count` is supplied and does not parse. `0`, `0x10`,
`2.5`, `-3`, `1e2`, `abc` and integers above `MAX_SAFE_INTEGER` now return HTTP 400. Previously
`?count=0` returned **the whole collection** (`limit(0)` is unbounded in MongoDB). The validator
is mounted on the whole v1 app before every router, so it covers `/treatments`, `/profile`,
`/devicestatus`, `/notifications`, `/activity`, `/food`, `/status`, `/alexa`, `/googlehome` and
**writes**: `POST /api/v1/treatments?count=0` now fails. (GT4 executed the new validator against
a transcription of the old `if (opts && opts.count) return this.limit(parseInt(opts.count))`.)*

**Answer: as written, MAJOR. The policy's recommended shape splits it, and both halves become
MINOR.**

> **Narrowing accepted input is MAJOR if a real client can send the narrowed input, MINOR if no
> client that could plausibly exist would send it.** The burden is on the author to name why
> nobody sends it, not on the reviewer to produce a victim.

| Spelling | Could a real client send it? | Verdict |
|---|---|---|
| `abc`, `0x10`, `1e2`, `2.5`, `-3`, `>MAX_SAFE_INTEGER` | No. Each is a typo or hand-written URL, and each silently returned a count unrelated to the request | **minor** |
| `0` | No client sends it as a literal; 9.1 % of call sites compute it, and a computed count is not bounded away from zero | **major** as written |

**The corpus measurement.**
[`seam-limit-and-projection-2026-09-14.md`](../../60-research/tenancy/seam-limit-and-projection-2026-09-14.md)
§2, from `tools/qc/v1_count_census.py`: **274 `count=` occurrences across 10 client projects —
236 literal (86.1 %), 25 computed at request time (9.1 %), 11 prose, 2 other. No client sends a
literal `count=0`**; the literal values observed are `1, 2, 3, 5, 10, 20, 24, 50, 100, 288, 500,
1000, 1500, 10000, 100000, 9999999`. The census reads client *source*, not request logs, because
there are no request logs. So the exposure is **latent, not observed**: the 9.1 % of call sites
that build the count at runtime (`'&count=' + n`), of which `oref0`, the closed loop, has four.

`?count=0` is reachable the way sync tools are written: "fetch the last *N* entries I do not
already have" evaluates to zero exactly when the client is up to date. *(An inference about how
such clients are built, supported by the 9.1 % dynamic arm; not an observation of a request.)*
Before, that client received the whole collection — wasteful, but a 200. Now it receives a 400,
and a client that treats 400 as fatal stops syncing. **For a Nightscout user, a sync tool that
stops is glucose data that stops arriving.**

**The counter-argument is strong.** `limit(0)` is an unbounded collection download — a denial of
service against the operator's own database, reachable by anyone who can read.

**The recommended resolution is to split rather than choose.** Reject the five meaningless
spellings (minor), and for `?count=0` **clamp rather than reject**: treat it as the endpoint's
default limit, return `Deprecation: true` with a `Warning` header naming the value and the
version that will start rejecting it, and log it once per process. That closes the
unbounded-download hole as completely as rejecting does, while giving the one reachable input a
warned release. **A maintainer who weighs the census more heavily can reasonably rule the whole
change minor** (§10 item 1).

**Where it stands:** the as-written version is on dev, so this is now a decision about 15.0.9's
number (§8.1). If it ships as written and the major reading stands, the release notes must name
`?count=0` and the write-path scope, which the branch's CHANGELOG does not (it lists read routes
only).

**Evidence added 2026-09-23, after 15.0.9's rule was amended by #8748.** *Reproduced end to end on
15.0.8 (`92d08342`), `dev` (`ddd9b600`) and the 15.0.9 candidate (tree `2ce67b27`), mongod 7.0.43, Node
22.23.2, each request with its well-formed control in the same run
([consumer survey](../../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md)). The decision is
recorded at the end of this addendum.* 15.0.9's rule is now: a read with
`count=0` answers an empty list; a read with any other count that is not a plain whole number answers
400; saves and updates ignore `count`; a delete with an unreadable count is refused. Two real clients
meet that rule in ways the table above did not foresee:

- **oref0, the closed loop, sends a count that is not a plain whole number.** `oref0-ns-loop.sh:242`
  calls `nightscout latest-openaps-treatment`, which passes `treatments.json?find[enteredBy]=…&count=1`
  to `ns-get.sh`; that script treats its credential argument as a query and appends `'?'${QUERY}`, so
  `count` arrives as `1?<credential>` (hashed-secret mode) or `1?token=<t>` (token mode). The same code
  is on oref0 `dev` `d219baf9` and `master` `88cf032a` (`bin/nightscout.sh:164`, `bin/ns-get.sh:9,29-35`).
  15.0.8 answers 200 with the latest treatment; `dev` and the candidate answer 400 "Bad count" in both
  modes, under `readable` and `denied`, while the plain `count=1` control answers 200 on all three.
  Run through oref0's own `jq`/`date` pipeline, the 400 leaves the "latest treatment" time empty, so the
  cull keeps the whole 24-hour pump history: **57 treatments re-uploaded on every loop instead of 1**.
  **Nightscout does not store duplicates**: three posts of that batch left the collection at 137 each
  time, because the treatments upsert on `created_at` and `eventType` is idempotent, so insulin and
  carbs are not counted twice. The cost is elsewhere. **An edit made in Nightscout to a rig-uploaded
  treatment from the last 24 hours is overwritten on the next loop** (measured: a `notes` edit is gone
  after the re-post, `_id` unchanged). That replace-on-repost already happens on 15.0.8; what 15.0.9
  adds is that the rig re-posts those records every loop. The defect is in the client, and it also
  puts the credential in a URL on 15.0.8 (mechanism only here).
- **GluPredKit sends a literal `count=0` meaning "no limit".** `glupredkit/parsers/nightscout.py:66-91`
  sends `count: 0` with a date window for profiles, treatments and entries. Measured over a 50-hour
  window: 15.0.8 returns 1 profile, 137 treatments and 576 entries; `dev` and the candidate return an
  empty list for all three, and the `count=100000` control returns the full set everywhere.
  GluPredKit's resampling then raises (read from its source). GluPredKit was not in the census above, which is why the census found no literal
  `count=0`.

**What this means under this policy's own test.** The table's "could a real client send it?" answers
were *No* for both rows, and both are now *Yes*: oref0 sends a non-integer spelling, and GluPredKit
sends a literal zero. By the rule stated at the top of this case, narrowing input that a real client
sends is **major**. The choices this puts to the maintainer before 15.0.9 is tagged are, in outline:
keep the rule and ship it under 15.0.9 as a declared correction, naming both clients in the release
notes; tolerate the specific shapes real clients send (for example, read a leading whole number the
way 15.0.8 did, and/or keep `count=0` as the default limit with a deprecation warning, as recommended
above) so 15.0.9 stays a patch; or keep the rule and number the release as a major. On the oref0
side, the measured cost is load (a day of treatments per loop) and reverted Nightscout-side edits,
not double-counted therapy.

**Decided 2026-09-24: tolerate the shapes real clients send, and keep 15.0.9 a patch.**
*(Maintainer. Implemented in #8761, `bf/count-client-compat`, on `dev` `ddd9b600`.)* On v1 reads only:

- **A whole number followed by `?`** is read as that number, as 15.0.8's `parseInt` read it.
  Only that shape is tolerated: `abc`, `-3`, `2.5`, `1e2` and `0x10` are still refused, with or
  without a `?` after them. What follows the `?` is never logged or echoed, because oref0's
  contains its credential.
- **`count=0` with a `find` that bounds one date field from both sides** reads everything in
  the window. It was first decided as "the endpoint's default limit". It was changed the same day
  because, on 15.0.8, the string `"0"` reached `.limit(0)`, which means no limit. So GluPredKit
  received everything in its window, and the entries default of 10 would have cut its 576 entries
  to 10 without an error.
- **`count=0` without such a window** reads as though no count had been given, which is the
  endpoint's default. This keeps the guard against an accidental whole-collection read. Where
  15.0.8 returned the whole collection here, 15.0.9 returns the default; no client in the census
  sends it.

Both tolerated shapes are answered with `Deprecation: true` and a `299` `Warning`, and are
logged once per process. Each has its own setting, `API_V1_COUNT_LEADING_NUMBER` and
`API_V1_COUNT_ZERO_WINDOW`. Both default to `true`, and a future release is expected to flip them
to `false`. That follows this programme's compatibility-flag rule: a flag that keeps today's
behaviour, with a planned flip, where real deployments rely on it. With a setting `false`, that
shape gets #8748's answer. Deletes are unchanged. Measured with the consumer-replay lab on the
branch: oref0 gets 200 in both auth modes and uploads 1 treatment per loop, not 57; GluPredKit
gets 1 profile, 137 treatments and 576 entries, the same as 15.0.8. By this section's test, no
input a real client sends is narrowed, so the change is a patch.

**The asymmetry with v3 `?limit=0x10`, which this policy keeps.** v3's limit is a documented
closed contract: `API3_MAX_LIMIT` is described in `lib/api3/swagger.json` (verified by grep at
`origin/dev`) and the endpoint already had a 400 path. **Restoring a documented bound is not the
same act as inventing one**, and it is a minor.

### 3.3 An alarm that starts firing for operators who have never received it

*The case: `bf/alarms` `8714093b`, insulinage's URGENT branch. See S7.*

**Answer: MINOR, with the strictest disclosure obligation in this policy.** Nothing an operator
configured stops working, no action is required and no data is lost — so not major. The
disclosure is stricter than any other minor because:

1. **The operator cannot have tested it.** It requires a reservoir 72 hours old and the
   20-minute post-hour window. Nobody sees it before it arrives for real.
2. **The audience is not the operator.** It is whoever holds the phone — often a parent, a
   partner, or a school nurse who was never told the deployment was upgraded.
3. **Alarm meaning is learned by repetition, and this one arrives with `persistent` sound.** A
   household that learned "URGENT means glucose" gets an URGENT that means "change your insulin
   reservoir".

**Three obligations on any S7 change**, without which a PR is not ready regardless of its number:

- The operator-facing note says **what will arrive, when, at what level, with what sound, and
  how to turn it off** (here: `IAGE_ENABLE_ALERTS`, `IAGE_URGENT`).
- The note names the **default** that decides whether it fires. Here the default is
  `IAGE_ENABLE_ALERTS=false`, so the sound reaches only operators who turned alerts on, while the
  urgent-red IAGE pill reaches everyone. A note saying only "a new alarm is coming" is wrong for
  most readers; one saying only "a pill turns red" is wrong for the rest.
- It does **not** simplify the algorithm. "Your reservoir alarm now works" does not tell someone
  that a new persistent sound is coming at 72 hours.

**General rule:** *making an unreachable branch reachable is a behaviour change of exactly the
size of the branch.* A dead URGENT alarm is a missing alarm, and restoring it is an addition.

### 3.4 Raising the Node floor — cut 1

**Answer: MAJOR** (argued in S5). Three practical additions:

1. **Prefer a floor (`>=22.23.2`, or `>=22.12` if the rebased range is kept) to a caret
   whitelist** unless there is a known incompatibility with an odd-numbered major, in which case
   name it in the PR. Measured: Node 26.0.0 fails
   `semver.satisfies('26.0.0', '^22.23.2 || ^24.20.0')`. That is a recurring maintenance
   obligation created by the notation, not by any incompatibility.
2. **The declared floor and the enforced floor must be the same thing.** Today `engines` says
   `>=20.x` and `bootevent.js` enforces `>=16.x`. Cut 1 derives the check from `engines`, which
   is the right design: **`engines.node` is the single source of truth for the runtime floor, and
   every other statement of it is generated or checked against it.** Six files state it
   independently (`.nvmrc`, `bin/setup.sh`, `azuredeploy.json`, `README.md`, `CONTRIBUTING.md`,
   `docs/meta/architecture-overview.md` — GT2), and a one-field revert leaves all six stale.
   Queue gate: `tools/queue/gates/node-floor-consistency.js`.
3. **A runtime floor needs a deprecation release like an ingestion removal does**: the symptom
   is total, and the operator finds out by their site being down. §5.4 sets the window.

Adding Node 26 to the accepted set is a minor, and the gate says so.

### 3.5 Deleting an ingestion path — cut 4

**Answer: MAJOR, and the number is the least of what it needs.**

**What cut 4 removes, with the caveat that applies.** Cut 4 (`chore/mime-exposure-review`)
deletes the legacy Dexcom Share bridge and the legacy MiniMed CareLink plugin (mmconnect). The
maintainer reports (2026-09-21; operational knowledge, **not measured here** — it would fail at
the CareLink vendor API, which no local test reaches) that **mmconnect has not worked for some
time**, and that **legacy Dexcom Share is intended to map to compatible `nightscout-connect`
options**. So the MiniMed deletion may remove nothing a user currently receives, and the Dexcom
path is the live one whose mapping must be verified. Register entries **BF-44** and **BF-45** were
graded assuming mmconnect is live and **have not been re-graded**. The cut's own evidence document
says *"No real Dexcom account or live database has been used and no live migration is claimed."*

**What does not depend on whether mmconnect works** (GT4, executing the shims from
`origin/chore/mime-exposure-review` under `node`; register BF-61):

- An operator with `MMCONNECT_*` set and no `CONNECT_COUNTRY_CODE` gets `{migrated:false,
  error:…}`, which becomes a `ctx.bootErrors` entry, which makes `lib/server/app.js:202` install
  `app.get('*', bootErrorView)` and `lib/server/server.js:61` skip websocket setup. **The whole
  deployment serves the boot-error page** — no API, no sockets, no charts. Leftover
  `MMCONNECT_*` variables from a broken integration are enough to trigger it.
- The shim states the country **cannot be inferred** from `MMCONNECT_SERVER`, so there is no
  configuration in which the migration is automatic.
- An operator running `BRIDGE_*` and `MMCONNECT_*` together — two independent boot stages today —
  gets the same total outage, because there is one `CONNECT_SOURCE`. **Concurrent multi-source
  CGM ingestion is removed**, and appears in no summary of the cut.
- `DEXCOM_BRIDGE_USE_LEGACY` becomes accepted-and-ignored (BF-62).

**What the policy requires beyond the number:**

1. **A deprecation release first** (§5.4), shipping `mmconnect-connect-compat.js` *without*
   deleting `lib/plugins/mmconnect.js`, warning and continuing to run.
2. **A boot error is never an acceptable deprecation mechanism.** If a migration cannot be
   automatic, the release that introduces the requirement warns and keeps running.
3. **Fix the version strings in the shims.** Both say *"retired in Nightscout 15.0.9"*; on the
   adopted train 15.0.9 retires nothing. Every deprecation warning must name the version that
   actually deletes the plugins.

**General rule:** *an ingestion removal is major, requires a deprecation release, and requires
that the failure mode during the window be "warn and keep ingesting" rather than "stop".*

### 3.6 A retry-timing change of 586× that makes outage recovery look slower — BF-34

*The case: `nightscout-connect` `lib/backoff.js` merged options as `{...config, ...defaults}` —
defaults last — so every value a caller passed was discarded. All five vendor sources configure a
2.5-minute retry interval; every one got the 256 ms default. Measured by executing both versions:
**585.94× exactly** (150000/256) at every attempt below the ceiling. Uncapped, attempt 20 is 4.99
years, so the precedence fix ships with a ceiling: `lib/builder.js:89` supplies
`max_interval_ms = expected_data_interval_ms * 6`, which is **30 minutes for four of the five
sources** (`dexcomshare`, `minimedcarelink`, `glooko`, `nightscout` each declare
`expected_data_interval_ms: 5 * 60 * 1000`). `librelinkup` derives it from
`opts.linkUpInterval * 60 * 1000` (`lib/sources/librelinkup.js:220`), so its ceiling is the
operator's configured interval × 6. With `'equal'` jitter the delay at the ceiling spreads over
[15 min, 30 min] (2,000 samples at attempt 10 fell in [900,351 ms, 1,799,757 ms]). The fix is
connector PR #68 (queue `P0-F`), merged into connector `dev` and in prerelease `0.1.0-dev.1` (§4.3).*

**Answer: MINOR in `cgm-remote-monitor` (a default change, question 11). A `y` bump in
`nightscout-connect` (§4). And the release note is the entire point**, because the change looks
like a regression from the operator's chair and is not one: previously data resumed the instant
the vendor did; now it can take up to half an hour.

Operator-language draft, to be carried into the note without simplifying it away:

> **After a Dexcom or CareLink outage, readings may take longer to start arriving again than they
> used to — up to about half an hour in the worst case.** "The connector" is the part of
> Nightscout that logs in to Dexcom or CareLink and fetches your readings for you. It now waits
> the gap its authors intended between attempts, instead of retrying several times a second.
> Retrying that fast never helped: it could not make Dexcom or CareLink answer any sooner, and
> because every Nightscout site was retrying at the same moments, a whole group of sites could be
> refused together for asking too often — which made the outage **longer** for everybody, not
> shorter.
>
> **How to tell the difference between "waiting to retry" and "something is actually wrong."**
> A pause looks exactly like a failure until it ends. Your site already watches for this on its
> own: by default it shows a warning when no new reading has arrived for **15 minutes** and an
> urgent alarm at **30 minutes** (`ALARM_TIMEAGO_WARN_MINS` and `ALARM_TIMEAGO_URGENT_MINS`, both
> on by default). **Because the new worst-case wait is about 30 minutes, an ordinary vendor outage
> can now reach that urgent stale-data alarm where before it would not have.** If readings come
> back within about half an hour and then continue normally, nothing is broken. If they do not
> come back, or the gap repeats, check that your Dexcom or CareLink password still works and look
> at the site's logs.
>
> If your readings stop, treat it the way you already treat a sensor you cannot see — use your
> meter and your usual routine. **Nightscout is not a medical device and nothing here is medical
> advice; if a gap in your data affects decisions about your therapy, talk to your care team.**

**Rule:** *a change that trades a visible fast-failure for an invisible systemic improvement is a
default change (minor) and carries a release note that states the visible cost first and the
reason second.*

The fix **also removes the lockstep**: `use_random_slot` was forced false, so a pool that failed
together retried together. Measured with the upstream refusing authentication, 100 actors
delivered the same 800 requests across 3 s before and 67 s after. The note should say that too.

### 3.7 A two-major dependency upgrade with no API change and jsdom-only coverage — D3 5.16 → 7.9

**Answer: MINOR under question 13 — and the number is not the problem.**

None of S1–S8 moves. Question 13 catches it (a dependency that renders what an operator sees
moved by two majors). It is not a major, because nothing forces an operator to act.

**What is actually wrong is coverage.** D3 v6 removed `d3.event` and changed every handler
signature. Commit `48075a18` reaches three production files — `lib/client/renderer.js`,
`lib/client/chart.js`, `lib/report_plugins/daytoday.js` (GT2). `lib/plugins/cob.js` +49/−73,
filed under the D3 heading in the 2026-09-14 release-readiness document, is **not** D3 work: it is
`34e9b2da`, a behaviour change to carbs-on-board reporting, with no line of its own in the release
decision (queue `RT-D3`).

Coverage on dev (GT2): `tests/dependency-d3.test.js`, 24 passing, drives the real renderer and
chart against the D3 7 bundle and is non-vacuous (it catches a revert of the mouseover handlers to
the D3-5 signature and a break of `d3.pointer`). The gap: jsdom's geometry is stubbed
(`getBoundingClientRect` fixed at 900×600), and **both treatment-drag clamps at `renderer.js:764`
and `770-771` are unexercised** — 24/24 still pass with both deleted, because the handler is only
invoked with x ∈ {20, 400}. Those clamps bound a user-initiated rewrite of a treatment's
`created_at`, emitted over the socket, and a treatment's timestamp is what IOB and COB key off.
Queue gate: `tools/queue/gates/d3-drag-clamp-covered.js`.

- **Number:** minor.
- **Gate:** a dependency major that reaches rendering code **requires a real-browser pass before
  the release ships**, recorded in the PR — either cut 1's Playwright suite, or a human who opens
  the chart, drags a treatment to each edge of the plot, opens the COB pill on a real deployment,
  and says so by name.

**Rule:** *a version number is never accepted as mitigation for absent coverage.*

### 3.8 A client-side calculation that gave the wrong number — the case the ladder cannot see

This is a **hole in §1's enumeration and §2's ladder**, left as an open decision.

*The case: `bf/food` `73495331`, merged to dev as #8735, not released; register **BF-35**, graded
**high**. `lib/client/boluscalc.js` `loadFoodQuickpicks` builds the `<option>` list by iterating
the **whole food collection** and using the array index as the option's `value`, while
`quickpickChange` looks that index up in `quickpicks`, the **filtered** array. They agree only
when every food record is a quick pick. Reproduced in jsdom (register): picking the option labelled
`Breakfast (45 g)` loads **Lunch (70 g)**; picking the last option throws. The register's severity
line: "the carbs that reach the insulin calculation come from a record the user did not choose,
**with no error shown**." A regression from `3457de5b`, 2017.*

**What §2 says about it: PATCH.** Every question 1–13 answers "no" — the HTTP responses are
byte-identical; defect and fix are entirely in the browser — and §5.6's note obligations attach
only to minors and majors, so **no note is required.**

**The gate agrees**, run 2026-09-15 against `a8888f0d`:

```
$ node tools/qc/semver-surface-gate.js --repo externals/cgm-remote-monitor-official \
      --base a8888f0d --head bf/food
  [S1] HTTP API v1/v3 request or response contract  -> requires NONE
      1 file(s): lib/server/food.js
  [S2] plugin interface, boot sequence, client bundle  -> requires NONE
      1 file(s): lib/client/boluscalc.js
  ...
    [OPEN]  Q-PLUGIN (S2) Does a third-party or forked plugin that works today need
            editing to keep working?
```

`lib/client/` maps to **S2**, whose only question is about forks; answered honestly, `bf/food`
scores `REQUIRED: NONE`. The same on `bf/merge` (**BF-36**, merged as #8734: the client's delta
merge read past the end of an array and threw, the throw escapes into `dataUpdate`, which has no
`try`/`catch`, so **the page stops advancing until reloaded**) asks only `Q-REMOVE` and `Q-PLUGIN`
and scores `NONE`.

**The candidate, for the maintainer to accept or reject:**

> **S9 — What the client computes and shows to a person.** The displayed value, the calculator's
> inputs and result, the chart, the pills and the page continuing to advance. Weight: **minor at
> least** whenever the number, the record or the reachability of the page changes, on §3.1's
> reasoning, with S6's precedence argument applying whenever the value feeds a therapy decision.
>
> Gate question, raised by `lib/client/**` and `lib/plugins/**`: **`Q-SHOWN` — does any number,
> record or chart a person reads change, or does the page stop or start updating?**
>
> §5.6 obligation: **a fix to a therapy-adjacent calculation names, in plain language, what was
> wrong, over what period, and what a person should do about decisions they already made on it.**
> For BF-35 that sentence has no draft anywhere in this programme. The model is §3.1's
> `bf/coercion` sentence — and BF-35 is the stronger case, because a wrong carb count reaching a
> bolus calculation is a dosing input, not a report.
>
> S9 would not make BF-35 a major. It makes it a **minor with a mandatory operator-facing note**,
> which is what is missing.

**Until S9 is decided, this policy classifies BF-35 as a patch and requires no note for it.**
`bf/food` is a minor anyway for a different reason (the `/api/v1/food/quickpicks` filter change is
an S1 event), so S9 changes the note, not the number, for the current batch.

---

## 4. 0.x versioning for nightscout-connect

### 4.1 The npm resolution rule

npm's caret is not uniform across 0.x. Measured with `semver.satisfies` (semver 6.3.1, Node
v24.15.0):

| range | 0.0.13 | 0.0.14 | 0.1.0 | 0.1.9 | 0.2.0 | 1.0.0 | 1.3.0 | 2.0.0 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `^0.0.13` | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| `^0.1.0`  | ✘ | ✘ | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| `~0.0.13` | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| `^1.2.3`  | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ | ✘ |

**The caret floats everything below the leftmost non-zero component.** `^0.0.13` matches exactly
`0.0.13`. So `0.0.z` carries no information a consumer can act on, and the convention the
ecosystem applies — **in `0.y.z`, `y` behaves as the major and `z` as minor-and-patch** — is the
one npm's operators encode.

### 4.2 How the connector is pinned

Every pin is a **tarball URL**, not an npm range. Measured 2026-09-22 with
`git show <ref>:package.json`:

| ref | pin |
|---|---|
| `origin/master` (15.0.8) | `refs/tags/v0.0.13.tar.gz` |
| `origin/dev` (15.0.9 candidate) | commit `234d47c` — in connector `dev` (PR #64, 2026-09-22) and prerelease `0.1.0-dev.1`, in no full connector release |
| cuts 1, 2, 3 (published tips) | `refs/tags/v0.0.13.tar.gz` |
| cut 4 `chore/mime-exposure-review` | commit `c962a13f` |
| cut 5 `chore/nightscout-modernization` (`b1bdaca0`) | commit `b77e5bb` |
| `rt/cut1` (local rebase, unpushed) | commit `234d47c` |
| `bf/connect-pin` (local, unpushed; queue `P0-PIN`) | `refs/tags/v0.0.14.tar.gz` — a tag that will not exist; P0-PIN replaces it with the npm version `0.1.0` |

The `^0.2.12` on master belongs to `share2nightscout-bridge`, a different package. There is no
npm-range pin for `nightscout-connect` anywhere in the tree, so **the version-number choice
changes no consumer's resolution; its job is to make a human stop.**

### 4.3 The policy for nightscout-connect

> **While `nightscout-connect` is below 1.0.0, `0.y.z` is read as `y` = major, `z` =
> minor-and-patch. A change that would be major under §2 bumps `y`. Everything else bumps `z`.**

**Applied to the backoff change (BF-34, PR #68): a `y` bump.** Measured on the programme's local
`v0.0.14` (`b394411` → `649a7de`, fast-forward from v0.0.13, 29 files +1362/−312, 887 lines new
tests), by executing `lib/backoff.js` at both revisions — five caller-visible changes:

1. option precedence reversed — `{...config, ...defaults}` → `{...defaults, ...config}`;
2. a changed default — `use_random_slot: false` → `jitter: 'equal'`;
3. a new throw — `backoff({jitter:'wild'})` now throws `backoff: unknown jitter mode "wild"`;
4. a new option, `max_interval_ms`;
5. `duration_for` is non-deterministic where it was deterministic.

(1) alone is question 3: a configured value went from ignored to honoured, moving timing 585.94×.

**The connector line is `0.1.0` (maintainer, connector PR #76, 2026-09-22).** Connector
`official/dev` `1946beb` declares `0.1.0` and carries all seven programme connector commits,
including the backoff change `c1cce2a`, so this policy's reading holds: the first release carrying
it is a `y` bump. Prerelease `0.1.0-dev.1` is on npm under `next`; the full `0.1.0` is queue
`P0-TAG`. Tags are checked against `package.json` by `scripts/release-version.js` in the connector
repository: `v0.1.0` must match it exactly, and a prerelease must be `v0.1.0-<id>`.

**Two things that do not change with the number:**

- **`package-lock.json` stays on the old SHA until the tag is pushed.** Its `integrity` is a hash
  over the tarball GitHub generates, which does not exist until then. A locally invented hash
  breaks `npm ci`; a stale lock fails `npm ci` loudly as out of sync, which is correct. Regenerate
  with `npm install` after the tag is pushed, **in the same PR** (queue `P0-LOCK`).
- **A tarball pin means the consumer's release note must carry the connector's breaking notes.**
  Nobody reading `cgm-remote-monitor`'s `package.json` sees a version number. The `+1/-1` pin diff
  is the only place the 585.94× change surfaces in the consuming repository — why R4 exists.

**If the maintainer prefers to stay on `0.0.z`** — defensible — the release **must** carry a
`BREAKING` section, because the number will not.

**On reaching 1.0.0:** the natural trigger is `cgm-remote-monitor` pinning connect by **version
range rather than tarball**, the moment a number starts resolving something.

---

## 5. Pre-release and deprecation conventions

### 5.1 Pre-release identifiers

Semver precedence: `16.0.0-alpha.1` < `16.0.0-rc.1` < `16.0.0`. npm will not install a
pre-release under a plain range unless asked.

> **Policy: a branch that is not the release its version names carries a pre-release
> identifier.**

One line per branch closes S8 (register BF-60, queue `RT-VERSION`). Proposed, using §8.3's
numbering — **the identifier is the point; the numbers move with §8**:

| branch | today (2026-09-22) | proposed |
|---|---|---|
| `origin/dev` | `15.0.9` | `15.1.0-rc.1`, or `16.0.0-rc.1` if §3.2's major reading is kept (§8.1) |
| `chore/retire-jsdom` (cut 1) | `15.0.9` | `16.0.0-alpha.1` |
| `chore/build-runtime-separation` (cut 2) | `15.0.9` | `16.1.0-alpha.1` |
| `chore/compose-mongodb6` (cut 3) | `15.0.9` | `17.0.0-alpha.1` |
| `chore/mime-exposure-review` (cut 4) | `15.0.9` | `18.0.0-alpha.1` |
| `chore/nightscout-modernization` (cut 5) | `15.0.9` | `17.0.0-alpha.2` |
| unmerged `bf/*` branches (`bf/auth`, `bf/throttle`, `bf/connect-pin`) | `15.0.9` | inherit dev's number when they land |

### 5.2 How a deprecation release is numbered

> **A deprecation release is a MINOR.** It adds warnings and compatibility shims and removes
> nothing. Not a patch, because it changes what a deployment emits and often adds a key operators
> are asked to set. Not a major, because nothing has broken yet — and calling it major spends the
> operator attention the actual removal release needs.

The removal that follows it is the major.

**The deprecation release ships the escape route, not merely the warning.** For cut 4 this means
shipping `mmconnect-connect-compat.js` *without* deleting `lib/plugins/mmconnect.js`, so an
operator can set `CONNECT_COUNTRY_CODE` and verify it **while the old path still runs**. A warning
that cannot be acted on without downtime is a countdown, not a deprecation.

### 5.3 What a deprecation announcement must contain

1. **The exact setting or endpoint** being removed, spelled as the operator spells it.
2. **The replacement**, with the exact new setting and a worked example.
3. **The version that will remove it**, named.
4. **What happens if they do nothing**, stated concretely. "MiniMed data will stop arriving" and
   "your site will not start" are different sentences.
5. **Where to ask for help.**

It must reach **at least two channels**: the boot log *and* an in-app banner. Nobody reads the log
of a service that is working. This is a code obligation, not a documentation one.

**Announced removal versions do not move earlier.** They may slip later.

### 5.4 How long the window should be

The variable that matters is **how long it takes news to reach a self-hoster who is not looking.**
Deployments routinely run untouched for a year or more, and the person who set it up is often not
the person depending on it.

> **Minimum windows, from the deprecation release being generally available to the removing
> release shipping:**
>
> | Change | Window | Extra requirement |
> |---|---|---|
> | Any behaviour change needing operator action | **1 release and 90 days** | release note + boot log |
> | **A change that can stop data arriving** — an ingestion path, a connector default, a required new setting, a runtime floor | **2 releases and 180 days** | release note + boot log + **in-app banner** + community announcement |
> | A security fix that cannot wait | no window | ship it, and say in the notes why the window was waived |

**Why 180 days.** The harm is asymmetric: shipping a removal a season late costs maintenance of a
shim already written; shipping it a season early costs a household its CGM data feed. **Why "2
releases" as well.** Time alone does not help an operator who upgrades in one jump from a version
predating the warning; the removing release should also **detect the removed configuration and say
what happened** (question 7). Both figures are reasoned, not measured (§10 item 5).

**Consequence for cut 4:** it cannot ship immediately after its deprecation release. The adopted
train already holds it last.

### 5.5 Deprecating something that was never announced

MiniMed is the live case: `lib/server/mmconnect-connect-compat.js` does not exist on dev or master
— it is born in the branch that deletes `lib/plugins/mmconnect.js`. Dexcom has had a shim
(`bridge-connect-compat.js`) on master and dev for some time, with a boot warning naming
`DEXCOM_BRIDGE_USE_LEGACY`. MiniMed's only warning today is a generic "PLEASE CONSIDER
nightscout-connect instead." naming no setting (queue gate
`tools/queue/gates/minimed-deprecation-path.js`).

> **Policy: the window starts when the announcement ships, not when the intention forms.** A
> migration shim that appears in the same release as the deletion has a window of zero.

So cut 4's deprecation release (queue `RT-4`) is real code work — the shim extracted, made
non-fatal, and shipped ahead. If mmconnect is confirmed already non-functional (§3.5), the
MiniMed half of that window protects configuration (leftover `MMCONNECT_*` variables that would
otherwise produce a boot error), not a working data path; the Dexcom half protects a live path.

### 5.6 The operator-facing half of every minor and major

The classification is contributor-facing; the release note is not. Any note a person managing
their own or a family member's diabetes will read must:

- use plain language and define every term it cannot avoid;
- say **what will change for them**, **what they must do**, and **by when**;
- preserve every safety-relevant caveat from the contributor-facing text **verbatim** —
  `bf/coercion`'s "earlier results may have under- or over-reported delivered therapy" is the
  model;
- **never simplify algorithm behaviour** in a way that could mislead someone relying on it;
- give **no individualised insulin dosing advice**, and suggest the care team where a change
  could affect therapy decisions;
- state that Nightscout is not a medical device and its output is not medical advice.

---

## 6. An enforceable check

### 6.1 Why a checklist and a gate are both needed

All 495 modernization commits have one author; the 100 child PRs were self-merged with zero human
reviews; release PR #8598 and integration PR #8605 each carry zero approving reviews (#8598:
`REVIEW_REQUIRED`, 2026-09-22). **When there is no second reader, the version number is the only
signal an operator gets about how carefully to upgrade.**

A checklist asks a human who may be the only human; a gate cannot read intent. The design: the gate
detects what is mechanically detectable and asks the questions it cannot decide. **As built, it
treats any non-empty answer that does not begin "yes" as "no"** (§6.3, run K) — so until that is
fixed, the checklist in §6.2 is the binding artefact and the gate's questions are advisory.

### 6.2 The reviewer checklist

Paste into the PR template.

```
## Semver impact

Surfaces touched (tick all that apply):
[ ] S1 HTTP API v1/v3 or the realtime socket contract
[ ] S2 plugin interface, boot sequence, or client bundle
[ ] S3 environment-variable configuration surface
[ ] S4 stored document shape or database schema
[ ] S5 Node or MongoDB runtime floor (engines, runtime-policy, CI matrix)
[ ] S6 an ingestion path (bridge, mmconnect, connect, uploader, API write)
[ ] S7 the set of alarms or notifications that can be emitted
[ ] S8 the version string itself
[ ] S9 (candidate) what the client computes and shows a person
[ ] none of the above

Answer every question. "No" needs evidence; "yes" needs a release-note line.
- Does anything that boots today fail to boot after this?            yes / no
- Does any ingestion path stop, or need new configuration?           yes / no
- Is any capability removed or narrowed?                             yes / no
- Does any request that returns 2xx today return 4xx/5xx after?      yes / no
    If yes, NAME a real client that sends it, or say none can exist.
- Does any request return a different SET of records, or a
    differently-shaped body?  (empty -> populated counts;
    a wrong answer becoming right counts)                            yes / no
- Can an alarm or notification fire that could not fire before,
    or fire at a different level or volume?                          yes / no
- Does any default change (logging, retry, limit, sort, units)?      yes / no
- Does any non-delete write drop a stored field?                     yes / no
- New env var?  Env var whose meaning changes?  Env var now
    accepted and ignored?                                            yes / no
- Dependency major bump reaching anything an operator sees?          yes / no
- Does any number, record or chart a PERSON reads change, or does
    the page stop or start updating?  (client-side counts: the bolus
    calculator, the pills, the chart)                                yes / no
    -- candidate S9.  MINOR at minimum, and a therapy-adjacent
       calculation needs the note in 5.6

Proposed: [ ] patch  [ ] minor  [ ] major
Evidence for each "no" (a test name, a diff line, or a transcript):

Non-vacuity: name one check in this PR, say how you broke the code
under it, and confirm the check failed.

If a dependency major reaches rendering code:
[ ] a real browser pass was done, or the Playwright suite runs here — say which

Deprecation (required if MAJOR):
[ ] a previous release warns about this, naming the setting AND the removing
    version, in the boot log AND in the app
[ ] the window in 5.4 has elapsed
[ ] or: no warning was possible, and here is why:

Operator-facing release note (required if MINOR or MAJOR):
[ ] drafted in plain language, jargon defined
[ ] every safety-relevant caveat preserved verbatim
[ ] says what the operator must do and by when
[ ] no individualised dosing advice; care team suggested where relevant
[ ] no algorithm behaviour simplified in a misleading way
```

### 6.3 The runnable gate

`tools/qc/semver-surface-gate.js` — read-only, no network, no dependency beyond `semver` (resolved
from the inspected repo where available).

```
node tools/qc/semver-surface-gate.js --repo <checkout> --base <ref> --head <ref> \
     [--impact <answers file>] [--simulate-version X.Y.Z] [--json]
```

From the diff alone it computes:

- **which declared surfaces the change touches**, by path;
- **env-var additions and removals**, by censusing `readENV*('NAME')` at both refs — removals a
  hard major, additions a minor;
- **whether `engines.node` narrowed or widened**, by testing both ranges against a grid of Node
  versions — narrowing a hard major, widening a minor;
- **whether the enforced boot-time Node check moved**, independently of `engines`;
- **whether the `nightscout-connect` pin moved**;
- **file deletions in capability-bearing paths** (S1, S2, S6) — a hard major;
- **added lines matching an emission pattern** in alarm files, indexed per file.

It then asks what it cannot decide (`Q-REMOVE`, `Q-4XX`, `Q-ROWS`, `Q-ALARM`, `Q-PLUGIN`,
`Q-FIELD`, `Q-PIN`, `Q-INGEST`). **It fails if any question is unanswered, if the answers imply a
larger bump than `package.json` moved, or if the PR's declared `proposed:` is smaller than the
computed one.** An answer escalates only when it begins `yes`.

Answers file — one `key: value` per line, `#` comments:

```
proposed: major
Q-4XX:    yes - ?count=0 and five other spellings now 400 on every v1 route, reads and writes
Q-ROWS:   yes - count/entries/where goes from [] to a number
Q-REMOVE: yes - ?count=0 previously returned the whole collection and now returns 400
Q-FIELD:  no  - storage.js change is the shared count parser, no stored field is dropped
```

**Three design choices, each forced by a run that failed for the wrong reason:**

1. **Content patterns are indexed per file** from the `+++ b/<path>` headers. Matched against the
   whole diff, a dependency-audit CSV line in cut 1 was reported as an alarm change in
   `lib/plugins/pushover.js`.
2. **`Q-ALARM` is asked on any touch of an S7 path**, with content patterns as supporting evidence
   only. The insulinage fix changes a comparison; the emitting lines are untouched context, so no
   added line matches an emission pattern. **A grep cannot see an unreachable branch becoming
   reachable.**
3. **A path touch raises a question, not a number.** Forcing a minor on any path touch failed
   `bf/cache`, a pure clone-avoidance change with identical bytes on the wire.

#### Demonstration and controls — measured 2026-09-15 against `a8888f0d`

`bf/reads` at `0d19bb31`, no answers:

```
$ node tools/qc/semver-surface-gate.js --repo externals/cgm-remote-monitor-official \
      --base a8888f0d --head bf/reads
========================================================================
semver surface gate   a8888f0d -> bf/reads
========================================================================
22 file(s) changed; version 15.0.9 -> 15.0.9  (NONE)

  [S1] HTTP API v1/v3 request or response contract  -> requires NONE
      12 file(s): lib/api/index.js, lib/api3/generic/collection.js,
                  lib/api3/generic/search/input.js, lib/api3/shared/fieldsProjector.js, ...
  [S4] stored document shape / database schema  -> requires NONE
      1 file(s): lib/authorization/storage.js

  questions the gate cannot answer from the diff:
    [OPEN]  Q-REMOVE (any) Is any capability removed or narrowed ...
    [OPEN]  Q-4XX (S1) An HTTP 4xx appears in 1 changed API file(s)
            (2 added line(s), e.g. lib/api/index.js) ...
    [OPEN]  Q-ROWS (S1) Does any request now return a DIFFERENT SET of records ...
    [OPEN]  Q-FIELD (S4) Does any non-delete write now drop a stored field ...

  REQUIRED: NONE     ACTUAL: NONE

FAIL
  - 4 surface question(s) unanswered
========================================================================
exit 1
```

Answered honestly, the arithmetic moves without anyone editing the number:

```
  [answered] Q-4XX    yes - ?count=0 and five other spellings now 400 ...   => escalates to MAJOR
  [answered] Q-ROWS   yes - count/entries/where goes from [] to a number    => escalates to MINOR
  [answered] Q-REMOVE yes - ?count=0 previously returned the whole collection => escalates to MAJOR
  [answered] Q-FIELD  no  - shared count parser, no stored field dropped

  REQUIRED: MAJOR     ACTUAL: NONE

FAIL
  - version bump is NONE (15.0.9 -> 15.0.9) but the surfaces touched require at least MAJOR
```

With `proposed: minor` and everything else unchanged (run C3), a second failure appears:
`PR declares "minor" but the gate computes major`.

Sixteen gate runs plus one git measurement. Runs A–H2 were reproduced by an independent second
pass (same verdicts, same exit codes, captured with `${PIPESTATUS[0]}`).

| # | Run | Expected | Got |
|---|---|---|---|
| A | `bf/reads`, no answers | fail (unanswered) | **fail**, exit 1 |
| B | `bf/reads`, answers, version unchanged | fail (bump too small) | **fail**, exit 1 |
| C | `bf/reads`, answers, `--simulate-version 16.0.0` | **pass** | **pass**, exit 0 |
| C2 | `bf/reads`, answers, `--simulate-version 15.1.0` | fail (minor < major) | **fail**, exit 1 |
| C3 | `bf/reads`, `proposed: minor`, `--simulate-version 16.0.0` | fail (declared < computed) | **fail**, exit 1 |
| D | `bf/cache`, answers `no`/`no`, version unchanged | **pass** (a true patch) | **pass**, exit 0 |
| E | `bf/alarms`, answers, version unchanged | fail (major, per Q-REMOVE as answered then) | **fail**, exit 1 |
| F | `origin/master` → `origin/dev` at `a8888f0d` | fail | **fail**: `REQUIRED: MINOR   ACTUAL: PATCH` |
| G | `origin/dev` → cut 1 | fail | **fail**: `REQUIRED: MAJOR   ACTUAL: NONE` |
| H | scratch repo **widening** `engines.node` (`>=20.x` → `>=18.x`) | minor | **minor**: `newly accepts: 18.20.4` |
| H2 | same scratch repo **narrowing** (`>=18.x` → `^22.23.2 \|\| ^24.20.0`) | major | **major**: `rejects now: 18.20.4, 20.0.0, ... 26.0.0` |
| J | `bf/reads` `0d19bb31` contained `bf/coercion` `88d1f8a4` on that date | — | `merge-base --is-ancestor` → yes (the two later merged separately, #8737 and #8738) |
| **K** | `bf/reads`, `proposed: patch`, all four answers `unknown` | **fail** | **PASS, exit 0 — the bypass** |
| **K2** | `bf/reads`, `Q-4XX: probably yes`, rest `no`, `proposed: patch` | fail | **PASS, exit 0** — `/^yes\b/` does not match `probably yes` |
| K3 | `bf/reads`, all four answer keys present but empty | fail | **fail**, exit 1 — emptiness is caught |
| L | `bf/food` (BF-35), no answers | should ask about the calculator | asks `Q-REMOVE`, `Q-ROWS`, `Q-PLUGIN` only; honestly answered, `REQUIRED: NONE` (§3.8) |
| M | `bf/merge` (BF-36), no answers | should ask about the frozen page | asks `Q-REMOVE`, `Q-PLUGIN` only; `REQUIRED: NONE` (§3.8) |

C and D show the arithmetic is discriminating, not a tax. H/H2 control the S5 rule. **K, L and M
decide whether the gate can be trusted**: K shows the arithmetic can be bypassed with one word;
L and M show two client-only defects score `NONE` however honestly answered.

Run F has not been re-run against `74fc6619`. dev now also carries `bf/reads` as written, so an
honest answers file on master → dev would escalate on `Q-4XX` (§8.1).

#### Open defect: the answer bypass (run K)

`unanswered` is `questions.filter(q => !impact[q.id])` — any non-empty string counts as answered —
while escalation is `/^yes\b/i.test(a)`. Every string that is not "yes…" is silently treated as
"no". Present in `tools/qc/semver-surface-gate.js` as of 2026-09-22 (line 354).

**Required fix before the gate is binding** (a decision for the gate's owner): parse answers into
an enum — `yes` / `no` / `unknown` — reject anything else with exit 2, and make `unknown` escalate
to the surface's minimum.

#### Known limits

- **Answers are free text and only `yes…` escalates** — the bypass above.
- **A version downgrade reads as no bump, not as an error**
  (`if (semver.lt(headVersion, baseVersion)) actual = 'none'`).
- Surface hits are prompts, not verdicts: `lib/authorization/storage.js` is reported under S4 on
  `bf/reads`, where the change is the shared count parser — a path rule on a storage file should
  ask a human.
- The path map is `cgm-remote-monitor`-shaped. `nightscout-connect`'s public surface is a module
  API, so it needs an exported-signature and default-value diff. **Not built** (§10).
- It cannot detect a semantic change confined to an untouched file's behaviour, a data migration in
  a script, or a change whose effect depends on configuration.
- `--simulate-version` exists for the non-vacuity harness; CI must never pass it.

### 6.4 Making it queue-able

```make
# Makefile target (proposed; not added)
semver-gate:
	@node tools/qc/semver-surface-gate.js \
	  --repo $(CRM_REPO) --base $(BASE_REF) --head $(HEAD_REF) \
	  $(if $(IMPACT),--impact $(IMPACT),)
```

In `cgm-remote-monitor`'s CI the job would run on `pull_request`, with `--base` as the merge base
and `--impact` read from a `.semver-impact` file or parsed from the PR body. **An override label is
mandatory** — a gate with no escape hatch gets deleted rather than corrected — and must record who
overrode it and why.

---

## 7. Where current practice departs from this policy

Stated without blame: the project has had **no written definition of its public surface**, so none
of these is a rule violation. Measured 2026-09-22 unless marked.

| # | Departure | Evidence |
|---|---|---|
| D-a | **The version number does not move.** `origin/dev` and all five published cut tips carry `15.0.9`, including the branch that changes the Node floor and the branch that deletes two ingestion paths | `git show <ref>:package.json`; register BF-60 |
| D-b | **Two artefacts claim the same version with different runtimes.** dev is `15.0.9` at `>=20.x`; the cut tips are `15.0.9` at `^22.23.2 \|\| ^24.20.0` | same; queue gate `tools/queue/gates/version-collision.js` |
| D-c | **A patch number carries a two-major charting upgrade with jsdom-only coverage** and two unexercised drag clamps | §3.7; queue `RT-D3` |
| D-d | **New environment variables ship under a patch number.** `DEBUG_LOGGING` and `CONNECT_DEBUG` are new on dev, and debug logging flips from on to off | env census, master 30 names → dev 32 |
| D-e | **The gate says so mechanically.** master → dev (at `a8888f0d`, 2026-09-15) is numbered PATCH and the gate computes MINOR | §6.3 run F |
| D-f | **Deprecation warnings name a version that does not do the thing.** Both cut-4 shims say "retired in Nightscout 15.0.9" | GT4, executed |
| D-g | **A deletion ships in the same release as its own migration shim** — `mmconnect-connect-compat.js` is born in the branch that deletes `mmconnect.js` | §5.5 |
| D-h | **A documented escape hatch is removed without a word** — `DEXCOM_BRIDGE_USE_LEGACY` becomes accepted-and-ignored in cut 4 | BF-62 |
| D-i | **Release dependencies are pinned to untagged commit SHAs**: dev → `234d47c` (in connector `dev`, in no connector release), cut 4 → `c962a13f`, cut 5 → `b77e5bb` | §4.2 |
| D-j | **Shipping the published cut 1 after 15.0.9 would remove two environment variables and regress the connector.** Published cut 1 (`bce12ecc`) is 133 commits behind dev and reads neither `DEBUG_LOGGING` nor `CONNECT_DEBUG`, and pins `v0.0.13`. The local rebase `rt/cut1` (`ed21961f`, 9 behind dev, unpushed) reads both and pins `234d47c`, so the published branch, not the train, carries this defect | §6.3 run G; `git grep` of `lib/server/env.js` at both refs |
| D-k | **15.0.9 as it stands classifies above a patch.** See §8.1 | queue `semver` fields |
| D-m | **There is no PR field for semver impact** | §6.2 closes this |
| D-n | **Nothing enforces the number** | §6.3, once the bypass is fixed |

**Why D-j matters beyond numbering.** The two connector pins have diverged rather than one being
older: `v0.0.13` is `b394411`, a merge commit, and `234d47c` is a sibling of it off the shared
parent `6dfc4f0b` (`git diff 6dfc4f0b b394411` is empty, so the practical effect is losing one
commit — "Make embedded connector debug logging opt-in", 18 files +379/−146 — which is the commit
that produced `CONNECT_DEBUG` and `DEBUG_LOGGING`). **None of the three log-redaction commits
(`9fa2c3c`, `5349d47`, `77e2396`) is in either pin**, so moving from `234d47c` back to `v0.0.13`
turns connector debug logging back on by default on a connector that still writes Dexcom and
MiniMed credentials, sessions and patient data into runtime logs (register BF-42/BF-43, queue
`BFQ-CONNECTOR`, `RT-CONNECT-PIN-CUTS`). That is the case for a connector pin carrying the
redaction fixes landing **before** any cut ships.

---

## 8. What this policy costs the work in flight

The options are laid out; **the choice is the maintainer's.** Where this document has a preference
it says so.

### 8.1 The 15.0.9 candidate (`origin/dev` `74fc6619`)

15.0.9 is master..dev: 48 first-parent merges (`git rev-list --first-parent --count
official/master..official/dev`), 200 files, +14381/−1262, including twelve of this programme's
backfix PRs plus #8741 from an external contributor (none released). Classified row by row from the queue's `semver` fields:

| Change | PR | Class under this policy |
|---|---|---|
| `?count=` validator, as written — rejects `?count=0` on every v1 route, reads and writes | #8738 (`bf/reads`) | **major** (§3.2), or minor if the maintainer adopts the census reading |
| `DEBUG_LOGGING`, `CONNECT_DEBUG`; debug logging off by default; new `lib/api2/loop-notification-errors.js` | pre-programme dev work | minor |
| insulinage URGENT made reachable (S7); Alexa/Google Home locale handling removed | #8739 (`bf/alarms`) | minor (the locale removal is a defect correction by maintainer ruling, §9) |
| schema-driven query coercion; `$exists` read as boolean (BF-40) | #8737 (`bf/coercion`) | minor |
| v1 operator allowlist (`$expr`, pipeline refused; `$type` allowed) | #8743 (`bf/operators`) | minor |
| `/alarm` delivery scoped to entitled sockets (GHSA-8849, BF-75/76) | #8745 | minor |
| food quick-pick filter (S1) and BF-35 chooser (client) | #8735 (`bf/food`) | minor |
| D3 5.16 → 7.9 | pre-programme dev work | minor (question 13), with the §3.7 browser-pass gate |
| quadratic treatment scans; read-path cost; client merge; URL parameter parsing; `loadRetro` authorization (GHSA-gjhc, BF-79); readable-by-world boot notice (BF-77) | #8733, #8740, #8734, #8736, #8744, #8746 | patch |
| external contributions | #8741, #8729, #8732 | not classified here |

**Under R3 the release is MAJOR on one row, and MINOR without it.** Options:

| Option | What it means | Cost |
|---|---|---|
| **1. Rule §3.2 minor on the census (§10 item 1) and number `15.1.0`** | One line in `package.json`; notes gain a "what changed for you" section naming `?count=0` and the write-path scope | Accepts the latent risk to runtime-computed counts |
| **2. Land the §3.2 clamp before release and number `15.1.0`** *(this document's preference)* | `?count=0` clamps with `Deprecation`/`Warning`; the five meaningless spellings stay rejected | One further PR before RT-0 |
| 3. Number `16.0.0` | Honest under the strict reading | Spends a major on bug fixes, and pulls forward the attention budget cut 1 needs |
| 4. Ship as `15.0.9` with a `BEHAVIOUR CHANGES` section | Keeps the planned number | The number understates the release, and D-b survives |

**`15.0.9` has never been tagged** (`git tag -l` stops at `15.0.8`), and dev Docker builds are
tagged `dev_<sha>` and `latest_dev`, not by version. **But the running application reports its
package.json version** (`lib/server/env.js:137`, `lib/api/status.js:32`), so dev-channel
deployments already answer `/api/v1/status` with `15.0.9`. If the release is renumbered, its note
should say `15.0.9` was never a release, so a reporter who says "I was on 15.0.9" is understood.

**Independent of the choice, the cut branches must stop claiming `15.0.9`** (§5.1, D-b).

The decision is queue items `RT-0` (release 15.0.9) and `RT-VERSION`; `RT-D3` also blocks RT-0.
Release PR #8598 (dev → master) is open, mergeable, CI green across Node 20/22/24 × Mongo
4.4/5/6, CodeQL and Docker build, with `REVIEW_REQUIRED` and zero approving reviews (2026-09-22).
See [release readiness for 15.0.9](release-readiness-15.0.9-2026-09-22.md).

### 8.2 The Phase 0 branches not yet merged

| Branch | Queue | Class | Why |
|---|---|---|---|
| `bf/auth` (BF-17) | `P0-C` | **major** | narrows `lib/authorization/storage.js` to an allow-list of fields, so a field a third-party admin tool stored is dropped on the next edit with no error (S4); adds `notes` to `GET /api/v1/subjects` |
| `bf/throttle` (BF-30) | `P0-J` | patch (queue classification) | failed-auth throttling with a compatibility default |
| `bf/connect-pin` | `P0-PIN` | minor under R4 | moves the connector pin to a tag that exists only locally; blocked on `P0-TAG` |

**Preference for `bf/auth`:** narrow it so it stops being major — delete only
`DERIVED_SUBJECT_FIELDS` instead of allow-listing the whole document. The major-ness is incidental
to the fix's purpose.

### 8.3 The release train

**Adopted by the maintainer, 2026-09-15.** The numbers are this policy's proposal; the order is the
decision.

| Step | Queue | Contents | Proposed number | Class |
|---|---|---|---|---|
| 1 | `RT-0` | 15.0.9: dev as it stands (§8.1) | `15.1.0` (or `16.0.0`, §8.1) | minor / major |
| 2 | `RT-1` | Cut 1 `chore/retire-jsdom`, **alone** — Playwright browser suite, Node floor, MongoDB 4.4 out of CI | `16.0.0` | major (S5) |
| 3 | `RT-2` | Cut 2 `chore/build-runtime-separation` — page bundles, narrowed D3, event bus, boot sequence, Babel 8 | `16.1.0` | minor (judgement; unmeasured against any third-party plugin) |
| 4 | `RT-3` | Cuts 3 + 5 combined — MongoDB driver 7, jQuery UI; Express 5, Helmet, EJS, Axios, Mocha 12, Swagger | `17.0.0` | major (dependency majors; no measured contract break) |
| 5 | `RT-4` | Deprecation release — MiniMed shim shipped non-fatally, Dexcom escape hatch preserved | `17.1.0` | minor |
| 6 | `RT-5` | Cut 4 `chore/mime-exposure-review` — legacy Dexcom and MiniMed retirement, trusted proxies, DOMPurify, Moment/tz — ≥180 days and 2 releases after step 5 | `18.0.0` | major |

**Open defect in step 4: BF-64** (register, **open**, reproduced). The stack is linear and cut 4 is
an **ancestor** of cut 5 (`merge-base --is-ancestor` exits 0), so "cuts 3 + 5 without 4" is not a
prefix: built from the branches as they stand, step 4 would ship cut 4's ingestion retirement
before the deprecation release meant to precede it. `lib/plugins/bridge.js` and `mmconnect.js` are
present on dev and cut 3 and absent on cuts 4 and 5. Step 4's contents cannot be written down until
this is resolved (for example by reverting the retirement out of cut 5 for step 4, or by
re-cutting the stack so the retirement is last).

**Why cut 4 is last and behind its own deprecation release** (§3.5): it deletes two CGM ingestion
paths, and if the Connect migration misbehaves the symptom is that a user's glucose data stops
arriving. The caveat: the maintainer reports mmconnect has not worked for some time (not measured
here), so the MiniMed half may remove nothing users receive; the Dexcom half is live and its
mapping to `nightscout-connect` has not been exercised against a real account. What does not
depend on the caveat: leftover `MMCONNECT_*` configuration without `CONNECT_COUNTRY_CODE`, or
`BRIDGE_*` and `MMCONNECT_*` together, produce a **whole-site outage** on cut 4 (BF-61; queue gate
`tools/queue/gates/cut4-total-outage.js`). Before step 5 is planned: re-grade BF-44 and BF-45 on
the maintainer's premise, and confirm the Dexcom Share → `nightscout-connect` option mapping
against a real account (a human step; nothing in this repository may use real credentials).

**Rebase state, 2026-09-22** (`git rev-list --left-right --count official/dev...<cut>` and
`git merge-tree --write-tree official/dev <cut>`; queue `RT-REBASE`): published cuts 1–4 are 133
commits behind dev with 7 / 14 / 16 / 18 conflicting paths; cut 5 (`b1bdaca0`) is 9 behind / 498
ahead with one conflict (`lib/server/bootevent.js`, from the BF-77 fix merged as #8746). Local
rebases `rt/cut1`…`rt/cut4` are prepared at 9 behind dev and are unpushed.

**The orderings are more durable than the numbers.** What matters: the deprecation release
precedes the major that needs it; the runtime break and the ingestion break are **not** in the same
release, because an operator debugging a site that will not start should not simultaneously be
debugging why their CGM data stopped; and cut 4 is last.

### 8.4 nightscout-connect

The connector line carrying the backoff change (PR #68) is **`0.1.0`** (connector PR #76), as §4.3
reads it. Prerelease `0.1.0-dev.1` is published; the full `0.1.0` is queue `P0-TAG`.
`cgm-remote-monitor`'s release note for the pin move must still carry the 585.94× retry change in
operator language (§3.6), because a pin diff shows no version semantics to a reader.

---

## 9. Judgement calls, resolved

GT4 marked eleven judgement calls. This policy's position on each:

| GT4 § | Judgement | This policy | Why |
|---|---|---|---|
| 3.5 | `?count=0` → 400 is major | **Major as written; the split makes both halves minor** (§3.2) | Five spellings are unreachable; `?count=0` is reachable by construction |
| 1 | S7 (alarms) is a first-class surface | **Adopted** (§1 S7) | |
| 3.1 | Alexa/Google Home locale removal is major | **Not major — maintainer ruling, 2026-09-17** | `ctx.language.set` and `moment.locale` are process-global, so a request carrying `request.locale` re-languaged every later request for every other user. The per-request locale was never a working capability; removing it is a correction, and the branch needed an ordinary review (queue `P0-A`) |
| 2 #1 | `bf/connect-pin` is minor although it is one line | **Upheld, as rule R4** | Classify by what the operator receives |
| 2 #5 | `bf/parms` is patch although `_`-decoding changes | **Upheld**, with a required release-note line | The old decoding was inconsistent and the server never agreed with it; a bookmarked report URL might depend on it, which is the note |
| 2 #15 | v3 `_id` tiebreak is patch | **Overruled → minor** | The commit's own subject is that paging "lost and repeated documents whenever the whole sort chain tied" — a paging client previously received a different set of records than the collection contains. That is question 10 |
| 2 #18 | v3 `?limit` restriction is minor, unlike `?count=` | **Upheld** (§3.2) | Restoring a documented bound ≠ inventing one |
| 5.2 | Cut 2 is minor | **Upheld, conditionally** | Unmeasured against third-party plugins. `Q-PLUGIN` must be answered with evidence; an honest "unknown" should escalate to the release's number — a reviewer obligation until the gate's enum fix lands (§6.3) |
| 5.5 | Cut 5 is major | **Upheld** | Express 4→5 changes routing and error semantics under everything that mounts a route. Classified from dependency majors, not a measured break (§10) |
| 6 | connect should be `0.1.0` | **Upheld** (§4.3) | Five caller-visible breaking changes |
| 5.6 | The numbering table | **Upheld with two changes**: pre-release identifiers on the cut branches (§5.1), and a 180-day window before cut 4 (§5.4) | |

**`bf/coercion` and `$exists=false` (BF-40).** GT4 noted the change replaced one wrong `$exists`
answer with another on the previously walked fields. That is a defect question, not a versioning
one, and it is closed: #8737 reads `$exists` operands as booleans (`BOOLEAN_OPERANDS` /
`readBooleanOperand` in `lib/server/query.js`), fixing BF-40. Merged 2026-09-18; not released.

---

## 10. What a verifier should attack, and what is unsettled

1. **§3.2 is the most overrulable call**, and it now decides 15.0.9's number. The unbounded-download
   counter-argument is real and the split is an opinion about sequencing, not a measurement.
2. **§1 S2 and §9's cut-2 row are unmeasured against any third-party plugin.** No plugin corpus
   exists here; running one would be worth more than both sections.
3. **Cut 5's major rests on dependency majors and a 36-file production diff**, not on a measured
   contract break. A browser pass plus the full suite could move it to minor.
4. **The gate has no surface map for `nightscout-connect`** — an exported-signature and
   default-value diff would have caught all five §4.3 changes mechanically. Not built.
5. **The 180-day window in §5.4 is reasoned, not measured.** If the Foundation has any telemetry on
   version distribution in the wild, that number should replace this one.
6. **§1's in/out arguments are where the document is falsifiable.** If S7 or S8 is rejected, several
   classifications move.
7. **Cut 4's risk grading rests partly on an unmeasured premise.** The maintainer reports mmconnect
   non-functional; BF-44/BF-45 have not been re-graded on that premise, and the Dexcom Share →
   `nightscout-connect` mapping has not been exercised against a real account.
8. **The gate can be passed by writing `unknown` in every answer** (§6.3, run K). Until answers are
   parsed as an enum, the gate is advisory and §6.2's checklist is binding. **Fix this first.**
9. **§1 has no surface for what the client computes and shows a person** (§3.8). Under §2 as
   written, BF-35 — the wrong carb count reaching a bolus calculation, with no error shown — is a
   patch with no release-note obligation. **If one thing here is wrong in a way that could reach a
   person, it is this.**
10. **Nothing here versions the seam and tenancy branches.** D1 keeps single-tenant first-class and
    D5 adds hosted entrypoints; a hosted entrypoint that withholds alarms outside tenant scope
    (T3.5) is an S7 event under this policy's reasoning, and no section addresses it.

---

*Draft policy requiring maintainer review before anything is renumbered, tagged or released; the
release-train order in §8.3 is adopted. Nothing in this document was pushed, tagged, merged or
published, and no shipping file was modified.*

*Operator-facing release notes derived from this document must follow §5.6. Nightscout is not a
medical device; nothing here or in a note derived from it is medical advice, and no part of it
gives individualised insulin dosing advice. Where a release changes something a person uses when
making decisions about therapy, the note should say so plainly and suggest they discuss it with
their care team.*
