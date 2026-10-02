# Enough quality management across the Nightscout ecosystem — proposal

*For the maintainers of the ecosystem projects, the Nightscout Foundation board, the companies that
host or build on Nightscout, and the community. **Recommendation** (part 3 of the overview;
[how the overview is organised](README.md)). **DRAFT PROPOSAL for discussion, requiring review by
the maintainers and by a quality-management professional before it is adopted.** Where it touches
vendor terms of use, device regulation or funding agreements, it also needs review by the
foundation's counsel (§10). Written 2026-09-30 against this repository at `df5e2ade` and the
[stack census record](../60-research/programme/stack-census-2026-09-30.md) of the same day. Borrowing
a practice from a quality standard is not a claim of conformity with it. Nothing here is decided.*

*Author's interests: the author maintains cgm-remote-monitor, founded a company that hosts
Nightscout commercially, and could be a candidate for paid work under the
[sponsored-team proposal](SPONSORED-TEAM-PROPOSAL.md). The rules in
[COLLABORATION-MODEL](COLLABORATION-MODEL.md) §5 would apply to that company and to the author like
anyone else.*

## 1. The request

Adopt a small quality system shared across the whole ecosystem stack: from the radio link to a
sensor or pump, through the controllers, connectors and servers, to the tools a person uses to see
and move their own data. Size it the way SQLite sized its own, by keeping only the practices that
"genuinely improve quality" ([qmplan](https://sqlite.org/qmplan.html)). Build it in stages, each
useful alone (§5). And agree the requirements for success in public, with a method that records
every objection and answers it (§8).

This page proposes what the system contains and how the requirements would be agreed. The
[ecosystem programme](ECOSYSTEM-PROGRAMME.md) says where it sits; the
[collaboration rules](COLLABORATION-MODEL.md) say how organisations work together on it; the
[sponsored-team proposal](SPONSORED-TEAM-PROPOSAL.md) says who could do the work that nobody is
paid for today.

## 2. Why the whole stack

The census of 2026-09-30 ([record](../60-research/programme/stack-census-2026-09-30.md); summarised
with the other observations in [evidence §1](observations/ECOSYSTEM-EVIDENCE.md#1-what-the-ecosystem-consists-of)) measured 62
repositories (63 listed; a fork kept level with its upstream counts once), 56 of them active in the last year, with 219 human authors between them:

- **The same work is done many times, separately.** 14 device protocols have 41 independent
  implementations, and for 10 of them no two implementations test against the same bytes. Six code
  bases log in to Dexcom Share and five to LibreLinkUp, and each meets a vendor change on its own
  schedule.
- **Evidence exists but is not kept as evidence.** There are more than 35,000 test declarations
  across the stack, and simulators as good as faketandem. But only 14 repositories run their tests in
  CI, and no device or connector repository publishes a per-release test report.
- **Some checks exist nowhere.** No fuzzing harnesses, no automated hardware-in-the-loop rigs, no
  shared fixtures for vendor clouds, no scheduled check that notices a vendor change before users do.

The ecosystem's purpose depends on every layer. People use these tools to keep their data portable
and computable for their own benefit, and to hand that job to helpers and tools they choose. That
holds only if the driver reads the sensor correctly, the connector still works after the vendor
changed its login, and the server stores what the app sent. A quality system for one layer leaves
the others unexamined.

## 3. What "enough" means: SQLite's plan, element by element

SQLite built its [quality management plan](https://sqlite.org/qmplan.html) by "going through the
description of outputs in section 11 of DO-178B" (the avionics software standard) "and writing down
those elements that seemed relevant". It keeps 100% MC/DC coverage for the core library because it
is so widely deployed, and says full coverage is "probably not cost effective for a typical
application" ([testing](https://sqlite.org/testing.html)). The transferable part is the method: take
each element, keep it only where it pays. Sources for every SQLite row:
[histories annex §A](../60-research/programme/stack-census-2026-09-30/histories.md#a-sqlites-quality-management-elements).

| element | SQLite | here today | proposed for the ecosystem |
|---|---|---|---|
| A plan short enough to read | its test: "a competent developer can be assimilated into the development team quickly" | [DOCUMENT-CONTROL](DOCUMENT-CONTROL.md), [DEFINITION-OF-DONE](DEFINITION-OF-DONE.md), [REVIEWER-ONBOARDING](REVIEWER-ONBOARDING.md), for this repository only | this page, kept to what a new contributor to any project can act on |
| Requirements are the documentation | requirement text carries an ID hashed from the text; the build reports which tests cover which IDs | schemas graded measured / declared / read-from-code (`specs/`); conformance assertions (`conformance/`) | stable IDs on the normative statements of the shared API description and of each protocol's vector corpus, with a coverage report from the conformance suite (§4) |
| A release checklist run by people | about 200 items, "record when and by whom each validation step was performed"; items added "as new problems … are discovered" | the work queue's gates and `no-gate:` reasons; the [15.0.9 integration record](../30-design/remedial/rc-15.0.9-integration-record.md) | one checklist template per kind of component (driver, connector, server, app), each item naming who ran it and when (§4) |
| A bug is fixed only with a test | "not considered fixed until new test cases that would exhibit the bug have been added" | the backfix register marks each defect **reproduced** or **read-derived**; break-its and red controls prove a test can fail | the same rule for every shared asset: a defect closes with a vector, fixture or test that shows it |
| "Pencils down" before release | about a week of bug fixes only | release candidates soaked against the previous release | a published freeze window for the server and connectors, announced to every app community |
| Public problem reports | a public, mirrored forum | GitHub issues per project | unchanged; add a cross-project notice channel for vendor changes (§4, cloud) |
| Several independent test harnesses | four, "designed, maintained, and managed separately" | per-project suites; this repository's replay and soak labs | shared vectors and fixtures that every implementation runs, so implementations check one another |
| Anomaly testing | simulated out-of-memory, I/O errors, crashes, power loss | fault injection in faketandem; disruption scenarios in the journey lab | fault injection in every simulator and lab: dropped, duplicated and corrupted frames, disconnects mid-command, clock skew, vendor refusals |
| Coverage target | 100% MC/DC for the library | none stated | a target chosen **per layer, by how many people depend on it**, and stated openly |
| Configuration management | code mirrored on three servers with two hosting companies | git and GitHub | release artefacts (Docker images, app builds) reproducible from the repository (the xz lesson, §7) |

## 4. The quality kit, layer by layer

What each layer needs, what exists, and the first step. Detail and file paths are in the
[device](../60-research/programme/stack-census-2026-09-30/device-layer.md) and
[cloud](../60-research/programme/stack-census-2026-09-30/cloud-layer.md) annexes.

| layer | the kit | exists today | first step |
|---|---|---|---|
| **device** (drivers, simulators, pairing cryptography) | a language-neutral vector corpus per protocol; known-answer tests from public standards for each primitive; fixed-randomness handshake transcripts; simulators with a virtual transport and fault injection; parser fuzzing; a hardware-in-the-loop smoke run before release | faketandem (simulator in CI with faults); pumpX2's captured-message suite; OpenMinimed's cross-implementation SAKE transcript; AndroidAPS's cross-platform crypto vectors; Omnipod vectors held in common by copying | extract the Omnipod and Tandem vectors that already exist into one file each and load them from every implementation's tests |
| **controller** (Loop, Trio, AndroidAPS, iAPS, oref0) | algorithm conformance vectors across implementations; driver test targets run in the app's CI; validation on real AID rigs | `conformance/` vectors for oref0; Trio and AndroidAPS CI; LoopAlgorithm as a package | run the kits' own test targets in Trio's and LoopWorkspace's CI |
| **cloud** (vendor connectors) | per-vendor contract notes; shared recorded-fixture suites with refusal cases; a read-only change canary with consenting accounts; a shared connector lab | nightscout-connect's LibreLinkUp lab against real Nightscout storage in CI; tconnectsync's captured-data parser tests; this repository's connector soak and log canary | one fixture format, seeded with synthetic LibreLinkUp and Dexcom Share cases, adopted by two implementations |
| **shared contract and servers** | one current API description with stable statement IDs; a conformance suite any server can run; the client census kept current | schemas, quirks registry and per-client mappings (`specs/`, `mapping/`); the 40-client census; Nocturne's parity suite | publish the conformance suite as runnable against any server URL, and invite Nocturne's maintainers to run it |
| **followers and reports** | the journey map's jobs checked on each release | the [journey map and lab](../60-research/remedial/journey-map-15.0.9.md) for cgm-remote-monitor | name the jobs each follower app promises and check them against the release candidate |
| **the data holder's view** | aggregate checks that data holders run on their own data, returning only results | `tools/nsprobe`; the OREF-INV-003 replication | a release-comparison probe that any holder can run |

**What the layers share.** Every layer needs the same three things: inputs described in one
language-neutral format, a record of each run, and a way for every implementation to use the same
inputs. That is what makes one person's test evidence reusable by the other projects.

### 4.1 The record every run leaves

A test run anywhere in the stack leaves one record with the same shape. Borrowed from design
controls, where **design inputs** (requirements) lead to **design outputs** (the code),
**verification** shows the outputs meet the inputs, and **validation** shows the product meets the
user's need.

| part | contents |
|---|---|
| identity | component, version, commit, and the digest of the artefact tested |
| inputs | the requirement IDs covered; the vector-corpus or fixture version; simulator scenarios; the configuration matrix (runtime, database, device, region) |
| procedure | the checklist item or gate; who ran it and when; automated or by hand |
| outputs | pass, fail and skip counts; the red control that shows the check can fail; logs, de-identified |
| known gaps | what was not covered and why (no device, no account in a region, no rig) |
| status | **verified** (checks against the requirements) or **validated** (checked in real use on a rig or with a person); never "safe" |

The 15.0.9 records in this repository already carry most of these parts; the proposal is that every
project can produce the same record with shared tooling. Rule 6 of the collaboration model applies:
a record says what was checked, and says nothing about clinical safety or regulatory status.

## 5. Build it in stages

Zephyr, an open-source real-time operating system working toward safety certification, brings in
its coding rules in stages: first published and "not enforced", then enforced on a small scope, then
widened ([Zephyr safety overview](https://docs.zephyrproject.org/latest/safety/safety_overview.html)).
The same pattern fits here, with each stage useful even if the next never happens:

1. **Publish.** The vector-corpus format, the fixture format, the record template and the checklist
   templates. No project is asked to change anything. Volunteer-sized.
2. **Adopt where it is already half done.** The projects that already share vectors or run
   simulators in CI: Omnipod (three implementations holding copied vectors), Tandem (pumpX2 and
   faketandem), Medtronic 7xxG (PythonSake and JavaSake), and nightscout-connect with
   cgm-remote-monitor.
3. **Shared labs.** A connector lab and a change canary for the vendor clouds; the conformance suite
   runnable against any server.
4. **The expensive pieces.** New simulators, parser fuzzing across decoders, a hardware-in-the-loop
   rig, controller validation on real AID rigs.

Each project's maintainers decide whether and when their project takes part.

## 6. What it costs, and who could pay

The census record estimates the device and cloud layers at **167–388 person-weeks one-time (about
3–7.5 person-years), then 0.4–0.7 of a full-time engineer, plus 6–30 person-weeks a year of vendor
changes** ([record §6](../60-research/programme/stack-census-2026-09-30.md#6-what-a-shared-quality-control-system-would-take-estimates)).
These are estimates with stated assumptions. They exclude maintainers' review time, counsel's time
and the server layer, which the sponsored-team proposal sizes.

Much of stage 1 and 2 is volunteer-sized: a checklist template, the bug-to-test rule, and vectors
extracted from tests that already exist. The rest is sustained work on fixed dates set by others, the
kind the sponsored-team proposal describes. Some maintainer time is paid today: commercial
Nightscout hosts pay for part of the time of maintainers who work for them, on terms each host sets,
and those arrangements differ in scope, availability and the compliance obligations each host
carries. No organisation pays for maintenance as shared ecosystem work, on published terms, with a
public report. That shared arrangement is what this page and the sponsored-team proposal describe.

Funding routes found (sources: [histories annex §C](../60-research/programme/stack-census-2026-09-30/histories.md#c-funders-for-maintenance-and-security)):

| route | fits | caveat |
|---|---|---|
| NLnet / NGI Zero | small milestone grants for public deliverables; the only funder read that has funded health software (Goupile, 2024) | its Commons Fund closed its final call on 2026-06-01; other programmes remain; a "clear European Dimension" is required, which a US 501(c)(3) would need to check |
| Sovereign Tech Fund | "open digital base technologies": the shared contract, conformance suite, protocol and connector libraries | work over €50,000; "currently not looking for user-facing applications" |
| Alpha-Omega | security audits and security work on critical projects, in quarterly rounds | security scope only |
| companies that need assurance | release evidence packaged for their own quality systems, fixes on the line they run (SQLite's model; collaboration rule 8) | the evidence that decides a public release stays public |
| a member-funded shared lab | device and connector labs that hosts and app builders each run privately today, pooled (KernelCI's model) | needs members; labs hold health data only when de-identified |

## 7. Histories that map

OpenSSL after Heartbleed, xz-utils, curl, Debian's paid long-term support and Dunc-Tank, the Open
Home Foundation, KernelCI, ELISA and Zephyr, and Tidepool Loop are in
[PRECEDENTS: histories](perspective/PRECEDENTS.md#histories), each with what maps to this
proposal; sources are in the [histories annex §B](../60-research/programme/stack-census-2026-09-30/histories.md#b-histories).
The two this proposal leans on most: OpenSSL turned money into a working project through named roles
plus written policies, not money alone; and Debian's lesson from 2006 is never to let one person
decide who is paid.

## 8. Agreeing the requirements

### 8.1 Methods other projects use

Sources: [histories annex §D](../60-research/programme/stack-census-2026-09-30/histories.md#d-consensus-methods).

| method | where from | how it would work here |
|---|---|---|
| requirement records with published states | Kubernetes KEPs (`provisional`, `implementable`, `implemented`, `deferred`, `rejected`, `withdrawn`, `replaced`), with approvers "distinct" from authors | each requirement for the shared layers is a record with a state, approved by maintainers of the projects it affects who did not write it |
| a champion who records dissent | Python PEP 1: the champion is "responsible for building consensus … and documenting dissenting opinions" | each record carries a dissent section; the volunteer-only view has a standing place there (§8.2) |
| a final comment period | Rust RFCs: ten calendar days, advertised widely; not "consensus amongst all participants" but no "strong consensus *against*" | a ten-day window announced in every app community's channel before a requirement becomes `implementable` |
| rough consensus | IETF RFC 7282: "all issues are addressed, but not necessarily accommodated" | the test for each requirement: every objection has a written answer; objections are answered, not counted |
| goals with owners | Rust project goals: "Goals cover a problem, not a solution"; "Nothing good happens without an owner"; reset every six months | a six-monthly slate of ecosystem goals, each with a named owner (volunteer or paid) and the projects that support it; funders pay for a goal, not a solution |
| a cap on any one employer | Python PEP 13: "at most 2 members of the council can work for any single employer" | no deciding group has a majority from one company or host |

### 8.2 The volunteer-only view, stated fairly

Some people argue the ecosystem should have no paid maintainers. The strongest form of that view
([histories annex §E](../60-research/programme/stack-census-2026-09-30/histories.md#e-the-volunteer-only-position-steelman-and-reconciliations)):

1. **Independence.** Whoever pays sets priorities, even without meaning to. In software next to
   dosing, a host's commercial priority could displace safety work.
2. **Fairness.** Paying some people makes a two-class project and can demotivate the others; Debian's
   2006 signers said so.
3. **Motivation is not bought.** "Money alone will not fix a struggling infrastructure project"
   ([Roads and Bridges](https://www.fordfoundation.org/wp-content/uploads/2016/07/roads-and-bridges-the-unseen-labor-behind-our-digital-infrastructure.pdf)),
   and some maintainers do not want pay.
4. **Money is fragile.** A paid seat ends when its sponsor leaves; a volunteer project has no
   payroll to lose.
5. **Money brings noise.** curl ended its bug bounty for that reason.
6. **The line between DIY and regulated.** People build and run these tools themselves; paid
   development could blur that line.

Each of these protects something every stakeholder wants: independence, fairness, and a community
that owns its tools. §8.1 asks that every objection get a written answer, so each has one here,
drawn from the histories in §7 and the [precedents](perspective/PRECEDENTS.md):

1. **Independence.** The risk is real, and the answer is structural rather than an absence of money:
   no payment decided by one person, paid people never approving their own work, and no deciding
   group with a majority from one employer (§8.3, rules 1, 4 and 5). Unpaid work is not free of
   outside priorities either; it goes to whatever its volunteers, or their employers, can fund.
2. **Fairness.** Debian's objection came from a project of about 1,000 voting developers, and
   Debian later accepted paid long-term support run outside the project (§7). The census counted 219
   human authors across 62 repositories in the last year, and cgm-remote-monitor had 11 to 18 a year
   from 2021 to 2025 ([sponsored-team proposal §2](SPONSORED-TEAM-PROPOSAL.md#2-why-now)). At that
   scale the question is less who is paid than whether the dated work in §6 gets done.
3. **Motivation is not bought.** Agreed for the work people choose. Paid roles here cover the work
   that waits: review queues, releases, vendor changes, security response. A maintainer who does not
   want pay is never asked to take it; that is a reason not to require pay, not to prevent it for
   others.
4. **Money is fragile.** So is volunteer time: cgm-remote-monitor's committers fell from 47 in 2019
   to 11 in 2024 before its releases slowed (sponsored-team proposal §2). Fixed terms, several funding
   routes (§6) and public records that outlast any one person reduce both risks.
5. **Money brings noise.** curl ended paying *per report*. Its lead is employed by a company that
   sells curl support (§7). Nothing here pays per report.
6. **The line between DIY and regulated.** Tidepool Loop's clearance ran alongside the DIY project,
   each with its own label, and ELISA and Zephyr supply evidence while certification stays with the
   certifier (§7). The same releases can serve people who build their own tools and companies that
   use the evidence in their own quality systems; collaboration rule 6 keeps the labels apart.

### 8.3 Requirements both views could accept

Other projects reconciled the same tension with safeguards, each sourced in the annex. Together they
make a set that a volunteer-only advocate and a proponent of paid maintenance could both accept:

1. No payment is decided by one person.
2. Paid work is a named role, service or goal, with public deliverables and an end date.
3. Money is held and paid out by a body that does not hold merge rights.
4. Paid people do not approve their own work.
5. No deciding group has a majority from one employer or host.
6. A public report every month.
7. Each project's maintainers, paid or not, keep the merge decision; no payer gains it.
8. Every proposal records its dissent, and every objection gets a written answer.

That gives the volunteer-only view a standing test that anyone can check in public. If a payer
ever decides what merges, rule 7 has been broken; if paid people approve their own work, rule 4. If paid work goes unreported, rule 6 has been
broken.

### 8.4 A first slate to discuss

These are **candidate** requirements for success, offered as the first records for the process in
§8.1, not as decisions. Each is a standing commitment of someone's time on dates set by others, so
each is read together with its cost (§6): adopting a requirement without funding it assigns the
work to whoever volunteers.

| id | candidate requirement | who it serves most | evidence it would be measured by |
|---|---|---|---|
| RQ-1 | Alarms and data keep working through vendor cloud changes | people with diabetes, caregivers | days from a vendor change to a released fix, per connector |
| RQ-2 | The server is released on a published schedule, with security fixes on a stated horizon | everyone, hosts most | release dates against the schedule |
| RQ-3 | Every device protocol with two or more implementations has one shared vector set | app projects, driver authors | protocols with a corpus, and implementations loading it |
| RQ-4 | Every release of a shared component leaves a public record in the §4.1 shape | reviewers, hosts, researchers | records per release |
| RQ-5 | Data holders can run checks on their own data without sending it anywhere | data holders, researchers | probes available; studies run |
| RQ-6 | No single party controls the shared contract | second servers, app projects | the change-request record (collaboration rule 5) |
| RQ-7 | The rules in §8.3 hold | volunteers, the foundation | the monthly reports |

## 9. Decisions requested

**For the maintainers of each project:**

1. Whether the kit in §4 fits your layer, and which piece your project would try first.
2. Whether your project would load a shared vector set or fixture set from its own tests, if one
   were published in a neutral repository.
3. Whether the method in §8.1 is acceptable for requirements that touch more than one project.

**For the foundation board:**

4. Whether the foundation hosts the neutral repository for the shared formats, corpora and records,
   and the requirement records of §8.
5. Whether to adopt the rules in §8.3 for any paid work it funds or brokers.
6. Which of the funding routes in §6 to pursue, and who writes the first application.

**For the companies that host or build on Nightscout:**

7. Which records in the §4.1 shape your own quality processes would use, and what you would
   contribute toward the shared labs.

## 10. Points for reviewers to verify

For a quality-management professional:

1. Whether the record in §4.1 is enough for a company to use as input to its own design controls,
   and what it must not be read as.
2. Whether "verified" and "validated" are used consistently with the standards the reviewer works to.

For counsel:

3. Whether a change canary that uses volunteers' own consenting accounts against vendor clouds is
   consistent with each vendor's terms of use (cloud annex §4.3).
4. Whether shared vector corpora derived from device captures raise any issue under the exemptions
   in [DIGITAL-RIGHTS](../DIGITAL-RIGHTS.md), and what de-identification they need.
5. Whether a US 501(c)(3) can meet NLnet's "European Dimension", and the terms of any grant in §6.

For everyone:

6. The census figures are dated 2026-09-30; re-run the census before quoting them.
7. The effort figures are estimates; check them against maintainers' own experience.
8. The histories in §7 were read 2026-09-30; the annex §F lists what could not be verified.
