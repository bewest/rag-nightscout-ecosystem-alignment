# A sponsored maintenance team for the Nightscout ecosystem — proposal

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**DRAFT PROPOSAL for discussion.** Written 2026-09-27 against this repository at `de46efc1` and
cgm-remote-monitor `official/dev` `295f1177`; figures re-measured against this repository at `55926206`
and `official/dev` `7000eb18` (the merge of #8786) the same day. Added 2026-09-29: the cross-project
release and contributor figures and the dated-work paragraph in §2, the OpenStreetMap and SQLite rows
in §6, and the vendor-change table in §6a. Added 2026-09-30: §1a, with the published clinical evidence
and the case for a research commons. Where it touches employment, contracting, tax or
the foundation's exempt status, it needs review by the foundation's counsel and accountant before
any decision rests on it (§9). Nothing here is decided.*

*Author's interests: the author maintains cgm-remote-monitor, founded a company that hosts
Nightscout commercially, and could be a candidate for paid work under this proposal. The
[collaboration rules](COLLABORATION-MODEL.md) §5 would apply to that company and to the author like
anyone else.*

## 1. The request

Fund a small, fulltime, paid team whose job is to keep the Nightscout ecosystem's shared software
reviewed, released and working with the apps that depend on it. The team works alongside the
volunteer maintainers and contributors, answers to the foundation for the time it is paid for, and
takes no authority away from any project.

Long-standing maintainers of the ecosystem projects have asked the foundation for this.
**[To confirm before this is shared: whether the maintainers who made the request agree to be named
here.]**

## 1a. What is at stake

**Open-source AID has published evidence behind it.** Abstracts read on PubMed, 2026-09-30:

| study | design | what it found | caveats the authors state or the design implies |
|---|---|---|---|
| CREATE ([Burnside et al., NEJM 2022;387:869–881](https://www.nejm.org/doi/full/10.1056/NEJMoa2203913)) | randomised controlled trial, 97 children and adults, 24 weeks; AndroidAPS 2.8 with the OpenAPS 0.7.0 algorithm against a sensor-augmented pump | time in range rose from 61.2% to 71.2% with AID and fell from 57.7% to 54.5% in the control group (adjusted difference 14 percentage points, 95% CI 9.2–18.8); no severe hypoglycaemia or DKA in either group | the comparator was a pump without automation, not a commercial AID system; two AID participants withdrew because of connectivity issues |
| Loop observational study ([Lum et al., Diabetes Technol Ther 2021;23:367–375](https://pubmed.ncbi.nlm.nih.gov/33226840/)) | prospective, real-world, 558 adults and children, 6 months | time in range rose from 67% to 73%; time below 54 mg/dL fell slightly | people who chose to start Loop themselves; no control group |
| Canadian comparison ([Wu et al., Diabetes Technol Ther 2025;27:517–526](https://pubmed.ncbi.nlm.nih.gov/40100927/)) | prospective, observational non-inferiority study, 26 open-source and 52 commercial AID users, 12 weeks | open-source non-inferior on 24-hour time in range (78.3% against 71.2%) | open-source users spent more time below 3.9 mmol/L (3.9% against 1.8%, "yet within the recommended range"); not randomised |
| Systematic review ([Knoll et al., Diabet Med 2022;39:e14741](https://pubmed.ncbi.nlm.nih.gov/34773301/)) | 21 real-world studies, 2018–2021 | improvements "observed in open-source and commercially developed AID systems alike" | real-world studies; most were of one commercial system |

So the evidence shows that open-source AID beat pump therapy in a randomised trial, and that in
real-world comparisons it matches or exceeds commercial systems on time in range, with differences
in time below range that matter for some people. No randomised head-to-head trial against commercial
AID systems has been published among the studies read here. The people in the real-world studies
chose these systems themselves, and the authors of one comparison describe them as "a very selected
group of people" ([Journal of Diabetes Science and Technology,
2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11571566/)).

**The assets grew in the open, over more than ten years.** #WeAreNotWaiting dates from 2013 and
OpenAPS from February 2015. On 2026-09-30 the [stack census](../60-research/programme/stack-census-2026-09-30.md)
counted 63 repositories, from device drivers to vendor-cloud connectors, with 219 distinct human authors committing
in the last year. 13 of the 63 are held under personal GitHub accounts, and most of the rest sit in
GitHub organisations run by volunteers. A foundation taking stewardship responsibility for these
assets is how the software behind that evidence keeps working, and how new evidence can be built on
it.

**Today the cost falls on people with diabetes and individual maintainers.** Their own time pays for
the review, releases, vendor changes and security response of §3. After the xz-utils backdoor in
2024, CISA wrote that "the burden of security shouldn't fall on an individual open source
maintainer" ([QUALITY-SYSTEM §7](QUALITY-SYSTEM.md#7-histories-that-map)). Full-time stewards
funded by the foundation would move that cost off the people the software serves.

**Better evidence needs a shared commons.** Which system does better, for whom and in which
circumstances (children, pregnancy, exercise, different pumps and sensors, different settings) is
the question the studies above cannot yet answer. The
[Nightscout datalake proposal](https://bewest.github.io/ns-data-proposal/) is the route to that
evidence. It proposes consented data from many sites, governed research extracts, and a
methods-review step before any clinical claim is published. Its current pilot outputs are a
data-quality report, a release-comparison report and extracts for two or three researchers.
Its research agenda lists comparative outcome studies across systems as a later use of the same
commons, with what a comparison needs before it is published: a registered protocol, a design that
accounts for who chooses which system, aggregate results only, and review by the maintainers of each
system compared. The OHDSI network's rule (data stays at each site; only aggregate results are shared,
[COLLABORATION-MODEL §4](COLLABORATION-MODEL.md#4-what-other-open-source-organisations-do)) is one
tested model. The team in §4 keeps the software and records such studies rely on; it does not run
the studies or make clinical claims.

## 2. Why now

**The ecosystem depends on one shared server.** Nightscout is a secondary display for CGM and pump
data, and it is also the place where many other apps read and write that data. The 15.0.9 client
survey mapped 40 client repositories against 15 parts of the API
([consumer impact](../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md)). Loop, Trio,
AndroidAPS, xDrip+, caregiver apps, watch faces and reporting tools all rely on how the server
actually behaves. A change there reaches every one of them.

**Releases have come in long gaps, here and across the ecosystem.** The other main projects have had
gaps of the same length in the same years, and in cgm-remote-monitor the contributors left before
releases slowed (both below). Tag dates in cgm-remote-monitor (`git tag --sort=creatordate`):

| release | tagged | days since the previous release |
|---|---|---:|
| 14.2.6 | 2022-09-30 | 295 |
| 15.0.0 | 2023-10-18 | 383 |
| 15.0.2 | 2023-10-25 | 5 |
| 15.0.3 | 2025-05-08 | 561 |
| 15.0.4 | 2026-02-28 | 296 |
| 15.0.7 | 2026-04-29 | 57 (15.0.5 and 15.0.6 in between) |
| 15.0.8 | 2026-09-04 | 128 |
| 15.0.9 | candidate `3014f883` (2026-09-30), not tagged | — |

**Important work can wait for years.** The MongoDB 5 driver upgrade was first proposed in #7344,
opened 2022-02-16. The upgrade that shipped was #8421: opened 2026-01-19, merged 2026-03-16, released
in 15.0.7 on 2026-04-29 (`mongodb` `^3.6.0` → `^5.9.2`). #7344 was closed as superseded on
2026-05-01. Hosting providers retire old database versions on their own schedule, so a site's
database driver is not optional maintenance.

**The same long waits appear across the ecosystem.** Longest gaps between stable GitHub releases in
the main projects (`gh api repos/<owner>/<repo>/releases`, measured 2026-09-29):

| project | longest gaps between stable releases | recent releases |
|---|---|---|
| cgm-remote-monitor | 383 days (2022–23), 561 (2023–25), 296 (2025–26), from the tag table above | 5 in 2026 |
| AndroidAPS | 443 days (Aug 2022–Oct 2023), 306 (Feb–Dec 2024) | 6 in 2025, 8 in 2026 |
| Loop | 323 days (2020–21), 284 (2022–23), 297 (2023–24) | 15 since April 2025, now published from LoopWorkspace |
| Trio | 255 days (Aug 2025–Apr 2026) | 8 in 2026, including 1.0 |
| xDrip+ | 422 days (2019–20), 234 (2024–25) | pre-release builds at least every 45 days since 2016 |
| oref0 | 951 days (2019–22); none since v0.7.1 in June 2022 | its algorithm is now maintained inside AndroidAPS and Trio |

Commits / distinct author emails per year (all branches, merge commits and bots excluded, from this
workspace's clones fetched 2026-09-09 to 2026-09-23, so 2026 is partial; Loop is the Loop app plus
LoopKit; Trio is left out because its history before 2024 is FreeAPS X's):

| project | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cgm-remote-monitor | 440/49 | 310/47 | 193/34 | 220/18 | 67/14 | 169/16 | 50/11 | 115/13 | 1050/27 |
| AndroidAPS | 1993/50 | 1465/42 | 1653/42 | 2041/32 | 1531/34 | 1563/36 | 566/24 | 916/33 | 2944/28 |
| Loop + LoopKit | 114/6 | 275/16 | 757/21 | 327/8 | 360/25 | 516/25 | 425/12 | 442/17 | 324/13 |
| xDrip+ | 1217/28 | 832/18 | 402/17 | 791/23 | 832/17 | 640/16 | 480/13 | 408/19 | 521/16 |

In cgm-remote-monitor the number of people committing fell first, from 47 in 2019 to 18 in 2021 and
11 in 2024; the years of one release a year followed. AndroidAPS's lowest year, 2024, is also the
year of its 306-day gap. Loop's commits held steady through its gaps, which suggests its waits were
on testing and release rather than on code. The 2026 cgm-remote-monitor figure includes
agent-written commits (§3).

Dates do not show causes. Several gaps coincide with large rewrites and with Apple and Google
platform changes. xDrip+ could not be built with current Android tools from September 2019 to
December 2020 ([#1012](https://github.com/NightscoutFoundation/xDrip/issues/1012)), because of
toolchain changes the project did not control. What the record shows is that every main project has
had the same long waits, and that most of them released more often in 2025–26 as capacity returned.
A gap in one project's history, read on its own, says little about the diligence of the people who
maintain it. Set beside the others and the contributor counts, it reads as the same work carried by
fewer people. Each project's maintainers are the right people to say what held their releases (§9).

**Much of the coming work is already dated.** Between now and the end of 2027 the ecosystem meets
Apple's medical-device status declaration (early 2027) and Xcode 27 upload requirement (April 2027),
Android developer verification for all installations (2027), Node 22 and Heroku-22 end of life on
the same day (2027-04-30), and MongoDB 7.0 end of life (2027-08-31), each on the vendor's calendar,
not a volunteer's ([collaboration model §3](COLLABORATION-MODEL.md#3-needs-we-can-predict)).

**2026 shows what steady attention produces.** Five releases so far this year. For 15.0.9 alone
([quality record](../60-research/programme/paving-the-cowpaths-2026-09-27.md), measured on `295f1177`): 85 pull requests
merged in 23 days, 146 defects filed and 87 of the 122 in scope closed, and the full test suite grown
from 1,533 passing tests on 15.0.8 to 3,473 on `295f1177`. The candidate `7000eb18` adds one more
(#8786, BF-147); its CI passed 3,478 tests in all nine cells. Before any release is tagged, 19
integration runs, a comparison soak against 15.0.8, browser checks against a simulated household and
a census of client behaviour were all completed.

## 3. Where the time goes

Much of the engineering in 2026 was done with AI coding agents under a maintainer's direction. That
changed what limits progress. Writing a fix is now the cheap part. The steps that still need a
person are the ones this proposal would fund:

| work that needs a person | measured 2026-09-27 |
|---|---|
| review | 144 of the 172 items in the work queue route review to the maintainer; 75 of them are not yet merged or closed (`queue/work-queue.yaml`, `review` field) |
| specialist review | 21 items ask for a security or safety reviewer; 14 are open, most of them in the multitenancy and alarm work. The queue names the kind of reviewer, not a person |
| decisions | 7 items wait on a decision (`needs-decision`), plus the release decisions themselves ([needs a human](NEEDS-A-HUMAN.md)) |
| hand checks | the 15.0.9 browser walk was done by the maintainer; six checks are still owed before the tag ([contents](../../releases/cgm-remote-monitor-15.0.9/contents.md#open-items-a-releaser-must-settle)) |
| checks on real systems | no real Loop, Trio, AndroidAPS or xDrip+ setup has yet run against the 15.0.9 candidate |
| dependency alerts | 80 Dependabot alerts are open against `master`, the last release; 74 of them are already fixed on `dev` and close only when a release ships (measured on `dev` `7000eb18`). 38 merges since 15.0.7 changed the lockfile, 20 of them Dependabot's. Each remaining finding needs a person to establish whether Nightscout reaches it: the 15.0.9 triage took 17 findings to 7, and the modernization line to 0 ([triage](../../releases/cgm-remote-monitor-15.0.9/contents.md#npm-audit-and-dependabot-triage)) |
| backlog | 35 open pull requests (18 opened in 2026, the oldest in 2021) and 102 open issues in cgm-remote-monitor (`gh pr list`, `gh issue list`, 2026-09-27) |

Today all of this depends on the unpaid time of a few people. When their time runs short, the work
waits.

## 4. What the team would do

A starting shape. The board and maintainers would settle the final one.

| role | what it does | why it is needed |
|---|---|---|
| **Release and review lead** | reviews pull requests, keeps the release process running on a published schedule, tags releases with the maintainers | review and release are where work waits (§3) |
| **Ecosystem compatibility engineer** | keeps the census of client apps current; runs the real-system checks with Loop, Trio, AndroidAPS and xDrip+ builders; turns what clients actually send into tests; watches the vendor clouds the connectors log into and keeps a connector test lab that any server can use | a server change reaches every client (§2), and a vendor change reaches every server (§6a) |
| **Quality and security lead** (part time at first) | triages security reports and dependency alerts, keeps the defect register and test records, is the named reviewer for security and safety items | 21 items ask for a kind of reviewer no one is assigned to be |

Beyond cgm-remote-monitor, the [stack census](../60-research/programme/stack-census-2026-09-30.md)
estimates a shared quality kit for the device drivers and vendor-cloud connectors at 167–388
person-weeks one-time and 0.4–0.7 of a full-time engineer after that (estimates, with their
assumptions). The [quality-system proposal](QUALITY-SYSTEM.md) sets out what that kit contains and
which parts volunteers can do alone.

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
| [OpenStreetMap Foundation](https://osmfoundation.org/wiki/Strategic_Plan) | donations and memberships | "Given that volunteer work has not proven to be sufficient in the past, support through paid development is necessary" for the core software ([strategic plan](https://osmfoundation.org/wiki/Strategic_Plan)); its scope is "needs that require an organization, and gaps that can not be filled by OSM's volunteer driven community" ([mission](https://osmfoundation.org/wiki/Mission_Statement)) | an elected board; it offers no commercial services and endorses no company | the same reasoning as §3: pay for the gaps volunteers cannot fill, and stay neutral among the companies that build on the commons |
| [SQLite](https://sqlite.org/consortium.html) (public domain; developers employed by Hwaci) | companies buy assurance: consortium membership ($150K a year on the [support page](https://sqlite.org/prosupport.html)), support contracts, test runs in the customer's configuration | a small fulltime team; every release is tested to 100% MC/DC coverage ([TH3](https://sqlite.org/th3.html)) | "technical control and direction of SQLite remains with the SQLite architect and developers" | companies with their own quality and legal obligations will pay for evidence, fixes on the line they run and a support horizon, not for control. Its closed-contribution policy does not fit a community project ([collaboration model §4a](COLLABORATION-MODEL.md#4a-sqlite-paying-for-assurance-not-control)) |

What they have in common:

- Where paid staff exist, the volunteer or project maintainers keep technical authority.
- Money tied to one sponsor or a few donors is the usual weak point.
- The smallest organisations that pay for code (Zig, the PSF residencies) spend almost all of it on
  engineering work and very little on administration.
- Companies that build on the commons pay for work and assurance, not for control (OpenStreetMap,
  SQLite). The rules that would keep it so here are in [COLLABORATION-MODEL](COLLABORATION-MODEL.md) §5.

## 6a. More than one server

Nightscout is no longer the only server that speaks its API. Nocturne
([`nightscout/nocturne`](https://github.com/nightscout/nocturne)) is a second implementation, in
.NET with PostgreSQL. xDrip+ ships an uploader for it
([adoption roadmap](../30-design/nightscout-adoption-roadmap-2026-09-11.md)). Its typed event model
has been used as a reference in this repository's own data-model work
([primitive coverage](../30-design/platform/nightscout-primitive-coverage-2026-09-11.md)).
Its web interface is its own design, with its own visual language, not a copy of Nightscout's
real-time display, so for operators it is an alternative, and choosing it is each operator's decision.

A second server makes this proposal more necessary, not less:

- **Client apps depend on behaviour, not on which server provides it.** On 2026-09-23 Nocturne
  (`42275c81`, v0.2.x) matched the 15.0.9 candidate on the count and filter fixes, and differed on
  eight measured behaviours ([consumer impact §6](../60-research/remedial/consumer-impact-15.0.9-2026-09-23.md#6-nocturne-parity)).
  Its parity suite runs against Nightscout 15.0.3. A shared, current description of the API and a
  test suite that any server can run keep the apps working on both. This is the WHATWG pattern in §6:
  several implementations, one living standard, and shared tests.
- **Building a server and keeping one current are different jobs.** Volunteers built both
  servers. Keeping them current includes work whose timing neither project sets: the vendor clouds
  that the CGM and pump connectors log into. When a vendor changes its service, glucose data stops
  arriving at the site until a fix ships. Changes the vendors forced, from the connectors' commit
  histories and issue trackers:

  | vendor | change the connector had to follow | where |
  |---|---|---|
  | Abbott LibreLinkUp | version header raised to 4.7.0, June 2023 | nightscout-librelink-up |
  | Abbott LibreLinkUp | requests blocked by Cloudflare from late March 2024; fixed 2024-04-02 ([#128](https://github.com/timoschlueter/nightscout-librelink-up/issues/128), 39 comments) | nightscout-librelink-up |
  | Abbott LibreLinkUp | version header raised to 4.12.0, November 2024; China region added, March 2025 | nightscout-librelink-up |
  | Abbott LibreLinkUp | "October 2025 changes", 2025-10-21 (`f52d929`) | nightscout-connect |
  | Abbott LibreLinkUp | new response shape and login handling, 2026-09-22 (`370d9f4`) | nightscout-connect |
  | Medtronic CareLink | OAuth and token-refresh changes, December 2020; care-partner login error 400, June 2023 | minimed-connect-to-nightscout, now deprecated |
  | Dexcom Share | trend field changed from a number to a string, November 2021 | share2nightscout-bridge, now deprecated in favour of nightscout-connect |

  Nocturne carries its own connectors for the same vendors (Dexcom, FreeStyle for LibreLinkUp,
  CareLink, and others; `externals/nocturne/src/Connectors` at `42275c81`), and pins the same
  LibreLinkUp version header, 4.16.0. Each vendor change therefore reaches both servers. A second
  server adds implementations of this work; it does not remove the work or let anyone schedule it.
  A connector test lab and one person watching the vendor clouds (§4) would serve both.
- **The existing sites still need maintenance.** Operators run cgm-remote-monitor on MongoDB today,
  with its own settings, data and hosting. Moving to another server is a migration each operator
  chooses. Until they choose it, their site needs the releases, security fixes and driver upgrades
  described in §2.
- **The roles in §4 serve the whole ecosystem.** The compatibility engineer and the quality and
  security lead would keep the client census, the conformance tests and the security triage open to
  every implementation.

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

For a clinician or clinical researcher:

- Whether §1a summarises the four studies fairly, including their comparators, the time-below-range
  difference in the Canadian study and the selection of participants; whether other studies (for
  example of Trio, or head-to-head comparisons published since) belong beside them; and what study
  designs a comparative analysis on the research commons would need before any result is published.

For the maintainers:

8. Whether the three roles in §4 are the right ones.
9. Whether the success measures in §8 are the right ones.
10. For the AndroidAPS, Loop, Trio and xDrip+ maintainers: whether §2's release gaps and
    contributor counts describe their projects fairly, and what held their releases.

Assumptions this draft makes:

- the foundation can hold restricted funds for this purpose;
- the maintainers would take part in hiring;
- the team would work in public, like any other contributor.
