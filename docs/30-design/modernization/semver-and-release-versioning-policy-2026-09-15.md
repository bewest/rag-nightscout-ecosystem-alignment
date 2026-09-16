# Semver and release versioning policy — cgm-remote-monitor and nightscout-connect

Date: 2026-09-15.
Status: **DRAFT for maintainer adoption.** It proposes a policy and a set of numbers.
It does not set any version, tag anything, or move any branch.
Audience: **contributors and maintainers.** Full technical depth is intended.
Operator-facing text derived from this document has its own rules — §5.6.

Builds on, and where it disagrees supersedes, the classification draft at
[`docs/60-research/modernization/gt4-semver-classification-2026-09-15.md`](../../60-research/modernization/gt4-semver-classification-2026-09-15.md).
Companion to [release readiness](cgm-remote-monitor-release-readiness-2026-09-14.md),
[Phase 0 PR sequencing](../remedial/phase0-pr-sequencing-2026-09-15.md) and the
[backfix register](../remedial/nightscout-backfix-register.md). This document does not edit those;
where it believes one of them is wrong, it says so in §9 and leaves the edit to the
reconciliation pass.

**What is new here, over GT4.** GT4 classified the changesets and drafted a procedure.
This document (a) argues the public surface in and out candidate by candidate, which is
the part that makes the rest falsifiable; (b) resolves GT4's eleven judgement calls,
overruling two; (c) adds the pre-release and deprecation conventions GT4 did not cover;
(d) ships a **runnable gate**, `tools/qc/semver-surface-gate.js`, and demonstrates on
real branches that it fails when it should and passes when it should; and (e) sets out
the renumbering options for work already in flight, without picking one silently.

---

## 0. How everything here was measured

Reads only. No branch, tag, worktree or shipping file was created, moved or modified.
The one file written outside this document is the new gate script, which is tooling in
this repository (decision D12) and touches nothing in the shipping checkouts.

| What | Where |
|---|---|
| `cgm-remote-monitor` | `externals/cgm-remote-monitor-official` — `origin/master` `92d08342` (15.0.8), `origin/dev` `a8888f0d` (15.0.9 candidate), the five `chore/*` cut tips, the nine `bf/*` branches |
| `nightscout-connect` | `externals/work/nc-jitter`, `externals/nightscout-connect` — `v0.0.13` `b394411`, `v0.0.14` `649a7de` |
| semver arithmetic | `semver` **6.3.1** under `node` v24.15.0, resolved from the inspected repo (`package.json` declares `"semver": "^6.3.0"` on `dev` and on every cut). *Corrected by the verification pass: the first draft said "semver 7.x". Every table below re-ran unchanged on 6.3.1.* |
| The gate | `tools/qc/semver-surface-gate.js`, written for this document, exercised in §6.3 |

House rule 9 applies throughout: **orderings are more durable than absolutes.** Where a
number appears, the method is named next to it.

### 0.0 Provenance — two passes, and which one wrote what

This document was drafted, then **adversarially verified by a second pass at head
`08753474`**, whose brief was to refute it rather than to extend it. Everything the second
pass re-measured or added is marked inline where it appears, and there is no unmarked
editing. The second pass:

- **re-ran all eleven of §6.3's original gate runs** (A–H2) and the git measurement J. All
  twelve reproduced their documented verdict and exit code, so §6.3's transcripts can be
  relied on as run output rather than as recollection;
- **independently reproduced** the npm caret table, the Node grid, the sixteen-ref version
  and connector-pin census, the `readENV*` env census (master 30 → dev 32), the
  `socket.on(` handler list, `API3_MAX_LIMIT` in `lib/api3/swagger.json`, the old
  `opts.count` code at six call sites, and insulinage's unreachable `urgent` comparison;
- **corrected seven factual statements** (§0's and §4.1's semver version, §1 S5's "except
  the first two majors", §4.2's pin and ref counts, §5.1's "six artefacts", §3.6's
  30-minute ceiling, §8.1's "has not been released", §7 D-k's list of minors);
- **corrected the blast radius of the one S7 case in both directions** (§1 S7, §3.3);
- **supplied a corpus measurement §3.2 argued without** (`count=0`, 274 occurrences);
- **escalated D-j** with the credential-logging consequence of the connector pin move;
- **found two things that change what a maintainer should do**: the gate can be passed by
  writing `unknown` in every answer (§6.3, run K), and §1's surfaces have no entry for what
  the client computes and shows a person, so BF-35 classifies as a patch (§3.8, runs L and
  M). Both are recorded as open, not repaired, because both are decisions.

Neither pass pushed, tagged, merged or modified any shipping file, and no worktree was
created or removed.

### 0.1 Two corrections to the ground-truth digest, found while measuring

Both matter to anyone acting on this document.

1. **`bf/reads` has been rewritten and is no longer flat on `dev`.** GT1 and GT4 recorded
   it at `824380a0`, seven commits, based directly on `origin/dev`. Measured today it is
   **`0d19bb31`, eight commits, and it contains `bf/coercion`'s tip `88d1f8a4` as its
   own base** (`git merge-base --is-ancestor bf/coercion bf/reads` → yes). The Phase 0
   set is therefore *not* flat: `bf/reads` is stacked on `bf/coercion`. A reviewer who
   lands `bf/reads` lands `bf/coercion` with it, and the classification of the two cannot
   be decided independently. Its new eighth commit is `0d19bb31`, a CHANGELOG.
2. **GT4's `lib/server/env.js` claim is right, but not by the route it gives.** The two
   new variables are read through `readENVTruthy('DEBUG_LOGGING', …)` and
   `readENVRaw('CONNECT_DEBUG')`, not `readENV`. A census restricted to `readENV(` shows
   **no difference at all** between `master` and `dev`. Measured by censusing
   `readENV[A-Za-z]*\('NAME'` at both refs: master 30 names, dev 32, the delta being
   exactly `CONNECT_DEBUG` and `DEBUG_LOGGING`. This is not pedantry — the first draft of
   the gate in §6 used the narrow pattern and reported "no change" on the very case the
   policy exists to catch.

---

## 1. What the public surface is

> Semver is specified for a library: "the public API" is what other code imports. That
> definition is empty for an application nobody imports. Without an explicit substitute,
> every classification argument here becomes unfalsifiable — which is exactly the state
> this project is in today, and why a two-major charting upgrade is shipping under a
> patch number without anybody having been wrong on the rules.

**The substitute this policy adopts:** the public surface of Nightscout is
**everything an operator, or a program an operator runs, can depend on without reading
the source.** If a reasonable person could build a habit, a script, a device integration
or a care routine on it, it is a surface.

Each candidate is argued below. The verdict column is what this policy adopts.

### S1 — HTTP API v1 and v3, and the realtime socket. **IN.**

**In, unambiguously.** v3 is a documented, versioned, swagger-described contract with a
closed 9-operator query set (decision D8). v1 is undocumented in places but is what every
uploader, watch face and mobile client actually calls; "undocumented" describes the
project's writing, not the client's dependency.

**The socket belongs here too, and this policy says so explicitly**, because it is easy
to miss. `lib/server/websocket.js` on `dev` registers client-callable `authorize`,
`dbAdd`, `dbUpdate`, `dbRemove`, `dbUpdateUnset` and `loadRetro` (measured by grepping
`socket.on('…'` at `origin/dev`). Those are **writes from third-party clients**. A change
to the shapes they accept is an API change in everything but the URL.

**The counter-argument, answered.** *"v1 is an open pass-through, so it has no contract
to break."* Decision D8 already says v1 is to be **bounded by corpus evidence**, not that
it is exempt. An open surface is a wide contract, not the absence of one.

### S2 — The plugin interface, boot sequence and client bundle. **IN, with a named limit.**

Nightscout plugins are files in `lib/plugins/`, not a published API, and forks are the
normal extension mechanism. That makes "the plugin interface" hard to state and easy to
break by accident: page bundles, a narrowed D3 import surface, a new event bus and a
reordered boot sequence (cut 2) are all invisible to S1 and all directly under a fork.

**In**, because a forked deployment is a supported way to run Nightscout and breaking it
silently is the worst failure mode this surface has. **The limit:** this policy does not
promise a stable plugin API, and says so. What it promises is that **a release that
changes the boot order, the plugin registration contract or the client event surface says
so in its notes and does not hide under a patch number.** That is a disclosure
obligation, not a compatibility guarantee, and it is the strongest promise that can
honestly be made without a plugin corpus to test against (§9, open).

**The embedding case, argued separately and OUT.** The client bundle is served, not
published; there is no npm artefact, no documented embed API, and no evidence in this
repository of anyone embedding it. Treating "anyone embedding the bundle" as a first-class
surface would create an obligation nobody can test. It is covered incidentally — a bundle
change is an S2 change — and that is where it should stay until someone produces a real
embedder.

### S3 — The environment-variable configuration surface. **IN. The most-used surface there is.**

For a self-hosted application this is the *primary* interface. Most operators never touch
the API; every operator sets environment variables, and one-click hosts encode them in
templates that outlive the operator's attention.

Three distinct events on this surface, each with a different weight:

| Event | Weight | Why |
|---|---|---|
| A new variable is read | minor | Additive; nothing an operator set stops working |
| An existing variable changes meaning or default | minor at least, major if it changes what the deployment does without the operator acting | `DEBUG_LOGGING` flipping logging off is the live example |
| A variable stops being read | **major** | The operator's expressed intent is discarded, usually silently. `DEXCOM_BRIDGE_USE_LEGACY` in cut 4 is the live example, and dev's own warning text tells operators to set it |

**Accepted-and-ignored is the worst of the three** and the policy names it explicitly,
because it produces no error, no log line and no failing test. The gate in §6 detects it
mechanically by censusing the variable names read at both refs.

### S4 — The database schema and stored document shapes. **IN, with the D4 nuance.**

Operators own their MongoDB. Their data outlives every release, and third-party tools
read and write the same collections. A change that requires a migration, or that causes a
write to drop a field it previously preserved, is an S4 change.

**The nuance that decision D4 forces:** the seam carries **two mature backends forever** —
MongoDB permanently for single-tenant, PostgreSQL for the hosted service. So "the schema"
is not one artefact, and a divergence between the two backends (BF-19, BF-21, BF-22) is a
correctness defect *within one version*, not a versioning question. **S4 is about what a
release does to an operator's stored documents**, not about backend parity. Register
entries own parity.

**The specific event this policy calls out**, because the programme has produced it:
*a non-delete write that silently discards a field it did not write.* `bf/auth`'s subject
and role allow-list does this. Data loss on an edit is a major even when the field being
removed is one that should never have been stored.

### S5 — The Node and MongoDB runtime floor. **IN, and for an application it is the loudest surface of all.**

**The strongest counter-argument in this document, stated fairly:** for a library,
`engines` is advisory. npm emits a warning and installs anyway. A library that raises its
`engines` floor has not changed one byte of its API, and plenty of well-run projects treat
that as a minor.

**Why this policy rejects that for Nightscout.** The reasoning is not "applications are
different" in the abstract; it is three measured facts.

1. **It is enforced with `process.exit(1)`.** Cut 1 introduces
   `lib/server/runtime-policy.js`, which reads `engines.node` and exits. There is no
   warn-and-continue path. The deployment does not start.
2. **The floor being replaced is not the one that is declared.** `package.json` on
   `master` and `dev` says `>=20.x`, but `lib/server/bootevent.js` enforces
   `semver.satisfies(nodeVersion, '>=16.x')`. So the *enforced* jump is 16 → 22.23.2, six
   majors, not one. (GT4 measured this; confirmed here by reading both files.)
