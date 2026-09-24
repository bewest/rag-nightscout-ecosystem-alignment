# GT3 — register truth and a contradiction sweep across the planning documents

> **Snapshot, 2026-09-15, against register head `70baa879` (contradiction table at `75c38a17`) and `origin/dev` `a8888f0d`. Historical: a point-in-time audit; every count and line number has moved. Contributor-facing. Current facts: [backfix register](../../30-design/remedial/nightscout-backfix-register.md), [work queue](../../../queue/work-queue.yaml).**

Date: 2026-09-15. **Read-only audit. No document was edited by this task** — a later agent applies
the fixes. Head at start `9fc55eaa`; the register was edited by another session **during** this
audit (BF-39 arrived at `5b49caec`/`70baa879`), so every line number below was re-taken against
head `70baa879` after that landing. Contributor-facing.

> **Summary (as of 2026-09-15).** The register held **39** BF entries. **BF-16 was fixed** on a
> branch, so the open operator-facing entries were two (BF-09, BF-10), plus BF-04 (§3d). The
> open/fixed split tracked work done, not operator exposure — see §0.

---

## 0. The framing correction that matters more than any single row

The register's own status legend says:

> `fixed <date>` (repaired on a backfix branch with tests and a release note, **not yet merged**)

**Nothing in the register has status `landed`.** Zero entries. Every one of the 26 §1 rows marked
*fixed* sits on an unpushed local branch. Measured: nine `cgm-remote-monitor` branches
(`bf/alarms`, `bf/auth`, `bf/cache`, `bf/coercion`, `bf/connect-pin`, `bf/food`, `bf/merge`,
`bf/parms`, `bf/reads`) and one `nightscout-connect` branch (`fix/connect-timer-jitter`) plus
`release/v0.0.14` and a local `v0.0.14` tag, none pushed.

So the sentence both the plan and the memory use — *"only three open register entries reach an
operator on today's release"* — is true of the **register's bookkeeping** and false of **operators**.
On today's release every one of the 26 §1 defects is still present for every self-hoster. The
open/fixed column tracks *work done*, not *operator exposure*, and no document says so. A reader
who takes "3 open" as "3 defects still shipping" will mis-size the release train by an order of
magnitude.

**Recommended wording for whoever fixes this**: "26 defects are repaired on local branches and
**none has shipped**; 2 remain unrepaired." That is the same fact without the trap.

---

## 1. The register, re-derived

39 BF ids (BF-01 … BF-39, none missing) plus CAP-01. Reconciled programmatically, table row against
detail section, over the whole file.

**Status counts, measured:**

| status | count | ids |
|---|---:|---|
| fixed (local branch, unmerged) | 23 | BF-01, 02, 05, 06, 08, 11, 13, 14, 15, 16, 17, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39 |
| partly fixed | 2 | BF-03 (`food`/`activity` misfiled, not outstanding), BF-07 (`devicestatus` clone kept on purpose) |
| invalid / closed | 1 | BF-12 |
| fixed-in-seam, never extracted | 1 | **BF-04** |
| open, §1 (operator-facing) | 2 | BF-09, BF-10 |
| open, §1b (pre-release) | 10 | BF-18, 19, 20, 21, 22, 23, 24, 25, 26, 27 |
| open, §1c capability | 1 | CAP-01 |

**Table vs detail: one structural disagreement, and it is a missing section, not a wrong word.**
Every id whose table row says *fixed* has a detail section that agrees, and every *open* row
likewise — **except BF-27, which has a §1b table row (L124) and no detail section at all.** Every
other id in the file has one. The brief's suspicion of "a stale detail heading or a second table"
is not what happened.

**BF-14 is where the naive grep came from, and it is a real defect in the document.** Its detail
section carries two paragraphs that contradict each other, in this order:

- **L587** **"Re-graded to high on 2026-09-15.** The medium grade rested on 'it returns no wrong
  data'. With a second backend that is no longer true."
- **L594-600**, immediately after: *"Sized, and at the time the measurement downgraded it from high to
  medium. … Two facts hold the grade down … **It returns no wrong data.** It **stays in the
  register** because a bounded request should not produce an unbounded read."*

The second paragraph is the superseded text. It restates, in the present tense, the exact sentence
the paragraph above it retracts, and it ends with a clause that reads as an open entry. This is
Rule 6 in miniature: an agent that reads the sizing paragraph gets *medium* and *open*; one that
reads the re-grade gets *high* and *fixed*. **Fix by folding the sizing into the re-grade as
history ("sized at the time as medium; superseded"), not by leaving both standing.**

