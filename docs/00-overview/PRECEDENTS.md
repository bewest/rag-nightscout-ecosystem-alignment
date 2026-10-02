# Precedents the overview proposals cite

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
Living page, written 2026-10-01 against this repository at `1644125b`. One table of every
organisation that the [sponsored-team](SPONSORED-TEAM-PROPOSAL.md),
[collaboration](COLLABORATION-MODEL.md) and [quality-system](QUALITY-SYSTEM.md) proposals cite. Each
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
| **Nightscout ecosystem** | donations to the foundation (amounts not read); commercial hosts pay part of the time of the maintainers who work for them | no shared, published paid role | eight hosted providers listed in the docs; a second server lists one managed instance, run by its creator | per-release records for cgm-remote-monitor 15.0.9; no per-release report in any device or connector repository | 219 human authors across 62 repositories in the year to 2026-09-30; cgm-remote-monitor 11–18 a year, 2021–2025 | [stack census](../60-research/programme/stack-census-2026-09-30.md); sponsored-team §2, §3; collaboration rule 3 |
| Apache Software Foundation | not read | not read | companies employ committers but gain no control "irrespective of employing Committers … or sponsorship status" | not read | not read | collaboration §4 |
| CNCF | events about two-thirds, membership 23.5% (2024) | services (events, infrastructure, audits); project engineers employed by members | certified conformance for vendor offerings against one upstream, and certified service providers | the same open-source conformance application for every offering, renewed yearly; over $3 million on security audits and tooling | 728 members (2024); over 90 certified offerings (2026-10-01) | sponsored-team §6; collaboration §4 |
| Debian, with Freexian LTS | Debian pays none of its members; LTS funded by sponsors outside the project | LTS contributors, through Freexian | paid long-term support as a separate service with monthly public reports | not read | 1,000 voting developers (2006); 1,030 (2025) | quality-system §7; histories annex §B, §E |
| Haskell Foundation | corporate sponsorship tiers; FY2024 revenue $136,256 | one director from 2024, none from mid-2026 | sponsors sit on an advisory board | not read | not read | sponsored-team §6 |
| Home Assistant / Open Home Foundation | partners contribute "a majority of its profit" from licensed products | "more than 50 full-time employees" | partners sell products and services under a published profit-share rule | not read | not read | collaboration §4; quality-system §7 |
| KernelCI | Linux Foundation members (from 2019) | not read | member-funded shared test lab | not read | not read | quality-system §7 |
| OpenMRS | not read | a paid support team for community operations, support and QA | implementer organisations recognised at five levels; their staff "typically contribute 40–50%" of each release | not read | not read | collaboration §4 |
| OpenSSL | about US$2,000 a year in donations before 2014; then funded roles | two developers full-time per role after 2014 | a foundation and a corporation as co-equal entities (2024) | written release, security and support policies; review of all code | two volunteer developers before 2014 | quality-system §7 |
| OpenStreetMap Foundation | donations and memberships | paid development for gaps volunteers cannot fill | offers no commercial services and endorses no company | not read | not read | sponsored-team §6; collaboration §4 |
| PSF Developers-in-Residence | a named sponsor per seat | four residents: triage, review, builds, security response | sponsors fund seats, not direction | not read | not read | sponsored-team §6 |
| SQLite | companies buying assurance: consortium, support, test runs, warranty of title | a small full-time team at Hwaci | assurance sold; control stays with the developers; free users get the same releases | a published quality management plan modelled on DO-178B; 100% MC/DC since 2009 | not read | collaboration §4a; quality-system §3 |
| Tidepool Loop | not read | Tidepool's own team for the regulated track | FDA 510(k) K203689 (2023-01-23) alongside the continuing DIY project | the clearance and a community observational study | not read | quality-system §7 |
| WHATWG / W3C | W3C: membership dues, FY2024 $8.71M | W3C: about 50 staff; WHATWG editors understood to be employed by browser vendors (not verified) | implementers decide; a feature needs two or more engines | shared tests across implementations | W3C 335+ members | sponsored-team §6 |
| Zig Software Foundation | donations, 100% contributions in FY2025 | one employee plus contractors; 92% of 2024 spending to contributors | none | not read | not read | sponsored-team §6 |
| curl | a company that sells curl support employs the lead; a project-held donation fund | the lead; named grant work | commercial support from the lead's employer; per-report bug bounty ended | not read | not read | quality-system §7 |

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
