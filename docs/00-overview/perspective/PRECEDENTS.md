# Precedents the overview proposals cite

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Perspective** (part 2 of the overview; [how the overview is organised](../README.md)). Living page,
written 2026-10-01 against this repository at `1644125b`, moved here 2026-10-02. The frame these
precedents are read in is [when a DIY ecosystem becomes infrastructure](INFRASTRUCTURE-TRANSITION.md). One table of every
organisation that the [sponsored-team](../SPONSORED-TEAM-PROPOSAL.md),
[collaboration](../COLLABORATION-MODEL.md) and [quality-system](../QUALITY-SYSTEM.md) proposals cite. Each
row is sourced where the "sourced in" column points, and figures carry the date they were read
there; re-check them at the source before quoting. "not read" means no figure has been read from a
source, not that none exists.*

## Why one table

Each proposal cites the organisations whose practice its rules borrow. Read together, they differ
most in two things a single proposal's table does not show: **size**, which decides whether a
practice transfers, and **the commercial role**, which shows how each keeps companies that build on
it from gaining control.

## The table

| organisation | money comes from | who is paid | commercial role | conformance or quality evidence | size | sourced in |
|---|---|---|---|---|---|---|
| **Nightscout ecosystem** | donations to the foundation (amounts not read); commercial hosts pay part of the time of the maintainers who work for them | no shared, published paid role | eight hosted providers listed in the docs; a second server lists one managed instance, run by its creator | per-release records for cgm-remote-monitor 15.0.9; no per-release report in any device or connector repository | 219 human authors across 62 repositories in the year to 2026-09-30; cgm-remote-monitor 11–18 a year, 2021–2025 | [stack census](../../60-research/programme/stack-census-2026-09-30.md); [evidence §3, §4](../observations/ECOSYSTEM-EVIDENCE.md#3-releases-and-contributors-across-the-main-projects); collaboration rule 3 |
| Apache Software Foundation | not read | not read | companies employ committers but gain no control "irrespective of employing Committers … or sponsorship status" | not read | not read | [rules](#rules-other-organisations-use) |
| CNCF | events about two-thirds, membership 23.5% (2024) | services (events, infrastructure, audits); project engineers employed by members | certified conformance for vendor offerings against one upstream, and certified service providers | the same open-source conformance application for every offering, renewed yearly; over $3 million on security audits and tooling | 728 members (2024); over 90 certified offerings (2026-10-01) | [funding](#how-other-organisations-fund-and-staff-the-work); [rules](#rules-other-organisations-use) |
| Debian, with Freexian LTS | Debian pays none of its members; LTS funded by sponsors outside the project | LTS contributors, through Freexian | paid long-term support as a separate service with monthly public reports | not read | 1,000 voting developers (2006); 1,030 (2025) | [histories](#histories); histories annex §B, §E |
| Haskell Foundation | corporate sponsorship tiers; FY2024 revenue $136,256 | one director from 2024, none from mid-2026 | sponsors sit on an advisory board | not read | not read | [funding](#how-other-organisations-fund-and-staff-the-work) |
| Home Assistant / Open Home Foundation | partners contribute "a majority of its profit" from licensed products | "more than 50 full-time employees" | partners sell products and services under a published profit-share rule | not read | not read | [rules](#rules-other-organisations-use); [histories](#histories) |
| KernelCI | Linux Foundation members (from 2019) | not read | member-funded shared test lab | not read | not read | [histories](#histories) |
| OpenMRS | not read | a paid support team for community operations, support and QA | implementer organisations recognised at five levels; their staff "typically contribute 40–50%" of each release | not read | not read | [rules](#rules-other-organisations-use) |
| OpenSSL | about US$2,000 a year in donations before 2014; then funded roles | two developers full-time per role after 2014 | a foundation and a corporation as co-equal entities (2024) | written release, security and support policies; review of all code | two volunteer developers before 2014 | [histories](#histories) |
| OpenStreetMap Foundation | donations and memberships | paid development for gaps volunteers cannot fill | offers no commercial services and endorses no company | not read | not read | [funding](#how-other-organisations-fund-and-staff-the-work); [rules](#rules-other-organisations-use) |
| PSF Developers-in-Residence | a named sponsor per seat | four residents: triage, review, builds, security response | sponsors fund seats, not direction | not read | not read | [funding](#how-other-organisations-fund-and-staff-the-work) |
| SQLite | companies buying assurance: consortium, support, test runs, warranty of title | a small full-time team at Hwaci | assurance sold; control stays with the developers; free users get the same releases | a published quality management plan modelled on DO-178B; 100% MC/DC since 2009 | not read | [SQLite](#sqlite-paying-for-assurance-not-control); quality-system §3 |
| Tidepool Loop | not read | Tidepool's own team for the regulated track | FDA 510(k) K203689 (2023-01-23) alongside the continuing DIY project | the clearance and a community observational study | not read | [histories](#histories) |
| WHATWG / W3C | W3C: membership dues, FY2024 $8.71M | W3C: about 50 staff; WHATWG editors understood to be employed by browser vendors (not verified) | implementers decide; a feature needs two or more engines | shared tests across implementations | W3C 335+ members | [funding](#how-other-organisations-fund-and-staff-the-work) |
| Zig Software Foundation | donations, 100% contributions in FY2025 | one employee plus contractors; 92% of 2024 spending to contributors | none | not read | not read | [funding](#how-other-organisations-fund-and-staff-the-work) |
| curl | a company that sells curl support employs the lead; a project-held donation fund | the lead; named grant work | commercial support from the lead's employer; per-report bug bounty ended | not read | not read | [histories](#histories) |

## What the table shows

- **No precedent matches on size and stakes together.** Debian has about five times as many voting
  developers (1,030) as the ecosystem had human authors in a year (219); CNCF and W3C count
  organisations as members (728 and 335+), each employing engineers. None of them carries clinical
  outcomes. Their structures transfer; their funding scale does
  not.
- **Every organisation that pays people keeps technical authority with the maintainers**, whether
  the money comes from donors (Zig, OpenStreetMap), sponsors (PSF), members (CNCF) or customers
  (SQLite, curl).
- **Commercial support adds to the commons where the codebase stays single.** SQLite sells
  assurance on the same releases free users get; CNCF certifies commercial offerings against the
  same upstream with the same public tests; Debian keeps paid support outside the project and
  reports it monthly. The collaboration model's rules 2, 5 and 8 draw on these.
- **Regulated and DIY tracks can coexist** when each carries its own label (Tidepool Loop).

## Rules other organisations use

Read from each organisation's own page on 2026-09-29 unless the row gives another date. The
[collaboration model §5](../COLLABORATION-MODEL.md#5-proposed-rules-for-working-together) borrows each of its rules from one of these.

| organisation | the rule it uses | source |
|---|---|---|
| Apache Software Foundation | "Apache projects must govern themselves independently of undue commercial influence." No organisation gains control "irrespective of employing Committers … or sponsorship status." The board "does not provide technical direction." | [how it works](https://www.apache.org/foundation/how-it-works/), [the Apache way](https://www.apache.org/theapacheway/), [PMCs](https://www.apache.org/foundation/governance/pmcs.html) |
| Apache | Discussion can happen anywhere, but decisions "should be taken back to the mailing list … If it didn't happen on the mailing list, it didn't happen." | [mailing lists](https://community.apache.org/contributors/mailing-lists) |
| Apache | The Incubator "doesn't fear … internal confrontation between projects which overlap in functionality." | [how it works](https://www.apache.org/foundation/how-it-works/) |
| CNCF | Project websites list support companies "in alphabetical order, or the order can be changed randomly"; "the origin company should not be favored over any other companies offering the same services." | [website guidelines](https://github.com/cncf/foundation/blob/main/policies-guidance/website-guidelines.md) |
| CNCF | Four maturity levels (Sandbox, Incubation, Graduated, Archived). Graduation asks for maintainers from at least two organisations, a code of conduct and a third-party security review. Projects with maintainers from several organisations at entry graduated at 2.07 times the rate of single-organisation projects (59.1% against 28.6%, 72 projects). | [TOC process](https://github.com/cncf/toc/blob/main/process/README.md), [graduation template](https://github.com/cncf/toc/blob/main/.github/ISSUE_TEMPLATE/template-graduation-application.md), [governance guidance, 2026-08-26](https://www.cncf.io/blog/2026/08/26/governance-guidance-for-cncf-projects-choosing-the-right-structure-for-your-projects-size-and-stage/) |
| CNCF | Commercial offerings are certified against one upstream: "every vendor's version of Kubernetes supports the required APIs", using "the identical open source conformance application" that any end user can run; results go to a public GitHub repository and must be renewed at least yearly; "over 90 Certified Kubernetes offerings". Certified service providers must be CNCF members with three or more certified engineers. Read 2026-10-01. | [conformance](https://www.cncf.io/training/certification/software-conformance/), [KCSP](https://www.cncf.io/training/certification/kcsp/) |
| CNCF | More than $3 million "over the past few years" on security audits and tooling. | [2025 annual report](https://www.cncf.io/wp-content/uploads/2026/03/cncf_ar25_033126a.pdf) |
| Open Home Foundation (Home Assistant) | A nonprofit owns the projects; commercial partners sell products and services and are "contractually required to contribute a majority of its profit from selling licensed products." In 2025 the staff working on foundation projects moved to the foundation. | [structure](https://www.openhomefoundation.org/structure/), [second partner, 2025-12-17](https://newsletter.openhomefoundation.org/meet-our-new-partner-apollo-automation/) |
| OpenStreetMap Foundation | Responsible "for needs that require an organization, and gaps that can not be filled by OSM's volunteer driven community." "Given that volunteer work has not proven to be sufficient in the past, support through paid development is necessary." It offers no commercial services and endorses no company. | [mission](https://osmfoundation.org/wiki/Mission_Statement), [strategic plan](https://osmfoundation.org/wiki/Strategic_Plan), [FAQ](https://osmfoundation.org/wiki/FAQ) |
| OpenMRS (clinical records, 501(c)(3)) | Organisations are recognised at five published levels, from Implementer to Transformative Leader. Staff of implementer organisations "typically contribute 40–50% of all updates in each OpenMRS release." A paid support team handles community operations, product support and QA. | [partners](https://openmrs.org/our-partners/), [get involved](https://openmrs.org/get-involved/), [about](https://openmrs.org/about/) |
| openEHR | Specifications have published states (Planning, Development, Trial, Stable, Paused, Retired). Anyone can raise a problem report; "No change can be made to the specifications without a CR." Conformance profiles are in development. | [change process](https://specifications.openehr.org/governance/change_process), [conformance](https://specifications.openehr.org/releases/CNF/development) |
| OHDSI | A common data model with federated analysis: "data remains at the site behind a firewall. No patient-level data pooling occurs … Only aggregate results are shared." | [Book of OHDSI, ch. 20](https://ohdsi.github.io/TheBookOfOhdsi/NetworkResearch.html) |

## SQLite: paying for assurance, not control

SQLite is public domain, free to anyone, and built into phones, browsers and aircraft ("Airbus
confirms that SQLite is being used in the flight software for the A350 XWB family"). Its developers
are employed by one small company, Hwaci, and paid from what companies with their own quality and
legal obligations buy. Read from sqlite.org on 2026-09-29:

| what is sold | what the buyer gets | source |
|---|---|---|
| consortium membership, $150K a year on the support page ($120,000 on the member page) | 23 staff-days a year, bug fixes back-ported to any version "no matter how old", regression tests run in the member's own configuration | [consortium](https://sqlite.org/consortium.html), [support](https://sqlite.org/prosupport.html) |
| technical support, $8K to $85K a year | priority support for versions up to a year old | [support](https://sqlite.org/prosupport.html) |
| test runs on the customer's hardware and build options | evidence for the customer's own quality system; the test harness was built to support the avionics standard DO-178B, and every release since 2009 meets 100% MC/DC coverage | [support](https://sqlite.org/prosupport.html), [TH3](https://sqlite.org/th3.html) |
| a "warranty of title", $6,000 once | indemnity for legal departments; "all proceeds … are used to fund continuing improvement and support of SQLite" | [copyright](https://sqlite.org/copyright.html) |

What stays constant across every tier: "technical control and direction of SQLite remains with the
SQLite architect and developers … [it] does not fall under the governance of any single company"
([consortium](https://sqlite.org/consortium.html)). Free users get the same releases, tested the
same way. The developers publish a [quality management plan](https://sqlite.org/qmplan.html)
modelled on DO-178B, and they "plan as if we will be supporting SQLite until 2050"
([long-term support](https://sqlite.org/lts.html)).

- **Check before quoting:** SQLite's own pages disagree on prices (above), and the site makes no
  medical-device quality claim; "medical devices" appears only as an example of where SQLite fits
  ([when to use](https://sqlite.org/whentouse.html)).

## How other organisations fund and staff the work

Gathered 2026-09-27 from each organisation's own pages and IRS Form 990 summaries on ProPublica.
Figures are for the year shown. Re-check each against its source before quoting it.

| organisation | how money comes in | who is paid, to do what | who decides | what it suggests for us |
|---|---|---|---|---|
| [Zig Software Foundation](https://ziglang.org/zsf/) (US 501(c)(3), 2020) | donations almost entirely: FY2025 revenue $921,832, 100% contributions ([990](https://projects.propublica.org/nonprofits/organizations/845105214)); 2024 income $670,673 from GitHub Sponsors and a few large donors ([2024 report](https://ziglang.org/news/2025-financials/)) | one fulltime employee plus hourly contractors; of $520,749 spent in 2024, $306,362 went to contractors and $154,263 to the employee, "92% of our money in 2024 paying contributors" in the report's words ([2024 report](https://ziglang.org/news/2025-financials/)) | a three-person board; no published technical governance document | the closest match: small, lean, nearly all money goes to code. It rests on one lead and a few large donors |
| [Haskell Foundation](https://haskell.foundation/) (2020; funds held through Haskell.org, Inc., a 501(c)(3); [merger announced 2024](https://blog.haskell.org/haskell-foundation-and-committee-merger/), completion not verified) | corporate sponsorship tiers from $15k to $100k+ a year; sponsors sit on an advisory board ([donations](https://haskell.foundation/donations/)); Haskell.org, Inc. FY2024 revenue $136,256 ([990](https://projects.propublica.org/nonprofits/organizations/475236502)) | one executive director from 2024; a DevOps role restructured after a 2024 shortfall ([post](https://discourse.haskell.org/t/devops-at-the-haskell-foundation/9654)); from mid-2026 no director and a volunteer technical committee directing most spending ([2026 update](https://discourse.haskell.org/t/haskell-foundation-2026-update/14136)) | a 12-member board; existing technical committees keep their authority | sponsor income did not reliably cover a director plus an engineer; fund engineering first, administration second |
| [CNCF](https://www.cncf.io/) (a directed fund of the Linux Foundation, a 501(c)(6), 2015) | 2024: events about two-thirds, membership 23.5%, training 7.5%; 728 members ([annual report 2024, p. 26](https://www.cncf.io/wp-content/uploads/2025/04/CNCF-Annual-Report-2024_v2.pdf)); dues up to $350k a year ([join](https://www.cncf.io/about/join/)) | pays for services (events, infrastructure, security audits, mentoring), not core developers; project engineers are employed by member companies. Commercial support grows around one upstream: "every vendor's version of Kubernetes supports the required APIs", checked by "the identical open source conformance application" any user can run, renewed yearly, over 90 certified offerings ([conformance](https://www.cncf.io/training/certification/software-conformance/)); certified service providers are CNCF members with three or more certified engineers ([KCSP](https://www.cncf.io/training/certification/kcsp/)), both read 2026-10-01 | a governing board sets budget; a technical oversight committee admits projects and tracks their maturity; projects keep their own governance ([charter](https://github.com/cncf/foundation/blob/main/charter.md) §9(c)) | its scale of membership does not transfer. What does: companies sell support for one open codebase and prove conformance with the same public tests everyone runs, so commercial support adds to the commons instead of forking it ([collaboration model](../COLLABORATION-MODEL.md) rules 5 and 8) |
| [WHATWG](https://whatwg.org/faq) (2004; steering group since 2017) | no published budget | editors work on the standards; they are understood to be employed by browser vendors (not verified) | a steering group of organisations that build a major browser engine ([agreement](https://whatwg.org/sg-agreement)); a feature needs two or more engines | authority follows the people who implement. Our equivalent is the app builders whose clients depend on the server |
| [W3C](https://www.w3.org/about/) (US 501(c)(3) since 2023) | mainly membership dues: FY2024 revenue $8.71M ([990](https://projects.propublica.org/nonprofits/organizations/844023862)); 335+ members | about 50 staff who coordinate and edit; members' employees do the technical work | a board, an advisory board, a technical architecture group; working groups decide by consensus | stable staff funding, but the overhead suits many paying members, not a small community |
| [PSF Developers-in-Residence](https://www.python.org/psf/developersinresidence/) (Python) | each seat paid for by a named sponsor; the first began in July 2021 ([announcement](https://pyfound.blogspot.com/2021/07/ukasz-langa-is-inaugural-cpython.html)) | four residents today; the work is triage, reviews, build monitoring and security response in support of the volunteer core team | the core developers and their elected steering council | the nearest model to the sponsored-team proposal's §4 roles: paid people doing the review and release work volunteers find hardest to sustain. Each seat lasts only as long as its sponsor |
| [Sovereign Tech Fellowship](https://www.sovereign.tech/programs/fellowship) (German federal funding) | public money, competitive | up to 12 fellows, freelance or employed (up to three two-year posts at €64k–€82k a year), working on their own projects | the fellows' own projects | a possible grant source for option C; it supplements a plan, it cannot anchor one |
| [OpenStreetMap Foundation](https://osmfoundation.org/wiki/Strategic_Plan) | donations and memberships | "Given that volunteer work has not proven to be sufficient in the past, support through paid development is necessary" for the core software ([strategic plan](https://osmfoundation.org/wiki/Strategic_Plan)); its scope is "needs that require an organization, and gaps that can not be filled by OSM's volunteer driven community" ([mission](https://osmfoundation.org/wiki/Mission_Statement)) | an elected board; it offers no commercial services and endorses no company | the same reasoning as the sponsored-team proposal's §3: pay for the gaps volunteers cannot fill, and stay neutral among the companies that build on the commons |
| [SQLite](https://sqlite.org/consortium.html) (public domain; developers employed by Hwaci) | companies buy assurance: consortium membership ($150K a year on the [support page](https://sqlite.org/prosupport.html)), support contracts, test runs in the customer's configuration | a small fulltime team; every release is tested to 100% MC/DC coverage ([TH3](https://sqlite.org/th3.html)) | "technical control and direction of SQLite remains with the SQLite architect and developers" | companies with their own quality and legal obligations will pay for evidence, fixes on the line they run and a support horizon, not for control. Its closed-contribution policy does not fit a community project ([SQLite, below](#sqlite-paying-for-assurance-not-control)) |

## Histories

Each row is sourced in the [histories annex §B](../../60-research/programme/stack-census-2026-09-30/histories.md#b-histories).

| history | the situation | what changed | what maps here |
|---|---|---|---|
| OpenSSL after Heartbleed (2014) | about US$2,000 a year in donations; two volunteer developers | two developers funded full-time per role, then written release, security and support policies, and review of all code; in 2024 a foundation and a corporation as co-equal entities | money turned into a working project through named roles plus written policies, not money alone |
| xz-utils (2024) | an "unpaid hobby project" with one maintainer | CISA: "the burden of security shouldn't fall on an individual open source maintainer"; OpenSSF: support for maintainers is "the primary deterrent" | reproducible release artefacts; maintainer rights earned through trust, with review by a second person |
| curl | one lead, employed by a company that sells curl support | a project-held donation fund spent on named work; time-boxed public grants whose scope the project wrote; a bug bounty ended when paying per report drew noise | the closest match to one commercial host paying a maintainer; add a project-held fund and public grants |
| Debian and Freexian LTS | a volunteer project that pays none of its own members; 1,030 voting developers in April 2025 ([vote 2025/001](https://www.debian.org/vote/2025/vote_001)) | paid long-term support run as a separate service, funded outside the project, with monthly public reports | paid work the volunteer project accepts: separate, outside its governance, reported |
| Debian's Dunc-Tank (2006) | a plan to pay two release managers for a month each, organised with the project leader, in a project of 1,000 voting developers ([vote 2006/006](https://www.debian.org/vote/2006/vote_006)) | the project said it "does not object" but the experiment was not its decision; the lesson drawn in 2019 was "don't let the DPL decide alone who gets paid" | never let one person decide who is paid |
| Home Assistant / Open Home Foundation | a founder-linked company paid the maintainers for years | a foundation with a published profit-share rule for partners, supporting "more than 50 full-time employees"; staff moved to the foundation in 2025 | the closest structural match to Nightscout; it took six years to formalise |
| KernelCI | a spare-time test lab from 2014 | a member-funded Linux Foundation project from 2019 | pooled device and connector labs |
| ELISA and Zephyr | open source used where safety evidence is needed | shared tools so a company can certify its own system; a limited certification scope; rules brought in by stages | two labels: the project provides evidence; any certification is the certifier's |
| Tidepool Loop (FDA 510(k) K203689, 2023-01-23) | DIY Loop, built by volunteers | a nonprofit took it through clearance with its own paid team and a community observational study; the DIY project continued alongside | regulated and DIY tracks coexist, each with its own label |

## Claims about these organisations that the sources do not support

Read 2026-10-02. They circulate in summaries of these organisations; do not cite them without a
source.

| claim | what the source says |
|---|---|
| the Open Home Foundation says its salaried staff give volunteers "more room to make creative contributions" | not found on its [structure](https://www.openhomefoundation.org/structure/), [about](https://www.openhomefoundation.org/about/) or announcement pages |
| the OSMF hiring rules separate "paid execution" from "paid authority" | a paraphrase. The [Hiring Framework](https://osmfoundation.org/wiki/Hiring_Framework) says the foundation wants "to avoid paid leadership or decision-making positions" |
| OSMF listed "dependence on paid capacity" among the risks of hiring | not in the [2020 osmf-talk post](https://lists.openstreetmap.org/pipermail/osmf-talk/2020-May/006816.html) that lists the risks |
| a CNCF "report" found multi-organisation projects reach higher maturity | the source is a [CNCF blog post of 2026-08-26](https://www.cncf.io/blog/2026/08/26/governance-guidance-for-cncf-projects-choosing-the-right-structure-for-your-projects-size-and-stage/) drawing on governance reviews of 72 projects; the 2.07× figure is the *graduation* rate of projects with maintainers from several organisations at sandbox entry (59.1% against 28.6%) |
| Apache: "if it didn't happen on the mailing list, it didn't happen" | the [Incubator committer guide](https://incubator.apache.org/guides/committer.html) says "If it isn't on the mailing list, it didn't happen." |

OpenMRS's "typically contribute 40–50% of all updates in each OpenMRS release" is on its
[get involved](https://openmrs.org/get-involved/) page (read 2026-10-02), and is supported.