### 1a. Provenance lines that contradict their own entries

The header block's whole argument is that an entry must say whether it was **read** or **run**.
Three entries now say both, because a *Fixed* block was prepended and the original body was never
swept:

| entry | top block says | body still says |
|---|---|---|
| **BF-17** | "**reproduced against a running instance** first" | "*Not reproduced against a live instance.*" |
| **BF-30** | "**reproduced against a running server**" | "*Not reproduced against a live server.*" |
| **BF-31** | "**Reproduced and fixed 2026-09-15**" | "*Not reproduced against a live server.*" |

An agent reading the body alone gets the opposite of the truth about the one property the register
says must be marked.

### 1b. Line references that no longer resolve

| entry | cites | measured |
|---|---|---|
| BF-05 (the *not fixed* sibling) | `lib/authorization/storage.js:84` | **line 113** on `bf/auth` |
| BF-09 | `lib/server/websocket.js:535-568` | **538-566** on `bf/alarms`; seam interface §4.4 carries the same stale range |
| plan T3.0 table | `lib/server/enclave.js:29` | **line 30** (`secrets[jwtKey] = readKey('randomString')`) |

`lib/authorization/index.js:169-173` and `lib/server/tenant-context.js:137` both resolve **exactly**
as cited. Those two are good.

---

## 2. The stale priority block — every occurrence

The brief says "the plan and the project memory both carry" it. **The plan does not.** It lives in
exactly one place, and a second memory file already contradicts it.

| where | line | says | true |
|---|---:|---|---|
| `memory/multitenancy-target-decision.md` | **67-68** | "new tenancy work is **STOPPED** … **Phase 0 is 0 of 5** … register holds **29 open entries**" | Phase 0 is 4 of 5 done locally with T0.3's gate unmet; 12 open BF entries + CAP-01 |
| `memory/release-train-and-work-queue.md` | 13-17 | "Both halves are now discharged … only **three** open register entries reach an operator — **BF-16**, BF-09, BF-10" | **BF-16 is fixed** (`bf/food` `73495331`, register L88). Two remain — and BF-04 is a third exposure of a different kind (§3d) |

**The two memory files disagree with each other**, which is worse than either being stale: whichever
one an agent loads becomes true for it. `multitenancy-target-decision.md:67-68` should be replaced
with a pointer to `release-train-and-work-queue.md`, not re-numbered, so there is one statement of
this fact and not two.

**A third memory claim does not resolve at all.** `release-train-and-work-queue.md` says
`queue/work-queue.yaml` "is the source of truth", `queue/QUEUE.md` "is generated and never
hand-edited", and `make queue-status` "runs each item's gates". Measured: **there is no `queue/`
directory in the repository and no `queue-status` target in the `Makefile`.** The memory instructs
every future agent to treat a nonexistent file as authoritative for item state. Either the queue
was planned and not built, or it was built elsewhere; either way the memory is currently wrong.

### The plan's equivalent block is stale in the opposite direction

`nightscout-multitenancy-execution-plan-2026-09-14.md:7-9` — the first thing anyone reads:

> "**Phase 0 is done and is not the blocker any more.** Five branches are ready to push … **13
> register entries closed, 3 new defects found, 4 register entries corrected as wrong.**"

Four claims, all wrong, and the first is contradicted by the same document 520 lines later:

| claim (L7-9) | contradicted by | measured |
|---|---|---|
| "Phase 0 is done" | plan **L529** "T0.1 · Land PR #8733. **In flight**"; plan **L541** "T0.3 — **GATE NOT MET**" | 4 of 5, one gate unmet |
| "Five branches ready to push" | sequencing **L40** "the **seven** Phase 0 branches" | **nine** branches + one connect branch + a tag |
| "13 register entries closed" | §1 of the register | 23 fixed + 2 partly + 1 invalid = **26** |
| "3 new defects found" | register | BF-32, 33, 34, 35, 36, 37, 38, 39 = **8** |
| "4 register entries corrected as wrong" | register header says five; §1 rows say more | **at least 7** (§4) |

---

## 3. The genuinely-open operator-facing entries, verified against code

### 3a. BF-16 — the entry is FIXED (on branch, as of 2026-09-15)

BF-16 is **not open**. Register L88: `fixed 2026-09-15` (`bf/food` `73495331`), reproduced live with
both spellings written over HTTP. It should be struck from every "open operator-facing" list.

**The underlying reachability claim is nonetheless confirmed**, measured against the released tree
`externals/cgm-remote-monitor-official`:

- `lib/server/food.js:146` is literally `{ $and: [ {'type':'quickpick'}, {'hidden':'false'} ] }` — the
  string, exactly as the entry says.
- `/api/v1/food/quickpicks` has **one route** (`lib/api/food/index.js:31`) and **no in-tree HTTP
  consumer**. `lib/client/boluscalc.js` reads `client.sbx.data.food` over the socket, not the
  endpoint. Searching the whole `externals/` ecosystem tree for a caller found none.

**But "no shipping client triggers it" was only ever true of the endpoint half.** The other half,
`restoreBoolValue` (`lib/food/food.js:69`), runs in the **built-in editor on every load**, and the
register's own fix table records that it "turned a real boolean `true` into `false`, silently
un-hiding a hidden pick". That fires for any operator whose food documents were ever written by a
JSON client or restored from an export. So the entry was *less* dormant than its summary said —
which is consistent with it having been promoted and fixed.

### 3b. BF-09 — settled enough to grade, and the entry names the wrong fields

Read at `lib/server/websocket.js:538-566` (`bf/alarms`). The block tests
`if (data.data.insulin)`, `if (data.data.carbs)`, `percent`, `absolute`, `duration`, `NSCLIENT_ID`,
each setting `selected = true`, with `if (!selected) query_similiar.eventType = …` as a fallback.
The window is `maxtimediff = times.secs(2).msecs` (L452) — **±2 seconds**, a fact the entry omits and
which bounds it sharply.

**Measured over the 11-site corpus, 277,690 treatment documents** (aggregate counts only; no
identifiers read or reproduced):

| field | present | zero/empty | share of present |
|---|---:|---:|---:|
| `insulin` | 107,732 | **0** | 0.0 % |
| `carbs` | 12,394 | **0** | 0.0 % |
| `percent` | 0 | 0 | — |
| **`absolute`** | 153,315 | **67,521** | **44.0 %** |
| `duration` | 251,051 | 2,094 | 0.8 % |

**The entry names `insulin` and `carbs`, and neither has a single zero-valued occurrence in 120,126
present values.** The field that actually carries falsy values is **`absolute`**, at 44 % — that is
the **zero temp basal**, the canonical AID suspend action, and `duration: 0` (cancel a temp) adds
2,094 more. The defect is real; the entry is looking at the wrong two fields, which is why it has
read as an edge case.

**Does the degraded key change an outcome? Measured: not in the surviving corpus.** For each of the
69,604 at-risk documents (carrying a present-but-falsy amount field), I compared the shipped
truthiness key against a presence key over every neighbour within ±2 s: **0 documents where the two
keys disagree about whether a "similar" record exists**, in either direction.

**Non-vacuity (Rule 2).** That zero is only evidence if the comparison can fail. Broken deliberately:

| injected pair | shipped key matches | presence key matches | |
|---|---|---|---|
| `{absolute:0, duration:30}` vs `{duration:30}` | **true** | false | **DIVERGES** |
| `{insulin:0, carbs:12}` vs `{carbs:12}` | **true** | false | **DIVERGES** |
| two identical zero temps *(control)* | true | true | agree |
| `{absolute:0,…}` vs `{absolute:1.5,…}` *(control)* | false | false | agree |

The harness distinguishes the branches. The corpus zero is a real negative.

**So which is it — bug or intent? My reading: a bug, and the register should say so.** Three reasons:

1. The author built an explicit `selected` flag and an `if (!selected)` fallback for "no
   distinguishing fields". Truthiness on `absolute` means the code treats *a zero temp basal* as
   "no value here", which is false in AID terms — a zero temp is the most consequential thing a
   loop writes.
2. The truthiness is uniform across all six fields, which reads as idiom (`if (x)`) rather than a
   per-field judgement. `git log -L` shows the lines only ever touched for driver hardening
   (`4b0bdf1a`, `69b620dd`), never for their semantics.
3. No test uses a zero value — checked `tests/websocket.*.test.js`; the only values are `insulin: 1`,
   `carbs: 9/10/15/18`.

**The honest caveat, and it is load-bearing: the corpus is survivorship-biased in exactly the
direction that hides this defect.** The corpus is *stored* data. If this bug ever caused a treatment
to be swallowed as a false duplicate, that treatment is not in the corpus to be counted. The
measurement bounds "how often the degraded key collides among records that were kept". It cannot
bound "how often a record was lost".