3. **The new range is a whitelist, not a floor.** Measured with `semver.satisfies` over a
   grid of Node versions: `^22.23.2 || ^24.20.0` rejects 20.0.0, 20.19.5, 21.7.3, 22.0.0,
   22.23.1, 23.11.0, 24.0.0, 24.19.1, 25.0.0 and 26.0.0. **`>=20.x` accepts every one of those
   ten** — there is no exception in the list. (The first draft's "except the first two majors
   below it" was wrong and is corrected here; only 18.20.4, which is not in the list, is rejected
   by both ranges.) **An operator on Node 22.23.1, a current
   22 LTS, boots today and exits immediately after cut 1.** And Node 26 LTS will not start
   Nightscout until someone edits `package.json`.

For a person whose family member's glucose data flows through that deployment, "it does
not start" is the largest observable change any branch in this programme makes. If that is
not a major, the category has no content.

**A refinement the policy adds:** *narrowing* the accepted runtime range is major;
*widening* it is minor. This is mechanically decidable and the gate decides it — see the
control run in §6.3(H), where a synthetic widening is correctly classified minor.

**MongoDB is in this surface too**, and more quietly. Cut 1 drops MongoDB 4.4 from CI
without any code refusing 4.4. Nothing breaks on upgrade; the project simply stops knowing
whether 4.4 works. **Policy: removing a database version from the CI matrix is a minor and
must be stated in the notes as a change to the supported set.** It is not a major because
nothing stops working, and it is not a patch because the support statement moved.

### S6 — The ingestion paths an operator's data flows through. **IN, and this policy gives it precedence over every other surface.**

Bridge, mmconnect, nightscout-connect, uploader writes, API writes. This is the surface
where a mistake has a physical consequence: **the symptom of an ingestion failure is that
a person's glucose data stops arriving.**

**In** without argument. What deserves argument is the *weight*, and the policy sets it
higher than S1–S5:

- A change that can stop ingestion is **major**, and it is major *even when it is also
  correct, also small, and also overdue.*
- A change to a pinned connector revision is classified by **what the operator receives**,
  not by the size of the diff. `bf/connect-pin` is one line, `+1/-1`, and it carries a
  585.94× change in retry timing plus three log-redaction fixes. One line is not a patch
  argument.
- **An ingestion removal requires a deprecation release first** (§5), and this is the one
  place in the policy where the number alone is not a sufficient warning.

### S7 — The set of alarms and notifications the deployment can emit. **IN. Newly declared.**

GT4 proposed this and marked it a judgement call. **This policy adopts it and removes the
judgement flag.** The argument:

An alarm is a contract with a *person*, not with a program. Every other surface here can
be renegotiated by an operator reading release notes at a keyboard. An alarm arrives at
3 a.m. on a phone belonging to someone who is asleep, and its meaning is learned by
repetition. A deployment that begins emitting a persistent URGENT notification it has
never emitted has changed the thing the household has learned to trust, and no diff size
makes that a patch.

The live case: `lib/plugins/insulinage.js` tested `insulinInfo.age >= insulinInfo.urgent`,
and `insulinInfo` is constructed without an `urgent` key, so the comparison was `>=
undefined` — false for every age, for every operator, since the line was written. The fix
makes a `persistent`-sound URGENT notification reachable at `IAGE_URGENT` (default 72 h).
Nothing an operator configured stops working, so it is not major; a new emission arrives,
so it is not a patch. **Minor, and the release note must say in plain language that a new
alarm will start arriving.**

> **Blast radius, corrected by the verification pass — the first draft of this section had it
> in both directions at once.** Read at `origin/dev` and on `bf/alarms`:
>
> - **The push/Pushover alarm is opt-in and off by default.** `iage.getPrefs` sets
>   `enableAlerts: sbx.extendedSettings.enableAlerts || false`, and the notification is built
>   only under `if (prefs.enableAlerts && sendNotification && insulinInfo.minFractions <= 20)`.
>   `IAGE_ENABLE_ALERTS` defaults to `false` (README `dev` line 465). `sendNotification` is
>   `insulinInfo.age === prefs.urgent`, an **exact** equality, so it is one shot at exactly
>   `IAGE_URGENT` hours inside the 20-minute post-hour window. **So the new alarm reaches only
>   deployments that set `IAGE_ENABLE_ALERTS=true`, not every operator.**
> - **But the red pill reaches everyone.** `insulinInfo.level = levels.URGENT` is assigned in
>   `findLatestTimeChange` (line 96), which is the property producer, *not* in
>   `checkNotifications`, and it sits outside the `enableAlerts` guard. `updateVisualisation`
>   reads that level and sets `pillClass = 'urgent'`. So on every deployment, with no opt-in,
>   the IAGE pill turns urgent-red once the reservoir passes `IAGE_URGENT` hours.
>
> Both effects are minors, and the ladder's answer does not change. The operator-facing note
> must describe **both**, and must not imply a new siren is coming to every household.

**Why this surface needs its own name rather than living inside S2:** a plugin-file rule
would have to fire on every `lib/plugins/` edit, which is most edits. S7 asks one question
instead, and it asks it about behaviour rather than about paths. §6.3 shows why the
question cannot be answered by grep.

### S8 — The version string itself. **IN. Newly declared, and the cheapest of all.**

Not a surface in the semver specification's sense, but a surface an operator, a support
volunteer and a bug reporter all depend on. Measured with `git show <ref>:package.json` at
**sixteen refs** (`master`, `dev`, the five cut tips, the nine `bf/*` branches): `master` is
`15.0.8` and **the other fifteen all carry `"version": "15.0.9"`**. Among the six that are
release candidates in their own right — `dev` and the five cuts — there are two different
`engines.node` values, and one of the six deletes two CGM ingestion paths. The string is
also **live**, not merely a file: `lib/server/env.js:137` copies it to `env.version` and
`lib/api/status.js:32` returns it, so every deployment on the `dev` channel already answers
`/api/v1/status` with `15.0.9`. An operator reporting "my 15.0.9 will not start" cannot be
triaged from the string. *(Count and the `/api/v1/status` route added by the verification
pass; the first draft said "six artefacts" here and "fifteen" in §7 D-a.)*

**Policy: a build that is not the release its version names must say so in its version
string** — a pre-release identifier is enough (§5.1). This costs one line per branch and
closes the problem completely.

### Candidates argued OUT

| Candidate | Verdict | Why |
|---|---|---|
| Internal module layout, `lib/**` requires | **out** | No supported consumer. A fork that requires an internal path is on notice by definition; it is covered incidentally by S2's disclosure duty |
| Log line text and format | **out as a contract**, in as a note | Operators grep logs and tooling parses them, but promising log stability would freeze every diagnostic. Removing a log line an operator was told to look for is an S3 event, not an S-of-its-own |
| Performance | **out** | `bf/cache`'s 0.837 ms → 0.025 ms is not a version event. It becomes one only if it changes what is returned |
| Test-suite layout and CI structure | **out**, except the supported-matrix statement in S5 | Contributor-facing |
| The client bundle as an embeddable artefact | **out** | See S2. Revisit when a real embedder exists. **Do not read this row as putting client *behaviour* out** — the enumeration has no surface for what the browser computes and shows, which is a hole, not a verdict. See §3.8 (candidate S9) |
| Documentation | **out**, but a deprecation announcement is not documentation — §5 |

---

## 2. The decision procedure

Short enough to use in review. Answer in order; **stop at the first yes.**

### MAJOR — any one of these

1. Does a supported deployment that starts today **fail to start**, or start into an error
   page, without the operator changing something? *(runtime floor, new required variable,
   boot error)*
2. Does any **ingestion path** stop working, or need reconfiguration to keep working?
3. Is a **capability removed or narrowed** — an endpoint, a parameter's effect, a request
   header that was honoured, an ingestion source, the ability to run two sources at once,
   a configuration key's meaning?
4. Does an input that a **real client sends**, and that returns 2xx today, now return
   4xx/5xx?
5. Does an operation that is **not a delete** lose stored data, or does stored data need
   migrating?
6. Does an existing **credential, token or session** stop working?
7. Does a configuration key become **accepted and ignored**?

### MINOR — any one of these

8. Can an **alarm or notification** fire that could not fire before, fire at a different
   level, or fire louder? *(Never waivable. See the standing rules.)*
9. Is something **added**: an endpoint, a response field, a configuration key, an accepted
   input, a plugin, a supported runtime?
10. Does any request return a **different set of records**, or a differently-shaped body,
    for the same query — **including empty becoming populated, and including a wrong
    answer becoming right**?
11. Does a **default** change: logging verbosity, retry timing, a limit, a sort order, a
    unit, a bundled image?
12. Does the **supported set** change — a database version leaving CI, a runtime being
    added?
13. Does a dependency that **renders, charts, styles or serves** anything an operator sees
    move by a major?

**A gap in this ladder, named rather than hidden.** Questions 1–13 are server-, HTTP- and
configuration-shaped. A change confined to what the **browser computes and shows a person** —
the bolus calculator's inputs, a pill's value, the page continuing to advance — answers "no"
to every one of them and falls through to patch. That is how BF-35, the highest-severity
defect in this batch, classifies as a patch with no release-note obligation. **Read §3.8
before using this ladder on anything under `lib/client/`.**

### PATCH — otherwise

The claim a patch makes, which a reviewer must be able to say out loud about the diff:

> *For every input a supported client actually sends, the bytes on the wire and the
> emissions from the deployment are the same as before.*

If that sentence cannot be said, it is not a patch.

### Four standing rules that override the ladder

- **R1. "It was a bug" is not a defence at any level.** Correctness decides *whether to
  ship*; observability decides *the number*. They are different questions, and a fix can
  be a major. This is the single largest departure from current practice.
- **R2. Question 8 is never waived.** An alarm is a contract with a person.
- **R3. A release is classified by its loudest change, not its median.** One major row
  makes the release major. The remedy is to **split the release**, not to round down.
- **R4. Classify by what the operator receives, not by the size of the diff.** A one-line
  dependency pin that changes retry behaviour by 585.94× is classified as that change.

### The one rule about *not* using this procedure

**A version number is not a substitute for a test.** Where this document recommends a
major, it is because operators must be warned, never because the change is risky and the
number will absorb the risk. The clearest case is D3 5.16 → 7.9: the honest problem is the
absence of real-browser coverage, and neither a major nor a patch makes an untested chart
render correctly. See §3.7.

---

## 3. The hard cases this programme has produced

Each is real, each recurs, and each is answered with the reasoning rather than a verdict.

### 3.1 A fix that makes a query start returning rows it previously, wrongly, omitted

*The case: `bf/coercion`. `find[duration][$gte]=30` produced `{"$gte":"30"}` — a string
compared against a numeric field — and matched nothing. It now produces `{"$gte":30}` and
matches. `find[insulin][$gte]=1.5` produced `{"$gte":1}` and now produces `{"$gte":1.5}`.
158 schema-driven coercions over five collections. (Old and new `query.js` executed
side by side by GT4; the operand semantics cross-checked against the `mingo` oracle, D8.)*

**Answer: MINOR. Correcting a wrong answer is a behaviour change.**

