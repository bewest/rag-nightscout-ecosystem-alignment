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
| 1 | This plan | done | this commit |
| 2 | Draft HISTORY | in progress | |
| 3 | Draft GOVERNANCE-TODAY | in progress | |
| 4 | Draft ECOSYSTEM-EVIDENCE, moving evidence out of the proposals; one home per figure, generated where a generator exists | not started | |
| 5 | Part 2: move PRECEDENTS, add case studies on the §4 template, write INFRASTRUCTURE-TRANSITION | not started | |
| 6 | Slim the four proposals to cite parts 1–2; refresh their stale figures by pointing at the one home | not started | |
| 7 | COLLABORATION-MODEL §7: a range of governance options, from "remain informal" to a cross-project technical council (proposed) | not started | |
| 8 | Landing page and site nav in three parts | not started | |
| 9 | Gates: `make docs-links` (with a restored dead link shown red), `make views-check`, `make site`; contradiction sweep across the overview | not started | |
| 10 | Maintainer review points (§6) | open | |

## 6. Open points for the maintainer

1. **Naming the requesters.** SPONSORED-TEAM-PROPOSAL §1 still carries "[To confirm before this is
   shared: whether the maintainers who made the request agree to be named here.]" on the published
   site.
2. **GOVERNANCE-TODAY gaps only the foundation can fill**: how spending is approved, who holds which
   repository and domain rights, how a submitted proposal is tracked. The page lists them as open
   rather than guessing.
3. **Whether HISTORY names founders and early authors** where primary sources name them, or uses
   roles throughout.

## 7. Figures found stale while planning

These are corrected in step 6 by pointing at the one home of each figure, not by copying the new
value:

- SPONSORED-TEAM-PROPOSAL §3: "144 of the 172 items … route review to the maintainer" (measured
  2026-09-27); PROGRAMME-STATUS's generated table now reads 149 of 183.
- ECOSYSTEM-PROGRAMME §3: "138 of 172"; and §2a: "measured 63 repositories" (62 distinct).