**What would settle it, precisely**: a live replay of an AAPS/NSClient upload burst containing a
zero temp basal and a same-duration neighbour inside 2 s, asserting both are stored. That is the
one arm neither the corpus nor the source can supply. Proposed grade: **medium**, reachable, not
`unsettled` — the behaviour is wrong; only its frequency is unmeasured.

### 3c. BF-10 — it is not documentation-only; there is a shipped file to change

The entry says: *"Not a code defect; it belongs in the operator documentation."* **Measured, that is
wrong.** `cgm-remote-monitor` ships `docker-compose.yml` at the repository root, with a `mongo:`
service, on both branches:

| branch | mongo image | `ulimits:` block |
|---|---|---|
| `master` (15.0.8, what operators run) | `mongo:5.0.32` | **absent** |
| `origin/dev` (15.0.9 candidate) | `mongo:4.4` | **absent** |

`grep -rn 'ulimit\|nofile'` over the whole released tree (excluding `node_modules`) returns **nothing**.
Meanwhile every harness in this repo that touches mongod already passes
`--ulimit nofile=64000:64000` — five research documents do it, because the authors hit exactly this.

**So the fix is both, and the code half lands first**: add
`ulimits: { nofile: { soft: 64000, hard: 64000 } }` to the `mongo` service in `docker-compose.yml`
(MongoDB's own recommended production value, and the value already used across `docs/60-research/`),
**plus** a line in the operator documentation for people running `mongod` outside that compose file.
The compose file is the artefact most self-hosters actually use, which makes this a one-block change
to a shipped file rather than a docs-only note. Landing site: a new branch off `dev`; it touches no
JavaScript and conflicts with nothing in the current batch.

*(Incidental, worth a separate look: `dev` pins `mongo:4.4` in compose while cut 1's release notes
say Mongo 4.4 is being removed from CI, and `master` already ships 5.0.32. Not mine to resolve.)*

### 3d. The fourth one nobody counts: BF-04

**BF-04 is high severity, ships to every current operator, and is not in anyone's open list**, because
its status is `fixed-in-seam` — repaired as a structural side effect of the seam branch's AST, which
is not shipping. Its own detail section says so: *"It should not have to wait for the seam to land.
Extracting the allowlist as a standalone change is a small piece of work and a security fix that
ships to every current operator."* **That extraction has never been done.** Any list of
"operator-facing work outstanding" that omits it is wrong.

---

## 4. Prescribed fixes that have never been run

The register's own failure mode: **two prescribed fixes were wrong when someone ran them** (BF-14's
prescribed fix carried the same hole — BF-33; BF-30's preferred option 1 was measured as a *net
regression*). Every fix below is prescribed **and unverified**, and should carry that word.

**First, the register undercounts its own retraction list.** The header block (**L26**) names five —
BF-12, BF-31, BF-14, BF-16, BF-03. The §1 table itself flags two more that the header omits:

- **BF-08**, L106: "**The interval half of this entry was wrong**" — the drivers already jitter 18 s.
- **BF-30**, L93: "**the register's preferred fix was refuted by measurement**."

Plus BF-16's "secondary consequence" half, BF-28's understated severity, and BF-36's two wrong
ablation attempts. **At least seven, not five.** The same undercount is copied into
`phase0-pr-sequencing-2026-09-15.md:526` and plan L8.

**Second, the suppression-audit tally is now stale.** The header (**L48-53**) says "45 suppressions,
**four defects** … 41 of the 45 were exactly what they said they were", with `no-useless-escape` at
"2 sites | **2** defects — BF-37, BF-38". **BF-39 is a third defect from that same category, on the
same site as BF-37** (`/[_\+]/`). The row should read 2 sites / 3 defects, the total **five defects,
40 of 45**, and the corollary sentence "from BF-35, BF-36, BF-37 and BF-38. All four…" should be five.
This strengthens the section's own thesis and should not be left understating it.

### Unverified prescriptions, by entry

