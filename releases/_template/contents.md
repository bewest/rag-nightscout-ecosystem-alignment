# <product> <version> — contents

<!--
  TEMPLATE. Copy the directory, rename it, delete each comment as you fill it in.

  AUDIENCE: maintainers and reviewers. Full technical depth, terse is fine.
  The one discipline this file enforces is PROVENANCE: every figure says how it
  was obtained. See "Provenance" below — it is not optional and it is the
  difference between this file and a guess.
-->

**Status: DRAFT. Nothing merged, tagged, pushed or published.**

## Identity

| | |
|---|---|
| Product | `<cgm-remote-monitor \| nightscout-connect>` |
| Directory name (the *planned* number) | `<dir>` |
| Tag to be cut | `<v15.1.0 \| v0.0.15>` <!-- keep the repo's own prefix convention --> |
| Base | `<ref>` at `<sha>` |
| Previous release | `<tag>` at `<sha>` |
| Repository | `<path under externals/>` |

<!-- If the directory name and the policy's number disagree, STATE THE
     DISAGREEMENT HERE, at the top, rather than hiding it. Both 15.0.9 and
     v0.0.14 do. The directory name is the planned number, not a decision. -->

## Provenance — read before trusting any figure below

**Every claim in this file is labelled `reproduced` or `read-derived`.**

- **`reproduced`** — something was executed and the output observed. Say what was
  run, against which SHA, and what it printed.
- **`read-derived`** — obtained by reading source. Legitimate, and weaker. Measured
  across this programme: **every claim that had to be retracted was read-derived; not
  one that began with a reproduction has been.**

Never present a reading as a run. A figure with no label is treated as unlabelled,
not as reproduced.

**State explicitly what was NOT done**, in particular: no vendor account exists on
this machine, no live run against any vendor was made, and no live migration is
claimed. An omission here reads as a claim.

## What is in the release

| Branch / area | SHA | Register entries | Summary |
|---|---|---|---|
| `<branch>` | `<sha>` | BF-nn, BF-nn | <one line> |

<!-- Then, per branch: what it changes, how it was tested, and what the test
     actually covers. Name the suite that was RUN, not the suite that exists.
     "N passing / 0 failing" needs the command and the worktree beside it. -->

## Merge state

<!-- Reproduced, not assumed. For each branch, against the base and against the
     others. Record the command. Branches drift; date this measurement. -->

## Operator-visible behaviour changes, with their evidence

<!-- One subsection per item on the tag message's numbered list. Same numbering,
     so the three files can be diffed against each other.

     Each carries: the mechanism, the file and line, the before/after, the
     provenance label, and — where a request or a stored value changes — a table
     of concrete inputs with the old and new results. A reviewer must be able to
     check the claim without re-deriving it.

     Where the change is a RESTRICTION, name a real client that sends the old
     form or say plainly that none can exist. Policy section 2. -->

## Remediation facts

<!-- What a code change does NOT accomplish. Security fixes especially: state
     whether existing artefacts (tokens, stored values, already-written records)
     are affected, quote the code that makes the answer what it is, and list the
     operator's levers by name.

     The 15.0.9 draft's BF-17 section is the model: the token is a deterministic
     function of three inputs, so a code change cannot move it, so rotation is
     the operator's action and there are exactly three ways to do it. -->

## Register entries

| Entry | State | Delivered by | Provenance |
|---|---|---|---|
| BF-nn | fixed / open / partial | `<branch>` | reproduced / read-derived |

<!-- Where an entry is INCOMPLETE or WRONG in a way that matters for the notes,
     say so here as a proposed correction. DO NOT allocate a BF- id: the register
     grows hourly across sessions and ids are allocated centrally. Describe the
     defect and let the register owner number it. -->

## Semver impact

<!-- Paste the reviewer checklist from
     docs/30-design/modernization/semver-and-release-versioning-policy-2026-09-15.md section 6.2
     and ANSWER IT. Every "no" needs evidence; every "yes" needs a line in
     release-notes.md. Note the known weakness recorded in section 6.1: the gate
     accepts any string not beginning "yes", so `unknown` passes. The gate does
     not do this thinking for you. -->

Surfaces touched:
[ ] S1 HTTP API v1/v3 or the realtime socket contract
[ ] S2 plugin interface, boot sequence, or client bundle
[ ] S3 environment-variable configuration surface
[ ] S4 stored document shape or database schema
[ ] S5 Node or MongoDB runtime floor
[ ] S6 an ingestion path (bridge, mmconnect, connect, uploader, API write)
[ ] S7 the set of alarms or notifications that can be emitted
[ ] S8 the version string itself
[ ] S9 (candidate) what the client computes and shows a person
[ ] none of the above

**Classification under the policy:** <PATCH / MINOR / MAJOR>, because <the row that
decides it>. **Directory name says:** `<n>`. **Settled?** <yes / no, and by whom>.

## Deprecation obligations

<!-- Only if this release deprecates or removes something. Policy section 5.
     A deprecation release is a MINOR and must ship the ESCAPE ROUTE, not just
     the warning. Record:
       - the exact setting or endpoint, spelled as the operator spells it;
       - the replacement, with a worked example;
       - the version that will remove it, NAMED - not "a future release";
       - what happens if the operator does nothing, stated concretely;
       - where to ask for help;
       - the two channels the announcement reaches (boot log AND in-app banner;
         a log line alone is not a deprecation notice for a household).
     Minimum windows: 1 release + 90 days generally; 2 releases + 180 days for
     anything that can stop data arriving. Announced removal versions may slip
     later, never earlier. -->

## Sequencing

<!-- What must happen before this tag is cut, in order, with the reason each
     step blocks the next. Include anything in the OTHER repository: a
     cgm-remote-monitor pin cannot be regenerated until the connector tarball
     exists, which means the connector tag must be pushed first. -->

## Non-vacuity (house rule 2)

<!-- For every check cited as evidence: was it observed to FAIL when the property
     is false? A check that has never failed is not yet evidence.

     If an ablation came back green, say which it was: a vacuous check, or a
     break that did not break anything (a MIS-SCOPED ablation). Those are
     different findings and only one of them is a defect in the check. -->

## What a reviewer must verify before this is relied on

<!-- A numbered list of the specific things a qualified reviewer must check.
     Be specific enough to act on. Include every read-derived claim that carries
     weight, every figure whose method has a known limit, and every question
     that cannot be settled without a real vendor account or a live deployment.

     Separate "not yet checked" from "cannot be checked here". The second is a
     standing limit of this machine and will not close by trying harder. -->

---

*Draft, <date>. Prepared locally; nothing pushed, tagged, merged or published.
Requires maintainer review before anything here is relied upon.*
