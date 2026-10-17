# Overview restructure: observations, perspective, recommendations — plan and progress

*Contributor- and maintainer-facing. **Living plan**, started 2026-10-02 against this repository at
`0f3ca59a`. It records the plan for reorganising `docs/00-overview` and the progress of each step.
§8 onward, added 2026-10-17, plans the second phase: drawings, and a thesis that has matured since
the first.
The maintainer asked for it on 2026-10-02. Decisions in it are the maintainer's unless a row says
"proposed".*

## 1. Why

Readers of the overview pages meet the ecosystem's facts inside documents that argue for a
particular answer. The sponsored-team proposal, for example, gives about 200 of its 359 lines
(§1a, §2, §3, §6a) to evidence: cross-project release history, contributor counts, clinical
studies, review load and vendor changes. A reader who wants a frame of reference first has to take
in a persuasive argument at the same time. Several readers have said this swamps them.

The facts are useful whether or not anyone agrees with the proposals. So they get their own pages,
the comparison material that gives perspective gets its own pages, and the author's
recommendations are labelled as recommendations and cite the other two.

## 2. The three parts

| part | asks | rules for the pages in it | where |
|---|---|---|---|
| **1. Observations** | What exists, and what has happened? | descriptive only: dates, counts, sources, methods and limits; no "should", no assessment words, no recommendation; every figure anchored to a date and a commit or a command | `docs/00-overview/observations/` |
| **2. Perspective** | How have comparable communities handled the same situation, and what frames help read the observations? | case studies on one template (§4); the volunteer-only view stated fairly beside the others; counter-evidence kept; interpretation labelled as interpretation | `docs/00-overview/perspective/` |
| **3. Recommendations** | What does the author propose? | each page opens with a line saying it is the author's recommendation and the author's interests; it cites parts 1 and 2 for facts and does not restate them; it offers options including "no change" | the existing proposal pages, at their current paths |

Operational pages (PROGRAMME-STATUS, ROADMAP, NEEDS-A-HUMAN, REVIEWER-ONBOARDING, DEFINITION-OF-DONE,
DOCUMENT-CONTROL) stay where they are. They are instruments of the work, not part of the argument.

Existing proposal URLs stay unchanged because they have been shared. PRECEDENTS moves into part 2, and
every inbound link to it is rewritten (DOCUMENT-CONTROL §3.5).

## 3. Pages

| page | part | built from | state |
|---|---|---|---|
| `observations/HISTORY.md` — a chronology of the ecosystem, 2013 to now | 1 | histories annex §B8; sponsored-team §2 tag table; research of 2026-10-02 | step 2 |
| `observations/GOVERNANCE-TODAY.md` — who decides what, today | 1 | repository and organisation measurements of 2026-10-02; the foundation's public pages | step 3 |
| `observations/ECOSYSTEM-EVIDENCE.md` — what the ecosystem depends on and what keeping it current takes | 1 | sponsored-team §1a, §2, §3, §6a; collaboration §3; quality-system §2; the stack census; the client census | step 4 |
| `perspective/PRECEDENTS.md` — the precedent table (moved) plus transition case studies | 2 | PRECEDENTS; collaboration §4, §4a; quality-system §7; sponsored-team §6; histories annex | step 5 |
| `perspective/INFRASTRUCTURE-TRANSITION.md` — when a DIY ecosystem becomes infrastructure | 2 | the "gravity" dimensions, each mapped to its observation or marked not measured; the volunteer-only view (quality-system §8.2) and its counter-evidence | step 5 |
| proposals: SPONSORED-TEAM-PROPOSAL, COLLABORATION-MODEL, QUALITY-SYSTEM, ECOSYSTEM-PROGRAMME | 3 | slimmed to the request, the options and the reviewer points, citing parts 1–2 | step 6 |
| the overview landing page and site nav | all | `tools/site/landing.yaml`, `tools/site/landing/docs-00-overview.md` | step 8 |

## 4. Case-study template for part 2

Each precedent that is used as a history, not only as a row in the table, answers the same
questions:

1. **Starting condition** — what the project was.
2. **What came to depend on it.**
3. **The pressure** — what stopped scaling, with dates.
4. **The response** — what changed, and when.
5. **What stayed volunteer or community-controlled.**
6. **What became paid or professional.**
7. **What went wrong or is still disputed.**
8. **What transfers here, and what does not** — sized against the ecosystem (PRECEDENTS "size").

## 5. Steps and progress