| entry | prescribed fix | status |
|---|---|---|
| **BF-04** | extract the operator allowlist from the seam AST as a standalone change | **never run.** High, operator-facing |
| **BF-18** | `if (limit > 0)` in `findFiltered` — but the entry then says `findFiltered` does not exist on `dev`, and the `dev` equivalent `findMany` "**was left alone**" | prescribed against a function that is not on the target branch |
| **BF-19** | "restrict sortable fields to declared single-typed ones", or a type-bucketed sort key | **never run.** Highest-severity §1b entry |
| **BF-21** | give PG `bulkUpsert` the `(ops, options)` signature and implement `'replace'`, or refuse a mode it cannot honour | **never run.** High; every shipping caller sends `{mode:'replace'}` |
| **BF-22** | *no `*Fix*` line at all.* Carries an explicit hole: reachability is "**subject to a validation layer that was not audited**" | fix undefined, premise unaudited |
| **BF-23** | *no `*Fix*` line* | — |
| **BF-24** | *no `*Fix*` line at all* — although a 2026-09-15 note raises it to **gating the nginx recipe** | **an entry that gates a deliverable with no prescribed fix** |
| **BF-25** | "*Regression test to write when fixing*: two tenants' subjects, assert A's token cannot read B's entries — **that end-to-end test is the gap**" | test named, never written. High |
| **BF-26** | "use `req.tenantPathPrefix` or `req.originalUrl`" | never run |
| **BF-27** | **no detail section at all** | no fix, no evidence, no section |
| **BF-07** | remaining 2.6 ms needs "proof no consumer anywhere in the plugin tier writes to a device status document" | not obtained — this *is* T0.3's unmet gate |
| **BF-17** residual | "`created_at` is not served by `GET /subjects` either … **not fixed** — one more field in the `pick` would round-trip it" | **verified still open**: `bf/auth` `lib/authorization/endpoints.js:44` picks `['_id','name','accessToken','roles','notes']` — `notes` was added, `created_at` was not. An edit still stamps a new `created_at` |
| **BF-05** sibling | unguarded `console.log('Loading', opts)` on the auth-storage read path, "left for an operator's judgement" | **verified still present**, at `storage.js:113` (entry says `:84`) |
| **BF-16** anchors | `SOURCE_ASSERTIONS` in `tools/nsschema/code_model.py` pin text that `bf/food` deletes; must be replaced "when the branch lands" | a scheduled breakage with no owner named. `make schema-code-drift` fails the day `bf/food` reaches a checked tree |
| **CAP-01** | 8 enumerated sites | absence, not defect; never built |

---

## 5. §7a alarm readiness — status claims verified

§7a closes with "**Nothing here may be marked done by inference.**" Checked each row against the
seam worktree (`externals/work/crm-seam`, `81a1f6ce`).

| # | claimed | verdict |
|---|---|---|
| 1 | **DONE** — T4.4a | **Stands, and it is the best-evidenced row in the plan.** `lib/storage/ack-store.js` and `lib/storage/postgres/alarm-ack.sql` both exist. The result table carries **two control arms that return 1** where the real arms return 0 — that is what makes the zeros a measurement. Two named residual costs (a sibling's ack lands one cycle late; MongoDB keeps the in-memory path and gets no restart survival) are stated, not glossed |
| 2 | **T4.4**, not started | **True.** `bin/` holds only `admin.js` and `feed.js` — no `ns-evaluator` entrypoint exists. D5's four hosted entrypoints are two short (T4.3 is the other) |
| 3 | not started | **True**, and consistent with plan L1505 "*Not done*: no entrypoint and no wiring" |
| 4 | not started | **True** — nothing in the tree emits a per-tenant health signal |
| 5 | **fixed 2026-09-15** (BF-31) | **The fix is real; the row's presence on this list is not.** The row's own text says the item does *not* reach alarm text. It was discharged by being **found misfiled**, not by making alarms safer. It is a shared-state item |
| 6 | **fixed 2026-09-15** (BF-29) | **True and honestly qualified** — the row itself says it "does not make per-tenant arming trustworthy; it removes the silence" |
| 7 | open | **True.** T4.4a chose wall time for ack; the data-time/wall-time split is unsettled |

**Nothing is marked done by inference in the sense of an unevidenced claim.** Item 1 carries
controls; items 5 and 6 carry commits and ablations. **But the table reads 3-of-7 done and the
honest count is 1.** Of seven rows: one genuinely complete (1), one partial by its own admission (6),
one misfiled and never an alarm-readiness item (5), four open (2, 3, 4, 7). **Recommendation: move
row 5 out of the table into the shared-state hazard note directly below it** — where the plan already
records the `ctx.moment`/`ctx.language`/`ctx.levels` closure-capture wall — and renumber. Leaving a
discharged-by-reclassification row in a safety checklist is precisely the inference the section
forbids.

### A defect in the plan that §7a's own row 5 proves

`BF-22` was renumbered to **BF-31** (register renumbering note). The plan has not been swept:

| plan line | text | correct id |
|---:|---|---|
| **351** | "process-wide `language`/`levels`, **BF-22**" | **BF-31** |
| **1189** | "Filed as **BF-22**, since it is a live defect in single-tenant deployments too" | **BF-31** |
| 1553 | "BF-21, **BF-22**, BF-23" (the write-path trio) | **correct — leave alone** |
| 1573 | "**BF-31** (was BF-22)" | correct |

So one document uses `BF-22` for two different defects, and `BF-22` today means the dotted-field
`updateOne` divergence. **L1189 additionally carries the claim BF-31's measurement refuted** — "level
names included, and that is how alarm text reaches a push notification" — which §7a row 5, in the
same document, explicitly corrects. Fix both halves of L1189 together.

---

## 6. The T3.0 amendment chain — what each DONE-EXCEPT still owes

For whoever writes the T3.0 specification. Every site below was opened and read at
`externals/work/crm-seam` `81a1f6ce`; **the line numbers in the plan's amendment table are accurate
except where noted.**

**What is NOT owed, and must not be re-litigated**: each task's measurements, isolation evidence and
ablations all stand. T3.1's 18 broken guards (three vacuous, all three the tests' fault), T3.2's
refuse-to-start proof with its `EADDRINUSE` control, T3.3's structural reachability crawl and its
deep-equal rebuild property — none of that is touched by D13/D14. Only the credential assumptions are.

