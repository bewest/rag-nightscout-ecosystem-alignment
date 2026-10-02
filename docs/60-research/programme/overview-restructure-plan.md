# Overview restructure: observations, perspective, recommendations — plan and progress

*Contributor- and maintainer-facing. **Living plan**, started 2026-10-02 against this repository at
`0f3ca59a`. It records the plan for reorganising `docs/00-overview` and the progress of each step.
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
| 10 | Maintainer review points (§6) | open | |

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
