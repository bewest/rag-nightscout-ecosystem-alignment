# Auditioning a dosing algorithm: same inputs, shadow only

*Contributor-facing.* **Snapshot — describes 2026-10-18. Status: current; a research note, not a
design. The harness in §4 is proposed, not specified, and nothing here is decided.** Repository
facts are read at this repository's `ef29293a`; counts marked **measured** were taken that day with
the command or method named beside them. Facts about an independent implementation (§3) are
**read-derived from its source and documents, 2026-10-18; not reproduced here**. Current decisions:
[execution plan §1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#1-decisions).

**The question.** Can a dosing algorithm be compared with others on the same recorded inputs, in
shadow — computing what it would do, with no path to the pump — and what would the ecosystem need
for that comparison to be trustworthy? "Auditioning" here means exactly that: an algorithm is heard,
never given control.

---

## TL;DR

| | What exists | What does not exist |
|---|---|---|
| **Same inputs, several implementations** | the ADR-005 adapter protocol and its vectors (§2.1); a shadow mode in Trio's Swift port work and in an independent implementation (§2.2, §3.2) | an input snapshot per run that can be replayed exactly after a divergence |
| **Knowing which algorithm ran** | D19 content-addressed definitions — for a controller's data model (§1.2) | an identity for an algorithm, its implementation version and settings schema |
| **Knowing what the run lacked** | replay completeness per controller: 20% Loop, 50% oref0 recorded (§2.3) | completeness shown per run |
| **An independent reference** | captured controller outputs in the public vectors (§2.1) | a stated reference implementation per family |
| **Keeping it out of control** | D18: the controller validates and enacts | a recorded decision, outside any harness, that moves an algorithm from shadow to control |

---

## 1. Three separate objects

### 1.1 Definition, instance, authority

| Object | What it is | What it carries |
|---|---|---|
| **Algorithm definition** | what the algorithm is | identity; implementation version; the settings it takes (a schema); the inputs it requires; its output contract (decision, predictions, intermediate values) |
| **Execution instance** | one running copy of a definition | its version as built; its configuration (the settings values); where it runs; the provenance of its inputs and outputs |
| **Execution authority** | what the instance may do with its result | *replay only* (offline, on stored inputs), *shadow* (live inputs, result stored and never enacted), or *authorised control* (the result reaches a pump) |

The three vary independently. One definition can run as a dosing instance on one phone and as a
shadow instance on another; one instance can be moved from shadow to control without any change
to its code. An audition is about the first two; it must never change the third (§4.6).

### 1.2 What D19 covers, and what it does not

D19 ([execution plan §2.6.2](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#262-d19--definitions-and-instances-maintainer-2026-10-14);
specified in [hub-sync §3.6](nightscout-hub-sync-architecture-2026-09-11.md#36-definitions-and-instances),
not implemented) has the same three-way split, for **controllers**:

| Algorithm object | Nearest D19 element | Fit |
|---|---|---|
| definition | a definition: a `ControllerStateModel` registration, its id the SHA-256 of its RFC 8785 canonical JSON | **partial.** The document describes the controller's data model — documents, intent kinds, composition, commands, `replayInputs`, `settings`, `extensions` ([hub-sync §3.1](nightscout-hub-sync-architecture-2026-09-11.md#31-registration)). Its only algorithm members are `metadata.algorithmFamily` (`oref0`, `loop` or `other`) and `metadata.versionRange`, a free-text string (`specs/sync/controller-state-model.schema.json`). It has no algorithm identity, no implementation version, no per-algorithm settings schema and no output contract |
| required inputs | `replayInputs`, each with a status and a path (a null path declares an input the controller has and does not publish) | **close**, per controller, not per algorithm |
| execution instance | an instance: a random id, a `definitionId`, roles, labels, a lease | **the shape fits**; nothing in it names which algorithm the copy is running |
| provenance | per role, closed: `device` or `simulated` | **gap.** A shadow result computed from a real person's live inputs is neither: its inputs are `device` data and its output was never enacted. No provenance or role says "computed, not enacted" |
| authority | roles: `source`, `command-sink`, `{value: other, controllerTerm}`; a `device` command-sink only for the product's bound subject or by the owner's transfer | **routing only.** Roles say who may receive a hub-originated command. They do not say which algorithm's output a controller enacts; that stays inside the controller (D18) |

So D19 registers a controller and the copies of it that connect, and says what data each copy
writes and receives. It does not register the algorithms inside a controller. A controller that
holds several algorithms registers once; which of them produced a decision is not visible to the
hub. The content-addressed id is the part an algorithm registry would reuse unchanged (§4.2).

## 2. What exists publicly

### 2.1 The adapter protocol and its vectors

[ADR-005](../../90-decisions/adr-005-adapter-protocol.md) (accepted 2025-03-30) fixes a
JSON-over-stdio protocol: each implementation runs in its own process behind a thin adapter that
reads `{mode, algorithm, input}`, runs the algorithm and writes a standard output; a
`manifest.json` per adapter declares its capabilities, invocation, modes and tolerances. Contracts
are in `tools/test-harness/contracts/`. **Measured** 2026-10-18 (`ls tools/test-harness/adapters`):
four adapters carry a manifest — oref0 in JavaScript, AndroidAPS in JavaScript, AndroidAPS in
Kotlin, and one Swift oref0 port. There is no Loop adapter, and the
[conformance README](../../../conformance/README.md) lists the Loop runner as not implemented.

**The vectors.** `specs/nsschema/dosing-input-sources.yaml` takes the oref0 input set as the union
of `input.*` paths across "the 385 replay vectors in `conformance/`". **Measured** 2026-10-18 by
loading every JSON file under `conformance/` with an `input` member:

| Directory | Files | Expected output kept from | Notes |
|---|---|---|---|
| `conformance/vectors/` | 85 | AndroidAPS's own result at capture (`originalOutput`), all 85 | AndroidAPS replay fixtures |
| `conformance/loop/vectors/` | 200 | Loop's own devicestatus prediction (`groundTruth.source: loop-devicestatus`), all 200 | Loop data replayed through the oref0 harness; they describe oref0's input shape, not Loop's |
| one adapter's end-to-end oref0 set | 100 | `originalOutput` on 99 | its manifest counts 78 captured from AndroidAPS fixtures, 1 from an OpenAPS example and 22 synthetic; 77 have the same `input` as a file in `conformance/vectors/` |

385 files therefore hold 308 distinct inputs, 22 of them synthetic. The union of input paths, and so
the oref0 completeness figure below, is unaffected by the duplicates. Every non-synthetic expected
output in this corpus comes from the original controller at capture, which is what makes it a
reference (§3.5).

### 2.2 A shadow run on record

The [cross-validation log](../../../traceability/cross-validation-log.md) (A10, 2025-03-30)
records Trio's port of oref0 to Swift and its shadow mode, which logs the JavaScript and Swift
outputs for the same inputs and compares them; its exit criterion for the first phase was "no
inconsistencies on 200k+ inputs". At Trio `e41c9db37` the Swift port is the running algorithm
([intent landscape §1](nightscout-intent-workflow-landscape-2026-10-09.md#1-sources)). That is an
audition inside one project, of one port against its original, with the original's output as the
reference.

### 2.3 Replay completeness is bounded by what was recorded

From `dosing-input-sources.yaml` (last changed `2cad3225`, 2026-09-10), counted 2026-10-18:

| | Declared inputs | Recorded | Derivable | Partial | Absent | Recorded | Recorded or derivable |
|---|---|---|---|---|---|---|---|
| Loop | 20 | 4 | 7 | 1 | 8 | **20%** | 55% |
| oref0 family | 40 | 20 | 9 | 3 | 8 | **50%** | 72% |

Loop's input set is **source-derived**: read from `AlgorithmInput` in LoopAlgorithm, because no
vector set here carries Loop's native inputs. oref0's is **capture-derived**: the union of input
paths across the vectors above. The figures are published in
[hub-sync §4.2](nightscout-hub-sync-architecture-2026-09-11.md#42-completeness-as-a-published-number),
and the change list that would raise them is
[replay-fidelity changes](PROPOSAL-replay-fidelity-changes-2026-09-11.md). A derived input is *a*
value, not necessarily the one the controller used, so a replay on derived inputs tests the
replayer as much as the algorithm.

### 2.4 Inputs come from the controller's records, not from a hub's answer

The two hubs do not always agree on what is active. **Measured** by
[`tools/lab/hub-active-state`](../../../tools/lab/hub-active-state/README.md) on synthetic records
(summarised in [agents in the ecosystem §3.3](agent-trust-boundaries-2026-10-18.md#33-compute-first-then-explain)):
a Loop devicestatus override's `duration` is read as seconds by one hub and minutes by the other;
a temporary target followed by a cancel disagrees on `Active`-state reads; the profile after a
timed switch, AAPS `timeshift` units and out-of-order backfill of two open overrides also
disagree. A harness that asked a hub "which override was active?" would audition each algorithm on
the hub's answer, not on what the controller held. Replay inputs have to be read from the
controller's own records of what it used.

## 3. What an independent implementation shows

*Every fact in this section is read-derived from the source and documents of an independent Swift
implementation of the oref and Loop algorithms, built for a commercial controller, 2026-10-18; not
reproduced here.* It is described by role only. No figure from it other than those below is cited,
because its other parity and error figures are not backed by a run anyone here can repeat.

### 3.1 Several algorithms behind one interface

It registers several algorithms behind one interface: each has a name, a free-text version string,
declared capabilities, a source-family tag, a calculate step and an input check. One is active at
a time; selection is by capability. The version is free text, not tied to content, so two builds
that compute differently can report the same version. That is the gap D19's content-addressed
definitions close for controllers (§1.2), and the one §4.2 would close for algorithms.

### 3.2 A shadow runner

It runs several algorithms on the same inputs, stores each result as never enacted, and reports
how often they agree and diverge. Two limits follow from how it stores a run:

- **A divergence cannot be replayed.** Each stored run keeps glucose, IOB and COB as numbers. It
  keeps no hash and no copy of the full inputs, so a divergence found afterwards cannot be re-run
  on exactly what produced it.
- **IOB and COB are not compared.** Inputs arrive with IOB and COB already computed, so two
  algorithms that compute IOB differently are compared on one shared IOB, not on their own.

### 3.3 Inputs it found Nightscout does not carry

Its replay work found these independently. Compared with `dosing-input-sources.yaml` at `ef29293a`:

| Input it needed | In `dosing-input-sources.yaml`? |
|---|---|
| the nominal temp-basal duration — Nightscout stores the duration after a later temp basal superseded it | **listed without the distinction.** `currentTemp.duration` is `recorded` from `openaps.iob.lastTemp.duration`; Loop's `doses` is `derivable` from treatments' `duration`. Neither entry says whether the stored value is the nominal or the superseded duration |
| pending insulin (requested, not yet confirmed delivered) | **not listed** |
| the pump's own dose log, rather than the uploaded treatments, because of upload gaps and races | **not listed.** Loop's `doses` is `derivable` from treatments; upload gaps and races are not noted |
| the profile's time zone | **not listed.** No entry names a time zone |
| the active temp basal at a decision, which needs the *previous* devicestatus, and its real duration, which needs the *next* | **not listed as a dependency.** `currentTemp` is read from the same devicestatus's `lastTemp` |

Four of the five are therefore new to this repository's input map, and the fifth is listed without
the distinction that decides its value.

### 3.4 One measured comparison, and what it is not

It compared its IOB with the IOB Loop itself reported: mean IOB error +0.51% over 14 samples in one
hour, 3 of 14 within ±1%. This measures **outputs** — one computed value against the controller's
own — and is a different measure from the 20% / 50% figures of §2.3, which measure **input
coverage**. Fourteen samples from one hour of one person's data is not a validation.

### 3.5 Two lessons

- **Parity against code the product never called.** Its parity tests passed against matching code
  that the product did not run; a live comparison against a running controller exposed a 2.30 U/hr
  disagreement in one recommendation. A parity suite needs an end-to-end gate that proves the code
  it tested is the code that runs: the same artefact, reached through the same call path the
  product uses.
- **Expected values from the port are not a reference.** Its exported test vectors carry the
  port's own outputs as the expected values, so they can detect a change in the port but not an
  error in it. A reference must come from the original implementation — a run of JavaScript oref0,
  or the upstream LoopAlgorithm package — or from captured controller output, as the public
  vectors of §2.1 do.

## 4. What an audition harness would need — proposed, not specified

Nothing in this section is specified or decided.

### 4.1 One input snapshot per run, content-hashed

Each run starts from one canonical input snapshot: every input the algorithm reads, in one
document, identified by `sha256:` and the SHA-256 of its RFC 8785 canonical JSON — the rule D19
uses for definition ids and etags. Every result names the snapshot hash, so any divergence can be
re-run on exactly its inputs (§3.2). Two algorithms that compute IOB or COB themselves get the raw
history, not one shared derived value.

### 4.2 The algorithm definition and its settings

Each run names a content-addressed algorithm definition (identity, implementation version,
settings schema, required inputs, output contract; §1.1) and the settings values it ran with,
hashed the same way. A free-text version is kept as a label, never as the identity (§3.1).
Whether such definitions live in D19's store, as a new element or a new resource, is open.

### 4.3 A reference per family

| Family | Reference implementation | How expected outputs are produced |
|---|---|---|
| oref0 | JavaScript `determine-basal` (oref0) | run on the snapshot; or the controller's own output captured at the time (`originalOutput`) |
| Loop | the upstream LoopAlgorithm package | run on the snapshot; or Loop's devicestatus output captured at the time |

A port's own outputs are never the reference (§3.5).

### 4.4 Completeness shown per run

Each run shows, per input in `dosing-input-sources.yaml`, whether it was **recorded**, **derived**
or **absent** in that snapshot, and the result is labelled with it. A run on derived inputs is
reported as such, never merged into a single agreement rate with runs on recorded ones.

### 4.5 Disagreement reports and fault injection

A disagreement report names the snapshot, both definitions and settings, both outputs and the
first intermediate value that differs (ADR-005's comparison granularity: predictions, eventual
glucose, IOB arrays). The harness also runs the same snapshot with faults, as the labs already do
for the hub: missing data; out-of-order arrival, as in the
[hub-active-state](../../../tools/lab/hub-active-state/README.md) backfill cases and the
[connector soak's](../../../tools/lab/connector-soak/disturb.js) backdated records; and duplicates
and re-sends, as in the
[v3-identifier-immutable](../../../tools/lab/v3-identifier-immutable/README.md) lab.

### 4.6 No audition result is promoted to control

The harness has no path to a pump and no way to change which algorithm a controller enacts.
Execution authority is a separate, recorded decision outside it. Under D18 the controller
validates and enacts
([execution plan §2.6.1](../tenancy/nightscout-multitenancy-execution-plan-2026-09-14.md#261-d18--two-tier-controller-registration)),
and a proposed change reaches it only through a lifecycle such as
[agents in the ecosystem §4.3](agent-trust-boundaries-2026-10-18.md#43-what-a-proposal-lifecycle-would-add--proposed-not-specified):
propose, validate, approve against the exact payload, command, outcome. An audition result is
evidence for that decision, never the decision.

**A registry is not enough to swap algorithms.** Changing the algorithm without replacing the
whole app also requires separating the algorithm's semantics from the pump and sensor safety
responsibilities around it: maximum basal and bolus enforcement, suspend handling, delivery
confirmation and the pump's own dose history. Today some of these limits are algorithm inputs
(`profile.maxIob` and `profile.maxBasal` in oref0's set) and the rest sit in each controller's
pump and sensor code; registering algorithms behind one interface (§3.1) moves neither.

## 5. Not measured, not decided

- No audition harness exists here; §4 is a list of requirements.
- No independent-implementation fact in §3 was reproduced; none of its code was run.
- Whether an algorithm definition belongs in D19 (a new element or resource) or elsewhere (§4.2).
- A provenance or role for a computed, never-enacted result (§1.2).
- Whether Nightscout stores nominal or superseded temp-basal durations on each upload path, and
  whether the four unlisted inputs of §3.3 should enter `dosing-input-sources.yaml`.
- A Loop adapter under ADR-005, and Loop's native inputs captured in any vector set.
- Fault-injection cases for algorithms; the labs linked in §4.5 exercise the hub, not an algorithm.
- Who decides that an auditioned algorithm may control a pump, and how that decision is recorded.