### T3.1 — tenant resolution middleware

- **Owed**: `tenantClaim` (`lib/server/tenant-middleware.js`, function opens at **L139**;
  `enclave.verifyJWT(jwt)` is at **L144**, so the plan's cited range `139-143` stops one line short
  of the call) verifies every tenant's tokens with one install-wide key. D14 replaces this with a
  per-tenant signing key, looked up by the tenant id T3.1 has **already resolved** — the ordering
  property that makes D14 available at all.
- **Also owed, and a consequence rather than a defect**: T3.1's departure 2 (*"a presented credential
  with no tenant claim is refused by default"*) exists **only** because subjects are one process-wide
  array. Once T3.0 gives subjects a tenant home, that knob's default should be revisited — the plan
  says "a knob, not a constant, so T3.3 can revisit" and nothing has.
- **Not owed**: the host-header rule, the one-capture-group regex, the no-flags rule, the charset
  re-check, `withTenant` binding rather than opening a transaction, the `fromEnv` null-unless-multi
  guard. All stand.
- **Pre-existing, listed separately by the plan and correctly**: `lib/authorization/index.js:169-173`
  — **verified exactly as cited** — grants shiro `['*']` on a matching deployment `api_secret` with
  no tenant dimension. D13 makes this path unreachable under `multi`.

### T3.2 — `bin/admin.js` and `platform.sql`

- **Owed**: `lib/admin/platform.sql` holds exactly **two** tables — `tenants` (L23) and
  `tenant_members` (L49). **Verified: no settings table, no secrets table, no signing-key column.**
  `tenant_members.subject_id` is `uuid NOT NULL` at **L52** with **no foreign key and no subjects
  table to reference**. T3.0 owes: a per-tenant configuration home, per-tenant credential storage,
  the per-tenant signing key with a rotation story, and something for `subject_id` to point at.
- **Owed, inherited from T4.4a**: "the export manifest now carries ack rows; whether it *should* is
  not this task's call" — **explicitly left open for T3.2's owner** and still open.
- **Note for the schema author**: `tenantScopedTables` discovers tables by asking the catalogue for a
  `tenant_id` column rather than from a hardcoded list. Any table T3.0 adds is **automatically**
  swept into the admin export and the delete cascade. That is the intended behaviour (GATE 3's
  orphan argument), but a secrets table entering an export manifest by catalogue discovery is a
  decision to make deliberately, not to inherit.
- **Not owed**: the refuse-to-start guard on a non-loopback bind, and its proof.

### T3.3 — `ctxFor(tenantId)`

- **Owed, and the plan's citation is right but incomplete.** `tenant-context.js:137` is the
  **comment** stating the rejected reasoning — verified, it reads *"`env.enclave` is shared … the
  deployment's API secret and JWT signing key, of which there is exactly one"*. **The code that
  implements it is elsewhere**: `PER_TENANT_ENV_KEYS = ['settings','extendedSettings','err','notifies']`
  at **L143**, consumed at **L278** (`if (PER_TENANT_ENV_KEYS.includes(key)) continue;`) — everything
  *not* in that list, `enclave` included, is shared by reference. **T3.0's wiring step must change
  L143 and L278, not L137.** A spec that only names L137 changes a comment.
