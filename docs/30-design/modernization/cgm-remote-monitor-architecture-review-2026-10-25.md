# cgm-remote-monitor architecture review: the patterns behind recent defects, as decision questions

*Contributor- and maintainer-facing review. **Status (snapshot, 2026-10-25): for maintainer
discussion; it proposes no new design.** It maps the register entries of roughly the last six weeks
onto the designs that already exist, and asks the maintainers seven questions (§4). Defect facts and
ids: [backfix register][reg] (ids below link to it; find the id there). Item state:
[`queue/QUEUE.md`](../../../queue/QUEUE.md). Decisions: the
[execution plan](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md) (D1–D20) and the
documents each row cites. Code refs are those the cited documents name; nothing was re-measured for
this review.*

## 1. Purpose and scope

| | |
|---|---|
| hub | `cgm-remote-monitor`: its four write paths (API v1, API v3, the v1 socket, in-process callers such as nightscout-connect and plugins), its read paths, its in-memory cache and its two sockets |
| clients | controllers and uploaders (AndroidAPS, Loop, Trio, xDrip+, xDrip4iOS, oref0, nightscout-connect, tconnectsync) and followers, as the hub sees them: what they send, and what they assume about replies, cursors and stored shapes |
| question | which root causes recur across the register, which existing design already answers each, what of that is decided and built, and what the maintainers would need to decide to stop each pattern recurring |
| out of scope | tenancy itself (Phases 1–4 of the execution plan), dependency advisories, and the alarm and report entries that fit none of the patterns below |

## 2. Evidence: register entries by root-cause pattern

Entries filed or touched from BF-99 (2026-09-25) to BF-192 (2026-10-25), plus older entries clearly
in a pattern. Each id is counted once, under its primary pattern; "also" lists the other patterns it
bears on.

| # | pattern | entries (primary) | n | also | state of those entries |
|---|---|---|---:|---|---|
| **P1** | **Divergent write paths.** The same write gives a different stored result, reply or emission depending on which of the four paths carries it; each path applies the shared rules itself | [BF-09][reg], [BF-99][reg], [BF-100][reg], [BF-103][reg], [BF-109][reg], [BF-112][reg], [BF-116][reg], [BF-122][reg], [BF-130][reg], [BF-131][reg], [BF-136][reg], [BF-141][reg], [BF-143][reg], [BF-146][reg], [BF-165][reg], [BF-166][reg], [BF-170][reg] | 17 | BF-122, BF-146 → P4; BF-170 → P5 | 13 released in 15.0.9, BF-09 merged to `dev`; BF-165, BF-166, BF-170 in PR #8845 |
| **P2** | **Reads trusting stored data.** A reader or lookup assumes the shape today's writer produces; a record stored in another shape (by an older release, another path, or an unchecked write) gives a wrong answer, a missed record or a stopped process | [BF-101][reg], [BF-102][reg], [BF-111][reg], [BF-117][reg], [BF-126][reg], [BF-135][reg], [BF-140][reg], [BF-142][reg], [BF-145][reg], [BF-171][reg]; **one entry filed under the disclosure rule** | 11 | the disclosure-rule entry also bears on P1; BF-126 → P3 | 9 released in 15.0.9; BF-145 in PR #8845; the disclosure-rule entry open |
| **P3** | **Validation living only in clients.** A check that every client needs (ordered range, declared units, a usable id) runs in a client or in one path's route layer, so the hub stores what another client then drops, clamps or misreads | [BF-115][reg], [BF-180][reg] | 2 | BF-180 → P5 | the register understates this pattern: the [write-validation design §1](../../60-research/modernization/write-validation-design-2026-10-25.md) lists 24 AndroidAPS ingestion drops, Trio's 80–200 mg/dL clamp and the careportal's client-only Temporary Target range, none of which the hub checks |
| **P4** | **Implicit delivery and cursor semantics.** What a client may assume about history cursors, `srvModified` and socket events is not stated, so a server change or a client's cursor rule loses or delays records | [BF-13][reg], [BF-93][reg], [BF-95][reg], [BF-120][reg], [BF-144][reg], [BF-164][reg], [BF-181][reg] | 7 | BF-181 → P2 | BF-164 blocked on write checks (log mode) covering every path, plan C, decided 2026-10-25: filtered broadcast after checks cover every path; filter and path-naming details open (measured 2026-10-25: missed, not only delayed); BF-181 and BF-95 open; BF-93 fixed on a branch |
| **P5** | **Units and identity conventions differing by client.** Each client spells units, labels records and signals state its own way; the hub stores the label and each consumer joins number and unit itself | units: [BF-67][reg], [BF-86][reg], [BF-118][reg], [BF-124][reg], [BF-128][reg], [BF-138][reg], [BF-139][reg], [BF-157][reg], [BF-172][reg], [BF-173][reg]; identity and conventions: [BF-114][reg], [BF-121][reg], [BF-123][reg], [BF-169][reg] | 14 | BF-121 → P1 | BF-67, BF-86 open (ladder decided 2026-10-13); BF-157, BF-172, BF-173 merged to `dev`; BF-169 in PR #8845; the rest released in 15.0.9 |
| **P6** | **Test and CI blind spots.** A suite or lane that passes without exercising what it names | [BF-53][reg], [BF-54][reg], [BF-55][reg], [BF-59][reg], [BF-96][reg], [BF-158][reg], [BF-167][reg], [BF-177][reg], [BF-185][reg], [BF-189][reg], [BF-192][reg] | 11 | — | BF-192 is a test-measurement blind spot, not a product regression: since #8542 the reports page draws its first report as soon as the profile loads, so the populated test measured a drawn report instead of an empty form (fix in PR #8843); plus two without an id of their own: browser CI ran zero tests from #8839 until the runner fix `e767ce4e` in #8843 (BF-192 detail), and BF-07's fix has a caller no test pins (reverting it stays green, BF-07 row, 2026-10-25) |

