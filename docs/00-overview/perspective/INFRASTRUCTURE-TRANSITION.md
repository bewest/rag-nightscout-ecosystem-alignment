# When a DIY ecosystem becomes infrastructure

*For the Nightscout Foundation board, the maintainers of the ecosystem projects, and the community.
**Perspective** (part 2 of the overview; [how the overview is organised](../README.md)). Living page,
written 2026-10-02 against this repository at `e3d7b65c`. It offers a frame for reading the
[observations](../observations/ECOSYSTEM-EVIDENCE.md) and sets other communities' experience beside
them. Where it interprets, it says so. It makes no request; the author's recommendations are in
part 3. Every outside quote was read at its source on the date given; re-read before quoting.*

## 1. The question

Open source describes rights: to use, study, change and share software. It says nothing about
whether the work of keeping that software current is paid. Many people's picture of open source is
still of volunteers working in their spare time, and for most projects that picture is accurate:
in Tidelift's 2024 survey of maintainers, 60% described themselves as unpaid hobbyists
([histories annex §B9](../../60-research/programme/stack-census-2026-09-30/histories.md#b9-studies-on-volunteer-and-paid-maintainers)).

Some communities have reached a point where they changed how parts of their work are organised and
paid for. This page asks what those points had in common, and which of those conditions can be
measured for the Nightscout ecosystem.

## 2. No single threshold

None of the communities below adopted a rule such as "past a number of users, pay maintainers".
They changed after conditions accumulated, often made visible by one event. The conditions recur
across the cases, and in this page they are called *gravity*: what a project accumulates that makes
its work harder to leave to whoever has time. The term is this page's, not a standard one.

| kind of gravity | what accumulates | what the Nightscout observations show |
|---|---|---|
| dependency | other software relies on behaviour staying compatible | 40 client repositories mapped against 15 parts of the API; a second server implementing the same API ([evidence §2](../observations/ECOSYSTEM-EVIDENCE.md#2-what-depends-on-the-shared-server)) |
| assets | code, schemas, test suites, protocol knowledge, documentation | 62 repositories, more than 35,000 test declarations, 14 device protocols with 41 independent implementations ([evidence §1](../observations/ECOSYSTEM-EVIDENCE.md#1-what-the-ecosystem-consists-of)) |
| deadlines set by others | platform, runtime and vendor dates that arrive regardless of anyone's free time | ten dated platform and runtime events to the end of 2027, and vendor-cloud changes the connectors have had to follow since 2020, with no date to plan against ([evidence §5](../observations/ECOSYSTEM-EVIDENCE.md#5-work-that-arrives-on-other-organisations-calendars)) |
| concentration | important work resting on few people | in 25 of 56 active repositories one author made 80% or more of the year's commits; cgm-remote-monitor had 11 to 18 authors a year from 2021 to 2025; review in its work queue routes mostly to one maintainer ([evidence §1, §3, §4](../observations/ECOSYSTEM-EVIDENCE.md#4-where-the-maintenance-time-goes-today)) |
| safety and security | consequences of a mistake beyond inconvenience | Nightscout is a secondary display for CGM and pump data, with alarms; the backfix register's operator-exposure table counts defects present in the shipping release ([PROGRAMME-STATUS](../PROGRAMME-STATUS.md)) |
| commercial use | businesses that depend on dependable releases | hosted providers listed in the Nightscout documentation; paid part-time arrangements set by individual hosts ([evidence §4](../observations/ECOSYSTEM-EVIDENCE.md#4-where-the-maintenance-time-goes-today)); revenue and site counts not measured |
| institutions | researchers, regulators, manufacturers and nonprofits interacting with the work | published trials and observational studies ([evidence §6](../observations/ECOSYSTEM-EVIDENCE.md#6-published-clinical-evidence-for-open-source-aid)); a nonprofit's FDA clearance built on DIY Loop ([histories annex §B8](../../60-research/programme/stack-census-2026-09-30/histories.md#b8-the-ecosystems-own-history-wearenotwaiting-openaps-tidepool-loop)) |
| users | people affected by failures who never meet the maintainers | **not measured**: no count of sites or users exists in this repository |
| jurisdictions | identity, consent, hosting and data rules that differ by country | **not measured**: no count of sites by country; the regulatory questions are listed for counsel in [ECOSYSTEM-PROGRAMME §9](../ECOSYSTEM-PROGRAMME.md#9-the-foundations-role-and-points-to-decide) |

*Interpretation:* on the dimensions that can be measured from this repository, the ecosystem has
accumulated each kind of gravity. Two dimensions, users and jurisdictions, have no measurement
here, and claims about them should wait for one.

## 3. What other communities did

Each row was read at its source on 2026-10-02 unless it says otherwise. Fuller histories on one
template are in [PRECEDENTS](PRECEDENTS.md).

| community | what made it change | what became paid | what stayed with the community |
|---|---|---|---|
| OpenSSL and the Linux Foundation's Core Infrastructure Initiative, 2014 | Heartbleed. The Linux Foundation: "The idea that open source just happens in someone's basement is a myth. As the software has grown more complex, so has the need for full time developer support." ([LF, 2014](https://www.linuxfoundation.org/blog/never-let-a-good-crisis-go-to-waste-core-infrastructure-initiative/)); folded into OpenSSF in 2020 | funded developers, audits and test infrastructure for critical projects | the projects' own maintainers and governance |
| Linux kernel | companies came to depend on it. "Seventy-five percent of all kernel development is done by developers who are being paid for their work" ([LF report, 2012](https://www.linuxfoundation.org/press-release/the-linux-foundation-releases-annual-linux-development-report/)) | most development, by employers' staff | the maintainer hierarchy decides what merges |
| OpenStreetMap Foundation | "Given that volunteer work has not proven to be sufficient in the past, support through paid development is necessary"; "An all volunteer Board has proven insufficient to execute on all Foundation needs" ([Strategic Plan](https://osmfoundation.org/wiki/Strategic_Plan)) | core-systems work and full-time system monitoring, under a [Hiring Framework](https://osmfoundation.org/wiki/Hiring_Framework) that avoids "paid leadership or decision-making positions" | working groups, so that "the overall course of the OSMF is driven by community members as opposed to a paid body of staff" |
| Django Software Foundation | review and ticket backlog; after a pilot, "a full-time, ongoing Django Fellow" from March 2015 ([DSF, 2015-03-06](https://www.djangoproject.com/weblog/2015/mar/06/welcome-our-full-time-django-fellow/)) | triage, review and release chores | feature work and technical decisions |
| Python Software Foundation | review and security load on volunteer core developers; Developers-in-Residence from July 2021, each seat funded by a named sponsor (Alpha-Omega and Bloomberg among them, [PSF](https://www.python.org/psf/developersinresidence/)) | triage, review, build monitoring, security response | the elected Steering Council |
| Home Assistant / Open Home Foundation | a founder-linked company had paid the maintainers for years; in 2024 a nonprofit took ownership, "funded by commercial partner fees and donations", supporting "more than 50 full-time employees" ([structure](https://www.openhomefoundation.org/structure/)) | the staff working on foundation projects | contributions from the wider community |
| Germany's Sovereign Tech Agency | public dependence on open infrastructure; set up "on the basis of a decision by the German Bundestag" ([about](https://www.sovereign.tech/about)); "A total of €33.6 million has been invested in 96 technologies" ([newsletter, November 2025](https://www.sovereign.tech/news/newsletter-november-2025)) | maintenance and security work in the projects it funds | each project's own governance |

*Interpretation:* across these cases the paid work was mostly operations, security, triage, review
and release, and technical authority stayed with community bodies. Several communities wrote down
how they would keep it that way before or as they hired.

## 4. The concerns these communities recorded

The worry that paid work changes a volunteer community is not peculiar to Nightscout, and some
communities wrote their concerns down. When OpenStreetMap's board introduced its hiring framework in
2020, the risks it listed included ([osmf-talk, 2020-05-06](https://lists.openstreetmap.org/pipermail/osmf-talk/2020-May/006816.html)):

- "Paid work can have a chilling effect on volunteering."
- "Paid staff has other incentives than volunteers."
- "Paid staff has more power to set direction of the project than a volunteer, if only because of
  the amount of time they have."

The volunteer-only view, in its strongest form, and the rules other projects used to reconcile it
with paid work, are in [QUALITY-SYSTEM §8.2](../QUALITY-SYSTEM.md#82-the-volunteer-only-view-stated-fairly)
and the [histories annex §E](../../60-research/programme/stack-census-2026-09-30/histories.md#e-the-volunteer-only-position-steelman-and-reconciliations).
Debian's 2006 experiment in paying release managers, and what that project drew from it, is in
[QUALITY-SYSTEM §7](../QUALITY-SYSTEM.md#7-histories-that-map).

## 5. What this frame does not show

- **It does not show that paid work is needed.** It shows which conditions other communities faced
  when they chose it, and which of those conditions are present here. Whether and how to respond is
  a decision, and the proposals in part 3 are one author's answer.
- **It does not show that volunteer work is failing.** Most maintainers in the wider open-source world
  are unpaid, and the 2025–26 release record across the ecosystem was more frequent than the years
  before it ([evidence §3](../observations/ECOSYSTEM-EVIDENCE.md#3-releases-and-contributors-across-the-main-projects)).
- **Size differs.** Every community above is larger than this ecosystem, or funded at a scale this
  ecosystem is not. Their structures may transfer; their budgets do not ([PRECEDENTS](PRECEDENTS.md)).
- **Two dimensions are unmeasured** (§2): users and jurisdictions.