- **Owed**: tenant settings still have **no source**. `deriveEnv` takes overrides as a parameter and
  nothing supplies them, because nothing stores them. This is T3.0 step 3 and it is the whole reason
  the mechanism currently does nothing in production.
- **Owed**: `DERIVED_CONTEXT_KEYS` (L123) is four entries with a test that fails if it grows, naming
  T3.4. If T3.0 adds per-tenant credentials to the derived context, that test fires **by design** —
  expect it, and treat firing as the review checkpoint it was built to be.
- **Owed, but reclassify before writing it down**: T3.3's "*Not done, and named*" paragraph (plan
  L1187-1191) says `language`/`levels` are shared "and that is how alarm text reaches a push
  notification". **That claim is refuted** (BF-31). Rewrite the paragraph as: the process-wide
  `language` instance is a cross-tenant leak in the **assistant** path, not the alarm path — and the
  real obstacle is the one the plan records two paragraphs later, that plugins capture `ctx.moment`,
  `ctx.language` and `ctx.levels` **at plugin init**, so a per-tenant `ctx` cannot re-point them for
  an already-initialised plugin. **That closure-capture wall is the actual T3.0/T3.3 blocker** and it
  is currently buried under a refuted sentence.
- **Not owed**: the structural isolation crawl, the cache-bound split between T3.1 and T3.3, the
  deep-equal rebuild property, and the two tests that exist because the agent's own code failed them.

---

## 7. The contradiction table

Line numbers at head `75c38a17`. The sequencing document gained 12 lines at its line 3 during this audit; its numbers below are post-shift. "Fix by" names the agent role, not a person.

| # | document | line | what it says | what is true | fix by |
|---:|---|---:|---|---|---|
| 1 | register | legend **67-74** + every §1 row | `fixed` reads as resolved | **no entry is `landed`; all 26 §1 fixes sit on unpushed branches**. The column tracks work, not operator exposure | register owner |
| 2 | register | **124** | BF-27 has a table row | **no detail section exists** for BF-27 — the only id in the file without one | register owner |
| 3 | register | **587, 594-600** | BF-14 "Re-graded to **high**" then "**It returns no wrong data** … It **stays in the register**" | the second paragraph is superseded; fold it in as history | register owner |
| 4 | register | **26-32** | "**Five** entries have had a claim fail on contact" | **at least seven** — BF-08 (L106) and BF-30 (L93) are flagged in §1 but omitted here | register owner |
| 5 | register | **48-53** | "45 suppressions, **four** defects … 41 of 45"; `no-useless-escape` "2 sites \| **2** defects" | **five** defects, 40 of 45; that row is 2 sites / **3** — BF-39 is on BF-37's own site | register owner |
| 6 | register | **41** | "a corollary, from BF-35, BF-36, BF-37 and BF-38. **All four**" | **all five**, with BF-39 | register owner |
| 7 | register | BF-17 / BF-30 / BF-31 bodies | "*Not reproduced against a live …*" | all three **were** reproduced; the top block says so and the body was never swept | register owner |
| 8 | register | **107** (BF-09 row) | "a `0` **insulin/carbs** value" | measured: **0 zero-valued insulin in 107,732; 0 carbs in 12,394**. The field is **`absolute`** — 67,521 of 153,315 (44 %), a zero temp basal | register owner |
| 9 | register | BF-09 detail | severity "**unsettled** — may be intentional" | grade **medium**; the ±2 s window (`websocket.js:452`) bounds it and is unstated; name the live-replay arm that would settle it | register owner |
| 10 | register | BF-10 detail | "Not a code defect; it belongs in the **operator documentation**" | `docker-compose.yml` ships a `mongo` service with **no `ulimits:`** on both `master` and `dev`. **Both** — compose file first | register owner |
| 11 | register | BF-05 detail | sibling `console.log` at `storage.js:**84**` | **line 113** on `bf/auth`; still present | register owner |
| 12 | register | **107** | BF-09 at `websocket.js:**535-568**` | **538-566**. Same stale range in seam interface §4.4 | register owner |
| 13 | register | BF-04 row/detail | status `fixed-in-seam` | **high severity, ships to every operator, extraction never done** — omitted from every "open operator-facing" list | register owner |
| 14 | plan | **7** | "**Phase 0 is done**" | plan **L529** "T0.1 … **In flight**", **L541** "T0.3 — **GATE NOT MET**". 4 of 5 | plan owner |
| 15 | plan | **7** | "**Five** branches ready to push" | **nine** cgm-remote-monitor branches + `fix/connect-timer-jitter` + `v0.0.14` | plan owner |
| 16 | plan | **8** | "**13** closed, **3** new, **4** corrected" | **26** closed-or-partly, **8** new (BF-32…39), **≥7** corrected | plan owner |
| 17 | plan | **351** | "process-wide `language`/`levels`, **BF-22**" | **BF-31**. `BF-22` today is the dotted-field divergence | plan owner |
| 18 | plan | **1189** | "Filed as **BF-22** … **that is how alarm text reaches a push notification**" | **BF-31**, and the alarm-text claim is **refuted** by §7a row 5 in the same document | plan owner |
| 19 | plan | **1573** (§7a row 5) | listed as a done alarm-readiness item | discharged by **reclassification**, not completion — its own text says it is a shared-state item. Move it out; the table reads 3-of-7 and the honest count is 1 | plan owner |
| 20 | plan | **1197** | "of 70 files … only six are server-resident and written after load; **the other 40** are browser files" | 70 − 6 = 64. Audit table is server 17 / both 13 / browser 40 | plan owner (low) |
| 21 | plan | T3.0 table | T3.3 site = `tenant-context.js:**137**` | L137 is the **comment**. The code is `PER_TENANT_ENV_KEYS` **L143** + the copy loop **L278** | T3.0 spec author |
| 22 | plan | T3.0 table | `lib/server/enclave.js:**29**` | **line 30** | T3.0 spec author |
| 23 | sequencing | **1, 3, 69, 87** | "**five** branches" | **L40 of the same file says seven**; the tables list **A–I = nine** | sequencing owner |
| 24 | sequencing | **526** | "**Five** register entries had claims that did not survive" | same undercount as register L26 — **at least seven** | sequencing owner |
| 25 | sequencing | **165** | bf/parms commits "`522c6ffb`, `eb0bc918`, `c9a7a21c`" | actual branch order is `522c6ffb`, `c9a7a21c`, `eb0bc918` (BF-37, BF-38, BF-39) | sequencing owner |
| 26 | sequencing | **71-79** | trial-merge matrix, 6 pairs | predates `bf/food`, `bf/merge`, `bf/parms`, `bf/connect-pin`. Prose claims "clean against all six/seven"; **the matrix was never extended** | sequencing owner |
| 27 | memory `multitenancy-target-decision.md` | **67-68** | "**STOPPED** … Phase 0 **0 of 5** … **29 open**" | 4 of 5; 12 open BF + CAP-01. **Replace with a pointer**, do not re-number | memory owner |
| 28 | memory `release-train-and-work-queue.md` | **15-17** | "three open … **BF-16**, BF-09, BF-10" | **BF-16 is fixed**. Two remain; BF-04 is a third of a different kind | memory owner |
| 29 | memory `release-train-and-work-queue.md` | ~44-48 | "`queue/work-queue.yaml` is the source of truth … `make queue-status` runs each item's gates" | **no `queue/` directory and no `queue-status` target exist** | memory owner |