Other patterns seen in the same period, not taken further here:

| pattern | entries | existing answer |
|---|---|---|
| a failure or unbounded request input stops or stalls the process | [BF-107][reg], [BF-108][reg], [BF-129][reg], [BF-151][reg], [BF-155][reg], [BF-156][reg], [BF-182][reg], [BF-187][reg], [BF-188][reg]; [BF-72][reg] and [BF-161][reg] by mechanism only, as the register words them | D8 (closed operator set; plan §3); write-path alignment §4.5 ("never answer a client error with a 5xx") |
| the server logs what it was sent | [BF-42][reg], [BF-104][reg], [BF-183][reg], [BF-186][reg] | none general; each fixed where found |
| a permission decided per route | [BF-105][reg], [BF-152][reg], [BF-184][reg] | [authority spec](../platform/spec/authority.md); BF-152's staged flag |

## 3. Each pattern against the designs that exist

| # | existing design (section) | decided | built | gap |
|---|---|---|---|---|
| P1 | [Write contract](../tenancy/write-contract-spec-2026-10-07.md) §2 (one step `write(intent)` in `collectionFor`), §3 (U1–U8), §5 (gates G1–G8); [execution plan §4.1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#41-the-write-contract-belongs-behind-the-seam); [sync-transport](../platform/spec/sync-transport.md) T1–T4 | §6.1 (2026-10-12): merge on match (Q1, with RFC 7386 null removal), identical re-send keeps each path's behaviour (Q2 b1), entries `date`+`type` and profile `created_at` keys (Q3), the socket's ±2 s match kept as `near` (Q4), activity like the rest (Q5), two releases: step with the matrix pinned (patch), then the changes (minor) (Q6) | the four 15.0.9 rule modules (`object-id-forms`, `srv-dates`, `soft-deleted`, `treatment-fallback-key`), called by 18 files; `tools/qc/write-contract-matrix.js`; the step itself is not built | `WRITE-CONTRACT` is blocked on `SEAM-REFRESH`, so each P1 defect is fixed per path. On `dev` `43289dde` stored state differed between paths in 33 of 66 groups, and a cross-path re-send was stored twice in 38 of 66 path pairs (write contract §0) |
| P2 | [Write-validation design §3.3](../../60-research/modernization/write-validation-design-2026-10-25.md) (R1 flag on read, R2 report, R3 migrate, not recommended); [identity](../platform/spec/identity.md) I2, I9; D20 quirks by version; `OID-MIGRATION` | read tolerance of both `_id` forms (15.0.9, #8758); "refuse a value the server could never have loaded; tolerate on read a value a working site may hold" (maintainer, 2026-10-25, [alignment §5](write-path-checks-alignment-2026-10-25.md)) | `matchEitherForm` / `idForms` for ids; per-entry guards for the rest | no stated contract for which stored shapes a reader must tolerate, and no rule that a stored record must never stop the process (boot and auth paths included); R1/R2 are queued (`MOD-WRITE-VALIDATION-READ`), not built |
| P3 | [Write-path checks alignment](write-path-checks-alignment-2026-10-25.md) §3 (one pure check module called by the step, outcome `refused`), §5 (classes a/b/c); write-validation design §2, §3.5 (class b surfaced from registration G2 `unit`/`range`, never enforced) | `WRITE_VALIDATION=off\|log\|reject`, default `off` (D1); the D2 batch reply; the double label refused (D4), all 2026-10-25 | `lib/server/write-validation.js` on local `feat/api3-domain-validation` (ready to push): Temporary Targets on v1 REST and v3; socket paths not covered | checks that refuse a write sit in different places per path, with different replies and batch rules (alignment §2); D3 (whether `reject` ever becomes the default), D5, D6 open; under `reject` no client sees a refusal ([upload-refusal note](../../60-research/remedial/upload-refusal-client-behaviour-2026-10-25.md) §2) |
| P4 | [Sync-transport](../platform/spec/sync-transport.md) T3 (server-owned `srvModified`), T6 (merged cursor), T8 (opaque cursor), T9 (low watermark; the idea is the stream-processing watermark of the Dataflow model), T10 (history is the record; a socket event never moves the cursor), T12 (open); write contract §2.4 (one change event) | T3's restore-at-boot (BF-144, 15.0.9); BF-164 reclassified as a behaviour question (2026-10-12); plan C, decided 2026-10-25: filtered broadcast after checks cover every path; filter and path-naming details open (alignment §6); `/storage` stays v3-only until then | `srv-dates.js` (unique, monotonic within one process, restored at boot) | T5–T10 are proposals; AndroidAPS sets its cursor from each pushed frame (a plain set), the opposite of T10, so a v3 write moves it past earlier non-v3 records ([websocket lab](../../60-research/remedial/aaps-websocket-delivery-lab-2026-10-25.md) §1–2); a future `srvModified` pins the clock (BF-181); the in-flight window is unmeasured (sync-transport §8.2) |
| P5 | Units: [profile boundary](../platform/glucose-units-at-the-profile-boundary-2026-10-21.md) U0–U5; write-validation §3.4 (N1 spelling only, N2 mg/dL plus original); state-intent A11 ("units are declared, never assumed"). Identity: [identity](../platform/spec/identity.md) I1–I9, §5; D20 two-id rule; `ID-SIMPLE-MATCH`; the [Loop reply's simple contract](../platform/upstream-asks-loop-identifier/README.md#the-simple-contract) | U0 merged (BF-172, BF-173, BF-174); BF-67/86 ladder (2026-10-13); `identifier` mandatory at a future version boundary and for registered instances (`ID-ABSENT-DECISION`, 2026-10-18) | U0 only; `ID-SIMPLE-MATCH` not started | units: UD2–UD5 and N1/N2 with the conversion constant (18, 18.016, 18.01559 all in use) open; spellings split by client (AndroidAPS exact `mmol`, NightscoutKit exact `mmol/L`, Trio reads no units on a Temporary Target). Identity: which version makes `identifier` mandatory; `ID-CLIENT-OID-DECISION` (the simple contract's "`_id` wins" differs from I5's identifier-first order) |
| P6 | Write contract §5 (each gate proved by a control that removes the step from one path); RT-TEST-TIERS (#8839: tier map, tier check, `test:affected` at depth 4 from a 100-mutant sample) | tiers by measurement (unit = passes with no MongoDB reachable) | tier map and `test:affected`; CI matrix PR #8843 (with BF-185's fix and the browser runner fix) awaiting review | nothing fails a CI lane that ran zero tests; G1–G8 are not CI gates (controls seen to fail for G1, G3, G7 only; the rest proposed); test isolation depends on file order (BF-185, BF-189) |

## 4. Decision questions for the maintainers

### Q-A · Pull the single write step forward, ahead of multitenancy?

| option | trade-off |
|---|---|
| (a) keep `WRITE-CONTRACT` behind `SEAM-REFRESH` (today) | no extra branch to maintain; P1 defects keep arriving one path at a time and each fix touches up to four paths |
| (b) **minimal slice on `dev`, single-tenant, MongoDB only**: `write(intent)` over today's collections, holding (1) one check module (the `write-validation.js` rules, run before target resolution), (2) one reply shape (`WriteResult.items[]`: outcome, `_id`, `identifier`, `reason`, mapped per route), (3) one change event per write, fanned out by one subscriber to today's three consumers with today's emissions pinned; the seam later wraps the same step | gives P1 and P3 one door and gate G2 something to enforce; shipped as Q6's patch release with G1 holding "no cell changed"; costs a rebase of the step onto the seam when `SEAM-REFRESH` happens, and must not change which writes reach `/storage` until Q-D is answered |
| (c) (b) plus the §3 changes in the same release | one release instead of two; drops Q6's pinned-matrix safety, which §6.1 chose |

Evidence: P1's 17 entries; write contract §0, §2.3–2.5, §5 G1/G2; execution plan §4.1 lists BF-122,
144, 141, 143, 146, 135, 109, 110, 116, 117, 130, 136, 140, 142, 145 as defects the step would have
prevented. Ask: AndroidAPS, Loop, xDrip+ (the reply shape and retries, write contract U6).

### Q-B · Who owns which validation, and how a controller declares its policy

| option | trade-off |
|---|---|
| (a) the split in alignment §5: structural invariants (class a) in the hub's check module, on the staged ladder; controller policy (class b) stays in the controller and is surfaced from its registration (G2 `unit`, `range`), never enforced; time sanity (class c) flagged only | one rule for every new check; needs controllers to publish declarations before the hub can surface them |
| (b) the hub also enforces declared ranges | one place refuses; two controllers on one site can disagree, and a refusal is lost silently for most clients today |
| (c) status quo: each client validates | no hub change; P3 continues (each client drops, clamps or misreads differently) |

Evidence: write-validation design §1–2, §3.5; upload-refusal note §2, §5. Ask: AndroidAPS, Trio,
Loop: which class-a checks they want the hub to enforce, and whether they would publish G2 ranges.

### Q-C · The read-path contract

| option | trade-off |
|---|---|
| (a) defensive reads: every reader tolerates any stored shape | no stored data changes; every new reader must repeat the tolerance, which is how P2 recurs |
| (b) the hub guarantees stored shapes: normalise on write and migrate what is stored | readers stay simple; a migration moves `srvModified` for every changed record into every history cursor (R3), and relaying writers can re-send the old shape (alignment §4.3) |
| (c) **normalise on write; tolerate and flag on read; never hide** (R1 flag on v3 reads, R2 report, opt-in migrations such as `OID-MIGRATION`) with one rule beside it: no stored record stops the process | matches the 2026-10-25 maintainer rule; needs the flag's shape and a list of reader entry points (boot, auth, cache load) that must not throw on a stored record |

Evidence: P2's 11 entries, among them BF-126 and BF-171, where one stored record stopped the
process at every restart; write-validation design §3.3. Ask: nightscout-connect,
oref0, tconnectsync and AndroidAPS 3.4.x (relaying writers), and every client on what a flag on read
would let them show.

### Q-D · The delivery contract for `/storage` and history

| item | options | evidence |
|---|---|---|
| events | plan C, decided 2026-10-25: filtered broadcast after checks cover every path; filter and path-naming details open; until then `/storage` stays v3-only, and afterwards only records that pass the type checks are announced (no unfiltered broadcast) / every state-changing write produces exactly one event, from every path (write contract §2.4, U7) / v3 writes only (today) | 0 of 190 non-v3 cells emitted (write contract D8); the lab shows websocket-mode AndroidAPS can miss careportal, v1 and connector records; AndroidAPS-side safety research (mechanism level): records from other paths already reach AndroidAPS through history, some cannot be decoded by it, and a pushed undecodable frame is expected to end the app process on AndroidAPS 3.4.2.6 (read-derived) |
| cursor | `srvModified` server-owned and monotonic (T3, built within one process) / an opaque cursor (T8) with a low watermark (T9) / both | BF-144 (fixed), BF-181 (open); sync-transport §8.2–8.3: the in-flight window and several writers are unmeasured |
| client rule | clients may assume: history is the record, an event never moves the cursor (T10) / events carry the cursor before them so a client can detect a gap (§8.1) | AndroidAPS moves its cursor on each pushed frame (lab §1) |

Decide in this order: what clients may assume, then which writes emit. Ask: AndroidAPS first
(the drafted note); also any follower that subscribes to `/storage`.

### Q-E · Units and identity canonicalisation

| item | options | evidence |
|---|---|---|
| units at write | N1 canonical spelling (Temporary Targets only until NightscoutKit reads both spellings) / N2 mg/dL plus the original, a major, with a D20 quirk entry / labels as written, converted once at the profile boundary (U1–U3) | write-validation §1.3, §3.4; profile boundary §2–3; BF-157, BF-172, BF-173, BF-180 |
| conversion constant | 18 / 18.016 / 18.01559 | all three in use (write-validation §3.4) |
| identity | ship `ID-SIMPLE-MATCH` (v1 entries and devicestatus match on `identifier`); name the version boundary where `identifier` becomes mandatory; settle `ID-CLIENT-OID-DECISION` | identity §5; Loop writes 3,078 groups of distinct statuses sharing `created_at`+`device` at 11 of 12 corpus sites (write contract §6.1 Q3) |

Ask: Loop (NightscoutKit spellings, the simple contract), Trio (units on Temporary Targets),
AndroidAPS (`mmol` exact match, constant 18), xDrip+ and xDrip4iOS (entries identity).

### Q-F · Test architecture that cannot go blind silently

| option | trade-off |
|---|---|
| (a) a vacuity check: each CI lane fails if it ran 0 tests (or fewer than its tier map lists) | cheap; would have caught the browser lane; needs the tier map as the expected count |
| (b) cross-path conformance from the write-contract matrix as a gate (G1, with G2's grep for direct adapter writes), each with its break-it control | catches P1 before review; the matrix needs a committed expected file per release line |
| (c) test isolation as a gate: shuffled-order `test:smoke` runs in CI | catches BF-185/BF-189 shapes; adds run time |

Evidence: P6's 11 entries; write contract §5; RT-TEST-TIERS. No controller input needed.

### Q-G · Sequencing against the release train

| option | trade-off |
|---|---|
| (a) all of the above after the 16.0.0 cuts and the seam refresh | no contention with cuts 3–5 (#8844 and later); P1–P4 entries keep arriving through 16.x |
| (b) **per the staged ladder**: now, Q-F(a) (CI only, no release); 16.0.x or 16.1 (S1), `WRITE_VALIDATION` with `log` (write-validation §4), the write-step patch release (Q-A b) and `ID-SIMPLE-MATCH`; 16.2 (S2), the §3 changes as a minor and opt-in strict flags; 17.0.0 (S3), strict defaults decided with the controller authors | follows the [defaults calendar](../../60-research/modernization/defaults-calendar-2026-10-25.md) §3.2–3.3 slots (offsets are proposals); each step is reversible within a major |
| (c) fold the write step into a cut | fewer releases; a behaviour change clients see rides in a dependency and build cut, and one release then carries both classes of change |

Evidence: write contract §4 (minor unless replace-on-match), §6.1 Q6; defaults calendar §3.3; the
[versioning policy](semver-and-release-versioning-policy-2026-09-15.md) §2. No controller input
needed beyond Q-B to Q-E.

## 5. Proposed next steps

| # | step | answers | needs |
|---|---|---|---|
| 1 | Add a zero-test check to every CI lane (with #8843) | Q-F(a) | maintainer review of #8843 |
| 2 | Send the drafted AndroidAPS note (BF-164, BF-152, ingestion checks; drafted as a public issue and a private report, not yet sent) with Q-D's client-rule question added | Q-D, Q-B | maintainer |
| 3 | Decide Q-A; if (b), cut `write(intent)` on `dev` with today's matrix pinned and G1/G2 as gates | Q-A | maintainer, second reviewer |
| 4 | Write the read contract for Q-C: reader entry points that must not throw on a stored record, and R1's flag shape | Q-C | maintainer |
| 5 | Ship `ID-SIMPLE-MATCH` and push `MOD-WRITE-VALIDATION` (default `off`; operators may try `log`) | Q-E, Q-B | maintainer |
| 6 | One cross-project note to the controller authors (table below): [drafted 2026-10-25](../platform/upstream-asks-controller-authors/README.md), not yet sent | Q-B to Q-E | controller authors |

| question | AndroidAPS | Loop (NightscoutKit) | Trio | xDrip+ / xDrip4iOS |
|---|---|---|---|---|
| Q-A reply shape, retries | yes | yes | yes | yes |
| Q-B class-a checks, G2 ranges | yes | yes | yes | — |
| Q-C what a read flag would let them show | yes | yes | yes | — |
| Q-D cursor rule, events from every path | **yes, first** | — | — | — |
| Q-E units spelling and constant | yes | yes | yes | — |
| Q-E identity and the simple contract | yes | **yes** | yes | yes |

[reg]: ../remedial/nightscout-backfix-register.md
