# Partial acceptance: binding an approval that accepts part of a plan

*What this is: a prototype and assessment (contributor-facing). Read after the
[command queue and planning note](command-queue-and-planning-2026-10-18.md) (§3, and §5 decision 4)
and the [command journeys](command-journeys-2026-10-18.md) (PL1.3, PL5.3 and "Specification
needs"); it compares three ways a hub could bind an approval that accepts some elements of a
proposed plan, runs them against the same hand-authored cases, and recommends one for the
[commands specification](spec/commands.md).* **Snapshot — describes 2026-10-18. Status: proposed.**

**The question.** The maintainer decided on 2026-10-18 that an adjustment is a new proposal, but
that a plan may be accepted in parts, with the approval naming what it accepted. CM13 today binds
an approval to the hash of the whole proposal and makes one command whose payload is the
proposal's, byte for byte, and CM10 has the controller recompute that one hash. The journeys
listed "partial acceptance: the approval names elements; a hash rule for the accepted subset" as a
specification need. The maintainer asked whether this could be prototyped and assessed for what
serves the ecosystem better.

## 1. What was built

| file | what it is |
|---|---|
| [`tools/nsschema/prototypes/partial_acceptance.py`](../../../tools/nsschema/prototypes/partial_acceptance.py) | the three variants as small decision functions (hub approval, command binding, controller check) and one scenario runner: propose, approve with an acceptance, deliver with optional tampering in transit, controller check, enact |
| [`tools/nsschema/prototypes/test_partial_acceptance.py`](../../../tools/nsschema/prototypes/test_partial_acceptance.py) | runs every case against every variant, two invariants, and a generated sweep |
| [`specs/sync/prototypes/partial-acceptance/`](../../../specs/sync/prototypes/partial-acceptance/) | 11 cases, each with expectations per variant written from the rules before the code was run |

**The plan payload.** `{"frame": {...}, "elements": [{"id", "content"}, ...]}`. The frame holds
what every element shares (days, end date, confirmation rule); each element is one separately
acceptable part. The cases use the PL1 plan: an `eating-soon` temporary-target element and a
`meal` element. The numbers in the cases are placeholders. All hashes are CM1's: SHA-256 over the
RFC 8785 canonical JSON (`negotiate.canonical_json`).

**The variants.**

| | the proposal carries | the approval sends | the hub checks | the command carries | the controller checks |
|---|---|---|---|---|---|
| **V1** hash per element | the whole hash, a frame hash and a hash per element | the frame hash and each accepted element's id and hash | each id exists, each hash equals the proposal's | the frame and the accepted elements, a frame hash and a hash per element | the frame hash; no element twice; no element without a hash; no hashed element missing; each element's hash |
| **V2** hash of the accepted subset | the whole hash | the accepted subset (frame and elements) | each id exists, each element's canonical content equals the proposal's | the frame and the accepted elements in the proposal's order, and one hash over them | one hash, as CM10 |
| **V3** no partial | the whole hash | the whole hash (CM13 as written) | a strict subset is refused `partial-not-supported`; the hash equals the proposal's | the proposal's payload and hash | one hash, as CM10 |

Shared by all three: an approval closes its proposal (CM13: only `open` changes), records the
accepted and declined element ids, and makes one command; the proposer cannot approve its own
proposal (CM14); the controller decides each `commandId` once (CM21). Routing, tenants, expiry and
`basedOn` are left out: they do not differ between the variants.

**Decided for the prototype: accepting the rest later.** In V1 and V2 a person who accepted part
of a plan and later wants the rest cannot approve the same proposal again; it is `approved` and
refused `proposal-closed`. The rest comes back as a new proposal, which is decision 4's rule for
adjustments, and keeps one proposal to one approval to one command. The person cannot approve a
proposal they made (CM14), so the proposer, or another party, proposes it again.

## 2. Cases

Each case runs against every variant; `only:` on a step limits it to the variants that need it
(V3's reject and new proposal).

| case | scenario | V1 | V2 | V3 |
|---|---|---|---|---|
| `accept-all` | both elements accepted; the command delivered twice | enacts both; second delivery `ignored` | same | same |
| `accept-one` | PL1.3: eating-soon accepted, meal declined | one command with eating-soon; meal recorded declined | same | `partial-not-supported`; reject, new proposal, approve, enact |
| `accept-unknown-element` | an id the plan lacks; nothing accepted; a plan with an id twice | `unknown-element`; `nothing-accepted`; `duplicate-element` | same | `hash-mismatch`; `partial-not-supported`; `duplicate-element` |
| `accept-altered-content` | the approver's display holds a larger meal, then a later end date | `hash-mismatch` twice | same | same |
| `transit-altered-element` | an element changed between hub and controller, whole and part | refused `hash-mismatch` | same | same (whole only) |
| `transit-dropped-or-duplicated` | an accepted element dropped; an element sent twice | `missing-element`; `duplicate-element` | `hash-mismatch` twice | same as V2 |
| `reordered-keys` | the display and the delivery hold every key in another order; then the accepted elements listed in reverse | approves and enacts; reverse order approved | same | approves and enacts; reverse order refused `hash-mismatch` |
| `declined-added-in-transit` | the declined meal added to the command in transit | refused `unbound-element` | refused `hash-mismatch` | same as V2 (after a new proposal) |
| `declined-built-in-by-hub` | a faulty hub builds the command from the whole proposal and binds it to what it built | **enacts the declined meal** | **enacts the declined meal** | the fault has no subset to get wrong; enacts eating-soon |
| `concurrent-approvals` | the person and a caregiver approve different parts in turn | first makes one command; second `proposal-closed` | same | same, both accepting the whole |
| `accept-rest-later` | eating-soon accepted, the meal wanted a week later | second approval `proposal-closed`; new proposal for the meal | same | reject, new proposal, then a third proposal for the meal |

**Invariants**, checked on every case and on a generated sweep (every acceptance of the two
elements, from none to both, against nine tamperings and none, in each variant):

1. the controller never enacts an element that no approval named;
2. every enacted element's content hash equals the hash its approval named.

The faulty-hub case is excluded from the invariant run and has its own tests: in V1 and V2 it
breaks invariant 1 with exactly `("unnamed", "c1", "meal")`, and in V3 it breaks neither.

## 3. Results

`cd tools && python3 -m pytest -q nsschema/prototypes`: **126 passed** (0.28 s). 11 cases × 3
variants for steps and for final state (66), invariants on 10 cases × 3 variants (30), 3 faulty-hub
tests, the sweep in 3 variants, and 24 structural and non-vacuity checks. Every hand-authored
expectation held on the first run.

**Weakenings**, each applied to `partial_acceptance.py`, run, and restored from a copy (126 passed
after the last restore):

| | weakening | red |
|---|---|---|
| W1 | V1 controller: no `unbound-element` check | 4: `declined-added-in-transit` V1 steps, final state and invariants; the V1 sweep |
| W2 | V2 hub: no comparison of element content | 2: `accept-altered-content` V2 steps and final state |
| W3 | an approval leaves its proposal `open` | 35: the final state of every case with an accepted approval, and the steps of `concurrent-approvals` and `accept-rest-later` |
| W4 | the hash over raw JSON instead of canonical JSON | 11: `reordered-keys` in all three variants (steps, final state, invariants) and the sweep in all three |
| W5 | no CM21 check at the controller | 3: `accept-all` steps in all three variants |
| W6 | V1 hub: no per-element hash check | 2: `accept-altered-content` V1 steps and final state |

W2 and W6 turn red only through the case expectations: nothing reaches the controller in that case,
so the invariants have nothing to check. They would catch it on delivery, because the approval's
named hash and the enacted content's hash would differ.

**A composition, run once.** V1's approval form and hub check with V2's command binding and
controller check (the recommendation in §5) reproduced V2's expectations on all 11 cases. It was
run as a one-off script, not as a fourth variant in the test file.

## 4. Assessment

| | V1 hash per element | V2 hash of the accepted subset | V3 no partial |
|---|---|---|---|
| **tamper in transit** | detected: altered, added, dropped and duplicated elements, and an altered frame; the refusal names which check failed | detected, all as `hash-mismatch` | detected, as `hash-mismatch` |
| **a hub that builds the wrong subset** | not detected: the controller gets the payload and the hashes from the same hub (CM10's limit) | not detected, for the same reason | nothing to build: the command is the proposal |
| **what the approver sees and sends** | the elements; the client computes and sends a frame hash and one hash per accepted element | the elements; the client sends the accepted content back, and the hub compares | the whole plan; to decline part, the approver rejects and waits for a new proposal |
| **controller burden** | a frame hash, a hash per element and five checks (13 lines in the prototype); the controller must know the element grammar | one hash over the payload (1 line), CM10 unchanged; a smaller plan is an ordinary payload | one hash, CM10 unchanged |
| **hub complexity** | 18 lines, 5 checks; per-element hashes stored on the proposal | 20 lines, 5 checks | 6 lines, 2 checks |
| **audit record** | accepted ids with their hashes, comparable one by one with the proposal's; declined ids | accepted and declined ids and one subset hash; per-element hashes are recomputed from the stored subset | a rejected proposal and an unrelated new one; the link between them is not recorded |
| **PL1 (lunch plan)** | PL1.3 in one step; PL1.2's required reviews stay on the one proposal | same | PL1.3 needs the agent to propose again, and the required reviews again |
| **PL3 (a week of overrides)** | the second parent can decline one day of five | same | a new proposal of four days; PL3.3's adjustment is a new proposal in all three |
| **PL5 (clinician, at the visit)** | one setting accepted at the visit; reviews attached weeks earlier still apply | same | the clinician proposes again during the visit, and the earlier reviews are on the old proposal |
| **CM21** | one command per approval, so one `commandId` per accepted set; accepting the rest later is a new proposal and a new `commandId` | same | one command per proposal |
| **the mirror** | the controller can report a hash per held element, and the mirror can show each element as held as approved | the mirror compares one hash for the held plan | same as V2 |
| **conflict with decision 4** | none | none | it does not allow partial acceptance |

**No controller computes a payload hash today** ([commands §8](spec/commands.md#8-compatibility)):
each checks its own sender authentication. Any variant adds hashing to every controller that takes
plans. V2 and V3 add exactly what CM10 already asks; V1 adds per-element hashing and five checks,
and ties the controller's check to the plan's element grammar.

**Unsafe control actions.**

| UCA | V1 | V2 | V3 |
|---|---|---|---|
| UCA-PROP-003: an approval creates a command whose payload differs from the one approved | a new path: the hub builds a subset. The approval-to-command check (invariant 1 at the hub) covers a correct hub; a faulty one is not detected at the controller (`declined-built-in-by-hub`) | same as V1 | unchanged: CM13's byte-for-byte rule |
| UCA-PROP-004: an approver misreads a payload's meaning | not addressed by any binding. Partial acceptance makes each element a unit the approver reads and decides on, so the element's kind needs a declared shape for a display to render | same | unchanged |
| UCA-CMD-007: the payload a controller receives differs from the one sent | covered, with a reason per check | covered | covered |

**What the prototype does not model.** Elements that depend on each other: declining an
eating-soon target can change whether a meal element is still what the person wants, and a plan
may need to say which elements can be accepted alone. Approver signatures, which are what would
close the faulty-hub gap in V1 and V2. Whether a later proposal for the declined part joins the
held plan or runs as a second plan (plan supersession, open in the journeys).

## 5. Recommendation

**Bind the command to the hash of the accepted subset (V2), and have the approval name each
accepted element by id and hash (V1's approval form).** The hub checks the named hashes against
the proposal's per-element hashes, records accepted and declined ids with their hashes, builds the
command from the accepted elements in the proposal's order, and binds it to one hash. The
controller recomputes one hash, as CM10 already asks, and sees an ordinary plan with fewer
elements. This composition reproduced V2's expectations on all 11 cases.

**Why.** Partial acceptance serves PL1.3 and PL5.3 in one step and keeps required reviews on the
proposal the reviewers read, which V3 cannot. Between V1 and V2, the controller is the expensive
side: none computes a hash today, and V2 asks it for one hash where V1 asks for one per element
plus four structural checks tied to the plan grammar. V1's approval form gives a small approval
message and an audit record that compares element by element, at no cost to the controller.

**The tradeoff.** The controller's refusal says `hash-mismatch` without naming the element, and
the hub gains a subset-building step that the controller cannot check (UCA-PROP-003's new path).
That step needs its own conformance cases and the invariant "a command made by an approval carries
exactly the elements it named" at the hub.

**What would change it.**

- **Toward V1's binding:** controllers that enact a held plan element by element and refuse one
  element while keeping the rest; then a per-element hash is the unit the controller needs.
- **Toward V3:** element dependencies that make most partial acceptances unsafe, or plans not
  reaching any controller for some time, in which case CM13 as written costs nothing now.
- **Toward an approver signature in any variant:** a hub not trusted to build the subset, which
  CM10 already names as the limit of a hash carried by the same hub.

## 6. For the specification

If adopted, CM13 gains: an approval of a plan names each accepted element's id and hash and the
frame's hash; ids must exist and be distinct, and at least one is accepted (422
`nothing-accepted`, 422 `duplicate-element`, 409 `unknown-element`, 409 `hash-mismatch`); the
command's payload is the frame and the accepted elements in the proposal's order, with its own
`payloadHash`; the proposal records accepted and declined ids; a later approval is refused
`proposal-closed`. The cases under `specs/sync/prototypes/partial-acceptance/` would move to
`specs/sync/conformance/commands/` in that format once the plan object (commands §9 item 3) is
specified.