---

## 8. Method, and what this audit did not do

**Measured**: register reconciliation programmatically (table row vs detail heading, all 40 ids);
branch inventory by `git rev-parse` in each of the 15 worktrees under `externals/work/`; connector
ancestry by `git merge-base --is-ancestor`; BF-09 by aggregate census over
`externals/ns-data/patients/*/raw/treatments.json` (11 sites, 277,690 documents) with a
four-case non-vacuity harness; BF-16, BF-10, BF-17's residual, BF-05's sibling and every T3.0
amendment site by opening the file and reading the cited line.

**Health data**: only aggregate counts were computed. No name, email, device id, site id or document
was read into this report.

**Not done**: BF-09's live-replay arm (§3b) needs a running server and a real uploader burst — it is
the one thing that would move that entry from *graded* to *settled*, and it is not something a
read-only audit can supply. BF-19, BF-21, BF-24, BF-25 and BF-26 were **not** re-reproduced; §4
reports only that their prescribed fixes have never been run, which is a statement about the
register, not a re-verification of the defects.

**Confirmed, not contradicted**: the connector pin finding survives checking. `9fa2c3c`, `5349d47`,
`77e2396`, `8406edf`, `51b6e6e` and `c1cce2a` are each **not** ancestors of `234d47c`
(`git merge-base --is-ancestor`, six for six), so `dev`'s pin does ship without the three
log-redaction fixes exactly as the brief states. `origin/main` is `b394411` at version `0.0.13`;
`release/v0.0.14` is `649a7de` at `0.0.14`; tags `v0.0.13` and `v0.0.14` both exist locally.
