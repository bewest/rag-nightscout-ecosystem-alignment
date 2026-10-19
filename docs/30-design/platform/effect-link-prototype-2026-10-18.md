# Effect link: how a command's outcome names the record that shows its effect

*Contributor-facing. Research note, 2026-10-18. Prototype for the maintainer's decision on
commands CM7: how the outcome report of an enacted command links to the record that shows the
effect. Read after the [commands specification §5](spec/commands.md#5-outcomes-proposed) and the
[partial acceptance prototype](partial-acceptance-prototype-2026-10-18.md), whose shape this note
follows: a small executable model per option, one set of scenarios run against each, the measured
results, and an assessment.* **Snapshot — describes 2026-10-18. Status: proposed.**

**The question.** CM7 says a report on an enacted command carries "the identity of the record
that shows the effect" ([identity](spec/identity.md)). It does not say where that identity lives,
who writes it, or what happens when the record is lost and re-sent, ended by a new record,
changed by a second command, or arrives after the report. The maintainer judged the answer
unclear, asked for prototypes, and noted that the work of building and maintaining the link
may weigh as much as what a person or follower sees.

## 1. What was built

| file | what it is |
|---|---|
| [`tools/nsschema/prototypes/effect_link.py`](../../../tools/nsschema/prototypes/effect_link.py) | one controller and one hub per option, the write step's re-send matching, the 24 scenarios, the measures, and the generator for the tables in §3 and §4 |
| [`tools/nsschema/prototypes/test_effect_link.py`](../../../tools/nsschema/prototypes/test_effect_link.py) | the expected links per scenario and option, four invariants, two weakenings that must be caught, and a check that the tables in this note equal the model's |

The tables between `BEGIN GENERATED` markers are written by `python3 -m
nsschema.prototypes.effect_link --write` (run from `tools/`); `--check` and
`test_note_tables_are_current` fail when they differ from the model.

**What the model holds.** A hub stores records through one write step: a re-send matches on
`identifier`, else on the time and kind among records without one (identity I5 and §3); a
match merges (sync transport T2); a delete is soft. The hub records each command, accepts one
final report (CM9), and the controller keeps CM21's decided ids. Ground truth is kept beside the
model: each step that makes a record says which command caused it, or that it was a local action
on the phone. The link functions read only what the hub stores. Routing, tenants, expiry and
payload hashes are left out: they do not differ between the options. Every record is synthetic;
the kinds stand for the carrier a controller writes.

**The options.**

| | the controller sends | the hub stores and links | prior art |
|---|---|---|---|
| **B0** today, inferred | nothing | nothing; a reader links a succeeded command to the earliest unclaimed record of each kind it asked for, within a window after it was made | what a follower does today when it watches for a record to appear |
| **E1** `effect[]` on the report | the report lists the identity of each record showing the effect, in identity I4's form (`collection`, `identifier`, else `_id`) | the list as reported, unverified, like the reported hash; resolved to stored records when read | Trio `dev`'s reply to a direct sender carries `command_id` and `meal_id`; for an edit, `meal_id` is the new carb entry |
| **E2** `commandId` on the record | each effect record carries the `commandId` | links by the field; keeps a stored value on merge and replace and refuses a different one | the drafted `DeliveryObservation.relatedRequestId`; Loop's override record carries the sender's `remoteAddress` |
| **E3** both | both | the union; a pair one source gives and the other, able to speak, does not, is flagged and never resolved by the hub | — |
| **E4** a reconciliation record | a record of its own kind, one per command (its identifier derived from the `commandId`), naming the effect identities | stores it through the write step like any record, so it can be re-sent and amended after the report is final | the drafted `Reconciliation {requestId, observationId, outcome}` |

The drafts named above are the cgm-remote-monitor `docs/proposals/` files this repository wrote
earlier; the platform specifications are proposed to supersede them.

**Decided for the prototype.**

- E1 lists the effect on any report whose command wrote a record, including `failed`: CM7 as
  written lists it only "when enacted", which would leave the carbs of a part-enacted meal unlinked
  (`meal-part-enacted`).
- E2 has one `commandId` per record. A second command that changes the record (a remote cancel)
  cannot add its own; the controller keeps the first.
- A conforming controller under E1 and E4 keeps each command's effect list with CM21's decided id
  across a restart; `restart-effects-not-kept` shows one that does not.
- The hub does not follow an instance across records (state and intent A2): E1 does not learn that
  a re-posted override is the same instance as the record its report named.

## 2. Scenarios

| scenario | what happens |
|---|---|
| `bolus-one-record` | an enacted bolus, one dose record |
| `override-ended-by-amend` | an override enacted, then ended early by amending its duration (the same record) |
| `override-ended-by-repost` | an override enacted, then ended by delete and re-post, as Trio writes it: a new record for the same instance |
| `override-then-remote-cancel` | an override enacted by one command and ended by a remote cancel; one record shows both effects |
| `carbs-edited-by-command` | carbs entered by one command and edited by another; the edit deletes the entry and makes a new one, as Trio `dev` does |
| `upload-request-lost-resent` | the record's upload is lost, the report goes, the record is re-sent |
| `upload-reply-lost-no-identifier` | a controller that sends no `identifier`; the write reply is lost, so it has no `_id` when it reports |
| `report-before-record` | the report reaches the hub before the record |
| `report-after-record` | the record reaches the hub before the report, and is re-sent after |
| `restart-effects-kept` | the controller restarts between enacting and reporting, and keeps its effect list |
| `restart-effects-not-kept` | the same, with a controller that keeps only CM21's decided ids |
| `refused-then-local-dose` | the command is refused; the person then doses on the phone |
| `local-dose-after-command` | a command is enacted; minutes later the person doses on the phone |
| `local-dose-while-command-in-flight` | a dose on the phone lands between the command and its enactment |
| `meal-part-enacted` | a meal command: carbs stored, bolus refused by the controller's limit; the report says failed |
| `meal-two-records` | one command, two records (carbs and bolus) |
| `effect-amended` | the dose record is amended later |
| `effect-deleted` | the person deletes the dose record later |
| `effect-replaced-by-follower` | a follower's editor replaces the stored record with a body that has no `commandId` |
| `controller-cannot-tag` | a controller whose new command module reports, but whose record uploader cannot carry a new field |
| `two-commands-close` | two commands on one channel a minute apart, enacted in the other order |
| `enacted-twice` | a controller without CM21 enacts a second delivery after a restart; its second report is refused |
| `fault-report-names-local-record` | fault: the report path names a local dose instead of the command's |
| `fault-tag-on-local-record` | fault: the tagging path puts the current `commandId` on a local dose |

An older reader or follower that ignores the link is measured by the last row of §3's totals: what
a reader holding only the stored records can tell.

## 3. Results

`cd tools && python3 -m pytest -q nsschema/prototypes`: **367 passed** (241 in `test_effect_link.py`). Each cell is links correct / wrong / missing against the
ground truth; `fN` is the number of pairs E3 flags. The `links` column is how many
(command, record) links the ground truth holds.

<!-- BEGIN GENERATED: effect-link-results -->
| scenario | links | B0 | E1 | E2 | E3 | E4 |
|---|---:|---|---|---|---|---|
| `bolus-one-record` | 1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `override-ended-by-amend` | 1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `override-ended-by-repost` | 2 | 0/0/2 | 1/0/1 | 2/0/0 | 2/0/0 f1 | 2/0/0 |
| `override-then-remote-cancel` | 2 | 1/0/1 | 2/0/0 | 1/0/1 | 2/0/0 f1 | 2/0/0 |
| `carbs-edited-by-command` | 2 | 1/0/1 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 |
| `upload-request-lost-resent` | 1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `upload-reply-lost-no-identifier` | 1 | 1/0/0 | 0/0/1 | 1/0/0 | 1/0/0 f1 | 1/0/0 |
| `report-before-record` | 1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `report-after-record` | 1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `restart-effects-kept` | 1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `restart-effects-not-kept` | 1 | 1/0/0 | 0/0/1 | 1/0/0 | 1/0/0 f1 | 0/0/1 |
| `refused-then-local-dose` | 0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| `local-dose-after-command` | 1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `local-dose-while-command-in-flight` | 1 | 0/1/1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `meal-part-enacted` | 1 | 0/0/1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `meal-two-records` | 2 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 |
| `effect-amended` | 1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `effect-deleted` | 1 | 0/0/1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `effect-replaced-by-follower` | 1 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 | 1/0/0 |
| `controller-cannot-tag` | 1 | 1/0/0 | 1/0/0 | 0/0/1 | 1/0/0 | 1/0/0 |
| `two-commands-close` | 2 | 0/2/2 | 2/0/0 | 2/0/0 | 2/0/0 | 2/0/0 |
| `enacted-twice` | 2 | 1/0/1 | 1/0/1 | 2/0/0 | 2/0/0 f1 | 1/0/1 |
| `fault-report-names-local-record` | 1 | 1/0/0 | 0/1/1 | 1/0/0 | 1/1/0 f2 | 0/1/1 |
| `fault-tag-on-local-record` | 1 | 1/0/0 | 1/0/0 | 1/1/0 | 1/1/0 f1 | 1/0/0 |
<!-- END GENERATED: effect-link-results -->

**Totals.** "A remote record shown as local" counts records some command caused that carry no
link at all; "a local record shown as remote" counts records from local actions that carry one.
"An effect in flight" counts effect records that had not reached the hub when the report did.

<!-- BEGIN GENERATED: effect-link-totals -->
| measure (over 24 scenarios) | B0 | E1 | E2 | E3 | E4 |
|---|---:|---:|---:|---:|---:|
| links correct | 19 | 24 | 27 | 29 | 26 |
| links wrong | 3 | 1 | 1 | 2 | 1 |
| links missing | 10 | 5 | 2 | 0 | 3 |
| pairs flagged | 0 | 0 | 0 | 8 | 0 |
| flagged pairs that are wrong links | 0 | 0 | 0 | 2 | 0 |
| a local record shown as remote | 1 | 1 | 1 | 2 | 1 |
| a remote record shown as local | 7 | 5 | 1 | 0 | 3 |
| a command with more live records than it asked for | 0 | 0 | 2 | 3 | 0 |
| an effect in flight known to the hub | 0 | 2 | 0 | 2 | 2 |
| an effect in flight not known to the hub | 2 | 0 | 2 | 0 | 0 |
| scenarios with a remote record where the stored records alone show which were remote | 0 | 0 | 21 | 21 | 0 |
<!-- END GENERATED: effect-link-totals -->

**What an auditor or follower can answer.**

| question | B0 | E1 | E2 | E3 | E4 |
|---|---|---|---|---|---|
| did this command cause this dose? | a guess by time and kind; wrong when a local dose or a second command lands in the window | yes, from the command record | yes, from the dose record | yes, with disagreements flagged | yes, from the reconciliation record |
| which doses did this command cause? | a guess | yes; also before the records arrive | yes, once the records arrive | yes | yes; also before the records arrive |
| was this dose remote? | a guess | yes, through an index from effect identity to command | yes, from the dose record alone | yes | yes, through an index |
| the same, from an export, a second hub, or a reader without access to commands | no | no | yes | yes | no |
| was one command enacted twice? | no | no: the second record looks local | yes: the command has more records than it asked for | yes | no: the second write replaces the first list |

## 4. Cost

<!-- BEGIN GENERATED: effect-link-costs -->
| | E1 | E2 | E3 | E4 |
|---|---:|---:|---:|---:|
| schemas or carriers touched | 1 | 13 | 14 | 1 |
| hub fields and indexes | 2 | 2 | 4 | 2 |
| new invariants | 1 | 3 | 5 | 3 |
| controller must keep or write | 2 | 2 | 4 | 2 |
| conformance cases | 7 | 18 | 27 | 8 |
<!-- END GENERATED: effect-link-costs -->

Counted from lists in `effect_link.COSTS`; each item is named there.

- **E1** adds one member to one message, the outcome report. Nothing changes in any record kind,
  so adding a command kind later adds nothing here. The hub stores the list and keeps an index
  from identity to command for "was this dose remote?". The controller keeps each command's effect
  identities with CM21's decided id until its report is accepted, and needs an `identifier` on each
  effect record, or the `_id` from the write reply. Seven cases.
- **E2** touches every carrier a command can reach: 12 carriers across `treatments`, `profile` and
  `settings` as commands §3 and §8 read them (bolus, carbs, Loop's and Trio's overrides, temporary
  targets, profile switch, running mode, temp basal, extended bolus, therapy events, AndroidAPS
  scenes, Loop's loop mode), plus a well-known field. Each needs the field in its schema, in each
  controller's uploader for that kind, in the projection to typed records, and a case. The hub gains
  three invariants, one of which (kept on replace, refused when changed) is a new exception to T2's
  merge and to API v1 and v3 `PUT`. Every app that round-trips a record (an editor, a downloader
  that re-uploads) must keep the field or rely on that exception. Eighteen cases.
- **E3** is E1 and E2 together, plus the flag rule. Twenty-seven cases.
- **E4** adds one record kind, an authorisation check on a record write (only the destination's
  subject, as CM7 checks a report), and a second place where an outcome is stated beside the
  command's state. Eight cases.

**With older apps** ([compatibility](spec/compatibility.md), verdicts in §2 there). Every
controller's L3 command row is `opt-in` today: no released controller reports to a hub. Under
E1 and E4, nothing a non-participating app sends or reads changes. Under E2 an older reader
ignores the field, but an older editor or a client that rebuilds a record from its own model sends
a body without it: on merge it survives (T2), on `PUT` only by E2's new rule. A record copied to
another hub carries a `commandId` that names no command there, which a reader on that hub must
not take as remote without the command. Under every option an older follower sees what it sees
today: the records, unlinked.

## 5. Weakenings

Each applied to the model, run, and restored.

| | weakening | red |
|---|---|---|
| W1 | E2's controller puts the last enacted `commandId` on every record it writes, including local actions (`RULES["tagOnlyEnacted"] = False`) | 11, among them `test_links[local-dose-after-command-E2]` (1/1/0 for 1/0/0), the same for E3, `test_a_local_action_is_never_linked` for E2 and E3, `test_no_option_links_wrongly_without_a_fault`, `test_without_a_fault` and `test_note_tables_are_current` |
| W2 | E2's hub drops a stored `commandId` on replace (`RULES["keepTag"] = False`) | 4: `test_links[effect-replaced-by-follower-E2]` (0/0/1 for 1/0/0) and its E3 row, `test_without_a_fault` and `test_note_tables_are_current` |

After each restore: 367 passed.

W1 is the safety case the brief named: a dose given on the phone shown as remote. Under E1 the
same controller fault cannot occur, because a local action has no report; its counterpart is a
report path that names the wrong record (`fault-report-names-local-record`), which E1 and E4
also show as a wrong link. Only E3 flags both faults. `test_weakened_tagging_links_a_local_action`
and `test_weakened_keep_tag_loses_the_link_on_replace` keep both weakenings in the suite.

## 6. Safety

Tied to the [control-loop analysis](spec/control-loops.md) where an entry exists.

- **A local dose shown as remote, or a remote dose shown as local** (HAZ-3). With no link (B0),
  a reader infers one, and the model shows it wrong when a local dose lands in the window or two
  commands are enacted in the other order: three wrong links, seven remote records shown as local.
  Without a controller fault, no option links wrongly, and remote records shown as local fall to
  4 (E1), 1 (E2), 0 (E3) and 2 (E4). A wrong link then comes only from a controller fault in the
  path the option uses; E3 alone flags it.
- **A second enactment hidden** (UCA-CMD-006, prevented by CM18 and CM21 at the controller).
  If CM21 fails, under E1 and E4 the second dose record has no link and looks like a local dose;
  under E2 and E3 it carries the command's id, and the command has more live records than it asked
  for, which a hub can show. This is the case where the record-side tag adds most.
- **An effect not yet at the hub** (UCA-SYNC-SERVE-004: a caregiver sends another dose because the
  first has not reached the hub). Under E1, E3 and E4 the report names the effect before its record
  arrives, so the hub can show "enacted, record not yet received" on the command and in CM24's
  outstanding list; under B0 and E2 it cannot know.
- **A part-enacted command** (UCA-CMD-011). With the effect listed on a `failed` report, a reader
  sees that the meal's carbs were stored although the command failed. CM7 as written would not
  list it.
- **A report or tag from another process** (FB-CMD-002, UCA-CMD-014). E1 inherits CM7's subject
  check. E2's tag arrives on an ordinary record write, so a process that may write treatments may
  make any dose look remote unless the hub checks that the writing instance was the command's
  destination; under `single` every holder of `API_SECRET` is one subject, so that check sees
  only the instance the writer claims. E4 needs the same check on a record write.
- **The effect record changed later** (UCA-SYNC-DL-003, UCA-SYNC-STORE-003). Amendment and
  deletion keep every option's link, because the link names the record's identity. An end written
  as delete and re-post loses E1's link to the new record unless the hub follows the instance (A2).

## 7. Assessment

| | E1 | E2 | E3 | E4 |
|---|---|---|---|---|
| links missing without a fault | 4 | 2 | 0 | 2 |
| where they come from | no `identifier` before the write reply; a restart that drops the effect list; a re-post; a second enactment | an uploader that cannot carry the field; a second command on the same record (a cancel) | — | a restart that drops the effect list; a second enactment |
| a record shows two commands' effects | yes | no: one field per record | yes, flagged | yes |
| changes per new command kind | none | one carrier, its uploader, its projection and a case | as E2 | none |
| where the change lands in a controller | its command module | its command module and every uploader of an effect kind | both | its command module and one new record kind |
| reported after final | no (CM9) | the record can change | as E1 and E2 | yes, which overlaps commands §9 item 4 |

E3 flags 8 pairs; 2 are wrong links, one from each controller fault, and 6 are correct links that
one source did not give (a cancel on a tagged record, a re-post, a missing `identifier`, a
restart, a second enactment, and the real dose that the faulty report left out). A reader shown a flag cannot tell the two apart without the scenario.

Three of E1's four misses have a rule that closes them. Identity's `ID-ABSENT-DECISION` makes
`identifier` mandatory for registered controller instances, and every command destination is
one, so `upload-reply-lost-no-identifier` cannot occur for a conforming controller. A rule that
the controller keeps effect identities with CM21's decided ids closes `restart-effects-not-kept`
and is one more thing CM21 already makes it keep. Resolving an effect identity to the instance it
belongs to (A2) closes the re-post. The fourth, a second enactment, is CM21's failure, and only a
tag on the record shows it.

## 8. Recommendation

**A recommendation for the maintainer to decide: E1, with CM7 widened, and a record-side
`commandId` left as an optional attribution a controller may declare later, which would make E3's
flags available where it is present.**

- **Why.** E1 links every scenario without a fault except the four in §7, three of which have a
  rule that closes them. It is the cheapest to build and to keep: one member on one message, no
  record kind touched, seven cases, and nothing to add when a command kind is added. The change
  lands in the controller's command module, which is the code that must be written anyway to
  report; no uploader changes. It is the only option besides E4 in which the hub knows of an
  effect before the record arrives, which serves UCA-SYNC-SERVE-004, and the only cheap one in
  which a record can show two commands' effects (an override and its cancel). It follows the one
  path read today that names its effect record, Trio `dev`'s reply.
- **The strongest argument against.** The link lives only in the hub's command record. A record
  alone does not say it was remote, so an export, a second hub or a reader without command access
  cannot tell (in none of the 23 scenarios with a remote record, against 21 under E2), and if CM21 fails a second enactment of one
  command looks like a local dose, the case UCA-CMD-006 names. E2 shows both. Against that, E2
  touches 12 carriers and every uploader, cannot record two commands on one record, and needs an
  exception to merge and `PUT`.
- **What would change it.** Toward E2 or E3: a requirement that the remote origin of a dose
  survive export or travel between hubs, or evidence that controllers will fail CM21. Toward E4:
  a decision on commands §9 item 4 that outcomes change after a final state; then the
  reconciliation record is a place for both.

## 9. What the specification would say under each option

- **E1.** CM7: the report carries `effect`, a list of `{collection, identifier}` or
  `{collection, _id}` (identity I4), on any state whose command wrote a record, including
  `failed` and `refused` when part was enacted; the hub stores it as reported and resolves it when
  read; an identity that resolves to nothing is shown as not yet received. CM21: the controller keeps
  each command's effect identities with its decided id until its report is accepted. Identity: an
  effect record from a registered instance carries `identifier` (`ID-ABSENT-DECISION`). Read: a
  command shows its effect records; a record shows the commands that name it.
- **E2.** Records: a well-known `commandId` field on each carrier a command can reach. Identity
  or sync transport: a stored `commandId` is kept on merge and on replace, and a write with a
  different value is refused. Commands: a `commandId` is accepted only from the destination's
  instance; a record from a local action carries none.
- **E3.** Both, and: the hub flags a link one source gives and the other does not, when the other
  could have given it, and never decides between them.
- **E4.** A reconciliation record kind with `commandId`, `effect` and `outcome`, its identifier
  derived from the `commandId`; written only by the destination's subject; re-sent and amended
  through the write step; shown beside the command's state, with a difference flagged.

## 10. What the prototype does not model

Several instances or tenants, and the hub's check that a tag or report came from the destination
instance. The hub following an instance across records (A2). Typed records and their projections
to carriers (registration §13), where E2's field would also need a typed declaration. The late
delivery failure after success (commands §9 item 4), beyond E4's ability to amend.
