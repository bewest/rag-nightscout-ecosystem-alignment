# A sponsored maintenance team for the Nightscout ecosystem — proposal

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**DRAFT PROPOSAL for discussion.** Written 2026-09-27 against this repository at `de46efc1` and
cgm-remote-monitor `official/dev` `295f1177`. Where it touches employment, contracting, tax or
the foundation's exempt status, it needs review by the foundation's counsel and accountant before
any decision rests on it (§9). Nothing here is decided.*

## 1. The request

Fund a small, fulltime, paid team whose job is to keep the Nightscout ecosystem's shared software
reviewed, released and working with the apps that depend on it. The team works alongside the
volunteer maintainers and contributors, answers to the foundation for the time it is paid for, and
takes no authority away from any project.

Long-standing maintainers of the ecosystem projects have asked the foundation for this.
**[To confirm before this is shared: whether the maintainers who made the request agree to be named
here.]**

## 2. Why now

**The ecosystem depends on one shared server.** Nightscout is a secondary display for CGM and pump
data, and it is also the place where many other apps read and write that data. The 15.0.9 client
survey mapped 40 client repositories against 15 parts of the API
([consumer impact](../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md)). Loop, Trio,
AndroidAPS, xDrip+, caregiver apps, watch faces and reporting tools all rely on how the server
actually behaves. A change there reaches every one of them.

**Releases have come in long gaps.** Tag dates in cgm-remote-monitor (`git tag --sort=creatordate`):

| release | tagged | days since the previous release |
|---|---|---:|
| 14.2.6 | 2022-09-30 | 295 |
| 15.0.0 | 2023-10-18 | 383 |
| 15.0.2 | 2023-10-25 | 5 |
| 15.0.3 | 2025-05-08 | 561 |
| 15.0.4 | 2026-02-28 | 296 |
| 15.0.7 | 2026-04-29 | 57 (15.0.5 and 15.0.6 in between) |
| 15.0.8 | 2026-09-04 | 128 |
| 15.0.9 | candidate `295f1177`, not tagged | — |

**Important work can wait for years.** The MongoDB 5 driver upgrade was first proposed in #7344,
opened 2022-02-16. The upgrade that shipped was #8421: opened 2026-01-19, merged 2026-03-16, released
in 15.0.7 on 2026-04-29 (`mongodb` `^3.6.0` → `^5.9.2`). #7344 was closed as superseded on
2026-05-01. Hosting providers retire old database versions on their own schedule, so a site's
database driver is not optional maintenance.

**2026 shows what steady attention produces.** Five releases so far this year. For 15.0.9 alone
([quality record](../60-research/programme/paving-the-cowpaths-2026-09-27.md)): 85 pull requests
merged in 23 days, 146 defects filed and 87 of the 122 in scope closed, and the full test suite grown
from 1,533 passing tests on 15.0.8 to 3,473 on the candidate. Before any release is tagged, 19
integration runs, a comparison soak against 15.0.8, browser checks against a simulated household and
a census of client behaviour were all completed.

## 3. Where the time goes

Much of the engineering in 2026 was done with AI coding agents under a maintainer's direction. That
changed what limits progress. Writing a fix is now the cheap part. The steps that still need a
person are the ones this proposal would fund:

| work that needs a person | measured 2026-09-27 |
|---|---|
| review | 143 of the 171 items in the work queue route review to the maintainer; 75 of them are not yet merged or closed (`queue/work-queue.yaml`, `review` field) |
| specialist review | 21 items ask for a security or safety reviewer; 14 are open, most of them in the multitenancy and alarm work. The queue names the kind of reviewer, not a person |
| decisions | 7 items wait on a decision (`needs-decision`), plus the release decisions themselves ([needs a human](NEEDS-A-HUMAN.md)) |
| hand checks | the 15.0.9 browser walk was done by the maintainer; six checks are still owed before the tag ([contents](../../releases/cgm-remote-monitor-15.0.9/contents.md#open-items-a-releaser-must-settle)) |
| checks on real systems | no real Loop, Trio, AndroidAPS or xDrip+ setup has yet run against the 15.0.9 candidate |
| backlog | 35 open pull requests (18 opened in 2026, the oldest in 2021) and 102 open issues in cgm-remote-monitor (`gh pr list`, `gh issue list`, 2026-09-27) |

Today all of this depends on the unpaid time of a few people. When their time runs short, the work
waits.

## 4. What the team would do

A starting shape. The board and maintainers would settle the final one.

| role | what it does | why it is needed |
|---|---|---|
| **Release and review lead** | reviews pull requests, keeps the release process running on a published schedule, tags releases with the maintainers | review and release are where work waits (§3) |
| **Ecosystem compatibility engineer** | keeps the census of client apps current; runs the real-system checks with Loop, Trio, AndroidAPS and xDrip+ builders; turns what clients actually send into tests | a server change reaches every client (§2) |
| **Quality and security lead** (part time at first) | triages security reports and dependency alerts, keeps the defect register and test records, is the named reviewer for security and safety items | 21 items ask for a kind of reviewer no one is assigned to be |

Out of scope for the team:

- It does not decide what a project accepts. Each project's maintainers keep the merge decision.
- It does not change project governance or licences.
- It does not give therapy or dosing advice.

## 5. How it fits with volunteers

- **Maintainers keep authority.** The team proposes and reviews; each project's maintainers decide
  what merges, as now.
- **Paid time goes to the work volunteers find hardest to sustain**: review queues, release chores,
  compatibility testing, security triage. New features stay open to everyone.
- **Everything happens in public.** The team works in the same repositories, issue trackers and chat
  as everyone else, and publishes a short monthly report.
- **The team makes it easier to contribute.** Reviews happen faster, and the release schedule is
  published, so a contributor knows when their fix will ship.

## 6. How other open-source organisations do this

Gathered 2026-09-27 from each organisation's own pages and IRS Form 990 summaries on ProPublica.
Figures are for the year shown. Re-check each against its source before quoting it (§9).

| organisation | how money comes in | who is paid, to do what | who decides | what it suggests for us |
|---|---|---|---|---|
| [Zig Software Foundation](https://ziglang.org/zsf/) (US 501(c)(3), 2020) | donations almost entirely: FY2025 revenue $921,832, 100% contributions ([990](https://projects.propublica.org/nonprofits/organizations/845105214)); 2024 income $670,673 from GitHub Sponsors and a few large donors ([2024 report](https://ziglang.org/news/2025-financials/)) | one fulltime employee plus hourly contractors; of $520,749 spent in 2024, $306,362 went to contractors and $154,263 to the employee, "92% of our money in 2024 paying contributors" in the report's words ([2024 report](https://ziglang.org/news/2025-financials/)) | a three-person board; no published technical governance document | the closest match: small, lean, nearly all money goes to code. It rests on one lead and a few large donors |
| [Haskell Foundation](https://haskell.foundation/) (2020; funds held through Haskell.org, Inc., a 501(c)(3); [merger announced 2024](https://blog.haskell.org/haskell-foundation-and-committee-merger/), completion not verified) | corporate sponsorship tiers from $15k to $100k+ a year; sponsors sit on an advisory board ([donations](https://haskell.foundation/donations/)); Haskell.org, Inc. FY2024 revenue $136,256 ([990](https://projects.propublica.org/nonprofits/organizations/475236502)) | one executive director from 2024; a DevOps role restructured after a 2024 shortfall ([post](https://discourse.haskell.org/t/devops-at-the-haskell-foundation/9654)); from mid-2026 no director and a volunteer technical committee directing most spending ([2026 update](https://discourse.haskell.org/t/haskell-foundation-2026-update/14136)) | a 12-member board; existing technical committees keep their authority | sponsor income did not reliably cover a director plus an engineer; fund engineering first, administration second |
| [CNCF](https://www.cncf.io/) (a directed fund of the Linux Foundation, a 501(c)(6), 2015) | 2024: events about two-thirds, membership 23.5%, training 7.5%; 728 members ([annual report 2024, p. 26](https://www.cncf.io/wp-content/uploads/2025/04/CNCF-Annual-Report-2024_v2.pdf)); dues up to $350k a year ([join](https://www.cncf.io/about/join/)) | pays for services (events, infrastructure, security audits, mentoring), not core developers; project engineers are employed by member companies | a governing board sets budget; a technical oversight committee admits projects and tracks their maturity; projects keep their own governance ([charter](https://github.com/cncf/foundation/blob/main/charter.md) §9(c)) | useful for its maturity levels and project independence; its funding model needs many corporate members we do not have |
| [WHATWG](https://whatwg.org/faq) (2004; steering group since 2017) | no published budget | editors work on the standards; they are understood to be employed by browser vendors (not verified) | a steering group of organisations that build a major browser engine ([agreement](https://whatwg.org/sg-agreement)); a feature needs two or more engines | authority follows the people who implement. Our equivalent is the app builders whose clients depend on the server |
| [W3C](https://www.w3.org/about/) (US 501(c)(3) since 2023) | mainly membership dues: FY2024 revenue $8.71M ([990](https://projects.propublica.org/nonprofits/organizations/844023862)); 335+ members | about 50 staff who coordinate and edit; members' employees do the technical work | a board, an advisory board, a technical architecture group; working groups decide by consensus | stable staff funding, but the overhead suits many paying members, not a small community |
| [PSF Developers-in-Residence](https://www.python.org/psf/developersinresidence/) (Python) | each seat paid for by a named sponsor; the first began in July 2021 ([announcement](https://pyfound.blogspot.com/2021/07/ukasz-langa-is-inaugural-cpython.html)) | four residents today; the work is triage, reviews, build monitoring and security response in support of the volunteer core team | the core developers and their elected steering council | the nearest model to §4's roles: paid people doing the review and release work volunteers find hardest to sustain. Each seat lasts only as long as its sponsor |
| [Sovereign Tech Fellowship](https://www.sovereign.tech/programs/fellowship) (German federal funding) | public money, competitive | up to 12 fellows, freelance or employed (up to three two-year posts at €64k–€82k a year), working on their own projects | the fellows' own projects | a possible grant source for option C; it supplements a plan, it cannot anchor one |

What they have in common:

- Where paid staff exist, the volunteer or project maintainers keep technical authority.
- Money tied to one sponsor or a few donors is the usual weak point.
- The smallest organisations that pay for code (Zig, the PSF residencies) spend almost all of it on
  engineering work and very little on administration.

## 7. Options

| option | what it is | first-year cost | trade-off |
|---|---|---|---|
| A. Release and review lead only | one person, fulltime | [board to fill in] | smallest step; one person is still a single point of failure |
| B. The three roles in §4 | two fulltime, one part time | [board to fill in] | covers review, compatibility and security; needs sustained funding |
| C. Grant-funded fixed term | option A or B for 12–18 months from a grant | per grant | tests the model before a long-term commitment; ends when the grant ends |
| D. No change | volunteers only | none | keeps today's pattern of long release gaps |

The board fills in the costs (§9). For reference, the Sovereign Tech Fellowship pays €64k–€82k a year
for an employed two-year post, and Zig paid $460,625 to its contractors and one employee in 2024 (§6).

## 8. How we would know it works

Measured the same way as the 15.0.9 record, and reported every quarter:

- time from a pull request opening to its first review, and to merge or close;
- time from a merge to the release that ships it;
- releases per year, and whether they follow the published schedule;
- the open-issue and open-PR backlog, and the age of the oldest items;
- how many client apps are checked against each release on real systems;
- how many security reports are acknowledged and resolved within the published window.

## 9. Points for reviewers to verify

For counsel and the accountant:

1. Whether the team members are employees or contractors. This affects classification, taxes,
   benefits and jurisdiction, since the maintainers do not all live in one country.
2. Whether paying developers who also volunteer on the same projects raises any private-benefit or
   conflict-of-interest issue for a 501(c)(3). What conflict-of-interest policy would cover it?
3. Whether restricted grants or corporate sponsorship impose conditions that could affect project
   independence, and how to disclose them.
4. How work paid for by the foundation is licensed and owned, so that it stays under each project's
   existing open-source licence.
5. The figures in §6 come from the organisations' pages and ProPublica 990 summaries (the Zig figures
   were re-read from the source on 2026-09-27). Confirm each against the underlying 990 before quoting it.
   Not verified: WHATWG editors' employment, and whether the Haskell Foundation merger has completed.

For the board:

6. Cost ranges for options A–C, and which funding sources to approach.
7. Who the team reports to, and how the maintainers take part in hiring and reviews.

For the maintainers:

8. Whether the three roles in §4 are the right ones.
9. Whether the success measures in §8 are the right ones.

Assumptions this draft makes:

- the foundation can hold restricted funds for this purpose;
- the maintainers would take part in hiring;
- the team would work in public, like any other contributor.