The instinct to call it a patch comes from a library habit: nobody *depended* on the wrong
answer, so nothing *broke*. That reasoning does not survive contact with an application.
The thing an operator interacts with is the answer, not the intent. A report that plotted
an empty chart now plots a full one. A dashboard that showed no temp basals now shows
thousands. Somebody has a saved filter whose meaning silently changed under them.

**The sharper form of the question — "what if clients adapted to the wrong answer?" — is
answered separately, and the answer is that it makes it worse, not better.** A client that
compensated for a broken filter (fetching wider and filtering locally, say) now
double-filters or double-counts. Adaptation is evidence *for* the minor, not against it:
it proves the wrong answer was load-bearing.

**Where the line actually is.** Not "wrong → right" versus "right → right", which is
unknowable from a diff. It is:

> Does the **set of records**, or the **shape of the body**, change for a request a client
> can send? If yes, minor. If the change is confined to internals — caching, cloning,
> logging, query plan — patch.

`bf/cache` sits cleanly on the patch side of that line: identical bytes, less copying.
`bf/coercion` sits cleanly on the minor side.

**The safety-relevant consequence, which is the part that must not be lost.** `bf/coercion`'s
own CHANGELOG says earlier results may have under- or over-reported delivered therapy.
That sentence must survive verbatim into the operator-facing release note. A person may
have looked at a total-insulin report built on a broken filter. The version number is
bookkeeping; that sentence is the actual warning.

### 3.2 A fix that adds restrictions — `?count=0x10` and `?count=2.5` now return 400

*The case: `bf/reads`. Measured by GT4 by executing the new `lib/server/count.js` against
a transcription of the old `if (opts && opts.count) return this.limit(parseInt(opts.count))`:
`0`, `0x10`, `2.5`, `-3`, `1e2`, `abc` and integers above `MAX_SAFE_INTEGER` now return
HTTP 400. Previously `?count=0` returned **the whole collection** (`limit(0)` is
unbounded in MongoDB). The validator is `app.use`-mounted on the whole v1 app before every
router, so it covers `/treatments`, `/profile`, `/devicestatus`, `/food`, `/status`,
`/alexa`, `/googlehome` and **writes**: `POST /api/v1/treatments?count=0` now fails.*

**Answer: as written, MAJOR. And the right move is not to ship it as written — split it,
and both halves become MINOR.**

The general rule first:

> **Narrowing accepted input is MAJOR if a real client can send the narrowed input, MINOR
> if no client that could plausibly exist would send it.** "Plausibly exist" is not
> "exists in our tests" — the burden is on the author to name why nobody sends it, not on
> the reviewer to produce a victim.

Applying it to the six spellings shows they are **not one change**:

| Spelling | Could a real client send it? | Verdict |
|---|---|---|
| `abc`, `0x10`, `1e2`, `2.5`, `-3`, `>MAX_SAFE_INTEGER` | No. Every one is a typo or a hand-written URL, and every one silently returned a count unrelated to the request | **minor** — the answer was never meaningful, so no behaviour anyone relies on is removed |
| `0` | **No client sends it as a literal; 9.1 % of call sites compute it, and a computed count is not bounded away from zero** | **major** as written — but see the census immediately below, which the first draft did not cite |

> **The measurement this section was missing** (added by the verification pass). A corpus
> census of `count=` already exists in this repository and was not cited:
> [`docs/60-research/tenancy/seam-limit-and-projection-2026-09-14.md`](../../60-research/tenancy/seam-limit-and-projection-2026-09-14.md)
> §2, from `tools/qc/v1_count_census.py`. **274 `count=` occurrences across 10 client
> projects: 236 literal (86.1 %), 25 computed at request time (9.1 %), 11 prose, 2 other.
> No client sends a literal `count=0`** — the literal values observed are `1, 2, 3, 5, 10,
> 20, 24, 50, 100, 288, 500, 1000, 1500, 10000, 100000, 9999999`. The census reads client
> *source*, not request logs, because there are no request logs.
>
> So the honest statement is **latent, not observed**: the exposure is the 9.1 % of call
> sites that build the count at runtime (`'&count=' + n`), where nothing bounds the value
> away from zero; `oref0`, the closed loop, has four such sites. The census's own author
> graded BF-14 *medium* partly on "no shipping client triggers it". **A maintainer who
> weighs that census more heavily than the argument below can reasonably reject the split
> in this section and ship all six rejections today.** That is §10 item 1, and this is the
> evidence for it.

`?count=0` is reachable the way sync tools are written. "Fetch the last *N* entries I do
not already have" evaluates to zero exactly when the client is up to date, which is most
of the time. *This is an inference about how such clients are built, supported by the 9.1 %
dynamic arm above; it is not an observation of a request.* Today that client receives the whole collection — wasteful, slow, but a 200
with data it can ignore. After this change it receives a 400, and a client that treats 400
as fatal stops syncing. **For a Nightscout user, a sync tool that stops is glucose data
that stops arriving.** That is the same class of harm the programme has already agreed to
slow down for in cut 4, and it should not be treated differently because the diff is
smaller.

**The counter-argument is strong and this policy does not bury it.** `limit(0)` is an
unbounded collection download — a denial of service against the operator's own database,
reachable by anyone who can read. Leaving it open to protect a hypothetical client has a
real cost, paid by the operator.

**Which is why the resolution is to split rather than to choose.** Reject the five
meaningless spellings now (minor, no deprecation needed — nothing meaningful is removed),
and for `?count=0` **clamp rather than reject**: treat it as the endpoint's default limit,
return `Deprecation: true` with a `Warning` header naming the value and the version that
will start rejecting it, log it once per process. That closes the unbounded-download hole
*immediately and completely* — which rejecting also does, no faster — while giving the
one reachable input a release in which it is warned. Both halves are minor; the hole shuts
today; nobody's sync silently dies.

**If the maintainer ships it as written anyway**, the policy's answer is major and the
release notes must name `?count=0` and the write-path scope, which the branch's current
CHANGELOG does not.

**The asymmetry with v3 `?limit=0x10`, which this policy keeps.** v3's limit is a
*documented closed contract*: `API3_MAX_LIMIT` is described in
`lib/api3/swagger.json` (verified by grep at `origin/dev`) and the endpoint already has a
400 path. `?limit=0x10` was escaping a ceiling the contract says exists. **Restoring a
documented bound is not the same act as inventing one**, and it is a minor.

### 3.3 An alarm that starts firing for operators who have never received it

*The case: `bf/alarms` `8714093b`, insulinage's URGENT branch. See S7.*

**Answer: MINOR, and the strictest disclosure obligation in this policy.**

Why not major: nothing an operator configured stops working; there is no action they must
take; no data is lost. Under the ladder, that is a minor.

Why the disclosure is stricter than any other minor, and why R2 makes question 8
unwaivable:

1. **The operator cannot have tested it.** Every other behaviour change can be exercised
   on a staging deployment in five minutes. This one requires a reservoir to be 72 hours
   old and the 20-minute post-hour window to come round. Nobody will see it before it
   arrives for real.
2. **The audience is not the operator.** It is whoever holds the phone. In this community
   that is frequently a parent, a partner, or a school nurse who was never told the
   deployment was upgraded.
3. **Alarm meaning is learned by repetition, and this one arrives with `persistent`
   sound.** A household that has calibrated on "URGENT means glucose" gets an URGENT that
   means "change your insulin reservoir". Re-teaching that is the operator's work, and the
   release note is how they learn they have to do it.

**Therefore the policy attaches three obligations to any S7 change**, and a PR that
cannot satisfy them is not ready regardless of its number:

- The operator-facing note says **what will arrive, when, at what level, with what sound,
  and how to turn it off** (here: `IAGE_ENABLE_ALERTS`, `IAGE_URGENT`).
- The note names the **default** that decides whether it fires, because most operators
  never set these and will get the default. **For this case the default is
  `IAGE_ENABLE_ALERTS=false`** (measured: `iage.getPrefs` in `lib/plugins/insulinage.js`,
  README `dev` line 465), so the *sound* reaches only operators who turned alerts on —
  while the urgent-red IAGE pill reaches everyone, because the level is set in
  `findLatestTimeChange` outside that guard. A note that says only "a new alarm is coming"
  is wrong for most readers and a note that says only "a pill turns red" is wrong for the
  rest. See the correction block in §1 S7.
- It does **not** simplify the algorithm. "Your reservoir alarm now works" is not
  adequate: it does not tell someone that a new persistent sound is coming at 72 hours.

**The general rule this case establishes:** *making an unreachable branch reachable is a
behaviour change of exactly the size of the branch.* A dead URGENT alarm is not a dead
line of code; it is a missing alarm, and restoring it is an addition.

### 3.4 Raising the Node floor — cut 1

**Answer: MAJOR.** The argument is in S5 and is not repeated. Three practical additions
the number alone does not carry:

1. **Prefer `>=22.23.2` to `^22.23.2 || ^24.20.0`** unless there is a known
   incompatibility with an odd-numbered major, in which case name it in the PR. The
   whitelist form excludes Node 21, 23, 25 and everything after — **measured**: Node 26.0.0
   fails `semver.satisfies('26.0.0', '^22.23.2 || ^24.20.0')`. That is a recurring
   maintenance obligation created by the notation, not by any incompatibility. A floor
   does not create it.
