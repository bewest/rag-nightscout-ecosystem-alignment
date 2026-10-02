# A sponsored maintenance team for the Nightscout ecosystem — proposal

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Recommendation** (part 3 of the overview; [how the overview is organised](README.md)).
**DRAFT PROPOSAL for discussion.** Written 2026-09-27 against this repository at `de46efc1` and
cgm-remote-monitor `official/dev` `295f1177`; revised through 2026-10-02. The facts it relies on are
on the [evidence page](observations/ECOSYSTEM-EVIDENCE.md), and the comparisons in
[perspective](perspective/INFRASTRUCTURE-TRANSITION.md). Where it touches employment,
contracting, tax or the foundation's exempt status, it needs review by the foundation's counsel and
accountant before any decision rests on it (§9). Nothing here is decided.*

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

The facts this section relies on are on the [evidence page](observations/ECOSYSTEM-EVIDENCE.md).

**Open-source AID has published evidence behind it.** It improved time in range over pump therapy in
a randomised trial and, in real-world comparisons, matched or exceeded commercial systems on time in
range, with differences in time below range that matter for some people
([evidence §6](observations/ECOSYSTEM-EVIDENCE.md#6-published-clinical-evidence-for-open-source-aid),
with each study's caveats).

**The assets grew in the open, over more than ten years**, across 62 repositories from device
drivers to vendor-cloud connectors, most of them in GitHub organisations run by volunteers or under
personal accounts ([evidence §1](observations/ECOSYSTEM-EVIDENCE.md#1-what-the-ecosystem-consists-of)).
A foundation taking stewardship responsibility for these assets is how the software behind that
evidence keeps working, and how new evidence can be built on it.

**Today the cost falls on people with diabetes and individual maintainers.** Their own time pays for
the review, releases, vendor changes and security response of §3. After the xz-utils backdoor in
2024, CISA wrote that "the burden of security shouldn't fall on an individual open source
maintainer" ([QUALITY-SYSTEM §7](QUALITY-SYSTEM.md#7-histories-that-map)). Full-time stewards
funded by the foundation would move that cost off the people the software serves.

**Better evidence needs a shared commons.** Which system does better, for whom and in which
circumstances (children, pregnancy, exercise, different pumps and sensors, different settings) is
the question the published studies cannot yet answer. The
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

**The ecosystem depends on one shared server.** Many other apps read and write their data through
it, and a change there reaches every one of them; a second server implements the same API
([evidence §2](observations/ECOSYSTEM-EVIDENCE.md#2-what-depends-on-the-shared-server)).

**Releases have come in long gaps, here and across the ecosystem.** Every main project has had gaps
of similar length in the same years, and in cgm-remote-monitor the number of people committing fell
before releases slowed ([evidence §3](observations/ECOSYSTEM-EVIDENCE.md#3-releases-and-contributors-across-the-main-projects)).
A gap in one project's history, read on its own, says little about the diligence of the people who
maintain it. Set beside the others and the contributor counts, it reads as the same work carried by
fewer people. Each project's maintainers are the right people to say what held their releases (§9).

**Important work can wait for years.** The MongoDB 5 driver upgrade was first proposed in 2022 and
shipped in 2026, while hosting providers retire old database versions on their own schedule
([evidence §3](observations/ECOSYSTEM-EVIDENCE.md#3-releases-and-contributors-across-the-main-projects)).

**Much of the coming work is already dated.** Between now and the end of 2027 the ecosystem meets
Apple's medical-device status declaration, Xcode 27, Android developer verification for all
installations, Node 22 and Heroku-22 end of life, and MongoDB 7.0 end of life, each on the vendor's
calendar, not a volunteer's ([evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars)).

**2026 shows what steady attention produces.** Five releases so far this year, and a 15.0.9
candidate built, tested and recorded in four weeks
([how 15.0.9 was made](../../releases/cgm-remote-monitor-15.0.9/colophon.md)).

## 3. Where the time goes

Much of the engineering in 2026 was done with AI coding agents under a maintainer's direction. That
changed what limits progress. Writing a fix is now the cheap part. The steps that still need a
person are the ones this proposal would fund: review, specialist security and safety review,
decisions, hand checks, checks on real client systems, dependency-alert triage and the backlog
([evidence §4](observations/ECOSYSTEM-EVIDENCE.md#4-where-the-maintenance-time-goes-today); the
current review load is the generated table on
[PROGRAMME-STATUS](PROGRAMME-STATUS.md#the-two-constraints-neither-of-them-engineering)).

Today all of this depends on a few people. Some of them are paid for part of their time by the
commercial hosts they work for, on terms each host sets, and those arrangements differ in scope,
availability and the compliance obligations each host carries. No one is paid to do this work for
the ecosystem as a whole, on published terms, with a public report. When those few people's time
runs short, the work waits.

## 4. What the team would do

A starting shape. The board and maintainers would settle the final one.

| role | what it does | why it is needed |
|---|---|---|
| **Release and review lead** | reviews pull requests, keeps the release process running on a published schedule, tags releases with the maintainers | review and release are where work waits (§3) |
| **Ecosystem compatibility engineer** | keeps the census of client apps current; runs the real-system checks with Loop, Trio, AndroidAPS and xDrip+ builders; turns what clients actually send into tests; watches the vendor clouds the connectors log into and keeps a connector test lab that any server can use | a server change reaches every client (§2), and a vendor change reaches every server (§6a) |
| **Quality and security lead** (part time at first) | triages security reports and dependency alerts, keeps the defect register and test records, is the named reviewer for security and safety items | the SECURITY and SAFETY items in the reviewer-load table name a kind of reviewer, and most name no individual |

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

How Zig, the Haskell Foundation, CNCF, WHATWG, W3C, the PSF, the Sovereign Tech Fellowship,
OpenStreetMap and SQLite fund and staff their work is in
[PRECEDENTS: how other organisations fund and staff the work](perspective/PRECEDENTS.md#how-other-organisations-fund-and-staff-the-work),
read from each organisation's own pages and IRS Form 990 summaries. What this proposal takes from
them:

- Where paid staff exist, the volunteer or project maintainers keep technical authority; §5 keeps
  it so here.
- Money tied to one sponsor or a few donors is the usual weak point; option C and E (§7) spread it.
- The smallest organisations that pay for code (Zig, the PSF residencies) spend almost all of it on
  engineering; §4 is three engineering roles.
- Companies that build on the commons pay for work and assurance, not for control, and commercial
  offerings prove they track the same upstream with the same public tests; the rules that would keep
  it so here are in [COLLABORATION-MODEL](COLLABORATION-MODEL.md) §5.

## 6a. More than one server

Nightscout is no longer the only server that speaks its API. Nocturne is a second implementation,
with its own design and visual language, so for operators it is an alternative, and choosing it is
each operator's decision ([evidence §2](observations/ECOSYSTEM-EVIDENCE.md#2-what-depends-on-the-shared-server)).

A second server makes this proposal more necessary, not less:

- **Client apps depend on behaviour, not on which server provides it.** The two servers already
  differ on eight measured behaviours, and Nocturne's parity suite targets an older Nightscout. A
  shared, current description of the API and a test suite that any server can run keep the apps
  working on both. This is the WHATWG pattern in §6: several implementations, one living standard,
  and shared tests.
- **Building a server and keeping one current are different jobs.** Volunteers built both
  servers. Keeping them current includes work whose timing neither project sets: the vendor clouds
  that the CGM and pump connectors log into. When a vendor changes its service, glucose data stops
  arriving at the site until a fix ships. Both servers carry connectors for the same vendors, so each
  vendor change reaches both ([evidence §5](observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars)).
  A second server adds implementations of this work; it does not remove the work or let anyone
  schedule it. A connector test lab and one person watching the vendor clouds (§4) would serve both.
- **The existing sites still need maintenance.** Moving to another server is a migration each
  operator chooses. Until they choose it, their site needs the releases, security fixes and driver
  upgrades described in §2.
- **The roles in §4 serve the whole ecosystem.** The compatibility engineer and the quality and
  security lead would keep the client census, the conformance tests and the security triage open to
  every implementation.

## 7. Options

| option | what it is | first-year cost | trade-off |
|---|---|---|---|
| A. Release and review lead only | one person, fulltime | [board to fill in] | smallest step; one person is still a single point of failure |
| B. The three roles in §4 | two fulltime, one part time | [board to fill in] | covers review, compatibility and security; needs sustained funding |
| C. Grant-funded fixed term | option A or B for 12–18 months from a grant | per grant | tests the model before a long-term commitment; ends when the grant ends |
| D. No change | volunteers, and the part-time paid arrangements individual hosts make (§3) | none to the foundation | keeps today's pattern of long release gaps; the requirements others ask of the server (release schedule, security response, vendor changes) stay with whoever has time |
| E. Companies pay for assurance | hosts and companies that build on Nightscout buy release evidence for their own quality systems, fixes on the release line they run, or test runs in their configuration, on published terms ([collaboration rule 8](COLLABORATION-MODEL.md#5-proposed-rules-for-working-together)); the money funds A or B | depends on demand | evidence and fixes stay public, so free users get the same releases; needs buyers, and adds the counsel questions in COLLABORATION-MODEL §8 |

Option E can be combined with A, B or C. The board fills in the costs (§9). For reference, the
Sovereign Tech Fellowship pays €64k–€82k a year for an employed two-year post, and Zig paid
$460,625 to its contractors and one employee in 2024 (§6).

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

6. Cost ranges for options A–C, which funding sources to approach, and whether to test demand for
   option E with the hosting providers (COLLABORATION-MODEL decision 6).
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