| step | what | state | commit |
|---|---|---|---|
| 0 | Fixes found by the 2026-10-02 source check: BFQ-72's withheld disposition, the census repository count, unsupported precedent claims | done | `0f3ca59a` |
| 1 | This plan | done | `e3d7b65c` |
| 2 | Draft HISTORY | drafted: 2012–2026 chronology from `git` on the stack clones and primary pages read 2026-10-02 (a sample re-run by the session; each external link checked for status); roles, not names; where sources differ and what is not established listed in its §5 | this commit |
| 3 | Draft GOVERNANCE-TODAY | drafted: per-repository merge and release accounts, licences and branch rules for 20 repositories; written governance files; the foundation's public statements and processes; the provider listing; where we looked and found nothing; what only the foundation can supply. Measured with `gh api` and the foundation's pages 2026-10-02, a sample re-run by the session. It corrected the provider count used in two pages (nine, not eight, at `9b5afad2`) | this commit |
| 4 | Draft ECOSYSTEM-EVIDENCE, moving evidence out of the proposals; one home per figure, generated where a generator exists | drafted: census, client survey, cross-project releases and contributors, maintenance time (review load links to the generated table), vendor calendar and connector changes, clinical studies | this commit |
| 5 | Part 2: move PRECEDENTS, add case studies on the §4 template, write INFRASTRUCTURE-TRANSITION | PRECEDENTS moved, and now holds the comparison tables the proposals carried (collaboration §4 rules and §4a SQLite, sponsored-team §6 funding, quality-system §7 histories), each proposal keeping its heading, a pointer and its own reading; INFRASTRUCTURE-TRANSITION drafted; six transitions on the §4 template (OpenSSL, OpenStreetMap, Debian, Home Assistant, the PSF residencies, Tidepool Loop), with "not found in the sources read" where a question has no source | `6e4137b4`, this commit |
| 6 | Slim the four proposals to cite parts 1–2; refresh their stale figures by pointing at the one home | all four labelled part 3; SPONSORED-TEAM-PROPOSAL 359 → 249 lines, COLLABORATION-MODEL 246 → 196 (§3 calendar and §4 tables), QUALITY-SYSTEM 317 → 307 (§7 table); ECOSYSTEM-PROGRAMME's 63 and 138-of-172 now cite the evidence page and the generated table | `6e4137b4`, this commit |
| 7 | COLLABORATION-MODEL §6a: four options from "remain informal" to a cross-project body for the shared contract, each with what it costs and leaves open; board decision 0 is which to start from; CNCF's sizing guidance quoted from the post (re-read 2026-10-02) | done | this commit |
| 8 | Landing page and site nav in three parts | `docs/00-overview/README.md` is the section index in three parts, and `observations/` and `perspective/` each have a README index; the hand-written landing file it replaces is removed; nav lists the operational pages, then the proposals, then the two subdirectories | this commit |
| 9 | Gates: `make docs-links` (with a restored dead link shown red), `make views-check`, `make site`; contradiction sweep across the overview | done: links green after a planted dead link went red; 94 overview anchors resolve (a wrong anchor is caught); views current; `make site` 0 warnings, 0 unresolved links, after re-rendering the ecosystem-programme rich page (`site/pages`) from its changed source; sweep retargeted five links whose content moved and found no stale 172/144/138/63/eight figures; observation pages scanned for assessment words (only quotations and a reviewer note remain) | this commit |
| 10 | Maintainer review points (§6) | two decided 2026-10-02 (roles throughout; 990-N left out); naming the requesters and the foundation-only facts still open | `d1bab40e` |
| 11 | Keep the overview accurate as 15.0.9 moves | the overview no longer pins the candidate's `dev` head: HISTORY, ECOSYSTEM-EVIDENCE and ECOSYSTEM-PROGRAMME point at ROADMAP §1 and the colophon, which are kept current with the release. **After BF-124 and BF-127 merge** (queue `BFQ-124`, `BFQ-127`, the last two 15.0.9 blockers): check the overview with `grep -rnE '<old dev head>' docs/00-overview`, confirm ROADMAP §1, PROGRAMME-STATUS and the colophon are re-measured on the new head, re-render `site/pages` pages whose sources changed, run `make docs-links views-check site`, push, and republish. **When 15.0.9 is tagged:** add the tag date to ECOSYSTEM-EVIDENCE §3's tag table and to HISTORY §4 | in place; post-merge pass pending | this commit |

## 6. Open points for the maintainer

1. **Naming the requesters.** SPONSORED-TEAM-PROPOSAL §1 still carries "[To confirm before this is
   shared: whether the maintainers who made the request agree to be named here.]" on the published
   site.
2. **GOVERNANCE-TODAY gaps only the foundation can fill**: how spending is approved, who holds which
   repository and domain rights, how a submitted proposal is tracked. The page lists them as open
   rather than guessing.
3. **Names in HISTORY.** Decided by the maintainer, 2026-10-02: roles throughout. Publication
   citations (author et al.) and source URLs are kept as citations.
4. **Financial filings in GOVERNANCE-TODAY.** Decided by the maintainer, 2026-10-02: the IRS master
   file's 990-N filing requirement stays out. The page says only that ProPublica has no Form 990 data.