2. **The declared floor and the enforced floor must be the same thing.** They are not
   today: `engines` says `>=20.x`, `bootevent.js` enforces `>=16.x`. Cut 1 fixes this by
   deriving the check from `engines`, which is the right design and should be stated as
   policy: **`engines.node` is the single source of truth for the runtime floor, and
   every other statement of it is generated or checked against it.** Six files state it
   independently today (`.nvmrc`, `bin/setup.sh`, `azuredeploy.json`, `README.md`,
   `CONTRIBUTING.md`, `docs/meta/architecture-overview.md` — GT2's measurement), and a
   one-field revert leaves all six stale.
3. **A runtime floor needs a deprecation release like an ingestion removal does**, for the
   same reason: the symptom is total, and the operator finds out by their site being
   down. §5.4 sets the window.

**The narrow-versus-widen rule** (S5) is what keeps this from being a blanket tax: adding
Node 26 to the accepted set is a minor, and the gate says so.

### 3.5 Deleting an ingestion path — cut 4

**Answer: MAJOR, and the number is the least of what it needs.**

The measurement (GT4, executing the shipping shims from `origin/chore/mime-exposure-review`
under `node`) shows the consequence is worse than "two ingestion paths are deleted":

- An operator with `MMCONNECT_*` and no `CONNECT_COUNTRY_CODE` gets `{migrated:false,
  error:…}`, which becomes a `ctx.bootErrors` entry, which makes `lib/server/app.js:202`
  install `app.get('*', bootErrorView)` and `lib/server/server.js:61` skip websocket
  setup. **The whole deployment serves the boot-error page.** Not degraded ingestion: no
  API, no sockets, no charts.
- The shim states the country **cannot be inferred** from `MMCONNECT_SERVER`, so there is
  no configuration in which the migration is automatic. Every one of these operators must
  set a new variable by hand.
- An operator running `BRIDGE_*` and `MMCONNECT_*` together — which works today as two
  independent boot stages — gets the same total outage. **Concurrent multi-source CGM
  ingestion is removed**, and that removal appears in no summary of the cut.

**What the policy requires beyond the number**, and this is the part a version cannot do:

1. **A deprecation release first** (§5.4), shipping `mmconnect-connect-compat.js` *without*
   deleting `lib/plugins/mmconnect.js`, warning and continuing to run.
2. **A boot error is never an acceptable deprecation mechanism.** If a migration cannot be
   automatic, the release that introduces the requirement warns and keeps running; only a
   later release refuses to boot.
3. **Fix the version strings in the shims.** Both say *"retired in Nightscout 15.0.9"*,
   and on the adopted train 15.0.9 retires nothing. An operator who reads that and checks
   the release notes finds a contradiction. The string must name the version that actually
   deletes the plugins, and every deprecation warning must name the same one.

**The general rule:** *an ingestion removal is major, requires a deprecation release, and
requires that the failure mode during the window be "warn and keep ingesting" rather than
"stop".* A version number does not protect anybody; the warning release does, and the
number's only job is to make the warning release findable.

### 3.6 A retry-timing change of 586× that makes outage recovery look slower — BF-34

*The case: `nightscout-connect` `lib/backoff.js` merged options as
`{...config, ...defaults}` — defaults **last** — so every value a caller passed was
discarded. All five vendor sources configure a 2.5-minute retry interval; every one got
the 256 ms default. Measured by executing both versions: the ratio is **585.94× exactly**
(150000/256) at every attempt below the ceiling — a constant, not an average. Uncapped,
attempt 20 is 4.99 years, which is why the precedence fix could not ship alone;
`lib/builder.js:89` supplies `max_interval_ms = expected_data_interval_ms * 6`, so the
**shipped ceiling is 30 minutes for four of the five sources** — `dexcomshare`,
`minimedcarelink`, `glooko` and `nightscout` each declare
`expected_data_interval_ms: 5 * 60 * 1000`. The fifth, `librelinkup`, derives it from
`opts.linkUpInterval * 60 * 1000` (`lib/sources/librelinkup.js:220`), so **its ceiling is
whatever the operator configured × 6** and is not 30 minutes unless the interval is 5.
(Qualification added by the verification pass; the first draft said "the shipped ceiling is
30 minutes" without exception.) With the new `'equal'` jitter the delay at the ceiling
spreads over [15 min, 30 min] (2,000 samples at attempt 10 fell in
[900,351 ms, 1,799,757 ms]).*

**Answer: MINOR in `cgm-remote-monitor` (it is a default change, rule 11). A `y` bump in
`nightscout-connect` — see §4. And the release note is the entire point.**

This is the case where the number is least informative and the note matters most, because
**the change looks like a regression from the operator's chair and is not one.**

What an operator sees: the vendor has an outage; previously the connector hammered it
every quarter-second and data resumed the instant the vendor did; now data can take up to
half an hour to resume. That is a worse experience in the only moment it is visible.

What is actually true, and must be said in operator language without simplifying it away:

> **After a Dexcom or CareLink outage, readings may take longer to start arriving again than
> they used to — up to about half an hour in the worst case.** "The connector" is the part of
> Nightscout that logs in to Dexcom or CareLink and fetches your readings for you. It now
> waits the gap its authors intended between attempts, instead of retrying several times a
> second. Retrying that fast never helped: it could not make Dexcom or CareLink answer any
> sooner, and because every Nightscout site was retrying at the same moments, a whole group
> of sites could be refused together for asking too often — which made the outage **longer**
> for everybody, not shorter.
>
> **How to tell the difference between "waiting to retry" and "something is actually wrong."**
> This is the part that matters, because a pause looks exactly like a failure until it ends.
> Your site already watches for this on its own: by default it shows a warning when no new
> reading has arrived for **15 minutes** and an urgent alarm at **30 minutes**
> (`ALARM_TIMEAGO_WARN_MINS` and `ALARM_TIMEAGO_URGENT_MINS`, both on by default). **Because
> the new worst-case wait is about 30 minutes, an ordinary vendor outage can now reach that
> urgent stale-data alarm where before it would not have.** If readings come back within
> about half an hour and then continue normally, nothing is broken. If they do not come back,
> or the gap repeats, check that your Dexcom or CareLink password still works and look at the
> site's logs.
>
> If your readings stop, treat it the way you already treat a sensor you cannot see — use your
> meter and your usual routine. **Nightscout is not a medical device and nothing here is
> medical advice; if a gap in your data affects decisions about your therapy, talk to your
> care team.**

**The rule this case establishes:** *a change that trades a visible fast-failure for an
invisible systemic improvement is classified as a default change (minor) and carries a
release note that states the visible cost first and the reason second.* Burying the cost
is what turns a good change into a support incident.

There is a second, sharper thing here that the number cannot express: the fix **also**
removes the lockstep. `use_random_slot` was forced false, so a pool that failed together
retried together. Measured with the upstream refusing authentication, 100 actors delivered
the same 800 requests across 3 s before and 67 s after. The note should say that too, in
plain language, because it is the part that helps other people's data arrive.

### 3.7 A two-major dependency upgrade with no API change, no browser coverage — D3 5.16 → 7.9

**Answer: MINOR under rule 13 — and the number is not the problem. Say so out loud.**

Under the ladder: none of S1–S8 moves. No endpoint, no variable, no schema, no runtime
floor, no ingestion path, no new emission. Rule 13 catches it — a dependency that *renders*
what an operator sees moved by two majors — and that makes it a minor. It is not a major,
because nothing forces an operator to act.

**But the honest statement is that the version number is not what is wrong with shipping
D3 here.** D3 v6 removed `d3.event` and changed every handler signature; v7 continued the
module reshuffle. The upgrade reaches `lib/client/renderer.js`, `lib/client/chart.js` and
`lib/report_plugins/daytoday.js` (GT2's measurement of `48075a18` — and note GT2 also
found that `lib/plugins/cob.js` +49/−73, currently filed under the D3 heading in
release-readiness §2, is **not** D3 work but `34e9b2da`, a behaviour change to
carbs-on-board reporting, more than twice the size of the whole D3 migration, with no line
of its own in the release decision).

What the coverage actually is, measured by GT2: `dev` does have
`tests/dependency-d3.test.js`, 218 lines, 24 passing, driving the real renderer and chart
against the D3 7 browser bundle — **and it is non-vacuous**, catching a revert of the
mouseover handlers to the D3-5 signature and a break of `d3.pointer`. The gap is narrower
and sharper than "no coverage": jsdom's geometry is stubbed (`getBoundingClientRect` is
fixed at 900×600), and **both treatment-drag clamps at `renderer.js:764` and `770-771`
are completely unexercised** — 24/24 still pass with both deleted, because the handler is
only ever invoked with x ∈ {20, 400}, strictly inside the clamp. Those clamps bound a
user-initiated rewrite of a treatment's `created_at`, emitted over the socket, and a
treatment's timestamp is what IOB and COB key off.

**So the policy's answer has two halves and the second is the load-bearing one:**

- **Number:** minor.
- **Gate:** a dependency major that reaches rendering code **requires a real-browser pass
  before the release ships**, recorded in the PR. Either land cut 1's Playwright suite
  first, or have a human open the chart, drag a treatment to each edge of the plot, and
  open the COB pill on a real deployment, and say so by name in the PR.

**The rule:** *a version number is never accepted as mitigation for absent coverage.* A
major would not make an untested chart render correctly, and a patch does not make it
render incorrectly. Where this document is tempted to raise a number because a change
feels risky, that is the signal to require the test instead.

### 3.8 A client-side calculation that gave the wrong number — the case the ladder cannot see

*Added by the adversarial verification pass. This is a **hole in §1's enumeration and in §2's
ladder**, not a classification the document got wrong, and it is left as an open decision
rather than silently patched into the surface list.*

*The case: `bf/food` `73495331`, register entry **BF-35**, graded **high**. Measured in the
register and confirmed here by reading the branch: `lib/client/boluscalc.js`
`loadFoodQuickpicks` builds the `<option>` list by iterating the **whole food collection**
and using the array index as the option's `value`, while `quickpickChange` looks that index
up in `quickpicks`, the **filtered** array. The two agree only when every food record is a
quick pick. The register's reproduction in jsdom: picking the option labelled
`Breakfast (45 g)` loads **Lunch (70 g)**; picking the last option throws. The register's own
severity line reads: "the carbs that reach the insulin calculation come from a record the
user did not choose, **with no error shown**." A regression from `3457de5b`, 2017.*

**What this policy, as written before this pass, says about it: PATCH.** Walk the ladder.
No deployment fails to start (1). No ingestion path stops (2). No capability is removed (3).
No 2xx becomes 4xx (4). No stored data is lost (5). No credential breaks (6). No key becomes
accepted-and-ignored (7). No alarm changes (8). Nothing is added (9). **No request returns a
different set of records** — the HTTP responses are byte-identical; the defect and the fix are
entirely inside the browser (10). No default, supported set or rendering dependency moves
(11, 12, 13). Every question answers "no", so it falls through to patch, and §5.6's
release-note obligations attach only to minors and majors — so **no note is required at all.**

**And the gate agrees, which is how the hole was found.** Run, today:

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

`lib/client/` is mapped to **S2**, whose only question is about *forks*. Answered honestly —
no fork needs editing — `bf/food` scores `REQUIRED: NONE`. The same run on `bf/merge`
(**BF-36**: the client's delta merge read past the end of an array and threw, and the throw
escapes into `dataUpdate`, which has no `try`/`catch`, so **the page stops advancing until it
is reloaded**) asks only `Q-REMOVE` and `Q-PLUGIN` and likewise scores `NONE`.

**Why that is the wrong answer for this application, and why it is not fixed here.** S1–S8
were argued from the premise "everything an operator, or a program an operator runs, can
depend on without reading the source." A person reading a number off the bolus calculator is
depending on it in exactly that sense, and more directly than on any HTTP contract in S1.
The enumeration reads as though the browser were a rendering detail of the server, and for a
self-hosted diabetes application it is the product. Two of the nine Phase 0 branches change
only client behaviour, and one of them is the highest-severity defect the programme found
this week.

**The candidate this pass proposes, for the maintainer to accept or reject — it is not
adopted here, because adding a ninth surface changes §2, §6 and §8 together:**

> **S9 — What the client computes and shows to a person. Candidate, IN.** The displayed
> value, the calculator's inputs and result, the chart, the pills and the page continuing to
> advance. Weight: **minor at least** whenever the number, the record or the reachability of
> the page changes, on the same reasoning as §3.1 — the thing a person interacts with is the
> answer, not the intent — and with S6's precedence argument applying whenever the value
> feeds a therapy decision.
>
> The matching gate question, which `lib/client/**` and `lib/plugins/**` would both raise:
> **`Q-SHOWN` — does any number, record or chart a person reads change, or does the page
> stop or start updating?**
>
> The matching §5.6 obligation, which is the part that actually protects someone: **a fix to
> a therapy-adjacent calculation names, in plain language, what was wrong, over what period,
> and what a person should do about decisions they already made on it.** For BF-35 that
> sentence is not optional and it has no draft anywhere in this programme. The model is
> §3.1's treatment of `bf/coercion`'s "earlier results may have under- or over-reported
> delivered therapy" — and BF-35 is the stronger case, because a wrong carb count reaching a
> bolus calculation is a dosing input, not a report.
>
> Note what S9 would *not* do: it would not make BF-35 a major. Nothing an operator
> configured stops working. It makes it a **minor with a mandatory operator-facing note**,
> which is the whole of what is missing.

**Until S9 is decided, the honest statement is that this policy classifies BF-35 as a patch
and requires no note for it.** That is recorded here rather than quietly repaired, because a
reader who acts on §2 today will get that answer, and the gap should be visible when they do.

### 3.9 A note on what §3.8 implies for the Phase 0 numbering

Nothing in §8 changes on the strength of §3.8 — `bf/food` is already a minor there for a
different reason (the `/api/v1/food/quickpicks` filter change, which *is* an S1 event) and
so travels in the 15.1.0 parcel either way. **What changes is the note, not the number**, and
§8.2's option 1 should be read as carrying that obligation.

---

## 4. 0.x versioning for nightscout-connect

### 4.1 The npm resolution rule, stated precisely

npm's caret is **not** uniform across the 0.x range. Measured with `semver.satisfies`
(`semver` 6.3.1 — the version the inspected repo resolves — Node v24.15.0):

| range | 0.0.13 | 0.0.14 | 0.1.0 | 0.1.9 | 0.2.0 | 1.0.0 | 1.3.0 | 2.0.0 |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `^0.0.13` | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| `^0.1.0`  | ✘ | ✘ | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ |
| `~0.0.13` | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ |
| `^1.2.3`  | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ | ✘ |

The rule in words: **the caret floats everything below the leftmost non-zero component.**
For `^1.2.3` that is the major, so minors and patches float. For `^0.1.0` it is the minor,
so only patches float. For `^0.0.13` it is the patch, so **nothing floats — `^0.0.13`
matches exactly `0.0.13`.**

This is why `0.0.z` is a dead letter as a communication channel: npm already treats every
`0.0.z` bump as potentially breaking, so the number carries no information a consumer can
act on, and the convention the ecosystem actually applies — **in `0.y.z`, `y` behaves as
the major and `z` as the minor-and-patch combined** — is the one npm's own operators
encode.

### 4.2 Applying it, and correcting the premise

**The brief and `phase0-pr-sequencing-2026-09-15.md:388` both say `master` depends on
`"^0.0.12"` from npm. That is wrong, and GT4's correction is confirmed here by reading
`origin/master:package.json` directly:**

```
"nightscout-connect": "https://github.com/nightscout/nightscout-connect/archive/refs/tags/v0.0.13.tar.gz"
```

Every pin in flight is a **tarball URL**, not an npm range. Measured at **eight refs**, which
carry **five distinct pin values**. (The first draft said "all four pins ... at all seven refs";
GT4's "four" excluded the unpushed `bf/connect-pin`, and the table below is eight rows' worth of
refs, not seven.)

| ref | pin |
|---|---|
| `origin/master` (15.0.8) | `refs/tags/v0.0.13.tar.gz` |
| `origin/dev` (15.0.9 candidate) | commit `234d47c8` |
| cuts 1, 2, 3 | `refs/tags/v0.0.13.tar.gz` |
| cut 4 `chore/mime-exposure-review` | commit `c962a13f` |
| cut 5 `chore/nightscout-modernization` | commit `b77e5bb` |
| `bf/connect-pin` | `refs/tags/v0.0.14.tar.gz` |

The `^0.2.12` that does appear on master is **`share2nightscout-bridge`**, a different
package. So there is no npm-range pin anywhere in the tree and never a floating one.

**This makes the version-number choice cost nothing and mean everything.** Nothing
resolves by range, so no consumer's resolution changes whichever number is chosen. The
number's entire job is to make a human stop.

### 4.3 The policy for nightscout-connect

> **While `nightscout-connect` is below 1.0.0, `0.y.z` is read as `y` = major, `z` =
> minor-and-patch. A change that would be major under §2 bumps `y`. Everything else bumps
> `z`.**

**Applied to 0.0.13 → v0.0.14 (`b394411` → `649a7de`, fast-forward, 29 files +1362/−312,
of which 887 lines are new tests): this is a `y` bump. It should be `0.1.0`, not
`0.0.14`.** Five caller-visible changes, each independently breaking (measured by
executing `lib/backoff.js` at both revisions):

1. option precedence reversed — `{...config, ...defaults}` → `{...defaults, ...config}`;
2. a changed default — `use_random_slot: false` → `jitter: 'equal'`;
3. a new throw — `backoff({jitter:'wild'})` now throws
   `backoff: unknown jitter mode "wild"` where it previously accepted anything;
4. a new option, `max_interval_ms`;
5. `duration_for` is now non-deterministic where it was deterministic.

(1) alone is §2 question 3: a caller's configured value went from ignored to honoured, and
the resulting timing moved by 585.94×.

**Two things that do not change with the number, and must not be quietly dropped:**

- **`package-lock.json` stays on the old SHA until the tag is pushed.** Its `integrity` is
  a hash over the tarball GitHub generates, which does not exist until then. A locally
  invented hash breaks `npm ci` for everyone; leaving the lock stale makes `npm ci` fail
  **loudly** as out of sync, which is the correct failure. Regenerate with `npm install`
  after the tag is pushed, **in the same PR**. This is already the position taken on
  `bf/connect-pin` and it is right.
- **A tarball pin means the consumer's release note must carry the connector's breaking
  notes.** Nobody reading `cgm-remote-monitor`'s `package.json` sees a version number at
  all. The `+1/-1` diff of `bf/connect-pin` is the only place the 585.94× change surfaces
  in the consuming repository, which is precisely why R4 exists.

**If the maintainer prefers to stay on `0.0.z`** — a defensible preference; plenty of
pre-1.0 packages never leave it — then the release **must** carry a `BREAKING` section in
its notes, because the number will not carry it. The policy accepts that trade explicitly
rather than pretending the number is mandatory.

**On reaching 1.0.0:** out of scope here, but worth one line so it is not decided by
accident. The natural trigger is `cgm-remote-monitor` pinning connect by **version range
rather than tarball**, because that is the moment a number starts resolving something.

---

## 5. Pre-release and deprecation conventions

### 5.1 Pre-release identifiers, and the cheapest fix in this document

Semver precedence: `16.0.0-alpha.1` < `16.0.0-rc.1` < `16.0.0`. npm will not install a
pre-release under a plain range unless asked. Both properties are what this project needs.

> **Policy: a branch that is not the release its version names carries a pre-release
> identifier.**

Applied to the tree as it stands, this is a one-line change per branch and it closes S8
completely:

| branch | today | proposed |
|---|---|---|
| `origin/dev` | `15.0.9` | `15.1.0-rc.1` (see §7 for why 15.1.0) |
| `chore/retire-jsdom` | `15.0.9` | `16.0.0-alpha.1` |
| `chore/build-runtime-separation` | `15.0.9` | `16.1.0-alpha.1` |
| `chore/compose-mongodb6` | `15.0.9` | `17.0.0-alpha.1` |
| `chore/mime-exposure-review` | `15.0.9` | `18.0.0-alpha.1` |
| `chore/nightscout-modernization` | `15.0.9` | `17.0.0-alpha.2` |
| the nine `bf/*` branches | `15.0.9` each | `15.1.0-rc.1` once rebased on the renumbered `dev`, or left alone if they land *into* `dev` before it is cut |

The numbers are §7's proposal and move with it; **the identifier is the point.** Today
**fifteen** refs report `15.0.9` — `dev`, the five cut tips and the nine `bf/*` branches
(§7 D-a, `git show <ref>:package.json` at sixteen refs) — and six of those differ in Node
floor or ingestion path. A support volunteer cannot tell them apart.

*(Corrected by the verification pass: the first draft said "six artefacts" here and
"fifteen" in D-a, and its table omitted the nine `bf/*` branches. The `bf/*` row is the
cheap case — they are meant to be merged into `dev`, so they inherit whatever `dev` is
numbered; the row exists so nobody reads "closes S8 completely" as covering refs the table
never listed.)

### 5.2 How a deprecation release is numbered

> **A deprecation release is a MINOR.** It adds warnings, adds compatibility shims, and
> removes nothing. It must not be a patch, because it changes what a deployment emits
> (new log lines, a UI banner) and often adds a configuration key operators are being
> asked to set. It must not be a major, because nothing has broken yet — and calling it
> major spends the operator attention that the actual removal release needs.

The removal that follows it is the major.

**The deprecation release must ship the escape route, not merely the warning.** For cut 4
this means shipping `mmconnect-connect-compat.js` *without* deleting
`lib/plugins/mmconnect.js`, so an operator can set `CONNECT_COUNTRY_CODE` at leisure and
verify it works **while the old path still runs**. A warning that cannot be acted on
without downtime is not a deprecation; it is a countdown.

### 5.3 What a deprecation announcement must contain

Every one of these, or it does not count as having started the window:

1. **The exact setting or endpoint** being removed, spelled as the operator spells it.
2. **The replacement**, with the exact new setting and a worked example.
3. **The version that will remove it**, named. Not "a future release."
4. **What happens if they do nothing** — stated concretely. "MiniMed data will stop
   arriving" and "your site will not start" are different sentences and only one of them
   is true for a given change.
5. **Where to ask for help.**

And the announcement must reach **at least two channels**: the boot log *and* an in-app
banner. A log line is not a deprecation notice for a household — nobody reads the log of a
service that is working. This is a real code obligation, not a documentation one, and it
is the single most valuable addition this section makes.

**Announced removal versions do not move earlier.** They may slip later. An operator who
planned around "removed in 18.0.0" must not be overtaken.

### 5.4 How long the window should be

The variable that matters is not how long the code takes; it is **how long it takes news
to reach a self-hoster who is not looking.** Nightscout deployments routinely run
untouched for a year or more; many operators upgrade only when something breaks; and the
person who set it up is often not the person depending on it.

> **Policy — minimum windows, measured from the deprecation release being generally
> available to the removing release shipping:**
>
> | Change | Window | Extra requirement |
> |---|---|---|
> | Any behaviour change needing operator action | **1 release and 90 days** | release note + boot log |
> | **A change that can stop data arriving** — an ingestion path, a connector default, a required new setting, a runtime floor | **2 releases and 180 days** | release note + boot log + **in-app banner** + community announcement |
> | A security fix that cannot wait | no window | ship it, say why the window was waived, in the notes |

**Why 180 days and not 30.** The harm is asymmetric and not symmetric-in-time. Shipping a
removal a season late costs the project maintenance of a shim it has already written.
Shipping it a season early costs a household its CGM data feed, discovered when a number
does not appear on a phone. There is no version number, and no amount of correctness in
the change itself, that makes the second cost acceptable to trade for the first.

**Why "2 releases" as well as "180 days".** Time alone does not help an operator who
upgrades in a single jump from a version predating the warning. Requiring the warning to
be present in *two* releases raises the chance it lands in whatever version they happen to
pass through — and the removing release should additionally **detect the removed
configuration and say what happened**, rather than silently doing nothing (§2, question 7).

**The specific consequence for cut 4:** it cannot ship immediately after a deprecation
release. The deprecation release is `15.2.0` in §7's numbering; the removal is the last
major in the train, which the adopted plan already holds back. The measurement supports
the plan.

### 5.5 Deprecating something that was never announced

MiniMed is the live case: `lib/server/mmconnect-connect-compat.js` does not exist on
`dev` or `master` — it is born in the branch that deletes `lib/plugins/mmconnect.js`.
Dexcom, by contrast, has had a shim on both `master` and `dev` for some time and a boot
warning that names `DEXCOM_BRIDGE_USE_LEGACY`.

> **Policy: the window starts when the announcement ships, not when the intention forms.**
> A migration shim that appears in the same release as the deletion has a window of zero.

The corollary is that **cut 4 contains real code work that has not been done yet**, not
merely a warning string: the shim must be extracted, made non-fatal, and shipped ahead.

### 5.6 The operator-facing half of every minor and major

The classification is contributor-facing. The release note is not. Any release note a
person managing their own or a family member's diabetes will read must:

- use plain language and define every term it cannot avoid;
- say **what will change for them**, **what they must do**, and **by when**;
- preserve every safety-relevant caveat from the contributor-facing text **verbatim** —
  `bf/coercion`'s "earlier results may have under- or over-reported delivered therapy" is
  the model;
- **never simplify algorithm behaviour** in a way that could mislead someone relying on
  it. "Your reservoir alarm now works" fails this test; §3.3 says why;
- give **no individualised insulin dosing advice**, and suggest the care team where a
  change could affect therapy decisions;
- state that Nightscout is not a medical device and its output is not medical advice.

---

## 6. An enforceable check

### 6.1 Why a checklist alone is not enough, and why a gate alone is not either

The governance finding from the release-readiness review is what makes this section the
operative part of the document rather than an appendix: **495 modernization commits with
one author; 100 child PRs self-merged with zero human reviews; release PR #8598 and
integration PR #8605 each carrying zero human reviews.** When there is no second reader,
**the version number is the only signal an operator gets about how carefully to upgrade.**
A patch number on a release that changes the Node floor is not a labelling error in that
situation; it is the whole of the warning, missing.

A checklist asks a human who may be the only human. A gate cannot read intent. So the
design is: ~~**the gate detects what is mechanically detectable and refuses to pass until a
human has answered, in writing, the questions it cannot decide.**~~ **Corrected by the
verification pass: as shipped it refuses to pass until a human has *typed something*. Any
string that does not begin "yes" is treated as "no", so `unknown` passes. See §6.3, run K,
and fix that before relying on any of this section.** The answers are the
artefact. They are what a reviewer — or the same author six months later — can be wrong
about in a way that is visible.

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
[ ] S9 (candidate, 3.8) what the client computes and shows a person
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
    -- added by the verification pass; see 3.8.  MINOR at minimum,
       and a therapy-adjacent calculation needs the note in 5.6

Proposed: [ ] patch  [ ] minor  [ ] major
Evidence for each "no" (a test name, a diff line, or a transcript):

Non-vacuity (house rule 2): name one check in this PR, say how you broke
the code under it, and confirm the check failed.

If a dependency major reaches rendering code:
[ ] a real browser pass was done, or the Playwright suite runs here — say which

Deprecation (required if MAJOR):
[ ] a previous release warns about this, naming the setting AND the removing
    version, in the boot log AND in the app
[ ] the window in §5.4 has elapsed
[ ] or: no warning was possible, and here is why:

Operator-facing release note (required if MINOR or MAJOR):
[ ] drafted in plain language, jargon defined
[ ] every safety-relevant caveat preserved verbatim
[ ] says what the operator must do and by when
[ ] no individualised dosing advice; care team suggested where relevant
[ ] no algorithm behaviour simplified in a misleading way
```

### 6.3 The runnable gate, and proof that it catches a real case

`tools/qc/semver-surface-gate.js` — read-only, no network, no dependency beyond `semver`
(resolved from the inspected repo where available, so it uses the same resolver the
application boots with).

```
node tools/qc/semver-surface-gate.js --repo <checkout> --base <ref> --head <ref> \
     [--impact <answers file>] [--simulate-version X.Y.Z] [--json]
```

It computes, from the diff alone:

- **which declared surfaces the change touches**, by path;
- **env-var additions and removals**, by censusing `readENV*('NAME')` at both refs —
  removals are a hard major, additions a minor;
- **whether `engines.node` narrowed or widened**, by testing both ranges against a grid of
  Node versions with `semver.satisfies`; narrowing is a hard major, widening a minor;
- **whether the enforced boot-time Node check moved**, independently of `engines`;
- **whether the `nightscout-connect` pin moved**;
- **file deletions in capability-bearing paths** (S1, S2, S6) — a hard major;
- **added lines matching an emission pattern** in alarm files, scoped per file.

and then asks the questions it cannot decide (`Q-REMOVE`, `Q-4XX`, `Q-ROWS`, `Q-ALARM`,
`Q-PLUGIN`, `Q-FIELD`, `Q-PIN`, `Q-INGEST`). **It fails if any question is unanswered, if
the answers imply a larger bump than `package.json` moved, or if the PR's declared number
is smaller than the computed one.** An answer escalates only when it begins `yes`.

Answers file format — one `key: value` line each, `#` comments; this is what a PR supplies:

```
proposed: major
Q-4XX:    yes - ?count=0 and five other spellings now 400 on every v1 route, reads and writes
Q-ROWS:   yes - count/entries/where goes from [] to a number
Q-REMOVE: yes - ?count=0 previously returned the whole collection and now returns 400
Q-FIELD:  no  - storage.js change is the shared count parser, no stored field is dropped
```

#### The demonstration — a real Phase 0 branch, run today

Per house rule 2, this is a run, not an assertion. `bf/reads` at `0d19bb31` against
`a8888f0d`:

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

Answer them honestly and the arithmetic moves without anyone editing the number:

```
  [answered] Q-4XX    yes - ?count=0 and five other spellings now 400 ...   => escalates to MAJOR
  [answered] Q-ROWS   yes - count/entries/where goes from [] to a number    => escalates to MINOR
  [answered] Q-REMOVE yes - ?count=0 previously returned the whole collection => escalates to MAJOR
  [answered] Q-FIELD  no  - shared count parser, no stored field dropped

  REQUIRED: MAJOR     ACTUAL: NONE

FAIL
  - version bump is NONE (15.0.9 -> 15.0.9) but the surfaces touched require at least MAJOR
```

The `proposed:` line is checked separately and independently of the version arithmetic.
With the answers above (`proposed: major`) it agrees and is silent. Change that one line
to `proposed: minor`, leave everything else alone, and a second failure appears — this is
run C3 in the table below, and it is the check that catches an author who has reasoned
about the surfaces correctly and then written the wrong word in the PR:

```
  REQUIRED: MAJOR     ACTUAL: MAJOR
FAIL
  - PR declares "minor" but the gate computes major
```

#### Non-vacuity: what it took to make it fail *for the right reason*, and what it took to make it pass

A check that has only ever failed is as uninformative as one that has only ever passed.
**Sixteen gate runs plus one supporting git measurement (J).** Runs A–H2 were written by
the drafting pass and **independently re-run by the adversarial verification pass; all
eleven reproduced their documented verdict and exit code exactly**, including run D (a
genuine patch passing with no bump) and run F on the shipped 15.0.9 candidate. Runs K, K2,
K3, L and M were added by the verification pass and are the ones that change the conclusion.
Exit codes were captured with `${PIPESTATUS[0]}`, not `$?` after a pipe — the drafting
pass's first attempt at this table read `tail`'s exit status instead of the gate's and
briefly showed C2 passing when it fails:

| # | Run | Expected | Got |
|---|---|---|---|
| A | `bf/reads`, no answers | fail (unanswered) | **fail**, exit 1 |
| B | `bf/reads`, answers, version unchanged | fail (bump too small) | **fail**, exit 1 |
| C | `bf/reads`, answers, `--simulate-version 16.0.0` | **pass** | **pass**, exit 0 |
| C2 | `bf/reads`, answers, `--simulate-version 15.1.0` | fail (minor < major) | **fail**, exit 1 |
| C3 | `bf/reads`, answers with `proposed: minor`, `--simulate-version 16.0.0` | fail (declared < computed) | **fail**, exit 1, `PR declares "minor" but the gate computes major` |
| D | `bf/cache`, answers `no`/`no`, version unchanged | **pass** (a true patch) | **pass**, exit 0 |
| E | `bf/alarms`, answers, version unchanged | fail (major, per Q-REMOVE) | **fail**, exit 1 |
| F | `origin/master` → `origin/dev` (the shipped 15.0.9 candidate) | fail | **fail**: `REQUIRED: MINOR   ACTUAL: PATCH` |
| G | `origin/dev` → cut 1 | fail | **fail**: `REQUIRED: MAJOR   ACTUAL: NONE` |
| H | synthetic **widening** of `engines.node` in a scratch repo (`>=20.x` -> `>=18.x`) | minor, not major | **minor**: `newly accepts: 18.20.4`, `REQUIRED: MINOR` |
| H2 | the same scratch repo **narrowing** (`>=18.x` -> `^22.23.2 \|\| ^24.20.0`) | major | **major**: `rejects now: 18.20.4, 20.0.0, ... 26.0.0`, `REQUIRED: MAJOR` |
| J | `bf/reads` at `0d19bb31` contains `bf/coercion` `88d1f8a4` | the §0.1 correction | `git merge-base --is-ancestor bf/coercion bf/reads` -> yes (re-run; 8 commits, base `a8888f0d`) |
| **K** | `bf/reads`, `proposed: patch`, all four answers `unknown` | **fail** — a MAJOR branch declared patch | **PASS, exit 0.** The bypass; see the section above |
| **K2** | `bf/reads`, `Q-4XX: probably yes`, rest `no`, `proposed: patch` | fail (a hedged yes) | **PASS, exit 0** — `/^yes\b/` does not match `probably yes` |
| **K3** | `bf/reads`, all four answer keys present but **empty** | fail (unanswered) | **fail**, exit 1, `4 surface question(s) unanswered` — emptiness *is* caught |
| **L** | `bf/food` (carries BF-35, high) , no answers | should ask about the calculator | asks `Q-REMOVE`, `Q-ROWS`, `Q-PLUGIN` only; answered honestly it is `REQUIRED: NONE`. §3.8 |
| **M** | `bf/merge` (carries BF-36) , no answers | should ask about the frozen page | asks `Q-REMOVE`, `Q-PLUGIN` only; `REQUIRED: NONE`. §3.8 |

C and D are the runs that matter most **for the arithmetic**: the gate passes when the
number is right and passes a genuine patch with no bump at all, so it is discriminating,
not a tax. H is the control for the S5 rule specifically — narrowing and widening are
distinguished, and both were reproduced independently.

**K, L and M are the runs that matter most for whether the gate should be trusted**, and
they are the verification pass's contribution: K shows the arithmetic can be bypassed with
one word, and L and M show two branches whose only defect is client-side scoring `NONE`
however honestly they are answered. A gate that is discriminating on the cases it models is
still blind to the cases it does not.

#### Three defects the gate had, found by breaking it, and fixed

Reported rather than hidden, because they are the interesting part:

1. **Content patterns were matched against the whole diff and attributed to files matched
   by path.** On its first run against cut 1 the gate reported a dependency-audit CSV line
   (`node-cache,^4.2.1,…`) as an alarm-emission change in `lib/plugins/pushover.js`.
   Fixed by indexing added lines **per file** from the `+++ b/<path>` headers.
2. **The S7 check was content-gated and missed the one S7 case in the programme.** On
   `bf/alarms` it asked no alarm question at all, because the insulinage fix changes
   `insulinInfo.age >= insulinInfo.urgent` to `>= prefs.urgent` — the *emitting* lines are
   untouched context, so no added line matches any emission pattern. **A grep cannot see
   an unreachable branch becoming reachable.** Fixed by asking `Q-ALARM` on any touch of an
   S7 path, and using the content patterns only as supporting evidence. This is the single
   strongest argument in this document for why S7 needs a *question* and not a rule.
3. **A path touch forced a MINOR, which failed every honest patch.** The first version
   failed `bf/cache` because it edits `lib/api/entries/index.js`, although the change is
   pure clone-avoidance with identical bytes on the wire. A gate that fails everything
   teaches reviewers to bypass it. Fixed by making a path touch raise a **question**, not
   a number; only content evidence and answered questions move the arithmetic.

#### The bypass the verification pass found, which must be fixed before this gate is trusted

**Run K, today, `bf/reads` `a8888f0d -> 0d19bb31`, with this answers file:**

```
proposed: patch
Q-4XX: unknown
Q-ROWS: unknown
Q-REMOVE: unknown
Q-FIELD: unknown
```

```
  REQUIRED: NONE     ACTUAL: NONE
PASS
exit 0   (captured with ${PIPESTATUS[0]})
```

**The branch this document classifies MAJOR passes the gate as a patch, with the number
unchanged, in four words.** The cause is in the gate's own logic, which §6.3 describes
accurately and then draws the wrong conclusion from: `unanswered` is
`questions.filter(q => !impact[q.id])` — *any* non-empty string counts as answered — while
escalation is `/^yes\b/i.test(a)`. So every string that is not "yes…" is silently
**treated as "no"**. `unknown` passes. `probably yes` passes (verified, run K2: `REQUIRED:
NONE`, exit 0). Only a genuinely empty value is caught (verified, run K3: `4 surface
question(s) unanswered`, exit 1).

Two statements elsewhere in this document are wrong because of it, and are struck rather
than deleted:

- ~~§6.1: "the gate ... **refuses to pass until a human has answered, in writing, the
  questions it cannot decide**"~~ — it refuses to pass until a human has *typed something*.
  That is a weaker property and it is the one that matters, because the failure mode of a
  gate is not a reviewer who lies, it is a reviewer in a hurry.
- ~~§9, cut-2 row: "If nobody can answer it, the honest answer is 'unknown'"~~ — the gate
  reads `unknown` as `no` and escalates nothing. As the tool stands, writing the honest
  answer produces the least honest arithmetic in the file.

**Required fix before adoption** (a decision for the gate's author, not made here): parse
answers into an enum — `yes` / `no` / `unknown` — reject anything else with exit 2, and make
`unknown` escalate to the surface's `minimum`, which is what §9's cut-2 row already assumes.
Until that lands, **the gate's questions are advisory and the checklist in §6.2 is the
binding artefact.** A register entry is proposed.

#### Known limits, stated so nobody over-trusts it

- **Answers are free text and only `yes…` escalates** — see the bypass above. This is the
  limit that matters most.
- **A version *downgrade* reads as no bump, not as an error.**
  `if (semver.lt(headVersion, baseVersion)) actual = 'none'`, so a head that renumbers
  15.0.9 → 15.0.8 is scored the same as no change at all.

- It reports `lib/authorization/storage.js` under S4 on `bf/reads`, where the change is
  actually the shared count parser. That false positive is **by design** — a path rule on
  a storage file should ask a human — but it means surface hits are prompts, not verdicts.
- Its path map is `cgm-remote-monitor`-shaped. `nightscout-connect` needs its own surface
  map (its public surface is a module API, so the relevant check is an exported-signature
  and default-value diff). **Not built. See §10.**
- It cannot detect a semantic change confined to an untouched file's behaviour, a data
  migration expressed in a script, or a change whose effect depends on configuration.
- `--simulate-version` exists for the non-vacuity harness. CI must never pass it.

### 6.4 Making it queue-able

Two work items, gates included, in the manifest this document returns. The CI shape:

```make
# Makefile target (proposed; not added by this document)
semver-gate:
	@node tools/qc/semver-surface-gate.js \
	  --repo $(CRM_REPO) --base $(BASE_REF) --head $(HEAD_REF) \
	  $(if $(IMPACT),--impact $(IMPACT),)
```

In `cgm-remote-monitor`'s own CI the job runs on `pull_request`, with `--base` as the
merge base and `--impact` read from a `.semver-impact` file in the PR or parsed out of the
PR body. **An override label is mandatory** — the gate will be wrong sometimes, and a gate
with no escape hatch gets deleted rather than corrected. The override must record *who*
overrode it and *why*, in the PR.

---

## 7. Where current practice departs from this policy

Stated plainly and without blame. Every row is measured and checkable today. Nothing here
is an accusation of carelessness: the project has had **no written definition of its public
surface**, and without one none of these is a rule violation. That is precisely the gap
this document exists to close.

| # | Departure | Evidence |
|---|---|---|
| D-a | **The version number does not move at all.** `origin/dev` and all five cut tips carry `15.0.9`, including the branch that changes the Node floor and the branch that deletes two ingestion paths. **All nine `bf/*` branches also carry `15.0.9`** | `git show <ref>:package.json` at sixteen refs: `master` is 15.0.8, the other **fifteen** (`dev`, five cut tips, nine `bf/*`) are all 15.0.9 |
| D-b | **Two artefacts claim the same version with different runtimes.** `dev` is `15.0.9` at `engines.node ">=20.x"`; cut 1 is `15.0.9` at `"^22.23.2 \|\| ^24.20.0"` | same |
| D-c | **A patch number carries a two-major charting upgrade with jsdom-only coverage** and two unexercised drag clamps | §3.7; GT2's break-it runs |
| D-d | **New environment variables ship under a patch number.** `DEBUG_LOGGING` and `CONNECT_DEBUG` are new on `dev`, and logging flips from on to off | env census, master 30 names → dev 32 |
| D-e | **The gate says so mechanically.** `master` → `dev` is tagged PATCH (15.0.8 → 15.0.9) and the gate computes MINOR | §6.3 run F |
| D-f | **Deprecation warnings name a version that does not do the thing.** Both cut-4 shims say "retired in Nightscout 15.0.9"; on the adopted train 15.0.9 retires nothing | GT4, executed |
| D-g | **A deletion ships in the same release as its own migration shim.** `mmconnect-connect-compat.js` is born in the branch that deletes `mmconnect.js` — a deprecation window of zero | §5.5 |
| D-h | **A documented escape hatch is removed without a word.** `DEXCOM_BRIDGE_USE_LEGACY` becomes accepted-and-ignored in cut 4, and dev's own boot warning tells operators to set it | §2 question 7 |
| D-i | **Release dependencies are pinned to untagged commit SHAs on unmerged branches** (`dev` → `234d47c8`, cut 4 → `c962a13f`, cut 5 → `b77e5bb`), so what an operator receives cannot be named or audited | §4.2 |
| D-j | **Shipping the cuts in train order would silently *remove* an environment variable.** The gate on `dev` → cut 1 reports `env vars REMOVED: CONNECT_DEBUG, DEBUG_LOGGING`, because cut 1 is 59 commits behind `dev` and predates them. The connector pin also moves **backwards**, `234d47c8` → `v0.0.13`. If 15.0.9 ships first and cut 1 ships next without merging `dev`, operators lose both variables and the connector regresses | §6.3 run G — **new; in no prior document** |
| D-k | **The Phase 0 batch contains at least three behaviour changes a strict reading calls more than a patch**: the Alexa/Google Home locale removal (major), the subject-storage allow-list (major), the `?count=` restriction (major as written). **The minors are not two but at least six** — the first draft named only `bf/coercion` and `bf/food`. Also minor: `bf/alarms`' insulinage URGENT emission (§3.3, R2, never waivable), `bf/reads`' v3 `_id` paging tiebreak (§9, overruled to minor), `bf/reads`' v3 dotted `?fields=` going from `{}` to a populated body, `bf/reads`' v3 `?limit=0x10` bound restoration, `bf/auth` adding `notes` to `GET /api/v1/subjects`, and `bf/connect-pin` under R4. `bf/cache` (§3.1) and `bf/parms` (§9) are the branches this policy calls clean patches; `bf/merge` and `bf/food`'s **BF-35** fall through the ladder entirely — see §3.8 | §8 |
| D-l | **`bf/reads` is no longer flat on `dev`** — it now contains `bf/coercion`, so the two cannot be numbered or landed independently | §0.1 |
| D-m | **There is no PR field for semver impact**, so classification is nobody's job at the moment it is cheapest | §6.2 closes this |
| D-n | **Nothing enforces the number** | §6.3 closes this |

**D-j deserves emphasis because it is new and it is a defect, not a labelling question.**
The train adopted on 2026-09-15 ships 15.0.9 first, then cut 1. GT2 measured that cuts 1–4
are each 59 commits behind `dev` and conflict against it in 4–5 files. The version
consequence is concrete: an operator who upgrades 15.0.9 → cut 1 **loses `DEBUG_LOGGING`
and `CONNECT_DEBUG`** and has their connector moved from `234d47c8` to `v0.0.13`. A
register entry is proposed for this.

**Two corrections and one escalation, from the verification pass, measured in
`externals/nightscout-connect`:**

1. **It is not a simple rollback; the two pins have diverged.**
   `git merge-base --is-ancestor v0.0.13 234d47c8` fails — `v0.0.13` is `b394411`, a merge
   commit ("Merge pull request #26 from nightscout/dev"), and `234d47c8` is a *sibling* of it
   off the shared parent `6dfc4f0b`. `git diff 6dfc4f0b b394411` is empty, so the tags'
   content is the same and the practical effect is still "lose one commit", but the branch
   arithmetic is a divergence, not a rewind. Saying "rolled back" invites someone to fix it
   by fast-forwarding, and there is nothing to fast-forward.
2. **The one commit lost is "Make embedded connector debug logging opt-in"** (`234d47c`, 18
   files, +379/−146) — which is exactly the commit that produced `CONNECT_DEBUG` and
   `DEBUG_LOGGING`. The two halves of D-j are one event, not two.
3. **The escalation, and it is safety-relevant.** None of the three log-redaction commits
   (`9fa2c3c`, `5349d47`, `77e2396`) is in *either* pin —
   `git merge-base --is-ancestor <each> 234d47c8` fails six times for six. So moving from
   `234d47c8` back to `v0.0.13` **turns connector debug logging back on by default on a
   connector that still writes Dexcom and MiniMed credentials, sessions and patient data
   into runtime logs.** Cut 1's pin is not merely older; it re-opens a credential exposure
   in the state where nothing redacts it. This is the strongest argument in this document
   for `bf/connect-pin` (which moves the pin to `v0.0.14`, the first ref carrying all seven
   commits) landing **before** any cut ships, and it is why D-j is graded as a defect rather
   than a numbering question.

---

## 8. What this policy costs the work already in flight

This is where the policy forces uncomfortable renumbering. **The options are laid out; the
choice is the maintainer's.** Where this document has a preference it says so and says why,
but none of these is decided here.

### 8.1 The 15.0.9 candidate

**Under this policy it is a MINOR: `15.1.0`.** Two independent reasons, neither involving
D3: two new environment variables with a changed logging default (rule 11 and question 9),
and a connector pin move that changes retry behaviour (rule 11, rule R4).

| Option | What it means | Cost |
|---|---|---|
| **1. Renumber to `15.1.0`** *(preferred)* | One line in `package.json`; notes gain a "what changed for you" section | Smallest — but not zero, see the note below the table |
| 2. Ship as `15.0.9` with a `BEHAVIOUR CHANGES` section | Keeps the planned number; the note carries what the number does not | The number lies, and D-b survives unless the cuts are renumbered anyway |
| 3. Ship as `15.0.9` and move the two env vars and the pin to 15.1.0 | Makes 15.0.9 a true patch | Most work; splits a coherent release; the pin move is the one carrying the log-redaction fixes and should not wait |

**"The 15.0.9 string has not been released" needs one qualification** (added by the
verification pass, because the first draft used it as the whole cost of option 1). There is
no `15.0.9` git tag — `git tag -l` in `cgm-remote-monitor-official` stops at `v15.0.8` — and
no version-tagged Docker image, because `.github/workflows/main.yml` tags `dev` builds
`dev_<sha>` and `latest_dev` and uses the `package.json` version only on `master`. **But the
running application reports its `package.json` version**: `lib/server/env.js:137` sets
`env.version`, and `lib/api/status.js:32` returns it. So every deployment on the `dev`
channel or a `latest_dev` image **already answers `/api/v1/status` with `15.0.9` today**.
Renumbering to `15.1.0` therefore means some sites will appear to go *backwards* from
`15.0.9` to a number that sorts above it — which is fine — but the release note should say
that `15.0.9` was never a release, so a bug reporter who says "I was on 15.0.9" is
understood rather than contradicted.

**Independent of the choice, one thing must happen: the cut branches must stop claiming
`15.0.9`** (§5.1). That is D-b and it costs one line each.

### 8.2 Phase 0

As one release, Phase 0 is a **major**, on three rows: the Alexa/Google Home locale
removal, the subject-storage allow-list, and `?count=` as written. That is an expensive
number for a batch that is overwhelmingly "things that were broken now work".

| Option | Shape | Consequence |
|---|---|---|
| **1. Split** *(preferred)* | `15.1.0` carries everything except those three; the three are held for the next major, each preceded by its own warning step | Everything operators gain ships now. Costs three extra PRs and a deprecation step for `?count=0` |
| 2. Ship whole as `16.0.0` | One release, honest number | Spends a major on bug fixes, and pulls forward the attention budget that cut 1 needs |
| 3. Ship whole as `15.1.0` | Convenient | Contradicts R3 and hides a capability removal on two HTTP endpoints under a minor. This policy recommends against it |
| 4. Split *and* narrow the two changes so they stop being major | `bf/auth` deletes only `DERIVED_SUBJECT_FIELDS` instead of allow-listing the whole document; `?count=0` clamps with a `Deprecation` header instead of rejecting | Best outcome, most code. Removes two of the three majors outright |

**Option 4 is the one this document would argue for if forced to choose**, because in both
cases the major-ness is incidental to the fix's purpose. Neither change needs to break
anything to achieve what it is for.

Note also §0.1: **`bf/reads` now contains `bf/coercion`**, so they land together and are
numbered together.

### 8.3 The cuts

Following §7 of GT4 with the pre-release identifiers of §5.1 and the deprecation rules of
§5.4:

| Release | Contents | Number |
|---|---|---|
| Bug-fix release | `dev` + the safe Phase 0 rows | **15.1.0** |
| Deprecation release | MiniMed shim shipped non-fatally, Dexcom escape hatch preserved, `?count=0` warned, subject allow-list warned | **15.2.0** |
| Runtime release | Cut 1 | **16.0.0** |
| Build release | Cut 2 | **16.1.0** |
| Dependency release | Cuts 3 + 5 | **17.0.0** |
| Ingestion retirement | Cut 4, ≥180 days after 15.2.0 | **18.0.0** |
| Deferred Phase 0 breaks | Alexa locale, storage allow-list, `?count=0` rejection | fold into 16.0.0 |

**The orderings here are more durable than the numbers** (house rule 9). What matters is:
the deprecation release precedes both majors that need it; the runtime break and the
ingestion break are **not** in the same release, because an operator debugging a site that
will not start should not simultaneously be debugging why their CGM data stopped; and cut
4 is last.

### 8.4 nightscout-connect

**`0.1.0`, not `0.0.14`** (§4.3). The cost is: the prepared local tag `v0.0.14` at
`649a7de` would be re-cut as `v0.1.0`, and `bf/connect-pin` (`0807eb1c`, `+1/-1`) would
point at the new tarball URL. Nothing else changes, because nothing resolves by range.

**If the maintainer keeps `0.0.14`** — which is defensible — then a `BREAKING` section in
the release notes is mandatory, and `cgm-remote-monitor`'s note must carry the 585.94×
retry change in operator language (§3.6). The pin's `+1/-1` diff is otherwise the only
place that change appears in the consuming repository.

---

## 9. Judgement calls, resolved

GT4 marked eleven judgement calls. This policy resolves each. **Two are overruled.**

| GT4 § | Judgement | This policy | Why |
|---|---|---|---|
| 3.5 | `?count=0` → 400 is major | **Upheld as written, with a split that makes both halves minor** (§3.2) | The six spellings are not one change. Five are unreachable; `?count=0` is reachable by construction |
| 1 | S7 (alarms) is a first-class surface | **Upheld, judgement flag removed** (§1 S7) | Adopted as policy, not as a call |
| 3.1 | Alexa/Google Home locale removal is major | **Upheld** | A per-request capability on an HTTP endpoint is removed with no replacement. The removal is *correct* — the old code set process-global state — and correctness is not the question (R1) |
| 2 #1 | `bf/connect-pin` is minor although it is one line | **Upheld, promoted to rule R4** | Classify by what the operator receives |
| 2 #5 | `bf/parms` is patch although `_`-decoding changes | **Upheld**, with a required release-note line | The old decoding was applied inconsistently and the server never agreed with it; no supported client depends on it. A bookmarked report URL might, which is the note |
| 2 #15 | v3 `_id` tiebreak is patch | **OVERRULED → minor** | GT4 reasons that only the order of tied documents changes. But the commit's own subject is that paging "lost and repeated documents whenever the whole sort chain tied" — so a paging client previously **received a different set of records** than the collection contains. That is question 10 exactly. Non-determinism in the old behaviour does not make the new set the same set |
| 2 #18 | v3 `?limit` restriction is minor, unlike `?count=` | **Upheld** (§3.2) | `API3_MAX_LIMIT` is documented in `lib/api3/swagger.json` and the endpoint already had a 400 path. Restoring a documented bound ≠ inventing one |
| 5.2 | Cut 2 is minor | **Upheld, conditionally** | Unmeasured against third-party plugins. Condition: `Q-PLUGIN` must be answered with evidence. **If nobody can answer it, the honest answer is "unknown", and unknown on S2 defaults to the number of whatever release it ships in** — *but note that the shipped gate does **not** implement this: it reads `unknown` as `no` and escalates nothing (§6.3, run K). Until that is fixed the rule is a reviewer obligation, not an enforced one* — which is why folding cut 2 into the 16.x line costs nothing and settles it |
| 5.5 | Cut 5 is major | **Upheld** | Express 4→5 changes routing and error semantics under everything that mounts a route, which is what a plugin does. Classified from dependency majors, not a measured break — flagged in §10 |
| 6 | connect should be `0.1.0` | **Upheld** (§4.3) | Three independently breaking changes for a caller |
| 5.6 | The numbering table | **Upheld with two changes**: pre-release identifiers on the cut branches (§5.1), and a minimum 180-day window between the deprecation release and cut 4 (§5.4) | |

**The second overrule** is not in GT4's table: GT4 classifies `bf/coercion` as minor
**and** notes at §9.1 that it *inverts* `$exists=false` on the five previously-walked
fields (`sgv`, `date`, `insulin`, `carbs`, `glucose`), replacing one wrong answer with a
different wrong answer. This policy agrees with the minor, and adds that **the inversion
is not a versioning question at all** — it is an open defect that should be fixed before
the branch lands, not classified. It is already proposed for the register by GT4; this
document does not duplicate it.

---

## 10. What a verifier should attack, and what is unsettled

1. **§3.2 remains the most overrulable call in the document.** The unbounded-download
   counter-argument is real and the split resolution is an opinion about sequencing, not a
   measurement. A maintainer can reasonably rule it a minor and reject all six spellings
   today.
2. **§1 S2 and §9's cut-2 row are unmeasured against any third-party plugin.** No plugin
   corpus exists on this machine. If one exists anywhere in the community, running it is
   worth more than both sections.
3. **Cut 5's major rests on dependency majors and a 36-file production diff, not on a
   measured contract break.** A browser pass plus the full suite could move it to minor.
4. **The gate has no surface map for `nightscout-connect`.** Its public surface is a module
   API, so the right check is an exported-signature and default-value diff — which would
   have caught all five of §4.3's breaking changes mechanically. Not built.
5. **The 180-day window in §5.4 is reasoned, not measured.** The reasoning — asymmetric
   harm, self-hosters who upgrade rarely — is stated so it can be argued with. Nobody here
   has data on how long news actually takes to reach a Nightscout self-hoster. **If the
   Foundation has any telemetry on version distribution in the wild, that number should
   replace this one.**
6. **§1's "argue each in or out" is where the whole document is falsifiable.** If S7 or S8
   is rejected, several classifications move. The arguments are set out at length for
   exactly that reason.
7. **D-j (cut 1 silently removing two env vars) was found by the gate and has not been
   confirmed by a human reading cut 1's intent.** It may be that the train assumes a merge
   of `dev` into each cut before release, in which case the finding is about the branches
   as they stand rather than about the plan. Nobody has written that assumption down.
   *What is not conditional on that assumption: moving the connector pin from `234d47c8`
   back to `v0.0.13` re-enables always-on connector debug logging on a connector none of
   whose three log-redaction commits is present in either pin (§7, D-j escalation).*
8. **The gate can be passed by writing `unknown` in every answer** (§6.3, run K, exit 0 on
   a branch this document classifies MAJOR). Until the answer field is parsed as an enum,
   the gate's questions are advisory and §6.2's checklist is the binding artefact. **This
   is the item to fix first**, because everything §6 claims for enforcement rests on it.
9. **§1's enumeration has no surface for what the client computes and shows a person**
   (§3.8). Under §2 as written, BF-35 — the bolus calculator loading a quick pick the user
   did not choose, so the wrong carb count reaches an insulin calculation, with no error
   shown — is a **patch with no release-note obligation**. Candidate S9 is proposed there
   and deliberately not adopted, because it moves §2, §6 and §8 together. **If one thing in
   this document is wrong in a way that could reach a person, it is this.**
10. **Nothing here says how the seam and tenancy branches are versioned.** The policy covers
   `cgm-remote-monitor`'s single-tenant releases and `nightscout-connect`. Decision D1 makes
   single-tenant first-class permanently and D5 adds four hosted entrypoints; a hosted
   entrypoint that withholds alarms outside tenant scope (T3.5) is an S7 event under this
   policy's own reasoning, and no section addresses it. Out of scope, but named so it is not
   assumed to be covered.

---

*Draft, 2026-09-15, drafted and then adversarially verified — see §0.0. Contributor- and
maintainer-facing. It proposes version numbers and a policy; it sets neither, and it is a
draft requiring maintainer review before anything is renumbered, tagged or released.
Nothing in this document was pushed, tagged, merged or published, and no shipping file was
modified.*

***Before acting on it, read §10 items 8 and 9.*** *The gate in §6 can be passed by writing
`unknown` in every answer, and the surface list in §1 has no entry for what the client
computes and shows a person — so this policy, as it stands, classifies BF-35 (the wrong carb
count reaching a bolus calculation) as a patch needing no release note. Both are open
decisions, not settled positions.*

*Operator-facing release notes derived from this document must follow §5.6. Nightscout is
not a medical device; nothing here or in a note derived from it is medical advice, and no
part of it gives individualised insulin dosing advice. Where a release changes something a
person uses when making decisions about therapy, the note should say so plainly and suggest
they discuss it with their care team.*