5. **GOVERNANCE-TODAY §7** lists five facts only the foundation can supply (bylaws and
   conflict-of-interest policy access, the request committee, spending approval, holdings,
   sponsorship records); a board member could fill them.

## 7. Figures found stale while planning

Corrected in step 6 by pointing at the one home of each figure, not by copying the new value:

- SPONSORED-TEAM-PROPOSAL §3: "144 of the 172 items … route review to the maintainer" (measured
  2026-09-27); PROGRAMME-STATUS's generated table now reads 149 of 183.
- ECOSYSTEM-PROGRAMME §3: "138 of 172"; and §2a: "measured 63 repositories" (62 distinct).

## 8. Phase 2 (2026-10-17): the thesis, its documents and its drawings

Since phase 1 the overview has gained a line of argument the three parts did not plan for: which
legal entities the ecosystem needs in order to hold agreements with manufacturers, what each
entity's activities oblige it to do, and how to draw it. The maintainer asked on 2026-10-17 for an
overview of the objectives and documents, so that the drawings' labelling serves the whole, and to
consolidate rather than add pages.

### 8.1 Objectives, and the page that carries each

| objective | the claim, in one line | part | home page | drawings it needs |
|---|---|---|---|---|
| O1. Show what exists | the ecosystem today, with no agreement joining it to any manufacturer | 1 | GOVERNANCE-TODAY, ECOSYSTEM-EVIDENCE, HISTORY | Z1 today |
| O2. Show how others met it | precedents, and when a DIY ecosystem becomes infrastructure | 2 | PRECEDENTS, INFRASTRUCTURE-TRANSITION | P1 SQLite, P2 CNCF, P3 Apple |
| O3. What each activity brings | the pillars an activity triggers, for any entity; the same requirements for anyone; the nonprofit as an oversight layer | 2 | ACCOUNTABILITY-THRESHOLDS ("What each activity brings") | the single-idea drawings in §8.3 |
| O4. Which entities to muster | sponsor by default; named operators hold agreements; one codebase | 3 | ECOSYSTEM-PROGRAMME §2b, PARTNER-READINESS | Z0, Z1 proposed with views, Z2, Z2b |
| O5. What a manufacturer agreement carries | tiers A–C, data-rights terms, complaints in both directions, credentials | 3 | PARTNER-READINESS | Z2, Z3 |
| O6. Data rights | access, export, share, delegate, audit; the law that now reaches device data | 1 and 3 | DIGITAL-RIGHTS, data rights primer (queue DOCS-DATA-RIGHTS-LAW) | a "person designates a third party" drawing (§8.3) |
| O7. The technical loops | controller, hub-and-spoke sync, delegation, with requested kept apart from applied | design | 30-design hub-sync and registration pages | L1–L3 from the technical-loops note |

STRUCTURES ("Control structures, drawn") is the gallery: every drawing appears there once, with
its source, and the page that argues from a drawing embeds or links it by its label.

### 8.2 Labelling

The labels so far mix two axes: Z0–Z3 is a zoom level, P1–P3 a kind (precedent), and the research
note's L1–L3 a topic (technical loops). Z2b exists because two drawings share a level.

**Decided by the maintainer, 2026-10-17** (§8.5 point 1): one label per drawing of the form *level ·
subject*, where the level is the Leveson hierarchy the drawing sits at, and the subject is a short
name that stays stable when drawings are added beside it:

| level | what sits at it | drawings, relabelled |
|---|---|---|
| 0 · society | legislatures, regulators, the sector | 0·sector |
| 1 · ecosystem | the organisations and how they connect | 1·today, 1·proposed (+ six views) |
| 2 · organisation or agreement | one entity, one agreement, one programme | 2·agreement, 2·controller-operator, P1–P3 as 2·sqlite, 2·cncf, 2·apple |
| 3 · technical process | one loop in software and devices | 3·person-loop, 3·controller, 3·hub-sync, 3·delegation |
| idea | a single idea from the argument, drawn small | idea·sponsor-or-operate, idea·one-codebase, … (§8.3) |

The file name carries the same label (`2-agreement.yaml`), captions say "Drawing 2·agreement", and
zoom markers name the label they open into. Views keep the base label plus the stakeholder
("1·proposed, manufacturer's view"). Precedents keep their "P" names in the text, where a reader
meets them as precedents. Bands, when used, name the same levels.

### 8.3 Drawings of single ideas

Leveson's figures are crisp partly because each carries one idea. The overview's argument has
several ideas that are now buried in Z1 and Z2; each could be a drawing of 3–6 boxes:

| idea | what it shows | page that would embed it |
|---|---|---|
| sponsor or operate | the same service under the foundation as sponsor (a funding edge) and as operator (control, feedback and liability edges) | ECOSYSTEM-PROGRAMME §2b |
| one codebase, two uses | one project's releases going to people who build their own and to an operator; the return edge | ECOSYSTEM-PROGRAMME, STRUCTURES Z2b |
| oversight layer | a nonprofit above several companies: criteria and certification down, conformance results up; the companies' own regulator beside it | What each activity brings §5 |
| the same requirements for anyone | three kinds of entity (company, nonprofit, individual) facing the same requirements box; only a legal entity passes | What each activity brings §5 |
| a credential's lifetime | issue, renew, expire or revoke, and the safe state at each | PARTNER-READINESS §7 |
| complaints in both directions | person, intake, manufacturer, regulator | PARTNER-READINESS §6 |
| a person designates a third party | the person instructs the manufacturer; data goes to the third party they chose | DIGITAL-RIGHTS |
| tiers A, B, C | the same relationship drawn three times with more edges each time | PARTNER-READINESS §2 |

### 8.4 The trim pass

Measured 2026-10-17 from the inputs: 0·sector has 9 boxes and 19 edges, 1·proposed 10 and 21,
2·controller-operator (Z2b) 10 and 19, 2·agreement 8 and 14; the rest have 12 or fewer edges.
Rule for the pass: one idea per drawing; at most about 12 edges; an edge that a lower drawing
carries is cut from the higher one and replaced by the zoom marker; an edge that only restates a
label is cut.

### 8.5 Open points for the maintainer

Answered by the maintainer, 2026-10-17:

1. **Labelling** (§8.2): *level · subject*, adopted.
2. **Bands**: the maintainer asked which serves communication; recommended and applied **legal,
   social, technical**, the boundaries the maintainer described accountability crossing, on the
   drawings that span more than one (0·sector, 1·proposed, 2·controller-operator, 3·controller).
   Bands named by level would repeat the labels.
3. **First drawings**: the controller, actuator and sensor loops on the pump, phone and CGM
   (3·controller), ahead of the single-idea drawings in §8.3.
4. **Where the technical loops live**: both: in the gallery at level 3, and embedded in the design
   pages they serve (hub-sync architecture §1; controller-descriptions proposal §1).

### 8.6 Steps and progress

| step | what | state | commit |
|---|---|---|---|
| 12 | Research notes: Apple's program, vendor programmes and data rights, technical loops | done | `8869dd3b`, `ffd5e2f4`, `59688c6f` |
| 13 | ACCOUNTABILITY-THRESHOLDS widened into "What each activity brings"; Apple and Dexcom in PRECEDENTS | done | `3996bd65` |
| 14 | Grid renderer replaces Graphviz for every drawing | done | `e7566100` |
| 15 | This phase plan | done | this commit |
| 16 | Trim pass (§8.4) | done for the three largest: 0·sector 9 boxes and 19 edges → 8 and 15 (the support-community column and edges Z1 carries; the pumps-and-CGMs line routed round the left), 1·proposed 10 and 21 → 9 and 16 (complaints to Z2, the person's loop to Z3), Z2b 10 and 19 → 9 and 15 (the device classifications the text states, the hub upload). STRUCTURES text and the stakeholder table updated to match | this commit |
| 17 | Relabel to *level · subject*: inputs and SVGs renamed, titles and zoom markers relabelled, the research note's L1–L3 inputs moved into `tools/structure-diagrams/inputs/` as 3·controller, 3·hub-sync and 3·delegation; zoom markers to undrawn drawings (L1a–L3a) removed; bands on four drawings; STRUCTURES gains "The technical loops"; inbound labels and anchors updated | done | this commit |
| 18 | Single-idea drawings (§8.3) | started: idea·sponsor-or-operate (two panels; the renderer gains per-scenario node labels), in the gallery and embedded in ECOSYSTEM-PROGRAMME §2b; next one codebase, oversight layer, same requirements, credential lifetime | this commit |
| 19 | Trim 3·delegation (15 edges; one label lies on a line) | next | |
| 20 | Icons on every box (Lucide, ISC) with a generated key | done | `0f5e6c76` |
| 21 | 1·authority, believed / actual / emerging, on one layout (renderer scenarios; `authority` and `discretion` edge kinds), with the emerging landscape's properties as interpretation; asked for by the maintainer 2026-10-17 | done | this commit |
| 22 | Eight more three-panel sets: 0·diy-status, 1·data-rights, 1·hosting (policy: believed, actual, emerging); 3·identity, 1·federation, 3·registration, 2·data-commons, 2·shared-infra (designs: believed, actual, proposed). Gathered with 1·authority on a companion page, PROCESS-MODELS ("What we believe, and how it works"), so the gallery stays to single-view drawings; TEFCA and eduGAIN added to PRECEDENTS; nine icons added to the key | done | this commit |
